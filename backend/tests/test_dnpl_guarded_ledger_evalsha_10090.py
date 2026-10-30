"""#10090: cache DNPL's exact authority guard without replaying ambiguous writes."""

import asyncio
from datetime import datetime, timezone
from hashlib import sha1
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, NoScriptError, ResponseError

from app.services.dnpl_authority import Authority
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils.blend_preview import LEDGER_SCRIPT
from app.utils.dnpl_authority_registry import AuthorityLedgerRegistry
from app.utils.dnpl_redis_authority import (
    GUARDED_LEDGER_SCRIPT,
    INITIALIZE_SCRIPT,
    guard_token,
    namespace_keys,
)
from app.utils.preview_reservations import ReservationPolicy
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "mode,script,opcode",
    [
        ("1", GUARDED_LEDGER_SCRIPT, "EVALSHA"),
        ("0", GUARDED_LEDGER_SCRIPT, "EVAL"),
        ("1", LEDGER_SCRIPT, "EVALSHA"),
        ("0", LEDGER_SCRIPT, "EVALSHA"),
        ("1", "return {'unrelated'}", "EVAL"),
        ("0", "return {'unrelated'}", "EVAL"),
    ],
)
async def test_cache_mode_preserves_exact_script_transport(
    mode, script, opcode, monkeypatch
):
    monkeypatch.setenv("DNPL_GUARDED_LEDGER_EVALSHA", mode)

    class Wire:
        def __init__(self):
            self.commands = []

        async def send_command(self, *args):
            self.commands.append(args)

        async def read_response(self):
            return ["reply"]

    wire = Wire()
    assert await LiveBlendRefresher._preview_call(wire)(
        "EVAL", script, 1, "key", "arg"
    ) == ["reply"]
    program = (
        sha1(script.encode(), usedforsecurity=False).hexdigest()
        if opcode == "EVALSHA"
        else script
    )
    assert wire.commands == [(opcode, program, 1, "key", "arg")]


class RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.commands = []

    async def send_command(self, *args):
        self.commands.append(args)
        await self.connection.send_command(*args)

    async def read_response(self):
        return await self.connection.read_response()


@pytest.mark.parametrize("cold", [False, True])
async def test_default_authority_registry_preserves_guarded_wire_contract(
    cold, monkeypatch
):
    monkeypatch.delenv("DNPL_GUARDED_LEDGER_EVALSHA", raising=False)
    policy = ReservationPolicy()
    authority = Authority(
        3,
        1,
        UUID(int=1),
        UUID(int=2),
        "ready",
        "a" * 40,
        "b" * 40,
        policy.fingerprint,
    )
    registry = AuthorityLedgerRegistry(
        sources=frozenset({"kalshi", "polymarket"}),
        authority=authority,
        observed_after=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )

    class Wire:
        def __init__(self):
            self.commands = []

        async def send_command(self, *args):
            self.commands.append(args)

        async def read_response(self):
            if cold and len(self.commands) == 1:
                raise NoScriptError("cache empty")
            return ["ok", "1"]

    wire = Wire()
    assert (
        await registry.claim(LiveBlendRefresher._preview_call(wire), "polymarket") == 1
    )
    assert registry.claims == {"polymarket": 1}
    first = wire.commands[0]
    assert first[:2] == (
        "EVALSHA",
        sha1(GUARDED_LEDGER_SCRIPT.encode(), usedforsecurity=False).hexdigest(),
    )
    assert first[2:] == (
        6,
        *namespace_keys(authority),
        guard_token(authority),
        "a" * 40,
        "b" * 40,
        "polymarket",
        "0",
        policy.fingerprint,
        "claim",
        "polymarket",
    )
    if cold:
        assert len(wire.commands) == 2
        assert wire.commands[1] == ("EVAL", GUARDED_LEDGER_SCRIPT, *first[2:])
    else:
        assert len(wire.commands) == 1


@pytest.fixture
async def guarded_rig(redis_kwargs, monkeypatch):  # noqa: F811
    monkeypatch.delenv("DNPL_GUARDED_LEDGER_EVALSHA", raising=False)
    client = Redis(**redis_kwargs, decode_responses=True)
    server = await client.info("server")
    repl = await client.info("replication")
    authority = Authority(
        3,
        1,
        uuid4(),
        uuid4(),
        "ready",
        server["run_id"],
        repl["master_replid"],
        ReservationPolicy().fingerprint,
    )
    assert await client.eval(
        INITIALIZE_SCRIPT,
        6,
        *namespace_keys(authority),
        guard_token(authority),
        authority.redis_run_id,
        authority.redis_master_replid,
    ) == ["initialized"]
    registry = AuthorityLedgerRegistry(
        sources=frozenset({"kalshi", "polymarket"}),
        authority=authority,
        observed_after=datetime.now(timezone.utc),
    )
    connection = await client.connection_pool.get_connection("EVAL")
    recorder = RecordingConnection(connection)
    try:
        yield registry, recorder, client, authority
    finally:
        await client.connection_pool.release(connection)
        await client.aclose()


