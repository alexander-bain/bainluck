"""#12335 step 2: one title market's verified-title verdict is kept briefly and shared.

THE SHIP. The NFL title page (`/futures/<id>`, `representation=verified_title`)
recomposed its blend on every read — measured on production just after midnight
PT on Nov 8 at 16.1 s cold, then 3.0, 1.2, 1.1 s — and since #12342 the Search
card for the same market composes it too. One verdict per market now serves
every reader for `VERIFIED_TITLE_CACHE_SECONDS` (60 s by default): the page,
its chart's current column and the Search card read the same numbers and pay
the composition once a minute instead of once a view.
"""

import asyncio
from types import SimpleNamespace

import pytest

import app.routes.futures as futures_mod
from app.utils.futures_verified_title import Composition, Refusal


def _verdict(tag):
    return Composition(question_identity={"tag": tag}, overlay={}, contributing_sources=["kalshi"])


@pytest.fixture
def composer(monkeypatch):
    calls = []

    async def _compose(db, market):
        calls.append(market.id)
        await asyncio.sleep(0)
        return _verdict(len(calls))

    monkeypatch.setattr(futures_mod, "_compose_verified_title", _compose)
    futures_mod._VERIFIED_TITLE_CACHE.clear()
    yield calls
    futures_mod._VERIFIED_TITLE_CACHE.clear()


@pytest.mark.asyncio
async def test_a_second_reader_inside_the_window_gets_the_same_verdict_without_recomposing(
    composer, monkeypatch
):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    m = SimpleNamespace(id=129037)
    first = await futures_mod._resolve_verified_title(None, m)
    second = await futures_mod._resolve_verified_title(None, m)
    assert first is second
    assert composer == [129037]


@pytest.mark.asyncio
async def test_an_expired_verdict_is_recomposed(composer, monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    m = SimpleNamespace(id=129037)
    first = await futures_mod._resolve_verified_title(None, m)
    exp, verdict = futures_mod._VERIFIED_TITLE_CACHE[129037]
    futures_mod._VERIFIED_TITLE_CACHE[129037] = (exp - 120, verdict)
    second = await futures_mod._resolve_verified_title(None, m)
    assert first is not second
    assert composer == [129037, 129037]


@pytest.mark.asyncio
async def test_markets_do_not_share_a_verdict(composer, monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    a = await futures_mod._resolve_verified_title(None, SimpleNamespace(id=1))
    b = await futures_mod._resolve_verified_title(None, SimpleNamespace(id=2))
    assert a is not b
    assert composer == [1, 2]


@pytest.mark.asyncio
async def test_zero_turns_it_off(composer, monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "0")
    m = SimpleNamespace(id=129037)
    await futures_mod._resolve_verified_title(None, m)
    await futures_mod._resolve_verified_title(None, m)
    assert composer == [129037, 129037]
    assert futures_mod._VERIFIED_TITLE_CACHE == {}


def test_the_test_suite_runs_with_it_off():
    """conftest's autouse default — rigs reuse market ids with different boards."""
    assert futures_mod._verified_title_cache_seconds() == 0


@pytest.mark.asyncio
async def test_a_resolver_error_is_never_kept(monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    futures_mod._VERIFIED_TITLE_CACHE.clear()
    calls = []

    async def _boom(db, market):
        calls.append(1)
        raise RuntimeError("db went away")

    monkeypatch.setattr(futures_mod, "_compose_verified_title", _boom)
    m = SimpleNamespace(id=129037)
    first = await futures_mod._resolve_verified_title(None, m)
    second = await futures_mod._resolve_verified_title(None, m)
    assert isinstance(first, Refusal) and first.reason == "resolver_error"
    assert isinstance(second, Refusal)
    assert calls == [1, 1], "a failure was cached; the next reader must retry"
    assert 129037 not in futures_mod._VERIFIED_TITLE_CACHE


@pytest.mark.asyncio
async def test_the_map_cannot_grow_past_its_bound(composer, monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "60")
    monkeypatch.setattr(futures_mod, "_VERIFIED_TITLE_CACHE_MAX", 3)
    for i in range(10):
        await futures_mod._resolve_verified_title(None, SimpleNamespace(id=i))
    assert len(futures_mod._VERIFIED_TITLE_CACHE) <= 3


def test_a_bad_setting_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("VERIFIED_TITLE_CACHE_SECONDS", "soon")
    assert futures_mod._verified_title_cache_seconds() == 60.0
