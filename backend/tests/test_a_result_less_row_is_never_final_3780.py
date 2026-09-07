"""A ROW NOTHING WATCHED IS NEVER FINAL — #3780.

═══ WHY THIS SUITE EXISTS ═══

`event_completion` has stated the rule since CERT-752: *wall-clock silence is
not on the ladder at all — it is the ABSENCE of every rung, and absence cannot
end a match.* `0ee26b71` applied it to the two staleness NETS on 2026-09-02.

It was applied to neither the third writer nor to the rows already written, and
both omissions were invisible for the same reason: nothing asserts the rule.
CERT-752's own suite proves the two nets it edited now write `suspended`; a
suite named after those nets cannot notice a fourth one, and no suite at all
looked at the table.

    the third writer   `backfill_winners._resolve_winners_only` Phase 0 flipped
                       every `scheduled` row two days past its kickoff to
                       `closed`, on a wall clock and nothing else, in order to
                       move it into another task's WHERE clause. Invisible in
                       production metrics because `resolve_winners` has been
                       retired from the beat since 2026-07-06 (#991).
    the rows           8,282 inside the league rail's own 14-day lookback,
                       measured on production 2026-09-06: `status='closed'`,
                       no score, no `statpal_end_time`, no `espn_id`, no box
                       score. On 25 league pages EVERY visible row of "Recent
                       Results" was one of them.

So this file asserts the RULE rather than either symptom:

    a row whose Final rests on nothing but a clock is not Final —
    in the table, and in every task that can write one

═══ WHAT IS DELIBERATELY NOT ASSERTED HERE ═══

That a rail may read the scoreline. It may not, and
`test_the_two_rails_are_jointly_exhaustive_3211
::test_no_rail_reads_the_scoreline_at_all` is the test that says so. The rails
in this file are executed, never edited: the repair moves the ROW's own
statement about itself, and `TestTheShip` spends the real rail conditions
unchanged to show the card lands where its own words already put it.
"""

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same shims, and
# the same reason, as `test_the_two_rails_are_jointly_exhaustive_3211`: without
# them `events` cannot be created and this module degrades to shape-only
# coverage, which for a claim about which ROWS move would be no coverage at all.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.event_completion import (  # noqa: E402
    EVENT_SUSPENDED,
    RECENT_RAIL_STATUSES,
    SETTLED_STATUSES,
    authority_may_settle,
)
from app.utils.event_rails import (  # noqa: E402
    settled_rail_condition,
    unreported_rail_condition,
    upcoming_rail_condition,
)
from scripts.repair_3780_stale_closed_without_a_result import (  # noqa: E402
    MAX_EXPECTED_POPULATION,
    MIN_EXPECTED_POPULATION,
    TARGET_STATUS,
    UNSETTLED_STATUS,
    _TARGET_IDS_SQL,
    _UNSETTLE_SQL,
    horizon_floor,
    population_refusal_reason,
    statement,
    unsettle_refusal_reason,
)
from scripts.restore_3780_stale_closed_without_a_result import restorable  # noqa: E402

NOW = datetime(2026, 9, 6, 13, 0, 0, tzinfo=timezone.utc)
LOOKBACK = timedelta(days=14)
FLOOR = horizon_floor(NOW, LOOKBACK.days)

S_BASEBALL = 1

#: Every word the ladder can write onto a row a reader-facing surface may meet.
#: Derived from the shipped vocabulary rather than re-listed, so a sixth state
#: arrives in this sweep without anybody remembering to add it.
ALL_STATUSES = sorted({"live", "scheduled", *RECENT_RAIL_STATUSES})

#: The scoreline axis. Half a score is not decoration: it is the shape a future
#: `or_`-where-it-meant-`and_` predicate gets wrong, and a row with one side
#: filled in has still had something reported ON it.
SCORE_CELLS = {
    "with a score": (3, 1),
    "with no score": (None, None),
    "with half a score": (3, None),
}

