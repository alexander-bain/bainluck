"""D104 = A4: the NBA joins the ruled failover set. #4493, ship parent #2867.

The second of the three releases Alex asked for:

    "Flip football first (the Thursday kickoff), then the rest in one release
    each."

Football shipped as #4417 and its resilience hole closed as #4443. This is the
NBA's release. NHL is the next one and must NOT move here — a release that
lands two flips is graded for one.

WHY THE NBA IS ELIGIBLE, MEASURED RATHER THAN ASSUMED
------------------------------------------------------
`flip_permitted` has six refusal branches and D104 retires exactly one of them,
the wait. The NBA had to be refused on the wait ALONE for this ship to be a
gate exemption rather than a hole punched through a structural branch. Read
from the live row on `/api/admin/statpal/authority-agreement` at
2026-09-09 21:19:54Z, before this change:

    basketball_nba  would_fire_if_espn_went_dark=false  NO-FAILOVER-NOT-GATED
    "has not cleared D50's measured half: basketball_nba is 5/7 consecutive
     days at or above 99.5% - a wait, not a defect"

That is branch 6 and nothing else. The four structural branches are clear:
`stamp_nba_statpal_fixtures` exists, the sport is in `DISCOVERY_SCHEDULED_SPORTS`
with `discovery_state == "SCHEDULED"`, and its governing number is populated.

THE `pct` TRAP
--------------
The NBA's identity `pct` reads **3.39** and the NHL's **2.28**, which look
disqualifying and are not. They are not those sports' governing numbers:
`GOVERNING_IDENTITY_NUMBERS["basketball_nba"]` is `("ours_covered_pct",)`, which
reads 100.0. Only football is governed by `("pct", "ours_covered_pct")`. A
reader who checks `pct` here concludes the NBA is nowhere near ready. The test
`test_the_nba_is_not_governed_by_the_number_that_looks_bad` pins the distinction
so the next release does not relitigate it.

WHAT THIS SHIP IS NOT
---------------------
It is not a flip. `basketball_nba` still holds ESPN in `AUTHORITY_BY_SPORT` and
must: that map is the STANDING source of record, and `authority_failover.decide`
reads a `STATPAL` value there as "this sport has already flipped, ESPN's silence
is not an outage for it" - which is not a fallback and is not what D104 asked
for. `TestTheStandingSwitchStillDidNotMove` is the guard that keeps the two
apart.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DISCOVERY_SCHEDULED_SPORTS,
    ESPN,
    FLIP_RULED_WITHOUT_STREAK,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
    authority_for,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS

NFL = "americanfootball_nfl"
NBA = "basketball_nba"
NHL = "icehockey_nhl"
MLB = "baseball_mlb"


def _days(n, state="MEETS"):
    """`n` CONSECUTIVE ledger days ending 2026-09-30, all in one state.

    Same shape as `test_d104_failover_stops_waiting_for_seven_days_4417._days`,
    and deliberately a second copy rather than an import: these two files pin
    two different releases, and a shared fixture edited for one would silently
    retune the other's controls.

    The key is `day`, not `date`. The first cut of this file used `date` and
    every ledger it built read as ABSENT, so the NHL control refused with "has
    no agreement ledger yet" instead of "5/7" — still `False`, still green if
    the assertion had only checked `permitted is False`. That is why the
    controls in this file assert the refusal REASON and not merely its verdict.
    """
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    return [
        {"day": (end - timedelta(days=n - 1 - i)).isoformat(), "state": state}
        for i in range(n)
    ]


class TestTheNbaFailsOverWithoutTheWait:
    """The ship itself."""

    def test_the_nba_is_in_the_ruled_set(self):
        assert NBA in FLIP_RULED_WITHOUT_STREAK, (
            "#4493 is the NBA's release under D104; the ruled set is the one "
            "line that delivers it"
        )

    def test_a_short_streak_no_longer_refuses_the_nba(self):
        """The exact state the live row was in: 5 of 7 days."""
        permitted, why = flip_permitted(NBA, _days(5))
        assert permitted is True, why

    def test_an_empty_ledger_no_longer_refuses_the_nba(self):
        """The #4443 case, now reaching a second sport.

        A ruled sport must be permitted on an unreadable/absent ledger, because
        `_decide_failovers` hands `flip_permitted` an empty list when the read
        fails. If this reds, #4443's caller fix has stopped reaching the ruled
        set.
        """
        permitted, why = flip_permitted(NBA, [])
        assert permitted is True, why


class TestOnlyTheNbaShipsOnThisIssue:
    """Alex: "then the rest in one release each" - so the set grows by one."""

    def test_the_ruled_set_is_exactly_football_and_the_nba(self):
        assert FLIP_RULED_WITHOUT_STREAK == frozenset({NFL, NBA}), (
            "the ruled set must equal what has actually been graded: football "
            "on #4417 and the NBA on #4493. NHL is its own release under "
            "#2867; adding it here lands two flips under a cert that graded one"
        )

    def test_the_nhl_still_waits(self):
        """The control that proves this ship is one sport wide."""
        permitted, why = flip_permitted(NHL, _days(5))
        assert permitted is False, why
        assert f"5/{REQUIRED_STREAK_DAYS}" in why, why

    def test_the_nhl_is_still_refused_on_an_empty_ledger(self):
        permitted, why = flip_permitted(NHL, [])
        assert permitted is False, why


class TestTheStructuralRefusalsAreUntouched:
    """D104 exempts the WAIT. It does not reach "there is nothing to flip to"."""

    def test_mlb_still_refuses_and_not_because_of_a_wait(self):
        """The D63 case (#4436) - a top-tier league Alex named, still refused.

        This is the test that keeps the ship honest. MLB is quoted in the same
        breath as football and the NBA, so a change that flipped it too would
        look like obedience to D104 rather than the bug it is.
        """
        permitted, why = flip_permitted(MLB, _days(30))
        assert permitted is False, why
        assert f"5/{REQUIRED_STREAK_DAYS}" not in why, (
            f"MLB must refuse on its missing governing number, not on a wait: {why}"
        )

    def test_every_ruled_sport_still_clears_all_four_structural_branches(self):
        """Ordering, re-checked against the set as it now stands.

        The ruling is asked AFTER the structural branches, so a key may only
        join the ruled set if it would have passed them anyway. This is the
        assertion that fires if a future release adds a sport that does not.
        """
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert key in SHADOW_STAMPERS, key
            assert key in DISCOVERY_SCHEDULED_SPORTS, key
            assert GOVERNING_IDENTITY_NUMBERS.get(key), key
            assert discovery_state(key)[0] == "SCHEDULED", key

    def test_an_empty_ledger_permits_only_ruled_sports(self):
        """#4443's property, re-proved now that the ruled set has two members.

        `flip_permitted(key, [])` can permit a RULED sport and nothing else -
        every other route to True runs through `compute_streak`, which refuses
        on an empty ledger. Asserted over every shadow-stamped sport so adding
        a third re-checks it.
        """
        permitted_on_empty = {
            key for key in SHADOW_STAMPERS if flip_permitted(key, [])[0]
        }
        assert permitted_on_empty == set(FLIP_RULED_WITHOUT_STREAK) & set(
            SHADOW_STAMPERS
        ), (
            "an empty ledger permitted a sport that is not ruled, so something "
            "other than the D104 branch is answering yes without a streak: "
            f"permitted={sorted(permitted_on_empty)} "
            f"ruled={sorted(FLIP_RULED_WITHOUT_STREAK)}"
        )

    def test_the_nba_is_not_governed_by_the_number_that_looks_bad(self):
        """The `pct` trap, pinned.

        NBA identity `pct` reads 3.39 on the live row while `ours_covered_pct`
        reads 100.0. Only the latter governs the NBA. If someone "fixes" the
        governing map to include `pct` for the NBA, this ship silently stops
        being reachable and the failure will look like a StatPal coverage
        problem rather than a config edit.
        """
        assert GOVERNING_IDENTITY_NUMBERS[NBA] == ("ours_covered_pct",)
        assert "pct" in GOVERNING_IDENTITY_NUMBERS[NFL]


class TestTheStandingSwitchStillDidNotMove:
    """A gate exemption, not a flip."""

    def test_every_sport_is_still_espn_standing(self):
        assert set(AUTHORITY_BY_SPORT.values()) == {ESPN}
        assert authority_for(NBA) == ESPN

    def test_no_ruled_sport_was_written_into_the_standing_switch(self):
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert AUTHORITY_BY_SPORT.get(key) == ESPN, (
                f"{key} was written into the standing switch as well as the "
                "gate; that is the STANDING-STATPAL path, which is not a "
                "fallback and is not what D104 asked for"
            )


class TestTheServedNoteStoppedDescribingARetiredRequirement:
    """The third site where D104's scaffolding still speaks (CERT-2404 follow-up).

    `/api/admin/statpal/authority-agreement` told every reader that flipping
    "needs `flip_permitted` to say yes on seven consecutive daily gate states",
    which has been false for a ruled sport since #4417 landed. Admin-only, so
    not a reader-facing defect under standing notice 34 - but it is the sentence
    a lane reads before deciding whether the gate still binds, and two sessions
    have now had to re-derive that it does not.

    The note is built per sport, so it cannot go stale again as sports join the
    set: it is derived from `FLIP_RULED_WITHOUT_STREAK`, not restated.
    """

    @pytest.mark.parametrize("sport", sorted(FLIP_RULED_WITHOUT_STREAK))
    def test_a_ruled_sports_note_says_the_wait_is_retired(self, sport):
        from app.routes.admin_providers import _authority_note

        note = _authority_note(sport)
        assert "D104" in note, note
        assert "seven consecutive daily gate states" not in note, (
            f"{sport} is ruled; its note still describes the retired wait: {note}"
        )

    def test_an_unruled_sports_note_still_describes_the_gate(self):
        from app.routes.admin_providers import _authority_note

        note = _authority_note(NHL)
        assert NHL not in FLIP_RULED_WITHOUT_STREAK
        assert "seven consecutive daily gate states" in note, note
