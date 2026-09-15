"""#6432 — ESPN lists two "Sydney Swans" and we kept the wrong one.

`site.api.espn.com/.../afl/teams` returns 19 records for 18 clubs. Two of them
answer to the display name "Sydney Swans":

    id  4 | Sydney Swans | SYD  | syd.png     ← the club; every game feed uses it
    id 19 | Sydney Swans | GCFC | gcfc.png    ← Gold Coast's media, listed last

`_backfill_team_logos` built its lookup as a plain dict keyed on the lowercased
name, so the later record won, our Sydney Swans row was stamped `espn_id = 19`
and given `gcfc.png`, and the Sydney card in AFL finals week wore Gold Coast's
badge. The name-based validator in `_cleanup_bad_espn_matches` cannot see it:
the *name* on the corrupt record is right. The abbreviation is the only witness
the record carries against itself.
"""

import pytest

from app.services.espn_api import ESPNTeam
from app.tasks.espn_sync import (
    build_espn_name_lookup,
    consistent_same_name_sibling,
    espn_abbreviation_corresponds,
)


def _team(espn_id, display_name, abbreviation, logo=None, short_name=None):
    return ESPNTeam(
        espn_id=espn_id,
        name=display_name,
        abbreviation=abbreviation,
        display_name=display_name,
        short_name=short_name,
        nickname=None,
        primary_color=None,
        secondary_color=None,
        logo_url=logo or f"https://a.espncdn.com/i/teamlogos/afl/500/{(abbreviation or 'x').lower()}.png",
        logo_url_dark=None,
        record=None,
    )


SYDNEY = _team("4", "Sydney Swans", "SYD")
GOLD_COAST_UNDER_SYDNEYS_NAME = _team("19", "Sydney Swans", "GCFC")


#: The AFL list as the venue served it 2026-09-15 21:40Z, read from
#: `site.api.espn.com/apis/site/v2/sports/australian-football/afl/teams`.
#: 19 records, 18 clubs. Kept verbatim so the rule below is measured against a
#: real roster and not against three hand-picked examples.
REAL_AFL_ROSTER = [
    ("15", "Adelaide Crows", "ADEL"),
    ("11", "Brisbane Lions", "BL"),
    ("9", "Carlton", "CARL"),
    ("17", "Collingwood", "COLL"),
    ("16", "Essendon", "ESS"),
    ("1", "Fremantle", "FRE"),
    ("8", "GWS GIANTS", "GWS"),
    ("14", "Geelong Cats", "GEEL"),
    ("10", "Gold Coast SUNS", "SUNS"),
    ("13", "Hawthorn", "HAW"),
    ("2", "Melbourne", "MELB"),
    ("5", "North Melbourne", "NMFC"),
    ("7", "Port Adelaide", "PORT"),
    ("12", "Richmond", "RICH"),
    ("18", "St Kilda", "STK"),
    ("4", "Sydney Swans", "SYD"),
    ("19", "Sydney Swans", "GCFC"),
    ("3", "West Coast Eagles", "WCE"),
    ("6", "Western Bulldogs", "WB"),
]


class TestAnAbbreviationIsReadAgainstItsOwnName:
    def test_the_real_roster_accuses_exactly_one_record(self):
        """18 clubs correspond; the 19th record is the only one that does not.

        Anti-vacuity is the 18: a rule that called everything inconsistent
        would "find" the defect and be useless as a tiebreak.
        """
        accused = [
            (espn_id, name, abbr)
            for espn_id, name, abbr in REAL_AFL_ROSTER
            if not espn_abbreviation_corresponds(abbr, name)
        ]
        assert accused == [("19", "Sydney Swans", "GCFC")], (
            "the abbreviation rule must accuse ESPN's corrupt duplicate and "
            f"nothing else; it accused {accused}"
        )
        corresponding = [
            abbr for _, name, abbr in REAL_AFL_ROSTER
            if espn_abbreviation_corresponds(abbr, name)
        ]
        assert len(corresponding) == 18

    @pytest.mark.parametrize(
        "abbreviation,name",
        [
            ("SYD", "Sydney Swans"),      # letters in order
            ("STK", "St Kilda"),          # letters in order, across two words
            ("NMFC", "North Melbourne"),  # initials, plus letters the name omits
            ("WCE", "West Coast Eagles"),  # pure initials
            ("SUNS", "Gold Coast SUNS"),   # letters in order, late in the name
        ],
    )
    def test_the_ways_a_real_club_builds_an_abbreviation_are_all_accepted(
        self, abbreviation, name
    ):
        assert espn_abbreviation_corresponds(abbreviation, name)

    @pytest.mark.parametrize(
        "abbreviation,name",
        [
            ("GCFC", "Sydney Swans"),
            ("MIA", "Atlanta United FC"),
            (None, "Sydney Swans"),
            ("", "Sydney Swans"),
        ],
    )
    def test_another_clubs_badge_does_not_correspond(self, abbreviation, name):
        assert not espn_abbreviation_corresponds(abbreviation, name)


