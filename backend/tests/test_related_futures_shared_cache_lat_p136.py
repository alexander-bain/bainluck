"""Guard tests for LAT-P136 (P127-2): the event page's Bigger Picture section
stops being rebuilt from scratch for almost every reader.

WHAT WAS MEASURED, and it is the reason these tests assert CALL COUNT rather
than wall clock. `GET /api/events/{id}/related-futures` on production
`fe5ec72c`, 2026-08-29, ten DISTINCT events taken off the live Discover feed,
first touch each, `x-timing-split` server time:

    1,441  2,924  4,255  5,488  5,572  6,210  7,426  8,619  8,736  8,807  ms
    p50 5,891 ms · max 8,807 ms · `db` 96-99 % of every one

The build is not what these tests touch. The cache is:

    _related_futures_cache: dict[int, tuple[float, str, dict]] = {}
    _RELATED_FUTURES_MAX_SIZE = 30

A process-global dict of thirty entries — the same shape LAT-P121 replaced for
`/game-markets` one door up the same file. Per PROCESS (`WEB_CONCURRENCY=2`
puts two workers on every dyno and there is more than one dyno), thirty entries
against a feed that shows dozens of games at once, and it dies with the process.
There was no shared slot and — the part that costs the wait — no mirror, so a
miss had never had anything to serve except a full rebuild.

Every assertion below is about SHAPE, TTL, CALL COUNT or which BRANCH fired.
None is about time.

🔴 THE ONE CHECK THAT IS NOT A COPY OF THE SIBLING'S is
`test_the_mirror_age_law_is_the_sibling_s_and_not_a_third_number`. This payload
carries `box_score`, `game_period` and `game_clock`, so an over-old mirror of a
LIVE game is a formatting lie arriving through a latency fix. The sibling tier
on the SAME PAGE already settled how old a mirror of a live game may be, and its
own docstring says two disagreeing ceilings in one route would be a coin flip
about which one a reader gets. That check is what stops this tier acquiring a
third opinion the next time either number is tuned — a substring test could not
see it, because the two numbers live in two files.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc
from app.utils import related_futures_cache as rfc


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
    """The shape the build returns on its FULL exit — the one that is cached."""
    return {
        "event_id": event_id,
        "home_team": "Home",
        "away_team": "Away",
        "home_team_futures": [],
        "away_team_futures": [],
        "series_markets": [],
        "total_count": 0,
        "summary": None,
        "event_status": "live",
        "box_score": [],
        "game_period": None,
        "game_clock": None,
        "league_context": None,
    }


def _empty_body(event_id: int = 7) -> dict:
    """The shape of the build's four early exits — the one that is NOT cached."""
    return {
        "event_id": event_id,
        "home_team": "Home",
        "away_team": "Away",
        "home_team_futures": [],
        "away_team_futures": [],
        "series_markets": [],
        "total_count": 0,
    }


def _stamped(status: str, *, age_s: float = 0.0, event_id: int = 7) -> dict:
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return rfc.stamp(_body(event_id), source_status=status, created_at=created)


class _Session:
    """Enough of an AsyncSession for the watermark aggregate, which is the only
    DB call the cache layer itself makes."""

    async def scalar(self, *_a, **_k):
        return None


@pytest.fixture(autouse=True)
def _clear_memo():
    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._related_futures_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


# ---------------------------------------------------------------------------
# The freshness rule is CARRIED ACROSS, not re-invented
# ---------------------------------------------------------------------------


def test_live_fresh_ttl_is_the_in_memory_tier_s_own_number():
    """The shared slot must not quietly re-base how fresh a live hit is.

    This ship changes who can see a cached copy and what a miss costs. If the
    two numbers drift, a later reader cannot tell which of those two things a
    latency delta came from.
    """
    assert rfc.FRESH_TTL_LIVE == events_route._RELATED_FUTURES_LIVE_TTL


def test_a_finished_game_s_fresh_ttl_is_finite_and_therefore_TIGHTER():
    """The dict cached finished games for the life of the PROCESS, which was
    never a decision — it is what a dict with no expiry does. Anything finite is
    strictly tighter than that, and this asserts the direction, not the value."""
    assert 0 < rfc.FRESH_TTL_FINAL < float("inf")
    assert rfc.FRESH_TTL_FINAL > rfc.FRESH_TTL_LIVE


