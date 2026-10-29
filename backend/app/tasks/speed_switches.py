"""#10090 — speed switches trialled without a release: on half of the live
games, or on alternate wall-clock periods for server-wide settings.

Alex's standing approval (ALEX-DECISIONS item 4): Speed may turn an already
reviewed speed switch on and off for live games without asking each time, for
at most HALF of the live games, at most 30 minutes per trial, switching back
automatically when the timer ends or on any error, every trial logged. These
limits are enforced here, not by process:

* the runtime modes are ``off``, ``ab`` and ``alternate``. ``ab`` turns a
  switch on for the events whose id parity equals the trial's ``half`` and
  for no other event. ``alternate`` switches between two values ``a`` and
  ``b`` every ``period_s`` (a whole number of minutes, from a minute boundary)
  of wall-clock time, so every venue process agrees on the arm and each UTC
  minute — a delivery-receipt window — falls in one arm. A boolean switch
  alternates off/on; a numeric one must keep today's value on one arm
  (`SPECS`). An alternation runs a whole number of a/b pairs from its start
  minute (`expiry`), so it spends at most half its minutes away from today.
  There is no runtime "all games on"; full-on is the switch's env default and
  needs a release or a config change Alex approves.
* a trial is one Redis key per switch (``speed_switch:<name>``), written with
  a TTL of at most `MAX_TTL_S`. The reader also refuses an ``expires_at``
  already passed or more than `MAX_TTL_S` ahead, so a key written by hand
  cannot outlive the limit either.
* every way a read can go wrong — Redis down or slow, a missing key, an
  unknown mode, a malformed value — reads OFF, which is the env value. The
  hot path never waits for Redis: it reads this process's cached state,
  refreshed on a background task at most every `CACHE_S` through
  `get_redis_client()` with a `READ_TIMEOUT_S` socket bound (gotcha #39).
  A cache that has not refreshed for `STALE_S` reads OFF.
* a switched path that fails calls `trip`: that switch is OFF in this
  process for the rest of the trial, logged once.

The layer itself is off unless `TRIALS_ENV` (``SPEED_SWITCH_TRIALS=1``) is
set: off, every switch reads OFF and this module never touches Redis, so a
worker that never runs a trial does exactly what it did before. Turning it on
is one config change; after that each trial is an admin call, not a release.

Each process logs one line whenever a switch's trial changes (name, mode,
half or values, expiry) and one line at every arm boundary of an alternation.
`tags(event_id, at)` gives the receipt suffix that splits a readout by arm.
The setter is ``POST /api/admin/speed-switch``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

#: Switch name → what a trial of it may do. ``values`` bounds ``a``/``b``;
#: ``today`` must be one of them, so an alternation spends at most half the
#: time away from today's behaviour.
SPECS = {
    # `live_blend_refresh.OPTIONAL_DB_ABANDON_ENV`: a pool-level switch, so
    # `alternate` (off/on by period) is its faithful comparison.
    "abandon_optional_db": {"modes": ("ab", "alternate"), "values": (0, 1), "today": 0},
    # `live_blend_refresh.FRESH_FLUSH_PENDING_ATTEMPTS`, read once per flush.
    # Its "today" is the worker's own setting (an env since #11709), `today()`.
    "pending_attempts": {"modes": ("alternate",), "values": (1, 32), "today": 1},
    # `live_blend_refresh.ADMITTED_DEBT_SLOTS`, read once per door admission.
    # Its "today" is likewise the worker's own setting (an env since #11718).
    "admitted_debt_slots": {"modes": ("alternate",), "values": (1, 3), "today": 1},
    # `live_blend_refresh.RELEASE_UNATTEMPTED_DEBT_SWITCH`, read once per mixed
    # refresh: when a call's unattempted old events leave its fence.
    "release_unattempted_debt": {"modes": ("alternate",), "values": (0, 1), "today": 0},
}
SWITCHES = tuple(SPECS)
MODES = ("off", "ab", "alternate")
KEY_PREFIX = "speed_switch:"
TRIALS_ENV = "SPEED_SWITCH_TRIALS"
#: Alex: at most 30 minutes per trial.
MAX_TTL_S = 1800
#: An alternation period is a whole number of minutes in this range.
PERIOD_MIN_S = 60
PERIOD_MAX_S = 900
CACHE_S = 3.0
STALE_S = 10.0
#: The socket bound on one background read; the whole read is bounded at 2×.
READ_TIMEOUT_S = 0.25


@dataclass(frozen=True)
class SwitchState:
    mode: str = "off"
    half: int = 0
    expires_at: float = 0.0
    a: int = 0
    b: int = 0
    period_s: int = 0
    start: float = 0.0

    def arm_index(self, at: float) -> int:
        """0 while ``a`` is in force, 1 while ``b`` is (alternate only)."""
        return int((at - self.start) // self.period_s) % 2

    def value_at(self, at: float) -> int:
        return self.a if self.arm_index(at) == 0 else self.b

    def describe(self) -> dict:
        out = {"mode": self.mode, "half": None, "expires_at": None}
        if self.mode == "ab":
            out.update(half=self.half, expires_at=self.expires_at)
        elif self.mode == "alternate":
            out.update(expires_at=self.expires_at, a=self.a, b=self.b,
                       period_s=self.period_s, start=self.start)
        return out


OFF = SwitchState()


def trials_enabled() -> bool:
    return os.getenv(TRIALS_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def key(name: str) -> str:
    return KEY_PREFIX + name


#: Switches whose "today" is a worker env setting in `live_blend_refresh`.
_TODAY_SETTINGS = {
    "pending_attempts": "FRESH_FLUSH_PENDING_ATTEMPTS",
    "admitted_debt_slots": "ADMITTED_DEBT_SLOTS",
}


def today(name: str) -> int:
    """A switch's value with no trial running: `pending_attempts` and
    `admitted_debt_slots` read the worker's own setting, so an alternation
    always keeps the value actually in force on one arm whatever it is."""
    setting = _TODAY_SETTINGS.get(name)
    if setting is not None:
        from app.tasks import live_blend_refresh

        return getattr(live_blend_refresh, setting)
    return SPECS[name]["today"]


def _int(value) -> bool:
    return type(value) is int


def validate(name: str, mode: str, half=0, a=None, b=None, period_s=None,
             span_s=None) -> Optional[str]:
    """Why this trial is outside the limits, or None. ``span_s`` is an
    alternation's length from its start minute, when known."""
    spec = SPECS.get(name)
    if spec is None:
        return f"unknown switch; allowed: {list(SWITCHES)}"
    if mode not in spec["modes"]:
        return f"{name} allows modes {list(spec['modes'])}"
    if mode == "ab":
        return None if _int(half) and half in (0, 1) else "half must be 0 or 1"
    low, high = spec["values"]
    if not (_int(a) and _int(b) and low <= a <= high and low <= b <= high):
        return f"a and b must be integers in {low}..{high}"
    if today(name) not in (a, b) or a == b:
        return f"one of a/b must be today's {today(name)} and the other must differ"
    if not (_int(period_s) and PERIOD_MIN_S <= period_s <= PERIOD_MAX_S
            and period_s % 60 == 0):
        return f"period_s must be a whole number of minutes in {PERIOD_MIN_S}..{PERIOD_MAX_S}"
    if span_s is not None and not (0 < span_s <= MAX_TTL_S and span_s % (2 * period_s) == 0):
        return (f"ttl_s must be a whole number of a/b pairs ({2 * period_s} s each) up to "
                f"{MAX_TTL_S}, so each arm runs equally long")
    return None


