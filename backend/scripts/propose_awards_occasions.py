"""Produce reviewable ceremony proposals from saved or live venue evidence.

Run from backend with PYTHONPATH=. python3 scripts/propose_awards_occasions.py
--source-file /absolute/path/to/a/venue-response.json, or select --live for a
read-only, bounded read of the stored open Kalshi entertainment pool.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.services.awards_occasion_source import (
    kalshi_occasion_event,
    read_kalshi_awards_occasions,
)
from app.utils.awards_occasion_finder import OccasionDiscovery, find_awards_occasions


async def read_live() -> OccasionDiscovery:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services.database import DATABASE_URL, build_connect_args
    from app.services.kalshi_api import KalshiAPIService

    connect_args = build_connect_args(
        DATABASE_URL,
        statement_timeout_ms=750,
        lock_timeout_ms=250,
    )
    connect_args["server_settings"]["default_transaction_read_only"] = "on"
    engine = create_async_engine(
        DATABASE_URL,
        connect_args=connect_args,
        poolclass=NullPool,
        hide_parameters=True,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    service = KalshiAPIService()
    try:
        async with sessions() as db:
            return await read_kalshi_awards_occasions(db, service)
    finally:
        try:
            await service.close()
        finally:
            await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source-file", type=Path, nargs="+")
    inputs.add_argument("--live", action="store_true")
    args = parser.parse_args()

    print(json.dumps({"model_cost_usd": 0, "state": "proposed"}), flush=True)
    if args.live:
        discovery = asyncio.run(read_live())
        scope = "stored_open_kalshi_entertainment"
    else:
        events = []
        for path in args.source_file:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ticker = payload.get("event", {}).get("event_ticker")
            events.append(kalshi_occasion_event(payload, ticker))
        discovery = find_awards_occasions(events)
        scope = "saved_venue_responses"
    print(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_scope": scope,
                "kind": "awards_ceremony",
                "model_cost_usd": 0,
                "occasions": [
                    {**asdict(occasion), "selector": occasion.selector}
                    for occasion in discovery.occasions
                ],
                "refused": discovery.refused,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
