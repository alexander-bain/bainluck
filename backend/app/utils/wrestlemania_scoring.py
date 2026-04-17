"""Pure scoring logic for WrestleMania prediction game."""

from decimal import Decimal


def compute_bankroll(picks: list[dict], starting_bankroll: float = 1_000_000) -> float:
    """
    Compute current bankroll from a list of picks.

    Each pick dict: {stake, decimal_odds_at_pick, result}
    result: "won" | "lost" | None (pending)

    Bankroll = starting - sum(all stakes) + sum(winning payouts)
    """
    total = Decimal(str(starting_bankroll))
    for p in picks:
        stake = Decimal(str(p["stake"]))
        total -= stake
        if p.get("result") == "won":
            odds = Decimal(str(p["decimal_odds_at_pick"]))
            total += stake * odds
    return float(total)
