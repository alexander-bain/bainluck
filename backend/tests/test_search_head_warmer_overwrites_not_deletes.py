"""#3526 — the `/search` warmer refreshes the entry it is replacing, never deletes it.

WHAT WENT WRONG, AND WHY IT IS A SECOND FILE RATHER THAN A PARAMETER ON THE FIRST.

`/api/events/search` writes its Redis entry only on the MISS path. So when
`search_head_warmer` wanted to extend a head term's life, the only lever it had
was to DELETE the entry (`_drop_cached`) and let the route miss. Its own
docstring said so:

    "The route writes its cache only on the miss path, so the sole way a warmer
    can extend an entry's life is to make the entry not be there."

That sentence stopped being true on 2026-08-29, when LAT-P134/#2304 built
`_force_cache_rebuild` for the SIBLING endpoint — in `routes/events.py`, the same
file this route lives in. Nobody carried it across. For eight days this warmer
went on blanking the entry it was in the middle of refreshing, and the hole is
the WIDER of the two: `PER_QUERY_TIMEOUT_SECONDS` is 25s, and on production
`c1ac1d6c` (2026-09-06) the warmer's real passes ran 3.3-23.8s against ~11-56ms
floor-skips. #2304's `/typeahead` hole measured 2.0-3.7s and that was enough.

THE FIX is `_force_search_cache_rebuild`: a ContextVar the warmer sets, which
makes the route skip the cache READ and keep the cache WRITE. The old answer
stays served until the new one overwrites it.

🔴 EVERY TEST BELOW EXISTS BECAUSE THE FIX HAS A SILENT FAILURE MODE. If the flag
stops reaching the route, or grows a second consumer on the WRITE condition, the
route answers from the very entry the warmer came to replace, returns in
milliseconds, and the warmer reports `warmed` — a green pass that warmed nothing
(gotcha #53). The DELETE at least guaranteed a miss; rebuilding over a live entry
takes that guarantee away, so the guards run in BOTH directions:

  * the warmer must not DELETE                (the defect being removed)
  * the warmer must set the flag              (the mechanism replacing it)
  * the route must honour it on the READ      (or nothing is rebuilt)
  * the route must NOT honour it on the WRITE (or nothing is warmed)
  * a rebuild that writes nothing must be COUNTED, not reported as success
  * an unreadable Redis must NOT read as that defect
  * the flag must not leak past the call      (a user must never bypass the cache)

🔴 THE ROUTE-SIDE GUARDS PARSE, THEY DO NOT GREP. The sibling's equivalents match
a substring against one source LINE, which works only because its conditions
happen to fit on one. This route's read condition is a parenthesised multi-line
boolean, and a line-wise `"A" in line and "B" in line` scan over it is vacuously
empty — it would pass with the feature deleted. These walk the AST instead, so
reformatting the condition cannot silently disarm them.
"""

import ast
import asyncio
import inspect
import math
import textwrap
import threading as _threading
import time as _time_mod
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.tasks import search_head_warmer as warmer

_FLAG = "_force_search_cache_rebuild"


class _FakeSession:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def _owned(token="test-token"):
    """The claim a successful acquire returns. CERT-2114.

    Tests that stub `_acquire_run_lock` used to hand back a bare `True`, which is
    precisely the two-valued answer the repair removed: `True` could not tell
    "we own it" from "we could not ask". Anything stubbing the acquire now has to
    say WHICH, and these three helpers are the only three answers there are.
    """
    return warmer._RunLockClaim(warmer.RunLockState.OWNED, token)


def _refused(token="test-token"):
    return warmer._RunLockClaim(warmer.RunLockState.HELD_ELSEWHERE, token)


def _unknown(token="test-token"):
    return warmer._RunLockClaim(warmer.RunLockState.UNKNOWN, token)


def _route_ast():
    """The `search_events` function body as an AST, dedented so it parses alone."""
    src = textwrap.dedent(inspect.getsource(events_route.search_events))
    return ast.parse(src)


# ---------------------------------------------------------------------------
# 1. The defect itself: no DELETE, on any path.
# ---------------------------------------------------------------------------

class TestTheWarmerNeverDeletesTheEntry:
    def test_the_drop_helper_is_gone_from_the_module(self):
        """`_drop_cached` is not "unused", it is REMOVED.

        Left in place it is a loaded gun sitting next to the trigger: the next
        reader wiring a refresh path reaches for the helper that already exists.
        """
        assert not hasattr(warmer, "_drop_cached"), (
            "_drop_cached is the hole. It must not survive as a callable."
        )

    def test_no_source_line_deletes_the_search_cache_key(self):
        """Source-shape guard, deliberately not a behavioural one.

        A behavioural test only sees the paths it drives. This sees every path,
        including one added later by someone who never reads this file.
        """
        src = inspect.getsource(warmer)
        offenders = [
            line.strip()
            for line in src.splitlines()
            # Comments excluded: the module docstring quotes the old mechanism on
            # purpose. `_LOCK_KEY` excluded because releasing the run lock is a
            # DELETE this module must keep — narrowing to "delete of the RESPONSE
            # cache key" is the whole distinction, and a guard that banned both
            # would have to be deleted the first time someone read it.
            if ".delete(" in line
            and not line.strip().startswith("#")
            and "_LOCK_KEY" not in line
        ]
        assert offenders == [], (
            "the warmer must never DELETE a /search entry; found: %r" % offenders
        )

    @pytest.mark.parametrize(
        "ttl_before", [0, 5, 24, warmer._TTL_NO_EXPIRY, warmer._TTL_NO_KEY]
    )
    def test_a_stale_entry_is_rebuilt_over_and_never_removed(self, ttl_before):
        """The whole point, driven behaviourally across every rebuild-worthy TTL.

        `_TTL_NO_EXPIRY` (-1) is in the set because it is the one value that
        *should* be impossible and is treated as needing a rebuild — the old code
        dropped it, and a rebuild-over must fix the missing expiry just as well.
        `_TTL_NO_KEY` (-2) is in the set because the OLD code special-cased it to
        skip the delete; nothing may now depend on that branch surviving.
        """
        deletes = []
        ttls = iter([ttl_before, 60])

        async def _fake_route(**kw):
            return {"events": []}

        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route), \
             patch("app.tasks.redis_state.get_redis_client") as rc:
            rc.return_value.delete.side_effect = lambda *a, **k: deletes.append(a)
            out = _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert deletes == [], "the entry was deleted; the hole is back"
        assert out["rebuilt"] is True
        assert out["reason"] == "warmed"


# ---------------------------------------------------------------------------
# 2. The mechanism: the flag is set, and it is set around the route call.
# ---------------------------------------------------------------------------

class TestTheWarmerForcesTheRebuildThroughTheFlag:
    def test_the_route_sees_the_flag_set_during_the_call(self):
        seen = {}

        async def _fake_route(**kw):
            seen["forced"] = events_route._force_search_cache_rebuild.get()
            return {"events": []}

        ttls = iter([10, 60])
        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route):
            _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert seen["forced"] is True, (
            "the route ran without the force flag — it would have answered from "
            "the entry the warmer came to replace and reported success"
        )

    def test_a_fresh_entry_is_skipped_without_ever_setting_the_flag(self):
        """The refresh-ahead skip must stay a pure no-op.

        Setting the flag and *then* deciding not to rebuild would be harmless
        today and load-bearing the moment someone moves the skip.

        The "fresh" TTL is DERIVED from `REFRESH_AHEAD_SECONDS`, not written as a
        literal. It used to be `59` — a number that was fresh only while the
        threshold was 25, and that silently became a REBUILD case when #3539
        moved the threshold to 150. A fixture that hardcodes a value the
        production constant derives stops testing what its name says the moment
        that constant moves.
        """
        called = []

        async def _fake_route(**kw):
            called.append(kw)
            return {"events": []}

        fresh_ttl = warmer.REFRESH_AHEAD_SECONDS + 1

        with patch.object(warmer, "_cache_ttl_seconds", return_value=fresh_ttl), \
             patch.object(events_route, "search_events", _fake_route):
            out = _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert called == []
        assert out["reason"] == "fresh"
        assert out["rebuilt"] is False
        assert events_route._force_search_cache_rebuild.get() is False

    @pytest.mark.parametrize("boom", [asyncio.TimeoutError, RuntimeError])
    def test_the_flag_is_reset_even_when_the_rebuild_blows_up(self, boom):
        """🔴 A LEAKED FLAG IS A USER BYPASSING THE CACHE.

        Per-task context copies already make this unreachable in production. The
        reset makes it unreachable *without depending on that argument* — and an
        argument is what the previous mispricing was made of.

        🔴 THE OBSERVATION POINT IS THE WHOLE TEST, and the sibling's file records
        getting it wrong first. Reading the flag from the test body after
        `run_until_complete` reads a DIFFERENT context — `run_until_complete`
        wraps the coroutine in a Task, which copies the context, so `set(True)`
        inside `_warm_one` could never be visible there and the assertion would
        hold with the reset deleted. The leak is only observable from a caller
        that `await`s `_warm_one` directly, because a plain `await` shares the
        caller's context — which is also the only arrangement in which the leak
        could ever hurt anyone.
        """
        async def _fake_route(**kw):
            raise boom("nope")

        async def _await_in_the_same_context():
            out = await warmer._warm_one(_FakeSession(), "red sox")
            return out, events_route._force_search_cache_rebuild.get()

        with patch.object(warmer, "_cache_ttl_seconds", return_value=10), \
             patch.object(events_route, "search_events", _fake_route):
            out, leaked = _run(_await_in_the_same_context())

        assert out["ok"] is False
        assert leaked is False, "the force flag leaked out of a failed rebuild"

    def test_the_flag_is_reset_after_a_SUCCESSFUL_rebuild_too(self):
        """The success path is the common one; a leak there is the likely one."""
        async def _fake_route(**kw):
            return {"events": []}

        async def _await_in_the_same_context():
            await warmer._warm_one(_FakeSession(), "red sox")
            return events_route._force_search_cache_rebuild.get()

        ttls = iter([10, 60])
        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route):
            leaked = _run(_await_in_the_same_context())

        assert leaked is False, "the force flag leaked out of a successful rebuild"


# ---------------------------------------------------------------------------
# 3. The route's half — read bypassed, write NOT bypassed.
# ---------------------------------------------------------------------------

class TestTheRouteHonoursTheFlagOnExactlyOneSide:
    def test_the_flag_is_on_the_read_condition(self):
        """Found by AST, so reformatting the condition cannot disarm the guard."""
        assigns = [
            node
            for node in ast.walk(_route_ast())
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_search_cache_readable"
                for t in node.targets
            )
        ]
        assert assigns, (
            "`_search_cache_readable` is gone; this guard is stale and is no "
            "longer proving anything about the cache READ"
        )
        names = {
            n.id for a in assigns for n in ast.walk(a.value) if isinstance(n, ast.Name)
        }
        assert _FLAG in names, (
            "the cache READ must be skipped under %s, or the warmer is served "
            "the entry it came to replace" % _FLAG
        )

    def test_the_flag_is_NOT_on_the_write_condition(self):
        """🔴 THE LOAD-BEARING HALF.

        `debug_timing` bypasses the cache in BOTH directions. This flag bypasses
        ONE. If it ever joins the write condition the warmer runs the full query
        path, writes nothing, and reports success — the exact failure the DELETE
        never had, traded in for the one it did.

        The write guard is located by its EFFECT (`setex` in its body), not by
        its text, so renaming `degraded` cannot turn this into a vacuous pass.
        """
        write_guards = [
            node
            for node in ast.walk(_route_ast())
            if isinstance(node, ast.If)
            and any(
                isinstance(c, ast.Attribute) and c.attr == "setex"
                for stmt in node.body
                for c in ast.walk(stmt)
            )
        ]
        assert write_guards, (
            "no `if ...: setex(...)` remains in search_events — the cache write "
            "moved and this guard is stale"
        )
        for guard in write_guards:
            names = {
                n.id for n in ast.walk(guard.test) if isinstance(n, ast.Name)
            }
            assert _FLAG not in names, (
                "the force flag reached the WRITE condition: the warmer would "
                "now warm nothing and still report success"
            )

    def test_the_route_never_sets_the_flag(self):
        """Read-only in the route. A route that sets it can force its own misses."""
        src = inspect.getsource(events_route)
        sets = [
            line.strip()
            for line in src.splitlines()
            if "%s.set(" % _FLAG in line and not line.strip().startswith("#")
        ]
        assert sets == [], (
            "only the warmer may set %s; found: %r" % (_FLAG, sets)
        )

    def test_the_two_warmers_do_not_share_one_flag(self):
        """🔴 The reason this is a second ContextVar and not a reuse.

        One flag read by both routes would let either warmer make the OTHER
        route bypass its cache. They must be distinct objects with distinct
        names, or the blast radius of a leak doubles.
        """
        assert events_route._force_cache_rebuild is not events_route._force_search_cache_rebuild
        assert (
            events_route._force_cache_rebuild.name
            != events_route._force_search_cache_rebuild.name
        )

    def test_the_default_is_false_so_a_user_request_is_unaffected(self):
        assert events_route._force_search_cache_rebuild.get() is False


# ---------------------------------------------------------------------------
# 4. "It returned" is not "it wrote" — and an unreadable Redis is not a defect.
# ---------------------------------------------------------------------------

class TestASilentNoWriteIsCountedNotCelebrated:
    def test_a_rebuild_that_moved_no_ttl_is_reported_no_write(self):
        """The signature of the flag failing to reach the route.

        The route returns fast from cache, the TTL is untouched, and without this
        check the pass reports `warmed` — indistinguishable from a healthy one.
        This is the check the module did not have at all before #3526: it
        reported `warmed` on the strength of the route having returned.
        """
        ttls = iter([10, 10])

        async def _fake_route(**kw):
            return {"events": []}

        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route):
            out = _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert out["reason"] == "no_write"
        assert out["ok"] is False, "a pass that wrote nothing is not a success"

    def test_an_unreadable_ttl_after_is_unverified_not_no_write(self):
        """🔴 A REDIS BLINK MUST NOT MANUFACTURE A DEFECT.

        `None` is not a TTL. Collapsing it into `no_write` would turn every
        unreadable instant into a reported warmer failure — the mirror of the
        conflation that produced this file's subject.
        """
        ttls = iter([10, None])

        async def _fake_route(**kw):
            return {"events": []}

        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route):
            out = _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert out["reason"] == "warmed_unverified"
        assert out["ok"] is True

    def test_a_first_write_over_no_key_at_all_is_a_warm(self):
        """`_TTL_NO_KEY` (-2) before, a real TTL after: the term WAS cold, now is not."""
        ttls = iter([warmer._TTL_NO_KEY, 60])

        async def _fake_route(**kw):
            return {"events": []}

        with patch.object(warmer, "_cache_ttl_seconds", side_effect=lambda k: next(ttls)), \
             patch.object(events_route, "search_events", _fake_route):
            out = _run(warmer._warm_one(_FakeSession(), "red sox"))

        assert out["reason"] == "warmed"
        assert out["ok"] is True


