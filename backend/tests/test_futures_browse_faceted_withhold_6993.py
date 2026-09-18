"""#6993, second arm — ``/browse`` and ``/faceted`` serve the same price refusal.

WHAT A READER SEES, production 2026-09-18, the /search category browser:

  * ``Atlantic 10 Men's Conference Tournament Champion`` — browse serves
    ``top_outcomes[0] = {"id": 222320669, "name": "Dayton", "probability": 0.3}``
    while ``GET /api/futures/59164905`` refuses to price Dayton at all.
  * ``Big Ten: Rushing Yards Leader`` — browse leads ``DeJuan Williams 39%``;
    detail serves ``probability: null`` for that same outcome id.
  * ``How low will the Nasdaq-100 get in 2026?`` (109485) — browse AND faceted
    lead ``24,800 or below 1.0``; detail serves ``null`` for outcome 1597367.

THIS IS THE WORST OF THE THREE SITES, not the least. ``CompactMarketCard``
renders ``top_outcomes[0]`` AND NOTHING ELSE — the comment above the browse
serializer says so in those words — so here the refused number is not one row in
a table (the detail route's case) and not one rung in a ladder (the group
route's case): it is the market's ENTIRE one-line description. And ``/faceted``
is what the iOS client reads (``APIClient.swift``), so this arm is the only one
that reaches the native surface at all.

MEASURED BEFORE-STATE, production 2026-09-18. Of 27 open Kalshi browse-eligible
markets sampled evenly across the 1,000+ that hold a leg matching the candidate
book shape, **6 served a withheld leg inside the rendered top-3 slice and 2 of
those had it at rank 1** (``artifacts-lane1b-344/BEFORE-route-diff-sample.json``).

THE ARMS THEMSELVES ARE NOT RE-ASSERTED HERE, for the reason the sibling file
(``test_futures_group_withhold_6993.py``) gives at length: which legs are refused
belongs to ``_unsupported_price_outcome_ids`` and its three siblings, each with
its own guards. These tests stub the composed union and assert the WIRING — that
whatever the union answers for a market, every route that serves that market's
prices applies it.

THE FIXTURE IS THE SPECIMEN'S OWN STORED ROWS, read off production 2026-09-18 via
``db-query`` against ``futures_outcomes`` for market 59164905 — all fourteen legs,
verbatim, not values chosen to make anything fire.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS

#: ``(id, name, external_id, current_probability, yes_bid, yes_ask)`` — the
#: fourteen stored legs of market 59164905, verbatim. Every one is ungraded
#: (``resolution_source IS NULL``) and none carries a 24h delta.
#:
#: 🪤 ELEVEN OF THE FOURTEEN QUOTE AN ASK AGAINST A ``0.0000`` BID and only the
#: two the sweep found are refused here; the field sums to 2.62. Pinning all
#: fourteen — rather than the two — is what stops a later reader taking the
#: twelve survivors for a leak.
SPECIMEN_LEGS = (
    (222320669, "Dayton", "KXNCAAMBA10-27-DAY", 0.300000, 0.0000, 0.3000),
    (222320670, "George Washington", "KXNCAAMBA10-27-GW", 0.250000, 0.0000, 0.2500),
    (222320671, "VCU", "KXNCAAMBA10-27-VCU", 0.250000, 0.1000, 0.4000),
    (222320672, "George Mason", "KXNCAAMBA10-27-GMU", 0.220000, 0.0000, 0.2200),
    (222320673, "Richmond", "KXNCAAMBA10-27-RICH", 0.190000, 0.0000, 0.1900),
    (222320674, "Davidson", "KXNCAAMBA10-27-DAV", 0.180000, 0.0000, 0.1800),
    (222320675, "Saint Louis", "KXNCAAMBA10-27-SLU", 0.180000, 0.0300, 0.3300),
    (222320676, "St. Bonaventure", "KXNCAAMBA10-27-SBON", 0.180000, 0.0000, 0.1800),
    (222320677, "Fordham", "KXNCAAMBA10-27-FOR", 0.170000, 0.0000, 0.1700),
    (222320678, "Saint Joseph's", "KXNCAAMBA10-27-JOES", 0.170000, 0.0000, 0.1700),
    (222320679, "Duquesne", "KXNCAAMBA10-27-DUQ", 0.160000, 0.0000, 0.1600),
    (222320680, "La Salle", "KXNCAAMBA10-27-LAS", 0.160000, 0.0000, 0.1600),
    (222320681, "Loyola Chicago", "KXNCAAMBA10-27-LCHI", 0.160000, 0.0000, 0.1600),
    (222320682, "Rhode Island", "KXNCAAMBA10-27-URI", 0.160000, 0.0000, 0.1600),
)

#: The rank-1 leg. Browse printed it as the card's whole subtitle — "Dayton 30%"
#: — while the market's own page refused to price it.
WITHHELD_ID = 222320669

#: The rank-2 leg, refused by the same union on the same market. Present so the
#: slice tests have a second refusal to displace rather than one.
WITHHELD_ID_2 = 222320670

MARKET_ID = 59164905

#: The leg with the best TWO-SIDED book (0.10/0.40). It is what should lead the
#: card once the two ask-only legs above it are refused.
FIRST_SURVIVOR_ID = 222320671


def _legs(delta_on=None):
    """The fourteen stored legs. ``delta_on`` puts a 24h delta on one id.

    No leg on this specimen carries a ``probability_change_24h`` in production,
    so the ``movement`` assertion below manufactures one rather than claiming a
    live population it does not have — see ``test_the_movement_twin_falls``.
    """
    return [
        SimpleNamespace(
            id=oid,
            name=name,
            external_id=ext,
            current_probability=prob,
            current_yes_bid=bid,
            current_yes_ask=ask,
            current_american_odds=110,
            probability_change_24h=0.05 if oid == delta_on else None,
            opening_probability=0.5,
            is_winner=False,
            resolution_source=None,
            last_updated=None,
        )
        for oid, name, ext, prob, bid, ask in SPECIMEN_LEGS
    ]


def _market(legs=None):
    return SimpleNamespace(
        id=MARKET_ID,
        name="Atlantic 10 Men's Conference Tournament Champion",
        source="kalshi",
        external_id="KXNCAAMBA10-27",
        status="open",
        event_id=None,
        market_type="winner",
        market_tier=3,
        llm_sport_category="basketball",
        mutually_exclusive=True,
        resolution_date=None,
        market_metadata=None,
        market_tags=[],
        image_url=None,
        hook_description=None,
        outcomes=_legs() if legs is None else legs,
    )


class _BrowseDB:
    """Answers the single windowed ``select(FuturesMarket, count() OVER ())``."""

    def __init__(self, markets):
        self._rows = [(m, len(markets)) for m in markets]

    async def execute(self, *_a, **_k):
        rows = self._rows

        class _Result:
            def unique(self):
                return self

            def all(self):
                return rows

            def scalar(self):
                return len(rows)

        return _Result()


class _FacetedDB:
    """Answers faceted's three reads in order: count, data, facet rows."""

    def __init__(self, markets):
        self._markets = markets

    async def execute(self, *_a, **_k):
        markets = self._markets

        class _Scalars:
            def unique(self):
                return self

            def all(self):
                return markets

        class _Result:
            def scalar(self):
                # Read 1, the COUNT.
                return len(markets)

            def scalars(self):
                # Read 2, the page of markets.
                return _Scalars()

            def all(self):
                # Read 3, the facet rows. Faceting is not what this file tests
                # and an empty facet map is a valid payload, so it stays empty.
                return []

        return _Result()


