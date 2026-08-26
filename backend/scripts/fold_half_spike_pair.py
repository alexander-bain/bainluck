#!/usr/bin/env python3
"""Re-derive the 0.5000 half-spike exclusion on the predicate its prose proposes.

CERT-403B BLOCKED the staged exclusion on a MEASUREMENT defect. Reading the
verdict literally, because the whole point of this script is to not repeat it:

    "the committed 12.14-pp evidence executes a broader single-leg filter than
     the proposed pair-scoped predicate"

The staged rule is pair-scoped — exclude a leg only when BOTH legs of an
exactly-two-leg named Over/Under market are 0.5000 — and its own criterion 2
requires a LONE 0.5000 leg to survive. But the 12.14 artifact was produced by
``fold_arbitrate_bbq.py --exclude-half-spike``, whose whole predicate is::

    AND ROUND(fo.opening_probability, 4) <> 0.5000

No partner test. No pair-size test. No name test. The cert reconciled it
numerically: baseline 6,778 legs, committed "after" 4,686, so **2,092 legs
removed**, against only **1,826** exact-0.5000 legs in the coherent named-pair
class — **266 extra legs**, which are precisely the lone-leg class criterion 2
says must not be silently swallowed.

So 12.14 is a real number about a DIFFERENT rule, and this fold produces the
number about the proposed one.

WHAT MAKES THIS FOLD UNABLE TO REPEAT THE DEFECT
------------------------------------------------
It does not restate the predicate. It **imports** the same shape columns and the
same boolean that ``_calibration_population_ctes`` applies
(``HALF_SPIKE_PAIR_SHAPE_COLUMNS`` / ``half_spike_pair_market_predicate``), and
``tests/test_half_spike_pair_exclusion.py`` asserts the two renderings are
identical modulo alias. ``fold_spike_provenance.py`` established the weaker
version of this discipline — asserting at import that its hard-coded tolerance
still equals the shipped one — and the weaker version would not have caught
CERT-403B's defect, because the broad filter never referenced a shipped constant
at all. Sharing the text is the only form that closes it.

THREE POPULATIONS, ONE PASS
---------------------------
Every leg is tagged into exactly one class, so all three readings come from one
scan of the same rows and cannot drift by re-query:

    ``half_spike_pair`` both legs of a named O/U market are exactly 0.5000
                        -> the class the PROPOSED rule excludes
    ``lone_half``       this leg is exactly 0.5000, its market is not such a pair
                        -> the CONTROL. Criterion 2 says these must SURVIVE.
                           The broad filter drops them; this is the 266.
    ``other``           everything else

    baseline      = half_spike_pair + lone_half + other   (the cell today)
    proposed      =                   lone_half + other   (the staged rule)
    broad_filter  =                               other   (what 12.14 measured)

Reporting ``broad_filter`` alongside is deliberate: reproducing the blocked
artifact's own number from this fold is what proves the two rules differ by
measurement rather than by assertion. If ``broad_filter`` comes back at ~12.14
and ``proposed`` does not, the cert's finding is confirmed from the inside.

Usage:
    python3 backend/scripts/fold_half_spike_pair.py --out artifacts/cal-p097
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
    _calibration_population_ctes,
    HALF_SPIKE_EXACT_VALUE,
    HALF_SPIKE_PAIR_CELL_CATEGORY,
    HALF_SPIKE_PAIR_CELL_MARKET_TYPE,
    HALF_SPIKE_PAIR_CELL_SOURCE,
    half_spike_pair_market_predicate,
    half_spike_pair_shape_columns,
)
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    BISECT_FLOOR_IDS,
    POPULATION_SOURCE,
    POPULATION_STATUS,
    ece_from_bins,
    gap_from_bins,
)

#: The three leg classes, and which of them each reading keeps. The readings are
#: defined as SETS here rather than as three queries, so "the proposed rule" and
#: "what 12.14 measured" differ in exactly one named class and nowhere else.
READINGS: dict[str, tuple[str, ...]] = {
    "baseline": ("half_spike_pair", "lone_half", "other"),
    "proposed": ("lone_half", "other"),
    "broad_filter": ("other",),
}


def shard_sql(league: str, market_type: str) -> str:
    """The cell fold, tagged by leg class.

    The shape subquery is restricted to the same ``fm.id`` window and the same
    cell as the outer scan. Both restrictions are exact rather than approximate,
    and for the same reason: they filter **markets**, never outcomes. An
    outcome's ``market_id`` IS the market it belongs to, so no leg of an
    in-window in-cell market can fall outside either restriction, and the
    aggregate is still over ALL outcomes of every market it reports — which is
    the basis ``market_result_shape`` uses in production.

    That distinction is the whole ballgame. A shape aggregate computed over a
    PARTIAL market would miscount ``hs_n_outcomes`` and ``hs_half_legs``, turn
    real pairs into non-pairs and lone legs into pairs, and produce a number
    that looks fine and answers a different question — the same defect this
    script exists to correct, one layer down.
    """
    return f"""
