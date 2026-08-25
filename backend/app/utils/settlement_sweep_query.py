"""Which rows the sweep asks the database for — and what it refuses to ask twice.

Queue 392 Item 1 (#2077). ``settlement_sweep_plan`` decides the ORDER; this module
decides the POPULATION and the exclusions. It is deliberately split out and kept
pure — SQL text plus row→dataclass mapping, no session, no engine — because the two
things most likely to be wrong here are the window bound and the idempotency
predicate, and both are cheaper to prove against a string than against a database.

THE WINDOW IS THE 86-DAY BOUND, NOT THE 66-DAY ONE, AND THAT IS DELIBERATE
--------------------------------------------------------------------------

Two constants govern two different questions, and using either for the other's job
is a real defect (``kalshi_retention`` says so in its own docstring):

* ``CAPTURE_PLANNING_AGE_DAYS`` (45 since 2026-08-24) — *"which rows do we spend the
  next call on first"*. It is the PRIORITIZATION anchor and what the buckets are cut
  against. It is **not** a claim that anything is still available.
* ``PROVABLY_PURGED_AGE_DAYS`` (86) — *"is one more call provably wasted"*. It is
  the SKIP-WORK horizon, and the only one of the two allowed to stop work.

The SQL window uses **86**. A market past its planning horizon but under 86 days is
*not* provably gone — C-KALSHI-RETENTION-1 measured 68-day markets still present with
100 trades alongside purged 54-day siblings in the same series — and the planner has
a name for it (``overdue``) that sorts it FIRST rather than dropping it. If the SQL
filtered at the planning horizon instead, those rows would never reach the planner to
be named, and the sweep would report a clean run over a population it had silently
narrowed — the gotcha #53 shape, arrived at from the query side. Fail open; let the
planner name it.

That division is what makes the planning constant safe to lower. Tightening it moves
rows into ``overdue``, which is a change in URGENCY; it can never remove a row from
the sweep, because removal is the other constant's job and that one has not moved.

WHY THE SQL ORDERS BY DATE WHEN THE PLANNER OWNS ORDERING
----------------------------------------------------------

Because the fetch cap is applied by the database, before the planner exists. An
unordered ``LIMIT`` could hand the planner a page with no terminal-bucket rows in
it at all, and the planner would then correctly, and uselessly, order what it was
given. ``ORDER BY resolution_date ASC, id ASC`` guarantees the oldest — the rows
closest to their deadline — survive the cap. The tiebreak on ``id`` is not
decoration: an unordered ``LIMIT`` means a rehearsal and the run that follows it can
select different rows while both report the same count, which is the
identity-vs-cardinality confusion that returned BLOCK four times on the delete rail.

IDEMPOTENCY IS TWO PREDICATES, AND THEY MEAN DIFFERENT THINGS
--------------------------------------------------------------

1. **Same sweep (resumability).** A market already carrying a row for *this*
   ``sweep_id`` is not re-probed. This is what makes the command safe to re-run:
   a run killed at row 400 of 1,202 resumes at 401 rather than starting over or
   double-writing. ``sweep_id`` defaults to a date, so "run it again today" resumes
   by default rather than by remembering a flag.
2. **Any sweep (terminality).** A market that has *ever* received a TERMINAL
   disposition is not re-probed at all. ``SETTLED`` is the answer; ``PURGED`` and
   ``NOT_FOUND`` are answers too — the source has told us, and it will not change
   its mind. Everything else (``AMBIGUOUS_EMPTY``, ``RATE_LIMITED``,
   ``TRANSPORT_ERROR``, ``OPEN_NO_SETTLEMENT``) is explicitly NOT terminal and comes
   back next sweep, because re-probes are the point of the table being plural.

These are reported separately and never summed. "We already have this" and "we could
not get this" are the two readings a single skipped-count would fuse, and the whole
capture program exists because that fusion is unrecoverable in a burn-down.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS
from app.utils.settlement_sweep_plan import Candidate
from app.utils.settlement_truth import (
    STABLE_NONANSWER_DISPOSITION_VALUES,
    Disposition,
)

#: The only source the weekly dated sweep covers. C-PM-RETENTION-1 measured no
#: Polymarket cliff at all (0 of 70 records gone, 30 days to 3.66 years), so
#: Polymarket's backlog is a bulk re-poll with no deadline and does not belong in a
#: race. Named rather than inlined so the scope of "the sweep" is greppable.
SWEEP_SOURCE = "kalshi"

#: Dispositions after which re-probing can only waste a call. Derived from the
#: enum rather than typed out, so a disposition added later must be classified
#: deliberately (see the test that asserts this partition is exhaustive) instead of
#: silently defaulting into the re-probe set.
TERMINAL_DISPOSITIONS: frozenset[str] = frozenset(
    {Disposition.SETTLED.value, Disposition.PURGED.value, Disposition.NOT_FOUND.value}
)

#: Dispositions that are NOT answers about the market and must be tried again.
RETRYABLE_DISPOSITIONS: frozenset[str] = frozenset(
    d.value for d in list(Disposition) if d.value not in TERMINAL_DISPOSITIONS
)

#: The candidate reason every row selected by this query carries. It is a reason to
#: LOOK — ``assert_grading_licensed`` refuses to let it become evidence.
CANDIDATE_REASON = "missing_winner"

#: How many candidate rows to fetch per budget unit. The planner needs a real
#: population to choose from — handed exactly ``budget`` rows it cannot prefer the
#: terminal bucket over anything, because there is nothing to prefer it over.
FETCH_MULTIPLIER = 20

#: Absolute ceiling on the candidate fetch, so a huge budget cannot pull the whole
#: backlog into memory. Reported when it binds; never silent (gotcha: a cap that
#: does not announce itself reads as "covered everything").
MAX_FETCH_ROWS = 20_000


def window_start(now: datetime | None = None) -> datetime:
    """Earliest ``resolution_date`` still worth a call — the 86-day skip bound."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)


