"""Pure scoring logic for WrestleMania prediction game."""

from decimal import Decimal
from itertools import product


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


def compute_max_possible(picks: list[dict], starting_bankroll: float = 1_000_000) -> float:
    """Bankroll if every pending pick wins."""
    total = Decimal(str(starting_bankroll))
    for p in picks:
        stake = Decimal(str(p["stake"]))
        odds = Decimal(str(p["decimal_odds_at_pick"]))
        total -= stake
        if p.get("result") == "won":
            total += stake * odds
        elif p.get("result") is None:
            total += stake * odds
    return float(total)


def compute_win_probabilities(
    players: list[dict],
    unresolved_matches: list[dict],
) -> dict[int, float]:
    """Exact win probability for each player via combinatorial enumeration.

    Args:
        players: [{id, picks: [{match_id, outcome_id, stake, decimal_odds_at_pick, result}]}]
            Each player must have a pre-computed `base_bankroll` (bankroll from resolved picks).
        unresolved_matches: [{match_id, outcomes: [{outcome_id, probability}]}]

    Returns:
        {player_id: probability_of_finishing_first}
    """
    if not players:
        return {}

    # If no unresolved matches, the current leader wins with 100%
    if not unresolved_matches:
        sorted_p = sorted(players, key=lambda p: p["base_bankroll"], reverse=True)
        return {p["id"]: (1.0 if i == 0 else 0.0) for i, p in enumerate(sorted_p)}

    # Build per-match outcome lists: [(outcome_id, probability), ...]
    match_outcomes: list[list[tuple[int, float]]] = []
    match_ids: list[int] = []
    for m in unresolved_matches:
        outcomes = [(o["outcome_id"], o["probability"]) for o in m["outcomes"]]
        match_outcomes.append(outcomes)
        match_ids.append(m["match_id"])

    # Index each player's pending picks by match_id -> (outcome_id, stake, odds)
    player_pending: dict[int, dict[int, tuple[int, float, float]]] = {}
    for p in players:
        pending = {}
        for pk in p["picks"]:
            if pk["result"] is None and pk["match_id"] in set(match_ids):
                pending[pk["match_id"]] = (
                    pk["outcome_id"],
                    pk["stake"],
                    pk["decimal_odds_at_pick"],
                )
        player_pending[p["id"]] = pending

    win_counts: dict[int, float] = {p["id"]: 0.0 for p in players}

    # Enumerate all outcome combinations
    for combo in product(*match_outcomes):
        # combo[i] = (winning_outcome_id, probability) for match i
        scenario_prob = 1.0
        for _, prob in combo:
            scenario_prob *= prob
        if scenario_prob <= 0:
            continue

        # Map match_id -> winning_outcome_id for this scenario
        winners = {match_ids[i]: combo[i][0] for i in range(len(match_ids))}

        # Compute each player's bankroll in this scenario
        best_bankroll = -1e18
        best_ids: list[int] = []

        for p in players:
            bankroll = p["base_bankroll"]
            pending = player_pending[p["id"]]
            for mid, winning_oid in winners.items():
                pick = pending.get(mid)
                if pick:
                    picked_oid, stake, odds = pick
                    if picked_oid == winning_oid:
                        bankroll += stake * odds

            if bankroll > best_bankroll:
                best_bankroll = bankroll
                best_ids = [p["id"]]
            elif bankroll == best_bankroll:
                best_ids.append(p["id"])

        # Split probability among ties
        share = scenario_prob / len(best_ids)
        for pid in best_ids:
            win_counts[pid] += share

    return win_counts
