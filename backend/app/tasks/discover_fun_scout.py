"""Celery worker entry point for the Nightly Fun Scout (#13102, Ruling 276: B).

Runs on ``bainluck``'s ``worker-background`` (queue ``background``, same app
and worker as ``grouping_sentinel``) so only ``bainluck`` needs
``ANTHROPIC_API_KEY_SCOUT``. Never called during a page load.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

from app.database import async_session_maker
from app.models.models import FuturesMarket
from app.utils.discover_fun_scout import (
    SCOUT_LICENCE_STATE_PATH,
    SCOUT_RETIRED_SETS_PATH,
    SCOUT_STAGED_SETS_DIR,
    ScoutLicenceState,
    ScoutMarketRow,
    ScoutUncoveredFamily,
    build_scout_anthropic_client,
    build_scout_openai_client,
    is_fun_scout_enabled,
    load_retired_scout_sets,
    run_nightly_fun_scout,
)

logger = logging.getLogger(__name__)

_NON_SPORTS_CATEGORIES: frozenset[str] = frozenset(
    {
        "politics",
        "economics",
        "tech",
        "entertainment",
        "culture",
        "weather",
        "geopolitics",
        "health",
        "science",
        "climate",
        "finance",
        "crypto",
    }
)

_MONTHLY_SPEND_REDIS_PREFIX = "bainluck:fun_scout:monthly_spend"
_MONTHLY_SPEND_TTL_S = 45 * 24 * 3600


def _read_monthly_spend_usd(month_key: str) -> float:
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client().get(f"{_MONTHLY_SPEND_REDIS_PREFIX}:{month_key}")
        if raw is None:
            return 0.0
        return max(0.0, float(raw.decode() if isinstance(raw, bytes) else raw))
    except Exception:
        logger.warning("Fun scout monthly spend ledger unavailable; failing closed at cap")
        return float("inf")


def _record_monthly_spend_usd(month_key: str, delta_usd: float) -> None:
    if delta_usd <= 0:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        key = f"{_MONTHLY_SPEND_REDIS_PREFIX}:{month_key}"
        client.incrbyfloat(key, float(delta_usd))
        client.expire(key, _MONTHLY_SPEND_TTL_S)
    except Exception as exc:
        logger.warning("Failed to record fun scout monthly spend: %s", exc)


async def fetch_open_non_sports_markets_for_scout(
    *, limit: int = 6000
) -> list[ScoutMarketRow]:
    """Read today's open non-sports titles from both venues (Kalshi + Polymarket)."""
    async with async_session_maker() as db:
        stmt = (
            select(
                FuturesMarket.id,
                FuturesMarket.source,
                FuturesMarket.name,
                FuturesMarket.status,
                FuturesMarket.llm_sport_category,
                FuturesMarket.resolution_date,
                FuturesMarket.volume,
                FuturesMarket.volume_24h,
                FuturesMarket.canonical_market_key,
                FuturesMarket.group_id,
                FuturesMarket.market_metadata,
            )
            .where(
                FuturesMarket.status == "open",
                FuturesMarket.source.in_(("kalshi", "polymarket")),
                FuturesMarket.llm_sport_category.in_(tuple(_NON_SPORTS_CATEGORIES)),
            )
            .order_by(FuturesMarket.volume.desc().nullslast(), FuturesMarket.id.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()

    return [
        ScoutMarketRow(
            market_id=int(r.id),
            source=str(r.source or ""),
            title=str(r.name or ""),
            status=str(r.status or "open"),
            category=r.llm_sport_category,
            resolution_date=r.resolution_date,
            volume=float(r.volume) if r.volume is not None else None,
            volume_24h=float(r.volume_24h) if r.volume_24h is not None else None,
            canonical_market_key=r.canonical_market_key,
            group_id=r.group_id,
            market_metadata=r.market_metadata if isinstance(r.market_metadata, dict) else None,
        )
        for r in rows
    ]


def _load_licence_state(path: Path = SCOUT_LICENCE_STATE_PATH) -> ScoutLicenceState:
    if not path.exists():
        return ScoutLicenceState()
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return ScoutLicenceState.from_dict(raw)
    return ScoutLicenceState()


async def _run_discover_fun_scout(
    *,
    force: bool = False,
    output_dir: Optional[Path] = SCOUT_STAGED_SETS_DIR,
    uncovered_families: Optional[list[ScoutUncoveredFamily]] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Execute one scheduled or attended Nightly Fun Scout run."""
    if not force and not is_fun_scout_enabled():
        logger.info("Nightly fun scout skipped: DISCOVER_FUN_SCOUT_ENABLED is off")
        return {"status": "disabled"}

    run_now = now or datetime.now(timezone.utc)
    month_key = run_now.strftime("%Y-%m")
    prior_spend = _read_monthly_spend_usd(month_key)

    markets = await fetch_open_non_sports_markets_for_scout()
    retired = load_retired_scout_sets(SCOUT_RETIRED_SETS_PATH)
    licence = _load_licence_state(SCOUT_LICENCE_STATE_PATH)

    openai_client = build_scout_openai_client()
    anthropic_client = build_scout_anthropic_client()

    result = run_nightly_fun_scout(
        markets,
        uncovered_families or [],
        openai_client=openai_client,
        anthropic_client=anthropic_client,
        output_dir=output_dir,
        retired_sets=retired,
        licence_state=licence,
        prior_monthly_spend_usd=prior_spend,
        now=run_now,
    )
    _record_monthly_spend_usd(month_key, float(result.get("actual_total_cost_usd") or 0.0))
    return {
        "status": "completed",
        "spend_line": result["spend_line"],
        "actual_total_cost_usd": result["actual_total_cost_usd"],
        "set_model": result["set_model"],
        "tagged_count": result["tagged_count"],
        "validated_set_count": len(result["validated_sets"]),
        "rejected_set_count": len(result["rejected_sets"]),
        "written_rule_files": result["written_rule_files"],
    }
