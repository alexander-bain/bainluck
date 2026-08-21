#!/usr/bin/env python3
"""CAL-P083 — grade the AGREEMENT BOUND per beat, and find its first descent.

``sample_calibration_beats.py`` (CAL-P082) answers "is the rebuild advancing"
from the phase ledger, one row per beat, keyed on ``generation``. This answers
the other half of #2007: **what bound did that beat's disclosure earn**, and
**when did it first come down**.

The bound is not a number this file invents. It is
:func:`app.utils.calibration_published_twin.tolerance_pp` over
:func:`app.utils.calibration_staged_disclosure.build_disclosure`, which is the
exact pair the served payload and the Gate 0 twin worker both go through. A
grader that re-implemented ``max(0.5, 100 * moved / banked)`` would agree with
production right up until the moment production changed, and would then report
its own arithmetic with production's authority. So it imports them.

WHY A DEDICATED GRADER, when the payload publishes ``staged`` and a reader can
divide two numbers:

1. **The bound is a SAWTOOTH, and one sample cannot see a sawtooth.** It falls
   to the tight floor on the beat that promotes a freshly-built bank, then
   climbs again as the roster moves under that bank. Whether the descent
   happened is a question about a SEQUENCE. CAL-P081's ``[13, 13]`` was the same
   class of mistake in the adjacent instrument.
2. **A descent must be attributed.** The bound can fall for two very different
   reasons: a PROMOTION (``served_at`` moves — a new census is being served) or
   a drift re-measurement against the same bank. Only the first is the thing
   #2007 has been waiting for. The grader refuses to call an unattributed dip a
   promotion, and says which it saw.
3. **A descent that does not HOLD is a different finding from one that does**,
   and it is the finding that governs when the Gate 0 twin can be run at all.
   So the grade reports the post-descent trajectory rather than stopping at the
   minimum, which would quote the program's best number and hide its shape.

    python3 scripts/grade_bound_descent.py beats.jsonl
    python3 scripts/grade_bound_descent.py beats.jsonl --json out.json

Exit codes follow gotcha #54's amendment: ``0`` a descent was found and
attributed, ``1`` no descent in this window (a real, reportable answer), ``2``
could not measure. ``1`` is a result; anything else is a story about the harness.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.calibration_published_twin import (  # noqa: E402
    DRIFT_TOLERANCE_SCALE_PP,
    TIGHT_TOLERANCE_PP,
    tolerance_pp,
)
from app.utils.calibration_staged_disclosure import build_disclosure  # noqa: E402

#: A bound is "at the floor" when it is the tight constant itself. Compared with
#: a tolerance rather than ``==`` only because the value crosses JSON; the
#: constant is exact on both sides today and this guards a future in which it
#: is not.
FLOOR_EPSILON_PP = 1e-9


def _parse_stamp(value):
    """A UTC ``datetime`` from whatever the row carried, or ``None``.

    Mirrors ``sample_calibration_beats._parse_stamp`` deliberately rather than
    importing it: this script must run against a jsonl produced by any version
    of the sampler, including one written before that helper existed.
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


def grade_beat(row: dict) -> dict:
    """One beat's bound, through the production pair. Pure.

    ``now`` is pinned to the beat's OWN ``generated_at``, never the wall clock.
    ``staged_age_s`` is the only field that reads it and ``tolerance_pp`` does
    not consume that field — but a grader whose output moves when you re-run it
    tomorrow cannot be quoted in a report, and gotcha #44 is this program's
    most-repeated self-inflicted wound.
    """
    stamp = _parse_stamp(row.get("generated_at"))
    stages = row.get("stages") or {}

    disclosure = build_disclosure(
        ledger_stages=stages,
        staged_generated_at=stamp,
        now=stamp,
    )
    bound = tolerance_pp(disclosure)

    return {
        "generation": row.get("generation"),
        "generated_at": row.get("generated_at"),
        "terminal": row.get("terminal"),
        "carried": row.get("carried"),
        # The bound, and the three gauges it is a function of, side by side.
        # A bound quoted without them is a number nobody can re-derive.
        "tolerance_pp": bound,
        "measured": disclosure.get("measured"),
        "unmeasured_reason": disclosure.get("reason"),
        "served_at": stages.get("staged:served_at"),
        "served_units": stages.get("staged:served_units"),
        "served_drifted": stages.get("staged:served_drifted"),
        "units_banked": disclosure.get("units_banked"),
        "units_drifted": disclosure.get("units_drifted"),
        "units_drift_unknown": disclosure.get("units_drift_unknown"),
        "frozen_over_drift": disclosure.get("frozen_over_drift"),
        "rebuild_units_banked": disclosure.get("rebuild_units_banked"),
        "rebuild_units_this_beat": disclosure.get("rebuild_units_this_beat"),
    }


