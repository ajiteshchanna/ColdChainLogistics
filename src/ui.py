"""REEFERTWIN Streamlit command centre."""

import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
from langchain_core.messages import HumanMessage, ToolMessage
from sqlalchemy import text

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import ConfigurationError, ServiceUnavailableError, load_config
from src.database import create_sql_engine
from src.orchestrator import get_agent
from src.ui_dashboard import (
    get_store,
    render_ai_command_centre,
    render_audit,
    render_digital_twin,
    render_fleet,
    render_overview,
    render_simulation_lab,
    render_user_manual,
    render_what_if_lab,
)

def write_audit_log(
    session_id: str,
    node_name: str,
    tool_name: str,
    content: str,
    *,
    status: str = "ok",
) -> None:
    """Write an agent trace and surface failures to the active operator."""
    try:
        config = load_config(project_root, require_agent=True)
        if config.reefertwin_mode == "demo":
            st.info("Audit logging is unavailable in demo mode.")
            return
        log_engine = create_sql_engine(config)
        with log_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO FDE_VIEWS.AgentAuditLog
                        (SessionID, NodeExecuted, ToolName, Content, CorrelationID, Status)
                    VALUES (
                        :session_id, :node_name, :tool_name, :content,
                        :correlation_id, :status
                    )
                    """
                ),
                {
                    "session_id": session_id,
                    "node_name": node_name,
                    "tool_name": tool_name,
                    "content": content,
                    "correlation_id": session_id,
                    "status": status,
                },
            )
    except Exception:
        st.warning("Audit logging is unavailable because SQL Server is not configured.")


def render_chat() -> None:
    """Render the existing LangGraph chat without mutating twin state."""
    try:
        agent = get_agent()
    except ServiceUnavailableError as exc:
        st.info(str(exc))
        return
    except Exception:
        st.error("AI Command Centre is unavailable. Check its configured backend.")
        return

    if "ui_messages" not in st.session_state:
        st.session_state.ui_messages = []
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    thread_config = {"configurable": {"thread_id": st.session_state.thread_id}}

    for entry in st.session_state.ui_messages:
        with st.chat_message(entry["role"]):
            for trace in entry.get("traces", []):
                with st.expander(f"{trace['type']}: {trace['name']}"):
                    st.json(trace.get("args", trace.get("content", "")))
            st.markdown(entry["content"])

    user_input = st.chat_input(
        "Query fleet telemetry, corridor updates, or compliance thresholds..."
    )
    if not user_input:
        return
    st.session_state.ui_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    final_response = ""
    traces: list[dict[str, object]] = []
    with st.chat_message("assistant"):
        with st.status("Running evidence-backed analysis...", expanded=True) as status:
            try:
                events = agent.stream(
                    {"messages": [HumanMessage(content=user_input)]},
                    config=thread_config,
                    stream_mode="updates",
                )
                for event in events:
                    for node_name, node_state in event.items():
                        if node_name == "reasoner":
                            latest_msg = node_state["messages"][-1]
                            for tool_call in getattr(latest_msg, "tool_calls", []):
                                traces.append(
                                    {
                                        "type": "tool_input",
                                        "name": tool_call["name"],
                                        "args": tool_call["args"],
                                    }
                                )
                                write_audit_log(
                                    st.session_state.thread_id,
                                    "reasoner",
                                    tool_call["name"],
                                    json.dumps(tool_call["args"]),
                                )
                            if latest_msg.content:
                                final_response = latest_msg.content
                        elif node_name == "tools":
                            for message in node_state.get("messages", []):
                                if isinstance(message, ToolMessage):
                                    traces.append(
                                        {
                                            "type": "tool_output",
                                            "name": message.name or "unknown",
                                            "content": message.content,
                                        }
                                    )
                                    write_audit_log(
                                        st.session_state.thread_id,
                                        "tools",
                                        message.name or "unknown",
                                        message.content,
                                    )
                status.update(label="Analysis complete", state="complete")
            except Exception:
                status.update(label="Analysis failed", state="error")
                st.error("Agent execution failed. Check the configured AI backend.")
        if final_response:
            st.markdown(final_response)
            st.session_state.ui_messages.append(
                {"role": "assistant", "content": final_response, "traces": traces}
            )


def render_audit_logs() -> None:
    with st.form("admin_auth_form"):
        input_user = st.text_input("Admin username")
        input_pass = st.text_input("Admin password", type="password")
        submit_admin = st.form_submit_button("Authenticate & load logs")
    if not submit_admin:
        return
    try:
        admin_config = load_config(project_root, require_admin=True)
    except ConfigurationError as exc:
        st.error(str(exc))
        return
    if input_user != admin_config.sql_admin_user or input_pass != admin_config.sql_admin_password:
        st.error("Invalid administrator credentials.")
        return
    try:
        admin_engine = create_sql_engine(
            admin_config,
            username=input_user,
            password=input_pass,
        )
        with admin_engine.connect() as conn:
            frame = pd.read_sql(
                text(
                    """
                    SELECT LogID, Timestamp, SessionID, NodeExecuted,
                           ToolName, Content, CorrelationID, Status
                    FROM FDE_VIEWS.AgentAuditLog
                    ORDER BY Timestamp DESC
                    """
                ),
                conn,
            )
        st.success("Authenticated successfully as Admin.")
        st.dataframe(frame, hide_index=True, use_container_width=True)
    except Exception:
        st.error("Audit log retrieval failed. Verify the configured SQL Server.")


st.set_page_config(
    page_title="REEFERTWIN Command Centre",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
        .stApp { background-color: #0B0E14; color: #E2E8F0; }
        div[data-testid="stSidebar"] { background-color: #111622; }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("REEFERTWIN")
    st.selectbox("Scenario", ["Demo baseline"])
    st.checkbox("Pause auto-refresh", value=True)
    page = st.radio(
        "Command centre",
        [
            "Overview",
            "Digital Twin",
            "Fleet",
            "Simulation Lab",
            "What-if Lab",
            "AI Command Centre",
            "Audit",
            "User Manual",
        ],
    )
    if st.button("Refresh projection", use_container_width=True):
        st.rerun()
    st.caption("Refresh is read-only. Simulation advances only from Simulation Lab.")
    if st.button("Clear AI session", use_container_width=True):
        st.session_state.ui_messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

store = get_store()
if page == "Overview":
    render_overview(store)
elif page == "Digital Twin":
    render_digital_twin(store)
elif page == "Fleet":
    render_fleet(store)
elif page == "Simulation Lab":
    render_simulation_lab(store)
elif page == "What-if Lab":
    render_what_if_lab(store)
elif page == "AI Command Centre":
    render_ai_command_centre(render_chat)
elif page == "User Manual":
    render_user_manual()
else:
    render_audit(render_audit_logs)
