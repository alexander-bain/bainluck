"""Q499 — the residual half of Q492: a price that names no side, drained.

PILLAR: FORMATTING. SHIP: a price on the US Open page names its side — for the
1,152 markets where it still doesn't.

WHAT THIS IS THE SECOND HALF OF
-------------------------------
Q492 (`c3143bc2`, merged and deployed) fixed the WRITER. Polymarket sends a
game-level moneyline with ``groupItemTitle: null`` and the question set to the
event's own title, so ``_extract_outcome_name``'s "short enough, use it
directly" fallback labelled the price with the whole matchup — a card reading
"US Open WTA: Iga Swiatek vs Nadia Podoroska 89.5%". 89.5% of *what*?
``_leg_label`` now rescues that case from ``outcomes[0]``, the array parallel to
``outcome_prices``, and every newly-ingested market is correct.

The report for that fix concluded 🟢 "NO BACKFILL IS NEEDED", projected from the
upsert's ``on_conflict_do_update`` clause. The clause is real. It never fires on
a row nobody re-reads.

🔴 A SELF-HEALING CLAIM IS A CLAIM ABOUT COVERAGE, NOT ABOUT THE WRITER.
The owed post-deploy check had two halves. The qualitative one passed (market
59970465 went from the full matchup to "Iga Swiatek") and read as proof. The
census half was skipped on a query timeout and named as skipped. Live 025 ran
it: **1,370 → 1,152**, a 16% fall and not a trend toward zero. ``table_tennis``
1,195 → 984, but ``tennis`` 92 → **92**, ``football`` 45 → **45**, and
baseball / basketball / geopolitics / rugby did not move at all. The control
that makes this a measurement: in ``table_tennis``, 222 of 11,286 non-collapsed
rows were touched since the deploy against **3** of 984 collapsed ones — uniform
sampling predicts ~19, so the cohort is revisited at ~1/6 the rate — and the
repaired count (1,195 − 984 = 211) tracks the touched count (222) almost
exactly. The rows that self-healed are the rows the poller happened to visit.
The rest are out of its rotation and will not heal.

Re-measured by this rail's author 2026-09-01: **1,153 legs across 1,152
markets** (one market carries two collapsed legs), unchanged from 025's count.
A static population is the argument for a drain.

WHY THE VENUE IS THE ONLY PLACE THE ANSWER EXISTS
-------------------------------------------------
The correct label is ``outcomes[0]`` and it is **not recoverable from the
database**. These markets keep exactly one surviving outcome — the only leg with
a real book — so there is no sibling to derive a side from, and
``futures_outcomes.external_id`` holds the ``0x…`` condition hash, not a name.

🔴 DERIVING "X" FROM THE MARKET NAME "Venue: X vs Y" IS THE TEMPTING SHORTCUT
AND IT IS FORBIDDEN HERE. It is exactly the M2 mutant Q492's own guard was built
to catch: it would destroy every informative ``groupItemTitle``, and it cannot
tell which of X and Y this price belongs to — which is the entire defect. This
module therefore contains **no label rule of its own**. It calls the shipped
``_leg_label``, byte-for-byte the function the poller calls, and a guard fails
the build if this file ever grows a matchup-splitting rule.

WHAT THE VENUE READ COST, AND THE TRAP IN IT
--------------------------------------------
🔴 ``/markets?condition_ids=…`` SILENTLY APPLIES ``closed=false``. Measured on a
40-id sample from this exact cohort: the default call returned **7 of 40**, and
``closed=true`` returned the other **33**. Union: 40 of 40, nothing missing. A
drain built on the default read would have reported 82% of its own population
``not_at_venue`` and looked like it had finished. ``include_closed=True``
(Q499, ``PolymarketAPIService``) makes both calls and unions them; the pair
measured 0.27s + 0.36s for 40 ids.

All 40 carried a usable side name in ``outcomes[0]`` — no Yes/No, no collapse.

THE CONTRACT
------------
``census``  — read-only. Never writes; ``apply`` is accepted and ignored. A
timeout returns ``measured: false`` with a reason, NEVER a zero (gotcha #54): a
zero here would read as "drained".

``repair``  — dry-run by default. Keyset-paged on ``futures_outcomes.id`` via
``?after_id=``, because the write removes rows from the rail's own population
and an offset would skip as many untouched rows as the last page repaired. Every
write is a compare-and-set on the exact name it selected on, so a concurrent
re-ingest is never clobbered, and it names **one column** — ``last_updated`` is
a poller touch-stamp another surface reads as liveness (#2024) and a repair must
not forge it.

ATTENDED ONLY: never wire either to a beat. This is a drain with an end state,
not a standing job. Read ``scan_exhausted``, not ``remaining_legs``.
"""

