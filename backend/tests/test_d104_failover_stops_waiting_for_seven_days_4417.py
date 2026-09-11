"""D104 = A4: the ESPN→StatPal failover stops waiting for seven certification days. #4417.

Alex, 2026-09-09 10:20am PT, relayed to the authority lane by Fable-5:

    "I'm not at all worried about StatPal having schedule coverage for top-tier
    leagues. We don't need 7 days of proof. If there's anything missing, it was
    a failure by us to fetch it correctly."

So StatPal becomes the backup source of record for the top-tier leagues under
D50's design — ESPN first, StatPal fallback, a game exists if either lists it —
with **no certification days**. Football first (Thursday's kickoff), the rest one
release each.

WHAT THIS FILE IS PINNING, AND WHAT IT DELIBERATELY IS NOT
----------------------------------------------------------
D104 removed **proof days**. It did not remove **existence**. `flip_permitted`
has six refusal branches and only one of them is a wait:

    1. the key is a MEASUREMENT POPULATION, not a sport key   -> still refuses
    2. no shadow stamper, so no id join to flip onto          -> still refuses
    3. no working StatPal discovery pass                      -> still refuses
    4. no governing identity number (D63)                     -> MOVED, see below
    5. no ledger at all — not measured                        -> see below
    6. a real streak shorter than seven days                  -> D104 RETIRES THIS

Branches 1-3 are "there is nothing here to flip TO", which is a different
sentence from "come back in a week", and a ruling about certification days has
no business touching them. They are unchanged and still asked above the ruling.

AMENDED BY D113 (Alex, 2026-09-10, #4436): branch 4 is NOT one of those, and
this file used to say it was. `baseball_mlb` was cited here as "the live proof
that this matters" — a top-tier league Alex named, refusing on (4). It was the
wrong example. MLB has a shadow stamper and a working hourly discovery pass, so
it was always able to fail over; the governing number only decides which
published percentage advances a STREAK, and `authority_failover` never reads it
at all. So (4) refused a ruled sport on a fact that decided nothing about the
flip, and Alex moved it below the ruling, where it is now the first of the
streak questions and still refuses every UNRULED sport that lacks one.

What survived intact is the thing the example was reaching for: **a ruling
cannot buy backup data that does not exist.** That is branches 2 and 3, it is
Alex's stated condition on D113, and it is pinned on a CONSTRUCTED sport in
`test_mlb_fails_over_and_the_ruling_still_cannot_skip_the_structure_4436.py`
rather than on whichever real sport happens to be unruled this week.

The rest of the module — `compute_streak`, `fold_day`, the daily ledger and
everything published on `/api/admin/statpal/authority-agreement` — is untouched
on purpose. Alex kept it explicitly: "The daily ledger keeps running as a
MONITOR." A gate that stops consulting the streak must not stop the streak.
"""

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DISCOVERY_SCHEDULED_SPORTS,
    ESPN,
    FLIP_EVIDENCE,
    FLIP_RULED_WITHOUT_STREAK,
    MEASUREMENT_POPULATION_SCOPES,
    SHADOW_STAMPERS,
    authority_for,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS
from tests.authority_specimens import register_specimen

NFL = "americanfootball_nfl"


def _days(n, state="MEETS"):
    """`n` CONSECUTIVE ledger days ending 2026-09-30, all in one state.

    Two fields, because those are the two the walk reads. Consecutive because
    `compute_streak` stops at a day with no stored row, so dated entries with
    gaps are not a streak of `n` — a helper that produced one would make every
    assertion below quietly weaker, which is how the first cut of this file
    managed to red four control tests that were describing real behaviour
    correctly.

    Hand-built rather than driven through `authority_streak.day_entry` for the
    reason `test_authority_flip_switch` gives: that function is the producer and
    `compute_streak` is the consumer, and one helper feeding both ends would hide
    a disagreement between them instead of surfacing it.
    """
    from datetime import date, timedelta

    end = date(2026, 9, 30)
    return [
        {"day": (end - timedelta(days=n - 1 - i)).isoformat(), "state": state}
        for i in range(n)
    ]


