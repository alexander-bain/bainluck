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
import time
from base64 import b64encode
from itertools import count
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_SIGN_PATH = "/trade-api/ws/v2"


# Includes lifecycle callbacks and quotes queued behind their own event's
# settlement. The reader backpressures at this bound; it never drops a frame.
MAX_PENDING_CALLBACKS = 64


class _KalshiCallbackDispatch:
    """Keep one event's settlement ordering without blocking other events.

    The linked-market writer groups siblings by the ticker prefix before the
    last dash, so serializing only the full outcome ticker would be unsafe.
    Unknown identities remain global barriers. Ordinary quotes stay inline
    unless their event already has a pending lifecycle callback.
    """

    def __init__(self):
        self._pending: set[asyncio.Task] = set()
        self._tails: dict[str, asyncio.Task] = {}
        self._owner = None
        self._closing = False

    async def __aenter__(self):
        self._owner = asyncio.current_task()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None and not issubclass(exc_type, Exception):
            await self._cancel()
        else:
            # A transport disconnect doesn't erase accepted lifecycle input.
            # Finish it before reconnecting. Cancellation during this drain
            # still joins every child before the task-level final price flush.
            await self.drain()

    async def _cancel(self):
        self._closing = True
        tasks = list(self._pending)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def drain(self):
        try:
            if self._pending:
                await asyncio.gather(*list(self._pending))
        except BaseException:
            await self._cancel()
            raise

    @staticmethod
    async def _call(callback, payload, label, prepare=None):
        try:
            if prepare is not None:
                callback = await prepare(payload)
            result = callback(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("%s handler error", label)

    async def submit(self, callback, payload, label, *, lifecycle=False, prepare=None):
        # Callbacks without the explicit preparation contract retain their
        # original synchronous ordering. Defer only opted-in, prepared work.
        if lifecycle and prepare is None:
            await self.drain()
            await self._call(callback, payload, label)
            return
        ticker = (
            payload.get("market_ticker") or payload.get("ticker")
            if isinstance(payload, dict)
            else None
        )
        parts = ticker.upper().rsplit("-", 1) if isinstance(ticker, str) else []
        if len(parts) != 2 or not all(parts):
            await self.drain()
            await self._call(callback, payload, label, prepare)
            return
        key = parts[0]
        previous = self._tails.get(key)
        if not lifecycle and previous is None:
            await self._call(callback, payload, label)
            return
        if lifecycle and previous is None:
            # Capture buffer-derived settlement inputs before yielding to a
            # flush or reading another frame. Queued siblings prepare in order.
            try:
                callback = await prepare(payload)
                prepare = None
            except Exception:
                logger.exception("%s preparation handler error", label)
                return

        while len(self._pending) >= MAX_PENDING_CALLBACKS:
            await asyncio.wait(self._pending, return_when=asyncio.FIRST_COMPLETED)

        async def ordered():
            if previous is not None:
                await previous
            await self._call(callback, payload, label, prepare)

        task = asyncio.create_task(ordered())
        self._pending.add(task)
        self._tails[key] = task

        def finished(done):
            # Cancellation raised by a callback used to cancel the reader.
            # Preserve that behavior instead of silently losing its tail.
            if done.cancelled() and not self._closing:
                self._closing = True
                self._owner.cancel()
            self._pending.discard(done)
            if self._tails.get(key) is done:
                del self._tails[key]

        task.add_done_callback(finished)


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
        self.on_lifecycle_prepare: Optional[Callable] = None
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
                            (
                                f"{len(market_tickers)} tickers"
                                if market_tickers
                                else "all markets"
                            ),
                        )

                    async with _KalshiCallbackDispatch() as dispatch:
                        try:
                            async for raw in ws:
                                self._message_count += 1
                                try:
                                    data = json.loads(raw)
                                except (json.JSONDecodeError, TypeError):
                                    continue

                                msg_type = data.get("type")
                                payload = data.get("msg", data)
                                if msg_type == "ticker" and self.on_ticker:
                                    await dispatch.submit(
                                        self.on_ticker, payload, "Ticker"
                                    )
                                elif (
                                    msg_type == "market_lifecycle_v2"
                                    and self.on_lifecycle
                                ):
                                    await dispatch.submit(
                                        self.on_lifecycle,
                                        payload,
                                        "Lifecycle",
                                        lifecycle=True,
                                        prepare=self.on_lifecycle_prepare,
                                    )
                                elif msg_type == "trade" and self.on_trade:
                                    await dispatch.submit(
                                        self.on_trade, payload, "Trade"
                                    )
                        finally:
                            self._connected = False

            except asyncio.CancelledError:
                # Q460 (CERT-491): RE-RAISE, never `return`. The caller bounds
                # this loop with `asyncio.wait_for(..., SUBSCRIPTION_REFRESH_
                # SECONDS)`, and a timeout is delivered as a cancellation of the
                # awaiting task. Swallowing it here let `wait_for` return
                # normally instead of raising `TimeoutError`, so the consumer
                # never set `status="resubscribe"` and `run_kalshi_ws.py` fell
                # through to its 10s error backoff on EVERY planned recycle —
                # ten dead seconds out of every ten minutes on the one stream
                # this queue exists to keep live. Propagating lets
                # `Timeout.__aexit__` convert it to `TimeoutError` as the caller
                # expects, and lets a genuine shutdown cancel actually stop.
                logger.info("Kalshi WS cancelled, shutting down")
                self._connected = False
                raise

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
