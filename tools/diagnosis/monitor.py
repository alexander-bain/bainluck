"""Read-only Terminal view of the supervised diagnosis worker."""
import argparse
import json
from pathlib import Path
import time

ROOT = Path.home() / "bainluck-diagnosis"


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def safe_text(value):
    return "".join(c for c in str(value) if c in "\n\t" or ord(c) >= 32 and ord(c) != 127)


def event_text(record):
    payload = record.get("payload") or {}
    kind = record.get("payload_type", "")
    if kind.startswith("run.terminal."):
        return "RESULT: " + str(payload.get("text") or payload.get("terminal") or kind)
    if kind == "tool.result":
        # Keep progress readable; complete tool output remains in worker.jsonl.
        return "TOOL: " + str(payload.get("text") or "completed")[:600]
    return ""


class Tail:
    def __init__(self):
        self.path = None
        self.offset = 0
        self.pending = b""

    def poll(self, path):
        if path != self.path:
            self.path, self.offset, self.pending = path, 0, b""
            if path and path.exists():
                # Opening the window should show current work, not replay hours.
                size = path.stat().st_size
                self.offset = max(0, size - 16000)
                if self.offset:
                    with path.open("rb") as stream:
                        stream.seek(self.offset)
                        stream.readline()
                        self.offset = stream.tell()
        if not path:
            return []
        try:
            with path.open("rb") as stream:
                if path.stat().st_size < self.offset:
                    self.offset, self.pending = 0, b""
                stream.seek(self.offset)
                data = stream.read(1024 * 1024)
                self.offset = stream.tell()
        except OSError:
            return []
        lines = (self.pending + data).split(b"\n")
        self.pending = lines.pop()
        output = []
        for line in lines:
            try:
                value = event_text(json.loads(line))
            except (ValueError, TypeError, AttributeError):
                continue
            if value:
                output.append(safe_text(value))
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    launcher = Path(__file__).resolve().parents[2] / "diagnosis-lane.sh"
    print("TBH DIAGNOSIS — live status and output", flush=True)
    print("Closing this window / Ctrl-C closes the view; the worker keeps running.", flush=True)
    print(f"Stop the worker: {launcher} stop", flush=True)
    print(f"Artifacts: {ROOT}\n", flush=True)
    tail, previous, last_notice = Tail(), None, 0
    recent = sorted((ROOT / "runs").glob("*/RESULT.json"))[-5:]
    for path in recent:
        r = read_json(path)
        print(f"Recent #{r.get('issue')}: {r.get('status')} — {safe_text(r.get('summary', ''))[:240]}", flush=True)
    while True:
        state = read_json(ROOT / "STATUS.json")
        now = time.monotonic()
        if state != previous or now - last_notice >= 60:
            print(f"\n[{time.strftime('%H:%M:%S')}] {state.get('state', 'not started')}"
                  f"  issue={state.get('issue', '—')}  {state.get('reason', '')}", flush=True)
            if state.get("run"):
                print(state["run"], flush=True)
            previous, last_notice = state, now
        run = state.get("run")
        path = Path(run) / "worker.jsonl" if run else tail.path
        for value in tail.poll(path):
            print(value, flush=True)
        if args.snapshot:
            break
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nView closed. Diagnosis worker continues in the background.")
