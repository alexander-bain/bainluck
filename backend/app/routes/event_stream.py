"""Server-Sent Events for live and supported open-market event quotes.

Alex September 28: quotes follow open contracts, independently of game phase.
The scheduled/suspended increment uses the existing producer cohort; wider
markets and standalone quotes remain separate delivery work.

WHY THIS IS SMALL. The hard part shipped already. `worker-ws` streams Kalshi and
Polymarket prices, flushes every 2 s, and `LiveBlendRefresher` stamps the blend
into `Event.win_probability_sources` at most once per event per flush. The number
in the database is already live. What was NOT live was the number on the screen:
the client polled every 32 s, so a value 3 s old in Postgres could be 32 s old in
front of a user. This endpoint closes that gap and nothing else — it makes no
data fresher, it makes the fresh data *arrive*.

That is also why this file has no throttle of its own. The per-event cadence
is the refresher's, upstream (`DEFAULT_MIN_REFRESH_INTERVAL_S`: the 2026-08-30
ruling's "≤1 update/5 s", moved to one per 2 s flush for Alex's 2026-09-28 live
benchmark). A second timer in this file could only drift away from the first.

It shares the web dyno's event loop with `/api/feed`. Single-row frames remain
database-free after connection. Actual folded streams forward the raw update
immediately, then request a bounded compact authoritative quote shared across
recipients of that update. Projection never blocks the Redis fanout reader and
failure retains the existing invalidation/detail fallback. No full page or
history read belongs on this path.

AND IT MUST NOT OPEN A REDIS CONNECTION PER STREAM (#6515). It used to: the
uncached `get_async_redis_client()` lived inside `_stream`, so N readers meant N
pools and N sockets held for up to `MAX_CONNECTION_S`, against a plan limit of
80 connections shared by every process of both apps. `MAX_CONNECTIONS` below is
200 per worker, so this endpoint could exhaust the whole budget — and take the
feed cache, the rate limiter and the Celery workers down with it — long before
its own 503 gate could refuse anything. Subscriptions now come from the
process-wide `utils/live_fanout` hub: one connection, every stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket
from app.services.database import async_session_maker
from app.utils.blend_preview import is_preview_frame, preview_route_events
from app.utils.live_push import (
    MAX_FRAME_AGE_S, event_channel, latest_frames, parse_frame, sse_encode,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Heroku's router closes a connection idle for ~55 s. Two heartbeats inside
#: that window means one can be lost to a hiccup without killing the stream.
HEARTBEAT_INTERVAL_S = float(os.getenv("SSE_HEARTBEAT_INTERVAL_S", "20"))

#: Hard ceiling on one connection's life. The client reconnects, which keeps
#: reconnect a routine, continuously-exercised path instead of the path that
#: only ever runs during an incident — and bounds any per-connection leak to
#: this long rather than to the length of a match.
MAX_CONNECTION_S = float(os.getenv("SSE_MAX_CONNECTION_S", "900"))

#: Concurrent streams allowed per uvicorn worker. Over this, connect is refused
#: with 503 and the client polls. Refusing loudly is the whole point: the
#: alternative is degrading `/api/feed` for everyone, silently, under load.
#:
#: #6515: this number is a bound on THIS LOOP's fanout work, and since the hub
#: it is no longer a multiplier on Redis connections — the process holds one for
#: any number of streams. While each stream built its own pool, 200 here was a
#: promise the 80-connection budget could not keep, and the gate refused at a
#: number the server had passed 120 readers earlier.
MAX_CONNECTIONS = int(os.getenv("SSE_MAX_CONNECTIONS", "200"))

#: Reconnect delay handed to the client via the SSE `retry:` field.
RETRY_MS = int(os.getenv("SSE_RETRY_MS", "5000"))

#: How long one pass waits for a frame before rechecking the clock and the
#: client. It is the loop's tick, not a delivery deadline: a frame that arrives
#: mid-wait ends the wait immediately.
FRAME_WAIT_S = 1.0

#: Existing live connections remain compatible. New nonlive connections also
#: require a publishable, mapped winner market in the producer's cohort.
LIVE_STATUSES = frozenset({"live"})
QUOTE_STATUSES = frozenset({"live", "scheduled", "suspended"})

#: Per-worker connection count. A plain int on the worker process, not Redis:
#: it is a guard on THIS loop's capacity, and asking Redis how loaded we are
#: would add a network round trip to the connect path to answer a local
#: question.
_open_connections = 0


def _frame_is_fresh(frame: dict, now: datetime) -> bool:
    """Drop a frame that has aged past the useful window.

    A frame can only be this old if it sat buffered through a stall, and a
    stalled client's REST refetch has almost certainly already passed it. The
    visible symptom of forwarding one is the number animating BACKWARDS to a
    price the market has left — worse than showing nothing, because it looks
    like a real move.
    """
    stamp = frame.get("updated_at")
    if not stamp:
        return True
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() <= MAX_FRAME_AGE_S


async def _event_status(db: AsyncSession, event_id: int) -> Optional[str]:
    return (
        await db.execute(select(Event.status).where(Event.id == event_id))
    ).scalar_one_or_none()


def _in_kalshi_open_contract_bridge(market, now: datetime) -> bool:
    """A Kalshi game winner the open-contract arm carries AND bridges to its
    event's blend (#9484, `tasks/ws_open_contracts`), read from the row alone.

    Mirrors the arm's admission (unresolved — checked by the caller — no
    `settled_at`, not past `expiration_time`, no graded leg) and its bridge
    (the market ticker feeds the blend). `WS_OPEN_CONTRACT_PRICES=0` turns the
    arm off, so it turns this off too: a stream nobody publishes to is a
    connection that only ever heartbeats.
    """
    from app.tasks.ws_open_contracts import open_contract_prices_enabled
    from app.utils.prediction_market_matching import feeds_win_prob_blend

    if market.source != "kalshi" or not open_contract_prices_enabled():
        return False
    if not feeds_win_prob_blend(market.external_id):
        return False
    if market.settled_at is not None:
        return False
    expires = market.expiration_time
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            return False
    return all(o.is_winner is None for o in market.outcomes)


def _in_polymarket_open_contract_bridge(market) -> bool:
    """A Polymarket market the open-contract arm carries AND bridges to its
    event's blend (#10091, `tasks/polymarket_open_contracts`), from the row.

    Mirrors the arm's admission — unresolved (checked by the caller), no
    `settled_at`, no graded leg (`is_winner IS NOT TRUE` and no
    `resolution_source`: the column defaults FALSE, so a NULL test would call
    every ungraded leg graded) — and its bridge (the blend's class rule calls
    the market a game winner). `_has_mapped_winner` still asks the blend's full
    speaker admission and the persisted token mapping. Either undo flag turns
    the arm off, so it turns this off too.
    """
    from app.tasks.polymarket_open_contracts import open_contract_prices_enabled
    from app.utils.live_blend import _class_says_game_winner

    if market.source != "polymarket" or not open_contract_prices_enabled():
        return False
    if not _class_says_game_winner(market):
        return False
    if market.settled_at is not None:
        return False
    return all(
        o.is_winner is not True and o.resolution_source is None
        for o in market.outcomes
    )


def _market_in_quote_cohort(event, market, now: datetime) -> bool:
    """Current #9499 producer coverage, not a permanent venue-hours policy."""
    if event.completed_at is not None or market.source not in {"kalshi", "polymarket"}:
        return False
    if market.status == "resolved":
        return False
    if event.status == "live":
        return True
    start = event.commence_time
    if start is None:
        return False
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if event.status == "suspended":
        return start >= now - timedelta(hours=24)
    if event.status == "scheduled":
        if start > now + timedelta(hours=6):
            # #9484 / #10091: beyond the slate's horizon only the open-contract
            # arms' bridged game winners publish this event's blend.
            return _in_kalshi_open_contract_bridge(
                market, now
            ) or _in_polymarket_open_contract_bridge(market)
        return market.source == "kalshi" or start >= now - timedelta(hours=24)
    return False


