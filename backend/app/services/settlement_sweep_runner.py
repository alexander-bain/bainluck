"""The sweep: select, plan, probe, record — and say honestly what it did.

Queue 392 Item 1 (#2077), built on queue 389's capture core. The three modules under
it are each pure in their own way and this one is the only place they meet a database
or a network:

    settlement_sweep_query   which rows, and which rows NOT twice   (SQL text)
    settlement_sweep_plan    what order, and what got left behind   (pure policy)
    settlement_probe         ask the source, keep the status        (HTTP)
    settlement_truth         what the answer MEANS                  (pure classifier)

WHAT THIS MODULE MUST NOT DO, STATED FIRST BECAUSE IT IS THE POINT
-------------------------------------------------------------------

**It never writes ``futures_outcomes.is_winner``.** Not on ``SETTLED``, not on a
unanimous two-channel agreement, not ever. The capture records what a source said
and when we asked; a separate, later, reviewable step decides what to do about it.
``assert_grading_licensed`` exists to refuse the shortcut, and this runner does not
call it because it does not go near grading — the absence is deliberate, not an
oversight, and a future edit that adds a grading write here should be read as
reverting the design rather than extending it.

THE VERDICT, AND WHY A ZERO IS NOT ALLOWED TO BE QUIET
-------------------------------------------------------

Gotcha #53 is the whole reason this program exists, and it applies to the sweep's own
report as forcefully as to Kalshi's empty 200s. These four runs all write zero rows:

* the cohort is empty — nothing to do, and that is success;
* every cohort row is already captured — nothing to do, and that is success;
* the budget was zero, or a dry run — nothing to do, and it proves nothing;
* every probe failed — a total loss, wearing the same zero.

A single ``captured: 0`` fuses all four, and a run that recovered nothing looks
exactly like a run with nothing to do — which is precisely how #683 sat open as a P0
for ten weeks while a task recorded SUCCESS every six hours. So the report carries a
``terminal`` that separates them, and the ``failed`` case is reachable: selection
found work, and none of it landed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settlement_probe import make_client, probe as default_probe
from app.utils.kalshi_retention import (
    CAPTURE_PLANNING_AGE_DAYS,
    days_until_purge,
)
from app.utils.settlement_sweep_plan import (
    Candidate,
    TERMINAL_BUCKET,
    TERMINAL_BUCKETS,
    bucket_for,
    burn_down,
    plan_sweep,
    tier_counts,
)
from app.utils.settlement_sweep_query import (
    ALREADY_CAPTURED_SQL,
    CANDIDATE_SQL,
    CAPTURED_BY_DAY_SQL,
    CAPTURED_BY_DISPOSITION_SQL,
    COHORT_BY_DAY_SQL,
    EXCLUSIONS_SQL,
    SWEEP_SOURCE,
    ExclusionCounts,
    candidate_params,
    cohort_params,
    default_sweep_id,
    exclusion_params,
    fetch_limit_for,
    rows_to_candidates,
)
from app.utils.settlement_truth import Disposition, ProbeOutcome

logger = logging.getLogger(__name__)

#: Version of the probe protocol that produced these dispositions. Bumped when the
#: classifier's *rules* change, so old rows are never silently re-read under a new
#: vocabulary — they answered a different question.
PROBE_PROTOCOL_VERSION = 1

#: Rows in the terminal bucket at C-CLIFF-CENSUS-1 (2026-08-21). These are the ones
#: that become permanently unrecoverable on 2026-08-28. Named so the budget below
#: can be checked against it by a test rather than by an operator's memory.
TERMINAL_BUCKET_CENSUS_2026_08_21 = 1_202

#: Default rows per invocation. Sized against the burn-down, not against comfort.
#:
#: **The reserve is why this is not simply 1,202.** ``plan_sweep`` caps the terminal
#: bucket at ``budget * (1 - NON_TERMINAL_RESERVE)`` so a large terminal bucket
#: cannot consume a whole week's capacity — a real protection, and one that quietly
#: converts "budget 2,000" into "terminal capacity 1,000" against a bucket of 1,202.
#: A sweep run at that budget would have looked successful and left 202 rows to
#: expire. The budget must therefore be read through the reserve, and the test
#: ``test_default_budget_clears_the_terminal_bucket_through_the_reserve`` is what
#: keeps the two numbers in a relationship instead of merely near each other.
DEFAULT_BUDGET = 3_000

#: Concurrent probes. Kalshi rate-limits, and a 429 is recorded as ``RATE_LIMITED``
#: rather than interpreted — but a sweep that spends its window collecting 429s has
#: burned the window, so this stays conservative.
DEFAULT_CONCURRENCY = 4

#: Rows written per commit. Per-batch rather than per-run so a killed sweep keeps
#: what it captured, and the re-run resumes past it (gotcha #41's family: a bounded
#: run over an EXPIRING population must bank progress as it goes).
COMMIT_EVERY = 50

# Terminal vocabulary consumed by app/utils/task_verdict.py.
TERMINAL_COMPLETE = "complete"
TERMINAL_PARTIAL = "partial"
TERMINAL_FAILED = "failed"
TERMINAL_NO_WORK = "no_work"


@dataclass
class SweepReport:
    """What the run did, in the shape the burn-down and the verdict both need."""

    sweep_id: str
    source: str
    started_at: datetime
    budget: int
    dry_run: bool

    #: The full at-risk population by bucket — the burn-down DENOMINATOR.
    cohort_by_bucket: dict[str, int] = field(default_factory=dict)
    #: Of that population, the rows no sweep has ever captured — what is still
    #: drainable, measured BEFORE this run wrote anything.
    uncaptured_by_bucket: dict[str, int] = field(default_factory=dict)
    #: Cohort rows absent from the work list, split by reason. Never summed.
    exclusions: ExclusionCounts = field(default_factory=ExclusionCounts)
    #: Rows the SQL returned before the planner cut them to budget.
    fetched: int = 0
    #: True when the candidate fetch cap bound. A cap that does not announce itself
    #: reads as "covered everything".
    fetch_capped: bool = False

    selected: int = 0
    selected_by_bucket: dict[str, int] = field(default_factory=dict)
    #: Selected rows by probe-history tier (#2175). This is the number that shows
    #: whether the sweep is spending its budget on rows that can answer or
    #: re-asking ones the source already declined. A pass whose selection is mostly
    #: ``stable_nonanswer`` is the livelock, visible before the results come back.
    selected_by_tier: dict[str, int] = field(default_factory=dict)
    #: Left behind by the BUDGET, per bucket. The number that says whether another
    #: run is needed before the next deadline.
    skipped_by_bucket: dict[str, int] = field(default_factory=dict)

    captured: int = 0
    by_disposition: dict[str, int] = field(default_factory=dict)
    #: Markets that raced us: selected, then found already captured at write time.
    write_collisions: int = 0
    #: Probes that raised past the probe layer's own isolation. Should be zero.
    errors: int = 0

    terminal: str = TERMINAL_NO_WORK
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sweep_id": self.sweep_id,
            "source": self.source,
            "started_at": self.started_at.isoformat(),
            "budget": self.budget,
            "dry_run": self.dry_run,
            "capture_planning_age_days": CAPTURE_PLANNING_AGE_DAYS,
            "cohort_by_bucket": self.cohort_by_bucket,
            "cohort_total": sum(self.cohort_by_bucket.values()),
            "uncaptured_by_bucket": self.uncaptured_by_bucket,
            "uncaptured_total": sum(self.uncaptured_by_bucket.values()),
            "terminal_bucket": TERMINAL_BUCKET,
            "terminal_buckets": sorted(TERMINAL_BUCKETS),
            # Summed over the whole urgency set for the reason given in
            # `verify_sweep`: reading only "0-7" turns rows that moved into
            # `overdue` into a false green.
            "terminal_bucket_uncaptured": sum(
                self.uncaptured_by_bucket.get(label, 0) for label in TERMINAL_BUCKETS
            ),
            "exclusions": {
                "already_this_sweep": self.exclusions.already_this_sweep,
                "terminal_prior": self.exclusions.terminal_prior,
            },
            "fetched": self.fetched,
            "fetch_capped": self.fetch_capped,
            "selected": self.selected,
            "selected_by_bucket": self.selected_by_bucket,
            "selected_by_tier": self.selected_by_tier,
            "skipped_by_bucket": self.skipped_by_bucket,
            "captured": self.captured,
            "by_disposition": self.by_disposition,
            "write_collisions": self.write_collisions,
            "errors": self.errors,
            "terminal": self.terminal,
            "reason": self.reason,
        }


ProbeFn = Callable[[str, str], Awaitable[ProbeOutcome]]


def _bucket_counts(
    day_rows: Sequence[Any], now: datetime, column: int = 1
) -> dict[str, int]:
    """Turn ``(day, count, ...)`` rows into bucket counts via the ONE bucket function.

    ``column`` selects which count to tally, so the cohort query's total and
    uncaptured columns are bucketed by the same code rather than by two copies of it.
    """
    counts: dict[str, int] = {}
    for row in day_rows:
        day = row[0]
        n = row[column]
        probe_candidate = Candidate(
            market_id=0,
            source=SWEEP_SOURCE,
            external_id="",
            resolution_date=day,
            candidate_reason="missing_winner",
        )
        label = bucket_for(probe_candidate.days_remaining(now))
        counts[label] = counts.get(label, 0) + int(n)
    return counts


def _capture_row(
    candidate: Candidate,
    outcome: ProbeOutcome,
    *,
    sweep_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Build the INSERT payload for one probe.

    ``winning_outcome`` is read from the claim and NOWHERE else. The dataclass
    already refuses to hold a claim without ``SETTLED`` and the table's CHECK
    constraint refuses the row, so this is the third guard on the same invariant —
    deliberately, because it is the one invariant whose violation manufactures
    ground truth.
    """
    settled = outcome.disposition is Disposition.SETTLED
    claim = outcome.claim if settled else None

    remaining = days_until_purge(candidate.resolution_date, now)

    return {
        "market_id": candidate.market_id,
        "source": candidate.source,
        "external_id": candidate.external_id,
        "disposition": outcome.disposition.value,
        "winning_outcome": claim.winning_outcome if claim else None,
        "answered_by": (
            claim.channel
            if claim
            else (outcome.channels[-1][0] if outcome.channels else None)
        ),
        "channels": [
            {"channel": name, "status": status} for name, status in outcome.channels
        ],
        "raw_response": outcome.raw or None,
        "reason": outcome.reason or None,
        "candidate_reason": candidate.candidate_reason,
        "days_remaining_at_capture": (
            None if remaining is None else int(round(remaining))
        ),
        "sweep_id": sweep_id,
        "protocol_version": PROBE_PROTOCOL_VERSION,
    }


