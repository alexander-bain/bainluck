"""
Utility functions for historical NCAA Tournament seed matchup data.
"""

from app.data.seed_history import SEED_HISTORY, NOTABLE_UPSETS


def get_historical_upset_rate(
    tournament_type: str,
    seed_a: int,
    seed_b: int,
) -> dict | None:
    """
    Get historical win rate for a seed matchup.

    Args:
        tournament_type: "mens" or "womens"
        seed_a: One team's seed (1-16)
        seed_b: Other team's seed (1-16)

    Returns:
        dict with matchups, higher_wins, upset_pct or None if no data
    """
    history = SEED_HISTORY.get(tournament_type, {})
    higher = min(seed_a, seed_b)
    lower = max(seed_a, seed_b)
    return history.get((higher, lower))


def get_seed_context_text(
    tournament_type: str,
    seed_favorite: int,
    seed_underdog: int,
) -> str:
    """Generate a human-readable context string for a seed matchup."""
    data = get_historical_upset_rate(tournament_type, seed_favorite, seed_underdog)
    if not data:
        return ""
    pct = data["upset_pct"] * 100
    if pct < 2:
        return f"{seed_underdog} seeds have almost never beaten {seed_favorite} seeds ({pct:.1f}% upset rate)"
    elif pct < 10:
        return f"{seed_underdog} seeds rarely beat {seed_favorite} seeds ({pct:.0f}% upset rate)"
    elif pct < 30:
        return f"{seed_underdog} seeds beat {seed_favorite} seeds about {pct:.0f}% of the time"
    elif pct < 45:
        return f"{seed_underdog} seeds upset {seed_favorite} seeds {pct:.0f}% of the time — common upset spot"
    else:
        return f"{seed_underdog} vs {seed_favorite} is essentially a coin flip ({pct:.0f}% upset rate)"


def get_first_round_seed_history(tournament_type: str) -> list[dict]:
    """
    Get all first-round seed matchup data for display as a reference table.

    Returns list of dicts sorted by matchup (1v16, 2v15, ..., 8v9).
    """
    history = SEED_HISTORY.get(tournament_type, {})
    first_round = []
    for higher_seed in range(1, 9):
        lower_seed = 17 - higher_seed
        data = history.get((higher_seed, lower_seed))
        if data:
            first_round.append({
                "higher_seed": higher_seed,
                "lower_seed": lower_seed,
                "matchups": data["matchups"],
                "higher_wins": data["higher_wins"],
                "upset_pct": data["upset_pct"],
                "label": f"#{higher_seed} vs #{lower_seed}",
            })
    return first_round


def get_notable_upsets(tournament_type: str) -> list[dict]:
    """Get notable historical upsets for context cards."""
    return NOTABLE_UPSETS.get(tournament_type, [])
