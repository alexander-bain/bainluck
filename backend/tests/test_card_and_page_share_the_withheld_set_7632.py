"""#7632 — a Discover card stops printing prices the page behind it refuses.

Third reopening of the card-vs-page class (#7274 → #7586 → #7632). The issue
body proposed SNAPSHOT STALENESS and that hypothesis is falsified: discover/359
measured the three stalest cards splitting by 0.0 points, and the detail
endpoint carries no `price_observed_at` to compare against in the first place.
Codex's independent review found the real mechanism and approved this build
(decision (b), `artifacts/other-model-probability-agreement-finish/`).

THE MECHANISM. `/futures/{id}` screens every leg through five arms —
unsupported price, refuted midpoint, book-refuted, empty book, and
unlocated-in-a-broken-field — and renders `-` for the ones it refuses. The card
ran NONE of them.

WHAT A READER SAW, on the feed `/api/feed?limit=250` actually served at
2026-09-23 06:09Z (cache MISS), matched by outcome id, not on the population:

    61960017  WTA Seoul Winner
        card: Kimberly Birrell 49% · Lanlana Tararudee 49% · Anna Bondar 49%
        page: prices 1 of 16 legs — all three of those are withheld
    61437318  WTA Singapore Singles Winner
        card leader: Daria Kasatkina 31%, then Janice Tjen 29%
        page: withholds 15 of 19 including both; its hero is Eala 28.5%
    61734333  Walmart NW Arkansas Championship (LPGA)
        page: withholds 100 of 144, prints Yamashita 11% / Hull 5.55%
        card: divides by the fuller mass, prints 7.65% / 3.86% — ratio 0.6955

Seoul is the plainest statement of the bug: a card offering three co-favourites
at 49% lands on a page that will not price any of them. Singapore is the worst
in kind — the card NAMES A LEADER the page refuses, so the story inverts on the
tap. LPGA is the divisor arm.

🔴 `TestMissingIsNotEmpty` IS THE LOAD-BEARING CLASS. `None` (the arms never ran
for this carrier) and `[]` (they ran and refused nothing) are different facts,
and collapsing them is how this ships as a regression: read as "refuse
everything" it empties cards on any path that skips the builder, and read as
`[]` a carrier that never ran the arms is indistinguishable from a healthy
board. Both directions are pinned below.

🔴 `TestTheBoardVerdictSeesTheWholeBoard` IS THE OTHER ONE. The first cut of
this fix ran the drop BEFORE `classify_fabricated_book` and so deleted the very
legs that function judges: SpaceX's sixteen 1c/99c rungs became one
healthy-looking leg, `phantom_drop_card` never fired, and a card Alex ruled must
never ship reached the feed. Order is the rule, and it is asserted here as well
as in the suppression suite that caught it.

Every stamp below is an OFFSET from the fixture's own frozen instant (gotcha
#44), so no assertion here can age out.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.feed import _drop_withheld_price_legs
from app.routes.futures import (
    _closest_trade_by_outcome,
    _refuted_midpoint_candidates,
    _refuted_midpoint_verdicts,
    _unsupported_price_candidates,
    _unsupported_price_verdicts,
    withheld_price_outcome_ids_for_markets,
)
from app.utils.futures_market_snapshot import (
    DERIVED_MARKET_COLUMNS,
    MARKET_ROW_COLUMNS,
    OUTCOME_LOAD_ONLY_EXTRA,
    SNAPSHOT_SCHEMA_VERSION,
    from_plain,
    is_snapshot_payload,
    to_plain,
)

NOW = datetime(2026, 9, 23, 6, 9, 0, tzinfo=timezone.utc)


def _leg(leg_id, name, prob, *, bid=None, ask=None, resolution_source=None):
    return SimpleNamespace(
        id=leg_id,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        resolution_source=resolution_source,
        is_winner=None,
        volume_24h=None,
        volume_24h_at=None,
        last_updated=NOW - timedelta(minutes=5),
        opening_captured_at=None,
        external_id=f"ext-{leg_id}",
        team_id=None,
        probability_change_24h=None,
        rank=None,
        rank_change_24h=None,
        opening_probability=None,
        calibration_probability=None,
    )


def _market(market_id, name, outcomes, *, source="kalshi", status="open"):
    values = {name_: None for name_ in MARKET_ROW_COLUMNS}
    values.update(
        id=market_id,
        name=name,
        source=source,
        status=status,
        market_type=None,
        market_metadata=None,
    )
    market = SimpleNamespace(**values)
    market.outcomes = outcomes
    market.sport = None
    return market


# ── The ship ─────────────────────────────────────────────────────────────────


class TestTheCardDropsWhatThePageRefuses:
    """The three served specimens, as the drop sees them."""

    def test_seoul_the_card_stops_offering_three_co_favourites_the_page_wont_price(
        self,
    ):
        """61960017: page prices 1 of 16; the card showed all three at 49%."""
        legs = [
            _leg(1, "Kimberly Birrell", 0.49),
            _leg(2, "Lanlana Tararudee", 0.49),
            _leg(3, "Anna Bondar", 0.49),
            _leg(4, "Yexin MA", 0.03),
        ]
        market = _market(61960017, "WTA Seoul Winner", legs)
        market.withheld_outcome_ids = [1, 2, 3]

        survivors = _drop_withheld_price_legs(market, legs)

        assert [o.id for o in survivors] == [4], (
            "the three legs the page refuses must not be on the card"
        )

    def test_singapore_the_card_stops_naming_a_leader_the_page_withholds(self):
        """61437318: the card's leader was Kasatkina, whom the page refuses.

        This is the assertion that needs the drop to happen BEFORE the leader
        pick. A withheld leg that merely inflated the divisor would be a
        rounding complaint; a withheld leg that NAMES THE CARD is the story
        inverting when the reader taps.
        """
        legs = [
            _leg(10, "Daria Kasatkina", 0.31),
            _leg(11, "Janice Tjen", 0.29),
            _leg(12, "Alexandra Eala", 0.285),
            _leg(13, "Amanda Anisimova", 0.26),
        ]
        market = _market(61437318, "WTA Singapore Singles Winner", legs)
        market.withheld_outcome_ids = [10, 11]

        survivors = _drop_withheld_price_legs(market, legs)

        assert survivors[0].name == "Alexandra Eala", (
            "the card's leader must be the page's hero, not a refused price"
        )
        assert [o.id for o in survivors] == [12, 13]

    def test_lpga_the_divisor_loses_the_hundred_legs_the_page_threw_out(self):
        """61734333: page withholds 100 of 144; every card leg was off by 0.6955.

        The drop is asserted on the DIVISOR — the surviving mass — rather than
        on a rendered percentage, because the scale step is a separate function
        with its own floor. What this rule owes the page is the same set of
        legs to divide by; what the scale then does with them is #7537's.
        """
        priced = [_leg(100 + n, f"Believed {n}", 0.02) for n in range(44)]
        refused = [_leg(200 + n, f"Refused {n}", 0.01) for n in range(100)]
        legs = priced + refused
        market = _market(61734333, "Walmart NW Arkansas Championship", legs)
        market.withheld_outcome_ids = [o.id for o in refused]

        survivors = _drop_withheld_price_legs(market, legs)

        assert len(survivors) == 44
        assert {o.id for o in survivors} == {o.id for o in priced}
        # The page divides by its own 44; so now does the card.
        assert sum(o.current_probability for o in survivors) == pytest.approx(0.88)


# ── The load-bearing distinction ─────────────────────────────────────────────


class TestMissingIsNotEmpty:
    """`None` means NOT COMPUTED and drops nothing; `[]` means REFUSED NOTHING.

    Two different facts. A consumer that collapses them either empties cards on
    every path that skips the snapshot builder, or lets a carrier that never ran
    the arms pass for a healthy board.
    """

    def test_a_carrier_that_never_ran_the_arms_keeps_every_leg(self):
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "never computed", legs)
        market.withheld_outcome_ids = None

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_a_carrier_with_no_such_attribute_at_all_keeps_every_leg(self):
        """The ORM path, and anything else that predates the wire column."""
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "no attribute", legs)
        del market.withheld_outcome_ids

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_computed_and_refused_nothing_also_keeps_every_leg(self):
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "computed, clean", legs)
        market.withheld_outcome_ids = []

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_the_two_are_distinguishable_on_the_wire(self):
        """Not computed and computed-clean must not serialize identically.

        The whole point of the distinction is that a later reader can tell them
        apart. If `to_plain` wrote `[]` for both, this class would be decorative.
        """
        legs = [_leg(1, "A", 0.6)]
        market = _market(1, "board", legs)

        not_computed = from_plain(to_plain([market]))[0]
        computed_clean = from_plain(to_plain([market], withheld_by_market={1: set()}))[0]

        assert not_computed.withheld_outcome_ids is None
        assert computed_clean.withheld_outcome_ids == []


# ── The ordering rule the first cut got wrong ────────────────────────────────


class TestTheBoardVerdictSeesTheWholeBoard:
    """A board-level screen must run before any per-leg drop thins its field.

    `classify_fabricated_book` judges whether a WHOLE BOARD's book is
    fabricated. `_drop_withheld_price_legs`'s empty-book arm removes exactly the
    1c/99c legs that verdict is made of. Run the drop first and SpaceX's sixteen
    phantom rungs become one healthy-looking leg, the card-level suppression
    never fires, and a card Alex ruled must never ship reaches the feed.
    """

    def test_the_drop_runs_after_the_fabricated_book_verdict(self):
        """Asserted on the SOURCE ORDER, because the bug is an ordering bug.

        A behavioural assertion lives in
        `test_feed_phantom_midpoint_suppression` (it is what caught this). This
        one pins the reason, so a later edit that moves the call back cannot
        pass by accident on a board with no phantoms in it.
        """
        from app.routes import feed as feed_module

        source = inspect.getsource(feed_module._score_futures)
        verdict_at = source.index("phantom_keep_mask, phantom_drop_card")
        drop_at = source.index("_drop_withheld_price_legs(market")

        assert verdict_at < drop_at, (
            "the withheld-price drop must not thin the field before "
            "classify_fabricated_book has judged the whole board"
        )

    def test_the_sports_serializer_also_drops_before_its_leader_pick(self):
        from app.routes import feed as feed_module

        source = inspect.getsource(feed_module._score_sports_mode_futures)
        drop_at = source.index("_drop_withheld_price_legs(market")
        rank_at = source.index("display_rank_order(")

        assert drop_at < rank_at

    def test_both_serializers_actually_call_it(self):
        """#4610: a membership rule in ONE serializer only moves the split.

        Card-vs-page becomes card-vs-card, which is harder to see and no better
        for the reader. Named here rather than left to the two ordering
        assertions above, because either of those would still pass if its
        `index` call were the only occurrence in the file.
        """
        from app.routes import feed as feed_module

        for serializer in (
            feed_module._score_futures,
            feed_module._score_sports_mode_futures,
        ):
            assert "_drop_withheld_price_legs(market" in inspect.getsource(
                serializer
            ), f"{serializer.__name__} does not share the page's withheld set"


# ── The batch driver ─────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _CountingSession:
    """A session that answers the trade reads and COUNTS them.

    The count is the point: decision (b) forbids a per-card query on
    `/api/feed`, so "the arms now run for the card" is only true if the query
    count does not grow with the pool.
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries = 0

    async def execute(self, _statement):
        self.queries += 1
        return _FakeResult(self.rows)


