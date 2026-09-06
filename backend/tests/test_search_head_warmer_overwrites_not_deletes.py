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
import textwrap
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

        with patch.object(warmer, "_acquire_run_lock", return_value=True), \
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
        with patch.object(warmer, "_acquire_run_lock", return_value=False):
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


def _simulate_residency(*, ttl_s, refresh_ahead_s, period_s, rebuild_walls, horizon_s):
    """Run pass cycles on a fake clock and report every interval the key was ABSENT.

    Faithful to the post-#3526 mechanism: the warmer does NOT delete, so the old
    value keeps serving for the whole rebuild and is replaced by `setex` at the
    END of it.

    🔴 The eligibility decision is production's `_needs_rebuild`. To exercise a
    configuration other than the shipped one we patch the CONSTANT it reads
    rather than reimplementing the predicate around it — the predicate under test
    stays the real one.
    """
    from unittest.mock import patch

    from app.tasks import search_head_warmer as warmer

    log = _ExpiringWriteLog(ttl_s)

    with patch.object(warmer, "REFRESH_AHEAD_SECONDS", refresh_ahead_s):
        # Pass 0 finds nothing and builds the first entry — the cold start.
        first_write = rebuild_walls[0]
        log.setex(first_write)
        timeline = [("write", first_write)]

        pass_i = 1
        while pass_i * period_s <= horizon_s:
            start = pass_i * period_s
            ttl_before = log.ttl_at(start)
            if warmer._needs_rebuild(None if ttl_before == -2 else ttl_before):
                wall = rebuild_walls[min(pass_i, len(rebuild_walls) - 1)]
                log.setex(start + wall)
                timeline.append(("write", start + wall))
            else:
                timeline.append(("fresh", start))
            pass_i += 1

    # Continuous check across the whole horizon.
    absent, run_start = [], None
    t = first_write
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
        period_s=60.0,
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
        period_s=effective_pass_period_s(),
        rebuild_walls=_SHORT_THEN_LONG,
        horizon_s=600.0,
    )
    assert absent == [], (
        f"the served key disappeared at the shipped constants: {absent}\n"
        f"timeline: {timeline}"
    )
    # ...and it was actually doing work, not passing by never rebuilding.
    assert sum(1 for kind, _ in timeline if kind == "write") >= 5, (
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
        period_s=effective_pass_period_s(),
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
        period_s=60.0,
        rebuild_walls=[100.0] * 12,
        horizon_s=900.0,
    )
    assert absent, (
        "option 4 as written (180/90) must be shown to leave a hole — if it does "
        "not, the derivation that rejected it is over-strict and should be revisited"
    )
