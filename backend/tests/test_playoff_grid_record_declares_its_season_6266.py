"""#6266 — a championship grid may not print a record for a season with no games.

THE SPECIMEN, production 2026-09-22 07:4xZ. `/api/playoffs/nba` heads itself
**NBA Playoffs 2026-27** and prints a completed 82-game record beside all thirty
clubs:

    Oklahoma City Thunder   64-18
    San Antonio Spurs       62-20
    Philadelphia 76ers      45-37

`/api/playoffs/nhl` heads itself 2026-27 and is wrong in two ways at once, which
is why that grid reads MIXED rather than uniformly stale: St. Louis carries last
season's finished `36-33-12`, eight clubs carry a record built from this week's
EXHIBITIONS (Colorado `1-0-0`, Washington `0-0-1`), and twenty-three have rolled
over to `0-0-0`. This is the surface #6266 was filed from; the team-page half
shipped at `b1c932bab`.

THE ARM THAT DECIDES THE SHIP IS THE ORDERING ONE. `team_row["record"]` has two
writers — `_team_meta` when the row is built, and the ESPN standings overlay
(#7675), which REPLACES it for every club ESPN names. A gate at the first writer
is inert wherever the second one speaks, and the second one is precisely who
supplies the NHL exhibition records. `test_withhold_runs_after_the_espn_overlay`
reads the AST of `get_playoff_grid` and fails if the withhold ever moves above
`apply_record_overlay`. It is an AST walk rather than a source scan because this
module's own prose names both functions, and a substring guard would count its
own comments (and be satisfied by them alone).

THE CONTRACT IS TWO-SIDED. A withhold-only guard passes just as well against a
serializer that blanks everything, so every refusal below is paired with a case
that must still be SERVED: the same league in season, the same league mid-break,
an in-season league on the same instant as the refusal, and an unmodelled league.

Clocks are injected explicitly and never branch on the real date (gotcha #44):
every anchor is a fixed `datetime` read back off `season_windows._LEAGUE_BANDS`,
so a band edit fails with the league named instead of silently turning a refusal
case into an admission case.
"""

import ast
import inspect
from datetime import datetime, timezone

import pytest

from app.routes.playoffs import _withhold_records_out_of_season
from app.utils import season_windows
from app.utils.espn_clinch import apply_record_overlay

# Anchors, all UTC, all fixed. Named for what the calendar says.
SEP_22 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)   # NBA+NHL offseason, MLB+NFL in season
DEC_01 = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)   # NBA and NHL regular season
FEB_17 = datetime(2027, 2, 17, 12, 0, tzinfo=timezone.utc)   # NBA All-Star break
MAY_01 = datetime(2027, 5, 1, 12, 0, tzinfo=timezone.utc)    # NBA postseason
JUN_15 = datetime(2027, 6, 15, 12, 0, tzinfo=timezone.utc)   # NFL offseason


def _rows(*records):
    """Grid rows in the shape `get_playoff_grid` builds them."""
    return [
        {"name": f"Club {i}", "record": r, "conference": "Eastern", "cells": {}}
        for i, r in enumerate(records)
    ]


# ── The anchors describe the calendar the code reads, not a date I remembered ──


@pytest.mark.parametrize(
    "league,anchor,phase",
    [
        ("nba", SEP_22, "offseason"),
        ("nhl", SEP_22, "offseason"),
        ("mlb", SEP_22, "in_season"),
        ("nfl", SEP_22, "in_season"),
        ("nba", DEC_01, "in_season"),
        ("nba", FEB_17, "break"),
        ("nba", MAY_01, "postseason"),
        ("nfl", JUN_15, "offseason"),
    ],
)
def test_anchor_means_what_its_name_says(league, anchor, phase):
    """A band edit fails HERE, naming the league, instead of quietly flipping a
    refusal case below into an admission case."""
    assert season_windows.league_phase(league, anchor) == phase


# ── Refusals ─────────────────────────────────────────────────────────────────


def test_nba_grid_blanks_a_completed_prior_season():
    """The specimen: 2026-27 heading, 2025-26 records."""
    rows = _rows("64-18", "62-20", "45-37")
    assert _withhold_records_out_of_season(rows, "nba", SEP_22) == 3
    assert [r["record"] for r in rows] == [None, None, None]


def test_nhl_grid_blanks_an_exhibition_record():
    """Colorado's `1-0-0` is this week's preseason, not the 2026-27 season."""
    rows = _rows("1-0-0", "0-0-1", "36-33-12")
    assert _withhold_records_out_of_season(rows, "nhl", SEP_22) == 3
    assert all(r["record"] is None for r in rows)


def test_a_rolled_over_zero_record_is_withheld_too():
    """The twenty-three NHL clubs reading `0-0-0`.

    Not an overreach — the club's own team page prints nothing for it since
    `b1c932bab`, and a grid answering `0-0-0` where the page answers nothing is
    a fresh disagreement about one club. This arm is what convicts a fix that
    only blanks records it judges "stale-looking".
    """
    rows = _rows("0-0-0", "0-0", "0-0-1")
    assert _withhold_records_out_of_season(rows, "nhl", SEP_22) == 3
    assert all(r["record"] is None for r in rows)


def test_the_nfl_grid_is_withheld_in_ITS_own_offseason():
    """The rule is per-league and travels — June blanks the NFL, which September
    does not. Without this arm, hard-coding `league in ("nba", "nhl")` passes."""
    rows = _rows("2-0", "1-1")
    assert _withhold_records_out_of_season(rows, "nfl", JUN_15) == 2
    assert all(r["record"] is None for r in rows)


# ── Admissions — the half that can rot ───────────────────────────────────────


