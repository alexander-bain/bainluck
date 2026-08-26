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
because they ARE that chain — and reads ``deduped``.

Baseline vs proposed is **one expression**:
``published_pair_coherence_enabled=False`` renders
``is_published_pair_incoherent`` as ``false``, switching the rule off at its
single definition and therefore off in ``field_completeness``, in ``deduped``
and in the removal counter at once. Nothing else about the population differs,
by construction rather than by inspection.

WHY THE ADMIN HTTP RAIL IS NOT USED HERE (C-PUBLISHED-PAIR-1, both P1s)
-----------------------------------------------------------------------
The first version of this fold made two ``POST /api/admin/db-query`` row
requests and passed ``--timeout-ms 5400000``. Neither half of that worked, and
the cert blocked on it:

1. **The row path refuses ``timeout_ms`` and is hard-coded to 10 s.**
   ``admin_data_quality.py`` raises ``"`timeout_ms` is only supported with
   `explain: true`"`` and then executes under ``SET LOCAL statement_timeout =
   '10s'``. So the advertised 5,400 s bound could not be "put in the request
   body" — a request carrying it is REFUSED, and a request omitting it silently
   runs under 10 s. The canonical calibration chain is already known to exceed
   that rail, so the instrument could not obtain its readings at all.
2. **Two admin requests are two snapshots.** Even had both finished, concurrent
   calibration writes between them would show as row movement that the exclusion
   did not cause — an attribution the artifact then could not defend.

Both readings therefore run on ONE direct connection inside ONE
``REPEATABLE READ, READ ONLY`` transaction, with the budget applied as a
database ``statement_timeout`` rather than an HTTP socket timeout. That makes
the pair one snapshot by construction, and it removes the 1,000-row response cap
that made row-level evidence impossible on the old rail.

WHAT THE ARTIFACT MUST PROVE, AND WHY BIN NUMBERS COULD NOT
------------------------------------------------------------
Criterion 4 is this Tier-1 change's stated kill: the exclusion removes the
flagged published rows and does nothing else. The old artifact emitted only
``bins_whose_row_identity_changed``. That list cannot answer it in either
direction — every bin holding a legitimately excluded row MUST appear changed,
so "changed" does not separate expected removal from an unrelated survivor
entering or leaving; and the digest hashed outcome IDs alone, so a survivor
whose normalized probability moved but stayed inside its decile left the digest
untouched and escaped the kill entirely.

This version compares ROWS. Both readings return ``(outcome_id, market_id, p,
is_winner, truth)``, and the same snapshot yields the flagged market set out of
the shipped ``published_pair_incoherent_markets`` CTE, so "expected removed" is
the builder's own answer rather than a second opinion. The verdict is exact set
arithmetic:

* ``added``   — in proposed, not in baseline. Must be empty.
* ``mutated`` — survivor whose ``(p, is_winner, truth)`` changed AT ALL, whether
  or not it crossed a bin edge. Must be empty.
* ``removed`` — must equal exactly the baseline rows in flagged markets.

Per-bin counts, sums, winners and identities are emitted for both readings and
both truth classes, so the bin table is readable evidence rather than the proof
itself.

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

Usage (one-off dyno — ``DATABASE_URL`` must be set; there is no HTTP fallback,
because the rail that would provide one cannot answer this question):
    heroku run:detached -a bainluck \\
      "python3 backend/scripts/fold_published_pair_coherence.py --out artifacts/cal-p100"
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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

from fold_cohort_cell_eligible import (  # noqa: E402
    POPULATION_SOURCE,
    ece_from_bins,
    gap_from_bins,
)

#: How many outcome IDs an evidence list carries before it is capped. The COUNT
#: is always exact and always emitted; only the enumeration is bounded, and a
#: capped list says so in its own key rather than looking complete.
ID_LIST_CAP = 20_000

#: Read once before and once after the two readings. ``pg_current_snapshot()``
#: is the visibility snapshot itself and ``now()`` is the TRANSACTION timestamp,
#: so under REPEATABLE READ both are fixed for the life of the transaction.
SNAPSHOT_PROBE_SQL = (
    "SELECT pg_current_snapshot()::text AS snapshot, now()::text AS tx_time, "
    "current_setting('transaction_isolation') AS isolation, "
    "current_setting('statement_timeout') AS statement_timeout"
)


