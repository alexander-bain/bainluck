"""Scheduled maintenance for the daily /guess challenge (#12619, 443: A).

Sweeps expired editions and group entries older than 30 days PT, and
best-effort pre-freezes today's PT daily pack shortly after midnight PT
(08:05 UTC).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.tasks.base import get_task_session
from app.utils.guess_daily import (
    GuessEditionUnavailableError,
    get_or_freeze_daily_edition,
    sweep_expired_guess_data,
    today_pt,
)

logger = logging.getLogger(__name__)


async def run_guess_daily_maintenance(
    *,
    now_utc: Optional[datetime] = None,
) -> dict[str, Any]:
    """Delete >30d /guess rows and ensure today's PT edition is frozen."""
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    today = today_pt(now)

    async with get_task_session() as db:
        swept = await sweep_expired_guess_data(db, today=today)
        edition_frozen = False
        edition_error: Optional[str] = None
        try:
            await get_or_freeze_daily_edition(db, today, now_utc=now)
            edition_frozen = True
        except GuessEditionUnavailableError as exc:
            edition_error = str(exc)
            logger.warning("guess_daily_maintenance could not freeze %s: %s", today, exc)

    return {
        "day_pt": today.isoformat(),
        "edition_frozen": edition_frozen,
        "edition_error": edition_error,
        **swept,
    }
