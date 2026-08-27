"""The nightly settlement-capture beat: it fires, it is enforced, and it resumes.

#2077 / queue 419. The sweep RUNNER is certified and unchanged (`CERT-405`,
`C-CAPTURE-AUTH-BACKOFF-1` GREEN on PR #2210; `C-CAPTURE-LIVELOCK-1` GREEN,
`CODEX-CERT-LOG.md:97` and `:105`). What did not exist was a *beat* — the run
fired twice, on 2026-08-25 and 2026-08-26, because a person pasted a
`heroku run:detached` line each time.

These gates are about the WRAPPER only. Every one of them is written so that the
obvious lazy wrapper fails it:

* **G1** the beat entry exists, at ~03:00 PT, with the certified parameters.
* **G2** the label is enrolled in ``ENFORCED_TASKS`` **and** the summary carries a
  real terminal. Either half alone is a no-op — ``task_verdict``'s own docstring
  spends thirty lines on that trap and ``polymarket_winners`` is the incident.
* **G3** the four zeros stay four. A wrapper that flattened them would report the
  total loss and the drained cohort with the same word.
* **G4** the sweep id is **date-derived**, never generated per run. A per-run id
  is what turns "re-running is the intended recovery" into "every run re-probes
  the whole population".
* **G5** the wrapper adds no sweep logic and writes no ``is_winner``.
* **G6** the in-task deadline is strictly inside the soft time limit, so a
  truncated run banks and resumes instead of being SIGKILLed (gotcha: a
  ``task_time_limit`` kill runs no exit path at all).
* **G7** it stays on ``background`` with the rest of the multi-minute backfill
  family, and is DECLARED there rather than left to the default.
"""

import inspect

import pytest

from app.tasks import celery_app


BEAT_KEY = "settlement-capture-sweep-nightly"
TASK_NAME = "app.tasks.run_settlement_sweep"
VERDICT_LABEL = "settlement_sweep"


def _entry():
    return celery_app.conf.beat_schedule[BEAT_KEY]


# ---------------------------------------------------------------------------
# G1 — the beat exists, at the ruled hour, with the certified parameters
# ---------------------------------------------------------------------------

class TestG1BeatEntry:
    def test_the_beat_entry_exists_and_names_the_task(self):
        assert BEAT_KEY in celery_app.conf.beat_schedule, (
            "the settlement sweep has no beat entry — it only runs when a person "
            "pastes a heroku line, which is the whole defect #2077 named"
        )
        assert _entry()["task"] == TASK_NAME

    def test_it_fires_once_a_night_at_about_0300_pacific(self):
        """10:00-10:59 UTC = 03:xx PDT. One fire a night, not an interval."""
        schedule = _entry()["schedule"]
        assert hasattr(schedule, "hour"), (
            f"expected a crontab, got {schedule!r} — an interval schedule would "
            "re-fire the sweep all day"
        )
        assert set(schedule.hour) == {10}, (
            f"expected hour=10 UTC (03:xx PDT / 02:xx PST), got {sorted(schedule.hour)}"
        )
        assert len(set(schedule.minute)) == 1, (
            f"expected a single minute, got {sorted(schedule.minute)}"
        )
        # Daily: the crontab must not narrow to particular days.
        assert len(set(schedule.day_of_week)) == 7
        assert len(set(schedule.day_of_month)) == 31

    def test_it_carries_the_certified_budget_and_concurrency(self):
        """3000 / 4 — the parameters the two live runs used, not new ones."""
        assert _entry()["kwargs"] == {"budget": 3000, "concurrency": 4}

    def test_the_beat_parameters_are_the_runner_defaults_not_a_second_opinion(self):
        """A literal in the beat that drifts from the runner's own constant is
        two sources of truth. They are pinned equal here so a change to either
        has to be a change to both, on purpose."""
        from app.services.settlement_sweep_runner import (
            DEFAULT_BUDGET,
            DEFAULT_CONCURRENCY,
        )

        assert _entry()["kwargs"]["budget"] == DEFAULT_BUDGET
        assert _entry()["kwargs"]["concurrency"] == DEFAULT_CONCURRENCY


# ---------------------------------------------------------------------------
# G2 — enrolled AND terminal-bearing. Either half alone is a no-op.
# ---------------------------------------------------------------------------

