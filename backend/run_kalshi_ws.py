"""Entry point for WebSocket consumer dyno.

Runs Kalshi + Polymarket WebSocket consumers concurrently on a single dyno.
Both maintain persistent connections for real-time price updates and
settlement events.

WS_VENUE_PROCESSES=1 isolates the venues in two fresh Python processes within
the SAME dyno. Unset it to use the existing shared-loop path. The parent owns
no app clients and never respawns a child; Heroku retains dyno restart ownership.

Usage (Procfile):
    worker-ws: python3 run_kalshi_ws.py
"""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from contextlib import contextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ws_runner")

#: Q504-b — how often the dyno says it is alive REGARDLESS of what either
#: consumer is doing. Two minutes: short enough that a wedge is named on the
#: same visit that noticed the symptom, long enough that the line cannot itself
#: become the flood it exists to survive.
HEARTBEAT_SECONDS = int(os.getenv("WS_HEARTBEAT_SECONDS", "120"))

#: The arms the heartbeat asserts about. Named as a constant, not derived from
#: whatever happens to have reported, so an arm that dies before its first
#: report is printed as NEVER REPORTED instead of quietly vanishing from the
#: line (gotcha #53 — an absence is not a response shape).
HEARTBEAT_ARMS = ("kalshi", "polymarket")

#: #10090 — allow existing final drains/session disposal to finish before the
#: platform's shutdown deadline. Escalation is ONLY for shutdown, not a watchdog.
SHUTDOWN_SECONDS = 25.0

#: #10090 — the heartbeat wakes this often to sample this process's loop.
#: Late wakes describe scheduling delay; they do not time an individual stamp.
LOOP_SAMPLE_SECONDS = 0.25


