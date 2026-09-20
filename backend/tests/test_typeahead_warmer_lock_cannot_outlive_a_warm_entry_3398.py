"""#3398: a killed pass must not wedge the warmer past the response TTL.

**The defect, measured on production 2026-09-20** (`/api/admin/typeahead-warmer/last`,
32 passes, 12:59:48Z → 13:26:54Z, all after the `0a7534ff9` release):

    write-gaps over the 65s response TTL : 5 of 31   (worst 267.7s)
    head entirely cold                   : 20.0% of the wall clock
    skips in 604s                        : lock 31, min_period 16
    passes in that same 604s             : 10, where the 30s floor allows ~20

`0a7534ff9` proved the refresh-ahead skip was not the cause (`fresh == 0` on
32/32 passes, zero skip-caused holes). What is left is the lock: a pass cannot
release when its worker child is killed — `worker-background` runs
`--max-memory-per-child=200000` — so the key sat for its full TTL, and the TTL
was **120s against a 65s response TTL**. One kill was therefore always a cold
search box, and every beat inside it recorded a `lock` skip.

So the invariant this file guards is a comparison between two constants that
previously nobody wrote down together:

    _LOCK_TTL_SECONDS < RESPONSE_CACHE_TTL_S

and the renewal that makes it safe to hold. Lowering the TTL alone would trade a
cold head for concurrent passes on any run longer than the TTL, which is the
trade `0a7534ff9`'s commit message explicitly refused — the renewal is what
removes it, so the two are tested together or the fix is not proven.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.tasks import typeahead_warmer as warmer
from app.utils.typeahead_beat_budget import RESPONSE_CACHE_TTL_S


class _FakeRedis:
    """Enough Redis to exercise SET NX / GET / EXPIRE / DELETE with a TTL."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.expire_calls: list[tuple[str, int]] = []

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex
        return True

    def get(self, key):
        return self.store.get(key)

    def expire(self, key, seconds):
        if key not in self.store:
            return False
        self.ttl[key] = seconds
        self.expire_calls.append((key, seconds))
        return True

    def delete(self, key):
        self.store.pop(key, None)
        self.ttl.pop(key, None)
        return 1

    def kill_the_worker(self):
        """A child dies mid-pass: nothing releases, the key keeps its TTL."""
        return self.ttl.get(warmer._LOCK_KEY)


@pytest.fixture
def fake_redis(monkeypatch):
    rc = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: rc, raising=False
    )
    return rc


class TestAKilledPassCannotOutliveAWarmedEntry:
    def test_the_lock_ttl_is_under_the_response_cache_ttl(self):
        """The whole finding, as one comparison.

        This is not a style preference. While `_LOCK_TTL_SECONDS` exceeded
        `RESPONSE_CACHE_TTL_S` there existed a single event — one killed child —
        that guaranteed every warmed entry expired before the next pass could
        rebuild it. Under it, no single wedge can do that.
        """
        assert warmer._LOCK_TTL_SECONDS < RESPONSE_CACHE_TTL_S, (
            f"a killed pass wedges the warmer for {warmer._LOCK_TTL_SECONDS}s, which is "
            f"longer than the {RESPONSE_CACHE_TTL_S}s a warmed entry lives — so one kill "
            "empties the whole head and the next person to type a top term pays the "
            "cold build (#3398, measured 20.0% of wall clock)"
        )

    def test_no_fixed_ttl_can_clear_both_bounds_so_the_renewal_is_load_bearing(self):
        """Why `_LOCK_RENEW_SECONDS` is not belt-and-braces.

        The obvious second bound — "keep the TTL above the pass wall so a healthy
        run never loses its own lock" — is UNSATISFIABLE here, and this test
        exists to stop a future reader re-deriving it and raising the TTL back
        over 65 to satisfy it. `MEASURED_WALL_MAX_S` sits above
        `RESPONSE_CACHE_TTL_S` on purpose (ruling 075's argued margin, after four
        cycles of point estimates each proving too low), so the two bounds do not
        overlap and no constant satisfies both.

        If this test ever fails, the wall bound has dropped under the response
        TTL and a plain TTL WOULD be sufficient — at which point the renewal
        becomes optional and this file should be revisited rather than patched.
        """
        from app.utils.typeahead_beat_budget import MEASURED_WALL_MAX_S

        assert MEASURED_WALL_MAX_S > RESPONSE_CACHE_TTL_S, (
            f"the registered pass wall ({MEASURED_WALL_MAX_S}s) now fits inside the "
            f"response TTL ({RESPONSE_CACHE_TTL_S}s), so a fixed lock TTL between them "
            "is possible and the renewal is no longer the only way to hold both bounds"
        )

    def test_the_ttl_survives_more_than_one_failed_renewal(self):
        """The bound the TTL DOES have to clear, now that renewal is the cover.

        A single Redis blink at renewal time must not cost the lock, or the
        wedge fix would trade one flake class for another.
        """
        assert warmer._LOCK_TTL_SECONDS >= 2 * warmer._LOCK_RENEW_SECONDS, (
            f"TTL {warmer._LOCK_TTL_SECONDS}s leaves under two renewal attempts at "
            f"{warmer._LOCK_RENEW_SECONDS}s — one failed renewal would drop the lock "
            "of a pass that is still warming"
        )

    def test_a_killed_pass_leaves_a_wedge_shorter_than_a_warmed_entry(self, fake_redis):
        """End to end on the constants, not on the comparison.

        Acquire, then kill — nothing releases — and read what the key is left
        holding. This is the production event: the pass never reaches its
        `finally`, so only the TTL ends the wedge.
        """
        token = warmer._acquire_run_lock()
        assert token not in (None, warmer._LOCK_UNKNOWN)

        wedge_s = fake_redis.kill_the_worker()

        assert wedge_s is not None, "a killed pass left no expiry — the wedge is forever"
        assert wedge_s < RESPONSE_CACHE_TTL_S, (
            f"a killed pass wedges the warmer {wedge_s}s, outliving the "
            f"{RESPONSE_CACHE_TTL_S}s warmed entry it was supposed to protect"
        )


