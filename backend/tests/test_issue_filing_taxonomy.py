"""Q434 — every issue-filing rail emits a ``priority:*``, and these tests pin it.

Two layers, because either alone would have missed the defect that motivated this:

  * **the mapping** — ``app.utils.issue_labels`` is pure, so the severity dialects and
    the family defaults are pinned directly;
  * **each rail's emitted label list** — the actual list the rail hands to
    ``create_github_issue`` / ``gh issue create``. The mapping being correct proved
    nothing about ``scripts/alert_intake.py``, which never consulted it and filed 78
    all-time CI-failure issues with no priority at all.

The rail-level tests deliberately assert on the LIST, not on a mocked HTTP call, so
they stay true when a rail's transport changes. Where a rail's list lives outside
Python (the browser-audit sweep filer is a Node script), the test reads the file — a
cross-language rail is exactly the one nobody remembers to check.
"""

import importlib.util
import pathlib
import re
import sys

import pytest

from app.utils.issue_labels import (
    DEFAULT_PRIORITY,
    FAMILY_DEFAULT_PRIORITY,
    PRIORITY_LABELS,
    SEVERITY_TO_PRIORITY,
    ensure_taxonomy,
    normalize_severity,
    priority_label,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _priority_of(labels) -> list[str]:
    return [name for name in labels if name.startswith("priority:")]


def _load_standalone(name: str, path: pathlib.Path):
    """Import a standalone script (not an importable package module) for testing.

    The ``sys.modules`` registration before ``exec_module`` is load-bearing, not
    ceremony: both scripts use ``from __future__ import annotations`` plus
    ``@dataclass``, and ``dataclasses._is_type`` resolves a field's stringized
    annotation via ``sys.modules[cls.__module__].__dict__``. Without the entry that
    lookup returns ``None`` and the import dies with a bare
    ``AttributeError: 'NoneType' object has no attribute '__dict__'``.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# The mapping
# ---------------------------------------------------------------------------


class TestPriorityMapping:
    def test_every_mapped_severity_lands_on_a_real_priority_label(self):
        for severity, label in SEVERITY_TO_PRIORITY.items():
            assert (
                label in PRIORITY_LABELS
            ), f"{severity} → {label} is not a priority label"

    def test_every_family_default_is_a_real_priority_label(self):
        for family, label in FAMILY_DEFAULT_PRIORITY.items():
            assert (
                label in PRIORITY_LABELS
            ), f"{family} → {label} is not a priority label"

    @pytest.mark.parametrize(
        "severity,expected",
        [
            ("P0", "priority:p0"),
            ("p1", "priority:p1"),
            ("  Error ", "priority:p1"),
            ("priority:p3", "priority:p3"),
            ("fatal", "priority:p0"),
            ("warning", "priority:p2"),
            ("info", "priority:p3"),
            (2, "priority:p2"),
        ],
    )
    def test_dialects_resolve(self, severity, expected):
        assert priority_label(severity) == expected

    @pytest.mark.parametrize("severity", [None, "", "  ", "banana", "sev9", object()])
    def test_unknown_severity_never_returns_none_and_never_raises(self, severity):
        """THE invariant. Every ``if priority:`` guard in this codebase was a place an
        issue could be born unprioritized; there is no falsy branch to guard."""
        assert priority_label(severity) == DEFAULT_PRIORITY

    def test_the_ratified_default_is_p2(self):
        """Alex 2026-07-27 (handoff README, Process v3 §5 / Queue #279): auto-filed
        issues are born at P2 — priority is earned at triage, not stamped at birth."""
        assert DEFAULT_PRIORITY == "priority:p2"

    def test_board_taxonomy_family_defaults(self):
        """BOARD-TAXONOMY.md, verbatim: "Family defaults: parked -> p3,
        Browser-audit -> p3"."""
        assert priority_label(family="browser-audit") == "priority:p3"
        assert priority_label(family="parked") == "priority:p3"

    def test_a_measured_severity_beats_the_family_default(self):
        assert priority_label("p0", family="browser-audit") == "priority:p0"

    def test_unknown_family_falls_through_to_the_default(self):
        assert priority_label(family="not-a-family") == DEFAULT_PRIORITY

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("P1", "p1"),
            ("priority:p2", "p2"),
            (" ERROR ", "error"),
            (3, "p3"),
            (None, ""),
        ],
    )
    def test_normalize_severity(self, raw, expected):
        assert normalize_severity(raw) == expected


