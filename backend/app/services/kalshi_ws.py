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

from app.utils.kalshi_orderbook import KalshiOrderBook
from app.utils import ws_json

logger = logging.getLogger(__name__)

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_SIGN_PATH = "/trade-api/ws/v2"


async def _cooperative_messages(socket):
    """Give ready probability writers a turn during an already-buffered burst.

    A cached receive and an uncontended inline callback need not suspend.
    Yield between processed frames, including ignored/invalid inputs, before
    consuming the next one. Dispatch retains its existing settlement ordering.
    """
    processed = 0
    async for raw in socket:
        yield raw
        raw = None
        processed += 1
        if processed >= 32:
            processed = 0
            await asyncio.sleep(0)


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

    async def submit(self, callback, payload, label, *, lifecycle=False, prepare=None,
                     discard_if_delayed=False):
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
            if discard_if_delayed:
                return
            await self.drain()
            await self._call(callback, payload, label, prepare)
            return
        key = parts[0]
        previous = self._tails.get(key)
        if discard_if_delayed and (previous is not None or self._closing):
            return  # optional observations never wait behind settlement work
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


#: #10090 — the order book channel: a snapshot, then signed quantity deltas
#: sequenced per subscription (``sid``/``seq``).
BOOK_CHANNEL = "orderbook_delta"


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
        self.on_book_observation: Optional[Callable] = None
        self.on_lifecycle: Optional[Callable] = None
        self.on_lifecycle_prepare: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        # #10702: supplied by the consumer, shared across its existing sockets.
        self.exact_trace = None
        # #10090: set by `retire`. The reader stops at a frame boundary and its
        # accepted callbacks drain; `run` then returns instead of reconnecting.
        self._retiring = False
        self._socket = None
        # #10090: this connection's subscribe commands (id -> channel), the
        # channels Kalshi acknowledged, and the first rejection. Reset at every
        # connect and disconnect, so a successor is ready only while its
        # current connection carries every channel it asked for.
        self._subscribe_pending: dict[int, str] = {}
        self._subscribed: set[str] = set()
        self._subscribe_rejected: Optional[dict] = None
        self._connected_at: Optional[float] = None
        # #10090 direct book: the tickers whose order book this client should
        # carry (set by the owner, `set_book_tickers`), and this connection's
        # book state. Optional: a rejected or pending book never blocks
        # readiness, and without a healthy book the ticker summary stands.
        self.book_tickers: frozenset[str] = frozenset()
        self._book: Optional[KalshiOrderBook] = None
        self._book_sid: Optional[int] = None
        self._book_pending: Optional[int] = None
        self._book_requested: frozenset[str] = frozenset()
        self._book_commands: dict[int, str] = {}
        # Genuine last-trade price per ticker from this connection's ticker
        # frames, carried on book quotes for the wide-book price policy.
        self._last_trade: dict[str, str] = {}
        self._primary_generation = object()
        self._primary_serial = 0
        self._primary_inputs = {}
        self._book_quotes = 0
        self._book_resnapshots = 0

    def _current_book_quote(self, ticker):
        """Current acknowledged session evidence shared by both proof types."""
        if (
            self._retiring or self._socket is None or not self.is_subscribed
            or ticker not in self.book_tickers or ticker not in self._book_requested
            or self._book is None or self._book_sid is None
            or self._book_pending is not None
            or self._book._owners.get(ticker) != self._book_sid
            or ticker in self._book._awaiting
        ):
            return None
        seed = {"market_ticker": ticker}
        quote = self._book.overlay_ticker(seed)
        if quote is seed:
            return None
        return quote

    def current_book_midpoint(self, ticker):
        """#10090: live sequenced-book evidence, never an observation clock."""
        from decimal import Decimal, InvalidOperation
        quote = self._current_book_quote(ticker)
        if quote is None:
            return None
        try:
            bid = Decimal(quote["yes_bid_dollars"])
            ask = Decimal(quote["yes_ask_dollars"])
            if (bid.is_finite() and ask.is_finite()
                    and 0 < bid <= ask < 1 and ask - bid < Decimal("0.50")):
                return (bid + ask) / 2
        except (KeyError, TypeError, ValueError, InvalidOperation):
            pass
        return None

    def current_book_primary_price(self, ticker):
        """Primary-only proof; an ask/trade fallback never proves a midpoint.

        The healthy current ask independently supports the same longshot cap
        already selected by normal price policy. A cached trade away from that
        ask is not current-price evidence and remains refused. No new clock.
        """
        from decimal import Decimal, InvalidOperation
        from app.tasks.kalshi import _kalshi_yes_probability
        from app.utils.kalshi_empty_book import ASK_ONLY_TRUSTED_MAX
        midpoint = self.current_book_midpoint(ticker)
        if midpoint is not None:
            return midpoint
        quote = self._current_book_quote(ticker)
        if quote is None:
            return None
        try:
            bid = (None if quote["yes_bid_dollars"] is None else
                   Decimal(quote["yes_bid_dollars"]))
            ask = Decimal(quote["yes_ask_dollars"])
            last = self._last_trade.get(ticker)
            trade = None if last is None else Decimal(last)
            if (not ask.is_finite() or not 0 < ask <= Decimal(str(ASK_ONLY_TRUSTED_MAX))
                    or (bid is not None and (not bid.is_finite() or bid != 0))
                    or (trade is not None and not trade.is_finite())):
                return None
            # Preserve missing versus numeric-zero bid exactly as overlay_ticker
            # does. In particular, an empty side without a trade still skips.
            selected = _kalshi_yes_probability(
                None if bid is None else float(bid), float(ask),
                None if trade is None else float(trade),
            )
            return ask if selected is not None and Decimal(str(selected)) == ask else None
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return None

    def _reset_subscription(self):
        self._subscribe_pending = {}
        self._subscribed = set()
        self._subscribe_rejected = None
        self._connected_at = None
        self._book = None
        self._book_sid = None
        self._book_pending = None
        self._book_requested = frozenset()
        self._book_commands = {}
        self._last_trade = {}
        self._primary_generation = object()
        self._primary_inputs = {}

    def _note_subscription_response(self, msg_type, data) -> None:
        """#10090 — record Kalshi's answer to one of this connection's
        subscribe commands (``subscribed`` or ``error`` with its ``id``)."""
        command_id = data.get("id")
        if command_id is not None and command_id == self._book_pending:
            self._book_pending = None
            msg = data.get("msg") or {}
            if msg_type == "subscribed" and isinstance(msg.get("sid"), int):
                self._book_sid = msg["sid"]
            else:
                # Optional: the ticker summary carries on alone.
                self._book = None
                self._book_requested = frozenset()
                logger.warning(
                    "Kalshi WS: order book subscription REJECTED, ticker only: %s",
                    str(msg)[:200],
                )
            return
        action = self._book_commands.pop(command_id, None)
        if action is not None:
            if msg_type == "error":
                # Membership/resync is now uncertain. Discard cached overlays;
                # genuine ticker quotes must keep flowing on this connection.
                self._book = None
                self._book_requested = frozenset()
                logger.warning(
                    "Kalshi WS: order book %s refused: %s",
                    action, str(data.get("msg"))[:200],
                )
            return
        if msg_type not in ("subscribed", "error"):
            return
        channel = self._subscribe_pending.pop(command_id, None)
        if channel is None:
            return
        if msg_type == "subscribed":
            self._subscribed.add(channel)
            return
        if self._subscribe_rejected is None:
            self._subscribe_rejected = {"channel": channel, "msg": data.get("msg")}
        logger.warning(
            "Kalshi WS: subscription to %s REJECTED: %s",
            channel, str(data.get("msg"))[:200],
        )

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
            if self._retiring:
                return
            try:
                headers = _sign_ws_request(self._private_key, self.api_key_id)
                async with websockets.connect(
                    WS_URL,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._socket = ws
                    self._reset_subscription()
                    self._connected_at = time.monotonic()
                    connection = None
                    if self.exact_trace is not None:
                        try:
                            import uuid
                            connection = uuid.uuid4().hex[:12]
                        except Exception:
                            pass
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
                        self._subscribe_pending[cmd["id"]] = channel
                        await ws.send(json.dumps(cmd))
                        if self.exact_trace is not None and connection is not None:
                            try:
                                self.exact_trace.sent(
                                    connection, cmd["id"], channel,
                                    params.get("market_tickers"), subscribe_all,
                                )
                            except Exception:
                                pass
                        logger.info(
                            "Subscription SENT to %s (%s)",
                            channel,
                            (
                                f"{len(market_tickers)} tickers"
                                if market_tickers
                                else "all markets"
                            ),
                        )

                    if self.book_tickers:
                        self._book = KalshiOrderBook()
                        await self._sync_book(ws)

                    async with _KalshiCallbackDispatch() as dispatch:
                        try:
                            async for raw in _cooperative_messages(ws):
                                self._message_count += 1
                                try:
                                    # #10090: the fast parser, same contract.
                                    data = ws_json.loads(raw)
                                except (json.JSONDecodeError, TypeError):
                                    continue
                                finally:
                                    raw = None

                                msg_type = data.get("type")
                                payload = data.get("msg", data)
                                if self.exact_trace is not None and connection is not None:
                                    try:
                                        self.exact_trace.response(connection, data)
                                        if msg_type == "ticker":
                                            self.exact_trace.received(connection, payload)
                                        elif msg_type in (
                                            "orderbook_snapshot", "orderbook_delta",
                                        ):
                                            self.exact_trace.book_received(connection, data)
                                    except Exception:
                                        pass
                                if msg_type in ("subscribed", "error", "ok"):
                                    self._note_subscription_response(msg_type, data)
                                    if msg_type == "subscribed" and self._book is not None:
                                        await self._sync_book(ws)
                                if msg_type in ("orderbook_snapshot", "orderbook_delta"):
                                    await self._handle_book_frame(ws, data, dispatch)
                                elif msg_type == "ticker" and self.on_ticker:
                                    if self._book is not None:
                                        received, payload = (
                                            payload, self._overlay_ticker(payload),
                                        )
                                        if self.exact_trace is not None:
                                            try:
                                                self.exact_trace.derived(
                                                    received, payload,
                                                    "TICKER_BOOK_OVERLAY",
                                                )
                                            except Exception:
                                                pass
                                        received = None
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
                                if self._retiring:
                                    break
                        finally:
                            self._connected = False
                            self._socket = None
                            self._reset_subscription()
                    if self._retiring:
                        return

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
                self._reset_subscription()
                raise

            except Exception as e:
                self._connected = False
                self._socket = None
                self._reset_subscription()
                if self._retiring:
                    # The close `retire` requested, or a transport error after
                    # it: either way a successor owns these tickers now.
                    return
                logger.warning(
                    "Kalshi WS disconnected (%s: %s), reconnecting in %.0fs",
                    type(e).__name__,
                    str(e)[:100],
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    async def set_book_tickers(self, tickers) -> None:
        """#10090 — the tickers whose order book this client carries. Applied
        to the current connection (add/delete on its book subscription) and
        subscribed afresh on every reconnect."""
        tickers = frozenset(t.upper() for t in tickers)
        if tickers == self.book_tickers:
            return
        self.book_tickers = tickers
        socket = self._socket
        if socket is None or not self._connected:
            return
        if self._book is None and tickers and self._book_sid is None:
            self._book = KalshiOrderBook()
        if self._book is not None:
            await self._sync_book(socket)

    async def _book_command(self, ws, action: str, params: dict) -> None:
        cmd = {"id": next(self._cmd_counter), "cmd": "update_subscription",
               "params": {"sids": [self._book_sid], **params, "action": action}}
        self._book_commands[cmd["id"]] = action
        await ws.send(json.dumps(cmd))

    async def _sync_book(self, ws) -> None:
        """Bring this connection's book subscription to ``book_tickers``."""
        if self._book is None or self._book_pending is not None:
            return  # no book, or its subscribe is unanswered: synced on ACK
        desired, requested = self.book_tickers, self._book_requested
        if self._book_sid is None:
            if not desired:
                return
            cmd = {"id": next(self._cmd_counter), "cmd": "subscribe", "params": {
                "channels": [BOOK_CHANNEL], "market_tickers": sorted(desired),
            }}
            self._book_pending = cmd["id"]
            self._book_requested = desired
            await ws.send(json.dumps(cmd))
            logger.info("Order book subscription SENT (%d tickers)", len(desired))
            return
        added, removed = desired - requested, requested - desired
        self._book_requested = desired
        if removed:
            for ticker in removed:
                self._primary_inputs.pop(ticker, None)
            self._book.forget(removed)
            self._last_trade = {
                t: p for t, p in self._last_trade.items() if t not in removed
            }
            await self._book_command(
                ws, "delete_markets", {"market_tickers": sorted(removed)},
            )
        if added:
            await self._book_command(ws, "add_markets", {"market_tickers": sorted(added)})

    async def _handle_book_frame(self, ws, data, dispatch) -> None:
        """#10090 — a changed best quote from this connection's book goes
        through the ordered price callback, before any ticker summary."""
        if self._book is None:
            return
        payload = data.get("msg")
        ticker = payload.get("market_ticker") if isinstance(payload, dict) else None
        ticker = ticker.upper() if isinstance(ticker, str) else ""
        sid, seq = data.get("sid"), data.get("seq")
        previous = self._book._sequences.get(sid) if type(sid) is int else None
        sequence_gap = (
            type(sid) is int and sid >= 0 and type(seq) is int and seq >= 0
            and previous is not None and seq > previous + 1
        )
        quote = self._book.apply(data, observe_unchanged=self.on_book_observation is not None)
        # Normal frames inspect only their ticker. A real SID gap invalidates
        # its affected books; do wider work only then, never for the full slate
        # on every delta. Include this ticker even if this very frame rebuilt
        # its snapshot and removed it from _awaiting.
        if sequence_gap:
            for invalidated in self._book._awaiting:
                self._primary_inputs.pop(invalidated, None)
        if (sequence_gap or ticker in self._book._awaiting
                or ticker not in self._book._owners
                or ticker not in self.book_tickers):
            self._primary_inputs.pop(ticker, None)
        if data.get("type") == "orderbook_snapshot":
            self._book_commands.pop(data.get("id"), None)
        if ticker not in self.book_tickers:
            # Still consume the SID sequence: later wanted deltas share it.
            # A queued snapshot after removal must not recreate an overlay.
            self._book.forget([ticker])
            quote = None
        await self._request_resnapshots(ws)
        if self.exact_trace is not None:
            try:
                self.exact_trace.derived(data, quote, "ORDERBOOK_DERIVED")
            except Exception:
                pass
        if quote is not None and quote.pop("_observation_only", False):
            if self.on_book_observation is not None:
                # No last trade or primary-input identity is minted, and the
                # ordinary price callback/write path never sees this packet.
                await dispatch.submit(self.on_book_observation, quote, "Book observation",
                                      discard_if_delayed=True)
            return
        if quote is None or not self.on_ticker:
            return
        last = self._last_trade.get(quote["market_ticker"])
        if last is not None:
            quote["price_dollars"] = last  # the genuine last trade, never local
        quote = self._with_primary_identity(quote)
        if data.get("type") == "orderbook_snapshot":
            # #10090: the consumer's repeat skip never skips a snapshot.
            quote["_book_snapshot"] = True
        self._book_quotes += 1
        await dispatch.submit(self.on_ticker, quote, "Ticker")

    def _overlay_ticker(self, payload: dict) -> dict:
        """A delayed ticker summary never replaces a newer healthy book; its
        genuine trade fields stand."""
        ticker = (payload.get("market_ticker") or "").upper()
        if payload.get("price_dollars") is not None:
            self._last_trade[ticker] = payload["price_dollars"]
        delivered = self._book.overlay_ticker(payload)
        return self._with_primary_identity(delivered, original_ticker=True)

    @staticmethod
    def _primary_policy_price(payload):
        import math
        from app.tasks.kalshi import _kalshi_yes_probability
        try:
            fields = [None if payload.get(key) in (None, "") else float(payload[key])
                      for key in ("yes_bid_dollars", "yes_ask_dollars", "price_dollars")]
            if any(v is not None and not math.isfinite(v) for v in fields):
                return None
            value = _kalshi_yes_probability(*fields)
            return value if value is not None and 0 < value < 1 else None
        except (TypeError, ValueError):
            return None

    def current_primary_input(self, ticker):
        quote = self._current_book_quote(ticker)
        entry = self._primary_inputs.get(ticker)
        if quote is None or entry is None:
            return None
        # A changed live book may refute the accepted quote. The unchanged
        # policy decides again at proof time; no execution clock is inferred.
        quote = {**quote, "price_dollars": self._last_trade.get(ticker)}
        return entry if self._primary_policy_price(quote) == entry[1] else None

    def _with_primary_identity(self, quote, *, original_ticker=False):
        # This is accepted QUOTE evidence, not execution order or a trade clock.
        # A genuine book callback may select a cached original trade under the
        # ordinary policy. Bind that changed selection to its own observation;
        # never wait for an unrelated new ticker to establish the same price.
        # Keep the callback object: ExactKalshiTrace keys its receipt by id.
        result = quote
        result.pop("_primary_quote_identity", None)
        result.pop("_primary_quote_probability", None)
        ticker = quote.get("market_ticker")
        value = self._primary_policy_price(quote)
        current = self._current_book_quote(ticker)
        # Only the bundled Challenger branch consumes this fallback. Other
        # markets and independently proved midpoint/ask inputs retain ordinary
        # SQL observation cadence instead of forcing writes for new identities.
        supported = (isinstance(ticker, str)
                     and ticker.startswith("KXATPCHALLENGERMATCH-")
                     and len(ticker.split("-")) == 3)
        selected_now = (None if current is None else self._primary_policy_price(
            {**current, "price_dollars": self._last_trade.get(ticker)}
        ))
        proof = self.current_book_primary_price(ticker) if supported else None
        # A valid tight midpoint already proves the normal-policy selection.
        # Do not turn binary-float arithmetic (e.g. .81/.83) into forced debt.
        independent = supported and (
            self.current_book_midpoint(ticker) is not None
            or (proof is not None and value is not None and float(proof) == value)
        )
        if (not supported or current is None or value is None
                or selected_now != value or independent):
            self._primary_inputs.pop(ticker, None)
            return result
        entry = self._primary_inputs.get(ticker)
        if original_ticker or entry is None or entry[1] != value:
            self._primary_serial += 1
            entry = ((self._primary_generation, self._primary_serial,
                      "ticker" if original_ticker else "book"), value)
            self._primary_inputs[ticker] = entry
        result.update(_primary_quote_identity=entry[0], _primary_quote_probability=entry[1])
        return result

    async def _request_resnapshots(self, ws) -> None:
        """A gapped, malformed or crossed book asks for a fresh snapshot; until
        it arrives the book is gone and the ticker summary stands."""
        for sid, tickers in self._book.take_resnapshot_requests().items():
            tickers = [t for t in tickers if t in self._book_requested]
            if not tickers:
                continue
            self._book_resnapshots += 1
            cmd = {"id": next(self._cmd_counter), "cmd": "update_subscription",
                   "params": {"sids": [sid], "market_tickers": tickers,
                              "action": "get_snapshot"}}
            self._book_commands[cmd["id"]] = "get_snapshot"
            await ws.send(json.dumps(cmd))

    async def retire(self):
        """#10090 — stop this client without losing input it already accepted.

        Cancelling `run` would cancel its pending lifecycle callbacks. Here the
        reader stops at its next frame boundary (or when the closed socket ends
        its iteration), the dispatch drains every accepted callback, and `run`
        returns. Frames still unread on the closed socket are not input; the
        caller retires a client only once another connection carries its
        tickers, or once none of them is in scope.
        """
        self._retiring = True
        socket = self._socket
        close = getattr(socket, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                logger.debug("Kalshi WS: close during retire failed", exc_info=True)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_subscribed(self) -> bool:
        """#10090 — connected, every channel sent on this connection
        acknowledged, and none rejected. ``is_connected`` turns true before the
        subscribe commands are even sent, so it cannot say a successor carries
        its tickers."""
        return (
            self._connected and self._subscribe_rejected is None
            and not self._subscribe_pending and bool(self._subscribed)
        )

    def subscription_failed(self, ack_deadline_s: float) -> bool:
        """#10090 — True when this connection's subscription was rejected, or
        it has been connected ``ack_deadline_s`` without every acknowledgement:
        a socket that may be silent, which only a rebuild repairs."""
        if not self._connected:
            return False
        if self._subscribe_rejected is not None:
            return True
        return (
            not self.is_subscribed and self._connected_at is not None
            and time.monotonic() - self._connected_at >= ack_deadline_s
        )

    @property
    def stats(self) -> dict:
        return {
            "connected": self._connected,
            "messages": self._message_count,
            "reconnects": self._reconnect_count,
            "book_quotes": self._book_quotes,
            "book_resnapshots": self._book_resnapshots,
        }