#: The LADDER axis — which rung, if any, spoke about this match. Every one of
#: these is a reason the row's Final might be somebody's rather than a clock's,
#: and each is a separate clause of `unsettle_refusal_reason`.
#: `espn_id` is per-row rather than a shared literal: the model declares a
#: PARTIAL UNIQUE index on it (`uq_events_espn_id`, #2693), so a constant would
#: make the corpus uninsertable — one authority id belongs to one game.
RUNG_CELLS = {
    "nothing spoke": lambda eid: {},
    "statpal watched it end": lambda eid: {
        "statpal_end_time": NOW - timedelta(days=2)
    },
    "an espn id is stamped": lambda eid: {"espn_id": f"4017{eid:05d}"},
    "a box score exists": lambda eid: {"box_score_data": {"players": {}}},
}

TIME_CELLS = {
    "yesterday": timedelta(days=-1),
    "just inside the lookback": -(LOOKBACK - timedelta(hours=1)),
    "beyond the lookback": -(LOOKBACK + timedelta(days=1)),
}

#: The specimen: NC Dinos v Kia Tigers, KBO, 2026-09-02, and 8,281 others. It
#: held slot 1 of `/api/leagues/baseball_kbo`'s "Recent Results" on 2026-09-06
#: under a heading claiming a result it does not have.
SPECIMEN_ID = 15300212
SPECIMEN_COMMENCE = datetime(2026, 9, 2, 9, 30, 49, tzinfo=timezone.utc)


def _event(eid, commence_time, status, score=(None, None), rung=None, **kw):
    home_score, away_score = score
    fields = {
        "id": eid,
        "sport_id": S_BASEBALL,
        "external_id": f"ext-{eid}",
        "home_team_name": "NC Dinos",
        "away_team_name": "Kia Tigers",
        "commence_time": commence_time,
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
    }
    fields.update(rung or {})
    fields.update(kw)
    return Event(**fields)


def _matrix_rows():
    """One row per (status, score, rung, time) cell, plus the named specimen.

    Ids encode the cell so a failure names the cell rather than a number.
    """
    rows, index, eid = [], {}, 1
    for status in ALL_STATUSES:
        for score_cell, score in SCORE_CELLS.items():
            for rung_cell, rung in RUNG_CELLS.items():
                for time_cell, offset in TIME_CELLS.items():
                    rows.append(
                        _event(eid, NOW + offset, status, score, rung(eid))
                    )
                    index[eid] = (status, score_cell, rung_cell, time_cell)
                    eid += 1
    rows.append(
        _event(
            SPECIMEN_ID,
            SPECIMEN_COMMENCE,
            TARGET_STATUS,
            completed_at=NOW - timedelta(days=3),
        )
    )
    index[SPECIMEN_ID] = (TARGET_STATUS, "with no score", "nothing spoke", "yesterday")
    return rows, index


@pytest.fixture
def corpus():
    """A real engine executing the real conditions and the real UPDATE.

    Function-scoped, not module-scoped: `TestTheShip` WRITES to it, and a
    mutated module fixture is how a later test starts passing for the wrong
    reason.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows, index = _matrix_rows()
    with Session(engine) as session:
        session.add(Sport(id=S_BASEBALL, key="baseball_kbo", name="KBO"))
        session.add_all(rows)
        session.commit()
        yield session, index


def _planned_ids(session):
    """Every id the PURE planner selects, evaluated over the real rows."""
    return {
        row.id
        for row in session.execute(select(Event)).scalars().all()
        if unsettle_refusal_reason(row, floor=FLOOR) is None
    }


def _sql_ids(session):
    """Every id the shipped SQL selects — the same statement the dyno runs."""
    return set(
        session.execute(
            statement(_TARGET_IDS_SQL), {"closed": TARGET_STATUS, "floor": FLOOR}
        )
        .scalars()
        .all()
    )


def _rails_holding(session, eid):
    """The names of every league rail that admits this row. The #3211 shape."""
    rails = {
        "upcoming": upcoming_rail_condition(NOW),
        "settled": settled_rail_condition(NOW, lookback=LOOKBACK),
        "unreported": unreported_rail_condition(NOW, lookback=LOOKBACK),
    }
    held = []
    for name, condition in rails.items():
        ids = set(session.execute(select(Event.id).where(condition)).scalars().all())
        if eid in ids:
            held.append(name)
    return sorted(held)


