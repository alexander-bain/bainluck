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
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any, Iterable, Sequence

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.calibration_price_provenance import (  # noqa: E402
    LEG_SPLIT_SQL,
    POLICIES,
    PROVENANCE_FOLD_SQL,
    PROPOSED_POLICY,
    REPRICE_FEASIBILITY_SQL,
    WHOLE_MARKET_FOLD_SQL,
    WHOLE_MARKET_POLICIES,
    FoldRow,
    MarketFoldRow,
    class_shares,
    ece,
    market_level_shares,
    market_policy_table,
    policy_table,
    reconciles_with_census,
    reconciles_with_row_fold,
    render_sql,
)

#: ``db-query`` truncates silently at 1,000 rows and says so in ``truncated``.
#: A truncated fold is a WRONG fold, not a short one, so it is an error here.
ROW_CAP = 1000

#: MEASURED 2026-08-21 (CAL-P085), because the docs read the other way. The
#: ``timeout_ms`` knob documented on ``db-query`` (``500 ms - 25 s``) is
#: **`explain`-only**: sending it on the row path returns
#: ``400 {"detail": "`timeout_ms` is only supported with `explain: true`"}``.
#:
#: So the row path is **fixed at the 10 s ``statement_timeout``** and there is no
#: headroom to buy. Partition escalation is not a last resort for this fold, it
#: is the only budget control there is — which is why :func:`fold_cell` escalates
#: rather than reporting a cell unmeasured on the first timeout.
ROW_PATH_STATEMENT_TIMEOUT_S = 10


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


def canonical_raw(rows: Iterable[Sequence[Any]]) -> list[list[str]]:
    """The grouped rows as COMMITTED INPUTS — verbatim, stringified, sorted.

    ``C-APPLY-PRE-WHICHPRICE-R3`` [P1] attack 1: the artifact preserved the
    producer's answers and not the grouped inputs those answers were computed
    from, so its pooled ``1.7422 pp`` could not be re-derived by anyone but the
    producer. Per-cell ECEs cannot be averaged into a pooled ECE — bin-level
    cancellation across cells is invisible from a cell summary (the cert
    measured the gap: cell-average ``4.2831`` vs pooled ``1.7422``).

    Every value is written as the STRING the read rail returned. ``sum_prob``
    arrives as a numeric string and float-normalising it here would make the
    receipt re-derive from the producer's rounding rather than from the
    database's answer. Sorting is what makes two partitions of the same cell
    byte-comparable (attack 7).
    """
    return sorted([str(v) for v in row] for row in rows)


