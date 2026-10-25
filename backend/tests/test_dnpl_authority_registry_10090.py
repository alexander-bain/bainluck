"""Real Redis controls for namespace-bound existing producer semantics."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry
from app.utils.dnpl_authority_transport import decode_preview
from app.utils.dnpl_redis_authority import namespace_keys
from app.utils.live_push import event_channel
from tests.test_dnpl_redis_authority_10090 import rig, initial  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = pytest.mark.asyncio


def registry(a, now, **kwargs):
    return AuthorityLedgerRegistry(
        authority=replace(a, state="ready"),
        observed_after=now - timedelta(seconds=2),
        sources=frozenset({"kalshi", "polymarket"}),
        **kwargs
    )


async def proposal(reg, call, source, value=0.7, *, now, ticket=None, basis=None):
    if ticket is None:
        ticket, _ = await reg.read_ticket(call, source)
    event = SimpleNamespace(
        status="live",
        sport_key="basketball_nba",
        commence_time=now,
        completed_at=None,
        preview_context_at=now,
        preview_read_ticket=ticket,
        espn_win_prob_home=None,
        opening_home_probability=None,
    )
    base = {
        name: {"value": 0.5, "updated_at": now.isoformat()}
        for name in ("kalshi", "polymarket")
    }
    return reg.propose(
        42,
        source,
        value=value,
        event=event,
        row_sources=base,
        row_rev=10,
        observed_basis=(
            basis
            if basis is not None
            else {"1": (now - timedelta(seconds=1)).timestamp()}
        ),
        stamped_at=now,
    )


async def read_wire(listener):
    message = await listener.get_message(ignore_subscribe_messages=True, timeout=1)
    assert message is not None
    return decode_preview(event_channel(42), message["data"], 0)


async def test_two_sources_compose_and_publish_v3_with_real_ttl_then_revoke(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    k, p = registry(a, now), registry(a, now)
    call = client.execute_command
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    listener = client.pubsub()
    await listener.subscribe(event_channel(42))
    await listener.get_message(timeout=1)
    stats = {}
    try:
        await k.execute(
            await proposal(k, call, "kalshi", now=now), call, event_channel, stats
        )
        first = json.loads((await read_wire(listener)).payload)
        assert first["p"] == pytest.approx(0.6)
        assert 0 < first["preview"]["ttl_ms"] <= 60000
        await p.execute(
            await proposal(p, call, "polymarket", value=0.9, now=now),
            call,
            event_channel,
            stats,
        )
        second = json.loads((await read_wire(listener)).payload)
        assert second["p"] == pytest.approx(0.8)
        assert second["preview"]["pending"] == {"kalshi": 0.7, "polymarket": 0.9}
        assert second["preview"]["seq"] > first["preview"]["seq"]
        await k.execute(k.refused(42, "kalshi", "test"), call, event_channel, stats)
        sibling = json.loads((await read_wire(listener)).payload)
        assert sibling["preview"]["pending"] == {"polymarket": 0.9}
        await p.execute(p.refused(42, "polymarket", "test"), call, event_channel, stats)
        revoked = json.loads((await read_wire(listener)).payload)
        assert revoked["preview"]["kind"] == "revoke"
        assert stats["published"] == 3 and stats["revoked"] == 1
    finally:
        await listener.aclose()


async def test_old_domain_ticket_operation_and_frame_cannot_enter_new_domain(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    old = registry(a, now)
    call = client.execute_command
    await old.claim(call, "kalshi")
    ticket, _ = await old.read_ticket(call, "kalshi")
    ops = await proposal(old, call, "kalshi", now=now, ticket=ticket)
    prepared = await old.prepare(ops, call, {})
    assert prepared
    b = replace(a, incarnation=2, namespace=uuid4(), operation_id=uuid4())
    await initial(client, b)
    new = registry(b, now)
    await new.claim(call, "kalshi")
    assert old.claims == new.claims == {"kalshi": 1}, "exercise numeric collision"
    before = {key: await client.dump(key) for key in namespace_keys(b)}
    assert await proposal(new, call, "kalshi", now=now, ticket=ticket) == []
    assert new.retire_missing(42, "kalshi", ticket) is None
    assert await new.prepare(ops, call, {}) == []
    stats = {}
    await new.execute(prepared, call, event_channel, stats)
    assert stats["authority_refused"] == 1
    assert before == {key: await client.dump(key) for key in namespace_keys(b)}
    assert await new.prepare(await proposal(new, call, "kalshi", now=now), call, {})


@pytest.mark.parametrize("basis", [{"1": -3}, {"1": -2}, {"1": -1, "2": -3}, {}])
async def test_pre_activation_observation_never_creates_local_or_shared_residency(
    rig, basis  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    reg = registry(a, now)
    call = client.execute_command
    await reg.claim(call, "kalshi")
    actual = {
        key: (now + timedelta(seconds=seconds)).timestamp()
        for key, seconds in basis.items()
    }
    assert await proposal(reg, call, "kalshi", now=now, basis=actual) == []
    assert not reg._events
    assert await client.hget(namespace_keys(a)[0], "nevents") == "0"


async def test_source_owner_change_refuses_prepared_operation_and_revoke(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    reg = registry(a, now)
    call = client.execute_command
    await reg.claim(call, "kalshi")
    ops = await proposal(reg, call, "kalshi", now=now)
    await reg.prepare(ops, call, {})
    revoked = await reg.prepare(reg.refused(42, "kalshi", "test"), call, {})
    assert revoked[0]["preview"]["kind"] == "revoke"
    await reg.claim(call, "kalshi")
    before = {key: await client.dump(key) for key in namespace_keys(a)}
    assert await reg.prepare(ops, call, {}) == []
    stats = {}
    await reg.execute(revoked, call, event_channel, stats)
    assert stats["authority_refused"] == 1
    assert before == {key: await client.dump(key) for key in namespace_keys(a)}


async def test_namespace_loss_stops_instance_without_reinitialization(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    reg = registry(a, now)
    call = client.execute_command
    await reg.claim(call, "kalshi")
    await client.delete(namespace_keys(a)[0])
    assert await reg.read_ticket(call, "kalshi") == (None, [])
    assert reg._halted
    with pytest.raises(RuntimeError, match="authority_stopped"):
        await reg.claim(call, "kalshi")
    assert await client.exists(namespace_keys(a)[0]) == 0


async def test_contributor_owner_change_recomposes_through_same_domain(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    k, p, successor = registry(a, now), registry(a, now), registry(a, now)
    call = client.execute_command
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    await k.prepare(await proposal(k, call, "kalshi", now=now), call, {})
    await p.prepare(await proposal(p, call, "polymarket", value=0.9, now=now), call, {})
    frames = await k.prepare(
        await proposal(
            k, call, "kalshi", value=0.75, now=now + timedelta(milliseconds=1)
        ),
        call,
        {},
    )
    assert set(frames[0]["preview"]["pending"]) == {"kalshi", "polymarket"}
    await successor.claim(call, "polymarket")
    listener = client.pubsub()
    await listener.subscribe(event_channel(42))
    await listener.get_message(timeout=1)
    stats = {}
    try:
        await k.execute(frames, call, event_channel, stats)
        record = await read_wire(listener)
        result = json.loads(record.payload)
        assert record.authority == k.authority
        assert result["preview"]["pending"] == {"kalshi": 0.75}
        assert stats["ledger_recomposed"] == 1
        assert stats["published"] == 1
    finally:
        await listener.aclose()


async def test_other_process_fences_old_revoke_at_guarded_lua(rig):  # noqa: F811
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    old, new = registry(a, now), registry(a, now)
    call = client.execute_command
    await old.claim(call, "kalshi")
    await old.prepare(await proposal(old, call, "kalshi", now=now), call, {})
    revoke = await old.prepare(old.refused(42, "kalshi", "test"), call, {})
    await new.claim(call, "kalshi")
    before = {key: await client.dump(key) for key in namespace_keys(a)}
    stats = {}
    await old.execute(revoke, call, event_channel, stats)
    assert stats == {"authority_refused": 1}
    assert before == {key: await client.dump(key) for key in namespace_keys(a)}


async def test_runtime_startup_binds_primary_once_before_redis_claim(
    rig, monkeypatch  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    from app.services.dnpl_authority import AuthorityStore
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from app.utils import blend_preview

    client, a = rig
    await initial(client, a)
    ready = replace(a, state="ready")
    reads = []
    now = datetime.now(timezone.utc)

    async def sample(store):
        reads.append(store.sessions)
        return ready, now

    class Connection:
        async def send_command(self, *args):
            self.reply = await client.execute_command(*args)

        async def read_response(self):
            return self.reply

    monkeypatch.setattr(AuthorityStore, "read_for_producer", sample)
    monkeypatch.setattr(blend_preview, "_REGISTRY", None)
    preview = blend_preview.registry()
    assert isinstance(preview, AuthorityLedgerRegistry) and preview.authority is None
    factory = object()
    worker = LiveBlendRefresher("kalshi", session_factory=factory)
    await worker._claim_preview_epoch(Connection(), preview)
    assert preview.authority == ready
    assert reads == [factory]
    assert preview.claim_of("kalshi") == 1
    # A second source shares the SAME bound instance; no fresh binding may
    # move the post-activation observation floor or relabel pending operations.
    other = LiveBlendRefresher("polymarket", session_factory=factory)
    await other._claim_preview_epoch(Connection(), preview)
    assert reads == [factory]
    assert preview.claim_of("polymarket") == 2


async def test_unready_startup_performs_no_redis_claim_and_keeps_registry_unbound(
    rig, monkeypatch  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    from app.services.dnpl_authority import AuthorityStore
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    _, a = rig

    async def sample(store):
        return a, datetime.now(timezone.utc)  # still preparing

    class Connection:
        async def send_command(self, *args):
            pytest.fail("unready control must not send Redis command")

    monkeypatch.setattr(AuthorityStore, "read_for_producer", sample)
    reg = AuthorityLedgerRegistry(sources=frozenset({"kalshi", "polymarket"}))
    worker = LiveBlendRefresher("kalshi", session_factory=object())
    with pytest.raises(ValueError, match="ready primary"):
        await worker._claim_preview_epoch(Connection(), reg)
    assert reg.authority is None and not reg.claims and not reg._events


async def test_actual_refresher_publishes_v3_above_its_own_claim_and_settles(
    rig, monkeypatch  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    from app.services.dnpl_authority import AuthorityStore
    from app.tasks.live_blend_refresh import LiveBlendRefresher
    from app.utils import blend_preview

    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    ready = replace(a, state="ready")

    async def sample(store):
        return ready, now - timedelta(seconds=2)

    monkeypatch.setattr(AuthorityStore, "read_for_producer", sample)
    monkeypatch.setattr(blend_preview, "_REGISTRY", None)
    worker = LiveBlendRefresher("kalshi")
    monkeypatch.setattr(worker, "_client", lambda: client)
    other = registry(a, now)
    await other.claim(client.execute_command, "polymarket")
    owner = await worker.claim_preview_display()
    reg = blend_preview.registry()
    assert owner == 2 and reg.authority == ready
    listener = client.pubsub()
    await listener.subscribe(event_channel(42))
    await listener.get_message(timeout=1)
    try:
        await worker._publish_previews(
            await proposal(reg, client.execute_command, "kalshi", now=now)
        )
        first = json.loads((await read_wire(listener)).payload)
        assert first["preview"]["kind"] == "blend"
        assert first["preview"]["epoch"] != owner
        assert first["preview"]["epoch"] == int(
            await client.hget(namespace_keys(a)[0], "e:42:gen")
        )
        assert worker.preview_stats["published"] == 1
        settled = await worker._prepare_ledger_previews(
            reg.refused(42, "kalshi", "test")
        )
        assert [f["preview"]["kind"] for f in settled] == ["revoke"]
        await worker._publish_previews(settled)
        revoke = json.loads((await read_wire(listener)).payload)
        assert revoke["preview"]["epoch"] == first["preview"]["epoch"]
        assert revoke["preview"]["through_seq"] == first["preview"]["seq"]
    finally:
        await listener.aclose()
