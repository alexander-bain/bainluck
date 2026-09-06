"""The registry passes the SPORT to the anchor key — #2879, D55, lane1/086.

`authority/003` (#2892) made `anchor_key_for_claim` accept `sport_key=` and made
`statpal_anchor_key` qualify by the sport instead of by counting the id's digits.
It shipped with the qualifier OPTIONAL, because the two production call sites are
in `event_registry.py` and that file is lane1's under D50. Optional means that
until those two call sites pass it, **every live StatPal claim still takes the
legacy digit branch** and D55 buys nothing at all. This file is the proof that
the two lines are wired, and it is behavioural: every assertion below is on what
`find_or_create_event` / `_find_by_anchor` actually did to the anchor store, not
on the text of the call.

## What is RED without the two lines

* **NFL and MLB collide.** An NFL `contestid` is 6 digits (`280445`-`280772`,
  374 of them measured 2026-09-03) and so is an MLB `id`. The digit rule files
  both under `s6:`, and the unique key `(source, source_id, id_kind)` spans every
  sport, so the second sport to arrive hits `ON CONFLICT DO NOTHING` and **gets
  no anchor row of its own**. It is then unanchorable forever, and the
  cross-sport early return in `_record_claim_anchor` swallows the collision
  without a receipt — the half of #2879 that produces no evidence.
* **Tennis is not anchorable at all.** Tennis fixture ids are 7 digits
  (`2629673`), which matched neither `^\\d{6}$` nor `^\\d{10}$`, so the key was
  `None` and the channel wrote nothing. Step 4 of the AUTHORITY program could
  have been built, deployed and stamped nothing.
* **Step 2 asks for a key the writer never wrote.** A read that derives `s6:`
  while the writer stored `americanfootball_nfl:` is a miss on a row that is
  right there.

## What must stay GREEN in BOTH arms (gotcha #43)

A guard that only proves the new keys appear is half a guard. Three of the tests
below pass before the two lines as well as after, and one of them is the reason
this change is safe to deploy in the order it is being deployed:

* **The live MLB anchors keep resolving.** This was the load-bearing one and it
  is the assertion that has MOVED, so read it before trusting the file. While
  these two lines were shipping, the rows were still stored as `s6:` and
  `find_event_by_anchor` matched the D55 key OR its legacy equivalent; the whole
  no-dark-window claim lived in that `OR`.
* **Kalshi is not double-qualified.** Kalshi keys are already `sport_key:game_id`
  by Alex's 2026-08-21 ruling; a careless edit that qualified them again would
  produce `baseball_mlb:baseball_mlb:...` and orphan every Kalshi anchor.
* **ESPN and Odds API are untouched**, because `sport_key` is a StatPal-only
  qualifier and every other provider ignores it.

## Amendment, 2026-09-06 — step 3 landed and two of these tests changed SUBJECT

The re-key ran (94 legacy rows: 29 rewritten, 65 deleted as already superseded,
0 collisions) and the legacy branch, `statpal_legacy_source_id` and the `OR` were
deleted together. Two consequences are recorded here rather than only in the
tests, because both are cases where a green suite would otherwise mean less than
it looks like:

* `_LegacyAwareAnchorSession` is **gone**. It existed only to model the `OR`,
  which the shared `_AnchorSession` double does not; with a single equality the
  shared double is an exact model and a subclass would be a divergent one.
  A double that still models a deleted predicate is the most expensive kind of
  green — every test here would keep passing against behaviour production
  stopped having.
* The cross-sport refusal changed MECHANISM, not verdict. It used to be
  `expected_sport_id` refusing a legacy row two sports could both reach; it is
  now the key not matching at all. The sport guard is still live and still
  needed — for ESPN and Odds API, whose ids are single global spaces with no
  qualifier by design — so nothing about it is deleted on the strength of this.
"""
import logging
from datetime import datetime, timezone

import pytest

from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _find_by_anchor,
    _sport_id_cache,
    find_or_create_event,
)
from app.utils.provider_anchor_keys import ANCHOR_KIND_GAME
from tests.test_anchor_channel_consumer_2213 import (
    _AnchorSession,
    _row,
)

MLB_SPORT_ID = 53232
NFL_SPORT_ID = 60001
ATP_SPORT_ID = 60002

