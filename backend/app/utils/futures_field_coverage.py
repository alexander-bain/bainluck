"""Whether a field's available prices support a leader on a card."""

import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from math import fsum, isfinite
from typing import Any


_TOP_PLACES = re.compile(r"^\s*top\s+([1-9][0-9]?|five)\s+\S", re.IGNORECASE)
_CHAMPIONSHIP_FINALISTS = re.compile(
    r"\bteams? to (?:reach|make|advance to|qualify for)\b.*\bchampionship game\s*[?!.]?$",
    re.IGNORECASE,
)
_WORLD_SERIES_FINALISTS = re.compile(
    r"\bteams? to advance to\b.*\bworld series\s*[?!.]?$",
    re.IGNORECASE,
)


def has_limited_field_price_coverage(data: Mapping[str, object]) -> bool:
    return (
        data.get("status") == "open"
        and data.get("field_price_coverage_incomplete") is True
    )


def field_winner_places(
    title: str, mutually_exclusive: bool | None, expected_winners: int | None = None
) -> int | None:
    """Only assign a place count when the contract supplies one."""
    top_places = _TOP_PLACES.match(title)
    if top_places:
        count = top_places[1]
        return 5 if count.casefold() == "five" else int(count)
    if _CHAMPIONSHIP_FINALISTS.search(title) or _WORLD_SERIES_FINALISTS.search(title):
        return 2
    if type(expected_winners) is int and expected_winners > 0:
        return expected_winners
    return 1 if mutually_exclusive is True else None


def field_leader_is_unsupported(
    probabilities: Iterable[float | Decimal | None],
    remaining_places: int | None,
    *,
    open_outcome_count: int,
    omitted_contender: bool,
    missing_price_ceiling: float | None = None,
) -> bool:
    """Use the whole screened field, never the top rows or a rescaled sum."""
    if remaining_places is not None and remaining_places <= 0:
        return False
    priced: list[float] = []
    for probability in probabilities:
        if probability is None or not isfinite(probability) or not 0 <= probability <= 1:
            omitted_contender = True
        else:
            priced.append(float(probability))
    if remaining_places is None:
        return 2 * len(priced) < open_outcome_count

    total = fsum(priced)
    if total < 0.5 * remaining_places:
        return True
    # Half the field's mass is a floor. In a partial field even above that
    # floor, the unaccounted mass can still hide a favorite or a tied leader.
    leader = max(priced)
    return (
        omitted_contender
        and remaining_places - total >= leader
        and (missing_price_ceiling is None or missing_price_ceiling >= leader)
    )


def greatest_trusted_ask_ceiling(asks: Iterable[float | Decimal | None]) -> float | None:
    """Bound all missing prices only when every missing row has a usable ask."""
    from app.utils.kalshi_empty_book import ASK_ONLY_TRUSTED_MAX

    greatest = None
    for ask in asks:
        if ask is None or not isfinite(ask) or not 0 < ask <= ASK_ONLY_TRUSTED_MAX:
            return None
        greatest = max(greatest or 0, float(ask))
    return greatest


def grouped_field_leader_is_unsupported(
    detail: Mapping[str, Any], *, expected_winners: int | None, group_type: str | None
) -> bool:
    """Check a grouped member's screened prices before display allocation."""
    from app.utils.discover_card_archetypes import classify_discover_card_archetype
    from app.utils.futures_unsupported_price import row_carries_a_verdict

    if (
        detail.get("status") != "open"
        or detail.get("market_type") not in ("field", "participation")
        or detail.get("ladder_treatment_refused")
    ):
        return False

    outcomes = detail["outcomes"]
    card = classify_discover_card_archetype(
        name=detail["name"], category=detail.get("llm_sport_category"),
        outcomes=outcomes, outcome_count=len(outcomes),
        source_count=1, sources=[detail["source"]], group_id=detail.get("group_id"),
        group_type=group_type, canonical_market_key=detail.get("canonical_market_key"),
        status=detail["status"], resolution_date=detail.get("resolution_date"),
    )
    if card["suggested_format"] != "outcome_distribution":
        return False

    places = field_winner_places(detail["name"], detail.get("mutually_exclusive"), expected_winners)
    open_prices = []
    missing_asks = []
    for row in outcomes:
        source_state = (row.get("source_mark") or {}).get("state")
        if source_state == "settled" or row_carries_a_verdict(row.get("resolution_source")):
            if places is not None and row.get("is_winner") is True:
                places -= 1
        else:
            probability = row["probability"]
            no_bid = detail["source"] == "kalshi" and row.get("kalshi_no_bid")
            if probability is None or not isfinite(probability) or not 0 <= probability <= 1:
                missing_asks.append(row.get("ask_ceiling") if no_bid else None)
            open_prices.append(probability)
    # The full set has already received its verified prices. A previously
    # withheld row can have an accepted price after the venue composition.
    return field_leader_is_unsupported(
        open_prices,
        places,
        open_outcome_count=len(open_prices),
        omitted_contender=False,
        missing_price_ceiling=greatest_trusted_ask_ceiling(missing_asks) if places == 1 else None,
    )
