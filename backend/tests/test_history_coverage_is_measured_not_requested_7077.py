"""#7077 live half — the history door stops claiming a week for a day of data.

Alex's build-15 phone walk photographed *The Game Awards: Game of the Year* with
the **7d** range selected and six x-axis ticks all reading **"Sep 18"**
(`artifacts/alex-phone-20260918-build15/game-awards-chart.png`). The chart was
not lying about the points; it was drawing the domain the payload told it to.

MEASURED ON PRODUCTION 2026-09-19 against the three markets that walk named,
`GET /api/futures/{id}/history?hours=168`:

| market | requested | served `actual_hours` | the points actually span | `total_data_points` |
|---|---|---|---|---|
| 58321581 Game Awards | 168 h | **168** | **19.3 h** (Sep 18 04:31 → 23:50) | 80 |
| 61122553 Meta training pause | 168 h | **168** | 75.4 h, 2 points per outcome | 4 |
| 59530987 US bank failure | 168 h | **720** (auto-extended) | 598.6 h | 11 |

Three markets, three ways the field named "actual" is not the data: twice it
echoes the REQUEST, once an internal `_EXTEND_TIERS` constant. It is the window
this route SEARCHED, and nothing in the payload has ever said the difference.

`total_data_points` cannot stand in for the missing claim, because it is summed
ACROSS outcomes: Game Awards reports 80 from **8** distinct observation times,
and a 24-outcome field clears the `sparse` threshold (`< 10`) on a single
observation each. `test_observation_times_is_not_multiplied_by_the_outcome_count`
pins that specifically — it is the reason a dense-looking payload can hold one
instant of truth.

WHAT THIS FILE DOES NOT DO. It does not move `actual_hours`, `total_data_points`,
`sparse` or `auto_extended` by one byte. `auto_extended`'s caption ("Extended to
30 days for more data", `frontend/app/futures/[id]/page.tsx:877`) is *correct*
about the search window, and that file is ux's under notice 41.
`test_no_existing_key_moved` is the control that fails if a later change buys
coverage honesty by redefining a key some reader already has. The four new keys
are a separate, measured claim; #7077 is native's consumer half and is OPEN.

`test_the_before_control` is the strawman guard: it fails if `coverage_hours`
ever collapses back onto `actual_hours`, which is the defect reverting.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import futures as futures_route
from app.routes.futures import _measure_history_coverage


#: Sep 18 2026 23:50:14Z — the last observation production served for market
#: 58321581, and the minute after Alex's 5:03pm PDT screenshot.
LAST = datetime(2026, 9, 18, 23, 50, 14, 826621, tzinfo=timezone.utc)
#: Sep 18 2026 04:31:29Z — the FIRST observation in that same 168-hour window.
FIRST = datetime(2026, 9, 18, 4, 31, 29, 38071, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The measurement itself, as a function of the series it is handed
# ---------------------------------------------------------------------------


def _series(*stamps):
    return {"history": [{"timestamp": s.isoformat(), "probability": 0.5} for s in stamps]}


class TestTheMeasurement:
    def test_it_reports_the_span_of_the_points_it_was_given(self):
        got = _measure_history_coverage({1: _series(FIRST, LAST)})

        assert got["coverage_start"] == FIRST.isoformat()
        assert got["coverage_end"] == LAST.isoformat()
        # 04:31:29 -> 23:50:14 on one calendar day.
        assert got["coverage_hours"] == pytest.approx(19.31, abs=0.01)

    def test_it_spans_every_outcome_not_just_the_first(self):
        """A field market's coverage is the union, or the leader decides it."""
        got = _measure_history_coverage(
            {1: _series(LAST), 2: _series(FIRST), 3: _series(FIRST + timedelta(hours=3))}
        )

        assert got["coverage_start"] == FIRST.isoformat()
        assert got["coverage_end"] == LAST.isoformat()

    def test_observation_times_counts_instants_not_rows(self):
        """Ten outcomes observed together are ONE observation, not ten."""
        shared = {oid: _series(FIRST, LAST) for oid in range(10)}

        got = _measure_history_coverage(shared)

        assert got["observation_times"] == 2

    def test_an_empty_history_is_null_and_not_zero(self):
        """gotcha #53 — an absence and an instant must not share a shape."""
        got = _measure_history_coverage({1: {"history": []}, 2: {}})

        assert got["coverage_start"] is None
        assert got["coverage_end"] is None
        assert got["coverage_hours"] is None
        assert got["observation_times"] == 0

    def test_one_observation_is_zero_hours_and_one_time(self):
        """The contrast to the test above: real, dated, and of no duration."""
        got = _measure_history_coverage({1: _series(LAST)})

        assert got["coverage_hours"] == 0.0
        assert got["observation_times"] == 1
        assert got["coverage_start"] == got["coverage_end"] == LAST.isoformat()

    def test_an_unparseable_stamp_is_skipped_not_fatal(self):
        got = _measure_history_coverage(
            {1: {"history": [{"timestamp": None}, {"timestamp": "not a date"},
                             {"timestamp": LAST.isoformat()}]}}
        )

        assert got["observation_times"] == 1
        assert got["coverage_end"] == LAST.isoformat()


