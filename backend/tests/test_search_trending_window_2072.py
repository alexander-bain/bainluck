"""#2072 — `search:trending:24h` must MEAN twenty-four hours.

The defect, in two lines of `app/routes/events.py`::

    rc.zincrby("search:trending:24h", 1, normalized)
    rc.expire("search:trending:24h", 86400)

The `expire` was re-issued on EVERY write, so the TTL was reset thousands of
times a day and the key never reached it. It was an **all-time cumulative
counter wearing a 24 h label**, and it could only ever reset by the site taking
zero typeahead traffic for a full day — which has never happened.

Three costs, one of which this program paid directly:

1. `GET /api/events/search/trending` is public and its docstring promises "the
   last 24 hours". Measured on production 2026-08-21 it served
   ``world cup 5414 / red sox 5411 / celtics 5403 / yankees 5400 /
   patriots 5399`` — an all-time leaderboard. Real `/search` volume over
   **thirty** days tops out at 102.
2. It froze the typeahead warmer's head (#1866, LAT-P078). `resolve_head` reads
   the top 40 of this zset; with no decay a term popular ONCE outranks a term
   popular NOW, permanently.
3. Nothing organic can ever break in. A breaking-news term needs thousands of
   searches in one day to overtake a leader that has been accumulating since
   the key was created.

🔴 **THE INTERACTION WITH #1866, WHICH IS WHY THIS IS NOT COSMETIC.** #1866
broke the warmer's feedback loop (the route stopped counting the warmer's own
calls) and made the query-log arm reachable (`_blend_heads`). But the zset half
of that blend still selected on all-time counts, so the ~5,400 accumulated
scores stayed frozen at the top of the very zset the warmer reads. **A wrong
window re-pollutes exactly what the loop-break just cleaned** — the loop-break
stops NEW pollution and the window fix is what drains the OLD. Neither alone
gives the warmer a head that describes today.

The obvious fix is wrong and the issue says so: moving the `expire` to fire only
on creation gives "everything, then suddenly nothing" — a full cliff every 24 h
from the first write, leaving the warmer cold-starting on `_STATIC_FLOOR` once a
day. The window has to ROLL, so it is bucketed.
"""

from __future__ import annotations

import inspect

import pytest

from app.utils import search_trending as st


HOUR = 3600.0

# A fixed epoch, never `time.time()`. Gotcha #44: an anchor that reads the wall
# clock is an anchor whose age swings 24 h with it, and this program has paid
# for that defect four times. Every age below is an OFFSET from this constant.
#
# Pinned to HH:30:00 UTC on purpose. An anchor that lands near an hour boundary
# makes "+10 minutes is the same bucket" true or false depending on where the
# constant happens to fall — a clock-shaped fragility inside a test written to
# avoid one. Mid-hour leaves 30 minutes of slack on both sides.
T0 = 1_786_998_600.0  # 2026-08-17T06:30:00Z


# ---------------------------------------------------------------------------
# A Redis stand-in that honours TTL against an INJECTED clock.
#
# Ruling 072: a fake that agrees with the code instead of with Redis proves only
# that the code agrees with itself. The whole defect under test is a TTL that
# never fires, so a fake that ignores TTL could not observe the fix. This one
# expires keys, sums ZUNIONSTORE scores, and returns bytes members like the real
# client does.
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self, now: float = T0):
        self.now = now
        self.zsets: dict[str, dict[str, float]] = {}
        self.expires_at: dict[str, float] = {}
        self.commands: list[tuple] = []

    # -- clock ------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        self.now += seconds

    def _reap(self) -> None:
        dead = [k for k, at in self.expires_at.items() if at <= self.now]
        for k in dead:
            self.zsets.pop(k, None)
            self.expires_at.pop(k, None)

    # -- commands ---------------------------------------------------------
    def zincrby(self, key, amount, member):
        self._reap()
        self.commands.append(("zincrby", key, member))
        z = self.zsets.setdefault(key, {})
        z[member] = z.get(member, 0.0) + float(amount)
        return z[member]

    def expire(self, key, seconds):
        self._reap()
        self.commands.append(("expire", key, seconds))
        if key not in self.zsets:
            return False
        self.expires_at[key] = self.now + float(seconds)
        return True

    # #2117: `record_query` pipelines its two writes into ONE round trip, so
    # this double needs to speak pipeline. Deliberately a real buffer-then-apply
    # rather than a pass-through, so `self.commands` still records the same
    # ("zincrby", ...) / ("expire", ...) pairs every assertion in this file
    # already reads — the transport changed, the observable behaviour did not.
    def pipeline(self, transaction=True):
        return _Pipeline(self)

    def zunionstore(self, dest, keys, aggregate=None):
        self._reap()
        self.commands.append(("zunionstore", dest, tuple(keys)))
        merged: dict[str, float] = {}
        for k in keys:
            for member, score in (self.zsets.get(k) or {}).items():
                merged[member] = merged.get(member, 0.0) + score
        if merged:
            self.zsets[dest] = merged
        else:
            self.zsets.pop(dest, None)
            self.expires_at.pop(dest, None)
        return len(merged)

    def zrevrange(self, key, start, stop, withscores=False):
        self._reap()
        z = self.zsets.get(key) or {}
        ordered = sorted(z.items(), key=lambda kv: (-kv[1], kv[0]))
        end = None if stop == -1 else stop + 1
        page = ordered[start:end]
        if withscores:
            return [(m.encode(), s) for m, s in page]
        return [m.encode() for m in page]

    def delete(self, key):
        self.zsets.pop(key, None)
        self.expires_at.pop(key, None)


