"""ux/1069 (#2960) — /weather draws real captures or no line at all.

WHAT WAS SHIPPED. `components/weather/data.ts` held `sparkFrom(seed, end)`: a
seeded LCG that produced a 14-point "price history" in which exactly ONE point,
the last, was real. It walked a noise path from a random-offset start toward
the current price, and both the hero card and every wild card rendered that
path in the same ink a real history would use. The hero seeded it on the card's
index in the 5.5s rotation, the wild cards on `i * 137 + 42`, their position in
the grid — so a market's chart was a function of where its card sat on the
page. On a site whose promise is "this is what the market thinks", that is
invented data, and D27's rule cuts harder here than for a broken chart: an
error must never look like data, and fabricated data is worse than an error
because it cannot be doubted.

THE REPLACEMENT. `_leader_histories` reads `futures_odds_snapshots` — rows the
pollers captured from the market — for the SAME outcome whose probability the
card prints, and the endpoints ship them as `history`. Below
`MIN_HISTORY_POINTS` real captures the market is absent from the map and the
card is handed `[]`, which the frontend renders as nothing: no placeholder, no
flat line, no empty chart slot.

WHY THESE ASSERTIONS. A test that only checked "history is a list of numbers"
would have passed on the generator, which also produced a list of numbers. What
separates a real series from a manufactured one is where the numbers COME FROM,
so every test here is about provenance:

  * the values are the captured rows, unrounded-through, not a function of the
    printed probability;
  * the series charts the leader outcome, not some other outcome's ladder rung;
  * a second bookmaker's raw rows never get interleaved into one line;
  * too few captures yields nothing, not a shorter fake;
  * and the endpoints emit the key even when empty, because an absent key must
    keep meaning "cache predates the field", never "invent one".
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import weather as weather_route
from app.routes.weather import (
    MAX_HISTORY_POINTS,
    MIN_HISTORY_POINTS,
    _downsample,
    _leader_histories,
    _leader_outcome,
    _leader_outcome_name,
    _highest_prob,
)

pytestmark = pytest.mark.asyncio


def _title_date(days_ahead):
    """A future month-day-year string. Gotcha #44: offset first, then format."""
    when = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return f"{when:%B} {when.day}, {when.year}"


_RAIN_TITLE = f"Where will it rain on {_title_date(5)}?"


def _outcome(name, probability, *, outcome_id):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        probability_change_24h=None,
        rank=1,
    )


def _market(*, market_id, name, outcomes, source="polymarket", resolution_date=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=f"px{market_id}",
        source=source,
        category="weather",
        llm_sport_category="weather",
        outcomes=outcomes,
        resolution_date=resolution_date or now + timedelta(days=14),
        updated_at=now,
        status="open",
    )


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CapturingDb:
    """A session that answers the ONE column query `_leader_histories` issues.

    It also records the statement, because half of what this fix has to get
    right is *which* rows are asked for — a query that fetched every outcome's
    snapshots and filtered afterwards would return the same answer and cost the
    hero a table scan.
    """

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _RowsResult(self._rows)


def _snap(outcome_id, probability, *, bookmaker="polymarket"):
    """One captured row, in the column order `_leader_histories` selects."""
    return (outcome_id, bookmaker, probability)


