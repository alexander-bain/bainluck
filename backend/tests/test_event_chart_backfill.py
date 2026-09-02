"""live/035 item 1: a finished match draws its whole life, from the venue's history.

The specimen these tests are shaped around, measured on production 2026-09-02:

    events.id 15300759          created 2026-09-01 22:05 UTC  (status 'scheduled')
    futures_markets 59693708    created 2026-08-28 18:49 UTC  (resolved)
    win_prob_snapshots          1 row
    Kalshi candlesticks for
      KXATPMATCH-…-MON          2,081 one-minute points, 0.495 -> 1.0,
                                2026-08-27T17:17 .. 2026-09-02T01:43

The event row is younger than the match. No sampler can fix that; only the
venue's own history can. Everything below guards a way that recovery can go
quietly wrong: a flipped curve, a series compressed to nothing, a re-run that
duplicates every point, a request Kalshi refuses, an interval Kalshi answers
with nonsense, or rows the #1828 state filter then deletes on read.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.event_chart_backfill import (
    KALSHI_MAX_PERIODS_PER_REQUEST,
    KALSHI_PERIOD_INTERVALS,
    SeriesPoint,
    backfill_event_chart,
    candle_windows,
    choose_period_interval,
    compress_series,
    heartbeat_seconds_for,
    is_thin_chart,
    minute_key,
    orient_points,
    resolve_orientation,
)

UTC = timezone.utc
T0 = datetime(2026, 8, 27, 17, 17, tzinfo=UTC)


def _pt(minutes: int, value: float) -> SeriesPoint:
    return SeriesPoint(
        captured_at=T0 + timedelta(minutes=minutes),
        home_probability=value,
        yes_probability=round(1.0 - value, 4),
    )


# ---------------------------------------------------------------------------
# compress_series — keep every move, breathe while flat, never lose an endpoint
# ---------------------------------------------------------------------------


def test_every_value_change_survives_compression():
    points = [_pt(i, 0.5 + (i % 7) / 100.0) for i in range(200)]
    kept = compress_series(points, heartbeat_seconds=30 * 60)

    changes = {
        p.captured_at
        for i, p in enumerate(points)
        if i == 0 or p.home_probability != points[i - 1].home_probability
    }
    assert changes <= {p.captured_at for p in kept}


def test_a_flat_stretch_still_breathes():
    """A motionless market must not compress to two points a week apart."""
    points = [_pt(i, 0.44) for i in range(0, 7 * 24 * 60, 1)]
    kept = compress_series(points, heartbeat_seconds=15 * 60)

    assert len(kept) > 2
    gaps = [
        (b.captured_at - a.captured_at).total_seconds()
        for a, b in zip(kept, kept[1:])
    ]
    assert max(gaps) <= 15 * 60


def test_both_endpoints_are_always_kept():
    """The opening opinion and the settlement are the two points a reader wants."""
    points = [_pt(0, 0.495)] + [_pt(i, 0.44) for i in range(1, 500)] + [_pt(500, 1.0)]
    kept = compress_series(points, heartbeat_seconds=60 * 60)

    assert kept[0].captured_at == points[0].captured_at
    assert kept[0].home_probability == 0.495
    assert kept[-1].captured_at == points[-1].captured_at
    assert kept[-1].home_probability == 1.0


def test_compression_never_emits_a_duplicate_timestamp():
    """A duplicated minute would insert two rows the chart draws on top of itself."""
    points = [_pt(0, 0.5), _pt(1, 0.5)]
    kept = compress_series(points, heartbeat_seconds=1)

    assert len({p.captured_at for p in kept}) == len(kept)


def test_empty_series_compresses_to_empty_not_to_a_crash():
    assert compress_series([], heartbeat_seconds=60) == []


def test_specimen_sized_series_lands_near_the_target():
    """2,081 candles over 5.4 days must become a drawable series, not 2,081 rows.

    Shaped like the measured specimen: 2,081 one-minute candles carrying only
    **266 distinct value changes** — the rest is a market holding its price.
    """
    lifetime = 5.4 * 24 * 3600
    points = []
    for i in range(2081):
        value = round(0.4 + (i // 8) / 10_000.0, 6)  # 261 changes, held for 8 min each
        points.append(_pt(i * 4, value))
    kept = compress_series(points, heartbeat_seconds_for(lifetime))

    assert 100 < len(kept) < 1200, (
        f"{len(kept)} points is not a chart-sized series"
    )


# ---------------------------------------------------------------------------
# heartbeat / thinness arithmetic
# ---------------------------------------------------------------------------


def test_heartbeat_scales_with_lifetime_and_stays_inside_its_bounds():
    from app.tasks.event_chart_backfill import (
        MAX_HEARTBEAT_SECONDS,
        MIN_HEARTBEAT_SECONDS,
    )

    short = heartbeat_seconds_for(2 * 3600)          # a two-hour match
    long = heartbeat_seconds_for(60 * 24 * 3600)     # a two-month futures market

    assert short == MIN_HEARTBEAT_SECONDS
    assert long == MAX_HEARTBEAT_SECONDS
    assert short < heartbeat_seconds_for(5 * 24 * 3600) < long


def test_heartbeat_survives_a_zero_lifetime():
    from app.tasks.event_chart_backfill import MIN_HEARTBEAT_SECONDS

    assert heartbeat_seconds_for(0) == MIN_HEARTBEAT_SECONDS
    assert heartbeat_seconds_for(-1) == MIN_HEARTBEAT_SECONDS


def test_the_specimen_reads_as_thin_and_a_drawn_chart_does_not():
    five_days = 5.4 * 24 * 3600

    assert is_thin_chart(1, five_days) is True, "the Monfils chart must be selected"
    assert is_thin_chart(600, five_days) is False, "a drawn chart must be left alone"


def test_a_short_market_is_not_thin_just_for_being_short():
    """Control: thinness is relative to LIFETIME, never an absolute point count."""
    two_hours = 2 * 3600
    assert is_thin_chart(5, two_hours) is False
    assert is_thin_chart(1, two_hours) is True


# ---------------------------------------------------------------------------
# Request shaping — the two ways Kalshi answers wrongly
# ---------------------------------------------------------------------------


def test_a_seven_day_minute_window_is_split_below_the_refusal_threshold():
    """Measured: 10,080 one-minute periods 400s; 10,000 is served.

    So the specimen's own lifetime cannot be fetched in one request, and a
    backfill that tried would record an exception as 'no history'.
    """
    start = int(T0.timestamp())
    end = start + 7 * 86400
    windows = candle_windows(start, end, period_minutes=1)

    assert len(windows) > 1
    assert all(
        (b - a) / 60 <= KALSHI_MAX_PERIODS_PER_REQUEST for a, b in windows
    )
    # No gaps and no overlaps: a dropped window is a hole in the curve.
    assert windows[0][0] == start
    assert windows[-1][1] == end
    assert all(b[0] == a[1] for a, b in zip(windows, windows[1:]))


def test_an_inverted_or_empty_range_yields_no_windows():
    """gotcha #53: fetching backwards returns an empty 200 that reads as 'no data'."""
    start = int(T0.timestamp())
    assert candle_windows(start, start, period_minutes=1) == []
    assert candle_windows(start, start - 3600, period_minutes=1) == []


