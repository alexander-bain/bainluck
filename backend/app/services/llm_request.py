"""Every backend LLM completion goes through ``complete_chat`` (#11042 slice 3).

``app.services.llm_models`` decides WHICH model a task calls and what it costs.
This module decides WHETHER the call may happen, and books what it spent:

1. **Reserve before every attempt.** Each attempt first reserves the most it can
   be billed (``cost_upper_bound_usd``: a byte-count bound on the prompt plus a
   full-length answer) against the caller's per-job budget, if it has one, and
   against one shared daily budget for every task on every dyno. A reservation
   that does not fit refuses the call. On a response with usage the reservation
   is settled down to the real cost; with no usage it is KEPT, because unknown
   is not zero.
2. **This layer owns retries.** Clients are built with ``max_retries=0`` (guarded
   in ``tests/test_llm_request_budget_11042.py``) and ``complete_chat`` retries a
   timeout, 408/409/429 or 5xx up to ``max_retries`` times (default 2, the SDK
   default every client had) with capped, jittered backoff. Each attempt is
   reserved on its own: an error the provider answered is released (no
   completion was billed); a timeout or dropped connection keeps its
   reservation, because the provider may have finished it.
3. **A bounded number of calls in flight per process.** A thread semaphore held
   by the thread making the call — not by an async wrapper, which cancellation
   would release while the OS thread carries on (see ``app/utils/async_llm.py``).

Every refusal raises ``LLMCallRefused``. Every call site already turns an
exception into its deterministic/no-copy fallback, so a refused call behaves like
a provider outage: the feature degrades, nothing is written.

The shared daily budget is ``LLM_DAILY_BUDGET_USD`` (default 10, the #11042
portfolio ceiling). At the old model's rates the scheduled workload in
``tasks/__init__.py`` is a few dollars a day, so the default bounds a runaway
without binding normal running; the per-task totals the ledger keeps are the
live cost the issue says the cap should later be set from. A malformed value,
or Redis being unreachable, refuses: a spend that cannot be booked is not free.
"""

from __future__ import annotations

import logging
import math
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.services.llm_models import (
    chat_request_kwargs,
    cost_upper_bound_usd,
    estimate_cost_usd,
)

logger = logging.getLogger(__name__)

DAILY_BUDGET_ENV = "LLM_DAILY_BUDGET_USD"
DEFAULT_DAILY_BUDGET_USD = 10.0

CONCURRENCY_ENV = "LLM_MAX_CONCURRENCY"
#: Twice ``app.utils.async_llm.MAX_CONCURRENT_LLM_CALLS``: that pool's four
#: workers plus as many direct callers in the same process never wait.
DEFAULT_MAX_CONCURRENCY = 8
#: How long a call waits for a slot before it is refused.
CONCURRENCY_WAIT_S = 10.0

#: The OpenAI SDK's own defaults, so moving retries here changes no schedule.
DEFAULT_MAX_RETRIES = 2
MAX_RETRIES_CEILING = 3
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0
_RETRYABLE_STATUS = frozenset({408, 409, 429})

_MICROS = 1_000_000
_LEDGER_TTL_S = 3 * 24 * 3600
_KEY_PREFIX = "bainluck:llm_budget"


class LLMCallRefused(RuntimeError):
    """The request layer declined to send a call."""


class LLMBudgetExceeded(LLMCallRefused):
    """The call's reservation does not fit the job or shared daily budget."""


class LLMBudgetUnavailable(LLMCallRefused):
    """The budget cannot be read or booked (malformed config, ledger down)."""


class LLMConcurrencyExhausted(LLMCallRefused):
    """No in-flight slot freed up within ``CONCURRENCY_WAIT_S``."""


def _to_micros(usd: float) -> int:
    return int(math.ceil(usd * _MICROS))


@dataclass(frozen=True)
class ChatResult:
    """A completed call: the SDK response, the model asked, and what it cost.

    ``cost_usd`` is ``None`` when the response carried no usable usage.
    """

    response: Any
    model: str
    cost_usd: Optional[float]


class JobBudget:
    """A per-run spending limit that every attempt reserves against first.

    Thread-safe; lives for one job invocation. Spent is the settled total plus
    any reservation still held (kept reservations are spent).
    """

    def __init__(self, limit_usd: float):
        self._limit = _to_micros(limit_usd)
        self._held = 0
        self._lock = threading.Lock()

    def _reserve(self, micros: int) -> bool:
        with self._lock:
            if self._held + micros > self._limit:
                return False
            self._held += micros
            return True

    def _adjust(self, delta: int) -> None:
        with self._lock:
            self._held += delta

    @property
    def spent_usd(self) -> float:
        return self._held / _MICROS


