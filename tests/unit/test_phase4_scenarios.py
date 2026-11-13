import unittest

from src.twin.demo_store import TwinDemoStore
from src.twin.scenarios import ActionStatus, ScenarioType


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.store = TwinDemoStore()
        self.manager = self.store.scenario_manager

    def test_compressor_failure_is_isolated_and_changes_risk(self):
        baseline_events = list(self.store.telemetry["REEFER-003"])
        baseline_compressor = self.store.vehicles["REEFER-003"].compressor_state

        scenario = self.manager.simulate_disruption(
            ScenarioType.COMPRESSOR_FAILURE,
            vehicle_id="REEFER-003",
        )

        self.assertEqual(scenario.risks["REEFER-003"].status, "critical")
        self.assertEqual(self.store.vehicles["REEFER-003"].compressor_state, baseline_compressor)
        self.assertEqual(self.store.telemetry["REEFER-003"], baseline_events)
        self.assertEqual(scenario.scenario_id, scenario.events[0].scenario_id)

    def test_temperature_spike_comparison_contains_both_projections(self):
        scenario = self.manager.create(
            ScenarioType.TEMPERATURE_SPIKE,
            vehicle_id="REEFER-003",
            value=2.0,
        )

        comparison = self.manager.compare(scenario.scenario_id, "REEFER-003")

        self.assertGreater(
            comparison.disrupted_temperature_c,
            comparison.baseline_temperature_c,
        )
        self.assertEqual(comparison.baseline_destination, "Pune")

    def test_scenario_vehicle_is_preserved_and_wrong_vehicle_is_rejected(self):
        scenario = self.manager.create(
            ScenarioType.COMPRESSOR_FAILURE,
            vehicle_id="REEFER-003",
        )

        self.assertEqual(scenario.vehicle_id, "REEFER-003")
        with self.assertRaises(ValueError):
            self.manager.compare(scenario.scenario_id, "REEFER-001")
        with self.assertRaises(ValueError):
            self.manager.recommend(scenario.scenario_id, "REEFER-001")

    def test_compressor_progression_is_scenario_specific(self):
        scenario = self.manager.create(
            ScenarioType.COMPRESSOR_FAILURE,
            vehicle_id="REEFER-003",
        )
        baseline_before = self.store.risk_for("REEFER-003").current_temperature_c

        self.store.advance(15)

        baseline_after = self.store.risk_for("REEFER-003").current_temperature_c
        disrupted_after = scenario.risks["REEFER-003"].current_temperature_c
        self.assertNotEqual(baseline_after, baseline_before)
        self.assertNotEqual(disrupted_after, baseline_after)
        self.assertEqual(
            self.store.vehicles["REEFER-003"].compressor_state,
            "healthy",
        )
        self.assertEqual(
            scenario.vehicles["REEFER-003"].compressor_state,
            "failed",
        )
        self.assertGreater(
            scenario.risks["REEFER-003"].estimated_breach_minutes,
            0,
        )

    def test_selected_scenario_remains_available_after_clock_navigation(self):
        scenario = self.manager.create(ScenarioType.COMPRESSOR_FAILURE)
        selected_id = scenario.scenario_id

        self.store.advance(5)

        self.assertIn(selected_id, self.store.scenario_manager.scenarios)
        self.assertEqual(
            self.store.scenario_manager.scenarios[selected_id].vehicle_id,
            "REEFER-003",
        )

    def test_reset_discards_scenarios_and_replays_baseline_deterministically(self):
        initial = self.store.risk_for("REEFER-003").current_temperature_c
        self.manager.create(ScenarioType.COMPRESSOR_FAILURE)
        self.store.advance(15)

        self.store.reset()

        self.assertFalse(self.store.scenario_manager.scenarios)
        self.assertEqual(
            self.store.risk_for("REEFER-003").current_temperature_c,
            initial,
        )

    def test_ranking_returns_candidates_and_reasons(self):
        scenario = self.manager.create(
            ScenarioType.WAREHOUSE_UNAVAILABLE,
            vehicle_id="REEFER-003",
            warehouse_id="WH-PUNE",
        )

        ranking = self.manager.recommend(scenario.scenario_id, "REEFER-003")

        pune = next(item for item in ranking.candidates if item.warehouse_id == "WH-PUNE")
        self.assertFalse(pune.feasible)
        self.assertTrue(pune.rejection_reasons)
        self.assertEqual(ranking.status, "no_feasible_destination")
        self.assertTrue(
            any("deadline feasibility" in reason for reason in pune.rejection_reasons)
        )

    def test_unknown_safety_margin_is_not_presented_as_feasible(self):
        scenario = self.manager.create(ScenarioType.COMPRESSOR_FAILURE)

        ranking = self.manager.recommend(scenario.scenario_id, "REEFER-003")

        self.assertFalse(ranking.feasible_candidates)
        self.assertTrue(
            all(
                candidate.safety_margin_minutes is None
                and any("deadline feasibility" in reason for reason in candidate.rejection_reasons)
                for candidate in ranking.candidates
            )
        )

    def test_no_feasible_destination_is_explicit(self):
        scenario = self.manager.create(
            ScenarioType.CAPACITY_REDUCTION,
            vehicle_id="REEFER-003",
            warehouse_id="WH-PUNE",
            value=2500.0,
        )
        self.manager.add_disruption(
            scenario.scenario_id,
            ScenarioType.WAREHOUSE_UNAVAILABLE,
            vehicle_id="REEFER-003",
            warehouse_id="WH-MUMBAI",
        )
        self.manager.add_disruption(
            scenario.scenario_id,
            ScenarioType.WAREHOUSE_UNAVAILABLE,
            vehicle_id="REEFER-003",
            warehouse_id="WH-NASHIK",
        )

        ranking = self.manager.recommend(scenario.scenario_id, "REEFER-003")

        self.assertEqual(ranking.status, "no_feasible_destination")
        self.assertIsNone(ranking.selected_warehouse_id)

    def test_action_requires_approval_before_execution(self):
        scenario = self.manager.create(ScenarioType.COMPRESSOR_FAILURE)
        self.store.advance(1)
        ranking = self.manager.recommend(scenario.scenario_id, "REEFER-003")
        warehouse_id = ranking.selected_warehouse_id
        self.assertIsNotNone(warehouse_id)
        action = self.manager.propose_action(
            scenario.scenario_id, "REEFER-003", warehouse_id
        )
        with self.assertRaises(PermissionError):
            self.manager.execute_action(action.action_id)
        approved = self.manager.approve_action(action.action_id)
        executed = self.manager.execute_action(approved.action_id)
        self.assertEqual(executed.status, ActionStatus.EXECUTED)
        self.assertEqual(
            self.manager.scenarios[scenario.scenario_id].vehicles["REEFER-003"].status,
            "diverted",
        )
        self.assertEqual(self.store.vehicles["REEFER-003"].status, "in_transit")


if __name__ == "__main__":
    unittest.main()