def _mapped_outcome_ids(entry) -> set[int]:
    """Prove persisted producer mappings without venue I/O or token top-ups."""
    if entry.market.source == "kalshi":
        return {o.id for o in entry.outcomes if isinstance(o.external_id, str) and o.external_id.strip()}
    metadata = entry.market.market_metadata or {}
    if not isinstance(metadata, dict):
        return set()
    tokens = metadata.get("clob_token_ids") or metadata.get("clobTokenIds")
    if tokens:
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except (ValueError, TypeError):
                return set()
        # The producer pairs the entire ordered outcome list with this list.
        # Partial lists suppress its per-outcome top-up: never use that cache
        # to declare an unmapped tail eligible.
        if (not isinstance(tokens, list) or len(tokens) != len(entry.outcomes)
                or not all(isinstance(t, (str, int)) and not isinstance(t, bool)
                           and str(t).strip() for t in tokens)
                or len(set(map(str, tokens))) != len(tokens)):
            return set()
        return {o.id for o in entry.outcomes}
    cached = metadata.get("clob_yes_token_by_outcome")
    if not isinstance(cached, dict):
        return set()
    return {o.id for o in entry.outcomes
            if isinstance(cached.get(str(o.id)), (str, int))
            and not isinstance(cached[str(o.id)], bool)
            and str(cached[str(o.id)]).strip()}


