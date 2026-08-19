"""#1990 — the ESPN box-score parser is group-aware.

The defect this file guards has two halves, and the second is the dangerous one:

1. A DEAD MAP ENTRY. `_STAT_NORMALIZE` looked up `SO` for baseball strikeouts.
   ESPN emits `K`, in both the batting and the pitching group, and has for the
   entire life of the map — so the lookup missed on every MLB player ever
   ingested and MLB strikeout props were ungradeable.

2. A GROUP-BLIND PARSER. `_parse_boxscore` iterated `statistics[]` without
   reading the group, so `H`/`R`/`BB`/`HR` — which mean *made* in the batting
   group and *allowed* in the pitching group — were written to the same
   canonical key. Shane Baz's 6.1 IP / 4 H / 3 R / 10 K line was stored as
   `{"hits": 4, "runs": 3, "walks": 2, "home runs": 1}`: a pitcher's line
   wearing a batter's names, distinguishable only by the absence of `at bats`.

(1) is a gap; (2) is a quiet corruption, and a live mis-grading hazard.

Every fixture below is a verbatim slice of a real ESPN payload, cited by event
id. Fixtures are frozen rather than fetched so the suite has no network
dependency — but they were read off the wire, which is the point: the previous
map was written against assumptions about what ESPN emits, and every one of the
dead entries proved those assumptions wrong.
"""

import pytest

from app.services.espn_api import ESPNAPIService


@pytest.fixture
def svc():
    # __new__ avoids the client's network/session setup — every method under
    # test is pure parsing over a dict.
    return ESPNAPIService.__new__(ESPNAPIService)


# --------------------------------------------------------------------------
# Fixtures — verbatim from live payloads
# --------------------------------------------------------------------------

# GET /baseball/mlb/summary?event=401816574 (Yankees @ Orioles, 2026-08-18)
MLB_BATTING = {
    "type": "batting",
    "names": ["H-AB", "AB", "R", "H", "RBI", "HR", "BB", "K", "#P", "AVG", "OBP", "SLG"],
    "labels": ["H-AB", "AB", "R", "H", "RBI", "HR", "BB", "K", "#P", "AVG", "OBP", "SLG"],
    "keys": [
        "hits-atBats", "atBats", "runs", "hits", "RBIs", "homeRuns", "walks",
        "strikeouts", "pitches", "avg", "onBasePct", "slugAvg",
    ],
    "athletes": [
        {
            "athlete": {"displayName": "Trent Grisham"},
            "stats": ["2-4", "4", "1", "2", "3", "1", "0", "1", "15", ".224", ".313", ".426"],
        }
    ],
}

MLB_PITCHING = {
    "type": "pitching",
    "names": ["IP", "H", "R", "ER", "BB", "K", "HR", "PC-ST", "ERA", "PC"],
    "labels": ["IP", "H", "R", "ER", "BB", "K", "HR", "PC-ST", "ERA", "PC"],
    "keys": [
        "fullInnings.partInnings", "hits", "runs", "earnedRuns", "walks",
        "strikeouts", "homeRuns", "pitches-strikes", "ERA", "pitches",
    ],
    "athletes": [
        {
            "athlete": {"displayName": "Shane Baz"},
            "stats": ["6.1", "4", "3", "3", "2", "10", "1", "104-69", "4.02", "104"],
        }
    ],
}


def _mlb_summary():
    return {"boxscore": {"players": [{"statistics": [MLB_BATTING, MLB_PITCHING]}]}}


# GET /football/nfl/summary?event=401873272. NOTE the `keys` array carries EIGHT
# entries for SEVEN columns — ESPN ships both adjQBR and QBRating for the single
# RTG column. This misalignment is the reason the parser may not blindly zip
# `keys` against a player's stats.
NFL_PASSING = {
    "name": "passing",
    "labels": ["C/ATT", "YDS", "AVG", "TD", "INT", "SACKS", "RTG"],
    "names": None,
    "keys": [
        "completions/passingAttempts", "passingYards", "yardsPerPassAttempt",
        "passingTouchdowns", "interceptions", "sacks-sackYardsLost",
        "adjQBR", "QBRating",
    ],
    "athletes": [
        {
            "athlete": {"displayName": "Luke Altmyer"},
            "stats": ["13/22", "130", "5.9", "1", "2", "1-12", "53.2"],
        }
    ],
}

