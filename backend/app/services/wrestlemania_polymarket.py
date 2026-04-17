"""Thin wrapper for polling WrestleMania odds from Polymarket."""

import logging
from typing import Optional

from app.services.polymarket_api import PolymarketAPIService

logger = logging.getLogger(__name__)


async def poll_wrestlemania_prices(
    matches: list[dict],
) -> dict[int, dict[str, float]]:
    """
    Poll current Polymarket prices for WrestleMania matches.

    Args:
        matches: list of dicts with {match_id, outcomes: [{outcome_id, polymarket_token_id}]}

    Returns:
        {outcome_id: {"probability": float}} for each outcome with a token_id
    """
    svc = PolymarketAPIService()
    results: dict[int, dict[str, float]] = {}
    try:
        for match in matches:
            for outcome in match.get("outcomes", []):
                token_id = outcome.get("polymarket_token_id")
                if not token_id:
                    continue
                price = await svc.get_midpoint(token_id)
                if price is not None and price > 0:
                    results[outcome["outcome_id"]] = {"probability": price}
    except Exception as e:
        logger.warning("WrestleMania Polymarket poll error: %s", e)
    finally:
        await svc.close()
    return results


async def discover_wrestlemania_markets() -> list[dict]:
    """
    Try to discover WrestleMania/Wrestlefest markets on Polymarket.
    Returns list of {event_id, title, markets: [{condition_id, question, outcomes, clob_token_ids}]}
    """
    svc = PolymarketAPIService()
    found = []
    try:
        events = await svc.get_all_active_events()
        for event in events:
            title_lower = event.title.lower()
            if any(
                k in title_lower
                for k in ("wrestle", "wwe", "wrestlefest", "wrestlemania")
            ):
                found.append(
                    {
                        "event_id": event.id,
                        "title": event.title,
                        "markets": [
                            {
                                "condition_id": m.condition_id,
                                "question": m.question,
                                "outcomes": m.outcomes,
                                "clob_token_ids": m.clob_token_ids,
                            }
                            for m in event.markets
                        ],
                    }
                )
    except Exception as e:
        logger.warning("WrestleMania market discovery error: %s", e)
    finally:
        await svc.close()
    return found
