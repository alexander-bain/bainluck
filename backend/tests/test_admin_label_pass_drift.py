"""#1542 / #1873 — the DRIFT layer: a verdict may not be written against a card
that moved since it was read.

The lifecycle suite next door (``test_admin_label_pass_lifecycle.py``) covers
"is this proposal still current". This one covers "is this still the card he
graded", which the lifecycle gate structurally cannot answer — see the module
docstring of ``app.utils.label_pass_card`` for why the pre-existing
``posted_generation`` check can never fire for a re-price.

Duck-typed fakes throughout, no DB: every function under test is pure by
construction, which is the point of extracting them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.admin_label_pass import (
    _drift_outcome,
    _live_features,
    _live_title,
)
from app.utils.label_pass_card import (
    card_fingerprint,
    compare_snapshot,
    rendered_percent,
)

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(days=30)


def _proposal(*, item_name="Michigan Senate winner?", features=None):
    return SimpleNamespace(
        id=1,
        item_type="futures",
        item_id="109081",
        item_name=item_name,
        category="politics",
        archetype=None,
        decision="llm_proposed_promote",
        admin_notes=None,
        features=features if features is not None else {"generation": "g1", "evidence_generation": "g1"},
        created_at=NOW,
    )


def _market(*, name="Michigan Senate winner?", status="open"):
    return SimpleNamespace(
        id=109081,
        name=name,
        status=status,
        resolution_date=FUTURE,
        volume_24h=4200,
        llm_sport_category="politics",
        market_tier=2,
    )


def _outcomes(*pairs):
    return [
        SimpleNamespace(id=i, market_id=109081, name=n, current_probability=p)
        for i, (n, p) in enumerate(pairs, start=1)
    ]


FIELD = (("Democrat", 0.565), ("Republican", 0.435))


# ── the gate refuses ─────────────────────────────────────────────────────────

def test_a_reprice_between_get_and_post_refuses_and_writes_nothing():
    """The headline case. Nothing about the PROPOSAL changed — same generation,
    same open market, same future resolution date — so every lifecycle signal
    still reads actionable. Only the price moved."""
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*FIELD))
    moved = _live_features(p, _market(), _outcomes(("Democrat", 0.71), ("Republican", 0.29)))

    drift = _drift_outcome(read, moved)
    assert drift is not None
    assert drift["reason"] == "card_drifted"
    assert drift["writes"] == 0 and drift["applied"] is False
    assert drift["expected"] == moved["card_fingerprint"]
    assert drift["posted"] == read["card_fingerprint"]
    # The refusal has to say what it moved TO, or the client cannot re-render.
    assert drift["live_card"]["probability"] == pytest.approx(0.71)


def test_the_generation_check_cannot_catch_that_case():
    """Non-vacuity for the whole queue: prove the EXISTING guard is blind here,
    so the new one is not decoration. Generation is stamped once at birth and
    #1542 item 5 stopped the evaluator refreshing it, so it is identical on both
    sides of a re-price."""
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*FIELD))
    moved = _live_features(p, _market(), _outcomes(("Democrat", 0.71), ("Republican", 0.29)))

    from app.utils.label_pass_lifecycle import read_generation

    assert read_generation(p.features) == read_generation(p.features)  # unchanged, by construction
    assert read.get("generation") == moved.get("generation")  # neither carries one
    assert read["card_fingerprint"] != moved["card_fingerprint"]  # only this separates them


def test_an_absent_fingerprint_fails_closed_with_its_own_reason():
    live = _live_features(_proposal(), _market(), _outcomes(*FIELD))
    for posted in ({}, None, {"generation": "g1"}):
        drift = _drift_outcome(posted, live)
        assert drift is not None, posted
        assert drift["reason"] == "card_fingerprint_missing"
        assert drift["writes"] == 0


def test_a_field_going_incoherent_refuses():
    """The card stops showing a number at all — honest-empty is a different card
    from a 56% one, and grading the first as if it were the second is the defect."""
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*FIELD))
    incoherent = _live_features(p, _market(), _outcomes(("Democrat", 0.9), ("Republican", 0.9)))
    assert incoherent["field_coherent"] is False
    assert incoherent["probability"] is None
    assert _drift_outcome(read, incoherent)["reason"] == "card_drifted"


def test_a_retitled_market_refuses():
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*FIELD))
    renamed = _live_features(p, _market(name="Michigan Senate: who wins?"), _outcomes(*FIELD))
    assert _drift_outcome(read, renamed)["reason"] == "card_drifted"


def test_a_reordered_field_refuses():
    """Two outcomes swapping rank changes the leader, so it changes the card even
    though the multiset of prices is identical."""
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*FIELD))
    flipped = _live_features(p, _market(), _outcomes(("Republican", 0.565), ("Democrat", 0.435)))
    assert _drift_outcome(read, flipped)["reason"] == "card_drifted"


# ── the gate does NOT refuse: the half that keeps it usable ──────────────────

def test_the_round_trip_verdicts_when_nothing_moved():
    """A guard that refuses everything is as useless as one that refuses nothing.
    The GET's own features, posted back verbatim, must pass."""
    p = _proposal()
    served = _live_features(p, _market(), _outcomes(*FIELD))
    served["generation"] = "g1"  # what the route adds before serving
    live = _live_features(p, _market(), _outcomes(*FIELD))
    assert _drift_outcome(served, live) is None


def test_a_subpercent_reprice_does_not_refuse():
    """THE LOAD-BEARING PROPERTY. The fingerprint is taken at the resolution the
    surface renders (whole percent), so a move Alex could not have seen cannot
    refuse his verdict. Hashing raw floats would 409 on every poll tick and take
    the label pass down on a labeling night."""
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(("Democrat", 0.561), ("Republican", 0.439)))
    nudged = _live_features(p, _market(), _outcomes(("Democrat", 0.5614), ("Republican", 0.4386)))
    assert read["probability"] != nudged["probability"]  # the floats really did differ
    assert _drift_outcome(read, nudged) is None


