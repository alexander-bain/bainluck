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
import re
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

# --- #1835 (CAL-P1122): the per-bookmaker curve key, and the freeze it causes -
#
# `bainluck:bookmaker_calibration` holds ~96K outcomes — the whole
# `odds_api_bookmaker` source. `precompute_calibration`'s producer path REFUSES
# to publish while it is absent rather than publish a curve that is short a
# source (D21/#1978, and rightly). The consequence nobody wired a rail for: an
# absent key does not degrade the accuracy page, it FREEZES it, and it stays
# frozen for as long as the key stays absent, because the only writer runs on
# its own 6h beat and nothing notices that it has not landed.
#
# Measured 2026-09-12: the key expired at ~00:5xZ, the 00:36Z / 01:18Z / 02:15Z
# / 03:15Z builds all refused 19 ms into their diagnostics phase, and the page
# served a 4.6-hour-old curve until a lane read the phase ledger by hand and
# fired the writer from a one-off dyno. That run took **196.5 s** and returned
# `terminal: complete` — the writer was never slow and never starved. It was
# killed by a release, four times in a row, six hours apart.
#
# The cadence change (`precompute-bookmaker-calibration` 6h -> 2h) is what stops
# the key expiring; see that beat entry for the arithmetic. THIS is the rail
# that notices when the cadence is not enough, because the failure it has to
# catch is the one the cadence cannot fix: a writer that is arriving and still
# not landing. Before this, the only signal of a frozen accuracy page was a
# person reading the phase ledger by hand.
#
# IT ALERTS AND DOES NOT ACT, and that is deliberate twice over. Re-dispatching
# the writer from here would be an intra-task dispatch, which
# `test_no_task_dispatches_another_task` forbids for result-retention reasons;
# and a watchdog that silently repairs its own subject is a watchdog whose
# alarm nobody ever tunes. The repair belongs to the cadence.
#
# WHY NOT IN `precompute_calibration.py`, where the refusal is raised: that file
# is frozen by ruling 009 until the publish converges. The refusal there is
# correct and unchanged.
BOOKMAKER_CURVE_KEY = "bainluck:bookmaker_calibration"
#: The key's only writer — named once, so `_writer_cadence_seconds` can read its
#: real cadence off the beat entry instead of a number retyped here that would
#: silently stop matching the day the beat moves.
BOOKMAKER_WRITER_TASK = "app.tasks.precompute_bookmaker_calibration"
#: Absence younger than this is expected housekeeping between two writer fires;
#: older than this means a fire has come and gone without landing, which is a
#: person's problem. Derived from the beat's own cadence plus one run's grace.
BOOKMAKER_ABSENCE_GRACE_SECONDS = 600
_BOOKMAKER_ABSENT_SINCE_KEY = "bainluck:watchdog:bookmaker_curve_absent_since"

# --- #2006: a backend that blocks vacuum, alarmed before it costs 40 hours ----
#
# #2005: one client backend held `backend_xmin` for ~40 h. Vacuum could not
# advance anywhere in the database, the default landing page served 500s, and
# every instrument that was actually watched read survivable: Grid Sentinel
# green, link rate 91.0%, `/api/health` `{"status":"ok","db":true}`. It was
# found by accident, by a Phase-0 probe, and fixed in one command once found.
#
# The signal nobody read is two numbers, both free, both in `pg_stat_activity`:
#
#   * `max(age(backend_xmin))` — 81,643 mid-incident, 372 healthy. Two orders of
#     magnitude with nothing in between; this is as clean as production gets.
#   * the age in SECONDS of the oldest non-idle transaction — the same fact on a
#     wall clock instead of an xid clock.
#
# WHICH OF THE TWO ACTUALLY MEETS THE ONE-HOUR BAR — the arithmetic, because the
# issue's acceptance criterion ("fires within ~1 h") is not deliverable by the
# xid signal and it is worth saying so once rather than discovering it later.
# `age(backend_xmin)` counts TRANSACTIONS, not time, so its rate is this
# database's xid rate: the incident's own 81,643 over ~40 h is **0.57 xid/s**.
# At that rate XMIN_PAGE (50,000) is reached after roughly 24 HOURS. So:
#
#   * the WALL-CLOCK signal is the one that pages inside the hour;
#   * the XID signal is the unambiguous corroborator, and the only one that
#     still reads when `xact_start` is unreadable or the holder is a backend
#     whose transaction start we filtered out.
#
# They are therefore classified INDEPENDENTLY (see `classify_vacuum_signals`)
# and the worst KNOWN verdict wins. A signal that is absent is not a signal that
# is healthy — that conflation is #2005's own failure mode, and a candidate for
# this issue reproduced it exactly (2026-09-20 review on #2006: one missing
# optional input returned `unavailable` for the whole check, so the incident
# shape published `ready`).
#
# IT ALERTS AND DOES NOT ACT. Cancelling a backend is not transactional and
# cannot be rolled back — #1641 refuses it on the SQL rail for that reason and
# that refusal is right. The reaper (scope item 3), the autovacuum `ALTER TABLE`
# plan and any attended vacuum stay out of this module entirely.
VACUUM_BLOCK_FLAG_KEY = "bainluck:watchdog:vacuum_block"

