"""Real PG + Unix-socket Redis lab: a limits-only reservation change and its rollback.

Production refusal reproduced first: the default "Other active" reservation
(48) refuses event 49 with `bucket_full`. The relimit plans then run through the
actual operator, runner, controller, PostgreSQL send permissions and Redis
scripts (only platform writer observations are simulated, as in the existing
operator controls). The new incarnation admits 160 Other events, a producer
still configured with the old sizes refuses to bind, the old namespace is gone,
and the scripted rollback restores the original allocation. No production.
"""

from dataclasses import asdict
from types import SimpleNamespace
import json
import os
from uuid import uuid4

import pytest

from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry
from app.utils.dnpl_redis_authority import GUARDED_LEDGER_SCRIPT, guard_token, namespace_keys
from app.utils.preview_reservations import ReservationPolicy
from tests.integration.test_dnpl_activation_10090_pg import recovery  # noqa: F401
from tests.integration.test_dnpl_authority_10090_pg import DB_URL, rig  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"),
]

OTHER_FIRST = (128, 48, 96, 48, 160, 32)
SOURCES = frozenset({"kalshi", "polymarket"})


def tool():
    from scripts import reservation_relimit_plan

    return reservation_relimit_plan


async def guarded(client, authority, op, *argv, owner="0", fingerprint=None):
    return await client.eval(
        GUARDED_LEDGER_SCRIPT, 6, *namespace_keys(authority), guard_token(authority),
        authority.redis_run_id, authority.redis_master_replid, "kalshi", owner,
        fingerprint or authority.policy_fingerprint, op, "kalshi", *argv,
    )


async def open_other_active(client, authority, owner, event_id):
    """One NEW event's first preview open in the Other-active bucket (4)."""
    reply = await guarded(
        client, authority, "propose", owner, str(event_id), "kalshi", "open", "1", "1",
        "10", "60000", "512", '{"value":0.6}', "10", '{"base":10}', "0", "4", "1",
        owner=owner,
    )
    return reply[0]


async def producer(store, client, limits):
    """The real producer registry: bind the PG authority, then claim in Redis."""
    registry = AuthorityLedgerRegistry(sources=SOURCES, policy=ReservationPolicy(limits))
    await registry.bind_primary(store)

    async def call(*args):
        return await client.execute_command(*args)

    await registry.claim(call, "kalshi")
    return registry


async def run_plan(plan_data, controller, tmp_path, monkeypatch, name):
    from app.services import dnpl_activation_operator as operator
    from app.services import dnpl_activation_runner as runner

    plan = operator.parse_plan(json.dumps(plan_data).encode())
    lock = tmp_path / f"{name}.lock"
    lock.write_text(
        f"status: HELD\nowner_identity: relimit-lab\nowner_pid: {os.getpid()}\nclaimed_epoch_s: 1\n"
    )
    run_dir = tmp_path / name
    run_dir.mkdir(mode=0o700)
    # Only the platform writer observation is a stand-in (disposable lab owns all writers).
    monkeypatch.setattr(
        runner, "execute_verifier",
        lambda *a, **k: SimpleNamespace(validate=lambda: {"nonce": str(uuid4())}),
    )
    result = await operator.execute_plan(
        plan, controller, lock_path=lock, identity="relimit-lab", run_dir=run_dir)
    assert result["status"] == "PLAN_DONE", result
    return plan


def apps():
    return {app: {"release": 1, "slug": str(uuid4()), "commit": "c" * 40}
            for app in ("bainluck", "bainluck-heavy")}


async def fill_other_active(client, authority, owner, count, start):
    for event_id in range(start, start + count):
        assert await open_other_active(client, authority, owner, event_id) == "ok"
    return await open_other_active(client, authority, owner, start + count)


