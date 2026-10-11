"""Negative receipts cannot impersonate successful Watch UI interaction."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("polish", ROOT / "tools/watch_discovery_polish_receipt.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def passing_log():
    return "\n".join(f"{marker}\nTest Case '-[BainLuckWatchUITests.WatchDiscoverPolishTests {method}]' passed (1.23 seconds)."
                     for method, marker in MODULE.CASES.items())


class ReceiptTests(unittest.TestCase):
    def test_exact_receipt_passes(self):
        MODULE.verify(passing_log())

    def test_each_missing_marker_or_method_fails(self):
        for method, marker in MODULE.CASES.items():
            for altered in (passing_log().replace(marker, ""), passing_log().replace(method, "anotherMethod")):
                with self.subTest(method=method), self.assertRaises(ValueError):
                    MODULE.verify(altered)

    def test_failed_skipped_and_duplicate_cases_fail(self):
        for method in MODULE.CASES:
            case = f"Test Case '-[BainLuckWatchUITests.WatchDiscoverPolishTests {method}]'"
            for ending in ("failed (1.0 seconds).", "skipped (1.0 seconds).", "passed (1.0 seconds)."):
                with self.subTest(method=method, ending=ending), self.assertRaises(ValueError):
                    MODULE.verify(passing_log() + "\n" + case + " " + ending)

    def test_prefixed_substrings_and_fabricated_markers_fail(self):
        for marker in MODULE.CASES.values():
            for altered in ("logged " + marker, marker + " extra", "print(\"" + marker + "\")", marker + "\n" + marker):
                with self.subTest(marker=marker, altered=altered), self.assertRaises(ValueError):
                    MODULE.verify(passing_log().replace(marker, altered))

    def test_fabricated_method_lines_fail(self):
        for method in MODULE.CASES:
            with self.subTest(method=method), self.assertRaises(ValueError):
                MODULE.verify(passing_log().replace("Test Case '-[BainLuckWatchUITests.WatchDiscoverPolishTests " + method,
                                                   "quoted Test Case '-[BainLuckWatchUITests.WatchDiscoverPolishTests " + method))

    def test_harness_and_workflow_wire_gate(self):
        script = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertIn('python3 "$ROOT/tools/watch_discovery_polish_receipt.py" "$OUT/tests.log"', script)
        self.assertLess(script.index('tools/watch_discovery_polish_receipt.py'), script.index("PHASE='full-suite receipt verification'"))
        workflow = (ROOT / ".github/workflows/watch-mvp.yml").read_text()
        self.assertIn('test_watch_discovery_polish_receipt.py', workflow)
        self.assertEqual(workflow.count("- 'tools/watch_discovery_polish_receipt.py'"), 2)


if __name__ == "__main__":
    unittest.main()
