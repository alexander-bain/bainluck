"""WrestleMania odds polling and match lifecycle management."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.models.wrestlemania import (
    WrestlemaniaMatch,
    WrestlemaniaOutcome,
    WrestlemaniaOddsSnapshot,
    WrestlemaniaPick,
)
from app.services.wrestlemania_polymarket import poll_wrestlemania_prices
from app.tasks.base import get_task_session as get_session

logger = logging.getLogger(__name__)


async def _poll_wrestlemania_odds():
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        # Fetch non-resolved matches
        result = await session.execute(
            select(WrestlemaniaMatch).where(
                WrestlemaniaMatch.status.in_(["open", "locked"])
            )
        )
        matches = result.scalars().all()

        # Auto-lock matches past lock_time
        locked_count = 0
        for match in matches:
            if match.status == "open" and match.lock_time <= now:
                await session.execute(
                    update(WrestlemaniaMatch)
                    .where(WrestlemaniaMatch.id == match.id)
                    .values(status="locked")
                )
                locked_count += 1

        # Build poll list
        poll_data = []
        for match in matches:
            outcomes_result = await session.execute(
                select(WrestlemaniaOutcome).where(
                    WrestlemaniaOutcome.match_id == match.id
                )
            )
            outcomes = outcomes_result.scalars().all()
            if any(o.polymarket_token_id for o in outcomes):
                poll_data.append(
                    {
                        "match_id": match.id,
                        "outcomes": [
                            {
                                "outcome_id": o.id,
                                "polymarket_token_id": o.polymarket_token_id,
                            }
                            for o in outcomes
                        ],
                    }
                )

        # Poll Polymarket
        if poll_data:
            prices = await poll_wrestlemania_prices(poll_data)
            updated = 0
            for outcome_id, data in prices.items():
                prob = data["probability"]
                decimal_odds = round(1.0 / prob, 3) if prob > 0.01 else 100.0
                await session.execute(
                    update(WrestlemaniaOutcome)
                    .where(WrestlemaniaOutcome.id == outcome_id)
                    .values(
                        probability=prob,
                        decimal_odds=decimal_odds,
                        updated_at=now,
                    )
                )
                session.add(
                    WrestlemaniaOddsSnapshot(
                        outcome_id=outcome_id,
                        probability=prob,
                        source="polymarket",
                        recorded_at=now,
                    )
                )
                updated += 1

            # Update complementary probabilities for binary markets
            for match_data in poll_data:
                outcomes = match_data["outcomes"]
                if len(outcomes) == 2:
                    for out in outcomes:
                        if out["outcome_id"] in prices:
                            other_id = [
                                o["outcome_id"]
                                for o in outcomes
                                if o["outcome_id"] != out["outcome_id"]
                            ][0]
                            if other_id not in prices:
                                comp_prob = round(
                                    1.0 - prices[out["outcome_id"]]["probability"], 4
                                )
                                comp_odds = (
                                    round(1.0 / comp_prob, 3)
                                    if comp_prob > 0.01
                                    else 100.0
                                )
                                await session.execute(
                                    update(WrestlemaniaOutcome)
                                    .where(WrestlemaniaOutcome.id == other_id)
                                    .values(
                                        probability=comp_prob,
                                        decimal_odds=comp_odds,
                                        updated_at=now,
                                    )
                                )
                                session.add(
                                    WrestlemaniaOddsSnapshot(
                                        outcome_id=other_id,
                                        probability=comp_prob,
                                        source="polymarket",
                                        recorded_at=now,
                                    )
                                )
                                updated += 1

        await session.commit()

        return {
            "matches": len(matches),
            "polled": len(poll_data),
            "locked": locked_count,
            "updated": updated if poll_data else 0,
        }
