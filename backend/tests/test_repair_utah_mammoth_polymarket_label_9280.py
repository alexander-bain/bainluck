"""#9280 — the Utah Mammoth row answers to the name Polymarket calls the club.

Two halves. The script half grades the repair's decisions, its compare-and-set,
its refusals and that the undo is the inverse of the apply. The resolver half
grades what the ship claims: that ``covered_league_for_matchup``, which both the
#5544 minting refusal and #7904's retired-row relink call, resolves Polymarket's
"Blackhawks vs. Utah" to the NHL once row 118 carries ``Utah`` (and NOT before),
and that the college and NBA matchups the same label already reaches do not
move. The rows are production's, as read 2026-09-28 03:3xZ.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.tasks.prediction_market_matching import covered_league_for_matchup

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "repair_9280_utah_mammoth_polymarket_label.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("repair_9280_unit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_9280_unit"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()
MAMMOTH = 118
BEFORE = ["Mammoth"]


def _at_before():
    return {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", list(BEFORE))}


def _applied():
    return {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", list(BEFORE) + ["Utah"])}


class TestThePin:
    def test_exactly_the_one_row(self):
        assert m.PINNED == {
            MAMMOTH: ("icehockey_nhl", "Utah Mammoth", "Utah", BEFORE),
        }

    def test_the_before_list_did_not_already_hold_the_label(self):
        """The undo removes exactly ``Utah``. That is only the inverse of the
        apply if the row did not hold it before, the proof the docstring leans on."""
        assert all(b.strip().lower() != "utah" for b in BEFORE)


class TestApplyPlan:
    def test_the_label_is_appended_and_the_rest_kept(self):
        out = m.plan(_at_before(), restore=False)
        assert out == {
            "write": [(MAMMOTH, ["Mammoth"], ["Mammoth", "Utah"])],
            "skip": [],
        }

    def test_a_name_an_espn_sync_added_since_the_read_survives(self):
        rows = {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", ["Mammoth", "UTA"])}
        assert m.plan(rows, restore=False)["write"] == [
            (MAMMOTH, ["Mammoth", "UTA"], ["Mammoth", "UTA", "Utah"]),
        ]

    def test_already_present_in_any_case_is_skipped(self):
        rows = {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", ["Mammoth", "UTAH"])}
        out = m.plan(rows, restore=False)
        assert out["write"] == []
        assert out["skip"] == [(MAMMOTH, "'Utah' already present")]

    def test_null_alternate_names_gets_the_label_alone(self):
        rows = {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", None)}
        assert m.plan(rows, restore=False)["write"] == [(MAMMOTH, [], ["Utah"])]

    @pytest.mark.parametrize("restore", [False, True])
    def test_a_missing_row_refuses_the_run_in_both_modes(self, restore):
        # CERT-3684 follow-up: a skip here exited 0 and read as a clean plan.
        with pytest.raises(m.Refused, match="not found"):
            m.plan({}, restore=restore)

    @pytest.mark.parametrize(
        "sport_key,name",
        [
            ("basketball_nba", "Utah Jazz"),
            ("icehockey_nhl_preseason", "Utah Mammoth"),
            ("icehockey_nhl", "Utah Hockey Club"),
        ],
    )
    def test_an_id_that_names_another_team_refuses_the_run(self, sport_key, name):
        with pytest.raises(m.Refused):
            m.plan({MAMMOTH: (sport_key, name, [])}, restore=False)


class TestRestorePlan:
    def test_restore_is_the_inverse_of_apply(self):
        assert m.plan(_applied(), restore=True) == {
            "write": [(MAMMOTH, ["Mammoth", "Utah"], ["Mammoth"])],
            "skip": [],
        }

    def test_restore_keeps_a_name_synced_in_after_the_repair(self):
        rows = {MAMMOTH: ("icehockey_nhl", "Utah Mammoth", ["Mammoth", "Utah", "UTA"])}
        assert m.plan(rows, restore=True)["write"][0][2] == ["Mammoth", "UTA"]

    def test_restore_before_apply_is_a_no_op(self):
        out = m.plan(_at_before(), restore=True)
        assert out["write"] == []
        assert out["skip"] == [(MAMMOTH, "'Utah' absent, nothing to undo")]


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def __iter__(self):
        return iter(self._rows)


class _TeamRow:
    def __init__(self, id, sport_key, name, alternate_names):
        self.id = id
        self.sport_key = sport_key
        self.name = name
        self.alternate_names = alternate_names


class _Session:
    def __init__(self, rows, update_rowcount=1):
        self._rows = rows
        self._update_rowcount = update_rowcount
        self.updates: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("SELECT"):
            assert params["ids"] == [MAMMOTH]
            return _Result(self._rows)
        self.updates.append((sql, params))
        return _Result(rowcount=self._update_rowcount)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def _rows(names, as_text=False):
    value = json.dumps(names) if (as_text and names is not None) else names
    return [_TeamRow(MAMMOTH, "icehockey_nhl", "Utah Mammoth", value)]


class TestRun:
    def test_dry_run_writes_nothing(self):
        s = _Session(_rows(list(BEFORE)))
        out = asyncio.run(m.run(s, apply=False, restore=False))
        assert out["mode"] == "dry-run" and len(out["write"]) == 1
        assert s.updates == [] and not s.committed

    @pytest.mark.parametrize("as_text", [False, True])
    def test_apply_issues_one_compare_and_set(self, as_text):
        s = _Session(_rows(list(BEFORE), as_text=as_text))
        out = asyncio.run(m.run(s, apply=True, restore=False))
        assert out["written"] == 1 and s.committed
        [(sql, params)] = s.updates
        assert params["id"] == MAMMOTH
        assert json.loads(params["current"]) == ["Mammoth"]
        assert json.loads(params["new"]) == ["Mammoth", "Utah"]
        assert sql.startswith("UPDATE teams SET alternate_names")
        assert "IS NOT DISTINCT FROM CAST(:current AS jsonb)" in sql

    def test_a_null_row_compares_against_sql_null(self):
        s = _Session(_rows(None))
        asyncio.run(m.run(s, apply=True, restore=False))
        assert s.updates[0][1]["current"] is None

    def test_a_write_that_changes_no_row_refuses_and_commits_nothing(self):
        s = _Session(_rows(list(BEFORE)), update_rowcount=0)
        with pytest.raises(m.Refused):
            asyncio.run(m.run(s, apply=True, restore=False))
        assert not s.committed


class TestRefusals:
    @pytest.mark.parametrize("app", ["", "bainluck-staging", "local"])
    def test_refuses_off_production(self, app):
        with pytest.raises(m.Refused):
            m.refuse_unless_production({"HEROKU_APP_NAME": app})

    @pytest.mark.parametrize("app", ["bainluck", "bainluck-heavy"])
    def test_runs_on_production(self, app):
        m.refuse_unless_production({"HEROKU_APP_NAME": app})


# ---------------------------------------------------------------------------
# The resolver half: what the one appended name does to the answer both
# #5544's minting refusal and #7904's relink read.
# ---------------------------------------------------------------------------


class _ClubRow:
    """One `teams`-joined-`sports` row as the resolver's query returns it."""

    def __init__(self, name, alternates, sport_key):
        self._values = (name, alternates, sport_key)

    def __iter__(self):
        return iter(self._values)


