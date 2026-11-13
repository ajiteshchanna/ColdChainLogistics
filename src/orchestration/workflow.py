"""Structured decision workflow primitives around the existing LangGraph agent."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from src.predictive.risk import RiskAssessment


class ApprovalStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DecisionTrace:
    correlation_id: UUID
    node: str
    status: str
    recorded_at: datetime
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class DecisionContext:
    """State carried between deterministic nodes and LangGraph tool calls."""

    correlation_id: UUID = field(default_factory=uuid4)
    vehicle_id: str | None = None
    risk: RiskAssessment | None = None
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    traces: list[DecisionTrace] = field(default_factory=list)

    def record(
        self,
        node: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> DecisionTrace:
        trace = DecisionTrace(
            correlation_id=self.correlation_id,
            node=node,
            status=status,
            recorded_at=datetime.now(timezone.utc),
            details=details or {},
        )
        self.traces.append(trace)
        return trace

    def require_approval(self) -> None:
        self.approval_status = ApprovalStatus.PENDING
        self.record("approval_gate", ApprovalStatus.PENDING)

    def approve(self) -> None:
        if self.approval_status != ApprovalStatus.PENDING:
            raise RuntimeError("Only a pending action can be approved.")
        self.approval_status = ApprovalStatus.APPROVED
        self.record("approval_gate", ApprovalStatus.APPROVED)

    def reject(self) -> None:
        if self.approval_status != ApprovalStatus.PENDING:
            raise RuntimeError("Only a pending action can be rejected.")
        self.approval_status = ApprovalStatus.REJECTED
        self.record("approval_gate", ApprovalStatus.REJECTED)

    def assert_action_approved(self) -> None:
        if self.approval_status != ApprovalStatus.APPROVED:
            raise PermissionError("Action execution requires explicit operator approval.")


@dataclass
class AlertDebouncer:
    """Suppress repeated monitoring alerts until the configured interval elapses."""

    minimum_interval_seconds: int = 300
    _last_alert_at: dict[str, datetime] = field(default_factory=dict)

    def should_emit(self, key: str, now: datetime | None = None) -> bool:
        if self.minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must not be negative.")
        current = now or datetime.now(timezone.utc)
        previous = self._last_alert_at.get(key)
        if previous is not None:
            elapsed = (current - previous).total_seconds()
            if elapsed < self.minimum_interval_seconds:
                return False
        self._last_alert_at[key] = current
        return True
