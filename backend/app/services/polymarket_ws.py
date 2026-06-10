"""Polymarket WebSocket consumer for real-time prices and resolution events.

Connects to Polymarket's CLOB WebSocket (no auth required), subscribes to:
  - best_bid_ask: live price updates
  - last_trade_price: trade executions
  - market_resolved: settlement push (winning outcome)

Requires custom_feature_enabled=true for best_bid_ask and market_resolved.
PING heartbeat every 8 seconds to keep connection alive.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PolymarketWebSocket:
    """Polymarket CLOB WebSocket consumer with auto-reconnect.

    Usage:
        ws = PolymarketWebSocket()
        ws.on_price = my_price_handler
        ws.on_resolved = my_resolution_handler
        await ws.run(asset_ids=["token1", "token2"])
    """

    def __init__(self):
        self._connected = False
        self._message_count = 0
        self._reconnect_count = 0

        self.on_price: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_resolved: Optional[Callable] = None
        self.on_new_market: Optional[Callable] = None

    async def run(self, asset_ids: Optional[list[str]] = None):
        """Connect and stream messages forever with auto-reconnect."""
        import websockets

        backoff = 1.0
        max_backoff = 60.0

        while True:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    close_timeout=5,
                ) as ws:
                    self._connected = True
                    if self._reconnect_count > 0:
                        logger.info(
                            "Polymarket WS reconnected (attempt %d)",
                            self._reconnect_count,
                        )
                    else:
                        logger.info("Polymarket WS connected")
                    self._reconnect_count += 1
                    backoff = 1.0

                    sub: dict[str, Any] = {
                        "type": "market",
                        "custom_feature_enabled": True,
                    }
                    if asset_ids:
                        sub["assets_ids"] = asset_ids
                    await ws.send(json.dumps(sub))
                    logger.info(
                        "Polymarket WS subscribed (%s)",
                        f"{len(asset_ids)} assets" if asset_ids else "all",
                    )

                    # Heartbeat task
                    async def heartbeat():
                        while True:
                            await asyncio.sleep(8)
                            try:
                                await ws.send("PING")
                            except Exception:
                                break

                    hb = asyncio.create_task(heartbeat())

                    try:
                        async for raw in ws:
                            if raw == "PONG":
                                continue
                            self._message_count += 1

                            try:
                                data = json.loads(raw)
                            except (json.JSONDecodeError, TypeError):
                                continue

                            if isinstance(data, list):
                                # book snapshot — skip for now
                                continue

                            event_type = data.get("event_type", "")

                            if event_type == "best_bid_ask" and self.on_price:
                                try:
                                    result = self.on_price(data)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception:
                                    logger.exception("Polymarket price handler error")

                            elif event_type == "last_trade_price" and self.on_trade:
                                try:
                                    result = self.on_trade(data)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception:
                                    logger.exception("Polymarket trade handler error")

                            elif event_type == "market_resolved" and self.on_resolved:
                                try:
                                    result = self.on_resolved(data)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception:
                                    logger.exception("Polymarket resolution handler error")

                            elif event_type == "new_market" and self.on_new_market:
                                try:
                                    result = self.on_new_market(data)
                                    if asyncio.iscoroutine(result):
                                        await result
                                except Exception:
                                    logger.exception("Polymarket new_market handler error")

                    finally:
                        hb.cancel()

            except asyncio.CancelledError:
                logger.info("Polymarket WS cancelled, shutting down")
                self._connected = False
                return

            except Exception as e:
                self._connected = False
                logger.warning(
                    "Polymarket WS disconnected (%s: %s), reconnecting in %.0fs",
                    type(e).__name__,
                    str(e)[:100],
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def stats(self) -> dict:
        return {
            "connected": self._connected,
            "messages": self._message_count,
            "reconnects": self._reconnect_count,
        }
