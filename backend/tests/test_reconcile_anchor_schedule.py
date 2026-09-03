"""The rail that dereferences anchors by id. #2693 / #2697, lane1/066.

The RULE is tested in `test_anchor_schedule.py`. This file tests the three
things the plumbing can get wrong on its own:

* **The terminal.** "It returned" is not "it worked" (gotcha #53). A run where
  ESPN answered for nothing must not read the same as a run where every row
  agreed — those are an outage and a clean bill of health, and the terminal is
  the only place that distinction survives.
* **The compare in the write.** The UPDATE re-states the two facts the decision
  was made from, so a row whose anchor or clock moved between the read and the
  write is skipped rather than overwritten. `rowcount` 0 is a finding.
* **`apply=False` writes nothing.** The default is a plan, and a rail whose dry
  run writes is not a dry run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import AnchoredRow
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc
OURS = datetime(2026, 9, 11, 0, 35, tzinfo=UTC)
THEIRS = datetime(2026, 12, 18, 1, 15, tzinfo=UTC)


def _row(event_id=14780595, **overrides) -> AnchoredRow:
    base = dict(
        event_id=event_id,
        sport_key="americanfootball_nfl",
        home_team_name="Los Angeles Chargers",
        away_team_name="San Francisco 49ers",
        espn_id="401873124",
        commence_time=OURS,
        status="scheduled",
        completed_at=None,
        commence_time_source="espn",
    )
    base.update(overrides)
    return AnchoredRow(**base)


def _record(starts_at=THEIRS) -> AuthorityRecord:
    return AuthorityRecord(
        authority_id="401873124",
        home_names=frozenset({"los angeles chargers"}),
        away_names=frozenset({"san francisco 49ers"}),
        starts_at=starts_at,
        label="Los Angeles Chargers v San Francisco 49ers",
    )


class _Result:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _Session:
    """Records the statements the rail executes instead of running them."""

    def __init__(self, rowcount=1):
        self.statements = []
        self._rowcount = rowcount

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rowcount)


@pytest.fixture
def wired(monkeypatch):
    """Stub the two edges — the database read and the authority — and nothing else."""

    def _wire(rows, records, rowcount=1):
        async def _load_rows(session, **kwargs):
            return list(rows)

        async def _fetch_record(service, sport_keys, authority_id):
            return records.get(authority_id)

        monkeypatch.setattr(rail, "_load_rows", _load_rows)
        monkeypatch.setattr(
            "app.tasks.repair_authority_id_collisions._fetch_record", _fetch_record
        )
        monkeypatch.setattr("app.services.espn_api.get_espn_service", lambda: object())
        return _Session(rowcount=rowcount)

    return _wire


class TestTheTerminal:
    async def test_a_plan_with_moves_is_plan_only_and_writes_nothing(self, wired):
        session = wired([_row()], {"401873124": _record()})
        result = await rail.reconcile(session, apply=False)

        assert result["terminal"] == "plan_only"
        assert result["by_verdict"]["authority_moves_us"] == 1
        assert result["moved"] == 0
        assert session.statements == [], "a dry run wrote to the database"

    async def test_applying_a_move_reports_complete(self, wired):
        session = wired([_row()], {"401873124": _record()})
        result = await rail.reconcile(session, apply=True)

        assert result["terminal"] == "complete"
        assert result["moved"] == 1 and result["stale"] == 0
        assert len(session.statements) == 1

    async def test_an_authority_that_answered_for_nothing_is_not_a_clean_run(
        self, wired
    ):
        """The load-bearing one. A dark ESPN must NOT read as 'all agree'.

        Every row returns no record — exactly what an outage looks like — and
        the census of verdicts is all `no_answer`. Reporting `no_work` here
        would tell an operator the population is healthy during an outage.
        """
        session = wired([_row(), _row(event_id=2)], {})
        result = await rail.reconcile(session, apply=False)

        assert result["terminal"] == "authority_dark"
        assert result["by_verdict"]["no_answer"] == 2

    async def test_a_population_that_agrees_is_no_work(self, wired):
        session = wired([_row()], {"401873124": _record(starts_at=OURS)})
        result = await rail.reconcile(session, apply=False)

        assert result["terminal"] == "no_work"
        assert result["by_verdict"]["agrees"] == 1

    async def test_an_empty_population_is_no_work_with_every_verdict_at_zero(
        self, wired
    ):
        session = wired([], {})
        result = await rail.reconcile(session, apply=False)

        assert result["terminal"] == "no_work"
        assert result["examined"] == 0
        assert set(result["by_verdict"].values()) == {0}

    async def test_a_stale_plan_is_partial_not_complete(self, wired):
        # rowcount 0: the row's anchor or clock moved between read and write.
        session = wired([_row()], {"401873124": _record()}, rowcount=0)
        result = await rail.reconcile(session, apply=True)

        assert result["terminal"] == "partial"
        assert result["moved"] == 0 and result["stale"] == 1


class TestTheWriteCompares:
    async def test_the_update_restates_the_facts_the_decision_was_made_from(
        self, wired
    ):
        """Without the compare, "the id moved" and "the row is gone" are the same zero."""
        session = wired([_row()], {"401873124": _record()})
        await rail.reconcile(session, apply=True)

        compiled = str(
            session.statements[0].compile(compile_kwargs={"literal_binds": True})
        )
        assert "events.id = 14780595" in compiled
        # The anchor and the clock are the two facts the verdict turned on.
        assert "401873124" in compiled
        assert "2026-09-11" in compiled

    async def test_only_the_two_columns_are_written(self, wired):
        session = wired([_row()], {"401873124": _record()})
        await rail.reconcile(session, apply=True)

        written = set(session.statements[0].compile().params) - {
            "id_1",
            "espn_id_1",
            "commence_time_1",
        }
        assert written == {"commence_time", "commence_time_source"}

    async def test_a_refused_row_is_never_written(self, wired):
        # Teams disagree -> identity, not clock. The rail must not touch it.
        session = wired(
            [_row(home_team_name="Somebody Else")], {"401873124": _record()}
        )
        result = await rail.reconcile(session, apply=True)

        assert result["by_verdict"]["teams_disagree"] == 1
        assert session.statements == []


class TestTheOperatorLine:
    def test_it_never_reads_an_unmeasured_run_as_a_result(self):
        line = rail.summarize_for_operator({"measured": False, "reason": "boom"})
        assert line.startswith("UNMEASURED")

    def test_it_carries_the_terminal_and_every_verdict(self):
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "plan_only",
                "examined": 3,
                "moved": 0,
                "by_verdict": {"authority_moves_us": 2, "agrees": 1},
            }
        )
        assert "plan_only" in line
        assert "authority_moves_us=2" in line
        # Absent verdicts print as zero rather than vanishing.
        assert "no_answer=0" in line


class TestTheWindow:
    def test_the_horizon_reaches_past_any_scoreboard_pass(self):
        """The whole defect hides at horizons a slate never reaches.

        The charter row's anchor was 98 days out. A horizon shorter than that
        would leave the rail unable to see the case it was built for.
        """
        assert rail.DEFAULT_HORIZON >= timedelta(days=98)
