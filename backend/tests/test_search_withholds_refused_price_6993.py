"""#6993, fourth and last arm — the SEARCH surfaces serve the same price refusal.

WHAT A READER SEES, production 2026-09-18. Three arms of #6993 had shipped and
``/futures/109485`` — *How low will the Nasdaq-100 get in 2026?* — serves outcome
``1597367`` ("24,800 or below") as ``probability: null``, ``prices_withheld: 1``,
the rung drawn as ``—`` with no bar. In the same minute::

    GET /api/events/search?q=Nasdaq-100
      .futures[3].top_outcomes[0]                     -> 1.0, rank 1
      .futures_families[0].members[2].top_outcomes[0] -> 1.0, rank 1

and ``/search?q=Nasdaq-100`` at 390px prints ``24,800 or below 100%`` in its
ANSWERS block — **one tap above the page that renders that identical rung as a
dash.** Search is the surface a reader actually arrives on; the detail page is
where they land afterwards and find it contradicted.

WHY THIS ARM IS SEPARATE AND NOT A WIDENING OF THE OTHERS. ``routes/events.py``
held **zero** references to the refusal rail, and ``_build_search_top_outcomes``
is SYNCHRONOUS — it takes a market and nothing else — while the union is
``async(db, market)`` because two of its four arms read the snapshot table. So
this is a real change of shape, not a hunk: both callers are async handlers that
now build the set and hand it down. That is why it was not folded into the
already-gated browse/faceted sha.

🪤 THE SPECIMEN'S ONE ARM. Of the four arms, only ``price_is_unsupported`` (the
db-backed one) catches ``1597367`` — ``prob=1.0, bid=0.0000, ask=1.0000``. The
two SYNC arms search could already have run answer False on it:
``is_empty_book_midpoint(1.0, 0.0, 1.0)`` is False because 1.0 is not the
midpoint of 0/1, and ``price_refuted_by_live_book`` is False. **Search's existing
sync guards structurally cannot reach this leg**, which is why threading ``db``
was unavoidable and why a cheaper local predicate would have shipped nothing.

THE ARMS THEMSELVES ARE NOT RE-ASSERTED HERE, for the reason both sibling files
give: which legs are refused belongs to ``_unsupported_price_outcome_ids`` and
its three siblings, each with its own guards. These tests stub the composed
union and assert the WIRING — that whatever the union answers, the search
surfaces apply it.

THE FIXTURE IS THE SPECIMEN'S OWN STORED ROWS, all nineteen legs of market
109485, read off production 2026-09-18 via ``db-query`` against
``futures_outcomes``, verbatim — probabilities, books, stored ranks, grades and
``last_updated`` stamps included. Nothing here was chosen to make something fire.

🪤 THE NEGATIVE CONTROL IS FREE AND IT IS ON THIS MARKET. Leg ``1597366``
("23,800 or below") has the **identical book** — ``0.0000 / 1.0000`` — but
carries ``resolution_source='api_settlement'``, so ``row_carries_a_verdict``
spares it and it keeps its ``0.99``. Any fix that withholds ``1597366`` too has
over-withheld, and settled means settled: withholding a graded row deletes a
result (#6532).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _build_search_top_outcomes,
    _served_prices_as_of,
)
from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS

MARKET_ID = 109485

#: The refused leg. Search led its card with this at ``1.0``/rank 1 while the
#: market's own page served ``null`` for it.
WITHHELD_ID = 1597367

#: Identical book (``0.0000/1.0000``), but GRADED — the over-withholding control.
GRADED_CONTROL_ID = 1597366

#: ``(id, name, prob, bid, ask, stored_rank, resolution_source, last_updated)``
#: — the nineteen stored legs of market 109485, verbatim, 2026-09-18.
#:
#: 🪤 THE STORED ``rank`` COLUMN IS NOT UNIQUE ON THIS MARKET: three legs carry
#: rank 1 (69678688, 1597363 and the refused 1597367) and three carry rank 7.
#: Pinning all nineteen rather than the interesting few is what stops a later
#: reader taking that for corruption, and it is why no assertion below keys on
#: "the rank-1 row" as if that named one leg.
#:
#: 🪤 ELEVEN LEGS QUOTE AN ASK AGAINST A ``0.0000`` BID and only ONE is refused
#: here — the graded ones are spared. The field sums well over 1.0 because this
#: is a cumulative threshold ladder, not a single-winner field.
SPECIMEN_LEGS = (
    (69678688, "22,600 or below", 0.185000, 0.1400, 0.2300, 1, "api_settlement", "2026-09-12T03:51:38.881246+00:00"),
    (1597363, "23,000 or below", 0.995000, 0.9910, 0.9990, 1, "api_settlement", "2026-06-09T08:47:04.116991+00:00"),
    (1597367, "24,800 or below", 1.000000, 0.0000, 1.0000, 1, None, "2026-04-13T16:45:15.777796+00:00"),
    (1597366, "23,800 or below", 0.990000, 0.0000, 1.0000, 2, "api_settlement", "2026-05-28T08:47:00.181844+00:00"),
    (69678687, "22,800 or below", 0.165000, 0.0800, 0.2500, 2, "api_settlement", "2026-09-12T03:51:38.881246+00:00"),
    (1597362, "23,200 or below", 0.985500, 0.9710, 1.0000, 2, "api_settlement", "2026-06-09T08:47:04.116991+00:00"),
    (69678689, "22,400 or below", 0.110000, 0.0700, 0.1500, 3, "api_settlement", "2026-09-12T03:51:38.881246+00:00"),
    (1597361, "23,400 or below", 0.985000, 0.9710, 0.9990, 3, "api_settlement", "2026-06-09T08:47:04.116991+00:00"),
    (69678691, "22,000 or below", 0.100000, 0.0700, 0.1300, 4, "api_settlement", "2026-09-12T03:51:38.881246+00:00"),
    (1597360, "23,600 or below", 0.910500, 0.8210, 1.0000, 4, "api_settlement", "2026-05-31T02:47:22.047552+00:00"),
    (69678690, "22,200 or below", 0.080000, 0.0500, 0.1100, 5, "api_settlement", "2026-09-12T03:51:38.881246+00:00"),
    (1597365, "24,000 or below", 0.950000, 0.0000, 1.0000, 5, "api_settlement", "2026-05-28T08:47:00.181844+00:00"),
    (1597364, "24,200 or below", 0.760000, 0.0000, 1.0000, 7, "api_settlement", "2026-05-28T08:47:00.181844+00:00"),
    (1597370, "25,500 or below", 0.940000, 0.0000, 1.0000, 7, None, "2026-04-13T16:45:15.777796+00:00"),
    (1597372, "24,600 or below", 0.880000, 0.0000, 1.0000, 7, None, "2026-04-27T00:45:52.620242+00:00"),
    (1597371, "24,400 or below", 0.800000, 0.0000, 1.0000, 8, None, "2026-04-27T00:45:52.620242+00:00"),
    (1597373, "25,400 or below", 0.880000, 0.0000, 1.0000, 9, None, "2026-04-13T16:45:15.777796+00:00"),
    (1597368, "25,000 or below", 0.860000, 0.0000, 1.0000, 11, None, "2026-04-13T16:45:15.777796+00:00"),
    (1597369, "25,200 or below", 0.820000, 0.0000, 1.0000, 12, None, "2026-04-13T16:45:15.777796+00:00"),
)


def _legs(only=None, delta_on=None):
    """The stored legs as row doubles. ``only`` restricts to a set of ids.

    ``delta_on`` puts a 24h delta on one id: no leg on this specimen carries a
    ``probability_change_24h`` in production, so the ``movement`` assertion
    manufactures one rather than claiming a live population it does not have.
    """
    return [
        SimpleNamespace(
            id=oid,
            name=name,
            external_id=f"KXNASDAQ100MINY-26DEC31H1600-T{name.split()[0].replace(',', '')}.01",
            current_probability=prob,
            current_yes_bid=bid,
            current_yes_ask=ask,
            current_american_odds=-110,
            probability_change_24h=0.05 if oid == delta_on else None,
            opening_probability=0.5,
            rank=stored_rank,
            is_winner=False,
            resolution_source=src,
            last_updated=datetime.fromisoformat(stamp),
        )
        for oid, name, prob, bid, ask, stored_rank, src, stamp in SPECIMEN_LEGS
        if only is None or oid in only
    ]


def _market(legs=None):
    return SimpleNamespace(
        id=MARKET_ID,
        name="How low will the Nasdaq-100 get in 2026?",
        source="kalshi",
        external_id="KXNASDAQ100MINY-26DEC31H1600",
        status="open",
        mutually_exclusive=False,
        outcomes=_legs() if legs is None else legs,
    )


def _by_id(served):
    return {o["id"]: o for o in served if "id" in o}


# ─────────────────────────────────────────────────────────────────────────────
# The defect itself: the refused price must not be served, and must not lead.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_refused_leg_no_longer_headlines_the_search_card():
    """RED AT THE PARENT: `top_outcomes[0]` was `1597367` at `1.0`."""
    served = _build_search_top_outcomes(
        _market(), limit=5, lean=False, withheld={WITHHELD_ID}
    )

    assert served, "the card must not be emptied by one refusal"
    assert served[0]["id"] != WITHHELD_ID
    # Nineteen legs and a slice of five, so demotion alone carries it off the
    # card entirely — the honest outcome when the ladder is longer than N.
    assert WITHHELD_ID not in _by_id(served)


def test_the_refused_price_and_every_spelling_of_it_are_null_when_it_survives_the_slice():
    """On a ladder SHORTER than the slice the leg stays, priceless but present.

    Manufactured deliberately: on the full nineteen-leg specimen the refused row
    is demoted off the card, so the nulling code path has no natural specimen
    there. Restricting the market to four legs is the same market, one door
    down — a short ladder is the common case across the browse population.
    """
    short = {WITHHELD_ID, GRADED_CONTROL_ID, 1597363, 1597362}
    served = _build_search_top_outcomes(
        _market(_legs(only=short, delta_on=WITHHELD_ID)),
        limit=5,
        lean=False,
        withheld={WITHHELD_ID},
    )

    row = _by_id(served)[WITHHELD_ID]
    assert row["probability"] is None
    # `movement` is this payload's spelling of the 24h delta — a number measured
    # FROM the value being refused. It is covered because it is in the shared
    # tuple, not because of a local rule.
    assert row["movement"] is None
    assert row["american_odds"] is None
    # Present-and-null, never omitted: the clients test `!== null`, and
    # `undefined !== null` is true (#5539).
    for field in WITHHELD_PRICE_FIELDS:
        if field in ("probability", "american_odds", "movement"):
            assert field in row, f"{field} must be present and null, not dropped"
    # Demoted even here, where it cannot leave the card.
    assert served[0]["id"] != WITHHELD_ID


def test_the_stored_rank_goes_with_the_price_because_it_is_seeded_from_it():
    """`rank: 1` beside `probability: null` republishes the refused claim.

    The stored column is seeded from the price at ingest — this leg's stored
    rank is literally 1 BECAUSE its price is the refused 1.0 — so serving it
    would say "this is the favourite" in a third costume.
    """
    short = {WITHHELD_ID, GRADED_CONTROL_ID, 1597363}
    served = _build_search_top_outcomes(
        _market(_legs(only=short)), limit=5, lean=False, withheld={WITHHELD_ID}
    )

    assert _by_id(served)[WITHHELD_ID]["rank"] is None
    # And ONLY that row's. The survivors keep the stored column untouched —
    # `rank` is deliberately NOT in `WITHHELD_PRICE_FIELDS`, because the detail
    # route already answers it correctly and differently (#2556 overwrites it
    # from the display order at `assign_display_ranks`).
    assert "rank" not in WITHHELD_PRICE_FIELDS
    assert _by_id(served)[GRADED_CONTROL_ID]["rank"] == 2


def test_the_typeahead_dropdown_is_withheld_too_although_it_carries_no_id():
    """🪤 THE TRAP THIS ARM MOST EASILY SHIPS BROKEN.

    The lean payload is `{name, probability, movement}` — no `id`. A withhold
    loop keyed on `od["id"]` matches nothing here, leaves the refused price
    headlining the dropdown, and looks exactly like a working fix everywhere
    else. The builder keys on the ORM row for this reason.
    """
    short = {WITHHELD_ID, GRADED_CONTROL_ID, 1597363}
    served = _build_search_top_outcomes(
        _market(_legs(only=short, delta_on=WITHHELD_ID)),
        limit=3,
        lean=True,
        withheld={WITHHELD_ID},
    )

    assert served and "id" not in served[0], "lean shape must stay lean"
    refused = [o for o in served if o["name"] == "24,800 or below"]
    assert refused, "the row stays on a ladder this short"
    assert refused[0]["probability"] is None
    assert refused[0]["movement"] is None
    assert served[0]["name"] != "24,800 or below"


# ─────────────────────────────────────────────────────────────────────────────
# Over-withholding, and the pass-through.
# ─────────────────────────────────────────────────────────────────────────────


def test_the_graded_leg_with_the_identical_book_keeps_its_price():
    """Settled means settled: withholding a graded row deletes a result.

    On the SHORT ladder since #8640: this is an open multi-winner board, so its
    graded rungs now sort below every live one, and on the full nineteen legs
    the six live rungs fill the five-row slice. The control is about the row
    being priced, not about where it sorts.
    """
    short = {WITHHELD_ID, GRADED_CONTROL_ID, 1597363}
    served = _build_search_top_outcomes(
        _market(_legs(only=short)), limit=5, lean=False, withheld={WITHHELD_ID}
    )
    control = _by_id(served)[GRADED_CONTROL_ID]
    assert control["probability"] is not None
    assert control["rank"] == 2


def test_no_other_leg_loses_its_price():
    served = _build_search_top_outcomes(
        _market(), limit=5, lean=False, withheld={WITHHELD_ID}
    )
    assert len(served) == 5
    for row in served:
        assert row["probability"] is not None, row["name"]


def test_withheld_none_is_a_pass_through():
    """Every pre-existing caller keeps its behaviour byte for byte."""
    before = _build_search_top_outcomes(_market(), limit=5, lean=False)
    explicit_empty = _build_search_top_outcomes(
        _market(), limit=5, lean=False, withheld=set()
    )
    assert before == explicit_empty
    # And the pass-through still serves the defect, which is what makes the
    # tests above meaningful rather than vacuous: with nobody asking, the
    # refused leg is still the headline at 1.0.
    assert before[0]["id"] == WITHHELD_ID
    assert before[0]["probability"] == pytest.approx(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# The age pip — the same defect arriving by a third door.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_withheld_leg_cannot_date_the_cards_age_pip():
    """#6923's rule, which a withheld row evades.

    `_outcome_prints_a_price` reads the ORM row, where `current_probability` is
    still the refused 1.0 long after the serializer nulled it on the wire. So
    the refused leg — last written 2026-04-13 — would go on setting the `min`
    for a card that prints none of its number.
    """
    short = {WITHHELD_ID, GRADED_CONTROL_ID, 1597363}
    legs = _legs(only=short)
    market = _market(legs)
    served = _build_search_top_outcomes(
        market, limit=5, lean=False, withheld={WITHHELD_ID}
    )
    assert WITHHELD_ID in _by_id(served), "the row is still ON the card"

    stale = _served_prices_as_of(market, served)
    fresh = _served_prices_as_of(market, served, withheld={WITHHELD_ID})

    # Unwithheld, the April row wins the min and claims five months of decay
    # over prices written in May and June.
    assert stale.startswith("2026-04-13")
    # Withheld, the oldest row that actually PRINTS a price dates the card.
    assert fresh.startswith("2026-05-28")


def test_the_age_pip_is_none_when_every_served_row_is_refused():
    """A card with no printed price has no price to be as-of (#6018's contract).

    The consumer renders nothing on None rather than falling back to
    `updated_at` — an empty space is honest and the old pip was not.
    """
    legs = _legs(only={WITHHELD_ID})
    market = _market(legs)
    served = [{"id": WITHHELD_ID}]
    assert _served_prices_as_of(market, served, withheld={WITHHELD_ID}) is None


def test_the_age_pip_is_unchanged_when_nothing_is_withheld():
    market = _market()
    served = _build_search_top_outcomes(market, limit=5, lean=False)
    assert _served_prices_as_of(market, served) == _served_prices_as_of(
        market, served, withheld=set()
    )


# ─────────────────────────────────────────────────────────────────────────────
# The hook, not a fifth spelling.
# ─────────────────────────────────────────────────────────────────────────────


async def test_a_row_that_cannot_answer_keeps_its_price_and_says_so_loudly(caplog):
    """The documented fail-open, verified where firing would do maximum damage.

    The union reads `resolution_source` straight off the outcome. A row double
    without it raised `AttributeError` through an entire search request — 28
    previously-green route tests went red on the first attempt at this arm.

    The direction is the judgement: an unreadable row is left PRICED. Refusing
    it instead would risk withholding a graded row, and withholding a graded row
    deletes a result (#6532).
    """
    from app.routes.events import _search_withheld_price_ids

    blind = SimpleNamespace(id=MARKET_ID, source="kalshi", outcomes=[
        SimpleNamespace(id=WITHHELD_ID, name="24,800 or below"),
    ])
    with caplog.at_level("WARNING"):
        got = await _search_withheld_price_ids(object(), blind)

    assert got == set(), "fail OPEN — the price stays, the row is not refused"
    # Loud: "it returned" is not "it worked". A real row always answers, so this
    # can only fire on a double or on a column renamed out from under the union,
    # and the second is a defect nobody may swallow silently.
    assert any("6993" in r.message or "refusal" in r.message for r in caplog.records)


async def test_the_boundary_does_not_swallow_anything_wider_than_attributeerror():
    """A failing session must not be laundered into "nothing is withheld"."""
    from app.routes.events import _search_withheld_price_ids

    class _AngryDB:
        async def execute(self, *_a, **_k):
            raise RuntimeError("the session is gone")

    legs = _legs(only={WITHHELD_ID})
    with pytest.raises(RuntimeError):
        await _search_withheld_price_ids(_AngryDB(), _market(legs))


def test_search_asks_the_one_shared_union_rather_than_a_local_rule():
    """An arm added to the union must reach this surface too.

    The rail's own docstring is "ONE HELPER, NOT A FIFTH SPELLING". This pins
    that `routes/events.py` imports it rather than re-deriving a local
    predicate — the failure mode being a fifth copy that drifts from the other
    four the next time an arm is added.
    """
    import app.routes.events as events_module

    assert events_module._withheld_price_outcome_ids is not None
    from app.routes.futures import _withheld_price_outcome_ids as canonical

    assert events_module._withheld_price_outcome_ids is canonical