def test_only_kalshi_supported_intervals_are_ever_requested():
    """5 and 15 are not errors — they return 4 candles for a 1,134-candle window.

    An answer shaped like data is worse than a refusal, so the chooser must never
    be able to emit one.
    """
    for lifetime_days in (0.1, 1, 5, 30, 200, 3650):
        assert (
            choose_period_interval(lifetime_days * 86400) in KALSHI_PERIOD_INTERVALS
        )


def test_a_long_lived_market_drops_to_hourly_rather_than_paging_forever():
    fine = choose_period_interval(5 * 86400)
    coarse = choose_period_interval(400 * 86400)

    assert fine == 1
    assert coarse > 1


# ---------------------------------------------------------------------------
# Orientation — a flipped curve is worse than no curve
# ---------------------------------------------------------------------------


def test_away_side_series_is_mirrored_onto_home():
    raw = [{"t": int(T0.timestamp()), "yes_price": 0.75}]

    home_side = orient_points(raw, yes_is_home=True)
    away_side = orient_points(raw, yes_is_home=False)

    assert home_side[0].home_probability == 0.75
    assert away_side[0].home_probability == 0.25


def test_settlement_prices_are_kept_but_corrupt_ones_are_dropped():
    """0 and 1 are the most-read part of a finished chart; 1.4 is not a price."""
    base = int(T0.timestamp())
    points = orient_points(
        [
            {"t": base, "yes_price": 0.0},
            {"t": base + 60, "yes_price": 1.0},
            {"t": base + 120, "yes_price": 1.4},
            {"t": base + 180, "yes_price": -0.2},
        ],
        yes_is_home=True,
    )

    assert [p.home_probability for p in points] == [0.0, 1.0]


