"""Transparent temperature projection and threshold timing calculations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TemperatureProjection:
    current_temperature_c: float
    projected_temperature_c: float
    rate_c_per_hour: float
    minutes_to_threshold: float | None
    threshold_c: float
    direction: str


def calculate_rate_c_per_hour(
    previous_temperature_c: float,
    current_temperature_c: float,
    elapsed_minutes: float,
) -> float:
    """Calculate an observed temperature rate; reject invalid time intervals."""
    if elapsed_minutes <= 0:
        raise ValueError("elapsed_minutes must be positive.")
    return (current_temperature_c - previous_temperature_c) * 60 / elapsed_minutes


def estimate_minutes_to_threshold(
    current_temperature_c: float,
    rate_c_per_hour: float,
    threshold_c: float,
) -> float | None:
    """Estimate a forward threshold crossing using a bounded linear trend."""
    if current_temperature_c >= threshold_c:
        return 0.0
    if rate_c_per_hour <= 0:
        return None
    return max(0.0, (threshold_c - current_temperature_c) / rate_c_per_hour * 60)


def project_temperature(
    current_temperature_c: float,
    ambient_temperature_c: float,
    compressor_health: float,
    compressor_state: str,
    *,
    minutes: float,
    setpoint_c: float = 3.0,
    thermal_response_per_hour: float = 0.08,
) -> TemperatureProjection:
    """Project temperature without claiming a validated spoilage model."""
    if minutes < 0:
        raise ValueError("minutes must not be negative.")
    if not 0 <= compressor_health <= 1:
        raise ValueError("compressor_health must be between 0 and 1.")
    if thermal_response_per_hour <= 0:
        raise ValueError("thermal_response_per_hour must be positive.")

    failed = compressor_state.lower() in {"failed", "off", "fault"}
    effective_response = (
        thermal_response_per_hour * max(compressor_health, 0.05)
        if not failed
        else thermal_response_per_hour * 0.25
    )
    target = ambient_temperature_c if failed else setpoint_c
    projected = current_temperature_c + (
        target - current_temperature_c
    ) * (1 - 2.718281828 ** (-effective_response * minutes / 60))
    rate = (projected - current_temperature_c) * 60 / minutes if minutes else 0.0
    direction = "rising" if projected > current_temperature_c else "stable_or_falling"
    return TemperatureProjection(
        current_temperature_c=current_temperature_c,
        projected_temperature_c=projected,
        rate_c_per_hour=rate,
        minutes_to_threshold=None,
        threshold_c=float("inf"),
        direction=direction,
    )
