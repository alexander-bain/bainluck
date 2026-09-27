"""A venue candle between two of our own readings is not drawn. #9111.

WHAT A READER SAW. `/events/15315470` (Crawley Town v Barnet, League Two,
postponed — ESPN 401881358 `STATUS_POSTPONED`) drew its win-probability line
flat at 22%, then a jump to exactly 50% at the scheduled kick-off (11:30Z 9/26)
and a solid ~31% block for two hours before returning to 22%. The match was
never played.

WHY. The page's series row is the twin 15311850 (#3810). Its Polymarket series
holds live readings every ~4 min (`ws_fast_lane` to 11:22:22, `live_fast` from
11:35:01) AND chart-backfill candles (`poll_type = history_backfill`). The
backfill skips minutes that already hold a reading, so a candle at 11:30:00
landed between readings at 11:22 and 11:35. The candles read 0.5, 0.255, 0.27
and 0.31; every live reading at the same minutes read 0.225 (bid 0.15 / ask
0.30). The chart drew the saw-tooth between the two instruments as a spike and
a block.

THE FIX. `/history` drops a candle whose neighbouring readings are no more than
20 min apart. The backfill still fills every stretch we did not watch — the
838 pre-match candles on the specimen, where our poll was hourly or absent,
all stay. Nothing is deleted from the table.

`SPECIMEN` is the stored rows of 15311850, source polymarket, 11:00-14:00Z
9/26, read from production 2026-09-27 — not hand-written.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import winprob_evidence
from app.utils.winprob_evidence import (
    CANDLE_UNDER_LIVE_MAX_GAP_S,
    EVIDENCE_CONTRACT,
    EVIDENCE_RESOLUTION_S,
    drop_candles_under_live_readings,
)

DAY = "2026-09-26"
CANDLE = "history_backfill"

# (captured_at UTC, home_win_probability, poll_type)
SPECIMEN = [
    ("11:02:49.549453", 0.225, "ws_fast_lane"),
    ("11:06:58.007251", 0.225, "ws_fast_lane"),
    ("11:09:25.496347", 0.225, "ws_fast_lane"),
    ("11:10:00.000000", 0.225, CANDLE),
    ("11:13:02.808623", 0.225, "ws_fast_lane"),
    ("11:14:34.624138", 0.225, "ws_fast_lane"),
    ("11:17:02.580463", 0.225, "ws_fast_lane"),
    ("11:18:20.116595", 0.225, "ws_fast_lane"),
    ("11:22:22.741452", 0.225, "ws_fast_lane"),
    ("11:30:00.000000", 0.5, CANDLE),
    ("11:35:01.180547", 0.225, "live_fast"),
    ("11:39:01.326984", 0.225, "live_fast"),
    ("11:43:01.181413", 0.225, "live_fast"),
    ("11:47:01.247504", 0.225, "live_fast"),
    ("11:50:00.000000", 0.255, CANDLE),
    ("11:51:01.344089", 0.225, "live_fast"),
    ("11:55:01.397712", 0.225, "live_fast"),
    ("11:59:01.104262", 0.225, "live_fast"),
    ("12:00:00.000000", 0.27, CANDLE),
    ("12:03:01.202256", 0.225, "live_fast"),
    ("12:07:01.912676", 0.225, "live_fast"),
    ("12:10:00.000000", 0.31, CANDLE),
    ("12:11:02.564471", 0.225, "live_fast"),
    ("12:15:01.345639", 0.225, "live_fast"),
    ("12:19:01.321789", 0.225, "live_fast"),
    ("12:23:01.635573", 0.225, "live_fast"),
    ("12:27:02.348062", 0.225, "live_fast"),
    ("12:31:01.340087", 0.225, "live_fast"),
    ("12:35:01.434320", 0.225, "live_fast"),
    ("12:39:01.263703", 0.225, "live_fast"),
    ("12:40:00.000000", 0.31, CANDLE),
    ("12:43:01.942793", 0.225, "live_fast"),
    ("12:47:01.608033", 0.225, "live_fast"),
    ("12:51:01.088016", 0.225, "live_fast"),
    ("12:55:01.422861", 0.225, "live_fast"),
    ("12:59:01.246599", 0.225, "live_fast"),
    ("13:01:01.193516", 0.225, "live_fast"),
    ("13:05:01.564339", 0.225, "live_fast"),
    ("13:09:01.402721", 0.225, "live_fast"),
    ("13:10:00.000000", 0.31, CANDLE),
    ("13:13:01.795297", 0.225, "live_fast"),
    ("13:17:01.845983", 0.225, "live_fast"),
    ("13:21:01.472204", 0.225, "live_fast"),
    ("13:25:01.906596", 0.225, "live_fast"),
    ("13:28:00.000000", 0.31, CANDLE),
    ("13:29:06.025714", 0.225, "live_fast"),
    ("13:33:02.287198", 0.225, "live_fast"),
    ("13:37:01.591752", 0.225, "live_fast"),
    ("13:41:02.808217", 0.225, "live_fast"),
    ("13:45:01.618515", 0.225, "live_fast"),
    ("13:49:01.568097", 0.225, "live_fast"),
    ("13:54:13.856763", 0.225, "live_fast"),
    ("13:58:13.952187", 0.225, "live_fast"),
]

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _served(ts: str, home: float, poll_type: str, **state) -> dict:
    return {
        "timestamp": f"{DAY}T{ts}+00:00",
        "home_probability": home,
        "away_probability": round(1 - home, 4),
        "draw_probability": None,
        "game_state": {"poll_type": poll_type, **state},
    }


def _at(minutes: float, poll_type: str = "live_fast", home: float = 0.4, **state) -> dict:
    return {
        "timestamp": (T0 + timedelta(minutes=minutes)).isoformat(),
        "home_probability": home,
        "away_probability": round(1 - home, 4),
        "draw_probability": None,
        "game_state": {"poll_type": poll_type, **state},
    }


def _specimen() -> list[dict]:
    return [_served(*row) for row in SPECIMEN]


def _candles(points: list[dict]) -> list[dict]:
    return [p for p in points if p["game_state"].get("poll_type") == CANDLE]


class TestTheSpecimen:
    def test_the_fifty_percent_kickoff_candle_is_not_drawn(self):
        kept, _ = drop_candles_under_live_readings(_specimen())

        assert 0.5 not in [p["home_probability"] for p in kept]

    def test_every_candle_between_live_readings_goes_and_every_reading_stays(self):
        series = _specimen()
        kept, dropped = drop_candles_under_live_readings(series)

        assert dropped == len(_candles(series)) == 8
        assert _candles(kept) == []
        assert kept == [p for p in series if p["game_state"]["poll_type"] != CANDLE]

    def test_the_drawn_line_is_flat_where_every_reading_agreed(self):
        kept, _ = drop_candles_under_live_readings(_specimen())

        assert {p["home_probability"] for p in kept} == {0.225}

    def test_the_kickoff_handoff_gap_is_inside_the_bound(self):
        """11:22:22 → 11:35:01 is the widest gap on the specimen, and the 0.5
        candle sits in it; the bound must cover it or the spike survives."""
        before = datetime.fromisoformat(f"{DAY}T11:22:22.741452+00:00")
        after = datetime.fromisoformat(f"{DAY}T11:35:01.180547+00:00")

        assert (after - before).total_seconds() <= CANDLE_UNDER_LIVE_MAX_GAP_S


class TestWhatTheBackfillIsForSurvives:
    def test_candles_between_hourly_pre_match_readings_are_kept(self):
        series = [
            _at(-180), _at(-170, CANDLE, 0.41), _at(-150, CANDLE, 0.43),
            _at(-120), _at(-100, CANDLE, 0.45), _at(-60),
        ]
        kept, dropped = drop_candles_under_live_readings(series)

        assert dropped == 0
        assert kept == series

    def test_candles_before_our_first_reading_and_after_our_last_are_kept(self):
        series = [
            _at(-30, CANDLE, 0.3), _at(-10, CANDLE, 0.35),
            _at(0), _at(4), _at(8),
            _at(9, CANDLE, 0.6), _at(15, CANDLE, 0.7),
        ]
        kept, dropped = drop_candles_under_live_readings(series)

        assert dropped == 0
        assert kept == series

    def test_a_series_of_candles_alone_is_served_whole(self):
        series = [_at(m, CANDLE, 0.3 + m / 1000) for m in range(0, 60, 5)]
        kept, dropped = drop_candles_under_live_readings(series)

        assert dropped == 0
        assert kept == series

    def test_a_series_with_no_candle_is_returned_untouched(self):
        series = [_at(0), _at(4), _at(8)]
        kept, dropped = drop_candles_under_live_readings(series)

        assert dropped == 0
        assert kept is series


class TestTheBound:
    @pytest.mark.parametrize(
        "gap_minutes, dropped",
        [(CANDLE_UNDER_LIVE_MAX_GAP_S / 60, 1), (CANDLE_UNDER_LIVE_MAX_GAP_S / 60 + 1 / 60, 0)],
    )
    def test_exactly_the_bound_drops_and_one_second_wider_keeps(self, gap_minutes, dropped):
        series = [_at(0), _at(gap_minutes / 2, CANDLE, 0.9), _at(gap_minutes)]
        _, n = drop_candles_under_live_readings(series)

        assert n == dropped

    def test_a_retention_keeper_is_measured_from_its_proven_end(self):
        """The 48-hour collapse merges a flat run into its earliest row and
        stamps `covered_through`; the gap to the next reading is from THERE."""
        through = (T0 + timedelta(minutes=58)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        span = {
            "contract": EVIDENCE_CONTRACT,
            "resolution_s": EVIDENCE_RESOLUTION_S,
            "covered_through": through,
        }
        stamped = [_at(0, evidence_span=span), _at(59, CANDLE, 0.9), _at(61)]
        unstamped = [_at(0), _at(59, CANDLE, 0.9), _at(61)]

        assert drop_candles_under_live_readings(stamped)[1] == 1
        assert drop_candles_under_live_readings(unstamped)[1] == 0

    @pytest.mark.parametrize(
        "neighbour_state",
        [
            {"poll_type": CANDLE},
            {"poll_type": "price_fill", "backfill": True},
            {"backfilled": True, "seconds_left": 100},
            {"final": True},
        ],
        ids=["candle", "price_history", "espn_reread", "final"],
    )
    def test_only_our_own_readings_bracket_a_candle(self, neighbour_state):
        def neighbour(minutes):
            point = _at(minutes)
            point["game_state"] = dict(neighbour_state)
            return point

        series = [neighbour(0), _at(2, CANDLE, 0.9), neighbour(4)]

        assert drop_candles_under_live_readings(series)[1] == 0

    def test_a_live_edge_does_not_bracket_a_candle(self):
        edge = _at(4)
        edge["live_edge"] = True
        series = [_at(0), _at(2, CANDLE, 0.9), edge]

        assert drop_candles_under_live_readings(series)[1] == 0


class TestTheRoute:
    def test_the_route_drops_before_the_blend_and_the_metadata(self):
        """The aggregate line is built from `win_prob_history`, and the legend's
        `snapshot_count` is rendered: both must see the series after the drop."""
        source = (
            pathlib.Path(winprob_evidence.__file__)
            .parents[1]
            .joinpath("routes", "events.py")
            .read_text()
        )
        assert source.count("drop_candles_under_live_readings(\n") == 1
        drop = source.index("drop_candles_under_live_readings(\n")
        loop = source.rindex("for _src in list(win_prob_history):", 0, drop)
        assert "win_prob_history[_src], _ = drop_candles_under_live_readings(" in source[loop:drop + 40]
        assert drop < source.index("win_prob_sources_meta[source_key] = {")
        assert drop < source.index("aggregate_line = []", drop)
        assert drop < source.index(
            "_extend_win_prob_history_to_live_edge(\n        win_prob_history,", drop
        )
