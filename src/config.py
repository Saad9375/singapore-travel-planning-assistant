"""Central configuration for the Travel Planning Assistant."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"
VECTOR_STORE_DIR = BASE_DIR / "data" / "vectorstore"
SOURCES_METADATA_PATH = DATA_DIR / "sources.json"

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# Free-tier request quota is per project PER MODEL, so if one model is exhausted for the day,
# switching LLM_MODEL to another gives a fresh allowance. Flash-lite carries the larger allowance.
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")

# Retrieval settings
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
# The corpus is ~230 chunks; k=4 was tuned for a much smaller one and was too narrow to pull a
# whole three-day itinerary (it returned one day and missed the others).
RETRIEVAL_K = 10

# Similarity search always returns k results, however poor the match. For a question the knowledge
# base does not cover (e.g. a currency conversion) that means ten weak chunks spread across every
# document, which the UI then lists as "sources used" -- making the citations meaningless. Chunks
# that genuinely answer a question score ~0.53-0.64; unrelated ones peak around 0.45, so anything
# below this floor is dropped and a question with no relevant content retrieves nothing at all.
RETRIEVAL_MIN_RELEVANCE = 0.50

# Ingestion pacing. The free Gemini tier allows 100 embedding requests per minute and the
# embedder issues one request per chunk, so ingestion adds chunks in batches and waits
# between them. Raise the batch size / drop the pause if you are on a paid tier.
EMBED_BATCH_SIZE = 50
EMBED_BATCH_PAUSE_SECONDS = 40

DESTINATION = "Singapore"
