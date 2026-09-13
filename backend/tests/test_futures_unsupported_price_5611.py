"""#5611 — a futures price no book and no trade supports is not served.

THE DEFECT, from production. `/futures/109279` ("Who will release a new song
this year?") printed twelve artists at `LATEST 100%`. Each row quotes
`yes_bid 0.0000 / yes_ask 1.0000` — nobody bidding anything, nobody offering
below certainty — its newest Kalshi snapshot carries `last_price 0.0000`, and
`current_probability` was last written in April. A five-month-old fossil under a
header reading "Latest".

WHAT THESE TESTS ARE REALLY GUARDING. The rule is a two-sided thing and the
dangerous side is the REFUSALS. Measured on production 2026-09-13, of the 2,474
ungraded open Kalshi legs quoting an empty book, 2,031 have a real trade behind
the price and must keep it; 4,444 more legs of the same raw bid/ask shape are
graded and hold a settlement value someone else's ship is responsible for. So a
predicate that merely "fires on an empty book" over-reaches by 15x and deletes
real prices and real results. Every exclusion below is a measured population,
named with its count, and is the assertion that would catch that.
"""

from types import SimpleNamespace

import pytest

from app.utils.futures_unsupported_price import (
    WITHHELD_PRICE_FIELDS,
    needs_trade_evidence,
    price_is_unsupported,
)
from app.utils.kalshi_empty_book import ASK_ONLY_TRUSTED_MAX


def _unsupported(
    source="kalshi",
    resolution_source=None,
    yes_bid=0.0,
    yes_ask=1.0,
    last_price=0.0,
    has_trade_evidence=True,
):
    """The production specimen's shape, with one field varied per test."""
    return price_is_unsupported(
        source,
        resolution_source,
        yes_bid,
        yes_ask,
        last_price,
        has_trade_evidence=has_trade_evidence,
    )


class TestTheProductionSpecimenIsRefused:
    def test_the_100_percent_row_on_109279_is_unsupported(self):
        """Don Toliver: bid 0.00, ask 1.00, last_price 0.00, ungraded, Kalshi."""
        assert _unsupported() is True

    def test_it_fires_wherever_the_frozen_price_happens_to_sit(self):
        """The served price is NOT an input, and that is the whole ship.

        #5247's shipped helper (`is_empty_book_midpoint`) asks whether the price
        sits ON the book's midpoint, reasoning that a price far from it came
        from a real trade. Measured over this population that premise is false:
        380 of the 443 legs are far from the midpoint AND have never traded
        (mean served price 0.988), so a midpoint rule catches 63 and leaves the
        380 loudest rows on the page. This rule reads the trade column instead,
        so where the fossil happens to sit cannot save it.
        """
        assert _unsupported() is True  # the 1.00 fossil, 0.50 from the midpoint
        assert _unsupported(yes_ask=0.99) is True


class TestTheMeasuredExclusions:
    """Each of these is a population, and each would be a deleted truth."""

    def test_a_real_trade_keeps_its_price(self):
        """The 2,031. The shipped predicate's rule 2: trade evidence beats a wide
        book. Whether such a trade has gone stale is the freshness ship (#5314,
        #5781), not this one."""
        assert _unsupported(last_price=0.42) is False

    def test_a_graded_row_keeps_its_number(self):
        """The 4,444. Once `resolution_source` is set the number is a settlement
        value, and what to print for it is the settled-language question
        (#4788/#5549/#5820) — answered elsewhere, with a verdict already on the
        wire. Withholding here would silently delete a result."""
        assert _unsupported(resolution_source="api_settlement") is False
        assert _unsupported(resolution_source="kalshi_ws") is False

    def test_polymarket_is_not_governed_by_kalshis_price_rule(self):
        """The 378 legs on 56 open markets. `lone_ask_on_empty_book_sql` carries
        the bookmaker term for exactly this reason — Polymarket's rule for these
        columns is gotcha #19's, a different one. A Polymarket ruling is its own
        ship, never a silent rider on this."""
        assert _unsupported(source="polymarket") is False

    def test_an_absent_snapshot_fails_open(self):
        """Gotcha #53: "we never looked" and "we looked and it never traded" are
        different answers. Only the second is evidence."""
        assert _unsupported(has_trade_evidence=False) is False
        assert (
            _unsupported(has_trade_evidence=True) is True
        ), "control: the ONLY difference is whether we found a snapshot"

    def test_a_null_last_price_is_not_evidence_of_no_trade(self):
        assert _unsupported(last_price=None, has_trade_evidence=False) is False

    def test_a_real_bid_is_a_real_price(self):
        """Somebody is paying. A lone BID grades at 93.7% — see the measured
        asymmetry table in `kalshi_empty_book`; only the ask side is refused."""
        assert _unsupported(yes_bid=0.35) is False

    def test_a_longshot_ask_inside_the_trusted_band_is_kept(self):
        """Rule 3 of the poller's own ladder: an ask-only book is trusted up to
        `ASK_ONLY_TRUSTED_MAX`. This rule must not reach below that line."""
        assert _unsupported(yes_ask=0.40) is False
        assert _unsupported(yes_ask=0.50) is False, "the bound is exclusive"
        assert _unsupported(yes_ask=0.51) is True

    def test_a_missing_book_is_not_an_empty_one(self):
        """None means the poller never recorded a book (model prices: DataGolf,
        odds_api, a derived complement). It is not nobody bidding."""
        assert _unsupported(yes_bid=None) is False
        assert _unsupported(yes_ask=None) is False
        assert _unsupported(yes_bid=None, yes_ask=None) is False


