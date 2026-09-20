"""
RAG layer: retrieves relevant knowledge-base chunks for a question and generates
a grounded answer, returning the source titles/URLs actually used.
"""
from dataclasses import dataclass, field

from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate

from src import config

RAG_SYSTEM_PROMPT = """You are the destination-knowledge component of a Singapore travel assistant.

Answer the user's question using ONLY the "Knowledge base context" below. Do not use outside
knowledge and do not invent attractions, prices, hours, or facts that are not present in the context.

Rules:
- If the context does not contain enough information to answer, say so explicitly
  (e.g. "The knowledge base doesn't cover that.") instead of guessing.
- Keep the answer concise and structured (use bullet points for lists of places/activities).
- Do not mention weather or currency conversion here -- that is handled elsewhere.

Knowledge base context:
{context}
"""


@dataclass
class RagResult:
    answer: str
    sources: list = field(default_factory=list)   # list of {"title": ..., "url": ...}
    used_knowledge_base: bool = True


class TravelRAG:
    def __init__(self):
        embeddings = GoogleGenerativeAIEmbeddings(
            model=config.EMBEDDING_MODEL, google_api_key=config.GOOGLE_API_KEY
        )
        self.vector_store = Chroma(
            collection_name="singapore_travel_kb",
            embedding_function=embeddings,
            persist_directory=str(config.VECTOR_STORE_DIR),
        )
        # Retrieval goes through similarity_search_with_relevance_scores in retrieve() rather than
        # a plain retriever, so weakly-matching chunks can be dropped -- see RETRIEVAL_MIN_RELEVANCE.
        self.llm = ChatGoogleGenerativeAI(
            model=config.LLM_MODEL, google_api_key=config.GOOGLE_API_KEY, temperature=0.2
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [("system", RAG_SYSTEM_PROMPT), ("human", "{question}")]
        )

    def retrieve(self, question: str):
        """
        Return the chunks that actually match the question.

        Similarity search returns k results no matter how poor the match, so a question the
        knowledge base does not cover still comes back with k weak chunks -- which would then be
        cited as sources. Anything below RETRIEVAL_MIN_RELEVANCE is discarded, so such a question
        correctly retrieves nothing and the assistant answers from the tools alone.
        """
        scored = self.vector_store.similarity_search_with_relevance_scores(
            question, k=config.RETRIEVAL_K
        )
        return [doc for doc, score in scored if score >= config.RETRIEVAL_MIN_RELEVANCE]

    def answer(self, question: str) -> RagResult:
        docs = self.retrieve(question)

        if not docs:
            return RagResult(
                answer="The knowledge base doesn't contain information relevant to that question.",
                sources=[],
                used_knowledge_base=False,
            )

        context = "\n\n---\n\n".join(
            f"[{d.metadata.get('source_title', 'Unknown source')}]\n{d.page_content}" for d in docs
        )
        chain = self.prompt | self.llm
        response = chain.invoke({"context": context, "question": question})

        sources = []
        seen = set()
        for d in docs:
            key = d.metadata.get("source_title")
            if key and key not in seen:
                seen.add(key)
                sources.append({"title": key, "url": d.metadata.get("source_url", "")})

        return RagResult(answer=response.content, sources=sources, used_knowledge_base=True)
