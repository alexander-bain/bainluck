#!/usr/bin/env python3
"""Local fleet controls. No network or model is needed for pause/status/admission."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(
    os.environ.get(
        "LANE_CONTROL_ROOT", str(Path.home() / "bainluck/.claude/handoff/fleet-control")
    )
)
NAMES = {
    "lane1": "Matching",
    "lane1b": "Matching support",
    "ux": "Design & interactions",
    "latency": "Speed & responsiveness",
    "authority": "Data truth",
    "native": "Apple platforms",
    "live": "Live prices",
    "discover": "Discover",
    "calibration": "Accuracy",
    "integrator": "Release coordinator",
    "shopper": "User journey testing",
    "review": "Independent review",
    "measurement": "Live monitoring",
    "diagnosis": "Bug diagnosis",
    "supervisor": "Fleet supervisor",
}


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value) + "\n")
    os.replace(temp, path)


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def state(lane, message):
    atomic(
        ROOT / "status" / (lane + ".json"),
        {"pid": os.getpid(), "state": message, "at": time.time()},
    )
    if sys.stdout.isatty():
        print(f"\033]0;{NAMES.get(lane, lane)} — {message}\007", end="", flush=True)


def paused(lane):
    if lane.startswith("review-"):
        lane = "review"
    return (ROOT / "paused" / "all").exists() or (ROOT / "paused" / lane).exists()


@contextlib.contextmanager
def lock(name):
    path = ROOT / "locks" / (name + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield None
            return
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def processes():
    rows = []
    for line in subprocess.check_output(
        ["ps", "-axww", "-o", "pid=,ppid=,command="], text=True
    ).splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) == 3:
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


def running(command):
    return [
        p
        for p, _, c in processes()
        if c in (command, "/bin/bash " + command, "bash " + command)
    ]


@contextlib.contextmanager
def reservation(lane, lease=False):
    with contextlib.ExitStack() as stack:
        # Inherited locks survive a controller crash while its command lives.
        held = stack.enter_context(lock(("worker-" if lease else "session-") + lane))
        if held is None:
            yield None
            return
        handles = [held]
        if not lease:
            if paused(lane):
                state(lane, "Paused — active work finishes first")
                yield None
                return
            limit = read(ROOT / "limits.json", {"sessions": 3})["sessions"]
            with lock("admission") as admission:
                if admission is None:
                    yield None
                    return
                free = []
                active = 0
                for n in range(6):
                    path = ROOT / "locks" / f"slot-{n}.lock"
                    handle = path.open("a")
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        free.append(handle)
                    except BlockingIOError:
                        active += 1
                        handle.close()
                if active >= limit or not free:
                    for handle in free:
                        handle.close()
                    state(lane, "Waiting for laptop capacity")
                    yield None
                    return
                slot = free.pop(0)
                for handle in free:
                    handle.close()
                stack.callback(slot.close)
                handles.append(slot)
            state(lane, "Working")
        try:
            yield handles
        finally:
            if not lease:
                state(lane, "Paused" if paused(lane) else "Waiting for assignment")


def execute(lane, argv, lease=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", lane):
        raise ValueError("Invalid lane/subject identifier")
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        raise ValueError("Missing command")
    with reservation(lane, lease) as handles:
        if handles is None:
            return 75
        env = dict(os.environ)
        for key in (
            "CMAKE_BUILD_PARALLEL_LEVEL",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "CIRCLE_NODE_TOTAL",
        ):
            env.setdefault(key, "2")
        if lease:
            env["LANE_LEASE_HELD"] = lane
            for handle in handles:
                os.set_inheritable(handle.fileno(), True)
            os.nice(10)
            os.execvpe(argv[0], argv, env)

        def priority():
            os.nice(10)

        child = subprocess.Popen(
            argv,
            env=env,
            pass_fds=tuple(h.fileno() for h in handles),
            preexec_fn=priority,
        )
        old = {}

        def forward(sig, frame):
            child.send_signal(sig)

        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            old[sig] = signal.signal(sig, forward)
        try:
            rc = child.wait()
        finally:
            for sig, handler in old.items():
                signal.signal(sig, handler)
        if not lease:
            state(lane, "Paused" if paused(lane) else f"Waiting — last exit {rc}")
        return rc if rc >= 0 else 128 - rc


def launch(lane, command):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}", lane):
        raise ValueError("Invalid lane")
    if paused(lane):
        print(f"{NAMES.get(lane, lane)}: paused")
        return 0
    with lock("launch-" + lane) as held:
        if held is None or running(command):
            print(f"{NAMES.get(lane, lane)}: already running or starting")
            return 0
        marker = ROOT / "launches" / (lane + ".json")
        pending = read(marker, {})
        if time.time() - pending.get("at", 0) < 60:
            print(f"{NAMES.get(lane, lane)}: start already requested")
            return 0
        script = """on run argv
 tell application "Terminal"
 set t to do script (item 1 of argv)
 set custom title of t to item 2 of argv
 end tell
