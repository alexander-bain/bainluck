"""Offline behavior checks; never invokes GitHub or mutates a real board."""

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "claim_issue", Path(__file__).parents[1] / "claim_issue.py"
)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "number": 9669,
            "title": "Ship",
            "url": "https://example.test/9669",
            "state": "OPEN",
            "labels": ["area:infra", "needs-agent"],
            "fields": {"Status": "Ready"},
            "item_id": "item",
            "comments": [],
        }
        self.fields = {
            name: {"id": name, "name": name}
            for name in [
                "Status",
                "Delivery owner",
                "Next step",
                "User outcome",
                "Evidence checked",
                "Delivery stage",
                "Release target",
            ]
        }
        self.fields["Status"]["options"] = [
            {"name": s, "id": s} for s in c.STATUS_LABELS
        ]
        self.fields["Delivery stage"]["options"] = [{"name": "Review", "id": "Review"}]
        self.commands = []
        self.patches = [
            patch.object(
                c, "read_issue", side_effect=lambda n: copy.deepcopy(self.snapshot)
            ),
            patch.object(c, "_project_fields", return_value=("project", self.fields)),
            patch.object(c, "_run", side_effect=self.fake_run),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_run(self, args):
        self.commands.append(args)
        if args[1:3] == ["project", "item-edit"]:
            name = args[args.index("--field-id") + 1]
            flag = "--text" if "--text" in args else "--single-select-option-id"
            self.snapshot["fields"][name] = args[args.index(flag) + 1]
        elif args[1:3] == ["project", "item-add"]:
            self.snapshot["item_id"] = "new-item"
            self.snapshot["fields"]["Title"] = "Ship"
        elif args[1:3] == ["issue", "edit"]:
            labels = set(self.snapshot["labels"])
            for i, arg in enumerate(args):
                if arg == "--add-label":
                    labels.add(args[i + 1])
                elif arg == "--remove-label":
                    labels.discard(args[i + 1])
            self.snapshot["labels"] = sorted(labels)
        elif args[1:3] == ["issue", "comment"]:
            self.snapshot["comments"].append(args[-1])
        else:
            raise AssertionError(args)

    def update(self, status, **kwargs):
        return c.set_status(9669, status, **kwargs)

    def test_all_statuses_clear_obsolete_routing_and_preserve_product_labels(self):
        for status, desired in c.STATUS_LABELS.items():
            with self.subTest(status=status):
                self.snapshot["labels"] = ["area:infra", *c.ROUTING_LABELS]
                self.snapshot["fields"]["Delivery owner"] = "Discover"
                self.update(status, owner="Discover")
                self.assertEqual(set(self.snapshot["labels"]), {"area:infra"} | desired)

    def test_claim_records_owner_and_delivery_details(self):
        self.update(
            "In Progress",
            owner="Discover",
            stage="Review",
            next_step="Review card",
            outcome="Interesting cards",
            evidence="52 tests",
        )
        self.assertEqual(self.snapshot["fields"]["Delivery owner"], "Discover")
        self.assertEqual(self.snapshot["fields"]["Next step"], "Review card")
        self.assertEqual(len(self.snapshot["comments"]), 1)

    def test_identical_retry_writes_nothing_and_does_not_repeat_comment(self):
        self.update("In Progress", owner="Discover")
        self.commands.clear()
        self.update("In Progress", owner="Discover")
        self.assertEqual(self.commands, [])

    def test_explicit_comment_retry_is_idempotent(self):
        self.update("Ready", comment="Next step confirmed")
        self.commands.clear()
        self.update("Ready", comment="Next step confirmed")
        self.assertEqual(self.commands, [])

    def test_other_owner_refused_before_mutation(self):
        self.snapshot["fields"]["Delivery owner"] = "Native"
        with self.assertRaisesRegex(RuntimeError, "Owned by"):
            self.update("In Progress", owner="Discover")
        self.assertEqual(self.commands, [])

    def test_ownerless_transition_cannot_overwrite_owned_issue(self):
        self.snapshot["fields"]["Delivery owner"] = "Native"
        with self.assertRaisesRegex(RuntimeError, "Owned by"):
            self.update("Done")
        self.assertEqual(self.commands, [])

    def test_legacy_claim_is_protected(self):
        self.snapshot["fields"]["Status"] = "In Progress"
        self.snapshot["comments"] = [
            "Active owner/context: Native. Marked In Progress as a collision-avoidance lock"
        ]
        with self.assertRaisesRegex(RuntimeError, "Owned by"):
            self.update("In Progress", owner="Discover")
        self.assertEqual(self.commands, [])

    def test_coordinated_owner_handoff_with_exact_expectation(self):
        self.snapshot["fields"]["Delivery owner"] = "Native"
        self.update("In Progress", owner="Discover", expected_owner="Native")
        self.assertEqual(self.snapshot["fields"]["Delivery owner"], "Discover")

    def test_stale_handoff_expectation_fails(self):
        self.snapshot["fields"]["Delivery owner"] = "Authority"
        with self.assertRaisesRegex(RuntimeError, "Owner changed"):
            self.update("In Progress", owner="Discover", expected_owner="Native")
        self.assertEqual(self.commands, [])

    def test_metadata_prevalidated_before_status_write(self):
        with self.assertRaisesRegex(RuntimeError, "Unknown Delivery stage"):
            self.update("Blocked", stage="Invented")
        self.assertEqual(self.commands, [])

    def test_drift_before_write_stops(self):
        initial = copy.deepcopy(self.snapshot)
        changed = copy.deepcopy(initial)
        changed["fields"]["Delivery owner"] = "Native"
        with patch.object(c, "read_issue", side_effect=[initial, changed]):
            with self.assertRaisesRegex(RuntimeError, "Concurrent"):
                self.update("In Progress", owner="Discover")
        self.assertEqual(self.commands, [])

    def test_partial_api_failure_never_reports_success(self):
        original = self.fake_run

        def fail(args):
            if args[1:3] == ["issue", "edit"]:
                raise RuntimeError("rate limit")
            original(args)

        with patch.object(c, "_run", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "rate limit"):
                self.update("Blocked")
        self.assertEqual(self.snapshot["fields"]["Status"], "Blocked")
        self.assertEqual(self.snapshot["labels"], ["area:infra", "needs-agent"])
        self.update("Blocked")
        self.assertIn("blocked", self.snapshot["labels"])

    def test_write_not_reflected_in_readback_fails(self):
        with patch.object(c, "_run", return_value=""):
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                self.update("Blocked")

    def test_partial_claim_retains_owner_for_safe_retry(self):
        original = self.fake_run

        def fail_status(args):
            if "--field-id" in args and args[args.index("--field-id") + 1] == "Status":
                raise RuntimeError("transient failure")
            original(args)

        with patch.object(c, "_run", side_effect=fail_status):
            with self.assertRaisesRegex(RuntimeError, "transient failure"):
                self.update("In Progress", owner="Discover")
        self.assertEqual(self.snapshot["fields"]["Delivery owner"], "Discover")
        self.assertEqual(self.snapshot["fields"]["Status"], "Ready")
        self.update("In Progress", owner="Discover")
        self.assertEqual(self.snapshot["fields"]["Status"], "In Progress")

    def test_other_owner_claim_during_write_is_detected(self):
        original = self.fake_run

        def concurrent(args):
            original(args)
            self.snapshot["comments"].append("Another worker claimed")

        with patch.object(c, "_run", side_effect=concurrent):
            with self.assertRaisesRegex(RuntimeError, "readback mismatch"):
                self.update("Blocked")
        self.assertEqual(len(self.commands), 1)

    def test_missing_card_added_then_read_back(self):
        self.snapshot["item_id"] = None
        self.update("Ready")
        self.assertEqual(self.snapshot["item_id"], "new-item")

    def test_unknown_active_owner_fails_closed(self):
        self.snapshot["fields"]["Status"] = "In Progress"
        with self.assertRaisesRegex(RuntimeError, "no readable owner"):
            self.update("Ready", owner="Discover")
        self.assertEqual(self.commands, [])


class ReadTests(unittest.TestCase):
    def test_truncated_or_missing_connections_fail(self):
        for value in [
            None,
            {},
            {"nodes": []},
            {"nodes": [], "pageInfo": {"hasNextPage": True}},
        ]:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                c._complete(value, "fields")
        self.assertEqual(
            c._complete({"nodes": [], "pageInfo": {"hasNextPage": False}}, "fields"), []
        )

    def test_graphql_errors_not_success(self):
        with patch.object(
            c,
            "_json",
            return_value={"data": {"user": None}, "errors": [{"message": "denied"}]},
        ):
            with self.assertRaisesRegex(RuntimeError, "GraphQL read failed"):
                c._graphql("query{}")


if __name__ == "__main__":
    unittest.main()
