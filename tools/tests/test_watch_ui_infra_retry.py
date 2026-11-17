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

    def test_setup_rechecks_both_members_and_reboots_the_pair_at_most_once(self):
        # Run 43990443905 (corner): the phone shut down while the Watch was rebooted.
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        prepare = harness.split("ready_or_reboot_once \"$TEST_UDID\" com.apple.Carousel\n", 1)[1]
        recheck, rest = prepare.split("PHASE='verify exact paired simulator runtime architecture'", 1)
        self.assertIn('if ! is_booted "$PHONE_UDID" || ! is_booted "$TEST_UDID"; then', recheck)
        self.assertEqual(recheck.count("reboot_pair_until_ready"), 1, "one pair reboot, never a loop")
        waiter = harness.split("wait_services_ready() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('if ! is_booted "$udid"; then', waiter, "a device that left Booted stops the wait at once")

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


# Lines from run 44094233390's widgets shard (the specimen): the launch request was
# never accepted, the test overran, and the simulator later denied the launch.
CASE = "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testCurrentGameAndOfflineDetailsAtAccessibilitySize]'"
LAUNCH_NEVER_ACCEPTED = (
    f"{CASE} started.\n"
    "    t =     0.07s Start Test at 2026-11-17 15:16:35.952\n"
    "    t =     0.18s Set Up\n"
    "    t =     0.18s Open com.bainluck.Bain-Luck.watchkitapp\n"
    "    t =     0.18s     Launch com.bainluck.Bain-Luck.watchkitapp\n"
    "2026-11-17 15:16:36.430 xcodebuild[13455:56408] [MT] IDELaunchParametersSnapshot: no debugger version\n"
    f"{CASE} exceeded execution time allowance of 5 minutes. The test may have hung.\n"
    "2026-11-17 15:54:24.728 xcodebuild[13455:58758]  iOSSimulator: EBFA: Failed to launch app with identifier: "
    "com.bainluck.Bain-Luck.watchkitapp and options: {\n"
    "Restarting after unexpected exit, crash, or test timeout; summary will include totals from previous launches.\n"
    "Failing tests:\n\tPickerCurrentGameJourneyTests.testCurrentGameAndOfflineDetailsAtAccessibilitySize()\n"
    "** TEST EXECUTE FAILED **\n"
)


class LaunchNeverAcceptedTests(unittest.TestCase):
    def test_the_specimen_launch_the_simulator_never_accepted_is_retried(self):
        self.assertIn("never accepted the Watch app's launch", infra.infra_abort(LAUNCH_NEVER_ACCEPTED))

    def test_a_quiescence_wait_before_the_request_is_still_the_simulator(self):
        log = LAUNCH_NEVER_ACCEPTED.replace(
            "watchkitapp\n2026-11-17 15:16:36.430",
            "watchkitapp\n    t =     0.18s         Waiting for system app quiescence\n2026-11-17 15:16:36.430", 1)
        self.assertIn("    Waiting for system app quiescence", log)
        self.assertIsNotNone(infra.infra_abort(log))

    def test_an_overrun_after_our_app_started_is_never_retried(self):
        for later in ("Setting up automation session", "Wait for com.bainluck.Bain-Luck.watchkitapp to idle"):
            log = LAUNCH_NEVER_ACCEPTED.replace(
                "watchkitapp\n2026-11-17 15:16:36.430",
                f"watchkitapp\n    t =     0.62s         {later}\n2026-11-17 15:16:36.430", 1)
            self.assertIsNone(infra.infra_abort(log), later)

    def test_an_overrun_in_the_tests_own_steps_is_never_retried(self):
        log = LAUNCH_NEVER_ACCEPTED.replace(
            "watchkitapp\n2026-11-17 15:16:36.430",
            'watchkitapp\n    t =    40.00s Waiting 45.0s for "watch.pick.101" Button to exist\n2026-11-17 15:16:36.430', 1)
        self.assertIsNone(infra.infra_abort(log))

    def test_one_launch_overrun_beside_a_real_overrun_is_never_retried(self):
        other = ("Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testActualComplicationHost]' started.\n"
                 "    t =    60.00s Swipe left\n"
                 "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testActualComplicationHost]' exceeded "
                 "execution time allowance of 5 minutes.\n")
        self.assertIsNone(infra.infra_abort(LAUNCH_NEVER_ACCEPTED + other))

    def test_a_failed_check_beside_a_launch_overrun_is_never_retried(self):
        failed = ("/x/PickerCurrentGameJourneyTests.swift:40: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests "
                  "testScheduledStartBoundariesAtStandardSize] : XCTAssertTrue failed\n")
        self.assertIsNone(infra.infra_abort(LAUNCH_NEVER_ACCEPTED + failed))

    def test_a_lost_simulator_service_is_restarted_once_on_hosted_runners_only(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        restart = harness.split("restart_simulator_service_once() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('[[ "${GITHUB_ACTIONS:-}" == true && "$SIM_SERVICE_RESTARTED" -eq 0 ]] || return 1', restart)
        self.assertIn("SIM_SERVICE_RESTARTED=1", restart, "once, never a loop")
        boot = harness.split("boot_until_ready() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("for attempt in 1 2 3; do", boot, "still three boots at most")
        self.assertIn("-e 'SimLaunchHostService' -e 'Status=4294967295, isTerminal=YES'", boot,
                      "only when the boot ended at once or the launch host connection was lost")
        self.assertIn('|| echo "bootstatus exited $? for $udid"', boot, "a failed boot must not end the job under set -e")

    def test_the_harness_runs_xcodebuild_beside_the_hang_watchdog(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        suite = harness.split("run_xctest_suite() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('> "$OUT/tests.log" 2>&1 &', suite)
        self.assertIn('tools/watch_ui_hang_watchdog.py" "$OUT/tests.log" "$xcodebuild_pid"', suite)
        self.assertIn('if wait "$xcodebuild_pid"; then', suite, "the judged exit is xcodebuild's own")
        self.assertIn('kill "$watchdog_pid"', suite)


if __name__ == "__main__":
    unittest.main()
