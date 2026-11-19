import importlib.util
import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dog", ROOT / "tools/watch_ui_hang_watchdog.py")
dog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dog)

OVERRUN = ("Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testX]' exceeded execution "
           "time allowance of 5 minutes.\n")
RESTART = "Restarting after unexpected exit, crash, or test timeout; summary will include totals.\n"


class HangWatchdogTests(unittest.TestCase):
    def test_only_an_overrun_not_yet_followed_by_a_restart_counts(self):
        self.assertFalse(dog.waiting_after_overrun("Test Case 'x' passed\n"))
        self.assertTrue(dog.waiting_after_overrun(OVERRUN))
        self.assertFalse(dog.waiting_after_overrun(OVERRUN + RESTART))
        self.assertTrue(dog.waiting_after_overrun(OVERRUN + RESTART + OVERRUN))

    def run_dog(self, text, quiet=1.0):
        with tempfile.TemporaryDirectory() as tmp:
            log, receipt = Path(tmp, "tests.log"), Path(tmp, "hang-watchdog.json")
            log.write_text(text)
            child = subprocess.Popen(["sleep", "30"])
            # Reap the child as soon as it ends, as bash's `wait` does for xcodebuild;
            # an unreaped zombie would still answer kill(pid, 0).
            reaper = threading.Thread(target=child.wait, daemon=True)
            reaper.start()
            try:
                if text == OVERRUN + RESTART:
                    # The child ends on its own; the dog must return without stopping it.
                    child.terminate()
                started = time.monotonic()
                stopped = dog.watch(log, child.pid, receipt, quiet=quiet, poll=0.2)
                reaper.join(timeout=40)
                return stopped, receipt.exists() and json.loads(receipt.read_text()), time.monotonic() - started
            finally:
                if child.poll() is None:
                    child.kill()

    def test_a_silent_log_after_an_overrun_stops_xcodebuild_and_leaves_a_receipt(self):
        stopped, receipt, elapsed = self.run_dog(OVERRUN)
        self.assertTrue(stopped)
        self.assertTrue(receipt["stopped"])
        self.assertLess(elapsed, 10)

    def test_a_silent_log_without_an_overrun_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "tests.log")
            log.write_text("    t =  10.00s Waiting 45.0s for x\n")
            child = subprocess.Popen(["sleep", "3"])
            threading.Thread(target=child.wait, daemon=True).start()
            stopped = dog.watch(log, child.pid, Path(tmp, "r.json"), quiet=0.5, poll=0.2)
            self.assertFalse(stopped)
            self.assertEqual(child.wait(timeout=10), 0, "the child ran to its own end")
            self.assertFalse(Path(tmp, "r.json").exists())

    def test_a_restart_after_the_overrun_is_left_alone(self):
        stopped, receipt, _ = self.run_dog(OVERRUN + RESTART)
        self.assertFalse(stopped)
        self.assertFalse(receipt)


if __name__ == "__main__":
    unittest.main()