def test_an_outcome_outside_the_served_slice_does_not_refuse():
    """Only the served slice is fingerprinted. A ninth row moving is invisible on
    screen, so refusing for it would be refusing for a change nobody saw."""
    # A coherent nine-way field (sums to 1.0) so the outcomes really are served.
    base = [("Front runner", 0.36)] + [(f"Candidate {i}", 0.08) for i in range(8)]
    p = _proposal()
    read = _live_features(p, _market(), _outcomes(*base))
    tail_moved = list(base)
    tail_moved[8] = ("Candidate 7", 0.079)
    moved = _live_features(p, _market(), _outcomes(*tail_moved))
    assert len(read["outcomes"] or []) == 8
    assert _drift_outcome(read, moved) is None


# ── the instrument (#1873's measurement half) ────────────────────────────────

def test_a_snapshot_with_no_reading_is_not_drift():
    """The production shape: every pending snapshot holds only generation keys.
    The boolean this replaces returned True for all of them."""
    assert compare_snapshot(None, 0.92) == "no_reading"
    assert compare_snapshot(None, None) == "no_reading"


def test_the_three_way_separates_drift_from_agreement():
    assert compare_snapshot(0.60, 0.71) == "drifted"
    assert compare_snapshot(0.60, 0.60) == "agrees"
    assert compare_snapshot(0.60, None) == "no_live_reading"
    assert compare_snapshot("not a number", 0.6) == "unreadable"


def test_the_snapshot_bar_is_material_drift_not_the_fingerprint_bar():
    """The two comparisons answer different questions over different timescales,
    so they carry different bars — and the difference is asserted rather than
    left to be discovered as an inconsistency (ruling 100)."""
    # One rendered percent apart: a DIFFERENT card to the fingerprint (it gates a
    # write and must be explicable on screen), the SAME reading to the diagnostic
    # (it reports weeks-long rot, where a point is noise).
    assert compare_snapshot(0.56, 0.55) == "agrees"
    assert rendered_percent(0.56) != rendered_percent(0.55)
    # Queue 355's tolerance, unchanged by this queue.
    assert compare_snapshot(0.60, 0.649) == "agrees"
    assert compare_snapshot(0.60, 0.651) == "drifted"


def test_the_route_reports_the_three_way_and_the_boolean_only_on_real_drift():
    live_only = _live_features(_proposal(), _market(), _outcomes(*FIELD))
    assert live_only["snapshot_comparison"] == "no_reading"
    assert live_only["snapshot_disagrees"] is False  # the old boolean said True here

    with_reading = _live_features(
        _proposal(features={"generation": "g1", "evidence_generation": "g1", "probability": 0.20}),
        _market(),
        _outcomes(*FIELD),
    )
    assert with_reading["snapshot_comparison"] == "drifted"
    assert with_reading["snapshot_disagrees"] is True


# ── the live title (#1873's copy half) ───────────────────────────────────────

def test_the_live_title_wins_and_the_snapshot_is_kept_beside_it():
    p = _proposal(item_name="Oscar winner: Best Picture")
    m = _market(name="Oscar Winner: Best Picture")
    assert _live_title(p, m) == "Oscar Winner: Best Picture"
    features = _live_features(p, m, _outcomes(*FIELD))
    assert features["title"] == "Oscar Winner: Best Picture"
    assert features["title_at_write"] == "Oscar winner: Best Picture"


def test_the_title_falls_back_when_there_is_no_market():
    """Email proposals and unresolvable ids have no live row to read a name from;
    they must keep working rather than serve a blank headline."""
    p = _proposal(item_name="Polymarket email: Fed Chair")
    assert _live_title(p, None) == "Polymarket email: Fed Chair"
    assert _live_title(p, SimpleNamespace(name=None)) == "Polymarket email: Fed Chair"


# ── the fingerprint primitive ────────────────────────────────────────────────

def test_rendered_percent_matches_javascript_math_round_not_python_round():
    """The .5 boundary is where Python and the surface disagree, so it is the
    only interesting case. ``round(56.5)`` is 56 in Python (banker's) and 57 in
    ``Math.round`` (half-up); the surface is the authority."""
    # 0.125 and 0.625 are exactly representable, so they really do land on .5 —
    # most decimals do not (0.565 * 100 is 56.4999…, where every rounding mode
    # agrees on 56, which is why a casual test value proves nothing here).
    assert round(0.125 * 100) == 12 and round(0.625 * 100) == 62  # Python, banker's
    assert rendered_percent(0.125) == 13  # Math.round, and what the page prints
    assert rendered_percent(0.625) == 63
    assert rendered_percent(0.565) == 56  # 56.4999… — no boundary, all modes agree
    assert rendered_percent(0.5651) == 57
    assert rendered_percent(0.0) == 0
    assert rendered_percent(None) is None
    assert rendered_percent("x") is None


def test_withheld_and_empty_fields_are_different_cards():
    args = dict(title="T", status="open", resolution_date=None, field_coherent=False)
    assert card_fingerprint(outcomes=None, **args) != card_fingerprint(outcomes=[], **args)


def test_the_fingerprint_is_stable_across_identical_reads():
    args = dict(
        title="T", status="open", resolution_date="2026-09-01T00:00:00+00:00",
        field_coherent=True, outcomes=[{"name": "A", "probability": 0.5}],
    )
    assert card_fingerprint(**args) == card_fingerprint(**args)
