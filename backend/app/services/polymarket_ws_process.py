"""#10090 — the open-contract CLOB sockets received and decoded in a child.

The open-contract client holds ~150 sockets. Each frame they carry — TLS,
inflate, websocket framing, a JSON decode of full-depth ``book`` and
``price_change`` payloads the consumer never reads past coverage — is paid on
the Polymarket consumer's own loop, ahead of the stamps and publication that
loop owns. This module moves ONLY that receive/decode into a child process.

The child runs the unchanged :class:`PolymarketWebSocket` (shards, subscription
sizing, reconnect, snapshots) and forwards just the frames that client would
have handed to ``on_price`` / ``on_trade``, verbatim and in the order it would
have called them. The parent (:class:`PolymarketOpenReceiverProcess`) is a
drop-in for the client's surface the consumer uses: ``on_price``/``on_trade``,
``run_refreshable``, ``update_asset_ids``, ``stats``, ``is_connected``. Every
price policy, map, buffer, write, stamp and publication stays in the parent.

Bounded both ways: the child awaits the pipe's ``drain`` after every frame, so
a slow parent stalls the child's socket reads exactly as a slow callback stalls
them in-process today (websockets' own ``max_queue`` then the TCP window), and
only the LATEST desired catalog is held for the child. Shutdown is the pipe:
closing the child's stdin (or the parent dying) ends it; it ignores TERM/INT so
a dyno-wide signal cannot cut it off ahead of the parent's final drain.

stdlib only — the child loads this file by path, without the ``app.services``
package (whose ``__init__`` imports the database and LLM stack).
"""

import asyncio
import logging
import os
import pickle
import signal
import struct
import sys
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_HEADER = struct.Struct(">I")

#: A forwarded quote/trade or a stats snapshot is a few KiB at most; anything
#: larger is a broken pipe, not a message.
MAX_FRAME_BYTES = 1 << 20

#: How often the child reports its client's ``stats`` (connection, coverage).
STATS_SECONDS = 5.0

#: Shutdown bound for the child after its stdin closes; it has no drain.
CHILD_EXIT_SECONDS = 5.0

RECEIVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "run_pm_open_receiver.py",
)

PRICE, TRADE, STATS, START, ASSETS = "p", "t", "s", "start", "assets"


def encode_frame(message: Any) -> bytes:
    body = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    if len(body) > MAX_FRAME_BYTES:
        raise ValueError(f"frame of {len(body)} bytes exceeds {MAX_FRAME_BYTES}")
    return _HEADER.pack(len(body)) + body


async def read_frame(reader: asyncio.StreamReader) -> Any:
    """The next message, or ``None`` once the peer has gone (EOF anywhere)."""
    try:
        (size,) = _HEADER.unpack(await reader.readexactly(_HEADER.size))
        if size > MAX_FRAME_BYTES:
            raise ValueError(f"frame of {size} bytes exceeds {MAX_FRAME_BYTES}")
        return pickle.loads(await reader.readexactly(size))
    except asyncio.IncompleteReadError:
        return None


