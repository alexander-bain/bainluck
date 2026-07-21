"""#995 NEVER-AGAIN watchdog: market-creation freshness + poll phase-heartbeat.

The 28-day Kalshi market-CREATION freeze (2026-06-09 → 07-06) went undetected
because:
  * the poll SIGKILLed at the 300s/660s wall — a SIGKILL raises no Python
    exception, so Sentry saw nothing; and
  * kalshi_ws + the backfill kept existing rows' ``updated_at`` fresh, so every
    coarse "was anything updated recently?" health check stayed green.

The only signal that catches this class is a CREATES-specific one: "when did we
last create a NEW market for this source?" This module adds two cheap beat
checks that alert (Sentry + an admin-visible Redis flag) the moment either
signal goes bad:

  (a) creation-freshness — MAX(created_at) per source vs a per-source threshold;
  (b) phase-heartbeat    — a poll's phase marker STARTED but not advancing → a
      suspected event-loop block (the exact freeze mechanism), named by phase.
"""

import json
import logging
from datetime import datetime, timezone

import sentry_sdk
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)

# Sources whose market CREATION should never stall for long. Kalshi & Polymarket
# list always-open markets (elections, economics, daily markets) so a multi-hour
# gap with zero new rows is a real freeze, not an off-season schedule gap. The
# poll runs every 1-2h, so 6h = ~3 missed cycles. odds_api is intentionally
# excluded here: it creates game markets that legitimately go quiet in the
# off-season, which needs the season-aware watchdog (deferred to #134).
CREATION_STALENESS_HOURS = {"kalshi": 6, "polymarket": 6}

# Admin-visible flag (surfaced on the ops dashboard); mirrors the alert payload.
CREATION_STALE_FLAG_KEY = "bainluck:watchdog:creation_stale"
# Latest full watchdog result (per-source ages + phase heartbeat) for the admin
# dashboard / /health surface — read-only, refreshed every run.
WATCHDOG_SUMMARY_KEY = "bainluck:watchdog:summary"

# Poll phase markers to heartbeat. Value format written by the poll tasks is
# ``"<phase>@<elapsed>s"``; a frozen loop stops calling _mark_phase entirely, so
# the marker stays BYTE-IDENTICAL across watchdog runs.
PHASE_MARKER_KEYS = {
    "poll_kalshi": "bainluck:poll_kalshi:phase",
    "kalshi_settled": "bainluck:kalshi_settled:phase",
}
_PHASE_SEEN_PREFIX = "bainluck:watchdog:phase_seen:"
PHASE_STUCK_SECONDS = 600  # 10 min unchanged on a non-terminal phase → alert
# Terminal/expected-idle phases: a run that ended here is not "stuck".
_TERMINAL_PHASE_PREFIXES = ("done", "fetch_walltime_exceeded", "idle")


def _bounded_rc():
    """Socket-timeout-bounded sync Redis client (gotcha: a bare client can hang
    a caller forever; #995 attempt-9)."""
    from app.tasks.redis_state import get_redis_client
    return get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)


# --- #219E Item 2: alert fingerprinting + GitHub rail --------------------
# The third email/Sentry-only incident (poly creation freeze) proved two gaps:
#   1. Sentry fingerprinted the creation-stall alert by MESSAGE, which embeds the
#      staleness HOURS ("6.0h" then "11.5h") — so a single stall episode spawned
#      a new Sentry issue every reading = noise nobody could triage.
#   2. The alert lived in Sentry+email only, never reaching the GitHub board or
#      the cockpit RED tile — so it stayed invisible to the execution loop.
# Fix: fingerprint on [alert-class, provider] (stable across readings), and route
# the same event to the GitHub filing rail (#215E's play for freshness) so ONE
# deduped board issue per stall episode carries the evidence.
_WATCHDOG_ALERT_MARKER = "watchdog-alert-fingerprint"


def _capture_fingerprinted(alert_class: str, provider: str, msg: str) -> None:
    """Send a Sentry event fingerprinted on [alert_class, provider] so all
    readings of the SAME stall episode collapse into ONE issue (not one per
    hour-value in the message)."""
    try:
        # sentry-sdk 2.x: new_scope replaces the deprecated push_scope.
        with sentry_sdk.new_scope() as scope:
            scope.fingerprint = [alert_class, provider]
            scope.set_tag("alert_class", alert_class)
            scope.set_tag("alert_provider", provider)
            sentry_sdk.capture_message(msg, level="error")
    except Exception:
        # Never let telemetry break the watchdog.
        logger.critical(msg)


