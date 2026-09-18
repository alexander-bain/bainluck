"""#6757 — the futures DETAIL route withholds an empty book's midpoint, like its siblings.

WHAT A READER SAW. ``/futures/57777176`` ("NBA: Steph Curry Next Team") printed a
confident percentage against all 30 teams and not one was a traded price: sixteen
clubs at **48%**, a ladder summing to **1112.5%**, every row written in one batch
six weeks earlier. ``/futures/110297`` answered a real election with "Opposition
49.7% / Government Alliance 49.1%", and ``/futures/109681`` priced five mutually
exclusive CPI rungs at 50% each.

WHY THE THREE SHIPPED ARMS WERE INERT, asserted here and not asserted-about:
``price_is_unsupported`` and ``midpoint_refuted_by_last_trade`` screen on
``market.source`` and on trade evidence, and ``price_refuted_by_live_book`` asks
whether the served price sits OUTSIDE its own book — a midpoint is inside
``[bid, ask]`` by construction, so it can never fire. The rule that does fire had
exactly one call site in this module, inside ``grouped_feed``.

THE FIXTURE IS THE SPECIMEN'S OWN STORED ROWS, read off production 2026-09-17 via
``db-query`` (``futures_outcomes`` for the ladder, ``futures_odds_snapshots`` for
the chart) — not values chosen to make the predicate fire.
"""

from types import SimpleNamespace

import pytest

from app.utils.feed_market_quality import is_empty_book_midpoint
from app.utils.futures_unsupported_price import WITHHELD_PRICE_FIELDS

#: ``(name, probability, yes_bid, yes_ask, withheld)`` — market 57777176's thirty
#: stored legs, collapsed to one row per distinct book shape plus its count.
#:
#: 🪤 THE EXPECTATION IS NOT "ALL THIRTY". The shipped predicate needs a spread of
#: at least ``EMPTY_BOOK_MIN_SPREAD`` (0.90), so it reaches the 0.01/0.95 and
#: 0.01/0.94 books and deliberately NOT the 0.01/0.49 or 0.01/0.40 ones, whose asks
#: still bound the number. Those legs keep printing and the ladder still sums past
#: 100%. Widening that bound is a separate decision with its own population to
#: count — a strict gate is also a safety net — and pinning the partial result here
#: is what stops a later reader mistaking the residual for a regression.
SPECIMEN_BOOK_SHAPES = (
    ("the 0.01/0.95 block", 15, 0.480, 0.0100, 0.9500, True),
    ("Milwaukee, 0.01/0.94", 1, 0.475, 0.0100, 0.9400, True),
    ("Golden State, a real bid", 1, 0.740, 0.5200, 0.9600, False),
    ("San Antonio, ask 0.49", 1, 0.250, 0.0100, 0.4900, False),
    ("the 0.01/0.40 block", 12, 0.205, 0.0100, 0.4000, False),
)


def _specimen_legs():
    """The thirty legs of 57777176, one reader for every test in this file.

    One expansion of :data:`SPECIMEN_BOOK_SHAPES` so a fixture and an expectation
    can never be built from two different filters.
    """
    legs = []
    for label, count, p, bid, ask, withheld in SPECIMEN_BOOK_SHAPES:
        for i in range(count):
            legs.append((f"{label} #{i + 1}", p, bid, ask, withheld))
    return legs


def _market(source="polymarket", legs=None, status="open"):
    return SimpleNamespace(
        id=57777176,
        name="NBA: Steph Curry Next Team",
        description=None,
        category="championship",
        source=source,
        external_id="curry-next-team",
        status=status,
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=5,
        llm_sport_category="basketball",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata=None,
        outcomes=[
            SimpleNamespace(
                id=i,
                name=name,
                external_id=f"curry-{i}",
                current_probability=p,
                current_yes_bid=bid,
                current_yes_ask=ask,
                current_american_odds=110,
                rank=i,
                rank_change_24h=None,
                probability_change_24h=0.01,
                opening_probability=None,
                opening_american_odds=None,
                is_winner=False,
                resolution_source=None,
                last_updated=None,
            )
            for i, (name, p, bid, ask, _w) in enumerate(_specimen_legs(), start=1)
        ]
        if legs is None
        else legs,
    )