def _apply_the_repair(session):
    """Run the SHIPPED UPDATE over the SHIPPED plan. No re-implementation."""
    ids = sorted(_sql_ids(session))
    for eid in ids:
        session.execute(
            text(_UNSETTLE_SQL),
            {"suspended": UNSETTLED_STATUS, "closed": TARGET_STATUS, "eid": eid},
        )
    session.commit()
    return ids


class TestTheDefectReproduces:
    """🔴 RED-FIRST. Without this the greens below could be free."""

    def test_the_specimen_is_filed_as_a_result_today(self, corpus):
        """It is on the SETTLED rail — the one headed "Recent Results" — while
        reporting nothing. That is the defect, stated over the real condition."""
        session, _ = corpus
        assert _rails_holding(session, SPECIMEN_ID) == ["settled"]

    def test_the_specimen_carries_a_wall_clock_completed_at(self, corpus):
        """The pre-CERT-752 net wrote the false Final and a derived game-end
        time in ONE statement, so an undone Final that leaves the timestamp
        behind has undone half of it."""
        session, _ = corpus
        row = session.get(Event, SPECIMEN_ID)
        assert row.completed_at is not None

    def test_the_specimen_cannot_be_settled_by_anybody(self):
        """The half that is not cosmetic. While it says `closed`, an authority
        that finally reports how this match ended is refused."""
        assert not authority_may_settle(TARGET_STATUS)
        assert authority_may_settle(UNSETTLED_STATUS)


class TestThePlanAndTheSqlAgree:
    """One rule, two expressions. A repair whose plan and whose UPDATE are
    independent readings of "which rows" is how a sweep quietly moves a row
    nobody adjudicated."""

    def test_they_select_the_same_rows(self, corpus):
        session, index = corpus
        planned, selected = _planned_ids(session), _sql_ids(session)
        assert planned == selected, {
            "planner only": sorted(index.get(i, i) for i in planned - selected),
            "sql only": sorted(index.get(i, i) for i in selected - planned),
        }

    def test_they_select_something_at_all(self, corpus):
        """Two empty sets agree perfectly and prove nothing (gotcha #53)."""
        session, _ = corpus
        assert _sql_ids(session), "the corpus admits no target rows"

    def test_the_specimen_is_in_the_plan_by_name(self, corpus):
        session, _ = corpus
        assert SPECIMEN_ID in _planned_ids(session)


class TestTheRefusalsProtectARealResult:
    """Every clause is a rung of the ladder. Swept, so a clause cannot be
    deleted while this file stays green."""

    def _cells(self, index, **want):
        keys = ("status", "score_cell", "rung_cell", "time_cell")
        found = [
            eid
            for eid, cell in index.items()
            if all(cell[keys.index(k)] == v for k, v in want.items())
        ]
        assert found, f"the corpus holds no row matching {want}"
        return found

    @pytest.mark.parametrize("score_cell", ["with a score", "with half a score"])
    def test_a_closed_row_with_any_scoreline_keeps_its_final(self, corpus, score_cell):
        session, index = corpus
        for eid in self._cells(
            index, status=TARGET_STATUS, score_cell=score_cell, time_cell="yesterday"
        ):
            assert unsettle_refusal_reason(session.get(Event, eid), floor=FLOOR)

    @pytest.mark.parametrize(
        "rung_cell",
        ["statpal watched it end", "an espn id is stamped", "a box score exists"],
    )
    def test_a_rung_of_the_ladder_speaking_keeps_the_final(self, corpus, rung_cell):
        session, index = corpus
        for eid in self._cells(
            index,
            status=TARGET_STATUS,
            score_cell="with no score",
            rung_cell=rung_cell,
            time_cell="yesterday",
        ):
            assert unsettle_refusal_reason(session.get(Event, eid), floor=FLOOR)

    def test_completed_is_never_touched(self, corpus):
        """`completed` is the AUTHORITY's word and no staleness net has ever
        written it. Swept over every score, rung and time cell, so the scope
        cannot be widened to it by an edit that looks like a tidy-up."""
        session, index = corpus
        for eid, cell in index.items():
            if cell[0] != "completed":
                continue
            assert unsettle_refusal_reason(session.get(Event, eid), floor=FLOOR)

    def test_nothing_outside_the_horizon_moves(self, corpus):
        """A horizon, not a gap: it applies to a real Final exactly as it
        applies to one of these rows."""
        session, index = corpus
        for eid in self._cells(index, time_cell="beyond the lookback"):
            assert unsettle_refusal_reason(session.get(Event, eid), floor=FLOOR)

    def test_a_row_with_no_commence_time_is_left_alone(self):
        """A row we cannot place on the clock is one we have no standing to
        move — the same rule `started_without_result` applies to its own."""
        orphan = _event(990_001, None, TARGET_STATUS)
        assert unsettle_refusal_reason(orphan, floor=FLOOR)


