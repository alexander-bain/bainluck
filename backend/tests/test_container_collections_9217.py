"""The NFL-week / MLB-postseason dispatch on the shared assembly pass. #9217 (v3).

SHIP: NFL-week and MLB-playoff hubs contain the correct related games and
markets. The membership rules are calibration's adapters (#9649, #9650) and
are graded in their own files; this file grades authority's half:

* the hourly pass runs the declared collections, one run per current NFL week
  and one for the MLB postseason, each against its own flat container row;
* the pass's verdict is rolled up from every run's own ``terminal`` — a partial
  NFL week beside a complete tennis edition is PARTIAL, never complete;
* assembly never overwrites the matcher's receipt for a market it edges.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.statpal_api import StatPalAPIService, StatPalUpstreamError
from app.tasks import container_assembly as ca
from app.utils.container_mlb_playoffs import MlbPostseason
from app.utils.container_nfl import (
    UNAVAILABLE_SEASON_MISMATCH,
    UNAVAILABLE_SEASON_UNKNOWN,
    NflWeek,
)
from app.utils.container_tournaments import (
    DECLARED_COLLECTIONS,
    MLB_2026_POSTSEASON,
    NFL_2026,
    NflSeasonDeclaration,
)
from app.utils.match_receipts import PHASE_CONTAINER_ASSEMBLY, MatchReceipt

REAL_SCHEDULE = Path(__file__).parent / "fixtures" / "statpal_nfl_season_schedule_20260903.json"


@pytest.fixture(scope="module")
def real():
    """The banked StatPal 2026 NFL capture: Week 1 (16 games) + the Hall of Fame game."""
    return StatPalAPIService()._parse_nfl_season_schedule(json.loads(REAL_SCHEDULE.read_text()))


def _at(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


# --- the roll-up ---------------------------------------------------------------


@pytest.mark.parametrize(
    "terminals, expected",
    [
        (["complete", "complete"], ("complete", None)),
        # The ruling's named guard: a partial NFL week must not ride a complete
        # tennis edition to a green pass.
        (["complete", "partial"], ("partial", "some_edition_incomplete")),
        (["complete", "unavailable"], ("partial", "some_edition_incomplete")),
        (["complete", "refused"], ("partial", "some_edition_incomplete")),
        (["complete", "failed"], ("partial", "some_edition_incomplete")),
        (["failed", "failed"], ("failed", "every_edition_failed")),
        ([], ("partial", "some_edition_incomplete")),
    ],
)
def test_the_pass_verdict_rolls_up_every_runs_own_terminal(terminals, expected):
    assert ca.roll_up_terminal([{"terminal": t} for t in terminals]) == expected


def test_an_nfl_partial_with_members_beside_complete_tennis_is_partial():
    """Adapters carry no `members` key; a member-count roll-up called this green."""
    tennis = {"slug": "us-open-2026", "terminal": "complete", "members": 61}
    nfl = {
        "slug": "nfl-2026-week-4",
        "terminal": "partial",
        "reason": "contest_without_event_row",
        "assembly": {"edges_written": 40},
    }
    assert ca.roll_up_terminal([tennis, nfl])[0] == "partial"
    assert ca._run_edges(nfl) == 40
    assert ca._run_edges(tennis) == 0


# --- which NFL weeks are current -------------------------------------------------


def test_week_1_is_current_the_weekend_it_is_played(real):
    weeks, why = ca.nfl_weeks_in_window(real, 2026, _at(2026, 9, 11), _at(2026, 9, 20))
    assert why is None
    assert weeks == [NflWeek(season=2026, week=1)]


def test_a_window_holding_no_kickoff_names_no_week(real):
    weeks, why = ca.nfl_weeks_in_window(real, 2026, _at(2026, 10, 1), _at(2026, 10, 10))
    assert (weeks, why) == ([], None)


def test_the_hall_of_fame_game_is_no_week_because_it_has_no_week_number(real):
    """'Pre Season / Hall of Fame Weekend' parses to no identity; nothing is guessed."""
    hof = next(f for f in real if f.fixture_id == "280493")
    lo, hi = hof.start_time - timedelta(hours=1), hof.start_time + timedelta(hours=1)
    assert ca.nfl_weeks_in_window(real, 2026, lo, hi) == ([], None)


def test_a_schedule_of_another_season_answers_no_week_and_says_so(real):
    assert ca.nfl_weeks_in_window(real, 2027, _at(2026, 9, 1), _at(2026, 9, 30)) == (
        [],
        UNAVAILABLE_SEASON_MISMATCH,
    )


def test_an_unreadable_season_answers_no_week_and_says_so():
    assert ca.nfl_weeks_in_window([], 2026, _at(2026, 9, 1), _at(2026, 9, 30)) == (
        [],
        UNAVAILABLE_SEASON_UNKNOWN,
    )


def test_the_week_comes_from_the_label_not_the_date(real):
    """A Week-2 label on a Thursday inside the window adds Week 2, ordered after 1."""
    moved = [f for f in real]
    thursday = next(f for f in moved if f.fixture_id == "280445")
    from dataclasses import replace

    moved.append(replace(thursday, fixture_id="999001", round_info="Regular Season / Week 2",
                         start_time=_at(2026, 9, 17, 0)))
    weeks, _ = ca.nfl_weeks_in_window(moved, 2026, _at(2026, 9, 11), _at(2026, 9, 20))
    assert weeks == [NflWeek(season=2026, week=1), NflWeek(season=2026, week=2)]


# --- the declarations -------------------------------------------------------------


def test_the_declared_collections_are_the_nfl_season_and_the_mlb_postseason():
    assert DECLARED_COLLECTIONS == (NFL_2026, MLB_2026_POSTSEASON)
    assert MLB_2026_POSTSEASON.root_slug == MlbPostseason(2026).slug
    from app.tasks.container_mlb_playoffs_assembly import MAX_BOARD_DAYS, board_days

    days = board_days(MLB_2026_POSTSEASON.window_start.date(), MLB_2026_POSTSEASON.window_end.date())
    assert days[0] == "20260929" and 0 < len(days) <= MAX_BOARD_DAYS


def test_the_collection_kinds_are_existing_vocabulary():
    from app.utils.container_graph import validate_container_kind

    assert validate_container_kind(ca.NFL_WEEK_KIND) == "season"
    assert validate_container_kind(ca.MLB_POSTSEASON_KIND) == "tournament"


# --- the dispatch -------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class ContainerSession:
    """Holds a slug -> row map; INSERT … ON CONFLICT adds unless ``insert_lands`` is off."""

    def __init__(self, rows=None, insert_lands=True):
        self.rows = dict(rows or {})
        self.insert_lands = insert_lands
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, sql, params=None):
        sql = str(sql)
        self.statements.append((sql, params))
        if sql.startswith("SELECT id, slug, window_start, window_end FROM containers"):
            row = self.rows.get(params["slug"])
            return _Result([row] if row else [])
        if sql.startswith("INSERT INTO containers"):
            assert "ON CONFLICT (slug) DO NOTHING" in sql
            if self.insert_lands and params["slug"] not in self.rows:
                self.rows[params["slug"]] = (
                    100 + len(self.rows), params["slug"], params["window_start"], params["window_end"]
                )
            return _Result([])
        raise AssertionError(f"unexpected statement: {sql[:80]}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def inserts(self):
        return [p for s, p in self.statements if s.startswith("INSERT INTO containers")]


class Schedule:
    def __init__(self, fixtures=None, error=None):
        self.fixtures, self.error, self.calls = fixtures, error, 0

    async def get_schedule_fixtures(self, sport):
        self.calls += 1
        assert sport == "nfl"
        if self.error:
            raise self.error
        return self.fixtures


@pytest.fixture
def nfl_calls(monkeypatch):
    calls = []

    async def fake_run(session, container, fixtures, target, *, apply=False, limit=None):
        calls.append(SimpleNamespace(container=container, target=target, apply=apply,
                                     fixtures=fixtures))
        return {"slug": target.slug, "terminal": "complete", "reason": None,
                "assembly": {"edges_written": 3} if apply else None}

    import app.tasks.container_nfl_assembly as nfl

    monkeypatch.setattr(nfl, "run_nfl_week_assembly", fake_run)
    return calls


WEEK1_NOW = _at(2026, 9, 12)


@pytest.mark.asyncio
async def test_apply_bootstraps_one_flat_row_per_current_week_and_commits_each(real, nfl_calls):
    session, schedule = ContainerSession(), Schedule(real)

    runs = await ca.run_nfl_collection(session, NFL_2026, apply=True, now=WEEK1_NOW,
                                       service=schedule)

    assert schedule.calls == 1
    assert [r["slug"] for r in runs] == ["nfl-2026-week-1"]
    assert runs[0]["bootstrap"] == "created" and runs[0]["family"] == "nfl"
    (insert,) = session.inserts()
    assert insert["kind"] == "season" and insert["name"] == "NFL 2026 · Week 1"
    assert nfl_calls[0].container.slug == "nfl-2026-week-1"
    assert nfl_calls[0].container.id is not None and nfl_calls[0].apply is True
    assert session.commits == 1


@pytest.mark.asyncio
async def test_an_existing_row_is_used_and_never_rewritten(real, nfl_calls):
    session = ContainerSession(rows={"nfl-2026-week-1": (7, "nfl-2026-week-1", None, None)})

    runs = await ca.run_nfl_collection(session, NFL_2026, apply=True, now=WEEK1_NOW,
                                       service=Schedule(real))

    assert runs[0]["bootstrap"] == "existing"
    assert session.inserts() == []
    assert nfl_calls[0].container.id == 7


@pytest.mark.asyncio
async def test_a_dry_run_writes_no_row_and_still_runs_the_week(real, nfl_calls):
    session = ContainerSession()

    runs = await ca.run_nfl_collection(session, NFL_2026, apply=False, now=WEEK1_NOW,
                                       service=Schedule(real))

    assert runs[0]["bootstrap"] == "would_create"
    assert session.inserts() == [] and session.commits == 0
    assert nfl_calls[0].container.id is None and nfl_calls[0].apply is False


@pytest.mark.asyncio
async def test_a_row_that_does_not_land_is_unavailable_never_skipped(real, nfl_calls):
    session = ContainerSession(insert_lands=False)

    runs = await ca.run_nfl_collection(session, NFL_2026, apply=True, now=WEEK1_NOW,
                                       service=Schedule(real))

    assert runs == [{"slug": "nfl-2026-week-1", "family": "nfl",
                     "terminal": "unavailable", "reason": "container_row_absent"}]
    assert nfl_calls == []


@pytest.mark.asyncio
async def test_an_unreadable_schedule_is_one_unavailable_run(nfl_calls):
    runs = await ca.run_nfl_collection(
        ContainerSession(), NFL_2026, apply=True, now=WEEK1_NOW,
        service=Schedule(error=StatPalUpstreamError("503")),
    )
    assert [(r["slug"], r["terminal"], r["reason"]) for r in runs] == [
        ("nfl-2026", "unavailable", "schedule_unreadable")
    ]


@pytest.mark.asyncio
async def test_no_week_in_the_window_is_one_unavailable_run_not_silence(real, nfl_calls):
    runs = await ca.run_nfl_collection(ContainerSession(), NFL_2026, apply=True,
                                       now=_at(2026, 10, 20), service=Schedule(real))
    assert [(r["terminal"], r["reason"]) for r in runs] == [("unavailable", "no_week_in_window")]


@pytest.mark.asyncio
async def test_another_seasons_schedule_is_unavailable(real, nfl_calls):
    runs = await ca.run_nfl_collection(
        ContainerSession(), NflSeasonDeclaration(season=2027), apply=True, now=WEEK1_NOW,
        service=Schedule(real),
    )
    assert runs[0]["reason"] == UNAVAILABLE_SEASON_MISMATCH and nfl_calls == []


@pytest.mark.asyncio
async def test_one_week_raising_rolls_back_and_the_next_week_still_runs(real, monkeypatch):
    from dataclasses import replace

    import app.tasks.container_nfl_assembly as nfl

    seen = []

    async def flaky(session, container, fixtures, target, *, apply=False, limit=None):
        seen.append(target.week)
        if target.week == 1:
            raise RuntimeError("boom")
        return {"slug": target.slug, "terminal": "complete"}

    monkeypatch.setattr(nfl, "run_nfl_week_assembly", flaky)
    thursday = next(f for f in real if f.fixture_id == "280445")
    fixtures = list(real) + [replace(thursday, fixture_id="999001",
                                     round_info="Regular Season / Week 2",
                                     start_time=_at(2026, 9, 17, 0))]
    session = ContainerSession()

    runs = await ca.run_nfl_collection(session, NFL_2026, apply=True, now=WEEK1_NOW,
                                       service=Schedule(fixtures))

    assert seen == [1, 2]
    assert [(r["slug"], r["terminal"]) for r in runs] == [
        ("nfl-2026-week-1", "failed"), ("nfl-2026-week-2", "complete")
    ]
    assert session.rollbacks == 1 and session.commits == 1


@pytest.mark.asyncio
async def test_the_mlb_postseason_runs_its_declared_board_window(monkeypatch):
    import app.tasks.container_mlb_playoffs_assembly as mlb

    calls = []

    async def fake(session, container, target, start, end, *, apply=False, espn=None):
        calls.append((container, target, start, end, apply))
        return {"slug": target.slug, "terminal": "partial", "reason": "board_day_unread"}

    monkeypatch.setattr(mlb, "assemble_mlb_postseason", fake)
    session = ContainerSession()

    runs = await ca.run_mlb_collection(session, MLB_2026_POSTSEASON, apply=True)

    (container, target, start, end, apply) = calls[0]
    assert target == MlbPostseason(2026) and container.slug == "mlb-2026-postseason"
    assert (start.isoformat(), end.isoformat()) == ("2026-09-29", "2026-11-12")
    (insert,) = session.inserts()
    assert insert["kind"] == "tournament"
    assert insert["window_start"] == MLB_2026_POSTSEASON.window_start
    assert runs[0]["terminal"] == "partial" and runs[0]["family"] == "mlb"
    assert session.commits == 1


# --- the hourly entry: flag off is the old pass, byte for byte ---------------------


class _TaskSession:
    def __init__(self, inner):
        self.inner = inner

    async def __aenter__(self):
        return self.inner

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def hourly(monkeypatch):
    import app.tasks.base as base

    state = SimpleNamespace(tennis=[], collections=[])

    async def present(session):
        return True

    async def tennis(session, declaration, *, apply=True):
        state.tennis.append(declaration.root_slug)
        return {"slug": declaration.root_slug, "terminal": "complete", "members": 61,
                "edges_written": 61}

    async def collection(session, declaration, *, apply=True):
        state.collections.append(declaration.root_slug)
        return [{"slug": declaration.root_slug, "terminal": "partial",
                 "assembly": {"edges_written": 5}}]

    monkeypatch.setattr(base, "get_task_session", lambda: _TaskSession(ContainerSession()))
    monkeypatch.setattr(ca, "containers_tables_present", present)
    monkeypatch.setattr(ca, "run_declared_assembly", tennis)
    monkeypatch.setattr(ca, "run_declared_collection", collection)
    monkeypatch.delenv(ca.COLLECTIONS_ENABLED_ENV, raising=False)
    return state


@pytest.mark.asyncio
async def test_flag_off_runs_no_collection_and_keeps_the_old_verdict(hourly):
    out = await ca._run_assemble_containers(apply=True)
    assert hourly.collections == []
    assert out["collections"] == "disabled"
    assert (out["terminal"], out["members"], out["edges_written"]) == ("complete", 61, 61)


@pytest.mark.asyncio
async def test_flag_on_runs_every_collection_and_a_partial_week_makes_the_pass_partial(
    hourly, monkeypatch
):
    monkeypatch.setenv(ca.COLLECTIONS_ENABLED_ENV, "true")
    out = await ca._run_assemble_containers(apply=True)
    assert hourly.collections == ["nfl-2026", "mlb-2026-postseason"]
    assert out["collections"] == "enabled"
    assert out["terminal"] == "partial"
    assert out["edges_written"] == 61 + 5 + 5


@pytest.mark.asyncio
async def test_naming_one_collection_runs_only_it_with_the_flag_off(hourly):
    out = await ca._run_assemble_containers(apply=False, only="mlb-2026-postseason")
    assert hourly.tennis == [] and hourly.collections == ["mlb-2026-postseason"]
    assert out["collections"] == "requested"


@pytest.mark.asyncio
async def test_naming_the_tournament_runs_no_collection(hourly, monkeypatch):
    monkeypatch.setenv(ca.COLLECTIONS_ENABLED_ENV, "true")
    out = await ca._run_assemble_containers(apply=False, only="us-open-2026")
    assert hourly.tennis == ["us-open-2026"] and hourly.collections == []
    assert out["collections"] == "not_requested"


# --- the matcher's receipt is not overwritten ----------------------------------------


class ReceiptSession:
    def __init__(self, owned):
        self.owned = owned
        self.asked = []

    async def execute(self, sql, params=None):
        self.asked.append((str(sql), params))
        return _Result([(m,) for m in self.owned if m in params["ids"]])


def _receipt(market_id):
    return MatchReceipt(market_id=market_id, source="kalshi", external_id=None,
                        market_name="m", phase=PHASE_CONTAINER_ASSEMBLY,
                        attempted_at=_at(2026, 9, 29))


@pytest.mark.asyncio
async def test_a_market_whose_receipt_another_phase_owns_is_not_receipted():
    session = ReceiptSession(owned={11})
    kept, preserved = await ca._drop_matcher_owned_receipts(
        session, [_receipt(11), _receipt(12)]
    )
    assert [r.market_id for r in kept] == [12] and preserved == 1
    ((sql, params),) = session.asked
    assert "phase <> :phase" in sql and params["phase"] == PHASE_CONTAINER_ASSEMBLY
    assert params["ids"] == [11, 12]


@pytest.mark.asyncio
async def test_no_foreign_receipt_keeps_every_receipt():
    kept, preserved = await ca._drop_matcher_owned_receipts(
        ReceiptSession(owned=set()), [_receipt(11)]
    )
    assert [r.market_id for r in kept] == [11] and preserved == 0
