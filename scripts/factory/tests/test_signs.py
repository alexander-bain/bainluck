from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collect import history_signals
from model import instant
from signs import add_signs, switched_off, wrong_numbers


class SignRecords(unittest.TestCase):
    def test_switch_off_confirmation_counts_but_a_plan_or_label_does_not(self):
        since = "2026-11-19T22:00:00Z"
        origin = {"author_association": "OWNER", "created_at": "2026-11-19T22:58:35Z"}
        comments = [
            {
                **origin,
                "id": 7024584672,
                "body": "switched off #12288 (server + website) — Atlas",
            },
            {**origin, "id": 1, "body": "merging #12971 (server) — switched off"},
            {
                **origin,
                "id": 2,
                "body": "Switch both off now. Report 'switched off' when done.",
            },
            {**origin, "id": 3, "author_association": "NONE", "body": "switched off"},
        ]
        self.assertEqual(
            switched_off(comments, since),
            [
                {
                    "kind": "switched-off",
                    "number": 7024584672,
                    "at": origin["created_at"],
                },
            ],
        )

    def test_issue_prefix_is_exact_and_an_incomplete_search_is_missing(self):
        since = "2026-11-19T22:00:00Z"
        at = "2026-11-20T00:42:39Z"
        results = {
            "pageInfo": {"hasNextPage": False},
            "issueCount": 2,
            "nodes": [
                {
                    "number": 13127,
                    "createdAt": at,
                    "title": "Wrong number in a published result",
                },
                {"number": 1, "createdAt": at, "title": "How to report a Wrong number"},
            ],
        }
        self.assertEqual(
            wrong_numbers(results, since),
            [
                {"kind": "wrong-number", "number": 13127, "at": at},
            ],
        )
        self.assertIsNone(wrong_numbers({**results, "issueCount": 3}, since))

    def test_missing_injury_reports_keep_deployment_history(self):
        at = "2026-11-19T22:00:00Z"
        history = {
            "pageInfo": {"hasNextPage": False},
            "nodes": [{
                "oid": "merged",
                "committedDate": at,
                "statusCheckRollup": {"contexts": {"nodes": [{
                    "context": "Vercel", "state": "SUCCESS", "createdAt": at,
                }]}},
            }],
        }
        api = Mock()
        api.request.return_value = {
            "data": {
                "reports": None,
                "repository": {"defaultBranchRef": {"target": {"history": history}}},
            },
            "errors": [{"path": ["reports"]}],
        }
        with patch("collect.git", return_value="merged"):
            receipts, _, _, reports = history_signals(api, instant(at), at)
        self.assertEqual([receipt["line"] for receipt in receipts], ["Website"])
        self.assertIsNone(reports)
        api.request.assert_called_once()

    def test_clipboard_keeps_only_observed_bench_times(self):
        before = "2026-11-19T22:00:00Z"
        now = "2026-11-19T22:05:00Z"
        bench = {"number": 13069, "line": "Website", "station": "Write"}
        observed = {"generated_at": before, "changes": [bench]}
        floor = {
            "generated_at": now,
            "changes": [
                {**bench, "station": "Live"},
                {**bench, "line": "Apps", "station": "Live"},
            ],
        }
        add_signs(floor, {}, observed)
        self.assertEqual(floor["changes"][0]["bench_seen_at"], before)
        self.assertNotIn("bench_seen_at", floor["changes"][1])
