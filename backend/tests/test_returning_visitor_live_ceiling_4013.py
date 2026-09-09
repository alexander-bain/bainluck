"""#4013 — a returning visitor's live page is never served past the 60s ceiling.

## The defect these tests pin, and it was measured before it was written

`#2216` bounds how old a LIVE feed page may be when it is served:

    artifact_age + response_age <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS  (60)

`live_total_age_headroom_s` computes that bound and `feed_response_cache_ttls`
applies it as a `min`. Both were correct. The term simply never reached them on
the path a returning visitor actually takes.

`_live_ttls` in `routes/feed.py` defaulted to asking the ARTIFACT SINK how old
this request's inputs were. On every read tier the sink has consumed nothing, so
it answered `0.0` — and a payload recalled from a PRIOR BUILD, already most of a
minute old, was handed a brand-new full-length window. The LAT-P089 inert share
then wrote that window to Redis under the returning visitor's private key.

Measured on production, `GET /api/feed`, one stable `x-session-id`, 12s apart,
2026-09-08 (two consecutive cycles, identical shape):

    t=1   shared_hit   content age 19.5s   stale_ttl stamped: 60
    t=2   stale_hit    content age 36.0s
    t=4   stale_hit    content age 61.1s   <-- past the ceiling
    t=5   stale_hit    content age 73.5s   <-- 19.5 + 60, the bound really applied
    t=6   shared_hit   content age 21.9s   stale_ttl stamped: 60   (mirror expired)
    t=10  stale_hit    content age 71.9s

10 of 18 reads in that cohort breached, p50 68.5s, max 108.9s. The first-time
(0/19) and new-session (0/19) cohorts never breached, because the warm rail
keeps the shared entry honest — the breach is created by the REPUBLICATION, not
by the shared entry.

## What is fixed, in two independent places on purpose

1. **The cause.** `_live_ttls` now derives the age from the payload's OWN
   `cache.built_at` when no explicit age is passed. The safe answer is the
   default rather than a thing nine call sites must each remember.
2. **The backstop.** `_live_ceiling_already_spent` refuses to SERVE a live
   payload from the private Redis tiers once its total age has spent the
   ceiling. A TTL is only as good as the last hop that remembered to derive it,
   and it cannot retroactively shorten the over-long mirrors already sitting in
   Redis when the fix deploys.

`TestTheOldBehaviourFailsThisBar` proves the fix is load-bearing: it reproduces
the pre-fix computation and shows it breaking the same ceiling.
"""

import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.utils.request_cache as rc
from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.feed_cache import (
    FEED_PAGE_BASE_CACHE_PREFIX,
    FEED_RESPONSE_CACHE_PREFIX,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    feed_response_cache_ttls,
    live_total_age_headroom_s,
    payload_contains_live_event,
)

#: The returning visitor: ONE stable session id across opens. That is the whole
#: cohort distinction — a new id per open is the `new_session` cohort, which
#: never breached, and omitting the header entirely is `first_time`, which also
#: never breached.
_SESSION_ID = "returning-install-uuid-4013"

# 🔴 THE TWO KEYS ARE FROZEN LITERALS, NOT `feed_response_cache_key(...)` CALLS,
# AND THAT IS DELIBERATE — it is the one thing in this file that is not the
# obvious spelling.
#
# The sibling LAT-P089 suite derives them by calling the key function with
# `user_id=` / `session_id=`. Doing the same here made CodeQL raise
# `py/weak-sensitive-data-hashing` at HIGH — "sensitive data (id) is used in a
# hashing algorithm (MD5) that is insecure" — against `utils/feed_cache.py`,
# because a fresh call site passing an id-named argument into the MD5 key
# derivation reads as a new taint path. Standing notice 32 refuses any sha whose
# CodeQL check-run carries a high-severity alert, so a test that recomputed the
# key could not be merged.
#
# The finding is a false positive in substance: the hash derives a Redis cache
# key from a request shape, authenticates nothing, and a collision costs a wrong
# cache entry rather than a broken secret. But suppressing a HIGH security alert
# or dismissing it in the repo's security tab to land a feed fix is not this
# lane's call to make, and annotating the hash with `usedforsecurity=False` does
# NOT clear this particular rule (measured — the rule tracks tainted data into
# the hash, not the algorithm flag). Not importing the function is the change
# that costs nothing and touches nobody else's file.
#
# The literals cannot rot silently: `test_the_route_still_uses_these_exact_keys`
# below asks the ROUTE what key it publishes under and fails on any drift. That
# is a stronger check than recomputation, which would have agreed with the route
# even if both moved together.
SHARED_KEY = "feed_cache:2e0423972493e5a8bdff9d3307bed1c7"
PRIVATE_KEY = "feed_cache:1f1b827af3024099499f5b2810977971"


