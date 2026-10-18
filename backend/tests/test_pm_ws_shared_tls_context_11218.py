"""#11218 — every Polymarket shard in a process dials with ONE TLS context.

`websockets.connect` builds a fresh `ssl.create_default_context()` per wss://
dial when it is given none, and each one loads the system CA bundle into its
own store (~0.7 MiB on OpenSSL 3, held for the connection's life). worker-ws
holds ~140 Polymarket shards, so the default cost ~100 MiB of identical stores
and kept worker-ws above the #11218 trial's 950 MB memory line. Local TLS rig
(real client, real `websockets`, 140 shards, CA bundle of 120 certs): 180 MiB
per process on 983018e0, 87 MiB with the shared context.

These tests pin the population fact (one context for every shard of every
client in the process, built once) and that the context is the same default
one `websockets` would have built, so verification is unchanged.
"""

import asyncio
import ssl

import pytest

import app.services.polymarket_ws as pm
from app.services.polymarket_ws import PolymarketWebSocket, _shard_asset_ids


def _ids(n, start=0):
    return [str(10**76 + start + i) for i in range(n)]


class _HeldSocket:
    """Accepts the subscribe and holds the connection open, like the venue."""

    async def send(self, payload):
        return None

    def __aiter__(self):
        async def gen():
            await asyncio.sleep(3600)
            yield "unreachable"

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def fresh_context(monkeypatch):
    monkeypatch.setattr(pm, "_TLS_CONTEXT", None)
    built = []
    real = ssl.create_default_context

    def counting(*args, **kwargs):
        ctx = real(*args, **kwargs)
        built.append(ctx)
        return ctx

    monkeypatch.setattr(pm.ssl, "create_default_context", counting)
    return built


async def _dial(monkeypatch, clients):
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return _HeldSocket()

    monkeypatch.setattr("websockets.connect", connect, raising=False)
    tasks = [
        asyncio.create_task(ws.run(asset_ids=assets)) for ws, assets in clients
    ]
    await asyncio.sleep(0.2)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return calls


class TestOneTlsContextPerProcess:
    @pytest.mark.asyncio
    async def test_every_shard_of_both_clients_shares_one_context_built_once(
        self, monkeypatch, fresh_context
    ):
        game_assets, open_assets = _ids(2600), _ids(3100, start=10**6)
        calls = await _dial(
            monkeypatch,
            [
                (PolymarketWebSocket(), game_assets),
                (PolymarketWebSocket(max_queue=4), open_assets),
            ],
        )
        shards = len(_shard_asset_ids(game_assets)) + len(
            _shard_asset_ids(open_assets)
        )
        assert shards >= 10, "the rig must hold a fleet, not one socket"
        assert len(calls) == shards
        contexts = [kwargs.get("ssl") for _, kwargs in calls]
        assert all(isinstance(c, ssl.SSLContext) for c in contexts), (
            "a shard dialled without an explicit context; websockets then "
            "builds and holds its own CA store for that connection"
        )
        assert len({id(c) for c in contexts}) == 1
        assert len(fresh_context) == 1, (
            f"{len(fresh_context)} contexts built for {shards} shards"
        )
        assert contexts[0] is fresh_context[0]

    @pytest.mark.asyncio
    async def test_a_later_client_reuses_the_context_instead_of_building_one(
        self, monkeypatch, fresh_context
    ):
        first = await _dial(monkeypatch, [(PolymarketWebSocket(), _ids(5))])
        second = await _dial(monkeypatch, [(PolymarketWebSocket(), _ids(5, 99))])
        assert first[0][1]["ssl"] is second[0][1]["ssl"]
        assert len(fresh_context) == 1

    def test_the_shared_context_verifies_like_the_default_websockets_builds(
        self, fresh_context
    ):
        ctx = pm._tls_context(pm.WS_URL)
        reference = ssl.create_default_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert ctx.protocol == reference.protocol
        assert ctx.minimum_version == reference.minimum_version
        assert ctx.options == reference.options
        assert ctx.verify_flags == reference.verify_flags

    def test_production_url_is_wss_so_the_shared_context_is_used(self):
        assert pm.WS_URL.startswith("wss://")

    @pytest.mark.asyncio
    async def test_a_plain_ws_url_passes_no_context(
        self, monkeypatch, fresh_context
    ):
        # websockets refuses any `ssl` argument on ws://; local rigs use one.
        monkeypatch.setattr(pm, "WS_URL", "ws://127.0.0.1:1")
        calls = await _dial(monkeypatch, [(PolymarketWebSocket(), _ids(5))])
        assert calls and all(kwargs["ssl"] is None for _, kwargs in calls)
        assert fresh_context == []