def test_final_statuses_match_the_in_memory_tier_s_own_definition():
    """Finality must not acquire a second definition on the way into Redis."""
    for status in ("completed", "closed"):
        assert rfc.is_final(status)
        # ...and the L1 read agrees, which is the branch that has always existed.
        events_route._related_futures_cache[1] = (0.0, status, {"x": 1})
        assert events_route._read_related_futures_memo(1) == {"x": 1}
        events_route._related_futures_cache.clear()


def test_the_L1_still_expires_a_LIVE_entry_on_its_own_ttl():
    """The other half of the branch above, so the parametrisation of the L1 is
    pinned in both directions (gotcha #43)."""
    import time as _time

    events_route._related_futures_cache[1] = (
        _time.time() - (events_route._RELATED_FUTURES_LIVE_TTL + 1),
        "live",
        {"x": 1},
    )
    assert events_route._read_related_futures_memo(1) is None


@pytest.mark.parametrize(
    "status,expected",
    [
        ("completed", rfc.FRESH_TTL_FINAL),
        ("closed", rfc.FRESH_TTL_FINAL),
        ("live", rfc.FRESH_TTL_LIVE),
        ("scheduled", rfc.FRESH_TTL_LIVE),
        ("", rfc.FRESH_TTL_LIVE),
        (None, rfc.FRESH_TTL_LIVE),
    ],
)
def test_fresh_ttl_by_status(status, expected):
    assert rfc.fresh_ttl(status) == expected


def test_stale_ttl_is_the_shared_constant_not_a_copy():
    """`write_payload` does not parameterize the mirror, so a local 86400 here
    would be a number the writer never reads."""
    assert rfc.STALE_TTL is concept_cache.STALE_TTL


# ---------------------------------------------------------------------------
# 🔴 The mirror-age law belongs to the PAGE, not to this tier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["live", "scheduled", "completed", "closed", "", None, "weird"]
)
def test_the_mirror_age_law_is_the_sibling_s_and_not_a_third_number(status):
    """The event detail page has ONE mirror-age ceiling and both tiers obey it.

    This payload carries `box_score` / `game_period` / `game_clock`; the
    sibling's carries prop windows. Both age the same way on the same screen, so
    a reader must not get one answer about "how stale may this be" from the
    markets block and a different one from the Bigger Picture block. The two
    numbers live in two files, so nothing but this comparison can see a drift.
    """
    assert rfc.stale_serve_ceiling_seconds(status) == gmc.stale_serve_ceiling_seconds(
        status
    )


def test_the_fresh_ttl_is_deliberately_NOT_shared_with_the_sibling():
    """The ceiling is a page-level question — how stale may a reader's copy be.
    The fresh TTL is a tier-level one — how often does this tier rebuild. This
    tier carried 60 s across verbatim and the sibling's is 30 s, so a future
    edit that "unifies" them is changing content freshness under cover of a
    latency change."""
    assert rfc.FRESH_TTL_LIVE != gmc.FRESH_TTL_LIVE


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------


def test_stamp_publishes_all_five_contract_fields():
    payload = _stamped("live")
    envelope = payload[concept_cache.ENVELOPE_FIELD]
    for field in concept_cache.ENVELOPE_FIELDS:
        assert field in envelope, f"contract field {field} absent"
    assert envelope["generation"] == concept_cache.GENERATION
    # `availability` is the SERVE decision and is stamped on the way out.
    assert envelope["availability"] is None


def test_a_served_payload_passes_the_shared_envelope_validator():
    served = concept_cache.with_availability(
        _stamped("live"), concept_cache.AVAILABILITY_LIVE
    )
    assert concept_cache.envelope_defect(served) is None


def test_stamp_records_the_raw_status_which_the_body_cannot_supply():
    """The four `empty` exits of the build do not carry `event_status` at all,
    so the ceiling's input cannot be recovered from the body in general."""
    payload = rfc.stamp(_empty_body(), source_status="closed")
    assert rfc.source_status_of(payload) == "closed"
    assert "event_status" not in _empty_body()


def test_watermark_is_null_and_not_fabricated_when_there_are_no_markets():
    payload = _stamped("live")
    assert payload[concept_cache.ENVELOPE_FIELD]["lifecycle_watermark"] is None


# ---------------------------------------------------------------------------
# The mirror is AGE-BOUNDED, and the bound is per status
# ---------------------------------------------------------------------------


def test_a_young_live_mirror_is_servable():
    servable, reason = rfc.mirror_is_servable(_stamped("live", age_s=10))
    assert servable and reason == "fresh_enough"


