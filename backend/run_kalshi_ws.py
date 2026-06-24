"""Entry point for WebSocket consumer dyno.

Runs Kalshi + Polymarket WebSocket consumers concurrently on a single dyno.
Both maintain persistent connections for real-time price updates and
settlement events.

Usage (Procfile):
    worker-ws: python3 run_kalshi_ws.py
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ws_runner")


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


async def main():
    logger.info("Starting WebSocket consumers (Kalshi + Polymarket + shadow)")
    await asyncio.gather(
        run_kalshi(),
        run_polymarket(),
        run_kalshi_shadow(),
    )


if __name__ == "__main__":
    asyncio.run(main())
