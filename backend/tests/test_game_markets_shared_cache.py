"""Guard tests for LAT-P121 (#1587): the event page's markets stop being rebuilt
for almost every reader.

WHAT WAS MEASURED, and it is the reason these tests assert CALL COUNT rather
than wall clock. #1587 timed `GET /api/events/{id}/game-markets` on production at
**2,250 ms for 8.5 KB** — the second request of the event detail page, the page
where the probability a person came for lives, one of the four north-star tasks.

The build is not what these tests touch. The cache is:

    _game_markets_cache: dict[int, tuple[float, str, dict]] = {}
    _GAME_MARKETS_MAX_SIZE = 30

A process-global dict of thirty entries. `WEB_CONCURRENCY=2` puts two Uvicorn
workers on every dyno, so a warm entry was visible to a fraction of requests even
for a game everyone was watching; thirty entries is fewer than the feed shows at
once, so the entry for the game you are opening had usually been evicted by games
someone else opened; and it died with the process on every deploy. There was no
shared slot and — the part that costs the wait — no mirror, so a miss had never
had anything to serve except a full rebuild.

Every assertion below is about SHAPE, TTL or CALL COUNT. None is about time.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc


class _FakeRedis:
    """In-memory Redis: get / setex / delete over a dict, with TTLs recorded."""

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


def _body(event_id: int = 7) -> dict:
    return {
        "event_id": event_id,
        "home_team": "Home",
        "away_team": "Away",
        "totals": [],
        "player_props": [],
        "spreads": [],
        "matchups": [],
        "other": [],
        "pace": None,
        "props_script": [],
    }


def _stamped(status: str, *, age_s: float = 0.0, event_id: int = 7) -> dict:
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return gmc.stamp(_body(event_id), source_status=status, created_at=created)


@pytest.fixture(autouse=True)
def _clear_memo():
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


# ---------------------------------------------------------------------------
# The freshness rule is CARRIED ACROSS, not re-invented
# ---------------------------------------------------------------------------


def test_live_fresh_ttl_is_the_in_memory_tier_s_own_number():
    """The shared slot must not quietly re-base how fresh a live hit is.

    This ship changes who can see a cached copy and what a miss costs. If the
    two numbers are allowed to drift, a later reader cannot tell which of those
    two things a latency delta came from.
    """
    assert gmc.FRESH_TTL_LIVE == events_route._GAME_MARKETS_LIVE_TTL


def test_final_statuses_match_the_in_memory_tier_s_own_definition():
    """Finality must not acquire a second definition on the way into Redis."""
    for status in ("completed", "closed"):
        assert gmc.is_final(status)
        # ...and the L1 read agrees, which is the branch that has always existed.
        events_route._game_markets_cache[1] = (0.0, status, {"x": 1})
        assert events_route._read_game_markets_memo(1) == {"x": 1}
        events_route._game_markets_cache.clear()


@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", gmc.FRESH_TTL_FINAL),
        ("closed", gmc.FRESH_TTL_FINAL),
        ("live", gmc.FRESH_TTL_LIVE),
        ("scheduled", gmc.FRESH_TTL_LIVE),
        ("", gmc.FRESH_TTL_LIVE),
        (None, gmc.FRESH_TTL_LIVE),
    ],
)
def test_fresh_ttl_by_status(status, expected):
    assert gmc.fresh_ttl(status) == expected


def test_stale_ttl_is_the_shared_constant_not_a_copy():
    """`write_payload` does not parameterize the mirror, so a local 86400 here
    would be a number the writer never reads."""
    assert gmc.STALE_TTL is concept_cache.STALE_TTL


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_stamp_publishes_all_five_contract_fields():
    payload = _stamped("live")
    envelope = payload[concept_cache.ENVELOPE_FIELD]
    for field in concept_cache.ENVELOPE_FIELDS:
        assert field in envelope, f"contract field {field} absent"
    assert envelope["generation"] == concept_cache.GENERATION
    assert envelope["quality"] == concept_cache.QUALITY_FULL
    # `availability` is the SERVE decision and is stamped on the way out.
    assert envelope["availability"] is None


def test_a_served_payload_passes_the_shared_envelope_validator():
    served = concept_cache.with_availability(
        _stamped("live"), concept_cache.AVAILABILITY_LIVE
    )
    assert concept_cache.envelope_defect(served) is None


def test_stamp_records_the_raw_status_which_the_body_cannot_supply():
    """`response["status"]` is `served_event_status`' presentation value. The
    ceiling is per-status, so the tier stores the row's own status."""
    payload = _stamped("closed")
    assert gmc.source_status_of(payload) == "closed"
    assert "source_status" not in _body()


