"""A RELEASE STOPS DEFEATING ITS OWN CACHE CLEAR. #6355.

═══ WHAT HAPPENED, TIMESTAMPED ═══

Found by lane1b/268 paying #6312's post-release after-check, production
2026-09-15:

| time | event |
|---|---|
| 10:44:23Z | #6312 merged (`0cd0531fe`) — a settled spread market stops being dropped from `/api/events/{id}/game-markets` |
| 10:58:52Z | release **v4579** carrying it; `web.1` up 10:59:23Z, so the L1 dict is **empty** |
| ~10:59:30Z | first read. The Redis primary slot for event 15306857 is **still fresh** (written ~10:0xZ, `FRESH_TTL_FINAL = 3600`), so L2 serves the **pre-ship** body and L1 warms *from it* |
| 11:01–11:05Z | every read after: `spreads: 0`, `db=0.0`, wall 2–4 ms — L1 hits of a payload built by code that no longer exists |

The fix was in the running process. The reader was not getting it. Still true
seven minutes of polling later.

═══ THE MECHANISM: THE TWO TIERS ARE ANTI-CORRELATED WITH THE DEPLOY ═══

A release clears L1 (the process restarts) and does **nothing** to the Redis
slot. So the instant L1 is empty is exactly the instant L2 is most likely to
still hold a pre-ship body — **and L1 re-warms from it.** One dyno,
`WEB_CONCURRENCY=2`, so a handful of requests pinned both workers.

Two defects, and BOTH are needed for the pin:

1. **L1 had no age bound for a final game.** `if is_final or (now - ts) < TTL`
   returned a completed event's entry forever, so that worker never consulted
   Redis for it again and the entire L2 ladder below it — mirror, `stale_ok`,
   exactly-one-rebuild — was unreachable. The only exits were eviction (30
   *distinct other* events, oldest-first) or the process dying. **Neither is a
   clock: it could not be waited out.**
2. **Nothing in either tier knew which build produced a payload.** Age cannot
   express "built by code that no longer exists" — the body was *young*, it was
   *wrong*.

═══ THE FIX, AND THE ONE DECISION IN IT ═══

L1 now uses `gmc.FRESH_TTL_FINAL` for a final entry (the number the L2 tier
already records for the same question) and both tiers stamp and check
`build_id`.

**A slot from another build is a MISS, not a stale serve.** It is not demoted
to the mirror path, because the mirror is the same bytes from the same dead
build — serving it `stale_ok` would launder the pre-ship payload through a
second door and call it policy.

That decision was measured, not assumed. Eight cold builds on production
2026-09-15: **73 / 110 / 159 / 170 / 207 / 299 / 722 / 2013 ms** — a ~190 ms
median, not the 2.25 s this tier was built for (#1587). It is paid once per
event per release, by the small set of events whose slot is still fresh at the
moment of a deploy. Correctness now, for a median 190 ms, once.

═══ THE BOUNDARY THAT MATTERS MOST ═══

**`payload_is_current_build` FAILS OPEN when either side is unknown**, and that
is the difference between a fix and an outage:

* **stored unknown** — every payload written before this shipped, and anything a
  future writer forgets to stamp. Reading that as a mismatch would invalidate
  the whole tier the moment this ship deploys.
* **running unknown** — local dev, CI, and any Heroku app without dyno metadata
  (`current_build_id` → `UNKNOWN_BUILD`). Reading that as a mismatch would make
  **every read a miss and the cache dead**, in exactly the environments least
  able to notice. That is a latency cliff shipped under a truth fix.

`TestItFailsOpenWhenTheBuildIsUnknown` is the half that holds this, and it
matters more than the forward direction.

═══ WHAT MUST NOT CHANGE ═══

* One helper for "which deploy am I" across both tiers
  (`db_session_identity.current_build_id`). Two tiers that disagree would
  reintroduce the bug somewhere harder to see.
* `stale_build` stays its OWN read state, not folded into `miss`: "nothing was
  cached" and "something was cached and a deploy made it a lie" are different
  facts, and only the second is supposed to be rare.
* L1's final TTL stays equal to `gmc.FRESH_TTL_FINAL`. Two tiers disagreeing
  about how long a finished game's payload is good for is how this started.
"""

import time

import pytest

import app.routes.events as events_route
from app.utils import game_markets_cache as gmc
from app.utils.db_session_identity import UNKNOWN_BUILD


@pytest.fixture(autouse=True)
def _clean_l1():
    events_route._game_markets_cache.clear()
    yield
    events_route._game_markets_cache.clear()


