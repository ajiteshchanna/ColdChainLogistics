"""Feasibility filtering and explainable cold-storage ranking."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from src.domain.models import Shipment, VehicleState, Warehouse
from src.optimization.osrm_client import OsrmClient, RouteEstimate
from src.predictive.risk import RiskAssessment


@dataclass(frozen=True)
class WarehouseCandidate:
    warehouse_id: str
    name: str
    feasible: bool
    route: RouteEstimate
    arrival_at: datetime
    safety_margin_minutes: float | None
    rejection_reasons: tuple[str, ...] = ()
    estimated_cost: float | None = None
    carbon_delta_kg: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "warehouse_id": self.warehouse_id,
            "name": self.name,
            "feasible": self.feasible,
            "route": self.route.as_dict(),
            "arrival_at": self.arrival_at.isoformat(),
            "safety_margin_minutes": self.safety_margin_minutes,
            "rejection_reasons": list(self.rejection_reasons),
            "estimated_cost": self.estimated_cost,
            "carbon_delta_kg": self.carbon_delta_kg,
        }


@dataclass(frozen=True)
class WarehouseRanking:
    candidates: tuple[WarehouseCandidate, ...]
    selected_warehouse_id: str | None
    status: str
    warnings: tuple[str, ...] = ()

    @property
    def feasible_candidates(self) -> tuple[WarehouseCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.feasible)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "selected_warehouse_id": self.selected_warehouse_id,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }


def rank_warehouses(
    vehicle: VehicleState,
    shipment: Shipment,
    warehouses: Iterable[Warehouse],
    risk: RiskAssessment,
    *,
    route_client: OsrmClient | None = None,
    now: datetime | None = None,
    fixed_handling_cost: float = 250.0,
    cost_per_km: float = 12.0,
    vehicle_emission_factor: float = 0.85,
    route_delays: dict[str, float] | None = None,
    unavailable_ids: set[str] | None = None,
) -> WarehouseRanking:
    if fixed_handling_cost < 0 or cost_per_km < 0 or vehicle_emission_factor < 0:
        raise ValueError("Cost and emission factors must not be negative.")
    client = route_client or OsrmClient()
    current_time = now or datetime.now(timezone.utc)
    current_time = _as_utc(current_time)
    candidates: list[WarehouseCandidate] = []
    for warehouse in warehouses:
        route = client.route(
            (vehicle.latitude, vehicle.longitude),
            (warehouse.latitude, warehouse.longitude),
            route_key=f"{vehicle.vehicle_id}:{warehouse.warehouse_id}",
            blocked=(unavailable_ids or set()).__contains__(warehouse.warehouse_id),
            delay_minutes=(route_delays or {}).get(warehouse.warehouse_id, 0.0),
        )
        arrival = current_time + timedelta(minutes=route.duration_minutes)
        reasons: list[str] = []
        if not warehouse.available:
            reasons.append("warehouse is unavailable")
        if warehouse.available_capacity < shipment.quantity:
            reasons.append("available capacity is insufficient")
        if (
            warehouse.min_temp_c > shipment.min_temp_c
            or warehouse.max_temp_c < shipment.max_temp_c
        ):
            reasons.append("warehouse temperature range does not support cargo")
        if route.status != "ok":
            reasons.append("route is unavailable")
        margin = None
        if risk.safe_intervention_deadline is not None:
            margin = (
                _as_utc(risk.safe_intervention_deadline) - arrival
            ).total_seconds() / 60
            if margin < 0:
                reasons.append("arrival exceeds safe intervention deadline")
        else:
            reasons.append(
                "safe intervention deadline is unknown; deadline feasibility cannot be verified"
            )
        cost = fixed_handling_cost + route.distance_km * cost_per_km
        carbon = route.distance_km * vehicle_emission_factor
        candidates.append(
            WarehouseCandidate(
                warehouse.warehouse_id,
                warehouse.name,
                not reasons,
                route,
                arrival,
                margin,
                tuple(reasons),
                cost,
                carbon,
            )
        )
    feasible = sorted(
        (candidate for candidate in candidates if candidate.feasible),
        key=lambda candidate: (
            -(candidate.safety_margin_minutes or 0.0),
            candidate.route.duration_minutes,
            candidate.estimated_cost or 0.0,
            candidate.warehouse_id,
        ),
    )
    return WarehouseRanking(
        tuple(candidates),
        feasible[0].warehouse_id if feasible else None,
        "ok" if feasible else "no_feasible_destination",
        () if feasible else ("No warehouse satisfies all safety and capacity constraints.",),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
