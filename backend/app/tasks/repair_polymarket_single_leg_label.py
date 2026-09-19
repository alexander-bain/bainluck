"""#6739 — the already-settled half: a graded page that never names the winner.

PILLAR: TRUTH. SHIP: a settled Polymarket game page says who won, for the 183
events where it still says only "Settled".

WHAT THIS IS THE SECOND HALF OF
-------------------------------
``301a2174a`` fixed the WRITER. ``_parent_outcome_data``'s single-market branch
hard-coded ``"name": "Yes"``, which is right for a genuine binary question and
wrong for a game whose venue listing holds only the moneyline — those arrive at
the same branch with ``question`` set to the matchup and the two sides sitting
in ``outcomes``. Every newly-ingested event now names its side.

🔴 AND IT REACHES NONE OF THE ALREADY-SETTLED ROWS, BY CONSTRUCTION.
``poll_polymarket_markets`` fetches ``closed=False``. A market that has settled
is out of its rotation permanently, so the upsert's ``on_conflict_do_update``
never fires on it again — the writer's own commit message says so and calls it
"FORWARD ONLY", rather than leaving it to be discovered later. That is the Q499
lesson applied in advance; this rail is the drain it names.

The reader cost is not cosmetic. ``venue_settlement._names_a_participant``
orients a settled page from the graded leg's NAME. A leg called "Yes" names no
participant, so the page draws a bare "Settled" chip over a win-probability hero
and never says who won. Photographed 2026-09-19 on ``/events/15312402``
(Melbourne Demons vs. Carlton Blues): the chip reads "Settled", both crests are
shown, the chart ends at 91% — and the winner appears nowhere, though the
venue's own ``outcomePrices`` read ``["1", "0"]`` and our ``is_winner`` is
already ``true``.

THE POPULATION, MEASURED AT THE VENUE RATHER THAN ASSUMED
---------------------------------------------------------
183 markets across 181 events, settled, whose event commenced inside the last
30 days (2026-08-21 → 2026-09-19). Every one re-read at Gamma by condition id,
both ``closed=false`` AND ``closed=true`` (see below), on 2026-09-19:

    venue names the two sides, leg mislabelled "Yes"    183
    venue outcomes really are ["Yes","No"]                0
    not at the venue                                      0

Unlike the live cohort the writer measured (223 of 240), this one is *pure*:
a genuine binary question does not get an ``events`` row with two crests and a
win-probability hero, so it is not in this population at all.

🔴 THE FIRST READ OF THAT COHORT SAID "77 NOT AT VENUE" AND THAT NUMBER WAS THE
INSTRUMENT, NOT THE VENUE. Gamma's default page size for ``/markets`` is 20, so
a 40-id batch silently returns the first 20 and the rest read as delisted. The
shipped ``get_markets_by_conditions`` has passed ``limit`` since 2026-08-26 and
says why in its own docstring; the ad-hoc probe did not. With ``limit`` the same
183 ids answered 183. This rail reads through the shipped service precisely so
it cannot reacquire that bug — and gotcha #53 is why the miss was visible at
all: 77 "absences" that were really one truncation.

``/markets?condition_ids=…`` ALSO silently applies ``closed=false`` (Q499,
measured 7 of 40 on the default call and the other 33 on ``closed=true``).
Every row in THIS cohort is settled, so the default read alone would have
returned approximately nothing. ``include_closed=True`` is not an optimisation
here, it is the difference between a drain and a no-op.

WHY THE LABEL RULE IS ``_sub_market_side_label`` AND NOT ``_leg_label``
-----------------------------------------------------------------------
🔴 THE SIBLING DRAIN (Q499) CALLS ``_leg_label``, AND COPYING IT HERE WOULD
SHIP THE DEFECT ITS OWN WRITER PINNED A TEST AGAINST. ``_leg_label`` falls back
to ``_extract_outcome_name``, which renames a genuine binary question to a
fragment of itself — ``test_leg_label_would_have_renamed_a_genuine_binary_question``
exists for exactly this. The writer commit chose ``_sub_market_side_label``
deliberately and this rail imports the same function, byte-for-byte, from the
poller. It contains **no label rule of its own** and a guard fails the build if
it grows one.

(The handoff note that queued this work said "only the population filter
changes" from Q499. That was wrong in the one way that matters, and it is
written down here so the next reader does not re-derive it from the sibling.)

WHY INDEX 0 IS THE SIDE THIS PRICE BELONGS TO
----------------------------------------------
``outcomes`` is the array parallel to ``outcome_prices``, and the single-market
branch prices its one leg from ``outcome_prices[0]`` — so ``outcomes[0]`` is the
matching side by construction, not by inference. There is no orientation guess
anywhere in this rail, which matters because a wrong answer here is not an ugly
label, it is a confident wrong winner on a settled page.

That argument holds only while the row really is a single-market-branch row, so
it is CHECKED rather than trusted, three ways:

* the population takes markets carrying exactly ONE outcome;
* a venue market with a ``group_item_title`` is REFUSED (``refused_grouped``) —
  that is the decomposed sub-market writer's shape, where the stored leg may be
  index 1 and index 0 would name the loser;
* corroborated against the stored price before this was built: of 183 rows,
  156 had ``current_probability`` equal to the venue's ``outcomePrices[0]``,
  **0 matched ``outcomePrices[1]``**, and 27 matched neither (a stale stored
  price — ``['0.5','0.5']``, or 0.5 against a settled ``['0','1']``). Zero
  contradictions. All 183 carried ``group_item_title: None`` and exactly one
  ``events`` entry.

The price corroboration is deliberately NOT a runtime gate: it cannot speak for
the 27 stale rows, and a rail that wrote only where the price agreed would drain
156 and call itself finished.

THE CONTRACT
------------
``census`` — read-only. Never writes; ``apply`` is accepted and ignored. A
timeout returns ``measured: false`` with a reason, NEVER a zero (gotcha #54):
a zero here would read as "drained".

``repair`` — dry-run by default. Keyset-paged on the leg's own id, because the
write removes rows from the rail's own population and an offset would skip as
many untouched rows as the last page repaired. Every write is a compare-and-set
on the exact name it selected on, and it names **one column** — ``last_updated``
is a poller touch-stamp another surface reads as liveness (#2024) and a repair
must not forge it.

🔴 BOTH HALVES ARE SCOPED TO A WINDOW (``days``, default 30) AND SAY SO IN THEIR
OWN OUTPUT. The bound is a PLAN choice as much as a product one: the unbounded
form of this population is a GROUP BY over ~90,000 event-attached legs and times
out at 10s, while the windowed form measures 2.4s. ``scan_exhausted`` therefore
means "no rows left INSIDE THIS WINDOW" and the response repeats the window back
so nobody reads it as "the cohort is empty". Widening is an operator's choice
with a cost, not a default.

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
# writer, and the drift would be invisible because both answers look plausible.
from app.tasks.polymarket import _sub_market_side_label

logger = logging.getLogger(__name__)


#: The Heroku router's hard wall on a synchronous request. Past this the router
#: returns H12 and the operator gets no body at all — no counts, and crucially
#: no ``next_cursor``, so an attended drain loses its place rather than pausing.
ROUTER_WALL_SECONDS = 30

#: One venue STEP is a batch PAIR — the default read plus the ``closed=true``
#: read — budgeted together rather than per request, because the pair is what
#: the loop actually waits on and two separate bounds would permit their sum.
#: Measured 2026-09-19 over this cohort's five batches; the pair stayed under
#: 1.5s throughout, so this is ~4x the observed cost.
BATCH_PAIR_BUDGET_SECONDS = 6.0

#: Condition ids per venue request. 40 keeps the URL ~3.3KB, well clear of a 414.
GAMMA_BATCH_SIZE = 40

#: Pause between venue steps. Polymarket's Gamma limiter is real.
VENUE_PAUSE = 0.35

#: The point past which no NEW batch is started, checked at the top of the loop.
#: The true worst case is this plus one whole batch pair plus one pause plus
#: everything after the loop — see ``budget_headroom_seconds()``, which a guard
#: asserts stays positive rather than leaving the arithmetic in a comment.
DEADLINE_SECONDS = 10

#: 🔴 WHAT ONE `_safe_rollback` COSTS — the CERT-681 line, inherited from the
#: sibling rail. A failed final write pays a cleanup; if the rail then started
#: its terminal count unconditionally, a failed count would pay a SECOND one and
#: the declared worst path exceeds the wall through the FAILURE path rather than
#: the happy one. ``repair()`` therefore SKIPS the terminal count when the write
#: has already failed, and a guard asserts at most one cleanup is on that path.
CLEANUP_RESERVE_SECONDS = 3.0

#: Response serialization plus the request dependency's own commit, which runs
#: after the handler has returned and so cannot be observed from inside it.
SERIALIZATION_RESERVE_SECONDS = 0.5

#: Time reserved for everything AFTER the loop's last fetch: the single bulk
#: write, its commit, at most one cleanup, the terminal count, serialization,
#: and the dependency's commit.
POST_LOOP_RESERVE_SECONDS = 8.0

#: The slice of the reserve that is NOT the terminal count. The count is armed
#: with whatever is left of the wall once this is set aside, so an over-running
#: loop shortens the count's timeout instead of borrowing against work that
#: still has to run. A guard asserts the DERIVED client bounds fit inside it.
POST_LOOP_NON_COUNT_RESERVE_SECONDS = 6.5

#: Bound on the page SELECT. It does not widen the worst case: ``started`` is
#: captured BEFORE this query, so a slow SELECT leaves the loop less room and
#: the first deadline check stops it. That holds only while this stays at or
#: under ``DEADLINE_SECONDS``, which a guard asserts. Measured 2.4s on
#: production 2026-09-19 for the windowed keyset form, so 8s is over 3x.
TARGET_SELECT_BUDGET_SECONDS = 8.0

#: Bound on the single bulk compare-and-set UPDATE. One statement per page keyed
#: by primary key; the realistic cost is milliseconds and the bound exists for
#: the row lock the ordinary poller can hold on the very legs this rewrites.
WRITE_BUDGET_SECONDS = 1.5

#: 🔴 THE COMMIT IS A SEPARATE UNIT BECAUSE THE RESULT IS READ BEFORE IT.
#: The write is ``UPDATE … RETURNING fo.id`` and those ids are the ONLY way to
#: tell a row that landed from a row the poller re-ingested between the SELECT
#: and the write. Reading a cursor after its transaction has committed is a
#: claim about SQLAlchemy's buffering, not about this rail — so the rows are
#: read while the transaction is open and the commit is its own bounded
#: statement, with a real bound because it can block on the update's own lock.
COMMIT_BUDGET_SECONDS = 0.5

#: Legs examined per call. A module constant, deliberately: the operator
#: re-invokes with the returned cursor, the operator does not raise the ceiling.
#: 120 legs is three batch pairs, so a full page normally COMPLETES and
#: ``stopped_before`` stays the exception it is meant to be. The measured
#: 183-leg cohort is two calls.
APPLY_LEG_CAP = 120

#: Statement timeout for the census, which runs ONE query under the router wall.
#: A census that H12s returns no body, so its honest "we could not look" answer
#: would never reach the operator and the gotcha-#54 argument would evaporate at
#: exactly the moment it matters.
CENSUS_STATEMENT_TIMEOUT_SECONDS = 12

#: Bound on the terminal ``remaining_legs`` count, capped by what the reserve
#: has left. Degradable on purpose: it reports itself unmeasured, never zero.
REMAINING_COUNT_MIN_BUDGET_SECONDS = 0.5

#: How far back the window reaches by default, in days. See the docstring: this
#: is a plan bound as much as a product one, and both halves report it back.
DEFAULT_WINDOW_DAYS = 30

#: 🔴 THE POPULATION, WRITTEN ONCE. The census and the pager must not be able to
#: disagree about what a side-less settled leg is.
#:
#: Expressed as a GROUP BY over the market rather than an anti-join, because the
#: anti-join forms TIME OUT: both ``NOT EXISTS (… f2.id <> fo.id)`` and its
#: ``IS NOT DISTINCT FROM`` variant exceeded 10s on production 2026-09-19, while
#: this form measured 2.4s with the cursor applied. ``count(*) = 1`` IS the
#: single-leg test and ``min(fo.name)`` is that one leg's name; the keyset rides
#: in the HAVING clause for the same reason, since ``min(fo.id)`` is the leg's
#: own id when there is exactly one of them.
POPULATION_FROM = """
          FROM futures_markets fm
          JOIN events e
            ON e.id = fm.event_id
           AND e.commence_time > now() - make_interval(days => CAST(:days AS int))
          JOIN futures_outcomes fo
            ON fo.market_id = fm.id
         WHERE fm.source = 'polymarket'
           AND fm.status = 'resolved'
