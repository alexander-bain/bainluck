"""#1978 — the all-cells provenance census, run as a resumable worker.

Executes the rail designed and measured in
``.claude/handoff/ARTIFACT-CAL-P074-1978-WORKER-PRE-AGGREGATE-DESIGN.md``. All
the decisions live in :mod:`app.utils.cohort_cell_census`; this module supplies
rows, a clock, and a checkpoint, and nothing else.

THREE REASONS IT IS A WORKER, none of which a better query fixes:

1. **The router.** ``GET /api/admin/cohort-provenance-split`` is the correct
   full-population reader, is deployed, and returns HTTP 503 at 30.21 s. CAL-P075
   re-measured it AFTER the 40 h orphan backend was killed and the vacuum
   reclaimed ``events`` and ``futures_markets``: **30.21 s again, to the
   hundredth.** Bloat was never the cause. A 12-to-76-minute job cannot be an
   HTTP request.
2. **The 6x load-dependence.** 645 markets/s quiet, 101 markets/s against a live
   producer beat. Any fixed budget chosen against one of those is wrong against
   the other — ruling 089 exactly. So there is **no run-level budget here**: the
   run checkpoints per page and a cancellation costs one page.
3. **Contention with the deadline-critical producer**, which reads this same
   population every hour from :15 to roughly :35. CAL-P074 measured self-inflicted
   contention costing a cell its first pass (``tennis/quantity``'s roster
   ``statement_timeout``, which then recovered in 93 s on a quiet retry). A
   worker can be run in the quiet window; a human's curl cannot.

THE PAGE IS THREE LEGS, and the split is deliberate:

* **leg 0 — roster.** ``id > :cursor ORDER BY id LIMIT :n`` over
  ``futures_markets`` with NO category predicate. One monotonic walk of the id
  space. This is what deletes CAL-P074's density trap: a per-cell roster walks
  the primary key filtering as it goes, so a thinly-scattered cell pays
  ``1/density`` (``tennis/container_member``, 27,739 markets, **504 s**, against
  the LARGER ``table_tennis/quantity``, 35,999 markets, **56 s**). Here every
  page is dense by construction. It also carries ``league`` and ``market_type``,
  so no later leg needs to join ``futures_markets`` at all.
* **leg A — grade.** ``legs_total`` / ``legs_graded`` per market, over **ALL**
  of the market's outcomes, unfiltered. Deliberately not the eligibility-filtered
  subset: ``repair_pm_never_graded``'s cohort predicate is
  ``bool_and(fo.resolution_source IS NULL)`` over every leg, and
  ``market_result_shape`` in the calibration population takes the same view
  ("counts are over ALL outcomes of the market"). Classifying on a filtered
  subset would call a market fully-graded because its ungraded legs were priced
  out of the curve.
* **leg B — bins.** Per ``(market_id, bin)``, with the endpoint's price filters.
  Returns at most 10 rows per market.

The classification itself happens **in Python**, in
:func:`~app.utils.cohort_cell_census.classify_market_grade`, rather than as a
``CASE`` in leg A. That costs one extra column on the wire and buys the thing
that matters: ONE definition of complete/incomplete/never, reachable by a test
without a database. There is no local Postgres in this sandbox, so a decision
made in SQL is a decision no test here can reach.

``ORDER BY id`` IS NOT OPTIONAL. Paging without it read 1,317 of
``basketball/quantity``'s 13,121 markets, reported them as the cell, and produced
plausible ECEs 3 pp off with nothing erroring. The independent roster
``GROUP BY`` (1.9 s, no join) is what caught it, and
:func:`~app.utils.cohort_cell_census.reconcile_markets` is where that check
lives now.

A TIMING-OUT RANGE IS BISECTED, NEVER SKIPPED. A skipped range and an empty range
produce the same output (gotcha #53). Below the 25-id floor the range is recorded
as an ABSENCE with its bounds — a real finding about the database, not a reason
to drop rows quietly.
"""

from __future__ import annotations

import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any

from sqlalchemy import text

