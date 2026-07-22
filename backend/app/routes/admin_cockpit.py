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
            "generated_at": None,
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
        # #232/Queue #234 Item 3: pass through the sentinel's own run stamp so the
        # cockpit renders per-sentinel age ("ran 6h ago") instead of age=None. The
        # sentinel persists generated_at in its cached payload (#232); None only
        # during the deploy-transition window before the first post-#232 run.
        "generated_at": raw.get("generated_at"),
        "per_flow": rows,
    }


def _grid_sentinel_group() -> dict | None:
    """Per-league grid VERDICT from the last Grid Sentinel run (Queue #196).

    Reads the scorecard the sentinel persists at ``bainluck:grid_sentinel:last``
    (14d TTL; ``POST /api/admin/grid-sentinel/run`` also writes it) and shapes it
    for the grid tile. The whole point (the mlb-66 lesson): a grid's tile status
    is its VERDICT — RED only when a REAL defect survives the artifact registry —
    not the raw penalty score, which cried wolf on blend-hidden source
    disagreement. RED if any league has real defects; AMBER if none do but a
    league carries explained artifacts/watches; GREEN when every league is clean.
    Returns None (not a stale tile) before the first run is cached, so the caller
    falls back to the raw audit score."""
    raw = _read_redis_json("bainluck:grid_sentinel:last")
    if not raw or "scorecard" not in raw:
        return None
    per = (raw.get("scorecard") or {}).get("per_league") or []
    if not per:
        return None

    filed_by_league: dict[str, int] = {}
    for f in raw.get("filed") or []:
        if isinstance(f, dict) and f.get("issue") and f.get("league"):
            try:
                filed_by_league[str(f["league"])] = int(f["issue"])
            except (TypeError, ValueError):
                continue

    rows = []
    any_real = False
    any_artifact = False
    for lg in per:
        if not isinstance(lg, dict):
            continue
        real = int(lg.get("real_defects") or 0)
        arts = int(lg.get("explained_artifacts") or 0)
        watch = int(lg.get("watch") or 0)
        any_real = any_real or real > 0
        any_artifact = any_artifact or arts > 0 or watch > 0
        league = str(lg.get("league") or "?")
        issue = filed_by_league.get(league)
        rows.append({
            "league": league,
            "verdict": lg.get("verdict"),
            "phase": lg.get("phase"),
            "real_defects": real,
            "explained_artifacts": arts,
            "watch": watch,
            "status": "red" if real else ("amber" if (arts or watch) else "green"),
            "issue": issue,
            "issue_url": _GH_ISSUE_URL.format(issue) if issue else None,
        })

    overall = "red" if any_real else ("amber" if any_artifact else "green")
    return {
        "status": overall,
        "mode": raw.get("mode"),
        "leagues_total": (raw.get("scorecard") or {}).get("leagues_total"),
        "leagues_red": (raw.get("scorecard") or {}).get("leagues_red"),
        "duration_seconds": raw.get("duration_seconds"),
        # #232/Queue #234 Item 3: per-sentinel run stamp (see _flow_sentinel_group).
        "generated_at": raw.get("generated_at"),
        "per_league": rows,
    }


