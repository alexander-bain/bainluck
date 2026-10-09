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
import random
from typing import Any, Callable, Optional

from pydantic_core import from_json

logger = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


def _decode_message(raw):
    """#10090: lower receive CPU without narrowing stdlib JSON semantics.

    The existing Pydantic dependency parses arbitrary-size integers exactly.
    Disable its string cache for the changing asset/book stream. Inputs it
    refuses (e.g. lone surrogate escapes) go through the original decoder,
    which also preserves the original accepted values and exception contract.
    """
    try:
        return from_json(raw, cache_strings=False)
    except (ValueError, TypeError):
        return json.loads(raw)


async def _cooperative_messages(socket):
    """Let ready stamp/publish work run during an already-buffered burst.

    Receiving a cached frame and awaiting an uncontended price handler need
    not suspend. Yield after every processed message, before consuming the next
    one, so ready probability writers do not wait behind another frame batch.
    """
    async for raw in socket:
        yield raw
        raw = None  # Do not retain the last full-depth book on a quiet socket.
        await asyncio.sleep(0)


# #837 — THE VENUE ACCEPTS AN OVERSIZED SUBSCRIBE AND SERVES A FRACTION OF IT,
# silently: no error, no close, the connection just holds and streams a few
# hundred assets. Measured against the public CLOB socket by live/512 with a
# 119-asset probe set pinned at the FRONT of every list and only the filler
# behind it changing: 119/119 served at 719 assets (56.9 KiB), 12/119 at 778
# (61.6 KiB), 6/119 at 2,000. Monotone, reproduced twice, and NOT a prefix — at
# 1,019 subscribed it served 180 assets, 8 of them from the front-placed probe.
# We were sending >=3,274 ids in one ~255 KiB frame and re-dealing that list six
# times an hour — far into the degraded band in both size and composition. A
# 176-minute MNF game produced one 15.5-minute band of prices while Kalshi ran
# the whole way; the measurement establishes that this transport was defective
# during it, and does NOT establish it as the sole cause of that hole, which was
# never independently attributed.
#
# So the list is FANNED over several connections, each sized to sit well under
# the cliff. Two deliberate choices:
#
#   * The bound is in BYTES, because bytes is the dimension the cliff moved in.
#     Ids run 74-78 characters today, so an asset COUNT alone silently drifts
#     with id length; the count cap rides along only so a pathological id length
#     cannot make one shard enormous.
#   * These numbers are NOT a claim about a documented venue limit. Nothing the
#     venue publishes says 60 KiB, and the cliff was measured, not announced.
#     They are chosen to sit comfortably below the lowest size that was ever
#     observed to degrade (56.9 KiB served in full, 61.6 KiB did not), so the
#     fix does not depend on the boundary being exactly where we found it.
MAX_SUBSCRIBE_BYTES = 40 * 1024
MAX_ASSETS_PER_CONNECTION = 500

# #837 — AN EXPLICIT RECEIVE CEILING, BECAUSE THE DEFAULT ONE IS 1 MiB AND A
# SUBSCRIBE CAN BE ANSWERED WITH ONE MESSAGE HOLDING EVERY BOOK WE ASKED FOR.
# `websockets.connect` defaults `max_size` to 2**20 = 1,048,576 bytes and closes
# the connection with 1009 "message too big" the moment a larger message
# arrives — before the consumer sees a byte of it, and before any price_change
# can follow. The shard would then reconnect, resubscribe, be sent the same
# dump, and be closed again, counting as connected the whole time while
# `stats()` said nothing about why it never served. Book depth is the venue's
# to choose and nothing on our side bounds it, so the ceiling is stated rather
# than inherited.
#
# ⚠️ THIS IS HARDENING AGAINST A LATENT MODE, NOT THE REPAIR OF A LIVE OUTAGE,
# and the distinction is written down because the measurement that motivated it
# reads like an outage report and is not one. The 1,286,965 – 1,372,376 byte
# figure (artifacts/other-model-837-final-coverage/, 2026-09-23, a single `list`
# of 460–496 book snapshots) was taken over WHOLE-VENUE live books, not over the
# sports subscription this client actually sends. Measured on production the
# same night at the shard shape that figure calls fatal — worker-ws v4950,
# uptime 1560s, `shards=3/3`, two shards subscribed at the full 500 assets
# (`0:448/500 1:482/500`) — the socket had received and json-parsed 186,472
# messages and delivered 3,611 prices to `on_price` with 0 errors and no 1009.
# `_shard_wire` is written only after JSON decoding succeeds, so those counts are
# proof of RECEIPT. They are WIRE counts and not the coverage figure `served=`
# reports today: they were taken before the numerator was narrowed to the
# subscription, so do not line them up against a current `served=` reading. Whichever spares us (thin sports books landing
# the dump under 1 MiB, or the venue not answering this population with one
# list), the close is not occurring, so do not read this constant as evidence
# that it was. It buys insurance against a book that deepens, and the mode it
# insures against is silent and total, which is why it is worth its cost.
#
# ⚠️ THE CEILING IS A MEMORY COMMITMENT, NOT JUST A RECEIVE BOUND, and it is
# written that way because the obvious reading is wrong: "the dump is parsed
# and dropped" says nothing about the cost of HOLDING it. `websockets` buffers
# the whole message before it hands the consumer a single frame, so the peak is
# paid per connected shard whatever we do with the bytes afterwards — and this
# client runs 7–8 shards concurrently. 8 MiB is therefore the per-shard worst
# case, ~64 MiB across the fleet, chosen as ~6x the largest dump ever measured
# so a deeper book does not reach the ceiling, and kept FINITE so a malformed or
# hostile message cannot grow the process without bound. Raise it only with the
# fleet-wide multiple in hand, never to clear a single observation.
MAX_MESSAGE_BYTES = 8 * 1024 * 1024

