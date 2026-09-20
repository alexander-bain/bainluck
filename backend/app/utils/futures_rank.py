"""#6598 — `futures_outcomes.rank`, and the one statement that derives it.

`rank` is a FIELD-LEVEL property: "where does this leg sit among the other legs
of its market". Every writer of the column computed it from the wrong
population — the legs in the CURRENT WRITE BATCH, renumbered from 1 — so a
market whose legs are written at different moments accumulates ranks from
several different orderings at once:

    Kyle Larson        22.5%   rank 1     written 09-15 15:16
    Ty Gibbs           12.0%   rank 1     written 09-16 00:50
    Denny Hamlin       11.5%   rank 2     written 09-16 00:50
    Ryan Blaney        11.5%   rank 1     written 09-15 17:17
    Christopher Bell   10.5%   rank 3     written 09-16 00:50
    Chase Briscoe       9.0%   rank 2     written 09-16 13:50

Three drivers badged `1`, and an 11% row ranked below a 9% row. Each fragment
is internally correct and the column as a whole is nonsense. The census in
#6598: **1,326 open markets** serve a duplicated rank across legs whose prices
are not equal, which no tie rule can explain.

── WHY A WHOLE-FIELD RE-DERIVATION AND NOT A BETTER PER-WRITE RANK ──────────

There is no per-write number that is correct. A poll legitimately sees a subset
of a market — Kalshi's placeholder pass inserts unpriced legs with
`on_conflict_do_nothing`, Polymarket's `_retire_unpriced_legs` withdraws a price
without renumbering anyone, and an empty book simply keeps a leg out of the
batch. Whatever the batch is ranked against, the legs OUTSIDE it keep a number
that was derived against a different field. So the derivation scope has to be
the market, and the only moment the market's field is knowable is after its
write: hence one statement, run at each poller's per-market boundary.

This also means no backfill is owed. Every open market re-derives its own field
on its next poll; the fossils drain on the ordinary poll cadence.

── COMPETITION RANKING: TIES SHARE A NUMBER ─────────────────────────────────

`rank()`, not `row_number()`. Two legs at the same price are tied, and any
tiebreak this module could invent (id, name, insertion order) would assert an
ordering between them that the prices do not support — the same class of
fabrication #6325 refused when it declined to renumber a settled board by
display position. Ties therefore share a rank and the next rank skips the gap
(1, 2, 2, 4), which is also exactly the shape #6598's census treats as legitimate:
its defect count excludes duplicate ranks whose probabilities are equal.

── ORDERING AND NULLS ───────────────────────────────────────────────────────

`current_probability DESC NULLS LAST`. An unpriced leg is a real row — Kalshi's
third pass records that the venue lists it (#3518) — and it must never outrank a
priced one on a page that sorts by this column, which is the intent the Kalshi
placeholder block already states in prose and implements only for the legs it
happens to insert. NULLS LAST makes it true for the whole field. Unpriced legs
tie with each other, so they all take the same trailing rank.

── WHAT THIS DELIBERATELY DOES NOT TOUCH ────────────────────────────────────

* ``last_updated`` — a TOUCH-STAMP that `routes/playoffs.py` reads as a liveness
  gate, and this is not a poll. The statement names `rank` and nothing else, and
  the column has no ``onupdate``, so a re-rank cannot make a six-week-old row
  look like it was seen today.
* ``rank_change_24h`` — a different column with a different defect (#2408's
  class: a per-write delta wearing a 24h label). Recomputing it here would mint
  a "moved N places" arrow spanning however long it has been since the row was
  last written, which is a louder lie than the stale value it replaces. It is
  left exactly as the poller wrote it, and named here so the next reader knows
  it was a decision.
"""

from __future__ import annotations

from sqlalchemy import func, select, update

from app.models.models import FuturesOutcome

__all__ = ["rerank_market_field_stmt"]


def rerank_market_field_stmt(market_id: int):
    """An UPDATE that re-derives ``rank`` across EVERY leg of one market.

    Core ``update()`` on purpose (gotchas #4/#5): the poll paths that call this
    write through Core in the same transaction, and an ORM assignment here would
    mix flush orderings with their upserts.

    The ``IS DISTINCT FROM`` guard is not an optimisation — it is what makes the
    statement a no-op on the overwhelmingly common case where the poll saw the
    whole field and the batch rank was already the field rank. A market that is
    healthy pays one indexed scan and zero row writes.
    """
    ranked = (
        select(
            FuturesOutcome.id.label("id"),
            func.rank()
            .over(order_by=FuturesOutcome.current_probability.desc().nullslast())
            .label("rnk"),
        )
        .where(FuturesOutcome.market_id == market_id)
        .subquery("field_rank")
    )

    return (
        update(FuturesOutcome)
        .where(FuturesOutcome.id == ranked.c.id)
        .where(FuturesOutcome.rank.is_distinct_from(ranked.c.rnk))
        .values(rank=ranked.c.rnk)
        .execution_options(synchronize_session=False)
    )
