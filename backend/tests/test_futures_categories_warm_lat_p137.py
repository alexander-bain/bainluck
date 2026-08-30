"""The Search page's category grid stops being built by whoever opens Search.
LAT-P137.

WHY THIS FILE EXISTS.

`/search` renders `CategoryBrowser` (`frontend/app/search/page.tsx:355`), whose
first act on mount is `fetchFuturesCategories()`. LAT-P122 measured that census
at 1,585.9 ms and 1,365.1 ms on two consecutive production reads, gave it a
shared Redis slot plus a 24 h age-bounded mirror, and took the cost off the
second reader. It gave the tier **no producer**: nothing on the fleet rebuilds
the census, so the mirror's serve ceiling — 25 minutes — is the only thing
standing between a visitor and the full 39,014-block scan.

Measured again on production slug `fe5ec72c`, 2026-08-30, this queue's own read:

    00:41:37Z  wall=1365.4; db=1330.7; q=1     <- mirror past its ceiling
    00:50:08Z  wall=28.0;   db=0.0;    q=0     <- mirror serve, same payload
    00:50:11Z  wall=23.8;   db=0.0;    q=0

Both fast reads carry `created_at: 00:41:37`, which is the finding in one line:
one person paid 1.4 s so the next few got 28 ms, and nothing was scheduled to
pay it instead of them.

WHAT THIS FILE ASSERTS, AND WHY EACH ONE IS HERE.

1. **The warmer writes the slot the ROUTE reads.** This is the failure mode of
   every warmer and it is invisible from either side alone: a producer that
   publishes into a key the consumer does not read warms nothing, raises nothing
   and reports success. Proven by making the database FATAL on the read path
   after a warm — the only way to know the hit came from the warm and not from a
   rebuild that happened to be quick.
2. **The period is DERIVED from the tier's own stale-serve ceiling**, not typed
   beside it. #2236 is the incident where a 120 in one file and a 60 in another,
   with nothing comparing them, left a payload uncovered for a full minute of
   every two. If a later queue shortens the ceiling — it is a FRESHNESS
   contract, those counts are printed to the user — the cadence must follow it
   down rather than quietly stop covering the gap.
3. **The beat spells the derived period**, names its queue, and expires. A
   derivation that the schedule does not actually use is a comment.
4. **A pass that published nothing reads `failed`, never green** (gotcha #53),
   including the two cases a warmer confuses: the build raised, and the build
   returned but the write did not land. `complete` requires a `created_at` THIS
   run put there.
5. **The warmer never raises**, whatever the build, the clock or Redis does. A
   beat that dies takes its next fire with it.
6. **The census is spelled once.** The warmer calls the route's own rebuild, so
   the bytes it publishes and the bytes a reader's rebuild publishes cannot
   drift; a copy of the statement in the task module would pass every other test
   in this file.
"""

from __future__ import annotations

import asyncio
import inspect
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import futures as futures_route
from app.tasks import futures_categories_warm as warm
from app.utils import event_concept_cache as concept_cache
from app.utils import futures_categories_cache as fcc


# ---------------------------------------------------------------------------
# Fixtures: the same in-memory Redis the tier's own suite uses
# ---------------------------------------------------------------------------


class _FakeRedis:
    """In-memory Redis: get / setex / set / delete / eval over a dict.

    TTLs are RECORDED rather than enforced — a test that needed a key to expire
    would have to sleep, and a gate that sleeps is a gate that flakes.
    """

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)

    def eval(self, _script, _numkeys, key, arg):
        held = self.store.get(key)
        if held is not None and held.decode() == arg:
            del self.store[key]
            self.ttls.pop(key, None)
            return 1
        return 0


class _Row:
    def __init__(self, key, count):
        self.llm_sport_category = key
        self.count = count


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CountingSession:
    """An `AsyncSession` stand-in that counts the statements it ran.

    The whole ship is "who runs the 39,014-block statement", so the instrument
    is a counter, not a clock.
    """

    def __init__(self):
        self.executions = 0

    async def execute(self, _query):
        self.executions += 1
        return _Result([_Row("politics", 6581), _Row("economics", 2898), _Row(None, 123)])


class _FatalSession:
    """A session that fails the test if anything runs a statement on it."""

    async def execute(self, _query):  # pragma: no cover - the assertion IS the point
        raise AssertionError("the read path ran the census statement")


@contextmanager
def _client(rc):
    """Make `rc` the tier's default client.

    BOTH names are patched, and that is not belt-and-braces: `futures_
    categories_cache` does `from ... import get_client`, so it holds its own
    reference, and patching only `event_concept_cache.get_client` leaves the
    tier reading the real Redis while the test believes it is isolated.
    """
    with patch.object(fcc, "get_client", return_value=rc), patch.object(
        concept_cache, "get_client", return_value=rc
    ):
        yield rc


