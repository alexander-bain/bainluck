#!/usr/bin/env python3
"""Rebuild the `/api/admin/heavy-move/falsifier` payload OFFLINE, from this
branch's falsifier module, against LIVE production task-metrics.

## Why this exists

Fable's 2026-08-22 directive (item 2) asks for the routing re-graded **"with the
corrected coverage counting AND the censoring mirror fix in place"**. Those two
fixes live in different places:

* the **coverage counting** fix (`no_new_runs` is not coverage) is CLIENT-side,
  in `grade_ruling_110.py` — it is already in effect against any payload;
* the **censoring mirror** fix (#2071, `518affd9`) is SERVER-side, in
  `app/utils/heavy_routing_falsifier.py`, and sits on `program/latency-74`,
  **which has not merged and is not deployed**. Production runs `a13239f1`.

So the live endpoint cannot answer the question that was asked. It grades with
the OLD censoring rule, which censors a beat on its `p95` — the exact defect
#2071 named, under which any clip rate above 5 % discards a beat whose grading
statistic (the p50) is perfectly readable.

The grade is a **pure function of the observations**: the route reads
`get_task_metrics(name)` for `READ_SET` and calls `grade_move(...)`. Nothing
else. So the fixed grade is obtainable today by fetching the same observations
through the public admin endpoint and running THIS branch's `grade_move` over
them locally. That is all this script does.

## 🔴 What it is NOT

It is **not** a second measurement, and it must never be reported as one. Every
number it emits comes from the same production Redis the endpoint reads, through
`GET /api/admin/celery/task-metrics/{name}`. It re-runs the GRADING, not the
MEASUREMENT. Reporting it as an independent confirmation would be inventing a
second observation out of one (doctrine clause 14).

It is also **not** a substitute for the post-deploy read. When `-74` merges and
deploys, the live endpoint becomes authoritative and this script's whole reason
to exist expires. It prints that in its own header so a later reader does not
mistake it for a permanent rail.

## Fidelity

The payload assembled here mirrors `admin_celery.heavy_move_falsifier` field for
field — same `READ_SET`, same `grade_move`, same `summarize_movers`, same
`horizon` block — so `grade_ruling_110.py` cannot tell the difference and no
second copy of any threshold is made. If the route's shape changes, this drifts,
which is why it names the route it mirrors in one place and is dated.

## Usage

    source ~/.claude/.env
    python3 backend/scripts/falsifier_offline_mirror.py --out /tmp/mirror.json
    python3 backend/scripts/grade_ruling_110.py --from-file /tmp/mirror.json

## Exit codes (gotcha #54 — read the VALUE)

    0  payload assembled
    3  a task-metrics read failed — a story about the harness, never a result
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.utils.heavy_routing_falsifier import (  # noqa: E402
    CONSUMER_CEILING_S,
    CONSUMER_FLOOR_S,
    DEGRADE_P50_RATIO,
    beat_payload,
    HEAVY_MOVE_EXCEPTION,
    POST_MOVE_RING_SHARE_REQUIRED,
    READ_SET,
    ROUTING_CHANGE_AT_EPOCH,
    RUN_COUNTER_WINDOW_S,
    grade_move,
    summarize_movers,
)

EXIT_OK = 0
EXIT_UNREADABLE = 3


def _fetch(name: str) -> dict[str, Any]:
    base = os.environ["BAINLUCK_API"]
    token = os.environ["ADMIN_TOKEN"]
    req = urllib.request.Request(
        f"{base}/api/admin/celery/task-metrics/{name}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="write the assembled payload here")
    args = ap.parse_args(argv)

    if not os.environ.get("BAINLUCK_API") or not os.environ.get("ADMIN_TOKEN"):
        print("UNREADABLE: source ~/.claude/.env first", file=sys.stderr)
        return EXIT_UNREADABLE

    observations: dict[str, Any] = {}
    for name in READ_SET:
        try:
            observations[name] = _fetch(name)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            # A failed read must NEVER render as an absent beat: an absent beat
            # grades `unreadable`, but a beat we could not fetch is a fact about
            # the network. Refuse the whole payload (gotcha #53).
            print(f"UNREADABLE: {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return EXIT_UNREADABLE

    now = time.time()
    age_s = now - ROUTING_CHANGE_AT_EPOCH
    result = grade_move(observations, now_epoch=now)

    payload = {
        "status": "ok",
        "ruling": 110,
        "_mirror": {
            "source": "OFFLINE MIRROR — grading re-run locally on program/latency-74",
            "why": (
                "the #2071 censoring-mirror fix is server-side and UNMERGED; production "
                "a13239f1 grades with the old p95-censoring rule, so the live endpoint "
                "cannot answer the question the directive asked"
            ),
            "measurement_source": "production task-metrics via GET /api/admin/celery/task-metrics/{name}",
            "not_a_second_measurement": True,
            "expires_when": "program/latency-74 deploys; the live endpoint is authoritative then",
        },
        "verdict": result.verdict,
        "reason": result.reason,
        "degrade_p50_ratio": DEGRADE_P50_RATIO,
        "consumer_floor_s": dict(CONSUMER_FLOOR_S),
        "consumer_ceiling_s": dict(CONSUMER_CEILING_S),
        "exception_tasks": sorted(HEAVY_MOVE_EXCEPTION),
        "horizon": {
            "routing_change_at_epoch": ROUTING_CHANGE_AT_EPOCH,
            "age_since_move_s": round(age_s, 1),
            "age_since_move_h": round(age_s / 3600.0, 2),
            "run_counter_window_s": RUN_COUNTER_WINDOW_S,
            "post_move_ring_share_required": POST_MOVE_RING_SHARE_REQUIRED,
            "counters_clear_the_move": age_s >= RUN_COUNTER_WINDOW_S,
        },
        "movers": summarize_movers(observations, age_since_move_s=age_s),
        # Shared with the route (`beat_payload`), never re-typed. This block
        # used to be a hand copy and #2116 caught it emitting `null` for six
        # new fields while still being read as the authoritative re-grade.
        "beats": [beat_payload(b) for b in result.beats],
    }

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"wrote {args.out}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