from app.utils.cohort_cell_census import (
    CENSUS_IDENTITY,
    CENSUS_SCHEMA,
    POPULATION_MARKET_TYPES,
    POPULATION_SOURCE,
    POPULATION_STATUS,
    bisect_range,
    build_report,
    cell_id,
    classify_market_grade,
    fold_page,
)

logger = logging.getLogger(__name__)

#: Default page size. CAL-P074 measured 300 -> 1000 buying 2.5x (255 -> 645
#: markets/s) because roster paging, not aggregation, dominates wall clock
#: (5,877 ms roster vs 980 ms aggregation on ``cricket/container_member``).
#: ``db-query``'s 1,000-row cap is what stopped that measurement going further;
#: a worker has no such cap, so this is a starting point that should be raised
#: on evidence — and the evidence is ``markets_per_s`` in the artifact.
DEFAULT_PAGE_SIZE = 1000

#: Per-statement budget for the aggregation legs. This is NOT a run budget. It
#: bounds ONE page so a contended page can be bisected instead of killing the
#: run — the ruling-089-safe form of a timeout: it is derived from the smallest
#: unit of work, and exceeding it triggers subdivision rather than cancellation.
_PAGE_TIMEOUT_MS = 20_000

#: The roster ``GROUP BY`` over ``futures_markets`` alone. Measured at 1.9 s;
#: 15 s is generous because this read is what makes every zero cell visible and
#: the reconciliation possible, so it is the last thing that should be starved.
_ROSTER_TIMEOUT_MS = 15_000

#: Wall-clock ceiling for ONE invocation, not for the census. On expiry the run
#: checkpoints and returns ``complete: false`` with a cursor; the next
#: invocation resumes. Chosen well under the Celery task time limit below.
_INVOCATION_SECONDS = 1500.0


def _population_where(alias: str = "fm") -> str:
    types = ", ".join(f"'{t}'" for t in POPULATION_MARKET_TYPES)
    return (
        f"{alias}.source = '{POPULATION_SOURCE}'\n"
        f"      AND {alias}.status = '{POPULATION_STATUS}'\n"
        f"      AND {alias}.market_type IN ({types})"
    )


_ROSTER_TOTALS_SQL = f"""
    SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS league,
           COALESCE(fm.market_type, 'unknown') AS market_type,
           COUNT(*) AS markets
    FROM futures_markets fm
    WHERE {_population_where()}
    GROUP BY 1, 2
"""

_ROSTER_PAGE_SQL = f"""
    SELECT fm.id AS market_id,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS league,
           COALESCE(fm.market_type, 'unknown') AS market_type
    FROM futures_markets fm
    WHERE {_population_where()}
      AND fm.id > :cursor
    ORDER BY fm.id
    LIMIT :page_size
"""

_GRADE_SQL = """
    SELECT fo.market_id AS market_id,
           COUNT(*) AS legs_total,
           COUNT(*) FILTER (WHERE fo.resolution_source IS NOT NULL) AS legs_graded
    FROM futures_outcomes fo
    WHERE fo.market_id = ANY(CAST(:ids AS bigint[]))
    GROUP BY fo.market_id
"""

_BINS_SQL = """
    SELECT fo.market_id AS market_id,
           LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
           COUNT(*) AS n,
           SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
           SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
    FROM futures_outcomes fo
    WHERE fo.market_id = ANY(CAST(:ids AS bigint[]))
      AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
      AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
      AND fo.opening_probability IS NOT NULL
      AND fo.is_winner IS NOT NULL
    GROUP BY 1, 2
"""


async def _bounded(session, sql: str, params: dict, timeout_ms: int):
    """Run one statement under its own budget, rolling back on failure.

    The rollback is not tidiness: after a ``statement_timeout`` the transaction
    is aborted and every subsequent statement on the session fails with
    ``InFailedSqlTransaction`` — which reads as "the next page also timed out"
    and would make one contended page look like a dead database.
    """
    await session.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
    return (await session.execute(text(sql), params)).all()


