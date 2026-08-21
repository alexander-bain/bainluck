#!/usr/bin/env python3
"""CAL-P083 — did the futures carry-withhold FIRE, and did it do its job?

CAL-P081 shipped a guard (`MainBuildRunner.build_checkpoint`, commit
``4dc4fa21``) that refuses to bank the futures phase while a rolling re-stage is
part-way through its 128 units. CAL-P082 then had to report the guard **had
never fired once** across four observed beats, and — the part worth keeping —
that it could not have: ``build_checkpoint`` is called only when the terminal is
NOT ``complete``, so a run of healthy beats proves the rebuild advances and
proves nothing whatever about the guard.

Fable's item 2 is therefore a request for a SPECIMEN, and this grades one. The
distinction it exists to hold is the one CAL-P082 nearly lost:

    "the guard fired" != "the beat was unhappy"

A beat can fail to bank futures for two completely different reasons, and only
one of them is the insurance working:

* **withheld** — the futures phase COMPLETED, the rebuild was in flight, and the
  guard chose not to bank it. ``banked["futures"] == "rebuild_in_flight"``.
* **nothing to bank** — the futures phase never completed, so there was no carry
  to withhold. ``banked`` is empty or absent. Reporting this as a firing would
  be the CAL-P082 error in the opposite direction: crediting the guard for a
  beat it never ran on.

The second is the NEGATIVE CONTROL, and it is why a firing means anything. A
token that showed up on every unhappy beat would be indistinguishable from a
label, so the grade counts both classes and refuses a PASS unless it saw the
guard stay silent where it should.

And a firing is only half the claim. The guard exists so the NEXT beat runs its
unit loop instead of spending itself on a carry, so where the following beat was
captured this grades the effect too: futures absent from ``carried`` and
``units_this_beat > 0``. The defect shape it is measured against is the 2026-08-20
20:15Z beat, ``carried: ['futures','sports']`` with ``units_this_beat: 0``.

    python3 scripts/grade_carry_withhold.py beats.jsonl
    python3 scripts/grade_carry_withhold.py beats.jsonl --json out.json

Exit codes follow gotcha #54's amendment: ``0`` a firing was observed and
attributed, ``1`` no firing in this window (a real, reportable answer — the
CAL-P082 state), ``2`` could not measure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: The guard's own outcome token. Owned by
#: ``app.tasks.calibration_main_build.build_checkpoint`` and restated here
#: because this reads a captured jsonl rather than importing the runner. A
#: rename that misses this site shows up as ``no_firing``, which is the safe
#: direction: it under-claims.
WITHHELD = "rebuild_in_flight"

PHASE_FUTURES = "futures"

#: Terminals on which ``build_checkpoint`` is reachable at all. A ``complete``
#: beat CLEARS the checkpoint instead, so the guard is structurally unreachable
#: there and such beats are neither evidence for nor against it.
GUARD_REACHABLE = ("failed", "cancelled", "partial", "interrupted")


def classify(row: dict) -> dict:
    """One beat's relationship to the guard. Pure.

    Five states, and the two that carry the finding are ``withheld`` and
    ``nothing_to_bank``. The others exist so a reader is never left inferring
    why a beat is absent from the count.
    """
    terminal = row.get("terminal")
    banked = row.get("banked")
    stages = row.get("stages") or {}
    completed = row.get("completed_required") or []

    planned = stages.get("staged:units_planned")
    done = stages.get("staged:units_done")
    if done is None:
        # Pre-CAL-P083 captures did not carry the gauge; the unit-cost block
        # carries the same number and is the honest fallback. Named, so a reader
        # can tell a derived operand from a recorded one.
        done = ((row.get("unit_costs") or {}).get(PHASE_FUTURES) or {}).get("units_done")
        done_source = "unit_costs" if done is not None else None
    else:
        done_source = "gauge"

    in_flight = None
    if isinstance(planned, int) and planned > 0 and isinstance(done, int):
        in_flight = done < planned

    out = {
        "generation": row.get("generation"),
        "generated_at": row.get("generated_at"),
        "terminal": terminal,
        "carried": row.get("carried"),
        "banked": banked,
        "completed_required": completed,
        "units_planned": planned,
        "units_done": done,
        "units_done_source": done_source,
        "rebuild_in_flight": in_flight,
        "futures_completed": PHASE_FUTURES in completed,
        "units_this_beat": stages.get("staged:units_this_beat"),
        "units_banked": stages.get("staged:units_banked"),
    }

    if isinstance(banked, dict) and banked.get(PHASE_FUTURES) == WITHHELD:
        out["state"] = "withheld"
        return out
    if terminal == "complete":
        out["state"] = "guard_unreachable_complete"
        return out
    if terminal not in GUARD_REACHABLE:
        out["state"] = "guard_unreachable_other_terminal"
        return out
    if not out["futures_completed"]:
        # The negative control. `build_checkpoint` ran; there was simply no
        # completed futures phase to withhold.
        out["state"] = "nothing_to_bank"
        return out
    # Reachable, futures completed, and yet not withheld. Either the rebuild was
    # NOT in flight (legitimate — the guard is scoped to the in-flight case) or
    # the guard failed to fire when it should have. Distinguished, never merged.
    out["state"] = (
        "banked_rebuild_not_in_flight" if in_flight is False else "expected_firing_absent"
    )
    return out


def grade(rows: list[dict]) -> dict:
    beats = [classify(r) for r in rows]
    beats.sort(key=lambda b: (b["generation"] or 0))

    by_state: dict[str, list[dict]] = {}
    for b in beats:
        by_state.setdefault(b["state"], []).append(b)

    firings = by_state.get("withheld", [])
    controls = by_state.get("nothing_to_bank", [])
    missed = by_state.get("expected_firing_absent", [])

    result = {
        "beats": beats,
        "counts": {k: len(v) for k, v in sorted(by_state.items())},
        "firings": firings,
        "negative_controls": controls,
        "expected_firing_absent": missed,
    }

    if missed:
        # The guard was reachable, futures had completed, the rebuild was in
        # flight, and it did NOT withhold. That is the guard being broken, and it
        # outranks any firing elsewhere in the window.
        result["verdict"] = "guard_defect"
        result["reason"] = (
            f"{len(missed)} beat(s) met every firing condition and did not "
            f"withhold"
        )
        return result

    if not firings:
        result["verdict"] = "no_firing"
        result["reason"] = (
            "no beat in this window reached build_checkpoint with a completed "
            "futures phase while a re-stage was in flight — the CAL-P082 state"
        )
        return result

    # The effect: the beat AFTER a firing should run its unit loop rather than
    # spend itself carrying futures.
    index = {b["generation"]: i for i, b in enumerate(beats)}
    for f in firings:
        nxt = beats[index[f["generation"]] + 1:index[f["generation"]] + 2]
        if not nxt:
            f["effect"] = {"observed": False, "reason": "no following beat captured"}
            continue
        n = nxt[0]
        carried = n.get("carried") or []
        units = n.get("units_this_beat")
        f["effect"] = {
            "observed": True,
            "next_generation": n["generation"],
            "next_generated_at": n["generated_at"],
            "next_carried": carried,
            "next_units_this_beat": units,
            "futures_not_carried": PHASE_FUTURES not in carried,
            "unit_loop_ran": isinstance(units, int) and units > 0,
            "bank_before": f.get("units_banked"),
            "bank_after": n.get("units_banked"),
        }

    result["verdict"] = "fired"
    result["negative_control_present"] = bool(controls)
    return result


def render(result: dict) -> str:
    lines = []
    for b in result["beats"]:
        lines.append(
            f"gen={b['generation']} {str(b['generated_at'])[:19]} "
            f"term={b['terminal']:<9} state={b['state']:<28} "
            f"done={b['units_done']}/{b['units_planned']} "
            f"in_flight={b['rebuild_in_flight']} "
            f"futures_done={b['futures_completed']}"
        )
    lines.append("")
    lines.append(f"counts: {json.dumps(result['counts'])}")
    lines.append("")
    v = result["verdict"]
    if v == "fired":
        for f in result["firings"]:
            lines.append(
                f"FIRED   gen={f['generation']} ({str(f['generated_at'])[:19]}Z) "
                f"terminal={f['terminal']}"
            )
            lines.append(
                f"  predicate: units_done {f['units_done']} < planned "
                f"{f['units_planned']} -> rebuild_in_flight={f['rebuild_in_flight']} "
                f"(operand from {f['units_done_source']})"
            )
            lines.append(f"  futures phase completed: {f['futures_completed']}")
            lines.append(f"  guard verdict: banked = {json.dumps(f['banked'])}")
            e = f.get("effect") or {}
            if e.get("observed"):
                lines.append(
                    f"  EFFECT on gen={e['next_generation']} "
                    f"({str(e['next_generated_at'])[:19]}Z): "
                    f"carried={e['next_carried']} "
                    f"units_this_beat={e['next_units_this_beat']} "
                    f"bank {e['bank_before']} -> {e['bank_after']}"
                )
                lines.append(
                    f"    futures_not_carried={e['futures_not_carried']} "
                    f"unit_loop_ran={e['unit_loop_ran']}"
                )
            else:
                lines.append(f"  EFFECT: unobserved ({e.get('reason')})")
        lines.append("")
        lines.append(
            f"negative control present: {result.get('negative_control_present')} "
            f"({len(result['negative_controls'])} beat(s) reached the checkpoint "
            f"with nothing to bank and correctly did not fire)"
        )
    else:
        lines.append(f"{v.upper()}: {result.get('reason')}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="beats jsonl from sample_calibration_beats.py")
    ap.add_argument("--json", dest="json_out")
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
            continue
    if not rows:
        print(f"UNMEASURABLE: no beat rows in {src}", file=sys.stderr)
        return 2

    result = grade(rows)
    print(render(result))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1, default=str))

    if result["verdict"] == "fired":
        return 0
    if result["verdict"] in ("no_firing", "guard_defect"):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
