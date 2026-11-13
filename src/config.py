
"""Validated application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


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


def load_config(
    project_root: Path | None = None,
    *,
    require_admin: bool = False,
    require_agent: bool = False,
    load_environment: bool = True,
) -> AppConfig:
    """
    Load and validate application configuration.

    Configuration is loaded from the project's .env file.
    Existing system environment variables take precedence.

    Args:
        project_root: Optional project root directory.
        require_admin: Require SQL administrator credentials.
        require_agent: Require SQL agent credentials.
        load_environment: Load values from the project `.env` file.

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

    # Load project environment variables
    env_file = root / ".env"

    if not env_file.is_file():
        raise ConfigurationError(
            f"Environment file not found: {env_file}"
        )

    if load_environment:
        load_dotenv(dotenv_path=env_file, override=False)

    # ---------------------------------------------------------
    # Configuration helpers
    # ---------------------------------------------------------

    def get_value(name: str, default: str = "") -> str:
        """Read and normalize an environment variable."""
        return os.getenv(name, default).strip()

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

    sql_host = get_required("SQL_SERVER_HOST") or "localhost"

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

    if agent_llm == "DEEPSEEK" and not deepseek_api_key:
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
    )