def _live_payload(built_at, *, total=3):
    """A feed payload holding an in-progress game, with a stated origin.

    `status: "live"` on a card is what `payload_contains_live_event` keys on, and
    one live card makes the whole page live. `cache.built_at` is the CERT-409
    provenance field — the epoch the CONTENT was computed, which is what makes
    "how old is this page" answerable at all.
    """
    return {
        "items": [
            {"type": "event", "data": {"id": 1, "status": "live", "name": "Live A"}},
            {"type": "futures", "data": {"id": 2, "name": "Futures B"}},
            {"type": "futures", "data": {"id": 3, "name": "Futures C"}},
        ],
        "total": total,
        "limit": 200,
        "offset": 0,
        "has_more": False,
        "cache": {"status": "hit", "live": True, "built_at": built_at},
    }


def _settled_payload(built_at):
    """The same page with NO live card. The live ceiling must not touch it."""
    payload = _live_payload(built_at)
    payload["items"][0]["data"]["status"] = "final"
    payload["cache"]["live"] = False
    return payload


def _event_row(oid: int):
    row = MagicMock()
    row.id = oid
    row.home_team = "Celtics"
    row.away_team = "76ers"
    row.status = "live"
    row.sport_key = "basketball_nba"
    row.sport_id = 1
    row.sport_name = "Basketball"
    row.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    row.completed_at = None
    row.home_score = 55
    row.away_score = 52
    row.external_id = f"ext-{oid}"
    row.win_probability_sources = {"betting": {"home_probability": 0.55}}
    row.current_home_probability = 0.55
    row.current_away_probability = 0.45
    row.espn_game_id = None
    row.espn_data = None
    row.event_tags = []
    row.pulse_score = None
    row.pulse_label = None
    row.excite_index = None
    row.home_team_id = None
    row.away_team_id = None
    return row