import asyncio
import logging
import time
from typing import Any, Optional

# The bounds this rail runs its database work under are NOT re-implemented here.
# They took four cert rounds to get right on the sibling drain (CERT-666 → 667 →
# 670 → 673 → 674), and a second copy of a bound is a second thing to get wrong.
from app.tasks.repair_polymarket_sport_category import (  # noqa: F401  (re-exported for guards)
    ClientDeadlineExceeded,
    _bounded_statement,
    _safe_rollback,
    client_db_budget_seconds,
)

# The SHIPPED label rule, imported rather than restated. See the module
# docstring: a second labeller is a second classifier free to drift from the
# poller, and the drift would be invisible because both answers look plausible.
from app.tasks.polymarket import _leg_label

logger = logging.getLogger(__name__)


#: The Heroku router's hard wall on a synchronous request. Past this the router
#: returns H12 and the operator gets no body at all — no counts, and crucially
#: no ``next_cursor``, so an attended drain loses its place rather than pausing.
#: Every budget below is derived from this number.
ROUTER_WALL_SECONDS = 30

#: One venue STEP is a batch PAIR — the default read plus the ``closed=true``
#: read — budgeted together rather than per request, because the pair is what
#: the loop actually waits on and two separate 8s bounds would permit 16s.
#: Measured 0.27s + 0.36s for 40 ids on production Gamma 2026-09-01, so this is
#: ~9.5x the observed cost.
BATCH_PAIR_BUDGET_SECONDS = 6.0

#: Condition ids per venue request. 40 keeps the URL ~3.3KB (measured), well
#: clear of the 414 the sibling helper's docstring warns about.
GAMMA_BATCH_SIZE = 40

#: Pause between venue steps. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35

#: The point past which no NEW batch is started. Checked at the top of the loop,
#: so the true worst case is this plus one whole batch pair plus one pause plus
#: everything after the loop — see ``budget_headroom_seconds()``, which a guard
#: asserts stays positive rather than leaving the arithmetic in a comment.
DEADLINE_SECONDS = 15

#: Time reserved for everything that happens AFTER the loop's last fetch: the
#: single bulk write, its commit, the ``remaining_legs`` terminal count,
#: response serialization, and the request dependency's own commit — which runs
#: after the handler has returned and so cannot be observed from inside it.
POST_LOOP_RESERVE_SECONDS = 5.5

#: The slice of the reserve that is NOT the terminal count. The count is armed
#: with whatever is left of the wall once this is set aside, so an over-running
#: loop shortens the count's timeout instead of borrowing against work that
#: still has to run. It must cover the CLIENT bound of BOTH post-loop database
#: units — the update and the commit — and their cleanup: "the failure path
#: costs more than the success path" is the easy thing to forget when sizing a
#: budget from the happy case. A guard asserts the two derived client bounds fit
#: inside it, rather than trusting three numbers to be edited together.
POST_LOOP_NON_COUNT_RESERVE_SECONDS = 3.5

#: Bound on the page SELECT. It does not widen the worst case: ``started`` is
#: captured BEFORE this query, so a slow SELECT does not add to the total, it
#: just leaves the loop less room and the first deadline check stops it. That
#: holds only while this stays at or under ``DEADLINE_SECONDS``, which a guard
#: asserts.
TARGET_SELECT_BUDGET_SECONDS = 10.0

#: Bound on the single bulk compare-and-set UPDATE. One statement per page keyed
#: by primary key over at most ``APPLY_LEG_CAP`` rows; the realistic cost is
#: milliseconds and the bound exists for the row lock the ordinary poller can be
#: holding on the very legs this rail is rewriting.
WRITE_BUDGET_SECONDS = 1.5

