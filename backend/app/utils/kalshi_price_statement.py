"""#10689: reuse Kalshi price expressions, preserving ordinary per-row execute.

The two Core statements are constructed once. Their storage binds use the
columns' Numeric types; comparison binds retain the original scalar Float
inputs before the canonical helpers cast to stored precision. Sharing a bind
between these roles changes asyncpg SQL/types, even when values are identical.
The repeat predicate checks the database row, never a cached quote. The caller
forces the first committed observation of each run; actual repeated input may
renew liveness after 30 seconds. Transaction and result accounting stay with
the caller.
"""

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType

from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    Integer,
    and_,
    bindparam,
    cast,
    column,
    exists,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

from app.models.models import FuturesOutcome
from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

# Real repeated input may renew liveness, but need not rewrite at socket cadence.
KALSHI_REPEAT_REFRESH_SECONDS = 30


def _needs_observation(has_book: bool):
    table = FuturesOutcome.__table__
    return _observation_needed(
        bindparam("kalshi_force_observation", type_=Boolean()),
        bindparam("kalshi_stored_probability", type_=table.c.current_probability.type),
        {
            name: bindparam(parameter, type_=table.c[name].type)
            for name, parameter in (
                ("current_yes_bid", "kalshi_stored_bid"),
                ("current_yes_ask", "kalshi_stored_ask"),
            )
        } if has_book else None,
    )


def _observation_needed(force, probability, book, has_book=None):
    """The repeat predicate over any value source (binds or an unnest row).

    ``book`` maps each book column to its value; ``has_book`` (per-row, for
    an unnest) gates it, else a present ``book`` always counts.
    """
    table = FuturesOutcome.__table__
    changes = [
        force,
        table.c.current_probability.is_distinct_from(
            cast(probability, table.c.current_probability.type)
        ),
        table.c.last_updated.is_(None),
        table.c.last_updated
        <= func.now() - timedelta(seconds=KALSHI_REPEAT_REFRESH_SECONDS),
    ]
    if book is not None:
        moved = [
            table.c[name].is_distinct_from(cast(value, table.c[name].type))
            for name, value in book.items()
        ]
        if has_book is None:
            changes.extend(moved)
        else:
            changes.append(and_(has_book, or_(*moved)))
    return or_(*changes)


def _writable():
    """#5411: a tier-3 settled row is never re-priced (see the statement)."""
    return or_(
        FuturesOutcome.resolution_source.is_(None),
        FuturesOutcome.resolution_source.notin_(sorted(AUTHORITATIVE_SOURCES)),
    )


def _build_price_statement(has_book: bool) -> Update:
    table = FuturesOutcome.__table__
    return (
        update(table)
        .where(
            FuturesOutcome.id == bindparam("kalshi_outcome_id", type_=Integer()),
            _writable(),
            _needs_observation(has_book),
        )
        .values(
            current_probability=bindparam(
                "kalshi_stored_probability", type_=table.c.current_probability.type
            ),
            last_updated=func.now(),
            price_changed_at=price_changed_at_value(
                FuturesOutcome.current_probability,
                FuturesOutcome.price_changed_at,
                bindparam("kalshi_compared_probability", type_=Float()),
            ),
            current_yes_bid=(
                bindparam("kalshi_stored_bid", type_=table.c.current_yes_bid.type)
                if has_book
                else FuturesOutcome.current_yes_bid
            ),
            current_yes_ask=(
                bindparam("kalshi_stored_ask", type_=table.c.current_yes_ask.type)
                if has_book
                else FuturesOutcome.current_yes_ask
            ),
        )
        .returning(
            FuturesOutcome.id,
            FuturesOutcome.market_id,
            FuturesOutcome.last_updated,
            func.clock_timestamp().label("database_clock"),
            quote_moved_column(
                table,
                (
                    (
                        bindparam("kalshi_compared_bid", type_=Float()),
                        bindparam("kalshi_compared_ask", type_=Float()),
                    )
                    if has_book
                    else None
                ),
            ),
            # #10090 `preview_from_commit`: the committed row's resolver
            # inputs, so its preview is composed without reading it back.
            FuturesOutcome.current_probability,
            FuturesOutcome.is_winner,
            FuturesOutcome.resolution_source,
        )
    )