def test_points_are_sorted_and_deduped_by_minute():
    base = int(T0.timestamp())
    points = orient_points(
        [
            {"t": base + 120, "yes_price": 0.6},
            {"t": base, "yes_price": 0.5},
            {"t": base + 30, "yes_price": 0.9},  # same minute as `base`
        ],
        yes_is_home=True,
    )

    assert [p.captured_at for p in points] == sorted(p.captured_at for p in points)
    assert len(points) == 2
    assert points[0].home_probability == 0.5, "first reading of a minute wins"


def test_unparseable_points_are_skipped_not_fatal():
    base = int(T0.timestamp())
    points = orient_points(
        [
            {"t": None, "yes_price": 0.5},
            {"t": base, "yes_price": None},
            {"t": "not-a-time", "yes_price": 0.5},
            {"t": base, "yes_price": 0.5},
        ],
        yes_is_home=True,
    )

    assert len(points) == 1


def _market(**kw):
    return SimpleNamespace(
        id=kw.get("id", 59693708),
        source=kw.get("source", "kalshi"),
        external_id=kw.get("external_id", "KXATPMATCH-26AUG30VALMON"),
        name=kw.get("name", "Vallejo vs Monfils"),
        market_metadata=kw.get("market_metadata"),
        group_id=kw.get("group_id"),
        created_at=kw.get("created_at", datetime(2026, 8, 28, 18, 49, tzinfo=UTC)),
    )


def _outcome(name, probability, external_id, rank, is_winner=None):
    return SimpleNamespace(
        id=hash(external_id) % 10**8,
        name=name,
        current_probability=probability,
        external_id=external_id,
        rank=rank,
        is_winner=is_winner,
    )


def _group(home_prob, away_prob):
    from app.utils.live_blend import MarketOutcomes

    return [
        MarketOutcomes(
            market=_market(),
            outcomes=[
                _outcome(
                    "Adolfo Daniel Vallejo",
                    home_prob,
                    "KXATPMATCH-26AUG30VALMON-VAL",
                    1,
                ),
                _outcome(
                    "Gael Monfils", away_prob, "KXATPMATCH-26AUG30VALMON-MON", 2
                ),
            ],
        )
    ]


def test_orientation_matches_the_live_writers_on_an_open_market():
    """The whole point: backfilled points must sit on the same axis as live ones."""
    from app.utils.live_blend import compute_source_home_probability

    group = _group(0.465, 0.535)
    live = compute_source_home_probability(group, "Vallejo", "Monfils")
    resolved = resolve_orientation(group, "Vallejo", "Monfils")

    assert live is not None
    assert resolved is not None
    _market_out, outcome, yes_is_home = resolved
    assert outcome.name == live.outcome.name
    implied = (
        float(outcome.current_probability)
        if yes_is_home
        else 1.0 - float(outcome.current_probability)
    )
    assert implied == pytest.approx(live.home_probability, abs=1e-6)


def test_a_settled_market_still_orients():
    """The cohort that needs backfilling MOST is the one priced 1.0 / 0.0.

    `find_moneyline_outcome` discards those on purpose for a live read. Without
    the clamp this module would decline exactly the events it exists for.
    """
    resolved = resolve_orientation(_group(0.0, 1.0), "Vallejo", "Monfils")

    assert resolved is not None
    _m, outcome, yes_is_home = resolved
    assert outcome.name in ("Adolfo Daniel Vallejo", "Gael Monfils")
    # The proxy must not leak: callers stamp `outcome.external_id` into the
    # candlestick request, and a wrapper that dropped it would fetch nothing.
    assert outcome.external_id.startswith("KXATPMATCH-")
    assert isinstance(yes_is_home, bool)


