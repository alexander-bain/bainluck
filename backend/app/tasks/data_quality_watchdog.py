"""
Data Quality Watchdog — automated alerting for data pipeline health.

Runs every 2 hours. Checks ingestion freshness, winner coverage, and snapshot
sparsity. When a check fails:
  1. GPT-4o-mini generates a diagnosis
  2. Email alert sent to DAILY_DIGEST_RECIPIENTS
  3. GitHub Issue created with diagnosis so /triage gets a running start

Redis dedup prevents duplicate alerts within 24h per check.
"""

import html
import logging
import os
from typing import Any

from sqlalchemy import text

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Check definitions
# ---------------------------------------------------------------------------

CHECKS: list[dict[str, Any]] = [
    # --- Ingestion freshness (P0) ---
    {
        "name": "kalshi_freshness",
        "query": (
            "SELECT COUNT(*) FROM futures_markets "
            "WHERE source = 'kalshi' AND updated_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",  # value >= threshold means pass
        "severity": "P0",
        "message": "No Kalshi markets updated in 6 hours — ingestion may be broken",
    },
    {
        # CREATE-freeze guard. kalshi_freshness above watches updated_at, which
        # stays fresh via kalshi_ws + backfill_winners even when poll_kalshi_markets
        # is SIGKILLed before committing any NEW markets — that masked a 17-day
        # creation outage (2026-06-09 → 06-26). This watches created_at so a frozen
        # ingestion fires an alert. New game tickers appear daily for in-season
        # leagues, so a 48h window comfortably clears weekend lulls.
        "name": "kalshi_ingestion",
        "query": (
            "SELECT COUNT(*) FROM futures_markets "
            "WHERE source = 'kalshi' AND created_at > NOW() - INTERVAL '48 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P0",
        "message": (
            "No NEW Kalshi markets created in 48 hours — poll_kalshi_markets may be "
            "dying before its end-commit (check for SIGKILL at the 660s time_limit)"
        ),
    },
    {
        "name": "polymarket_freshness",
        "query": (
            "SELECT COUNT(*) FROM futures_markets "
            "WHERE source = 'polymarket' AND updated_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P0",
        "message": "No Polymarket markets updated in 6 hours — ingestion may be broken",
    },
    {
        "name": "odds_api_freshness",
        "query": (
            "SELECT COUNT(*) FROM events "
            "WHERE updated_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P0",
        "message": "No events updated in 6 hours — Odds API ingestion may be broken",
    },
    # --- Winner coverage (P1) ---
    {
        "name": "kalshi_winner_coverage",
        "query": (
            "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) "
            "/ NULLIF(COUNT(*), 0), 1) "
            "FROM futures_outcomes fo JOIN futures_markets fm ON fo.market_id = fm.id "
            "WHERE fm.source = 'kalshi' AND fm.status = 'resolved'"
        ),
        "threshold": 99.0,
        "comparison": "gte",
        "severity": "P1",
        "message": "Kalshi winner coverage below 99% — backfill may be stalled",
    },
    {
        "name": "polymarket_winner_coverage",
        "query": (
            "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) "
            "/ NULLIF(COUNT(*), 0), 1) "
            "FROM futures_outcomes fo JOIN futures_markets fm ON fo.market_id = fm.id "
            "WHERE fm.source = 'polymarket' AND fm.status = 'resolved'"
        ),
        "threshold": 99.0,
        "comparison": "gte",
        "severity": "P1",
        "message": "Polymarket winner coverage below 99% — backfill may be stalled",
    },
    # --- ESPN freshness (P0) ---
    {
        "name": "espn_freshness",
        "query": (
            "SELECT COUNT(*) FROM events "
            "WHERE espn_id IS NOT NULL "
            "AND updated_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P0",
        "message": "No ESPN-linked events updated in 6 hours — live scores, win probability, and Score Differential chart not updating",
    },
    # --- StatPal freshness (P1) ---
    {
        "name": "statpal_freshness",
        "query": (
            "SELECT COUNT(*) FROM events "
            "WHERE statpal_fixture_id IS NOT NULL "
            "AND updated_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P1",
        "message": "No StatPal-linked events updated in 6 hours — livescores and play-by-play may be stalled",
    },
    # --- ScoreSnapshot freshness (P1) — core product chart data ---
    {
        "name": "score_snapshot_freshness",
        "query": (
            "SELECT COUNT(*) FROM score_snapshots "
            "WHERE captured_at > NOW() - INTERVAL '12 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P1",
        "message": "No ScoreSnapshots captured in 12 hours — Score Differential charts will be empty for recent games",
    },
    # --- DataGolf freshness (P1) ---
    {
        "name": "datagolf_freshness",
        "query": (
            "SELECT COUNT(*) FROM futures_markets "
            "WHERE source = 'datagolf' AND updated_at > NOW() - INTERVAL '12 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P1",
        "message": "No DataGolf markets updated in 12 hours — golf leaderboards and probabilities may be stale",
    },
    # --- MLB win probability freshness (P1) ---
    {
        "name": "mlb_win_prob_freshness",
        "query": (
            "SELECT COUNT(*) FROM win_prob_snapshots "
            "WHERE source = 'mlb' AND captured_at > NOW() - INTERVAL '12 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P1",
        "message": "No MLB win probability snapshots in 12 hours — baseball live charts not updating",
    },
    # --- Snapshot sparsity (P1) ---
    {
        "name": "odds_api_sparsity",
        "query": (
            "SELECT COUNT(*) FROM events e "
            "WHERE e.status IN ('live', 'scheduled') "
            "AND e.commence_time < NOW() + INTERVAL '1 hour' "
            "AND (SELECT COUNT(*) FROM odds_snapshots os "
            "     WHERE os.event_id = e.id "
            "     AND os.captured_at > NOW() - INTERVAL '48 hours') < 10"
        ),
        "threshold": 0,
        "comparison": "lte",  # value <= threshold means pass (0 sparse events = good)
        "severity": "P1",
        "message": "Active Tier 1 events have sparse snapshot coverage (<10 in 48h)",
    },
]


def passes_threshold(value: Any, check: dict[str, Any]) -> bool:
    """Return True if the check value meets the threshold (i.e. passes)."""
    if value is None:
        # NULL from DB means no data — treat as a pass for coverage checks
        # (0 resolved markets = nothing to cover) but fail for freshness
        if check["comparison"] == "gte" and check["threshold"] >= 1:
            return False
        return True

    v = float(value)
    comparison = check.get("comparison", "gte")
    threshold = float(check["threshold"])

    if comparison == "gte":
        return v >= threshold
    elif comparison == "lte":
        return v <= threshold
    elif comparison == "eq":
        return v == threshold
    else:
        return v >= threshold


# ---------------------------------------------------------------------------
# LLM diagnosis
# ---------------------------------------------------------------------------

_DIAGNOSIS_PROMPT = """\
You are a data pipeline engineer for Bain Luck, a prediction market platform.

A data quality check failed:
- Check: {name}
- Current value: {value}
- Threshold: {threshold}
- Severity: {severity}

Based on the check name and value, provide:
1. Most likely root cause (1-2 sentences)
2. Investigation steps (numbered list, 3-5 steps with specific curl commands or SQL queries)
3. A Claude Code prompt that an agent can paste to investigate and fix the issue

Be specific — reference actual API endpoints like /api/admin/celery-debug, \
/api/admin/backfill-winners/status, etc.\
"""


def _deterministic_fallback(check: dict[str, Any], value: Any) -> str:
    """Generate a deterministic diagnosis when OpenAI is unavailable."""
    name = check["name"]
    severity = check["severity"]

    if "freshness" in name:
        source = name.replace("_freshness", "").replace("odds_api", "Odds API")
        return (
            f"**Root cause:** {source} ingestion has not updated any records in 6+ hours. "
            f"The polling task may have failed, the upstream API may be down, or Celery "
            f"workers may be unhealthy.\n\n"
            f"**Investigation steps:**\n"
            f"1. Check Celery queue health: `curl -s \"https://api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN\"`\n"
            f"2. Check Heroku worker logs: `heroku logs --tail -a bainluck --dyno worker`\n"
            f"3. Check Sentry for recent task errors\n"
            f"4. Manually trigger the polling task via admin endpoint\n\n"
            f"**Claude Code prompt:** Investigate why {source} ingestion stopped. "
            f"Check Celery task logs, Sentry errors, and upstream API status. "
            f"The watchdog detected 0 updates in 6 hours ({severity})."
        )
    elif "winner_coverage" in name:
        source = name.replace("_winner_coverage", "")
        return (
            f"**Root cause:** {source} winner resolution coverage dropped below 99%. "
            f"The backfill_winners task may be failing or the resolution source may "
            f"have changed its API.\n\n"
            f"**Investigation steps:**\n"
            f"1. Check backfill status: `curl -s \"https://api.bainluck.com/api/admin/backfill-winners/status?secret=$ADMIN_TOKEN\"`\n"
            f"2. Check Celery task history for backfill_winners failures\n"
            f"3. Verify {source} API is returning resolution data\n"
            f"4. Run manual backfill: `POST /api/admin/backfill-winners/probability-only`\n\n"
            f"**Claude Code prompt:** Investigate why {source} winner coverage dropped. "
            f"Check backfill_winners task logs and resolution data sources."
        )
    elif "sparsity" in name:
        return (
            f"**Root cause:** Some active events near start time have fewer than 10 "
            f"odds snapshots in 48 hours. The odds polling task may be throttled, "
            f"or quota conservation mode may be too aggressive.\n\n"
            f"**Investigation steps:**\n"
            f"1. Check quota status: `curl -s \"https://api.bainluck.com/api/admin/quota?secret=$ADMIN_TOKEN\"`\n"
            f"2. Check Celery queue health: `curl -s \"https://api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN\"`\n"
            f"3. Look for LIVE_ONLY or FULL_STOP mode in Redis state\n"
            f"4. Check sparsity details: `curl -s \"https://api.bainluck.com/api/admin/snapshot-sparsity?secret=$ADMIN_TOKEN\"`\n\n"
            f"**Claude Code prompt:** Investigate sparse snapshot coverage on active events. "
            f"Check Odds API quota state, polling mode, and whether the circuit breaker is engaged."
        )
    else:
        return (
            f"**Root cause:** Data quality check '{name}' failed with value {value} "
            f"(threshold: {check['threshold']}).\n\n"
            f"**Investigation steps:**\n"
            f"1. Check Celery queue health\n"
            f"2. Review Sentry for related errors\n"
            f"3. Examine recent task run history\n\n"
            f"**Claude Code prompt:** Investigate data quality check '{name}' failure."
        )


def get_llm_diagnosis(check: dict[str, Any], value: Any) -> str:
    """Get an LLM-generated diagnosis, falling back to deterministic template."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.info("OPENAI_API_KEY not set, using deterministic diagnosis")
        return _deterministic_fallback(check, value)

    try:
        import openai

        client = openai.OpenAI(api_key=api_key)
        prompt = _DIAGNOSIS_PROMPT.format(
            name=check["name"],
            value=value,
            threshold=check["threshold"],
            severity=check["severity"],
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data pipeline engineer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("OpenAI diagnosis failed, using fallback: %s", exc)
        return _deterministic_fallback(check, value)


# ---------------------------------------------------------------------------
# Email alert
# ---------------------------------------------------------------------------

def _build_alert_email_html(
    check: dict[str, Any],
    value: Any,
    diagnosis: str,
) -> str:
    """Build an HTML email body for a data quality alert."""
    safe_name = html.escape(check["name"])
    safe_message = html.escape(check["message"])
    safe_severity = html.escape(check["severity"])
    safe_diagnosis = html.escape(diagnosis).replace("\n", "<br>")

    return f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a1a1a;">
    <div style="background: {'#dc2626' if check['severity'] == 'P0' else '#f59e0b'}; color: white; padding: 12px 16px; border-radius: 8px 8px 0 0;">
        <strong>{safe_severity} Alert:</strong> {safe_name}
    </div>
    <div style="border: 1px solid #e5e7eb; border-top: none; padding: 16px; border-radius: 0 0 8px 8px;">
        <p style="font-size: 15px; margin: 0 0 12px;"><strong>What happened:</strong> {safe_message}</p>
        <table style="width: 100%; border-collapse: collapse; margin: 12px 0;">
            <tr><td style="padding: 6px 0; color: #6b7280;">Current value</td><td style="padding: 6px 0; font-weight: 600;">{value}</td></tr>
            <tr><td style="padding: 6px 0; color: #6b7280;">Threshold</td><td style="padding: 6px 0;">{check['threshold']}</td></tr>
            <tr><td style="padding: 6px 0; color: #6b7280;">Severity</td><td style="padding: 6px 0;">{safe_severity}</td></tr>
        </table>
        <div style="background: #f9fafb; padding: 12px; border-radius: 6px; margin-top: 12px;">
            <strong>Diagnosis:</strong><br>{safe_diagnosis}
        </div>
        <p style="font-size: 13px; color: #6b7280; margin-top: 16px;">
            <a href="https://bainluck.com/admin" style="color: #2563eb;">Admin Dashboard</a> |
            <a href="https://api.bainluck.com/docs" style="color: #2563eb;">API Docs</a>
        </p>
    </div>
</div>"""


def send_alert_email(check: dict[str, Any], value: Any, diagnosis: str) -> bool:
    """Send an alert email via Gmail OAuth (reuses bug_notifications pattern)."""
    from app.tasks.bug_notifications import (
        GMAIL_CLIENT_ID,
        GMAIL_CLIENT_SECRET,
        GMAIL_REFRESH_TOKEN,
        _send_gmail,
    )

    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN]):
        logger.warning("Gmail OAuth not configured, skipping alert email")
        return False

    recipients_str = os.environ.get("DAILY_DIGEST_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]
    if not recipients:
        logger.warning("DAILY_DIGEST_RECIPIENTS not set, skipping alert email")
        return False

    subject = f"[Bain Luck Alert] {check['severity']}: {check['message']}"
    body_html = _build_alert_email_html(check, value, diagnosis)

    sent_any = False
    for email in recipients:
        try:
            if _send_gmail(email, subject, body_html):
                sent_any = True
        except Exception as exc:
            logger.error("Failed to send alert email to %s: %s", email, exc)

    return sent_any


# ---------------------------------------------------------------------------
# GitHub Issue creation
# ---------------------------------------------------------------------------

def create_alert_issue(
    check: dict[str, Any],
    value: Any,
    diagnosis: str,
) -> int | None:
    """Create a GitHub Issue for the failed check, returns issue number or None."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        create_github_issue,
        add_to_project_board,
    )

    if not GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN not set, skipping issue creation")
        return None

    severity = check["severity"].lower()
    title = f"[Data Quality] {check['name']}: {check['message']}"
    # Truncate title to 256 chars (GitHub limit)
    if len(title) > 256:
        title = title[:253] + "..."

    body = (
        f"## Data Quality Alert\n\n"
        f"**Severity:** {check['severity']}  \n"
        f"**Check:** `{check['name']}`  \n"
        f"**Current value:** `{value}`  \n"
        f"**Threshold:** `{check['threshold']}` ({check.get('comparison', 'gte')})  \n\n"
        f"### What happened\n\n"
        f"{check['message']}\n\n"
        f"### Diagnosis\n\n"
        f"{diagnosis}\n\n"
        f"---\n"
        f"*Auto-created by data quality watchdog. "
        f"[Admin Dashboard](https://bainluck.com/admin)*"
    )

    labels = [f"priority:{severity}", "alert-intake", "needs-agent"]

    try:
        issue_number, issue_node_id = create_github_issue(title, body, labels)
        logger.info(
            "Created GitHub issue #%d for watchdog check '%s'",
            issue_number,
            check["name"],
        )
        try:
            add_to_project_board(issue_node_id)
        except Exception:
            logger.warning(
                "Failed to add issue #%d to project board (non-fatal)",
                issue_number,
                exc_info=True,
            )
        return issue_number
    except Exception as exc:
        logger.error("Failed to create GitHub issue for '%s': %s", check["name"], exc)
        return None


# ---------------------------------------------------------------------------
# Redis dedup
# ---------------------------------------------------------------------------

def _check_redis_dedup(check_name: str) -> bool:
    """Return True if this check has already alerted in the last 24h."""
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        key = f"watchdog:alert:{check_name}"
        return r.get(key) is not None
    except Exception as exc:
        logger.warning("Redis dedup check failed (allowing alert): %s", exc)
        return False


def _set_redis_dedup(check_name: str, issue_number: int | None = None) -> None:
    """Mark this check as alerted for 24h."""
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        key = f"watchdog:alert:{check_name}"
        r.setex(key, 86400, str(issue_number or "alerted"))
    except Exception as exc:
        logger.warning("Redis dedup set failed: %s", exc)


# ---------------------------------------------------------------------------
# Main task
# ---------------------------------------------------------------------------

async def _run_data_quality_watchdog() -> dict[str, Any]:
    """Run all data quality checks and fire alerts for failures."""
    stats: dict[str, Any] = {
        "checks_run": 0,
        "checks_passed": 0,
        "alerts_fired": 0,
        "alerts_deduped": 0,
        "errors": [],
        "results": {},
    }

    async with get_task_session() as session:
        for check in CHECKS:
            check_name = check["name"]
            try:
                result = await session.execute(text(check["query"]))
                value = result.scalar()
                stats["checks_run"] += 1
                stats["results"][check_name] = {
                    "value": float(value) if value is not None else None,
                    "threshold": check["threshold"],
                    "passed": passes_threshold(value, check),
                }

                if passes_threshold(value, check):
                    stats["checks_passed"] += 1
                    continue

                # Check failed — check dedup before firing
                if _check_redis_dedup(check_name):
                    stats["alerts_deduped"] += 1
                    stats["results"][check_name]["deduped"] = True
                    logger.info(
                        "Watchdog check '%s' failed but already alerted in 24h",
                        check_name,
                    )
                    continue

                # Fire alert
                logger.warning(
                    "Watchdog check '%s' FAILED: value=%s threshold=%s severity=%s",
                    check_name,
                    value,
                    check["threshold"],
                    check["severity"],
                )
                diagnosis = get_llm_diagnosis(check, value)

                # Email
                try:
                    send_alert_email(check, value, diagnosis)
                except Exception as exc:
                    logger.error("Alert email failed for '%s': %s", check_name, exc)

                # GitHub Issue
                issue_number = None
                try:
                    issue_number = create_alert_issue(check, value, diagnosis)
                except Exception as exc:
                    logger.error("GitHub issue creation failed for '%s': %s", check_name, exc)

                # Set dedup key
                _set_redis_dedup(check_name, issue_number)

                stats["alerts_fired"] += 1

            except Exception as exc:
                logger.error("Watchdog check '%s' errored: %s", check_name, exc)
                stats["errors"].append({"check": check_name, "error": str(exc)[:200]})
                # Continue to next check — don't let one failure block others

    # --- Link rate change detection ---
    # Snapshot per-sport/league link rates and alert on significant changes.
    try:
        link_rates = {}
        for source in ("kalshi", "polymarket"):
            lr_result = await session.execute(text(f"""
                SELECT llm_sport_category,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE event_id IS NOT NULL) AS linked
                FROM futures_markets
                WHERE source = '{source}'
                  AND status = 'open'
                  AND llm_sport_category IS NOT NULL
                  AND (category IS NULL OR category NOT IN ('championship','award','season_win_total','player_futures','division','conference'))
                GROUP BY llm_sport_category
                HAVING COUNT(*) >= 5
            """))
            for row in lr_result.all():
                sport, total, linked = row[0], row[1], row[2]
                pct = round(100.0 * linked / max(total, 1), 1)
                link_rates[f"{source}:{sport}"] = pct

        from app.tasks.redis_state import record_link_rate_snapshot, get_link_rate_changes
        record_link_rate_snapshot(link_rates)

        changes = get_link_rate_changes(threshold_pp=5.0)
        drops = [c for c in changes if c.get("delta") is not None and c["delta"] < -5]
        if drops:
            for drop in drops:
                alert_msg = (
                    f"Link rate drop: {drop['key']} went from "
                    f"{drop['yesterday']}% to {drop['today']}% "
                    f"({drop['delta']:+.1f}pp)"
                )
                logger.warning(alert_msg)
                stats["alerts_fired"] += 1
            stats["link_rate_drops"] = drops

        stats["link_rate_snapshot"] = link_rates
    except Exception as exc:
        logger.warning("Link rate snapshot failed: %s", exc)

    # --- Event-level source coverage change detection ---
    # "What % of events have data from each source?" — the metric that
    # matches the user experience on event detail pages.
    try:
        from app.tasks.redis_state import record_source_coverage_snapshot, get_source_coverage_changes

        # Tier 1 sports only — these are the ones users actually look at
        _TIER1 = ("basketball_nba", "icehockey_nhl", "baseball_mlb",
                  "americanfootball_nfl", "basketball_wnba", "basketball_ncaab")
        _SOURCES = ("betting", "espn", "kalshi", "polymarket", "stat_model", "mlb")

        coverage = {}
        for sport in _TIER1:
            cov_result = await session.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'betting') AS has_betting,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'espn') AS has_espn,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'kalshi') AS has_kalshi,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'polymarket') AS has_polymarket,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'stat_model') AS has_stat_model,
                    COUNT(*) FILTER (WHERE win_probability_sources ? 'mlb') AS has_mlb
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                WHERE s.key = :sport
                  AND e.status IN ('scheduled', 'live', 'completed', 'closed')
                  AND e.commence_time > NOW() - INTERVAL '7 days'
            """), {"sport": sport})
            row = cov_result.first()
            if row and row[0] > 0:
                total = row[0]
                for i, src in enumerate(_SOURCES):
                    pct = round(100.0 * row[i + 1] / total, 1)
                    coverage[f"{sport}:{src}"] = pct

        record_source_coverage_snapshot(coverage)

        cov_changes = get_source_coverage_changes(threshold_pp=5.0)
        cov_drops = [c for c in cov_changes if c.get("delta") is not None and c["delta"] < -5]
        if cov_drops:
            for drop in cov_drops:
                alert_msg = (
                    f"Source coverage drop: {drop['key']} went from "
                    f"{drop['yesterday']}% to {drop['today']}% "
                    f"({drop['delta']:+.1f}pp)"
                )
                logger.warning(alert_msg)
                stats["alerts_fired"] += 1
            stats["source_coverage_drops"] = cov_drops

        stats["source_coverage_snapshot"] = coverage
    except Exception as exc:
        logger.warning("Source coverage snapshot failed: %s", exc)

    logger.info(
        "Watchdog complete: %d/%d passed, %d alerts fired, %d deduped, %d errors",
        stats["checks_passed"],
        stats["checks_run"],
        stats["alerts_fired"],
        stats["alerts_deduped"],
        len(stats["errors"]),
    )
    return stats
