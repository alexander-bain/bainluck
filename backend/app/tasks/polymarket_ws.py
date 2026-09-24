"""Polymarket WebSocket consumer task.

Streams live prices and resolution events from Polymarket's CLOB WebSocket.
No auth required. Runs alongside the Kalshi WS consumer on the same dyno.

Events:
  - best_bid_ask: price updates → FuturesOutcome.current_probability
  - last_trade_price: trade executions → FuturesOutcome.current_probability
  - market_resolved: settlement → FuturesMarket resolved + is_winner
"""

import asyncio
import logging
import os
from typing import Optional
from datetime import datetime, timezone

from app.tasks.kalshi_ws import (
    FINAL_FLUSH_ATTEMPTS,
    PRICE_FLUSH_SECONDS,
    SUBSCRIPTION_REFRESH_SECONDS,
)
from app.tasks.polymarket import _poly_book_is_untradeable
from app.utils.market_settlement import settled_values

logger = logging.getLogger(__name__)


#: A leg whose external id ends in one of these is the book of Gamma's
#: ``outcomes[1]``, the second CLOB token. ``_side1`` is a named two-sided
#: game's complement (``polymarket.py``, the ``_side1`` writer); ``_no`` is a
#: Yes/No binary's.
_SECOND_TOKEN_SUFFIXES = ("_side1", "_no")
_FIRST_TOKEN_SUFFIXES = ("_yes",)


def _token_index(ext: str) -> Optional[int]:
    ext = ext or ""
    if ext.endswith(_SECOND_TOKEN_SUFFIXES):
        return 1
    # A bare condition id (``0x...``, no suffix at all) is the first token.
    if ext.endswith(_FIRST_TOKEN_SUFFIXES) or (ext and "_" not in ext):
        return 0
    return None


def legs_in_token_order(pairs: list) -> list:
    """Order one market's ``(outcome_id, external_id)`` legs as its CLOB tokens are.

    #8403. Only a market whose legs are exactly one first-token leg and one
    second-token leg, each named by its own suffix, is reordered. Any other
    shape keeps the id order the caller passed, which is what it did before, so
    a shape nobody measured cannot be moved by this.
    """
    indexed = [(_token_index(ext), oid, ext) for oid, ext in pairs]
    if len(indexed) == 2 and {i for i, _, _ in indexed} == {0, 1}:
        return [(oid, ext) for _, oid, ext in sorted(indexed, key=lambda t: t[0])]
    return list(pairs)


async def _apply_ws_resolution(session, market_id, outcomes, winning_outcome):
    """Apply a Polymarket ``market_resolved`` settlement to the DB.

    Queue #261 Item 2: sets ``status='resolved'`` on the market and ``is_winner``
    on its outcomes, routed through the resolution-authority contract — and NEVER
    writes ``calibration_probability``. A terminal price must not both define the
    winner AND grade the earlier/current forecast (self-grading leakage, C20/C21);
    the terminal price still reaches ``current_probability`` via the ordinary
    buffered flush loop, and the published forecast is left to the timestamped
    snapshot pipeline. An outcome already settled by an authoritative source
    (tier 3) is left untouched — a bare websocket push must not downgrade it.

    Queue #284 Item 1: every applied winner write stamps its registered tier-3
    ``resolution_source`` (``clob_authoritative``) in the SAME UPDATE — winner and
    provenance are atomic, so a failed/partial write can never leave a graded
    outcome with a NULL source (which the authority ladder treats as tier -1,
    silently overwritable by a later guess).

    Module-level (not a closure) so the leakage contract is unit-testable.
    Returns the number of outcome winner-writes applied.
    """
    from sqlalchemy import select, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.resolution_authority import is_authoritative

    # A CLOB `market_resolved` push is the venue's own settlement delivered over
    # the socket — the same authority as the CLOB REST resolver
    # (`clob_resolve.py`). Stamp its registered tier-3 source so the winner write
    # carries audit-grade provenance, survives the authority ladder (a later
    # guess-family pass can no longer silently overwrite a NULL-source winner),
    # and is calibration-truth eligible. Do NOT invent a new source string.
    _WS_RESOLUTION_SOURCE = "clob_authoritative"

    outcome_ids = [oid for oid, _ in outcomes]
    existing_sources: dict = {}
    if outcome_ids:
        existing_sources = {
            r.id: r.resolution_source
            for r in (
                await session.execute(
                    select(
                        FuturesOutcome.id, FuturesOutcome.resolution_source
                    ).where(FuturesOutcome.id.in_(outcome_ids))
                )
            ).all()
        }

    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market_id)
        .values(status="resolved", **settled_values(FuturesMarket.settled_at))
    )

    written = 0
    for oid, ext in outcomes:
        if is_authoritative(existing_sources.get(oid)):
            continue  # venue already settled authoritatively — leave it
        is_winner = (
            (winning_outcome.lower() == "yes" and ext.endswith("_yes"))
            or (winning_outcome.lower() == "no" and ext.endswith("_no"))
        )
        # Winner AND provenance in the SAME statement (Queue #284 Item 1): an
        # atomic write means a failed/partial apply can never leave is_winner set
        # with a NULL resolution_source. Deliberately NOT setting
        # calibration_probability here (Queue #261) — no price self-grading.
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == oid)
            .values(is_winner=is_winner, resolution_source=_WS_RESOLUTION_SOURCE)
        )
        written += 1
    return written