#: 🔴 THE COMMIT IS A SEPARATE UNIT BECAUSE THE RESULT IS READ BEFORE IT.
#:
#: The write is ``UPDATE … RETURNING fo.id`` and those ids are the ONLY way to
#: tell a row that landed from a row the ordinary poller re-ingested between the
#: SELECT and the write. Reading a cursor after its transaction has committed is
#: a claim about SQLAlchemy's buffering, not about this rail — so the rows are
#: read while the transaction is still open, and the commit is its own bounded
#: statement afterwards. A commit runs on the same connection and can block on
#: the very lock the update took, so it gets a real bound rather than riding on
#: the update's.
COMMIT_BUDGET_SECONDS = 0.5

#: Legs examined per call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
#: 120 legs is three batch pairs — ~1.9s of measured venue time plus 1.05s of
#: pause — so a full page normally COMPLETES and ``stopped_before`` stays the
#: exception it is meant to be. The whole 1,153-leg cohort is ten calls.
APPLY_LEG_CAP = 120

#: Statement timeout for the census, which runs TWO queries under ONE router
#: wall. At 12s its own permitted worst case is 24s, inside the wall — a census
#: that H12s returns no body, so its honest "we could not look" answer would
#: never reach the operator and the whole gotcha-#54 argument would evaporate at
#: exactly the moment it matters.
CENSUS_STATEMENT_TIMEOUT_SECONDS = 12

#: Bound on the terminal ``remaining_legs`` count, capped by what the reserve
#: actually has left. Degradable on purpose: it reports itself unmeasured, it
#: never reports zero.
REMAINING_COUNT_MIN_BUDGET_SECONDS = 0.5

#: 🔴 THE POPULATION PREDICATE, WRITTEN ONCE. The census and the pager must not
#: be able to disagree about what a collapsed leg is.
#:
#: ``IS NOT DISTINCT FROM`` rather than ``=`` is a PLAN choice, not a null-safety
#: flourish, and it is the reason this rail can run at all. With ``=`` the
#: planner ``BitmapAnd``s the ``futures_outcomes.name`` index into every
#: per-market probe (~8ms each; EXPLAIN cost 86,006) and the query times out at
#: 10s even narrowed to one category. ``IS NOT DISTINCT FROM`` is non-indexable,
#: so the planner drops the name index and probes ``ix_futures_outcomes_market_id``
#: alone: **10s timeout → 152ms** measured on production 2026-09-01, and ~2.5s
#: for the full per-category GROUP BY. Same answer, no index, no migration.
COLLAPSED_LEG_PREDICATE = "fo.name IS NOT DISTINCT FROM fm.name"

#: Verdicts a single leg can reach. Every one is COUNTED — ruling 054: an
#: exclusion is counted, not skipped, and each zero state gets its own terminal
#: rather than one silent success (gotcha #53).
LEG_VERDICTS = (
    "relabelled",
    "unchanged",
    "not_at_venue",
    "no_condition_id",
    "refused_collision",
    "raced",
)


class VenueUnavailable(Exception):
    """The venue did not answer a batch: 429, 5xx, or a timeout.

    Distinct from "the market is not there". Nothing is written for a batch that
    raises this and the cursor RETRIES it — a throttled fetch treated as an
    empty answer would relabel nothing and report the cohort drained
    (gotcha #36, and gotcha #53's "an empty 200 is not an absence").
    """


def budget_headroom_seconds() -> float:
    """Seconds left under the router wall in the rail's WORST case.

    The deadline is checked at the top of the loop, so after it passes the rail
    may still start one whole batch pair and one pause; and after that the write,
    the terminal count, serialization and the dependency's commit still run.

    Expressed as a function so a guard can assert it stays positive, rather than
    as a comment that goes stale the first time someone raises one of the four
    numbers. Positive means an over-running call returns a partial answer WITH
    its cursor. Negative means H12 with no body, and an attended drain silently
    loses its place.
    """
    return ROUTER_WALL_SECONDS - (
        DEADLINE_SECONDS
        + BATCH_PAIR_BUDGET_SECONDS
        + VENUE_PAUSE
        + POST_LOOP_RESERVE_SECONDS
    )


