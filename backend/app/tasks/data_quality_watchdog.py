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
import json
import logging
import os
from datetime import datetime, timezone
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
        # #1000/#1001: the events table has NO updated_at column (schema drift —
        # see events-has-no-sport_key class). The real Odds API freshness signal
        # is fresh odds_snapshots, which is what ingestion actually writes.
        "query": (
            "SELECT COUNT(*) FROM odds_snapshots "
            "WHERE captured_at > NOW() - INTERVAL '6 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P0",
        "message": "No odds snapshots in 6 hours — Odds API ingestion may be broken",
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
        # #1000/#1001: events has no updated_at. ESPN freshness is measured by
        # its win-probability snapshots (source='espn').
        #
        # #215E (2026-07-20): the old unconditional "0 espn snapshots in 12h"
        # form cried wolf EVERY day. ESPN win-prob is captured ONLY for live
        # ESPN-matched games (_sync_espn_live_events returns 'no_live_games' and
        # writes nothing when the slate is empty), so any 12h window with no live
        # games — every overnight/daytime gap, and ALL of an off-season — trips a
        # P0 that only means "no games were on." It fired a false P0 today (#1149)
        # while capture was fully healthy (realtime worker alive, fresh odds on the
        # same queue). Now LIVE-GATED: it fails ONLY when a coverable game (any
        # ESPN-matched event — espn_id NOT NULL — that is live or completed within
        # the window) existed AND zero espn snapshots landed. Season-agnostic:
        # espn_id, not a hardcoded sport list (the live ESPN-winprob sports are
        # baseball_mlb + basketball_wnba in July, NBA/NFL/NHL in-season — probed
        # 2026-07-20). Returns 1 (real gap) / 0 (nothing to capture, or healthy).
        "query": (
            "SELECT CASE WHEN EXISTS ("
            "  SELECT 1 FROM events e"
            "  WHERE e.espn_id IS NOT NULL"
            "    AND e.commence_time <= NOW()"
            "    AND (e.status = 'live'"
            "         OR (e.status IN ('completed', 'closed')"
            "             AND e.commence_time > NOW() - INTERVAL '12 hours'))"
            ") AND (SELECT COUNT(*) FROM win_prob_snapshots"
            "       WHERE source = 'espn'"
            "       AND captured_at > NOW() - INTERVAL '12 hours') = 0"
            " THEN 1 ELSE 0 END"
        ),
        "threshold": 0,
        "comparison": "lte",
        "severity": "P0",
        "message": "A live/recent ESPN-matched game produced NO ESPN win-probability snapshots in 12 hours — live scores, win probability, and Score Differential chart not updating (live-gated: fires only when there were games to capture)",
    },
    # --- StatPal freshness (P1) ---
    {
        "name": "statpal_freshness",
        # #1000/#1001: events has no updated_at. StatPal drives live scores for
        # its linked fixtures, so its freshness is measured by recent
        # score_snapshots on StatPal-linked events. 24h window (soccer is near-
        # daily); P1 so a rare quiet window doesn't page.
        "query": (
            "SELECT COUNT(*) FROM score_snapshots ss "
            "JOIN events e ON e.id = ss.event_id "
            "WHERE e.statpal_fixture_id IS NOT NULL "
            "AND ss.captured_at > NOW() - INTERVAL '24 hours'"
        ),
        "threshold": 1,
        "comparison": "gte",
        "severity": "P1",
        "message": "No score snapshots for StatPal-linked events in 24 hours — livescores and play-by-play may be stalled",
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
        # #215E (2026-07-20): same crying-wolf class as espn_freshness. MLB win
        # prob (source='mlb', MLB Stats API) is captured only during live MLB
        # games, so the daily daytime gap between last night's finale and tonight's
        # first pitch (e.g. 23:33Z 7/19 → 22:40Z 7/20, a ~23h no-game window) trips
        # the old "0 in 12h" form as a false P1 (#1150). Now LIVE-GATED: fails only
        # when a baseball_mlb game was live or completed within the window AND zero
        # mlb snapshots landed. Returns 1 (real gap) / 0 (no games / healthy).
        "query": (
            "SELECT CASE WHEN EXISTS ("
            "  SELECT 1 FROM events e JOIN sports s ON s.id = e.sport_id"
            "  WHERE s.key = 'baseball_mlb'"
            "    AND e.commence_time <= NOW()"
            "    AND (e.status = 'live'"
            "         OR (e.status IN ('completed', 'closed')"
            "             AND e.commence_time > NOW() - INTERVAL '12 hours'))"
            ") AND (SELECT COUNT(*) FROM win_prob_snapshots"
            "       WHERE source = 'mlb'"
            "       AND captured_at > NOW() - INTERVAL '12 hours') = 0"
            " THEN 1 ELSE 0 END"
        ),
        "threshold": 0,
        "comparison": "lte",
        "severity": "P1",
        "message": "A live/recent MLB game produced NO win-probability snapshots in 12 hours — baseball live charts not updating (live-gated: fires only when there were games to capture)",
    },
    # --- Snapshot sparsity (P1) ---
    {
        "name": "odds_api_sparsity",
        # #215E (2026-07-20): the message says "Tier 1" but the old query counted
        # EVERY sport, so it paged on upstream gaps the Odds API simply doesn't
        # cover (esports/NPB/off-brand) and on stale-status events months in the
        # past — not our bug (#1151 was 1 esports + 1 pre-game MLB). Now scoped to
        # the actual Tier-1 leagues (CLAUDE.md SPORT_POLLING_TIERS) and to a
        # recently-active window (started within 12h or starting within 1h) so a
        # genuinely under-covered Tier-1 game is the only thing that fires.
        "query": (
            "SELECT COUNT(*) FROM events e "
            "JOIN sports s ON s.id = e.sport_id "
            "WHERE e.status IN ('live', 'scheduled') "
            "AND s.key IN ('baseball_mlb', 'basketball_nba', "
            "              'americanfootball_nfl', 'icehockey_nhl', 'basketball_ncaab') "
            "AND e.commence_time < NOW() + INTERVAL '1 hour' "
            "AND e.commence_time > NOW() - INTERVAL '12 hours' "
            "AND (SELECT COUNT(*) FROM odds_snapshots os "
            "     WHERE os.event_id = e.id "
            "     AND os.captured_at > NOW() - INTERVAL '48 hours') < 10"
        ),
        "threshold": 0,
        "comparison": "lte",  # value <= threshold means pass (0 sparse events = good)
        "severity": "P1",
        "message": "Active Tier 1 events have sparse snapshot coverage (<10 in 48h)",
    },
    # --- ESPN capture gap (P1) — granular per-live-game detector (#207 Item 2) ---
    # espn_freshness (above) catches a GLOBAL ESPN outage; this catches a gap on a
    # SPECIFIC live game while other games still flow. Recoverable after the fact
    # via backfill_espn_win_prob.
    #
    # #1132 (#215E carryover): baseball was excluded on the claim "ESPN's baseball
    # summary returns an empty winprobability array" — but prod shows ESPN DOES
    # capture MLB win-prob (1,538 espn baseball_mlb rows in win_prob_snapshots),
    # so the detector was blind to live-MLB ESPN gaps (a false NEGATIVE). Baseball
    # is now included. To avoid the false-POSITIVE class (flagging a live game
    # ESPN simply never covers — MLB ESPN coverage is not universal), the check is
    # gated on `EXISTS(any prior espn snapshot for this event)`: it fires only when
    # ESPN WAS actively capturing this game and then went silent for 15 min — a
    # real mid-game stop. This gate also strictly tightens the other sports.
    # status='live' self-gates against off-season false alarms (no live games =>
    # count 0 => pass).
    {
        "name": "espn_capture_gap",
        "query": (
            "SELECT COUNT(*) FROM events e "
            "JOIN sports s ON s.id = e.sport_id "
            "WHERE e.status = 'live' "
            "AND e.espn_id IS NOT NULL "
            "AND (s.key LIKE 'basketball%' OR s.key LIKE 'americanfootball%' "
            "     OR s.key LIKE 'icehockey%' OR s.key LIKE 'baseball%') "
            # ESPN was actively covering this game (>=1 espn snapshot ever) ...
            "AND EXISTS (SELECT 1 FROM win_prob_snapshots wp "
            "     WHERE wp.event_id = e.id AND wp.source = 'espn') "
            # ... and has now gone silent for 15 min (a real mid-game stop).
            "AND (SELECT COUNT(*) FROM win_prob_snapshots wp "
            "     WHERE wp.event_id = e.id AND wp.source = 'espn' "
            "     AND wp.captured_at > NOW() - INTERVAL '15 minutes') = 0"
        ),
        "threshold": 0,
        "comparison": "lte",
        "severity": "P1",
        "message": "A live NBA/NFL/NHL/MLB game ESPN was covering has no ESPN win-probability snapshot in 15 min — live capture gap; its chart will lose the curve (recoverable via backfill_espn_win_prob)",
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
# Diagnosis
#
# #215E (2026-07-20): the diagnosis was GPT-4o-mini given only the check name +
# value with NO real schema — so it hallucinated fake tables (`espn_data`),
# fake endpoints (`/api/admin/logs?service=espn`), placeholder URLs
# (`http://<your-platform-url>/...`), and the wrong ESPN API. That garbage
# shipped verbatim into both the alert email AND the GitHub issue body (#1149),
# actively misleading whoever picked up the alert. The LLM added zero signal
# over a deterministic template and one real failure mode (hallucination), so
# the LLM call is REMOVED. Diagnoses are now deterministic, per-check, and cite
# only REAL admin endpoints/tables/runbooks (all verified 2026-07-20).
# ---------------------------------------------------------------------------

# Real, verified admin surface — safe to cite in alert bodies.
_CELERY_DEBUG = "curl -s -H \"Authorization: Bearer $ADMIN_TOKEN\" \"$BAINLUCK_API/api/admin/celery-debug\""
_QUOTA = "curl -s -H \"Authorization: Bearer $ADMIN_TOKEN\" \"$BAINLUCK_API/api/admin/dashboard\"  # quota block"
_LINK_RATE = "curl -s -H \"Authorization: Bearer $ADMIN_TOKEN\" \"$BAINLUCK_API/api/admin/prediction-markets/link-rate\""


def _dbq(sql: str) -> str:
    """Render a real /api/admin/db-query POST for the given read-only SQL."""
    return (
        "curl -s -H \"Authorization: Bearer $ADMIN_TOKEN\" -H \"Content-Type: application/json\" "
        f"-X POST \"$BAINLUCK_API/api/admin/db-query\" -d '{{\"sql\":\"{sql}\"}}'"
    )


def _deterministic_fallback(check: dict[str, Any], value: Any) -> str:
    """Generate a deterministic, real-endpoint diagnosis for a failed check.

    (Named `_deterministic_fallback` for back-compat; it is now the ONLY path.)
    Cites only verified admin endpoints/tables — never an LLM guess.
    """
    name = check["name"]
    severity = check["severity"]

    # ESPN / MLB win-prob freshness are LIVE-GATED (#215E): they fire only when a
    # coverable game existed but produced no snapshots — so this is a REAL capture
    # gap, not an empty slate. Point the responder at the realtime worker + the
    # specific polling task rather than "the slate is quiet."
    if name in ("espn_freshness", "mlb_win_prob_freshness"):
        src = "espn" if name.startswith("espn") else "mlb"
        task = "sync_espn_live_events" if src == "espn" else "sync_mlb_win_probability"
        cadence = "60s" if src == "espn" else "120s"
        upstream = "ESPN" if src == "espn" else "MLB Stats API"
        coverable = "ESPN-matched" if src == "espn" else "MLB"
        gap_sql = _dbq(
            "SELECT source, MAX(captured_at) FROM win_prob_snapshots "
            f"WHERE source='{src}' GROUP BY source"
        )
        odds_sql = _dbq(
            "SELECT COUNT(*), MAX(captured_at) FROM odds_snapshots "
            "WHERE captured_at > NOW() - INTERVAL '1 hour'"
        )
        return (
            f"**Root cause:** This check is LIVE-GATED — it fired because a live/recent "
            f"{coverable} game existed in the last 12h but ZERO `{src}` rows landed in "
            f"`win_prob_snapshots`. That is a real capture gap (not an empty slate). "
            f"Likely: the `{task}` task ({cadence}, realtime queue) is failing/stuck, the "
            f"realtime worker is down, or the upstream ({upstream}) changed/errored. "
            f"Recoverable after the fact via backfill.\n\n"
            f"**Investigation steps:**\n"
            f"1. Realtime worker + queue depth (if odds are also stale, the whole realtime "
            f"worker is down): `{_CELERY_DEBUG}`\n"
            f"2. Confirm the gap and which games lacked capture:\n   `{gap_sql}`\n"
            f"3. Cross-check odds capture on the same realtime queue is alive:\n   `{odds_sql}`\n"
            f"4. Check Sentry for `{task}` errors; check the Heroku worker-realtime dyno.\n\n"
            f"**Claude Code prompt:** A live-gated {src} win-prob freshness alert ({severity}) "
            f"fired — a coverable game produced no snapshots. Verify the realtime worker is up "
            f"(fresh odds_snapshots => worker fine => suspect `{task}` specifically), check "
            f"Sentry for that task, then backfill the gap window."
        )

    if "freshness" in name:
        # Derive the real window from the query rather than hardcoding "6+ hours".
        q = check.get("query", "")
        window = "the configured window"
        for hrs in ("48 hours", "24 hours", "12 hours", "6 hours"):
            if hrs in q:
                window = hrs
                break
        source = name.replace("_freshness", "").replace("odds_api", "Odds API")
        confirm_sql = _dbq(
            "SELECT COUNT(*), MAX(updated_at) FROM futures_markets WHERE source = ..."
        )
        return (
            f"**Root cause:** {source} ingestion wrote no rows in {window}. The polling "
            f"task may be failing, the upstream API may be down, or the Celery worker may "
            f"be unhealthy (note gotchas #38/#39 — GIL/Redis hangs can SIGKILL a poll "
            f"before commit).\n\n"
            f"**Investigation steps:**\n"
            f"1. Celery queue/worker health: `{_CELERY_DEBUG}`\n"
            f"2. Confirm the freshness gap directly:\n   `{confirm_sql}`\n"
            f"3. Check Sentry for recent task errors; check the relevant Heroku worker dyno.\n"
            f"4. Manually trigger the polling task via its admin endpoint if the worker is up.\n\n"
            f"**Claude Code prompt:** Investigate why {source} ingestion stopped ({severity}); "
            f"the watchdog saw 0 updates in {window}. Check Celery health, Sentry, upstream API."
        )
    elif "winner_coverage" in name:
        source = name.replace("_winner_coverage", "")
        backfill_status = (
            "curl -s -H \"Authorization: Bearer $ADMIN_TOKEN\" "
            "\"$BAINLUCK_API/api/admin/backfill-winners/status\""
        )
        gap_sql = _dbq(
            "SELECT ROUND(100.0*COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL)"
            "/NULLIF(COUNT(*),0),1) FROM futures_outcomes fo "
            "JOIN futures_markets fm ON fo.market_id=fm.id "
            f"WHERE fm.source='{source}' AND fm.status='resolved'"
        )
        return (
            f"**Root cause:** {source} winner resolution coverage dropped below 99%. "
            f"The backfill_winners task may be failing or the resolution source may "
            f"have changed its API.\n\n"
            f"**Investigation steps:**\n"
            f"1. Backfill status: `{backfill_status}`\n"
            f"2. Celery task health / recent failures: `{_CELERY_DEBUG}`\n"
            f"3. Verify {source} API is returning resolution data.\n"
            f"4. Confirm the gap: `{gap_sql}`\n\n"
            f"**Claude Code prompt:** Investigate why {source} winner coverage dropped "
            f"({severity}). Check backfill_winners logs and resolution data sources."
        )
    elif "sparsity" in name:
        sparse_sql = _dbq(
            "SELECT e.id, s.key, e.status, e.commence_time, "
            "(SELECT COUNT(*) FROM odds_snapshots os WHERE os.event_id=e.id "
            "AND os.captured_at > NOW() - INTERVAL '48 hours') AS n "
            "FROM events e JOIN sports s ON s.id=e.sport_id "
            "WHERE e.status IN ('live','scheduled') "
            "AND e.commence_time BETWEEN NOW()-INTERVAL '12 hours' "
            "AND NOW()+INTERVAL '1 hour' ORDER BY n"
        )
        return (
            f"**Root cause:** A Tier-1 event active in the last 12h has <10 odds snapshots "
            f"in 48h. Either odds polling is throttled (quota LIVE_ONLY/FULL_STOP), the "
            f"realtime worker is degraded, or the event is unlinked/duplicated so its "
            f"snapshots landed on a sibling event (distinguish our bug from an upstream gap "
            f"— esports/NPB/off-brand are excluded by design).\n\n"
            f"**Investigation steps:**\n"
            f"1. Quota / circuit-breaker mode: `{_QUOTA}`\n"
            f"2. Realtime queue health: `{_CELERY_DEBUG}`\n"
            f"3. Identify the sparse events + snapshot counts:\n   `{sparse_sql}`\n"
            f"4. If a Tier-1 game has 0 lines, check it isn't a duplicate/unlinked event: `{_LINK_RATE}`\n\n"
            f"**Claude Code prompt:** Investigate sparse odds coverage on an active Tier-1 event "
            f"({severity}). Check quota/circuit-breaker, realtime worker, and event linkage."
        )
    else:
        return (
            f"**Root cause:** Data quality check '{name}' failed with value {value} "
            f"(threshold: {check.get('threshold')}, {check.get('comparison', 'gte')}).\n\n"
            f"**Investigation steps:**\n"
            f"1. Celery queue/worker health: `{_CELERY_DEBUG}`\n"
            f"2. Review Sentry for related errors.\n"
            f"3. Re-run the check's query via `$BAINLUCK_API/api/admin/db-query` to confirm.\n\n"
            f"**Claude Code prompt:** Investigate data quality check '{name}' failure ({severity})."
        )


def get_llm_diagnosis(check: dict[str, Any], value: Any) -> str:
    """Return a deterministic, real-endpoint diagnosis.

    Kept for back-compat; the LLM path was removed in #215E (it hallucinated fake
    schema/URLs into live alerts — see the module comment above).
    """
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
                    "severity": check["severity"],
                    "message": check["message"],
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
                if issue_number:
                    stats["results"][check_name]["issue"] = issue_number

                stats["alerts_fired"] += 1

            except Exception as exc:
                logger.error("Watchdog check '%s' errored: %s", check_name, exc)
                stats["errors"].append({"check": check_name, "error": str(exc)[:200]})
                # #1001: a failed statement aborts the asyncpg transaction, so
                # EVERY subsequent check (and the post-loop link-rate/coverage
                # queries) then fail with InFailedSQLTransactionError — the
                # cascade that produced ~2,585 Sentry events from a single bad
                # check. Roll back so the next check runs in a clean transaction.
                try:
                    await session.rollback()
                except Exception:
                    pass

    # #1001: the watchdog must not fail SILENTLY. If any check raised an
    # exception (not merely failed a threshold), the monitor's "all clear" is
    # unreliable — surface it as a deduped P1 alert so a broken monitor is
    # visible instead of only landing in Sentry.
    if stats["errors"] and not _check_redis_dedup("watchdog_self_error"):
        err_names = ", ".join(e["check"] for e in stats["errors"])
        self_check = {
            "name": "watchdog_self_error",
            "severity": "P1",
            "threshold": 0,
            "comparison": "eq",
            "message": (
                f"Data-quality watchdog checks ERRORED: {err_names}. The "
                "monitor's pass/fail signal is unreliable until these are fixed."
            ),
        }
        try:
            issue_number = create_alert_issue(
                self_check,
                len(stats["errors"]),
                "One or more watchdog check queries raised an exception "
                "(see the task result's errors list / Sentry).",
            )
            _set_redis_dedup("watchdog_self_error", issue_number)
            stats["alerts_fired"] += 1
        except Exception as exc:
            logger.error("Watchdog self-alert failed: %s", exc)

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
        # Odds-API sport key → season_windows league slug (Queue #196 Item 3).
        # WNBA (summer) has no offseason window in season_windows → drops stay
        # real; NCAAB maps to a slug season_windows treats as always-active
        # unless a band is defined, so only the leagues with defined offseason
        # bands (nba/nhl/mlb/nfl) get seasonal suppression.
        _SPORT_KEY_TO_LEAGUE = {
            "basketball_nba": "nba",
            "icehockey_nhl": "nhl",
            "baseball_mlb": "mlb",
            "americanfootball_nfl": "nfl",
        }

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
            # Queue #196 Item 3 (r197's ask): a Tier-1 sport's source coverage
            # naturally falls when it stops playing (NBA/NHL in July, NCAAB in
            # summer). Those drops are the calendar, not a regression — annotate
            # them "seasonal" and do NOT count them as fired alerts (crying wolf),
            # while keeping them visible in the snapshot. Only ACTIVE-league drops
            # remain real alerts.
            from app.utils import season_windows

            real_drops, seasonal_drops = [], []
            for drop in cov_drops:
                league = _SPORT_KEY_TO_LEAGUE.get((drop.get("key") or "").split(":", 1)[0])
                note = season_windows.seasonal_note(league) if league else None
                if note:
                    drop["seasonal"] = True
                    drop["seasonal_note"] = note
                    seasonal_drops.append(drop)
                    logger.info(
                        "Source coverage drop (seasonal, suppressed): %s %+.1fpp — %s",
                        drop["key"], drop["delta"], note,
                    )
                    continue
                alert_msg = (
                    f"Source coverage drop: {drop['key']} went from "
                    f"{drop['yesterday']}% to {drop['today']}% "
                    f"({drop['delta']:+.1f}pp)"
                )
                logger.warning(alert_msg)
                stats["alerts_fired"] += 1
                real_drops.append(drop)
            stats["source_coverage_drops"] = real_drops
            if seasonal_drops:
                stats["source_coverage_drops_seasonal"] = seasonal_drops

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

    # --- Cockpit verdict (#1132 / L2-140): persist a compact summary the Alex
    # Cockpit reads as a RED tile. A P0/P1 that only lands in an email + a GitHub
    # issue is a silent alert if nobody's looking there; the cockpit is the eye
    # that's always open. RED when any P0/P1 check is failing; AMBER on a P2
    # failure or a self-error (monitor unreliable); GREEN when all clear.
    try:
        from app.tasks.redis_state import get_redis_client

        failing = [
            {
                "name": name,
                "severity": r.get("severity"),
                "value": r.get("value"),
                "threshold": r.get("threshold"),
                "message": r.get("message"),
                "issue": r.get("issue"),
            }
            for name, r in stats["results"].items()
            if not r.get("passed")
        ]
        red = any(f["severity"] in ("P0", "P1") for f in failing)
        amber = bool(failing) or bool(stats["errors"])
        summary = {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "status": "red" if red else ("amber" if amber else "green"),
            "checks_run": stats["checks_run"],
            "checks_passed": stats["checks_passed"],
            "alerts_fired": stats["alerts_fired"],
            "self_error": bool(stats["errors"]),
            "failing": failing,
        }
        # 26h TTL > the daily cadence, so a missed run reads stale (not green).
        get_redis_client().setex(
            "bainluck:data_quality_watchdog:last", 26 * 3600, json.dumps(summary, default=str)
        )
        stats["cockpit_status"] = summary["status"]
    except Exception as exc:
        logger.warning("Data-quality cockpit summary persist failed: %s", exc)

    return stats
