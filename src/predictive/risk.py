"""Deterministic cargo-risk evaluation with explicit uncertainty states."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.domain.models import Shipment, TelemetryEvent
from src.predictive.temperature import (
    calculate_rate_c_per_hour,
    estimate_minutes_to_threshold,
)


@dataclass(frozen=True)
class RiskAssessment:
    status: str
    current_temperature_c: float
    temperature_deviation_c: float
    rate_c_per_hour: float | None
    estimated_breach_minutes: float | None
    safe_intervention_deadline: datetime | None
    compressor_state: str
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "current_temperature_c": self.current_temperature_c,
            "temperature_deviation_c": self.temperature_deviation_c,
            "rate_c_per_hour": self.rate_c_per_hour,
            "estimated_breach_minutes": self.estimated_breach_minutes,
            "safe_intervention_deadline": (
                self.safe_intervention_deadline.isoformat()
                if self.safe_intervention_deadline
                else None
            ),
            "compressor_state": self.compressor_state,
            "evidence": list(self.evidence),
            "limitations": list(self.limitations),
        }


def evaluate_cargo_risk(
    telemetry: list[TelemetryEvent],
    shipment: Shipment,
    *,
    now: datetime | None = None,
    max_data_age_minutes: float = 15.0,
) -> RiskAssessment:
    """Evaluate threshold risk, not spoilage or remaining shelf life."""
    if not telemetry:
        return _unknown("No telemetry observations were supplied.")
    if max_data_age_minutes <= 0:
        raise ValueError("max_data_age_minutes must be positive.")

    observations = sorted(telemetry, key=lambda event: event.observed_at)
    latest = observations[-1]
    current_time = now or datetime.now(timezone.utc)
    latest_time = _as_utc(latest.observed_at)
    age_minutes = (current_time - latest_time).total_seconds() / 60
    if age_minutes > max_data_age_minutes:
        return _unknown(f"Latest telemetry is {age_minutes:.1f} minutes old.")

    deviation = latest.internal_temperature_c - shipment.max_temp_c
    rate: float | None = None
    if len(observations) >= 2:
        previous = observations[-2]
        elapsed = (
            _as_utc(latest.observed_at) - _as_utc(previous.observed_at)
        ).total_seconds() / 60
        if elapsed > 0:
            rate = calculate_rate_c_per_hour(
                previous.internal_temperature_c,
                latest.internal_temperature_c,
                elapsed,
            )

    threshold_minutes = estimate_minutes_to_threshold(
        latest.internal_temperature_c,
        rate or 0.0,
        shipment.max_temp_c,
    )
    deadline = (
        _as_utc(latest.observed_at) + timedelta(minutes=threshold_minutes)
        if threshold_minutes is not None
        else None
    )
    evidence = [
        f"Telemetry {latest.event_id} observed at {latest.observed_at.isoformat()}",
        f"Permitted maximum is {shipment.max_temp_c:.1f}°C",
    ]
    limitations = (
        "Threshold timing is a deterministic trend estimate.",
        "This result is not a spoilage or shelf-life prediction.",
    )

    if latest.internal_temperature_c > shipment.max_temp_c:
        status = "critical"
        evidence.append("Current temperature exceeds the permitted maximum.")
    elif latest.internal_temperature_c < shipment.min_temp_c:
        status = "warning"
        evidence.append("Current temperature is below the permitted minimum.")
    elif latest.compressor_state.lower() in {"failed", "off", "fault"}:
        status = "critical"
        evidence.append("Refrigeration compressor is not operational.")
    elif threshold_minutes is not None and threshold_minutes <= 60:
        status = "warning"
        evidence.append("Projected threshold crossing is within 60 minutes.")
    else:
        status = "normal"

    return RiskAssessment(
        status=status,
        current_temperature_c=latest.internal_temperature_c,
        temperature_deviation_c=deviation,
        rate_c_per_hour=rate,
        estimated_breach_minutes=threshold_minutes,
        safe_intervention_deadline=deadline,
        compressor_state=latest.compressor_state,
        evidence=tuple(evidence),
        limitations=limitations,
    )


def _unknown(reason: str) -> RiskAssessment:
    return RiskAssessment(
        status="unknown",
        current_temperature_c=0.0,
        temperature_deviation_c=0.0,
        rate_c_per_hour=None,
        estimated_breach_minutes=None,
        safe_intervention_deadline=None,
        compressor_state="unknown",
        evidence=(reason,),
        limitations=("No operational decision should be based on missing or stale data.",),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
