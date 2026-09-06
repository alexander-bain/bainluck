#!/usr/bin/env python3
"""latency/180 ITEM 1(1) — the TOTAL demand on a queue, in worker-seconds/hour.

179's lesson (rule (tt)): a RANKING of who holds the slots does not tell you
that fixing the top of it will help. 179 took the largest consumer off a 2-slot
queue, made it 31.8x faster, and the victim's dead-second share did not fall.
The number that decides topology is a TOTAL against a CAPACITY, so this script
computes a total and reports what it could not price.

FOUR traps, all of which this script hit before it was right:

1. THE JOIN. The metrics hash is keyed by a LABEL written inside `_tracked_run`,
   not by the celery task name; only 53 of 148 labels equal the task's short
   name. `bainluck:task_metrics:label_map` is the real map and is read, never
   inferred. (`refresh_registered_tournament_prices` -> `tournament_price_refresh`.)

2. THE DENOMINATOR. `starts_24h` NAMES 24 hours and holds anywhere from 0 to 24
   of them — `_bump_window_counter` stamps the window once at the first
   increment and lets it die. Measured here: `tournament_price_refresh` has
   `starts_window_s` = 14,478s (4.0h). Dividing by 24h under-reported its rate
   by 6x, and made both queue totals read ~2.3x low across ~34 rows. The window
   is IN the payload; this script divides by it. (The codebase already says so:
   "a count without its window is not a rate".)

3. THE STRADDLE. `recent_durations_ms` is the last 50 runs, which for a 6/hr
   task spans 8.1 hours and therefore straddles a deploy. A mean over it blends
   pre- and post-change populations: `tournament_price_refresh` reads a 172.0s
   mean whose newest four samples are 5.9-9.5s and whose older 46 are 165-240s.
   Every task is step-tested (newest third vs oldest third) and, where the split
   is real, priced on the RECENT population with the old one reported beside it.

4. BIMODALITY (rule (rr)). A lock- or floor-gated task has two duration
   populations and every percentile of their union is a fiction. p50/mean/p95
   are all printed so a bimodal row is visible rather than averaged over.

Two rate arms are kept even after fixing (2), because agreement between two
independently-derived numbers is the only check available on either.
"""
import json
import statistics as st
import sys

CAPACITY = {"background": 2, "heavy": 2, "realtime": 4}  # slots
STEP_RATIO = 3.0  # newest-third vs oldest-third mean ratio that counts as a step
STEP_MIN_N = 9    # below this the thirds are too small to split on

beat = json.load(open("/tmp/lat180-beatmap.json"))
adh = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/lat180-adh0.json"))
dash = json.load(open("/tmp/lat180-dash.json"))
lm = json.load(open("/tmp/lat180-labelmap.json"))

label_of = {k: v for k, v in lm.items() if k.startswith("app.tasks.")}
by_label = {t["task"]: t for t in dash.get("tasks") or []}
arows = adh.get("all") or {}


def step_split(durs):
    """(mean_used, step_note). `durs` is newest-first.

    Returns the recent population's mean when the series has a step, else the
    whole-ring mean. A step is reported, never silently applied.

    Scans EVERY split point rather than comparing fixed thirds. A thirds test
    misses exactly the case this exists for: `tournament_price_refresh`'s step
    is in its newest FOUR samples of fifty (179's fix deployed 34 minutes before
    this read), so a newest-third mean of 16 samples still carries twelve
    pre-fix runs and reads 172s against a true 7.9s. The split with the largest
    mean ratio is chosen, requiring MIN_SIDE samples on each side so a single
    outlier cannot declare one.
    """
    MIN_SIDE, MAX_CV = 3, 0.6
    if len(durs) < STEP_MIN_N:
        return (st.mean(durs) if durs else None), ""

    def cv(xs):
        m = st.mean(xs)
        return (st.pstdev(xs) / m) if m > 0 else float("inf")

    best = None
    for i in range(MIN_SIDE, len(durs) - MIN_SIDE + 1):
        lo, hi = durs[:i], durs[i:]
        new, old = st.mean(lo), st.mean(hi)
        ratio = max(old / max(new, 1e-9), new / max(old, 1e-9))
        # A BIMODAL series is not a step, and a change-point scan cannot tell
        # them apart by ratio alone — rule (rr) in its most direct form. On
        # `warm_typeahead` (p50 0.1s / mean 16.5s, the lock-skip path against
        # the work path) the scan happily "finds" 0->17s at newest 45/50, which
        # is a run of skips and not a regime change. A real step has two TIGHT
        # populations; a bimodal split has two wide ones. Both sides must be
        # tight for the split to be believed.
        if cv(lo) > MAX_CV or cv(hi) > MAX_CV:
            continue
        if best is None or ratio > best[0]:
            best = (ratio, i, new, old)
    if best and best[0] >= STEP_RATIO:
        ratio, i, new, old = best
        return new, f"STEP {old:.0f}->{new:.0f}s @ newest {i}/{len(durs)}"
    return st.mean(durs), ""


