"""Focused real-Redis namespace controls; not a hosted failover proof."""

from dataclasses import replace
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.services.dnpl_authority import Authority
from app.utils.blend_preview import LEDGER_SCRIPT
from app.utils.dnpl_redis_authority import (
    GUARDED_LEDGER_SCRIPT,
    INITIALIZE_SCRIPT,
    INITIAL_READBACK_SCRIPT,
    guard_token,
    guarded_ledger_script,
    namespace_keys,
)
from app.utils.preview_reservations import ReservationPolicy
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def rig(redis_kwargs):  # noqa: F811 - imported pytest fixture binding
    client = Redis(**redis_kwargs, decode_responses=True)
    server = await client.info("server")
    repl = await client.info("replication")
    authority = Authority(
        3,
        1,
        uuid4(),
        uuid4(),
        "preparing",
        server["run_id"],
        repl["master_replid"],
        ReservationPolicy().fingerprint,
    )
    try:
        yield client, authority
    finally:
        await client.aclose()


async def initial(client, authority, script=INITIALIZE_SCRIPT):
    return await client.eval(
        script,
        6,
        *namespace_keys(authority),
        guard_token(authority),
        authority.redis_run_id,
        authority.redis_master_replid
    )


async def call(
    client, authority, *argv, owner="0", source="kalshi", script=GUARDED_LEDGER_SCRIPT
):
    return await client.eval(
        script,
        6,
        *namespace_keys(authority),
        guard_token(authority),
        authority.redis_run_id,
        authority.redis_master_replid,
        source,
        owner,
        authority.policy_fingerprint,
        *argv
    )


async def test_initialization_is_exact_and_not_replayable(rig):
    client, a = rig
    assert await initial(client, a) == ["initialized"]
    assert await initial(client, a, INITIAL_READBACK_SCRIPT) == ["initial_verified"]
    assert await initial(client, a) == ["exists"]
    claim = await call(client, a, "claim", "kalshi")
    assert claim == ["ok", "1"]
    assert await initial(client, a, INITIAL_READBACK_SCRIPT) == ["not_initial"]
    assert await call(
        client, a, "read_ticket", "kalshi", "1", "", "kalshi polymarket", "0", owner="1"
    ) == ["ok", "0"]


@pytest.mark.parametrize("field", ["redis_run_id", "redis_master_replid"])
async def test_wrong_identity_refuses_initialization_without_writes(rig, field):
    client, a = rig
    wrong = replace(a, **{field: "0" * 40})
    assert await initial(client, wrong) == ["identity_changed"]
    assert await client.dbsize() == 0


@pytest.mark.parametrize("index", [0, 1, 2, 5])
async def test_lost_required_key_cannot_be_reinitialized_or_claimed(rig, index):
    client, a = rig
    assert await initial(client, a) == ["initialized"]
    await client.delete(namespace_keys(a)[index])
    before = {k: await client.dump(k) for k in namespace_keys(a)}
    assert (await call(client, a, "claim", "kalshi"))[0] in ("lost", "guard_refused")
    assert await initial(client, a) == ["exists"]
    assert before == {k: await client.dump(k) for k in namespace_keys(a)}


async def test_invalid_normal_operation_does_not_poison_clean_guard(rig):
    client, a = rig
    await initial(client, a)
    assert await call(client, a, "claim", "kalshi") == ["ok", "1"]
    # Valid outer source, stale source owner: refuse before any semantic write.
    assert await call(
        client, a, "read_ticket", "kalshi", "0", "", "kalshi polymarket", "0"
    ) == ["fenced"]
    assert await client.get(namespace_keys(a)[5]) == "clean:" + guard_token(a)
    assert await call(client, a, "claim", "polymarket", source="polymarket") == [
        "ok",
        "2",
    ]


async def test_early_revoke_requires_current_owner(rig):
    client, a = rig
    await initial(client, a)
    assert await call(client, a, "claim", "kalshi") == ["ok", "1"]
    assert await call(client, a, "claim", "kalshi") == ["ok", "2"]
    assert await call(client, a, "revoke", "test-channel", "{}", owner="1") == [
        "fenced"
    ]
    assert await call(client, a, "revoke", "test-channel", "{}", owner="2") == [
        "published"
    ]
    assert await client.get(namespace_keys(a)[5]) == "clean:" + guard_token(a)


async def test_wrong_policy_cannot_claim_empty_namespace(rig):
    client, a = rig
    await initial(client, a)
    keys = namespace_keys(a)
    result = await client.eval(
        GUARDED_LEDGER_SCRIPT,
        6,
        *keys,
        guard_token(a),
        a.redis_run_id,
        a.redis_master_replid,
        "kalshi",
        "0",
        "wrong-policy",
        "claim",
        "kalshi"
    )
    assert result == ["policy_mismatch"]
    assert await client.hget(keys[0], "epoch") == "0"


async def test_error_after_first_mutation_leaves_dirty_and_refuses_retry(rig):
    client, a = rig
    await initial(client, a)
    marker = "  redis.call('HSET', L, 'policy_owner:' .. src, decimal(n))"
    assert LEDGER_SCRIPT.count(marker) == 1
    fault = LEDGER_SCRIPT.replace(marker, marker + "\n  error('injected after write')")
    with pytest.raises(ResponseError, match="injected after write"):
        await call(client, a, "claim", "kalshi", script=guarded_ledger_script(fault))
    assert await client.hget(namespace_keys(a)[0], "policy_owner:kalshi") == "1"
    assert await client.get(namespace_keys(a)[5]) == "dirty:" + guard_token(a)
    assert await call(client, a, "claim", "kalshi") == ["guard_refused"]


