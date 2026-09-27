"""#5576: the venue-named-competition repair places its pinned rows and nothing else.

The refusal rule and the manifest's shape are pure and driven here. The SQL —
the bank, the guarded ``sport_id`` move, the re-run and the undo — runs against
a real PostgreSQL in
``tests/integration/test_repair_5576_venue_named_competition_pg.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tasks.prediction_market_matching import MARKET_BORN_COMMENCE_SOURCES
from app.utils.venue_competition import POLYMARKET_LEAGUE_CODES

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_5576_venue", _SCRIPTS / "repair_5576_venue_named_competition.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

UNL = "soccer_uefa_nations_league"
NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 10, 4, 18, 45, tzinfo=timezone.utc)


def _event(**over) -> dict:
    """Portugal v Norway 15316636 exactly as production held it on 2026-09-27."""
    row = {
        "id": 15316636,
        "sport_id": 900,
        "sport_key": "soccer_other",
        "home_team_name": "Portugal",
        "away_team_name": "Norway",
        "commence_time": KICKOFF,
        "status": "scheduled",
        "commence_time_source": "polymarket_venue",
        "tags": '["provenance:source:polymarket", "provenance:unanchored"]',
    }
    row.update(over)
    return row


SIDES = [{"soccer_fifa_world_cup", UNL}, {"soccer_fifa_world_cup", UNL}]


def _why(event=None, venues=None, sides=SIDES, counterparts=(), league=UNL):
    return m.refusal(
        league,
        _event() if event is None else event,
        {UNL} if venues is None else venues,
        sides,
        list(counterparts),
        NOW,
    )


class TestTheRule:
    def test_the_specimen_is_placed(self):
        assert _why() is None

    def test_one_resolvable_side_is_enough(self):
        """Republic of Ireland v Israel: `teams` carries no 'Republic of Ireland'."""
        assert _why(sides=[set(), {UNL}]) is None

    @pytest.mark.parametrize(
        "event,expected",
        [
            (None, "gone"),
            (_event(sport_key=UNL), "not the catch-all"),
            (_event(status="live"), "status"),
            (_event(status="completed"), "status"),
            (_event(commence_time=NOW), "kicked off"),
            (_event(commence_time=NOW - timedelta(hours=1)), "kicked off"),
            (
                _event(tags='["provenance:duplicate-of:15316810"]'),
                "duplicate-of",
            ),
            (_event(tags=["provenance:duplicate-of:15316810"]), "duplicate-of"),
            (_event(commence_time_source="espn"), "not market-born"),
            (_event(commence_time_source="odds_api"), "not market-born"),
            (_event(commence_time_source=None), "not market-born"),
        ],
    )
    def test_a_row_that_no_longer_qualifies_is_skipped(self, event, expected):
        if event is None:
            why = m.refusal(UNL, None, {UNL}, SIDES, [], NOW)
        else:
            why = _why(event=event)
        assert why is not None and expected in why

    @pytest.mark.parametrize(
        "venues",
        [set(), {"soccer_fifa_world_cup"}, {UNL, "soccer_fifa_world_cup"}],
    )
    def test_the_venue_must_still_name_exactly_the_pinned_league(self, venues):
        assert "the venue now names" in _why(venues=venues)

    def test_no_side_in_the_league_is_skipped(self):
        assert "no side plays in" in _why(sides=[{"soccer_fifa_world_cup"}, set()])
        assert "no side plays in" in _why(sides=None)

    def test_a_row_with_its_own_counterpart_is_left_to_the_drain(self):
        assert "#8818" in _why(counterparts=[("Portugal", "Norway")])

    def test_a_covered_league_is_never_placed_into(self):
        why = _why(
            league="soccer_usa_mls",
            venues={"soccer_usa_mls"},
            sides=[{"soccer_usa_mls"}, set()],
        )
        assert why is not None and "covered" in why

    def test_every_market_born_source_is_eligible(self):
        for source in MARKET_BORN_COMMENCE_SOURCES:
            assert _why(event=_event(commence_time_source=source)) is None


class TestTheCounterpart:
    @pytest.mark.parametrize(
        "theirs",
        [
            ("Czech Republic", "England"),  # 15315653 beside 15313497 Czechia v England
            ("Turkey", "Italy"),  # 15304745 beside 15312968 Türkiye v Italy
            ("SD Eibar", "Las Palmas"),  # 15316221 beside 15312462
        ],
    )
    def test_the_measured_counterparts_share_a_side(self, theirs):
        mine = {
            ("Czech Republic", "England"): ("Czechia", "England"),
            ("Turkey", "Italy"): ("Türkiye", "Italy"),
            ("SD Eibar", "Las Palmas"): ("SD Eibar", "UD Las Palmas"),
        }[theirs]
        assert m.has_counterpart(*mine, [theirs])

    def test_accents_case_and_punctuation_fold(self):
        assert m.has_counterpart("Córdoba CF", "X", [("cordoba c.f.", "Y")])
        assert m.has_counterpart("Bosnia & Herzegovina", "Z", [("Bosnia  Herzegovina", "Q")])

    def test_a_different_fixture_is_no_counterpart(self):
        assert not m.has_counterpart("Portugal", "Norway", [("Denmark", "Wales")])
        # A name is a whole name, not a substring: "Córdoba" is not "Córdoba CF".
        assert not m.has_counterpart("Córdoba CF", "A", [("Córdoba", "B")])

    def test_an_empty_name_matches_nothing(self):
        assert not m.has_counterpart("", "", [("", "")])


class TestTheManifest:
    def test_sixty_nine_rows_forty_six_nations_league(self):
        leagues = Counter(league for _, league in m.PLACEMENTS)
        assert len(m.PLACEMENTS) == 69
        assert leagues[UNL] == 46
        assert len(leagues) == 13

    def test_no_row_is_pinned_twice(self):
        ids = [event_id for event_id, _ in m.PLACEMENTS]
        assert len(ids) == len(set(ids))

    def test_every_target_is_a_league_the_venue_map_can_name(self):
        for _, league in m.PLACEMENTS:
            assert league in POLYMARKET_LEAGUE_CODES, league
            assert league.startswith("soccer_") and not league.endswith("_other")

    def test_the_specimen_and_each_failure_arm_are_pinned(self):
        pinned = dict(m.PLACEMENTS)
        assert pinned[15316636] == UNL  # Portugal v Norway: two competitions
        assert pinned[15316641] == UNL  # Greece v Germany: season guard
        assert pinned[15316638] == UNL  # Republic of Ireland v Israel: name
        assert pinned[15316107] == UNL  # Croatia v England (authority's /search?q=england)
        assert pinned[15316642] == UNL  # Wales v Denmark (/search?q=wales)
        assert pinned[15317249] == UNL  # Italy v Türkiye (/search?q=italy)

    def test_the_rows_with_their_own_counterpart_are_not_pinned(self):
        pinned = dict(m.PLACEMENTS)
        for event_id in (
            15313497, 15312968, 15312967,  # Czechia, Türkiye, Bosnia and …
            15312462, 15312463, 15312464,  # Segunda: Eibar, Burgos, Valladolid
            15312261, 15319484, 15319485,  # K League, Süper Lig ×2
        ):
            assert event_id not in pinned


class TestWhereItRuns:
    def test_refuses_off_the_heavy_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert "bainluck-heavy" in m.wrong_app_refusal()
        monkeypatch.delenv("HEROKU_APP_NAME")
        assert m.wrong_app_refusal() is not None

    def test_runs_on_the_heavy_app(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        assert m.wrong_app_refusal() is None

    def test_the_backup_is_backup_prefixed_and_its_own(self):
        assert m.BACKUP.startswith("backup_5576")
