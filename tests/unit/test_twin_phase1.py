import unittest
from datetime import datetime, timezone
from dataclasses import replace

from src.twin.state_manager import TwinStateManager
from src.twin.telemetry_simulator import TelemetrySimulator, build_demo_fleet


class TelemetrySimulatorTests(unittest.TestCase):
    def test_builds_five_vehicle_demo_fleet(self):
        fleet = build_demo_fleet()

        self.assertEqual(len(fleet.vehicles), 5)
        self.assertIn("REEFER-003", fleet.vehicles)
        self.assertEqual(len(fleet.shipments), 5)
        self.assertEqual(len(fleet.warehouses), 3)

    def test_tick_moves_each_vehicle_and_emits_complete_telemetry(self):
        fleet = build_demo_fleet()
        simulator = TelemetrySimulator(
            fleet,
            seed=7,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        events = simulator.tick()

        self.assertEqual(len(events), 5)
        self.assertEqual({event.vehicle_id for event in events}, set(fleet.vehicles))
        self.assertTrue(all(event.source == "simulator" for event in events))
        self.assertTrue(all(0 <= event.humidity_percent <= 100 for event in events))
        self.assertTrue(all(vehicle.state_version == 1 for vehicle in fleet.vehicles.values()))

    def test_same_seed_and_clock_reproduce_payloads_and_ids(self):
        first_fleet = build_demo_fleet()
        second_fleet = build_demo_fleet()
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = TelemetrySimulator(first_fleet, seed=9, start_time=start).tick()
        second = TelemetrySimulator(second_fleet, seed=9, start_time=start).tick()

        self.assertEqual(
            [(event.event_id, event.as_payload()) for event in first],
            [(event.event_id, event.as_payload()) for event in second],
        )

    def test_failed_compressor_increases_temperature(self):
        fleet = build_demo_fleet()
        healthy = TelemetrySimulator(
            fleet,
            seed=3,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        healthy_event = next(
            event for event in healthy.tick() if event.vehicle_id == "REEFER-003"
        )

        failed_fleet = build_demo_fleet()
        failed_vehicle = failed_fleet.vehicles["REEFER-003"]
        failed_fleet.vehicles["REEFER-003"] = replace(
            failed_vehicle,
            compressor_state="failed",
            compressor_health=0.0,
        )
        failed = TelemetrySimulator(
            failed_fleet,
            seed=3,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        failed_event = next(
            event for event in failed.tick() if event.vehicle_id == "REEFER-003"
        )

        self.assertGreater(
            failed_event.internal_temperature_c,
            healthy_event.internal_temperature_c,
        )


class TwinStateManagerTests(unittest.TestCase):
    def test_event_append_is_idempotent_and_updates_projection(self):
        fleet = build_demo_fleet()
        events = TelemetrySimulator(
            fleet,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ).tick()
        manager = TwinStateManager()

        self.assertEqual(manager.append_telemetry(events, fleet.vehicles), 5)
        self.assertEqual(manager.append_telemetry(events, fleet.vehicles), 0)
        self.assertEqual(manager.event_count(), 5)
        self.assertEqual(manager.current_vehicles["REEFER-001"].state_version, 1)


if __name__ == "__main__":
    unittest.main()