class TestEnsureTaxonomy:
    def test_adds_a_priority_when_absent(self):
        assert "priority:p2" in ensure_taxonomy(["alert-intake"])

    def test_never_overrides_an_existing_priority(self):
        """A human's P0 must survive a later default-P2 pass. The shared rail already
        refuses to edit an existing issue's labels for this reason; normalizing at
        filing time must not reintroduce the downgrade from the other end."""
        out = ensure_taxonomy(["priority:p0", "alert-intake"], severity="p3")
        assert _priority_of(out) == ["priority:p0"]

    def test_is_idempotent(self):
        once = ensure_taxonomy(["alert-intake"], area="area:infra", type_="type:bug")
        assert ensure_taxonomy(once, area="area:frontend", type_="type:ops") == once

    def test_preserves_order_and_drops_duplicates(self):
        out = ensure_taxonomy(["b", "a", "b", "priority:p1"])
        assert out == ["b", "a", "priority:p1"]

    def test_area_and_type_are_optional_but_priority_is_not(self):
        out = ensure_taxonomy([])
        assert out == [DEFAULT_PRIORITY]

    def test_bare_area_and_type_get_their_prefixes(self):
        out = ensure_taxonomy([], area="infra", type_="ops")
        assert "area:infra" in out and "type:ops" in out

    def test_none_input_is_tolerated(self):
        assert ensure_taxonomy(None) == [DEFAULT_PRIORITY]


# ---------------------------------------------------------------------------
# Per-rail: the labels each rail actually emits
# ---------------------------------------------------------------------------


class TestSharedSentinelRail:
    """``sentinel_filing.filing_labels`` is what every sentinel's create goes through."""

    def test_default_labels_carry_a_priority(self):
        from app.tasks.sentinel_filing import DEFAULT_LABELS

        assert _priority_of(DEFAULT_LABELS) == ["priority:p2"]

    def test_a_caller_that_forgets_a_priority_still_gets_one(self):
        """The regression this closes: ``DEFAULT_LABELS`` only applied when a caller
        passed NO labels, and every sentinel passes its own, so the P2 default
        protected nobody."""
        from app.tasks.sentinel_filing import filing_labels

        assert _priority_of(filing_labels(["alert-intake", "area:infra"])) == [
            "priority:p2"
        ]

    def test_a_callers_own_priority_wins(self):
        from app.tasks.sentinel_filing import filing_labels

        assert _priority_of(filing_labels(["alert-intake", "priority:p0"])) == [
            "priority:p0"
        ]

    def test_the_source_label_is_guaranteed(self):
        """The rail's dedup source is the open ``alert-intake`` list, so an issue filed
        without that label is invisible to its own sentinel on the next run and gets
        re-filed forever. Two sentinels were doing exactly this."""
        from app.tasks.sentinel_filing import filing_labels

        assert "alert-intake" in filing_labels(["area:data-quality", "priority:p2"])

    @pytest.mark.parametrize(
        "rail_labels",
        [
            # tournament_register_sentinel — no alert-intake, has a priority
            ["needs-triage", "area:data-quality", "priority:p2"],
            # precompute_calibration publish gate — same shape
            ["type:bug", "area:calibration", "priority:p2", "needs-triage"],
            # grid_register_sentinel — complete already
            ["alert-intake", "type:bug", "priority:p2", "needs-triage", "area:grids"],
        ],
    )
    def test_every_in_tree_caller_emits_a_complete_source_and_priority(
        self, rail_labels
    ):
        from app.tasks.sentinel_filing import filing_labels

        out = filing_labels(rail_labels)
        assert "alert-intake" in out
        assert len(_priority_of(out)) == 1


