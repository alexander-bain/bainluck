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


# L2-104 honesty pass: known context for RED health sub-signals, so a tracked or
# expected RED never reads as a fresh four-alarm fire. Keyed by (tile_key,
# sub_label). Anything RED and ABSENT here is a genuine untracked alarm — the
# frontend renders that state distinctly.
_RED_CONTEXT: dict[tuple[str, str], dict] = {
    ("grid_health", "nba"): {
        "kind": "tracked",
        "ref": "#1059",
        "note": "NBA-Kalshi degenerate mapping",
        "url": "https://github.com/alexander-bain/bainluck/issues/1059",
    },
    ("grid_health", "golf"): {
        "kind": "artifact",
        "note": "pre-tournament illiquidity, expected",
    },
}


def _status_from_pct(pct: float | None, *, green: float, amber: float) -> str:
    """Green/amber/red band for a higher-is-better percentage."""
    if pct is None:
        return "unknown"
    if pct >= green:
        return "green"
    if pct >= amber:
        return "amber"
    return "red"


def _red_sub_context(tile_key: str, label: str, value: str) -> dict:
    """Annotate a RED sub-signal as tracked / known-artifact / untracked.

    A RED that is neither tracked (an open issue) nor a known artifact is the
    only genuine four-alarm state; the frontend surfaces ``untracked`` distinctly.
    """
    ctx = _RED_CONTEXT.get((tile_key, label))
    if ctx is None:
        return {
            "label": label,
            "value": value,
            "kind": "untracked",
            "note": None,
            "ref": None,
            "url": None,
        }
    return {
        "label": label,
        "value": value,
        "kind": ctx["kind"],
        "note": ctx.get("note"),
        "ref": ctx.get("ref"),
        "url": ctx.get("url"),
    }