#: How long after its scheduled start an event that is STILL 'scheduled' may
#: hold a place in the subscription. A start time is not a finish time (gotcha:
#: "scheduled kickoff timestamps are not actual start/finish"), so this is
#: deliberately far longer than any game: a rain-delayed baseball game, a
#: five-set match and a full day of status-updater lag all stay subscribed.
#:
#: It bounds the `scheduled` arm ONLY. Nothing here is ever applied to a live
#: event — see `_slate_event_window`.
#:
#: The exact value is not a judgement call, because the population it cuts is a
#: CLIFF rather than a gradient. Measured on production 2026-09-23 02:5xZ, the
#: slate held nothing at all between 6 h and 48 h old — a floor of 6, 12, 24 or
#: 48 hours each kept the identical 594 markets — while the nearest stale event
#: was 2 days old and the bulk (101 events, 1,175 markets) was the US Open,
#: three weeks finished. 24 h is the widest margin that still costs nothing.
SLATE_MAX_AGE_HOURS = 24


def _slate_event_window():
    """The event window the socket subscribes to — the scheduled arm bounded
    at BOTH ends, the live arm at neither.

    The upper bound (start within 6 h) was always here. The floor was not, and
    without it ``status='scheduled'`` is not a statement about the future: it is
    whatever the status updater last managed to write. Every event that never
    left ``scheduled`` stayed in the subscription forever, so the slate silently
    accumulated months of finished sport.

    Measured on production 2026-09-23 02:5xZ, before this floor existed:

        CURRENT (live, or starting within 6 h) ....  640 markets,  79 events
        STALE   (started > 6 h ago, still
                 'scheduled') ....................  1,248 markets, 107 events
                 oldest commence_time 2026-06-01 — nearly four months

    So **66 % of the subscription was finished sport**, and the venue confirms
    those rows are not merely quiet but gone: of 30 randomly sampled stale
    tokens, 27 answered ``/book`` with *"No orderbook exists for the requested
    token id"*, against 30 of 30 alive for a same-size current control. That is
    the whole of #837's unexplained ``served=1413/3367`` — four contiguous
    shards reading 14/500, 26/500, 36/500, 39/500 while the two holding current
    sport read 500/500 and 488/500. The subscription was not being truncated by
    the venue; we were asking it for dead tokens.

    What that cost a reader, which is why this is a fix and not hygiene: the
    token top-up that gives a market its ``clob_token_ids`` is capped per
    recycle, and its queue was **253 stale against 46 current**. It is ordered
    by a rotating cursor, not by whether anyone is watching, so live games
    waited behind finished ones for a budget 85 % of which could never pay.
    At the moment of the measurement 42 markets on games *in progress* had no
    tokens and therefore no price stream at all — eight MLB games among them,
    including the Dodgers/Padres game filed as #8156.

    THE FLOOR BINDS THE ``scheduled`` ARM ONLY, AND THE LIVE ARM STAYS
    CLOCK-FREE. This is the whole of the fix's shape, so it is worth the
    paragraph. A first draft applied the floor once, above the ``or_()``,
    reasoning that a ``scheduled``-only floor is re-admitted through the wider
    ``live`` sibling the first time an event sticks at ``status='live'``. That
    hazard is real (see below) but the cure regressed the thing #837 exists to
    protect: above the ``or_()`` the 24-hour bound applies to live rows too, so
    an event the graph still calls live is unsubscribed after 24 hours — a
    multi-day tournament, a suspended game, any delayed state advancement. That
    is a hero stream going dark, decided by a clock we do not trust, which is
    the premise of the constant above.

    (The ``IS NOT NULL`` in that draft was inert rather than harmful:
    ``events.commence_time`` is NOT NULL in the model and in production, so it
    can never exclude a row. It is kept below inside the scheduled arm, where
    the pre-#837 code had it, as belt-and-braces against the column being
    loosened — not because it fires. The Postgres contract asserts the schema
    that makes it inert, so that assumption fails loudly if it changes.)

    The ship does not need the live floor. Measured on production 2026-09-23
    03:4xZ over ALL events (a superset of the slate, so a zero here is a zero
    there):

        live ....... 58 rows,     0 older than 24 h
        scheduled .. 3,284 rows, 850 older than 24 h

    Every row the floor is for is a ``scheduled`` row, and the live arm's copy
    of the floor cuts nothing at all today. It is pure downside on exactly the
    row a reader is watching, so the live arm fails OPEN: no clock test, no
    NULL test, subscribed.

    The stuck-at-live hazard is therefore NOT fixed here, deliberately. An
    event wedged at ``status='live'`` for weeks is a state-machine defect in
    whatever should have advanced it, and it cannot be answered by dropping
    live rows out of the price stream — that trades a rare stale subscription
    for a routine dark hero. It needs a status-freshness signal (an advanced-at
    stamp, or the venue's own resolution) rather than a clock this module is
    already on record as not trusting. ``the_event_stuck_at_live`` stays in the
    Postgres contract as a live-preservation control, asserting it KEEPS its
    subscription, so nobody re-lands the above draft by accident.
    """
    # Imported in-function like every other SQLAlchemy use in this module: the
    # consumer is started by `run_kalshi_ws.py`, and module scope here stays
    # light on purpose.
    from sqlalchemy import text, or_, and_

    from app.models.models import Event

    return or_(
        # Clock-free and fail-open, on purpose. Unchanged from before the floor
        # existed — the fix narrows the sibling arm and leaves this one alone.
        Event.status == "live",
        and_(
            Event.status == "scheduled",
            Event.commence_time.isnot(None),
            # int() by construction: the interval literal can never carry
            # anything but a number, whatever a future edit does to the
            # constant.
            Event.commence_time >= text(
                f"NOW() - INTERVAL '{int(SLATE_MAX_AGE_HOURS)} hours'"
            ),
            Event.commence_time <= text("NOW() + INTERVAL '6 hours'"),
        ),
    )