class LoopLoad:
    """#10090 — CPU and scheduling lag in this process since the last line.

    `cpu` is this process's CPU seconds over wall seconds (threads included, so
    it can pass 1.00). `lag` is how late a `LOOP_SAMPLE_SECONDS` sleep woke
    (p50 / p95 / max); it is a scheduling sample, not per-stamp latency. In
    venue mode each line describes that venue's process, not the whole dyno.
    """

    def __init__(self, clock=time.monotonic, cpu=time.process_time):
        self._clock, self._cpu = clock, cpu
        self._reset()

    def _reset(self):
        self._wall0, self._cpu0, self._lags = self._clock(), self._cpu(), []

    def sample(self, lag):
        self._lags.append(max(0.0, lag))

    def line(self):
        wall = self._clock() - self._wall0
        cpu = (self._cpu() - self._cpu0) / wall if wall > 0 else 0.0
        lags = sorted(self._lags)
        n = len(lags)
        self._reset()
        if not n:
            return f"loop cpu={cpu:.2f} lag n=0"
        p50, p95 = lags[n // 2], lags[min(n - 1, int(n * 0.95))]
        return (
            f"loop cpu={cpu:.2f} lag p50={p50 * 1000:.0f}ms "
            f"p95={p95 * 1000:.0f}ms max={lags[-1] * 1000:.0f}ms n={n}"
        )


async def run_kalshi():
    from app.tasks.kalshi_ws import _run_kalshi_ws_consumer

    while True:
        try:
            result = await _run_kalshi_ws_consumer()
            logger.info("Kalshi WS returned: %s", result)
            if result and result.get("status") == "skipped":
                logger.warning("Kalshi WS: missing credentials, will retry in 5m")
                await asyncio.sleep(300)
                continue
            if result and result.get("status") == "no_markets":
                logger.info("Kalshi WS: no markets, retrying in 60s")
                await asyncio.sleep(60)
                continue
            if result and result.get("status") == "resubscribe":
                # Q460: a planned recycle so the slate can be re-read, not a
                # fault. Sleeping the error backoff here would blind the fast
                # lane for ten seconds out of every ten minutes for no reason.
                logger.info("Kalshi WS: refreshing subscription list")
                continue
        except Exception as e:
            logger.exception("Kalshi WS crashed: %s", e)
        await asyncio.sleep(10)


async def run_polymarket():
    from app.tasks.polymarket_ws import _run_polymarket_ws_consumer

    while True:
        try:
            result = await _run_polymarket_ws_consumer()
            logger.info("Polymarket WS returned: %s", result)
            if result and result.get("status") in ("no_markets", "no_asset_ids"):
                logger.info("Polymarket WS: no markets, retrying in 60s")
                await asyncio.sleep(60)
                continue
            if result and result.get("status") == "resubscribe":
                # Planned recycle (Q460), same as the Kalshi arm above.
                logger.info("Polymarket WS: refreshing subscription list")
                continue
        except Exception as e:
            logger.exception("Polymarket WS crashed: %s", e)
        await asyncio.sleep(10)


async def run_kalshi_shadow():
    """#836 Batch 2 (SHADOW): widened lifecycle-only grader, Redis-shadow only.
    Deploy-dark — does nothing until `bainluck:ws_shadow_enabled` is turned on;
    never writes is_winner (records verdicts to Redis for the comparison)."""
    from app.tasks.kalshi_ws import _run_kalshi_ws_shadow_consumer

    while True:
        try:
            result = await _run_kalshi_ws_shadow_consumer()
            if result and result.get("status") in ("shadow_disabled", "skipped"):
                await asyncio.sleep(300)  # flag off / no creds — re-check in 5m
                continue
        except Exception as e:
            logger.exception("Kalshi WS SHADOW crashed: %s", e)
        await asyncio.sleep(30)


async def run_polymarket_shadow():
    """#837 fast-follow (SHADOW): widened resolution-only grader, Redis-shadow
    only. Deploy-dark — does nothing until `bainluck:ws_shadow_enabled` is
    turned on; never writes is_winner (records verdicts to Redis for the
    source-agnostic comparison)."""
    from app.tasks.polymarket_ws import _run_polymarket_ws_shadow_consumer

    while True:
        try:
            result = await _run_polymarket_ws_shadow_consumer()
            if result and result.get("status") in ("shadow_disabled", "skipped"):
                await asyncio.sleep(300)  # flag off — re-check in 5m
                continue
        except Exception as e:
            logger.exception("Polymarket WS SHADOW crashed: %s", e)
        await asyncio.sleep(30)


async def heartbeat(arms=HEARTBEAT_ARMS):
    """Q504-b — one line per `HEARTBEAT_SECONDS`, from OUTSIDE both consumers.

    THE FAILURE THIS CLOSES. On 2026-09-01 `worker-ws` was reported dead: two
    attended log pulls showed no `app[worker-ws.1]` lines at all while
    `worker-realtime` flooded the shared buffer, and the socket was written off
    as wedged. A per-dyno pull proved the opposite — connected, 23,456 tickers,
    10,098 price updates in ten minutes. Hours of a P1 evening went to
    establishing which of "silent because dead" and "silent because evicted" was
    true, and the dyno had no way to answer.

    Every other log line on this process is emitted by an arm, which means the
    one state that most needs reporting — an arm stuck in a pre-subscribe await
    — is the one state that cannot report itself. This coroutine is a sibling of
    the arms under the same `gather`, so it keeps printing while they hang, and
    it prints an AGE per arm so a frozen-but-plausible phase is distinguishable
    from a live one.

    It never touches the sockets, never awaits anything but its own sleep, and
    swallows everything: a heartbeat that can take down the stream it watches is
    worse than no heartbeat (gotcha #42).
    """
    from app.tasks.ws_liveness import render

    started = time.monotonic()
    load = LoopLoad()
    while True:
        # #10090: the same interval, slept in short steps so each wake can be
        # timed. Always at least one await, so an interval of 0 still yields.
        deadline = time.monotonic() + HEARTBEAT_SECONDS
        while True:
            step = min(LOOP_SAMPLE_SECONDS, max(0.0, deadline - time.monotonic()))
            before = time.monotonic()
            await asyncio.sleep(step)
            load.sample(time.monotonic() - before - step)
            if time.monotonic() >= deadline:
                break
        try:
            now = time.monotonic()
            logger.info(
                "%s uptime=%ds %s",
                render(arms, now), int(now - started), load.line(),
            )
        except Exception:
            logger.exception("worker-ws heartbeat failed")


async def main():
    logger.info("Starting WebSocket consumers (Kalshi + Polymarket + shadow)")
    await asyncio.gather(
        run_kalshi(),
        run_polymarket(),
        run_kalshi_shadow(),
        run_polymarket_shadow(),
        heartbeat(),
    )


@contextmanager
def _stop_signals(stop):
    """Repeated TERM/INT requests never recancel a consumer's final drain."""
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    try:
        yield
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


async def run_venue(venue):
    """One production arm, its deploy-dark shadow, and its local heartbeat.

    Consumer retries and epoch handoff stay inside this process. Cancellation
    joins the existing final drain before the consumer disposes its engine.
    No engine, Redis socket or in-memory handoff is inherited from the parent.
    """
    if venue == "kalshi":
        arms = (run_kalshi, run_kalshi_shadow)
    elif venue == "polymarket":
        arms = (run_polymarket, run_polymarket_shadow)
    else:
        raise ValueError(f"unknown venue: {venue}")

    stop = asyncio.Event()
    with _stop_signals(stop):
        logger.info("Starting %s WebSocket process pid=%d", venue, os.getpid())
        tasks = [asyncio.create_task(arm()) for arm in arms]
        tasks.append(asyncio.create_task(heartbeat((venue,))))
        stopped = asyncio.create_task(stop.wait())
        try:
            done, _ = await asyncio.wait(
                [*tasks, stopped], return_when=asyncio.FIRST_COMPLETED,
            )
            if stopped not in done:
                for task in done:
                    task.result()  # propagate a failed arm; never silently lose it
                raise RuntimeError(f"{venue} WebSocket task returned unexpectedly")
        finally:
            # Signal handlers only set the event, so a second TERM while this
            # gather awaits a drain cannot cancel the drain again.
            for task in [*tasks, stopped]:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, stopped, return_exceptions=True)


