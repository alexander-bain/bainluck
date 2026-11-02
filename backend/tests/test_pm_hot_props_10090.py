"""#10090 — the hottest Polymarket props stay live (Alex 2026-11-01 ~9:20 AM PT:
"30 seconds for almost all props, but live for the props with the highest very
recent trading volume, to the extent that we can do that without burdening the
cpu"). The poll records the props it saw move; the open arm seeds the top
`PM_HOT_PROPS_MAX` (moved in at least `PM_HOT_PROPS_MIN_MOVES` passes of the last
ten minutes) exactly as markets a reader holds."""

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import pm_hot_props as hot


class _Pipe:
    def __init__(self, store):
        self.store, self.ops = store, []

    def zincrby(self, key, amount, member):
        self.ops.append(("zincrby", key, amount, member))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    def zrange(self, key, start, end, withscores=False):
        self.ops.append(("zrange", key))

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "zincrby":
                bucket = self.store.setdefault(op[1], {})
                bucket[op[3]] = bucket.get(op[3], 0) + op[2]
                out.append(bucket[op[3]])
            elif op[0] == "zrange":
                out.append([(str(m).encode(), float(s))
                            for m, s in self.store.get(op[1], {}).items()])
            else:
                out.append(True)
        self.ops = []
        return out


class _Redis:
    def __init__(self):
        self.store = {}

    def pipeline(self):
        return _Pipe(self.store)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "1")
    monkeypatch.delenv("PM_HOT_PROPS_MAX", raising=False)
    monkeypatch.delenv("PM_HOT_PROPS_MIN_MOVES", raising=False)
    rc = _Redis()
    monkeypatch.setattr(hot, "_redis", lambda: rc)
    return rc


def _heat(rc, now, counts_by_minute_ago):
    for ago, counts in counts_by_minute_ago.items():
        bucket = rc.store.setdefault(hot._bucket(int(now // 60) - ago), {})
        for mid, n in counts.items():
            bucket[mid] = n


def test_hot_is_the_top_n_with_enough_moves_in_the_last_ten_minutes(on, monkeypatch):
    now = 1_800_000_000.0
    _heat(on, now, {0: {1: 2, 2: 1, 3: 9}, 4: {1: 2, 2: 1}, 9: {4: 5}, 10: {5: 50}})
    # 1: 4 moves, 2: 2 (below 3), 3: 9, 4: 5, 5: outside the window
    assert hot.hot_market_ids(now=now) == {1, 3, 4}
    monkeypatch.setenv("PM_HOT_PROPS_MAX", "2")
    assert hot.hot_market_ids(now=now) == {3, 4}
    monkeypatch.setenv("PM_HOT_PROPS_MIN_MOVES", "6")
    assert hot.hot_market_ids(now=now) == {3}


@pytest.mark.parametrize("env", [{"PM_WS_PROPS_TO_POLL": "0"}, {"PM_HOT_PROPS_MAX": "0"}])
def test_off_means_no_hot_props(on, monkeypatch, env):
    now = 1_800_000_000.0
    _heat(on, now, {0: {1: 10}})
    for k, val in env.items():
        monkeypatch.setenv(k, val)
    assert hot.hot_market_ids(now=now) == frozenset()


def test_unreadable_heat_is_empty_never_an_error(on, monkeypatch):
    def boom():
        raise ConnectionError("redis down")
    monkeypatch.setattr(hot, "_redis", boom)
    assert hot.hot_market_ids(now=1_800_000_000.0) == frozenset()


class _Session:
    def __init__(self, owned):
        self.owned, self.stmts, self.commits = owned, [], 0

    async def execute(self, stmt):
        self.stmts.append(stmt)
        owned = self.owned

        class _R:
            def all(self):
                return [(m,) for m in owned]
        return _R()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


async def test_only_the_props_arms_markets_are_counted(on):
    now = 1_800_000_000.0
    session = _Session(owned=[11, 12])
    assert await hot.record_moved(session, [11, 12, 99], now=now) == 2
    assert on.store[hot._bucket(int(now // 60))] == {11: 1, 12: 1}
    await hot.record_moved(session, [11], now=now)
    assert on.store[hot._bucket(int(now // 60))][11] == 2


async def test_recording_off_reads_nothing(on, monkeypatch):
    monkeypatch.setenv("PM_WS_PROPS_TO_POLL", "0")
    session = _Session(owned=[11])
    assert await hot.record_moved(session, [11]) == 0 and session.stmts == []


def test_the_props_arm_is_the_sockets_window_and_the_venue_refusal():
    sql = str(hot.props_arm_stmt([3, 1]).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "events.status = 'live'" in sql and "venue_type" in sql
    assert "futures_markets.source = 'polymarket'" in sql and "IN (1, 3)" in sql