class TestG2EnforcedWithARealTerminal:
    def test_the_label_is_enrolled(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert VERDICT_LABEL in ENFORCED_TASKS

    def test_the_task_hands_that_exact_label_to_tracked_run(self):
        """Enrolment keys on the label passed to `_tracked_run`, not on the
        Celery task name. A label typo enrols nothing and still reads GREEN."""
        from app.tasks import run_settlement_sweep

        source = inspect.getsource(run_settlement_sweep)
        assert f'"{VERDICT_LABEL}"' in source, (
            f"the task does not pass {VERDICT_LABEL!r} to _tracked_run — "
            "enrolment would key on a label nothing emits"
        )

    @pytest.mark.parametrize(
        "terminal,expected_authoritative",
        [
            ("complete", True),
            ("partial", True),
            ("failed", True),
            ("no_work", True),
        ],
    )
    def test_every_terminal_the_runner_can_emit_is_authoritative(
        self, terminal, expected_authoritative
    ):
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(VERDICT_LABEL, {"terminal": terminal, "reason": "x"})
        assert verdict.authoritative is expected_authoritative, (
            f"terminal={terminal!r} classified non-authoritatively — enrolment "
            "without terminal truth is the no-op this gate exists to refuse"
        )

    def test_a_summary_with_no_terminal_is_the_kill_control(self):
        """The control that keeps the gate above from passing vacuously: if a
        terminal-less summary ALSO read authoritative, the four assertions above
        would prove nothing about the wrapper."""
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(VERDICT_LABEL, {"captured": 3000})
        assert not verdict.authoritative

    def test_the_summary_the_wrapper_returns_actually_carries_a_terminal(self):
        """Not "the classifier would like a terminal" — the wrapper's own return
        value has one. `SweepReport.to_dict` is the contract; assert against it."""
        from datetime import datetime, timezone

        from app.services.settlement_sweep_runner import SweepReport

        payload = SweepReport(
            sweep_id="kalshi-2026-08-26",
            source="kalshi",
            started_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            budget=3000,
            dry_run=False,
        ).to_dict()
        assert "terminal" in payload and "reason" in payload


# ---------------------------------------------------------------------------
# G3 — the four zeros stay four
# ---------------------------------------------------------------------------

class TestG3FourZeros:
    def test_the_four_terminals_are_four_distinct_verdicts(self):
        from app.utils.task_verdict import verdict_for

        verdicts = {
            t: verdict_for(VERDICT_LABEL, {"terminal": t, "reason": "x"}).verdict
            for t in ("complete", "partial", "failed", "no_work")
        }
        assert verdicts["complete"] != verdicts["failed"]
        assert verdicts["partial"] != verdicts["complete"]
        assert verdicts["no_work"] != verdicts["complete"], (
            "a run that found nothing to do must not read the same as a run that "
            "drained the cohort"
        )

    def test_a_total_loss_never_reads_green(self):
        from app.utils.task_verdict import COMPLETE, verdict_for

        verdict = verdict_for(
            VERDICT_LABEL, {"terminal": "failed", "reason": "total_loss"}
        )
        assert verdict.verdict != COMPLETE

    def test_a_budget_capped_run_never_reads_green(self):
        from app.utils.task_verdict import COMPLETE, verdict_for

        verdict = verdict_for(
            VERDICT_LABEL, {"terminal": "partial", "reason": "1200 left"}
        )
        assert verdict.verdict != COMPLETE

    def test_the_wrapper_does_not_rewrite_the_terminal(self):
        """The runner decides the terminal. A wrapper that post-processes it —
        even to be helpful — re-opens the flattening this gate forbids."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        for forbidden in ('"terminal"', "'terminal'", ".terminal ="):
            assert forbidden not in source, (
                f"the wrapper touches {forbidden} — the terminal is the runner's"
            )


# ---------------------------------------------------------------------------
# G4 — date-derived sweep id: re-running is the recovery
# ---------------------------------------------------------------------------

class TestG4Idempotency:
    def test_the_wrapper_passes_no_sweep_id(self):
        """`run_sweep` defaults to `default_sweep_id(now, source)` = the DATE.
        Passing anything at all — including a uuid, a task id, or a timestamp —
        makes each nightly run a fresh population and deletes resumability."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        assert "sweep_id" not in source, (
            "the wrapper names sweep_id — the only correct value is the one it "
            "does not pass"
        )

    def test_the_default_sweep_id_is_stable_within_a_day(self):
        from datetime import datetime, timezone

        from app.utils.settlement_sweep_query import default_sweep_id

        morning = datetime(2026, 8, 26, 3, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 8, 26, 23, 59, tzinfo=timezone.utc)
        next_day = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)

        assert default_sweep_id(morning, "kalshi") == default_sweep_id(evening, "kalshi")
        assert default_sweep_id(next_day, "kalshi") != default_sweep_id(morning, "kalshi")

    def test_a_second_fire_on_the_same_night_resumes_rather_than_re_probes(self):
        """The beat fires once a night, but a retry, a redeploy or an operator
        re-run must land on the same id. Proven through the wrapper's own call,
        not through the runner's docstring."""
        import asyncio
        from datetime import datetime, timezone

        from app.tasks import settlement_sweep

        seen = []

        async def fake_run_sweep(session, **kwargs):
            seen.append(kwargs)

            class _R:
                def to_dict(self):
                    return {"terminal": "no_work", "reason": "stub"}

            return _R()

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        asyncio.run(
            _drive(settlement_sweep, fake_run_sweep, _Session)
        )
        asyncio.run(
            _drive(settlement_sweep, fake_run_sweep, _Session)
        )

        assert len(seen) == 2
        for kwargs in seen:
            assert kwargs.get("sweep_id") is None, (
                f"the wrapper pinned a sweep_id: {kwargs.get('sweep_id')!r}"
            )
        # And the date-derived id both runs land on is the same one.
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        from app.utils.settlement_sweep_query import default_sweep_id

        assert default_sweep_id(now, "kalshi") == default_sweep_id(now, "kalshi")