class TestBugReportRail:
    """The rage-shake rail (``bug_report_github.build_labels``)."""

    @pytest.mark.parametrize("severity", ["P0", "P1", "P2", "P3"])
    def test_every_computed_severity_yields_exactly_one_priority(self, severity):
        from app.tasks.bug_report_github import build_labels

        assert len(_priority_of(build_labels("ui", severity))) == 1

    def test_an_unexpected_severity_still_yields_a_priority(self):
        """``build_labels`` is public and the old ``if priority:`` guard produced an
        unprioritized issue, silently, for any severity outside P0-P3."""
        from app.tasks.bug_report_github import build_labels

        assert _priority_of(build_labels("ui", "URGENT")) == [DEFAULT_PRIORITY]

    @pytest.mark.parametrize(
        "category",
        [
            "ios",
            "ui",
            "data_quality",
            "performance",
            "feature_request",
            "other",
            None,
            "",
        ],
    )
    def test_priority_area_and_type_are_always_present(self, category):
        """`BOARD-TAXONOMY.md` invariant 1. This rail emitted NO ``type:*`` at all and
        no ``area:*`` for an unmapped category, so every such issue was born failing
        the lint."""
        from app.tasks.bug_report_github import build_labels

        labels = build_labels(category, "P2")
        assert len(_priority_of(labels)) == 1
        assert any(name.startswith("area:") for name in labels), labels
        assert any(name.startswith("type:") for name in labels), labels

    def test_a_feature_request_is_not_typed_as_a_bug(self):
        from app.tasks.bug_report_github import build_labels

        assert "type:feature" in build_labels("feature_request", "P2")
        assert "type:bug" not in build_labels("feature_request", "P2")

    def test_reporter_provenance_survives(self):
        from app.tasks.bug_report_github import build_labels

        assert "reporter:owner" in build_labels("ui", "P1", is_owner=True)
        assert "reporter:external" in build_labels("ui", "P1", is_owner=False)

    def test_every_compute_severity_output_is_mapped(self):
        for desc in ["data loss here", "it crashed", "typo in the header", "hmm"]:
            assert len(_priority_of(build_labels_for(desc))) == 1


def build_labels_for(description: str) -> list[str]:
    from app.tasks.bug_report_github import build_labels, compute_severity

    return build_labels("ui", compute_severity(description))


class TestCreateIssueChokepoint:
    """Every backend rail funnels through ``create_github_issue``; the floor is there."""

    def test_a_labelless_create_still_posts_a_priority(self, monkeypatch):
        import app.tasks.bug_report_github as gh

        captured = {}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"number": 1, "node_id": "N"}

        def _post(url, headers=None, json=None, timeout=None):
            captured["labels"] = json["labels"]
            return _Resp()

        monkeypatch.setattr(gh.httpx, "post", _post)
        gh.create_github_issue("t", "b", ["alert-intake"])
        assert _priority_of(captured["labels"]) == [DEFAULT_PRIORITY]

    def test_the_chokepoint_does_not_override_a_supplied_priority(self, monkeypatch):
        import app.tasks.bug_report_github as gh

        captured = {}

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"number": 1, "node_id": "N"}

        monkeypatch.setattr(
            gh.httpx,
            "post",
            lambda url, headers=None, json=None, timeout=None: (
                captured.update(labels=json["labels"]) or _Resp()
            ),
        )
        gh.create_github_issue("t", "b", ["alert-intake", "priority:p0"])
        assert _priority_of(captured["labels"]) == ["priority:p0"]


class TestAlertIntakeRail:
    """``scripts/alert_intake.py`` — Sentry + GitHub Actions. 78 all-time CI-failure
    issues were filed by this rail with no priority label."""

    @staticmethod
    def _module():
        return _load_standalone(
            "q434_alert_intake", REPO_ROOT / "scripts" / "alert_intake.py"
        )

    def test_github_actions_labels_carry_priority_area_and_type(self):
        labels = self._module().GITHUB_ACTIONS_LABELS
        assert len(_priority_of(labels)) == 1
        assert "area:infra" in labels and "type:ops" in labels
        # The source labels are hardcoded by BOARD-TAXONOMY contract — do not rename.
        assert {"alert-intake", "ci-failure", "github-actions"} <= set(labels)

    @pytest.mark.parametrize(
        "level,expected",
        [
            ("error", "priority:p2"),
            ("warning", "priority:p2"),
            ("info", "priority:p2"),
            (None, "priority:p2"),
            ("fatal", "priority:p1"),
        ],
    )
    def test_sentry_level_mapping(self, level, expected):
        """Sentry's DEFAULT level is ``error``. Reading it as P1 would stamp P1 on
        essentially every production alert and manufacture exactly the template-P1
        noise the Board Sentinel caps at a 35% share. Only an explicit ``fatal``
        escalates."""
        labels = self._module().sentry_labels_for(level)
        assert _priority_of(labels) == [expected]

    def test_sentry_labels_carry_area_and_type(self):
        labels = self._module().sentry_labels_for("error")
        assert "area:backend" in labels and "type:bug" in labels

    def test_alert_intake_fallback_matches_canonical_default(self):
        """The script loads the canonical module by path and falls back to a local
        constant if that ever fails — filing one tier off beats losing a production
        alert. The two must not drift."""
        assert self._module()._FALLBACK_PRIORITY == DEFAULT_PRIORITY

    def test_the_canonical_module_actually_loaded(self):
        """If the path load silently broke, every assertion above would still pass on
        the fallback. Pin that the real module is in use."""
        assert self._module()._ISSUE_LABELS is not None


