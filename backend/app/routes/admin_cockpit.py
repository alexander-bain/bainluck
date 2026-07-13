"""Alex Cockpit — a single read-only landing view for /admin (L2-102).

One payload, three groups, so Alex can (a) get a quick view of site issues,
(b) see what work is waiting on his judgment, and (c) knock out quick human-eval
decisions where his call is highly leveraged.

This route is intentionally READ-ONLY and reuses existing internals instead of
recomputing anything expensive:
  - Site health tiles read the warm Redis snapshots the L2-90 precompute beats
    already keep fresh (link rate, grid audit) plus a couple of cheap COUNT/MAX
    queries (queue depth, creation freshness).
  - "Waiting on you" uses the GitHub API when a server-side token exists, else a
    static fallback of the known standing items (per memory: GITHUB_TOKEN is
    unset on Heroku, so the fallback is the normal production path).
  - The quick-eval queue counts pending ``llm_proposed_*`` review rows (same
    semantics as ``/admin/label-pass/pending``) plus new bug reports; inline
    accept/reject on the frontend posts to the existing ``/label-pass/verdict``.

The whole payload is cached in Redis for 5 minutes.
"""

import json as _json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    BugReport,
    DiscoverLabelEvalRun,
    DiscoverReviewDecision,
    Event,
    FuturesMarket,
)
from app.routes.admin_utils import _check_admin_secret
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Cockpit"])

_CACHE_KEY = "bainluck:admin:cockpit"
_CACHE_TTL = 300  # 5 minutes

# The known items that need Alex's judgment when GitHub isn't reachable
# server-side. Kept in sync with the queue's "court" notes.
_WAITING_FALLBACK = [
    {
        "ref": "#997",
        "title": "Walk /calibration through the D5 App Store gate",
        "action": "Walk /calibration D5 — the App Store submission gate",
        "url": "https://github.com/alexander-bain/bainluck/issues/997",
    },
    {
        "ref": "#1055",
        "title": "Set the two production tokens (GITHUB_TOKEN + one more)",
        "action": "Set GITHUB_TOKEN on Heroku so backend issue-filing works",
        "url": "https://github.com/alexander-bain/bainluck/issues/1055",
    },
    {
        "ref": "L2-82",
        "title": "Run xcodebuild archive to confirm the iOS build is green",
        "action": "Run xcodebuild archive — confirm iOS build before TestFlight",
        "url": "https://github.com/alexander-bain/bainluck/issues",
    },
]


def _status_from_pct(pct: float | None, *, green: float, amber: float) -> str:
    """Green/amber/red band for a higher-is-better percentage."""
    if pct is None:
        return "unknown"
    if pct >= green:
        return "green"
    if pct >= amber:
        return "amber"
    return "red"


def _hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 1)


def _read_redis_json(key: str) -> dict | None:
    try:
        from app.tasks.redis_state import get_redis_client

        cached = get_redis_client().get(key)
        if cached:
            return _json.loads(cached)
    except Exception:
        logger.debug("cockpit: could not read redis key %s", key, exc_info=True)
    return None


def _queue_depths() -> dict:
    """Realtime + background Celery queue depths (cheap LLEN)."""
    depths = {"background": None, "realtime": None}
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        depths["background"] = r.llen("background")
        depths["realtime"] = r.llen("realtime")
    except Exception:
        logger.debug("cockpit: could not read queue depths", exc_info=True)
    return depths