class TestTheShip:
    """The rails, executed unchanged, before and after the shipped UPDATE."""

    def test_the_specimen_moves_to_the_no_result_rail(self, corpus):
        """gotcha #43's direction: not merely OFF "Recent Results" but ON the
        named other rail. A row only asserted absent can satisfy the assertion
        by vanishing, which is the defect `event_rails` exists to refuse."""
        session, _ = corpus
        assert _rails_holding(session, SPECIMEN_ID) == ["settled"]
        _apply_the_repair(session)
        assert _rails_holding(session, SPECIMEN_ID) == ["unreported"]

    def test_the_repaired_row_stops_carrying_a_game_end_time(self, corpus):
        """Production's 2,268 suspended rows all have `completed_at IS NULL`
        (measured 2026-09-06). The repair keeps that true; a suspended row
        holding a game-end time is CERT-752's contradiction in a new status."""
        session, _ = corpus
        _apply_the_repair(session)
        assert session.get(Event, SPECIMEN_ID).completed_at is None

    def test_every_repaired_row_still_lands_on_exactly_one_rail(self, corpus):
        """live/056's lesson, and the reason this is not "hide the bad rows":
        vanishing is a worse answer to "where did my match go" than the false
        Final. Asserted over every row the repair touched."""
        session, _ = corpus
        moved = _apply_the_repair(session)
        for eid in moved:
            assert _rails_holding(session, eid) == ["unreported"], (
                f"event {eid} left the settled rail and did not arrive on the "
                f"unreported one — it is now on {_rails_holding(session, eid)}"
            )

    def test_a_real_final_is_untouched_by_the_sweep(self, corpus):
        """The control arm. A `closed` row WITH a score keeps its slot, so the
        rail is narrowed rather than emptied."""
        session, index = corpus
        keeper = next(
            eid
            for eid, cell in index.items()
            if cell == (TARGET_STATUS, "with a score", "nothing spoke", "yesterday")
        )
        assert _rails_holding(session, keeper) == ["settled"]
        _apply_the_repair(session)
        assert _rails_holding(session, keeper) == ["settled"]

    def test_the_repaired_rows_are_settleable_again(self, corpus):
        session, _ = corpus
        _apply_the_repair(session)
        assert authority_may_settle(session.get(Event, SPECIMEN_ID).status)

    def test_the_sweep_is_idempotent(self, corpus):
        session, _ = corpus
        first = _apply_the_repair(session)
        assert first
        assert _apply_the_repair(session) == []