rows = []
for task, b in beat.items():
    q = b["queue"]
    if q not in ("background", "heavy", "realtime"):
        continue
    m = by_label.get(label_of.get(task, "")) or {}
    a = arows.get(task) or {}
    durs = [d / 1000.0 for d in (m.get("recent_durations_ms") or []) if d is not None]

    # Arm A: dispatch deliveries over their OWN reported window.
    rate_a = None
    d, w = a.get("deliveries"), a.get("deliveries_window_s")
    if d is not None and w:
        rate_a = d / w * 3600.0
    # Arm B: the worker's own start counter over ITS OWN reported window.
    s, sw = m.get("starts_24h"), m.get("starts_window_s")
    rate_b = (s / sw * 3600.0) if isinstance(s, (int, float)) and sw else None

    mean, step = step_split(durs)
    srt = sorted(durs)
    rows.append({
        "task": task.rsplit(".", 1)[-1], "queue": q,
        "interval_s": b["interval_s"], "cron": b["cron"], "label": label_of.get(task),
        "rate_a": rate_a, "rate_b": rate_b, "n": len(durs), "step": step,
        "p50": st.median(durs) if durs else None, "mean": mean,
        "p95": srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))] if durs else None,
        "dwin": m.get("recent_durations_window_s"), "swin": sw,
        "verdict": a.get("verdict"),
    })


def wsec(r, arm):
    rate = r["rate_a"] if arm == "a" else r["rate_b"]
    if rate is None or r["mean"] is None:
        return None
    return rate * r["mean"]


for q in ("background", "heavy", "realtime"):
    qr = [r for r in rows if r["queue"] == q]
    cap = CAPACITY[q] * 3600
    print(f"\n{'='*112}\n{q.upper()}  —  {CAPACITY[q]} slots = {cap:,} worker-seconds/hour"
          f"  ({len(qr)} beats)\n{'='*112}")
    print(f"{'wsec/hr A':>10} {'wsec/hr B':>10} {'rate/h A':>8} {'rate/h B':>8} "
          f"{'mean':>7} {'p50':>7} {'p95':>7} {'n':>4} {'bimod':>6}  task")
    tot_a = tot_b = 0.0
    unpriced, disagree, steps = [], [], []
    for r in sorted(qr, key=lambda x: -(wsec(x, "a") or wsec(x, "b") or 0)):
        wa, wb = wsec(r, "a"), wsec(r, "b")
        if wa is None and wb is None:
            unpriced.append(r)
            continue
        tot_a += wa or 0.0
        tot_b += wb or 0.0
        bim = ""
        if r["p50"] is not None and r["mean"]:
            ratio = r["mean"] / max(r["p50"], 0.001)
            if ratio > 2 or ratio < 0.5:
                bim = f"{ratio:.1f}x"
        if r["rate_a"] and r["rate_b"] and (
                r["rate_a"] / r["rate_b"] > 1.5 or r["rate_b"] / r["rate_a"] > 1.5):
            disagree.append(r)
        if r["step"]:
            steps.append(r)
        f = lambda v: f"{v:10.0f}" if v is not None else f"{'—':>10}"  # noqa: E731
        print(f"{f(wa)} {f(wb)} {(r['rate_a'] or 0):8.2f} {(r['rate_b'] or 0):8.2f} "
              f"{(r['mean'] or 0):7.1f} {(r['p50'] or 0):7.1f} {(r['p95'] or 0):7.1f} "
              f"{r['n']:4d} {bim:>6}  {r['task']}"
              + (f"   [{r['step']}]" if r["step"] else ""))
    print(f"\n  TOTAL arm A (deliveries / deliveries_window_s): {tot_a:10,.0f} wsec/hr "
          f"= {tot_a/cap:.2f}x capacity")
    print(f"  TOTAL arm B (starts / starts_window_s):        {tot_b:10,.0f} wsec/hr "
          f"= {tot_b/cap:.2f}x capacity")
    print(f"  UNPRICED (no duration sample — a FLOOR on the total, not a zero): "
          f"{len(unpriced)} beats")
    if unpriced:
        print("    " + ", ".join(
            f"{r['task']}@{(r['rate_a'] or 0):.2f}/hr" for r in
            sorted(unpriced, key=lambda x: -(x["rate_a"] or 0))))
    if steps:
        print(f"  STEP-CHANGED (priced on the recent population): "
              + ", ".join(f"{r['task']} {r['step']}" for r in steps))
    if disagree:
        print(f"  ARMS DISAGREE >1.5x: "
              + ", ".join(f"{r['task']}(A={r['rate_a']:.2f}/B={r['rate_b']:.2f})"
                          for r in disagree))