def test_a_live_mirror_past_the_ceiling_is_refused():
    """A day-old mirror of a LIVE game shows a game clock from another quarter.

    That is a formatting lie arriving through a latency fix, so past the page's
    live ceiling the reader blocks and rebuilds — the pre-LAT-P136 behaviour.
    """
    over = rfc.stale_serve_ceiling_seconds("live") + 1
    servable, reason = rfc.mirror_is_servable(_stamped("live", age_s=over))
    assert not servable and reason == "too_old"


def test_a_finished_game_s_mirror_survives_far_longer():
    """Its content stops moving, so the same 24 h mirror is honest for hours."""
    under = rfc.stale_serve_ceiling_seconds("completed") - 60
    over = rfc.stale_serve_ceiling_seconds("completed") + 60
    assert rfc.mirror_is_servable(_stamped("completed", age_s=under))[0]
    assert not rfc.mirror_is_servable(_stamped("completed", age_s=over))[0]


def test_an_unknown_status_takes_the_SHORTER_ceiling():
    """The failure mode of a missing field must be a rebuild, never a stale live
    payload. If the default were `completed`, a four-hour-old mirror of a game
    in progress would be served — with its four-hour-old clock."""
    payload = _stamped("live", age_s=4 * 3600)
    del payload[concept_cache.ENVELOPE_FIELD][rfc.SOURCE_STATUS_FIELD]
    assert rfc.source_status_of(payload) == ""
    assert not rfc.mirror_is_servable(payload)[0]


def test_a_mirror_that_cannot_say_when_it_was_built_is_refused():
    payload = _stamped("live")
    payload[concept_cache.ENVELOPE_FIELD]["created_at"] = None
    servable, reason = rfc.mirror_is_servable(payload)
    assert not servable and reason == "no_created_at"


def test_mirror_is_servable_refuses_a_non_dict():
    assert rfc.mirror_is_servable("nope") == (False, "absent")


# ---------------------------------------------------------------------------
# read() / write() — the serve decision, published rather than re-derived
# ---------------------------------------------------------------------------


def test_no_redis_client_reads_as_a_miss_and_never_raises():
    with patch.object(rfc, "get_client", return_value=None):
        assert rfc.read(7) == (None, "miss")


def test_primary_hit_is_published_as_live():
    rc = _FakeRedis()
    rfc.write(7, _stamped("live"), rc=rc)
    body, state = rfc.read(7, rc=rc)
    assert state == "live"
    assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


def test_primary_absent_but_young_mirror_is_published_as_stale_ok():
    rc = _FakeRedis()
    rfc.write(7, _stamped("live", age_s=10), rc=rc)
    rc.delete(rfc.keys_for(7).primary)  # what a TTL expiry looks like
    body, state = rfc.read(7, rc=rc)
    assert state == "stale_ok"
    assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


def test_an_over_age_mirror_yields_no_body_so_the_reader_rebuilds():
    rc = _FakeRedis()
    over = rfc.stale_serve_ceiling_seconds("live") + 60
    rfc.write(7, _stamped("live", age_s=over), rc=rc)
    rc.delete(rfc.keys_for(7).primary)
    body, state = rfc.read(7, rc=rc)
    assert body is None and state == "stale_too_old"


def test_write_publishes_both_slots_with_the_status_s_own_ttls():
    rc = _FakeRedis()
    keys = rfc.keys_for(7)
    rfc.write(7, _stamped("live"), rc=rc)
    assert rc.ttls[keys.primary] == rfc.FRESH_TTL_LIVE
    assert rc.ttls[keys.stale] == rfc.STALE_TTL

    rc2 = _FakeRedis()
    rfc.write(9, _stamped("completed"), rc=rc2)
    assert rc2.ttls[rfc.keys_for(9).primary] == rfc.FRESH_TTL_FINAL


def test_the_three_tiers_do_not_share_a_redis_namespace():
    """The prefix was copied from the sibling module; a forgotten edit would
    have made the two tiers on ONE page overwrite each other's payloads under
    the same event id, and both would still have looked like a working cache."""
    assert rfc.CACHE_PREFIX != gmc.CACHE_PREFIX
    assert not rfc.CACHE_PREFIX.startswith(concept_cache.CACHE_PREFIX)
    assert rfc.keys_for(7).primary != gmc.keys_for(7).primary
    assert rfc.keys_for(7).primary != concept_cache.cache_keys("7").primary


def test_stored_bytes_are_json_and_carry_the_envelope():
    rc = _FakeRedis()
    rfc.write(7, _stamped("live"), rc=rc)
    raw = json.loads(rc.store[rfc.keys_for(7).primary].decode())
    assert raw[concept_cache.ENVELOPE_FIELD]["generation"] == concept_cache.GENERATION


