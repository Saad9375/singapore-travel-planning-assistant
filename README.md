# AI Travel Planning Assistant -- Singapore

## GitHub Repo
GitHub Repo Link - https://github.com/Saad9375/singapore-travel-planning-assistant

A context-aware travel assistant combining a document-based knowledge base (RAG) with live
current-information tools (MCP) for weather and currency conversion.

## 1. Architecture

```
                       ┌─────────────────────┐
                       │   Streamlit UI       │  (app.py)
                       │  chat + history      │
                       └──────────┬───────────┘
                                  │
                        st.session_state (multi-turn memory)
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │   TravelAgent        │  (src/agent.py)
                       │  orchestrator        │
                       └───┬─────────────┬────┘
                           │             │
              always runs  │             │  bound as tools, model decides
                           ▼             ▼
                  ┌────────────────┐   ┌──────────────────────────┐
                  │   TravelRAG    │   │   MCP client (stdio)     │
                  │  (src/rag.py)  │   │  -> src/mcp_server.py    │
                  │  similarity    │   │  - get_weather_forecast  │
                  │  retriever     │   │  - convert_currency      │
                  └───────┬────────┘   └──────────┬────────────────┘
                          │                        │
                          ▼                        ▼
                 ┌─────────────────┐      ┌──────────────────┐
                 │  Chroma vector   │      │ Open-Meteo API    │
                 │  store           │      │ Frankfurter API   │
                 │ (data/vectorstore)│     │ (no API key)       │
                 └─────────────────┘      └──────────────────┘
                          ▲
                          │ embeddings
                 ┌─────────────────┐
                 │ data/raw/*.md    │  <- knowledge base source docs
                 │ + sources.json   │  <- citation metadata
                 └─────────────────┘
```

**Flow per user turn:**
1. The question is embedded and the top-k relevant chunks are retrieved from the vector store
   (RAG always runs -- destination context is useful for nearly every travel question).
2. The LLM is given those chunks plus the two MCP tools (weather, currency) bound via
   `bind_tools`. It decides, per the system prompt, whether the question needs a tool call.
3. If it calls a tool, the request goes over MCP (stdio transport) to `src/mcp_server.py`, which
   hits a free public API and returns structured JSON.
4. The LLM produces a final answer that explicitly labels `[Knowledge Base]`, `[MCP Tool]` and
   `[Recommendation]` content, so each part of a combined response is traceable to where it came
   from -- retrieved fact, live tool result, or the model's own synthesis.
5. The UI shows the answer plus expandable panels listing the KB sources and raw tool calls used.

## 2. Knowledge-base sources

Location: `data/raw/*.md`, with citation metadata in `data/raw/sources.json`.

All content is extracted from **three public Wikivoyage resources**, and the five files cover all
six required topic areas (attractions/neighbourhoods, transport, culture/practical tips, food,
itineraries, indoor/outdoor activities):