class _ClubSession:
    """Returns every row regardless of predicate, as #5544's own file does, so
    this grades the exact-match + intersection logic, not SQL."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, statement):
        return list(self._rows)


def _clubs(mammoth_alternates):
    # Production's rows (db-query 2026-09-28 03:3xZ), trimmed to the ones these
    # matchups can touch. Utah Jazz already carries `Utah`; so do the Utes.
    return [
        _ClubRow("Utah Mammoth", mammoth_alternates, "icehockey_nhl"),
        _ClubRow("Utah Mammoth", None, "icehockey_nhl_preseason"),
        _ClubRow("Chicago Blackhawks", ["Chicago", "Blackhawks"], "icehockey_nhl"),
        _ClubRow("New York Rangers", ["New York R", "Rangers", "New York Rangers"],
                 "icehockey_nhl"),
        _ClubRow("Tampa Bay Lightning", ["Tampa Bay Lightning", "Tampa Bay", "Lightning"],
                 "icehockey_nhl"),
        _ClubRow("Colorado Avalanche", ["Colorado", "Avalanche", "Colorado Avalanche"],
                 "icehockey_nhl"),
        _ClubRow("Utah Jazz", ["Utah", "Jazz"], "basketball_nba"),
        _ClubRow("Denver Nuggets", ["Denver", "Nuggets"], "basketball_nba"),
        _ClubRow("Utah Utes", ["Utes", "Utah"], "americanfootball_ncaaf"),
        _ClubRow("Iowa State Cyclones", ["Iowa State", "Cyclones"],
                 "americanfootball_ncaaf"),
        _ClubRow("Colorado Buffaloes", ["Colorado", "Buffaloes"],
                 "americanfootball_ncaaf"),
    ]


BEFORE_CLUBS = _clubs(list(BEFORE))
AFTER_CLUBS = _clubs(list(BEFORE) + ["Utah"])


def _resolve(rows, a, b, **kw):
    return asyncio.run(covered_league_for_matchup(_ClubSession(rows), a, b, **kw))


class TestTheShip:
    """Polymarket's own titles for Utah Mammoth games, both orientations."""

    @pytest.mark.parametrize(
        "a,b",
        [
            ("Blackhawks", "Utah"),   # 60199695, stuck on voided 15304618
            ("Utah", "Rangers"),      # 60393522, phantom 15307143
            ("Utah", "Lightning"),    # minted 2026-09-27 16:23Z as 15320100
        ],
    )
    @pytest.mark.parametrize("unambiguous_only", [False, True])
    def test_resolves_to_the_nhl_after_and_to_nothing_before(self, a, b, unambiguous_only):
        assert _resolve(BEFORE_CLUBS, a, b, unambiguous_only=unambiguous_only) is None
        assert (
            _resolve(AFTER_CLUBS, a, b, unambiguous_only=unambiguous_only)
            == "icehockey_nhl"
        )


