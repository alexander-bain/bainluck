"""The Kalshi resolution-window sweep — the repair, in the app, on a beat.

CAL-P998 / D47. Moved verbatim out of
``backend/scripts/backfill_kalshi_resolution_window.py``; that script is now the
attended CLI over this module and restates nothing. The move is what makes the
last open line of #2771 buildable:

    > **The sweep is scheduled, not attended.** The population refills daily; a
    > one-off cannot hold it. That half is NOT in this branch.

A Celery task cannot import from ``scripts/`` — it is not on the dyno's path —
so as long as the repair lived there the only way to run it was for a human to
run it, and the measurement says nobody did: 5,143 sealed rows on 2026-09-03
05:00Z, **5,137** at 22:0xZ the same day. The population is not draining, and
every one of those rows renders a dead last-trade price as a live probability
the moment the venue finalizes it (gotcha #33, #2660's card).

WHAT THE SWEEP IS FOR, in one sentence: settled-at-the-venue is a fact
regardless of what date we are holding, and the row we hold must converge onto
the venue's ``close_time`` rather than sit forever on its legal backstop.

Everything about the predicate, the ordering, the retention floor and the
zero-yield discipline is documented at its definition below and was ratified by
CERT-766 / CAL-P992 — none of it is re-argued here, because none of it changed
in this move. What is NEW in this module is only :func:`run_sweep`: the bound,
unattended entry point the beat calls, and the terminal truth it returns.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import text

# `KalshiAPIService` — NOT `KalshiAPIClient`, which has never existed in
# `app.services.kalshi_api`. CERT-766 caught the wrong name as an ImportError
# raised before argparse ran, so the script could not select a row, let alone
# write one, and the catch-up this whole ship depends on was a no-op.
from app.services.kalshi_api import KalshiAPIService
from app.utils.kalshi_resolution_window import derive_resolution_window
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

#: What ONE unattended beat run may touch.
#:
#: 500 is the limit every attended run of this repair has used (CAL-P989's
#: catch-up, CAL-P992's re-runs), so the beat inherits a batch size whose venue
#: cost and wall time are already observed rather than picking a fresh one on
#: the day it becomes unattended. At 500/day against the 6,302 rows eligible on
#: 2026-09-03 the population is reached in ~13 runs — and because the ordering
#: is `updated_at ASC` and every write refreshes that stamp, the sweep rotates
#: rather than re-reading the same head (the starvation CAL-P992 measured).
SWEEP_BATCH_LIMIT = 500

#: Concurrent venue reads. Matches the attended default; Kalshi's rate limit has
#: never been the binding constraint at this width and a beat is not the place
#: to find out where it is.
SWEEP_CONCURRENCY = 6

@dataclass
class _Leg:
    close_time: Optional[datetime]
    expiration_time: Optional[datetime]


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


#: A row is a candidate while the date we hold for it is still PROVISIONAL, i.e.
#: while the venue has not yet told us when trading actually stopped.
#:
#: `expiration_time IS NULL` alone — the original marker — is "have I ever touched
#: this row", and CAL-P992 measured what that costs. Kalshi sets `close_time` equal
#: to the backstop while a market is ACTIVE and rewrites it to the settlement
#: instant on finalize. So a row swept while its market was still trading is written
#: with `resolution_date == expiration_time`, which stamps the backstop column and
#: makes the row permanently unselectable — and then the market finalizes and the
#: open-market poll can never re-enumerate it (gotcha #33). The row keeps a future
#: date forever and no run of this script can reach it. Measured on production
#: 2026-09-02: 5,143 `status='open'` rows already sealed this way, five of them
#: (US Open `KXWTASETWINNER` / `KXATPEXACTMATCH` legs) finalized at the venue within
#: an hour of the sweep that sealed them.
#:
#: `resolution_date >= expiration_time` is the provisional test and it is a
#: PROVENANCE read, not a proxy: it is true exactly while `resolution_date` is still
#: a backstop. Once the venue rewrites `close_time`, `resolution_date` moves strictly
#: earlier, the row converges out, and it stays out — the same convergence the old
#: marker gave, keyed on the fact that makes the row done rather than on the fact
#: that we looked at it.
#:
#: `LIKE 'KX%'` rather than `~ '^KX'`: identical semantics for a left-anchored
#: literal prefix, sargable, and executable by the guard in
#: `tests/test_kalshi_resolution_backfill_script_989.py`, which runs this exact
#: string against a seeded table. A regex operator would have made the starvation
#: guard un-runnable, and an un-runnable guard is how the post-LIMIT floor shipped
#: in the first place. (It also excludes 211 legacy non-`KX` rows — all measured as
#: genuinely-future 2027-2032 political/macro markets, so not a dead-card source
#: today; named in #2773 rather than widened here.)
#:
#: ORDERING — `updated_at ASC`, NOT `market_tier ASC`. Tier-first is what the
#: original backlog wanted, but on the provisional population it starves: measured
#: 2026-09-02, tier 1+2 hold 2,951 provisional rows and tier 5 holds 2,038, so a
#: `--limit 500` run ordered by tier never reaches tier 5 at all — and tier 5 is
#: where the settled prop legs live. `updated_at ASC` is not a tie-break dressed up:
#: on a `status='open'` Kalshi row the 2h poller bumps `updated_at` only while the
#: venue still enumerates the market as open, so the moment Kalshi finalizes it the
#: stamp FREEZES (gotcha #33 read forwards). Least-recently-enumerated first is
#: therefore a direct observation of "most likely already settled", and it rotates,
#: so no row can be starved behind a prefix. `commence_time` cannot do this job:
#: 4,954 of the 5,143 sealed rows carry `commence_time = expiration_time`, the same
#: poisoned backstop, so a "has it commenced" gate would have missed all five of the
#: rows that motivated this change.
SELECT_SQL = """
    SELECT id, external_id, resolution_date, commence_time, market_tier
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
      AND (commence_time IS NULL OR commence_time >= :purge_floor)
    ORDER BY updated_at ASC NULLS FIRST,
             market_tier ASC NULLS LAST,
             commence_time DESC NULLS LAST
    LIMIT :limit OFFSET :offset
