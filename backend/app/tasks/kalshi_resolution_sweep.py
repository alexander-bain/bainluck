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
# The rotating cursor — CAL-P998, measured on the first unattended-shaped run
# ---------------------------------------------------------------------------

#: Where the next batch starts. A ROTATING cursor, and it exists because the
#: first production run of this sweep under CAL-P998 selected 500 rows and wrote
#: zero.
#:
#: WHAT WAS MEASURED (2026-09-03 16:17 PT, `heroku run:detached`, `--limit 500
#: --apply`). Before and after on the exact selected batch: 411 rows with a NULL
#: `expiration_time` before and 411 after, 89 sealed before and 89 after, 0
#: converged. `pg_stat_statements` confirms the run happened and what it did:
#: `SELECT_SQL` **1 call, 500 rows, 185 ms**, `COUNT_SQL` 1 call — and **no
#: matching UPDATE statement recorded at all.** (The dyno's stdout is not
#: readable from the agent sandbox — `heroku logs` returns EPERM — so the
#: distinction between "ran and yielded nothing" and "never ran" was settled by
#: a second signal rather than assumed. Gotcha #53.)
#:
#: WHY, off the head of the batch itself:
#:
#:     KXTXPRIMARY-31D26   commence_time 2027-11-03   resolution_date 2027-11-03
#:                         expiration_time NULL       updated_at 2026-06-20
#:
#: `commence_time` equals the backstop — the poisoned-column shape #2771 named
#: (4,954 of 5,143 sealed rows carry `commence_time = expiration_time`). So the
#: retention floor, which is a `commence_time` test, reads these as recent and
#: admits them, while the venue purged them months ago and returns no markets.
#: They yield no date, and a row this script may not write is a row whose
#: `updated_at` is never refreshed — so under `ORDER BY updated_at ASC` it stays
#: at the head **forever**.
#:
#: #2771's rotation argument ("every write refreshes the stamp, so the sweep
#: rotates") is true only of rows that get written. Unwritable rows do not
#: rotate, and 500 of them are enough to jam the entire beat: 5,143 sealed rows
#: at 05:00Z became 5,137 seventeen hours later, which is what a jam looks like
#: from outside.
#:
#: The script's own docstring already names the remedy for a human — *"`--offset`
#: exists so an operator can advance past a stuck prefix rather than re-running
#: into it"*. An unattended beat has no operator, so it must do that itself.
#:
#: 🔴 **CERT-863 BLOCK (2026-09-04) — the offset alone could not wrap, so the
#: jam it skipped was never re-reached.** The cursor held TWO facts in one
#: number and they diverge. `offset` answers *"how far past the stuck prefix am
#: I"*; the wrap needs *"how much of the population has this cycle seen"*, and
#: on a stable, fully-writable suffix the first stops moving while the second
#: must keep going. The cert's exact-head reproduction — a 1,500-row population
#: whose first 500 are stranded, then three clean batches — printed
#: ``0 -> 500 -> 500 -> 500 -> 500``. Every clean batch strands nothing, so
#: `offset + stranded` re-returns 500 forever, the wrap test never fires, and
#: the only thing that ever sends the sweep back to the head is the 30-day TTL
#: below. A market that is unresolvable in September and finalized in October
#: therefore keeps rendering its dead last-trade price for up to a month — which
#: is the exact failure this whole ship claims to end, so the claim did not hold.
#:
#: The two facts are now stored as two, and the pair travels together in ONE
#: Redis value (``"<offset>:<scanned>"``) rather than two keys: a half-written
#: pair is a cursor that says a cycle is further along than the offset it
#: carries, which skips rows silently — the failure mode this repair exists to
#: remove. A legacy bare ``"500"`` left in Redis by the pre-repair beat parses as
#: ``(500, 0)``, so the first run after deploy starts where the old cursor
#: pointed and begins counting its cycle from there.
SWEEP_CURSOR_KEY = "bainluck:kalshi_resolution_sweep:offset"

#: 30 days. Long enough that a fortnight of failed beats does not silently reset
#: the sweep to the jammed head; short enough that a stale cursor left behind by
#: a retired population expires instead of skipping rows forever.
#:
#: It is a BACKSTOP and must never be the mechanism. Before CERT-863's repair it
#: was the mechanism — expiry was the only path back to offset 0 — and a backstop
#: doing load-bearing work is how a 30-day dead-price window looked like a
#: working nightly sweep. The cycle wrap in :func:`next_cursor` now returns to
#: the head in ``ceil(eligible_total / limit)`` runs; at the measured 6,302
#: eligible rows and a 500-row batch that is ~13 nights, comfortably inside this.
SWEEP_CURSOR_TTL_S = 60 * 60 * 24 * 30