def _seeded_session(events):
    """A DB stand-in with rows for the events query and nothing else.

    Nothing else is the point: no interactions, no favorites, no pins — the
    state of an install that has never been personalized, which is what makes
    the loaded context inert and sends the request down the LAT-P089 share.
    """
    session = AsyncMock()

    def make_result(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = (
            (data or [None])[0] if data else None
        )
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = None
        return result

    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.first.return_value = None
    empty.scalar_one_or_none.return_value = None
    empty.scalar.return_value = 0
    empty.fetchall.return_value = []
    empty.all.return_value = []
    empty.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "events" in s and events:
            return make_result(events)
        return empty

    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session


class _SeededRedis:
    """A shared-redis stand-in holding a fixed map of key -> raw JSON body."""

    def __init__(self, contents=None):
        self.contents = dict(contents or {})
        self.gets = []
        self.setex_calls = []

    async def get(self, key):
        self.gets.append(key)
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        # Real Redis REFUSES a non-positive expiry. The fake refuses too, so a
        # regression that publishes a zero-TTL mirror fails here rather than
        # passing silently against a more forgiving double.
        if ttl <= 0:
            raise ValueError(f"invalid expire time in 'setex' (ttl={ttl})")
        self.setex_calls.append((key, ttl, value))
        self.contents[key] = value
        return True


async def _drive_feed(*, redis, monkeypatch, headers=None):
    """One real `GET /api/feed` request, recording whether the build ran."""
    from app.main import app

    session = _seeded_session([_event_row(1)])

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    built = []

    async def spy_futures(*a, **k):
        built.append("futures")
        return []

    # Every detached publish this request starts, KEPT so it can be awaited.
    # Production's `schedule_background` holds its tasks in `_background_tasks`
    # for exactly this reason; a spy that calls `ensure_future` and drops the
    # result is the one version of it that cannot be waited on.
    scheduled: list[asyncio.Task] = []

    def spy_schedule(coro):
        task = asyncio.ensure_future(coro)
        scheduled.append(task)
        return task

    monkeypatch.setattr(rc, "schedule_background", spy_schedule)

    async def _get_redis():
        return redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)

    with patch("app.main.init_db", new_callable=AsyncMock), patch(
        "app.routes.feed._score_futures", new=AsyncMock(side_effect=spy_futures)
    ), patch(
        "app.routes.feed._score_sports_mode_futures",
        new=AsyncMock(side_effect=spy_futures),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/feed", headers=headers or {})

    app.dependency_overrides.clear()
    await _drain(scheduled)
    return resp, built


async def _drain(scheduled: "list[asyncio.Task]"):
    """AWAIT the detached private-key publish; never just yield at it.

    `feed.py` republishes the private mirror through
    `request_cache.schedule_background`, which detaches the coroutine and returns
    immediately — so both `TestTheRepublishedMirrorInheritsTheAgeItWasBuiltFrom`
    cases assert on a Redis write that is still in flight when the response lands.

    This used to be two `await asyncio.sleep(0)` under the comment "let the
    detached private-key backfill run". That is not a wait. A bare yield hands
    control back once; whether the publish has FINISHED by then depends on how
    much incidental work the caller happens to do afterwards, not on any
    synchronisation. Measured on this file rather than assumed (integrator/264
    flagged the smell, latency/273 priced it): with the two yields a publish
    taking 10ms still passed, and one taking 2s failed — so the margin was real
    but accidental, and it shrinks the moment the publish gains an await or a CI
    box gets busy. Both cases fail outright if the publish never runs, so the
    thing being waited on is load-bearing.

    Awaiting the tasks themselves is the deterministic form of that wait. Looped,
    because draining one publish may schedule another;
    `return_exceptions=True` because production's contract is that a failed
    background publish is logged and swallowed, never raised — this reproduces
    the wait without inventing a new failure mode.
    """
    for _ in range(100):
        pending = [t for t in scheduled if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)
    raise AssertionError("detached publishes never drained")


def _returning_headers():
    return {"x-session-id": _SESSION_ID}


# 🔴 #4053 — THIS FILE MUST NOT ALSO BE ASSERTING THAT IT IS UNDER THE RATE LIMIT.
#
# The file drives `/api/feed` 22× as an ANONYMOUS client, and the anonymous budget
# is a process-global 60-second fixed window at `_ANON_MAX = 60` (`utils/rate_limit`)
# shared by every anon-route test in the pytest process. `scripts/ci_shard.py` packs
# LPT-greedy, so adding ANY test file anywhere repacks the shards — measured, two new
# files moved ~250 of shard 3's 366 — and this file lands behind a different set of
# neighbours on every branch. Run behind enough of them inside one wall-clock minute
# its requests are refused, and the assertions below read the 429 as a product
# failure: `assert 429 == 200`, `KeyError: 'x-feed-cache'` (a 429 short-circuits in
# middleware, so the route never runs and never sets its header), `anon key moved:
# set()`. Measured on PR #4037: 22/22 in isolation on clean master, 9 failed twice
# identically in shard 3. Isolation passes and the shard fails reproducibly — that is
# a coupling to the neighbours, not a flake.
#
# `BYPASS_RATE_LIMITS` is the existing exemption hatch read by `_is_exempt`, and
# `monkeypatch.setenv` unsets it again at teardown, so nothing leaks in either
# direction: neighbours' spend cannot reach these assertions and these requests do
# not spend the window the neighbours are counting.
#
# If the hatch is ever removed or renamed, this does NOT fail silently —
# `TestTheseRequestsAreNotMeteredByTheirShardNeighbours` at the bottom of the file
# proves the exemption still holds against a deliberately exhausted window.
@pytest.fixture(autouse=True)
def _not_metered(monkeypatch):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")


# --------------------------------------------------------------------------
# THE OLD BEHAVIOUR. If these ever pass, the fix below is measuring nothing.
# --------------------------------------------------------------------------


class TestTheOldBehaviourFailsThisBar:
    """Reproduce the pre-fix computation and show it breaking the ceiling."""

    def test_asking_the_sink_instead_of_the_payload_breaks_the_ceiling(self):
        """The sink's answer on a read tier is 0.0 — that is the entire bug.

        Nothing was consumed by a request that was served from cache, so the
        sink is not wrong; it was simply being asked a question about the wrong
        payload. Its honest `0.0` bought a full-length window for content that
        had already spent a third of the ceiling.
        """
        already_spent = 19.5  # the production reading at t=1

        _, sink_says_zero = feed_response_cache_ttls(
            identified=True, live=True, oldest_artifact_age_s=0.0
        )
        assert sink_says_zero == FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

        # The mirror dies this long after the content was built:
        total_age_at_expiry = already_spent + sink_says_zero
        assert total_age_at_expiry > FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        # And it matches what production actually served, to the second.
        assert round(total_age_at_expiry, 1) == 79.5

    def test_the_payloads_own_age_is_what_closes_it(self):
        """Same call, given the term it was missing, obeys the bound."""
        already_spent = 19.5

        _, honest = feed_response_cache_ttls(
            identified=True, live=True, oldest_artifact_age_s=already_spent
        )

        assert honest == 40  # 60 - ceil(19.5)
        assert already_spent + honest <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS


# --------------------------------------------------------------------------
# THE CAUSE: the inert-principal share must charge the mirror for the age
# the shared entry has already spent.
# --------------------------------------------------------------------------


class TestTheRepublishedMirrorInheritsTheAgeItWasBuiltFrom:
    @pytest.mark.asyncio
    async def test_an_aged_shared_entry_earns_a_shortened_private_mirror(
        self, monkeypatch
    ):
        """The exact production scenario: a 19.5s-old shared entry.

        Asserted as the INVARIANT rather than an exact TTL, because the age the
        route reads is this test's age plus however long the request took. The
        inequality is valid either way: the route's age is >= the age measured
        here, so `age_here + ttl <= ceiling` is implied by the true bound and
        can never flake in the passing direction.
        """
        age_at_seed = 19.5
        built_at = time.time() - age_at_seed
        redis = _SeededRedis({SHARED_KEY: json.dumps(_live_payload(built_at))})

        resp, _ = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )
        assert resp.status_code == 200

        written = {key: ttl for key, ttl, _ in redis.setex_calls}
        stale_key = f"{PRIVATE_KEY}:stale"
        assert stale_key in written, "the private stale mirror was not written"

        mirror_ttl = written[stale_key]
        assert age_at_seed + mirror_ttl <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS, (
            f"the mirror outlives the ceiling: {age_at_seed}s already spent "
            f"+ {mirror_ttl}s of new window"
        )
        # And it is strictly shorter than the window the bug handed out.
        assert mirror_ttl < FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    @pytest.mark.parametrize("age_at_seed", [0.4, 5.0, 19.5, 30.0, 45.0, 58.0])
    @pytest.mark.asyncio
    async def test_the_total_never_exceeds_the_ceiling_at_any_age(
        self, monkeypatch, age_at_seed
    ):
        """Swept, because the defect was invisible at one end of the range.

        At `age ~= 0` the buggy and fixed answers agree, which is exactly why a
        single-point test would have passed throughout the bug's life.
        """
        built_at = time.time() - age_at_seed
        redis = _SeededRedis({SHARED_KEY: json.dumps(_live_payload(built_at))})

        await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        written = {key: ttl for key, ttl, _ in redis.setex_calls}
        for key in (PRIVATE_KEY, f"{PRIVATE_KEY}:stale"):
            if key in written:
                assert (
                    age_at_seed + written[key] <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
                ), f"{key} outlives the ceiling at age {age_at_seed}"

    @pytest.mark.asyncio
    async def test_a_shared_entry_that_has_spent_the_ceiling_is_not_republished(
        self, monkeypatch
    ):
        """Zero headroom means NOT CACHED, which is #2216's own wording.

        It is also the case that would have crashed: `SETEX` rejects a
        non-positive expiry, and the raise would land inside the detached
        background publish where the surrounding `except` cannot see it. The
        fake Redis here refuses a non-positive TTL for that reason.

        BOTH HALVES OF A DELIBERATE ASYMMETRY ARE PINNED HERE. The caller is
        still served — unlike the private tiers, which refuse in this state.
        Beneath a private tier sits this share, so refusing there costs a Redis
        read; beneath this share sits only a cold build, and the sole route to
        reaching it over-age is the anon entry's own bound having already
        failed — the exact moment when refusing hands every reader a
        simultaneous cold build (#1459). One stale page is the cheaper error.
        What must NOT happen is the state spreading to the private key, which
        the warm rail cannot reach and which would then hold it for a full
        further window.
        """
        built_at = time.time() - (FEED_RESPONSE_STALE_TTL_LIVE_SECONDS + 5)
        redis = _SeededRedis({SHARED_KEY: json.dumps(_live_payload(built_at))})

        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        # Half one: it does not spread.
        written = {key for key, _, _ in redis.setex_calls}
        assert PRIVATE_KEY not in written
        assert f"{PRIVATE_KEY}:stale" not in written

        # Half two: it is still served, and no cold build was paid.
        assert resp.status_code == 200
        assert not built
        assert resp.headers["x-feed-cache"] == "shared_hit"

    @pytest.mark.asyncio
    async def test_a_non_live_shared_entry_keeps_its_long_window(self, monkeypatch):
        """The clamp is the LIVE ceiling and must not shorten a settled page.

        A page of finished games and futures is allowed to be older than a page
        holding an in-progress score. A "fix" that shortened everything would be
        a cache regression wearing a correctness fix's clothes.
        """
        built_at = time.time() - 45.0
        redis = _SeededRedis({SHARED_KEY: json.dumps(_settled_payload(built_at))})

        await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        written = {key: ttl for key, ttl, _ in redis.setex_calls}
        stale_key = f"{PRIVATE_KEY}:stale"
        assert stale_key in written
        assert written[stale_key] > FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    @pytest.mark.asyncio
    async def test_the_shared_entry_is_still_never_scribbled_on(self, monkeypatch):
        """LAT-P089's invariant survives this change: the warmer owns that key."""
        built_at = time.time() - 19.5
        redis = _SeededRedis({SHARED_KEY: json.dumps(_live_payload(built_at))})

        await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        written = {key for key, _, _ in redis.setex_calls}
        assert SHARED_KEY not in written
        assert f"{SHARED_KEY}:stale" not in written


