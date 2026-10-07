"""Package-resolution retries are bounded and preserve failed attempt evidence."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "watch_resolve_packages.py"
SPEC = importlib.util.spec_from_file_location("watch_resolve_packages", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RESOLUTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOLUTION)


COMMAND = [
    "xcodebuild",
    "-resolvePackageDependencies",
    "-project",
    "/isolated/Bain Luck/Bain Luck.xcodeproj",
    "-scheme",
    "BainLuckWatchUITests",
    "-clonedSourcePackagesDirPath",
    "/isolated/packages",
]
# Error format retained from the actual d118 hosted build-for-testing failure.
FIREBASE_TIMEOUT = (
    "xcodebuild: error: Could not resolve package dependencies:\n"
    "  failed downloading 'https://dl.google.com/firebase/ios/bin/abseil/"
    "1.2024072200.0/rc0/absl.zip' which is required by binary target 'absl': "
    'downloadError("The request timed out.")\n'
    "  failed downloading 'https://dl.google.com/firebase/ios/bin/grpc/"
    "1.69.1/rc0/grpc.zip' which is required by binary target 'grpc': "
    'downloadError("The request timed out.")\n'
    "  failed downloading 'https://dl.google.com/firebase/ios/bin/grpc/"
    "1.69.1/rc0/grpcpp.zip' which is required by binary target 'grpcpp': "
    'downloadError("The request timed out.")\n'
    "  fatalError\n"
)
# Log tail retained from hosted Watch run 37508835672 (corner job 112426774845):
# SwiftPM prints the failure inline before the result-bundle line, then the
# final diagnostic repeats it.
LOST_CONNECTION_LINE = (
    "failed downloading 'https://dl.google.com/firebase/ios/bin/grpc/1.69.1/rc0/"
    "grpcpp.zip' which is required by binary target 'grpcpp': "
    'downloadError("The network connection was lost.")'
)
FIREBASE_LOST_CONNECTION = (
    "Checking out 4.1.1 of package \u2018GTMAppAuth\u2019\n\n"
    + LOST_CONNECTION_LINE
    + "fatalError2026-10-06 18:14:19.982 xcodebuild[22825:58400] Writing error result bundle"
    " to /var/folders/8w/T/ResultBundle_2026-06-10_18-14-0019.xcresult\n"
    "xcodebuild: error: Could not resolve package dependencies:\n  "
    + LOST_CONNECTION_LINE
    + "\n  fatalError\n"
)
SUCCESS = "Resolved source packages:\n  Firebase: https://github.com/firebase/firebase-ios-sdk @ 12.0.0\n"


class ResolutionTests(unittest.TestCase):
    def exercise(self, outcomes):
        calls = []
        sleeps = []

        def runner(command, **kwargs):
            calls.append(list(command))
            self.assertEqual(command, COMMAND)
            self.assertIn("-resolvePackageDependencies", command)
            self.assertFalse({"build", "build-for-testing", "test", "test-without-building"} & set(command))
            self.assertEqual(kwargs["stderr"], subprocess.STDOUT)
            self.assertEqual(kwargs["timeout"], 900)
            self.assertFalse(kwargs["check"])
            self.assertLessEqual(len(calls), len(outcomes), "Unexpected extra resolution attempt")
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                kwargs["stdout"].write("Resolution started, no completed result\n")
                raise outcome
            exit_code, log = outcome
            kwargs["stdout"].write(log)
            return SimpleNamespace(returncode=exit_code)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            receipt = RESOLUTION.run_resolution(COMMAND, output, runner=runner, sleep=sleeps.append)
            persisted = json.loads((output / "resolution-receipt.json").read_text())
            self.assertEqual(persisted, receipt)
            self.assertEqual(len(receipt["attempts"]), len(calls))
            for number, attempt in enumerate(receipt["attempts"], 1):
                self.assertEqual(attempt["attempt"], number)
                self.assertEqual(Path(attempt["log"]), output / f"attempt-{number}.log")
                outcome = outcomes[number - 1]
                expected_exit = 124 if isinstance(outcome, subprocess.TimeoutExpired) else 127 if isinstance(outcome, OSError) else outcome[0]
                self.assertEqual(attempt["exit_code"], expected_exit)
            logs = [(output / f"attempt-{number}.log").read_text() for number in range(1, len(calls) + 1)]
            self.assertFalse((output / f"attempt-{len(calls) + 1}.log").exists())
        return receipt, logs, calls, sleeps

    def test_real_firebase_timeout_retries_once_and_preserves_both_attempts(self):
        receipt, logs, calls, sleeps = self.exercise([(74, FIREBASE_TIMEOUT), (0, SUCCESS)])
        self.assertEqual(receipt["verdict"], "RESOLVED")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertIn(FIREBASE_TIMEOUT, logs[0])
        self.assertIn(SUCCESS, logs[1])

    def test_persistent_download_failure_stops_after_second_attempt(self):
        receipt, logs, calls, sleeps = self.exercise([(74, FIREBASE_TIMEOUT), (74, FIREBASE_TIMEOUT)])
        self.assertEqual(receipt["verdict"], "FAILED")
        self.assertEqual(receipt["exit_code"], 74)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertTrue(all(FIREBASE_TIMEOUT in log for log in logs))

    def test_non74_download_timeout_is_not_retried_or_accepted(self):
        receipt, logs, calls, sleeps = self.exercise([(65, FIREBASE_TIMEOUT)])
        self.assertEqual(receipt["verdict"], "FAILED")
        self.assertEqual(receipt["exit_code"], 65)
        self.assertEqual(len(calls), 1)
        self.assertFalse(sleeps)
        self.assertIn(FIREBASE_TIMEOUT, logs[0])

    def test_integrity_configuration_and_unclassified_timeout_fail_closed(self):
        failures = {
            "checksum": "checksum of downloaded artifact does not match checksum specified by the manifest\n",
            "configuration": "xcodebuild: error: The project does not contain a scheme named 'BainLuckWatchUITests'.\n",
            "unclassified timeout": "xcodebuild: error: Timed out waiting for a simulator destination.\n",
            "mixed integrity and download": FIREBASE_TIMEOUT + "checksum of downloaded artifact does not match manifest\n",
            "earlier integrity failure": "checksum mismatch before final diagnostic\n" + FIREBASE_TIMEOUT,
            "earlier configuration failure": "xcodebuild: error: invalid project configuration\n" + FIREBASE_TIMEOUT,
        }
        for name, log in failures.items():
            with self.subTest(name=name):
                receipt, logs, calls, sleeps = self.exercise([(74, log)])
                self.assertEqual(receipt["verdict"], "FAILED")
                self.assertEqual(receipt["exit_code"], 74)
                self.assertEqual(len(calls), 1)
                self.assertFalse(sleeps)
                self.assertIn(log, logs[0])

    def test_observed_lost_connection_retries_once_and_preserves_both_attempts(self):
        receipt, logs, calls, sleeps = self.exercise([(74, FIREBASE_LOST_CONNECTION), (0, SUCCESS)])
        self.assertEqual(receipt["verdict"], "RESOLVED")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertTrue(receipt["attempts"][0]["retryable_download_timeout"])
        self.assertIn(FIREBASE_LOST_CONNECTION, logs[0])
        self.assertIn(SUCCESS, logs[1])

    def test_persistent_lost_connection_stops_after_second_attempt(self):
        receipt, logs, calls, sleeps = self.exercise([(74, FIREBASE_LOST_CONNECTION)] * 2)
        self.assertEqual(receipt["verdict"], "FAILED")
        self.assertEqual(receipt["exit_code"], 74)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertTrue(all(FIREBASE_LOST_CONNECTION in log for log in logs))

    def test_non74_lost_connection_is_not_retried(self):
        receipt, logs, calls, sleeps = self.exercise([(65, FIREBASE_LOST_CONNECTION)])
        self.assertEqual(receipt["verdict"], "FAILED")
        self.assertEqual(len(calls), 1)
        self.assertFalse(sleeps)

    def test_lost_connection_mixed_with_other_failures_fails_closed(self):
        final = "xcodebuild: error: Could not resolve package dependencies:\n  " + LOST_CONNECTION_LINE
        failures = {
            "checksum in final": final + "\n  checksum of downloaded artifact does not match manifest\n  fatalError\n",
            "auth earlier": "authentication failed for https://github.com/firebase\n" + final + "\n  fatalError\n",
            "configuration earlier": "xcodebuild: error: invalid project configuration\n" + final + "\n  fatalError\n",
            "simulator earlier": "xcodebuild: error: Unable to find a destination matching the provided destination specifier\n" + final + "\n  fatalError\n",
            "runtime earlier": "xcodebuild: error: iOS 26.0 runtime is not installed\n" + final + "\n  fatalError\n",
            "other download error earlier": 'downloadError("The certificate for this server is invalid.")\n' + final + "\n  fatalError\n",
        }
        for name, log in failures.items():
            with self.subTest(name=name):
                receipt, logs, calls, sleeps = self.exercise([(74, log)])
                self.assertEqual(receipt["verdict"], "FAILED")
                self.assertEqual(len(calls), 1)
                self.assertFalse(sleeps)
                self.assertFalse(receipt["attempts"][0]["retryable_download_timeout"])

    def test_unobserved_transport_messages_remain_unpaid(self):
        for message in ("The Internet connection appears to be offline.", "cancelled", "An unknown error occurred."):
            log = FIREBASE_LOST_CONNECTION.replace("The network connection was lost.", message)
            with self.subTest(message=message):
                receipt, logs, calls, sleeps = self.exercise([(74, log)])
                self.assertEqual(receipt["verdict"], "FAILED")
                self.assertEqual(len(calls), 1)
                self.assertFalse(sleeps)

    def test_lost_connection_retry_interrupted_preserves_first_failure(self):
        receipt, logs, calls, sleeps = self.exercise(
            [(74, FIREBASE_LOST_CONNECTION), subprocess.TimeoutExpired(COMMAND, 900)]
        )
        self.assertEqual(receipt["verdict"], "TIMED_OUT")
        self.assertEqual(len(calls), 2)
        self.assertIn(FIREBASE_LOST_CONNECTION, logs[0])

    def test_subprocess_timeout_is_not_a_success_or_retry(self):
        receipt, logs, calls, sleeps = self.exercise([subprocess.TimeoutExpired(COMMAND, 900)])
        self.assertEqual(receipt["verdict"], "TIMED_OUT")
        self.assertEqual(receipt["exit_code"], 124)
        self.assertEqual(len(calls), 1)
        self.assertFalse(sleeps)
        self.assertIn("Resolution started, no completed result", logs[0])

    def test_retry_timeout_preserves_first_failure_and_does_not_attempt_third_run(self):
        receipt, logs, calls, sleeps = self.exercise([(74, FIREBASE_TIMEOUT), subprocess.TimeoutExpired(COMMAND, 900)])
        self.assertEqual(receipt["verdict"], "TIMED_OUT")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertIn(FIREBASE_TIMEOUT, logs[0])
        self.assertIn("Resolution started, no completed result", logs[1])

    def test_first_attempt_success_never_retries(self):
        receipt, logs, calls, sleeps = self.exercise([(0, SUCCESS)])
        self.assertEqual(receipt["verdict"], "RESOLVED")
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(len(calls), 1)
        self.assertFalse(sleeps)
        self.assertIn(SUCCESS, logs[0])

    def test_process_start_failure_is_retained_without_retry(self):
        receipt, logs, calls, sleeps = self.exercise([FileNotFoundError("xcodebuild unavailable")])
        self.assertEqual(receipt["verdict"], "FAILED")
        self.assertEqual(receipt["exit_code"], 127)
        self.assertEqual(len(calls), 1)
        self.assertFalse(sleeps)
        self.assertIn("xcodebuild unavailable", logs[0])

    def test_nonresolution_and_mixed_action_commands_never_invoke_runner(self):
        commands = {
            "empty": [],
            "build only": ["xcodebuild", "build-for-testing"],
            "wrong executable": ["other-tool", "-resolvePackageDependencies"],
            "missing resolution": ["xcodebuild", "-project", "Example.xcodeproj"],
        }
        for action in ("build", "build-for-testing", "test", "test-without-building", "archive", "clean", "install"):
            commands[f"mixed {action}"] = COMMAND + [action]
        for name, command in commands.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                def forbidden_runner(*args, **kwargs):
                    self.fail("A nonresolution command reached the subprocess runner")

                with self.assertRaises(ValueError):
                    RESOLUTION.run_resolution(command, Path(directory), runner=forbidden_runner)


if __name__ == "__main__":
    unittest.main()
