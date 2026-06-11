"""Shared staleness detection for category routes and the Discover feed.

Pure functions — no I/O, no DB. Determines whether a market's title implies
the real-world event has passed (e.g., "Eurovision" after May 31).
"""

import re
from datetime import datetime, timedelta, timezone

_MONTH_NAME_TO_NUMBER = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_EXPLICIT_MONTH_DAY_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
    re.IGNORECASE,
)

_RECURRING_MARKET_EVENT_END_RULES: tuple[
    tuple[re.Pattern, tuple[int, int], int], ...
] = (
    (re.compile(r"\beurovision\b", re.IGNORECASE), (5, 31), 0),
    (re.compile(r"\b(australian open)\b", re.IGNORECASE), (2, 2), 2),
    (re.compile(r"\b(french open|roland garros)\b", re.IGNORECASE), (6, 8), 0),
    (re.compile(r"\bwimbledon\b", re.IGNORECASE), (7, 15), 2),
    (re.compile(r"\bus open\b", re.IGNORECASE), (9, 15), 2),
)

PROBABILITY_EXTREME_LOW = 0.02
PROBABILITY_EXTREME_HIGH = 0.98


def _implied_year_from_market_name(market_name: str, now: datetime) -> int:
    years = [int(year) for year in re.findall(r"\b(20\d{2})\b", market_name)]
    return max(years) if years else now.year


def infer_market_real_world_end(
    market_name: str | None,
    sport_category: str | None,
    now: datetime,
) -> tuple[datetime, str, int] | None:
    """Infer when the real-world question stopped being current."""
    name = market_name or ""
    if not name:
        return None

    explicit_matches = list(_EXPLICIT_MONTH_DAY_RE.finditer(name))
    if explicit_matches:
        match = explicit_matches[-1]
        month = _MONTH_NAME_TO_NUMBER[match.group(1).lower().rstrip(".")]
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        try:
            implied_end = datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        except ValueError:
            return None
        grace_days = 7 if re.search(r"\bweek of\b", name, re.IGNORECASE) else 1
        return implied_end, "explicit_title_date", grace_days

    event_year = _implied_year_from_market_name(name, now)
    if event_year > now.year:
        return None

    sport_lower = (sport_category or "").lower()
    for pattern, (month, day), grace_days in _RECURRING_MARKET_EVENT_END_RULES:
        if not pattern.search(name):
            continue
        if pattern.pattern == r"\bus open\b" and sport_lower != "tennis":
            continue
        implied_end = datetime(event_year, month, day, 23, 59, 59, tzinfo=timezone.utc)
        return implied_end, "recurring_event_calendar", grace_days

    return None


def is_title_implied_stale(
    market_name: str | None,
    sport_category: str | None,
    now: datetime,
) -> str | None:
    """Return a stale reason string if the market's title implies it's over, else None."""
    inferred = infer_market_real_world_end(market_name, sport_category, now)
    if not inferred:
        return None
    implied_end, reason, grace_days = inferred
    if now > implied_end + timedelta(days=grace_days):
        return f"stale_{reason}"
    return None


def is_probability_extreme(probability: float | None) -> bool:
    """True if the leader probability is at a dead extreme (<2% or >98%)."""
    if probability is None:
        return False
    return probability < PROBABILITY_EXTREME_LOW or probability > PROBABILITY_EXTREME_HIGH


def should_exclude_from_featured(
    market_name: str | None,
    sport_category: str | None,
    status: str | None,
    leader_probability: float | None,
    now: datetime,
) -> str | None:
    """Return a reason to exclude from featured sections, or None if OK.

    Checks: resolved status, probability extremes, title-implied staleness.
    """
    if status and status != "open":
        return "resolved"
    if is_probability_extreme(leader_probability):
        return "probability_extreme"
    return is_title_implied_stale(market_name, sport_category, now)
