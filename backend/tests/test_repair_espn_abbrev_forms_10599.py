"""#10599 — a correct LIU linkage must not read as ``espn_id_drifted``.

Production 2026-10-03: ev15321991, americanfootball_ncaaf_fcs, LIU Sharks
(home) vs Mercyhurst Lakers (away), espn_id 401867910, stored 27-24. ESPN's
game for that id is Mercyhurst Lakers @ Long Island University Sharks,
24-27 away-home: the same fixture, the same date, the same final.

The rail's only failing axis was the home side: our row stores ESPN's
``abbreviation`` + ``name`` form (``LIU Sharks``) while the rail compared
only ``display_name`` (``Long Island University Sharks``). The Flow Sentinel
filed a linkage drift and prescribed the attended ``event-espn-id`` repair —
with no target proven, so nothing could be applied, and the stored score
already equals ESPN's.

The fix admits ESPN's initialism form, and ONLY through the strict predicate.
Every board below is built by ``ESPNAPIService._parse_event`` from the
retained real FCS board entry (Harvard @ Brown, 401867806). The LIU team
object is RECONSTRUCTED from the issue's display strings: the raw ESPN
competitor for 401867910 was not retained, so its ``abbreviation`` /
``location`` fields are this file's assumption, not provider proof. Every
positive has a control that must still refuse.
"""

import copy
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.services import espn_api
from app.utils.name_normalization import names_match
from scripts.repair_event_final_scores import (
    ESPN_ID_DRIFTED,
    ESPN_ID_UNRESOLVABLE,
    LINK_PROVEN,
    _espn_team_initialism_form,
    _identity_matches_team,
    classify_espn_link,
    same_fixture_games,
)

UTC = timezone.utc
FCS = "americanfootball_ncaaf_fcs"
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "espn_fcs_board_entry_harvard_at_brown_401867806.json"
)

# The real entry: 2026-09-25T23:00Z = 7pm ET on 09-25.
REAL_WHEN = datetime(2026, 9, 25, 23, 0, tzinfo=UTC)
REAL_DAY = date(2026, 9, 25)
# The LIU specimen: 2026-10-03T16:01Z.
LIU_WHEN = datetime(2026, 10, 3, 16, 1, tzinfo=UTC)
LIU_DAY = date(2026, 10, 3)

LIU = dict(id="2341", location="Long Island University", name="Sharks",
           abbreviation="LIU", displayName="Long Island University Sharks",
           shortDisplayName="LIU")
MERCYHURST = dict(id="2385", location="Mercyhurst", name="Lakers",
                  abbreviation="MERC", displayName="Mercyhurst Lakers",
                  shortDisplayName="Mercyhurst")


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())


def _parse(raw: dict):
    ee = espn_api.ESPNAPIService()._parse_event(raw)
    assert ee is not None
    return ee


def _entry(espn_id, when, *, home=None, away=None, home_score=None,
           away_score=None, drop=()):
    """The real board entry with ids, date and (optionally) teams swapped.

    ``drop`` removes team fields from BOTH competitors, so a missing field
    travels through the real parser exactly as an absent key would.
    """
    raw = copy.deepcopy(_raw())
    stamp = when.strftime("%Y-%m-%dT%H:%MZ")
    raw["id"] = espn_id
    raw["date"] = stamp
    comp = raw["competitions"][0]
    comp["id"] = espn_id
    comp["date"] = stamp
    for c in comp["competitors"]:
        side = home if c["homeAway"] == "home" else away
        if side is not None:
            c["id"] = side["id"]
            c["team"].update(side)
        score = home_score if c["homeAway"] == "home" else away_score
        if score is not None:
            c["score"] = str(score)
        for key in drop:
            c["team"].pop(key, None)
    return _parse(raw)


def _liu_game(espn_id="401867910", when=LIU_WHEN, **kw):
    return _entry(espn_id, when, home=LIU, away=MERCYHURST,
                  home_score=27, away_score=24, **kw)


def _classify(espn_id, board, *, home, away, when, day, sport_key=FCS):
    return classify_espn_link(
        espn_id=espn_id, commence_time=when, game_date=day,
        home_team_name=home, away_team_name=away, board=board,
        sport_key=sport_key,
    )


