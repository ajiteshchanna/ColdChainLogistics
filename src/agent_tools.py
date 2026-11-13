"""LangChain tools for the existing FDE assistant."""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import requests
from langchain_core.tools import tool
from sqlalchemy import text

from src.config import ConfigurationError, ServiceUnavailableError, load_config
from src.database import create_sql_engine, validate_telemetry_query
from src.domain.models import Shipment, TelemetryEvent
from src.predictive.risk import evaluate_cargo_risk as calculate_cargo_risk


script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent


@lru_cache(maxsize=1)
def _get_config():
    """Load agent configuration only when an external tool is invoked."""
    try:
        return load_config(project_root, require_agent=True)
    except ConfigurationError as exc:
        raise ServiceUnavailableError(
            "Agent integrations are not configured."
        ) from exc


def get_cached_huggingface_embeddings(model_name: str):
    """Cache local embedding weights for Streamlit reruns."""
    import streamlit as st

    @st.cache_resource(show_spinner=False)
    def _load_model(name: str):
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=name,
            model_kwargs={"device": "cpu"},
        )

    return _load_model(model_name)


def _result(status: str, data: object = None, *, message: str | None = None) -> str:
    """Serialize a tool result into a stable, machine-readable envelope."""
    payload: dict[str, object] = {"status": status, "data": data}
    if message:
        payload["message"] = message
    return json.dumps(payload, default=str)


def _get_retriever():
    """Create the SOP retriever only when the SOP tool is actually used."""
    config = _get_config()
    if not config.pinecone_api_key:
        raise ServiceUnavailableError(
            "SOP retrieval is unavailable because Pinecone is not configured."
        )

    from langchain_pinecone import PineconeVectorStore

    if config.embeddings_model == "OPENAI":
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings()
        index_name = "fde-sop-index-openai"
    else:
        local_model_target = config.local_embedding_model
        try:
            import streamlit as st

            if st.runtime.exists():
                embeddings = get_cached_huggingface_embeddings(local_model_target)
            else:
                from langchain_huggingface import HuggingFaceEmbeddings

                embeddings = HuggingFaceEmbeddings(
                    model_name=local_model_target,
                    model_kwargs={"device": "cpu"},
                )
        except ImportError:
            from langchain_huggingface import HuggingFaceEmbeddings

            embeddings = HuggingFaceEmbeddings(
                model_name=local_model_target,
                model_kwargs={"device": "cpu"},
            )
        index_name = "fde-sop-index-local"

    vector_store = PineconeVectorStore(index_name=index_name, embedding=embeddings)
    return vector_store.as_retriever(search_kwargs={"k": 2})


@tool
def query_telemetry_db(sql_query: str) -> str:
    """Execute a bounded SELECT against the semantic telemetry view only."""
    security_error = validate_telemetry_query(sql_query)
    if security_error:
        return _result("error", message=security_error)

    try:
        config = _get_config()
        engine = create_sql_engine(config)
        with engine.connect() as conn:
            cursor = conn.execute(text(sql_query))
            rows = cursor.fetchmany(10)
            return _result(
                "ok",
                {
                    "columns": list(cursor.keys()),
                    "rows": [dict(row._mapping) for row in rows],
                },
                message=(
                    "No records matched the query criteria."
                    if not rows
                    else None
                ),
            )
    except Exception as exc:
        return _result("error", message=f"Database query failed: {exc}")


@tool
def fetch_corridor_conditions(latitude: float, longitude: float) -> str:
    """Fetch current Open-Meteo conditions with explicit degraded states."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return _result(
            "error",
            message=(
                "Latitude must be between -90 and 90 and longitude between "
                "-180 and 180."
            ),
        )

    try:
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={latitude}&longitude={longitude}&current_weather=true"
        )
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        payload = response.json().get("current_weather", {})
        if "temperature" not in payload or "windspeed" not in payload:
            return _result(
                "degraded",
                message="Weather response omitted current conditions.",
            )

        wind = float(payload["windspeed"])
        return _result(
            "ok",
            {
                "latitude": latitude,
                "longitude": longitude,
                "temperature_c": payload["temperature"],
                "wind_speed_kph": wind,
                "congestion_index": 8.5 if wind > 10.0 else 2.5,
                "status_note": (
                    "High Transit Disruption" if wind > 10.0 else "Corridor Normal"
                ),
                "source": "open-meteo",
            },
        )
    except Exception as exc:
        return _result("degraded", message=f"Corridor API unavailable: {exc}")


@tool
def search_compliance_sop(query: str) -> str:
    """Search indexed SOPs, returning source metadata and explicit failures."""
    if not query.strip():
        return _result("error", message="An SOP search query is required.")

    try:
        retriever = _get_retriever()
        matched_docs = retriever.invoke(query)
        documents = [
            {
                "source_file": doc.metadata.get("source_file", "SOP"),
                "file_format": doc.metadata.get("file_format", "RAW"),
                "content": doc.page_content,
            }
            for doc in matched_docs
        ]
        return _result(
            "ok",
            {"documents": documents},
            message=(
                "No matching compliance clauses found."
                if not documents
                else None
            ),
        )
    except Exception as exc:
        return _result("degraded", message=f"SOP retrieval unavailable: {exc}")


@tool
def evaluate_cargo_risk(telemetry_json: str, shipment_json: str) -> str:
    """Evaluate threshold risk from serialized telemetry and shipment records."""
    try:
        telemetry_records = json.loads(telemetry_json)
        shipment_record = json.loads(shipment_json)
        if not isinstance(telemetry_records, list) or not isinstance(
            shipment_record, dict
        ):
            raise ValueError("telemetry_json must be a list and shipment_json an object.")
        telemetry = [
            TelemetryEvent(
                **{
                    **record,
                    "observed_at": datetime.fromisoformat(record["observed_at"]),
                }
            )
            for record in telemetry_records
        ]
        shipment = Shipment(**shipment_record)
        assessment = calculate_cargo_risk(telemetry, shipment)
        return _result("ok", assessment.as_dict())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _result("error", message=f"Invalid risk input: {exc}")
    except Exception as exc:
        return _result("error", message=f"Risk evaluation failed: {exc}")


if __name__ == "__main__":
    print(
        query_telemetry_db.invoke(
            "SELECT TOP 2 Latitude, Longitude, Current_Temperature_C "
            "FROM FDE_VIEWS.VW_ACTIVE_FLEET"
        )
    )
    print(fetch_corridor_conditions.invoke({"latitude": 33.77, "longitude": -118.19}))
    print(search_compliance_sop.invoke("What are the temperature rules for fresh perishables?"))
