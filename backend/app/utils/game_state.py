"""Display helpers for live game state labels."""

from __future__ import annotations

import re


_BASEBALL_HALF_ALIASES = {
    "top": "Top",
    "t": "Top",
    "bot": "Bottom",
    "bottom": "Bottom",
    "b": "Bottom",
    "mid": "Mid",
    "middle": "Mid",
    "end": "End",
}
_NON_BASEBALL_PERIODS = {"1h", "2h", "ht", "halftime", "1st half", "2nd half"}


def _ordinal_inning(value: str) -> str | None:
    try:
        inning = int(value)
    except (TypeError, ValueError):
        return None
    if inning <= 0:
        return None
    if 10 <= inning % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(inning % 10, "th")
    return f"{inning}{suffix}"


def _baseball_inning_label(value: str | None) -> str | None:
    if not value:
        return None

    text = str(value).strip()
    lowered = text.lower().strip()
    if lowered in _NON_BASEBALL_PERIODS:
        return None

    half_match = re.search(
        r"\b(top|t|bot|bottom|b|mid|middle|end)\b(?:\s+of)?\s+"
        r"(?:the\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if half_match:
        half = _BASEBALL_HALF_ALIASES[half_match.group(1)]
        inning = _ordinal_inning(half_match.group(2))
        return f"{half} {inning}" if inning else None

    inning_match = re.search(
        r"\b(?:inning\s+)?(\d+)(?:st|nd|rd|th)?(?:\s+inning)?\b",
        lowered,
    )
    if inning_match and ("inning" in lowered or lowered.isdigit()):
        return _ordinal_inning(inning_match.group(1))

    return None


def normalize_live_game_state(
    sport_key: str | None,
    period: str | None,
    game_clock: str | None,
) -> tuple[str | None, str | None]:
    """Return display-safe ``(period, game_clock)`` for API payloads."""
    if not sport_key or not sport_key.startswith("baseball"):
        return period, game_clock

    inning_label = _baseball_inning_label(period) or _baseball_inning_label(game_clock)
    return inning_label, None
