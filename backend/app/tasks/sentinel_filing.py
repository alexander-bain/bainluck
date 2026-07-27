"""Shared sentinel filing rail — one fingerprint lifecycle for RED and GREEN.

Queue #258 (hardened by Queue #266). Every sentinel (Flow / Grid / Board / …)
files ONE deduped, evidence-packed GitHub issue per fingerprint on RED, and —
this is the new half — CLOSES exactly that fingerprint's canonical open issue when
the same check re-observes GREEN. Before Queue #258 the Grid Sentinel still deduped
via the eventually-consistent ``/search/issues`` index, which let 5 copies of the
same fingerprint through (r252 evidence: `286b23d93590` ×5); and no sentinel ever
resolved its own issue on recovery, so the board only ever grew.

The rail centralizes these so no sentinel re-implements (and re-breaks) them:

  * ``fetch_open_alert_issues`` — the strongly-consistent REST list of OPEN
    ``alert-intake`` issues (paginated) as a TYPED result (``OpenIssuesResult``):
    ``ok``/``issues``/``error``/``truncated``. This is the dedup source of truth —
    NOT the flaky search index. A failed or truncated read is ``ok=False`` and is
    NEVER indistinguishable from "genuinely empty" (C37 P1 — the empty-list-means-
    both bug that could file a duplicate during a second REST fault).
    ``list_open_alert_issues`` is kept as a thin back-compat list wrapper.
  * ``declared_fingerprints`` — the ONE canonical declaration parser. A fingerprint
    is *owned* by a body only when its ``<marker>:<fp>  (dedupe key …)`` declaration
    appears on a real line — NOT inside a fenced code block, a blockquote, an
    indented code block, or a Markdown table. A cleanup/meta issue that merely
    QUOTES another alert's marker (even a full copied declaration inside a table or
    code fence) is never a phantom owner (C37 P1/P2). Used by dedup, recurrence, and
    close alike.
  * ``find_matching_issue`` — pure fingerprint match (declaration marker, with an
    optional title-prefix fallback for RED dedup only), returning the LOWEST
    matching number so a stable canonical issue wins when dupes already exist.
  * ``reconcile_issue`` — the unified RED/GREEN entry: on RED file-or-comment
    (never duplicate); on GREEN comment-and-close the canonical issue (or no-op
    when none is open). When the dedup source cannot be read it performs an explicit
    UNKNOWN no-op (``dedup_unknown_no_op``) — it never files or closes blind. Create
    is serialized per fingerprint with a Redis idempotency claim plus a final
    re-read so a beat+manual overlap cannot file the same fingerprint twice.

Filing defaults to ``priority:p2``. A sentinel that wants P1/P0 passes it in its
``labels`` with threshold evidence in the body; the rail NEVER edits the labels of
an existing issue, so a human-prioritized issue is never silently downgraded by a
later P2-default re-observation (it is only commented on).

Read-only against production data — the rail files/updates GitHub metadata only,
never touches market data.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

# Default labels for a freshly-filed sentinel issue (P2 per Queue #258 policy).
DEFAULT_LABELS = ["alert-intake", "needs-agent", "area:infra", "priority:p2"]

# Pagination cap for the open ``alert-intake`` list. Reaching the cap on a still-full
# final page means the read is TRUNCATED → ``ok=False`` (UNKNOWN), never a false
# "empty" that could let a duplicate through.
_ALERT_LIST_MAX_PAGES = 5
_PER_PAGE = 100

# One canonical DECLARATION marker: ``<marker>:<fp>`` (optionally in backticks)
# immediately followed by the ``(dedupe key …)`` annotation every sentinel writes.
_DECLARED_FINGERPRINT_RE = re.compile(
    r"`?([a-z][a-z0-9-]*-fingerprint):([0-9a-f]{6,40})`?\s*\(dedupe key",
)


@dataclass
class OpenIssuesResult:
    """Typed result of the open-issue dedup-source read. ``ok=False`` means the
    canonical population could NOT be trusted (missing token, HTTP/rate-limit
    failure, or truncated pagination) — distinct from ``ok=True`` with an empty
    ``issues`` (the board genuinely has no open alert-intake issues). Reconciliation
    must no-op on ``ok=False`` and never treat it as "no existing issue"."""

    ok: bool
    issues: list[dict] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False


def fetch_open_alert_issues() -> OpenIssuesResult:
    """Fetch OPEN ``alert-intake`` issues via the REST list API (strongly
    consistent, unlike the eventually-consistent /search index that let 5 dupes
    through — r252). Returns a TYPED ``OpenIssuesResult`` so a failed/truncated read
    (``ok=False``) is never confused with a genuinely empty board (``ok=True``,
    ``issues=[]``) — the C37 P1 "empty list means both" bug that could file a
    duplicate during a second REST fault."""
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    if not GITHUB_TOKEN:
        return OpenIssuesResult(ok=False, error="GITHUB_TOKEN unset — cannot read the open-issue list")
    issues: list[dict] = []
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    last_full = False
    try:
        for page in range(1, _ALERT_LIST_MAX_PAGES + 1):
            resp = httpx.get(
                f"https://api.github.com/repos/{REPO}/issues",
                headers=headers,
                params={
                    "state": "open",
                    "labels": "alert-intake",
                    "per_page": _PER_PAGE,
                    "page": page,
                },
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list) or not batch:
                last_full = False
                break
            # Drop PRs (the issues endpoint includes them).
            issues.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < _PER_PAGE:
                last_full = False
                break
            last_full = True
    except Exception as exc:
        logger.warning("sentinel_filing: open-issue list failed: %s", exc)
        return OpenIssuesResult(ok=False, issues=issues, error=f"open-issue list failed: {str(exc)[:160]}")
    if last_full:
        # Stopped on the cap with a still-full final page → more issues remain →
        # the dedup population is incomplete → UNKNOWN, never a false empty.
        return OpenIssuesResult(
            ok=False,
            issues=issues,
            truncated=True,
            error=f"open alert-intake list truncated at {_ALERT_LIST_MAX_PAGES} pages ({len(issues)} scanned)",
        )
    return OpenIssuesResult(ok=True, issues=issues)


def list_open_alert_issues() -> list[dict]:
    """Back-compat list wrapper over ``fetch_open_alert_issues``. Returns the issue
    list (possibly a partial one on a failed read). Prefer ``fetch_open_alert_issues``
    for the typed ok/error/truncated signal — a bare ``[]`` here cannot distinguish
    "genuinely empty" from "read failed", which is exactly why reconciliation now
    consumes the typed result instead."""
    return fetch_open_alert_issues().issues


def declared_fingerprints(body: str | None) -> set[tuple[str, str]]:
    """Every ``(marker, fp)`` pair *canonically declared* (owned) by a body.

    A declaration is a line that (a) matches ``<marker>:<fp>`` immediately followed
    by the ``(dedupe key …)`` annotation every sentinel writes, AND (b) is NOT inside
    a fenced code block, a blockquote (``>``), an indented code block (4+ spaces / a
    tab), or a Markdown table row (``|``). A marker QUOTED in a cleanup report's
    evidence — even a full copied declaration inside a code fence, blockquote, or
    table — is deliberately ignored, so a meta/cleanup issue that lists another
    alert's marker never becomes a phantom owner for dedup or auto-close (C37
    P1/P2, Queue #266 Item 2). This is the ONE parser shared by dedup, recurrence,
    and close."""
    out: set[tuple[str, str]] = set()
    in_fence = False
    for raw_line in (body or "").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):  # blockquote — a quote, not ownership
            continue
        if raw_line.startswith("    ") or raw_line.startswith("\t"):  # indented code
            continue
        if stripped.startswith("|"):  # table row — evidence, not ownership
            continue
        for m in _DECLARED_FINGERPRINT_RE.finditer(raw_line):
            out.add((m.group(1), m.group(2)))
    return out


def issue_matches(
    issue: dict, fingerprint: str, marker_key: str, title_prefix: str | None = None
) -> bool:
    """True when an OPEN issue is the sentinel's canonical issue for this
    fingerprint. Pure (unit-tested).

    Two match paths:
      * **canonical declaration** — ``(marker_key, fingerprint)`` is DECLARED in the
        body (the primary key; parsed by ``declared_fingerprints`` so a quoted /
        code-fenced / tabled marker is never a match — C37 P1/P2). This is the ONLY
        path used on close.
      * **title prefix** (optional, RED dedup only) — the title starts with
        ``title_prefix``. This is the fingerprint-equivalent fallback (title ↔
        fingerprint are 1:1 within a sentinel) that still de-dups an issue whose body
        declaration was edited away. Callers OMIT this on the close path so a
        human-filed lookalike is never auto-closed by a title coincidence.
    """
    if not isinstance(issue, dict):
        return False
    if (marker_key, fingerprint) in declared_fingerprints(issue.get("body")):
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


# ---------------------------------------------------------------------------
# Per-fingerprint create serialization (Redis idempotency claim).
# ---------------------------------------------------------------------------
_FILING_CLAIM_TTL = 300  # seconds — long enough to cover a create round-trip


def _claim_fingerprint(marker_key: str, fingerprint: str) -> str:
    """Atomically claim the right to CREATE this fingerprint's issue.

    Returns ``"won"`` (this run holds the claim → it may create), ``"lost"`` (another
    concurrent run already holds it → we must NOT create), or ``"no_redis"`` (Redis
    unavailable → degrade to unlocked, proceed). A SET NX EX makes two overlapping
    RED runs (beat + manual) serialize so only one files (C37 P2)."""
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(fast_fail=True)
        key = f"sentinel:filing:claim:{marker_key}:{fingerprint}"
        got = rc.set(key, "1", nx=True, ex=_FILING_CLAIM_TTL)
    except Exception:
        return "no_redis"
    return "won" if got else "lost"


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
    open_issues: "list[dict] | OpenIssuesResult | None" = None,
    add_to_board: bool = True,
) -> dict:
    """The one fingerprint lifecycle for RED and GREEN.

    * ``red=True``  — file OR comment. Match the fingerprint against OPEN
      ``alert-intake`` issues; if one exists, comment (no duplicate, no label
      edit); else create a new issue (default P2 labels) and add it to the board.
      Create is serialized per fingerprint (Redis claim + final re-read) so a
      beat+manual overlap cannot both file.
    * ``red=False`` — resolve. If the fingerprint's canonical open issue exists,
      comment a recovery note and CLOSE it; else no-op. The close path matches by
      canonical body declaration ONLY (title_prefix is ignored) so a human-filed /
      quoting lookalike is never auto-closed.

    ``open_issues`` may be:
      * an ``OpenIssuesResult`` (preferred) — a failed/truncated read (``ok=False``)
        makes the whole call an explicit ``dedup_unknown_no_op`` (no file, no close);
      * a plain ``list`` (back-compat) — trusted as a complete snapshot;
      * ``None`` — the rail fetches the typed list itself and no-ops on failure.

    Returns a dict describing the action taken. ``action`` ∈
    {``filed``, ``commented``, ``resolved``, ``green_no_issue``,
    ``skipped_no_token``, ``dedup_unknown_no_op``, ``filing_deferred``,
    ``comment_failed``, ``close_failed``, ``error``}."""
    from app.tasks import bug_report_github as gh

    result: dict[str, Any] = {"fingerprint": fingerprint, "marker": marker_key}

    if not gh.GITHUB_TOKEN:
        result["action"] = "skipped_no_token"
        return result

    # --- Normalize the dedup source into a trusted snapshot, or no-op UNKNOWN. ---
    if isinstance(open_issues, OpenIssuesResult):
        if not open_issues.ok:
            result.update(
                action="dedup_unknown_no_op",
                error=open_issues.error or "open-issue list unavailable",
            )
            return result
        snapshot = open_issues.issues
    elif open_issues is None:
        fetched = fetch_open_alert_issues()
        if not fetched.ok:
            result.update(
                action="dedup_unknown_no_op",
                error=fetched.error or "open-issue list unavailable",
            )
            return result
        snapshot = fetched.issues
    else:
        snapshot = open_issues  # plain list — trusted (back-compat)

    if red:
        existing = find_matching_issue(snapshot, fingerprint, marker_key, title_prefix)
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

        # Serialize read-before-create: only one concurrent run may create this
        # fingerprint's issue (C37 P2). A lost claim means another run is filing it.
        claim = _claim_fingerprint(marker_key, fingerprint)
        if claim == "lost":
            result.update(
                action="filing_deferred",
                note="another run holds the filing claim for this fingerprint",
            )
            return result
        if claim == "won":
            # Belt-and-suspenders: re-read immediately before create to catch an
            # issue a racing run created just outside our claim window. On a failed
            # re-read fall back to the snapshot (never abort a legitimate file).
            fresh = fetch_open_alert_issues()
            if fresh.ok:
                raced = find_matching_issue(fresh.issues, fingerprint, marker_key, title_prefix)
                if raced is not None:
                    try:
                        gh.comment_on_issue(
                            raced,
                            red_comment
                            or f"Sentinel re-observed this failure (fingerprint `{fingerprint}`). Still open.",
                        )
                    except Exception as exc:
                        logger.warning("sentinel_filing: comment failed on #%d: %s", raced, exc)
                        result.update(action="comment_failed", issue=raced, error=str(exc)[:200])
                        return result
                    result.update(action="commented", issue=raced)
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

    # GREEN — resolve the canonical open issue (declaration-only match; never title).
    existing = find_matching_issue(snapshot, fingerprint, marker_key, title_prefix=None)
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
    open_issues: "list[dict] | OpenIssuesResult | None" = None,
) -> list[dict]:
    """Reconcile a batch of fingerprints against ONE shared open-issue snapshot.

    Each item is a kwargs dict for ``reconcile_issue`` (minus ``open_issues``). The
    open-issue list is fetched once (typed) and reused, so a run that files/closes
    many fingerprints makes a single REST-list round-trip. A failed read propagates
    as ``ok=False`` so every item no-ops UNKNOWN rather than filing blind. Note:
    because the snapshot is fixed, two items that would file NEW issues for distinct
    fingerprints are safe, but two items resolving/commenting the SAME fingerprint in
    one batch is a caller bug (fingerprints are unique per sentinel check)."""
    if open_issues is None:
        open_issues = fetch_open_alert_issues()
    out = []
    for it in items:
        kwargs = build(it) if build else dict(it)
        kwargs.setdefault("open_issues", open_issues)
        out.append(reconcile_issue(**kwargs))
    return out
