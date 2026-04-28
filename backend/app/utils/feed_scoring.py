"""Feed event scoring — pure functions for ranking events by interestingness.

Extracted from routes/feed.py `_score_events` to make scoring logic
independently testable. These functions take pre-fetched data and return
scores/dicts — no database access, no side effects.
"""

from datetime import datetime


# Tag-based scoring boosts (LLM taxonomy enrichment)
TAG_BOOSTS = {
    "stakes:elimination": 12,
    "stakes:clinch": 10,
    "stakes:title_defense": 10,
    "stakes:must_win": 8,
    "stakes:record_chase": 8,
    "stakes:seeding": 5,
    "stakes:playoff_race": 3,
    "narrative:rivalry": 8,
    "narrative:historic_rivalry": 10,
    "narrative:cinderella": 8,
    "narrative:comeback": 8,
    "narrative:revenge_game": 6,
    "narrative:upset_alert": 6,
    "narrative:rematch": 5,
    "narrative:farewell_tour": 5,
    "narrative:david_vs_goliath": 3,
    "audience:national_interest": 5,
    "audience:crossover_appeal": 3,
    "audience:viral_potential": 3,
}


def compute_content_richness_penalty(
    event_status: str,
    raw_ei: float | None,
    home_score: int | None,
    away_score: int | None,
    source_count: int | None,
    game_progress: float | None,
    sport_key: str | None,
) -> tuple[int, list[str]]:
    """Penalize live events with flat/thin content so they don't outrank interesting games.

    Returns (adjustment, reasons) where adjustment is typically negative.
    Only applies to live events — scheduled/completed are unaffected.
    Combined penalty is capped at -20.
    """
    if event_status != "live":
        return 0, []

    penalty = 0
    bonus = 0
    reasons: list[str] = []
    progress = game_progress or 0.0

    # Signal A: Probability stasis (flat EI)
    # Gate on progress >= 0.25 — EI is naturally 0 at game start
    if progress >= 0.25:
        if raw_ei is None or raw_ei == 0.0:
            penalty -= 10
            reasons.append("flat_line")
        elif raw_ei < 0.05:
            penalty -= 5
            reasons.append("low_movement")

    # Signal B: Score stasis (0-0 deep into game)
    # Exempt soccer and hockey where 0-0 is normal/tense
    is_low_score_sport = sport_key and (
        sport_key.startswith("soccer_") or sport_key.startswith("icehockey_")
    )
    if (
        not is_low_score_sport
        and progress >= 0.5
        and home_score is not None
        and away_score is not None
        and home_score == 0
        and away_score == 0
    ):
        penalty -= 8
        reasons.append("scoreless_stalemate")

    # Signal C: Data thinness (source count)
    if source_count is not None:
        if source_count == 0:
            penalty -= 8
            reasons.append("no_sources")
        elif source_count == 1:
            penalty -= 5
            reasons.append("thin_data")
        elif source_count >= 4:
            bonus += 3
            reasons.append("rich_data")

    # Cap the penalty at -20 (bonus is separate)
    penalty = max(penalty, -20)

    return penalty + bonus, reasons


