"""Board Sentinel — RED means the board itself has a real hygiene defect (Queue #258).

The Flow/Grid/Calibration sentinels keep the *product* honest; this one keeps the
*board* honest, so GitHub `Ready` stays a trustworthy execution source. It follows
the same verdict grammar as the Grid Sentinel — classify every candidate as REAL
(an objective, agent-fixable board-hygiene violation) vs UNKNOWN (an API /
rate-limit / auth inability — never GREEN, never a cleanup accusation) — and files
exactly ONE deduped board-cleanup issue when RED, closing it on GREEN through the
shared filing rail (app/tasks/sentinel_filing.py).

Since Queue #265 it measures the WHOLE open Project population (every open issue,
not just ``alert-intake``) so routing invariants hold board-wide. Daily checks (all
target 0 unless noted):
  1. duplicate DECLARED fingerprints among open ``alert-intake`` issues — the exact
     class the shared rail now prevents forward (r252: `286b23d93590` ×5). Only a
     canonical *declaration* (``<marker>:<fp>  (dedupe key …)``) counts as ownership;
     a cleanup/meta issue that merely QUOTES a marker is never a phantom owner.
  2. untriaged issues left in Inbox over 48h (board-wide) — Inbox is temporary
     intake; the >48h bar is itself the fresh-intake exemption.
  3. default/template P1 share among open ``alert-intake`` above a documented cap —
     after Queue #258 sentinels default P2, so a high auto-filed-P1 share is
     template noise to review (never an auto-downgrade — that stays a human call).
  4. parked/blocked issues sitting in Inbox — a blocked card belongs out of intake.
  5. any open issue missing every ``area:*`` label (board-wide, minus a tiny explicit
     meta allowlist) — an un-routed card.
  6. label ↔ Status parity for blocked / parked / needs-user, in both directions.
  7. ``needs-agent`` on a blocked/parked card — it can't be picked up.
  8. any open issue absent from the Project board — an untracked routing defect.
  9. Ready cards that lack an owner signal or are under-scoped.

The column-dependent checks (2, 4, 6, 9) need the Project Status column and the
membership check (8) needs the Project item set, both read via GraphQL. If that read
fails — or the REST/GraphQL pagination truncates, or a duplicate card makes the join
ambiguous — those checks are UNKNOWN (not GREEN): we never assert the board is clean
when we could not measure it.

Read-only against GitHub — the sentinel files/updates its own cleanup issue only;
it performs NO bulk board mutation (Ops owns the one-time cleanup, per Queue #258).
"""

import hashlib
import logging
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
READY_COLUMN = "Ready"
_BOARD_MARKER = "board-sentinel-fingerprint"
# Labels that mean "not active intake" — a card carrying one should not sit in Inbox.
_PARKED_LABELS = {"blocked", "parked", "on-hold"}

# Routing label ↔ Project Status column pairs whose drift is a REAL defect in both
# directions (label present but wrong column; column set but label missing). These
# are the board's canonical routing columns (see docs/github-workflow.md).
_LABEL_COLUMN_PAIRS = (
    ("blocked", "Blocked"),
    ("parked", "Parked"),
    ("needs-user", "Needs User"),
)
# A Ready card must carry one of these ownership signals (or an assignee) — otherwise
# `Ready` is not a trustworthy pick-up queue.
_OWNER_READY_LABELS = {"needs-agent", "owner-ready", "in-progress"}
READY_MIN_BODY_CHARS = 200
# Open issues legitimately allowed to carry no ``area:*`` label — tracking/meta cards
# that route by their epic, not an area. Kept deliberately tiny and explicit.
_AREA_EXEMPT_LABELS = {"epic", "meta", "tracking"}

# The canonical statuses (Project Status column values) a board card may carry —
# the documented routing vocabulary (docs/github-workflow.md). An OPEN Project
# member whose Status is unset OR outside this set is a REAL routing defect: it is on
# the board but in no recognized execution lane (C37 P1, Queue #266 Item 1). When
# Ops adds a column, add it here (and to the workflow doc) in the same change.
_KNOWN_STATUSES = frozenset({
    "Inbox",
    "Ready",
    "In Progress",
    "Needs User",
    "Review / Verify",
    "Blocked",
    "Parked",
    "Done",
})


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