async def test_relimit_admits_more_other_events_and_rolls_back(recovery, tmp_path, monkeypatch):  # noqa: F811
    t, r = tool(), recovery
    server, repl = await r.client.info("server"), await r.client.info("replication")
    primary = (server["run_id"], repl["master_replid"])

    # Today's production shape: incarnation 1, default sizes, Other active full at 48.
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    old = await r.controller.ready(first)
    assert old.policy_fingerprint == ReservationPolicy().fingerprint
    k = await producer(r.store, r.client, ReservationPolicy().limits)
    owner = str(k.claim_of("kalshi"))
    assert await fill_other_active(r.client, old, owner, 48, 1) == "bucket_full"

    # Integrator order: config var already set to the target before the plans run.
    built = t.build(old, primary, apps(), OTHER_FIRST, "128,48,96,48,160,32")
    await run_plan(built["activate"], r.controller, tmp_path, monkeypatch, "activate")
    new = await r.store.read()
    assert (new.incarnation, new.state) == (2, "ready")
    assert new.policy_fingerprint == "v1-six-hour-ba82e47ee634aba7:128,48,96,48,160,32"
    assert await r.store.read_retirement() == old
    await run_plan(built["retire"], r.controller, tmp_path, monkeypatch, "retire")
    assert await r.store.read_retirement() is None
    assert await r.client.exists(*namespace_keys(old)) == 0
    assert await r.client.dbsize() == 5  # one fence + the new namespace's four keys
    assert json.loads(json.dumps(built["next_expected_authority"])) == json.loads(
        json.dumps(asdict(new), default=str))

    # Fail closed: a producer still configured with the old sizes cannot bind,
    # an old-sized command is refused, and the retired namespace refuses its token.
    with pytest.raises(ValueError, match="reservation policy mismatch"):
        await producer(r.store, r.client, ReservationPolicy().limits)
    assert await guarded(r.client, new, "claim",
                         fingerprint=old.policy_fingerprint) == ["policy_mismatch"]
    assert await guarded(r.client, old, "claim") == ["guard_refused"]
    assert await r.client.exists(*namespace_keys(old)) == 0

    # The new allocation: 160 Other-active events, the 161st refused.
    k2 = await producer(r.store, r.client, OTHER_FIRST)
    assert k2.authority == new
    owner2 = str(k2.claim_of("kalshi"))
    assert await fill_other_active(r.client, new, owner2, 160, 1) == "bucket_full"
    ledger = namespace_keys(new)[0]
    assert await r.client.hget(ledger, "reservation_policy") == new.policy_fingerprint
    assert await r.client.hget(ledger, "r:count:4") == "160"

    # Scripted rollback to 192,64,128,64,48,16 with the config var unset again.
    back = t.build(new, primary, apps(), t.parse_limits("default"), "")
    await run_plan(back["activate"], r.controller, tmp_path, monkeypatch, "rollback")
    await run_plan(back["retire"], r.controller, tmp_path, monkeypatch, "rollback-retire")
    restored = await r.store.read()
    assert (restored.incarnation, restored.state) == (3, "ready")
    assert restored.policy_fingerprint == ReservationPolicy().fingerprint
    assert await r.client.exists(*namespace_keys(new)) == 0
    assert await r.client.dbsize() == 5
    with pytest.raises(ValueError, match="reservation policy mismatch"):
        await producer(r.store, r.client, OTHER_FIRST)
    k3 = await producer(r.store, r.client, ReservationPolicy().limits)
    assert await fill_other_active(r.client, restored, str(k3.claim_of("kalshi")), 48, 1) == "bucket_full"


async def test_a_plan_built_for_other_sizes_than_configured_never_reaches_the_operator(recovery):  # noqa: F811
    t, r = tool(), recovery
    server, repl = await r.client.info("server"), await r.client.info("replication")
    first = await r.prepare()
    await r.controller.arm(first)
    await r.controller.initialize(first)
    old = await r.controller.ready(first)
    with pytest.raises(t.RelimitRefused, match="does not produce"):
        t.build(old, (server["run_id"], repl["master_replid"]), apps(), OTHER_FIRST, "")
    # Nothing was allocated or sent.
    assert await r.store.read() == old
    assert await r.store.read_retirement() is None
    assert await r.client.dbsize() == 5
