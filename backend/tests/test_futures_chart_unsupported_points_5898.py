"""#5898 — the chart stops drawing the price the ladder underneath it refuses.

WHAT A READER CAN DO TODAY. ``/futures/8641774`` (*Brazil Série B: Winner*)
withholds Ceará's price under #5876, so the outcome row prints ``—``. Tick that
row's checkbox and the Probability Trend draws Ceará's line ending at ``0.4700``
— the exact number the table one inch below has just declined to state. Nine of
the ten series that page charts end on a refused value (production, 20:48Z on
2026-09-13).

EVERY SNAPSHOT ROW IN THIS FILE IS A PRODUCTION ROW, read from
``futures_odds_snapshots`` for outcome 46856662 (Ceará) at 20:58Z on 2026-09-13,
because the shape of the defect IS the argument: a price and a trade written by
the same insert that contradict each other. The refused rows are the 2026-07-21
tail; the honest rows are the 2026-07-18 plateau, where the same outcome quotes a
0.0040/0.0050 book and a 0.0020 trade against a 0.0045 price.

WHAT WOULD MAKE THIS FILE VACUOUS, stated so a later reader can check it rather
than trust it:

- If the rule dropped points on the fabricated SHAPE alone, or on "this outcome
  is withheld in the ladder", it would take the honest 2026-07-18 half of the
  same outcome's own series with it. Those rows are asserted KEPT, by value, in
  the same tests that assert the tail goes.
- If ``is_fabricated_midpoint``'s constant or ``_DISPLAY_ROUNDING`` ever moved so
  far that the fixture stopped matching, every route test below would pass by
  drawing a series with nothing to drop. ``TestTheFixtureItselfStillCarriesTheDefect``
  asserts the predicate's verdict on each fixture row directly, so that failure
  is loud instead of silent.
- If the filter were wired into the handler but never reached (the #5876 lesson:
  every other test in that file passed with the new arm wired to nothing), the
  route tests would still pass on the unit rule. They assert the SERVED payload's
  points, never the predicate.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.models import FuturesMarket, FuturesOddsSnapshot
from app.routes import futures as futures_route
from app.utils.futures_unsupported_price import snapshot_price_is_unsupported

# ── Production rows, outcome 46856662 (Ceará), market 8641774 ────────────────
# (probability, yes_bid, yes_ask, last_price)
#
# The 2026-07-21 tail: a midpoint of a 0.002/0.938 book, against a 0.0040 trade
# the same writer recorded. This is what the chart's right-hand edge shows.
_REFUSED_TAIL = [
    (0.456000, 0.0040, 0.9080, 0.0040),
    (0.446500, 0.0020, 0.8910, 0.0040),
    (0.457500, 0.0020, 0.9130, 0.0040),
    (0.458000, 0.0020, 0.9140, 0.0040),
    (0.489000, 0.0020, 0.9760, 0.0040),
    (0.470000, 0.0020, 0.9380, 0.0040),
]
# The 2026-07-18 plateau: a 0.0010-wide book and a trade 0.0025 away from the
# price. Honest by both terms — not a fabricated shape, and not refuted.
_HONEST_HEAD = [(0.004500, 0.0040, 0.0050, 0.0020)] * 6


def _snap(oid, minutes, prob, bid, ask, last, bookmaker="polymarket"):
    return SimpleNamespace(
        outcome_id=oid,
        bookmaker=bookmaker,
        probability=prob,
        yes_bid=bid,
        yes_ask=ask,
        last_price=last,
        captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc)
        + timedelta(minutes=minutes),
    )


def _series(oid, rows, start=0, bookmaker="polymarket"):
    return [
        _snap(oid, start + i * 60, *row, bookmaker=bookmaker)
        for i, row in enumerate(rows)
    ]


def _outcome(
    oid,
    name="Ceará",
    prob=0.47,
    resolution_source=None,
    is_winner=None,
    external_id=None,
):
    return SimpleNamespace(
        id=oid,
        name=name,
        team_id=None,
        probability_change_24h=None,
        current_probability=prob,
        current_yes_bid=0.0020,
        current_yes_ask=0.9380,
        resolution_source=resolution_source,
        is_winner=is_winner,
        # `FuturesOutcome.external_id` is a mapped column, so a real row always
        # HAS one — this double simply never modelled it. `/history` reads it to
        # spell out truncated club names (#6479 chart half), and `None` is the
        # faithful value here: these rows are a Polymarket field, whose ids are
        # condition hashes that carry no club, so the repair no-ops and every
        # assertion in this file is about exactly the series it was about before.
        external_id=external_id,
    )


def _market(outcomes, id=8641774, source="polymarket"):
    return SimpleNamespace(
        id=id,
        name="Brazil Série B: Winner",
        source=source,
        outcomes=outcomes,
        market_metadata=None,
        resolution_date=None,
    )


class _Result:
    def __init__(self, value=None, rows=()):
        self._value = value
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self


class _Session:
    """Answers each ``execute`` from a queue, so a handler's Nth query is scripted.

    The last entry repeats, which is what lets the sparse-extend tiers re-ask for
    the same window without the test having to know how many tiers ran.
    """

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        # #7747 (chart shares the page's whole withheld set): the handler now
        # asks `_withheld_price_outcome_ids`, whose Polymarket arm (#5876)
        # takes ONE trade read on this board's empty-book leg before the
        # snapshot query — the same read the page makes. A column select is
        # that read; it is answered empty (no trade rows, which fails OPEN, so
        # nothing in this file is withheld that was not withheld before) and
        # does not consume the scripted queue, which is keyed to the snapshot
        # reads alone.
        if statement.column_descriptions[0]["expr"] is not FuturesMarket and (
            statement.column_descriptions[0]["expr"] is not FuturesOddsSnapshot
        ):
            return _Result(rows=[])
        self.calls += 1
        idx = min(self.calls - 1, len(self._results) - 1)
        return self._results[idx]


async def _history(db, hours=8760):
    """Call the handler the way FastAPI does — every Query parameter RESOLVED.

    Omitting one hands the function the unresolved ``Query`` default object,
    which is not None and not an int. ``top_n`` then raises on ``min()``, and
    ``outcome_id`` silently reads as a single-outcome filter that suppresses the
    settled winner freeze. Both are traps this file must not fall into while
    claiming to measure the served payload.
    """
    return await futures_route.get_futures_history(
        8641774, outcome_id=None, hours=hours, top_n=10, champion=None, db=db
    )


def _points(payload, outcome_id):
    for entry in payload["outcomes"]:
        if entry["outcome_id"] == outcome_id:
            return [round(p["probability"], 6) for p in entry["history"]]
    return None


class TestTheFixtureItselfStillCarriesTheDefect:
    """The strawman guard. Every route test below is worthless if these fixtures
    stopped being what the issue described, and that can happen without anyone
    touching this file — ``is_fabricated_midpoint``'s spread constant and
    ``_DISPLAY_ROUNDING`` both live elsewhere."""

    @pytest.mark.parametrize("prob,bid,ask,last", _REFUSED_TAIL)
    def test_every_tail_row_is_refused_on_its_own_columns(self, prob, bid, ask, last):
        assert (
            snapshot_price_is_unsupported("polymarket", None, prob, bid, ask, last)
            is True
        )

    @pytest.mark.parametrize("prob,bid,ask,last", _HONEST_HEAD[:1])
    def test_every_head_row_is_honest_on_its_own_columns(self, prob, bid, ask, last):
        assert (
            snapshot_price_is_unsupported("polymarket", None, prob, bid, ask, last)
            is False
        )


class TestTheRuleAskedOfOneRow:
    def test_a_null_trade_fails_open(self):
        """Gotcha #53 survives the port: "the venue told us nothing at this
        capture" is not "the venue said zero". 3,220 of the 3,898 fabricated
        legs #5876 measured are in this state."""
        assert (
            snapshot_price_is_unsupported("polymarket", None, 0.47, 0.002, 0.938, None)
            is False
        )

    def test_a_zero_trade_is_evidence_and_refutes(self):
        """The manufactured coin-flip: 0.5000 off a 0.0/1.0 book with a recorded
        zero trade. Polymarket's writer passes ``last_trade_price`` straight
        through, so a stored 0.0 is the venue speaking."""
        assert (
            snapshot_price_is_unsupported("polymarket", None, 0.5, 0.0, 1.0, 0.0)
            is True
        )

    def test_a_trade_that_prints_as_the_served_percent_supports_it(self):
        assert (
            snapshot_price_is_unsupported(
                "polymarket", None, 0.47, 0.002, 0.938, 0.4680
            )
            is False
        )

    def test_a_graded_row_is_never_refused(self):
        """Settled means settled — once ``resolution_source`` is set the number is
        a settlement value, and withholding it would delete a result."""
        assert (
            snapshot_price_is_unsupported(
                "polymarket", "api_settlement", 0.47, 0.002, 0.938, 0.004
            )
            is False
        )

    def test_the_kalshi_arm_refuses_a_lone_ask_with_a_zero_trade(self):
        assert snapshot_price_is_unsupported("kalshi", None, 1.0, 0.0, 1.0, 0.0) is True

    def test_the_kalshi_arm_fails_open_without_a_recorded_trade(self):
        assert (
            snapshot_price_is_unsupported("kalshi", None, 1.0, 0.0, 1.0, None) is False
        )

    def test_a_sportsbook_row_is_screened_by_neither_arm(self):
        """Both arms key on a venue string. A DraftKings row carries no book
        columns at all and must pass through whatever its numbers look like."""
        assert (
            snapshot_price_is_unsupported("draftkings", None, 0.47, None, None, None)
            is False
        )