async def _fetch_with_bisect(
    session, sql: str, ids: list[int], failed: list[dict[str, Any]]
) -> list[Any]:
    """Aggregate over ``ids``, halving the id RANGE on timeout.

    Bisects on the id range rather than on the list index, because that is what
    the database's cost actually tracks — and because a range has bounds that can
    be reported when it turns out to be irreducible. CAL-P066 got all 27
    categories exact in 74 calls / 415 s this way where fixed sharding could not
    finish at all.
    """
    stack: list[list[int]] = [ids]
    out: list[Any] = []
    while stack:
        chunk = stack.pop()
        if not chunk:
            continue
        try:
            out.extend(await _bounded(session, sql, {"ids": chunk}, _PAGE_TIMEOUT_MS))
            continue
        except Exception as exc:  # noqa: BLE001 — a timeout is data, not a crash
            try:
                await session.rollback()
            except Exception:  # noqa: BLE001
                pass
            lo, hi = chunk[0], chunk[-1]
            halves = bisect_range(lo, hi)
            if halves is None or len(chunk) <= 1:
                # IRREDUCIBLE. Recorded with its bounds and its reason, and the
                # cells it could have contained are unknowable — which is exactly
                # why build_report taints the run rather than guessing at them.
                failed.append(
                    {
                        "lo": lo,
                        "hi": hi,
                        "ids": len(chunk),
                        "reason": f"{type(exc).__name__}: {str(exc)[:120]}",
                    }
                )
                logger.warning(
                    "cohort_cell_census: irreducible range [%s, %s] (%d ids): %s",
                    lo,
                    hi,
                    len(chunk),
                    exc,
                )
                continue
            (a_lo, a_hi), (b_lo, b_hi) = halves
            stack.append([i for i in chunk if b_lo <= i <= b_hi])
            stack.append([i for i in chunk if a_lo <= i <= a_hi])
    return out