def grade(rows: list[dict]) -> dict:
    """Find and attribute the first descent across a beat sequence. Pure."""
    graded = [grade_beat(r) for r in rows]
    graded.sort(key=lambda g: (g["generation"] or 0))

    measurable = [g for g in graded if g["tolerance_pp"] is not None]
    if len(measurable) < 2:
        return {
            "verdict": "unmeasurable",
            "reason": (
                "fewer_than_two_measurable_beats: a descent is a relation "
                "between two bounds, and there is only one"
            ),
            "beats": graded,
            "measurable_beats": len(measurable),
        }

    descent = None
    for prev, cur in zip(measurable, measurable[1:]):
        if cur["tolerance_pp"] < prev["tolerance_pp"]:
            # Attribution. A promotion moves ``served_at`` — a different census
            # is now being served. Anything else is the same bank re-measured,
            # which is a real observation but NOT the event #2007 is waiting on.
            promoted = (
                cur.get("served_at") is not None
                and prev.get("served_at") is not None
                and cur["served_at"] != prev["served_at"]
            )
            descent = {
                "from_generation": prev["generation"],
                "from_generated_at": prev["generated_at"],
                "from_tolerance_pp": prev["tolerance_pp"],
                "to_generation": cur["generation"],
                "to_generated_at": cur["generated_at"],
                "to_tolerance_pp": cur["tolerance_pp"],
                "delta_pp": cur["tolerance_pp"] - prev["tolerance_pp"],
                "attribution": "promotion" if promoted else "drift_remeasurement",
                "served_at_before": prev.get("served_at"),
                "served_at_after": cur.get("served_at"),
                "at_tight_floor": (
                    cur["tolerance_pp"] <= TIGHT_TOLERANCE_PP + FLOOR_EPSILON_PP
                ),
            }
            break

    if descent is None:
        return {
            "verdict": "no_descent",
            "reason": (
                "the bound did not fall between any two adjacent measurable "
                "beats in this window"
            ),
            "beats": graded,
            "measurable_beats": len(measurable),
            "bound_series_pp": [g["tolerance_pp"] for g in measurable],
        }

    # What the bound did AFTER. A descent that immediately re-climbs bounds the
    # window in which anything can be certified against it, and that window is
    # the operational fact — not the minimum.
    idx = next(
        i for i, g in enumerate(measurable)
        if g["generation"] == descent["to_generation"]
    )
    after = measurable[idx + 1:]
    descent["held"] = bool(after) and all(
        g["tolerance_pp"] <= descent["to_tolerance_pp"] + FLOOR_EPSILON_PP
        for g in after
    )
    descent["beats_observed_after"] = len(after)
    descent["tolerance_pp_after"] = [
        {"generation": g["generation"], "generated_at": g["generated_at"],
         "tolerance_pp": g["tolerance_pp"]}
        for g in after
    ]

    return {
        "verdict": "descent",
        "descent": descent,
        "beats": graded,
        "measurable_beats": len(measurable),
        "bound_series_pp": [g["tolerance_pp"] for g in measurable],
        "constants": {
            "TIGHT_TOLERANCE_PP": TIGHT_TOLERANCE_PP,
            "DRIFT_TOLERANCE_SCALE_PP": DRIFT_TOLERANCE_SCALE_PP,
        },
    }


def render(result: dict) -> str:
    lines: list[str] = []
    for g in result.get("beats", []):
        bound = g["tolerance_pp"]
        shown = "UNMEASURABLE" if bound is None else f"{bound:.4f}pp"
        lines.append(
            f"gen={g['generation']} {str(g['generated_at'])[:19]} "
            f"bound={shown} served_at={g.get('served_at')} "
            f"drift={g.get('served_drifted')}/{g.get('served_units')} "
            f"term={g.get('terminal')}"
        )
    verdict = result.get("verdict")
    lines.append("")
    if verdict == "descent":
        d = result["descent"]
        lines.append(
            f"DESCENT  {d['from_tolerance_pp']:.4f}pp -> {d['to_tolerance_pp']:.4f}pp "
            f"({d['delta_pp']:+.4f}pp) at generation {d['to_generation']} "
            f"({str(d['to_generated_at'])[:19]}Z)"
        )
        lines.append(f"  attribution: {d['attribution']}")
        lines.append(f"  at tight floor: {d['at_tight_floor']}")
        lines.append(
            f"  held: {d['held']} over {d['beats_observed_after']} later beat(s)"
        )
        for a in d["tolerance_pp_after"]:
            lines.append(
                f"    then gen={a['generation']} {str(a['generated_at'])[:19]} "
                f"-> {a['tolerance_pp']:.4f}pp"
            )
    else:
        lines.append(f"{verdict.upper()}: {result.get('reason')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="beats jsonl from sample_calibration_beats.py")
    ap.add_argument("--json", dest="json_out", help="write the full result here")
    args = ap.parse_args()

    src = Path(args.path)
    if not src.exists():
        print(f"UNMEASURABLE: no such file: {src}", file=sys.stderr)
        return 2

    rows = []
    for line in src.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # A truncated last line is normal while a follower is writing.
            continue

    if not rows:
        print(f"UNMEASURABLE: no beat rows in {src}", file=sys.stderr)
        return 2

    result = grade(rows)
    print(render(result))

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1, default=str))

    if result["verdict"] == "descent":
        return 0
    if result["verdict"] == "no_descent":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
