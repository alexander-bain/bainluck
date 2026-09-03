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
        self.commits = 0
        self._rowcount = rowcount

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rowcount)

    async def commit(self):
        self.commits += 1


@pytest.fixture
def wired(monkeypatch):
    """Stub the two edges — the database read and the authority — and nothing else."""

    def _wire(rows, records, rowcount=1, eligible=None):
        async def _load_rows(session, **kwargs):
            return list(rows)

        async def _count_eligible(session, **kwargs):
            # Defaults to "the limit reached everything", so a test that says
            # nothing about reach gets the complete-pass reading it means.
            # Pass `eligible=` to model a truncated window.
            return len(rows) if eligible is None else eligible

        async def _fetch_record(service, sport_keys, authority_id):
            return records.get(authority_id)

        async def _save_undo(identity, payload):
            # The D51 record's own guards live in
            # `test_anchor_schedule_undo_d51.py`; here it is stubbed to succeed
            # so these tests keep testing what they are about. Note the default
            # is SUCCESS: a stub that failed would make every apply below refuse
            # and each of these tests would pass for the wrong reason.
            return True, "ok"

        monkeypatch.setattr(rail, "_save_undo", _save_undo)
        monkeypatch.setattr(rail, "_load_rows", _load_rows)
        monkeypatch.setattr(rail, "_count_eligible", _count_eligible)
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

    def test_the_default_limit_fits_inside_the_router_timeout(self):
        """One ESPN call per row at ~0.2s, against Heroku's 30-second cutoff.

        The only caller is an admin endpoint, so a limit whose run cannot return
        is not a limit — and worse here than usual, because ``apply`` commits
        its writes before the router gives up, leaving an operator with an H12
        and no idea what landed.
        """
        assert rail.DEFAULT_LIMIT * 0.2 < 25


class TestReachIsReported:
    """A truncated pass and a complete one must not read the same. #2792.

    Measured 2026-09-03: the window held 685 anchored rows and the default limit
    was 200, so every unfiltered run saw under a third of the population and
    said nothing about it. The NFL slice alone was 239 against the same 200.
    """

    async def test_a_complete_pass_reports_its_reach(self, wired):
        session = wired([_row()], {"401873124": _record()})
        result = await rail.reconcile(session)

        assert result["eligible"] == 1
        assert result["truncated"] is False

    async def test_a_truncated_pass_says_so_and_cannot_report_complete(self, wired):
        session = wired([_row()], {"401873124": _record()}, eligible=685)
        result = await rail.reconcile(session, apply=True)

        assert result["truncated"] is True
        assert result["eligible"] == 685 and result["examined"] == 1
        assert result["terminal"] == "partial", (
            "a run that saw 1 of 685 rows has not completed, whatever it did "
            "with the one it saw"
        )
        # The write still happened — truncation is about reach, not correctness.
        assert result["moved"] == 1

    async def test_a_truncated_pass_that_found_nothing_is_not_an_all_clear(self, wired):
        """The worst of the three misreadings, and the reason for the ordering.

        A page of rows that all agree, out of a window ten times larger, would
        otherwise terminate ``no_work`` — the one word that sounds like the
        population is clean.
        """
        session = wired([_row()], {"401873124": _record(starts_at=OURS)}, eligible=685)
        result = await rail.reconcile(session)

        assert result["by_verdict"]["agrees"] == 1
        assert result["by_verdict"]["authority_moves_us"] == 0
        assert result["terminal"] == "partial"

    async def test_a_dark_authority_still_outranks_truncation(self, wired):
        """Both readings are true; the operator needs the more alarming one."""
        session = wired([_row()], {}, eligible=685)
        result = await rail.reconcile(session)

        assert result["terminal"] == "authority_dark"
        assert result["truncated"] is True

    async def test_the_operator_line_prints_reach_and_shouts_when_short(self):
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "partial",
                "examined": 200,
                "eligible": 685,
                "truncated": True,
                "moved": 0,
                "by_verdict": {"agrees": 200},
            }
        )
        assert "examined=200/685" in line
        assert "TRUNCATED" in line

    async def test_the_operator_line_is_quiet_on_a_complete_pass(self):
        line = rail.summarize_for_operator(
            {
                "measured": True,
                "terminal": "no_work",
                "examined": 34,
                "eligible": 34,
                "truncated": False,
                "moved": 0,
                "by_verdict": {"agrees": 34},
            }
        )
        assert "examined=34/34" in line
        assert "TRUNCATED" not in line
