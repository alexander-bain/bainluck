"""#1280: durability tests for the ``refresh_open_commentary`` background task.

The pure helpers are covered in ``test_golf_commentary.py``. This file covers the
async task body — the exact failure modes that crashed the background worker:
a hung provider, a slow aggregation, a generation timeout, partial/cancelled
work, and clean DB-session cleanup — plus the eligibility self-suppression that
stops the expensive Open aggregation from running every 3 minutes off-tournament.

Every failure path must degrade to an honest skip (never a raised soft-limit that
retries and re-wedges the worker), and healthy runs must still generate.
"""

import asyncio
import time

import pytest

from app.tasks import golf_commentary as task
from app.utils.golf_commentary import OPEN_SLUG, commentary_redis_key


class _FakeRedis:
    """Minimal sync Redis stand-in (TTL-agnostic get/setex/delete)."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def get(self, key):
        v = self.store.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_rc(monkeypatch):
    rc = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: rc, raising=True
    )
    # Default: a golf tournament IS live (the off-Open grind condition #1280).
    monkeypatch.setattr(
        "app.tasks.datagolf._golf_inplay_window_active", lambda _rc: True, raising=True
    )
    return rc


def _envelope(status, name="The Open Championship", competitors=None):
    return {
        "event": {"name": name, "status": status, "as_of": "2026-07-19T15:00:00Z"},
        "primary": {"competitors": competitors or []},
    }


def _patch_build(monkeypatch, envelope=None, *, sleep=None, raises=None):
    async def _fake_build():
        if sleep is not None:
            await asyncio.sleep(sleep)
        if raises is not None:
            raise raises
        return envelope

    monkeypatch.setattr(task, "_build_open_envelope", _fake_build, raising=True)


# ---------------------------------------------------------------------------
# Eligibility — cheap skips that never touch the expensive build
# ---------------------------------------------------------------------------


def test_no_active_window_skips_before_build(fake_rc, monkeypatch):
    monkeypatch.setattr(
        "app.tasks.datagolf._golf_inplay_window_active", lambda _rc: False, raising=True
    )
    # If the build runs at all this fails loudly.
    _patch_build(monkeypatch, raises=AssertionError("build must not run"))
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "no_active_tournament_window"}


def test_suppress_latch_skips_expensive_build(fake_rc, monkeypatch):
    fake_rc.store[task._OPEN_SUPPRESS_KEY] = "1"
    _patch_build(monkeypatch, raises=AssertionError("build must not run when suppressed"))
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "open_not_eligible_cached"}


def test_settled_clears_box_and_sets_suppress(fake_rc, monkeypatch):
    key = commentary_redis_key(OPEN_SLUG)
    fake_rc.store[key] = "stale blurb"
    _patch_build(monkeypatch, envelope=_envelope("settled"))
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "status_settled"}
    assert key not in fake_rc.store  # box cleared
    assert fake_rc.store.get(task._OPEN_SUPPRESS_KEY) == "1"  # latched


def test_no_envelope_sets_suppress(fake_rc, monkeypatch):
    _patch_build(monkeypatch, envelope=None)
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "no_envelope"}
    assert fake_rc.store.get(task._OPEN_SUPPRESS_KEY) == "1"


# ---------------------------------------------------------------------------
# Bounded inner operations — degrade honestly, never raise / crash the worker
# ---------------------------------------------------------------------------


def test_build_timeout_degrades_without_suppress_or_clearing(fake_rc, monkeypatch):
    key = commentary_redis_key(OPEN_SLUG)
    fake_rc.store[key] = "existing blurb"
    monkeypatch.setattr(task, "_BUILD_TIMEOUT_S", 0.05, raising=True)
    _patch_build(monkeypatch, envelope=_envelope("live"), sleep=0.5)
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "build_timeout", "degraded": True}
    # A transient slow build must NOT be read as "tournament over": box preserved,
    # suppress NOT latched (so we retry next cycle).
    assert key in fake_rc.store
    assert task._OPEN_SUPPRESS_KEY not in fake_rc.store


def test_build_error_degrades(fake_rc, monkeypatch):
    _patch_build(monkeypatch, raises=RuntimeError("db exploded"))
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "build_error", "degraded": True}


def test_generation_timeout_degrades(fake_rc, monkeypatch):
    monkeypatch.setattr(task, "_GENERATE_TIMEOUT_S", 0.05, raising=True)
    _patch_build(monkeypatch, envelope=_envelope("live", competitors=[{"name": "X"}]))

    def _hung_provider(name, competitors, status):  # runs in a worker thread
        time.sleep(0.5)
        return "too late"

    monkeypatch.setattr(task, "generate_commentary", _hung_provider, raising=True)
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "commentary_timeout", "degraded": True}


def test_generation_returning_none_degrades_to_no_box(fake_rc, monkeypatch):
    key = commentary_redis_key(OPEN_SLUG)
    _patch_build(monkeypatch, envelope=_envelope("live", competitors=[{"name": "X"}]))
    monkeypatch.setattr(
        task, "generate_commentary", lambda *a, **k: None, raising=True
    )
    out = asyncio.run(task._refresh_open_commentary())
    assert out == {"skipped": "no_commentary_generated"}
    assert key not in fake_rc.store  # no broken/empty box written


def test_live_run_generates_and_writes_box(fake_rc, monkeypatch):
    key = commentary_redis_key(OPEN_SLUG)
    _patch_build(
        monkeypatch,
        envelope=_envelope("live", competitors=[{"name": "Scottie", "probability": 0.4}]),
    )
    monkeypatch.setattr(
        task, "generate_commentary", lambda *a, **k: "Scottie is charging.", raising=True
    )
    out = asyncio.run(task._refresh_open_commentary())
    assert out["generated"] is True
    assert key in fake_rc.store
    # A healthy live run must NOT latch suppress (it keeps refreshing every cycle).
    assert task._OPEN_SUPPRESS_KEY not in fake_rc.store


# ---------------------------------------------------------------------------
# Cancellation cleanup — a cancelled build closes its DB session (no leak)
# ---------------------------------------------------------------------------


def test_build_cancellation_closes_db_session(monkeypatch):
    """A build that overruns is cancelled by wait_for; the async-with must still
    run __aexit__ so the DB connection is returned to the pool."""
    closed = {"aexit": False}

    class _FakeSession:
        pass

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeSession()

        async def __aexit__(self, *a):
            closed["aexit"] = True
            return False

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", lambda: _FakeCtx(), raising=True)

    class _SlowAdapter:
        async def build_event(self, slug, db):
            await asyncio.sleep(0.5)
            return {}

    monkeypatch.setattr(
        "app.utils.event_concept.GolfEventAdapter", _SlowAdapter, raising=True
    )

    async def _run():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task._build_open_envelope(), timeout=0.05)

    asyncio.run(_run())
    assert closed["aexit"] is True
