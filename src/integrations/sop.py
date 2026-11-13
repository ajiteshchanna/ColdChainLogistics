"""Compliance retrieval result contracts and citation normalization."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComplianceCitation:
    source_file: str
    file_format: str
    content: str
    policy_version: str | None = None


@dataclass(frozen=True)
class ComplianceResult:
    status: str
    citations: tuple[ComplianceCitation, ...]
    message: str | None = None


def normalize_retrieval_result(payload: dict[str, Any]) -> ComplianceResult:
    """Convert the existing SOP tool envelope to a typed result."""
    if payload.get("status") != "ok":
        return ComplianceResult(
            status=str(payload.get("status", "degraded")),
            citations=(),
            message=payload.get("message", "Compliance retrieval unavailable."),
        )
    documents = payload.get("data", {}).get("documents", [])
    citations = tuple(
        ComplianceCitation(
            source_file=str(document.get("source_file", "SOP")),
            file_format=str(document.get("file_format", "RAW")),
            content=str(document.get("content", "")),
            policy_version=document.get("policy_version"),
        )
        for document in documents
    )
    return ComplianceResult(
        status="ok",
        citations=citations,
        message=payload.get("message"),
    )
