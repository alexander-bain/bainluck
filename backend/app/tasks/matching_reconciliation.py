"""Matching reconciliation — the golden set and the invariants, in production (#2706).

WHY A JOB AND NOT JUST A CI TEST. The CI gate
(``tests/test_matching_golden_set_2706.py``) replays the golden pairs against a
frozen fixture, so it catches a change to the matcher's LOGIC before it merges.
It cannot catch the other half: production data moving under a matcher nobody
changed. Every failure this program exists to end arrived that way — the 8/28
ingest wave went unattempted with no code change, the Li–Vekic links landed on a
ghost twin with no code change, and Bublik and Harris were "attached" with zero
price snapshots with no code change. The definition of solved in the program
brief is explicit about who notices: *"nothing the authority knows about is
missing, doubled, or half-sourced for more than an hour without an issue
existing — and the SYSTEM files that issue, not a person."*

WHAT IT CHECKS, every matching cycle:

* **golden** — the 709 adjudicated pairs, against production ``event_id``.
  Positives must be on their event, negatives must be on none. The baseline is
  the state captured with the fixture, so the check is *regression*, not
  perfection — most pairs are the audit's open failure classes and filing them
  every 15 minutes would be noise, not signal.
* **anchor_collision** — INVARIANTS-2026-09-02 query (a): one
  ``(source, source_id, id_kind)`` naming two events. Target 0.
* **market_multi_event** — query (b): one market linked to two events. Target 0.
  Open-scoped, deliberately: the unscoped form times out (fp fedd618081365d6b).
* **receipt_coverage** — query (c)'s successor. (c) counted 996 markets with an
  exact-name candidate, unlinked, and *no written reason*, and noted the reason
  was "structural today — futures_markets has no attempt/reject columns". With
  receipts (#2705) it becomes answerable: open unlinked markets with NO receipt.
  Target 0; above 0, "never attempted" is still possible.
* **linked_unsourced** — attached is not sourced. A market can hold an
  ``event_id`` and still write no price, which is what Bublik and Harris looked
  like on 9/2: linked, outcomes priced, and no polymarket curve on the card.

FILING. One deduped issue per SUBJECT via the shared sentinel rail
(``app/tasks/sentinel_filing.py``), so each check has its own fingerprint, its
own issue, and its own RED→GREEN lifecycle: recovery closes the issue instead of
leaving the board to grow. Filing uses the repo's ``GITHUB_TOKEN`` bot identity —
never a person's. Every issue carries the label ``matching-drift`` and links
#2693.

READ-ONLY against market data. This job files GitHub metadata and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)

MARKER = "matching-drift-fingerprint"
DRIFT_LABEL = "matching-drift"

#: The adjudicated pairs + the production state they were captured in. Shared
#: with the CI gate on purpose: two copies of the golden set is two golden sets.
FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures"
    / "matching_golden_inputs.json"
)

#: Rows named in an issue body. Enough to act on, bounded so the body stays
#: readable; the total is always stated, so truncation is never silent.
MAX_LISTED = 25

#: A market linked this long without a single price snapshot is not "sourced".
#: 90 minutes: two 15-minute matching cycles plus the 2-minute live poll's
#: worst case, with room for a slow backfill — short enough to satisfy the
#: brief's one-hour-ish bar, long enough that a market linked seconds ago is
#: not accused.
UNSOURCED_AFTER_MINUTES = 90


# ---------------------------------------------------------------------------
# The checks. Each returns {"key", "red", "count", "detail", "rows"}.
# ---------------------------------------------------------------------------


def _finding(key: str, red: bool, count: int, detail: str, rows=None) -> dict:
    return {
        "key": key, "red": red, "count": count, "detail": detail,
        "rows": rows or [],
    }


def load_golden_baseline() -> tuple[list[dict], dict[int, bool]]:
    """The pairs, and which of them production satisfied at capture time.

    ``event_id_at_capture`` is the state the audit adjudicated against, so the
    baseline is derived from the fixture rather than stored twice. A pair that
    was already wrong on 2026-09-02 is not news every fifteen minutes; a pair
    that was RIGHT and stops being right is exactly the news this job exists
    for.
    """
    data = json.loads(FIXTURE_PATH.read_text())
    pairs = data["pairs"]
    baseline = {}
    for p in pairs:
        at_capture = p["market"].get("event_id_at_capture")
        baseline[int(p["market_id"])] = at_capture == p["correct_event_id"]
    return pairs, baseline


async def check_golden_pairs(session) -> dict:
    """Re-check every adjudicated pair against production's current ``event_id``."""
    pairs, baseline = load_golden_baseline()
    by_market = {int(p["market_id"]): p for p in pairs}
    ids = sorted(by_market)
    if not ids:
        return _finding("golden", False, 0, "no golden pairs loaded")

    rows = (await session.execute(
        text("SELECT id, event_id FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": ids},
    )).all()
    current = {int(r[0]): (int(r[1]) if r[1] is not None else None) for r in rows}

    regressed, recovered, vanished = [], [], []
    for mid, was_ok in baseline.items():
        if mid not in current:
            vanished.append(mid)
            continue
        expected = by_market[mid]["correct_event_id"]
        now_ok = current[mid] == expected
        if was_ok and not now_ok:
            p = by_market[mid]
            regressed.append({
                "market_id": mid,
                "title": p["title"],
                "failure_class": p["failure_class"],
                "expected_event_id": expected,
                "actual_event_id": current[mid],
            })
        elif not was_ok and now_ok:
            recovered.append(mid)

    detail = (
        f"{len(regressed)} of {len(baseline)} adjudicated pairs regressed "
        f"({len(recovered)} recovered, {len(vanished)} markets no longer exist)"
    )
    out = _finding("golden", bool(regressed), len(regressed), detail, regressed)
    out["recovered"] = len(recovered)
    out["vanished"] = len(vanished)
    return out


