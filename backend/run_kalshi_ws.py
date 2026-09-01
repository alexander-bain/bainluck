"""Entry point for WebSocket consumer dyno.

Runs Kalshi + Polymarket WebSocket consumers concurrently on a single dyno.
Both maintain persistent connections for real-time price updates and
settlement events.

Usage (Procfile):
    worker-ws: python3 run_kalshi_ws.py
"""

import asyncio
import logging
import os
import sys
import time

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


async def heartbeat():
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
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            now = time.monotonic()
            logger.info(
                "%s uptime=%ds", render(HEARTBEAT_ARMS, now), int(now - started),
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


if __name__ == "__main__":
    asyncio.run(main())
