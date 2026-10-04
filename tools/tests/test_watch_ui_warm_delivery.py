"""Pure guards for the hosted warm-URL readiness handshake and delivery receipt."""
import copy
import importlib.util
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
