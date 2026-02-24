"""
Template-based reason generation for the unified feed.

Generates 1-line explanations for why a feed item is interesting.
Returns empty string when the card UI already tells the story — avoids
repeating scores, odds, or team names visible on the card.
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

    Returns a human-readable reason string for the feed card, or empty
    string when the card's visual elements (score, odds bar, badges)
    already convey the information.
    """
    reasons = set(highlight_reasons)

    # ── Finished events ──────────────────────────────────────────
    # Card shows: score (winner bolded) + opening odds bar + "Opened X/Y".
    # Only add text for genuinely insightful context.
    if status in ("completed", "closed"):
        if "upset" in reasons:
            if home_score is not None and away_score is not None and opening_home_prob is not None:
                if home_score > away_score:
                    winner_opening_prob = opening_home_prob
                else:
                    winner_opening_prob = 1 - opening_home_prob
                pct = round(winner_opening_prob * 100)
                return f"Won as {pct}% underdog"
            return "Upset result"
        if "major_prob_swing" in reasons:
            if opening_home_prob is not None and home_probability is not None:
                change = home_probability - opening_home_prob
                direction_team = home_team if change > 0 else away_team
                pct_change = abs(round(change * 100))
                return f"{direction_team} odds shifted {pct_change}% during the game"
            return ""
        # Non-upset finished: card UI (score + opening odds) tells the story
        return ""

    # ── Live events ──────────────────────────────────────────────
    if status == "live":
        if "favorite_switched" in reasons:
            if opening_home_prob is not None:
                if opening_home_prob > 0.5:
                    underdog = away_team
                else:
                    underdog = home_team
                return f"{underdog} leading as underdog"
            return "Underdog leading"

        if "very_close" in reasons:
            return "Virtually even"

        if "close_matchup" in reasons:
            return "Tight game"

        if "major_prob_swing" in reasons:
            if opening_home_prob is not None and home_probability is not None:
                change = home_probability - opening_home_prob
                direction_team = home_team if change > 0 else away_team
                pct_change = abs(round(change * 100))
                return f"{direction_team} odds shifted {pct_change}%"
            return ""

        # Generic live — LIVE badge is sufficient
        return ""

    # ── Upcoming/scheduled events ────────────────────────────────
    if "major_prob_swing" in reasons:
        if opening_home_prob is not None and home_probability is not None:
            change = home_probability - opening_home_prob
            direction_team = home_team if change > 0 else away_team
            pct_change = abs(round(change * 100))
            return f"{direction_team} odds shifted {pct_change}% since open"
        return ""

    if "starting_soon" in reasons and "close_matchup" in reasons:
        return "Starting soon \u2014 close matchup"

    if "starting_very_soon" in reasons:
        return "Starting in under an hour"

    if "starting_soon" in reasons:
        return "Starting soon"

    # Fallback — the card shows teams and odds, no need for text
    return ""


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