# ---------------------------------------------------------------------------
# The served payload, through the handler — the Game Awards shape
# ---------------------------------------------------------------------------


def _outcome(oid, name, prob):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.external_id = name
    o.current_probability = prob
    o.is_winner = None
    o.resolution_source = None
    return o


def _snapshot(oid, book, prob, stamp):
    s = MagicMock()
    s.outcome_id = oid
    s.bookmaker = book
    s.probability = prob
    s.captured_at = stamp
    s.yes_bid = None
    s.yes_ask = None
    s.last_price = None
    return s


class _Result:
    def __init__(self, rows=(), scalar=None):
        self._rows, self._scalar = list(rows), scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def unique(self):
        return self

    def scalar_one_or_none(self):
        return self._scalar


class _Session:
    """Answers each ``execute`` from a queue; the last entry repeats."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    async def execute(self, statement):
        self.calls += 1
        return self._results[min(self.calls - 1, len(self._results) - 1)]


def _game_awards(stamps):
    """Market 58321581's charted shape: a three-horse field over `stamps`.

    Two books so the de-vig has a column to divide by — a single book would
    exercise a different computation than production's.
    """
    outcomes = [
        _outcome(216388319, "Grand Theft Auto VI", 0.65),
        _outcome(216388320, "Resident Evil Requiem", 0.1044),
        _outcome(216388337, "Slay the Spire 2", 0.015),
    ]
    market = MagicMock()
    market.id = 58321581
    market.name = "The Game Awards: Game of the Year"
    market.outcomes = outcomes
    market.mutually_exclusive = True
    market.market_metadata = None
    market.status = "open"

    rows = []
    for stamp in stamps:
        for book, scale in (("polymarket", 1.0), ("kalshi", 1.15)):
            rows.append(_snapshot(216388319, book, 0.65 * scale, stamp))
            rows.append(_snapshot(216388320, book, 0.1044 * scale, stamp))
            rows.append(_snapshot(216388337, book, 0.015 * scale, stamp))
    return market, rows


#: The eight instants production actually held for market 58321581 inside a
#: 168-hour window — every one of them on Sep 18.
EIGHT_STAMPS = [FIRST + timedelta(hours=h) for h in (0, 2, 5, 9, 12, 15, 18, 19.31)]


@pytest.mark.asyncio
async def test_the_before_control_coverage_does_not_echo_the_requested_window():
    """THE STRAWMAN GUARD. Revert the fix and this is the assertion that fails.

    The whole defect in one line: 168 hours were asked for and searched, and
    19 hours of observations came back. A payload where these two agree on this
    market is the payload Alex photographed.
    """
    market, rows = _game_awards(EIGHT_STAMPS)
    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        58321581, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["actual_hours"] == 168, "the search window is not the subject"
    assert payload["coverage_hours"] == pytest.approx(19.31, abs=0.05)
    assert payload["coverage_hours"] < payload["actual_hours"] / 8


@pytest.mark.asyncio
async def test_the_served_payload_dates_its_own_coverage():
    market, rows = _game_awards(EIGHT_STAMPS)
    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        58321581, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["coverage_start"] == FIRST.isoformat()
    assert payload["coverage_end"] == EIGHT_STAMPS[-1].isoformat()
    # Both ends land on one calendar day — the six identical "Sep 18" ticks.
    assert payload["coverage_start"][:10] == payload["coverage_end"][:10] == "2026-09-18"


@pytest.mark.asyncio
async def test_observation_times_is_not_multiplied_by_the_outcome_count():
    """Why `total_data_points` could never have carried this claim.

    Three outcomes × eight instants = 24 served points, comfortably clear of the
    `sparse` threshold of 10 — off EIGHT observations. Production's real row is
    starker: 80 points, 8 instants, 10 outcomes.
    """
    market, rows = _game_awards(EIGHT_STAMPS)
    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        58321581, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["observation_times"] == len(EIGHT_STAMPS) == 8
    assert payload["total_data_points"] == 24
    assert payload.get("sparse") is None, "24 points is not sparse by the old rule"
    assert payload["observation_times"] < payload["total_data_points"]


@pytest.mark.asyncio
async def test_coverage_is_measured_from_the_data_when_the_window_auto_extends():
    """Market 59530987's shape: `actual_hours` becomes 720, coverage stays real.

    The auto-extend path is the one place `actual_hours` is neither the request
    nor the data — it is an `_EXTEND_TIERS` constant. Coverage must still be the
    observations.
    """
    now = datetime.now(timezone.utc)
    sparse_stamps = [now - timedelta(days=d) for d in (1, 3, 6)]
    market, rows = _game_awards(sparse_stamps)
    wide_stamps = sparse_stamps + [now - timedelta(days=d) for d in (10, 14, 20, 24)]
    _, wide_rows = _game_awards(wide_stamps)

    db = _Session(_Result(scalar=market), _Result(rows), _Result(wide_rows))

    payload = await futures_route.get_futures_history(
        59530987, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["actual_hours"] == 720, "the 30-day tier is the searched window"
    assert payload.get("auto_extended") is True
    # 24 days of observations inside a 30-day search — close, and not the same.
    assert payload["coverage_hours"] == pytest.approx(23 * 24, abs=2)
    assert payload["coverage_hours"] < 720


@pytest.mark.asyncio
async def test_no_existing_key_moved():
    """THE CONTROL on the other side: coverage honesty is bought additively.

    `actual_hours`, `hours`, `total_data_points`, `sparse` and `auto_extended`
    are read today — `auto_extended` by ux's own caption. A later change that
    made `actual_hours` mean the data would pass every test above and break a
    reader; this is the test it breaks instead.
    """
    market, rows = _game_awards(EIGHT_STAMPS)
    db = _Session(_Result(scalar=market), _Result(rows))

    payload = await futures_route.get_futures_history(
        58321581, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["hours"] == 168
    assert payload["actual_hours"] == 168
    assert payload["total_data_points"] == 24
    assert "sparse" not in payload
    assert "auto_extended" not in payload
    assert payload["market_id"] == 58321581
    assert payload["market_name"] == "The Game Awards: Game of the Year"
    assert {o["outcome_id"] for o in payload["outcomes"]} == {
        216388319, 216388320, 216388337
    }


@pytest.mark.asyncio
async def test_a_market_with_no_snapshots_serves_nulls_through_the_handler():
    """The end-to-end half of gotcha #53: an empty chart says so in dates too."""
    market, _ = _game_awards(EIGHT_STAMPS)
    db = _Session(_Result(scalar=market), _Result([]))

    payload = await futures_route.get_futures_history(
        58321581, outcome_id=None, hours=168, top_n=10, champion=None, db=db
    )

    assert payload["coverage_start"] is None
    assert payload["coverage_end"] is None
    assert payload["coverage_hours"] is None
    assert payload["observation_times"] == 0
    assert payload["total_data_points"] == 0


