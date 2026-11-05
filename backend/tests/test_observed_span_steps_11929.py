"""#11929 Decide 27-B serve: an observed span draws flat at 15-minute steps.

Pinned here:

* off by default: with ``SERVE_OBSERVED_SPANS`` unset neither chart route reads
  the span table and both payloads are exactly as before;
* the step rule (``span_steps``): only inside a span; strictly before the next
  real point; a final step AT a span's end when the span ends first, and the
  stretch after it stays a gap; a tail only up to ``until``; never across an
  uncovered gap;
* ``/history``: steps carry ``provenance: "observed_span"`` and the earlier
  point's book, sorted into the line, never counted; ``/probability-timeline``:
  a step never displaces a value and never adds ``Field``;
* wiring: after the settled freezes and after coverage is measured;
* the span read on real PostgreSQL: an open span ends at its venue heartbeat.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app.utils.observed_span_steps as steps_mod
from app.utils.observed_span_steps import (
    OBSERVED_SPAN_PROVENANCE,
    SERVE_OBSERVED_SPANS_ENV,
    add_history_steps,
    add_timeline_steps,
    load_observed_spans,
    merge_spans,
    span_steps,
)
from tests.pm_bulk_test_support import cleanup_pg_engines  # noqa: F401 — autouse

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 11, 5, 18, 0, 0, tzinfo=timezone.utc)


def m(minutes):
    return T0 + timedelta(minutes=minutes)


@pytest.fixture
def serve_on(monkeypatch):
    monkeypatch.setenv(SERVE_OBSERVED_SPANS_ENV, "1")


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class SpanDB:
    """Answers the span read with ``rows`` [(oid, started, ended)]; ``fail`` raises."""

    def __init__(self, rows=(), fail=False):
        self.rows, self.fail, self.calls = list(rows), fail, []

    async def execute(self, stmt, params=None):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError("span read failed")
        return _Result([r for r in self.rows if r[0] in params["ids"]])


# ── the step rule ───────────────────────────────────────────────────────────


class TestSpanSteps:
    def test_inside_one_span_a_flat_stretch_draws_at_15_minute_steps(self):
        out = span_steps([(m(0), 0.4), (m(50), 0.45)], [(m(-10), m(50))], until=m(200))
        assert out == [(m(15), 0.4), (m(30), 0.4), (m(45), 0.4)]

    def test_a_step_never_lands_on_or_after_the_next_point(self):
        out = span_steps([(m(0), 0.4), (m(30), 0.5)], [(m(0), m(30))], until=m(90))
        assert out == [(m(15), 0.4)]

    def test_the_span_ending_first_gets_a_final_step_and_the_rest_stays_a_gap(self):
        out = span_steps([(m(0), 0.4), (m(120), 0.5)], [(m(0), m(40))], until=m(200))
        assert out == [(m(15), 0.4), (m(30), 0.4), (m(40), 0.4)]

    def test_no_span_no_steps_and_a_point_outside_every_span_gets_none(self):
        assert span_steps([(m(0), 0.4), (m(90), 0.5)], [], until=m(100)) == []
        assert span_steps([(m(0), 0.4), (m(90), 0.5)], [(m(5), m(80))], until=m(100)) == []

    def test_the_tail_runs_to_the_span_end_when_it_ends_before_now(self):
        out = span_steps([(m(0), 0.4)], [(m(0), m(35))], until=m(100))
        assert out == [(m(15), 0.4), (m(30), 0.4), (m(35), 0.4)]

    def test_the_tail_stops_before_until(self):
        assert span_steps([(m(0), 0.4)], [(m(0), m(100))], until=m(31)) == [(m(15), 0.4), (m(30), 0.4)]

    def test_no_until_means_no_tail(self):
        assert span_steps([(m(0), 0.4)], [(m(0), m(100))], until=None) == []

    def test_until_also_caps_a_fill_between_points(self):
        out = span_steps([(m(0), 0.4), (m(90), 1.0)], [(m(0), m(100))], until=m(40))
        assert out == [(m(15), 0.4), (m(30), 0.4)]

    def test_touching_spans_are_one_observation(self):
        assert merge_spans([(m(30), m(60)), (m(0), m(30)), (m(90), m(80))]) == [(m(0), m(60))]
        out = span_steps([(m(0), 0.4), (m(55), 0.5)], [(m(0), m(30)), (m(30), m(60))], until=m(99))
        # ...and the last point's tail reaches the joined span's end.
        assert out == [(m(15), 0.4), (m(30), 0.4), (m(45), 0.4), (m(60), 0.5)]


# ── the routes' helpers ─────────────────────────────────────────────────────


def _history(*pts):
    return {"history": [
        {"timestamp": at.isoformat(), "probability": p, "american_odds": None, "bookmaker": b}
        for at, p, b in pts
    ]}


class TestOffByDefault:
    async def test_no_span_read_and_nothing_added(self, monkeypatch):
        monkeypatch.delenv(SERVE_OBSERVED_SPANS_ENV, raising=False)
        db = SpanDB([(1, m(0), m(100))])
        hist = {1: _history((m(0), 0.4, "consensus"))}
        assert await add_history_steps(db, hist, now=m(100), until_for=lambda _o: m(100)) == 0
        assert await add_timeline_steps(db, {}, {1: "A"}, now=m(100), until=m(100)) == 0
        assert await load_observed_spans(db, [1], m(0), m(100)) == {}
        assert db.calls == [] and len(hist[1]["history"]) == 1


class TestHistorySteps:
    async def test_steps_are_marked_carry_the_earlier_book_and_sort_in(self, serve_on):
        db = SpanDB([(1, m(0), m(100)), (2, m(0), m(100))])
        hist = {
            1: _history((m(0), 0.4, "consensus"), (m(40), 0.42, "polymarket")),
            2: _history((m(0), 0.6, "consensus")),
        }
        added = await add_history_steps(db, hist, now=m(100), until_for=lambda _o: None)
        assert added == 2  # leg 1: 15, 30. Leg 2: no tail without `until`.
        line = hist[1]["history"]
        assert [pt["timestamp"] for pt in line] == [m(t).isoformat() for t in (0, 15, 30, 40)]
        step = line[1]
        assert step == {
            "timestamp": m(15).isoformat(), "probability": 0.4, "american_odds": None,
            "bookmaker": "consensus", "provenance": OBSERVED_SPAN_PROVENANCE,
        }
        assert db.calls[0]["start"] == m(0) and sorted(db.calls[0]["ids"]) == [1, 2]

    async def test_a_failed_span_read_serves_the_chart_without_steps(self, serve_on, caplog):
        hist = {1: _history((m(0), 0.4, "consensus"), (m(60), 0.5, "consensus"))}
        added = await add_history_steps(SpanDB(fail=True), hist, now=m(99), until_for=lambda _o: m(99))
        assert added == 0 and len(hist[1]["history"]) == 2
        assert "observed spans: read" in caplog.text


class TestTimelineSteps:
    async def test_a_step_never_displaces_a_value_and_never_adds_field(self, serve_on):
        entries = {
            m(0): {"timestamp": m(0).isoformat(), "outcomes": {"A": 0.4, "Field": 0.3}},
            m(30): {"timestamp": m(30).isoformat(), "outcomes": {"A": 0.41}},
            m(60): {"timestamp": m(60).isoformat(), "outcomes": {"A": 0.5}},
        }
        db = SpanDB([(7, m(0), m(60))])
        added = await add_timeline_steps(db, entries, {7: "A"}, now=m(60), until=m(60))
        assert added == 2
        assert entries[m(15)] == {
            "timestamp": m(15).isoformat(), "outcomes": {"A": 0.4}, "observed_span": ["A"],
        }
        assert entries[m(45)]["outcomes"] == {"A": 0.41}
        assert entries[m(30)]["outcomes"] == {"A": 0.41}  # the capture kept its seat
        assert "Field" not in entries[m(15)]["outcomes"]


# ── wiring ──────────────────────────────────────────────────────────────────


def _routes():
    return (BACKEND / "app" / "routes" / "futures.py").read_text()


class TestWiring:
    def test_history_steps_come_after_the_settled_freezes_and_after_coverage(self):
        src = _routes()
        freeze = src.index("_apply_settled_loser_freeze(\n        market, outcome_history, _settle_ts")
        coverage = src.index("_history_coverage = _measure_history_coverage(outcome_history)")
        hook = src.index("await add_history_steps(db, outcome_history")
        assert freeze < coverage < hook
        assert "**_history_coverage," in src[hook:hook + 2000]
        assert "total_data_points +=" not in src[coverage:hook]

    def test_timeline_steps_come_before_the_series_is_built_and_after_coverage(self):
        src = _routes()
        coverage = src.index("_timeline_coverage = _measure_timeline_coverage(")
        hook = src.index("await add_timeline_steps(", coverage)
        built = src.index("timeline = [entries_by_instant[at] for at in sorted(entries_by_instant)]", hook)
        assert coverage < hook < built
        assert "**_timeline_coverage," in src[built:built + 4000]

    def test_a_settled_board_gets_no_tail(self):
        src = _routes()
        hist = src[src.index("def _step_until(oid: int):"):src.index("await add_history_steps(")]
        assert "if _settle_ts is not None:\n            return min(_settle_ts, _steps_now)" in hist
        assert 'if oid in resolved_ids or (market.status or "").lower() == "resolved":\n            return None' in hist


# ── real PostgreSQL ─────────────────────────────────────────────────────────


class TestSpanReadOnRealPostgres:
    async def test_an_open_span_ends_at_its_venue_heartbeat(self, serve_on):
        from sqlalchemy import text
        from sqlalchemy.engine import make_url
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        import tests.pm_bulk_test_support as support
        from app.models.models import StreamObservedSpan, StreamSpanHeartbeat

        engine = support.pg_engine()  # skips without SEARCH_TEST_DATABASE_URL
        StreamObservedSpan.__table__.create(engine)
        StreamSpanHeartbeat.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO stream_observed_spans (venue, outcome_id, started_at, ended_at) VALUES "
                "('kalshi', 1, :a, :b), ('kalshi', 1, :c, NULL), ('kalshi', 2, :d, :e)"
            ), {"a": m(0), "b": m(30), "c": m(60), "d": m(-300), "e": m(-200)})
            conn.execute(text(
                "INSERT INTO stream_span_heartbeats (venue, beat_at) VALUES ('kalshi', :h)"
            ), {"h": m(95)})
        schema = support._ENGINES[-1][2]
        url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
        aengine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        try:
            async with AsyncSession(aengine) as session:
                spans = await load_observed_spans(session, [1, 2], m(-60), m(120))
        finally:
            await aengine.dispose()
        assert spans == {1: [(m(0), m(30)), (m(60), m(95))]}  # leg 2's span is outside


def test_the_module_reads_its_switch_per_request(monkeypatch):
    monkeypatch.setenv(SERVE_OBSERVED_SPANS_ENV, "0")
    assert not steps_mod.serve_spans_enabled()
    monkeypatch.setenv(SERVE_OBSERVED_SPANS_ENV, "1")
    assert steps_mod.serve_spans_enabled()