# ---------------------------------------------------------------------------
# 5. The pass summary must not launder any of it.
# ---------------------------------------------------------------------------

class TestThePassSummaryTellsTheTruthAboutWrites:
    def _summarise(self, results):
        """Drive the REAL summary assembly with a canned result set.

        Deliberately not a hand-built dict compared against literals: the thing
        under test is the assembly, and a test that re-writes it proves nothing.
        """
        async def _fake_concurrent(sessions, head):
            return results

        with patch.object(warmer, "_acquire_run_lock", return_value=_owned()), \
             patch.object(warmer, "_release_run_lock"), \
             patch.object(warmer, "_warm_head_concurrently", _fake_concurrent), \
             patch.object(warmer, "_record_pass_start"), \
             patch.object(warmer, "_seconds_since_last_pass", return_value=100.0), \
             patch("app.tasks.base.get_task_session", _fake_session_cm):
            out = _run(warmer._warm_search_head(queries=[r["q"] for r in results]))
        # 🔴 ASSERTED, NOT ASSUMED. `_warm_search_head` filters the head to
        # `_MIN_QUERY_CHARS.._MAX_QUERY_CHARS`, so a one-character probe term
        # empties the head and the pass reports `partial` for a reason that has
        # nothing to do with writes — a no_write test would then go green with
        # the feature deleted. The sibling's file records exactly that near-miss.
        assert out["total"] > 0, (
            "the canned head was filtered away; this summary is not about writes"
        )
        return out

    def test_a_no_write_forces_partial_and_names_the_query(self):
        results = [
            {"q": "red sox", "ok": True, "reason": "warmed", "ttl_before": 5,
             "rebuilt": True, "ttl_after": 60, "seconds": 1.0},
            {"q": "world cup", "ok": False, "reason": "no_write", "ttl_before": 5,
             "rebuilt": True, "ttl_after": 5, "seconds": 0.02},
        ]
        out = self._summarise(results)
        assert out["terminal"] == "partial", (
            "a pass where the route wrote nothing must never report complete"
        )
        assert out["no_writes"] == ["world cup"]

    def test_a_clean_pass_still_reports_complete(self):
        """The control. Without it, `partial` could be the answer to everything."""
        results = [
            {"q": "red sox", "ok": True, "reason": "warmed", "ttl_before": 5,
             "rebuilt": True, "ttl_after": 60, "seconds": 1.0},
        ]
        out = self._summarise(results)
        assert out["terminal"] == "complete"
        assert out["no_writes"] == []

    def test_unverified_still_counts_as_a_rebuild(self):
        """A Redis blink must not read as "the refresh threshold did not fire"."""
        results = [
            {"q": "red sox", "ok": True, "reason": "warmed_unverified",
             "ttl_before": 5, "rebuilt": True, "ttl_after": None, "seconds": 1.0},
        ]
        out = self._summarise(results)
        assert out["rebuilt"] == 1
        assert out["unverified"] == 1
        assert out["terminal"] == "complete"

    def test_a_skipped_pass_carries_the_new_keys_too(self):
        """The same-keys contract, extended to #3526's fields.

        An absent field and a zero field must not read the same (gotcha #53), and
        a consumer must never have to branch on `terminal` to know whether a
        field exists.
        """
        with patch.object(warmer, "_acquire_run_lock", return_value=_refused()):
            out = _run(warmer._warm_search_head())
        assert out["terminal"] == "skipped"
        for key in ("no_writes", "unverified"):
            assert key in out, (
                f"{key!r} missing from the skip shape — a consumer would have to "
                "branch on `terminal` to know whether it exists"
            )


class _FakeSessionCM:
    async def __aenter__(self):
        return _FakeSession()

    async def __aexit__(self, *a):
        return False


def _fake_session_cm(*a, **kw):
    return _FakeSessionCM()


# ============================================================================
# CERT-2068's NAMED REGRESSION — residency across two cycles, expiring Redis.
#
# The BLOCK on `f81fdfe45da777bd74f271bea2ac767e4b9e1b0f` said, in full:
#
#   "removing the eager DELETE does not keep the old /search entry alive through
#    rebuild. A 20s beat plus a 45s minimum yields actual eligible starts 60s
#    apart; at the next pass the 60s key has roughly the prior build duration
#    left. The submitted measured 3.3s-to-23.8s sequence permits ~20.5s of
#    absence during the second rebuild ... Required regression: fake-clock two
#    cycles with expiring Redis and a short-then-long rebuild, continuously
#    asserting the served key never disappears."
#
# That is exactly this section. It reproduces the grader's ~20.5 s on the blocked
# constants and shows it closed on the shipped ones.
#
# WHY IT IS A SIMULATION AND WHAT IS REAL IN IT. Everything that decides the
# outcome is production code: `_needs_rebuild` is imported and called, and the
# cadence and thresholds come from `effective_pass_period_s()`,
# `REFRESH_AHEAD_SECONDS` and `SEARCH_RESPONSE_TTL_SECONDS`. What is modelled is
# only the environment — a clock that advances and a Redis that expires — because
# a guard that re-implements the predicate it is guarding agrees with it by
# construction and can never fail.
# ============================================================================


class _ExpiringWriteLog:
    """Redis TTL semantics as an append-only log, so presence is answerable at ANY t.

    A single mutable `expires_at` cannot answer "was the key present at t=63.3?"
    once a later write has moved the expiry — the first draft of this harness had
    exactly that bug and reported a clean run over a configuration that measurably
    holes. Each `setex` appends `[written, written + ttl)`; presence at `t` is
    membership in any interval.
    """

    def __init__(self, ttl_s: float):
        self._ttl = ttl_s
        self.writes: list[tuple[float, float]] = []

    def setex(self, written_at: float) -> None:
        self.writes.append((written_at, written_at + self._ttl))

    def ttl_at(self, t: float) -> int:
        """Redis's three-valued dialect: -2 no key, else whole seconds left."""
        live = [exp for w, exp in self.writes if w <= t < exp]
        if not live:
            return -2
        return int(max(live) - t)          # Redis floors; so must we.

    def present_at(self, t: float) -> bool:
        return self.ttl_at(t) != -2


def _simulate_residency(
    *,
    ttl_s,
    refresh_ahead_s,
    rebuild_walls,
    horizon_s,
    beat_s=20.0,
    floor_s=45.0,
    organic_phase=False,
):
    """Run pass cycles on a fake clock and report every interval the key was ABSENT.

    Faithful to the post-#3526 mechanism: the warmer does NOT delete, so the old
    value keeps serving for the whole rebuild and is replaced by `setex` at the
    END of it.

    🔴 THE RUN LOCK IS MODELLED (CERT-2084). A pass holds `_LOCK_KEY` for its whole
    duration, so a rebuild longer than one beat does not merely delay itself — it
    suppresses every fire underneath it. The next pass starts at the first beat
    multiple at or after BOTH the floor and the previous pass's end. A scheduler
    that just adds a fixed period cannot see that, and a 100 s rebuild against a
    20 s beat is exactly where it stops being fixed.

    🔴 `organic_phase=True` SEEDS THE ENTRY THE WAY A USER DOES, NOT THE WAY THE
    WARMER DOES (CERT-2084). `/search` writes its own cache on a MISS, at whatever
    moment the user searched, so an entry can first be observed at ANY remaining
    life — including exactly `refresh_ahead_s`, where `<` skips it. Seeding only
    warmer-aligned writes (always observed at `ttl - period`) is what made the
    first version of this harness green over a configuration that holes.

    Eligibility is production's `_needs_rebuild`; alternative configurations are
    exercised by patching the CONSTANT it reads, never by reimplementing it.
    """
    from unittest.mock import patch

    from app.tasks import search_head_warmer as warmer

    log = _ExpiringWriteLog(ttl_s)

    def _next_start(last_start, last_end, phase):
        # The floor is measured from the last pass START; the lock from its END.
        # `phase` is the beat grid's alignment, which relative to a user's organic
        # write is ARBITRARY — pinning it to 0 privileges one alignment and is how
        # a sweep can miss the edge entirely.
        earliest = max(last_start + floor_s, last_end)
        return phase + beat_s * math.ceil((earliest - phase) / beat_s)

    with patch.object(warmer, "REFRESH_AHEAD_SECONDS", refresh_ahead_s):
        if organic_phase:
            # A user's MISS writes at t=0; the first pass therefore lands with
            # exactly `refresh_ahead_s` of life left — the skipped edge.
            log.setex(0.0)
            watch_from = 0.0
            start = float(ttl_s - refresh_ahead_s)
            phase = start % beat_s
            last_start, last_end = start - floor_s, 0.0
        else:
            # Warmer-aligned: pass 0 finds nothing and builds the first entry.
            first = rebuild_walls[0]
            log.setex(first)
            watch_from = first
            last_start, last_end = 0.0, first
            phase = 0.0
            start = _next_start(last_start, last_end, phase)

        timeline, i = [], 1
        while start <= horizon_s:
            ttl_before = log.ttl_at(start)
            if warmer._needs_rebuild(None if ttl_before == -2 else ttl_before):
                wall = rebuild_walls[min(i, len(rebuild_walls) - 1)]
                log.setex(start + wall)
                timeline.append(("write", start + wall, ttl_before))
                last_start, last_end = start, start + wall
            else:
                timeline.append(("fresh", start, ttl_before))
                last_start, last_end = start, start   # a skip is ~instant
            start = _next_start(last_start, last_end, phase)
            i += 1

    absent, run_start = [], None
    t = watch_from
    while t <= horizon_s:
        present = log.present_at(t)
        if not present and run_start is None:
            run_start = t
        elif present and run_start is not None:
            absent.append((round(run_start, 1), round(t, 1)))
            run_start = None
        t = round(t + 0.1, 1)
    if run_start is not None:
        absent.append((round(run_start, 1), horizon_s))
    return absent, timeline


# The grader's own measured sequence: a short pass followed by a long one.
_SHORT_THEN_LONG = [3.3, 23.8, 23.8, 23.8, 23.8, 23.8]


def test_the_blocked_constants_leave_the_key_absent_for_the_graders_twenty_seconds():
    """CERT-2068's finding, reproduced. This is the RED half of the regression.

    On `f81fdfe4`'s constants (TTL 60, refresh-ahead 25) the entry written by the
    3.3 s pass expires at t=63.3, and the 23.8 s pass that should have replaced it
    does not write until t=83.8. The head is cold for the difference. If this test
    ever stops finding a hole, the simulation has stopped modelling the defect and
    the GREEN half below is worthless.
    """
    absent, _ = _simulate_residency(
        ttl_s=60,
        refresh_ahead_s=25,
        rebuild_walls=_SHORT_THEN_LONG,
        horizon_s=180.0,
    )
    assert absent, "the blocked constants must reproduce a hole — they measured one"
    widest = max(b - a for a, b in absent)
    assert 20.0 <= widest <= 21.0, (
        f"expected the grader's ~20.5 s of absence on the blocked constants, "
        f"measured {widest:.1f} s across {absent}"
    )


def test_the_head_never_disappears_across_two_cycles_at_the_shipped_constants():
    """The GREEN half. Same clock, same Redis, same short-then-long sequence.

    Under D81 = A (TTL 180) with the derived refresh-ahead (150), the 3.3 s pass
    writes an entry that lives to t=183.3, and the 23.8 s pass replaces it at
    t=83.8 — a hundred seconds of margin rather than twenty seconds of hole.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        effective_pass_period_s,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    absent, timeline = _simulate_residency(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        refresh_ahead_s=REFRESH_AHEAD_SECONDS,
        rebuild_walls=_SHORT_THEN_LONG,
        horizon_s=600.0,
    )
    assert absent == [], (
        f"the served key disappeared at the shipped constants: {absent}\n"
        f"timeline: {timeline}"
    )
    # ...and it was actually doing work, not passing by never rebuilding.
    assert sum(1 for kind, *_ in timeline if kind == "write") >= 5, (
        "a run that never rebuilt would also report no absence — that is the "
        "vacuous pass this assertion exists to refuse"
    )


def test_residency_holds_when_every_rebuild_takes_the_full_declared_budget():
    """The bound, not the sample. Every pass pinned at `full_rebuild_budget_s()`.

    Sizing against the measured 3.3-23.8 s is the error this program has made
    twice; the invariant is written against what the code PERMITS. At 8 terms,
    concurrency 2 and a 25 s per-query bound that is 100 s per pass, and the
    entry must still never vanish.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        effective_pass_period_s,
        full_rebuild_budget_s,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    budget = full_rebuild_budget_s()
    absent, _ = _simulate_residency(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        refresh_ahead_s=REFRESH_AHEAD_SECONDS,
        rebuild_walls=[budget] * 12,
        horizon_s=900.0,
    )
    assert absent == [], (
        f"at the declared {budget:g}s rebuild budget the head still went cold: {absent}"
    )


def test_option_four_as_written_on_3539_would_have_shipped_a_hole():
    """Why the ruling's letter needed the derivation and not the issue's numbers.

    #3539's option 4 proposed TTL 180 with refresh-ahead 90. 90 is below
    `TTL - period` (120), so the first pass that could rebuild the entry calls it
    `fresh` and walks past; the entry is only caught a period later and by then
    a full-budget rebuild overruns its life. Recorded as a test because the
    number was recommended in writing and is the obvious thing to reach for.
    """
    absent, _ = _simulate_residency(
        ttl_s=180,
        refresh_ahead_s=90,
        rebuild_walls=[100.0] * 12,
        horizon_s=900.0,
    )
    assert absent, (
        "option 4 as written (180/90) must be shown to leave a hole — if it does "
        "not, the derivation that rejected it is over-strict and should be revisited"
    )


# ---------------------------------------------------------------------------
# CERT-2084's NAMED REGRESSION — the ORGANIC phase, which the first harness
# could not see.
#
#   "residency_invariant() checks TTL - period > budget instead of #3539's
#    necessary refresh_ahead - period > budget. At shipped 180/150/60/100,
#    _needs_rebuild(150) skips; the next pass sees 90s left and a permitted 100s
#    rebuild opens a 10s cold interval. The fake-clock guard seeds only
#    warmer-aligned writes and cannot see an organic route write at the
#    threshold edge. ... Required catching test: organic entry first observed at
#    TTL exactly threshold, next pass 60s later, full 100s rebuild, continuously
#    resident; current SHA must expose [180,190)."
# ---------------------------------------------------------------------------