# --------------------------------------------------------------------------
# The shared daily ledger
# --------------------------------------------------------------------------

_RESERVE_LUA = """
local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
if cur + amount > tonumber(ARGV[2]) then
  return 0
end
redis.call('INCRBY', KEYS[1], amount)
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('HINCRBY', KEYS[2], ARGV[4], amount)
redis.call('HINCRBY', KEYS[2], ARGV[4] .. ':calls', 1)
redis.call('EXPIRE', KEYS[2], ARGV[3])
return 1
"""


class RedisBudgetLedger:
    """Micro-dollars reserved per UTC day, shared by every process of both apps.

    ``bainluck:llm_budget:<day>`` is the day's total; ``…:<day>:tasks`` holds
    each task's total and attempt count. The check and the increment are one
    Lua script, so two dynos cannot both squeeze into the last dollar.
    """

    def __init__(self):
        self._script = None

    def _client(self):
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()

    def reserve(self, day: str, task: str, micros: int, cap_micros: int) -> bool:
        client = self._client()
        if self._script is None:
            self._script = client.register_script(_RESERVE_LUA)
        key = f"{_KEY_PREFIX}:{day}"
        return bool(
            self._script(keys=[key, f"{key}:tasks"], args=[micros, cap_micros, _LEDGER_TTL_S, task], client=client)
        )

    def adjust(self, day: str, task: str, delta: int) -> None:
        key = f"{_KEY_PREFIX}:{day}"
        pipe = self._client().pipeline()
        pipe.incrby(key, delta)
        pipe.hincrby(f"{key}:tasks", task, delta)
        pipe.execute()


class MemoryBudgetLedger:
    """The same contract in one process; tests install it (``set_ledger``)."""

    def __init__(self):
        self.totals: dict[str, int] = {}
        self.tasks: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def reserve(self, day: str, task: str, micros: int, cap_micros: int) -> bool:
        with self._lock:
            if self.totals.get(day, 0) + micros > cap_micros:
                return False
            self.totals[day] = self.totals.get(day, 0) + micros
            self.tasks[(day, task)] = self.tasks.get((day, task), 0) + micros
            return True

    def adjust(self, day: str, task: str, delta: int) -> None:
        with self._lock:
            self.totals[day] = self.totals.get(day, 0) + delta
            self.tasks[(day, task)] = self.tasks.get((day, task), 0) + delta


_ledger: Any = None
_ledger_lock = threading.Lock()


def set_ledger(ledger: Any) -> None:
    """Install the ledger every call books against (``None`` = Redis, lazily)."""
    global _ledger
    _ledger = ledger


def _get_ledger():
    global _ledger
    with _ledger_lock:
        if _ledger is None:
            _ledger = RedisBudgetLedger()
        return _ledger


def daily_budget_micros() -> int:
    raw = os.getenv(DAILY_BUDGET_ENV)
    if raw is None or not raw.strip():
        return _to_micros(DEFAULT_DAILY_BUDGET_USD)
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or value < 0:
        raise LLMBudgetUnavailable(f"{DAILY_BUDGET_ENV}={raw!r} is not a non-negative number")
    return _to_micros(value)


class _Hold:
    """One attempt's reservation: settle it to a known cost, release it, or keep it."""

    def __init__(self, ledger, day: str, task: str, micros: int, job: Optional[JobBudget]):
        self._ledger, self._day, self._task = ledger, day, task
        self.micros = micros
        self._job = job

    def settle(self, actual_micros: int) -> None:
        delta = actual_micros - self.micros
        if delta == 0:
            return
        if delta > 0:
            logger.warning("LLM task %s cost %d micro-USD over its reservation", self._task, delta)
        if self._job is not None:
            self._job._adjust(delta)
        try:
            self._ledger.adjust(self._day, self._task, delta)
        except Exception as exc:  # the reservation stands: an over-count, never an under-count
            logger.warning("LLM budget settle failed for %s: %s", self._task, exc)

    def keep(self) -> None:
        """Unknown cost: the worst case stays booked."""


def _reserve(task: str, micros: int, cap: int, job: Optional[JobBudget], day: str) -> _Hold:
    if job is not None and not job._reserve(micros):
        raise LLMBudgetExceeded(f"LLM task {task}: job budget exhausted")
    ledger = _get_ledger()
    try:
        ok = ledger.reserve(day, task, micros, cap)
    except Exception as exc:
        if job is not None:
            job._adjust(-micros)
        raise LLMBudgetUnavailable(f"LLM budget ledger unavailable: {exc}") from exc
    if not ok:
        if job is not None:
            job._adjust(-micros)
        logger.warning("LLM task %s refused: shared daily budget exhausted (%s)", task, day)
        raise LLMBudgetExceeded(f"LLM task {task}: shared daily budget exhausted")
    return _Hold(ledger, day, task, micros, job)


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------

