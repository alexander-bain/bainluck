"""A COMPLETED EVENT'S BIGGER PICTURE STOPS BEING PINNED TO A PRE-DEPLOY BODY. #6883.

WHAT WAS SEEN, and it is why these tests exist at all.

On 2026-09-18, thirty minutes after release v4715 `ef59f73b` carried the #6806
fix to production, `/events/15298552` (Crystal Palace v Lech Poznan,
`completed`) still printed **two rows both labelled `Ekstraklasa Champion`, at
99% and 1%** under Bigger Picture -> Season context. Twelve of twelve
consecutive requests returned the pre-fix body; `cache.created_at` on every one
of them was `2026-09-18T05:50:05Z`, i.e. **thirty minutes BEFORE the release**.
The same process, asked to BUILD instead of remember (`?debug=1`), returned the
corrected body. `heroku ps` showed ONE web dyno, `up 23:21:36 -0700` — started
*by* that release — so this was not an un-cycled old process and there was
nothing to route around.

    away_team_futures   served 2   ·   build 1
    total_count         served 8   ·   build 7

THE CAUSE, and it is two independent holes, not one:

    if cached_status in ("completed", "closed"):
        return cached_response          # <- no expiry, EVER

1. **The L1 final entry never aged out.** So once a worker had warmed L1 for a
   completed event it never consulted Redis for that event again, and the whole
   L2 ladder below it — mirror, `stale_ok`, exactly-one-rebuild — was
   unreachable from behind it. The only exits were eviction
   (`_RELATED_FUTURES_MAX_SIZE = 30`) and the process dying. Neither is a clock:
   it could not be waited out. This tier's own `FRESH_TTL_FINAL` docstring
   already CLAIMED the hour bound that L1 was silently overriding.

2. **Neither level of this tier knew what a release was.** The sequence that
   bit: a pre-release process published the pre-fix body to the shared slot at
   05:50:05Z; `FRESH_TTL_FINAL = 3600` meant that slot was still *fresh* at
   06:26Z; the post-release process read it, called it `live`, and copied it
   into an L1 entry that never ages out. Age cannot express "built by code that
   no longer exists", because such a payload is YOUNG — it was not stale, it
   was WRONG.

Both holes were already closed on the sibling `/game-markets` tier one door up
the same file, by #6355 and #6394. This tier shipped (LAT-P136) as a copy of the
sibling's PRE-#6355 shape and never received either. So every assertion here has
a twin in `test_a_release_does_not_pin_its_own_pre_ship_payload_6355.py` and
`test_the_two_cache_tiers_share_one_deadline_6394.py`, deliberately: the point
is that the two tiers serving ONE page agree, not that this one has opinions.

🔴 THE TRAP THIS FILE PINS, and it would have made a false pass:
`rfc.payload_is_current_build` DELEGATES to the sibling's, which reads
`current_build_id` out of the **`_gmc` module namespace**. A test that
monkeypatches `rfc.current_build_id` alone patches only what `rfc.stamp`
writes — the refusal would go on asking the real helper and the test would pass
while proving nothing. `TestOneDefinitionOfWhichDeployAmI` is what stops that
delegation being quietly broken into two identities later.
"""

import time

import pytest

import app.routes.events as events_route
from app.utils import game_markets_cache as gmc
from app.utils import related_futures_cache as rfc
from app.utils.db_session_identity import UNKNOWN_BUILD


@pytest.fixture(autouse=True)
def _clean_l1():
    events_route._related_futures_cache.clear()
    yield
    events_route._related_futures_cache.clear()


def _stamped(build: str | None, *, status: str = "completed") -> dict:
    """A stored payload carrying `build`, or carrying no build field at all."""
    body = rfc.stamp({"away_team_futures": []}, source_status=status)
    envelope = dict(body[rfc.ENVELOPE_FIELD])
    if build is None:
        envelope.pop(rfc.BUILD_FIELD, None)
    else:
        envelope[rfc.BUILD_FIELD] = build
    body[rfc.ENVELOPE_FIELD] = envelope
    return body


def _both_tiers_running(monkeypatch, build: str) -> None:
    """Pin the running build for the WRITER and the REFUSAL — see the trap above."""
    monkeypatch.setattr(gmc, "current_build_id", lambda: build)
    monkeypatch.setattr(rfc, "current_build_id", lambda: build)


# ---------------------------------------------------------------------------
# 1. L1 — the pin itself. This is the filed defect.
# ---------------------------------------------------------------------------