def _file_watchdog_issue(alert_class: str, provider: str, title: str, body: str):
    """File OR comment ONE deduped GitHub issue per [alert_class, provider].

    Mirrors the flow/calibration sentinel rail (bug_report_github). Fingerprint
    is embedded in the body so the search-based dedup finds the open issue and
    accretes evidence instead of spawning duplicates. No-ops (returns a reason)
    when GITHUB_TOKEN is unset so a token gap can never crash the watchdog."""
    fingerprint = f"{alert_class}:{provider}"
    try:
        from app.tasks.bug_report_github import (
            GITHUB_TOKEN,
            REPO,
            add_to_project_board,
            comment_on_issue,
            create_github_issue,
        )
        import httpx
    except Exception as exc:  # pragma: no cover - import guard
        return {"action": "error", "error": f"import: {exc}"[:200]}

    if not GITHUB_TOKEN:
        return {"action": "skipped_no_token", "fingerprint": fingerprint}

    marker = f"{_WATCHDOG_ALERT_MARKER}:{fingerprint}"
    body = f"{body}\n\n<!-- {marker} -->"
    # Dedup: find an open issue carrying this fingerprint marker.
    existing = None
    try:
        resp = httpx.get(
            "https://api.github.com/search/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"q": f'repo:{REPO} in:body "{marker}" state:open'},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        existing = items[0]["number"] if items else None
    except Exception as exc:
        logger.warning("watchdog dedup search failed (%s): %s", fingerprint, exc)

    if existing:
        try:
            comment_on_issue(existing, f"Watchdog re-observed this alert. {title}")
        except Exception as exc:
            logger.warning("watchdog comment failed on #%d: %s", existing, exc)
        return {"action": "commented", "issue": existing, "fingerprint": fingerprint}

    labels = ["alert-intake", "needs-agent", "area:infra", "priority:p1"]
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("watchdog issue creation failed (%s): %s", fingerprint, exc)
        return {"action": "error", "error": str(exc)[:200], "fingerprint": fingerprint}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("watchdog: add #%d to board failed (non-fatal)", number, exc_info=True)
    return {"action": "filed", "issue": number, "fingerprint": fingerprint}


def evaluate_creation_alerts(max_created_by_source, now):
    """Pure staleness decision (testable without a DB). ``max_created_by_source``
    maps source -> latest created_at (datetime or None). Returns the alert list.
    A source with no rows (None) is a fresh/unknown state, NOT a freeze — never
    alert on it (don't cry wolf)."""
    alerts = []
    for source, max_hours in CREATION_STALENESS_HOURS.items():
        max_created = max_created_by_source.get(source)
        if max_created is None:
            continue
        if max_created.tzinfo is None:
            max_created = max_created.replace(tzinfo=timezone.utc)
        age_hours = (now - max_created).total_seconds() / 3600.0
        if age_hours > max_hours:
            alerts.append(
                {
                    "source": source,
                    "age_hours": round(age_hours, 1),
                    "threshold_hours": max_hours,
                    "last_created": max_created.isoformat(),
                }
            )
    return alerts


async def _run_creation_freshness_watchdog():
    """Alert if any watched source hasn't CREATED a new market within its
    threshold. Returns a summary dict (also used by tests)."""
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    max_created_by_source = {}
    async with get_task_session() as session:
        for source in CREATION_STALENESS_HOURS:
            row = await session.execute(
                sa_text(
                    "SELECT MAX(created_at) FROM futures_markets WHERE source = :s"
                ),
                {"s": source},
            )
            max_created_by_source[source] = row.scalar()

    alerts = evaluate_creation_alerts(max_created_by_source, now)

    # Per-source ages for the admin/health surface (always populated, fresh or
    # stale) so the dashboard can show every watched source, not just the ones
    # currently alerting.
    by_source = {}
    for source, mc in max_created_by_source.items():
        if mc is None:
            by_source[source] = {"last_created": None, "age_hours": None}
            continue
        if mc.tzinfo is None:
            mc = mc.replace(tzinfo=timezone.utc)
        by_source[source] = {
            "last_created": mc.isoformat(),
            "age_hours": round((now - mc).total_seconds() / 3600.0, 1),
            "threshold_hours": CREATION_STALENESS_HOURS[source],
        }

    rc = _bounded_rc()
    filed = []
    if alerts:
        for a in alerts:
            msg = (
                f"Market CREATION stalled: {a['source']} — no new markets in "
                f"{a['age_hours']}h (threshold {a['threshold_hours']}h, last "
                f"{a['last_created']}). SIGKILL raises no exception and updates "
                f"stay fresh, so this creates-specific signal is the only catch "
                f"(#995)."
            )
            logger.critical(msg)
            # #219E Item 2(a): fingerprint on [class, provider] — NOT the message
            # (its hours-value spawned one Sentry issue per reading = noise).
            _capture_fingerprinted("creation_stall", a["source"], msg)
            # #219E Item 2(b): route to the GitHub board (no alert class may be
            # Sentry/email-only). ONE deduped issue per source per episode.
            title = (
                f"[watchdog] {a['source']} market creation stalled "
                f"(>{a['threshold_hours']}h with no new markets)"
            )
            body = (
                f"The creation-freshness watchdog detected a market CREATION "
                f"stall.\n\n"
                f"- **Source:** {a['source']}\n"
                f"- **Newest market age:** {a['age_hours']}h "
                f"(threshold {a['threshold_hours']}h)\n"
                f"- **Last created:** {a['last_created']}\n\n"
                f"This is the create-freeze class (gotcha #35 / #995 / #219E): a "
                f"poll SIGKILLs before its create/commit phase (or an upstream "
                f"API/pagination change starves the create path) while `updated_at` "
                f"stays fresh, so only a creates-specific signal catches it. "
                f"Root-cause via the freeze playbook (gotchas #38/#39, rate-limit "
                f"hang inside fetch, upstream pagination caps).\n\n"
                f"_Auto-filed by the freshness watchdog; comments accrete as the "
                f"stall persists._"
            )
            try:
                filed.append(_file_watchdog_issue("creation_stall", a["source"], title, body))
            except Exception as exc:
                logger.warning("watchdog filing failed for %s: %s", a["source"], exc)
        try:
            rc.setex(CREATION_STALE_FLAG_KEY, 7200, json.dumps(alerts))
        except Exception:
            pass
    else:
        try:
            rc.delete(CREATION_STALE_FLAG_KEY)
        except Exception:
            pass

    return {
        "stale_sources": [a["source"] for a in alerts],
        "alerts": alerts,
        "by_source": by_source,
        "filed": filed,
    }


def _run_phase_heartbeat_watchdog():
    """Alert if a poll's phase marker is present but hasn't advanced within
    PHASE_STUCK_SECONDS — a suspected event-loop block at that exact phase."""
    rc = _bounded_rc()
    now = datetime.now(timezone.utc)
    stuck = []

    for task_label, phase_key in PHASE_MARKER_KEYS.items():
        try:
            marker = rc.get(phase_key)
        except Exception:
            continue
        seen_key = _PHASE_SEEN_PREFIX + task_label
        if not marker:
            # No active phase — clear our tracking so a future run starts clean.
            try:
                rc.delete(seen_key)
            except Exception:
                pass
            continue
        marker = marker.decode() if isinstance(marker, bytes) else marker
        phase = marker.split("@", 1)[0]
        if any(phase.startswith(p) for p in _TERMINAL_PHASE_PREFIXES):
            try:
                rc.delete(seen_key)
            except Exception:
                pass
            continue

        try:
            prev_raw = rc.get(seen_key)
        except Exception:
            prev_raw = None
        prev = None
        if prev_raw:
            try:
                prev = json.loads(
                    prev_raw.decode() if isinstance(prev_raw, bytes) else prev_raw
                )
            except Exception:
                prev = None

        if prev and prev.get("marker") == marker:
            try:
                first_seen = datetime.fromisoformat(prev["first_seen"])
            except Exception:
                first_seen = now
            stuck_seconds = (now - first_seen).total_seconds()
            if stuck_seconds > PHASE_STUCK_SECONDS:
                msg = (
                    f"Suspected event-loop block: {task_label} phase "
                    f"'{marker}' has not advanced in {stuck_seconds:.0f}s "
                    f"(threshold {PHASE_STUCK_SECONDS}s) — the poll is likely "
                    f"stuck on a synchronous op at this phase (#995)."
                )
                logger.critical(msg)
                # #219E Item 2(a): fingerprint on [class, task] — the phase suffix
                # carries an elapsed-seconds value ("@174s") + the stuck_seconds in
                # the message both drift, so message-fingerprinting spawned a new
                # Sentry issue per reading. Group by the STALLED PHASE instead.
                _stuck_phase = marker.split("@", 1)[0]
                _capture_fingerprinted(
                    "phase_block", f"{task_label}:{_stuck_phase}", msg
                )
                stuck.append(
                    {
                        "task": task_label,
                        "phase": marker,
                        "stuck_seconds": round(stuck_seconds),
                    }
                )
        else:
            # New/changed marker — record first-seen wall-clock time.
            try:
                rc.setex(
                    seen_key,
                    7200,
                    json.dumps({"marker": marker, "first_seen": now.isoformat()}),
                )
            except Exception:
                pass

    return {"stuck": stuck}


async def _run_freshness_watchdog():
    """Combined entry: creation-freshness (async DB) + phase-heartbeat (Redis)."""
    creation = await _run_creation_freshness_watchdog()
    phase = _run_phase_heartbeat_watchdog()
    summary = {
        "creation": creation,
        "phase_heartbeat": phase,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist the latest result so the admin dashboard / health surface can show
    # per-source creates-freshness + any stuck phase without its own DB query.
    try:
        _bounded_rc().setex(WATCHDOG_SUMMARY_KEY, 3600, json.dumps(summary))
    except Exception:
        pass
    return summary