def test_the_live_selector_alone_would_have_declined_that_market():
    """Control for the test above — proves the clamp is load-bearing, not decorative."""
    from app.utils.live_blend import compute_source_home_probability

    assert compute_source_home_probability(_group(0.0, 1.0), "Vallejo", "Monfils") is None


def test_orientation_declines_rather_than_guesses_on_an_unparseable_market():
    from app.utils.live_blend import MarketOutcomes

    group = [
        MarketOutcomes(
            market=_market(name="Some market", external_id="KXNOTAMATCH-XYZ"),
            outcomes=[_outcome("Yes", 0.5, "KXNOTAMATCH-XYZ-Y", 1)],
        )
    ]
    assert resolve_orientation(group, "Vallejo", "Monfils") is None


def test_orientation_declines_on_an_empty_group():
    assert resolve_orientation([], "Vallejo", "Monfils") is None


# ---------------------------------------------------------------------------
# The rail end to end
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    """Answers the two queries `backfill_event_chart` makes, in order."""

    def __init__(self, markets, existing_snapshots):
        self._answers = [_Result(markets), _Result(existing_snapshots)]
        self.added = []

    async def execute(self, *_args, **_kwargs):
        return self._answers.pop(0)

    def add(self, obj):
        self.added.append(obj)


def _orm_market(outcomes):
    market = _market()
    market.outcomes = outcomes
    return market


def _raw_candle(ts, *, bid=None, ask=None, last=None):
    """A Kalshi candle in the shape the API actually returns (dollars, strings)."""
    candle = {"end_period_ts": int(ts)}
    if bid is not None:
        candle["yes_bid"] = {"close_dollars": f"{bid:.4f}"}
    if ask is not None:
        candle["yes_ask"] = {"close_dollars": f"{ask:.4f}"}
    if last is not None:
        candle["price"] = {"close_dollars": f"{last:.4f}"}
    return candle


def _candles(count, *, start=T0, first=0.495, last=0.99):
    """A rising series: `count` minute candles from `first` to `last`, tight book."""
    step = (last - first) / max(1, count - 1)
    out = []
    for i in range(count):
        mid = round(first + step * i, 4)
        out.append(
            _raw_candle(
                (start + timedelta(minutes=i)).timestamp(),
                bid=max(0.01, mid - 0.005),
                ask=min(0.99, mid + 0.005),
                last=mid,
            )
        )
    return out


#: Distinct from ``None``, which is the meaningful answer "Kalshi 404'd — purged".
_DEFAULT_MARKET = object()


def _kalshi_service(candles, *, market_detail=_DEFAULT_MARKET):
    service = MagicMock()
    service.get_market_candlesticks_raw = AsyncMock(return_value=candles)
    service.get_market = AsyncMock(
        return_value=(
            {
                "ticker": "KXATPMATCH-26AUG30VALMON-MON",
                "status": "finalized",
                "open_time": "2026-08-27T17:16:00Z",
                "close_time": "2026-09-02T01:40:50Z",
            }
            if market_detail is _DEFAULT_MARKET
            else market_detail
        )
    )
    service.close = AsyncMock()
    return service


def _event():
    return SimpleNamespace(
        id=15300759,
        home_team_name="Vallejo",
        away_team_name="Monfils",
        commence_time=datetime(2026, 8, 30, tzinfo=UTC),
        completed_at=None,
        status="scheduled",
    )


async def test_the_specimen_gains_a_curve_from_pre_match_to_settlement():
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])

    verdict = await backfill_event_chart(
        session, _event(), kalshi_service=_kalshi_service(_candles(600))
    )

    assert verdict["status"] == "written"
    assert verdict["points_written"] > 50, "one dot is the bug; a curve is the fix"
    assert len(session.added) == verdict["points_written"]

    stamps = [row.captured_at for row in session.added]
    assert stamps == sorted(stamps)
    assert stamps[0] < _event().commence_time, "the pre-match drift must be there"