class TestTheFinalEntryNoLongerPins:
    def test_a_completed_entry_older_than_the_final_ttl_is_a_miss(self):
        """🔴 THE DEFECT. This entry used to be returned forever."""
        events_route._related_futures_cache[15298552] = (
            time.time() - (rfc.FRESH_TTL_FINAL + 1),
            "completed",
            events_route._current_build_id(),
            {"away_team_futures": []},
        )
        assert events_route._read_related_futures_memo(15298552) is None

    def test_a_completed_entry_inside_the_final_ttl_is_still_served(self):
        """The reverse direction: this is a cache, and it must still cache.

        Deliberately older than the LIVE ttl, so this fails if finality stops
        selecting the longer bound and the tier collapses to 60 s.
        """
        events_route._related_futures_cache[15298552] = (
            time.time() - (events_route._RELATED_FUTURES_LIVE_TTL + 5),
            "completed",
            events_route._current_build_id(),
            {"away_team_futures": [1]},
        )
        assert events_route._read_related_futures_memo(15298552) == {
            "away_team_futures": [1]
        }

    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_both_final_statuses_take_the_bound(self, status):
        """`closed` is the one a status-string fix forgets."""
        events_route._related_futures_cache[1] = (
            time.time() - (rfc.FRESH_TTL_FINAL + 1),
            status,
            events_route._current_build_id(),
            {"away_team_futures": [1]},
        )
        assert events_route._read_related_futures_memo(1) is None

    def test_l1s_final_bound_is_the_l2_tiers_own_number(self):
        """Not a new constant. Two levels disagreeing is how this started."""
        fresh = time.time() - (rfc.FRESH_TTL_FINAL - 5)
        stale = time.time() - (rfc.FRESH_TTL_FINAL + 5)
        for ts, expected in ((fresh, {"away_team_futures": [1]}), (stale, None)):
            events_route._related_futures_cache[1] = (
                ts,
                "completed",
                events_route._current_build_id(),
                {"away_team_futures": [1]},
            )
            assert events_route._read_related_futures_memo(1) == expected

    def test_a_live_entry_keeps_its_sixty_seconds(self):
        """Untouched by this ship, asserted so the bound is not widened by it."""
        events_route._related_futures_cache[1] = (
            time.time() - (events_route._RELATED_FUTURES_LIVE_TTL + 1),
            "live",
            events_route._current_build_id(),
            {"away_team_futures": [1]},
        )
        assert events_route._read_related_futures_memo(1) is None

    def test_a_round_trip_through_the_writer_is_served(self):
        """NOT VACUOUS: the writer and the reader agree on the tuple shape.

        Every assertion above hand-builds the entry, so all of them would still
        pass if the writer wrote a shape the reader could never match.
        """
        events_route._write_related_futures_memo(
            15298552, "completed", {"away_team_futures": [1]}
        )
        assert events_route._read_related_futures_memo(15298552) == {
            "away_team_futures": [1]
        }


class TestL1RefusesAnotherBuild:
    def test_an_entry_from_another_build_is_a_miss_at_any_age(self):
        """Brand new, and built by code that is gone. Age cannot see this."""
        events_route._related_futures_cache[15298552] = (
            time.time(),
            "completed",
            "v4714-preship",
            {"away_team_futures": []},
        )
        assert events_route._read_related_futures_memo(15298552) is None

    def test_the_same_build_is_served(self):
        events_route._related_futures_cache[15298552] = (
            time.time(),
            "completed",
            events_route._current_build_id(),
            {"away_team_futures": [1]},
        )
        assert events_route._read_related_futures_memo(15298552) == {
            "away_team_futures": [1]
        }


# ---------------------------------------------------------------------------
# 2. 🔴 THE SEAM (#6394). L1 counts from the BUILD, not from this process's read.
# ---------------------------------------------------------------------------


