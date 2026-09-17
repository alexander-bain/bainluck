"""Fast-lane CLOB token top-up — address the slate directly, never wait for a rotation.

WHY THIS EXISTS.  ``poll_polymarket_markets`` now stamps ``clob_token_ids`` at
ingest (Q460), and it does so on the UPDATE path as well as the insert, so
existing rows acquire the key when the poll reaches them.  Measured on
production 2026-08-31: the first sync after that deploy took 0 -> 701 markets
carrying the key, 558 of them rows created before the deploy.  The write works.

**Reaching the row is the problem.**  Gamma caps ``/events`` at offset 2000, so
the poll addresses at most ~2,000 of ~39,000 open markets per run; it rotates a
20-page cursor and truncates on a 420s budget.  Which markets get refreshed in a
given hour is therefore a rotation, not a guarantee — the same fact
``PolymarketAPIService.get_markets_by_conditions`` was written for ("any given
event is re-priced only when the cursor happens to land on it").

Measured consequence for the fast lane, 2026-08-31 03:58 UTC, ~2h after the
deploy: 701 markets carried tokens and **0 of the 77 markets the WebSocket
consumer actually subscribes to** were among them.  The socket kept returning
``no_asset_ids``.  A ship that depends on a rotation reaching it is a ship with
no delivery date.

So the fast lane asks for exactly the markets it needs.  ``/markets?condition_ids=``
is the one Gamma read not subject to the offset cap, because it does not
paginate — it names its markets.  The slate is ~77 markets, two orders of
magnitude below the catalogue, so this is cheap and bounded, and it makes the
socket's coverage independent of the catalogue sweep entirely.

This does not replace the ingest stamp.  Ingest still owns the other ~39,000
markets and every future row; this closes the gap for the small, time-critical
subset where "eventually" is not an answer.
"""

import asyncio
import bisect
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

#: Upper bound on one top-up pass.  The fast-lane slate is ~77 markets, so this
#: is ~4x headroom rather than a real limit — it exists so that a slate query
#: that unexpectedly widens (a matching change, a busy Saturday) cannot turn one
#: socket recycle into a thousand-market Gamma sweep.  Exceeding it is LOGGED,
#: never silent: a truncated top-up that read as "nothing was missing" is the
#: same class of lie this module was written to end (gotcha #53).
MAX_TOPUP_MARKETS = 300

#: Where a parent/field market records the YES token for each of its OUTCOMES.
#: A sibling of ``clob_token_ids`` rather than a reuse of it: that key means
#: "the two tokens of THIS market's own binary book", and a field market has no
#: such book.  Shape is ``{"<outcome_id>": "<yes_token>"}`` — keyed by
#: ``FuturesOutcome.id`` because that is what the socket must attribute a tick
#: to, and stringified because JSONB object keys are always strings.
OUTCOME_TOKEN_METADATA_KEY = "clob_yes_token_by_outcome"

#: Where the outcome top-up's position between recycles lives (#837).  Redis,
#: not a column, for the reason ``anchor_schedule_sentinel`` keeps its
#: continuation there (CERT-843): it is scheduling scratch, it is worthless the
#: moment the slate moves past it, and a migration for it would outlive its
#: usefulness by years.
TOPUP_CURSOR_KEY = "polymarket_token_topup:outcome_cursor"

#: Long enough to survive a deploy and a quiet night, short enough that a
#: position from a dead era expires instead of resuming into a slate that no
#: longer holds it.  Losing it costs one pass's fairness, never correctness —
#: the selector simply restarts at the front, which is today's behaviour.
TOPUP_CURSOR_TTL_SECONDS = 7 * 24 * 3600

#: How long after its event's start time an outcome stays worth asking about
#: (#837).  Past this, the game is over by any reading and its CLOB book cannot
#: be live, so the leg is dropped from the ask instead of holding a seat under
#: the cap.
#:
#: NOT A TUNED NUMBER, and that is the point of stating the measurement.  The
#: slate's age distribution is bimodal — today's fixtures, then corpses weeks
#: old, with nothing in between — so the constant sits on a flat plateau rather
#: than a cliff.  Measured on production 2026-09-17 07:0xZ, distinct condition
#: ids the ask would carry at each bound:
#:
#:     no bound  1,803   (today's behaviour)
#:     12 h        581
#:     24 h        581
#:     48 h        581
#:      7 d        589
#:
#: Any choice between 12 h and 48 h is the same answer, and seven days moves it
#: by eight ids.  48 h is taken as the most conservative point that is still on
#: the plateau: comfortably longer than any single fixture we carry, so no real
#: game can age out while its book is still trading.
STALE_EVENT_HOURS = 48


