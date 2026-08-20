#!/usr/bin/env python3
"""CAL-P082 — grade the staged rebuild PER BEAT, from the phase ledger.

``verify_rolling_restage.py`` (CAL-P079/P081) samples ``/api/calibration`` on a
wall-clock interval and asks whether the numbers MOVED between samples. That is
the right question for "is the served census advancing", and it is the wrong
instrument for the question CAL-P082 was given:

    >= 1 unit banked per unit-loop beat, verified across >= 3 CONSECUTIVE beats
    from the ledger -- not one.

Three things the payload-sampling verifier cannot do, each of which has already
produced a wrong reading in this program:

1. **It cannot tell one beat from two.** Two samples 60 s apart inside the same
   beat are one observation wearing two hats. CAL-P081's ``[13, 13]`` FAIL was
   graded on exactly that shape, and the two samples were 8 minutes apart in the
   *same* inter-beat gap. The finding was real; the sample count was one.
2. **It cannot see a GAP.** If a beat is missed -- a deploy killed it, the
   sampler was not running -- the next two rows in the file still look adjacent.
   "Three consecutive beats" then means "three rows", which is not the claim.
3. **`rebuild_advancing` grades CHANGE, not RATE.** ``len(set(banked)) > 1`` is
   satisfied by 13 -> 14 across four hours. The bar is per beat.

So this samples the LEDGER (``durable_state_snapshots`` identity
``calibration:main:phase_ledger``), which is written once per beat and carries
that beat's own ``generation``, its ``staged:units_this_beat``, and whether the
futures phase was ``carried``. Rows are keyed by ``generation``, so re-reading
the same beat can never be counted as a second one, and consecutiveness is
checked against the beat CADENCE rather than against adjacency in the file.

    python3 scripts/sample_calibration_beats.py out.jsonl              # follow
    python3 scripts/sample_calibration_beats.py out.jsonl --once       # one read
    python3 scripts/sample_calibration_beats.py out.jsonl --grade      # verdict

Exit codes follow gotcha #54's amendment: ``0`` pass, ``1`` a real failure,
``2`` could not measure. ``1`` is a result; anything else is a story about the
harness.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

#: Gauges lifted out of the ledger's ``stages`` map. Everything here is either a
#: number the grader reads or a number a human needs beside it to believe the
#: grade; the rest of the ledger is left where it is rather than copied.
LEDGER_GAUGES = (
    "staged:units_this_beat",
    "staged:units_banked",
    "staged:units_planned",
    "staged:units_completed_this_beat",
    "staged:beats_to_publish",
    "staged:unit_ms_mean",
    "staged:unit_ms_worst",
    "staged:window_left_ms",
    "staged:units_drifted",
    "staged:units_drift_checkable",
    "staged:units_drift_uncheckable",
    "staged:served_units",
    "staged:served_drifted",
    "staged:served_at",
    "staged:cursor_resume",
    "staged:units_cancelled",
)

#: The beat's scheduled period. ``precompute-calibration-main`` is
#: ``crontab(minute=15)`` -- hourly. Consecutiveness is judged against this, so
#: a missed beat reads as a GAP instead of silently closing up.
BEAT_PERIOD_S = 3600

#: How far two beats may drift from exactly one period apart and still count as
#: adjacent. A beat's ledger is written when the build FINISHES, not when it
#: starts, and finish time swings with how much work the beat did -- the
#: measured spread on 2026-08-20 was ~18 to ~22 minutes. Generous on purpose:
#: this tolerance exists to absorb a variable finish time, not to paper over a
#: skipped beat, which is a whole period away and nowhere near this band.
BEAT_ADJACENCY_SLACK_S = 1500

LEDGER_SQL = (
    "SELECT generation, generated_at, complete, payload "
    "FROM durable_state_snapshots "
    "WHERE identity = 'calibration:main:phase_ledger'"
)


# ---------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------

def _parse_stamp(value):
    """A UTC ``datetime`` from whatever the row carried, or ``None``.

    Never raises and never guesses a timezone onto a naive stamp beyond UTC,
    which is what every writer in this rail uses. ``None`` propagates as
    "unmeasurable" rather than being flattened into a default instant -- a
    default instant is how a gap becomes invisible.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        stamp = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            stamp = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.astimezone(datetime.timezone.utc)