async def check_anchor_collision(session) -> dict:
    """INVARIANTS (a): one provider id naming two events. Baseline 0/6,039."""
    rows = (await session.execute(text(
        """
        SELECT source, source_id, id_kind, count(DISTINCT event_id) AS n
        FROM event_provider_anchors
        GROUP BY 1, 2, 3
        HAVING count(DISTINCT event_id) > 1
        LIMIT 200
        """
    ))).all()
    listed = [
        {"source": r[0], "source_id": r[1], "id_kind": r[2], "events": int(r[3])}
        for r in rows
    ]
    return _finding(
        "anchor_collision", bool(listed), len(listed),
        f"{len(listed)} (source, source_id, id_kind) key(s) name more than one "
        "event — the anchor channel is the thing absorption is allowed to trust",
        listed,
    )


async def check_market_multi_event(session) -> dict:
    """INVARIANTS (b): one market on two events. Open-scoped — see the module docstring."""
    rows = (await session.execute(text(
        """
        SELECT source, external_id, count(DISTINCT event_id) AS n
        FROM futures_markets
        WHERE status = 'open' AND event_id IS NOT NULL
        GROUP BY 1, 2
        HAVING count(DISTINCT event_id) > 1
        LIMIT 200
        """
    ))).all()
    listed = [
        {"source": r[0], "external_id": r[1], "events": int(r[2])} for r in rows
    ]
    return _finding(
        "market_multi_event", bool(listed), len(listed),
        f"{len(listed)} open market(s) linked to more than one event "
        "(scope: open only — the unscoped query times out)",
        listed,
    )


async def check_receipt_coverage(session) -> dict:
    """INVARIANTS (c)'s successor: open unlinked markets with NO receipt.

    (c) counted 996 markets with an exact-name candidate and no written reason,
    and said the gap was structural: ``futures_markets`` had nowhere to write a
    reason. Receipts (#2705) closed that, so the question becomes countable —
    and the number that matters is not "how many are unlinked" but "how many
    have never been LOOKED AT". Above 0, the 8/28 wave can happen again.
    """
    n = await session.scalar(text(
        """
        SELECT count(*)
        FROM futures_markets fm
        WHERE fm.source IN ('kalshi', 'polymarket')
          AND fm.event_id IS NULL
          AND fm.status = 'open'
          AND NOT EXISTS (
              SELECT 1 FROM market_match_receipts r WHERE r.market_id = fm.id
          )
        """
    ))
    n = int(n or 0)
    return _finding(
        "receipt_coverage", n > 0, n,
        f"{n} open unlinked market(s) have never been attempted — while this is "
        "above 0, a whole ingest wave can sit unlooked-at (ARTIFACT-M-20260902-N)",
    )


