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
