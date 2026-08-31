#!/usr/bin/env python3
"""CAL-P148 — measure the serve's cache phase, and catch a skip in the act.

WHY THIS EXISTS
---------------
CAL-P147 §4 recorded that the API served census 14:38:38 (beat 16) while the
producer was already at 15:37:22 (beat 17), and flagged "the serve may skip a
census" as unsettled. It is settleable, and this probe settles it.

The mechanism is not a mystery once you read the route. ``routes/calibration.py``
serves from a **per-worker in-process dict** (``_cache``, ``CACHE_TTL = 3600``)
placed *in front of* Redis. Tier 1 returns the memo whenever it is younger than
CACHE_TTL; it does **not** consult Redis to ask whether a newer census exists.
So a worker pins whatever census it happened to fetch for a full hour.

Producer beats in this window run **48–76 min apart, mean 60.1 min**. A worker
therefore samples on a 60-minute clock a stream that advances every ~60 minutes
on average but with wide variance. That is an aliasing problem: whenever a
census's residency in Redis is shorter than the time left on a worker's clock,
that worker steps clean over it. For a *single* clock the miss rate is ~4.2% of
beats (1 in 24), resampling the 16 measured gaps.

HOW MANY CLOCKS THERE ARE — and how I got this wrong first
----------------------------------------------------------
Initially a 20-request burst at 16:07Z returned **one** distinct
``generated_at``, 20/20, and I took that for a phase-locked serve — one
effective clock, ~1 beat in 24 lost. That inference was wrong, and the probe is
what caught it: at 16:11:37Z it recorded the serve at beat 17 and at 16:14:20Z
back at beat 16. **The served stamp moved BACKWARD**, which a single clock
cannot do. A re-burst at 16:16Z split **19/5** across the two censuses.

So there are two independent clocks — ``WEB_CONCURRENCY=2``, one web dyno, two
uvicorn worker processes, each with its own ``_cache`` dict and its own phase
(they boot together but diverge, because each pins its memo at whatever moment
its own first unmarked Redis read lands). The 20/20 burst was both workers
briefly holding the same census, not one worker.

A census is skipped only if **every** clock misses it, so the rate is not 4.2%
but ~0.5% — about 1 beat in 200, and ~1 promotion bracket in 100. The lesson is
that the burst measured a coincidence and read as a mechanism; only the
time-series distinguished them.

Two consequences worth keeping: the serve reads **non-monotonically** (a client
can legitimately see an older census than it saw a moment ago), and any skip
test must be over sets across time, never over adjacent samples.

WHAT IT RECORDS
---------------
Every ``--interval`` seconds, both halves of the same question:

  * ``served``  — ``generated_at`` from the public ``/api/calibration`` (what a
    user, and the render banker, can actually see).
  * ``redis``   — ``generated_at`` from ``/api/admin/calibration/mce``, which is
    a bare ``_rc.get("bainluck:calibration:main")`` with no in-process cache in
    front of it. ``bust`` is left at its default False, so this route performs a
    pure Redis GET: it queues nothing and writes nothing. Confirmed by reading
    the handler (admin_data_quality.py:3807 — the task send is inside
    ``if bust:``). **Never pass bust.** It would queue the heavy task and inject
    a phantom producer run into the very beat log the window is measuring.

A row is written only when either stamp CHANGES, so the log is a transition
list, not a poll dump.

THE CALL IT MAKES
-----------------
When the serve finally flips off census X, the probe reports which census it
flipped TO:

  * flipped to the census that was in Redis all along  -> NO SKIP, pure lag.
  * flipped straight past it to a LATER census         -> SKIP CONFIRMED: that
    intermediate census was never exposed to any client, and no amount of
    polling could have banked it.

The second case is the one that matters, because it means some promotions are
unreadable no matter who or what is awake — a render banker cannot capture a
payload the API never served. That is an Alex-facing finding, not something to
work around.

Deliberately does NOT perturb the producer, and carries a lane-unique token so
it can be pgrep'd and killed without a pattern that touches another lane. Its
name cannot match ``rebaseline.py --baseline-at`` (the watcher) or
``CAL-P147-RENDER-BANKER`` (the banker).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
LOG_PATH = OUT_DIR / "serve-phase-log.jsonl"
HEARTBEAT_PATH = OUT_DIR / "serve-phase-heartbeat.json"

PUBLIC_PATH = "/api/calibration"
REDIS_PATH = "/api/admin/calibration/mce"  # bare Redis GET; never pass bust


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env() -> tuple[str, str]:
    """Read BAINLUCK_API / ADMIN_TOKEN out of ~/.claude/.env.

    The sandbox blocks direct curl unless the env is sourced in the same shell,
    so the values are pulled once here and passed to curl explicitly.
    """
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if api and token:
        return api, token
    env_file = Path.home() / ".claude" / ".env"
    if not env_file.exists():
        sys.exit("no BAINLUCK_API/ADMIN_TOKEN in env and no ~/.claude/.env")
    out = subprocess.run(
        ["bash", "-c", f"source {env_file} && echo \"$BAINLUCK_API\" && echo \"$ADMIN_TOKEN\""],
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    if len(out) < 2 or not out[0] or not out[1]:
        sys.exit("~/.claude/.env did not yield BAINLUCK_API + ADMIN_TOKEN")
    return out[0].strip(), out[1].strip()


def _get_json(url: str, token: str | None) -> dict | None:
    cmd = ["curl", "-s", "--max-time", "25"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd.append(url)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        # A rate-limited or 5xx response parses as valid JSON of the wrong
        # shape, or as nothing at all. Both read as "no sample", never as a
        # census change — otherwise throttling would fabricate a transition.
        return None


def sample(api: str, token: str) -> tuple[str | None, str | None]:
    pub = _get_json(f"{api}{PUBLIC_PATH}", None)
    red = _get_json(f"{api}{REDIS_PATH}", token)
    served = pub.get("generated_at") if isinstance(pub, dict) else None
    redis = red.get("generated_at") if isinstance(red, dict) else None
    return served, redis


def _load_log() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    rows = []
    for line in LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _append(row: dict) -> None:
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def _heartbeat(**kw) -> None:
    tmp = HEARTBEAT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_cycle_at": _now(), "pid": os.getpid(), **kw}, indent=2))
    tmp.replace(HEARTBEAT_PATH)


def report() -> int:
    """Print the transition list and the skip verdict."""
    rows = _load_log()
    if not rows:
        print("no samples yet")
        return 0

    print("=" * 88)
    print("CAL-P148 — serve cache phase vs Redis")
    print("=" * 88)
    print(f"{'observed_at':22} {'served (public)':32} {'redis (producer)':32}")
    for r in rows:
        print(f"{r['at'][:22]:22} {str(r['served'])[:32]:32} {str(r['redis'])[:32]:32}")

    # A skip is NOT a prev/cur transition. The serve is fronted by one in-process
    # memo PER UVICORN WORKER (WEB_CONCURRENCY=2), each with its own independent
    # 60-minute clock, so consecutive requests land on different workers and the
    # served stamp legitimately moves BACKWARD. Measured 2026-08-30T16:16Z: a
    # 24-request burst split 19/5 across two censuses. A naive adjacent-pair test
    # reads every one of those oscillations as a transition and is meaningless.
    #
    # The right test is over SETS: a census that Redis held, and that no worker
    # ever served, and that is now old enough that every worker has certainly
    # refreshed past it (> CACHE_TTL since it left Redis), was skipped by all of
    # them and is unrecoverable. Anything younger than that is merely still in
    # flight — reporting it as a skip would be the "unbracketed so far is not
    # permanent" error in a new costume.
    served_set = {r["served"] for r in rows if r["served"]}
    redis_seq = [r["redis"] for r in rows if r["redis"]]
    redis_set = set(redis_seq)

    backward = sum(
        1
        for a, b in zip(rows, rows[1:])
        if a["served"] and b["served"] and b["served"] < a["served"]
    )
    print(f"distinct censuses seen in Redis: {len(redis_set)}   ever served: {len(served_set)}")
    print(f"backward moves in the served stamp: {backward}  (>0 proves multiple independent worker clocks)")
    print()

    last_redis = redis_seq[-1] if redis_seq else None
    settled = 0
    skips = []
    for census in sorted(redis_set):
        if census == last_redis:
            continue  # still current in Redis; workers may yet pick it up
        # Time since this census was last seen in Redis.
        left_at = max(r["at"] for r in rows if r["redis"] == census)
        age_min = (
            datetime.fromisoformat(rows[-1]["at"]) - datetime.fromisoformat(left_at)
        ).total_seconds() / 60.0
        if age_min < 60.0:
            continue  # not yet settled — a worker could still be about to serve it
        settled += 1
        if census not in served_set:
            skips.append((census, left_at))

    for census, left_at in skips:
        print(
            f"🔴 SKIP  {census} was in Redis (last seen {left_at[:19]}), was superseded, and\n"
            "         no worker ever served it. That payload reached no client and cannot be banked."
        )

    print()
    if settled == 0:
        print(
            "VERDICT: no census has SETTLED yet (each needs >60 min since it left Redis, so every\n"
            "         worker clock has certainly turned over). The question is still open — keep the\n"
            "         probe running. 'Not yet served' is not 'skipped'."
        )
        return 0
    if skips:
        print(
            f"VERDICT: 🔴 SKIP CONFIRMED ({len(skips)} of {settled} settled censuses). A census entered\n"
            "         Redis and was superseded before ANY worker exposed it, so no poller could bank it\n"
            "         and a promotion landing there is unreadable to anyone. ALEX-FACING."
        )
        return 4
    print(
        f"VERDICT: ✅ no skip in {settled} settled census(es) — the serve LAGS (up to ~1 h per worker,\n"
        "         and reads non-monotonically across workers) but every settled census did reach it."
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", action="store_true", help="poll until stopped")
    ap.add_argument("--once", action="store_true", help="take a single sample")
    ap.add_argument("--report", action="store_true", help="print transitions + verdict")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--lane-token", default="CAL-P148-SERVE-PHASE-PROBE", help="lane-unique pgrep token")
    args = ap.parse_args()

    if args.report:
        return report()

    api, token = _env()
    rows = _load_log()
    last = (rows[-1]["served"], rows[-1]["redis"]) if rows else (None, None)

    while True:
        served, redis = sample(api, token)
        if (served, redis) != (None, None) and (served, redis) != last:
            _append({"at": _now(), "served": served, "redis": redis})
            last = (served, redis)
            print(f"[{_now()}] CHANGE served={served} redis={redis}", flush=True)
        _heartbeat(served=served, redis=redis, lane_token=args.lane_token, samples=len(_load_log()))
        if args.once:
            print(f"[{_now()}] served={served} redis={redis}", flush=True)
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
