#!/usr/bin/env python3
"""One-shot CU v2 backfill — run via heroku run:detached."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from app.tasks.enrich_markets import enrich_cu_v2_profiles
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    print(f"Starting CU v2 backfill with limit={limit}")
    result = await enrich_cu_v2_profiles(limit=limit)
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
