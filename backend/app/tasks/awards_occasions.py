"""Refresh ceremony evidence on the worker for the reviewed definition files (#11935)."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx

from app.services.awards_occasion_snapshot import (
    AWARDS_OCCASION_CACHE_KEY,
    AWARDS_OCCASION_CACHE_SECONDS,
    occasion_snapshot,
)
from app.services.awards_occasion_source import AwardsOccasionSourceError, read_live

logger = logging.getLogger(__name__)


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
        discovery = await read_live("all")
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
    written = await asyncio.to_thread(
        client.setex,
        AWARDS_OCCASION_CACHE_KEY,
        AWARDS_OCCASION_CACHE_SECONDS,
        json.dumps(occasion_snapshot(discovery, observed_at=started), allow_nan=False),
    )
    if not written:
        raise AwardsOccasionSourceError("source_snapshot_not_written")
    return {
        "terminal": "complete",
        "occasions": len(discovery.occasions),
        "provider_events": sum(
            len(occasion.events) for occasion in discovery.occasions
        ),
        "refused": discovery.refused,
        "model_cost_usd": 0,
    }