class TestTheBatchDriverCostsAConstantNumberOfQueries:
    def test_a_hundred_boards_do_not_cost_a_hundred_queries(self):
        """The property the per-card ban actually needs."""
        import asyncio

        markets = [
            _market(
                m,
                f"board {m}",
                # A 1c/99c book: a real candidate for the trade-evidence arm, so
                # the query genuinely fires rather than being screened out.
                [_leg(m * 10 + 1, "Yes", 0.5, bid=0.01, ask=0.99)],
            )
            for m in range(1, 101)
        ]
        session = _CountingSession()

        result = asyncio.run(
            withheld_price_outcome_ids_for_markets(session, markets)
        )

        assert len(result) == 100, "every board gets an answer"
        assert session.queries <= 4, (
            f"query count must not scale with the pool, got {session.queries} "
            "for 100 boards"
        )

    def test_an_empty_pool_costs_no_query_at_all(self):
        import asyncio

        session = _CountingSession()
        result = asyncio.run(withheld_price_outcome_ids_for_markets(session, []))

        assert result == {}
        assert session.queries == 0


class TestOneBadBoardNeverWipesThePool:
    """Gotcha #42, and the guard that caught the first cut.

    This driver runs OUTSIDE the serializers' per-item `try`, in the shared
    artifact builder, so an unreadable board would otherwise take the whole
    futures pass down with it.
    """

    def test_a_board_that_raises_is_omitted_and_its_siblings_answer(self):
        import asyncio

        healthy = _market(1, "healthy", [_leg(11, "Yes", 0.5, bid=0.01, ask=0.99)])
        poison = _market(2, "poison", [_leg(21, "Yes", "not-a-number")])
        also_healthy = _market(
            3, "also healthy", [_leg(31, "Yes", 0.5, bid=0.01, ask=0.99)]
        )
        session = _CountingSession()

        result = asyncio.run(
            withheld_price_outcome_ids_for_markets(
                session, [healthy, poison, also_healthy]
            )
        )

        assert 2 not in result, "the unreadable board is omitted, not guessed at"
        assert 1 in result and 3 in result, "its siblings still get answers"

    def test_the_omitted_board_then_keeps_its_prices_rather_than_losing_them(self):
        """Omission must degrade to the pre-#7632 card, never to an empty one."""
        legs = [_leg(21, "Yes", 0.5), _leg(22, "No", 0.5)]
        poison = _market(2, "poison", legs)
        row = to_plain([poison], withheld_by_market={1: {11}})
        rebuilt = from_plain(row)[0]

        assert rebuilt.withheld_outcome_ids is None
        assert _drop_withheld_price_legs(rebuilt, legs) == legs


