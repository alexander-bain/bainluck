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

Bounded both ways, with no unbounded queue: the child awaits the pipe's
``drain`` after every frame, so a slow parent stalls the child's socket reads
exactly as a slow callback stalls them in-process today (websockets' own
``max_queue`` then the TCP window). The pipe's high-water mark is not the whole
of it: every active shard calls back independently, writes its one frame and
only then waits on ``drain``, so the child can hold up to one pending frame per
shard (~150 today; a few KiB each, ``MAX_FRAME_BYTES`` at most) on top of the
transport's high-water mark and the parent's stdout reader buffer. Only the
LATEST desired catalog is held for the child; the catalog is the one large
message, has its own budget (``MAX_CATALOG_FRAME_BYTES``, copies accounted
there), and the frames coming back keep the small one. Shutdown is the pipe:
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

#: The parent's START/ASSETS catalog. Measured 10/09: 76,632 retained open
#: contracts (77-digit ids) pickle to 6,131,659 bytes, ~80 bytes an id, so this
#: admits ~209k ids (2.7x today). Memory at the bound, transient per catalog:
#: parent <= 3x (pickle output, the pipe transport's copy while it drains,
#: one coalesced successor encoding) = 48 MiB; child <= ~4x (stream buffer, the
#: frame bytes, the decoded list ~1.7x) = 64 MiB. Only the latest catalog is
#: ever pending, so that is the whole of it. A larger catalog is refused, not
#: truncated: the run fails (``catalog of N bytes exceeds ...``) and the
#: consumer's existing open-client failure path logs it.
MAX_CATALOG_FRAME_BYTES = 16 << 20

#: How often the child reports its client's ``stats`` (connection, coverage).
STATS_SECONDS = 5.0

#: Shutdown bound for the child after its stdin closes; it has no drain.
CHILD_EXIT_SECONDS = 5.0

RECEIVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "run_pm_open_receiver.py",
)

PRICE, TRADE, STATS, START, ASSETS = "p", "t", "s", "start", "assets"


def encode_frame(message: Any, max_bytes: int = MAX_FRAME_BYTES) -> bytes:
    body = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    if len(body) > max_bytes:
        raise ValueError(f"frame of {len(body)} bytes exceeds {max_bytes}")
    return _HEADER.pack(len(body)) + body


def encode_catalog(kind: str, body: dict) -> bytes:
    return encode_frame((kind, body), MAX_CATALOG_FRAME_BYTES)


async def read_frame(
    reader: asyncio.StreamReader, max_bytes: int = MAX_FRAME_BYTES,
) -> Any:
    """The next message, or ``None`` once the peer has gone (EOF anywhere)."""
    try:
        (size,) = _HEADER.unpack(await reader.readexactly(_HEADER.size))
        if size > max_bytes:
            raise ValueError(f"frame of {size} bytes exceeds {max_bytes}")
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
        """Run one child until cancelled; its exit is this call's failure.

        One ownership boundary covers spawn, START, the catalog sender, the
        frame reader and teardown. The sender and the reader are supervised
        together: whichever stops first fails this call (a catalog over its
        budget, a pipe write/drain error, the child's EOF), so a child can never
        go on serving an old catalog after its updates stopped being delivered.
        Teardown always joins both tasks, closes the child's stdin and reaps it
        (kill past ``CHILD_EXIT_SECONDS``) — including when spawn or START
        failed, and through further cancellations, which are re-raised only
        once the child is gone. Afterwards the proxy is reusable: the consumer
        retries the same object at its next catalog boundary.
        """
        if self._wake is not None:
            raise RuntimeError("Polymarket refreshable client is already running")
        if price_book_snapshots is not None:
            self._price_book_snapshots = price_book_snapshots
        start = encode_catalog(START, {
            "asset_ids": list(dict.fromkeys(asset_ids)),
            "price_book_snapshots": self._price_book_snapshots,
            "max_concurrent_handshakes": self._max_concurrent_handshakes,
            "max_queue": self._max_queue,
        })
        self._wake = asyncio.Event()
        self._wanted = None
        spawn: Optional[asyncio.Future] = None
        tasks: list[asyncio.Task] = []
        try:
            # A task, so a cancellation landing mid-spawn leaves a handle the
            # teardown can await for the child that may already exist.
            spawn = asyncio.ensure_future(asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            ))
            child = await asyncio.shield(spawn)
            logger.info("Polymarket open receiver started pid=%d", child.pid)
            child.stdin.write(start)
            start = None
            await child.stdin.drain()
            sender = asyncio.create_task(self._send_catalogs(child.stdin))
            reader = asyncio.create_task(self._dispatch(child))
            tasks = [sender, reader]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if sender.done():
                raise RuntimeError(
                    f"Polymarket open receiver catalog not delivered (pid={child.pid})"
                ) from (None if sender.cancelled() else sender.exception())
            reader.result()  # only ever ends by raising
            raise RuntimeError(f"Polymarket open receiver reader ended (pid={child.pid})")
        finally:
            self._wake = None
            self._wanted = None
            self._stats = {**self._stats, "connected": False, "shards_connected": 0}
            await _to_completion(_teardown(spawn, tasks))

    async def _dispatch(self, child) -> None:
        """The child's frames, to the callbacks one at a time, in pipe order."""
        while True:
            message = await read_frame(child.stdout)
            if message is None:
                raise RuntimeError(f"Polymarket open receiver exited (pid={child.pid})")
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

    async def _send_catalogs(self, stdin: asyncio.StreamWriter) -> None:
        wake = self._wake
        while True:
            await wake.wait()
            wake.clear()
            wanted, self._wanted = self._wanted, None
            if wanted is None:
                continue
            ids, snapshots = wanted
            frame = encode_catalog(ASSETS, {
                "asset_ids": ids, "price_book_snapshots": snapshots,
            })
            wanted = ids = None
            stdin.write(frame)
            frame = None
            await stdin.drain()


async def _teardown(spawn: Optional[asyncio.Future], tasks: list) -> None:
    """Join the run's tasks, then close and reap its child, if one exists."""
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if spawn is None:
        return
    try:
        child = await spawn
    except BaseException:
        return  # no child: the spawn failed (asyncio reaps a half-made one)
    await _stop_child(child)


async def _to_completion(coro) -> None:
    """Run ``coro`` to its end however often the caller is cancelled meanwhile;
    a cancellation that arrived is re-raised only after it finishes."""
    task = asyncio.ensure_future(coro)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                break
            cancelled = True
    exc = None if task.cancelled() else task.exception()
    if exc is not None:
        logger.error("Polymarket open receiver teardown failed", exc_info=exc)
    if cancelled:
        raise asyncio.CancelledError


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

    start = await read_frame(reader, MAX_CATALOG_FRAME_BYTES)
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
            message = await read_frame(reader, MAX_CATALOG_FRAME_BYTES)
            if message is None:
                return
            _, body = message
            message = None
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
