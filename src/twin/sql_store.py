"""SQL Server persistence for twin events, projections, scenarios, and audit."""

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from src.domain.models import TelemetryEvent, TwinEvent, VehicleState


class TwinSqlStore:
    """Persist simulator output using parameterized SQL transactions."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def persist_tick(
        self,
        telemetry_events: Iterable[TelemetryEvent],
        vehicle_states: dict[str, VehicleState],
    ) -> int:
        """Insert telemetry exactly once and update baseline projections only."""
        events = list(telemetry_events)
        if not events:
            return 0

        with self.engine.begin() as connection:
            inserted = 0
            for event in events:
                if self._insert_event(connection, self._to_twin_event(event)):
                    inserted += 1
                    connection.execute(
                        text(
                            """
                            INSERT INTO Twin.Telemetry (
                                event_id, vehicle_id, shipment_id, observed_at,
                                latitude, longitude, internal_temperature_c,
                                ambient_temperature_c, humidity_percent,
                                compressor_state, compressor_health,
                                fuel_level_percent, quality, source, scenario_id
                            )
                            VALUES (
                                :event_id, :vehicle_id, :shipment_id, :observed_at,
                                :latitude, :longitude, :internal_temperature_c,
                                :ambient_temperature_c, :humidity_percent,
                                :compressor_state, :compressor_health,
                                :fuel_level_percent, :quality, :source,
                                :scenario_id
                            )
                            """
                        ),
                        {
                            "event_id": event.event_id,
                            "vehicle_id": event.vehicle_id,
                            "shipment_id": event.shipment_id,
                            "observed_at": event.observed_at,
                            "latitude": event.latitude,
                            "longitude": event.longitude,
                            "internal_temperature_c": event.internal_temperature_c,
                            "ambient_temperature_c": event.ambient_temperature_c,
                            "humidity_percent": event.humidity_percent,
                            "compressor_state": event.compressor_state,
                            "compressor_health": event.compressor_health,
                            "fuel_level_percent": event.fuel_level_percent,
                            "quality": event.quality,
                            "source": event.source,
                            "scenario_id": event.scenario_id,
                        },
                    )

            baseline_vehicle_ids = {
                event.vehicle_id
                for event in events
                if event.scenario_id is None
            }
            for vehicle_id in baseline_vehicle_ids:
                connection.execute(
                    text(
                        """
                        UPDATE Twin.Vehicles
                        SET status = :status, latitude = :latitude,
                            longitude = :longitude, speed_kph = :speed_kph,
                            route_id = :route_id, waypoint_index = :waypoint_index,
                            compressor_state = :compressor_state,
                            compressor_health = :compressor_health,
                            fuel_level_percent = :fuel_level_percent,
                            state_version = :state_version,
                            updated_at = :updated_at
                        WHERE vehicle_id = :vehicle_id
                        """
                    ),
                    vehicle_states[vehicle_id].__dict__,
                )
        return inserted

    def persist_event(self, event: TwinEvent) -> bool:
        """Append one event and return whether it was newly inserted."""
        with self.engine.begin() as connection:
            return self._insert_event(connection, event)

    def persist_scenario(
        self,
        *,
        scenario_id: UUID,
        baseline_version: int,
        scenario_type: str,
        status: str,
        parameters: dict[str, Any],
        created_at: datetime,
        seed: int | None = None,
        approved_at: datetime | None = None,
    ) -> bool:
        """Insert a scenario once, preserving its baseline reference."""
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM Twin.Scenarios
                        WHERE scenario_id = :scenario_id
                    )
                    BEGIN
                        INSERT INTO Twin.Scenarios (
                            scenario_id, baseline_version, scenario_type, status,
                            seed, parameters, created_at, approved_at
                        )
                        VALUES (
                            :scenario_id, :baseline_version, :scenario_type, :status,
                            :seed, :parameters, :created_at, :approved_at
                        );
                        SELECT 1 AS inserted;
                    END
                    ELSE
                        SELECT 0 AS inserted;
                    """
                ),
                {
                    "scenario_id": scenario_id,
                    "baseline_version": baseline_version,
                    "scenario_type": scenario_type,
                    "status": status,
                    "seed": seed,
                    "parameters": json.dumps(parameters),
                    "created_at": created_at,
                    "approved_at": approved_at,
                },
            )
            return result.scalar() == 1

    def persist_audit(
        self,
        *,
        correlation_id: UUID,
        node_name: str,
        status: str,
        scenario_id: UUID | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
        input_summary: Any = None,
        output_summary: Any = None,
        evidence: Any = None,
        approval_status: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Append a structured audit record in the same SQL transaction."""
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO Twin.Audit (
                        correlation_id, scenario_id, session_id, node_name,
                        tool_name, status, input_summary, output_summary,
                        evidence, approval_status, error_code
                    )
                    VALUES (
                        :correlation_id, :scenario_id, :session_id, :node_name,
                        :tool_name, :status, :input_summary, :output_summary,
                        :evidence, :approval_status, :error_code
                    )
                    """
                ),
                {
                    "correlation_id": correlation_id,
                    "scenario_id": scenario_id,
                    "session_id": session_id,
                    "node_name": node_name,
                    "tool_name": tool_name,
                    "status": status,
                    "input_summary": self._serialize_optional(input_summary),
                    "output_summary": self._serialize_optional(output_summary),
                    "evidence": self._serialize_optional(evidence),
                    "approval_status": approval_status,
                    "error_code": error_code,
                },
            )

    @staticmethod
    def _to_twin_event(event: TelemetryEvent) -> TwinEvent:
        return TwinEvent(
            event_id=event.event_id,
            aggregate_type="vehicle",
            aggregate_id=event.vehicle_id,
            event_type="telemetry.observed",
            occurred_at=event.observed_at,
            source=event.source,
            payload=event.as_payload(),
            scenario_id=event.scenario_id,
            correlation_id=event.correlation_id,
        )

    @staticmethod
    def _insert_event(connection, event: TwinEvent) -> bool:
        result = connection.execute(
            text(
                """
                IF NOT EXISTS (
                    SELECT 1 FROM Twin.Events WHERE event_id = :event_id
                )
                BEGIN
                    INSERT INTO Twin.Events (
                        event_id, aggregate_type, aggregate_id, event_type,
                        occurred_at, source, scenario_id, correlation_id, payload
                    )
                    VALUES (
                        :event_id, :aggregate_type, :aggregate_id, :event_type,
                        :occurred_at, :source, :scenario_id, :correlation_id,
                        :payload
                    );
                    SELECT 1 AS inserted;
                END
                ELSE
                    SELECT 0 AS inserted;
                """
            ),
            {
                "event_id": event.event_id,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": event.aggregate_id,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "source": event.source,
                "scenario_id": event.scenario_id,
                "correlation_id": event.correlation_id,
                "payload": json.dumps(event.payload),
            },
        )
        return result.scalar() == 1

    @staticmethod
    def _serialize_optional(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)
