"""Run synchronous LLM helpers without parking the event loop (#4068).

`app/services/llm.py` is synchronous end to end, so calling one of its helpers
from an async route handler blocks every concurrent request on that worker
process — not just the one that asked. `WEB_CONCURRENCY=2`, so an operator
running an admin enrichment sweep takes half a dyno's public capacity for the
length of the sweep. The sweeps call these helpers in loops over rows, so the
park is per row, not per request.

THE BOUND IS THE THREAD POOL, NOT A SEMAPHORE. The obvious shape —

    async with _SEMAPHORE:
        return await asyncio.to_thread(func, *args, **kwargs)

— does not hold under cancellation, and a request path is where cancellation
happens (a client disconnects, a timeout fires). Cancel the awaiter and
`to_thread` raises `CancelledError`, `async with` releases the permit on the
way out, and the OS thread underneath carries on running the LLM call because
an OS thread cannot be cancelled. Four orphaned calls plus four fresh permits
is eight concurrent LLM requests against an advertised bound of four; that is
measured, not theorised (Codex, #4068, `CODEX-cancellation.json`).

So the limiter is a dedicated `ThreadPoolExecutor`: the bound is a property of
the resource rather than of a wrapper around it. An orphaned call keeps
occupying its worker until it actually returns, and the next call queues —
which is the correct behaviour. Being loop-agnostic, the executor also has
none of the loop affinity a module-global `asyncio.Semaphore` carries (it
binds the first loop that contends on it and raises on every later one).
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

#: How many LLM requests concurrent sweeps may hold open at once (#1280: never
#: fan out unbounded). Tests pin this literally rather than reading it back
#: from here — a test that asks the source for its own bound cannot fail when
#: the bound drifts.
MAX_CONCURRENT_LLM_CALLS = 4

_LLM_EXECUTOR = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_LLM_CALLS,
    thread_name_prefix="llm-off-loop",
)


async def run_llm_off_loop(
    func: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
) -> T:
    """Await `func(*args, **kwargs)` on a bounded pool of worker threads.

    Evaluate every argument on the caller's side before calling this: anything
    handed over crosses into a thread, so an unloaded ORM attribute would be
    dereferenced off the loop. The call sites pass scalars for that reason.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _LLM_EXECUTOR, functools.partial(func, *args, **kwargs)
    )


__all__ = ["run_llm_off_loop", "MAX_CONCURRENT_LLM_CALLS"]