async def _drive(module, fake_run_sweep, session_cls):
    """Call the wrapper with the runner and the session both stubbed."""
    import contextlib

    real_run = module.run_sweep
    real_session = module.get_task_session

    @contextlib.asynccontextmanager
    async def fake_session():
        yield session_cls()

    module.run_sweep = fake_run_sweep
    module.get_task_session = fake_session
    try:
        return await module._run_settlement_sweep(budget=3000, concurrency=4)
    finally:
        module.run_sweep = real_run
        module.get_task_session = real_session


# ---------------------------------------------------------------------------
# G5 — no new sweep logic, and is_winner is untouched
# ---------------------------------------------------------------------------

class TestG5NoNewLogic:
    def test_the_wrapper_calls_the_certified_runner(self):
        from app.tasks import settlement_sweep
        from app.services import settlement_sweep_runner

        assert settlement_sweep.run_sweep is settlement_sweep_runner.run_sweep

    def test_the_wrapper_writes_no_sql_and_no_is_winner(self):
        """The sweep never writes `is_winner` — it writes `settlement_captures`.
        A wrapper that reached for the winner column would turn a capture rail
        into a grader, which is a different authority (ruling: the resolution
        authority ladder)."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        for forbidden in ("is_winner", "UPDATE ", "INSERT ", "text("):
            assert forbidden not in source, (
                f"the wrapper contains {forbidden!r} — it must add no sweep logic"
            )

    def test_the_wrapper_is_small(self):
        """A size bound is a crude proxy and it is deliberate: 'no new sweep
        logic' is the acceptance, and the cheapest way to violate it is to grow
        the wrapper until nobody re-reads it."""
        from app.tasks import settlement_sweep

        body = inspect.getsource(settlement_sweep._run_settlement_sweep)
        code_lines = [
            ln for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        assert len(code_lines) < 30, f"wrapper grew to {len(code_lines)} lines"


# ---------------------------------------------------------------------------
# G6 — the deadline is inside the soft limit
# ---------------------------------------------------------------------------

class TestG6DeadlineInsideTheSoftLimit:
    def test_the_task_declares_both_limits(self):
        from app.tasks import run_settlement_sweep

        assert run_settlement_sweep.soft_time_limit, (
            "no soft_time_limit — the Celery default hard limit runs no exit "
            "path, so a long sweep is SIGKILLed with its progress unbanked"
        )
        assert run_settlement_sweep.time_limit > run_settlement_sweep.soft_time_limit

    def test_the_in_task_deadline_is_strictly_inside_the_soft_limit(self):
        """`run_sweep(deadline_s=...)` bounds the probe phase. If it were >= the
        soft limit the deadline would never bind and the sweep would die at the
        limit instead of returning a resumable `partial`."""
        from app.tasks import run_settlement_sweep
        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        assert SWEEP_DEADLINE_S < run_settlement_sweep.soft_time_limit
        margin = run_settlement_sweep.soft_time_limit - SWEEP_DEADLINE_S
        assert margin >= 60, (
            f"only {margin}s between the deadline and the soft limit — the "
            "report still has to be built and returned after the probes stop"
        )

    def test_the_deadline_reaches_the_wrapper(self):
        """A constant nothing passes is a comment. Assert it arrives."""
        import asyncio

        from app.tasks import settlement_sweep
        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        seen = []

        async def fake_run_sweep(session, **kwargs):
            seen.append(kwargs)

            class _R:
                def to_dict(self):
                    return {"terminal": "no_work", "reason": "stub"}

            return _R()

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        asyncio.run(_drive(settlement_sweep, fake_run_sweep, _Session))
        assert seen[0]["deadline_s"] == SWEEP_DEADLINE_S


# ---------------------------------------------------------------------------
# G7 — background, declared, not defaulted
# ---------------------------------------------------------------------------

class TestG7Routing:
    def test_the_beat_declares_the_background_queue(self):
        """Beat `options["queue"]` overrides `task_routes` at dispatch, so the
        two can disagree silently. Both arms are asserted."""
        assert _entry()["options"]["queue"] == "background"

    def test_it_is_declared_in_keep_on_background(self):
        from app.tasks import _HEAVY_KEEP_ON_BACKGROUND

        assert TASK_NAME in _HEAVY_KEEP_ON_BACKGROUND, (
            "a multi-minute network sweep that is not declared here can be "
            "moved onto `heavy` by the next person who reads the routing block "
            "and sees no objection"
        )

    def test_it_is_not_on_heavy(self):
        from app.tasks import HEAVY_TASKS, celery_app as app

        assert TASK_NAME not in HEAVY_TASKS
        assert app.conf.task_routes.get(TASK_NAME, {}).get("queue") != "heavy"