class TestTheBatchedAnswerMatchesThePerMarketOne:
    """Both paths call the same pure halves, so they cannot drift.

    The risk the split introduces is a batched trade dict carrying rows for
    OTHER boards. Every read is keyed on the leg's own id, and
    `_closest_trade_by_outcome` skips ids outside its own candidate list — this
    pins both.
    """

    def test_a_wider_trade_dict_does_not_change_one_boards_verdict(self):
        legs = [_leg(1, "Yes", 0.5, bid=0.01, ask=0.99)]
        market = _market(7, "board", legs)
        candidates = _unsupported_price_candidates(market)

        narrow = _unsupported_price_verdicts(market, candidates, {})
        wide = _unsupported_price_verdicts(
            market, candidates, {999: 0.42, 1000: 0.9}
        )

        assert narrow == wide

    def test_the_midpoint_fold_skips_rows_belonging_to_other_boards(self):
        # A 20c/80c book midpointing to a confident-looking 50% — the shape the
        # midpoint arm exists for, so this fixture genuinely produces a
        # candidate rather than skipping and convicting nothing.
        legs = [_leg(1, "Yes", 0.5, bid=0.2, ask=0.8)]
        market = _market(7, "board", legs, source="polymarket")
        candidates = _refuted_midpoint_candidates(market)
        assert candidates, "fixture must produce a midpoint candidate"

        own_only = _closest_trade_by_outcome(candidates, [(1, 0.5)])
        with_foreign = _closest_trade_by_outcome(
            candidates, [(1, 0.5), (999, 0.01), (1000, 0.99)]
        )

        assert own_only == with_foreign
        assert set(with_foreign) <= {o.id for o in candidates}

    def test_the_midpoint_verdict_half_is_also_blind_to_foreign_ids(self):
        """The sibling of the unsupported-arm control, and it needs its own.

        `_closest_trade_by_outcome` filters foreign rows out of the FOLD; this
        asserts the VERDICT half is independently keyed on the leg's own id, so
        the two halves are not relying on each other to be safe. Caught as an
        unused import — the arm was split and only one of its two pure halves
        had a test.
        """
        legs = [_leg(1, "Yes", 0.5, bid=0.2, ask=0.8)]
        market = _market(7, "board", legs, source="polymarket")
        candidates = _refuted_midpoint_candidates(market)
        assert candidates, "fixture must produce a midpoint candidate"

        narrow = _refuted_midpoint_verdicts(market, candidates, {1: 0.5})
        wide = _refuted_midpoint_verdicts(
            market, candidates, {1: 0.5, 999: 0.01, 1000: 0.99}
        )

        assert narrow == wide
        assert wide <= {o.id for o in candidates}

    def test_a_non_midpoint_venue_has_no_candidates_so_sends_no_ids(self):
        """The venue gate moved into the candidate helper; it must still bite."""
        # Byte-identical to the fixture one test up, venue apart — so the
        # assertion turns on the gate and nothing else.
        legs = [_leg(1, "Yes", 0.5, bid=0.2, ask=0.8)]
        market = _market(7, "board", legs, source="datagolf")

        assert _refuted_midpoint_candidates(market) == []


