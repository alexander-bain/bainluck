#!/usr/bin/env python3
"""Show top 10 events by Game Excitement Index."""

import asyncio
import sys
sys.path.insert(0, '/home/user/odds-tracker/backend')

from sqlalchemy import select
from app.services.database import async_session_maker
from app.models import Event, Sport


async def get_top_events():
    async with async_session_maker() as session:
        result = await session.execute(
            select(Event, Sport.key)
            .join(Sport)
            .where(Event.raw_gei.isnot(None))
            .order_by(Event.raw_gei.desc())
            .limit(10)
        )
        rows = result.all()

        print("\n## Top 10 Events by Excitement Score\n")
        print("| # | Score | Teams | Final | Sport | URL |")
        print("|---|-------|-------|-------|-------|-----|")
        for i, (event, sport_key) in enumerate(rows, 1):
            score = min(100, max(1, round(float(event.raw_gei) * 100)))
            teams = f"{event.home_team} vs {event.away_team}"[:40]
            final = f"{event.home_score or '?'}-{event.away_score or '?'}"
            url = f"https://bainluck.com/events/{event.id}"
            print(f"| {i} | {score} | {teams} | {final} | {sport_key} | {url} |")
        print()


if __name__ == "__main__":
    asyncio.run(get_top_events())