async def _health_group(db: AsyncSession) -> list[dict]:
    """Build the site-health tile row from warm caches + cheap queries."""
    tiles: list[dict] = []

    # --- Link rate (warm cache from precompute_admin_link_rate) ---
    link = _read_redis_json("bainluck:admin:link_rate")
    if link and isinstance(link.get("overall"), dict):
        pct = link["overall"].get("link_rate_all_pct")
        tiles.append(
            {
                "key": "link_rate",
                "label": "Market link rate",
                "value": f"{pct}%" if pct is not None else "—",
                "numeric": pct,
                "status": _status_from_pct(pct, green=99, amber=90),
                "detail": (
                    f"{link['overall'].get('linked', 0)}/"
                    f"{link['overall'].get('total_game_markets', 0)} game markets linked"
                ),
                "href": "/admin/matching",
            }
        )
    else:
        tiles.append(
            {
                "key": "link_rate",
                "label": "Market link rate",
                "value": "—",
                "numeric": None,
                "status": "unknown",
                "detail": "cache cold — open Matching Review to warm it",
                "href": "/admin/matching",
            }
        )

    # --- Grid health (warm cache from precompute_admin_audit_all) ---
    audit = _read_redis_json("bainluck:admin:audit_all")
    if audit and audit.get("avg_score") is not None:
        avg = audit["avg_score"]
        scores = audit.get("scores") or {}
        tiles.append(
            {
                "key": "grid_health",
                "label": "Grid health",
                "value": f"{avg}/100",
                "numeric": avg,
                "status": _status_from_pct(avg, green=99, amber=90),
                "detail": ", ".join(f"{g}:{s}" for g, s in scores.items()) or "no grids",
                "href": "/admin/matching",
            }
        )
    else:
        tiles.append(
            {
                "key": "grid_health",
                "label": "Grid health",
                "value": "—",
                "numeric": None,
                "status": "unknown",
                "detail": "cache cold — open Matching Review to warm it",
                "href": "/admin/matching",
            }
        )

    # --- Queue depth (cheap LLEN) ---
    depths = _queue_depths()
    bg = depths.get("background")
    if bg is None:
        q_status = "unknown"
    elif bg > 50:
        q_status = "red"
    elif bg > 20:
        q_status = "amber"
    else:
        q_status = "green"
    tiles.append(
        {
            "key": "queue_depth",
            "label": "Background queue",
            "value": str(bg) if bg is not None else "—",
            "numeric": bg,
            "status": q_status,
            "detail": (
                f"realtime: {depths.get('realtime')}"
                if depths.get("realtime") is not None
                else "realtime: —"
            ),
            "href": "/admin",
        }
    )

    # --- Feed quality (latest offline eval run, lower boring-rate is better) ---
    try:
        eval_row = (
            await db.execute(
                select(DiscoverLabelEvalRun)
                .order_by(DiscoverLabelEvalRun.captured_at.desc())
                .limit(1)
            )
        ).scalars().first()
    except Exception:
        eval_row = None
        logger.debug("cockpit: feed-quality query failed", exc_info=True)

    if eval_row is not None and eval_row.boring_rate_at_k is not None:
        boring = eval_row.boring_rate_at_k
        boring_pct = round(boring * 100, 1)
        if boring <= 0:
            fq_status = "green"
        elif boring <= 0.05:
            fq_status = "amber"
        else:
            fq_status = "red"
        tiles.append(
            {
                "key": "feed_quality",
                "label": f"Feed boring-rate@{eval_row.top_k}",
                "value": f"{boring_pct}%",
                "numeric": boring_pct,
                "status": fq_status,
                "detail": (
                    f"dup {round((eval_row.duplicate_family_rate_at_k or 0) * 100)}% · "
                    f"bad-expl {round((eval_row.bad_explanation_rate_at_k or 0) * 100)}%"
                ),
                "href": "/admin/discover-quality",
            }
        )
    else:
        tiles.append(
            {
                "key": "feed_quality",
                "label": "Feed boring-rate",
                "value": "—",
                "numeric": None,
                "status": "unknown",
                "detail": "no eval run recorded yet",
                "href": "/admin/discover-quality",
            }
        )

    # --- Creation freshness per source (cheap MAX(created_at)) ---
    freshness = await _creation_freshness(db)
    worst_hours = None
    worst_src = None
    for src, hrs in freshness.items():
        if hrs is None:
            continue
        if worst_hours is None or hrs > worst_hours:
            worst_hours = hrs
            worst_src = src
    if worst_hours is None:
        f_status = "unknown"
    elif worst_hours >= 24:
        f_status = "red"
    elif worst_hours >= 6:
        f_status = "amber"
    else:
        f_status = "green"
    tiles.append(
        {
            "key": "creation_freshness",
            "label": "Newest market age",
            "value": f"{worst_hours}h" if worst_hours is not None else "—",
            "numeric": worst_hours,
            "status": f_status,
            "detail": ", ".join(
                f"{s}: {h}h" if h is not None else f"{s}: —"
                for s, h in freshness.items()
            ),
            "href": "/admin/source-intelligence",
        }
    )

    return tiles


