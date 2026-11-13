import unittest
from datetime import datetime, timezone
from uuid import uuid4

from src.twin.sql_store import TwinSqlStore
from src.twin.telemetry_simulator import TelemetrySimulator, build_demo_fleet


class _Result:
    def __init__(self, value: int):
        self.value = value

    def scalar(self) -> int:
        return self.value


class _Connection:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if "Twin.Events" in sql:
            return _Result(1)
        if "Twin.Scenarios" in sql:
            return _Result(1)
        return _Result(0)


class _Transaction:
    def __init__(self, connection: _Connection):
        self.connection = connection

    def __enter__(self) -> _Connection:
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class _Engine:
    def __init__(self):
        self.connection = _Connection()

    def begin(self) -> _Transaction:
        return _Transaction(self.connection)


class TwinSqlStoreTests(unittest.TestCase):
    def setUp(self):
        fleet = build_demo_fleet()
        self.events = TelemetrySimulator(
            fleet,
            seed=4,
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ).tick()
        self.states = fleet.vehicles
        self.engine = _Engine()
        self.store = TwinSqlStore(self.engine)

    def test_persists_baseline_events_and_only_touched_projections(self):
        inserted = self.store.persist_tick(self.events, self.states)

        self.assertEqual(inserted, 5)
        updates = [
            sql for sql, _ in self.engine.connection.calls
            if "UPDATE Twin.Vehicles" in sql
        ]
        self.assertEqual(len(updates), 5)

    def test_scenario_events_do_not_update_baseline_projections(self):
        scenario_id = uuid4()
        scenario_events = [
            type(event)(**{**event.__dict__, "scenario_id": scenario_id})
            for event in self.events
        ]

        inserted = self.store.persist_tick(scenario_events, self.states)

        self.assertEqual(inserted, 5)
        self.assertFalse(
            any(
                "UPDATE Twin.Vehicles" in sql
                for sql, _ in self.engine.connection.calls
            )
        )

    def test_persists_scenario_parameters_as_json(self):
        scenario_id = uuid4()

        inserted = self.store.persist_scenario(
            scenario_id=scenario_id,
            baseline_version=1,
            scenario_type="compressor_failure",
            status="active",
            parameters={"vehicle_id": "REEFER-003"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            seed=42,
        )

        self.assertTrue(inserted)
        scenario_call = next(
            params
            for sql, params in self.engine.connection.calls
            if "Twin.Scenarios" in sql
        )
        self.assertEqual(scenario_call["parameters"], '{"vehicle_id": "REEFER-003"}')

    def test_persists_structured_audit_fields(self):
        correlation_id = uuid4()

        self.store.persist_audit(
            correlation_id=correlation_id,
            node_name="evaluate_risk",
            tool_name="evaluate_cargo_risk",
            status="ok",
            evidence=["telemetry-1", "SOP-v2"],
            output_summary={"risk": "warning"},
        )

        audit_call = next(
            params
            for sql, params in self.engine.connection.calls
            if "Twin.Audit" in sql
        )
        self.assertEqual(audit_call["correlation_id"], correlation_id)
        self.assertEqual(audit_call["evidence"], '["telemetry-1", "SOP-v2"]')
        self.assertEqual(audit_call["output_summary"], '{"risk": "warning"}')


if __name__ == "__main__":
    unittest.main()
