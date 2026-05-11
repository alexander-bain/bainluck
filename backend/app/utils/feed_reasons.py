"""
Template-based reason generation for the unified feed.

Generates 1-line explanations for why a feed item is interesting.
Returns empty string when the card UI already tells the story — avoids
repeating scores, odds, or team names visible on the card.
"""

from typing import Optional


def _side_label(name: str) -> str:
    """Make binary Yes/No outcome labels read naturally in movement text."""
    if name.strip().lower() in {"yes", "no"}:
        return f"{name.strip()} side"
    return name


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
    event_tags: Optional[list[str]] = None,
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

    # ── Tag-based context (LLM enrichment) ─────────────────────────
    # These add a story angle when no odds-based reason was found.
    tags = set(event_tags or [])
    _TAG_REASONS: list[tuple[str, str]] = [
        ("narrative:historic_rivalry", "Historic rivalry"),
        ("narrative:rivalry", "Rivalry game"),
        ("stakes:elimination", "Elimination game"),
        ("stakes:clinch", "Clinch scenario"),
        ("stakes:title_defense", "Title defense"),
        ("narrative:cinderella", "Cinderella story"),
        ("narrative:revenge_game", "Revenge game"),
        ("narrative:rematch", "Postseason rematch"),
        ("narrative:farewell_tour", "Farewell tour"),
        ("narrative:comeback", "Comeback story"),
        ("stakes:record_chase", "Record chase"),
        ("stakes:must_win", "Must-win game"),
        ("audience:national_interest", "National interest"),
        ("narrative:david_vs_goliath", "David vs. Goliath"),
    ]
    for tag, label in _TAG_REASONS:
        if tag in tags:
            return label

    # Fallback — the card shows teams and odds, no need for text
    return ""


def generate_futures_reason(
    market_name: str,
    highlight_reasons: list[str],
    top_mover_name: Optional[str] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_name: Optional[str] = None,
    top_surprise_change: Optional[float] = None,
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
            return f"{_side_label(top_mover_name)} moved {direction} {pct}% in 24h for {market_name}"
        return f"Big odds movement in {market_name}"

    # Surprise vs opening
    if "major_surprise" in reasons:
        if top_surprise_name and top_surprise_change is not None:
            direction = "up" if top_surprise_change > 0 else "down"
            pct = round(abs(top_surprise_change) * 100, 1)
            return f"{_side_label(top_surprise_name)} moved {direction} {pct} points from opening in {market_name}"
        return f"Big shift from opening in {market_name}"

    # Rankings shakeup
    if "rank_shakeup" in reasons:
        return f"Multiple ranking changes in {market_name}"

    # Moderate movement
    if "moderate_movement_24h" in reasons:
        if top_mover_name and top_mover_change is not None:
            direction = "up" if top_mover_change > 0 else "down"
            pct = round(abs(top_mover_change) * 100, 1)
            return f"{_side_label(top_mover_name)} odds shifted {direction} {pct}% for {market_name}"
        return f"Odds shifting in {market_name}"

    if "moderate_surprise" in reasons:
        if top_surprise_name and top_surprise_change is not None:
            direction = "up" if top_surprise_change > 0 else "down"
            pct = round(abs(top_surprise_change) * 100, 1)
            return f"{_side_label(top_surprise_name)} shifted {direction} {pct} points from opening in {market_name}"
        return f"Odds shifted from opening in {market_name}"

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


def generate_futures_headline(
    highlight_reasons: list[str],
    top_mover_name: Optional[str] = None,
    top_mover_change: Optional[float] = None,
    top_surprise_name: Optional[str] = None,
    top_surprise_change: Optional[float] = None,
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    source_count: int = 1,
) -> str:
    """Generate compact, specific card text for futures Discover cards."""
    reasons = set(highlight_reasons)

    if "leader_change" in reasons:
        if leader_name and leader_probability is not None:
            return f"New favorite: {leader_name} ({round(leader_probability * 100)}%)"
        return "New favorite"

    if "source_divergence" in reasons:
        return f"Sources disagree ({source_count})" if source_count >= 2 else "Sources disagree"

    if "major_movement_24h" in reasons and top_mover_name and top_mover_change is not None:
        direction = "up" if top_mover_change > 0 else "down"
        return f"{_side_label(top_mover_name)} {direction} {round(abs(top_mover_change) * 100, 1)} points today"

    if "major_surprise" in reasons and top_surprise_name and top_surprise_change is not None:
        direction = "up" if top_surprise_change > 0 else "down"
        return f"{_side_label(top_surprise_name)} {direction} {round(abs(top_surprise_change) * 100, 1)} points from opening"

    if "rank_shakeup" in reasons:
        return "Multiple ranking changes"

    if "moderate_movement_24h" in reasons and top_mover_name and top_mover_change is not None:
        direction = "up" if top_mover_change > 0 else "down"
        return f"{_side_label(top_mover_name)} {direction} {round(abs(top_mover_change) * 100, 1)} points today"

    if "moderate_surprise" in reasons and top_surprise_name and top_surprise_change is not None:
        direction = "up" if top_surprise_change > 0 else "down"
        return f"{_side_label(top_surprise_name)} {direction} {round(abs(top_surprise_change) * 100, 1)} points from opening"

    if "resolving_soon_7d" in reasons:
        if leader_name and leader_probability is not None:
            return f"Resolving soon: {leader_name} leads at {round(leader_probability * 100)}%"
        return "Resolving soon"

    if "resolving_soon_30d" in reasons:
        return "Resolving this month"

    if "multi_source" in reasons:
        return f"Tracked by {source_count} sources" if source_count >= 2 else "Multi-source"

    if leader_name and leader_probability is not None:
        return f"{leader_name} leads at {round(leader_probability * 100)}%"

    return ""


def generate_futures_context_summary(
    *,
    headline: Optional[str],
    highlight_reasons: list[str],
    leader_name: Optional[str] = None,
    leader_probability: Optional[float] = None,
    source_count: int = 1,
) -> str:
    """Generate short visible context copy for Discover cards.

    This is intentionally tighter than the full reason and avoids using long
    LLM hook paragraphs as the on-card snippet. Full hooks remain available for
    "See more" expansion.
    """
    headline = (headline or "").strip()
    reasons = set(highlight_reasons)

    def leader_clause() -> str:
        if leader_name and leader_probability is not None:
            return f"{leader_name} leads at {round(leader_probability * 100)}%"
        return ""

    leader = leader_clause()

    if "resolving_soon_7d" in reasons:
        return f"{leader}; resolves this week" if leader else "Resolves this week"
    if "resolving_soon_30d" in reasons and headline == "Resolving this month":
        return f"{leader}; resolves this month" if leader else "Resolves this month"
    if "multi_source" in reasons and headline.startswith("Tracked by"):
        if leader:
            return f"{leader} across {source_count} sources"
        return headline

    if headline:
        if leader and len(headline) < 80:
            lower_headline = headline.lower()
            lower_leader = leader_name.lower() if leader_name else ""
            if lower_leader and lower_leader not in lower_headline:
                return f"{headline}; {leader}"
        return headline

    return leader
