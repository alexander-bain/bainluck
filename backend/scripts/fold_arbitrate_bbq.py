#!/usr/bin/env python3
"""Arbitrate a 0.78 pp disagreement between two measurements of ONE cell.

Two numbers exist for ``baseball/quantity``'s truth-eligible ECE at the SAME
denominator ``n = 6,778``:

* **16.64** — CAL-P093, a single whole-range ``db-query`` per cell (fp
  ``2d93a44ea9fb6022``, 5,374 ms).
* **15.86** — CAL-P094, ``fold_cohort_cell_eligible.py``, 26 sargable shards,
  0 irreducible, and reproduced a second time by ``fold_pairclass_ece.py``
  through a completely different query shape.

Their predicates are byte-comparable (same population filter, same
``COALESCE(calibration_probability, opening_probability)``, same
``LEAST(FLOOR(p*10),9)`` binning, and the pairclass fold literally *imports*
``ece_from_bins`` from the eligible fold). So the shape is not the difference,
and two agreeing shards-based measurements against one older single-shot
measurement points at TIME, not at arithmetic.

That distinction matters and is not cosmetic. If the cell moved, 15.86 is
current and 16.64 is stale — fine, publish the new one. If the cell did NOT
move, then a whole-range query and a sharded fold return different answers over
identical rows, which would mean one of them is wrong about a *live* cell and
every sharded number in the re-ranked board inherits the doubt.

The test: re-measure the cell TODAY and read the value against BOTH priors.
Three outcomes, three different conclusions:

    returns ~15.86  -> the cell moved once; 16.64 was correct when taken.
    returns ~16.64  -> shape disagreement at identical n. Real defect. Escalate.
    returns other   -> the cell is moving fast enough that neither is a fact
                       about today, and n=6,778 twice was a coincidence.

The whole-range single-shot shape is NOT reproducible: it answered in 5,374 ms
for CAL-P093 and hits ``statement_timeout`` at 10 s today (recorded in
``arbitrate_bbq.json``, ``measured: false``). So this fold shards on ``fm.id``
like every other fold in this queue, and it carries two extra columns the
originals did not, because they are what makes the temporal reading FALSIFIABLE
rather than merely plausible:

* ``n_with_calibration_probability`` — how many of these legs are priced from
  the live closing-line column at all. If that count is ~0 the temporal story
  is dead on arrival, because ``opening_probability`` is written once.
* ``MAX(last_updated)`` — a row-touch stamp, not a price-change stamp. It can
  only ever bound the claim ("nothing was written after T"); a recent value is
  consistent with a rewrite and does not demonstrate one. Reported with that
  limit attached rather than as proof.

``n`` is reported alongside, because two ECEs at the same ``n`` and two ECEs at
different ``n`` are different findings and the headline number hides which one
this is.

Usage:
    python3 backend/scripts/fold_arbitrate_bbq.py --out artifacts/cal-p094
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    POPULATION_SOURCE,
    POPULATION_STATUS,
    ece_from_bins,
    gap_from_bins,
)

from fold_cohort_cell_eligible import BISECT_FLOOR_IDS  # noqa: E402


def shard_sql(league: str = "baseball", market_type: str = "quantity") -> str:
    """The cell fold, parameterised.

    CAL-P095 generalised this from the two hard-coded literals it shipped with.
    The spike this script measures is not a ``baseball/quantity`` property —
    ``soccer/quantity`` carries the same exact-0.5000 mass at the same ~38% share
    — and the exclusion delta has to be MEASURED per cell rather than scaled from
    another cell's, for the reason this script's own header records: ECE is
    computed within bins, so a decomposition share is not an exclusion delta.

    Defaults preserve the CAL-P094 invocation byte-for-byte.
    """
    return f"""
SELECT CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners,
       COUNT(fo.calibration_probability) AS n_cal,
       MAX(fo.last_updated) AS newest_leg
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND fm.source = '{POPULATION_SOURCE}'
  AND fm.status = '{POPULATION_STATUS}'
  AND fm.market_type = '{market_type}'
  AND fm.llm_sport_category = '{league}'
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
  {{extra}}