# ── The wire ─────────────────────────────────────────────────────────────────


class TestTheWireCarriesTheVerdictAndNotTheColumns:
    def test_the_four_read_columns_are_loaded_but_not_serialized(self):
        """Four columns in, one id list out.

        They must be LOADED — every arm reads them through `getattr(..., None)`,
        which on a `load_only`-restricted row does not raise, it silently
        refuses nothing, which is the card/page divergence all over again. And
        they must NOT be on the wire: this artifact is size-capped and the
        verdict is one list per market, not four values per leg.
        """
        for column in (
            "resolution_source",
            "volume_24h",
            "volume_24h_at",
            "is_winner",
        ):
            assert column in OUTCOME_LOAD_ONLY_EXTRA, (
                f"{column} must be loaded for the withheld-price arms"
            )

        from app.utils.futures_market_snapshot import OUTCOME_ROW_COLUMNS

        for column in ("volume_24h_at", "is_winner"):
            assert column not in OUTCOME_ROW_COLUMNS, (
                f"{column} is read at build time only and must not reach the wire"
            )

    def test_the_verdict_is_a_market_level_derived_column(self):
        assert "withheld_outcome_ids" in DERIVED_MARKET_COLUMNS

    def test_the_schema_version_was_bumped_for_the_new_column(self):
        """A v7 payload is a row of the wrong width and must not decode as v8."""
        assert SNAPSHOT_SCHEMA_VERSION >= 8

        stale = to_plain([_market(1, "board", [_leg(1, "A", 0.5)])])
        stale["v"] = 7

        assert is_snapshot_payload(stale) is False

    def test_the_ids_survive_a_round_trip_and_are_sorted(self):
        """Sorted because this lands in a digest-keyed shared cache.

        A set's iteration order is not stable across processes, so an unsorted
        list would make two otherwise-identical builds produce two payloads.
        """
        legs = [_leg(n, f"leg {n}", 0.1) for n in (5, 3, 9, 1)]
        market = _market(42, "board", legs)

        rebuilt = from_plain(to_plain([market], withheld_by_market={42: {9, 3, 5}}))[0]

        assert rebuilt.withheld_outcome_ids == [3, 5, 9]

    def test_the_artifact_is_still_eligible_for_the_shared_cache(self):
        """A nested list of ints is new for this payload — prove it passes.

        `assert_plain_data` is what makes the artifact shareable across workers
        at all. If the new column made it INELIGIBLE the failure would be
        invisible to every other test here: the cache would simply never store,
        `/api/feed` would rebuild on every request, and the only symptom would
        be latency. So the gate is asserted directly rather than inferred from
        a passing round trip.
        """
        from app.utils.principal_independent_cache import assert_plain_data

        market = _market(1, "board", [_leg(1, "A", 0.5), _leg(2, "B", 0.5)])

        assert_plain_data(to_plain([market], withheld_by_market={1: {2}}))
        assert_plain_data(to_plain([market], withheld_by_market={1: set()}))
        assert_plain_data(to_plain([market]))

    def test_a_market_absent_from_the_map_serializes_as_unknown_not_clean(self):
        """Gotcha #53: the honest answer to a builder bug is "I do not know"."""
        market = _market(1, "board", [_leg(1, "A", 0.5)])

        rebuilt = from_plain(to_plain([market], withheld_by_market={999: {7}}))[0]

        assert rebuilt.withheld_outcome_ids is None


