"""Seed the Phase 1 Twin schema with the deterministic demo fleet."""

import sys
import json
from pathlib import Path

from sqlalchemy import text

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.config import load_config
from src.database import create_sql_engine
from src.twin.telemetry_simulator import DEFAULT_ROUTES, build_demo_fleet


def main() -> int:
    config = load_config(project_root, require_admin=True)
    engine = create_sql_engine(
        config,
        username=config.sql_admin_user,
        password=config.sql_admin_password,
    )
    fleet = build_demo_fleet()
    with engine.begin() as connection:
        for vehicle in fleet.vehicles.values():
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM Twin.Vehicles WHERE vehicle_id = :vehicle_id
                    )
                    INSERT INTO Twin.Vehicles (
                        vehicle_id, registration, status, latitude, longitude,
                        speed_kph, route_id, waypoint_index, compressor_state,
                        compressor_health, fuel_level_percent, updated_at
                    )
                    VALUES (
                        :vehicle_id, :registration, :status, :latitude, :longitude,
                        :speed_kph, :route_id, :waypoint_index, :compressor_state,
                        :compressor_health, :fuel_level_percent, :updated_at
                    )
                    """
                ),
                vehicle.__dict__,
            )
        for shipment in fleet.shipments.values():
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM Twin.Shipments
                        WHERE shipment_id = :shipment_id
                    )
                    INSERT INTO Twin.Shipments (
                        shipment_id, vehicle_id, cargo_category, min_temp_c,
                        max_temp_c, origin_name, destination_name, cargo_value,
                        quantity
                    )
                    VALUES (
                        :shipment_id, :vehicle_id, :cargo_category, :min_temp_c,
                        :max_temp_c, :origin_name, :destination_name, :cargo_value,
                        :quantity
                    )
                    """
                ),
                shipment.__dict__,
            )
        for warehouse in fleet.warehouses.values():
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM Twin.Warehouses
                        WHERE warehouse_id = :warehouse_id
                    )
                    INSERT INTO Twin.Warehouses (
                        warehouse_id, name, latitude, longitude, total_capacity,
                        available_capacity, min_temp_c, max_temp_c, available
                    )
                    VALUES (
                        :warehouse_id, :name, :latitude, :longitude, :total_capacity,
                        :available_capacity, :min_temp_c, :max_temp_c, :available
                    )
                    """
                ),
                warehouse.__dict__,
            )
        for route_id, waypoints in DEFAULT_ROUTES.items():
            connection.execute(
                text(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM Twin.Routes WHERE route_id = :route_id
                    )
                    INSERT INTO Twin.Routes (
                        route_id, origin_name, destination_name, geometry_json, source
                    )
                    VALUES (
                        :route_id, 'Mumbai', 'Pune', :geometry_json, 'simulator'
                    )
                    """
                ),
                {
                    "route_id": route_id,
                    "geometry_json": json.dumps(waypoints),
                },
            )
    print(f"Seeded {len(fleet.vehicles)} vehicles and {len(fleet.warehouses)} warehouses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
