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
import time
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

#: #10090 — the open fleet's subscribe-snapshot quotes reach the consumer at
#: most this many per second (``POLYMARKET_WS_OPEN_SNAPSHOT_QUOTES_PER_SECOND``;
#: ``0`` forwards them unpaced, as before). The consumer writes standalone open
#: rows at most ``OPEN_FLUSH_CHUNKS_PER_FLUSH`` x ``FLUSH_CHUNK_ROWS`` per
#: ``PRICE_FLUSH_SECONDS`` (2 x 500 / 2 s = 500 rows/s) and a binary's quote
#: prices both legs, so 250 quotes/s already fills that write capacity: a
#: faster arrival only grows the consumer's buffer. Measured startup (Boyer
#: trace, 10/15): ~15k snapshot quotes reached the consumer in the 14 s after
#: the open handover while only 3,149 open rows were written.
OPEN_SNAPSHOT_QUOTES_PER_SECOND = 250.0


def open_snapshot_quotes_per_second() -> float:
    raw = os.getenv("POLYMARKET_WS_OPEN_SNAPSHOT_QUOTES_PER_SECOND")
    if raw is None:
        return OPEN_SNAPSHOT_QUOTES_PER_SECOND
    try:
        rate = float(raw)
    except ValueError:
        return OPEN_SNAPSHOT_QUOTES_PER_SECOND
    return rate if rate > 0 and rate != float("inf") else 0.0