#: Messages `websockets` may hold received-but-unread per connection. Its own
#: default, stated so the per-shard memory bound is written down rather than
#: inherited: the worst case one connection can hold is this many messages of
#: up to MAX_MESSAGE_BYTES plus the one being assembled. A client that runs many
#: shards (#9484's open-contract arm) passes a smaller number.
DEFAULT_MAX_QUEUE_MESSAGES = 16

# #9484 — RECONNECT SAFEGUARDS, because one client may now hold ~70 connections
# and every one of them used to reconnect the instant its socket closed. Three
# holes, all in `_run_one`, all harmless at 7 shards and a storm at 70:
#
#   * A CLEAN close (the venue ends the socket without an error) fell straight
#     back into `connect` with no sleep at all, so a venue that closed on
#     subscribe was re-dialled in a tight loop.
#   * The backoff was reset to its floor the moment a handshake succeeded, so a
#     socket that connected and dropped every second never backed off.
#   * Every retry slept the same deterministic delay, so shards that dropped
#     together re-dialled together.
#
# So the backoff resets only once a connection has lasted
# STABLE_CONNECTION_SECONDS, a clean close sleeps at least CLEAN_CLOSE_FLOOR,
# and every sleep is jittered. None of these waits applies while a socket is
# up — they only space out re-dials.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0
STABLE_CONNECTION_SECONDS = 60.0
CLEAN_CLOSE_FLOOR_SECONDS = 1.0

#: How long a handshake permit (see `PolymarketWebSocket(max_concurrent_
#: handshakes=...)`) is held after the subscribe is sent, waiting for the
#: venue's first frame — the initial book dump. Released as soon as that frame
#: has been received and parsed, so concurrent dumps are bounded by the permit
#: count; the timeout only frees the permit of a shard whose books are silent.
HANDSHAKE_PERMIT_HOLD_SECONDS = 10.0


def _jittered(delay: float) -> float:
    """``delay`` scaled into [delay/2, delay], so siblings do not re-dial in step."""
    return delay * (0.5 + random.random() / 2)


class _HandshakePermit:
    """One shard's hold on the client's handshake gate. Release is idempotent.

    Held from before `connect` until the venue's first frame (or the hold
    timeout), never for the life of the subscription: the gate bounds how many
    shards are dialling and receiving their initial dump at once, not how many
    stay subscribed.
    """

    def __init__(self, gate: Optional[asyncio.Semaphore]):
        self._gate = gate
        self._held = False
        self._timer: Optional[asyncio.TimerHandle] = None

    async def acquire(self) -> None:
        if self._gate is not None:
            await self._gate.acquire()
            self._held = True

    def release_after(self, seconds: float) -> None:
        if self._held and self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(
                seconds, self.release
            )

    def release(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._held:
            self._held = False
            self._gate.release()


# How long a shard must have been connected before a silent one is worth
# mentioning. Long enough that an ordinary quiet stretch is not the reason.
COVERAGE_GRACE_SECONDS = 120

# How many unserved ids each shard names at the recycle. Bounded because the
# point is a sample somebody can carry to the venue and ask about, not a dump:
# a starved cycle has thousands of unserved ids and a log line is not the place
# for them. Five per shard is enough to ask the question and small enough that
# eight shards cost one line.
UNSERVED_SAMPLE_PER_SHARD = 5


def _assets_in(message: Any) -> set[str]:
    """Every asset id this frame carries, whatever shape the venue used.

    Deliberately the same harvest as live/512's `ws_probe_convict.py`, which is
    the instrument that measured the cliff — a coverage counter that reads a
    different set of shapes than the evidence did would grade the fix against
    its own blind spots. Three shapes are real on this socket: a top-level
    `asset_id` (or `assetId`), a LIST of book snapshots, and `price_change`
    frames whose ids live in a nested `changes` / `price_changes` array. A
    counter that only read the top-level key would report zero for a shard
    receiving nothing but book and price_change traffic — healthy, and
    indistinguishable from the silence this whole change exists to detect.
    """
    found: set[str] = set()
    for entry in message if isinstance(message, list) else [message]:
        if not isinstance(entry, dict):
            continue
        direct = entry.get("asset_id") or entry.get("assetId")
        if direct:
            found.add(direct)
        for key in ("changes", "price_changes"):
            for change in entry.get(key) or []:
                if isinstance(change, dict) and change.get("asset_id"):
                    found.add(change["asset_id"])
    return found


def _snapshot_quotes(message: Any) -> list[dict]:
    """A ``best_bid_ask``-shaped quote for every book in a snapshot frame.

    #9733. The venue answers a subscribe with the current book of every asset
    it serves (a LIST of ``event_type: book`` entries; a lone ``book`` dict is
    the same thing). This client used to discard it, so only a CHANGE moved a
    leg: a quiet book that moved while we were disconnected (every recycle) or
    before the leg was admitted stayed frozen until it moved again. Kittle
    524.5+ receiving yards, market 61352683, read Yes 77% / No 10% for hours
    while the venue's book sat at 0.80/0.87 and 0.13/0.20.

    Top of book is read by value, never by position: the venue lists bids
    ascending and asks descending, so ``[-1]`` happens to be best today and
    ``[0]`` is the worst quote on each side. A side with no quote gets no
    field, and the price handler refuses a half-empty book as it always has.
    """
    out: list[dict] = []
    for entry in message if isinstance(message, list) else [message]:
        if not isinstance(entry, dict):
            continue
        asset_id = entry.get("asset_id") or entry.get("assetId")
        if not asset_id:
            continue
        best: dict[str, Optional[float]] = {}
        for side, pick in (("bids", max), ("asks", min)):
            prices = []
            for level in entry.get(side) or []:
                try:
                    prices.append(float(level["price"]))
                except (KeyError, TypeError, ValueError):
                    continue
            best[side] = pick(prices) if prices else None
        if best["bids"] is None or best["asks"] is None:
            continue
        out.append(
            {
                "event_type": "best_bid_ask",
                "asset_id": asset_id,
                "market": entry.get("market"),
                "best_bid": str(best["bids"]),
                "best_ask": str(best["asks"]),
                "timestamp": entry.get("timestamp"),
                "book_snapshot": True,
            }
        )
    return out


def _evenly_spaced(items: list[str], limit: int) -> list[str]:
    """At most `limit` items, spread from the first to the last.

    Position-preserving on purpose: the caller samples a list whose ORDER is
    the thing it must not select on, so the picks are spaced across the whole
    range instead of taken off one end. Shorter than `limit` means take it all
    — there is nothing to spread.
    """
    if limit <= 0 or not items:
        return []
    if len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(k * step)] for k in range(limit)]


