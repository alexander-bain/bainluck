"""The tournament register drift sentinel (UX-P134).

The register is what makes `/tournaments/us-open` immune to the
`llm_sport_category` contamination, and it is a COMMITTED file — so the two
questions these tests exist to answer are "does it notice drift" and, more
importantly, "can it ever report clean without having looked".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.tournament_register_sentinel import (
    WATCHED,
    _terminal,
    build_candidates,
    build_drift_issue_body,
    drift_fingerprint,
    register_age_hours,
)
from app.utils.tournament_register import (
    classify,
    diff_against_inventory,
    load_register,
)


def _register():
    register = load_register("us-open", "2026")
    assert register is not None, "the committed US Open register must be readable"
    return register


def _candidates_matching(register):
    """The inventory a perfectly-undrifted source would return.

    Built through `priced_source_blocks`, the same walk the comparator uses, so
    this helper cannot fall behind the register's collections. It did once:
    UX-P139 added 336 reach identities and a players-only helper made an
    undrifted register report `REGISTERED_IDENTITY_NOT_OBSERVED` 336 times.
    """
    from app.utils.tournament_register import priced_source_blocks

    return [
        {
            "source": block["source"],
            "market_id": block["market_id"],
            "outcome_id": block["outcome_id"],
            "outcome_name": block.get("source_name"),
            "status": "live",
            "terminal_result": None,
            "season": register["season"],
        }
        for block in priced_source_blocks(register)
        if block.get("status") != "missing"
    ]


class TestItActuallyLooked:
    """The false-green class. A sentinel that reports clean having compared
    nothing is worse than no sentinel, because it is trusted."""

    def test_no_tournaments_compared_is_no_work_never_complete(self):
        assert _terminal({"tournaments": 0, "errors": []}) == "no_work"

    def test_every_tournament_erroring_is_failed_not_a_long_error_list(self):
        assert _terminal({"tournaments": 0, "errors": [{"e": "boom"}]}) == "failed"

    def test_a_comparison_that_happened_is_complete(self):
        assert _terminal({"tournaments": 1, "errors": []}) == "complete"

    def test_some_errors_is_partial_so_coverage_is_never_implied(self):
        assert _terminal({"tournaments": 1, "errors": [{"e": "boom"}]}) == "partial"

    def test_the_sentinel_is_enrolled_so_its_terminal_is_authoritative(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert "tournament_register_sentinel" in ENFORCED_TASKS

    def test_the_us_open_register_is_actually_watched(self):
        """The whole point is that the LIVE page's register is guarded."""
        assert ("us-open", "2026") in WATCHED


class TestDriftDetection:
    def test_an_undrifted_register_is_clean(self):
        register = _register()
        findings = diff_against_inventory(register, _candidates_matching(register))
        assert findings == []
        assert classify(findings)["classification"] == "clean"

    def test_a_vanished_identity_is_caught(self):
        """The finding that matters most: the market backing a row is gone, and
        the page's only symptom would be a row that quietly stops rendering."""
        register = _register()
        candidates = _candidates_matching(register)[:-1]
        findings = diff_against_inventory(register, candidates)
        assert "REGISTERED_IDENTITY_NOT_OBSERVED" in findings

    def test_a_renamed_outcome_is_unambiguous_drift(self):
        register = _register()
        candidates = _candidates_matching(register)
        candidates[0]["outcome_name"] = "Somebody Else Entirely"
        findings = diff_against_inventory(register, candidates)
        assert "UNAMBIGUOUS_RENAME_DRIFT" in findings

    def test_two_markets_competing_for_one_row_is_ambiguous(self):
        register = _register()
        candidates = _candidates_matching(register)
        candidates.append(dict(candidates[0]))
        findings = diff_against_inventory(register, candidates)
        assert classify(findings)["action"] == "file_p2_needs_triage"

    def test_a_malformed_candidate_set_is_never_read_as_no_drift(self):
        """Gotcha #53 — an empty answer is a response shape, not an absence."""
        register = _register()
        assert diff_against_inventory(register, "not a list") == ["CANDIDATES_WRONG_SHAPE"]
        assert diff_against_inventory(register, [1, 2]) == ["POISON_CANDIDATE"]
        # Both route to a human and NEITHER can read as clean, which is the
        # property that matters. (They classify `needs_ruling`, not `invalid` —
        # the register itself is fine; it is the observation that is unusable.)
        for finding in ("POISON_CANDIDATE", "CANDIDATES_WRONG_SHAPE"):
            verdict = classify([finding])
            assert verdict["classification"] == "needs_ruling"
            assert verdict["action"] == "file_p2_needs_triage"
            assert verdict["publish"] is False