def _declared_fingerprints_in(body: str | None) -> set[tuple[str, str]]:
    """Every ``(marker, fp)`` pair *canonically declared* (owned) by a body.

    Delegates to the ONE shared declaration parser (``sentinel_filing`` — Queue #266
    Item 2) so dedup, recurrence, and close all agree on ownership. A marker QUOTED
    in a cleanup report's evidence table, a Markdown code fence, a blockquote, or an
    indented code block is NOT ownership and is deliberately ignored, so a
    meta/cleanup issue listing another alert's marker does not become a phantom
    duplicate owner (Queue #265 Item 2, hardened by Queue #266)."""
    from app.tasks.sentinel_filing import declared_fingerprints

    return declared_fingerprints(body)


def _labels(issue: dict) -> list[str]:
    return list(issue.get("labels") or [])


def _is_intake(issue: dict) -> bool:
    return "alert-intake" in _labels(issue)


# ---------------------------------------------------------------------------
# Pure checks (unit-tested — operate on normalized issue dicts:
#   {number, title, body, labels:[str], created_at:iso, column:str|None})
# ---------------------------------------------------------------------------
def check_duplicate_fingerprints(issues: list[dict]) -> list[dict]:
    """Same sentinel fingerprint *declared* on ≥2 open alert-intake issues — the
    r252 dupe class the shared rail now prevents forward. Only canonical
    declarations count (a cleanup issue that merely QUOTES a marker is not a second
    owner — Queue #265 Item 2). The board sentinel's OWN marker is excluded (its
    own issue is single-by-construction)."""
    groups: dict[tuple[str, str], set[int]] = {}
    for i in issues:
        if not _is_intake(i):
            continue
        num = i.get("number")
        if num is None:
            continue
        for marker, fp in _declared_fingerprints_in(i.get("body")):
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


def check_stale_inbox(
    issues: list[dict],
    now,
    inbox_first_seen: dict[int, Any] | None = None,
    max_hours: float = INBOX_TRIAGE_HOURS,
) -> list[dict]:
    """Any open issue that has *resided* in Inbox longer than the triage bar (Queue
    #265: board-wide, not just alert-intake — Inbox is temporary intake for
    everything).

    Measures RESIDENCE, not issue age (C37 P2, Queue #266 Item 3): an old issue just
    moved into Inbox is not instantly stale. ``inbox_first_seen`` maps issue number →
    the datetime the sentinel FIRST observed it in Inbox (persisted across runs by
    ``_load_inbox_residence`` and cleared when it leaves). An issue with no recorded
    first-seen (this run is the first trustworthy observation) is given a grace pass.
    The >``max_hours`` bar is itself the exemption for genuinely fresh intake. ``now``
    is injected for testability."""
    inbox_first_seen = inbox_first_seen or {}
    out = []
    for i in issues:
        if i.get("column") != INBOX_COLUMN:
            continue
        num = i.get("number")
        first_seen = inbox_first_seen.get(num)
        if first_seen is None:
            # First trustworthy observation in Inbox → grace (residence unknown yet).
            continue
        residence_h = (now - first_seen).total_seconds() / 3600.0
        if residence_h > max_hours:
            out.append({
                "check": "stale_inbox",
                "issue": num,
                "age_hours": round(residence_h, 1),
                "detail": f"#{num} '{(i.get('title') or '')[:60]}' has resided "
                          f"in Inbox {residence_h:.0f}h (>{max_hours:.0f}h triage bar)",
            })
    return out


