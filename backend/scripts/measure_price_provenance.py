#!/usr/bin/env python3
"""CAL-P077 — run the price-provenance fold against production and emit an artifact.

The reader half of ``app.utils.calibration_price_provenance``. Every decision
lives in that pure module; this file supplies rows, a clock and a file handle,
which is the split that lets the decisions be tested without a database (there
is no local Postgres in this sandbox).

Why ``db-query`` and not a session
----------------------------------
The admin read rail is what an agent session can actually reach. It also happens
to be the *bounding* constraint worth designing against: its row path is fixed
at a 10 s ``statement_timeout``, so a fold that fits there fits anywhere. All 49
cells fit at ``k=1``, the slowest at 9.7 s (``esports/container_member``,
78,906 rows). The ``--partition`` escape exists for the cell that one day does
not, and it partitions on ``MOD(fm.id, k)`` rather than an ``ORDER BY fm.id``
walk — CAL-P074's density trap is that an ordered walk over a thinly-scattered
cell filters millions of primary keys and times out on a cell of 1,304 markets.

Usage::

    source ~/.claude/.env
    python3 backend/scripts/measure_price_provenance.py \\
        --census .claude/handoff/ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json \\
        --out artifacts/cal-p077/price-provenance.json

    # one cell, with the two decision queries attached
    python3 backend/scripts/measure_price_provenance.py \\
        --cell hockey/container_member --feasibility --leg-split

Writes NOTHING to the database. Every statement is a ``SELECT`` through the
read-only guard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.calibration_price_provenance import (  # noqa: E402
    LEG_SPLIT_SQL,
    POLICIES,
    PROVENANCE_FOLD_SQL,
    PROPOSED_POLICY,
    REPRICE_FEASIBILITY_SQL,
    FoldRow,
    class_shares,
    ece,
    policy_table,
    reconciles_with_census,
    render_sql,
)

#: ``db-query`` truncates silently at 1,000 rows and says so in ``truncated``.
#: A truncated fold is a WRONG fold, not a short one, so it is an error here.
ROW_CAP = 1000


class ReadError(RuntimeError):
    pass


def db_query(sql: str, *, api: str, token: str, limit: int = ROW_CAP) -> dict[str, Any]:
    """One read through the admin rail. Raises rather than returning an absence.

    Gotcha #53's rule, applied to a read: an empty result and a failed read must
    not reach the caller as the same value. A ``statement_timeout`` here means
    "this cell was not measured", and a fold that treated it as "this cell is
    empty" would publish a clean zero over a cell it never saw.
    """
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    request = urllib.request.Request(
        api.rstrip("/") + "/api/admin/db-query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400]
        raise ReadError(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001 — surfaced, never swallowed
        raise ReadError(f"{type(exc).__name__}: {exc}") from exc

    if "rows" not in payload:
        raise ReadError(json.dumps(payload.get("detail", payload))[:400])
    if payload.get("truncated"):
        raise ReadError(f"truncated at {ROW_CAP} rows — re-run with a larger --partition")
    return payload


#: How far the partition escalates before a cell is reported UNMEASURED. Each
#: step quarters the work per statement; 16 partitions of the largest cell
#: (``weather/quantity``, 64K outcomes) is ~4K each, far inside the budget.
MAX_PARTITION_K = 16


def _fold_at(cat: str, mt: str, *, api: str, token: str, k: int) -> tuple[list[FoldRow], dict[str, Any]]:
    rows: list[FoldRow] = []
    meta: dict[str, Any] = {"partition_k": k, "durations_ms": [], "fingerprints": []}
    for m in range(k):
        sql = render_sql(PROVENANCE_FOLD_SQL, cat=cat, mt=mt, k=k, m=m)
        payload = db_query(sql, api=api, token=token)
        meta["durations_ms"].append(payload.get("duration_ms"))
        meta["fingerprints"].append(payload.get("sql_fingerprint"))
        rows.extend(FoldRow.from_row(r) for r in payload["rows"])
    return rows, meta


def fold_cell(
    cat: str, mt: str, *, api: str, token: str, k: int = 1
) -> tuple[list[FoldRow], dict[str, Any]]:
    """Fold one cell, escalating the partition on a timeout rather than giving up.

    The first full sweep measured 47 of 49 and lost ``soccer/quantity`` (189K
    outcomes) and ``weather/quantity`` (64K) to ``statement_timeout`` at ``k=1``.
    Both are large, well-calibrated cells, and losing them does not merely leave
    two holes — it MOVES THE POOLED HEADLINE, because the pool is re-folded over
    whatever was measured. A 47-cell pool read 5.02 pp where the 49-cell pool
    read 3.78 pp, purely from the absence.

    So a partial sweep is not a slightly smaller sweep. Escalating here is the
    difference between an artifact that is complete and one that is biased
    toward the cells that happened to be cheap — which is the same bias codex
    named in round 1 (an oldest-500 head sample), arriving through a different
    door.

    Escalation is bounded and the partition reached is recorded in ``meta``, so
    a reader can see which cells needed it.
    """
    attempted: list[int] = []
    k = max(1, int(k))
    while True:
        attempted.append(k)
        try:
            rows, meta = _fold_at(cat, mt, api=api, token=token, k=k)
        except ReadError as exc:
            if "statement_timeout" not in str(exc) or k >= MAX_PARTITION_K:
                raise
            k *= 4
            print(f"  {cat}/{mt}: timeout, escalating partition -> k={k}", file=sys.stderr)
            continue
        meta["partitions_attempted"] = attempted
        return rows, meta


def scalar_query(
    template: str, cat: str, mt: str, *, api: str, token: str, k: int = 1
) -> dict[str, Any]:
    """A one-row aggregate, summed across partitions."""
    totals: dict[str, int] = {}
    meta: dict[str, Any] = {"durations_ms": [], "fingerprints": []}
    for m in range(k):
        sql = render_sql(template, cat=cat, mt=mt, k=k, m=m)
        payload = db_query(sql, api=api, token=token, limit=5)
        meta["durations_ms"].append(payload.get("duration_ms"))
        meta["fingerprints"].append(payload.get("sql_fingerprint"))
        for column, value in zip(payload["columns"], payload["rows"][0]):
            totals[column] = totals.get(column, 0) + int(value)
    return {"totals": totals, "meta": meta}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", help="the #1978 all-cells census artifact, for reconciliation")
    parser.add_argument("--cell", action="append", help="cat/market_type; repeatable. Default: every census cell")
    parser.add_argument("--partition", type=int, default=1, help="MOD(fm.id, k) partitions per cell")
    parser.add_argument("--feasibility", action="store_true", help="also run the re-price feasibility query")
    parser.add_argument("--leg-split", action="store_true", help="also run the leg-split safety query")
    parser.add_argument("--out", help="write the artifact here (default: stdout)")
    args = parser.parse_args()

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API and ADMIN_TOKEN must be set (source ~/.claude/.env)", file=sys.stderr)
        return 2

    census: dict[str, Any] = {}
    if args.census:
        with open(args.census) as handle:
            census = {c["cell"]: c for c in json.load(handle)["cells"]}

    if args.cell:
        cells = [tuple(c.split("/", 1)) for c in args.cell]
    elif census:
        cells = [(c["league"], c["market_type"]) for c in census.values()]
    else:
        print("give --cell or --census", file=sys.stderr)
        return 2

    started = time.time()
    pooled_rows: list[FoldRow] = []
    out: dict[str, Any] = {
        "schema": "calibration-price-provenance/v1",
        "proposed_policy": PROPOSED_POLICY,
        "policies": sorted(POLICIES),
        "cells": {},
        "unmeasured": {},
    }

    for cat, mt in cells:
        key = f"{cat}/{mt}"
        try:
            rows, meta = fold_cell(cat, mt, api=api, token=token, k=args.partition)
        except ReadError as exc:
            # Named, not dropped. An unmeasured cell that vanishes from the
            # artifact reads as a cell with nothing wrong with it.
            out["unmeasured"][key] = str(exc)
            print(f"{key:34} UNMEASURED — {exc}", file=sys.stderr)
            continue

        entry: dict[str, Any] = {
            "read": meta,
            "policies": policy_table(rows),
            "shares": class_shares(rows),
        }
        if key in census:
            entry["census_reconciliation"] = reconciles_with_census(rows, census[key])
        # The two SIDE probes must not be able to kill the run. Found the hard
        # way on the first full sweep: one ``statement_timeout`` on the
        # feasibility query (a correlated EXISTS into
        # ``futures_odds_snapshots``, far heavier than the fold) took down a
        # 49-cell walk that had already measured 30 of them, because only
        # ``fold_cell``'s ReadError was caught.
        #
        # That is the CAL-P077 ruling-(a) lesson landing on its own author: the
        # impure test covered the fold path failing and not this one, so the
        # untested branch is exactly where the defect was. The probes are now
        # per-cell optional evidence, recorded as unmeasured BY NAME.
        for flag, label, template in (
            (args.feasibility, "reprice_feasibility", REPRICE_FEASIBILITY_SQL),
            (args.leg_split, "leg_split", LEG_SPLIT_SQL),
        ):
            if not flag:
                continue
            try:
                entry[label] = scalar_query(
                    template, cat, mt, api=api, token=token, k=args.partition
                )
            except ReadError as exc:
                entry[label] = {"measured": False, "reason": str(exc)}
                print(f"{key:34} {label} UNMEASURED — {exc}", file=sys.stderr)
        out["cells"][key] = entry
        pooled_rows.extend(rows)

        today = entry["policies"]["A_today"]
        proposed = entry["policies"][PROPOSED_POLICY]
        recon = entry.get("census_reconciliation", {})
        flag = {True: "OK", False: "DIFF", None: "--"}[recon.get("reconciled")]
        print(
            f"{key:34} n={today['n']:7d} ECE {today['ece']} -> {proposed['ece']} "
            f"(d {proposed['delta_ece']}) census={flag}",
            file=sys.stderr,
        )

    # The pooled figure is the headline, so it is computed here rather than left
    # for a reader to assemble — and it is computed by re-folding every cell's
    # rows TOGETHER, not by averaging per-cell ECEs. An average over cells would
    # weight a 164-row cell like a 78,906-row one and hand the headline to the
    # noise.
    out["pooled"] = {
        name: ece(pooled_rows, selector) for name, selector in POLICIES.items()
    }
    baseline = out["pooled"]["A_today"]["ece"]
    for name, result in out["pooled"].items():
        result["delta_ece"] = (
            None
            if result["ece"] is None or baseline is None
            else round(result["ece"] - baseline, 4)
        )
    out["elapsed_s"] = round(time.time() - started, 2)
    out["cells_measured"] = len(out["cells"])
    out["cells_unmeasured"] = len(out["unmeasured"])

    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as handle:
            handle.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0 if not out["unmeasured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
