#!/usr/bin/env python3
"""CAL-P147 — bank a scorecard render for every census the API serves.

WHY THIS EXISTS
---------------
CAL-P146 established that the freeze window's one MEASUREMENT beat (beat 14,
a real census promotion under freeze) was COUNTED and never READ: the nearest
banked render was 6 beats before and 2 after, so ten fields that moved across
the bracket are confounded with ordinary within-census drift and are
unattributable FOREVER.

`promotion-datapoint.py` now exits 4 on that, and the standing directive says
"bank a scorecard render on the beat either side of the next promotion".

That instruction has a defect: it requires a session to be awake at the right
beat. The next promotion is ~8 beats (~8 h) out and beats land on the
producer's cadence, not a session's. Vigilance already failed once here — that
is precisely how beat 14 was lost. So this banks renders on a timer instead of
on attention: every distinct census the API serves gets a render on disk,
which means whichever beat the promotion lands on is bracketed 1+1.

WHAT IT DOES NOT DO
-------------------
* It does not perturb the producer. `?bust=1` is gone from the public route and
  the admin variant QUEUES the heavy task — firing either during the freeze
  window would inject a phantom producer run into the very beat log the window
  is measuring. This polls the served payload and takes what it is given.
* It does not pass `--record`, so the CAL-P128 sigma ledger is never written.
* It does not touch the window log, and its name cannot match
  `pgrep -f "rebaseline.py --baseline-at"`, so it can never be mistaken for a
  second watcher (two watchers corrupt the log).

KNOWN LIMIT, MEASURED NOT ASSUMED
---------------------------------
The served payload lags the beat: at 15:51Z the API served 14:38:38 (beat 16)
while the producer was already at 15:37:22 (beat 17). The serve is behind a 1 h
cache and beats run 57-77 min apart, so it is NOT yet established that the
serve exposes every beat's payload — it may skip one. This banks every distinct
`generated_at` it can see, which is the most that can be captured without
perturbing the producer; `--report` prints beat coverage so the next session can
read whether skipping actually happens rather than guessing.

Read-only against production. Needs BAINLUCK_API and ADMIN_TOKEN.

    python3 render-banker.py --once            # bank the current census, exit
    python3 render-banker.py --watch           # bank every census, on a timer
    python3 render-banker.py --report          # beat coverage of banked renders
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
WINDOW_LOG = os.path.join(ROOT, "artifacts", "cal-p140", "window-log.jsonl")
SCORECARD = os.path.join(ROOT, "backend", "scripts", "calibration_scorecard.py")

#: Flat, and one level under artifacts/, because `promotion-datapoint.py`
#: discovers renders with `artifacts/*/scorecard*.txt` -- a nested directory
#: would be banked and then never found.
RENDER_DIR = os.path.join(ROOT, "artifacts", "cal-p147-renders")

#: A lane-unique token so a future session can pgrep/pkill THIS process without
#: a pattern that also matches another lane's work.
LANE_TOKEN = "CAL-P147-RENDER-BANKER"

BANK_LOG = os.path.join(RENDER_DIR, "banker-log.jsonl")

#: Rewritten every cycle. Without it, "alive and polling" and "wedged four hours
#: ago" look identical to the next session -- and this runs unattended across a
#: session boundary for the ~8 beats before the next promotion, which is exactly
#: the stretch where a silent death costs the datapoint.
HEARTBEAT = os.path.join(RENDER_DIR, "banker-heartbeat.json")

_STOP = False


def _on_signal(signum, _frame):
    global _STOP
    _STOP = True
    print(f"[banker] signal {signum} — finishing current cycle and stopping", flush=True)


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def compact(stamp: str) -> str:
    """`2026-08-30T14:38:38.114919+00:00` -> `20260830T143838-114919`."""
    keep = "".join(ch for ch in stamp if ch.isdigit() or ch in "T.")
    date_time, _, frac = keep.partition(".")
    frac = frac.replace("T", "")[:6]
    return f"{date_time[:15]}-{frac}" if frac else date_time[:15]


def fetch_payload(api: str, token: str, timeout: int = 90) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/calibration",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def load_json_prefix(path: str) -> dict:
    """Renders are a JSON object followed by a human board; take the object.

    Sessions bank renders as `<json><the printed board>`, so a strict
    `json.load` fails on every hand-banked render. Reading them strictly made
    this banker miss the 3 renders already on disk and re-bank a census it
    already had -- the same shape as CAL-P145's lesson (an instrument reporting
    its own scope as the world), caught by running the default path.
    """
    with open(path) as fh:
        return json.JSONDecoder().raw_decode(fh.read())[0]


def banked_stamps() -> set[str]:
    """Every census generated_at already on disk, from ANY session's renders."""
    stamps = set()
    for pattern in ("artifacts/*/scorecard*.txt", "artifacts/*/scorecard*.json"):
        for path in glob.glob(os.path.join(ROOT, pattern)):
            try:
                obj = load_json_prefix(path)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("generated_at"):
                stamps.add(obj["generated_at"])
    return stamps