NFL_INTERCEPTIONS = {
    "name": "interceptions",
    "labels": ["INT", "YDS", "TD"],
    "names": None,
    "keys": ["interceptions", "interceptionYards", "interceptionTouchdowns"],
    "athletes": [
        {"athlete": {"displayName": "Luke Altmyer"}, "stats": ["3", "40", "1"]}
    ],
}

NFL_RECEIVING = {
    "name": "receiving",
    "labels": ["REC", "YDS", "AVG", "TD", "LONG", "TGTS"],
    "names": None,
    "keys": [
        "receptions", "receivingYards", "yardsPerReception",
        "receivingTouchdowns", "longReception", "receivingTargets",
    ],
    "athletes": [
        {"athlete": {"displayName": "Some Receiver"}, "stats": ["7", "88", "12.6", "1", "24", "9"]}
    ],
}

NFL_FUMBLES = {
    "name": "fumbles",
    "labels": ["FUM", "LOST", "REC"],
    "names": None,
    "keys": ["fumbles", "fumblesLost", "fumblesRecovered"],
    "athletes": [
        {"athlete": {"displayName": "Some Receiver"}, "stats": ["1", "1", "2"]}
    ],
}

# GET /hockey/nhl/summary?event=401803652 (2026-04-15). `S` is shotsTotal and
# `SOG` is shootoutGoals — NOT saves and NOT shots-on-goal.
NHL_SKATERS = {
    "name": "forwards",
    "labels": ["BS", "HT", "TK", "+/-", "TOI", "G", "A", "S", "SOG", "GV", "PIM"],
    "names": None,
    "keys": [
        "blockedShots", "hits", "takeaways", "plusMinus", "timeOnIce", "goals",
        "assists", "shotsTotal", "shootoutGoals", "giveaways", "penaltyMinutes",
    ],
    "athletes": [
        {
            "athlete": {"displayName": "Oskar Back"},
            "stats": ["2", "3", "1", "1", "18:32", "1", "2", "5", "0", "1", "2"],
        }
    ],
}

NHL_GOALIES = {
    "name": "goalies",
    "labels": ["GA", "SA", "SV", "SV%", "PIM"],
    "names": None,
    "keys": ["goalsAgainst", "shotsAgainst", "saves", "savePct", "penaltyMinutes"],
    "athletes": [
        {"athlete": {"displayName": "Some Goalie"}, "stats": ["2", "31", "29", ".935", "0"]}
    ],
}

# GET /basketball/nba/summary?event=401859966. A single UNNAMED group: no
# `type`, no `name`. This is the case the flat legacy map still serves.
NBA_GROUP = {
    "type": None,
    "name": None,
    "names": ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"],
    "labels": ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"],
    "keys": [
        "minutes", "points", "fieldGoalsMade-fieldGoalsAttempted",
        "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
        "freeThrowsMade-freeThrowsAttempted", "rebounds", "assists", "turnovers",
        "steals", "blocks", "offensiveRebounds", "defensiveRebounds", "fouls",
        "plusMinus",
    ],
    "athletes": [
        {
            "athlete": {"displayName": "Victor Wembanyama"},
            "stats": ["44", "24", "9-16", "2-6", "4-4", "13", "1", "0", "0", "3", "5", "8", "1", "1"],
        }
    ],
}


def _summary(*groups):
    return {"boxscore": {"players": [{"statistics": list(groups)}]}}


# --------------------------------------------------------------------------
# The specimen — the exact line named in #1990
# --------------------------------------------------------------------------