def _hours_since(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((datetime.now(timezone.utc) - dt).total_seconds() / 3600.0, 1)


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# L2-105 autopilot visibility: scheduled beats that silently stop firing are
# invisible until someone digs. r178 found ``calibration_prices`` had ZERO
# scheduled fires for weeks (it kept missing its 6-hourly slot under background-
# worker contention) while occasional manual triggers masked it — see memory
# [[project_cal_price_beat_not_firing]]. These tiles put last-fire age, fires/24h,
# and the rescued count on the dashboard Alex actually looks at. Task metrics have
# NO scheduled-vs-manual flag, so successes_24h vs the beat's cadence
# (``expected_24h``) is the honest proxy: fires/24h below cadence reads AMBER even
# when the last fire was recent — that is exactly the r178 "only-manual" signature.
_AUTOPILOT_BEATS = [
    {
        "label": "calibration_prices",  # metric label from _tracked_run (NOT the beat name)
        "display": "Cal-price beat",
        "schedule": "every 6h (02/08/14/20:10 UTC)",
        "expected_24h": 4,
        "stale_hours": 8,  # 6h cadence → >8h means a scheduled slot was missed
        "rescued_field": "rescued",
        "href": "/admin",
    },
    {
        "label": "backfill_combat_wps",
        "display": "Combat WPS backfill",
        "schedule": "daily 09:50 UTC",
        "expected_24h": 1,
        "stale_hours": 28,  # daily → allow slack past 24h before RED
        "rescued_field": "written",
        "first_fire": "2026-07-14T09:50:00+00:00",
        "href": "/admin",
    },
]


def _autopilot_tile(beat: dict, metrics: dict) -> dict:
    """Site-health tile for one scheduled beat (last-fire age, fires/24h, rescued).

    Pure over ``metrics`` (a ``get_task_metrics`` dict) so it unit-tests without
    Redis. RED = never fired, or stale past the beat's cadence. AMBER = fresh but
    firing below cadence (the r178 "only-manual, beat not scheduled-firing"
    signature) or inside the approaching-stale window. A beat scheduled to start
    in the future reads "awaiting first fire" and is never RED.
    """
    label = beat["label"]
    key = f"autopilot:{label}"
    last_dt = _parse_iso(metrics.get("last_success_at"))
    hrs = _hours_since(last_dt)
    successes = metrics.get("successes_24h")
    summary = metrics.get("last_result_summary")
    rescued = summary.get(beat["rescued_field"]) if isinstance(summary, dict) else None
    expected = beat.get("expected_24h")
    stale = beat["stale_hours"]

    # Pre-first-fire: a beat scheduled to begin later isn't broken — it's pending.
    first_fire = _parse_iso(beat.get("first_fire"))
    if last_dt is None and first_fire is not None and first_fire > datetime.now(timezone.utc):
        return {
            "key": key,
            "label": beat["display"],
            "value": "—",
            "numeric": None,
            "status": "unknown",
            "detail": (
                f"awaiting first fire · {beat['schedule']} · "
                f"starts {first_fire.strftime('%b %d %H:%MZ')}"
            ),
            "href": beat["href"],
        }

    if hrs is None or hrs > stale:
        status = "red"
    elif hrs > stale * 0.75:
        status = "amber"
    elif expected and successes is not None and successes < expected:
        status = "amber"
    else:
        status = "green"

    detail_bits = [beat["schedule"]]
    if successes is not None:
        exp = f"/{expected}" if expected else ""
        detail_bits.append(f"{successes}{exp} fires/24h")
    else:
        detail_bits.append("no fires/24h recorded")
    if rescued is not None:
        detail_bits.append(f"{rescued} rescued")

    return {
        "key": key,
        "label": beat["display"],
        "value": f"{hrs}h ago" if hrs is not None else "never fired",
        "numeric": hrs,
        "status": status,
        "detail": " · ".join(detail_bits),
        "href": beat["href"],
    }


def _feed_quality_empty_detail(eval_row) -> str:
    """Honest empty-state text for the feed boring-rate tile (L2-106).

    The metric comes from the daily human-label gold-set eval
    (``snapshot_discover_label_eval_run`` — the 09:55 UTC background beat), which
    scores recent ``RankingJudgment`` labels. The tile reads "—" in two distinct
    cases; name which one so it never looks like a broken pipeline:

      - no run row at all → the beat hasn't written one yet (e.g. hasn't fired
        since the last deploy) OR there are no human labels to score;
      - a run exists but ``boring_rate`` is null → the beat ran but scored zero
        graded labels in its window.

    Both are fixed the same way — grade markets in Discover Quality — so the text
    points there (the tile's ``href``). Display-shaping only; no scheduling.
    """
    if eval_row is None:
        return (
            "No gold-set eval recorded yet — the daily label-eval beat "
            "(09:55 UTC) writes one from human labels. If it hasn't run since the "
            "last deploy, wait a cycle; otherwise grade markets in Discover Quality "
            "to seed it."
        )
    captured_age = _hours_since(getattr(eval_row, "captured_at", None))
    age_str = f"{captured_age}h ago" if captured_age is not None else "recently"
    return (
        f"Last eval ran {age_str} but scored 0 human labels — grade markets in "
        "Discover Quality to populate boring-rate."
    )


_GH_ISSUE_URL = "https://github.com/alexander-bain/bainluck/issues/{}"


def _flow_sentinel_group() -> dict:
    """Per-flow pass/fail from the last Flow Sentinel run (#1078 / Queue #185).

    Reads the scorecard the sentinel persists at ``bainluck:flow_sentinel:last``
    (14d TTL, ``GET /api/admin/flow-sentinel/run`` also writes it) and shapes it
    for the cockpit: an overall banded status plus one row per flow, each linked
    to the issue the sentinel filed for it (if any). Pure display — it never
    re-runs the flows. RED if any flow failed; AMBER if none failed but one was
    skipped (e.g. event_completeness idles in the summer offseason); GREEN when
    every flow that ran passed; UNKNOWN before the first run is cached.
    """
    raw = _read_redis_json("bainluck:flow_sentinel:last")
    if not raw or raw.get("status") == "no_run_cached" or "scorecard" not in raw:
        return {
            "status": "unknown",
            "detail": (
                "No Flow Sentinel run cached yet — it runs daily (07:10 UTC) or "
                "on POST /api/admin/flow-sentinel/run."
            ),
            "per_flow": [],
        }

    scorecard = raw.get("scorecard") or {}
    per_flow = scorecard.get("per_flow") or []

    # flow → the issue this run filed/commented on (so a failing tile links out).
    filed_by_flow: dict[str, int] = {}
    for f in raw.get("filed") or []:
        if isinstance(f, dict) and f.get("issue") and f.get("flow"):
            try:
                filed_by_flow[str(f["flow"])] = int(f["issue"])
            except (TypeError, ValueError):
                continue

    rows: list[dict] = []
    for pf in per_flow:
        if not isinstance(pf, dict):
            continue
        flow = str(pf.get("flow") or "?")
        passed = bool(pf.get("passed"))
        skipped = bool(pf.get("skipped"))
        flow_status = "amber" if skipped else ("green" if passed else "red")
        issue = filed_by_flow.get(flow)
        rows.append(
            {
                "flow": flow,
                "passed": passed,
                "skipped": skipped,
                "checked": pf.get("checked"),
                "failing": pf.get("failing"),
                "status": flow_status,
                "issue": issue,
                "issue_url": _GH_ISSUE_URL.format(issue) if issue else None,
            }
        )

    failed = scorecard.get("flows_failed") or 0
    if failed:
        overall = "red"
    elif any(r["skipped"] for r in rows):
        overall = "amber"
    elif rows:
        overall = "green"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "mode": raw.get("mode"),
        "flows_total": scorecard.get("flows_total"),
        "flows_passed": scorecard.get("flows_passed"),
        "flows_failed": failed,
        "duration_seconds": raw.get("duration_seconds"),
        "per_flow": rows,
    }


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
    # L2-104 honesty pass: the HEADLINE is the open-markets rate (the CLAUDE.md
    # metric, ~99.6%). The all-status rate (~90.3%) is real but capped by aged-out
    # settled markets that stay status='open' in our DB (gotcha #35) — demote it
    # to a subtitle so it never reads as a fixable gap.
    link = _read_redis_json("bainluck:admin:link_rate")
    if link and isinstance(link.get("overall"), dict):
        overall = link["overall"]
        open_pct = overall.get("link_rate_pct")
        all_pct = overall.get("link_rate_all_pct")
        open_linked = overall.get("open_linked")
        open_total = overall.get("open_total")
        detail_bits = []
        if open_linked is not None and open_total is not None:
            detail_bits.append(f"{open_linked}/{open_total} open game markets linked")
        if all_pct is not None:
            detail_bits.append(
                f"{all_pct}% all-status — capped by aged-out settled markets (gotcha #35)"
            )
        tiles.append(
            {
                "key": "link_rate",
                "label": "Market link rate",
                "value": f"{open_pct}%" if open_pct is not None else "—",
                "numeric": open_pct,
                "status": _status_from_pct(open_pct, green=99, amber=90),
                "detail": " · ".join(detail_bits) if detail_bits else None,
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
        # L2-104: annotate each RED grid (below the amber band) so a tracked or
        # expected RED reads as context, not a fresh alarm; untracked REDs stay
        # four-alarm and sort to the front for the frontend to surface distinctly.
        grid_context = [
            _red_sub_context("grid_health", g, f"{s}/100")
            for g, s in scores.items()
            if isinstance(s, (int, float))
            and _status_from_pct(s, green=99, amber=90) == "red"
        ]
        grid_context.sort(key=lambda c: 0 if c["kind"] == "untracked" else 1)
        tiles.append(
            {
                "key": "grid_health",
                "label": "Grid health",
                "value": f"{avg}/100",
                "numeric": avg,
                "status": _status_from_pct(avg, green=99, amber=90),
                "detail": ", ".join(f"{g}:{s}" for g, s in scores.items()) or "no grids",
                "context": grid_context,
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
                "detail": _feed_quality_empty_detail(eval_row),
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

    # --- Autopilot beats (L2-105): scheduled-fire visibility ---
    # Read each beat's live task-metrics (cheap hgetall via get_task_metrics) and
    # render a last-fire/fires-24h/rescued tile. Isolated in try/except so a Redis
    # hiccup degrades to no autopilot tiles rather than breaking the whole payload.
    try:
        from app.tasks.redis_state import get_task_metrics

        for beat in _AUTOPILOT_BEATS:
            try:
                m = get_task_metrics(beat["label"])
            except Exception:
                m = {}
            tiles.append(_autopilot_tile(beat, m))
    except Exception:
        logger.debug("cockpit: autopilot tiles failed", exc_info=True)

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
        "flow_sentinel": _flow_sentinel_group(),
    }

    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(_CACHE_KEY, _json.dumps(payload), ex=_CACHE_TTL)
    except Exception:
        logger.debug("cockpit: could not write cache", exc_info=True)

    return payload
