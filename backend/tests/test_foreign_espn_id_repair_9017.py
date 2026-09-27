"""#9017 — Miami (OH) stops wearing Miami's ESPN id, crest and record.

**SHIP: searching "miami hurricanes" (or Florida, Texas, Oregon) stops showing a
different school with the Hurricanes' crest and record.** (Pillar: TRUTH.)

`scripts/repair_9017_foreign_espn_id.py` clears a team row's ESPN identity only
when the row's own name is the name of a DIFFERENT team in ESPN's directory.
These witnesses use the values ESPN's college-baseball, NBA and college-football
directories returned on 2026-09-27, so a green here is about the real payloads.
"""

from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace

import pytest


def _team(espn_id, display_name, name, short_name, nickname, location):
    from app.services.espn_api import ESPNTeam

    return ESPNTeam(
        espn_id=espn_id,
        name=name,
        abbreviation=None,
        display_name=display_name,
        short_name=short_name,
        nickname=nickname,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
        location=location,
    )


def _baseball():
    return [
        _team("176", "Miami Hurricanes", "Hurricanes", "Miami", "Miami", "Miami"),
        _team("107", "Miami (OH) RedHawks", "RedHawks", "Miami OH", "Miami OH", "Miami (OH)"),
        _team("126", "Texas Longhorns", "Longhorns", "Texas", "Texas", "Texas"),
        _team("147", "Texas State Bobcats", "Bobcats", "Texas St", "Texas St", "Texas State"),
        _team("75", "Florida Gators", "Gators", "Florida", "Florida", "Florida"),
        _team("296", "North Florida Ospreys", "Ospreys", "North Florida", "North Florida", "North Florida"),
        _team("110", "Oklahoma State Cowboys", "Cowboys", "Oklahoma St", "Oklahoma St", "Oklahoma State"),
        _team("399", "Nicholls Colonels", "Colonels", "Nicholls", "Nicholls", "Nicholls"),
    ]


def _nba():
    return [
        _team("12", "LA Clippers", "Clippers", "Clippers", "LA", "LA"),
        _team("13", "Los Angeles Lakers", "Lakers", "Lakers", "Los Angeles", "Los Angeles"),
    ]


def _fcs():
    return [
        _team("2166", "Davidson Wildcats", "Wildcats", "Davidson", "Davidson", "Davidson"),
        _team("2065", "Bethune-Cookman Wildcats", "Wildcats", "Bethune", "Bethune", "Bethune-Cookman"),
    ]


def _verdict(name, espn_id, directory):
    from scripts.repair_9017_foreign_espn_id import names_another_espn_club

    owner = next(t for t in directory if t.espn_id == espn_id)
    return [t.display_name for t in names_another_espn_club(name, owner, directory)]


class TestTheProductionSpecimens:
    """Rows production held on 2026-09-27, each wearing another school's id."""

    def test_miami_oh_holding_miamis_id_is_foreign(self):
        assert _verdict("Miami (OH)", "176", _baseball()) == ["Miami (OH) RedHawks"]

    def test_texas_state_holding_texass_id_is_foreign(self):
        assert _verdict("Texas State", "126", _baseball()) == ["Texas State Bobcats"]

    def test_florida_and_north_florida_holding_each_others_ids_are_both_foreign(self):
        assert _verdict("Florida", "296", _baseball()) == ["Florida Gators"]
        assert _verdict("North Florida", "75", _baseball()) == ["North Florida Ospreys"]

    def test_the_in_season_fcs_row_is_foreign(self):
        assert _verdict("Bethune-Cookman Wildcats", "2166", _fcs()) == [
            "Bethune-Cookman Wildcats"
        ]


class TestTheRowsItMustKeep:
    """The same subset shape, on rows whose id is right."""

    def test_miami_fl_names_no_other_espn_team(self):
        # ESPN calls it "Miami", not "Miami (FL)". A token-shape veto refused it.
        assert _verdict("Miami (FL)", "176", _baseball()) == []

    def test_nicholls_state_where_espn_dropped_the_state(self):
        assert _verdict("Nicholls State", "399", _baseball()) == []

    def test_an_abbreviated_spelling_of_its_own_club(self):
        assert _verdict("Oklahoma St Cowboys", "110", _baseball()) == []

    def test_the_owner_named_exactly(self):
        assert _verdict("Miami Hurricanes", "176", _baseball()) == []
        assert _verdict("Texas", "126", _baseball()) == []

    def test_the_clippers_fragment_row_is_not_read_as_the_lakers(self):
        # `normalize_name` strips the trailing "c" and turns this row into
        # "los angeles", the Lakers' location. Light normalization does not.
        from app.utils.name_normalization import normalize_name

        assert normalize_name("Los Angeles C") == "los angeles"
        assert _verdict("Los Angeles C", "12", _nba()) == []

    def test_no_owner_or_no_name_keeps_the_row(self):
        from scripts.repair_9017_foreign_espn_id import names_another_espn_club

        assert names_another_espn_club("Miami (OH)", None, _baseball()) == []
        owner = _baseball()[0]
        assert names_another_espn_club("", owner, _baseball()) == []


