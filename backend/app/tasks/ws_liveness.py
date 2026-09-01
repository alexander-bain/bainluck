"""Q504-b — the one place `worker-ws` says it is alive, and what it is holding.

WHY THIS EXISTS. On 2026-09-01 the dyno was reported as "up but silent": two
attended `heroku logs` pulls showed ZERO `app[worker-ws.1]` lines while
`worker-realtime` flooded the shared buffer, and the conclusion drawn was that
both socket consumers had wedged before their first log line. They had not — a
per-dyno log pull showed the Kalshi arm connected, 23,456 tickers subscribed and
10,098 price updates in ten minutes. The silence was log-buffer eviction, not a
dead process.

That is still a defect, because *nothing on the dyno could tell the two apart*.
An arm that is streaming and an arm that is wedged in a pre-subscribe await both
produce no output between the 60-second stats lines, and those lines are emitted
BY the arms — so the one state you most need to see is the one state that cannot
report itself.

WHAT THIS FIXES. The registry below is written by the consumers and read by
`run_kalshi_ws.py`, which logs it on its own timer from OUTSIDE both arms. The
heartbeat therefore fires whether or not either consumer has reached its first
log line, and every field it prints is either a count or an AGE:

    worker-ws heartbeat: kalshi[subscribed legs=23456 age=41s stamped=118
    no_reading=6] polymarket[connecting legs=0 age=311s]

`age` is the load-bearing column. A phase that is correct and a phase that is
frozen read identically until you can see how long it has been true, and the
whole cost of this incident was measured in the hours nobody could see that.

NO CLOCK BRANCHING (gotcha #44). `render` takes its `now` rather than reading
one, so the guard tests fix the instant instead of arranging to run at a
convenient time.
"""

from __future__ import annotations

import time
from typing import Any, Optional

#: arm name -> {"phase": str, "at": monotonic, "fields": {...}}
_STATE: dict[str, dict[str, Any]] = {}


def report(arm: str, phase: str, *, now: Optional[float] = None, **fields: Any) -> None:
    """Record what ``arm`` is doing right now.

    Called from the consumers on every state change worth waiting on — slate
    loaded, subscribed, recycling, backing off, crashed — and from their
    60-second stats loops, which is what keeps ``age`` small while an arm is
    healthy and lets it grow the moment one stops making progress.

    Deliberately total and non-raising: this is instrumentation inside a flush
    loop, and instrumentation that can take down the stream it watches is worse
    than no instrumentation (gotcha #42).
    """
    try:
        _STATE[arm] = {
            "phase": phase,
            "at": time.monotonic() if now is None else now,
            "fields": dict(fields),
        }
    except Exception:  # pragma: no cover - defensive; dict writes do not raise
        pass


def snapshot() -> dict[str, dict[str, Any]]:
    """A copy of the registry, safe for the caller to hold."""
    return {
        arm: {"phase": s["phase"], "at": s["at"], "fields": dict(s["fields"])}
        for arm, s in _STATE.items()
    }


def reset() -> None:
    """Drop all state. For tests, and for nothing else."""
    _STATE.clear()


def render(arms: tuple[str, ...], now: float) -> str:
    """The heartbeat line for ``arms``, in the order given.

    An arm that has never reported is printed as ``NEVER REPORTED`` rather than
    omitted. Omitting it would make a consumer that died before its first
    ``report`` look exactly like a consumer that was never configured — which is
    the ambiguity this module exists to remove (gotcha #53: an absence is not a
    response shape).
    """
    parts: list[str] = []
    state = snapshot()
    for arm in arms:
        entry = state.get(arm)
        if entry is None:
            parts.append(f"{arm}[NEVER REPORTED]")
            continue
        age = max(0, int(now - entry["at"]))
        extras = " ".join(f"{k}={v}" for k, v in sorted(entry["fields"].items()))
        body = f"{entry['phase']} age={age}s"
        parts.append(f"{arm}[{body}{' ' + extras if extras else ''}]")
    return "worker-ws heartbeat: " + " ".join(parts)
