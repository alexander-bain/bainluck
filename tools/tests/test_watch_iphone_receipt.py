"""Guard the completed full-suite evidence required by the iPhone receipt."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "watch_iphone_receipt.py"
SPEC = importlib.util.spec_from_file_location("watch_iphone_receipt", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RECEIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPT)


def summary(count=2083, failures=0, state="passed"):
    return (
        f"Test Suite 'All tests' {state} at 2026-10-03 12:00:00.000.\n"
        f"\t Executed {count} tests, with {failures} failures (0 unexpected) "
        "in 27.902 (29.156) seconds\n"
    )


class VerifiedSummaryTests(unittest.TestCase):
    def test_named_total_survives_trailing_class_bait(self):
        log = (
            summary()
            + "Test Suite 'StragglerTests' passed at 2026-10-03 12:00:01.000.\n"
            + "\t Executed 2 tests, with 0 failures (0 unexpected) in 0.1 seconds\n"
            + "** TEST SUCCEEDED **\n"
        )
        count, line = RECEIPT.verified_summary(log, 0)
        self.assertEqual(count, 2083)
        self.assertIn("Executed 2083 tests, with 0 failures", line)

    def test_rejects_incomplete_or_contradictory_evidence(self):
        class_only = (
            "Test Suite 'ExampleTests' passed at 2026-10-03 12:00:00.000.\n"
            "\t Executed 5 tests, with 0 failures (0 unexpected) in 0.1 seconds\n"
        )
        cases = {
            "failed suite": (summary(failures=3, state="failed") + "** TEST FAILED **\n", 65),
            "missing summary": ("** TEST SUCCEEDED **\n", 0),
            "class total only": (class_only + "** TEST SUCCEEDED **\n", 0),
            "started suite only": ("Test Suite 'All tests' started at 12:00.\n" + class_only, 137),
            "zero tests": (summary(count=0) + "** TEST SUCCEEDED **\n", 0),
            "missing success marker": (summary(), 0),
            "nonzero exit": (summary() + "** TEST SUCCEEDED **\n", 65),
            "contradictory failures": (summary(failures=2) + "** TEST SUCCEEDED **\n", 0),
            "failed suite with success marker": (summary(state="failed") + "** TEST SUCCEEDED **\n", 0),
            "unanchored success marker": (summary() + "diagnostic: ** TEST SUCCEEDED **\n", 0),
            "nonadjacent total": (summary().replace("\n\t", "\nOther output\n\t") + "** TEST SUCCEEDED **\n", 0),
        }
        for name, (log, exit_code) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    RECEIPT.verified_summary(log, exit_code)


if __name__ == "__main__":
    unittest.main()
