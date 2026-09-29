"""A terminal exact-leaf projection for an already visible futures card.

This does not select or rank feed candidates. It replaces forecasts with the
assigned result only; neither a high probability nor an expired date is a grade.
"""
from app.utils.settledness import market_assigned_settled
from app.utils.futures_unsupported_price import row_carries_a_verdict


def settled_feed_price_card(market, revision_clocks):
    outcomes = list(getattr(market, "outcomes", None) or [])
    # A Kalshi contract may keep status=open even after every leg is graded No.
    # One losing sibling alone does not settle an otherwise open multi-leg field.
    all_graded_losses = bool(outcomes) and all(
        getattr(o, "is_winner", None) is False
        and row_carries_a_verdict(getattr(o, "resolution_source", None))
        for o in outcomes
    )
    if not market_assigned_settled(market) and not all_graded_losses:
        return None
    winners = [o for o in outcomes if getattr(o, "is_winner", None) is True]
    winner = getattr(winners[0], "name", None) if len(winners) == 1 else None
    if isinstance(winner, str):
        winner = winner.strip() or None
    sport = getattr(market, "sport", None)
    resolution_date = getattr(market, "resolution_date", None)
    data = {
        "id": market.id,
        "name": market.name,
        "sport": getattr(sport, "key", None),
        "sport_name": getattr(sport, "name", None),
        "source": getattr(market, "source", None),
        "external_id": getattr(market, "external_id", None),
        "canonical_market_key": getattr(market, "canonical_market_key", None),
        "group_id": getattr(market, "group_id", None),
        "group_type": getattr(market, "group_type", None),
        "market_tier": getattr(market, "market_tier", None),
        "market_type": getattr(market, "market_type", None),
        "llm_sport_category": getattr(market, "llm_sport_category", None),
        "status": getattr(market, "status", None),
        "resolution_date": resolution_date.isoformat() if resolution_date else None,
        "resolved": True,
        # A closed/ungraded or multi-winner question has no single named winner.
        "winner": winner,
        "winner_opening_probability": None,
        "top_outcomes": [],
        "outcome_count": len(outcomes),
        "price_observed_at": None,
        "card_sum_reason": None,
        "outcome_revision_at": revision_clocks,
        "outcome_observed_at": revision_clocks,  # Legacy ORDERING alias only.
        "outcome_clock_kind": "row_revision",
    }
    # In-place clients retain the held card's ranking/editorial fields.
    return {"type": "futures", "score": 0, "data": data}