class TestTheArm:
    def test_it_selects_exactly_the_empty_book_legs(self):
        from app.routes.futures import _empty_book_outcome_ids

        market = _market()
        expected = {
            o.id
            for o, (_n, _p, _b, _a, withheld) in zip(market.outcomes, _specimen_legs())
            if withheld
        }
        assert len(expected) == 16, "15 at 0.01/0.95 plus Milwaukee at 0.01/0.94"
        assert _empty_book_outcome_ids(market) == expected

    def test_a_bounded_book_is_left_alone_at_both_venues(self):
        """🪤 The arm screens on no source, so BOTH venues are asserted.

        The three arms beside it are venue-scoped and a reader of this file could
        reasonably assume this one is too. It is not, and that is the property the
        union comment on the route now turns on.
        """
        from app.routes.futures import _empty_book_outcome_ids

        for source in ("kalshi", "polymarket"):
            bounded = [
                SimpleNamespace(
                    id=1,
                    name="Golden State Warriors",
                    external_id="gsw",
                    current_probability=0.740,
                    current_yes_bid=0.5200,
                    current_yes_ask=0.9600,
                    current_american_odds=110,
                    rank=1,
                    rank_change_24h=None,
                    probability_change_24h=None,
                    opening_probability=None,
                    opening_american_odds=None,
                    is_winner=False,
                    resolution_source=None,
                    last_updated=None,
                )
            ]
            assert _empty_book_outcome_ids(_market(source, bounded)) == set()

    def test_a_row_without_book_columns_is_passed_over_and_not_a_500(self):
        """🪤 THE FAIL-OPEN, PINNED IN BOTH DIRECTIONS.

        This arm runs on every ``/api/futures/{id}`` request, so an object without
        the book columns must leave the price alone rather than raise — the same
        choice ``_book_refuted_outcome_ids`` makes beside it. The second assertion
        is the one that matters: a fail-open can go inert without anybody noticing,
        so the full-shaped row is asserted to still fire in the same test. If a
        column is ever renamed, THAT is what fails.
        """
        from app.routes.futures import _empty_book_outcome_ids

        bookless = SimpleNamespace(id=1, name="no columns at all")
        assert _empty_book_outcome_ids(_market(legs=[bookless])) == set()

        full = SimpleNamespace(
            id=1,
            name="the same row, with its book",
            current_probability=0.480,
            current_yes_bid=0.0100,
            current_yes_ask=0.9500,
            resolution_source=None,
        )
        assert _empty_book_outcome_ids(_market(legs=[full])) == {1}

    def test_it_delegates_and_does_not_re_spell_the_rule(self):
        """One price policy, one definition — #6757's entire shape.

        A second, differently-spelled copy of the empty-book test is the thing this
        change exists to avoid: the rule already ran three feet away in
        ``grouped_feed``. If someone inlines a comprehension here, the route and the
        strip can drift, which is the defect being fixed.
        """
        import app.routes.futures as futures_route
        import app.utils.feed_market_quality as fmq

        assert futures_route.is_empty_book_midpoint is fmq.is_empty_book_midpoint

        leg = SimpleNamespace(
            current_probability=0.480,
            current_yes_bid=0.0100,
            current_yes_ask=0.9500,
        )
        assert futures_route._leg_prices_an_empty_book(leg) is is_empty_book_midpoint(
            0.480, 0.0100, 0.9500
        )