async def check_linked_unsourced(session) -> dict:
    """Attached is not sourced: a source on the card with no line behind it.

    Bublik and Harris on 2026-09-02 were linked with priced outcomes and NO
    polymarket win_prob_snapshots, so their cards drew no curve. ``event_id`` is
    not the ship; the line on the card is.

    COUNTED PER (EVENT, SOURCE), NOT PER MARKET, and the difference is the whole
    reading. Only the game-winner market feeds the blend — a spread, a total or
    a first-half prop is *supposed* to write nothing — so counting markets
    accuses 300 rows of a fault 264 of them cannot commit. What a user can
    actually see is one thing: this event has that source attached and no curve
    from it. Measured 2026-09-02: 300 markets, **36** event×source pairs, among
    them Auger-Aliassime v Khachanov.
    """
    rows = (await session.execute(text(
        """
        SELECT fm.event_id, fm.source, count(*) AS markets,
               min(e.commence_time) AS commence_time
        FROM futures_markets fm
        JOIN events e ON e.id = fm.event_id
        WHERE fm.source IN ('kalshi', 'polymarket')
          AND fm.status = 'open'
          AND e.status IN ('scheduled', 'live')
          AND e.commence_time BETWEEN NOW() - INTERVAL '6 hours'
                                  AND NOW() + INTERVAL '24 hours'
          AND fm.updated_at < NOW() - (:mins * INTERVAL '1 minute')
        GROUP BY 1, 2
        HAVING NOT EXISTS (
            SELECT 1 FROM win_prob_snapshots w
            WHERE w.event_id = fm.event_id AND w.source = fm.source
        )
        ORDER BY 3 DESC
        LIMIT 200
        """
    ), {"mins": UNSOURCED_AFTER_MINUTES})).all()
    listed = [
        {"event_id": int(r[0]), "source": r[1], "linked_markets": int(r[2]),
         "commence_time": r[3].isoformat() if r[3] else None}
        for r in rows
    ]
    return _finding(
        "linked_unsourced", bool(listed), len(listed),
        f"{len(listed)} near-term event/source pair(s) are linked but have written "
        "no win-prob snapshot — attached is not sourced, so the card shows the "
        "source and draws no curve",
        listed,
    )


CHECKS = (
    check_golden_pairs,
    check_anchor_collision,
    check_market_multi_event,
    check_receipt_coverage,
    check_linked_unsourced,
)


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------


def fingerprint_for(key: str) -> str:
    """One stable fingerprint per SUBJECT.

    Per subject, not per finding: a check that goes RED on 40 markets and then
    on 41 is the same problem, and giving it a content-derived fingerprint would
    file a new issue every cycle — the duplicate class the shared rail exists to
    prevent, arrived at from the fingerprint side.
    """
    return hashlib.sha256(f"matching-reconciliation:{key}".encode()).hexdigest()[:12]


def build_title(finding: dict) -> str:
    return f"[Matching Drift] {finding['key']}: {finding['detail']}"[:256]


def build_body(finding: dict, receipts_hint: str | None = None) -> str:
    fp = fingerprint_for(finding["key"])
    parts = [
        f"## Matching reconciliation — `{finding['key']}` is RED",
        "",
        f"`{MARKER}:{fp}`  (dedupe key — do not remove)",
        "",
        f"**Finding:** {finding['detail']}",
        f"**Count:** {finding['count']}",
        "",
    ]
    if finding["rows"]:
        parts.append(f"### Rows ({min(len(finding['rows']), MAX_LISTED)} of {finding['count']})")
        for row in finding["rows"][:MAX_LISTED]:
            parts.append(f"- `{json.dumps(row, sort_keys=True, default=str)}`")
        if finding["count"] > MAX_LISTED:
            parts.append(f"- …and {finding['count'] - MAX_LISTED} more")
        parts.append("")
    if receipts_hint:
        parts += ["### Receipt", "", receipts_hint, ""]
    parts += [
        "---",
        "Part of the durable matching program (#2693). Step 1 receipts (#2705) "
        "answer *why* a specific market is unattached: "
        "`GET /api/admin/match-receipts?market_id=<id>`.",
        "",
        "*Auto-filed by `app.tasks.matching_reconciliation` (#2706) using the "
        "repo's bot identity. Read-only against market data. Reproduce with "
        "`POST /api/admin/matching-reconciliation/run?inline=true&file_issues=false`.*",
    ]
    return "\n".join(parts)