def _members(rows):
    return [m for m, _ in rows]


# ---------------------------------------------------------------------------
# THE HEADLINE. The window rolls, which is the entire content of #2072.
# ---------------------------------------------------------------------------


def test_a_query_from_twenty_five_hours_ago_is_NOT_in_the_window():
    """The defect's definition, stated as a test.

    Under the old shape this term's score was immortal: the key's TTL was reset
    on every subsequent write by anyone, so nothing ever aged out.
    """
    rc = FakeRedis(now=T0)
    st.record_query(rc, "old news", now=T0 - 25 * HOUR)
    st.record_query(rc, "old news", now=T0 - 25 * HOUR)

    assert _members(st.read_window(rc, 5, now=T0)) == [], (
        "a term last searched 25 h ago is outside a 24 h window — if it is "
        "still here, the window is not a window"
    )


def test_a_query_from_one_hour_ago_IS_in_the_window():
    """The mirror. A window that drops everything is not a fix, it is a cliff."""
    rc = FakeRedis(now=T0)
    st.record_query(rc, "stanley cup", now=T0 - 1 * HOUR)

    assert _members(st.read_window(rc, 5, now=T0)) == ["stanley cup"]


def test_continuous_traffic_does_not_keep_ancient_scores_alive():
    """🔴 THE EXACT MECHANISM OF #2072, replayed.

    The old code's TTL never fired *because the site never went quiet*. So the
    test writes continuously for four days — the condition under which the old
    shape accumulated forever — and asserts the ancient term is still gone.
    """
    rc = FakeRedis(now=T0)
    st.record_query(rc, "ancient", now=T0)
    for hour in range(1, 96):  # four days of unbroken traffic
        st.record_query(rc, "chatter", now=T0 + hour * HOUR)

    at = T0 + 95 * HOUR
    assert "ancient" not in _members(st.read_window(rc, 20, now=at)), (
        "unbroken traffic must not keep a four-day-old score alive; that is "
        "precisely how the old key became an all-time counter"
    )


def test_a_breaking_term_can_overtake_an_entrenched_all_time_leader():
    """Cost 3 from the issue: 'nothing organic gets there'.

    5,000 hits spread over the two days BEFORE the window, against 20 hits in
    the last hour. The recent term must win — under the old shape it could not,
    ever.
    """
    rc = FakeRedis(now=T0)
    for i in range(5_000):
        st.record_query(rc, "world cup", now=T0 - (48 - (i % 24)) * HOUR)
    for _ in range(20):
        st.record_query(rc, "breaking story", now=T0 - 0.5 * HOUR)

    top = _members(st.read_window(rc, 5, now=T0))
    assert top[:1] == ["breaking story"], f"entrenched leader survived: {top}"
    assert "world cup" not in top


# ---------------------------------------------------------------------------
# The bucketing itself — the properties the rolling behaviour rests on.
# ---------------------------------------------------------------------------


def test_a_bucket_key_names_the_only_hour_in_which_it_can_be_written():
    """Why re-issuing EXPIRE is safe HERE and was fatal THERE.

    The old key had no time in its name, so writes to it never stopped and the
    refreshed TTL never came due. A bucket key names its hour, so writes to it
    stop when that hour ends — the refreshed TTL is bounded by construction.
    This is the single fact that makes the fix correct rather than a reshuffle.
    """
    k1 = st.bucket_key(T0)            # HH:30
    k2 = st.bucket_key(T0 + 10 * 60)  # HH:40 — same hour
    k3 = st.bucket_key(T0 + 40 * 60)  # HH+1:10 — next hour

    assert k1 == k2 and k1 != k3
    assert k1.startswith(st.TRENDING_BUCKET_PREFIX)
    assert k1[len(st.TRENDING_BUCKET_PREFIX):].isdigit()
    assert len(k1[len(st.TRENDING_BUCKET_PREFIX):]) == 10  # YYYYMMDDHH, UTC