class TestFingerprintLifecycle:
    def test_the_fingerprint_survives_red_to_green(self):
        """The close is attempted exactly when the findings clear, so a
        finding-derived fingerprint would look for an issue that never existed
        and silently close nothing — the alert stays open forever while the
        sentinel reports it resolved."""
        red = drift_fingerprint("us-open", "2026")
        green = drift_fingerprint("us-open", "2026")
        assert red == green

    def test_different_tournaments_do_not_share_an_issue(self):
        assert drift_fingerprint("us-open", "2026") != drift_fingerprint("wimbledon", "2026")
        assert drift_fingerprint("us-open", "2026") != drift_fingerprint("us-open", "2027")


class TestIssueBody:
    def test_the_body_carries_the_findings_and_the_fingerprint(self):
        body = build_drift_issue_body({
            "tournament": "us-open",
            "season": "2026",
            "version": 3,
            "age_hours": 12.0,
            "registered_count": 211,
            "candidate_count": 209,
            "classification": "needs_ruling",
            "action": "file_p2_needs_triage",
            "findings": ["AMBIGUOUS_CANDIDATES", "AMBIGUOUS_CANDIDATES"],
            "fingerprint": "abc123",
        })
        assert "AMBIGUOUS_CANDIDATES" in body
        assert "abc123" in body
        assert "211" in body and "209" in body
        # Deduped, so a hundred instances of one code do not fill the issue.
        assert body.count("`AMBIGUOUS_CANDIDATES`") == 1
        # And it says plainly that nothing was republished.
        assert "never republishes" in body


class TestRegisterAge:
    def test_age_is_measured_from_generated_at(self):
        now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        register = {"generated_at": (now - timedelta(hours=5)).isoformat()}
        assert register_age_hours(register, now) == pytest.approx(5.0)

    def test_an_unreadable_timestamp_is_none_not_zero(self):
        """Zero would read as "generated just now", which is the opposite."""
        assert register_age_hours({"generated_at": "not a date"}) is None
        assert register_age_hours({}) is None


class TestTheObserverSeesEverythingTheComparatorChecks:
    """The hole plant 12 found, closed.

    `diff_against_inventory` reports `REGISTERED_IDENTITY_NOT_OBSERVED` for any
    pinned identity the candidate list does not contain. So if `build_candidates`
    looks at FEWER identities than the comparator checks, an undrifted register
    reports drift for every one it missed — a sentinel crying wolf about its own
    blind spot, and it would fire 336 times the day the grid shipped.

    The existing drift tests cannot catch that: they build candidates through the
    same helper the comparator uses, so the two move together. This asserts the
    OBSERVER's query directly, against the register rather than against the
    helper.
    """

    class _RecordingSession:
        """Captures the `IN (...)` id set and returns nothing."""

        def __init__(self):
            self.wanted: set = set()

        async def execute(self, statement):
            for parameter in statement.compile().params.values():
                if isinstance(parameter, (list, tuple, set)):
                    self.wanted.update(parameter)
            class _Empty:
                def all(self_inner):
                    return []
            return _Empty()

    async def test_build_candidates_asks_for_every_reach_identity(self):
        register = _register()
        session = self._RecordingSession()
        await build_candidates(session, register)

        pinned = {
            block["outcome_id"]
            for reach in register.get("reaches", [])
            for block in reach["sources"]
            if block.get("outcome_id") is not None
        }
        assert pinned, "the committed register carries no reach identities"
        missing = pinned - session.wanted
        assert not missing, f"{len(missing)} reach identities are unwatched"

    async def test_build_candidates_asks_for_every_player_identity(self):
        register = _register()
        session = self._RecordingSession()
        await build_candidates(session, register)

        pinned = {
            block["outcome_id"]
            for player in register["players"]
            for block in (player.get("sources") or [])
            if block.get("outcome_id") is not None
        }
        assert pinned
        assert not pinned - session.wanted