#: The collision D55 exists to remove: one 6-digit token, two sports. MLB calls
#: it `id`, NFL calls it `contestid`, and the digit rule called both `s6`.
SHARED_SIX_DIGITS = "280445"
#: 7 digits — neither legacy namespace, i.e. previously unanchorable.
TENNIS_FIXTURE_ID = "2629673"
#: One of the 91 live MLB anchors still stored under the legacy shape.
LIVE_MLB_FIXTURE_ID = "354453"

MLB_ROW_ID = 15228865
NFL_ROW_ID = 15330001

GAME_TIME = datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _seed_sport_cache():
    """Resolve every sport from the cache so one double can serve three sports.

    `_resolve_sport_id` short-circuits on this dict, which is what lets a single
    `_AnchorSession` (whose `FROM sports` answer is one scalar) hand back a
    different `sport_id` per claim.
    """
    _sport_id_cache["baseball_mlb"] = MLB_SPORT_ID
    _sport_id_cache["americanfootball_nfl"] = NFL_SPORT_ID
    _sport_id_cache["tennis_atp"] = ATP_SPORT_ID
    yield
    for key in ("baseball_mlb", "americanfootball_nfl", "tennis_atp"):
        _sport_id_cache.pop(key, None)


#: `_LegacyAwareAnchorSession` lived here until step 3 (2026-09-06). It was a
#: `_AnchorSession` subclass that modelled the two-shape Step 2 read — `a.source_id
#: = :source_id OR a.source_id = :legacy_source_id` — because the shared double
#: ignores the second parameter and the entire no-dark-window claim lived in that
#: `OR`. `_FIND_BY_ANCHOR_SQL` is a single equality again, so the shared double is
#: now an exact model of it and the subclass would be a divergent second one.
#:
#: Deleting it is not tidying. A test double that models a predicate the code no
#: longer has is the most expensive kind of green: every test below would keep
#: passing against behaviour production stopped having.


def _identity(source, source_id, *, sport_key, home, away, commence=GAME_TIME):
    return EventIdentity(
        sport_key=sport_key, home_team_name=home, away_team_name=away,
        commence_time=commence,
        claim=EventClaim(source, source_id),
        commence_time_source=source, status="scheduled",
    )


def _statpal_keys(session):
    """The StatPal `source_id`s currently in the anchor store."""
    return {
        source_id
        for (source, source_id, _kind) in session.anchors
        if source == "statpal"
    }


# ══════════════════════════════════════════════════════════════════════════
# RED without the two lines — the write side
# ══════════════════════════════════════════════════════════════════════════

class TestTheWriteSideStopsCollidingAcrossSports:

    @pytest.mark.asyncio
    async def test_nfl_and_mlb_fixtures_sharing_six_digits_each_get_an_anchor(self):
        """Two sports, one 6-digit token, two anchor rows — one per event.

        Without the qualifier both claims key `s6:280445`. The MLB event is
        created and anchored; the NFL event is created and its anchor write is
        swallowed by `ON CONFLICT DO NOTHING`, leaving a live row that no anchor
        names. The assertion is on which EVENTS are anchored, not on the key
        strings, so it fails for the reason that matters rather than on spelling.
        """
        session = _AnchorSession(sport_id=MLB_SPORT_ID)

        mlb, mlb_created = await find_or_create_event(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
        )
        nfl, nfl_created = await find_or_create_event(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
        )

        assert mlb_created and nfl_created
        assert mlb.id != nfl.id

        anchored_events = set(session.anchors.values())
        assert anchored_events == {mlb.id, nfl.id}, (
            "both events must be anchored; a shared key means the second sport "
            "hit ON CONFLICT DO NOTHING and is unanchorable"
        )
        assert _statpal_keys(session) == {
            f"baseball_mlb:{SHARED_SIX_DIGITS}",
            f"americanfootball_nfl:{SHARED_SIX_DIGITS}",
        }

    @pytest.mark.asyncio
    async def test_a_tennis_fixture_is_anchorable_at_all(self):
        """7 digits matched neither legacy namespace, so nothing was written.

        This is not a near-miss that a threshold could have caught: the key was
        `None`, the channel wrote no row, and the absence looked exactly like a
        provider that had nothing to say.
        """
        session = _AnchorSession(sport_id=ATP_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            _identity(
                "statpal", TENNIS_FIXTURE_ID, sport_key="tennis_atp",
                home="Carlos Alcaraz", away="Jannik Sinner",
            ),
        )

        assert created
        assert session.anchors == {
            ("statpal", f"tennis_atp:{TENNIS_FIXTURE_ID}", ANCHOR_KIND_GAME): event.id
        }