def bank(payload: dict, stamp: str) -> tuple[bool, str]:
    """Score `payload` offline and write the render. Returns (ok, detail)."""
    os.makedirs(RENDER_DIR, exist_ok=True)
    tmp = os.path.join(RENDER_DIR, ".payload-in-flight.json")
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    out = os.path.join(RENDER_DIR, f"scorecard-{compact(stamp)}.txt")
    proc = subprocess.run(
        [sys.executable, SCORECARD, "--payload", tmp, "--out", out],
        capture_output=True,
        text=True,
        timeout=600,
    )
    try:
        os.remove(tmp)
    except OSError:
        pass
    if proc.returncode != 0:
        # A self-check failure is a real signal about the served census, not a
        # banker bug -- record it rather than swallowing it.
        return False, f"scorecard exit {proc.returncode}: {proc.stderr.strip()[:300]}"
    return True, os.path.relpath(out, ROOT)


def log_line(record: dict) -> None:
    os.makedirs(RENDER_DIR, exist_ok=True)
    with open(BANK_LOG, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def beat(record: dict, pid: int, banked: int) -> None:
    os.makedirs(RENDER_DIR, exist_ok=True)
    tmp = HEARTBEAT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(
            {
                "last_cycle_at": record["at"],
                "last_event": record["event"],
                "last_census_seen": record.get("census"),
                "censuses_banked": banked,
                "pid": pid,
                "lane_token": LANE_TOKEN,
            },
            fh,
            indent=2,
        )
    os.replace(tmp, HEARTBEAT)  # atomic: a reader never sees a half-written beat


def cycle(api: str, token: str, seen: set[str]) -> dict:
    """One poll. Never raises -- a transient 503 must not kill the banker."""
    try:
        payload = fetch_payload(api, token)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        # Calibration 503s for 1-4 min after every release; that is a wait, not
        # a failure.
        rec = {"at": utcnow(), "event": "fetch_failed", "detail": str(exc)[:200]}
        log_line(rec)
        return rec
    except json.JSONDecodeError as exc:
        rec = {"at": utcnow(), "event": "bad_json", "detail": str(exc)[:200]}
        log_line(rec)
        return rec

    stamp = payload.get("generated_at")
    if not stamp:
        rec = {"at": utcnow(), "event": "no_generated_at"}
        log_line(rec)
        return rec
    if stamp in seen:
        return {"at": utcnow(), "event": "already_banked", "census": stamp}

    ok, detail = bank(payload, stamp)
    if ok:
        seen.add(stamp)
    rec = {
        "at": utcnow(),
        "event": "banked" if ok else "bank_failed",
        "census": stamp,
        "detail": detail,
    }
    log_line(rec)
    return rec


def load_beats() -> list[dict]:
    if not os.path.exists(WINDOW_LOG):
        return []
    with open(WINDOW_LOG) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _ts(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def report() -> int:
    """Which beats have a render, and did the serve skip any censuses?"""
    beats = load_beats()
    stamps = banked_stamps()
    print("=" * 88)
    print("CAL-P147 — beat coverage of banked scorecard renders")
    print("=" * 88)
    print(f"beats logged: {len(beats)}   distinct censuses banked: {len(stamps)}")
    print()
    covered = 0
    prev_staged = None
    for b in beats:
        # NOT string equality. The beat's generated_at is the watcher's own
        # observation and the render's is the payload's; beat 16 differs from
        # its own render by 0.5 s. `promotion-datapoint.py` brackets on a 5 s
        # tolerance for exactly this reason, and a stricter test here reported
        # 0/17 covered while the sibling instrument mapped five renders.
        has = any(abs((_ts(b["generated_at"]) - _ts(s)).total_seconds()) <= 5 for s in stamps)
        covered += has
        promo = prev_staged is not None and b.get("staged_at") != prev_staged
        prev_staged = b.get("staged_at")
        mark = "RENDER" if has else "  --  "
        tag = "  <- MEASUREMENT (promotion)" if promo else ""
        print(f"  beat {b['n']:>3}  {b['generated_at'][:19]}  {mark}  {b.get('class', '')}{tag}")
    print()
    print(f"beats with a banked render: {covered}/{len(beats)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="bank the current census and exit")
    mode.add_argument("--watch", action="store_true", help="bank every census, on a timer")
    mode.add_argument("--report", action="store_true", help="beat coverage of banked renders")
    ap.add_argument(
        "--interval",
        type=int,
        default=240,
        help="seconds between polls; must stay well under the 57-77 min beat spacing",
    )
    ap.add_argument("--lane-token", default=LANE_TOKEN, help="appears in argv for a safe pkill")
    args = ap.parse_args()

    if args.report:
        return report()

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("source ~/.claude/.env first — BAINLUCK_API/ADMIN_TOKEN unset", file=sys.stderr)
        return 1

    seen = banked_stamps()
    print(f"[banker] {args.lane_token} up; {len(seen)} censuses already banked", flush=True)

    if args.once:
        rec = cycle(api, token, seen)
        print(json.dumps(rec, indent=2), flush=True)
        return 0 if rec["event"] in ("banked", "already_banked") else 1

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    while not _STOP:
        rec = cycle(api, token, seen)
        beat(rec, os.getpid(), len(seen))
        if rec["event"] != "already_banked":
            print(f"[banker] {rec['event']} {rec.get('census', '')}", flush=True)
        for _ in range(args.interval):
            if _STOP:
                break
            time.sleep(1)
    print("[banker] stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