def test_bucket_ttl_outlives_every_window_that_still_needs_the_bucket():
    """A bucket must not vanish while it is still inside the window.

    Worst case: the bucket's LAST write lands at the very start of its hour, and
    it stays in the window until `TRENDING_WINDOW_HOURS` whole hours later plus
    the partial hour of bucket granularity. Anything less and the oldest bucket
    disappears early, silently shortening the window.
    """
    needed_s = (st.TRENDING_WINDOW_HOURS + 2) * HOUR
    assert st.BUCKET_TTL_SECONDS >= needed_s, (
        "TTL is shorter than the window it serves — buckets would expire while "
        "still being summed"
    )
    # ...and bounded, so a bucket cannot become the old immortal key by another
    # route. Twice the window is generous; ten times would be a leak.
    assert st.BUCKET_TTL_SECONDS <= 2 * st.TRENDING_WINDOW_HOURS * HOUR


def test_the_window_covers_at_least_its_advertised_hours():
    """Over-covering is the honest direction for a window named as a floor.

    Hour-granularity buckets cannot land exactly on 24 h. Covering 24-25 h keeps
    the promise; covering 23-24 h breaks it for part of every hour.
    """
    keys = st.window_bucket_keys(T0)
    assert len(keys) == st.TRENDING_WINDOW_HOURS + 1
    assert keys[0] == st.bucket_key(T0)
    assert st.bucket_key(T0 - st.TRENDING_WINDOW_HOURS * HOUR) in keys


def test_scores_sum_across_buckets_rather_than_taking_the_best_hour():
    """Three hits spread over three hours beats two hits in one hour."""
    rc = FakeRedis(now=T0)
    for h in (1, 2, 3):
        st.record_query(rc, "spread", now=T0 - h * HOUR)
    for _ in range(2):
        st.record_query(rc, "burst", now=T0 - 1 * HOUR)

    rows = st.read_window(rc, 5, now=T0)
    assert rows[0] == ("spread", 3.0)
    assert rows[1] == ("burst", 2.0)


# ---------------------------------------------------------------------------
# Degradation, absence, and the guards the old code carried.
# ---------------------------------------------------------------------------


def test_a_fresh_redis_reads_empty_rather_than_raising():
    assert st.read_window(FakeRedis(now=T0), 5, now=T0) == []


def test_an_unreadable_redis_returns_empty_and_does_not_propagate():
    """A trending list is never worth a 500 — the old route caught broadly too."""

    class Broken:
        def __getattr__(self, name):
            def _boom(*a, **kw):
                raise RuntimeError("redis down")

            return _boom

    assert st.read_window(Broken(), 5, now=T0) == []
    assert st.record_query(Broken(), "red sox", now=T0) is False


def test_short_queries_are_still_not_recorded():
    """The route's `len(normalized) >= 3` guard moved into the helper intact.

    It is a real guard, not noise: two-character prefixes are typed on the way
    to every query and would dominate any count that admitted them.
    """
    rc = FakeRedis(now=T0)
    assert st.record_query(rc, "ab", now=T0) is False
    assert st.record_query(rc, "  a  ", now=T0) is False
    assert st.record_query(rc, "abc", now=T0) is True
    assert _members(st.read_window(rc, 5, now=T0)) == ["abc"]


def test_queries_are_normalized_exactly_as_the_route_did():
    rc = FakeRedis(now=T0)
    st.record_query(rc, "  Red Sox  ", now=T0)
    st.record_query(rc, "RED SOX", now=T0)
    assert st.read_window(rc, 5, now=T0) == [("red sox", 2.0)]


def test_the_scratch_aggregate_key_is_outside_the_bucket_namespace():
    """A scratch key inside the bucket prefix would be summed into itself.

    Not hypothetical: the aggregate is a zset written next to the buckets, and
    the natural name for it collides with the natural glob for them.
    """
    assert not st.AGGREGATE_KEY.startswith(st.TRENDING_BUCKET_PREFIX)
    assert st.AGGREGATE_KEY not in st.window_bucket_keys(T0)


