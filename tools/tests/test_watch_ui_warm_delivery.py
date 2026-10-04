"""Pure guards for the hosted warm-URL readiness handshake and delivery receipt."""
import copy
import importlib.util
from pathlib import Path
import unittest
import json
import subprocess
import tempfile
import sys
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("warm_delivery", Path(__file__).resolve().parents[1] / "watch_ui_warm_delivery.py")
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)

SHA = "a" * 40
UDID = "11111111-2222-4333-8444-555555555555"
NONCE = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


class WarmDeliveryTests(unittest.TestCase):
    def receipt(self):
        return {"sha": SHA, "udid": UDID, "verdict": "PASS", "deliveries": [
            {"step": 1, "nonce": NONCE, "exit_code": 0},
            {"step": 2, "nonce": NONCE, "exit_code": 0},
        ]}

    def test_valid_readiness_normalizes_uuid(self):
        for step in (1, 2):
            self.assertEqual(warm.readiness(f"WATCH_UI_WARM_READY={step}:{NONCE.upper()}"), (step, NONCE))

    def test_malformed_and_non_uuid_markers(self):
        for line in ["", "ordinary XCTest output", f"WATCH_UI_WARM_READY=0:{NONCE}",
                     f"WATCH_UI_WARM_READY=3:{NONCE}", f"WATCH_UI_WARM_READY=1:{NONCE}:extra",
                     f"prefix WATCH_UI_WARM_READY=1:{NONCE}", "WATCH_UI_WARM_READY=1:not-a-uuid",
                     "WATCH_UI_WARM_READY=1:" + "-" * 36, "WATCH_UI_WARM_READY=1:" + "g" * 36,
                     "WATCH_UI_WARM_READY=1:" + "a" * 35]:
            with self.subTest(line=line):
                self.assertIsNone(warm.readiness(line))

    def test_valid_two_step_receipt(self):
        self.assertTrue(warm.verify(self.receipt(), SHA, UDID))

    def test_wrong_source_destination_or_verdict(self):
        for key, value in [("sha", "b" * 40), ("udid", "booted"), ("verdict", "UNPAID")]:
            receipt = self.receipt()
            receipt[key] = value
            with self.subTest(key=key):
                self.assertFalse(warm.verify(receipt, SHA, UDID))
        for key in ["sha", "udid", "verdict", "deliveries"]:
            receipt = self.receipt()
            del receipt[key]
            with self.subTest(missing=key):
                self.assertFalse(warm.verify(receipt, SHA, UDID))

    def test_missing_extra_duplicate_and_out_of_order_steps(self):
        valid = self.receipt()["deliveries"]
        for steps in [[], valid[:1], valid[::-1], [valid[0], valid[0]], valid + [valid[1]]]:
            receipt = self.receipt()
            receipt["deliveries"] = copy.deepcopy(steps)
            with self.subTest(steps=steps):
                self.assertFalse(warm.verify(receipt, SHA, UDID))
        receipt = self.receipt()
        del receipt["deliveries"][1]["step"]
        self.assertFalse(warm.verify(receipt, SHA, UDID))

    def test_each_failed_or_missing_delivery_exit(self):
        for index in (0, 1):
            for code in (1, 65, 124):
                receipt = self.receipt()
                receipt["deliveries"][index]["exit_code"] = code
                with self.subTest(index=index, code=code):
                    self.assertFalse(warm.verify(receipt, SHA, UDID))
            receipt = self.receipt()
            del receipt["deliveries"][index]["exit_code"]
            self.assertFalse(warm.verify(receipt, SHA, UDID))

    def test_missing_empty_or_different_nonce(self):
        for index in (0, 1):
            receipt = self.receipt()
            del receipt["deliveries"][index]["nonce"]
            self.assertFalse(warm.verify(receipt, SHA, UDID))
            receipt = self.receipt()
            receipt["deliveries"][index]["nonce"] = ""
            self.assertFalse(warm.verify(receipt, SHA, UDID))
        receipt = self.receipt()
        receipt["deliveries"][1]["nonce"] = UDID
        self.assertFalse(warm.verify(receipt, SHA, UDID))



class WarmWatcherTests(unittest.TestCase):
    def invoke(self, lines, result=None, hosted=True):
        with tempfile.TemporaryDirectory() as root:
            log = Path(root) / "tests.log"
            receipt = Path(root) / "receipt.json"
            log.write_text("\n".join(lines) + "\n")
            args = ["watch_ui_warm_delivery.py", "--log", str(log), "--receipt", str(receipt),
                    "--sha", SHA, "--udid", UDID]
            env = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"} if hosted else {}
            outcome = result if result is not None else subprocess.CompletedProcess([], 0, "", "")
            with patch.object(sys, "argv", args), \
                 patch.dict(warm.os.environ, env, clear=True), \
                 patch.object(warm.subprocess, "run") as command, \
                 patch.object(warm.time, "monotonic", side_effect=[0, 0, 1201]), \
                 patch.object(warm.time, "sleep"):
                if isinstance(outcome, BaseException):
                    command.side_effect = outcome
                else:
                    command.return_value = outcome
                status = None
                try:
                    warm.main()
                except SystemExit as error:
                    status = error.code
                calls = command.call_args_list
            saved = json.loads(receipt.read_text()) if receipt.exists() else None
            return status, saved, calls

    def markers(self):
        return [f"WATCH_UI_WARM_READY=1:{NONCE}", f"WATCH_UI_WARM_READY=2:{NONCE}"]

    def test_exact_two_explicit_destination_commands(self):
        status, receipt, calls = self.invoke(self.markers())
        self.assertIsNone(status)
        self.assertTrue(warm.verify(receipt, SHA, UDID))
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call.args[0], ["xcrun", "simctl", "openurl", UDID, "bainluck-watch://selected-game"])
            self.assertEqual(call.kwargs, {"capture_output": True, "text": True, "timeout": 15})

    def test_duplicate_marker_does_not_repeat_delivery(self):
        first, second = self.markers()
        status, receipt, calls = self.invoke([first, first, second])
        self.assertIsNone(status)
        self.assertEqual(len(calls), 2)
        self.assertEqual([item["step"] for item in receipt["deliveries"]], [1, 2])

    def test_wrong_nonce_and_out_of_order_remain_unpaid(self):
        first, second = self.markers()
        for lines, expected_calls in [([second], 0), ([first, second.replace(NONCE, UDID)], 1)]:
            with self.subTest(lines=lines):
                status, receipt, calls = self.invoke(lines)
                self.assertEqual(status, 1)
                self.assertEqual(receipt["verdict"], "UNPAID")
                self.assertIn("handshake", receipt["reason"])
                self.assertEqual(len(calls), expected_calls)

    def test_subprocess_failure_and_timeout_remain_unpaid(self):
        for outcome, code in [(subprocess.CompletedProcess([], 65, "", "delivery failed"), 65),
                              (subprocess.TimeoutExpired("mock openurl", 15), 124)]:
            with self.subTest(code=code):
                status, receipt, calls = self.invoke(self.markers(), result=outcome)
                self.assertEqual(status, code)
                self.assertEqual(receipt["verdict"], "UNPAID")
                self.assertEqual(len(calls), 1)
                self.assertEqual(receipt["deliveries"][0]["exit_code"], code)
                self.assertFalse(warm.verify(receipt, SHA, UDID))

    def test_local_environment_refused_before_command(self):
        status, receipt, calls = self.invoke(self.markers(), hosted=False)
        self.assertIn("disposable hosted runner", str(status))
        self.assertIsNone(receipt)
        self.assertEqual(calls, [])

if __name__ == "__main__":
    unittest.main()
