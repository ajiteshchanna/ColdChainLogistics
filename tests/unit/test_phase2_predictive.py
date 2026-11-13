import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import requests

from src.domain.models import Shipment, TelemetryEvent
from src.integrations.weather import WeatherClient
from src.orchestration.workflow import (
    AlertDebouncer,
    ApprovalStatus,
    DecisionContext,
)
from src.predictive.risk import evaluate_cargo_risk
from src.predictive.temperature import (
    estimate_minutes_to_threshold,
    project_temperature,
)


def _shipment() -> Shipment:
    return Shipment(
        shipment_id="SHIPMENT-003",
        vehicle_id="REEFER-003",
        cargo_category="fresh_perishables",
        min_temp_c=0.0,
        max_temp_c=4.0,
        origin_name="Mumbai",
        destination_name="Pune",
        cargo_value=125000.0,
        quantity=1000.0,
    )


def _telemetry(
    temperature: float,
    observed_at: datetime,
    *,
    compressor_state: str = "healthy",
) -> TelemetryEvent:
    return TelemetryEvent(
        vehicle_id="REEFER-003",
        shipment_id="SHIPMENT-003",
        observed_at=observed_at,
        latitude=19.0,
        longitude=73.0,
        internal_temperature_c=temperature,
        ambient_temperature_c=30.0,
        humidity_percent=65.0,
        compressor_state=compressor_state,
        compressor_health=1.0 if compressor_state == "healthy" else 0.0,
        fuel_level_percent=80.0,
    )


class TemperatureTests(unittest.TestCase):
    def test_threshold_time_is_none_when_temperature_is_not_rising(self):
        self.assertIsNone(estimate_minutes_to_threshold(3.0, 0.0, 4.0))

    def test_projected_failed_compressor_moves_toward_ambient(self):
        projection = project_temperature(
            3.0,
            30.0,
            0.0,
            "failed",
            minutes=60,
        )
        self.assertGreater(projection.projected_temperature_c, 3.0)
        self.assertEqual(projection.direction, "rising")


class RiskTests(unittest.TestCase):
    def test_current_breach_is_critical(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assessment = evaluate_cargo_risk(
            [_telemetry(4.1, now)],
            _shipment(),
            now=now,
        )
        self.assertEqual(assessment.status, "critical")
        self.assertEqual(assessment.estimated_breach_minutes, 0.0)

    def test_projected_breach_within_one_hour_is_warning(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assessment = evaluate_cargo_risk(
            [
                _telemetry(3.0, now - timedelta(minutes=5)),
                _telemetry(3.2, now),
            ],
            _shipment(),
            now=now,
        )
        self.assertEqual(assessment.status, "warning")
        self.assertIsNotNone(assessment.safe_intervention_deadline)

    def test_stale_data_is_unknown(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assessment = evaluate_cargo_risk(
            [_telemetry(3.0, now - timedelta(minutes=16))],
            _shipment(),
            now=now,
        )
        self.assertEqual(assessment.status, "unknown")

    def test_compressor_failure_is_critical_inside_limits(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assessment = evaluate_cargo_risk(
            [_telemetry(3.0, now, compressor_state="failed")],
            _shipment(),
            now=now,
        )
        self.assertEqual(assessment.status, "critical")
        self.assertIn("compressor", " ".join(assessment.evidence).lower())


class WorkflowTests(unittest.TestCase):
    def test_actions_require_approval(self):
        context = DecisionContext(vehicle_id="REEFER-003")
        context.require_approval()
        self.assertEqual(context.approval_status, ApprovalStatus.PENDING)
        with self.assertRaises(PermissionError):
            context.assert_action_approved()
        context.approve()
        context.assert_action_approved()
        self.assertEqual(len(context.traces), 2)

    def test_alert_debouncer_suppresses_repeats(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        debouncer = AlertDebouncer(minimum_interval_seconds=300)
        self.assertTrue(debouncer.should_emit("REEFER-003", now))
        self.assertFalse(
            debouncer.should_emit("REEFER-003", now + timedelta(seconds=299))
        )
        self.assertTrue(
            debouncer.should_emit("REEFER-003", now + timedelta(seconds=300))
        )


class WeatherTests(unittest.TestCase):
    def test_weather_failure_is_degraded(self):
        session = Mock()
        session.get.side_effect = requests.Timeout("offline")
        client = WeatherClient(session=session)
        snapshot = client.current(19.0, 73.0)
        self.assertEqual(snapshot.status, "degraded")
        self.assertIsNone(snapshot.temperature_c)


if __name__ == "__main__":
    unittest.main()
