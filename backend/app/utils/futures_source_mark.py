"""Futures provenance from the inputs used by the existing reader (#12581).

Outcome touch times and cached history are not clocks bound to these prices.
Keep their ages unknown until the writer supplies that evidence.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    DETERMINISTIC_SOURCES,
    PRICE_DERIVED_SOURCES,
)
from app.utils.source_mark import no_source_mark, quote_source_mark, settled_source_mark
from app.utils.settlement_display import applies_to_market, settlement_display

_RESULT_SOURCES = (
    AUTHORITATIVE_SOURCES - PRICE_DERIVED_SOURCES
) | DETERMINISTIC_SOURCES


def describe_field_normalization(
    mark: dict,
    *,
    input_probability: float | Decimal | None,
    displayed_probability: float | Decimal | None,
) -> None:
    """Explain the existing field scaling without altering inputs or arithmetic."""
    if (
        mark.get("state") not in {"single", "blend"}
        or input_probability is None
        or displayed_probability is None
        or abs(float(input_probability) - float(displayed_probability)) < 1e-8
    ):
        return
    mark["method"] = (
        mark.get("method", "Bain Luck field")
        + " · scaled with the other outcomes to total 100%"
    )


def futures_outcome_source_mark(market: Any, outcome: Any, row: dict) -> dict:
    """Retain the venue input before field normalization; never reprice it."""
    settlement = row.get("settlement_display")
    if isinstance(settlement, dict) and settlement.get("verdict") == "unknown":
        return no_source_mark("result_unknown")
    grade = getattr(outcome, "is_winner", None)
    authority = getattr(outcome, "resolution_source", None)
    # The sheet calls this an official result. Price/clock guesses and a
    # retracted grade cannot supply it, even when the stored flag is boolean.
    if type(grade) is bool and authority in _RESULT_SOURCES:
        return settled_source_mark(authority, "Won" if grade else "Lost")
    if (
        authority == "ungradeable_result"
        or getattr(market, "status", None) == "resolved"
    ):
        return no_source_mark("result_unknown")
    if row.get("probability") is None:
        return no_source_mark("no_probability")
    return quote_source_mark(
        [
            {
                "key": getattr(market, "source", None),
                "probability": getattr(outcome, "current_probability", None),
                "observed_at": None,
            }
        ]
    )


def verified_futures_source_mark(
    inputs: Iterable[tuple[str, float]],
    probability: float | None,
    rule: str,
) -> dict:
    """The compositor's admitted quotes, including its divergence selection."""
    if probability is None:
        return no_source_mark("no_probability")
    method = {
        "equal_weight_midpoint": "Bain Luck blend · the average of these sources",
        "weighted_median": "Bain Luck blend · the weighted middle of these sources",
    }.get(rule)
    return quote_source_mark(
        (
            {"key": key, "probability": value, "observed_at": None}
            for key, value in inputs
        ),
        method=method,
    )


def futures_card_source_mark(
    market: Any, outcome: Any, row: dict, *, verified: Any = None
) -> dict:
    """Explain a card's final value using its original row or held composition.

    Cards do not all carry the detail settlement object, so ask that same
    contract before calling a stored grade official. No clock or read is added.
    """
    evidence = row
    if applies_to_market(market):
        evidence = {
            **row,
            "settlement_display": settlement_display(
                is_winner=getattr(outcome, "is_winner", None),
                resolution_source=getattr(outcome, "resolution_source", None),
                stored_probability=getattr(outcome, "current_probability", None),
            ),
        }
    mark = futures_outcome_source_mark(market, outcome, evidence)
    input_probability = getattr(outcome, "current_probability", None)
    if (
        verified is not None
        and mark["state"] != "settled"
        and mark.get("reason") != "result_unknown"
    ):
        overlay = verified.overlay.get(outcome.id)
        mark = verified_futures_source_mark(
            overlay.source_inputs if overlay is not None else (),
            row["probability"],
            overlay.aggregation_rule if overlay is not None else "unsupported",
        )
        input_probability = overlay.probability if overlay is not None else None
    describe_field_normalization(
        mark,
        input_probability=input_probability,
        displayed_probability=row["probability"],
    )
    return mark


def mark_futures_card_rows(market: Any, rows: list[dict]) -> None:
    """Attach marks to the already selected source-card rows, without repricing."""
    outcomes = {o.id: o for o in market.outcomes}
    for row in rows:
        row["source_mark"] = futures_card_source_mark(
            market, outcomes[row["id"]], row,
        )
