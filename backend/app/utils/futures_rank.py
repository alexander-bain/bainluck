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

🔴 THE SENTENCE THAT USED TO BE HERE SAID "no backfill is owed — every open
market re-derives its own field on its next poll", AND IT WAS MEASURED WRONG
(#7640). It is true only of a market something polls. This ship's own
after-check found **86,205 rows across 13,965 open markets** already wrong at
release, and splitting them by whether anything schedules them:
`refresh_stale_futures_prices` admits on `market_tier = 1` OR
`volume >= HIGH_VALUE_VOLUME_FLOOR`, and **10,145 of those markets fail both
arms**. A tier-5, $3k-volume fantasy board is repaired only if an unrelated
socket flush happens to touch it, which may be never — while the team page
renders it regardless of tier or volume. The drain is
`scripts/repair_7640_stale_futures_ranks.py`, which re-derives with the
statement below rather than a copy of it.

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

── THE POPULATION THIS HAS TO BE CALLED FROM IS "WRITES THE PRICE", NOT
── "WRITES THE RANK" (CERT-3182) ────────────────────────────────────────────

The first version of this ship wired the three pollers that *number* a batch,
and its reachability guard enumerated exactly those three. That is the wrong
population, and the gap is not a missed call site — it is a missed CLASS. `rank`
is derived from ``current_probability``, so **every writer of the price
invalidates the number, including the writers that have never heard of it**:

    scheduled hourly `futures_price_refresh._write_prices` moves the price of
    a served market's legs and leaves `rank` exactly where the last poll put it.

Those writers do not corrupt the column by numbering it wrong; they corrupt it
by leaving it alone while the thing it describes moves underneath. A price
CROSSING on such a path re-creates the served defect in full — the stale
ordering on `/economics`, the fossil badge on a team page — within the hour, on
rows a poller may not reach for days. So the invariant is:

    a transaction that changes or retires ``current_probability`` on any leg of
    a market re-derives that market's field before it commits.

Six modules were dark to the first wiring and are wired now:
`futures_price_refresh` (the hourly net, and its three retirement paths),
`tournament_price_refresh`, `kalshi_ws`, `polymarket_ws`, `datagolf` and
`prediction_market_matching`'s live poll. `tests/test_futures_rank_field_wide_6598.py`
enumerates the population by AST rather than by hand, so the seventh writer
fails a test on the day it is written instead of being found by a reader.

Two writers are exempt WITH A REASON rather than merely absent, and the reason
is the same one: `backfill_winners` and `repair_winner_field` write 1.0/0.0 as a
SETTLEMENT, onto a board that is over. #6325 refused to renumber a settled board
and that refusal still holds — a finished field's rank is the record of how it
finished, not a live ordering, and re-deriving it from the grade would collapse
every loser onto one number.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select, update

from app.models.models import FuturesOutcome

__all__ = [
    "field_rank_expr",
    "rerank_market_field_stmt",
    "rerank_market_fields_stmt",
]


def field_rank_expr():
    """The ordering itself — partition, direction, tie rule and NULL placement.

    Lifted out of the UPDATE below because #7640 needed a SELECT that asks the
    same question ("which stored ranks disagree with the field?") and the only
    safe way to ask it is with this expression, not with a hand-written copy in
    another module's SQL. A repair that re-derives `rank` from its own window
    function is a second opinion about the ordering, and a second opinion is
    exactly the defect #6598 exists to end — it would "fix" boards to a rule the
    live writers do not follow, and the next poll would undo it.

    Everything discriminating lives here: ``PARTITION BY market_id`` (the field
    is the market), ``rank()`` not ``row_number()`` (ties share a number), and
    ``DESC NULLS LAST`` (an unpriced leg never outranks a priced one). Change
    one of them and every consumer changes with it, which is the point.
    """
    return func.rank().over(
        partition_by=FuturesOutcome.market_id,
        order_by=FuturesOutcome.current_probability.desc().nullslast(),
    )


def rerank_market_fields_stmt(market_ids: Sequence[int]):
    """The same re-derivation, for several markets in ONE statement.

    ``PARTITION BY market_id`` is what makes this the same rule and not a second
    opinion: the ordering expression, the tie rule, the NULL placement and the
    ``IS DISTINCT FROM`` guard are written once, here, and the single-market form
    below is a call into this one. Two copies of a ranking rule is how the
    fragment defect gets reintroduced by a writer that thought it was following
    the existing one.

    It exists for the writers that do not walk a market at a time. A socket
    flush holds a batch of ``outcome_id``s spanning whatever ticked in the last
    few seconds, and `tournament_price_refresh` walks Gamma *conditions* whose
    legs live on several market rows; both would otherwise pay one round trip per
    market on a hot path.

    An empty list is a no-op (SQLAlchemy compiles ``IN ()`` to a false
    predicate), so a caller never has to guard the call — which matters, because
    the flush that wrote nothing is the common case on a quiet book.
    """
    ranked = (
        select(
            FuturesOutcome.id.label("id"),
            field_rank_expr().label("rnk"),
        )
        .where(FuturesOutcome.market_id.in_(market_ids))
        .subquery("field_rank")
    )

    return (
        update(FuturesOutcome)
        .where(FuturesOutcome.id == ranked.c.id)
        .where(FuturesOutcome.rank.is_distinct_from(ranked.c.rnk))
        .values(rank=ranked.c.rnk)
        .execution_options(synchronize_session=False)
    )


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
    return rerank_market_fields_stmt([market_id])
