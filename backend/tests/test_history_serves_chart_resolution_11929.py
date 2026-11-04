"""#11929 — `/history` serves a line at the chart's resolution, not every row.

Cause 1 of #11929 in Alex's framing: "the chart endpoint returns the bounded
series at the chart's resolution". A line longer than `CHART_RESOLUTION_POINTS`
is served as the last real observation in each slice of its window; a line that
fits is untouched. These pin: the bound, last-observation-per-slice (never an
interpolated or averaged value), the first point and settlement marks kept,
nothing #5898 withheld coming back, the additive shape, and the "a fuller
history is on its way" flag riding through unchanged.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes import futures as futures_route
from app.utils import history_resolution
from app.utils.history_resolution import (
    CHART_RESOLUTION_POINTS,
    bucket_seconds_for,
    thin_history_to_resolution,
    thin_line,
)
from tests.test_history_column_is_the_whole_field_8296 import _Result, _Session

BOOK = "datagolf_model"
A, B, FIELD, EMPTY = 1, 2, 3, 4
MINUTES = 36 * 60  # a point a minute for 36 h: 2,160 per line, ~3x the budget


def _pt(ts: datetime, p: float, **extra) -> dict:
    return {"timestamp": ts.isoformat(), "probability": p, "american_odds": None,
            "bookmaker": "consensus", **extra}


class TestThinLine:
    T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def test_bucket_width_is_the_window_over_the_plot_width_in_whole_minutes(self):
        assert CHART_RESOLUTION_POINTS == 730
        assert bucket_seconds_for(168 * 3600) == 840  # 1W -> 14 min
        assert bucket_seconds_for(720 * 3600) == 3600  # 1M -> 1 h
        assert bucket_seconds_for(1) == 60 and bucket_seconds_for(0) == 60

    def test_last_real_observation_per_bucket_never_a_new_value(self):
        line = [_pt(self.T0 + timedelta(minutes=i), i / 1000) for i in range(60)]
        out = thin_line(line, 600)  # 10-minute slices
        assert [p["probability"] for p in out] == [0.0] + [
            (10 * k + 9) / 1000 for k in range(6)
        ]
        # Every served point is an input point, byte for byte.
        assert all(p in line for p in out)

    def test_first_point_and_settlement_marks_are_always_kept(self):
        line = [_pt(self.T0 + timedelta(seconds=i), 0.4) for i in range(30)]
        line.insert(10, {**_pt(self.T0 + timedelta(seconds=9, milliseconds=500), 1.0),
                         "bookmaker": "settlement"})
        out = thin_line(line, 3600)
        assert out[0] is line[0]
        assert any(p["bookmaker"] == "settlement" for p in out)
        assert out[-1] is line[-1]

    def test_an_unparseable_stamp_is_kept_not_bucketed(self):
        line = [_pt(self.T0, 0.1), {"timestamp": "not a time", "probability": 0.2},
                _pt(self.T0 + timedelta(seconds=1), 0.3)]
        assert len(thin_line(line, 3600)) == 3

    def test_a_line_that_fits_is_untouched_and_no_block_is_served(self):
        history = {A: {"history": [_pt(self.T0 + timedelta(minutes=i), 0.5)
                                   for i in range(CHART_RESOLUTION_POINTS)]}}
        before = [dict(p) for p in history[A]["history"]]
        assert thin_history_to_resolution(
            history, window_hours=168, now=self.T0 + timedelta(days=1)
        ) is None
        assert history[A]["history"] == before

    def test_a_long_line_is_bounded_and_its_short_sibling_untouched(self):
        now = self.T0 + timedelta(days=7)
        long_line = [_pt(now - timedelta(minutes=i), 0.5) for i in range(10_080)][::-1]
        short = [_pt(now - timedelta(hours=i), 0.2) for i in range(5)][::-1]
        history = {A: {"history": list(long_line)}, B: {"history": list(short)}}
        block = thin_history_to_resolution(history, window_hours=168, now=now)
        assert len(history[A]["history"]) <= CHART_RESOLUTION_POINTS + 2
        assert history[B]["history"] == short
        assert block == {
            "bucket_seconds": 840, "max_points_per_line": 730, "lines_thinned": 1,
            "points_before": 10_080, "points_served": len(history[A]["history"]),
        }

    def test_the_window_reaches_back_to_the_oldest_served_point(self):
        """A `range=full` archive point older than the searched window widens it."""
        now = self.T0 + timedelta(days=60)
        line = [_pt(now - timedelta(minutes=i), 0.5) for i in range(1000)][::-1]
        line.insert(0, _pt(now - timedelta(days=60), 0.5))
        block = thin_history_to_resolution({A: {"history": line}}, window_hours=168, now=now)
        assert block["bucket_seconds"] == bucket_seconds_for(60 * 86400)


# --------------------------------------------------------------------------
# Through the handler
# --------------------------------------------------------------------------

def _outcome(oid, prob, *, is_winner=None, resolution_source=None):
    return SimpleNamespace(
        id=oid, name=f"Leg {oid}", team_id=None, probability_change_24h=None,
        current_probability=prob, current_yes_bid=None, current_yes_ask=None,
        resolution_source=resolution_source, is_winner=is_winner,
        last_updated=datetime.now(timezone.utc), price_changed_at=None,
        external_id=f"dg_{oid}",
    )


def _market(outcomes, *, status="open"):
    return SimpleNamespace(
        id=11929, name="Dense Board", source="datagolf", market_type="field",
        external_id="dg_dense", status=status, mutually_exclusive=True,
        outcomes=outcomes, resolution_date=None, settled_at=None,
        market_metadata={"shape": {
            "shape": "field", "exhaustive": True, "expected_winners": 1,
            "outcome_relation": "competitors", "confidence": "high",
        }},
    )


def _rows(now):
    """A point a minute per leg; one leg's every 7th minute is an empty-book midpoint."""
    rows = []
    for i in range(MINUTES):
        at = now - timedelta(minutes=MINUTES - i)
        a = 0.30 + 0.10 * math.sin(i / 40)
        for oid, value in ((A, a), (B, 0.25), (FIELD, 0.95 - a - 0.25)):
            rows.append(SimpleNamespace(
                outcome_id=oid, bookmaker=BOOK, probability=round(value, 6),
                yes_bid=None, yes_ask=None, last_price=None, captured_at=at,
            ))
        if i % 7 == 0:
            # #6757's empty-book midpoint: withheld from the drawn line (#5898).
            rows.append(SimpleNamespace(
                outcome_id=EMPTY, bookmaker=BOOK, probability=0.5,
                yes_bid=0.01, yes_ask=0.99, last_price=None, captured_at=at,
            ))
    rows.sort(key=lambda r: r.captured_at)
    return rows