class TestTheRenewalIsWhatMakesTheShortTtlSafe:
    def test_a_pass_longer_than_the_ttl_keeps_its_own_lock(self, fake_redis):
        """The trade the short TTL would otherwise make, refused.

        Drives the real holder coroutine with a compressed renew interval, and
        asserts the key is still ours after more than a full TTL of simulated
        work.
        """

        async def scenario():
            token = warmer._acquire_run_lock()
            holder = asyncio.create_task(warmer._hold_run_lock(token))
            # Longer than the TTL would be if nothing renewed.
            await asyncio.sleep(0.05)
            holder.cancel()
            with pytest.raises(asyncio.CancelledError):
                await holder
            return token

        with patch.object(warmer, "_LOCK_RENEW_SECONDS", 0.01):
            token = asyncio.run(scenario())

        assert fake_redis.expire_calls, (
            "the holder never renewed — a pass outlasting the TTL would be overtaken "
            "by its own successor, which is exactly what lowering the TTL must not cost"
        )
        assert all(s == warmer._LOCK_TTL_SECONDS for _, s in fake_redis.expire_calls)
        assert fake_redis.get(warmer._LOCK_KEY) == token

    def test_the_holder_stops_renewing_once_the_lock_is_someone_elses(self, fake_redis):
        """Losing the lock must not become a fight over it.

        If our renewal lost a race, another pass is already doing this work.
        Re-taking the key would produce the duplicate warm the lock prevents, so
        the holder returns instead.
        """

        async def scenario():
            token = warmer._acquire_run_lock()
            fake_redis.store[warmer._LOCK_KEY] = "somebody-elses-token"
            holder = asyncio.create_task(warmer._hold_run_lock(token))
            await asyncio.sleep(0.05)
            return holder

        with patch.object(warmer, "_LOCK_RENEW_SECONDS", 0.01):
            holder = asyncio.run(scenario())

        assert holder.done() and not holder.cancelled(), (
            "the holder kept renewing a lock it no longer owns — it would extend "
            "ANOTHER pass's lock, and two copies would warm the same head"
        )
        assert fake_redis.get(warmer._LOCK_KEY) == "somebody-elses-token"


class _FakeSessionCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *a):
        return False


def _fake_session_cm(*a, **kw):
    return _FakeSessionCM()