#: Held-horizon thresholds in XIDS, straight from the issue body (warn 10,000 /
#: page 50,000) against a measured-healthy 372. At this database's 0.57 xid/s
#: those are ~4.9 h and ~24 h of held horizon.
VACUUM_XMIN_WARN = 10_000
VACUUM_XMIN_PAGE = 50_000

#: Oldest non-idle transaction, in SECONDS.
#:
#: PAGE is the issue's 1 h. WARN is 30 min, NOT the issue's 15 min, and the
#: departure is deliberate: the issue's own "Why" section records that the
#: calibration producer's beats cancel at **17–22 minutes**, so a 15-minute warn
#: would fire on healthy, designed behaviour several times a day and train
#: everyone to ignore this alarm. 30 min sits above the longest legitimate
#: holder and below the page.
VACUUM_XACT_WARN_S = 1_800
VACUUM_XACT_PAGE_S = 3_600

#: Worst-table dead-tuple percentage (scope item 4). Kept as a THIRD, OPTIONAL
#: signal rather than a check of its own: the issue's later measurement shows it
#: reads 2.2% "healthy" on the 38 GB table throughout the incident, so it can
#: corroborate but must never be required. During #2005 `events` read 57.5% and
#: `futures_markets` 24.6%.
VACUUM_DEAD_PCT_WARN = 20.0
VACUUM_DEAD_PCT_PAGE = 50.0

#: Every read below is bounded by this through the connection's startup packet
#: (#4482 — never a bare `SET`). All three queries are stats-view reads with no
#: user-table access; 5 s is two orders of magnitude of headroom, and a monitor
#: that can itself hang is the thing being monitored.
VACUUM_QUERY_TIMEOUT_MS = 5_000

#: WHAT AN UNPRIVILEGED ROLE ACTUALLY SEES — measured, 2026-09-20, on a real
#: server by `tests/integration/test_vacuum_block_signals_2006_real_postgres.py`,
#: because the answer decides whether either query works on Heroku at all (the
#: application role is not a superuser and is not in `pg_read_all_stats`).
#:
#: `pg_stat_activity` returns EVERY backend's row to everyone, and then nulls
#: most columns of the rows belonging to other roles. The split is not the one
#: the documentation's "the `query` field" sentence suggests:
#:
#:   * **`backend_xmin` IS readable across roles.** A superuser backend holding
#:     a snapshot reported its real `backend_xmin` to a freshly-created role with
#:     no privileges at all.
#:   * **`state`, `xact_start` and `backend_type` are NULL across roles.**
#:
#: Two consequences, and the first is a trap that would have shipped:
#:
#: 1. `backend_type <> 'autovacuum worker'` evaluates to NULL — and therefore
#:    EXCLUDES — every other-role row, i.e. exactly the rows whose `backend_xmin`
#:    is still readable. Written that way the xid signal would have been blinded
#:    on Heroku by its own autovacuum filter. `IS DISTINCT FROM` keeps them.
#: 2. The WALL-CLOCK signal is same-role-only by construction, and no SQL fixes
#:    that. It is not a defect for this ship: the application role owns every
#:    backend the application opens, and #2005's culprit was one of them — an
#:    orphaned dyno connection. It is a stated limit, and it is the sharpest
#:    argument for classifying the two signals independently, because they do not
#:    even see the same population.
#:
#: `application_name NOT LIKE 'pg_dump%'` excludes a backup, which holds one long
#: transaction on a 38 GB database by construction. The xid read deliberately
#: keeps pg_dump — a dump genuinely does hold the horizon, and at ~24 h to page
#: it cannot fire on one. An autovacuum worker is excluded where it is visible
#: (PostgreSQL ignores a vacuum's own xmin for the horizon, so counting one would
#: be a false positive); where its `backend_type` is nulled by the role check it
#: is counted, which is why this query returns the offending PID rather than a
#: bare `max()` — the pid is what turns an alarm into an action.
Q_VACUUM_OLDEST_XMIN = (
    "SELECT pid, coalesce(usename, '') AS usename, age(backend_xmin) AS xmin_age "
    "FROM pg_stat_activity "
    "WHERE backend_xmin IS NOT NULL "
    "AND backend_type IS DISTINCT FROM 'autovacuum worker' "
    "ORDER BY age(backend_xmin) DESC LIMIT 1"
)
#: The worst offender, not just its age — a pid and an application_name are what
#: make the alarm actionable instead of merely true. `query` is deliberately NOT
#: selected: it is nulled for other roles anyway, and it is the one column here
#: that could carry row data.
Q_VACUUM_OLDEST_XACT = (
    "SELECT pid, backend_type, coalesce(application_name, '') AS application_name, "
    "EXTRACT(EPOCH FROM (now() - xact_start)) AS xact_age_s "
    "FROM pg_stat_activity "
    "WHERE xact_start IS NOT NULL AND state <> 'idle' "
    "AND backend_type IS DISTINCT FROM 'autovacuum worker' "
    "AND coalesce(application_name, '') NOT LIKE 'pg_dump%' "
    "ORDER BY xact_start ASC LIMIT 1"
)
Q_VACUUM_WORST_DEAD_PCT = (
    "SELECT relname, n_live_tup, n_dead_tup FROM pg_stat_user_tables "
    "WHERE schemaname = 'public' AND n_live_tup + n_dead_tup > 1000 "
    "ORDER BY n_dead_tup::float8 / NULLIF(n_live_tup + n_dead_tup, 0) DESC "
    "LIMIT 1"
)