# ---------------------------------------------------------------------------
# THE SHIP — the route, and how many times it builds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_reader_on_a_DIFFERENT_process_does_not_rebuild():
    """This is the ship.

    The first reader builds and publishes to the shared slot. The second reader
    is a different worker — no L1 entry — and under the old tier it paid the
    full build, measured at a p50 of 5,891 ms. It must now pay a Redis read.
    """
    rc = _FakeRedis()
    builds = []

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _body(event_id), "live", [], True

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        first = await events_route.get_related_futures(7, False, _Session())
        assert builds == [7]

        # A different worker: same Redis, empty in-process dict.
        events_route._related_futures_cache.clear()
        second = await events_route.get_related_futures(7, False, _Session())

    assert builds == [7], "the second reader rebuilt — the shared slot did nothing"
    assert second["event_id"] == first["event_id"]
    assert second[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_a_primary_expiry_serves_the_mirror_and_schedules_ONE_rebuild():
    """A miss must cost a Redis read, not a build — and a burst behind one
    expiry must produce one rebuild, not one per reader."""
    rc = _FakeRedis()
    builds = []
    scheduled = []

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _body(event_id), "live", [], True

    def _fake_refresh(name, rebuild):
        scheduled.append(name)
        return True

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        await events_route.get_related_futures(7, False, _Session())
        rc.delete(rfc.keys_for(7).primary)  # the fresh TTL expires
        events_route._related_futures_cache.clear()

        served = await events_route.get_related_futures(7, False, _Session())
        events_route._related_futures_cache.clear()
        await events_route.get_related_futures(7, False, _Session())

    assert builds == [7], "a reader behind the mirror rebuilt synchronously"
    assert scheduled == ["related_futures:7", "related_futures:7"]
    assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


@pytest.mark.asyncio
async def test_no_running_loop_to_refresh_behind_us_means_BUILD_not_stale():
    """`_serve_stale_and_refresh` returns False when nothing can run behind the
    caller. Serving stale then would serve it forever, so the reader builds."""
    rc = _FakeRedis()
    builds = []

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _body(event_id), "live", [], True

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", lambda *_: False):
        await events_route.get_related_futures(7, False, _Session())
        rc.delete(rfc.keys_for(7).primary)
        events_route._related_futures_cache.clear()
        await events_route.get_related_futures(7, False, _Session())

    assert builds == [7, 7]


@pytest.mark.asyncio
async def test_debug_bypasses_the_cache_in_BOTH_directions():
    """`debug=1` adds a `_debug` block. It never read the cache before this ship
    and it must never WRITE one either — publishing it would serve internals to
    every normal reader of that event for a TTL (LAT-P050 / LAT-P054's rule)."""
    rc = _FakeRedis()
    builds = []

    async def _fake_build(event_id, db, debug=False):
        builds.append(debug)
        body = _body(event_id)
        if debug:
            body["_debug"] = {"season_market_count": 1}
        return body, "live", [], True

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        # A warm cache exists...
        await events_route.get_related_futures(7, False, _Session())
        assert rc.store, "the non-debug reader did not publish"
        # ...and the debug reader ignores it and rebuilds.
        out = await events_route.get_related_futures(7, True, _Session())

    assert builds == [False, True]
    assert "_debug" in out
    stored = json.loads(rc.store[rfc.keys_for(7).primary].decode())
    assert "_debug" not in stored, "a debug payload was published to the shared slot"


@pytest.mark.asyncio
async def test_an_EMPTY_build_is_returned_but_never_published():
    """The four `return empty` exits have never been cached, and this ship does
    not change WHAT is cached — only where. Publishing them would make an event
    whose futures have not been ingested yet answer "no futures" for a TTL after
    they appear: a content change smuggled inside a latency change."""
    rc = _FakeRedis()

    async def _fake_build(event_id, db, debug=False):
        return _empty_body(event_id), "scheduled", [], False

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        out = await events_route.get_related_futures(7, False, _Session())

    assert out == _empty_body(7)
    assert rc.store == {}, "an empty answer was published to the shared slot"
    assert events_route._related_futures_cache == {}


@pytest.mark.asyncio
async def test_a_refresh_that_comes_back_EMPTY_leaves_the_mirror_ALONE():
    """A rebuild behind a stale serve that now returns `empty` must not
    overwrite a real answer with nothing. Same rule as a FAILED rebuild: degrade
    to slow, never to wrong."""
    rc = _FakeRedis()
    rfc.write(7, _stamped("live"), rc=rc)
    before = dict(rc.store)

    async def _fake_build(event_id, db, debug=False):
        return _empty_body(event_id), "scheduled", [], False

    class _Maker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_a):
            return False

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch("app.services.database.async_session_maker", _Maker()):
        await events_route._rebuild_related_futures(7)

    assert rc.store == before


