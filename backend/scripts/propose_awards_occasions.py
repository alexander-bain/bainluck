"""Produce reviewable ceremony proposals from saved or live venue evidence.

Run from backend with PYTHONPATH=. python3 scripts/propose_awards_occasions.py
--source-file /absolute/path/to/a/venue-response.json, or select --live for a
read-only, bounded read of the stored open entertainment pool on both venues.
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
    polymarket_occasion_event,
    read_live,
    read_only_session,
)
from app.utils.awards_ceremony import awards_ceremony_definition
from app.utils.awards_occasion_finder import OccasionDiscovery, find_awards_occasions


async def preview_ceremonies(discovery: OccasionDiscovery) -> list[dict]:
    from app.utils.awards_ceremony import build_awards_ceremony_producer
    from app.utils.roundup_containers import (
        RoundupRefusal,
        compose_roundup_container,
        compose_roundup_feed_item,
    )

    async def load_occasions(db):
        return discovery

    previews = []
    async with read_only_session() as db:
        for occasion in discovery.occasions:
            producer = build_awards_ceremony_producer(
                occasion.selector,
                load_occasions=load_occasions,
            )
            result = await producer.produce(db)
            preview = {"selector": occasion.selector, "stage": "proposed_preview"}
            if isinstance(result, RoundupRefusal):
                preview["refused"] = result.reasons
            else:
                preview["feed_item"] = compose_roundup_feed_item(producer, result)
                preview["container"] = compose_roundup_container(producer, result)
            previews.append(preview)
    return previews


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source-file", type=Path, nargs="+")
    inputs.add_argument("--live", action="store_true")
    parser.add_argument(
        "--provider", choices=("kalshi", "polymarket", "all"), default="all"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Read stored market cards and include proposed card/page payloads.",
    )
    args = parser.parse_args()

    print(json.dumps({"model_cost_usd": 0, "state": "proposed"}), flush=True)
    if args.live:
        discovery = asyncio.run(read_live(args.provider))
        providers = "kalshi_and_polymarket" if args.provider == "all" else args.provider
        scope = f"stored_open_{providers}_entertainment"
    else:
        events = []
        for path in args.source_file:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "event" in payload:
                ticker = payload.get("event", {}).get("event_ticker")
                events.append(kalshi_occasion_event(payload, ticker))
            else:
                events.append(
                    polymarket_occasion_event(payload, str(payload.get("id") or ""))
                )
        discovery = find_awards_occasions(events)
        scope = "saved_venue_responses"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_scope": scope,
        "kind": "awards_ceremony",
        "model_cost_usd": 0,
        "occasions": [
            {**asdict(occasion), "selector": occasion.selector}
            for occasion in discovery.occasions
        ],
        "refused": discovery.refused,
        "definitions": [
            awards_ceremony_definition(occasion.selector)
            for occasion in discovery.occasions
        ],
    }
    if args.preview:
        report["previews"] = asyncio.run(preview_ceremonies(discovery))
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
