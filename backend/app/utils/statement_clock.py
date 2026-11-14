"""#12042: time every statement of one task run, so a run that hits its soft limit
names the statement it was in.

``update_max_movement`` raised ``SoftTimeLimitExceeded`` on every run Fable read
on Nov 12 (7:23, 8:52 and 9:06 AM PT), light and heavy alike. It is ~1,700 lines
of statements in one session with no phase timings, so a bound would be a guess.
This wraps the session: each ``execute`` is timed under a short label (the
statement's first words, or its leading SQL comment), and the statement still in
flight is remembered. The summary is logged from the task's outer ``finally``,
which runs even when the soft-limit signal lands inside the event loop.

Instrumentation only: it forwards every call unchanged and never raises.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

_SPACE = re.compile(r"\s+")
LABEL_CHARS = 72


def statement_label(statement: Any) -> str:
    """A short, stable name for a statement: its first words, comments included."""
    try:
        text = _SPACE.sub(" ", str(statement)).strip()
    except Exception:
        return "<unprintable>"
    return text[:LABEL_CHARS] or "<empty>"


class StatementClock:
    """A session wrapper that times ``execute`` and forwards everything else."""

    def __init__(self, session: Any, clock=time.monotonic):
        self._session = session
        self._clock = clock
        self._started = clock()
        #: label -> [seconds, calls]
        self.totals: dict[str, list] = {}
        #: (label, started) of the statement in flight, else None
        self.in_flight: Optional[tuple[str, float]] = None
        #: (label, seconds) of the statement an exception left (e.g. the soft
        #: limit), which ``in_flight`` no longer shows once it has unwound
        self.interrupted: Optional[tuple[str, float]] = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        label = statement_label(statement)
        started = self._clock()
        self.in_flight = (label, started)
        try:
            return await self._session.execute(statement, *args, **kwargs)
        except BaseException:
            self.interrupted = (label, self._clock() - started)
            raise
        finally:
            spent = self._clock() - started
            entry = self.totals.setdefault(label, [0.0, 0])
            entry[0] += spent
            entry[1] += 1
            self.in_flight = None

    def summary(self, top: int = 6) -> str:
        """One log line: run time, statement time, the slowest labels, and what
        was in flight. Never raises."""
        try:
            now = self._clock()
            ranked = sorted(self.totals.items(), key=lambda kv: kv[1][0], reverse=True)[:top]
            parts = [f"{secs:.1f}s x{calls} [{label}]" for label, (secs, calls) in ranked]
            in_flight = (
                f"{now - self.in_flight[1]:.1f}s in [{self.in_flight[0]}]"
                if self.in_flight
                else "none"
            )
            interrupted = (
                f"{self.interrupted[1]:.1f}s in [{self.interrupted[0]}]"
                if self.interrupted
                else "none"
            )
            spent = sum(v[0] for v in self.totals.values())
            return (
                f"elapsed={now - self._started:.1f}s statements={spent:.1f}s "
                f"in_flight={in_flight} interrupted={interrupted} slowest: "
                + "; ".join(parts)
            )
        except Exception as exc:  # noqa: BLE001 — instrumentation never raises
            return f"summary unavailable: {type(exc).__name__}"