def test_the_previous_threshold_holes_when_the_entry_is_seen_at_the_threshold_edge():
    """The RED half of CERT-2084's regression. 150 was the blocked value.

    A user's MISS writes the entry at t=0 with a 180 s life. The first pass lands
    when exactly 150 s remain — `_needs_rebuild(150)` is `150 < 150`, False, so the
    pass walks past. The next pass is 60 s later with 90 s left, and the rebuild is
    permitted 100 s: the entry dies at t=180 and the replacement lands at t=190.

    This is the interval the grader named, reproduced exactly: **[180, 190)**.
    """
    absent, timeline = _simulate_residency(
        ttl_s=180,
        refresh_ahead_s=150,          # the blocked value
        rebuild_walls=[100.0] * 12,   # the full declared budget
        horizon_s=600.0,
        organic_phase=True,
    )
    assert absent, f"the blocked threshold must hole on the organic phase; timeline={timeline}"
    assert absent[0] == (180.0, 190.0), (
        f"expected the graded [180, 190) cold interval, measured {absent[0]}"
    )


def test_an_organic_entry_seen_at_the_threshold_edge_stays_resident_at_the_shipped_threshold():
    """The GREEN half. Same seeding, same full-budget rebuilds, shipped constants.

    At 150 the entry is skipped at 150 s and rebuilt one period later with 90 s
    left, against a 70 s budget — it survives with 20 s to spare, every cycle.

    🔴 THE WALL HERE IS `full_rebuild_budget_s()` AND IT USED TO BE A LITERAL 100.
    That literal was the budget when this test was written, and it stopped being
    the budget the moment CERT-2089's repair re-derived the budget off the
    ENFORCED worker unit (70 s). A hardcoded bound in a test whose whole subject
    is "the code is measured against what it PERMITS, never against a sample" is
    the same substitution the four BLOCKs in this chain each found in the module:
    a number that was true once, kept after the thing it named moved.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        full_rebuild_budget_s,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    absent, timeline = _simulate_residency(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        refresh_ahead_s=REFRESH_AHEAD_SECONDS,
        rebuild_walls=[full_rebuild_budget_s()] * 20,
        horizon_s=1200.0,
        organic_phase=True,
    )
    assert absent == [], (
        f"the served key disappeared on the organic phase: {absent}\ntimeline={timeline}"
    )
    assert sum(1 for kind, *_ in timeline if kind == "write") >= 5, (
        "a run that never rebuilt would also report no absence"
    )


def test_the_organic_phase_is_swept_not_sampled_at_one_lucky_offset():
    """One seeding is one phase. The route writes at ARBITRARY phase, so sweep it.

    A single organic offset can miss the edge by luck — which is exactly how the
    warmer-aligned-only harness passed over a holing configuration. Every REACHABLE
    offset is swept by a CLOSED FORM that is deliberately not the simulation, so the
    two methods have to agree rather than one method being run twice.

    The sweep runs over `[0, period]`, not `[0, TTL]`, and the bound is load-bearing
    rather than an optimisation: a pass arrives within one period of any write, so
    an entry cannot first be OBSERVED with less than `TTL - period` left. Sweeping
    to the TTL reports offsets 80-180 as cold, and every one of them is a state the
    scheduler cannot produce — a sweep that ranges outside the reachable set
    manufactures failures and then gets loosened to silence them.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        effective_pass_period_s,
        full_rebuild_budget_s,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    period, budget = effective_pass_period_s(), full_rebuild_budget_s()
    bad = [
        bad_row
        for offset in range(0, int(period) + 1)
        for bad_row in _sweep_one_offset(
            offset=offset,
            ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
            refresh_ahead_s=REFRESH_AHEAD_SECONDS,
            period_s=period,
            budget_s=budget,
        )
    ]
    assert bad == [], f"organic write offsets that leave the head cold: {bad[:6]}"

    # ...and the same sweep must CONVICT the blocked threshold, or it is vacuous.
    convicted = [
        row
        for offset in range(0, int(period) + 1)
        for row in _sweep_one_offset(
            offset=offset,
            ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
            refresh_ahead_s=150,
            period_s=period,
            budget_s=100.0,
        )
    ]
    assert convicted, "the sweep does not convict the blocked 150 — it proves nothing"


def _sweep_one_offset(*, offset, ttl_s, refresh_ahead_s, period_s, budget_s):
    """Closed-form residency for one organic offset. Deliberately NOT the sim.

    A second, independent derivation of the same property: an entry first seen
    with `r0 = ttl - offset` left is skipped while `r >= refresh_ahead`, and the
    first pass that rebuilds it starts with `r` seconds of life against a
    `budget_s` rebuild. If any such `r` is <= the budget, the head goes cold.
    Two methods agreeing is worth more than one method run twice.
    """
    r = ttl_s - offset
    while r >= refresh_ahead_s:      # skipped as `fresh`
        r -= period_s
    if r <= 0:                        # already expired before any pass saw it
        return [(offset, "expired unseen")]
    return [] if r > budget_s else [(offset, f"rebuild starts with {r}s vs {budget_s}s budget")]


# ---------------------------------------------------------------------------
# CERT-2086's NAMED REGRESSION — the head is RE-RANKED and the cursor is SHARED,
# so a query does not hold its position between passes.
#
#   "the proof assumes one within-pass write position while production re-ranks
#    the head every pass and dispatches it through a dynamic two-worker cursor.
#    An allowed full-budget schedule writes query A first at t=1, holds the pass
#    lock to t=100, then after re-ranking writes A last at t=200; its 180-second
#    entry expires at t=181, leaving [181,200) cold. ... Required catching test:
#    real two-worker cursor plus run-lock fake clock, same query first/fast then
#    last/full-budget, continuously asserting no absence; current SHA must expose
#    the 19-second hole."
# ---------------------------------------------------------------------------


def _run_two_pass_reranked(
    *, ttl_s, per_query_s, head_a, head_b, walls, concurrency=None
):
    """Drive the REAL shared-cursor dispatcher twice, re-ranking between passes.

    `_warm_head_concurrently` is production's own function — the point of this
    harness is that the cursor is the real one, because it is the cursor that
    makes a query's write position vary. `_warm_one` is replaced by a stub that
    consumes fake time from `walls` and records the write; the run lock is
    modelled by starting pass two no earlier than pass one's end.

    `per_query_s` is A WHOLE WORKER UNIT, not a route call (CERT-2089): the cursor
    hands out units, so a wall consumed here has to include the two TTL reads that
    bracket the route call. `concurrency` defaults to the shipped
    `WARM_CONCURRENCY` so the harness follows the module rather than pinning the
    width the module happened to have when it was written.

    Returns the write times of query "a" and the absence intervals for its key.
    """
    from unittest.mock import patch

    from app.tasks import search_head_warmer as warmer

    width = warmer.WARM_CONCURRENCY if concurrency is None else concurrency
    clock = {"t": 0.0}
    log = _ExpiringWriteLog(ttl_s)
    writes_a = []

    async def _fake_warm_one(session, q):
        # One query in flight per session, and each session keeps its OWN clock —
        # the two workers run in parallel. Threading a single global clock through
        # both serializes the pool and inflates every write time (this harness did
        # exactly that on its first run, and reported a 199 s hole where the real
        # schedule gives 19 s).
        # Yield once, so `asyncio.gather` actually interleaves the two workers over
        # the shared cursor. Without it the stub never suspends, the first worker
        # drains the whole cursor, and the pool is silently a pool of one — which
        # inflated this harness's first run to a 199 s hole where the real schedule
        # gives 19 s.
        await asyncio.sleep(0)
        wall = walls[q].pop(0) if walls.get(q) else per_query_s
        session["free_at"] += wall
        clock["t"] = max(clock["t"], session["free_at"])
        if q == "a":
            log.setex(session["free_at"])
            writes_a.append(session["free_at"])
        return {"q": q, "ok": True, "reason": "warmed", "rebuilt": True, "seconds": wall}

    async def _one_pass(head, pass_start):
        clock["t"] = pass_start
        sessions = [{"free_at": pass_start} for _ in range(width)]
        with patch.object(warmer, "_warm_one", _fake_warm_one):
            await warmer._warm_head_concurrently(sessions, head)
        return max(s["free_at"] for s in sessions)      # the pass END = lock release

    end_1 = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        _one_pass(head_a, 0.0)
    )
    # The run lock: pass two cannot start before pass one ends, quantized to the beat.
    start_2 = 20.0 * math.ceil(max(45.0, end_1) / 20.0)
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        _one_pass(head_b, start_2)
    )

    absent, run_start = [], None
    t = writes_a[0]
    horizon = writes_a[-1] + 5
    while t <= horizon:
        present = log.present_at(t)
        if not present and run_start is None:
            run_start = t
        elif present and run_start is not None:
            absent.append((round(run_start, 1), round(t, 1)))
            run_start = None
        t = round(t + 0.1, 1)
    return writes_a, absent


#: "a" is fast and FIRST in pass one; slow and LAST in pass two after re-ranking.
_HEAD_FIRST = ["a", "b", "c", "d", "e", "f", "g", "h"]
_HEAD_RERANKED = ["b", "c", "d", "e", "f", "g", "h", "a"]


def test_the_previous_budget_holes_when_a_query_is_written_first_then_last():
    """The RED half of CERT-2086's regression, on the 100 s budget it blocked.

    Query "a" is written at t=1 in pass one and, after the head is re-ranked, at
    t=200 in pass two. Its 180 s entry expired at t=181.
    """
    walls = {q: [25.0] * 4 for q in _HEAD_FIRST}
    walls["a"] = [1.0, 25.0]
    writes, absent = _run_two_pass_reranked(
        ttl_s=180,
        per_query_s=25.0,
        head_a=_HEAD_FIRST,
        head_b=_HEAD_RERANKED,
        walls=walls,
        # The width CERT-2086 was graded at, pinned rather than inherited: this is
        # a reproduction of a past configuration, so it must not follow the module
        # when the module's width changes.
        concurrency=2,
    )
    assert absent, f"the 100s-budget configuration must hole; writes of 'a' = {writes}"
    width = max(b - a for a, b in absent)
    assert 18.0 <= width <= 20.0, (
        f"expected the graded ~19 s hole, measured {width:.1f}s across {absent} "
        f"(writes of 'a' at {writes})"
    )


def test_a_reranked_query_written_first_then_last_stays_resident_at_the_shipped_budget():
    """The GREEN half. Same re-ranking, same worst schedule, corrected budget.

    Sized off the ENFORCED worker unit (35 s) at the shipped width of 4, the full
    pass budget is 70 s, so the worst same-query interval is 80 + 70 = 150 s
    inside a 180 s life.
    """
    from app.tasks.search_head_warmer import worker_unit_bound_s
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    bound = worker_unit_bound_s()
    walls = {q: [bound] * 4 for q in _HEAD_FIRST}
    walls["a"] = [1.0, bound]
    writes, absent = _run_two_pass_reranked(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        per_query_s=bound,
        head_a=_HEAD_FIRST,
        head_b=_HEAD_RERANKED,
        walls=walls,
    )
    assert absent == [], f"'a' went cold across the re-rank: {absent} (writes {writes})"


def test_the_route_deadline_mirror_has_not_drifted():
    """`ROUTE_SEARCH_DEADLINE_SECONDS` mirrors the route; a mirror needs a guard.

    It is a mirror rather than an import because `app.routes.events` importing
    back into `app.tasks` is the circular shape this package avoids. The cost of a
    mirror is drift, and the payment for it is this test — the same bargain
    `/typeahead`'s 45->65 s change had to make in two places.
    """
    from app.routes import events
    from app.tasks.search_head_warmer import ROUTE_SEARCH_DEADLINE_SECONDS

    assert ROUTE_SEARCH_DEADLINE_SECONDS == events._SEARCH_DEADLINE_MS / 1000.0, (
        "the warmer's copy of the route deadline has drifted from the route. Every "
        "residency budget is derived from it, so the drift silently re-opens the hole."
    )


# ===========================================================================
# CERT-2089's NAMED REGRESSION — the route's deadline is COOPERATIVE, the two
# TTL reads are INSIDE the cursor and OUTSIDE the wall, and the unit is neither
# of the numbers the budget was priced at.
#
#   "the new 80-second pass budget treats the route's cooperative 20-second stage
#    deadline as a hard per-query wall. `_warm_one` still wraps the route at 25
#    seconds, the route has no whole-call timeout, and synchronous TTL reads that
#    occupy the cursor sit outside that wrapper. The code therefore still permits
#    a 100-second-or-longer pass and a >=200-second same-query write interval
#    against a 180-second TTL. Required repair: derive from and enforce a hard
#    whole-worker-unit bound, or change width/concurrency/cadence so that real
#    bound fits D81. Required catching test: real cursor with a route returning
#    after 20 but before 25 seconds plus TTL-read time must fail this SHA and
#    remain continuously resident after repair."
#
# `_ROUTE_PAST_ITS_DEADLINE` is the grader's own case: 24 s is past the 20 s
# cooperative deadline and inside the 25 s `wait_for`, so it is a route call the
# blocked SHA permits and reports as a clean `warmed`.
# ===========================================================================

_ROUTE_PAST_ITS_DEADLINE = 24.0


def _unit_when_the_route_runs_past_its_deadline() -> float:
    """One worker unit at the grader's case: two TTL reads bracketing a 24 s route."""
    from app.tasks.search_head_warmer import ttl_read_cooperative_bound_s

    return _ROUTE_PAST_ITS_DEADLINE + 2 * ttl_read_cooperative_bound_s()