def _liu(espn_id, board, *, home="LIU Sharks", away="Mercyhurst Lakers",
         when=LIU_WHEN):
    return _classify(espn_id, board, home=home, away=away, when=when,
                     day=LIU_DAY)


class TestTheRealBoardEntry:
    def test_the_real_parser_carries_abbreviation_and_no_nickname(self):
        ee = _parse(_raw())
        assert ee.home_team.abbreviation == "BRWN"
        assert ee.home_team.name == "Bears"
        assert ee.home_team.nickname is None
        assert _espn_team_initialism_form(ee.home_team) == "BRWN Bears"
        assert _espn_team_initialism_form(ee.away_team) == "HARV Crimson"

    def test_the_display_name_row_is_still_proven(self):
        board = [_parse(_raw())]
        verdict, target, _ = _classify(
            "401867806", board, home="Brown Bears", away="Harvard Crimson",
            when=REAL_WHEN, day=REAL_DAY,
        )
        assert verdict == LINK_PROVEN
        assert target.espn_id == "401867806"

    def test_an_initialism_row_is_proven_off_the_real_object(self):
        board = [_parse(_raw())]
        verdict, target, _ = _classify(
            "401867806", board, home="BRWN Bears", away="HARV Crimson",
            when=REAL_WHEN, day=REAL_DAY,
        )
        assert verdict == LINK_PROVEN
        assert target.espn_id == "401867806"


class TestInitialismForm:
    def test_a_stutter_is_not_an_alias(self):
        ee = _entry("1", LIU_WHEN, home=dict(LIU, abbreviation="Sharks"),
                    away=MERCYHURST)
        assert _espn_team_initialism_form(ee.home_team) == ""

    def test_a_missing_abbreviation_means_no_form_never_an_error(self):
        ee = _liu_game(drop=("abbreviation",))
        assert ee.home_team.abbreviation is None
        assert _espn_team_initialism_form(ee.home_team) == ""
        assert _espn_team_initialism_form(None) == ""

    def test_location_and_nickname_are_not_admitted(self):
        ee = _entry("1", LIU_WHEN, home=dict(LIU, nickname="Blackbirds"),
                    away=MERCYHURST)
        assert _espn_team_initialism_form(ee.home_team) == "LIU Sharks"
        assert not _identity_matches_team(
            "Blackbirds Sharks", "Mercyhurst Lakers",
            ee.home_team, ee.away_team, sport_key=FCS,
        )


class TestTheSpecimen10599:
    def test_the_production_shape_is_proven(self):
        verdict, target, reason = _liu("401867910", [_liu_game()])
        assert verdict == LINK_PROVEN, reason
        assert target.espn_id == "401867910"

    def test_the_strict_slate_read_elects_only_the_held_game(self):
        sibs = same_fixture_games(
            "LIU Sharks", "Mercyhurst Lakers", [_liu_game()], LIU_DAY,
            sport_key=FCS,
        )
        assert [g.espn_id for g in sibs] == ["401867910"]

    def test_without_the_abbreviation_the_legacy_verdict_stands(self):
        verdict, target, reason = _liu(
            "401867910", [_liu_game(drop=("abbreviation",))]
        )
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT fixture" in reason
        assert target is None

    def test_the_reverse_fixture_is_not_this_game(self):
        verdict, target, _ = _liu(
            "401867910", [_liu_game()],
            home="Mercyhurst Lakers", away="LIU Sharks",
        )
        assert verdict == ESPN_ID_DRIFTED
        assert target is None

    def test_a_held_id_on_another_day_is_drift_with_no_target(self):
        board = [_liu_game(when=LIU_WHEN + timedelta(days=7))]
        verdict, target, reason = _liu("401867910", board)
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT date" in reason
        assert target is None

    def test_a_missing_side_matches_nothing(self):
        ee = _liu_game()
        assert not _identity_matches_team(
            "LIU Sharks", "Mercyhurst Lakers", None, ee.away_team,
            sport_key=FCS,
        )