class TestThePlan:
    def _row(self, id, name, sport_key, espn_id):
        return SimpleNamespace(
            id=id, name=name, sport_key=sport_key, espn_id=espn_id, current_record=None
        )

    def test_the_plan_picks_the_foreign_rows_and_says_what_it_did_not_judge(self):
        from scripts.repair_9017_foreign_espn_id import plan

        rows = [
            self._row(2862, "Miami Hurricanes", "baseball_ncaa", "176"),
            self._row(14629, "Miami (OH)", "baseball_ncaa", "176"),
            self._row(14631, "Miami (FL)", "baseball_ncaa", "176"),
            self._row(12649, "Los Angeles C", "basketball_nba", "12"),
            self._row(1, "Somebody", "baseball_ncaa", "999999"),
            self._row(2, "Boston University", "lacrosse_ncaa", "104"),
        ]
        foreign, skipped = plan(
            rows,
            {"baseball_ncaa": _baseball(), "basketball_nba": _nba(), "lacrosse_ncaa": None},
        )
        assert [r.id for r, _, _ in foreign] == [14629]
        assert skipped == {"lacrosse_ncaa": 1, "(id not in directory)": 1}


class TestFetchDirectory:
    class _Svc:
        def __init__(self, result):
            self.result = result
            self.urls = []

        def _get_espn_path(self, sport_key):
            return ("baseball", "college-baseball") if sport_key == "baseball_ncaa" else None

        async def _get(self, url):
            self.urls.append(url)
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

        def _parse_team(self, raw):
            from app.services.espn_api import ESPNAPIService

            return ESPNAPIService()._parse_team(raw)

    def _run(self, svc, key="baseball_ncaa"):
        from scripts.repair_9017_foreign_espn_id import fetch_directory

        return asyncio.run(fetch_directory(svc, key))

    def test_reads_the_whole_directory_not_the_first_hundred(self):
        body = {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {
                                    "team": {
                                        "id": "176",
                                        "displayName": "Miami Hurricanes",
                                        "name": "Hurricanes",
                                        "location": "Miami",
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        svc = self._Svc(body)
        teams = self._run(svc)
        assert svc.urls[0].endswith("/baseball/college-baseball/teams?limit=1000")
        assert [t.espn_id for t in teams] == ["176"]

    @pytest.mark.parametrize(
        "result", [{"sports": [{"leagues": [{"teams": []}]}]}, {}, None]
    )
    def test_an_empty_directory_is_unread_not_empty(self, result):
        assert self._run(self._Svc(result)) is None

    def test_espn_dark_is_unread(self):
        from app.services.espn_api import ESPNAuthorityDark

        assert self._run(self._Svc(ESPNAuthorityDark("timeout"))) is None

    def test_no_mapping_is_unread(self):
        assert self._run(self._Svc({}), key="lacrosse_nowhere") is None


class TestTheWriteGates:
    def test_writes_refuse_off_the_producer_app(self, monkeypatch):
        from scripts.repair_9017_foreign_espn_id import wrong_app_refusal

        args = argparse.Namespace(apply=False, backup=True)
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        assert "REFUSING" in wrong_app_refusal(args)
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        assert "REFUSING" in wrong_app_refusal(args)
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        assert wrong_app_refusal(args) is None
        monkeypatch.delenv("HEROKU_APP_NAME")
        assert wrong_app_refusal(argparse.Namespace(apply=False, backup=False)) is None

    def test_apply_without_backup_refuses_before_any_read(self, monkeypatch, capsys):
        from scripts import repair_9017_foreign_espn_id as repair

        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        rc = asyncio.run(repair.run(argparse.Namespace(apply=True, backup=False)))
        assert rc == 2
        assert "--apply without --backup" in capsys.readouterr().out

    def test_the_restore_puts_back_every_field_the_repair_clears(self):
        import inspect

        from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS
        from scripts import repair_9017_foreign_espn_id as repair
        from scripts.restore_9017_foreign_espn_id import _RESTORE_SQL, RESTORED_FIELDS

        assert RESTORED_FIELDS == ("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)
        for field in RESTORED_FIELDS:
            assert f"{field} = COALESCE(t.{field}, b.{field})" in _RESTORE_SQL
        # The repair's UPDATE clears exactly that tuple.
        src = inspect.getsource(repair.run)
        assert '("espn_id", *ESPN_SOURCED_IDENTITY_FIELDS)' in src
