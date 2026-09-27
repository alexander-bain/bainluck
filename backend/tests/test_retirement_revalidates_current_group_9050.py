"""A queued retirement may not erase a now-backed price or a sibling (#9050).

Database locking/interleavings are covered by the separate PostgreSQL suite.
These cases exercise the real retirement predicates with stale candidate refs
and independently supplied current database rows, including no-op lock release.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app.tasks.prediction_market_matching import _LinkedMarketRef, _retire_unbacked_blend_source

HOME, AWAY = "Boston Red Sox", "Chicago Cubs"
NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)


def market(name=None, status="open", mid=10):
    return NS(id=mid, source="polymarket", external_id=f"pm-{mid}",
              name=name or f"{HOME} vs. {AWAY}", status=status)


def outcome(name=HOME, price=.7, mid=10, rank=1):
    return NS(id=100 + rank, market_id=mid, name=name, current_probability=price,
              current_yes_bid=None, current_yes_ask=None, rank=rank,
              last_updated=NOW, is_winner=False)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, markets, outcomes, *, completed=False, sources=None):
        self.event = NS(id=1, home_team_name=HOME, away_team_name=AWAY,
                        commence_time=NOW - timedelta(hours=1),
                        completed_at=NOW if completed else None,
                        win_probability_sources=sources if sources is not None else {
                            "polymarket": {"value": .7}, "kalshi": {"value": .8}})
        self.markets, self.outcomes = markets, outcomes
        self.selects, self.updates, self.commits = [], [], 0

    async def execute(self, stmt):
        sql = str(stmt)
        if sql.startswith("UPDATE"):
            self.updates.append(stmt)
            return Result([])
        self.selects.append(sql)
        if "FROM events" in sql:
            assert "FOR UPDATE" in sql
            return Result([self.event])
        if "FROM futures_markets" in sql:
            return Result(self.markets)
        if "FROM futures_outcomes" in sql:
            return Result(self.outcomes)
        raise AssertionError(sql)

    async def commit(self):
        self.commits += 1


def anchor():
    # This stale candidate claims a derivative-only group and stale team names.
    return _LinkedMarketRef(10, "polymarket", "pm-10", "Exact Score", 1,
                            NOW - timedelta(days=1), "Old home", "Old away",
                            status="resolved", event_has_result=False)


@pytest.mark.asyncio
async def test_current_winner_quote_vetoes_old_derivative_decision():
    session = Session([market()], [outcome(), outcome(AWAY, .3, rank=2)])
    assert not await _retire_unbacked_blend_source(session, anchor(), [], {})
    assert session.updates == []
    assert session.commits == 1
    assert len(session.selects) == 3


@pytest.mark.asyncio
async def test_still_unbacked_source_retires_preserving_current_sibling():
    session = Session([market("Boston Red Sox vs. Chicago Cubs - Exact Score")],
                      [outcome("2 - 1", .07)])
    stats = {}
    assert await _retire_unbacked_blend_source(session, anchor(), [], stats)
    values = {column.name: value.value for column, value in session.updates[0]._values.items()}
    assert values == {"win_probability_sources": {"kalshi": {"value": .8}}}
    assert stats["funnel"] == {"blend_source_retired_no_winner_market": 1}
    assert session.commits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prices", [(None, None), ()])
async def test_current_transient_unpriced_or_empty_winner_keeps_source(prices):
    outcomes = [outcome(HOME if i == 0 else AWAY, p, rank=i + 1)
                for i, p in enumerate(prices)]
    session = Session([market()], outcomes)
    assert not await _retire_unbacked_blend_source(session, anchor(), [], {})
    assert session.updates == []
    assert session.commits == 1


@pytest.mark.asyncio
async def test_phase2c_cannot_promote_fresh_derivative_silence_to_retirement():
    session = Session([market("Boston Red Sox vs. Chicago Cubs - Exact Score")],
                      [outcome("2 - 1", .07)])
    assert not await _retire_unbacked_blend_source(
        session, anchor(), [], {}, settled_only=True)
    assert session.updates == []
    assert session.commits == 1


@pytest.mark.asyncio
async def test_phase2c_refuses_after_event_acquires_result():
    session = Session([market(status="resolved")], [outcome(price=1)], completed=True)
    assert not await _retire_unbacked_blend_source(
        session, anchor(), [], {}, settled_only=True)
    assert session.updates == []
    assert session.commits == 1


@pytest.mark.asyncio
async def test_already_absent_source_releases_lock_without_write():
    session = Session([], [], sources={"kalshi": {"value": .8}})
    assert not await _retire_unbacked_blend_source(session, anchor(), [], {})
    assert session.updates == []
    assert session.commits == 1