class TestTheTwoLevelsShareOneDeadline:
    def test_a_body_l2_hands_over_just_inside_the_bound_is_not_given_a_fresh_hour(
        self,
    ):
        """🔴 THE PRODUCTION SEQUENCE, in one assertion.

        This is what actually happened on 15298552: L2 called a 05:50:05Z body
        `live` because it was inside `FRESH_TTL_FINAL`, and L1 stamped it with a
        brand-new clock. Were the stamp the READ time, the two bounds would
        COMPOSE to ~2x the hour both levels believe they enforce. Stamping from
        the payload's own `created_at` makes the L1 entry expire when the slot
        it was copied from expires — one deadline, not two in series.
        """
        from datetime import datetime, timedelta, timezone

        nearly_expired = rfc.stamp(
            {"away_team_futures": [1]},
            source_status="completed",
            created_at=datetime.now(timezone.utc)
            - timedelta(seconds=rfc.FRESH_TTL_FINAL - 5),
        )
        events_route._write_related_futures_memo(
            15298552, "completed", nearly_expired
        )

        stamped_at = events_route._related_futures_cache[15298552][0]
        age = time.time() - stamped_at
        assert age > rfc.FRESH_TTL_FINAL - 60, (
            "L1 stamped the READ time, so the entry just bought another full hour"
        )

    def test_l1_ages_a_payload_with_the_same_helper_l2_bounds_its_mirror_with(self):
        """One age computation for the page, not two that can drift apart."""
        assert events_route._memo_stamp.__module__ == "app.routes.events"
        from app.utils.event_concept_cache import payload_age_seconds

        assert gmc.payload_age_seconds is payload_age_seconds

    def test_a_payload_that_cannot_say_when_it_was_built_still_memoises(self):
        """Fails towards today's behaviour: a latency cost, never a truth one.

        The body is still bounded exactly as it is now — it just counts from
        now, because there is nothing else to count from.
        """
        before = time.time()
        events_route._write_related_futures_memo(
            15298552, "completed", {"away_team_futures": [1]}
        )
        assert events_route._related_futures_cache[15298552][0] >= before

    def test_a_created_at_in_the_future_can_only_shorten_the_entrys_life(self):
        """Writer-clock skew must never push the stamp forward past `now`."""
        from datetime import datetime, timedelta, timezone

        from_the_future = rfc.stamp(
            {"away_team_futures": [1]},
            source_status="completed",
            created_at=datetime.now(timezone.utc) + timedelta(seconds=600),
        )
        events_route._write_related_futures_memo(15298552, "completed", from_the_future)
        assert events_route._related_futures_cache[15298552][0] <= time.time() + 1


# ---------------------------------------------------------------------------
# 3. L2 — the slot that survived the release.
# ---------------------------------------------------------------------------


class TestTheStoredPayloadNamesItsBuild:
    def test_stamp_records_the_running_build(self):
        assert rfc.build_id_of(rfc.stamp({}, source_status="completed")) == (
            rfc.current_build_id()
        )

    def test_build_id_of_is_empty_for_shapes_that_cannot_carry_one(self):
        assert rfc.build_id_of(None) == ""
        assert rfc.build_id_of({}) == ""
        assert rfc.build_id_of({rfc.ENVELOPE_FIELD: "not-a-dict"}) == ""


class TestAPayloadFromAnotherBuildIsRefused:
    def test_a_different_build_is_not_current(self, monkeypatch):
        _both_tiers_running(monkeypatch, "v4715")
        assert rfc.payload_is_current_build(_stamped("v4714")) is False

    def test_the_same_build_is_current(self, monkeypatch):
        _both_tiers_running(monkeypatch, "v4715")
        assert rfc.payload_is_current_build(_stamped("v4715")) is True

    def test_read_refuses_a_fresh_primary_slot_from_another_build(self, monkeypatch):
        """🔴 THE PRODUCTION SPECIMEN: young, and built by code that is gone.

        15298552's slot was ~36 min old against a 3600 s TTL, so every age-based
        check in the tier called it fresh — and it was, and it was also wrong.
        """
        _both_tiers_running(monkeypatch, "v4715")
        monkeypatch.setattr(rfc, "get_client", object)  # any non-None client
        monkeypatch.setattr(
            rfc, "read_slot", lambda client, key: _stamped("v4714-preship")
        )

        body, state = rfc.read(15298552)
        assert state == "stale_build"
        assert body is None

    def test_the_mirror_is_refused_too_and_not_used_as_a_second_door(self, monkeypatch):
        """The mirror is the same bytes from the same dead build.

        If only the primary were checked, a mismatch would fall through to the
        mirror, pass `mirror_is_servable` on age, and be served `stale_ok` — the
        pre-ship payload delivered anyway, now wearing an availability label.
        """
        _both_tiers_running(monkeypatch, "v4715")
        monkeypatch.setattr(rfc, "get_client", object)  # any non-None client

        keys = rfc.keys_for(15298552)
        monkeypatch.setattr(
            rfc,
            "read_slot",
            lambda client, key: (
                None if key == keys.primary else _stamped("v4714-preship")
            ),
        )

        body, state = rfc.read(15298552)
        assert state == "stale_build"
        assert body is None

    def test_a_current_build_slot_is_still_served_live(self, monkeypatch):
        """The reverse direction. This is a cache and it must still cache."""
        _both_tiers_running(monkeypatch, "v4715")
        monkeypatch.setattr(rfc, "get_client", object)  # any non-None client
        monkeypatch.setattr(rfc, "read_slot", lambda client, key: _stamped("v4715"))

        body, state = rfc.read(15298552)
        assert state == "live"
        assert body is not None

    def test_stale_build_is_its_own_state_and_not_folded_into_miss(self, monkeypatch):
        """"Nothing was cached" and "a deploy made it a lie" are different facts.

        Only the second is supposed to be rare, so a counter on the wrong one of
        those reads as a healthy cache.
        """
        _both_tiers_running(monkeypatch, "v4715")
        monkeypatch.setattr(rfc, "get_client", object)
        monkeypatch.setattr(rfc, "read_slot", lambda client, key: None)
        assert rfc.read(15298552)[1] == "miss"