class TestNoTaskEndsAMatchOnAWallClock:
    """🔴 THE STRUCTURAL HALF. Repairing the rows without this leaves the
    writer that produced them, which is the mistake `event_rails`' own header
    names: "each repair widened one literal in one file and left the structure
    that produced it, so the next state fell through the same hole."

    An AST scan rather than a grep, for the reason CERT-1924 established on the
    sibling guard: the prose in this repo QUOTES the defect it fixed, so a
    text search over comments and docstrings reports the fix as the bug.
    """

    #: The one writer entitled to it: `detect_and_close_stale_events`' StatPal
    #: arm, where `statpal_end_time` is rung 1 of the ladder saying when the
    #: match ended. Named as (file, the reason it is allowed).
    ALLOWED = {
        "odds_polling.py": (
            "the StatPal arm of detect_and_close_stale_events — rung 1 watched "
            "the match and reported an end time, which is a positive statement, "
            "not a clock running out"
        )
    }

    @staticmethod
    def _closed_writes(tree):
        """Every place this module WRITES `closed` into a status, by line.

        Four shapes, because the codebase uses all four: a dict literal
        (`{"status": "closed"}`), a keyword (`.values(status="closed")`), an
        attribute assignment (`event.status = "closed"`), and raw SQL
        (`SET status = 'closed'`) inside a string constant.
        """
        found = []
        sql = re.compile(r"\bSET\s+status\s*=\s*'closed'", re.IGNORECASE)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "status"
                        and isinstance(value, ast.Constant)
                        and value.value == "closed"
                    ):
                        found.append((node.lineno, "dict literal"))
            elif isinstance(node, ast.keyword):
                if (
                    node.arg == "status"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value == "closed"
                ):
                    found.append((node.value.lineno, "keyword argument"))
            elif isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Constant) and node.value.value == "closed":
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and target.attr == "status"
                        ):
                            found.append((node.lineno, "attribute assignment"))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if sql.search(node.value):
                    found.append((node.lineno, "raw SQL"))
        return found

    def test_only_the_statpal_arm_may_write_closed(self):
        offenders = {}
        tasks = Path(__file__).resolve().parents[1] / "app" / "tasks"
        scanned = 0
        for path in sorted(tasks.glob("*.py")):
            scanned += 1
            writes = self._closed_writes(ast.parse(path.read_text()))
            if writes and path.name not in self.ALLOWED:
                offenders[path.name] = writes
        assert scanned > 20, (
            f"only {scanned} task modules scanned — the glob has stopped "
            "matching and this guard is asserting nothing"
        )
        assert offenders == {}, (
            "these task modules write the TERMINAL status `closed`, and the only "
            f"writer entitled to is {sorted(self.ALLOWED)}: {offenders}. Wall-clock "
            "silence is the absence of every rung of the ladder and cannot end a "
            "match (EVENT-GRAPH-DOCTRINE §R, CERT-752). Write EVENT_SUSPENDED."
        )

    def test_the_allowed_writer_still_writes_it(self):
        """Otherwise the allowlist is stale and the test above is vacuous — the
        BUILD-time-gate-goes-stale failure, applied to an allowlist."""
        tasks = Path(__file__).resolve().parents[1] / "app" / "tasks"
        for name in self.ALLOWED:
            writes = self._closed_writes(ast.parse((tasks / name).read_text()))
            assert writes, (
                f"{name} no longer writes `closed` at all, so its entry in "
                "ALLOWED is protecting nothing — remove it, or the next module "
                "that needs to write a Final inherits an unexamined licence"
            )

    def test_the_scanner_sees_all_four_shapes(self):
        """The scanner is the instrument, so its sensitivity is asserted rather
        than assumed. A guard that cannot see the write it forbids is the
        `_backfill_espn_ids`-style "correct but nobody called it" failure."""
        source = (
            'def f(e, s):\n'
            '    a = {"status": "closed"}\n'
            '    s.values(status="closed")\n'
            '    e.status = "closed"\n'
            '    q = "UPDATE events SET status = \'closed\' WHERE id = 1"\n'
            '    return a, q\n'
        )
        kinds = {kind for _, kind in self._closed_writes(ast.parse(source))}
        assert kinds == {
            "dict literal",
            "keyword argument",
            "attribute assignment",
            "raw SQL",
        }

    def test_the_scanner_ignores_prose_about_the_defect(self):
        """This repo's comments and docstrings quote the bug verbatim. A grep
        would flag `event_completion`'s own rule statement as a violation."""
        source = (
            '"""It used to write ``status=\'closed\'`` on a wall clock."""\n'
            '# 1. `status = "closed"`. Every client renders closed as Final.\n'
            'x = 1\n'
        )
        assert self._closed_writes(ast.parse(source)) == []