# ---------------------------------------------------------------------------
# /probability-timeline — THE DOOR THE PHONE ACTUALLY READS
#
# `ios/.../Services/APIClient.swift:929` fetches `/probability-timeline`.
# NOTHING native calls `/futures/{id}/history`, so the door above serves the web
# and this one served Alex's screenshot. Production 01:05Z, market 58321581:
# `actual_hours` **168**, **nine buckets spanning 20.0 hours**.
#
# Coverage here is measured off the BUCKET stamps rather than the raw rows: the
# buckets are the x-positions drawn, and a claim taken from the rows would
# disagree with the plotted line by up to one `bucket_seconds`. That is why this
# door reports 04:30 where /history reports the raw 04:31.
# ---------------------------------------------------------------------------


from app.routes.futures import _measure_timeline_coverage, get_probability_timeline  # noqa: E402


def _tl_outcome(oid, name, prob, market_id=1):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.current_probability = prob
    o.market_id = market_id
    o.probability_change_24h = None
    o.opening_probability = None
    o.rank = None
    o.team_id = None
    o.team = None
    return o


def _tl_market(outcomes, commence_time=None):
    m = MagicMock()
    m.id = 58321581
    m.name = "The Game Awards: Game of the Year"
    m.outcomes = outcomes
    m.commence_time = commence_time
    m.market_metadata = None
    m.llm_sport_category = "entertainment"
    m.source = "polymarket"
    m.status = "open"
    m.mutually_exclusive = True
    return m


