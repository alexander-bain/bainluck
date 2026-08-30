"""Guard tests for LAT-P144 (P136-1 / P143-2): the event page's Bigger Picture
stops re-deriving the whole sport's market list on every single load.

WHAT WAS MEASURED, and it is why these tests assert CALL COUNT and KEY SHAPE
rather than wall clock. Production `pg_stat_statements`, 2026-08-30, the
`_tier_query` in `_build_related_futures`:

    8 fingerprints · 2,245 calls · mean 1,061 ms · max 30,773 ms · 2,381 s total

`EXPLAIN (ANALYZE, BUFFERS)` on production, baseball:

    live/upcoming event   Bitmap Heap Scan   31,497 blocks   ~1,000 ms  ->  96 rows
    finished event        Parallel Seq Scan 126,177 blocks    3,413 ms  -> 400 rows

LAT-P136 cached this tier's PAYLOAD and said in its own docstring that the build
was not made faster, parking "which of the 14-16 queries dominates" as P136-1.
It is this one, and it does not depend on the event — every input derives from
the sport key or from `event_is_finished`. The rationale, the collation
measurement that rules out an index, and the twelve-sport check that rules out
deleting the expensive arms all live in
`app/utils/season_market_discovery.py`.

🔴 THE CHECK THAT IS NOT A RESTATEMENT OF THE CODE is
`test_a_second_event_in_the_same_sport_does_not_re_run_the_discovery_query`.
It drives the real `_build_related_futures` against a fake session that RECORDS
every statement, so it fails if the cache is read but the query runs anyway —
which is what a `read()` whose result is dropped on the floor would look like,
and what no substring or AST assertion could see. Its sibling
`..._a_different_sport_does` is what stops the whole thing passing by never
querying at all.

The empty-vs-missing distinction (gotcha #53) gets its own three checks: an
empty discovery is a real, cacheable ANSWER, and it must not read back as a
MISS — otherwise the sport that costs the most (a boxing event measured 7.03 s
to return 511 bytes) is exactly the one that never gets a hit.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import season_market_discovery as smd


class _FakeRedis:
    """In-memory Redis: get / setex over a dict, with the TTLs recorded."""

    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v
        return True


class _Boom:
    """A client whose every operation raises — the 'Redis is sick' case."""

    def get(self, k):
        raise RuntimeError("redis down")

    def setex(self, k, ttl, v):
        raise RuntimeError("redis down")


# ---------------------------------------------------------------------------
# The key
# ---------------------------------------------------------------------------


def test_the_key_is_the_sport_and_nothing_about_the_event():
    """Two different events in one sport must land on ONE key.

    This is the whole premise of the ship: if the key carried anything
    event-shaped, every reader would still be the first reader.
    """
    a = smd.cache_key("baseball_mlb", False)
    b = smd.cache_key("baseball_mlb", False)
    assert a == b
    assert "baseball_mlb" in a


def test_finished_and_live_are_different_keys():
    """They select different SQL — a wider status set plus a 90-day recency
    bound — so sharing a key would serve one shape's answer for the other."""
    assert smd.cache_key("baseball_mlb", True) != smd.cache_key("baseball_mlb", False)


def test_different_sports_are_different_keys():
    assert smd.cache_key("baseball_mlb", False) != smd.cache_key("basketball_nba", False)


def test_the_key_is_namespaced_and_generation_marked():
    """A stored shape change must be able to invalidate by bumping, not by
    teaching the reader two shapes."""
    key = smd.cache_key("soccer_epl", False)
    assert key.startswith(smd.CACHE_PREFIX)
    assert ":v1:" in smd.CACHE_PREFIX


# ---------------------------------------------------------------------------
# decode — an empty answer is an ANSWER, everything malformed is a MISS
# ---------------------------------------------------------------------------


def test_an_empty_list_decodes_to_an_empty_list_not_to_none():
    """🔴 The gotcha #53 check. `[]` means 'this sport genuinely has none' and
    must suppress the rebuild; `None` means 'we do not know' and must not."""
    assert smd.decode("[]") == []
    assert smd.decode("[]") is not None


