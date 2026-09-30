"""#9482 — the NHL page spells the Canadiens and the Blues one way.

Team rows below are production's, read 2026-09-29:

    568  Montreal Canadiens  espn 10  standings 2026-09-29
    3706 Montréal Canadiens  espn 10  standings 2026-09-28
    571  St. Louis Blues     espn 19  standings 2026-05-05
    3705 St Louis Blues      espn 19  standings 2026-09-29

ESPN's displayNames (site.api.espn.com, same day): ``Montreal Canadiens`` (10),
``St. Louis Blues`` (19).
"""

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.espn_team_spelling import apply_espn_respelling, espn_respelling

NHL = 4


def _team(team_id, name, espn_id, stamp):
    return SimpleNamespace(
        id=team_id, name=name, espn_id=espn_id, sport_id=NHL,
        standings_updated_at=(
            datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc) if stamp else None
        ),
    )


MTL = _team(568, "Montreal Canadiens", "10", "2026-09-29T08:00:00")
MTL_ACCENT = _team(3706, "Montréal Canadiens", "10", "2026-09-28T08:00:08")
STL_ESPN = _team(571, "St. Louis Blues", "19", "2026-05-05T08:00:29")
STL = _team(3705, "St Louis Blues", "19", "2026-09-29T08:00:00")
PIT = _team(60, "Pittsburgh Penguins", "16", "2026-09-29T08:00:00")
CACHE = {(t.name, NHL): t for t in (MTL, MTL_ACCENT, STL_ESPN, STL, PIT)}


def _espn(espn_id, display):
    return SimpleNamespace(espn_id=espn_id, display_name=display)


ESPN_MTL = _espn("10", "Montreal Canadiens")
ESPN_STL = _espn("19", "St. Louis Blues")
ESPN_PIT = _espn("16", "Pittsburgh Penguins")


class TestTheCanadiensTakeEspnsSpelling:
    def test_the_accented_side_bound_to_3706_is_respelled(self):
        assert espn_respelling(
            "Montréal Canadiens", ESPN_MTL, NHL, CACHE, bound_team_id=3706,
        ) == "Montreal Canadiens"

    def test_an_unbound_side_is_respelled(self):
        assert espn_respelling("Montréal Canadiens", ESPN_MTL, NHL, CACHE) == "Montreal Canadiens"

    def test_the_right_spelling_is_left_alone(self):
        assert espn_respelling("Montreal Canadiens", ESPN_MTL, NHL, CACHE, bound_team_id=568) is None


class TestTheBluesNeverMoveOntoMaysStandings:
    def test_espns_row_is_staler_than_the_bound_row_so_the_side_holds(self):
        assert espn_respelling(
            "St Louis Blues", ESPN_STL, NHL, CACHE, bound_team_id=3705,
        ) is None

    def test_strawman_without_the_bound_row_it_would_move(self):
        # The guard is what holds it: the same side with no binding would move.
        assert espn_respelling("St Louis Blues", ESPN_STL, NHL, CACHE) == "St. Louis Blues"

    def test_a_side_already_on_espns_row_is_never_blocked_by_itself(self):
        assert espn_respelling(
            "St Louis Blues", ESPN_STL, NHL, CACHE, bound_team_id=571,
        ) == "St. Louis Blues"


class TestItNeverNamesAnotherClubOrMints:
    def test_a_different_fold_is_not_a_spelling(self):
        cache = {**CACHE, ("Los Angeles Clippers", NHL): _team(9, "Los Angeles Clippers", "12", None)}
        assert espn_respelling("LA Clippers", _espn("12", "Los Angeles Clippers"), NHL, cache) is None

    def test_no_row_with_espns_spelling_means_no_rewrite(self):
        cache = {k: v for k, v in CACHE.items() if v is not MTL}
        assert espn_respelling("Montréal Canadiens", ESPN_MTL, NHL, cache) is None

    def test_a_row_with_espns_spelling_but_another_espn_id_is_not_the_club(self):
        cache = {**CACHE, ("Montreal Canadiens", NHL): _team(568, "Montreal Canadiens", "99", None)}
        assert espn_respelling("Montréal Canadiens", ESPN_MTL, NHL, cache) is None

    def test_another_sports_row_is_not_consulted(self):
        assert espn_respelling("Montréal Canadiens", ESPN_MTL, NHL + 1, CACHE) is None

    @pytest.mark.parametrize("espn_team", [None, _espn("10", None), _espn(None, "Montreal Canadiens")])
    def test_a_thin_payload_writes_nothing(self, espn_team):
        assert espn_respelling("Montréal Canadiens", espn_team, NHL, CACHE) is None


