"""#5876 — a Polymarket midpoint the venue's own newest trade refutes is not served.

THE READER'S COMPLAINT, which every specimen below is taken from verbatim.
``/futures/8641774`` (*Brazil Série B: Winner*) printed SIXTEEN of twenty clubs
at 45–50% each, under a column header reading *LATEST*, in a table summing to
roughly 700%. Every one of those rows stores ``(bid+ask)/2`` to five decimal
places over a book 0.90–0.98 wide, written 2026-07-21 and never rewritten.

The numbers in this file are production rows read 2026-09-13, not invented
fixtures, because the shape of the defect IS the argument: a price and a trade
written in the same microsecond that contradict each other.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it:
- if the rule fired on the shape alone it would take the four honest rows at the
  bottom of the same board (Avaí, Botafogo-SP, América Mineiro, Ponte Preta) and
  the hero (Juventude), so those are asserted SPARED, by name, from the same
  market;
- if the route asked for the best trade instead of the newest one it would spare
  every leg on the page, so that is a route-level test with two snapshots, not a
  unit test of the predicate.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    POLYMARKET_BOOKMAKER,
    WITHHELD_PRICE_FIELDS,
    midpoint_refuted_by_last_trade,
    needs_trade_disconfirmation,
)
from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD


def _refuted(
    source="polymarket",
    resolution_source=None,
    prob=0.4895,
    bid=0.0010,
    ask=0.9780,
    last_price=0.0100,
    has_trade_evidence=True,
):
    return midpoint_refuted_by_last_trade(
        source,
        resolution_source,
        prob,
        bid,
        ask,
        last_price,
        has_trade_evidence=has_trade_evidence,
    )


#: Market 8641774 as production served it at 09:40Z on 2026-09-13:
#: (name, served probability, yes_bid, yes_ask, newest snapshot's last_price).
#: The first fifteen are the defect; the last five are the same board's honest
#: rows and are the control.
_SERIE_B = [
    ("Sport", 0.489500, 0.0010, 0.9780, 0.0100),
    ("Fortaleza", 0.484500, 0.0060, 0.9630, 0.0210),
    ("Novorizontino", 0.481500, 0.0020, 0.9610, 0.2070),
    ("Cuiabá", 0.478500, 0.0040, 0.9530, 0.0080),
    ("Londrina", 0.472500, 0.0060, 0.9390, 0.0500),
    ("Ceará", 0.470000, 0.0020, 0.9380, 0.0040),
    ("Náutico", 0.470000, None, 0.9400, 0.0100),
    ("Vila Nova", 0.468500, 0.0020, 0.9350, 0.0280),
    ("São Bernardo", 0.465000, None, 0.9300, 0.0100),
    ("Operário Ferroviário", 0.464500, 0.0020, 0.9270, 0.0500),
    ("Goiás", 0.464500, 0.0020, 0.9270, 0.0070),
    ("Athletic", 0.460000, 0.0020, 0.9180, 0.0100),
    ("Atlético Goianiense", 0.459000, 0.0040, 0.9140, 0.0100),
    ("Criciúma", 0.456000, 0.0040, 0.9080, 0.0020),
    ("CRB", 0.454000, 0.0020, 0.9060, 0.0110),
]
_SERIE_B_HONEST = [
    ("Juventude", 0.499000, 0.0080, 0.4990, 0.4990),
    ("Avaí", 0.020500, 0.0120, 0.0290, 0.0500),
    ("Botafogo-SP", 0.018000, 0.0080, 0.0280, 0.0500),
    ("América Mineiro", 0.008000, 0.0020, 0.0140, 0.0020),
    ("Ponte Preta", 0.001000, None, 0.0100, 0.0010),
]


class TestTheProductionSpecimenIsRefused:
    @pytest.mark.parametrize("name,prob,bid,ask,last", _SERIE_B)
    def test_every_frozen_club_on_8641774_is_withheld(self, name, prob, bid, ask, last):
        assert _refuted(prob=prob, bid=bid, ask=ask, last_price=last) is True, name

    def test_the_page_said_47_percent_and_the_last_trade_said_0_point_4(self):
        """Ceará, the headline arithmetic of #5876 in one row."""
        assert _refuted(prob=0.470000, bid=0.0020, ask=0.9380, last_price=0.0040)

    def test_a_missing_bid_is_the_widest_possible_book_not_a_missing_one(self):
        """Náutico and São Bernardo carry no bid at all. If a null bid dropped the
        row instead of coalescing to 0.0, two of the fifteen would survive."""
        assert _refuted(prob=0.470000, bid=None, ask=0.9400, last_price=0.0100)
        assert _refuted(prob=0.465000, bid=None, ask=0.9300, last_price=0.0100)


