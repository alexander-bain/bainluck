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
    """The inventory a perfectly-undrifted source would return."""
    rows = []
    for player in register["players"]:
        for block in player.get("sources") or []:
            if block.get("status") == "missing":
                continue
            rows.append({
                "source": block["source"],
                "market_id": block["market_id"],
                "outcome_id": block["outcome_id"],
                "outcome_name": block["source_name"],
                "status": "live",
                "terminal_result": None,
                "season": register["season"],
            })
    return rows


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
