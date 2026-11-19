"""#13000 (Decision 250-A): single predicate for ``score_source_unavailable``.

Distinguishes a live match with NO score feed carrying it (for example an ATP
Challenger or ITF tennis match, or an unmapped niche league) from a covered
match whose score has not moved yet or a scheduled/finished match.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING

_LIVE_SCORE_STATUSES = frozenset({"live", "in_progress"})
_NON_SCOREBOARD_COVERED_PREFIXES = ("golf_", "mma_", "boxing_")


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def event_score_source_unavailable(
    event: Any,
    *,
    sport_key: Optional[str] = None,
    status: Optional[str] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True when this live match has no score feed carrying it (#13000, 250-A)."""
    raw_status = status if status is not None else getattr(event, "status", None)
    normalized_status = (
        raw_status.strip().lower() if isinstance(raw_status, str) else ""
    )
    if normalized_status not in _LIVE_SCORE_STATUSES:
        return False

    # Any score, observation clock, period, or tennis linescore proves a source.
    home_score = (
        payload.get("home_score")
        if isinstance(payload, Mapping) and "home_score" in payload
        else getattr(event, "home_score", None)
    )
    away_score = (
        payload.get("away_score")
        if isinstance(payload, Mapping) and "away_score" in payload
        else getattr(event, "away_score", None)
    )
    if home_score is not None or away_score is not None:
        return False

    if (
        getattr(event, "score_observed_at", None) is not None
        or _non_empty_str(getattr(event, "score_source", None))
        or _non_empty_str(getattr(event, "period", None))
    ):
        return False

    if isinstance(payload, Mapping):
        if (
            payload.get("linescore") is not None
            or payload.get("score_observed_at") is not None
            or _non_empty_str(payload.get("score_source"))
            or _non_empty_str(payload.get("period"))
        ):
            return False

    # An ESPN competition anchor proves ESPN covers this match.
    if _non_empty_str(getattr(event, "espn_id", None)):
        return False

    resolved_sport = sport_key
    if not _non_empty_str(resolved_sport):
        resolved_sport = getattr(getattr(event, "sport", None), "key", None)
    if not _non_empty_str(resolved_sport) and isinstance(payload, Mapping):
        resolved_sport = payload.get("sport") or payload.get("sport_key")
    if not _non_empty_str(resolved_sport):
        return False

    key = str(resolved_sport).strip().lower()
    if key.startswith("tennis"):
        # Main-tour ATP/WTA and ESPN-covered 125s carry `espn_id` or a live
        # StatPal/ESPN score; live Challenger/ITF matches have neither.
        return True

    if key in ESPN_SPORT_MAPPING or key in STATPAL_SPORT_MAPPING:
        return False
    if key.startswith(_NON_SCOREBOARD_COVERED_PREFIXES):
        return False
    return True
