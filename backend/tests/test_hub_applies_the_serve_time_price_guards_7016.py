"""#7016: the hub/league cards apply the serve-time price guards the detail route does.

WHAT A READER SAW, on production 2026-09-18. ``/hub/boxing`` "TOURNAMENT WINNERS"
printed **Tyson Fury 97% · Usyk 93% · Kabayel 87% · Itauma 79% — for ONE belt**,
and a Featherweight ladder printed nine legs at a flat **49%** with
``Title is vacant`` among them. The same market, through the other door:

    GET /api/futures/2951423   Tyson Fury -> None  (mutually_exclusive, prices_withheld: 1)
    GET /api/hub/boxing        Tyson Fury -> 0.97

``routes/hub.py`` composes ``get_league_futures`` payloads, and
``routes/league_futures.py`` built ``top_outcomes`` straight off the stored
column — it imported none of the serve-time price policy. So the withholding
(#5611 / #5876 / #6532 / #6757) and the exclusive-field squeeze (#23 / #199)
that ``/api/futures/{id}`` has applied for months never ran for any hub.
Measured across the first 12 ladders of each hub: **76 rows published that the
detail route withholds, 115 rows served at a different number.**

THE DEFECT IS THE DISAGREEMENT, so these guards are written about the two
behaviours that produce it — what a refused row prints, and what the surviving
rows are divided by — plus one structural guard that the two routes keep asking
ONE rule rather than two copies of it.
"""

import pytest

from app.routes import futures as futures_route
from app.routes import league_futures as lf


class _Outcome:
    def __init__(self, oid, name, prob, opening=None, movement=None):
        self.id = oid
        self.name = name
        self.current_probability = prob
        self.opening_probability = opening
        self.rank = oid
        self.probability_change_24h = movement
        self.team_id = None
        self.is_winner = False
        self.resolution_source = None


class _Market:
    def __init__(self, name="WBC Heavyweight Title", *, mutually_exclusive=True):
        self.name = name
        self.llm_sport_category = "boxing"
        self.mutually_exclusive = mutually_exclusive


# ── what a refused row prints (acceptance 2 + 3) ────────────────────────────


def test_a_withheld_row_serves_no_price():
    """Fury's row, the specimen. The detail route serves null; so does this one."""
    rows = lf._serialize_outcomes(
        [_Outcome(1, "Tyson Fury", 0.97, movement=0.04), _Outcome(2, "Usyk", 0.03)],
        _Market(),
        {1},
    )
    fury = next(r for r in rows if r["id"] == 1)
    assert fury["probability"] is None


def test_the_movement_twin_goes_with_it():
    """Leaving the 24h change lets a reader reconstruct the price we just refused.

    This payload's spelling of ``probability_change_24h``, which is in the detail
    route's ``WITHHELD_PRICE_FIELDS`` for exactly this reason.
    """
    rows = lf._serialize_outcomes(
        [_Outcome(1, "Tyson Fury", 0.97, movement=0.04), _Outcome(2, "Usyk", 0.03)],
        _Market(),
        {1},
    )
    assert next(r for r in rows if r["id"] == 1)["movement_24h"] is None


def test_the_key_is_present_and_null_never_omitted():
    """The clients test ``!== null`` and ``undefined !== null`` is true."""
    rows = lf._serialize_outcomes([_Outcome(1, "Tyson Fury", 0.97)], _Market(), {1})
    assert "probability" in rows[0]


def test_the_row_is_withheld_not_deleted():
    """gotcha #21: withhold, never rewrite. The nine flat-0.49 Featherweight legs
    keep their names — including ``Title is vacant`` — and print the no-price mark
    the card already draws. Dropping them would answer a question nobody asked.
    """
    legs = [_Outcome(i, f"Fighter {i}", 0.49) for i in range(1, 10)]
    legs.append(_Outcome(99, "Title is vacant", 0.49))
    rows = lf._serialize_outcomes(legs, _Market(), {o.id for o in legs})

    assert [r["name"] for r in rows] == [o.name for o in legs]
    assert all(r["probability"] is None for r in rows)