class TestFootballFlipsWithoutSevenDays:
    """The ship. NFL is permitted on a ledger that has not reached seven."""

    @pytest.mark.parametrize("n", [0, 1, 5, 6])
    def test_nfl_is_permitted_on_a_streak_shorter_than_seven(self, n):
        """The exact state NFL was in when Alex ruled: 5 of 7 and climbing.

        Parameterised down to 0 because D104's sentence is "we don't need 7 days
        of proof", not "we need fewer days of proof" — a rule that still refused
        at 4/7 would be the same rule with a smaller number, which is what Alex
        declined to give.
        """
        assert n < REQUIRED_STREAK_DAYS  # or this test proves nothing
        permitted, why = flip_permitted(NFL, _days(n))
        assert permitted is True, why
        assert "D104" in why, (
            "the permission must say WHY it did not need seven days, or the next "
            f"reader reconstructs a streak rule that is not there: {why}"
        )

    def test_the_why_does_not_claim_a_streak_it_did_not_have(self):
        """A permission granted on 2 days must not print a seven-day sentence.

        The pre-D104 `True` branch reads "has 7/7 consecutive days at or above
        99.5%". Reusing it here would hand an operator a receipt for evidence
        that was never collected — the failure gotcha #53 is the standing version
        of, applied to a permission instead of an absence.
        """
        _, why = flip_permitted(NFL, _days(2))
        assert f"{REQUIRED_STREAK_DAYS}/{REQUIRED_STREAK_DAYS}" not in why
        assert "consecutive days at or above" not in why

    def test_an_empty_ledger_still_permits_and_still_says_it_is_empty(self):
        """"Not measured" is not a refusal any more, but it is still a fact.

        Before D104 this branch refused with "no agreement ledger yet — not
        measured, which is not a streak of zero" (gotcha #53). The refusal goes;
        the honesty must not. An operator reading `serving: statpal` on a sport
        with no ledger should be able to see that from the receipt.
        """
        permitted, why = flip_permitted(NFL, [])
        assert permitted is True, why
        assert "D104" in why