def parse(raw, now: float, name: str) -> SwitchState:
    """The trial a stored value describes, or OFF for anything else."""
    if raw is None:
        return OFF
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        mode, expires_at = data["mode"], float(data["expires_at"])
        if mode == "ab":
            half, a, b, period_s, start = data["half"], 0, 0, None, 0.0
        else:
            half = 0
            a, b, period_s = data["a"], data["b"], data["period_s"]
            start = float(data["start"])
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
        return OFF
    span_s = expires_at - start if mode == "alternate" else None
    if validate(name, mode, half, a, b, period_s, span_s) is not None:
        return OFF
    if not math.isfinite(expires_at) or not now < expires_at <= now + MAX_TTL_S:
        return OFF
    if mode == "alternate" and not (math.isfinite(start) and start % 60 == 0
                                    and start <= now + 60):
        return OFF
    return SwitchState(mode, half, expires_at, a, b, period_s or 0, start)


def expiry(mode: str, ttl_s: int, set_at: float) -> float:
    """When a trial set at ``set_at`` ends: an alternation ``ttl_s`` after its
    start minute (whole a/b pairs, so each arm runs equally long), anything else
    ``ttl_s`` after it is set."""
    if mode == "alternate":
        return math.floor(set_at / 60) * 60.0 + ttl_s
    return set_at + ttl_s