async def _creation_freshness(db: AsyncSession) -> dict:
    """Hours since the newest created row per ingestion source.

    Catches the Kalshi create-freeze class (gotcha #35/create-freeze memo):
    updates can stay fresh while creation silently stops.
    """
    out: dict[str, float | None] = {"kalshi": None, "polymarket": None, "odds": None}
    try:
        rows = await db.execute(
            select(FuturesMarket.source, func.max(FuturesMarket.created_at))
            .where(FuturesMarket.source.in_(["kalshi", "polymarket"]))
            .group_by(FuturesMarket.source)
        )
        for src, newest in rows.all():
            if src in out:
                out[src] = _hours_since(newest)
    except Exception:
        logger.debug("cockpit: futures freshness query failed", exc_info=True)

    try:
        newest_event = await db.execute(select(func.max(Event.created_at)))
        out["odds"] = _hours_since(newest_event.scalar_one_or_none())
    except Exception:
        logger.debug("cockpit: event freshness query failed", exc_info=True)

    return out


def _waiting_on_you() -> dict:
    """GitHub issues labeled needs-user, or the static standing fallback."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        try:
            import httpx

            resp = httpx.get(
                "https://api.github.com/repos/alexander-bain/bainluck/issues",
                params={"labels": "needs-user", "state": "open", "per_page": 20},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=5.0,
            )
            if resp.status_code == 200:
                items = [
                    {
                        "ref": f"#{it['number']}",
                        "title": it.get("title", ""),
                        "action": it.get("title", ""),
                        "url": it.get("html_url", ""),
                    }
                    for it in resp.json()
                    if "pull_request" not in it
                ]
                return {"source": "github", "items": items}
        except Exception:
            logger.debug("cockpit: github needs-user fetch failed", exc_info=True)

    return {"source": "fallback", "items": _WAITING_FALLBACK}


async def _eval_queue(db: AsyncSession) -> dict:
    """Pending LLM proposals (for inline accept/reject) + new bug report count."""
    # Pending llm_proposed_* rows, minus any that already have a human verdict —
    # same semantics as /admin/label-pass/pending, kept lightweight here.
    proposals_res = await db.execute(
        select(DiscoverReviewDecision)
        .where(
            DiscoverReviewDecision.decision.in_(
                ["llm_proposed_promote", "llm_proposed_downrank"]
            )
        )
        .order_by(DiscoverReviewDecision.created_at.desc())
        .limit(500)
    )
    proposals = proposals_res.scalars().all()

    verdicted: set[tuple[str, str]] = set()
    if proposals:
        verdict_res = await db.execute(
            select(
                DiscoverReviewDecision.item_type,
                DiscoverReviewDecision.item_id,
            ).where(
                DiscoverReviewDecision.decision.in_(
                    [
                        "accepted_promote",
                        "rejected_promote",
                        "accepted_downrank",
                        "rejected_downrank",
                        "skipped",
                    ]
                )
            )
        )
        for row in verdict_res.all():
            verdicted.add((row[0], row[1]))

    pending = [p for p in proposals if (p.item_type, p.item_id) not in verdicted]
    sample = [
        {
            "id": p.id,
            "item_name": p.item_name,
            "category": p.category,
            "decision": p.decision,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pending[:8]
    ]

    new_bugs = (
        await db.execute(
            select(func.count(BugReport.id)).where(BugReport.status == "new")
        )
    ).scalar()

    return {
        "pending_eval_count": len(pending),
        "pending_eval_sample": sample,
        "new_bug_reports": int(new_bugs or 0),
        "verdict_endpoint": "/api/admin/label-pass/verdict",
        "eval_href": "/admin/eval",
        "bug_reports_href": "/admin/bug-reports",
    }


@router.get("/cockpit")
async def cockpit(
    request: Request,
    secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
    bust: int = Query(0, include_in_schema=False),
):
    """Alex Cockpit — health tiles, what's waiting on Alex, and the quick-eval queue."""
    _check_admin_secret(secret, request=request)

    if not bust:
        cached = _read_redis_json(_CACHE_KEY)
        if cached:
            cached["cached"] = True
            return cached

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
        "health": await _health_group(db),
        "waiting_on_you": _waiting_on_you(),
        "eval_queue": await _eval_queue(db),
    }

    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(_CACHE_KEY, _json.dumps(payload), ex=_CACHE_TTL)
    except Exception:
        logger.debug("cockpit: could not write cache", exc_info=True)

    return payload