def test_watermark_is_null_and_not_fabricated_when_there_are_no_markets():
    payload = _stamped("live")
    assert payload[concept_cache.ENVELOPE_FIELD]["lifecycle_watermark"] is None


# ---------------------------------------------------------------------------
# The mirror is AGE-BOUNDED, and the bound is per status
# ---------------------------------------------------------------------------


def test_a_young_live_mirror_is_servable():
    servable, reason = gmc.mirror_is_servable(_stamped("live", age_s=100))
    assert servable and reason == "fresh_enough"


def test_a_live_mirror_past_the_ceiling_is_refused():
    """A 24h mirror of a LIVE game shows prop windows that closed hours ago.

    That is a formatting lie arriving through a latency fix, so past
    5 x 30 s the reader blocks and rebuilds — the pre-LAT-P121 behaviour.
    """
    servable, reason = gmc.mirror_is_servable(_stamped("live", age_s=200))
    assert not servable and reason == "too_old"


def test_a_finished_game_s_mirror_survives_far_longer():
    """Its content stops moving, so the same 24h mirror is honest for hours."""
    assert gmc.mirror_is_servable(_stamped("completed", age_s=4 * 3600))[0]
    assert not gmc.mirror_is_servable(_stamped("completed", age_s=6 * 3600))[0]


def test_an_unknown_status_takes_the_SHORTER_ceiling():
    """The failure mode of a missing field must be a rebuild, never a stale live
    payload. If the default were `completed`, a four-hour-old mirror of a game
    in progress would be served."""
    payload = _stamped("live", age_s=4 * 3600)
    del payload[concept_cache.ENVELOPE_FIELD]["source_status"]
    assert gmc.source_status_of(payload) == ""
    assert not gmc.mirror_is_servable(payload)[0]


def test_a_mirror_that_cannot_say_when_it_was_built_is_refused():
    payload = _stamped("live")
    payload[concept_cache.ENVELOPE_FIELD]["created_at"] = None
    servable, reason = gmc.mirror_is_servable(payload)
    assert not servable and reason == "no_created_at"


def test_mirror_is_servable_refuses_a_non_dict():
    assert gmc.mirror_is_servable("nope") == (False, "absent")


# ---------------------------------------------------------------------------
# read() — the serve decision, published rather than re-derived
# ---------------------------------------------------------------------------


def test_no_redis_client_reads_as_a_miss_and_never_raises():
    with patch.object(gmc, "get_client", return_value=None):
        assert gmc.read(7) == (None, "miss")


def test_primary_hit_is_published_as_live():
    rc = _FakeRedis()
    gmc.write(7, _stamped("live"), rc=rc)
    body, state = gmc.read(7, rc=rc)
    assert state == "live"
    assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


def test_primary_absent_but_young_mirror_is_published_as_stale_ok():
    rc = _FakeRedis()
    gmc.write(7, _stamped("live", age_s=100), rc=rc)
    rc.delete(gmc.keys_for(7).primary)  # what a TTL expiry looks like
    body, state = gmc.read(7, rc=rc)
    assert state == "stale_ok"
    assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


