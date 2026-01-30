"""
Backfill projected scores for historical snapshots.

This script finds all OddsSnapshot records that have home_spread and over_under
but are missing projected_home_score, and calculates the projected scores.

Run with: python -m scripts.backfill_projected_scores
"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_
from app.services.database import async_session_maker
from app.models import OddsSnapshot
from app.utils.odds_math import project_scores


async def backfill_projected_scores():
    """Find and update snapshots missing projected scores."""
    async with async_session_maker() as session:
        # Find snapshots with spread + over_under but no projected scores
        result = await session.execute(
            select(OddsSnapshot)
            .where(
                and_(
                    OddsSnapshot.home_spread.isnot(None),
                    OddsSnapshot.over_under.isnot(None),
                    OddsSnapshot.projected_home_score.is_(None),
                )
            )
        )
        snapshots = result.scalars().all()

        print(f"Found {len(snapshots)} snapshots to backfill")

        updated = 0
        for snap in snapshots:
            try:
                home_score, away_score = project_scores(
                    float(snap.home_spread),
                    float(snap.over_under),
                )
                snap.projected_home_score = home_score
                snap.projected_away_score = away_score
                updated += 1

                if updated % 1000 == 0:
                    print(f"Updated {updated} snapshots...")
                    await session.commit()

            except Exception as e:
                print(f"Error updating snapshot {snap.id}: {e}")
                continue

        await session.commit()
        print(f"Backfill complete: updated {updated} snapshots")


if __name__ == "__main__":
    asyncio.run(backfill_projected_scores())
