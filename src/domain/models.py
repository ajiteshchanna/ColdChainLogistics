"""Typed contracts for the Phase 1 digital-twin data flow."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class VehicleState:
    vehicle_id: str
    registration: str
    status: str
    latitude: float
    longitude: float
    speed_kph: float
    route_id: str
    waypoint_index: int
    compressor_state: str
    compressor_health: float
    fuel_level_percent: float
    updated_at: datetime
    state_version: int = 0


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    vehicle_id: str
    cargo_category: str
    min_temp_c: float
    max_temp_c: float
    origin_name: str
    destination_name: str
    cargo_value: float
    quantity: float


@dataclass(frozen=True)
class Warehouse:
    warehouse_id: str
    name: str
    latitude: float
    longitude: float
    total_capacity: float
    available_capacity: float
    min_temp_c: float
    max_temp_c: float
    available: bool = True


@dataclass(frozen=True)
class TelemetryEvent:
    vehicle_id: str
    shipment_id: str
    observed_at: datetime
    latitude: float
    longitude: float
    internal_temperature_c: float
    ambient_temperature_c: float
    humidity_percent: float
    compressor_state: str
    compressor_health: float
    fuel_level_percent: float
    source: str = "simulator"
    scenario_id: UUID | None = None
    event_id: UUID = field(default_factory=uuid4)
    correlation_id: UUID = field(default_factory=uuid4)
    quality: str = "good"

    def as_payload(self) -> dict[str, Any]:
        return {
            "vehicle_id": self.vehicle_id,
            "shipment_id": self.shipment_id,
            "observed_at": self.observed_at.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "internal_temperature_c": self.internal_temperature_c,
            "ambient_temperature_c": self.ambient_temperature_c,
            "humidity_percent": self.humidity_percent,
            "compressor_state": self.compressor_state,
            "compressor_health": self.compressor_health,
            "fuel_level_percent": self.fuel_level_percent,
            "source": self.source,
            "quality": self.quality,
        }


@dataclass(frozen=True)
class TwinEvent:
    event_id: UUID
    aggregate_type: str
    aggregate_id: str
    event_type: str
    occurred_at: datetime
    source: str
    payload: dict[str, Any]
    scenario_id: UUID | None = None
    correlation_id: UUID = field(default_factory=uuid4)