def receipts_hint_for(finding: dict) -> str | None:
    """The one query that turns this finding into a diagnosis."""
    if finding["key"] == "golden" and finding["rows"]:
        mid = finding["rows"][0]["market_id"]
        return (
            f"Why market {mid} sits where it does: "
            f"`GET /api/admin/match-receipts?market_id={mid}` — the candidates it "
            "was offered, their scores, and the closed-enum reason."
        )
    if finding["key"] == "receipt_coverage":
        return (
            "Coverage summary: `GET /api/admin/match-receipts` — "
            "`coverage.open_unlinked_without_receipt` is this number, and "
            "`funnel.backlog_dropped` on the matcher's last run says how many "
            "eligible markets that cycle did not reach."
        )
    if finding["key"] == "linked_unsourced" and finding["rows"]:
        eid = finding["rows"][0]["event_id"]
        return f"What the matcher put on event {eid}: `GET /api/admin/match-receipts?event_id={eid}`."
    return None


def file_findings(findings: list[dict], open_issues=None) -> list[dict]:
    """RED/GREEN reconcile, one issue per subject, via the shared rail."""
    from app.tasks.sentinel_filing import reconcile_issue

    results = []
    for finding in findings:
        fp = fingerprint_for(finding["key"])
        if finding["red"]:
            body = build_body(finding, receipts_hint_for(finding))
            res = reconcile_issue(
                red=True,
                fingerprint=fp,
                marker_key=MARKER,
                labels=[
                    "alert-intake", DRIFT_LABEL, "needs-agent",
                    "area:event-details", "priority:p1",
                ],
                title=build_title(finding),
                body=body,
                red_body=body,
                red_comment=(
                    f"Still RED: {finding['detail']} (fingerprint `{fp}`)."
                ),
                open_issues=open_issues,
            )
        else:
            res = reconcile_issue(
                red=False,
                fingerprint=fp,
                marker_key=MARKER,
                green_comment=(
                    f"Matching reconciliation re-checked `{finding['key']}` GREEN "
                    f"— {finding['detail']}. Auto-closing; a recurrence opens a "
                    f"fresh episode."
                ),
                open_issues=open_issues,
            )
        res["check"] = finding["key"]
        results.append(res)
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run_matching_reconciliation(file_issues: bool = True) -> dict[str, Any]:
    """Run every check; file or resolve one issue per subject."""
    findings: list[dict] = []
    errors: list[str] = []

    async with get_task_session() as session:
        for check in CHECKS:
            try:
                findings.append(await check(session))
            except Exception as e:
                # A check that cannot run is UNKNOWN, never GREEN. Recording it
                # as GREEN would close a real issue on the strength of a failed
                # query (gotcha #53 — a failure is not an absence).
                errors.append(f"{check.__name__}: {str(e)[:200]}")
                logger.warning("matching_reconciliation: %s failed: %s", check.__name__, e)

    red = [f for f in findings if f["red"]]
    result: dict[str, Any] = {
        "checks_run": len(findings),
        "checks_failed": len(errors),
        "red": [f["key"] for f in red],
        "findings": [
            {k: v for k, v in f.items() if k != "rows"} for f in findings
        ],
        "errors": errors,
        "filed": [],
    }

    if not file_issues:
        result["filing"] = "skipped"
        return result

    from app.tasks.sentinel_filing import fetch_open_alert_issues

    open_issues = fetch_open_alert_issues()
    result["filed"] = file_findings(findings, open_issues=open_issues)
    logger.info(
        "matching_reconciliation: %d check(s), %d RED, %d unmeasurable — %s",
        len(findings), len(red), len(errors),
        ", ".join(f"{r['check']}={r.get('action')}" for r in result["filed"]),
    )
    return result