class _ScalarRows:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

    def unique(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


def _result_for(items, rows):
    """A Result serving the entity query out of `scalars()` and the capture
    query out of `all()` — two different questions, two different answers."""
    return SimpleNamespace(
        scalars=lambda: _ScalarRows(items),
        all=lambda: rows,
        first=lambda: items[0] if items else None,
    )


# The Aug-29 rain market as production held it. Minneapolis is the leader at
# 0.785; New York City at 0.045 is the bottom of the ladder and is here so a
# mutation that charts `outcomes[0]` or `outcomes[-1]` bites.
_SEATTLE, _MINNEAPOLIS, _MIAMI, _NYC = 1, 2, 3, 4
_RAIN_OUTCOMES = [
    _outcome("Seattle", 0.740, outcome_id=_SEATTLE),
    _outcome("Minneapolis", 0.785, outcome_id=_MINNEAPOLIS),
    _outcome("Miami", 0.720, outcome_id=_MIAMI),
    _outcome("New York City", 0.045, outcome_id=_NYC),
]


# ---------------------------------------------------------------------------
# 1. The ship — the line is the captures
# ---------------------------------------------------------------------------


class TestTheLineIsTheCaptures:
    async def test_the_points_are_the_captured_prices(self):
        market = _market(market_id=59704867, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.612),
            _snap(_MINNEAPOLIS, 0.703),
            _snap(_MINNEAPOLIS, 0.785),
        ])

        histories = await _leader_histories(db, [market])

        # Exactly the captures, scaled to the 0-100 the card draws on. Nothing
        # smoothed, nothing interpolated, nothing appended.
        assert histories == {59704867: [61.2, 70.3, 78.5]}

    async def test_the_series_belongs_to_the_outcome_whose_number_is_printed(self):
        """A line under a number has to be that number's line.

        The card prints Minneapolis' 78%. New York City's captures are also in
        the result set here — they are rows on the same market — and charting
        them under the 78% would be a new way to lie with the same pixels.
        """
        market = _market(market_id=59704867, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([
            _snap(_NYC, 0.011),
            _snap(_MINNEAPOLIS, 0.612),
            _snap(_NYC, 0.030),
            _snap(_MINNEAPOLIS, 0.703),
            _snap(_NYC, 0.045),
            _snap(_MINNEAPOLIS, 0.785),
        ])

        histories = await _leader_histories(db, [market])

        assert histories == {59704867: [61.2, 70.3, 78.5]}
        assert _leader_outcome(market).id == _MINNEAPOLIS
        assert _leader_outcome_name(market) == "Minneapolis"
        assert _highest_prob(market) == 78

    async def test_only_the_leader_outcome_is_queried_for(self):
        """The query asks for one outcome per market, not for the whole ladder.

        Compiled and read as text because that is the only place the WHERE
        clause is observable without a database, and the shape of the ask is
        the difference between four snapshot rows and forty-two.
        """
        market = _market(market_id=59704867, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([_snap(_MINNEAPOLIS, 0.7)] * MIN_HISTORY_POINTS)

        await _leader_histories(db, [market])

        assert len(db.statements) == 1
        compiled = db.statements[0].compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled)
        assert "futures_odds_snapshots" in sql
        assert "captured_at" in sql
        # The leader's id is in the IN-list; the ladder's other rungs are not.
        assert str(_MINNEAPOLIS) in sql
        for other in (_SEATTLE, _MIAMI, _NYC):
            assert f"({other}," not in sql and f", {other})" not in sql

    async def test_two_markets_do_not_share_a_line(self):
        rain = _market(market_id=1, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        volcano = _market(
            market_id=2,
            name="Major volcano eruption in 2026?",
            outcomes=[
                _outcome("At least 1", 0.110, outcome_id=11),
                _outcome("At least 2", 0.680, outcome_id=12),
            ],
        )
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.60),
            _snap(12, 0.50),
            _snap(_MINNEAPOLIS, 0.70),
            _snap(12, 0.60),
            _snap(_MINNEAPOLIS, 0.785),
            _snap(12, 0.68),
        ])

        histories = await _leader_histories(db, [rain, volcano])

        assert histories == {1: [60.0, 70.0, 78.5], 2: [50.0, 60.0, 68.0]}


# ---------------------------------------------------------------------------
# 2. When there is nothing honest to draw
# ---------------------------------------------------------------------------