class TestTheGatesAreNotDecoration:
    """The population band and the ladder census gate `--apply`. Pure, so they
    are testable without a database — which is the point of them being pure."""

    def _measured(self, **overrides):
        base = {
            "population": (MIN_EXPECTED_POPULATION + MAX_EXPECTED_POPULATION) // 2,
            "with_score": 0,
            "with_statpal_end": 0,
            "with_espn_id": 0,
            "with_box_score": 0,
        }
        base.update(overrides)
        return base

    def test_a_healthy_census_is_allowed(self):
        assert population_refusal_reason(self._measured(), default_window=True) is None

    def test_an_empty_run_refuses_rather_than_reporting_success(self):
        """gotcha #53: an empty result is a response shape, not an absence."""
        assert population_refusal_reason(self._measured(population=0), default_window=True)

    def test_a_growing_cohort_refuses(self):
        """The cohort is supposed to be FROZEN. If it is not, there is a fourth
        writer of `closed` on a wall clock and the sweep would hide it."""
        assert population_refusal_reason(
            self._measured(population=MAX_EXPECTED_POPULATION + 1), default_window=True
        )

    @pytest.mark.parametrize(
        "field", ["with_score", "with_statpal_end", "with_espn_id", "with_box_score"]
    )
    def test_any_rung_speaking_in_the_window_refuses(self, field):
        assert population_refusal_reason(
            self._measured(**{field: 1}), default_window=True
        )

    def test_the_band_is_not_applied_to_a_widened_window(self):
        """It is a number about the 14-day question. Applying it to a 30-day
        sweep would be asserting something nobody measured."""
        assert (
            population_refusal_reason(
                self._measured(population=MAX_EXPECTED_POPULATION * 5),
                default_window=False,
            )
            is None
        )

    def test_a_rung_still_refuses_a_widened_window(self):
        """Widening the horizon relaxes the SIZE claim, never the ladder one."""
        assert population_refusal_reason(
            self._measured(with_score=1), default_window=False
        )


class TestTheUndo:
    """D51's other half. A repair whose restore is untested is a repair with no
    restore."""

    class _Row:
        def __init__(self, current_status):
            self.current_status = current_status

    def test_a_row_the_repair_left_is_restorable(self):
        assert restorable(self._Row(UNSETTLED_STATUS))

    @pytest.mark.parametrize("moved_on", sorted(SETTLED_STATUSES) + ["live", "voided"])
    def test_a_row_that_moved_on_is_skipped(self, moved_on):
        """Putting a banked `closed` back over a real `completed` would be the
        undo causing the damage it exists to reverse — and `suspended` being
        settleable is exactly why that is not hypothetical."""
        assert not restorable(self._Row(moved_on))


class TestTheVocabularyBindsStillHold:
    """The script asserts these at IMPORT so it cannot run against a moved
    vocabulary. They are re-asserted here so a failure names the reason rather
    than surfacing as a collection error."""

    def test_closed_still_means_final(self):
        assert TARGET_STATUS in SETTLED_STATUSES

    def test_suspended_still_asserts_nothing(self):
        assert UNSETTLED_STATUS == EVENT_SUSPENDED
        assert UNSETTLED_STATUS not in SETTLED_STATUSES

    def test_the_repaired_rows_are_still_reachable(self):
        """`suspended` rides a past rail. If it were dropped from
        `RECENT_RAIL_STATUSES` this repair would become a mass disappearance."""
        assert UNSETTLED_STATUS in RECENT_RAIL_STATUSES
