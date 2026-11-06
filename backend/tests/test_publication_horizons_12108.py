"""#12108 PR 1: the recorded blend at each grading horizon, and the coverage gauge.

Pinned here (plan §5 on #11850):

* the selector picks, per horizon, the highest-``rev`` row recorded at or before
  it — on a fixture whose rows straddle every horizon, including two rows with
  the same ``recorded_at`` and different ``rev``;
* an event with no row before a horizon gets ``None`` there, never a later row;
* the gauge: shares UNKNOWN with no events, growth from the previous size
  sample, the 2 GB/month alarm, and no table scan in its SQL;
* with ``PROBABILITY_PUBLICATION_RECORDING`` off, nothing runs (no read, no
  session, no run record).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import app.utils.publication_coverage as cov
from app.utils.probability_publication import RECORDING_FLAG
from app.utils.publication_reader import HORIZONS, horizon_rows, select_horizon_rows

START = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)


def h(hours_before: float) -> datetime:
    return START - timedelta(hours=hours_before)


class TestSelector:
    def test_each_horizon_takes_the_highest_rev_at_or_before_it(self):
        rows = [
            (1, h(30), 0.40),
            (2, h(24), 0.41),       # exactly T-24h: counts
            (3, h(10), 0.45),
            (5, h(6), 0.50),        # same instant as rev 4, later commit: wins
            (4, h(6), 0.49),
            (6, h(2), 0.52),
            (7, h(1) + timedelta(seconds=1), 0.53),  # one second after T-1h: not T-1h's
            (8, START, 0.55),
            (9, START + timedelta(minutes=5), 0.70),  # after the start: never served
        ]
        out = select_horizon_rows(rows, START)
        assert [name for name, _ in HORIZONS] == ["t_minus_24h", "t_minus_6h", "t_minus_1h", "start"]
        assert out["t_minus_24h"]["rev"] == 2 and out["t_minus_24h"]["blend_probability"] == 0.41
        assert out["t_minus_6h"]["rev"] == 5 and out["t_minus_6h"]["blend_probability"] == 0.50
        assert out["t_minus_1h"]["rev"] == 6
        assert out["start"]["rev"] == 8 and out["start"]["recorded_at"] == START.isoformat()

    def test_order_is_rev_not_recorded_at(self):
        # rev 11 committed after rev 10 but carries an EARLIER insert stamp.
        rows = [(10, h(2), 0.6), (11, h(3), 0.7)]
        assert select_horizon_rows(rows, START)["t_minus_1h"]["rev"] == 11

    def test_no_row_before_a_horizon_is_none_never_a_later_row(self):
        rows = [(1, h(3), 0.4), (2, h(0.5), 0.45)]
        out = select_horizon_rows(rows, START)
        assert out["t_minus_24h"] is None and out["t_minus_6h"] is None
        assert out["t_minus_1h"]["rev"] == 1 and out["start"]["rev"] == 2

    def test_no_start_or_no_rows_is_all_none(self):
        assert set(select_horizon_rows([(1, h(3), 0.4)], None).values()) == {None}
        assert set(select_horizon_rows([], START).values()) == {None}

    def test_a_null_blend_is_the_row_in_force_not_a_missing_row(self):
        out = select_horizon_rows([(1, h(3), 0.4), (2, h(2), None)], START)
        assert out["t_minus_1h"] == {"rev": 2, "recorded_at": h(2).isoformat(), "blend_probability": None}


class _Result:
    def __init__(self, scalar=None, rows=()):
        self._scalar, self._rows = scalar, list(rows)

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


class _DB:
    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    async def execute(self, stmt, params=None):
        self.calls += 1
        return self.results.pop(0)


class TestHorizonRowsRead:
    async def test_reads_the_start_then_the_rows(self):
        db = _DB(_Result(scalar=START), _Result(rows=[(1, h(2), 0.4)]))
        out = await horizon_rows(db, 15324072)
        assert out["event_id"] == 15324072 and out["start"] == START.isoformat()
        assert out["horizons"]["t_minus_1h"]["rev"] == 1 and db.calls == 2

    async def test_a_missing_event_is_none(self):
        assert await horizon_rows(_DB(_Result(scalar=None), _Result(scalar=None)), 1) is None


class TestGauge:
    def test_shares_are_unknown_with_no_events(self):
        out = cov.coverage_summary({"events_with_line": 0}, 1000, None)
        assert out["share_by_t_minus_1h"] is None and out["share_by_start"] is None
        assert out["projected_month_bytes"] is None and out["status"] == "ok"

    def test_coverage_shares(self):
        out = cov.coverage_summary(
            {"events_with_line": 40, "with_row_by_t_minus_1h": 36, "with_row_by_start": 39}, 10, None
        )
        assert out["share_by_t_minus_1h"] == 0.9 and out["share_by_start"] == 0.975

    def test_growth_from_the_previous_sample_and_the_alarm(self):
        now = START
        six_h = {"bytes": 1_000_000, "at": (now - timedelta(hours=6)).timestamp()}
        # +10 MB in 6 h → 40 MB/day → 1.2 GB/month: under the 2 GB alarm.
        quiet = cov.projected_month_bytes(11_000_000, now, six_h)
        assert quiet == pytest.approx(10_000_000 * 4 * 30)
        assert cov.coverage_summary({}, 11_000_000, quiet)["status"] == "ok"
        loud = cov.projected_month_bytes(1_000_000 + 20_000_000, now, six_h)  # 2.4 GB/month
        assert cov.coverage_summary({}, 21_000_000, loud)["status"] == "alarm"

    def test_no_or_too_recent_or_junk_sample_is_unknown_growth(self):
        assert cov.projected_month_bytes(5, START, None) is None
        assert cov.projected_month_bytes(5, START, {"bytes": 1, "at": START.timestamp() - 60}) is None
        assert cov.projected_month_bytes(5, START, {"bytes": "x", "at": 0}) is None

    def test_the_sql_never_scans_the_table(self):
        sql = " ".join(cov.COVERAGE_SQL.split()).lower()
        assert "where p.event_id = e.id and p.recorded_at <= e.commence_time - interval '1 hour'" in sql
        assert "where p.event_id = e.id and p.recorded_at <= e.commence_time" in sql
        assert "win_probability_sources ? 'betting'" in sql
        assert "count(*) from probability_publications" not in sql
        assert cov.SIZE_SQL == "SELECT pg_total_relation_size('probability_publications') AS table_bytes"

    def test_the_size_sample_is_swapped_and_a_redis_failure_costs_only_growth(self):
        class FakeRedis:
            def __init__(self, raw=None):
                self.raw, self.set_calls = raw, []

            def get(self, key):
                return self.raw

            def set(self, key, value, ex=None):
                self.set_calls.append((key, json.loads(value), ex))

        prev = {"bytes": 5, "at": 1.0}
        r = FakeRedis(json.dumps(prev))
        assert cov._swap_size_sample(9, START, r) == prev
        assert r.set_calls == [(cov.SIZE_SAMPLE_KEY, {"bytes": 9, "at": START.timestamp()}, cov.SIZE_SAMPLE_TTL_S)]

        class Broken:
            def get(self, key):
                raise ConnectionError("down")

        assert cov._swap_size_sample(9, START, Broken()) is None


class TestDark:
    async def test_off_reads_nothing(self, monkeypatch):
        monkeypatch.delenv(RECORDING_FLAG, raising=False)

        class Boom:
            async def execute(self, *a, **k):
                raise AssertionError("read while off")

        assert await cov.publication_coverage(Boom()) == {"status": "disabled"}

    def test_off_the_task_opens_no_session_and_records_no_run(self, monkeypatch):
        import app.tasks as tasks

        monkeypatch.delenv(RECORDING_FLAG, raising=False)
        monkeypatch.setattr(tasks, "_tracked_run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran while off")))
        assert tasks.probability_publication_coverage.run() == {"status": "disabled"}

    async def test_on_it_reads_and_reports(self, monkeypatch):
        monkeypatch.setenv(RECORDING_FLAG, "true")

        class Mapped:
            def __init__(self, row):
                self.row = row

            def mappings(self):
                return self

            def one(self):
                return self.row

            def scalar(self):
                return self.row

        class DB:
            def __init__(self):
                self.results = [
                    Mapped({"events_with_line": 10, "with_row_by_t_minus_1h": 9, "with_row_by_start": 10}),
                    Mapped(123456),
                ]

            async def execute(self, stmt, params=None):
                return self.results.pop(0)

        class NoSample:
            def get(self, key):
                return None

            def set(self, *a, **k):
                pass

        out = await cov.publication_coverage(DB(), now=START, redis=NoSample())
        assert out["share_by_t_minus_1h"] == 0.9 and out["table_bytes"] == 123456
        assert out["projected_month_bytes"] is None