def published_reading_sql(league: str, market_type: str, *, enabled: bool) -> str:
    """The cell's PUBLISHED rows, out of the shared builder, through ``deduped``.

    Emits ROWS, not bins. The old aggregate could not support criterion 4: bin
    membership is derived downstream in Python from these same rows, so the two
    readings are compared by the identities AND the values of the rows that
    moved, rather than by a digest that could match for the wrong reason.

    ``resolution_source`` is read back from ``futures_outcomes`` rather than
    added to the shipping chain's projection: a measurement does not get to
    widen the population's projection, because that changes the thing measured.
    """
    chain = _calibration_population_ctes(published_pair_coherence_enabled=enabled)
    return f"""
WITH {chain}
SELECT d.outcome_id, d.market_id, d.adj_opening_probability AS p, d.is_winner,
       CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth
FROM deduped d
JOIN futures_outcomes fo ON fo.id = d.outcome_id
WHERE d.source = '{POPULATION_SOURCE}'
  AND d.category = '{league}'
  AND d.market_type = '{market_type}'
ORDER BY d.outcome_id
""".strip()


def flagged_markets_sql() -> str:
    """The market IDs the shipped rule flags, out of the shipped CTE.

    This is what makes "expected removed" the BUILDER's answer. Re-deriving the
    flagged set from the predicate here would be CERT-403B's defect wearing the
    hat of a cross-check: the fold would agree with itself and prove nothing.
    """
    chain = _calibration_population_ctes(published_pair_coherence_enabled=True)
    return f"""
WITH {chain}
SELECT market_id FROM published_pair_incoherent_markets
""".strip()


def bin_of(p: float) -> int:
    """``LEAST(FLOOR(p * 10), 9)`` — the curve's decile, in Python.

    Moved off SQL deliberately. The comparison needs rows anyway, and one
    definition consumed by both the bin table and the mutants is one definition
    a mutant can actually reach.
    """
    return min(int(p * 10), 9)


def rows_by_outcome(rows) -> dict[int, dict]:
    """``(outcome_id, market_id, p, is_winner, truth)`` tuples -> keyed rows."""
    out: dict[int, dict] = {}
    for outcome_id, market_id, p, is_winner, truth in rows:
        out[int(outcome_id)] = {
            "market_id": int(market_id),
            "p": float(p),
            "is_winner": bool(is_winner),
            "truth": str(truth),
        }
    return out


def _row_value(row: dict) -> tuple:
    """Everything about a row that the exclusion is forbidden to change.

    ``p`` is compared EXACTLY, not by bin. The same-bin normalization mutant is
    the one the previous artifact could not see: a survivor renormalized from
    0.61 to 0.68 stays in bin 6, leaves an outcome-ID digest untouched, and
    still moves the curve.
    """
    return (row["p"], row["is_winner"], row["truth"])


def fold_bins(rows: dict[int, dict]) -> dict[str, dict[int, dict]]:
    """Per truth class and decile: n, sum_prob, winners, and a row identity.

    The identity hashes ``outcome_id:p:is_winner`` — not the outcome ID alone.
    A digest over IDs answers "are these the same rows"; criterion 4 has to
    answer "are these the same rows with the same values".
    """
    grouped: dict[str, dict[int, list[tuple[int, dict]]]] = {}
    for outcome_id, row in sorted(rows.items()):
        grouped.setdefault(row["truth"], {}).setdefault(bin_of(row["p"]), []).append(
            (outcome_id, row)
        )

    out: dict[str, dict[int, dict]] = {}
    for truth, by_bin in grouped.items():
        for b, members in by_bin.items():
            digest = hashlib.md5(
                ",".join(
                    f"{oid}:{r['p']!r}:{int(r['is_winner'])}" for oid, r in members
                ).encode()
            ).hexdigest()
            out.setdefault(truth, {})[b] = {
                "n": len(members),
                "sum_prob": sum(r["p"] for _, r in members),
                "winners": sum(1 for _, r in members if r["is_winner"]),
                "row_identity": digest,
            }
    return out