class TestTheScreenAgreesWithTheRule:
    """`needs_trade_evidence` decides who gets a snapshot read. If it can say no
    where the full rule says yes, the route silently under-serves the fix."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"yes_ask": 0.51},
            {"yes_ask": 0.99},
        ],
    )
    def test_everything_the_rule_refuses_was_screened_in(self, kwargs):
        assert _unsupported(**kwargs) is True
        assert (
            needs_trade_evidence(
                "kalshi",
                None,
                kwargs.get("yes_bid", 0.0),
                kwargs.get("yes_ask", 1.0),
            )
            is True
        )

    def test_the_screen_is_cheap_and_never_asks_about_a_graded_or_foreign_row(self):
        assert needs_trade_evidence("kalshi", "api_settlement", 0.0, 1.0) is False
        assert needs_trade_evidence("polymarket", None, 0.0, 1.0) is False
        assert needs_trade_evidence("odds_api", None, 0.0, 1.0) is False
        assert needs_trade_evidence(None, None, 0.0, 1.0) is False

    def test_source_matching_is_not_case_or_whitespace_sensitive(self):
        assert needs_trade_evidence(" Kalshi ", None, 0.0, 1.0) is True

    def test_the_screen_and_the_shipped_bound_cannot_drift_apart(self):
        """Two records of one capability must be asserted equal, not assumed."""
        assert needs_trade_evidence("kalshi", None, 0.0, ASK_ONLY_TRUSTED_MAX) is False
        assert (
            needs_trade_evidence("kalshi", None, 0.0, ASK_ONLY_TRUSTED_MAX + 0.01)
            is True
        )


def _market(outcome_specs, mutually_exclusive=True, source="kalshi"):
    outcomes = [
        SimpleNamespace(
            id=i,
            name=f"Entrant {i}",
            external_id=f"ENT-{i}",
            current_probability=spec["prob"],
            current_american_odds=-9900,
            rank=i,
            rank_change_24h=None,
            probability_change_24h=spec.get("change", 0.5),
            opening_probability=None,
            opening_american_odds=None,
            is_winner=None,
            resolution_source=None,
            last_updated=None,
        )
        for i, spec in enumerate(outcome_specs, start=1)
    ]
    return SimpleNamespace(
        id=109279,
        name="Who will release a new song this year?",
        description=None,
        category="entertainment",
        source=source,
        external_id="KXNEWSONG-26",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=2,
        llm_sport_category="entertainment",
        mutually_exclusive=mutually_exclusive,
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
        outcomes=outcomes,
    )


def _detail(market, withheld_ids=None):
    from app.routes.futures import _format_market_detail

    return _format_market_detail(market, None, withheld_ids)


class TestTheSerializerPublishesTheRefusal:
    def test_a_withheld_row_serves_the_key_present_and_null(self):
        """`undefined !== null` is true, so an OMITTED key is not a refusal.
        `formatProbability(null)` prints "-"; `formatProbability(undefined)`
        happens to as well, but the sort and hero read `probability ?? 0` and a
        missing key would be a contract the clients were never given."""
        detail = _detail(_market([{"prob": 1.0}, {"prob": 0.30}]), {1})
        row = next(o for o in detail["outcomes"] if o["id"] == 1)
        for field in WITHHELD_PRICE_FIELDS:
            assert field in row, f"{field} must be PRESENT, not omitted"
            assert row[field] is None

    def test_every_restatement_of_the_price_falls_with_it(self):
        """Leaving `american_odds` would let any consumer reconstruct exactly the
        price just refused; leaving `probability_change_24h` prints a move
        measured from a number we declined to state."""
        assert set(WITHHELD_PRICE_FIELDS) == {
            "probability",
            "american_odds",
            "probability_change_24h",
        }

    def test_an_untouched_row_keeps_everything(self):
        detail = _detail(_market([{"prob": 1.0}, {"prob": 0.30}]), {1})
        kept = next(o for o in detail["outcomes"] if o["id"] == 2)
        assert kept["probability"] == pytest.approx(0.30)
        assert kept["american_odds"] is not None

    def test_the_count_is_published_for_probes_and_is_always_present(self):
        clean = _detail(_market([{"prob": 0.30}, {"prob": 0.20}]))
        assert clean["prices_withheld"] == 0, "absence must mean an old build"
        one = _detail(_market([{"prob": 1.0}, {"prob": 0.30}]), {1})
        assert one["prices_withheld"] == 1

    def test_no_withheld_ids_changes_nothing(self):
        before = _detail(_market([{"prob": 0.6}, {"prob": 0.4}]))
        after = _detail(_market([{"prob": 0.6}, {"prob": 0.4}]), set())
        assert [o["probability"] for o in before["outcomes"]] == [
            o["probability"] for o in after["outcomes"]
        ]
        assert before["prices_withheld"] == after["prices_withheld"] == 0


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Records every statement so a test can assert what was asked, and how often."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeResult(self.rows)

    def sql(self):
        return " ".join(str(s.compile()) for s in self.statements)


def _outcome(id, bid, ask, resolution_source=None):
    return SimpleNamespace(
        id=id,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
    )


@pytest.mark.asyncio
class TestTheRouteAsksTheRightQuestionOfTheSnapshots:
    """The unit tests above can all pass while the ROUTE feeds the rule a wrong
    input, and the worst of those is not hypothetical: handing
    `price_is_unsupported` a `last_price` of None instead of the row's real one
    turns "never traded" into "we did not look" and withholds 2,474 legs where
    443 are warranted — a 4.6x over-reach that deletes 2,031 real prices. Only a
    test at this level can see it.
    """

    @staticmethod
    async def _ids(outcomes, rows, source="kalshi"):
        from app.routes.futures import _unsupported_price_outcome_ids

        market = SimpleNamespace(id=109279, source=source, outcomes=outcomes)
        db = _FakeSession(rows)
        return await _unsupported_price_outcome_ids(db, market), db

    async def test_a_traded_leg_is_not_withheld_and_an_untraded_one_is(self):
        ids, _ = await self._ids(
            [_outcome(1, 0.0, 1.0), _outcome(2, 0.0, 1.0)],
            [(1, 0.0), (2, 0.42)],
        )
        assert ids == {1}, (
            "outcome 2 has a real last_price and must keep its price; a route "
            "that passes None for the trade would withhold both"
        )

    async def test_a_leg_with_no_snapshot_row_is_left_alone(self):
        ids, _ = await self._ids([_outcome(1, 0.0, 1.0)], [])
        assert ids == set(), "absence is not evidence (gotcha #53)"

    async def test_a_null_last_price_in_the_snapshot_is_left_alone(self):
        ids, _ = await self._ids([_outcome(1, 0.0, 1.0)], [(1, None)])
        assert ids == set()

    async def test_the_trade_read_is_scoped_to_kalshis_own_snapshots(self):
        """`lone_ask_on_empty_book_sql` carries the bookmaker term and its
        docstring says why: unscoped, this Kalshi policy reads a book Polymarket
        wrote under a different rule (gotcha #19).

        COUNTED, NOT MERELY PRESENT. The read has two halves — the newest
        `captured_at` per outcome, and the `last_price` at that instant — and
        each needs the term. `"bookmaker" in sql` was the first version of this
        assertion and it SURVIVED the mutant that strips the term from the outer
        half, because the subquery's own term keeps the word in the string. An
        absence assertion about a shared name is not a confinement assertion.
        """
        _, db = await self._ids([_outcome(1, 0.0, 1.0)], [(1, 0.0)])
        sql = db.sql()
        assert sql.count("bookmaker = :bookmaker") == 2, (
            "both the newest-snapshot subquery and the price read must carry the "
            "term. Counting the word alone does not work: it appears four times "
            "(column name and bind name, twice each), so stripping one filter "
            f"still leaves two. Got: {sql}"
        )

    async def test_a_market_with_no_candidate_never_touches_the_database(self):
        """The screen is on the row, so the 1,300-odd open Kalshi markets this
        cannot fire on pay nothing for it."""
        ids, db = await self._ids(
            [_outcome(1, 0.45, 0.55), _outcome(2, None, None)], [(1, 0.0)]
        )
        assert ids == set()
        assert db.statements == [], "no candidates must mean no query at all"

    async def test_the_whole_market_costs_exactly_one_query(self):
        """The cost this ship adds, pinned so it cannot grow into a per-outcome
        read. LAT-P127 asserts the futures detail page does no snapshot work on a
        cached second load; that contract is about the source-breakdown cache and
        this read is outside it, so on the 47 production markets holding a
        candidate the page pays ONE extra indexed query per load. Twenty
        candidates must still be one query, not twenty.
        """
        outcomes = [_outcome(i, 0.0, 1.0) for i in range(1, 21)]
        ids, db = await self._ids(outcomes, [(i, 0.0) for i in range(1, 21)])
        assert len(ids) == 20
        assert len(db.statements) == 1

    async def test_a_graded_leg_is_screened_out_before_the_query(self):
        ids, db = await self._ids(
            [_outcome(1, 0.0, 1.0, resolution_source="api_settlement")], [(1, 0.0)]
        )
        assert ids == set()
        assert db.statements == []

    async def test_a_polymarket_market_is_screened_out_before_the_query(self):
        ids, db = await self._ids(
            [_outcome(1, 0.0, 1.0)], [(1, 0.0)], source="polymarket"
        )
        assert ids == set()
        assert db.statements == []

    async def test_decimal_columns_do_not_break_the_float_predicates(self):
        """`Numeric` arrives as `Decimal`; the predicates are typed for floats."""
        from decimal import Decimal

        ids, _ = await self._ids(
            [_outcome(1, Decimal("0.0000"), Decimal("1.0000"))],
            [(1, Decimal("0.0000"))],
        )
        assert ids == {1}


class TestTheRefusedValueLeavesTheDivisor:
    """The order of the withhold against `normalize_display_probs` is the whole
    difference between fixing a board and halving it.

    UX-P163's measured case: a no-bid `Other` at 1.0 stayed in `_feed_display_
    scale`'s divisor and Discover printed `Democratic Party 43%` against a book
    price of 85.5%. A withheld value left in the sum does the same thing here,
    once per fabricated leg.
    """

    # The fabricated midpoint of a 0.00/1.00 book is 0.50, so that is the leg
    # shape used here. 0.50 + 0.60 + 0.40 = 1.50 sits inside the normalization
    # band (> 1.05, <= `_FIELD_SUM_MAX` 1.60); withholding drops the sum to 1.00,
    # below the band, so the honest pair is published as stored.
    _BOARD = [{"prob": 0.50}, {"prob": 0.60}, {"prob": 0.40}]

    def test_the_same_board_without_the_withhold_is_squeezed(self):
        """The control, and it is written FIRST because it is what makes the
        test below mean anything. A board that was never normalized would pass
        the assertion underneath while proving nothing — the first draft of this
        pair used a 1.0 leg, whose sum of 2.0 trips the #1200 overround guard and
        turns normalization off entirely, so both readings were 0.60 and the real
        test was vacuous."""
        squeezed = {
            o["id"]: o["probability"] for o in _detail(_market(self._BOARD))["outcomes"]
        }
        assert squeezed[2] == pytest.approx(
            0.40, abs=0.001
        ), "precondition: 0.60 divided by a sum of 1.50 prints 0.40"

    def test_withholding_first_leaves_the_honest_rows_unsqueezed(self):
        survivors = {
            o["id"]: o["probability"]
            for o in _detail(_market(self._BOARD), {1})["outcomes"]
        }
        assert survivors[2] == pytest.approx(
            0.60
        ), "the refused 0.50 must leave the divisor, not merely the page"
        assert survivors[3] == pytest.approx(0.40)

    def test_a_board_of_fossils_can_start_normalizing_once_they_are_gone(self):
        """Disclosed, not hidden: withholding can change an honest row's number.

        Fabricated 1.0s push a field's raw sum past `_FIELD_SUM_MAX`, and the
        #1200 guard then serves the WHOLE board raw. Remove them and the true
        field can fall back inside the band, so the surviving rows are normalized
        where before they were not. That is the guard working on the real field
        rather than on a field plus its phantoms — but it is a visible change to
        rows this ship did not refuse, and it belongs in a test that names it.
        """
        board = [{"prob": 1.0}, {"prob": 1.0}, {"prob": 0.80}, {"prob": 0.50}]
        raw = {o["id"]: o["probability"] for o in _detail(_market(board))["outcomes"]}
        assert raw[3] == pytest.approx(0.80), "sum 3.30 > 1.60 — served raw today"

        after = {
            o["id"]: o["probability"]
            for o in _detail(_market(board), {1, 2})["outcomes"]
        }
        assert after[1] is None and after[2] is None
        assert after[3] == pytest.approx(0.80 / 1.30, abs=0.001)
        assert after[4] == pytest.approx(0.50 / 1.30, abs=0.001)