def _stamped(build: str | None, *, status: str = "completed") -> dict:
    """A stored payload carrying `build`, or carrying no build field at all."""
    body = gmc.stamp({"spreads": []}, source_status=status)
    envelope = dict(body[gmc.ENVELOPE_FIELD])
    if build is None:
        envelope.pop(gmc.BUILD_FIELD, None)
    else:
        envelope[gmc.BUILD_FIELD] = build
    body[gmc.ENVELOPE_FIELD] = envelope
    return body


# ---------------------------------------------------------------------------
# 1. L1 — the pin itself.
# ---------------------------------------------------------------------------


class TestTheFinalEntryNoLongerPins:
    def test_a_completed_entry_older_than_the_final_ttl_is_a_miss(self):
        """🔴 The defect. This entry used to be returned forever."""
        events_route._game_markets_cache[15306857] = (
            time.time() - (gmc.FRESH_TTL_FINAL + 1),
            "completed",
            events_route._current_build_id(),
            {"spreads": []},
        )
        assert events_route._read_game_markets_memo(15306857) is None

    def test_a_completed_entry_inside_the_final_ttl_is_still_served(self):
        """The reverse direction: this is a cache, and it must still cache.

        Deliberately older than the LIVE ttl, so the test fails if finality
        stops selecting the longer bound and everything collapses to 30 s.
        """
        events_route._game_markets_cache[15306857] = (
            time.time() - (events_route._GAME_MARKETS_LIVE_TTL + 5),
            "completed",
            events_route._current_build_id(),
            {"spreads": [1]},
        )
        assert events_route._read_game_markets_memo(15306857) == {"spreads": [1]}

    def test_l1s_final_bound_is_the_l2_tiers_own_number(self):
        """Not a new constant. Two tiers disagreeing is how this started."""
        fresh = time.time() - (gmc.FRESH_TTL_FINAL - 5)
        stale = time.time() - (gmc.FRESH_TTL_FINAL + 5)
        for ts, expected in ((fresh, {"spreads": [1]}), (stale, None)):
            events_route._game_markets_cache[1] = (
                ts,
                "completed",
                events_route._current_build_id(),
                {"spreads": [1]},
            )
            assert events_route._read_game_markets_memo(1) == expected

    def test_a_live_entry_keeps_its_thirty_seconds(self):
        """Untouched by this ship, asserted so the bound is not widened by it."""
        events_route._game_markets_cache[1] = (
            time.time() - (events_route._GAME_MARKETS_LIVE_TTL + 1),
            "live",
            events_route._current_build_id(),
            {"spreads": [1]},
        )
        assert events_route._read_game_markets_memo(1) is None

    def test_a_round_trip_through_the_writer_is_served(self):
        """NOT VACUOUS: the writer and reader agree on the tuple shape.

        Every assertion above hand-builds the entry, so all of them would still
        pass if the writer wrote something the reader could never match.
        """
        events_route._write_game_markets_memo(15306857, "completed", {"spreads": [1]})
        assert events_route._read_game_markets_memo(15306857) == {"spreads": [1]}


class TestL1RefusesAnotherBuild:
    def test_an_entry_from_another_build_is_a_miss(self):
        events_route._game_markets_cache[15306857] = (
            time.time(),
            "completed",
            "v4578-old",
            {"spreads": []},
        )
        assert events_route._read_game_markets_memo(15306857) is None

    def test_the_same_build_is_served(self):
        events_route._game_markets_cache[15306857] = (
            time.time(),
            "completed",
            events_route._current_build_id(),
            {"spreads": [1]},
        )
        assert events_route._read_game_markets_memo(15306857) == {"spreads": [1]}


# ---------------------------------------------------------------------------
# 2. L2 — the slot that survived the release.
# ---------------------------------------------------------------------------


class TestTheStoredPayloadNamesItsBuild:
    def test_stamp_records_the_running_build(self):
        assert gmc.build_id_of(gmc.stamp({}, source_status="completed")) == (
            gmc.current_build_id()
        )

    def test_build_id_of_is_empty_for_shapes_that_cannot_carry_one(self):
        assert gmc.build_id_of(None) == ""
        assert gmc.build_id_of({}) == ""
        assert gmc.build_id_of({gmc.ENVELOPE_FIELD: "not-a-dict"}) == ""


