#!/usr/bin/env python3
"""Measure the published-pair-coherence exclusion (CAL-P100) on the rule that ships.

WHAT IS BEING MEASURED, AND WHY IT IS OWED RATHER THAN INCLUDED
---------------------------------------------------------------
``SUBCOHORT_DIAGNOSIS.md`` item 2 check 2 established, on the 2,438
``baseball/quantity`` Over/Under pairs that are COHERENT at opening, that the
OPENING means sum to 1.0001 and the PUBLISHED means sum to 0.8749. A pair
captured coherently is published as two numbers that cannot both be forecasts of
the same binary, and the curve grades the platform on them.

The exclusion that follows from it is built and shipped. Its DELTA is not
measured, and under ruling 134 the build lane may not measure it: this is the
instrument that lets the measurement lane do so.

WHY THIS FOLD CANNOT REPEAT CERT-403B's DEFECT
-----------------------------------------------
CERT-403B blocked an exclusion whose evidence executed a BROADER predicate than
the rule it claimed to measure, and nothing could have caught it, because the
fold and the builder shared no code. CERT-406B then blocked the rework because
the evidence executed a different POPULATION than the one that publishes.

This fold restates neither. It renders ``_calibration_population_ctes`` — the
same chain the payload publishes from, carrying ``is_liquid``,
``is_poly_placeholder``, the malformed/result-authority gates, field
completeness, mode filtering and the ``ELSE ro.rn = 1`` representative rule,
because they ARE that chain — and aggregates ``deduped``.

Baseline vs proposed is **one expression**:
``published_pair_coherence_enabled=False`` renders
``is_published_pair_incoherent`` as ``false``, switching the rule off at its
single definition and therefore off in ``field_completeness``, in ``deduped``
and in the removal counter at once. Nothing else about the population differs,
by construction rather than by inspection.

TWO THINGS THAT WILL COST YOU IF YOU SKIP THEM
-----------------------------------------------
1. **This is an ATTENDED-DYNO fold with no bisect, and it must not grow one.**
   The cell is restricted at the FINAL select, not at ``market_info``, and that
   is not an optimisation miss: ``vm_id`` is assigned by ``group_sizes`` /
   ``event_sizes`` COUNTing over ``market_info``, so narrowing it re-derives
   virtual identity instead of replaying it — a group of three straddling the
   cell becomes a group of two and ``is_grouped`` flips. An id-chunked version
   returns a number that looks like this one and answers a different question.

2. **A timeout is a named refusal carrying ``measured: false``, never an empty
   fold reading as "the exclusion removes nothing"** (gotcha #53). The two
   answers are the same response shape and opposite facts.

Usage (one-off dyno; the admin endpoint clamps to 1,350 s and will not say so):
    heroku run:detached -a bainluck \\
      "python3 backend/scripts/fold_published_pair_coherence.py --out artifacts/cal-p100"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    PUBLISHED_PAIR_CELL_CATEGORY,
    PUBLISHED_PAIR_CELL_MARKET_TYPE,
    PUBLISHED_PAIR_CELL_SOURCE,
    PUBLISHED_PAIR_RULE_TEXT,
    _calibration_population_ctes,
    published_pair_incoherent_market_predicate,
)
from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE  # noqa: E402
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    POPULATION_SOURCE,
    ece_from_bins,
    gap_from_bins,
)


def published_reading_sql(league: str, market_type: str, *, enabled: bool) -> str:
    """The cell's PUBLISHED rows, out of the shared builder, through ``deduped``.

    Emits per truth class and bin the sufficient statistics AND an ordered
    row-identity digest, so the two readings are compared by the identities of
    the rows that moved rather than by an aggregate that could match for the
    wrong reason (the standard ``C-FOLD-REWRITE-1``'s G1 sets).

    ``resolution_source`` is read back from ``futures_outcomes`` rather than
    added to the shipping chain's projection: a measurement does not get to
    widen the population's projection, because that changes the thing measured.
    """
    chain = _calibration_population_ctes(published_pair_coherence_enabled=enabled)
    return f"""
WITH {chain},
cell AS (
    SELECT d.outcome_id, d.market_id, d.adj_opening_probability AS p, d.is_winner,
           CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
                THEN 'eligible' ELSE 'ineligible' END AS truth
    FROM deduped d
    JOIN futures_outcomes fo ON fo.id = d.outcome_id
    WHERE d.source = '{POPULATION_SOURCE}'
      AND d.category = '{league}'
      AND d.market_type = '{market_type}'
)
SELECT truth,
       LEAST(FLOOR(p * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(p) AS sum_prob,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners,
       MD5(STRING_AGG(outcome_id::text, ',' ORDER BY outcome_id)) AS row_identity
FROM cell
GROUP BY 1, 2
ORDER BY 1, 2
""".strip()


def _fold(rows) -> dict[str, dict[int, dict]]:
    out: dict[str, dict[int, dict]] = {}
    for truth, b, n, sum_prob, winners, identity in rows:
        out.setdefault(truth, {})[int(b)] = {
            "n": int(n),
            "sum_prob": float(sum_prob or 0),
            "winners": int(winners or 0),
            "row_identity": identity,
        }
    return out


def _summarise(bins_by_truth: dict[str, dict[int, dict]], truth: str) -> dict:
    bins = list(bins_by_truth.get(truth, {}).values())
    ece, n = ece_from_bins(bins)
    return {"ece": ece, "n": n, "gap": gap_from_bins(bins), "bins": len(bins)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--league", default=PUBLISHED_PAIR_CELL_CATEGORY)
    parser.add_argument("--market-type", default=PUBLISHED_PAIR_CELL_MARKET_TYPE)
    parser.add_argument("--timeout-ms", type=int, default=5_400_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    if POPULATION_SOURCE != PUBLISHED_PAIR_CELL_SOURCE:
        # The shipped rule is source-scoped and this fold's population comes from
        # a different constant. Diverged, the fold would measure a population the
        # rule does not apply to — CERT-403B's defect in a different hat. Refuse
        # rather than publish a mismatched number.
        print(
            f"ERROR: population source {POPULATION_SOURCE!r} != shipped cell scope "
            f"{PUBLISHED_PAIR_CELL_SOURCE!r}",
            file=sys.stderr,
        )
        return 2

    started = time.monotonic()
    readings: dict[str, dict] = {}
    folded: dict[str, dict] = {}
    for name, enabled in (("baseline", False), ("proposed", True)):
        sql = published_reading_sql(args.league, args.market_type, enabled=enabled)
        result = dbq_run(sql, timeout_ms=args.timeout_ms)
        if result.get("status") != "ok" or result.get("truncated"):
            # The whole point of gotcha #53: this is a REFUSAL, not a zero.
            readings[name] = {
                "measured": False,
                "reason": result.get("reason") or result.get("status") or "unknown",
                "truncated": bool(result.get("truncated")),
            }
            continue
        bins = _fold(result.get("rows") or [])
        folded[name] = bins
        readings[name] = {
            "measured": True,
            "eligible": _summarise(bins, "eligible"),
            "ineligible": _summarise(bins, "ineligible"),
        }

    out: dict = {
        "rule": PUBLISHED_PAIR_RULE_TEXT,
        "predicate": published_pair_incoherent_market_predicate("mrs"),
        "pair_sum_tolerance": PAIR_SUM_TOLERANCE,
        "cell": (
            f"{PUBLISHED_PAIR_CELL_SOURCE}/{args.league}/{args.market_type}"
        ),
        "readings": readings,
        "elapsed_s": round(time.monotonic() - started, 1),
    }

    if readings.get("baseline", {}).get("measured") and readings.get(
        "proposed", {}
    ).get("measured"):
        base = readings["baseline"]["eligible"]
        prop = readings["proposed"]["eligible"]
        # Criterion 4, from the two readings rather than from a candidate count.
        # ``bins_whose_row_identity_changed`` is the falsifier that matters: if
        # the exclusion touched bins it should not have, the rule has a
        # normalization side effect and is not the local edit it claims to be.
        moved = [
            b
            for b in set(folded["baseline"].get("eligible", {}))
            | set(folded["proposed"].get("eligible", {}))
            if folded["baseline"].get("eligible", {}).get(b, {}).get("row_identity")
            != folded["proposed"].get("eligible", {}).get(b, {}).get("row_identity")
        ]
        out["criterion_4"] = {
            "published_rows_removed": (base["n"] - prop["n"])
            if base["n"] is not None and prop["n"] is not None
            else None,
            "ece_delta": (
                round(prop["ece"] - base["ece"], 2)
                if base["ece"] is not None and prop["ece"] is not None
                else None
            ),
            "bins_whose_row_identity_changed": sorted(moved),
        }

    path = Path(args.out)
    path.mkdir(parents=True, exist_ok=True)
    dest = path / "published_pair_coherence.json"
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nwrote {dest}")
    # A run in which either reading refused is NOT a success — "it returned" is
    # not "it worked" (``app/utils/task_verdict.py``'s whole reason to exist).
    return 0 if all(r.get("measured") for r in readings.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
