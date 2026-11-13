"""Deterministic refrigerated-fleet telemetry simulator."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
from uuid import NAMESPACE_URL, uuid5

from src.domain.models import Shipment, TelemetryEvent, VehicleState, Warehouse


DEFAULT_ROUTES: dict[str, tuple[tuple[float, float], ...]] = {
    "MUMBAI_PUNE": (
        (19.0760, 72.8777),
        (19.0178, 73.1020),
        (18.9894, 73.1175),
        (18.7600, 73.4000),
        (18.5204, 73.8567),
    ),
}


@dataclass
class SimulatedFleet:
    vehicles: dict[str, VehicleState]
    shipments: dict[str, Shipment]
    warehouses: dict[str, Warehouse]


class TelemetrySimulator:
    """Advance a reproducible fleet along predefined route waypoints."""

    def __init__(
        self,
        fleet: SimulatedFleet,
        *,
        seed: int = 42,
        start_time: datetime | None = None,
        tick_seconds: int = 60,
    ) -> None:
        if tick_seconds <= 0:
            raise ValueError("tick_seconds must be positive.")
        self.fleet = fleet
        self.random = random.Random(seed)
        self.current_time = start_time or datetime.now(timezone.utc)
        self.tick_seconds = tick_seconds
        self._temperatures = {vehicle_id: 3.0 for vehicle_id in fleet.vehicles}

    def tick(self) -> list[TelemetryEvent]:
        """Advance all vehicles once and return one event per vehicle."""
        events: list[TelemetryEvent] = []
        for vehicle_id, vehicle in list(self.fleet.vehicles.items()):
            shipment = self.fleet.shipments[
                vehicle_id.replace("REEFER", "SHIPMENT")
            ]
            route = DEFAULT_ROUTES[vehicle.route_id]
            next_index = (vehicle.waypoint_index + 1) % len(route)
            latitude, longitude = route[next_index]
            previous_temperature = self._temperatures[vehicle_id]

            ambient = 30.0 + self.random.uniform(-1.5, 1.5)
            if vehicle.compressor_state == "failed":
                temperature_delta = (ambient - previous_temperature) * 0.08
            else:
                temperature_delta = (3.0 - previous_temperature) * 0.35
            temperature = previous_temperature + temperature_delta
            temperature += self.random.uniform(-0.08, 0.08)
            self._temperatures[vehicle_id] = temperature
            fuel = max(0.0, vehicle.fuel_level_percent - 0.03)

            updated_vehicle = VehicleState(
                vehicle_id=vehicle.vehicle_id,
                registration=vehicle.registration,
                status=vehicle.status,
                latitude=latitude,
                longitude=longitude,
                speed_kph=vehicle.speed_kph,
                route_id=vehicle.route_id,
                waypoint_index=next_index,
                compressor_state=vehicle.compressor_state,
                compressor_health=vehicle.compressor_health,
                fuel_level_percent=fuel,
                updated_at=self.current_time,
                state_version=vehicle.state_version + 1,
            )
            self.fleet.vehicles[vehicle_id] = updated_vehicle
            events.append(
                TelemetryEvent(
                    vehicle_id=vehicle_id,
                    shipment_id=shipment.shipment_id,
                    observed_at=self.current_time,
                    latitude=latitude,
                    longitude=longitude,
                    internal_temperature_c=temperature,
                    ambient_temperature_c=ambient,
                    humidity_percent=65.0 + self.random.uniform(-3.0, 3.0),
                    compressor_state=vehicle.compressor_state,
                    compressor_health=vehicle.compressor_health,
                    fuel_level_percent=fuel,
                    event_id=uuid5(
                        NAMESPACE_URL,
                        f"{vehicle_id}:{self.current_time.isoformat()}",
                    ),
                    correlation_id=uuid5(
                        NAMESPACE_URL,
                        f"telemetry:{vehicle_id}:{self.current_time.isoformat()}",
                    ),
                )
            )
        self.current_time += timedelta(seconds=self.tick_seconds)
        return events


def build_demo_fleet(vehicle_count: int = 5) -> SimulatedFleet:
    """Create the reproducible Mumbai–Pune demonstration fleet."""
    if not 5 <= vehicle_count <= 10:
        raise ValueError("vehicle_count must be between 5 and 10.")

    shipments: dict[str, Shipment] = {}
    vehicles: dict[str, VehicleState] = {}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(1, vehicle_count + 1):
        vehicle_id = f"REEFER-{index:03d}"
        shipment_id = f"SHIPMENT-{index:03d}"
        shipments[shipment_id] = Shipment(
            shipment_id=shipment_id,
            vehicle_id=vehicle_id,
            cargo_category="fresh_perishables",
            min_temp_c=0.0,
            max_temp_c=4.0,
            origin_name="Mumbai",
            destination_name="Pune",
            cargo_value=125000.0,
            quantity=1000.0,
        )
        latitude, longitude = DEFAULT_ROUTES["MUMBAI_PUNE"][0]
        vehicles[vehicle_id] = VehicleState(
            vehicle_id=vehicle_id,
            registration=f"MH-01-RT-{index:04d}",
            status="in_transit",
            latitude=latitude,
            longitude=longitude,
            speed_kph=55.0,
            route_id="MUMBAI_PUNE",
            waypoint_index=0,
            compressor_state="healthy",
            compressor_health=1.0,
            fuel_level_percent=85.0,
            updated_at=now,
        )

    warehouses = {
        "WH-MUMBAI": Warehouse(
            "WH-MUMBAI", "Mumbai Cold Hub", 19.0760, 72.8777,
            5000.0, 3000.0, 0.0, 4.0,
        ),
        "WH-PUNE": Warehouse(
            "WH-PUNE", "Pune Cold Hub", 18.5204, 73.8567,
            5000.0, 2500.0, 0.0, 4.0,
        ),
        "WH-NASHIK": Warehouse(
            "WH-NASHIK", "Nashik Overflow Cold Store", 19.9975, 73.7898,
            2500.0, 1200.0, 0.0, 4.0,
        ),
    }
    return SimulatedFleet(vehicles, shipments, warehouses)