"""

#: The half of the population that cannot go in a WHERE clause. ``'Yes'`` and
#: not a broader Yes/No set: the single-market branch wrote the literal ``"Yes"``
#: and nothing else, so a ``'No'`` leg here would be some other writer's row and
#: index 0 would not be its side.
POPULATION_HAVING = "count(*) = 1 AND min(fo.name) = 'Yes'"

#: Verdicts a single leg can reach. Every one is COUNTED — ruling 054: an
#: exclusion is counted, not skipped, and each zero state gets its own terminal
#: rather than one silent success (gotcha #53).
LEG_VERDICTS = (
    "relabelled",
    "unchanged",
    "not_at_venue",
    "no_condition_id",
    "refused_grouped",
    "refused_collision",
    "raced",
)


class VenueUnavailable(Exception):
    """The venue did not answer a batch: 429, 5xx, or a timeout.

    Distinct from "the market is not there". Nothing is written for a batch that
    raises this and the cursor RETRIES it — a throttled fetch treated as an
    empty answer would relabel nothing and report the cohort drained (gotcha #36,
    and gotcha #53's "an empty 200 is not an absence").
    """


def budget_headroom_seconds() -> float:
    """Seconds left under the router wall in the rail's WORST case.

    The deadline is checked at the top of the loop, so after it passes the rail
    may still start one whole batch pair and one pause; and after that the write,
    its commit, ONE cleanup, the terminal count, serialization and the
    dependency's commit still run. The cleanup appears once and not twice
    because ``repair()`` skips the count after a failed write.

    Expressed as a function so a guard can assert it stays positive, rather than
    as a comment that goes stale the first time someone raises one of the four
    numbers. Positive means an over-running call returns a partial answer WITH
    its cursor; negative means H12 with no body, and an attended drain silently
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
    days: int,
) -> dict[str, Any]:
    """The response for a page that died before it examined anything.

    Every count is zero and ``next_cursor`` is the cursor the operator HANDED
    IN, unchanged. Nothing was examined, so nothing may advance — re-running
    with it repeats the page rather than skipping it, which is the whole point
    of answering at all instead of letting the router return H12 with no body.
    """
    return {
        "repair": "polymarket-single-leg-label",
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
        "window_days": days,
        "elapsed_s": round(time.monotonic() - started, 2),
    }


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------