def _summarise(bins_by_truth: dict[str, dict[int, dict]], truth: str) -> dict:
    bins = list(bins_by_truth.get(truth, {}).values())
    ece, n = ece_from_bins(bins)
    return {"ece": ece, "n": n, "gap": gap_from_bins(bins), "bins": len(bins)}


def _bin_table(bins_by_truth: dict[str, dict[int, dict]], truth: str) -> dict:
    """Per-bin evidence, keyed by bin, with the sums rounded for readability."""
    return {
        str(b): {
            "n": v["n"],
            "sum_prob": round(v["sum_prob"], 6),
            "winners": v["winners"],
            "row_identity": v["row_identity"],
        }
        for b, v in sorted(bins_by_truth.get(truth, {}).items())
    }


def _id_list(ids) -> dict:
    """An exact count, and an enumeration that admits when it is capped."""
    ordered = sorted(ids)
    return {
        "count": len(ordered),
        "ids": ordered[:ID_LIST_CAP],
        "ids_truncated": len(ordered) > ID_LIST_CAP,
    }


def _snapshot_proof(raw: dict) -> dict:
    """Turn the two bracketing probes into a verdict the reader can check.

    ``one_snapshot`` is the claim the whole instrument rests on. It is emitted
    as a measured boolean with both readings beside it, so a future reader can
    disagree with the verdict without re-running the fold.
    """
    def _probe(name: str) -> dict | None:
        result = raw.get(name) or {}
        if not result.get("measured") or not result.get("rows"):
            return None
        snapshot, tx_time, isolation, timeout = result["rows"][0]
        return {
            "snapshot": str(snapshot),
            "tx_time": str(tx_time),
            "isolation": str(isolation),
            "statement_timeout": str(timeout),
        }

    opened, closed = _probe("snapshot_open"), _probe("snapshot_close")
    return {
        "opened": opened,
        "closed": closed,
        "one_snapshot": bool(
            opened
            and closed
            and opened["snapshot"] == closed["snapshot"]
            and opened["tx_time"] == closed["tx_time"]
        ),
    }


def compare_readings(
    baseline: dict[int, dict],
    proposed: dict[int, dict],
    flagged_market_ids: set[int],
) -> dict:
    """Criterion 4, as exact row arithmetic. Pure — this is what the mutants hit.

    The verdict is ``local`` only when all three hold:

    * nothing was ADDED (the rule may not admit a row the baseline excluded);
    * nothing SURVIVING changed value, by any amount, in or out of its bin;
    * what was REMOVED is exactly the baseline rows in the flagged markets.

    Any one of those failing means the measured ECE delta is not attributable to
    this rule, which is the whole thing criterion 4 exists to decide.
    """
    baseline_ids = set(baseline)
    proposed_ids = set(proposed)

    removed = baseline_ids - proposed_ids
    added = proposed_ids - baseline_ids
    expected_removed = {
        oid for oid, row in baseline.items() if row["market_id"] in flagged_market_ids
    }

    mutated = []
    for oid in sorted(baseline_ids & proposed_ids):
        before, after = baseline[oid], proposed[oid]
        if _row_value(before) != _row_value(after):
            mutated.append(
                {
                    "outcome_id": oid,
                    "before": {
                        "p": before["p"],
                        "bin": bin_of(before["p"]),
                        "is_winner": before["is_winner"],
                        "truth": before["truth"],
                    },
                    "after": {
                        "p": after["p"],
                        "bin": bin_of(after["p"]),
                        "is_winner": after["is_winner"],
                        "truth": after["truth"],
                    },
                    # Named so the two normalization mutants are distinguishable
                    # in the artifact rather than only in the pass/fail bit.
                    "crossed_bin": bin_of(before["p"]) != bin_of(after["p"]),
                }
            )

    unexpectedly_removed = removed - expected_removed
    expected_but_kept = expected_removed - removed
    local = not added and not mutated and not unexpectedly_removed and not expected_but_kept

    return {
        "removed": _id_list(removed),
        "expected_removed": _id_list(expected_removed),
        "unexpectedly_removed": _id_list(unexpectedly_removed),
        "expected_but_kept": _id_list(expected_but_kept),
        "added": _id_list(added),
        "mutated_survivors": {
            "count": len(mutated),
            "same_bin": sum(1 for m in mutated if not m["crossed_bin"]),
            "cross_bin": sum(1 for m in mutated if m["crossed_bin"]),
            "rows": mutated[:ID_LIST_CAP],
            "rows_truncated": len(mutated) > ID_LIST_CAP,
        },
        "flagged_markets": len(flagged_market_ids),
        "locality_verdict": "local" if local else "not_local",
    }


