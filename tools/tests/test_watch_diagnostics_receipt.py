import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("receipt", ROOT / "tools/watch_diagnostics_receipt.py")
receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(receipt)


class DiagnosticsReceiptTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row for case, marker in receipt.CASES.items() for row in
            (f"Test Case '-[BainLuckWatchUITests.WatchDiagnosticsJourneyTests {case}]' passed (40.0 seconds).", marker)]

    def test_actual_harness_requires_diagnostics_receipt(self):
        harness = (ROOT / "tools/watch-ui-journey.sh").read_text()
        self.assertIn('python3 "$ROOT/tools/watch_diagnostics_receipt.py" --log "$OUT/tests.log"', harness)
        self.assertLess(harness.index('tools/watch_diagnostics_receipt.py'), harness.rindex('tools/watch_iphone_receipt.py'))

    def test_complete_actual_cases(self):
        receipt.validate("\n".join(self.rows))

    def test_each_missing_or_duplicate_case_or_marker_is_rejected(self):
        for row in self.rows:
            for rows in ([v for v in self.rows if v != row], [*self.rows, row]):
                with self.subTest(row=row, count=len(rows)), self.assertRaises(ValueError):
                    receipt.validate("\n".join(rows))

    def test_failed_skipped_or_prefixed_evidence_is_rejected(self):
        for row in self.rows:
            replacements = ["prefix " + row]
            if " passed " in row:
                replacements += [row.replace(" passed ", " failed "), row.replace(" passed ", " skipped ")]
            for replacement in replacements:
                with self.subTest(row=replacement), self.assertRaises(ValueError):
                    receipt.validate("\n".join(replacement if v == row else v for v in self.rows))
        for row in self.rows[::2]:
            with self.subTest(contradiction=row), self.assertRaises(ValueError):
                receipt.validate("\n".join([*self.rows, row.replace(" passed ", " failed ")]))
