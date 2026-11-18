"""Price evidence for the selected winner-field inputs on a golf card."""

from __future__ import annotations

from math import isclose
from typing import Any

from app.utils.source_mark import no_source_mark, quote_source_mark, settled_source_mark


def golfer_price_mark(data: dict[str, Any], displayed: float) -> dict:
    """Bind the original quotes before either stage of field normalization."""
    admitted = data["sources"]
    members = data.get("comparison_members", {})
    if not admitted or members.keys() != admitted.keys():
        return no_source_mark("source_evidence_incomplete")

    mark = quote_source_mark(
        (
            {
                "key": getattr(market, "source", None),
                "probability": getattr(outcome, "current_probability", None),
            }
            for market, outcome in members.values()
        ),
        method="Bain Luck blend · the average of these sources",
    )
    if mark["state"] == "none":
        return mark

    # The golfer's own sources can be scaled before the mean. An exclusive
    # field can also be scaled after the mean. Display rounding happens later.
    scaled_inputs = any(
        not isclose(admitted[key], float(outcome.current_probability), abs_tol=1e-9)
        for key, (_, outcome) in members.items()
    )
    if scaled_inputs:
        mark["method"] = (
            "Bain Luck blend · average after scaling the individual winner fields"
            if mark["state"] == "blend"
            else "Bain Luck field · source price scaled across the winner field"
        )
    mean = sum(admitted.values()) / len(admitted)
    if not isclose(mean, displayed, abs_tol=1e-9):
        mark["method"] = (
            mark.get("method", "Bain Luck field")
            + " · scaled with the other golfers to total 100%"
        )
    return mark


def golfer_result_mark(name: str | None, matched_champion: str | None) -> dict:
    if not matched_champion or not name:
        return no_source_mark("result_unknown")
    return settled_source_mark("espn", "Won" if name == matched_champion else "Lost")