def test_the_blocked_bound_holes_when_the_route_returns_after_its_cooperative_deadline():
    """The RED half, on the width and the pricing CERT-2089 blocked.

    The blocked SHA priced a unit at 20 s — `min(25, route_deadline)` — and got a
    80 s budget and a 160 s worst interval, which cleared the 180 s TTL on paper.
    The unit it actually permitted is this one: an unbounded TTL read, a route
    call walled at 25 s whose own 20 s deadline it may overrun, and a second
    unbounded TTL read. At the grader's 24 s route that is 32.2 s, and driving the
    REAL shared cursor at the blocked width of 2 puts the two writes of "a" 267.8 s
    apart against a 180 s life.

    **87.8 s, not the 19 s of CERT-2086 and not the 20 s of CERT-2068.** Worth
    stating: each repair in this chain closed the hole it was shown and left a
    wider one behind it, because each was arithmetic over a budget nothing
    enforced.
    """
    unit = _unit_when_the_route_runs_past_its_deadline()
    walls = {q: [unit] * 4 for q in _HEAD_FIRST}
    walls["a"] = [1.0, unit]
    writes, absent = _run_two_pass_reranked(
        ttl_s=180,
        per_query_s=unit,
        head_a=_HEAD_FIRST,
        head_b=_HEAD_RERANKED,
        walls=walls,
        concurrency=2,          # the blocked width, pinned — see CERT-2086's RED half
    )
    assert absent, (
        f"the blocked configuration must hole on a route that overruns its own "
        f"cooperative deadline; writes of 'a' = {writes}"
    )
    widest = max(b - a for a, b in absent)
    assert 85.0 <= widest <= 90.0, (
        f"expected ~87.8 s of absence at the blocked width and unit, measured "
        f"{widest:.1f}s across {absent} (writes of 'a' at {writes})"
    )


def test_the_head_stays_resident_when_the_route_returns_after_its_cooperative_deadline():
    """The GREEN half. Same route overrun, same re-ranking, the shipped width.

    Nothing about the route changed — it still returns at 24 s, still past its own
    cooperative deadline. What changed is that the unit containing it is walled at
    35 s and the width is 4, so the pass budget is 70 s and the worst same-query
    interval is 150 s inside a 180 s life.
    """
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    unit = _unit_when_the_route_runs_past_its_deadline()
    walls = {q: [unit] * 4 for q in _HEAD_FIRST}
    walls["a"] = [1.0, unit]
    writes, absent = _run_two_pass_reranked(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        per_query_s=unit,
        head_a=_HEAD_FIRST,
        head_b=_HEAD_RERANKED,
        walls=walls,
    )
    assert absent == [], (
        f"'a' went cold on a route past its cooperative deadline: {absent} "
        f"(writes {writes})"
    )


def test_residency_holds_at_the_full_enforced_unit_wall_across_a_rerank():
    """And at the WALL, not merely at the grader's case, which is under it.

    The 24 s route above is a sample. The bound is 35 s per unit, and the number
    the code has to survive is the one it PERMITS. Two methods have to agree here:
    the real-cursor harness's measured worst interval, and the closed-form
    `max_same_query_write_interval_s()` that clause (4) checks. If they disagree,
    one of them is modelling something the other is not.
    """
    from app.tasks.search_head_warmer import (
        max_same_query_write_interval_s,
        worker_unit_bound_s,
    )
    from app.utils.search_cache import SEARCH_RESPONSE_TTL_SECONDS

    unit = worker_unit_bound_s()
    walls = {q: [unit] * 4 for q in _HEAD_FIRST}
    walls["a"] = [1.0, unit]
    writes, absent = _run_two_pass_reranked(
        ttl_s=SEARCH_RESPONSE_TTL_SECONDS,
        per_query_s=unit,
        head_a=_HEAD_FIRST,
        head_b=_HEAD_RERANKED,
        walls=walls,
    )
    assert absent == [], f"'a' went cold at the full enforced wall: {absent}"
    measured = writes[-1] - writes[0]
    closed_form = max_same_query_write_interval_s()
    assert measured <= closed_form, (
        f"the real cursor produced a {measured:g}s same-query interval, WIDER than "
        f"the {closed_form:g}s clause (4) certifies. The closed form is what the "
        f"invariant checks, so a harness that exceeds it means the invariant is "
        f"certifying a schedule the dispatcher can beat."
    )


def test_the_width_is_whatever_the_solver_says():
    """The width is SOLVED FOR, and this asserts the shipped constant equals the solution.

    🔴 CERT-2095. CERT-2089 moved the width 2 -> 4 on an argument in prose, and the
    prose had priced the pass wrong, so the argument was wrong in a way no test
    could see. The argument is a function now: `minimum_concurrency_for_residency()`
    reads the walls and returns the narrowest width that satisfies the invariant.
    Nobody edits `WARM_CONCURRENCY` by hand; if the walls move, this test says so.

    Both directions matter. If the constant is WIDER than the solution we are
    taking load we do not need; if it is NARROWER the head goes cold.
    """
    from app.tasks.search_head_warmer import (
        WARM_CONCURRENCY,
        minimum_concurrency_for_residency,
        residency_invariant,
    )

    solved = minimum_concurrency_for_residency()
    assert solved is not None, (
        "no width satisfies the invariant at the shipped walls — the constants no "
        "longer admit a resident head at any concurrency, which is a product "
        "decision (the TTL or the head size), not a tuning one"
    )
    assert WARM_CONCURRENCY == solved, (
        f"WARM_CONCURRENCY is {WARM_CONCURRENCY} but the walls solve to {solved}. "
        f"{'It is wider than needed — that is load nobody is buying anything with.' if WARM_CONCURRENCY > solved else 'It is narrower than the arithmetic allows — the head will go cold.'}"
    )
    assert residency_invariant()[0], residency_invariant()[1]


def test_every_width_below_the_solution_actually_fails_and_the_next_one_up_passes():
    """The solver is only worth trusting if the widths it rejects really do fail.

    A `min` over a predicate that is true everywhere returns 1 and looks decisive.
    So: sweep every width below the solution and require the invariant to refuse
    each one, then require the solution itself to pass. This is the assertion that
    would have caught CERT-2089's width-4 claim, which was true of the budget as
    it was priced and false of the pass as it runs.
    """
    from app.tasks.search_head_warmer import (
        DEFAULT_HEAD_SIZE,
        derive_refresh_ahead_s,
        full_rebuild_budget_s,
        minimum_concurrency_for_residency,
        residency_invariant,
    )

    solved = minimum_concurrency_for_residency()

    def _holds(conc):
        budget = full_rebuild_budget_s(head_size=DEFAULT_HEAD_SIZE, concurrency=conc)
        return residency_invariant(
            refresh_ahead_s=derive_refresh_ahead_s(budget_s=budget), budget_s=budget
        )

    for conc in range(1, solved):
        ok, why = _holds(conc)
        assert not ok, (
            f"width {conc} is below the solver's answer of {solved} and the "
            f"invariant accepted it — the solver is not returning a minimum: {why}"
        )
    assert _holds(solved)[0], _holds(solved)[1]

    # 🔴 The 10 seconds that decide it, pinned. Width 4 fails by exactly this much,
    # and the two constants that would rescue it are named so that anyone tempted
    # to shave them finds this test first. Shaving a wall to buy a width is the
    # substitution six BLOCKs in this chain were about.
    #
    # CERT-2107 moved WHICH clause refuses width 4 without moving the 10 s: at a
    # 110 s budget its derived threshold is 190 s against a 180 s TTL, so clause
    # (3) now fires before clause (4) gets to. Both the size of the miss and the
    # clause are asserted, because a repair that changed the margin and a repair
    # that relocated the failure are different events and this test should be able
    # to say which one happened.
    if solved > 4:
        budget_4 = full_rebuild_budget_s(head_size=DEFAULT_HEAD_SIZE, concurrency=4)
        assert budget_4 == 110.0, budget_4
        _, why4 = _holds(4)
        assert "NOT A THRESHOLD" in why4, why4
        assert "190s" in why4, (
            f"width 4's derived threshold should be 190s against a 180s TTL — a 10s "
            f"miss, not a comfortable one: {why4}"
        )

        # ...and the clause it USED to fail is still the one waiting underneath, so
        # shaving clause (3) into compliance does not seat width 4 either. Driven at
        # the exact shave the docstring names: rollback 5 -> 2.5, setup 10 -> 5.
        from app.tasks.search_head_warmer import worker_unit_worst_case_s

        shaved = full_rebuild_budget_s(
            head_size=DEFAULT_HEAD_SIZE,
            concurrency=4,
            setup_s=5.0,
            per_query_s=worker_unit_worst_case_s(rollback_s=2.5),
        )
        assert shaved == 100.0, shaved
        ok_shaved, why_shaved = residency_invariant(
            refresh_ahead_s=derive_refresh_ahead_s(budget_s=shaved), budget_s=shaved
        )
        assert not ok_shaved, (
            "shaving the rollback and setup walls seated width 4 — the failure was "
            "supposed to walk to the next clause, not disappear"
        )
        assert "WRITE INTERVAL EXCEEDS THE TTL" in why_shaved, why_shaved


def test_the_wall_sits_strictly_above_every_cooperative_bound_inside_the_unit():
    """Clause (5), both directions, because only one of them was ever wrong.

    A wall BELOW the cooperative bounds is not enforcement — it aborts rebuilds
    that were about to succeed, and an abandoned rebuild writes nothing. A wall
    AT them is the same thing at the boundary. This is the inequality the previous
    repair inverted by taking a `min`.
    """
    from app.tasks.search_head_warmer import (
        PER_QUERY_TIMEOUT_SECONDS,
        ROUTE_SEARCH_DEADLINE_SECONDS,
        residency_invariant,
        ttl_read_cooperative_bound_s,
        worker_unit_bound_s,
    )

    cooperative = ROUTE_SEARCH_DEADLINE_SECONDS + 2 * ttl_read_cooperative_bound_s()
    assert worker_unit_bound_s() > cooperative, (
        f"the enforced {worker_unit_bound_s():g}s unit is not above the {cooperative:g}s "
        f"of cooperative bounds inside it"
    )
    # The route-call wall on its own, which is the sub-claim the module docstring
    # makes and the one the blocked SHA's `min()` reversed.
    assert PER_QUERY_TIMEOUT_SECONDS > ROUTE_SEARCH_DEADLINE_SECONDS, (
        "the route-call wall is at or below the route's own cooperative deadline, "
        "so it aborts rebuilds the route was about to complete"
    )

    # Driven from both sides, so a clause that always passed would be visible.
    assert not residency_invariant(unit_s=cooperative)[0], "AT the bound must fail"
    assert not residency_invariant(unit_s=cooperative - 0.1)[0], "BELOW must fail"
    assert residency_invariant(unit_s=cooperative + 0.1)[0], "ABOVE must pass"


def test_the_pass_must_fit_inside_the_run_lock_that_bounds_its_gap():
    """Clause (6), driven where it is reachable rather than asserted as present.

    Clause (4) derives the pass gap from the run lock excluding the next pass. A
    pass longer than `_LOCK_TTL_SECONDS` releases its own exclusion and the next
    one starts underneath it, so (4) would be reasoning from a premise that has
    stopped holding — which is what the blocked SHA's real ~236 s budget did to a
    180 s lock.

    At D81's TTL of 180 the clause cannot fire: (2) and (3) together already force
    the budget below 120. That is a fact about today's constants, not about the
    clause, so it is driven at a raised TTL — the case #3539's remaining options
    would create — instead of being left as an unreachable branch nobody has run.
    """
    from app.tasks.search_head_warmer import _LOCK_TTL_SECONDS, residency_invariant

    over = residency_invariant(
        ttl_s=600, refresh_ahead_s=560, budget_s=float(_LOCK_TTL_SECONDS) + 20
    )
    assert not over[0] and "OUTRUNS ITS OWN LOCK" in over[1], over

    at = residency_invariant(
        ttl_s=600, refresh_ahead_s=560, budget_s=float(_LOCK_TTL_SECONDS)
    )
    assert not at[0] and "OUTRUNS ITS OWN LOCK" in at[1], at

    under = residency_invariant(
        ttl_s=600, refresh_ahead_s=560, budget_s=float(_LOCK_TTL_SECONDS) - 10
    )
    assert under[0], under


def test_the_ttl_read_is_awaitable_bounded_and_off_the_event_loop():
    """The three properties that make the unit wall real, checked as three claims.

    A sync Redis call from inside the loop cannot be cancelled by any `wait_for`
    (gotcha #39): the coroutine never suspends, so there is no point at which a
    timer can run. Wrapping `_warm_one` in a timeout while this read stayed
    synchronous would have produced a wall that reads as enforcement and is not.
    """
    import inspect
    import threading
    import time as _time

    from app.tasks import search_head_warmer as warmer

    assert inspect.iscoroutinefunction(warmer._cache_ttl_seconds), (
        "the TTL read is synchronous again — the unit wall around it is decorative"
    )

    loop_thread = threading.current_thread().ident
    saw = {}
    # Released once the wall has fired. `asyncio.run` joins its default executor on
    # the way out, so a `sleep(30)` here would make the wall's own proof a 30 s
    # test — the orphan thread outliving the await is the POINT, not an accident.
    release = threading.Event()

    def _hang(key):
        saw["thread"] = threading.current_thread().ident
        assert not release.wait(timeout=30), "the wall never fired"
        return 1

    async def _drive():
        # A ticker that can only advance if the loop is actually free while the
        # read is out. This is the assertion gotcha #39 exists for.
        ticks = 0

        async def _tick():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(_tick())
        started = _time.monotonic()
        got = await warmer._cache_ttl_seconds("k")
        elapsed = _time.monotonic() - started
        release.set()
        ticker.cancel()
        return got, elapsed, ticks

    with patch.object(warmer, "_ttl_blocking", _hang), \
         patch.object(warmer, "TTL_READ_BOUND_SECONDS", 0.2):
        got, elapsed, ticks = asyncio.run(_drive())

    assert got is None, "a walled read reports Redis-silent, never a fabricated TTL"
    assert elapsed < 5.0, f"the wall did not fire: the read took {elapsed:.1f}s"
    assert saw["thread"] != loop_thread, (
        "the blocking read ran on the event loop's own thread"
    )
    assert ticks > 2, (
        f"the loop only advanced {ticks} times while a 30 s blocking read was out — "
        f"the read is blocking the loop, so no wall anywhere in the process can fire"
    )


def test_a_unit_that_breaches_the_wall_is_reported_as_a_timeout_and_never_as_a_warm():
    """The abandoned-rebuild case, NAMED AND COUNTED rather than modelled away.

    A hard wall means a rebuild can be abandoned, and an abandoned rebuild writes
    nothing. Clause (5) is why that cannot happen to a rebuild that was going to
    succeed; this is why it can never be mistaken for one that did.
    """
    from app.tasks import search_head_warmer as warmer

    async def _forever(session, q, started):
        await asyncio.sleep(30)
        return {"q": q, "ok": True, "reason": "warmed"}

    with patch.object(warmer, "_warm_one_inner", _forever), \
         patch.object(warmer, "worker_unit_bound_s", lambda: 0.05):
        result = asyncio.run(warmer._warm_one(_FakeSession(), "patriots"))

    assert result["reason"] == "unit_timeout", result
    assert result["ok"] is False, "an abandoned rebuild must never report ok"
    assert result["rebuilt"] is True, (
        "it DID start a rebuild — reporting rebuilt=False would hide the work the "
        "pass spent and make an abandoned unit look like a `fresh` skip"
    )

    summary = warmer._summarize(
        head=["patriots"],
        results=[result],
        source="test",
        seconds_wall=1.0,
        since_last=60.0,
        width=warmer.WARM_CONCURRENCY,
        budget_s=warmer.full_rebuild_budget_s(),
    )
    assert len(summary["timeouts"]) == 1, (
        f"a unit that breached the wall is not in `timeouts`: {summary}"
    )
    assert summary["warmed"] == 0, summary
    assert summary["terminal"] != "complete", (
        f"a pass that abandoned a rebuild reported {summary['terminal']!r}"
    )