async def test_initialization_partial_error_is_not_a_clean_namespace(rig):
    client, a = rig
    marker = "redis.call('SET', KEYS[2], '1')"
    assert INITIALIZE_SCRIPT.count(marker) == 1
    fault = INITIALIZE_SCRIPT.replace(
        marker, marker + "\nerror('injected init failure')"
    )
    with pytest.raises(ResponseError, match="injected init failure"):
        await initial(client, a, fault)
    assert await client.get(namespace_keys(a)[5]) == "initializing:" + guard_token(a)
    assert await call(client, a, "claim", "kalshi") == ["guard_refused"]
    assert await initial(client, a) == ["exists"]


async def test_new_namespace_does_not_reuse_old_state_and_old_token_refuses(rig):
    client, a = rig
    await initial(client, a)
    await call(client, a, "claim", "kalshi")
    b = replace(a, incarnation=2, namespace=uuid4(), operation_id=uuid4())
    await initial(client, b)
    assert await call(client, b, "claim", "kalshi") == ["ok", "1"]
    result = await client.eval(
        GUARDED_LEDGER_SCRIPT,
        6,
        *namespace_keys(b),
        guard_token(a),
        a.redis_run_id,
        a.redis_master_replid,
        "kalshi",
        "1",
        a.policy_fingerprint,
        "revoke",
        "x",
        "{}"
    )
    assert result == ["guard_refused"]
    # Old namespace may still exist: PostgreSQL/fanout must refuse its output.
    # The Redis wrapper alone is deliberately not claimed as that authority.
    assert await client.hget(namespace_keys(a)[0], "epoch") == "1"


async def claimed(rig):
    client, a = rig
    assert await initial(client, a) == ["initialized"]
    assert await call(client, a, "claim", "kalshi") == ["ok", "1"]
    return client, a


async def assert_clean_and_next_operation(client, a):
    assert await client.get(namespace_keys(a)[5]) == "clean:" + guard_token(a)
    assert (await call(client, a, "claim", "kalshi"))[0] == "ok"


@pytest.mark.parametrize(
    "op,args",
    [
        ("terminal", ("10", "512", "0")),
        ("retire", ("10", "0", "11")),
        ("retire_missing", ("0",)),
    ],
)
async def test_absent_retirement_advances_barrier_without_poisoning(rig, op, args):
    client, a = await claimed(rig)
    assert await call(
        client, a, op, "kalshi", "1", "42", "kalshi", *args, owner="1"
    ) == ["none"]
    assert await client.hget(namespace_keys(a)[0], "retired") == "1"
    # The completed retirement must still invalidate an already-prepared open.
    assert (await propose(client, a, ticket="0"))[0] == "read_required"
    await assert_clean_and_next_operation(client, a)


async def propose(client, a, *, chain="1", bucket="0", clock="1", ticket="0"):
    return await call(
        client,
        a,
        "propose",
        "kalshi",
        "1",
        "42",
        "kalshi",
        "open",
        chain,
        chain,
        "10",
        "60000",
        "512",
        '{"value":0.6}',
        "10",
        '{"base":10}',
        ticket,
        bucket,
        clock,
        owner="1",
    )


@pytest.mark.parametrize(
    "mode,expected", [("settle", "unchanged"), ("expire", "current")]
)
async def test_base_only_settle_remains_clean(rig, mode, expected):
    client, a = await claimed(rig)
    assert (await propose(client, a))[0] == "ok"
    assert (
        await call(
            client,
            a,
            "settle",
            "kalshi",
            "1",
            "42",
            "kalshi",
            "settle",
            "1",
            "10",
            '{"base":10}',
            owner="1",
        )
    )[0] == "ok"
    assert await client.hget(namespace_keys(a)[0], "e:42:m:kalshi") is None
    result = await call(
        client,
        a,
        "settle",
        "kalshi",
        "1",
        "42",
        "kalshi",
        mode,
        "1",
        "11",
        '{"base":11}',
        "1",
        owner="1",
    )
    assert result[0] == expected
    assert await client.hget(namespace_keys(a)[0], "e:42:base_rev") == "11"
    assert await client.hget(namespace_keys(a)[0], "e:42:base") == '{"base":11}'
    await assert_clean_and_next_operation(client, a)


async def test_migration_debt_preserves_active_preview_and_clean_guard(rig):
    client, a = await claimed(rig)
    assert (await propose(client, a))[0] == "ok"
    key = namespace_keys(a)[0]
    held = {
        field: await client.hget(key, "e:42:" + field)
        for field in ("gen", "seq", "m:kalshi", "p:kalshi")
    }
    assert await propose(client, a, chain="2", bucket="6", clock="2") == [
        "migration_debt"
    ]
    assert await client.hget(key, "e:42:r_target") == "6"
    assert await client.hget(key, "e:42:r_clock") == "2"
    assert held == {field: await client.hget(key, "e:42:" + field) for field in held}
    await assert_clean_and_next_operation(client, a)


@pytest.mark.parametrize("status", ["none", "unchanged", "migration_debt", "published"])
async def test_completion_status_from_wrong_operation_stays_dirty(rig, status):
    client, a = rig
    await initial(client, a)
    marker = "  redis.call('HSET', L, 'policy_owner:' .. src, decimal(n))"
    assert LEDGER_SCRIPT.count(marker) == 1
    fault = LEDGER_SCRIPT.replace(
        marker, marker + "\n  do return {'" + status + "'} end"
    )
    assert await call(
        client, a, "claim", "kalshi", script=guarded_ledger_script(fault)
    ) == ["dirty_result"]
    assert await client.get(namespace_keys(a)[5]) == "dirty:" + guard_token(a)
    assert await call(client, a, "claim", "kalshi") == ["guard_refused"]
