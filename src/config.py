
"""Validated application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
import sys
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from dotenv import dotenv_values


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class ServiceUnavailableError(RuntimeError):
    """Raised when an optional external service is not configured."""


@dataclass(frozen=True)
class AppConfig:
    """Application configuration."""

    project_root: Path

    # SQL Server configuration
    sql_host: str
    sql_port: int
    sql_agent_user: str
    sql_agent_password: str
    sql_admin_user: str
    sql_admin_password: str
    sql_database: str
    sql_timeout_seconds: int

    # LLM configuration
    agent_llm: str
    deepseek_api_key: str | None
    pinecone_api_key: str | None
    embeddings_model: str
    local_embedding_model: str
    reefertwin_mode: str
    ai_enabled: bool


def load_config(
    project_root: Path | None = None,
    *,
    require_admin: bool = False,
    require_agent: bool = False,
    load_environment: bool = True,
    secrets: Mapping[str, Any] | None = None,
) -> AppConfig:
    """
    Load and validate application configuration.

    Configuration precedence is environment variables, Streamlit secrets,
    then the optional project `.env` file.

    Args:
        project_root: Optional project root directory.
        require_admin: Require SQL administrator credentials.
        require_agent: Require SQL agent credentials.
        load_environment: Read values from the project `.env` file when present.
        secrets: Optional secret mapping, primarily for isolated tests. When
            omitted, Streamlit secrets are read when available.

    Returns:
        Validated AppConfig instance.

    Raises:
        ConfigurationError: If required configuration is missing
        or a configuration value is invalid.
    """

    # Resolve project root
    root = (
        Path(project_root).resolve()
        if project_root
        else Path(__file__).resolve().parent.parent
    )

    env_file = root / ".env"
    dotenv_values_map = (
        dotenv_values(dotenv_path=env_file)
        if load_environment and env_file.is_file()
        else {}
    )
    secret_values = dict(secrets) if secrets is not None else _streamlit_secrets()

    # ---------------------------------------------------------
    # Configuration helpers
    # ---------------------------------------------------------

    def get_value(name: str, default: str = "") -> str:
        """Read and normalize an environment variable."""
        raw_value = os.environ.get(
            name,
            secret_values.get(name, dotenv_values_map.get(name, default)),
        )
        return str(raw_value if raw_value is not None else "").strip()

    def get_required(
        name: str,
        *,
        required: bool = True,
    ) -> str:
        """Read a required environment variable."""
        value = get_value(name)

        if required and not value:
            raise ConfigurationError(
                f"Missing required configuration: {name}. "
                "Set it in the environment or project .env file."
            )

        return value

    def get_integer(
        name: str,
        default: str,
        *,
        minimum: int,
        maximum: int | None = None,
    ) -> int:
        """Read and validate an integer environment variable."""

        raw_value = get_value(name, default)

        try:
            value = int(raw_value)
        except ValueError as exc:
            raise ConfigurationError(
                f"{name} must be an integer."
            ) from exc

        if value < minimum:
            raise ConfigurationError(
                f"{name} must be at least {minimum}."
            )

        if maximum is not None and value > maximum:
            raise ConfigurationError(
                f"{name} must not exceed {maximum}."
            )

        return value

    # ---------------------------------------------------------
    # SQL Server configuration
    # ---------------------------------------------------------

    sql_host = get_value("SQL_SERVER_HOST", "localhost") or "localhost"

    sql_port = get_integer(
        "SQL_SERVER_PORT",
        "1433",
        minimum=1,
        maximum=65535,
    )

    sql_timeout = get_integer(
        "SQL_CONNECT_TIMEOUT_SECONDS",
        "10",
        minimum=1,
    )

    sql_database = get_value("SQL_DATABASE", "master") or "master"

    sql_agent_user = get_value(
        "SQL_AGENT_USER",
        "USR_FDE_RO",
    )

    sql_agent_password = get_required(
        "SQL_AGENT_PASSWORD",
        required=require_agent,
    )

    sql_admin_user = get_required(
        "SQL_ADMIN_USER",
        required=require_admin,
    )

    sql_admin_password = get_required(
        "SQL_ADMIN_PASSWORD",
        required=require_admin,
    )

    # ---------------------------------------------------------
    # LLM configuration
    # ---------------------------------------------------------

    agent_llm = get_value(
        "Agent_llm",
        "OLLAMA",
    ).upper()

    supported_llms = {
        "OLLAMA",
        "DEEPSEEK",
    }

    if agent_llm not in supported_llms:
        raise ConfigurationError(
            f"Unsupported Agent_llm value: {agent_llm}. "
            f"Supported values: {', '.join(sorted(supported_llms))}."
        )

    deepseek_api_key = get_value("DEEPSEEK_API_KEY") or None
    pinecone_api_key = get_value("PINECONE_API_KEY") or None

    if require_agent and agent_llm == "DEEPSEEK" and not deepseek_api_key:
        raise ConfigurationError(
            "DEEPSEEK_API_KEY is required when Agent_llm=DEEPSEEK."
        )

    # ---------------------------------------------------------
    # Embedding configuration
    # ---------------------------------------------------------

    embeddings_model = get_value(
        "Embeddings_model",
        "LOCAL",
    ).upper()

    local_embedding_model = get_value(
        "Local_Embedding_Model",
        "BAAI/bge-m3",
    )

    if not local_embedding_model:
        raise ConfigurationError(
            "Local_Embedding_Model cannot be empty."
        )

    reefertwin_mode = get_value("REEFERTWIN_MODE", "local").lower()
    if reefertwin_mode not in {"local", "demo"}:
        raise ConfigurationError(
            "REEFERTWIN_MODE must be either 'local' or 'demo'."
        )
    ai_enabled = get_value(
        "REEFERTWIN_AI_ENABLED",
        "false" if reefertwin_mode == "demo" else "true",
    ).lower() in {"1", "true", "yes", "on"}

    # ---------------------------------------------------------
    # Return validated configuration
    # ---------------------------------------------------------

    return AppConfig(
        project_root=root,

        sql_host=sql_host,
        sql_port=sql_port,
        sql_agent_user=sql_agent_user,
        sql_agent_password=sql_agent_password,
        sql_admin_user=sql_admin_user,
        sql_admin_password=sql_admin_password,
        sql_database=sql_database,
        sql_timeout_seconds=sql_timeout,

        agent_llm=agent_llm,
        deepseek_api_key=deepseek_api_key,
        pinecone_api_key=pinecone_api_key,
        embeddings_model=embeddings_model,
        local_embedding_model=local_embedding_model,
        reefertwin_mode=reefertwin_mode,
        ai_enabled=ai_enabled,
    )


def _streamlit_secrets() -> dict[str, Any]:
    """Read flat Streamlit secrets without making Streamlit mandatory."""
    if "streamlit" not in sys.modules:
        return {}
    try:
        import streamlit as st
        from streamlit.errors import StreamlitSecretNotFoundError
    except (ImportError, RuntimeError):
        return {}
    try:
        return dict(st.secrets)
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        return {}