@contextmanager
def _session_maker(session):
    """Point the warmer's WORKER session factory at `session`.

    `app.tasks.base.get_task_session`, not `services.database.async_session_maker`
    — and the distinction is the ship's own bug report. The first draft of the
    warmer called the route's `_rebuild_futures_categories`, which opens the
    module-level session maker bound to the web process's loop; a Celery task
    that reuses it earns the "attached to a different loop" failures
    `app/tasks/base.py` exists to prevent. Patching the name the task actually
    uses is what makes this suite able to notice a regression back to it.
    """

    class _Maker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    import app.tasks.base as task_base

    with patch.object(task_base, "get_task_session", _Maker()):
        yield session


def _run(coro):
    return asyncio.run(coro)


def _stamped(*, age_s: float = 0.0) -> dict:
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return fcc.stamp({"categories": [{"key": "politics", "count": 6581}], "total": 6581},
                     created_at=created)


# ---------------------------------------------------------------------------
# 1. The warmer writes the slot the ROUTE reads
# ---------------------------------------------------------------------------


def test_a_warmed_census_is_served_without_touching_the_database():
    """The end-to-end claim, and the only one that can catch a key mismatch.

    A producer publishing into a slot the consumer does not read warms nothing
    and reports success, so the reader's session is FATAL here: any statement at
    all on the request path means the warm did not cover it.
    """
    rc = _FakeRedis()
    build = _CountingSession()

    async def _go():
        with _client(rc), _session_maker(build):
            summary = await warm._warm_futures_categories(rc)
            body = await futures_route.list_futures_categories(db=_FatalSession())
        return summary, body

    summary, body = _run(_go())

    assert build.executions == 1, "the warm did not run the census exactly once"
    assert summary["terminal"] == "complete"
    assert body["cache"]["availability"] == fcc.AVAILABILITY_LIVE
    assert body["categories"][0]["key"] == "politics"


def test_the_warm_writes_the_primary_at_the_tiers_own_fresh_ttl():
    """A producer TTL and a reader TTL answering different questions is a real
    pattern (LAT-P115), but this tier is not that case: the warm publishes
    through the route's own writer, so a different TTL here could only mean the
    writer was bypassed."""
    rc = _FakeRedis()

    async def _go():
        with _client(rc), _session_maker(_CountingSession()):
            await warm._warm_futures_categories(rc)

    _run(_go())

    assert rc.ttls[fcc.keys().primary] == fcc.FRESH_TTL


# ---------------------------------------------------------------------------
# 2. The period is derived from the ceiling it exists to cover
# ---------------------------------------------------------------------------


def test_the_period_is_derived_from_the_tiers_stale_serve_ceiling():
    """`ceiling / (allowance + 1)`, so `MISSED_DELIVERY_ALLOWANCE` consecutive
    lost deliveries still leave the mirror servable."""
    ceiling = fcc.stale_serve_ceiling_seconds()

    assert warm.warm_period_seconds() == ceiling // (warm.MISSED_DELIVERY_ALLOWANCE + 1)
    assert warm.warm_period_seconds() * (warm.MISSED_DELIVERY_ALLOWANCE + 1) <= ceiling


def test_shortening_the_ceiling_shortens_the_cadence():
    """The property the derivation exists for. A literal period would sail past
    a tightened freshness contract without a single test going red."""
    with patch.object(fcc, "STALE_SERVE_CEILING", 2):
        tightened = warm.warm_period_seconds()

    assert tightened < warm.warm_period_seconds()
    assert tightened == (2 * fcc.FRESH_TTL) // (warm.MISSED_DELIVERY_ALLOWANCE + 1)


def test_the_period_is_a_whole_number_of_minutes_that_divides_an_hour():
    """The beat spells `*/N`, so a period of, say, seven minutes would fire at
    :00 and :07 ... :56 and then :00 again — a silently uneven cadence with a
    13-minute hole in it, which no assertion on the number alone would catch."""
    period = warm.warm_period_seconds()

    assert period % 60 == 0, f"period {period}s is not whole minutes"
    assert 60 % warm.warm_period_minutes() == 0, (
        f"*/{warm.warm_period_minutes()} does not divide an hour evenly"
    )
    assert warm.warm_period_minutes() == period // 60


# ---------------------------------------------------------------------------
# 3. The beat uses the derivation
# ---------------------------------------------------------------------------