class TestBrowserAuditRail:
    """The sweep filer is Node, so its label list is read from source. #2249 and
    #2250 (2026-08-28) were both filed unprioritized by this rail."""

    HELPER = REPO_ROOT / "frontend" / "e2e" / "helpers" / "sweepFiling.js"
    SCRIPT = REPO_ROOT / "frontend" / "e2e" / "scripts" / "file-sweep-findings.js"

    def _filing_labels(self) -> list[str]:
        source = self.HELPER.read_text()
        match = re.search(r"const FILING_LABELS = \[(.*?)\];", source, re.S)
        assert match, "FILING_LABELS not found in sweepFiling.js"
        return re.findall(r'"([^"]+)"', match.group(1))

    def test_browser_audit_files_at_the_family_default(self):
        assert "priority:p3" in self._filing_labels()

    def test_exactly_one_priority(self):
        assert len(_priority_of(self._filing_labels())) == 1

    def test_area_type_and_source_labels_survive(self):
        assert {"type:bug", "area:frontend", "alert-intake", "program:ux"} <= set(
            self._filing_labels()
        )

    def test_the_script_consumes_the_shared_constant(self):
        """The list moved into the pure, contract-tested helper precisely so it stops
        being a literal in the side-effecting shell no test loads."""
        source = self.SCRIPT.read_text()
        assert "FILING_LABELS" in source
        assert not re.search(
            r"const LABELS = \[", source
        ), "file-sweep-findings.js re-declared its own LABELS literal"


class TestFeatureRequestDigestRail:
    def test_the_digest_labels_carry_priority_and_area(self):
        """The weekly external feature-request roll-up filed with
        ``["alert-intake","type:feature","reporter:external"]`` — no priority, no
        area. Pinned by source read because the labels are built inside an async
        Celery task body."""
        source = (REPO_ROOT / "backend" / "app" / "tasks" / "__init__.py").read_text()
        match = re.search(
            r"issue_number, _ = create_github_issue\((.*?)\n\s*\)\n", source, re.S
        )
        assert match, "the digest create_github_issue call moved — re-pin this test"
        call = match.group(1)
        assert 'priority_label(family="digest")' in call
        assert '"area:frontend"' in call
        assert '"type:feature"' in call

    def test_the_digest_family_default_is_p3(self):
        assert priority_label(family="digest") == "priority:p3"


class TestCockpitFileIssueRail:
    """``POST /api/admin/file-issue`` — its ``if prio:`` guard meant a blank or
    unknown severity filed with no priority at all."""

    def test_known_cockpit_dialect_is_unchanged(self):
        from app.routes.admin_file_issue import _SEVERITY_TO_PRIORITY

        assert _SEVERITY_TO_PRIORITY["critical"] == "priority:p1"
        assert _SEVERITY_TO_PRIORITY["warning"] == "priority:p2"

    def test_the_cockpit_dialect_deliberately_diverges_from_canonical(self):
        """``critical`` is P0 canonically (a Sentry ``fatal``-class word) but P1 here,
        where it is an LLM's adjective about a cockpit tile. Promoting it to "drop
        everything" is an escalation nobody asked for, so the divergence is pinned
        rather than left to look like an oversight."""
        from app.routes.admin_file_issue import _SEVERITY_TO_PRIORITY

        assert _SEVERITY_TO_PRIORITY["critical"] != priority_label("critical")

    @pytest.mark.parametrize("severity", [None, "", "   ", "unmapped-word"])
    def test_an_unknown_severity_falls_through_to_the_default(self, severity):
        from app.routes.admin_file_issue import _SEVERITY_TO_PRIORITY

        resolved = _SEVERITY_TO_PRIORITY.get(
            (severity or "").strip().lower()
        ) or priority_label(severity)
        assert resolved == DEFAULT_PRIORITY