def test_a_populated_list_round_trips():
    assert smd.decode("[1, 2, 3]") == [1, 2, 3]


def test_bytes_are_decoded():
    assert smd.decode(b"[4, 5]") == [4, 5]


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not json",
        "{}",
        '{"ids": [1]}',
        "[1, \"2\"]",
        "[1, null]",
        "[[1]]",
        "3",
    ],
)
def test_anything_that_is_not_a_list_of_ints_reads_as_a_miss(raw):
    assert smd.decode(raw) is None


def test_a_boolean_is_not_an_int_here():
    """`True` is an `int` in Python and would silently become market id 1.

    Left unguarded this is a content bug wearing a cache bug's clothes: the
    Bigger Picture would show whatever market happens to have id 1.
    """
    assert smd.decode("[true]") is None
    assert smd.decode("[1, false]") is None


def test_undecodable_bytes_read_as_a_miss():
    assert smd.decode(b"\xff\xfe") is None


# ---------------------------------------------------------------------------
# TTL — the empty answer gets the SHORTER one
# ---------------------------------------------------------------------------


def test_an_empty_discovery_expires_sooner_than_a_populated_one():
    """So a sport recovers within a minute of its markets being ingested,
    instead of showing an empty Bigger Picture for the full found-TTL."""
    assert smd.ttl_for([]) == smd.TTL_EMPTY
    assert smd.ttl_for([1]) == smd.TTL_FOUND
    assert smd.TTL_EMPTY < smd.TTL_FOUND


def test_the_write_applies_the_ttl_the_answer_earns():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [1, 2], rc=rc)
    smd.write("boxing_boxing", False, [], rc=rc)
    assert rc.ttls[smd.cache_key("baseball_mlb", False)] == smd.TTL_FOUND
    assert rc.ttls[smd.cache_key("boxing_boxing", False)] == smd.TTL_EMPTY


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


def test_write_then_read_round_trips_the_ids():
    # `write` publishes to Redis, so the call stays OUT of the assert: `-O`
    # strips assertions and would take the publication with them, leaving the
    # read below with nothing to find. Assert the returned flag instead.
    rc = _FakeRedis()
    wrote = smd.write("baseball_mlb", False, [7, 8, 9], rc=rc)
    assert wrote is True
    assert smd.read("baseball_mlb", False, rc=rc) == [7, 8, 9]


def test_write_then_read_round_trips_an_EMPTY_answer():
    """The case the whole two-TTL split exists for."""
    rc = _FakeRedis()
    smd.write("boxing_boxing", False, [], rc=rc)
    assert smd.read("boxing_boxing", False, rc=rc) == []


def test_a_read_for_the_other_shape_is_a_miss():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [7], rc=rc)
    assert smd.read("baseball_mlb", True, rc=rc) is None


def test_no_redis_at_all_is_a_miss_and_not_a_crash():
    """No client configured — every request runs the query, as before."""
    with patch.object(smd, "_client", lambda: None):
        assert smd.read("baseball_mlb", False) is None
        wrote = smd.write("baseball_mlb", False, [1])
        assert wrote is False


def test_a_sick_redis_costs_a_rebuild_never_a_500():
    """Both directions. A cache that cannot be reached must degrade to the
    behaviour that existed before it, which is 'run the query'."""
    rc = _Boom()
    assert smd.read("baseball_mlb", False, rc=rc) is None
    wrote = smd.write("baseball_mlb", False, [1], rc=rc)
    assert wrote is False


def test_write_reports_attempted_not_durable():
    """`write` returning True means 'there was a client and we handed it the
    bytes'. Only the next read can establish that Redis has them."""
    rc = _FakeRedis()
    wrote = smd.write("baseball_mlb", False, [1], rc=rc)
    assert wrote is True
    assert smd.read("baseball_mlb", False, rc=rc) == [1]


def test_the_stored_encoding_is_a_plain_json_list():
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [3, 1, 2], rc=rc)
    raw = rc.store[smd.cache_key("baseball_mlb", False)]
    assert json.loads(raw.decode()) == [3, 1, 2]


