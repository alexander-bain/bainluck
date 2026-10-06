"""Kalshi WebSocket consumer task.

Long-running process that streams live prices and settlement events from
Kalshi's WebSocket API. Replaces the 2-minute REST polling for linked markets
with sub-second latency updates.

Channels:
  - ticker: price updates → batch-write FuturesOutcome.current_probability
  - market_lifecycle_v2: settlement → mark FuturesMarket as resolved
"""

import asyncio
import contextlib
import logging
import os
import time
from datetime import datetime, timezone

from app.utils.kalshi_market_status import is_terminal
from app.tasks.ws_consumer_sessions import owns_consumer_sessions  # #2471
from app.utils.market_quote_push import queue_market_change
from app.utils.market_settlement import settled_values

logger = logging.getLogger(__name__)


#: Q460 — how long a WS consumer run keeps one subscription list before handing
#: control back so the slate can be re-read. Ten minutes bounds the "game went
#: live after we connected" hole to ten minutes; the cost is one reconnect per
#: consumer per ten minutes, which is ordinary client behaviour on both venues'
#: published sockets and adds no REST calls at all.
SUBSCRIPTION_REFRESH_SECONDS = int(
    os.getenv("WS_SUBSCRIPTION_REFRESH_SECONDS", "600")
)

#: Q491 — the interval between flush STARTS (#10090: start to start, so a
#: flush's own work is not added to it; `run_flush_cadence`). Both sockets share
#: it, as they share the recycle timer above, so the two cannot drift to
#: different write cadences on the same dyno. Named rather than inlined because
#: it is also the RETRY interval: a flush that fails re-queues its batch, and
#: this is how long after the failure the price waits for the next attempt.
PRICE_FLUSH_SECONDS = float(os.getenv("WS_PRICE_FLUSH_SECONDS", "2"))

# Q491 repair (CERT-654 BLOCK). The periodic flush can afford to requeue a failed
# batch because another flush is `PRICE_FLUSH_SECONDS` away. **The final flush has
# no successor** — after it the consumer returns and the buffer is garbage — so
# requeueing there discarded the batch exactly as the pre-Q491 code did, and the
# recycle path runs it every `SUBSCRIPTION_REFRESH_SECONDS`, not just at shutdown.
# The last drain therefore RETRIES instead of requeueing.
#
# No sleep between attempts, deliberately: this runs inside a `finally` that is
# also reached via `CancelledError`, and awaiting a sleep during cancellation
# raises immediately and would abandon the drain. Each attempt opens a FRESH
# session (and so a fresh connection), which is what a connection-level transient
# actually needs in order to clear.
FINAL_FLUSH_ATTEMPTS = int(os.getenv("WS_FINAL_FLUSH_ATTEMPTS", "3"))


def _kalshi_slate_event_window():
    """The events whose Kalshi markets the socket subscribes to.

    Live, scheduled within 6 h, and (#9484) an open market on a recently
    suspended event — see `app.tasks.ws_slate`. A function rather than inline
    so the real-Postgres contract reads the shipped expression.
    """
    from sqlalchemy import and_, or_, text

    from app.models.models import Event
    from app.tasks.ws_slate import suspended_open_market_arm

    return or_(
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
        suspended_open_market_arm(),
    )


def linked_first_phases(batch, market_id_by_outcome, event_id_by_outcome):
    """#10640 — split one flush's batch into the game phase and the rest.

    WHY. The #9484 open-contract shards feed the same buffer as the game
    socket, and the flush wrote every buffered row in ONE transaction, then
    committed, published, and only then re-stamped event blends. So a live
    game's Kalshi move waited behind every futures/prop row buffered in the
    same 2 s (≥60% of written rows, from the 17:53Z stats line) before its
    commit, its market frame and its blend stamp. Root's hold/release control
    reproduced it on the #2471 head.

    A MARKET goes first if any of its buffered rows has a linked event (a slate
    leg, or the #9484 bridge), and goes WHOLE: its siblings stay in the same
    transaction, so the price rows and the field re-rank describe one cut of
    the batch. Returns ``[batch]`` — the old single transaction — when either
    phase would be empty, or when any row's market is unknown (guessing that
    an unknown row has no siblings could split a market). Never two phases
    that share a market. Pure: no I/O, the batch is not mutated.
    """
    if any(oid not in market_id_by_outcome for oid in batch):
        return [batch]
    linked_markets = {
        market_id_by_outcome[oid]
        for oid in batch
        if event_id_by_outcome.get(oid) is not None
    }
    first = {
        oid: entry for oid, entry in batch.items()
        if market_id_by_outcome[oid] in linked_markets
    }
    if not first or len(first) == len(batch):
        return [batch]
    rest = {oid: entry for oid, entry in batch.items() if oid not in first}
    return [first, rest]


