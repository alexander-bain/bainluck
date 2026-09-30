import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import issue_progress as p


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.issue = {
            "number": 2,
            "title": "A | B",
            "url": "https://example.test/2",
            "state": "OPEN",
            "labels": [],
            "fields": {
                "Status": "In Progress",
                "Delivery stage": "Building",
                "Delivery owner": "Discover",
                "Next step": "Ship card",
            },
        }

    def test_deterministic_order_and_separate_delivery_fields(self):
        other = copy.deepcopy(self.issue)
        other["number"] = 1
        a = p.render([self.issue, other], "2026-09-29T18:00:00Z")
        self.assertEqual(a, p.render([other, self.issue], "2026-09-29T18:00:00Z"))
        self.assertIn("In Progress | Building | Discover | Ship card", a)
        self.assertIn(r"A \| B", a)

    def test_user_waits_include_label_status_drift_and_exclude_closed(self):
        self.issue["labels"] = ["needs-user"]
        self.assertIn("- [#2]", p.render([self.issue], "now"))
        self.issue["state"] = "CLOSED"
        self.assertNotIn("- [#2]", p.render([self.issue], "now"))

    def test_missing_fields_are_not_guessed(self):
        self.issue["fields"] = {}
        text = p.render([self.issue], "now")
        self.assertIn("Not recorded", text)
        self.assertIn("does not cover issues outside", text)

    def test_duplicates_refused(self):
        with self.assertRaises(ValueError):
            p.render([self.issue, self.issue], "now")

    def test_api_failure_preserves_existing_timestamped_view(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "view.md"
            output.write_text("old view with old timestamp")
            with patch.object(
                sys, "argv", ["issue_progress.py", "2", "--output", str(output)]
            ), patch.object(p, "read_issue", side_effect=RuntimeError("denied")):
                with self.assertRaises(RuntimeError):
                    p.main()
            self.assertEqual(output.read_text(), "old view with old timestamp")


if __name__ == "__main__":
    unittest.main()
