"""The `max_movement_24h` market pool — one home for a bound two surfaces use.

WHAT THE BOUND IS.

`futures_markets.max_movement_24h` is defined by the task that writes it
(`app.tasks.update_max_movement`, every 10 minutes) as
`MAX(ABS(outcome.probability_change_24h))` over that market's outcomes. So for
every outcome, **its market's `max_movement_24h` is at least its own |change|**.

Take the top-N markets by `max_movement_24h` and let `v` be the smallest
`max_movement_24h` in that pool. Any outcome whose |change| exceeds `v` lives in
a market whose `max_movement_24h` exceeds `v`, and therefore in a market already
inside the pool. **The pool is a provable superset of the answer, not a sample
of it** — which is why a query that ranks outcomes by `abs(probability_change_24h)`
may restrict itself to the pool and still return the same rows.

WHY IT LIVES HERE RATHER THAN IN A ROUTE.

LAT-P108 proved and shipped this bound for `/api/futures/movers`
(`routes/futures.py:_build_movers_query`) and measured it on production
2026-08-28: 11,129 ms -> 627 ms, with the value vector and id list IDENTICAL to
the unbounded scan at limit 10/pool 400 and limit 20/pool 800.

LAT-P151 needed exactly the same reduction for the second consumer — section 3
of `/api/events/search-suggestions`, whose own comment had recorded the cost
(1.14 GB, an external merge to disk, five rows out) and named an expression
index as the only fix, unaware that the bound next door already was one.

The reason to give the shape ONE home rather than a second spelling is that the
bound is not a query optimisation; it is a claim about an invariant maintained
by a task in a different file. `test_the_bound_depends_on_max_movement_being_maintained`
in `tests/test_futures_movers_pool_bound.py` is the executable form of that
precondition. If `update_max_movement` ever stops maintaining the column, ONE
function goes wrong and both readers go wrong together and visibly — rather than
one being repaired and the other quietly continuing to drop real movers.

WHAT IS DELIBERATELY *NOT* HERE.

**Pool sizing.** The two callers ask genuinely different questions — `/movers`
scales its pool with a caller-supplied `limit` (`_movers_market_pool_size`,
40x the ask, floored at 400 and capped at 1500), while search-suggestions asks
for a fixed five. A shared sizing function would have to pretend those are the
same decision. `pool_size` is therefore the caller's, and each caller carries
the measurement that justifies its own number.

**The status list.** `/movers` counts `('open','active')`; search-suggestions
section 3 has always counted `open` alone. Neither is wrong and this module is
not the place to unify them — passing the statuses in keeps this function a
shape and not a policy.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select


def market_pool_subquery(*, pool_size: int, statuses: Sequence[str]):
    """The top-`pool_size` market ids by `max_movement_24h`, as a scalar subquery.

    Intended for `FuturesOutcome.market_id.in_(...)`. Because the pool is already
    restricted to `statuses`, a caller using it that way does NOT also need to
    join `futures_markets` to re-state the status filter — the `IN` carries it.

    🔴 `max_movement_24h IS NOT NULL` IS PART OF THE BOUND, NOT A TIDY-UP. A
    market that has never had the column written cannot be ordered against the
    pool, so it is out of the pool — and therefore its outcomes are out of the
    answer, however far they have moved. That is the same trade `/api/futures/movers`
    has shipped since LAT-P108, and it is pinned by
    `test_a_market_with_null_max_movement_is_out_of_the_pool`.
    """
    # Imported inside the function: `app.models.models` imports a large part of
    # the ORM, and this module is imported from route modules at request time.
    from app.models.models import FuturesMarket

    return (
        select(FuturesMarket.id)
        .where(
            FuturesMarket.status.in_(tuple(statuses)),
            FuturesMarket.max_movement_24h.isnot(None),
        )
        .order_by(FuturesMarket.max_movement_24h.desc())
        .limit(pool_size)
        .scalar_subquery()
    )
