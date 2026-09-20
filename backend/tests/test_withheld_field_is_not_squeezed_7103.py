"""#7103: a field with withheld members is not a proved-complete distribution.

WHAT A READER SAW, on production. ``/hub/boxing`` → *WBC Heavyweight Title on
January 1, 2027* printed **Agit Kabayel 77%**. Kabayel's stored price is
**0.870**, and his is one of the six legs that SURVIVED #7059's book test — his
book bounds something, so 0.87 is the only price we have any evidence for. The
page restated it as 77%, a 10.3-point move on an honest leg:

    GET /api/futures/2951423        prices_withheld: 11
      Agit Kabayel     stored 0.870 -> served 0.767
      Title is vacant  stored 0.225 -> served 0.198
      Chisora / Parker / Wilder / Wardley   0.010 -> 0.009

Every survivor scaled by the same 0.8816 = 1 / 1.135.

THE CAUSE IS THE SQUEEZE'S PREMISE, NOT ITS ARITHMETIC. Before #7059 the field
sat at a raw 2.995 — above ``_FIELD_SUM_MAX`` — so #1200 bailed it out to raw
prices and ``normalize_display_probs`` never fired. Withholding 11 legs dropped
the surviving sum to 1.135, INTO the band, and the squeeze switched on. So
withholding changes WHETHER the squeeze fires, not merely what it divides by.

``normalize_display_probs`` reads an absent value as 0 (``o.get(key) or 0``), so
the field is normalized as if eleven fighters cannot win. That is ruling 051's
sentence one case over: absent is not zero, and a withheld price means the price
is UNKNOWN, not that it is nothing.

THE SURVIVORS PRINT RAW AND MAY SUM PAST 100%, which is the deliberate trade and
not a regression. #1200 already prints raw overrounded fields summing to several
multiples of 100%, and ``drop_incoherent_near_certain`` already makes exactly
this call for its own drop — "deliberately NOT re-normalizing the survivors",
because squeezing three 0.0005 longshots would print three 33% contenders out of
noise.

BOTH SURFACES GATE TOGETHER. ``routes/futures.py`` (detail) and
``routes/league_futures.py`` (/hub) carry two copies of the withhold-then-squeeze
pair. Gating one and not the other would divide the same board by two different
numbers and re-open the disagreement #7016 closed, so the cross-surface
agreement is guarded here by name.
"""

import pytest

from app.routes import league_futures as lf
from app.utils.outcome_display import normalize_display_probs


class _Outcome:
    def __init__(self, oid, name, prob):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = None
        self.rank = oid
        self.probability_change_24h = None
        self.team_id = None
        self.is_winner = False
        self.resolution_source = None


class _Market:
    def __init__(self, name="WBC Heavyweight Title", *, mutually_exclusive=True):
        self.name = name
        self.llm_sport_category = "boxing"
        self.mutually_exclusive = mutually_exclusive
        self.status = "open"


def _field(*pairs):
    return [_Outcome(i, n, p) for i, (n, p) in enumerate(pairs, start=1)]


# ── the unit: the gate on the shared normalizer ─────────────────────────────


def test_a_withheld_field_is_not_squeezed():
    """The specimen's shape, reduced. Survivors sum to 1.135 — inside the band,
    so the squeeze WOULD fire — and must be left exactly as their books read."""
    outcomes = [
        {"probability": 0.870},
        {"probability": 0.225},
        {"probability": 0.010},
        {"probability": 0.010},
        {"probability": 0.010},
        {"probability": 0.010},
    ]

    moved = normalize_display_probs(outcomes, field_complete=False)

    assert moved is False
    assert [o["probability"] for o in outcomes] == [0.870, 0.225, 0.010, 0.010, 0.010, 0.010]
    # The honest leg keeps the only price anything bounded, not 0.767.
    assert outcomes[0]["probability"] != pytest.approx(0.767, abs=1e-3)


def test_the_same_field_IS_squeezed_when_nothing_was_withheld():
    """THE GATE IS NOT A BLANKET OFF-SWITCH. Byte-identical input to the test
    above; the ONLY difference is that nothing was withheld, and the #23 squeeze
    must still do its job. Without this pair the fix could be "never squeeze"
    and both tests above would still pass."""
    outcomes = [
        {"probability": 0.870},
        {"probability": 0.225},
        {"probability": 0.010},
        {"probability": 0.010},
        {"probability": 0.010},
        {"probability": 0.010},
    ]

    moved = normalize_display_probs(outcomes, field_complete=True)

    assert moved is True
    assert sum(o["probability"] for o in outcomes) == pytest.approx(1.0, abs=1e-2)
    assert outcomes[0]["probability"] == pytest.approx(0.767, abs=1e-3)