class TestAPayloadFromAnotherBuildIsRefused:
    def test_a_different_build_is_not_current(self, monkeypatch):
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        assert gmc.payload_is_current_build(_stamped("v4578")) is False

    def test_the_same_build_is_current(self, monkeypatch):
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        assert gmc.payload_is_current_build(_stamped("v4579")) is True

    def test_read_refuses_a_fresh_primary_slot_from_another_build(self, monkeypatch):
        """🔴 THE PRODUCTION SPECIMEN: young, and built by code that is gone.

        Event 15306857's slot was ~50 min old against a 3600 s TTL, so every
        age-based check in the tier called it fresh — and it was, and it was
        also wrong.
        """
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        monkeypatch.setattr(gmc, "get_client", object)  # any non-None client
        monkeypatch.setattr(
            gmc, "read_slot", lambda client, key: _stamped("v4578-preship")
        )

        body, state = gmc.read(15306857)
        assert state == "stale_build"
        assert body is None

    def test_the_mirror_is_refused_too_and_not_used_as_a_second_door(self, monkeypatch):
        """The mirror is the same bytes from the same dead build.

        If only the primary were checked, a mismatch would fall through to the
        mirror, pass `mirror_is_servable` on age, and be served `stale_ok` — the
        pre-ship payload delivered anyway, now wearing an availability label.
        """
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        monkeypatch.setattr(gmc, "get_client", object)  # any non-None client

        keys = gmc.keys_for(15306857)
        monkeypatch.setattr(
            gmc,
            "read_slot",
            lambda client, key: (
                None if key == keys.primary else _stamped("v4578-preship")
            ),
        )

        body, state = gmc.read(15306857)
        assert state == "stale_build"
        assert body is None

    def test_a_current_build_slot_is_still_served_live(self, monkeypatch):
        """The reverse direction. This is a cache and it must still cache."""
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        monkeypatch.setattr(gmc, "get_client", object)  # any non-None client
        monkeypatch.setattr(gmc, "read_slot", lambda client, key: _stamped("v4579"))

        body, state = gmc.read(15306857)
        assert state == "live"
        assert body is not None


# ---------------------------------------------------------------------------
# 3. 🔴 THE HALF THAT MATTERS MOST. Fail open, or the cache dies everywhere.
# ---------------------------------------------------------------------------


class TestItFailsOpenWhenTheBuildIsUnknown:
    def test_a_payload_written_before_this_ship_is_served(self, monkeypatch):
        """No build field at all — every slot in Redis at deploy time.

        Refusing these would invalidate the entire tier at the moment this
        lands, which is a self-inflicted herd on a north-star page.
        """
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        assert gmc.payload_is_current_build(_stamped(None)) is True

    def test_an_unknown_RUNNING_build_serves_everything(self, monkeypatch):
        """Local dev, CI, and any app without dyno metadata.

        This is the branch that would silently disable the cache in every
        environment that cannot measure the difference.
        """
        monkeypatch.setattr(gmc, "current_build_id", lambda: UNKNOWN_BUILD)
        assert gmc.payload_is_current_build(_stamped("v4578")) is True

    def test_an_unknown_STORED_build_serves(self, monkeypatch):
        monkeypatch.setattr(gmc, "current_build_id", lambda: "v4579")
        assert gmc.payload_is_current_build(_stamped(UNKNOWN_BUILD)) is True

    def test_read_still_serves_live_when_the_running_build_is_unknown(
        self, monkeypatch
    ):
        """End to end, because the predicate passing is not the cache working."""
        monkeypatch.setattr(gmc, "current_build_id", lambda: UNKNOWN_BUILD)
        monkeypatch.setattr(gmc, "get_client", object)  # any non-None client
        monkeypatch.setattr(gmc, "read_slot", lambda client, key: _stamped("v4578"))

        body, state = gmc.read(15306857)
        assert state == "live"
        assert body is not None

    def test_l1_serves_an_entry_when_the_build_is_unknown_on_both_sides(
        self, monkeypatch
    ):
        """The L1 twin of the same guard.

        L1 compares the stamp it wrote against the stamp it reads, so when the
        platform sets nothing both sides are `UNKNOWN_BUILD` and they match —
        which is the fail-open, reached by equality rather than by a special
        case. Asserted so a future "tighten this" cannot make L1 dead locally
        while L2 stays correct.
        """
        monkeypatch.setattr(events_route, "_current_build_id", lambda: UNKNOWN_BUILD)
        events_route._write_game_markets_memo(1, "completed", {"spreads": [1]})
        assert events_route._read_game_markets_memo(1) == {"spreads": [1]}


# ---------------------------------------------------------------------------
# 4. One definition of "which deploy am I".
# ---------------------------------------------------------------------------


class TestBothTiersAskTheSameHelper:
    def test_l1_and_l2_agree_on_the_running_build(self):
        assert events_route._current_build_id() == gmc.current_build_id()

    def test_neither_tier_mints_its_own_identity(self):
        """Both must resolve to `db_session_identity.current_build_id`."""
        from app.utils import db_session_identity

        assert gmc.current_build_id is db_session_identity.current_build_id
        assert events_route._current_build_id() == (
            db_session_identity.current_build_id()
        )