def fetch_limit_for(budget: int) -> int:
    """Rows to pull so the planner has something to plan over."""
    return max(1, min(MAX_FETCH_ROWS, max(budget, 1) * FETCH_MULTIPLIER))


def default_sweep_id(now: datetime | None = None, source: str = SWEEP_SOURCE) -> str:
    """``kalshi-2026-08-28`` — a DATE, so re-running today resumes today's sweep.

    Idempotency that depends on the operator remembering to pass a flag is not
    idempotency. The identifier a second invocation naturally produces has to be the
    same one the first produced, so the default is derived rather than generated.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return f"{source}-{now.strftime('%Y-%m-%d')}"


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

#: The cohort predicate, written ONCE and composed into every query below.
#:
#: Three reads need this exact population — the work list, the burn-down
#: denominator, and the exclusion split — and if any one of them drifts, the sweep
#: reports coverage of a population it did not measure. Composing beats copying:
#: there is no version of this string that can be updated in two places and missed
#: in the third.
#:
#: ``is_winner`` is a NOT NULL boolean defaulting to false, so "no winner" is
#: ``NOT EXISTS (... IS TRUE)`` and not a NULL test — a market whose outcomes all
#: read false IS the population, not an absence of rows.
_COHORT_WHERE = """
    m.source = :source
  AND m.external_id IS NOT NULL
  AND m.external_id <> ''
  AND m.resolution_date IS NOT NULL
  AND m.resolution_date > :window_start
  AND m.resolution_date <= :now
  AND NOT EXISTS (
      SELECT 1 FROM futures_outcomes o
      WHERE o.market_id = m.id AND o.is_winner IS TRUE
  )
"""

#: EXISTS fragments for the two idempotency exclusions, also composed rather than
#: copied, so the work list and the exclusion census can never disagree about what
#: "already captured" means.
_EXISTS_THIS_SWEEP = """
    EXISTS (
        SELECT 1 FROM settlement_captures c
        WHERE c.market_id = m.id AND c.sweep_id = :sweep_id
    )
"""

_EXISTS_TERMINAL_PRIOR = """
    EXISTS (
        SELECT 1 FROM settlement_captures c
        WHERE c.market_id = m.id AND c.disposition = ANY(:terminal_dispositions)
    )