def _slate_market_filter():
    """A market our own rows already record the venue as having SETTLED is not
    subscribed — the market-level half of the slate, and the signal the event
    window says it needs.

    ``_slate_event_window`` deliberately leaves the live arm clock-free, and
    says in as many words that the stuck-at-live hazard "needs a
    status-freshness signal (an advanced-at stamp, or the venue's own
    resolution) rather than a clock this module is already on record as not
    trusting". ``futures_markets.status = 'resolved'`` IS the venue's own
    resolution: it is written by this module's ``handle_resolved`` off a
    ``market_resolved`` push, and by ``sync_polymarket_resolved_status`` off the
    venue's closed/terminal read. Nothing here infers a finish from a clock.

    WHAT IT COSTS TO LEAVE THEM IN, measured on production 2026-09-23 05:2xZ.
    Of the 709 Polymarket markets the event window then selected, **54 markets /
    108 outcomes on 12 events were already ``status='resolved'`` in our own
    database** — 7.6% of a subscription whose per-shard budget is BYTE-capped
    and was sitting at 40,594 of 40,960 bytes, i.e. effectively full. Those
    tokens cannot pay: a 120-second probe of the public CLOB socket (8 assets,
    one connection, ``initial_dump``) returned **nothing whatsoever** for the
    four tokens of two such markets — not even the opening ``book`` frame every
    open market answers with — while the same connection's control arm got its
    books at once and 726 ``price_change`` frames on one of them. Two matches in
    the same M25 Yinchuan tournament, one resolved and one open, split exactly
    that way, so this is not a tier or a thin-book story.

    WHAT A READER SAW. Those 12 events were still ``status='live'`` on the site
    with no score and no ``completed_at``, showing a Polymarket price last
    written when the venue settled the market — four of them frozen over an
    hour, one at 733 minutes. Dropping the settled MARKET does not touch the
    event or its open siblings, so this returns the budget without taking a
    single price off a game still being played.

    FAIL OPEN, WHICH IS WHY THE NULL ARM IS HERE AND NOT A PLAIN ``!=``. In SQL
    ``status != 'resolved'`` is NULL — not true — for a NULL status, so the
    plain form silently DROPS a market whose status was never written. That is
    the dark-hero direction this module refuses everywhere else, and the case is
    reachable on the schema that actually serves readers: the model's
    ``Mapped[str]`` reads as NOT NULL, but **production's column is
    ``is_nullable = YES`` with ``DEFAULT 'open'``** (``information_schema``,
    2026-09-23 05:3xZ), so a raw-SQL writer can leave it NULL there while a
    ``create_all`` test database refuses the same row. The contract test relaxes
    its column to match production rather than let the stricter schema retire
    the control. Values in production today: ``open`` (29,039) and ``resolved``
    (784,156). ``suspended`` — the third the model's own comment names — is
    KEPT: a suspended market can reopen, and only ``resolved`` is terminal.
    """
    from sqlalchemy import or_

    from app.models.models import FuturesMarket

    return or_(
        FuturesMarket.status.is_(None),
        FuturesMarket.status != "resolved",
    )


def _format_by_shard(ws_stats: dict) -> str:
    """`0:14/500 1:26/500 …` — the per-shard shape behind the coverage ratio.

    The aggregate cannot carry this. `served=1837/3793` is the same 49% whether
    every shard is half-served (a quiet venue, nothing wrong) or four shards sit
    at 3% while four stream in full (a truncated subscription), and only the
    second is a defect. The first production read WAS the second shape, and the
    reader had to reconstruct the denominators from a separate capture to see
    it: the pairs were in `PolymarketWebSocket.stats` the whole time and reached
    no line until the ten-minute recycle, so a minute-resolution reader saw one
    number that could not be acted on.

    BOTH halves per shard, never a bare served count. Shard subscriptions are
    not all the same size — the last shard is a remainder, and the byte bound
    makes shards of different lengths at different id lengths — so `0:14` cannot
    be read as a share by anyone, including the next person to grep this line.

    Degrades to `-` rather than vanishing or raising. The shadow consumer shares
    this client and subscribes without shards, and an exception in the stats loop
    kills the socket's only heartbeat; a field that disappears when empty is also
    a field no grep can rely on.
    """
    served = ws_stats.get("served_by_shard") or {}
    subscribed = ws_stats.get("subscribed_by_shard") or {}
    if not served and not subscribed:
        return "-"

    def _order(key):
        # Shard keys are ints in-process but arrive as strings through any JSON
        # round-trip, and "10" sorts before "2" as text.
        try:
            return (0, int(key), "")
        except (TypeError, ValueError):
            return (1, 0, str(key))

    return " ".join(
        f"{key}:{served.get(key, 0)}/{subscribed.get(key, 0)}"
        for key in sorted(set(served) | set(subscribed), key=_order)
    )


def _log_stats_line(stats: dict, ws_stats: dict, blend: dict) -> None:
    """The once-a-minute socket line, including #837's coverage ratio.

    Module-level rather than inline in the consumer's `stats_loop` for one
    reason: the defect this exists to prevent is a number that is COMPUTED and
    never EMITTED, and a closure three `await`s deep inside a consumer that
    needs a database, a slate and a live socket cannot be asserted on. Lifted
    here, the emitted line is checkable directly, so "the coverage fields
    silently stopped being logged" is a red test rather than something a person
    has to notice in a log tail months later.

    Every field is read with `.get(..., 0)` because the shadow consumer shares
    this client and subscribes without shards: absent coverage keys must print
    a zero, never raise inside a stats loop whose exception would kill the
    socket's only heartbeat.

    `wire=` rides beside `served=` for the reason stated at the top of this
    docstring, applied to the field that was just added: `served` is now the
    intersection against the subscription, so it can no longer exceed its own
    denominator — and an excess that can no longer show up in the ratio would
    stop existing for every reader if the raw total were computed and never
    printed. `wire - served` is the count of ids the venue sent us unasked,
    which was previously being read AS coverage. It is also the only
    served-shaped number the shadow consumer has, since that one subscribes to
    everything and so has no subscription to intersect against.
    """
    logger.info(
        "Polymarket WS: %d prices, %d trades, %d resolutions, %d errors, "
        "%d msgs | coverage shards=%d/%d served=%d/%d wire=%d by_shard=%s "
        "| blend stamped=%d no_reading=%d throttled=%d errors=%d lock_skipped=%d",
        stats["price_updates"], stats["trade_updates"],
        stats["resolutions"], stats["errors"],
        ws_stats.get("messages", 0),
        ws_stats.get("shards_connected", 0), ws_stats.get("shards", 0),
        ws_stats.get("assets_served", 0),
        ws_stats.get("assets_subscribed", 0),
        ws_stats.get("assets_on_wire", 0),
        _format_by_shard(ws_stats),
        blend["stamped"], blend["no_reading"],
        blend["throttled"], blend["errors"],
        # #837 tail: stamps re-queued rather than left waiting on a row lock.
        blend.get("lock_skipped", 0),
    )


