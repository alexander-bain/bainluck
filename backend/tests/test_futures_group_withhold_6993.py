"""#6993 — the futures GROUP route serves the same refusal the DETAIL route does.

WHAT A READER SAW, production 2026-09-18, ``/futures/109485`` ("How low will the
Nasdaq-100 get in 2026?") at 390px in one screenshot:

  * the ``# OR BELOW`` ladder drew the rung **``≤ 24800   100%``** with a full
    green bar, and
  * the "All Outcomes" table BELOW IT ON THE SAME SCREEN folded that identical
    outcome away into "More outcomes (1)", because its price is withheld.

One outcome (id ``1597367``, stored ``current_probability`` 1.000000 on a
``0.0000/1.0000`` book), two answers, one screen. ``GET /api/futures/109485``
served ``probability: None`` for it while ``GET /api/futures/groups/
kalshi:KXNASDAQ100MINY-26DEC31H1600`` served ``1.0`` in the same minute.

WHY IT WAS A BYPASS AND NOT A DUPLICATE. The page fetches BOTH payloads
(``app/futures/[id]/page.tsx`` — ``fetchFuturesMarket`` and ``fetchFuturesGroup``)
and builds the threshold ladder from the GROUP one. ``ownLadderRungs`` returns
``[]`` whenever ``thresholdEntries`` is non-empty, so for a threshold-shaped
market the group payload's ladder is the ONLY ladder that draws — the withheld
detail payload never reaches the rungs at all. The refusal was not merely served
twice and inconsistently; on this class of market it was not served.

THE ARMS THEMSELVES ARE NOT RE-ASSERTED HERE. Which legs are refused is
``_unsupported_price_outcome_ids`` and its three siblings' business, each with its
own guards (#5611, #5876, #6532, #6757); on the specimen the selecting arm is the
trade read, which is why these tests stub the union and assert the WIRING. The
property this file owns is narrower and is the whole of #6993: whatever the union
answers for a market, both routes that serve that market's prices apply it.

THE FIXTURE IS THE SPECIMEN'S OWN STORED ROWS, read off production 2026-09-18 via
``db-query`` against ``futures_outcomes`` for market 109485 — not values chosen to
make anything fire.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS

#: ``(id, name, current_probability, yes_bid, yes_ask, resolution_source)`` — the
#: nineteen stored legs of market 109485, verbatim.
#:
#: 🪤 SEVEN LEGS SHARE THE ``0.0000/1.0000`` BOOK AND ONLY ONE IS REFUSED. The
#: others carry a recorded Kalshi trade, which is rule 2 ("trade evidence beats a
#: wide book") doing its job. Pinning all nineteen here — rather than the one —
#: is what stops a later reader reading the six survivors as a leak.
SPECIMEN_LEGS = (
    (69678691, "22,000 or below", 0.100000, 0.0700, 0.1300, "api_settlement"),
    (69678690, "22,200 or below", 0.080000, 0.0500, 0.1100, "api_settlement"),
    (69678689, "22,400 or below", 0.110000, 0.0700, 0.1500, "api_settlement"),
    (69678688, "22,600 or below", 0.185000, 0.1400, 0.2300, "api_settlement"),
    (69678687, "22,800 or below", 0.165000, 0.0800, 0.2500, "api_settlement"),
    (1597363, "23,000 or below", 0.995000, 0.9910, 0.9990, "api_settlement"),
    (1597362, "23,200 or below", 0.985500, 0.9710, 1.0000, "api_settlement"),
    (1597361, "23,400 or below", 0.985000, 0.9710, 0.9990, "api_settlement"),
    (1597360, "23,600 or below", 0.910500, 0.8210, 1.0000, "api_settlement"),
    (1597366, "23,800 or below", 0.990000, 0.0000, 1.0000, "api_settlement"),
    (1597365, "24,000 or below", 0.950000, 0.0000, 1.0000, "api_settlement"),
    (1597364, "24,200 or below", 0.760000, 0.0000, 1.0000, "api_settlement"),
    (1597371, "24,400 or below", 0.800000, 0.0000, 1.0000, None),
    (1597372, "24,600 or below", 0.880000, 0.0000, 1.0000, None),
    (1597367, "24,800 or below", 1.000000, 0.0000, 1.0000, None),
    (1597368, "25,000 or below", 0.860000, 0.0000, 1.0000, None),
    (1597369, "25,200 or below", 0.820000, 0.0000, 1.0000, None),
    (1597373, "25,400 or below", 0.880000, 0.0000, 1.0000, None),
    (1597370, "25,500 or below", 0.940000, 0.0000, 1.0000, None),
)

#: The leg production withheld on the detail route and served at 1.0 on the group
#: route — the rung the reader met as ``≤ 24800  100%``.
WITHHELD_ID = 1597367

GROUP_ID = "kalshi:KXNASDAQ100MINY-26DEC31H1600"


def _legs():
    return [
        SimpleNamespace(
            id=oid,
            name=name,
            external_id=f"kx-{oid}",
            current_probability=prob,
            current_yes_bid=bid,
            current_yes_ask=ask,
            current_american_odds=110,
            rank=None,
            rank_change_24h=None,
            probability_change_24h=None,
            opening_probability=0.5,
            opening_american_odds=100,
            is_winner=src == "api_settlement",
            resolution_source=src,
            last_updated=None,
        )
        for oid, name, prob, bid, ask, src in SPECIMEN_LEGS
    ]


def _market(legs=None):
    return SimpleNamespace(
        id=109485,
        name="How low will the Nasdaq-100 get in 2026?",
        description=None,
        category="economics",
        source="kalshi",
        external_id="KXNASDAQ100MINY-26DEC31H1600",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type="quantity",
        market_tier=3,
        llm_sport_category="economics",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=GROUP_ID,
        group_type="threshold",
        group_position=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=_legs() if legs is None else legs,
    )


class _DB:
    """Answers the one ``select(FuturesMarket)`` ``get_group`` issues."""

    def __init__(self, markets):
        self._markets = markets

    async def execute(self, *_a, **_k):
        markets = self._markets

        class _Scalars:
            def all(self):
                return markets

        class _Result:
            def scalars(self):
                return _Scalars()

            def scalar_one_or_none(self):
                return markets[0] if markets else None

        return _Result()


def _stub_union(monkeypatch, ids):
    """Pin the composed union so these tests assert the WIRING, not the arms."""
    import app.routes.futures as fr

    async def _ids(_db, _market):
        return set(ids)

    monkeypatch.setattr(fr, "_withheld_price_outcome_ids", _ids)


def _served(group, market_id=109485):
    market = next(m for m in group["markets"] if m["id"] == market_id)
    return {o["id"]: o for o in market["outcomes"]}


class TestTheGroupRouteApplies:
    @pytest.mark.asyncio
    async def test_the_refused_leg_is_served_with_no_number(self, monkeypatch):
        """🔴 THE DEFECT, PINNED. ``1.0`` becomes ``None`` on the group payload."""
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        served = _served(group)
        assert (
            served[WITHHELD_ID]["probability"] is None
        ), "the leg the detail route refuses may not be priced by the group route"

    @pytest.mark.asyncio
    async def test_the_american_twin_falls_with_it(self, monkeypatch):
        """🪤 A refusal that leaves the odds column is cosmetic.

        ``american_odds`` is the same number in another notation — the exact
        reconstruction ``WITHHELD_PRICE_FIELDS`` exists to prevent. This is the
        assertion that fails if someone nulls ``probability`` alone.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        assert _served(group)[WITHHELD_ID]["american_odds"] is None

    @pytest.mark.asyncio
    async def test_every_other_leg_keeps_its_stored_price(self, monkeypatch):
        """The fix withholds ONE row, not a category.

        Eighteen legs — including the six sharing the refused leg's empty book —
        must be untouched, or this is a blanket deletion wearing a fix's clothes.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        served = _served(group)
        survivors = {
            oid: prob
            for oid, _n, prob, _b, _a, _s in SPECIMEN_LEGS
            if oid != WITHHELD_ID
        }
        assert len(survivors) == 18
        for oid, prob in survivors.items():
            assert served[oid]["probability"] == pytest.approx(prob), oid

    @pytest.mark.asyncio
    async def test_nothing_is_dropped__withheld_not_skipped(self, monkeypatch):
        """The row stays and keeps its name; only the number goes.

        Dropping it would answer a question nobody asked and would silently
        shorten a cumulative ladder — the contract the detail arm already keeps.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        served = _served(group)
        assert len(served) == len(SPECIMEN_LEGS) == 19
        assert served[WITHHELD_ID]["name"] == "24,800 or below"

    @pytest.mark.asyncio
    async def test_the_refused_leg_does_not_lead_the_board(self, monkeypatch):
        """🪤 ORDERING READ THE COLUMN THE REFUSAL JUST DELETED.

        The specimen's withheld leg is a stored ``1.0`` — the highest value in the
        market. Sorting on the raw column and nulling afterwards seats it FIRST
        with no number beside it, which is the withhold announcing itself as the
        leader. It must sort as unpriced.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        order = [o["id"] for o in group["markets"][0]["outcomes"]]
        assert order[0] != WITHHELD_ID
        assert order[-1] == WITHHELD_ID, "an unpriced row sinks to the bottom"

    @pytest.mark.asyncio
    async def test_the_ladder_rung_the_reader_meets_carries_no_number(
        self, monkeypatch
    ):
        """🔴 THE READER'S ACTUAL PATH — ``threshold_groups``, not ``markets``.

        This is the payload the page turns into rungs (``buildThresholdRungs``),
        and for a threshold-shaped market it is the only ladder drawn. If the
        withhold reached ``markets`` but not here, the screenshot would be
        unchanged and every other test in this file would still pass.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, {WITHHELD_ID})
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        rungs = [
            r
            for outs in group["threshold_groups"].values()
            for r in outs
            if r["outcome_id"] == WITHHELD_ID
        ]
        assert rungs, "the specimen's rung must still be ON the ladder"
        assert all(
            r["probability"] is None for r in rungs
        ), "≤ 24800 may not draw 100% when the detail route refuses the price"

    @pytest.mark.asyncio
    async def test_a_market_with_nothing_refused_is_untouched(self, monkeypatch):
        """The fail-open direction: an empty union changes no number.

        A withholding rule that fires on the empty set would blank the site, so
        the no-op case is asserted rather than assumed.
        """
        import app.routes.futures as fr

        _stub_union(monkeypatch, set())
        group = await fr.get_group(GROUP_ID, _DB([_market()]))

        served = _served(group)
        for oid, _n, prob, _b, _a, _s in SPECIMEN_LEGS:
            assert served[oid]["probability"] == pytest.approx(prob), oid