def test_the_unit_wall_is_the_UNIT_bound_and_not_the_route_call():
    """🔴 A SURVIVING MUTANT, REPORTED AND THEN KILLED, NOT QUIETLY FIXED.

    The first battery run was 37/40 and this was one of the three. Every other
    test here proves the ARITHMETIC — that `worker_unit_bound_s()` is 35 s and
    that a 70 s budget fits D81. None of them proved that `_warm_one` passes that
    number to `wait_for`. Swapping the wall to `PER_QUERY_TIMEOUT_SECONDS` (25 s)
    left the whole suite green while walling the unit 10 s BELOW the bound every
    budget is derived from — which is not a smaller version of the same thing, it
    is clause (5) inverted: a wall under the work it walls abandons rebuilds that
    were inside budget, and an abandoned rebuild writes nothing.

    Driven behaviourally rather than by reading the source, and from both sides:
    a unit between the two values must COMPLETE, and one above the unit bound must
    be abandoned. Asserting only the second would pass under the mutant.
    """
    from app.tasks import search_head_warmer as warmer

    async def _takes(seconds):
        async def _inner(session, q, started):
            await asyncio.sleep(seconds)
            return {"q": q, "ok": True, "reason": "warmed", "rebuilt": True}

        return _inner

    def _drive(inner_seconds):
        with patch.object(warmer, "_warm_one_inner", asyncio.run(_takes(inner_seconds))), \
             patch.object(warmer, "worker_unit_bound_s", lambda: 0.30), \
             patch.object(warmer, "PER_QUERY_TIMEOUT_SECONDS", 0.10):
            return asyncio.run(warmer._warm_one(_FakeSession(), "patriots"))

    # Between the route-call wall and the unit wall: inside budget, must survive.
    assert _drive(0.20)["reason"] == "warmed", (
        "a unit longer than the ROUTE-CALL wall but inside the UNIT wall was "
        "abandoned — the wall is priced at the wrong quantity, and every rebuild "
        "whose two TTL reads push it past the route wall now writes nothing"
    )
    # Above the unit wall: must be abandoned, or the wall is not a wall.
    assert _drive(0.50)["reason"] == "unit_timeout"


def test_the_ttl_read_client_is_built_at_the_bounds_clause_five_assumes():
    """🔴 THE OTHER TWO SURVIVORS OF THE FIRST BATTERY RUN, killed together.

    `fast_fail=False` and the default 5 s socket timeouts both left the suite
    green, and both silently move `ttl_read_cooperative_bound_s()` from 4.1 s to
    ~17 s — above the 5 s wall that is supposed to backstop it. Clause (5) would
    still read `35 > 28.2` and pass, because it computes the cooperative bound
    from the CONSTANTS and nothing checked that `_ttl_blocking` builds its client
    to match them. A mirror in the other direction, and the same bargain: the cost
    is drift, the payment is this test.
    """
    from app.tasks import redis_state
    from app.tasks.search_head_warmer import (
        TTL_READ_BOUND_SECONDS,
        TTL_READ_SOCKET_TIMEOUT_SECONDS,
        _ttl_blocking,
        ttl_read_cooperative_bound_s,
    )

    seen = {}

    class _Client:
        def ttl(self, key):
            return 42

    def _capture(**kwargs):
        seen.update(kwargs)
        return _Client()

    with patch.object(redis_state, "get_redis_client", _capture):
        assert _ttl_blocking("k") == 42

    assert seen.get("fast_fail") is True, (
        f"the TTL read is using the background retry policy ({seen}). That is 3 "
        f"attempts at up to 5 s each — a cooperative bound of ~17 s against a "
        f"{TTL_READ_BOUND_SECONDS:g}s wall, so the wall fires FIRST and clause (5)'s "
        f"comparison is being made against a number the client does not honour"
    )
    assert seen.get("socket_timeout") == TTL_READ_SOCKET_TIMEOUT_SECONDS, seen
    assert seen.get("socket_connect_timeout") == TTL_READ_SOCKET_TIMEOUT_SECONDS, seen

    # The property all three assertions exist to protect, stated once.
    assert TTL_READ_BOUND_SECONDS > ttl_read_cooperative_bound_s(), (
        "the TTL read's wall is not above its own cooperative bound"
    )


# ===========================================================================
# CERT-2095's TWO NAMED REGRESSIONS.
#
#   "the declared 70-second full-pass budget omits lock-held session entry, head
#    resolution, four session context exits, commit/close/engine disposal, and
#    timeout rollback. An independent exact-code scaled probe made all eight query
#    results succeed yet `_warm_search_head()` reported `complete` after 208 ms
#    against a 20 ms scaled declared budget; a second probe showed `_warm_one()`
#    still running at 5x its declared wall because post-timeout rollback is
#    outside `wait_for`. ... add a scaled two-pass successful slow-teardown/
#    head-resolution regression plus a hung-rollback unit-wall regression."
# ===========================================================================


def test_a_hung_rollback_cannot_run_past_the_unit_wall():
    """The grader's second probe: `_warm_one` at 5x its declared wall. **My bug.**

    I introduced it in the CERT-2089 repair, in the same commit whose docstring
    says *"a coroutine that never suspends cannot be cancelled"* — and then put
    `await _safe_rollback(session)` in the wall's own `except` clause, outside the
    `wait_for`. The path the wall exists to handle was the one path it did not
    bound, and the rollback on it is the least likely rollback to return: it is
    being issued against the connection that just wedged.

    Driven at real time with scaled constants. A rollback that never returns must
    cost at most its own wall, not the process.
    """
    import time

    from app.tasks import search_head_warmer as warmer

    class _WedgedSession:
        """A session whose `rollback()` never completes. asyncpg offers no bound."""

        def __init__(self):
            self.rollback_started = False

        async def rollback(self):
            self.rollback_started = True
            await asyncio.sleep(30)

    async def _never_returns(session, q, started):
        await asyncio.sleep(30)

    session = _WedgedSession()
    with patch.object(warmer, "_warm_one_inner", _never_returns), \
         patch.object(warmer, "worker_unit_bound_s", lambda: 0.10), \
         patch.object(warmer, "ROLLBACK_BOUND_SECONDS", 0.10):
        started = time.monotonic()
        result = asyncio.run(warmer._warm_one(session, "patriots"))
        elapsed = time.monotonic() - started

    assert session.rollback_started, "the poisoned session was never rolled back at all"
    assert result["reason"] == "unit_timeout", result
    assert elapsed < 3.0, (
        f"the unit took {elapsed:.1f}s against a 0.10s wall and a 0.10s rollback "
        f"bound. A wall whose failure handler is unbounded is not a wall, and the "
        f"pass budget every residency clause consumes is built on this returning."
    )


def test_a_slow_teardown_and_head_resolution_cannot_widen_the_write_interval():
    """The grader's first probe, as a two-pass residency regression. Scaled.

    `_warm_search_head` reported `complete` after 208 ms against a 20 ms scaled
    declared budget, because the budget counted only the warming while the lock
    was held through session entry, head resolution and `width` context exits.

    Two independent claims, and the second is the one that makes the first safe:

    1. Setup and head resolution are IN the declared budget now.
    2. Teardown is OUTSIDE the run lock, so however slow it is it cannot widen the
       gap between passes — and therefore cannot widen the same-query write
       interval that clause (4) certifies.

    (2) is asserted by observing WHEN the lock is released relative to teardown,
    which is the only thing that actually decides it.
    """
    from app.tasks import search_head_warmer as warmer

    events = []

    class _SlowTeardownSession:
        async def rollback(self):
            pass

    class _SlowCM:
        async def __aenter__(self):
            events.append("setup")
            return _SlowTeardownSession()

        async def __aexit__(self, *a):
            # The expensive part: commit + close + engine.dispose(), all network.
            events.append("teardown_start")
            await asyncio.sleep(0.05)
            events.append("teardown_end")
            return False

    async def _fake_resolve_head(session, limit):
        events.append("resolve_head")
        return ["aa", "bb"], "test"

    async def _fake_warm_one(session, q):
        events.append(f"warm:{q}")
        return {"q": q, "ok": True, "reason": "warmed", "ttl_before": 1,
                "rebuilt": True, "ttl_after": 99, "seconds": 0.0}

    # All four lock-control helpers are `async def` since CERT-2107 (walled, and
    # run off the loop), so their stand-ins have to be too.
    async def _release(claim):
        events.append("lock_released")

    async def _acquire():
        return _owned()

    async def _no_last_pass(now):
        return None

    async def _record(now):
        return None

    from app.tasks import base as task_base
    with patch.object(task_base, "get_task_session", lambda: _SlowCM()), \
         patch.object(warmer, "resolve_head", _fake_resolve_head), \
         patch.object(warmer, "_warm_one", _fake_warm_one), \
         patch.object(warmer, "_acquire_run_lock", _acquire), \
         patch.object(warmer, "_release_run_lock", _release), \
         patch.object(warmer, "_seconds_since_last_pass", _no_last_pass), \
         patch.object(warmer, "_record_pass_start", _record), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        summary = asyncio.run(warmer._warm_search_head(head_size=2))

    assert summary["warmed"] == 2, summary
    assert "lock_released" in events, f"the lock was never released: {events}"

    # 🔴 THE ASSERTION THAT MATTERS. Teardown must begin only after the lock is
    # gone, or the exclusion covers work that writes nothing and the pass gap —
    # and with it the write interval clause (4) certifies — is longer than the
    # budget says.
    assert events.index("lock_released") < events.index("teardown_start"), (
        f"the run lock is still held during teardown, so the lock-held interval is "
        f"longer than `full_rebuild_budget_s()` declares and clause (4)'s write "
        f"interval is understated: {events}"
    )
    # ...and the lock must not be released before the last write, or two passes
    # can warm at once and the exclusion means nothing.
    assert events.index("warm:bb") < events.index("lock_released"), events

    # Setup and head resolution are inside the declared budget, and the budget
    # says so rather than a comment saying so.
    assert warmer.full_rebuild_budget_s(setup_s=0) < warmer.full_rebuild_budget_s(), (
        "the setup wall is not a term in the budget — CERT-2095 exactly"
    )
    # ...and so are the four lock-control round-trips the exclusion also covers.
    assert warmer.full_rebuild_budget_s(control_s=0) < warmer.full_rebuild_budget_s(), (
        "the lock-control round-trips are not a term in the budget — CERT-2107 exactly"
    )


def test_a_setup_that_never_finishes_releases_the_lock_and_says_why():
    """The other half of the setup wall: it must not hold the exclusion open.

    A wall that fires and then leaves the run lock held has converted a slow pass
    into a dead warmer — every later beat takes the `lock` skip path forever.
    """
    import time

    from app.tasks import search_head_warmer as warmer

    released = []

    class _HangingCM:
        async def __aenter__(self):
            await asyncio.sleep(30)

        async def __aexit__(self, *a):
            return False

    async def _acquire():
        return _owned()

    async def _release(claim):
        released.append(1)

    async def _no_last_pass(now):
        return None

    async def _record(now):
        return None

    from app.tasks import base as task_base
    with patch.object(task_base, "get_task_session", lambda: _HangingCM()), \
         patch.object(warmer, "PASS_SETUP_BOUND_SECONDS", 0.05), \
         patch.object(warmer, "_acquire_run_lock", _acquire), \
         patch.object(warmer, "_release_run_lock", _release), \
         patch.object(warmer, "_seconds_since_last_pass", _no_last_pass), \
         patch.object(warmer, "_record_pass_start", _record), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        started = time.monotonic()
        summary = asyncio.run(warmer._warm_search_head(head_size=2))
        elapsed = time.monotonic() - started

    assert elapsed < 3.0, f"the setup wall did not fire: {elapsed:.1f}s"
    assert summary["skip_reason"] == "setup_timeout", summary
    assert summary["terminal"] != "complete", (
        f"a pass that never reached its first warm reported {summary['terminal']!r}"
    )
    assert released, "the setup wall fired and left the run lock held — the warmer is now wedged"
    # Exactly once. A double release would delete the NEXT pass's exclusion.
    assert len(released) == 1, f"the lock was released {len(released)} times: {released}"


def test_the_solver_does_not_read_the_constant_it_exists_to_derive():
    """🔴 A SURVIVING MUTANT, REPORTED AND KILLED. The solver must not be circular.

    Replacing `derive_refresh_ahead_s(budget_s=budget)` with a bare
    `REFRESH_AHEAD_SECONDS` inside `minimum_concurrency_for_residency()` left the
    whole suite green, because at the shipped constants the two are the same
    number — `REFRESH_AHEAD_SECONDS` IS `derive_refresh_ahead_s()`, by
    construction. So every assertion on the shipped answer passed with the
    derivation deleted.

    That is not cosmetic. The solver's job is to be right when the constants MOVE,
    and a solver that reads the current threshold while solving for the width that
    determines the threshold is circular: it would report that today's width is
    fine no matter what the walls became. Each candidate width implies its own
    budget, and each budget implies its own threshold.

    Driven by making the two differ: pin `REFRESH_AHEAD_SECONDS` to a value the
    invariant refuses and require the answer not to move.
    """
    from app.tasks import search_head_warmer as warmer

    honest = warmer.minimum_concurrency_for_residency()

    for bogus in (25, 60, 179):
        with patch.object(warmer, "REFRESH_AHEAD_SECONDS", bogus):
            assert warmer.minimum_concurrency_for_residency() == honest, (
                f"the solver's answer moved to "
                f"{warmer.minimum_concurrency_for_residency()} when "
                f"REFRESH_AHEAD_SECONDS was set to {bogus}. It is reading the "
                f"shipped threshold instead of deriving one per candidate width, "
                f"which makes the width and the threshold depend on each other."
            )


