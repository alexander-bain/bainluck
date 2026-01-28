#!/usr/bin/env python
"""One-time script to remove soccer data from the database."""

import asyncio
from sqlalchemy import select, delete
from app.services.database import async_session_maker
from app.models import Sport, Event, OddsSnapshot


async def cleanup_soccer():
    """Remove all soccer sports, events, and odds snapshots."""
    async with async_session_maker() as session:
        # Find soccer sports
        result = await session.execute(
            select(Sport).where(Sport.key.like("soccer_%"))
        )
        soccer_sports = result.scalars().all()
        print(f"Found {len(soccer_sports)} soccer sports")

        for sport in soccer_sports:
            print(f"Removing: {sport.key}")

            # Get events for this sport
            events_result = await session.execute(
                select(Event).where(Event.sport_id == sport.id)
            )
            events = events_result.scalars().all()
            print(f"  - {len(events)} events")

            # Delete odds snapshots for these events
            for event in events:
                await session.execute(
                    delete(OddsSnapshot).where(OddsSnapshot.event_id == event.id)
                )

            # Delete events
            await session.execute(
                delete(Event).where(Event.sport_id == sport.id)
            )

            # Delete sport
            await session.delete(sport)

        await session.commit()
        print("Soccer data cleanup complete")


if __name__ == "__main__":
    asyncio.run(cleanup_soccer())