def _data_quality_group() -> dict:
    """Data-quality watchdog VERDICT as a cockpit tile (#1132 / L2-140).

    Reads the summary the watchdog persists at
    ``bainluck:data_quality_watchdog:last`` (26h TTL) and shapes it to the exact
    contract the L2-140 frontend renders (``data_quality_watchdog`` group with a
    ``per_check`` list). The point (the #1091 lesson wearing a new coat): a P0/P1
    that only emails a personal inbox + files a GitHub issue is a SILENT alert —
    the cockpit is the always-open eye. RED when any P0/P1 check is failing; AMBER
    on a P2 failure or a self-error (monitor unreliable); GREEN when all clear.
    Always returns a group (never None): before the first run, status='unknown'
    with an empty per_check so the tile renders 'unknown', never a false green."""
    raw = _read_redis_json("bainluck:data_quality_watchdog:last")
    if not raw or "status" not in raw:
        return {
            "status": "unknown",
            "detail": (
                "No data-quality watchdog run cached yet — it runs on its schedule "
                "or on POST /api/admin/data-quality/check."
            ),
            "per_check": [],
        }

    per_check = [
        {
            "name": f.get("name"),
            "severity": f.get("severity"),
            "message": f.get("message"),
            "value": f.get("value"),
            "threshold": f.get("threshold"),
            "status": "red" if f.get("severity") in ("P0", "P1") else "amber",
            "issue": f.get("issue"),
            "issue_url": _GH_ISSUE_URL.format(f["issue"]) if f.get("issue") else None,
        }
        for f in (raw.get("failing") or [])
        if isinstance(f, dict)
    ]
    return {
        "status": raw.get("status", "unknown"),
        "last_run": raw.get("computed_at"),
        "checks_run": raw.get("checks_run"),
        "checks_passed": raw.get("checks_passed"),
        "alerts_fired": raw.get("alerts_fired"),
        "self_error": raw.get("self_error"),
        "per_check": per_check,
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


def _watchdog_stuck_phases() -> list[dict]:
    """Stuck-fetch entries from the warm freshness-watchdog summary (L2-116).

    The phase-heartbeat watchdog (`tasks/watchdog.py`) writes
    `bainluck:watchdog:summary` (1h TTL) with a `phase_heartbeat.stuck` list of
    poll phases whose `running_phase` marker has not advanced past
    PHASE_STUCK_SECONDS — a genuinely wedged fetch (#995's synchronous-op block),
    which is the DISTINCT failure mode the idle-misread fix must keep visible.
    Pure warm read (no query); returns [] on cold cache or any error so the tile
    degrades to its plain queue detail rather than breaking the payload."""
    summary = _read_redis_json("bainluck:watchdog:summary")
    if not isinstance(summary, dict):
        return []
    phase = summary.get("phase_heartbeat")
    stuck = phase.get("stuck") if isinstance(phase, dict) else None
    return [s for s in stuck if isinstance(s, dict)] if isinstance(stuck, list) else []


def _worker_heartbeat_age() -> float | None:
    """Seconds since the last Celery worker heartbeat (None if never/unreadable).

    Mirrors the celery dashboard's heartbeat read (``admin_celery.py``): the
    realtime worker refreshes ``bainluck:heartbeat`` every ~60s; an age past 180s
    means the workers are down and NO task metric can be trusted — the tile must
    read red regardless of per-task health."""
    try:
        from app.tasks.redis_state import get_redis_client

        hb = get_redis_client().get("bainluck:heartbeat")
        if not hb:
            return None
        hb_str = hb.decode() if isinstance(hb, bytes) else hb
        hb_dt = datetime.fromisoformat(hb_str)
        if hb_dt.tzinfo is None:
            hb_dt = hb_dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - hb_dt).total_seconds()
    except Exception:
        logger.debug("cockpit: heartbeat read failed", exc_info=True)
        return None


