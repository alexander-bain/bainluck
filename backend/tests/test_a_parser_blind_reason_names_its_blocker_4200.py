"""#4200 — a parser-blind reason must not tell an operator the work is unblocked.

`discovery_state` ended every `NO-BEAT-AND-PARSER-BLIND` reason with "both are
build steps, not a wait". That ending is correct for a parser nobody else's
ruling governs and FALSE for tennis, which is the only thing in the arm: the
`tennis_atp` vs `tennis_atp_us_open` key split is lane1's to rule on
(D39/#2693), the same file's own comment says so, and #3193's disposition says
"the tennis half is NOT claimed and should not be built as a parser ticket".

🔴 WHY THIS IS A GUARD AND NOT A COPY EDIT. The string is an operator
prescription on `/api/admin/statpal/authority-agreement`. Followed, it teaches
the parser and schedules the beat, and the beat creates a second copy of every
US Open match hourly — registry Step 1 is sport-scoped (D55/#2879) and the
tennis linker anchors under keys `STATPAL_SPORT_MAPPING` does not claim. #4155
is that failure mode already on the site from a smaller cause.

The tests below pin BOTH directions, because a repair that simply deleted the
phrase everywhere would pass a one-sided assertion while destroying the honest
ending the id-less and bare arms depend on.
"""

from __future__ import annotations

import pytest

from app.config import authority_by_sport as cfg
from app.config.authority_by_sport import (
    DISCOVERY_NO_BEAT,
    DISCOVERY_NO_BEAT_AND_NO_PARSE,
    DISCOVERY_NO_BEAT_AND_PARSER_BLIND,
    DISCOVERY_PARSER_BLOCKED_ON,
    discovery_state,
)

_NOT_A_WAIT = "not a wait"


class TestThePremise:
    """If tennis leaves either map the tests below assert nothing, so the
    premise is asserted first (memory: a guard that cannot fail is not a guard).
    """

    def test_both_tennis_keys_are_parser_blind_and_carry_a_blocker(self):
        assert set(DISCOVERY_NO_BEAT_AND_NO_PARSE) == {
            "tennis_singles",
            "tennis_doubles",
        }
        assert set(DISCOVERY_PARSER_BLOCKED_ON) == {
            "tennis_singles",
            "tennis_doubles",
        }

    def test_every_blocked_sport_is_also_parser_blind(self):
        """The blocker map is only ever read inside the parser-blind arm. An
        entry for a sport that never reaches that arm is dead text that reads
        as a live warning.
        """
        assert set(DISCOVERY_PARSER_BLOCKED_ON) <= set(DISCOVERY_NO_BEAT_AND_NO_PARSE)


class TestTheBlockedReasonStopsClaimingItIsUnblocked:
    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_PARSER_BLOCKED_ON))
    def test_the_reason_no_longer_says_not_a_wait(self, sport_key):
        """The bug, pinned from the side that shipped it."""
        _, why = discovery_state(sport_key)
        assert _NOT_A_WAIT not in why, (
            "the published reason tells an operator the tennis parser is "
            "unblocked; #3193, this file's own comment and D39/#2693 all say "
            "it is lane1's to rule on first"
        )

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_PARSER_BLOCKED_ON))
    def test_the_reason_names_the_blocker_and_says_it_waits(self, sport_key):
        _, why = discovery_state(sport_key)
        assert DISCOVERY_PARSER_BLOCKED_ON[sport_key] in why
        assert "WAITS ON" in why

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_PARSER_BLOCKED_ON))
    def test_the_blocker_names_its_owner_and_the_ruling(self, sport_key):
        """Naming a blocker without an owner is how a wait becomes permanent.
        One string assertion on purpose: the owner is the actionable half.
        """
        blocker = DISCOVERY_PARSER_BLOCKED_ON[sport_key]
        assert "lane1" in blocker
        assert "#2693" in blocker

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_PARSER_BLOCKED_ON))
    def test_the_code_is_unchanged_so_callers_branching_on_it_still_work(
        self, sport_key
    ):
        code, _ = discovery_state(sport_key)
        assert code == DISCOVERY_NO_BEAT_AND_PARSER_BLIND
        assert code != DISCOVERY_NO_BEAT