def test_the_stored_order_is_preserved():
    """The tier cap downstream is positional — `ORDER BY market_tier, id` then
    'first 100 of each tier' — so a re-ordered list is a different answer."""
    rc = _FakeRedis()
    smd.write("baseball_mlb", False, [9, 4, 7], rc=rc)
    assert smd.read("baseball_mlb", False, rc=rc) == [9, 4, 7]


# ---------------------------------------------------------------------------
# The route — driving the real build against a recording session
# ---------------------------------------------------------------------------


_NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


class _Result:
    """Just enough of a SQLAlchemy Result for the path under test."""

    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """A fake `AsyncSession` that records the compiled SQL of every statement.

    It answers the four queries on the short path through
    `_build_related_futures`: load event, resolve compatible sports, discover
    season markets, load this event's game props. With no team names on the
    event the series pass is skipped, and with no markets found the build takes
    its `empty` exit immediately after — so the statement log is exactly the
    part of the build this queue changes.
    """

    def __init__(self, event, tier_rows):
        self.event = event
        self.tier_rows = tier_rows
        self.statements: list[str] = []

    async def execute(self, stmt):
        sql = str(stmt)
        self.statements.append(sql)
        if "FROM events" in sql:
            return _Result(scalar=self.event)
        if "FROM sports" in sql:
            return _Result(rows=[SimpleNamespace(id=7)])
        if "futures_markets.market_tier" in sql and "SELECT futures_markets.id" in sql:
            return _Result(rows=self.tier_rows)
        return _Result(rows=[])

    @property
    def discovery_calls(self) -> int:
        return sum(
            1
            for s in self.statements
            if s.startswith("SELECT futures_markets.id, futures_markets.market_tier")
        )


def _event(sport_key: str, status: str = "scheduled"):
    return SimpleNamespace(
        id=101,
        sport=SimpleNamespace(id=7, key=sport_key),
        sport_id=7,
        status=status,
        # No team names: the series pass needs both, so the build skips it and
        # takes its `empty` exit right after the part under test.
        home_team_name=None,
        away_team_name=None,
        commence_time=_NOW + timedelta(hours=3),
    )


def _tier_rows():
    return [
        SimpleNamespace(id=11, market_tier=1),
        SimpleNamespace(id=12, market_tier=2),
    ]


async def _build(session, debug=False):
    return await events_route._build_related_futures(
        session.event.id, session, debug=debug
    )


@pytest.mark.asyncio
async def test_a_second_event_in_the_same_sport_does_not_re_run_the_discovery_query():
    """🔴 The load-bearing check. Two different events, one sport, one query.

    Drives the real build, so it fails if the cache is read and its result
    then dropped — the shape an AST or substring guard cannot see.
    """
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        first = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(first)
        assert first.discovery_calls == 1, "the first reader must pay for it"

        second = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        second.event.id = 202
        await _build(second)
        assert second.discovery_calls == 0, (
            "the second event in the same sport re-ran the sport-wide query"
        )


@pytest.mark.asyncio
async def test_but_a_different_sport_does_re_run_it():
    """The other direction, which is what stops the check above passing
    because the query was simply never issued."""
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        await _build(_RecordingSession(_event("baseball_mlb"), _tier_rows()))
        other = _RecordingSession(_event("basketball_nba"), _tier_rows())
        await _build(other)
        assert other.discovery_calls == 1


@pytest.mark.asyncio
async def test_a_finished_event_does_not_serve_a_live_event_s_discovery():
    """`event_is_finished` selects a wider status set and a 90-day recency
    bound, so it is a different answer and must not share the slot."""
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        await _build(_RecordingSession(_event("baseball_mlb"), _tier_rows()))
        finished = _RecordingSession(
            _event("baseball_mlb", status="completed"), _tier_rows()
        )
        finished.event.commence_time = _NOW - timedelta(hours=4)
        await _build(finished)
        assert finished.discovery_calls == 1


