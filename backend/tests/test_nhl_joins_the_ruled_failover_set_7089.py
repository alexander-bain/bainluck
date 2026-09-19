"""D104 = A4: the NHL joins the ruled failover set. #7089, ship parent #2867.

**SHIP (pillar MATCHING): on a pass where ESPN goes dark during an NHL game the
slate and the scores keep coming — and they stop being one bad day in a monitor
away from freezing for a week.**

The fourth and last of the four releases Alex asked for:

    "Flip football first (the Thursday kickoff), then the rest in one release
    each."

Football shipped as #4417 (and flipped standing on #4954), the NBA as #4493, MLB
as #4436 under D113. This is the NHL's, and it is timed to the season: StatPal's
first NHL fixture is 2026-09-19 23:00Z.

WHAT THIS CHANGES, STATED BEFORE ANYTHING ELSE
══════════════════════════════════════════════
**Nothing, today.** `flip_permitted("icehockey_nhl", …)` returned `True` before
this ship and returns `True` after it, because the NHL's streak currently reads
15/7. A grader who measures the diff against today's ledger measures nothing,
and that is the correct reading, not a defect in the ship.

What changes is what the answer DEPENDS ON. Read from the live row at
2026-09-19T00:51:01Z (standing notice 37 — the row, never the config):

    icehockey_nhl   would_fire_if_espn_went_dark=true   FAILOVER-ESPN-DARK
    "the gate permits it: icehockey_nhl has 15/7 consecutive days at or above
     99.5%, counted over 32-82 of the 1,404-1,405 fixtures in the measured
     population"

Every other sport in `AUTHORITY_BY_SPORT` is permitted by the RULING. The NHL
alone is permitted by its STREAK, and a streak is a thing that resets:
`authority_streak` says so in its own words — *"`BELOW` — stops the walk. This
is the reset the spec means."* The walk starts at the newest day, so one day
under 99.5% takes 15 to 0 and `flip_permitted` refuses for the next seven.

So every assertion in this file that matters is made on a ledger with a BELOW
day in it. A guard written against today's ledger would pass before the config
line and after it, and would be proving nothing.

WHY THE CONTINGENCY IS NOT HYPOTHETICAL
═══════════════════════════════════════
Three measured facts, none of them a forecast:

1. A BELOW day has actually happened, on our best-covered sport. From
   `authority_streak`'s own docstring: *"NFL read 99.38 (`BELOW`) on 9/4 and
   99.69 (`MEETS`) on…"* — the sport that reads 321/321 today.
2. The NHL's governing number is scored on `both = 82` and one row breaks it.
   `ours_covered_pct` is 100.0 over 82; a single `ours_only` row makes it
   81/82 = 98.8%, which is BELOW. The population that produces exactly such a
   row is already tracked as
   `ours_only_in_span_composition.second_row_for_a_matched_game` — the twins of
   #3093/#3463 — and reads 0 for the NHL only because its season has not
   started. (#3071's open Question A, seen from the other side.)
3. That denominator is about to grow ~17×: StatPal lists 1,405 NHL fixtures to
   2027-04-10 and we hold 82. Every new game is a new chance for a twin.

`TestTheRefusalThisShipRemovesIsReachable` pins fact 2 as arithmetic rather than
as prose, so the motive cannot rot into a story.

WHAT HAPPENS WHEN IT DOES RESET, AND WHY THAT IS THE READER'S PROBLEM
══════════════════════════════════════════════════════════════════════
`authority_failover.decide` turns a shut gate into `NO-FAILOVER-NOT-GATED` with
`serving=ESPN, failed_over=False`. On a pass where ESPN is the thing that went
dark, "keep using ESPN" writes nothing: score, clock and slate freeze. That is
the blank the three prior releases were ruled to prevent, and it is what the NHL
is one monitor blip away from for its whole season.

WHAT THIS SHIP IS NOT
═════════════════════
It is not a flip. `icehockey_nhl` keeps `ESPN` in `AUTHORITY_BY_SPORT` and gets
no `FLIP_EVIDENCE` entry, exactly as the NBA and MLB did — *permission is not
the flip*. The standing flip is gated on D50's second half (a YOUR-TURN entry
Alex has seen) and is not part of this issue.
`TestTheStandingSwitchStillDidNotMove` keeps the two apart.

THE POOL THIS RELEASE EMPTIES
═════════════════════════════
`icehockey_nhl` was the last real fully-structural unruled sport, and five guard
files borrowed it as their negative control. #4564 built
`tests/authority_specimens.py` for this exact moment (*"the state
`icehockey_nhl` is the last of"*) and #4588 named this release as the one that
consumes it. Those controls move to the CONSTRUCTED specimen in this ship.
There is now no real sport left to borrow, so a sixth release has nothing to
consume — which was the point of building the specimen.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DISCOVERY_SCHEDULED_SPORTS,
    ESPN,
    FLIP_EVIDENCE,
    FLIP_RULED_WITHOUT_STREAK,
    GOVERNING_IDENTITY_NUMBERS,
    SHADOW_STAMPERS,
    authority_for,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS, compute_streak
from tests.authority_specimens import register_specimen

NFL = "americanfootball_nfl"
NBA = "basketball_nba"
NHL = "icehockey_nhl"
MLB = "baseball_mlb"


def _days(n, state="MEETS"):
    """`n` CONSECUTIVE ledger days ending 2026-09-30, all in one state.

    A third copy of the shape in #4417's and #4493's files, and deliberately a
    copy rather than an import for the reason #4493 gave: these files pin
    different releases, and a shared fixture retuned for one would silently
    retune the others' controls.

    The key is `day`, not `date` — a ledger keyed on `date` reads as ABSENT and
    refuses with "has no agreement ledger yet", which is still `False` and still
    green if a control only checks the verdict. Every control here asserts the
    refusal REASON.
    """
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    return [
        {"day": (end - timedelta(days=n - 1 - i)).isoformat(), "state": state}
        for i in range(n)
    ]


def _days_broken_today(n=15):
    """`n` days, all MEETS except the NEWEST, which is BELOW.

    The state the whole ship is about. `compute_streak` starts its walk at
    `ordered[-1]` and `GATE_BELOW` breaks out immediately, so this ledger scores
    a streak of **0** however long its healthy tail is — which is precisely why
    a 15-day run is no protection at all.
    """
    days = _days(n)
    days[-1]["state"] = "BELOW"
    return days


class TestTheNhlFailsOverAfterItsStreakBreaks:
    """The ship itself, asserted on the state that distinguishes before/after."""

    def test_the_nhl_is_in_the_ruled_set(self):
        assert NHL in FLIP_RULED_WITHOUT_STREAK, (
            "#7089 is the NHL's release under D104; the ruled set is the one "
            "line that delivers it"
        )

    def test_a_streak_broken_today_no_longer_refuses_the_nhl(self):
        """RED before the config line. This is the ship in one assertion.

        15 healthy days with one BELOW day on top of them. Before #7089 this
        refused with "0/7"; after it, the ruling answers.
        """
        permitted, why = flip_permitted(NHL, _days_broken_today())
        assert permitted is True, why
        assert "D104" in why, (
            f"the NHL was permitted by something other than the ruling: {why}"
        )

    def test_a_short_streak_no_longer_refuses_the_nhl(self):
        """The state the NBA's row was in when #4493 shipped: 5 of 7 days."""
        permitted, why = flip_permitted(NHL, _days(5))
        assert permitted is True, why

    def test_an_empty_ledger_no_longer_refuses_the_nhl(self):
        """#4443's case, reaching the fourth sport.

        `_decide_failovers` hands `flip_permitted` an empty list when the
        monitor read FAILS. A ruled sport must survive that: an outage in the
        thing that watches the outage must not become an outage.
        """
        permitted, why = flip_permitted(NHL, [])
        assert permitted is True, why

    def test_the_ruling_reports_what_the_monitor_still_says(self):
        """D104 kept the ledger as a MONITOR; the permission must still quote it.

        A `True` that stops mentioning the streak is how the monitor quietly
        stops being read at all.
        """
        _, why = flip_permitted(NHL, _days(15))
        assert "15 day" in why, why


