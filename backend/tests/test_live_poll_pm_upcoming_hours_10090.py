"""#10090 decision L — the 2-minute poll's Polymarket window is a setting.

`_load_live_poll_population` read every scheduled event starting within a
literal 3 h, for both venues. The Polymarket legs now read
`LIVE_POLL_PM_UPCOMING_HOURS` (env, read once at import, default 3, clamped to
1..12); the Kalshi legs stay at 3 h. Alex approved L (ALEX-DECISIONS item 42):
the socket carries live + 3 h and this poll carries Polymarket out to 6 h, so
no game inside 6 h is priced by the hourly poll alone.

These arms read the statement the session is handed. The real-Postgres half
(at 6, a 5 h Polymarket game is polled and a 5 h Kalshi game is not) is
`TestThePolymarketWindowIsItsOwn` in
`integration/test_live_poll_kalshi_prices_real_postgres.py`, run by CI's #3569
step.
"""

import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import prediction_market_matching as pmm

#: A fixed instant; nothing here reads the clock.
NOW = datetime(2026, 10, 30, 15, 0, tzinfo=timezone.utc)


class _Result:
    def all(self):
        return []


class _Session:
    """Records the population read and answers it with no rows."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result()


async def _population_sql(monkeypatch, pm_hours: int) -> str:
    monkeypatch.setattr(pmm, "LIVE_POLL_PM_UPCOMING_HOURS", pm_hours)
    session = _Session()
    await pmm._load_live_poll_population(session, NOW)
    assert len(session.statements) == 1, "an empty population makes one read"
    return " ".join(
        str(
            session.statements[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        ).split()
    )


def _bound(hours: int) -> str:
    return f"events.commence_time <= '{(NOW + timedelta(hours=hours)).isoformat(sep=' ')}'"


class TestTheEnv:
    def test_the_default_is_three(self):
        assert pmm.LIVE_POLL_PM_UPCOMING_HOURS_DEFAULT == 3

    def test_the_kalshi_window_is_three(self):
        assert pmm._LIVE_POLL_KALSHI_UPCOMING_HOURS == 3

    def test_unset_reads_three(self, monkeypatch):
        monkeypatch.delenv("LIVE_POLL_PM_UPCOMING_HOURS", raising=False)
        assert pmm._live_poll_pm_upcoming_hours_env() == 3

    def test_blank_reads_three(self, monkeypatch):
        monkeypatch.setenv("LIVE_POLL_PM_UPCOMING_HOURS", "  ")
        assert pmm._live_poll_pm_upcoming_hours_env() == 3

    def test_six_reads_six_without_a_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("LIVE_POLL_PM_UPCOMING_HOURS", "6")
        with caplog.at_level(logging.WARNING, logger=pmm.logger.name):
            assert pmm._live_poll_pm_upcoming_hours_env() == 6
        assert not caplog.records

    @pytest.mark.parametrize("raw,expected", [("0", 1), ("-4", 1), ("13", 12), ("48", 12)])
    def test_out_of_range_is_clamped_with_one_warning(
        self, monkeypatch, caplog, raw, expected
    ):
        monkeypatch.setenv("LIVE_POLL_PM_UPCOMING_HOURS", raw)
        with caplog.at_level(logging.WARNING, logger=pmm.logger.name):
            assert pmm._live_poll_pm_upcoming_hours_env() == expected
        assert len(caplog.records) == 1
        assert "outside 1..12" in caplog.records[0].getMessage()

    @pytest.mark.parametrize("raw", ["6h", "4.5", "six"])
    def test_garbage_is_the_default_with_one_warning(self, monkeypatch, caplog, raw):
        monkeypatch.setenv("LIVE_POLL_PM_UPCOMING_HOURS", raw)
        with caplog.at_level(logging.WARNING, logger=pmm.logger.name):
            assert pmm._live_poll_pm_upcoming_hours_env() == 3
        assert len(caplog.records) == 1
        assert "not a whole number" in caplog.records[0].getMessage()


class TestTheReadIsPerVenue:
    async def test_at_six_polymarket_is_bounded_at_six_and_kalshi_at_three(
        self, monkeypatch
    ):
        sql = await _population_sql(monkeypatch, 6)
        assert (
            f"futures_markets.source = 'kalshi' AND {_bound(3)}" in sql
        ), sql
        assert (
            f"futures_markets.source = 'polymarket' AND {_bound(6)}" in sql
        ), sql

    async def test_at_the_default_both_venues_end_at_three(self, monkeypatch):
        sql = await _population_sql(monkeypatch, 3)
        assert f"futures_markets.source = 'kalshi' AND {_bound(3)}" in sql, sql
        assert f"futures_markets.source = 'polymarket' AND {_bound(3)}" in sql, sql
        assert _bound(6) not in sql

    async def test_the_lower_bound_and_live_arm_are_unchanged(self, monkeypatch):
        sql = await _population_sql(monkeypatch, 6)
        assert "events.status = 'live'" in sql
        assert "events.status = 'scheduled'" in sql
        assert f"events.commence_time > '{NOW.isoformat(sep=' ')}'" in sql