def _has_mapped_winner(event, markets, now: datetime) -> bool:
    from app.utils.live_blend import MarketOutcomes, compute_source_home_probability

    for source in ("kalshi", "polymarket"):
        group = [MarketOutcomes(m, m.outcomes, event_has_result=False)
                 for m in markets if m.source == source and _market_in_quote_cohort(event, m, now)]
        reading = compute_source_home_probability(group, event.home_team_name, event.away_team_name)
        if reading is None:
            continue
        mapped = set().union(*(_mapped_outcome_ids(entry) for entry in group))
        contributors = reading.contributing_outcomes or (reading.outcome,)
        if contributors and all(o.id in mapped for o in contributors):
            return True
    return False


async def _nonlive_stream_eligible(db: AsyncSession, event_id: int, contributor_ids: list[int]) -> bool:
    """Bounded fold lookup before returning the session; never query per frame."""
    events = (await db.execute(select(Event).where(Event.id.in_(contributor_ids)))).scalars().all()
    canonical = next((event for event in events if event.id == event_id), None)
    if (canonical is None or canonical.completed_at is not None
            or canonical.status not in QUOTE_STATUSES):
        return False
    markets = (await db.execute(
        select(FuturesMarket).options(selectinload(FuturesMarket.outcomes)).where(
            FuturesMarket.event_id.in_(contributor_ids),
            FuturesMarket.source.in_(("kalshi", "polymarket")),
        )
    )).scalars().all()
    now = datetime.now(timezone.utc)
    return any(_has_mapped_winner(event, [m for m in markets if m.event_id == event.id], now)
               for event in events)


async def _fold_stream_ids(db: AsyncSession, event_id: int) -> list[int]:
    """Resolve detail's orientation-safe fold once, before releasing the DB.

    Include rows with removed sources: their next revision still invalidates
    the fold. Membership changes are picked up on stream reconnect.
    """
    from app.utils.proven_duplicates import folded_series_event_ids
    from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

    event = (await db.execute(
        select(Event).options(selectinload(Event.sport)).where(Event.id == event_id)
    )).scalar_one_or_none()
    if event is None:
        return [event_id]
    absorbed = await serve_fold_absorbed_rows(db, event)
    return await folded_series_event_ids(db, event_id, absorbed)