class TestTheRefusalThisShipRemovesIsReachable:
    """Fact 2 of the motive, as arithmetic rather than as prose.

    A ship whose value is contingent has to prove the contingency can occur, or
    it is architecture-only under the RIDER RULE. The claim is narrow and
    checkable: on the NHL's live denominator, ONE `ours_only` row scores BELOW.
    """

    def test_one_extra_row_of_ours_puts_the_live_denominator_under_the_bar(self):
        from app.utils.authority_agreement import FLIP_BAR_PCT

        both = 82  # live row, 2026-09-19T00:51:01Z
        assert round(100.0 * both / both, 2) >= FLIP_BAR_PCT
        with_one_twin = round(100.0 * both / (both + 1), 2)
        assert with_one_twin < FLIP_BAR_PCT, (
            "the premise of #7089 is that the NHL's governing number can be "
            f"broken by a single row; on both={both} it reads {with_one_twin}%"
        )

    def test_a_below_day_really_does_zero_a_fifteen_day_run(self):
        """The reset, measured on `compute_streak` rather than quoted from it."""
        healthy = compute_streak(_days(15))
        assert healthy["days"] == 15 and healthy["meets_flip_gate"] is True
        broken = compute_streak(_days_broken_today())
        assert broken["days"] == 0, broken
        assert broken["meets_flip_gate"] is False, broken
        assert broken["stopped_by"]["kind"] == "below", broken["stopped_by"]

    def test_an_unruled_sport_with_that_ledger_is_refused(self, monkeypatch):
        """What the NHL would have got, on a sport that is still in that state.

        The constructed specimen, not a borrowed sport — after this release
        there is no real one left, which is the state #4588 predicted.
        """
        key = register_specimen(monkeypatch, "unittest_nhl_before_7089")
        permitted, why = flip_permitted(key, _days_broken_today())
        assert permitted is False, why
        assert f"0/{REQUIRED_STREAK_DAYS}" in why or "below" in why.lower(), why


