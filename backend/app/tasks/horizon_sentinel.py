"""Horizon Sentinel — the marquee-event early-warning sentinel (Queue #223 Item 1).

A marquee event should never arrive without a page. The Open and the World Cup
both went live in a top slot with no unified surface because nobody was watching
the horizon. This sentinel is that watcher: it reads THE HORIZON CALENDAR
(``app/config/majors_calendar.yaml`` — every knowable major through 2030) every
day and escalates as each event nears:

  T-30  (0 <= days_to_start <= 30)  -> candidate            (info / P3)
  T-14  (0 <= days_to_start <= 14)  -> needs-page            (P1 marquee / P2)
  T-7   (0 <= days_to_start <=  7)  -> marquee escalation    (P1 marquee / P2)
  in progress (start <= today <= end) AND no page -> IN-PROGRESS-WITHOUT-PAGE (P0)

"Has a page" is resolved against the LIVE event-concept surface
(``GET /api/event/{concept_key}``): a real page returns a non-empty primary
field or sections/children; a 404 / empty envelope means no page. Only entries
that carry a ``concept_key`` (the ones whose expected surface is a concept page)
are page-checked and filed; ``concept_key: null`` entries (plain events / brackets
with no concept adapter yet) are tracked in the scorecard as ``surface_tbd`` but
never filed — the sentinel cries wolf on nothing.

Modeled on the Flow/Grid sentinels: same mine -> evidence-pack -> auto-file rail
(``bug_report_github``), same fingerprint dedup, same Redis scorecard, same admin
``run``/``last`` pair. Read-only against production — it files work, never data.
"""

import hashlib
import logging
import os
import time as _time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HORIZON_SENTINEL_API = os.environ.get(
    "HORIZON_SENTINEL_API", os.environ.get("FLOW_SENTINEL_API", "https://api.bainluck.com")
)
HTTP_TIMEOUT = 20.0

# Escalation window edges, in days-to-start.
T30_DAYS = 30
T14_DAYS = 14
T7_DAYS = 7

# All horizon findings are page/coverage gaps.
_AREA_LABEL = "area:event-details"


# ---------------------------------------------------------------------------
# Calendar loading (pure, defensive)
# ---------------------------------------------------------------------------
def load_calendar(path: str | Path | None = None) -> list[dict]:
    """Load and normalize the majors calendar (delegates to the shared util so the
    sentinel and the feed's marquee-pin pass read one parser + one file). Returns []
    on any failure so the sentinel degrades to a no-op rather than crashing the beat."""
    from app.utils.majors_calendar import load_calendar as _load

    return _load(path)


