"""Admin on-demand issue filing — the cockpit "File this" one-tap rail.

L2-142 Item 1/3: turns a red/amber cockpit tile or a System Diagnosis blurb
into a real filed GitHub issue via the SAME rail the sentinels use
(`app.tasks.bug_report_github`). Deduped by a stable fingerprint embedded in the
body so a repeat tap comments on the open issue instead of creating a duplicate.
The read-side surfaces (AdminCockpit, DiagnosisCard) call this and flip from
"File this" to "filed #N → handled" — RED becomes a state that resolves itself
in front of Alex.

Kept in its OWN route file (not admin_cockpit.py, which is read-only) so the
one on-demand write endpoint stays isolated from the cockpit payload builder.
"""

import hashlib
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.routes.admin_utils import _check_admin_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin File Issue"])

# The dedup marker embedded in every filed body. Matches the sentinels' pattern
# (flow-sentinel-fingerprint / grid, etc.) so cockpit-filed issues are searchable
# and never double-file on a repeat tap.
_FINGERPRINT_MARKER = "cockpit-file-fingerprint"
_GH_ISSUE_URL = "https://github.com/alexander-bain/bainluck/issues/{}"

# Map the two severity vocabularies the cockpit uses (watchdog P0..P3, LLM
# diagnosis critical/warning/info) onto a priority label.
_SEVERITY_TO_PRIORITY = {
    "p0": "priority:p0",
    "p1": "priority:p1",
    "p2": "priority:p2",
    "p3": "priority:p3",
    "critical": "priority:p1",
    "warning": "priority:p2",
    "info": "priority:p3",
}


class FileIssueRequest(BaseModel):
    # Where the tap came from — part of the dedup key so the same signal filed
    # from two surfaces still collapses to one issue.
    source: str
    # A stable identifier for the underlying signal (tile key, check name,
    # diagnosis title). source|key is the fingerprint.
    key: str
    title: str
    body: str = ""
    severity: str | None = None
    labels: list[str] = []


def _fingerprint(source: str, key: str) -> str:
    raw = f"{source}|{key}".strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _find_open_issue_by_fingerprint(fingerprint: str) -> int | None:
    """Search open issues for a prior filing of this fingerprint (dedup)."""
    import httpx

    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return None
    q = f'repo:{REPO} in:body "{_FINGERPRINT_MARKER}:{fingerprint}" state:open'
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
        logger.warning("cockpit file-issue dedup search failed for %s: %s", fingerprint, exc)
        return None


@router.post("/file-issue")
def file_issue(
    request: Request,
    body: FileIssueRequest,
    secret: str = Query(None),
):
    """File (or comment on the existing) GitHub issue for a cockpit signal.

    Sync def on purpose: the rail (`bug_report_github`) uses blocking httpx, so
    FastAPI runs this in its threadpool rather than on the event loop.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.bug_report_github import (
        GITHUB_TOKEN,
        add_to_project_board,
        comment_on_issue,
        create_github_issue,
    )

    if not GITHUB_TOKEN:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN not configured — rail unavailable")

    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    fp = _fingerprint(body.source, body.key)

    # Dedup: if this signal already has an open issue, comment and return it
    # rather than filing a second one.
    existing = _find_open_issue_by_fingerprint(fp)
    if existing:
        try:
            comment_on_issue(
                existing,
                f"Re-filed from the Alex cockpit ({body.source}). Still open. "
                f"(`{_FINGERPRINT_MARKER}:{fp}`)",
            )
        except Exception:
            logger.warning("cockpit file-issue: comment on #%d failed (non-fatal)", existing, exc_info=True)
        return {
            "status": "exists",
            "issue": existing,
            "url": _GH_ISSUE_URL.format(existing),
            "fingerprint": fp,
        }

    labels = ["alert-intake", "needs-agent"]
    prio = _SEVERITY_TO_PRIORITY.get((body.severity or "").strip().lower())
    if prio:
        labels.append(prio)
    for lbl in body.labels:
        if lbl and lbl not in labels:
            labels.append(lbl)

    full_body = (body.body or "").strip()
    full_body += (
        f"\n\n---\n*Filed one-tap from the Alex cockpit ({body.source}).*"
        f"\n`{_FINGERPRINT_MARKER}:{fp}`"
    )

    try:
        number, node_id = create_github_issue(title, full_body, labels)
    except Exception as exc:
        logger.error("cockpit file-issue creation failed (%s): %s", fp, exc)
        raise HTTPException(status_code=502, detail=f"issue creation failed: {str(exc)[:200]}")

    try:
        add_to_project_board(node_id)
    except Exception:
        logger.warning("cockpit file-issue: add #%d to board failed (non-fatal)", number, exc_info=True)

    return {
        "status": "filed",
        "issue": number,
        "url": _GH_ISSUE_URL.format(number),
        "fingerprint": fp,
    }
