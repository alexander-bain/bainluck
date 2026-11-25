"""#13673: half-hourly catalog refresh must not self-cancel DNPL price updates."""

from __future__ import annotations

import ast
import asyncio
import inspect
from contextlib import asynccontextmanager

import pytest

from app.tasks import polymarket_open_contracts as catalog
from app.tasks import polymarket_ws as pm
from tests.test_pm_price_statement_deadline_10090 import configured_writer


async def test_reading_catalog_widens_refresh_window_and_clears_on_exception(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(pm.time, "monotonic", lambda: now[0])
    boundary = pm._PMCatalogFlushBoundary()
    assert not boundary.refreshing_catalog

    async with boundary.reading_catalog(grace_s=10.0):
        assert boundary.refreshing_catalog
        now[0] = 105.0
        assert boundary.refreshing_catalog

    # Stays True through the short post-handover settle window, then reverts.
    assert boundary.refreshing_catalog
    now[0] = 114.9
    assert boundary.refreshing_catalog
    now[0] = 115.0
    assert not boundary.refreshing_catalog

    with pytest.raises(RuntimeError, match="boom"):
        async with boundary.reading_catalog(grace_s=0.0):
            assert boundary.refreshing_catalog
            raise RuntimeError("boom")
    assert not boundary.refreshing_catalog


def test_statement_timeout_backoff_progression():
    assert pm._statement_timeout_backoff_seconds(0) == 0.0
    assert pm._statement_timeout_backoff_seconds(1) == 0.0
    assert pm._statement_timeout_backoff_seconds(2) == 0.25
    assert pm._statement_timeout_backoff_seconds(3) == 0.5
    assert pm._statement_timeout_backoff_seconds(4) == 1.0
    assert pm._statement_timeout_backoff_seconds(5) == pm.PRICE_FLUSH_SECONDS
    assert pm._statement_timeout_backoff_seconds(9) == pm.PRICE_FLUSH_SECONDS


async def test_write_chunk_widens_budget_during_refresh_and_backs_off_repeated_timeouts(
    monkeypatch,
):
    now = [1000.0]
    r, _state, _events = configured_writer(monkeypatch, "timeout")
    monkeypatch.setattr("app.tasks.live_blend_refresh._mono", lambda: now[0])
    monkeypatch.setattr(pm.time, "monotonic", lambda: now[0])
    armed_ms: list[str] = []
    factory = r.ns["get_task_session"]

    @asynccontextmanager
    async def recording_sessions():
        async with factory() as session:
            orig_execute = session.execute

            async def record(stmt, params=None):
                if stmt is pm.ARM_LOCK_AND_DNPL_PRICE_STATEMENT_TIMEOUT_SQL:
                    armed_ms.append(params["ms"])
                    return type("R", (), {"scalar_one": staticmethod(lambda: "2s")})()
                return await orig_execute(stmt, params)

            session.execute = record
            yield session

    r.ns["get_task_session"] = recording_sessions
    boundary = r.ns["catalog_boundary"]

    # During active refresh: 1500ms budget is armed; strike 1 keeps 0 cooldown.
    async with boundary.reading_catalog(grace_s=0.0):
        assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert armed_ms == ["1500ms"]
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}

    # Outside refresh: reverts to 250ms; strike 2 arms 0.25s backoff, strike 3 arms 0.5s.
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert armed_ms == ["1500ms", "250ms"]
    assert r.ns["lock_retry_until"][1] == pytest.approx(1000.25)

    now[0] = 1000.3
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert r.ns["lock_retry_until"][1] == pytest.approx(1000.8)

    # A clean commit clears strike counts so a later timeout starts fresh at 0 cooldown.
    r_ok, _s_ok, _e_ok = configured_writer(monkeypatch, None)
    now[0] = 1001.0
    monkeypatch.setattr("app.tasks.live_blend_refresh._mono", lambda: now[0])
    r.ns["get_task_session"] = r_ok.ns["get_task_session"]
    wrote = await r.ns["write_chunk"]({1: 0.6, 2: 0.4})
    assert wrote.written_ids == (1, 2)
    assert r.ns["lock_retry_until"] == {}

    r.ns["get_task_session"] = recording_sessions
    assert await r.ns["write_chunk"]({1: 0.6, 2: 0.4}) is None
    assert r.ns["lock_retry_until"] == {1: 0, 2: 0}


async def test_read_open_contracts_releases_session_and_pauses_between_chunks(monkeypatch):
    src = inspect.getsource(pm)
    node = next(
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "read_open_contracts"
    )
    events: list[str] = []
    market_rows = [(m, [f"{m}a", f"{m}b"], None, None, None, f"M{m}", f"x{m}") for m in (1, 2, 3)]

    class _Result:
        def __init__(self, found):
            self._found = found

        def all(self):
            return self._found

    class _Session:
        async def execute(self, stmt, *args, **kwargs):
            ids = stmt.compile().params.get("market_ids")
            if ids is None:
                events.append("markets")
                return _Result(market_rows)
            events.append(f"outcomes:{list(ids)}")
            return _Result([
                leg
                for m in ids
                for leg in (
                    (m * 10, m, f"0x{m:04x}_yes", False),
                    (m * 10 + 1, m, f"0x{m:04x}_no", False),
                )
            ])

    @asynccontextmanager
    async def session():
        events.append("open_session")
        try:
            yield _Session()
        finally:
            events.append("close_session")

    sleeps: list[float] = []

    async def fake_sleep(delay):
        events.append(f"sleep:{delay}")
        sleeps.append(delay)

    monkeypatch.setattr(catalog, "OUTCOME_READ_MARKETS", 1)
    monkeypatch.setattr(catalog, "OPEN_OUTCOME_CHUNK_PAUSE_S", 0.05)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    ns = {k: getattr(catalog, k) for k in dir(catalog)}
    ns.update(
        open_contract_prices_enabled=lambda: True,
        open_contract_scope=lambda: catalog.OPEN_SCOPE_ALL,
        get_task_session=session,
        open_contract_bridge_event_stmt=lambda *a, **k: None,
        open_contract_event_bridge=lambda *a, **k: {},
    )
    exec(compile(ast.get_source_segment(src, node), inspect.getfile(pm), "exec"), ns)

    admission, failed, bridge, bridge_failed = await ns["read_open_contracts"](set(), set())
    assert not failed and not bridge_failed and bridge == {}
    assert len(admission.asset_to_outcome) == 6
    assert sleeps == [0.05, 0.05]
    # Sessions must close BEFORE sleeping so pooled connections return to live writers.
    assert events == [
        "open_session",
        "markets",
        "close_session",
        "open_session",
        "outcomes:[1]",
        "close_session",
        "sleep:0.05",
        "open_session",
        "outcomes:[2]",
        "close_session",
        "sleep:0.05",
        "open_session",
        "outcomes:[3]",
        "close_session",
    ]