class TestTheRepairDidNotDamageTheHonestEndings:
    """🔴 THE CONTROL HALF. "not a wait" is the right ending for a parser that
    waits on nobody, and for the bare no-beat state. A repair that grepped the
    phrase out of the file would pass every test above.
    """

    def test_a_parser_blind_sport_with_no_blocker_still_reads_not_a_wait(
        self, monkeypatch
    ):
        sport_key = "korfball_synthetic"
        census = "a pinned payload parses 0 of 9 fixtures"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")
        monkeypatch.setitem(cfg.DISCOVERY_NO_BEAT_AND_NO_PARSE, sport_key, census)
        # deliberately NOT added to DISCOVERY_PARSER_BLOCKED_ON

        code, why = cfg.discovery_state(sport_key)

        assert code == DISCOVERY_NO_BEAT_AND_PARSER_BLIND
        assert census in why
        assert _NOT_A_WAIT in why, (
            "a parser nobody else's ruling governs IS just a build step; the "
            "repair must narrow the claim, not delete it"
        )
        assert "WAITS ON" not in why

    def test_the_same_sport_with_a_blocker_flips_to_the_waiting_ending(
        self, monkeypatch
    ):
        """The pair of the test above, on one sport, so the two endings are
        proven to be selected by the blocker map and by nothing else.
        """
        sport_key = "korfball_synthetic"
        census = "a pinned payload parses 0 of 9 fixtures"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")
        monkeypatch.setitem(cfg.DISCOVERY_NO_BEAT_AND_NO_PARSE, sport_key, census)
        monkeypatch.setitem(
            cfg.DISCOVERY_PARSER_BLOCKED_ON, sport_key, "the korfball id ruling"
        )

        code, why = cfg.discovery_state(sport_key)

        assert code == DISCOVERY_NO_BEAT_AND_PARSER_BLIND
        assert census in why
        assert "the korfball id ruling" in why
        assert _NOT_A_WAIT not in why

    def test_the_bare_no_beat_ending_is_untouched(self, monkeypatch):
        sport_key = "korfball_synthetic"
        monkeypatch.setitem(cfg.SHADOW_STAMPERS, sport_key, "stamp_korfball")

        code, why = cfg.discovery_state(sport_key)

        assert code == DISCOVERY_NO_BEAT
        assert _NOT_A_WAIT in why

    def test_the_id_less_ending_is_untouched(self):
        """Soccer's arm says "build step, not a wait" and that is TRUE — the
        missing id is ours to mint. #4200 must not have reached it.
        """
        _, why = discovery_state("soccer")
        assert _NOT_A_WAIT in why
        assert "WAITS ON" not in why


class TestTheCensusAndOrderingSurvive:
    """#4175's guarantees, re-asserted through the changed function rather than
    assumed — the census and the parser-before-beat ordering are what made the
    reason actionable in the first place.
    """

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_NO_BEAT_AND_NO_PARSE))
    def test_the_published_reason_still_carries_the_maps_own_census(self, sport_key):
        _, why = discovery_state(sport_key)
        assert DISCOVERY_NO_BEAT_AND_NO_PARSE[sport_key] in why

    def test_the_singles_reason_still_carries_the_measured_counts(self):
        _, why = discovery_state("tennis_singles")
        assert "0 of the 7 fixtures" in why
        assert "0 of 11" in why

    @pytest.mark.parametrize("sport_key", sorted(DISCOVERY_NO_BEAT_AND_NO_PARSE))
    def test_the_blindness_is_still_named_before_the_beat(self, sport_key):
        _, why = discovery_state(sport_key)
        census = DISCOVERY_NO_BEAT_AND_NO_PARSE[sport_key]
        assert why.index(census) < why.index("scheduling a beat")
