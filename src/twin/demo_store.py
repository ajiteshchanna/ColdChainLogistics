"""Session-local read model for the Phase 3 command centre."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.domain.models import Shipment, TelemetryEvent, VehicleState, Warehouse
from src.predictive.risk import RiskAssessment, evaluate_cargo_risk
from src.twin.state_manager import TwinStateManager
from src.twin.telemetry_simulator import SimulatedFleet, TelemetrySimulator
from src.twin.scenarios import ScenarioManager


@dataclass
class TwinDemoStore:
    """Own mutable demo state so Streamlit reruns remain read-only."""

    vehicle_count: int = 5
    seed: int = 42
    simulator: TelemetrySimulator = field(init=False)
    state_manager: TwinStateManager = field(default_factory=TwinStateManager)
    telemetry: dict[str, list[TelemetryEvent]] = field(default_factory=dict)
    scenario_manager: ScenarioManager = field(init=False)

    def __post_init__(self) -> None:
        fleet = self._new_fleet()
        self.simulator = TelemetrySimulator(
            fleet,
            seed=self.seed,
            start_time=fleet.vehicles["REEFER-001"].updated_at,
        )
        self._advance()
        self.scenario_manager = ScenarioManager(self)

    def _new_fleet(self) -> SimulatedFleet:
        from src.twin.telemetry_simulator import build_demo_fleet

        return build_demo_fleet(self.vehicle_count)

    @property
    def vehicles(self) -> dict[str, VehicleState]:
        return self.state_manager.current_vehicles

    @property
    def shipments(self) -> dict[str, Shipment]:
        return self.simulator.fleet.shipments

    @property
    def warehouses(self) -> dict[str, Warehouse]:
        return self.simulator.fleet.warehouses

    @property
    def current_time(self) -> datetime:
        return self.simulator.current_time

    def _advance(self, ticks: int = 1) -> int:
        appended = 0
        for _ in range(ticks):
            events = self.simulator.tick()
            appended += self.state_manager.append_telemetry(
                events,
                self.simulator.fleet.vehicles,
            )
            for event in events:
                self.telemetry.setdefault(event.vehicle_id, []).append(event)
            if hasattr(self, "scenario_manager"):
                self.scenario_manager.sync_to_baseline()
        return appended

    def advance(self, minutes: int) -> int:
        """Advance the simulation only in response to an explicit operator action."""
        if minutes not in {1, 5, 15}:
            raise ValueError("minutes must be one of 1, 5, or 15.")
        return self._advance(minutes)

    def reset(self) -> None:
        """Reset to the same deterministic baseline."""
        self.state_manager = TwinStateManager()
        self.telemetry = {}
        self.simulator = TelemetrySimulator(
            self._new_fleet(),
            seed=self.seed,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self._advance()
        self.scenario_manager = ScenarioManager(self)

    def risk_for(self, vehicle_id: str) -> RiskAssessment:
        shipment = self.shipments[self.vehicles[vehicle_id].vehicle_id.replace(
            "REEFER", "SHIPMENT"
        )]
        return evaluate_cargo_risk(
            self.telemetry.get(vehicle_id, []),
            shipment,
            now=self.current_time,
        )

    def snapshot(self) -> list[dict[str, Any]]:
        """Return serializable rows for tables and charts."""
        rows: list[dict[str, Any]] = []
        for vehicle_id, vehicle in self.vehicles.items():
            shipment = self.shipments[vehicle_id.replace("REEFER", "SHIPMENT")]
            risk = self.risk_for(vehicle_id)
            rows.append(
                {
                    "vehicle_id": vehicle_id,
                    "registration": vehicle.registration,
                    "status": vehicle.status,
                    "latitude": vehicle.latitude,
                    "longitude": vehicle.longitude,
                    "speed_kph": vehicle.speed_kph,
                    "temperature_c": risk.current_temperature_c,
                    "risk": risk.status,
                    "compressor": vehicle.compressor_state,
                    "shipment_id": shipment.shipment_id,
                    "destination": shipment.destination_name,
                    "updated_at": vehicle.updated_at,
                }
            )
        return rows