KALSHI_PRICE_STATEMENTS: Mapping[bool, Update] = MappingProxyType(
    {has_book: _build_price_statement(has_book) for has_book in (False, True)}
)


def kalshi_price_parameters(
    outcome_id: int,
    probability: float,
    yes_bid: float | None,
    yes_ask: float | None,
    force_observation: bool = True,
) -> dict[str, int | float | bool]:
    """Fresh values for exactly one row; half/absent books write neither side."""
    parameters: dict[str, int | float | bool] = {
        "kalshi_outcome_id": outcome_id,
        "kalshi_stored_probability": probability,
        "kalshi_compared_probability": probability,
        "kalshi_force_observation": force_observation,
    }
    if yes_bid is not None and yes_ask is not None:
        parameters.update(
            kalshi_stored_bid=yes_bid,
            kalshi_stored_ask=yes_ask,
            kalshi_compared_bid=yes_bid,
            kalshi_compared_ask=yes_ask,
        )
    return parameters


def kalshi_skip_locked_stmt(rows) -> Select:
    """#10090: lock a phase's rows the UPDATEs will write, SKIP LOCKED.

    ``rows``: ``(outcome_id, probability, yes_bid, yes_ask, force)`` in phase
    order. The row locks are taken in that order, and only on a row the
    per-row statement would write: the same settled refusal and repeat
    predicate, at the same stored precision, so an unchanged row still takes
    no lock. Returns the ids such a row the lock SKIPPED (held by another
    transaction): explicit, never inferred from a missing RETURNING row,
    which an unchanged or settled row also is. Run in the phase's own
    transaction before its UPDATEs, which then find their rows already held.
    """
    table = FuturesOutcome.__table__
    rows = list(rows)
    given = (
        func.unnest(
            bindparam("skip_ids", [r[0] for r in rows], type_=ARRAY(Integer)),
            bindparam(
                "skip_probabilities", [r[1] for r in rows],
                type_=ARRAY(table.c.current_probability.type),
            ),
            bindparam(
                "skip_bids", [r[2] for r in rows], type_=ARRAY(table.c.current_yes_bid.type)
            ),
            bindparam(
                "skip_asks", [r[3] for r in rows], type_=ARRAY(table.c.current_yes_ask.type)
            ),
            bindparam(
                "skip_books", [r[2] is not None and r[3] is not None for r in rows],
                type_=ARRAY(Boolean),
            ),
            bindparam("skip_force", [bool(r[4]) for r in rows], type_=ARRAY(Boolean)),
        )
        .table_valued(
            column("id", Integer),
            column("probability", table.c.current_probability.type),
            column("bid", table.c.current_yes_bid.type),
            column("ask", table.c.current_yes_ask.type),
            column("has_book", Boolean),
            column("force", Boolean),
            with_ordinality="ord",
        )
        .render_derived(name="given")
    )
    wanted_rows = and_(
        _writable(),
        _observation_needed(
            given.c.force, given.c.probability,
            {"current_yes_bid": given.c.bid, "current_yes_ask": given.c.ask},
            has_book=given.c.has_book,
        ),
    )
    wanted = (
        select(table.c.id)
        .join_from(given, table, table.c.id == given.c.id)
        .where(wanted_rows)
        .cte("wanted")
        .prefix_with("MATERIALIZED")
    )
    locked = (
        select(table.c.id)
        .join_from(given, table, table.c.id == given.c.id)
        .where(wanted_rows)
        .order_by(given.c.ord)
        .with_for_update(of=table, skip_locked=True, key_share=True)
        .cte("locked")
        .prefix_with("MATERIALIZED")
    )
    return select(wanted.c.id).where(~exists().where(locked.c.id == wanted.c.id))