async def _timeline(stamps, hours=168, top=3):
    outcomes = [
        _tl_outcome(216388319, "Grand Theft Auto VI", 0.65),
        _tl_outcome(216388320, "Resident Evil Requiem", 0.1044),
        _tl_outcome(216388337, "Slay the Spire 2", 0.015),
    ]
    market = _tl_market(outcomes)
    snaps = [
        _snapshot(o.id, "consensus", o.current_probability, stamp)
        for stamp in stamps
        for o in outcomes
    ]
    # `_Session` rather than a two-entry `side_effect`: the handler's call count
    # is not this test's subject, and a list that runs out raises
    # StopAsyncIteration — a harness story wearing the shape of a failure.
    db = _Session(_Result(scalar=market), _Result(snaps))

    return await get_probability_timeline(market_id=58321581, top=top, hours=hours, db=db)


class TestTheTimelineDoor:
    def test_the_measurement_reads_bucket_stamps(self):
        got = _measure_timeline_coverage([
            {"timestamp": FIRST.isoformat(), "outcomes": {}},
            {"timestamp": LAST.isoformat(), "outcomes": {}},
        ])

        assert got["coverage_hours"] == pytest.approx(19.31, abs=0.01)
        assert got["observation_times"] == 2

    def test_an_empty_timeline_is_null_and_not_zero(self):
        for empty in ([], None):
            got = _measure_timeline_coverage(empty)
            assert got["coverage_hours"] is None
            assert got["observation_times"] == 0

    def test_a_bucket_without_a_stamp_is_skipped_not_fatal(self):
        got = _measure_timeline_coverage(
            [{"outcomes": {}}, None, {"timestamp": LAST.isoformat()}]
        )

        assert got["observation_times"] == 1

    @pytest.mark.asyncio
    async def test_the_before_control_on_the_phones_own_door(self):
        """THE STRAWMAN GUARD for the door the screenshot came from.

        Twenty hours of buckets served under a 168-hour window, and until this
        fix the payload carried no way to tell them apart.
        """
        stamps = [LAST - timedelta(hours=h) for h in (20, 15, 10, 5, 0)]

        payload = await _timeline(stamps)

        assert payload["actual_hours"] == 168, "the search window is not the subject"
        assert payload["coverage_hours"] == pytest.approx(20.0, abs=0.3)
        assert payload["coverage_hours"] < payload["actual_hours"] / 8

    @pytest.mark.asyncio
    async def test_the_timeline_dates_its_own_coverage(self):
        stamps = [LAST - timedelta(hours=h) for h in (20, 10, 0)]

        payload = await _timeline(stamps)

        assert payload["coverage_start"] is not None
        assert payload["coverage_end"] is not None
        assert payload["coverage_start"] < payload["coverage_end"]
        assert payload["observation_times"] == len(payload["timeline"])

    @pytest.mark.asyncio
    async def test_no_existing_timeline_key_moved(self):
        """The control. `bucket_seconds` is NON-OPTIONAL in shipped iOS."""
        stamps = [LAST - timedelta(hours=h) for h in (20, 10, 0)]

        payload = await _timeline(stamps)

        assert payload["hours"] == 168
        assert payload["actual_hours"] == 168
        assert payload["top"] == 3
        assert isinstance(payload["bucket_seconds"], int)
        assert payload["market_id"] == 58321581
        assert payload["source"] == "polymarket"
        assert payload["sport_category"] == "entertainment"
        assert payload["timeline"], "the chart lost its series"
        assert payload["outcomes"], "the chart lost its legend"
