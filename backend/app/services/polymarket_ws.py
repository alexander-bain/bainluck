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

# How long a shard must have been connected before a silent one is worth
# mentioning. Long enough that an ordinary quiet stretch is not the reason.
COVERAGE_GRACE_SECONDS = 120


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

    def __init__(self):
        self._message_count = 0
        self._reconnect_count = 0

        # #837 coverage: what we asked the venue for, against what it has
        # actually sent us. Per shard, because the silent-fraction signature is
        # one connection going quiet while its same-sized siblings do not.
        self._shard_subscribed: dict[int, int] = {}
        self._shard_served: dict[int, set[str]] = {}
        self._shards_connected: set[int] = set()
        self._shard_connected_at: dict[int, float] = {}

        self.on_price: Optional[Callable] = None
        self.on_trade: Optional[Callable] = None
        self.on_resolved: Optional[Callable] = None
        self.on_new_market: Optional[Callable] = None

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

        self._shard_subscribed = {i: len(s or []) for i, s in enumerate(shards)}
        self._shard_served = {i: set() for i in range(len(shards))}
        self._shards_connected = set()
        self._shard_connected_at = {}

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
        """
        return [
            i
            for i, served in self._shard_served.items()
            if not served
            and i in self._shard_connected_at
            and now - self._shard_connected_at[i] >= COVERAGE_GRACE_SECONDS
        ]

    async def _coverage_loop(self):
        """Say so when one shard is silent and its siblings are not.

        Deliberately NOT "every subscribed leg must emit" — a quiet market is
        quiet for honest reasons, and absence on one leg proves nothing. The
        signal is comparative: same-sized shards, some serving and one serving
        nothing at all, is the shape the oversized subscribe produced.
        """
        while True:
            await asyncio.sleep(COVERAGE_GRACE_SECONDS)
            served = {i: len(s) for i, s in self._shard_served.items()}
            silent = self._silent_shards(asyncio.get_running_loop().time())
            if silent and any(n > 0 for n in served.values()):
                logger.warning(
                    "Polymarket WS coverage: shard(s) %s have served 0 distinct "
                    "assets while siblings are streaming — served/subscribed %s",
                    silent,
                    {i: f"{served[i]}/{self._shard_subscribed.get(i, 0)}" for i in served},
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

        backoff = 1.0
        max_backoff = 60.0

        while True:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    close_timeout=5,
                ) as ws:
                    self._shards_connected.add(shard)
                    self._shard_connected_at[shard] = (
                        asyncio.get_running_loop().time()
                    )
                    if self._reconnect_count > 0:
                        logger.info(
                            "Polymarket WS shard %d reconnected (attempt %d)",
                            shard,
                            self._reconnect_count,
                        )
                    else:
                        logger.info("Polymarket WS shard %d connected", shard)
                    self._reconnect_count += 1
                    backoff = 1.0

                    frame = _subscribe_frame(asset_ids)
                    await ws.send(frame)
                    logger.info(
                        "Polymarket WS shard %d subscribed (%s, %d bytes)",
                        shard,
                        f"{len(asset_ids)} assets" if asset_ids else "all",
                        len(frame.encode("utf-8")),
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

                            # #837 coverage is counted HERE — on the wire, above
                            # every skip and before any event_type or handler
                            # dispatch. A count taken after filtering answers a
                            # different question ("did we act on this shard?")
                            # and reads zero for a shard the venue is in fact
                            # serving, which would make an unhandled shard
                            # indistinguishable from a starved one.
                            served = _assets_in(data)
                            if served:
                                self._shard_served.setdefault(shard, set()).update(
                                    served
                                )

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

    @property
    def stats(self) -> dict:
        served = {i: len(s) for i, s in self._shard_served.items()}
        return {
            "connected": self.is_connected,
            "messages": self._message_count,
            "reconnects": self._reconnect_count,
            # #837: what we asked for against what the venue actually sent, so
            # a silently-served fraction is a number somebody can read rather
            # than something inferred from a missing chart.
            "shards": len(self._shard_subscribed),
            "shards_connected": len(self._shards_connected),
            "assets_subscribed": sum(self._shard_subscribed.values()),
            "assets_served": sum(served.values()),
            "served_by_shard": served,
        }