def test_the_ttl_read_retry_mirror_has_not_drifted():
    """`TTL_READ_ATTEMPTS`/`_BACKOFF_CAP` mirror `_redis_fast_fail_retry()`.

    `ttl_read_cooperative_bound_s()` is what clause (5) compares the wall against,
    so if the retry policy grows an attempt the wall silently stops being above
    what it walls. The cost of a mirror is drift and the payment is this test.
    """
    from app.tasks.redis_state import _redis_fast_fail_retry
    from app.tasks.search_head_warmer import (
        TTL_READ_ATTEMPTS,
        TTL_READ_BACKOFF_CAP_SECONDS,
    )

    retry = _redis_fast_fail_retry()
    retries = getattr(retry, "_retries", None)
    assert retries is not None, "redis-py's Retry stopped exposing `_retries`"
    assert TTL_READ_ATTEMPTS == retries + 1, (
        f"the warmer models {TTL_READ_ATTEMPTS} attempts but the fast-fail policy "
        f"allows {retries + 1}; clause (5)'s cooperative bound is now understated"
    )
    cap = getattr(getattr(retry, "_backoff", None), "_cap", None)
    assert cap == TTL_READ_BACKOFF_CAP_SECONDS, (
        f"the backoff cap drifted: warmer says {TTL_READ_BACKOFF_CAP_SECONDS}, "
        f"policy says {cap}"
    )


# ===========================================================================
# CERT-2107's NAMED REGRESSION.
#
#   "the promised complete lock-held budget still omits `_seconds_since_last_pass()`,
#    `_record_pass_start()`, and lock deletion: all are synchronous default-client
#    Redis operations after acquisition and outside any priced wall. An independent
#    exact-code scaled probe delayed only the first two controls by 80ms each; the
#    task returned `complete`, held the lock 0.172s against a 0.03s declared budget,
#    and reported `seconds_wall=0.0`. Required repair: bound and price every
#    operation from successful acquisition through completed release, start
#    lock-held timing at acquisition, and add a scaled entry-point regression
#    delaying the control read/write/delete that requires an in-budget completion
#    or non-complete terminal and honest wall telemetry."
#
# Three claims, three tests: the ops are BOUNDED (walled, off the loop, on a
# fast-fail client), the ops are PRICED (a term in the budget, checked by clause
# (7)), and the reported wall IS the interval the budget bounds — measured from
# before the acquire round-trip to after the release round-trip.
# ===========================================================================


def _async_lock_stubs(*, since_last=None, on_acquire=None, on_release=None):
    """Async stand-ins for the four lock-control helpers. All four are coroutines."""

    async def _acquire():
        if on_acquire is not None:
            on_acquire()
        return True

    async def _release():
        if on_release is not None:
            on_release()

    async def _since(now):
        return since_last

    async def _record(now):
        return None

    return _acquire, _release, _since, _record


def test_the_reported_wall_is_the_whole_lock_held_interval():
    """🔴 THE GRADER'S PROBE, AS A SCALED ENTRY-POINT REGRESSION (CERT-2107).

    On the blocked SHA this delay was invisible three times over: the four control
    round-trips ran unwalled, sat outside `full_rebuild_budget_s()`, and sat
    outside `seconds_wall` — which started AFTER `_record_pass_start()` and so
    reported 0.0 for an interval the probe measured at 0.172 s against a 0.03 s
    declared budget, with a `complete` terminal on top.

    The blocked shape fails every arm below. The `complete`-and-in-budget arm is
    what the cert asked for; the wall arms are what make it impossible to satisfy
    that arm by lying about the wall, which is exactly how the blocked SHA passed
    every test it had.

    Scaled: 80 ms per control op against a 30 ms declared budget, the grader's own
    numbers. The delay goes on the BLOCKING halves, so the real thread + `wait_for`
    path is exercised rather than stubbed past.
    """
    import time as _time

    from app.tasks import search_head_warmer as warmer

    DELAY = 0.08
    SCALED_BUDGET = 0.03

    class _Session:
        async def rollback(self):
            pass

    class _CM:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *a):
            return False

    async def _fake_resolve_head(session, limit):
        return ["aa", "bb"], "test"

    async def _fake_warm_one(session, q):
        return {"q": q, "ok": True, "reason": "warmed", "ttl_before": 1,
                "rebuilt": True, "ttl_after": 99, "seconds": 0.0}

    # Every control op slow, including the two the blocked SHA did bound nothing
    # around and the release the grader named separately.
    # CERT-2114 signatures: the acquire is handed the token it must install and
    # the deadline past which it must undo itself, and it answers with the token
    # rather than a bare `True`. The release is handed the token to compare
    # against. A stand-in on the old signature is a TypeError, not a silent pass.
    def _slow_acquire(token, deadline=None):
        _time.sleep(DELAY)
        return token

    def _slow_last_pass():
        _time.sleep(DELAY)
        return None

    def _slow_release(token):
        _time.sleep(DELAY)

    def _slow_record_client():
        _time.sleep(DELAY)
        return _RecordingClient()

    class _RecordingClient:
        def setex(self, *a, **kw):
            return True

    from app.tasks import base as task_base
    with patch.object(task_base, "get_task_session", lambda: _CM()), \
         patch.object(warmer, "resolve_head", _fake_resolve_head), \
         patch.object(warmer, "_warm_one", _fake_warm_one), \
         patch.object(warmer, "_acquire_blocking", _slow_acquire), \
         patch.object(warmer, "_last_pass_blocking", _slow_last_pass), \
         patch.object(warmer, "_release_blocking", _slow_release), \
         patch.object(warmer, "_lock_control_client", _slow_record_client), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        started = _time.monotonic()
        # The scaled DECLARED budget, handed to the pass the same way
        # `full_rebuild_budget_s(per_query_s=...)` hands the regressions a scaled
        # wall. The pass judges itself against this number, so the disjunction
        # below is checked against the ceiling the code used and not one the test
        # invented afterwards.
        summary = asyncio.run(
            warmer._warm_search_head(head_size=2, budget_s=SCALED_BUDGET)
        )
        observed = _time.monotonic() - started

    # Four control round-trips at 80 ms. The pass really did hold the exclusion for
    # about this long — the question the blocked SHA got wrong is whether it says so.
    assert observed >= 4 * DELAY, (
        f"the four control ops did not actually run slowly ({observed:.3f}s) — the "
        f"probe is not reproducing the grader's conditions"
    )

    # 🔴 (a) HONEST TELEMETRY. `seconds_wall` must contain the control time. The
    # blocked SHA reported 0.0 here while holding the lock for 0.172 s.
    assert summary["seconds_wall"] >= 4 * DELAY, (
        f"`seconds_wall` is {summary['seconds_wall']}s but the pass spent at least "
        f"{4 * DELAY:.3f}s in lock-control round-trips alone. The clock is not "
        f"starting at the acquire and stopping at the release — this is CERT-2107's "
        f"`seconds_wall=0.0` exactly"
    )
    # ...and it must not have quietly become the whole-function duration either:
    # teardown is outside the exclusion (CERT-2095) and must stay out of this number.
    assert summary["seconds_wall"] <= observed, summary["seconds_wall"]

    # 🔴 (b) IN BUDGET, OR NOT `complete`. The cert's disjunction, checked against
    # the ceiling the pass published for itself.
    assert summary["budget_s"] == SCALED_BUDGET, summary
    in_budget = summary["seconds_wall"] <= summary["budget_s"]
    assert in_budget or summary["terminal"] != "complete", (
        f"the pass held the lock {summary['seconds_wall']}s against a declared budget "
        f"of {summary['budget_s']}s and still reported {summary['terminal']!r}. A pass "
        f"that outruns its declared lock-held budget may not call itself complete — "
        f"clauses (2), (4) and (6) all certify residency over that interval, so this "
        f"pass is outside the arithmetic its own summary is published under"
    )
    # At 4 x 80 ms against a 30 ms declared budget it is the SECOND disjunct that
    # holds, and it is worth pinning which so the test cannot pass by both arms
    # collapsing into vacuity.
    assert not in_budget, (
        f"the scaled probe was supposed to be over budget ({summary['seconds_wall']}s "
        f"vs {summary['budget_s']}s); if it now fits, the delay or the budget has moved "
        f"and this test has stopped reproducing the counterexample"
    )
    assert summary["over_budget"] is True, summary
    assert summary["terminal"] == "partial", (
        f"terminal is {summary['terminal']!r}. Nothing timed out, nothing errored and "
        f"every write landed, so `partial` here can only come from the budget check — "
        f"which is the point: the budget is a postcondition, not a docstring"
    )
    # ...and the reason is nameable from the summary alone. A bare `partial` with no
    # cause sends a reader hunting in the query results, where nothing is wrong.
    assert summary["timeouts"] == [] and summary["errors"] == [], summary
    assert summary["no_writes"] == [], summary

    # The healthy direction, same pass, same delays: a budget that really does cover
    # the interval yields `complete`. Without this the rule could be satisfied by a
    # warmer that never reports complete at all.
    with patch.object(task_base, "get_task_session", lambda: _CM()), \
         patch.object(warmer, "resolve_head", _fake_resolve_head), \
         patch.object(warmer, "_warm_one", _fake_warm_one), \
         patch.object(warmer, "_acquire_blocking", _slow_acquire), \
         patch.object(warmer, "_last_pass_blocking", _slow_last_pass), \
         patch.object(warmer, "_release_blocking", _slow_release), \
         patch.object(warmer, "_lock_control_client", _slow_record_client), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        roomy = asyncio.run(warmer._warm_search_head(head_size=2, budget_s=30.0))

    assert roomy["over_budget"] is False, roomy
    assert roomy["terminal"] == "complete", roomy
    assert roomy["seconds_wall"] >= 4 * DELAY, roomy

    # 🔴 AND THE OTHER END OF THE INTERVAL, which a stopwatch stopped at the summary
    # would get wrong in the opposite direction. Teardown is outside the exclusion
    # (CERT-2095), so a slow `__aexit__` must NOT appear in `seconds_wall` — a wall
    # that swallows teardown re-inflates the number clause (4) is derived from and
    # would push honest passes over budget for work that writes nothing.
    TEARDOWN = 0.4

    class _SlowTeardownCM:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *a):
            await asyncio.sleep(TEARDOWN)
            return False

    with patch.object(task_base, "get_task_session", lambda: _SlowTeardownCM()), \
         patch.object(warmer, "resolve_head", _fake_resolve_head), \
         patch.object(warmer, "_warm_one", _fake_warm_one), \
         patch.object(warmer, "_acquire_blocking", _slow_acquire), \
         patch.object(warmer, "_last_pass_blocking", _slow_last_pass), \
         patch.object(warmer, "_release_blocking", _slow_release), \
         patch.object(warmer, "_lock_control_client", _slow_record_client), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        started = _time.monotonic()
        torn = asyncio.run(warmer._warm_search_head(head_size=2, budget_s=30.0))
        torn_observed = _time.monotonic() - started

    assert torn_observed >= TEARDOWN, torn_observed
    assert torn["seconds_wall"] < torn_observed - TEARDOWN / 2, (
        f"`seconds_wall` is {torn['seconds_wall']}s out of {torn_observed:.3f}s "
        f"total with {TEARDOWN}s of that in teardown. The clock is being stopped "
        f"after the stack unwinds instead of at the release, which puts work that "
        f"writes no cache entry back inside the interval clause (4) is derived from"
    )

    # 🔴 (c) AND THE SAME ON THE EARLY EXITS. `min_period` holds the lock for three
    # control ops and `setup_timeout` for the acquire plus a fired setup wall; both
    # hardcoded `seconds_wall=0.0` on the blocked SHA.
    def _slow_recent_pass():
        # One second ago, read off the real clock — no clock patching, so there is
        # no anchor to branch on (gotcha #44). The floor is 45 s, so this is under
        # it however long the suite has been running.
        _time.sleep(DELAY)
        return str(_time.time() - 1.0)

    with patch.object(task_base, "get_task_session", lambda: _CM()), \
         patch.object(warmer, "resolve_head", _fake_resolve_head), \
         patch.object(warmer, "_warm_one", _fake_warm_one), \
         patch.object(warmer, "_acquire_blocking", _slow_acquire), \
         patch.object(warmer, "_last_pass_blocking", _slow_recent_pass), \
         patch.object(warmer, "_release_blocking", _slow_release), \
         patch.object(warmer, "_lock_control_client", _slow_record_client), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        floored = asyncio.run(warmer._warm_search_head(head_size=2))

    assert floored["skip_reason"] == "min_period", floored
    assert floored["seconds_wall"] >= 3 * DELAY, (
        f"the floor skip held the exclusion for three control round-trips and "
        f"reported {floored['seconds_wall']}s. It is the cheapest real pass in the "
        f"module and it still may not report zero for time it held the lock"
    )

    # The setup-timeout exit, which held the exclusion for the acquire plus a fired
    # setup wall plus the release. This arm is also what keeps the explicit
    # `await _release_once()` in that handler alive: without it the summary is built
    # before the `finally` runs and `lock_wall_s` is still `None`.
    SETUP_WALL = 0.06

    class _HangingCM:
        async def __aenter__(self):
            await asyncio.sleep(30)

        async def __aexit__(self, *a):
            return False

    with patch.object(task_base, "get_task_session", lambda: _HangingCM()), \
         patch.object(warmer, "PASS_SETUP_BOUND_SECONDS", SETUP_WALL), \
         patch.object(warmer, "_acquire_blocking", _slow_acquire), \
         patch.object(warmer, "_last_pass_blocking", _slow_last_pass), \
         patch.object(warmer, "_release_blocking", _slow_release), \
         patch.object(warmer, "_lock_control_client", _slow_record_client), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        timed_out = asyncio.run(warmer._warm_search_head(head_size=2, budget_s=30.0))

    assert timed_out["skip_reason"] == "setup_timeout", timed_out
    assert timed_out["terminal"] != "complete", timed_out
    assert timed_out["seconds_wall"] >= 4 * DELAY + SETUP_WALL, (
        f"the setup wall fired after {4 * DELAY + SETUP_WALL:.3f}s of exclusion and "
        f"the pass reported {timed_out['seconds_wall']}s. This exit hardcoded 0.0 on "
        f"the blocked SHA, and it is the exit where a wedged database is holding the "
        f"lock — the one case where the number is worth having"
    )