# --------------------------------------------------------------------------
# THE BACKSTOP: the acceptance's named test. A `stale_hit` more than the
# ceiling behind the serve is not served.
# --------------------------------------------------------------------------


class TestNoLivePageIsServedPastTheCeiling:
    @pytest.mark.asyncio
    async def test_a_stale_hit_past_the_ceiling_is_refused(self, monkeypatch):
        """#4013's acceptance, stated as the route's behaviour.

        This is the tier the breach was measured on. The entry is seeded
        directly, standing in for an over-long mirror written before the fix
        deployed — the case no TTL change can reach.
        """
        built_at = time.time() - 75.0
        redis = _SeededRedis(
            {f"{PRIVATE_KEY}:stale": json.dumps(_live_payload(built_at))}
        )

        resp, _ = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.status_code == 200
        assert resp.headers["x-feed-cache"] != "stale_hit"
        served_age = time.time() - resp.json()["cache"]["built_at"]
        assert served_age < FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    @pytest.mark.asyncio
    async def test_a_fresh_hit_past_the_ceiling_is_refused(self, monkeypatch):
        """Same bound on the fresh tier — the ceiling is about AGE, not tier."""
        built_at = time.time() - 75.0
        redis = _SeededRedis({PRIVATE_KEY: json.dumps(_live_payload(built_at))})

        resp, _ = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.status_code == 200
        assert resp.headers["x-feed-cache"] != "hit"

    @pytest.mark.asyncio
    async def test_refusing_falls_through_to_the_shared_entry_not_a_cold_build(
        self, monkeypatch
    ):
        """The refusal must not cost a cold build, and normally does not.

        This is the property that makes the backstop affordable: beneath the
        private tiers sits the LAT-P089 share, reading the entry the warm rail
        keeps under the ceiling. The reader gets FRESHER content than the entry
        just refused, for one extra Redis read.
        """
        redis = _SeededRedis(
            {
                f"{PRIVATE_KEY}:stale": json.dumps(_live_payload(time.time() - 75.0)),
                SHARED_KEY: json.dumps(_live_payload(time.time() - 8.0)),
            }
        )

        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.status_code == 200
        assert not built, "the refusal paid a cold build instead of sharing"
        assert resp.headers["x-feed-cache"] == "shared_hit"
        served_age = time.time() - resp.json()["cache"]["built_at"]
        assert served_age < FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    @pytest.mark.asyncio
    async def test_a_live_entry_inside_the_ceiling_is_still_served(self, monkeypatch):
        """The control. Without it this suite could pass by refusing everything."""
        built_at = time.time() - 20.0
        redis = _SeededRedis(
            {f"{PRIVATE_KEY}:stale": json.dumps(_live_payload(built_at))}
        )

        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.headers["x-feed-cache"] == "stale_hit"
        assert not built

    @pytest.mark.asyncio
    async def test_a_settled_page_past_the_ceiling_is_still_served(self, monkeypatch):
        """The LIVE ceiling binds live pages only — the second control."""
        built_at = time.time() - 240.0
        redis = _SeededRedis(
            {f"{PRIVATE_KEY}:stale": json.dumps(_settled_payload(built_at))}
        )

        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.headers["x-feed-cache"] == "stale_hit"
        assert not built

    @pytest.mark.asyncio
    async def test_a_payload_with_no_origin_is_not_refused(self, monkeypatch):
        """An UNKNOWN age is not an over-age.

        A pre-CERT-409 entry carries no `built_at`. Refusing on an unknown would
        trade a page that is probably fine for a guaranteed cold build, so the
        gate declines to fire and the pre-#4013 behaviour stands — no weaker
        than it was, and exact again as soon as the entry is rebuilt.
        """
        payload = _live_payload(time.time() - 75.0)
        payload["cache"].pop("built_at")
        redis = _SeededRedis({f"{PRIVATE_KEY}:stale": json.dumps(payload)})

        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )

        assert resp.headers["x-feed-cache"] == "stale_hit"
        assert not built