"""

#: Per-market probe history, joined onto every candidate so the planner can tell a
#: row nobody has asked from a row the source has already declined to answer (#2175).
#:
#: Counted over ALL sweeps, not the current one — the current sweep's rows are
#: excluded from the work list entirely by ``_EXISTS_THIS_SWEEP``, so anything this
#: sees is by definition history. Index-backed by
#: ``ix_settlement_captures_market_time`` on ``(market_id, captured_at)``; the same
#: correlated access pattern the two EXISTS predicates above already pay for.
_HISTORY_LATERAL = """
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS attempts,
            COUNT(*) FILTER (
                WHERE c.disposition = ANY(:stable_nonanswer_dispositions)
            ) AS stable_nonanswers
        FROM settlement_captures c
        WHERE c.market_id = m.id
    ) h ON TRUE
"""

#: The at-risk cohort minus both idempotency exclusions: this run's work list.
#:
#: THE ``ORDER BY`` HERE IS STILL PURE DEADLINE, AND DELIBERATELY SO. The planner
#: tiers on probe history (#2175), but this ordering exists for a different job:
#: surviving the ``LIMIT``. Its contract is "the rows closest to their deadline
#: reach the planner at all". Sorting the FETCH by tier would let never-probed rows
#: from a distant bucket displace dying ones off the page, and the planner cannot
#: prefer a row it was never handed. Deadline decides who gets in the room; the
#: planner decides who gets called on.
CANDIDATE_SQL = f"""
SELECT m.id, m.source, m.external_id, m.resolution_date,
    COALESCE(h.attempts, 0) AS attempts,
    COALESCE(h.stable_nonanswers, 0) AS stable_nonanswers
FROM futures_markets m
{_HISTORY_LATERAL}
WHERE {_COHORT_WHERE}
  AND NOT {_EXISTS_THIS_SWEEP}
  AND NOT {_EXISTS_TERMINAL_PRIOR}
ORDER BY m.resolution_date ASC, m.id ASC
LIMIT :fetch_limit
"""

#: The same cohort WITHOUT the idempotency exclusions, counted per day, split by
#: whether the market has EVER been captured.
#:
#: The second column is the burn-down's real remaining, and getting it wrong is easy
#: in a specific way worth naming: the obvious "remaining" — cohort rows still
#: missing a winner — **never decreases**, because the capture path is forbidden
#: from writing ``is_winner``. A verification built on it would report zero progress
#: after a perfect sweep, and a reader would reasonably conclude the sweep was
#: broken. What the sweep can actually drain is the UNCAPTURED count: rows whose
#: settlement we have not yet asked a source about while it still answers.
#:
#: Bucketing happens in Python against ``settlement_sweep_plan.bucket_for``, not in
#: SQL. One bucket implementation, one place to be wrong. A ``CASE WHEN`` ladder here
#: would be a second copy of the policy that no test compares to the first — the
#: self-oracular shape that blocked the delete rail three rounds running.
COHORT_BY_DAY_SQL = f"""
SELECT
    date_trunc('day', m.resolution_date) AS day,
    COUNT(*) AS n_total,
    COUNT(*) FILTER (
        WHERE NOT EXISTS (
            SELECT 1 FROM settlement_captures c WHERE c.market_id = m.id
        )
    ) AS n_uncaptured
FROM futures_markets m
WHERE {_COHORT_WHERE}
GROUP BY 1
ORDER BY 1
"""

#: Why cohort rows are absent from the work list, split by reason and never summed.
#: ``terminal_prior`` is counted only where ``this_sweep`` is false, so the two
#: columns partition the excluded set instead of double-counting a market that is
#: both.
EXCLUSIONS_SQL = f"""
SELECT
    COUNT(*) FILTER (WHERE x.this_sweep) AS already_this_sweep,
    COUNT(*) FILTER (WHERE x.terminal_prior AND NOT x.this_sweep) AS terminal_prior
