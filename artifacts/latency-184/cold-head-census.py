#!/usr/bin/env python3
"""LAT-P243 / #3480 — how often does the whole 40-term search head go cold, and is
the morning compaction collision the cause?

Reads the warmer ring samples collected by `.lat182-sampler.sh` (+ its 19:10Z
continuation) and answers three questions the CERT-2038->2061 chain kept assuming
rather than measuring:

  1. How many warmer passes report `expired == head_n` (the WHOLE head cold)?
  2. Was any compaction grinder resident while those happened?
  3. Does the rate move across the #3399 shed deploy at 10:05:31Z?

WHY `expired` IS THE RIGHT COUNTER. The endpoint's own note: "passes.expired is
cache-entry loss: entries whose key was already gone when the pass reached them."
So `expired == head_n` means every head term's cache entry was absent when the
warmer arrived — i.e. a user typing any head term in that interval took the cold
path (measured elsewhere at ~1094.5ms/710 shared read blocks vs 27.1ms warm).

CAVEAT, stated because it bounds the claim: `expired` proves the ENTRY was gone,
not that a user queried during the gap. It is a proxy for user-visible coldness,
strong because the head is by definition the most-queried terms, but a proxy.
`artifacts/latency-184/headprobe-*.txt` is the independent user-shaped check.

Usage:  python3 artifacts/latency-184/cold-head-census.py .lat182-warmer-samples.jsonl
"""

import datetime as dt
import json
import statistics
import sys

UTC = dt.timezone.utc
# #3399's shed fix reached production at this instant — the cutover was observed
# live and is banked in artifacts/latency-180/postdeploy-3399-cutover.txt.
CUTOVER_3399 = dt.datetime(2026, 9, 6, 10, 5, 31, tzinfo=UTC).timestamp()
RESPONSE_TTL_S = 65   # RESPONSE_CACHE_TTL_S — a gap past this lapses the entry
EXPIRY_BUDGET_S = 120  # warm-typeahead's `expires: 120`


def fmt(epoch):
    return dt.datetime.fromtimestamp(epoch, UTC).strftime("%H:%M:%S")


def load_passes(path):
    """Union the ring records across samples, deduped by their `at` epoch.

    The ring holds only the last 32 passes, so no single sample sees the whole
    window; the union across overlapping reads is what reconstructs it.
    """
    rows = [json.loads(line) for line in open(path)]
    passes = {}
    for row in rows:
        for rec in row["ring"].get("passes", {}).get("records", []) or []:
            passes[round(rec["at"], 1)] = rec
    return rows, passes


def compaction_residency(rows):
    """Did either turbo grinder START inside the sampled window?

    `last_started_at` is a last-write-wins stamp, so it cannot be differenced —
    but it CAN be compared for change. Unchanged across every sample means no
    new start occurred, which is the only thing this needs to establish.
    """
    out = {}
    for task in ("turbo_collapse_futures", "turbo_collapse_odds"):
        stamps = {(r.get(task) or {}).get("last_started_at") for r in rows}
        out[task] = {"distinct_last_started": sorted(s for s in stamps if s)}
    return out


def report(path):
    rows, passes = load_passes(path)
    keys = sorted(passes)
    t0, t1 = rows[0]["ring"]["read_at_epoch"], rows[-1]["ring"]["read_at_epoch"]
    window = [k for k in keys if t0 <= k <= t1]

    print(f"samples          : {len(rows)}  ({rows[0]['fetched_at']} -> {rows[-1]['fetched_at']})")
    print(f"sampled window   : {fmt(t0)}Z -> {fmt(t1)}Z  ({(t1 - t0) / 60:.1f} min)")
    print(f"distinct passes  : {len(window)} in window ({len(keys)} incl. ring backfill to {fmt(keys[0])}Z)")

    gaps = sorted(window[i + 1] - window[i] for i in range(len(window) - 1))
    print(
        f"\ninter-pass gap   : p50={statistics.median(gaps):.0f}s "
        f"p95={gaps[int(len(gaps) * 0.95)]:.0f}s max={gaps[-1]:.0f}s"
    )
    print(f"  gaps > {RESPONSE_TTL_S}s (response TTL lapses) : {sum(g > RESPONSE_TTL_S for g in gaps)} of {len(gaps)}")
    print(f"  gaps > {EXPIRY_BUDGET_S}s (expiry budget blown): {sum(g > EXPIRY_BUDGET_S for g in gaps)} of {len(gaps)}")

    print("\n-- Q1: whole-head-cold passes --")
    cold = [k for k in window if passes[k]["expired"] >= passes[k]["head_n"]]
    print(f"expired == head_n on {len(cold)} of {len(window)} passes ({100 * len(cold) / len(window):.1f}%)")

    # A pass count is NOT what a user experiences. The head is cold for whatever
    # part of each inter-pass gap runs past the response TTL, so weight by wall
    # clock: one 750s gap hurts users far more than four 70s gaps, and the
    # pass-based figure scores them the other way round.
    cold_s = sum(max(0.0, g - RESPONSE_TTL_S) for g in gaps)
    span = window[-1] - window[0]
    print(
        f"COLD WALL TIME (gap beyond the {RESPONSE_TTL_S}s TTL): "
        f"{cold_s / 60:.1f} min of {span / 60:.1f} min = {100 * cold_s / span:.1f}% of the window"
    )
    print("  ^ this is the user-facing number; the pass percentage above understates it.")

    print("\n-- Q2: was a compaction grinder resident? --")
    for task, info in compaction_residency(rows).items():
        stamps = info["distinct_last_started"]
        verdict = "NO new start in window" if len(stamps) == 1 else "STARTED during window"
        print(f"  {task}: {verdict} — last_started_at {stamps}")

    print("\n-- Q3: does the rate move across the #3399 deploy? --")
    for label, keep in (
        (f"pre-#3399  (-> {fmt(CUTOVER_3399)}Z)", lambda k: k < CUTOVER_3399),
        (f"post-#3399 ({fmt(CUTOVER_3399)}Z ->)", lambda k: k >= CUTOVER_3399),
    ):
        sub = [k for k in keys if keep(k)]
        if len(sub) < 2:
            print(f"  {label}: too few passes ({len(sub)})")
            continue
        sub_cold = [k for k in sub if passes[k]["expired"] >= passes[k]["head_n"]]
        sub_gaps = sorted(sub[i + 1] - sub[i] for i in range(len(sub) - 1))
        print(
            f"  {label}: passes={len(sub)} whole-head-cold={len(sub_cold)} "
            f"({100 * len(sub_cold) / len(sub):.1f}%)  gap p50={statistics.median(sub_gaps):.0f}s "
            f"p95={sub_gaps[int(len(sub_gaps) * 0.95)]:.0f}s"
        )

    print("\n-- the cold passes, with the gap that caused each --")
    for k in cold:
        print(f"   {fmt(k)}Z  expired={passes[k]['expired']}/{passes[k]['head_n']}  period_s={passes[k]['period_s']:.1f}")


if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else ".lat182-warmer-samples.jsonl")
