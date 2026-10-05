"""Pure projection of a served event-detail reading, never a raw database row.

The caller supplies one coherent response from get_event, including its folded
hero and producer clocks. No fetch time, row updated_at, or current-odds timestamp
may substitute for the clock of the selected reading. Delivery is a separate owner.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
import math

from app.utils.activitykit_payload import GameActivitySnapshot, Lifecycle
from app.utils.draw_priced_winner import sport_prices_a_draw
from app.utils.graded_card import rendered_duel_percents, rendered_percent
from app.utils.settled_hero import is_finished_status


def _probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def _clock(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _lifecycle(status: object) -> Lifecycle:
    normalized = status.strip().lower() if isinstance(status, str) else None
    # Same provider alias as the phone-only EventState adapter.
    canonical = "completed" if normalized == "final" else normalized
    if is_finished_status(canonical):
        return "closed" if canonical == "closed" else "final"
    if canonical == "suspended":
        return "suspended"
    if canonical in {"live", "in_progress"}:
        return "live"
    if canonical in {"scheduled", "upcoming", "pregame"}:
        return "scheduled"
    return "unknown"


def project_activitykit_snapshot(detail: Mapping[str, object]) -> GameActivitySnapshot:
    """Project canonical detail fields with the phone's current-then-hero selection.

    The hero clock dates current_odds only if BOTH values agree with that hero.
    An unmatched current reading remains displayable with unknown observation age.
    Terminal status never follows probability extremes or score comparisons.
    """
    lifecycle = _lifecycle(detail.get("status"))
    hero = _probability(detail.get("hero_probability"))
    raw_hero_away = detail.get("hero_probability_away")
    odds = detail.get("current_odds")
    odds = odds if isinstance(odds, Mapping) else {}
    current = _probability(odds.get("home_probability"))
    home = current if current is not None else hero
    raw_away = odds.get("away_probability") if current is not None else raw_hero_away
    away = _probability(raw_away)
    percent = None
    probability_clock = None
    if lifecycle in {"scheduled", "live"}:
        sport = detail.get("sport")
        if (
            not isinstance(sport, str)
            or not sport.strip()
            or sport_prices_a_draw(sport)
        ):
            percent = rendered_percent(home)
        else:
            percent = rendered_duel_percents(away, home)[1]
        if percent is not None and home == hero and raw_away == raw_hero_away:
            probability_clock = _clock(detail.get("hero_probability_observed_at"))
    home_score = detail.get("home_score")
    away_score = detail.get("away_score")
    home_score = home_score if type(home_score) is int and home_score >= 0 else None
    away_score = away_score if type(away_score) is int and away_score >= 0 else None
    # The widget prints only a complete named tuple; an orphan clock dates no display.
    score_source = detail.get("score_source")
    score_clock = (
        _clock(detail.get("score_observed_at"))
        if home_score is not None
        and away_score is not None
        and isinstance(score_source, str)
        and bool(score_source.strip())
        else None
    )
    return GameActivitySnapshot(
        event_id=detail.get("id"),
        home_team=detail.get("home_team"),
        away_team=detail.get("away_team"),
        lifecycle=lifecycle,
        home_score=home_score,
        away_score=away_score,
        home_rendered_percent=percent,
        score_observed_at=score_clock,
        probability_observed_at=probability_clock,
    )
