"""Deterministic market interestingness scoring utilities.

This module is intentionally pure: no database access, no network calls, and no
runtime feed integration. It provides a lightweight first slice for calibrating
future ranking signals against labeled rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from math import log10
from typing import Any


@dataclass(frozen=True)
class InterestingnessWeights:
    """Point weights for each normalized signal.

    Defaults sum to 100, so the final score is easy to read as a 0-100 score.
    """

    decisiveness: float = 15.0
    multi_source: float = 10.0
    recency: float = 12.0
    movement: float = 16.0
    resolution_proximity: float = 12.0
    category_novelty: float = 10.0
    volume: float = 15.0
    llm_quality: float = 10.0

    @property
    def total(self) -> float:
        return (
            self.decisiveness
            + self.multi_source
            + self.recency
            + self.movement
            + self.resolution_proximity
            + self.category_novelty
            + self.volume
            + self.llm_quality
        )


DEFAULT_WEIGHTS = InterestingnessWeights()


@dataclass(frozen=True)
class MarketInterestingnessInputs:
    """Input signals for market interestingness scoring.

    Probability and movement values accept either fractions (0.72, 0.08) or
    percentage-style values (72, 8). Dates accept datetimes, dates, or ISO
    strings.
    """

    probability: float | None = None
    source_count: int | None = None
    updated_at: datetime | date | str | None = None
    movement_24h: float | None = None
    resolution_date: datetime | date | str | None = None
    category: str | None = None
    category_recent_count: int | None = None
    category_feed_share: float | None = None
    volume_24h: float | None = None
    llm_quality: float | None = None

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "MarketInterestingnessInputs":
        """Build inputs from common CSV/JSON field names."""

        return cls(
            probability=_first_present(
                row,
                "probability",
                "leader_probability",
                "current_probability",
                "yes_probability",
            ),
            source_count=_first_present(row, "source_count", "sources"),
            updated_at=_first_present(row, "updated_at", "last_updated", "captured_at"),
            movement_24h=_first_present(
                row,
                "movement_24h",
                "probability_change_24h",
                "change_24h",
            ),
            resolution_date=_first_present(
                row,
                "resolution_date",
                "close_time",
                "end_date",
                "resolve_by",
            ),
            category=_first_present(row, "category", "llm_sport_category"),
            category_recent_count=_first_present(
                row,
                "category_recent_count",
                "category_impressions",
                "recent_category_count",
            ),
            category_feed_share=_first_present(
                row,
                "category_feed_share",
                "category_share",
            ),
            volume_24h=_first_present(row, "volume_24h", "volume", "volume_24hr"),
            llm_quality=_first_present(
                row,
                "llm_quality",
                "hook_quality",
                "explanation_quality",
            ),
        )


@dataclass(frozen=True)
class MarketInterestingnessScore:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    normalized_signals: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def score_market_interestingness(
    inputs: MarketInterestingnessInputs | dict[str, Any],
    *,
    now: datetime | None = None,
    weights: InterestingnessWeights = DEFAULT_WEIGHTS,
) -> MarketInterestingnessScore:
    """Score a market from deterministic signals.

    Returns a 0-100 score plus component details. Missing signals contribute 0
    except category novelty and LLM quality, which get conservative neutral
    defaults because unlabeled rows should still be scoreable during calibration.
    """

    if isinstance(inputs, dict):
        inputs = MarketInterestingnessInputs.from_mapping(inputs)

    now = _coerce_datetime(now) or datetime.now(timezone.utc)
    signals = {
        "decisiveness": decisiveness_signal(inputs.probability),
        "multi_source": multi_source_signal(inputs.source_count),
        "recency": recency_signal(inputs.updated_at, now=now),
        "movement": movement_signal(inputs.movement_24h),
        "resolution_proximity": resolution_proximity_signal(
            inputs.resolution_date, now=now
        ),
        "category_novelty": category_novelty_signal(
            recent_count=inputs.category_recent_count,
            feed_share=inputs.category_feed_share,
        ),
        "volume": volume_signal(inputs.volume_24h),
        "llm_quality": llm_quality_signal(inputs.llm_quality),
    }

    components = {
        name: round(value * getattr(weights, name), 4)
        for name, value in signals.items()
    }
    raw_score = sum(components.values())
    normalized_score = raw_score / weights.total * 100 if weights.total > 0 else 0.0

    return MarketInterestingnessScore(
        score=round(_clamp(normalized_score, 0.0, 100.0), 2),
        components=components,
        normalized_signals={k: round(v, 4) for k, v in signals.items()},
        reasons=_build_reasons(signals),
    )


def decisiveness_signal(probability: float | str | None) -> float:
    """Return a sweet-spot signal for non-settled markets with a visible leader."""

    prob = _normalize_probability(probability)
    if prob is None:
        return 0.0

    leader = max(prob, 1.0 - prob)
    if leader <= 0.52:
        return 0.35
    if leader <= 0.75:
        return _interpolate(leader, 0.52, 0.75, 0.35, 1.0)
    if leader <= 0.95:
        return _interpolate(leader, 0.75, 0.95, 1.0, 0.2)
    return _interpolate(min(leader, 0.99), 0.95, 0.99, 0.2, 0.0)


def multi_source_signal(source_count: int | str | None) -> float:
    count = _coerce_int(source_count)
    if count is None or count <= 1:
        return 0.0
    if count == 2:
        return 0.7
    return 1.0


def recency_signal(
    updated_at: datetime | date | str | None,
    *,
    now: datetime | None = None,
) -> float:
    timestamp = _coerce_datetime(updated_at)
    if timestamp is None:
        return 0.0

    now = _coerce_datetime(now) or datetime.now(timezone.utc)
    age_hours = max(0.0, (now - timestamp).total_seconds() / 3600)
    if age_hours <= 0.5:
        return 1.0
    if age_hours <= 6:
        return _interpolate(age_hours, 0.5, 6, 1.0, 0.75)
    if age_hours <= 24:
        return _interpolate(age_hours, 6, 24, 0.75, 0.35)
    if age_hours <= 168:
        return _interpolate(age_hours, 24, 168, 0.35, 0.0)
    return 0.0


def movement_signal(movement_24h: float | str | None) -> float:
    movement = _normalize_probability(movement_24h, allow_negative=True)
    if movement is None:
        return 0.0

    magnitude = abs(movement)
    if magnitude >= 0.25:
        return 1.0
    if magnitude >= 0.10:
        return _interpolate(magnitude, 0.10, 0.25, 0.65, 1.0)
    if magnitude >= 0.03:
        return _interpolate(magnitude, 0.03, 0.10, 0.2, 0.65)
    return _interpolate(magnitude, 0.0, 0.03, 0.0, 0.2)


def resolution_proximity_signal(
    resolution_date: datetime | date | str | None,
    *,
    now: datetime | None = None,
) -> float:
    resolved_at = _coerce_datetime(resolution_date)
    if resolved_at is None:
        return 0.0

    now = _coerce_datetime(now) or datetime.now(timezone.utc)
    days_until = (resolved_at - now).total_seconds() / 86400
    if days_until < 0:
        return 0.0
    if days_until <= 1:
        return 1.0
    if days_until <= 7:
        return _interpolate(days_until, 1, 7, 1.0, 0.9)
    if days_until <= 30:
        return _interpolate(days_until, 7, 30, 0.9, 0.55)
    if days_until <= 90:
        return _interpolate(days_until, 30, 90, 0.55, 0.2)
    return 0.1


def category_novelty_signal(
    *,
    recent_count: int | str | None = None,
    feed_share: float | str | None = None,
) -> float:
    """Score how underrepresented the market's category is in the current set."""

    values: list[float] = []
    count = _coerce_int(recent_count)
    if count is not None:
        if count <= 0:
            values.append(1.0)
        elif count <= 2:
            values.append(0.8)
        elif count <= 5:
            values.append(0.55)
        elif count <= 10:
            values.append(0.3)
        else:
            values.append(0.1)

    share = _normalize_probability(feed_share)
    if share is not None:
        if share <= 0.05:
            values.append(1.0)
        elif share <= 0.20:
            values.append(_interpolate(share, 0.05, 0.20, 1.0, 0.55))
        elif share <= 0.50:
            values.append(_interpolate(share, 0.20, 0.50, 0.55, 0.1))
        else:
            values.append(0.0)

    if not values:
        return 0.5
    return min(values)


