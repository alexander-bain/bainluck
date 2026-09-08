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
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    feed_response_cache_key,
    feed_response_cache_ttls,
    live_total_age_headroom_s,
    payload_contains_live_event,
)

# The bare `GET /api/feed` shape after the route's own Discover defaulting.
# Built from the SAME function the route uses so it cannot drift from the key
# under test (the LAT-P089 suite's convention, kept deliberately).
_BARE_FEED_SHAPE = dict(
    sport=None,
    limit=200,
    offset=0,
    include_events=True,
    include_futures=True,
    tags=None,
    event_pct=0.15,
    my_teams_only=False,
    mode="discover",
)

#: The returning visitor: ONE stable session id across opens. That is the whole
#: cohort distinction — a new id per open is the `new_session` cohort, which
#: never breached, and omitting the header entirely is `first_time`, which also
#: never breached.
_SESSION_ID = "returning-install-uuid-4013"

SHARED_KEY = feed_response_cache_key(user_id=None, session_id=None, **_BARE_FEED_SHAPE)
PRIVATE_KEY = feed_response_cache_key(
    user_id=None, session_id=_SESSION_ID, **_BARE_FEED_SHAPE
)


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

    def spy_schedule(coro):
        return asyncio.ensure_future(coro)

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
    # Let the detached private-key backfill run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return resp, built


def _returning_headers():
    return {"x-session-id": _SESSION_ID}


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

    def test_a_first_time_visitor_shares_the_warmed_key(self):
        """No `x-session-id` at all resolves the key the warmer keeps warm.

        This is what `lib/api.ts` deliberately sends for a fresh zero-interaction
        visitor, and it is why that cohort read 0/19 breaches.
        """
        first_time_key = feed_response_cache_key(
            user_id=None, session_id=None, **_BARE_FEED_SHAPE
        )
        assert first_time_key == SHARED_KEY


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
# THE CODEQL ANNOTATION ON THE CACHE KEY. Not part of #4013's mechanism, but
# shipped with it because standing notice 32 refuses the sha otherwise.
# --------------------------------------------------------------------------


class TestTheCacheKeyDigestIsUnchangedByTheCodeqlAnnotation:
    """`usedforsecurity=False` must be an annotation and nothing else.

    CodeQL reads the principal ids hashed into a feed cache key as sensitive
    input to a weak hash (`py/weak-sensitive-data-hashing`, HIGH), which blocks
    every merge gate. The flag is the sanctioned way to say "this hash
    authenticates nothing" — it derives a Redis key from a request shape, and a
    collision costs a wrong cache entry, not a broken secret.

    The digests below were captured from the function BEFORE the flag was added
    and are frozen here. If a change ever moves one, the feed response cache
    cold-starts on deploy for every key at once — which is a 2.30s p50 build
    for every reader, not a cosmetic diff. That is worth a frozen constant.
    """

    _SHAPE = dict(
        sport=None,
        limit=200,
        offset=0,
        include_events=True,
        include_futures=True,
        tags=None,
        event_pct=0.15,
        my_teams_only=False,
        mode="discover",
    )

    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            (
                dict(user_id=None, session_id=None),
                "feed_cache:2e0423972493e5a8bdff9d3307bed1c7",
            ),
            (
                dict(user_id=None, session_id="returning-install-uuid-4013"),
                "feed_cache:1f1b827af3024099499f5b2810977971",
            ),
            (
                dict(user_id=42, session_id=None),
                "feed_cache:717c51d67a63963206eb5bfc26d867e0",
            ),
            (
                dict(user_id=None, session_id=None, category="politics"),
                "feed_cache:1fc676a99155fdd5a550d000f73d8795",
            ),
            (
                dict(user_id=7, session_id="x"),
                "feed_cache:a4bbc61044de60171b4bdf067e7d0557",
            ),
        ],
    )
    def test_the_digest_is_byte_identical_to_the_pre_annotation_key(
        self, kwargs, expected
    ):
        assert feed_response_cache_key(**kwargs, **self._SHAPE) == expected