def encode(name: str, mode: str, expires_at: float, set_at: float, *, half=0, a=None,
           b=None, period_s=None) -> str:
    data = {"mode": mode, "expires_at": expires_at, "set_at": set_at}
    if mode == "ab":
        data["half"] = half
    else:
        # From the minute the trial is set, so arms follow UTC minutes.
        data.update(a=a, b=b, period_s=period_s, start=math.floor(set_at / 60) * 60.0)
    return json.dumps(data, sort_keys=True)


def _read_stored() -> list:
    from app.tasks.redis_state import get_redis_client

    client = get_redis_client(socket_timeout=READ_TIMEOUT_S,
                              socket_connect_timeout=READ_TIMEOUT_S, fast_fail=True)
    return client.mget([key(name) for name in SWITCHES])


class SpeedSwitches:
    """One process's view of the running trials."""

    def __init__(self, read: Callable[[], list] = _read_stored,
                 clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        self._read = read
        self._clock = clock
        self._monotonic = monotonic
        self._stored: dict[str, SwitchState] = {}
        self._read_at: Optional[float] = None
        self._refresh: Optional[asyncio.Task] = None
        self._tripped: dict[str, float] = {}
        self._logged: dict[str, SwitchState] = {}
        self._reads_lock = threading.Lock()
        self._reads_running = 0
        self._logged_arm: dict[str, tuple] = {}
        #: When this process began running each switch's current state.
        self._since: dict[str, float] = {}

    def state(self, name: str) -> SwitchState:
        """The trial in force for ``name`` in this process now; never waits."""
        enabled = trials_enabled()
        now_m = self._monotonic()
        if enabled and (self._read_at is None or now_m - self._read_at >= CACHE_S):
            self._schedule_refresh()
        state = self._stored.get(name, OFF)
        if (not enabled or self._read_at is None or now_m - self._read_at >= STALE_S
                or state.mode == "off" or not self._clock() < state.expires_at
                or self._tripped.get(name) == state.expires_at):
            state = OFF
        if self._logged.get(name, OFF) != state:
            self._logged[name] = state
            self._since[name] = self._clock()
            self._logged_arm.pop(name, None)
            logger.info(
                "speed_switch[pid=%d]: %s mode=%s half=%s values=%s period_s=%s expires_at=%s",
                os.getpid(), name, state.mode,
                state.half if state.mode == "ab" else "-",
                f"{state.a}/{state.b}" if state.mode == "alternate" else "-",
                state.period_s if state.mode == "alternate" else "-",
                _iso(state.expires_at) if state.mode != "off" else "-",
            )
        return state

    def value(self, name: str, default: int, at: Optional[float] = None) -> int:
        """A numeric switch's value now (or at ``at``): the alternation's arm, else ``default``."""
        state = self.state(name)
        if state.mode != "alternate":
            return default
        when = self._clock() if at is None else at
        if at is None:
            self._note_arm(name, state, when)
        return state.value_at(when)

    def arm(self, name: str, event_id: int, at: Optional[float] = None) -> bool:
        """Whether a boolean switch is on for this event now (or at ``at``)."""
        state = self.state(name)
        if state.mode == "ab":
            return int(event_id) % 2 == state.half
        if state.mode == "alternate":
            when = self._clock() if at is None else at
            if at is None:
                self._note_arm(name, state, when)
            return state.value_at(when) == 1
        return False

    def tags(self, event_id: int, at: Optional[float] = None) -> str:
        """The receipt suffix: `` sw=<name>:<arm>`` per running trial, else empty.

        A boolean switch's arm is ``on``/``off``; a numeric one's is its value.
        ``at`` is the moment the receipt describes (a delivery window's start).
        A window that opened before this process began running the trial (the
        minute before it, or the one it began in) carries no arm.
        """
        out = []
        for name in SWITCHES:
            state = self.state(name)
            if state.mode == "off":
                continue
            if at is not None and at < self._since.get(name, 0.0):
                continue
            if SPECS[name]["values"] == (0, 1):
                arm = "on" if self.arm(name, event_id, at) else "off"
            else:
                arm = str(self.value(name, today(name), at))
            out.append(f" sw={name}:{arm}")
        return "".join(out)

    def trip(self, name: str, error: BaseException) -> None:
        """A switched path failed: OFF in this process for the rest of the trial."""
        state = self.state(name)
        if state.mode == "off":
            return
        self._tripped[name] = state.expires_at
        logger.warning(
            "speed_switch[pid=%d]: %s switched off for the rest of its trial "
            "(expires_at=%s) after %s: %s",
            os.getpid(), name, _iso(state.expires_at), type(error).__name__, error,
        )
        self.state(name)

    def _note_arm(self, name: str, state: SwitchState, at: float) -> None:
        """One line per process at each arm boundary of an alternation."""
        index = int((at - state.start) // state.period_s)
        mark = (state, index)
        if self._logged_arm.get(name) == mark:
            return
        self._logged_arm[name] = mark
        logger.info(
            "speed_switch[pid=%d]: %s arm=%s value=%s since=%s until=%s",
            os.getpid(), name, "ab"[index % 2], state.value_at(at),
            _iso(state.start + index * state.period_s),
            _iso(min(state.start + (index + 1) * state.period_s, state.expires_at)),
        )

    def _schedule_refresh(self) -> None:
        if self._refresh is not None and not self._refresh.done():
            return
        if self._reads_running:
            # The last read's thread outlived its bound (a stalled resolver is not
            # bounded by socket timeouts): never start a second; the cache goes
            # stale and reads OFF meanwhile.
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._refresh = loop.create_task(self._refresh_once(), name="speed-switch-read")

    def _read_counted(self) -> list:
        with self._reads_lock:
            self._reads_running += 1
        try:
            return self._read()
        finally:
            with self._reads_lock:
                self._reads_running -= 1

    async def _refresh_once(self) -> None:
        try:
            async with asyncio.timeout(2 * READ_TIMEOUT_S):
                values = await asyncio.to_thread(self._read_counted)
            now = self._clock()
            stored = {name: parse(raw, now, name) for name, raw in zip(SWITCHES, values)}
        except Exception:  # noqa: BLE001 — every failure reads OFF
            logger.debug("speed_switch: read failed; every switch reads off", exc_info=True)
            stored = {}
        self._stored = stored
        self._read_at = self._monotonic()


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


_SWITCHES: Optional[SpeedSwitches] = None
_SWITCHES_PID: Optional[int] = None


def speed_switches() -> SpeedSwitches:
    """This process's switches (a forked venue process gets its own)."""
    global _SWITCHES, _SWITCHES_PID
    if _SWITCHES is None or _SWITCHES_PID != os.getpid():
        _SWITCHES, _SWITCHES_PID = SpeedSwitches(), os.getpid()
    return _SWITCHES