async def _read_cursor() -> tuple[int, int]:
    """``(offset, scanned)`` to start at. An unreadable cursor is the head.

    ``(0, 0)`` is the pre-cursor behaviour, so a Redis outage degrades this sweep
    to exactly what it did before the cursor existed rather than taking it down.

    A bare integer is the pre-CERT-863 encoding and is read as ``(offset, 0)``:
    the offset is still true, and starting that cycle's traversal count at zero
    only makes the first wrap after deploy late by at most one cycle. Guessing a
    `scanned` to match would be inventing a measurement.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        raw = await get_async_redis_client().get(SWEEP_CURSOR_KEY)
        if isinstance(raw, bytes):
            raw = raw.decode()
        offset_s, _, scanned_s = str(raw).partition(":")
        return max(0, int(offset_s)), max(0, int(scanned_s or 0))
    except Exception:  # noqa: BLE001 — a missing cursor is a start, not a failure
        return 0, 0


async def _write_cursor(offset: int, scanned: int) -> bool:
    """Persist the pair. Returns whether it landed — the caller reports it.

    Swallowing this would be the worst option available: the run would look
    clean, the cursor would stay where it was, and the next beat would re-enter
    the same jam. So the boolean travels onto the summary and into the terminal.

    One key, one round trip, both numbers — see :data:`SWEEP_CURSOR_KEY` for why
    the pair must not be split across two keys.
    """
    try:
        from app.tasks.redis_state import get_async_redis_client

        await get_async_redis_client().set(
            SWEEP_CURSOR_KEY,
            f"{int(offset)}:{int(scanned)}",
            ex=SWEEP_CURSOR_TTL_S,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def next_cursor(
    *, offset: int, scanned: int, candidates: int, applied: int, eligible_total: int
) -> tuple[int, int]:
    """The next ``(offset, scanned)``, given what this batch could not move.

    ## The offset half — where the next batch starts

    ``candidates - applied`` is exactly the number of rows that KEPT their slot:
    a written row rotates to the back of `updated_at ASC` on its own (the write
    refreshes the stamp), an unwritten one does not. Advancing by that number —
    not by ``limit`` — is what makes the cursor track the jam rather than a
    batch size, so a run that writes 470 of 500 advances 30 and a run that
    writes none advances a full batch.

    A CLEAN BATCH HOLDS ITS OFFSET; IT DOES NOT RESET. This is the correction
    that the offset-500 measurement forced, and it is worth spelling out because
    the reset is the obvious first implementation and it re-enters the jam every
    other night. Measured 2026-09-03: offset 0 is 500 unwritable rows last
    touched in June, and offset 500 is 500 rows the poller touched today which
    all write cleanly. Under "reset to 0 when nothing was stranded" the sweep
    alternates jam / productive / jam / productive and burns half its nights.
    Holding the offset is also simply correct: when 500 rows rotate to the back,
    the row that was at position 1,000 is now at position 500, so the same
    offset points at fresh content.

    ## The scanned half — CERT-863, and why the offset cannot also do this job

    Holding the offset is right, and it is exactly what made the wrap
    unreachable: a run of clean batches strands nothing, so an offset-only
    cursor is CORRECTLY motionless while the cycle is in fact advancing through
    a rotating suffix. The two facts had to be separated. ``scanned`` accumulates
    ``candidates`` — the rows this cycle has actually looked at — and it is a
    fair count of traversal precisely BECAUSE the suffix rotates: a clean batch
    at a held offset reads 500 rows it has not read before this cycle.

    IT WRAPS ON TRAVERSAL, NOT ON ARITHMETIC LUCK. Once ``scanned + candidates``
    reaches the eligible population the cycle is done: offset and scanned both
    return to 0 and the next run re-reads the head — the stranded prefix
    included. That is the promise the module made and could not keep. The venue
    publishes `close_time` on finalize, so September's unresolvable row is
    October's necessary write, and it is now re-offered every
    ``ceil(eligible_total / limit)`` runs instead of once a month by expiry.

    The old walk-off-the-end guard is kept beside it rather than replaced.
    ``offset <= scanned`` holds for any cursor this function produces (stranded
    is never more than candidates), so on a consistent cursor the traversal test
    always fires first — but a legacy bare offset, or a population that shrank
    under the cursor, can present a high offset with a low scanned, and then the
    offset test is the one that saves the run from selecting nothing forever.
    """
    if candidates == 0:
        # Nothing at this offset: either the cursor is past the end of a
        # population that shrank, or the population is empty. Both are the end
        # of a cycle, not a failure — start the next one at the head.
        return 0, 0

    traversed = scanned + candidates
    advanced = offset + max(0, candidates - applied)

    if eligible_total <= 0 or traversed >= eligible_total or advanced >= eligible_total:
        return 0, 0
    return advanced, traversed


# ---------------------------------------------------------------------------
# The unattended entry point
# ---------------------------------------------------------------------------


async def run_sweep(
    *,
    limit: int = SWEEP_BATCH_LIMIT,
    concurrency: int = SWEEP_CONCURRENCY,
    apply: bool = True,
    offset: Optional[int] = None,
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

    ``offset`` defaults to the rotating cursor. Pass an explicit one only to pin
    a run; see :data:`SWEEP_CURSOR_KEY` for the measurement that made the cursor
    necessary — without it this beat writes zero rows every night, forever, and
    looks healthy doing it.
    """
    from app.services.database import async_session_maker

    if offset is None:
        start, scanned = await _read_cursor()
    else:
        # An explicitly pinned run is a probe of one batch, not a step in the
        # cycle, so it starts that cycle's traversal count at zero rather than
        # crediting the pin against a cycle it did not walk.
        start, scanned = max(0, int(offset)), 0

    report = await run_backfill(
        session_maker=session_maker or async_session_maker,
        client_factory=client_factory or KalshiAPIService,
        limit=limit,
        offset=start,
        apply=apply,
        concurrency=concurrency,
    )

    stats = report.get("stats") or {}
    candidates = int(stats.get("candidates") or 0)
    applied = int(stats.get("writes_applied") or 0)
    errors = int(stats.get("errors") or 0)
    eligible = int(stats.get("eligible_total") or 0)

    nxt, nxt_scanned = next_cursor(
        offset=start,
        scanned=scanned,
        candidates=candidates,
        applied=applied,
        eligible_total=eligible,
    )
    # BOTH halves must be unchanged to skip the write. The offset alone standing
    # still is the normal healthy case (a clean batch holds it) and it is exactly
    # when `scanned` is moving — skipping the write on the offset alone is how
    # cycle progress would be dropped every productive night, which is the
    # CERT-863 defect rebuilt inside the optimisation that was meant to be free.
    unchanged = nxt == start and nxt_scanned == scanned
    persisted = True if unchanged else await _write_cursor(nxt, nxt_scanned)

    report["offset"] = start
    report["next_offset"] = nxt
    report["scanned_before"] = scanned
    report["next_scanned"] = nxt_scanned
    # The cycle closed on this run: the next beat re-reads the head, stranded
    # prefix included. Named on the summary because "the sweep went back to 0"
    # must be legible as a completed traversal rather than as a lost cursor.
    report["cycle_wrapped"] = nxt == 0 and nxt_scanned == 0 and start != 0
    report["stranded"] = max(0, candidates - applied)
    report["cursor_persisted"] = persisted

    if not persisted:
        # Progress may have been made and it is silently unresumable: the next
        # beat re-enters this exact batch and the jam returns. The typeahead
        # index builder makes the same call for the same reason (#1866).
        report["terminal"] = "failed"
        report["terminal_reason"] = (
            f"cursor not persisted — the next run repeats offset {start} "
            f"instead of advancing to {nxt}"
        )
    elif candidates and errors >= candidates:
        report["terminal"] = "failed"
        report["terminal_reason"] = f"all {candidates} selected rows errored at the venue"
    elif candidates and applied == 0:
        report["terminal"] = "partial"
        report["terminal_reason"] = (
            f"{candidates} rows selected, 0 written — "
            f"{stats.get('unresolvable_at_venue')} unresolvable at the venue; "
            f"cursor advanced {start} -> {nxt} so the next run does not re-enter it"
        )
    else:
        report["terminal"] = "complete"

    # The population this run did NOT reach, carried on the summary so a bounded
    # sweep can never be read as a finished one — the same reason `run_backfill`
    # reports `eligible_total` beside `candidates`.
    report["remaining_after_batch"] = max(0, eligible - applied)
    return report
