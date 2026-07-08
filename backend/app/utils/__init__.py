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
    detect_reversed_bookmakers,
)
from app.utils.highlights import (
    compute_highlight,
    compute_time_series_metrics,
    get_highlight_label,
    should_highlight,
    EventFlags,
    HighlightResult,
    TimeSeriesMetrics,
    get_league_tier,
    get_season_multiplier,
)
from app.utils.pulse import (
    calculate_pulse,
    get_pulse_status,
    get_pulse_emoji,
    get_pulse_label,
    PulseDataPoint,
    PulseComponents,
    PulseResult,
)
from app.utils.futures_categorization import (
    categorize_market,
    categorize_by_rules,
)
from app.utils.futures_highlights import (
    compute_futures_highlight,
    FuturesFlags,
    FuturesHighlightResult,
)
from app.utils.feed_reasons import (
    generate_event_reason,
    generate_futures_reason,
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
    "detect_reversed_bookmakers",
    "compute_highlight",
    "get_highlight_label",
    "should_highlight",
    "EventFlags",
    "HighlightResult",
    "get_league_tier",
    "get_season_multiplier",
    "calculate_pulse",
    "get_pulse_status",
    "get_pulse_emoji",
    "get_pulse_label",
    "PulseDataPoint",
    "PulseComponents",
    "PulseResult",
    "categorize_market",
    "categorize_by_rules",
    "compute_futures_highlight",
    "FuturesFlags",
    "FuturesHighlightResult",
    "generate_event_reason",
    "generate_futures_reason",
]
