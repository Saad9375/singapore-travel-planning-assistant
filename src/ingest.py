"""
Builds the RAG knowledge base:
  1. Load markdown files from data/raw/
  2. Attach source-title/url metadata (from sources.json) to every document
  3. Split into overlapping chunks
  4. Embed the chunks
  5. Persist them in a local Chroma vector store

Run this once (and again any time you add/update knowledge-base documents):
    python -m src.ingest
"""
import json
import time

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from src import config


def load_documents():
    """Load every .md file in data/raw and attach citation metadata to it."""
    with open(config.SOURCES_METADATA_PATH, "r", encoding="utf-8") as f:
        sources_meta = json.load(f)

    documents = []
    for md_path in sorted(config.DATA_DIR.glob("*.md")):
        meta = sources_meta.get(md_path.name, {})
        documents.append(
            Document(
                page_content=md_path.read_text(encoding="utf-8"),
                metadata={
                    "source": str(md_path),
                    "source_title": meta.get("title", md_path.stem),
                    "source_url": meta.get("url", ""),
                    "file_name": md_path.name,
                },
            )
        )

    if not documents:
        raise RuntimeError(
            f"No .md documents found in {config.DATA_DIR}. "
            "Add knowledge-base files before running ingestion."
        )
    return documents


def chunk_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"Loaded {len(documents)} document(s) -> split into {len(chunks)} chunk(s).")
    return chunks


def build_vector_store(chunks):
    embeddings = GoogleGenerativeAIEmbeddings(
        model=config.EMBEDDING_MODEL, google_api_key=config.GOOGLE_API_KEY
    )
    config.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)

    vector_store = Chroma(
        collection_name="singapore_travel_kb",
        embedding_function=embeddings,
        persist_directory=str(config.VECTOR_STORE_DIR),
    )

    # Added in batches rather than in one Chroma.from_documents call: the free Gemini tier
    # caps embedding requests per minute, and the whole corpus in one go exceeds it.
    total = len(chunks)
    for start in range(0, total, config.EMBED_BATCH_SIZE):
        batch = chunks[start : start + config.EMBED_BATCH_SIZE]
        vector_store.add_documents(batch)
        done = min(start + config.EMBED_BATCH_SIZE, total)
        print(f"  embedded {done}/{total} chunk(s)")
        if done < total:
            time.sleep(config.EMBED_BATCH_PAUSE_SECONDS)

    print(f"Vector store persisted to {config.VECTOR_STORE_DIR}")
    return vector_store


def main():
    docs = load_documents()
    chunks = chunk_documents(docs)
    build_vector_store(chunks)


if __name__ == "__main__":
    main()