class TestShaneBazSpecimen:
    """Event 401816574, Shane Baz: IP 6.1 / K 10 under PITCHING keys."""

    def test_strikeouts_are_captured_at_all(self, svc):
        baz = svc._parse_boxscore(_mlb_summary())["Shane Baz"]
        # Pre-fix this was absent entirely: the map looked up "SO", ESPN said "K".
        assert baz["pitching strikeouts"] == 10.0

    def test_innings_pitched_and_earned_runs_are_stored(self, svc):
        baz = svc._parse_boxscore(_mlb_summary())["Shane Baz"]
        assert baz["innings pitched"] == 6.1
        assert baz["earned runs"] == 3.0

    def test_pitcher_line_never_wears_batting_names(self, svc):
        """The corruption half. 4 H / 3 R / 2 BB / 1 HR were ALLOWED."""
        baz = svc._parse_boxscore(_mlb_summary())["Shane Baz"]
        for batting_key in ("hits", "runs", "walks", "home runs", "strikeouts", "at bats"):
            assert batting_key not in baz, (
                f"{batting_key!r} on a pitcher is the #1990 corruption: a "
                f"consumer reading it gets hits-allowed in the field a "
                f"batter's hits live in."
            )
        assert baz["pitching hits allowed"] == 4.0
        assert baz["pitching runs allowed"] == 3.0
        assert baz["pitching walks allowed"] == 2.0
        assert baz["pitching home runs allowed"] == 1.0

    def test_batter_keeps_every_legacy_key_and_gains_strikeouts(self, svc):
        """No regression in the seven stats production already stored."""
        grisham = svc._parse_boxscore(_mlb_summary())["Trent Grisham"]
        assert grisham["hits"] == 2.0
        assert grisham["runs"] == 1.0
        assert grisham["home runs"] == 1.0
        assert grisham["rbis"] == 3.0
        assert grisham["walks"] == 0.0
        assert grisham["at bats"] == 4.0
        assert grisham["batting average"] == pytest.approx(0.224)
        # New: the batter's K, the other side of a strikeout prop.
        assert grisham["strikeouts"] == 1.0

    def test_batter_and_pitcher_do_not_share_a_key(self, svc):
        parsed = svc._parse_boxscore(_mlb_summary())
        assert set(parsed["Trent Grisham"]) & set(parsed["Shane Baz"]) == set()


# --------------------------------------------------------------------------
# The general defect: one abbreviation, two meanings, one key
# --------------------------------------------------------------------------


class TestFootballGroupCollisions:
    def test_interceptions_thrown_and_caught_are_different_keys(self, svc):
        """`INT` is thrown in `passing` and caught in `interceptions`.

        Same player, same abbreviation, opposite meaning — the baseball bug
        in a second sport. Pre-fix the later group simply overwrote the earlier.
        """
        parsed = svc._parse_boxscore(_summary(NFL_PASSING, NFL_INTERCEPTIONS))
        altmyer = parsed["Luke Altmyer"]
        assert altmyer["interceptions thrown"] == 2.0
        assert altmyer["interceptions caught"] == 3.0

    def test_fumble_recovery_is_not_a_reception(self, svc):
        """`REC` is a catch in `receiving` and a fumble recovery in `fumbles`."""
        parsed = svc._parse_boxscore(_summary(NFL_RECEIVING, NFL_FUMBLES))
        rec = parsed["Some Receiver"]
        assert rec["receptions"] == 7.0
        assert rec["fumbles recovered"] == 2.0

    def test_yards_do_not_overwrite_across_groups(self, svc):
        parsed = svc._parse_boxscore(_summary(NFL_PASSING, NFL_RECEIVING))
        assert parsed["Luke Altmyer"]["passing yards"] == 130.0
        assert parsed["Some Receiver"]["receiving yards"] == 88.0

    def test_misaligned_keys_array_falls_back_to_labels(self, svc):
        """NFL `passing` ships 8 keys for 7 columns (adjQBR + QBRating).

        A blind `zip(keys, stats)` shifts every stat one position left, so
        yards would be written under completions. The length check is the whole
        guard, and this asserts it holds rather than that it exists.
        """
        assert len(NFL_PASSING["keys"]) != len(NFL_PASSING["labels"])
        altmyer = svc._parse_boxscore(_summary(NFL_PASSING))["Luke Altmyer"]
        assert altmyer["completions"] == 13.0      # from "13/22", not 130
        assert altmyer["passing yards"] == 130.0
        assert altmyer["passing touchdowns"] == 1.0