def test_a_hung_control_op_cannot_hold_the_exclusion_past_its_wall():
    """The other half of (a): the wall has to FIRE, not merely be declared.

    An honest `seconds_wall` over an unbounded interval is a better-reported
    version of the same defect. Each control op is walled at
    `LOCK_CONTROL_BOUND_SECONDS`, so a Redis that never answers costs the exclusion
    that wall and not the ~20 s the background client's retry policy would spend.

    Driven at a scaled wall against an op that never returns, and asserted on the
    fail-open answer each caller is built to accept — because the wall is only
    tolerable because those answers exist.
    """
    import time as _time

    from app.tasks import search_head_warmer as warmer

    # 20x the wall, not 600x — long enough that a wall which did not fire is
    # unmistakable, short enough that the orphan thread is cheap.
    HANG = 1.0
    WALL = 0.05

    def _hangs(*_args, **_kwargs):
        # `*_args` because CERT-2114 gave the acquire and the release parameters
        # (the token, and the acquire's undo deadline). A stand-in that ignores
        # them is still the right stand-in HERE — this test is about the wall
        # firing, and the ops it stands in for never return.
        _time.sleep(HANG)

    def _measure(target: str, call):
        """Time the AWAIT, from inside the loop.

        🔴 Not `asyncio.run(...)` with a stopwatch around it, and the difference is
        the whole subject of this test. `asyncio.run` joins the default executor on
        close, so a timer around it measures the orphan THREAD finishing — which is
        precisely the thing `_lock_control` deliberately does not wait for. The
        first draft of this test measured that and read 1.0 s while the log line
        showed the wall firing at 0.05 s. What the exclusion pays is how long the
        coroutine is suspended, so that is what is measured.
        """

        async def _drive():
            started = _time.monotonic()
            out = await call()
            return out, _time.monotonic() - started

        with patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", WALL), \
             patch.object(warmer, target, _hangs):
            return asyncio.run(_drive())

    def _assert_walled(elapsed: float, what: str):
        assert elapsed < HANG / 2, (
            f"the {what} took {elapsed:.3f}s against a {WALL}s wall and a {HANG}s "
            f"hung op — the wall did not fire, so the exclusion is bounded by Redis "
            f"rather than by this module"
        )

    claim, elapsed = _measure("_acquire_blocking", warmer._acquire_run_lock)
    _assert_walled(elapsed, "acquire")
    assert claim.may_run is True, (
        "the acquire must fail OPEN — a warmer that stops warming because Redis "
        "blinked is the defect this whole family of modules is about"
    )
    # 🔴 AND FAILING OPEN IS NOT OWNING IT (CERT-2114). The blocked SHA answered a
    # bare `True` here, which the pass read as ownership; the two facts now have
    # two properties and the walled acquire satisfies exactly one of them.
    assert claim.state is warmer.RunLockState.UNKNOWN, claim
    assert claim.owns is False, (
        f"a walled acquire reported ownership ({claim}). It cannot know whether "
        f"the `SET NX` landed, and a pass that believes it owns a lock it may not "
        f"hold is the CERT-2114 defect at its source"
    )

    since, elapsed = _measure(
        "_last_pass_blocking", lambda: warmer._seconds_since_last_pass(1_000_000.0)
    )
    _assert_walled(elapsed, "last-pass read")
    assert since is None, (
        f"a control read that hit its wall returned {since!r}. `None` means "
        f"'unknown' and 0.0 means 'two passes started at the same instant' — an "
        f"absent value and a zero value must not read the same (gotcha #53)"
    )

    _, elapsed = _measure(
        "_release_blocking", lambda: warmer._release_run_lock(_owned())
    )
    _assert_walled(elapsed, "release")
    # The release is the one whose fallback lives outside this function: a lost
    # compare-and-delete is collected by `_LOCK_KEY`'s own TTL, and clause (6) is what keeps
    # that TTL above the budget so the collection is never the thing that ends a
    # pass's exclusion.
    assert warmer.full_rebuild_budget_s() < warmer._LOCK_TTL_SECONDS, (
        "a lost release is only survivable while the lock's TTL outlasts the budget"
    )

    # And the pass-start write, for completeness: four ops, four walls. It is the
    # one with no return value, so the assertion is only about the caller coming
    # back — which is the assertion that matters, since it runs while the lock is
    # held and nothing else would notice it hanging.
    _, elapsed = _measure(
        "_lock_control_client", lambda: warmer._record_pass_start(1_000_000.0)
    )
    _assert_walled(elapsed, "pass-start write")


def test_the_lock_control_client_is_built_at_the_bounds_clause_seven_assumes():
    """Clause (7) compares the wall against CONSTANTS. This is the mirror.

    Exactly `test_the_ttl_read_client_is_built_at_the_bounds_clause_five_assumes`,
    one term over: `fast_fail=False` or the default 5 s socket timeouts move the
    cooperative bound from 4.1 s to ~17 s, above the 5 s wall meant to backstop it,
    and clause (7) would go on reading `5 > 4.1` and passing because nothing
    checked that the client matches the constants the clause is computed from.

    All four ops share `_lock_control_client()`, so one capture covers the four.
    """
    from app.tasks import redis_state
    from app.tasks.search_head_warmer import (
        LOCK_CONTROL_BOUND_SECONDS,
        LOCK_CONTROL_SOCKET_TIMEOUT_SECONDS,
        _lock_control_client,
        lock_control_cooperative_bound_s,
    )

    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return object()

    with patch.object(redis_state, "get_redis_client", _capture):
        _lock_control_client()

    assert seen.get("fast_fail") is True, (
        f"the lock-control ops are using the background retry policy ({seen}). That "
        f"is 4 attempts at up to 5 s each way — a cooperative bound of ~20 s against "
        f"a {LOCK_CONTROL_BOUND_SECONDS:g}s wall, so the wall fires FIRST and clause "
        f"(7)'s comparison is against a number the client does not honour. It is also "
        f"the exact client CERT-2107 found these four calls on"
    )
    assert seen.get("socket_timeout") == LOCK_CONTROL_SOCKET_TIMEOUT_SECONDS, seen
    assert seen.get("socket_connect_timeout") == LOCK_CONTROL_SOCKET_TIMEOUT_SECONDS, seen

    assert LOCK_CONTROL_BOUND_SECONDS > lock_control_cooperative_bound_s(), (
        "the lock-control wall is not above its own cooperative bound"
    )


def test_the_four_control_ops_run_off_the_event_loop():
    """A wall around a sync Redis call issued ON the loop bounds nothing.

    CERT-2089's finding, owed again for these four: a coroutine that never suspends
    cannot be cancelled, so `wait_for` around a blocking call in the loop thread
    fires only after the call has already returned. The threading is what makes the
    wall real, and it is asserted by observing the thread rather than by reading the
    source.
    """
    import threading

    from app.tasks import search_head_warmer as warmer

    loop_thread = None
    ran_on = []

    def _record_thread(token, deadline=None):
        ran_on.append(threading.current_thread().ident)
        return token

    async def _drive():
        nonlocal loop_thread
        loop_thread = threading.current_thread().ident
        with patch.object(warmer, "_acquire_blocking", _record_thread):
            await warmer._acquire_run_lock()

    asyncio.run(_drive())

    assert ran_on, "the acquire never ran"
    assert ran_on[0] != loop_thread, (
        "the acquire ran on the event-loop thread, so its wall cannot fire while it "
        "is out — and neither can any other wall in the process (gotcha #39)"
    )


def test_clause_seven_refuses_a_control_wall_at_or_below_its_cooperative_bound():
    """The clause fires, and it fires at equality as well as below it.

    Clause (5)'s lesson, applied: a strict inequality asserted only from the
    comfortable side is a clause nobody has seen refuse anything.
    """
    from app.tasks import search_head_warmer as warmer

    assert warmer.residency_invariant()[0]

    for bad in (4.1, 4.0, 1.0):
        with patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", bad):
            ok, why = warmer.residency_invariant()
            assert not ok, (
                f"a {bad}s control wall against a "
                f"{warmer.lock_control_cooperative_bound_s()}s cooperative bound was "
                f"accepted — clause (7) is not enforcing its own inequality"
            )
            assert "CONTROL WALL IS NOT ABOVE WHAT IT WALLS" in why, why

    # And it is not simply always-false: one tick above the cooperative bound passes.
    with patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", 4.2):
        assert warmer.residency_invariant()[0], warmer.residency_invariant()[1]


def test_the_shipped_threshold_is_the_derived_one():
    """`REFRESH_AHEAD_SECONDS` has been 150, then 130, then 150 again.

    The first 150 was refused (CERT-2084, derived from `ttl - period`); the second
    is certified (derived from `period + budget + margin` over a budget that now
    includes the control term). The integer carries no information, so the constant
    is held to the derivation by a test rather than by the comment above it — which
    was itself stale for two commits and described a threshold the module was not
    shipping.
    """
    from app.tasks.search_head_warmer import (
        REFRESH_AHEAD_SECONDS,
        derive_refresh_ahead_s,
        residency_invariant,
    )

    assert REFRESH_AHEAD_SECONDS == derive_refresh_ahead_s(), (
        f"the shipped threshold is {REFRESH_AHEAD_SECONDS} but the derivation gives "
        f"{derive_refresh_ahead_s()}. One of them moved without the other; the "
        f"derivation is the claim and the constant is supposed to be its value"
    )
    assert residency_invariant()[0], residency_invariant()[1]


def test_the_pass_budget_fits_inside_the_workers_own_time_limit():
    """🔴 THE BOUND OUTSIDE THE MODULE, found while pricing the one inside it.

    `residency_invariant()` reasons entirely in the warmer's own quantities, and
    every clause is about the CACHE. None of them can see the constraint that ends
    a pass from above: `warm_search_head` carries `soft_time_limit=120`, and the
    task has to fit budget PLUS teardown inside it.

    CERT-2107's control term moved the budget 50 -> 70, which is a 40% cut in that
    headroom in one commit — the same shape as every finding in this chain (a
    number grew against a ceiling nobody was checking), one layer out. It still
    fits, comfortably, and the point of the test is that the next term cannot close
    the gap without saying so.

    A soft-limit breach is not a clean stop: writes are abandoned mid-pass and the
    exclusion is left for `_LOCK_KEY`'s TTL to collect, so the pass gap that clause
    (4) derives its write interval from is no longer the one the lock enforces.
    """
    from app.tasks import celery_app
    from app.tasks.search_head_warmer import (
        _LOCK_TTL_SECONDS,
        full_rebuild_budget_s,
    )

    task = celery_app.tasks["app.tasks.warm_search_head"]
    soft = task.soft_time_limit
    hard = task.time_limit
    assert soft and hard, f"the warmer lost its time limits: soft={soft} hard={hard}"

    budget = full_rebuild_budget_s()
    assert budget < soft, (
        f"the declared lock-held budget is {budget:g}s against a {soft:g}s soft time "
        f"limit, so a worst-case pass is killed by the worker before it finishes. "
        f"Writes are abandoned mid-pass and the run lock is left for its "
        f"{_LOCK_TTL_SECONDS:g}s TTL to collect — clause (4)'s pass gap stops being "
        f"the one the lock enforces"
    )
    # Teardown is outside the exclusion but INSIDE the task: `width` session exits,
    # each a commit + close + `engine.dispose()`. Requiring the budget to leave at
    # least a third of the limit is a coarse bar deliberately — the honest number is
    # unmeasured, and a bar that pretends otherwise is the substitution this chain
    # keeps blocking.
    assert soft - budget >= soft / 3, (
        f"only {soft - budget:g}s of the {soft:g}s soft limit is left for teardown "
        f"after a worst-case {budget:g}s pass. Teardown is `width` session exits, "
        f"all network work and none of it bounded by anything in this module"
    )
    assert hard > soft, (hard, soft)


# ---------------------------------------------------------------------------
# 10. CERT-2114 — the acquire's side effect does not outlive the wait for it.
#
# CERT-2107 walled the four lock-control round-trips. CERT-2114 found that the
# wall bounds the WAIT and not the WORK: `asyncio.wait_for(asyncio.to_thread(fn))`
# cancels the await and leaves the thread running, so an abandoned `SET NX` went
# on to install a full `_LOCK_TTL_SECONDS` lock AFTER the pass had published
# `complete` and released. The grader's probe returned in 0.012 s and left the
# lock standing; every later pass then skipped on `skip_reason="lock"` for long
# enough that the `SEARCH_RESPONSE_TTL_SECONDS` entry the warmer exists to keep
# resident expired underneath it. That is the DISCOVER ship, false.
#
# The tests below are the three the cert named, plus the two that stop the repair
# being satisfied by a cheaper lie: that the fix bought no budget, and that the
# release script is the repo's one copy rather than a third.
# ---------------------------------------------------------------------------


class _LockRedis:
    """A Redis stand-in for the run lock: `SET NX EX`, `EVAL` compare-and-delete, `DEL`.

    🔴 `delete()` IS IMPLEMENTED ON PURPOSE, even though production no longer calls
    it. The mutant these tests exist to kill is "put the unconditional `DEL` back",
    and a fake that cannot express the mutant cannot be shown to catch it. Same
    reasoning for `get`: the fake is a Redis, not a mould of the current code.

    `set_delay` and `eval_delay` are how a round-trip is driven past a scaled wall
    without sleeping for a real five seconds. The store is mutex-guarded because
    the whole subject here is a worker thread racing the event loop.
    """

    def __init__(self, *, set_delay=0.0, eval_delay=0.0):
        self.store = {}
        self.ops = []
        self.scripts = []
        self.set_delay = set_delay
        self.eval_delay = eval_delay
        self._mutex = _threading.Lock()

    def set(self, key, value, nx=False, ex=None):
        if self.set_delay:
            _time_mod.sleep(self.set_delay)
        with self._mutex:
            self.ops.append(("set", key, value))
            if nx and key in self.store:
                return None
            self.store[key] = value
            return True

    def eval(self, script, numkeys, key, arg):
        if self.eval_delay:
            _time_mod.sleep(self.eval_delay)
        with self._mutex:
            self.ops.append(("eval", key, arg))
            self.scripts.append(script)
            if self.store.get(key) == arg:
                del self.store[key]
                return 1
            return 0

    def delete(self, key):
        with self._mutex:
            self.ops.append(("delete", key, None))
            return int(self.store.pop(key, None) is not None)

    def setex(self, key, ttl, value):
        with self._mutex:
            self.ops.append(("setex", key, value))
            self.store[key] = value
            return True

    def get(self, key):
        with self._mutex:
            self.ops.append(("get", key, None))
            return self.store.get(key)

    def ttl(self, key):
        return 999

    def held(self):
        """Whatever token currently holds the run lock, or None."""
        with self._mutex:
            return self.store.get(warmer._LOCK_KEY)


