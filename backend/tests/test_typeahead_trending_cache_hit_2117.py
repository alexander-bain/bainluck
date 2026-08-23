"""#2117 — WARMING A TERM MADE IT UNCOUNTABLE. The mirror of #1866.

MEASURED FIRST (LAT-P082, ratified by Fable 2026-08-23), on production, with a
paired control:

    stanley cup (WARMED)         cache HIT   -> recorded in trending?  NO
    zzq obscure probe lat82      cache MISS  -> recorded in trending?  YES, count 1
    qqx another probe            cache MISS  -> recorded in trending?  YES, count 1

The trending write is the LAST statement in `typeahead_search`. A cache hit
returns from the top of the function, hundreds of lines earlier. So the counter
that decides what the warmer warms was conditioned on **whether we had already
warmed it** — a term, once warmed, could never be re-elected, only displaced by
something that had not been warmed yet.

🔴 THIS IS #1866 IN A MIRROR, AND THAT IS WHY IT WAS INVISIBLE FOR SO LONG.
#1866 was the warmer voting FOR its own head (every pass incremented all 40 head
terms, so the head was self-sustaining and closed). The fix stopped the warmer's
own calls from counting. What nobody then asked was the complementary question:
once the warmer's votes are gone, can a REAL user's vote for a warmed term still
land? It could not. #1866 removed the false votes; #2117 restores the true ones.
Between the two fixes the head could only ever drain — which is exactly what
production shows: `GET /api/events/search/trending` returns `{"trending": []}`
and `resolve_head` falls through to `db:search_query_logs:30d` on 40/40 slots.

THE FIX. One helper, `_record_trending`, called from BOTH return paths, with the
`_suppress_trending_write` guard inside it rather than at each call site.

⚠️ **THE GUARD ON THE HIT PATH IS THE LOAD-BEARING HALF, not a copy-paste.** The
warmer warms by calling this route, and on a warm pass the entry it is
refreshing is frequently still live — so the warmer's calls are DISPROPORTIONATELY
cache hits. Counting the hit path without the guard would re-open #1866's closed
loop on precisely the traffic that closed it, and would do so more efficiently
than the original bug. `test_the_warmer_is_still_not_counted_on_a_cache_hit` is
the test that must never be deleted.

⚠️ **DO NOT READ THE TWO PROBE TERMS AS RECOVERY.** `zzq obscure probe lat82` and
`qqx another probe` were written into `search:trending:24h` by LAT-P082's
measurement at ~09:2x PDT 2026-08-23 and expire with the bucket TTL at ~09:2x
PDT 2026-08-24. The zset is otherwise empty, so until then THEY ARE THE
DISTRIBUTION and the warmer will spend 2 of 40 slots on them. A non-empty
trending read before that time is probably these two — read the member names.
"""

from __future__ import annotations

import json

import pytest

from app.utils import search_trending as st

T0 = 1_787_000_000.0


class FakeRedis:
    """Minimal Redis double: string get/setex plus the zset calls `record_query` makes."""

    def __init__(self, now: float = T0):
        self.now = now
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.expires_at: dict[str, float] = {}
        self.commands: list[tuple] = []
        #: How many times a caller opened a network conversation with us. A
        #: pipeline is ONE, however many commands it carries — which is the
        #: whole point of `test_the_trending_write_is_one_round_trip`.
        self.round_trips = 0

    # -- strings ----------------------------------------------------------
    def get(self, key):
        self.round_trips += 1
        self.commands.append(("get", key))
        v = self.strings.get(key)
        return v.encode() if isinstance(v, str) else v

    def setex(self, key, ttl, value):
        self.round_trips += 1
        self.commands.append(("setex", key, ttl))
        self.strings[key] = value
        return True

    # -- zsets ------------------------------------------------------------
    def zincrby(self, key, amount, member):
        self.round_trips += 1
        return self._zincrby(key, amount, member)

    def _zincrby(self, key, amount, member):
        self.commands.append(("zincrby", key, member))
        z = self.zsets.setdefault(key, {})
        z[member] = z.get(member, 0.0) + float(amount)
        return z[member]

    def expire(self, key, seconds):
        self.round_trips += 1
        return self._expire(key, seconds)

    def _expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        if key not in self.zsets:
            return False
        self.expires_at[key] = self.now + float(seconds)
        return True

    # -- pipeline ---------------------------------------------------------
    def pipeline(self, transaction=True):
        return _FakePipeline(self)

    # -- helpers ----------------------------------------------------------
    def counted(self, query: str) -> float:
        key = st.bucket_key(self.now)
        return (self.zsets.get(key) or {}).get(st.normalize(query), 0.0)


class _FakePipeline:
    """Buffers commands and spends exactly ONE round trip on `execute()`."""

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
        self._rc.round_trips += 1
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


async def _typeahead(q: str):
    """Call the route directly, with the debug flags passed EXPLICITLY.

    Their declared defaults are `Query(False, ...)` objects, which are TRUTHY
    when the function is called outside FastAPI — so omitting them silently
    disables the cache read and every assertion here would be made against the
    uncached path. Cost this file one red run before it was spotted.
    """
    from app.routes.events import typeahead_search

    return await typeahead_search(
        q=q, debug_evidence=False, debug_timing=False, db=None
    )


