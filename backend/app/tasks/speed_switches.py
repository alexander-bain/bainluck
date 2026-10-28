"""#10090 — speed switches trialled on half of the live games, without a release.

Alex's standing approval (ALEX-DECISIONS item 4): Speed may turn an already
reviewed speed switch on and off for live games without asking each time, for
at most HALF of the live games, at most 30 minutes per trial, switching back
automatically when the timer ends or on any error, every trial logged. These
limits are enforced here, not by process:

* the only runtime modes are ``off`` and ``ab``. ``ab`` turns a switch on for
  the events whose id parity equals the trial's ``half`` and for no other
  event. There is no runtime "all games on"; full-on is the switch's env
  default and needs a release or a config change Alex approves.
* a trial is one Redis key per switch (``speed_switch:<name>``), written with
  a TTL of at most `MAX_TTL_S`. The reader also refuses an ``expires_at``
  already passed or more than `MAX_TTL_S` ahead, so a key written by hand
  cannot outlive the limit either.
* every way a read can go wrong — Redis down or slow, a missing key, an
  unknown mode, a malformed value — reads OFF. The hot path never waits for
  Redis: it reads this process's cached state, refreshed on a background task
  at most every `CACHE_S` through `get_redis_client()` (bounded, gotcha #39).
  A cache that has not refreshed for `STALE_S` reads OFF.
* a switched path that raises calls `trip`: that switch is OFF in this
  process for the rest of the trial, logged once.

The layer itself is off unless `TRIALS_ENV` (``SPEED_SWITCH_TRIALS=1``) is
set: off, every switch reads OFF and this module never touches Redis, so a
worker that never runs a trial does exactly what it did before. Turning it on
is one config change; after that each trial is an admin call, not a release.

Each process logs one line whenever a switch's effective mode changes (name,
mode, half, expiry), and `tags(event_id)` gives the receipt suffix that splits
a readout window by arm. The setter is ``POST /api/admin/speed-switch``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

#: Switch names a trial may name. Each is wired where its switched path runs.
#: ``abandon_optional_db`` is `live_blend_refresh.OPTIONAL_DB_ABANDON_ENV`.
SWITCHES = ("abandon_optional_db",)
MODES = ("off", "ab")
KEY_PREFIX = "speed_switch:"
TRIALS_ENV = "SPEED_SWITCH_TRIALS"
#: Alex: at most 30 minutes per trial.
MAX_TTL_S = 1800
CACHE_S = 3.0
STALE_S = 10.0
#: The bound on one background read (socket and connect timeout).
READ_TIMEOUT_S = 0.25


@dataclass(frozen=True)
class SwitchState:
    mode: str = "off"
    half: int = 0
    expires_at: float = 0.0

    def describe(self) -> dict:
        return {"mode": self.mode, "half": self.half if self.mode == "ab" else None,
                "expires_at": self.expires_at if self.mode == "ab" else None}


OFF = SwitchState()


def trials_enabled() -> bool:
    return os.getenv(TRIALS_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def key(name: str) -> str:
    return KEY_PREFIX + name


def parse(raw, now: float) -> SwitchState:
    """The trial a stored value describes, or OFF for anything else."""
    if raw is None:
        return OFF
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        mode, half, expires_at = data["mode"], data["half"], float(data["expires_at"])
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
        return OFF
    if mode != "ab" or type(half) is not int or half not in (0, 1):
        return OFF
    if not math.isfinite(expires_at) or not now < expires_at <= now + MAX_TTL_S:
        return OFF
    return SwitchState("ab", half, expires_at)


def encode(half: int, expires_at: float, set_at: float) -> str:
    return json.dumps({"mode": "ab", "half": half, "expires_at": expires_at,
                       "set_at": set_at}, sort_keys=True)


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

    def state(self, name: str) -> SwitchState:
        """The trial in force for ``name`` in this process now; never waits."""
        enabled = trials_enabled()
        now_m = self._monotonic()
        if enabled and (self._read_at is None or now_m - self._read_at >= CACHE_S):
            self._schedule_refresh()
        state = self._stored.get(name, OFF)
        if (not enabled or self._read_at is None or now_m - self._read_at >= STALE_S
                or state.mode != "ab" or not self._clock() < state.expires_at
                or self._tripped.get(name) == state.expires_at):
            state = OFF
        if self._logged.get(name, OFF) != state:
            self._logged[name] = state
            logger.info(
                "speed_switch[pid=%d]: %s mode=%s half=%s expires_at=%s",
                os.getpid(), name, state.mode,
                state.half if state.mode == "ab" else "-",
                _iso(state.expires_at) if state.mode == "ab" else "-",
            )
        return state

    def arm(self, name: str, event_id: int) -> bool:
        """Whether ``name`` is on for this event: only its trial's half, only while it runs."""
        state = self.state(name)
        return state.mode == "ab" and int(event_id) % 2 == state.half

    def tags(self, event_id: int) -> str:
        """The receipt suffix: `` sw=<name>:<on|off>`` per running trial, else empty."""
        return "".join(
            f" sw={name}:{'on' if self.arm(name, event_id) else 'off'}"
            for name in SWITCHES if self.state(name).mode == "ab"
        )

    def trip(self, name: str, error: BaseException) -> None:
        """A switched path raised: OFF in this process for the rest of the trial."""
        state = self.state(name)
        if state.mode != "ab":
            return
        self._tripped[name] = state.expires_at
        logger.warning(
            "speed_switch[pid=%d]: %s switched off for the rest of its trial "
            "(expires_at=%s) after %s: %s",
            os.getpid(), name, _iso(state.expires_at), type(error).__name__, error,
        )
        self.state(name)

    def _schedule_refresh(self) -> None:
        if self._refresh is not None and not self._refresh.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._refresh = loop.create_task(self._refresh_once(), name="speed-switch-read")

    async def _refresh_once(self) -> None:
        try:
            async with asyncio.timeout(2 * READ_TIMEOUT_S):
                values = await asyncio.to_thread(self._read)
            now = self._clock()
            stored = {name: parse(raw, now) for name, raw in zip(SWITCHES, values)}
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