def _paused_before_examining(
    *,
    incoming_cursor: Optional[dict[str, Any]],
    started: float,
    terminal: str,
    reason: str,
) -> dict[str, Any]:
    """The response for a page that died before it examined anything.

    Every count is zero and ``next_cursor`` is the cursor the operator HANDED
    IN, unchanged. Nothing was examined, so nothing may advance — re-running
    with it repeats the page rather than skipping it, which is the whole point
    of answering at all instead of letting the router return H12 with no body.
    """
    return {
        "repair": "polymarket-leg-label",
        "applied": False,
        "counts": {"legs_examined": 0, **{v: 0 for v in LEG_VERDICTS}},
        "samples": [],
        "remaining_legs": None,
        "remaining_legs_measured": False,
        "scan_exhausted": False,
        "next_cursor": incoming_cursor,
        "stopped_before": None,
        "terminal": terminal,
        "reason": reason,
        "cap": APPLY_LEG_CAP,
        "elapsed_s": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------


async def census(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """How many open Polymarket legs still print a number that names no side.

    Split by ``llm_sport_category``, because "1,152" alone cannot tell a drain
    that is working from one that is only reaching the category the poller
    happens to rotate through — the exact reading that let Q492's partial fix
    look complete.

    ``apply`` is accepted and ignored. A census that could write would be a
    repair with a reassuring name.
    """
    started = time.monotonic()
    out: dict[str, Any] = {
        "census": "polymarket-leg-label",
        "measured": False,
        "reason": None,
        "total_legs": None,
        "total_markets": None,
        "by_category": {},
    }

    sql = f"""
        SELECT COALESCE(fm.llm_sport_category, '(null)') AS category,
               count(*) AS legs,
               count(DISTINCT fm.id) AS markets
          FROM futures_markets fm
          JOIN futures_outcomes fo
            ON fo.market_id = fm.id
           AND {COLLAPSED_LEG_PREDICATE}
         WHERE fm.source = 'polymarket'
           AND fm.status = 'open'
         GROUP BY 1
         ORDER BY 2 DESC
    """

    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{CENSUS_STATEMENT_TIMEOUT_SECONDS}s'",
            server_budget_s=float(CENSUS_STATEMENT_TIMEOUT_SECONDS),
            sql=sql,
        )
        rows = result.fetchall()
    except ClientDeadlineExceeded as exc:
        await _safe_rollback(session)
        out["reason"] = f"pool_timeout: {exc}"
        out["elapsed_s"] = round(time.monotonic() - started, 2)
        return out
    except Exception as exc:  # noqa: BLE001 — a census that cannot look says so
        await _safe_rollback(session)
        out["reason"] = f"census_query_failed: {type(exc).__name__}: {exc}"
        out["elapsed_s"] = round(time.monotonic() - started, 2)
        return out

    by_category = {str(r[0]): {"legs": int(r[1]), "markets": int(r[2])} for r in rows}
    out["measured"] = True
    out["by_category"] = by_category
    out["total_legs"] = sum(v["legs"] for v in by_category.values())
    out["total_markets"] = sum(v["markets"] for v in by_category.values())
    out["elapsed_s"] = round(time.monotonic() - started, 2)
    return out


# ---------------------------------------------------------------------------
# The venue read
# ---------------------------------------------------------------------------


async def _fetch_batch(service, condition_ids: list[str]) -> dict[str, Any]:
    """Ask the venue for one batch of named markets, open AND closed.

    Returns ``{condition_id: PolymarketMarket}``. Raises ``VenueUnavailable``
    rather than returning a short dict when the venue does not answer, because
    a throttled fetch that returned fewer markets would be indistinguishable
    from those markets having been delisted.
    """
    try:
        markets = await asyncio.wait_for(
            service.get_markets_by_conditions(
                condition_ids,
                batch_size=GAMMA_BATCH_SIZE,
                include_closed=True,
            ),
            timeout=BATCH_PAIR_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise VenueUnavailable(
            f"no answer inside the {BATCH_PAIR_BUDGET_SECONDS}s batch-pair bound"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — 429/5xx re-raised as one verdict
        raise VenueUnavailable(f"{type(exc).__name__}: {exc}") from exc

    return {m.condition_id: m for m in markets if getattr(m, "condition_id", None)}


# ---------------------------------------------------------------------------
# Repair — dry-run by default.
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int = None,
    sport: str = None,
    after_id: int = None,
) -> dict[str, Any]:
    """Re-ask the venue for each side-less leg and store the shipped label.

    ``sport`` filters ``llm_sport_category`` — an operator draining the tennis
    cohort before the Setka backlog is choosing an order, not a different
    population. ``after_id`` is a keyset cursor on ``futures_outcomes.id``.
    """
    started = time.monotonic()
    cap = min(int(limit), APPLY_LEG_CAP) if limit else APPLY_LEG_CAP
    incoming_cursor = {"after_id": int(after_id)} if after_id else None

    counts: dict[str, int] = {"legs_examined": 0, **{v: 0 for v in LEG_VERDICTS}}
    samples: list[dict[str, Any]] = []

    # ---- the page --------------------------------------------------------
    page_sql = f"""
        SELECT fo.id           AS outcome_id,
               fo.market_id    AS market_id,
               fo.external_id  AS condition_id,
               fo.name         AS outcome_name,
               fm.name         AS market_name,
               fm.llm_sport_category AS category
          FROM futures_markets fm
          JOIN futures_outcomes fo
            ON fo.market_id = fm.id
           AND {COLLAPSED_LEG_PREDICATE}
         WHERE fm.source = 'polymarket'
           AND fm.status = 'open'
           AND (:after_id::bigint IS NULL OR fo.id > :after_id::bigint)
           AND (:sport::text IS NULL OR fm.llm_sport_category = :sport::text)
         ORDER BY fo.id
         LIMIT :cap::int
    """
    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{TARGET_SELECT_BUDGET_SECONDS}s'",
            server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
            sql=page_sql,
            params={"after_id": after_id, "sport": sport, "cap": cap},
        )
        page = result.fetchall()
    except ClientDeadlineExceeded as exc:
        await _safe_rollback(session)
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="paused_pool_timeout",
            reason=f"no pooled connection came free: {exc}",
        )
    except Exception as exc:  # noqa: BLE001 — the page SELECT is the first thing
        await _safe_rollback(session)
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="paused_target_timeout",
            reason=f"page select did not finish: {type(exc).__name__}: {exc}",
        )

    if not page:
        out = _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="ok",
            reason="no collapsed legs remain in this population",
        )
        out["scan_exhausted"] = True
        out["applied"] = bool(apply)
        return out

    rows = [
        {
            "outcome_id": int(r[0]),
            "market_id": int(r[1]),
            "condition_id": (r[2] or "").strip(),
            "outcome_name": r[3],
            "market_name": r[4],
            "category": r[5],
        }
        for r in page
    ]

    # ---- the venue loop --------------------------------------------------
    from app.services.polymarket_api import PolymarketAPIService

    service = PolymarketAPIService()
    planned: list[dict[str, Any]] = []
    stopped_before: Optional[int] = None
    venue_reason: Optional[str] = None
    last_examined: Optional[int] = None
    examined_rows: list[dict[str, Any]] = []

    try:
        for start in range(0, len(rows), GAMMA_BATCH_SIZE):
            if time.monotonic() - started > DEADLINE_SECONDS:
                stopped_before = rows[start]["outcome_id"]
                break

            batch = rows[start : start + GAMMA_BATCH_SIZE]
            addressable = [r["condition_id"] for r in batch if r["condition_id"]]

            found: dict[str, Any] = {}
            if addressable:
                try:
                    found = await _fetch_batch(service, addressable)
                except VenueUnavailable as exc:
                    # Nothing in THIS batch was examined, so the cursor stops
                    # before it and a retry repeats it rather than stepping over.
                    stopped_before = batch[0]["outcome_id"]
                    venue_reason = str(exc)
                    break

            for row in batch:
                counts["legs_examined"] += 1
                last_examined = row["outcome_id"]
                examined_rows.append(row)

                if not row["condition_id"]:
                    counts["no_condition_id"] += 1
                    continue

                market = found.get(row["condition_id"])
                if market is None:
                    counts["not_at_venue"] += 1
                    continue

                # The SHIPPED rule, given the market's own event title. For this
                # cohort `fm.name` IS the event title: these rows are the parent
                # anchor of a game-level event, whose name is `event.title`, and
                # the collapse is precisely `derived == event_title`. Verified on
                # production 2026-09-01 across the tennis/football/baseball
                # sample — every `market_name` was the venue event's title.
                new_name = _leg_label(market, row["market_name"])
                if not new_name or new_name == row["outcome_name"]:
                    # The venue's own answer still collapses onto the market
                    # name, or is a bare Yes/No that names no side either.
                    # Counted, not silent: a drain that "found nothing to do"
                    # must say how many times.
                    counts["unchanged"] += 1
                    continue

                planned.append({**row, "new_name": new_name})

            await asyncio.sleep(VENUE_PAUSE)
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001 — cleanup must not mask the real result
            logger.warning("repair_polymarket_leg_label: venue client close failed")

    # ---- collision refusal ----------------------------------------------
    # One market can carry two collapsed legs (measured: one does). If two legs
    # of the SAME market would take the same label, writing both replaces one
    # unreadable card with a card that prints the same side twice. Refuse the
    # pair and count it; a human can look.
    by_market: dict[int, list[dict[str, Any]]] = {}
    for p in planned:
        by_market.setdefault(p["market_id"], []).append(p)
    writable: list[dict[str, Any]] = []
    for market_id, group in by_market.items():
        names = [g["new_name"] for g in group]
        if len(names) != len(set(names)):
            counts["refused_collision"] += len(group)
            logger.warning(
                "repair_polymarket_leg_label: market %s would take the label %r "
                "on %d legs; refusing the whole group",
                market_id,
                names[0],
                len(group),
            )
            continue
        writable.extend(group)

    for p in writable[:20]:
        samples.append(
            {
                "outcome_id": p["outcome_id"],
                "market_id": p["market_id"],
                "category": p["category"],
                "from": p["outcome_name"],
                "to": p["new_name"],
            }
        )

    # ---- the write -------------------------------------------------------
    write_terminal: Optional[str] = None
    write_reason: Optional[str] = None
    if apply and writable:
        # ONE statement, compare-and-set on the exact name each row was selected
        # on, RETURNING the ids that actually landed. A row the ordinary poller
        # re-ingested between the SELECT and here fails its own compare and is
        # counted `raced` — never clobbered.
        #
        # It names ONE column. `last_updated` is a poller touch-stamp that
        # `app/routes/playoffs.py` reads as liveness (#2024); a repair that
        # bumped it would forge a venue observation that never happened.
        values = ", ".join(
            f"(:id{i}::bigint, :old{i}::text, :new{i}::text)" for i in range(len(writable))
        )
        params: dict[str, Any] = {}
        for i, p in enumerate(writable):
            params[f"id{i}"] = p["outcome_id"]
            params[f"old{i}"] = p["outcome_name"]
            params[f"new{i}"] = p["new_name"]

        write_sql = f"""
            UPDATE futures_outcomes fo
               SET name = v.new_name
              FROM (VALUES {values}) AS v(id, old_name, new_name)
             WHERE fo.id = v.id
               AND fo.name IS NOT DISTINCT FROM v.old_name
         RETURNING fo.id
        """
        landed: set[int] = set()
        try:
            result = await _bounded_statement(
                session,
                timeout_literal=f"'{int(WRITE_BUDGET_SECONDS * 1000)}ms'",
                server_budget_s=WRITE_BUDGET_SECONDS,
                sql=write_sql,
                params=params,
            )
            # Read BEFORE the commit — see COMMIT_BUDGET_SECONDS.
            landed = {int(r[0]) for r in result.fetchall()}
            await _bounded_statement(
                session,
                timeout_literal=f"'{int(COMMIT_BUDGET_SECONDS * 1000)}ms'",
                server_budget_s=COMMIT_BUDGET_SECONDS,
                sql="SELECT 1",
                commit=True,
            )
        except ClientDeadlineExceeded as exc:
            await _safe_rollback(session)
            write_terminal = "paused_pool_timeout"
            write_reason = f"the write never reached the database: {exc}"
            landed = set()
        except Exception as exc:  # noqa: BLE001 — a lock on these very rows
            await _safe_rollback(session)
            write_terminal = "paused_write_timeout"
            write_reason = (
                f"the update did not land inside its budget: "
                f"{type(exc).__name__}: {exc}"
            )
            landed = set()

        if write_terminal is None:
            # `raced` is only meaningful when the statement RAN. A write that
            # never landed leaves every leg unwritten for one shared reason, and
            # counting those as `raced` would tell the operator 120 concurrent
            # re-ingests had happened.
            for p in writable:
                if p["outcome_id"] in landed:
                    counts["relabelled"] += 1
                    # The only audit trail this table can carry:
                    # `futures_outcomes` has no metadata column, so the old
                    # label survives nowhere else.
                    logger.info(
                        "repair_polymarket_leg_label: outcome %s (market %s) %r -> %r",
                        p["outcome_id"],
                        p["market_id"],
                        p["outcome_name"],
                        p["new_name"],
                    )
                else:
                    counts["raced"] += 1
    else:
        # A dry run plans exactly what an apply would write, and says so with a
        # count rather than an empty `relabelled` that reads like "nothing to do".
        counts["relabelled"] = 0

    # ---- the cursor ------------------------------------------------------
    if write_terminal:
        # The page was examined but its write did not land. Retry the PAGE.
        next_cursor = incoming_cursor
        terminal = write_terminal
        scan_exhausted = False
    elif stopped_before is not None:
        # The cursor is EXCLUSIVE (`fo.id > :after_id`), so it names the last leg
        # actually examined and the next call resumes at `stopped_before`. When
        # the very first batch failed, nothing was examined and the cursor the
        # operator handed in is returned unchanged — a retry repeats the page
        # rather than skipping the legs the venue refused to answer for.
        resume_after = last_examined if last_examined is not None else (after_id or None)
        next_cursor = {"after_id": int(resume_after)} if resume_after else incoming_cursor
        terminal = "paused_venue" if venue_reason else "paused_deadline"
        scan_exhausted = False
    else:
        next_cursor = {"after_id": int(last_examined)} if last_examined else incoming_cursor
        terminal = "ok"
        # A short page means the population ran out under this cursor. It does
        # NOT mean the cohort is empty — re-run `census` for that.
        scan_exhausted = len(rows) < cap

    # ---- the terminal count ---------------------------------------------
    remaining: Optional[int] = None
    remaining_measured = False
    spent = time.monotonic() - started
    # The SERVER bound, derived so that the CLIENT bound wrapped around it still
    # fits under the wall. `client_db_budget_seconds(0)` is the pool slack the
    # helper adds; subtracting it here is what stops the count from overshooting
    # the wall by exactly that slack — the arithmetic the reserve exists to make
    # auditable rather than approximately right.
    count_budget = (
        ROUTER_WALL_SECONDS
        - spent
        - POST_LOOP_NON_COUNT_RESERVE_SECONDS
        - client_db_budget_seconds(0.0)
    )
    if count_budget >= REMAINING_COUNT_MIN_BUDGET_SECONDS:
        count_sql = f"""
            SELECT count(*)
              FROM futures_markets fm
              JOIN futures_outcomes fo
                ON fo.market_id = fm.id
               AND {COLLAPSED_LEG_PREDICATE}
             WHERE fm.source = 'polymarket'
               AND fm.status = 'open'
               AND (:sport::text IS NULL OR fm.llm_sport_category = :sport::text)
        """
        try:
            result = await _bounded_statement(
                session,
                timeout_literal=f"'{int(count_budget * 1000)}ms'",
                server_budget_s=count_budget,
                sql=count_sql,
                params={"sport": sport},
            )
            remaining = int(result.scalar_one())
            remaining_measured = True
        except Exception:  # noqa: BLE001 — degradable: unmeasured, never zero
            await _safe_rollback(session)
            remaining = None
            remaining_measured = False

    return {
        "repair": "polymarket-leg-label",
        "applied": bool(apply),
        "counts": counts,
        "planned": len(writable),
        "samples": samples,
        "remaining_legs": remaining,
        "remaining_legs_measured": remaining_measured,
        "scan_exhausted": scan_exhausted,
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        "terminal": terminal,
        "reason": write_reason or venue_reason,
        "cap": cap,
        "sport": sport,
        "elapsed_s": round(time.monotonic() - started, 2),
    }
