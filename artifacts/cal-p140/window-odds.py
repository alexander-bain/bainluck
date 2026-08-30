#!/usr/bin/env python3
"""CAL-P140 — what are the odds this window reaches 22/24, given the miss classes
that are still live?

THE QUESTION THIS ANSWERS AND THE ONE IT DOES NOT
--------------------------------------------------
`calibration_freeze_score.py` says where the window stands. This says where it is
GOING, and it exists because the two are being confused: a window at 4/5 with one
miss reads as comfortable, and it is not, because the miss that already happened
is from a class that has never been repaired and fires at a measurable rate.

It does NOT predict the freeze. It prices the remaining budget against the
measured base rate of each surviving class, and it prints the class breakdown so
a reader can reject the rate rather than the arithmetic.

THE REGIME PROBLEM — WHY THE RATE IS NOT JUST 65/168
-----------------------------------------------------
The ring spans three regimes and pooling them is the mistake this script is
written to avoid:

  * **pre-v3921** — class D (the sports `read:events` cancel) is live. Repaired
    by `3200b840`; CAL-P139 §2 measured it firing once since deploy and not at
    all in the 29 h after. Beats before that deploy over-state the rate.
  * **the key outage**, 2026-08-29T01:38Z -> 20:21Z — class A saturates. CAL-P139
    §2 showed all twelve gate refusals in the ring fall inside it and none
    outside. Those A's are measurements of a missing Redis key, not of the
    producer. Including them over-states the rate enormously.
  * **now** — A is quiet, D is repaired, and what remains is B (the diagnostics
    statement) and C (deploy kills).

So the rate is computed on the third regime and, because that regime is short,
on the widest band that excludes the other two. Both are printed. Where the
bands disagree, the disagreement IS the finding.

WHY C IS COUNTED
----------------
A deploy-killed beat is exogenous to the producer and it spends freeze budget
exactly like any other miss. Ruling 009's amendment is explicit — "No beat is
excused; that is the point of a budget." A forecast that excuses C would be
forecasting a different condition from the one that has to be met.

USAGE
-----
    source ~/.claude/.env && python3 artifacts/cal-p140/window-odds.py
    python3 artifacts/cal-p140/window-odds.py --json
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request

WINDOW = 24
CLEAN_REQUIRED = 22
MISSES_ALLOWED = WINDOW - CLEAN_REQUIRED

#: The v3921 deploy — the baseline the previous freeze attempt was scored from,
#: and the instant class D stops being live.
V3921_AT = "2026-08-28T18:55:19Z"

#: The key outage, bracketed by CAL-P139 §2 to the second: first gate refusal
#: 01:38:36Z, key rewritten 20:27:39Z, last refusal ever recorded 20:21:15Z.
KEY_OUTAGE = ("2026-08-29T01:38:00Z", "2026-08-29T20:27:39Z")

#: The re-baseline: the first beat that published after the key was rewritten.
REBASELINE_AT = "2026-08-29T23:35:53Z"

#: plan.deadline_ms, read off `calibration:main:phase_ledger`. A beat whose
#: elapsed exceeds it ran out of window rather than hitting a fixed timeout.
DEADLINE_MS = 1_380_000

SQL_RING = (
    "SELECT o::text AS obs FROM durable_state_snapshots d, "
    "jsonb_array_elements(d.payload->'observations') o "
    "WHERE d.identity = 'calibration:beat_gauge_history' "
    "ORDER BY (o->>'generation')::bigint"
)


def parse(text):
    stamp = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.astimezone(datetime.timezone.utc)


def fetch(api: str, token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/admin/db-query",
        data=json.dumps({"sql": SQL_RING, "limit": 400}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    rows = payload.get("rows") or []
    if not rows:
        # gotcha #53 — an empty 200 is a shape. An empty ring means the sampler
        # is down, and a base rate computed from it would be a fabrication.
        raise RuntimeError("beat_gauge_history returned no observations — sampler down")
    return [json.loads(r[0]) for r in rows]


def classify(obs: dict) -> str:
    outcome = obs.get("outcome") or {}
    terminal = obs.get("terminal")
    gate = outcome.get("gate")
    if outcome.get("published") is True and terminal == "complete" and gate == "pass":
        return "CLEAN"
    if gate == "refuse":
        return "A_GATE_REFUSAL"
    if terminal == "cancelled":
        return "C_DEPLOY_KILL"
    if terminal == "failed" and gate == "not_evaluated":
        # Sub-split. NOT a partition — 15/33 of this class ran past the deadline
        # and 18 did not, and 2/67 clean beats also ran past it. It is an
        # association with a mechanism, printed as counts so it can be argued
        # with, and it is why the two halves are reported separately.
        over = (obs.get("elapsed_ms") or 0) > DEADLINE_MS
        return "B_WINDOW_EXHAUSTION" if over else "BD_EARLY_CANCEL"
    return "UNCLASSIFIED"


def binom_at_most(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Bin(n, p). Exact; n is 24."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


#: Moving-block bootstrap settings. The block length is the point: misses are
#: CLUSTERED — deploy kills arrive in bursts of releases, and a squeezed window
#: stays squeezed for as long as the futures rebuild is heavy — so resampling
#: individual beats i.i.d. would under-state the spread. Blocks of 3 preserve
#: short runs. This is the same instrument the amendment used to choose 22/24,
#: applied to the question the amendment left open: what the rate is NOW.
BOOTSTRAP_BLOCK = 3
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260830


def bootstrap_miss_rate(sequence: list[bool], *, draws=BOOTSTRAP_DRAWS,
                        block=BOOTSTRAP_BLOCK, seed=BOOTSTRAP_SEED) -> dict:
    """CI for the miss rate of a short, autocorrelated beat sequence.

    ``sequence`` is one bool per beat, True for a miss. Seeded, so the banked
    artifact is reproducible; a CI that moves between runs is not evidence.

    Returns ``None`` when the band is shorter than one block — a bootstrap over
    two beats is a number with no information in it, and printing one would give
    a thin band the appearance of a measured one.
    """
    n = len(sequence)
    if n < block:
        return None
    rng = random.Random(seed)
    rates = []
    for _ in range(draws):
        drawn: list[bool] = []
        while len(drawn) < n:
            start = rng.randrange(n)
            # Circular blocks, so every beat is equally likely to be sampled;
            # non-circular blocks systematically under-weight both ends, which
            # on a 13-beat band is most of the band.
            drawn.extend(sequence[(start + i) % n] for i in range(block))
        rates.append(sum(drawn[:n]) / n)
    rates.sort()
    return {
        "point": round(sum(sequence) / n, 4),
        "ci90": [round(rates[int(draws * 0.05)], 4), round(rates[int(draws * 0.95)], 4)],
        "draws": draws,
        "block": block,
        "seed": seed,
        "n_beats": n,
    }


def band(observations, *, start=None, end=None, exclude=None):
    kept = []
    for obs in observations:
        stamp = parse(obs["generated_at"])
        if start and stamp < start:
            continue
        if end and stamp > end:
            continue
        if exclude and exclude[0] <= stamp <= exclude[1]:
            continue
        kept.append(obs)
    return kept


def summarise(name: str, observations: list[dict], *, note: str) -> dict:
    counts: dict[str, int] = {}
    for obs in observations:
        cls = classify(obs)
        counts[cls] = counts.get(cls, 0) + 1
    total = len(observations)
    clean = counts.get("CLEAN", 0)
    return {
        "band": name,
        "note": note,
        "beats": total,
        "clean": clean,
        "misses": total - clean,
        "miss_rate": round((total - clean) / total, 4) if total else None,
        "class_counts": counts,
        "oldest": observations[0]["generated_at"] if observations else None,
        "newest": observations[-1]["generated_at"] if observations else None,
    }


def project(miss_rate: float, *, beats_remaining: int, misses_spent: int) -> dict:
    """Odds the window still reaches 22/24, given what it has already spent."""
    budget_left = MISSES_ALLOWED - misses_spent
    if budget_left < 0:
        return {"miss_rate": miss_rate, "beats_remaining": beats_remaining,
                "budget_left": budget_left, "p_condition_met": 0.0,
                "note": "budget already overspent"}
    p = binom_at_most(budget_left, beats_remaining, miss_rate)
    return {
        "miss_rate": miss_rate,
        "beats_remaining": beats_remaining,
        "budget_left": budget_left,
        "expected_further_misses": round(beats_remaining * miss_rate, 2),
        "p_condition_met": round(p, 4),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    api, token = os.environ.get("BAINLUCK_API"), os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API and ADMIN_TOKEN required", file=sys.stderr)
        return 2

    try:
        observations = fetch(api, token)
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"could not read the ring: {exc}", file=sys.stderr)
        return 2

    outage = (parse(KEY_OUTAGE[0]), parse(KEY_OUTAGE[1]))
    bands = [
        summarise("whole-ring", observations,
                  note="all three regimes pooled — printed only so the pooling error is visible"),
        summarise("post-v3921, key-outage excluded",
                  band(observations, start=parse(V3921_AT), exclude=outage),
                  note="THE OPERATIVE BAND: D repaired, A's key-outage saturation removed"),
        summarise("post-rebaseline", band(observations, start=parse(REBASELINE_AT)),
                  note="the live window itself — too short to be a rate, printed as the check"),
    ]

    operative = bands[1]
    live = bands[2]
    beats_remaining = WINDOW - live["beats"]
    forecasts = [
        project(operative["miss_rate"], beats_remaining=beats_remaining,
                misses_spent=live["misses"]),
    ]

    # How much of the headline number is the band being 13 beats long? Answered
    # rather than caveated: the CI is carried into the forecast so a reader sees
    # the range of conclusions the evidence actually supports.
    operative_beats = band(observations, start=parse(V3921_AT), exclude=outage)
    misses_sequence = [classify(o) != "CLEAN" for o in operative_beats]
    boot = bootstrap_miss_rate(misses_sequence)
    if boot:
        forecasts.append({
            **project(boot["ci90"][0], beats_remaining=beats_remaining,
                      misses_spent=live["misses"]),
            "counterfactual": f"optimistic end of the measured rate's 90% CI "
                              f"({boot['n_beats']} beats, moving-block bootstrap)",
        })
        forecasts.append({
            **project(boot["ci90"][1], beats_remaining=beats_remaining,
                      misses_spent=live["misses"]),
            "counterfactual": "pessimistic end of the same CI",
        })
    # The optimistic counterfactual: deploy kills are the one class a human can
    # choose to stop, by not releasing during the window. Priced separately
    # because it is the only lever anyone actually holds.
    without_c = operative["beats"] - operative["class_counts"].get("C_DEPLOY_KILL", 0)
    misses_without_c = operative["misses"] - operative["class_counts"].get("C_DEPLOY_KILL", 0)
    if without_c:
        forecasts.append(
            {
                **project(round(misses_without_c / without_c, 4),
                          beats_remaining=beats_remaining, misses_spent=live["misses"]),
                "counterfactual": "no releases during the window (class C suppressed)",
            }
        )
    # The ceiling. 0.95 is the publish rate the amendment itself names as healthy
    # (`P_AT_HEALTHY_RATE` in calibration_freeze_score.py, where a fresh window
    # succeeds 0.884 of the time). Printed so the reader can see that even a
    # producer performing as well as the ruling imagines is not comfortable once
    # one of two misses is already spent — which is the difference between
    # "the window is behind" and "the rate is wrong".
    forecasts.append(
        {
            **project(0.05, beats_remaining=beats_remaining, misses_spent=live["misses"]),
            "counterfactual": "the amendment's own healthy 0.95 publish rate — a ceiling, not a forecast",
        }
    )

    result = {
        "instrument": "CAL-P140 window-odds",
        "condition": f"{CLEAN_REQUIRED} of {WINDOW}",
        "deadline_ms": DEADLINE_MS,
        "bands": bands,
        "operative_rate_bootstrap": boot,
        "live_window": {
            "beats_so_far": live["beats"],
            "misses_so_far": live["misses"],
            "budget": MISSES_ALLOWED,
            "beats_remaining": beats_remaining,
        },
        "forecasts": forecasts,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("CAL-P140 WINDOW ODDS — " + result["condition"])
    for b in bands:
        print(f"\n  [{b['band']}]  {b['note']}")
        print(f"    {b['beats']} beats, {b['clean']} clean, {b['misses']} misses"
              + (f", miss rate {b['miss_rate']:.3f}" if b["miss_rate"] is not None else ""))
        for cls, n in sorted(b["class_counts"].items(), key=lambda kv: -kv[1]):
            print(f"      {cls:<24} {n}")
    if boot:
        print(f"\n  operative miss rate {boot['point']:.3f}, 90% CI "
              f"[{boot['ci90'][0]:.3f}, {boot['ci90'][1]:.3f}] "
              f"({boot['n_beats']} beats, {boot['draws']} moving-block draws, "
              f"block {boot['block']}, seed {boot['seed']})")
    print(f"\n  live window: {live['beats']}/{WINDOW} beats, {live['misses']} misses, "
          f"{MISSES_ALLOWED - live['misses']} of {MISSES_ALLOWED} budget left, "
          f"{beats_remaining} beats to go")
    for f in forecasts:
        tag = f.get("counterfactual", "measured rate carried forward")
        print(f"\n    at miss rate {f['miss_rate']:.3f}  ({tag})")
        print(f"      expected further misses: {f['expected_further_misses']} "
              f"against a budget of {f['budget_left']}")
        print(f"      P(condition met) = {f['p_condition_met']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