def _celery_health_tile() -> dict:
    """First-class worker-health tile from the fixed get_task_metrics (L2-117).

    L2-116 fixed ``get_task_metrics`` (idle→no_data instead of a latched
    critical), but the cockpit still had NO overall celery/worker tile — the
    only place worker health rendered was buried in the full ops dashboard.
    This tile mirrors the celery dashboard's ``overall_health`` banding
    (``admin_celery.py``) so both agree, and surfaces the failing tasks WITH
    their consecutive-failure counts as the tile detail (the honest first render:
    the genuinely-failing tasks show RED and named).

    Banding (celery-dashboard parity → cockpit green/amber/red/unknown):
      - worker heartbeat stale (>180s) → red ("worker down"): metrics untrustworthy
      - any task health == critical (consecutive >= 5) → red
      - any task health == degraded (consecutive >= 2) → amber
      - tasks tracked, none failing → green
      - no tasks / no heartbeat cache → unknown

    Retired and idle (no_data) tasks are excluded from the failing rollups by
    ``get_task_metrics`` itself, so the idle-misread can never turn this red.
    Pure warm read (hgetall per task); isolated by the caller's try/except.
    """
    hb_age = _worker_heartbeat_age()
    from app.tasks.redis_state import get_all_task_metrics

    tasks = get_all_task_metrics()
    critical = [t for t in tasks if t.get("health") == "critical"]
    degraded = [t for t in tasks if t.get("health") == "degraded"]

    def _label(t: dict) -> str:
        name = t.get("task", "?")
        c = t.get("consecutive_failures")
        try:
            c = int(c)
        except (TypeError, ValueError):
            c = None
        return f"{name} ×{c}" if c else name

    worker_down = hb_age is not None and hb_age > 180
    if hb_age is None and not tasks:
        status, value = "unknown", "—"
    elif worker_down:
        status, value = "red", "Worker down"
    elif critical:
        status, value = "red", "Critical"
    elif degraded:
        status, value = "amber", "Degraded"
    elif not tasks:
        status, value = "unknown", "—"
    else:
        status, value = "green", "Healthy"

    detail_bits: list[str] = []
    if worker_down:
        detail_bits.append(f"⚠ no heartbeat for {round(hb_age)}s — tasks may not be running")
    if critical:
        detail_bits.append(f"{len(critical)} failing: " + ", ".join(_label(t) for t in critical[:4]))
    if degraded:
        detail_bits.append(f"{len(degraded)} degraded: " + ", ".join(_label(t) for t in degraded[:4]))
    if not detail_bits:
        if tasks:
            hb_str = f"heartbeat {round(hb_age)}s ago" if hb_age is not None else "heartbeat —"
            detail_bits.append(f"{len(tasks)} tasks tracked · all healthy · {hb_str}")
        else:
            detail_bits.append("no task metrics recorded yet — workers idle or cache cold")

    return {
        "key": "celery_health",
        "label": "Worker health",
        "value": value,
        "numeric": None,
        "status": status,
        "detail": " · ".join(detail_bits),
        "href": "/admin",
    }


def _raw_link_rate_subtitle() -> str | None:
    """The raw market link-rate, worded as the link tile's diagnostic subtitle
    (L2-145 Item 1). Never its own tile — it cried wolf (below-100 for non-defect
    reasons), so it rides along under the matured-linkage headline as context.
    Returns None when the cache is cold (the tile then omits the subtitle)."""
    link = _read_redis_json("bainluck:admin:link_rate")
    if link and isinstance(link.get("overall"), dict):
        overall = link["overall"]
        open_pct = overall.get("link_rate_pct")
        all_pct = overall.get("link_rate_all_pct")
        open_linked = overall.get("open_linked")
        open_total = overall.get("open_total")
        bits: list[str] = []
        if open_pct is not None:
            head = f"raw link rate {open_pct}% open"
            if open_linked is not None and open_total is not None:
                head += f" ({open_linked}/{open_total} game markets)"
            bits.append(head)
        if all_pct is not None:
            bits.append(
                f"{all_pct}% all-status — capped by the aged-out settled-market flood (gotcha #35)"
            )
        return " · ".join(bits) if bits else None
    return None


_LINK_TILE_STATE_KEY = "bainluck:admin:link_tile_state"