class TestTooFewCapturesDrawNothing:
    @pytest.mark.parametrize("count", list(range(MIN_HISTORY_POINTS)))
    async def test_below_the_floor_the_market_is_absent(self, count):
        """Absent, not shortened. The caller turns absence into `[]`, and `[]`
        into no chart element at all — the generator's whole crime was that it
        always had something to draw."""
        market = _market(market_id=7, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([_snap(_MINNEAPOLIS, 0.5 + i / 100) for i in range(count)])

        assert await _leader_histories(db, [market]) == {}

    async def test_at_the_floor_it_draws(self):
        """The survivor. A floor that swallowed everything would also pass every
        test above it."""
        market = _market(market_id=7, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.5 + i / 100) for i in range(MIN_HISTORY_POINTS)
        ])

        histories = await _leader_histories(db, [market])

        assert len(histories[7]) == MIN_HISTORY_POINTS

    async def test_a_market_with_no_priced_outcomes_asks_for_nothing(self):
        """No leader, no query — and no crash on the way to no query."""
        market = _market(
            market_id=8,
            name=_RAIN_TITLE,
            outcomes=[_outcome("Seattle", None, outcome_id=99)],
        )
        db = _CapturingDb([])

        assert await _leader_histories(db, [market]) == {}
        assert db.statements == []

    async def test_no_markets_at_all_asks_for_nothing(self):
        db = _CapturingDb([])
        assert await _leader_histories(db, []) == {}
        assert db.statements == []


# ---------------------------------------------------------------------------
# 3. One book per line
# ---------------------------------------------------------------------------


