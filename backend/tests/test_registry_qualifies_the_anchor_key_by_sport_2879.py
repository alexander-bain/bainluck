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

* **The 91 live `s6:` MLB anchors keep resolving.** They are still stored under
  the legacy shape when these two lines go live, and the re-key script runs
  *after*. `find_event_by_anchor` matches the D55 key OR its legacy equivalent,
  so there is no dark window. `_LegacyAwareAnchorSession` below exists because
  the shared `_AnchorSession` double does **not** model that `OR` — it reads
  `params["source_id"]` only — and a control test that cannot fail is not a
  control. See `r_getsource_guard_vacuous_when`.
* **Kalshi is not double-qualified.** Kalshi keys are already `sport_key:game_id`
  by Alex's 2026-08-21 ruling; a careless edit that qualified them again would
  produce `baseball_mlb:baseball_mlb:...` and orphan every Kalshi anchor.
* **ESPN and Odds API are untouched**, because `sport_key` is a StatPal-only
  qualifier and every other provider ignores it.
"""
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
    _FakeExecuteResult,
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


class _LegacyAwareAnchorSession(_AnchorSession):
    """`_AnchorSession` whose Step 2 read models the REAL D55 predicate.

    `_FIND_BY_ANCHOR_SQL` matches `a.source_id = :source_id OR a.source_id =
    :legacy_source_id`, preferring the D55 shape deterministically. The shared
    double ignores `legacy_source_id` entirely, which is harmless for the suites
    that never pass a sport (both parameters carry the same value there) and
    fatal here: the whole no-dark-window claim lives in that `OR`, so a control
    test written against the shared double would pass without exercising it.
    """

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM event_provider_anchors a" in sql:
            self.statements.append(statement)
            # Preference order copied from the SQL's ORDER BY: the D55 key wins
            # when both shapes are present, so a re-key in flight cannot flip
            # the answer depending on insertion order.
            for candidate in (params["source_id"], params["legacy_source_id"]):
                hit = self.anchors.get(
                    (params["source"], candidate, params["id_kind"])
                )
                if hit is not None:
                    return _FakeExecuteResult(
                        first_row=(hit, self.event_sports.get(hit, MLB_SPORT_ID))
                    )
            return _FakeExecuteResult()
        return await super().execute(statement, params)


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
        session = _LegacyAwareAnchorSession(sport_id=MLB_SPORT_ID)

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
        session = _LegacyAwareAnchorSession(sport_id=ATP_SPORT_ID)

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
        session = _LegacyAwareAnchorSession(
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
    async def test_a_legacy_s6_anchor_is_still_found_once_the_caller_qualifies(self):
        """The 91 live MLB anchors keep resolving — there is no dark window.

        This is the test that licenses the deploy ORDER (#2892 → these two lines
        → the re-key). The stored row is the pre-D55 `s6:` shape; the caller now
        derives `baseball_mlb:`; the `OR` in `_FIND_BY_ANCHOR_SQL` bridges them,
        and `anchor_is_current` re-derives the qualifier off the key it was
        handed rather than off the event, so corroboration still agrees.

        Green before the two lines (direct hit on `s6:`) and after (legacy arm).
        """
        row = _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=LIVE_MLB_FIXTURE_ID, commence_time_source="statpal",
        )
        session = _LegacyAwareAnchorSession(
            anchors={
                ("statpal", f"s6:{LIVE_MLB_FIXTURE_ID}", ANCHOR_KIND_GAME): MLB_ROW_ID
            },
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[row],
            sport_id=MLB_SPORT_ID,
        )

        found = await _find_by_anchor(
            session,
            _identity(
                "statpal", LIVE_MLB_FIXTURE_ID, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
            MLB_SPORT_ID,
        )

        assert found is not None and found.id == MLB_ROW_ID

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
        session = _LegacyAwareAnchorSession(
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
    async def test_the_legacy_arm_does_not_reopen_the_cross_sport_collision(self):
        """The transition window's real hazard, and why the guard is NOT dead code.

        Sport-qualified keys look like they make `_record_claim_anchor`'s
        cross-sport early return unreachable by construction: two sports can no
        longer derive the same `source_id`, so there is no cross-sport incumbent
        left to find. That is true only AFTER the re-key. Until then
        `find_event_by_anchor` also matches `statpal_legacy_source_id(key)`, and
        an NFL claim for `280445` still resolves `s6:280445` — which is an MLB
        row. The collision the qualifier removes comes straight back through the
        bridge that keeps the 91 live anchors working.

        What refuses it is `expected_sport_id`, not the key. So the branch stays
        until the legacy arm is deleted with it, and this pins the refusal for as
        long as both exist. Green in both arms, by two different mechanisms.
        """
        row = _row(
            event_id=MLB_ROW_ID, sport_id=MLB_SPORT_ID,
            commence=GAME_TIME, status="scheduled",
            statpal_fixture_id=SHARED_SIX_DIGITS, commence_time_source="statpal",
        )
        session = _LegacyAwareAnchorSession(
            anchors={
                ("statpal", f"s6:{SHARED_SIX_DIGITS}", ANCHOR_KIND_GAME): MLB_ROW_ID
            },
            event_sports={MLB_ROW_ID: MLB_SPORT_ID},
            structured_candidates=[row],
            sport_id=MLB_SPORT_ID,
        )

        assert await _find_by_anchor(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="americanfootball_nfl",
                home="Los Angeles Rams", away="San Francisco 49ers",
            ),
            NFL_SPORT_ID,
        ) is None

        # NON-VACUITY: the refusal above must be the SPORT check, not a miss.
        # The same legacy row, asked for by the sport that owns it, resolves —
        # so the bridge is live and the previous assertion actually reached the
        # guard it claims to be pinning.
        reached = await _find_by_anchor(
            session,
            _identity(
                "statpal", SHARED_SIX_DIGITS, sport_key="baseball_mlb",
                home="Miami Marlins", away="Boston Red Sox",
            ),
            MLB_SPORT_ID,
        )
        assert reached is not None and reached.id == MLB_ROW_ID

    @pytest.mark.asyncio
    async def test_kalshi_is_not_double_qualified_by_the_new_argument(self):
        """Kalshi game keys are ALREADY `sport_key:game_id` (Alex, 2026-08-21).

        Passing the sport to a provider that has its own qualifier is the one
        way these two lines could break a channel that was working: every live
        Kalshi anchor would be orphaned behind `baseball_mlb:baseball_mlb:...`.
        """
        session = _LegacyAwareAnchorSession(sport_id=MLB_SPORT_ID)

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
        session = _LegacyAwareAnchorSession(sport_id=NFL_SPORT_ID)

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
