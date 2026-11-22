import importlib.util
import json
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest import mock

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

    def test_clockface_idle_stall_restarts_clockface_at_safe_test_boundary_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "tests.log")
            receipt = Path(tmp, "hang-watchdog.json")
            cf_receipt = Path(tmp, "clockface-recovery.json")
            calls = []

            def fake_terminate(udid):
                calls.append(udid)
                return {"returncode": 0, "stderr": ""}

            log.write_text("")
            child = subprocess.Popen(["sleep", "5"])
            reaper = threading.Thread(target=child.wait, daemon=True)
            reaper.start()
            try:
                thread_res = []
                worker = threading.Thread(
                    target=lambda: thread_res.append(
                        dog.watch(
                            log,
                            child.pid,
                            receipt,
                            quiet=30.0,
                            poll=0.05,
                            watch_udid="WATCH-UDID-1",
                            clockface_receipt=cf_receipt,
                            clockface_terminator=fake_terminate,
                        )
                    )
                )
                worker.start()
                # Healthy clockface wait never arms recovery.
                with log.open("a") as fh:
                    fh.write(
                        "    t =    79.73s         Wait for com.apple.clockface to idle\n"
                        "    t =    79.77s     Synthesize event\n"
                    )
                time.sleep(0.15)
                self.assertEqual(calls, [])

                # Clockface wedges mid-test: must wait until safe boundary.
                with log.open("a") as fh:
                    fh.write(
                        "    t =    73.38s         Wait for com.apple.clockface to idle\n"
                        "    t =   133.44s App animations complete notification not received, will attempt to continue.\n"
                        "    t =   133.68s     Synthesize event\n"
                    )
                time.sleep(0.15)
                self.assertEqual(calls, [], "must not terminate mid-test")

                # Test finishes -> safe boundary triggers exactly one recovery.
                with log.open("a") as fh:
                    fh.write(
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testColdActualWidgetTapOffersPickerWithoutSelection]' passed (140.245 seconds).\n"
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testColdActualWidgetTapRetainsOfflineReading]' started.\n"
                        "    t =     0.07s     Launch com.bainluck.Bain-Luck.watchkitapp\n"
                    )
                time.sleep(0.2)
                self.assertEqual(calls, ["WATCH-UDID-1"])

                # Next boundary after healthy run must not re-fire.
                with log.open("a") as fh:
                    fh.write(
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testColdActualWidgetTapRetainsOfflineReading]' passed (80.000 seconds).\n"
                    )
                time.sleep(0.15)
                self.assertEqual(calls, ["WATCH-UDID-1"])

                # Runner restart boundary after another stall also recovers.
                with log.open("a") as fh:
                    fh.write(
                        "    t =    17.28s         Wait for com.apple.clockface to idle\n"
                        "    t =    77.34s App animations complete notification not received, will attempt to continue.\n"
                        "Restarting after unexpected exit, crash, or test timeout; summary will include totals from previous launches.\n"
                    )
                time.sleep(0.2)
                self.assertEqual(calls, ["WATCH-UDID-1", "WATCH-UDID-1"])

                child.terminate()
                worker.join(timeout=5)
                reaper.join(timeout=5)
                self.assertEqual(thread_res, [False])
                self.assertFalse(receipt.exists())
                saved = json.loads(cf_receipt.read_text())
                self.assertEqual(saved["count"], 2)
                self.assertIn("passed (140.245 seconds)", saved["recoveries"][0]["boundary"])
                self.assertIn("Restarting after unexpected exit", saved["recoveries"][1]["boundary"])
            finally:
                if child.poll() is None:
                    child.kill()

    def test_terminate_clockface_succeeds_without_fallback_at_25s_budget(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs.get("timeout")))
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch.object(dog.subprocess, "run", side_effect=fake_run):
            outcome = dog.terminate_clockface("WATCH-UDID-1")

        self.assertEqual(outcome["returncode"], 0)
        self.assertEqual(outcome["method"], "simctl_terminate")
        self.assertEqual(
            calls,
            [(["xcrun", "simctl", "terminate", "WATCH-UDID-1", "com.apple.clockface"], 25)],
        )

    def test_terminate_clockface_falls_back_to_verified_launchctl_sigkill(self):
        killed = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["xcrun", "simctl", "terminate"]:
                raise subprocess.TimeoutExpired(cmd, 25)
            if cmd == ["xcrun", "simctl", "spawn", "WATCH-UDID-1", "launchctl", "list"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=(
                        "-\t0\tcom.apple.other\n"
                        "4210\t0\tUIKitApplication:com.apple.clockface[1234][rb-legacy]\n"
                    ),
                    stderr="",
                )
            if cmd == ["ps", "-p", "4210", "-o", "comm="]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="/Applications/ClockFace.app/ClockFace\n",
                    stderr="",
                )
            raise AssertionError(f"Unexpected command: {cmd}")

        with (
            mock.patch.object(dog.subprocess, "run", side_effect=fake_run),
            mock.patch.object(dog.os, "kill", side_effect=lambda pid, sig: killed.append((pid, sig))),
        ):
            outcome = dog.terminate_clockface("WATCH-UDID-1")

        self.assertEqual(outcome["returncode"], 0)
        self.assertEqual(outcome["method"], "launchctl_sigkill")
        self.assertEqual(outcome["pids"], [4210])
        self.assertEqual(killed, [(4210, signal.SIGKILL)])

    def test_terminate_clockface_fallback_refuses_non_clockface_comm(self):
        killed = []

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["xcrun", "simctl", "terminate"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="failed")
            if cmd[:5] == ["xcrun", "simctl", "spawn", "WATCH-UDID-1", "launchctl"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="9999\t0\tcom.apple.clockface\n", stderr=""
                )
            if cmd == ["ps", "-p", "9999", "-o", "comm="]:
                return subprocess.CompletedProcess(cmd, 0, stdout="/usr/sbin/SomeOtherDaemon\n", stderr="")
            raise AssertionError(f"Unexpected command: {cmd}")

        with (
            mock.patch.object(dog.subprocess, "run", side_effect=fake_run),
            mock.patch.object(dog.os, "kill", side_effect=lambda pid, sig: killed.append((pid, sig))),
        ):
            outcome = dog.terminate_clockface("WATCH-UDID-1")

        self.assertEqual(outcome["returncode"], -1)
        self.assertEqual(outcome["method"], "launchctl_sigkill")
        self.assertEqual(killed, [])
        self.assertIn("comm='SomeOtherDaemon'", outcome["stderr"])

    def test_clockface_recovery_triggers_on_watch_app_wait_but_not_complication_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "tests.log")
            receipt = Path(tmp, "hang-watchdog.json")
            cf_receipt = Path(tmp, "clockface-recovery.json")
            calls = []

            def fake_terminate(udid):
                calls.append(udid)
                return {"returncode": 0, "stderr": ""}

            log.write_text("")
            child = subprocess.Popen(["sleep", "5"])
            reaper = threading.Thread(target=child.wait, daemon=True)
            reaper.start()
            try:
                worker = threading.Thread(
                    target=lambda: dog.watch(
                        log,
                        child.pid,
                        receipt,
                        quiet=30.0,
                        poll=0.05,
                        watch_udid="WATCH-UDID-2",
                        clockface_receipt=cf_receipt,
                        clockface_terminator=fake_terminate,
                    )
                )
                worker.start()

                with log.open("a") as fh:
                    fh.write(
                        "    t =    82.15s         Wait for com.apple.clockface to idle\n"
                        "    t =   142.19s App animations complete notification not received, will attempt to continue.\n"
                        "    t =   143.25s Wait for com.bainluck.Bain-Luck.watchkitapp to become Running Foreground\n"
                        '    t =   143.26s Waiting 20.0s for "watch.complication.matchup.during" Any to exist\n'
                    )
                time.sleep(0.15)
                self.assertEqual(calls, [], "must not fire on Carousel watch.complication.* wait")

                with log.open("a") as fh:
                    fh.write('    t =   143.30s Waiting 15.0s for "watch.game-state" Any to exist\n')
                time.sleep(0.2)
                self.assertEqual(calls, ["WATCH-UDID-2"])

                child.terminate()
                worker.join(timeout=5)
                reaper.join(timeout=5)
                saved = json.loads(cf_receipt.read_text())
                self.assertEqual(saved["count"], 1)
                self.assertEqual(saved["recoveries"][0]["trigger"], "watch_app_foreground")
            finally:
                if child.poll() is None:
                    child.kill()

    def test_clockface_recovery_retries_failed_boundary_and_caps_at_three_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "tests.log")
            receipt = Path(tmp, "hang-watchdog.json")
            cf_receipt = Path(tmp, "clockface-recovery.json")
            outcomes = iter([
                {"returncode": -1, "stderr": "attempt 1 timed out"},
                {"returncode": -1, "stderr": "attempt 2 timed out"},
                {"returncode": -1, "stderr": "attempt 3 timed out"},
                {"returncode": 0, "stderr": ""},
            ])
            calls = []

            def fake_terminate(udid):
                calls.append(udid)
                return next(outcomes)

            log.write_text("")
            child = subprocess.Popen(["sleep", "5"])
            reaper = threading.Thread(target=child.wait, daemon=True)
            reaper.start()
            try:
                worker = threading.Thread(
                    target=lambda: dog.watch(
                        log,
                        child.pid,
                        receipt,
                        quiet=30.0,
                        poll=0.05,
                        watch_udid="WATCH-UDID-3",
                        clockface_receipt=cf_receipt,
                        clockface_terminator=fake_terminate,
                    )
                )
                worker.start()

                with log.open("a") as fh:
                    fh.write(
                        "    t =    82.15s         Wait for com.apple.clockface to idle\n"
                        "    t =   142.19s App animations complete notification not received, will attempt to continue.\n"
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testA]' passed (154.026 seconds).\n"
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testB]' started.\n"
                        '    t =     4.75s Waiting 20.0s for "watch.pick.101" Button to exist\n'
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testB]' passed (30.000 seconds).\n"
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testC]' passed (20.000 seconds).\n"
                    )
                time.sleep(0.25)
                self.assertEqual(len(calls), 3)

                child.terminate()
                worker.join(timeout=5)
                reaper.join(timeout=5)
                saved = json.loads(cf_receipt.read_text())
                self.assertEqual(saved["count"], 3)
                self.assertEqual(
                    [r["trigger"] for r in saved["recoveries"]],
                    ["safe_boundary", "watch_app_foreground", "safe_boundary"],
                )
            finally:
                if child.poll() is None:
                    child.kill()

    def test_clockface_recovery_fires_once_at_mid_test_third_stall(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp, "tests.log")
            receipt = Path(tmp, "hang-watchdog.json")
            cf_receipt = Path(tmp, "clockface-recovery.json")
            calls = []

            def fake_terminate(udid):
                calls.append(udid)
                return {"returncode": 0, "stderr": ""}

            log.write_text("")
            child = subprocess.Popen(["sleep", "5"])
            reaper = threading.Thread(target=child.wait, daemon=True)
            reaper.start()
            try:
                worker = threading.Thread(
                    target=lambda: dog.watch(
                        log,
                        child.pid,
                        receipt,
                        quiet=30.0,
                        poll=0.05,
                        watch_udid="WATCH-UDID-4",
                        clockface_receipt=cf_receipt,
                        clockface_terminator=fake_terminate,
                    )
                )
                worker.start()

                with log.open("a") as fh:
                    fh.write(
                        "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testLong]' started.\n"
                        "    t =    53.55s         Wait for com.apple.clockface to idle\n"
                        "    t =   113.62s App animations complete notification not received, will attempt to continue.\n"
                        "    t =   117.60s         Wait for com.apple.clockface to idle\n"
                        "    t =   177.65s App animations complete notification not received, will attempt to continue.\n"
                    )
                time.sleep(0.15)
                self.assertEqual(calls, [])

                with log.open("a") as fh:
                    fh.write(
                        "    t =   179.84s         Wait for com.apple.clockface to idle\n"
                        "    t =   239.90s App animations complete notification not received, will attempt to continue.\n"
                        "    t =   242.40s         Wait for com.apple.clockface to idle\n"
                        "    t =   302.44s App animations complete notification not received, will attempt to continue.\n"
                    )
                time.sleep(0.2)
                self.assertEqual(calls, ["WATCH-UDID-4"])

                child.terminate()
                worker.join(timeout=5)
                reaper.join(timeout=5)
                saved = json.loads(cf_receipt.read_text())
                self.assertEqual(saved["count"], 1)
                self.assertEqual(saved["recoveries"][0]["trigger"], "mid_test_3_stalls")
            finally:
                if child.poll() is None:
                    child.kill()


if __name__ == "__main__":
    unittest.main()