def test_the_default_is_complete_so_every_existing_caller_is_unmoved():
    """``field_complete`` defaults True exactly as ``mutually_exclusive`` does.
    The dozen callers that know nothing about withholding — search, politics,
    f1/tennis/awards/cycling/soccer event adapters, the history basis — must be
    bit-identical to today."""
    outcomes = [{"probability": 0.8}, {"probability": 0.4}]

    assert normalize_display_probs(outcomes) is True
    assert sum(o["probability"] for o in outcomes) == pytest.approx(1.0, abs=1e-2)


def test_the_gate_sits_below_the_untraded_placeholder_strip():
    """PLACEMENT, and the one way this fix could have changed more than it meant
    to. The #1201 strip mutates the caller's list IN PLACE — it is what takes a
    run of untraded exact-0.5 placeholders off the page. A gate that returned
    above it would change WHICH ROWS ARE SERVED on a withheld-bearing field, not
    just whether they are scaled. Twelve placeholders plus two real legs: the
    placeholders still go, and the two real legs still print raw."""
    outcomes = [{"probability": 0.5} for _ in range(12)]
    outcomes += [{"probability": 0.62}, {"probability": 0.44}]

    moved = normalize_display_probs(outcomes, field_complete=False)

    assert moved is False
    assert len(outcomes) == 2, "the untraded-midpoint strip must still run"
    assert [o["probability"] for o in outcomes] == [0.62, 0.44]


def test_a_non_exclusive_family_is_still_refused_first():
    """The participation gate (#199) is unaffected and still answers first: a
    complete golf make-cut field is not squeezed either."""
    outcomes = [{"probability": 0.86}, {"probability": 0.74}, {"probability": 0.55}]

    assert normalize_display_probs(outcomes, mutually_exclusive=False) is False
    assert [o["probability"] for o in outcomes] == [0.86, 0.74, 0.55]


# ── the surfaces: the hub, and its agreement with the detail route ──────────


def test_the_hub_prints_the_survivors_raw():
    """`/hub/boxing` is where #7103's reader stood.

    THE SURVIVORS MUST LAND IN THE BAND OR THIS GUARD PROVES NOTHING. The first
    draft used the specimen's own tail (0.225 + 0.04), which sums to 0.265 —
    under the band, where the squeeze never fires anyway — so it passed with the
    gate severed. Here the refused 0.9 leaves 0.7 + 0.45 = **1.15**, inside the
    band, so an ungated hub squeezes these two to sum 1.0 and a gated one prints
    the prices the books bound.
    """
    rows = lf._serialize_outcomes(
        _field(("Refused", 0.9), ("Kabayel", 0.7), ("Vacant", 0.45)),
        _Market(),
        {1},
    )

    by_id = {r["id"]: r["probability"] for r in rows}
    assert by_id[1] is None, "the refused leg still prints nothing"
    assert [by_id[2], by_id[3]] == [0.7, 0.45]
    assert sum(v for v in by_id.values() if v is not None) != pytest.approx(1.0, abs=1e-2)


def test_the_hub_still_squeezes_a_complete_field():
    """The hub's half of the not-a-blanket-off-switch pair (#7016 item 1 stays
    shipped): with nothing withheld, the exclusive-field squeeze still runs."""
    rows = lf._serialize_outcomes(
        _field(("A", 0.87), ("B", 0.225), ("C", 0.04)),
        _Market(),
        set(),
    )

    assert sum(r["probability"] for r in rows) == pytest.approx(1.0, abs=1e-2)


def test_the_hub_gate_counts_what_this_payload_refused_not_the_market_wide_set():
    """``withheld_ids`` is computed over the WHOLE market, so testing its
    truthiness would gate the squeeze on ids that need not appear in these rows
    at all — a board would stop being squeezed because of a leg this payload
    never carried. The count is taken while nulling, so an id that matches
    nothing here leaves the field complete and the squeeze runs."""
    rows = lf._serialize_outcomes(
        _field(("A", 0.87), ("B", 0.225), ("C", 0.04)),
        _Market(),
        {99_999},  # a real id in the market, absent from this payload
    )

    assert [r["probability"] for r in rows] != [0.87, 0.225, 0.04]
    assert sum(r["probability"] for r in rows) == pytest.approx(1.0, abs=1e-2)


def test_the_two_surfaces_gate_on_the_same_rule():
    """THE STRUCTURAL GUARD, and the reason this file exists rather than two.
    Both routes carry their own copy of withhold-then-squeeze; if either one
    stops passing ``field_complete`` the same board divides by two different
    numbers and #7016's disagreement is back. Asked of the source, because the
    two copies cannot be made to share a call site without moving far more than
    this fix should."""
    import inspect

    from app.routes import futures as futures_route

    for module in (futures_route, lf):
        src = inspect.getsource(module)
        assert "field_complete=prices_withheld == 0" in src, (
            f"{module.__name__} must gate the squeeze on its own withheld count"
        )