def _subscribe_frame(asset_ids: Optional[list[str]]) -> str:
    """The exact frame `run` sends, so sizing is measured and never estimated."""
    sub: dict[str, Any] = {"type": "market", "custom_feature_enabled": True}
    if asset_ids:
        sub["assets_ids"] = list(asset_ids)
    return json.dumps(sub)


#: The two syntax costs `json.dumps` writes around the ids, MEASURED from the
#: serializer rather than read off the shape of the string.
#:
#: An earlier version of this file hardcoded one byte for the separator, on the
#: reasonable-looking grounds that the separator is a comma. `json.dumps`
#: defaults to `", "` — comma AND space — so every shard was under-charged by
#: one byte per id and the planner's own ceiling was breached by the frames it
#: planned: 1,100 ids of 78 characters gave frames of 41066 / 41066 / 8266
#: bytes against a 40960 ceiling, and at 90 characters 41332 / 41332 / 20934.
#: Deriving both numbers means a separator change in the stdlib, or a key added
#: to the envelope, moves the accounting instead of silently invalidating it.
def _frame_overheads() -> tuple[int, int]:
    """`(envelope, separator)` in bytes for the frame `_subscribe_frame` builds.

    `envelope` is every byte a one-id frame costs EXCEPT that id's own
    serialization — the object around it plus the brackets. `separator` is what
    each id after the first adds on top of its own serialization.
    """
    probe = "x"
    encoded_probe = len(json.dumps(probe).encode("utf-8"))
    one = len(_subscribe_frame([probe]).encode("utf-8"))
    two = len(_subscribe_frame([probe, probe]).encode("utf-8"))
    return one - encoded_probe, two - one - encoded_probe


def _shard_asset_ids(
    asset_ids: list[str],
    max_bytes: int = MAX_SUBSCRIBE_BYTES,
    max_assets: int = MAX_ASSETS_PER_CONNECTION,
) -> list[list[str]]:
    """Split `asset_ids` into subscribe-sized shards, losing none of them.

    Losing none is the load-bearing property: a dropped id is exactly the defect
    this function exists to fix, so an id too large to fit a shard on its own
    still gets its own shard rather than being silently discarded. That lone
    oversized id is the ONE case a shard may exceed `max_bytes`, and it is the
    only exemption the boundary check below grants.
    """
    envelope, separator = _frame_overheads()
    shards: list[list[str]] = []
    current: list[str] = []
    current_bytes = 0

    for asset_id in asset_ids:
        encoded = len(json.dumps(asset_id).encode("utf-8"))
        # The first id in a shard pays no separator; every later one does.
        cost = encoded + (separator if current else 0)
        too_many = len(current) + 1 > max_assets
        too_big = envelope + current_bytes + cost > max_bytes
        if current and (too_many or too_big):
            shards.append(current)
            current, current_bytes = [], encoded
        else:
            current_bytes += cost
        current.append(asset_id)

    if current:
        shards.append(current)

    # Boundary check. The arithmetic above is exact, so this never fires — it is
    # here because the failure it catches is INVISIBLE at the venue: an
    # oversized frame is accepted and served in part (that is the whole finding
    # behind this file), so a sizing bug shows up as quiet missing prices, not
    # as an error. Better to fail here, loudly, than to under-serve a game.
    for shard in shards:
        size = len(_subscribe_frame(shard).encode("utf-8"))
        if size > max_bytes and len(shard) > 1:
            raise RuntimeError(
                f"subscribe shard of {len(shard)} ids serializes to {size} bytes, "
                f"over the {max_bytes}-byte ceiling — the frame sizing is wrong "
                "and the venue would silently serve only part of it"
            )
    return shards