def _stub_union(monkeypatch, ids):
    """Pin the composed union so these tests assert the WIRING, not the arms."""
    import app.routes.futures as fr

    async def _ids(_db, _market):
        return set(ids)

    monkeypatch.setattr(fr, "_withheld_price_outcome_ids", _ids)


async def _browse(monkeypatch, withheld, legs=None):
    import app.routes.futures as fr

    _stub_union(monkeypatch, withheld)
    payload = await fr.browse_futures(
        category=None, q=None, limit=50, offset=0, db=_BrowseDB([_market(legs)])
    )
    return payload["items"][0]


async def _faceted(monkeypatch, withheld, legs=None):
    import app.routes.futures as fr

    _stub_union(monkeypatch, withheld)
    payload = await fr.faceted_futures_search(
        tags=None,
        sport=None,
        category=None,
        stakes=None,
        narrative=None,
        audience=None,
        q=None,
        sort=None,
        page=1,
        per_page=25,
        db=_FacetedDB([_market(legs)]),
    )
    return payload["markets"][0]


def _by_id(item):
    return {o["id"]: o for o in item["top_outcomes"]}


class TestBrowseAppliesTheRefusal:
    @pytest.mark.asyncio
    async def test_the_refused_leg_does_not_lead_the_card(self, monkeypatch):
        """🔴 THE DEFECT, PINNED, IN THE ONLY SLOT THIS PAYLOAD'S CONSUMER RENDERS.

        ``CompactMarketCard`` prints ``top_outcomes[0]`` and nothing else, so a
        withheld leg at rank 1 is not a wasted row — it is the whole card. Before
        this change the card read "Dayton 30%" against a market page that refused
        to price Dayton.
        """
        item = await _browse(monkeypatch, {WITHHELD_ID, WITHHELD_ID_2})

        assert item["top_outcomes"][0]["id"] == FIRST_SURVIVOR_ID, (
            "the card must lead with a leg we are willing to price; "
            f"got {item['top_outcomes'][0]}"
        )

    @pytest.mark.asyncio
    async def test_a_refused_leg_that_still_fits_is_served_with_no_number(
        self, monkeypatch
    ):
        """Sinking is not enough — a refused leg inside the slice carries no price.

        With one refusal on a fourteen-leg field the withheld row sinks out of the
        top 3 entirely, so this drives the case where the slice is the whole list:
        the refusal has to survive serialization, not just ordering.
        """
        item = await _browse(monkeypatch, {WITHHELD_ID}, legs=_legs()[:2])

        served = _by_id(item)
        assert served[WITHHELD_ID]["probability"] is None
        assert (
            served[WITHHELD_ID_2]["probability"] == 0.25
        ), "only the refused leg loses its price"

    @pytest.mark.asyncio
    async def test_the_movement_twin_falls(self, monkeypatch):
        """🪤 THE RENAMED FIELD. ``movement`` IS ``probability_change_24h`` HERE.

        ``WITHHELD_PRICE_FIELDS`` is keyed on presence so it covers a price field a
        payload gains later — but not one the payload SPELLS DIFFERENTLY, and
        browse/faceted spell the 24h delta ``movement``. A loop over the three
        original names walks straight past it and serves
        ``{"probability": null, "movement": 0.05}``: the delta of the number we
        just refused to state, which is the #5539 mistake in a second costume.

        NO LIVE SPECIMEN. Every leg of market 59164905 stores a NULL delta, so the
        delta here is manufactured. This clause is closed by rule, not because a
        reader was measured meeting it.
        """
        item = await _browse(
            monkeypatch, {WITHHELD_ID}, legs=_legs(delta_on=WITHHELD_ID)[:2]
        )

        served = _by_id(item)
        assert (
            served[WITHHELD_ID]["movement"] is None
        ), "a delta measured from the withheld price restates it"
        assert served[WITHHELD_ID]["probability"] is None

    @pytest.mark.asyncio
    async def test_the_row_is_withheld_not_dropped(self, monkeypatch):
        """Withheld, not skipped: the leg keeps its name, its id and its place."""
        item = await _browse(monkeypatch, {WITHHELD_ID}, legs=_legs()[:2])

        assert WITHHELD_ID in _by_id(item), "the refused leg must still be served"
        assert _by_id(item)[WITHHELD_ID]["name"] == "Dayton"
        assert item["outcome_count"] == 2, "the count is of rows, not of prices"

    @pytest.mark.asyncio
    async def test_the_other_twelve_are_untouched(self, monkeypatch):
        """The refusal is surgical — the survivors keep the prices they had."""
        item = await _browse(monkeypatch, {WITHHELD_ID, WITHHELD_ID_2})

        assert [(o["id"], o["probability"]) for o in item["top_outcomes"]] == [
            (222320671, 0.25),
            (222320672, 0.22),
            (222320673, 0.19),
        ]

    @pytest.mark.asyncio
    async def test_an_empty_union_changes_nothing(self, monkeypatch):
        """🪤 THE FAIL-OPEN DIRECTION. No refusals ⇒ byte-identical to before.

        This is the assertion that fails if the sort key or the serializer starts
        nulling on something other than membership of the union.
        """
        item = await _browse(monkeypatch, set())

        assert [(o["id"], o["probability"]) for o in item["top_outcomes"]] == [
            (222320669, 0.3),
            (222320670, 0.25),
            (222320671, 0.25),
        ]