"""

#: What the batch does NOT cover. Reported every run so a bounded sweep can never
#: read as a complete one. `never_swept` / `provisional_recheck` split the eligible
#: population by which of the two selection reasons put the row there, because they
#: behave differently: the never-swept tail can only shrink (the poller writes
#: `expiration_time` on every upsert), while the provisional set refills every time
#: a market is swept before it settles.
COUNT_SQL = """
    SELECT
        count(*) AS eligible_total,
        count(*) FILTER (
            WHERE commence_time IS NOT NULL AND commence_time < :purge_floor
        ) AS excluded_purged,
        count(*) FILTER (WHERE expiration_time IS NULL) AS never_swept,
        count(*) FILTER (
            WHERE expiration_time IS NOT NULL
              AND (resolution_date IS NULL OR resolution_date >= expiration_time)
        ) AS provisional_recheck
    FROM futures_markets
    WHERE source = 'kalshi'
      AND status = 'open'
      AND external_id LIKE 'KX%'
      AND (expiration_time IS NULL
           OR resolution_date IS NULL
           OR resolution_date >= expiration_time)
"""

#: `updated_at` is BOUND, not `now()`: the two date columns and the stamp then come
#: from one instant the caller controls, so the guard can assert on the exact
#: parameters that reach the driver instead of on a value the database invents.
UPDATE_SQL = """
    UPDATE futures_markets
    SET resolution_date = :resolution_date,
        expiration_time = :expiration_time,
        updated_at = :updated_at
    WHERE id = :id