class TestTheLadder:
    """``/api/futures/{id}`` — what the reader is actually handed."""

    def test_the_withheld_price_reaches_the_reader_as_null_and_is_counted(self):
        from app.routes.futures import _empty_book_outcome_ids, _format_market_detail

        market = _market()
        withheld = _empty_book_outcome_ids(market)
        detail = _format_market_detail(market, None, withheld)

        assert detail["prices_withheld"] == len(withheld) == 16
        for row in detail["outcomes"]:
            if row["id"] in withheld:
                for field in WITHHELD_PRICE_FIELDS:
                    assert field in row, f"{field} must be PRESENT and null, not omitted"
                    assert row[field] is None
            else:
                assert row["probability"] is not None, row["name"]

    def test_the_sixteen_fabricated_forty_eights_stop_being_served(self):
        """🔴 The reader-visible claim of the ship, stated as the reader meets it."""
        from app.routes.futures import _empty_book_outcome_ids, _format_market_detail

        market = _market()
        before = _format_market_detail(market, None, set())
        after = _format_market_detail(
            _market(), None, _empty_book_outcome_ids(_market())
        )

        def _at(detail, value):
            return sum(
                1 for o in detail["outcomes"] if o["probability"] == pytest.approx(value)
            )

        assert _at(before, 0.48) == 15 and _at(before, 0.475) == 1
        assert _at(after, 0.48) == 0 and _at(after, 0.475) == 0

    def test_the_survivors_keep_their_raw_prices_and_the_leader_does_not_move(self):
        """🪤 SHRINKING THE SUM COULD HAVE RESCALED THE WHOLE BOARD, and does not.

        ``normalize_display_probs`` squeezes a mutually-exclusive field whose raw
        sum is over 105 but bails above ``_FIELD_SUM_MAX`` (1.60), leaving it raw.
        This ladder sums to 11.125 before the fix and 3.45 after — over the ceiling
        on both sides, so nothing is rescaled and Golden State is still 74%. Had the
        fix carried the sum UNDER 1.60 it would silently have re-scaled every
        surviving row and moved a number no part of this change is about.
        """
        from app.routes.futures import _empty_book_outcome_ids, _format_market_detail

        detail = _format_market_detail(
            _market(), None, _empty_book_outcome_ids(_market())
        )
        priced = [o for o in detail["outcomes"] if o["probability"] is not None]

        assert len(priced) == 14
        leader = max(priced, key=lambda o: o["probability"])
        assert leader["name"].startswith("Golden State")
        assert leader["probability"] == pytest.approx(0.74)
        assert sum(o["probability"] for o in priced) == pytest.approx(3.45, abs=1e-6)

    @pytest.mark.asyncio
    async def test_the_route_actually_composes_the_arm(self, monkeypatch):
        """🔴 THE TEST THAT GUARDS THE FIX ITSELF, and the rest of this file does not.

        Every other ladder test calls ``_empty_book_outcome_ids`` by hand and hands
        the result to ``_format_market_detail`` — so all of them stay green if the
        one line wiring the arm into ``get_futures_market`` is deleted, which IS the
        fix. This one asks the handler and reads what it returns. The three sibling
        arms are stubbed to the empty set so a 16 here can only have come from the
        fourth.
        """
        import app.routes.futures as fr

        market = _market()

        class _Result:
            def scalar_one_or_none(self):
                return market

        class _DB:
            async def execute(self, *_a, **_k):
                return _Result()

        async def _no_ids(_db, _market):
            return set()

        async def _no_sources(_db, _market_id, _outcome_ids):
            return [], []

        monkeypatch.setattr(fr, "_unsupported_price_outcome_ids", _no_ids)
        monkeypatch.setattr(fr, "_refuted_midpoint_outcome_ids", _no_ids)
        monkeypatch.setattr(fr, "_book_refuted_outcome_ids", lambda _m: set())
        monkeypatch.setattr(fr, "_load_market_sources", _no_sources)

        detail = await fr.get_futures_market(57777176, _DB())

        assert detail["prices_withheld"] == 16
        blanked = [o for o in detail["outcomes"] if o["probability"] is None]
        assert len(blanked) == 16

    def test_a_settled_row_is_exempt_and_keeps_its_price(self):
        """🔴 SETTLED MEANS SETTLED — the grade exemption, on the ladder.

        The shared predicate knows nothing about settlement, so the exemption lives
        at this call site. #6532 names the cost of getting it wrong: withholding a
        settled row's price deletes a result. 58 of the 4,192 legs this arm reaches
        are graded (production, 2026-09-17), so the exemption is cheap and the harm
        it prevents is the only irreversible one in the change.
        """
        from app.routes.futures import _empty_book_outcome_ids, _format_market_detail

        graded = [
            SimpleNamespace(
                id=1,
                name="A settled leg on a stale empty book",
                external_id="settled",
                current_probability=0.500,
                current_yes_bid=0.0000,
                current_yes_ask=1.0000,
                current_american_odds=100,
                rank=1,
                rank_change_24h=None,
                probability_change_24h=None,
                opening_probability=None,
                opening_american_odds=None,
                is_winner=True,
                resolution_source="api_settlement",
                last_updated=None,
            )
        ]
        market = _market(legs=graded)
        assert _empty_book_outcome_ids(market) == set(), (
            "a graded row is exempt — withholding its price deletes a result"
        )

        row = _format_market_detail(market, None, set())["outcomes"][0]
        assert row["probability"] == pytest.approx(0.5)
        assert row["is_winner"] is True
        assert row["resolution_source"] == "api_settlement"

        # 🪤 And the exemption is the GRADE, not the book: the identical row
        # ungraded is withheld, so this test cannot pass by the predicate simply
        # failing to reach the shape.
        ungraded = SimpleNamespace(**{**vars(graded[0]), "resolution_source": None,
                                      "is_winner": False})
        assert _empty_book_outcome_ids(_market(legs=[ungraded])) == {1}


