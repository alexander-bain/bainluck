"""The graded-share census — the denominator that makes the selection-bias rule live.

CAL-P068 item 2. The rule shipped in CAL-P067 and rendered nothing, because it
had no denominator: *a ruling that renders nothing protects nobody.*

Why it needed a rail rather than a query. The denominator is a
``futures_outcomes x futures_markets`` aggregate, which is the planner-hostile
shape CAL-P066 documented — every such join drives from a Seq Scan on
``futures_outcomes``, so a category filter does not restrict it. Measured this
window, all against a 10 s statement timeout:

* the whole-population aggregate — ``statement_timeout``
* a SINGLE category (``table_tennis``) — ``statement_timeout``
* even ``SELECT count(*) FROM futures_markets WHERE status='resolved'`` — ``statement_timeout``

What DOES work, proven on #1145's hockey cohort this window, is driving from an
explicit ``market_id = ANY(ARRAY[...])``: that forces the index, and 9,841
markets scored in ~25 bounded calls. So this is a **cursor rail**, not a query —
it pages markets by id, accumulates per category, and persists its cursor so a
run that dies resumes instead of restarting.

Two properties it inherits from this lane's standing lessons:

* **A page that fails is never counted as zero** (gotcha #53, ruling 075 clause
  2). Failed pages are counted and named, and a census with any failed page
  publishes ``complete: false`` — the consumer then renders ``unknown``, which is
  not a pass.
* **The result declares its unit and population** so it can be divided into a
  published cell at all. CAL-P067 came one line from dividing a market-level
  Polymarket-only table into an outcome-level all-source cell and getting a
  confident ``provable`` off a 0.7096 "share"; :class:`GradedShareCensus`
  refuses that now, and this rail is what feeds it a coherent one.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy import text

from app.utils.calibration_provability import (
    CELL_POPULATION,
    UNIT_OUTCOMES,
    GradedShareCensus,
)

logger = logging.getLogger(__name__)

CENSUS_IDENTITY = "calibration:graded_share_census"
CENSUS_SCHEMA = "calibration-graded-share/v1"

#: Markets per page. Sized from the #1145 run: 400 ids scored comfortably inside
#: the statement timeout with the per-outcome work included. Smaller is safer
#: than faster here — a page that times out costs a retry AND becomes a hole.
PAGE_MARKETS = 400

#: Statement timeout for one page, well under the admin endpoint's own bound.
PAGE_TIMEOUT_MS = 20_000

#: THE canonical denominator predicate, defined once.
#:
#: A published calibration cell answers "of the outcomes that COULD have been
#: scored in this category, what fraction carry a grade?" — so the denominator is
#: every resolved outcome carrying a curve price, and the numerator is those with
#: a ``resolution_source``. An outcome with ``is_winner = false`` and a NULL
#: source is NOT graded: that False is the column default standing in for a
#: verdict nobody wrote (the fabricated-loss class, #1145 / #1912).
#:
#: Stated here rather than in the caller because there is already a second
#: graded-share implementation arriving on ``codex-adhoc/cohort-views``
#: (``cohort_sweep.GRADED_SHARE_THRESHOLD`` / ``_verdict_for``), keyed by
#: ``(source, league, market_type)`` and using a different total predicate. Two
#: definitions of one quantity is the contradiction machine this lane has now
#: found three times; when that branch merges it should adopt THIS predicate, and
#: the threshold + verdict from ``calibration_provability``.
GRADED_PREDICATE = "fo.resolution_source IS NOT NULL"
DENOMINATOR_PREDICATE = (
    "COALESCE(fo.calibration_probability, fo.opening_probability) IS NOT NULL"
)

_PAGE_SQL = f"""
SELECT COALESCE(fm.llm_sport_category, 'unknown') AS category,
       count(*) AS total_outcomes,
       count(*) FILTER (WHERE {GRADED_PREDICATE}) AS graded_outcomes
FROM futures_outcomes fo
JOIN futures_markets fm ON fm.id = fo.market_id
WHERE fo.market_id = ANY(:ids)
  AND fm.status = 'resolved'
  AND {DENOMINATOR_PREDICATE}