async def test_ready_authority_uses_warm_guarded_sha(guarded_rig):
    registry, connection, client, _ = guarded_rig
    await client.script_load(GUARDED_LEDGER_SCRIPT)
    claim = await registry.claim(
        LiveBlendRefresher._preview_call(connection), "polymarket"
    )
    assert claim == 1
    [command] = connection.commands
    assert command[:2] == (
        "EVALSHA",
        sha1(GUARDED_LEDGER_SCRIPT.encode(), usedforsecurity=False).hexdigest(),
    )


async def test_cold_guarded_sha_falls_back_once_with_original_args(guarded_rig):
    registry, connection, client, authority = guarded_rig
    await client.script_flush()
    call = LiveBlendRefresher._preview_call(connection)
    assert await registry.claim(call, "polymarket") == 1
    first, fallback = connection.commands
    assert first[0] == "EVALSHA"
    assert fallback[:2] == ("EVAL", GUARDED_LEDGER_SCRIPT)
    assert first[2:] == fallback[2:]
    assert fallback[2:9] == (6, *namespace_keys(authority))
    assert await registry.claim(call, "polymarket") == 2
    assert len(connection.commands) == 3
    assert connection.commands[-1][:2] == first[:2]


async def test_cached_guard_still_refuses_lost_authority(guarded_rig):
    registry, connection, client, authority = guarded_rig
    await client.script_load(GUARDED_LEDGER_SCRIPT)
    await client.delete(namespace_keys(authority)[0])
    with pytest.raises(RuntimeError, match="ledger claim refused"):
        await registry.claim(LiveBlendRefresher._preview_call(connection), "polymarket")
    assert len(connection.commands) == 1
    assert connection.commands[0][0] == "EVALSHA"
    assert registry.claims == {}


async def test_rollback_restores_guarded_eval_without_disabling_dnpl(
    guarded_rig, monkeypatch
):
    registry, connection, _, _ = guarded_rig
    monkeypatch.setenv("DNPL_GUARDED_LEDGER_EVALSHA", "0")
    assert (
        await registry.claim(LiveBlendRefresher._preview_call(connection), "polymarket")
        == 1
    )
    [command] = connection.commands
    assert command[:2] == ("EVAL", GUARDED_LEDGER_SCRIPT)


@pytest.mark.parametrize("script", [LEDGER_SCRIPT, "return {'unrelated'}"])
async def test_existing_plain_cache_and_unrelated_eval_stay_intact(guarded_rig, script):
    _, connection, client, _ = guarded_rig
    call = LiveBlendRefresher._preview_call(connection)
    if script == LEDGER_SCRIPT:
        await client.script_load(script)
        # Missing ledger arguments get the ledger's own refusal; only transport is asserted.
        await call("EVAL", script, 0)
        assert [command[0] for command in connection.commands] == ["EVALSHA"]
    else:
        assert await call("EVAL", script, 0) == ["unrelated"]
        assert connection.commands == [("EVAL", script, 0)]


class FailingResponse:
    def __init__(self, error, after_response=None):
        self.error = error
        self.after_response = after_response
        self.commands = []

    async def send_command(self, *args):
        self.commands.append(args)

    async def read_response(self):
        if self.after_response is not None:
            self.after_response()
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("reply lost after send"),
        asyncio.CancelledError(),
        ConnectionError("connection lost after send"),
        ResponseError("NOSCRIPT-looking generic error is not proof"),
    ],
)
async def test_ambiguous_guarded_send_is_never_replayed(error, monkeypatch):
    monkeypatch.delenv("DNPL_GUARDED_LEDGER_EVALSHA", raising=False)
    connection = FailingResponse(error)
    with pytest.raises(type(error)):
        await LiveBlendRefresher._preview_call(connection)(
            "EVAL", GUARDED_LEDGER_SCRIPT, 0
        )
    assert len(connection.commands) == 1
    assert connection.commands[0][0] == "EVALSHA"


async def test_cold_fallback_rechecks_deadline(monkeypatch):
    monkeypatch.delenv("DNPL_GUARDED_LEDGER_EVALSHA", raising=False)
    clock = SimpleNamespace(now=0.0)
    loop = SimpleNamespace(time=lambda: clock.now)
    connection = FailingResponse(
        NoScriptError("cold cache"),
        lambda: setattr(clock, "now", 2.0),
    )
    with monkeypatch.context() as patch:
        patch.setattr(asyncio, "get_running_loop", lambda: loop)
        with pytest.raises(TimeoutError, match="before transmission"):
            await LiveBlendRefresher._preview_call(connection, send_before=1.0)(
                "EVAL",
                GUARDED_LEDGER_SCRIPT,
                0,
            )
    assert len(connection.commands) == 1
    assert connection.commands[0][0] == "EVALSHA"


async def test_expired_deadline_sends_nothing():
    connection = FailingResponse(NoScriptError("must not reach Redis"))
    with pytest.raises(TimeoutError, match="before transmission"):
        await LiveBlendRefresher._preview_call(connection, send_before=0.0)(
            "EVAL",
            GUARDED_LEDGER_SCRIPT,
            0,
        )
    assert connection.commands == []
