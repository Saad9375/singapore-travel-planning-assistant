"""
Streamlit UI for the AI Travel Planning Assistant.

Run with:
    streamlit run app.py
"""
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from src import config
from src.agent import TravelAgent

st.set_page_config(page_title="Singapore Travel Assistant", page_icon="🧳")
st.title("🧳 Singapore Travel Planning Assistant")
st.caption(
    "Destination knowledge comes from a curated knowledge base (RAG). "
    "Weather and currency come from live MCP tools."
)


@st.cache_resource(show_spinner="Loading knowledge base and connecting to MCP tools...")
def get_agent():
    return TravelAgent()


def friendly_error(exc: Exception) -> str:
    """Turn an exception from a turn into something a user can act on, not a traceback."""
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return (
            f"**Gemini API quota reached for `{config.LLM_MODEL}`.**\n\n"
            "The free tier allows a limited number of requests per model per day. Because the "
            "quota is counted *per model*, the quickest fix is to set a different `LLM_MODEL` in "
            "`.env` and restart -- that model has its own separate allowance. Otherwise, wait for "
            "the daily reset or enable billing on the API key."
        )
    if "API key not valid" in text or "API_KEY_INVALID" in text:
        return (
            "**The Gemini API key was rejected.** Check `GOOGLE_API_KEY` in `.env` -- a valid "
            "AI Studio key is 39 characters long."
        )
    return (
        "**The assistant couldn't complete this turn.**\n\n"
        f"```\n{type(exc).__name__}: {text[:400]}\n```"
    )


if "display_history" not in st.session_state:
    st.session_state.display_history = []   # what's rendered: role, content, sources, tool_calls
if "lc_history" not in st.session_state:
    st.session_state.lc_history = []        # LangChain messages fed back into the agent for context

with st.sidebar:
    st.header("Try asking")
    st.markdown(
        "- What are the must-visit attractions in Singapore?\n"
        "- Suggest activities for a family with children.\n"
        "- What is the weather forecast for the next 3 days?\n"
        "- Convert INR 60,000 to SGD.\n"
        "- Plan a 3-day itinerary and adjust it for the weather forecast.\n"
        "- I have a budget of INR 60,000 -- convert it to SGD and suggest a 3-day trip."
    )
    if st.button("Clear conversation"):
        st.session_state.display_history = []
        st.session_state.lc_history = []
        st.rerun()

for turn in st.session_state.display_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("sources"):
            with st.expander("📚 Knowledge base sources used"):
                for s in turn["sources"]:
                    st.markdown(f"- [{s['title']}]({s['url']})" if s["url"] else f"- {s['title']}")
        if turn.get("tool_calls"):
            with st.expander("🔧 MCP tool calls used"):
                for tc in turn["tool_calls"]:
                    st.markdown(f"**{tc['name']}**  \nArgs: `{tc['args']}`  \nResult: `{tc['result']}`")

question = st.chat_input("Ask about your Singapore trip...")

if question:
    st.session_state.display_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    agent = get_agent()
    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                result = agent.run_turn(question, chat_history=st.session_state.lc_history)
        except Exception as exc:  # noqa: BLE001 -- a failed turn must not take down the whole app
            message = friendly_error(exc)
            st.error(message)
            st.session_state.display_history.append({"role": "assistant", "content": message})
            st.stop()

        st.markdown(result.answer)
        if result.kb_sources:
            with st.expander("📚 Knowledge base sources used"):
                for s in result.kb_sources:
                    st.markdown(f"- [{s['title']}]({s['url']})" if s["url"] else f"- {s['title']}")
        if result.tool_calls:
            with st.expander("🔧 MCP tool calls used"):
                for tc in result.tool_calls:
                    st.markdown(f"**{tc['name']}**  \nArgs: `{tc['args']}`  \nResult: `{tc['result']}`")

    st.session_state.display_history.append(
        {
            "role": "assistant",
            "content": result.answer,
            "sources": result.kb_sources,
            "tool_calls": result.tool_calls,
        }
    )
    st.session_state.lc_history.append(HumanMessage(content=question))
    st.session_state.lc_history.append(AIMessage(content=result.answer))