def raw_fingerprint(rows: Iterable[Sequence[Any]]) -> str:
    """SHA-256 over :func:`canonical_raw`, so two reads compare in one field."""
    payload = json.dumps(canonical_raw(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def aggregate_raw(rows: Iterable[Sequence[Any]]) -> list[list[str]]:
    """Sum the grouped rows per key. The LAST THREE columns are ``n``/``sum_prob``/``winners``.

    A ``k``-way partition emits the same ``(grade, bin, level…)`` key once per
    partition, so two reads of the same cell at different ``k`` are only
    comparable after re-aggregation. This is not a normalisation convenience —
    comparing the verbatim rows would report "the partitions disagree" for every
    cell that was ever partitioned, which is a false alarm of exactly the shape
    this program keeps having to unlearn.

    ``sum_prob`` is summed as :class:`~decimal.Decimal` from the numeric string
    the rail returned, so the re-aggregation is EXACT and a mismatch is a real
    mismatch rather than float drift. The output is canonicalised with
    ``format(x.normalize(), "f")``, which never uses exponent notation.
    """
    acc: dict[tuple[str, ...], list[Any]] = {}
    for row in rows:
        key = tuple(str(v) for v in row[:-3])
        slot = acc.setdefault(key, [0, Decimal(0), 0])
        slot[0] += int(row[-3])
        slot[1] += Decimal(str(row[-2]))
        slot[2] += int(row[-1])
    return sorted(
        list(key) + [str(v[0]), format(v[1].normalize(), "f"), str(v[2])]
        for key, v in acc.items()
    )


def aggregate_fingerprint(rows: Iterable[Sequence[Any]]) -> str:
    payload = json.dumps(aggregate_raw(rows), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _fold_at(
    cat: str,
    mt: str,
    *,
    api: str,
    token: str,
    k: int,
    template: str = PROVENANCE_FOLD_SQL,
    row_class: Any = FoldRow,
) -> tuple[list[Any], dict[str, Any]]:
    rows: list[Any] = []
    raw: list[Sequence[Any]] = []
    meta: dict[str, Any] = {"partition_k": k, "durations_ms": [], "fingerprints": []}
    for m in range(k):
        sql = render_sql(template, cat=cat, mt=mt, k=k, m=m)
        payload = db_query(sql, api=api, token=token)
        meta["durations_ms"].append(payload.get("duration_ms"))
        meta["fingerprints"].append(payload.get("sql_fingerprint"))
        raw.extend(payload["rows"])
        rows.extend(row_class.from_row(r) for r in payload["rows"])
    # Carried on ``meta`` so every caller — including the escalating
    # :func:`fold_cell` — gets the inputs of the read that actually SUCCEEDED,
    # not of the attempt before it. The writer pops it back out; it never
    # reaches the artifact's ``read`` block by accident.
    meta["_raw"] = raw
    return rows, meta


def fold_cell(
    cat: str,
    mt: str,
    *,
    api: str,
    token: str,
    k: int = 1,
    template: str = PROVENANCE_FOLD_SQL,
    row_class: Any = FoldRow,
) -> tuple[list[Any], dict[str, Any]]:
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
            rows, meta = _fold_at(
                cat, mt, api=api, token=token, k=k, template=template, row_class=row_class
            )
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


def partition_invariance(
    cat: str, mt: str, ks: Sequence[int], *, api: str, token: str
) -> dict[str, Any]:
    """Run ONE cell's whole-market fold at several ``k`` and compare the results.

    ``C-APPLY-PRE-WHICHPRICE-R3`` [P1] attack 7: the R3 artifact recorded
    ``partitions_attempted: [1, 4]`` for ``esports/container_member`` and a
    committed test proving only that the SQL *text* partitions on ``fm.id``.
    Two database results were never compared, so the safety argument for
    ``MOD(fm.id, k)`` — "a partitioned run and a ``k=1`` run are the same fold"
    (:data:`WHOLE_MARKET_FOLD_SQL`'s docstring) — was structural reasoning, not
    execution.

    This executes it. Each ``k`` is a genuinely separate set of statements
    against the database; the comparison is on the **policy table** (the object
    the apply is authorised against) and, independently, on the byte-canonical
    grouped inputs. Failures are reported per ``k`` and never collapsed into the
    reassuring reading: a ``k`` that times out is recorded as ``unmeasured``,
    which is NOT "the tables agreed".
    """
    out: dict[str, Any] = {
        "cell": f"{cat}/{mt}",
        "k_values": list(ks),
        "reads": {},
        "policy_tables": {},
        "raw_fingerprints": {},
        "aggregate_fingerprints": {},
        "unmeasured": {},
    }
    for k in ks:
        try:
            rows, meta = _fold_at(
                cat,
                mt,
                api=api,
                token=token,
                k=k,
                template=WHOLE_MARKET_FOLD_SQL,
                row_class=MarketFoldRow,
            )
        except ReadError as exc:
            out["unmeasured"][str(k)] = str(exc)
            print(f"  invariance {cat}/{mt} k={k}: UNMEASURED — {exc}", file=sys.stderr)
            continue
        raw = meta.pop("_raw", [])
        out["reads"][str(k)] = meta
        out["policy_tables"][str(k)] = market_policy_table(rows)
        out["raw_fingerprints"][str(k)] = raw_fingerprint(raw)
        out["aggregate_fingerprints"][str(k)] = aggregate_fingerprint(raw)

    measured = sorted(out["policy_tables"])
    if len(measured) < 2:
        out["verdict"] = None
        out["reason"] = f"needs two measured k, have {measured}"
        return out

    def canon(table: Any) -> str:
        return json.dumps(table, sort_keys=True, separators=(",", ":"))

    reference = measured[0]
    out["reference_k"] = reference
    out["policy_tables_byte_equal"] = {
        k: canon(out["policy_tables"][k]) == canon(out["policy_tables"][reference])
        for k in measured
    }
    # The re-aggregated grouped inputs, NOT the verbatim ones: see
    # :func:`aggregate_raw`. The verbatim fingerprints stay in the artifact as a
    # record of what each read actually returned.
    out["raw_rows_equal"] = {
        k: out["aggregate_fingerprints"][k] == out["aggregate_fingerprints"][reference]
        for k in measured
    }
    out["verdict"] = bool(
        all(out["policy_tables_byte_equal"].values())
        and all(out["raw_rows_equal"].values())
        and not out["unmeasured"]
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", help="the #1978 all-cells census artifact, for reconciliation")
    parser.add_argument("--cell", action="append", help="cat/market_type; repeatable. Default: every census cell")
    parser.add_argument("--partition", type=int, default=1, help="MOD(fm.id, k) partitions per cell")
    parser.add_argument("--feasibility", action="store_true", help="also run the re-price feasibility query")
    parser.add_argument("--leg-split", action="store_true", help="also run the leg-split safety query")
    parser.add_argument(
        "--whole-market",
        action="store_true",
        help=(
            "CAL-P085 (#2087): also run the market-aware fold and report policies A-E at the "
            "granularity the approved apply actually runs at. The row-level fold still runs, "
            "because A_today under both is the reconciliation key."
        ),
    )
    parser.add_argument(
        "--raw-rows",
        action="store_true",
        help=(
            "CAL-P092 (WHICHPRICE-R3 attack 1): also commit each cell's grouped "
            "SQL output verbatim, so the pooled table can be re-derived by "
            "someone who is not the producer."
        ),
    )
    parser.add_argument(
        "--invariance",
        action="append",
        default=[],
        metavar="CELL:K,K",
        help=(
            "CAL-P092 (WHICHPRICE-R3 attack 7): run one cell's whole-market fold "
            "at each k and compare the resulting policy tables. Repeatable, e.g. "
            "--invariance tennis/container_member:1,16"
        ),
    )
    parser.add_argument("--out", help="write the artifact here (default: stdout)")
    args = parser.parse_args()

    invariance_specs: list[tuple[str, str, list[int]]] = []
    for spec in args.invariance:
        cell, _, ks = spec.partition(":")
        cat, _, mt = cell.partition("/")
        if not (cat and mt and ks):
            print(f"--invariance wants CELL:K,K, got {spec!r}", file=sys.stderr)
            return 2
        invariance_specs.append((cat, mt, [int(k) for k in ks.split(",")]))

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
    elif invariance_specs:
        cells = []
    else:
        print("give --cell, --census or --invariance", file=sys.stderr)
        return 2

    started = time.time()
    pooled_rows: list[FoldRow] = []
    pooled_market_rows: list[MarketFoldRow] = []
    out: dict[str, Any] = {
        "schema": "calibration-price-provenance/v2" if args.whole_market else "calibration-price-provenance/v1",
        "proposed_policy": PROPOSED_POLICY,
        "policies": sorted(POLICIES),
        "cells": {},
        "unmeasured": {},
    }
    if args.whole_market:
        out["whole_market_policies"] = sorted(WHOLE_MARKET_POLICIES)
        out["whole_market_unmeasured"] = {}

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

        raw = meta.pop("_raw", [])
        entry: dict[str, Any] = {
            "read": meta,
            "policies": policy_table(rows),
            "shares": class_shares(rows),
        }
        if args.raw_rows:
            entry["raw_rows"] = canonical_raw(raw)
            entry["raw_fingerprint"] = raw_fingerprint(raw)

        # CAL-P085 (#2087). The market-aware fold is a SECOND statement, run and
        # failed independently: a cell whose whole-market read times out must not
        # take down the row-level read that already succeeded, and — the whole
        # point of the P077 discipline — must be named as unmeasured rather than
        # dropped, because a pooled figure re-folded over whatever survived MOVES
        # (47 cells read 5.02 pp where 49 read 3.78 pp).
        if args.whole_market:
            try:
                market_rows, market_meta = fold_cell(
                    cat,
                    mt,
                    api=api,
                    token=token,
                    k=args.partition,
                    template=WHOLE_MARKET_FOLD_SQL,
                    row_class=MarketFoldRow,
                )
            except ReadError as exc:
                out["whole_market_unmeasured"][key] = str(exc)
                print(f"{key:34} WHOLE-MARKET UNMEASURED — {exc}", file=sys.stderr)
            else:
                market_raw = market_meta.pop("_raw", [])
                entry["whole_market"] = {
                    "read": market_meta,
                    "policies": market_policy_table(market_rows),
                    "shares": market_level_shares(market_rows),
                    "row_fold_reconciliation": reconciles_with_row_fold(market_rows, rows),
                }
                if args.raw_rows:
                    entry["whole_market"]["raw_rows"] = canonical_raw(market_raw)
                    entry["whole_market"]["raw_fingerprint"] = raw_fingerprint(market_raw)
                pooled_market_rows.extend(market_rows)

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
        line = (
            f"{key:34} n={today['n']:7d} ECE {today['ece']} -> {proposed['ece']} "
            f"(d {proposed['delta_ece']}) census={flag}"
        )
        if "whole_market" in entry:
            wm = entry["whole_market"]["policies"]["all_legs"][PROPOSED_POLICY]
            rec = entry["whole_market"]["row_fold_reconciliation"]
            wm_flag = {True: "OK", False: "DIFF", None: "--"}[rec.get("reconciled")]
            line += (
                f" | WM {wm['ece']} (d {wm['delta_ece']}) n={wm['n']} recon={wm_flag}"
            )
        print(line, file=sys.stderr)

    if invariance_specs:
        out["partition_invariance"] = {}
        for cat, mt, ks in invariance_specs:
            result = partition_invariance(cat, mt, ks, api=api, token=token)
            out["partition_invariance"][result["cell"]] = result
            print(
                f"INVARIANCE {result['cell']:34} k={result['k_values']} "
                f"verdict={result['verdict']} unmeasured={sorted(result['unmeasured'])}",
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
    # The headline the apply is actually authorised against. Same construction as
    # the row-level pool above — every cell's rows re-folded TOGETHER, never an
    # average of per-cell ECEs — so the two are comparable line for line.
    if args.whole_market:
        out["pooled_whole_market"] = market_policy_table(pooled_market_rows)
        out["pooled_whole_market"]["shares"] = market_level_shares(pooled_market_rows)
        out["pooled_whole_market"]["row_fold_reconciliation"] = reconciles_with_row_fold(
            pooled_market_rows, pooled_rows
        )
        out["whole_market_cells_measured"] = sum(
            1 for c in out["cells"].values() if "whole_market" in c
        )
        out["whole_market_cells_unmeasured"] = len(out["whole_market_unmeasured"])

    # ``C-APPLY-PRE-WHICHPRICE-R3`` [P1] attack 3: the load-bearing
    # ``101 mixed markets in 464,777`` was carried forward from the P077
    # artifact, whose A population is 370,677 rows against this fold's 372,293 —
    # a 1,616-row drift. A repeated count is not a current measurement, so the
    # split is re-measured here on the SAME 49-cell snapshot as the fold and
    # pooled by summation (every column is a market COUNT, and no market spans
    # two cells because the cell predicates are all on ``fm``).
    #
    # The pool is only a total if every cell is in it. Cells whose probe timed
    # out are named in ``cells_unmeasured`` and ``complete`` goes false, because
    # a partial sum presented as a population count is the same defect this
    # attack is about.
    for label in ("leg_split", "reprice_feasibility"):
        contributing = {
            key: cell[label]
            for key, cell in out["cells"].items()
            if isinstance(cell.get(label), dict) and "totals" in cell[label]
        }
        missing = sorted(
            key
            for key, cell in out["cells"].items()
            if label in cell and "totals" not in cell[label]
        )
        if not contributing and not missing:
            continue
        totals: dict[str, int] = {}
        for cell in contributing.values():
            for column, value in cell["totals"].items():
                totals[column] = totals.get(column, 0) + int(value)
        out[f"pooled_{label}"] = {
            "totals": totals,
            "cells_measured": len(contributing),
            "cells_unmeasured": missing,
            "complete": not missing,
        }

    out["elapsed_s"] = round(time.time() - started, 2)
    out["cells_measured"] = len(out["cells"])
    out["cells_unmeasured"] = len(out["unmeasured"])
    if args.raw_rows:
        # Column order, written down, because an independent re-deriver that has
        # to infer it from the data is re-deriving the producer's assumptions.
        out["raw_rows_schema"] = {
            "row_fold": [
                "price_class",
                "capture_class",
                "grade",
                "bin",
                "n",
                "sum_prob",
                "winners",
            ],
            "whole_market": [
                "grade",
                "bin",
                "mkt_price_level",
                "mkt_capture_level",
                "mkt_capture_level_pop",
                "n",
                "sum_prob",
                "winners",
            ],
            "note": (
                "Every value is the string the read rail returned, sorted "
                "lexicographically. Pool = the concatenation of every measured "
                "cell's rows; pooled ECE is a re-fold of that pool, never an "
                "average of per-cell ECEs."
            ),
        }

    text = json.dumps(out, indent=1, sort_keys=True)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as handle:
            handle.write(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)

    if args.whole_market:
        pooled = out["pooled_whole_market"]
        rec = pooled["row_fold_reconciliation"]
        print(
            f"POOLED WHOLE-MARKET  A_today {pooled['all_legs']['A_today']['ece']} "
            f"-> {PROPOSED_POLICY} {pooled['all_legs'][PROPOSED_POLICY]['ece']} "
            f"(d {pooled['all_legs'][PROPOSED_POLICY]['delta_ece']}), "
            f"n {pooled['all_legs']['A_today']['n']} -> "
            f"{pooled['all_legs'][PROPOSED_POLICY]['n']}; "
            f"row-fold reconciliation {rec['reconciled']} (n_delta {rec['n_delta']})",
            file=sys.stderr,
        )
    invariance_ok = all(
        r.get("verdict") is True for r in out.get("partition_invariance", {}).values()
    )
    return (
        0
        if not out["unmeasured"]
        and not out.get("whole_market_unmeasured")
        and invariance_ok
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
