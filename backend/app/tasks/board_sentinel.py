"""Board Sentinel — RED means the board itself has a real hygiene defect (Queue #258).

The Flow/Grid/Calibration sentinels keep the *product* honest; this one keeps the
*board* honest, so GitHub `Ready` stays a trustworthy execution source. It follows
the same verdict grammar as the Grid Sentinel — classify every candidate as REAL
(an objective, agent-fixable board-hygiene violation) vs UNKNOWN (an API /
rate-limit / auth inability — never GREEN, never a cleanup accusation) — and files
exactly ONE deduped board-cleanup issue when RED, closing it on GREEN through the
shared filing rail (app/tasks/sentinel_filing.py).

Daily checks (all target 0 unless noted):
  1. duplicate fingerprints among open ``alert-intake`` issues — the exact class
     the shared rail now prevents forward (r252: `286b23d93590` ×5; the confirmed
     #1443/#1251/#1125 Grid dupes). Any residual is a REAL cleanup target.
  2. untriaged ``alert-intake`` left in Inbox over 48h — Inbox is temporary intake;
     a stale card means triage stalled.
  3. default/template P1 share among open ``alert-intake`` above a documented cap —
     after Queue #258 sentinels default P2, so a high auto-filed-P1 share is
     template noise to review (never an auto-downgrade — that stays a human call).
  4. parked/blocked issues sitting in Inbox — a blocked card belongs out of intake.
  5. open ``alert-intake`` issues missing every ``area:*`` label — automation-filed
     issues must always route to an area; a bare one is a filing regression.

Checks 2 and 4 need the Project board column (Status), read via GraphQL. If that
read fails, those two checks are UNKNOWN (not GREEN) — we never accuse the board of
being clean or dirty when we could not measure it.

Read-only against GitHub — the sentinel files/updates its own cleanup issue only;
it performs NO bulk board mutation (Ops owns the one-time cleanup, per Queue #258).
"""

import hashlib
import logging
import os
import re
import time as _time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (Redis-tunable, no-deploy — mirrors the flow/grid sentinels).
# Documented caps live here and in docs/github-workflow.md.
# ---------------------------------------------------------------------------
INBOX_TRIAGE_HOURS = 48.0          # board:sentinel_inbox_triage_hours
# No more than this fraction of open alert-intake issues should be priority:p1.
# After Queue #258 sentinels default to P2; a higher share is template noise worth
# a human review pass (NOT an auto-downgrade). Applied only past a small floor so a
# tiny board can't trip it.
TEMPLATE_P1_SHARE_CAP = 0.35       # board:sentinel_template_p1_share_cap
TEMPLATE_P1_MIN_POPULATION = 6     # need at least this many intake issues to judge share

INBOX_COLUMN = "Inbox"
_BOARD_MARKER = "board-sentinel-fingerprint"
# Labels that mean "not active intake" — a card carrying one should not sit in Inbox.
_PARKED_LABELS = {"blocked", "parked", "on-hold"}

# Any sentinel fingerprint marker embedded in an issue body, e.g.
# ``flow-sentinel-fingerprint:abc123``. Used for the duplicate-fingerprint scan.
_FINGERPRINT_RE = re.compile(r"([a-z][a-z0-9-]*-fingerprint):([0-9a-f]{6,40})")


def _load_overrides() -> None:
    global INBOX_TRIAGE_HOURS, TEMPLATE_P1_SHARE_CAP
    try:
        from app.tasks.redis_state import get_redis_client

        r = get_redis_client()
        for key, name, cast in (
            ("board:sentinel_inbox_triage_hours", "INBOX_TRIAGE_HOURS", float),
            ("board:sentinel_template_p1_share_cap", "TEMPLATE_P1_SHARE_CAP", float),
        ):
            v = r.get(key)
            if v is not None:
                globals()[name] = cast(v.decode() if isinstance(v, bytes) else v)
    except Exception as exc:
        logger.info("Board sentinel overrides not loaded (using defaults): %s", exc)


