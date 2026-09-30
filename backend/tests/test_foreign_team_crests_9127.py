"""#9127 — a fuzzy ESPN hit never lends a team another school's crest.

Production 2026-09-27: searching "hornets" showed Alabama St and Delaware St with
Sacramento State's crest. ``_backfill_team_logos`` filled a crest-less row from
whatever club a token score above 0.5 picked, and ESPN's ``/teams?limit=100``
lists under a third of Division I, so an unlisted school's best hit was a listed
school with the same mascot. #8353 held the aliases to the id's bar and left the
crest on the fuzzy path; Central Arkansas, whose Razorbacks crest #8353 cleared,
wore it again within three days. Two halves pinned here: the writer
(``espn_media_may_be_written`` + ``fuzzy_hit_is_identical``, driven through the
real pass) and the repair of the thirteen rows already wearing another school.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import repair_9127_foreign_team_crests as repair  # noqa: E402
from app.services import espn_api  # noqa: E402
from app.services.espn_api import ESPNTeam  # noqa: E402
from app.tasks import espn_sync  # noqa: E402
from app.tasks.espn_sync import (  # noqa: E402
    espn_media_may_be_written,
    fuzzy_hit_is_identical,
)


def _espn(espn_id, display, short, abbr, color="000000"):
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
    )


SACRAMENTO = _espn("16", "Sacramento State Hornets", "Sacramento St", "SAC", "00573C")
ARKANSAS = _espn("8", "Arkansas Razorbacks", "Arkansas", "ARK", "a32136")
TEXAS_STATE = _espn("326", "Texas State Bobcats", "Texas St", "TXST", "501214")


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
    """Drive the real ``_backfill_team_logos`` over fake rows and a fake ESPN list."""

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
    import asyncio

    return asyncio.run(espn_sync._backfill_team_logos())


class TestTheRealPassLendsNoCrest:
    def test_the_specimen_delaware_st_stays_blank_rather_than_wear_sacramentos(self, monkeypatch):
        delaware = _team(1186, "Delaware St Hornets", ["Hornets"])
        stats = _run_pass(monkeypatch, [delaware], [SACRAMENTO, ARKANSAS])
        assert delaware.logo_url_small is None
        assert delaware.logo_url_large is None
        assert delaware.primary_color is None
        assert delaware.espn_id is None
        assert stats["fuzzy_media_refused"] == 1, stats

    def test_central_arkansas_c_arkansas_alias_does_not_borrow_the_razorbacks(self, monkeypatch):
        # "C Arkansas" drops its one-letter token and scores 1.0 against ESPN's
        # "Arkansas" — the exact shape that refilled row 724 after #8353.
        uca = _team(724, "Central Arkansas Bears", ["Bears", "C Arkansas"])
        _run_pass(monkeypatch, [uca], [ARKANSAS, SACRAMENTO])
        assert uca.logo_url_small is None

    def test_the_rows_own_name_in_other_spelling_still_fills(self, monkeypatch):
        txst = _team(702, "Texas St Bobcats", ["Bobcats"])
        stats = _run_pass(monkeypatch, [txst], [TEXAS_STATE, SACRAMENTO])
        assert txst.logo_url_small == TEXAS_STATE.logo_url
        assert txst.primary_color == "#501214"
        assert txst.espn_id is None  # the id keeps its own, stricter bar
        assert stats["fuzzy_media_refused"] == 0

    def test_an_exact_name_still_fills_and_anchors(self, monkeypatch):
        sac = _team(1126, "Sacramento State Hornets", None)
        _run_pass(monkeypatch, [sac], [SACRAMENTO])
        assert sac.logo_url_small == SACRAMENTO.logo_url
        assert sac.espn_id == "16"


class TestTheBar:
    @pytest.mark.parametrize(
        "had_media, exact, repoint, identical, expected",
        [
            (False, False, None, False, False),  # the #9127 fill: a partial score
            (False, False, None, True, True),  # same words, one club
            (True, False, None, True, False),  # never overwrites (#4750)
            (True, True, None, False, True),
            (False, True, None, False, True),
            (True, False, "999", False, True),  # a repoint is an id match
        ],
    )
    def test_table(self, had_media, exact, repoint, identical, expected):
        assert (
            espn_media_may_be_written(
                had_media=had_media,
                match_was_exact=exact,
                repointed_from=repoint,
                fuzzy_identical=identical,
            )
            is expected
        )

    def test_identical_needs_the_rows_own_name(self):
        assert fuzzy_hit_is_identical("Texas St Bobcats", "Texas St Bobcats", 1.0, {"326"})
        assert not fuzzy_hit_is_identical("C Arkansas", "Central Arkansas Bears", 1.0, {"8"})

    def test_identical_needs_one_club(self):
        assert not fuzzy_hit_is_identical("Texas St Bobcats", "Texas St Bobcats", 1.0, {"326", "147"})

    def test_identical_needs_a_full_score_and_two_words(self):
        assert not fuzzy_hit_is_identical("Delaware St Hornets", "Delaware St Hornets", 0.67, {"16"})
        assert not fuzzy_hit_is_identical("Harvard", "Harvard", 1.0, {"108"})


def _read_row(state: dict, name: str) -> dict:
    return {
        "name": name,
        "espn_id": state["espn_id"],
        "abbreviation": state["abbreviation"],
        "logo_url_small": state["logo"],
        "logo_url_large": state["logo"],
        "primary_color": state["primary_color"],
        "secondary_color": state["secondary_color"],
        "alternate_names": list(reversed(state["alternate_names"])),  # order-free
    }


class TestTheRepair:
    def test_it_refuses_off_production(self):
        with pytest.raises(repair.Refused):
            repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck-staging"})
        repair.refuse_unless_production({"HEROKU_APP_NAME": "bainluck"})

    def test_the_population_is_thirteen_rows_none_keeping_a_foreign_crest(self):
        assert len(repair.PINNED) == 13
        for team_id, row in repair.PINNED.items():
            assert row.before["logo"] != row.after["logo"], team_id
            assert row.after["logo"].endswith(f"/{row.after['espn_id']}.png"), team_id

    def test_the_specimens(self):
        alabama = repair.PINNED[1209]
        assert alabama.name == "Alabama St Hornets"
        assert (alabama.before["espn_id"], alabama.before["abbreviation"]) == ("16", "SAC")
        assert (alabama.after["espn_id"], alabama.after["abbreviation"]) == ("2011", "ALST")
        assert repair.PINNED[1186].after["espn_id"] == "2169"
        assert repair.PINNED[724].after["logo"].endswith("/2110.png")

    def test_no_after_alias_is_another_schools(self):
        foreign = {
            "Sacramento St",
            "Sacramento State Hornets",
            "Michigan St",
            "Michigan State Spartans",
            "Montana St",
            "Montana State Bobcats",
            "San Diego St",
            "San Diego State Aztecs",
            "Aztecs",
            "Mount St Marys",
            "Mount St. Mary's Mountaineers",
            "Fairleigh Dickinson Knights",
            "FDU",
            "East Carolina",
            "East Carolina Pirates",
        }
        for team_id, row in repair.PINNED.items():
            assert not foreign & set(row.after["alternate_names"]), team_id
            assert row.name not in row.after["alternate_names"], team_id

    def test_no_two_pinned_rows_in_one_sport_share_an_after_id(self):
        # 1186/8990 share 2169 across ncaab and wncaab — that is ESPN's scheme.
        by_id = {}
        for team_id, row in repair.PINNED.items():
            by_id.setdefault(row.after["espn_id"], []).append(team_id)
        assert all(len(ids) <= 2 for ids in by_id.values()), by_id

    def test_plan_writes_rows_holding_before_and_skips_the_rest(self):
        rows = {i: _read_row(r.before, r.name) for i, r in repair.PINNED.items()}
        rows[724]["logo_url_small"] = None  # touched since the pin
        rows[1209] = _read_row(repair.PINNED[1209].after, "Alabama St Hornets")
        del rows[2873]
        got = repair.plan(rows, restore=False)
        written = {w[0] for w in got["write"]}
        assert written == set(repair.PINNED) - {724, 1209, 2873}
        assert dict(got["skip"]) == {
            724: "changed since the pin",
            1209: "already repaired",
            2873: "row missing",
        }

    def test_restore_writes_before_only_where_the_row_holds_after(self):
        rows = {i: _read_row(r.after, r.name) for i, r in repair.PINNED.items()}
        rows[1066]["abbreviation"] = "XXX"
        got = repair.plan(rows, restore=True)
        assert {w[0] for w in got["write"]} == set(repair.PINNED) - {1066}
        for team_id, want_from, want_to in got["write"]:
            assert want_to == repair.PINNED[team_id].before

    def test_a_renamed_row_refuses_the_whole_run(self):
        rows = {i: _read_row(r.before, r.name) for i, r in repair.PINNED.items()}
        rows[1186]["name"] = "Someone Else"
        with pytest.raises(repair.Refused):
            repair.plan(rows, restore=False)

    def test_the_update_carries_its_own_compare_and_swap(self):
        sql = str(repair._UPDATE)
        for clause in (
            "espn_id IS NOT DISTINCT FROM :from_espn_id",
            "logo_url_small IS NOT DISTINCT FROM :from_logo",
            "logo_url_large IS NOT DISTINCT FROM :from_logo",
            "primary_color IS NOT DISTINCT FROM :from_primary_color",
            "alternate_names @> CAST(:from_alternate_names AS jsonb)",
            "alternate_names <@ CAST(:from_alternate_names AS jsonb)",
        ):
            assert clause in sql
        params = repair.update_params(1209, repair.PINNED[1209].before, repair.PINNED[1209].after)
        assert params["from_espn_id"] == "16" and params["to_espn_id"] == "2011"
