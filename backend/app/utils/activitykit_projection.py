"""Pure projection of a served event-detail reading, never a raw database row.

The caller supplies one coherent response from get_event, including its folded
hero and producer clocks. No fetch time, row updated_at, or current-odds timestamp
may substitute for the clock of the selected reading. Delivery is a separate owner.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
import math
import re

from app.utils.activitykit_payload import GameActivitySnapshot, Lifecycle, Result
from app.utils.draw_priced_winner import sport_prices_a_draw
from app.utils.graded_card import rendered_duel_percents, rendered_percent
from app.utils.settled_hero import is_finished_status

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")
_SPORT_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_RESULTS: set[str] = {"home", "away", "draw"}


def _clean_sport(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if _SPORT_RE.match(text) else None


def _clean_badge(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if 1 <= len(text) <= 6 else None


def _clean_hex(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _HEX_RE.match(text):
        return None
    return (text if text.startswith("#") else f"#{text}").upper()


def _clean_period(detail: Mapping[str, object], lifecycle: Lifecycle) -> str | None:
    if lifecycle not in {"live", "suspended"}:
        return None
    espn = detail.get("espn")
    raw = espn.get("period") if isinstance(espn, Mapping) else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not 1 <= len(text) <= 24 or ":" in text or "'" in text:
        return None
    return text


def _headline_tenths(home: float | None, away: float | None) -> int | None:
    """Match Swift EventHeadlineTenths10090.tenths(home / (home + away))."""
    if home is None or away is None:
        return None
    total = home + away
    if not 0.99 <= total <= 1.01:
        return None
    p_home = home / total
    scaled = round(p_home * 1000.0, 6)
    return int(math.floor(scaled + 0.5))


def _pregame_percents(
    detail: Mapping[str, object], sport: str | None
) -> tuple[int | None, int | None]:
    """Strict prematch_odds pair (never opening_odds) for two-way games (ruling 209)."""
    if sport is None or sport_prices_a_draw(sport):
        return (None, None)
    prematch = detail.get("prematch_odds")
    if not isinstance(prematch, Mapping):
        return (None, None)
    away_p = _probability(prematch.get("away_probability"))
    home_p = _probability(prematch.get("home_probability"))
    if away_p is None or home_p is None:
        return (None, None)
    served = prematch.get("rendered_percents")
    if (
        isinstance(served, (list, tuple))
        and len(served) > 1
        and type(served[0]) is int
        and type(served[1]) is int
        and 0 <= served[0] <= 100
        and 0 <= served[1] <= 100
    ):
        return (served[0], served[1])
    duel = rendered_duel_percents(away_p, home_p)
    if duel[0] is None or duel[1] is None:
        return (None, None)
    return (duel[0], duel[1])


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
    An opening-tagged or undated reading supplies no current forecast.
    Terminal status never follows probability extremes or score comparisons.
    """
    lifecycle = _lifecycle(detail.get("status"))
    sport = _clean_sport(detail.get("sport"))
    percent = None
    away_percent = None
    headline_tenths = None
    probability_clock = None
    if lifecycle in {"scheduled", "live"} and detail.get("hero_probability_source") != "opening":
        hero = _probability(detail.get("hero_probability"))
        raw_hero_away = detail.get("hero_probability_away")
        odds = detail.get("current_odds")
        odds = odds if isinstance(odds, Mapping) else {}
        current = _probability(odds.get("home_probability"))
        home = current if current is not None else hero
        raw_away = odds.get("away_probability") if current is not None else raw_hero_away
        away = _probability(raw_away)
        if sport is None or sport_prices_a_draw(sport):
            percent = rendered_percent(home)
        else:
            duel = rendered_duel_percents(away, home)
            percent = duel[1]
            away_percent = duel[0] if percent is not None else None
            if away_percent is not None:
                headline_tenths = _headline_tenths(home, away)
        if percent is not None and home == hero and raw_away == raw_hero_away:
            probability_clock = _clock(detail.get("hero_probability_observed_at"))
        if probability_clock is None:
            percent = None
            away_percent = None
            headline_tenths = None
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
    home_team_data = detail.get("home_team_data")
    away_team_data = detail.get("away_team_data")
    home_team_data = home_team_data if isinstance(home_team_data, Mapping) else {}
    away_team_data = away_team_data if isinstance(away_team_data, Mapping) else {}
    raw_result = detail.get("hero_settled_result")
    result: Result | None = (
        raw_result
        if lifecycle == "final" and isinstance(raw_result, str) and raw_result in _RESULTS
        else None
    )
    pregame_away, pregame_home = _pregame_percents(detail, sport)
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
        away_rendered_percent=away_percent,
        home_headline_tenths=headline_tenths,
        sport=sport,
        home_abbreviation=_clean_badge(home_team_data.get("abbreviation")),
        away_abbreviation=_clean_badge(away_team_data.get("abbreviation")),
        home_color_hex=_clean_hex(home_team_data.get("primary_color")),
        away_color_hex=_clean_hex(away_team_data.get("primary_color")),
        away_secondary_color_hex=_clean_hex(away_team_data.get("secondary_color")),
        period_label=_clean_period(detail, lifecycle),
        result=result,
        pregame_away_percent=pregame_away,
        pregame_home_percent=pregame_home,
    )