def select_ask_window(
    ordered: list[str], size: int, cursor: Optional[str]
) -> tuple[list[str], Optional[str]]:
    """``size`` condition ids from ``ordered``, resuming after ``cursor``.

    Returns ``(kept, next_cursor)``.  ``next_cursor`` is None when there was
    nothing to defer — the caller then leaves the stored position alone rather
    than spending a write on a pass that asked the whole slate.

    WHY A POSITION AND NOT A CLOCK.  #6634 made FILLED outcomes leave the ask,
    so the set shrinks as legs are mapped.  Nothing makes UNFILLABLE ones leave,
    and most legs of a live game's parent row are unfillable for good: a closed
    sub-market is an empty 200 on this read (gotcha #53), and an open
    spread/total comes back with outcomes our single leg cannot be attributed
    to.  Those legs keep their lexicographic seats forever and starve whatever
    sorts above the cap — measured 2026-09-16 as 324 of 333 condition ids
    identical between consecutive recycles, 2 newly mapped per pass, with the
    Braves moneyline ``0x8670…`` (which maps first try when asked directly)
    among the starved.

    The obvious repair — turn the window by wall clock,
    ``(now // recycle_seconds) * size % len`` — was PROVED to starve before it
    was built, which is why it is not what this is.  The window quantum and the
    call cadence resonate: 900 stable ids, cap 300, a pass every 900 s visits
    clock buckets 0, 1, 3, 4, 6, 7… so the starts are 0 and 300 forever and the
    last 300 ids are never asked at all; 600 ids at cap 300 on a 1,200 s cadence
    starves half.  A skipped window does not cost "one cycle" — it can cost
    every cycle, permanently, and no cadence assumption is safe in a runner that
    restarts inside the dyno and whose recycles drift.

    So the window turns on WHERE IT STOPPED, never on when it ran:

    * **Cadence-free.**  Consecutive passes ask contiguous, disjoint runs, so
      with a stable slate of N ids every id is asked within ``ceil(N / size)``
      passes whatever the interval between them, however irregular, however
      often one is skipped or repeated.  There is no clock in this function and
      no clock in its caller's use of it.
    * **Restart-proof.**  The position is durable (Redis), so a runner restart
      resumes where the last pass stopped.  A pass counter in module state would
      restart at 0 and re-select the head forever, which is the present defect.
    * **Churn-safe.**  The cursor is an id, not an index, so an id added or
      removed below it shifts nobody's turn.  An id that enters the slate ABOVE
      the cursor is asked this cycle; one that enters below waits at most one
      full cycle (``ceil(N / size)`` passes).  Legs enter the slate ~6 h before
      first pitch, so a hero leg is asked long before anybody can read it.

    The bound is on being ASKED.  Whether Gamma can answer, and whether the
    answer can be attributed to our leg, are the mapping rules above, and this
    function deliberately knows nothing about them: it needs no theory of why a
    leg is dead, so it cannot mis-classify one.
    """
    if size <= 0:
        return [], None
    if len(ordered) <= size:
        return list(ordered), None

    # ``bisect_right`` is the first id STRICTLY greater than the cursor, which
    # is also the right answer when the cursor's own id has left the slate —
    # the position survives its id's departure.
    # A cursor past the last id gives ``start == len(ordered)``; the modulo
    # below is what wraps it to the front, so there is no separate guard for it
    # (one no test could kill, because it cannot change an answer).
    start = bisect.bisect_right(ordered, cursor) if cursor is not None else 0
    kept = [ordered[(start + i) % len(ordered)] for i in range(size)]
    return kept, kept[-1]


def _is_stale(commence_time, cutoff: datetime) -> bool:
    """True only when ``commence_time`` is KNOWN to be older than ``cutoff``.

    Every other case is False — unknown is not stale.  A missing start time, an
    unlinked market or a value we cannot compare keeps its leg in the ask, so
    the worst case of this whole filter is today's behaviour.  That asymmetry is
    the safety argument: the cost of wrongly keeping a dead leg is one seat for
    one pass, and the cost of wrongly dropping a live one is a hero line that
    never streams.

    A naive datetime is read as UTC rather than refused.  The column is
    ``timestamptz`` so production always hands back an aware value; the coercion
    exists because a naive one would otherwise raise inside the comparison and
    take the socket's token pass down with it.
    """
    if not isinstance(commence_time, datetime):
        return False
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    return commence_time < cutoff


