"""
Template-based reason generation for the unified feed.

Generates 1-line explanations for why a feed item is interesting.
Templates first, LLM upgrade later (roadmap item #12).
"""

from typing import Optional


def generate_event_reason(
    home_team: str,
    away_team: str,
    status: str,
    highlight_reasons: list[str],
    home_probability: Optional[float] = None,
    away_probability: Optional[float] = None,
    opening_home_prob: Optional[float] = None,
    home_score: Optional[int] = None,
    away_score: Optional[int] = None,
) -> str:
    """
    Generate a one-line explanation for why an event is interesting.

    Returns a human-readable reason string for the feed card.
    """
    reasons = set(highlight_reasons)

    # Upset scenarios (most interesting)
    if "upset" in reasons:
        if home_score is not None and away_score is not None:
            winner = home_team if home_score > away_score else away_team
            loser = away_team if home_score > away_score else home_team
            return f"{winner} upset {loser} {home_score}-{away_score}"
        return f"Upset result in {away_team} at {home_team}"

    if "favorite_switched" in reasons and status == "live":
        if opening_home_prob is not None and home_probability is not None:
            # Determine who was the original favorite
            if opening_home_prob > 0.5:
                orig_fav = home_team
                underdog = away_team
            else:
                orig_fav = away_team
                underdog = home_team
            score_str = ""
            if home_score is not None and away_score is not None:
                score_str = f" ({home_score}-{away_score})"
            return f"{underdog} leading against favored {orig_fav}{score_str}"
        return f"Underdog leading in {away_team} at {home_team}"

    # Close live games
    if status == "live" and "very_close" in reasons:
        prob_display = ""
        if home_probability is not None:
            home_pct = round(home_probability * 100)
            prob_display = f" ({home_pct}-{100 - home_pct})"
        score_str = ""
        if home_score is not None and away_score is not None:
            score_str = f" {home_score}-{away_score},"
        return f"{away_team} at {home_team},{score_str} virtually even{prob_display}"

    if status == "live" and "close_matchup" in reasons:
        score_str = ""
        if home_score is not None and away_score is not None:
            score_str = f" {home_score}-{away_score},"
        return f"{away_team} at {home_team},{score_str} tight game"

    # Major probability swing
    if "major_prob_swing" in reasons:
        if opening_home_prob is not None and home_probability is not None:
            change = home_probability - opening_home_prob
            direction_team = home_team if change > 0 else away_team
            pct_change = abs(round(change * 100))
            return f"{direction_team} odds improved {pct_change}% since open"
        return f"Significant line movement in {away_team} at {home_team}"

    # Starting soon + close
    if "starting_soon" in reasons and "close_matchup" in reasons:
        prob_display = ""
        if home_probability is not None:
            home_pct = round(home_probability * 100)
            prob_display = f" at {home_pct}-{100 - home_pct}"
        return f"{away_team} at {home_team} starting soon{prob_display}"

    # Starting soon
    if "starting_very_soon" in reasons:
        return f"{away_team} at {home_team} starting in under an hour"
    if "starting_soon" in reasons:
        return f"{away_team} at {home_team} starting soon"

    # Live game (generic)
    if "live" in reasons:
        score_str = ""
        if home_score is not None and away_score is not None:
            score_str = f" ({home_score}-{away_score})"
        return f"{away_team} at {home_team} is live{score_str}"

    # Recently finished
    if "recent_finish" in reasons:
        if home_score is not None and away_score is not None:
            winner = home_team if home_score > away_score else away_team
            loser = away_team if home_score > away_score else home_team
            return f"{winner} beat {loser} {max(home_score, away_score)}-{min(home_score, away_score)}"
        return f"{away_team} at {home_team} recently finished"

    # Fallback
    if home_probability is not None:
        home_pct = round(home_probability * 100)
        return f"{away_team} at {home_team} ({home_pct}-{100 - home_pct})"

    return f"{away_team} at {home_team}"


def generate_futures_reason(
    market_name: str,
    highlight_reasons: list[str],
    top_mover_name: Optional[str] = None,
    top_mover_change: Optional[float] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    source_count: int = 1,
) -> str:
    """
    Generate a one-line explanation for why a futures market is interesting.

    Returns a human-readable reason string for the feed card.
    """
    reasons = set(highlight_reasons)

    # Leader change (most interesting)
    if "leader_change" in reasons:
        if leader_name and leader_probability is not None:
            pct = round(leader_probability * 100)
            return f"New favorite: {leader_name} ({pct}%) now leads {market_name}"
        return f"New favorite in {market_name}"

    # Source divergence
    if "source_divergence" in reasons:
        if source_count >= 2:
            return f"Sources disagree on {market_name} ({source_count} sources tracking)"
        return f"Sources disagree on {market_name}"

    # Major movement
    if "major_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None:
            direction = "up" if top_mover_change > 0 else "down"
            pct = round(abs(top_mover_change) * 100, 1)
            return f"{top_mover_name} moved {direction} {pct}% in 24h for {market_name}"
        return f"Big odds movement in {market_name}"

    # Rankings shakeup
    if "rank_shakeup" in reasons:
        return f"Multiple ranking changes in {market_name}"

    # Moderate movement
    if "moderate_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None:
            direction = "up" if top_mover_change > 0 else "down"
            pct = round(abs(top_mover_change) * 100, 1)
            return f"{top_mover_name} odds shifted {direction} {pct}% for {market_name}"
        return f"Odds shifting in {market_name}"

    # Resolving soon
    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            pct = round(leader_probability * 100)
            return f"{market_name} resolving soon, {leader_name} leads at {pct}%"
        return f"{market_name} resolving this week"
    if "resolving_soon_30d" in reasons:
        return f"{market_name} resolving this month"

    # Multi-source
    if "multi_source" in reasons:
        if leader_name and leader_probability is not None:
            pct = round(leader_probability * 100)
            return f"{leader_name} ({pct}%) leads {market_name} across {source_count} sources"
        return f"{market_name} tracked by {source_count} sources"

    # Fallback
    if leader_name and leader_probability is not None:
        pct = round(leader_probability * 100)
        return f"{leader_name} ({pct}%) leads {market_name}"

    return market_name