class TestTheSameBoardsHonestRowsSurvive:
    """The control, and the reason this is not a shape-only rule."""

    @pytest.mark.parametrize("name,prob,bid,ask,last", _SERIE_B_HONEST)
    def test_the_cliff_and_the_hero_keep_their_prices(self, name, prob, bid, ask, last):
        assert _refuted(prob=prob, bid=bid, ask=ask, last_price=last) is False, name

    def test_the_hero_is_spared_because_it_is_not_a_midpoint_at_all(self):
        """Juventude's book IS wide (0.008/0.499), so a spread-only rule would
        take it. Its served 0.4990 is the last TRADE, not the 0.2535 midpoint."""
        assert (
            needs_trade_disconfirmation("polymarket", None, 0.499000, 0.0080, 0.4990)
            is False
        )

    def test_the_cliff_is_spared_because_its_book_is_tight(self):
        """Avaí's 0.012/0.029 is 1.7 cents wide against a 20-cent threshold."""
        assert 0.0290 - 0.0120 < FEED_PHANTOM_MIN_SPREAD
        assert (
            needs_trade_disconfirmation("polymarket", None, 0.020500, 0.0120, 0.0290)
            is False
        )


class TestTheMeasuredExclusions:
    """Each of these is a population counted on production 2026-09-13. Deleting
    any one of them changes a number in the module docstring."""

    def test_an_absent_snapshot_fails_open(self):
        """gotcha #53: "we never looked" is not "there is no trade"."""
        assert _refuted(last_price=None, has_trade_evidence=False) is False

    def test_absence_is_answered_by_the_flag_and_not_by_the_value(self):
        """`has_trade_evidence` is a SEPARATE question from `last_price`, and a
        test that only ever passes None for both cannot tell the two apart — the
        `last_price is None` check alone would satisfy it. A caller holding a
        number it did not get from a snapshot read must still fail open, which is
        the contract #5611's arm states at length and this arm inherits."""
        assert _refuted(last_price=0.0040, has_trade_evidence=False) is False
        assert _refuted(last_price=0.0040, has_trade_evidence=True) is True

    def test_a_null_last_price_is_not_evidence_of_no_trade(self):
        """3,220 of the 3,898 fabricated-midpoint legs are in exactly this state
        — the MAJORITY of the raw shape — and are deliberately left alone."""
        assert _refuted(last_price=None, has_trade_evidence=True) is False

    def test_a_zero_last_price_is_evidence_and_does_refute(self):
        """46 legs on 5 markets, every one serving 0.5000 off a 0.0/1.0 book.
        Polymarket assigns `last_trade_price` straight through, so NULL and 0.0
        arrive from different upstream answers and may be read differently."""
        assert _refuted(prob=0.5, bid=0.0, ask=1.0, last_price=0.0) is True

    def test_a_trade_that_prints_as_the_served_number_supports_it(self):
        """The page prints whole percents; 47.2% and 47.0% are the same row to a
        reader. 15 legs sit inside this tolerance and keep their prices."""
        assert _refuted(prob=0.4895, last_price=0.4895) is False
        assert _refuted(prob=0.4895, last_price=0.4870) is False

    def test_a_trade_half_a_point_away_does_not(self):
        assert _refuted(prob=0.4895, last_price=0.4840) is True

    def test_a_graded_row_keeps_its_number(self):
        """Once `resolution_source` is set the number is a settlement value, not
        a quote. Withholding here would delete a RESULT and pre-empt #4788."""
        assert _refuted(resolution_source="polymarket") is False

    def test_kalshi_is_not_governed_by_polymarkets_price_rule(self):
        """gotcha #19: the two venues write these columns under different rules,
        which is why #5611 scoped itself and left this ship to be built."""
        assert _refuted(source="kalshi") is False
        assert _refuted(source="odds_api") is False

    def test_source_matching_is_not_case_or_whitespace_sensitive(self):
        assert _refuted(source="  PolyMarket ") is True

    def test_a_model_priced_row_with_no_book_is_untouched(self):
        """Both sides null means there is no order book — a DataGolf/odds_api
        model price or a derived complement. `is_fabricated_midpoint` returns
        False by construction, which is why those controls need no exemption."""
        assert _refuted(prob=0.5, bid=None, ask=None, last_price=0.01) is False