def _parse_date(v: Any) -> date | None:
    """Accept a YAML date, a datetime, or an ISO string."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return datetime.strptime(v[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return None


def days_to_start(entry: dict, today: date) -> int | None:
    start = _parse_date(entry.get("start"))
    if start is None:
        return None
    return (start - today).days


# ---------------------------------------------------------------------------
# Phase + severity classification (pure)
# ---------------------------------------------------------------------------
def horizon_phase(entry: dict, today: date) -> str:
    """One of: in_progress | t7 | t14 | t30 | future | past.

    in_progress wins over the T-buckets: an event whose window contains today is
    live regardless of how its start compares. past = window fully behind us.
    """
    start = _parse_date(entry.get("start"))
    end = _parse_date(entry.get("end")) or start
    if start is None:
        return "future"
    if start <= today <= (end or start):
        return "in_progress"
    if today > (end or start):
        return "past"
    d = (start - today).days  # start is in the future here
    if d <= T7_DAYS:
        return "t7"
    if d <= T14_DAYS:
        return "t14"
    if d <= T30_DAYS:
        return "t30"
    return "future"


def severity_for(entry: dict, phase: str) -> str | None:
    """Priority for a phase when the page is MISSING. None => no finding filed."""
    marquee = bool(entry.get("marquee"))
    if phase == "in_progress":
        return "p0" if marquee else "p1"  # in-progress-without-page is the worst class
    if phase in ("t7", "t14"):
        return "p1" if marquee else "p2"
    if phase == "t30":
        return "p3"
    return None


_PHASE_LABEL = {
    "in_progress": "IN PROGRESS — no page",
    "t7": "T-7 marquee escalation — no page",
    "t14": "T-14 needs-page",
    "t30": "T-30 candidate",
}


def classify_entry(entry: dict, today: date, has_page: bool) -> dict | None:
    """Pure finding builder. Returns a finding dict when the entry is inside a
    filing window and lacks a live page; None when covered, out of window, or the
    phase is not a filing phase."""
    phase = horizon_phase(entry, today)
    if phase in ("future", "past"):
        return None
    if has_page:
        return None  # covered — the sentinel is green for this entry
    sev = severity_for(entry, phase)
    if sev is None:
        return None
    d = days_to_start(entry, today)
    when = (
        "in progress now"
        if phase == "in_progress"
        else (f"starts in {d} day(s)" if d is not None else "date unknown")
    )
    detail = (
        f"{entry.get('name')} ({_PHASE_LABEL.get(phase, phase)}) — {when}, "
        f"but no live page resolves at concept_key `{entry.get('concept_key')}`. "
        f"Expected surface: {entry.get('archetype') or 'event page'}"
        + (" (marquee — pin atop feed once built)." if entry.get("marquee") else ".")
    )
    return {
        "slug": entry.get("slug"),
        "name": entry.get("name"),
        "concept_key": entry.get("concept_key"),
        "domain": entry.get("domain"),
        "archetype": entry.get("archetype"),
        "marquee": bool(entry.get("marquee")),
        "phase": phase,
        "severity": sev,
        "days_to_start": d,
        "start": str(entry.get("start")),
        "end": str(entry.get("end")),
        "date_confidence": entry.get("date_confidence"),
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Fingerprint + issue rendering
# ---------------------------------------------------------------------------
def horizon_fingerprint(slug: str) -> str:
    """One issue per calendar entry (by slug); the phase escalates in-place via
    comments so a single issue tracks candidate -> needs-page -> P0."""
    return hashlib.sha1(f"horizon:{slug}".encode("utf-8")).hexdigest()[:12]


def build_horizon_issue_title(finding: dict) -> str:
    tag = "P0 " if finding["severity"] == "p0" else ""
    title = f"[Horizon] {tag}{finding['name']} — {_PHASE_LABEL.get(finding['phase'], finding['phase'])}"
    return title[:256]


def build_horizon_issue_body(finding: dict) -> str:
    fp = horizon_fingerprint(finding["slug"])
    parts = [
        "## Horizon Sentinel finding",
        "",
        f"`horizon-sentinel-fingerprint:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Event:** {finding['name']}  ",
        f"**Phase:** `{finding['phase']}` — {_PHASE_LABEL.get(finding['phase'], finding['phase'])}  ",
        f"**Severity:** `{finding['severity'].upper()}`  ",
        f"**Window:** {finding['start']} → {finding['end']}"
        + (f"  (starts in {finding['days_to_start']}d)" if finding.get("days_to_start") is not None else "")
        + "  ",
        f"**Expected surface:** {finding['archetype']} at `{finding['concept_key']}` "
        f"(domain `{finding['domain']}`)  ",
        f"**Marquee:** {'yes — pin atop feed once built' if finding['marquee'] else 'no'}  ",
        f"**Date confidence:** {finding.get('date_confidence') or 'n/a'}  ",
        f"**Checked against:** {HORIZON_SENTINEL_API}",
        "",
        "### What to build",
        f"- {finding['detail']}",
        "- Ship the event-concept surface so `GET /api/event/"
        f"{finding['concept_key']}` returns a real page (winner field / bracket / "
        "props as appropriate), wire search + breadcrumbs, and — if marquee — "
        "confirm it pins atop the sports feed while live.",
        "",
        "---",
        "*Auto-filed by the Horizon Sentinel (Queue #223) — the marquee-event "
        "early-warning. Read-only detection; it files work, never data. Reproduce "
        "with `POST /api/admin/horizon-sentinel/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Filing + dedup (reuses the bug_report_github rail, per the flow/grid sentinels)
# ---------------------------------------------------------------------------
def _find_open_issue_by_fingerprint(fingerprint: str) -> int | None:
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "horizon-sentinel-fingerprint:{fingerprint}" state:open'
    try:
        resp = httpx.get(
            "https://api.github.com/search/issues",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"q": q},
            timeout=30,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return items[0]["number"] if items else None
    except Exception as exc:
        logger.warning("Horizon sentinel dedup search failed for %s: %s", fingerprint, exc)
        return None


def file_horizon_issue(finding: dict) -> dict:
    """File OR update one issue per calendar-entry fingerprint (escalating phase)."""
    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    slug = finding["slug"]
    fp = horizon_fingerprint(slug)
    if not GITHUB_TOKEN:
        return {"slug": slug, "fingerprint": fp, "action": "skipped_no_token"}

    existing = _find_open_issue_by_fingerprint(fp)
    if existing:
        try:
            comment_on_issue(
                existing,
                f"Horizon Sentinel re-observed: **{finding['name']}** is now in phase "
                f"`{finding['phase']}` ({finding['severity'].upper()}) — still no page "
                f"at `{finding['concept_key']}` (fingerprint `{fp}`).",
            )
        except Exception as exc:
            logger.warning("Horizon sentinel comment failed on #%d: %s", existing, exc)
        return {"slug": slug, "fingerprint": fp, "action": "commented", "issue": existing}

    labels = [
        "alert-intake",
        "needs-agent",
        _AREA_LABEL,
        f"priority:{finding['severity']}",
    ]
    title = build_horizon_issue_title(finding)
    body = build_horizon_issue_body(finding)
    try:
        number, node_id = create_github_issue(title, body, labels)
    except Exception as exc:
        logger.error("Horizon sentinel issue creation failed (%s): %s", fp, exc)
        return {"slug": slug, "fingerprint": fp, "action": "error", "error": str(exc)[:200]}
    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("Horizon sentinel: add issue #%d to board failed (non-fatal)", number, exc_info=True)
    return {"slug": slug, "fingerprint": fp, "action": "filed", "issue": number, "severity": finding["severity"]}


# ---------------------------------------------------------------------------
# Page-existence probe (live event-concept surface)
# ---------------------------------------------------------------------------
async def _check_page_exists(client: httpx.AsyncClient, concept_key: str) -> bool:
    """A page exists when GET /api/event/{key} returns 200 with real content —
    a non-empty primary competitor list OR non-empty sections/children. A 404,
    error, or hollow envelope (adapter registered but no data) counts as no page."""
    try:
        resp = await client.get(f"{HORIZON_SENTINEL_API}/api/event/{concept_key}")
    except Exception as exc:
        logger.info("Horizon page-check request failed for %s: %s", concept_key, exc)
        return False
    if resp.status_code != 200:
        return False
    try:
        data = resp.json()
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    primary = data.get("primary") or {}
    competitors = primary.get("competitors") or []
    sections = data.get("sections") or []
    children = data.get("children") or []
    return bool(competitors or sections or children)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
async def _run_horizon_sentinel(
    file_issues: bool = True,
    deadline_seconds: float = 180.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Walk the calendar, page-check every in-window concept, file one deduped
    issue per uncovered marquee/major, and cache a scorecard to Redis."""
    start_mono = _time.monotonic()
    today = (now or datetime.now(timezone.utc)).date()
    entries = load_calendar()

    findings: list[dict] = []
    surface_tbd: list[dict] = []
    covered: list[dict] = []
    checked = 0

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for entry in entries:
            phase = horizon_phase(entry, today)
            if phase in ("future", "past"):
                continue
            ck = entry.get("concept_key")
            if not ck:
                # Plain event / bracket with no concept adapter yet — track, don't file.
                surface_tbd.append(
                    {
                        "slug": entry.get("slug"),
                        "name": entry.get("name"),
                        "phase": phase,
                        "days_to_start": days_to_start(entry, today),
                        "reason": "no concept_key — surface is a plain event/bracket (adapter TBD)",
                    }
                )
                continue
            if _time.monotonic() - start_mono > deadline_seconds:
                logger.warning("Horizon sentinel: deadline hit, %d entries unchecked", len(entries))
                break
            has_page = await _check_page_exists(client, ck)
            checked += 1
            finding = classify_entry(entry, today, has_page)
            if finding:
                findings.append(finding)
            elif has_page:
                covered.append({"slug": entry.get("slug"), "name": entry.get("name"), "phase": phase})

    filed: list[dict] = []
    if file_issues:
        for f in findings:
            filed.append(file_horizon_issue(f))

    stats: dict[str, Any] = {
        "mode": "live" if file_issues else "detect_only",
        "api": HORIZON_SENTINEL_API,
        "as_of": today.isoformat(),
        "calendar_entries": len(entries),
        "in_window_checked": checked,
        "findings": findings,
        "n_findings": len(findings),
        "p0": [f for f in findings if f["severity"] == "p0"],
        "covered": covered,
        "surface_tbd": surface_tbd,
        "filed": filed,
        "duration_s": round(_time.monotonic() - start_mono, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Queue 298 (#1512): durable row first, Redis as the accelerator.
    from app.services.durable_snapshots import publish_sentinel_evidence
    from app.utils.durable_state import evaluate_publication

    stages = await publish_sentinel_evidence(
        identity="sentinel:horizon",
        redis_key="bainluck:horizon_sentinel:last",
        stats=stats,
        source="horizon_sentinel",
    )
    stats["persistence"] = stages
    evaluate_publication(
        compute_complete=True,
        durable_write="ok" if stages["durable"] in ("ok", "superseded") else "error",
        volatile_write=stages.get("volatile", "not_attempted"),
        stages=stages,
    ).raise_if_failed("horizon sentinel evidence")

    return stats