class TestTheFilterOverASeries:
    def test_the_refused_tail_goes_and_the_honest_head_stays(self):
        out = _outcome(46856662)
        snaps = _series(46856662, _HONEST_HEAD) + _series(
            46856662, _REFUSED_TAIL, start=600
        )
        kept = futures_route._drop_unsupported_snapshot_points(snaps, [out])
        assert [round(float(s.probability), 6) for s in kept] == [0.0045] * 6

    def test_an_outcome_the_caller_did_not_load_keeps_every_point(self):
        """Ignorance is not a reason to delete a reader's point: an unknown id
        would otherwise be screened as ungraded, i.e. as a candidate."""
        snaps = _series(46856662, _REFUSED_TAIL)
        assert futures_route._drop_unsupported_snapshot_points(snaps, []) == snaps

    def test_a_graded_outcomes_series_survives_intact(self):
        out = _outcome(46856662, resolution_source="api_settlement")
        snaps = _series(46856662, _REFUSED_TAIL)
        assert len(futures_route._drop_unsupported_snapshot_points(snaps, [out])) == 6

    def test_one_timestamp_keeps_its_honest_book_when_a_venue_row_is_refused(self):
        """THE REASON THE KEY IS THE ROW'S OWN BOOKMAKER. Both chart endpoints
        average every book at one timestamp into one consensus point. Screening
        on the market's source would take the sportsbook row down with the
        refuted Polymarket one."""
        out = _outcome(46856662)
        refused = _snap(46856662, 0, 0.470, 0.0020, 0.9380, 0.0040)
        honest = _snap(46856662, 0, 0.0050, None, None, None, bookmaker="draftkings")
        kept = futures_route._drop_unsupported_snapshot_points([refused, honest], [out])
        assert [s.bookmaker for s in kept] == ["draftkings"]

    def test_each_venues_row_is_judged_by_its_own_venues_rule(self):
        """ANY single hard-coded venue string here would survive the test above,
        because a sportsbook row carries no book columns and is spared by both
        arms whatever you call it. These two rows are each refused by their OWN
        arm and SPARED by the other's, so exactly one of them survives any
        mis-keying:

          kalshi row (1.0 off a 0.0/1.0 book, zero trade) — the lone-ask rule
              refuses it; the midpoint rule spares it (1.0 is not the 0.5
              midpoint);
          polymarket row (0.47 off a 0.002/0.938 book, 0.004 trade) — the
              midpoint rule refuses it; the lone-ask rule spares it (the bid is
              not zero).
        """
        out = _outcome(46856662)
        kalshi = _snap(46856662, 0, 1.0, 0.0, 1.0, 0.0, bookmaker="kalshi")
        poly = _snap(46856662, 0, 0.470, 0.0020, 0.9380, 0.0040)
        assert (
            futures_route._drop_unsupported_snapshot_points([kalshi, poly], [out]) == []
        )