def _warm(rc: FakeRedis, q: str, payload=None):
    """Put `q` in the response cache exactly as the route's own writer would."""
    rc.strings[f"bainluck:typeahead:{q.lower().strip()}"] = json.dumps(
        payload if payload is not None else {"suggestions": [], "_warmed": q}
    )


# ---------------------------------------------------------------------------
# 1. THE DEFECT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_cache_hit_still_counts_the_query(rc):
    """RED before the fix. The whole of #2117 in one assertion."""
    _warm(rc, "stanley cup")

    result = await _typeahead("stanley cup")

    assert result["_warmed"] == "stanley cup", "the fixture did not serve from cache"
    assert rc.counted("stanley cup") == 1.0, (
        "a warmed term served from cache was not counted — the counter that "
        "decides what to warm is conditioned on what we already warmed (#2117)"
    )


@pytest.mark.asyncio
async def test_warming_a_term_no_longer_makes_it_uncountable(rc):
    """The paired control from the production measurement, as a test.

    One warmed term and one cold term, each queried once by a user. Before the
    fix the warmed one scored 0 and the cold one scored 1 — the instrument
    reported demand for exactly the terms we had failed to serve fast.
    """
    _warm(rc, "stanley cup")

    await _typeahead("stanley cup")  # HIT
    try:
        await _typeahead("zzq obscure probe")  # MISS — reaches the DB path
    except Exception:
        # `db=None` makes the uncached build raise. Irrelevant here: the point
        # is the HIT path, and the miss path's counting has never been in doubt.
        pass

    assert rc.counted("stanley cup") == 1.0


# ---------------------------------------------------------------------------
# 2. THE LOAD-BEARING GUARD — #1866 must not be re-opened by this fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_warmer_is_still_not_counted_on_a_cache_hit(rc):
    """🔴 NEVER DELETE THIS.

    The warmer warms by calling this route, and on a warm pass the entry it is
    refreshing is frequently still live — so the warmer's calls are
    DISPROPORTIONATELY cache hits. Counting the hit path without carrying
    `_suppress_trending_write` across would re-open #1866's closed feedback loop
    on exactly the traffic that closed it, and more efficiently than the
    original bug did.
    """
    from app.routes.events import _suppress_trending_write

    _warm(rc, "stanley cup")

    token = _suppress_trending_write.set(True)
    try:
        await _typeahead("stanley cup")
    finally:
        _suppress_trending_write.reset(token)

    assert rc.counted("stanley cup") == 0.0, (
        "the warmer's own cache hit was counted — #1866's loop is back"
    )


@pytest.mark.asyncio
async def test_a_real_user_after_the_warmer_still_counts(rc):
    """The two callers are distinguished per-call, not per-key.

    A ContextVar is per-task, so the warmer's suppression must not persist into
    the next request for the same term. This is what makes a warmed term
    re-electable rather than merely countable once.
    """
    from app.routes.events import _suppress_trending_write

    _warm(rc, "stanley cup")

    token = _suppress_trending_write.set(True)
    try:
        await _typeahead("stanley cup")
    finally:
        _suppress_trending_write.reset(token)
    await _typeahead("stanley cup")

    assert rc.counted("stanley cup") == 1.0


# ---------------------------------------------------------------------------
# 3. IT MUST NOT COST THE FAST PATH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_cache_hit_path_spends_one_extra_round_trip(rc):
    """A cache hit is the fastest path in the system (~13ms p50 measured).

    `record_query` used to spend TWO round trips (`zincrby` then `expire`).
    Moving it onto the hit path unpipelined would have added both to the hottest
    request the API serves, on a program whose headline metric is typeahead p50.
    Pipelined it is one — and the MISS path gets faster than it was.
    """
    _warm(rc, "stanley cup")
    await _typeahead("stanley cup")

    # 1 for the cache GET, 1 for the pipelined trending write.
    assert rc.round_trips == 2, rc.commands


def test_record_query_is_a_single_round_trip(rc):
    rc.round_trips = 0
    assert st.record_query(rc, "some query", now=T0) is True
    assert rc.round_trips == 1, rc.commands
    assert rc.counted("some query") == 1.0


def test_record_query_still_refuses_short_queries_without_a_round_trip(rc):
    rc.round_trips = 0
    assert st.record_query(rc, "ab", now=T0) is False
    assert rc.round_trips == 0


def test_record_query_still_never_raises(rc):
    class Broken:
        def pipeline(self, transaction=True):
            raise RuntimeError("redis is down")

    assert st.record_query(Broken(), "some query", now=T0) is False


# ---------------------------------------------------------------------------
# 4. STRUCTURE — one guard, one writer, both paths
# ---------------------------------------------------------------------------


def test_both_return_paths_go_through_one_recording_helper():
    """The guard lives in ONE place, and both exits use it.

    Two call sites each carrying their own copy of
    `if not _suppress_trending_write.get()` is gotcha #128 — a rule that lives
    in two consumers has two verdicts, and the repaired copy is what hides the
    broken one. This is exactly how #2117 came to exist in the first place: the
    write had one home and the function had two exits.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "events.py"
    ).read_text()

    assert src.count("def _record_trending(") == 1
    assert src.count("_suppress_trending_write.get()") == 1, (
        "the suppression guard has been copied — it must live only inside "
        "`_record_trending`"
    )
    assert src.count("_record_trending(q)") == 2, (
        "both `/typeahead` return paths must record: the cache hit and the "
        "full build. Losing the hit path is #2117; losing the build path is a "
        "counter that only ever sees cold queries."
    )