@pytest.mark.parametrize("league", ["mlb", "nfl"])
def test_an_in_season_league_keeps_its_record_on_the_refusal_instant(league):
    """MLB and the NFL are in season on the very instant that blanks the NBA, so
    this is a per-league calendar rule and not a date cutoff."""
    rows = _rows("96-60", "89-66")
    assert _withhold_records_out_of_season(rows, league, SEP_22) == 0
    assert [r["record"] for r in rows] == ["96-60", "89-66"]


def test_a_mid_season_break_is_not_an_offseason():
    """February games HAVE been played. This arm is the one that convicts
    swapping `is_offseason` for `is_quiet` (offseason OR break)."""
    rows = _rows("31-20")
    assert _withhold_records_out_of_season(rows, "nba", FEB_17) == 0
    assert rows[0]["record"] == "31-20"


def test_the_postseason_keeps_its_record():
    rows = _rows("64-18")
    assert _withhold_records_out_of_season(rows, "nba", MAY_01) == 0
    assert rows[0]["record"] == "64-18"


@pytest.mark.parametrize("league", ["epl", "ncaa-basketball", "wnba", "golf", ""])
def test_an_unmodelled_league_falls_through_untouched(league):
    """Ten of the fourteen grids have no band. They keep every record they have
    — including the college grids, which have this defect and are named as NOT
    REACHED in the change rather than swept in by widening the bands."""
    rows = _rows("14-11-12", "12-16-7")
    assert _withhold_records_out_of_season(rows, league, SEP_22) == 0
    assert [r["record"] for r in rows] == ["14-11-12", "12-16-7"]


# ── Degradation, counting, and shape ─────────────────────────────────────────


def test_a_raising_calendar_costs_the_grid_nothing(monkeypatch):
    """A display withhold may never cost a reader the grid."""
    def _boom(*_a, **_k):
        raise RuntimeError("bands unreadable")

    monkeypatch.setattr(season_windows, "is_offseason", _boom)
    rows = _rows("64-18", "62-20")
    assert _withhold_records_out_of_season(rows, "nba", SEP_22) == 0
    assert [r["record"] for r in rows] == ["64-18", "62-20"]


def test_the_count_is_rows_changed_not_rows_seen():
    """A row already carrying no record is not counted, so the log line cannot
    report work it did not do."""
    rows = _rows("64-18", None, "45-37")
    assert _withhold_records_out_of_season(rows, "nba", SEP_22) == 1 + 1
    assert [r["record"] for r in rows] == [None, None, None]


def test_a_row_with_no_record_key_survives():
    rows = [{"name": "Club", "cells": {}}]
    assert _withhold_records_out_of_season(rows, "nba", SEP_22) == 0
    assert rows == [{"name": "Club", "cells": {}}]


def test_an_empty_grid_is_not_an_error():
    assert _withhold_records_out_of_season([], "nba", SEP_22) == 0


# ── The ordering arm: the withhold must outlast the ESPN overlay ─────────────


def test_a_record_the_espn_overlay_writes_is_still_withheld():
    """The behavioural half. `apply_record_overlay` writes ESPN's record over
    ours unconditionally; running after it means its output is withheld too.

    Reversing the two calls here fails this test, which is the same mistake as
    gating `_team_meta` instead.
    """
    rows = _rows(None, None)
    pairs = [("401584793", rows[0]), ("401584794", rows[1])]
    assert apply_record_overlay(pairs, {"401584793": "1-0-0", "401584794": "0-0-1"}) == 2
    assert [r["record"] for r in rows] == ["1-0-0", "0-0-1"]

    assert _withhold_records_out_of_season(rows, "nhl", SEP_22) == 2
    assert [r["record"] for r in rows] == [None, None]


def test_withhold_runs_after_the_espn_overlay():
    """The structural half, and the arm that decides the ship.

    An `ast` walk, not a substring scan: this module's own docstring names both
    functions, and `routes/playoffs.py` names them in its comments, so a source
    scan would be satisfied by prose alone (the trap a `"now" in call_text`
    assertion falls into).
    """
    from app.routes import playoffs as playoffs_module

    tree = ast.parse(inspect.getsource(playoffs_module))
    grid_fn = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "get_playoff_grid"
    )

    def _call_lines(name):
        return [
            n.lineno
            for n in ast.walk(grid_fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == name
        ]

    overlay = _call_lines("apply_record_overlay")
    withhold = _call_lines("_withhold_records_out_of_season")

    assert len(overlay) == 1, f"expected one overlay call, found {overlay}"
    assert len(withhold) == 1, f"expected one withhold call, found {withhold}"
    assert withhold[0] > overlay[0], (
        "#6266: the record withhold must run AFTER the ESPN standings overlay — "
        f"withhold at line {withhold[0]}, overlay at line {overlay[0]}. Above it "
        "the gate is inert for every club ESPN names, which is exactly the "
        "population carrying the NHL exhibition records."
    )


# ── A sweep, so the rule cannot be right only on the days I picked ───────────


@pytest.mark.parametrize("month", list(range(1, 13)))
@pytest.mark.parametrize("league", ["nba", "nhl", "mlb", "nfl"])
def test_the_withhold_tracks_the_calendar_all_year(league, month):
    """Twelve clocks per modelled league. The withhold fires when and only when
    `season_windows` calls the league offseason — so the two can never drift,
    and a band edit changes this test's expectation with it."""
    anchor = datetime(2027, month, 15, 12, 0, tzinfo=timezone.utc)
    expected_offseason = season_windows.league_phase(league, anchor) == "offseason"

    rows = _rows("10-5")
    changed = _withhold_records_out_of_season(rows, league, anchor)

    assert bool(changed) is expected_offseason
    assert (rows[0]["record"] is None) is expected_offseason