class TestTheStructuralRefusalsSurviveTheRuling:
    """D104 removed proof days. Everything else still refuses."""

    def test_an_unruled_sport_with_no_governing_number_still_refuses(
        self, monkeypatch
    ):
        """D63 survives D113 — for an UNRULED sport, which is all it ever meant.

        This test used to be `test_mlb_still_refuses_on_its_missing_governing_
        number`, and it carried the instruction that decided how to rewrite it:

            "MLB acquired a governing number; this test's premise is gone and it
             must be rewritten against whatever now refuses MLB, not deleted"

        MLB did not acquire a governing number — Alex moved the question below
        the ruling (D113) — but the instruction still applies, and "whatever now
        refuses MLB" is nothing, because being ruled is the answer. So the test
        follows the branch instead of the sport: D63 is asserted where it still
        binds, on a sport that is not ruled.

        Built rather than borrowed, because after #4436 there is no real sport
        left in this state — every shadow-stamped, discovery-scheduled sport is
        either governed (NFL/NBA/NHL) or ruled (MLB). Borrowing the next one
        would put this test back on the clock of the next release.
        """
        key = register_specimen(
            monkeypatch, "unittest_unruled_ungoverned", governing=None, ruled=False
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False, why
        assert "governing identity number" in why
        assert "D63" in why

    def test_the_ruling_is_what_carries_mlb_past_that_branch(self, monkeypatch):
        """The other arm, so the test above cannot pass for the wrong reason.

        Same specimen, same missing governing number, `ruled=True`. If this were
        also refused, D113 would not have shipped; if the test above passed while
        this one did too, the specimen would be refusing on something other than
        D63 and neither assertion would mean what it says.
        """
        key = register_specimen(
            monkeypatch, "unittest_ruled_ungoverned", governing=None, ruled=True
        )
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is True, why
        assert "D63" in why, (
            "a ruled sport permitted past an unruled governing number must "
            f"disclose that the question is still open (D113): {why}"
        )

    def test_a_measurement_population_still_refuses(self):
        for population in ("tennis_singles", "soccer"):
            assert population in MEASUREMENT_POPULATION_SCOPES
            permitted, why = flip_permitted(population, _days(30))
            assert permitted is False, f"{population}: {why}"
            assert "MEASUREMENT POPULATION" in why

    def test_a_sport_with_no_shadow_stamper_still_refuses(self):
        key = "cricket_ipl"
        assert key not in SHADOW_STAMPERS
        permitted, why = flip_permitted(key, _days(30))
        assert permitted is False
        assert "no shadow stamper" in why

    def test_a_ruled_sport_with_no_discovery_pass_would_still_refuse(self):
        """Order matters: the ruling is asked AFTER the structural branches.

        A key in `FLIP_RULED_WITHOUT_STREAK` that had no working discovery pass
        must still refuse — otherwise the ruling becomes a way to skip branch 3,
        whose own comment says "fix the path, do not wait for days". Nothing in
        the shipped set is in that state today, so this is asserted on the
        ordering rather than on a specimen.

        The governing number is NOT asserted here any more: D113 moved it below
        the ruling, so a ruled sport lacking one is permitted BY DESIGN and this
        loop would fail on `baseball_mlb` for the correct behaviour. What the
        loop still asserts is exactly Alex's condition on D113 — every ruled
        sport really does have the backup data (a stamper and a working
        discovery pass) that the ruling is not allowed to conjure.
        """
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert key in SHADOW_STAMPERS, key
            assert key in DISCOVERY_SCHEDULED_SPORTS, key
            assert discovery_state(key)[0] == "SCHEDULED", key


class TestOnlyFootballShipsOnThisIssue:
    """Alex: "Flip football first, then the rest in one release each".

    AMENDED BY #4493 (the NBA's release). The specimen moved; the principle did
    not. This class asserts that the ruled set contains exactly the sports that
    have actually been graded, one release at a time — it never asserted that
    football would be alone forever, and rewriting it that way would have made
    every later release edit a test named for #4417.

    So `basketball_nba` moves from the still-waiting parametrize to the shipped
    set, and `icehockey_nhl` stays behind as the control. This is the same
    resolution the unreadable-ledger test above took when #4443 landed: the
    specimen moves, the test stays.
    """

    def test_the_ruled_set_is_exactly_what_has_shipped(self):
        assert FLIP_RULED_WITHOUT_STREAK == frozenset(
            {NFL, "basketball_nba", "baseball_mlb"}
        ), (
            "the ruled set must equal the sports that have been graded: "
            "football on #4417, the NBA on #4493, MLB on #4436 under D113. NHL "
            "is one release of its own under #2867; adding it lands two flips "
            "under a cert that graded one"
        )

    def test_football_is_still_ruled(self):
        """This issue's own ship, which a later release must not undo."""
        assert NFL in FLIP_RULED_WITHOUT_STREAK
        permitted, why = flip_permitted(NFL, _days(5))
        assert permitted is True, why

    @pytest.mark.parametrize("sport", ["icehockey_nhl"])
    def test_the_sports_that_have_not_shipped_still_wait(self, sport):
        assert sport not in FLIP_RULED_WITHOUT_STREAK
        permitted, why = flip_permitted(sport, _days(5))
        assert permitted is False, why
        assert f"5/{REQUIRED_STREAK_DAYS}" in why


class TestTheSwitchItselfDidNotMove:
    """A gate exemption is not a flip — still the claim, re-derived.

    Alex asked for "ESPN first, StatPal fallback". `AUTHORITY_BY_SPORT` is the
    *standing* switch, and `authority_failover.decide` is explicit that a sport
    set to STATPAL there "has already flipped ... this pass's silence from ESPN
    is not an outage for it" — a different behaviour, reached by a different
    question, and one that on a pass where ESPN DOES answer changes nothing at
    all. Writing STATPAL there would not have delivered what D104 asked for, so
    this ship must be visible as having not touched it.

    **NFL LEFT THIS STATE ON 2026-09-11, and not by this ship (#4954).** It was
    flipped by a separate, evidenced, attended edit under D50's second half — a
    YOUR-TURN entry Alex saw, fired on silence. That is the proof that the two
    steps are two, not a hole in the claim below, and the tests here are
    re-derived rather than re-pointed at the new value: the proposition is
    MEMBERSHIP OF THE RULED SET DOES NOT WRITE THE STANDING SWITCH, and it is
    observable on every ruled sport no ship of its own has flipped.

    Re-pointing them (`== STATPAL` for NFL) would have been one character and
    would have deleted the only proof that D104's ship kept its hands off the
    switch. The anti-vacuity assert below is what stops the same deletion
    happening silently on the day the last ruled sport flips.
    """

    def test_the_ruled_set_is_not_the_standing_switch(self):
        unflipped = sorted(k for k in FLIP_RULED_WITHOUT_STREAK if k not in FLIP_EVIDENCE)
        assert unflipped, (
            "every ruled sport now carries FLIP_EVIDENCE, so this test can no "
            "longer observe the distinction it exists to pin. Re-derive it on "
            "a constructed sport (tests/authority_specimens) — do not delete it"
        )
        for key in unflipped:
            assert AUTHORITY_BY_SPORT.get(key) == ESPN, (
                f"{key} was written into the standing switch as well as the "
                "gate, and carries no FLIP_EVIDENCE; that is the "
                "STANDING-STATPAL path arriving by membership, which is not a "
                "fallback and is not what D104 asked for"
            )

    def test_the_one_sport_that_did_leave_espn_left_by_an_evidenced_ship(self):
        """Whatever moved is accounted for — a flip never arrives anonymously.

        This is the other half of the same guard. The test above proves the
        ruling did not write the switch; this one proves that what DID write it
        brought D50's receipts, so "the ruled set leaked into the map" and "a
        ship flipped a sport on purpose" can never be confused for each other.
        """
        for key, authority in sorted(AUTHORITY_BY_SPORT.items()):
            if authority == ESPN:
                continue
            evidence = FLIP_EVIDENCE.get(key)
            assert evidence, f"{key} left ESPN with no FLIP_EVIDENCE entry"
            assert evidence.get("your_turn"), (
                f"{key} left ESPN naming no YOUR-TURN entry; D50's second half "
                "is not optional"
            )
        assert authority_for(NFL) != ESPN and FLIP_EVIDENCE.get(NFL), (
            "NFL is this file's subject and #4954 flipped it on 2026-09-11 — "
            "if it is back on ESPN the rollback happened, and the docstring "
            "above needs rewriting before this test is made to pass again"
        )


class TestTheMonitorSurvives:
    """"The daily ledger keeps running as a MONITOR" — Alex, same ruling."""

    def test_the_streak_is_still_computed_for_a_ruled_sport(self):
        """A gate that stops CONSULTING the streak must not stop COMPUTING it.

        The cheapest wrong implementation of D104 is an early return above
        `compute_streak`, which would leave the ledger unread and every
        downstream monitor reading a sport that had quietly stopped being
        measured. The permission's own `why` has to carry the streak it did not
        need, which is only possible if it still walked it.
        """
        from app.utils.authority_streak import compute_streak

        days = _days(5)
        assert compute_streak(days)["days"] == 5
        _, why = flip_permitted(NFL, days)
        assert "5" in why, (
            "the permission does not report the streak it ignored, so an "
            f"operator cannot tell the monitor is still running: {why}"
        )
