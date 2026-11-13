import unittest

from src.twin.demo_store import TwinDemoStore
from src.ui_dashboard import USER_MANUAL_PATH


class TwinDemoStoreTests(unittest.TestCase):
    def test_initial_projection_contains_five_vehicles_and_events(self):
        store = TwinDemoStore()

        self.assertEqual(len(store.vehicles), 5)
        self.assertIn("REEFER-003", store.vehicles)
        self.assertEqual(store.state_manager.event_count(), 5)
        self.assertEqual(store.risk_for("REEFER-003").status, "normal")

    def test_reading_snapshot_does_not_advance_state(self):
        store = TwinDemoStore()
        before = store.current_time
        event_count = store.state_manager.event_count()

        first = store.snapshot()
        second = store.snapshot()

        self.assertEqual(first, second)
        self.assertEqual(store.current_time, before)
        self.assertEqual(store.state_manager.event_count(), event_count)

    def test_explicit_advance_updates_projection_once_per_minute(self):
        store = TwinDemoStore()
        before = store.current_time

        appended = store.advance(5)

        self.assertEqual(appended, 25)
        self.assertEqual(store.state_manager.event_count(), 30)
        self.assertEqual((store.current_time - before).total_seconds(), 300)

    def test_reset_replays_same_baseline(self):
        store = TwinDemoStore()
        baseline = store.snapshot()
        store.advance(15)

        store.reset()

        self.assertEqual(store.snapshot(), baseline)
        self.assertEqual(store.state_manager.event_count(), 5)

    def test_advance_rejects_unlisted_tick_size(self):
        store = TwinDemoStore()

        with self.assertRaises(ValueError):
            store.advance(2)

    def test_user_manual_asset_is_available_to_dashboard(self):
        self.assertTrue(USER_MANUAL_PATH.is_file())
        self.assertIn("REEFERTWIN AI Digital Twin", USER_MANUAL_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