class TestFilingDedupsNightOverNight:
    """#9092: the body marker was an HTML comment the shared dedup parser cannot
    read, and no title_prefix was passed — so every red night filed a fresh copy
    (five open by 9/27) and the GREEN close could never find one. These run the
    sentinel's OWN filing call against the real `reconcile_issue`, GitHub faked."""

    FP = drift_fingerprint("us-open", "2026")
    LEGACY_TITLE = "Tournament register drift: us-open 2026 (needs_ruling)"
    LEGACY_BODY = (
        "**Tournament register drift — us-open 2026**\n\n- `SETTLEMENT_WITHOUT_RESULT`\n\n"
        f"<!-- sentinel-fingerprint: tournament_register_sentinel:{drift_fingerprint('us-open', '2026')} -->"
    )

    def _red(self):
        return {
            "tournament": "us-open", "season": "2026", "status": "ok", "version": 12,
            "age_hours": 751.4, "registered_count": 378, "candidate_count": 454,
            "findings": ["SETTLEMENT_WITHOUT_RESULT"], "classification": "needs_ruling",
            "action": "file_p2_needs_triage", "publish": False, "fingerprint": self.FP,
        }

    def _green(self):
        return {
            "tournament": "us-open", "season": "2026", "status": "ok", "version": 13,
            "registered_count": 378, "candidate_count": 378, "findings": [],
            "classification": "clean", "action": "none", "publish": False,
        }

    def _night(self, monkeypatch, result, open_issues):
        """One sentinel run; returns every GitHub call it made."""
        import asyncio

        from app.services import database
        from app.tasks import bug_report_github as gh
        from app.tasks import sentinel_filing
        from app.tasks import tournament_register_sentinel as sentinel

        calls: list[tuple] = []

        class _Session:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *exc):
                return False

        async def fake_run(session, tournament, season, *, directory):
            return dict(result)

        monkeypatch.setattr(database, "async_session_maker", lambda: _Session())
        monkeypatch.setattr(sentinel, "_run_tournament", fake_run)
        monkeypatch.setattr(sentinel_filing, "fetch_open_alert_issues", lambda: open_issues)
        monkeypatch.setattr(sentinel_filing, "_claim_fingerprint", lambda *a: "no_redis")
        monkeypatch.setattr(gh, "GITHUB_TOKEN", "tok")
        monkeypatch.setattr(gh, "create_github_issue", lambda t, b, labels: calls.append(("create", t, b)) or (9999, "N"))
        monkeypatch.setattr(gh, "add_to_project_board", lambda nid: None)
        monkeypatch.setattr(gh, "comment_on_issue", lambda n, b: calls.append(("comment", n)))
        monkeypatch.setattr(gh, "update_issue_body", lambda n, b: calls.append(("body", n, b)))
        monkeypatch.setattr(gh, "close_issue", lambda n, comment=None: calls.append(("close", n)))
        stats = asyncio.run(sentinel._run_tournament_register_sentinel())
        assert not stats["errors"], stats["errors"]
        return calls

    def test_the_body_declares_a_fingerprint_the_shared_parser_reads(self):
        from app.tasks.sentinel_filing import declared_fingerprints
        from app.tasks.tournament_register_sentinel import MARKER_KEY

        body = build_drift_issue_body(self._red())
        # The pair the sentinel dedups and closes on is exactly what the one
        # shared parser recovers from its own body — not merely a substring.
        assert declared_fingerprints(body) == {(MARKER_KEY, self.FP)}

    def test_a_second_red_night_comments_instead_of_filing(self, monkeypatch):
        from app.tasks.sentinel_filing import OpenIssuesResult

        first = self._night(monkeypatch, self._red(), OpenIssuesResult(ok=True, issues=[]))
        created = [c for c in first if c[0] == "create"]
        assert len(created) == 1
        _, title, body = created[0]

        second = self._night(
            monkeypatch, self._red(),
            OpenIssuesResult(ok=True, issues=[{"number": 9999, "title": title, "body": body}]),
        )
        assert not [c for c in second if c[0] == "create"]
        assert ("comment", 9999) in second

    def test_green_closes_what_red_filed(self, monkeypatch):
        from app.tasks.sentinel_filing import OpenIssuesResult

        body = build_drift_issue_body(self._red())
        calls = self._night(
            monkeypatch, self._green(),
            OpenIssuesResult(ok=True, issues=[{"number": 9999, "title": "renamed by a human", "body": body}]),
        )
        assert calls == [("close", 9999)]

    def test_the_pre_fix_copies_fold_onto_the_oldest_and_it_becomes_closable(self, monkeypatch):
        from app.tasks.sentinel_filing import OpenIssuesResult

        legacy = [
            {"number": n, "title": self.LEGACY_TITLE, "body": self.LEGACY_BODY}
            for n in (9092, 8806, 8195, 8570, 8374)
        ]
        calls = self._night(monkeypatch, self._red(), OpenIssuesResult(ok=True, issues=legacy))
        assert not [c for c in calls if c[0] == "create"]
        assert ("comment", 8195) in calls
        refreshed = [c for c in calls if c[0] == "body"]
        assert [c[1] for c in refreshed] == [8195]

        # The refreshed body now carries the declaration, so GREEN finds it.
        green = self._night(
            monkeypatch, self._green(),
            OpenIssuesResult(ok=True, issues=[{"number": 8195, "title": self.LEGACY_TITLE, "body": refreshed[0][2]}]),
        )
        assert green == [("close", 8195)]

    def test_another_tournaments_issue_is_not_a_match(self, monkeypatch):
        from app.tasks.sentinel_filing import OpenIssuesResult

        other = {
            "number": 7000,
            "title": "Tournament register drift: us-open 2027 (needs_ruling)",
            "body": build_drift_issue_body({**self._red(), "season": "2027",
                                            "fingerprint": drift_fingerprint("us-open", "2027")}),
        }
        calls = self._night(monkeypatch, self._red(), OpenIssuesResult(ok=True, issues=[other]))
        assert [c[0] for c in calls] == ["create"]

    def test_a_failed_open_issue_read_files_nothing(self, monkeypatch):
        from app.tasks.sentinel_filing import OpenIssuesResult

        calls = self._night(
            monkeypatch, self._red(),
            OpenIssuesResult(ok=False, issues=[], error="rate limited"),
        )
        assert calls == []