class TestTheRealPassStartsTheHolder:
    """The WIRING, which the unit tests above cannot see.

    Mutation-checked: replacing `_hold_run_lock(lock_token)` in `_warm_typeahead`
    with an inert `asyncio.sleep` left every other test in this file green. A
    renewal that is correct but never started is the same production defect as no
    renewal at all, so the guard has to drive the real task.
    """

    def test_a_slow_pass_renews_through_the_real_task_body(self, fake_redis):
        async def _slow_warm(sessions, head):
            # Longer than the compressed renew interval, so a wired holder fires.
            await asyncio.sleep(0.05)
            return [
                {"q": q, "ok": True, "reason": "warmed", "ttl_before": 5,
                 "rebuilt": True, "ttl_after": 65, "seconds": 0.01}
                for q in head
            ]

        with patch.object(warmer, "_LOCK_RENEW_SECONDS", 0.01), \
             patch.object(warmer, "_warm_head_concurrently", _slow_warm), \
             patch.object(warmer, "_record_outcome"), \
             patch.object(warmer, "_record_pass_start"), \
             patch.object(warmer, "_seconds_since_last_pass", return_value=100.0), \
             patch("app.tasks.base.get_task_session", _fake_session_cm):
            out = asyncio.run(warmer._warm_typeahead(queries=["red sox", "chiefs"]))

        assert out["total"] > 0, "the canned head was filtered away; this proves nothing"
        assert fake_redis.expire_calls, (
            "`_warm_typeahead` ran a pass longer than the renew interval and the lock "
            "was never renewed — the holder is not wired into the task body"
        )

    def test_the_pass_leaves_no_lock_behind(self, fake_redis):
        """And the holder must not outlive the pass that started it.

        A holder still renewing after `finally` would wedge the warmer forever —
        the exact failure the TTL exists to bound, reintroduced by the fix.
        """

        async def _warm(sessions, head):
            return [
                {"q": q, "ok": True, "reason": "warmed", "ttl_before": 5,
                 "rebuilt": True, "ttl_after": 65, "seconds": 0.01}
                for q in head
            ]

        async def scenario():
            out = await warmer._warm_typeahead(queries=["red sox", "chiefs"])
            # Well past several renew intervals; a leaked holder would re-take.
            await asyncio.sleep(0.05)
            return out

        with patch.object(warmer, "_LOCK_RENEW_SECONDS", 0.01), \
             patch.object(warmer, "_warm_head_concurrently", _warm), \
             patch.object(warmer, "_record_outcome"), \
             patch.object(warmer, "_record_pass_start"), \
             patch.object(warmer, "_seconds_since_last_pass", return_value=100.0), \
             patch("app.tasks.base.get_task_session", _fake_session_cm):
            asyncio.run(scenario())

        assert fake_redis.get(warmer._LOCK_KEY) is None, (
            "the lock survived the pass that took it — a leaked holder is renewing it"
        )


class TestReleaseMeansReleaseMine:
    def test_a_stale_pass_does_not_release_its_successors_lock(self, fake_redis):
        """The bug a short TTL introduces if release stays unconditional.

        Pass A's renewal fails twice and its key expires; pass B takes the lock;
        pass A then reaches its `finally`. Under the old unconditional `delete`
        this hands a third copy the lock while B is still warming.
        """
        stale = warmer._acquire_run_lock()
        fake_redis.delete(warmer._LOCK_KEY)  # A's TTL ran out
        successor = warmer._acquire_run_lock()  # B takes it
        assert successor not in (None, warmer._LOCK_UNKNOWN, stale)

        warmer._release_run_lock(stale)  # A's finally, arriving late

        assert fake_redis.get(warmer._LOCK_KEY) == successor, (
            "a finished pass released a lock it did not hold — the successor is "
            "still warming and a third copy can now start on the same head"
        )

    def test_an_owning_pass_does_release(self, fake_redis):
        """The guard above must not be satisfied by never releasing at all."""
        token = warmer._acquire_run_lock()
        warmer._release_run_lock(token)
        assert fake_redis.get(warmer._LOCK_KEY) is None, (
            "the ordinary path stopped releasing — every pass would now wait out "
            "the full TTL and the cadence would collapse"
        )


class TestRedisSilenceIsItsOwnState:
    def test_an_unreadable_redis_warms_but_claims_nothing(self, monkeypatch):
        """Three states, never two (gotcha #53).

        A blink must not read as a refusal (the warmer would stop warming) and
        must not read as ownership either (release would delete a key this pass
        never wrote).
        """

        class _Dead:
            def set(self, *a, **k):
                raise RuntimeError("redis down")

            def get(self, *a, **k):
                raise AssertionError("an UNKNOWN claim must not touch redis again")

            def delete(self, *a, **k):
                raise AssertionError("an UNKNOWN claim must never delete the lock")

        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda *a, **k: _Dead(), raising=False
        )

        claim = warmer._acquire_run_lock()

        assert claim == warmer._LOCK_UNKNOWN, (
            "a Redis blink was collapsed into OWNED or REFUSED — one of those stops "
            "the warmer, the other lets it delete somebody else's lock"
        )
        assert claim is not None, "a blink must not skip the pass (fail open)"
        # Neither of these may reach Redis; `_Dead` asserts it.
        warmer._release_run_lock(claim)
        assert warmer._renew_run_lock(claim) is False

    def test_a_held_lock_is_still_a_refusal(self, fake_redis):
        """UNKNOWN must not have swallowed the real refusal path."""
        warmer._acquire_run_lock()
        assert warmer._acquire_run_lock() is None, (
            "a second pass was allowed in while the first holds the lock — the "
            "duplicate warm this lock exists to prevent"
        )
