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
        """
        called = []

        async def _fake_route(**kw):
            called.append(kw)
            return {"events": []}

        with patch.object(warmer, "_cache_ttl_seconds", return_value=59), \
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