GROUP BY 1, 2
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="arbitrate_bbq")
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--league", default="baseball")
    parser.add_argument("--market-type", default="quantity")
    parser.add_argument("--exclude-half-spike", action="store_true",
                        help="drop legs whose opening_probability is exactly "
                             "0.5000 — the #1578-family placeholder spike")
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    extra = ("AND ROUND(fo.opening_probability, 4) <> 0.5000"
             if args.exclude_half_spike else "")
    template = shard_sql(args.league, args.market_type)

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    buckets: dict[str, dict[int, dict]] = {"eligible": {}, "ineligible": {}}
    newest: dict[str, str] = {}
    n_cal: dict[str, int] = {"eligible": 0, "ineligible": 0}
    shards: list[dict] = []
    irreducible: list[dict] = []

    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi, extra=extra),
                         timeout_ms=args.timeout_ms)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            for truth, b, n, sum_prob, winners, ncal, newest_leg in result.get("rows") or []:
                slot = buckets[truth].setdefault(
                    int(b), {"n": 0, "sum_prob": 0.0, "winners": 0})
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob or 0)
                slot["winners"] += int(winners or 0)
                n_cal[truth] += int(ncal or 0)
                if newest_leg and str(newest_leg) > newest.get(truth, ""):
                    newest[truth] = str(newest_leg)
            shards.append({"lo": lo, "hi": hi, "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            print(f"  [{lo}..{hi}) ok {result.get('duration_ms')}ms", flush=True)
            continue
        width = hi - lo
        if width <= BISECT_FLOOR_IDS:
            irreducible.append({"lo": lo, "hi": hi, "reason": result.get("reason")})
            print(f"  [{lo}..{hi}) IRREDUCIBLE — {result.get('reason')}", flush=True)
            continue
        mid = lo + width // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
        print(f"  [{lo}..{hi}) {result.get('status')} — bisecting", flush=True)

    elapsed = round(time.monotonic() - started, 1)
    complete = not irreducible

    summary = {}
    for truth, bins in buckets.items():
        ece, n = ece_from_bins(list(bins.values()))
        summary[truth] = {
            "ece": ece, "n": n, "gap": gap_from_bins(list(bins.values())),
            "n_with_calibration_probability": n_cal[truth],
            "newest_leg_last_updated": newest.get(truth),
            "bins": [{"bin": b, **v} for b, v in sorted(bins.items())],
        }

    e, a = summary["eligible"], summary["ineligible"]
    print(f"\nirreducible={len(irreducible)} complete={complete} elapsed={elapsed}s")
    print(f"TODAY  ece_eligible={e['ece']} n={e['n']} gap={e['gap']}")
    print(f"       live calibration_probability on {e['n_with_calibration_probability']} "
          f"of {e['n']} eligible legs")
    print(f"       newest last_updated (row-touch, bounds the claim, does not prove it): "
          f"{e['newest_leg_last_updated']}")
    # The two priors are BASEBALL/QUANTITY readings. Printing them beside another
    # cell's number would invite exactly the cross-cell comparison this script
    # exists to forbid, so they are gated on the cell they describe.
    if (args.league, args.market_type) == ("baseball", "quantity"):
        print("CAL-P093 single-shot : 16.64 / n=6778   (ece_all 25.96 / n_all 47170)")
        print("CAL-P094 sharded x2  : 15.86 / n=6778   (ece_all 23.05 / n_all 47170)")
    print(f"       ece over ALL truth classes today: "
          f"n={(e['n'] or 0) + (a['n'] or 0)}")

    out = {"label": args.label, "measured": complete, "complete": complete,
           "shard_count": len(shards), "shards": shards,
           "irreducible": irreducible, "elapsed_s": elapsed, "summary": summary,
           "prior_measurements": {
               "cal_p093_single_shot": {"ece_eligible": 16.64, "n_eligible": 6778,
                                        "ece_all": 25.96, "n_all": 47170},
               "cal_p094_sharded": {"ece_eligible": 15.86, "n_eligible": 6778,
                                    "ece_all": 23.05, "n_all": 47170}}}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {out_dir / (args.label + '.json')}", flush=True)
    return 0 if out.get("measured") else 1


if __name__ == "__main__":
    sys.exit(main())