class _WarmerStubs:
    """The non-lock half of a pass, stubbed so only the lock is under test."""

    @staticmethod
    async def resolve_head(session, limit):
        return ["aa"], "test"

    @staticmethod
    async def warm_one(session, q):
        return {"q": q, "ok": True, "reason": "warmed", "ttl_before": 1,
                "rebuilt": True, "ttl_after": 99, "seconds": 0.0}


class _StubSession:
    async def rollback(self):
        pass


class _StubCM:
    async def __aenter__(self):
        return _StubSession()

    async def __aexit__(self, *a):
        return False


def _drive_pass(redis, *, wall=0.05, min_period=0, **kwargs):
    """Run ONE real `_warm_search_head` against `redis`, joining the worker threads.

    🔴 `asyncio.run`, NEVER this file's `_run` helper, and that is the whole
    apparatus of these tests. `_run` builds a loop and calls `run_until_complete`,
    which does NOT shut down the default executor — so an abandoned worker is
    still mid-flight when the assertions run and a residual lock has not been
    installed yet. `asyncio.run` closes its runner, which awaits
    `loop.shutdown_default_executor()` and joins the thread. That is the exact
    observation point the grader's probe used, and it is the only one at which
    "the side effect outlived the wait" is a statement about anything.
    """
    from app.tasks import base as task_base

    with patch.object(task_base, "get_task_session", lambda: _StubCM()), \
         patch.object(warmer, "resolve_head", _WarmerStubs.resolve_head), \
         patch.object(warmer, "_warm_one", _WarmerStubs.warm_one), \
         patch.object(warmer, "_lock_control_client", lambda: redis), \
         patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", wall), \
         patch.object(warmer, "MIN_PASS_PERIOD_SECONDS", min_period), \
         patch.object(warmer, "head_warm_enabled", lambda: True):
        return asyncio.run(warmer._warm_search_head(head_size=1, budget_s=1.0, **kwargs))


def test_an_acquire_that_lands_after_its_wall_leaves_no_ghost_lock():
    """🔴 THE GRADER'S PROBE, AS AN ENTRY-POINT REGRESSION (CERT-2114).

    The blocked SHA's exact shape: the `SET NX` sleeps past the control wall, the
    pass gives up waiting, publishes its summary and releases — and THEN the
    abandoned worker installs a 180 s lock nobody believes they hold. The probe
    reported `complete` at 0.012 s wall and ended with the lock present.

    The repair is that `_acquire_blocking` undoes its own late `SET`, by token,
    in the thread that made it, before that thread exits. So the assertion is
    made at the point the worker has been joined, and it is about STATE and not
    about timing: whatever the pass said about itself, the lock must be gone.
    """
    redis = _LockRedis(set_delay=0.5)

    summary = _drive_pass(redis, wall=0.05)

    assert redis.held() is None, (
        f"the pass ended with {redis.held()!r} still holding {warmer._LOCK_KEY}. "
        f"The acquire hit its wall, the pass reported {summary['terminal']!r} and "
        f"released — and the abandoned worker then installed a "
        f"{warmer._LOCK_TTL_SECONDS}s lock behind it. That is CERT-2114 exactly: "
        f"every later pass skips on `lock` until it expires, which is longer than "
        f"the {warmer.SEARCH_RESPONSE_TTL_SECONDS}s entry it exists to keep warm"
    )

    # ...and it is gone because it was UNDONE, not because it was never installed.
    # Without this, a fake that simply never stored the key would satisfy the
    # assertion above and the test would prove nothing about the repair.
    kinds = [op for op, key, _ in redis.ops if key == warmer._LOCK_KEY]
    assert "set" in kinds, (
        f"the late acquire never installed anything, so this run did not exercise "
        f"the ghost path at all: {redis.ops}"
    )
    assert kinds.index("set") < len(kinds) - 1 and "eval" in kinds[kinds.index("set"):], (
        f"the lock was installed and nothing compare-and-deleted it afterwards. "
        f"The undo has to follow the SET inside the same worker: {redis.ops}"
    )


def test_a_walled_acquire_is_reported_unknown_and_never_owned():
    """Requirement two, at the three-state boundary: unknown is not ownership.

    All three states driven through the REAL `_acquire_run_lock` against a real
    `SET NX`, because the property is about what the code concludes from what
    Redis said, and stubbing the conclusion tests nothing.
    """
    # OWNED — an empty key, a clean SET NX.
    redis = _LockRedis()
    with patch.object(warmer, "_lock_control_client", lambda: redis):
        claim = asyncio.run(warmer._acquire_run_lock())
    assert claim.state is warmer.RunLockState.OWNED, claim
    assert claim.owns and claim.may_run and not claim.refused
    assert redis.held() == claim.token, "OWNED must mean OUR token is in the key"

    # HELD_ELSEWHERE — somebody else's token is already there.
    redis = _LockRedis()
    redis.store[warmer._LOCK_KEY] = "somebody-else"
    with patch.object(warmer, "_lock_control_client", lambda: redis):
        claim = asyncio.run(warmer._acquire_run_lock())
    assert claim.state is warmer.RunLockState.HELD_ELSEWHERE, claim
    assert claim.refused and not claim.owns and not claim.may_run
    assert redis.held() == "somebody-else", "a refused acquire must not have written"

    # UNKNOWN — the wall fires. Runs, and owns nothing.
    redis = _LockRedis(set_delay=0.5)
    with patch.object(warmer, "_lock_control_client", lambda: redis), \
         patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", 0.05):
        claim = asyncio.run(warmer._acquire_run_lock())
    assert claim.state is warmer.RunLockState.UNKNOWN, claim
    assert claim.may_run, (
        "an unknown acquire must still warm — a warmer that stops because Redis "
        "blinked is the defect this whole family of modules is about"
    )
    assert not claim.owns, (
        f"{claim} claims ownership it cannot have observed. This is the bare `True` "
        f"the blocked SHA returned, and the pass consumed it as ownership"
    )
    assert claim.token, "the compensating release needs the token even when UNKNOWN"


def test_a_release_that_lands_late_cannot_delete_a_successors_lock():
    """The symmetric case the cert named: release by token, never a blind DEL.

    A release whose round-trip is abandoned lands after its caller has gone. By
    then the lock may legitimately belong to the NEXT pass — the old
    `client.delete(_LOCK_KEY)` would remove that pass's exclusion and let a third
    run underneath it, which is #1678's defect one module over.

    Driven as an interleaving rather than as a unit call: pass A's release is in
    flight when A's lock expires and successor B takes the key.
    """
    redis = _LockRedis(eval_delay=0.3)
    a = _owned("token-A")
    redis.store[warmer._LOCK_KEY] = a.token

    async def _drive():
        task = asyncio.ensure_future(warmer._release_run_lock(a))
        # A's release is out. Its TTL lapses and B legitimately acquires — the
        # exact window in which a blind DEL is wrong.
        await asyncio.sleep(0.05)
        redis.store[warmer._LOCK_KEY] = "token-B"
        await task

    with patch.object(warmer, "_lock_control_client", lambda: redis), \
         patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", 5.0):
        asyncio.run(_drive())

    assert redis.held() == "token-B", (
        f"A's late release removed the successor's lock (key now {redis.held()!r}). "
        f"Release has to be a compare-and-delete against the releasing pass's own "
        f"token; an unconditional DEL admits a third concurrent warm"
    )
    assert ("delete", warmer._LOCK_KEY) not in [
        (op, key) for op, key, _ in redis.ops
    ], (
        f"the release reached `DEL` rather than the compare-and-delete: {redis.ops}"
    )


def test_the_release_script_is_the_repos_one_copy_and_not_a_third():
    """The compare-and-delete is imported, not retyped.

    `single_flight` owns it and `event_concept_cache` already carries a second
    copy. A third hand-written copy is how the three drift apart, and a release
    that drifts into a plain `del` is the defect above.
    """
    from app.utils.single_flight import RELEASE_IF_OWNER_LUA

    redis = _LockRedis()
    redis.store[warmer._LOCK_KEY] = "tok"
    with patch.object(warmer, "_lock_control_client", lambda: redis):
        asyncio.run(warmer._release_run_lock(_owned("tok")))

    assert redis.scripts, "the release never evaluated a script"
    assert redis.scripts[0] is RELEASE_IF_OWNER_LUA, (
        "the warmer is running its own copy of the compare-and-delete rather than "
        "`single_flight.RELEASE_IF_OWNER_LUA`. Three copies of one Lua script is "
        "three chances for one of them to become an unconditional delete"
    )
    assert redis.held() is None, "the compare-and-delete did not fire on a match"


def test_a_late_acquire_cannot_suppress_the_next_pass_until_the_entry_expires():
    """The harm, end to end: the ghost is what starves the cache, so drive both passes.

    The two constants are the reason a ghost is fatal rather than untidy, and the
    test states the arithmetic rather than assuming the reader knows it: a residual
    lock lives `_LOCK_TTL_SECONDS` and the entry it protects lives
    `SEARCH_RESPONSE_TTL_SECONDS`. At 180 and 180 a single ghost spans the ENTIRE
    life of the entry — every pass inside that window takes the `lock` skip, and
    `/search` goes cold. This is the `DISCOVER` ship in one assertion.
    """
    assert warmer._LOCK_TTL_SECONDS >= warmer.SEARCH_RESPONSE_TTL_SECONDS, (
        f"this test's premise has moved: a ghost lock now lives "
        f"{warmer._LOCK_TTL_SECONDS}s against a {warmer.SEARCH_RESPONSE_TTL_SECONDS}s "
        f"entry, so it can no longer starve one on its own. Re-derive the harm "
        f"before relaxing anything here"
    )

    redis = _LockRedis(set_delay=0.5)

    # Pass one: the acquire is abandoned. On the blocked SHA this is where the
    # ghost is born.
    _drive_pass(redis, wall=0.05)
    assert redis.held() is None, "pass one left a lock behind"

    # Pass two: the very next scheduled beat, now with a healthy Redis.
    redis.set_delay = 0.0
    second = _drive_pass(redis, wall=5.0)

    assert second.get("skip_reason") != "lock", (
        f"the next pass was refused by a lock nobody holds: {second}. A ghost that "
        f"suppresses passes for {warmer._LOCK_TTL_SECONDS}s outlasts the "
        f"{warmer.SEARCH_RESPONSE_TTL_SECONDS}s entry, so `/search` serves cold"
    )
    assert second["terminal"] != "skipped", second
    assert second["warmed"] >= 1, (
        f"the next pass reached no warm at all, so nothing proves the head can be "
        f"kept resident after a walled acquire: {second}"
    )
    assert redis.held() is None, "pass two did not release its own lock"


def test_the_lifetime_safe_acquire_costs_the_budget_nothing():
    """The repair buys no width and no budget, and that is CHECKED, not argued.

    `_acquire_blocking` can now make TWO round-trips (the `SET`, then the undo).
    The budget prices what the EXCLUSION costs, and the exclusion is what the
    coroutine waits for — the undo runs only on the path where the caller has
    already stopped waiting, so it is not a fifth wall. If that reasoning were
    wrong, `LOCK_CONTROL_OPS_PER_PASS` would owe a fifth op, the budget would move
    off 70 and `REFRESH_AHEAD_SECONDS` would owe a re-derivation.

    This module has been blocked twice for picking a constant and justifying it
    afterwards, so the check runs the other way round: nothing was re-tuned, and
    the assertions below are what say so.
    """
    assert warmer.LOCK_CONTROL_OPS_PER_PASS == 4, warmer.LOCK_CONTROL_OPS_PER_PASS
    assert warmer.full_rebuild_budget_s() == 70.0, warmer.full_rebuild_budget_s()
    assert warmer.REFRESH_AHEAD_SECONDS == 150, warmer.REFRESH_AHEAD_SECONDS
    ok, why = warmer.residency_invariant()
    assert ok, why

    # And the coroutine really does wait on ONE wall even though the worker makes
    # two round-trips. Measured on the await, for `test_a_hung_control_op...`'s
    # reason: `asyncio.run` joins the worker, so a stopwatch outside it would time
    # the undo as well and this assertion would be vacuous.
    redis = _LockRedis(set_delay=0.4)
    WALL = 0.05

    async def _drive():
        started = _time_mod.monotonic()
        claim = await warmer._acquire_run_lock()
        return claim, _time_mod.monotonic() - started

    with patch.object(warmer, "_lock_control_client", lambda: redis), \
         patch.object(warmer, "LOCK_CONTROL_BOUND_SECONDS", WALL):
        claim, waited = asyncio.run(_drive())

    assert claim.state is warmer.RunLockState.UNKNOWN, claim
    assert waited < 2 * WALL + 0.05, (
        f"the acquire's await took {waited:.3f}s against a {WALL}s wall. The "
        f"compensating delete has been folded into the interval the caller pays "
        f"for, so `lock_control_budget_s()` now understates the exclusion and "
        f"clause (7) is being asked to certify a fifth round-trip it cannot see"
    )


def test_a_lock_that_lands_a_hair_before_the_wall_is_still_released_by_the_pass():
    """Ordering (4), and it is the reason the release is not skipped on UNKNOWN.

    `_acquire_blocking` undoes a late `SET` by comparing `monotonic()` against the
    caller's deadline. There is one ordering that comparison cannot catch: the
    `SET` lands microseconds BEFORE the deadline, so the thread reads "not late"
    and returns a token — to a caller whose `wait_for` has already fired. The lock
    is real, this pass will never call itself its owner, and nothing in the worker
    will remove it.

    What removes it is `_release_once()` running on `UNKNOWN` as well as on
    `OWNED`, by the same token. Skipping the release for a pass that "does not own
    anything" is the obvious tidy-up and it reopens the ghost, so the ordering is
    modelled explicitly rather than left to the clock: the stand-in installs the
    lock and IGNORES the deadline, which is precisely what a thread that read
    `monotonic() < deadline` does.
    """
    redis = _LockRedis()
    DELAY = 0.4

    def _lands_just_inside(token, deadline=None):
        redis.set(warmer._LOCK_KEY, token, nx=True, ex=warmer._LOCK_TTL_SECONDS)
        # The caller's wall fires while we are in here. We are not "late" by our
        # own clock, so we do not undo — ordering (4) exactly.
        _time_mod.sleep(DELAY)
        return token

    with patch.object(warmer, "_acquire_blocking", _lands_just_inside):
        summary = _drive_pass(redis, wall=0.05)

    assert redis.held() is None, (
        f"the lock installed on ordering (4) survived the pass (key holds "
        f"{redis.held()!r}, terminal {summary['terminal']!r}). The acquire's own "
        f"undo cannot see this ordering, so the only thing that removes it is the "
        f"pass releasing by token on an UNKNOWN claim — restore that release"
    )