class TestFacetedAppliesTheRefusal:
    @pytest.mark.asyncio
    async def test_the_refused_leg_does_not_lead_the_native_card(self, monkeypatch):
        """``/api/futures/faceted`` is the iOS client's read (``APIClient.swift``).

        Faceted slices ``[:3]`` straight off the sort, so an unfixed sort key does
        not merely mis-order — it spends a slot on a row it then renders blank.
        """
        item = await _faceted(monkeypatch, {WITHHELD_ID, WITHHELD_ID_2})

        assert item["top_outcomes"][0]["id"] == FIRST_SURVIVOR_ID
        assert len(item["top_outcomes"]) == 3, "the slice still yields three rows"

    @pytest.mark.asyncio
    async def test_a_refused_leg_inside_the_slice_carries_no_price(self, monkeypatch):
        item = await _faceted(monkeypatch, {WITHHELD_ID}, legs=_legs()[:2])

        served = _by_id(item)
        assert served[WITHHELD_ID]["probability"] is None
        assert served[WITHHELD_ID_2]["probability"] == 0.25

    @pytest.mark.asyncio
    async def test_the_movement_twin_falls(self, monkeypatch):
        item = await _faceted(
            monkeypatch, {WITHHELD_ID}, legs=_legs(delta_on=WITHHELD_ID)[:2]
        )

        assert _by_id(item)[WITHHELD_ID]["movement"] is None

    @pytest.mark.asyncio
    async def test_an_empty_union_changes_nothing(self, monkeypatch):
        item = await _faceted(monkeypatch, set())

        assert [(o["id"], o["probability"]) for o in item["top_outcomes"]] == [
            (222320669, 0.3),
            (222320670, 0.25),
            (222320671, 0.25),
        ]