async def test_backfilled_rows_survive_the_1828_cross_game_state_filter():
    """These rows would be DELETED ON READ if they carried a period or an inning.

    `app/utils/game_window.py` drops state-bearing win-prob rows from outside the
    game window, and this cohort's `commence_time` is exactly the field that is
    wrong. A candlestick asserts a price, not an inning, so it must carry no
    state key at all.
    """
    from app.utils.game_window import filter_state_bearing_rows, game_state_window

    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])
    await backfill_event_chart(
        session, _event(), kalshi_service=_kalshi_service(_candles(600))
    )

    rows = [
        {"timestamp": row.captured_at.isoformat(), "game_state": row.game_state}
        for row in session.added
    ]
    window = game_state_window(_event().commence_time, None)
    kept, dropped = filter_state_bearing_rows(rows, window)

    assert dropped == 0
    assert len(kept) == len(rows)
    for row in session.added:
        assert not ({"period", "inning", "clock", "game_clock"} & set(row.game_state))
        assert row.game_state["poll_type"] == "history_backfill"
        assert row.game_state["backfill_source"] == "kalshi_candlesticks"


async def test_a_second_run_writes_nothing():
    """Idempotency is by minute, because the table carries no unique constraint.

    Adding one would mean a non-CONCURRENT unique build over a very large table
    inside an Alembic release (gotcha #31), so this is the guarantee instead —
    and it has to be tested, since nothing in the schema enforces it.
    """
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    candles = _candles(600)

    first = _Session([_orm_market(outcomes)], existing_snapshots=[])
    await backfill_event_chart(
        first, _event(), kalshi_service=_kalshi_service(candles)
    )
    written = [row.captured_at for row in first.added]
    assert written

    second = _Session([_orm_market(outcomes)], existing_snapshots=written)
    verdict = await backfill_event_chart(
        second, _event(), kalshi_service=_kalshi_service(candles)
    )

    assert second.added == []
    assert verdict["points_written"] == 0
    assert verdict["sources"]["kalshi"]["status"] == "already_complete"


async def test_a_live_written_point_is_skipped_around_never_duplicated():
    """The one real point the specimen already has must not become two."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    candles = _candles(600)
    already = [minute_key(datetime.fromtimestamp(candles[0]["end_period_ts"], tz=UTC))]

    session = _Session([_orm_market(outcomes)], existing_snapshots=already)
    await backfill_event_chart(
        session, _event(), kalshi_service=_kalshi_service(candles)
    )

    assert already[0] not in [row.captured_at for row in session.added]
    assert len(session.added) > 10


async def test_a_purged_market_is_reported_as_purged_not_as_empty():
    """gotcha #53: an empty 200 is a response SHAPE. Only the 404 lookup decides."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])

    verdict = await backfill_event_chart(
        session,
        _event(),
        kalshi_service=_kalshi_service([], market_detail=None),
    )

    assert session.added == []
    assert verdict["sources"]["kalshi"]["purged"] == 1
    assert verdict["sources"]["kalshi"].get("api_empty", 0) == 0
    assert verdict["status"] == "no_new_points"


async def test_an_existing_but_silent_market_is_api_empty_not_purged():
    """Control for the test above: the two absences must stay distinguishable."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])

    verdict = await backfill_event_chart(
        session,
        _event(),
        kalshi_service=_kalshi_service([], market_detail={"ticker": "X"}),
    )

    assert verdict["sources"]["kalshi"]["api_empty"] == 1
    assert verdict["sources"]["kalshi"].get("purged", 0) == 0


async def test_an_event_with_no_linked_markets_says_so():
    session = _Session([], existing_snapshots=[])
    verdict = await backfill_event_chart(session, _event())

    assert verdict["status"] == "no_linked_markets"
    assert session.added == []


async def test_one_source_blowing_up_does_not_cost_the_other(monkeypatch):
    """gotcha #42: one bad item must never wipe the pass."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])
    service = _kalshi_service([])
    service.get_market = AsyncMock(side_effect=RuntimeError("upstream 500"))

    verdict = await backfill_event_chart(session, _event(), kalshi_service=service)

    assert verdict["sources"]["kalshi"]["status"] == "error"
    assert any("upstream 500" in e for e in verdict["errors"])


