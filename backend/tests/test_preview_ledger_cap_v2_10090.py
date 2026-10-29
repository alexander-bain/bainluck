"""#10090: the preview ledger's resident cap rises above 512 as a VERSIONED policy.

SHIP: busy live games in every tier get sub-second price previews instead of
waiting for the slower committed stamp; the ledger's total may exceed 512, so
"Other" leagues get far more slots without taking room from top leagues or
college.

Contract pinned here:

- every allocation has exactly one fingerprint: totals 1..512 stay ``v1`` (the
  default's bytes are unchanged, so the ready production authority keeps
  binding after the release), totals 513..1024 are ``v2``, 1025 is refused;
- the Lua cap is the fingerprint's: a v2 ledger admits exactly its total and
  refuses the next, and the producer passes its policy's cap (a v1 512 would
  refuse resident 513 with ``full``);
- a writer that predates v2 parses no v2 fingerprint: it refuses to claim, and
  every command it sends to a v2 ledger is ``policy_mismatch``.

Real Redis cases use the TSP-1 rig (private ``redis-server``); they skip without one.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest

from app.utils import blend_preview
from app.utils.preview_reservations import (
    DEFAULT_LIMITS,
    RESERVATIONS_ENV,
    ReservationPolicy,
)
from tests.test_blend_preview_ledger_tsp1_10090 import (  # noqa: F401
    NOW,
    SOURCES,
    Rig,
    _ev,
    _fresh_ops,
    _script,
    redis_kwargs,
)

#: The proposed 1024 split: T1 96/48 and T2 >= 128/64 (Alex item 35), Other the rest.
V2_SPLIT = (96, 48, 192, 128, 448, 112)
DEFAULT_FINGERPRINT = "v1-six-hour-ba82e47ee634aba7:192,64,128,64,48,16"
V2_PARSE = "'^(v[12])%-six%-hour%-%x+:(.*)$'"


def v1_only_script(script: str = blend_preview.LEDGER_SCRIPT) -> str:
    """The ledger as a writer that predates v2 runs it: v1 parse, cap 512."""
    assert script.count(V2_PARSE) == 1
    return script.replace(V2_PARSE, "'^(v1)%-six%-hour%-%x+:(.*)$'")


def _policy(limits):
    return ReservationPolicy(tuple(limits))


class TestVersionedPolicy:
    def test_the_default_keeps_its_exact_v1_fingerprint(self):
        policy = ReservationPolicy()
        assert policy.limits == DEFAULT_LIMITS
        assert (policy.version, policy.cap) == ("v1", 512)
        assert policy.fingerprint == DEFAULT_FINGERPRINT

    def test_today_s_512_resize_is_still_v1(self):
        policy = _policy((96, 48, 128, 64, 144, 32))
        assert (policy.version, policy.cap, policy.total) == ("v1", 512, 512)
        assert policy.fingerprint.startswith("v1-six-hour-ba82e47ee634aba7:")

    @pytest.mark.parametrize("limits, total", [
        ((97, 48, 128, 64, 144, 32), 513),
        (V2_SPLIT, 1024),
    ])
    def test_a_total_above_512_is_v2_at_cap_1024(self, limits, total):
        policy = _policy(limits)
        assert (policy.version, policy.cap, policy.total) == ("v2", 1024, total)
        assert policy.fingerprint == (
            "v2-six-hour-ba82e47ee634aba7:" + ",".join(map(str, limits)))

    def test_1025_is_refused_from_the_environment_too(self, monkeypatch):
        with pytest.raises(ValueError, match="1..1024"):
            _policy((97, 48, 192, 128, 448, 112))
        monkeypatch.setenv(RESERVATIONS_ENV, "97,48,192,128,448,112")
        with pytest.raises(ValueError):
            ReservationPolicy.configured()
        monkeypatch.setenv(RESERVATIONS_ENV, ",".join(map(str, V2_SPLIT)))
        assert ReservationPolicy.configured().cap == 1024

    def test_the_registry_bound_follows_the_policy(self):
        v2 = blend_preview.LedgerRegistry(sources=SOURCES, policy=_policy(V2_SPLIT))
        assert v2.max_events == 1024
        v1 = blend_preview.LedgerRegistry(sources=SOURCES, policy=ReservationPolicy())
        assert v1.max_events == 512
        small = blend_preview.LedgerRegistry(sources=SOURCES, policy=_policy((3, 1, 2, 1, 1, 1)))
        assert small.max_events == 9


def _event_in(bucket):
    event = _ev()
    event.sport_key = (("americanfootball_nfl", "basketball_wnba", None)[bucket // 2])
    if bucket % 2:
        event.status = "scheduled"
        event.commence_time = NOW + timedelta(hours=1)
    return event


@pytest.fixture
async def v2rig(redis_kwargs, monkeypatch):  # noqa: F811
    from redis.asyncio import Redis

    monkeypatch.setenv(RESERVATIONS_ENV, ",".join(map(str, V2_SPLIT)))
    client = Redis(**redis_kwargs)
    pubsub_client = Redis(**redis_kwargs)
    listener = pubsub_client.pubsub()
    await listener.psubscribe("tsp1:ev:*")
    await listener.get_message(timeout=0.2)
    r = Rig(client, listener, monkeypatch, False)
    r.use()
    await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
    r.k, r.p = r.registry(), r.registry()
    assert r.k.policy.cap == 1024
    await r.k.claim(r.call, "kalshi")
    await r.p.claim(r.call, "polymarket")
    try:
        yield r
    finally:
        await listener.aclose()
        await pubsub_client.aclose()
        await client.aclose()


async def _admit(rig, reg, source, event_id, bucket):
    ops = await _fresh_ops(rig, reg, source, event_id=event_id, event=_event_in(bucket))
    return await reg.prepare(ops, rig.call, rig.stats)


class TestV2LedgerOnRealRedis:
    async def test_holds_exactly_1024_residents_and_refuses_the_next_in_every_bucket(self, v2rig, caplog):
        rig = v2rig
        eid = 0
        for bucket, limit in enumerate(V2_SPLIT):
            for _ in range(limit):
                eid += 1
                reg, source = (rig.k, "kalshi") if eid % 2 else (rig.p, "polymarket")
                assert await _admit(rig, reg, source, eid, bucket), (bucket, eid)
                if eid == 513:
                    # Beyond v1's cap: the producer passed its policy's 1024.
                    assert await rig.hget("nevents") == "513"
        assert eid == 1024
        assert await rig.hget("nevents") == "1024"
        assert await rig.hget("reservation_policy") == rig.k.policy.fingerprint
        for bucket, limit in enumerate(V2_SPLIT):
            assert await rig.hget(f"r:count:{bucket}") == str(limit)
            eid += 1
            assert await _admit(rig, rig.k, "kalshi", eid, bucket) == []
        assert await rig.hget("nevents") == "1024"
        # At capacity the bounded candidate read offers all 1024 ids, never more.
        _, ids = await rig.p.read_ticket(rig.call, "polymarket", include_candidates=True)
        assert sorted(ids) == list(range(1, 1025))
        # The capacity receipt validates against the policy's cap, not v1's 512.
        with caplog.at_level(logging.INFO, logger=blend_preview.logger.name):
            await rig.k.capacity_ticket(rig.call, "kalshi", maintenance_receipt=True)
        receipts = [json.loads(r.getMessage().split("receipt ", 1)[1]) for r in caplog.records
                    if "reservation receipt" in r.getMessage()]
        assert [(r["status"], r["policy_fingerprint"]) for r in receipts] == [
            ("ready", rig.k.policy.fingerprint)]
        assert sum(receipts[0]["shared"]["counts"].values()) == 1024

    async def test_a_writer_that_predates_v2_refuses_a_v2_ledger(self, v2rig):
        rig = v2rig
        assert await _admit(rig, rig.k, "kalshi", 1, 4)
        rig.monkeypatch.setattr(blend_preview, "LEDGER_SCRIPT", v1_only_script(_script()))
        old = blend_preview.LedgerRegistry(sources=SOURCES, policy=_policy(V2_SPLIT))
        with pytest.raises(RuntimeError, match="policy_mismatch"):
            await old.claim(rig.call, "kalshi")
        # The already-claimed owner, now running old bytes, is refused too.
        assert await _admit(rig, rig.k, "kalshi", 2, 4) == []
        keys = blend_preview.ledger_keys()
        reply = await rig.client.eval(
            blend_preview.LEDGER_SCRIPT, len(keys), *keys,
            rig.k.policy.fingerprint, "capacity_ticket", "kalshi",
            str(rig.k.claim_of("kalshi")), "", "kalshi polymarket")
        assert reply == [b"policy_mismatch"]
        assert await rig.hget("nevents") == "1"
        assert await rig.hget("e:2:gen") is None


@pytest.mark.parametrize("fingerprint", [
    "v2-six-hour-ba82e47ee634aba7:192,64,128,64,48,16",   # v2 at <= 512: not canonical
    "v2-six-hour-ba82e47ee634aba7:97,48,192,128,448,112",  # 1025
    "v1-six-hour-ba82e47ee634aba7:96,48,192,128,448,112",  # v1 above 512
    "v3-six-hour-ba82e47ee634aba7:96,48,192,128,448,112",
])
async def test_the_script_refuses_a_fingerprint_outside_its_version_s_range(redis_kwargs, fingerprint):  # noqa: F811
    from redis.asyncio import Redis

    client = Redis(**redis_kwargs)
    try:
        await client.set(blend_preview.FENCE_EPOCH_KEY, "41")
        keys = blend_preview.ledger_keys()
        reply = await client.eval(blend_preview.LEDGER_SCRIPT, len(keys), *keys,
                                  fingerprint, "claim", "kalshi")
        assert reply == [b"policy_mismatch"]
        assert await client.exists(keys[0]) == 0
    finally:
        await client.aclose()


class TestCapacityOrderOnRealRedis:
    async def test_capacity_candidates_are_clockless_first_then_oldest_context_then_numeric_id(self, v2rig):
        # Each context clock is read once before the sort; the order is unchanged.
        rig = v2rig
        offsets = {5: 3, 9: 1, 10: 1, 1: 2, 7: 4}
        for eid, seconds in offsets.items():
            event = _event_in(4)
            event.preview_context_at = NOW + timedelta(seconds=seconds)
            assert await rig.k.prepare(
                await _fresh_ops(rig, rig.k, "kalshi", event_id=eid, event=event), rig.call, rig.stats)
        await rig.client.hdel(blend_preview.LEDGER_KEY, "e:7:r_clock")
        _, candidates, _, _ = await rig.k.capacity_ticket(rig.call, "kalshi")
        assert candidates == [7, 9, 10, 1, 5]