class TestTheFormNeverReachesTheFuzzyStage:
    """``names_match`` scores any ``X Mascot`` pair at 0.5 token overlap."""

    UNCO = dict(id="2458", location="Northern Colorado", name="Bears",
                abbreviation="UNCO", displayName="Northern Colorado Bears",
                shortDisplayName="N Colorado")

    def test_the_hazard_is_real_in_the_loose_predicate(self):
        # Strawman: the comparison this fix refuses to make. If it ever
        # stops being True the strict-only clause is no longer load-bearing.
        assert names_match("Brown Bears", "UNCO Bears")
        assert not names_match("Brown Bears", "Northern Colorado Bears")

    def test_a_mascot_sharing_rival_is_still_drift(self):
        rival = _entry("401867999", REAL_WHEN, home=self.UNCO)
        verdict, target, reason = _classify(
            "401867999", [rival], home="Brown Bears", away="Harvard Crimson",
            when=REAL_WHEN, day=REAL_DAY,
        )
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT fixture" in reason
        assert target is None

    def test_the_rival_is_never_elected_off_the_slate(self):
        rival = _entry("401867999", REAL_WHEN, home=self.UNCO)
        assert same_fixture_games(
            "Brown Bears", "Harvard Crimson", [rival], REAL_DAY, sport_key=FCS
        ) == []


class TestNoUniqueRivalIsChosen:
    """Two ESPN games our row's names fit: the rail must refuse to pick."""

    # A DISTINCT team id publishing the same abbreviation and mascot.
    LIU_TWIN = dict(LIU, id="9999", location="Lincoln Institute",
                    displayName="Lincoln Institute Sharks",
                    shortDisplayName="Lincoln")

    def _collision_board(self, *, second_when=LIU_WHEN):
        return [
            _liu_game(),
            _entry("401867911", second_when, home=self.LIU_TWIN,
                   away=MERCYHURST, home_score=10, away_score=3),
        ]

    def test_an_abbreviation_collision_with_the_held_id_absent(self):
        verdict, target, reason = _liu("401800000", self._collision_board())
        assert verdict == ESPN_ID_UNRESOLVABLE, reason
        assert target is None

    def test_an_abbreviation_collision_never_reads_as_drift(self):
        later = LIU_WHEN + timedelta(hours=5)
        for held, when in (
            ("401867910", LIU_WHEN),
            ("401867910", later),
            ("401867911", LIU_WHEN),
        ):
            verdict, _, reason = _liu(
                held, self._collision_board(second_when=later), when=when
            )
            assert verdict != ESPN_ID_DRIFTED, (held, when, reason)

    def test_two_ids_for_the_same_pair_elect_no_target(self):
        board = [
            _liu_game("401867910"),
            _liu_game("401867920", when=LIU_WHEN + timedelta(hours=5)),
        ]
        verdict, target, _ = _liu("401800000", board)
        assert verdict == ESPN_ID_UNRESOLVABLE
        assert target is None


class TestKnownRivalControls:
    def test_a_same_city_impostor_is_still_drift(self):
        # #1980's specimen, WITH abbreviations present on the ESPN objects.
        yankees = dict(id="10", location="New York", name="Yankees",
                       abbreviation="NYY", displayName="New York Yankees",
                       shortDisplayName="Yankees")
        dodgers = dict(id="19", location="Los Angeles", name="Dodgers",
                       abbreviation="LAD", displayName="Los Angeles Dodgers",
                       shortDisplayName="Dodgers")
        board = [_entry("401816142", REAL_WHEN, home=yankees, away=dodgers)]
        verdict, target, reason = _classify(
            "401816142", board, home="Mets", away="Dodgers",
            when=REAL_WHEN, day=REAL_DAY, sport_key="baseball_mlb",
        )
        assert verdict == ESPN_ID_DRIFTED
        assert "DIFFERENT fixture" in reason
        assert target is None

    def test_ohio_state_is_not_texas_state(self):
        # #2792's row: the one real mis-anchor every widening must keep out.
        txst = dict(id="326", location="Texas State", name="Bobcats",
                    abbreviation="TXST", displayName="Texas State Bobcats",
                    shortDisplayName="Texas St")
        tex = dict(id="251", location="Texas", name="Longhorns",
                   abbreviation="TEX", displayName="Texas Longhorns",
                   shortDisplayName="Texas")
        board = [_entry("401636611", REAL_WHEN, home=txst, away=tex)]
        verdict, _, _ = _classify(
            "401636611", board, home="Ohio State", away="Texas",
            when=REAL_WHEN, day=REAL_DAY, sport_key="americanfootball_ncaaf",
        )
        assert verdict == ESPN_ID_DRIFTED
