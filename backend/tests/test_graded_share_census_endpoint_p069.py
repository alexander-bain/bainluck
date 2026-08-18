"""CAL-P069 — the census rail had no caller, and nothing could tell.

CAL-P068 shipped ``run_graded_share_census`` as a bounded, resumable cursor rail
and recorded in its handoff that running it was "one bounded admin call away".
Measured on the branch: the function had **zero callers**. Not an endpoint, not
a Celery task, not a script — reachable only from its own tests.

The reason that survived a full window is the shape this lane keeps meeting. A
selection-bias rule with no denominator reports::

    provability_census: {measured: false, reason: "..."}

which is exactly what it reports while working perfectly against a population
nobody has censused yet. "The rail has never run" and "the rail cannot be run"
produce the same payload, so the second hid behind the first. Gotcha #53, one
level up from the data: not an empty result standing in for a fact, but an
unreachable *mechanism* standing in for an unrun one.

Two kinds of test here, and the second is the one that matters:

* the endpoint behaves — composes with a partial, refuses to silently restart,
  persists an incomplete census while still refusing it as a divisor;
* **the rail is REACHABLE** — a structural assertion that something outside the
  test tree calls it. That is the guard the missing endpoint needed, and it is
  written to catch the next unreachable rail rather than this one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.routes import admin_data_quality as adq

APP_DIR = Path(__file__).parents[1] / "app"


# ── the structural guard: a shipped rail must be reachable ────────────────────


def _names_called_in_app() -> set[str]:
    """Every function name invoked anywhere under ``app/`` (calls + attributes)."""
    called: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — a parse failure is another test's job
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name:
                    called.add(name)
    return called


def test_the_graded_share_census_is_reachable_from_the_application():
    """The defect in one line: a rail only its tests can run has not shipped.

    Deliberately asserted over ``app/`` and not over the test tree, because the
    census WAS covered by 274 lines of passing tests while being dead code in
    production. Test coverage proves a function works; it says nothing about
    whether anything will ever call it.
    """
    assert "run_graded_share_census" in _names_called_in_app(), (
        "run_graded_share_census has no caller under app/ — it is unreachable in "
        "production and the selection-bias rule it feeds can never render"
    )


def test_the_endpoint_that_calls_it_is_mounted_and_is_a_post():
    """Gotcha #2: an admin route that is not mounted is not an endpoint."""
    from app.main import app

    routes = [
        r
        for r in app.routes
        if getattr(r, "path", "") == "/api/admin/calibration/graded-share-census"
    ]
    assert routes, "the census endpoint is not mounted"
    assert "POST" in routes[0].methods


# ── behaviour ─────────────────────────────────────────────────────────────────


class _Redis:
    def __init__(self, initial=None, fail_get=False, fail_set=False):
        self.store = dict(initial or {})
        self.fail_get = fail_get
        self.fail_set = fail_set
        self.ttls: dict[str, int] = {}

    def get(self, key):
        if self.fail_get:
            raise RuntimeError("redis get exploded")
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if self.fail_set:
            raise RuntimeError("redis setex exploded")
        self.store[key] = value
        self.ttls[key] = ttl


CACHE_KEY = "bainluck:calibration:graded_share_census"


@pytest.fixture
def wired(monkeypatch):
    """Patch the gate, the clock-free census and redis; capture the census args."""
    monkeypatch.setattr(adq, "_check_admin_secret", lambda *a, **k: None)

    seen: dict = {}
    redis = _Redis()

    def _install(payload, *, redis_obj=None):
        nonlocal redis
        if redis_obj is not None:
            redis = redis_obj

        async def _census(session, *, max_pages, start_cursor, prior):
            seen.update(
                max_pages=max_pages, start_cursor=start_cursor, prior=prior
            )
            return payload

        import app.tasks.calibration_graded_share as gs
        import app.tasks.redis_state as rs

        monkeypatch.setattr(gs, "run_graded_share_census", _census, raising=False)
        monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: redis, raising=False)
        return redis

    return _install, seen


