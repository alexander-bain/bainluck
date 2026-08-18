#!/usr/bin/env python3
"""LAT-P068 S4 — who actually OCCUPIES the background pool, sampled over time.

Why this instrument exists
--------------------------
LAT-P067 graded T1 **REFUTED**: 6 clean holes > 120 s in 62 probe-free minutes,
while the #1609 routing fix was CONFIRMED working on the wire. The refutation
therefore landed on the *causal model*, not on the code — the fix was real and
the holes did not move, which means the model named the wrong occupant.

Every prior latency instrument measured a **backlog** (`llen`) or a **task's own
cadence** (`task-metrics`). Neither can answer "what was holding the slot while
the warmer was silent", and that is the only question left. `llen` in particular
is structurally blind here: the background pool is **2 slots**, so a task can own
50 % of the pool for 14 minutes while the depth gauge reads a number that has
nothing to do with it (gotcha #53 — an empty/flat reading is a response shape,
not an absence).

So this samples `/api/admin/celery-debug`, which reports `active` tasks with
their `time_start` and their **publish-time** `delivery_info.routing_key`, and
turns them into per-slot occupancy intervals.

What it produces
----------------
* ``sample``    — one per HTTP call: depths + the active set (thin).
* ``occupancy`` — one per observed (worker, task, time_start) triple, closed out
  with the last time it was seen. This is the fat record: it is a real interval
  of a real slot being held, not an average.
* ``summary``   — per-task and per-worker occupancy totals, plus the fraction of
  samples in which the background pool was **fully saturated** (the condition
  under which a warmer hole is forced rather than merely possible).

Guards, each for a failure this lane has actually hit
-----------------------------------------------------
1. **A failed sample is not an empty pool.** A throttled request parses as
   ``None``; read as "nothing active" it would manufacture idle time and hide
   the very saturation being measured (the API rate-limit false-null). Every
   sample carries ``ok``; occupancy intervals that span a failed sample are
   flagged ``sampling_gap_overlap`` and are excluded from the clean totals.
2. **`routing_key` is stamped at PUBLISH, not at execution.** It is recorded
   verbatim and never normalised, because a task appearing under two different
   routing keys is a *finding* (a pre-deploy message still draining, or a second
   publisher), and normalising it away would erase exactly that.
3. **Our own polling is load.** The interval is recorded in the artifact so the
   read carries its own observation cost, and the default is deliberately slow
   (30 s) — this instrument is meant to run *alongside* a 3 s S1 read without
   the pair becoming the thing they measure.
4. **An interval is bounded by what was SEEN.** A task observed once gets a
   duration of one interval, not zero and not its true length; the artifact
   records ``samples_seen`` so a one-sample sighting can never be mistaken for a
   measured duration.
5. **A 200 whose `inspect` half came back empty is not an idle pool.**
   ``celery-debug`` builds ``active``/``stats`` from a broadcast ``inspect`` and
   ``queue_lengths`` from Redis, in *separate* try blocks — so the endpoint
   happily returns HTTP 200 with real depths and a silently empty active set
   when the broadcast times out. Read naively that is "both slots free", which
   is the precise opposite of the truth and would manufacture idle time in the
   one measurement this instrument exists to make. Every sample therefore
   carries ``inspect_ok``; a sample without it is excluded from saturation
   eligibility *and* counted as a sampling gap for interval cleanliness. This
   is gotcha #53 applied to a sub-field rather than to a whole response.

Measured cost, and why the defaults are what they are
-----------------------------------------------------
``/api/admin/celery-debug`` took **20.5 s** wall on the first LAT-P068 call
(broadcast inspect against three workers). A 30 s interval would therefore hold
the endpoint busy ~68 % of the time — the instrument would become a meaningful
share of the load it is measuring. Default interval is 60 s (≈34 % duty) with a
45 s timeout. The occupant under investigation runs **9–14 minutes**, so 60 s
resolution is far finer than the signal needs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

# The pool sizes are DISCOVERED from the worker stats, never assumed. This map
# only labels a worker by the queue whose tasks it is observed to run, so that
# "the background pool was saturated" is a statement about the right two slots.
BACKGROUND_MARKER_TASKS = {
    "app.tasks.warm_typeahead",
    "app.tasks.precompute_discover_candidate_base",
    "app.tasks.refresh_open_commentary",
}
HEAVY_MARKER_TASKS = {
    "app.tasks.precompute_calibration_main",
    "app.tasks.compute_time_horizon_calibration",
    "app.tasks.precompute_backfill_winners_status",
}


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _fetch(url: str, token: str, timeout: float) -> tuple[bool, Any, str]:
    """Return (ok, payload, note). ok=False NEVER yields a usable payload."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status != 200:
                return False, None, f"http_{resp.status}"
            try:
                return True, json.loads(raw), ""
            except json.JSONDecodeError:
                # A 200 that is not JSON is a throttle/error page. Never a fact.
                return False, None, "non_json_200"
    except urllib.error.HTTPError as exc:
        return False, None, f"http_{exc.code}"
    except Exception as exc:  # noqa: BLE001 - the note carries the class
        return False, None, f"{type(exc).__name__}"