def _read_cursor_sync() -> Optional[str]:
    from app.tasks.redis_state import get_redis_client

    raw = get_redis_client().get(TOPUP_CURSOR_KEY)
    if not raw:
        return None
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)


def _write_cursor_sync(cursor: str) -> None:
    from app.tasks.redis_state import get_redis_client

    get_redis_client().setex(TOPUP_CURSOR_KEY, TOPUP_CURSOR_TTL_SECONDS, cursor)


async def load_topup_cursor() -> Optional[str]:
    """The position the last pass stopped at, or None to start at the front.

    A Redis fault degrades to None — one pass from the front, which is exactly
    the pre-#837 behaviour — rather than raising.  That is the right way to
    fail: the socket still gets its tokens, it just loses its place for a pass.

    The bounded SYNC client on a worker thread, not ``get_async_redis_client``:
    the sync client is cached per process (#1197) while the async factory builds
    a fresh connection pool per call, and this runs on the socket's event loop
    every recycle.  ``to_thread`` keeps a slow Redis off that loop; the client's
    own 5 s socket timeout (#969) is what bounds the work itself.
    """
    try:
        return await asyncio.to_thread(_read_cursor_sync)
    except Exception:
        logger.warning(
            "Polymarket outcome token top-up: could not read the saved window "
            "position; asking from the front of the slate this pass",
            exc_info=True,
        )
        return None


async def save_topup_cursor(cursor: Optional[str]) -> None:
    """Persist where this pass stopped.  A fault costs the next pass its place."""
    if not cursor:
        return
    try:
        await asyncio.to_thread(_write_cursor_sync, cursor)
    except Exception:
        logger.warning(
            "Polymarket outcome token top-up: could not persist the window "
            "position; the next pass will ask from the front of the slate",
            exc_info=True,
        )


def condition_id_of(external_id: Optional[str]) -> Optional[str]:
    """The Gamma condition id a ``FuturesMarket.external_id`` addresses, or None.

    Polymarket sub-market rows store the bare condition id; outcome rows store it
    with a ``_yes`` / ``_no`` suffix, and a caller holding the wrong one is a
    404 (the reason `12fd2496` exists).  ``removesuffix`` rather than the
    ``rstrip("_yes")`` in that commit: ``rstrip`` takes a CHARACTER SET, so it
    eats any trailing run of ``_``/``y``/``e``/``s`` — on a hex condition id
    ending in ``e`` it silently truncates a real character.

    Returns None for parent rows, whose ``external_id`` is a Gamma EVENT id
    (a bare integer), not a condition id.  Those rows are addressable one level
    down, by their OUTCOMES' condition ids — see ``topup_outcome_clob_tokens``,
    which is the caller that does it. Guessing which kind an id is would be the
    bug this function prevents; ``0x`` is the discriminator.
    """
    if not external_id:
        return None
    cid = external_id.removesuffix("_yes").removesuffix("_no")
    return cid if cid.startswith("0x") else None


def yes_token_of(market) -> Optional[str]:
    """The CLOB token that is the book for this binary market's YES side.

    Gamma serves ``outcomes`` and ``clob_token_ids`` index-aligned, and for a
    "Will <team> win?" market that is ``["Yes","No"]`` / ``[yesTok, noTok]``.
    The YES token is looked up BY NAME rather than taken at index 0, and a
    market whose outcomes do not name a "Yes" returns None instead of guessing.

    That refusal is the Q489 lesson written down: mapping a token to the wrong
    leg does not make a card stale, it makes it *inverted* — the rendered number
    oscillates between p and 1-p as the two books tick. A dropped tick costs one
    market its live cadence; a mis-attributed one prints a wrong probability.
    """
    tokens = [str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)]
    outcomes = [str(o) for o in (getattr(market, "outcomes", None) or [])]
    if not tokens:
        return None
    for i, name in enumerate(outcomes):
        if name.strip().lower() == "yes" and i < len(tokens):
            return tokens[i]
    return None