def _fmt_duration(seconds: float) -> str:
    """Compact h/m/s duration for tile subtitles (e.g. '2h04m', '5m', '45s')."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    mins = seconds // 60
    if mins < 60:
        return f"{mins}m"
    hrs = mins // 60
    return f"{hrs}h{mins % 60:02d}m"


def _link_tile_state_change(status: str, value) -> dict | None:
    """Track when the link tile's status band last changed (L2-146 Item 3).

    When Lane 1's matcher fix lands and the tile returns to 100%, the recovery
    should be visible on the tile itself — no log archaeology. This records the
    tile's status + a `since` timestamp in Redis and reports how long the tile
    has held its current state (and what it changed from).

    Write-on-read is cheap and idempotent; the whole cockpit payload is cached
    5 min (``_CACHE_TTL``), so this fires at most once per cache refresh —
    timestamps are accurate to the refresh cadence, which is all the recovery
    watch needs. Degrades to None on any Redis error so the tile simply omits
    the recovery subtitle rather than breaking the payload.

    Returns ``{'age_s': float, 'prev': str|None, 'bootstrap': bool}`` or None.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        now = datetime.now(timezone.utc)
        raw = r.get(_LINK_TILE_STATE_KEY)
        prior = None
        if raw:
            try:
                prior = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            except Exception:
                prior = None
        if prior and prior.get("status") == status:
            since_iso = prior.get("since")
            try:
                since_dt = datetime.fromisoformat(since_iso) if since_iso else now
            except Exception:
                since_dt = now
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            return {
                "age_s": (now - since_dt).total_seconds(),
                "prev": prior.get("prev"),
                "bootstrap": False,
            }
        # Status changed (or first observation) — stamp a fresh transition.
        prev_status = prior.get("status") if prior else None
        r.set(
            _LINK_TILE_STATE_KEY,
            _json.dumps(
                {
                    "status": status,
                    "value": value,
                    "since": now.isoformat(),
                    "prev": prev_status,
                }
            ),
        )
        return {"age_s": 0.0, "prev": prev_status, "bootstrap": prev_status is None}
    except Exception:
        logger.debug("cockpit: link tile state-change read failed", exc_info=True)
        return None


def _apply_link_tile_state_change(detail_bits: list[str], status: str, value) -> None:
    """Append a 'how long in this state / recovered from what' bit to the link
    tile's detail (L2-146 Item 3). No-op on the first ever observation (nothing
    to report yet) or on any Redis error."""
    change = _link_tile_state_change(status, value)
    if not change or change["bootstrap"]:
        return
    age = _fmt_duration(change["age_s"])
    prev = change["prev"]
    if status == "green" and prev and prev != "green":
        detail_bits.append(f"recovered {age} ago (was {prev})")
    elif prev and prev != status:
        detail_bits.append(f"{status} for {age} (was {prev})")
    else:
        detail_bits.append(f"stable {status} for {age}")