#: Ordered worst-last, so `max(known, key=...)` is the whole severity rule.
_VACUUM_SEVERITY = {"unknown": 0, "ok": 1, "warn": 2, "page": 3}


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


# --- #1501: alert EMISSION cooldown ------------------------------------------
# Fingerprinting (above) collapses many readings into one ISSUE. It does NOT
# reduce the EVENT count, and Sentry bills events — so a stall that persists for
# a day still billed one event per watchdog run.
#
# Measured over the 2026-07-21 -> 07-29 billing cycle, culprit
# ``app.tasks.run_freshness_watchdog``: **1,579 events, 24% of the entire
# 6,584-event cycle**, from a handful of distinct conditions repeating. And it
# is TWO events per reading, not one:
#
#   * 805 with no logger  -> ``sentry_sdk.capture_message`` below;
#   * 774 with logger ``app.tasks.watchdog`` -> the ``logger.critical(msg)`` at
#     the call sites, which the SDK's LoggingIntegration turns into an event of
#     its own because its default ``event_level`` is ``logging.ERROR``.
#
# Suppressing only the capture_message would therefore have removed roughly half
# the volume and looked like a fix. ``_alert`` gates BOTH behind one cooldown,
# and on the suppressed path logs at WARNING — still in the dyno logs, below the
# LoggingIntegration's event threshold, so it costs no quota.
#
# The alert itself must survive: #1158's gap table lists creation-stall and
# event-loop-block as Sentry-ONLY classes with no board or cockpit equivalent.
# So this rate-limits REPEATS, never the first occurrence: one emission per
# [alert_class, normalized provider] per ALERT_COOLDOWN_SECONDS. The GitHub
# filing rail (_file_watchdog_issue) is untouched — it has its own search-based
# dedup and accretes evidence onto the open issue.
ALERT_COOLDOWN_SECONDS = 6 * 3600
_ALERT_COOLDOWN_PREFIX = "bainluck:watchdog:alert_cooldown:"

#: A page/offset counter token: ``p0``, ``p35``, ``recv50``, ``a0``, ``155``.
_COUNTER_TOKEN_RE = re.compile(r"[A-Za-z]{0,6}\d+")


def _normalize_provider(provider: str) -> str:
    """Collapse high-cardinality tokens out of a fingerprint provider.

    ``kalshi_settled:fetch:KXNASDAQ100U:p0`` and
    ``kalshi_settled:fetch:KXMLBHRR:p1`` are the same condition on two tickers,
    but they fingerprinted as two issues AND held two independent cooldowns.

    Three token shapes are dropped, all of them measured in the real 2026-07-21
    census, where 31 raw ``[class, provider]`` pairs in 8 days collapse to 13:

    * ticker-shaped: ALL-CAPS, or ALL-CAPS-with-digits
      (``KXNASDAQ100U``, ``KXNBAGAME``);
    * a short alpha prefix followed by digits, or bare digits — page and offset
      counters (``p0``, ``p35``, ``recv50``, ``a0``, ``155``). Without this the
      SAME stalled phase held a separate cooldown per page of a paginated fetch,
      which is the fragmentation the cooldown exists to stop.

    Never returns empty — a provider that normalizes away entirely keeps its raw
    form rather than colliding with every other one.
    """
    parts = []
    for token in provider.split(":"):
        if not token:
            continue
        if _COUNTER_TOKEN_RE.fullmatch(token):
            continue
        stripped = token.replace("_", "")
        if stripped.isupper() and any(c.isdigit() for c in token):
            continue
        if stripped.isupper() and len(stripped) > 3:
            continue
        parts.append(token)
    return ":".join(parts) or provider


