"""#698 — what a settled detail row may SAY about its own result.

A read-only display contract, served beside `is_winner` / `resolution_source`
on `/api/futures/{id}` outcomes. It writes nothing and changes no stored flag,
price, opening/calibration field, source tier, market shape or filter.

## Why the two existing fields are not enough

`/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, Polymarket, resolved)
stores BOTH legs as `current_probability 0.500000, is_winner false,
resolution_source 'clob_authoritative'`. The renderer's verdict rule
(`OutcomeRow.outcomeRowVerdict`) reads only the grade and the source, so a
resolved market with a sourced `false` printed **Lost · 0% · Settled** on both
rows — a literal 0% the stored data never contained, over a price that says
nothing was decided. A tier-3 source name is provenance, not a statement that
this exact token received a definite binary payout: `false` is also the column
DEFAULT (#4788), and a 50/50 last price is what a void, a refund, an unconfirmed
call or a stale book can all look like. Whether this match voided is UNKNOWN —
the venue read stopped on a 403 and was not retried — and this module does not
decide it.

So the contract states only what the STORED row supports:

- a finite stored price strictly between 0 and 1 is never a result, whatever the
  grade or source says (`nonterminal_stored_price`) — no rounding threshold, so
  0.001 / 0.999 are unknown too;
- exact 1 + `true`, or exact 0 + `false`, with a recognised grade source and no
  retraction, is a result (`stored_terminal_agreement`). That is two stored
  fields agreeing, NOT independent venue verification, and the basis says so;
- anything missing, unrecognised, retracted, invalid or disagreeing is unknown,
  with a basis naming which. A missing value is never read as zero.

Every outcome is judged on its own row. There is deliberately NO pair or field
rule: a genuinely independent field (`12194657`, ten candidates at 0/false)
can settle with no affirmative winner, so all-losses is not a contradiction,
and this serializer carries no existing explicit complementary-pair identity to
build a pair rule on. Generalising quantity/field/duel boards into pairs would
be the guess this contract exists to stop making.

## Scope

Resolved Polymarket markets only (`applies_to_market`). Every outcome on a
targeted payload carries the object, so a client can tell "this server says
unknown" from "this server predates the field". Other sources' graded-priceless
contracts (#10066 / #10964) are untouched because they are not targeted.

Pure module: imports only `resolution_authority`, no DB or network.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.utils.resolution_authority import KNOWN_SOURCES

# Mirror of `RETRACTION_SOURCE` in `app/utils/kalshi_fabricated_loss.py` and of
# `RETRACTED_RESOLUTION_SOURCE` in `frontend/components/futures/OutcomeRow.tsx`.
RETRACTED_SOURCE = "ungradeable_result"

VERDICT_WON = "won"
VERDICT_LOST = "lost"
VERDICT_UNKNOWN = "unknown"

BASIS_TERMINAL_AGREEMENT = "stored_terminal_agreement"
BASIS_NONTERMINAL_PRICE = "nonterminal_stored_price"
BASIS_CONFLICTING = "conflicting_stored_evidence"
BASIS_RETRACTED = "retracted_grade"
BASIS_MISSING_SOURCE = "missing_grade_source"
BASIS_UNRECOGNIZED_SOURCE = "unrecognized_grade_source"
BASIS_MISSING_GRADE = "missing_grade"
BASIS_MISSING_PRICE = "missing_stored_price"
BASIS_INVALID_PRICE = "invalid_stored_price"

TARGETED_SOURCES: frozenset[str] = frozenset({"polymarket"})


def applies_to_market(market: Any) -> bool:
    """True when this market's detail outcomes carry `settlement_display`."""
    return (
        getattr(market, "source", None) in TARGETED_SOURCES
        and getattr(market, "status", None) == "resolved"
    )


def _stored_price(value: Any) -> tuple[Optional[Decimal], Optional[str]]:
    """The stored price as an exact Decimal, or the basis that refuses it."""
    if value is None:
        return None, BASIS_MISSING_PRICE
    if isinstance(value, bool):
        return None, BASIS_INVALID_PRICE
    try:
        price = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None, BASIS_INVALID_PRICE
    if not price.is_finite() or price < 0 or price > 1:
        return None, BASIS_INVALID_PRICE
    return price, None


def settlement_display(
    *,
    is_winner: Optional[bool],
    resolution_source: Optional[str],
    stored_probability: Any,
) -> dict[str, str]:
    """`{"verdict": won|lost|unknown, "basis": <stored evidence>}` for one row.

    Read from the STORED row (`current_probability`), never from the served
    number, which later display steps may normalise or withhold.
    """

    def unknown(basis: str) -> dict[str, str]:
        return {"verdict": VERDICT_UNKNOWN, "basis": basis}

    # The retraction is refused first and unconditionally, exactly as the
    # renderer's own rule does: a leg we declared unknowable is never a result.
    if resolution_source == RETRACTED_SOURCE:
        return unknown(BASIS_RETRACTED)
    if not resolution_source:
        return unknown(BASIS_MISSING_SOURCE)
    if resolution_source not in KNOWN_SOURCES:
        return unknown(BASIS_UNRECOGNIZED_SOURCE)
    if is_winner is None:
        return unknown(BASIS_MISSING_GRADE)
    price, refused = _stored_price(stored_probability)
    if price is None:
        return unknown(refused or BASIS_INVALID_PRICE)
    if 0 < price < 1:
        return unknown(BASIS_NONTERMINAL_PRICE)
    if price == 1 and is_winner is True:
        return {"verdict": VERDICT_WON, "basis": BASIS_TERMINAL_AGREEMENT}
    if price == 0 and is_winner is False:
        return {"verdict": VERDICT_LOST, "basis": BASIS_TERMINAL_AGREEMENT}
    return unknown(BASIS_CONFLICTING)
