"""Worker evidence for reviewed ceremony definitions, without venue I/O in readers."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Mapping
from typing import Any

from app.services.awards_occasion_source import AwardsOccasionSourceError
from app.utils.awards_occasion_finder import OccasionDiscovery, find_awards_occasions

AWARDS_OCCASION_CACHE_KEY = "awards_occasions:v1"
AWARDS_OCCASION_CACHE_SECONDS = 7200


def occasion_snapshot(
    discovery: OccasionDiscovery, *, observed_at: float
) -> dict[str, Any]:
    """Keep the verbatim evidence needed to reproduce each proposed occasion."""
    events = []
    for occasion in discovery.occasions:
        for event in occasion.events:
            identity_field = "event_ticker" if event.provider == "kalshi" else "id"
            events.append(
                {
                    "provider": event.provider,
                    identity_field: event.event_id,
                    "title": event.title,
                    "markets": [{"rules_primary": quote} for quote in event.evidence],
                }
            )
    return {
        "version": 1,
        "state": "proposed",
        "observed_at": observed_at,
        "events": events,
        "refused": discovery.refused,
    }


def discovery_from_snapshot(payload: Any, *, now: float) -> OccasionDiscovery:
    """Refuse missing, stale, failed or malformed evidence before any member read."""
    if (
        not isinstance(payload, Mapping)
        or type(payload.get("version")) is not int
        or payload["version"] != 1
    ):
        raise AwardsOccasionSourceError("source_snapshot_malformed")
    observed_at = payload.get("observed_at")
    if (
        isinstance(observed_at, bool)
        or not isinstance(observed_at, (int, float))
        or not math.isfinite(observed_at)
        or observed_at > now
    ):
        raise AwardsOccasionSourceError("source_snapshot_malformed")
    if now - observed_at >= AWARDS_OCCASION_CACHE_SECONDS:
        raise AwardsOccasionSourceError("source_snapshot_stale")
    if payload.get("state") == "unavailable":
        raise AwardsOccasionSourceError(
            "source_unavailable:" + str(payload.get("reason") or "unknown")
        )
    if payload.get("state") != "proposed":
        raise AwardsOccasionSourceError("source_snapshot_malformed")
    events = payload.get("events")
    refused = payload.get("refused")
    if (
        not isinstance(events, list)
        or not isinstance(refused, (list, tuple))
        or any(
            not isinstance(row, (list, tuple))
            or len(row) != 3
            or any(not isinstance(value, str) for value in row)
            for row in refused
        )
    ):
        raise AwardsOccasionSourceError("source_snapshot_malformed")
    found = find_awards_occasions(events)
    if found.refused:
        raise AwardsOccasionSourceError("source_snapshot_malformed")
    return OccasionDiscovery(
        found.occasions, tuple(sorted({tuple(row) for row in refused}))
    )


async def read_cached_awards_occasions(db: Any) -> OccasionDiscovery:
    """A page reads the bounded shared cache. The worker owns discovery."""
    from app.tasks.redis_state import get_redis_client

    client = get_redis_client()
    if client is None:
        raise AwardsOccasionSourceError("source_unavailable:redis")
    raw = await asyncio.to_thread(client.get, AWARDS_OCCASION_CACHE_KEY)
    if raw is None:
        raise AwardsOccasionSourceError("source_snapshot_missing")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise AwardsOccasionSourceError("source_snapshot_malformed") from error
    return discovery_from_snapshot(payload, now=time.time())
