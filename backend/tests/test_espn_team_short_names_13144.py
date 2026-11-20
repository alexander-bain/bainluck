"""#13144 — ESPN team list truncation (limit=100) and St/State short-name fill.

Production audit:
1. ``ESPNAPIService.get_teams`` requested ``/teams?limit=100``, cutting off
   Division I college rosters alphabetically around F (NCAAB ~365, WNCAAB ~363,
   NCAAF ~763), leaving 129 NCAAB, 116 WNCAAB, and 85 NCAA baseball rows with
   no short name (e.g. Penn State Nittany Lions).
2. Already-crested ``St`` vs ``State`` rows (e.g. Sacramento St Hornets, Murray
   St Racers) scored ``fuzzy_identical=True`` (score 1.0 on the row's own
   multi-word name, unique ESPN club), but ``espn_media_may_be_written``
   rightfully refused to overwrite existing media (#4750/#9127) and skipped
   filling the blank ``abbreviation`` as well.

This test pins both fixes while preserving #9127 (partial fuzzy / alias hits
never write crests or short names), #8353 (fuzzy hits never write aliases),
#4750 (existing crests/abbreviations are never overwritten), and #5697
(group-scoped boards such as FCS still return ``[]`` without calling ``/teams``).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.services import espn_api
from app.services.espn_api import ESPNAPIService, ESPNTeam
from app.tasks import espn_sync
from app.tasks.espn_sync import (
    espn_abbreviation_may_be_written,
    espn_id_name_agrees,
)


def _espn(espn_id, display, short, abbr, color="000000", *, location=None):
    return ESPNTeam(
        espn_id=espn_id,
        name=display.split()[-1],
        abbreviation=abbr,
        display_name=display,
        short_name=short,
        nickname=short,
        primary_color=f"#{color}",
        secondary_color="#ffffff",
        logo_url=f"https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png",
        logo_url_dark=None,
        record=None,
        location=location,
    )


SACRAMENTO = _espn(
    "16", "Sacramento State Hornets", "Sacramento St", "SAC", "00573C",
    location="Sacramento State",
)
MURRAY = _espn(
    "93", "Murray State Racers", "Murray St", "MUR", "002144",
    location="Murray State",
)
PENN_STATE = _espn(
    "213", "Penn State Nittany Lions", "Penn State", "PSU", "041E42",
    location="Penn State",
)
TEXAS_STATE = _espn(
    "326", "Texas State Bobcats", "Texas St", "TXST", "501214",
    location="Texas State",
)
ARKANSAS = _espn(
    "8", "Arkansas Razorbacks", "Arkansas", "ARK", "a32136",
    location="Arkansas",
)
VIKING = _espn(
    "510", "Viking FK", "Viking", "VFK", "00205b",
    location="Viking",
)


def _team(team_id, name, aliases=None, *, espn_id=None, logo=None, abbreviation=None):
    return SimpleNamespace(
        id=team_id,
        name=name,
        alternate_names=aliases,
        espn_id=espn_id,
        logo_url_small=logo,
        logo_url_large=logo,
        abbreviation=abbreviation,
        primary_color=None,
        secondary_color=None,
    )


def _run_pass(monkeypatch, teams, espn_teams, sport_key="basketball_ncaab"):
    class _Result:
        def all(self):
            return [(t, sport_key) for t in teams]

    class _Session:
        async def execute(self, *_a, **_k):
            return _Result()

    @asynccontextmanager
    async def _session_cm():
        yield _Session()

    class _FakeESPN:
        async def get_teams(self, _sport_key):
            return list(espn_teams)

        async def close(self):
            return None

    monkeypatch.setattr(espn_sync, "get_task_session", _session_cm)
    monkeypatch.setattr(espn_api, "ESPNAPIService", _FakeESPN)
    return asyncio.run(espn_sync._backfill_team_logos())


class TestGetTeamsLimit1000:
    @pytest.mark.parametrize(
        "sport_key, expected_path",
        [
            ("basketball_ncaab", "/basketball/mens-college-basketball/teams?limit=1000"),
            ("basketball_wncaab", "/basketball/womens-college-basketball/teams?limit=1000"),
            ("americanfootball_ncaaf", "/football/college-football/teams?limit=1000"),
            ("baseball_ncaa", "/baseball/college-baseball/teams?limit=1000"),
        ],
    )
    def test_get_teams_requests_full_roster_limit_1000(self, sport_key, expected_path):
        svc = ESPNAPIService()
        seen_urls: list[str] = []

        async def fake_get(url):
            seen_urls.append(url)
            return {"sports": [{"leagues": [{"teams": []}]}]}

        svc._get = fake_get  # type: ignore[assignment]
        got = asyncio.run(svc.get_teams(sport_key))
        assert got == []
        assert len(seen_urls) == 1
        assert seen_urls[0].endswith(expected_path), seen_urls[0]

    def test_group_scoped_fcs_board_still_skips_teams_endpoint(self):
        svc = ESPNAPIService()
        called = False

        async def fake_get(url):
            nonlocal called
            called = True
            return {}

        svc._get = fake_get  # type: ignore[assignment]
        assert asyncio.run(svc.get_teams("americanfootball_ncaaf_fcs")) == []
        assert not called


class TestAbbreviationWriteGate:
    @pytest.mark.parametrize(
        "has_abbr, exact, repoint, identical, expected",
        [
            (False, True, None, False, True),
            (False, False, "999", False, True),
            (False, False, None, True, True),  # Sacramento St Hornets -> SAC
            (False, False, None, False, False),  # partial fuzzy / alias refused
            (True, True, None, False, False),  # never overwrites populated abbr
            (True, False, None, True, False),
            (True, False, "999", False, False),
        ],
    )
    def test_table(self, has_abbr, exact, repoint, identical, expected):
        assert (
            espn_abbreviation_may_be_written(
                has_abbreviation=has_abbr,
                match_was_exact=exact,
                repointed_from=repoint,
                fuzzy_identical=identical,
            )
            is expected
        )


class TestBackfillShortNamesPass:
    def test_crested_st_state_rows_fill_only_abbreviation_leaving_media_and_identity_untouched(
        self, monkeypatch
    ):
        existing_logo = "https://a.espncdn.com/i/teamlogos/ncaa/500/16.png"
        sac = _team(1126, "Sacramento St Hornets", ["Hornets"], logo=existing_logo)
        mur = _team(
            1141,
            "Murray St Racers",
            ["Racers"],
            logo="https://a.espncdn.com/i/teamlogos/ncaa/500/93.png",
        )
        stats = _run_pass(monkeypatch, [sac, mur], [SACRAMENTO, MURRAY, ARKANSAS])

        assert sac.abbreviation == "SAC"
        assert sac.logo_url_small == existing_logo
        assert sac.primary_color is None
        assert sac.espn_id is None
        assert sac.alternate_names == ["Hornets"]

        assert mur.abbreviation == "MUR"
        assert mur.espn_id is None
        assert stats["teams_updated"] == 2
        assert stats["fuzzy_media_refused"] == 0

    def test_exact_match_beyond_old_100_cutoff_fills_short_name_and_espn_id(self, monkeypatch):
        psu = _team(2559, "Penn State Nittany Lions", None)
        stats = _run_pass(monkeypatch, [psu], [PENN_STATE])

        assert psu.abbreviation == "PSU"
        assert psu.espn_id == "213"
        assert psu.logo_url_small == PENN_STATE.logo_url
        assert stats["teams_updated"] == 1

    def test_uncrested_st_state_row_fills_crest_and_abbreviation_without_anchoring_espn_id(
        self, monkeypatch
    ):
        txst = _team(702, "Texas St Bobcats", ["Bobcats"])
        stats = _run_pass(monkeypatch, [txst], [TEXAS_STATE, SACRAMENTO])

        assert txst.abbreviation == "TXST"
        assert txst.logo_url_small == TEXAS_STATE.logo_url
        assert txst.espn_id is None
        assert txst.alternate_names == ["Bobcats"]
        assert stats["teams_updated"] == 1

    def test_partial_fuzzy_and_alias_hits_still_refuse_abbreviation(self, monkeypatch):
        delaware = _team(1186, "Delaware St Hornets", ["Hornets"])
        uca = _team(724, "Central Arkansas Bears", ["Bears", "C Arkansas"])
        stats = _run_pass(monkeypatch, [delaware, uca], [SACRAMENTO, ARKANSAS])

        assert delaware.abbreviation is None
        assert delaware.logo_url_small is None
        assert uca.abbreviation is None
        assert uca.logo_url_small is None
        assert stats["fuzzy_media_refused"] == 2
        assert stats["teams_updated"] == 0

    def test_existing_abbreviation_is_never_overwritten(self, monkeypatch):
        sac = _team(
            1126,
            "Sacramento St Hornets",
            logo="https://a.espncdn.com/i/teamlogos/ncaa/500/16.png",
            abbreviation="KEEP",
        )
        stats = _run_pass(monkeypatch, [sac], [SACRAMENTO])

        assert sac.abbreviation == "KEEP"
        assert stats["teams_updated"] == 0
        assert stats["fuzzy_media_refused"] == 1

    def test_stored_espn_id_pointing_to_another_school_stays_blank_and_logs_row_id(
        self, monkeypatch, caplog
    ):
        # #12762 / #13144: Stanford carrying Arkansas's ESPN id with a blank
        # short name (even with a contaminated alias) must stay completely
        # blank and count as `espn_id_name_disagreement` with its row id logged.
        stanford = _team(
            2401,
            "Stanford Cardinal",
            aliases=["Arkansas Razorbacks"],
            espn_id="8",
            logo=None,
            abbreviation=None,
        )
        qarabag = _team(
            2298,
            "Qarabağ FK",
            espn_id="510",
            logo=None,
            abbreviation=None,
        )
        delaware = _team(
            1186,
            "Delaware St Hornets",
            espn_id="16",
            logo=None,
            abbreviation=None,
        )
        with caplog.at_level("WARNING", logger="app.tasks.espn_sync"):
            stats = _run_pass(
                monkeypatch,
                [stanford, qarabag, delaware],
                [ARKANSAS, VIKING, SACRAMENTO],
            )

        for row in (stanford, qarabag, delaware):
            assert row.abbreviation is None
            assert row.logo_url_small is None
            assert row.primary_color is None
        assert stanford.alternate_names == ["Arkansas Razorbacks"]
        assert stats["espn_id_name_disagreement"] == 3
        assert stats["teams_updated"] == 0
        assert "2401" in caplog.text
        assert "2298" in caplog.text
        assert "1186" in caplog.text

    def test_stored_espn_id_agreeing_on_name_fills_blank_short_name(self, monkeypatch):
        psu = _team(2559, "Penn State Nittany Lions", espn_id="213", abbreviation=None)
        sac = _team(1126, "Sacramento St Hornets", espn_id="16", abbreviation=None)
        stats = _run_pass(monkeypatch, [psu, sac], [PENN_STATE, SACRAMENTO])

        assert psu.abbreviation == "PSU"
        assert sac.abbreviation == "SAC"
        assert stats["espn_id_name_disagreement"] == 0
        assert stats["teams_updated"] == 2

    def test_dry_run_sets_read_only_records_planned_writes_and_rolls_back(
        self, monkeypatch
    ):
        sac = _team(
            1126,
            "Sacramento St Hornets",
            logo="https://a.espncdn.com/i/teamlogos/ncaa/500/16.png",
            abbreviation=None,
        )
        psu = _team(2559, "Penn State Nittany Lions", abbreviation=None)
        events: list[str] = []

        class _Result:
            def all(self):
                return [(sac, "basketball_ncaab"), (psu, "basketball_ncaab")]

        class _DrySession:
            async def execute(self, stmt, *_a, **_k):
                sql = str(stmt)
                if "SET TRANSACTION READ ONLY" in sql:
                    events.append("read_only")
                    return None
                return _Result()

            def expunge_all(self):
                events.append("expunge_all")

            async def rollback(self):
                events.append("rollback")

        @asynccontextmanager
        async def _session_cm():
            yield _DrySession()

        class _FakeESPN:
            async def get_teams(self, _sport_key):
                return [SACRAMENTO, PENN_STATE]

            async def close(self):
                return None

        monkeypatch.setattr(espn_sync, "get_task_session", _session_cm)
        monkeypatch.setattr(espn_api, "ESPNAPIService", _FakeESPN)

        stats = asyncio.run(espn_sync._backfill_team_logos(dry_run=True))

        assert events == ["read_only", "expunge_all", "rollback"]
        assert stats["teams_updated"] == 2
        by_id = {w["team_id"]: w for w in stats["planned_writes"]}
        assert by_id[1126] == {
            "team_id": 1126,
            "sport_key": "basketball_ncaab",
            "name": "Sacramento St Hornets",
            "current_abbr": None,
            "new_abbr": "SAC",
            "crest_changed": False,
            "color_changed": False,
            "espn_id_changed": False,
            "new_espn_id": None,
            "match_kind": "fuzzy_identical_abbr_only",
        }
        assert by_id[2559] == {
            "team_id": 2559,
            "sport_key": "basketball_ncaab",
            "name": "Penn State Nittany Lions",
            "current_abbr": None,
            "new_abbr": "PSU",
            "crest_changed": True,
            "color_changed": True,
            "espn_id_changed": True,
            "new_espn_id": "213",
            "match_kind": "exact",
        }


class TestEspnIdNameAgreement:
    @pytest.mark.parametrize(
        "db_name, espn_team, expected",
        [
            ("Sacramento St Hornets", SACRAMENTO, True),
            ("Murray St Racers", MURRAY, True),
            ("Penn State Nittany Lions", PENN_STATE, True),
            ("Texas St Bobcats", TEXAS_STATE, True),
            ("Stanford Cardinal", ARKANSAS, False),
            ("Qarabağ FK", VIKING, False),
            ("Delaware St Hornets", SACRAMENTO, False),
            ("Central Arkansas Bears", ARKANSAS, False),
            ("Alabama St Hornets", SACRAMENTO, False),
            ("Oklahoma State", _espn("197", "Missouri State Bears", "Missouri St", "MOST", location="Missouri State"), False),
            ("West Virginia Mountaineers", _espn("258", "Virginia Cavaliers", "Virginia", "UVA", location="Virginia"), False),
            ("Michigan State", _espn("127", "BYU Cougars", "BYU", "BYU", location="BYU"), False),
        ],
    )
    def test_agreement_cases(self, db_name, espn_team, expected):
        assert espn_id_name_agrees(db_name, espn_team) is expected