class TestTheTwoRoutesAgree:
    @pytest.mark.asyncio
    async def test_detail_and_group_serve_one_answer_for_one_leg(self, monkeypatch):
        """🔴 THE PROPERTY #6993 IS ABOUT, asserted across both handlers.

        Every other test here could pass while the two routes still disagreed —
        they only read the group side. This one drives BOTH on the same market
        with the same arms and compares leg for leg, which is the thing a reader
        actually met on one screen.
        """
        import app.routes.futures as fr

        market = _market()

        async def _no_ids(_db, _market):
            return set()

        async def _empty_book(_db, _market):
            return {WITHHELD_ID}

        async def _no_sources(_db, _market_id, _outcome_ids):
            return [], []

        # Three arms silent, one firing — so an agreement here cannot come from
        # both routes happening to refuse nothing.
        monkeypatch.setattr(fr, "_unsupported_price_outcome_ids", _empty_book)
        monkeypatch.setattr(fr, "_refuted_midpoint_outcome_ids", _no_ids)
        monkeypatch.setattr(fr, "_book_refuted_outcome_ids", lambda _m: set())
        monkeypatch.setattr(fr, "_empty_book_outcome_ids", lambda _m: set())
        monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

        detail = await fr.get_futures_market(109485, _DB([market]))
        group = await fr.get_group(GROUP_ID, _DB([market]))

        detail_prices = {o["id"]: o["probability"] for o in detail["outcomes"]}
        group_prices = {
            o["id"]: o["probability"] for o in group["markets"][0]["outcomes"]
        }

        assert detail_prices.keys() == group_prices.keys()
        assert (
            detail_prices == group_prices
        ), "the two payloads the event page fetches together must not disagree"
        assert detail_prices[WITHHELD_ID] is None
        assert detail["prices_withheld"] == 1

    @pytest.mark.asyncio
    async def test_the_group_route_asks_the_union_and_does_not_re_spell_it(
        self, monkeypatch
    ):
        """One hook, so a fifth arm reaches both routes the day it lands.

        The #6960 lesson applied before the second copy hardens: if someone
        inlines the four-arm union back into either handler, the routes can drift
        again and this fails. ``_withheld_price_outcome_ids`` is stubbed to a
        sentinel no arm could produce, so a handler that composed its own union
        would ignore it.
        """
        import app.routes.futures as fr

        sentinel = {WITHHELD_ID, 1597368}
        _stub_union(monkeypatch, sentinel)

        group = await fr.get_group(GROUP_ID, _DB([_market()]))
        served = _served(group)

        blanked = {oid for oid, o in served.items() if o["probability"] is None}
        assert blanked == sentinel

    def test_the_union_composes_all_four_arms(self):
        """The helper is the composition, not a rename of one arm.

        Guards the extraction itself: a future edit that drops an arm from
        ``_withheld_price_outcome_ids`` silently un-withholds a whole class on
        BOTH routes at once, which is exactly the blast radius the shared hook
        buys.
        """
        import inspect

        import app.routes.futures as fr

        src = inspect.getsource(fr._withheld_price_outcome_ids)
        for arm in (
            "_unsupported_price_outcome_ids",
            "_refuted_midpoint_outcome_ids",
            "_book_refuted_outcome_ids",
            "_empty_book_outcome_ids",
        ):
            assert arm in src, f"{arm} dropped out of the shared union"


class TestTheConstantIsTheContract:
    def test_the_group_route_nulls_every_withheld_price_field(self):
        """🪤 A hand-listed pair of keys goes stale the day a field is added.

        ``WITHHELD_PRICE_FIELDS`` is the list of "restatements of the refused
        price"; the group route iterates it rather than naming keys, so a field
        added to that tuple is covered on this route without a second edit.
        """
        import inspect

        import app.routes.futures as fr

        src = inspect.getsource(fr.get_group)
        assert (
            "WITHHELD_PRICE_FIELDS" in src
        ), "the group route must iterate the constant, not hand-list keys"
        assert "probability" in WITHHELD_PRICE_FIELDS
        assert "american_odds" in WITHHELD_PRICE_FIELDS