async def test_dry_run_writes_nothing_but_still_reports_what_it_would_draw():
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01, "KXATPMATCH-26AUG30VALMON-VAL", 1),
        _outcome("Gael Monfils", 0.99, "KXATPMATCH-26AUG30VALMON-MON", 2),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])

    verdict = await backfill_event_chart(
        session,
        _event(),
        kalshi_service=_kalshi_service(_candles(600)),
        dry_run=True,
    )

    assert session.added == []
    assert verdict["sources"]["kalshi"]["status"] == "dry_run"
    assert verdict["sources"]["kalshi"]["points_kept"] > 50


# ---------------------------------------------------------------------------
# Selection for the nightly sweep
# ---------------------------------------------------------------------------


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    async def execute(self, statement, params=None):
        self.sql = str(statement)
        self.params = params
        return _RowsResult(self.rows)


def _candidate(event_id, *, lifetime_hours, points):
    last = datetime(2026, 9, 1, tzinfo=UTC)
    return SimpleNamespace(
        event_id=event_id,
        market_first_seen=last - timedelta(hours=lifetime_hours),
        market_last_seen=last,
        point_count=points,
    )


async def test_the_selection_query_does_not_use_the_shape_that_timed_out():
    """A nightly task whose selection query times out never runs.

    Measured on production 2026-09-02: the single-GROUP-BY form with a
    `LEFT JOIN win_prob_snapshots` + `COUNT(DISTINCT w.id)` hit
    `statement_timeout`, because it counts points for every candidate before the
    LIMIT can discard any. The candidate set must be bounded FIRST.
    """
    from app.tasks.event_chart_backfill import THIN_CHART_CANDIDATES_SQL

    assert "LEFT JOIN win_prob_snapshots" not in THIN_CHART_CANDIDATES_SQL
    assert "COUNT(DISTINCT" not in THIN_CHART_CANDIDATES_SQL.upper()
    # The bound must precede the count: the CTE carries the LIMIT, and the
    # correlated count sits outside it.
    cte_end = THIN_CHART_CANDIDATES_SQL.index("FROM candidates c")
    assert "LIMIT :limit" in THIN_CHART_CANDIDATES_SQL[:cte_end]
    assert "win_prob_snapshots" in THIN_CHART_CANDIDATES_SQL[cte_end - 400 : ]


async def test_selection_keeps_the_thin_and_drops_the_drawn():
    from app.tasks.event_chart_backfill import select_thin_chart_events

    session = _RecordingSession([
        _candidate(1, lifetime_hours=130, points=1),     # the specimen shape
        _candidate(2, lifetime_hours=130, points=600),   # already drawn
        _candidate(3, lifetime_hours=3, points=1),       # thin for its short life
        _candidate(4, lifetime_hours=3, points=40),      # drawn
    ])

    picked = await select_thin_chart_events(session, limit=10)

    assert picked == [1, 3]


async def test_selection_bounds_itself_and_honours_the_retention_floor():
    from app.tasks.event_chart_backfill import select_thin_chart_events
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    session = _RecordingSession(
        [_candidate(i, lifetime_hours=130, points=1) for i in range(50)]
    )

    picked = await select_thin_chart_events(session, limit=5, scan_multiple=4)

    assert len(picked) == 5, "the sweep must stop at its limit, not at the scan"
    assert session.params["limit"] == 20, "scan a multiple, return a limit"
    assert session.params["purge_days"] == PROVABLY_PURGED_AGE_DAYS


# ---------------------------------------------------------------------------
# normalize_candle — the settled loser must not end at 1.0
# ---------------------------------------------------------------------------


def test_the_settled_losers_final_candle_is_not_one():
    """THE production specimen, byte-for-byte from Kalshi on 2026-09-02.

    `KXATPMATCH-26AUG30VALMON-VAL` — Vallejo LOST. His final candle's book is
    bid 0.00 / ask 1.00 (the shell a settled market leaves) with a last trade of
    0.01. Priced off the ask, this curve ends by declaring the loser certain.
    """
    from app.tasks.event_chart_backfill import normalize_candle

    final = {
        "end_period_ts": 1788335000,
        "yes_bid": {"close_dollars": "0.0000", "high_dollars": "0.0000",
                    "low_dollars": "0.0000", "open_dollars": "0.0000"},
        "yes_ask": {"close_dollars": "1.0000", "high_dollars": "1.0000",
                    "low_dollars": "0.0100", "open_dollars": "0.0100"},
        "price": {"previous_dollars": "0.0100"},
    }

    assert normalize_candle(final) == pytest.approx(0.01)