end run"""
        subprocess.run(
            ["osascript", "-", command, NAMES.get(lane, lane)],
            input=script,
            text=True,
            check=True,
        )
        atomic(marker, {"at": time.time()})
        print(f"{NAMES.get(lane, lane)}: start requested")
    return 0


def is_context(path):
    # Explicit machine-readable classification; never guess from incidental prose.
    return any(
        s.strip().lower() == "dispatch: context"
        for s in path.read_text().splitlines()[:40]
    )


def contexts(inbox):
    return sorted(
        (p for p in inbox.glob("*.md") if is_context(p)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def integrator_changed(handoff):
    # Only real intake/dependency changes, not this worker's own reports/logs.
    items = []
    for lane in ("integrator",):
        for p in sorted((handoff / "runner-inbox" / lane).glob("*.md")):
            if not p.name.startswith(("SELF-", "RESTOCK-")) and not is_context(p):
                items.append((p.name, hashlib.sha256(p.read_bytes()).hexdigest()))
    for name in ("CERT-QUEUE.md", "CODEX-CERT-LOG.md", "INTEGRATOR-WAKE.json"):
        p = handoff / name
        if p.exists():
            items.append((name, hashlib.sha256(p.read_bytes()).hexdigest()))
    fingerprint = hashlib.sha256(json.dumps(items).encode()).hexdigest()
    p = ROOT / "integrator-input.json"
    old = read(p, {})
    if old.get("fingerprint") == fingerprint and time.time() - old.get("at", 0) < 3600:
        return False
    atomic(p, {"fingerprint": fingerprint, "at": time.time()})
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "status",
            "pause",
            "resume",
            "mode",
            "run",
            "lease",
            "launch",
            "check",
            "state",
            "context",
            "contexts",
            "integrator-ready",
        ],
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    a = ns.args
    if ns.action in ("pause", "resume"):
        lane = a[0] if a else "all"
        if lane not in {*NAMES, "all"}:
            parser.error("Unknown lane")
        p = ROOT / "paused" / lane
        p.parent.mkdir(parents=True, exist_ok=True)
        if ns.action == "pause":
            p.touch()
        else:
            p.unlink(missing_ok=True)
        print(
            f"{lane}: {ns.action} requested; active work is preserved. Run start-lanes.sh for missing workers."
        )
    elif ns.action == "mode":
        limits = {"workday": 3, "quiet": 1, "full": 6}
        if not a or a[0] not in limits:
            parser.error("Use workday, quiet or full")
        atomic(ROOT / "limits.json", {"sessions": limits[a[0]], "mode": a[0]})
        print(
            f"{a[0]}: at most {limits[a[0]]} new model sessions; existing sessions finish normally"
        )
    elif ns.action in ("run", "lease"):
        return execute(a[0], a[1:], lease=ns.action == "lease")
    elif ns.action == "launch":
        return launch(a[0], a[1])
    elif ns.action == "check":
        return 1 if paused(a[0]) else 0
    elif ns.action == "state":
        state(a[0], " ".join(a[1:]))
    elif ns.action == "context":
        return 0 if is_context(Path(a[0])) else 1
    elif ns.action == "contexts":
        budget = 16000
        for p in contexts(Path(a[0])):
            if budget <= 0:
                break
            body = p.read_text()[:budget]
            print(f"\nContext only — {p} (retained original)\n{body}")
            budget -= len(body)
    elif ns.action == "integrator-ready":
        return 0 if integrator_changed(Path(a[0])) else 1
    else:
        limits = read(ROOT / "limits.json", {"sessions": 3, "mode": "workday"})
        print(
            f"Fleet: {limits['mode']}; at most {limits['sessions']} concurrent model sessions; low CPU priority"
        )
        for lane, name in NAMES.items():
            current = read(ROOT / "status" / (lane + ".json"), {})
            pattern = "session-review-*" if lane == "review" else f"session-{lane}.lock"
            active = False
            for path in (ROOT / "locks").glob(pattern):
                with path.open("a") as handle:
                    try:
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        active = True
            message = (
                "Working; pause takes effect after this session"
                if active and paused(lane)
                else (
                    "Working"
                    if active
                    else (
                        "Paused"
                        if paused(lane)
                        else current.get("state", "No runtime receipt yet")
                    )
                )
            )
            age = (
                f"; updated {int(time.time()-current['at'])}s ago"
                if current.get("at")
                else ""
            )
            print(f"{lane:12} {name:25} {message}{age}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