async def _read_one_snapshot(statements: dict[str, str], timeout_ms: int) -> dict:
    """Execute every statement on ONE connection in ONE REPEATABLE READ snapshot.

    The isolation level is the point, not decoration: baseline and proposed are
    two renderings of the same population, so they have to see the same rows.
    Two requests, or two transactions, would let concurrent calibration writes
    appear as movement the exclusion did not cause.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.services.database import DATABASE_URL

    connect_args = {}
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        connect_args["ssl"] = "require"
    # ``pool_size=1``: one connection, and no chance of a second statement
    # silently landing on a different one and therefore a different snapshot.
    engine = create_async_engine(
        DATABASE_URL, pool_size=1, max_overflow=0, connect_args=connect_args
    )
    results: dict[str, dict] = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            # The budget the old rail advertised and could not apply. A database
            # statement_timeout is the only kind that bounds the QUERY; an HTTP
            # socket timeout bounds the wait and leaves the query running.
            await conn.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
            for name, sql in statements.items():
                started = time.monotonic()
                try:
                    rows = (await conn.execute(text(sql))).fetchall()
                except Exception as exc:  # a refusal, and it must say so
                    results[name] = {
                        "measured": False,
                        "reason": f"{type(exc).__name__}: {exc}"[:400],
                        "elapsed_s": round(time.monotonic() - started, 1),
                    }
                    # One failed statement aborts the transaction in PostgreSQL,
                    # so every later read here would fail as transaction-aborted
                    # and report a reason about the wrong statement.
                    break
                results[name] = {
                    "measured": True,
                    "rows": [tuple(r) for r in rows],
                    "row_count": len(rows),
                    "elapsed_s": round(time.monotonic() - started, 1),
                }
    finally:
        await engine.dispose()

    for name in statements:
        results.setdefault(
            name,
            {
                "measured": False,
                "reason": "not_executed: an earlier statement in the snapshot failed",
            },
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--league", default=PUBLISHED_PAIR_CELL_CATEGORY)
    parser.add_argument("--market-type", default=PUBLISHED_PAIR_CELL_MARKET_TYPE)
    parser.add_argument("--timeout-ms", type=int, default=5_400_000)
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print(
            "ERROR: DATABASE_URL not set. This fold runs on an attended dyno; the "
            "admin HTTP rail cannot answer it (row path is fixed at 10 s and "
            "refuses timeout_ms, and two requests are two snapshots).",
            file=sys.stderr,
        )
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
    # ``dict`` order is execution order. The two SNAPSHOT_PROBE reads bracket the
    # readings: under REPEATABLE READ both return the same visibility snapshot
    # and the same transaction timestamp, so the artifact PROVES one snapshot
    # instead of asserting it. If they ever differ, the pair is two readings of
    # two populations and the delta is not attributable — the same failure the
    # two-HTTP-request version had, caught rather than assumed away.
    statements = {
        "snapshot_open": SNAPSHOT_PROBE_SQL,
        "baseline": published_reading_sql(
            args.league, args.market_type, enabled=False
        ),
        "proposed": published_reading_sql(args.league, args.market_type, enabled=True),
        "flagged_markets": flagged_markets_sql(),
        "snapshot_close": SNAPSHOT_PROBE_SQL,
    }
    raw = asyncio.run(_read_one_snapshot(statements, args.timeout_ms))

    readings: dict[str, dict] = {}
    rows_by_name: dict[str, dict[int, dict]] = {}
    bins_by_name: dict[str, dict[str, dict[int, dict]]] = {}
    for name in ("baseline", "proposed"):
        result = raw[name]
        if not result.get("measured"):
            # The whole point of gotcha #53: this is a REFUSAL, not a zero.
            readings[name] = {
                "measured": False,
                "reason": result.get("reason") or "unknown",
            }
            continue
        rows = rows_by_outcome(result["rows"])
        bins = fold_bins(rows)
        rows_by_name[name] = rows
        bins_by_name[name] = bins
        readings[name] = {
            "measured": True,
            "rows_read": result["row_count"],
            "elapsed_s": result["elapsed_s"],
            "eligible": _summarise(bins, "eligible"),
            "ineligible": _summarise(bins, "ineligible"),
            "bins": {
                "eligible": _bin_table(bins, "eligible"),
                "ineligible": _bin_table(bins, "ineligible"),
            },
        }

    flagged = raw["flagged_markets"]
    readings["flagged_markets"] = (
        {"measured": True, "n_markets": flagged["row_count"]}
        if flagged.get("measured")
        else {"measured": False, "reason": flagged.get("reason") or "unknown"}
    )

    proof = _snapshot_proof(raw)
    # A pair of readings taken across two snapshots is measured and useless: the
    # movement between them is not attributable to the rule. So the proof is a
    # READING, gated with the others, not a footnote under them.
    readings["snapshot_probe"] = {
        "measured": proof["one_snapshot"],
        "reason": None
        if proof["one_snapshot"]
        else "the bracketing probes disagree — the two readings are not one snapshot",
    }

    out: dict = {
        "rule": PUBLISHED_PAIR_RULE_TEXT,
        "predicate": published_pair_incoherent_market_predicate("mrs"),
        "pair_sum_tolerance": PAIR_SUM_TOLERANCE,
        "cell": (f"{PUBLISHED_PAIR_CELL_SOURCE}/{args.league}/{args.market_type}"),
        "snapshot": {
            "isolation_requested": "REPEATABLE READ, READ ONLY",
            "statements": list(statements),
            "statement_timeout_ms": args.timeout_ms,
            "transport": "direct DATABASE_URL connection (not POST /api/admin/db-query)",
            **proof,
        },
        "readings": readings,
        "elapsed_s": round(time.monotonic() - started, 1),
    }

    all_measured = all(r.get("measured") for r in readings.values())
    if all_measured:
        base = readings["baseline"]["eligible"]
        prop = readings["proposed"]["eligible"]
        comparison = compare_readings(
            rows_by_name["baseline"],
            rows_by_name["proposed"],
            {int(r[0]) for r in flagged["rows"]},
        )
        moved = sorted(
            b
            for b in set(bins_by_name["baseline"].get("eligible", {}))
            | set(bins_by_name["proposed"].get("eligible", {}))
            if bins_by_name["baseline"].get("eligible", {}).get(b, {}).get("row_identity")
            != bins_by_name["proposed"].get("eligible", {}).get(b, {}).get("row_identity")
        )
        out["criterion_4"] = {
            "published_rows_removed": (
                (base["n"] - prop["n"])
                if base["n"] is not None and prop["n"] is not None
                else None
            ),
            "ece_delta": (
                round(prop["ece"] - base["ece"], 2)
                if base["ece"] is not None and prop["ece"] is not None
                else None
            ),
            # Retained, and demoted to context. Every bin holding an excluded row
            # MUST appear here, so on its own it separates nothing — the verdict
            # below is what decides.
            "bins_whose_row_identity_changed": moved,
            **comparison,
        }

    path = Path(args.out)
    path.mkdir(parents=True, exist_ok=True)
    dest = path / "published_pair_coherence.json"
    dest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nwrote {dest}")

    # A run in which any reading refused is NOT a success — "it returned" is not
    # "it worked" (``app/utils/task_verdict.py``'s whole reason to exist). And a
    # run whose exclusion was not LOCAL is a third outcome, not a success either:
    # the numbers are real, the attribution is not.
    if not all_measured:
        return 1
    return 0 if out["criterion_4"]["locality_verdict"] == "local" else 3


if __name__ == "__main__":
    raise SystemExit(main())
