"""Q457 — a three-letter school or club reaches its own event row.

Kalshi ships college and club teams under their acronym: "UAB vs Illinois",
"Clemson vs LSU", "VMI vs Virginia Tech". Our events store the full row —
"UAB Blazers", "LSU Tigers", "VMI Keydets". ``_fuzzy_team_match`` refused every
one of them, because its containment test is gated on BOTH names being at least
four characters and an acronym is three. ``_score_candidates`` requires BOTH
teams to fuzzy-match, so one unmatched acronym unlinked the whole game — the
moneyline, the spread, the total, and every half and quarter prop with it.

Measured on production 2026-08-30 over all 5,110 unlinked open Kalshi
"X vs Y" markets: 172 carry a team name under four characters, 43 of those have
a live candidate event, and exactly ONE of the 43 linked. With the acronym rule
it is 23 — six upcoming games (UAB/Illinois, Bethune-Cookman/UCF, LIU/Kansas,
Clemson/LSU, VMI/Virginia Tech, Utah Tech/BYU), 0 changed bindings, 0 lost.

The guard is written for the CLASS, not the six specimens:

* the four-character floor's own reason ("LA" must not reach
  "Los Angeles Lakers") still holds, and is asserted here rather than assumed;
* a three-character SUBSTRING that is not a whole word must still be refused —
  this is what makes the change "whole-word acronym" and not "floor lowered to
  three", and it is the property a careless re-implementation would break;
* every entry in ``_MATCH_STOPWORDS`` is two characters, so a bare club
  designator can never bind two different clubs — asserted against the real
  stopword set, so adding a three-character stopword fails this file.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.name_normalization import _MATCH_STOPWORDS, normalize_name
from app.utils.prediction_market_matching import (
    _ACRONYM_MIN_LEN,
    _fuzzy_team_match,
    _writes_token_as_an_acronym,
    extract_matchup,
)
from app.tasks.prediction_market_matching import (
    _score_candidates,
    ticker_start_utc,
)
from app.utils.prediction_market_matching import extract_game_date_from_ticker


# The six games the fix makes reachable, as measured on production 2026-08-30.
# (market name, kalshi ticker, event home, event away)
MEASURED_GAMES = [
    ("UAB vs Illinois", "KXNCAAFGAME-26SEP03UABILL",
     "Illinois Fighting Illini", "UAB Blazers"),
    ("Bethune-Cookman vs UCF", "KXNCAAFGAME-26SEP03COOKUCF",
     "UCF Knights", "Bethune-Cookman Wildcats"),
    ("LIU vs Kansas", "KXNCAAFGAME-26SEP04LIUKU",
     "Kansas Jayhawks", "LIU Sharks"),
    ("Clemson vs LSU", "KXNCAAFGAME-26SEP05CLEMLSU",
     "LSU Tigers", "Clemson Tigers"),
    ("VMI vs Virginia Tech", "KXNCAAFGAME-26SEP05VMIVT",
     "Virginia Tech Hokies", "VMI Keydets"),
    ("Utah Tech vs BYU", "KXNCAAFGAME-26SEP05UTUBYU",
     "BYU Cougars", "Utah Tech Trailblazers"),
]

# Every three-letter acronym the production corpus actually ships, paired with
# the event row it must reach. Not a wishlist — each was read off a live row.
CORPUS_ACRONYMS = [
    ("TCU", "TCU Horned Frogs"),
    ("USC", "USC Trojans"),
    ("UAB", "UAB Blazers"),
    ("UCF", "UCF Knights"),
    ("LSU", "LSU Tigers"),
    ("LIU", "LIU Sharks"),
    ("BYU", "BYU Cougars"),
    ("SMU", "SMU Mustangs"),
    ("VMI", "VMI Keydets"),
    ("PSG", "PSG Paris Saint-Germain"),
    ("QPR", "QPR Queens Park Rangers"),
    ("AIK", "AIK Stockholm"),
]


class TestAcronymReachesItsOwnRow:
    """The bug: a three-letter school never matched its own event."""

    @pytest.mark.parametrize("acronym,event_team", CORPUS_ACRONYMS)
    def test_acronym_matches_its_own_event_row(self, acronym, event_team):
        assert _fuzzy_team_match(acronym, event_team), (
            f"{acronym!r} must reach {event_team!r} — it is a whole word of it"
        )

    @pytest.mark.parametrize("acronym,event_team", CORPUS_ACRONYMS)
    def test_match_is_symmetric(self, acronym, event_team):
        """The event row may arrive on either side of the comparison."""
        assert _fuzzy_team_match(event_team, acronym)

    @pytest.mark.parametrize("market_name,ticker,home,away", MEASURED_GAMES)
    def test_both_teams_of_a_measured_game_match(
        self, market_name, ticker, home, away
    ):
        """
        _score_candidates requires BOTH teams. Asserting only the acronym would
        pass while the game stayed unlinked — that is the gate that actually
        decides, so both halves are asserted together.
        """
        matchup = extract_matchup(market_name, ticker)
        assert matchup is not None and matchup.team_b
        for team in (matchup.team_a, matchup.team_b):
            assert _fuzzy_team_match(team, home) or _fuzzy_team_match(team, away), (
                f"{team!r} matched neither {home!r} nor {away!r}"
            )


class TestTheFourCharFloorsReasonStillHolds:
    """The floor was written to stop substring accidents. It still does."""

    def test_la_does_not_reach_los_angeles_lakers(self):
        """The case named in the original comment. Two chars — still refused."""
        assert not _fuzzy_team_match("LA", "Los Angeles Lakers")

    @pytest.mark.parametrize("short,long_", [
        ("ans", "Kansas Jayhawks"),      # substring of "Kansas", not a word
        ("ill", "Illinois Fighting Illini"),
        ("tig", "LSU Tigers"),
        ("byu", "Byumba United"),        # substring of a longer single word
        ("uab", "Quabbin Rovers"),
    ])
    def test_substring_that_is_not_a_whole_word_is_refused(self, short, long_):
        """
        This is the property that distinguishes the fix from "lower the floor
        to three". A three-character run inside a longer word must NOT bind.
        """
        assert not _fuzzy_team_match(short, long_)

    @pytest.mark.parametrize("acronym,other_team", [
        ("TCU", "North Carolina Tar Heels"),
        ("UAB", "Illinois Fighting Illini"),
        ("LSU", "Clemson Tigers"),
        ("VMI", "Virginia Tech Hokies"),
        ("BYU", "Utah Tech Trailblazers"),
    ])
    def test_acronym_does_not_reach_its_opponent(self, acronym, other_team):
        """Each acronym must bind to exactly one side of its own game."""
        assert not _fuzzy_team_match(acronym, other_team)

    def test_two_different_clubs_sharing_a_designator_do_not_bind(self):
        assert not _fuzzy_team_match("AS Roma", "AS Monaco")
        assert not _fuzzy_team_match("FC Porto", "FC Basel")

    @pytest.mark.parametrize("stopword", sorted(_MATCH_STOPWORDS))
    def test_no_stopword_can_bind_two_rows(self, stopword):
        """
        Swept over the REAL stopword set, so a stopword added later is covered
        the day it is added. Not all of them are short enough to be excluded by
        the floor — "the" and "and" are three characters — which is exactly why
        _fuzzy_team_match refuses the set by name rather than trusting length.
        """
        word = normalize_name(stopword)
        assert not _fuzzy_team_match(word, f"Rovers {word} Athletic"), (
            f"{stopword!r} bound as an acronym — it carries no identity and "
            f"would join any two rows that happen to share it"
        )


class TestTheChangeIsExactlyThreeCharWholeWord:
    """
    The acronym block is unreachable for names of four characters or more: at
    that length the containment test above it has already returned True for
    every whole-word case. Pinning this keeps the change auditable as "three
    characters, whole word" rather than an open-ended relaxation.
    """

    @pytest.mark.parametrize("short,long_", [
        ("Kansas", "Kansas Jayhawks"),
        ("Clemson", "Clemson Tigers"),
        ("Purdue", "Purdue Boilermakers"),
        ("Illinois", "Illinois Fighting Illini"),
    ])
    def test_four_plus_char_names_already_matched_by_containment(
        self, short, long_
    ):
        assert _fuzzy_team_match(short, long_)

    def test_floor_is_three(self):
        assert _ACRONYM_MIN_LEN == 3

    @pytest.mark.parametrize("length", [1, 2])
    def test_nothing_below_the_floor_binds(self, length):
        """
        A generated sweep rather than a handful of examples: no name shorter
        than the floor may bind as a whole word, whatever it spells.
        """
        stub = "x" * length
        assert not _fuzzy_team_match(stub, f"{stub} United")


def _event(eid, home, away, sport_key, commence, status="scheduled"):
    return SimpleNamespace(
        id=eid,
        sport=SimpleNamespace(key=sport_key),
        home_team_name=home,
        away_team_name=away,
        commence_time=commence,
        status=status,
        external_id=f"oddsapi:{eid}",
        sport_id=7,
    )


class TestTheGameActuallyLinks:
    """
    The unit above is the gate; this is the decision. _score_candidates is what
    the matcher calls, and a fix asserted only on _fuzzy_team_match would pass
    while the market stayed unlinked (Q455's lesson: assert the route, not the
    helper).
    """

    @pytest.mark.parametrize("market_name,ticker,home,away", MEASURED_GAMES)
    def test_measured_game_binds_to_its_event(
        self, market_name, ticker, home, away
    ):
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        kickoff = datetime(2026, 9, 3, 23, 0, tzinfo=timezone.utc)
        matchup = extract_matchup(market_name, ticker)
        market = SimpleNamespace(
            external_id=ticker, name=market_name, source="kalshi",
            llm_sport_category="football", commence_time=None,
        )
        candidates = [
            _event(4242, home, away, "americanfootball_ncaaf", kickoff)
        ]
        result = _score_candidates(candidates, matchup, market, now, kickoff)
        assert result is not None, f"{market_name} did not bind to its event"
        assert result["event_id"] == 4242

    def test_a_wrong_sport_row_is_still_refused(self):
        """
        The acronym rule must not become a way around the sport gate: "UAB"
        appears in basketball too, and the ticker says football.
        """
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        kickoff = datetime(2026, 9, 3, 23, 0, tzinfo=timezone.utc)
        matchup = extract_matchup("UAB vs Illinois", "KXNCAAFGAME-26SEP03UABILL")
        market = SimpleNamespace(
            external_id="KXNCAAFGAME-26SEP03UABILL", name="UAB vs Illinois",
            source="kalshi", llm_sport_category="football", commence_time=None,
        )
        candidates = [
            _event(999, "Illinois Fighting Illini", "UAB Blazers",
                   "basketball_ncaab", kickoff)
        ]
        assert _score_candidates(candidates, matchup, market, now, kickoff) is None

    def test_the_opponents_row_is_not_taken(self):
        """
        Two games on the same day, one shared acronym: the market must bind to
        its own game and not to the other one.
        """
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        kickoff = datetime(2026, 9, 5, 23, 0, tzinfo=timezone.utc)
        matchup = extract_matchup("Clemson vs LSU", "KXNCAAFGAME-26SEP05CLEMLSU")
        market = SimpleNamespace(
            external_id="KXNCAAFGAME-26SEP05CLEMLSU", name="Clemson vs LSU",
            source="kalshi", llm_sport_category="football", commence_time=None,
        )
        decoy = _event(1, "LSU Tigers", "Florida Gators",
                       "americanfootball_ncaaf", kickoff)
        real = _event(2, "LSU Tigers", "Clemson Tigers",
                      "americanfootball_ncaaf", kickoff)
        result = _score_candidates([decoy, real], matchup, market, now, kickoff)
        assert result is not None and result["event_id"] == 2


class TestAThreeLetterSurnameIsNotAnAcronym:
    """The regression the rule above shipped with, and the case signal that ends it.

    A three-letter acronym and a three-letter surname are indistinguishable once
    normalized, so "whole word of the longer name" reads ``"gea"`` inside
    ``"arthur gea"`` exactly as it reads ``"tcu"`` inside ``"tcu horned frogs"``.
    Production has both rows for the same US Open match — ``Arthur Gea vs
    Nishesh Basavareddy`` and its surname-only twin ``Gea vs Basavareddy`` — so
    the rule as first written bound golden pair 59720702 to the twin.

    The discriminator is case, read off the RAW name before normalization folds
    it: a source writes an acronym in capitals and a surname in title case.
    """

    # Real short surnames from the tennis and golf fields, each paired with the
    # full-name row it must NOT be read as an acronym of.
    SURNAMES = [
        ("Gea", "Arthur Gea"),
        ("Kim", "Si Woo Kim"),
        ("Lee", "Min Woo Lee"),
        ("Cho", "Minsu Cho"),
        ("Nys", "Hugo Nys"),
        ("Bez", "Alexandre Bez"),
    ]

    @pytest.mark.parametrize("surname,full_name", SURNAMES)
    def test_a_surname_does_not_bind_to_its_own_full_name(self, surname, full_name):
        assert not _fuzzy_team_match(surname, full_name), (
            f"{surname!r} is a surname, not an acronym of {full_name!r}"
        )

    @pytest.mark.parametrize("surname,full_name", SURNAMES)
    def test_the_refusal_is_symmetric(self, surname, full_name):
        assert not _fuzzy_team_match(full_name, surname)

    @pytest.mark.parametrize("acronym,event_team", CORPUS_ACRONYMS)
    def test_the_case_guard_is_what_separates_them(self, acronym, event_team):
        """
        Stated as the property, not as the six specimens: every corpus acronym
        is written in capitals by its own event row, and no surname is. Delete
        the case check and the first half still passes while the second stops.
        """
        assert _writes_token_as_an_acronym(normalize_name(acronym), event_team)

    @pytest.mark.parametrize("surname,full_name", SURNAMES)
    def test_no_surname_is_written_as_an_acronym(self, surname, full_name):
        assert not _writes_token_as_an_acronym(normalize_name(surname), full_name)

    def test_a_source_that_shouts_every_name_carries_no_signal(self):
        """
        Capitalization only means "acronym" where the rest of the name is not
        capitalized. An all-caps row would otherwise make every word an acronym
        and hand the twin back. The rule fails closed: it costs a link, never
        invents one.
        """
        assert not _fuzzy_team_match("Gea", "ARTHUR GEA")
        assert not _writes_token_as_an_acronym("gea", "ARTHUR GEA")

    def test_the_evidence_is_the_long_names_casing_not_the_short_ones(self):
        """
        A market may ship its acronym in any case; the event row is what proves
        the name is an acronym. So a lowercase market string still binds.
        """
        assert _fuzzy_team_match("byu", "BYU Cougars")
        assert _fuzzy_team_match("Tcu", "TCU Horned Frogs")

    def test_the_us_open_twin_does_not_take_the_market(self):
        """
        The decision, not the helper: golden pair 59720702. Both rows exist,
        ten minutes apart, and the surname-only twin matches on
        "Basavareddy" — which is long enough for the containment test and
        always did. Only the home side decides, and _score_candidates needs
        both, so the twin must lose.
        """
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        ticker = "KXATPEXACTMATCH-26AUG27GEABAS"
        name = "Arthur Gea vs Nishesh Basavareddy: Exact Match Score"
        matchup = extract_matchup(name, ticker)
        assert matchup is not None
        market = SimpleNamespace(
            external_id=ticker, name=name, source="kalshi",
            llm_sport_category="tennis", commence_time=None,
        )
        twin = _event(15294883, "Gea", "Basavareddy", "tennis_atp",
                      datetime(2026, 8, 28, 16, 56, tzinfo=timezone.utc))
        correct = _event(15295316, "Arthur Gea", "Nishesh Basavareddy",
                         "tennis_atp",
                         datetime(2026, 8, 28, 17, 6, tzinfo=timezone.utc))
        # The scoring reference production actually has is the TICKER's date, a
        # day with no hour in it. Handing this test the true 17:06 kick-off
        # would let proximity decide and the case guard would never be
        # consulted — the test would pass with the guard deleted. It is exactly
        # because the two rows are ten minutes apart and the reference is a
        # whole day away that the names have to settle it.
        scoring_ref = ticker_start_utc(extract_game_date_from_ticker(ticker))
        result = _score_candidates(
            [twin, correct], matchup, market, now, scoring_ref
        )
        assert result is not None, "the market must still reach its own row"
        assert result["event_id"] == 15295316, (
            "the surname-only twin took the market — the acronym rule read "
            "'Gea' as an acronym of 'Arthur Gea'"
        )