SELECT CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       CASE WHEN {half_spike_pair_market_predicate('shp')}
                 AND ROUND(fo.opening_probability, 4) = {HALF_SPIKE_EXACT_VALUE}
            THEN 'half_spike_pair'
            WHEN ROUND(fo.opening_probability, 4) = {HALF_SPIKE_EXACT_VALUE}
            THEN 'lone_half'
            ELSE 'other' END AS legclass,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
JOIN (
       SELECT p.market_id,
                    {half_spike_pair_shape_columns('p')}
       FROM futures_outcomes p
       JOIN futures_markets m2 ON m2.id = p.market_id
       WHERE p.market_id >= {{lo}} AND p.market_id < {{hi}}
         AND m2.source = '{POPULATION_SOURCE}'
         AND m2.status = '{POPULATION_STATUS}'
         AND m2.market_type = '{market_type}'
         AND m2.llm_sport_category = '{league}'
       GROUP BY p.market_id
     ) shp ON shp.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND fm.source = '{POPULATION_SOURCE}'
  AND fm.status = '{POPULATION_STATUS}'
  AND fm.market_type = '{market_type}'
  AND fm.llm_sport_category = '{league}'
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3
""".strip()


def published_reading_sql(league: str, market_type: str, *, enabled: bool) -> str:
    """The cell's PUBLISHED rows, out of the shared builder, through ``deduped``.

    CERT-406B, verbatim:

        "the fold selects resolved Polymarket baseball/quantity outcomes with an
         opening, truth, and in-range coalesced price ... It does not execute
         ``is_liquid``, ``is_poly_placeholder``, malformed/result-authority
         gates, field completeness, mode filtering, or the ``ELSE ro.rn = 1``
         representative rule that define ``deduped`` ... the artifact proves
         arithmetic over 6,778 raw truth-eligible legs, not the before/after
         identity of the published bucket rows."

    So this reading does not select anything itself. It renders
    ``_calibration_population_ctes`` — the same chain the payload publishes from,
    with every gate the BLOCK lists, because they ARE that chain — and
    aggregates ``deduped``. ``enabled`` is the whole difference between the two
    readings: ``False`` renders ``is_half_spike_pair`` as ``false``, which
    switches the rule off at its single definition and therefore off in
    ``field_completeness``, in ``deduped``, and in the removal counter at once.
    Nothing else about the population differs, by construction rather than by
    inspection.

    THE CELL IS RESTRICTED AT THE FINAL SELECT, NOT AT ``market_info``, AND THAT
    IS NOT AN OPTIMISATION MISS
    ---------------------------------------------------------------------------
    Scoping ``market_info`` would be far cheaper and would be WRONG. ``vm_id``
    is assigned by ``group_sizes`` / ``event_sizes``, which COUNT over
    ``market_info``: narrow it and a group of three markets that straddles the
    cell becomes a group of two, ``is_grouped`` flips, and the market publishes
    under a different virtual question than it does in production. The
    ``>= 3`` gate is only meaningful over the whole population — the builder's
    own ``_virtual_market_ctes`` docstring says so, and the frozen-roster path
    exists precisely because chunking this chain requires REPLAYING the global
    assignment rather than re-deriving it on a subset.

    Which is why this statement is one scan of the whole resolved population and
    does not fit the ``db-query`` rail's fixed 10 s timeout. It is an ATTENDED
    DYNO fold. It has no bisect and it must not grow one: an id-chunked version
    of this query would return a number that looks like this one and answers a
    different question, which is the failure being repaired.

    Emits, per truth class and bin, the sufficient statistics AND an ordered
    row-identity digest, so the two readings can be compared by the identities
    of the rows that moved rather than by an aggregate that could match for the
    wrong reason (the same standard as ``C-FOLD-REWRITE-1``'s G1).
    """
    chain = _calibration_population_ctes(half_spike_pair_enabled=enabled)
    return f"""
WITH {chain},
cell AS (
    SELECT d.outcome_id, d.market_id, d.adj_opening_probability AS p, d.is_winner,
           -- ``resolution_source`` is not projected by ``ranked_outcomes``, so
           -- it is read back from the row rather than added to the shipping
           -- chain. A measurement does not get to widen the population's
           -- projection; that would change the thing being measured.
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


def run_published_reading(args) -> dict:
    """Both published readings, plus criterion 4's reconciliation.

    Criterion 4 is *"published totals move by the excluded count and no more"*.
    CERT-406B's point is that nobody had measured either side of it: the
    exclusion count came from ``normalized`` and the totals from ``deduped``, so
    the claim compared two different populations and could only ever have been
    right by luck. Here both readings come out of the same builder and the
    delta is computed from THEM.

    Reports three numbers that were previously one:

    ``candidate_excluded``     legs the rule matched (``normalized``-side).
    ``published_rows_removed`` legs that would have PUBLISHED and no longer do.
                               This is the one criterion 4 is about.
    ``rows_only_in_baseline``  the same figure derived from row IDENTITIES
                               rather than from counts. If it disagrees with
                               ``published_rows_removed`` the rule removed some
                               rows and ADDED others — a normalization or
                               representative-selection side effect — and the
                               exclusion is not the local edit it claims to be.

    Returns a ``measured: False`` block with a named reason rather than raising.
    A fold that cannot run must say so in its own artifact; the calling cert
    reads the artifact, not this process's exit code.
    """
    out: dict = {
        "measured": False,
        "reason": None,
        "runs_on": (
            "attended dyno — one scan of the whole resolved population, no "
            "bisect (see published_reading_sql: chunking market_info would "
            "re-derive vm_id and change the population being measured)"
        ),
        "readings": {},
    }
    if not args.published:
        out["reason"] = (
            "not requested — pass --published. Withheld by default because it "
            "does not fit the db-query rail and a silent timeout would look "
            "exactly like a zero-yield success (gotcha #53)."
        )
        return out

    per_reading: dict[str, dict] = {}
    for name, enabled in (("baseline", False), ("proposed", True)):
        sql = published_reading_sql(args.league, args.market_type, enabled=enabled)
        result = dbq_run(sql, timeout_ms=args.timeout_ms)
        if result.get("status") != "ok" or result.get("truncated"):
            out["reason"] = (
                f"the {name} published reading did not complete: "
                f"status={result.get('status')} reason={result.get('reason')} "
                f"truncated={result.get('truncated')}. NOT a zero — the shared "
                "builder does not fit this rail and this fold needs the "
                "attended dyno."
            )
            out["readings"] = per_reading
            return out
        bins: dict[str, list[dict]] = {}
        identities: dict[str, dict[int, str]] = {}
        for truth, b, n, sum_prob, winners, row_identity in result.get("rows") or []:
            bins.setdefault(truth, []).append(
                {"n": int(n), "sum_prob": float(sum_prob or 0), "winners": int(winners or 0)}
            )
            identities.setdefault(truth, {})[int(b)] = row_identity
        per_reading[name] = {
            "half_spike_pair_enabled": enabled,
            "sql_fingerprint": result.get("sql_fingerprint"),
            "duration_ms": result.get("duration_ms"),
            "by_truth": {
                truth: {
                    "ece": ece_from_bins(rows)[0],
                    "n": ece_from_bins(rows)[1],
                    "gap": gap_from_bins(rows),
                    "row_identity_by_bin": identities.get(truth, {}),
                }
                for truth, rows in bins.items()
            },
        }

    base = per_reading["baseline"]["by_truth"].get("eligible", {})
    prop = per_reading["proposed"]["by_truth"].get("eligible", {})
    removed = (base.get("n") or 0) - (prop.get("n") or 0)
    moved_bins = sorted(
        b
        for b in set(base.get("row_identity_by_bin", {}))
        | set(prop.get("row_identity_by_bin", {}))
        if base.get("row_identity_by_bin", {}).get(b)
        != prop.get("row_identity_by_bin", {}).get(b)
    )
    out["measured"] = True
    out["readings"] = per_reading
    out["criterion_4"] = {
        "published_rows_removed": removed,
        "bins_whose_row_identity_changed": moved_bins,
        "ece_baseline": base.get("ece"),
        "ece_proposed": prop.get("ece"),
        "note": (
            "`published_rows_removed` is the number criterion 4 constrains. The "
            "candidate-side count in `cert_403b_reconciliation` above is NOT it "
            "and the two are not required to agree: a flagged leg that was also "
            "illiquid, a placeholder, or a losing rn side never published, so "
            "the exclusion cost the curve nothing for that row."
        ),
    }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--published",
        action="store_true",
        help=(
            "also take the PUBLISHED before/after reading through the shared "
            "builder (CERT-406B). Needs the attended dyno — one scan of the "
            "whole resolved population, no bisect."
        ),
    )
    parser.add_argument("--label", default="half_spike_pair")
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--league", default=HALF_SPIKE_PAIR_CELL_CATEGORY)
    parser.add_argument("--market-type", default=HALF_SPIKE_PAIR_CELL_MARKET_TYPE)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    if POPULATION_SOURCE != HALF_SPIKE_PAIR_CELL_SOURCE:
        # The shipped exclusion is source-scoped and this fold's population comes
        # from a different constant. If they ever diverge, the fold would measure
        # a population the rule does not apply to — the CERT-403B defect wearing
        # a different hat. Refuse rather than publish a mismatched number.
        print(
            f"ERROR: population source {POPULATION_SOURCE!r} != shipped cell scope "
            f"{HALF_SPIKE_PAIR_CELL_SOURCE!r}",
            file=sys.stderr,
        )
        return 2

    template = shard_sql(args.league, args.market_type)

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    # truth -> legclass -> bin -> {n, sum_prob, winners}
    buckets: dict[str, dict[str, dict[int, dict]]] = {}
    shards: list[dict] = []
    irreducible: list[dict] = []

    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=args.timeout_ms)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            for truth, legclass, b, n, sum_prob, winners in result.get("rows") or []:
                slot = (
                    buckets.setdefault(truth, {})
                    .setdefault(legclass, {})
                    .setdefault(int(b), {"n": 0, "sum_prob": 0.0, "winners": 0})
                )
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob or 0)
                slot["winners"] += int(winners or 0)
            shards.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "duration_ms": result.get("duration_ms"),
                    "sql_fingerprint": result.get("sql_fingerprint"),
                }
            )
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

    def merge(truth: str, keep: tuple[str, ...]) -> list[dict]:
        merged: dict[int, dict] = {}
        for legclass in keep:
            for b, v in buckets.get(truth, {}).get(legclass, {}).items():
                slot = merged.setdefault(b, {"n": 0, "sum_prob": 0.0, "winners": 0})
                slot["n"] += v["n"]
                slot["sum_prob"] += v["sum_prob"]
                slot["winners"] += v["winners"]
        return [{"bin": b, **v} for b, v in sorted(merged.items())]

    summary: dict = {}
    for truth in sorted(buckets):
        per_truth: dict = {"class_counts": {}, "readings": {}}
        for legclass, bins in sorted(buckets[truth].items()):
            per_truth["class_counts"][legclass] = sum(v["n"] for v in bins.values())
        for name, keep in READINGS.items():
            bins = merge(truth, keep)
            ece, n = ece_from_bins([{k: v for k, v in b.items() if k != "bin"} for b in bins])
            per_truth["readings"][name] = {
                "ece": ece,
                "n": n,
                "gap": gap_from_bins(
                    [{k: v for k, v in b.items() if k != "bin"} for b in bins]
                ),
                "keeps_classes": list(keep),
                "bins": bins,
            }
        summary[truth] = per_truth

    elig = summary.get("eligible", {})
    counts = elig.get("class_counts", {})
    readings = elig.get("readings", {})
    removed_proposed = counts.get("half_spike_pair", 0)
    removed_broad = removed_proposed + counts.get("lone_half", 0)

    payload = {
        "label": args.label,
        "measured": not irreducible,
        "cell": {
            "source": POPULATION_SOURCE,
            "status": POPULATION_STATUS,
            "league": args.league,
            "market_type": args.market_type,
        },
        "predicate": {
            "shape_columns": half_spike_pair_shape_columns("p"),
            "market_predicate": half_spike_pair_market_predicate("shp"),
            "exact_value": HALF_SPIKE_EXACT_VALUE,
            "imported_from": "app.tasks.precompute_calibration",
            "note": (
                "IMPORTED, not restated. CERT-403B's first P1 was a fold whose "
                "filter did not match the rule it was offered as evidence for."
            ),
        },
        "cert_403b_reconciliation": {
            "legs_removed_by_proposed_rule": removed_proposed,
            "legs_removed_by_broad_filter": removed_broad,
            "lone_half_legs_the_broad_filter_swallowed": counts.get("lone_half", 0),
            "cert_claimed_extra_legs": 266,
        },
        "elapsed_s": elapsed,
        "shards": shards,
        "irreducible": irreducible,
        "summary": summary,
    }

    # ------------------------------------------------------------------
    # CERT-406B: the PUBLISHED reading. Everything above this line is
    # CANDIDATE-side and is now labelled as such — it is a true statement
    # about the raw truth-eligible legs and it reconciles CERT-403B's 266,
    # but it is NOT the before/after identity of the published bucket rows
    # and it can no longer be offered as one.
    # ------------------------------------------------------------------
    payload["scope_of_the_candidate_reading"] = (
        "CANDIDATE-side. These bins are raw truth-eligible legs; they do not "
        "execute is_liquid, is_poly_placeholder, the malformed/result-authority "
        "gates, field completeness, mode filtering, or the rn=1 representative "
        "rule. Use `published` below for anything about the curve."
    )
    payload["published"] = run_published_reading(args)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.label}.json"
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n=== {args.label} — {elapsed}s, {len(shards)} shards, "
          f"{len(irreducible)} irreducible ===")
    print(f"eligible class counts: {counts}")
    for name in ("baseline", "proposed", "broad_filter"):
        r = readings.get(name) or {}
        print(f"  {name:>13}: ECE {r.get('ece')}  n {r.get('n')}  gap {r.get('gap')}")
    print(f"legs removed — proposed {removed_proposed}, broad {removed_broad}, "
          f"lone-half difference {counts.get('lone_half', 0)}")
    print(f"wrote {out_path}")
    return 0 if not irreducible else 1


if __name__ == "__main__":
    raise SystemExit(main())