@pytest.mark.asyncio
class TestTheServedChart:
    """These assert the PAYLOAD, never the predicate. A filter wired into the
    module but not reached by the handler passes every test above and fails
    every test here."""

    async def test_the_series_no_longer_ends_at_the_value_the_table_withholds(self):
        out = _outcome(46856662)
        snaps = _series(46856662, _HONEST_HEAD) + _series(
            46856662, _REFUSED_TAIL, start=600
        )
        db = _Session(_Result(value=_market([out])), _Result(rows=snaps))
        payload = await _history(db)
        served = _points(payload, 46856662)
        assert served == [0.0045] * 6
        assert 0.470 not in served

    async def test_a_series_with_nothing_left_is_not_charted_at_all(self):
        """Notice 34's direction, and what #5968 already does one surface over:
        if a number cannot be shown honestly, leave the space empty."""
        out = _outcome(46856662)
        db = _Session(
            _Result(value=_market([out])),
            _Result(rows=_series(46856662, _REFUSED_TAIL)),
        )
        payload = await _history(db)
        assert payload["outcomes"] == []
        assert payload["total_data_points"] == 0

    async def test_the_point_count_and_sparse_flag_describe_the_surviving_points(self):
        out = _outcome(46856662)
        snaps = _series(46856662, _HONEST_HEAD) + _series(
            46856662, _REFUSED_TAIL, start=600
        )
        db = _Session(_Result(value=_market([out])), _Result(rows=snaps))
        payload = await _history(db)
        assert payload["total_data_points"] == 6
        assert payload["sparse"] is True

    async def test_the_sparse_window_widens_on_real_points_not_refused_ones(self):
        """The filter runs BEFORE the extend tiers on purpose. A window holding
        40 fabricated points and 2 real ones is a thin chart, and counting the
        fabrications would stop the handler reaching back for real history."""
        out = _outcome(46856662)
        thin = _Result(rows=_series(46856662, _REFUSED_TAIL * 7))
        wide = _Result(
            rows=_series(46856662, _HONEST_HEAD) + _series(46856662, _REFUSED_TAIL, 600)
        )
        db = _Session(_Result(value=_market([out])), thin, wide)
        payload = await _history(db, hours=168)
        assert payload["auto_extended"] is True
        assert _points(payload, 46856662) == [0.0045] * 6

    async def test_a_graded_winners_completed_journey_is_untouched(self):
        """Two standing rulings meet here: the graded exemption in the predicate,
        and ``_apply_settled_winner_freeze`` resolving the champion's line to 1.0
        AFTER this filter. A settled chart shows the completed journey."""
        champ = _outcome(46856662, resolution_source="api_settlement", is_winner=True)
        db = _Session(
            _Result(value=_market([champ])),
            _Result(rows=_series(46856662, _REFUSED_TAIL)),
        )
        payload = await _history(db)
        served = _points(payload, 46856662)
        assert served[:6] == [round(r[0], 6) for r in _REFUSED_TAIL]
        assert served[-1] == 1.0

    async def test_the_cross_source_chart_drops_it_too(self):
        """``/multi-history`` is the sharper half: it merges outcomes ACROSS
        source markets, so a refused midpoint does not just draw its own false
        line — it pulls the blended line toward a number our ladder refuses."""
        poly = _outcome(46856662, name="Ceará")
        book = _outcome(999001, name="Ceará", prob=0.005)
        markets = [
            _market([poly], id=8641774),
            _market([book], id=8641775, source="odds_api"),
        ]
        snaps = _series(46856662, _REFUSED_TAIL) + _series(
            999001, _HONEST_HEAD, bookmaker="draftkings"
        )

        class _Multi(_Session):
            async def execute(self, statement):
                self.calls += 1
                if self.calls == 1:
                    return _Result(rows=markets)
                return _Result(rows=snaps)

        payload = await futures_route.get_multi_market_history(
            market_ids="8641774,8641775", hours=8760, top_n=10, db=_Multi()
        )
        charted = [p["probability"] for o in payload["outcomes"] for p in o["history"]]
        assert charted, "the honest sportsbook line must survive"
        assert all(round(v, 6) == 0.0045 for v in charted)


