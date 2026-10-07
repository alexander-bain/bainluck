"""#10678 lab — SYNTHETIC mixed-buffer comparison, baseline vs live-first.

No retained production buffer exists for this candidate, and none is
collected: every buffer here is generated from a seed. Nothing in this file is
an observed timing. Positions are counted in the two units the pinned #10655
flush actually spends per component — PHASES (one commit + publish + blend
refresh each) and ROWS (one UPDATE round trip each until #10664) — and are
reported separately, because their real-world costs are not measured here.

    cd backend && python3 ../tools/live-speed-lab/live-priority-replay.py \
        --out ../artifacts/10678-live-priority-lab/replay-results.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app.tasks.kalshi_ws import linked_first_phases  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "live_priority_planner", HERE / "live-priority-planner.py")
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)


def make_buffer(rng, n_live, n_sched, n_open, tick_share):
    """One flush's buffer: games with 1-3 two-outcome markets, plus open rows.

    ``tick_share`` is the chance each known outcome has a buffered tick this
    flush (a game with none simply is not in the batch). Arrival order is a
    uniform shuffle — the #10655 planner's first-seen order is that order.
    """
    markets, events, live = {}, {}, set()
    oid = mid = 0
    items = []
    for g in range(n_live + n_sched):
        event = 1000 + g
        if g < n_live:
            live.add(event)
        for _ in range(rng.randint(1, 3)):
            mid += 1
            for _ in range(2):  # complement pair
                oid += 1
                markets[oid], events[oid] = mid, event
                if rng.random() < tick_share:
                    items.append(oid)
    for _ in range(n_open):
        mid += 1
        oid += 1
        markets[oid] = mid
        items.append(oid)
    rng.shuffle(items)
    return {o: (0.5, 0.49, 0.51) for o in items}, markets, events, live


def positions(phases, markets, events, live):
    """Per live game: (phases strictly before its phase, rows through its last)."""
    out = []
    rows = 0
    for i, phase in enumerate(phases):
        rows += len(phase)
        touched = lp.component_events(phase, markets, events)
        if touched & live:
            out.append((i, rows))
    return out


def run(seed_count, mixes):
    results = []
    for n_live, n_sched, n_open, tick in mixes:
        cells = {"base_phase": [], "cand_phase": [], "base_rows": [],
                 "cand_rows": [], "phase_gain": [], "row_gain": [],
                 "sched_phase_delay": [], "flushes_with_live": 0,
                 "flushes_with_gain": 0}
        for seed in range(seed_count):
            rng = random.Random(seed * 7919 + n_live * 101 + n_sched)
            batch, markets, events, live = make_buffer(
                rng, n_live, n_sched, n_open, tick)
            base = linked_first_phases(batch, markets, events)
            cand = lp.live_first_phases(batch, markets, events,
                                        live_event_ids=live)
            # Re-order only: same phases, same rows, same total work.
            assert sorted(tuple(p) for p in base) == sorted(tuple(p) for p in cand)
            bp, cp = positions(base, markets, events, live), positions(
                cand, markets, events, live)
            if not bp:
                continue
            cells["flushes_with_live"] += 1
            # The LAST live game's position = when every live game is done.
            b_last, c_last = bp[-1], cp[-1]
            cells["base_phase"].append(b_last[0])
            cells["cand_phase"].append(c_last[0])
            cells["base_rows"].append(b_last[1])
            cells["cand_rows"].append(c_last[1])
            cells["phase_gain"].append(b_last[0] - c_last[0])
            cells["row_gain"].append(b_last[1] - c_last[1])
            if b_last[1] > c_last[1]:
                cells["flushes_with_gain"] += 1
            # The cost side: how much later the last SCHEDULED game finishes.
            not_live = lambda ph: [
                i for i, p in enumerate(ph)
                if (ev := lp.component_events(p, markets, events)) and not ev & live]
            bs, cs = not_live(base), not_live(cand)
            if bs:
                cells["sched_phase_delay"].append(cs[-1] - bs[-1])

        def s(xs):
            if not xs:
                return None
            xs = sorted(xs)
            return {"mean": round(statistics.mean(xs), 2),
                    "p50": xs[len(xs) // 2],
                    "p90": xs[min(len(xs) - 1, int(len(xs) * 0.9))],
                    "max": xs[-1]}

        results.append({
            "mix": {"live_games": n_live, "scheduled_games": n_sched,
                    "open_rows": n_open, "tick_share": tick},
            "flushes": seed_count,
            "flushes_with_live": cells["flushes_with_live"],
            "flushes_where_last_live_moved_earlier": cells["flushes_with_gain"],
            "last_live_phase_index": {"baseline": s(cells["base_phase"]),
                                      "candidate": s(cells["cand_phase"])},
            "rows_through_last_live": {"baseline": s(cells["base_rows"]),
                                       "candidate": s(cells["cand_rows"])},
            "phases_saved_for_last_live": s(cells["phase_gain"]),
            "rows_saved_for_last_live": s(cells["row_gain"]),
            "last_scheduled_phase_delay": s(cells["sched_phase_delay"]),
        })
    return results


MIXES = [
    # (live games, scheduled games, open rows, tick share)
    (3, 0, 40, 0.5),   # all-live control: must save nothing
    (0, 6, 40, 0.5),   # no-live control: nothing to move
    (1, 1, 40, 0.5),
    (2, 6, 40, 0.5),
    (4, 12, 40, 0.5),
    (6, 4, 40, 0.5),
    (2, 6, 40, 0.15),  # quiet pre-game books: few scheduled ticks per flush
    (8, 30, 200, 0.3),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2000)
    ap.add_argument("--out")
    args = ap.parse_args()
    res = run(args.seeds, MIXES)
    doc = {"synthetic": True,
           "note": "Generated buffers; uniform first-seen order; no observed "
                   "timing. Units are phases and rows, reported separately.",
           "planner": "app.tasks.kalshi_ws.linked_first_phases @ eaa8027a59",
           "results": res}
    text = json.dumps(doc, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n")
    for r in res:
        m = r["mix"]
        print(f"live={m['live_games']:>2} sched={m['scheduled_games']:>2} "
              f"open={m['open_rows']:>3} tick={m['tick_share']:.2f} | "
              f"moved {r['flushes_where_last_live_moved_earlier']}/"
              f"{r['flushes_with_live']} | phases saved {r['phases_saved_for_last_live']} "
              f"| rows saved {r['rows_saved_for_last_live']} "
              f"| sched delay {r['last_scheduled_phase_delay']}")


if __name__ == "__main__":
    main()