def _payload(**over):
    base = {
        "by_category": {"hockey": {"total_outcomes": 10, "graded_outcomes": 3}},
        "cursor": 900,
        "exhausted": False,
        "complete": False,
        "usable_as_denominator": False,
        "reason": "census incomplete — pages still pending; ",
        "pages_ok": 2,
        "pages_failed": 0,
        "failed_ranges": [],
        "elapsed_s": 1.0,
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_it_resumes_from_the_persisted_cursor(wired):
    """The whole reason the rail is a cursor: call two continues call one."""
    install, seen = wired
    redis = _Redis({CACHE_KEY: json.dumps(_payload(cursor=400))})
    install(_payload(cursor=900), redis_obj=redis)

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=False, db=object()
    )

    assert seen["start_cursor"] == 400
    assert seen["prior"]["cursor"] == 400
    assert out["resumed_from"] == 400
    assert out["cursor"] == 900


@pytest.mark.asyncio
async def test_reset_discards_the_prior_deliberately(wired):
    """``reset`` exists so restarting is a request, never a side effect."""
    install, seen = wired
    redis = _Redis({CACHE_KEY: json.dumps(_payload(cursor=400))})
    install(_payload(cursor=100), redis_obj=redis)

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=True, db=object()
    )

    assert seen["start_cursor"] == 0
    assert seen["prior"] is None
    assert out["resumed_from"] == 0


@pytest.mark.asyncio
async def test_an_unreadable_prior_refuses_rather_than_restarting_at_zero(wired):
    """Silently restarting would report a SMALLER census as a fresh full one.

    And smaller is the fatal direction: every graded share computed off a short
    denominator is too large, which flips cells from NOT-PROVABLE to provable.
    """
    install, seen = wired
    install(_payload(), redis_obj=_Redis(fail_get=True))

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=False, db=object()
    )

    assert out["status"] == "error"
    assert out["stage"] == "read_prior"
    assert "reset=true" in out["hint"]
    assert not seen, "the census must not run when its prior could not be read"


@pytest.mark.asyncio
async def test_an_incomplete_census_is_persisted_but_still_refused_as_a_divisor(wired):
    """Both halves matter, and they pull in opposite directions.

    Persisted, or the next call cannot resume. Refused, or a partial denominator
    reaches the page. ``usable_as_denominator`` is the field that lets one
    artifact do both.
    """
    install, _ = wired
    redis = install(_payload(), redis_obj=_Redis())

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=False, db=object()
    )

    assert out["status"] == "ok"
    assert out["usable_as_denominator"] is False
    assert out["reason"]
    stored = json.loads(redis.store[CACHE_KEY])
    assert stored["cursor"] == 900
    assert stored["usable_as_denominator"] is False
    assert redis.ttls[CACHE_KEY] == 14 * 24 * 3600


@pytest.mark.asyncio
async def test_a_complete_census_says_so_and_stops_advertising_a_next_call(wired):
    """The other direction (gotcha #43) — the success path must be reachable too."""
    install, _ = wired
    install(
        _payload(exhausted=True, complete=True, usable_as_denominator=True, reason=None),
        redis_obj=_Redis(),
    )

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=False, db=object()
    )

    assert out["complete"] is True
    assert out["usable_as_denominator"] is True
    assert out["next_call"] is None


@pytest.mark.asyncio
async def test_a_failed_write_is_not_reported_as_ok(wired):
    """A census that computed and did not persist is not a census (gotcha #53).

    Reported as ``computed_not_persisted`` rather than ``ok``, because the next
    call would otherwise resume from a cursor that was never stored and quietly
    re-walk the same range while believing it had advanced.
    """
    install, _ = wired
    install(_payload(), redis_obj=_Redis(fail_set=True))

    out = await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=5, reset=False, db=object()
    )

    assert out["status"] == "computed_not_persisted"
    assert out["artifact_write"].startswith("failed:")


@pytest.mark.asyncio
async def test_the_bound_the_operator_asked_for_is_the_bound_that_runs(wired):
    """An attended rail whose limit is ignored is an unattended rail."""
    install, seen = wired
    install(_payload(), redis_obj=_Redis())

    await adq.run_calibration_graded_share_census(
        request=None, secret="x", max_pages=7, reset=False, db=object()
    )

    assert seen["max_pages"] == 7
