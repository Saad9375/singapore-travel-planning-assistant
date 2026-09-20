"""
The orchestrator: for every user turn it
  1. Always runs RAG retrieval against the knowledge base (cheap, and destination
     context is useful for almost every travel question).
  2. Gives the LLM access to the MCP tools (weather, currency) via an MCP client
     connected to src/mcp_server.py over stdio.
  3. Lets the LLM decide -- through normal tool-calling -- whether it needs to call
     a tool for this specific question.
  4. Returns a final answer plus a structured trace of what was used (KB sources,
     tool calls + their raw results) so the UI can show "how the answer was built".
"""
import asyncio
import concurrent.futures
import sys
from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from src import config
from src.rag import TravelRAG
from src.prompts import AGENT_SYSTEM_PROMPT

MCP_SERVER_SCRIPT = str((config.BASE_DIR / "src" / "mcp_server.py").resolve())


def _message_text(message: AIMessage) -> str:
    """
    Flatten an AIMessage's content to plain text.

    langchain-core 1.x no longer guarantees a plain string: Gemini 3 replies arrive as a
    list of typed content blocks (text blocks plus thought-signature metadata). The UI
    renders this with st.markdown, so pull out just the text.
    """
    content = message.content
    if isinstance(content, str):
        return content

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


def _run_async(coro_factory):
    """
    Run an async coroutine to completion from synchronous code.

    Streamlit runs on Tornado, which installs WindowsSelectorEventLoopPolicy on Windows.
    A SelectorEventLoop cannot spawn subprocesses (loop.subprocess_exec raises
    NotImplementedError), and the MCP stdio client needs to launch mcp_server.py as one.
    So we run the coroutine on its own thread with a loop that supports subprocesses --
    ProactorEventLoop on Windows -- without disturbing the loop Streamlit is using.
    """

    def runner():
        loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_factory())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(runner).result()


@dataclass
class TurnResult:
    answer: str
    kb_sources: list = field(default_factory=list)     # [{"title":..., "url":...}]
    tool_calls: list = field(default_factory=list)      # [{"name":..., "args":..., "result":...}]
    used_knowledge_base: bool = False


class TravelAgent:
    def __init__(self):
        self.rag = TravelRAG()
        self.llm = ChatGoogleGenerativeAI(
            model=config.LLM_MODEL, google_api_key=config.GOOGLE_API_KEY, temperature=0.3
        )
        self.mcp_client = MultiServerMCPClient(
            {
                "travel_tools": {
                    # sys.executable, not "python": guarantees the server subprocess runs
                    # in this venv (where mcp is installed) regardless of PATH.
                    "command": sys.executable,
                    "args": [MCP_SERVER_SCRIPT],
                    "transport": "stdio",
                }
            }
        )

    async def _run_turn_async(self, question: str, chat_history: list) -> TurnResult:
        # 1. Always retrieve KB context up front.
        kb_docs = self.rag.retrieve(question)
        used_kb = len(kb_docs) > 0
        kb_context = "\n\n---\n\n".join(
            f"[{d.metadata.get('source_title', 'Unknown source')}]\n{d.page_content}" for d in kb_docs
        ) or "(No relevant knowledge-base content found for this question.)"

        kb_sources = []
        seen = set()
        for d in kb_docs:
            title = d.metadata.get("source_title")
            if title and title not in seen:
                seen.add(title)
                kb_sources.append({"title": title, "url": d.metadata.get("source_url", "")})

        # 2. Load MCP tools and bind them to the LLM.
        tools = await self.mcp_client.get_tools()
        llm_with_tools = self.llm.bind_tools(tools)
        tools_by_name = {t.name: t for t in tools}

        system_prompt = AGENT_SYSTEM_PROMPT.format(destination=config.DESTINATION, kb_context=kb_context)
        messages = [SystemMessage(content=system_prompt)] + chat_history + [HumanMessage(content=question)]

        tool_call_trace = []

        # 3. Tool-calling loop (max 2 rounds is plenty for weather+currency style tools).
        for _ in range(3):
            ai_msg: AIMessage = await llm_with_tools.ainvoke(messages)
            messages.append(ai_msg)

            if not ai_msg.tool_calls:
                return TurnResult(
                    answer=_message_text(ai_msg),
                    kb_sources=kb_sources,
                    tool_calls=tool_call_trace,
                    used_knowledge_base=used_kb,
                )

            for call in ai_msg.tool_calls:
                tool = tools_by_name.get(call["name"])
                if tool is None:
                    result = {"error": f"Unknown tool '{call['name']}'"}
                else:
                    try:
                        result = await tool.ainvoke(call["args"])
                    except Exception as e:  # noqa: BLE001 -- surface any tool failure, don't crash the turn
                        result = {"error": f"Tool '{call['name']}' failed: {e}"}

                tool_call_trace.append({"name": call["name"], "args": call["args"], "result": result})
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"])
                )

        # Safety net if the loop above didn't return (shouldn't normally happen).
        final = await llm_with_tools.ainvoke(messages)
        return TurnResult(
            answer=_message_text(final),
            kb_sources=kb_sources,
            tool_calls=tool_call_trace,
            used_knowledge_base=used_kb,
        )

    def run_turn(self, question: str, chat_history: list | None = None) -> TurnResult:
        """Synchronous entry point for use from Streamlit."""
        chat_history = chat_history or []
        return _run_async(lambda: self._run_turn_async(question, chat_history))