def test_an_over_age_mirror_yields_no_body_so_the_reader_rebuilds():
    rc = _FakeRedis()
    gmc.write(7, _stamped("live", age_s=1000), rc=rc)
    rc.delete(gmc.keys_for(7).primary)
    body, state = gmc.read(7, rc=rc)
    assert body is None and state == "stale_too_old"


def test_write_publishes_both_slots_with_the_status_s_own_ttls():
    rc = _FakeRedis()
    keys = gmc.keys_for(7)
    gmc.write(7, _stamped("live"), rc=rc)
    assert rc.ttls[keys.primary] == gmc.FRESH_TTL_LIVE
    assert rc.ttls[keys.stale] == gmc.STALE_TTL

    rc2 = _FakeRedis()
    gmc.write(9, _stamped("completed"), rc=rc2)
    assert rc2.ttls[gmc.keys_for(9).primary] == gmc.FRESH_TTL_FINAL


def test_the_two_tiers_do_not_share_a_redis_namespace():
    assert not gmc.CACHE_PREFIX.startswith(concept_cache.CACHE_PREFIX)
    assert gmc.keys_for(7).primary != concept_cache.cache_keys("7").primary


def test_stored_bytes_are_json_and_carry_the_envelope():
    rc = _FakeRedis()
    gmc.write(7, _stamped("live"), rc=rc)
    raw = json.loads(rc.store[gmc.keys_for(7).primary].decode())
    assert raw[concept_cache.ENVELOPE_FIELD]["generation"] == concept_cache.GENERATION


# ---------------------------------------------------------------------------
# THE SHIP — the route, and how many times it builds
# ---------------------------------------------------------------------------


class _Session:
    """Enough of an AsyncSession for the watermark aggregate, which is the only
    DB call the cache layer itself makes."""

    async def scalar(self, *_a, **_k):
        return None


