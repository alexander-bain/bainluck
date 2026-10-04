"""Read-only polling retains exactly the bytes verified by the live receipt."""
import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watch_live_preferences import capture
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_watch_live_receipt as receipt_tests


class FakeTime:
    def __init__(self):
        self.elapsed = 0
        self.pauses = []

    def clock(self):
        return self.elapsed

    def pause(self, seconds):
        self.pauses.append(seconds)
        self.elapsed += seconds


class Source:
    def __init__(self, readings):
        self.readings = readings
        self.reads = 0

    def read_bytes(self):
        item = self.readings[min(self.reads, len(self.readings) - 1)]
        self.reads += 1
        if isinstance(item, Exception):
            raise item
        return item


class WatchLivePreferencesTests(unittest.TestCase):
    def setUp(self):
        fixture = receipt_tests.WatchLiveReceiptTests()
        fixture.setUp()
        self.fixture = fixture
        self.fresh = plistlib.dumps(fixture.preferences())
        fixture.snapshot["fetchedAt"] -= 60
        self.stale = plistlib.dumps(fixture.preferences())
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.output = root / "preferences-final.plist"
        self.observations = root / "observations.json"
        self.initial = root / "preferences-initial.plist"
        self.time = FakeTime()

    def run_capture(self, source, timeout=3):
        capture(self.fixture.log(), source, self.output, self.observations,
                timeout=timeout, clock=self.time.clock, pause=self.time.pause)

    def history(self):
        return json.loads(self.observations.read_text())

    def test_immediate_valid_preserves_bytes_without_sleep(self):
        source = Source([self.fresh])
        self.run_capture(source)
        self.assertEqual(source.reads, 1)
        self.assertEqual(self.time.pauses, [])
        self.assertEqual(self.initial.read_bytes(), self.fresh)
        self.assertEqual(self.output.read_bytes(), self.fresh)
        self.assertEqual([row["verdict"] for row in self.history()], ["PASS"])

    def test_stale_then_fresh_preserves_original_and_observations(self):
        source = Source([self.stale, self.stale, self.fresh])
        self.run_capture(source)
        self.assertEqual(source.reads, 3)
        self.assertEqual(self.initial.read_bytes(), self.stale)
        self.assertEqual(self.output.read_bytes(), self.fresh)
        self.assertEqual([row["verdict"] for row in self.history()], ["UNPAID", "UNPAID", "PASS"])
        self.assertEqual([row["elapsed_seconds"] for row in self.history()], [0, 1, 2])
        self.assertIn("after relaunch", self.history()[0]["reason"])

    def test_stale_invalid_and_missing_timeout_unpaid(self):
        for reading in [self.stale, b"invalid plist", FileNotFoundError("missing preferences")]:
            with self.subTest(reading=reading):
                self.time = FakeTime()
                source = Source([reading])
                with self.assertRaisesRegex(ValueError, "UNPAID after 3s"):
                    self.run_capture(source)
                self.assertEqual(source.reads, 4)
                self.assertEqual(self.time.elapsed, 3)
                self.assertEqual(self.time.pauses, [1, 1, 1])
                self.assertEqual([row["verdict"] for row in self.history()], ["UNPAID"] * 4)

    def test_success_never_rereads_mutating_source(self):
        source = Source([self.stale, self.fresh, b"changed after verification"])
        self.run_capture(source)
        self.assertEqual(source.reads, 2, "No re-copy after successful validation")
        self.assertEqual(self.output.read_bytes(), self.fresh)
        self.assertEqual(self.initial.read_bytes(), self.stale)
        self.assertEqual(self.history()[-1]["verdict"], "PASS")

    def test_fresh_fixture_is_rejected_by_full_receipt(self):
        self.fixture.evidence["fixture"] = True
        source = Source([self.fresh])
        with self.assertRaisesRegex(ValueError, "UNPAID"):
            self.run_capture(source)
        self.assertEqual(source.reads, 4)
        self.assertTrue(all(row["verdict"] == "UNPAID" for row in self.history()))
        self.assertIn("real-data", self.history()[-1]["reason"])


if __name__ == "__main__":
    unittest.main()