@pytest.mark.asyncio
async def test_two_finished_events_in_one_sport_share_a_slot_of_their_own():
    """The other half of the finishedness split, and it is not symmetric with
    the read.

    🔴 THIS CHECK EXISTS BECAUSE ITS MUTANT SURVIVED. A write that drops
    `event_is_finished` and always publishes to the LIVE slot is invisible to a
    test that only ever asks whether the finished build MISSED — it does miss,
    every time, which is precisely the bug. It only becomes visible when a
    second finished event is expected to HIT.
    """
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        first = _RecordingSession(
            _event("baseball_mlb", status="completed"), _tier_rows()
        )
        first.event.commence_time = _NOW - timedelta(hours=4)
        await _build(first)
        assert first.discovery_calls == 1

        second = _RecordingSession(
            _event("baseball_mlb", status="completed"), _tier_rows()
        )
        second.event.id = 303
        second.event.commence_time = _NOW - timedelta(hours=4)
        await _build(second)
        assert second.discovery_calls == 0, (
            "the second finished event re-ran the sport-wide query"
        )

    # And it must have landed in the finished slot, not the live one.
    assert smd.read("baseball_mlb", True, rc=rc) == [11, 12]
    assert smd.read("baseball_mlb", False, rc=rc) is None


@pytest.mark.asyncio
async def test_an_empty_discovery_is_cached_too():
    """The sport that costs the most is the one with nothing to find — a
    boxing event measured 7.03 s to return 511 bytes. If `[]` read back as a
    miss it would never get a hit."""
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        first = _RecordingSession(_event("boxing_boxing"), [])
        await _build(first)
        assert first.discovery_calls == 1
        second = _RecordingSession(_event("boxing_boxing"), [])
        await _build(second)
        assert second.discovery_calls == 0


@pytest.mark.asyncio
async def test_debug_bypasses_the_cache_in_both_directions():
    """A debug request must see the uncached truth, and must never publish it.

    Same rule the cache ladder at the top of this route already follows: the
    debug body carries a `_debug` block that must not reach a normal reader.
    """
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        # A debug build must not READ a warm slot...
        smd.write("baseball_mlb", False, [999], rc=rc)
        dbg = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(dbg, debug=True)
        assert dbg.discovery_calls == 1, "debug served a cached discovery"

        # ...and must not WRITE one either.
        rc.store.clear()
        rc.ttls.clear()
        dbg2 = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(dbg2, debug=True)
        assert rc.store == {}, "debug published its uncached read to the cache"


@pytest.mark.asyncio
async def test_the_cached_ids_are_the_tier_capped_ones_not_the_raw_rows():
    """What is stored is the post-cap list the build actually uses, so a hit
    and a miss produce the same downstream input."""
    rc = _FakeRedis()
    with patch.object(smd, "_client", lambda: rc):
        await _build(_RecordingSession(_event("baseball_mlb"), _tier_rows()))
        assert smd.read("baseball_mlb", False, rc=rc) == [11, 12]


@pytest.mark.asyncio
async def test_the_per_tier_cap_still_applies_and_is_what_gets_stored():
    """101 tier-1 rows must store 100 ids — the cap is upstream of the cache,
    so caching must not smuggle an extra market onto the page."""
    rc = _FakeRedis()
    rows = [SimpleNamespace(id=i, market_tier=1) for i in range(101)]
    with patch.object(smd, "_client", lambda: rc):
        await _build(_RecordingSession(_event("baseball_mlb"), rows))
        stored = smd.read("baseball_mlb", False, rc=rc)
    assert len(stored) == 100
    assert stored == list(range(100))


@pytest.mark.asyncio
async def test_a_dead_cache_leaves_the_route_working():
    """Every request runs the query, exactly as before this ship. The failure
    mode of this cache is slow, never wrong and never a 500."""
    with patch.object(smd, "_client", lambda: _Boom()):
        a = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(a)
        b = _RecordingSession(_event("baseball_mlb"), _tier_rows())
        await _build(b)
        assert a.discovery_calls == 1
        assert b.discovery_calls == 1
