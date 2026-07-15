"""Morning Digest task (Queue #200, Item 2) — the PRD notifications v1.

Once daily (~7 AM PT), select the 3-5 most interesting probabilities and push a
single digest to opted-in device tokens. Content selection reuses the Discover
interestingness scores already cached in Redis by ``precompute_interestingness``
— one content brain, and a cheap read path (no LLM, no scoring on the send
path; gotcha #39: Redis access is routed through the bounded ``get_redis_client``).

Opt-in model: a device's user must have ``push_preferences["morning_digest"] is
True`` (explicit opt-in — unlike daily_challenge/big_moves which are opt-out).
This keeps v1 a dogfood surface (Alex first) rather than a broadcast.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select, update as sa_update

from app.models.models import DeviceToken, FuturesMarket, FuturesOutcome, User
from app.utils.morning_digest import (
    DEFAULT_DIGEST_LIMIT,
    DigestCandidate,
    render_digest_payload,
    select_digest_candidates,
)

logger = logging.getLogger(__name__)

# Cheap upper bound on the candidate query — we rank the highest-volume open
# markets by their cached interestingness. A once-daily bounded sort.
CANDIDATE_POOL_SIZE = 400


async def _gather_digest_candidates(session, redis, *, pool_size=CANDIDATE_POOL_SIZE) -> list[DigestCandidate]:
    """Cheap read: top-volume feed-eligible markets + their cached interestingness."""
    now = datetime.now(timezone.utc)
    from sqlalchemy.orm import load_only, selectinload

    result = await session.execute(
        select(FuturesMarket)
        .options(
            load_only(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.llm_sport_category,
                FuturesMarket.canonical_market_key,
                FuturesMarket.group_id,
                FuturesMarket.volume_24h,
            ),
            selectinload(FuturesMarket.outcomes).load_only(
                FuturesOutcome.name,
                FuturesOutcome.current_probability,
            ),
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.event_id.is_(None),
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now,
            ),
            FuturesMarket.volume_24h.isnot(None),
        )
        .order_by(FuturesMarket.volume_24h.desc())
        .limit(pool_size)
    )
    markets = result.scalars().unique().all()
    if not markets:
        return []

    # Batch-read cached interestingness scores (one MGET, no per-market round trips).
    keys = [f"interestingness:{m.id}" for m in markets]
    scores: dict[int, float] = {}
    try:
        raws = redis.mget(keys)
        for m, raw in zip(markets, raws):
            if not raw:
                continue
            try:
                scores[m.id] = float(json.loads(raw).get("score", 0.0))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    except Exception:
        logger.warning("Digest interestingness MGET failed — ranking by volume only", exc_info=True)

    candidates: list[DigestCandidate] = []
    for m in markets:
        leader_name = None
        leader_prob = None
        for o in m.outcomes:
            if o.current_probability is None:
                continue
            prob = float(o.current_probability)
            if leader_prob is None or prob > leader_prob:
                leader_prob = prob
                leader_name = o.name
        if leader_name is None or leader_prob is None:
            continue
        candidates.append(
            DigestCandidate(
                market_id=m.id,
                name=m.name,
                leader_name=leader_name,
                leader_prob=leader_prob,
                interestingness=scores.get(m.id, 0.0),
                volume_24h=float(m.volume_24h) if m.volume_24h is not None else None,
                category=m.llm_sport_category,
                dedup_key=m.canonical_market_key or m.group_id or m.name,
            )
        )
    return candidates


async def _run_morning_digest(
    *,
    dry_run: bool = False,
    target_token: str | None = None,
    limit: int = DEFAULT_DIGEST_LIMIT,
) -> dict:
    """Build the digest and send it to opted-in tokens.

    - ``dry_run=True``: build + return payload, send nothing (admin preview).
    - ``target_token`` set: send only to that token, bypassing opt-in
      (dogfood/test send for a specific device).
    - otherwise: send to every active token whose user opted in via
      ``push_preferences["morning_digest"] is True``.
    """
    from app.tasks.base import get_task_session
    from app.tasks.redis_state import get_redis_client

    redis = get_redis_client()

    async with get_task_session() as db:
        candidates = await _gather_digest_candidates(db, redis)
        # Pass now so the feed's dated-bucket/quality suppression runs — a market
        # whose title implies a past month (Kalshi settlement lands in the next
        # month, gotcha #883) must never rank into today's digest.
        selected = select_digest_candidates(
            candidates, limit=limit, now=datetime.now(timezone.utc)
        )
        payload = render_digest_payload(selected)

        summary: dict = {
            "status": "ok",
            "dry_run": dry_run,
            "candidates": len(candidates),
            "selected": len(selected),
            "title": payload.title,
            "body": payload.body,
            "items": payload.items,
        }

        if dry_run:
            return summary

        if not selected:
            summary["status"] = "no_content"
            summary["sent"] = 0
            return summary

        # Resolve the recipient token set.
        if target_token:
            recipient_tokens = [(None, target_token)]  # (device_row_id, token)
        else:
            rows = await db.execute(
                select(DeviceToken, User)
                .outerjoin(User, DeviceToken.user_id == User.id)
                .where(DeviceToken.is_active.is_(True))
            )
            recipient_tokens = []
            for device_token, user in rows.all():
                prefs = user.push_preferences if (user and isinstance(user.push_preferences, dict)) else {}
                if prefs.get("morning_digest", False) is True:
                    recipient_tokens.append((device_token.id, device_token.device_token))

        sent, failed = 0, 0
        from app.tasks.push_notifications import _InvalidTokenError, _send_fcm_message

        for device_row_id, token in recipient_tokens:
            try:
                _send_fcm_message(
                    token=token,
                    title=payload.title,
                    body=payload.body,
                    data=payload.data,
                )
                sent += 1
            except _InvalidTokenError:
                if device_row_id is not None:
                    await db.execute(
                        sa_update(DeviceToken)
                        .where(DeviceToken.id == device_row_id)
                        .values(is_active=False)
                    )
                failed += 1
            except Exception as exc:
                logger.warning("Morning digest send failed to %s...: %s", token[:8], exc)
                failed += 1

        summary["recipients"] = len(recipient_tokens)
        summary["sent"] = sent
        summary["failed"] = failed

    logger.info(
        "Morning digest (%s): candidates=%d selected=%d sent=%d failed=%d",
        "dry_run" if dry_run else ("target" if target_token else "broadcast"),
        len(candidates),
        len(selected),
        summary.get("sent", 0),
        summary.get("failed", 0),
    )
    return summary