def beat_row(record: dict, served: dict | None = None) -> dict:
    """Reduce one ledger row (+ optional served payload) to a beat observation."""
    payload = record.get("payload") or {}
    stages = payload.get("stages") or {}
    row = {
        "generation": record.get("generation"),
        "generated_at": str(record.get("generated_at")),
        "complete": record.get("complete"),
        "terminal": payload.get("terminal"),
        "carried": payload.get("carried"),
        "checkpoint_action": payload.get("checkpoint_action"),
        "checkpoint_write": payload.get("checkpoint_write"),
        "completed_required": payload.get("completed_required"),
        "elapsed_ms": payload.get("elapsed_ms"),
        "input_fingerprint": payload.get("input_fingerprint"),
        "unit_costs": payload.get("unit_costs"),
        "outcome": payload.get("outcome"),
        "stages": {k: stages.get(k) for k in LEDGER_GAUGES if k in stages},
        "staged_stage_counts": {
            k: v for k, v in (payload.get("stage_counts") or {}).items()
            if str(k).startswith("staged:")
        },
    }
    if served is not None:
        row["served"] = served
    return row


def _units_this_beat(row: dict):
    value = (row.get("stages") or {}).get("staged:units_this_beat")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _futures_carried(row: dict) -> bool:
    """Did this beat CARRY the futures phase (so the unit loop never ran)?"""
    return "futures" in (row.get("carried") or [])


def grade_consecutive(rows: list[dict], *, minimum: int = 3) -> dict:
    """PASS iff `minimum` ADJACENT beats each banked at least one unit.

    Three separate ways to fail, reported separately because they call for
    different responses:

    * ``insufficient`` -- fewer than ``minimum`` distinct beats were observed.
      This is UNMEASURABLE, not a failure of the build, and grades ``None``.
    * ``gap`` -- the observed beats are not adjacent. Also unmeasurable: a beat
      that was never sampled is not a beat that banked zero, and CAL-P081's
      whole finding was that the two look identical from outside (gotcha #53).
    * ``stalled`` -- ``minimum`` adjacent beats were observed and at least one of
      them banked nothing. This is the real FAIL.

    The window graded is the LAST ``minimum`` beats, so a run that stalls after
    a healthy stretch is not rescued by its own history.
    """
    ordered = sorted(
        (r for r in rows if r.get("generation") is not None),
        key=lambda r: r["generation"],
    )
    # Distinct beats only. A generation seen twice is one beat, read twice.
    seen, distinct = set(), []
    for row in ordered:
        if row["generation"] in seen:
            continue
        seen.add(row["generation"])
        distinct.append(row)

    detail = {
        "beats_observed": len(distinct),
        "minimum": minimum,
        "beats": [
            {
                "generation": r["generation"],
                "generated_at": r["generated_at"],
                "units_this_beat": _units_this_beat(r),
                "units_banked": (r.get("stages") or {}).get("staged:units_banked"),
                "carried": r.get("carried"),
                "terminal": r.get("terminal"),
            }
            for r in distinct
        ],
    }

    if len(distinct) < minimum:
        return {"pass": None, "reason": "insufficient",
                "detail": f"{len(distinct)} distinct beat(s); need {minimum}", **detail}

    window = distinct[-minimum:]

    gaps = []
    for earlier, later in zip(window, window[1:]):
        a, b = _parse_stamp(earlier["generated_at"]), _parse_stamp(later["generated_at"])
        if a is None or b is None:
            gaps.append({"between": [earlier["generation"], later["generation"]],
                         "reason": "unparseable_stamp"})
            continue
        delta = (b - a).total_seconds()
        if abs(delta - BEAT_PERIOD_S) > BEAT_ADJACENCY_SLACK_S:
            gaps.append({"between": [earlier["generation"], later["generation"]],
                         "delta_s": round(delta), "expected_s": BEAT_PERIOD_S})
    if gaps:
        return {"pass": None, "reason": "gap",
                "detail": f"{len(gaps)} non-adjacent pair(s) in the graded window",
                "gaps": gaps, **detail}

    banked = [_units_this_beat(r) for r in window]
    if any(b is None for b in banked):
        return {"pass": None, "reason": "gauge_missing",
                "detail": f"staged:units_this_beat not readable on every beat: {banked}",
                **detail}

    ok = all(b >= 1 for b in banked)
    return {
        "pass": ok,
        "reason": "advancing" if ok else "stalled",
        "detail": f"units_this_beat across {minimum} adjacent beats: {banked}",
        "graded_window": [r["generation"] for r in window],
        "carried_in_window": [r.get("carried") for r in window],
        **detail,
    }


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------