class PolymarketWebSocket:
    """Polymarket CLOB WebSocket consumer with auto-reconnect.

    Usage:
        ws = PolymarketWebSocket()
        ws.on_price = my_price_handler
        ws.on_resolved = my_resolution_handler
        await ws.run(asset_ids=["token1", "token2"])
    """

    def __init__(
        self,
        max_concurrent_handshakes: Optional[int] = None,
        max_queue: int = DEFAULT_MAX_QUEUE_MESSAGES,
        price_book_snapshots: bool = False,
    ):
        self._message_count = 0
        # #9733: hand each book in a snapshot frame to `on_price` as a quote.
        # Off by default, so the game socket and the shadow consumer keep
        # their behaviour; the open-contract client turns it on.
        self._price_book_snapshots = price_book_snapshots
        self._book_snapshot_quotes = 0
        self._reconnect_count = 0
        # #9484: None keeps every shard free to dial at once (the game slate's
        # handful). A client with many shards bounds how many dial and take
        # their initial dump concurrently; see `_HandshakePermit`.
        self._max_concurrent_handshakes = max_concurrent_handshakes
        self._handshake_gate: Optional[asyncio.Semaphore] = None
        self._max_queue = max_queue

        # #837 coverage: what we asked the venue for, against what it has
        # actually sent us. Per shard, because the silent-fraction signature is
        # one connection going quiet while its same-sized siblings do not.
        #
        # The ASKED half holds the ids themselves rather than a count, so the
        # difference between the two is nameable. A count could only ever say
        # "1832 of 3738", which is breadth and not a finding: an untraded book
        # and a truncated subscription produce the same ratio. Naming the ids
        # is what lets the next reader ask the venue whether those particular
        # books were quiet, and one structure rather than a list beside a
        # count is deliberate — a count that can drift from the list it
        # summarises is the coverage instrument lying about coverage.
        # Two populations, deliberately not one. `_shard_wire` is everything the
        # connection was sent, foreign ids included — the venue is free to push
        # an id we never asked for, and it does: production read shard 2 at
        # 394 on the wire against a 375-id subscription, an excess of 19. That
        # raw set is what answers "did this socket receive anything at all",
        # which is `_silent_shards`' question and not a coverage question.
        # Coverage is `_served_by_shard()`, the intersection against
        # `_shard_ids`, so that the numerator and the denominator of every
        # served/subscribed ratio are drawn from the same population. Counting
        # the wire against the subscription is what let a ratio print 105% and
        # made every honest one — 98.3%, 97.8% — an over-read of the real figure.
        self._shard_ids: dict[int, list[str]] = {}
        self._shard_wire: dict[int, set[str]] = {}
        self._shards_connected: set[int] = set()
        self._shard_connected_at: dict[int, float] = {}

        self.on_price: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_resolved: Optional[Callable] = None
        self.on_new_market: Optional[Callable] = None
        self._asset_refresh: Optional[asyncio.Event] = None
        self._next_asset_ids: list[str] = []

    def update_asset_ids(
        self,
        asset_ids: list[str],
        *,
        price_book_snapshots: Optional[bool] = None,
    ) -> None:
        """Replace a refreshable client's desired catalog, including an empty one."""
        if self._asset_refresh is None:
            raise RuntimeError("Polymarket refreshable client is not running")
        if price_book_snapshots is not None:
            self._price_book_snapshots = price_book_snapshots
        self._next_asset_ids = list(dict.fromkeys(asset_ids))
        self._asset_refresh.set()

    async def run_refreshable(
        self,
        asset_ids: list[str],
        *,
        price_book_snapshots: Optional[bool] = None,
    ):
        """Keep unchanged shards connected while admitting/removing catalog tokens.

        Empty means no subscriptions here, unlike the resolution-only `run()`.
        One owner reconciles shard tasks; cancellation joins every socket before
        returning. Existing subscription-size and reconnect safeguards remain.
        """
        if self._asset_refresh is not None:
            raise RuntimeError("Polymarket refreshable client is already running")
        if price_book_snapshots is not None:
            self._price_book_snapshots = price_book_snapshots
        self._asset_refresh = asyncio.Event()
        self._next_asset_ids = list(dict.fromkeys(asset_ids))
        self._shard_ids = {}
        self._shard_wire = {}
        self._shards_connected.clear()
        self._shard_connected_at.clear()
        self._handshake_gate = (
            asyncio.Semaphore(max(1, int(self._max_concurrent_handshakes)))
            if self._max_concurrent_handshakes
            else None
        )
        tasks: dict[int, asyncio.Task] = {}
        coverage = asyncio.create_task(self._coverage_loop())
        refresh = None
        try:
            while True:
                self._asset_refresh.clear()
                wanted = set(self._next_asset_ids)
                retained = {
                    i: [a for a in ids if a in wanted]
                    for i, ids in self._shard_ids.items()
                }
                present = {a for ids in retained.values() for a in ids}
                added = [a for a in self._next_asset_ids if a not in present]
                # Fill spare capacity without moving any retained token to a
                # different shard. A stable catalog therefore restarts NONE.
                for i, ids in retained.items():
                    if added and len(ids) < MAX_ASSETS_PER_CONNECTION:
                        filled = _shard_asset_ids(ids + added)[0]
                        used = len(filled) - len(ids)
                        retained[i] = filled
                        added = added[used:]
                next_index = max(retained, default=-1) + 1
                for ids in _shard_asset_ids(added):
                    retained[next_index] = ids
                    next_index += 1
                desired = {i: ids for i, ids in retained.items() if ids}
                changed = {
                    i
                    for i in self._shard_ids.keys() | desired.keys()
                    if self._shard_ids.get(i) != desired.get(i)
                }
                stopped = [tasks.pop(i) for i in changed if i in tasks]
                for task in stopped:
                    task.cancel()
                await asyncio.gather(*stopped, return_exceptions=True)
                for i in changed:
                    self._mark_shard_down(i)
                    self._shard_ids.pop(i, None)
                    self._shard_wire.pop(i, None)
                    if i in desired:
                        self._shard_ids[i] = desired[i]
                        self._shard_wire[i] = set()
                        tasks[i] = asyncio.create_task(self._run_one(desired[i], i))
                refresh = asyncio.create_task(self._asset_refresh.wait())
                done, _ = await asyncio.wait(
                    {refresh, *tasks.values()},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done - {refresh}:
                    task.result()
                    raise RuntimeError("Polymarket shard exited unexpectedly")
                await refresh
                refresh = None
        finally:
            self._asset_refresh = None
            if refresh is not None:
                refresh.cancel()
            coverage.cancel()
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(
                *tasks.values(),
                coverage,
                *([refresh] if refresh is not None else []),
                return_exceptions=True,
            )
            self._shards_connected.clear()
            self._shard_connected_at.clear()

    async def run(self, asset_ids: Optional[list[str]] = None):
        """Connect and stream messages forever, fanned over sized connections.

        One connection per shard, all of them reconnecting independently. The
        caller is unchanged: `_run_polymarket_ws_consumer` still awaits this
        under `wait_for(..., SUBSCRIPTION_REFRESH_SECONDS)`, and the timeout's
        cancellation still tears every connection down — see the `finally`.
        """
        shards: list[Optional[list[str]]]
        if asset_ids:
            shards = list(_shard_asset_ids(asset_ids))
        else:
            # No ids at all means "subscribe to everything", which is one frame
            # with nothing to fan. The shadow resolution-only consumer uses it.
            shards = [None]

        self._shard_ids = {i: list(s or []) for i, s in enumerate(shards)}
        self._shard_wire = {i: set() for i in range(len(shards))}
        self._shards_connected = set()
        self._shard_connected_at = {}
        # Built here, inside the running loop, and fresh per run.
        self._handshake_gate = (
            asyncio.Semaphore(max(1, int(self._max_concurrent_handshakes)))
            if self._max_concurrent_handshakes
            else None
        )

        if asset_ids and len(shards) > 1:
            logger.info(
                "Polymarket WS fanning %d assets over %d connections "
                "(<=%d assets / <=%d bytes each; one frame would have been %d bytes)",
                len(asset_ids),
                len(shards),
                MAX_ASSETS_PER_CONNECTION,
                MAX_SUBSCRIBE_BYTES,
                len(_subscribe_frame(asset_ids).encode("utf-8")),
            )

        if len(shards) == 1:
            await self._run_one(shards[0], 0)
            return

        tasks = [
            asyncio.create_task(self._run_one(shard, index))
            for index, shard in enumerate(shards)
        ]
        coverage = asyncio.create_task(self._coverage_loop())
        try:
            await asyncio.gather(*tasks)
        finally:
            # Bounded lifetime: no connection outlives this call on ANY exit
            # path, cancellation included. Without this, a planned recycle every
            # SUBSCRIPTION_REFRESH_SECONDS would leak one socket per shard.
            coverage.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, coverage, return_exceptions=True)
            self._shards_connected.clear()
            self._shard_connected_at.clear()

    def _silent_shards(self, now: float) -> list[int]:
        """Shards that have been connected long enough to have been served, and
        were not.

        Split out from the loop so the decision can be graded on seeded state
        instead of on how long a test slept — the grace below is exactly the
        kind of rule a timing-raced test pins by accident and never convicts.

        Two shards are deliberately NOT subjects, and `_shard_connected_at`
        decides both, which is why it is read here rather than
        `_shards_connected`. A shard that connected moments ago has not had time
        to be served, so it is not evidence of anything: without the grace the
        loop's own tick can convict a shard that reconnected a second before it,
        a false positive in the very instrument this fix is graded on. And a
        shard with no live socket has no stamp at all — `_mark_shard_down` takes
        it with the connection — so it drops out here too, correctly: that is a
        disconnect, already logged loudly, not a starved subscription.

        The RAW wire set is the right input here and the intersected coverage
        set is not: this asks whether a connection received anything at all, so
        a shard that was sent only ids outside its own subscription has plainly
        not gone quiet — the socket is alive and the venue is answering it. That
        is a different defect from a starved subscription and it would be a
        false positive under this warning's own wording. It is visible instead
        as `on_wire_by_shard` exceeding `served_by_shard` in `stats`.
        """
        return [
            i
            for i, wire in self._shard_wire.items()
            if not wire
            and i in self._shard_connected_at
            and now - self._shard_connected_at[i] >= COVERAGE_GRACE_SECONDS
        ]

    async def _coverage_loop(self):
        """Say so when one shard is silent and its siblings are not.

        Deliberately NOT "every subscribed leg must emit" — a quiet market is
        quiet for honest reasons, and absence on one leg proves nothing. The
        signal is comparative: same-sized shards, some serving and one serving
        nothing at all, is the shape the oversized subscribe produced.

        The ratio printed beside it is the INTERSECTED count over the
        subscription, so the two halves of `served/subscribed` count the same
        population; the trip condition above it is still the raw wire, because
        silence is about the socket and coverage is about the subscription.
        """
        while True:
            await asyncio.sleep(COVERAGE_GRACE_SECONDS)
            served = {i: len(s) for i, s in self._served_by_shard().items()}
            silent = self._silent_shards(asyncio.get_running_loop().time())
            # The sibling test stays on the RAW wire for the same reason
            # `_silent_shards` does: "is anyone else being answered at all" is
            # the comparison that makes one shard's silence mean something, and
            # scoring a sibling on the intersection would suppress this warning
            # in exactly the case where the venue is answering the fleet with
            # ids nobody asked for.
            streaming = any(self._shard_wire.values())
            if silent and streaming:
                logger.warning(
                    "Polymarket WS coverage: shard(s) %s have served 0 distinct "
                    "assets while siblings are streaming — served/subscribed %s",
                    silent,
                    {
                        i: f"{served[i]}/{len(self._shard_ids.get(i) or [])}"
                        for i in served
                    },
                )

    def _mark_shard_down(self, shard: int) -> None:
        """This shard has no live socket, so it is not a coverage subject.

        The connect stamp goes with the connection: a shard that has been down
        for ten minutes would otherwise carry an old stamp and read as silent
        forever, reporting a disconnect — already logged, loudly — a second time
        as a starved subscription, which is a different and wrong diagnosis.
        """
        self._shards_connected.discard(shard)
        self._shard_connected_at.pop(shard, None)

    async def _run_one(self, asset_ids: Optional[list[str]], shard: int):
        """One connection: subscribe, stream, reconnect. The original loop."""
        import websockets

        backoff = INITIAL_BACKOFF_SECONDS
        loop = asyncio.get_running_loop()

        while True:
            permit = _HandshakePermit(self._handshake_gate)
            connected_at: Optional[float] = None
            try:
                await permit.acquire()
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    close_timeout=5,
                    # The initial dump for a full shard is one message over the
                    # library's 1 MiB default; see MAX_MESSAGE_BYTES.
                    max_size=MAX_MESSAGE_BYTES,
                    max_queue=self._max_queue,
                ) as ws:
                    connected_at = loop.time()
                    self._shards_connected.add(shard)
                    self._shard_connected_at[shard] = connected_at
                    if self._reconnect_count > 0:
                        logger.info(
                            "Polymarket WS shard %d reconnected (attempt %d)",
                            shard,
                            self._reconnect_count,
                        )
                    else:
                        logger.info("Polymarket WS shard %d connected", shard)
                    self._reconnect_count += 1

                    frame = _subscribe_frame(asset_ids)
                    await ws.send(frame)
                    logger.info(
                        "Polymarket WS shard %d subscribed (%s, %d bytes)",
                        shard,
                        f"{len(asset_ids)} assets" if asset_ids else "all",
                        len(frame.encode("utf-8")),
                    )
                    # #9484: the permit rides until the initial dump lands (the
                    # first frame, below) or this timeout, whichever is first.
                    permit.release_after(HANDSHAKE_PERMIT_HOLD_SECONDS)

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
                        async for raw in _cooperative_messages(ws):
                            try:
                                if raw == "PONG":
                                    continue
                                self._message_count += 1

                                try:
                                    data = _decode_message(raw)
                                except (json.JSONDecodeError, TypeError):
                                    continue
                                finally:
                                    # First frame received and parsed — the dump is
                                    # no longer in flight. Idempotent after that.
                                    permit.release()

                                # #837 coverage is counted HERE — on the wire, above
                                # every skip and before any event_type or handler
                                # dispatch. A count taken after filtering answers a
                                # different question ("did we act on this shard?")
                                # and reads zero for a shard the venue is in fact
                                # serving, which would make an unhandled shard
                                # indistinguishable from a starved one.
                                #
                                # It is recorded RAW, and narrowed to the
                                # subscription at the read (`_served_by_shard`),
                                # not here: an id the venue sent us unasked is a
                                # real thing this connection received, and dropping
                                # it at the write would erase the only evidence that
                                # it happened. Filtering here would also make the
                                # counter silently depend on `_shard_ids` having
                                # been populated first.
                                on_wire = _assets_in(data)
                                if on_wire:
                                    self._shard_wire.setdefault(shard, set()).update(
                                        on_wire
                                    )

                                event_type = (
                                    "book"
                                    if isinstance(data, list)
                                    else data.get("event_type", "")
                                )

                                if event_type == "book":
                                    # #9733: the venue's current book. Priced only
                                    # by a client that asked for it; skipped by
                                    # every other, as before.
                                    if self._price_book_snapshots and self.on_price:
                                        await self._price_snapshot(data)
                                    continue

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
                                        logger.exception(
                                            "Polymarket resolution handler error"
                                        )

                                elif event_type == "new_market" and self.on_new_market:
                                    try:
                                        result = self.on_new_market(data)
                                        if asyncio.iscoroutine(result):
                                            await result
                                    except Exception:
                                        logger.exception(
                                            "Polymarket new_market handler error"
                                        )

                            finally:
                                # #10663: a quiet socket must not retain its last
                                # processed full-depth book while awaiting input.
                                # Awaited callbacks finish/unwind before cleanup.
                                raw = None
                                data = None
                                result = None

                    finally:
                        hb.cancel()
                        # Leaving the `async for` at all means this socket is
                        # done, including the clean-close path that raises
                        # nothing — without this, a shard that fell out quietly
                        # would keep counting as connected until its next error.
                        self._mark_shard_down(shard)

            except asyncio.CancelledError:
                # Q460 (CERT-491): RE-RAISE — same contract as
                # `app/services/kalshi_ws.py`. A `wait_for` timeout arrives as a
                # cancellation; swallowing it turned every planned subscription
                # recycle into a 10-second blackout in `run_kalshi_ws.py`.
                logger.info("Polymarket WS shard %d cancelled, shutting down", shard)
                self._mark_shard_down(shard)
                raise

            except Exception as e:
                self._mark_shard_down(shard)
                reason = f"{type(e).__name__}: {str(e)[:100]}"
                floor = 0.0
            else:
                # #9484: a CLEAN close used to re-dial with no sleep at all.
                reason = "closed cleanly"
                floor = CLEAN_CLOSE_FLOOR_SECONDS
            finally:
                permit.release()

            # #9484: only a connection that held earns the backoff its reset;
            # one that drops straight after its handshake keeps backing off.
            if (
                connected_at is not None
                and loop.time() - connected_at >= STABLE_CONNECTION_SECONDS
            ):
                backoff = INITIAL_BACKOFF_SECONDS
            delay = _jittered(max(backoff, floor))
            logger.warning(
                "Polymarket WS shard %d disconnected (%s), reconnecting in %.1fs",
                shard,
                reason,
                delay,
            )
            await asyncio.sleep(delay)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    @property
    def is_connected(self) -> bool:
        """At least one shard is connected.

        Kept as "any", not "all", because that is what the single-connection
        version meant and the liveness line that reads it
        (`_run_polymarket_ws_consumer`'s stats loop) prints
        streaming/disconnected. `stats["shards_connected"]` is where a partial
        fan-out is visible.

        Derived from the per-shard set rather than a shared flag: with seven
        connections writing one boolean, the first shard to drop reported the
        whole consumer disconnected while six others streamed — the liveness
        line would have called a working fan-out dead.
        """
        return bool(self._shards_connected)

    def _served_by_shard(self) -> dict[int, set[str]]:
        """Per shard, the SUBSCRIBED ids the venue has actually sent a frame for.

        The intersection, and the reason coverage is read through this rather
        than off `_shard_wire` directly. The venue sends ids we never asked for
        — measured on production, shard 2 carried 19 of them across two reads,
        `2:394/375` and `2:498/479` — so a numerator taken from the wire is
        counted over a different population from the subscription denominator
        beside it. That produced ratios above 100% where the excess was large
        enough to notice and, far worse, quietly inflated every ratio where it
        was not: the 98.3% and 97.8% coverage figures this instrument reported
        are upper bounds, not readings.

        AN INTERSECTION AND NOT A CAP, which codex's counterexample settles
        (review 2026-09-23 06:38Z): one subscribed id never sent, one foreign id
        received, and the old counter read `assets_served=1` of
        `assets_subscribed=1` while `unserved_by_shard` said 1 in the same
        breath. That shard never crossed its own denominator, so there was no
        excess to subtract and a cap would have left `1/1` exactly as it was.
        The over-count does not require an overfull shard.

        Keyed on `_shard_ids` so the population is the subscription even for a
        shard that has been sent nothing, and so this and `_unserved_by_shard`
        below partition that subscription exactly — served + unserved is the
        subscribed count for every shard, which is the invariant the old
        counter could not satisfy.
        """
        out: dict[int, set[str]] = {}
        for shard, ids in self._shard_ids.items():
            wire = self._shard_wire.get(shard) or set()
            out[shard] = {asset_id for asset_id in ids if asset_id in wire}
        return out

    def _unserved_by_shard(self) -> dict[int, list[str]]:
        """Per shard, the subscribed ids the venue has never sent a frame for.

        Set difference against the SUBSCRIPTION, not against everything seen:
        the venue is free to send an id we did not ask for, and counting that
        against a shard's coverage would credit one shard for another's
        traffic. The order of the shard's own subscribe is preserved because
        the sampler below reads position, and position is the confound it
        exists to spread across.
        """
        served = self._served_by_shard()
        out: dict[int, list[str]] = {}
        for shard, ids in self._shard_ids.items():
            hit = served.get(shard) or set()
            out[shard] = [asset_id for asset_id in ids if asset_id not in hit]
        return out

    def unserved_sample(
        self, limit: int = UNSERVED_SAMPLE_PER_SHARD
    ) -> dict[int, list[str]]:
        """Up to `limit` unserved ids per shard, spread across each shard.

        This is the whole point of keeping the ids. `assets_served` counts
        assets that sent at least one message, so an untraded book and a
        truncated subscription read identically in the ratio — 49% served is
        measured breadth, not a finding. Naming ids converts it: ask the venue
        whether these particular books were quiet, and the answer separates
        "nobody traded them" from "we were never served them".

        SPREAD, not the first `limit`. `_shard_asset_ids` slices the caller's
        list contiguously, and that list comes from a query with no `ORDER BY`
        — heap order, which tracks insertion order, which tracks market age. So
        the head of a shard is its oldest slice, and taking the first few ids
        would select the sample by the very variable under test. Evenly spaced
        indices touch head, middle and tail, so a sample that comes back
        uniformly quiet says something about the shard rather than about its
        oldest corner.

        Shards with nothing unserved are omitted rather than reported empty:
        an empty list is the healthy case and does not need a line.
        """
        sample: dict[int, list[str]] = {}
        for shard, unserved in self._unserved_by_shard().items():
            if not unserved:
                continue
            sample[shard] = _evenly_spaced(unserved, limit)
        return sample

    async def _price_snapshot(self, data: Any) -> None:
        """Each book in a snapshot frame, through `on_price` like a quote."""
        # An async price callback can complete without suspending. Bound book
        # extraction as well as callbacks so a reconnect dump cannot monopolize
        # the loop ahead of ready quotes on other shards (#10665).
        entries = data if isinstance(data, list) else [data]
        batch_size = 32
        for start in range(0, len(entries), batch_size):
            for quote in _snapshot_quotes(entries[start : start + batch_size]):
                self._book_snapshot_quotes += 1
                try:
                    result = self.on_price(quote)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Polymarket book snapshot price handler error")
            if start + batch_size < len(entries):
                await asyncio.sleep(0)

    @property
    def stats(self) -> dict:
        served = {i: len(s) for i, s in self._served_by_shard().items()}
        subscribed = {i: len(ids) for i, ids in self._shard_ids.items()}
        on_wire = {i: len(s) for i, s in self._shard_wire.items()}
        return {
            "connected": self.is_connected,
            "messages": self._message_count,
            "reconnects": self._reconnect_count,
            # #837: what we asked for against what the venue actually sent, so
            # a silently-served fraction is a number somebody can read rather
            # than something inferred from a missing chart.
            "shards": len(self._shard_ids),
            "shards_connected": len(self._shards_connected),
            "assets_subscribed": sum(subscribed.values()),
            "assets_served": sum(served.values()),
            "served_by_shard": served,
            # Both halves per shard, so the unserved COUNT is read rather than
            # subtracted by hand. The first production read of this ratio came
            # back bimodal (four shards under 40, four near 500) and the reader
            # had to reconstruct the denominators from a separate capture to
            # see it.
            "subscribed_by_shard": subscribed,
            "unserved_by_shard": {
                i: len(u) for i, u in self._unserved_by_shard().items()
            },
            # The raw wire count, kept as its own field rather than folded into
            # `served_by_shard`, because narrowing the numerator to the
            # subscription would otherwise make the excess unreadable: served
            # can no longer exceed its denominator — a consequence of the
            # intersection, NOT a cap, which would leave the counterexample
            # below untouched — so `2:375/375` reads the same whether the wire
            # carried 375 ids or 394. Stated
            # separately, `on_wire - served` is the count of ids the venue sent
            # this shard unasked — the thing that was being scored AS coverage —
            # and it is also the only served-ish number the shadow consumer has,
            # since that one subscribes to everything and so has no subscription
            # to intersect against.
            "assets_on_wire": sum(on_wire.values()),
            "on_wire_by_shard": on_wire,
            # #9733: books from snapshot frames handed to `on_price`.
            "book_snapshot_quotes": self._book_snapshot_quotes,
        }
