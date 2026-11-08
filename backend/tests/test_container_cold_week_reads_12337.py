"""Compact card reads overlap references and join their session on every exit."""

from __future__ import annotations

import asyncio
from builtins import ExceptionGroup
from contextlib import asynccontextmanager

import pytest

from app.routes import containers as route
from app.routes import events as event_route
from app.services import database
from tests.test_container_hydrated_reader_9636 import _Session, _nfl_week


@pytest.fixture(autouse=True)
def empty_reference_caches(monkeypatch):
    monkeypatch.setattr(event_route, "_ei_cache", {})
    monkeypatch.setattr(event_route, "_team_cache", {})


async def test_concurrent_cards_equal_the_sequential_cards_and_use_a_separate_session(monkeypatch):
    hub, events, markets = _nfl_week()
    event_ids = [event.id for event in events]
    reference_started = asyncio.Event()
    odds_finished = asyncio.Event()
    closed = asyncio.Event()
    sessions = []

    class ReferenceSession(_Session):
        async def execute(self, sql, params=None):
            reference_started.set()
            await asyncio.wait_for(odds_finished.wait(), timeout=5)
            return await super().execute(sql, params)

    @asynccontextmanager
    async def references():
        session = ReferenceSession()
        sessions.append(session)
        try:
            yield session
        finally:
            closed.set()

    monkeypatch.setattr(database, "async_session_maker", references)
    baseline = await route._hydrate_event_cards(
        _Session(hub, events=events, markets=markets), event_ids
    )
    assert sessions == []

    class MainSession(_Session):
        async def execute(self, sql, params=None):
            if "odds_bookmakers" in str(sql):
                await asyncio.wait_for(reference_started.wait(), timeout=5)
                odds_finished.set()
            return await super().execute(sql, params)

    main = MainSession(hub, events=events, markets=markets)
    concurrent = await route._hydrate_event_cards(
        main, event_ids, concurrent_references=True
    )

    assert concurrent == baseline
    assert len(sessions) == 1
    assert sessions[0] is not main
    assert closed.is_set()
    assert reference_started.is_set() and odds_finished.is_set()


async def test_a_failed_main_read_cancels_and_closes_the_reference_session(monkeypatch):
    hub, events, markets = _nfl_week()
    reference_started = asyncio.Event()
    reference_cancelled = asyncio.Event()
    closed = asyncio.Event()
    never_finished = asyncio.Event()

    class ReferenceSession(_Session):
        async def execute(self, sql, params=None):
            reference_started.set()
            try:
                await never_finished.wait()
            except asyncio.CancelledError:
                reference_cancelled.set()
                raise

    @asynccontextmanager
    async def references():
        try:
            yield ReferenceSession()
        finally:
            closed.set()

    class MainSession(_Session):
        async def execute(self, sql, params=None):
            if "odds_bookmakers" in str(sql):
                await asyncio.wait_for(reference_started.wait(), timeout=5)
                raise RuntimeError("representative snapshot read failure")
            return await super().execute(sql, params)

    monkeypatch.setattr(database, "async_session_maker", references)
    with pytest.raises(ExceptionGroup) as failure:
        await route._hydrate_event_cards(
            MainSession(hub, events=events, markets=markets),
            [event.id for event in events],
            concurrent_references=True,
        )

    assert any(isinstance(error, RuntimeError) for error in failure.value.exceptions)
    assert reference_cancelled.is_set()
    assert closed.is_set()


async def test_a_failed_reference_read_cancels_the_main_read_and_closes_its_session(monkeypatch):
    hub, events, markets = _nfl_week()
    main_started = asyncio.Event()
    main_cancelled = asyncio.Event()
    closed = asyncio.Event()
    never_finished = asyncio.Event()

    class ReferenceSession(_Session):
        async def execute(self, sql, params=None):
            await asyncio.wait_for(main_started.wait(), timeout=5)
            raise RuntimeError("representative reference read failure")

    @asynccontextmanager
    async def references():
        try:
            yield ReferenceSession()
        finally:
            closed.set()

    class MainSession(_Session):
        async def execute(self, sql, params=None):
            if "odds_bookmakers" in str(sql):
                main_started.set()
                try:
                    await never_finished.wait()
                except asyncio.CancelledError:
                    main_cancelled.set()
                    raise
            return await super().execute(sql, params)

    monkeypatch.setattr(database, "async_session_maker", references)
    with pytest.raises(ExceptionGroup) as failure:
        await route._hydrate_event_cards(
            MainSession(hub, events=events, markets=markets),
            [event.id for event in events],
            concurrent_references=True,
        )

    assert any(isinstance(error, RuntimeError) for error in failure.value.exceptions)
    assert main_cancelled.is_set()
    assert closed.is_set()


async def test_request_cancellation_joins_and_closes_the_reference_session(monkeypatch):
    hub, events, markets = _nfl_week()
    reference_started = asyncio.Event()
    reference_cancelled = asyncio.Event()
    closed = asyncio.Event()
    never_finished = asyncio.Event()

    class ReferenceSession(_Session):
        async def execute(self, sql, params=None):
            reference_started.set()
            try:
                await never_finished.wait()
            except asyncio.CancelledError:
                reference_cancelled.set()
                raise

    @asynccontextmanager
    async def references():
        try:
            yield ReferenceSession()
        finally:
            closed.set()

    class MainSession(_Session):
        async def execute(self, sql, params=None):
            if "odds_bookmakers" in str(sql):
                await never_finished.wait()
            return await super().execute(sql, params)

    monkeypatch.setattr(database, "async_session_maker", references)
    request = asyncio.create_task(
        route._hydrate_event_cards(
            MainSession(hub, events=events, markets=markets),
            [event.id for event in events],
            concurrent_references=True,
        )
    )
    await asyncio.wait_for(reference_started.wait(), timeout=5)
    request.cancel()

    with pytest.raises(asyncio.CancelledError):
        await request

    assert reference_cancelled.is_set()
    assert closed.is_set()