class _FoldSubscription:
    """Read contributor mailboxes concurrently through the existing shared hub."""

    def __init__(self, hub):
        self.hub = hub
        self.subscriptions = {}
        self.pending = {}

    async def subscribe(self, event_ids):
        watch = getattr(self.hub, "watch_confirmation", None)
        for event_id in dict.fromkeys(event_ids):
            subscription = await self.hub.subscribe(event_channel(event_id))
            self.subscriptions[event_id] = subscription
            if callable(watch):
                watch(subscription)

    async def next(self, timeout):
        if len(self.subscriptions) == 1:
            event_id, subscription = next(iter(self.subscriptions.items()))
            return event_id, await subscription.next(timeout=timeout)
        for event_id, subscription in self.subscriptions.items():
            if event_id not in self.pending:
                self.pending[event_id] = asyncio.create_task(subscription.next(timeout=timeout))
        done, _ = await asyncio.wait(
            self.pending.values(), timeout=timeout, return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            return None, None
        for event_id, task in list(self.pending.items()):
            if task in done:
                del self.pending[event_id]
                return event_id, task.result()
        return None, None  # pragma: no cover

    def release(self):
        # No await: cancellation must not strand any contributor subscription.
        for task in self.pending.values():
            task.cancel()
        for subscription in self.subscriptions.values():
            self.hub.release(subscription)


def _fold_invalidation(frame: dict, event_id: int, origin_id: int) -> Optional[dict]:
    """A sibling moved; reread the fold without relabeling its price or source."""
    rev = frame.get("rev")
    if (not isinstance(rev, dict) or set(rev) != {str(origin_id)}
            or type(rev[str(origin_id)]) is not int or rev[str(origin_id)] < 0):
        return None
    return {
        "event_id": event_id, "origin_event_id": origin_id, "invalidation": True,
        "p": None, "source": None, "source_value": None,
        "updated_at": frame.get("updated_at"), "rev": rev,
    }


def _origin_revision(frame: dict, origin_id: int) -> Optional[int]:
    rev = frame.get("rev")
    value = rev.get(str(origin_id)) if isinstance(rev, dict) else None
    return value if type(value) is int else None


async def _await_honouring_cancel(awaitable):
    """Await ``awaitable``; if this task was cancelled meanwhile, stay cancelled.

    Python 3.11's ``asyncio.wait_for`` (production and CI) returns the inner
    result and DROPS the outer ``CancelledError`` when the cancel lands in the
    same loop turn as the inner awaitable finishing (CPython gh-86296; 3.12
    rewrote it). Both of this stream's waits go through it — the replay MGET via
    ``bounded_redis_call`` and the hub mailbox via ``Subscription.next`` — so a
    leaving reader could keep its stream, and its hub refcount, until
    ``MAX_CONNECTION_S``. A swallowed cancel still leaves ``cancelling()`` raised,
    so compare it across THIS wait only: anything that cancels and properly
    uncancels (a timeout scope, Starlette's ``is_disconnected`` probe) nets zero.
    """
    task = asyncio.current_task()
    before = task.cancelling() if task is not None else 0
    result = await awaitable
    if task is not None and task.cancelling() > before:
        raise asyncio.CancelledError()
    return result



def _withdrawal_reconcile(frame: dict, event_id: int, origin_id: int):
    """Separate control admission from price freshness and price ordering."""
    control = frame.get("reconcile")
    if (not isinstance(control, dict)
            or type(frame.get("event_id")) is not int
            or type(control.get("event_id")) is not int
            or frame["event_id"] != origin_id
            or control["event_id"] != origin_id):
        return None
    custody = control.get("custody_id")
    floor = control.get("removal_rev")
    if (not isinstance(custody, str) or not 1 <= len(custody) <= 96
            or not isinstance(floor, dict) or set(floor) != {str(origin_id)}
            or type(floor[str(origin_id)]) is not int
            or not 0 <= floor[str(origin_id)] <= 9007199254740991
            or floor != frame.get("rev")):
        return None
    return {"event_id": event_id, "custody_id": custody, "removal_rev": floor}


async def _normal_recovery_quote(hub, event_id, frame, control):
    """Recover current committed authority; the separate control keeps history owed."""
    project = getattr(hub, "project_recovery_quote", None)
    if not callable(project):
        return None
    quote = await project(event_id, frame)
    if not isinstance(quote, dict) or quote.get("event_id") != event_id:
        return None
    if quote.get("status") not in QUOTE_STATUSES:
        return False
    revision = quote.get("blend_fold_revision")
    if not isinstance(revision, dict) or any(
        type(revision.get(eid)) is not int or revision[eid] < floor
        for eid, floor in control["removal_rev"].items()
    ):
        return None
    return {
        "event_id": event_id, "p": None, "source": None, "source_value": None,
        "status": quote["status"], "rev": revision,
        "folded_quote_pending": False, "folded_quote": quote,
    }


async def _current_reconcile(event_id: int, event_ids: list[int]):
    """One current-state coverage read on connect/confirmation/hub recovery.

    This is a recovery obligation, never a reader acknowledgement. Committed
    state covers earlier removals; a transaction committing later still needs
    its producer notification/recovery. No per-price query or new retention key.
    """
    import hashlib
    async with asyncio.timeout(1):
        async with async_session_maker() as db:
            rows = (await db.execute(select(
                Event.id, Event.win_probability_sources_rev,
            ).where(Event.id.in_(event_ids)))).all()
    floor = {str(eid): rev for eid, rev in rows
             if type(rev) is int and 0 <= rev <= 9007199254740991}
    if set(floor) != {str(eid) for eid in event_ids}:
        raise ValueError("incomplete reconciliation coverage")
    identity = json.dumps(floor, sort_keys=True, separators=(",", ":"))
    return {"event_id": event_id,
            "custody_id": "state:" + hashlib.sha256(identity.encode()).hexdigest(),
            "removal_rev": floor}


async def _stream(
    event_id: int, request: Request, contributor_ids: Optional[list[int]] = None,
) -> AsyncIterator[str]:
    """Yield SSE frames for one event until the client leaves or time is up."""
    global _open_connections

    from app.utils.live_fanout import CLOSED, CONFIRMED, Recovery, fanout

    hub = fanout()
    subscription = _FoldSubscription(hub)
    preview_on = event_id in preview_route_events()
    # Old readers treat a folded frame as a singleton claim. Require explicit
    # vector-aware admission support before sending provisional folded values.
    folded_preview_capable = (
        getattr(request, "query_params", {}).get("preview_protocol") in {"folded-v1", "folded-v2"}
    )
    started = asyncio.get_event_loop().time()
    _open_connections += 1
    initial_coverage = None
    recovery_coverage = None
    recovery_force = False
    pending_confirmations = set()
    pending_recovery = False
    next_frame = None
    recovery_quote = None
    pending_quote_control = None
    active_quote_control = None
    quote_retry_at = 0.0
    folded_projection = None
    projection_frame = None
    pending_projection = None
    preview_floors = {}
    active_preview_origin = None
    preview_session = None

    def update_preview_session(frame=None, elapsed_ms=0):
        if preview_session is None:
            return None
        get_base = getattr(hub, "folded_preview_base", None)
        base = (get_base(event_id, members=list(subscription.subscriptions))
                if callable(get_base) else None)
        return preview_session.update(
            base, floors=preview_floors, now=asyncio.get_event_loop().time(),
            frame=frame, elapsed_ms=elapsed_ms,
        )

    def note_floors(vector):
        if not isinstance(vector, dict):
            return
        members = {str(eid) for eid in subscription.subscriptions}
        for key, value in vector.items():
            if key in members and type(value) is int and 0 <= value <= 9007199254740991:
                preview_floors[key] = max(value, preview_floors.get(key, -1))

    def covers_floors(quote):
        if not isinstance(quote, dict):
            return False
        vector = quote.get("blend_fold_revision")
        return (isinstance(vector, dict)
                and set(vector) == {str(eid) for eid in subscription.subscriptions}
                and all(type(vector.get(key)) is int and vector[key] >= value
                        for key, value in preview_floors.items()))

    async def read_recovery(ids, confirmed):
        control = await _current_reconcile(event_id, ids)
        retained = (await _await_honouring_cancel(latest_frames(confirmed))) if confirmed else []
        return control, retained

    try:
        await subscription.subscribe([event_id, *(contributor_ids or [])])
        if (preview_on and len(subscription.subscriptions) > 1
                and getattr(request, "query_params", {}).get("preview_protocol") == "folded-v2"):
            from app.utils.folded_blend_preview_v2 import FoldedPreviewSession

            preview_session = FoldedPreviewSession(event_id, list(subscription.subscriptions))
        yield f"retry: {RETRY_MS}\n\n"
        yield sse_encode(json.dumps({
            "event_id": event_id,
            **({"fold_session": preview_session.session} if preview_session else {}),
        }), event="open")
        recovery_ids = list(subscription.subscriptions)
        # One owned read may finish after replay or live prices. Reconciliation
        # is an obligation, not permission to hold already committed prices.
        initial_coverage = asyncio.create_task(
            _current_reconcile(event_id, recovery_ids)
        )
        last_state_control = None

        # Replay immediately after initiating subscription, so the first frame
        # never waits on Redis. Redis may not have registered SUBSCRIBE yet,
        # and this read travels on another connection: a quote published
        # before Redis reads a late SUBSCRIBE is in neither place. The hub's
        # CONFIRMED, below, owes one more read of that channel (#10090).
        replay = deque(await _await_honouring_cancel(
            latest_frames([event_id, *(contributor_ids or [])])
        ))
        last_beat = started
        recovery_generation = 0
        # Highest revision already sent per origin: a catch-up read that finds
        # only what the open-time replay sent stays silent.
        sent_revision: dict[int, int] = {}
        # The last replayed frame per origin. A quote that is both retained and
        # already in flight on the channel arrives once by each path; the first
        # live frame after a replay is dropped only when it is that same frame.
        replayed: dict[int, dict] = {}
        while True:
            # The client going away is the common exit, and it is the one that
            # actually frees the slot — check it every pass, not just on send.
            if await request.is_disconnected():
                return
            if any(getattr(sub, "dropped", 0) for sub in subscription.subscriptions.values()):
                # A dropped obligation cannot be paid by later price traffic.
                # Reconnect owns a fresh coverage read; never heartbeat through
                # a silently lost control or launch per-drop database queries.
                yield sse_encode(json.dumps({"reason": "mailbox_overflow"}), event="reconnect")
                return
            loop_now = asyncio.get_event_loop().time()
            if loop_now - started >= MAX_CONNECTION_S:
                yield sse_encode(
                    json.dumps({"reason": "max_age"}), event="reconnect"
                )
                return

            projected_preview = update_preview_session()
            if projected_preview is not None:
                yield sse_encode(json.dumps(projected_preview), event="preview")

            if folded_projection is not None and folded_projection.done():
                quote = folded_projection.result()
                folded_projection = None
                if not covers_floors(quote):
                    quote = None
                yield sse_encode(json.dumps({
                    **projection_frame, "folded_quote_pending": False, "folded_quote": quote,
                }), event="folded_probability")
                projection_frame = None
            if folded_projection is None and pending_projection is not None:
                projection_frame, incoming_projection = pending_projection
                pending_projection = None
                folded_projection = asyncio.create_task(hub.project_folded_quote(event_id, incoming_projection))

            if recovery_quote is not None and recovery_quote.done():
                projected = recovery_quote.result()
                recovery_quote = None
                if projected is False:
                    yield sse_encode(json.dumps({"reason": "not_live"}), event="closed")
                    return
                if (preview_on and len(subscription.subscriptions) > 1
                        and projected is not None and not covers_floors(projected.get("folded_quote"))):
                    projected = None
                if projected is not None:
                    yield sse_encode(json.dumps(projected), event="folded_probability")
                else:
                    if pending_quote_control is None:
                        pending_quote_control = active_quote_control
                    quote_retry_at = loop_now + 0.25
                active_quote_control = None
            if (recovery_quote is None and pending_quote_control is not None
                    and loop_now >= quote_retry_at):
                active_quote_control = pending_quote_control
                recovery_frame, recovery_control = active_quote_control
                pending_quote_control = None
                recovery_quote = asyncio.create_task(_normal_recovery_quote(
                    hub, event_id, recovery_frame, recovery_control,
                ))

            if initial_coverage is not None and initial_coverage.done():
                control = initial_coverage.result()  # Failure still closes.
                initial_coverage = None
                note_floors(control.get("removal_rev"))
                if (preview_on and len(subscription.subscriptions) > 1
                        and pending_quote_control is None):
                    # Seed from the existing bounded recovery projector. The
                    # open/reconcile events and live mailbox do not wait on it.
                    pending_quote_control = ({
                        "event_id": event_id,
                        "rev": {str(event_id): control["removal_rev"][str(event_id)]},
                    }, control)
                yield sse_encode(json.dumps(control), event="reconcile")
                last_state_control = control["custody_id"]

            if recovery_coverage is not None and recovery_coverage.done():
                control, retained = recovery_coverage.result()  # Failure closes.
                recovery_coverage = None
                note_floors(control.get("removal_rev"))
                if preview_on and len(subscription.subscriptions) > 1:
                    # Rewarm even when no committed revision changed during
                    # reconnect. Retained-frame dedup must not strand previews.
                    origin, revision = next(iter(control["removal_rev"].items()))
                    pending_quote_control = ({
                        "event_id": int(origin), "rev": {origin: revision},
                    }, control)
                if recovery_force or control["custody_id"] != last_state_control:
                    yield sse_encode(json.dumps(control), event="reconcile")
                    last_state_control = control["custody_id"]
                for item in retained:
                    rev = _origin_revision(json.loads(item[1]), item[0])
                    if rev is not None and rev > sent_revision.get(item[0], -1):
                        replay.append(item)
            if recovery_coverage is None and (pending_recovery or pending_confirmations):
                # One extra owned read, independent of price drain. A repeated
                # confirmation/generation during this read stays pending for a
                # later read, so its post-registration boundary is not lost.
                confirmed = sorted(pending_confirmations)
                ids = recovery_ids if pending_recovery else confirmed
                recovery_force = pending_recovery
                pending_recovery = False
                pending_confirmations.clear()
                recovery_coverage = asyncio.create_task(read_recovery(ids, confirmed))

            # Bounded wait: this is what keeps the heartbeat on its clock even
            # when the market is completely silent, and what keeps this
            # coroutine yielding control back to the loop that is also serving
            # `/api/feed`.
            quote_wait = (min(FRAME_WAIT_S, max(0.001, quote_retry_at - loop_now))
                          if pending_quote_control is not None and recovery_quote is None else FRAME_WAIT_S)
            if preview_session is not None:
                quote_wait = preview_session.wait_seconds(loop_now, quote_wait)
            from_replay = bool(replay)
            if from_replay:
                origin_id, payload = replay.popleft()
            elif (next_frame is None and initial_coverage is None
                  and recovery_coverage is None and recovery_quote is None
                  and folded_projection is None):
                # Nothing owned can complete during this wait: keep the
                # parent's inline read, with no task or wait set per frame.
                origin_id, payload = await _await_honouring_cancel(
                    subscription.next(timeout=quote_wait)
                )
            else:
                # A completed coverage read must wake an otherwise quiet
                # stream. Keep the mailbox owner when a read wins the race:
                # cancelling it could consume and lose a simultaneous frame.
                if next_frame is None:
                    next_frame = asyncio.create_task(
                        subscription.next(timeout=quote_wait)
                    )
                waiting = {next_frame}
                waiting.update(task for task in (initial_coverage, recovery_coverage, recovery_quote, folded_projection)
                               if task is not None)
                done, _ = await _await_honouring_cancel(asyncio.wait(
                    waiting, return_when=asyncio.FIRST_COMPLETED,
                    timeout=quote_wait if (preview_session is not None or
                        (pending_quote_control is not None and recovery_quote is None)) else None
                ))
                if next_frame not in done:
                    continue
                origin_id, payload = next_frame.result()
                next_frame = None
            if payload is CONFIRMED:
                pending_confirmations.add(origin_id)
                continue
            if isinstance(payload, Recovery):
                # Fold subscriptions share a hub generation; emit it only once.
                if payload.generation > recovery_generation:
                    recovery_generation = payload.generation
                    forget = getattr(hub, "forget_folded_preview", None)
                    if callable(forget):
                        forget(event_id)
                    active_preview_origin = None
                    if preview_session is not None:
                        preview_session.reset()
                        projected_preview = update_preview_session()
                        if projected_preview is not None:
                            yield sse_encode(json.dumps(projected_preview), event="preview")
                    yield sse_encode(
                        json.dumps({"generation": recovery_generation}), event="resync"
                    )
                    pending_recovery = True
                continue
            if payload is CLOSED:
                # The shared reader stopped, so no frame will ever arrive on
                # this subscription again. Saying so is not optional: the
                # heartbeat below is generated HERE, not by Redis, so a stream
                # left running on a dead hub would look healthy forever while
                # the number on screen froze. `reconnect` is the event the
                # client already treats as a rollover, and reconnecting is what
                # rebuilds the hub.
                yield sse_encode(
                    json.dumps({"reason": "upstream"}), event="reconnect"
                )
                return
            if payload is not None:
                frame = parse_frame(payload)
                if frame is not None and is_preview_frame(frame):
                    from app.utils.live_fanout import mailbox_age_ms

                    elapsed_ms = mailbox_age_ms(payload)
                    # #10090: a provisional blend has no revision and is
                    # never a `probability` frame. Forwarded under its own
                    # event name only for a canary event's unfolded page;
                    # otherwise dropped, so no reader can take it for a
                    # committed price.
                    if (preview_on and origin_id == event_id
                            and frame.get("event_id") == event_id
                            and len(subscription.subscriptions) == 1):
                        yield sse_encode(json.dumps(frame), event="preview")
                    elif (preview_on and folded_preview_capable
                          and frame.get("event_id") == origin_id
                          and len(subscription.subscriptions) > 1):
                        if preview_session is not None:
                            projected_preview = update_preview_session(frame, elapsed_ms)
                            if projected_preview is not None:
                                yield sse_encode(json.dumps(projected_preview), event="preview")
                            continue
                        meta = frame.get("preview", {})
                        if meta.get("kind") == "revoke" and active_preview_origin == origin_id:
                            yield sse_encode(json.dumps({
                                **frame, "event_id": event_id,
                                "preview": {**meta, "origin_event_id": origin_id},
                            }), event="preview")
                        elif meta.get("kind") == "blend":
                            project_preview = getattr(hub, "project_folded_preview", None)
                            projected = project_preview(
                                event_id, frame, members=list(subscription.subscriptions), floors=preview_floors,
                                elapsed_ms=elapsed_ms,
                            ) if callable(project_preview) else None
                            if projected is not None:
                                active_preview_origin = origin_id
                                yield sse_encode(json.dumps(projected), event="preview")
                    continue
                if frame is not None and frame.get("event_id") == origin_id:
                    note_floors(frame.get("rev"))
                    if (preview_on and len(subscription.subscriptions) > 1
                            and _origin_revision(frame, origin_id) is not None):
                        # A revision floor withdraws old provisional authority
                        # even when this raw price is too old to replay.
                        yield sse_encode(json.dumps({
                            "event_id": event_id, "floor": preview_floors,
                        }), event="fold_preview_floor")
                        if preview_session is not None:
                            if origin_id == event_id and frame.get("status") not in QUOTE_STATUSES:
                                preview_session.reset()
                            projected_preview = update_preview_session()
                            if projected_preview is not None:
                                yield sse_encode(json.dumps(projected_preview), event="preview")
                    control = _withdrawal_reconcile(frame, event_id, origin_id)
                    if control is not None:
                        note_floors(control.get("removal_rev"))
                        yield sse_encode(json.dumps(control), event="reconcile")
                    if frame.get("reconcile_only") is True:
                        if (control is not None and control["custody_id"] ==
                                f"normal-price:{origin_id}:{frame['rev'][str(origin_id)]}"):
                            pending_quote_control = (frame, control)
                        continue
                if (frame is not None and type(frame.get("event_id")) is int
                        and frame["event_id"] == origin_id and _frame_is_fresh(
                            frame, datetime.now(timezone.utc)
                        )):
                    incoming = frame
                    if from_replay:
                        replayed[origin_id] = incoming
                    elif replayed.pop(origin_id, None) == incoming:
                        continue
                    rev = _origin_revision(incoming, origin_id)
                    if rev is not None:
                        sent_revision[origin_id] = max(
                            rev, sent_revision.get(origin_id, rev)
                        )
                    if origin_id != event_id:
                        frame = _fold_invalidation(frame, event_id, origin_id)
                        if frame is None:
                            continue
                    elif (len(subscription.subscriptions) > 1
                            and "source_snapshot" in frame):
                        # #10090: one row's sources never stand for a folded
                        # page. Its complete map comes only in `folded_quote`.
                        frame = {k: v for k, v in frame.items()
                                 if k != "source_snapshot"}
                    project = getattr(hub, "project_folded_quote", None)
                    pending_quote = (
                        len(subscription.subscriptions) > 1 and callable(project)
                        and not (origin_id == event_id and frame.get("status") not in QUOTE_STATUSES)
                    )
                    raw = {**frame, "folded_quote_pending": True} if pending_quote else frame
                    yield sse_encode(json.dumps(raw), event="probability")
                    # A frame is as good as a heartbeat for keeping the router
                    # from reaping us; a busy market should not also pay for
                    # pings it does not need.
                    last_beat = loop_now
                    if origin_id == event_id and frame.get("status") not in QUOTE_STATUSES:
                        # The match ended under us. Say so and close, so the
                        # client refetches once and settles rather than holding
                        # a stream open on a decided event forever.
                        yield sse_encode(
                            json.dumps({"reason": "not_live"}), event="closed"
                        )
                        return
                    if pending_quote:
                        if preview_on:
                            # One read plus latest owed trigger; keep consuming
                            # revokes/terminal/preview while the database waits.
                            pending_projection = (frame, incoming)
                            continue
                        quote = await project(event_id, incoming)
                        # Every promise completes, including null on failure.
                        # Legacy clients ignore this named event; modern clients
                        # can defer raw invalidation and fall back only on null.
                        yield sse_encode(
                            json.dumps({**frame, "folded_quote_pending": False,
                                        "folded_quote": quote}),
                            event="folded_probability",
                        )
                continue

            if loop_now - last_beat >= HEARTBEAT_INTERVAL_S:
                # A NAMED event, deliberately not the conventional `: ping`
                # comment. A comment keeps the router from reaping us but fires
                # no handler in EventSource, so the client cannot observe it —
                # and the client's silence watchdog would then be measuring
                # "is this market moving" instead of "is this server alive".
                # On a quiet market those differ, and the watchdog would tear
                # down a perfectly healthy stream. This is observable.
                yield sse_encode(
                    json.dumps(
                        {"t": datetime.now(timezone.utc).isoformat()}
                    ),
                    event="heartbeat",
                )
                last_beat = loop_now
    except asyncio.CancelledError:
        raise
    except Exception:
        # `%d` with an explicit int, not `%s`: `event_id` reaches this module
        # from the URL, and formatting it as a string would put caller-supplied
        # text into the log line. FastAPI already coerces the path param to int,
        # so this is belt-and-braces — but it is the kind of belt that costs
        # nothing and makes the safety local instead of inherited.
        logger.warning(
            "event_stream: stream for event %d failed", int(event_id),
            exc_info=True,
        )
    finally:
        _open_connections -= 1
        # NOT AWAITED, AND THAT IS THE POINT (#6515). This `finally` commonly
        # runs while the task is being cancelled, where the first `await`
        # re-raises `CancelledError` and nothing after it executes. When each
        # stream owned its own client that only risked an untidy close; with a
        # shared hub a skipped release would strand this subscriber forever —
        # the hub would never go idle and its channel would keep being
        # delivered to nobody. `release()` is synchronous, so it cannot be
        # interrupted and cannot raise out of the generator; the hub's reader
        # sends the `UNSUBSCRIBE` on its next pass.
        subscription.release()
        owned_reads = [task for task in (initial_coverage, recovery_coverage, next_frame, recovery_quote, folded_projection) if task is not None]
        for task in owned_reads:
            task.cancel()
        if owned_reads:
            await asyncio.gather(*owned_reads, return_exceptions=True)


@router.get("/{event_id}/stream")
async def stream_event(event_id: int, request: Request):
    """SSE stream of live blend updates for one event.

    Scheduled/suspended events require a mapped winner in the current producer
    cohort. Connection eligibility is not proof of a venue subscription or a
    new observation: only a received quote provides that evidence.

    THE SESSION IS OPENED BY HAND, AND THAT IS THE WHOLE POINT — do not put this
    connect lookup back on `Depends(get_db)`. FastAPI finalises a yield-dependency only
    after the response has been *fully sent*, and this response is a stream that
    lives up to `MAX_CONNECTION_S`. A `Depends(get_db)` here therefore does not
    hold a session for the microsecond of the status lookup; it pins one, and its
    pooled connection, for the entire life of every open stream — up to
    `MAX_CONNECTIONS` per uvicorn worker, times `WEB_CONCURRENCY` workers, against
    a Postgres that already runs at plan-limit contention. Measured on
    fastapi 0.136.3: teardown ordering is `open -> ...every frame... -> close`.
    Opening the session explicitly bounds it to the lookup and returns the
    connection to the pool before the first byte of the stream is written.
    """
    async with async_session_maker() as session:
        status = await _event_status(session, event_id)
        contributor_ids = (
            await _fold_stream_ids(session, event_id) if status in QUOTE_STATUSES else [event_id]
        )
        eligible = status in LIVE_STATUSES
        if status in QUOTE_STATUSES and not eligible:
            eligible = await _nonlive_stream_eligible(session, event_id, contributor_ids)
    if status is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not eligible:
        raise HTTPException(
            status_code=409,
            detail={"reason": "not_live", "status": status, "poll": True},
        )
    if _open_connections >= MAX_CONNECTIONS:
        raise HTTPException(
            status_code=503,
            detail={"reason": "stream_capacity", "poll": True},
        )

    return StreamingResponse(
        _stream(event_id, request, contributor_ids=contributor_ids),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # nginx and friends buffer by default, which for SSE means frames
            # arrive in a clump at close instead of as they happen.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
