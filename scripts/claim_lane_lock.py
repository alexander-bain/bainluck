#!/usr/bin/env python3
"""The shared lane-lock claim primitive — ruling 022.

ONE implementation of READ -> TEST -> WRITE, consumed by every lane and by the
Integrator. Hand-rolled claim logic is deleted, not deprecated: a second path
that still works is a second path that still gets used, under time pressure, by
the lane that does not know this exists yet.

Why this file exists, in three failures inside two days:

* **Queue 309 overwrote INT-033's held claim** mid-gate-run, in good faith,
  obeying ruling 017's instruction to take the lock. Nothing told it that taking
  could be refused.
* **INT-035's regex claim** pattern-matched ``^status: RELEASED`` and appended a
  ``HELD`` line without reading the current value, against a lock held by a live
  Queue 310. The authoritative fields survived only because the pattern found
  nothing to replace. It was written by the author of the rule forbidding it,
  hours later. The mistake was never in the understanding.
* **A fresh latency window self-identified as INT-036 from ambient tree state**
  and proceeded with that authority, having claimed nothing.

Usage::

    python3 scripts/claim_lane_lock.py claim   <lock_path> --queue "INT-037" [--note "..."]
    python3 scripts/claim_lane_lock.py release <lock_path> [--note "..."]
    python3 scripts/claim_lane_lock.py check   <lock_path>

Exit codes: ``0`` acquired/released/free, ``1`` REFUSED (held by a live other),
``2`` malformed lock. A refusal is a normal outcome, not an error to retry past.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from typing import Optional

#: The process name of a Claude Code session. Identity resolution walks up to it.
SESSION_COMM_MARKER = "native/claude"

FREE_STATES = {"RELEASED", "FREE"}


def _ps_alive(pid: int) -> bool:
    """Ruling 008: `ps` is the whole test. Never the heartbeat."""
    return subprocess.run(
        ["ps", "-p", str(pid)], capture_output=True
    ).returncode == 0


def _comm(pid: int) -> str:
    out = subprocess.run(
        ["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True
    )
    return out.stdout.strip()


def _ppid(pid: int) -> Optional[int]:
    out = subprocess.run(
        ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True
    )
    raw = out.stdout.strip()
    return int(raw) if raw.isdigit() else None


def session_pid() -> int:
    """Resolve the SESSION's pid — ruling 022 addendum, as CORRECTED.

    The addendum as first written said "held by me requires ``owner_pid == $$``".
    **That is wrong for a Claude Code window and would never match.** Every Bash
    tool call runs in a FRESH SUBSHELL, so ``$$`` is a different number every
    time and never equals the long-lived session process. A lane testing
    ``owner_pid == $$`` can neither confirm nor refute its own identity: it would
    refuse its own valid lock, then "recover" by overwriting it — turning the
    guard into the very failure it was written to stop.

    Caught by the LAT-P026 window, which is exactly the review the ruling wanted.

    So identity is resolved by walking ``ppid`` up to the ``native/claude``
    ancestor. That process outlives every subshell and is the thing a lock owner
    actually IS. Falls back to the top-most reachable ancestor if the marker is
    not found (a non-Claude caller, e.g. a human at a terminal), which is
    honest: it identifies the longest-lived thing we can prove.
    """
    pid = os.getpid()
    seen = set()
    while pid and pid not in seen and pid > 1:
        seen.add(pid)
        if SESSION_COMM_MARKER in _comm(pid):
            return pid
        parent = _ppid(pid)
        if parent is None or parent <= 1:
            break
        pid = parent
    return pid


def _read(path: str) -> tuple[str, str, Optional[int], re.Match]:
    try:
        text = open(path).read()
    except OSError as exc:
        print(f"MALFORMED: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    m = re.search(r"(?m)^status:\s*(\S+)", text)
    if not m:
        print(f"MALFORMED: no `status:` line in {path}", file=sys.stderr)
        sys.exit(2)
    pm = re.search(r"(?m)^(?:owner_)?pid:\s*(\d+)", text)
    return text, m.group(1).upper().rstrip(","), (int(pm.group(1)) if pm else None), m


def cmd_check(args) -> int:
    text, status, owner, _ = _read(args.lock)
    me = session_pid()
    alive = _ps_alive(owner) if owner else False
    # Ruling 013: an explicit RELEASED/free frees the lock regardless of pid.
    if status in FREE_STATES:
        verdict = "FREE (explicitly released)"
    elif status == "HELD" and owner == me:
        verdict = "HELD BY ME"
    elif status == "HELD" and alive:
        verdict = f"HELD by a LIVE other (pid {owner})"
    elif status == "HELD":
        verdict = f"FREE (owner pid {owner} is dead — takeover, record it)"
    else:
        verdict = f"UNKNOWN status {status!r} — treat as HELD and stop"
    print(f"status={status} owner_pid={owner} alive={alive} me={me} -> {verdict}")
    return 0


def cmd_claim(args) -> int:
    text, status, owner, m = _read(args.lock)
    me = session_pid()

    # --- TEST, before any write. This is the whole ruling. ---
    if status == "HELD" and owner is not None and owner != me and _ps_alive(owner):
        print(
            f"REFUSED: lock is HELD by pid {owner}, which is ALIVE and is not me ({me}).\n"
            f"You are the second writer. Stop and say so — do NOT overwrite.",
            file=sys.stderr,
        )
        return 1
    if status not in FREE_STATES and status != "HELD":
        print(f"REFUSED: unrecognised status {status!r}; treating as held.", file=sys.stderr)
        return 1

    takeover = status == "HELD" and owner is not None and owner != me and not _ps_alive(owner)
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M %Z")

    # --- WRITE, only now. ---
    new = text[: m.start()] + f"status: HELD   # {stamp} — {args.queue}." + text[m.end():]
    new = re.sub(r"(?m)^(owner_)?pid:.*$", lambda mo: f"{mo.group(1) or ''}pid: {me}", new, count=1)
    new = re.sub(r"(?m)^queue:.*$", f"queue: {args.queue}", new, count=1)
    line = f"- {stamp} — **HELD** by {args.queue}, pid {me} (claimed via scripts/claim_lane_lock.py)."
    if takeover:
        line += f" **TAKEOVER**: prior owner pid {owner} was dead."
    if args.note:
        line += f" {args.note}"
    new += line + "\n"
    open(args.lock, "w").write(new)
    print(f"CLAIMED {args.queue} pid={me}" + (" (takeover)" if takeover else ""))
    return 0


def cmd_release(args) -> int:
    text, status, owner, m = _read(args.lock)
    me = session_pid()
    if status == "HELD" and owner is not None and owner != me and _ps_alive(owner):
        print(
            f"REFUSED: will not release a lock HELD by a live other (pid {owner}).",
            file=sys.stderr,
        )
        return 1
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M %Z")
    new = text[: m.start()] + f"status: RELEASED   # {stamp}." + text[m.end():]
    line = f"- {stamp} — **RELEASED** by pid {me}."
    if args.note:
        line += f" {args.note}"
    new += line + "\n"
    open(args.lock, "w").write(new)
    print(f"RELEASED pid={me}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("claim", "release", "check"):
        s = sub.add_parser(name)
        s.add_argument("lock")
        s.add_argument("--note", default="")
        if name == "claim":
            s.add_argument("--queue", required=True)
    args = ap.parse_args()
    return {"claim": cmd_claim, "release": cmd_release, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