def test_the_beat_spells_the_derived_period_names_its_queue_and_expires():
    """A derivation the schedule does not use is a comment."""
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-futures-categories"]

    assert entry["task"] == "app.tasks.warm_futures_categories"
    assert entry["options"]["queue"] == "background"
    assert entry["options"]["expires"] == warm.warm_period_seconds()
    # `crontab.minute` is the EXPANDED set, which is the honest thing to compare:
    # `*/5` and `0,5,10,...` are the same schedule, and a test that compared the
    # spelling would pass a period that fires at the wrong minutes.
    assert entry["schedule"].minute == set(range(0, 60, warm.warm_period_minutes()))


def test_the_task_is_registered_and_enrolled_in_the_verdict_contract():
    """Enrolment without a terminal is a no-op, and a terminal without enrolment
    is unread. Both halves, asserted together."""
    from app.tasks import celery_app
    from app.utils.task_verdict import ENFORCED_TASKS, verdict_for

    assert "app.tasks.warm_futures_categories" in celery_app.tasks
    assert "warm_futures_categories" in ENFORCED_TASKS

    green = verdict_for("warm_futures_categories", {"terminal": "complete"})
    red = verdict_for("warm_futures_categories", {"terminal": "failed"})

    assert green.authoritative and red.authoritative
    assert green.verdict != red.verdict


# ---------------------------------------------------------------------------
# 4. A pass that published nothing reads failed, never green
# ---------------------------------------------------------------------------


def test_a_build_that_raises_reads_failed_and_does_not_propagate():
    """A warmer that dies takes its next fire's slot with it, and a beat is not
    a place to raise."""
    rc = _FakeRedis()

    async def _boom(_db):
        raise RuntimeError("the census statement was cancelled")

    async def _go():
        with _client(rc), _session_maker(_CountingSession()), patch.object(
            futures_route, "_build_futures_categories", _boom
        ):
            return await warm._warm_futures_categories(rc)

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert summary["error"] == "error"


def test_a_build_that_hangs_is_bounded_and_reads_failed_with_a_reason():
    """The inner op is bounded so a wedged build is REPORTED, rather than killed
    by the task limit with nothing to say about it."""
    rc = _FakeRedis()

    async def _hang(_db):
        # Five seconds, not sixty: with the bound in place this sleep is never
        # reached past 10 ms, and the number is only paid by the mutation run
        # that DELETES the bound — where it is the harness's own wall.
        await asyncio.sleep(5)

    async def _go():
        with _client(rc), _session_maker(_CountingSession()), patch.object(
            futures_route, "_build_futures_categories", _hang
        ), patch.object(warm, "BUILD_TIMEOUT_SECONDS", 0.01):
            return await warm._warm_futures_categories(rc)

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["error"] == "timeout"


def test_a_build_whose_write_was_swallowed_reads_failed():
    """`write()` reports that a client took the bytes, never that Redis kept
    them. A run that left the PREVIOUS census readable published nothing, and
    grading that green is how a warmer rots while the surface it protects stays
    200."""
    rc = _FakeRedis()
    fcc.write(_stamped(age_s=30), rc=rc)

    def _write_nothing(response):
        return response

    async def _go():
        with _client(rc), _session_maker(_CountingSession()), patch.object(
            futures_route, "_publish_futures_categories", _write_nothing
        ):
            return await warm._warm_futures_categories(rc)

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["published"] is False
    assert summary["previous_created_at"] == summary["created_at"], (
        "the census changed, so this test proved nothing"
    )


def test_complete_requires_a_created_at_this_run_wrote():
    """Not "a census exists" — "a census this run published exists". The two
    differ exactly when the warmer has stopped working."""
    rc = _FakeRedis()
    fcc.write(_stamped(age_s=120), rc=rc)
    before = warm._census_created_at(rc)

    async def _go():
        with _client(rc), _session_maker(_CountingSession()):
            return await warm._warm_futures_categories(rc)

    summary = _run(_go())

    assert summary["terminal"] == "complete"
    assert summary["previous_created_at"] == before
    assert summary["created_at"] != before


def test_no_redis_at_all_reads_failed_rather_than_raising():
    """A cache that cannot be reached must cost the reader a rebuild — today's
    behaviour — and must cost the beat a red line, not a traceback."""

    async def _go():
        with _client(None), _session_maker(_CountingSession()):
            return await warm._warm_futures_categories(None)

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["published"] is False