class TestBoardSentinelGuard:
    """The check that catches this class if a rail ever regresses."""

    def test_flags_an_issue_with_no_priority(self):
        from app.tasks.board_sentinel import check_missing_priority_label

        found = check_missing_priority_label(
            [{"number": 1, "title": "x", "labels": ["alert-intake", "area:infra"]}]
        )
        assert len(found) == 1
        assert found[0]["check"] == "missing_priority_label"

    def test_names_a_rail_regression_distinctly(self):
        from app.tasks.board_sentinel import check_missing_priority_label

        rail = check_missing_priority_label(
            [{"number": 1, "title": "x", "labels": ["alert-intake"]}]
        )[0]
        human = check_missing_priority_label(
            [{"number": 2, "title": "x", "labels": ["area:infra"]}]
        )[0]
        assert "rail" in rail["detail"]
        assert "triage" in human["detail"]

    def test_clean_issue_is_not_flagged(self):
        from app.tasks.board_sentinel import check_missing_priority_label

        assert (
            check_missing_priority_label(
                [{"number": 1, "title": "x", "labels": ["alert-intake", "priority:p2"]}]
            )
            == []
        )

    def test_taxonomy_exempt_is_skipped(self):
        from app.tasks.board_sentinel import check_missing_priority_label

        assert (
            check_missing_priority_label(
                [{"number": 1, "title": "x", "labels": ["taxonomy-exempt"]}]
            )
            == []
        )

    def test_the_check_is_wired_into_the_run(self):
        """A pure check nobody calls is a check that never fires."""
        source = (
            REPO_ROOT / "backend" / "app" / "tasks" / "board_sentinel.py"
        ).read_text()
        assert "real += check_missing_priority_label(issues)" in source