class SnapshotPacer:
    """#10090 — the child's subscribe-snapshot quotes, paced; live frames never.

    On startup (and every reconnect) each open shard answers its subscribe with
    a full-depth book for every token, and the client turns each into a quote
    (``book_snapshot``). Forwarded as they decode, ~66k such quotes arrive on
    the consumer's loop within about a minute of the catalog handover, beside
    the live game stream that loop also owns, and pile up in its price buffer
    far faster than the open rows can be written.

    Held here instead: the LATEST snapshot quote per token, released at most
    ``rate`` quotes a second. Semantics the consumer relies on are kept:

    - A live price or trade for a token first releases every pending snapshot
      quote of the same venue market (its own and its binary partner's, in
      arrival order), then is forwarded at once. So per token, and across one
      binary's complementary legs, the consumer sees exactly the order the
      client produced; only snapshot quotes of OTHER markets move later.
    - A newer snapshot of a token replaces its pending one (latest state).
    - The pacer never waits on the sockets: holding a quote costs one dict
      entry per token, bounded by the catalog. Live frames keep the existing
      pipe backpressure.

    A snapshot quote still pending when the child stops is not forwarded; the
    consumer's next run subscribes again and receives a fresh snapshot.
    """

    def __init__(self, write: Callable[[str, Any], None], drain, rate: float, *,
                 sleep=asyncio.sleep, clock=time.monotonic):
        self._write = write
        self._drain = drain
        self._rate = float(rate)
        self._sleep = sleep
        self._clock = clock
        self._seq = 0
        #: token -> (arrival seq, group, quote); dict order = oldest pending first
        self._pending: dict[str, tuple[int, str, dict]] = {}
        self._groups: dict[str, set[str]] = {}
        self._wake = asyncio.Event()
        self.released = 0

    @property
    def pending(self) -> int:
        return len(self._pending)

    @staticmethod
    def _token(message: Any) -> Optional[str]:
        if not isinstance(message, dict):
            return None
        return message.get("asset_id") or message.get("assetId") or None

    def _group(self, message: dict, token: str) -> str:
        return message.get("market") or token

    async def price(self, message: Any) -> None:
        token = self._token(message)
        if token is not None and message.get("book_snapshot"):
            self._seq += 1
            group = self._group(message, token)
            held = self._pending.get(token)
            if held is not None and held[1] != group:
                self._discard(token)
                held = None
            if held is None:
                self._groups.setdefault(group, set()).add(token)
            # Assigning an existing key keeps its place in the release order.
            self._pending[token] = (self._seq, group, message)
            self._wake.set()
            return
        await self._live(PRICE, message)

    async def trade(self, message: Any) -> None:
        await self._live(TRADE, message)

    async def _live(self, kind: str, message: Any) -> None:
        token = self._token(message)
        if token is not None and self._pending:
            self._release(self._group(message, token), token)
        self._write(kind, message)
        await self._drain()

    def _discard(self, token: str) -> None:
        _seq, group, _quote = self._pending.pop(token)
        members = self._groups.get(group)
        if members is not None:
            members.discard(token)
            if not members:
                del self._groups[group]

    def _release(self, group: str, token: Optional[str] = None) -> int:
        """Write every pending quote of ``group`` (and ``token``'s), oldest first."""
        names = set(self._groups.get(group, ()))
        if token is not None and token in self._pending:
            names.add(token)
            names.update(self._groups.get(self._pending[token][1], ()))
        held = sorted(
            (self._pending[name] for name in names if name in self._pending),
            key=lambda entry: entry[0],
        )
        for _seq, _group, quote in held:
            self._discard(self._token(quote))
        for _seq, _group, quote in held:
            self._write(PRICE, quote)
        self.released += len(held)
        return len(held)

    async def run(self) -> None:
        """Release pending snapshot quotes, a whole market at a time, <= rate/s."""
        while True:
            if not self._pending:
                self._wake.clear()
                await self._wake.wait()
                continue
            token = next(iter(self._pending))
            sent = self._release(self._pending[token][1], token)
            await self._drain()
            if sent:
                await self._sleep(sent / self._rate)


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
        self._snapshot_quotes_per_second = open_snapshot_quotes_per_second()
        self._command = command or [sys.executable, RECEIVER_SCRIPT]
        self._stats: dict = {}
        self._wanted: Optional[tuple[list[str], bool]] = None
        self._wake: Optional[asyncio.Event] = None
        # #10090: the catalog this client currently owns. The child fences its
        # own sockets, but frames already in the pipe when a catalog changes
        # still arrive here after the shared routing maps moved, so a token
        # that left this client is dropped at the parent too.
        self._routed: Optional[frozenset[str]] = None
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
        self._routed = frozenset(self._wanted[0])
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
            "snapshot_quotes_per_second": self._snapshot_quotes_per_second,
        })
        self._wake = asyncio.Event()
        self._wanted = None
        self._routed = frozenset(asset_ids)
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
            self._routed = None
            self._stats = {**self._stats, "connected": False, "shards_connected": 0}
            try:
                await _to_completion(_teardown(spawn, tasks))
            finally:
                # #10090: the reader runs until teardown joins it and may apply
                # one more `connected: True` frame after the line above. The
                # run's final state is written once the reader is gone.
                self._stats = {**self._stats, "connected": False, "shards_connected": 0}

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
            routed = self._routed
            if handler is not None and routed is not None and isinstance(body, dict):
                asset_id = body.get("asset_id") or body.get("assetId")
                if asset_id and asset_id not in routed:
                    handler = None
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

    pacer = None
    rate = config.get("snapshot_quotes_per_second") or 0
    if rate > 0:
        pacer = SnapshotPacer(
            lambda kind, message: writer.write(encode_frame((kind, message))),
            writer.drain, rate,
        )
        client.on_price = pacer.price
        client.on_trade = pacer.trade
    else:
        client.on_price = lambda message: forward(PRICE, message)
        client.on_trade = lambda message: forward(TRADE, message)

    async def report():
        while True:
            stats = client.stats
            if pacer is not None:
                stats = {**stats, "snapshot_quotes_pending": pacer.pending,
                         "snapshot_quotes_released": pacer.released}
            await forward(STATS, stats)
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
    if pacer is not None:
        tasks.append(asyncio.create_task(pacer.run()))
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
