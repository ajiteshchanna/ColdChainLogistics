"""Event persistence and in-memory projection for local/demo operation."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from src.domain.models import TelemetryEvent, TwinEvent, VehicleState


@dataclass
class TwinStateManager:
    """Apply idempotent telemetry events without mutating historical inputs."""

    events: dict[UUID, TwinEvent] = field(default_factory=dict)
    current_vehicles: dict[str, VehicleState] = field(default_factory=dict)

    def append_telemetry(
        self,
        events: Iterable[TelemetryEvent],
        vehicle_states: dict[str, VehicleState],
    ) -> int:
        """Append new events and update projections exactly once."""
        appended = 0
        for telemetry in events:
            if telemetry.event_id in self.events:
                continue
            self.events[telemetry.event_id] = TwinEvent(
                event_id=telemetry.event_id,
                aggregate_type="vehicle",
                aggregate_id=telemetry.vehicle_id,
                event_type="telemetry.observed",
                occurred_at=telemetry.observed_at,
                source=telemetry.source,
                payload=telemetry.as_payload(),
                scenario_id=telemetry.scenario_id,
                correlation_id=telemetry.correlation_id,
            )
            self.current_vehicles[telemetry.vehicle_id] = vehicle_states[
                telemetry.vehicle_id
            ]
            appended += 1
        return appended

    def event_count(self) -> int:
        return len(self.events)
