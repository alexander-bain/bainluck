"""#12042: a chart-series build logs its memory after each step.

`fill_futures_chart_series` peaked at 465 MB on worker-background (512 MB) for one
golf market on Nov 10 (+306 MB), and neither its candidate legs (33 markets) nor
its sampled snapshots (~37k rows) account for that. The build now logs
``futures_chart_series_memory market=<id> legs=rss/peak captures=... <venue>:<n>=...
series=...`` so the next runs name the step that grew. Log-only.
"""
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import futures_chart_series_fill as fill

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


class _Outcome:
    def __init__(self, oid, name, external_id):
        self.id = oid
        self.name = name
        self.external_id = external_id
        self.current_probability = 0.5


class _Market:
    def __init__(self, outcomes, created_at, source="kalshi", mid=900):
        self.id = mid
        self.source = source
        self.outcomes = outcomes
        self.created_at = created_at
        self.name = "Field"
        self.market_tier = 1
        self.llm_sport_category = "golf"


@pytest.fixture
def fake_memory(monkeypatch):
    from app.tasks import heavy_memory_turns as hmt

    readings = iter([(180.0, 190.0), (200.0, 210.0), (420.0, 465.0), (300.0, 465.0)])
    current = {}

    def rss():
        current["r"], current["p"] = next(readings)
        return current["r"]

    monkeypatch.setattr(hmt, "rss_mb", rss)
    monkeypatch.setattr(hmt, "peak_rss_mb", lambda: current["p"])


async def _build(monkeypatch, kalshi_raises=False):
    outcome = _Outcome(11, "Scottie Scheffler", "KXPGA-MAST-SS")
    market = _Market([outcome], NOW - timedelta(days=30))

    async def _legs(_s, _m, **_kw):
        return [market]

    async def _captures(_s, _ids):
        return {}

    async def _kalshi(_service, _outcomes, **_kw):
        if kalshi_raises:
            raise RuntimeError("venue down")
        return {"KXPGA-MAST-SS": [(NOW - timedelta(hours=h), 0.3 + h * 0.001) for h in range(48, 0, -1)]}

    monkeypatch.setattr(fill, "find_venue_legs", _legs)
    monkeypatch.setattr(fill, "capture_series_by_name", _captures)
    monkeypatch.setattr(fill, "kalshi_field_series", _kalshi)
    return await fill.build_market_series(None, market, kalshi_service=object(), now=NOW)


@pytest.mark.asyncio
async def test_each_step_logs_rss_and_peak_on_one_line(monkeypatch, fake_memory, caplog):
    with caplog.at_level(logging.INFO, logger=fill.__name__):
        payload = await _build(monkeypatch)
    lines = [r.getMessage() for r in caplog.records if "futures_chart_series_memory" in r.getMessage()]
    assert lines == [
        "futures_chart_series_memory market=900 legs=180.0/190.0 captures=200.0/210.0 "
        "kalshi:1=420.0/465.0 series=300.0/465.0"
    ]
    assert "rss" not in str(payload["stats"]), "the stamps must not reach the cached payload"


@pytest.mark.asyncio
async def test_a_failed_venue_still_stamps_its_step(monkeypatch, fake_memory, caplog):
    with caplog.at_level(logging.INFO, logger=fill.__name__):
        await _build(monkeypatch, kalshi_raises=True)
    line = [r.getMessage() for r in caplog.records if "futures_chart_series_memory" in r.getMessage()][0]
    assert " kalshi:1=420.0/465.0 " in line


@pytest.mark.asyncio
async def test_unreadable_memory_logs_none_and_the_build_still_returns(monkeypatch, caplog):
    from app.tasks import heavy_memory_turns as hmt

    monkeypatch.setattr(hmt, "rss_mb", lambda: None)
    monkeypatch.setattr(hmt, "peak_rss_mb", lambda: None)
    with caplog.at_level(logging.INFO, logger=fill.__name__):
        payload = await _build(monkeypatch)
    assert payload["market_id"] == 900
    line = [r.getMessage() for r in caplog.records if "futures_chart_series_memory" in r.getMessage()][0]
    assert "legs=None/None" in line


# --- #12042 fix: captures read only the chart's outcomes, aggregated per instant ---


class _RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.sql: list[str] = []

    async def execute(self, stmt):
        from sqlalchemy.dialects import postgresql

        self.sql.append(str(stmt.compile(dialect=postgresql.dialect())))
        rows = self.rows

        class _R:
            def all(self_inner):
                return rows

        return _R()


@pytest.mark.asyncio
async def test_captures_merge_sums_and_counts_into_the_same_mean_as_every_reading():
    t1 = NOW - timedelta(hours=2)
    t2 = NOW - timedelta(hours=1)
    # Two legs spell one golfer two ways; at t1 the kalshi row averages 2
    # readings (sum 1.0) and the odds_api row 3 readings (sum 0.9): the old
    # per-reading mean is 1.9 / 5.
    session = _RecordingSession([
        ("Scottie Scheffler", t1, 1.0, 2),
        ("scottie  scheffler", t1, 0.9, 3),
        ("Scottie Scheffler", t2, 0.4, 1),
        ("Rory McIlroy", t1, None, 0),  # all readings NULL: no point
    ])
    out = await fill.capture_series_by_name(session, [1, 2, 3])
    key = fill._norm("Scottie Scheffler")
    assert [round(p, 6) for _ts, p in out[key]] == [0.38, 0.4]
    assert fill._norm("Rory McIlroy") not in out
    sql = session.sql[0]
    assert "GROUP BY" in sql and "futures_odds_snapshots.outcome_id IN" in sql
    assert "sum(futures_odds_snapshots.probability)" in sql


@pytest.mark.asyncio
async def test_captures_read_nothing_for_no_outcomes():
    session = _RecordingSession([])
    assert await fill.capture_series_by_name(session, []) == {}
    assert session.sql == []


@pytest.mark.asyncio
async def test_the_build_reads_captures_only_for_the_chart_s_outcomes(monkeypatch):
    on_chart = [_Outcome(i, f"Player {i}", f"KX-{i}") for i in range(3)]
    off_chart = [_Outcome(100 + i, f"Longshot {i}", f"KX-L{i}") for i in range(20)]
    for i, o in enumerate(on_chart):
        o.current_probability = 0.5 - i * 0.01
    for o in off_chart:
        o.current_probability = 0.001
    market = _Market(on_chart + off_chart, NOW - timedelta(days=30))
    seen: list[list[int]] = []

    async def _legs(_s, _m, **_kw):
        return [market]

    async def _captures(_s, ids):
        seen.append(sorted(ids))
        return {}

    async def _kalshi(_service, _outcomes, **_kw):
        return {}

    monkeypatch.setattr(fill, "find_venue_legs", _legs)
    monkeypatch.setattr(fill, "capture_series_by_name", _captures)
    monkeypatch.setattr(fill, "kalshi_field_series", _kalshi)
    await fill.build_market_series(None, market, kalshi_service=object(), top_n=3, now=NOW)
    assert seen == [[0, 1, 2]], "captures read outcomes the chart does not draw"