# ---------------------------------------------------------------------------
# 4. 🔴 THE HALF THAT MATTERS MOST. Fail open, or the cache dies everywhere.
# ---------------------------------------------------------------------------


class TestItFailsOpenWhenTheBuildIsUnknown:
    def test_a_payload_written_before_this_ship_is_served(self, monkeypatch):
        """No build field at all — every slot in Redis at deploy time.

        Reading an absent stored build as a mismatch would invalidate the whole
        tier at the moment this deploys: a self-inflicted thundering herd on one
        of the four north-star pages.
        """
        _both_tiers_running(monkeypatch, "v4715")
        assert rfc.payload_is_current_build(_stamped(None)) is True

    def test_an_unknown_running_build_serves_everything(self, monkeypatch):
        """Local dev, CI, and any Heroku app without dyno metadata.

        Reading this as a mismatch would mean EVERY read is a miss and the cache
        is dead in exactly the environments that cannot notice.
        """
        _both_tiers_running(monkeypatch, UNKNOWN_BUILD)
        assert rfc.payload_is_current_build(_stamped("v4714")) is True

    def test_an_empty_stored_build_is_served(self, monkeypatch):
        _both_tiers_running(monkeypatch, "v4715")
        assert rfc.payload_is_current_build(_stamped("")) is True

    def test_it_refuses_only_when_both_are_known_and_they_differ(self, monkeypatch):
        """The one case #6883 is about, stated as the conjunction it is."""
        _both_tiers_running(monkeypatch, "v4715")
        assert rfc.payload_is_current_build(_stamped("v4714")) is False


# ---------------------------------------------------------------------------
# 5. One definition of "which deploy am I" across the two tiers on one page.
# ---------------------------------------------------------------------------


class TestOneDefinitionOfWhichDeployAmI:
    def test_the_two_tiers_and_the_l1_agree_on_the_running_build(self):
        assert events_route._current_build_id() == rfc.current_build_id()
        assert rfc.current_build_id() == gmc.current_build_id()

    def test_neither_tier_mints_its_own_identity(self):
        """All three must resolve to `db_session_identity.current_build_id`."""
        from app.utils import db_session_identity

        assert rfc.current_build_id is db_session_identity.current_build_id
        assert gmc.current_build_id is db_session_identity.current_build_id
        assert events_route._current_build_id() == (
            db_session_identity.current_build_id()
        )

    def test_the_refusal_delegates_rather_than_keeping_a_second_opinion(self):
        """🔴 THE TRAP IN THIS FILE'S HEADER.

        `rfc.payload_is_current_build` asks the sibling, which reads
        `current_build_id` from the `_gmc` namespace. If someone later gives
        this tier its own copy, `_both_tiers_running` above silently stops
        covering the refusal path and several tests here go vacuous.
        """
        assert rfc.payload_is_current_build.__module__ == (
            "app.utils.related_futures_cache"
        )
        assert rfc.BUILD_FIELD is gmc.BUILD_FIELD
        assert rfc.FRESH_TTL_FINAL is gmc.FRESH_TTL_FINAL


# ---------------------------------------------------------------------------
# 6. The tier's OTHER bounds are untouched by this ship.
# ---------------------------------------------------------------------------


def test_eviction_still_bounds_the_dict():
    """The size bound is the only thing that used to end a pin. It survives."""
    for event_id in range(events_route._RELATED_FUTURES_MAX_SIZE + 10):
        events_route._write_related_futures_memo(
            event_id, "completed", {"away_team_futures": [event_id]}
        )
    assert (
        len(events_route._related_futures_cache)
        <= events_route._RELATED_FUTURES_MAX_SIZE
    )


def test_the_live_ttl_is_still_the_tiers_own_number():
    assert rfc.FRESH_TTL_LIVE == events_route._RELATED_FUTURES_LIVE_TTL
