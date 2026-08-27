"""LAT-P098/#1866 — AN EVAL CALL IS NOT A USER'S INTENT, AND MUST NOT VOTE.

MEASURED FIRST, on production `baae52c2` (v3907), 2026-08-27.
`GET /api/events/search/trending`, the public read of `search:trending:24h`:

    celtics         62   <- the only real user traffic in the top five
    emmy             9   <- LAT-P097 done-bar probe
    wimbledon        8   <- LAT-P097 done-bar probe
    hurricane        8   <- LAT-P097 done-bar probe
    tour de france   6   <- LAT-P097 done-bar probe

Four of the top five were one lane's own cold measurement probes. And `emmy`
measured WARM (`x-timing-split: q=0`) five hours after its last touch, against a
65 s response-cache TTL — the same signature as `masters winner`, a known head
member. A term cannot be warm five hours later unless something is rebuilding
it, and the only thing that does is `typeahead_warmer`. The probes had been
elected into the warmer's head and were being rebuilt every ~37 s.

WHY THAT IS A USER-VISIBLE COST, not bookkeeping. The head is a FIXED 40 slots.
A probe term holding one is a slot a real user's term is not holding, and the
displaced term falls out of the cache and pays the full cold build — measured
elsewhere in this program at ~4 s against a <150 ms budget.

🔴 THIS IS #1866's CLOSED LOOP THROUGH A DOOR NOBODY GUARDED. #1866 stopped the
warmer voting for its own head; #2117 restored the real user's vote on the hit
path. Neither asked whether a NON-user could vote. Anything that can reach the
route over HTTP can, and `_suppress_trending_write` is a ContextVar — reachable
only in-process, so an external probe had no way to opt out even if it wanted to.

⚠️ IT HAD ALREADY BEEN SEEN AND WRITTEN DOWN AS A FOOTNOTE.
`test_typeahead_trending_cache_hit_2117.py`'s own header records
`zzq obscure probe lat82` and `qqx another probe` doing precisely this on
2026-08-23 — "THEY ARE THE DISTRIBUTION and the warmer will spend 2 of 40 slots
on them" — described as a transient to wait out rather than a defect to fix. It
recurred four days later and took ranks 2 through 5.

WHY THE INSTRUMENTS' OWN CONTAMINATION ARITHMETIC DID NOT CATCH IT, which is the
general lesson: `done_bar_snapshot.py` priced its budget against
`search_query_logs`' 30-day head, "a head cut near 65 votes", and concluded one
vote per cycle was unreachable. But it WRITES to `search:trending:24h`, a
different distribution whose rank 2 sits at 9. `resolve_head` blends both, ~20
slots each, so a probe needs single-digit votes to buy a warm slot — not 65.
**A contamination budget priced against a distribution you read instead of the
one you write to is not a budget.**

THE FIX. The debug flags already mean "this answer is not interchangeable with a
user's" on both cache directions. The trending zset is the third direction and
it was missed. `typeahead_search` now sets the existing
`_suppress_trending_write` ContextVar when either flag is on, so the guard stays
in its single home inside `_record_trending` (gotcha #128).
"""

from __future__ import annotations

import json

import pytest

from app.utils import search_trending as st

T0 = 1_787_000_000.0


class FakeRedis:
    """Minimal Redis double — the same shape as the #2117 suite's."""

    def __init__(self, now: float = T0):
        self.now = now
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    def get(self, key):
        v = self.strings.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, ttl, value):
        self.strings[key] = value
        return True

    def _zincrby(self, key, amount, member):
        z = self.zsets.setdefault(key, {})
        z[member] = z.get(member, 0.0) + float(amount)
        return z[member]

    def _expire(self, key, seconds):
        return key in self.zsets

    def pipeline(self, transaction=True):
        return _FakePipeline(self)

    def counted(self, query: str) -> float:
        key = st.bucket_key(self.now)
        return (self.zsets.get(key) or {}).get(st.normalize(query), 0.0)


class _FakePipeline:
    def __init__(self, rc: FakeRedis):
        self._rc = rc
        self._queued: list[tuple] = []

    def zincrby(self, key, amount, member):
        self._queued.append(("zincrby", key, amount, member))
        return self

    def expire(self, key, seconds):
        self._queued.append(("expire", key, seconds))
        return self

    def execute(self):
        out = []
        for cmd, *args in self._queued:
            out.append(getattr(self._rc, "_" + cmd)(*args))
        self._queued.clear()
        return out