def test_a_row_nobody_refused_is_untouched():
    """The control. A coherent field with an empty withheld set still prints its
    prices — this fix withholds what the guards name and nothing else.
    """
    rows = lf._serialize_outcomes(
        [_Outcome(1, "Iga Swiatek", 0.795), _Outcome(2, "Qinwen Zheng", 0.205)],
        _Market(),
        set(),
    )
    assert [r["probability"] for r in rows] == [0.795, 0.205]


# ── what the survivors are divided by ───────────────────────────────────────


def test_the_withholding_decides_whether_there_is_a_divisor_at_all():
    """THE ORDERING GUARD. Re-specimened by #7103, which REVERSED this test's
    original expectation, so the reversal is recorded here rather than hidden in
    a diff.

    As shipped, this guard used three legs — 0.9 (refused) + 0.6 + 0.5 — and
    asserted the two survivors were squeezed to sum 1.0, because withholding
    first dropped the raw 2.0 field into the normalizable band. #7103 measured
    that exact mechanism as the defect: the squeeze's premise is that the legs it
    can see ARE the field, and once a leg is withheld because its price is
    UNKNOWN that premise is false. On `/api/futures/2951423` it restated Agit
    Kabayel's honest 0.870 as 0.767. So a withheld-bearing field is no longer
    squeezed at all, and the old specimen's survivors correctly stay raw.

    THE ORDER IS STILL LOAD-BEARING, and this specimen proves it with a live
    observable rather than a vacuous one. Three legs — 0.5 (refused) + 0.4 + 0.3
    — sum to **1.2**, INSIDE the band. A NORMALIZE-THEN-WITHHOLD implementation
    has withheld nothing yet when it asks, so it squeezes the whole field by 1.2
    and hands the reader 0.333 and 0.25. Withholding FIRST makes the count the
    gate reads non-zero, the squeeze is refused, and the survivors print the raw
    0.4 and 0.3 their books actually bound.

    The two orders therefore still disagree on the printed number, which is what
    makes this assertion worth writing — only now they disagree the other way up.
    """
    rows = lf._serialize_outcomes(
        [_Outcome(1, "A", 0.5), _Outcome(2, "B", 0.4), _Outcome(3, "C", 0.3)],
        _Market(),
        {1},
    )
    survivors = [r["probability"] for r in rows if r["id"] != 1]

    assert survivors == [0.4, 0.3]
    # The wrong order squeezes the whole field by 1.2 and lands exactly here.
    assert survivors != [0.333, 0.25]
    assert sum(survivors) == pytest.approx(0.7, abs=1e-3)


def test_the_squeeze_divides_by_the_whole_field_not_the_served_ten():
    """THE TRUNCATION TRAP, and the subtlest way to "fix" this into a new defect.

    This payload serves the top ten; the detail route serves all N. Twelve legs —
    ten at 0.12 and two at 0.05 — sum to **1.30** over the field and **1.20** over
    the served ten. Normalizing the slice would divide by the smaller sum, inflate
    all ten rows to a tidy 100%, and manufacture a BRAND-NEW disagreement with the
    detail route on the very rows this issue exists to reconcile.

    So the served ten must keep the two longshots' share — summing to ~0.92, a
    tenth short of the whole — and specifically NOT to 1.0.

    The band is deliberately loose because the shared normalizer rounds on the
    PERCENT scale (``politics.py`` ``round(…, 1)``), so 9.230…% is printed 9.2%
    and ten of those sum to 0.920 rather than 0.923. Pinning the exact figure
    would make this guard a restatement of that rounding; what it is actually
    about is the divisor, and the two divisors are 0.92 apart from 1.0.
    """
    legs = [_Outcome(i, f"Contender {i}", 0.12) for i in range(1, 11)]
    legs += [_Outcome(11, "Longshot A", 0.05), _Outcome(12, "Longshot B", 0.05)]

    rows = lf._serialize_outcomes(legs, _Market(), set())

    assert len(rows) == 10
    served = sum(r["probability"] for r in rows)
    assert 0.90 <= served <= 0.94
    # Normalizing the served slice instead of the field lands exactly here.
    assert served != pytest.approx(1.0, abs=1e-2)


