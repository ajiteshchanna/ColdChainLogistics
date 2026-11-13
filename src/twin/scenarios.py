"""Isolated what-if scenario projections and approval-gated actions."""

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from src.domain.models import Shipment, TelemetryEvent, VehicleState, Warehouse
from src.optimization.osrm_client import OsrmClient
from src.optimization.warehouse_ranker import WarehouseRanking, rank_warehouses
from src.predictive.risk import RiskAssessment, evaluate_cargo_risk
from src.predictive.temperature import project_temperature


class ScenarioType(StrEnum):
    COMPRESSOR_FAILURE = "compressor_failure"
    HEATWAVE = "heatwave"
    TEMPERATURE_SPIKE = "temperature_spike"
    TRAFFIC_CONGESTION = "traffic_congestion"
    HIGHWAY_CLOSURE = "highway_closure"
    CAPACITY_REDUCTION = "capacity_reduction"
    WAREHOUSE_UNAVAILABLE = "warehouse_unavailable"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ScenarioEvent:
    event_type: ScenarioType
    vehicle_id: str | None = None
    warehouse_id: str | None = None
    value: float = 0.0
    duration_minutes: int = 60
    scenario_id: UUID = field(default_factory=uuid4)


@dataclass
class ScenarioProjection:
    scenario_id: UUID
    vehicle_id: str
    baseline_version: int
    events: list[ScenarioEvent]
    vehicles: dict[str, VehicleState]
    telemetry: dict[str, list[TelemetryEvent]]
    warehouses: dict[str, Warehouse]
    risks: dict[str, RiskAssessment]
    ranking: WarehouseRanking | None = None
    action_status: ActionStatus | None = None


@dataclass(frozen=True)
class ScenarioComparison:
    vehicle_id: str
    baseline: RiskAssessment
    disrupted: RiskAssessment
    baseline_temperature_c: float
    disrupted_temperature_c: float
    baseline_breach_minutes: float | None
    disrupted_breach_minutes: float | None
    baseline_destination: str
    disrupted_destination: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "vehicle_id": self.vehicle_id,
            "baseline": self.baseline.as_dict(),
            "disrupted": self.disrupted.as_dict(),
            "baseline_temperature_c": self.baseline_temperature_c,
            "disrupted_temperature_c": self.disrupted_temperature_c,
            "baseline_breach_minutes": self.baseline_breach_minutes,
            "disrupted_breach_minutes": self.disrupted_breach_minutes,
            "baseline_destination": self.baseline_destination,
            "disrupted_destination": self.disrupted_destination,
        }


@dataclass(frozen=True)
class ScenarioAction:
    action_id: UUID
    scenario_id: UUID
    vehicle_id: str
    warehouse_id: str
    status: ActionStatus
    rationale: str
    estimated_cost: float | None
    carbon_delta_kg: float | None