async def _health_group(db: AsyncSession) -> list[dict]:
    """Build the site-health tile row from warm caches + cheap queries."""
    tiles: list[dict] = []

    # --- Worker health (L2-117): first-class celery/worker tile ---
    # Placed first: if the workers are down, every other warm-cache tile below is
    # stale-by-omission, so surface the worker state before anything else. Isolated
    # so a Redis hiccup degrades to no worker tile rather than breaking the payload.
    try:
        tiles.append(_celery_health_tile())
    except Exception:
        logger.debug("cockpit: celery health tile failed", exc_info=True)

    # --- The link tile (L2-145 Item 1) — ONE tile: matured-linkage is the
    # HEADLINE number, the raw market link-rate is the diagnostic subtitle. ---
    # Alex's ruling (earned by r227's clean 100% read): below-100 must MEAN
    # something. The raw market link-rate cried wolf — it sits permanently below
    # 100 for non-defect reasons (upstream coverage gaps + a settled-market flood
    # that drains the all-status denominator as markets age out, gotcha #35), so
    # its below-100 is noise, not a fixable defect. The tile that reigns is
    # matured-linkage: of imminent events (≤24h) it counts blend prediction-market
    # sources with NO linked winner market — a phantom blend source, always a real
    # defect. The old standalone raw-rate tile retires; the raw rate now rides
    # along in this tile's subtitle as context, never its own tile again.
    raw_subtitle = _raw_link_rate_subtitle()
    ml = _read_redis_json("bainluck:admin:matured_linkage")
    if ml and ml.get("status") == "ok":
        ml_pct = ml.get("headline_pct")
        phantom = ml.get("phantom") or 0
        checkable = ml.get("checkable_pairs") or 0
        # 100 = clean. Any phantom is a real defect → amber below 100.
        ml_status = (
            "green" if ml_pct == 100 else _status_from_pct(ml_pct, green=100, amber=90)
        )
        if ml_pct == 100:
            detail_bits = ["every matured event fully linked"]
        else:
            detail_bits = [f"{ml.get('backed')}/{checkable} imminent blend sources linked"]
        if phantom:
            detail_bits.append(f"{phantom} phantom (in blend, no linked market)")
        # L2-146 Item 3: surface how long the tile has held this state so a
        # recovery to 100% (when Lane 1's matcher fix lands) is self-evident.
        _apply_link_tile_state_change(detail_bits, ml_status, ml_pct)
        if raw_subtitle:
            detail_bits.append(raw_subtitle)
        tiles.append(
            {
                "key": "link_rate",
                "label": "Link rate",
                "value": f"{ml_pct}%" if ml_pct is not None else "—",
                "numeric": ml_pct,
                "status": ml_status,
                "detail": " · ".join(detail_bits),
                "href": "/admin/matching",
            }
        )
    elif ml and ml.get("status") == "insufficient_slate":
        detail_bits = ["no imminent Kalshi/Poly blend sources to check (off-brand slate)"]
        if raw_subtitle:
            detail_bits.append(raw_subtitle)
        tiles.append(
            {
                "key": "link_rate",
                "label": "Link rate",
                "value": "n/a",
                "numeric": None,
                "status": "unknown",
                "detail": " · ".join(detail_bits),
                "href": "/admin/matching",
            }
        )
    else:
        detail_bits = ["cache cold — matured-linkage beat has not run yet"]
        if raw_subtitle:
            detail_bits.append(raw_subtitle)
        tiles.append(
            {
                "key": "link_rate",
                "label": "Link rate",
                "value": "—",
                "numeric": None,
                "status": "unknown",
                "detail": " · ".join(detail_bits),
                "href": "/admin/matching",
            }
        )

    # --- Grid health ---
    # Queue #196: the Grid Sentinel VERDICT replaces the raw penalty score as the
    # tile's status. The raw score cried wolf (mlb-66 was 100% blend-hidden source
    # disagreement, zero real defects). When a sentinel run is cached, the tile is
    # GREEN/AMBER/RED by real-defect verdict and links to the filed issue; the raw
    # score rides along as secondary context. Cold sentinel cache falls back to the
    # legacy raw-score tile below.
    grid_group = _grid_sentinel_group()
    audit = _read_redis_json("bainluck:admin:audit_all")
    if grid_group:
        reds = [r for r in grid_group["per_league"] if r["status"] == "red"]
        scores = (audit or {}).get("scores") or {}
        if reds:
            detail = "real defects: " + ", ".join(
                f"{r['league']}({r['real_defects']})" for r in reds
            )
        else:
            detail = "no real defects — " + ", ".join(
                f"{r['league']}:{r['verdict']}" for r in grid_group["per_league"]
            )
        grid_context = [
            _red_sub_context("grid_health", r["league"],
                             f"{r['real_defects']} real defect(s), phase {r['phase']}")
            for r in reds
        ]
        tiles.append(
            {
                "key": "grid_health",
                "label": "Grid health",
                "value": ("GREEN" if grid_group["status"] == "green"
                          else grid_group["status"].upper()),
                "numeric": (audit or {}).get("avg_score"),
                "status": grid_group["status"],
                "detail": detail
                + (f"  ·  raw avg {audit['avg_score']}/100" if audit and audit.get("avg_score") is not None else ""),
                "context": grid_context,
                "sentinel": grid_group,
                "raw_scores": scores,
                "href": "/admin/matching",
            }
        )
    elif audit and audit.get("avg_score") is not None:
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
    q_detail = (
        f"realtime: {depths.get('realtime')}"
        if depths.get("realtime") is not None
        else "realtime: —"
    )
    # L2-116 companion signal: the phase-heartbeat watchdog flags a poll that is
    # WEDGED mid-fetch (a `running_phase` marker unchanged past PHASE_STUCK_SECONDS
    # — #995's synchronous-op block). This is the distinct, real failure mode that
    # the idle-misread fix must NOT swallow: an idle task reads green, but a stuck
    # fetch stays visible. It rides the warm watchdog summary (1h TTL) so the tile
    # needs no extra query. A stuck phase elevates the tile to red and names it.
    stuck_phases = _watchdog_stuck_phases()
    if stuck_phases:
        q_status = "red"
        first = stuck_phases[0]
        marker = first.get("marker") or first.get("key") or "poll"
        secs = first.get("stuck_seconds")
        more = f" (+{len(stuck_phases) - 1} more)" if len(stuck_phases) > 1 else ""
        q_detail = (
            f"⚠ stuck fetch: {marker}"
            + (f" — {secs}s no progress" if secs is not None else "")
            + more
            + f" · {q_detail}"
        )
    tiles.append(
        {
            "key": "queue_depth",
            "label": "Background queue",
            "value": str(bg) if bg is not None else "—",
            "numeric": bg,
            "status": q_status,
            "detail": q_detail,
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
    detail = ", ".join(
        f"{s}: {h}h" if h is not None else f"{s}: —"
        for s, h in freshness.items()
    )
    # #219E Item 2(b): honor the watchdog's active creation-stall flag. The
    # newest-age numeric is fooled by a TRICKLE — the poly freeze kept creating
    # ~10/day, so MAX(created_at) age stayed <6h (GREEN) while real creation was
    # dead. When the freshness watchdog has an active stall alert, force RED so a
    # trickle-masked freeze is visible on the cockpit, not just in Sentry/email.
    stall = _read_redis_json("bainluck:watchdog:creation_stale")
    if isinstance(stall, list) and stall:
        f_status = "red"
        _stalled = ", ".join(
            f"{a.get('source')} {a.get('age_hours')}h>{a.get('threshold_hours')}h"
            for a in stall
        )
        detail = f"STALL ALERT: {_stalled} | newest-age {detail}"
    tiles.append(
        {
            "key": "creation_freshness",
            "label": "Newest market age",
            "value": f"{worst_hours}h" if worst_hours is not None else "—",
            "numeric": worst_hours,
            "status": f_status,
            "detail": detail,
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

    # #222: how many human-accepted steers are LIVE in Discover right now — i.e.
    # accepted_* verdicts within the 14-day TTL. This is the observability half of
    # human-in-the-ranking-loop: the number should track the taps Alex makes.
    from app.utils.eval_promote import (
        APPLIED_DECISIONS,
        EVAL_PROMOTE_ENABLED_KEY,
        is_enabled_value,
        ttl_cutoff,
    )

    applied_boosts = (
        await db.execute(
            select(func.count(DiscoverReviewDecision.id)).where(
                DiscoverReviewDecision.decision.in_(list(APPLIED_DECISIONS)),
                DiscoverReviewDecision.created_at >= ttl_cutoff(),
            )
        )
    ).scalar()

    eval_promote_enabled = True
    try:
        from app.tasks.redis_state import get_redis_client

        eval_promote_enabled = is_enabled_value(
            get_redis_client().get(EVAL_PROMOTE_ENABLED_KEY)
        )
    except Exception:
        eval_promote_enabled = True

    return {
        "pending_eval_count": len(pending),
        "pending_eval_sample": sample,
        "new_bug_reports": int(new_bugs or 0),
        "applied_boosts_count": int(applied_boosts or 0),
        "eval_promote_enabled": eval_promote_enabled,
        "verdict_endpoint": "/api/admin/label-pass/verdict",
        "undo_endpoint": "/api/admin/label-pass/undo",
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
        "grid_sentinel": _grid_sentinel_group(),
        "data_quality_watchdog": _data_quality_group(),
    }

    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client().set(_CACHE_KEY, _json.dumps(payload), ex=_CACHE_TTL)
    except Exception:
        logger.debug("cockpit: could not write cache", exc_info=True)

    return payload