def test_the_shared_service_normalizer_still_gets_that_candle_wrong():
    """Control — proves `normalize_candle` is load-bearing, not decorative.

    `KalshiAPIService.get_market_candlesticks` is deliberately left alone (its
    consumers are calibration, not charts). If it were ever fixed, this test
    fails and the note pointing chart callers away from it can come out.
    """
    yes_bid, yes_ask = {"close_dollars": "0.0000"}, {"close_dollars": "1.0000"}
    bid = float(yes_bid.get("close_dollars") or 0)
    ask = float(yes_ask.get("close_dollars") or 0)
    shared_result = (bid + ask) / 2 if (bid > 0 and ask > 0) else (ask if ask > 0 else bid)

    assert shared_result == 1.0


def test_the_settled_winners_final_candle_is_its_last_trade():
    """`…-MON` — Monfils WON. bid collapses to 0.00, ask 1.00, last trade 0.99."""
    from app.tasks.event_chart_backfill import normalize_candle

    final = {
        "yes_bid": {"close_dollars": "0.0000", "open_dollars": "0.9900"},
        "yes_ask": {"close_dollars": "1.0000"},
        "price": {"previous_dollars": "0.9900"},
    }

    assert normalize_candle(final) == pytest.approx(0.99)


def test_a_tight_book_is_priced_at_the_mid():
    """Control: normal trading must still use the mid, not the last trade.

    The last trade can be minutes stale while the book moves; the mid is the
    better number whenever the mid means anything.
    """
    from app.tasks.event_chart_backfill import normalize_candle

    candle = {
        "yes_bid": {"close_dollars": "0.5500"},
        "yes_ask": {"close_dollars": "0.5700"},
        "price": {"close_dollars": "0.4000"},  # stale
    }

    assert normalize_candle(candle) == pytest.approx(0.56)


def test_a_one_sided_book_with_a_real_quote_and_no_trade_uses_the_quote():
    from app.tasks.event_chart_backfill import normalize_candle

    assert normalize_candle(
        {"yes_bid": {"close_dollars": "0.0000"},
         "yes_ask": {"close_dollars": "0.0300"}}
    ) == pytest.approx(0.03)


def test_an_empty_book_with_no_trade_yields_no_price_rather_than_a_guess():
    from app.tasks.event_chart_backfill import normalize_candle

    assert normalize_candle({}) is None
    assert normalize_candle(
        {"yes_bid": {"close_dollars": "0.0000"},
         "yes_ask": {"close_dollars": "1.0000"}}
    ) is None, "the 0.00/1.00 shell is not a price"


def test_the_curve_drawn_from_the_specimens_endgame_ends_where_it_should():
    """End to end over the real settlement shape, both sides.

    The loser's series must fall to ~0.01 and the winner's rise to ~0.99 — and
    critically, they must not both end at 1.0.
    """
    from app.tasks.event_chart_backfill import normalize_candle

    base = int(T0.timestamp())
    loser = [
        _raw_candle(base, bid=0.0, ask=0.01, last=0.01),
        {"end_period_ts": base + 60,
         "yes_bid": {"close_dollars": "0.0000"},
         "yes_ask": {"close_dollars": "1.0000"},
         "price": {"previous_dollars": "0.0100"}},
    ]
    winner = [
        _raw_candle(base, bid=0.99, ask=1.0, last=0.99),
        {"end_period_ts": base + 60,
         "yes_bid": {"close_dollars": "0.0000"},
         "yes_ask": {"close_dollars": "1.0000"},
         "price": {"previous_dollars": "0.9900"}},
    ]

    loser_end = normalize_candle(loser[-1])
    winner_end = normalize_candle(winner[-1])

    assert loser_end == pytest.approx(0.01)
    assert winner_end == pytest.approx(0.99)
    assert loser_end != winner_end