class TestWhatDoesNotMove:
    @pytest.mark.parametrize(
        "a,b,league",
        [
            ("Iowa State", "Utah", "americanfootball_ncaaf"),
            ("Utah", "Iowa State", "americanfootball_ncaaf"),
            ("Utah", "Denver", "basketball_nba"),
        ],
    )
    @pytest.mark.parametrize("unambiguous_only", [False, True])
    def test_college_and_nba_matchups_resolve_where_they_did(self, a, b, league, unambiguous_only):
        before = _resolve(BEFORE_CLUBS, a, b, unambiguous_only=unambiguous_only)
        after = _resolve(AFTER_CLUBS, a, b, unambiguous_only=unambiguous_only)
        assert before == after == league


class TestTheDeclaredStricterCase:
    """An opponent spelled as a city that is ALSO an NHL row's alternate.

    "Utah vs. Colorado" (football) was {ncaaf}; with the label it is
    {ncaaf, nhl}. The minting refusal still refuses (it only needs a covered
    league to exist); the relink arms, which need the league NAMED, now
    decline instead of searching ncaaf. Declared in the script's docstring;
    over 200 days of Polymarket markets no such matchup exists.
    """

    def test_minting_refusal_still_fires(self):
        assert _resolve(BEFORE_CLUBS, "Utah", "Colorado") == "americanfootball_ncaaf"
        assert _resolve(AFTER_CLUBS, "Utah", "Colorado") is not None

    def test_the_relink_declines_rather_than_guessing(self):
        assert (
            _resolve(BEFORE_CLUBS, "Utah", "Colorado", unambiguous_only=True)
            == "americanfootball_ncaaf"
        )
        assert _resolve(AFTER_CLUBS, "Utah", "Colorado", unambiguous_only=True) is None