class TestApplyWritesEachSideOnce:
    def test_away_side_only_and_counted(self):
        event = SimpleNamespace(
            id=15169778, sport_id=NHL,
            home_team_name="Pittsburgh Penguins", home_team_id=60,
            away_team_name="Montréal Canadiens", away_team_id=3706,
        )
        ee = SimpleNamespace(home_team=ESPN_PIT, away_team=ESPN_MTL)
        stats: dict = {}
        assert apply_espn_respelling(event, ee, CACHE, stats, source="espn_scheduled") == 1
        assert (event.home_team_name, event.away_team_name) == (
            "Pittsburgh Penguins", "Montreal Canadiens",
        )
        assert stats == {"espn_scheduled_team_name_respelled": 1}

    def test_a_reversed_pairing_is_not_a_spelling(self):
        event = SimpleNamespace(
            id=1, sport_id=NHL,
            home_team_name="Montréal Canadiens", home_team_id=3706,
            away_team_name="Pittsburgh Penguins", away_team_id=60,
        )
        ee = SimpleNamespace(home_team=ESPN_PIT, away_team=ESPN_MTL)
        assert apply_espn_respelling(event, ee, CACHE, {}, source="espn_live") == 0
        assert event.home_team_name == "Montréal Canadiens"


class _Row:
    """A stand-in ORM row: any column not named here reads as NULL."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __getattr__(self, _name):
        return None


class TestTheScheduledPassResolvesTheRespelledName:
    async def test_upsert_team_is_asked_for_espns_spelling(self, monkeypatch):
        from app.utils import espn_helpers

        class _Sport:
            id = NHL
            key = "icehockey_nhl"

        kickoff = datetime(2026, 10, 3, 23, 0, tzinfo=timezone.utc)
        event = _Row(
            id=15169778, espn_id="401891822", sport=_Sport(), sport_id=NHL,
            home_team_name="Pittsburgh Penguins", away_team_name="Montréal Canadiens",
            home_team_id=60, away_team_id=3706, commence_time=kickoff,
            commence_time_source="espn", status="scheduled",
        )
        game = _Row(espn_id="401891822", date=kickoff, home_team=ESPN_PIT,
                    away_team=ESPN_MTL, broadcasts=[])

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return self

            def all(self):
                return self._rows

        answers = iter([[event], list(CACHE.values())])

        class _Session:
            async def execute(self, *_a, **_k):
                return _Result(next(answers, []))

        asked = []

        async def _upsert(_session, name, _espn_team, _sport_id, cache, _stats):
            asked.append(name)
            return cache.get((name, NHL))

        async def _noop(*_a, **_k):
            return None

        monkeypatch.setattr(espn_helpers, "upsert_team", _upsert)
        monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
        monkeypatch.setattr(espn_helpers, "espn_confirms_start_placeholder", _noop)
        monkeypatch.setattr(espn_helpers, "record_authority_stoppage", _noop)
        stats: dict = {}
        await espn_helpers.sync_scheduled_events(_Session(), "icehockey_nhl", [game], stats)

        assert asked == ["Pittsburgh Penguins", "Montreal Canadiens"]
        assert event.away_team_name == "Montreal Canadiens"
        assert event.away_team_id == 568
        assert stats["espn_scheduled_team_name_respelled"] == 1


def test_the_live_pass_respells_before_it_resolves_the_team():
    from app.tasks import espn_sync

    source = inspect.getsource(espn_sync._process_live_sport)
    respell = source.index("apply_espn_respelling(event, ee, team_cache")
    assert respell < source.index("await upsert_team_fn(session, event.home_team_name")


class TestTheRepairPlan:
    @staticmethod
    def _state(which):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import SIDES

        return {key: (spec[0], spec[1 if which == "before" else 2]) for key, spec in SIDES.items()}

    def test_before_plans_three_writes_in_id_order(self):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import plan

        writes = plan(self._state("before"), restore=False)
        assert [(e, s, n) for e, s, _o, n in writes] == [
            (15169778, "away", ("Montreal Canadiens", 568)),
            (15169783, "home", ("Montreal Canadiens", 568)),
            (15319664, "away", ("St Louis Blues", 3705)),
        ]

    def test_after_is_a_no_op_and_restore_walks_back(self):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import plan

        assert plan(self._state("after"), restore=False) == []
        back = plan(self._state("after"), restore=True)
        assert [n for *_x, n in back] == [
            ("Montréal Canadiens", 3706), ("Montréal Canadiens", 3706), ("St. Louis Blues", 3705),
        ]

    def test_a_mixed_state_refuses(self):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import Refused, plan

        state = self._state("before")
        state[(15169783, "home")] = self._state("after")[(15169783, "home")]
        with pytest.raises(Refused):
            plan(state, restore=False)

    def test_a_moved_kickoff_refuses(self):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import Refused, plan

        state = self._state("before")
        state[(15169778, "away")] = ("2026-10-04T23:00:00+00:00", state[(15169778, "away")][1])
        with pytest.raises(Refused):
            plan(state, restore=False)

    def test_a_missing_row_refuses(self):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import Refused, plan

        state = self._state("before")
        del state[(15319664, "away")]
        with pytest.raises(Refused):
            plan(state, restore=False)

    @pytest.mark.parametrize("app", ["", "bainluck-staging"])
    def test_refuses_off_production(self, app):
        from scripts.repair_9482_nhl_club_spelling_on_upcoming_games import (
            Refused,
            refuse_unless_production,
        )

        with pytest.raises(Refused):
            refuse_unless_production({"HEROKU_APP_NAME": app})
