"""Shared SQL Server connection and read-only query helpers."""

import re
import urllib.parse
from typing import TYPE_CHECKING

from src.config import AppConfig

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


ALLOWED_TELEMETRY_VIEW = "FDE_VIEWS.VW_ACTIVE_FLEET"
_SQL_COMMENT_RE = re.compile(r"(--|/\*|\*/)")
_SQL_UNSAFE_KEYWORDS_RE = re.compile(
    r"\b(JOIN|UNION|EXEC(?:UTE)?|INTO|OPENROWSET|OPENDATASOURCE)\b"
)


def build_sql_connection_string(
    config: AppConfig,
    *,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Build an ODBC connection string from validated configuration."""
    user = username if username is not None else config.sql_agent_user
    secret = password if password is not None else config.sql_agent_password
    if not user or not secret:
        raise ValueError("A SQL username and password are required.")
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={config.sql_host},{config.sql_port};"
        f"DATABASE={config.sql_database};"
        f"UID={user};"
        f"PWD={secret};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )


def create_sql_engine(
    config: AppConfig,
    *,
    username: str | None = None,
    password: str | None = None,
) -> "Engine":
    """Create a pre-pinged SQLAlchemy engine with a bounded login timeout."""
    from sqlalchemy import create_engine

    params = urllib.parse.quote_plus(
        build_sql_connection_string(config, username=username, password=password)
    )
    return create_engine(
        f"mssql+pyodbc:///?odbc_connect={params}",
        connect_args={"timeout": config.sql_timeout_seconds},
        pool_pre_ping=True,
    )


def validate_telemetry_query(sql_query: str) -> str | None:
    """Return a security error for queries outside the semantic telemetry view."""
    normalized = " ".join(sql_query.strip().split()).upper()
    if not normalized:
        return "SECURITY BLOCK: A SQL query is required."
    if not normalized.startswith("SELECT "):
        return "SECURITY BLOCK: Only SELECT operations are authorized."
    if _SQL_COMMENT_RE.search(sql_query) or ";" in sql_query:
        return "SECURITY BLOCK: Comments and multiple SQL statements are not allowed."
    if _SQL_UNSAFE_KEYWORDS_RE.search(normalized):
        return (
            "SECURITY BLOCK: Joins, unions, execution, and external sources "
            "are not allowed."
        )
    view_name = ALLOWED_TELEMETRY_VIEW.replace(".", "")
    normalized_without_brackets = normalized.replace("[", "").replace("]", "")
    if view_name not in normalized_without_brackets.replace(".", ""):
        return (
            "SECURITY BLOCK: Queries must read only from "
            f"{ALLOWED_TELEMETRY_VIEW}."
        )
    return None