async def _join_children(children, waiters):
    """Stop once, join, and escalate only when the shutdown bound expires."""
    for child in children:
        if child.returncode is None:
            try:
                child.terminate()
            except ProcessLookupError:
                pass  # exited between returncode inspection and the signal
    if not waiters:
        return
    _, pending = await asyncio.wait(waiters, timeout=SHUTDOWN_SECONDS)
    if pending:
        logger.error("WebSocket child drain exceeded %.0fs; killing", SHUTDOWN_SECONDS)
        for child, waiter in zip(children, waiters):
            if waiter in pending and child.returncode is None:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
    await asyncio.gather(*waiters)


async def supervise_venues():
    """Exactly two exec children; any unexpected exit stops the whole dyno.

    The lightweight parent imports only stdlib. No respawn loop means a dead
    child's process-local stamp handoff is never mistaken for a normal epoch,
    and a replacement can never overlap a still-draining production copy.
    """
    stop = asyncio.Event()
    children, waiters = [], []
    with _stop_signals(stop):
        stopped = asyncio.create_task(stop.wait())
        try:
            for venue in HEARTBEAT_ARMS:
                child = await asyncio.create_subprocess_exec(
                    sys.executable, os.path.abspath(__file__), "--venue", venue,
                )
                children.append(child)
                waiters.append(asyncio.create_task(child.wait()))
                logger.info("Started %s child pid=%d", venue, child.pid)
            done, _ = await asyncio.wait(
                [*waiters, stopped], return_when=asyncio.FIRST_COMPLETED,
            )
            if stopped in done:
                return 0
            logger.error("WebSocket child exited unexpectedly; stopping sibling")
            return 1
        finally:
            await _join_children(children, waiters)
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)


async def entrypoint(venue=None):
    if venue is not None:
        await run_venue(venue)
        return 0
    if os.getenv("WS_VENUE_PROCESSES") == "1":
        return await supervise_venues()
    await main()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venue", choices=HEARTBEAT_ARMS)
    sys.exit(asyncio.run(entrypoint(parser.parse_args().venue)))
