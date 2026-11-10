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
    While an open episode's finding is UNCHANGED it is re-commented at most
    once a day; a CHANGED finding is commented on the run that sees it (#12276:
    95 identical "Still RED" lines on #12144 in 29 hours). The body refresh
    still runs every cycle.
  * ``post_report`` — the report path (#12231): one comment per period on a
    NAMED issue (a sentinel's report-only weeks), never a filing. Idempotent by
    a marker line read back from the issue's own comments plus a Redis claim;
    an unreadable comment list is an explicit no-op, never a blind post.

Filing defaults to ``priority:p2``. A sentinel that wants P1/P0 passes it in its
``labels`` with threshold evidence in the body; the rail NEVER edits the labels of
an existing issue, so a human-prioritized issue is never silently downgraded by a
later P2-default re-observation (it is only commented on).

**The default is enforced on the caller's list too, not just on ours.**
``DEFAULT_LABELS`` only ever applied when a sentinel passed no ``labels`` at all, and
every sentinel passes its own — so the P2 default protected nobody. Since Q434 the
rail runs whatever the caller supplied through
:func:`app.utils.issue_labels.ensure_taxonomy` and guarantees two things on create:

  * a ``priority:*`` label (the caller's if it set one, else P2 per the ratified
    2026-07-27 filing default), so no future sentinel can file an unprioritized
    issue by forgetting a list entry;
  * the ``alert-intake`` source label, because this rail's OWN dedup source is the
    open ``alert-intake`` list. Two sentinels were filing without it
    (``tournament_register_sentinel``, the calibration publish gate), which means
    their issues were invisible to ``fetch_open_alert_issues`` and re-filed on every
    run — the exact duplicate class the rail exists to prevent, arrived at from the
    label side instead of the search-index side.

**A delivery hold keeps an owned issue open on GREEN (#10526).** A sentinel's
GREEN says its cohort is empty, not that the reader got what the issue promised:
#10523 auto-closed twice (12:12Z, and again 12:30Z after a guarded reopen) on
``linked_unsourced`` GREEN while its exact event still had no Kalshi price and no
chart history and the repair was unmerged. An owner who needs the issue to outlive
the cohort puts ONE explicit label, ``sentinel:delivery-hold``
(:data:`DELIVERY_HOLD_LABEL`), on the canonical issue. GREEN then returns
``held_no_close`` — no close, and no recovery comment, so a sentinel that re-checks
GREEN every run does not bury the issue in identical notes. Only the canonical
target's OWN label counts; RED dedup/comment/body refresh is untouched, and the
owner removes the label when the original delivery is accepted.

Read-only against production data — the rail files/updates GitHub metadata only,
never touches market data.
"""

import hashlib
import json
import logging
import os
import re
import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

from app.utils.issue_labels import ensure_taxonomy

logger = logging.getLogger(__name__)

# Default labels for a freshly-filed sentinel issue (P2 per Queue #258 policy).
DEFAULT_LABELS = ["alert-intake", "needs-agent", "area:infra", "priority:p2"]

# The dedup source (``fetch_open_alert_issues``) lists issues by this label, so an
# issue filed without it is invisible to its own sentinel on the next run.
SOURCE_LABEL = "alert-intake"

# Opt-in, per-issue: the canonical issue carrying this label is NOT closed on GREEN
# (#10526). The marker and ``alert-intake`` stay, so dedup is unaffected.
DELIVERY_HOLD_LABEL = "sentinel:delivery-hold"


def filing_labels(labels: list[str] | None) -> list[str]:
    """The label list a create actually uses: the caller's, with the source label
    and a ``priority:*`` guaranteed. Pure, so a test can pin what each rail emits
    without reaching GitHub."""
    resolved = list(labels) if labels else list(DEFAULT_LABELS)
    if SOURCE_LABEL not in resolved:
        resolved.insert(0, SOURCE_LABEL)
    return ensure_taxonomy(resolved)

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


def issue_has_label(issue: dict, label: str) -> bool:
    """True when ``issue``'s OWN labels include ``label``. Pure (unit-tested).

    Accepts the REST list shape (``[{"name": ...}]``) and bare strings; anything
    else is not a label."""
    if not isinstance(issue, dict):
        return False
    for entry in issue.get("labels") or []:
        name = entry.get("name") if isinstance(entry, dict) else entry
        if name == label:
            return True
    return False


#: GitHub accepts no more comments on an issue that already has 2,500 — the
#: comment POST answers 403. #11958: Matching Drift's #2728 reached exactly 2,500
#: on Sep 29, and from then on every RED run "filed" a 403 and reached nobody.
GITHUB_COMMENT_CAP = 2500


def issue_is_full(issue: dict) -> bool:
    """True when GitHub will refuse another comment on this issue (the list
    API's ``comments`` count is at the cap)."""
    try:
        return int(issue.get("comments") or 0) >= GITHUB_COMMENT_CAP
    except (TypeError, ValueError):
        return False


def find_matching_issue(
    open_issues: list[dict],
    fingerprint: str,
    marker_key: str,
    title_prefix: str | None = None,
    *,
    accepting_comments: bool = False,
) -> int | None:
    """Pure dedup lookup over a list of open issues → matching issue number.

    Returns the LOWEST matching number so a stable canonical issue wins when
    duplicates already exist (the r252 cleanup: comment/close the oldest, not a
    later dupe). ``accepting_comments`` (the RED path) skips an issue GitHub
    will no longer take a comment on, so the episode continues on a successor
    issue instead of 403-ing forever (#11958)."""
    matches = [
        i["number"]
        for i in (open_issues or [])
        if isinstance(i, dict)
        and i.get("number") is not None
        and not (accepting_comments and issue_is_full(i))
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


# ---------------------------------------------------------------------------
# RED comment cadence (#12276).
# ---------------------------------------------------------------------------
#: An open episode whose finding is unchanged is re-commented at most once per
#: this many seconds. A changed finding is commented on the run that sees it.
RED_COMMENT_MIN_INTERVAL_S = 24 * 3600
#: How early inside the 24 h the daily comment may land. A daily sentinel's runs
#: are a few seconds either side of 24 h apart, so a strict 24 h would hold every
#: other night's comment at random; the 15-minute matching beat still lands at
#: exactly 24 h (95 cycles is 23 h 45 m, short of 23 h 50 m).
RED_COMMENT_DAILY_SLACK_S = 10 * 60
_RED_COMMENT_STATE_TTL_S = 8 * 24 * 3600

#: A date and time in a finding's text is when it was looked at — a run's own
#: clock, a pass's last run, a matcher's last attempt — and moves every run, so
#: the digest reads past it. A bare date is left in: at most it changes once a day.
_DIGEST_MOMENT = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
)


def _red_comment_cadence_on() -> bool:
    """The cadence's switch, read at call time: on unless
    ``SENTINEL_RED_COMMENT_CADENCE`` is ``off`` (every run comments, as before
    #12276). Tests run with it off unless a test turns it on (conftest)."""
    return os.getenv("SENTINEL_RED_COMMENT_CADENCE", "on").strip().lower() not in ("0", "off", "false", "no")


def _now() -> float:
    """Wall-clock seconds for the cadence; one seam for tests."""
    return _time.time()


def red_finding_digest(
    red_comment: str | None, red_body: str | None, basis: str | None = None
) -> str:
    """What one RED re-observation says, as a digest: the comment line plus the
    body the issue is refreshed to, read past every date and time in them.
    Counts, rows or provenance moving change it; the same finding seen again does
    not. ``basis``, when a caller gives one, replaces both: the caller's own
    statement of what makes the finding the same finding, for text that carries
    a measurement moving every run. Pure."""
    raw = basis if basis is not None else f"{red_comment or ''}\x00{red_body or ''}"
    return hashlib.sha1(_DIGEST_MOMENT.sub("<t>", raw).encode("utf-8")).hexdigest()[:16]


def _red_comment_key(marker_key: str, fingerprint: str) -> str:
    return f"sentinel:red_comment:last:{marker_key}:{fingerprint}"


def _red_comment_due(
    marker_key: str, fingerprint: str, issue: int, digest: str, now: float
) -> tuple[bool, str]:
    """``(comment now?, why)`` from the last recorded comment on this episode.

    Unreadable state comments, as every run did before #12276: a sentinel that
    cannot tell whether its finding changed must not go quiet."""
    if not _red_comment_cadence_on():
        return True, "cadence_off"
    try:
        from app.tasks.redis_state import get_redis_client

        raw = get_redis_client(fast_fail=True).get(_red_comment_key(marker_key, fingerprint))
    except Exception:
        return True, "state_unreadable"
    if not raw:
        return True, "first"
    try:
        last = json.loads(raw)
    except (TypeError, ValueError):
        return True, "state_unreadable"
    if not isinstance(last, dict) or last.get("issue") != issue:
        return True, "new_issue"
    if last.get("digest") != digest:
        return True, "changed"
    try:
        age = now - float(last.get("at"))
    except (TypeError, ValueError):
        return True, "state_unreadable"
    if age >= RED_COMMENT_MIN_INTERVAL_S - RED_COMMENT_DAILY_SLACK_S:
        return True, "daily"
    return False, "unchanged"


def _record_red_comment(marker_key: str, fingerprint: str, issue: int, digest: str, now: float) -> None:
    if not _red_comment_cadence_on():
        return
    try:
        from app.tasks.redis_state import get_redis_client

        get_redis_client(fast_fail=True).set(
            _red_comment_key(marker_key, fingerprint),
            json.dumps({"issue": issue, "digest": digest, "at": now}),
            ex=_RED_COMMENT_STATE_TTL_S,
        )
    except Exception:
        logger.warning(
            "sentinel_filing: could not record the RED comment state for %s:%s "
            "(the next run comments, as before #12276)",
            marker_key,
            fingerprint,
        )


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
    red_body: str | None = None,
    green_comment: str | None = None,
    open_issues: "list[dict] | OpenIssuesResult | None" = None,
    add_to_board: bool = True,
    red_digest_basis: str | None = None,
) -> dict:
    """The one fingerprint lifecycle for RED and GREEN.

    * ``red=True``  — file OR comment. Match the fingerprint against OPEN
      ``alert-intake`` issues; if one exists, comment AND (when ``red_body`` is
      supplied) refresh the body (no duplicate, no label edit, no state change);
      else create a new issue (default P2 labels) and add it to the board.
      The comment keeps a cadence (#12276): while the finding
      (``red_finding_digest`` of ``red_comment`` + ``red_body``, or of
      ``red_digest_basis`` when given) is unchanged since the episode's last
      comment, or since it was filed, the run is ``comment_skipped_unchanged``
      for 24 h (the body refresh still runs); a changed finding, a new issue, or
      unreadable state comments at once.
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

    A GREEN whose canonical issue carries ``DELIVERY_HOLD_LABEL`` returns
    ``held_no_close`` and writes nothing (#10526).

    Returns a dict describing the action taken. ``action`` ∈
    {``filed``, ``commented``, ``comment_skipped_unchanged``, ``resolved``, ``held_no_close``, ``green_no_issue``,
    ``skipped_no_token``, ``dedup_unknown_no_op``, ``filing_deferred``,
    ``comment_failed``, ``close_failed``, ``error``}."""
    from app.tasks import bug_report_github as gh

    result: dict[str, Any] = {"fingerprint": fingerprint, "marker": marker_key}

    def _refresh_body(issue: int) -> str:
        """Re-point an already-open issue's body at the CURRENT observation.

        Returns the outcome, recorded in the result as ``body_refresh`` so a
        silently-skipped refresh is visible rather than assumed.

        REFUSES a body that has lost the fingerprint declaration. The GREEN path
        matches the canonical issue by that declaration and nothing else, so a
        body without it can never be auto-closed again — the issue would go
        permanently stale in exactly the way this refresh exists to prevent.
        Better to leave a frozen body than to orphan the issue from its
        lifecycle.
        """
        if not red_body:
            return "not_requested"
        if fingerprint not in red_body:
            logger.warning(
                "sentinel_filing: refusing body refresh on #%d — the new body has "
                "lost fingerprint %s and would orphan the issue from its GREEN "
                "close path",
                issue,
                fingerprint,
            )
            return "refused_no_fingerprint"
        try:
            gh.update_issue_body(issue, red_body)
        except Exception as exc:
            # Non-fatal by design: the comment already carried the current
            # failures, so a failed refresh degrades to UX-P091's behaviour
            # rather than losing the re-detection.
            logger.warning(
                "sentinel_filing: body refresh failed on #%d: %s", issue, exc
            )
            return "failed"
        return "refreshed"

    def _reobserve(issue: int) -> dict:
        """Comment on an open episode — at most once a day while its finding is
        unchanged, at once when it changes (#12276) — then refresh its body."""
        now = _now()
        digest = red_finding_digest(red_comment, red_body, red_digest_basis)
        due, why = _red_comment_due(marker_key, fingerprint, issue, digest, now)
        if not due:
            result.update(
                action="comment_skipped_unchanged",
                issue=issue,
                comment_reason=why,
                body_refresh=_refresh_body(issue),
            )
            return result
        try:
            gh.comment_on_issue(
                issue,
                red_comment
                or f"Sentinel re-observed this failure (fingerprint `{fingerprint}`). Still open.",
            )
        except Exception as exc:
            logger.warning("sentinel_filing: comment failed on #%d: %s", issue, exc)
            result.update(action="comment_failed", issue=issue, error=str(exc)[:200])
            return result
        _record_red_comment(marker_key, fingerprint, issue, digest, now)
        result.update(
            action="commented", issue=issue, comment_reason=why, body_refresh=_refresh_body(issue)
        )
        return result

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
        existing = find_matching_issue(
            snapshot, fingerprint, marker_key, title_prefix, accepting_comments=True
        )
        if existing is not None:
            return _reobserve(existing)

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
                raced = find_matching_issue(
                    fresh.issues, fingerprint, marker_key, title_prefix, accepting_comments=True
                )
                if raced is not None:
                    return _reobserve(raced)
        # #11958: an open issue for this fingerprint that GitHub will take no
        # more comments on is continued, not abandoned — the successor names it.
        full = find_matching_issue(snapshot, fingerprint, marker_key, title_prefix)
        if full is not None:
            body = (
                f"{body}\n\nContinues #{full}, which reached GitHub's limit of "
                f"{GITHUB_COMMENT_CAP:,} comments on one issue."
            )
        try:
            number, node_id = gh.create_github_issue(title, body, filing_labels(labels))
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
        # The new issue's body carries this finding, so the next run's "Still RED"
        # waits for a change or a day, like any other comment (#12276).
        _record_red_comment(
            marker_key, fingerprint, number,
            red_finding_digest(red_comment, red_body, red_digest_basis), _now(),
        )
        return result

    # GREEN — resolve the canonical open issue (declaration-only match; never title).
    existing = find_matching_issue(snapshot, fingerprint, marker_key, title_prefix=None)
    if existing is None:
        result["action"] = "green_no_issue"
        return result
    target = next(
        i for i in snapshot if isinstance(i, dict) and i.get("number") == existing
    )
    if issue_has_label(target, DELIVERY_HOLD_LABEL):
        # The owner has said GREEN cohort health is not delivery: leave it open,
        # silently — a comment per GREEN run would bury the issue (#10526).
        result.update(action="held_no_close", issue=existing, hold=DELIVERY_HOLD_LABEL)
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


# ---------------------------------------------------------------------------
# Report path — a periodic count on a NAMED issue, never a filing (#12231).
# ---------------------------------------------------------------------------
#: Pages of an issue's comments read back for a period's marker. With ``since``
#: set to the period's start, a weekly report reads one page.
_REPORT_COMMENT_MAX_PAGES = 10


def report_marker_line(marker_key: str, period_key: str) -> str:
    """The line that makes "one post per period" provable from the issue itself.

    Same shape as a fingerprint declaration but a different annotation, so
    ``declared_fingerprints`` never reads a report as owning an alert.
    """
    return f"`{marker_key}:{period_key}`  (report period — one post per period)"


def _report_already_posted(
    issue: int, marker_line: str, since: str | None
) -> tuple[bool | None, str | None]:
    """Whether a comment on ``issue`` already carries ``marker_line``.

    ``(True, url)`` when one does; ``(False, None)`` when every comment was read
    and none does; ``(None, error)`` when the list could not be read in full.
    The third is never the second: a truncated or failed read cannot prove the
    week has no post (the C37 P1 "empty list means both" lesson, applied here).
    """
    from app.tasks.bug_report_github import GITHUB_TOKEN, REPO

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params: dict[str, Any] = {"per_page": _PER_PAGE}
    if since:
        params["since"] = since
    try:
        for page in range(1, _REPORT_COMMENT_MAX_PAGES + 1):
            resp = httpx.get(
                f"https://api.github.com/repos/{REPO}/issues/{issue}/comments",
                headers=headers,
                params={**params, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not isinstance(batch, list):
                return None, "comment list was not a list"
            for comment in batch:
                body = (comment or {}).get("body") or ""
                if any(line.strip() == marker_line for line in body.splitlines()):
                    return True, comment.get("html_url")
            if len(batch) < _PER_PAGE:
                return False, None
    except Exception as exc:
        logger.warning("sentinel_filing: report read-back failed on #%d: %s", issue, exc)
        return None, f"comment list failed: {str(exc)[:160]}"
    return None, f"comment list truncated at {_REPORT_COMMENT_MAX_PAGES} pages"


def post_report(
    *,
    issue: int,
    marker_key: str,
    period_key: str,
    body: str,
    since: str | None = None,
) -> dict:
    """Post one periodic report as a comment on a named issue: the rail's report path.

    #12231 (Fable's answer 1: A, Nov 6, 9:28 PM). A sentinel in its report-only
    weeks posts counts once per period on a named issue (the grouping sentinel
    posts on #12221) and **files nothing**. This function never creates, closes,
    relabels or edits an issue.

    One post per period, proven three ways:

    * the issue's own comments are read back for ``report_marker_line`` (since
      ``since``, the period's start, when given). A re-run, a manual run, or a
      run after a Redis flush finds the earlier post and returns
      ``already_posted``;
    * a Redis claim (the rail's ``_claim_fingerprint``, keyed ``report:<marker>``)
      serializes two runs that start together. The loser returns ``claim_lost``;
    * the winner re-reads before posting. A failed re-read falls back to the
      first read rather than abort a legitimate post, as ``reconcile_issue``
      does for a create.

    A comment list that cannot be read in full returns ``read_unknown_no_op``.
    It never posts blind. The marker line is appended when the body lacks it.

    Returns a dict; ``action`` ∈ {``posted``, ``already_posted``, ``claim_lost``,
    ``read_unknown_no_op``, ``skipped_no_token``, ``comment_failed``}.
    """
    from app.tasks import bug_report_github as gh

    result: dict[str, Any] = {"issue": issue, "marker": marker_key, "period": period_key}
    if not gh.GITHUB_TOKEN:
        result["action"] = "skipped_no_token"
        return result

    line = report_marker_line(marker_key, period_key)
    text = body if any(ln.strip() == line for ln in body.splitlines()) else f"{body.rstrip()}\n\n{line}\n"

    posted, info = _report_already_posted(issue, line, since)
    if posted is None:
        result.update(action="read_unknown_no_op", error=info)
        return result
    if posted:
        result.update(action="already_posted", url=info)
        return result

    claim = _claim_fingerprint(f"report:{marker_key}", period_key)
    if claim == "lost":
        result.update(action="claim_lost", note="another run holds this period's report claim")
        return result
    if claim == "won":
        again, again_info = _report_already_posted(issue, line, since)
        if again:
            result.update(action="already_posted", url=again_info)
            return result

    try:
        gh.comment_on_issue(issue, text)
    except Exception as exc:
        logger.warning("sentinel_filing: report post failed on #%d: %s", issue, exc)
        result.update(action="comment_failed", error=str(exc)[:200])
        return result
    result["action"] = "posted"
    return result