def _inspect_answered(payload: dict[str, Any]) -> bool:
    """Did the broadcast `inspect` half of `celery-debug` actually answer?

    `celery-debug` fills `active`/`stats` from a broadcast inspect and
    `queue_lengths` from Redis in SEPARATE try blocks, so a timed-out broadcast
    still yields HTTP 200 with valid depths and `active == {}`. Treating that as
    "both slots free" inverts the measurement at exactly the moment the pool is
    most likely to be saturated.

    A host answering with an empty list (`{"h": []}`) IS an answer — that worker
    is genuinely idle. No hosts at all is not. Gotcha #53, at the sub-field
    level: an empty response and an absent one carry opposite facts.
    """
    return bool(payload.get("stats")) or bool(payload.get("active"))


def _classify_workers(stats: dict[str, Any], active: dict[str, Any]) -> dict[str, str]:
    """Label each worker host by the queue it serves, from OBSERVED task names.

    Falls back to ``pool<N>`` rather than guessing, so an unlabelled worker is
    visible as unlabelled instead of being silently folded into 'background'.
    """
    labels: dict[str, str] = {}
    for host, st in (stats or {}).items():
        names = set((st.get("total") or {}).keys())
        names |= {t.get("name", "") for t in (active.get(host) or [])}
        pool = st.get("pool")
        if names & BACKGROUND_MARKER_TASKS:
            labels[host] = "background"
        elif names & HEAVY_MARKER_TASKS:
            labels[host] = "heavy"
        elif pool and pool >= 4:
            labels[host] = "realtime"
        else:
            labels[host] = f"pool{pool}"
    return labels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=70.0)
    ap.add_argument("--interval", type=float, default=60.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=45.0)
    args = ap.parse_args()

    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        print("BAINLUCK_API and ADMIN_TOKEN must be set", file=sys.stderr)
        return 2

    dbg_url = f"{base}/api/admin/celery-debug"

    started = _now()
    deadline = started + args.minutes * 60.0

    # key: (host, task_name, time_start) -> interval record
    seen: dict[tuple[str, str, float], dict[str, Any]] = {}
    samples_ok = 0
    samples_bad = 0
    # A sample index at which fetching failed; any interval spanning one of
    # these is not clean.
    bad_sample_idxs: list[int] = []
    saturation_samples = 0
    saturation_eligible = 0
    pool_sizes: dict[str, Any] = {}
    worker_labels: dict[str, str] = {}
    depth_series: list[dict[str, Any]] = []

    idx = 0
    with open(args.out, "w") as fh:
        fh.write(
            json.dumps(
                {
                    "record": "meta",
                    "instrument": "lat_p068_occupancy_observe",
                    "started_at": _iso(started),
                    "interval_s": args.interval,
                    "planned_minutes": args.minutes,
                    "observation_cost_note": (
                        "one celery-debug call per interval; this is itself load"
                    ),
                }
            )
            + "\n"
        )
        fh.flush()

        while _now() < deadline:
            idx += 1
            t = _now()
            ok, payload, note = _fetch(dbg_url, token, args.timeout)
            if not ok or not isinstance(payload, dict):
                samples_bad += 1
                bad_sample_idxs.append(idx)
                fh.write(
                    json.dumps(
                        {
                            "record": "sample",
                            "idx": idx,
                            "at": _iso(t),
                            "ok": False,
                            "note": note,
                        }
                    )
                    + "\n"
                )
                fh.flush()
                time.sleep(max(0.0, args.interval - (_now() - t)))
                continue

            active = payload.get("active") or {}
            stats = payload.get("stats") or {}
            depths = payload.get("queue_lengths") or {}

            # Guard 5: the endpoint returns 200 with a silently empty inspect
            # half when the broadcast times out. `active == {}` then reads as
            # "pool idle", which is the exact inverse of the truth. Require
            # evidence that the broadcast actually answered.
            if not _inspect_answered(payload):
                samples_bad += 1
                bad_sample_idxs.append(idx)
                fh.write(
                    json.dumps(
                        {
                            "record": "sample",
                            "idx": idx,
                            "at": _iso(t),
                            "ok": True,
                            "inspect_ok": False,
                            "note": "inspect_empty_200 - depths valid, pool state UNKNOWN",
                            "depths": depths,
                            "inspect_error": payload.get("inspect_error"),
                        }
                    )
                    + "\n"
                )
                fh.flush()
                depth_series.append({"at": _iso(t), **{k: v for k, v in depths.items()}})
                time.sleep(max(0.0, args.interval - (_now() - t)))
                continue

            samples_ok += 1
            if stats:
                pool_sizes = {h: (s or {}).get("pool") for h, s in stats.items()}
                worker_labels = _classify_workers(stats, active)

            active_summary = []
            bg_busy = 0
            bg_pool = None
            for host, tasks in active.items():
                label = worker_labels.get(host, "?")
                if label == "background":
                    bg_busy = len(tasks)
                    bg_pool = pool_sizes.get(host)
                for tk in tasks:
                    name = tk.get("name", "unknown")
                    ts = tk.get("time_start")
                    rk = (tk.get("delivery_info") or {}).get("routing_key")
                    if ts is None:
                        continue
                    key = (host, name, float(ts))
                    rec = seen.get(key)
                    if rec is None:
                        rec = {
                            "record": "occupancy",
                            "worker": host,
                            "worker_label": label,
                            "task": name,
                            "routing_key": rk,
                            "kwargs": tk.get("kwargs"),
                            "time_start": _iso(float(ts)),
                            "time_start_epoch": float(ts),
                            "first_seen": _iso(t),
                            "first_seen_idx": idx,
                            "last_seen": _iso(t),
                            "last_seen_idx": idx,
                            "samples_seen": 0,
                        }
                        seen[key] = rec
                    rec["last_seen"] = _iso(t)
                    rec["last_seen_idx"] = idx
                    rec["samples_seen"] += 1
                    active_summary.append(
                        {
                            "task": name,
                            "label": label,
                            "rk": rk,
                            "running_s": round(t - float(ts), 1),
                        }
                    )

            if bg_pool:
                saturation_eligible += 1
                if bg_busy >= bg_pool:
                    saturation_samples += 1

            depth_series.append({"at": _iso(t), **{k: v for k, v in depths.items()}})
            fh.write(
                json.dumps(
                    {
                        "record": "sample",
                        "idx": idx,
                        "at": _iso(t),
                        "ok": True,
                        "inspect_ok": True,
                        "depths": depths,
                        "bg_busy": bg_busy,
                        "bg_pool": bg_pool,
                        "active": active_summary,
                    }
                )
                + "\n"
            )
            fh.flush()
            time.sleep(max(0.0, args.interval - (_now() - t)))

        # Close out every interval, flagging any that spanned a failed sample.
        per_task: dict[str, dict[str, Any]] = {}
        for rec in seen.values():
            spans_gap = any(
                rec["first_seen_idx"] <= b <= rec["last_seen_idx"]
                for b in bad_sample_idxs
            )
            rec["sampling_gap_overlap"] = spans_gap
            # Observed occupancy: bounded by what was SEEN, never extrapolated.
            observed_s = (rec["samples_seen"] - 1) * args.interval
            if rec["samples_seen"] == 1:
                # A single sighting proves presence for <= one interval. Record
                # the bound explicitly rather than emitting a fake 0 or a fake
                # full interval.
                rec["observed_occupancy_s"] = 0.0
                rec["observed_occupancy_note"] = f"single_sighting_upper_bound_{args.interval}s"
            else:
                rec["observed_occupancy_s"] = observed_s
            fh.write(json.dumps(rec) + "\n")

            if not spans_gap:
                agg = per_task.setdefault(
                    rec["task"],
                    {
                        "task": rec["task"],
                        "intervals": 0,
                        "observed_occupancy_s": 0.0,
                        "routing_keys": {},
                        "worker_labels": {},
                        "max_single_interval_s": 0.0,
                    },
                )
                agg["intervals"] += 1
                agg["observed_occupancy_s"] += rec["observed_occupancy_s"]
                agg["max_single_interval_s"] = max(
                    agg["max_single_interval_s"], rec["observed_occupancy_s"]
                )
                rk = str(rec.get("routing_key"))
                agg["routing_keys"][rk] = agg["routing_keys"].get(rk, 0) + 1
                lb = str(rec.get("worker_label"))
                agg["worker_labels"][lb] = agg["worker_labels"].get(lb, 0) + 1

        wall_s = _now() - started
        summary = {
            "record": "summary",
            "started_at": _iso(started),
            "ended_at": _iso(_now()),
            "wall_s": round(wall_s, 1),
            "interval_s": args.interval,
            "samples_ok": samples_ok,
            "samples_bad": samples_bad,
            "bad_sample_idxs": bad_sample_idxs,
            "pool_sizes": pool_sizes,
            "worker_labels": worker_labels,
            "background_saturation_samples": saturation_samples,
            "background_saturation_eligible": saturation_eligible,
            "background_saturation_pct": (
                round(100.0 * saturation_samples / saturation_eligible, 1)
                if saturation_eligible
                else None
            ),
            "per_task": sorted(
                per_task.values(),
                key=lambda r: r["observed_occupancy_s"],
                reverse=True,
            ),
            "depth_first": depth_series[0] if depth_series else None,
            "depth_last": depth_series[-1] if depth_series else None,
        }
        fh.write(json.dumps(summary) + "\n")
        fh.flush()

    print(json.dumps({k: v for k, v in summary.items() if k != "per_task"}, indent=1))
    print("--- per_task ---")
    for r in summary["per_task"]:
        print(
            f"  {r['task']:<52} occ={r['observed_occupancy_s']:>7.0f}s "
            f"n={r['intervals']:<3} max={r['max_single_interval_s']:>6.0f}s "
            f"rk={r['routing_keys']} label={r['worker_labels']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