#: Every chart reader in `app/routes/futures.py`, by name. This list is the
#: guard's whole point and is not a convenience: `/history` and `/multi-history`
#: have route tests above, but `/probability-timeline` and
#: `/cross-source-timeline` are expensive to drive and would otherwise ship
#: unguarded — which is the exact shape of the bug the file's own comment records
#: at `_EXTEND_TIERS` ("which is how `/multi-history` came to lack it").
_CHART_READERS = {
    "get_futures_history",
    "get_multi_market_history",
    "get_probability_timeline",
    "get_cross_source_timeline",
}


def _count_whole_snapshot_selects(node) -> int:
    """``select(FuturesOddsSnapshot)`` — the ENTITY, not columns off it.

    This is the structural line between the two populations that touch this
    table. A chart reader wants whole rows over a window; the two price-support
    helpers want one aggregated column per outcome
    (``select(FuturesOddsSnapshot.outcome_id, func.max(...))``). Matching on the
    name alone would sweep them in, and excluding on the word "max" would sweep
    out any handler that happens to call the builtin.
    """
    seen = 0
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Name) and call.func.id == "select"):
            continue
        if any(
            isinstance(arg, ast.Name) and arg.id == "FuturesOddsSnapshot"
            for arg in call.args
        ):
            seen += 1
    return seen


