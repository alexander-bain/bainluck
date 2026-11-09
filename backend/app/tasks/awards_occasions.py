"""Refresh ceremony evidence on the worker for the reviewed definition files (#11935)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import httpx

from app.services.awards_occasion_snapshot import (
    AWARDS_OCCASION_CACHE_KEY,
    AWARDS_OCCASION_CACHE_SECONDS,
    AWARDS_OCCASION_MAX_BYTES,
    discovery_from_snapshot,
    occasion_snapshot,
)
from app.services.awards_occasion_source import AwardsOccasionSourceError, read_live
from app.services.durable_snapshots import (
    STATUS_CAS_MISS,
    publish_cas_snapshot_standalone,
    read_snapshot_standalone,
)
from app.utils.durable_state import DurableEnvelope

logger = logging.getLogger(__name__)
AWARDS_OCCASION_EVIDENCE_ID = "awards_occasions:evidence:v1"


async def refresh_awards_occasions() -> dict:
    """Publish one complete evidence snapshot. An incomplete pass withdraws the old one."""
    from app.tasks.redis_state import get_redis_client

    client = get_redis_client()
    if client is None:
        raise AwardsOccasionSourceError("source_unavailable:redis")
    started = time.time()
    logger.info(
        "Awards occasion discovery model cost $0.00, source-read cap 90 seconds"
    )
    try:
        retained = await read_snapshot_standalone(
            AWARDS_OCCASION_EVIDENCE_ID,
            expected_version="v1",
            max_age_s=float("inf"),
        )
        generation = None
        retained_events = ()
        if retained.ok and retained.envelope is not None:
            # Expired evidence supplies fetch identities. Every retained event
            # must pass the venue reader again before a fresh page can use it.
            previous = discovery_from_snapshot(
                retained.envelope.payload, now=started, allow_expired=True
            )
            retained_events = tuple(
                event for occasion in previous.occasions for event in occasion.events
            )
            generation = retained.envelope.generation
        elif not retained.missing:
            raise AwardsOccasionSourceError("retained_source_" + retained.status)
        discovery = await read_live("all", retained_events=retained_events)
        known_ids = {(event.provider, event.event_id) for event in retained_events}
        current_ids = {
            (event.provider, event.event_id)
            for occasion in discovery.occasions
            for event in occasion.events
        }
        missing = known_ids - current_ids
        if missing:
            provider, event_id = min(missing)
            reasons = {
                (p, identifier): reason for p, identifier, reason in discovery.refused
            }
            reason = reasons.get((provider, event_id), "not_returned")
            raise AwardsOccasionSourceError(
                f"retained_event_unavailable:{provider}:{event_id}:{reason}"
            )
        payload = occasion_snapshot(discovery, observed_at=started)
        encoded = json.dumps(payload, allow_nan=False)
        if len(encoded.encode("utf-8")) > AWARDS_OCCASION_MAX_BYTES:
            raise AwardsOccasionSourceError("source_snapshot_too_large")
        envelope = DurableEnvelope.build(
            identity=AWARDS_OCCASION_EVIDENCE_ID,
            schema_version="v1",
            generation=max(int(started * 1000), (generation or 0) + 1),
            generated_at=datetime.fromtimestamp(started, timezone.utc),
            payload=payload,
            source="awards_occasions",
        )
        stage = await publish_cas_snapshot_standalone(
            envelope, expected_generation=generation
        )
        if stage["status"] == STATUS_CAS_MISS:
            return {
                "terminal": "skipped",
                "reason": "retained_source_changed",
                "model_cost_usd": 0,
            }
        if stage["status"] != "ok":
            raise AwardsOccasionSourceError(
                "retained_source_publish:" + stage["status"]
            )
        written = await asyncio.to_thread(
            client.setex,
            AWARDS_OCCASION_CACHE_KEY,
            AWARDS_OCCASION_CACHE_SECONDS,
            encoded,
        )
        if not written:
            raise AwardsOccasionSourceError("source_snapshot_not_written")
    except Exception as error:
        reason = (
            str(error)
            if isinstance(error, AwardsOccasionSourceError)
            else type(error).__name__
        )
        if isinstance(error, httpx.HTTPStatusError):
            reason += ":" + str(error.response.status_code)
        failed = {
            "version": 1,
            "state": "unavailable",
            "observed_at": started,
            "reason": reason,
        }
        try:
            withdrawn = await asyncio.to_thread(
                client.setex,
                AWARDS_OCCASION_CACHE_KEY,
                AWARDS_OCCASION_CACHE_SECONDS,
                json.dumps(failed),
            )
            if not withdrawn:
                logger.error(
                    "Awards source failure did not withdraw its previous snapshot"
                )
        except Exception:
            logger.exception(
                "Awards source failure could not withdraw its previous snapshot"
            )
        raise
    return {
        "terminal": "complete",
        "occasions": len(discovery.occasions),
        "provider_events": sum(
            len(occasion.events) for occasion in discovery.occasions
        ),
        "refused": discovery.refused,
        "model_cost_usd": 0,
    }