async def _served(monkeypatch, *, thin=True, status="open", winner=None, venue=None, now=None):
    # One anchor per comparison: two reads a second apart are two fixtures.
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    outcomes = [
        _outcome(A, 0.3, is_winner=(True if winner == A else None),
                 resolution_source=("datagolf_results" if winner == A else None)),
        _outcome(B, 0.25), _outcome(FIELD, 0.4), _outcome(EMPTY, 0.5),
    ]
    if not thin:
        monkeypatch.setattr(history_resolution, "thin_history_to_resolution",
                            lambda *a, **k: None)
    if venue is not None:
        async def _venue(*_a, **_k):
            return venue
        monkeypatch.setattr(futures_route, "_load_generic_venue_history", _venue)
        monkeypatch.setattr(futures_route, "_plan_and_dispatch_generic_history_fill",
                            lambda *a, **k: "requested")
    rows = _rows(now)
    return await futures_route.get_futures_history(
        11929, outcome_id=None, hours=168, top_n=10, champion=None,
        db=_Session(_Result(value=_market(outcomes, status=status)),
                    _Result(rows=()), _Result(rows=rows)),
    ), rows


def _lines(payload):
    return {e["outcome_id"]: e["history"] for e in payload["outcomes"]}


class TestTheHandlerServesTheChartsResolution:
    @pytest.mark.asyncio
    async def test_every_line_is_bounded(self, monkeypatch):
        payload, _rows_ = await _served(monkeypatch)
        lines = _lines(payload)
        assert lines, "the board drew nothing"
        for oid, history in lines.items():
            assert len(history) <= CHART_RESOLUTION_POINTS + 2, (
                f"line {oid} served {len(history)} points — more than the chart's "
                f"{CHART_RESOLUTION_POINTS}-unit plot can draw (#11929)"
            )

    @pytest.mark.asyncio
    async def test_each_served_point_is_the_last_observation_of_its_slice(self, monkeypatch):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        full, _ = await _served(monkeypatch, thin=False, now=now)
        monkeypatch.undo()
        thinned, _ = await _served(monkeypatch, now=now)
        bucket = thinned["resolution"]["bucket_seconds"]
        for oid, raw in _lines(full).items():
            served = _lines(thinned)[oid]
            assert len(raw) > CHART_RESOLUTION_POINTS  # the fixture is dense
            assert served[0] == raw[0] and served[-1] == raw[-1]
            last_of: dict[int, dict] = {}
            for p in raw:
                last_of[int(datetime.fromisoformat(p["timestamp"]).timestamp()) // bucket] = p
            expected = [raw[0]] + [p for p in raw[1:] if p in last_of.values()]
            assert served == expected, f"line {oid}: not last-observation-per-slice"

    @pytest.mark.asyncio
    async def test_nothing_withheld_comes_back(self, monkeypatch):
        payload, rows = await _served(monkeypatch)
        empty_book = {r.captured_at.isoformat() for r in rows if r.outcome_id == EMPTY}
        assert EMPTY not in _lines(payload)
        for history in _lines(payload).values():
            assert all(p["probability"] != 0.5 or p["timestamp"] not in empty_book
                       for p in history)

    @pytest.mark.asyncio
    async def test_the_shape_is_additive(self, monkeypatch):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        full, _ = await _served(monkeypatch, thin=False, now=now)
        monkeypatch.undo()
        thinned, _ = await _served(monkeypatch, now=now)
        assert "resolution" not in full
        assert set(thinned) - set(full) == {"resolution"}
        block = thinned["resolution"]
        assert block["max_points_per_line"] == CHART_RESOLUTION_POINTS
        assert block["points_served"] == thinned["total_data_points"]
        assert block["points_before"] == full["total_data_points"]
        assert thinned["hours"] == full["hours"] == 168
        assert thinned["actual_hours"] == full["actual_hours"]
        # Coverage is what the chart DRAWS — first and last kept, so it holds.
        assert thinned["coverage_start"] == full["coverage_start"]
        assert thinned["coverage_end"] == full["coverage_end"]

    @pytest.mark.asyncio
    async def test_a_settled_line_still_ends_on_its_settlement_mark(self, monkeypatch):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        full, _ = await _served(monkeypatch, thin=False, status="settled", winner=A, now=now)
        monkeypatch.undo()
        thinned, _ = await _served(monkeypatch, status="settled", winner=A, now=now)
        full_end, thin_end = _lines(full)[A][-1], _lines(thinned)[A][-1]
        assert full_end["bookmaker"] == "settlement" and full_end["probability"] == 1.0
        assert thin_end == full_end
        assert "resolution" in thinned

    @pytest.mark.asyncio
    async def test_the_fuller_history_flag_rides_through(self, monkeypatch):
        """While the venue's history is on its way, the page's re-ask (#883) reads
        `venue_history.fill`; thinning must not drop or rewrite it."""
        venue = futures_route._GenericVenueHistory()
        venue.applicable = True
        venue.state = "cold"
        payload, _ = await _served(monkeypatch, venue=venue)
        assert payload["venue_history"]["fill"] == "requested"
        assert payload["venue_history"]["points_served"] == 0
        assert "resolution" in payload