def board_fingerprint() -> str:
    """One stable fingerprint for the whole board-cleanup issue — a repeat RED run
    comments the same issue instead of filing a new one, and a GREEN run closes it
    (Queue #258 lifecycle). Deliberately constant across runs."""
    return hashlib.sha1(b"board:hygiene").hexdigest()[:12]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def _parse_dt(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _fingerprints_in(body: str | None) -> set[tuple[str, str]]:
    """Every ``<marker>:<fp>`` sentinel fingerprint pair found in a body."""
    return {(m.group(1), m.group(2)) for m in _FINGERPRINT_RE.finditer(body or "")}


def _labels(issue: dict) -> list[str]:
    return list(issue.get("labels") or [])


def _is_intake(issue: dict) -> bool:
    return "alert-intake" in _labels(issue)


# ---------------------------------------------------------------------------
# Pure checks (unit-tested — operate on normalized issue dicts:
#   {number, title, body, labels:[str], created_at:iso, column:str|None})
# ---------------------------------------------------------------------------
def check_duplicate_fingerprints(issues: list[dict]) -> list[dict]:
    """Same sentinel fingerprint on ≥2 open alert-intake issues — the r252 dupe
    class the shared rail now prevents forward. The board sentinel's OWN marker is
    excluded (its own issue is single-by-construction)."""
    groups: dict[tuple[str, str], set[int]] = {}
    for i in issues:
        if not _is_intake(i):
            continue
        num = i.get("number")
        if num is None:
            continue
        for marker, fp in _fingerprints_in(i.get("body")):
            if marker == _BOARD_MARKER:
                continue
            groups.setdefault((marker, fp), set()).add(num)
    out = []
    for (marker, fp), nums in sorted(groups.items()):
        if len(nums) > 1:
            ordered = sorted(nums)
            out.append({
                "check": "duplicate_fingerprint",
                "marker": marker,
                "fingerprint": fp,
                "issues": ordered,
                "detail": f"`{marker}:{fp}` appears on {len(ordered)} open "
                          f"alert-intake issues {ordered} — keep #{ordered[0]}, "
                          f"close the rest (the r252 dupe class)",
            })
    return out


def check_stale_inbox(issues: list[dict], now, max_hours: float = INBOX_TRIAGE_HOURS) -> list[dict]:
    """alert-intake issues sitting in Inbox longer than the triage bar. ``now`` is
    injected for testability."""
    out = []
    for i in issues:
        if not _is_intake(i) or i.get("column") != INBOX_COLUMN:
            continue
        created = _parse_dt(i.get("created_at"))
        if created is None:
            continue
        age_h = (now - created).total_seconds() / 3600.0
        if age_h > max_hours:
            out.append({
                "check": "stale_inbox",
                "issue": i.get("number"),
                "age_hours": round(age_h, 1),
                "detail": f"#{i.get('number')} '{(i.get('title') or '')[:60]}' has sat "
                          f"in Inbox {age_h:.0f}h (>{max_hours:.0f}h triage bar)",
            })
    return out


def check_template_p1_share(
    issues: list[dict],
    cap: float = TEMPLATE_P1_SHARE_CAP,
    min_population: int = TEMPLATE_P1_MIN_POPULATION,
) -> list[dict]:
    """Share of open alert-intake issues at priority:p1 above the documented cap.
    Only judged past a small floor so a tiny board can't trip it. This flags for a
    human REVIEW pass — it never downgrades anything (Queue #258)."""
    intake = [i for i in issues if _is_intake(i)]
    if len(intake) < min_population:
        return []
    p1 = [i for i in intake if "priority:p1" in _labels(i)]
    share = len(p1) / len(intake)
    if share > cap:
        return [{
            "check": "template_p1_share",
            "share": round(share, 3),
            "cap": cap,
            "p1_issues": [i.get("number") for i in p1],
            "detail": f"{len(p1)}/{len(intake)} open alert-intake issues are "
                      f"priority:p1 ({share*100:.0f}% > {cap*100:.0f}% cap) — review "
                      f"whether each P1 is evidence-gated (do NOT bulk-downgrade)",
        }]
    return []


def check_blocked_in_inbox(issues: list[dict]) -> list[dict]:
    """Blocked/parked cards sitting in Inbox — a blocked card belongs out of active
    intake (board-wide, not just alert-intake)."""
    out = []
    for i in issues:
        if i.get("column") != INBOX_COLUMN:
            continue
        parked = _PARKED_LABELS & set(_labels(i))
        if parked:
            out.append({
                "check": "blocked_in_inbox",
                "issue": i.get("number"),
                "labels": sorted(parked),
                "detail": f"#{i.get('number')} '{(i.get('title') or '')[:60]}' is "
                          f"{'/'.join(sorted(parked))} but sits in Inbox — move it out "
                          f"of active intake",
            })
    return out


def check_missing_area_label(issues: list[dict]) -> list[dict]:
    """Open alert-intake issues carrying no ``area:*`` label — an automation filing
    regression (every sentinel adds an area label)."""
    out = []
    for i in issues:
        if not _is_intake(i):
            continue
        if not any(str(l).startswith("area:") for l in _labels(i)):
            out.append({
                "check": "missing_area_label",
                "issue": i.get("number"),
                "detail": f"#{i.get('number')} '{(i.get('title') or '')[:60]}' has no "
                          f"area:* label — assign one so it routes",
            })
    return out


# ---------------------------------------------------------------------------
# Classification → verdict. REAL = any objective violation. UNKNOWN = a check
# could not run (no column data / fetch failure). GREEN = everything ran clean.
# ---------------------------------------------------------------------------
def classify_board(
    issues: list[dict], now, *, columns_available: bool, fetch_errors: list[dict] | None = None
) -> dict:
    """Run every check and split into real findings + unknown checks. ``now`` and
    ``columns_available`` are injected so the whole classification is a pure,
    deterministic function of its inputs (fixtures cover every branch)."""
    fetch_errors = fetch_errors or []
    real: list[dict] = []
    unknown: list[dict] = []

    # Checks that only need issue metadata (labels/body/created_at) always run.
    real += check_duplicate_fingerprints(issues)
    real += check_template_p1_share(issues)
    real += check_missing_area_label(issues)

    # Column-dependent checks: REAL findings when we have column data, else UNKNOWN.
    if columns_available:
        real += check_stale_inbox(issues, now)
        real += check_blocked_in_inbox(issues)
    else:
        unknown.append({
            "check": "inbox_column_checks",
            "detail": "Project board column (Status) unavailable — stale-inbox and "
                      "blocked-in-inbox checks could not run (UNKNOWN, not GREEN)",
        })

    for err in fetch_errors:
        unknown.append({"check": "fetch_error", "detail": err.get("detail", str(err))})

    return {"real": real, "unknown": unknown, "counts": _counts(issues, columns_available)}


def _counts(issues: list[dict], columns_available: bool) -> dict:
    intake = [i for i in issues if _is_intake(i)]
    return {
        "open_issues_scanned": len(issues),
        "open_alert_intake": len(intake),
        "in_inbox": sum(1 for i in issues if i.get("column") == INBOX_COLUMN)
        if columns_available else None,
        "columns_available": columns_available,
    }


def board_verdict(classified: dict) -> str:
    """RED if any REAL finding; else UNKNOWN if any check could not run; else GREEN.
    UNKNOWN is deliberately distinct from GREEN — a board we could not fully measure
    is never asserted clean."""
    if classified.get("real"):
        return "red"
    if classified.get("unknown"):
        return "unknown"
    return "green"


# ---------------------------------------------------------------------------
# Data fetch (GitHub REST + Project GraphQL). Returns (issues, columns_available,
# errors). Network-touching — tests monkeypatch it or its httpx calls.
# ---------------------------------------------------------------------------
def _fetch_project_columns() -> dict[int, str] | None:
    """issue number → Project Status (column) via GraphQL, paginated. Returns None
    on any failure (so the column-dependent checks go UNKNOWN, never GREEN)."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, PROJECT_ID

    if not GITHUB_TOKEN or not PROJECT_ID:
        return None
    query = """
    query($projectId: ID!, $cursor: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              fieldValueByName(name: "Status") {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
              }
              content {
                ... on Issue { number }
                ... on PullRequest { number }
              }
            }
          }
        }
      }
    }
    """
    columns: dict[int, str] = {}
    cursor = None
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    try:
        for _ in range(20):  # up to 2000 board items — ample
            resp = httpx.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={"query": query, "variables": {"projectId": PROJECT_ID, "cursor": cursor}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                logger.warning("Board sentinel: GraphQL project read errored: %s", data["errors"])
                return None
            items = (((data.get("data") or {}).get("node") or {}).get("items") or {})
            for node in items.get("nodes") or []:
                content = node.get("content") or {}
                num = content.get("number")
                status = (node.get("fieldValueByName") or {}).get("name")
                if num is not None and status:
                    columns[num] = status
            page = items.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
    except Exception as exc:
        logger.warning("Board sentinel: project column fetch failed: %s", exc)
        return None
    return columns


def _fetch_board_state() -> tuple[list[dict], bool, list[dict]]:
    """Assemble the normalized open-issue list + column annotations.

    Returns (issues, columns_available, errors). A REST failure yields an empty
    issue list + an error (→ verdict UNKNOWN). A GraphQL column failure keeps the
    issues but marks columns unavailable (→ only checks 2/4 go UNKNOWN)."""
    from app.tasks.sentinel_filing import list_open_alert_issues

    errors: list[dict] = []
    raw = list_open_alert_issues()
    if not raw:
        # Could be a genuinely empty board OR a fetch failure — the rail already
        # logged. We cannot tell them apart here, so treat empty as UNKNOWN only
        # when the token is set (a real call was attempted).
        from app.tasks.bug_report_github import GITHUB_TOKEN

        if not GITHUB_TOKEN:
            errors.append({"detail": "GITHUB_TOKEN unset — cannot read the board"})
            return [], False, errors

    columns = _fetch_project_columns()
    columns_available = columns is not None
    if not columns_available:
        errors.append({"detail": "Project board column read failed (GraphQL)"})

    issues = []
    for i in raw:
        num = i.get("number")
        issues.append({
            "number": num,
            "title": i.get("title") or "",
            "body": i.get("body") or "",
            "labels": [
                (lbl.get("name") if isinstance(lbl, dict) else lbl)
                for lbl in (i.get("labels") or [])
            ],
            "created_at": i.get("created_at"),
            "column": (columns or {}).get(num),
        })
    return issues, columns_available, errors


# ---------------------------------------------------------------------------
# Evidence-pack + filing (via the shared rail)
# ---------------------------------------------------------------------------
def build_board_issue_title(real: list[dict]) -> str:
    kinds = sorted({f["check"] for f in real})
    return f"[Board Sentinel] {len(real)} board-hygiene defect(s): {', '.join(kinds)}"[:256]


def build_board_issue_body(classified: dict) -> str:
    fp = board_fingerprint()
    real = classified["real"]
    unknown = classified.get("unknown") or []
    counts = classified.get("counts") or {}
    parts = [
        "## Board Sentinel finding",
        "",
        f"`{_BOARD_MARKER}:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Real board-hygiene defects:** {len(real)}  ",
        f"**Open alert-intake scanned:** {counts.get('open_alert_intake')}  ",
        f"**Unknown (could not measure):** {len(unknown)}  ",
        "",
        "### Real defects (RED — objective board-hygiene violations)",
    ]
    for f in real[:60]:
        parts.append(f"- **[{f['check']}]** {f['detail']}")
    if len(real) > 60:
        parts.append(f"- …and {len(real) - 60} more")
    if unknown:
        parts += ["", "### Unknown (not counted against GREEN)"]
        for u in unknown[:10]:
            parts.append(f"- {u['detail']}")
    parts += [
        "",
        "---",
        "*Auto-filed by the Board Sentinel (Queue #258) — keeps GitHub `Ready` a "
        "trustworthy execution source. Read-only detection; files/updates only this "
        "one cleanup issue, never bulk-mutates the board. Reproduce with "
        "`POST /api/admin/board-sentinel/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


def severity_for_board(real: list[dict]) -> str:
    """P2 by default (Queue #258 policy). Duplicate fingerprints are the one class
    that actively corrupts the board's trustworthiness, so a duplicate finding
    warrants P1 (with the offender list as its embedded threshold evidence)."""
    if any(f["check"] == "duplicate_fingerprint" for f in real):
        return "P1"
    return "P2"


def file_board_issue(classified: dict, open_issues: list[dict] | None = None) -> dict:
    """RED/GREEN lifecycle for the single board-cleanup issue, via the shared rail
    (Queue #258). UNKNOWN neither files nor closes — we never accuse or falsely
    resolve when we could not measure."""
    from app.tasks.sentinel_filing import reconcile_issue

    fp = board_fingerprint()
    verdict = board_verdict(classified)
    real = classified["real"]

    if verdict == "unknown":
        return {"fingerprint": fp, "action": "unknown_no_op", "verdict": verdict}

    if verdict == "green":
        res = reconcile_issue(
            red=False,
            fingerprint=fp,
            marker_key=_BOARD_MARKER,
            green_comment=(
                f"Board Sentinel re-checked GREEN — 0 board-hygiene defects "
                f"(fingerprint `{fp}`). Auto-closing; a future recurrence opens a "
                f"fresh episode."
            ),
            open_issues=open_issues,
        )
        res["verdict"] = verdict
        return res

    severity = severity_for_board(real)
    labels = ["alert-intake", "needs-agent", "area:admin-ops", f"priority:{severity.lower()}"]
    res = reconcile_issue(
        red=True,
        fingerprint=fp,
        marker_key=_BOARD_MARKER,
        labels=labels,
        title=build_board_issue_title(real),
        body=build_board_issue_body(classified),
        red_comment=(
            f"Board Sentinel re-observed {len(real)} board-hygiene defect(s) "
            f"(fingerprint `{fp}`). Still open."
        ),
        open_issues=open_issues,
    )
    res["verdict"] = verdict
    if res.get("action") == "filed":
        res["severity"] = severity
    return res


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_board_sentinel(
    file_issues: bool = True,
    now=None,
    deadline_seconds: float = 120.0,
) -> dict[str, Any]:
    """Read the board, classify hygiene findings, and (in a live run) file/close the
    single deduped board-cleanup issue. Caches a scorecard to Redis for the cockpit.
    ``now`` is injected for testability (the age math is otherwise wall-clock)."""
    _load_overrides()
    start = _time.monotonic()
    from datetime import datetime as _dt, timezone as _tz

    now = now or _dt.now(_tz.utc)

    issues, columns_available, errors = _fetch_board_state()
    classified = classify_board(
        issues, now, columns_available=columns_available, fetch_errors=errors
    )
    verdict = board_verdict(classified)

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "verdict": verdict,
        "counts": classified["counts"],
        "thresholds": {
            "inbox_triage_hours": INBOX_TRIAGE_HOURS,
            "template_p1_share_cap": TEMPLATE_P1_SHARE_CAP,
            "template_p1_min_population": TEMPLATE_P1_MIN_POPULATION,
        },
        "real": classified["real"],
        "unknown": classified["unknown"],
        "offenders": sorted({
            n for f in classified["real"]
            for n in (f.get("issues") or ([f["issue"]] if f.get("issue") else []))
        }),
        "filed": None,
    }

    if file_issues:
        from app.tasks.sentinel_filing import list_open_alert_issues

        # Reuse one snapshot (the same list already backs _fetch_board_state, but a
        # fresh read here keeps the filing dedup honest even if the board changed).
        stats["filed"] = file_board_issue(classified, open_issues=list_open_alert_issues())

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    stats["generated_at"] = now.isoformat()

    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            "bainluck:board_sentinel:last", 14 * 86400, _json.dumps(stats, default=str)
        )
    except Exception as exc:
        logger.warning("Board sentinel result cache write failed: %s", exc)

    logger.info(
        "Board sentinel (%s): verdict=%s, %d real defect(s), %d unknown in %.1fs",
        stats["mode"], verdict, len(classified["real"]), len(classified["unknown"]),
        stats["duration_seconds"],
    )
    return stats
