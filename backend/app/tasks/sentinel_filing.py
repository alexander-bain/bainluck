"""Shared sentinel filing rail — one fingerprint lifecycle for RED and GREEN.

Queue #258. Every sentinel (Flow / Grid / Board / …) files ONE deduped,
evidence-packed GitHub issue per fingerprint on RED, and — this is the new half —
CLOSES exactly that fingerprint's canonical open issue when the same check
re-observes GREEN. Before Queue #258 the Grid Sentinel still deduped via the
eventually-consistent ``/search/issues`` index, which let 5 copies of the same
fingerprint through (r252 evidence: `286b23d93590` ×5); and no sentinel ever
resolved its own issue on recovery, so the board only ever grew.

The rail centralizes three things so no sentinel re-implements (and re-breaks)
them:

  * ``list_open_alert_issues`` — the strongly-consistent REST list of OPEN
    ``alert-intake`` issues (paginated, degrades to ``[]`` on error). This is the
    dedup source of truth — NOT the flaky search index.
  * ``find_matching_issue`` — pure fingerprint match (body marker, with an
    optional title-prefix fallback), returning the LOWEST matching number so a
    stable canonical issue wins when dupes already exist.
  * ``reconcile_issue`` — the unified RED/GREEN entry: on RED file-or-comment
    (never duplicate); on GREEN comment-and-close the canonical issue (or no-op
    when none is open). A later recurrence opens a new episode cleanly because the
    close path only ever matched OPEN issues.

Filing defaults to ``priority:p2``. A sentinel that wants P1/P0 passes it in its
``labels`` with threshold evidence in the body; the rail NEVER edits the labels of
an existing issue, so a human-prioritized issue is never silently downgraded by a
later P2-default re-observation (it is only commented on).

Read-only against production data — the rail files/updates GitHub metadata only,
never touches market data.
"""

import logging
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# Default labels for a freshly-filed sentinel issue (P2 per Queue #258 policy).
DEFAULT_LABELS = ["alert-intake", "needs-agent", "area:infra", "priority:p2"]


