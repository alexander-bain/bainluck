"""#10090 Fix A follow-up: a live leg Gamma could not token gives up its seat.

Measured 2026-10-30 on v5984: "395 / 386 live-leg condition ids exceed the
priority cap of 200". 191 of the 200 asked were still untokened a pass later, so
the same lowest-sorting 200 held every seat and the rest waited for a rotation.
An id asked and left untokened now rests outside the seats for
``PRIORITY_MISS_SECONDS``; it keeps competing in the rotating window.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.sql.dml import Update

import app.tasks.polymarket_token_topup as topup
import app.tasks.redis_state as redis_state

LIVE_MARKET = 1
PROP_MARKET = 2
#: 250 live-leg condition ids: more than the 200 seats.
FLOOD = [(LIVE_MARKET, 5000 + i, f"0xe{i:063d}") for i in range(250)]
FLOOD_IDS = [cid for _m, _o, cid in FLOOD]
#: 400 untokened prop ids sorting ahead of every live leg.
PROPS = [(PROP_MARKET, 1000 + i, f"0x0{i:063d}") for i in range(400)]


class Gamma:
    def __init__(self, missing=(), fail=False):
        self.asked: list[list[str]] = []
        # An empty 200 for these ids: how a closed sub-market answers.
        self.missing = set(missing)
        self.fail = fail

    async def get_markets_by_conditions(self, ids, **_kw):
        self.asked.append(list(ids))
        if self.fail:
            raise RuntimeError("429 Too Many Requests")
        return [
            SimpleNamespace(
                condition_id=cid,
                clob_token_ids=[cid + "-yes", cid + "-no"],
                outcomes=["Yes", "No"],
            )
            for cid in ids
            if cid not in self.missing
        ]

    async def close(self):
        pass


class Session:
    """Nothing stored, nothing stale; ``names`` answers the outcome-name read."""

    def __init__(self, names=()):
        self.reads = 0
        self.names = list(names)

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            return SimpleNamespace(all=lambda: [])
        self.reads += 1
        rows = self.names if self.reads == 2 else []
        return SimpleNamespace(all=lambda: rows)


class FakeRedis:
    """The sorted-set surface the resting memory uses, scored like Redis."""

    def __init__(self):
        self.zset: dict[str, float] = {}
        self.expiry = None
        self.reads = 0

    def zrangebyscore(self, key, lo, hi):
        assert key == topup.PRIORITY_MISS_KEY and hi == "+inf"
        self.reads += 1
        return [m.encode() for m, score in self.zset.items() if score >= lo]

    def pipeline(self):
        return Pipe(self)


class Pipe:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def zremrangebyscore(self, key, lo, hi):
        assert key == topup.PRIORITY_MISS_KEY and lo == "-inf"
        self.ops.append(
            lambda: [
                self.redis.zset.pop(m)
                for m, s in list(self.redis.zset.items())
                if s <= hi
            ]
        )

    def zadd(self, key, mapping):
        assert key == topup.PRIORITY_MISS_KEY
        self.ops.append(lambda: self.redis.zset.update(mapping))

    def expire(self, key, seconds):
        assert key == topup.PRIORITY_MISS_KEY
        self.ops.append(lambda: setattr(self.redis, "expiry", seconds))

    def execute(self):
        for op in self.ops:
            op()


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: fake)
    store = {"value": None}

    async def load():
        return store["value"]

    async def save(value):
        if value:
            store["value"] = value

    monkeypatch.setattr(topup, "load_topup_cursor", load)
    monkeypatch.setattr(topup, "save_topup_cursor", save)
    return fake


async def run(gamma, targets=PROPS + FLOOD, session=None):
    return await topup.topup_outcome_clob_tokens(
        session or Session(),
        targets,
        service=gamma,
        max_priority=200,
        priority_market_ids={LIVE_MARKET},
    )


async def test_untokened_live_legs_give_their_seats_to_the_rest(redis):
    gamma = Gamma(missing=FLOOD_IDS[:200])
    await run(gamma)
    await run(gamma)
    first, second = gamma.asked
    assert first[:200] == FLOOD_IDS[:200]
    # The 50 that waited behind the cap lead the next ask, in the first batch.
    assert second[:50] == FLOOD_IDS[200:]
    assert set(FLOOD_IDS[:200]).isdisjoint(second[:50])


async def test_a_resting_leg_still_rides_the_rotating_window(redis):
    gamma = Gamma(missing=FLOOD_IDS[:200])
    await run(gamma)
    await run(gamma)
    # Window after props[299]: the last 100 props, then the 200 resting legs.
    assert gamma.asked[1][50:] == [c for _m, _o, c in PROPS[300:]] + FLOOD_IDS[:200]


async def test_a_leg_the_rotation_still_cannot_fill_rests_again(redis):
    gamma = Gamma(missing=FLOOD_IDS[:200])
    await run(gamma)
    first_rest = dict(redis.zset)
    assert set(first_rest) == set(FLOOD_IDS[:200])
    for cid in first_rest:
        redis.zset[cid] -= 60
    await run(gamma)
    # Re-asked in the window and still untokened: the rest restarts.
    assert all(
        redis.zset[cid] == pytest.approx(first_rest[cid], abs=5) for cid in first_rest
    )


async def test_a_rest_ends_after_priority_miss_seconds(redis):
    gamma = Gamma(missing=FLOOD_IDS[:200])
    await run(gamma)
    for cid in list(redis.zset):
        redis.zset[cid] -= topup.PRIORITY_MISS_SECONDS + 1
    await run(gamma)
    assert gamma.asked[1][:200] == FLOOD_IDS[:200]


async def test_only_untokened_live_ids_rest(redis):
    # A rest that ended an hour ago and is not re-earned is pruned on write.
    redis.zset["0x" + "d" * 64] = 0.0
    gamma = Gamma(missing={FLOOD_IDS[3], PROPS[0][2]})
    await run(gamma, targets=PROPS + FLOOD[:10])
    assert set(redis.zset) == {FLOOD_IDS[3]}
    assert redis.expiry == topup.PRIORITY_MISS_SECONDS


async def test_an_id_with_one_row_still_untokened_rests(redis):
    """One condition id, two of our rows; Gamma's answer tokens only one."""
    cid = "0x" + "a" * 64

    class H2H(Gamma):
        async def get_markets_by_conditions(self, ids, **_kw):
            self.asked.append(list(ids))
            return [
                SimpleNamespace(
                    condition_id=cid,
                    clob_token_ids=["tok-tigers", "tok-jays"],
                    outcomes=["Detroit Tigers", "Toronto Blue Jays"],
                )
            ]

    filled = await run(
        H2H(),
        targets=[(LIVE_MARKET, 1, cid + "_yes"), (LIVE_MARKET, 2, cid + "_no")],
        session=Session(names=[(1, "Detroit Tigers"), (2, "Nobody")]),
    )
    assert filled == {1: (LIVE_MARKET, "tok-tigers")}
    assert set(redis.zset) == {cid}


async def test_a_gamma_outage_rests_nothing(redis):
    with pytest.raises(RuntimeError):
        await run(Gamma(fail=True))
    assert redis.zset == {}


async def test_a_redis_fault_fails_open_to_every_live_leg_competing(monkeypatch, redis):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_state, "get_redis_client", boom)
    gamma = Gamma(missing=FLOOD_IDS[:200])
    for _ in range(2):
        filled = await run(gamma)
    # Fix A as shipped: the same 200 seats, and the pass still returns tokens.
    assert gamma.asked[1][:200] == FLOOD_IDS[:200]
    assert len(filled) == 300


async def test_no_live_legs_reads_no_memory(redis):
    gamma = Gamma()
    await topup.topup_outcome_clob_tokens(Session(), PROPS, service=gamma)
    assert redis.reads == 0


async def test_the_rest_lasts_one_hour():
    assert topup.PRIORITY_MISS_SECONDS == 3600