class TestHockeyWrongQuantities:
    def test_skater_shots_are_not_saves(self, svc):
        """`S` is shotsTotal. The old flat map read it as "saves"."""
        back = svc._parse_boxscore(_summary(NHL_SKATERS))["Oskar Back"]
        assert back["shots"] == 5.0
        assert "saves" not in back

    def test_sog_is_shootout_goals_not_shots_on_goal(self, svc):
        back = svc._parse_boxscore(_summary(NHL_SKATERS))["Oskar Back"]
        assert back["shootout goals"] == 0.0
        assert "shots on goal" not in back

    def test_goalie_saves_still_resolve(self, svc):
        """`kxnhlsaves` grades off this key — it must not move."""
        goalie = svc._parse_boxscore(_summary(NHL_GOALIES))["Some Goalie"]
        assert goalie["saves"] == 29.0
        assert goalie["goals against"] == 2.0
        assert goalie["shots against"] == 31.0

    def test_skater_goals_and_assists_still_resolve(self, svc):
        """`kxnhlgoal` / `kxnhlast` / `kxnhlpts` grade off these."""
        back = svc._parse_boxscore(_summary(NHL_SKATERS))["Oskar Back"]
        assert back["goals"] == 1.0
        assert back["assists"] == 2.0


class TestBasketballUnchanged:
    """A single unnamed group has no collisions, so it stays on the flat map."""

    def test_group_key_is_empty_when_espn_declares_none(self, svc):
        assert svc._group_key(NBA_GROUP) == ""

    def test_every_basketball_stat_survives(self, svc):
        wemby = svc._parse_boxscore(_summary(NBA_GROUP))["Victor Wembanyama"]
        assert wemby["points"] == 24.0
        assert wemby["rebounds"] == 13.0
        assert wemby["assists"] == 1.0
        assert wemby["blocks"] == 3.0
        assert wemby["three pointers"] == 2.0
        assert wemby["field goals"] == 9.0
        assert wemby["double doubles"] == 1


# --------------------------------------------------------------------------
# The mechanism itself
# --------------------------------------------------------------------------


class TestGroupResolution:
    def test_group_is_read_from_type_or_name(self, svc):
        """Baseball puts it in `type`; football and hockey put it in `name`."""
        assert svc._group_key(MLB_PITCHING) == "pitching"
        assert svc._group_key(NFL_PASSING) == "passing"
        assert svc._group_key(NHL_GOALIES) == "goalies"

    def test_forwards_and_defenses_alias_onto_skaters(self, svc):
        assert svc._group_key({"name": "forwards"}) == "skaters"
        assert svc._group_key({"name": "defenses"}) == "skaters"

    def test_namespaced_group_drops_unmapped_columns(self, svc):
        """A namespaced group must not borrow the flat map for a stray column.

        `PC-ST` ("104-69") and `H-AB` ("2-4") are unmapped. Falling through to
        the flat map would resolve `H-AB`'s neighbours by abbreviation and
        reintroduce exactly the cross-meaning write this change removes.
        """
        baz = svc._parse_boxscore(_mlb_summary())["Shane Baz"]
        assert "pitches-strikes" not in baz
        # PC-ST's leading number is 104, same as the real pitch count — assert
        # the value present came from PC and that no stray key carries it.
        assert baz["pitch count"] == 104.0
        assert len([k for k, v in baz.items() if v == 104.0]) == 1

    def test_unknown_group_still_parses_via_flat_map(self, svc):
        """A group ESPN adds tomorrow degrades to the legacy behaviour."""
        novel = {
            "name": "somethingNew",
            "labels": ["PTS", "REB"],
            "names": ["PTS", "REB"],
            "keys": ["points", "rebounds"],
            "athletes": [{"athlete": {"displayName": "X"}, "stats": ["10", "4"]}],
        }
        parsed = svc._parse_boxscore(_summary(novel))
        assert parsed["X"] == {"points": 10.0, "rebounds": 4.0}


class TestParseStatValue:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("28", 28.0),
            ("10-22", 10.0),      # basketball made-attempted
            ("13/22", 13.0),      # football C/ATT — dropped before this fix
            ("2/2", 2.0),         # kicking FG
            (".455", 0.455),
            ("6.1", 6.1),         # innings pitched, NOT a compound
            ("--", None),
            ("", None),
            ("18:32", None),      # time on ice — deliberately unparsed
        ],
    )
    def test_values(self, svc, raw, expected):
        assert svc._parse_stat_value(raw) == expected

    def test_negative_numbers_are_not_compounds(self, svc):
        assert svc._parse_stat_value("-1") == -1.0