def test_the_scratch_aggregate_cannot_outlive_a_reader():
    """It is written by a READ path, so an orphan must expire on its own."""
    rc = FakeRedis(now=T0)
    st.record_query(rc, "red sox", now=T0)
    st.read_window(rc, 5, now=T0)

    assert st.AGGREGATE_KEY in rc.expires_at
    assert 0 < rc.expires_at[st.AGGREGATE_KEY] - rc.now <= 600


# ---------------------------------------------------------------------------
# The three consumers, at the seam. A window nobody reads through is not a fix.
# ---------------------------------------------------------------------------


def test_the_legacy_all_time_key_is_no_longer_written_by_the_route():
    """Source-shape guard, and it replaces the #1866 guard that pinned the old
    literal. A behavioural test cannot see a revert that re-adds the bare
    `zincrby` alongside the new one — both would pass.
    """
    from app.routes import events as events_route

    # RE-POINTED by LAT-P083/#2117: the write moved out of the route body into
    # `events._record_trending`, so both exits could reach one copy of it. The
    # module is read as a whole for the legacy-key check — a bare `zincrby` on
    # the all-time key is forbidden ANYWHERE in this file, not just inside the
    # one function it used to live in, which is a wider net than before.
    module_src = inspect.getsource(events_route)
    helper_src = inspect.getsource(events_route._record_trending)
    assert f'zincrby("{st.LEGACY_TRENDING_KEY}"' not in module_src, (
        "the all-time key is being written again (#2072)"
    )
    # The CALL, not the bare name: the name also appears in the comment above
    # the guard, so a substring search would compare the guard against prose.
    call = "record_query(get_redis_client()"
    assert call in helper_src, "the trending write moved; re-point this guard"

    guard = "if _suppress_trending_write.get():"
    assert guard in helper_src, "the trending write is no longer guarded (#1866)"
    assert helper_src.index(guard) < helper_src.index(call), (
        "the guard must precede the write it guards — #1866 and #2072 are two "
        "halves of one head, and losing either re-freezes it"
    )


@pytest.mark.asyncio
async def test_the_public_trending_endpoint_serves_the_window():
    """`GET /api/events/search/trending` — the endpoint whose docstring lies."""
    from unittest.mock import patch

    from app.routes.events import get_trending_searches

    rc = FakeRedis(now=T0)
    st.record_query(rc, "too old", now=T0 - 30 * HOUR)
    st.record_query(rc, "recent", now=T0 - 2 * HOUR)

    # `_now` is pinned as well as the fake's clock: the route has no clock to
    # hand down, so it calls `read_window` without `now=` and would otherwise
    # sum the buckets around the real wall clock (gotcha #44).
    with patch("app.tasks.redis_state.get_redis_client", lambda *a, **kw: rc), \
            patch.object(st, "_now", lambda: T0):
        payload = await get_trending_searches()

    assert [row["query"] for row in payload["trending"]] == ["recent"]
    assert payload["trending"][0]["count"] == 1


def test_the_warmer_heads_from_the_window_not_from_all_time():
    """🔴 The #1866 interaction, at the seam that matters.

    `_head_from_redis` is the zset half of `_blend_heads`. If it still selected
    on all-time counts, the loop-break would have stopped new pollution while
    the accumulated ~5,400 scores kept the same terms pinned at the top — the
    warmer would go on warming yesterday's head with a clean conscience.
    """
    from unittest.mock import patch

    from app.tasks import typeahead_warmer as warmer

    rc = FakeRedis(now=T0)
    for _ in range(400):
        st.record_query(rc, "world cup", now=T0 - 40 * HOUR)
    st.record_query(rc, "nba champion", now=T0 - 1 * HOUR)

    with patch("app.tasks.redis_state.get_redis_client", lambda *a, **kw: rc), \
            patch.object(st, "_now", lambda: T0):
        head = warmer._head_from_redis(40)

    assert head == ["nba champion"], f"warmer still heading from all-time: {head}"


class _Pipeline:
    """Buffers `record_query`'s two commands and applies them on `execute()`."""

    def __init__(self, rc):
        self._rc = rc
        self._queued = []

    def zincrby(self, key, amount, member):
        self._queued.append(("zincrby", (key, amount, member)))
        return self

    def expire(self, key, seconds):
        self._queued.append(("expire", (key, seconds)))
        return self

    def execute(self):
        out = []
        for name, args in self._queued:
            out.append(getattr(self._rc, name)(*args))
        self._queued.clear()
        return out
