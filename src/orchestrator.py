"""Lazy LangGraph orchestrator for the optional AI command centre."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from src.agent_tools import (
    evaluate_cargo_risk,
    fetch_corridor_conditions,
    query_telemetry_db,
    search_compliance_sop,
)
from src.config import AppConfig, ServiceUnavailableError, load_config


project_root = Path(__file__).resolve().parent.parent


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_agent(config: AppConfig | None = None):
    """Build the AI graph only when the AI page is used."""
    config = config or load_config(project_root)
    if not config.ai_enabled:
        raise ServiceUnavailableError(
            "AI Command Centre is unavailable in demo mode until an AI backend is configured."
        )

    prompt_path = project_root / "src" / "prompts" / "system_prompt.txt"
    try:
        system_instructions = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Unable to load the AI system prompt.") from exc

    try:
        if config.agent_llm == "DEEPSEEK":
            if not config.deepseek_api_key:
                raise ServiceUnavailableError(
                    "DeepSeek is unavailable because its API key is not configured."
                )
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model="deepseek-v4-flash",
                temperature=0,
                openai_api_key=config.deepseek_api_key,
                base_url="https://api.deepseek.com",
                max_tokens=2048,
            )
        else:
            from langchain_ollama import ChatOllama

            llm = ChatOllama(
                model="qwen2.5:7b",
                temperature=0,
                num_predict=1024,
            )
    except ImportError as exc:
        raise ServiceUnavailableError(
            "The configured AI backend is not installed."
        ) from exc

    fde_tools = [
        query_telemetry_db,
        fetch_corridor_conditions,
        search_compliance_sop,
        evaluate_cargo_risk,
    ]
    llm_with_tools = llm.bind_tools(fde_tools)

    def reasoning_node(state: AgentState):
        messages = state["messages"]
        if not any(isinstance(message, SystemMessage) for message in messages):
            messages = [SystemMessage(content=system_instructions), *messages]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    graph_builder = StateGraph(AgentState)
    graph_builder.add_node("reasoner", reasoning_node)
    graph_builder.add_node("tools", ToolNode(fde_tools))
    graph_builder.add_edge(START, "reasoner")
    graph_builder.add_conditional_edges("reasoner", tools_condition)
    graph_builder.add_edge("tools", "reasoner")
    return graph_builder.compile(checkpointer=MemorySaver())


@lru_cache(maxsize=1)
def get_agent():
    """Return the cached AI graph, or raise a typed unavailable error."""
    return create_agent()


if __name__ == "__main__":
    agent = get_agent()
    agent.invoke(
        {"messages": [("user", "Summarize current fleet risk.")]},
        config={"configurable": {"thread_id": "production_test_1"}},
    )