# ── Controls ─────────────────────────────────────────────────────────────────


class TestControls:
    def test_a_settled_board_is_untouched(self):
        """A settled board is a RESULT, and a result shows what ran."""
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "settled", legs, status="completed")
        market.withheld_outcome_ids = [1, 2]

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_an_all_withheld_board_keeps_its_legs_rather_than_emptying(self):
        """Fails open: the harmful direction is taking a card's numbers away.

        The page renders such a board as an all-`-` table. The card keeps what
        it has and is at worst no worse than today, which is where it already
        is — a card with nothing on it would be a new defect.
        """
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "all refused", legs)
        market.withheld_outcome_ids = [1, 2]

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_a_supported_zero_leg_is_kept(self):
        """ABSENT IS NOT ZERO (ruling 051, #6195).

        A leg the field has priced at nothing is an ANSWER and the page prints
        `0%` for it. Only the arms decide what is refused; this function must
        never infer a refusal from the number itself.
        """
        legs = [_leg(1, "Eliminated", 0.0), _leg(2, "Alive", 1.0)]
        market = _market(1, "PLL-shaped", legs)
        market.withheld_outcome_ids = []

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_an_id_in_the_list_that_is_not_on_the_board_changes_nothing(self):
        """A stale snapshot whose id list outlived its legs must be inert."""
        legs = [_leg(1, "A", 0.6), _leg(2, "B", 0.4)]
        market = _market(1, "board", legs)
        market.withheld_outcome_ids = [77, 88]

        assert _drop_withheld_price_legs(market, legs) == legs

    def test_a_board_with_no_outcomes_does_not_raise(self):
        market = _market(1, "empty", [])
        market.withheld_outcome_ids = [1]

        assert _drop_withheld_price_legs(market, []) == []