@owns_consumer_sessions("kalshi")
async def _run_kalshi_ws_consumer(*, sessions):
    """Main WebSocket consumer loop.

    1. Load linked Kalshi market tickers from DB
    2. Connect to WS and subscribe to ticker + lifecycle channels
    3. Buffer price updates, flush every 2s
    4. Process settlements immediately
    """
    from sqlalchemy import select, update, text, or_, and_, func
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.kalshi_ws import KalshiWebSocket
    from app.tasks.kalshi import _kalshi_yes_probability  # #8753
    from app.tasks.live_blend_refresh import (
        LiveBlendRefresher, TailReceipts, adopt_handed_off, event_ids_for_outcomes,
        hand_off_pending, run_flush_cadence,
    )
    from app.tasks.ws_admission import (  # #9418
        run_until_admission, unadmitted_live_events,
        watch_for_unadmitted_live_events,
    )
    from app.tasks.ws_liveness import report as _report_liveness
    from app.tasks.ws_open_contracts import (  # #9484
        grade_open_contract_leg, kalshi_open_contract_stmt,  # #10022
        lifecycle_state, lifecycle_verdict, open_contract_bridge_event_stmt,
        open_contract_channels, open_contract_event_bridge,
        open_contract_event_candidates, open_contract_prices_enabled,
        open_contract_settlement_enabled, open_contract_ticker_map,
        shard_tickers,
    )
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    from app.utils.price_change_stamp import price_changed_at_value
    from app.utils.price_change_stamp import quote_moved_column  # #9484
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

    # #2471: one engine for this run, a fresh session per operation; the
    # decorator disposes it after the final drain. Same call shape as the
    # task factory, so every site below is unchanged.
    get_task_session = sessions.session

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    has_key = os.getenv("KALSHI_RSA_PRIVATE_KEY") or os.getenv("KALSHI_PRIVATE_KEY_PATH")

    if not api_key_id or not has_key:
        logger.warning("Kalshi WS: missing credentials, skipping")
        _report_liveness("kalshi", "no_credentials")
        return {"status": "skipped", "reason": "no_credentials"}

    # Q504-b: reported BEFORE the slate query, because a DB handshake that never
    # resolves is one of the two shapes "up and silent" can take, and the arm
    # cannot describe a state it is stuck inside.
    _report_liveness("kalshi", "loading_slate")

    # #9418: the admission floor is measured from here, the previous recycle.
    run_started_at = time.monotonic()
    ws = KalshiWebSocket()

    # -- Load market tickers to subscribe to --
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesMarket.external_id,
                FuturesMarket.id,
                FuturesMarket.event_id,
            )
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "kalshi",
                FuturesMarket.event_id.isnot(None),
                _kalshi_slate_event_window(),
            )
        )
        rows = result.all()

    event_tickers = list({row[0] for row in rows})
    market_id_by_ext = {row[0]: row[1] for row in rows}
    # Q460: the linked event behind each market, so a flushed price can be
    # traced back to the card it belongs on and the blend re-stamped there.
    event_id_by_market: dict[int, int] = {
        row[1]: row[2] for row in rows if row[2] is not None
    }

    # Load outcome tickers for subscription
    all_market_ids = list(market_id_by_ext.values())
    outcome_rows = []
    if all_market_ids:
        async with get_task_session() as session:
            outcome_result = await session.execute(
                select(
                    FuturesOutcome.external_id,
                    FuturesOutcome.market_id,
                    FuturesOutcome.id,
                ).where(
                    FuturesOutcome.market_id.in_(all_market_ids),
                    FuturesOutcome.external_id.isnot(None),
                )
            )
            outcome_rows = outcome_result.all()

    ticker_to_ids: dict[str, tuple[int, int]] = {}
    for ext_id, market_id, outcome_id in outcome_rows:
        ticker_to_ids[ext_id.upper()] = (market_id, outcome_id)

    market_tickers = list(ticker_to_ids.keys())

    # #9484 — every other unsettled Kalshi contract, for PRICES only, on its own
    # connections (`app.tasks.ws_open_contracts`). Never added to
    # `market_id_by_ext` (the lifecycle map) or to `ticker_to_ids` (which the
    # #9418 admission watcher reads as "this event is subscribed"). A failed read
    # costs the arm, never the game slate.
    #
    # Also returns the #9484 EVENT BRIDGE — outcome → event for the admitted
    # game winners whose event is still to be decided (`ws_open_contracts`), so
    # the flush re-stamps their event blend like a slate leg's. Its own read
    # fails on its own: a failed bridge costs the blend re-stamp, never the
    # prices.
    async def read_open_contracts() -> tuple[
        dict[str, tuple[int, int]], dict[int, int], bool, bool,
    ]:
        if not open_contract_prices_enabled():
            return {}, {}, False, False
        try:
            async with get_task_session() as session:
                open_rows = (
                    await session.execute(kalshi_open_contract_stmt())
                ).all()
        except Exception:
            logger.exception(
                "Kalshi WS: open-contract admission read failed; "
                "streaming the linked slate only this run"
            )
            return {}, {}, True, False
        ids = open_contract_ticker_map(open_rows, ticker_to_ids)
        candidates = open_contract_event_candidates(open_rows, ticker_to_ids)
        if not candidates:
            return ids, {}, False, False
        try:
            async with get_task_session() as session:
                admitted = (
                    await session.execute(
                        open_contract_bridge_event_stmt(candidates.values())
                    )
                ).scalars().all()
        except Exception:
            logger.exception(
                "Kalshi WS: open-contract event-bridge read failed; "
                "streaming their prices without the event blend this run"
            )
            return ids, {}, False, True
        return ids, open_contract_event_bridge(candidates, admitted), False, False

    # Read up front ONLY when there is no game slate for the read to delay:
    # production's read takes ~2.8 s, and on the recycle path that would be
    # 2.8 s more of every live game without a socket. Otherwise it runs beside
    # the game socket (`admit_open_contracts` below).
    preread = None
    if not market_tickers:
        preread = await read_open_contracts()
        if not preread[0]:
            logger.info("Kalshi WS: no live/upcoming linked markets")
            _report_liveness("kalshi", "no_markets", legs=0)
            return {"status": "no_markets"}

    logger.info(
        "Kalshi WS: %d tickers (%d events)", len(market_tickers), len(event_tickers),
    )

    stats = {
        "tickers_subscribed": len(market_tickers),
        "price_updates": 0,
        "flushes": 0,
        "settlements": 0,
        "errors": 0,
        # Q491: prices a failed flush put BACK on the buffer instead of dropping.
        # `errors` alone cannot distinguish a retried batch from a lost one.
        "requeued": 0,
        # Q491 repair: the final drain retries instead of requeueing, because
        # nothing runs after it. These two separate "we had to try again" from
        # "we gave up and a price is gone".
        "final_flush_retries": 0,
        "final_flush_dropped": 0,
        # #5411: buffered prices the settled-row guard REFUSED to write. Counted
        # separately from `price_updates` so a refusal is a number and not an
        # absence — "it returned" is not "it wrote" (gotcha #53). A refusal is
        # terminal, not an error: the entry leaves the buffer like any other.
        "settled_declined": 0,
        # #9484: rows a flush wrote whose price and book were already what it
        # stored — written (liveness), but no market invalidation sent.
        "quotes_unchanged": 0,
        # #6598 / CERT-3182: rows whose `rank` a flush corrected. This socket
        # moves `current_probability` faster than anything else in the system
        # and had never heard of the column derived from it, so a favourite
        # changing hands mid-game left the board ordered by the last REST poll.
        # Counted unconditionally — the re-derivation is a no-op on a field that
        # did not cross, so 0 is the healthy reading and absence is the failure.
        "ranks_rederived": 0,
        # #9484: the open-contract arm. `open_contract_prices_written` counts
        # rows that TOOK a price, so "the arm is subscribed" and "the arm is
        # moving stored prices" are two numbers, not one.
        "open_contract_tickers": 0,
        "open_contract_connections": 0,
        "open_contract_admission_error": False,
        "open_contract_prices_written": 0,
        # #10022: open-contract legs the socket GRADED from a lifecycle frame,
        # and boards that grade closed. Frames for an open contract that
        # declared no gradeable side (scalar, "", closed) are counted, not
        # silently skipped — they stay with the REST sweep.
        "open_contract_settlements": 0,
        "open_contract_markets_resolved": 0,
        "open_contract_lifecycle_unverdicted": 0,
        # #9484 event bridge: admitted game-winner outcomes (and their distinct
        # events) whose flushed price re-stamps the event blend. 0 with no
        # error is "no such contract this run", not a failure.
        "open_contract_bridged_outcomes": 0,
        "open_contract_bridged_events": 0,
        "open_contract_bridge_error": False,
    }

    # -- Buffered price updates --
    # outcome_id → (probability, yes_bid, yes_ask). #8753: the book travels WITH
    # the price it produced, so the row the flush writes is one instant's quote —
    # price and book together — and never a socket price beside a REST book.
    price_buffer: dict[int, tuple[float, float | None, float | None]] = {}
    buffer_lock = asyncio.Lock()
    # Q460: outcome → linked event, for the blend re-stamp after each flush.
    event_id_by_outcome: dict[int, int] = {
        outcome_id: event_id_by_market[market_id]
        for market_id, outcome_id in ticker_to_ids.values()
        if market_id in event_id_by_market
    }
    # #6598 / CERT-3182: outcome → its market, for the field re-rank after each
    # flush. Taken from the subscription map that is already in memory rather
    # than read back per flush — this runs every `PRICE_FLUSH_SECONDS`, and a
    # lookup query on that cadence is a cost the socket does not have to pay.
    market_id_by_outcome: dict[int, int] = {
        outcome_id: market_id for market_id, outcome_id in ticker_to_ids.values()
    }
    # #9484: filled IN PLACE by `admit_open_contracts`, which the handlers and
    # the flush read through these same objects.
    open_contract_ids: dict[str, tuple[int, int]] = {}
    open_contract_outcome_ids: set[int] = set()
    blend_refresher = LiveBlendRefresher(
        "kalshi", session_factory=get_task_session,  # #2471
    )
    # #10090 — the receipt Polymarket has carried since #837: every accepted
    # input is marked (seq, receive instant) as it is buffered, so the
    # per-minute delivery receipt can say what this game received and which
    # published revision carried it. Keyed like `price_buffer`.
    tail_receipts = TailReceipts("kalshi")
    blend_refresher.receipts = tail_receipts
    input_marks: dict = {}
    # #9462 review: stamps the previous run still owed when it recycled. Its
    # prices are already stored; the first flush below stamps them.
    stats["blend_pending_adopted"] = adopt_handed_off(blend_refresher)

    async def flush_prices(flush_started=None):
        """Write buffered price updates to DB — #10640: game markets first.

        Returns False when a write failed (its rows stay buffered and the
        cadence waits a full interval before retrying); #10090
        ``flush_started`` is this flush's start, for the refresher's floor.

        #10640 — the batch is split by `linked_first_phases`. The game phase is
        written, committed, published, acknowledged and its blends refreshed
        BEFORE the unrelated phase opens its transaction, so a held or failed
        futures/prop write can neither delay nor undo a committed game price.
        Each phase keeps every rule below on its own rows. A failed game phase
        stops the flush with the whole batch retained, as before.
        """
        async with buffer_lock:
            batch = dict(price_buffer)
            batch_marks = {
                oid: input_marks[oid] for oid in batch if oid in input_marks
            }
        if not batch:
            # #837 tail — a flush with no new prices still owes the stamps a row
            # lock deferred: those prices are already stored, so waiting for the
            # next venue tick would strand them on a quiet market. Free when
            # nothing is queued (no session is opened).
            await blend_refresher.refresh_pending(flush_started=flush_started)
            return True
        # Q491 repair 2 (CERT-659 BLOCK) — THE BUFFER IS DELIBERATELY *NOT*
        # CLEARED HERE. Draining first and putting the batch back on failure
        # only covers the failures you thought to catch, and two rounds of certs
        # found two we had not: `except Exception` never sees `CancelledError`
        # (it is a BaseException), so a recycle cancelling `flush_loop` between
        # the drain and the write lost the batch with `errors=0, requeued=0` —
        # invisible. Entries are now removed ONLY after the write lands, so no
        # failure mode — exception, cancellation, or a hard kill between the two
        # — can lose a price the buffer was holding. Nothing needs to be
        # "put back", because it was never taken away.
        phases = linked_first_phases(
            batch, market_id_by_outcome, event_id_by_outcome,
        )
        for index, phase in enumerate(phases):
            declined = 0
            written_outcome_ids: list[int] = []
            try:
                async with get_task_session() as session:
                    for outcome_id, (prob, yes_bid, yes_ask) in phase.items():
                        # #8753: the book columns move only when the tick carried
                        # BOTH sides; otherwise each is set to itself (a no-op). Half
                        # a book beside the other half from an older REST poll is a
                        # quote nobody ever offered. Spelled as keywords, not a
                        # splat, so the #4958 writer scan can read the mapping.
                        tick_has_book = yes_bid is not None and yes_ask is not None
                        result = await session.execute(
                            # #9484: the TABLE, not the entity. An ORM-enabled
                            # UPDATE ... RETURNING comes back as an ORM result with
                            # no `rowcount`, and the #5411 guard below reads it;
                            # the Core form keeps the CursorResult (asyncpg sets
                            # its rowcount from the command status) and returns
                            # the rows that actually took the price.
                            update(FuturesOutcome.__table__)
                            .where(
                                FuturesOutcome.id == outcome_id,
                                # #5411 — A SETTLED CONTRACT HAS NO LIVE PRICE. It is
                                # worth exactly 1 or 0, and #5246 made every reachable
                                # settlement writer say so. This socket had never heard
                                # of settlement: it wrote `current_probability`
                                # unconditionally, so 189 of the 6,895 rows that
                                # repair cleared were re-priced within 55 minutes (one
                                # burst, 22:48-22:52Z on 9/11) and eliminated players
                                # went back to showing a live number. The invariant was
                                # enforced on ENTRY and not on UPDATE.
                                #
                                # The refusal is the TIER-3 set, not `IS NOT NULL`, and
                                # the distinction is the whole correctness of it: the
                                # two live US Open finalists carry `ungradeable_result`
                                # (tier 1 — a RETRACTION meaning the venue never called
                                # it, explicitly reversible by evidence), so refusing
                                # every graded-looking row would have FROZEN the two
                                # rows that most need to move. Guess-family and NULL
                                # rows stay writable for the same reason.
                                #
                                # `or_` with an explicit NULL arm because the column is
                                # nullable and `NOT IN (...)` is NULL — not TRUE — for
                                # a NULL source, which would silently refuse every
                                # ungraded row in the book.
                                #
                                # Mirrors `polymarket_ws`'s `is_authoritative` skip
                                # (its line 84); that socket has always had this guard
                                # and this one has not, which is why the two behaved
                                # differently on the same class of row.
                                or_(
                                    FuturesOutcome.resolution_source.is_(None),
                                    FuturesOutcome.resolution_source.notin_(
                                        sorted(AUTHORITATIVE_SOURCES)
                                    ),
                                ),
                            )
                            .values(
                                current_probability=prob,
                                # This socket IS a live writer of this row, so it
                                # owes both stamps the polls owe (#2024). Without
                                # `last_updated` the playoff grid's liveness gate
                                # read actively-streaming rows as days stale —
                                # measured 2026-08-30 at up to 23 days on rows whose
                                # price had moved seconds earlier.
                                last_updated=func.now(),
                                price_changed_at=price_changed_at_value(
                                    FuturesOutcome.current_probability,
                                    FuturesOutcome.price_changed_at,
                                    prob,
                                ),
                                current_yes_bid=(
                                    yes_bid
                                    if tick_has_book
                                    else FuturesOutcome.current_yes_bid
                                ),
                                current_yes_ask=(
                                    yes_ask
                                    if tick_has_book
                                    else FuturesOutcome.current_yes_ask
                                ),
                            )
                            .returning(
                                FuturesOutcome.id,
                                FuturesOutcome.market_id,
                                FuturesOutcome.last_updated,
                                quote_moved_column(
                                    FuturesOutcome.__table__,
                                    (yes_bid, yes_ask) if tick_has_book else None,
                                ),
                            )
                        )
                        # #5411 — a settled row matches the id and fails the guard, so
                        # the statement affects 0 rows. (A row deleted between
                        # subscription and flush lands here too; both are honestly "a
                        # buffered price that did not become a stored price", which is
                        # what this counter is named for.)
                        if result.rowcount == 0:
                            declined += 1
                        else:
                            written_outcome_ids.append(outcome_id)
                        # #9484: one market invalidation per row the UPDATE
                        # RETURNED, stamped with the stored `last_updated` — never
                        # the buffered id, never a local clock. A #5411 refusal or
                        # a deleted row returns nothing, so it signals nothing.
                        # Staged against this transaction; published below only
                        # once the outer commit has landed.
                        #
                        # And only when the write changed what a reader is served
                        # (price or book, `quote_moved_column`). A tick that only
                        # re-stamped `last_updated` (volume, open interest, the
                        # same quote again) still writes — liveness reads that
                        # stamp — but a frame for it sends every held page to
                        # re-read an unchanged row (ux, #9526).
                        for row in result.all():
                            if not row.quote_moved:
                                stats["quotes_unchanged"] += 1
                                continue
                            queue_market_change(
                                session,
                                market_id=row.market_id,
                                source="kalshi",
                                outcome_observed_at={row.id: row.last_updated},
                            )

                    # #6598 / CERT-3182. `rank` is derived from the price this loop
                    # just moved, and nothing in this module has ever written it —
                    # so a favourite changing hands mid-game left the board numbered
                    # by whichever REST poll last saw it, on the exact rows this
                    # socket exists to keep current.
                    #
                    # KEYED ON THE ROWS THAT ACTUALLY WROTE, not on the batch: a
                    # settled row declined by the #5411 guard changed nothing, and
                    # re-deriving its market's field would be this socket reaching a
                    # board it was just refused. Same session, so it lands in the
                    # transaction that carries the prices.
                    reranked_markets = {
                        market_id_by_outcome[oid]
                        for oid in written_outcome_ids
                        if oid in market_id_by_outcome
                    }
                    if reranked_markets:
                        stats["ranks_rederived"] += (
                            await session.execute(
                                rerank_market_fields_stmt(sorted(reranked_markets))
                            )
                        ).rowcount
                if index == 0:
                    stats["flushes"] += 1
                stats["price_updates"] += len(phase) - declined
                stats["settled_declined"] += declined
                stats["open_contract_prices_written"] += sum(
                    1 for oid in written_outcome_ids
                    if oid in open_contract_outcome_ids
                )
            except Exception:
                # Q491 — the batch is still in `price_buffer`, so the next flush
                # retries it. Before Q491 the buffer was drained up front and a
                # failed write discarded those prices outright: the socket only
                # refills an outcome when that market ticks again, and 86.7% of open
                # Polymarket markets never tick, so one transient error left the
                # card on its old number with a stale `last_updated` (#2024).
                #
                # #10640: what is unpaid is this phase and every later one — a
                # committed game phase is already acknowledged and stays done.
                unpaid = sum(len(p) for p in phases[index:])
                stats["errors"] += 1
                stats["requeued"] += unpaid
                logger.exception(
                    "Kalshi WS: flush error (%d updates retained for retry)", unpaid
                )
                return False

            # #9484 — the commit landed, so the rows it carried may now say so on
            # `live:market:{id}`. Before the buffer bookkeeping and the blend
            # refresh, so neither can suppress it: a standalone future or prop has
            # no event blend, and its moved quote is just as real.
            await blend_refresher.publish_market_changes(session)

            # Q491 repair 2 — the write landed, so and only so do these entries
            # leave the buffer. The `== prob` test is what used to be `setdefault`:
            # `handle_ticker` may have buffered a FRESHER price for the same outcome
            # while this write was in flight, and that newer value is the truth, so
            # it must survive to the next flush rather than be dropped as "already
            # written". Same contract, enforced at removal instead of at re-queue.
            async with buffer_lock:
                for outcome_id, entry in phase.items():
                    if price_buffer.get(outcome_id) == entry:
                        del price_buffer[outcome_id]

            # Q460 — THE SHIP. Prices in `futures_outcomes` are invisible; the card
            # renders `Event.win_probability_sources`. Push the freshly-flushed
            # prices through to that blend so the number on screen moves with the
            # action instead of waiting for the next 120s poll. Failures are counted
            # inside the refresher and never interrupt streaming. #10090: the
            # revisions this write committed ride into this refresh, and only this
            # one (a settled row the #5411 guard declined committed nothing).
            #
            # #10640: the game phase refreshes (with every owed retry, exactly as
            # the single transaction did) BEFORE the unrelated phase is written.
            # That phase has no linked event by construction, so it refreshes
            # only if the #9484 bridge named one of its rows since the split.
            linked_events = event_ids_for_outcomes(event_id_by_outcome, phase.keys())
            if index == 0 or linked_events:
                with contextlib.suppress(Exception):
                    tail_receipts.stage(
                        [
                            batch_marks[oid]
                            for oid in written_outcome_ids if oid in batch_marks
                        ]
                    )
                await blend_refresher.refresh(
                    linked_events, flush_started=flush_started,
                )
        return True

    async def drain_prices():
        """The LAST flush of this consumer's life — retry, never requeue.

        Q491 repair (CERT-654 BLOCK). `flush_prices` hands a failed batch back to
        `price_buffer` so the next periodic flush retries it. At recycle and at
        shutdown there IS no next flush, so that requeue is a silent drop — the
        certifier's exact-head probe read `writes=[]`, `errors=1`, `requeued=1`.
        Here we call `flush_prices` again instead, up to `FINAL_FLUSH_ATTEMPTS`,
        each attempt on a fresh session.

        Every attempt after the first is counted, so a dyno that routinely needs
        them is visible rather than merely quiet.
        """
        try:
            for attempt in range(FINAL_FLUSH_ATTEMPTS):
                await flush_prices()
                async with buffer_lock:
                    if not price_buffer:
                        return
                if attempt + 1 < FINAL_FLUSH_ATTEMPTS:
                    stats["final_flush_retries"] += 1
        except asyncio.CancelledError:
            # Q491 repair 2: a hard cancel during the LAST drain. The
            # cancellation must keep travelling (CERT-491 — swallowing it makes
            # the runner relaunch a consumer the process is stopping), but the
            # prices it strands must be REPORTED on the way out rather than
            # vanishing at the silent `errors=0, requeued=0` CERT-659 measured.
            stranded = len(price_buffer)
            if stranded:
                stats["final_flush_dropped"] += stranded
                logger.error(
                    "Kalshi WS: %d price updates STRANDED by cancellation "
                    "during the final drain — these are lost, not deferred",
                    stranded,
                )
            raise
        async with buffer_lock:
            stranded = len(price_buffer)
        if stranded:
            # Loud: this is the one place a price genuinely cannot be retried
            # again, so it must never be inferable only from a silence.
            stats["final_flush_dropped"] += stranded
            logger.error(
                "Kalshi WS: %d price updates STRANDED after %d final-flush "
                "attempts — these are lost, not deferred",
                stranded, FINAL_FLUSH_ATTEMPTS,
            )

    def _parse_dollar(val) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    async def handle_ticker(msg: dict):
        ticker = (msg.get("market_ticker") or msg.get("ticker", "")).upper()
        ids = ticker_to_ids.get(ticker) or open_contract_ids.get(ticker)
        if not ids:
            return

        _, outcome_id = ids
        # #10090 — a message for this game's contract, before the price policy.
        with contextlib.suppress(Exception):
            tail_receipts.note_raw(event_id_by_outcome.get(outcome_id))

        last_price = _parse_dollar(msg.get("price_dollars"))
        yes_bid = _parse_dollar(msg.get("yes_bid_dollars"))
        yes_ask = _parse_dollar(msg.get("yes_ask_dollars"))

        # #8753 — THE REST WRITER'S RULE, CALLED, NEVER RE-SPELLED. This used to
        # store the last trade whenever there was one, so a trade the live book
        # had already moved past became the stored price between polls: on
        # `/events/15315945` (Northwestern @ Indiana, live) the socket stored
        # Indiana "scores first TD" at 0.96 above its own 0.95 ask, and the
        # three exclusive legs of that card summed to 139%. The poll that wrote
        # the same row two minutes earlier would have stored the 0.77 midpoint;
        # the socket, being faster, won every time. One price policy per venue:
        # tight book → midpoint, else a trade the book does not refute, else a
        # longshot ask, else nothing (a wide book with no trade is not a price).
        prob = _kalshi_yes_probability(yes_bid, yes_ask, last_price)
        # The socket's historical open bounds, kept: a terminal 0 or 1 is
        # settlement's to write (`handle_lifecycle`), never a streamed tick's.
        if prob is None or not 0 < prob < 1:
            return

        async with buffer_lock:
            price_buffer[outcome_id] = (prob, yes_bid, yes_ask)
            # Under the lock, so seq order is buffer order. Never raises into
            # the socket: a receipt is evidence about the price, not the price.
            try:
                mark = tail_receipts.note_input(
                    event_id_by_outcome.get(outcome_id), outcome_id, prob, "ticker",
                )
            except Exception:
                mark = None
            if mark is not None:
                input_marks[outcome_id] = mark

    async def handle_open_contract_lifecycle(ticker: str, msg: dict):
        """#10022: one open-contract leg, graded by its own frame — never the
        two-sided write below (see `ws_open_contracts`)."""
        if not open_contract_settlement_enabled():
            return  # the undo line: prices only, settlement left to REST
        verdict = lifecycle_verdict(msg)
        if verdict is None:
            stats["open_contract_lifecycle_unverdicted"] += 1
            return
        market_id, outcome_id = open_contract_ids[ticker]
        try:
            async with get_task_session() as session:
                graded, resolved = await grade_open_contract_leg(
                    session, market_id=market_id, outcome_id=outcome_id,
                    state=lifecycle_state(msg), result=msg.get("result"),
                )
                if graded is not None:
                    queue_market_change(
                        session,
                        market_id=market_id,
                        source="kalshi",
                        outcome_observed_at={graded.id: graded.last_updated},
                    )
                if resolved is not None:
                    queue_market_change(
                        session,
                        market_id=resolved.id,
                        source="kalshi",
                        outcome_observed_at={},
                        terminal=True,
                        updated_at=resolved.settled_at,
                    )
            if graded is None:
                return
            # A tick still buffered for this leg would be refused by the
            # #5411 guard anyway; dropping it keeps the count honest.
            async with buffer_lock:
                price_buffer.pop(outcome_id, None)
            stats["open_contract_settlements"] += 1
            if resolved is not None:
                stats["open_contract_markets_resolved"] += 1
            await blend_refresher.publish_market_changes(session)
            logger.info(
                "Kalshi WS: open contract %s graded (won=%s, market %d%s)",
                ticker, verdict[1], market_id,
                " resolved" if resolved is not None else "",
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: open-contract settlement error for %s", ticker)

    async def handle_shard_lifecycle(msg: dict):
        """An open-contract connection grades its own legs and nothing else: a
        linked-slate frame is the game socket's to handle, exactly once."""
        ticker = (msg.get("market_ticker") or "").upper()
        if ticker in open_contract_ids and ticker not in ticker_to_ids:
            await handle_open_contract_lifecycle(ticker, msg)

    async def handle_lifecycle(msg: dict):
        ticker = (msg.get("market_ticker") or "").upper()
        status = msg.get("status", "")
        result = msg.get("result")

        # #10022: an open contract is never in the lifecycle map (its event
        # ticker is not the linked slate's), so it is routed before the
        # two-sided handler can see it. `open_contract_ids` already excludes
        # every ticker the linked slate carries.
        if ticker in open_contract_ids and ticker not in ticker_to_ids:
            await handle_open_contract_lifecycle(ticker, msg)
            return

        # CAL-P049 (#1818): this writes FuturesMarket.status='resolved', so it is
        # the same class as the poll's inverted tuple — it missed ``determined``.
        # Reads the one measured set now (app/utils/kalshi_market_status.py).
        if not is_terminal(status):
            return

        parts = ticker.rsplit("-", 1)
        if len(parts) < 2:
            return
        event_ticker = parts[0]
        if event_ticker not in market_id_by_ext:
            return

        market_id = market_id_by_ext[event_ticker]

        # Capture closing price from the buffer before flushing
        async with buffer_lock:
            ids = ticker_to_ids.get(ticker)
            buffered = price_buffer.get(ids[1]) if ids else None
            closing_price = buffered[0] if buffered else None

        try:
            async with get_task_session() as session:
                settled = (
                    await session.execute(
                        update(FuturesMarket)
                        .execution_options(synchronize_session=False)
                        .where(FuturesMarket.id == market_id)
                        .values(
                            status="resolved",
                            **settled_values(FuturesMarket.settled_at),
                        )
                        .returning(FuturesMarket.id, FuturesMarket.settled_at)
                    )
                ).first()
                # #9484: the terminal invalidation carries the stored
                # `settled_at` this write returned, and only if it returned
                # one. It mirrors exactly what REST will now serve for the
                # market; clients refetch and apply their settlement guards.
                if settled is not None:
                    queue_market_change(
                        session,
                        market_id=settled.id,
                        source="kalshi",
                        outcome_observed_at={},
                        terminal=True,
                        updated_at=settled.settled_at,
                    )

                if result in ("yes", "no"):
                    is_winner = result == "yes"
                    # Set is_winner on the settling outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id == ticker,
                        )
                        .values(
                            is_winner=is_winner,
                            calibration_probability=closing_price,
                        )
                    )
                    # Set is_winner=False on the opposite outcome
                    await session.execute(
                        update(FuturesOutcome)
                        .where(
                            FuturesOutcome.market_id == market_id,
                            FuturesOutcome.external_id != ticker,
                        )
                        .values(
                            is_winner=not is_winner,
                            calibration_probability=(
                                1.0 - closing_price if closing_price else None
                            ),
                        )
                    )

            stats["settlements"] += 1
            await blend_refresher.publish_market_changes(session)
            logger.info(
                "Kalshi WS: %s settled (result=%s, closing=%.3f)",
                ticker, result, closing_price or 0,
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Kalshi WS: settlement error for %s", ticker)

    ws.on_ticker = handle_ticker
    ws.on_lifecycle = handle_lifecycle

    # -- Periodic flush task --
    # #10090: start to start, so the flush's own work is not added to the
    # interval; see `run_flush_cadence` for what it preserves.
    async def flush_loop():
        await run_flush_cadence(flush_prices, PRICE_FLUSH_SECONDS)

    # -- Periodic stats logging --
    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            # Q504-b: the blend counters ride along. `stamped` and `no_reading`
            # are the difference between "the socket is delivering prices" and
            # "the number on the card is moving", and on 2026-09-01 only the
            # first of those was observable — the fast lane was streaming
            # 10,098 prices into `futures_outcomes` while every tennis event's
            # last mile returned None, invisibly, for hours.
            blend = blend_refresher.stats
            logger.info(
                "Kalshi WS: %d updates, %d flushes, %d settlements, %d errors, "
                "%d msgs | blend stamped=%d no_reading=%d throttled=%d errors=%d "
                "lock_skipped=%d unobserved=%d stale=%d",
                stats["price_updates"], stats["flushes"],
                stats["settlements"], stats["errors"],
                ws.stats.get("messages", 0),
                blend["stamped"], blend["no_reading"],
                blend["throttled"], blend["errors"],
                blend.get("lock_skipped", 0),
                blend.get("unobserved_skipped", 0),
                # #8910: readings refused as older than the stored observation.
                blend.get("stale_readings_refused", 0),
            )
            _report_liveness(
                "kalshi", "streaming" if ws.is_connected else "disconnected",
                legs=len(market_tickers),
                msgs=ws.stats.get("messages", 0),
                stamped=blend["stamped"],
                no_reading=blend["no_reading"],
            )

    flush_task = asyncio.create_task(flush_loop())
    stats_task = asyncio.create_task(stats_loop())

    # #9484: the open-contract connections, admitted beside the game socket and
    # torn down in the `finally` on every exit path. #10022: they also carry
    # `market_lifecycle_v2`, routed to the PER-LEG grader (never the two-sided
    # handler — see `ws_open_contracts`).
    open_contract_sockets = []
    open_contract_tasks = []

    async def admit_open_contracts():
        ids, bridge, failed, bridge_failed = (
            preread if preread is not None else await read_open_contracts()
        )
        stats["open_contract_admission_error"] = failed
        stats["open_contract_bridge_error"] = bridge_failed
        # #9484: their event is re-stamped after a flush exactly like a slate
        # leg's (`event_ids_for_outcomes` in `flush_prices`). Never overwrites a
        # slate entry — the map excluded every ticker the slate carries.
        for outcome_id, event_id in bridge.items():
            event_id_by_outcome.setdefault(outcome_id, event_id)
        stats["open_contract_bridged_outcomes"] = len(bridge)
        stats["open_contract_bridged_events"] = len(set(bridge.values()))
        # An open contract's field is re-ranked like a linked one's.
        market_id_by_outcome.update(
            (outcome_id, market_id) for market_id, outcome_id in ids.values()
        )
        open_contract_outcome_ids.update(oid for _, oid in ids.values())
        open_contract_ids.update(ids)
        shards = shard_tickers(ids)
        stats["open_contract_tickers"] = len(ids)
        stats["open_contract_connections"] = len(shards)
        for shard in shards:
            sock = KalshiWebSocket()
            sock.on_ticker = handle_ticker
            sock.on_lifecycle = handle_shard_lifecycle
            open_contract_sockets.append(sock)
            open_contract_tasks.append(
                asyncio.create_task(
                    sock.run(market_tickers=shard, channels=open_contract_channels())
                )
            )
        if ids:
            logger.info(
                "Kalshi WS: %d open-contract tickers over %d connection(s)",
                len(ids), len(shards),
            )

    admission_task = asyncio.create_task(admit_open_contracts())

    _report_liveness("kalshi", "subscribing", legs=len(market_tickers))

    # #9462 review: the markets with a ticker on the wire. A market row that
    # exists without an outcome ticker (or gained its winner market after the
    # slate was read) is not among them.
    legged_market_ids = {market_id for market_id, _ in ticker_to_ids.values()}

    # #9418: the slate's live arm, re-read while the socket runs. Same source,
    # same join and same status test as the slate above, so it can only name an
    # event that turned live after the slate was read.
    # #9462 review: read per MARKET, beside the reading the card renders, so
    # an event counts as subscribed only when the leg that feeds its displayed
    # number has a ticker here (`unadmitted_live_events`).
    async def load_unadmitted_live_event_ids():
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesMarket.event_id,
                    FuturesMarket.id,
                    Event.win_probability_sources["kalshi"],
                )
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "kalshi",
                    FuturesMarket.event_id.isnot(None),
                    Event.status == "live",
                )
                .distinct()
            )
            return unadmitted_live_events(result.all(), legged_market_ids)

    try:
        # Q460: RECYCLE, don't run forever. The subscription list above is built
        # ONCE, from events that are live or start within 6 hours, and `ws.run`
        # reconnects internally without ever rebuilding it — so a socket that
        # stays healthy keeps yesterday's slate. Heroku cycles this dyno about
        # daily, which means a restart at (say) 11:17am subscribes nothing that
        # starts after 5:17pm, and every evening game silently misses the fast
        # lane. Returning on a timer hands control back to `run_kalshi_ws.py`,
        # which re-invokes this function and re-reads the slate.
        #
        # #9418: the timer is the ceiling, not the only door. A live event the
        # slate missed ends the run early through the same cancellation.
        admitted = await asyncio.wait_for(
            run_until_admission(
                # #9484: an EMPTY ticker list means "every market, both
                # channels" to `KalshiWebSocket.run`, so a run whose linked
                # slate is empty (open contracts only) opens no game socket
                # and simply waits out the recycle.
                (
                    ws.run(market_tickers=market_tickers)
                    if market_tickers
                    else asyncio.Event().wait()
                ),
                watch_for_unadmitted_live_events(
                    load_unadmitted_live_event_ids,
                    event_id_by_market.values(),
                    arm="Kalshi",
                    started_at=run_started_at,
                ),
            ),
            timeout=SUBSCRIPTION_REFRESH_SECONDS,
        )
        if admitted:
            stats["status"] = "resubscribe"
            stats["recycle_reason"] = "admission"
            stats["admitted_event_ids"] = sorted(admitted)[:20]
            logger.info(
                "Kalshi WS: %d live event(s) without a mapped leg for their rendered "
                "price, recycling early: %s",
                len(admitted), sorted(admitted)[:20],
            )
    except asyncio.TimeoutError:
        stats["status"] = "resubscribe"
    except asyncio.CancelledError:
        # Not the recycle — that arrives above as `TimeoutError` now that the
        # service loop propagates (CERT-491). This is a real shutdown, so it
        # must keep travelling: swallowing it would make `run_kalshi_ws.py`
        # sleep and relaunch a consumer the process is trying to stop. The
        # `finally` below still drains the buffer first.
        raise
    finally:
        flush_task.cancel()
        stats_task.cancel()
        # #9484: cancelled here, awaited only after the drain below, so a
        # second cancellation landing on that await can never skip the drain.
        admission_task.cancel()
        for task in open_contract_tasks:
            task.cancel()
        # Q491 repair (CERT-654 BLOCK): the last flush has no successor, so it
        # must RETRY rather than requeue into a buffer nobody will read again.
        try:
            await drain_prices()
        finally:
            # #9462 review: the drain returns once the price BUFFER is empty,
            # but a price it (or the last flush) committed inside the 2 s
            # throttle is still owed its blend stamp. The next run adopts it.
            stats["blend_pending_carried"] = hand_off_pending(blend_refresher)
            stats["open_contract_messages"] = sum(
                sock.stats.get("messages", 0) for sock in open_contract_sockets
            )
            # #10090: after the drain and hand-off, so the run's last stamps
            # are in the final minute's line.
            with contextlib.suppress(Exception):
                tail_receipts.close_all(
                    "recycle_reset" if stats.get("status") == "resubscribe"
                    else "exit"
                )
            await asyncio.gather(
                admission_task, *open_contract_tasks, return_exceptions=True,
            )

    logger.info("Kalshi WS consumer exiting: %s", stats)
    return stats


