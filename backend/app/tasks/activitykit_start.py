"""Default-off kickoff Live Activity push-to-start task (#13052 / 254-A / 178-B).

Reuses `ProviderConfiguration.from_environment(os.environ)` (`ACTIVITYKIT_APNS_*`)
and guards execution behind `ACTIVITYKIT_START_PUSH_ENABLED=true`.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.activitykit_start_dispatch import (
    EnvAPNsTransportPool,
    RedisStartDedupStore,
    dispatch_kickoff_starts,
)
from app.tasks.activitykit_runtime import ProviderConfiguration
from app.tasks.base import _get_task_engine


async def run_activitykit_start_dispatch() -> dict:
    if os.environ.get("ACTIVITYKIT_START_PUSH_ENABLED") != "true":
        return {"status": "disabled", "terminal": "skipped"}

    min_version = os.environ.get("ACTIVITYKIT_START_MIN_APP_VERSION", "1.0.8").strip() or None
    engine = transports = None
    result: dict = {"status": "configuration_failed", "terminal": "failed"}
    try:
        config = ProviderConfiguration.from_environment(os.environ)
        engine = _get_task_engine(statement_timeout_ms=5000, lock_timeout_ms=2000)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        transports = EnvAPNsTransportPool(bundle_id=config.bundle_id)
        dedup = RedisStartDedupStore()
        summary = await dispatch_kickoff_starts(
            sessions,
            transports,
            config.provider_token,
            dedup,
            min_app_version=min_version,
        )
        result = summary.as_dict()
    except Exception:
        # Never pass credential-bearing exception strings to Celery/Sentry.
        result = {"status": "start_dispatch_failed", "terminal": "failed"}
    finally:
        for resource in (transports, engine):
            if resource is None:
                continue
            try:
                async with asyncio.timeout(5):
                    if resource is transports:
                        await transports.aclose()
                    else:
                        await engine.dispose()
            except Exception:
                result = {"status": "cleanup_failed", "terminal": "failed"}
    return result