def list_open_alert_issues() -> list[dict]:
    """Fetch OPEN ``alert-intake`` issues via the REST list API (strongly
    consistent, unlike the eventually-consistent /search index that let 5 dupes
    through — r252). Returns ``[]`` on any error / no token so filing degrades
    safely (a missing dedup source must never CAUSE a duplicate — the caller can
    treat an empty list as "search failed" and fall back)."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return []
    issues: list[dict] = []
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        for page in range(1, 6):  # up to 500 open alert-intake issues — ample
            resp = httpx.get(
                f"https://api.github.com/repos/{REPO}/issues",
                headers=headers,
                params={
                    "state": "open",
                    "labels": "alert-intake",
                    "per_page": 100,
                    "page": page,
                },
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                break
            # Drop PRs (the issues endpoint includes them).
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
    except Exception as exc:
        logger.warning("sentinel_filing: open-issue list failed: %s", exc)
        return []
    return issues


def issue_matches(
    issue: dict, fingerprint: str, marker_key: str, title_prefix: str | None = None
) -> bool:
    """True when an OPEN issue is the sentinel's canonical issue for this
    fingerprint. Pure (unit-tested).

    Two match paths:
      * **body marker** — ``{marker_key}:{fingerprint}`` appears in the body (the
        primary key; matched as a plain substring so backticks / the colon can't
        break it, unlike a GitHub quoted-phrase search).
      * **title prefix** (optional) — the title starts with ``title_prefix``. This
        is the fingerprint-equivalent fallback (title ↔ fingerprint are 1:1 within
        a sentinel) that still de-dups an issue whose body marker was edited away.
        Callers OMIT this on the close path so a human-filed lookalike is never
        auto-closed by a title coincidence.
    """
    if not isinstance(issue, dict):
        return False
    body = issue.get("body") or ""
    if f"{marker_key}:{fingerprint}" in body:
        return True
    if title_prefix:
        return str(issue.get("title") or "").startswith(title_prefix)
    return False


def find_matching_issue(
    open_issues: list[dict],
    fingerprint: str,
    marker_key: str,
    title_prefix: str | None = None,
) -> int | None:
    """Pure dedup lookup over a list of open issues → matching issue number.

    Returns the LOWEST matching number so a stable canonical issue wins when
    duplicates already exist (the r252 cleanup: comment/close the oldest, not a
    later dupe)."""
    matches = [
        i["number"]
        for i in (open_issues or [])
        if isinstance(i, dict)
        and i.get("number") is not None
        and issue_matches(i, fingerprint, marker_key, title_prefix)
    ]
    return min(matches) if matches else None


def reconcile_issue(
    *,
    red: bool,
    fingerprint: str,
    marker_key: str,
    labels: list[str] | None = None,
    title: str | None = None,
    body: str | None = None,
    title_prefix: str | None = None,
    red_comment: str | None = None,
    green_comment: str | None = None,
    open_issues: list[dict] | None = None,
    add_to_board: bool = True,
) -> dict:
    """The one fingerprint lifecycle for RED and GREEN.

    * ``red=True``  — file OR comment. Match the fingerprint against OPEN
      ``alert-intake`` issues; if one exists, comment (no duplicate, no label
      edit); else create a new issue (default P2 labels) and add it to the board.
    * ``red=False`` — resolve. If the fingerprint's canonical open issue exists,
      comment a recovery note and CLOSE it; else no-op. The close path matches by
      body marker ONLY (title_prefix is ignored) so a human-filed lookalike is
      never auto-closed.

    ``open_issues`` may be injected (fetched once and reused across many
    fingerprints in one run, and for deterministic tests); when omitted the rail
    fetches the strongly-consistent REST list itself.

    Returns a dict describing the action taken. ``action`` ∈
    {``filed``, ``commented``, ``resolved``, ``green_no_issue``,
    ``skipped_no_token``, ``comment_failed``, ``close_failed``, ``error``}."""
    from app.tasks import bug_report_github as gh

    result: dict[str, Any] = {"fingerprint": fingerprint, "marker": marker_key}

    if not gh.GITHUB_TOKEN:
        result["action"] = "skipped_no_token"
        return result

    if open_issues is None:
        open_issues = list_open_alert_issues()

    if red:
        existing = find_matching_issue(open_issues, fingerprint, marker_key, title_prefix)
        if existing is not None:
            try:
                gh.comment_on_issue(
                    existing,
                    red_comment
                    or f"Sentinel re-observed this failure (fingerprint `{fingerprint}`). Still open.",
                )
            except Exception as exc:
                logger.warning("sentinel_filing: comment failed on #%d: %s", existing, exc)
                result.update(action="comment_failed", issue=existing, error=str(exc)[:200])
                return result
            result.update(action="commented", issue=existing)
            return result

        if not (title and body):
            result.update(action="error", error="missing title/body for a new issue")
            return result
        try:
            number, node_id = gh.create_github_issue(title, body, labels or DEFAULT_LABELS)
        except Exception as exc:
            logger.error("sentinel_filing: issue creation failed (%s): %s", fingerprint, exc)
            result.update(action="error", error=str(exc)[:200])
            return result
        if add_to_board:
            try:
                gh.add_to_project_board(node_id)
            except Exception:
                logger.warning(
                    "sentinel_filing: add issue #%d to board failed (non-fatal)",
                    number,
                    exc_info=True,
                )
        result.update(action="filed", issue=number)
        return result

    # GREEN — resolve the canonical open issue (marker-only match; never title).
    existing = find_matching_issue(open_issues, fingerprint, marker_key, title_prefix=None)
    if existing is None:
        result["action"] = "green_no_issue"
        return result
    try:
        gh.close_issue(
            existing,
            comment=green_comment
            or (
                f"Sentinel re-checked GREEN — this failure is no longer observed "
                f"(fingerprint `{fingerprint}`). Auto-closing; a future recurrence "
                f"opens a fresh episode."
            ),
        )
    except Exception as exc:
        logger.warning("sentinel_filing: close failed on #%d: %s", existing, exc)
        result.update(action="close_failed", issue=existing, error=str(exc)[:200])
        return result
    result.update(action="resolved", issue=existing)
    return result


def reconcile_many(
    items: list[dict],
    *,
    build: Callable[[dict], dict] | None = None,
    open_issues: list[dict] | None = None,
) -> list[dict]:
    """Reconcile a batch of fingerprints against ONE shared open-issue snapshot.

    Each item is a kwargs dict for ``reconcile_issue`` (minus ``open_issues``). The
    open-issue list is fetched once and reused, so a run that files/closes many
    fingerprints makes a single REST-list round-trip. Note: because the snapshot is
    fixed, two items that would file NEW issues for distinct fingerprints are safe,
    but two items resolving/commenting the SAME fingerprint in one batch is a
    caller bug (fingerprints are unique per sentinel check)."""
    if open_issues is None:
        open_issues = list_open_alert_issues()
    out = []
    for it in items:
        kwargs = build(it) if build else dict(it)
        kwargs.setdefault("open_issues", open_issues)
        out.append(reconcile_issue(**kwargs))
    return out
