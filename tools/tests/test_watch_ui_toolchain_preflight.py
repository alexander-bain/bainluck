"""Portable identity-preflight guards: all subprocesses are mocked, no Apple calls."""

import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch

from tools import watch_ui_products as gate


class ToolchainPreflightTests(unittest.TestCase):
    commands = [
        ("xcodebuild", "-version"),
        ("xcrun", "swiftc", "--version"),
        ("xcrun", "--sdk", "watchsimulator", "--show-sdk-version"),
        ("xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"),
        ("xcrun", "--sdk", "watchsimulator", "--show-sdk-build-version"),
        ("xcrun", "--sdk", "iphonesimulator", "--show-sdk-build-version"),
    ]
    keys = ["xcode", "swift", "watch_sdk", "phone_sdk", "watch_sdk_build", "phone_sdk_build"]
    outputs = ["Xcode 27.0\nBuild version 27A266a", "Swift 6.2", "27.0", "27.0", "24R362", "24A335"]

    def test_all_six_exact_reads_and_outputs_preserved_without_retry(self):
        with patch.object(gate.subprocess, "check_output", side_effect=["  " + s + "\n" for s in self.outputs]) as run:
            self.assertEqual(gate.toolchain(), dict(zip(self.keys, self.outputs)))
        self.assertEqual(run.call_args_list, [call(c, text=True, timeout=60) for c in self.commands])

    def test_one_timeout_at_each_identity_read_recovers_only_that_command(self):
        for index, command in enumerate(self.commands):
            with self.subTest(command=command):
                effects = self.outputs[:index] + [subprocess.TimeoutExpired(command, 60)] + self.outputs[index:]
                with patch.object(gate.subprocess, "check_output", side_effect=effects) as run, patch.object(gate.sys, "stderr", new_callable=io.StringIO) as log:
                    self.assertEqual(gate.toolchain(), dict(zip(self.keys, self.outputs)))
                    self.assertIn(repr(command), log.getvalue())
                    self.assertEqual(log.getvalue().count("retrying once"), 1)
                expected = self.commands[:index] + [command] + self.commands[index:]
                self.assertEqual(run.call_args_list, [call(c, text=True, timeout=60) for c in expected])

    def test_two_timeouts_propagate_and_never_start_later_identity_reads(self):
        for index, command in enumerate(self.commands):
            with self.subTest(command=command):
                last = subprocess.TimeoutExpired(command, 60, output="partial untrusted identity")
                effects = self.outputs[:index] + [subprocess.TimeoutExpired(command, 60), last]
                with patch.object(gate.subprocess, "check_output", side_effect=effects) as run, patch.object(gate.sys, "stderr", new_callable=io.StringIO):
                    with self.assertRaises(subprocess.TimeoutExpired) as error:
                        gate.toolchain()
                self.assertIs(error.exception, last)
                self.assertEqual(run.call_count, index + 2)
                self.assertEqual(run.call_args_list[-2:], [call(command, text=True, timeout=60)] * 2)

    def test_nonzero_exit_is_not_retried_or_swallowed(self):
        error = subprocess.CalledProcessError(72, self.commands[0], output="no selected Xcode")
        with patch.object(gate.subprocess, "check_output", side_effect=error) as run:
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                gate.toolchain()
        self.assertIs(caught.exception, error)
        run.assert_called_once_with(self.commands[0], text=True, timeout=60)

    def test_missing_tool_is_not_retried_or_swallowed(self):
        with patch.object(gate.subprocess, "check_output", side_effect=FileNotFoundError("missing")) as run:
            with self.assertRaises(FileNotFoundError):
                gate.toolchain()
        self.assertEqual(run.call_count, 1)

    def test_timeout_followed_by_real_failure_stops_without_third_attempt(self):
        effects = [subprocess.TimeoutExpired(self.commands[0], 60), subprocess.CalledProcessError(1, self.commands[0])]
        with patch.object(gate.subprocess, "check_output", side_effect=effects) as run, patch.object(gate.sys, "stderr", new_callable=io.StringIO):
            with self.assertRaises(subprocess.CalledProcessError):
                gate.toolchain()
        self.assertEqual(run.call_count, 2)

    def test_every_read_can_retry_once_without_unbounded_loop(self):
        effects = []
        for command, output in zip(self.commands, self.outputs):
            effects.extend([subprocess.TimeoutExpired(command, 60), output])
        with patch.object(gate.subprocess, "check_output", side_effect=effects) as run, patch.object(gate.sys, "stderr", new_callable=io.StringIO):
            self.assertEqual(gate.toolchain(), dict(zip(self.keys, self.outputs)))
        self.assertEqual(run.call_count, 12)
        self.assertTrue(all(c.kwargs["timeout"] == 60 for c in run.call_args_list))

    def test_successful_retry_still_requires_exact_manifest_toolchain(self):
        effects = [subprocess.TimeoutExpired(self.commands[0], 60)] + self.outputs
        with patch.object(gate.subprocess, "check_output", side_effect=effects), patch.object(gate.sys, "stderr", new_callable=io.StringIO):
            observed = gate.toolchain()
        for key in self.keys:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest = {"schema": 1, "sha": "a" * 40, "configuration": "Debug",
                            "source_fingerprint": "b" * 64,
                            "toolchain": {**observed, key: "different identity"}}
                (root / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "toolchain/SDK mismatch"):
                    gate.verify_manifest(root, "a" * 40, observed, "c" * 64, "b" * 64)


if __name__ == "__main__":
    unittest.main()