class TestTheScreenAgreesWithTheRule:
    """A screen that is narrower than its rule silently drops real rows; one that
    is wider costs a snapshot read per market. They must agree exactly."""

    @pytest.mark.parametrize("name,prob,bid,ask,last", _SERIE_B)
    def test_everything_the_rule_refuses_was_screened_in(
        self, name, prob, bid, ask, last
    ):
        assert needs_trade_disconfirmation("polymarket", None, prob, bid, ask), name

    def test_the_screen_never_asks_about_a_graded_or_foreign_row(self):
        assert not needs_trade_disconfirmation("kalshi", None, 0.4895, 0.001, 0.978)
        assert not needs_trade_disconfirmation(
            "polymarket", "poly", 0.4895, 0.001, 0.978
        )

    def test_the_screen_and_the_shipped_spread_bound_cannot_drift_apart(self):
        """Two records of one capability, asserted rather than assumed. The
        boundary is `is_fabricated_midpoint`'s own constant, not a copy."""
        edge = FEED_PHANTOM_MIN_SPREAD
        assert (
            needs_trade_disconfirmation("polymarket", None, edge / 2, 0.0, edge) is True
        )
        assert (
            needs_trade_disconfirmation(
                "polymarket", None, (edge - 0.01) / 2, 0.0, edge - 0.01
            )
            is False
        )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.rows)

    def sql(self):
        return " ".join(str(s.compile()) for s in self.statements)


def _poly_market(outcomes, source="polymarket"):
    return SimpleNamespace(id=8641774, source=source, outcomes=outcomes)


def _poly_outcome(id, prob, bid, ask, resolution_source=None):
    return SimpleNamespace(
        id=id,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
    )