def _alert_on_cooldown(alert_class: str, provider: str) -> bool:
    """True when an identical alert was already emitted inside the window.

    Fails OPEN (returns False -> the alert is emitted) if Redis is unreachable:
    a telemetry-infra failure must never swallow an alarm, and the Redis error
    class itself is filtered separately in ``app/utils/sentry_filter.py``.

    Unlike the filter's in-process throttle this is FLEET-SHARED, which it can
    afford to be: it runs once per watchdog beat rather than on every exception
    path, so a bounded Redis round-trip here costs nothing.
    """
    key = f"{_ALERT_COOLDOWN_PREFIX}{alert_class}:{provider}"
    try:
        rc = _bounded_rc()
        # SET NX is the whole test: it succeeds only for the first caller in the
        # window, so check-then-set cannot race between concurrent watchdog runs.
        return not bool(rc.set(key, "1", nx=True, ex=ALERT_COOLDOWN_SECONDS))
    except Exception:
        return False


def _clear_alert_cooldown(alert_class: str, provider: str) -> None:
    """Drop the emission cooldown for one ``[class, provider]`` pair.

    This is RECOVERY behaviour and it has to be a separate action, because the
    cooldown window (6 h) is far longer than the beat that sets it (10 min). A
    condition that goes bad, clears, and goes bad again inside one window would
    otherwise be silent the second time — the alarm would be quietest exactly
    when a stall is flapping, which is the shape hardest to catch by hand.

    Best-effort by design: a Redis failure here can only leave a cooldown in
    place, i.e. it can delay the next alarm by less than one window. It can
    never raise, and it can never emit anything.
    """
    key = f"{_ALERT_COOLDOWN_PREFIX}{alert_class}:{_normalize_provider(provider)}"
    try:
        _bounded_rc().delete(key)
    except Exception:
        pass