_INSERT_SQL = text(
    """
    INSERT INTO settlement_captures (
        market_id, source, external_id, disposition, winning_outcome,
        answered_by, channels, raw_response, reason, candidate_reason,
        days_remaining_at_capture, sweep_id, protocol_version, captured_at
    ) VALUES (
        :market_id, :source, :external_id, :disposition, :winning_outcome,
        :answered_by, CAST(:channels AS jsonb), CAST(:raw_response AS jsonb),
        :reason, :candidate_reason,
        :days_remaining_at_capture, :sweep_id, :protocol_version, now()
    )
    """
)


async def run_sweep(
    session: AsyncSession,
    *,
    budget: int = DEFAULT_BUDGET,
    sweep_id: str | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
    source: str = SWEEP_SOURCE,
    concurrency: int = DEFAULT_CONCURRENCY,
    probe_fn: ProbeFn | None = None,
) -> SweepReport:
    """Run one sweep. Safe to re-run: same ``sweep_id`` resumes, never duplicates.

    ``probe_fn`` is injectable so the orchestration — planning, idempotency, the
    verdict — is testable without a network. The default issues real requests.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    sweep_id = sweep_id or default_sweep_id(now, source)

    report = SweepReport(
        sweep_id=sweep_id,
        source=source,
        started_at=now,
        budget=budget,
        dry_run=dry_run,
    )

    # --- 1. the denominator, before anything is excluded ---------------------
    cohort_rows = (
        await session.execute(text(COHORT_BY_DAY_SQL), cohort_params(now, source))
    ).all()
    report.cohort_by_bucket = _bucket_counts(cohort_rows, now, column=1)
    report.uncaptured_by_bucket = _bucket_counts(cohort_rows, now, column=2)

    exclusion_row = (
        await session.execute(
            text(EXCLUSIONS_SQL), exclusion_params(sweep_id=sweep_id, now=now, source=source)
        )
    ).first()
    if exclusion_row is not None:
        report.exclusions = ExclusionCounts(
            already_this_sweep=int(exclusion_row[0] or 0),
            terminal_prior=int(exclusion_row[1] or 0),
        )

    # --- 2. the work list ----------------------------------------------------
    rows = (
        await session.execute(
            text(CANDIDATE_SQL),
            candidate_params(sweep_id=sweep_id, budget=budget, now=now, source=source),
        )
    ).all()
    candidates = rows_to_candidates(rows)
    report.fetched = len(candidates)
    report.fetch_capped = len(candidates) >= fetch_limit_for(budget)

    selected, skipped = plan_sweep(candidates, budget, now)
    report.selected = len(selected)
    report.selected_by_bucket = burn_down(selected, now)
    report.selected_by_tier = tier_counts(selected)
    report.skipped_by_bucket = skipped

    if dry_run:
        report.terminal = TERMINAL_NO_WORK
        report.reason = (
            f"dry run: would probe {len(selected)} of {len(candidates)} candidates "
            f"against a cohort of {sum(report.cohort_by_bucket.values())}"
        )
        return report

    if not selected:
        report.terminal = TERMINAL_NO_WORK
        cohort_total = sum(report.cohort_by_bucket.values())
        if cohort_total == 0:
            report.reason = "cohort_empty: no at-risk markets in the capture window"
        elif report.exclusions.total() >= cohort_total:
            # The GOOD zero, said out loud so it cannot be read as the bad one.
            report.reason = (
                f"all_captured: every one of {cohort_total} cohort rows is already "
                f"captured ({report.exclusions.already_this_sweep} this sweep, "
                f"{report.exclusions.terminal_prior} terminal from an earlier sweep)"
            )
        elif budget <= 0:
            report.reason = f"zero_budget: {cohort_total} cohort rows left unprobed"
        else:
            report.reason = (
                f"no_candidates_selected from a cohort of {cohort_total} — "
                "investigate: exclusions do not account for the population"
            )
        return report

    # --- 3. probe and record -------------------------------------------------
    probe_client = None
    if probe_fn is None:
        probe_client = make_client()

        async def probe_fn(src: str, external_id: str) -> ProbeOutcome:  # noqa: F811
            return await default_probe(src, external_id, probe_client)

    # Chunked: probe a chunk concurrently, write it, commit, move on. The chunk is
    # the commit unit, so a killed run keeps every completed chunk and the re-run
    # resumes past it. Chunks stay in planned order, so an interrupted sweep has
    # drained the terminal bucket first rather than a random sample of it.
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _probe_one(candidate: Candidate) -> tuple[Candidate, ProbeOutcome | None]:
        async with semaphore:
            try:
                return candidate, await probe_fn(candidate.source, candidate.external_id)
            except Exception as exc:  # noqa: BLE001 - per-item isolation, gotcha #42
                logger.warning(
                    "settlement sweep probe raised for market %s: %s",
                    candidate.market_id,
                    exc,
                )
                return candidate, None

    try:
        for start in range(0, len(selected), COMMIT_EVERY):
            chunk = selected[start : start + COMMIT_EVERY]
            results = await asyncio.gather(*(_probe_one(c) for c in chunk))

            # Counted only after the chunk COMMITS. A report that increments on
            # execute() overstates by exactly the rows a later rollback discarded,
            # and "captured" is the number the burn-down is read from.
            staged: list[str] = []
            collisions = 0
            failed = False

            for candidate, outcome in results:
                if outcome is None:
                    report.errors += 1
                    continue

                try:
                    already = (
                        await session.execute(
                            text(ALREADY_CAPTURED_SQL),
                            {"market_id": candidate.market_id, "sweep_id": sweep_id},
                        )
                    ).first()
                    if already is not None:
                        collisions += 1
                        continue

                    await session.execute(
                        _INSERT_SQL,
                        _serialise(
                            _capture_row(candidate, outcome, sweep_id=sweep_id, now=now)
                        ),
                    )
                except Exception as exc:  # noqa: BLE001 - one bad row must not empty the run
                    logger.warning(
                        "settlement capture write failed for market %s: %s",
                        candidate.market_id,
                        exc,
                    )
                    # The rollback discards this chunk's uncommitted siblings too,
                    # so they are re-probed on the next run rather than lost — the
                    # sweep_id exclusion makes that safe and not a double-write.
                    await session.rollback()
                    report.errors += 1
                    failed = True
                    break

                staged.append(outcome.disposition.value)

            if failed:
                continue

            if staged:
                await session.commit()
                report.captured += len(staged)
                for key in staged:
                    report.by_disposition[key] = report.by_disposition.get(key, 0) + 1
            report.write_collisions += collisions
    finally:
        if probe_client is not None:
            await probe_client.aclose()

    report.terminal, report.reason = _verdict(report)
    return report


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-encode the JSONB columns.

    ``text()`` drops a bind parameter immediately followed by a ``::`` cast, so the
    INSERT uses ``CAST(:p AS jsonb)`` and the value must arrive as a string
    (``reference_asyncpg_jsonb_bind_gotcha``).
    """
    import json

    out = dict(row)
    for key in ("channels", "raw_response"):
        value = out.get(key)
        out[key] = None if value is None else json.dumps(value, default=str)
    return out