def token_for_outcome(market, outcome_name: Optional[str]) -> Optional[str]:
    """The CLOB token that is the book for ONE of our outcome rows.

    ``yes_token_of`` first, unchanged, and its answer wins whenever it has one.
    This adds the one shape it cannot read: a head-to-head market whose Gamma
    ``outcomes`` are the CONTENDERS THEMSELVES rather than ``["Yes","No"]``.

    WHY THIS EXISTS — Q500 taught the fast lane to address a parent row one
    level down, through its outcomes' condition ids, and that closed the
    three-way soccer case: each outcome resolves to its own *"Will <team> win on
    <date>?"* market, outcomes ``["Yes","No"]``, and ``yes_token_of`` reads it.
    A two-way head-to-head does not decompose that way. Gamma answers
    ``0xc72411a3…`` with question *"Detroit Tigers vs. Toronto Blue Jays"*,
    ``outcomes ["Detroit Tigers","Toronto Blue Jays"]`` and two ``clobTokenIds``
    — real tokens on a real book — and ``yes_token_of`` finds no ``"Yes"``, so
    it correctly refuses rather than guessing, and the leg is never subscribed.

    Measured on production 2026-09-16 20:4xZ, hero-speaking markets on the
    live+6h slate that carry no ``clob_token_ids``: Gamma answered 20 outcome
    conditions, **10 fill through the Yes path and 10 fill only through this
    one** — Tigers/Blue Jays, Dodgers/Reds, Brewers/Pirates, Athletics/Rays.
    Every MLB game on the board was in the second half. Their hero legs sat on
    the 120 s poll sawtooth (eight live events sharing the identical stamp
    ``20:38:58.300``) while the Kalshi arm of the SAME events streamed at
    sub-30 s, and Gamma moved Detroit 0.255 -> 0.195 inside one poll interval.

    STILL BY NAME, NEVER BY POSITION. Q489's lesson is not "look for Yes", it is
    "attribute a token to the leg it is actually the book for, or drop the
    tick": a mis-attributed token does not make a card stale, it makes it
    *inverted*. So the fallback matches OUR outcome's own name against Gamma's
    outcome list and takes the index-aligned token, and it refuses on anything
    it cannot prove — no match, or more than one, returns None exactly as today.

    PURELY ADDITIVE, and that is the safety argument rather than a hope: this
    function can only return a token where ``yes_token_of`` returned None, so no
    leg that streams today can be moved, re-attributed or lost by it. The worst
    case is the present behaviour.
    """
    token = yes_token_of(market)
    if token:
        return token

    tokens = [str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)]
    outcomes = [str(o) for o in (getattr(market, "outcomes", None) or [])]
    if not tokens or not outcome_name:
        return None

    want = outcome_name.strip().lower()
    if not want:
        return None
    hits = [i for i, name in enumerate(outcomes) if name.strip().lower() == want]
    # Exactly one, or nothing. Two outcomes sharing a name is a shape we cannot
    # resolve, and picking the first would be the positional guess this whole
    # module refuses to make.
    if len(hits) != 1 or hits[0] >= len(tokens):
        return None
    return tokens[hits[0]]


