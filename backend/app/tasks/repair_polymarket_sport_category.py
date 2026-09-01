"""Polymarket sport-category recovery — Q495, the drain half of Q493.

PILLAR: MATCHING. SHIP: the US Open matches still filed under Table Tennis —
a category with no tile — move to Tennis, instead of waiting years for a
re-ingest that never arrives.

WHY THIS RAIL EXISTS
====================

Q493 (`d297f948`, merged `3ab15b20`, CERT-663) fixed the CLASSIFIER: Polymarket
tags Setka/TT-Cup events "Table Tennis" and real ATP/WTA events "Tennis", and
neither answer was being read. That fix is correct and was graded correct on
production — of the 44 rows the first `:15` beat after deploy re-ingested,
**44 of 44** migrated `table_tennis` -> `tennis`, and the Setka control event
`945534` held at `table_tennis`. No row the fix ran on stayed wrong.

**But a classifier only repairs a row the poller re-fetches, and the poller is
not reaching this population.** Measured on production at `3ab15b20`,
2026-09-01 08:25Z:

  * 283 of the 344 rows on the Q493 check predicate were still `table_tennis`.
    **Not one** had been touched by the beat that fixed the other 44.
  * **177 of those 283 (63%) had not been re-ingested since 2026-08-28** — four
    days.
  * Across the whole open `table_tennis` bucket (12,826 rows) only **866** were
    touched that day; 3,008 were 6d stale, 2,173 5d, 2,190 4d. Ingest reaches
    roughly **7%/day** of the bucket.
  * Every row on the predicate has a **PAST `commence_time` and
    `status='open'`** — the venue is not returning them in discovery, so the
    hourly upsert never sees them. Gotcha #33's shape (Kalshi settled markets
    stay `open`) on the Polymarket side.

Board item 23 claimed "NO BACKFILL NEEDED" on the strength of a single observed
row repair. That row was inside the ~7%/day slice the beat reaches. The claim
does not generalise, and this rail is the correction.

WHAT IT DOES — AND THE ONE RULE IT REFUSES TO INVENT
====================================================

It does **not** re-derive the sport from the stored row. The tags are not
persisted (`market_metadata` carries `event_title`, `matchup_title`,
`polymarket_event_id` and the shape block — no tags), so a DB-only rule would
have to guess the sport from the NAME. That would be a SECOND classifier, free
to drift from the shipped one, and reconciling two classifiers is the failure
this codebase already pays for elsewhere.

Instead it re-asks the venue and runs **the shipped cascade, unmodified**:

    category, llm = _tags_to_category(event.tags)
    group_names   = [title] + [m.question for m in event.markets]
    category, llm, arm = resolve_event_category(category, llm, title, group_names)

— byte-for-byte the sequence `_process_event_batch` runs at ingest
(`app/tasks/polymarket.py`). If this rail and the poller ever disagree, that is
a bug in one of them, not a policy difference. **The 44/44 beat migration is the
oracle this rail must reproduce**, and `tests/test_repair_polymarket_sport_category_q495.py`
pins exactly that: the real US Open specimen must come back `tennis`, the real
Setka specimen must come back `table_tennis`.

POPULATION, AND WHY SETKA IS THE CONTROL RATHER THAN AN EXCLUSION
=================================================================

The population is open Polymarket rows currently filed `table_tennis` — the
bug's own output. Setka/TT-Cup rows are **inside** that population and are not
excluded by a predicate: they are re-asked like everything else and the venue's
`Table Tennis` tag keeps them where they are. An exclusion list would have to be
maintained and could go stale; a control that rides the same code path cannot.
`counts["unchanged"]` rising on Setka events is the rail proving it is safe, so
a run that changes *everything* is as suspect as one that changes nothing.

WRITES, AND WHAT IS NEVER WRITTEN
=================================

Writes `llm_sport_category` (and `category` when the cascade promotes the event
to `championship`) on every row of the event, via Core UPDATE — never ORM
attribute assignment (gotchas #4/#5). Touches no prices, no outcomes, no
`is_winner`, no resolution fields.

Nothing is written when the venue does not answer clearly:

  * fetch 429/5xx/timeout -> ``indeterminate`` — counted, never written. A
    transient venue failure must not be recorded as a category verdict (#36).
  * fetch 404 -> ``not_at_venue`` — counted, never written.
  * the cascade returns ``None``/``"other"`` -> ``refused_other`` — counted,
    never written. Same guard the poller carries: never overwrite a real value
    with the "other" default.

An empty result is a response SHAPE, not an absence (gotcha #53): a pass that
examined events and wrote nothing says so in a named terminal rather than
leaving four zeros for a reader to interpret.

ORDERING — AND WHAT IT STARTS ON
================================

Newest `commence_time` first, deliberately, and gotcha #41 is the reason it is
spelled out rather than assumed. #41 warns that newest-first starves the old
tail. It does here too, and that is the accepted trade:

  * the ship is user-visible — the matches a reader opens today are the newest
    ones, and they are the rows on a category page with no tile;
  * the population is **not expiring**. Polymarket EVENT data is durable (unlike
    Kalshi MARKET data, `app/utils/kalshi_retention.py`), so the tail cannot rot
    while it waits — the argument that forces oldest-first-within-a-floor on the
    Kalshi rails does not apply;
  * the tail is never silent: ``remaining_events`` is reported on every call and
    the operator pages with ``next_cursor`` until ``scan_exhausted`` comes back
    true. NOT until ``remaining_events`` reaches zero — it counts the suspect
    category, which legitimately contains the control events, so it has a
    positive floor and zero is unreachable.

Paging is a KEYSET (``after_date`` + ``after_id``), never an offset: this
repair removes rows from its own population, so an offset would skip exactly as
many untouched rows as the last page fixed.

**The query parameter is ``after_date``.** Not ``after_commence`` — the
dispatcher does not declare that name, FastAPI drops an unknown query param
SILENTLY, and the resulting call re-reads page one forever while looking busy.
``tests/test_repair_polymarket_sport_category_q496.py`` fails the build if any
prose in ``routes/admin_repairs.py`` names a param the dispatcher cannot pass.

Q496 CORRECTIONS TO THE PAGER AND THE BUDGET
============================================

Three defects the CERT-664 follow-ups named, and one the fix for the third
exposed. None changes what the rail decides; all three change whether an
operator can finish a drain.

1. **The request budget could not fit under the router wall.** A synchronous
   ``POST /api/admin/repairs/...`` has 30s, after which Heroku returns H12 with
   **no body** — so the operator loses ``next_cursor`` and the drain loses its
   place. The old numbers were a 55s loop deadline, a 25s per-fetch timeout and
   a 60-event cap whose *sleep alone* was 21s: the DOCUMENTED DEFAULT was the
   case most likely to fail. Now derived from the wall and asserted by
   ``budget_headroom_seconds()``, which a guard requires to stay positive. The
   cap is sized on a MEASURED figure rather than a guess: the target query below
   runs in **179ms** on production (``EXPLAIN ANALYZE``, first page, no cursor,
   2026-09-01), so the database is not the cost and the budget belongs almost
   entirely to the venue calls.

2. **``terminal="complete"`` was unreachable.** It keyed on
   ``remaining_events == 0``, but ``remaining_events`` counts the suspect
   CATEGORY — which legitimately contains the Setka control. A fully drained
   population therefore reported ``no_work``, i.e. "your cursor is wrong",
   rather than "you are finished". Exhaustion is now proven by the pager
   (``scan_exhausted``: a short page, fully consumed) and ``remaining_events``
   is labelled as the floor it is.

3. **The NULL-``commence_time`` region was unresumable.** ``NULLS LAST`` puts it
   at the very end; a cursor there carries ``after_date: None``; the keyset
   gate required a truthy ``after_date``, so it never activated and the next
   call silently restarted at page one. The gate is now ``after_id is not
   None``, with an explicit second form for the NULL region.

4. **(Found while fixing 3.)** The keyset filtered the raw market rows while
   the cursor names two AGGREGATES over them. An event whose markets straddle
   the boundary would lose some rows, recompute a different
   ``max(commence_time)``, and move in the ordering between pages — a keyset
   that both repeats and skips. The aggregation now happens first and the
   cursor filters its output, so the filtered quantity is the quantity the
   cursor names.

CERT-666 CORRECTIONS — THE DRAIN COULD STILL SAY "FINISHED" WHEN IT WAS NOT
===========================================================================

Q496 made the end state REACHABLE. CERT-666 found it was also reachable when it
was FALSE, which is the worse half of the same bug.

1. **A transient venue failure was advanced past and reported as complete.**
   The cursor was assigned BEFORE the fetch, so a 429/5xx/timeout on the last
   short page left the event unchanged in the suspect category, moved the cursor
   PAST it, and — because exhaustion was computed from the page length alone —
   returned ``scan_exhausted=true`` and a terminal reading "this was the LAST
   page, so the drain is finished". The operator would stop with a user-visible
   match still hidden from Tennis, and the emitted cursor guaranteed nothing
   would ever look at it again. **A transient failure is not a verdict.**

   Now: the cursor advances only past RESOLVED events (``ok`` or a 404
   ``not_at_venue``), the scan STOPS at the first unresolved one, and exhaustion
   additionally requires ``indeterminate == 0`` so completion is impossible
   while any retryable result remains. The state has its own terminal,
   ``paused_unresolved``, and its own field, ``stopped_at_unresolved``.

2. **The advertised headroom omitted everything after the last fetch.** The
   worst case was reported as ``DEADLINE + FETCH_TIMEOUT + VENUE_PAUSE``, but
   the last event still classifies, UPDATEs and commits after that fetch, and
   the ``remaining_events`` count then ran with NO statement timeout at all —
   the one genuinely unbounded statement in the request. Now
   ``POST_LOOP_RESERVE_SECONDS`` is part of the budget, the deadline and cap came
   down to keep the headroom positive, and the count is armed with the time that
   ACTUALLY remains and reports itself unmeasured rather than dying.

CERT-667 CORRECTIONS — THE BUDGET WAS END-TO-END EXCEPT WHERE IT TOUCHED THE DB
===============================================================================

Q496 derived every constant from the router wall and CERT-666 extended the
reserve past the last fetch. Both bounded the VENUE. Neither bounded the
DATABASE, and two statements sat outside the budget they were described by.
Neither disproves the shipped rail — CERT-667 granted its token — but each is a
way for an attended drain to lose its place, which is the one failure this rail
exists to prevent.

1. **The page SELECT ran before every deadline the rail checks.** It is the first
   statement of the request; ``DEADLINE_SECONDS`` is not evaluated until it
   returns, so a lock or a bad plan held the request to the wall with nothing
   able to interrupt it. Now armed with ``TARGET_SELECT_BUDGET_SECONDS``, and a
   timeout returns the named terminal ``paused_target_timeout`` carrying the
   operator's OWN cursor — not a bare 500, which cannot be told from a broken
   rail and carries no cursor at all.

2. **The compare-and-set UPDATE was unbounded.** ``POST_LOOP_RESERVE_SECONDS``
   said it covered "the last event's write and commit"; nothing made the write
   honour that. The UPDATE takes a row lock on ``futures_markets``, which the
   ordinary poller also writes, so a contended row could block past the wall.
   Now armed with ``WRITE_BUDGET_SECONDS``, sized to fit inside that reserve.

3. **(Found while fixing 2.)** The cursor still crossed unfinished work — one
   statement further along than CERT-666 found it. CERT-666 moved the advance
   from before the fetch to after it; the WRITE was downstream of the advance, so
   a failed UPDATE left the event mis-filed with the cursor already past it and
   the terminal reading ``changed``. The advance now happens per-outcome, after
   the event is genuinely finished, and a failed write has its own count
   (``write_failed``), its own field (``stopped_at_write_timeout``) and its own
   terminal (``paused_write_timeout``) ranked above every success arm.

4. **The census leaked its statement timeout onto the pooled connection.** A
   plain ``SET`` inside a transaction that ``get_db_rw`` then COMMITS is a
   property of the connection, not of the request; the connection returns to a
   20-slot pool carrying a 12s ``statement_timeout`` that later requests inherit
   invisibly. Now ``SET LOCAL``. Note which path leaked: the HEALTHY one — a
   census that timed out left an aborted transaction whose commit degraded to a
   rollback and took the ``SET`` with it.

CERT-670 (P1) then found the floor under all of that. Every bound above is a
PostgreSQL ``statement_timeout``, and PostgreSQL cannot enforce a bound it has
not been sent — but the statement that SENDS it is also the statement that
acquires the pooled connection, lazily, and the engine leaves SQLAlchemy's
``pool_timeout`` at its 30s default: **exactly ``ROUTER_WALL_SECONDS``**. So
under pool saturation the arming statement could burn the entire wall before any
timeout existed, at all three sites, and the operator got back the H12 with no
body and no cursor that this rail exists to prevent. Q497 had made the budget
reach the database; it reached the database only once the database was already
reachable. Every unit — checkout, ``SET LOCAL``, statement, commit — is now
wrapped in a CLIENT-side deadline too, because a client-side deadline is the only
one that can fire while the server is unreachable. **A bound you can only install
over the channel you are trying to bound is not yet a bound.**

ATTENDED ONLY: never wire this to a beat. It is a drain with an end state, not
a standing job — when ``scan_exhausted`` comes back true the poller's own fixed
classifier keeps new rows correct.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from sqlalchemy import text

logger = logging.getLogger(__name__)

GAMMA = "https://gamma-api.polymarket.com"

#: The Heroku router's hard wall on a synchronous request. Not ours to change,
#: and not a timeout we get to observe: past this the router returns **H12 and
#: the operator gets no body at all** — no counts, and crucially no
#: ``next_cursor``, so an attended drain loses its place rather than pausing.
#: Every budget below is derived from this number so the derivation is auditable
#: rather than three constants that happen to look reasonable.
ROUTER_WALL_SECONDS = 30

#: Per-venue-call timeout. Q496: this was 25s, which alone could carry a single
#: request past the wall no matter what the loop deadline said.
FETCH_TIMEOUT_SECONDS = 8

#: The point past which no NEW event is started. Checked at the top of the loop,
#: so the true worst case is this plus one whole fetch plus one pause — see
#: ``budget_headroom_seconds()``, which is asserted by a guard rather than left
#: as arithmetic in a comment.
#:
#: CERT-666 (P2) lowered this from 20. The loop deadline was being treated as if
#: the response were free after it, but the LAST event still classifies, UPDATEs
#: and commits after its fetch, and the terminal count then runs — see
#: ``POST_LOOP_RESERVE_SECONDS``.
DEADLINE_SECONDS = 15

#: Pause between venue calls. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35

#: CERT-666 (P2): time reserved for everything that happens AFTER the loop's last
#: fetch returns, all of which was previously unbudgeted and some of which was
#: unbounded:
#:
#:   * the last event's classify + Core UPDATE + ``commit()``,
#:   * the ``remaining_events`` terminal count — a ``count(DISTINCT ...)`` that
#:     carried NO statement timeout at all, so a lock or a bad plan could hold
#:     the request past the wall on its own,
#:   * response serialization and the request dependency's own commit, which
#:     runs after the handler has already returned.
#:
#: The deadline bounds when the rail stops STARTING work; this bounds the work it
#: has already committed to finishing. ``repair()`` arms a Postgres
#: ``statement_timeout`` from the budget genuinely remaining at that moment, so
#: the count cannot outlive its reservation even if this estimate is wrong.
POST_LOOP_RESERVE_SECONDS = 4.0

#: The slice of ``POST_LOOP_RESERVE_SECONDS`` that is NOT the terminal count: the
#: last event's write and commit, response serialization, and the request
#: dependency's own commit — which runs after the handler has returned and so
#: cannot be observed from inside it. The count is armed with whatever is left of
#: the wall once this is set aside, which is why an over-running loop shortens
#: the count's timeout instead of borrowing against work that still has to run.
#:
#: CERT-670 (P1) raised this from 1.5. The thing charged to this reserve is no
#: longer ``WRITE_BUDGET_SECONDS`` but ``client_db_budget_seconds(WRITE_BUDGET_
#: SECONDS)`` — the write's server bound PLUS the client-side slack that now
#: wraps it — and at 1.5 that derived number left nothing at all for the
#: serialization and dependency commit this reserve also names. Widening the
#: reserve rather than shrinking the write budget keeps the write's own bound at
#: the value CERT-667 graded, and costs only the terminal count, which is
#: explicitly degradable (it reports itself unmeasured; it never reports zero).
#:
#: And the reserve holds the write's CLEANUP too, not just the write. A starved
#: write is followed by a bounded rollback, and at 2.0 the pair came to exactly
#: the reserve — nothing left for the serialization and dependency commit this
#: same reserve names. "The failure path costs more than the success path" is the
#: easy thing to forget when sizing a budget from the happy case.
POST_LOOP_NON_COUNT_RESERVE_SECONDS = 2.5

#: CERT-667 (`Q496-END-TO-END-DB-DEADLINE`): bound on the page SELECT, which was
#: the FIRST unbounded statement in the request and ran before any deadline the
#: rail checks. Measured at 179ms on production; 10s is ~56x that.
#:
#: It does NOT widen the worst case, and the reason is worth stating because it
#: is the whole argument for the number: ``started`` is captured BEFORE this
#: query, so its time is already inside ``DEADLINE_SECONDS``' window — a slow
#: SELECT does not add to the total, it just leaves the loop less room and the
#: first deadline check stops it. That holds only while this stays at or under
#: ``DEADLINE_SECONDS``, so a guard asserts exactly that rather than trusting the
#: two numbers to be edited together.
TARGET_SELECT_BUDGET_SECONDS = 10.0

#: CERT-667 (`Q496-END-TO-END-DB-DEADLINE`): bound on each compare-and-set UPDATE.
#:
#: The write was the other half of the reserve the rail computed but never
#: enforced. ``POST_LOOP_NON_COUNT_RESERVE_SECONDS`` already *claimed* to cover
#: "the last event's write and commit"; nothing made the write honour it, so a
#: row lock on ``futures_markets`` could hold the request past the wall and cost
#: the operator the H12-with-no-body — the exact failure the budget exists to
#: prevent, arrived at through the one statement the budget did not bound.
#:
#: Sized to fit INSIDE that reserve (a guard asserts it), leaving the remainder
#: for response serialization and the request dependency's own commit. A
#: mid-loop write costs the loop its own time and the next deadline check sees
#: it; only the LAST write is charged to the reserve, which is why one constant
#: covers both cases.
WRITE_BUDGET_SECONDS = 1.0

#: Events touched per apply call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
#:
#: Q496 lowered this from 60. At 60 the *sleep alone* was 60 x 0.35 = 21s before
#: a single byte of HTTP or DB time, against a 30s router wall — so the
#: DOCUMENTED DEFAULT was the case most likely to H12, and the operator would
#: have read that as the rail being broken.
#:
#: Sized on MEASURED numbers, not a guess. The target query was run against
#: production on 2026-09-01 (`EXPLAIN ANALYZE`, first page, no cursor): **179ms**
#: for 25 rows, so the DB is not the cost — the venue calls are.
#:
#: CERT-666 (P2) lowered this again, from 20 to 15, because reserving the
#: post-loop work took ``DEADLINE_SECONDS`` down to 15. At ~0.75s per event (a
#: Gamma fetch plus VENUE_PAUSE) a 15-event page lands near 11.3s, inside the 15s
#: deadline with margin — so a full page still normally COMPLETES and
#: ``stopped_before`` stays the exception it is meant to be. Had the cap stayed
#: at 20 the documented default would have run to ~15s and hit the deadline
#: routinely, which is safe (partial answer WITH a cursor) but would have made
#: the exceptional state the normal one.
APPLY_EVENT_CAP = 15

#: The category this rail drains. Named once so the census and the repair
#: cannot disagree about their own population.
SUSPECT_CATEGORY = "table_tennis"

#: Statement timeout for the census, which runs TWO queries under ONE router
#: wall. Q496: this was ``'25s'``, so its own permitted worst case was 50s
#: against a 30s wall — the census could H12 while still believing its
#: ``measured: false`` path had it covered. It cannot: an H12 returns no body,
#: so the honest "we could not look" answer never reaches the operator and the
#: rail's whole gotcha-#54 argument evaporates at exactly the moment it matters.
#: Both queries measured **94ms and 179ms** on production 2026-09-01, so 12s is
#: ~60x the observed cost and still leaves 6s of the wall for everything else.
CENSUS_STATEMENT_TIMEOUT_SECONDS = 12

#: CERT-670 (P1) — A SERVER-SIDE BOUND DOES NOT EXIST UNTIL A CONNECTION DOES.
#:
#: Every bound above is a PostgreSQL ``statement_timeout``, and PostgreSQL cannot
#: enforce a bound it has not been sent. ``AsyncSession`` acquires its connection
#: LAZILY, on the first ``execute`` of a transaction — which is the very
#: ``SET LOCAL`` that arms the bound. So the arming statement itself runs
#: unbounded, and what it waits on is SQLAlchemy's pool: ``app/services/
#: database.py`` builds the engine with ``pool_size=10, max_overflow=10`` and
#: never sets ``pool_timeout``, leaving SQLAlchemy's default of **30 seconds —
#: exactly ``ROUTER_WALL_SECONDS``**. Under pool saturation the first statement of
#: a unit can therefore consume the whole wall before any timeout exists, and the
#: operator gets the H12 with no body and no cursor that this entire rail exists
#: to prevent. Q497 bounded the venue and the database and left the CONNECTION
#: unbounded: the budget reached PostgreSQL, but only once PostgreSQL was already
#: reachable.
#:
#: The fix is a CLIENT-side deadline around the whole unit — checkout, ``SET
#: LOCAL``, statement, commit — because only a client-side deadline can fire
#: while the server is still unreachable.
#:
#: This is SLACK, not a second budget. It sits just OUTSIDE each server bound so
#: that in the normal case PostgreSQL's own ``statement_timeout`` wins the race
#: and the rail takes its precise, already-guarded server-timeout path; the
#: client bound is the backstop that fires only when the server never received
#: the statement at all. What it has to cover is a healthy checkout plus two
#: round trips — milliseconds — so it is small on purpose. A large value here
#: would start swallowing server timeouts and report pool starvation for what is
#: really a slow query.
#:
#: Deliberately NOT fixed by lowering the engine's ``pool_timeout``: that is a
#: global property of every route in the app, and this is a hardening queue on
#: one attended rail. A rail may bound its own use of a shared resource; it does
#: not get to re-tune the resource for everyone else.
POOL_ACQUIRE_SLACK_SECONDS = 0.5

#: Bound on the CLEANUP rollback after a unit has already failed. A rollback is
#: itself a statement on the same connection, so it can block for the same reason
#: the statement did — and a cleanup that hangs costs the operator exactly what
#: the failure path was written to preserve: the response, and the cursor in it.
ROLLBACK_BUDGET_SECONDS = 0.5


class ClientDeadlineExceeded(Exception):
    """A database unit did not finish inside the rail's CLIENT-side bound.

    Distinct from a PostgreSQL ``statement_timeout``, and the distinction is
    operational rather than cosmetic. A server timeout means the database took
    the statement and could not finish it — a lock, or a bad plan — and retrying
    immediately is reasonable. This means the statement did not get that far:
    almost always every pooled connection was checked out, so retrying
    immediately just queues behind the same saturation.

    Raised in place of ``asyncio.TimeoutError`` on purpose. ``asyncio.Timeout
    Error`` is the builtin ``TimeoutError`` on 3.11+, which is an ``OSError``
    subclass a driver could plausibly raise for something else entirely; a rail
    that branches on it would be guessing.
    """


def client_db_budget_seconds(server_budget_s: float) -> float:
    """The client-side bound that must sit OUTSIDE a server-side statement bound.

    Expressed as a function so the guards can assert the DERIVED number fits the
    reserve it is charged to. Asserting the server bound fits and leaving the
    slack unaccounted is how the original bound came to be described but not
    enforced — the same class of gap twice over.
    """
    return server_budget_s + POOL_ACQUIRE_SLACK_SECONDS


async def _bounded_statement(
    session,
    *,
    timeout_literal: str,
    server_budget_s: float,
    sql: str,
    params: Optional[dict[str, Any]] = None,
    commit: bool = False,
):
    """Run one statement under a server bound AND a client bound.

    ``timeout_literal`` is whatever follows ``SET LOCAL statement_timeout = ``.
    It is passed in rather than derived because the census states its bound in
    seconds (``'12s'``) and the pager in milliseconds, and guards pin those exact
    spellings — a helper that quietly normalised them would rewrite what those
    guards read while still passing.

    Raises ``ClientDeadlineExceeded`` when the client bound fires. Every call
    site handles that separately from a server timeout, because the two mean
    different things to the operator reading the terminal.
    """

    async def _unit():
        # The pool checkout happens HERE, on the first execute of the
        # transaction, BEFORE PostgreSQL can be told about any bound. That is
        # the whole reason the wait_for has to wrap the SET and not just the
        # statement the SET is arming.
        await session.execute(text(f"SET LOCAL statement_timeout = {timeout_literal}"))
        result = await session.execute(text(sql), params or {})
        if commit:
            # Inside the bound deliberately: a commit runs on the same
            # connection and can block on the very lock the statement took.
            await session.commit()
        return result

    try:
        return await asyncio.wait_for(
            _unit(), timeout=client_db_budget_seconds(server_budget_s)
        )
    except asyncio.TimeoutError as exc:
        raise ClientDeadlineExceeded(
            f"no answer inside the {client_db_budget_seconds(server_budget_s)}s "
            f"client bound around a {server_budget_s}s server bound"
        ) from exc


async def _safe_rollback(session) -> None:
    """Roll back without letting the cleanup cost the operator the response.

    Bounded for the reason in ``ROLLBACK_BUDGET_SECONDS``, and if the bounded
    rollback does not land the connection is INVALIDATED rather than left in an
    unknown state. That second step is load-bearing: ``get_db_rw`` issues its own
    ``commit()`` after this handler returns, so a session still holding a wedged
    connection would turn a carefully built paused response — cursor and all —
    into the bare 500 the response existed to replace. Invalidating discards the
    connection instead of negotiating with it, which leaves the session able to
    begin a fresh, empty transaction that commits without touching the pool.
    """
    try:
        await asyncio.wait_for(session.rollback(), timeout=ROLLBACK_BUDGET_SECONDS)
        return
    except Exception:  # noqa: BLE001 — cleanup must never mask the real failure
        logger.warning(
            "repair_polymarket_sport_category: rollback did not land inside "
            "%.2fs; invalidating the connection so the operator still gets a "
            "response with a cursor",
            ROLLBACK_BUDGET_SECONDS,
        )
    try:
        await session.invalidate()
    except Exception:  # noqa: BLE001 — there is nothing further to try
        logger.warning(
            "repair_polymarket_sport_category: could not invalidate the "
            "connection after a failed rollback"
        )


def _paused_before_examining(
    *,
    incoming_cursor: Optional[dict[str, Any]],
    cap: int,
    started: float,
    terminal: str,
    stopped_at_pool_timeout: Optional[str],
    reason: str,
) -> dict[str, Any]:
    """The response for a page that died before it examined anything.

    Shared by the two ways the page SELECT can fail. CERT-670 noted the single
    early return already duplicated the response shape instead of sharing a
    builder, and flagged it as a drift risk if fields were added later; adding a
    second such arm is exactly that "later", so the builder arrives with it.

    Every count is zero and ``next_cursor`` is the cursor the operator HANDED IN,
    unchanged. Nothing was examined, so nothing may advance — re-running with it
    repeats the page rather than skipping it, which is the whole point of
    answering at all instead of letting the router return H12 with no body.
    """
    return {
        "repair": "polymarket-sport-category",
        "applied": False,
        "counts": {
            "events_examined": 0,
            "changed": 0,
            "unchanged": 0,
            "refused_other": 0,
            "not_at_venue": 0,
            "indeterminate": 0,
            "write_failed": 0,
            "markets_written": 0,
        },
        "changed_to": {},
        "samples": [],
        "remaining_events": None,
        "remaining_events_measured": False,
        "scan_exhausted": False,
        "next_cursor": incoming_cursor,
        "stopped_before": None,
        "stopped_at_unresolved": None,
        "stopped_at_write_timeout": None,
        "stopped_at_pool_timeout": stopped_at_pool_timeout,
        "terminal": terminal,
        "reason": reason,
        "cap": cap,
        "elapsed_s": round(time.monotonic() - started, 2),
    }


def budget_headroom_seconds() -> float:
    """Seconds left under the router wall in the rail's WORST case.

    The deadline is checked at the top of the loop, so after it passes the rail
    may still start one fetch and one pause. And after THAT fetch returns the
    rail still has real work to do — the last event's write and commit, the
    terminal count, serialization, the dependency's commit. So the worst case is
    ``DEADLINE + FETCH_TIMEOUT + VENUE_PAUSE + POST_LOOP_RESERVE``, not
    ``DEADLINE``, and not the three-constant subtotal this function returned
    before CERT-666 (P2) — that version reported 1.65s of headroom the rail did
    not actually have, because it stopped counting at the last fetch.

    Expressed as a function so a guard can assert it stays positive, rather than
    as a comment that goes stale the first time someone raises one of the four
    numbers.

    Positive means an over-running call returns a partial answer WITH its
    cursor. Negative means it returns H12 with no body, and an attended drain
    silently loses its place.
    """
    return ROUTER_WALL_SECONDS - (
        DEADLINE_SECONDS + FETCH_TIMEOUT_SECONDS + VENUE_PAUSE + POST_LOOP_RESERVE_SECONDS
    )


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------


async def census(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """Size the mis-filed population and how stale it is. Writes nothing.

    `apply` is accepted and ignored so the census can never be turned into a
    write by a stray query parameter.
    """
    started = time.monotonic()
    try:
        # CERT-667 (`Q496-CENSUS-SET-LOCAL`) — THIS USED TO BE A PLAIN `SET`, AND A
        # PLAIN `SET` OUTLIVES THE REQUEST THAT ISSUED IT.
        #
        # `get_db_rw` COMMITS the session when the handler returns, and a
        # session-level `SET` inside a committed transaction is not undone — it is
        # a property of the CONNECTION from then on. The connection then goes back
        # to a pool (`pool_size=10, max_overflow=10`), so every later request that
        # checks it out silently inherits a 12s `statement_timeout` it never asked
        # for and cannot see. A census is a diagnostic; it must not re-arm the rest
        # of the dyno.
        #
        # It leaks on the SUCCESS path specifically: on a timeout the transaction
        # is already aborted, so the commit degrades to a rollback and takes the
        # `SET` with it. The healthy run is the one that poisons the pool, which is
        # why nothing ever attributed a stray cancellation to this line.
        #
        # `SET LOCAL` is scoped to the transaction and is reset at COMMIT or
        # ROLLBACK either way. It is valid here because the session autobegins a
        # real transaction on this very statement — the engine is not in
        # AUTOCOMMIT, which matters: `SET LOCAL` outside a transaction block is a
        # WARNING and a NO-OP, i.e. it would remove the bound rather than scope it.
        #
        # CERT-670 (P1): and both queries now run through `_bounded_statement`,
        # so the `SET LOCAL` above cannot itself wait out the router wall
        # acquiring the pooled connection it needs before PostgreSQL can be told
        # anything. A census that H12s is the same silent failure as a census
        # that returns a zero — worse, in fact, because `measured: false` never
        # reaches the operator at all.
        rows = (
            await _bounded_statement(
                session,
                timeout_literal=f"'{CENSUS_STATEMENT_TIMEOUT_SECONDS}s'",
                server_budget_s=CENSUS_STATEMENT_TIMEOUT_SECONDS,
                sql="""
                    SELECT
                      (CURRENT_DATE - fm.updated_at::date) AS days_since_touch,
                      count(*)                             AS markets,
                      count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                                                           AS events
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1
                    """,
                params={"cat": SUSPECT_CATEGORY},
            )
        ).all()

        # Q496: this second query used to sit OUTSIDE the try. It is the same
        # scan under the same statement timeout, so it can fail the same way —
        # and when it did, the exception escaped, the dispatcher turned it into
        # a 500, and the `measured: false` contract the block above exists to
        # honour was never reached. A census's whole job is to be honest about
        # not knowing; a second query that can only fail LOUDLY defeats that.
        #
        # Events are counted per staleness bucket above, so they do NOT sum: one
        # event's rows can straddle two buckets. Ask for the distinct figure.
        total_events = (
            await _bounded_statement(
                session,
                timeout_literal=f"'{CENSUS_STATEMENT_TIMEOUT_SECONDS}s'",
                server_budget_s=CENSUS_STATEMENT_TIMEOUT_SECONDS,
                sql="""
                    SELECT count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    """,
                params={"cat": SUSPECT_CATEGORY},
            )
        ).scalar() or 0
    except Exception as exc:  # noqa: BLE001 — a census timeout is not a zero
        # Gotcha #54: a census that could not measure returns `measured: false`
        # with a reason, NEVER a zero. A zero here would read as "the population
        # is drained" — the exact opposite of "we could not look".
        #
        # CERT-670 (P1): this arm deliberately also catches
        # `ClientDeadlineExceeded`, and the `reason` below carries the type name,
        # so "we could not look" and "we could not even get a connection to look
        # with" are distinguishable without a second terminal on a diagnostic
        # that has no cursor to protect.
        #
        # The rollback is new and is not tidiness. A client-side deadline cancels
        # the statement mid-flight, and `get_db_rw` COMMITS after this handler
        # returns — a wedged connection would turn this honest `measured: false`
        # into the bare 500 it exists to replace.
        await _safe_rollback(session)
        return {
            "repair": "polymarket-sport-category-census",
            "measured": False,
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "elapsed_s": round(time.monotonic() - started, 2),
        }

    by_staleness = [
        {"days_since_touch": int(r[0]), "markets": int(r[1]), "events": int(r[2])}
        for r in rows
    ]
    total_markets = sum(b["markets"] for b in by_staleness)

    stale_4d_plus = sum(b["markets"] for b in by_staleness if b["days_since_touch"] >= 4)

    return {
        "repair": "polymarket-sport-category-census",
        "measured": True,
        "population": f"source=polymarket status=open llm_sport_category={SUSPECT_CATEGORY}",
        "markets": total_markets,
        "events": int(total_events),
        "markets_stale_4d_plus": stale_4d_plus,
        "by_staleness": by_staleness,
        # Said out loud because the number is the argument for the rail: these
        # rows are not being re-fetched, so they do not self-heal.
        "note": (
            "markets_stale_4d_plus have not been re-ingested in 4+ days; the "
            "hourly poller is not reaching them, so the Q493 classifier fix "
            "cannot repair them without this drain"
        ),
        "elapsed_s": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------


async def _fetch_event(
    client: httpx.AsyncClient, event_id: str
) -> tuple[str, Optional[dict[str, Any]]]:
    """Return ``(status, payload)`` where status is ok/not_at_venue/indeterminate.

    Never raises for a venue condition and never collapses "does not exist" into
    "did not answer" — 404 and 429 need opposite handling and a catch-all that
    returned ``None`` for both would write a verdict on a rate limit (#36).
    """
    try:
        r = await client.get(f"{GAMMA}/events/{event_id}", timeout=FETCH_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — transport failure is INDETERMINATE
        return "indeterminate", None
    if r.status_code == 404:
        return "not_at_venue", None
    if r.status_code != 200:
        return "indeterminate", None
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        return "indeterminate", None
    if not isinstance(payload, dict):
        return "indeterminate", None
    return "ok", payload


def classify_event_payload(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Run the SHIPPED ingest cascade over a raw Gamma event payload.

    Returns ``(category, llm_sport_category)`` exactly as
    ``_process_event_batch`` would compute them. Imported inside the function so
    this module stays import-light and `sport_keys`-style circularity cannot
    creep in via the task package.

    This function deliberately contains NO sport rules of its own. Every rule it
    applies lives in `app/tasks/polymarket.py`; if that file changes, this rail
    changes with it and cannot drift.
    """
    from app.tasks.polymarket import _tags_to_category, resolve_event_category

    raw_tags = payload.get("tags") or []
    tags: list[str] = []
    for t in raw_tags:
        # Gamma returns tags as objects ({"label": "Tennis", ...}); older shapes
        # and our own fixtures use bare strings. Accept both rather than assume.
        if isinstance(t, str):
            tags.append(t)
        elif isinstance(t, dict):
            label = t.get("label") or t.get("slug") or t.get("name")
            if label:
                tags.append(str(label))

    title = payload.get("title") or ""
    markets = payload.get("markets") or []
    group_names = [title] + [
        str((m or {}).get("question") or "") for m in markets if isinstance(m, dict)
    ]

    category, llm_sport_category = _tags_to_category(tags)
    category, llm_sport_category, _arm = resolve_event_category(
        category, llm_sport_category, title, group_names
    )
    return category, llm_sport_category


# ---------------------------------------------------------------------------
# Repair — the write half
# ---------------------------------------------------------------------------


async def repair(
    session,
    apply: bool = False,
    limit: int = None,
    after_date: str = None,
    after_id: int = None,
    **_ignored,
) -> dict[str, Any]:
    """Re-ask the venue for each mis-filed event and store the shipped cascade's answer.

    Dry-run by default. Resumable by KEYSET (``after_date`` + ``after_id``
    from ``next_cursor``), never by offset — this repair removes rows from its
    own population.
    """
    started = time.monotonic()
    cap = min(int(limit or APPLY_EVENT_CAP), APPLY_EVENT_CAP)

    # CERT-666 (P1): the cursor starts where the OPERATOR already was, not at
    # None. A page whose very first event fails to resolve must hand back the
    # cursor it was given — handing back None reads as "start over" and silently
    # sends an attended drain to page one.
    #
    # CERT-667: computed BEFORE the page SELECT, because the SELECT can now fail
    # in a bounded, reportable way and that report has to carry a cursor too.
    incoming_cursor: Optional[dict[str, Any]] = (
        {"after_date": after_date, "after_id": int(after_id)} if after_id is not None else None
    )

    params: dict[str, Any] = {"cat": SUSPECT_CATEGORY, "cap": cap}

    # The cursor is a page position, and `after_id` alone is enough to name one.
    # Q496: the gate used to be `after_date AND after_id is not None`, so the
    # NULL-commence_time region — which `NULLS LAST` puts at the very end — was
    # unresumable: its cursor carries `after_date: None`, the keyset never
    # activated, and the next call silently re-read page ONE forever.
    keyset = ""
    if after_id is not None:
        params["after_id"] = int(after_id)
        if after_date:
            # In the non-NULL region. Everything still to come is either a
            # smaller (commence_time, anchor_id) tuple, or ANY row in the NULL
            # region — because NULLS LAST sorts the whole of it after us.
            keyset = """
                  AND ( ev.commence_time IS NULL
                        OR (ev.commence_time, ev.anchor_id) <
                           (CAST(:after_date AS timestamptz), CAST(:after_id AS integer)) )
            """
            params["after_date"] = after_date
        else:
            # Already inside the NULL region: ordering there is by anchor_id
            # alone, and no non-NULL row can follow.
            keyset = """
                  AND ev.commence_time IS NULL
                  AND ev.anchor_id < CAST(:after_id AS integer)
            """

    # One row per EVENT (the unit of a venue call), carrying the anchor row's
    # id/commence for the cursor. `min(id)` keeps the cursor deterministic.
    #
    # Q496: the keyset is applied AFTER the aggregation, never to the raw market
    # rows. The cursor is a pair of AGGREGATES (`max(commence_time)`,
    # `min(id)`), so filtering the inputs to those aggregates is filtering a
    # different quantity than the one the cursor names: an event whose markets
    # straddle the boundary would have some rows removed, recompute a DIFFERENT
    # `max(commence_time)`, and so move in the ordering between pages — which is
    # exactly how a keyset both repeats and skips events.
    #
    # CERT-667 (`Q496-END-TO-END-DB-DEADLINE`): armed with a statement timeout.
    # This is the first statement of the request and it ran BEFORE every deadline
    # the rail checks — the loop's ``DEADLINE_SECONDS`` cannot fire until this
    # returns — so a lock on `futures_markets` or a bad plan held the request to
    # the router wall with nothing able to interrupt it. That is an H12 with no
    # body: no counts, no cursor, and an attended drain loses its place. Bounding
    # the venue calls while leaving the query that FINDS them unbounded was the
    # gap; the budget was end-to-end everywhere except its own first step.
    #
    # CERT-670 (P1): the statement timeout above is armed by a statement, and
    # that statement is the one that acquires the pooled connection. Arming was
    # therefore itself unbounded, and the pool's own wait is 30s — the router
    # wall exactly. `_bounded_statement` puts a client-side deadline around the
    # checkout as well as the query, which is the only bound that can fire while
    # PostgreSQL is still unreachable.
    try:
        targets = (
            await _bounded_statement(
                session,
                timeout_literal=str(int(TARGET_SELECT_BUDGET_SECONDS * 1000)),
                server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
                sql=f"""
                SELECT ev.event_id, ev.commence_time, ev.anchor_id, ev.markets
                FROM (
                  SELECT
                    fm.market_metadata->>'polymarket_event_id' AS event_id,
                    max(fm.commence_time)                      AS commence_time,
                    min(fm.id)                                 AS anchor_id,
                    count(*)                                   AS markets
                  FROM futures_markets fm
                  WHERE fm.source = 'polymarket'
                    AND fm.status = 'open'
                    AND fm.llm_sport_category = :cat
                    AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                  GROUP BY 1
                ) ev
                WHERE TRUE
                  {keyset}
                ORDER BY ev.commence_time DESC NULLS LAST, ev.anchor_id DESC
                LIMIT :cap
                """,
                params=params,
            )
        ).all()
    # CERT-670 (P1): ordered before the generic arm, and it has to be — the two
    # failures are indistinguishable in a stack trace and completely different to
    # the operator. A server timeout says the database took the query and could
    # not finish it; this says the query never got a connection to run on, so
    # retrying straight away just re-joins the same queue.
    except ClientDeadlineExceeded as exc:
        await _safe_rollback(session)
        paused = _paused_before_examining(
            incoming_cursor=incoming_cursor,
            cap=cap,
            started=started,
            terminal="paused_pool_timeout",
            stopped_at_pool_timeout="target_select",
            reason=(
                f"the page SELECT did not get a database connection inside its "
                f"{client_db_budget_seconds(TARGET_SELECT_BUDGET_SECONDS)}s client "
                f"bound ({type(exc).__name__}: {exc})"[:300]
                + ". This is almost always pool saturation rather than a slow "
                "query — the statement never reached PostgreSQL, so no server "
                "timeout could fire. THIS IS NOT A COMPLETED DRAIN and it is not "
                "a verdict on any event: nothing was examined and nothing was "
                "written. The cursor returned is the one you passed in. Retrying "
                "immediately will usually queue behind the same saturation; give "
                "the pool a moment first."
            ),
        )
        logger.warning(
            "repair_polymarket_sport_category: the target page SELECT did not get "
            "a pooled connection inside its %.2fs client bound; returning the "
            "operator's own cursor rather than an H12 with no body",
            client_db_budget_seconds(TARGET_SELECT_BUDGET_SECONDS),
        )
        return paused
    except Exception as exc:  # noqa: BLE001 — a bounded page SELECT is not a crash
        # A statement timeout aborts the whole TRANSACTION, so the session is
        # unusable until it is rolled back.
        await _safe_rollback(session)
        logger.warning(
            "repair_polymarket_sport_category: the target page SELECT exceeded its "
            "%.2fs budget; returning the operator's own cursor rather than a 500",
            TARGET_SELECT_BUDGET_SECONDS,
        )
        # Gotcha #53/#54, and the same contract the census keeps: a step that could
        # not run says so by NAME. Letting this escape gave the dispatcher a bare
        # 500 whose detail does not distinguish "the database was busy" from "the
        # rail is broken", and which carries no cursor — so an operator mid-drain
        # could not tell a retry from a restart.
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            cap=cap,
            started=started,
            terminal="paused_target_timeout",
            stopped_at_pool_timeout=None,
            reason=(
                f"the page SELECT did not finish inside its "
                f"{TARGET_SELECT_BUDGET_SECONDS}s budget "
                f"({type(exc).__name__}: {exc})"[:300]
                + ". THIS IS NOT A COMPLETED DRAIN and it is not a verdict on any "
                "event — nothing was examined and nothing was written. The cursor "
                "returned is the one you passed in, so re-running retries the same "
                "page."
            ),
        )

    counts = {
        "events_examined": 0,
        "changed": 0,
        "unchanged": 0,
        "refused_other": 0,
        "not_at_venue": 0,
        "indeterminate": 0,
        # CERT-667: an event the venue answered for, that we decided to move, and
        # whose UPDATE then did not land. It is NOT `indeterminate` (the venue was
        # fine) and NOT `changed` in any useful sense (nothing was written), so it
        # gets its own number rather than hiding inside either.
        "write_failed": 0,
        "markets_written": 0,
    }
    #: What it changed them TO. A single "changed" number cannot tell a correct
    #: drain from a rail that relabelled the bucket to one wrong answer.
    to_category: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    next_cursor: Optional[dict[str, Any]] = incoming_cursor
    stopped_before: Optional[str] = None
    stopped_at_unresolved: Optional[str] = None
    stopped_at_write_timeout: Optional[str] = None
    # CERT-670 (P1): the write could not get a connection at all. Its own field
    # rather than a flag on the one above, for the same reason `write_failed` is
    # not folded into `indeterminate`: an operator who reads "the row was locked"
    # waits and retries, and an operator who reads "the pool was empty" goes and
    # looks at what else is holding twenty connections.
    stopped_at_pool_timeout: Optional[str] = None

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for t in targets:
            if (time.monotonic() - started) > DEADLINE_SECONDS:
                stopped_before = f"event_id={t.event_id}"
                break

            counts["events_examined"] += 1

            status, payload = await _fetch_event(client, str(t.event_id))
            await asyncio.sleep(VENUE_PAUSE)

            if status == "indeterminate":
                # CERT-666 (P1) — THE CURSOR MUST NOT CROSS UNFINISHED WORK.
                #
                # This used to advance `next_cursor` BEFORE the fetch, then
                # `continue`. So an ordinary 429/5xx/timeout on the last short
                # page left the event unchanged in the suspect category, moved
                # the cursor PAST it, and — because exhaustion was computed from
                # the page length alone — reported the drain finished. The
                # operator stopped with a mis-filed, user-visible match still
                # hidden, and the emitted cursor guaranteed it would never be
                # looked at again. A transient venue failure is not a verdict.
                #
                # We stop here instead, leaving the cursor on the last RESOLVED
                # event, so re-running with `next_cursor` retries this one.
                # Backing off is also the correct response to the 429 that most
                # often causes this.
                counts["indeterminate"] += 1
                stopped_at_unresolved = f"event_id={t.event_id}"
                break

            # Resolved — `ok` or a 404 `not_at_venue`, both of which are real,
            # repeatable answers.
            #
            # CERT-667: the cursor is PREPARED here and assigned only where this
            # event is genuinely finished. CERT-666 (P1) moved the advance from
            # before the fetch to after it, which fixed the venue half; the WRITE
            # was still downstream of the advance, so a failed UPDATE left the
            # event mis-filed with the cursor already past it — the same "cursor
            # crosses unfinished work" defect, one statement further along. Every
            # `continue` below therefore carries its own advance.
            resolved_cursor = {
                "after_date": t.commence_time.isoformat() if t.commence_time else None,
                "after_id": int(t.anchor_id),
            }

            if status != "ok" or payload is None:
                counts[status] += 1
                next_cursor = resolved_cursor
                continue

            category, llm_sport_category = classify_event_payload(payload)

            if not llm_sport_category or llm_sport_category == "other":
                # Never overwrite a real value with the "other" default — the
                # same guard the poller's own update_set carries.
                counts["refused_other"] += 1
                next_cursor = resolved_cursor
                continue

            if llm_sport_category == SUSPECT_CATEGORY:
                # The venue confirms it. Setka/TT-Cup lands here, which is how
                # this rail proves it is safe rather than asserting it.
                counts["unchanged"] += 1
                next_cursor = resolved_cursor
                continue

            counts["changed"] += 1
            to_category[llm_sport_category] = to_category.get(llm_sport_category, 0) + 1
            if len(samples) < 10:
                samples.append(
                    {
                        "event_id": str(t.event_id),
                        "title": str(payload.get("title") or "")[:100],
                        "from": SUSPECT_CATEGORY,
                        "to": llm_sport_category,
                        "markets": int(t.markets),
                    }
                )

            if not apply:
                next_cursor = resolved_cursor
                continue

            # CERT-667 (`Q496-END-TO-END-DB-DEADLINE`) — THE WRITE WAS THE LAST
            # STATEMENT THE BUDGET DESCRIBED BUT DID NOT ENFORCE.
            #
            # `POST_LOOP_NON_COUNT_RESERVE_SECONDS` already accounted for "the last
            # event's write and commit", but nothing held the write to it: this
            # UPDATE takes a row lock on `futures_markets`, which the ordinary
            # Polymarket poller also writes, so a contended row could block here
            # for as long as the other transaction lived — unbounded, past the
            # router wall, H12 with no body, cursor lost. The rail bounded the
            # venue and left the database open.
            #
            # Re-armed per event because the `commit()` below ends the transaction
            # and a `SET LOCAL` dies with it.
            #
            # CERT-670 (P1): the commit is now INSIDE the bounded unit, and the
            # unit is bounded on the client side as well. Two reasons. The commit
            # runs on the same connection and can block on the same row lock the
            # UPDATE took, so leaving it outside bounded the statement and not the
            # operation. And this write begins a NEW transaction — the previous
            # event's commit released the connection back to the pool — so the
            # `SET LOCAL` that arms the bound has to check a connection out
            # first, unbounded, against a pool whose own wait equals the router
            # wall.
            #
            # A cancelled commit is genuinely ambiguous: the UPDATE may have
            # landed on the server after we stopped waiting. That is safe here
            # and it is the compare-and-set that makes it safe — a retry of an
            # event that did commit matches no rows (`llm_sport_category` is no
            # longer `:cat_old`), writes nothing, and reports rowcount 0. The
            # ambiguity costs a wasted venue call, never a wrong row.
            try:
                # Core UPDATE, never ORM attribute assignment (gotchas #4/#5).
                # Compare-and-set on the category we selected on, so a concurrent
                # re-ingest that already corrected the row is never clobbered by a
                # verdict computed before it landed.
                r = await _bounded_statement(
                    session,
                    timeout_literal=str(int(WRITE_BUDGET_SECONDS * 1000)),
                    server_budget_s=WRITE_BUDGET_SECONDS,
                    sql="""
                        UPDATE futures_markets
                        SET llm_sport_category = :llm,
                            category = CASE
                                WHEN :cat_new = 'championship' THEN 'championship'
                                ELSE category
                            END,
                            updated_at = NOW()
                        WHERE source = 'polymarket'
                          AND status = 'open'
                          AND llm_sport_category = :cat_old
                          AND market_metadata->>'polymarket_event_id' = :eid
                        """,
                    params={
                        "llm": llm_sport_category,
                        "cat_new": category,
                        "cat_old": SUSPECT_CATEGORY,
                        "eid": str(t.event_id),
                    },
                    commit=True,
                )
            except ClientDeadlineExceeded:
                # Same stop-and-keep-the-cursor rule as the server timeout below,
                # and deliberately its OWN field: "the pool was empty" and "the
                # row was locked" send an operator to different places.
                await _safe_rollback(session)
                counts["write_failed"] += 1
                stopped_at_pool_timeout = f"event_id={t.event_id} (write)"
                logger.warning(
                    "repair_polymarket_sport_category: the UPDATE for %s did not "
                    "get a database connection inside its %.2fs client bound; "
                    "stopping the scan with the cursor BEFORE it",
                    t.event_id,
                    client_db_budget_seconds(WRITE_BUDGET_SECONDS),
                )
                break
            except Exception:  # noqa: BLE001 — a blocked write is not a verdict
                # A statement timeout aborts the whole TRANSACTION, so the session
                # is unusable until it is rolled back. Everything committed by the
                # events BEFORE this one is already durable and stays counted.
                await _safe_rollback(session)
                counts["write_failed"] += 1
                stopped_at_write_timeout = f"event_id={t.event_id}"
                logger.warning(
                    "repair_polymarket_sport_category: the UPDATE for %s exceeded "
                    "its %.2fs budget; stopping the scan with the cursor BEFORE it",
                    t.event_id,
                    WRITE_BUDGET_SECONDS,
                )
                # Deliberately WITHOUT advancing the cursor: this event is still
                # mis-filed, so re-running with `next_cursor` must retry it. Same
                # rule as an unresolved venue answer — the cursor never crosses
                # work that did not happen.
                break

            counts["markets_written"] += r.rowcount
            next_cursor = resolved_cursor

    # CERT-666 (P2) — THE TERMINAL COUNT WAS THE LAST UNBOUNDED STATEMENT IN THE
    # REQUEST. It ran after the loop deadline had already passed, carried no
    # statement timeout, and a lock or a bad plan could therefore hold the
    # request past the router wall on its own — costing the operator the H12 with
    # no body, and so the cursor, which is the exact failure this rail exists to
    # avoid. Give it the budget that ACTUALLY remains rather than a constant: if
    # the loop over-ran, the count gets less time, not the same time.
    count_budget_s = max(
        0.25,
        ROUTER_WALL_SECONDS
        - (time.monotonic() - started)
        - POST_LOOP_NON_COUNT_RESERVE_SECONDS,
    )
    remaining: Optional[int] = None
    remaining_measured = True
    try:
        # Interpolated, not bound: `SET` takes no bind parameters. The value is
        # an int we computed from our own constants, never operator input.
        #
        # CERT-670 (P1): the loop's last commit released the connection, so this
        # count checks one out again — the third site where arming the bound was
        # itself unbounded.
        remaining = (
            await _bounded_statement(
                session,
                timeout_literal=str(int(count_budget_s * 1000)),
                server_budget_s=count_budget_s,
                sql="""
                    SELECT count(DISTINCT fm.market_metadata->>'polymarket_event_id')
                    FROM futures_markets fm
                    WHERE fm.source = 'polymarket'
                      AND fm.status = 'open'
                      AND fm.llm_sport_category = :cat
                      AND fm.market_metadata->>'polymarket_event_id' IS NOT NULL
                    """,
                params={"cat": SUSPECT_CATEGORY},
            )
        ).scalar() or 0
    except Exception:  # noqa: BLE001 — a slow count must not cost the operator the cursor
        # A statement timeout aborts the whole TRANSACTION, not just the
        # statement, so the session is unusable until it is rolled back.
        #
        # CERT-670 (P1): `ClientDeadlineExceeded` lands here TOO, and that is the
        # deliberate choice rather than an oversight. The count is a decoration on
        # a drain that has already happened: every write above is committed and
        # the cursor is already correct. Giving this arm a pause terminal would
        # turn a successful page into a paused one over a number the response
        # already knows how to describe as unmeasured — inventing a failure out of
        # a missing statistic. `remaining_events_measured: false` is the whole
        # contract here and it covers both ways of not knowing.
        await _safe_rollback(session)
        remaining_measured = False
        logger.warning(
            "repair_polymarket_sport_category: remaining_events count exceeded its "
            "%.2fs budget; reporting it unmeasured rather than losing the response",
            count_budget_s,
        )

    # Q496 — SCAN EXHAUSTION IS A DIFFERENT FACT FROM `remaining_events`, and
    # conflating them made the drain's success state unreachable.
    #
    # `remaining_events` counts the SUSPECT CATEGORY, and Setka/TT-Cup events
    # are legitimately in it — they are the control this rail deliberately does
    # not move. So `remaining_events` has a positive floor it can never go
    # below, `remaining == 0` is unreachable, and the old `terminal="complete"`
    # arm was dead code: a fully drained population reported `no_work`, which
    # reads as "the cursor is wrong", not "you are finished".
    #
    # Exhaustion is instead proven by the PAGER: the page came back short of the
    # cap (so no row sorts after it) and the loop consumed all of it (so nothing
    # was left unexamined by the deadline).
    #
    # CERT-666 (P1): exhaustion also requires that nothing on the page was left
    # UNRESOLVED. A short, fully-consumed page proves no row sorts after it — it
    # does not prove every row in it was answered, and a transient venue failure
    # leaves an event that may still be mis-filed sitting behind the cursor.
    #
    # Both terms are deliberate. `stopped_at_unresolved` is what the loop
    # actually sets today; the `indeterminate` count is the invariant — if a
    # later change turns that `break` back into a `continue`, completion still
    # cannot be claimed while any retryable result remains.
    #
    # CERT-667: and that nothing on the page was left UNWRITTEN. A short page
    # every event of which the venue answered still is not a finished drain if
    # one of those answers never reached the table — the row is as mis-filed as
    # if we had never asked. Both terms again: `stopped_at_write_timeout` is what
    # the loop sets today, `write_failed` is the invariant that survives someone
    # turning that `break` back into a `continue`.
    #
    # CERT-670 (P1): and that nothing on the page was left unwritten because the
    # rail could not reach the database at all. `write_failed` below already
    # covers this arm as an invariant — the pool-timeout branch increments it for
    # exactly that reason — and the named term is here anyway, on the same
    # both-terms principle the two clauses above use: the count survives someone
    # turning the `break` into a `continue`, and the field survives someone
    # deciding a connection failure should not be counted as a failed write.
    scan_exhausted = (
        len(targets) < cap
        and stopped_before is None
        and stopped_at_unresolved is None
        and stopped_at_write_timeout is None
        and stopped_at_pool_timeout is None
        and counts["indeterminate"] == 0
        and counts["write_failed"] == 0
    )

    result: dict[str, Any] = {
        "repair": "polymarket-sport-category",
        "applied": bool(apply),
        "counts": counts,
        "changed_to": to_category,
        "samples": samples,
        "remaining_events": int(remaining) if remaining_measured else None,
        # CERT-666 (P2): "it returned" is not "it worked" (gotcha #53). A count
        # that ran out of budget reports itself unmeasured; it never reports 0.
        "remaining_events_measured": remaining_measured,
        # NB: this string may not name the control league. `SUSPECT_CATEGORY` is
        # the only sport literal permitted in executable code here, and the Q495
        # anti-drift guard scans string literals too — correctly, since a rule
        # table would arrive as literals long before it arrived as an `if`.
        "remaining_events_note": (
            "count of the SUSPECT CATEGORY, which legitimately includes the "
            "control events the venue confirms really do belong to it. It has a "
            "positive floor and reaching zero is NOT the end state — read "
            "`scan_exhausted` for that. `null` means the count ran out of its "
            "budget and was NOT measured; it never means zero — see "
            "`remaining_events_measured`."
        ),
        "scan_exhausted": scan_exhausted,
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        # CERT-666 (P1): the event the venue would not answer for. The cursor
        # stops BEFORE it, so re-running retries it. Never a verdict on the row.
        "stopped_at_unresolved": stopped_at_unresolved,
        # CERT-667: the event the venue DID answer for and whose UPDATE did not
        # land inside its budget. Also not a verdict, and also behind the cursor.
        "stopped_at_write_timeout": stopped_at_write_timeout,
        # CERT-670: the event whose UPDATE never reached the database, because no
        # pooled connection came free inside the client bound. Also not a verdict,
        # also behind the cursor — and a different thing to go and look at.
        "stopped_at_pool_timeout": stopped_at_pool_timeout,
        "cap": cap,
        "ordering": (
            "newest commence_time first — the user-visible rows. Gotcha #41's "
            "tail-starvation is accepted here because Polymarket EVENT data is "
            "durable, so the tail cannot rot while it waits; `remaining_events` "
            "is reported every call so it is never silent."
        ),
        "budget": {
            "router_wall_s": ROUTER_WALL_SECONDS,
            "deadline_s": DEADLINE_SECONDS,
            "fetch_timeout_s": FETCH_TIMEOUT_SECONDS,
            "venue_pause_s": VENUE_PAUSE,
            # CERT-667: the two DB bounds are reported because they are the two
            # the rail previously described and did not enforce. Neither widens
            # the worst case — the SELECT runs inside the deadline's own window
            # and the write inside the post-loop reserve — so the headroom below
            # is unchanged by them, which is a claim a guard checks.
            "target_select_budget_s": TARGET_SELECT_BUDGET_SECONDS,
            "write_budget_s": WRITE_BUDGET_SECONDS,
            # CERT-670: the two SERVER bounds above are only reachable once a
            # connection is, so the client-side slack that wraps every unit is
            # published alongside them. Reported as the slack rather than as two
            # more derived numbers, because it is one constant and the derivation
            # is `client_db_budget_seconds`.
            "pool_acquire_slack_s": POOL_ACQUIRE_SLACK_SECONDS,
            "worst_case_headroom_s": round(budget_headroom_seconds(), 2),
        },
    }

    # "It returned" is not "it worked" (gotcha #53 / task_verdict). Each zero
    # state is a DIFFERENT real state and gets its own terminal rather than
    # sharing one silent success.
    # CERT-666 (P1): an unresolved event outranks every other terminal. The run
    # did NOT finish, whatever else it managed, and the operator must re-run
    # before reading anything as complete. Checked first so no arm below can
    # quietly describe this as a finished drain.
    # CERT-670 (P1): checked FIRST, above even `paused_unresolved`. Not because a
    # lost connection is worse for the data — it is the same "one event behind the
    # cursor is still mis-filed" — but because it is the only terminal here that
    # says something about the DYNO rather than about an event. Ranked below the
    # others it would be reachable only when nothing else went wrong, so the run
    # that starves the pool AND then fails a venue call — the likely combination,
    # since both follow from load — would report the venue and hide the cause.
    if stopped_at_pool_timeout is not None:
        result["terminal"] = "paused_pool_timeout"
        result["reason"] = (
            f"the database work for {stopped_at_pool_timeout} did not get a "
            f"pooled connection inside its client bound — almost always pool "
            "saturation, NOT a verdict on that event and NOT a slow query: the "
            "statement never reached PostgreSQL, so no server timeout could "
            "fire. The cursor deliberately stops BEFORE it, so re-running with "
            "`next_cursor` retries it. THIS IS NOT A COMPLETED DRAIN: that event "
            "is still mis-filed. Everything committed above it on this page is "
            "durable and still applies. Retrying immediately will usually queue "
            "behind the same saturation — look at what else is holding "
            "connections first."
        )
    elif stopped_at_unresolved is not None:
        result["terminal"] = "paused_unresolved"
        result["reason"] = (
            f"the venue did not answer for {stopped_at_unresolved} — a transient "
            "failure (timeout, 429, 5xx, or an unreadable body), NOT a verdict on "
            "that event. The cursor deliberately stops BEFORE it, so re-running "
            "with `next_cursor` retries it. THIS IS NOT A COMPLETED DRAIN: the "
            "event may still be mis-filed, and anything already counted above it "
            "on this page is real and still applies."
        )
    elif stopped_at_write_timeout is not None:
        # CERT-667: ranked with `paused_unresolved`, above every success arm, for
        # the same reason — the run did NOT finish. Without this the terminal
        # would have read "changed", because the classification counts are real
        # and only the write is missing: the most reassuring possible wording for
        # a page that left a user-visible row exactly as wrong as it found it.
        result["terminal"] = "paused_write_timeout"
        result["reason"] = (
            f"the venue answered for {stopped_at_write_timeout} but its UPDATE did "
            f"not land inside the {WRITE_BUDGET_SECONDS}s write budget — almost "
            "always a row lock held by the ordinary poller, NOT a verdict on that "
            "event. The cursor deliberately stops BEFORE it, so re-running with "
            "`next_cursor` retries it. THIS IS NOT A COMPLETED DRAIN: that event "
            "is still mis-filed. Everything committed above it on this page is "
            "durable and still applies."
        )
    elif counts["events_examined"] == 0:
        result["terminal"] = "complete" if scan_exhausted else "no_work"
        result["reason"] = (
            "the pager reached the end of the population under this cursor — "
            "every event still filed here has been examined and the venue "
            "confirmed it, so `remaining_events` is a floor, not a backlog"
            if scan_exhausted
            else "no events selected by this page — advance or clear the cursor"
        )
    elif counts["changed"] == 0:
        result["terminal"] = "examined_no_change_complete" if scan_exhausted else "examined_no_change"
        result["reason"] = (
            "every event examined was confirmed by the venue, refused as "
            "'other', or did not answer — see counts; this is a real state, "
            "not a silent success"
            + (
                " — and this was the LAST page, so the drain is finished"
                if scan_exhausted
                else ""
            )
        )
    else:
        result["terminal"] = "changed" if apply else "dry_run"
        result["reason"] = (
            f"{counts['changed']} event(s) disagree with the venue"
            + ("" if apply else " — nothing written, re-run with apply=true")
        )
    result["elapsed_s"] = round(time.monotonic() - started, 2)
    return result
