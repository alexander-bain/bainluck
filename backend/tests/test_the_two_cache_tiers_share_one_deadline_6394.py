"""L1 AND L2 STOP RUNNING TWO BOUNDS IN SERIES. #6394.

═══ WHAT WAS MEASURED ═══

Found by latency/425 paying #6355's after-check, production 2026-09-15. Four of
four completed controls on `/api/events/{id}/game-markets` were serving a payload
built at 16:02:54Z when read at 17:04:44Z — **age 3,710 s, under a 3,600 s
bound.** Nothing was broken in either tier; they were each doing their job, one
after the other:

| tier | what it bounds | from when |
|---|---|---|
| L2 (Redis primary) | `FRESH_TTL_FINAL` = 3600 s | the payload's own `created_at`, via the slot's TTL |
| L1 (process dict) | `FRESH_TTL_FINAL` = 3600 s | ← **when this process READ it** |

So a body handed over by L2 as `live` at 3,599 s — one second inside the bound —
was stamped into L1 with a brand-new clock and served for another full hour. The
two windows COMPOSE to ~2x the number both tiers believe they are enforcing, and
the worst case is not the average case: it is exactly the payload that was most
nearly expired when somebody happened to read it.

═══ WHY #6355's TESTS DID NOT CATCH IT ═══

🔴 **Every test in the battery exercises ONE TIER AT A TIME.** #6355 shipped with
197 passing tests and 19/19 mutants killed, and not one of them ever asked what
the two bounds do when a payload passes through BOTH. `TestTheFinalEntryNoLongerPins`
hand-builds an L1 entry with `time.time() - N`; the shared-cache battery reads L2
and asserts call counts. Each is right about its own tier. The defect lives in the
seam, so it survived both.

That is the lesson this file is written to hold, and it is why
`TestTheSeamItself` drives the real route with a real (fake-backed) L2 instead of
asserting on `_memo_stamp` alone. A unit test of the helper would have passed on
the pre-fix code too if the helper had existed.

═══ WHAT THIS IS NOT ═══

Not #6355 again. `build_id` refuses a payload the RELEASE invalidated, at ANY
age, and is untouched here — the two checks are independent and both still run.
This one covers the payload that nothing invalidated except the clock.

═══ WHAT MUST NOT CHANGE ═══

* The fall-backs stay in the direction of today's behaviour. A payload with no
  parseable `created_at` is still MEMOISED (unlike L2's mirror, which refuses
  one) — the wall-clock bound still applies to it, so refusing here would buy a
  latency regression and no truth.
* A `created_at` in the future can only ever SHORTEN an entry's life. That is the
  one direction this fix exists to close, so skew must not reopen it.
* A freshly built payload is unaffected: it gets the full TTL, because its
  `created_at` IS now. This is a cache and it must still cache.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import app.routes.events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc


@pytest.fixture(autouse=True)
def _clean_l1():
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


def _body(event_id: int = 7) -> dict:
    return {"event_id": event_id, "spreads": [1], "totals": [], "other": []}


def _aged(age_s: float, *, status: str = "completed", event_id: int = 7) -> dict:
    """A stamped payload that says it was built `age_s` seconds ago."""
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return gmc.stamp(_body(event_id), source_status=status, created_at=created)


def _remaining_life(event_id: int, ttl: float) -> float:
    """Seconds until L1 will start missing on this entry."""
    stamped_ts = events_route._game_markets_cache[event_id][0]
    return ttl - (time.time() - stamped_ts)


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


class _Session:
    """Enough of an AsyncSession for the watermark aggregate."""

    async def scalar(self, *_a, **_k):
        return None


# ---------------------------------------------------------------------------
# 1. The bound is measured from the BUILD, not from the read.
# ---------------------------------------------------------------------------


class TestL1CountsFromWhenThePayloadWasBuilt:
    def test_a_body_already_past_the_bound_is_not_given_a_fresh_hour(self):
        """🔴 THE DEFECT, at its crispest.

        Pre-fix this is a HIT: the writer stamped `time.time()`, so a payload
        that was already too old to serve became the freshest entry in the tier.
        """
        events_route._write_game_markets_memo(
            7, "completed", _aged(gmc.FRESH_TTL_FINAL + 1)
        )
        assert events_route._read_game_markets_memo(7) is None

    def test_a_body_inside_the_bound_is_still_served(self):
        """The reverse direction: this is a cache, and it must still cache.

        Deliberately older than the LIVE ttl, so this fails if finality stops
        selecting the longer bound and everything collapses to 30 s.
        """
        body = _aged(events_route._GAME_MARKETS_LIVE_TTL + 5)
        events_route._write_game_markets_memo(7, "completed", body)
        assert events_route._read_game_markets_memo(7) == body

    def test_the_remaining_life_is_the_payloads_remaining_life(self):
        """The measurement, not just the verdict.

        A payload 60 s short of the bound must have ~60 s of L1 left — not 3,600.
        Pre-fix the second assertion reads ~3,600 and this is the line that says
        by how much the tier was over.
        """
        events_route._write_game_markets_memo(
            7, "completed", _aged(gmc.FRESH_TTL_FINAL - 60)
        )
        remaining = _remaining_life(7, gmc.FRESH_TTL_FINAL)
        assert 50 < remaining <= 60
        assert remaining < gmc.FRESH_TTL_FINAL / 2

    def test_a_freshly_built_payload_keeps_the_whole_ttl(self):
        """NOT VACUOUS: the fix must not shorten the ordinary path.

        A build's `created_at` IS now, so nothing is subtracted and the entry
        gets the full hour it has always had.
        """
        events_route._write_game_markets_memo(7, "completed", _aged(0))
        assert events_route._read_game_markets_memo(7) is not None
        assert _remaining_life(7, gmc.FRESH_TTL_FINAL) > gmc.FRESH_TTL_FINAL - 5

    def test_a_live_entry_still_counts_from_the_build_too(self):
        """The 30 s tier composes the same way and is fixed by the same line."""
        events_route._write_game_markets_memo(
            7, "live", _aged(events_route._GAME_MARKETS_LIVE_TTL + 1, status="live")
        )
        assert events_route._read_game_markets_memo(7) is None


# ---------------------------------------------------------------------------
# 2. The seam. This is the half a single-tier test cannot reach.
# ---------------------------------------------------------------------------


class TestTheSeamItself:
    @pytest.mark.asyncio
    async def test_an_almost_expired_L2_body_does_not_buy_another_hour_in_L1(self):
        """🔴 THE SHIP, end to end, through the real route.

        L2 hands over a body that is one minute short of its own deadline. The
        route memoises it. Pre-fix, L1 then served that same body for a further
        `FRESH_TTL_FINAL` — the 3,710 s production read in the docstring. The two
        tiers must now expire together.
        """
        rc = _FakeRedis()
        aged = _aged(gmc.FRESH_TTL_FINAL - 60)
        gmc.write(7, aged, rc=rc)

        async def _must_not_build(event_id, db):  # pragma: no cover - guard
            raise AssertionError("the route rebuilt; L2 was supposed to serve")

        with patch.object(gmc, "get_client", return_value=rc), patch.object(
            events_route, "_build_game_markets", _must_not_build
        ):
            served = await events_route.get_game_markets(7, _Session())

        assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "live"
        assert 7 in events_route._game_markets_cache, "the route did not memoise"
        assert _remaining_life(7, gmc.FRESH_TTL_FINAL) <= 60

    @pytest.mark.asyncio
    async def test_the_memoised_entry_expires_and_the_reader_returns_to_L2(self):
        """The consequence the reader actually feels.

        Not "the number is smaller" but "the next read consults the shared tier
        again". With the body past the bound, L1 must decline and the route must
        go back to L2 — which is where a corrected payload would be waiting.
        """
        rc = _FakeRedis()
        gmc.write(7, _aged(gmc.FRESH_TTL_FINAL + 5), rc=rc)
        builds = []

        async def _fake_build(event_id, db):
            builds.append(event_id)
            return _body(event_id), "completed", []

        with patch.object(gmc, "get_client", return_value=rc), patch.object(
            events_route, "_build_game_markets", _fake_build
        ):
            await events_route.get_game_markets(7, _Session())

        # Whatever the first read did, the SECOND must not be an L1 hit: the
        # entry is already past the shared deadline the moment it is written, so
        # the next reader consults the shared tier again — which is where a
        # corrected payload would be waiting.
        #
        # ⚠️ An earlier draft of this asserted `!= _aged(...)`, which can never
        # be equal (`_aged` mints a new `created_at` per call) and passed against
        # the pre-fix code. Assert the miss itself.
        assert events_route._read_game_markets_memo(7) is None


# ---------------------------------------------------------------------------
# 3. The fall-backs. Both point at today's behaviour, on purpose.
# ---------------------------------------------------------------------------


class TestTheFallbacksFailTowardsTodaysBehaviour:
    def test_a_payload_that_cannot_say_when_it_was_built_is_still_memoised(self):
        """L2's mirror REFUSES such a payload; L1 must not.

        Refusing here would stop L1 memoising anything a writer forgot to stamp
        — a latency regression with no truth benefit, because the wall-clock
        bound still applies to it exactly as it does today.
        """
        events_route._write_game_markets_memo(7, "completed", {"spreads": [1]})
        assert events_route._read_game_markets_memo(7) == {"spreads": [1]}
        assert _remaining_life(7, gmc.FRESH_TTL_FINAL) > gmc.FRESH_TTL_FINAL - 5

    def test_an_unparseable_created_at_falls_back_rather_than_raising(self):
        body = _aged(10)
        body[concept_cache.ENVELOPE_FIELD]["created_at"] = "not-a-timestamp"
        events_route._write_game_markets_memo(7, "completed", body)
        assert events_route._read_game_markets_memo(7) == body

    def test_a_created_at_in_the_future_cannot_extend_the_entry(self):
        """A writer dyno whose clock runs ahead.

        A negative age would push the stamp FORWARD and make the entry outlive
        the bound — the one direction this fix exists to close. Skew may shorten
        a life; it may never lengthen one.
        """
        events_route._write_game_markets_memo(7, "completed", _aged(-3600))
        assert _remaining_life(7, gmc.FRESH_TTL_FINAL) <= gmc.FRESH_TTL_FINAL

    def test_a_non_dict_response_does_not_raise(self):
        events_route._write_game_markets_memo(7, "completed", None)
        assert 7 in events_route._game_markets_cache


# ---------------------------------------------------------------------------
# 4. Eviction sorts on the same field, so it now drops the oldest CONTENT.
# ---------------------------------------------------------------------------


class TestEviction:
    def test_the_bound_is_unchanged(self):
        for i in range(events_route._GAME_MARKETS_MAX_SIZE + 5):
            events_route._write_game_markets_memo(i, "completed", _aged(0, event_id=i))
        assert (
            len(events_route._game_markets_cache)
            <= events_route._GAME_MARKETS_MAX_SIZE
        )

    def test_the_entry_dropped_is_the_one_holding_the_oldest_payload(self):
        """A consequence of stamping content age, asserted so it is not an accident.

        Entry 1 was WRITTEN first but holds the youngest payload; entry 2 holds
        the oldest. The tier should keep what is most likely to still be true.
        """
        events_route._game_markets_cache.clear()
        events_route._write_game_markets_memo(1, "completed", _aged(1, event_id=1))
        events_route._write_game_markets_memo(2, "completed", _aged(900, event_id=2))
        while len(events_route._game_markets_cache) < events_route._GAME_MARKETS_MAX_SIZE:
            n = 100 + len(events_route._game_markets_cache)
            events_route._write_game_markets_memo(n, "completed", _aged(0, event_id=n))

        events_route._write_game_markets_memo(999, "completed", _aged(0, event_id=999))
        assert 2 not in events_route._game_markets_cache
        assert 1 in events_route._game_markets_cache


# ---------------------------------------------------------------------------
# 5. #6355 is untouched. The two checks are independent and both still run.
# ---------------------------------------------------------------------------


class TestTheBuildCheckStillBinds:
    def test_a_young_payload_from_another_build_is_still_refused(self):
        events_route._write_game_markets_memo(7, "completed", _aged(1))
        ts, status, _build, response = events_route._game_markets_cache[7]
        events_route._game_markets_cache[7] = (ts, status, "v0000-old", response)
        assert events_route._read_game_markets_memo(7) is None

    def test_the_stored_entry_still_carries_the_running_build(self):
        events_route._write_game_markets_memo(7, "completed", _aged(1))
        assert (
            events_route._game_markets_cache[7][2] == events_route._current_build_id()
        )

    def test_the_stored_entry_still_carries_the_raw_source_status(self):
        """The status selects the TTL, so a write that loses it silently
        collapses a finished game to the 30 s live bound."""
        events_route._write_game_markets_memo(7, "completed", _aged(1))
        assert events_route._game_markets_cache[7][1] == "completed"


# ---------------------------------------------------------------------------
# 6. One helper, one clock — the same rule #6355 recorded for `build_id`.
# ---------------------------------------------------------------------------


def test_l1_ages_a_payload_with_the_same_helper_l2_bounds_its_mirror_with():
    """Two tiers computing age two ways is how #6394 happened in the first place.

    Pinned by BEHAVIOUR rather than by grepping for the call: a payload whose age
    `gmc.payload_age_seconds` puts past the bound must be one L1 declines.
    """
    body = _aged(gmc.FRESH_TTL_FINAL + 30)
    assert gmc.payload_age_seconds(body) > gmc.FRESH_TTL_FINAL
    events_route._write_game_markets_memo(7, "completed", body)
    assert events_route._read_game_markets_memo(7) is None


def test_the_stored_bytes_are_untouched_by_the_restamp():
    """The stamp is metadata about the entry, never an edit of the payload."""
    body = _aged(120)
    before = json.dumps(body, default=str, sort_keys=True)
    events_route._write_game_markets_memo(7, "completed", body)
    assert json.dumps(
        events_route._game_markets_cache[7][3], default=str, sort_keys=True
    ) == before