def test_the_BUILD_hands_back_all_three_market_id_lists():
    """🔴 An AST check, not a call, and not a substring test either.

    The claim "the watermark's input set is every market this payload was
    assembled from" lives in one line of `_build_related_futures` — and that
    line is ~900 lines into a function no unit test can execute, because
    reaching it needs a real database. The mutation battery's M6 (return only
    `season_market_ids`) SURVIVED every behavioural test in this file for
    exactly that reason: they all patch the build.

    So this reads the function's own final `return` out of the AST and asserts
    which names it hands over. A substring test would pass on the three names
    appearing anywhere in the body — they appear in the `_debug` block eight
    lines above — and a comment-stripped grep would still pass if they were
    concatenated in the wrong argument position.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(events_route._build_related_futures)))
    fn = tree.body[0]
    # `fn.body[-1]`, NOT `ast.walk(...)[-1]`: walk is unordered AND descends into
    # the build's several nested helpers, so "the last Return it yields" is an
    # arbitrary one of theirs. The function's own final statement is the exit.
    final = fn.body[-1]
    assert isinstance(final, ast.Return), "the build no longer ends in a return"
    assert isinstance(final.value, ast.Tuple), "the build's final exit is not the 4-tuple"
    assert len(final.value.elts) == 4, "the build's contract is (resp, status, ids, cacheable)"

    market_ids_expr = final.value.elts[2]
    names = {n.id for n in ast.walk(market_ids_expr) if isinstance(n, ast.Name)}
    assert names == {
        "season_market_ids",
        "game_prop_ids",
        "series_market_ids",
    }, f"the watermark's input set is {sorted(names)}, not all three lists"

    # And the fourth element is the literal True — an `empty` exit that reached
    # here would be published, which is the thing `cacheable` exists to prevent.
    assert isinstance(final.value.elts[3], ast.Constant)
    assert final.value.elts[3].value is True


@pytest.mark.asyncio
async def test_the_watermark_is_taken_over_ALL_THREE_market_id_lists():
    """`season_market_ids + game_prop_ids + series_market_ids`. Series markets
    are assembled through a separate top-level array, so a watermark that
    forgot them would under-report how current the payload is on exactly the
    markets the matchup block is made of."""
    rc = _FakeRedis()
    seen = []

    async def _fake_build(event_id, db, debug=False):
        return _body(event_id), "live", [11, 22, 33], True

    async def _fake_watermark(db, market_ids):
        seen.append(list(market_ids))
        return None

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(rfc, "compute_watermark", _fake_watermark):
        await events_route.get_related_futures(7, False, _Session())

    assert seen == [[11, 22, 33]]


@pytest.mark.asyncio
async def test_what_a_build_serves_and_what_redis_serves_are_the_SAME_BYTES():
    """The tier's codec is `json.dumps(payload, default=str)`, so anything not
    natively JSON comes back as `str(value)`. Encoding on the way in makes the
    round trip lossless: the first reader and the hundredth get one dict."""
    rc = _FakeRedis()
    when = datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc)

    async def _fake_build(event_id, db, debug=False):
        body = _body(event_id)
        body["league_context"] = {"as_of": when}
        return body, "live", [], True

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        from_build = await events_route.get_related_futures(7, False, _Session())
        events_route._related_futures_cache.clear()
        from_redis = await events_route.get_related_futures(7, False, _Session())

    assert from_build["league_context"] == from_redis["league_context"]
    assert isinstance(from_build["league_context"]["as_of"], str)


@pytest.mark.asyncio
async def test_a_dead_redis_degrades_to_the_old_behaviour_and_never_500s():
    """No client at all: every reader builds, exactly as before this ship. A
    cache that cannot be reached must cost a rebuild, not an error."""
    builds = []

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _body(event_id), "live", [], True

    with patch.object(rfc, "get_client", return_value=None), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        out = await events_route.get_related_futures(7, False, _Session())
        events_route._related_futures_cache.clear()
        await events_route.get_related_futures(7, False, _Session())

    assert builds == [7, 7]
    assert out["event_id"] == 7