class TestDeadMapEntriesStayDead:
    """Each of these was verified absent from a real payload on 2026-08-18.

    Restoring one re-opens a defect, so they are asserted gone rather than
    merely deleted — a future edit that "adds back the missing SO entry" fails
    here with the reason.
    """

    def test_so_is_not_a_baseball_strikeout(self):
        assert "SO" not in ESPNAPIService._STAT_NORMALIZE, (
            "ESPN emits 'K' for baseball strikeouts, never 'SO'. This entry "
            "was dead for the life of the map and is why #1990 happened."
        )

    def test_hockey_s_is_not_saves(self):
        assert "S" not in ESPNAPIService._STAT_NORMALIZE

    def test_flat_sog_entry_is_gone(self):
        assert "SOG" not in ESPNAPIService._STAT_NORMALIZE

    def test_football_sack_singular_is_gone(self):
        # ESPN emits "SACKS"; the singular never matched.
        assert "SACK" not in ESPNAPIService._STAT_NORMALIZE

    def test_never_emitted_compound_yard_labels_are_gone(self):
        for label in ("PASS YDS", "RUSH YDS", "REC YDS"):
            assert label not in ESPNAPIService._STAT_NORMALIZE


# --------------------------------------------------------------------------
# The cross-file invariant that would have caught this in the first place
# --------------------------------------------------------------------------


class TestPropResolverAgreesWithParser:
    """A prop mapping must name a stat the parser can actually emit.

    This is the check for the CLASS, not the instance. `kxmlbks -> strikeouts`
    looked correct in isolation and was unresolvable in practice, because
    nothing on either side asserted that the name the resolver looks up is a
    name the parser writes. Any future mapping onto a stat we never produce
    fails here instead of silently grading every outcome a loser.
    """

    @staticmethod
    def _emittable() -> set:
        names = set(ESPNAPIService._STAT_NORMALIZE.values())
        for table in ESPNAPIService._GROUP_STAT_MAP.values():
            names |= set(table.values())
        for table in ESPNAPIService._GROUP_LABEL_MAP.values():
            names |= set(table.values())
        # Computed by the parser rather than mapped from a column.
        names |= {"double doubles", "triple doubles"}
        return names

    def test_every_ticker_mapping_names_an_emittable_stat(self):
        from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

        emittable = self._emittable()
        unresolvable = {
            prefix: stat
            for prefix, stat in _PROP_TICKER_TO_STAT.items()
            if stat not in emittable
        }
        assert not unresolvable, (
            f"These prop mappings look up a stat the ESPN parser never writes, "
            f"so every outcome grades off a missing key: {unresolvable}"
        )

    def test_every_combo_mapping_names_emittable_stats(self):
        from app.tasks.backfill_winners import _COMBO_STATS

        emittable = self._emittable()
        unresolvable = {
            prefix: [s for s in stats if s not in emittable]
            for prefix, stats in _COMBO_STATS.items()
            if any(s not in emittable for s in stats)
        }
        assert not unresolvable, (
            f"Combo prop mappings reference stats the parser never writes: "
            f"{unresolvable}"
        )

    def test_mlb_strikeout_prop_points_at_the_pitching_key(self):
        """KXMLBKS is a pitcher prop — the series rules say so explicitly.

        'If this pitcher does not start the game but does not record at least
        one batter faced, this market will resolve to Fair Market Price.'
        Pointing it at the bare batting `strikeouts` key would grade a
        starter's 9+ K line off a batter's strikeout count.
        """
        from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

        assert _PROP_TICKER_TO_STAT["kxmlbks"] == "pitching strikeouts"

    def test_mlb_hit_and_hr_props_stay_on_the_batting_keys(self):
        from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

        assert _PROP_TICKER_TO_STAT["kxmlbhit"] == "hits"
        assert _PROP_TICKER_TO_STAT["kxmlbhr"] == "home runs"

    def test_the_specimen_grades_end_to_end(self, svc):
        """Shane Baz, 10 K, against a 9+ threshold — the actual product outcome.

        Mirrors the resolver's lookup (`player_stats.get(stat_name, 0)`) so a
        change to either side that breaks grading fails here.
        """
        from app.tasks.backfill_winners import _PROP_TICKER_TO_STAT

        baz = svc._parse_boxscore(_mlb_summary())["Shane Baz"]
        stat_name = _PROP_TICKER_TO_STAT["kxmlbks"]
        actual = baz.get(stat_name, 0)
        assert actual == 10.0
        assert (actual >= 9) is True    # KXMLBKS-...-9  → Yes
        assert (actual >= 11) is False  # KXMLBKS-...-11 → No