async def topup_outcome_clob_tokens(
    session,
    outcomes: list[tuple[int, int, Optional[str]]],
    *,
    service=None,
    max_outcomes: int = MAX_TOPUP_MARKETS,
) -> dict[int, tuple[int, str]]:
    """Fetch the YES token for each OUTCOME of a parent/field market.

    ``outcomes`` is ``[(market_id, outcome_id, outcome_external_id), ...]``.
    Returns ``{outcome_id: (market_id, yes_token)}`` for those actually filled.

    WHY THIS EXISTS — the moneyline leg was the one leg that never streamed.
    ``topup_clob_tokens`` addresses a FuturesMarket by its own ``external_id``,
    and ``condition_id_of`` correctly returns None for a parent row, whose
    ``external_id`` is a bare Gamma EVENT id (``"917153"``). So a three-way
    soccer market — the only market on the event that can answer "who wins",
    and therefore the only one ``compute_source_home_probability`` can read —
    was never asked for tokens, never subscribed, and moved only on the 120s
    poll. Measured on production 2026-09-01: across every live event, the
    ``betting`` blend stamp had p50 age 23s while ``kalshi`` and ``polymarket``
    sat at p50 122s with **0 of 9 events fresher than two minutes**. The socket
    was streaming the whole time — into Over/Under and Both-Teams-To-Score
    props, none of which the hero renders.

    The tokens were addressable all along, one level down: a field market's
    OUTCOMES each carry a real condition id, and each resolves to its own binary
    market. Verified against production Gamma the same day —
    ``0xfa91ccd0…`` → *"Will Wolfsberger AC win on 2026-09-01?"*, outcomes
    ``["Yes","No"]``, two ``clobTokenIds``.

    ONLY ONE TOKEN PER OUTCOME IS RETURNED, and only the one that IS that
    outcome's book. On a ``["Yes","No"]`` sub-market that is the YES token: the
    NO book is P(not this outcome), and on a three-way market that is not any
    other outcome row — it is the other two combined — so there is no leg to
    write it to and it is never subscribed rather than written somewhere
    plausible. On a two-way head-to-head, whose Gamma ``outcomes`` are the
    contenders themselves, it is the token index-aligned with OUR outcome's own
    name; the other contender's token is that market's other leg and is left to
    the outcome row that owns it. ``token_for_outcome`` holds both rules and
    refuses anything it cannot attribute by name.

    WHAT IS ASKED WHEN THE SLATE EXCEEDS THE CAP is a resuming window, not the
    lexicographic head — ``select_ask_window`` carries that argument and the
    measurement behind it. A leg that can never be filled therefore costs one
    seat for one pass rather than holding it for good.

    WHAT IS NOT ASKED AT ALL is a leg whose game finished days ago. The caller's
    slate has no lower bound on start time, so events stuck at 'scheduled' kept
    their legs in the ask for ever — 73% of it, measured. ``STALE_EVENT_HOURS``
    and the block that applies it carry that argument, including why the
    predicate is the event's START TIME and not any settlement column.
    """
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Event, FuturesMarket, FuturesOutcome

    # condition id -> (market_id, outcome_id). Keyed by condition id because
    # that is what Gamma echoes back, and it de-dupes an outcome accidentally
    # sharing a condition with a sibling rather than letting both claim a tick.
    addressable: dict[str, tuple[int, int]] = {}
    for market_id, outcome_id, external_id in outcomes:
        cid = condition_id_of(external_id)
        if cid:
            addressable[cid] = (market_id, outcome_id)

    if not addressable:
        return {}

    # WHAT IS ALREADY STORED IS RETURNED, NEVER RE-ASKED. The cap below keeps the
    # lexicographically lowest condition ids, and the caller drops a market from
    # `outcomes` only when it carries the MARKET-level `clob_token_ids` — it never
    # reads `OUTCOME_TOKEN_METADATA_KEY`, the key this function writes. So without
    # this read the ask never shrinks: every recycle re-derives the same set, sorts
    # it the same way, and re-asks the same head, while everything above the
    # boundary is starved permanently rather than "deferred to the next recycle".
    #
    # Measured on production 2026-09-16 22:39-22:47Z (#6634): 1,706 addressable
    # outcomes against a cap of 300 — the constant was sized as "~4x headroom" for
    # a slate an order of magnitude smaller — boundary `0x2b8f76c0…`. Of nine live
    # MLB hero legs, the one below the boundary (Red Sox/Rangers `0x0614…`) carried
    # its token and streamed off-beat at 22:42:06.181160, while eight above it sat
    # on the 120 s poll sawtooth, six sharing the identical stamp 22:40:58.322131.
    # Gamma answered the misses with the shape #6617 handles and names that match
    # verbatim, so the cap was the whole difference.
    #
    # Seeded into `filled` rather than merely skipped: the return value IS the
    # socket's subscription list, so dropping a stored outcome would unsubscribe
    # the very legs this module exists to keep streaming.
    # The event's start time rides along on this read rather than taking a
    # second round trip: staleness is a property of the MARKET's parent event,
    # so it has the same grain as the row this query already returns, and this
    # runs on the socket's event loop every recycle.  Outer join — a market with
    # no linked event yields NULL and is KEPT, never dropped (below).
    stored_filled: dict[int, tuple[int, str]] = {}
    stale_market_ids: set[int] = set()
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_EVENT_HOURS)
    try:
        stored_rows = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.market_metadata,
                Event.commence_time,
            )
            .outerjoin(Event, FuturesMarket.event_id == Event.id)
            .where(FuturesMarket.id.in_({mid for mid, _oid in addressable.values()}))
        )
        for stored_market_id, metadata, commence_time in stored_rows.all():
            if _is_stale(commence_time, stale_cutoff):
                stale_market_ids.add(stored_market_id)
            stored = (metadata or {}).get(OUTCOME_TOKEN_METADATA_KEY)
            if not isinstance(stored, dict):
                continue
            for raw_outcome_id, token in stored.items():
                if not token:
                    continue
                try:
                    stored_filled[int(raw_outcome_id)] = (
                        stored_market_id,
                        str(token),
                    )
                except (TypeError, ValueError):
                    # A key we cannot read is left to be re-asked, which is the
                    # behaviour that predates this block.
                    continue
    except Exception:
        # Never take the socket's token pass down for a bookkeeping read: without
        # it the whole slate is asked again, which is today's behaviour rather
        # than a new failure.
        logger.exception(
            "Polymarket outcome token top-up: stored-token read failed; "
            "re-asking the whole slate this pass"
        )
        stored_filled = {}
        # Fail OPEN on staleness too: with no start times read, nothing is known
        # to be stale, so nothing is dropped.  A failed bookkeeping read must
        # never be able to shrink the ask — that would be a silent outage
        # wearing the shape of a healthy pass (gotcha #53).
        stale_market_ids = set()

    if stored_filled:
        addressable = {
            cid: entry
            for cid, entry in addressable.items()
            if entry[1] not in stored_filled
        }
        if not addressable:
            # Everything on the slate is already known. Still a full answer, so
            # the caller subscribes exactly as it would have.
            logger.info(
                "Polymarket outcome token top-up: 0 outcomes to ask, %d already "
                "stored",
                len(stored_filled),
            )
            return stored_filled

    if stale_market_ids:
        # DROPPED AFTER THE STORED SHRINK, DELIBERATELY. `stored_filled` is
        # already seeded into the return value above, and the return value IS
        # the socket's subscription list — so filtering here can only remove
        # legs from what is ASKED, never unsubscribe a leg whose token we hold.
        #
        # WHY THE ASK IS FULL OF CORPSES. The caller's slate is
        # `Event.status = 'live' OR (status = 'scheduled' AND commence_time <=
        # NOW() + 6h)`, and that window has no LOWER bound, so an event stuck at
        # 'scheduled' whose game finished weeks ago satisfies it for ever.
        # Measured on production 2026-09-17 07:0xZ: of 4,148 slate outcomes,
        # 3,050 sat on markets whose event had commenced up to FIFTEEN WEEKS
        # earlier — 2,996 of them more than 12 h ago. The ask was 73% dead, the
        # 300 cap bound on the corpses, and a live leg waited ~7 passes for a
        # turn it should get in 2.
        #
        # WHY START TIME AND NOT A SETTLEMENT COLUMN. `status = 'resolved'` was
        # the obvious predicate and it is WRONG HERE: measured the same hour,
        # the four live ITF tennis legs this ship exists to reach
        # (`W35 Kyoto`, `Phan Thiet 4`, events 15313682 / 15313516 / 15313625)
        # were themselves `status = 'resolved'` while still in play, carrying
        # `is_winner = False` on BOTH contenders — the column's own default, not
        # a settlement. Filtering on it would have dropped exactly the legs
        # #837 is about. `settled_at` is no better: it is NULL on 66 of 576
        # sampled corpses and the model says it is never backfilled. The start
        # time is the one signal that is written by ingest for every row,
        # independent of whether anything ever streamed the market.
        #
        # ONLY A POSITIVELY KNOWN OLD START DROPS A LEG: a NULL start time, an
        # unlinked market, or a failed read all KEEP it. This refuses rather
        # than guesses, the same way `token_for_outcome` does.
        before = len(addressable)
        addressable = {
            cid: entry
            for cid, entry in addressable.items()
            if entry[0] not in stale_market_ids
        }
        logger.info(
            "Polymarket outcome token top-up: dropped %d of %d outcomes whose "
            "event started more than %dh ago; %d remain askable",
            before - len(addressable),
            before,
            STALE_EVENT_HOURS,
            len(addressable),
        )
        if not addressable:
            # Every askable leg is stale. Still a full answer for the caller:
            # the stored legs stay subscribed exactly as they would have.
            return dict(stored_filled)

    if len(addressable) > max_outcomes:
        # "Deferred to the next recycle" was a claim nothing kept: the head was
        # re-selected every pass and the tail was starved for good. The window
        # now RESUMES where the last pass stopped, so the sentence is true and
        # the bound is ceil(len / max_outcomes) passes at any cadence — see
        # `select_ask_window`, which holds the whole argument.
        cursor = await load_topup_cursor()
        kept, next_cursor = select_ask_window(
            sorted(addressable), max_outcomes, cursor
        )
        # Saved BEFORE the ask, not after it: a Gamma failure must cost this
        # slice one pass, not hold the window at the same slice until Gamma
        # recovers — which is the livelock this replaces, with a different cause.
        await save_topup_cursor(next_cursor)
        logger.warning(
            "Polymarket outcome token top-up: %d outcomes needed tokens, "
            "capped at %d (%d deferred to the next recycle; window resumed "
            "after %s, stops at %s)",
            len(addressable),
            max_outcomes,
            len(addressable) - max_outcomes,
            cursor or "the front",
            next_cursor,
        )
        addressable = {cid: addressable[cid] for cid in kept}

    # Our own name for each outcome, for the head-to-head shape whose Gamma
    # `outcomes` are the contenders rather than ["Yes","No"] — see
    # `token_for_outcome`. Read HERE rather than widened into the `outcomes`
    # argument on purpose: the caller is `polymarket_ws`, another lane's file,
    # and this keeps the repair inside one module. One batched `IN` bounded by
    # `max_outcomes`, and a name we cannot read simply leaves that outcome on
    # the Yes path exactly as before.
    name_by_outcome: dict[int, str] = {}
    try:
        name_rows = await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.name).where(
                FuturesOutcome.id.in_([oid for _mid, oid in addressable.values()])
            )
        )
        name_by_outcome = {oid: (name or "") for oid, name in name_rows.all()}
    except Exception:
        # Never take the socket's token pass down for a name lookup: without it
        # every outcome falls through to the Yes path, which is today's
        # behaviour, not a new failure.
        logger.exception(
            "Polymarket outcome token top-up: outcome-name read failed; "
            "continuing with the Yes path only"
        )

    own_service = service is None
    if own_service:
        from app.services.polymarket_api import PolymarketAPIService

        service = PolymarketAPIService()

    try:
        # The CLIENT still raises on a 429 or a 5xx (gotcha #36) — an empty list
        # from it would read as "these outcomes have no tokens", the exact false
        # negative that hid this gap for the market-level path. What changes
        # here is only what THIS function does with the raise.
        #
        # WHY IT IS CAUGHT, and why ONLY WITH SOMETHING STORED. The caller
        # (`polymarket_ws`) answers an exception out of this function with
        # `outcome_yes_token = {}` — so one Gamma failure unsubscribes every
        # moneyline leg whose token we already hold and had no need to ask
        # about. The provider being down is not a reason to stop streaming the
        # legs that are already mapped; their tokens were read before this call
        # and are still valid. So a failed ASK returns what is already KNOWN.
        #
        # With nothing stored there is nothing known, and `{}` would say "these
        # outcomes have no tokens" — the exact false negative gotcha #36 forbids
        # and the one that hid this whole gap for the market-level path. So that
        # case RE-RAISES, exactly as it did before this ship, and the caller
        # logs the outage. The difference between the two arms is whether this
        # function has an answer of its own, never whether the provider failed.
        #
        # Loud either way (gotcha #53 / `task_verdict`): the swallowed arm logs
        # the traceback and both counts, so a Gamma outage still reads as an
        # outage rather than as a quiet pass that mapped nothing.
        fetched = await service.get_markets_by_conditions(list(addressable))
    except Exception:
        if not stored_filled:
            raise
        logger.exception(
            "Polymarket outcome token top-up: Gamma failed for %d outcomes; "
            "keeping the %d already-stored legs subscribed and retrying the "
            "rest next recycle",
            len(addressable),
            len(stored_filled),
        )
        return dict(stored_filled)
    finally:
        if own_service:
            await service.close()

    # Seeded with what is already stored so the caller subscribes to those legs
    # too; `by_market` stays empty for them, so a known token is never rewritten.
    filled: dict[int, tuple[int, str]] = dict(stored_filled)
    by_market: dict[int, dict[str, str]] = {}
    named_fallback = 0
    for market in fetched:
        entry = addressable.get(getattr(market, "condition_id", "") or "")
        if entry is None:
            continue
        market_id, outcome_id = entry
        token = token_for_outcome(market, name_by_outcome.get(outcome_id))
        if not token:
            continue
        if not yes_token_of(market):
            named_fallback += 1
        filled[outcome_id] = (market_id, token)
        by_market.setdefault(market_id, {})[str(outcome_id)] = token

    for market_id, token_map in by_market.items():
        # Nested merge, not a replace: the outer `||` protects sibling metadata
        # keys (`polymarket_event_id`, `matchup_title`) exactly as the
        # market-level top-up does, and the INNER one protects outcome entries
        # stamped on an earlier pass — `||` is shallow, so writing the key with
        # only this pass's outcomes would silently drop the rest.
        await session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id == market_id)
            .values(
                market_metadata=func.coalesce(
                    FuturesMarket.market_metadata, cast(literal("{}"), JSONB)
                ).op("||")(
                    func.jsonb_build_object(
                        OUTCOME_TOKEN_METADATA_KEY,
                        func.coalesce(
                            FuturesMarket.market_metadata.op("->")(
                                OUTCOME_TOKEN_METADATA_KEY
                            ),
                            cast(literal("{}"), JSONB),
                        ).op("||")(cast(literal(json.dumps(token_map)), JSONB)),
                    )
                )
            )
        )

    # `named` is kept APART from the total for the reason every other counter in
    # this module is: one number cannot say "the Yes path is healthy" and "the
    # head-to-head path is reaching anything". A pass with `mapped` high and
    # `named` 0 on an MLB evening is the fallback having gone dark, and the
    # total would report that pass as a good one.
    # `stored` is kept apart from `mapped` for the same reason `named` is: a pass
    # that asked nothing because everything was already known, and a pass that
    # asked and filled, are different events, and one total reports them alike.
    logger.info(
        "Polymarket outcome token top-up: %d outcomes asked, %d returned by "
        "Gamma, %d newly mapped across %d markets (%d via the outcome-name "
        "fallback), %d already stored, %d subscribable",
        len(addressable),
        len(fetched),
        len(filled) - len(stored_filled),
        len(by_market),
        named_fallback,
        len(stored_filled),
        len(filled),
    )
    return filled