FROM (
    SELECT
        {_EXISTS_THIS_SWEEP} AS this_sweep,
        {_EXISTS_TERMINAL_PRIOR} AS terminal_prior
    FROM futures_markets m
    WHERE {_COHORT_WHERE}
) x
"""

#: Rows this sweep has already written, by disposition. The verification read.
CAPTURED_BY_DISPOSITION_SQL = """
SELECT c.disposition, COUNT(*) AS n
FROM settlement_captures c
WHERE c.sweep_id = :sweep_id
GROUP BY 1
ORDER BY 1
"""

#: Per-day captured counts for this sweep, bucketed in Python for the same reason
#: ``COHORT_BY_DAY_SQL`` is. Joins back to the market so the bucket is cut against
#: the same ``resolution_date`` the cohort query used.
CAPTURED_BY_DAY_SQL = """
SELECT date_trunc('day', m.resolution_date) AS day, COUNT(*) AS n
FROM settlement_captures c
JOIN futures_markets m ON m.id = c.market_id
WHERE c.sweep_id = :sweep_id
  AND m.resolution_date IS NOT NULL
GROUP BY 1
ORDER BY 1
"""

#: The pre-insert guard. Cheap, and it closes the window between selection and
#: write in which a concurrent invocation of the same sweep could have written the
#: same market. Selection-time exclusion alone is correct for a single writer; this
#: makes a second writer harmless rather than merely unlikely.
ALREADY_CAPTURED_SQL = """
SELECT 1 FROM settlement_captures
WHERE market_id = :market_id AND sweep_id = :sweep_id
LIMIT 1
"""


def candidate_params(
    *,
    sweep_id: str,
    budget: int,
    now: datetime | None = None,
    source: str = SWEEP_SOURCE,
) -> dict:
    """Bind parameters for :data:`CANDIDATE_SQL`."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return {
        "source": source,
        "window_start": window_start(now),
        "now": now,
        "sweep_id": sweep_id,
        "terminal_dispositions": sorted(TERMINAL_DISPOSITIONS),
        "stable_nonanswer_dispositions": sorted(STABLE_NONANSWER_DISPOSITION_VALUES),
        "fetch_limit": fetch_limit_for(budget),
    }


def cohort_params(now: datetime | None = None, source: str = SWEEP_SOURCE) -> dict:
    """Bind parameters for :data:`COHORT_BY_DAY_SQL`."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return {"source": source, "window_start": window_start(now), "now": now}


def exclusion_params(
    *, sweep_id: str, now: datetime | None = None, source: str = SWEEP_SOURCE
) -> dict:
    """Bind parameters for :data:`EXCLUSIONS_SQL`."""
    params = cohort_params(now, source)
    params["sweep_id"] = sweep_id
    params["terminal_dispositions"] = sorted(TERMINAL_DISPOSITIONS)
    return params


@dataclass(frozen=True)
class ExclusionCounts:
    """Why rows in the cohort are not in the work list. Never summed together."""

    #: Already captured under THIS sweep_id — we have it, this run.
    already_this_sweep: int = 0
    #: Terminal disposition from an earlier sweep — we have it, permanently.
    terminal_prior: int = 0

    def total(self) -> int:
        return self.already_this_sweep + self.terminal_prior


def rows_to_candidates(rows) -> list[Candidate]:
    """Map candidate rows to :class:`Candidate`.

    Accepts both the 4-column shape (``id, source, external_id, resolution_date``)
    and the 6-column shape that adds ``attempts, stable_nonanswers``. The short form
    is tolerated because a caller that has no probe history to offer should get a
    planner that treats its rows as never-probed — which is the tier that gets
    served FIRST. Defaulting the other way would let a caller silently demote its
    own work to the back of the queue (#2175).
    """
    return [
        Candidate(
            market_id=row[0],
            source=row[1],
            external_id=row[2],
            resolution_date=row[3],
            candidate_reason=CANDIDATE_REASON,
            attempts=int(row[4]) if len(row) > 4 and row[4] is not None else 0,
            stable_nonanswers=int(row[5]) if len(row) > 5 and row[5] is not None else 0,
        )
        for row in rows
    ]
