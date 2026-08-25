#!/usr/bin/env python3
"""CAL-P092 — re-derive a price-provenance artifact's policy tables from its own committed inputs.

This is the **recomputation receipt** ``C-APPLY-PRE-WHICHPRICE-R3`` [P1] attack 1
asked for, and it exists because the R3 artifact could not discharge that attack:

    "the artifact contains zero ``rows``, ``bins``, ``sum_prob``, or ``winners``
    fields. Its per-cell policy summaries can reproduce each pooled ``n``
    exactly, but cannot reproduce pooled ECE: for policy C, the committed pooled
    value is ``1.7422 pp``, while the only available aggregation of cell ECEs is
    ``4.2831 pp``; bin-level cancellation is unknowable from the artifact."

The `4.2831` is the whole point. A pooled ECE is a re-fold of every cell's BINS
together, and cancellation between cells inside a bin is invisible from a per-cell
summary — so an artifact of answers can be checked for self-consistency and still
not be checkable at all. Only the grouped inputs make the headline falsifiable.

INDEPENDENCE, and its exact limits
----------------------------------
This file **does not import** ``app.utils.calibration_price_provenance``. The
policies, the bin-pooled ECE, and the whole-market lift are re-stated here from
ruling 103's prose and the artifact's own ``raw_rows_schema``. If the producer's
selector and this one disagree, the receipt says so; if they agree, the headline
has been reproduced by a second implementation reading only committed inputs.

What this is NOT: it is not independent of the SQL. Both sides read the same
grouped rows the database returned, so a defect in ``PROVENANCE_FOLD_SQL``'s
classification would be reproduced faithfully by both. Attack 1 is about the
Python fold above the rows; the SQL is attacks 2/4/6's ground. Saying so here
rather than letting a green receipt imply more than it proves.

Arithmetic
----------
Every value is re-derived TWICE:

* ``exact`` — :class:`~fractions.Fraction` over the numeric strings the read rail
  returned, so it carries no float error at all;
* ``float`` — IEEE doubles in the producer's order, which is what must match the
  committed number bit for bit.

A receipt that only did the float pass would be re-deriving the producer's
rounding; one that only did the exact pass would report a last-digit rounding
difference as a defect. Both are reported, and the verdict requires the float
pass to match exactly and the exact pass to agree within one ulp of the fourth
decimal place (``1e-4 pp``).

Usage::

    python3 backend/scripts/verify_price_provenance_artifact.py \\
        artifacts/cal-p092/price-provenance-whole-market-r4.json

Exit 0 iff every committed table was reproduced. Reads no database, no network,
and no file but the artifact named on the command line.
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from typing import Any, Callable, Iterable, Mapping, Sequence

#: Re-stated, not imported. Below this an ECE is ``None`` with a stated reason —
#: an absent measurement must never render as a clean zero.
MIN_CELL_N = 30

#: Row-level policies, from ruling 103 and the artifact's ``raw_rows_schema``.
#: Each takes the row as a dict of column name -> string.
ROW_POLICIES: dict[str, Callable[[Mapping[str, str]], bool]] = {
    "A_today": lambda r: r["grade"] == "complete",
    "B_exclude_cp_absent": lambda r: r["grade"] == "complete"
    and r["price_class"] != "cp_absent",
    "C_exclude_hindsight": lambda r: r["grade"] == "complete"
    and r["capture_class"] != "after_resolution",
    "D_moved_price_only": lambda r: r["grade"] == "complete"
    and r["price_class"] == "cp_moved",
    "E_pregame_or_unknown_ts": lambda r: r["grade"] == "complete"
    and r["capture_class"] in ("pregame", "no_capture_ts"),
}

#: The same five, lifted to the market. The lift is one rule applied five times:
#: keep a market iff EVERY leg satisfies the row-level selector of the same name
#: ("winners and losers together"). The SQL has already collapsed each market to
#: an ordered level, so each lift is one comparison.
MARKET_POLICIES: dict[str, Callable[[Mapping[str, str]], bool]] = {
    "A_today": lambda r: r["grade"] == "complete",
    "B_exclude_cp_absent": lambda r: r["grade"] == "complete"
    and r["mkt_price_level"] != "has_absent",
    "C_exclude_hindsight": lambda r: r["grade"] == "complete"
    and r["mkt_capture_level"] != "has_after_res",
    "D_moved_price_only": lambda r: r["grade"] == "complete"
    and r["mkt_price_level"] == "all_moved",
    "E_pregame_or_unknown_ts": lambda r: r["grade"] == "complete"
    and r["mkt_capture_level"] == "all_pregame_or_nots",
}

#: The sensitivity ladder: the same two capture policies decided by only the legs
#: the curve reads.
MARKET_POPULATION_LEG_POLICIES: dict[str, Callable[[Mapping[str, str]], bool]] = {
    "C_exclude_hindsight": lambda r: r["grade"] == "complete"
    and r["mkt_capture_level_pop"] != "has_after_res",
    "E_pregame_or_unknown_ts": lambda r: r["grade"] == "complete"
    and r["mkt_capture_level_pop"] == "all_pregame_or_nots",
}

#: How far the exact rational pass may sit from the committed float before it is
#: called a disagreement rather than fourth-decimal rounding.
ROUNDING_SLACK_PP = 1e-4


def as_dicts(
    rows: Iterable[Sequence[str]], columns: Sequence[str]
) -> list[dict[str, str]]:
    """Zip committed rows against the schema the artifact wrote down.

    A row whose width does not match the schema is an error, not a row to
    truncate: the schema is the artifact's promise about its own inputs, and a
    silent ``zip`` would let a shifted column reproduce a plausible wrong table.
    """
    out = []
    for row in rows:
        if len(row) != len(columns):
            raise ValueError(f"row width {len(row)} != schema width {len(columns)}")
        out.append(dict(zip(columns, (str(v) for v in row))))
    return out


def fold(
    rows: Iterable[Mapping[str, str]],
    keep: Callable[[Mapping[str, str]], bool],
) -> dict[str, Any]:
    """Bin-pooled ECE: ``sum_b (n_b / N) * |mean_price_b - winrate_b|``, in pp.

    Both arithmetics, from the same bins, in one pass.
    """
    bins: dict[str, list[Any]] = {}
    for row in rows:
        if not keep(row):
            continue
        slot = bins.setdefault(row["bin"], [0, Fraction(0), 0])
        slot[0] += int(row["n"])
        slot[1] += Fraction(row["sum_prob"])
        slot[2] += int(row["winners"])

    total = sum(int(s[0]) for s in bins.values())
    if total == 0:
        return {"ece": None, "gap": None, "n": 0, "reason": "empty"}

    exact = sum(
        Fraction(s[0], total) * abs((s[1] / s[0]) - Fraction(s[2], s[0]))
        for s in bins.values()
    )
    exact_gap = (
        sum(s[1] for s in bins.values()) - sum(s[2] for s in bins.values())
    ) / Fraction(total)

    # The producer's order, verbatim, in doubles. This is the value that must
    # match the committed one exactly; anything else is re-deriving the
    # producer's rounding and calling it agreement.
    value = sum(
        (s[0] / total) * abs((float(s[1]) / s[0]) - (s[2] / s[0]))
        for s in bins.values()
    )
    gap = (
        sum(float(s[1]) for s in bins.values()) - sum(s[2] for s in bins.values())
    ) / total

    out: dict[str, Any] = {
        "ece": round(value * 100, 4),
        "gap": round(gap * 100, 4),
        "n": total,
        "ece_exact": round(float(exact) * 100, 6),
        "gap_exact": round(float(exact_gap) * 100, 6),
    }
    if total < MIN_CELL_N:
        out["ece"] = None
        out["reason"] = f"below_min_cell_n:{total}<{MIN_CELL_N}"
    return out


def table(
    rows: Sequence[Mapping[str, str]],
    policies: Mapping[str, Callable[[Mapping[str, str]], bool]],
    baseline_name: str = "A_today",
) -> dict[str, dict[str, Any]]:
    baseline = fold(rows, policies[baseline_name]) if baseline_name in policies else None
    out: dict[str, dict[str, Any]] = {}
    for name, keep in policies.items():
        result = fold(rows, keep)
        if baseline is None:
            result["delta_ece"] = None
        elif result["ece"] is not None and baseline["ece"] is not None:
            result["delta_ece"] = round(result["ece"] - baseline["ece"], 4)
        else:
            result["delta_ece"] = None
        out[name] = result
    return out


def compare(
    label: str, committed: Mapping[str, Any], derived: Mapping[str, Any]
) -> list[str]:
    """Field-by-field, naming every difference. Silence here is the receipt."""
    problems: list[str] = []
    for field in ("ece", "gap", "n", "delta_ece"):
        if field not in committed:
            continue
        want, got = committed.get(field), derived.get(field)
        if want != got:
            problems.append(f"{label}.{field}: committed {want!r} != re-derived {got!r}")
    # The exact pass is a second, independent witness to the same field. It is
    # allowed to differ in the fourth decimal and nowhere else.
    if committed.get("ece") is not None and derived.get("ece_exact") is not None:
        drift = abs(committed["ece"] - derived["ece_exact"])
        if drift > ROUNDING_SLACK_PP:
            problems.append(
                f"{label}.ece: exact-rational {derived['ece_exact']} differs from "
                f"committed {committed['ece']} by {drift:.6f} pp — beyond rounding"
            )
    return problems


def verify(artifact: Mapping[str, Any]) -> dict[str, Any]:
    schema = artifact.get("raw_rows_schema")
    if not schema:
        return {
            "verdict": False,
            "reason": (
                "no raw_rows_schema — this artifact commits answers, not inputs, "
                "and cannot be re-derived (attack 1's original finding)"
            ),
            "problems": [],
        }

    problems: list[str] = []
    checked = {"cells_row_fold": 0, "cells_whole_market": 0, "pooled": 0}
    pooled_rows: list[dict[str, str]] = []
    pooled_market_rows: list[dict[str, str]] = []

    for key, cell in sorted(artifact.get("cells", {}).items()):
        if "raw_rows" in cell:
            rows = as_dicts(cell["raw_rows"], schema["row_fold"])
            pooled_rows.extend(rows)
            derived = table(rows, ROW_POLICIES)
            for name, committed in cell.get("policies", {}).items():
                problems += compare(f"{key}.policies.{name}", committed, derived[name])
            checked["cells_row_fold"] += 1

        market = cell.get("whole_market") or {}
        if "raw_rows" in market:
            rows = as_dicts(market["raw_rows"], schema["whole_market"])
            pooled_market_rows.extend(rows)
            derived = table(rows, MARKET_POLICIES)
            for name, committed in market.get("policies", {}).get("all_legs", {}).items():
                problems += compare(
                    f"{key}.whole_market.all_legs.{name}", committed, derived[name]
                )
            pop = table(rows, MARKET_POPULATION_LEG_POLICIES, baseline_name="")
            for name, committed in (
                market.get("policies", {}).get("population_legs", {}).items()
            ):
                problems += compare(
                    f"{key}.whole_market.population_legs.{name}",
                    {k: v for k, v in committed.items() if k != "delta_ece"},
                    pop[name],
                )
            checked["cells_whole_market"] += 1

    # THE HEADLINE. Re-folded from the concatenation of every cell's committed
    # bins — never an average of the per-cell ECEs, which is the arithmetic that
    # produced the cert's 4.2831 and cannot produce 1.7422 from any artifact.
    if pooled_rows and "pooled" in artifact:
        derived = table(pooled_rows, ROW_POLICIES)
        for name, committed in artifact["pooled"].items():
            problems += compare(f"pooled.{name}", committed, derived[name])
        checked["pooled"] += 1

    if pooled_market_rows and "pooled_whole_market" in artifact:
        derived = table(pooled_market_rows, MARKET_POLICIES)
        for name, committed in artifact["pooled_whole_market"].get("all_legs", {}).items():
            problems += compare(
                f"pooled_whole_market.all_legs.{name}", committed, derived[name]
            )
        pop = table(pooled_market_rows, MARKET_POPULATION_LEG_POLICIES, baseline_name="")
        for name, committed in (
            artifact["pooled_whole_market"].get("population_legs", {}).items()
        ):
            problems += compare(
                f"pooled_whole_market.population_legs.{name}",
                {k: v for k, v in committed.items() if k != "delta_ece"},
                pop[name],
            )
        checked["pooled"] += 1

    # The cert's own counter-example, recomputed so the receipt states the size
    # of what it just closed rather than asserting the closure.
    cell_average = None
    if pooled_market_rows:
        cells = [
            c["whole_market"]["policies"]["all_legs"]["C_exclude_hindsight"]["ece"]
            for c in artifact.get("cells", {}).values()
            if (c.get("whole_market") or {})
            .get("policies", {})
            .get("all_legs", {})
            .get("C_exclude_hindsight", {})
            .get("ece")
            is not None
        ]
        if cells:
            cell_average = round(sum(cells) / len(cells), 4)

    if not checked["cells_row_fold"] and not checked["cells_whole_market"]:
        problems.append("no cell carried raw_rows — nothing was re-derived")

    return {
        "verdict": not problems,
        "problems": problems,
        "checked": checked,
        "unweighted_cell_average_C_whole_market": cell_average,
        "note": (
            "The cell average is printed as the counter-example, not as a "
            "measurement: it is what an artifact of answers can produce, and it "
            "is not the pooled figure."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact")
    parser.add_argument("--out", help="write the receipt as JSON")
    args = parser.parse_args()

    with open(args.artifact) as handle:
        artifact = json.load(handle)

    receipt = verify(artifact)
    receipt["artifact"] = args.artifact

    text = json.dumps(receipt, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text)
        print(f"wrote {args.out}", file=sys.stderr)

    for problem in receipt["problems"][:40]:
        print(problem, file=sys.stderr)
    print(
        f"RECEIPT verdict={receipt['verdict']} checked={receipt['checked']} "
        f"problems={len(receipt['problems'])} "
        f"cell_average_C={receipt['unweighted_cell_average_C_whole_market']}",
        file=sys.stderr,
    )
    if not args.out:
        print(text)
    return 0 if receipt["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