def compute_base_score(
    highlight_score: int,
    highlight_reasons: list[str],
    home_champ_prob: float,
    away_champ_prob: float,
    sport_key: str | None,
    now: datetime,
    event_tags: list[str],
    event_status: str,
    raw_ei: float | None,
    get_season_multiplier_fn=None,
    get_league_tier_fn=None,
    home_score: int | None = None,
    away_score: int | None = None,
    source_count: int | None = None,
    game_progress: float | None = None,
) -> tuple[int, list[str]]:
    """Compute the base interestingness score for a feed event.

    Returns (score, additional_reasons). Pure function — no DB access.

    Score components:
    - Highlight score (closeness, upset, lead change, etc.)
    - Stakes weighting (championship contender boost)
    - Season context (late-season major league boost)
    - LLM tag boosts (rivalry, elimination, narrative, etc.)
    - EI boost for completed high-excitement games
    """
    score = highlight_score
    reasons = list(highlight_reasons)

    # Stakes weighting
    max_champ_prob = max(home_champ_prob, away_champ_prob)
    if max_champ_prob >= 0.15:
        score += 15
        reasons.append("high_stakes")
    elif max_champ_prob >= 0.05:
        score += 8
        reasons.append("contender")
    elif max_champ_prob >= 0.01:
        score += 3

    # Season context
    if sport_key and get_season_multiplier_fn and get_league_tier_fn:
        season_mult = get_season_multiplier_fn(sport_key, now)
        if season_mult != 1.0:
            tier = get_league_tier_fn(sport_key)
            if tier in (1, 2):
                tier_weight = 20 if tier == 1 else 10
                season_bonus = int(tier_weight * (season_mult - 1.0))
                score += season_bonus

    # LLM tag boosts
    tag_set = set(event_tags)
    tag_bonus = sum(pts for tag, pts in TAG_BOOSTS.items() if tag in tag_set)
    if tag_bonus > 0:
        score += tag_bonus
        reasons.append("llm_tags")

    # EI boost for completed events
    if event_status in ("completed", "closed") and raw_ei is not None:
        ei_score = max(1, min(100, round(raw_ei * 100)))
        if ei_score >= 80:
            score += 25
            reasons.append("high_ei")
        elif ei_score >= 60:
            score += 15
            reasons.append("good_ei")

    # Content richness penalty for live events with thin/flat data
    richness_adj, richness_reasons = compute_content_richness_penalty(
        event_status=event_status,
        raw_ei=raw_ei,
        home_score=home_score,
        away_score=away_score,
        source_count=source_count,
        game_progress=game_progress,
        sport_key=sport_key,
    )
    if richness_adj != 0:
        score += richness_adj
        reasons.extend(richness_reasons)

    return score, reasons


def format_event_data(
    event_id: int,
    external_id: str | None,
    sport_key: str | None,
    sport_name: str | None,
    home_team: str | None,
    away_team: str | None,
    commence_time: datetime,
    status: str,
    home_score: int | None,
    away_score: int | None,
    current_home_prob: float | None,
    current_away_prob: float | None,
    opening_home_prob: float | None,
    opening_away_prob: float | None,
    opening_favorite: str | None,
    win_probability_sources: dict | None,
    prob_source: str | None,
    game_clock: str | None,
    period: str | None,
    broadcast_info: str | None,
    highlight_label: str | None,
    raw_ei: float | None,
    inline_tags: list[str],
    ended_at: datetime | None,
) -> dict:
    """Build the compact event data dict for the feed response.

    Pure function — takes all data as arguments, returns a dict.
    """
    data: dict = {
        "id": event_id,
        "external_id": external_id,
        "sport": sport_key,
        "sport_name": sport_name,
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": commence_time.isoformat(),
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
    }

    if win_probability_sources:
        data["win_probability_sources"] = win_probability_sources

    if status == "live":
        espn_data = {}
        if game_clock:
            espn_data["game_clock"] = game_clock
        if period:
            espn_data["period"] = period
        if broadcast_info:
            espn_data["broadcast"] = broadcast_info
        if espn_data:
            data["espn"] = espn_data

    if current_home_prob is not None:
        odds_data = {
            "home_probability": current_home_prob,
            "away_probability": current_away_prob,
        }
        if prob_source:
            odds_data["source"] = prob_source
        data["current_odds"] = odds_data

    if opening_home_prob is not None:
        data["opening_odds"] = {
            "home_probability": opening_home_prob,
            "away_probability": opening_away_prob,
            "favorite": opening_favorite,
        }

    if ended_at:
        data["ended_at"] = ended_at.isoformat()

    if highlight_label:
        data["highlight"] = {"label": highlight_label}

    if status in ("completed", "closed") and raw_ei is not None:
        raw_score = max(1, min(100, round(raw_ei * 100)))
        from app.routes.feed import _ei_label
        ei_data = {"score": raw_score, "label": _ei_label(raw_score)}
        data["ei"] = ei_data
        data["pulse"] = ei_data

    data["event_tags"] = inline_tags

    return data