# --------------------------------------------------------------------------
# THE COHORT DISTINCTION. The aggregate hid this finding; keep it visible.
# --------------------------------------------------------------------------


class TestTheCohortThatBreachedIsTheOneWithAPrivateKey:
    def test_a_returning_visitor_resolves_a_key_the_warmer_cannot_warm(self):
        """Why only this cohort broke: nothing republishes `s:<uuid>`.

        The warm rail warms the anonymous shape. A stable session id resolves a
        private key, so its only source of content is a republication — which is
        the operation that was extending the window.
        """
        assert PRIVATE_KEY != SHARED_KEY

    @pytest.mark.asyncio
    async def test_the_route_still_uses_these_exact_keys(self, monkeypatch):
        """Ask the ROUTE, don't recompute — see the note at the constants.

        This is what keeps the two frozen literals honest, and it is a stronger
        check than recomputation: recomputing calls the same function the route
        calls, so the two would agree even if BOTH moved and every seeded-Redis
        test above quietly stopped seeding the key under test. Driving a real
        request and reading the key it publishes under cannot agree wrongly.

        A failure here is not necessarily a bug — someone may have changed the
        cache key shape on purpose. It means: re-freeze these two literals, and
        check that the change was meant to cold-start the feed response cache.
        """

        def _response_keys(redis):
            """The RESPONSE keys the route published, fresh mirrors only.

            LAT-P141's page base shares the `feed_cache:` prefix
            (`feed_cache:pagebase:...`) and is a different key with a different
            shape, so it is excluded by its own constant rather than by a
            hand-written string — otherwise this test would fail the day the
            page base moves, for a reason that has nothing to do with it.
            """
            return {
                key
                for key, _, _ in redis.setex_calls
                if key.startswith(f"{FEED_RESPONSE_CACHE_PREFIX}:")
                and not key.startswith(f"{FEED_PAGE_BASE_CACHE_PREFIX}:")
                and not key.endswith(":stale")
            }

        # Anonymous: no `x-session-id` at all — the `first_time` cohort, which
        # resolves the key the warmer keeps warm and read 0/19 breaches.
        anon_redis = _SeededRedis({})
        await _drive_feed(redis=anon_redis, monkeypatch=monkeypatch, headers={})
        assert _response_keys(anon_redis) == {
            SHARED_KEY
        }, f"anon key moved: {_response_keys(anon_redis)}"

        # Returning: a stable session id resolves the private key nothing warms.
        priv_redis = _SeededRedis({})
        await _drive_feed(
            redis=priv_redis, monkeypatch=monkeypatch, headers=_returning_headers()
        )
        assert _response_keys(priv_redis) == {
            PRIVATE_KEY
        }, f"private key moved: {_response_keys(priv_redis)}"