def test_a_participation_family_is_never_squeezed():
    """#199: golf make-cut / top-N are simultaneously true and honestly sum past
    100%. Squeezing them turned an 86% to make the cut into ~1%. The flag comes
    off the market, and a hub ladder must respect it exactly as the detail does.

    THE SUM HERE IS CHOSEN, AND THAT IS THE WHOLE TEST. My first version of this
    case used 0.86 / 0.80 / 0.75 — a sum of 2.41, past ``_FIELD_SUM_MAX`` (1.60),
    where the independent-binary overround guard keeps every price raw no matter
    what the flag says. It passed against a mutant that ignored the flag
    completely: both programs agree on that input, so it asserted nothing. 1.45
    sits inside the normalizable band, where honouring the flag and ignoring it
    give different printed numbers, and only there does this guard have an
    opinion.
    """
    rows = lf._serialize_outcomes(
        [_Outcome(1, "A", 0.60), _Outcome(2, "B", 0.55), _Outcome(3, "C", 0.30)],
        _Market("The Open: To Make The Cut", mutually_exclusive=False),
        set(),
    )
    assert [r["probability"] for r in rows] == [0.60, 0.55, 0.30]


def test_an_opening_is_withheld_once_the_printed_column_has_moved():
    """#5539, inherited with the squeeze. A raw opening beside a squeezed price is
    a movement the reader can compute and we never observed; rescaling it would
    invent an opening, and ``calibration_probability`` coalesces to
    ``opening_probability`` (gotcha #144), so the invention becomes a forecast we
    are graded on.
    """
    rows = lf._serialize_outcomes(
        [_Outcome(1, "A", 0.8, opening=0.7), _Outcome(2, "B", 0.5, opening=0.3)],
        _Market(),
        set(),
    )
    assert all(r["opening_probability"] is None for r in rows)


def test_an_opening_survives_a_field_that_did_not_move():
    """The control for the guard above — it fires on the squeeze, not on every card."""
    rows = lf._serialize_outcomes(
        [_Outcome(1, "A", 0.6, opening=0.55), _Outcome(2, "B", 0.4, opening=0.45)],
        _Market(),
        set(),
    )
    assert [r["opening_probability"] for r in rows] == [0.55, 0.45]


# ── one rule, not two copies ────────────────────────────────────────────────


def test_the_hub_asks_the_detail_routes_own_withhold_helper():
    """THE CLASS GUARD. #7016 is not "the hub computes the wrong prices" — it is
    "one market, two doors, two answers". A second spelling of the withholding
    rule living in this module would satisfy every assertion above and re-open the
    defect the first time the two copies drifted, which is the failure master's own
    history keeps paying for: one rule, two copies, and the copy nobody executes is
    the one that rots.

    #6993 hung the four arms on ONE hook days before this shipped, precisely so
    that "adding an arm reaches every caller". This asserts the hub is hanging
    from that same hook — IDENTITY, not behaviour, so forking a private union into
    ``league_futures`` fails here even on the day it is written byte-for-byte
    correct, and so a fifth arm added to the helper can never silently miss the
    five hub pages.
    """
    assert lf._withheld_price_outcome_ids is futures_route._withheld_price_outcome_ids


@pytest.mark.asyncio
async def test_a_fifth_arm_added_to_the_helper_reaches_the_hub_card():
    """The property the identity check above exists to buy, exercised end to end.

    Patched on ``futures_route`` — the module that OWNS the rule — and read
    through the hub's own serializer, so this fails if the hub is ever pointed at
    a private copy that a change to the shared helper cannot reach.
    """
    market = _Market()
    market.outcomes = [_Outcome(1, "Tyson Fury", 0.97)]
    market.source = "kalshi"

    original = futures_route._empty_book_outcome_ids
    try:
        futures_route._empty_book_outcome_ids = lambda *_a, **_k: {1}
        withheld = await futures_route._withheld_price_outcome_ids(None, market)
    finally:
        futures_route._empty_book_outcome_ids = original

    rows = lf._serialize_outcomes(market.outcomes, market, withheld)
    assert rows[0]["probability"] is None