async def topup_clob_tokens(
    session,
    markets: list[tuple[int, Optional[str]]],
    *,
    service=None,
    max_markets: int = MAX_TOPUP_MARKETS,
) -> dict[int, list[str]]:
    """Fetch and persist ``clob_token_ids`` for ``markets`` that lack them.

    ``markets`` is ``[(futures_market_id, external_id), ...]``.  Returns
    ``{futures_market_id: [token, ...]}`` for the markets that were actually
    filled, so the caller can subscribe in the same pass rather than waiting for
    the next recycle to re-read the row it just wrote.

    Writes MERGE (``COALESCE(md,'{}') || jsonb_build_object(...)``), the same
    idiom the ingest uses, so a top-up cannot clobber ``polymarket_event_id``,
    ``matchup_title`` or the venue-settled stamp that share this column.
    """
    from sqlalchemy import cast, func, literal, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import FuturesMarket

    addressable: dict[str, int] = {}
    for market_id, external_id in markets:
        cid = condition_id_of(external_id)
        if cid:
            addressable[cid] = market_id

    if not addressable:
        return {}

    if len(addressable) > max_markets:
        # Loud, not silent — and deterministic, so a repeated run makes progress
        # through the same order rather than re-drawing the same truncated slice.
        kept = sorted(addressable)[:max_markets]
        logger.warning(
            "Polymarket token top-up: %d markets needed tokens, capped at %d "
            "(%d deferred to the next recycle)",
            len(addressable),
            max_markets,
            len(addressable) - max_markets,
        )
        addressable = {cid: addressable[cid] for cid in kept}

    own_service = service is None
    if own_service:
        from app.services.polymarket_api import PolymarketAPIService

        service = PolymarketAPIService()

    try:
        # Rate-limit and server errors re-raise out of this call by design
        # (gotcha #36) — an empty list would read as "these markets have no
        # tokens", which is exactly the false negative that hid this gap.
        fetched = await service.get_markets_by_conditions(list(addressable))
    finally:
        if own_service:
            await service.close()

    filled: dict[int, list[str]] = {}
    for market in fetched:
        market_id = addressable.get(getattr(market, "condition_id", "") or "")
        if market_id is None:
            continue
        tokens = [
            str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)
        ]
        if not tokens:
            continue

        await session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id == market_id)
            .values(
                market_metadata=func.coalesce(
                    FuturesMarket.market_metadata,
                    cast(literal("{}"), JSONB),
                ).op("||")(
                    func.jsonb_build_object(
                        "clob_token_ids",
                        cast(literal(json.dumps(tokens)), JSONB),
                    )
                )
            )
        )
        filled[market_id] = tokens

    logger.info(
        "Polymarket token top-up: %d markets asked, %d returned by Gamma, "
        "%d stamped with tokens",
        len(addressable),
        len(fetched),
        len(filled),
    )
    return filled
