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

    def test_a_watch_shut_down_after_the_suite_is_booted_before_the_installed_app_reads(self):
        # Run 44371871767 (navigation): 39 of 39 passed, then the Watch was Shutdown and
        # the installed-app reads failed. Booting it back keeps the same installed app.
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        recover = harness.index('if ! is_booted "$TEST_UDID"; then\n  echo')
        self.assertLess(harness.index('printf \'%s\\n\' "$TEST_EXIT" > "$OUT/test-exit.txt"'), recover)
        self.assertLess(recover, harness.index("<<'REGISTRATION'"))
        self.assertLess(recover, harness.index("<<'SIMSIGN'"))
        block = harness[recover:].split("\nfi\n", 1)[0]
        self.assertIn('boot_until_ready "$TEST_UDID" || true', block, "boot only; the reads still judge")
        for forbidden in ("install", "erase", "TEST_EXIT=", "run_xctest_suite"):
            self.assertNotIn(forbidden, block.replace("installed-app", ""))

    def test_the_journey_evidence_upload_outlasts_a_slow_storage_stall(self):
        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        step = workflow.split("- name: Preserve UI journey evidence", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("timeout-minutes: 10", step)
        self.assertIn("if: always()", step)

    def test_pre_connect_and_simulator_service_interruptions_are_retried_only_without_real_failures(self):
        samples = (
            "Runner encountered an error (Early unexpected exit, operation never finished bootstrapping - no restart will be attempted)",
            "Runner encountered an error (Failed to establish communication with the test runner.)",
            "The test runner failed to initialize for UI testing.",
            "CoreSimulatorService: Connection interrupted during boot",
            "SimLaunchHostService: Connection interrupted",
            "Simulator device failed to launch com.bainluck.Bain-Luck.watchkitapp with error: RequestDenied",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertIsNotNone(infra.infra_abort(sample))
                failed = "/x/PickerAliasJourneyTests.swift:12: error: -[BainLuckWatchUITests.PickerAliasJourneyTests testX] : XCTAssertTrue failed\n"
                self.assertIsNone(infra.infra_abort(failed + "\n" + sample))
                overrun = "Test Case '-[BainLuckWatchUITests.PickerAliasJourneyTests testX]' exceeded execution time allowance of 5 minutes.\n"
                self.assertIsNone(infra.infra_abort(overrun + "\n" + sample))

    def test_stage_guard_and_receipt_steps_have_five_minute_timeout(self):
        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        for step_name in (
            "Bound the execution step independently of its child supervisor",
            "Keep failed or interrupted execution receipts unpaid",
        ):
            step = workflow.split(f"- name: {step_name}", 1)[1].split("\n      - ", 1)[0]
            self.assertIn("timeout-minutes: 5", step, step_name)

    def test_execute_readiness_recovers_once_via_pair_reboot(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        execute_boot = harness.split("products-verification.json\"", 1)[1].split("XCODE_ARGS=", 1)[0]
        self.assertIn("reboot_pair_until_ready", execute_boot)


CLOCKFACE_CASE = "Test Case '-[BainLuckWatchUITests.WidgetTapJourneyTests testColdActualWidgetTapRetainsOfflineReading]'"
CLOCKFACE_OVERRUN = (
    f"{CLOCKFACE_CASE} started.\n"
    "    t =     0.00s Start Test at 2026-11-21 18:59:28.538\n"
    + "".join(
        f"    t = {i*62+17:7.2f}s         Wait for com.apple.clockface to idle\n"
        f"    t = {i*62+77:7.2f}s App animations complete notification not received, will attempt to continue.\n"
        for i in range(8)
    )
    + f"{CLOCKFACE_CASE} exceeded execution time allowance of 9 minutes. The test may have hung.\n"
    + "Restarting after unexpected exit, crash, or test timeout; summary will include totals from previous launches.\n"
    + "** TEST EXECUTE FAILED **\n"
)


class ClockfaceIdleRetryTests(unittest.TestCase):
    def test_verbatim_clockface_nine_minute_overrun_is_retried(self):
        reason = infra.infra_abort(CLOCKFACE_OVERRUN)
        self.assertIsNotNone(reason)
        self.assertIn("com.apple.clockface", reason)
        self.assertIn("testColdActualWidgetTapRetainsOfflineReading", reason)

    def test_three_clockface_stalls_below_threshold_are_not_retried(self):
        fewer = (
            f"{CLOCKFACE_CASE} started.\n"
            + "".join(
                f"    t = {i*62+17:7.2f}s         Wait for com.apple.clockface to idle\n"
                f"    t = {i*62+77:7.2f}s App animations complete notification not received, will attempt to continue.\n"
                for i in range(3)
            )
            + f"{CLOCKFACE_CASE} exceeded execution time allowance of 9 minutes.\n"
        )
        self.assertIsNone(infra.infra_abort(fewer))

    def test_in_app_idle_timeouts_are_never_retried(self):
        in_app = (
            f"{CLOCKFACE_CASE} started.\n"
            + "".join(
                f"    t = {i*62+17:7.2f}s         Wait for com.bainluck.Bain-Luck.watchkitapp to idle\n"
                f"    t = {i*62+77:7.2f}s App animations complete notification not received, will attempt to continue.\n"
                for i in range(8)
            )
            + f"{CLOCKFACE_CASE} exceeded execution time allowance of 9 minutes.\n"
        )
        self.assertIsNone(infra.infra_abort(in_app))

    def test_real_assertion_failure_beside_clockface_overrun_is_never_retried(self):
        failed = "/x/WidgetTapJourneyTests.swift:679: error: -[BainLuckWatchUITests.WidgetTapJourneyTests testActualCircularLauncherAndTap] : failed\n"
        self.assertIsNone(infra.infra_abort(failed + CLOCKFACE_OVERRUN))
        self.assertIsNone(infra.infra_abort("WATCH_UI_ACTUAL_CIRCULAR_LAUNCHER=FAIL\n" + CLOCKFACE_OVERRUN))

    def test_clockface_overrun_beside_launch_never_accepted_overrun_is_retried(self):
        self.assertIsNotNone(infra.infra_abort(LAUNCH_NEVER_ACCEPTED + "\n" + CLOCKFACE_OVERRUN))

    def test_harness_wires_clockface_recovery_receipt_and_retry_preservation(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertIn('--watch-udid "$TEST_UDID"', harness)
        self.assertIn('--clockface-receipt "$OUT/clockface-recovery.json"', harness)
        self.assertIn("clockface-recovery-infra-abort.json", harness)


PRE_SESSION_REFUSAL = (
    "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize]' started.\n"
    "    t =     0.08s Open com.bainluck.Bain-Luck.watchkitapp\n"
    "    t =     0.09s     Launch com.bainluck.Bain-Luck.watchkitapp\n"
    "    t =     0.09s         Waiting for system app quiescence\n"
    "<unknown>:0: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize] : "
    "Application 'com.bainluck.Bain-Luck.watchkitapp' does not have a process ID\n"
    "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize]' failed (70.326 seconds).\n"
    "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize]' started.\n"
    "    t =     0.05s         Open com.bainluck.Bain-Luck.watchkitapp\n"
    "    t =     0.05s             Launch com.bainluck.Bain-Luck.watchkitapp\n"
    "<unknown>:0: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize] : "
    "Failed to get background assertion for target app with pid 37670: No failure details provided\n"
    "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize]' failed (22.957 seconds).\n"
    "** TEST EXECUTE FAILED **\n"
)


class PreSessionLaunchRefusalTests(unittest.TestCase):
    def test_verbatim_44945738586_pre_session_launch_refusal_is_retried(self):
        reason = infra.infra_abort(PRE_SESSION_REFUSAL)
        self.assertIsNotNone(reason)
        self.assertIn("refused Watch app launch before automation session start", reason)
        self.assertIn("testAdaptiveScoreShortLiveAtAccessibilitySize", reason)
        self.assertIn("testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize", reason)

    def test_launch_error_after_automation_session_started_is_never_retried(self):
        after_session = PRE_SESSION_REFUSAL.replace(
            "<unknown>:0: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize]",
            "    t =     4.55s Setting up automation session\n"
            "<unknown>:0: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAlternativeCardSelectionAndCurrentReturnAtAccessibilitySize]",
            1,
        )
        self.assertIsNone(infra.infra_abort(after_session))

    def test_other_unknown_zero_error_or_crash_is_never_retried(self):
        other = (
            "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize]' started.\n"
            "    t =     0.09s     Launch com.bainluck.Bain-Luck.watchkitapp\n"
            "<unknown>:0: error: -[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize] : "
            "Test crashed with signal segfault\n"
            "Test Case '-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testAdaptiveScoreShortLiveAtAccessibilitySize]' failed (5.000 seconds).\n"
        )
        self.assertIsNone(infra.infra_abort(other))

    def test_real_assertion_failure_or_fail_marker_beside_launch_refusal_is_never_retried(self):
        real_err = (
            "/x/PickerCurrentGameJourneyTests.swift:45: error: "
            "-[BainLuckWatchUITests.PickerCurrentGameJourneyTests testTeamColorNamesAndMissingFallbackAtStandardSize] : failed\n"
        )
        self.assertIsNone(infra.infra_abort(PRE_SESSION_REFUSAL + real_err))
        self.assertIsNone(infra.infra_abort(PRE_SESSION_REFUSAL + "WATCH_UI_CURRENT_GAME_LARGE=FAIL\n"))

    def test_harness_terminates_warmup_watch_app_and_waits_for_carousel_before_suite(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        between = harness.split('>> "$OUT/preflight.log"\n', 1)[1].split("PHASE='BainLuckWatchUITests full suite", 1)[0]
        self.assertIn('xcrun simctl terminate "$TEST_UDID" com.bainluck.Bain-Luck.watchkitapp', between)
        self.assertIn('wait_services_ready "$TEST_UDID" com.apple.Carousel', between)


if __name__ == "__main__":
    unittest.main()
