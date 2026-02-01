"""Utility modules."""
from app.utils.odds_math import (
    american_to_probability,
    decimal_to_probability,
    remove_vig,
    moneyline_to_probability,
    project_scores,
    calculate_gei,
    format_probability,
    probability_to_american,
    aggregate_probabilities,
    aggregate_bookmaker_odds,
)
from app.utils.highlights import (
    compute_highlight,
    get_highlight_label,
    should_highlight,
    EventFlags,
    HighlightResult,
    get_league_tier,
)

__all__ = [
    "american_to_probability",
    "decimal_to_probability",
    "remove_vig",
    "moneyline_to_probability",
    "project_scores",
    "calculate_gei",
    "format_probability",
    "probability_to_american",
    "aggregate_probabilities",
    "aggregate_bookmaker_odds",
    "compute_highlight",
    "get_highlight_label",
    "should_highlight",
    "EventFlags",
    "HighlightResult",
    "get_league_tier",
]