| Resource | File(s) built from it | Sections used |
| --- | --- | --- |
| [Wikivoyage: Singapore](https://en.wikivoyage.org/wiki/Singapore) (main article) | `transportation.md`, `food_experiences.md`, `culture_practical_tips.md` | *Get around*; *Eat* (venue listings omitted); *Talk, Stay safe, Stay healthy, Respect, Connect, Cope* |
| [Wikivoyage Singapore district articles](https://en.wikivoyage.org/wiki/Singapore#Districts) (9 pages) | `attractions_neighbourhoods.md` | *Understand* + *See* for Marina Bay, Riverside, Chinatown, Little India, Bugis, Orchard, Sentosa, East Coast, North and West |
| [Wikivoyage: Three days in Singapore](https://en.wikivoyage.org/wiki/Three_days_in_Singapore) | `itineraries.md` | *Understand, Prepare, Day 1, Day 2, Day 3* |

Every file carries an attribution header naming the article, sections, licence and retrieval date,
and every entry in `sources.json` records a `title` and `url` (used for the in-app citation) plus
`provenance` and `license` fields. All text is licensed **CC BY-SA 4.0**, which permits reuse with
attribution. Cross-references to Wikivoyage pages that are not part of this knowledge base are
stripped during extraction, so the assistant never points a user at a page it cannot read.

To add a new source: save the text as a new `.md` file in `data/raw/`, add an entry to
`sources.json` with its `title` and `url`, then re-run ingestion (Section 5). Check the site's reuse
terms first -- Wikivoyage permits reuse with attribution, most commercial tourism sites do not.

## 3. RAG workflow

Implemented in `src/ingest.py` (build-time), `src/rag.py` (retrieval) and `src/agent.py`
(generation):
1. **Load** -- every `.md` file in `data/raw/` (read into `langchain_core` `Document`s), with `source_title`/`source_url`
   attached from `sources.json` as metadata.
2. **Chunk** -- `RecursiveCharacterTextSplitter`, 700 chars / 100 overlap, splitting on markdown
   headers first so related content stays together.
3. **Embed** -- Google `models/gemini-embedding-001` via Gemini (configurable in `.env`). Chunks are
   embedded in batches with a pause between them, because the free tier caps embedding requests per
   minute -- see `EMBED_BATCH_SIZE` / `EMBED_BATCH_PAUSE_SECONDS` in `src/config.py`.
4. **Store** -- persisted locally in Chroma (`data/vectorstore/`).
5. **Retrieve** -- `TravelRAG.retrieve` returns the top-10 chunks by similarity for each question
   (`RETRIEVAL_K`). Retrieval runs on every turn, before the model is called. The corpus is ~230
   chunks; a smaller `k` was too narrow to pull a complete three-day itinerary.
6. **Generate** -- the retrieved chunks are injected into `AGENT_SYSTEM_PROMPT` (`src/prompts.py`)
   and answered by `TravelAgent` in `src/agent.py`, which forbids using outside knowledge and
   requires an explicit "not covered" response when retrieval is empty or irrelevant.
7. **Cite** -- every response tracks which `source_title`/`source_url` pairs were actually used by
   the retrieved chunks, shown in the UI's "Knowledge base sources" panel.

## 4. MCP tools

Implemented as a real MCP server (`src/mcp_server.py`, using the official `mcp` Python SDK's
`FastMCP`), launched by the agent as a stdio subprocess and consumed via `langchain-mcp-adapters`.

| Tool | Backing API | Key required | Failure handling |
|---|---|---|---|
| `get_weather_forecast(destination, days)` | Open-Meteo (geocoding + forecast) | No | Returns `{"error": ...}` on network/lookup failure; agent reports this instead of guessing |
| `convert_currency(amount, from_currency, to_currency)` | Frankfurter API (ECB reference rates) | No | Same explicit `{"error": ...}` pattern |

Tool selection is left to the LLM's native tool-calling (`bind_tools`), guided by clear tool
docstrings and the system prompt rule "don't call these tools for questions the knowledge base
already covers." All tool calls (name, args, raw result) are captured and shown to the user, so
current information is always visibly attributed to "MCP Tool" rather than blended in silently.

## 5. Prompt and context strategy

Full prompt in `src/prompts.py`. Key design choices:
- **Separation of channels**: the model must label output as `[Knowledge Base]`, `[MCP Tool]` or
  `[Recommendation]`, so users can see what's a retrieved fact vs. a live tool result vs. the
  model's own suggestion. The prompt states explicitly that anything the model worked out itself --
  reordering an itinerary, picking indoor alternatives because rain is forecast -- belongs under
  `[Recommendation]` and must never be presented under the other two tags.
- **Recommendations only when asked**: `[Recommendation]` appears for advice and planning questions.
  A plain lookup ("convert 5,000 INR", "what is laksa") is answered and closed, with no padding.
- **Recommendations stay grounded**: synthesis must build on the retrieved chunks and tool results,
  not on the model's own outside knowledge.
- **No fabrication**: explicit rules against inventing destination facts, weather, or exchange
  rates; the model is told to say "not covered" / "tool unavailable" instead.
- **Scoped tool use**: MCP tools are only for current info, not destination facts already in the KB.
- **Multi-turn memory**: prior turns (as LangChain messages) are passed into every call, and the
  prompt explicitly instructs the model to reuse stated preferences (budget, travelling with kids,
  dates) without asking the user to repeat them.
- **Structured output**: bullet points / day-by-day formatting requested for itineraries and lists.

## 6. Setup and running

Developed and tested on **Python 3.11**.

```bash
# 1. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
(or) .\venv\Scripts\Activate.ps1    # for Windows PowerShell 

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
cp .env.example .env            # Windows: copy .env.example .env
# edit .env and set GOOGLE_API_KEY=AIza...
# Get a free key from Google AI Studio: https://aistudio.google.com/app/apikey

# 4. Build the knowledge base (run once, and again after editing data/raw/*.md)
python -m src.ingest            # ~4 min: embeddings are throttled to the free-tier limit

# 5. Launch the app
streamlit run app.py
```

The weather and currency tools use free, keyless public APIs (Open-Meteo, Frankfurter) -- no
additional signup needed. Only the LLM and embeddings require a `GOOGLE_API_KEY`.

### Free-tier quota -- plan around this before demoing

The Google AI Studio free tier is limited enough to interrupt a demo, and the limits are counted
**per project per model**:

- **Chat requests**: roughly 20 `generateContent` requests per day, per model. One question costs
  1 request, but a question that triggers a tool call costs 2-3 (each tool round-trip is its own
  call), so a handful of itinerary questions can exhaust a day's allowance.
- **Embeddings**: a separate quota (100 requests/minute), which is why ingestion is batched.
  Re-ingesting does **not** consume chat quota.

Because the cap is per model, the quickest recovery is to point `LLM_MODEL` in `.env` at a
different model -- it gets its own fresh allowance. Check your live usage at
https://aistudio.google.com/rate-limit. If the cap is hit while the app is running, the UI shows an
explanatory message rather than a traceback (`app.py::friendly_error`).

### Testing the MCP server standalone
```bash
python -m src.mcp_server
```
This starts the server on stdio; it's normally launched automatically as a subprocess by the agent.

## 7. Minimum acceptance criteria -- where each is satisfied

| Criterion | Where |
|---|---|
| Knowledge base from 3+ resources | `data/raw/*.md` + `sources.json` (see Section 2 for per-file provenance) |
| Embedding-based semantic retrieval | `src/ingest.py`, `src/rag.py` (Chroma + Gemini embeddings) |
| Grounded answers with source references | `src/rag.py::TravelRAG.retrieve` + `src/agent.py::TravelAgent._run_turn_async`, UI "Knowledge base sources" panel |
| Weather via MCP | `src/mcp_server.py::get_weather_forecast` |
| Currency conversion via MCP | `src/mcp_server.py::convert_currency` |
| Combined RAG + MCP response | `src/agent.py::TravelAgent._run_turn_async` |
| Multi-turn context | `app.py` session state + `chat_history` passed into every agent call |
| Appropriate tool selection | LLM tool-calling guided by tool docstrings + system prompt rule |
| Missing-knowledge / tool-failure handling | `prompts.py` "not covered" rules + empty-context fallback in `agent.py`; `mcp_server.py` `{"error": ...}` path; `app.py::friendly_error` for API failures |
| Simple, usable interface | `app.py` (Streamlit chat with source/tool-call transparency) |

## 8. Repository layout

```
travel_assistant/
├── app.py                   # Streamlit UI
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── raw/                 # knowledge-base source documents + sources.json metadata
│   └── vectorstore/         # generated by `python -m src.ingest` (git-ignored)
├── src/
│   ├── __init__.py
│   ├── config.py            # settings, loaded from .env
│   ├── ingest.py            # RAG build step
│   ├── rag.py               # vector store + retriever
│   ├── mcp_server.py        # MCP tools (weather, currency)
│   ├── agent.py             # orchestrator combining RAG + MCP
│   └── prompts.py           # system prompt
└── docs/
    └── sample_qa.md         # sample questions and example responses
```

## 9. Demo checklist (for the required walkthrough video)

1. Ask a pure destination question -> show RAG answer + cited sources.
2. Ask a pure weather or currency question -> show the MCP tool call + result in the expander.
3. Ask the required combined scenario ("3-day itinerary ... adjust for weather") -> show labeled
   `[Knowledge Base]`, `[MCP Tool]` and `[Recommendation]` sections in one answer.
4. Have a 2-turn conversation where turn 1 states a preference (e.g. "travelling with kids") and
   turn 2 asks for an itinerary -> show the preference carried through.
5. Ask something the knowledge base doesn't cover -> show the explicit "not covered" response.

## 10. Troubleshooting

**`429 RESOURCE_EXHAUSTED` / `GoogleRateLimitError`**
The free-tier daily quota for that model is used up. Set a different `LLM_MODEL` in `.env` and
restart -- quota is counted per model, so another model has its own allowance. See Section 6.

**`404 ... is not found for API version v1beta` (embeddings or chat)**
Google retires models, and a retired model can still appear in `ListModels`. List what your key can
actually use, then update `EMBEDDING_MODEL` / `LLM_MODEL` in `.env`:
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GOOGLE_API_KEY"
```

**`400 API key not valid`**
`GOOGLE_API_KEY` in `.env` is wrong or still the placeholder. A real AI Studio key is 39 characters.

**`NotImplementedError` from `asyncio` when asking a question**
Streamlit runs on Tornado, which installs a selector event loop on Windows; selector loops cannot
spawn the MCP server subprocess. Handled by `_run_async` in `src/agent.py`, which runs each turn on
its own thread with a `ProactorEventLoop`. If you see this, that helper has been bypassed.

**`SSL: CERTIFICATE_VERIFY_FAILED` from the weather or currency tool**
A corporate proxy is re-signing HTTPS with an internal root CA that is in the OS certificate store
but not in certifi's bundle. `src/mcp_server.py` calls `truststore.inject_into_ssl()` to verify
against the OS store instead. Ensure `truststore` is installed; certificates are still fully
verified.

**Ingestion fails partway with a 429**
The corpus exceeded the per-minute embedding quota. Lower `EMBED_BATCH_SIZE` or raise
`EMBED_BATCH_PAUSE_SECONDS` in `src/config.py`, delete `data/vectorstore/`, and re-run.

**Chroma errors after upgrading dependencies, or "the process cannot access the file"**
The on-disk store format is tied to the chromadb major version, and a running Streamlit process
holds the files open. Stop the app, delete `data/vectorstore/`, and re-run `python -m src.ingest`.