class TestBackfillScript:
    """The one-shot backward half. Pure planning is tested; nothing here touches the
    network."""

    @staticmethod
    def _module():
        return _load_standalone(
            "q434_backfill",
            REPO_ROOT / "backend" / "scripts" / "backfill_rail_issue_priorities.py",
        )

    def test_rail_filed_issue_is_actionable(self):
        m = self._module()
        actionable, skipped = m.plan(
            [{"number": 1, "title": "t", "labels": [{"name": "alert-intake"}]}]
        )
        assert [r["number"] for r in actionable] == [1]
        assert skipped == []
        assert actionable[0]["priority"] == "priority:p2"

    def test_human_filed_issue_is_skipped_not_stamped(self):
        """Stamping P2 on a human-filed card converts "un-triaged" into "triaged as
        P2", which is worse than the lint violation it fixes."""
        m = self._module()
        actionable, skipped = m.plan(
            [{"number": 2, "title": "t", "labels": [{"name": "area:infra"}]}]
        )
        assert actionable == []
        assert [r["number"] for r in skipped] == [2]

    def test_browser_audit_backfills_to_p3(self):
        m = self._module()
        actionable, _ = m.plan(
            [
                {
                    "number": 3,
                    "title": "Browser audit: console.no_errors on tournament.hub",
                    "labels": [{"name": "alert-intake"}, {"name": "program:ux"}],
                }
            ]
        )
        assert actionable[0]["priority"] == "priority:p3"

    def test_browser_audit_detected_by_body_marker_too(self):
        m = self._module()
        actionable, _ = m.plan(
            [
                {
                    "number": 4,
                    "title": "something else entirely",
                    "body": "`browser-sweep-fingerprint:abc` (dedupe key — do not edit)",
                    "labels": [{"name": "alert-intake"}, {"name": "program:ux"}],
                }
            ]
        )
        assert actionable[0]["priority"] == "priority:p3"

    def test_already_prioritized_and_exempt_issues_are_untouched(self):
        m = self._module()
        actionable, skipped = m.plan(
            [
                {
                    "number": 5,
                    "title": "t",
                    "labels": [{"name": "alert-intake"}, {"name": "priority:p1"}],
                },
                {"number": 6, "title": "t", "labels": [{"name": "taxonomy-exempt"}]},
            ]
        )
        assert actionable == [] and skipped == []

    def test_the_measured_four(self):
        """The exact rail-filed population on 2026-08-28, as a fixture: #992
        (ci-failure), #1459 (alert-intake), #2249/#2250 (browser-audit)."""
        m = self._module()
        actionable, _ = m.plan(
            [
                {
                    "number": 992,
                    "title": "[Alert] CI failed: de-poison the curve",
                    "labels": [
                        {"name": "alert-intake"},
                        {"name": "ci-failure"},
                        {"name": "github-actions"},
                        {"name": "area:calibration"},
                    ],
                },
                {
                    "number": 1459,
                    "title": "/api/feed cold-compute tail ~9-13s",
                    "labels": [
                        {"name": "alert-intake"},
                        {"name": "area:infra"},
                        {"name": "type:perf"},
                    ],
                },
                {
                    "number": 2249,
                    "title": "Browser audit: console.no_errors on tournament.hub",
                    "labels": [{"name": "alert-intake"}, {"name": "program:ux"}],
                },
                {
                    "number": 2250,
                    "title": "Browser audit: network.no_unexpected_failures on tournament.hub",
                    "labels": [{"name": "alert-intake"}, {"name": "program:ux"}],
                },
            ]
        )
        assert {r["number"]: r["priority"] for r in actionable} == {
            992: "priority:p2",
            1459: "priority:p2",
            2249: "priority:p3",
            2250: "priority:p3",
        }

    def test_source_label_set_matches_board_taxonomy(self):
        m = self._module()
        assert {
            "alert-intake",
            "bug-report",
            "manus-digest",
            "ci-failure",
            "github-actions",
        } <= m.RAIL_SOURCE_LABELS

    def test_dry_run_is_the_default(self):
        """A backfill that writes by default is one typo away from a bulk board
        mutation. Asserted behaviourally, not by reading the argparse call out of the
        source — the first version of this test did that and black reflowing the call
        broke it, which is a test failing for a reason the code was not."""
        args = self._module().build_parser().parse_args([])
        assert args.apply is False
        assert args.limit == 0

    def test_apply_is_opt_in(self):
        assert self._module().build_parser().parse_args(["--apply"]).apply is True


class TestNoRailBypassesTheTaxonomy:
    """A census, so a NEW rail added later cannot quietly reintroduce the defect.

    Any module calling ``create_github_issue`` inherits the chokepoint floor. Any
    module calling GitHub's issue-create endpoint DIRECTLY does not, and must be
    added here deliberately.
    """

    # An httpx.post whose URL is the bare `/issues` collection = an issue CREATE.
    # `/issues/{n}/comments` and the GET list of `/issues` are NOT creates, which is
    # why this matches the post call and its URL together rather than the path alone:
    # a looser check flags `sentinel_filing.py` and `board_sentinel.py`, whose only
    # sin is reading the open-issue list.
    _CREATE_CALL = re.compile(
        r"httpx\.post\(\s*f?\"https://api\.github\.com/repos/\{REPO\}/issues\"",
    )

    def test_only_the_chokepoint_creates_issues(self):
        offenders = []
        for path in sorted((REPO_ROOT / "backend" / "app").rglob("*.py")):
            if path.name == "bug_report_github.py":
                continue
            if self._CREATE_CALL.search(path.read_text()):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == [], (
            "these modules create issues outside the taxonomy chokepoint "
            f"(route them through create_github_issue): {offenders}"
        )

    def test_the_census_regex_actually_matches_the_chokepoint(self):
        """A census that matches nothing passes for the wrong reason. Prove the
        pattern finds the one call it is supposed to find."""
        chokepoint = (
            REPO_ROOT / "backend" / "app" / "tasks" / "bug_report_github.py"
        ).read_text()
        assert self._CREATE_CALL.search(chokepoint)