def _db_query(api: str, token: str, sql: str, limit: int = 5) -> dict:
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        api + "/api/admin/db-query", data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    raw = urllib.request.urlopen(req, timeout=90).read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # gotcha #40 — db-query serialises JSONB as a Python repr, so a reader
        # that only knows json.loads silently sees nothing at all.
        return ast.literal_eval(raw)


def _coerce_jsonb(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value


def fetch_ledger(api: str, token: str) -> dict:
    data = _db_query(api, token, LEDGER_SQL)
    rows = data.get("rows", data)
    if not rows:
        raise RuntimeError("phase ledger row absent — the build has never published one")
    first = rows[0]
    record = first if isinstance(first, dict) else dict(zip(data.get("columns") or [], first))
    record["payload"] = _coerce_jsonb(record.get("payload"))
    return record


def fetch_served(api: str) -> dict:
    req = urllib.request.Request(
        api + "/api/calibration", headers={"User-Agent": "bainluck-cal-p082-beat-sampler"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read())
    staged = payload.get("staged") or {}
    return {
        "http_status": resp.status if hasattr(resp, "status") else 200,
        "generated_at": payload.get("generated_at"),
        "availability": payload.get("availability"),
        "bucket_count": len(payload.get("buckets") or []),
        "staged_at": staged.get("staged_at"),
        "rebuild_units_banked": staged.get("rebuild_units_banked"),
        "rebuild_units_this_beat": staged.get("rebuild_units_this_beat"),
        "units_banked": staged.get("units_banked"),
        "units_drifted": staged.get("units_drifted"),
    }


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _seconds_to_next_sample(now: datetime.datetime, minute: int) -> float:
    target = now.replace(minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(hours=1)
    return max(30.0, (target - now).total_seconds())


def sample_once(path: Path, api: str, token: str) -> tuple[dict | None, bool]:
    """Read the ledger; append it iff its generation is new. Returns (row, appended)."""
    record = fetch_ledger(api, token)
    try:
        served = fetch_served(api)
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        served = {"error": f"{type(exc).__name__}: {exc}"}
    row = beat_row(record, served)
    row["captured_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    known = {r.get("generation") for r in read_rows(path)}
    if row["generation"] in known:
        return row, False
    with path.open("a") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return row, True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", help="jsonl to append beats to")
    parser.add_argument("--once", action="store_true", help="one read, then exit")
    parser.add_argument("--grade", action="store_true",
                        help="grade the file and exit; take no new sample")
    parser.add_argument("--minimum", type=int, default=3,
                        help="consecutive beats required to PASS (default 3)")
    parser.add_argument("--sample-minute", type=int, default=40,
                        help="minute past the hour to sample (default 40; the beat "
                             "starts at :15 and finishes ~:33)")
    parser.add_argument("--api", default=os.environ.get("BAINLUCK_API",
                                                        "https://api.bainluck.com"))
    args = parser.parse_args(argv)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)

    if args.grade:
        verdict = grade_consecutive(read_rows(path), minimum=args.minimum)
        print(json.dumps(verdict, indent=2, default=str))
        return {True: 0, False: 1}.get(verdict["pass"], 2)

    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN is not set — cannot read the ledger", file=sys.stderr)
        return 2

    while True:
        try:
            row, appended = sample_once(path, args.api, token)
            stages = row.get("stages") or {}
            print(f"{row['captured_at']} {'BANKED' if appended else 'duplicate'} "
                  f"gen={row['generation']} beat={row['generated_at']} "
                  f"this_beat={stages.get('staged:units_this_beat')} "
                  f"banked={stages.get('staged:units_banked')} "
                  f"btp={stages.get('staged:beats_to_publish')} "
                  f"carried={row.get('carried')} terminal={row.get('terminal')}", flush=True)
        except Exception as exc:  # noqa: BLE001 — a read that failed is loud, never silent
            print(f"{datetime.datetime.now(datetime.timezone.utc).isoformat()} "
                  f"READ FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.once:
            break
        time.sleep(_seconds_to_next_sample(
            datetime.datetime.now(datetime.timezone.utc), args.sample_minute))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