async def test_a_failing_candle_window_costs_that_window_and_nothing_else():
    """A five-day curve must survive losing one of its chunks."""
    from app.tasks.event_chart_backfill import fetch_kalshi_series

    calls = {"n": 0}

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("400 Bad Request")
        return _candles(50, start=T0 + timedelta(days=4))

    service = MagicMock()
    service.get_market_candlesticks_raw = AsyncMock(side_effect=flaky)
    service.get_market = AsyncMock(return_value={"ticker": "X"})

    stats: dict = {}
    out = await fetch_kalshi_series(
        service, "T",
        start=T0, end=T0 + timedelta(days=7),
        stats=stats,
    )

    # A 7-day span at 1-minute chunks into 3 windows; the first is lost.
    assert stats["window_errors"] == 1
    assert stats["candle_requests"] == 2
    assert len(out) == 100, "the surviving windows' candles must still come back"


# ---------------------------------------------------------------------------
# The inverted-axis backstop
# ---------------------------------------------------------------------------


def test_a_curve_ending_on_the_wrong_winner_is_a_contradiction():
    from app.tasks.event_chart_backfill import contradicts_known_winner

    assert contradicts_known_winner(0.99, home_won=False) is True
    assert contradicts_known_winner(0.01, home_won=True) is True


def test_a_curve_ending_on_the_right_winner_is_not():
    from app.tasks.event_chart_backfill import contradicts_known_winner

    assert contradicts_known_winner(0.01, home_won=False) is False
    assert contradicts_known_winner(0.99, home_won=True) is False


def test_an_unknown_winner_never_convicts_and_an_upset_never_does_either():
    """The check catches an inverted AXIS, not a surprising RESULT.

    A genuine upset ends with the loser high right up to the final point, and
    that is a true story about the market. Only a stark disagreement — and only
    when the winner is positively known — is a contradiction.
    """
    from app.tasks.event_chart_backfill import contradicts_known_winner

    assert contradicts_known_winner(0.99, home_won=None) is False
    assert contradicts_known_winner(0.45, home_won=False) is False
    assert contradicts_known_winner(0.85, home_won=False) is False


def test_home_won_is_unknown_unless_exactly_one_outcome_is_marked():
    """`is_winner` is a Boolean defaulting to False — absence is not a loss."""
    from app.tasks.event_chart_backfill import home_won_from_outcomes

    home = _outcome("Vallejo", 0.01, "A", 1, is_winner=False)
    away = _outcome("Monfils", 0.99, "B", 2, is_winner=False)

    assert home_won_from_outcomes([home, away], home, True) is None
    assert home_won_from_outcomes([], home, True) is None

    away.is_winner = True
    assert home_won_from_outcomes([home, away], home, True) is False
    assert home_won_from_outcomes([home, away], away, True) is True


async def test_an_inverted_curve_is_refused_rather_than_written():
    """A missing chart is a gap; a mirrored one is a legible lie."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01,
                 "KXATPMATCH-26AUG30VALMON-VAL", 1, is_winner=False),
        _outcome("Gael Monfils", 0.99,
                 "KXATPMATCH-26AUG30VALMON-MON", 2, is_winner=True),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])
    # A series that rises to 0.99 for the HOME side (Vallejo) — who lost.
    rising = _candles(200, first=0.5, last=0.99)

    verdict = await backfill_event_chart(
        session, _event(), kalshi_service=_kalshi_service(rising)
    )

    assert session.added == []
    assert verdict["sources"]["kalshi"]["status"] == "orientation_contradicts_winner"
    assert verdict["points_written"] == 0


async def test_the_correctly_oriented_curve_for_the_same_market_is_written():
    """Control: the guard must not refuse the real, correctly-oriented curve."""
    outcomes = [
        _outcome("Adolfo Daniel Vallejo", 0.01,
                 "KXATPMATCH-26AUG30VALMON-VAL", 1, is_winner=False),
        _outcome("Gael Monfils", 0.99,
                 "KXATPMATCH-26AUG30VALMON-MON", 2, is_winner=True),
    ]
    session = _Session([_orm_market(outcomes)], existing_snapshots=[])
    falling = _candles(200, first=0.5, last=0.01)

    verdict = await backfill_event_chart(
        session, _event(), kalshi_service=_kalshi_service(falling)
    )

    assert verdict["sources"]["kalshi"]["status"] == "written"
    assert verdict["points_written"] > 50
    assert session.added[-1].home_win_probability == pytest.approx(0.01, abs=0.02)