async def census(session, apply: bool = False, **_ignored) -> dict[str, Any]:
    """How many settled Polymarket game legs still name no side.

    Split by ``llm_sport_category``, because a bare total cannot tell a drain
    that is working from one that is only reaching the category the poller
    happens to rotate through — the exact reading that let Q492's partial fix
    look complete.

    ``apply`` is accepted and ignored. A census that could write would be a
    repair with a reassuring name. ``window_days`` is reported back because
    every number here is scoped to it.
    """
    started = time.monotonic()
    days = int(DEFAULT_WINDOW_DAYS)
    out: dict[str, Any] = {
        "census": "polymarket-single-leg-label",
        "measured": False,
        "reason": None,
        "total_legs": None,
        "total_markets": None,
        "window_days": days,
        "by_category": {},
    }

    sql = f"""
        SELECT COALESCE(category, '(null)') AS category,
               count(*) AS legs,
               count(DISTINCT market_id) AS markets
          FROM (
                SELECT fm.id AS market_id,
                       min(fm.llm_sport_category) AS category
                {POPULATION_FROM}
                 GROUP BY fm.id
                HAVING {POPULATION_HAVING}
               ) t
         GROUP BY 1
         ORDER BY 2 DESC
    """

    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{CENSUS_STATEMENT_TIMEOUT_SECONDS}s'",
            server_budget_s=float(CENSUS_STATEMENT_TIMEOUT_SECONDS),
            sql=sql,
            params={"days": days},
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

    ``include_closed=True`` is load-bearing and not a precaution: every row in
    this cohort is settled, and the default ``condition_ids`` read silently
    applies ``closed=false``, so without it this rail reads an empty venue and
    reports its whole population ``not_at_venue``.
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
    """Re-ask the venue for each side-less settled leg and store the shipped label.

    ``sport`` filters ``llm_sport_category`` — an operator draining hockey before
    baseball is choosing an order, not a different population. ``after_id`` is a
    keyset cursor on the leg's own id.

    The event window is ``DEFAULT_WINDOW_DAYS`` and is deliberately NOT a
    parameter: the dispatcher forwards a fixed set of names, and a rail that
    declared one outside it would advertise a knob no caller could turn. It is
    reported back on every response as ``window_days`` because
    ``scan_exhausted`` is scoped to it.
    """
    started = time.monotonic()
    cap = min(int(limit), APPLY_LEG_CAP) if limit else APPLY_LEG_CAP
    days = int(DEFAULT_WINDOW_DAYS)
    incoming_cursor = {"after_id": int(after_id)} if after_id else None

    counts: dict[str, int] = {"legs_examined": 0, **{v: 0 for v in LEG_VERDICTS}}
    samples: list[dict[str, Any]] = []

    # ---- the page --------------------------------------------------------
    page_sql = f"""
        SELECT min(fo.id)                  AS outcome_id,
               fm.id                       AS market_id,
               min(fo.external_id)         AS condition_id,
               min(fo.name)                AS outcome_name,
               min(fm.name)                AS market_name,
               min(fm.llm_sport_category)  AS category
        {POPULATION_FROM}
           AND (CAST(:sport AS text) IS NULL OR fm.llm_sport_category = CAST(:sport AS text))
         GROUP BY fm.id
        HAVING {POPULATION_HAVING}
           AND (CAST(:after_id AS bigint) IS NULL OR min(fo.id) > CAST(:after_id AS bigint))
         ORDER BY 1
         LIMIT CAST(:cap AS int)
    """
    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{TARGET_SELECT_BUDGET_SECONDS}s'",
            server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
            sql=page_sql,
            params={"after_id": after_id, "sport": sport, "cap": cap, "days": days},
        )
        page = result.fetchall()
    except ClientDeadlineExceeded as exc:
        await _safe_rollback(session)
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="paused_pool_timeout",
            reason=f"no pooled connection came free: {exc}",
            days=days,
        )
    # Its own arm, and its own terminal: "the pool was empty" and "the row was
    # locked" send an operator to different places.
    except Exception as exc:  # noqa: BLE001 — the page SELECT is the first thing
        await _safe_rollback(session)
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="paused_target_timeout",
            reason=f"page select did not finish: {type(exc).__name__}: {exc}",
            days=days,
        )

    if not page:
        out = _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="ok",
            reason=(
                f"no side-less settled legs remain in this population "
                f"(window: {days} days)"
            ),
            days=days,
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

                if not row["condition_id"]:
                    counts["no_condition_id"] += 1
                    continue

                market = found.get(row["condition_id"])
                if market is None:
                    counts["not_at_venue"] += 1
                    continue

                # 🔴 THE ORIENTATION GUARD. Index 0 is this leg's side only for a
                # single-market-branch row. A venue market carrying a
                # `group_item_title` is the DECOMPOSED writer's shape, where the
                # stored leg can be index 1 — taking index 0 there would print
                # the loser's name on a settled page with total confidence.
                # Measured 0 of 183 in this cohort; refused anyway, and counted,
                # because "it did not happen in the sample" is not a guarantee.
                if (getattr(market, "group_item_title", None) or "").strip():
                    counts["refused_grouped"] += 1
                    logger.warning(
                        "repair_polymarket_single_leg_label: outcome %s (market %s) "
                        "has venue group_item_title %r — refusing, index 0 is not "
                        "provably this leg's side",
                        row["outcome_id"],
                        row["market_id"],
                        market.group_item_title,
                    )
                    continue

                # The SHIPPED rule, given the venue's own question and falling
                # back to the stored market name. `_sub_market_side_label` is a
                # RESCUE: a blank token, a bare Yes/No, or a token echoing the
                # question all keep "Yes", so this may fail to improve a row but
                # can never guess a side.
                new_name = _sub_market_side_label(
                    market, 0, market.question or row["market_name"], "Yes"
                )
                if not new_name or new_name == row["outcome_name"]:
                    # The venue's own answer still names no side. Counted, not
                    # silent: a drain that "found nothing to do" must say how
                    # many times.
                    counts["unchanged"] += 1
                    continue

                planned.append({**row, "new_name": new_name})

            await asyncio.sleep(VENUE_PAUSE)
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001 — cleanup must not mask the real result
            logger.warning(
                "repair_polymarket_single_leg_label: venue client close failed"
            )

    # ---- collision refusal ----------------------------------------------
    # The population takes one leg per market, so two planned rows for one market
    # cannot occur by construction. Checked anyway and counted: the day the
    # population predicate is widened, this is the guard that stops the widening
    # from quietly printing the same side twice on one card.
    by_market: dict[int, list[dict[str, Any]]] = {}
    for p in planned:
        by_market.setdefault(p["market_id"], []).append(p)
    writable: list[dict[str, Any]] = []
    for market_id, group in by_market.items():
        names = [g["new_name"] for g in group]
        if len(names) != len(set(names)):
            counts["refused_collision"] += len(group)
            logger.warning(
                "repair_polymarket_single_leg_label: market %s would take the "
                "label %r on %d legs; refusing the whole group",
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
            f"(CAST(:id{i} AS bigint), CAST(:old{i} AS text), CAST(:new{i} AS text))"
            for i in range(len(writable))
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
                        "repair_polymarket_single_leg_label: outcome %s (market %s) "
                        "%r -> %r",
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
        # The cursor is EXCLUSIVE (`min(fo.id) > :after_id`), so it names the
        # last leg actually examined and the next call resumes at
        # `stopped_before`. When the very first batch failed, nothing was
        # examined and the cursor the operator handed in is returned unchanged —
        # a retry repeats the page rather than skipping the legs the venue
        # refused to answer for.
        resume_after = (
            last_examined if last_examined is not None else (after_id or None)
        )
        next_cursor = (
            {"after_id": int(resume_after)} if resume_after else incoming_cursor
        )
        terminal = "paused_venue" if venue_reason else "paused_deadline"
        scan_exhausted = False
    else:
        next_cursor = (
            {"after_id": int(last_examined)} if last_examined else incoming_cursor
        )
        terminal = "ok"
        # A short page means the population ran out under this cursor. It does
        # NOT mean the cohort is empty, and it does not speak for anything
        # outside the window — re-run `census` for that.
        scan_exhausted = len(rows) < cap

    # ---- the terminal count ---------------------------------------------
    remaining: Optional[int] = None
    remaining_measured = False
    # 🔴 CERT-681: A FAILED WRITE HAS ALREADY PAID ITS CLEANUP. Starting the
    # count anyway puts a SECOND cleanup on the same reserve, which is the
    # arithmetic that took the sibling rail's worst path past its wall. The
    # count is degradable by construction — it reports itself unmeasured and
    # never reports zero — and the page is paused anyway, so the operator is
    # about to re-invoke and get a fresh count for free.
    spent = time.monotonic() - started
    # The SERVER bound, derived so that the CLIENT bound wrapped around it still
    # fits under the wall. `client_db_budget_seconds(0)` is the pool slack the
    # helper adds; subtracting it here is what stops the count from overshooting
    # the wall by exactly that slack.
    count_budget = (
        ROUTER_WALL_SECONDS
        - spent
        - POST_LOOP_NON_COUNT_RESERVE_SECONDS
        - client_db_budget_seconds(0.0)
    )
    if write_terminal is None and count_budget >= REMAINING_COUNT_MIN_BUDGET_SECONDS:
        count_sql = f"""
            SELECT count(*)
              FROM (
                    SELECT fm.id
                    {POPULATION_FROM}
                       AND (CAST(:sport AS text) IS NULL
                            OR fm.llm_sport_category = CAST(:sport AS text))
                     GROUP BY fm.id
                    HAVING {POPULATION_HAVING}
                   ) t
        """
        try:
            result = await _bounded_statement(
                session,
                timeout_literal=f"'{int(count_budget * 1000)}ms'",
                server_budget_s=count_budget,
                sql=count_sql,
                params={"sport": sport, "days": days},
            )
            remaining = int(result.scalar_one())
            remaining_measured = True
        except Exception:  # noqa: BLE001 — degradable: unmeasured, never zero
            await _safe_rollback(session)
            remaining = None
            remaining_measured = False

    return {
        "repair": "polymarket-single-leg-label",
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
        "window_days": days,
        "elapsed_s": round(time.monotonic() - started, 2),
    }
