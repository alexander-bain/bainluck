#!/usr/bin/env python3
"""
One-time script to remove cricket (and other excluded) sports from the database.

Run with: heroku run python scripts/cleanup_cricket.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete, or_
from app.services.database import async_session_maker
from app.models import Sport, Event, OddsSnapshot

# Excluded sport prefixes
EXCLUDED_SPORT_PREFIXES = ["soccer_", "cricket_", "rugbyleague_", "rugbyunion_", "aussierules_"]

# Additional keywords to catch non-standard keys
EXCLUDED_KEYWORDS = ["cricket", "rugby", "t20", "odi", "test_match", "afl", "nrl"]


async def cleanup():
    """Remove all excluded sports, events, and snapshots."""
    async with async_session_maker() as session:
        # Build exclusion conditions
        conditions = []
        for prefix in EXCLUDED_SPORT_PREFIXES:
            conditions.append(Sport.key.like(f"{prefix}%"))
        for keyword in EXCLUDED_KEYWORDS:
            conditions.append(Sport.key.ilike(f"%{keyword}%"))

        # Find all excluded sports
        result = await session.execute(
            select(Sport).where(or_(*conditions))
        )
        excluded_sports = result.scalars().all()

        if not excluded_sports:
            print("No excluded sports found in database.")
            return

        print(f"Found {len(excluded_sports)} excluded sports:")
        for sport in excluded_sports:
            print(f"  - {sport.key}: {sport.name}")

        total_events = 0
        total_snapshots = 0

        for sport in excluded_sports:
            # Get events for this sport
            events_result = await session.execute(
                select(Event).where(Event.sport_id == sport.id)
            )
            events = events_result.scalars().all()
            event_count = len(events)
            total_events += event_count

            # Delete odds snapshots for these events
            snapshot_count = 0
            for event in events:
                snapshot_result = await session.execute(
                    delete(OddsSnapshot).where(OddsSnapshot.event_id == event.id)
                )
                snapshot_count += snapshot_result.rowcount or 0
            total_snapshots += snapshot_count

            # Delete events
            await session.execute(
                delete(Event).where(Event.sport_id == sport.id)
            )

            # Delete sport
            await session.delete(sport)

            print(f"Removed {sport.key}: {event_count} events, {snapshot_count} snapshots")

        await session.commit()

        print(f"\nTotal removed:")
        print(f"  Sports: {len(excluded_sports)}")
        print(f"  Events: {total_events}")
        print(f"  Snapshots: {total_snapshots}")


if __name__ == "__main__":
    print("Starting cleanup of excluded sports (cricket, rugby, etc.)...\n")
    asyncio.run(cleanup())
    print("\nDone!")