class TestOneBookPerLine:
    async def test_a_foreign_books_rows_are_not_interleaved(self):
        """`FuturesOddsSnapshot.probability` is a RAW, vig-inclusive reading
        from one bookmaker, never a blend (see the column's own comment, and
        #1844, which shipped because a reader forgot). Two books' captures
        merged by time would render the spread between them as movement."""
        market = _market(
            market_id=9, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES, source="polymarket"
        )
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.60, bookmaker="polymarket"),
            _snap(_MINNEAPOLIS, 0.31, bookmaker="kalshi"),
            _snap(_MINNEAPOLIS, 0.70, bookmaker="polymarket"),
            _snap(_MINNEAPOLIS, 0.33, bookmaker="kalshi"),
            _snap(_MINNEAPOLIS, 0.785, bookmaker="polymarket"),
        ])

        assert await _leader_histories(db, [market]) == {9: [60.0, 70.0, 78.5]}

    async def test_a_kalshi_market_charts_kalshi(self):
        """The mirror arm. A filter hard-coded to one source would pass the
        test above and blank every card from the other."""
        market = _market(
            market_id=10, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES, source="kalshi"
        )
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.60, bookmaker="polymarket"),
            _snap(_MINNEAPOLIS, 0.31, bookmaker="kalshi"),
            _snap(_MINNEAPOLIS, 0.33, bookmaker="kalshi"),
            _snap(_MINNEAPOLIS, 0.35, bookmaker="kalshi"),
        ])

        assert await _leader_histories(db, [market]) == {10: [31.0, 33.0, 35.0]}

    async def test_a_book_that_leaves_too_few_rows_draws_nothing(self):
        """Filtering can take a series below the floor, and then it must fall
        through the floor rather than be topped up from the other book."""
        market = _market(
            market_id=11, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES, source="kalshi"
        )
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.60, bookmaker="polymarket"),
            _snap(_MINNEAPOLIS, 0.70, bookmaker="polymarket"),
            _snap(_MINNEAPOLIS, 0.31, bookmaker="kalshi"),
        ])

        assert await _leader_histories(db, [market]) == {}

    async def test_a_null_price_is_skipped_not_charted_as_zero(self):
        market = _market(market_id=12, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([
            _snap(_MINNEAPOLIS, 0.60),
            _snap(_MINNEAPOLIS, None),
            _snap(_MINNEAPOLIS, 0.70),
            _snap(_MINNEAPOLIS, 0.785),
        ])

        assert await _leader_histories(db, [market]) == {12: [60.0, 70.0, 78.5]}


# ---------------------------------------------------------------------------
# 4. Downsampling keeps the ends
# ---------------------------------------------------------------------------


class TestDownsample:
    async def test_a_short_series_is_returned_whole(self):
        assert _downsample([1.0, 2.0, 3.0], MAX_HISTORY_POINTS) == [1.0, 2.0, 3.0]

    async def test_a_long_series_keeps_the_first_and_the_last(self):
        points = [float(i) for i in range(500)]
        thinned = _downsample(points, MAX_HISTORY_POINTS)
        assert thinned[0] == 0.0
        assert thinned[-1] == 499.0
        assert thinned == sorted(thinned)
        assert len(thinned) <= MAX_HISTORY_POINTS + 1

    async def test_a_dense_market_is_thinned_not_truncated(self):
        """Truncation would chart a month-old window and call it now."""
        market = _market(market_id=13, name=_RAIN_TITLE, outcomes=_RAIN_OUTCOMES)
        db = _CapturingDb([_snap(_MINNEAPOLIS, i / 1000) for i in range(1, 601)])

        series = (await _leader_histories(db, [market]))[13]

        assert len(series) <= MAX_HISTORY_POINTS + 1
        assert series[0] == 0.1
        assert series[-1] == 60.0


# ---------------------------------------------------------------------------
# 5. The endpoints ship it, always keyed
# ---------------------------------------------------------------------------


class TestTheEndpointsShipIt:
    async def test_featured_and_wildcards_both_carry_history(self, client, mock_db):
        """Both surfaces drew a fabricated line, so both are checked. A fix
        landed on one endpoint only would have left half the page lying."""
        volcano = _market(
            market_id=2,
            name="Major volcano eruption in 2026?",
            outcomes=[
                _outcome("At least 1", 0.110, outcome_id=11),
                _outcome("At least 2", 0.680, outcome_id=12),
            ],
        )
        rows = [_snap(12, 0.50), _snap(12, 0.60), _snap(12, 0.68)]

        for endpoint in ("featured", "wildcards"):
            mock_db.execute.return_value = _result_for([volcano], rows)
            item = (await client.get(f"/api/weather/{endpoint}")).json()[0]
            assert item["history"] == [50.0, 60.0, 68.0], endpoint
            assert item["prob"] == 68, endpoint

    async def test_the_key_is_present_and_empty_when_there_is_no_history(
        self, client, mock_db
    ):
        """An ABSENT key means "this payload predates the field" — the hourly
        weather cache really does serve one of those for up to an hour after a
        deploy. An empty list means "we looked, there is nothing". Both render
        no line, and the frontend must never have to guess which it got."""
        volcano = _market(
            market_id=2,
            name="Major volcano eruption in 2026?",
            outcomes=[_outcome("At least 2", 0.680, outcome_id=12)],
        )

        for endpoint in ("featured", "wildcards"):
            mock_db.execute.return_value = _result_for([volcano], [])
            item = (await client.get(f"/api/weather/{endpoint}")).json()[0]
            assert item["history"] == [], endpoint


async def test_the_generator_is_gone_from_the_frontend():
    """The backend can only OFFER real captures; it cannot stop the frontend
    from drawing its own. `sparkFrom` is deleted, and this notices if it comes
    back — the jest suite proves the components no longer call it, this proves
    the module no longer offers it to anyone."""
    from pathlib import Path

    data_ts = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "components"
        / "weather"
        / "data.ts"
    )
    if not data_ts.exists():  # backend-only checkouts
        pytest.skip("frontend not present in this checkout")
    source = data_ts.read_text()
    assert "Math.random" not in source
    assert "export function sparkFrom" not in source


async def test_the_floor_is_three():
    """Named, because the number is a judgment and not an implementation
    detail: two points is a straight segment, and a straight segment reads as a
    trend the data has not earned."""
    assert MIN_HISTORY_POINTS == 3
    assert weather_route.MAX_HISTORY_POINTS == 14
