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

THE SCOPE THIS RAIL CAN LOOK AT, AND WHY IT STILL ONLY WRITES INSIDE ONE OF THEM
--------------------------------------------------------------------------------
#7701, rung 1. ``status_scope`` selects which side of the status line the pager
reads: ``open`` (the default, this rail's original and only writable cohort) or
``not_open``, the EXACT complement — the same predicate ``_out_of_scope_legs``
counts, so the widened page and that counter can never describe two different
populations. On 2026-09-21 the open side measured **0** and the complement
**25,469 legs across 25,402 markets**, every one still printing the whole matchup
as its own price label.

🔴 ``not_open`` IS READ-ONLY AND THE REFUSAL IS NAMED, NOT IMPLIED. Two separate
reasons, either one sufficient. First, the venue is the only place the correct
label exists (above) and **how far back Gamma answers for a resolved market is
unmeasured** — Kalshi's analogue is a measured constant in
``app/utils/kalshi_retention.py`` and Polymarket has no equivalent. A drain that
applied across an unmeasured retention edge would count the purged tail
``not_at_venue`` and stop, which reads exactly like a finished drain. Measuring
that edge is what this rung is FOR. Second, this rail has no undo receipt: the
sibling settled drain (#6739) stages one before it writes, and 25,469 rows is not
the population to debut an unreversible write on. So the widened scope is a
LOOKING instrument at this rung; the write half is rung 2, behind the bound this
one measures.

``band`` — ``MIN-MAX``, two ages in days, youngest-first — is how the bound gets
read. It bounds ``fm.resolution_date``, so one call samples one age slice and its
``not_at_venue`` count IS that slice's retention reading. Six calls are the curve.

🔴 A BANDED PAGE CAN NEVER REPORT ``scan_exhausted``. Band exhaustion and
population exhaustion are different answers and this rail returns them as two
fields (#3257's ruling, learned on the Kalshi rail): a banded page that ran out
of rows means "this slice is empty", and reporting that as a drained scope is the
same lie ``out_of_scope_legs`` was added to stop one layer up.

🔴 A BAND CANNOT SEE A ROW WHOSE ``resolution_date`` IS NULL. Every comparison
against NULL is unknown, so an age band silently excludes the age-unknown tail —
which is why the UNBANDED page reports those rows in an ``unknown`` age bucket
rather than letting them vanish between slices. ``by_age_bucket`` is computed
from the rows the page actually examined, not from a second query, so it costs
nothing and it is the control that proves the band bound at all.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
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
#:
#: 10 rather than the sibling rail's 15, because the post-loop reserve here has
#: to pay for a CLEANUP (below) and the loop is cheap: a full 120-leg page is
#: three batch pairs, ~1.9s of measured venue time plus 1.05s of pause. 10s is
#: over 3x that, so a full page still normally COMPLETES.
DEADLINE_SECONDS = 10

#: 🔴 WHAT ONE `_safe_rollback` COSTS. THIS IS THE CERT-681 LINE.
#:
#: CERT-681 blocked the sibling rail's round two on exactly this arithmetic: a
#: failed final write pays a cleanup, the rail then unconditionally started its
#: terminal count, a failed count paid a SECOND cleanup, and the post-loop
#: reserve budgeted only one. Declared worst path 31.10s against a 30s wall —
#: the H12-with-no-body the whole budget exists to prevent, arrived at through
#: the failure path rather than the happy one.
#:
#: Two things follow, and both are enforced rather than described. First, this
#: reserve exists at all. Second, ``repair()`` SKIPS the terminal count when the
#: write has already failed, so at most ONE cleanup is ever on the worst path —
#: a guard asserts that, because "we only clean up once" is the kind of claim
#: that stays true until someone adds a branch.
#:
#: Sized from CERT-674's own reproduction against a real ``QueuePool``: the
#: bounded rollback (``ROLLBACK_BUDGET_SECONDS``, 0.5s in the sibling) plus the
#: invalidate, which the dialect's ``close(timeout=2)`` bounds at ~2s even where
#: this rail does not. 3.0s covers the pair. Deliberately NOT derived from the
#: sibling's constants by import: the invalidate's own budget exists only on the
#: Q498 branch, and a number that silently changes meaning when a sibling merges
#: is worse than one that is stated and guarded here.
CLEANUP_RESERVE_SECONDS = 3.0

#: Response serialization plus the request dependency's own commit, which runs
#: after the handler has returned and so cannot be observed from inside it.
SERIALIZATION_RESERVE_SECONDS = 0.5

#: Time reserved for everything that happens AFTER the loop's last fetch: the
#: single bulk write, its commit, at most one cleanup, the ``remaining_legs``
#: terminal count, response serialization, and the dependency's commit.
POST_LOOP_RESERVE_SECONDS = 8.0

#: The slice of the reserve that is NOT the terminal count. The count is armed
#: with whatever is left of the wall once this is set aside, so an over-running
#: loop shortens the count's timeout instead of borrowing against work that
#: still has to run. It must cover the CLIENT bound of both post-loop database
#: units — the update and the commit — plus one cleanup and the serialization:
#: "the failure path costs more than the success path" is the easy thing to
#: forget when sizing a budget from the happy case, and it is what CERT-681
#: withheld a token over. A guard asserts the DERIVED client bounds fit inside
#: it, rather than trusting five numbers to be edited together.
POST_LOOP_NON_COUNT_RESERVE_SECONDS = 6.5

#: Bound on the page SELECT. It does not widen the worst case: ``started`` is
#: captured BEFORE this query, so a slow SELECT does not add to the total, it
#: just leaves the loop less room and the first deadline check stops it. That
#: holds only while this stays at or under ``DEADLINE_SECONDS``, which a guard
#: asserts. Measured 152ms for the filtered form and ~2.5s for the full
#: per-category GROUP BY on production, so 8s is over 3x the worst observed.
TARGET_SELECT_BUDGET_SECONDS = 8.0

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

#: 🔴 #7701 rung 3a: how many EXTRA legs a capped page may take on so its trailing
#: market arrives whole. The collision guard groups by market and is only sound on
#: a complete group, but `LIMIT` cuts the leg stream wherever 120 falls, not on a
#: market boundary. Measured 2026-09-21: the widened cohort is 25,469 legs across
#: 25,402 markets, so the surplus is ~67 legs in total and the realistic top-up is
#: ONE row. The cap is a rail against a pathological market, not a working bound —
#: a market that overruns it is refused by name rather than written half-checked.
GROUP_COMPLETION_CAP = 500

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

#: Bound on the #7701 rung 2 dangling-cursor probe. A single primary-key lookup
#: on ``futures_outcomes``, run ONLY when a page came back empty under an
#: ``?after_id=`` — so at most once per drain, with the venue budget untouched.
#: Small because a pk lookup that needs longer than this is a sick database, not
#: a slow query, and the caller fails closed either way.
CURSOR_PROBE_BUDGET_SECONDS = 2

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
#:
#: 🔴 THAT REASONING IS SCOPED TO THE COHORT IT WAS MEASURED ON, AND #7701 RUNG 2
#: WALKED OUT OF IT. Being non-indexable is what makes the NARROW
#: ``status = 'open'`` scope probe one index, and it is also exactly what makes
#: the WIDENED scope a double sequential scan: with ~463K resolved Polymarket
#: markets on the inner side the planner stops probing and hash-joins 4.34M
#: outcomes against them (measured 2026-09-23: EXPLAIN cost **603,538**, up from
#: 451's 483,632 on 2026-09-21 — it degrades on its own as the tables grow).
#: The predicate is still right. What changed is which side the join must be
#: DRIVEN from; see ``_page_sql_for`` below. Do not "fix" this by restoring
#: ``=`` — that is the 86,006 plan, and it was measured worse.
def collapsed_leg_predicate(outcome_alias: str = "fo") -> str:
    """The population rule, written once, rendered under whichever alias asks.

    The census, ``_out_of_scope_legs`` and the pager must not be able to
    disagree about what a collapsed leg is, and rung 2 needs the same sentence
    under a second alias because the pager now names the outcome table inside a
    LATERAL. A function rather than a second constant, so there is exactly one
    place the rule can be edited and no way to edit one copy of it.
    """
    return f"{outcome_alias}.name IS NOT DISTINCT FROM fm.name"


COLLAPSED_LEG_PREDICATE = collapsed_leg_predicate()

#: 🔴 THE SCOPE, WRITTEN ONCE BESIDE THE POPULATION. This rail was built for the
#: cohort as it stood on 2026-09-01: markets we still held ``open`` that the
#: venue had already closed. It is NOT the whole defect, and the difference is
#: not academic — measured on production 2026-09-21, the in-scope population is
#: **0** and the out-of-scope one is **25,469 legs across 25,402 markets**, every
#: one of them still serving the whole matchup as its own price label.
#:
#: The 1,153 legs this rail was built to drain never drained. They RESOLVED, and
#: a resolved market leaves this rail's scope without any of its rows being
#: repaired — while new ones resolve into the gap behind them. So an empty page
#: here means "the scope is empty", which is a different sentence from "the
#: defect is gone", and `_out_of_scope_legs` exists so the rail can tell an
#: operator which one it is (gotcha #53 — an empty answer is not an absence).
IN_SCOPE_STATUS_SQL = "fm.status = 'open'"
OUT_OF_SCOPE_STATUS_SQL = "fm.status IS DISTINCT FROM 'open'"

#: The two cohorts ``status_scope`` can address, keyed by the name an operator
#: types. Built FROM the two constants above rather than restating them, so the
#: widened page and ``_out_of_scope_legs`` cannot drift into describing
#: different populations — the whole argument for the counter is that the two
#: numbers add up to the defect.
#:
#: ``not_open`` and not ``resolved``: the complement is `status IS DISTINCT FROM
#: 'open'`, which also admits `suspended`. Naming it ``resolved`` would be a
#: claim about what those rows are, and the page reports `by_status` from the
#: rows it examined so the operator reads that rather than trusting a label.
STATUS_SCOPE_SQL = {
    "open": IN_SCOPE_STATUS_SQL,
    "not_open": OUT_OF_SCOPE_STATUS_SQL,
}

#: The only scope this rail may WRITE in. See the module docstring: Gamma's
#: retention edge for resolved markets is unmeasured and this rail stages no undo
#: receipt, so the widened scope is a looking instrument until both change.
WRITABLE_STATUS_SCOPE = "open"

DEFAULT_STATUS_SCOPE = "open"

#: Upper edges, in days, of the age buckets the examined rows are folded into.
#: Wide and few on purpose: this is a retention CURVE read from a 120-row sample
#: per call, and a bucket narrower than the sample's own noise would invite a
#: reader to see a cliff that is three rows.
AGE_BUCKET_EDGES = (30, 60, 90, 180, 365)

#: The bucket for a row whose ``resolution_date`` is NULL. NOT folded into the
#: oldest bucket: "we do not know when this resolved" and "this resolved over a
#: year ago" are different facts, and collapsing the first into the second would
#: manufacture the very retention reading this rung exists to measure.
AGE_BUCKET_UNKNOWN = "unknown"

#: ``?band=30-60``. Two whole ages in days, youngest edge first.
_BAND_FORM = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")

#: Verdicts a single leg can reach. Every one is COUNTED — ruling 054: an
#: exclusion is counted, not skipped, and each zero state gets its own terminal
#: rather than one silent success (gotcha #53).
LEG_VERDICTS = (
    "relabelled",
    "unchanged",
    "not_at_venue",
    "no_condition_id",
    "refused_collision",
    # #7701 rung 3a: the market arrived PARTIAL, so distinctness could not be
    # tested at all. Its own verdict, not folded into `refused_collision`: one
    # says two legs would collide, the other says we could not tell, and an
    # operator reading a drain needs to know which.
    "refused_group_incomplete",
    "raced",
)


class VenueUnavailable(Exception):
    """The venue did not answer a batch: 429, 5xx, or a timeout.

    Distinct from "the market is not there". Nothing is written for a batch that
    raises this and the cursor RETRIES it — a throttled fetch treated as an
    empty answer would relabel nothing and report the cohort drained
    (gotcha #36, and gotcha #53's "an empty 200 is not an absence").
    """


class SelectorRefused(Exception):
    """A ``status_scope`` or ``band`` this rail will not run, refused BY NAME.

    Never a silent fallback to the default. Every one of these mistakes produces
    a page that looks exactly like a correct one — an unrecognised scope dropped
    to ``open`` returns a truthful empty page for a cohort of 0 and reads as "the
    resolved cohort is clean", which is the strongest possible wrong answer this
    rail can give (gotcha #53, one layer further out).
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_status_scope(status_scope: Optional[str]) -> str:
    """``None`` -> the default cohort; a name -> that cohort; anything else raises."""
    if status_scope is None:
        return DEFAULT_STATUS_SCOPE
    key = str(status_scope).strip().lower()
    if key not in STATUS_SCOPE_SQL:
        raise SelectorRefused(
            "STATUS_SCOPE_UNKNOWN",
            f"?status_scope={status_scope!r} is not a cohort this rail knows. "
            f"Choose one of {sorted(STATUS_SCOPE_SQL)}. It is refused rather "
            "than defaulted: a misspelling quietly served from the `open` "
            "cohort — measured empty on 2026-09-21 — would answer 'nothing to "
            "repair' for a population of 25,469.",
        )
    return key


def parse_band(band: Optional[str]) -> Optional[tuple[int, int]]:
    """``"30-60"`` -> ``(30, 60)``, two ages in DAYS, youngest edge first.

    🔴 DELIBERATELY NOT :func:`app.tasks.repair_kalshi_fabricated_loss.parse_band`,
    WHICH IS THE SAME GRAMMAR AND THE WRONG RULE HERE. That one refuses any band
    reaching past ``PROVABLY_PURGED_AGE_DAYS`` — correct there, because Kalshi's
    retention floor is a MEASURED constant and a band over it would return an
    empty page that reads as "nothing to repair". This cohort has no such
    constant: the whole purpose of banding here is to find where Polymarket's
    edge is, so a floor refusal would refuse exactly the slices worth reading.
    Importing it would have made this rail unable to ask its own question, and
    the failure would have looked like an empty tail.

    (Same reasoning as ``CLEANUP_RESERVE_SECONDS`` above: a number that silently
    changes meaning when a sibling rail re-measures its own venue is worse than
    one stated and guarded here.)

    Raises :class:`SelectorRefused`, and never returns ``None`` for a value that
    was supplied — a band silently dropped walks the whole population while the
    response echoes the band the operator asked for.
    """
    if band is None:
        return None
    m = _BAND_FORM.match(str(band))
    if not m:
        raise SelectorRefused(
            "BAND_UNPARSEABLE",
            f"?band={band!r} is not two whole ages in days. Write it "
            "youngest-first as MIN-MAX, e.g. ?band=30-60 for the second month "
            "after resolution.",
        )
    low, high = int(m.group(1)), int(m.group(2))
    if low >= high:
        raise SelectorRefused(
            "BAND_INVERTED",
            f"?band={band!r} has MIN >= MAX ({low} >= {high}). Both numbers are "
            "AGES IN DAYS, so the second one is the OLDER edge.",
        )
    return low, high


def age_bucket(resolution_date: Optional[datetime], now: datetime) -> str:
    """Fold one row's age into a named bucket. ``now`` is passed, never read.

    The clock is an argument because a bucket boundary computed from a live
    ``now()`` inside a test is a guard that changes its own answer as it runs
    (Hot List #44). Production passes one instant for the whole page, so every
    row of a page is bucketed against the same clock.
    """
    if resolution_date is None:
        return AGE_BUCKET_UNKNOWN
    when = resolution_date
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age_days = (now - when).total_seconds() / 86400.0
    if age_days < 0:
        # A resolution date in the FUTURE on a market we no longer hold open.
        # Its own bucket, because folding it into `0-30` would report a row that
        # has not reached its own close as a fresh resolution.
        return "future_date"
    # A running lower bound rather than `EDGES.index(edge) - 1`, which wraps to
    # the LAST edge on the first bucket and would label 0-30 as "365-30".
    low = 0
    for edge in AGE_BUCKET_EDGES:
        if age_days < edge:
            return f"{low}-{edge}"
        low = edge
    return f"{AGE_BUCKET_EDGES[-1]}+"


def budget_headroom_seconds() -> float:
    """Seconds left under the router wall in the rail's WORST case.

    The deadline is checked at the top of the loop, so after it passes the rail
    may still start one whole batch pair and one pause; and after that the write,
    its commit, ONE cleanup, the terminal count, serialization and the
    dependency's commit still run. The cleanup is in that list because of
    CERT-681 — see ``CLEANUP_RESERVE_SECONDS``. It appears once and not twice
    because ``repair()`` skips the count after a failed write, which
    ``test_a_failed_write_does_not_also_start_the_terminal_count`` pins.

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


def _refused(
    *,
    incoming_cursor: Optional[dict[str, Any]],
    started: float,
    code: str,
    reason: str,
) -> dict[str, Any]:
    """The response for a call this rail declined to run at all.

    Shares ``_paused_before_examining``'s zeroed shape — nothing was examined and
    the operator's cursor comes back untouched — but its terminal is ``refused``
    and not ``paused_*``. The distinction is the operator's next move: a pause
    says "run me again", a refusal says "your selector is wrong and re-running it
    will do this again". ``scan_exhausted`` is False for the same reason every
    other unexamined page sets it False.
    """
    out = _paused_before_examining(
        incoming_cursor=incoming_cursor,
        started=started,
        terminal="refused",
        reason=reason,
    )
    out["refused_code"] = code
    return out


# ---------------------------------------------------------------------------
# Census — read-only. Never writes; `apply` is accepted and ignored.
# ---------------------------------------------------------------------------


async def _out_of_scope_legs(
    session, sport: str = None, budget_s: float = None
) -> Optional[dict[str, int]]:
    """Count the collapsed legs this rail's scope EXCLUDES, or say it could not.

    The same population predicate, the same source, the complement of the same
    status test — so the two numbers add up to the whole defect and cannot drift
    apart the way two hand-written cohorts would.

    🔴 RETURNS ``None``, NEVER ``{"legs": 0}``, WHEN THE COUNT DOES NOT FINISH.
    The entire point of this counter is to stop an empty in-scope page reading
    as "the defect is gone"; a counter that answered ``0`` on a timeout would
    reintroduce exactly that lie one layer down (gotcha #53, and the
    ``remaining_legs_measured`` flag beside it for the same reason).
    """
    budget = float(budget_s or CENSUS_STATEMENT_TIMEOUT_SECONDS)
    sql = f"""
        SELECT count(*) AS legs, count(DISTINCT fm.id) AS markets
          FROM futures_markets fm
          JOIN futures_outcomes fo
            ON fo.market_id = fm.id
           AND {COLLAPSED_LEG_PREDICATE}
         WHERE fm.source = 'polymarket'
           AND {OUT_OF_SCOPE_STATUS_SQL}
           AND (CAST(:sport AS text) IS NULL
                OR fm.llm_sport_category = CAST(:sport AS text))
    """
    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{int(budget * 1000)}ms'",
            server_budget_s=budget,
            sql=sql,
            params={"sport": sport},
        )
        row = result.one()
    except Exception:  # noqa: BLE001 — degradable: unmeasured, never zero
        await _safe_rollback(session)
        return None
    return {"legs": int(row[0]), "markets": int(row[1])}


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
           AND {IN_SCOPE_STATUS_SQL}
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

    # 🔴 THE FIELDS THAT STOP `total_legs: 0` READING AS "Q499 IS FINISHED".
    # Additive, so every existing reader of the three fields above is unchanged:
    # they still describe this rail's scope and only its scope. What they could
    # never say on their own is that the cohort LEFT that scope rather than being
    # repaired — on 2026-09-21 the census answered a confident
    # `measured: true, total_legs: 0` while 25,469 collapsed legs sat one status
    # away, and the rail had never successfully run a single page select.
    out_of_scope = await _out_of_scope_legs(session)
    out["out_of_scope_measured"] = out_of_scope is not None
    out["out_of_scope_legs"] = out_of_scope["legs"] if out_of_scope else None
    out["out_of_scope_markets"] = out_of_scope["markets"] if out_of_scope else None
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
    status_scope: str = None,
    band: str = None,
) -> dict[str, Any]:
    """Re-ask the venue for each side-less leg and store the shipped label.

    ``sport`` filters ``llm_sport_category`` — an operator draining the tennis
    cohort before the Setka backlog is choosing an order, not a different
    population. ``after_id`` is a keyset cursor on ``futures_outcomes.id``.
    Since #7701 rung 2 the page is ORDERED by ``(fm.id, fo.id)`` and the market
    half of the keyset is derived from ``after_id`` inside the statement, so the
    operator-facing contract is unchanged — one leg id, from ``next_cursor`` —
    while the walk itself runs down the market side. A cursor naming a leg that
    no longer exists is REFUSED (``CURSOR_DANGLING``) rather than answered with
    an empty page, because those two are the same page and only one of them
    means the drain is finished.

    ``status_scope`` (``open`` default, or ``not_open``) and ``band``
    (``MIN-MAX`` ages in days over ``fm.resolution_date``) are #7701 rung 1: they
    let the rail LOOK at the resolved complement and read Gamma's retention edge
    one age slice at a time. The widened scope never writes — see the module
    docstring for the two independent reasons, and
    ``STATUS_SCOPE_APPLY_REFUSED`` below for the refusal itself.
    """
    started = time.monotonic()
    cap = min(int(limit), APPLY_LEG_CAP) if limit else APPLY_LEG_CAP
    # `is not None`, not truthiness: `?after_id=0` is a cursor the operator
    # actually typed, and the refusal below has to be able to echo it back.
    incoming_cursor = {"after_id": int(after_id)} if after_id is not None else None

    # ---- the selectors, validated BEFORE anything is read ----------------
    # Ordered so the most dangerous misreading is refused first: a scope the
    # rail does not know would otherwise be served from the cohort measured
    # EMPTY, and an empty page is the one answer that reads as success.
    try:
        scope = parse_status_scope(status_scope)
        band_ages = parse_band(band)
    except SelectorRefused as exc:
        return _refused(
            incoming_cursor=incoming_cursor,
            started=started,
            code=exc.code,
            reason=exc.message,
        )

    if apply and scope != WRITABLE_STATUS_SCOPE:
        return _refused(
            incoming_cursor=incoming_cursor,
            started=started,
            code="STATUS_SCOPE_APPLY_REFUSED",
            reason=(
                f"?status_scope={scope!r} is READ-ONLY at this rung (#7701). The "
                "correct label exists only at the venue and Polymarket's "
                "retention edge for resolved markets is unmeasured, so an apply "
                "across it would count the purged tail `not_at_venue` and stop, "
                "which is indistinguishable from a finished drain; and this rail "
                "stages no undo receipt, which 25,469 rows is not the population "
                "to debut. Re-run with apply=false to read the bound, which is "
                "what this scope is for."
            ),
        )

    if apply and band_ages is not None:
        return _refused(
            incoming_cursor=incoming_cursor,
            started=started,
            code="BAND_ON_APPLY_REFUSED",
            reason=(
                f"?band={band!r} is a sampling selector for reading the retention "
                "curve, not a paging order for a write. A banded apply drains one "
                "age slice and then reports that slice running out, which an "
                "operator reads as the population being drained."
            ),
        )

    # 🔴 #7701 rung 3a: `?after_id=0` IS A CURSOR IN SQL AND AN ABSENT ONE IN
    # PYTHON, AND THAT DISAGREEMENT REPORTS A WALK THAT EXAMINED NOTHING AS A
    # FINISHED DRAIN. The page select tests `CAST(:after_id AS bigint) IS NULL`,
    # which `0` is not, so it takes the cursor arm: `cursor_market` resolves to
    # NULL, every comparison against NULL is NULL, and the page comes back empty.
    # Python then tested the SAME parameter for truthiness — `if after_id` — which
    # `0` is falsy for, so the `CURSOR_DANGLING` probe below was skipped and the
    # empty page fell through to the branch that says `scan_exhausted`. The route
    # hands `0` straight through (`admin_repairs.py` filters on `is not None`, and
    # the Query has no `ge=`), and initialising a cursor variable to 0 is the
    # ordinary way to script a 212-page drain, so this is the FIRST call such a
    # script makes. Refused here, under the name a missing row already gets, which
    # is what lets the three tests below be `is not None`.
    if after_id is not None and int(after_id) < 1:
        return _refused(
            incoming_cursor=incoming_cursor,
            started=started,
            code="CURSOR_DANGLING",
            reason=(
                f"?after_id={after_id} is not a row id — `futures_outcomes.id` "
                "starts at 1 — so the keyset has no market to resume from and the "
                "page would be empty for that reason ALONE. It is not an exhausted "
                "scan. Omit ?after_id= to start the walk, or hand the `next_cursor` "
                "from the last call that examined a leg."
            ),
        )

    if band_ages is not None and after_id is not None:
        # CERT-1935 on the sibling rail: a band's two ages are measured from an
        # instant, and re-measuring them from today on every call moves the old
        # edge forward while the keyset stays put — the rows sharing the cursor's
        # own timestamp then sit after the cursor AND outside the new window, so
        # no page of that walk ever selects them again, and it reports as the
        # band being exhausted. That rail closed it with a `band_as_of` anchor
        # minted on page one. This rung does not need a banded WALK — one page
        # per slice is the sample — so the case is REFUSED rather than
        # implemented subtly wrong.
        return _refused(
            incoming_cursor=incoming_cursor,
            started=started,
            code="BAND_RESUME_UNSUPPORTED",
            reason=(
                f"?band={band!r} with ?after_id={after_id} is a banded RESUME, "
                "which needs the `band_as_of` anchor this rung does not mint "
                "(CERT-1935): re-measuring the band from today while the cursor "
                "stays put strands every row sharing the cursor's timestamp and "
                "reports it as the band being exhausted. One unpaged page per "
                "band is the sample this rung is for."
            ),
        )

    counts: dict[str, int] = {"legs_examined": 0, **{v: 0 for v in LEG_VERDICTS}}
    samples: list[dict[str, Any]] = []

    # ---- the page --------------------------------------------------------
    # 🔴 `CAST(x AS t)`, NOT THE POSTFIX `x::t` FORM, AND NOT AS A STYLE CHOICE.
    # SQLAlchemy's `text()` refuses to read a bind name that runs into a colon —
    # the lookahead exists so a postfix cast is not eaten as part of the name —
    # so the whole token is passed to Postgres as literal SQL with NO parameter
    # bound to it, and the statement dies on `syntax error at or near` a colon.
    # That is what this rail did on every invocation from 2026-09-05 to
    # 2026-09-21 (#7167): never one completed work selection, reported as
    # `paused_target_timeout`. Both halves of every pair are cast because
    # asyncpg prepares with no parameter types and the first occurrence fixes
    # the type.
    #
    # The sibling `repair_kalshi_fabricated_loss.py` and the class guard
    # `tests/test_untyped_bind_in_is_null_guard.py` both cited THESE lines as
    # the exemplar that got it right. They did not.
    #
    # This explanation is a PYTHON comment and must stay one. Inside the SQL a
    # `--` line is a comment to Postgres but not to SQLAlchemy, which still
    # reads any colon-prefixed word in it as a bind nobody supplies; and if
    # anything ever collapses the statement to a single line, a `--` comment
    # silently comments out the rest of the query.
    #
    # 🔴 THE BAND'S MAX IS THE OLDER EDGE, SO IT IS A LOWER BOUND ON THE DATE.
    # Reading the pair as "max age => max date" inverts the window and returns
    # the slice next to the one asked for — a page that looks entirely
    # plausible. Both bounds are on the SAME column the buckets are folded from,
    # so `by_age_bucket` is a direct control on this clause having bound at all.
    # 🔴 #7701 RUNG 2: THE JOIN IS DRIVEN FROM THE MARKET SIDE, AND EVERY PIECE
    # OF THAT SENTENCE IS LOAD BEARING. Measured on production 2026-09-23,
    # widened scope, 120-leg page:
    #
    #     driven by            head page   deep resume   terminal page
    #     planner (was)        14.0s / timeout on every page, cost 603,538
    #     futures_outcomes     626ms       —             20.5s  ⛔
    #     futures_markets      102ms       738ms         2.57s  ✅
    #
    # The arithmetic behind it: the cohort is ~1 collapsed leg per 20 resolved
    # Polymarket markets but ~1 per 427 outcomes, and there are 4.34M outcomes
    # against 463K markets. Driving from the smaller, denser side is ~9x less
    # keyspace at ~20x the hit density, and that margin is what buys the
    # TERMINAL page — the one that must scan to the end of the keyspace to prove
    # the drain is finished. An outcome-driven scan is quick at the head and
    # needs 20.5s to walk the 1,251,774 outcome rows above the last collapsed
    # leg, so it could never say "done" inside the budget. A rail that cannot
    # report exhaustion is the rung-1 failure mode wearing the opposite costume.
    #
    # 🔴 `OFFSET 0` IS AN OPTIMIZATION FENCE AND DELETING IT SILENTLY RESTORES
    # THE 603,538 PLAN. Postgres pulls a simple LATERAL subquery up into the
    # outer join and re-derives the identical hash join — measured, the plan is
    # byte-identical to the one above this change. `OFFSET 0` blocks the pull-up
    # and nothing else; it reads like a no-op, it changes no row, and no test
    # that only checks results can see it go. `test_the_offset_0_fence_is_load_bearing`
    # pins the token itself for that reason.
    #
    # 🔴 THE `fm.id >=` BOUND IS DELIBERATELY REDUNDANT WITH THE ROW-WISE
    # COMPARISON BESIDE IT. The row-wise `(fm.id, fo.id) > (...)` is correct on
    # its own but cannot be an index condition, because `fo.id` is produced by
    # the LATERAL — so a resume was applied as a FILTER and re-walked the whole
    # market keyspace from zero: 302,453 markets and 5.1s at a mid-cohort
    # cursor. Adding the scalar `fm.id >=` gives the pk scan a range start
    # (`Index Cond: (id >= (InitPlan 1).col1)`) and the same resume walks 11,652
    # markets in 738ms. Both clauses stay: the bound makes it fast, the row-wise
    # comparison makes it correct.
    #
    # 🔴 ORDERING BY `(fm.id, fo.id)` IS WHAT MAKES A SPLIT MARKET SAFE. The
    # cursor stays a single `?after_id=` on `futures_outcomes.id` — unchanged
    # contract, no new dispatcher parameter — and the market half is derived
    # from it in the statement. Because the order is total over the cohort, a
    # market whose legs straddle a page boundary (67 of the 25,402 hold more
    # than one collapsed leg) resumes at its own next leg rather than being
    # stepped over, and the SAME mechanism carries the mid-market venue stop
    # that `last_examined` already records. There is no trimming rule to get
    # wrong because there is no page to trim.
    cursor_market = (
        "(SELECT c.market_id FROM futures_outcomes c "
        "WHERE c.id = CAST(:after_id AS bigint))"
    )
    page_sql = f"""
        SELECT fo.id           AS outcome_id,
               fo.market_id    AS market_id,
               fo.external_id  AS condition_id,
               fo.name         AS outcome_name,
               fm.name         AS market_name,
               fm.llm_sport_category AS category,
               fm.resolution_date    AS resolution_date,
               fm.status             AS market_status
          FROM futures_markets fm
          JOIN LATERAL (
                 SELECT leg.id          AS id,
                        leg.market_id   AS market_id,
                        leg.external_id AS external_id,
                        leg.name        AS name
                   FROM futures_outcomes leg
                  WHERE leg.market_id = fm.id
                    AND {collapsed_leg_predicate("leg")}
                 OFFSET 0
               ) fo ON TRUE
         WHERE fm.source = 'polymarket'
           AND {STATUS_SCOPE_SQL[scope]}
           AND (CAST(:after_id AS bigint) IS NULL
                OR (fm.id >= {cursor_market}
                    AND (fm.id, fo.id) > ({cursor_market},
                                          CAST(:after_id AS bigint))))
           AND (CAST(:sport AS text) IS NULL
                OR fm.llm_sport_category = CAST(:sport AS text))
           AND (CAST(:band_max_age AS double precision) IS NULL
                OR fm.resolution_date >= NOW()
                   - (CAST(:band_max_age AS double precision) * INTERVAL '1 day'))
           AND (CAST(:band_min_age AS double precision) IS NULL
                OR fm.resolution_date <= NOW()
                   - (CAST(:band_min_age AS double precision) * INTERVAL '1 day'))
         ORDER BY fm.id, fo.id
         LIMIT CAST(:cap AS int)
    """
    try:
        result = await _bounded_statement(
            session,
            timeout_literal=f"'{TARGET_SELECT_BUDGET_SECONDS}s'",
            server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
            sql=page_sql,
            params={
                "after_id": after_id,
                "sport": sport,
                "cap": cap,
                "band_min_age": band_ages[0] if band_ages else None,
                "band_max_age": band_ages[1] if band_ages else None,
            },
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
    # Its own arm, and its own terminal: "the pool was empty" and "the row was
    # locked" send an operator to different places. (This comment is also load
    # bearing for `scan_mutation_residue.py` Pass B — without a line here, the
    # closing paren above plus the bare `noqa` below reproduce
    # `typeahead_outcome_arm_mutations:M2-NO-LIMIT`'s replacement literal
    # verbatim and this file reads as mutation residue. Do not delete it.)
    except Exception as exc:  # noqa: BLE001 — the page SELECT is the first thing
        await _safe_rollback(session)
        return _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="paused_target_timeout",
            reason=f"page select did not finish: {type(exc).__name__}: {exc}",
        )

    # 🔴 #7701 rung 3a: COMPLETE THE TRAILING MARKET. The collision guard below
    # groups the page by market and refuses a market whose legs would take the
    # same label — but `LIMIT :cap` cuts the leg stream wherever 120 falls, and
    # nothing aligns that cut to a market boundary. A market whose two collapsed
    # legs straddle the cut is seen as two groups of one, each trivially distinct,
    # so BOTH legs are written the same label and `refused_collision` stays 0: the
    # guard is not weakened at the boundary, it is bypassed, silently. Topping the
    # page up to the end of its last market is what keeps the common case whole
    # AND keeps the walk moving; the completeness test at the guard itself is what
    # catches every other way a group can arrive partial.
    overrun_market: Optional[int] = None
    if page and len(page) >= cap:
        topup_sql = f"""
            SELECT leg.id, leg.market_id, leg.external_id, leg.name,
                   fm.name, fm.llm_sport_category, fm.resolution_date, fm.status
              FROM futures_markets fm
              JOIN futures_outcomes leg ON leg.market_id = fm.id
             WHERE fm.id = CAST(:mid AS bigint)
               AND leg.id > CAST(:last_leg AS bigint)
               AND {collapsed_leg_predicate("leg")}
             ORDER BY leg.id
             LIMIT CAST(:topup_cap AS int)
        """
        try:
            topup = await _bounded_statement(
                session,
                timeout_literal=f"'{TARGET_SELECT_BUDGET_SECONDS}s'",
                server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
                sql=topup_sql,
                params={
                    "mid": int(page[-1][1]),
                    "last_leg": int(page[-1][0]),
                    "topup_cap": GROUP_COMPLETION_CAP,
                },
            )
            tail = topup.fetchall()
        except Exception as exc:  # noqa: BLE001 — see FAILS CLOSED below
            await _safe_rollback(session)
            return _paused_before_examining(
                incoming_cursor=incoming_cursor,
                started=started,
                terminal="paused_target_timeout",
                reason=(
                    "the page was read but its trailing market could not be "
                    "completed, and writing a market the collision guard has only "
                    "half of is the defect this rung closes: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        if tail:
            # Only the LAST market can be short here, so one probe completes the
            # page. A tail that fills the cap has not proven it is the whole
            # market, so that market is named and the guard refuses it below.
            if len(tail) >= GROUP_COMPLETION_CAP:
                overrun_market = int(page[-1][1])
            page = list(page) + list(tail)

    if not page and after_id is not None:
        # 🔴 #7701 RUNG 2: AN UNRESOLVABLE CURSOR AND A DRAINED COHORT RETURN THE
        # SAME EMPTY PAGE, AND ONLY ONE OF THEM MEANS "FINISHED". Rung 2 derives
        # the market half of the keyset from `?after_id=` inside the statement
        # (see `cursor_market` above). If that outcome row has gone, the scalar
        # subquery is NULL, every comparison against it is NULL, the page is
        # empty — and the branches below would read that as the scope being
        # exhausted and bank a finish this rail never earned. That is gotcha #53
        # in the one place it would cost the most: at the END of a 212-page
        # drain, where "done" is the answer everybody is waiting for.
        #
        # The check is one primary-key lookup and it runs ONLY on the empty-page
        # path — once per drain, with the whole venue budget unspent — so the
        # common case pays nothing for it. It FAILS CLOSED: if the lookup itself
        # cannot complete we pause rather than fall through, because "I could
        # not check" is not "the cursor was fine".
        try:
            probe = await _bounded_statement(
                session,
                timeout_literal=f"'{CURSOR_PROBE_BUDGET_SECONDS}s'",
                server_budget_s=CURSOR_PROBE_BUDGET_SECONDS,
                sql=(
                    "SELECT 1 FROM futures_outcomes "
                    "WHERE id = CAST(:after_id AS bigint)"
                ),
                params={"after_id": after_id},
            )
            cursor_resolves = bool(probe.fetchall())
        except Exception as exc:  # noqa: BLE001 — see FAILS CLOSED above
            await _safe_rollback(session)
            return _paused_before_examining(
                incoming_cursor=incoming_cursor,
                started=started,
                terminal="paused_target_timeout",
                reason=(
                    "the page was empty and the cursor could not be checked, so "
                    "this call cannot tell an exhausted scan from a dangling "
                    f"?after_id={after_id}: {type(exc).__name__}: {exc}"
                ),
            )
        if not cursor_resolves:
            return _refused(
                incoming_cursor=incoming_cursor,
                started=started,
                code="CURSOR_DANGLING",
                reason=(
                    f"?after_id={after_id} names no row in futures_outcomes, so "
                    "the keyset has no market to resume from and this page is "
                    "empty for that reason ALONE. It is not an exhausted scan. "
                    "Re-run without ?after_id= to restart the walk, or hand the "
                    "`next_cursor` from the last call that examined a leg."
                ),
            )

    if not page and (band_ages is not None or scope != DEFAULT_STATUS_SCOPE):
        # 🔴 AN EMPTY BANDED PAGE IS "THIS SLICE IS EMPTY" AND NOTHING ELSE, AND
        # THE SENTENCE BELOW WOULD HAVE SAID SOMETHING MUCH LARGER. The default
        # branch's whole vocabulary — `scan_exhausted`, "no collapsed legs
        # remain", the complement count — is written about this rail's ORIGINAL
        # cohort, and every one of those words is false for a 30-day slice of the
        # resolved tail. So the widened selectors get their own terminal rather
        # than borrowing prose that was true for a different question (#7701).
        if band_ages is not None:
            reason = (
                f"no collapsed legs in scope {scope!r} resolved between "
                f"{band_ages[0]} and {band_ages[1]} days ago. This is THIS "
                "BAND being empty — not the scope, and not the defect. A band "
                "also cannot see a row whose resolution_date is NULL, so an "
                "unbanded page is what counts the age-unknown tail."
            )
        else:
            reason = (
                f"no collapsed legs remain in scope {scope!r}. This rail writes "
                f"only in the {WRITABLE_STATUS_SCOPE!r} scope, so this is a "
                "statement about what a LOOK found, not about anything drained."
            )
        out = _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="ok",
            reason=reason,
        )
        # Band exhaustion and population exhaustion are different answers and
        # this rail returns them as two fields (#3257's ruling). `scan_exhausted`
        # keeps its documented meaning — THIS scan covered its population — and
        # a banded scan covered one slice of it, so it stays False.
        out["scan_exhausted"] = band_ages is None
        out["band_exhausted"] = band_ages is not None
        out["status_scope"] = scope
        out["band"] = list(band_ages) if band_ages else None
        out["by_age_bucket"] = {}
        out["by_status"] = {}
        out["applied"] = False
        return out

    if not page:
        # 🔴 AN EMPTY PAGE IS "THE SCOPE IS EMPTY", NOT "THE DEFECT IS GONE", AND
        # BEFORE 7167 THIS BRANCH COULD NOT TELL THEM APART. Read the complement
        # before answering: on 2026-09-21 the in-scope population was 0 and the
        # complement was 25,469 legs, so the unqualified sentence below would
        # have reported a drain that had never run as a drain that had finished.
        out_of_scope = await _out_of_scope_legs(session, sport=sport)
        if out_of_scope is None:
            reason = (
                "no collapsed legs remain IN SCOPE (Polymarket markets we still "
                "hold open); the out-of-scope cohort could not be counted, so "
                "this is NOT a statement that the defect is drained"
            )
        elif out_of_scope["legs"]:
            reason = (
                "no collapsed legs remain IN SCOPE (Polymarket markets we still "
                f"hold open), but {out_of_scope['legs']} collapsed legs across "
                f"{out_of_scope['markets']} markets sit OUTSIDE this rail's "
                "scope and are not repaired by it — a resolved market leaves "
                "the scope without any of its rows being fixed"
            )
        else:
            reason = "no collapsed legs remain, in scope or out of it"
        out = _paused_before_examining(
            incoming_cursor=incoming_cursor,
            started=started,
            terminal="ok",
            reason=reason,
        )
        # `scan_exhausted` keeps its documented meaning — THIS scan covered its
        # population — so the operator's paging contract is untouched. The two
        # fields beside it are what say whether finishing the scan finished the
        # job, which is the question `scan_exhausted` was never asking.
        out["scan_exhausted"] = True
        out["out_of_scope_measured"] = out_of_scope is not None
        out["out_of_scope_legs"] = out_of_scope["legs"] if out_of_scope else None
        out["applied"] = bool(apply)
        return out

    # ONE clock for the whole page, captured before the venue loop: a bucket
    # boundary re-read per row would sort two rows of one resolution into two
    # different slices while the loop is still running (Hot List #44).
    bucket_now = datetime.now(timezone.utc)

    rows = [
        {
            "outcome_id": int(r[0]),
            "market_id": int(r[1]),
            "condition_id": (r[2] or "").strip(),
            "outcome_name": r[3],
            "market_name": r[4],
            "category": r[5],
            "age_bucket": age_bucket(r[6], bucket_now),
            "market_status": r[7],
            # Overwritten by the loop below. Not defaulted to a verdict: a row
            # the loop never reaches must not be counted as one it examined.
            "verdict": None,
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
                    row["verdict"] = "no_condition_id"
                    continue

                market = found.get(row["condition_id"])
                if market is None:
                    counts["not_at_venue"] += 1
                    # 🔴 THE READING THIS WHOLE RUNG EXISTS FOR. Folded by age
                    # below: `not_at_venue` against a 0-30 day slice is a market
                    # the venue really has dropped, and against a 365+ slice it
                    # is the retention edge. One number cannot tell those apart,
                    # which is why the bound was unmeasurable before #7167.
                    row["verdict"] = "not_at_venue"
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
                    row["verdict"] = "unchanged"
                    continue

                row["verdict"] = "relabellable"
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

    # 🔴 #7701 rung 3a: A GROUP IS ONLY TESTABLE IF IT IS WHOLE, AND A PAGE CUT IS
    # NOT THE ONLY WAY IT ARRIVES PARTIAL. The top-up above fixes the `LIMIT` cut,
    # but a venue pause or the deadline `break`s the loop mid-market and the write
    # below still runs on what was planned, and a cursor handed in mid-market
    # starts the page there. All three present as a group of one that is trivially
    # distinct. So the test is not "are this page's labels distinct" but "did this
    # call examine every collapsed leg this market has" — measured against the
    # table, at the same instant, before anything is written.
    #
    # FAILS CLOSED. If the count cannot be taken, nothing is written: the whole
    # point of the guard is that an unprovable group is indistinguishable from a
    # safe one, and writing on "we could not check" is the bug, not the fallback.
    examined_by_market: dict[int, int] = {}
    for r in examined_rows:
        examined_by_market[r["market_id"]] = examined_by_market.get(r["market_id"], 0) + 1

    collapsed_by_market: dict[int, int] = {}
    count_failed: Optional[str] = None
    if by_market:
        try:
            counted = await _bounded_statement(
                session,
                timeout_literal=f"'{TARGET_SELECT_BUDGET_SECONDS}s'",
                server_budget_s=TARGET_SELECT_BUDGET_SECONDS,
                sql=f"""
                    SELECT leg.market_id, COUNT(*)
                      FROM futures_markets fm
                      JOIN futures_outcomes leg ON leg.market_id = fm.id
                     WHERE fm.id = ANY(CAST(:mids AS bigint[]))
                       AND {collapsed_leg_predicate("leg")}
                     GROUP BY leg.market_id
                """,
                params={"mids": sorted(by_market)},
            )
            collapsed_by_market = {int(r[0]): int(r[1]) for r in counted.fetchall()}
        except Exception as exc:  # noqa: BLE001 — unprovable is not writable
            await _safe_rollback(session)
            count_failed = f"{type(exc).__name__}: {exc}"

    writable: list[dict[str, Any]] = []
    for market_id, group in by_market.items():
        whole = (
            count_failed is None
            and market_id != overrun_market
            and market_id in collapsed_by_market
            and examined_by_market.get(market_id, 0) == collapsed_by_market[market_id]
        )
        if not whole:
            counts["refused_group_incomplete"] += len(group)
            logger.warning(
                "repair_polymarket_leg_label: market %s arrived partial "
                "(examined %d of %s collapsed legs%s); refusing the whole group "
                "because distinctness cannot be tested on a fragment",
                market_id,
                examined_by_market.get(market_id, 0),
                collapsed_by_market.get(market_id, "?"),
                f", count failed: {count_failed}" if count_failed else "",
            )
            continue
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
        # 🔴 `CAST(x AS t)` here for the SAME reason as the page select above,
        # and this line is why that comment was not enough. The source-level
        # guard scans for `:name::type`; an f-string writes the index BETWEEN
        # the name and the cast (`:id{i}::bigint`), so the offending token only
        # exists AFTER interpolation and no scan of this file could see it.
        # Compiling the rendered statement is the only guard that can.
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
        # The cursor is EXCLUSIVE (`(fm.id, fo.id) > (…, :after_id)`), so it names the last leg
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
    # 🔴 CERT-681: A FAILED WRITE HAS ALREADY PAID ITS CLEANUP. Starting the
    # count anyway puts a SECOND cleanup on the same reserve, and that is the
    # arithmetic that took the sibling rail's worst path to 31.10s against a 30s
    # wall. The count is degradable by construction — it reports itself
    # unmeasured and never reports zero — and the page is paused anyway, so the
    # operator is about to re-invoke and get a fresh count for free.
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
    if write_terminal is None and count_budget >= REMAINING_COUNT_MIN_BUDGET_SECONDS:
        # Scoped and banded IDENTICALLY to the page above. A terminal count that
        # kept the original predicate while the page walked a slice would report
        # the whole cohort as this band's remainder — the same number meaning two
        # different things on one response, which is how a banded drain comes to
        # read as an unfinished one.
        count_sql = f"""
            SELECT count(*)
              FROM futures_markets fm
              JOIN futures_outcomes fo
                ON fo.market_id = fm.id
               AND {COLLAPSED_LEG_PREDICATE}
             WHERE fm.source = 'polymarket'
               AND {STATUS_SCOPE_SQL[scope]}
               AND (CAST(:sport AS text) IS NULL
                    OR fm.llm_sport_category = CAST(:sport AS text))
               AND (CAST(:band_max_age AS double precision) IS NULL
                    OR fm.resolution_date >= NOW()
                       - (CAST(:band_max_age AS double precision) * INTERVAL '1 day'))
               AND (CAST(:band_min_age AS double precision) IS NULL
                    OR fm.resolution_date <= NOW()
                       - (CAST(:band_min_age AS double precision) * INTERVAL '1 day'))
        """
        try:
            result = await _bounded_statement(
                session,
                timeout_literal=f"'{int(count_budget * 1000)}ms'",
                server_budget_s=count_budget,
                sql=count_sql,
                params={
                    "sport": sport,
                    "band_min_age": band_ages[0] if band_ages else None,
                    "band_max_age": band_ages[1] if band_ages else None,
                },
            )
            remaining = int(result.scalar_one())
            remaining_measured = True
        except Exception:  # noqa: BLE001 — degradable: unmeasured, never zero
            await _safe_rollback(session)
            remaining = None
            remaining_measured = False

    # ---- the retention reading -------------------------------------------
    # Folded from the rows the page ACTUALLY EXAMINED, not from a second query:
    # it costs nothing, it cannot disagree with `counts`, and it is the control
    # that proves the band clause bound — a band that silently failed to apply
    # shows up here as buckets outside the slice that was asked for.
    #
    # Only examined rows are folded. A row the loop never reached (the deadline
    # fired, or the venue refused its batch) carries `verdict: None` and is
    # counted NOWHERE rather than in a bucket it was never read for: the whole
    # value of this table is that a `not_at_venue` in it is a venue answer.
    by_age_bucket: dict[str, dict[str, int]] = {}
    by_status: dict[str, int] = {}
    for row in examined_rows:
        if row["verdict"] is None:
            continue
        cell = by_age_bucket.setdefault(row["age_bucket"], {})
        cell[row["verdict"]] = cell.get(row["verdict"], 0) + 1
        status_key = str(row["market_status"])
        by_status[status_key] = by_status.get(status_key, 0) + 1

    return {
        "repair": "polymarket-leg-label",
        "applied": bool(apply),
        "counts": counts,
        "planned": len(writable),
        "samples": samples,
        "remaining_legs": remaining,
        "remaining_legs_measured": remaining_measured,
        "scan_exhausted": scan_exhausted and band_ages is None,
        # Two answers, never one (#3257). A banded page that ran out of rows
        # exhausted its SLICE; saying so through `scan_exhausted` would report a
        # 30-day sample as a drained cohort.
        "band_exhausted": (scan_exhausted if band_ages is not None else None),
        "status_scope": scope,
        "band": list(band_ages) if band_ages else None,
        "by_age_bucket": by_age_bucket,
        "by_status": by_status,
        "next_cursor": next_cursor,
        "stopped_before": stopped_before,
        "terminal": terminal,
        "reason": write_reason or venue_reason,
        "cap": cap,
        "sport": sport,
        "elapsed_s": round(time.monotonic() - started, 2),
    }
