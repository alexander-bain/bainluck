"""Real existing PG + Unix-socket Redis lab; explicit recovery, no production."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.services import dnpl_activation as activation
from app.services.dnpl_authority import AuthorityConflict, preparing_candidate
from app.utils.dnpl_redis_authority import guard_token, namespace_keys
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
    tail = (
        guard_token(predecessor)
        if script == activation.CLEAN_PREDECESSOR_SCRIPT and predecessor is not None
        else "1" if bootstrap else "0"
    )
    return await activation.eval_once(
        r.client,
        script,
        keys,
        (*activation.arguments(authority), tail),
    )


async def test_command_preview_preserves_actual_recovery_state(recovery):
    from app.services.dnpl_activation_command import preview

    r = recovery
    prepared = await r.prepare()
    primary = (prepared.redis_run_id, prepared.redis_master_replid)
    for action in (None, r.controller.arm, r.controller.initialize, r.controller.ready):
        if action is not None:
            await action(prepared)
        current = await r.store.read()
        before = (
            current,
            await r.store.activation_step(current),
            await r.store.read_retirement(),
        )
        keys = sorted(await r.client.keys("*"))
        values = [await r.client.dump(key) for key in keys]
        result = await preview(r.store, r.client, current, primary)
        assert result["status"] == "SNAPSHOT_MATCH"
        assert result["mutation_permitted"] is False
        assert result["activation_step"] == before[1]
        assert (
            await r.store.read(),
            await r.store.activation_step(current),
            await r.store.read_retirement(),
        ) == before
        assert sorted(await r.client.keys("*")) == keys
        assert [await r.client.dump(key) for key in keys] == values


async def test_command_preview_rejects_wrong_actual_primary_without_mutation(recovery):
    from app.services.dnpl_activation_command import preview

    r = recovery
    prepared = await r.prepare()
    with pytest.raises(AuthorityConflict, match="expected Redis primary differs"):
        await preview(r.store, r.client, prepared, ("0" * 40, "0" * 40))
    assert await r.store.read() == prepared
    assert await r.store.activation_step(prepared) == 0
    assert await r.client.dbsize() == 0


@pytest.mark.parametrize("lost_reply", [False, True])
async def test_command_runner_real_lifecycle_and_uncertain_readback(
    recovery, tmp_path, monkeypatch, lost_reply
):
    import os
    from app.services import dnpl_activation_runner as runner
    from app.services.dnpl_operation_hold import DeskHold, OperationHoldRefused

    r = recovery
    server, repl = await r.client.info("server"), await r.client.info("replication")
    primary = (server["run_id"], repl["master_replid"])
    seed = await r.store.read()
    prepared = preparing_candidate(
        seed,
        namespace=uuid4(),
        operation_id=uuid4(),
        redis_run_id=primary[0],
        redis_master_replid=primary[1],
        policy_fingerprint=ReservationPolicy().fingerprint,
    )
    lock = tmp_path / "local-only.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: integrator-local-test\nowner_pid: {os.getpid()}\nclaimed_epoch_s: 1\n"
    )
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    # The disposable lab itself owns all writers. Platform observation is a
    # local stand-in; real child execution/response validation has its own tests.
    monkeypatch.setattr(
        runner,
        "execute_verifier",
        lambda *a, **k: SimpleNamespace(validate=lambda: {"nonce": str(uuid4())}),
    )
    original = activation.eval_once
    sends = []

    async def transport(*args):
        result = await original(*args)
        sends.append(args[1])
        if lost_reply and args[1] == activation.INITIALIZE_ONCE_SCRIPT:
            raise ConnectionError("reply lost after actual initialization")
        return result

    monkeypatch.setattr(activation, "eval_once", transport)
    with DeskHold.capture(lock, "integrator-local-test", run) as hold:
        bound = dict(
            hold=hold,
            controller=r.controller,
            run_dir=run,
            run_id=str(uuid4()),
            primary=primary,
            apps={},
        )
        assert (
            await runner.run_step(
                **bound, step="prepare", expected=seed, candidate=prepared
            )
        ).status == "DONE"
        assert (
            await runner.run_step(**bound, step="arm", expected=prepared)
        ).status == "DONE"
        result = await runner.run_step(**bound, step="initialize", expected=prepared)
        assert result.status == ("UNCERTAIN" if lost_reply else "DONE")
        with pytest.raises(OperationHoldRefused, match="already consumed"):
            await runner.run_step(**bound, step="initialize", expected=prepared)
        assert (
            await runner.run_step(**bound, step="ready", expected=prepared)
        ).status == "DONE"
        assert await r.controller.read_ready(prepared)
    assert sends.count(activation.INITIALIZE_ONCE_SCRIPT) == 1
    assert await r.client.dbsize() == 5


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
    deletions = []

    async def lose_reply(*args):
        result = await original(*args)
        if args[1] == activation.CLEAN_PREDECESSOR_SCRIPT:
            deletions.append(args)
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

    await r.controller.acknowledge_retirement(current)
    assert len(deletions) == 1
    assert await r.store.read_retirement() is None
    # Reading and acknowledging absence unblocks a new allocation, without
    # replaying a lost Redis mutation or treating timeout as non-execution.
    assert (await r.prepare()).incarnation == 3


async def test_retirement_readback_refuses_surviving_keys_or_missing_fence(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    current = await r.prepare()
    await r.controller.arm(current)
    with pytest.raises(activation.ActivationRefused, match="cleanup_unverified"):
        await r.controller.acknowledge_retirement(current)
    assert await r.store.read_retirement() == first
    await r.client.delete(*namespace_keys(first), activation.ADMISSION_KEY)
    with pytest.raises(activation.ActivationRefused, match="admission_lost"):
        await r.controller.acknowledge_retirement(current)
    assert await r.store.read_retirement() == first


@pytest.mark.parametrize(
    "evict_fence,lose_reply", [(False, False), (True, False), (False, True)]
)
async def test_replacement_primary_frees_pending_predecessor_then_recovers(
    recovery, monkeypatch, evict_fence, lose_reply
):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    await r.controller.ready(first)
    second = await r.prepare()
    await r.controller.arm(second)
    if evict_fence:
        await r.client.delete(activation.ADMISSION_KEY)
    # Existing fixture starts a second real private server. Simulate persisted
    # old key bytes carried to the new identity, not an always-empty shortcut.
    with contextmanager(redis_kwargs.__wrapped__)() as new_kwargs:
        fresh = Redis(**new_kwargs, decode_responses=True)
        try:
            for key in (
                *namespace_keys(first),
                *namespace_keys(second),
                activation.ADMISSION_KEY,
            ):
                data = await r.client.dump(key)
                if data is not None:
                    await fresh.restore(key, 0, data)
            server = await fresh.info("server")
            repl = await fresh.info("replication")
            identity = dict(
                redis_run_id=server["run_id"], redis_master_replid=repl["master_replid"]
            )
            assert identity["redis_run_id"] != second.redis_run_id
            controller = activation.ActivationController(r.store, fresh)
            with pytest.raises(activation.ActivationRefused, match="identity_changed"):
                await controller.retire(second)
            original = activation.eval_once
            deletions = []

            async def maybe_lose(*args):
                result = await original(*args)
                if args[1] == activation.CLEAN_REPLACED_PREDECESSOR_SCRIPT:
                    deletions.append(args)
                    if lose_reply:
                        raise ConnectionError("replacement cleanup reply lost")
                return result

            monkeypatch.setattr(activation, "eval_once", maybe_lose)
            if lose_reply:
                with pytest.raises(ConnectionError):
                    await controller.retire_after_primary_change(second, **identity)
                assert await r.store.read_retirement() == replace(first, state="ready")
                await controller.retire_after_primary_change(
                    second, **identity, readback_only=True
                )
            else:
                await controller.retire_after_primary_change(second, **identity)
            assert len(deletions) == 1
            assert await fresh.exists(*namespace_keys(first)) == 0
            assert await r.store.read_retirement() is None
            assert await r.store.read() == second
            third = await r.store.prepare(
                second,
                preparing_candidate(
                    second,
                    namespace=uuid4(),
                    operation_id=uuid4(),
                    policy_fingerprint=second.policy_fingerprint,
                    **identity,
                ),
            )
            await controller.arm(third)
            await controller.initialize(third)
            await controller.retire(third)
            assert (await controller.ready(third)).incarnation == 3
            assert await fresh.dbsize() == 5
            # The address is reused, but the old replacement cleanup must not
            # delete the new occupant after its original PG receipt was cleared.
            assert namespace_keys(first) == namespace_keys(third)
            before = {key: await fresh.dump(key) for key in namespace_keys(third)}
            delayed = deletions[0]
            assert await original(*delayed) == ["occupant_changed"]
            assert before == {
                key: await fresh.dump(key) for key in namespace_keys(third)
            }
            assert await controller.read_ready(third)
            # Old authority cannot recreate its cleaned namespace on replacement.
            assert await activation.eval_once(
                fresh,
                activation.INITIALIZE_ONCE_SCRIPT,
                (*namespace_keys(first), activation.ADMISSION_KEY),
                activation.arguments(first),
            ) == ["identity_changed"]
        finally:
            await fresh.aclose()


async def test_replacement_cleanup_requires_distinct_actual_identity(recovery):
    r = recovery
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    second = await r.prepare()
    await r.controller.arm(second)
    with pytest.raises(activation.ActivationRefused, match="fence both"):
        await r.controller.retire_after_primary_change(
            second,
            redis_run_id=second.redis_run_id,
            redis_master_replid=second.redis_master_replid,
        )
    with pytest.raises(activation.ActivationRefused, match="identity_changed"):
        await r.controller.retire_after_primary_change(
            second,
            redis_run_id="0" * 40,
            redis_master_replid="1" * 40,
        )
    assert await r.client.exists(*namespace_keys(first)) == 4
    assert await r.store.read_retirement() == first


@pytest.mark.parametrize("lost_reply", [False, True])
@pytest.mark.parametrize("remote_budget", [False, True])
async def test_operator_plan_real_lifecycle_stops_without_replaying(
    recovery, tmp_path, monkeypatch, lost_reply, remote_budget
):
    from dataclasses import asdict
    import json
    import os
    from app.services import dnpl_activation_operator as operator
    from app.services import dnpl_activation_runner as runner
    from app.services.dnpl_operation_hold import OperationHoldRefused

    r = recovery
    from app.services.dnpl_operator_budget import (
        OperatorAuthorityStore,
        OperatorBudgets,
    )

    budgets = OperatorBudgets(1000, 5000) if remote_budget else OperatorBudgets()
    if remote_budget:
        import asyncio
        from contextlib import asynccontextmanager

        sessions = r.store.sessions

        @asynccontextmanager
        async def delayed_sessions():
            await asyncio.sleep(0.2)
            async with sessions() as session:
                yield session

        r.store = OperatorAuthorityStore(delayed_sessions, budgets)
        r.controller = activation.ActivationController(
            r.store, r.client, command_budget_s=budgets.io_s
        )
        acquire = r.client.connection_pool.get_connection

        async def delayed_connection(*args, **kwargs):
            await asyncio.sleep(0.2)
            return await acquire(*args, **kwargs)

        monkeypatch.setattr(
            r.client.connection_pool, "get_connection", delayed_connection
        )
    seed = await r.store.read()
    server, repl = await r.client.info("server"), await r.client.info("replication")
    primary = (server["run_id"], repl["master_replid"])
    candidate = preparing_candidate(
        seed,
        namespace=uuid4(),
        operation_id=uuid4(),
        redis_run_id=primary[0],
        redis_master_replid=primary[1],
        policy_fingerprint=ReservationPolicy().fingerprint,
    )
    payload = {
        "run_id": str(uuid4()),
        "primary": ":".join(primary),
        "apps": {
            app: {"release": 1, "slug": str(uuid4()), "commit": "c" * 40}
            for app in operator.APPS
        },
        "steps": [
            {
                "step": "prepare",
                "expected": asdict(seed),
                "candidate": asdict(candidate),
            }
        ]
        + [
            {"step": step, "expected": asdict(candidate), "candidate": None}
            for step in ("arm", "initialize", "ready")
        ],
    }
    plan = operator.parse_plan(json.dumps(payload, default=str).encode())
    lock = tmp_path / "operator.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: local-plan\nowner_pid: {os.getpid()}\nclaimed_epoch_s: 1\n"
    )
    run_dir = tmp_path / "operator-run"
    run_dir.mkdir(mode=0o700)
    # Only platform observations are simulated. The hold, runner, controller,
    # PG send permissions and Redis commands are the actual implementation.
    monkeypatch.setattr(
        runner,
        "execute_verifier",
        lambda *a, **k: SimpleNamespace(validate=lambda: {"nonce": str(uuid4())}),
    )
    original, sent = activation.eval_once, []

    async def transport(*args, **kwargs):
        result = await original(*args, **kwargs)
        sent.append(args[1])
        if lost_reply and args[1] == activation.INITIALIZE_ONCE_SCRIPT:
            raise ConnectionError("lost actual initializer reply")
        return result

    monkeypatch.setattr(activation, "eval_once", transport)
    kwargs = {"lock_path": lock, "identity": "local-plan", "run_dir": run_dir}
    result = await operator.execute_plan(plan, r.controller, budgets=budgets, **kwargs)
    assert result["status"] == ("UNCERTAIN" if lost_reply else "PLAN_DONE")
    assert result["transport_budgets"] == {
        "io_ms": budgets.io_ms,
        "preview_ms": budgets.preview_ms,
    }
    assert sent.count(activation.INITIALIZE_ONCE_SCRIPT) == 1
    assert (await r.store.read()).state == ("preparing" if lost_reply else "ready")
    with pytest.raises(OperationHoldRefused, match="already consumed"):
        await operator.execute_plan(
            plan, r.controller, budgets=OperatorBudgets(5000, 30000), **kwargs
        )
    if lost_reply:
        assert result["steps"][-1]["step"] == "initialize"
        # Explicit local readback resolves the sent initializer; the CLI did
        # not automatically continue after uncertainty or resend anything.
        assert (await r.controller.ready(candidate)).state == "ready"
    assert sent.count(activation.INITIALIZE_ONCE_SCRIPT) == 1
    assert await r.controller.read_ready(candidate)