def _count_filter_calls(node) -> int:
    return sum(
        1
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_drop_unsupported_snapshot_points"
    )


def _series_reading_functions():
    """Functions that pull SNAPSHOT ROWS to draw a line, found rather than listed.

    The value is ``(entity selects, filter calls)`` and they are COUNTED, not
    tested for presence. Three of the four readers fetch twice — the requested
    window, then a wider one when the first looks sparse — and a presence test
    calls a handler covered when only one of its two fetches is filtered. That is
    not a hypothetical: the sparse-extend path is the one that REPLACES the
    series wholesale, so an unfiltered second fetch serves every refused point
    the first fetch just removed.
    """
    tree = ast.parse(inspect.getsource(futures_route))
    return {
        node.name: (_count_whole_snapshot_selects(node), _count_filter_calls(node))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _count_whole_snapshot_selects(node)
    }


class TestEveryChartReaderIsCovered:
    def test_the_population_is_the_four_known_readers(self):
        """Fails on a FIFTH chart endpoint as loudly as on a missing filter, so
        the next one cannot be added without this decision being made again. It
        also stops this guard going vacuous by matching nothing."""
        assert set(_series_reading_functions()) == _CHART_READERS

    @pytest.mark.parametrize("name", sorted(_CHART_READERS))
    def test_every_snapshot_fetch_in_each_reader_is_filtered(self, name):
        selects, filters = _series_reading_functions()[name]
        assert filters == selects, (
            f"{name} fetches whole snapshot rows {selects}x and filters {filters}x; "
            "an unfiltered fetch serves refused points"
        )