_slots: Optional[threading.BoundedSemaphore] = None
_slots_lock = threading.Lock()


def _get_slots() -> threading.BoundedSemaphore:
    global _slots
    with _slots_lock:
        if _slots is None:
            try:
                size = int(os.getenv(CONCURRENCY_ENV) or DEFAULT_MAX_CONCURRENCY)
            except ValueError:
                size = DEFAULT_MAX_CONCURRENCY
            _slots = threading.BoundedSemaphore(max(1, size))
        return _slots


# --------------------------------------------------------------------------
# Retries
# --------------------------------------------------------------------------

_sleep = time.sleep


def _openai_errors():
    try:
        import openai
    except ImportError:  # pragma: no cover - the package is a requirement
        return (), ()
    return (openai.APIStatusError,), (openai.APIConnectionError,)


def _retry_delay(attempt: int, exc: Any) -> float:
    """Full-jitter exponential backoff, honouring a short ``Retry-After``."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        after = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        after = None
    if after is not None and 0 <= after <= BACKOFF_CAP_S:
        return after
    return random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** attempt)))


def _utc_day(today: Optional[date]) -> str:
    return (today or datetime.now(timezone.utc).date()).isoformat()


# --------------------------------------------------------------------------
# The one entry point
# --------------------------------------------------------------------------


def complete_chat_detailed(
    task: str,
    client: Any,
    *,
    messages: list,
    max_output_tokens: int,
    temperature: float,
    max_retries: int = DEFAULT_MAX_RETRIES,
    job_budget: Optional[JobBudget] = None,
    today: Optional[date] = None,
    **extra: Any,
) -> ChatResult:
    """Send one Chat Completions request for ``task`` under every bound above.

    ``extra`` carries the call site's remaining arguments (``response_format``).
    Raises ``UnsupportedModelError`` for an unregistered task or unpriced model,
    ``LLMCallRefused`` when a bound refuses, and the SDK's error after the last
    retry.
    """
    request = chat_request_kwargs(task, max_output_tokens=max_output_tokens, temperature=temperature, today=today)
    model = request["model"]
    reservation = _to_micros(cost_upper_bound_usd(model, messages, max_output_tokens))
    cap = daily_budget_micros()
    day = _utc_day(today)
    retries = max(0, min(int(max_retries), MAX_RETRIES_CEILING))
    status_errors, transport_errors = _openai_errors()

    slots = _get_slots()
    if not slots.acquire(timeout=CONCURRENCY_WAIT_S):
        raise LLMConcurrencyExhausted(f"LLM task {task}: no free slot in {CONCURRENCY_WAIT_S}s")
    try:
        attempt = 0
        while True:
            hold = _reserve(task, reservation, cap, job_budget, day)
            try:
                response = client.chat.completions.create(**request, messages=messages, **extra)
            except status_errors as exc:
                hold.settle(0)  # the provider answered with an error: nothing was generated
                status = getattr(exc, "status_code", None)
                if attempt >= retries or not (status in _RETRYABLE_STATUS or (status or 0) >= 500):
                    raise
                delay = _retry_delay(attempt, exc)
            except transport_errors as exc:
                hold.keep()  # timed out or dropped: the provider may have finished it
                if attempt >= retries:
                    raise
                delay = _retry_delay(attempt, exc)
            except BaseException:
                hold.keep()  # cancelled, killed or failed locally: cost unknown
                raise
            else:
                cost = estimate_cost_usd(model, getattr(response, "usage", None))
                if cost is None:
                    hold.keep()
                else:
                    hold.settle(_to_micros(cost))
                return ChatResult(response=response, model=model, cost_usd=cost)
            logger.info("LLM task %s attempt %d failed; retrying in %.2fs", task, attempt + 1, delay)
            _sleep(delay)
            attempt += 1
    finally:
        slots.release()


def complete_chat(task: str, client: Any, **kwargs: Any) -> Any:
    """``complete_chat_detailed`` returning only the SDK response."""
    return complete_chat_detailed(task, client, **kwargs).response


__all__ = [
    "ChatResult",
    "JobBudget",
    "LLMBudgetExceeded",
    "LLMBudgetUnavailable",
    "LLMCallRefused",
    "LLMConcurrencyExhausted",
    "MemoryBudgetLedger",
    "RedisBudgetLedger",
    "complete_chat",
    "complete_chat_detailed",
    "set_ledger",
]
