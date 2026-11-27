"""Default-off 1.0.8 plain APNs game-alerts task + hourly App Clip purge (#13081, #13079).

Reuses ``ProviderConfiguration.from_environment(os.environ)`` (`ACTIVITYKIT_APNS_*`)
and guards game-alert delivery behind ``GAME_ALERTS_PUSH_ENABLED=true`` (default-off
until Fable looks and Alex verifies on his phone).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.apns_alert import EnvAPNsAlertTransportPool
from app.services.game_alerts_dispatch import (
    RedisGameAlertDedupStore,
    dispatch_game_alerts,
)
from app.services.push_audience import purge_expired_appclip_devices
from app.tasks.activitykit_runtime import ProviderConfiguration
from app.tasks.base import _get_task_engine


async def run_game_alerts_dispatch() -> dict:
    if os.environ.get("GAME_ALERTS_PUSH_ENABLED") != "true":
        return {"status": "disabled", "terminal": "skipped"}

    min_version = (
        os.environ.get("ACTIVITYKIT_START_MIN_APP_VERSION", "1.0.8").strip() or None
    )
    engine = transports = None
    result: dict = {"status": "configuration_failed", "terminal": "failed"}
    try:
        config = ProviderConfiguration.from_environment(os.environ)
        engine = _get_task_engine(statement_timeout_ms=5000, lock_timeout_ms=2000)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        transports = EnvAPNsAlertTransportPool()
        dedup = RedisGameAlertDedupStore()
        summary = await dispatch_game_alerts(
            sessions,
            transports,
            config.provider_token,
            dedup,
            min_app_version=min_version,
        )
        result = summary.as_dict()
    except Exception:
        # Never pass credential-bearing exception strings to Celery/Sentry.
        result = {"status": "game_alerts_failed", "terminal": "failed"}
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


async def run_purge_expired_appclip_devices(*, now: datetime | None = None) -> dict:
    """Delete App Clip device rows older than Apple's 8-hour ephemeral window (#13079)."""
    clock = now if now is not None else datetime.now(timezone.utc)
    engine = None
    result: dict = {"status": "purge_failed", "terminal": "failed", "deleted": 0}
    try:
        engine = _get_task_engine(statement_timeout_ms=5000, lock_timeout_ms=2000)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            deleted = await purge_expired_appclip_devices(db, now=clock)
            await db.commit()
        result = {"status": "ok", "terminal": "ok", "deleted": int(deleted)}
    except Exception:
        result = {"status": "purge_failed", "terminal": "failed", "deleted": 0}
    finally:
        if engine is not None:
            try:
                async with asyncio.timeout(5):
                    await engine.dispose()
            except Exception:
                result = {"status": "cleanup_failed", "terminal": "failed", "deleted": 0}
    return result
