"""Kalshi WebSocket consumer for real-time prices and settlement events.

Connects to Kalshi's WebSocket API with RSA-PSS auth, subscribes to:
  - ticker: live price updates (yes_bid, yes_ask, last_price)
  - market_lifecycle_v2: settlement push (market resolved with result)

Runs as a long-lived async loop with auto-reconnect.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from base64 import b64encode
from itertools import count
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_SIGN_PATH = "/trade-api/ws/v2"


def _load_rsa_key():
    """Load RSA private key from env var (PEM string) or file path."""
    from cryptography.hazmat.primitives import serialization

    key_pem = os.getenv("KALSHI_RSA_PRIVATE_KEY")
    key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if key_pem:
        key_bytes = key_pem.encode()
    elif key_path:
        with open(key_path, "rb") as f:
            key_bytes = f.read()
    else:
        raise ValueError(
            "Kalshi RSA key required. Set KALSHI_RSA_PRIVATE_KEY (PEM string) "
            "or KALSHI_PRIVATE_KEY_PATH."
        )

    return serialization.load_pem_private_key(key_bytes, password=None)


def _sign_ws_request(private_key, api_key_id: str) -> dict[str, str]:
    """Create RSA-PSS signed headers for WebSocket handshake."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}GET{WS_SIGN_PATH}"

    signature = private_key.sign(
        message.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": b64encode(signature).decode(),
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }


class KalshiWebSocket:
    """Kalshi WebSocket consumer with auto-reconnect.

    Usage:
        ws = KalshiWebSocket()
        ws.on_ticker = my_ticker_handler
        ws.on_lifecycle = my_lifecycle_handler
        await ws.run(market_tickers=["KXMLBGAME-..."])
    """

    def __init__(self):
        self.api_key_id = os.getenv("KALSHI_API_KEY_ID", "")
        self._private_key = None
        self._cmd_counter = count(1)
        self._connected = False
        self._message_count = 0
        self._reconnect_count = 0

        self.on_ticker: Optional[Callable] = None
        self.on_lifecycle: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None

    def _ensure_key(self):
        if self._private_key is None:
            self._private_key = _load_rsa_key()

    async def run(
        self,
        market_tickers: Optional[list[str]] = None,
        channels: Optional[list[str]] = None,
        subscribe_all: bool = False,
    ):
        """Connect and stream messages forever with auto-reconnect.

        Args:
            market_tickers: List of market tickers to subscribe to.
            channels: Channels to subscribe to. Defaults to ["ticker", "market_lifecycle_v2"].
            subscribe_all: If True, subscribe to all markets (no ticker filter).
        """
        import websockets

        self._ensure_key()

        if channels is None:
            channels = ["ticker", "market_lifecycle_v2"]

        backoff = 1.0
        max_backoff = 60.0

        while True:
            try:
                headers = _sign_ws_request(self._private_key, self.api_key_id)
                async with websockets.connect(
                    WS_URL,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._connected = True
                    if self._reconnect_count > 0:
                        logger.info(
                            "Kalshi WS reconnected (attempt %d)",
                            self._reconnect_count,
                        )
                    else:
                        logger.info("Kalshi WS connected")
                    self._reconnect_count += 1
                    backoff = 1.0

                    # Subscribe
                    for channel in channels:
                        params: dict[str, Any] = {"channels": [channel]}
                        if market_tickers and not subscribe_all:
                            params["market_tickers"] = [
                                t.upper() for t in market_tickers
                            ]
                        cmd = {
                            "id": next(self._cmd_counter),
                            "cmd": "subscribe",
                            "params": params,
                        }
                        await ws.send(json.dumps(cmd))
                        logger.info(
                            "Subscribed to %s (%s)",
                            channel,
                            f"{len(market_tickers)} tickers"
                            if market_tickers
                            else "all markets",
                        )

                    async for raw in ws:
                        self._message_count += 1
                        try:
                            data = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            continue

                        msg_type = data.get("type")
                        payload = data.get("msg", data)

                        if msg_type == "ticker" and self.on_ticker:
                            try:
                                result = self.on_ticker(payload)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                logger.exception("Ticker handler error")

                        elif msg_type == "market_lifecycle_v2" and self.on_lifecycle:
                            try:
                                result = self.on_lifecycle(payload)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                logger.exception("Lifecycle handler error")

                        elif msg_type == "trade" and self.on_trade:
                            try:
                                result = self.on_trade(payload)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                logger.exception("Trade handler error")

            except asyncio.CancelledError:
                logger.info("Kalshi WS cancelled, shutting down")
                self._connected = False
                return

            except Exception as e:
                self._connected = False
                logger.warning(
                    "Kalshi WS disconnected (%s: %s), reconnecting in %.0fs",
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
