"""Entry point for Kalshi WebSocket consumer dyno.

Runs as a standalone process (not Celery) — maintains a persistent WebSocket
connection for real-time price updates and settlement events.

Usage (Procfile):
    worker-ws: python3 run_kalshi_ws.py
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("kalshi_ws_runner")


async def main():
    from app.tasks.kalshi_ws import _run_kalshi_ws_consumer

    logger.info("Starting Kalshi WebSocket consumer")
    while True:
        try:
            result = await _run_kalshi_ws_consumer()
            logger.info("Consumer returned: %s", result)
            if result and result.get("status") == "skipped":
                logger.error("Missing credentials, exiting")
                sys.exit(1)
        except Exception as e:
            logger.exception("Consumer crashed: %s", e)

        logger.info("Restarting consumer in 10s...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
