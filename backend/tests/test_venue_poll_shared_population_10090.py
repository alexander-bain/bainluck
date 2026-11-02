"""#10090 (11/01 17:32-17:35Z): every poll pass re-ran the population read — 6-12 s
of a 24 s pass, `population_cached` False on each — because the prefork children
each held their own copy and the 200 MB child recycle dropped it. The population
is now shared through Redis for `POPULATION_TTL_S`, keyed by the statement; and
the props arm reads the window's events first (it planned from futures_markets
at ~3 s)."""

import time

import pytest

from app.tasks import polymarket_ws
from app.tasks import venue_poll_30s as v


class _Redis:
    def __init__(self):
        self.kv = {}

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, ex=None):
        self.kv[key] = value


class _Session:
    def __init__(self, rows):
        self.rows, self.reads = rows, 0

    async def execute(self, *_a, **_k):
        self.reads += 1
        rows = self.rows

        class _R:
            def fetchall(self):
                return rows
        return _R()


@pytest.fixture
def rc(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(v, "_redis", lambda: fake)
    monkeypatch.setattr(v, "_POPULATION", {})
    monkeypatch.setattr(v, "backoff_remaining", lambda _n: 0.0)
    monkeypatch.setattr(v, "clear_backoff", lambda _n: None)
    monkeypatch.setattr(v, "shown_market_ids", lambda: [])
    monkeypatch.setattr(v, "population_binds", lambda _ids: {})
    return fake


ROWS = [(1, "900", 11, "0xa"), (1, "900", 12, "0xa_side1"), (2, "901", 21, "0xb")]


async def test_a_second_process_reuses_the_first_ones_read(rc, monkeypatch):
    first = _Session(ROWS)
    a = await v.load_population(first, "polymarket", now_mono=time.monotonic(), stats={})
    monkeypatch.setattr(v, "_POPULATION", {})  # another prefork child
    second = _Session([])
    stats = {}
    b = await v.load_population(second, "polymarket", now_mono=time.monotonic(), stats=stats)
    assert first.reads == 1 and second.reads == 0
    assert stats["population_cached"] == "shared"
    assert [(u.key, u.legs) for u in a] == [(u.key, u.legs) for u in b]


async def test_an_expired_or_other_statements_population_is_never_reused(rc, monkeypatch):
    await v.load_population(_Session(ROWS), "polymarket", now_mono=time.monotonic(), stats={})
    (key,) = rc.kv
    monkeypatch.setattr(v, "_POPULATION", {})
    monkeypatch.setattr(v, "polymarket_population_sql", lambda _arm: "SELECT 'another scope'")
    other = _Session([])
    await v.load_population(other, "polymarket", now_mono=time.monotonic(), stats={})
    assert other.reads == 1, "a different statement reads its own population"

    monkeypatch.setattr(v, "_POPULATION", {})
    monkeypatch.setattr(time, "time", lambda: 10 ** 10)  # far past the TTL
    late = _Session([])
    assert v._read_shared_population("polymarket", "SELECT 'another scope'") is None


async def test_unreadable_redis_reads_the_database(rc, monkeypatch):
    def boom():
        raise ConnectionError("down")
    monkeypatch.setattr(v, "_redis", boom)
    s = _Session(ROWS)
    units = await v.load_population(s, "polymarket", now_mono=time.monotonic(), stats={})
    assert s.reads == 1 and len(units) == 2


def test_the_props_arms_event_superset_covers_the_sockets_window(monkeypatch):
    assert v.SLATE_SUPERSET_PAST_HOURS >= polymarket_ws.SLATE_MAX_AGE_HOURS
    assert v.SLATE_SUPERSET_AHEAD_HOURS >= polymarket_ws.PM_WS_UPCOMING_HOURS_MAX
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    sql = v.polymarket_population_sql(False)
    assert "props_events AS MATERIALIZED" in sql and "FROM props_events pe" in sql