class TestANameTwoRecordsAnswerToIsNotResolvedByListOrder:
    def test_the_self_consistent_record_wins_whatever_order_espn_lists_them(self):
        for roster in (
            [SYDNEY, GOLD_COAST_UNDER_SYDNEYS_NAME],
            [GOLD_COAST_UNDER_SYDNEYS_NAME, SYDNEY],
        ):
            _by_id, by_name, _candidates, collisions = build_espn_name_lookup(roster)
            assert by_name["sydney swans"].espn_id == "4", (
                "the lookup kept whichever record ESPN listed last — that is "
                "the #6432 defect"
            )
            assert collisions["resolved"] == 1

    def test_a_collision_no_abbreviation_can_settle_is_refused_not_guessed(self):
        roster = [
            _team("100", "Springfield Atoms", "SA"),
            _team("101", "Springfield Atoms", "SPRA"),
        ]
        _by_id, by_name, _candidates, collisions = build_espn_name_lookup(roster)
        assert "springfield atoms" not in by_name, (
            "two equally plausible records must leave the name unresolved "
            "rather than let list order pick one"
        )
        assert collisions["refused"] == 1

    def test_an_uncontested_name_still_resolves(self):
        roster = [_team("13", "Hawthorn", "HAW"), SYDNEY]
        _by_id, by_name, _candidates, collisions = build_espn_name_lookup(roster)
        assert by_name["hawthorn"].espn_id == "13"
        assert by_name["sydney swans"].espn_id == "4"
        assert collisions == {"resolved": 0, "refused": 0}

    def test_a_short_display_name_is_still_skipped(self):
        """The len>=4 floor is pre-existing behaviour and must survive."""
        roster = [_team("77", "UNI", "UNI")]
        _by_id, by_name, _candidates, _collisions = build_espn_name_lookup(roster)
        assert by_name == {}


class TestAPoisonedAnchorNamesItsOwnReplacement:
    def test_the_corrupt_record_points_at_the_club(self):
        _by_id, _by_name, candidates, _collisions = build_espn_name_lookup(
            [SYDNEY, GOLD_COAST_UNDER_SYDNEYS_NAME]
        )
        sibling = consistent_same_name_sibling(
            GOLD_COAST_UNDER_SYDNEYS_NAME, candidates
        )
        assert sibling is not None and sibling.espn_id == "4"

    def test_a_healthy_anchor_is_left_alone(self):
        _by_id, _by_name, candidates, _collisions = build_espn_name_lookup(
            [SYDNEY, GOLD_COAST_UNDER_SYDNEYS_NAME, _team("13", "Hawthorn", "HAW")]
        )
        assert consistent_same_name_sibling(SYDNEY, candidates) is None
        assert consistent_same_name_sibling(
            _team("13", "Hawthorn", "HAW"), candidates
        ) is None

    def test_an_inconsistent_record_with_no_sibling_is_not_repointed(self):
        """Refuse, never guess: an odd abbreviation alone is not evidence."""
        lonely = _team("200", "Atlanta United FC", "MIA")
        _by_id, _by_name, candidates, _collisions = build_espn_name_lookup([lonely])
        assert consistent_same_name_sibling(lonely, candidates) is None