GROUP BY 1
"""

_MARKET_PAGE_SQL = """
SELECT id FROM futures_markets
WHERE status = 'resolved' AND id > :cursor
ORDER BY id
LIMIT :limit
"""


async def run_graded_share_census(
    session,
    *,
    max_pages: int = 40,
    start_cursor: int = 0,
    prior: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Page the resolved population and accumulate per-category graded share.

    Bounded by ``max_pages`` so an attended call cannot run away; the returned
    ``cursor`` resumes the next call exactly where this one stopped. ``prior``
    carries a previous partial run's totals so the rail composes across calls.

    Never raises on a page failure — a failed page is COUNTED and the census is
    marked incomplete, because a census that silently skipped a range and a
    census that covered everything must not produce the same artifact.
    """
    started = time.monotonic()
    totals: dict[str, dict[str, int]] = {}
    if prior and isinstance(prior.get("by_category"), dict):
        for cat, v in prior["by_category"].items():
            if isinstance(v, dict):
                totals[cat] = {
                    "total_outcomes": int(v.get("total_outcomes") or 0),
                    "graded_outcomes": int(v.get("graded_outcomes") or 0),
                }

    cursor = int(start_cursor)
    pages_ok = int((prior or {}).get("pages_ok") or 0)
    pages_failed = int((prior or {}).get("pages_failed") or 0)
    failed_ranges: list[list[int]] = list((prior or {}).get("failed_ranges") or [])
    exhausted = False

    for _ in range(max_pages):
        try:
            await session.execute(text(f"SET LOCAL statement_timeout = {PAGE_TIMEOUT_MS}"))
            rows = (
                await session.execute(
                    text(_MARKET_PAGE_SQL), {"cursor": cursor, "limit": PAGE_MARKETS}
                )
            ).all()
        except Exception as exc:  # noqa: BLE001
            await _rollback(session)
            pages_failed += 1
            failed_ranges.append([cursor, -1])
            logger.warning("graded-share census: market page from %s failed: %s", cursor, exc)
            break

        if not rows:
            exhausted = True
            break

        ids = [r[0] for r in rows]
        page_hi = ids[-1]
        try:
            await session.execute(text(f"SET LOCAL statement_timeout = {PAGE_TIMEOUT_MS}"))
            agg = (await session.execute(text(_PAGE_SQL), {"ids": ids})).all()
        except Exception as exc:  # noqa: BLE001
            await _rollback(session)
            pages_failed += 1
            # The RANGE is recorded, not just the count: a hole you cannot name
            # is a hole you cannot go back and fill.
            failed_ranges.append([cursor, page_hi])
            cursor = page_hi
            logger.warning(
                "graded-share census: outcome page %s-%s failed: %s", cursor, page_hi, exc
            )
            continue

        for category, total_outcomes, graded_outcomes in agg:
            slot = totals.setdefault(
                category, {"total_outcomes": 0, "graded_outcomes": 0}
            )
            slot["total_outcomes"] += int(total_outcomes)
            slot["graded_outcomes"] += int(graded_outcomes)

        pages_ok += 1
        cursor = page_hi
        if len(rows) < PAGE_MARKETS:
            exhausted = True
            break

    complete = exhausted and pages_failed == 0
    return {
        "schema": CENSUS_SCHEMA,
        "unit": UNIT_OUTCOMES,
        "population": CELL_POPULATION,
        "by_category": totals,
        "cursor": cursor,
        "exhausted": exhausted,
        "complete": complete,
        "pages_ok": pages_ok,
        "pages_failed": pages_failed,
        "failed_ranges": failed_ranges,
        "elapsed_s": round(time.monotonic() - started, 2),
        # The consumer must be able to tell "this covered everything" from "this
        # stopped early", without inferring it from a count.
        "usable_as_denominator": complete,
        "reason": (
            None
            if complete
            else (
                "census incomplete — "
                + ("pages still pending; " if not exhausted else "")
                + (f"{pages_failed} page(s) failed; " if pages_failed else "")
                + "a partial denominator understates graded share, so cells "
                "render unknown rather than not-provable"
            )
        ),
    }


async def _rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001
        pass


def census_from_payload(payload: Any) -> Optional[GradedShareCensus]:
    """Turn a persisted census into a divisible :class:`GradedShareCensus`, or None.

    Returns ``None`` — never a partial census — when the run did not cover the
    whole population. A denominator missing an unknown slice of its own
    population is smaller than the truth, which inflates every graded share
    computed from it and would flip cells from NOT-PROVABLE to provable. That is
    the one direction this rule must never fail in.
    """
    if not isinstance(payload, dict):
        return None
    if not payload.get("usable_as_denominator"):
        return None
    by_category = payload.get("by_category")
    if not isinstance(by_category, dict) or not by_category:
        return None
    by_key: dict[str, int] = {}
    for category, v in by_category.items():
        if not isinstance(v, dict):
            continue
        total = v.get("total_outcomes")
        if isinstance(total, int) and total > 0:
            by_key[category] = total
    if not by_key:
        return None
    return GradedShareCensus(
        by_key=by_key,
        unit=str(payload.get("unit") or UNIT_OUTCOMES),
        population=str(payload.get("population") or CELL_POPULATION),
    )
