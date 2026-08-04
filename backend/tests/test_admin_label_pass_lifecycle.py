"""#1542 — route-level lifecycle safety for the Label Pass admin endpoints.

Exercises the pure partition/verdict helpers in ``routes.admin_label_pass`` with
duck-typed fakes (no DB), pinning every named case from the queue: valid,
resolved, past-resolution, missing, superseded, unmatched email, poison
isolation, GET-valid/POST-stale, duplicate, and stale-skip. The reason grammar
is proven against the C143 corpus in ``test_label_pass_lifecycle.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routes.admin_label_pass import _partition_candidates, _verdict_outcome

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=5)
PAST = NOW - timedelta(days=5)


def _proposal(pid, item_id, *, item_type="futures", decision="llm_proposed_promote", gen="g1", created=NOW):
    return SimpleNamespace(
        id=pid, item_type=item_type, item_id=str(item_id),
        item_name=f"Market {item_id}", category="politics", archetype=None,
        decision=decision, admin_notes="note",
        features={"generation": gen, "evidence_generation": gen} if gen else None,
        created_at=created,
    )


def _market(mid, *, status="open", resolution_date=FUTURE):
    return SimpleNamespace(
        id=mid, status=status, resolution_date=resolution_date,
        volume_24h=1000, llm_sport_category="politics", market_tier=2,
    )


# ---- GET /pending partition ------------------------------------------------

def test_valid_proposal_is_actionable():
    p = _proposal(1, 101)
    part = _partition_candidates([p], {101: _market(101)}, NOW)
    assert [pp.id for pp, _ in part["actionable"]] == [1]
    assert part["retired_reasons"] == {}
    assert part["quarantine_reasons"] == {}
    assert part["oldest_gen"] == "g1" and part["newest_gen"] == "g1"


def test_resolved_market_is_retired_terminal():
    part = _partition_candidates([_proposal(1, 101)], {101: _market(101, status="resolved")}, NOW)
    assert part["actionable"] == []
    assert part["retired_reasons"] == {"lifecycle_terminal": 1}


def test_past_resolution_is_retired():
    part = _partition_candidates([_proposal(1, 101)], {101: _market(101, resolution_date=PAST)}, NOW)
    assert part["retired_reasons"] == {"lifecycle_past": 1}


def test_missing_market_is_retired():
    part = _partition_candidates([_proposal(1, 999)], {}, NOW)
    assert part["retired_reasons"] == {"market_missing": 1}


def test_unmatched_email_is_retired():
    p = _proposal(1, "some-headline-slug", item_type="email")
    part = _partition_candidates([p], {}, NOW)
    assert part["retired_reasons"] == {"canonical_identity_missing": 1}


def test_superseded_older_duplicate_is_retired():
    # Newest-first: the fresh proposal for target 101 stays actionable; the older
    # duplicate for the SAME target is superseded.
    newest = _proposal(2, 101, gen="g2")
    oldest = _proposal(1, 101, gen="g1")
    part = _partition_candidates([newest, oldest], {101: _market(101)}, NOW)
    assert [pp.id for pp, _ in part["actionable"]] == [2]
    assert part["retired_reasons"] == {"proposal_superseded": 1}


def test_poison_proposal_is_isolated_healthy_siblings_survive():
    class Poison:
        id = 7
        item_type = "futures"
        item_id = "500"
        created_at = NOW
        @property
        def features(self):
            raise RuntimeError("boom")

    good_before = _proposal(1, 101)
    good_after = _proposal(3, 103)
    part = _partition_candidates(
        [good_before, Poison(), good_after], {101: _market(101), 103: _market(103), 500: _market(500)}, NOW
    )
    # Both healthy siblings survive; the poison proposal is quarantined, not fatal.
    assert sorted(pp.id for pp, _ in part["actionable"]) == [1, 3]
    assert part["quarantine_reasons"] == {"authority_unavailable": 1}


# ---- POST /verdict revalidation --------------------------------------------

def _outcome(proposal, market, **kw):
    kw.setdefault("verdict", "accept")
    kw.setdefault("kill_switch", True)
    kw.setdefault("duplicate", False)
    kw.setdefault("posted_gen", "g1")
    return _verdict_outcome(proposal, market, NOW, **kw)


def test_valid_accept_writes_bounded_term():
    out = _outcome(_proposal(1, 101), _market(101))
    assert out == {"status": "written", "reason": "current", "writes": 1, "delta": 8}


def test_valid_reject_writes_negative_term():
    out = _outcome(_proposal(1, 101), _market(101), verdict="reject")
    assert out["status"] == "written" and out["delta"] == -18


def test_kill_switch_off_writes_zero_term():
    out = _outcome(_proposal(1, 101), _market(101), kill_switch=False)
    assert out["status"] == "written" and out["delta"] == 0


def test_verdict_on_resolved_market_refuses():
    out = _outcome(_proposal(1, 101), _market(101, status="resolved"))
    assert out == {"status": "conflict", "reason": "lifecycle_terminal", "writes": 0, "delta": 0}


def test_stale_skip_writes_nothing():
    out = _outcome(_proposal(1, 101), _market(101, status="resolved"), verdict="skip")
    assert out["writes"] == 0 and out["status"] == "conflict"


def test_get_valid_post_stale_generation_refuses():
    # Proposal generation advanced (client saw g1, proposal now regenerated) → refuse.
    out = _outcome(_proposal(1, 101, gen="g2"), _market(101), posted_gen="g1")
    assert out == {"status": "conflict", "reason": "posted_generation_mismatch", "writes": 0, "delta": 0}


def test_duplicate_post_refuses():
    out = _outcome(_proposal(1, 101), _market(101), duplicate=True)
    assert out == {"status": "conflict", "reason": "duplicate_verdict", "writes": 0, "delta": 0}


def test_legacy_proposal_without_generation_still_verdicts():
    # A pre-#1542 row (features=None) must still accept a verdict; created_at is
    # its stable generation fallback and the client echoes it back unchanged.
    legacy = _proposal(1, 101, gen=None)
    posted = legacy.created_at.isoformat()
    out = _outcome(legacy, _market(101), posted_gen=posted)
    assert out["status"] == "written" and out["writes"] == 1