class TestOnlyTheNhlShipsOnThisIssue:
    """Alex: "then the rest in one release each" — so the set grows by one."""

    def test_the_ruled_set_is_exactly_what_has_been_graded(self):
        assert FLIP_RULED_WITHOUT_STREAK == frozenset({NFL, NBA, MLB, NHL}), (
            "the ruled set must equal what has actually been graded: football "
            "on #4417, the NBA on #4493, MLB on #4436 under D113, the NHL on "
            "#7089. It is now every sport in AUTHORITY_BY_SPORT, so a fifth "
            "member is a NEW sport and needs its own release"
        )

    def test_the_ruled_set_is_now_every_sport_the_switch_names(self):
        """The four releases are done; say so where the next reader will look."""
        assert FLIP_RULED_WITHOUT_STREAK == frozenset(AUTHORITY_BY_SPORT), (
            "D104 named the top-tier leagues and the switch names four sports; "
            "after #7089 those are the same set"
        )


class TestTheStructuralRefusalsAreUntouched:
    """D104 exempts the WAIT. It does not reach "there is nothing to flip to"."""

    def test_a_sport_with_no_id_join_still_refuses_however_ruled_it_is(
        self, monkeypatch
    ):
        """Alex's condition on D113: "a sport with no backup data can never slip
        through". Re-proved with the ruled set at its final size."""
        key = register_specimen(
            monkeypatch, "unittest_ruled_but_unstamped_7089", stamper=False, ruled=True
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "no shadow stamper" in why, why
        assert "D104" not in why, (
            f"the ruling answered a sport with nothing to flip onto: {why}"
        )

    def test_a_sport_with_no_discovery_pass_still_refuses_however_ruled(
        self, monkeypatch
    ):
        key = register_specimen(
            monkeypatch, "unittest_ruled_but_blind_7089", discovery=False, ruled=True
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "no working StatPal discovery pass" in why, why

    def test_every_ruled_sport_still_clears_the_structural_branches(self):
        """The ruling is asked AFTER the structural branches, so a key may only
        join the set if it would have passed them anyway. Re-checked at four."""
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert key in SHADOW_STAMPERS, key
            assert key in DISCOVERY_SCHEDULED_SPORTS, key
            assert discovery_state(key)[0] == "SCHEDULED", key

    def test_an_empty_ledger_permits_only_ruled_sports(self):
        """#4443's property, re-proved now that the ruled set is the whole switch.

        Every route to `True` other than the D104 branch runs through
        `compute_streak`, which refuses on an empty ledger.
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

    def test_the_nhl_is_not_governed_by_the_number_that_looks_bad(self):
        """The `pct` trap, pinned for the fourth sport.

        NHL identity `pct` reads 5.84 on the live row while `ours_covered_pct`
        reads 100.0. Only the latter governs the NHL. If someone "fixes" the
        governing map to include `pct` here, the monitor this ship keeps alive
        goes permanently BELOW and the failure will look like a StatPal coverage
        problem rather than a config edit.
        """
        assert GOVERNING_IDENTITY_NUMBERS[NHL] == ("ours_covered_pct",)
        assert "pct" in GOVERNING_IDENTITY_NUMBERS[NFL]


class TestTheStandingSwitchStillDidNotMove:
    """A gate exemption, not a flip."""

    def test_nhl_is_still_espn_standing(self):
        assert authority_for(NHL) == ESPN
        assert NHL not in FLIP_EVIDENCE

    def test_no_ruled_sport_was_written_into_the_standing_switch(self):
        unflipped = sorted(
            k for k in FLIP_RULED_WITHOUT_STREAK if k not in FLIP_EVIDENCE
        )
        assert NHL in unflipped, (
            "the NHL is this file's subject and it has been flipped by some "
            "later ship — re-read that ship before touching this test"
        )
        for key in unflipped:
            assert AUTHORITY_BY_SPORT.get(key) == ESPN, (
                f"{key} was written into the standing switch as well as the "
                "gate, with no FLIP_EVIDENCE; that is the STANDING-STATPAL "
                "path arriving by membership, which is not a fallback and is "
                "not what D104 asked for"
            )


class TestTheServedNoteStoppedDescribingARetiredRequirement:
    """The admin prose, which is where a lane reads whether the gate still binds.

    Not reader-facing (standing notice 34), and it is the sentence the next
    session reads before deciding what the gate does — #4493 shipped this class
    because two sessions had already had to re-derive it.
    """

    @pytest.mark.parametrize("sport", sorted(FLIP_RULED_WITHOUT_STREAK))
    def test_a_ruled_sports_note_says_the_wait_is_retired(self, sport):
        from app.routes.admin_providers import _authority_note

        note = _authority_note(sport)
        assert "D104" in note, note
        assert "seven consecutive daily gate states" not in note, (
            f"{sport} is ruled; its note still describes the retired wait: {note}"
        )

    def test_an_unruled_sports_note_still_describes_the_gate(self, monkeypatch):
        """The control #4493 wrote against the NHL, now against a specimen.

        Moved rather than deleted: the branch is still real and still needs a
        guard, and after #7089 no real sport is in the state that exercises it.
        """
        from app.routes.admin_providers import _authority_note

        key = register_specimen(monkeypatch, "unittest_unruled_note_7089")
        note = _authority_note(key)
        assert "seven consecutive daily gate states" in note, note
