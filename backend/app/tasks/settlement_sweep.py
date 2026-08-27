"""The nightly settlement-capture sweep — scheduling, and nothing else.

#2077 / queue 419. Everything this module's beat depends on already exists and is
certified: ``app/services/settlement_sweep_runner.run_sweep`` is the path
``C-CAPTURE-AUTH-BACKOFF-1`` returned GREEN on (CERT-405, `CODEX-CERT-LOG.md:105`,
closing with the words *capture RUN two-defect gate satisfied*) and
``C-CAPTURE-LIVELOCK-1`` returned GREEN on (`:97`). The RUN then fired in
production twice, 2026-08-25 and 2026-08-26, 3,000 rows each, ``rate_limited`` 0
both nights.

**Both of those fires happened because a person pasted a shell line.** The drain
is continuous — C-KALSHI-RETENTION-1 measured market-level purge starting at 47
days, with age ordering that is *not monotonic*, so there is no cliff date to
beat and no step function to point at. A missed week is not a deadline slipped,
it is rows gone. A backlog that drains only when somebody remembers is a backlog
that stops draining the first quiet evening.

So this module is a **wrapper, deliberately**. It opens a session, calls the
certified runner with the parameters the two live runs used, and returns the
runner's own report. It adds no planning, no query, no disposition logic and no
write of its own — ``tests/test_settlement_sweep_beat.py`` asserts that as a
gate (G5) rather than trusting this paragraph.

Three properties are load-bearing and each has a test:

**The identifier is derived, not generated.** ``run_sweep`` defaults it to
``kalshi-YYYY-MM-DD``. This wrapper therefore passes *nothing*, which is the
whole point: a retry, a redeploy or an operator re-run on the same night lands on
the same label, so already-captured markets are excluded by the candidate query
and a run killed at row 400 of 3,000 is recovered by running it again. Passing a
uuid or a task id here would look tidier and would silently convert every fire
into a fresh full-population probe.

**The deadline is inside the soft limit.** ``deadline_s`` bounds the whole probe
phase (#2174). Past it the probes stop retrying and answer retryable outcomes, so
the rows stay in the cohort and tomorrow's fire picks them up. Without it the
task would run until Celery's hard ``time_limit`` and be SIGKILLed — which runs no
exit path, banks nothing, and (gotcha: ``celery_sigkill_untracked``) is not even
recorded as a failure.

**The four zeros stay four.** ``_verdict`` in the runner already separates *total
loss* / *budget-capped* / *drained* / *nothing to do*, and ``settlement_sweep`` is
enrolled in ``app.utils.task_verdict.ENFORCED_TASKS`` in the same change that
gives it that vocabulary — enrolment without terminal truth is a no-op that still
reads GREEN, which is the trap ``task_verdict`` spends thirty lines on and
``polymarket_winners`` is the incident for. This wrapper passes the runner's
verdict through untouched.
"""

from __future__ import annotations

from typing import Any

from app.services.settlement_sweep_runner import (
    DEFAULT_BUDGET,
    DEFAULT_CONCURRENCY,
    run_sweep,
)
from app.tasks.base import get_task_session

#: Wall-clock bound on the probe phase, in seconds.
#:
#: Read against the task's ``soft_time_limit`` (900s), not on its own: the run
#: still has to build and return its report after the probes stop, so the two
#: numbers are held 120s apart by a test rather than by whoever edits one of
#: them next. Sized against production: both live fires covered 3,000 markets in
#: ~7 minutes at concurrency 4, so 780s is ~1.9x the observed wall and the
#: deadline binds only when something is genuinely wrong upstream.
SWEEP_DEADLINE_S = 780.0


async def _run_settlement_sweep(
    *,
    budget: int = DEFAULT_BUDGET,
    concurrency: int = DEFAULT_CONCURRENCY,
    deadline_s: float = SWEEP_DEADLINE_S,
) -> dict[str, Any]:
    """One sweep, on the certified path, resumable by construction."""
    async with get_task_session() as session:
        report = await run_sweep(
            session,
            budget=budget,
            concurrency=concurrency,
            deadline_s=deadline_s,
        )
    return report.to_dict()