# ══════════════════════════════════════════════════════════════════════════
# RED without the Step 1 repair — the cascade answered before it knew the sport
# ══════════════════════════════════════════════════════════════════════════

class TestStep1CannotAnswerBeforeTheSportIsKnown:
    """CERT-853. A qualified anchor key buys nothing while Step 1 is global.

    The two lines above qualify Step 2. Step 1 runs FIRST, and for StatPal it read
    `WHERE statpal_fixture_id = :id` across every sport — so an NFL claim for
    `280445` was answered by the MLB row of the same token and
    `find_or_create_event` returned `created=False` before the qualified key was
    ever derived. CERT-853 reproduced exactly that. Ordering does not cure it:
    Step 1 is the step that has to know the sport.

    Every test in the classes above calls `_find_by_anchor` directly, and that is
    precisely how Step 1 escaped them. These run the WHOLE cascade.
    """

    @staticmethod
    def _mlb_row_carrying_the_shared_token():
        return _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            home="Miami Marlins", away="Boston Red Sox",
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=SHARED_SIX_DIGITS, commence_time_source="statpal",
        )

    @pytest.mark.asyncio
    async def test_an_nfl_claim_never_absorbs_the_mlb_row_sharing_its_token(self):
        """The exact reproduction CERT-853 blocked on, run end to end."""
        mlb = self._mlb_row_carrying_the_shared_token()
        session = _AnchorSession(
            source_matches={SHARED_SIX_DIGITS: mlb},
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            sport_id=NFL_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
        )

        assert created, (
            "the NFL claim must CREATE; absorbing the MLB row is the #2879 "
            "cross-sport merge the whole ruling exists to stop"
        )
        assert event.id != MLB_ROW_ID
        assert event.sport_id == NFL_SPORT_ID
        assert event.home_team_name == "Los Angeles Rams"

        # And the new row is anchored under its OWN sport, so the next NFL poll
        # of `280445` finds it at Step 2 instead of creating a third row.
        assert (
            "statpal", f"americanfootball_nfl:{SHARED_SIX_DIGITS}", ANCHOR_KIND_GAME
        ) in session.anchors

    @pytest.mark.asyncio
    async def test_the_sport_that_owns_the_token_still_finds_its_row(self):
        """The same-sport control. Green in both arms, and that is the point.

        Scoping Step 1 must refuse the OTHER sport without also refusing the
        owner — otherwise every StatPal poll re-creates the row it already has.
        Without this the repair could 'pass' by breaking Step 1 outright.
        """
        mlb = self._mlb_row_carrying_the_shared_token()
        session = _AnchorSession(
            source_matches={SHARED_SIX_DIGITS: mlb},
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            sport_id=MLB_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
        )

        assert created is False
        assert event is mlb

    @pytest.mark.asyncio
    async def test_the_refused_collision_leaves_a_receipt(self, caplog):
        """D55: a collision raises or tags — it never silently no-ops.

        A `WHERE sport_id = :x` would have fixed the absorption and made the MLB
        row invisible at the same time, so the twin nobody can see is the twin
        nobody fixes. Step 2 already WARNs on this exact collision
        (`find_event_by_anchor`); Step 1 now reports it the same way.
        """
        mlb = self._mlb_row_carrying_the_shared_token()
        session = _AnchorSession(
            source_matches={SHARED_SIX_DIGITS: mlb},
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            sport_id=NFL_SPORT_ID,
        )

        with caplog.at_level(logging.WARNING, logger="app.services.event_registry"):
            await find_or_create_event(
                session,
                _identity(
                    "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
                    home="Los Angeles Rams", away="San Francisco 49ers",
                ),
            )

        receipts = [
            record.getMessage() for record in caplog.records
            if "D55/#2879" in record.getMessage()
        ]
        assert len(receipts) == 1, caplog.text
        # Both sports and the incumbent row are named, so the receipt is
        # actionable without a second query.
        assert str(MLB_ROW_ID) in receipts[0]
        assert str(MLB_SPORT_ID) in receipts[0]
        assert str(NFL_SPORT_ID) in receipts[0]

    @pytest.mark.asyncio
    async def test_espn_step_1_is_deliberately_not_sport_scoped(self):
        """The asymmetry is a decision, not an oversight — pin it.

        StatPal issues fixture tokens per sport, so its ids collide. An ESPN id
        is one global id space: the same token never names two games. Scoping
        ESPN would buy nothing and would turn a mis-sported row into a silent
        second create, which is the failure #2869 is already about.
        """
        espn_row = _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            home="Miami Marlins", away="Boston Red Sox",
            commence=GAME_TIME, status="scheduled",
            espn_id="401872657", commence_time_source="espn",
        )
        session = _AnchorSession(
            source_matches={"401872657": espn_row},
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            sport_id=NFL_SPORT_ID,
        )

        event, created = await find_or_create_event(
            session,
            _identity(
                "espn", "401872657", sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
        )

        assert created is False
        assert event is espn_row


# ══════════════════════════════════════════════════════════════════════════
# RED without the two lines — the read side
# ══════════════════════════════════════════════════════════════════════════

class TestTheReadSideAsksForTheKeyTheWriterWrote:

    @pytest.mark.asyncio
    async def test_step_2_finds_the_row_its_own_d55_anchor_names(self):
        """A read that derives `s6:` misses a row stored under the sport."""
        row = _row(
            event_id=NFL_ROW_ID, sport_id=NFL_SPORT_ID,
            home="Los Angeles Rams", away="San Francisco 49ers",
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=SHARED_SIX_DIGITS, commence_time_source="statpal",
        )
        session = _AnchorSession(
            anchors={
                ("statpal", f"americanfootball_nfl:{SHARED_SIX_DIGITS}",
                 ANCHOR_KIND_GAME): NFL_ROW_ID
            },
            event_sports={NFL_ROW_ID: NFL_SPORT_ID},
            structured_candidates=[row],
            sport_id=NFL_SPORT_ID,
        )

        found = await _find_by_anchor(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
            NFL_SPORT_ID,
        )

        assert found is not None and found.id == NFL_ROW_ID


# ══════════════════════════════════════════════════════════════════════════
# GREEN in BOTH arms — the refusals and the transition (gotcha #43)
# ══════════════════════════════════════════════════════════════════════════

class TestWhatMustNotChange:

    @pytest.mark.asyncio
    async def test_the_rekeyed_mlb_anchor_resolves_and_the_legacy_shape_does_not(
        self,
    ):
        """The live MLB anchors keep resolving — there is no dark window.

        This test licensed the deploy ORDER (#2892 → lane1's two lines → the
        re-key) and it still does, from the far side. Its subject moved with the
        data: the stored row used to be `s6:` and had to be reachable from a
        `baseball_mlb:` caller through the `OR`; after the re-key of 2026-09-06
        the stored row IS `baseball_mlb:` and the `OR` is gone.

        Both arms are asserted, because the two facts have to hold together for
        the sequence to have been safe. If only the first were checked, deleting
        the bridge one deploy early would look identical — and 94 MLB anchors
        would have gone dark with a green suite.
        """
        row = _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=LIVE_MLB_FIXTURE_ID, commence_time_source="statpal",
        )
        claim = _identity(
            "statpal", LIVE_MLB_FIXTURE_ID, sport_key="baseball_mlb",
            home="Miami Marlins", away="Boston Red Sox",
        )

        rekeyed = _AnchorSession(
            anchors={
                (
                    "statpal",
                    f"baseball_mlb:{LIVE_MLB_FIXTURE_ID}",
                    ANCHOR_KIND_GAME,
                ): MLB_ROW_ID
            },
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[row],
            sport_id=MLB_SPORT_ID,
        )
        found = await _find_by_anchor(rekeyed, claim, MLB_SPORT_ID)
        assert found is not None and found.id == MLB_ROW_ID

        # The same claim against the shape the re-key removed: a miss now, by
        # design. A row in this shape can only come from the `--rollback`
        # restore or an un-migrated copy, and resolving it would mean the bridge
        # is still live under a different name.
        legacy_only = _AnchorSession(
            anchors={
                (
                    "statpal",
                    f"s6:{LIVE_MLB_FIXTURE_ID}",
                    ANCHOR_KIND_GAME,
                ): MLB_ROW_ID
            },
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[row],
            sport_id=MLB_SPORT_ID,
        )
        assert await _find_by_anchor(legacy_only, claim, MLB_SPORT_ID) is None

    @pytest.mark.asyncio
    async def test_no_cross_sport_absorption_on_a_shared_fixture_id(self):
        """An MLB claim never lands on the NFL row that shares its digits.

        Green in both arms — before the two lines the `expected_sport_id` guard
        refuses it, after them the key does not even match. Pinned because those
        are different mechanisms and the guard must survive losing either one.
        """
        row = _row(
            event_id=NFL_ROW_ID, sport_id=NFL_SPORT_ID,
            home="Los Angeles Rams", away="San Francisco 49ers",
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=SHARED_SIX_DIGITS, commence_time_source="statpal",
        )
        session = _AnchorSession(
            anchors={
                ("statpal", f"americanfootball_nfl:{SHARED_SIX_DIGITS}",
                 ANCHOR_KIND_GAME): NFL_ROW_ID
            },
            event_sports={NFL_ROW_ID: NFL_SPORT_ID},
            structured_candidates=[row],
            sport_id=NFL_SPORT_ID,
        )

        assert await _find_by_anchor(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
            MLB_SPORT_ID,
        ) is None

    @pytest.mark.asyncio
    async def test_the_cross_sport_collision_is_now_closed_by_the_KEY(self):
        """What deleting the legacy arm changed: the MECHANISM of the refusal.

        Through the transition this collision was live. An NFL claim for
        `280445` derived `americanfootball_nfl:280445`, missed, and then the
        legacy arm resolved `s6:280445` — an MLB row. Only `expected_sport_id`
        refused it, so `_record_claim_anchor`'s cross-sport early return was
        load-bearing for StatPal and this test pinned it there.

        With the arm gone the two sports cannot reach one row at all: the key
        does not match and there is nothing for the sport guard to refuse. That
        is a strictly better place to stop, and the reason the whole D55
        sequence was worth running.

        The sport guard is NOT thereby dead code, which is why it is not deleted
        here — and this is the one thing about the guard worth stating clearly.
        ESPN and Odds API ids are single global id spaces with no sport
        qualifier by design (`test_espn_step_1_is_deliberately_not_sport_scoped`
        pins that on purpose: scoping them would turn a mis-sported row into a
        silent second create). A mis-sported ESPN row still produces a
        cross-sport incumbent, and `expected_sport_id` is still the only thing
        that refuses it. StatPal simply stopped being one of the ways to get
        there.
        """
        mlb_row = _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=SHARED_SIX_DIGITS, commence_time_source="statpal",
        )
        session = _AnchorSession(
            anchors={
                (
                    "statpal",
                    f"baseball_mlb:{SHARED_SIX_DIGITS}",
                    ANCHOR_KIND_GAME,
                ): MLB_ROW_ID
            },
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[mlb_row],
            sport_id=MLB_SPORT_ID,
        )

        nfl_claim = _identity(
            "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
            home="Los Angeles Rams", away="San Francisco 49ers",
        )
        assert await _find_by_anchor(session, nfl_claim, NFL_SPORT_ID) is None

        # NON-VACUITY, and it is doing more work than it looks like. The
        # refusal above must not be "this session resolves nothing": the SAME
        # row, asked for by the sport that owns it, still resolves. Without this
        # arm, deleting the Step 2 read entirely would pass the assertion above.
        reached = await _find_by_anchor(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
            MLB_SPORT_ID,
        )
        assert reached is not None and reached.id == MLB_ROW_ID

        # And the refusal is the KEY, not the sport guard: hand the NFL claim
        # the sport its own incumbent is in and it STILL misses, because
        # `americanfootball_nfl:280445` names no row. A sport-guard-only refusal
        # would resolve here.
        assert await _find_by_anchor(session, nfl_claim, MLB_SPORT_ID) is None

    @pytest.mark.asyncio
    async def test_kalshi_is_not_double_qualified_by_the_new_argument(self):
        """Kalshi game keys are ALREADY `sport_key:game_id` (Alex, 2026-08-21).

        Passing the sport to a provider that has its own qualifier is the one
        way these two lines could break a channel that was working: every live
        Kalshi anchor would be orphaned behind `baseball_mlb:baseball_mlb:...`.
        """
        session = _AnchorSession(sport_id=MLB_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            _identity(
                "kalshi", "KXMLBGAME-26AUG25MIABOS-BOS", sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
        )

        assert created
        assert session.anchors == {
            ("kalshi", "baseball_mlb:26AUG25MIABOS", ANCHOR_KIND_GAME): event.id
        }

    @pytest.mark.asyncio
    async def test_espn_keys_are_untouched_by_the_sport(self):
        """`sport_key` is a StatPal qualifier; every other provider ignores it."""
        session = _AnchorSession(sport_id=NFL_SPORT_ID)

        event, created = await find_or_create_event(
            session,
            _identity(
                "espn", "401866758", sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
        )

        assert created
        assert session.anchors == {
            ("espn", "401866758", ANCHOR_KIND_GAME): event.id
        }