@pytest.fixture
def rc(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    monkeypatch.setattr(st, "_now", lambda: client.now)
    return client


@pytest.fixture(autouse=True)
def _isolate_suppression():
    """Reset the ContextVar around every test.

    These tests deliberately observe a ContextVar the route sets and does NOT
    reset — safe in production because each request runs in its own Task with
    its own Context copy, but NOT safe across tests in one context. Without this
    fixture a debug test would leak `True` into the next test and turn a real
    RED into a false green.
    """
    from app.routes.events import _suppress_trending_write

    token = _suppress_trending_write.set(False)
    try:
        yield
    finally:
        _suppress_trending_write.reset(token)


async def _typeahead(q: str, *, debug_evidence=False, debug_timing=False):
    """Call the route directly, with the debug flags passed EXPLICITLY.

    Their declared defaults are `Query(False, ...)` objects, which are TRUTHY
    outside FastAPI — so omitting them would silently make EVERY call a debug
    call and every assertion here vacuous. The #2117 suite paid one red run to
    learn this; it is repeated rather than referenced because a reader of this
    file will not have read that one.
    """
    from app.routes.events import typeahead_search

    return await typeahead_search(
        q=q, debug_evidence=debug_evidence, debug_timing=debug_timing, db=None
    )


def _warm(rc: FakeRedis, q: str, payload=None):
    rc.strings[f"bainluck:typeahead:{q.lower().strip()}"] = json.dumps(
        payload if payload is not None else {"suggestions": [], "_warmed": q}
    )


# ---------------------------------------------------------------------------
# 1. THE DEFECT — an eval call cast a real vote
# ---------------------------------------------------------------------------
#
# These assert on the ContextVar rather than on a resulting zset score, and the
# reason is structural rather than stylistic: a debug call SKIPS the cache read
# (LAT-P050/LAT-P054), so it can never take the early hit exit, and with
# `db=None` the full build raises long before reaching the trending write at the
# other exit. A score-based assertion would therefore read 0.0 with or without
# the fix — a test that passes for the wrong reason. The flag is the mechanism;
# `_record_trending`'s obedience to it is pinned by the #2117 suite.


@pytest.mark.asyncio
async def test_a_debug_timing_call_does_not_vote(rc):
    """RED before the fix."""
    from app.routes.events import _suppress_trending_write

    with pytest.raises(Exception):
        await _typeahead("hurricane", debug_timing=True)

    assert _suppress_trending_write.get() is True, (
        "a `?debug_timing=1` probe cast a real vote into search:trending:24h — "
        "measurement traffic is electing the terms the warmer warms (LAT-P098)"
    )


@pytest.mark.asyncio
async def test_a_debug_evidence_call_does_not_vote(rc):
    """RED before the fix. The offline rerank harness is not a user either."""
    from app.routes.events import _suppress_trending_write

    with pytest.raises(Exception):
        await _typeahead("wimbledon", debug_evidence=True)

    assert _suppress_trending_write.get() is True


# ---------------------------------------------------------------------------
# 2. THE TWO WAYS THIS FIX COULD DO HARM — both pinned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_real_user_still_votes(rc):
    """The fix must silence probes, NOT users.

    Over-suppressing here is the worse failure: it would drain the head exactly
    as #1866 and #2117 each did, and it would do so silently, because a head
    that is merely stale still reports `warmed: 40/40` every pass.
    """
    from app.routes.events import _suppress_trending_write

    _warm(rc, "celtics")
    result = await _typeahead("celtics")

    assert result["_warmed"] == "celtics", "the fixture did not serve from cache"
    assert _suppress_trending_write.get() is False
    assert rc.counted("celtics") == 1.0, (
        "a real user's query stopped counting — the fix over-reached and is "
        "draining the head it was meant to protect"
    )


@pytest.mark.asyncio
async def test_the_warmer_suppression_is_never_clobbered_by_a_non_debug_call(rc):
    """🔴 NEVER DELETE THIS. The load-bearing half of the fix.

    `typeahead_warmer` sets this same ContextVar to True and then calls the
    route in-process with both debug flags FALSE. The obvious spelling of the
    fix —

        _suppress_trending_write.set(bool(debug_evidence or debug_timing))

    — is therefore catastrophic: it resets the warmer's own suppression to False
    on every warm pass and re-opens #1866 proper, the closed feedback loop where
    the warmer votes for all 40 of its own head terms ~1,700 times a day against
    ~3 for a real query. The guard must be SET-ONLY, never an `else`.
    """
    from app.routes.events import _suppress_trending_write

    _warm(rc, "stanley cup")

    _suppress_trending_write.set(True)  # the warmer, before it calls the route
    await _typeahead("stanley cup")

    assert _suppress_trending_write.get() is True, (
        "the route cleared the warmer's suppression — #1866's closed loop is back"
    )
    assert rc.counted("stanley cup") == 0.0


# ---------------------------------------------------------------------------
# 3. STRUCTURE — the guard keeps its single home
# ---------------------------------------------------------------------------


def test_the_suppression_guard_still_lives_in_exactly_one_place():
    """Gotcha #128: a rule that lives in two consumers has two verdicts.

    This fix deliberately routes through the EXISTING ContextVar rather than
    adding a second predicate at the trending write, so `_record_trending` stays
    the only place that decides whether a query counts.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "events.py"
    ).read_text()

    assert src.count("_suppress_trending_write.get()") == 1, (
        "the suppression guard has been copied — it must be read only inside "
        "`_record_trending`"
    )
    assert "_suppress_trending_write.set(bool(" not in src, (
        "SET-ONLY: a computed set() clobbers the warmer's suppression "
        "(see test_the_warmer_suppression_is_never_clobbered_by_a_non_debug_call)"
    )