def _log_unserved_sample(ws) -> None:
    """Name a few of the ids the venue never sent, once per recycle.

    #837's ratio said 49% served and could not say why: `assets_served` counts
    assets that sent at least one message, so a book nobody traded and a
    subscription the venue truncated are the same number. The ids the
    difference is made of already exist in process memory at this point and
    were being discarded. Named, they are answerable — the books can be put to
    Polymarket directly, and the reply turns "49% served" into a share that is
    actually truncated.

    Module-level for the same reason `_log_stats_line` is: the failure this
    guards against is a line that quietly stops being emitted, and a closure
    inside a consumer that needs a database, a slate and a live socket cannot
    be asserted on.

    Defensive around the client because this runs in the recycle path, after
    the `finally` that drained prices: a consumer that raised here would turn
    a planned resubscribe into a crash, trading a diagnostic for the socket.
    """
    # Imported here, not at module scope, for the same reason the client is:
    # nothing on this module's import path should pull the websocket service.
    from app.services.polymarket_ws import UNSERVED_SAMPLE_PER_SHARD

    try:
        sample = ws.unserved_sample()
    except Exception:
        logger.exception("Polymarket WS unserved sample failed (#837)")
        return
    if not sample:
        return
    logger.info(
        "Polymarket WS unserved sample (#837): %d shard(s) with unserved ids, "
        "up to %d spread per shard — %s",
        len(sample),
        UNSERVED_SAMPLE_PER_SHARD,
        sample,
    )


