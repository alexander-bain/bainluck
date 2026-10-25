"""Real existing PG + Unix-socket Redis lab; explicit recovery, no production."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.services import dnpl_activation as activation
from app.services.dnpl_authority import AuthorityConflict, preparing_candidate
from app.utils.dnpl_redis_authority import namespace_keys
from app.utils.preview_reservations import ReservationPolicy
from tests.integration.test_dnpl_authority_10090_pg import DB_URL, rig  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.fixture
async def recovery(rig, redis_kwargs):  # noqa: F811
    client = Redis(**redis_kwargs, decode_responses=True)
    server = await client.info("server")
    repl = await client.info("replication")

    async def prepare():
        old = await rig.store.read()
        candidate = preparing_candidate(
            old,
            namespace=uuid4(),
            operation_id=uuid4(),
            redis_run_id=server["run_id"],
            redis_master_replid=repl["master_replid"],
            policy_fingerprint=ReservationPolicy().fingerprint,
        )
        return await rig.store.prepare(old, candidate)

    try:
        yield SimpleNamespace(
            client=client,
            store=rig.store,
            prepare=prepare,
            controller=activation.ActivationController(rig.store, client),
        )
    finally:
        await client.aclose()


async def wire(r, script, authority, *, predecessor=None, bootstrap=False):
    if script == activation.ARM_SCRIPT:
        keys = (activation.ADMISSION_KEY,)
    else:
        keys = (*namespace_keys(predecessor or authority), activation.ADMISSION_KEY)
    return await activation.eval_once(
        r.client,
        script,
        keys,
        (*activation.arguments(authority), "1" if bootstrap else "0"),
    )


async def test_actual_controller_recovers_and_keeps_namespace_count_bounded(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    ready = await r.controller.ready(first)
    assert ready.state == "ready"
    assert await r.controller.read_ready(first)
    for _ in range(5):
        current = await r.prepare()
        await r.controller.arm(current)
        await r.controller.initialize(current)
        # Two namespaces, four keys initially in each, one root fence.
        assert await r.client.dbsize() == 9
        await r.controller.retire(current)
        assert await r.client.dbsize() == 5
        assert await r.store.read_retirement() is None
        ready = await r.controller.ready(current)
    assert ready.incarnation == 6
    # A late old init or ordinary old arm cannot restore a cleaned namespace.
    assert await wire(r, activation.INITIALIZE_ONCE_SCRIPT, first) == ["admission_lost"]
    assert await wire(r, activation.ARM_SCRIPT, first) == ["superseded"]
    assert await r.client.exists(*namespace_keys(first)) == 0


async def test_admission_eviction_never_allows_delayed_arm_to_recreate(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    second = await r.prepare()
    await r.controller.arm(second)
    await r.controller.retire(second)
    await r.client.delete(activation.ADMISSION_KEY)
    # Old ordinary arms cannot recreate missing root; bootstrap was one-shot
    # and already executed before successor arm/cleanup could have succeeded.
    assert await wire(r, activation.ARM_SCRIPT, second) == ["admission_lost"]
    with pytest.raises(activation.ActivationRefused, match="admission_lost"):
        await r.controller.initialize(second)
    assert await r.client.exists(*namespace_keys(first), *namespace_keys(second)) == 0
    with pytest.raises(AuthorityConflict):
        await r.controller.arm(first)
    with pytest.raises(AuthorityConflict):
        await r.controller.arm(second)
    third = await r.prepare()
    with pytest.raises(activation.ActivationRefused, match="admission_lost"):
        await r.controller.arm(third)
    assert (await r.store.read()).state == "preparing"


async def test_delayed_arm_and_init_refuse_after_newer_cleanup(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    # Simulate old init sent but delayed at server; durable permission consumed.
    await r.store.take_activation_step(first, 2)
    second = await r.prepare()
    await r.controller.arm(second)
    await r.controller.retire(second)
    assert await wire(r, activation.INITIALIZE_ONCE_SCRIPT, first) == ["admission_lost"]
    assert await wire(r, activation.ARM_SCRIPT, first) == ["superseded"]
    await r.controller.initialize(second)
    assert (await r.controller.ready(second)).incarnation == 2
    assert await r.client.exists(*namespace_keys(first)) == 0


async def test_lost_initializer_reply_is_read_back_without_resend(
    recovery, monkeypatch
):
    r = recovery
    current = await r.prepare()
    await r.controller.arm(current)
    original = activation.eval_once
    sent = []

    async def lose_reply(*args):
        result = await original(*args)
        sent.append(args[1])
        if args[1] == activation.INITIALIZE_ONCE_SCRIPT:
            raise ConnectionError("initializer reply lost after successful write")
        return result

    monkeypatch.setattr(activation, "eval_once", lose_reply)
    with pytest.raises(ConnectionError):
        await r.controller.initialize(current)
    with pytest.raises(AuthorityConflict):
        await r.controller.initialize(current)
    ready = await r.controller.ready(current)
    assert ready.state == "ready"
    assert sent.count(activation.INITIALIZE_ONCE_SCRIPT) == 1


async def test_partial_initializer_consumes_send_and_keeps_preparing(recovery):
    r = recovery
    current = await r.prepare()
    await r.controller.arm(current)
    await r.store.take_activation_step(current, 2)
    fault = activation.INITIALIZE_ONCE_SCRIPT.replace(
        "redis.call('SET', KEYS[2], '1')",
        "error('injected init failure')\nredis.call('SET', KEYS[2], '1')",
    )
    with pytest.raises(ResponseError, match="injected init failure"):
        await wire(r, fault, current)
    assert await wire(r, activation.INITIALIZE_ONCE_SCRIPT, current) == [
        "send_consumed"
    ]
    with pytest.raises(activation.ActivationRefused, match="not_initial"):
        await r.controller.ready(current)
    assert await r.store.read() == current
    successor = await r.prepare()
    await r.controller.arm(successor)
    await r.controller.retire(successor)
    await r.controller.initialize(successor)
    assert (await r.controller.ready(successor)).incarnation == 2
    assert await r.client.exists(*namespace_keys(current)) == 0


async def test_identity_or_newer_authority_prevents_cleanup_ack(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    current = await r.prepare()
    await r.controller.arm(current)
    wrong = replace(current, redis_run_id="0" * 40)
    assert await wire(
        r, activation.CLEAN_PREDECESSOR_SCRIPT, wrong, predecessor=first
    ) == ["identity_changed"]
    assert await r.client.exists(*namespace_keys(first)) == 4
    assert await r.store.read_retirement() == first
    disabled = await r.store.disable(current)
    with pytest.raises(AuthorityConflict):
        await r.controller.retire(current)
    assert await r.store.read_retirement() == first
    await r.controller.retire(disabled)
    assert await r.store.read_retirement() is None


async def test_lost_cleanup_reply_keeps_durable_predecessor_until_verified(
    recovery, monkeypatch
):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    current = await r.prepare()
    await r.controller.arm(current)
    original = activation.eval_once

    async def lose_reply(*args):
        result = await original(*args)
        if args[1] == activation.CLEAN_PREDECESSOR_SCRIPT:
            raise ConnectionError("cleanup reply lost")
        return result

    monkeypatch.setattr(activation, "eval_once", lose_reply)
    with pytest.raises(ConnectionError):
        await r.controller.retire(current)
    assert await r.client.exists(*namespace_keys(first)) == 0
    assert await r.store.read_retirement() == first
    with pytest.raises(AuthorityConflict, match="cleanup outstanding"):
        await r.prepare()
    assert await wire(r, activation.INITIALIZE_ONCE_SCRIPT, first) == ["admission_lost"]