class TestTheRuleStaysInOnePlace:
    def test_movement_is_a_withheld_price_field(self):
        """The renamed spelling belongs to the tuple, not to two call sites.

        If a later reader trims this back to the three original names, the two
        ``movement`` tests above fail and say why — but this one names the reason
        without needing a route.
        """
        assert "movement" in WITHHELD_PRICE_FIELDS
        for field in ("probability", "american_odds", "probability_change_24h"):
            assert field in WITHHELD_PRICE_FIELDS, "no spelling may be dropped"

    def test_neither_route_re_inlines_the_union(self):
        """🪤 ANTI-DRIFT. Four routes, one hook — the whole point of #6993.

        The union exists so that adding a fifth arm reaches every surface that
        serves a price. A route that re-derives the arms locally passes every
        behavioural test above and silently opts out of the next arm.
        """
        import inspect

        import app.routes.futures as fr

        for fn in (fr.browse_futures, fr.faceted_futures_search):
            src = inspect.getsource(fn)
            assert (
                "_withheld_price_outcome_ids" in src
            ), f"{fn.__name__} must ask the composed union"
            for arm in (
                "_unsupported_price_outcome_ids",
                "_refuted_midpoint_outcome_ids",
                "_book_refuted_outcome_ids",
                "_empty_book_outcome_ids",
            ):
                assert (
                    arm not in src
                ), f"{fn.__name__} re-inlines {arm} instead of calling the union"
