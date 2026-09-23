"""`run_llm_off_loop` moves sync LLM work off the event loop, bounded (#4068).

BEHAVIOURAL, not structural: every test here runs a real blocking function
through the runner and observes what the loop and the worker threads actually
do, so each one fails if the runner is replaced by a direct call or if its
bound stops being a bound.

Three of them exist because the first candidate for #4068 passed its own
suite while being wrong (Codex review, 2026-09-23):

* `test_the_bound_survives_cancellation_of_the_awaiters` — the candidate bounded
  with `async with asyncio.Semaphore(4)` around `asyncio.to_thread`. Cancelling
  the awaiters released four permits while four OS threads were still running
  their LLM calls, so a second group started: EIGHT concurrent calls against an
  advertised four.
* `test_the_runner_survives_a_second_event_loop` — that module-global semaphore
  binds the first loop that contends on it and raises on every later one.
* `test_the_bound_is_four` — the candidate's concurrency test read the bound
  back out of the module it was testing, so raising the constant moved the
  assertion with it and it could not fail in the drift direction. FOUR is a
  literal here, written independently of the source.
"""

import asyncio
import threading
import time

import pytest

from app.utils.async_llm import MAX_CONCURRENT_LLM_CALLS, run_llm_off_loop

# The bound, written out independently of the module under test. If you are
# changing the runner's capacity, change it here too and say why in the PR.
PINNED_BOUND = 4


def test_the_bound_is_four():
    """The declared bound is pinned by a literal, not by the source's own value."""
    assert MAX_CONCURRENT_LLM_CALLS == PINNED_BOUND


async def test_result_and_kwargs_pass_through():
    def add(a, b=0):
        return a + b

    assert await run_llm_off_loop(add, 2, b=3) == 5


async def test_an_exception_propagates_to_the_caller():
    """A failed LLM call must still raise where the handler can catch it.

    Every call site sits inside a per-row `try/except` that records the row and
    carries on; swallowing the exception in the runner would turn a failed sweep
    into a silently empty one.
    """

    class Boom(RuntimeError):
        pass

    def explode():
        raise Boom("upstream refused")

    with pytest.raises(Boom, match="upstream refused"):
        await run_llm_off_loop(explode)


async def test_blocking_call_runs_on_a_worker_thread_not_the_loop():
    main_ident = threading.get_ident()
    seen = {}

    def blocking():
        time.sleep(0.2)
        seen["ident"] = threading.get_ident()
        return "done"

    assert await run_llm_off_loop(blocking) == "done"
    assert seen["ident"] != main_ident


async def test_the_loop_stays_responsive_while_blocked_work_runs():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.05)

    def blocking():
        time.sleep(0.3)
        return "done"

    # A direct call would park the loop here and the ticker would starve; the
    # runner must let at least one tick through during the 0.3s block.
    task = asyncio.create_task(ticker())
    try:
        assert await run_llm_off_loop(blocking) == "done"
    finally:
        task.cancel()
    assert ticks >= 1, "event loop was parked by the blocking call"


async def test_concurrent_sweeps_never_exceed_the_bound():
    """PINNED_BOUND, not the module's own number — see the module docstring."""
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}

    def blocking():
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        try:
            time.sleep(0.2)
        finally:
            with lock:
                state["live"] -= 1
        return "done"

    n = PINNED_BOUND * 2
    results = await asyncio.gather(*(run_llm_off_loop(blocking) for _ in range(n)))

    assert results == ["done"] * n
    assert state["peak"] <= PINNED_BOUND
    # And it does overlap — a runner that serialised everything would also
    # satisfy the upper bound while making every sweep n times slower.
    assert state["peak"] >= 2, "runner serialized work it should overlap"


async def test_the_bound_survives_cancellation_of_the_awaiters():
    """THE #4068 REGRESSION: cancelling an awaiter must not free a slot.

    An OS thread cannot be cancelled, so a limiter that lives in the async
    wrapper hands back capacity that the underlying call is still using. The
    bound has to be the resource: an orphaned call keeps its worker until it
    returns, and the next call queues behind it.
    """
    release = threading.Event()
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}

    def blocking():
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        try:
            # Bounded so a regression cannot hang CI; released explicitly below.
            release.wait(timeout=10)
        finally:
            with lock:
                state["live"] -= 1
        return "done"

    first = [
        asyncio.create_task(run_llm_off_loop(blocking)) for _ in range(PINNED_BOUND)
    ]
    try:
        deadline = time.monotonic() + 5
        while state["peak"] < PINNED_BOUND and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        # CONTROL: if the first wave never filled the bound there is no orphaned
        # capacity to free and the assertion below would pass vacuously.
        assert state["peak"] == PINNED_BOUND, (
            f"first wave only reached {state['peak']} of {PINNED_BOUND} concurrent "
            "calls — the test never got into the state it is about to measure"
        )

        for task in first:
            task.cancel()
        await asyncio.gather(*first, return_exceptions=True)
        # The four awaiters are gone. The four threads are still inside
        # `blocking`, still holding what the bound is supposed to be bounding.

        second = [
            asyncio.create_task(run_llm_off_loop(blocking))
            for _ in range(PINNED_BOUND)
        ]
        try:
            # Ample time for an unbounded-after-cancellation runner to start the
            # second wave; a correctly bounded one leaves them queued.
            await asyncio.sleep(0.5)
            peak_after_cancellation = state["peak"]
        finally:
            release.set()
            await asyncio.gather(*second, return_exceptions=True)
    finally:
        release.set()

    assert peak_after_cancellation == PINNED_BOUND, (
        f"cancellation freed the bound: {peak_after_cancellation} concurrent LLM "
        f"calls against a bound of {PINNED_BOUND} — the limiter is in the wrapper, "
        "not in the resource (#4068)"
    )


def test_the_runner_survives_a_second_event_loop():
    """Sync on purpose: it drives two SEPARATE event loops, one after the other.

    The web dyno runs one loop, but the test suite and any `asyncio.run` caller
    do not, and a module-global `asyncio.Semaphore` raises `RuntimeError: ... is
    bound to a different event loop` the second time round. The workload
    CONTENDS (twice the bound) because a loop-affine limiter only reaches for
    the running loop when it actually has to wait — an uncontended call would
    pass under both mechanisms and prove nothing.
    """

    def blocking():
        time.sleep(0.05)
        return "done"

    async def contend():
        n = PINNED_BOUND * 2
        return await asyncio.gather(*(run_llm_off_loop(blocking) for _ in range(n)))

    expected = ["done"] * (PINNED_BOUND * 2)
    assert asyncio.run(contend()) == expected
    assert asyncio.run(contend()) == expected