def _alert(alert_class: str, provider: str, msg: str) -> bool:
    """Emit one watchdog alarm, rate-limited to one emission per cooldown window.

    Returns True when the alarm was emitted at full volume. Both quota-costing
    channels (the ERROR-level log record and the Sentry message) are inside the
    gate; the suppressed path still writes the line at WARNING so a persistent
    stall stays fully visible in ``heroku logs``.
    """
    provider = _normalize_provider(provider)
    if _alert_on_cooldown(alert_class, provider):
        logger.warning("%s [sentry suppressed — %ss cooldown]", msg, ALERT_COOLDOWN_SECONDS)
        return False
    logger.critical(msg)
    _capture_fingerprinted(alert_class, provider, msg)
    return True


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
            # #219E Item 2(a): fingerprint on [class, provider] — NOT the message
            # (its hours-value spawned one Sentry issue per reading = noise).
            # #1501: and rate-limit the EMISSION, since fingerprinting collapses
            # issues but not billable events. _alert owns the logger.critical.
            _alert("creation_stall", a["source"], msg)
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
    PHASE_STUCK_SECONDS — a suspected event-loop block at that exact phase.

    #1280 Item 3: a frozen marker whose owning worker generation is no longer
    alive (deploy/restart) is reconciled away, not paged — only a stall owned by a
    live generation reads RED."""
    from app.tasks.redis_state import worker_boot_alive

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
                # #1280 Item 3: a frozen marker is only a LIVE stall if the worker
                # generation that wrote it is still alive. If the marker records an
                # owner boot id but that generation is gone (a deploy/restart left
                # the marker behind), this is a stale leftover, NOT an event-loop
                # block — reconcile it away (clear marker + owner + tracking) and
                # do not page. A marker with no recorded owner (legacy / owner
                # write dropped) falls through to the original alert path so a real
                # stall is never silently suppressed.
                owner_key = phase_key + ":owner"
                try:
                    owner_raw = rc.get(owner_key)
                except Exception:
                    owner_raw = None
                owner = (
                    owner_raw.decode() if isinstance(owner_raw, bytes) else owner_raw
                )
                if owner and not worker_boot_alive(rc, owner):
                    for _k in (phase_key, owner_key, seen_key):
                        try:
                            rc.delete(_k)
                        except Exception:
                            pass
                    continue
                msg = (
                    f"Suspected event-loop block: {task_label} phase "
                    f"'{marker}' has not advanced in {stuck_seconds:.0f}s "
                    f"(threshold {PHASE_STUCK_SECONDS}s) — the poll is likely "
                    f"stuck on a synchronous op at this phase (#995)."
                )
                # #219E Item 2(a): fingerprint on [class, task] — the phase suffix
                # carries an elapsed-seconds value ("@174s") + the stuck_seconds in
                # the message both drift, so message-fingerprinting spawned a new
                # Sentry issue per reading. Group by the STALLED PHASE instead.
                # #1501: _alert adds the emission cooldown and owns the
                # logger.critical (which was itself a billable Sentry event).
                _stuck_phase = marker.split("@", 1)[0]
                _alert("phase_block", f"{task_label}:{_stuck_phase}", msg)
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


def _writer_cadence_seconds() -> int:
    """How long the key may legitimately be absent — read from the beat entry.

    A number retyped here would keep its old value the day the beat moves, and
    the alarm would then fire one cadence early (noise) or one cadence late —
    the thing it exists to catch, missed. So it is derived from the crontab's
    own (minute, hour) sets: the LARGEST gap between consecutive fire slots in a
    day, which is the longest the key can legitimately be unwritten.

    Deliberately NOT ``crontab.remaining_estimate``. That reads as the obvious
    way to ask a schedule about itself and it answers a different question —
    it measures from *now* to the next fire after the anchor, not from the
    anchor — so on the 2h form it returns anything from 5 minutes to 3.5 hours
    depending on when it is called.
    """
    from app.tasks import celery_app

    for entry in celery_app.conf.beat_schedule.values():
        if entry.get("task") != BOOKMAKER_WRITER_TASK:
            continue
        schedule = entry.get("schedule")
        minutes = sorted(getattr(schedule, "minute", ()) or ())
        hours = sorted(getattr(schedule, "hour", ()) or ())
        if not minutes or not hours:
            break
        slots = sorted(h * 60 + m for h in hours for m in minutes)
        # Circular: the last slot of the day is followed by the first of the
        # next, so the wrap is a real gap and on a 4-fire schedule it is often
        # the largest one.
        gaps = [b - a for a, b in zip(slots, slots[1:])]
        gaps.append(slots[0] + 24 * 60 - slots[-1])
        return max(gaps) * 60
    # No beat entry, or a schedule with no (minute, hour) to read. Six hours is
    # the cadence this beat carried before CAL-P1122 — the most forgiving value
    # that was ever true, so a fallback can only make this alarm later than it
    # should be, never noisier.
    return 6 * 3600


def _run_bookmaker_curve_watchdog(rc=None, now=None):
    """Alarm when the per-bookmaker curve key is absent for longer than one
    writer cadence.

    The accuracy page does not degrade when ``bainluck:bookmaker_calibration``
    expires — it FREEZES, because the producer refuses to publish a curve short
    a whole source. See the constant block above.

    Three states, and the middle one is why this is not a one-line "key missing"
    alarm:

    * **present** — nothing to report, and the absent-since marker is cleared.
    * **absent, briefly** — recorded, not alarmed. The key is rewritten by a
      beat, not continuously, so a short gap after an expiry is housekeeping and
      paging on it would train everyone to ignore this alarm.
    * **absent for longer than one writer cadence plus grace** — a fire has come
      and gone without landing. The cadence cannot fix that, so it is a person's
      problem and it says so, with the terminal to read.

    Injectable ``rc`` and ``now`` for the guard test. Nothing here may raise: a
    watchdog that dies on its own newest check takes the two older ones with it.
    """
    rc = rc or _bounded_rc()
    now = now or datetime.now(timezone.utc)

    try:
        present = bool(rc.get(BOOKMAKER_CURVE_KEY))
    except Exception:
        # Cannot tell present from absent, so claim neither rather than start an
        # absence clock that a Redis blip invented.
        return {"key_present": None, "alerted": False, "reason": "redis_unreadable"}

    if present:
        try:
            rc.delete(_BOOKMAKER_ABSENT_SINCE_KEY)
        except Exception:
            pass
        return {"key_present": True, "alerted": False}

    try:
        raw = rc.get(_BOOKMAKER_ABSENT_SINCE_KEY)
    except Exception:
        raw = None
    first_seen = None
    if raw:
        try:
            first_seen = datetime.fromisoformat(
                raw.decode() if isinstance(raw, bytes) else raw
            )
        except Exception:
            first_seen = None

    if first_seen is None:
        # First reading of this absence. Record the clock and say nothing: the
        # TTL is 24h and the writer fires far more often than that, so a gap
        # here is usually the seconds between an expiry and the next fire.
        try:
            rc.setex(
                _BOOKMAKER_ABSENT_SINCE_KEY,
                7 * 24 * 3600,
                now.isoformat(),
            )
        except Exception:
            pass
        return {"key_present": False, "alerted": False, "absent_seconds": 0}

    absent_seconds = (now - first_seen).total_seconds()
    tolerated = _writer_cadence_seconds() + BOOKMAKER_ABSENCE_GRACE_SECONDS
    if absent_seconds < tolerated:
        return {
            "key_present": False,
            "alerted": False,
            "absent_seconds": round(absent_seconds),
        }

    _alert(
        "bookmaker_curve_absent",
        "odds_api_bookmaker",
        f"{BOOKMAKER_CURVE_KEY} has been absent for {round(absent_seconds / 60)} "
        f"minutes — longer than one writer cadence ({round(tolerated / 60)} min) "
        f"— so a fire has come and gone without landing. THE ACCURACY PAGE IS "
        f"FROZEN: every hourly build refuses rather than publish ~96K outcomes "
        f"short (#1835). Read the writer's terminal at "
        f"/api/admin/celery/task-metrics/bookmaker_calibration; re-running "
        f"{BOOKMAKER_WRITER_TASK} is idempotent and fails closed.",
    )
    return {
        "key_present": False,
        "alerted": True,
        "absent_seconds": round(absent_seconds),
    }


def _classify_one(value, warn_at, page_at) -> str:
    """One signal's verdict: ``unknown`` / ``ok`` / ``warn`` / ``page``.

    ``None`` is ``unknown``, never ``ok``. Comparisons are "at or above"; the
    issue writes ``>``, which differs by one xid / one second and is not worth a
    second comparison operator in a file where the point is that all three
    signals are judged the same way.
    """
    if value is None:
        return "unknown"
    if value >= page_at:
        return "page"
    if value >= warn_at:
        return "warn"
    return "ok"


def classify_vacuum_signals(xmin_age, xact_age_s, dead_pct):
    """Judge each signal on its own and return ``(status, per_signal)``.

    THE CORRECTION THIS FUNCTION EXISTS FOR. The rejected candidate opened with
    ``if xmin_age is None or xact_age_s is None or dead_pct is None: return
    "unavailable"`` — so one absent optional input erased two present ones, and
    the #2005 shape itself (``xmin_age=81_643`` with no table stats) classified
    as "we could not tell" rather than as the page it is. That is #2005's own
    failure mode rebuilt inside its fix: the absence of a signal read as the
    absence of a problem.

    So: each signal is classified independently, and the status is the WORST
    KNOWN verdict. ``unavailable`` is returned only when NOTHING is known — all
    three ``None`` — because that, and only that, is genuinely "we could not
    tell", and it is never ``ok``.
    """
    per_signal = {
        "xmin_age": _classify_one(xmin_age, VACUUM_XMIN_WARN, VACUUM_XMIN_PAGE),
        "xact_age_s": _classify_one(
            xact_age_s, VACUUM_XACT_WARN_S, VACUUM_XACT_PAGE_S
        ),
        "worst_dead_pct": _classify_one(
            dead_pct, VACUUM_DEAD_PCT_WARN, VACUUM_DEAD_PCT_PAGE
        ),
    }
    known = [v for v in per_signal.values() if v != "unknown"]
    if not known:
        return "unavailable", per_signal
    return max(known, key=_VACUUM_SEVERITY.__getitem__), per_signal


async def _read_vacuum_signals() -> dict:
    """Read the three vacuum-blocking signals. Never raises.

    Each read is isolated: a failure degrades THAT field to ``None`` and leaves
    the others intact, which is the only reason `classify_vacuum_signals` has
    anything to be independent about. The whole session is bounded at
    ``VACUUM_QUERY_TIMEOUT_MS`` through the connection's startup packet — see
    ``get_task_session``'s #4482 note for why a bare ``SET`` would not hold.
    """
    from app.tasks.base import get_task_session

    signals = {
        "xmin_age": None,
        "xmin_pid": None,
        "xmin_usename": None,
        "xact_age_s": None,
        "xact_pid": None,
        "xact_backend_type": None,
        "xact_application_name": None,
        "worst_table": None,
        "worst_dead_pct": None,
    }

    try:
        async with get_task_session(
            statement_timeout_ms=VACUUM_QUERY_TIMEOUT_MS
        ) as session:
            try:
                row = (await session.execute(sa_text(Q_VACUUM_OLDEST_XMIN))).first()
                if row is not None and row.xmin_age is not None:
                    signals["xmin_age"] = int(row.xmin_age)
                    signals["xmin_pid"] = row.pid
                    signals["xmin_usename"] = row.usename
            except Exception:
                logger.warning("watchdog: xmin-age read failed", exc_info=True)

            try:
                row = (await session.execute(sa_text(Q_VACUUM_OLDEST_XACT))).first()
                if row is not None and row.xact_age_s is not None:
                    signals["xact_age_s"] = int(float(row.xact_age_s))
                    signals["xact_pid"] = row.pid
                    signals["xact_backend_type"] = row.backend_type
                    signals["xact_application_name"] = row.application_name
            except Exception:
                logger.warning("watchdog: oldest-xact read failed", exc_info=True)

            try:
                row = (
                    await session.execute(sa_text(Q_VACUUM_WORST_DEAD_PCT))
                ).first()
                if row is not None:
                    live, dead = int(row.n_live_tup), int(row.n_dead_tup)
                    total = live + dead
                    if total > 0:
                        signals["worst_dead_pct"] = round(dead / total * 100, 1)
                        signals["worst_table"] = row.relname
            except Exception:
                logger.warning("watchdog: dead-tuple read failed", exc_info=True)
    except Exception:
        # The session itself could not be opened. Every field stays None, which
        # classifies as `unavailable` — not `ok`, and not an alarm either.
        logger.warning("watchdog: vacuum-signal session failed", exc_info=True)

    return signals


def _vacuum_alert_body(signals: dict, status: str, per_signal: dict) -> tuple[str, str]:
    """The alarm's message and its board-issue body — numbers, then the DO."""
    xmin = signals.get("xmin_age")
    xmin_pid = signals.get("xmin_pid")
    xact = signals.get("xact_age_s")
    pid = signals.get("xact_pid")
    app_name = signals.get("xact_application_name") or "?"
    table = signals.get("worst_table")
    dead = signals.get("worst_dead_pct")

    msg = (
        f"Postgres vacuum horizon is held ({status}): "
        f"age(backend_xmin)={xmin if xmin is not None else 'unknown'} on pid "
        f"{xmin_pid if xmin_pid is not None else '?'} "
        f"(warn {VACUUM_XMIN_WARN} / page {VACUUM_XMIN_PAGE}); oldest non-idle "
        f"transaction={xact if xact is not None else 'unknown'}s "
        f"(warn {VACUUM_XACT_WARN_S} / page {VACUUM_XACT_PAGE_S}) on pid "
        f"{pid if pid is not None else '?'} application_name '{app_name}'; "
        f"worst dead-tuple table "
        f"{table or 'unknown'}={dead if dead is not None else 'unknown'}%. "
        f"#2005 was this shape for 40 hours with /api/health reading ok."
    )

    body = (
        f"The vacuum-block watchdog classified the Postgres vacuum horizon as "
        f"**{status}**.\n\n"
        f"| signal | value | verdict |\n|---|---:|---|\n"
        f"| `age(backend_xmin)` (pid "
        f"`{xmin_pid if xmin_pid is not None else '?'}`, role "
        f"`{signals.get('xmin_usename') or '?'}`) | "
        f"{xmin if xmin is not None else '—'} | {per_signal['xmin_age']} |\n"
        f"| oldest non-idle transaction (s) | "
        f"{xact if xact is not None else '—'} | {per_signal['xact_age_s']} |\n"
        f"| worst dead-tuple table | "
        f"{(table or '—')} "
        f"{('' if dead is None else f'({dead}%)')} | "
        f"{per_signal['worst_dead_pct']} |\n\n"
        f"Oldest transaction's backend: pid `{pid if pid is not None else '?'}`, "
        f"backend_type `{signals.get('xact_backend_type') or '?'}`, "
        f"application_name `{app_name}`.\n\n"
        f"**Why this pages.** #2005: one client backend held `backend_xmin` for "
        f"~40 h, vacuum could not advance anywhere, the landing page served "
        f"500s, and `/api/health` answered `ok` throughout. It was found by "
        f"accident and fixed in one command. `max(age(backend_xmin))` read "
        f"**81,643** during that incident and **372** ten minutes after it was "
        f"cleared.\n\n"
        f"**What this does NOT do.** It does not cancel anything. Cancelling a "
        f"backend is not transactional and cannot be rolled back — #1641 "
        f"refuses `pg_cancel_backend` on the SQL rail for that reason. The "
        f"remedy is an attended `heroku pg:kill <pid>`, and the pid is above.\n\n"
        f"_Auto-filed by the vacuum-block watchdog (#2006); comments accrete "
        f"while the condition persists._"
    )
    return msg, body


