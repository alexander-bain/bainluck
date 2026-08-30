"""When each futures outcome's price was last actually OBSERVED.

One question — *what is the newest ``captured_at`` for each of these outcomes?*
— asked the only way that stays cheap as the snapshot table grows.

## why this is not a ``max() ... GROUP BY``

The obvious spelling is the one this module replaces:

```sql
SELECT outcome_id, max(captured_at)
FROM futures_odds_snapshots
WHERE outcome_id IN (:ids) AND probability IS NOT NULL
GROUP BY outcome_id
```

It is correct and it does not scale, because **an aggregate cannot skip**: to
return one row per group PostgreSQL must visit every row of every group. On the
US Open register's 514 pinned outcomes, measured on production 2026-08-30 with
``EXPLAIN (ANALYZE, BUFFERS)``:

    Aggregate (Sorted)                                514 rows out
      Index Only Scan ...outcome_bookmaker_captured   342,059 rows in
      Shared Hit 173,444 + Read 2,310 = 175,754 blocks

**342,059 index tuples read to return 514 numbers**, and ~1.4 GB of buffer
traffic. Warm that is ~1.1 s; it is the buffer volume, not the CPU, that makes
the same statement cost 3.6 s one minute and 11.9 s the next on a request path.

The set of outcomes is always BOUNDED here (a register pins them), and
``idx_fos_outcome_captured (outcome_id, captured_at)`` exists, so the same
answer is one top-1 index probe per outcome. Measured on the same 514 ids, same
database, same minute:

    | executed row query | 1,766 ms  ->    118 ms |
    | buffer blocks      | 175,754   ->    3,407  |
    | rows returned      | 514       ->    514, 0 diffs |

🔴 **This is only the right shape for a BOUNDED id list.** N correlated probes
beat one aggregate at 514 outcomes; they do not at 500,000. A caller that wants
this over an unbounded population wants the aggregate back, or an index.

## the two predicates, and why neither is decoration

**``probability IS NOT NULL`` is carried even though it is dead today.**
``futures_odds_snapshots.probability`` is ``NOT NULL`` in the live schema, so
PostgreSQL removes the clause during planning — it appears in the plan of
neither the old form nor this one. It is kept because it states the caller's
actual question (*observed with a price*), it costs exactly nothing while the
column stays non-nullable, and it is the difference between right and wrong on
the day it does not.

🔴 **``captured_at IS NOT NULL`` IS LOAD-BEARING, AND THE DIALECT IS WHY.**
``ORDER BY x DESC`` is ``NULLS FIRST`` in PostgreSQL. Without this predicate an
outcome holding a single ``captured_at IS NULL`` row would report ``None`` while
``max()`` — which skips NULLs — reports its real newest observation. The two
forms would disagree on exactly the rows a freshness display exists to describe.

The column is nullable *in the database* (``information_schema`` says
``is_nullable = YES``, checked on production 2026-08-30) even though the model
declares ``captured_at: Mapped[datetime]``. **The model and the deployed schema
disagree**, and the database is the one that executes the query — which is also
why a real-PostgreSQL gate built from ``Base.metadata`` cannot police this: it
would emit a ``NOT NULL`` column and be unable to hold the row that breaks it.
The predicate, and the tests that pin it, are the guard.

🔴 **AND DO NOT "FIX" IT WITH ``NULLS LAST``.** The defensive-looking spelling
``ORDER BY captured_at DESC NULLS LAST`` is answer-identical and **19x slower**,
measured on the same population, same minute:

    DESC (NULLS FIRST) + IS NOT NULL     124 ms    3,503 buffer blocks
    DESC NULLS LAST    + IS NOT NULL   2,408 ms  177,719 buffer blocks

``NULLS LAST`` does not match the index's own ordering, so each probe stops
being a one-row backward scan and becomes a Sort over the whole group — which
is the aggregate's cost back again, wearing a safer-looking clause.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesOddsSnapshot, FuturesOutcome


def latest_observed_at_subquery():
    """Correlated scalar subquery: newest ``captured_at`` for ``FuturesOutcome.id``.

    Exposed separately from :func:`load_latest_observed_at` so the statement can
    be compiled and inspected without a session, and so a caller already
    selecting from ``futures_outcomes`` can add this as one more column rather
    than issuing a second round trip.

    ``.correlate(FuturesOutcome)`` is explicit rather than left to SQLAlchemy's
    auto-correlation: this subquery is only ever correct when the outer query
    supplies ``FuturesOutcome``, and an auto-correlation that quietly does not
    happen is a cross join against the whole snapshot table.
    """
    return (
        select(FuturesOddsSnapshot.captured_at)
        .where(
            FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
            # Dead today (schema NOT NULL), kept because it is the question.
            FuturesOddsSnapshot.probability.isnot(None),
            # NOT dead. `DESC` is NULLS FIRST in PostgreSQL — see the module
            # docstring. Removing this makes a NULL row win its own group.
            FuturesOddsSnapshot.captured_at.isnot(None),
        )
        .order_by(FuturesOddsSnapshot.captured_at.desc())
        .limit(1)
        .correlate(FuturesOutcome)
        .scalar_subquery()
    )


async def load_latest_observed_at(
    session: AsyncSession, outcome_ids: Iterable[int]
) -> dict[int, datetime]:
    """``{outcome_id: newest captured_at}`` for the ids given.

    An outcome with no priced observation is **absent from the mapping**, not
    present with ``None``. That is the aggregate form's shape and callers depend
    on it: ``.get(id)`` yields ``None`` either way, but a caller that iterates or
    counts the mapping would silently start seeing rows that have never been
    observed.
    """
    ids = list(outcome_ids)
    if not ids:
        return {}

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                latest_observed_at_subquery().label("observed_at"),
            ).where(FuturesOutcome.id.in_(ids))
        )
    ).all()

    return {row.id: row.observed_at for row in rows if row.observed_at is not None}