def volume_signal(volume_24h: float | str | None) -> float:
    volume = _coerce_float(volume_24h)
    if volume is None or volume <= 0:
        return 0.0
    return _clamp(log10(volume + 1) / 5.0, 0.0, 1.0)


def llm_quality_signal(llm_quality: float | str | None) -> float:
    quality = _coerce_float(llm_quality)
    if quality is None:
        return 0.5
    if quality > 1.0:
        quality = quality / 10.0
    return _clamp(quality, 0.0, 1.0)


def _build_reasons(signals: dict[str, float]) -> list[str]:
    labels = {
        "decisiveness": "decisive_but_not_settled",
        "multi_source": "multi_source",
        "recency": "fresh",
        "movement": "moving",
        "resolution_proximity": "resolving_soon",
        "category_novelty": "category_novelty",
        "volume": "trading_volume",
        "llm_quality": "quality_explanation",
    }
    return [labels[name] for name, value in signals.items() if value >= 0.7]


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_probability(
    value: float | str | None,
    *,
    allow_negative: bool = False,
) -> float | None:
    number = _coerce_float(value)
    if number is None:
        return None
    if abs(number) > 1.0:
        number = number / 100.0
    lower = -1.0 if allow_negative else 0.0
    return _clamp(number, lower, 1.0)


def _coerce_datetime(value: datetime | date | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_float(value: float | str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: int | str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _interpolate(
    value: float,
    left: float,
    right: float,
    left_score: float,
    right_score: float,
) -> float:
    if right == left:
        return right_score
    ratio = _clamp((value - left) / (right - left), 0.0, 1.0)
    return left_score + ratio * (right_score - left_score)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
