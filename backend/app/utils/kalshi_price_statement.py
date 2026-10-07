"""#10689: reuse Kalshi price expressions, preserving ordinary per-row execute.

The two Core statements are constructed once. Their storage binds use the
columns' Numeric types; comparison binds retain the original scalar Float
inputs before the canonical helpers cast to stored precision. Sharing a bind
between these roles changes asyncpg SQL/types, even when values are identical.
No transaction, row ordering, result accounting or writer policy lives here.
"""

from collections.abc import Mapping
from types import MappingProxyType

from sqlalchemy import Float, Integer, bindparam, func, or_, update
from sqlalchemy.sql.dml import Update

from app.models.models import FuturesOutcome
from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column
from app.utils.resolution_authority import AUTHORITATIVE_SOURCES


def _build_price_statement(has_book: bool) -> Update:
    table = FuturesOutcome.__table__
    return (
        update(table)
        .where(
            FuturesOutcome.id == bindparam("kalshi_outcome_id", type_=Integer()),
            or_(
                FuturesOutcome.resolution_source.is_(None),
                FuturesOutcome.resolution_source.notin_(sorted(AUTHORITATIVE_SOURCES)),
            ),
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
) -> dict[str, int | float]:
    """Fresh values for exactly one row; half/absent books write neither side."""
    parameters: dict[str, int | float] = {
        "kalshi_outcome_id": outcome_id,
        "kalshi_stored_probability": probability,
        "kalshi_compared_probability": probability,
    }
    if yes_bid is not None and yes_ask is not None:
        parameters.update(
            kalshi_stored_bid=yes_bid,
            kalshi_stored_ask=yes_ask,
            kalshi_compared_bid=yes_bid,
            kalshi_compared_ask=yes_ask,
        )
    return parameters