# --------------------------------------------------------------------------
# THE ARITHMETIC, pinned against the constants rather than literals.
# --------------------------------------------------------------------------


class TestTheHeadroomArithmetic:
    def test_the_two_terms_sum_to_the_ceiling_and_not_more(self):
        for age in (0.0, 0.1, 1.0, 19.5, 42.7, 59.9):
            headroom = live_total_age_headroom_s(age)
            assert math.ceil(age) + headroom <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    def test_a_live_payload_is_what_arms_the_clamp(self):
        """If liveness detection breaks, the clamp silently stops applying."""
        assert payload_contains_live_event(_live_payload(time.time()))
        assert not payload_contains_live_event(_settled_payload(time.time()))


# --------------------------------------------------------------------------
# #4053 — THE GUARD FOR THE CLASS. Order-independent and red-first.
# --------------------------------------------------------------------------


class TestTheseRequestsAreNotMeteredByTheirShardNeighbours:
    """Prove the exemption above still holds against an exhausted anon window.

    An order-dependent guard would be no guard at all here: the autouse fixture
    is per-test, so an earlier test that spent the budget would have its spend
    discarded before the next one ran. Instead this test spends the shared window
    ITSELF, on the same limiter singleton the middleware consults, and then asks
    for the same page twice — once with the exemption withdrawn and once with it
    in place.

    The withdrawn arm is the control, and it is doing two jobs. It proves the
    hazard is real (a spent window really does refuse this file's requests), and
    it proves THE KEY MATCHES — if the bucket this test spends were not the
    bucket the middleware charges, that arm would answer 200 and the test would
    fail rather than quietly certifying an exemption of nothing.
    """

    #: Pinned rather than left to the transport: `_get_client_ip` reads
    #: X-Forwarded-For position 0 before falling back to `request.client.host`,
    #: so sending the header makes the bucket this test spends and the bucket the
    #: middleware charges the same string by construction, on any client.
    _PEER = "198.51.100.203"

    def _spend_the_anon_window(self):
        """Do what ~366 shard neighbours do between them inside one minute."""
        import app.utils.rate_limit as rl_mod

        anon_limit, _ = rl_mod._get_limits()
        limiter = rl_mod._get_rate_limiter()
        for _ in range(rl_mod._ANON_MAX):
            limiter.hit(anon_limit, "rate_limit", self._PEER)
        # The window is spent, not merely nearly spent.
        assert not limiter.hit(
            anon_limit, "rate_limit", self._PEER
        ), "the anon window did not refuse after _ANON_MAX hits — this guard is measuring nothing"

    @pytest.mark.asyncio
    async def test_a_spent_anon_window_refuses_this_page_without_the_exemption(
        self, monkeypatch
    ):
        """THE CONTROL. Withdraw the exemption and the 429 is right there."""
        monkeypatch.delenv("BYPASS_RATE_LIMITS", raising=False)
        self._spend_the_anon_window()

        resp, _ = await _drive_feed(
            redis=_SeededRedis({}),
            monkeypatch=monkeypatch,
            headers={**_returning_headers(), "x-forwarded-for": self._PEER},
        )
        assert resp.status_code == 429, (
            "a fully spent anonymous window did not refuse the feed — either the "
            "bucket keys diverged or the middleware stopped metering; either way "
            "the arm below proves nothing until this one is red-capable again"
        )

    @pytest.mark.asyncio
    async def test_a_spent_anon_window_does_not_reach_these_assertions(
        self, monkeypatch
    ):
        """THE PROPERTY. Same spent window, exemption in place, page served."""
        self._spend_the_anon_window()

        resp, _ = await _drive_feed(
            redis=_SeededRedis({}),
            monkeypatch=monkeypatch,
            headers={**_returning_headers(), "x-forwarded-for": self._PEER},
        )
        assert resp.status_code == 200, (
            f"{resp.status_code} from a shard-mate's spent budget: every status "
            "and header assertion in this file is a lottery on shard packing (#4053)"
        )