@pytest.mark.asyncio
class TestTheRouteAsksTheRightQuestionOfTheSnapshots:
    """The unit tests above can all pass while the ROUTE feeds the rule the wrong
    trade — and on this defect that is not hypothetical. It is the single most
    likely way to ship #5876 broken."""

    async def test_the_route_reads_the_newest_trade_and_not_the_best_one(self):
        """THE TRAP, with the production numbers that set it. Market 8641774's
        outcomes carry ~2,386 snapshots each; `max(last_price)` over that history
        reads 0.92–0.96 and would spare EVERY leg on the page, while the newest
        row reads 0.0040. An aggregate here reads the outcome's liquid past."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        outcome = _poly_outcome(1, 0.470000, 0.0020, 0.9380)
        # Only the newest row survives the route's own LATERAL, so the fake
        # returns exactly what that query would: one row, the 2026-07-21 one.
        db = _FakeSession(rows=[(1, 0.0040)])
        assert await _refuted_midpoint_outcome_ids(db, _poly_market([outcome])) == {1}

        # And the shape that would spare it, to prove the assertion above is
        # about the VALUE and not merely about the row existing.
        db2 = _FakeSession(rows=[(1, 0.4700)])
        assert (
            await _refuted_midpoint_outcome_ids(db2, _poly_market([outcome])) == set()
        )

    async def test_the_snapshot_read_is_scoped_to_polymarket(self):
        """Reading Kalshi's snapshots for a Polymarket leg would compare a price
        against another venue's trades entirely.

        TWO ASSERTIONS, BECAUSE EITHER ALONE IS WEAK. The read has two halves —
        the newest `captured_at` per outcome and the `last_price` at that instant
        — and each needs the term, so the COUNT is what catches a mutant that
        strips the outer filter (#5611's own note records that `"bookmaker" in
        sql` survived exactly that). But the count cannot see the venue NAME:
        SQLAlchemy binds it as `:bookmaker_1`, so a rule reading Kalshi's trades
        would compile to the identical string. The bound VALUES are therefore
        asserted separately.
        """
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0040)])
        await _refuted_midpoint_outcome_ids(
            db, _poly_market([_poly_outcome(1, 0.470000, 0.0020, 0.9380)])
        )
        compiled = db.statements[0].compile()
        assert str(compiled).count("bookmaker = :bookmaker") == 2, (
            "both the newest-snapshot subquery and the price read must carry the "
            f"term, or the outer half reads every venue. Got: {compiled}"
        )
        bound = [v for k, v in compiled.params.items() if k.startswith("bookmaker")]
        assert bound == [
            POLYMARKET_BOOKMAKER,
            POLYMARKET_BOOKMAKER,
        ], f"both halves must be bound to Polymarket, got {bound}"

    async def test_a_market_with_no_candidate_never_touches_the_snapshot_table(self):
        """The screen is the cost control: 1,361 open Polymarket markets hold the
        shape, but a board of honest rows must cost zero queries."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0040)])
        honest = [
            _poly_outcome(i, p, b, a)
            for i, (_, p, b, a, _l) in enumerate(_SERIE_B_HONEST, start=1)
        ]
        assert await _refuted_midpoint_outcome_ids(db, _poly_market(honest)) == set()
        assert db.statements == [], "a clean board must ask the database nothing"

    async def test_a_kalshi_market_is_not_screened_by_this_arm_at_all(self):
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, 0.0040)])
        kalshi = _poly_market(
            [_poly_outcome(1, 0.470000, 0.0020, 0.9380)], source="kalshi"
        )
        assert await _refuted_midpoint_outcome_ids(db, kalshi) == set()
        assert db.statements == []

    async def test_an_outcome_with_no_snapshot_row_fails_open(self):
        """The LATERAL returns nothing for it; the route must not read that as a
        zero trade. This is the route-level face of gotcha #53."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[])
        assert (
            await _refuted_midpoint_outcome_ids(
                db, _poly_market([_poly_outcome(1, 0.470000, 0.0020, 0.9380)])
            )
            == set()
        )

    async def test_a_null_last_price_row_fails_open(self):
        from app.routes.futures import _refuted_midpoint_outcome_ids

        db = _FakeSession(rows=[(1, None)])
        assert (
            await _refuted_midpoint_outcome_ids(
                db, _poly_market([_poly_outcome(1, 0.470000, 0.0020, 0.9380)])
            )
            == set()
        )

    @pytest.mark.parametrize(
        "rows", [[(1, 0.0040), (1, 0.4700)], [(1, 0.4700), (1, 0.0040)]]
    )
    async def test_ties_on_captured_at_resolve_to_the_trade_that_spares_the_row(
        self, rows
    ):
        """Two snapshots can share a microsecond. Fail-open means the one most
        likely to SUPPORT what we print is the one that gets to speak — and the
        answer must not depend on the order the rows come back in."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        assert (
            await _refuted_midpoint_outcome_ids(
                _FakeSession(rows=rows),
                _poly_market([_poly_outcome(1, 0.470000, 0.0020, 0.9380)]),
            )
            == set()
        )

    async def test_the_tie_break_is_closest_to_served_and_not_the_highest_price(self):
        """CLOSEST, not BEST, and the two are only distinguishable when the
        sparing trade is the LOWER one. With trades of 0.4700 and 0.9000 against
        a served 0.4700, `max` picks 0.9000 and withholds a row a real trade
        supports — fail-CLOSED, the opposite of the intent. A tie case where the
        sparing value is also the maximum cannot see this."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        for rows in ([(1, 0.4700), (1, 0.9000)], [(1, 0.9000), (1, 0.4700)]):
            assert (
                await _refuted_midpoint_outcome_ids(
                    _FakeSession(rows=rows),
                    _poly_market([_poly_outcome(1, 0.470000, 0.0020, 0.9380)]),
                )
                == set()
            ), f"max() would withhold here; rows={rows}"

    async def test_the_full_specimen_board_withholds_fifteen_and_keeps_five(self):
        """End to end over the real market, which is the number #5876 claims."""
        from app.routes.futures import _refuted_midpoint_outcome_ids

        outcomes, rows = [], []
        for i, (_n, p, b, a, last) in enumerate(_SERIE_B + _SERIE_B_HONEST, start=1):
            outcomes.append(_poly_outcome(i, p, b, a))
            rows.append((i, last))
        withheld = await _refuted_midpoint_outcome_ids(
            _FakeSession(rows=rows), _poly_market(outcomes)
        )
        assert withheld == set(range(1, len(_SERIE_B) + 1))
        assert len(withheld) == 15


@pytest.mark.asyncio
class TestBothArmsLandInOneWithheldSet:
    """#5611 and #5876 are disjoint by construction — each screens on
    `market.source` — but the serializer must receive their union, or the second
    ship silently does nothing."""

    async def test_the_endpoint_passes_the_union_of_both_arms_to_the_serializer(
        self, monkeypatch
    ):
        """THE UNWIRED-HELPER GUARD, and it is the reason this test exists at the
        endpoint rather than one level down. Every other test in this file passes
        with `_refuted_midpoint_outcome_ids` never called by anything — a fully
        tested helper that changes nothing a reader sees. Deleting the `|=` line
        in `get_futures_market`, or replacing it with `=`, must fail here.
        """
        from app.routes import futures as futures_route

        market = SimpleNamespace(
            id=8641774,
            source="polymarket",
            outcomes=[SimpleNamespace(id=1), SimpleNamespace(id=2)],
        )

        class _Res:
            def scalar_one_or_none(self):
                return market

        class _DB:
            async def execute(self, _stmt):
                return _Res()

        async def _sources(*_a, **_k):
            return [], []

        async def _kalshi_arm(_db, _m):
            return {101}

        async def _poly_arm(_db, _m):
            return {202}

        seen = {}

        def _fake_detail(_m, _b, withheld):
            seen["withheld"] = withheld
            return {}

        monkeypatch.setattr(futures_route, "_load_market_sources", _sources)
        monkeypatch.setattr(
            futures_route, "_unsupported_price_outcome_ids", _kalshi_arm
        )
        monkeypatch.setattr(futures_route, "_refuted_midpoint_outcome_ids", _poly_arm)
        monkeypatch.setattr(futures_route, "_format_market_detail", _fake_detail)

        await futures_route.get_futures_market(8641774, _DB())
        assert seen["withheld"] == {101, 202}, (
            "the serializer must receive BOTH arms; got "
            f"{seen['withheld']}. 101 alone means #5876 is unwired, 202 alone "
            "means #5611 was overwritten rather than unioned."
        )

    async def test_the_polymarket_arm_reaches_the_serializer(self):
        from app.routes.futures import _format_market_detail

        market = SimpleNamespace(
            id=8641774,
            name="Brazil Série B: Winner",
            description=None,
            category="sports",
            source="polymarket",
            external_id="serie-b",
            status="open",
            sport=None,
            sport_id=None,
            event_id=None,
            market_type=None,
            market_tier=1,
            llm_sport_category="soccer",
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
                    external_id=f"club-{i}",
                    current_probability=p,
                    current_american_odds=110,
                    rank=i,
                    rank_change_24h=None,
                    probability_change_24h=0.01,
                    opening_probability=None,
                    opening_american_odds=None,
                    is_winner=None,
                    resolution_source=None,
                    last_updated=None,
                )
                for i, (name, p, _b, _a, _l) in enumerate(
                    _SERIE_B + _SERIE_B_HONEST, start=1
                )
            ],
        )
        detail = _format_market_detail(market, None, set(range(1, 16)))
        assert detail["prices_withheld"] == 15
        for row in detail["outcomes"]:
            if row["id"] <= 15:
                for field in WITHHELD_PRICE_FIELDS:
                    assert field in row, f"{field} must be present, not omitted"
                    assert row[field] is None
            else:
                assert row["probability"] is not None