def _verdict(report: SweepReport) -> tuple[str, str]:
    """Separate the four zeros, and refuse to call a budget-capped run complete."""
    if report.captured == 0 and report.selected > 0:
        return (
            TERMINAL_FAILED,
            f"total_loss: selected {report.selected}, captured 0 "
            f"({report.errors} errors, {report.write_collisions} collisions)",
        )

    unfinished = sum(report.skipped_by_bucket.values())
    if unfinished or report.errors or report.fetch_capped:
        return (
            TERMINAL_PARTIAL,
            f"captured {report.captured}; {unfinished} left for the next run "
            f"({report.errors} errors"
            + (", fetch cap bound" if report.fetch_capped else "")
            + ")",
        )

    return (
        TERMINAL_COMPLETE,
        f"captured {report.captured}; the at-risk cohort is drained for this window",
    )


async def verify_sweep(
    session: AsyncSession,
    *,
    sweep_id: str,
    now: datetime | None = None,
    source: str = SWEEP_SOURCE,
) -> dict[str, Any]:
    """Captured rows against the at-risk cohort — the proof the deadline was met.

    Read-only, and deliberately re-derived from the database rather than reported
    out of the run's own memory: a runner that verifies itself from its own counters
    proves only that it can count, which is the self-oracular shape that blocked the
    delete rail four rounds running. This asks the table.

    ``remaining_by_bucket`` is the number that matters. The terminal bucket must read
    **0** by its deadline; anything else is rows that will not exist next week.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cohort_rows = (
        await session.execute(text(COHORT_BY_DAY_SQL), cohort_params(now, source))
    ).all()
    cohort_by_bucket = _bucket_counts(cohort_rows, now, column=1)
    uncaptured_by_bucket = _bucket_counts(cohort_rows, now, column=2)

    captured_rows = (
        await session.execute(text(CAPTURED_BY_DAY_SQL), {"sweep_id": sweep_id})
    ).all()
    captured_by_bucket = _bucket_counts(captured_rows, now)

    disposition_rows = (
        await session.execute(text(CAPTURED_BY_DISPOSITION_SQL), {"sweep_id": sweep_id})
    ).all()
    by_disposition = {str(d): int(n) for d, n in disposition_rows}

    # Summed over TERMINAL_BUCKETS, not the single "0-7" label. When the planning
    # horizon dropped to 45 on 2026-08-24, every row in the 59-66 day production
    # cohort became `overdue` — so a drain flag reading only "0-7" would have
    # reported `terminal_bucket_drained: True` over ~1,096 uncaptured rows. That is
    # a false green on the one number the capture wall is judged by, and it is the
    # gotcha #53 shape one level up: an empty bucket is not an absence of work.
    terminal_uncaptured = sum(
        uncaptured_by_bucket.get(label, 0) for label in TERMINAL_BUCKETS
    )
    return {
        "sweep_id": sweep_id,
        "source": source,
        "checked_at": now.isoformat(),
        "capture_planning_age_days": CAPTURE_PLANNING_AGE_DAYS,
        # --- what THIS sweep wrote ---
        "captured_by_bucket": captured_by_bucket,
        "captured_total": sum(by_disposition.values()),
        "by_disposition": by_disposition,
        # --- the at-risk cohort, all sweeps ---
        "cohort_by_bucket": cohort_by_bucket,
        "cohort_total": sum(cohort_by_bucket.values()),
        # The burn-down's real remaining: cohort rows no sweep has ever asked a
        # source about. NOT "rows still missing a winner" — capture is forbidden
        # from writing is_winner, so that number cannot move and a verification
        # built on it would call a perfect sweep a failure.
        "uncaptured_by_bucket": uncaptured_by_bucket,
        "uncaptured_total": sum(uncaptured_by_bucket.values()),
        "terminal_bucket": TERMINAL_BUCKET,
        "terminal_buckets": sorted(TERMINAL_BUCKETS),
        "terminal_bucket_uncaptured": terminal_uncaptured,
        # Per-label breakdown beside the total, so a drain can never be read as
        # progress when the work merely moved between urgency labels.
        "terminal_uncaptured_by_bucket": {
            label: uncaptured_by_bucket.get(label, 0)
            for label in sorted(TERMINAL_BUCKETS)
        },
        # The gate the capture deadline is actually about.
        "terminal_bucket_drained": terminal_uncaptured == 0,
    }