async def _run_kalshi_ws_shadow_consumer():
    """#836 Batch 2 (SHADOW): widened lifecycle-only grader that records its
    verdict to Redis (NEVER is_winner). Subscribes to ALL markets' settlement
    lifecycle (not the price `ticker` firehose) so every Kalshi settlement is
    graded in real time — into the shadow store, for the automated comparison.

    Runs ONLY when the `bainluck:ws_shadow_enabled` flag is on (deploy-dark).
    The authoritative `_run_kalshi_ws_consumer` is untouched and keeps owning
    `is_winner`.
    """
    from app.services.kalshi_ws import KalshiWebSocket
    from app.services.ws_shadow import (
        is_ws_shadow_enabled, verdict_from_lifecycle, record_shadow_verdict,
    )

    if not await is_ws_shadow_enabled():
        return {"status": "shadow_disabled"}

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    has_key = os.getenv("KALSHI_RSA_PRIVATE_KEY") or os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not api_key_id or not has_key:
        return {"status": "skipped", "reason": "no_credentials"}

    ws = KalshiWebSocket()
    stats = {"shadow_verdicts": 0, "errors": 0}

    async def handle_lifecycle_shadow(msg: dict):
        parsed = verdict_from_lifecycle(msg)
        if not parsed:
            return
        ticker, is_winner = parsed
        try:
            # SHADOW ONLY — keyed by the settled ticker's external_id; the
            # comparison joins FuturesOutcome.external_id == ticker exactly, so
            # no rsplit / event resolution is needed here.
            await record_shadow_verdict(ticker, is_winner)
            stats["shadow_verdicts"] += 1
        except Exception:
            stats["errors"] += 1

    ws.on_lifecycle = handle_lifecycle_shadow
    # lifecycle-only + all markets: settlement trickle, NOT the price ticker firehose
    try:
        await ws.run(channels=["market_lifecycle_v2"], subscribe_all=True)
    except asyncio.CancelledError:
        raise  # shutdown must stop the runner, not restart it (CERT-491)
    logger.info("Kalshi WS SHADOW consumer exiting: %s", stats)
    return stats