async def _run_polymarket_ws_consumer():
    """Main Polymarket WebSocket consumer loop."""
    # `text`/`or_`/`and_` left with `_slate_event_window`, which now owns the
    # only expression in this consumer that needed them.
    from sqlalchemy import select, update, func

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.tasks.base import get_task_session
    from app.tasks.live_blend_refresh import (
        LiveBlendRefresher, event_ids_for_outcomes,
    )
    from app.tasks.polymarket_token_topup import (
        topup_clob_tokens, topup_outcome_clob_tokens,
    )
    from app.tasks.ws_liveness import report as _report_liveness
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    from app.utils.price_change_stamp import price_changed_at_value

    # Q504-b: see the Kalshi arm — reported before the slate work, so a stall in
    # the token top-up or the slate query is visible as an AGE rather than as a
    # silence indistinguishable from health.
    _report_liveness("polymarket", "loading_slate")

    ws = PolymarketWebSocket()

    # Load linked Polymarket market asset IDs
    async with get_task_session() as session:
        result = await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.market_id,
                FuturesOutcome.external_id,
                FuturesMarket.external_id.label("market_ext_id"),
                FuturesMarket.event_id.label("linked_event_id"),
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.isnot(None),
                _slate_event_window(),
                _slate_market_filter(),
            )
        )
        rows = result.all()

    if not rows:
        logger.info("Polymarket WS: no live/upcoming linked markets")
        return {"status": "no_markets"}

    # Polymarket outcomes store condition_id as external_id (e.g. "0xabc..._yes").
    # But the WS needs asset_ids (token IDs), which we store in market_metadata.
    # For now, load token IDs from the outcomes' market_metadata.
    # Build lookup: condition_id → (market_id, outcome_id)
    condition_to_ids: dict[str, tuple[int, int]] = {}
    market_ids = set()
    # Q460: linked event per market, so a flushed price can re-stamp the blend.
    event_id_by_market: dict[int, int] = {}
    for outcome_id, market_id, ext_id, market_ext_id, linked_event_id in rows:
        if ext_id:
            condition_to_ids[ext_id] = (market_id, outcome_id)
        market_ids.add(market_id)
        if linked_event_id is not None:
            event_id_by_market[market_id] = linked_event_id

    # Load clob_token_ids from market_metadata
    asset_ids: list[str] = []
    asset_to_outcome: dict[str, int] = {}  # asset_id → outcome_id
    asset_to_market: dict[str, int] = {}   # asset_id → market_id
    condition_to_market: dict[str, int] = {}  # condition_id → market_id

    tokens_by_market: dict[int, list[str]] = {}

    async with get_task_session() as session:
        market_result = await session.execute(
            select(FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.market_metadata)
            .where(FuturesMarket.id.in_(list(market_ids)))
        )
        ext_by_market: dict[int, str] = {}
        for mid, mext, metadata in market_result.all():
            if mext:
                condition_to_market[mext] = mid
                ext_by_market[mid] = mext
            if not metadata:
                continue
            tokens = metadata.get("clob_token_ids") or metadata.get("clobTokenIds")
            if not tokens:
                continue
            if isinstance(tokens, str):
                import json
                try:
                    tokens = json.loads(tokens)
                except Exception:
                    continue
            for token in tokens:
                asset_ids.append(str(token))
                asset_to_market[str(token)] = mid
            tokens_by_market[mid] = [str(t) for t in tokens]

        # Q490 — ask for the slate's tokens instead of waiting for a rotation.
        # The ingest stamp (Q460) is correct and covers the catalogue, but Gamma
        # caps `/events` at offset 2000, so the poll addresses ~2,000 of ~39,000
        # open markets per run on a rotating cursor. Measured 2h after that
        # deploy: 701 markets carried tokens and 0 of the 77 on THIS slate did.
        # `/markets?condition_ids=` does not paginate, so the fast lane can name
        # exactly what it needs. Bounded by the slate size, which is ~77.
        topup_missing = [
            (mid, ext_by_market.get(mid))
            for mid in market_ids
            if mid not in tokens_by_market
        ]
        if topup_missing:
            try:
                topped = await topup_clob_tokens(session, topup_missing)
            except Exception:
                # A Gamma outage must not take the socket down with it: the
                # markets that already have tokens keep streaming, and the next
                # recycle retries. Loud, because a silently-empty top-up is the
                # failure this whole queue exists to end.
                logger.exception(
                    "Polymarket WS: token top-up failed for %d markets; "
                    "continuing with the %d already stamped",
                    len(topup_missing), len(tokens_by_market),
                )
                topped = {}
            for mid, tokens in topped.items():
                tokens_by_market[mid] = tokens
                for token in tokens:
                    asset_ids.append(token)
                    asset_to_market[token] = mid

        outcome_result = await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.market_id, FuturesOutcome.external_id)
            .where(FuturesOutcome.market_id.in_(list(market_ids)))
            .order_by(FuturesOutcome.id)
        )
        outcomes_by_market: dict[int, list[tuple[int, str]]] = {}
        for oid, mid, ext in outcome_result.all():
            outcomes_by_market.setdefault(mid, []).append((oid, ext or ""))

        # ── THE MONEYLINE LEG ────────────────────────────────────────────────
        # Everything above addresses a market by its OWN condition id, which a
        # parent/field row does not have — its `external_id` is a bare Gamma
        # event id ("917153"), so `condition_id_of` returns None and the
        # market-level top-up skips it by design. That row is the three-way
        # "who wins" market: the ONLY market on the event that
        # `compute_source_home_probability` can read, and therefore the only one
        # whose price is the number the hero renders.
        #
        # Measured on production 2026-09-01 before this block existed: the
        # socket was streaming continuously (7 distinct sub-minute flushes in
        # one minute) into Over/Under and Both-Teams-To-Score props, while
        # across EVERY live event the `polymarket` and `kalshi` blend stamps sat
        # at p50 age 122s — the 120s poll's sawtooth — with 0 of 9 fresher than
        # two minutes, against `betting` at 23s. The fast lane was real and it
        # was pointed at the markets nobody reads.
        #
        # A field market's OUTCOMES each carry a real condition id, so the
        # tokens were reachable one level down the whole time. Only markets
        # still missing tokens after the market-level pass are asked about, so
        # an ordinary binary sub-market costs nothing here.
        outcome_topup_targets: list[tuple[int, int, str]] = [
            (mid, oid, ext)
            for mid in market_ids
            if mid not in tokens_by_market
            for oid, ext in outcomes_by_market.get(mid, [])
        ]
        outcome_yes_token: dict[int, str] = {}
        if outcome_topup_targets:
            try:
                outcome_yes_token = {
                    oid: token
                    for oid, (_mid, token) in (
                        await topup_outcome_clob_tokens(
                            session, outcome_topup_targets
                        )
                    ).items()
                }
            except Exception:
                # Same posture as the market-level top-up: a Gamma outage must
                # not take the socket down. The props keep streaming and the
                # next recycle retries the moneyline.
                logger.exception(
                    "Polymarket WS: outcome token top-up failed for %d outcomes; "
                    "continuing without the moneyline legs",
                    len(outcome_topup_targets),
                )
                outcome_yes_token = {}

        market_by_outcome: dict[int, int] = {
            oid: mid
            for mid, pairs in outcomes_by_market.items()
            for oid, _ext in pairs
        }
        for oid, token in outcome_yes_token.items():
            mid = market_by_outcome.get(oid)
            if mid is None:
                continue
            asset_ids.append(token)
            asset_to_market[token] = mid
            # Attributed directly, never positionally: this token IS the book
            # for "will <this outcome> win", so the pairing is carried by the
            # condition id rather than reconstructed from ordering.
            asset_to_outcome[token] = oid

    # Q489 — WHICH outcome an asset id belongs to. Both CLOB tokens of a binary
    # (`clobTokenIds == [yesToken, noToken]`) map to the same FuturesMarket, and
    # the price handlers used to resolve every tick to `outcomes[0]` — the
    # Over/Yes leg — because this map was declared and never filled. A No-token
    # `best_bid_ask` therefore wrote P(No) into the Yes outcome, and since both
    # legs stream continuously the rendered number would oscillate between p and
    # 1-p on every tick. That is strictly worse than a stale price: a stale card
    # is wrong once, an inverted card is wrong at random.
    #
    # The pairing is positional and both sides are already ordered the same way:
    # Gamma serves `[yes, no]`, and the ingest inserts the Over/Yes outcome
    # before the Under/No one (`polymarket.py`, the sub-market loop), so ordering
    # by `FuturesOutcome.id` reproduces the token order. `zip` is deliberate — a
    # market whose outcome count disagrees with its token count maps only the
    # pairs it can prove and leaves the rest unmapped, so a shape we did not
    # anticipate drops ticks instead of writing them to the wrong leg.
    #
    # #8403: "ordering by id reproduces the token order" is an ASSUMPTION about
    # insertion order, and on a named two-sided game it fails. The legs are
    # `{condition}` (Gamma `outcomes[0]`, token 0) and `{condition}_side1`
    # (`outcomes[1]`, token 1), and on 21 of 67 live-or-upcoming markets
    # measured 2026-09-24 the `_side1` leg held the LOWER id — so token 0 was
    # zipped onto the second team's row and each team's price streamed onto
    # the other's. The leg's own suffix says which token it is; ordering by it
    # is `legs_in_token_order`.
    for mid, mtokens in tokens_by_market.items():
        for token, (oid, _ext) in zip(
            mtokens, legs_in_token_order(outcomes_by_market.get(mid, []))
        ):
            asset_to_outcome[token] = oid

    unmapped_assets = [a for a in asset_ids if a not in asset_to_outcome]

    if not asset_ids:
        logger.info("Polymarket WS: no asset IDs found in market_metadata")
        _report_liveness("polymarket", "no_asset_ids", legs=0)
        return {"status": "no_asset_ids"}

    logger.info(
        "Polymarket WS: %d asset IDs (%d markets), %d mapped to an outcome, "
        "%d unmapped (ticks dropped rather than mis-attributed), "
        "%d moneyline legs subscribed via outcome condition ids",
        len(asset_ids), len(market_ids),
        len(asset_to_outcome), len(unmapped_assets),
        len(outcome_yes_token),
    )

    stats = {
        "assets_subscribed": len(asset_ids),
        # Q489: the number that says whether a tick can land on the right leg.
        # `assets_subscribed` counts what we listen to; this counts what we can
        # actually attribute, and the gap between them is the silent-loss bound.
        "assets_mapped": len(asset_to_outcome),
        "assets_unmapped": len(unmapped_assets),
        # The count this queue exists to move off zero. Every other number here
        # can look healthy while the hero is stale, because props tick loudly
        # and the moneyline is the only leg the rendered blend reads. A run that
        # subscribes 0 moneyline legs on a non-empty slate is the bug, restated.
        "moneyline_legs_subscribed": len(outcome_yes_token),
        "price_updates": 0,
        "trade_updates": 0,
        "resolutions": 0,
        "errors": 0,
        # Q491: prices a failed flush put BACK on the buffer instead of dropping.
        # `errors` alone cannot distinguish a retried batch from a lost one.
        "requeued": 0,
        # Q491 repair: the final drain retries instead of requeueing, because
        # nothing runs after it. These two separate "we had to try again" from
        # "we gave up and a price is gone".
        "final_flush_retries": 0,
        "final_flush_dropped": 0,
        # #6598 / CERT-3182: rows whose `rank` a flush corrected. Twin of the
        # Kalshi socket's counter and there for the same reason — this module
        # moves `current_probability` and had never written the column derived
        # from it, so a live crossing left the board ordered by the last poll.
        # Counted unconditionally: the statement is a no-op on a field that did
        # not cross, so 0 is healthy and absence is the failure.
        "ranks_rederived": 0,
    }

    # Buffered price updates
    price_buffer: dict[int, float] = {}
    buffer_lock = asyncio.Lock()
    # Q460: outcome → linked event, for the blend re-stamp after each flush.
    #
    # Built from `market_by_outcome` (every outcome of every slate market) and
    # not, as it first was, from `condition_to_ids` — which is keyed by outcome
    # `external_id` and so silently omits any outcome whose external_id is NULL
    # or empty. An omitted outcome still gets its price written by the flush;
    # it just cannot name its event, so `event_ids_for_outcomes` drops it and
    # the blend is never re-stamped. That is the Q460 join failing open on
    # exactly the rows least likely to be noticed.
    event_id_by_outcome: dict[int, int] = {
        outcome_id: event_id_by_market[market_id]
        for outcome_id, market_id in market_by_outcome.items()
        if market_id in event_id_by_market
    }
    blend_refresher = LiveBlendRefresher("polymarket")

    async def flush_prices():
        async with buffer_lock:
            if not price_buffer:
                return
            batch = dict(price_buffer)
        # Q491 repair 2 (CERT-659 BLOCK) — THE BUFFER IS DELIBERATELY *NOT*
        # CLEARED HERE. Twin of the Kalshi socket: draining first and putting
        # the batch back on failure only covers the failures you thought to
        # catch, and `except Exception` never sees `CancelledError` (a
        # BaseException), so a recycle cancelling `flush_loop` between the drain
        # and the write lost the batch with `errors=0, requeued=0` — invisible.
        # Entries now leave only after the write lands, so nothing needs to be
        # "put back", because it was never taken away.
        try:
            async with get_task_session() as session:
                for outcome_id, prob in batch.items():
                    await session.execute(
                        update(FuturesOutcome)
                        .where(FuturesOutcome.id == outcome_id)
                        .values(
                            current_probability=prob,
                            # Same contract as every other price writer (#2024):
                            # a live socket owes the touch-stamp AND the
                            # change-stamp, or downstream liveness gates read a
                            # streaming row as long dead.
                            last_updated=func.now(),
                            price_changed_at=price_changed_at_value(
                                FuturesOutcome.current_probability,
                                FuturesOutcome.price_changed_at,
                                prob,
                            ),
                        )
                    )

                # #6598 / CERT-3182, twin of the Kalshi socket's. Every price
                # above moved the value `rank` is derived from and this module
                # has never written that column, so a crossing mid-game left the
                # board numbered by whichever poll last saw it. One statement
                # for every market the batch touched, in the same session as the
                # prices. `market_by_outcome` is the slate map already in memory
                # — no per-flush lookup on a two-second cadence.
                reranked_markets = {
                    market_by_outcome[oid]
                    for oid in batch
                    if oid in market_by_outcome
                }
                if reranked_markets:
                    stats["ranks_rederived"] += (
                        await session.execute(
                            rerank_market_fields_stmt(sorted(reranked_markets))
                        )
                    ).rowcount
            stats["price_updates"] += len(batch)
        except Exception:
            # Q491 — THE SHIP. The batch is still in `price_buffer`, so the next
            # flush retries it. Before Q491 the buffer was drained up front and
            # a failed write DISCARDED those prices outright: the socket only
            # refills an outcome when that market ticks again, and 86.7% of open
            # Polymarket markets never tick at all, so one transient error froze
            # a card at its old number indefinitely with no `last_updated`
            # either (#2024).
            #
            # Bounded by construction: the buffer is keyed by outcome_id over a
            # fixed slate, so a long outage holds at most one entry per
            # subscribed outcome however many attempts are burned.
            stats["errors"] += 1
            stats["requeued"] += len(batch)
            logger.exception(
                "Polymarket WS: flush error (%d retained for retry)", len(batch)
            )
            return

        # Q491 repair 2 — the write landed, so and only so do these entries
        # leave the buffer. The `== prob` test is what used to be `setdefault`:
        # `handle_price` may have buffered a FRESHER price for the same outcome
        # while this write was in flight, and that newer value is the truth, so
        # it must survive to the next flush rather than be dropped as "already
        # written". Same contract, enforced at removal instead of at re-queue.
        async with buffer_lock:
            for outcome_id, prob in batch.items():
                if price_buffer.get(outcome_id) == prob:
                    del price_buffer[outcome_id]

        # Q460 — THE SHIP. Carry the freshly-flushed prices through to
        # `Event.win_probability_sources`, the JSONB the card actually renders.
        await blend_refresher.refresh(
            event_ids_for_outcomes(event_id_by_outcome, batch.keys())
        )

    async def drain_prices():
        """The LAST flush of this consumer's life — retry, never requeue.

        Q491 repair (CERT-654 BLOCK), twin of the Kalshi socket's. `flush_prices`
        hands a failed batch back to `price_buffer` so the next periodic flush
        retries it. At recycle and at shutdown there IS no next flush, so that
        requeue is a silent drop — the certifier's exact-head probe read
        `writes=[]`, `errors=1`, `requeued=1`. Call `flush_prices` again instead,
        up to `FINAL_FLUSH_ATTEMPTS`, each attempt on a fresh session.
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
                    "Polymarket WS: %d price updates STRANDED by cancellation "
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
                "Polymarket WS: %d price updates STRANDED after %d final-flush "
                "attempts — these are lost, not deferred",
                stranded, FINAL_FLUSH_ATTEMPTS,
            )

    async def handle_price(msg: dict):
        """Handle best_bid_ask event."""
        asset_id = msg.get("asset_id", "")
        market_id = asset_to_market.get(asset_id)
        if not market_id:
            return

        best_bid = msg.get("best_bid")
        best_ask = msg.get("best_ask")
        if best_bid is None or best_ask is None:
            return

        try:
            bid_f = float(best_bid)
            ask_f = float(best_ask)
        except (ValueError, TypeError):
            return

        # #1578: never stream a midpoint from a book nobody will trade inside.
        # This path matters most of the five, because it is the only one that
        # UPDATEs an outcome directly rather than going through the upsert — a
        # wide quote arriving here would overwrite a good stored price with a
        # phantom. Returning early leaves the existing value untouched; the
        # real-trade stream (handle_trade, below) is what moves an illiquid
        # market's price, which is correct.
        if _poly_book_is_untradeable(bid_f, ask_f):
            return

        prob = (bid_f + ask_f) / 2
        if prob <= 0 or prob >= 1:
            return

        # Q489: the outcome this ASSET is the book for — not "the market's first
        # outcome". `prob` here is the midpoint of THIS token's own book, so on
        # the No token it is P(No), which belongs on the No leg and nowhere else.
        outcome_id = asset_to_outcome.get(asset_id)
        if outcome_id is None:
            return

        async with buffer_lock:
            price_buffer[outcome_id] = prob

    async def handle_trade(msg: dict):
        """Handle last_trade_price event."""
        asset_id = msg.get("asset_id", "")
        market_id = asset_to_market.get(asset_id)
        if not market_id:
            return

        price = msg.get("price")
        if price is None:
            return
        try:
            prob = float(price)
        except (ValueError, TypeError):
            return
        if prob <= 0 or prob >= 1:
            return

        # Q489: same contract as `handle_price` — a `last_trade_price` is a trade
        # in THIS token, so it grades THIS token's leg.
        outcome_id = asset_to_outcome.get(asset_id)
        if outcome_id is None:
            return

        async with buffer_lock:
            price_buffer[outcome_id] = prob
        stats["trade_updates"] += 1

    async def handle_resolved(msg: dict):
        """Handle market_resolved event.

        Sets status=resolved and is_winner, routed through the resolution-authority
        contract. Queue #261 Item 2: this path NEVER copies the last buffered
        trade into ``calibration_probability`` — a terminal price must not both
        define the winner AND grade the earlier/current forecast (self-grading
        leakage, C20/C21). The terminal price still reaches ``current_probability``
        through the ordinary buffered flush loop, and the published calibration
        forecast is left to the timestamped snapshot pipeline (opening/closing
        lines). An outcome already settled by an authoritative source (tier 3) is
        left untouched — a bare websocket push must not downgrade it.
        """
        condition_id = msg.get("market", "")
        winning_outcome = msg.get("winning_outcome", "")

        market_id = condition_to_market.get(condition_id)
        if not market_id:
            return

        outcomes = outcomes_by_market.get(market_id, [])

        try:
            async with get_task_session() as session:
                written = await _apply_ws_resolution(
                    session, market_id, outcomes, winning_outcome
                )
            stats["resolutions"] += 1
            logger.info(
                "Polymarket WS: %s resolved (winner=%s, %d/%d outcomes written, "
                "no calibration scalar captured)",
                condition_id[:20], winning_outcome, written, len(outcomes),
            )
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: resolution error")

    ws.on_price = handle_price
    ws.on_trade = handle_trade
    ws.on_resolved = handle_resolved

    async def flush_loop():
        while True:
            await asyncio.sleep(PRICE_FLUSH_SECONDS)
            await flush_prices()

    async def stats_loop():
        while True:
            await asyncio.sleep(60)
            # Q504-b: blend counters ride along, same reasoning as the Kalshi arm.
            blend = blend_refresher.stats
            # #837: the fan-out already counts, on the wire, how many distinct
            # assets each shard was actually served — but nothing read it, so
            # the one number that answers "is the venue serving the whole
            # subscription or a fraction of it" existed only in process memory
            # and no after-check could ever be paid from production. The
            # coverage WARNING beside it fires only when a shard serves
            # literally zero while a sibling streams; a shard served 3 of 500
            # is the same silent-fraction defect and is invisible to it. So the
            # ratio is stated every minute, whether or not anything is wrong.
            ws_stats = ws.stats
            _log_stats_line(stats, ws_stats, blend)
            _report_liveness(
                "polymarket",
                "streaming" if getattr(ws, "is_connected", False) else "disconnected",
                legs=len(asset_ids),
                msgs=ws_stats.get("messages", 0),
                served=ws_stats.get("assets_served", 0),
                stamped=blend["stamped"],
                no_reading=blend["no_reading"],
            )

    flush_task = asyncio.create_task(flush_loop())
    stats_task = asyncio.create_task(stats_loop())

    _report_liveness("polymarket", "subscribing", legs=len(asset_ids))

    try:
        # Q460: recycle on a timer so the slate is re-read — same reasoning as
        # `kalshi_ws.SUBSCRIPTION_REFRESH_SECONDS`, and the same constant, so the
        # two sockets on this dyno cannot drift to different coverage windows.
        await asyncio.wait_for(
            ws.run(asset_ids=asset_ids),
            timeout=SUBSCRIPTION_REFRESH_SECONDS,
        )
    except asyncio.TimeoutError:
        stats["status"] = "resubscribe"
    except asyncio.CancelledError:
        # Real shutdown, not the planned recycle (CERT-491) — keep it travelling
        # so the runner stops instead of relaunching. Buffer still drains below.
        raise
    finally:
        flush_task.cancel()
        stats_task.cancel()
        # Q491 repair (CERT-654 BLOCK): the last flush has no successor, so it
        # must RETRY rather than requeue into a buffer nobody will read again.
        await drain_prices()

    # #837: the per-shard breakdown, once per recycle rather than once a minute
    # — this is the shape that tells a starved subscription from a quiet one.
    # `run()`'s teardown clears the CONNECTED sets but deliberately not the
    # served ones, so the cycle's coverage is still readable here; `shards_
    # connected` is not, and is left out rather than logged as a misleading 0.
    exit_stats = ws.stats
    stats["assets_served"] = exit_stats.get("assets_served", 0)
    stats["served_by_shard"] = exit_stats.get("served_by_shard", {})
    stats["subscribed_by_shard"] = exit_stats.get("subscribed_by_shard", {})
    stats["unserved_by_shard"] = exit_stats.get("unserved_by_shard", {})
    # PER SHARD, because that is the resolution the excess was found at: the
    # minute line's fleet total would have read 394 over a 375 shard as a few
    # ids across eight shards and nothing would have stood out. `2:394/375`
    # stood out precisely because one shard crossed its own denominator.
    stats["on_wire_by_shard"] = exit_stats.get("on_wire_by_shard", {})
    _log_unserved_sample(ws)
    logger.info("Polymarket WS consumer exiting: %s", stats)
    return stats


async def _run_polymarket_ws_shadow_consumer():
    """#837 fast-follow (SHADOW): widened resolution-only grader that records
    its verdict to Redis (NEVER is_winner). Subscribes to ALL markets'
    resolution pushes (not the price firehose) so every Polymarket settlement
    is graded in real time — into the shadow store, for the automated
    source-agnostic comparison (`compare_shadow_verdicts`).

    Runs ONLY when the `bainluck:ws_shadow_enabled` flag is on (deploy-dark).
    The authoritative `_run_polymarket_ws_consumer` is untouched and keeps
    owning `is_winner`.
    """
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.services.ws_shadow import (
        is_ws_shadow_enabled,
        verdict_from_polymarket_resolved,
        record_shadow_verdict,
    )

    if not await is_ws_shadow_enabled():
        return {"status": "shadow_disabled"}

    ws = PolymarketWebSocket()
    stats = {"shadow_verdicts": 0, "errors": 0}

    async def handle_resolved_shadow(msg: dict):
        parsed = verdict_from_polymarket_resolved(msg)
        if not parsed:
            return
        # SHADOW ONLY — record BOTH outcome verdicts, keyed by each outcome's
        # external_id ({condition_id}_yes / {condition_id}_no). The comparison
        # joins FuturesOutcome.external_id == key exactly, source-agnostic.
        for ext_id, is_winner in parsed:
            try:
                await record_shadow_verdict(ext_id, is_winner)
                stats["shadow_verdicts"] += 1
            except Exception:
                stats["errors"] += 1

    ws.on_resolved = handle_resolved_shadow
    # resolution-only + all markets: NO asset_ids -> subscribe to all; the
    # service only dispatches market_resolved here (on_price/on_trade unset),
    # so this is the settlement trickle, NOT the price firehose.
    try:
        await ws.run()
    except asyncio.CancelledError:
        raise  # shutdown must stop the runner, not restart it (CERT-491)
    logger.info("Polymarket WS SHADOW consumer exiting: %s", stats)
    return stats
