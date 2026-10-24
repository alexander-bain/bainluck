"""Guard: `Sporting Lisbon` and `Sporting CP` are one club, to the fold and to the stamp (#2823).

THE PAYLOAD. The Sports feed, 2026-10-21 21:05Z (measurement M-R-FRESH-20261021-21),
carried one Champions League game twice at the same 19:00Z kickoff:

    15330361  Sporting Lisbon / LASK      odds_api, ESPN 401915391  completed 2-3, FT
    15327076  Sporting CP / LASK Linz     polymarket, StatPal soccer:9543347  live, no score

THE GAP. `soccer_team_matching` named this pair under THE MISSES ("alternative
club names ... none has been measured"): `lisbon` and `cp` are both core tokens
and the two spellings share only `sporting`, so the serve-time fold could not
pair them and the StatPal stamp, which reads the same predicate, anchored only
the Polymarket row. With no shared id the drain could not reach them either.

THE FIX is one whole-name entry in `CLUB_NAME_ALIASES`, the #3391 shape. Whole
name, so no other `Sporting` club and no reserve side is reachable through it.
"""

from datetime import datetime, timezone

import pytest

from app.services.statpal_api import StatPalFixture
from app.tasks.stamp_v1_statpal_fixtures import (
    VERDICT_STAMP_TWIN,
    classify_fixture,
)
from app.utils.event_twin_fold import fold_twin_events
from app.utils.soccer_team_matching import soccer_pair_matches, soccer_team_matches

KICKOFF = datetime(2026, 10, 21, 19, 0, tzinfo=timezone.utc)
UCL_SPORT_ID = 1322


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock (see #3391's guard)."""

    def __init__(self, id, home, away, **fields):
        self.id = id
        self.sport_id = UCL_SPORT_ID
        self.sport = _Sport("soccer_uefa_champs_league")
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = KICKOFF
        self.home_score = None
        self.away_score = None
        self.espn_id = None
        self.external_id = None
        self.commence_time_source = "espn"
        self.win_probability_sources = None
        self.status = "scheduled"
        self.completed_at = None
        self.period = None
        self.event_tags = None
        self.statpal_fixture_id = None
        for name, value in fields.items():
            setattr(self, name, value)


def _the_production_pair():
    """Both rows as production served them, read 2026-10-21 ~21:10Z."""
    finished = _Row(
        15330361, "Sporting Lisbon", "LASK",
        external_id="8fdcaee14b3e8966e09d468a0b17ce18",
        espn_id="401915391",
        status="completed",
        home_score=2,
        away_score=3,
        period="FT",
        completed_at=datetime(2026, 10, 21, 20, 59, 40, tzinfo=timezone.utc),
        win_probability_sources={"betting": {"value": 0.0094}},
    )
    ghost = _Row(
        15327076, "Sporting CP", "LASK Linz",
        commence_time_source="polymarket_venue",
        status="live",
        statpal_fixture_id="9543347",
        win_probability_sources={"polymarket": {"value": 0.0005}},
        event_tags=["provenance:source:polymarket", "provenance:unanchored"],
    )
    return finished, ghost


class TestThePredicateSeesOneClub:
    @pytest.mark.parametrize("a,b", [("Sporting Lisbon", "Sporting CP"), ("Sporting CP", "Sporting Lisbon")])
    def test_both_directions(self, a, b):
        assert soccer_team_matches(a, b)

    def test_the_fixture_pairs_with_lasks_two_spellings(self):
        assert soccer_pair_matches(("Sporting CP", "LASK Linz"), ("Sporting Lisbon", "LASK"))
        assert soccer_pair_matches(("Sporting CP", "LASK"), ("Sporting Lisbon", "LASK"))

    @pytest.mark.parametrize(
        "other",
        [
            "Sporting Braga",
            "Sporting Gijon",
            "Sporting Kansas City",
            "Sporting Lisbon B",
            "Sporting CP B",
            "Sporting Lisbon W",
        ],
    )
    def test_it_reaches_no_other_sporting_club_and_no_other_squad(self, other):
        assert not soccer_team_matches(other, "Sporting Lisbon")
        assert not soccer_team_matches(other, "Sporting CP")


class TestTheFoldServesTheFinishedRowOnce:
    @pytest.mark.parametrize("reverse", [False, True])
    def test_the_live_ghost_folds_into_the_finished_row(self, reverse):
        finished, ghost = _the_production_pair()
        rows = [ghost, finished] if reverse else [finished, ghost]
        fold = fold_twin_events(rows)

        assert [e.id for e in fold.events] == [finished.id], "the ESPN-scored row is served"
        assert fold.survivor_of == {ghost.id: finished.id}

    def test_before_the_alias_this_pair_did_not_fold(self, monkeypatch):
        """Non-vacuity: the fold above is the alias's doing, not a looser rule."""
        from app.utils import event_twin_fold as etf
        from app.utils import soccer_team_matching as stm

        etf._pair_matches.cache_clear()
        without = {k: v for k, v in stm.CLUB_NAME_ALIASES.items() if v != ("sporting", "cp")}
        assert len(without) == len(stm.CLUB_NAME_ALIASES) - 1
        monkeypatch.setattr(stm, "CLUB_NAME_ALIASES", without)
        try:
            finished, ghost = _the_production_pair()
            fold = fold_twin_events([finished, ghost])
            assert fold.dropped_ids == []
        finally:
            etf._pair_matches.cache_clear()

    def test_a_braga_fixture_at_the_same_minute_does_not_fold(self):
        finished, _ = _the_production_pair()
        braga = _Row(
            1, "Sporting Braga", "LASK",
            commence_time_source="polymarket_venue",
            win_probability_sources={"polymarket": {"value": 0.5}},
        )
        fold = fold_twin_events([finished, braga])
        assert fold.dropped_ids == []


class TestTheStampHandsTheDrainTheSharedId:
    """The durable half. The stamp anchored only 15327076 on 2026-10-18; with the
    alias the ESPN row is a second candidate, one row already holds the contest id
    and the other holds none, which is `STAMP_TWIN`: the write `merge_duplicate_events`
    needs under ruling 048. StatPal's spellings here are an assumption from the row
    it anchored (`Sporting CP`), and both LASK spellings are tried."""

    @pytest.mark.parametrize("statpal_away", ["LASK", "LASK Linz"])
    def test_stamp_twin_writes_the_espn_row(self, statpal_away):
        fixture = StatPalFixture(
            fixture_id="9543347", home_team="Sporting CP", away_team=statpal_away,
            start_time=KICKOFF,
        )
        pool = [
            {"id": 15327076, "commence_time": KICKOFF, "home": "Sporting CP",
             "away": "LASK Linz", "statpal_fixture_id": "9543347"},
            {"id": 15330361, "commence_time": KICKOFF, "home": "Sporting Lisbon",
             "away": "LASK", "statpal_fixture_id": None},
        ]
        from app.utils.soccer_team_matching import soccer_pair_matches as rule

        verdict, rows = classify_fixture(fixture, pool, pair_rule=rule)
        assert verdict == VERDICT_STAMP_TWIN
        assert rows[0]["id"] == 15330361
