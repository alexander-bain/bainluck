import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("infra", ROOT / "tools/watch_ui_infra_retry.py")
infra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(infra)

# Lines from run 43867918866's corner shard (the specimen).
DROPPED = (
    "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testActualCornerLauncherAndTap]' started.\n"
    "    t =    92.75s Find the Cell (Element at index 3)\n"
    '2026-11-16 14:11:04.138 xcodebuild[25391:102340]  iOSSimulator: <DVTiPhoneSimulator, codex-watch-ui-companion> '
    'unable to connect to "com.apple.instruments.deviceservice.lockdown" - timed out after 120 seconds\n'
    "Restarting after unexpected exit, crash, or test timeout; summary will include totals from previous launches.\n"
    "\t Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.000) seconds\n"
    "Failing tests:\n\tWidgetTapJourneyTests.testActualCornerLauncherAndTap()\n** TEST EXECUTE FAILED **\n"
)
PRECONNECT = "\tBainLuckWatchUITests-Runner (10765) encountered an error (Test crashed with signal term before establishing connection.)\n"


class InfraRetryTests(unittest.TestCase):
    def test_the_specimen_dropped_connection_is_retried(self):
        self.assertIn("deviceservice.lockdown", infra.infra_abort(DROPPED))

    def test_a_runner_that_died_before_connecting_is_retried(self):
        self.assertIn("before establishing connection", infra.infra_abort(PRECONNECT))

    def test_a_failed_check_is_never_retried_even_beside_a_dropped_connection(self):
        failed = ("/x/WidgetTapJourneyTests.swift:40: error: -[BainLuckWatchUITests.WidgetTapJourneyTests "
                  "testActualCornerLauncherAndTap] : XCTAssertTrue failed\n")
        self.assertIsNone(infra.infra_abort(failed + DROPPED))

    def test_a_timed_out_test_is_never_retried(self):
        timeout = ("Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testX]' exceeded execution "
                   "time allowance of 3 minutes.\n")
        self.assertIsNone(infra.infra_abort(timeout + DROPPED))

    def test_a_failure_marker_is_never_retried(self):
        self.assertIsNone(infra.infra_abort("WATCH_UI_ACTUAL_CORNER_LAUNCHER=FAIL\n" + DROPPED))

    def test_an_ordinary_failure_without_a_connection_signature_is_not_retried(self):
        self.assertIsNone(infra.infra_abort("Failing tests:\n\tX.testY()\n** TEST EXECUTE FAILED **\n"))

    def test_the_harness_retries_once_and_keeps_the_first_log(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertEqual(harness.count('python3 "$ROOT/tools/watch_ui_infra_retry.py"'), 1)
        self.assertEqual(harness.count("run_xctest_suite\n"), 2, "one run plus at most one retry")
        self.assertIn('cp "$OUT/tests.log" "$OUT/tests-infra-abort.log"', harness)
        self.assertIn('wait_services_ready "$PHONE_UDID" com.apple.SpringBoard', harness)
        self.assertIn('wait_services_ready "$TEST_UDID" com.apple.Carousel', harness)
        retry = harness.split('cp "$OUT/tests.log" "$OUT/tests-infra-abort.log"', 1)[1].split("fi\n", 1)[0]
        self.assertIn("reboot_pair_until_ready", retry, "the retry waits for a ready pair first")

    def test_setup_waits_for_readiness_and_installs_at_most_twice(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertIn('ready_or_reboot_once "$PHONE_UDID" com.apple.SpringBoard', harness)
        self.assertIn('ready_or_reboot_once "$TEST_UDID" com.apple.Carousel', harness)
        self.assertEqual(harness.count("install_pair\n"), 1, "one retried install, never a loop")
        self.assertIn("if ! install_pair; then", harness)

    def test_the_warm_up_runs_once_before_the_measured_suite_and_judges_nothing(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        execute = harness.split("XCODE_ARGS=(-xctestrun", 1)[1]
        warm, measured = execute.split("run_xctest_suite() {", 1)
        self.assertEqual(warm.count("xcodebuild test-without-building"), 1, "one warm-up, never a loop")
        self.assertIn('"-only-testing:$WARMUP_CASE"', warm, "the warm-up runs a single case")
        self.assertIn('> "$OUT/tests-warmup.log"', warm, "kept apart from the judged tests.log")
        self.assertIn('-resultBundlePath "$RUN/warmup.xcresult"', warm)
        self.assertIn("(not judged)", warm)
        self.assertNotIn("TEST_EXIT", warm, "the warm-up never sets the judged exit")
        self.assertNotIn("tests-warmup.log", measured)
        case = harness.split("WARMUP_CASE='", 1)[1].split("'", 1)[0].rsplit("/", 1)[1]
        tests = (ROOT / "ios/Bain Luck/BainLuckWatchUITests/PickerCurrentGameJourneyTests.swift").read_text()
        self.assertIn(f"func {case}()", tests, "the warm-up case must exist")


if __name__ == "__main__":
    unittest.main()