class TestTheChart:
    """The graph above the ladder must not plot what the ladder just refused.

    #5898's rule, one arm later. Market 57777176's Chicago Bulls row carries five
    stored points, every one of them the midpoint of a 0.01/0.96 or 0.01/0.95 book,
    so without this the table would print "—" while the graph drew 48.5%.
    """

    @staticmethod
    def _snapshot(outcome_id, probability, yes_bid, yes_ask):
        return SimpleNamespace(
            outcome_id=outcome_id,
            bookmaker="polymarket",
            probability=probability,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            last_price=None,
        )

    #: Outcome 214465541's five stored points, read off production 2026-09-17.
    BULLS_POINTS = (
        (0.485, 0.0100, 0.9600),
        (0.485, 0.0100, 0.9600),
        (0.485, 0.0100, 0.9600),
        (0.485, 0.0100, 0.9600),
        (0.480, 0.0100, 0.9500),
    )

    def test_every_fabricated_point_is_dropped_and_an_honest_one_survives(self):
        from app.routes.futures import _drop_unsupported_snapshot_points

        outcomes = [
            SimpleNamespace(id=214465541, resolution_source=None, is_winner=False),
            SimpleNamespace(id=214465546, resolution_source=None, is_winner=False),
        ]
        snapshots = [
            self._snapshot(214465541, p, bid, ask) for p, bid, ask in self.BULLS_POINTS
        ]
        # Golden State's own point: a real 0.52 bid, so a real line.
        snapshots.append(self._snapshot(214465546, 0.740, 0.5200, 0.9600))

        kept = _drop_unsupported_snapshot_points(snapshots, outcomes)
        assert [s.outcome_id for s in kept] == [214465546]
        assert kept[0].probability == pytest.approx(0.740)

    def test_an_outcome_the_caller_did_not_load_keeps_every_point(self):
        """🪤 #5898's CONTRACT, WHICH THIS ARM OBEYS RATHER THAN OVERRIDES.

        An earlier revision asked this rule of every snapshot, on the reasoning
        that it reads only the snapshot's own columns and so needs nothing from
        ``grades``. That is true and it is still the wrong place: the docstring
        above refuses to let an unloaded outcome lose points ON PURPOSE, and a
        new arm is not the occasion to quietly reverse another ship's decision.
        Pinned so the arm cannot drift back out of the branch.
        """
        from app.routes.futures import _drop_unsupported_snapshot_points

        kept = _drop_unsupported_snapshot_points(
            [self._snapshot(999_999, 0.485, 0.0100, 0.9600)], []
        )
        assert [s.probability for s in kept] == [0.485]

    def test_a_settled_outcomes_completed_journey_is_shown_whole(self):
        """🔴 SETTLED MEANS SETTLED, on the chart (#225 item 3, #232, #5898).

        A market's price legitimately passes through midpoints of a wide book
        while it is live; once the venue decides it, the line that got there is
        the completed journey and is not re-judged on the book it travelled
        through. ``_REFUSED_TAIL`` in #5898's own tests is this exact shape, and
        an ungated version of this arm took it off a champion's chart.
        """
        from app.routes.futures import _drop_unsupported_snapshot_points

        graded = [
            SimpleNamespace(
                id=1, resolution_source="api_settlement", is_winner=True
            )
        ]
        snapshots = [self._snapshot(1, p, bid, ask) for p, bid, ask in self.BULLS_POINTS]
        kept = _drop_unsupported_snapshot_points(snapshots, graded)
        assert len(kept) == len(self.BULLS_POINTS)

    def test_a_null_book_is_not_an_empty_one(self):
        """A model price (DataGolf, odds_api, a derived complement) has no book at
        all and is passed through untouched — the predicate's own rule, pinned on
        the chart path because a missing side read as the widest quote would blank
        every such series."""
        from app.routes.futures import _drop_unsupported_snapshot_points

        kept = _drop_unsupported_snapshot_points(
            [self._snapshot(1, 0.485, None, None)],
            [SimpleNamespace(id=1, resolution_source=None, is_winner=False)],
        )
        assert [s.probability for s in kept] == [0.485]
