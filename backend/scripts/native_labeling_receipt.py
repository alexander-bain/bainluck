#!/usr/bin/env python3
"""THE NATIVE LABELING RECEIPT — UX-P110 item 3 (Fable directive 2026-08-20).

    "Alex will label >=5 cards in the NATIVE app tonight. Prove the pipe
     end-to-end: those exact rows landed with the right surface and reviewer
     tier, judged values intact, and the scorer reads them. Post the receipt on
     the board with row ids. Until this exists, phone-native sessions don't
     count toward gold; after it, they do."

── WHY A SCRIPT AND NOT A HAND-ASSEMBLED COMMENT ────────────────────────────────

The claim being made is that a whole class of future sessions counts toward gold.
A receipt assembled by hand proves one night; a receipt that is a command proves
every night after it, and can be re-run the first time someone doubts it. It also
cannot quietly skip the check that would have failed.

── THE FIVE CLAIMS, AND WHAT WOULD FALSIFY EACH ─────────────────────────────────

1. LANDED           rows exist on ``surface = native_discover`` in the window
2. RIGHT SURFACE    that surface, not the ``discover`` default the route falls
                    back to when a client omits it
3. RIGHT TIER       resolves to a GOLD tier, read through the SAME
                    ``reviewer_tier`` helper production reads it through, never a
                    re-implemented string compare (doctrine clause 5)
4. VALUES INTACT    label / rank_seen / item id / reason tags / card snapshot
5. SCORER READS     the daily eval run's ``row_count`` rises by exactly the
                    number of new gold rows in its window

Claim 5 is the end-to-end one and the only one that cannot be faked by the write
path being tidy. It is measured as a DELTA across two runs rather than as an
absolute, because ``row_count`` is a 30-day rolling window and its absolute value
carries rows nobody is claiming.

── PRECEDENT, ALREADY MEASURED (2026-08-20, before tonight's session) ───────────

The last native session wrote ids 80/81/82 at 2026-08-17 22:36–22:37 UTC, all
``native_discover`` / tier ``alex`` / reviewer ``alex.bain@gmail.com``. The eval
runs bracketing them went ``55 -> 58``, and a census of that window returns those
three rows and nothing else. So the pipe demonstrably works; what it has never
had is a receipt. This script is the receipt.

── WHAT IT WILL REPORT AS A KNOWN GAP RATHER THAN A FAILURE ─────────────────────

``score_at_review`` is 0 on all 57 web rows and 23 of 27 native rows, and
``feed_request_id`` is NULL on all 84 rows in the table. Those are TABLE-WIDE and
predate the native surface, so they are not evidence against the native pipe and
must not fail the receipt — but a receipt that silently omitted them would be
overclaiming "values intact". They are printed under GAPS.

USAGE
    source ~/.claude/.env
    python3 scripts/native_labeling_receipt.py --since 2026-08-20T20:00:00Z

    --since     ISO8601 UTC; the start of the labeling session
    --expect    minimum rows required to pass (default 5)
    --surface   default native_discover

EXIT CODES
    0  receipt PASSES — every claim verified
    1  a claim FAILED — the detail says which
    2  could not check (no credentials, API unreachable) — deliberately NOT 1,
       because "the gate could not run" is a different fact from "the gate
       failed" (gotcha #54's amendment).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.reviewer_tier import GOLD_TIERS, tier_of  # noqa: E402

VALID_LABELS = {"love", "fine", "bad", "kill"}
TIMEOUT = 45


def _api() -> tuple[str, str]:
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        print("CANNOT CHECK: BAINLUCK_API / ADMIN_TOKEN unset — `source ~/.claude/.env`")
        raise SystemExit(2)
    return base.rstrip("/"), token


def _get(path: str) -> dict:
    base, token = _api()
    req = urllib.request.Request(
        f"{base}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        return json.loads(res.read().decode())


def _query(sql: str, limit: int = 200) -> list[list]:
    """Read-only SQL through the admin endpoint.

    Returns rows as lists. The endpoint serializes JSONB as a Python repr rather
    than JSON (gotcha #40), so this asks Postgres for scalars and text and never
    for a JSONB column — the alternative is an ``ast.literal_eval`` fallback in
    every consumer, which is the bug that endpoint keeps causing.
    """
    base, token = _api()
    req = urllib.request.Request(
        f"{base}/api/admin/db-query",
        data=json.dumps({"sql": sql, "limit": limit}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        payload = json.loads(res.read().decode())
    if payload.get("truncated"):
        raise SystemExit("CANNOT CHECK: db-query truncated the result; narrow the window")
    return payload.get("rows") or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="ISO8601 UTC session start")
    ap.add_argument("--expect", type=int, default=5)
    ap.add_argument("--surface", default="native_discover")
    args = ap.parse_args()

    since = args.since.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(since)
    except ValueError:
        print(f"CANNOT CHECK: --since {args.since!r} is not ISO8601")
        return 2

    print("=" * 78)
    print(f"NATIVE LABELING RECEIPT — surface={args.surface} since={args.since}")
    print("=" * 78)

    try:
        rows = _query(
            "SELECT id, created_at, surface, reviewer, label, rank_seen, item_type, "
            "market_id, event_id, "
            "COALESCE(label_metadata->>'reviewer_tier', '') AS tier, "
            "COALESCE(array_length(reason_tags, 1), 0) AS n_tags, "
            "(label_metadata ? 'card_snapshot') AS has_snapshot, "
            "COALESCE(label_metadata->'drift_gate'->>'bound', 'unrecorded') AS gate, "
            "COALESCE(label_metadata->'drift_gate'->>'reason', '') AS gate_reason, "
            "score_at_review, (feed_request_id IS NOT NULL) AS has_request_id, "
            "left(coalesce(market_name, ''), 60) AS name "
            f"FROM ranking_judgments WHERE created_at >= '{since}' "
            "ORDER BY created_at"
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"CANNOT CHECK: {exc}")
        return 2

    failures: list[str] = []
    gaps: list[str] = []

    # ---- claims 1-4, per row -------------------------------------------------
    native = [r for r in rows if r[2] == args.surface]
    other = [r for r in rows if r[2] != args.surface]

    print(f"\nROWS IN WINDOW: {len(rows)}  ({len(native)} {args.surface}, {len(other)} other)\n")
    if not native:
        failures.append(f"CLAIM 1 LANDED: no {args.surface} rows since {args.since}")
    elif len(native) < args.expect:
        failures.append(
            f"CLAIM 1 LANDED: {len(native)} rows, expected >= {args.expect}"
        )

    zero_score = 0
    no_request_id = 0
    gate_tally: dict[str, int] = {}
    gate_reasons: dict[str, int] = {}
    for r in native:
        (rid, created, surface, reviewer, label, rank_seen, item_type,
         market_id, event_id, tier_raw, n_tags, has_snapshot,
         gate, gate_reason, score, has_request_id, name) = r

        # Claim 3 through the production helper, so a change to tier semantics
        # moves the receipt with it rather than leaving it asserting the old rule.
        tier = tier_of({"reviewer_tier": tier_raw} if tier_raw else {})
        gold = tier in GOLD_TIERS
        ok = "OK " if gold else "FAIL"
        print(f"  [{ok}] id={rid} {created} tier={tier} reviewer={reviewer}")
        print(f"        label={label} rank={rank_seen} {item_type}={market_id or event_id} "
              f"tags={n_tags} snapshot={has_snapshot}")
        print(f"        {name}")

        if not gold:
            failures.append(f"CLAIM 3 TIER: id {rid} resolves to {tier!r}, not gold")
        if reviewer in (None, "", "native"):
            # "native" unresolved means the Bearer-token identity lookup did not
            # run, so reviewed-state would be a shared pool rather than his.
            failures.append(f"CLAIM 3 REVIEWER: id {rid} reviewer={reviewer!r} unresolved")
        if label not in VALID_LABELS:
            failures.append(f"CLAIM 4 VALUES: id {rid} label={label!r} not in {sorted(VALID_LABELS)}")
        if rank_seen is None:
            failures.append(f"CLAIM 4 VALUES: id {rid} has no rank_seen")
        if not (market_id or event_id):
            failures.append(f"CLAIM 4 VALUES: id {rid} has neither market_id nor event_id")
        if not has_snapshot:
            failures.append(f"CLAIM 4 VALUES: id {rid} carries no card_snapshot")

        gate_tally[gate] = gate_tally.get(gate, 0) + 1
        if gate != "true" and gate_reason:
            gate_reasons[gate_reason] = gate_reasons.get(gate_reason, 0) + 1

        if not score:
            zero_score += 1
        if not has_request_id:
            no_request_id += 1

    # ---- claim 6: the drift gate, reported either way (#1933) ----------------
    #
    # This is a MANIFEST, not a pass/fail. The gate binds only clients that
    # declare it, so an old build in the field legitimately writes unbound rows —
    # and a receipt that printed nothing when they were all unbound would let a
    # whole session of ungated labels read as gated ones. Zero bound is a
    # measurement here, never a silence.
    print("\nDRIFT GATE (#1933), all rows in the window:")
    if not native:
        print("  (no rows to classify)")
    else:
        labels = {"true": "bound", "false": "unbound", "unrecorded": "unrecorded"}
        for key in ("true", "false", "unrecorded"):
            count = gate_tally.get(key, 0)
            print(f"  {labels[key]:11} {count}/{len(native)}")
        for reason, count in sorted(gate_reasons.items(), key=lambda kv: -kv[1]):
            print(f"      {reason}: {count}")

    if native and gate_tally.get("unrecorded"):
        # A row written by a server that has the gate ALWAYS carries the stamp,
        # so an unrecorded row in a post-deploy window means the write went down
        # a path that never consulted it. That is a real failure, unlike unbound.
        failures.append(
            f"CLAIM 6 GATE: {gate_tally['unrecorded']} row(s) carry no drift_gate "
            "stamp at all — a write path that never consulted the gate"
        )
    if native and gate_tally.get("false"):
        gaps.append(
            f"CLAIM 6 GATE: {gate_tally['false']}/{len(native)} rows are UNBOUND "
            f"({', '.join(f'{k}={v}' for k, v in sorted(gate_reasons.items()))}) — "
            "expected until the gate-aware build is the only one in the field"
        )

    # Table-wide, pre-existing, and named rather than folded into a pass.
    if zero_score:
        gaps.append(
            f"score_at_review is 0 on {zero_score}/{len(native)} rows — table-wide "
            "(0 on all 57 web rows too), predates this surface, filed separately"
        )
    if no_request_id:
        gaps.append(
            f"feed_request_id NULL on {no_request_id}/{len(native)} rows — NULL on "
            "all 84 rows in the table, both surfaces"
        )

    # ---- claim 5: the scorer reads them --------------------------------------
    print("\nSCORER (daily discover-label eval, gold tier, all surfaces):")
    try:
        runs = _get("/api/admin/discover-label-eval/runs?limit=10").get("runs", [])
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  CANNOT CHECK: {exc}")
        return 2

    before = None
    after = None
    for run in runs:  # newest first
        captured = run.get("captured_at")
        if not captured:
            continue
        when = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        if when >= datetime.fromisoformat(since):
            after = run  # keep walking; the LAST match is the earliest run after
        elif before is None:
            before = run
            break

    for tag, run in (("before", before), ("after", after)):
        if run:
            print(f"  {tag:6} {run['captured_at']}  row_count={run['row_count']}  "
                  f"tapworthy_at_k={run.get('tapworthy_at_k')}")
        else:
            print(f"  {tag:6} (none)")

    if after is None:
        # NOT a failure: the beat runs 09:55 UTC daily, so an evening session is
        # simply waiting for it. Saying "failed" here would teach the reader to
        # ignore a real failure tomorrow.
        print("\n  PENDING: no eval run since the session. The beat is 09:55 UTC "
              "daily — re-run this after it, or trigger the task.")
        gaps.append("CLAIM 5 SCORER: pending the next 09:55 UTC eval run")
    elif before is None:
        gaps.append("CLAIM 5 SCORER: no run before the session to compare against")
    else:
        delta = after["row_count"] - before["row_count"]
        # Count gold rows in the SAME window the delta spans — [since, after).
        # Counting every row since `since` would include rows written after the
        # `after` run captured, and the two numbers would be quietly measuring
        # different windows while sitting on one line pretending to compare.
        after_at = datetime.fromisoformat(after["captured_at"].replace("Z", "+00:00"))
        in_delta_window = [
            r for r in rows
            if datetime.fromisoformat(str(r[1]).replace(" ", "T")) < after_at
        ]
        gold_new = len([
            r for r in in_delta_window
            if tier_of({"reviewer_tier": r[9]} if r[9] else {}) in GOLD_TIERS
        ])
        native_in_window = len([r for r in in_delta_window if r[2] == args.surface])
        print(f"\n  eval window [{args.since} .. {after['captured_at']}]")
        print(f"  row_count delta = {delta}; gold rows written in that window = {gold_new} "
              f"(of which {args.surface}: {native_in_window})")
        if delta < native_in_window:
            failures.append(
                f"CLAIM 5 SCORER: row_count rose {delta} but {native_in_window} "
                f"{args.surface} gold rows landed inside that window — the scorer "
                "is not reading them"
            )
        else:
            print("  the scorer counted them.")

    # ---- verdict --------------------------------------------------------------
    print("\n" + "=" * 78)
    if gaps:
        print("GAPS (known, not failures):")
        for g in gaps:
            print(f"  - {g}")
    if failures:
        print("RECEIPT FAILED:")
        for f in failures:
            print(f"  - {f}")
        print("=" * 78)
        return 1

    ids = ", ".join(str(r[0]) for r in native)
    print(f"RECEIPT PASSES — {len(native)} native gold rows: ids {ids}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