@pytest.mark.asyncio
async def test_a_second_reader_on_a_DIFFERENT_process_does_not_rebuild():
    """This is the ship.

    The first reader builds and publishes to the shared slot. The second reader
    is a different worker — no L1 entry — and under the old tier it paid the full
    build. It must now pay a Redis read.
    """
    rc = _FakeRedis()
    builds = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        first = await events_route.get_game_markets(7, _Session())
        assert builds == [7]

        # A different worker: same Redis, empty in-process dict.
        events_route._game_markets_cache.clear()
        second = await events_route.get_game_markets(7, _Session())

    assert builds == [7], "the second reader rebuilt — the shared slot did nothing"
    assert second["event_id"] == first["event_id"]
    assert second[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_a_primary_expiry_serves_the_mirror_and_schedules_ONE_rebuild():
    """A miss must cost a Redis read, not a build — and a burst behind one expiry
    must produce one rebuild, not one per reader."""
    rc = _FakeRedis()
    builds = []
    scheduled = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _body(event_id), "live", []

    def _fake_refresh(name, rebuild):
        scheduled.append(name)
        return True

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        await events_route.get_game_markets(7, _Session())
        rc.delete(gmc.keys_for(7).primary)
        events_route._game_markets_cache.clear()

        with patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
            for _ in range(3):
                events_route._game_markets_cache.clear()
                body = await events_route.get_game_markets(7, _Session())

    assert builds == [7], "a reader behind the expiry paid for a build"
    assert scheduled == ["game_markets:7"] * 3
    assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


@pytest.mark.asyncio
async def test_with_no_loop_to_refresh_behind_us_the_reader_builds():
    """Fail-closed: serving stale with nothing coming to replace it is the one
    outcome worse than being slow."""
    rc = _FakeRedis()
    builds = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        await events_route.get_game_markets(7, _Session())
        rc.delete(gmc.keys_for(7).primary)
        events_route._game_markets_cache.clear()
        with patch.object(
            events_route, "_serve_stale_and_refresh", lambda name, rebuild: False
        ):
            await events_route.get_game_markets(7, _Session())

    assert builds == [7, 7]


@pytest.mark.asyncio
async def test_the_L1_hit_still_short_circuits_before_redis():
    """The in-memory dict was never the defect and it is faster than a round
    trip. A Redis client that raises on every call proves it is not consulted."""

    class _Exploding:
        def get(self, *_a, **_k):
            raise AssertionError("L1 hit must not reach Redis")

        def setex(self, *_a, **_k):
            return None

        def delete(self, *_a, **_k):
            return 0

    rc = _FakeRedis()

    async def _fake_build(event_id, db):
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        await events_route.get_game_markets(7, _Session())

    with patch.object(gmc, "get_client", return_value=_Exploding()):
        again = await events_route.get_game_markets(7, _Session())
    assert again["event_id"] == 7


@pytest.mark.asyncio
async def test_the_wire_shape_is_unchanged_apart_from_the_envelope():
    """Two clients decode this body (`frontend/lib/api.ts`, iOS `APIClient`).
    The envelope is additive; nothing else may move."""
    rc = _FakeRedis()

    async def _fake_build(event_id, db):
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        served = await events_route.get_game_markets(7, _Session())

    assert set(served) - set(_body()) == {concept_cache.ENVELOPE_FIELD}
    for key, value in _body().items():
        assert served[key] == value


@pytest.mark.asyncio
async def test_the_L1_entry_and_the_served_body_are_the_same_bytes():
    """A reader served from memory and a reader served from Redis must not get
    payloads that differ in whether they disclose anything."""
    rc = _FakeRedis()

    async def _fake_build(event_id, db):
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        served = await events_route.get_game_markets(7, _Session())
        memo = await events_route.get_game_markets(7, _Session())

    assert memo == served


@pytest.mark.asyncio
async def test_a_non_json_value_survives_the_round_trip_identically():
    """The codec is `json.dumps(..., default=str)`, so a datetime comes back as
    `"2026-08-29 09:00:00+00:00"` where FastAPI's encoder writes an ISO `T`.

    Without encoding before storing, the FIRST reader of a game would get one
    shape and every subsequent reader another — in exactly the values nobody
    looks at. So the build path must serve what the cache path will serve.
    """
    rc = _FakeRedis()
    when = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    async def _fake_build(event_id, db):
        payload = _body(event_id)
        payload["totals"] = [{"market_name": "O/U 8.5", "as_of": when}]
        return payload, "live", []

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        built = await events_route.get_game_markets(7, _Session())
        events_route._game_markets_cache.clear()
        from_redis = await events_route.get_game_markets(7, _Session())

    assert built == from_redis
    assert built["totals"][0]["as_of"] == "2026-08-29T09:00:00+00:00"


@pytest.mark.asyncio
async def test_a_dead_redis_costs_a_build_and_never_a_500():
    """Every Redis helper on this path is best-effort by construction."""

    class _Dead:
        def get(self, *_a, **_k):
            raise RuntimeError("redis down")

        def setex(self, *_a, **_k):
            raise RuntimeError("redis down")

        def delete(self, *_a, **_k):
            raise RuntimeError("redis down")

    builds = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _body(event_id), "live", []

    with patch.object(gmc, "get_client", return_value=_Dead()), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        served = await events_route.get_game_markets(7, _Session())
        events_route._game_markets_cache.clear()
        await events_route.get_game_markets(7, _Session())

    assert builds == [7, 7]
    assert served["event_id"] == 7


@pytest.mark.asyncio
async def test_the_memo_eviction_bound_is_unchanged():
    """30 entries, oldest-first. Not fixed here — named in the module docstring
    as one of the three reasons the dict never hit, and left alone because the
    shared slot is what removes its importance."""
    assert events_route._GAME_MARKETS_MAX_SIZE == 30
    for i in range(events_route._GAME_MARKETS_MAX_SIZE + 5):
        events_route._write_game_markets_memo(i, "live", {"event_id": i})
    assert len(events_route._game_markets_cache) <= events_route._GAME_MARKETS_MAX_SIZE