def check_missing_status(issues: list[dict], status_missing: set[int] | None) -> list[dict]:
    """Any OPEN Project member whose Status is unset or outside the recognized
    routing vocabulary (``_KNOWN_STATUSES``) — it is on the board but in no execution
    lane, so it is invisible to every board-driven pick-up (C37 P1, Queue #266 Item
    1). ``status_missing`` is the set of such member issue numbers (computed at fetch
    time from the Project read); ``None`` means the Project read failed → UNKNOWN, so
    this check does not run."""
    if not status_missing:
        return []
    by_num = {i.get("number"): i for i in issues}
    out = []
    for num in sorted(status_missing):
        i = by_num.get(num) or {}
        out.append({
            "check": "missing_status",
            "issue": num,
            "detail": f"#{num} '{(i.get('title') or '')[:60]}' is on the Project board "
                      f"but has no recognized Status column — set one so it routes",
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
    """Any open issue carrying no ``area:*`` label (Queue #265: board-wide — every
    open issue must route to an area), excepting a tiny explicit meta allowlist
    (tracking/epic cards that route by their epic). For automation-filed
    alert-intake this is a filing regression; for the rest it is an un-routed card."""
    out = []
    for i in issues:
        labels = _labels(i)
        if _AREA_EXEMPT_LABELS & set(labels):
            continue
        if not any(str(l).startswith("area:") for l in labels):
            scope = "alert-intake " if _is_intake(i) else ""
            out.append({
                "check": "missing_area_label",
                "issue": i.get("number"),
                "detail": f"#{i.get('number')} '{(i.get('title') or '')[:60]}' has no "
                          f"area:* label — assign one so this {scope}card routes",
            })
    return out


def check_label_status_parity(issues: list[dict]) -> list[dict]:
    """Routing label ↔ Project Status drift, in both directions (Queue #265):
      * a card with a ``blocked``/``parked``/``needs-user`` label that is NOT in the
        matching column (except the Inbox+parked case, which ``check_blocked_in_inbox``
        owns, so we don't double-flag); and
      * a card sitting in the ``Blocked``/``Parked``/``Needs User`` column that lacks
        the matching routing label.
    Column-dependent: an issue whose column is unknown is skipped (measured elsewhere
    as UNKNOWN)."""
    out = []
    for i in issues:
        col = i.get("column")
        if not col:
            continue
        labelset = set(_labels(i))
        num = i.get("number")
        title = (i.get("title") or "")[:60]
        for label, column in _LABEL_COLUMN_PAIRS:
            has_label = label in labelset
            in_column = col == column
            if has_label and not in_column:
                # Inbox+blocked/parked is owned by check_blocked_in_inbox — skip so
                # the same card isn't reported twice.
                if col == INBOX_COLUMN and label in _PARKED_LABELS:
                    continue
                out.append({
                    "check": "label_status_parity",
                    "issue": num,
                    "detail": f"#{num} '{title}' carries '{label}' but sits in "
                              f"'{col}' (expected the '{column}' column)",
                })
            elif in_column and not has_label:
                out.append({
                    "check": "label_status_parity",
                    "issue": num,
                    "detail": f"#{num} '{title}' is in the '{column}' column but "
                              f"lacks the '{label}' label",
                })
    return out


def check_needs_agent_conflict(issues: list[dict]) -> list[dict]:
    """``needs-agent`` on a ``blocked``/``parked`` card — a card that can't be
    picked up must not advertise itself as agent-ready (Queue #265). Label-only."""
    out = []
    for i in issues:
        labelset = set(_labels(i))
        if "needs-agent" not in labelset:
            continue
        conflict = {"blocked", "parked"} & labelset
        if conflict:
            out.append({
                "check": "needs_agent_conflict",
                "issue": i.get("number"),
                "detail": f"#{i.get('number')} '{(i.get('title') or '')[:60]}' is "
                          f"{'/'.join(sorted(conflict))} yet still carries "
                          f"needs-agent — clear one so it routes honestly",
            })
    return out


def check_missing_from_project(issues: list[dict], project_numbers: set[int]) -> list[dict]:
    """Open issues absent from the Project board (Queue #265 Item 1) — an untracked
    issue is a REAL routing defect (it is invisible to every board-driven lane).
    Runs only when the Project membership read succeeded (else UNKNOWN)."""
    out = []
    for i in issues:
        num = i.get("number")
        if num is None:
            continue
        if num not in project_numbers:
            out.append({
                "check": "missing_from_project",
                "issue": num,
                "detail": f"#{num} '{(i.get('title') or '')[:60]}' is open but not on "
                          f"the Project board — add it so it routes",
            })
    return out


def check_ready_scoping(issues: list[dict]) -> list[dict]:
    """Ready cards must be scoped and pickable (Queue #265): each carries an
    ownership signal (``needs-agent``/``owner-ready``/``in-progress`` or an assignee)
    AND enough body to execute (>= ``READY_MIN_BODY_CHARS``). Column-dependent."""
    out = []
    for i in issues:
        if i.get("column") != READY_COLUMN:
            continue
        num = i.get("number")
        title = (i.get("title") or "")[:60]
        labelset = set(_labels(i))
        has_owner = bool(_OWNER_READY_LABELS & labelset) or bool(i.get("assignees"))
        if not has_owner:
            out.append({
                "check": "ready_scoping",
                "issue": num,
                "detail": f"#{num} '{title}' is Ready but has no owner signal "
                          f"(needs-agent / owner-ready / in-progress / assignee)",
            })
            continue
        if len(str(i.get("body") or "")) < READY_MIN_BODY_CHARS:
            out.append({
                "check": "ready_scoping",
                "issue": num,
                "detail": f"#{num} '{title}' is Ready but under-scoped "
                          f"(body < {READY_MIN_BODY_CHARS} chars) — add scope/AC "
                          f"before it is picked up",
            })
    return out


# ---------------------------------------------------------------------------
# Classification → verdict. REAL = any objective violation. UNKNOWN = a check
# could not run (no column data / fetch failure). GREEN = everything ran clean.
# ---------------------------------------------------------------------------
def classify_board(
    issues: list[dict],
    now,
    *,
    columns_available: bool,
    project_numbers: set[int] | None = None,
    open_project_items: int | None = None,
    fetch_errors: list[dict] | None = None,
    population_complete: bool = True,
    inbox_first_seen: dict[int, Any] | None = None,
    status_missing: set[int] | None = None,
) -> dict:
    """Run every check and split into real findings + unknown checks. ``now``,
    ``columns_available`` and the Project data are injected so the whole
    classification is a pure, deterministic function of its inputs (fixtures cover
    every branch).

    ``population_complete`` is the TRUST GATE (C37 P1, Queue #266 Item 1): when the
    REST open-issue population is incomplete (a total failure or truncated
    pagination), NO population-derived REAL check runs and NO filing/closing happens
    — the whole run is UNKNOWN. Only a COMPLETE population may RED honestly. (A
    Project/GraphQL read failure with a complete REST population is different: the
    column/membership checks go UNKNOWN, but the label/body checks on the complete
    population may still RED.)

    ``columns_available`` gates the Project-column-dependent checks (stale-inbox,
    blocked-in-inbox, label/status parity, Ready scoping, missing-status).
    ``project_numbers`` (open issue numbers ON the board) gates missing-from-project;
    ``status_missing`` (members with no recognized Status) gates missing-status —
    both ``None``/absent when the read failed → UNKNOWN, never GREEN."""
    fetch_errors = fetch_errors or []
    real: list[dict] = []
    unknown: list[dict] = []

    if not population_complete:
        # The open-issue population itself is incomplete → we cannot trust any
        # population-derived finding (denominators, board-wide routing). Run NO real
        # checks and NO reconciliation; the run is UNKNOWN, never a false RED accusation
        # or a false GREEN (C37 P1 #1).
        unknown.append({
            "check": "population_incomplete",
            "detail": "Open-issue population incomplete (REST read failed or "
                      "truncated) — no board-hygiene check ran (UNKNOWN, not GREEN "
                      "and never a filed accusation)",
        })
        for err in fetch_errors:
            unknown.append({"check": "fetch_error", "detail": err.get("detail", str(err))})
        return {
            "real": [],
            "unknown": unknown,
            "counts": _counts(issues, columns_available, open_project_items,
                              population_complete=False),
        }

    # Label/body-only checks always run (board-wide where applicable) — the
    # population is complete, so these are trustworthy.
    real += check_duplicate_fingerprints(issues)
    real += check_template_p1_share(issues)
    real += check_missing_area_label(issues)
    real += check_needs_agent_conflict(issues)

    # Project-column-dependent checks: REAL when we have column data, else UNKNOWN.
    if columns_available:
        real += check_stale_inbox(issues, now, inbox_first_seen)
        real += check_blocked_in_inbox(issues)
        real += check_label_status_parity(issues)
        real += check_ready_scoping(issues)
    else:
        unknown.append({
            "check": "inbox_column_checks",
            "detail": "Project board column (Status) unavailable — stale-inbox, "
                      "blocked-in-inbox, label/status-parity and Ready-scoping "
                      "checks could not run (UNKNOWN, not GREEN)",
        })

    # Project membership: missing-from-board is REAL only when the membership read
    # succeeded; otherwise it is UNKNOWN so we never falsely assert a clean board.
    if project_numbers is not None:
        real += check_missing_from_project(issues, project_numbers)
        # A member with no recognized Status is a real routing defect — but only when
        # we actually read the Project (else the membership branch already went UNKNOWN).
        real += check_missing_status(issues, status_missing)
    else:
        unknown.append({
            "check": "project_membership",
            "detail": "Project board membership unavailable — missing-from-project "
                      "and missing-status checks could not run (UNKNOWN, not GREEN)",
        })

    for err in fetch_errors:
        unknown.append({"check": "fetch_error", "detail": err.get("detail", str(err))})

    return {
        "real": real,
        "unknown": unknown,
        "counts": _counts(issues, columns_available, open_project_items,
                          population_complete=True),
    }


def _counts(
    issues: list[dict],
    columns_available: bool,
    open_project_items: int | None = None,
    *,
    population_complete: bool = True,
) -> dict:
    intake = [i for i in issues if _is_intake(i)]
    by_column: dict[str, int] | None = None
    if columns_available:
        by_column = {}
        for i in issues:
            col = i.get("column") or "(no column)"
            by_column[col] = by_column.get(col, 0) + 1
    return {
        # ``open_issues_scanned`` is trustworthy only when the population is complete;
        # on an incomplete read it is a partial count (cockpit reads population_complete
        # to distinguish a full count from an unavailable/partial dimension — C37 P1).
        "open_issues_scanned": len(issues),
        "open_alert_intake": len(intake),
        "open_project_items": open_project_items,
        "in_inbox": (by_column or {}).get(INBOX_COLUMN, 0) if columns_available else None,
        "by_column": by_column,
        "columns_available": columns_available,
        "population_complete": population_complete,
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
# Data fetch (GitHub REST + Project GraphQL). Returns (issues, board, errors)
# where board carries columns_available + Project membership. Network-touching —
# tests monkeypatch it or its httpx calls.
# ---------------------------------------------------------------------------
# Page caps sized well past the current board (1,013 items, 2026-07): 40×100 open
# issues and 30×100 Project cards. Reaching the cap with a full final page means the
# read was TRUNCATED → we report it as an error → UNKNOWN, never a false GREEN.
_OPEN_ISSUES_MAX_PAGES = 40
_PROJECT_MAX_PAGES = 30
_PER_PAGE = 100


def _fetch_open_issues(deadline: float | None = None) -> tuple[list[dict], bool, str | None]:
    """Full paginated list of OPEN issues (ALL labels — the whole board population,
    not just alert-intake), for board-wide routing checks.

    Returns ``(issues, ok, error)``. ``ok`` is False on missing token, any REST/HTTP
    failure (incl. rate-limit 403/429 via ``raise_for_status``), TRUNCATED pagination
    (more open issues than the cap), or the inner ``deadline`` (a ``time.monotonic()``
    instant) elapsing mid-pagination — every one of which must go UNKNOWN, never a
    false GREEN. PRs are dropped (the issues endpoint includes them)."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return [], False, "GITHUB_TOKEN unset — cannot read the board"
    issues: list[dict] = []
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    last_full = False
    try:
        for page in range(1, _OPEN_ISSUES_MAX_PAGES + 1):
            if deadline is not None and _time.monotonic() > deadline:
                return issues, False, (
                    f"open-issue read exceeded the inner deadline at page {page} "
                    f"({len(issues)} scanned) — population incomplete"
                )
            resp = httpx.get(
                f"https://api.github.com/repos/{REPO}/issues",
                headers=headers,
                params={"state": "open", "per_page": _PER_PAGE, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                last_full = False
                break
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < _PER_PAGE:
                last_full = False
                break
            last_full = True
    except Exception as exc:
        logger.warning("Board sentinel: open-issue list failed: %s", exc)
        return issues, False, f"open-issue list failed: {str(exc)[:160]}"
    if last_full:
        # We stopped on the cap with a still-full final page → more issues remain.
        return issues, False, (
            f"open-issue pagination truncated at {_OPEN_ISSUES_MAX_PAGES} pages "
            f"({len(issues)} scanned) — population incomplete"
        )
    return issues, True, None


def _fetch_project_items(deadline: float | None = None) -> dict | None:
    """Read the Project board via GraphQL, paginated. Returns a dict:

        {"columns": {issue_number: Status},         # OPEN Bain Luck issues only
         "project_numbers": set[int],               # OPEN issue numbers on the board
         "duplicate_cards": [int, ...],             # issues with >1 card (ambiguous)
         "status_missing": [int, ...],              # members with no recognized Status
         "open_project_items": int}

    or ``None`` on ANY failure so the membership + column-dependent checks go UNKNOWN,
    never GREEN. Returns ``None`` for: missing token/project id; an HTTP/GraphQL
    error; the inner ``deadline`` elapsing; TRUNCATED pagination; or a STRUCTURALLY
    MALFORMED success payload (``node`` not a ProjectV2 object, missing/typed-wrong
    ``items``/``nodes``/``pageInfo``) — a null/absent node must be a typed failure,
    never a "successfully empty board" that would falsely flag every issue as
    missing-from-project (C37 P1 #2). Closed issues, PRs/draft items, and cards from
    OTHER repositories are filtered at the source; the join is by (repository, number)
    so a same-number issue from another repo can never satisfy Bain Luck membership
    or supply its Status (C37 P2)."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, PROJECT_ID, REPO

    if not GITHUB_TOKEN or not PROJECT_ID:
        return None
    query = """
    query($projectId: ID!, $cursor: String) {
      node(id: $projectId) {
        __typename
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              fieldValueByName(name: "Status") {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
              }
              content {
                __typename
                ... on Issue { number state repository { nameWithOwner } }
                ... on PullRequest { number state repository { nameWithOwner } }
              }
            }
          }
        }
      }
    }
    """
    columns: dict[int, str] = {}
    card_counts: dict[int, int] = {}
    project_numbers: set[int] = set()
    cursor = None
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    truncated = True
    try:
        for _ in range(_PROJECT_MAX_PAGES):
            if deadline is not None and _time.monotonic() > deadline:
                logger.warning("Board sentinel: project read exceeded the inner deadline")
                return None
            resp = httpx.post(
                "https://api.github.com/graphql",
                headers=headers,
                json={"query": query, "variables": {"projectId": PROJECT_ID, "cursor": cursor}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or data.get("errors"):
                logger.warning("Board sentinel: GraphQL project read errored: %s",
                               (data.get("errors") if isinstance(data, dict) else data))
                return None
            # Validate the success payload structurally — a null/absent/wrong-typed
            # node|items|nodes|pageInfo is a typed FAILURE (UNKNOWN), never an empty
            # board (C37 P1 #2).
            node = (data.get("data") or {}).get("node")
            if not isinstance(node, dict) or node.get("__typename") != "ProjectV2":
                logger.warning("Board sentinel: GraphQL node is not a ProjectV2 (%r)",
                               type(node).__name__)
                return None
            items = node.get("items")
            if not isinstance(items, dict):
                logger.warning("Board sentinel: GraphQL items block malformed")
                return None
            nodes = items.get("nodes")
            page = items.get("pageInfo")
            if not isinstance(nodes, list) or not isinstance(page, dict):
                logger.warning("Board sentinel: GraphQL nodes/pageInfo malformed")
                return None
            for card in nodes:
                content = (card or {}).get("content") or {}
                # Skip PRs and draft items; count Issues only. ``__typename``/``state``
                # are optional in fixtures → lenient: exclude only when explicitly a PR
                # or explicitly CLOSED.
                if content.get("__typename") == "PullRequest":
                    continue
                if str(content.get("state") or "").upper() == "CLOSED":
                    continue
                # Repository-safe join: only Bain Luck issues count. A repository that
                # is present and NOT the configured REPO is another project's card and
                # is skipped (lenient when absent — fixtures omit it, the real API does
                # not — C37 P2).
                repo = (content.get("repository") or {}).get("nameWithOwner")
                if repo is not None and repo != REPO:
                    continue
                num = content.get("number")
                if num is None:
                    continue
                project_numbers.add(num)
                card_counts[num] = card_counts.get(num, 0) + 1
                status = (card.get("fieldValueByName") or {}).get("name")
                if status:
                    columns[num] = status
            if not page.get("hasNextPage"):
                truncated = False
                break
            cursor = page.get("endCursor")
    except Exception as exc:
        logger.warning("Board sentinel: project item fetch failed: %s", exc)
        return None
    if truncated:
        logger.warning("Board sentinel: project pagination truncated at %d pages", _PROJECT_MAX_PAGES)
        return None
    duplicate_cards = sorted(n for n, c in card_counts.items() if c > 1)
    # A member whose Status is unset or outside the recognized vocabulary is in no
    # execution lane — a REAL routing defect. Duplicate-card members are excluded here
    # (their Status is ambiguous, owned by the duplicate-card UNKNOWN).
    dup_set = set(duplicate_cards)
    status_missing = sorted(
        n for n in project_numbers
        if n not in dup_set and columns.get(n) not in _KNOWN_STATUSES
    )
    return {
        "columns": columns,
        "project_numbers": project_numbers,
        "duplicate_cards": duplicate_cards,
        "status_missing": status_missing,
        "open_project_items": len(project_numbers),
    }


# Back-compat thin wrapper (issue number → Status) — some callers/tests only need
# the column map. Prefer ``_fetch_project_items`` for membership + duplicate data.
def _fetch_project_columns() -> dict[int, str] | None:
    """issue number → Project Status (column). Returns None on any failure."""
    proj = _fetch_project_items()
    return None if proj is None else proj["columns"]


def _fetch_board_state(deadline: float | None = None) -> tuple[list[dict], dict, list[dict]]:
    """Assemble the normalized FULL open-issue population + Project annotations.

    Returns ``(issues, board, errors)`` where ``board`` carries
    ``columns_available``, ``project_numbers`` (set | None), ``open_project_items``
    (int | None), ``status_missing`` (set | None), and ``population_complete`` (bool).

    * A total OR truncated OR deadline-hit REST read makes ``population_complete``
      False — the whole run is UNKNOWN and NO check runs (C37 P1 #1: an incomplete
      population must never file a RED accusation).
    * A Project/GraphQL read failure keeps a COMPLETE REST population but marks
      columns/membership unavailable (→ the column + membership + status checks go
      UNKNOWN, while the label/body checks on the complete population may still RED).
    * Duplicate Project cards make specific joins ambiguous: those issues' columns are
      set to ``None`` (excluded from column-dependent findings) and an UNKNOWN error
      is recorded, but unambiguous label/body findings on the complete population may
      still RED.

    ``deadline`` (a ``time.monotonic()`` instant) bounds both paginators."""
    errors: list[dict] = []
    raw, issues_ok, issues_err = _fetch_open_issues(deadline=deadline)
    population_complete = issues_ok
    if not issues_ok:
        errors.append({"detail": issues_err or "open-issue list failed"})
        if not raw:
            # Nothing to scan at all — pure UNKNOWN; skip the Project read entirely.
            return [], {
                "columns_available": False,
                "project_numbers": None,
                "open_project_items": None,
                "status_missing": None,
                "population_complete": False,
            }, errors

    proj = _fetch_project_items(deadline=deadline)
    columns_available = proj is not None
    dup_set: set[int] = set()
    if proj is None:
        errors.append({"detail": "Project board read failed (GraphQL)"})
        columns: dict[int, str] = {}
        project_numbers: set[int] | None = None
        open_project_items: int | None = None
        status_missing: set[int] | None = None
    else:
        columns = proj["columns"]
        project_numbers = proj["project_numbers"]
        open_project_items = proj["open_project_items"]
        status_missing = set(proj.get("status_missing") or [])
        if proj.get("duplicate_cards"):
            # Duplicate cards make the column join ambiguous for THOSE issues. Exclude
            # them from column-dependent findings (column → None) and record UNKNOWN,
            # so we never falsely flag or clear a double-listed card (C37 P1 #1).
            dup_set = set(proj["duplicate_cards"])
            errors.append({
                "detail": f"Duplicate Project cards for issues {proj['duplicate_cards']} "
                          f"— column join ambiguous",
            })

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
            "assignees": [
                (a.get("login") if isinstance(a, dict) else a)
                for a in (i.get("assignees") or [])
            ],
            "created_at": i.get("created_at"),
            # A duplicate-card issue's column is ambiguous → exclude it from column
            # checks by leaving it None.
            "column": None if num in dup_set else columns.get(num),
        })
    board = {
        "columns_available": columns_available,
        "project_numbers": project_numbers,
        "open_project_items": open_project_items,
        "status_missing": status_missing,
        "population_complete": population_complete,
    }
    return issues, board, errors


# ---------------------------------------------------------------------------
# Inbox residence state (Queue #266 Item 3) — measure time SPENT in Inbox, not
# issue age. Keyed by issue identity in Redis; cleared when an issue leaves Inbox.
# ---------------------------------------------------------------------------
_INBOX_STATE_KEY = "bainluck:board_sentinel:inbox_first_seen"
_INBOX_STATE_TTL = 60 * 86400  # 60 days — well past the 48h triage bar


def _load_inbox_residence(issues: list[dict], now, columns_available: bool) -> dict[int, Any]:
    """Return ``{issue_number: first-seen-in-Inbox datetime}`` for issues CURRENTLY in
    Inbox, persisting/refreshing the durable state as a side effect (C37 P2, Queue
    #266 Item 3).

    First observation of an issue in Inbox records ``now`` (so it gets a grace pass —
    residence ~0 — and an old issue just moved into Inbox is not instantly stale).
    Issues no longer in Inbox are dropped from the state (cleared on exit, so a
    re-entry starts a fresh clock). Degrades to an empty map when columns are
    unavailable (stale-inbox is UNKNOWN then anyway) or Redis is unreachable."""
    if not columns_available:
        return {}
    current = {
        i["number"] for i in issues
        if i.get("column") == INBOX_COLUMN and i.get("number") is not None
    }
    stored: dict[str, str] = {}
    rc = None
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client()
        raw = rc.get(_INBOX_STATE_KEY)
        if raw:
            loaded = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if isinstance(loaded, dict):
                stored = loaded
    except Exception as exc:
        logger.info("Board sentinel: inbox-residence state read failed: %s", exc)

    result: dict[int, Any] = {}
    updated: dict[str, str] = {}
    for num in current:
        prior = _parse_dt(stored.get(str(num)))
        first_seen = prior or now
        result[num] = first_seen
        updated[str(num)] = first_seen.isoformat()

    if rc is not None:
        try:
            import json as _json

            rc.setex(_INBOX_STATE_KEY, _INBOX_STATE_TTL, _json.dumps(updated))
        except Exception as exc:
            logger.info("Board sentinel: inbox-residence state write failed: %s", exc)
    return result


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
        f"**Open issues scanned:** {counts.get('open_issues_scanned')}  ",
        f"**Open Project items:** {counts.get('open_project_items')}  ",
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


def file_board_issue(classified: dict, open_issues=None) -> dict:
    """RED/GREEN lifecycle for the single board-cleanup issue, via the shared rail
    (Queue #258). UNKNOWN neither files nor closes — we never accuse or falsely
    resolve when we could not measure. ``open_issues`` may be a plain list or a typed
    ``OpenIssuesResult`` (a failed dedup read then makes the rail no-op UNKNOWN rather
    than file blind — Queue #266 Item 2)."""
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
def _cache_board_stats(stats: dict) -> None:
    try:
        import json as _json

        from app.tasks.redis_state import get_redis_client

        get_redis_client().setex(
            "bainluck:board_sentinel:last", 14 * 86400, _json.dumps(stats, default=str)
        )
    except Exception as exc:
        logger.warning("Board sentinel result cache write failed: %s", exc)


async def _run_board_sentinel(
    file_issues: bool = True,
    now=None,
    deadline_seconds: float = 120.0,
) -> dict[str, Any]:
    """Read the board, classify hygiene findings, and (in a live run) file/close the
    single deduped board-cleanup issue. Caches a scorecard to Redis for the cockpit.
    ``now`` is injected for testability (the age math is otherwise wall-clock).

    The board read runs in a worker thread bounded by an INNER ``deadline_seconds``
    budget (default 120s, well under the 840/900s Celery limits and short enough that
    the inline admin route never blocks unbounded — C37 P2, Queue #266 Item 3). Both
    paginators also self-check the same monotonic deadline. On timeout the run caches
    an honest UNKNOWN and performs NO reconciliation."""
    import asyncio

    _load_overrides()
    start = _time.monotonic()
    deadline_mono = start + deadline_seconds
    from datetime import datetime as _dt, timezone as _tz

    now = now or _dt.now(_tz.utc)
    mode = "live" if file_issues else "detect_only"

    try:
        issues, board, errors = await asyncio.wait_for(
            asyncio.to_thread(_fetch_board_state, deadline_mono),
            timeout=deadline_seconds,
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("Board sentinel: board read exceeded the %ss inner budget", deadline_seconds)
        stats = {
            "mode": mode,
            "verdict": "unknown",
            "counts": {"population_complete": False, "columns_available": False},
            "thresholds": {
                "inbox_triage_hours": INBOX_TRIAGE_HOURS,
                "template_p1_share_cap": TEMPLATE_P1_SHARE_CAP,
                "template_p1_min_population": TEMPLATE_P1_MIN_POPULATION,
            },
            "real": [],
            "unknown": [{
                "check": "deadline_exceeded",
                "detail": f"board read exceeded the {deadline_seconds:.0f}s inner budget "
                          f"— cached UNKNOWN, no reconciliation (never a false GREEN/RED)",
            }],
            "offenders": [],
            "filed": None,
            "duration_seconds": round(_time.monotonic() - start, 1),
            "generated_at": now.isoformat(),
        }
        _cache_board_stats(stats)
        return stats

    inbox_first_seen = _load_inbox_residence(
        issues, now, board.get("columns_available", False)
    )
    classified = classify_board(
        issues,
        now,
        columns_available=board.get("columns_available", False),
        project_numbers=board.get("project_numbers"),
        open_project_items=board.get("open_project_items"),
        fetch_errors=errors,
        population_complete=board.get("population_complete", True),
        inbox_first_seen=inbox_first_seen,
        status_missing=board.get("status_missing"),
    )
    verdict = board_verdict(classified)

    stats: dict[str, Any] = {
        "mode": mode,
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
        from app.tasks.sentinel_filing import fetch_open_alert_issues

        # A fresh TYPED read keeps the filing dedup honest even if the board changed —
        # and a failed read makes the rail no-op UNKNOWN instead of filing blind.
        stats["filed"] = file_board_issue(classified, open_issues=fetch_open_alert_issues())

    stats["duration_seconds"] = round(_time.monotonic() - start, 1)
    stats["generated_at"] = now.isoformat()
    _cache_board_stats(stats)

    logger.info(
        "Board sentinel (%s): verdict=%s, %d real defect(s), %d unknown in %.1fs",
        stats["mode"], verdict, len(classified["real"]), len(classified["unknown"]),
        stats["duration_seconds"],
    )
    return stats
