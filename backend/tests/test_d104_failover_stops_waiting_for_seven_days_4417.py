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
    4. no governing identity number (D63)                     -> still refuses
    5. no ledger at all — not measured                        -> see below
    6. a real streak shorter than seven days                  -> D104 RETIRES THIS

Branches 1-4 are "there is nothing here to flip TO", which is a different
sentence from "come back in a week", and a ruling about certification days has
no business touching them. `baseball_mlb` is the live proof that this matters:
it is a top-tier league Alex named, and it refuses on (4), so it must NOT flip
on this ship however loudly D104 is quoted at it.

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
    FLIP_RULED_WITHOUT_STREAK,
    GOVERNING_IDENTITY_NUMBERS,
    MEASUREMENT_POPULATION_SCOPES,
    SHADOW_STAMPERS,
    authority_for,
    discovery_state,
    flip_permitted,
)
from app.utils.authority_streak import REQUIRED_STREAK_DAYS

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

    def test_mlb_still_refuses_on_its_missing_governing_number(self):
        """The live proof that D104 is not a skeleton key.

        `baseball_mlb` is a top-tier league Alex named in the same sentence as
        football, and it refuses on D63 — no governing identity number — which is
        a ruling it needs, not a week it has to sit out. If this ever flips, the
        ruling was made by accident.
        """
        assert not GOVERNING_IDENTITY_NUMBERS.get("baseball_mlb"), (
            "MLB acquired a governing number; this test's premise is gone and it "
            "must be rewritten against whatever now refuses MLB, not deleted"
        )
        permitted, why = flip_permitted("baseball_mlb", _days(30))
        assert permitted is False
        assert "governing identity number" in why
        assert "D63" in why

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
        """
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert key in SHADOW_STAMPERS, key
            assert key in DISCOVERY_SCHEDULED_SPORTS, key
            assert GOVERNING_IDENTITY_NUMBERS.get(key), key
            assert discovery_state(key)[0] == "SCHEDULED", key


class TestOnlyFootballShipsOnThisIssue:
    """Alex: "Flip football first, then the rest in one release each"."""

    def test_the_ruled_set_is_football_alone(self):
        assert FLIP_RULED_WITHOUT_STREAK == frozenset({NFL}), (
            "NBA/NHL are one release each under #2867 and are not this ship; "
            "adding them here lands three flips under a cert that graded one"
        )

    @pytest.mark.parametrize("sport", ["basketball_nba", "icehockey_nhl"])
    def test_nba_and_nhl_still_wait(self, sport):
        permitted, why = flip_permitted(sport, _days(5))
        assert permitted is False, why
        assert f"5/{REQUIRED_STREAK_DAYS}" in why


class TestTheSwitchItselfDidNotMove:
    """The flip is a FALLBACK, not a standing source of record.

    Alex asked for "ESPN first, StatPal fallback". `AUTHORITY_BY_SPORT` is the
    *standing* switch, and `authority_failover.decide` is explicit that a sport
    set to STATPAL there "has already flipped ... this pass's silence from ESPN
    is not an outage for it" — a different behaviour, reached by a different
    question, and one that on a pass where ESPN DOES answer changes nothing at
    all. Writing STATPAL there would not have delivered what was asked, so this
    ship must be visible as having not touched it.
    """

    def test_every_sport_is_still_espn_standing(self):
        assert set(AUTHORITY_BY_SPORT.values()) == {ESPN}
        assert authority_for(NFL) == ESPN

    def test_the_ruled_set_is_not_the_standing_switch(self):
        for key in FLIP_RULED_WITHOUT_STREAK:
            assert AUTHORITY_BY_SPORT.get(key) == ESPN, (
                f"{key} was written into the standing switch as well as the "
                "gate; that is the STANDING-STATPAL path, which is not a "
                "fallback and is not what D104 asked for"
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