def _run_vacuum_block_watchdog(signals: dict, rc=None) -> dict:
    """Alarm, suppress, and recover on the classified vacuum signals.

    Split from :func:`_read_vacuum_signals` so the decision is testable without
    a database and the read is provable without a decision.

    Three behaviours, and the third is the one a monitor usually lacks:

    * **page** — one alarm through the shared rail (Sentry fingerprinted on
      ``[vacuum_block, postgres]`` + `logger.critical`) plus ONE deduped board
      issue, then a Redis flag for the admin surfaces.
    * **warn** — the same alarm, no board issue. A warn is "look at this today",
      and an auto-filed issue per warn is how a board stops being read.
    * **ok / unavailable — RECOVERY** — the flag is cleared AND so is the
      emission cooldown, so the next episode alarms at once instead of inheriting
      up to 6 h of silence from the last one. ``unavailable`` clears the flag but
      never alarms: we could not tell, which is not the same as bad.
    """
    rc = rc or _bounded_rc()
    status, per_signal = classify_vacuum_signals(
        signals.get("xmin_age"),
        signals.get("xact_age_s"),
        signals.get("worst_dead_pct"),
    )
    result = {"status": status, "signals": per_signal, "alerted": False, **signals}

    if status in ("ok", "unavailable"):
        try:
            rc.delete(VACUUM_BLOCK_FLAG_KEY)
        except Exception:
            pass
        _clear_alert_cooldown("vacuum_block", "postgres")
        return result

    msg, body = _vacuum_alert_body(signals, status, per_signal)
    result["alerted"] = _alert("vacuum_block", "postgres", msg)

    if status == "page":
        title = (
            "[watchdog] a Postgres backend is holding the vacuum horizon "
            f"(oldest non-idle transaction {signals.get('xact_age_s')}s, "
            f"age(backend_xmin) {signals.get('xmin_age')})"
        )
        try:
            result["filed"] = _file_watchdog_issue(
                "vacuum_block", "postgres", title, body
            )
        except Exception as exc:
            logger.warning("watchdog: vacuum-block filing failed: %s", exc)

    try:
        rc.setex(
            VACUUM_BLOCK_FLAG_KEY,
            7200,
            json.dumps({"status": status, "signals": per_signal, **signals}),
        )
    except Exception:
        pass
    return result


