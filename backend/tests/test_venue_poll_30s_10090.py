"""#10090 — the 30-second venue poll: dark switch, budgets, rotation, history
bound, hand-off reading, Kalshi refusals, 429 back-off and the time budget.

The SQL and the write path are proved against real Postgres in
``tests/integration/test_venue_poll_30s_real_postgres_10090.py``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.tasks import venue_poll_30s as v


# ── the switch ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, set()),
        ("", set()),
        ("0", set()),
        ("off", set()),
        ("1", {"kalshi", "polymarket"}),
        ("all", {"kalshi", "polymarket"}),
        ("kalshi", {"kalshi"}),
        ("polymarket, kalshi", {"kalshi", "polymarket"}),
        ("bogus", set()),
    ],
)
def test_the_switch_is_off_unless_it_names_a_venue(raw, expected):
    env = {} if raw is None else {v.ENABLED_ENV: raw}
    assert v.enabled_venues(env) == expected


def test_a_dark_tick_touches_neither_redis_nor_the_database(monkeypatch):
    from app import tasks

    monkeypatch.delenv(v.ENABLED_ENV, raising=False)

    def explode(*_a, **_k):
        raise AssertionError("a dark tick must not take a lease or open a session")

    monkeypatch.setattr("app.utils.single_flight.single_flight", explode)
    monkeypatch.setattr("app.tasks.base.get_task_session", explode)
    assert tasks.poll_venue_prices_30s.run() == {"status": "disabled", "terminal": "complete"}


def test_the_beat_entry_is_30_seconds_on_realtime_and_expires_in_one_period():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["poll-venue-prices-30s"]
    assert entry["task"] == "app.tasks.poll_venue_prices_30s"
    assert entry["schedule"] == 30.0
    assert entry["options"]["expires"] == 30
    assert celery_app.conf.task_routes["app.tasks.poll_venue_prices_30s"] == {"queue": "realtime"}


# ── budgets and rotation ──────────────────────────────────────────────────────


def _unit(key, n, market=None):
    market = int(key) if market is None else market
    return v.Unit(key, {market: [(market * 1000 + i, f"T{key}-{i}") for i in range(n)]})


def test_kalshi_requests_pack_whole_markets_within_the_ticker_and_request_budgets():
    units = [_unit(str(k), 30) for k in range(1, 11)]  # 300 tickers
    groups = v.kalshi_requests(units, budget=2)
    chunks = [c for _u, cs in groups for c in cs]
    assert len(chunks) == 2
    assert all(len(c) <= v.KALSHI_TICKERS_PER_REQUEST for c in chunks)
    # A market is never split: each group's tickers are exactly its markets'.
    for group_units, cs in groups:
        assert sum(u.leg_count() for u in group_units) == sum(len(c) for c in cs)
    assert [g[0][0].key for g in groups] == ["1", "4"]


def test_a_market_larger_than_one_request_spans_requests_and_counts_against_the_budget():
    big = _unit("1", 250)
    groups = v.kalshi_requests([big, _unit("2", 5)], budget=3)
    assert len(groups[0][1]) == 3 and groups[0][0] == [big]
    assert len(groups) == 1  # the budget is spent; market 2 waits for the next pass
    assert v.kalshi_requests([big], budget=2) == []  # never half a market


def test_polymarket_requests_batch_events_within_the_budget():
    units = [_unit(str(k), 2) for k in range(1, 46)]
    groups = v.polymarket_requests(units, budget=2)
    assert [len(cs[0]) for _u, cs in groups] == [v.PM_EVENTS_PER_REQUEST] * 2


def test_rotation_starts_after_the_cursor_and_wraps():
    units = [_unit(str(k), 1) for k in (3, 10, 25)]
    assert [u.key for u in v.rotate(units, "10")] == ["25", "3", "10"]
    assert [u.key for u in v.rotate(units, None)] == ["3", "10", "25"]
    assert [u.key for u in v.rotate(units, "99")] == ["3", "10", "25"]


def test_build_units_groups_polymarket_markets_by_gamma_event():
    rows = [(1, "500", 11, "0xa_yes"), (1, "500", 12, "0xa_no"), (2, "500", 21, "0xb"), (3, None, 31, "0xc")]
    (unit,) = v.build_units("polymarket", rows)
    assert unit.key == "500" and unit.legs == {1: [(11, "0xa_yes"), (12, "0xa_no")], 2: [(21, "0xb")]}


def test_items_for_a_polymarket_market_are_its_own_conditions_only():
    found = [{"external_id": "0xa"}, {"external_id": "0xb"}]
    assert v._items_for_market("polymarket", [(1, "0xa_yes"), (2, "0xa_no")], found) == [{"external_id": "0xa"}]


# ── the history bound ─────────────────────────────────────────────────────────


def _poll(last_point=None, stored=None, now=None):
    now = now or datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)
    return v.PollWrite(
        fetched_at=now,
        now=now,
        stored=stored or {},
        last_point=last_point or {},
        allowed=frozenset({1, 2}),
    )


def test_a_leg_whose_price_and_book_are_unchanged_is_not_written():
    poll = _poll(stored={1: (0.4, 0.39, 0.41)})
    stats = {}
    assert poll.admit(1, 0.4, 0.39, 0.41, stats) is False
    assert stats == {"legs_unchanged": 1} and 1 in poll.unchanged
    assert poll.admit(1, 0.4, 0.38, 0.41, stats) is True  # the book moved


def test_a_leg_the_pass_does_not_poll_is_never_admitted():
    stats = {}
    assert _poll().admit(99, 0.5, 0.49, 0.51, stats) is False
    assert stats == {"legs_not_polled": 1}


def test_history_points_on_change_at_most_one_per_interval_unless_the_move_is_big():
    now = datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)
    recent = now - timedelta(seconds=10)
    old = now - timedelta(seconds=v.HISTORY_MIN_INTERVAL_S + 1)
    stats = {}
    assert _poll(now=now).history(1, 0.5, stats) is True  # no point yet
    assert _poll({1: (recent, 0.5)}, now=now).history(1, 0.5, stats) is False  # no change
    assert _poll({1: (recent, 0.5)}, now=now).history(1, 0.51, stats) is False  # deferred
    assert stats["history_deferred"] == 1
    assert _poll({1: (recent, 0.5)}, now=now).history(1, 0.5 + v.HISTORY_BIG_MOVE, stats) is True
    assert _poll({1: (old, 0.5)}, now=now).history(1, 0.51, stats) is True


def test_a_deferred_move_gains_its_point_once_the_interval_passes():
    now = datetime(2026, 10, 30, 14, 0, tzinfo=timezone.utc)
    poll = _poll({1: (now - timedelta(seconds=10), 0.50)}, stored={1: (0.51, 0.5, 0.52)}, now=now)
    poll.admit(1, 0.51, 0.5, 0.52, {})
    assert poll.trailing() == []  # still inside the interval
    later = _poll({1: (now - timedelta(seconds=10), 0.50)}, stored={1: (0.51, 0.5, 0.52)},
                  now=now + timedelta(seconds=v.HISTORY_MIN_INTERVAL_S))
    later.admit(1, 0.51, 0.5, 0.52, {})
    assert later.trailing() == [(1, (0.51, 0.5, 0.52))]
    assert later.trailing() == []  # once


def test_an_unchanged_leg_with_no_history_gains_no_point_just_for_being_read():
    poll = _poll(stored={1: (0.4, 0.39, 0.41)})
    poll.admit(1, 0.4, 0.39, 0.41, {})
    assert poll.trailing() == []


# ── hand-off: the sockets' own windows ────────────────────────────────────────


def test_both_socket_windows_still_read_as_six_hours_with_the_band_inside_them():
    """If a socket's window changes shape this goes red, rather than the band
    silently emptying (see ``_handoff_band_sql``)."""
    from app.tasks.kalshi_ws import SUBSCRIPTION_REFRESH_SECONDS, _kalshi_slate_event_window
    from app.tasks.polymarket_ws import _slate_event_window

    for window in (_kalshi_slate_event_window(), _slate_event_window()):
        sql = v._render(window)
        assert v._upcoming_hours(sql) == 6
        band = v._handoff_band_sql(sql)
        assert f"secs => {6 * 3600 - SUBSCRIPTION_REFRESH_SECONDS - v.HANDOFF_SLACK_S}" in band


def test_the_population_sql_carries_the_shipped_socket_predicates_verbatim():
    from app.tasks.kalshi_ws import _kalshi_slate_event_window
    from app.tasks.ws_open_contracts import kalshi_open_contract_stmt

    sql = v.kalshi_population_sql(open_arm=True)
    assert v._render(_kalshi_slate_event_window()) in sql
    assert v._render(kalshi_open_contract_stmt().whereclause) in sql
    assert v._render(kalshi_open_contract_stmt().whereclause) not in v.kalshi_population_sql(open_arm=False)


def test_an_unreadable_window_hands_off_exactly_at_the_predicate():
    assert v._handoff_band_sql("(e.status = 'live')") == "FALSE"


# ── Kalshi pricing rules ──────────────────────────────────────────────────────


def _raw(ticker, *, bid="0.4500", ask="0.4700", last="0.4600", status="active", result=""):
    return {
        "ticker": ticker,
        "event_ticker": "KXE",
        "title": ticker,
        "status": status,
        "result": result,
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "last_price_dollars": last,
    }


def test_kalshi_items_price_by_the_2_hour_poll_rules_and_refuse_settled_and_withdrawn():
    from app.services.kalshi_api import KalshiAPIService

    raw = [
        _raw("kxe-open"),
        _raw("KXE-SETTLED", result="yes"),
        _raw("KXE-GONE", status="inactive"),
        _raw("KXE-WIDE", bid="0.0100", ask="0.9900", last=None),
    ]
    stats = {}
    items = v.kalshi_items(KalshiAPIService(api_key="x"), raw, stats)
    assert set(items) == {"KXE-OPEN"}
    assert items["KXE-OPEN"]["probability"] == pytest.approx(0.46)
    assert stats["refused_settled"] == 1 and stats["refused_withdrawn"] == 1
    assert stats["no_price"] == 1


def test_kalshi_tickers_ride_one_comma_separated_read():
    from app.services.kalshi_api import KalshiAPIService

    seen = {}

    class _Client:
        async def get(self, url, params):
            seen.update(params)
            return httpx.Response(200, json={"markets": []}, request=httpx.Request("GET", url))

    service = KalshiAPIService(api_key="x")
    service.client = _Client()
    import asyncio

    asyncio.run(service.get_markets(status=None, tickers=["A", "B"], limit=2))
    assert seen == {"limit": 2, "tickers": "A,B"}


# ── one venue's pass: 429 and the budget ──────────────────────────────────────


class _Session:
    def __init__(self):
        self.commits = 0

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one(self):
                return datetime.now(timezone.utc)

        return _R()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _wire_pass(monkeypatch, *, units, fetch):
    @asynccontextmanager
    async def _session(**_k):
        yield _Session()

    async def _population(_session, _venue, *, now_mono):
        return units

    async def _no_write(*_a, **_k):
        raise AssertionError("nothing may be written")

    class _Service:
        async def close(self):
            pass

    calls = {"backoff": 0, "cursor": []}
    monkeypatch.setattr("app.tasks.base.get_task_session", _session)
    monkeypatch.setattr(v, "load_population", _population)
    monkeypatch.setattr(v, "_new_service", lambda _venue: _Service())
    monkeypatch.setattr(v, "_fetch_group", fetch)
    monkeypatch.setattr(v, "_write_group", _no_write)
    monkeypatch.setattr(v, "backoff_remaining", lambda _venue: 0.0)
    monkeypatch.setattr(v, "read_cursor", lambda _venue: None)
    monkeypatch.setattr(v, "write_cursor", lambda _venue, key: calls["cursor"].append(key))
    monkeypatch.setattr(v, "clear_backoff", lambda _venue: None)

    def _start(_venue):
        calls["backoff"] += 1
        return 30

    monkeypatch.setattr(v, "start_backoff", _start)
    return calls


@pytest.mark.asyncio
async def test_a_429_stops_the_venue_backs_it_off_and_writes_nothing(monkeypatch):
    async def _fetch(*_a, **_k):
        request = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets")
        raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))

    calls = _wire_pass(monkeypatch, units=[_unit("1", 3)], fetch=_fetch)
    import time

    stats = await v.poll_venue("kalshi", deadline=time.monotonic() + 20)
    assert stats["stopped"] == "rate_limited" and stats["backoff_started_s"] == 30
    assert calls["backoff"] == 1 and calls["cursor"] == [None]  # the cursor does not move


@pytest.mark.asyncio
async def test_a_venue_in_backoff_is_not_read(monkeypatch):
    async def _fetch(*_a, **_k):
        raise AssertionError("a backed-off venue is not read")

    _wire_pass(monkeypatch, units=[_unit("1", 3)], fetch=_fetch)
    monkeypatch.setattr(v, "backoff_remaining", lambda _venue: 42.0)
    stats = await v.poll_venue("kalshi", deadline=10**9)
    assert stats == {"errors": [], "unknown_outcomes": 0, "backoff_s": 42.0, "stopped": "backoff"}


@pytest.mark.asyncio
async def test_the_pass_starts_no_request_past_its_time_budget(monkeypatch):
    async def _fetch(*_a, **_k):
        raise AssertionError("no request after the budget")

    _wire_pass(monkeypatch, units=[_unit("1", 3)], fetch=_fetch)
    import time

    stats = await v.poll_venue("kalshi", deadline=time.monotonic() + v._MIN_REQUEST_S - 0.5)
    assert stats["stopped"] == "budget" and "units_done" not in stats


@pytest.mark.asyncio
async def test_one_venue_failing_never_takes_the_other_down(monkeypatch):
    async def _kalshi(venue, *, deadline):
        if venue == "kalshi":
            return {"stopped": "error", "errors": ["boom"]}
        return {"stopped": "done", "errors": []}

    monkeypatch.setattr(v, "poll_venue", _kalshi)
    summary = await v.poll_venue_prices({"kalshi", "polymarket"})
    assert summary["polymarket"]["stopped"] == "done"
    assert summary["terminal"] == "partial"
