"""Guard real selected-game evidence and post-relaunch cache confirmation."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watch_live_receipt import verify


def summary(count=1):
    return ("Test Suite 'All tests' passed at 2026-10-04 12:00:00.000.\n"
            f"\t Executed {count} tests, with 0 failures in 1 second\n"
            "** TEST SUCCEEDED **\n"
            "Test Case '-[BainLuckWatchUITests.LiveSelectedGameJourneyTests testProductionPickerSelectionSurvivesRelaunchAndRefreshes]' passed (1.0 seconds).\n")


class WatchLiveReceiptTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        relaunched = now - timedelta(seconds=10)
        self.evidence = {
            "schema_version": 1, "configuration": "Release", "fixture": False,
            "refreshed_after_relaunch": True, "picker_id": 1, "canonical_id": 2,
            "home_team": "Home", "away_team": "Away",
            "production_detail": {"id": 2, "home_team": "Home", "away_team": "Away"},
            "first_state": "Live", "reopened_state": "Live",
            "first_probability": "Home win probability, 60%",
            "reopened_probability": "Home win probability, 61%",
            "requested_at": (relaunched - timedelta(seconds=10)).isoformat(),
            "relaunched_at": relaunched.isoformat(),
        }
        self.snapshot = {"version": 1, "game": {"id": 2, "home_team": "Home", "away_team": "Away"},
                         "fetchedAt": now.timestamp() - datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp()}

    def preferences(self):
        return {"bainluck_watch_selected_event_id": 2,
                "bainluck_watch_selected_game_snapshot_v1": json.dumps(self.snapshot).encode()}

    def log(self, count=1):
        return summary(count) + "WATCH_LIVE_EVIDENCE=" + json.dumps(self.evidence) + "\n"

    def reject(self, log=None, exit_code=0, preferences=None):
        with self.assertRaises((ValueError, KeyError, TypeError, OverflowError)):
            verify(self.log() if log is None else log, exit_code,
                   self.preferences() if preferences is None else preferences)

    def test_valid_canonical_alias(self):
        result = verify(self.log(), 0, self.preferences())
        self.assertEqual(result["tests"], 1)
        self.assertEqual(result["evidence"]["picker_id"], 1)
        self.assertEqual(result["evidence"]["canonical_id"], 2)

    def test_exit_and_exact_test_count(self):
        self.reject(exit_code=65)
        for count in [0, 2, 2083]:
            with self.subTest(count=count):
                self.reject(self.log(count))

    def test_wrong_named_test(self):
        self.reject(self.log().replace("testProductionPickerSelectionSurvivesRelaunchAndRefreshes", "testFixtureExample"))

    def test_targeted_root_and_ambiguous_summaries(self):
        selected = self.log().replace("'All tests'", "'Selected tests'")
        verify(selected, 0, self.preferences())
        self.reject(selected + summary())
        self.reject(self.log() + summary())
        self.reject(selected.replace("'Selected tests'", "'Nested suite'"))
        self.reject(selected.replace("with 0 failures", "with 1 failure"))
        self.reject(selected.replace("** TEST SUCCEEDED **", "** TEST FAILED **"))
        self.reject(selected.replace("'Selected tests' passed", "'Selected tests' failed"))
        named = "Test Case '-[BainLuckWatchUITests.LiveSelectedGameJourneyTests testProductionPickerSelectionSurvivesRelaunchAndRefreshes]' passed (1.0 seconds).\n"
        self.reject(selected + named)

    def test_missing_duplicate_and_malformed_packets(self):
        for log in [summary(), self.log() + "WATCH_LIVE_EVIDENCE=" + json.dumps(self.evidence) + "\n",
                    summary() + "WATCH_LIVE_EVIDENCE={broken\n"]:
            with self.subTest(log=log):
                self.reject(log)

    def test_release_real_data_and_completed_refresh_required(self):
        original = copy.deepcopy(self.evidence)
        for key, value in [("configuration", "Debug"), ("fixture", True),
                           ("fixture", 0), ("schema_version", 2), ("refreshed_after_relaunch", False)]:
            with self.subTest(key=key, value=value):
                self.evidence = copy.deepcopy(original)
                self.evidence[key] = value
                self.reject()

    def test_identity_and_named_sides(self):
        original = copy.deepcopy(self.evidence)
        for key, value in [("picker_id", 0), ("canonical_id", -1), ("picker_id", True),
                           ("home_team", "Other"), ("away_team", ""), ("canonical_id", 3)]:
            with self.subTest(key=key):
                self.evidence = copy.deepcopy(original)
                self.evidence[key] = value
                self.reject()
        self.evidence = original
        self.evidence["production_detail"]["id"] = 99
        self.reject()

    def test_saved_and_error_states(self):
        for phase in ["first", "reopened"]:
            for state in ["Saved reading · Live", "Offline", "Couldn't refresh", "Try again",
                          "Timed out", "Temporarily busy", ""]:
                with self.subTest(phase=phase, state=state):
                    self.evidence["first_state"] = self.evidence["reopened_state"] = "Live"
                    self.evidence[f"{phase}_state"] = state
                    self.reject()

    def test_final_and_closed_remove_forecasts(self):
        for state in ["Final", "Closed · result unverified"]:
            self.evidence["first_state"] = self.evidence["reopened_state"] = state
            self.reject()
            self.evidence["first_probability"] = self.evidence["reopened_probability"] = f"No forecast: {state}"
            self.assertEqual(verify(self.log(), 0, self.preferences())["tests"], 1)
            self.evidence["first_probability"] = self.evidence["reopened_probability"] = "Home win probability, 60%"

    def test_unavailable_is_valid(self):
        self.evidence["first_probability"] = self.evidence["reopened_probability"] = "Win probability unavailable"
        verify(self.log(), 0, self.preferences())

    def test_invalid_named_probabilities(self):
        for probability in ["Away win probability, 60%", "Home win probability, 101%",
                            "Home win probability, -1%", "60%", "Home win probability, NaN%"]:
            with self.subTest(probability=probability):
                self.evidence["reopened_probability"] = probability
                self.reject()

    def test_selection_snapshot_identity_and_version(self):
        preferences = self.preferences()
        preferences["bainluck_watch_selected_event_id"] = 1
        self.reject(preferences=preferences)
        original = copy.deepcopy(self.snapshot)
        for section, key, value in [(None, "version", 2), ("game", "id", 1),
                                    ("game", "home_team", "Other"), ("game", "away_team", "Other")]:
            with self.subTest(key=key):
                self.snapshot = copy.deepcopy(original)
                (self.snapshot if section is None else self.snapshot[section])[key] = value
                self.reject()

    def test_fetch_before_relaunch_or_in_future(self):
        original = self.snapshot["fetchedAt"]
        for fetched in [original - 60, original + 3600, "recent", float("nan"), float("inf")]:
            with self.subTest(fetched=fetched):
                self.snapshot["fetchedAt"] = fetched
                self.reject()

    def test_invalid_timestamps(self):
        original = copy.deepcopy(self.evidence)
        for key, value in [("requested_at", "invalid"), ("relaunched_at", "invalid"),
                           ("requested_at", "2026-01-01T00:00:00"),
                           ("relaunched_at", "2026-01-01T00:00:00"),
                           ("requested_at", "2999-01-01T00:00:00Z")]:
            with self.subTest(key=key, value=value):
                self.evidence = copy.deepcopy(original)
                self.evidence[key] = value
                self.reject()


if __name__ == "__main__":
    unittest.main()
