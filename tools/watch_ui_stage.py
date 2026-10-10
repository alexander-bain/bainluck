"""One 3000s deadline across preparation, evidence upload and UI execution."""

import argparse
import json
import signal
from pathlib import Path
import time

try:
    from .watch_ui_deadline import Interrupted, MAX_SECONDS, _write, run_gate
except ImportError:
    from watch_ui_deadline import Interrupted, MAX_SECONDS, _write, run_gate

# Retained e356 setup consumed 2213.570s including successful compilation.
# With compilation removed, allow at most20m for infrastructure preparation,
# leaving at least30m for unchanged cases; upload time also consumes that50m.
PREPARATION_SECONDS = 20 * 60
MIN_EXECUTION_SECONDS = 30 * 60


def admission(output, stage, now):
    path = output / "global-deadline.json"
    if stage in {"prepare", "products"}:
        if path.exists():
            raise ValueError("A stage cannot reset an existing gate deadline")
        state = {
            "started_monotonic": now,
            "budget_seconds": MAX_SECONDS,
            "stages": {},
            "started_utc": time.time(),
        }
        _write(path, state)
    else:
        state = json.loads(path.read_text())
        if state.get("stages", {}).get("prepare") != 0:
            raise ValueError("Execution requires successful preparation")
        if "execute" in state["stages"]:
            raise ValueError("An execution stage cannot be repeated")
    if state.get("budget_seconds") != MAX_SECONDS:
        raise ValueError("Unexpected global deadline budget")
    remaining = MAX_SECONDS - (now - state["started_monotonic"])
    if remaining <= 0 or remaining > MAX_SECONDS:
        raise ValueError("Global gate deadline exhausted or invalid")
    if stage == "execute" and remaining < MIN_EXECUTION_SECONDS:
        raise ValueError(
            "Preparation/upload exceeded20m admission; insufficient full-shard reserve"
        )
    return min(remaining, PREPARATION_SECONDS) if stage == "prepare" else remaining


def run(output, stage, command):
    output.mkdir(parents=True, exist_ok=True)
    try:
        seconds = admission(output, stage, time.monotonic())
        stage_dir = output / ("stage-" + stage)
        code = run_gate(command, stage_dir, seconds=seconds)
        state = json.loads((output / "global-deadline.json").read_text())
        state["stages"][stage] = code
        state["elapsed_seconds"] = time.monotonic() - state["started_monotonic"]
        _write(output / "global-deadline.json", state)
        if code:
            _write(
                output / "receipt.json",
                {
                    "verdict": "UNPAID",
                    "reason": "Stage failed: " + stage,
                    "exit_code": code,
                },
            )
        return code
    except (OSError, ValueError, KeyError) as error:
        _write(
            output / "receipt.json",
            {"verdict": "UNPAID", "reason": str(error), "stage": stage},
        )
        return 1


def install_signal_handlers():
    def interrupted(signum, _frame):
        signal.signal(signum, signal.SIG_IGN)
        raise Interrupted(signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "execute", "products", "phase"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--phase")
    args, command = parser.parse_known_args()
    if command and command[0] == "--":
        command = command[1:]
    if args.stage == "phase":
        args.output_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "phase": args.phase,
            "monotonic": time.monotonic(),
            "utc": time.time(),
        }
        _write(args.output_dir / "phase.json", record)
        with (args.output_dir / "phases.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        return
    install_signal_handlers()
    raise SystemExit(run(args.output_dir, args.stage, command))


if __name__ == "__main__":
    main()
