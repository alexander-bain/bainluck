"""WebSocket SHADOW grading (#836/#844 Batch 2, Redis-shadow, no migration).

The real-time WS grader can settle is_winner with sub-second latency, but the
flip to authoritative is high-blast-radius. This module runs the widened
lifecycle-only WS grader in SHADOW: it records its computed verdict to a Redis
hash (NEVER the real `is_winner`), and a comparison reports the shadow-vs-current
agreement rate per source — so the eventual flip is gated on an automated match,
not live human watching.

Deploy-dark: the shadow consumer only runs when the Redis flag is enabled
(default OFF), so deploying this changes nothing until the flag is turned on.
Even when on, it touches only Redis — never `is_winner`.

Shadow store: `bainluck:ws_shadow_verdict` hash, field = settled ticker
(outcome external_id), value = "1"/"0". Keyed by external_id so the comparison
joins `FuturesOutcome.external_id == ticker` EXACTLY — no rsplit / format-aware
event resolution needed on the shadow path (exact match handles non-game tickers
like KXPGAPLAYOFF-PGC26 that broke the authoritative path's rsplit).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SHADOW_FLAG_KEY = "bainluck:ws_shadow_enabled"
SHADOW_VERDICT_KEY = "bainluck:ws_shadow_verdict"
SHADOW_COMPARISON_KEY = "bainluck:ws_shadow_comparison"
_VERDICT_TTL_S = 14 * 86400  # 14 days — long enough to accumulate a comparison

_SETTLED_STATUSES = ("closed", "settled", "finalized")


async def is_ws_shadow_enabled() -> bool:
    """Whether the shadow consumer should run. Default False (deploy-dark)."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        raw = await rc.get(SHADOW_FLAG_KEY)
        await rc.aclose()
        return str(raw.decode() if isinstance(raw, bytes) else raw).lower() in (
            "1", "true", "on", "yes",
        ) if raw is not None else False
    except Exception:
        return False  # fail closed — never run the shadow consumer on a Redis error


def verdict_from_lifecycle(msg: dict) -> tuple[str, bool] | None:
    """Pure: parse a Kalshi market_lifecycle message into (ticker, is_winner).

    Returns None for non-terminal messages or missing/ambiguous result. is_winner
    is True when the market settled 'yes'. NEVER touches the DB.
    """
    if not isinstance(msg, dict):
        return None
    if msg.get("status", "") not in _SETTLED_STATUSES:
        return None
    ticker = (msg.get("market_ticker") or "").upper()
    result = msg.get("result")
    if not ticker or result not in ("yes", "no"):
        return None
    return ticker, (result == "yes")


async def record_shadow_verdict(ticker: str, is_winner: bool) -> None:
    """Write the shadow verdict to Redis (NEVER the real is_winner)."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        await rc.hset(SHADOW_VERDICT_KEY, ticker, "1" if is_winner else "0")
        await rc.expire(SHADOW_VERDICT_KEY, _VERDICT_TTL_S)
        await rc.aclose()
    except Exception:
        logger.warning("ws_shadow: failed to record verdict for %s", ticker, exc_info=True)


async def compare_shadow_verdicts(session) -> dict:
    """Compare recorded shadow verdicts against the current authoritative
    is_winner, per source. Reviewable any time — no live watching.

    Returns {sources: {src: {agree, disagree, ungraded, match_rate}}, total: {...}}.
    """
    from sqlalchemy import select
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.tasks.redis_state import get_async_redis_client

    rc = get_async_redis_client()
    raw = await rc.hgetall(SHADOW_VERDICT_KEY)
    await rc.aclose()
    # normalize bytes
    shadow: dict[str, bool] = {}
    for k, v in (raw or {}).items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v
        shadow[key] = val == "1"

    if not shadow:
        return {"sources": {}, "total": {"agree": 0, "disagree": 0, "ungraded": 0, "match_rate": None}, "shadow_count": 0}

    tickers = list(shadow.keys())
    result = await session.execute(
        select(FuturesOutcome.external_id, FuturesOutcome.is_winner, FuturesMarket.source)
        .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
        .where(FuturesOutcome.external_id.in_(tickers))
    )

    from collections import defaultdict
    per_src = defaultdict(lambda: {"agree": 0, "disagree": 0, "ungraded": 0})
    tot = {"agree": 0, "disagree": 0, "ungraded": 0}
    for ext_id, is_winner, source in result.all():
        sv = shadow.get(ext_id)
        if sv is None:
            continue
        bucket = per_src[source or "unknown"]
        if is_winner is None:
            bucket["ungraded"] += 1
            tot["ungraded"] += 1
        elif bool(is_winner) == sv:
            bucket["agree"] += 1
            tot["agree"] += 1
        else:
            bucket["disagree"] += 1
            tot["disagree"] += 1

    def _rate(b: dict) -> float | None:
        graded = b["agree"] + b["disagree"]
        return round(b["agree"] / graded, 4) if graded else None

    sources = {s: {**b, "match_rate": _rate(b)} for s, b in per_src.items()}
    tot["match_rate"] = _rate(tot)
    return {"sources": sources, "total": tot, "shadow_count": len(shadow)}
