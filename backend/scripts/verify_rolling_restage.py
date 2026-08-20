#!/usr/bin/env python3
"""CAL-P079 — prove the rolling re-stage is ALIVE, from outside, over real beats.

``program/calibration-75`` replaced a bank that could freeze forever with a
rolling re-stage that retains a serving bank. Its own READY token lists four
post-deploy checks. This is the instrument for them, and it exists because the
alternative — reading the payload once and eyeballing it — cannot distinguish
the two states that matter:

* a bank that ADVANCED, and
* a bank that was republished with a fresh-looking timestamp.

Telling those apart needs **more than one sample**, which is the whole reason
#2007 survived six hours and then twenty-three: every single observation of a
frozen bank looks exactly like an observation of a healthy one.

    python3 scripts/verify_rolling_restage.py --samples 4 --interval-s 900
    python3 scripts/verify_rolling_restage.py --replay a.json b.json c.json

What it checks, in the order the token asks:

1. ``rolling_restage: true`` is present — the new code is actually serving.
2. ``rebuild_units_this_beat > 0`` — the BUILDER is alive.
3. ``staged_at`` MOVES across samples — the SERVED census is advancing. This is
   the one the old gauge could not answer, and the one that matters.
4. ``units_drifted`` falls — the backlog is draining, not just churning.
5. ``/api/calibration`` keeps serving 200 with a coherent curve THROUGHOUT, so a
   partial rebuild is never visible to a reader.

The two readings CAL-P078 caught failing toward comfort are checked explicitly
and NEGATIVELY, because they are the ones a careless verification would use as
evidence of health:

* ``staged_at`` must not merely be RECENT — the durable row's write time now
  advances every beat by construction, so recency proves nothing. It must be
  the SERVED census's completion time, which is why check 3 is about MOVEMENT
  across samples and check 5 is about the drift count falling with it.
* ``bank_advanced_this_beat`` must not be read as "the curve is current". The
  builder always advances now. It is recorded, and deliberately NOT used as a
  pass condition.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.calibration_published_twin import tolerance_pp  # noqa: E402


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--interval-s", type=int, default=900)
    p.add_argument("--api", default=os.environ.get("BAINLUCK_API", "https://api.bainluck.com"))
    p.add_argument("--out", help="write the artifact here")
    p.add_argument("--replay", nargs="*", help="saved payload files, instead of polling")
    return p.parse_args(argv)


def _fetch(api: str) -> dict:
    started = time.monotonic()
    try:
        req = urllib.request.Request(
            f"{api}/api/calibration",
            headers={"User-Agent": "bainluck-cal-p079-restage-verify"},
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read()
            payload = json.loads(body)
            status = resp.status
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        return {"error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": round(time.monotonic() - started, 2)}
    return {
        "http_status": status,
        "elapsed_s": round(time.monotonic() - started, 2),
        "bytes": len(body),
        "payload": payload,
    }


def _observe(sample: dict) -> dict:
    """Reduce one payload to the fields the four checks turn on."""
    if "error" in sample:
        return {"error": sample["error"]}
    p = sample["payload"]
    staged = p.get("staged") or {}
    buckets = p.get("buckets") or []
    return {
        "http_status": sample["http_status"],
        "elapsed_s": sample["elapsed_s"],
        "generated_at": p.get("generated_at"),
        "availability": p.get("availability"),
        "bucket_count": len(buckets),
        "total_outcomes": p.get("total_outcomes"),
        # -- the served bank --------------------------------------------------
        "staged_at": staged.get("staged_at"),
        "staged_age_s": staged.get("staged_age_s"),
        "units_banked": staged.get("units_banked"),
        "units_drifted": staged.get("units_drifted"),
        "units_drift_unknown": staged.get("units_drift_unknown"),
        "frozen_over_drift": staged.get("frozen_over_drift"),
        # -- the builder, published under its own name (CAL-P078) -------------
        "rolling_restage": staged.get("rolling_restage"),
        "rebuild_units_this_beat": staged.get("rebuild_units_this_beat"),
        "rebuild_units_banked": staged.get("rebuild_units_banked"),
        # -- recorded, never used as a pass condition -------------------------
        "bank_advanced_this_beat": staged.get("bank_advanced_this_beat"),
        "units_this_beat": staged.get("units_this_beat"),
        "tolerance_pp": tolerance_pp(staged),
    }


def evaluate(obs: list[dict]) -> dict:
    """Pure. Turn a list of observations into the token's four verdicts."""
    good = [o for o in obs if "error" not in o]
    checks: dict[str, dict] = {}

    def verdict(name, ok, detail):
        checks[name] = {"pass": ok, "detail": detail}

    if len(good) < 2:
        verdict("samples", False,
                f"only {len(good)} readable sample(s); movement needs at least 2")
        return {"checks": checks, "verdict": "unmeasurable"}
    verdict("samples", True, f"{len(good)} readable samples")

    # 1 — the new code is serving
    flags = [o.get("rolling_restage") for o in good]
    verdict("rolling_restage_present", all(f is True for f in flags),
            f"rolling_restage across samples: {flags}")

    # 2 — the builder is alive
    beats = [o.get("rebuild_units_this_beat") for o in good]
    alive = [b for b in beats if isinstance(b, int) and b > 0]
    verdict("builder_alive", bool(alive),
            f"rebuild_units_this_beat: {beats}")

    # 3 — THE ONE THAT MATTERS: the SERVED census moved
    stamps = [o.get("staged_at") for o in good]
    distinct = [s for s in dict.fromkeys(stamps) if s]
    verdict("served_census_advanced", len(distinct) > 1,
            f"{len(distinct)} distinct staged_at value(s): {distinct}")

    # 4a — the REBUILD is advancing. CAL-P081 adds this because check 4 below
    # cannot answer per beat and this one can: ``rebuild_units_banked`` is the
    # count of units the successor bank holds, and it is the only number that
    # moves every beat the loop runs. Measured 2026-08-20: it sat at 13/128
    # across 18:22Z -> 20:25Z while every other field looked healthy.
    banked = [
        o.get("rebuild_units_banked") for o in good
        if isinstance(o.get("rebuild_units_banked"), int)
    ]
    if len(banked) < 2:
        verdict("rebuild_advancing", False,
                f"rebuild_units_banked not readable across samples: {banked}")
    else:
        # CHANGED, not merely increased. The count resets toward zero when a
        # complete bank is promoted, so a window that spans a promotion reads
        # 120 -> 0 -> 8 and a strict `last > first` would grade the single best
        # outcome in the system as a failure. Any change is a unit banked or a
        # promotion; no change across samples is the frozen state.
        verdict("rebuild_advancing", len(set(banked)) > 1,
                f"rebuild_units_banked across samples: {banked}")

    # 4 — the backlog is draining.
    #
    # CAL-P081 makes this THREE-VALUED, and the reason is a measurement rather
    # than a preference. ``units_drifted`` is ``served_drift``: the count of
    # SERVING-bank units whose membership digest no longer matches the plan. The
    # served digests are frozen when a bank is promoted, and the population only
    # grows, so the count is MONOTONE UP until ``promote_if_complete`` swaps in a
    # successor. It cannot fall on an ordinary beat, and once it reaches the
    # bank size it cannot move at all.
    #
    # So on 2026-08-20 this check reported ``fail`` for 128/128 — a state that is
    # expected, correct, and fully disclosed. That is the false RED this whole
    # queue has been removing, inside the instrument built to detect the false
    # GREEN. The check is not weakened: a drift that CAN move and does not still
    # fails. It is marked unanswerable only when it is saturated, which is a fact
    # about the measurement and not about the build.
    drift = [o.get("units_drifted") for o in good if isinstance(o.get("units_drifted"), int)]
    checkable = [
        o.get("units_banked") for o in good if isinstance(o.get("units_banked"), int)
    ]
    saturated = bool(drift) and bool(checkable) and all(
        d >= c > 0 for d, c in zip(drift, checkable)
    )
    if saturated:
        checks["drift_falling"] = {
            "pass": None,
            "detail": (
                f"units_drifted is SATURATED at {drift[0]}/{checkable[0]} across every "
                "sample. The served bank's drift resets only when a complete "
                "successor is promoted, so this cannot fall on an ordinary beat and "
                "its not-falling is NOT evidence of a stall — read `rebuild_advancing` "
                "for the per-beat answer."
            ),
        }
    else:
        verdict("drift_falling", bool(drift) and drift[-1] < drift[0],
                f"units_drifted first={drift[0] if drift else None} "
                f"last={drift[-1] if drift else None}")

    # 5 — the reader never sees a partial rebuild
    statuses = [o.get("http_status") for o in good]
    counts = [o.get("bucket_count") for o in good]
    served_ok = all(s == 200 for s in statuses) and all(
        isinstance(c, int) and c > 0 for c in counts
    )
    verdict("served_200_and_coherent_throughout", served_ok,
            f"statuses={statuses} bucket_counts={counts}")

    # The bound, which is the CAL-P079 headline number.
    bounds = [o.get("tolerance_pp") for o in good]
    checks["bound"] = {
        "pass": None,
        "detail": f"tolerance_pp across samples: {bounds}",
        "first": bounds[0] if bounds else None,
        "last": bounds[-1] if bounds else None,
    }

    graded = [c["pass"] for c in checks.values() if c["pass"] is not None]
    return {
        "checks": checks,
        "verdict": "pass" if all(graded) else "fail",
    }


def main(argv=None) -> int:
    args = _parse_args(argv)

    samples = []
    if args.replay:
        for path in args.replay:
            samples.append({"http_status": 200, "elapsed_s": 0.0,
                            "bytes": 0, "payload": json.loads(Path(path).read_text())})
    else:
        for i in range(args.samples):
            if i:
                time.sleep(args.interval_s)
            samples.append(_fetch(args.api))
            print(f"sample {i + 1}/{args.samples} taken", file=sys.stderr)

    obs = [_observe(s) for s in samples]
    result = evaluate(obs)
    artifact = {
        "queue": "CAL-P079",
        "issue": 2007,
        "gate": "the rolling re-stage is alive (program/calibration-75 post-deploy)",
        "api": args.api,
        "interval_s": args.interval_s,
        "observations": obs,
        **result,
    }

    text_out = json.dumps(artifact, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text_out)
    print(text_out)
    # 0 pass, 1 a real failure, 2 could not measure — gotcha #54's amendment.
    return {"pass": 0, "fail": 1}.get(artifact["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