def test_a_census_read_that_raises_is_a_warm_reason_and_not_a_crash():
    """`_census_created_at` is called before AND after the build, so a read that
    raises would otherwise kill the pass from either side of it.

    🔴 THIS TEST WAS REWRITTEN BY ITS OWN MUTANT. The first version made the
    Redis client's `get` raise and asserted no crash — and M7, which narrows the
    guard to `except AssertionError`, SURVIVED it. The reason is worth keeping:
    the tier's `read()` goes through `read_slot`, which is best-effort by
    construction and swallows a raising client itself, so the client could never
    reach this module's guard at all. The test proved the tier's swallow, not
    this one. Driving `fcc.read` directly is the only way to exercise the
    failure this except clause is actually for — a future read path that stops
    swallowing.
    """

    def _explode(_rc=None):
        raise RuntimeError("connection reset")

    async def _go():
        with patch.object(fcc, "read", _explode), _session_maker(_CountingSession()):
            return await warm._warm_futures_categories(_FakeRedis())

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["error"] is None, "the build itself was fine; only the read failed"


def test_a_redis_that_raises_on_get_is_already_swallowed_by_the_tier():
    """The other half of the pair above, kept so the boundary is written down:
    a raising CLIENT never reaches this module, because `read_slot` handles it.
    A later change that removes that swallow makes this test the one that
    notices."""

    class _Exploding(_FakeRedis):
        def get(self, k):
            raise RuntimeError("connection reset")

    async def _go():
        with _client(_Exploding()), _session_maker(_CountingSession()):
            return await warm._warm_futures_categories(_Exploding())

    summary = _run(_go())

    assert summary["terminal"] == "failed"
    assert summary["published"] is False


# ---------------------------------------------------------------------------
# 5. The census is spelled once
# ---------------------------------------------------------------------------


def test_the_warmer_holds_no_copy_of_the_census_statement():
    """It calls the route's own builder and publisher, so the warmed bytes and
    the reader's bytes cannot drift. A second copy of the query here would pass
    every other test in this file and then rot on the first predicate change."""
    source = inspect.getsource(warm)

    assert "_build_futures_categories" in source
    assert "_publish_futures_categories" in source
    for forbidden in ("FuturesMarket", "group_by", "ilike", "select("):
        assert forbidden not in source, (
            f"the warmer spells its own census ({forbidden!r}) instead of calling the route's"
        )


def test_the_warmer_opens_a_WORKER_session_and_not_the_web_processs():
    """🔴 THIS TEST IS A BUG REPORT AGAINST THIS SHIP'S OWN FIRST DRAFT.

    That draft called `routes.futures._rebuild_futures_categories`, which is the
    route's serve-stale dispatch and opens `services.database.async_session_maker`
    — the module-level maker bound to the WEB process's event loop. Reusing it
    from a Celery task is what `app/tasks/base.get_task_session` exists to
    prevent ("attached to a different loop"), and it is the shape every other
    worker-side rebuild in this repo already uses (`refresh_league`).

    Nothing else in this file could have caught it: with the session patched out,
    both spellings pass every behavioural assertion here and the failure appears
    only on a real worker.

    🔴 READ OUT OF THE AST, NOT OUT OF THE TEXT. The module's docstring NAMES
    the helper it must not call, in the paragraph explaining why — so a
    substring test would fail on the explanation and pass on a rewrite that
    deleted it. What is asserted is what the module IMPORTS.
    """
    import ast

    source = inspect.getsource(warm)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "get_task_session" in imported
    assert "async_session_maker" not in imported
    assert "_rebuild_futures_categories" not in imported, (
        "the warmer is back on the route's web-loop rebuild helper"
    )
    assert {"_build_futures_categories", "_publish_futures_categories"} <= imported


def test_the_warmer_publishes_through_the_routes_own_writer():
    """Same claim from the other side: whatever the warm writes must be exactly
    what a cold reader's own build would have written, envelope included."""
    rc = _FakeRedis()

    async def _go():
        with _client(rc), _session_maker(_CountingSession()):
            await warm._warm_futures_categories(rc)
            warmed, state = fcc.read(rc)
        return warmed, state

    warmed, state = _run(_go())

    assert state == "live"
    assert warmed["cache"]["created_at"]
    assert warmed["cache"]["lifecycle_watermark"] is None
    assert warmed["total"] == 6581 + 2898 + 123


@pytest.mark.parametrize("attr", ["BUILD_TIMEOUT_SECONDS", "MISSED_DELIVERY_ALLOWANCE"])
def test_the_bounds_are_positive_numbers(attr):
    """Cheap, and it is the shape a mutation actually takes: a timeout of 0
    turns every build into a reported failure and every reader into a builder,
    silently, because the surface still answers 200."""
    assert getattr(warm, attr) > 0