"""


async def run_backfill(
    *,
    session_maker: Callable,
    client_factory: Callable[[], object],
    limit: int = 200,
    offset: int = 0,
    apply: bool = False,
    concurrency: int = 6,
    now: Optional[datetime] = None,
) -> dict:
    """Select, derive and (optionally) write. Every dependency is a parameter.

    `session_maker` and `client_factory` are injected rather than imported at the
    call site so the composed guard can drive this whole path — selection,
    derivation, and the two-column UPDATE — against a seeded table and a faked
    venue. `now` is a parameter for the same reason the derivation takes no clock
    (gotcha #44): the retention floor must not move under a test.
    """
    now = now or datetime.now(timezone.utc)
    purge_floor = now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)

    async with session_maker() as session:
        rows = (
            await session.execute(
                text(SELECT_SQL),
                {"purge_floor": purge_floor, "limit": limit, "offset": offset},
            )
        ).all()
        totals = (
            await session.execute(text(COUNT_SQL), {"purge_floor": purge_floor})
        ).first()

    eligible_total = int(totals[0]) if totals else -1
    excluded_purged = int(totals[1]) if totals else -1
    never_swept = int(totals[2]) if totals else -1
    provisional_recheck = int(totals[3]) if totals else -1

    stats = {
        "eligible_total": eligible_total,
        "excluded_purged": excluded_purged,
        # The two selection reasons, reported apart. `never_swept` is the original
        # backlog and can only shrink; `provisional_recheck` is the population that
        # refills whenever a market is swept before the venue settles it, and is the
        # reason this sweep is not a one-off (CAL-P992).
        "never_swept": never_swept,
        "provisional_recheck": provisional_recheck,
        "candidates": len(rows),
        "moved_earlier": 0,
        "unchanged": 0,
        "newly_past": 0,
        "fallback_no_close_time": 0,
        "unresolvable_at_venue": 0,
        "errors": 0,
    }
    samples: list[dict] = []

    if not rows:
        # Not a success. Either the migration has not run, or the floor has
        # excluded everything left — two very different facts, so print both
        # numbers rather than one word.
        stats["writes_prepared"] = 0
        stats["writes_applied"] = 0
        return {
            "mode": "APPLY" if apply else "DRY_RUN",
            "measured_at": now.isoformat(),
            "purge_floor": purge_floor.isoformat(),
            "zero_yield": True,
            "zero_yield_reason": (
                f"no candidates at offset {offset}: {eligible_total} rows still "
                f"eligible ({never_swept} never swept, {provisional_recheck} holding "
                f"a provisional date), {excluded_purged} of them past the purge "
                "floor. If eligible_total is 0 the migration may not have run; if it "
                "equals excluded_purged the recoverable population is exhausted."
            ),
            "stats": stats,
            "newly_past_samples": [],
        }

    sem = asyncio.Semaphore(concurrency)
    client = client_factory()

    async def handle(row) -> Optional[dict]:
        market_id, ticker, stored_rd, commence, tier = row

        async with sem:
            try:
                event = await client.get_event(ticker, with_nested_markets=True)
            except Exception:
                stats["errors"] += 1
                return None

        markets = (event or {}).get("markets") or []
        if not markets:
            # 200-with-no-markets and 404 are NOT the same fact, but neither
            # yields a date. Counted apart from errors so a zero-yield run
            # cannot read as a clean one.
            stats["unresolvable_at_venue"] += 1
            return None

        window = derive_resolution_window(
            [
                _Leg(_parse(m.get("close_time")), _parse(m.get("expiration_time")))
                for m in markets
            ]
        )
        if window.resolution_date is None:
            stats["unresolvable_at_venue"] += 1
            return None
        if window.used_expiration_fallback:
            stats["fallback_no_close_time"] += 1

        if stored_rd is not None and window.resolution_date < stored_rd:
            stats["moved_earlier"] += 1
            if stored_rd > now >= window.resolution_date:
                stats["newly_past"] += 1
                if len(samples) < 15:
                    samples.append(
                        {
                            "id": market_id,
                            "ticker": ticker,
                            "tier": tier,
                            "was": stored_rd.isoformat(),
                            "now": window.resolution_date.isoformat(),
                        }
                    )
        else:
            stats["unchanged"] += 1

        return {
            "id": market_id,
            "resolution_date": window.resolution_date,
            "expiration_time": window.expiration_time,
            "updated_at": now,
        }

    try:
        results = await asyncio.gather(*(handle(r) for r in rows))
    finally:
        # `BaseAPIClient` exposes `close()` and no `__aenter__`, so `async with`
        # on the service raises AttributeError. Explicit try/finally instead.
        close = getattr(client, "close", None)
        if close is not None:
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe

    writes = [r for r in results if r]
    stats["writes_prepared"] = len(writes)

    if apply and writes:
        async with session_maker() as session:
            for chunk_start in range(0, len(writes), 500):
                chunk = writes[chunk_start : chunk_start + 500]
                for w in chunk:
                    await session.execute(text(UPDATE_SQL), w)
                await session.commit()
        stats["writes_applied"] = len(writes)
    else:
        stats["writes_applied"] = 0

    report = {
        "mode": "APPLY" if apply else "DRY_RUN",
        "measured_at": now.isoformat(),
        "purge_floor": purge_floor.isoformat(),
        "offset": offset,
        "zero_yield": len(writes) == 0,
        "stats": stats,
        "newly_past_samples": samples,
    }
    if stats["unresolvable_at_venue"] == len(rows):
        # Every slot in the batch went to a row this script may not write. Those
        # rows keep their slot, so an unattended re-run selects them again.
        report["batch_fully_unresolvable"] = (
            f"all {len(rows)} selected rows were unresolvable at the venue and "
            "none can be written (a missing date is not a status change). "
            f"Re-running at --offset {offset} selects the same rows; advance the "
            "offset to reach the recoverable tail."
        )
    return report


# ---------------------------------------------------------------------------
# The unattended entry point
# ---------------------------------------------------------------------------


async def run_sweep(
    *,
    limit: int = SWEEP_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    session_maker: Optional[Callable] = None,
    client_factory: Optional[Callable[[], object]] = None,
) -> dict:
    """One bounded beat run, with terminal truth attached.

    THE TERMINAL IS THE POINT, not decoration. ``_tracked_run`` classifies this
    summary through ``app.utils.task_verdict``, and a summary with no terminal
    field is recorded as a success merely because the invocation returned —
    which is how three calibration tasks reported ``health: healthy`` while
    producing nothing (#1515). This sweep has a zero-yield mode that is a
    perfectly normal return value, so it must say which zero it is:

    * **complete** — the batch wrote what the venue gave it, OR nothing is
      eligible at all (the population really is drained).
    * **partial** — rows were selected and NOTHING could be written. The batch
      spent its whole slot on rows the venue would not resolve; the population
      did not move and the next run selects the same head. Never green.
    * **failed** — every selected row errored at the venue. That is an outage,
      not a drained population, and it must not read as either of the above.

    ``apply`` defaults to TRUE here and FALSE in ``run_backfill``, deliberately:
    the CLI's default must be the harmless one because a human types it, and the
    beat's default must be the useful one because nobody is there to pass a flag.
    """
    from app.services.database import async_session_maker

    report = await run_backfill(
        session_maker=session_maker or async_session_maker,
        client_factory=client_factory or KalshiAPIService,
        limit=limit,
        offset=0,
        apply=apply,
        concurrency=concurrency,
    )

    stats = report.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    applied = int(stats.get("writes_applied") or 0)
    errors = int(stats.get("errors") or 0)

    if candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = f"all {candidates} selected rows errored at the venue"
    elif candidates and applied == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} rows selected, 0 written — "
            f"{stats.get('unresolvable_at_venue')} unresolvable at the venue"
        )
    else:
        report["terminal"] = "complete"

    # The population this run did NOT reach, carried on the summary so a bounded
    # sweep can never be read as a finished one — the same reason `run_backfill`
    # reports `eligible_total` beside `candidates`.
    report["remaining_after_batch"] = max(
        0, int(stats.get("eligible_total") or 0) - applied
    )
    return report