class ScenarioManager:
    """Create and mutate scenario projections without changing the baseline."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.scenarios: dict[UUID, ScenarioProjection] = {}
        self.actions: dict[UUID, ScenarioAction] = {}

    def create(
        self,
        event_type: ScenarioType | str,
        *,
        vehicle_id: str = "REEFER-003",
        warehouse_id: str | None = None,
        value: float = 0.0,
        duration_minutes: int = 60,
    ) -> ScenarioProjection:
        event_type = ScenarioType(event_type)
        if vehicle_id not in self.store.vehicles:
            raise KeyError(f"Unknown vehicle: {vehicle_id}")
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive.")
        scenario_id = uuid4()
        event = ScenarioEvent(
            event_type,
            vehicle_id,
            warehouse_id,
            value,
            duration_minutes,
            scenario_id,
        )
        vehicles = deepcopy(self.store.vehicles)
        telemetry = deepcopy(self.store.telemetry)
        warehouses = deepcopy(self.store.warehouses)
        self._apply_event(event, vehicles, telemetry, warehouses)
        risks = {
            vehicle: self._risk(vehicle, telemetry, vehicles, self.store.shipments)
            for vehicle in vehicles
        }
        projection = ScenarioProjection(
            scenario_id,
            vehicle_id,
            max(state.state_version for state in self.store.vehicles.values()),
            [event],
            vehicles,
            telemetry,
            warehouses,
            risks,
        )
        self.scenarios[scenario_id] = projection
        return projection

    def simulate_disruption(
        self,
        event_type: ScenarioType | str,
        **kwargs: Any,
    ) -> ScenarioProjection:
        """Compatibility entry point for the Phase 4 simulation tool contract."""
        return self.create(event_type, **kwargs)

    def add_disruption(
        self,
        scenario_id: UUID,
        event_type: ScenarioType | str,
        *,
        vehicle_id: str = "REEFER-003",
        warehouse_id: str | None = None,
        value: float = 0.0,
        duration_minutes: int = 60,
    ) -> ScenarioProjection:
        """Append a disruption to an existing isolated projection."""
        projection = self._get(scenario_id)
        if vehicle_id != projection.vehicle_id:
            raise ValueError(
                f"Scenario {scenario_id} is associated with {projection.vehicle_id}, "
                f"not {vehicle_id}."
            )
        event = ScenarioEvent(
            ScenarioType(event_type),
            vehicle_id,
            warehouse_id,
            value,
            duration_minutes,
            scenario_id,
        )
        self._apply_event(
            event,
            projection.vehicles,
            projection.telemetry,
            projection.warehouses,
        )
        projection.events.append(event)
        projection.risks = {
            vehicle: self._risk(
                vehicle,
                projection.telemetry,
                projection.vehicles,
                self.store.shipments,
            )
            for vehicle in projection.vehicles
        }
        projection.ranking = None
        return projection

    def compare(self, scenario_id: UUID, vehicle_id: str) -> ScenarioComparison:
        projection = self._get(scenario_id)
        self._ensure_vehicle(projection, vehicle_id)
        baseline_risk = self.store.risk_for(vehicle_id)
        disrupted_risk = projection.risks[vehicle_id]
        shipment = self.store.shipments[vehicle_id.replace("REEFER", "SHIPMENT")]
        return ScenarioComparison(
            vehicle_id,
            baseline_risk,
            disrupted_risk,
            baseline_risk.current_temperature_c,
            disrupted_risk.current_temperature_c,
            baseline_risk.estimated_breach_minutes,
            disrupted_risk.estimated_breach_minutes,
            shipment.destination_name,
            shipment.destination_name,
        )

    def recommend(self, scenario_id: UUID, vehicle_id: str) -> WarehouseRanking:
        projection = self._get(scenario_id)
        self._ensure_vehicle(projection, vehicle_id)
        shipment = self.store.shipments[vehicle_id.replace("REEFER", "SHIPMENT")]
        route_delays: dict[str, float] = {}
        unavailable_ids: set[str] = set()
        for event in projection.events:
            if event.event_type == ScenarioType.TRAFFIC_CONGESTION:
                route_delays = {
                    warehouse_id: event.value
                    for warehouse_id in projection.warehouses
                }
            elif event.event_type == ScenarioType.HIGHWAY_CLOSURE:
                unavailable_ids = set(projection.warehouses)
        ranking = rank_warehouses(
            projection.vehicles[vehicle_id],
            shipment,
            projection.warehouses.values(),
            projection.risks[vehicle_id],
            route_client=OsrmClient(),
            now=self.store.current_time,
            route_delays=route_delays,
            unavailable_ids=unavailable_ids,
        )
        projection.ranking = ranking
        return ranking

    def propose_action(
        self,
        scenario_id: UUID,
        vehicle_id: str,
        warehouse_id: str,
    ) -> ScenarioAction:
        ranking = self.recommend(scenario_id, vehicle_id)
        candidate = next(
            (item for item in ranking.candidates if item.warehouse_id == warehouse_id),
            None,
        )
        if candidate is None or not candidate.feasible:
            raise ValueError("Only a feasible warehouse can be proposed.")
        action = ScenarioAction(
            uuid4(),
            scenario_id,
            vehicle_id,
            warehouse_id,
            ActionStatus.PROPOSED,
            "Divert shipment to the highest-safety feasible cold-storage candidate.",
            candidate.estimated_cost,
            candidate.carbon_delta_kg,
        )
        self.actions[action.action_id] = action
        return action

    def approve_action(self, action_id: UUID) -> ScenarioAction:
        action = self.actions[action_id]
        if action.status != ActionStatus.PROPOSED:
            raise RuntimeError("Only proposed actions can be approved.")
        approved = ScenarioAction(**{**action.__dict__, "status": ActionStatus.APPROVED})
        self.actions[action_id] = approved
        return approved

    def execute_action(self, action_id: UUID) -> ScenarioAction:
        action = self.actions[action_id]
        if action.status != ActionStatus.APPROVED:
            raise PermissionError("Scenario action requires explicit approval.")
        projection = self._get(action.scenario_id)
        projection.action_status = ActionStatus.EXECUTED
        vehicle = projection.vehicles[action.vehicle_id]
        projection.vehicles[action.vehicle_id] = VehicleState(
            **{**vehicle.__dict__, "status": "diverted"}
        )
        warehouse = projection.warehouses[action.warehouse_id]
        shipment = self.store.shipments[action.vehicle_id.replace("REEFER", "SHIPMENT")]
        projection.warehouses[action.warehouse_id] = Warehouse(
            **{
                **warehouse.__dict__,
                "available_capacity": max(
                    0.0, warehouse.available_capacity - shipment.quantity
                ),
            }
        )
        updated = ScenarioAction(**{**action.__dict__, "status": ActionStatus.EXECUTED})
        self.actions[action_id] = updated
        return updated

    def _get(self, scenario_id: UUID) -> ScenarioProjection:
        try:
            return self.scenarios[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

    @staticmethod
    def _ensure_vehicle(projection: ScenarioProjection, vehicle_id: str) -> None:
        if vehicle_id != projection.vehicle_id:
            raise ValueError(
                f"Scenario {projection.scenario_id} is associated with "
                f"{projection.vehicle_id}, not {vehicle_id}."
            )

    def sync_to_baseline(self) -> None:
        """Advance each scenario projection to the store's latest baseline tick."""
        for projection in self.scenarios.values():
            if not any(
                event.event_type == ScenarioType.COMPRESSOR_FAILURE
                for event in projection.events
            ):
                continue
            baseline_vehicle = self.store.vehicles[projection.vehicle_id]
            baseline_events = self.store.telemetry.get(projection.vehicle_id, [])
            scenario_events = projection.telemetry.setdefault(projection.vehicle_id, [])
            if not baseline_events or (
                scenario_events
                and scenario_events[-1].observed_at >= baseline_events[-1].observed_at
            ):
                continue
            baseline_event = baseline_events[-1]
            previous = scenario_events[-1] if scenario_events else baseline_event
            elapsed_minutes = (
                baseline_event.observed_at - previous.observed_at
            ).total_seconds() / 60
            if elapsed_minutes <= 0:
                continue
            scenario_vehicle = replace(
                baseline_vehicle,
                compressor_state="failed",
                compressor_health=0.0,
            )
            projected_temperature = project_temperature(
                previous.internal_temperature_c,
                baseline_event.ambient_temperature_c,
                scenario_vehicle.compressor_health,
                scenario_vehicle.compressor_state,
                minutes=elapsed_minutes,
            ).projected_temperature_c
            scenario_events.append(
                replace(
                    baseline_event,
                    internal_temperature_c=projected_temperature,
                    compressor_state="failed",
                    compressor_health=0.0,
                    source="scenario",
                    scenario_id=projection.scenario_id,
                )
            )
            projection.vehicles[projection.vehicle_id] = scenario_vehicle
            projection.baseline_version = max(
                state.state_version for state in self.store.vehicles.values()
            )
            projection.risks = {
                vehicle: self._risk(
                    vehicle,
                    projection.telemetry,
                    projection.vehicles,
                    self.store.shipments,
                )
                for vehicle in projection.vehicles
            }

    def _apply_event(
        self,
        event: ScenarioEvent,
        vehicles: dict[str, VehicleState],
        telemetry: dict[str, list[TelemetryEvent]],
        warehouses: dict[str, Warehouse],
    ) -> None:
        if event.event_type == ScenarioType.COMPRESSOR_FAILURE:
            vehicle = vehicles[event.vehicle_id]
            vehicles[event.vehicle_id] = VehicleState(
                **{**vehicle.__dict__, "compressor_state": "failed", "compressor_health": 0.0}
            )
        elif event.event_type == ScenarioType.HEATWAVE:
            self._shift_latest_telemetry(telemetry, event.vehicle_id, event.value)
        elif event.event_type == ScenarioType.TEMPERATURE_SPIKE:
            self._shift_latest_telemetry(telemetry, event.vehicle_id, event.value)
        elif event.event_type == ScenarioType.TRAFFIC_CONGESTION:
            pass
        elif event.event_type == ScenarioType.HIGHWAY_CLOSURE:
            pass
        elif event.event_type == ScenarioType.CAPACITY_REDUCTION:
            warehouse = warehouses[event.warehouse_id]
            warehouses[event.warehouse_id] = Warehouse(
                **{
                    **warehouse.__dict__,
                    "available_capacity": max(0.0, warehouse.available_capacity - event.value),
                }
            )
        elif event.event_type == ScenarioType.WAREHOUSE_UNAVAILABLE:
            warehouse = warehouses[event.warehouse_id]
            warehouses[event.warehouse_id] = Warehouse(
                **{**warehouse.__dict__, "available": False}
            )

    @staticmethod
    def _shift_latest_telemetry(
        telemetry: dict[str, list[TelemetryEvent]],
        vehicle_id: str,
        delta: float,
    ) -> None:
        if delta < 0:
            raise ValueError("Temperature disruption value must not be negative.")
        events = telemetry.get(vehicle_id, [])
        if not events:
            raise ValueError("Temperature disruption requires telemetry.")
        latest = events[-1]
        events[-1] = TelemetryEvent(
            **{
                **latest.__dict__,
                "internal_temperature_c": latest.internal_temperature_c + delta,
                "source": "scenario",
            }
        )

    @staticmethod
    def _risk(
        vehicle_id: str,
        telemetry: dict[str, list[TelemetryEvent]],
        vehicles: dict[str, VehicleState],
        shipments: dict[str, Shipment],
    ) -> RiskAssessment:
        events = telemetry.get(vehicle_id, [])
        if vehicles[vehicle_id].compressor_state == "failed" and events:
            events = [
                replace(event, compressor_state="failed", compressor_health=0.0)
                for event in events
            ]
        return evaluate_cargo_risk(
            events,
            shipments[vehicle_id.replace("REEFER", "SHIPMENT")],
            now=events[-1].observed_at if events else None,
        )
