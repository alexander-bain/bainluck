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
* **event_espn_id_collision** — one ESPN event id worn by two ``events`` rows.
  Target 0 (#2693 step 2). The sibling of ``anchor_collision``, over the column
  that actually steers ESPN's writes; that one reads 0 only because nothing had
  written an anchor for these rows.
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
* **receipt_contradicts_link** — the receipt and the database disagree about
  where a market sits. Without this arm a link lost to a sibling market's
  rollback is invisible to every other check here: coverage counts markets with
  NO receipt and this one has one, linked_unsourced joins through the now-NULL
  ``event_id``, and golden only sees its fixed 709 ids. Target 0.

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

#: A market this old without a single price snapshot is not "sourced".
#: 90 minutes: two 15-minute matching cycles plus the 2-minute live poll's
#: worst case, with room for a slow backfill — short enough to satisfy the
#: brief's one-hour-ish bar, long enough that a market ingested seconds ago is
#: not accused.
#:
#: MEASURED ON ``created_at``, NOT ``updated_at``, and the first draft had it
#: wrong. ``updated_at`` moves on every price poll, so it says nothing about how
#: long a market has been ATTACHED — it let a market linked two minutes ago be
#: accused while its first snapshot was still in flight. Re-measured 2026-09-02
#: twenty minutes apart, the count fell 36 → 18 on its own, which is a check
#: reporting a queue depth and calling it a defect.
UNSOURCED_AFTER_MINUTES = 90

#: How close to kickoff an event has to be before a missing curve is a defect
#: rather than a not-yet. ±6h, not +24h: at a day out the 2-minute live poller
#: has legitimately not reached the event, and counting those is what made the
#: first draft of this check transient.
UNSOURCED_WINDOW_HOURS = 6


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
    """Re-check every adjudicated pair against production's current ``event_id``.

    A NEGATIVE PAIR'S ``None`` IS NOT A PROMISE THAT NOTHING MAY EVER ATTACH.
    548 of the 709 were adjudicated ``correct_event_id: None`` because no correct
    event *existed at capture time* — ``a-no-event``'s note is literally "global
    2+-token check; titles batch-read", i.e. the adjudicator swept the event
    titles and found no candidate. That is a statement about the world on
    2026-09-02, not a property of the market. This check used to read it as
    "must remain attached to nothing" and count every later attachment as a
    regression, which put "we broke it" and "we fixed it" under one RED number.

    Measured on production 2026-09-03, all 39 of the RED rows were negative
    pairs, and five of them had attached to a **provider-anchored** fixture that
    simply did not exist when the pair was adjudicated — "Hamburg vs Mainz" onto
    the real Bundesliga ``Hamburger SV v FSV Mainz 05``, "Ipswich Town vs
    Liverpool: Spread" onto the real EPL fixture. The check was reporting the
    matcher's successes as its failures.

    So a later attachment is judged by WHAT IT ATTACHED TO:

    * **provider-anchored** (``events.external_id`` present) — an outside source
      carries this fixture now. The matcher is corroborated, the baseline row is
      merely stale, and it is reported as ``baseline_stale`` and never RED.
    * **id-less** (``external_id IS NULL``) — nothing outside the matcher says
      this event exists; the matcher created it and then matched to its own
      creation. There is no corroboration to promote it out of RED, and the
      id-less-claim rule (gotcha #32 / ruling 048) means such a row can never be
      absorbed or reconciled later, so it is permanent. RED, as ``self_answered``.

    A POSITIVE pair — one the audit adjudicated onto a specific event — is
    unchanged: it had a known-correct answer, and losing it is a regression with
    no ambiguity at all.
    """
    pairs, baseline = load_golden_baseline()
    by_market = {int(p["market_id"]): p for p in pairs}
    ids = sorted(by_market)
    if not ids:
        return _finding("golden", False, 0, "no golden pairs loaded")

    # LEFT JOIN, not a second query: an unlinked market must still come back as a
    # row, or it reads as vanished (the deleted-market bucket) and the check
    # accuses the twin cleanup of being a matcher failure.
    rows = (await session.execute(
        text(
            "SELECT fm.id, fm.event_id, (e.external_id IS NULL) AS event_is_idless "
            "FROM futures_markets fm "
            "LEFT JOIN events e ON e.id = fm.event_id "
            "WHERE fm.id = ANY(:ids)"
        ),
        {"ids": ids},
    )).all()
    current = {
        int(r[0]): (int(r[1]) if r[1] is not None else None, r[2]) for r in rows
    }

    regressed, self_answered, baseline_stale = [], [], []
    recovered, vanished = [], []
    for mid, was_ok in baseline.items():
        if mid not in current:
            vanished.append(mid)
            continue
        actual, event_is_idless = current[mid]
        expected = by_market[mid]["correct_event_id"]
        now_ok = actual == expected
        if was_ok and not now_ok:
            p = by_market[mid]
            row = {
                "market_id": mid,
                "title": p["title"],
                "failure_class": p["failure_class"],
                "expected_event_id": expected,
                "actual_event_id": actual,
            }
            if expected is not None:
                # The audit knew the right answer and the market left it.
                row["verdict"] = "regressed"
                regressed.append(row)
            elif event_is_idless is False:
                # A provider anchors this fixture now. Not the matcher's error.
                row["verdict"] = "baseline_stale"
                baseline_stale.append(row)
            else:
                # id-less, or an event_id whose events row we could not read —
                # either way nothing outside the matcher corroborates it.
                row["verdict"] = "self_answered"
                self_answered.append(row)
        elif not was_ok and now_ok:
            recovered.append(mid)

    red_rows = regressed + self_answered
    detail = (
        f"{len(regressed)} adjudicated pairs regressed and {len(self_answered)} "
        f"negative pairs attached to an id-less event the matcher created "
        f"itself, of {len(baseline)} pairs ({len(baseline_stale)} attached to a "
        f"provider-anchored fixture that did not exist at capture — baseline "
        f"stale, not a regression; {len(recovered)} recovered, "
        f"{len(vanished)} markets no longer exist)"
    )
    out = _finding("golden", bool(red_rows), len(red_rows), detail, red_rows)
    out["regressed"] = len(regressed)
    out["self_answered"] = len(self_answered)
    out["baseline_stale"] = len(baseline_stale)
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


async def check_event_espn_id_collision(session) -> dict:
    """One ESPN event id worn by two ``events`` rows. Target 0 (#2693 step 2).

    ``check_anchor_collision`` above asks the same question of
    ``event_provider_anchors``, and it has always answered 0 — because nothing
    had written an anchor for these rows. The column ``espn_sync`` actually
    steers its writes through is ``events.espn_id``, and on 2026-09-02 that one
    was worn by two or more rows for **196 ids, 430 rows**.

    THIS CHECK IS THE DURABLE HALF OF THE REPAIR, and it exists because
    CERT-784 asked the right question: a repair whose population an active
    writer refills is not a repair. The writers are holder-checked now
    (``espn_id_stamp``, #2017), but "we fixed every writer we found" is a claim
    about a census, and this is the measurement that would notice a writer
    nobody censused. It does not depend on the unique index existing — which
    matters, because ``backend/Procfile`` wraps the release-phase Alembic run in
    ``|| echo`` and so cannot fail a deploy on a missing migration (#2741).
    """
    rows = (await session.execute(text(
        """
        SELECT espn_id, count(*) AS n
        FROM events
        WHERE espn_id IS NOT NULL
        GROUP BY espn_id
        HAVING count(*) > 1
        ORDER BY n DESC, espn_id
        LIMIT 200
        """
    ))).all()
    listed = [{"espn_id": r[0], "events": int(r[1])} for r in rows]
    return _finding(
        "event_espn_id_collision", bool(listed), len(listed),
        f"{len(listed)} ESPN event id(s) worn by more than one events row — the "
        "authority writes one game's status, clock and score onto two fixtures",
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
          AND e.commence_time BETWEEN NOW() - (:hrs * INTERVAL '1 hour')
                                  AND NOW() + (:hrs * INTERVAL '1 hour')
          AND fm.created_at < NOW() - (:mins * INTERVAL '1 minute')
        GROUP BY 1, 2
        HAVING NOT EXISTS (
            SELECT 1 FROM win_prob_snapshots w
            WHERE w.event_id = fm.event_id AND w.source = fm.source
        )
        ORDER BY 3 DESC
        LIMIT 200
        """
    ), {"mins": UNSOURCED_AFTER_MINUTES,
         "hrs": UNSOURCED_WINDOW_HOURS})).all()
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


async def check_receipt_contradicts_link(session) -> dict:
    """A receipt that disagrees with the database about where a market sits.

    CERT-772'S FINDING, ANSWERED. Receipts are written on their own session, so
    a market can be claimed as linked and then have its pending ``event_id``
    rolled back by a sibling market's failure in the same pass. Before this
    check, such a row was invisible to every other arm here:
    ``receipt_coverage`` counts markets with NO receipt and this one HAS one;
    ``linked_unsourced`` joins through an ``event_id`` that is now NULL; and
    ``golden`` only ever looks at its fixed 709 ids. All five could report GREEN
    while a market sat unattached and its one-query answer said "linked".

    Two shapes, one subject, because they are the same failure seen from two
    sides:

    * a published receipt whose ``linked_event_id`` disagrees with the market's
      actual ``event_id`` — the contradiction itself;
    * a receipt already downgraded to ``link_not_durable`` by the write-time
      guard — the contradiction caught before publication.

    The second is the healthy path and should still be reported: nonzero means
    the matcher IS losing links, even though the receipt no longer lies about it.
    """
    rows = (await session.execute(text(
        """
        SELECT r.market_id, r.linked_event_id, fm.event_id, r.phase,
               r.last_attempted_at
        FROM market_match_receipts r
        JOIN futures_markets fm ON fm.id = r.market_id
        WHERE r.outcome = 'linked'
          AND r.linked_event_id IS DISTINCT FROM fm.event_id
        LIMIT 200
        """
    ))).all()
    contradictions = [
        {"market_id": int(r[0]), "receipt_says_event_id": int(r[1]) if r[1] is not None else None,
         "database_says_event_id": int(r[2]) if r[2] is not None else None,
         "phase": r[3],
         "last_attempted_at": r[4].isoformat() if r[4] else None}
        for r in rows
    ]

    lost = int(await session.scalar(text(
        "SELECT count(*) FROM market_match_receipts "
        "WHERE reject_reason = 'link_not_durable'"
    )) or 0)

    total = len(contradictions) + lost
    return _finding(
        "receipt_contradicts_link", total > 0, total,
        f"{len(contradictions)} receipt(s) disagree with the database about "
        f"where their market sits, and {lost} were caught by the write-time "
        "guard as link_not_durable — either way the matcher is losing links a "
        "sibling market's failure rolled back",
        contradictions,
    )


CHECKS = (
    check_golden_pairs,
    check_anchor_collision,
    check_event_espn_id_collision,
    check_market_multi_event,
    check_receipt_coverage,
    check_linked_unsourced,
    check_receipt_contradicts_link,
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
            "eligible markets that cycle did not reach. Read "
            "`coverage.by_source` and its per-source "
            "`explained_no_game_here` before "
            "reading it as missing links (#2803): what clears this number is a "
            "receipt, and for most of the population that receipt is a refusal. "
            "`coverage.backlog_pass_has_run` true means the pass that drives it "
            "down has run. It is never false: a run whose record write failed "
            "is indistinguishable from no run, so the absent case is null — "
            "check `coverage.backlog_pass.status` before concluding the backlog "
            "pass never ran."
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