class PolymarketOpenReceiverProcess:
    """The parent side: the open client's surface, fed by the child's pipe."""

    def __init__(
        self,
        *,
        max_concurrent_handshakes: Optional[int] = None,
        max_queue: Optional[int] = None,
        price_book_snapshots: bool = False,
        command: Optional[list[str]] = None,
    ):
        self._max_concurrent_handshakes = max_concurrent_handshakes
        self._max_queue = max_queue
        self._price_book_snapshots = price_book_snapshots
        self._command = command or [sys.executable, RECEIVER_SCRIPT]
        self._stats: dict = {}
        self._wanted: Optional[tuple[list[str], bool]] = None
        self._wake: Optional[asyncio.Event] = None
        self.on_price: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def is_connected(self) -> bool:
        return bool(self._stats.get("connected"))

    def update_asset_ids(
        self,
        asset_ids: list[str],
        *,
        price_book_snapshots: Optional[bool] = None,
    ) -> None:
        """Replace the desired catalog; an unsent older one is superseded."""
        if self._wake is None:
            raise RuntimeError("Polymarket refreshable client is not running")
        if price_book_snapshots is not None:
            self._price_book_snapshots = price_book_snapshots
        self._wanted = (list(dict.fromkeys(asset_ids)), self._price_book_snapshots)
        self._wake.set()

    async def run_refreshable(
        self,
        asset_ids: list[str],
        *,
        price_book_snapshots: Optional[bool] = None,
    ):
        """Run one child until cancelled; its exit is this call's failure."""
        if self._wake is not None:
            raise RuntimeError("Polymarket refreshable client is already running")
        if price_book_snapshots is not None:
            self._price_book_snapshots = price_book_snapshots
        self._wake = asyncio.Event()
        self._wanted = None
        child = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        logger.info("Polymarket open receiver started pid=%d", child.pid)
        sender = None
        try:
            child.stdin.write(encode_frame((START, {
                "asset_ids": list(dict.fromkeys(asset_ids)),
                "price_book_snapshots": self._price_book_snapshots,
                "max_concurrent_handshakes": self._max_concurrent_handshakes,
                "max_queue": self._max_queue,
            })))
            await child.stdin.drain()
            sender = asyncio.create_task(self._send_catalogs(child.stdin))
            while True:
                message = await read_frame(child.stdout)
                if message is None:
                    raise RuntimeError(
                        f"Polymarket open receiver exited (pid={child.pid})"
                    )
                kind, body = message
                message = None
                if kind == STATS:
                    self._stats = body
                    continue
                handler = self.on_price if kind == PRICE else (
                    self.on_trade if kind == TRADE else None
                )
                if handler is not None:
                    try:
                        result = handler(body)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception(
                            "Polymarket %s handler error",
                            "price" if kind == PRICE else "trade",
                        )
                body = result = None
                await asyncio.sleep(0)
        finally:
            self._wake = None
            self._stats = {**self._stats, "connected": False, "shards_connected": 0}
            if sender is not None:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            await _stop_child(child)

    async def _send_catalogs(self, stdin: asyncio.StreamWriter) -> None:
        wake = self._wake
        while True:
            await wake.wait()
            wake.clear()
            wanted, self._wanted = self._wanted, None
            if wanted is None:
                continue
            ids, snapshots = wanted
            stdin.write(encode_frame((ASSETS, {
                "asset_ids": ids, "price_book_snapshots": snapshots,
            })))
            await stdin.drain()


async def _stop_child(child) -> None:
    """Close the child's stdin, join it, and kill only past the bound."""
    try:
        child.stdin.close()
    except Exception:
        pass
    try:
        await asyncio.wait_for(child.wait(), CHILD_EXIT_SECONDS)
    except asyncio.TimeoutError:
        logger.error("Polymarket open receiver ignored stdin close; killing")
        _kill(child)
        await child.wait()
    except BaseException:
        # A second cancellation landing on the join still reaps the child.
        _kill(child)
        await child.wait()
        raise


def _kill(child) -> None:
    if child.returncode is None:
        try:
            child.kill()
        except ProcessLookupError:
            pass


async def serve_receiver(client_cls, *, read_fd: int = 0, write_fd: int = 1) -> int:
    """The child: one client, forwarding its prices/trades up the pipe.

    Returns 0 when the parent closes the pipe, 1 when the client fails.
    """
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, signal.SIG_IGN)
    loop = asyncio.get_running_loop()
    # Anything that prints to stdout must not corrupt the frame stream.
    out = os.dup(write_fd)
    os.dup2(2, write_fd)
    reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES)
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), os.fdopen(read_fd, "rb", 0),
    )
    transport, protocol = await loop.connect_write_pipe(
        asyncio.streams.FlowControlMixin, os.fdopen(out, "wb", 0),
    )
    writer = asyncio.StreamWriter(transport, protocol, None, loop)

    start = await read_frame(reader)
    if start is None:
        return 0
    _, config = start
    client = client_cls(
        max_concurrent_handshakes=config["max_concurrent_handshakes"],
        max_queue=config["max_queue"],
        price_book_snapshots=config["price_book_snapshots"],
    )

    async def forward(kind, message):
        writer.write(encode_frame((kind, message)))
        await writer.drain()

    client.on_price = lambda message: forward(PRICE, message)
    client.on_trade = lambda message: forward(TRADE, message)

    async def report():
        while True:
            await forward(STATS, client.stats)
            await asyncio.sleep(STATS_SECONDS)

    async def control():
        # Started after `run_refreshable` owns the refresh event.
        await asyncio.sleep(0)
        while True:
            message = await read_frame(reader)
            if message is None:
                return
            _, body = message
            client.update_asset_ids(
                body["asset_ids"], price_book_snapshots=body["price_book_snapshots"],
            )

    run = asyncio.create_task(client.run_refreshable(
        config["asset_ids"], price_book_snapshots=config["price_book_snapshots"],
    ))
    await asyncio.sleep(0)
    tasks = [run, asyncio.create_task(control()), asyncio.create_task(report())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if run in done:
            logger.error("Polymarket open receiver client ended", exc_info=run.exception())
            return 1
        for task in done:
            if task.exception() is not None:
                logger.error("Polymarket open receiver pipe failed",
                             exc_info=task.exception())
                return 1
        return 0
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        transport.close()