async def _run_freshness_watchdog():
    """Combined entry: creation-freshness (async DB) + phase-heartbeat (Redis)."""
    creation = await _run_creation_freshness_watchdog()
    phase = _run_phase_heartbeat_watchdog()
    try:
        bookmaker_curve = _run_bookmaker_curve_watchdog()
    except Exception:
        # Belt and braces over the function's own internal guards: the two
        # checks above predate this one and must not be able to fail because of
        # it.
        logger.exception("watchdog: bookmaker-curve check raised")
        bookmaker_curve = {"key_present": None, "refired": False, "reason": "raised"}
    # #2006. Last, and behind the same belt-and-braces guard as the check above
    # it: three checks that predate this one must not be able to fail because of
    # it. The verdict rides the existing summary key, which is already read by
    # the celery dashboard (`routes/admin_celery.py`) and the cockpit
    # (`routes/admin_cockpit.py`) — both admin-authenticated. Nothing here goes
    # near the unauthenticated readiness probe, which is where a candidate for
    # this issue tried to put it and where three sequential stats queries do not
    # belong.
    try:
        vacuum_block = _run_vacuum_block_watchdog(await _read_vacuum_signals())
    except Exception:
        logger.exception("watchdog: vacuum-block check raised")
        vacuum_block = {"status": "unavailable", "alerted": False, "reason": "raised"}
    summary = {
        "creation": creation,
        "phase_heartbeat": phase,
        "bookmaker_curve": bookmaker_curve,
        "vacuum_block": vacuum_block,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Persist the latest result so the admin dashboard / health surface can show
    # per-source creates-freshness + any stuck phase without its own DB query.
    try:
        _bounded_rc().setex(WATCHDOG_SUMMARY_KEY, 3600, json.dumps(summary))
    except Exception:
        pass
    return summary