async def _read_checkpoint() -> dict[str, Any] | None:
    from app.services.durable_snapshots import read_snapshot_standalone

    try:
        read = await read_snapshot_standalone(
            CENSUS_IDENTITY, expected_version=CENSUS_SCHEMA, max_age_s=30 * 86400
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cohort_cell_census: checkpoint unreadable: %s", exc)
        return None
    if not read.ok or read.envelope is None:
        return None
    return read.envelope.payload


async def _write_checkpoint(payload: dict[str, Any], *, complete: bool) -> bool:
    from app.services.durable_snapshots import publish_snapshot_standalone
    from app.utils.durable_state import DurableEnvelope

    try:
        result = await publish_snapshot_standalone(
            DurableEnvelope.build(
                identity=CENSUS_IDENTITY,
                schema_version=CENSUS_SCHEMA,
                payload=payload,
                complete=complete,
                source="worker:cohort-cell-census",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cohort_cell_census: checkpoint write raised: %s", exc)
        return False
    return result.get("status") in ("ok", "superseded")


async def run_cohort_cell_census(
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    resume: bool = True,
    max_seconds: float = _INVOCATION_SECONDS,
) -> dict[str, Any]:
    """Run (or resume) the all-cells census. Reads only; writes no market data.

    Returns the report from :func:`~app.utils.cohort_cell_census.build_report`,
    with ``complete: false`` and a ``resume_cursor`` when the invocation budget
    ran out. A partial census is a NORMAL outcome and says so — that is the whole
    reason ``measured`` is per cell rather than per run.
    """
    from app.tasks.base import get_task_session

    started = time.monotonic()
    state: dict[str, Any] = {}
    if resume:
        prior = await _read_checkpoint()
        if prior and not prior.get("complete"):
            state = prior
            logger.info(
                "cohort_cell_census: resuming at cursor=%s pages=%s",
                state.get("cursor"),
                state.get("pages_done"),
            )

    run_id = state.get("run_id") or uuid.uuid4().hex[:12]
    cursor = int(state.get("cursor") or 0)
    pages_done = int(state.get("pages_done") or 0)
    accumulator: dict[str, dict[str, float]] = {
        k: dict(v) for k, v in (state.get("bins") or {}).items()
    }
    paged_totals: dict[str, int] = dict(state.get("paged_totals") or {})
    failed_ranges: list[dict[str, Any]] = list(state.get("failed_ranges") or [])
    roster_totals: dict[str, int] = dict(state.get("roster_totals") or {})

    complete = False
    session_gen = get_task_session()
    session = await session_gen.__anext__()
    try:
        # The roster totals are re-read on a FRESH run only. On a resume they are
        # carried, because re-reading them mid-walk would compare a cursor that
        # has covered part of an OLD population against totals from a NEW one,
        # and every cell would report a spurious mismatch.
        if not roster_totals:
            rows = await _bounded(session, _ROSTER_TOTALS_SQL, {}, _ROSTER_TIMEOUT_MS)
            roster_totals = {
                cell_id(str(r.league), str(r.market_type)): int(r.markets) for r in rows
            }
            logger.info(
                "cohort_cell_census: roster enumerated — %d cells, %d markets",
                len(roster_totals),
                sum(roster_totals.values()),
            )

        while True:
            if time.monotonic() - started > max_seconds:
                logger.info(
                    "cohort_cell_census: invocation budget spent at cursor=%s", cursor
                )
                break

            page = await _bounded(
                session,
                _ROSTER_PAGE_SQL,
                {"cursor": cursor, "page_size": int(page_size)},
                _ROSTER_TIMEOUT_MS,
            )
            if not page:
                complete = True
                break

            ids = [int(r.market_id) for r in page]
            meta = {
                int(r.market_id): (str(r.league), str(r.market_type)) for r in page
            }

            grade_rows = await _fetch_with_bisect(session, _GRADE_SQL, ids, failed_ranges)
            grades = {
                int(r.market_id): classify_market_grade(
                    int(r.legs_total or 0), int(r.legs_graded or 0)
                )
                for r in grade_rows
            }

            bin_rows = await _fetch_with_bisect(session, _BINS_SQL, ids, failed_ranges)
            folded = []
            for r in bin_rows:
                mid = int(r.market_id)
                league, market_type = meta.get(mid, ("uncategorized", "unknown"))
                folded.append(
                    SimpleNamespace(
                        league=league,
                        market_type=market_type,
                        # A market with bin rows but no grade row cannot happen
                        # (leg A is unfiltered and leg B is a subset of it), so
                        # reaching the default means leg A lost a bisected range
                        # that leg B kept. ``never`` is the conservative read and
                        # the irreducible-range record is what explains it.
                        grade=grades.get(mid, "never"),
                        bin=int(r.bin),
                        n=r.n,
                        sum_prob=r.sum_prob,
                        winners=r.winners,
                    )
                )
            fold_page(accumulator, folded)

            for league, market_type in meta.values():
                key = cell_id(league, market_type)
                paged_totals[key] = paged_totals.get(key, 0) + 1

            cursor = ids[-1]
            pages_done += 1

            # Cursor and fold are written in ONE payload, so a resume has both
            # or neither. fold_page is not idempotent — banking the page without
            # its cursor would re-read and double-count it on resume.
            await _write_checkpoint(
                {
                    "run_id": run_id,
                    "cursor": cursor,
                    "pages_done": pages_done,
                    "bins": accumulator,
                    "paged_totals": paged_totals,
                    "roster_totals": roster_totals,
                    "failed_ranges": failed_ranges,
                    "complete": False,
                },
                complete=False,
            )
    finally:
        try:
            await session_gen.aclose()
        except Exception:  # noqa: BLE001
            pass

    report = build_report(
        accumulator=accumulator,
        roster_totals=roster_totals,
        paged_totals=paged_totals,
        failed_ranges=failed_ranges,
        complete=complete,
        elapsed_s=time.monotonic() - started,
        pages_done=pages_done,
    )
    report["run_id"] = run_id
    report["page_size"] = int(page_size)
    report["resume_cursor"] = None if complete else cursor
    elapsed = max(time.monotonic() - started, 1e-6)
    report["markets_per_s"] = round(sum(paged_totals.values()) / elapsed, 1)

    await _write_checkpoint({**report, "bins": accumulator, "paged_totals": paged_totals,
                             "roster_totals": roster_totals, "cursor": cursor,
                             "pages_done": pages_done, "run_id": run_id},
                            complete=complete)
    return report
