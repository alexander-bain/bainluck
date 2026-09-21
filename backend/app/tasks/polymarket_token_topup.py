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

#: The ONLY event status an outcome may be aged out on (#837).  The caller's
#: slate admits two — ``'live'``, and ``'scheduled'`` starting within 6 h — and
#: an event that reached ``'live'`` is never dropped no matter how old its start
#: time is, because that is the event graph saying the game is happening now.
#:
#: Measured on production 2026-09-17 07:5xZ, and this is why the guard costs
#: nothing: of the slate legs older than ``STALE_EVENT_HOURS``, 2,996 of 2,996
#: are ``'scheduled'`` and NONE is ``'live'`` — there is no live event anywhere
#: in the table with a start time that old.  The clause therefore removes a
#: whole class of wrong drop without changing a single leg of the repair.
STALE_EVENT_STATUS = "scheduled"


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


def _is_stale(commence_time, status, cutoff: datetime) -> bool:
    """True only for a leg KNOWN to be a corpse: old start AND never left the gate.

    TWO conditions, and the second one is the guard rather than a refinement.
    AGE ALONE MAY NOT DROP A LEG.  The caller's slate admits an event on either
    of two statuses — ``'live'``, or ``'scheduled'`` starting within 6 h — and an
    event that reached ``'live'`` is one the rest of the system believes is
    happening NOW, whatever its start time says.  Aging such a leg out would be
    this module deciding a game is over on a clock, against the event graph's own
    reading, and dropping exactly the live winner line #837 exists to reach.  So
    only ``STALE_EVENT_STATUS`` — the status the corpses are stuck on — is
    eligible, and every other status keeps its leg.

    That is also what makes the predicate honest about what it detects.  The
    3,050 dead legs are not "old": they are events stuck at ``'scheduled'`` whose
    games finished weeks ago and whose rows nothing ever advanced (an event-state
    defect, filed on #837, not fixable here).  Never transitioning IS the corpse
    signature; the age bound only separates that from tonight's fixtures.

    Every unknown is False — unknown is not stale.  A missing start time, a
    missing status, an unlinked market or a value we cannot compare keeps its leg
    in the ask, so the worst case of this whole filter is today's behaviour.
    That asymmetry is the safety argument: the cost of wrongly keeping a dead leg
    is one seat for one pass, and the cost of wrongly dropping a live one is a
    hero line that never streams.

    A naive datetime is read as UTC rather than refused.  The column is
    ``timestamptz`` so production always hands back an aware value; the coercion
    exists because a naive one would otherwise raise inside the comparison and
    take the socket's token pass down with it.
    """
    if status != STALE_EVENT_STATUS:
        return False
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
    with a ``_yes`` / ``_no`` / ``_side1`` suffix, and a caller holding the wrong
    one is a 404 (the reason `12fd2496` exists).  ``removesuffix`` rather than the
    ``rstrip("_yes")`` in that commit: ``rstrip`` takes a CHARACTER SET, so it
    eats any trailing run of ``_``/``y``/``e``/``s`` — on a hex condition id
    ending in ``e`` it silently truncates a real character.

    ``_side1`` is #7505's companion leg, written beside the BARE id on a
    sole-moneyline event where the decomposition that makes a ``_yes``/``_no``
    pair never runs.  Without it here the companion's id never reduces to a
    condition id, ``condition_id_of`` returns None on an id that plainly starts
    ``0x``, and the leg gets no CLOB token top-up — so the one row a reader was
    given a price for is the one row whose book goes cold.  The suffixes are
    chained rather than listed because they are mutually exclusive by
    construction: a leg wears exactly one.

    Returns None for parent rows, whose ``external_id`` is a Gamma EVENT id
    (a bare integer), not a condition id.  Those rows are addressable one level
    down, by their OUTCOMES' condition ids — see ``topup_outcome_clob_tokens``,
    which is the caller that does it. Guessing which kind an id is would be the
    bug this function prevents; ``0x`` is the discriminator.
    """
    if not external_id:
        return None
    cid = (
        external_id.removesuffix("_yes").removesuffix("_no").removesuffix("_side1")
    )
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

    OUR OWN OUTCOME'S NAME IS TRIED FIRST, and ``yes_token_of`` is the fallback
    for the rows that name is silent about. This reads both shapes: a market
    whose Gamma ``outcomes`` are ``["Yes","No"]``, and a head-to-head whose
    ``outcomes`` are the CONTENDERS THEMSELVES.

    🔴 WHY THE NAME GOES FIRST, and why the other order was a live inversion.
    ``yes_token_of`` answers "which token is the YES side of this market" — a
    question about the MARKET. It cannot see which of our rows is asking. When
    one condition id carries BOTH of our outcome rows (a ``…_yes`` / ``…_no``
    pair, which is every binary sub-market — 384 of the 385 live condition ids
    measured 2026-09-17 09:2xZ), the ``_no`` row asking this function is handed
    the YES token, because ``yes_token_of`` has an answer and its answer wins.
    That is not a stale leg, it is the Q489 *inversion*: the row renders ``p``
    where the truth is ``1-p``. Two live rows have the shape that would trip it —
    ``0xd7a5b002…`` and ``0x4dc1cca8…``, our row named ``"No"``, Gamma
    ``outcomes ["Yes","No"]``.

    ⚠️ NEITHER IS ACTUALLY INVERTED ON A SCREEN, and an earlier version of this
    note said they were. Both markets carry market-level ``clob_token_ids``, so
    the socket attributes their legs through the Q489 zip and never asks this
    function about them. The branch is latent, and it is repaired on that
    footing rather than on a reader-visible one — see the work-set comment in
    ``topup_outcome_clob_tokens`` for the reach measurement. Trying our own name
    first is what makes the answer a statement about the ROW; nothing else in
    the shape distinguishes them.

    NOTHING THAT IS CORRECT TODAY MOVES. The name path only fires on an exact,
    unique match against Gamma's own outcome list, and where it fires the old
    order agreed with it or was wrong: a row named ``"Yes"`` matches index 0,
    which is what ``yes_token_of`` returned; a row named ``"Wolfsberger AC"``
    against ``["Yes","No"]`` matches nothing and still falls through to the Yes
    token; a row named ``"Under"`` against ``["Over","Under"]`` reached the name
    path before this change too, because ``yes_token_of`` had refused.

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
    it cannot prove — no match, or more than one, falls back rather than guesses.
    """
    tokens = [str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)]
    outcomes = [str(o) for o in (getattr(market, "outcomes", None) or [])]
    if not tokens:
        return None

    want = (outcome_name or "").strip().lower()
    if want:
        hits = [i for i, name in enumerate(outcomes) if name.strip().lower() == want]
        # Exactly one, or fall through. Two outcomes sharing a name is a shape we
        # cannot resolve, and picking the first would be the positional guess
        # this whole module refuses to make.
        if len(hits) == 1 and hits[0] < len(tokens):
            return tokens[hits[0]]

    return yes_token_of(market)


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

    ONLY ONE TOKEN PER OUTCOME ROW IS RETURNED, and only the one that IS that
    row's book — but a condition id may carry MORE THAN ONE of our rows, and
    then each gets its own. That is the ordinary binary shape, not an edge case:
    our outcome rows store the condition id with a ``_yes`` / ``_no`` suffix, so
    both legs of a two-way market share one id and each names one of Gamma's two
    ``clobTokenIds``. On a three-way market the NO book is the other two
    contenders combined, so it is not any outcome row of ours and is never
    subscribed rather than written somewhere plausible.
    ``token_for_outcome`` decides which token belongs to which row, by that
    row's own name, and refuses anything it cannot attribute.

    WHAT IS ASKED WHEN THE SLATE EXCEEDS THE CAP is a resuming window, not the
    lexicographic head — ``select_ask_window`` carries that argument and the
    measurement behind it. A leg that can never be filled therefore costs one
    seat for one pass rather than holding it for good.

    WHAT IS NOT ASKED AT ALL is a leg whose game finished days ago. The caller's
    slate has no lower bound on start time, so events stuck at 'scheduled' kept
    their legs in the ask for ever — 73% of it, measured. ``STALE_EVENT_HOURS``,
    ``STALE_EVENT_STATUS`` and the block that applies them carry that argument,
    including why the predicate is the event's START TIME plus its STATUS and
    not any settlement column, and why an event the graph calls 'live' is never
    aged out however old its start time reads.
    """
    from sqlalchemy import cast, func, literal, select, update
    from sqlalchemy.dialects.postgresql import JSONB

    from app.models.models import Event, FuturesMarket, FuturesOutcome

    # condition id -> [(market_id, outcome_id), ...]. Keyed by condition id
    # because that is what Gamma echoes back and what the ask is billed in; the
    # VALUE is a list because sharing a condition id is the normal shape, not an
    # accident, and both sharers have a real book.
    #
    # 🔴 A DICT HERE CAPPED LIVE COVERAGE AT HALF, PERMANENTLY. Our outcome rows
    # store a condition id with a ``_yes`` / ``_no`` suffix, so a binary
    # sub-market's two rows differ only in that suffix and `condition_id_of`
    # maps both to one key. With a scalar value the second assignment overwrote
    # the first, so exactly one of the two legs was ever asked about — and it
    # was not a fair coin: the caller orders by `FuturesOutcome.id` and the
    # `_no` row is minted second, so the `_no` leg won every collision and the
    # `_yes` leg was never subscribed. Nor was it retried: once the survivor's
    # token is stored, the stored-shrink below drops the whole condition id from
    # the ask, so its sibling is unreachable for good rather than next recycle.
    #
    # Measured against production and Gamma 2026-09-17 09:2x-09:5xZ: 385
    # condition ids carry an outcome row on a `status='live'` event, 384 of them
    # holding EXACTLY TWO of our rows — the collapsing shape, and essentially the
    # whole binary population.
    #
    # ⚠️ AND IT COSTS ZERO LEGS TODAY, which is stated here so the next reader
    # does not re-derive a payoff from the shape. All 385 of those markets carry
    # market-level `clob_token_ids`, so `polymarket_ws` excludes them from
    # `outcome_topup_targets` and attributes both legs positionally through the
    # Q489 zip; this function never sees them. Of the 235 slate markets that DO
    # lack market-level tokens — the population this function is handed — exactly
    # 38 condition ids are pairs, and every one sits on a `status='scheduled'`
    # event older than `STALE_EVENT_HOURS`, which the filter below drops before
    # the ask is built. The repair is a latent one: it holds the invariant this
    # function claims (one token per ROW, attributed to that row) against the day
    # a binary reaches it without an ingest-stamped market-level pair.
    addressable: dict[str, list[tuple[int, int]]] = {}
    for market_id, outcome_id, external_id in outcomes:
        cid = condition_id_of(external_id)
        if not cid:
            continue
        # Not de-duplicated, deliberately: a repeated row resolves to the same
        # token, writes the same metadata key and lands on the same entry of
        # `filled`, so a guard here would have nothing observable to protect and
        # would be a test that cannot fail.
        addressable.setdefault(cid, []).append((market_id, outcome_id))

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
    # The event's start time AND status ride along on this read rather than
    # taking a second round trip: staleness is a property of the MARKET's parent
    # event, so both have the same grain as the row this query already returns,
    # and this runs on the socket's event loop every recycle.  Outer join — a
    # market with no linked event yields NULL for both and is KEPT, never
    # dropped (below).  Two columns, not one, because age alone may not drop a
    # leg: see `_is_stale` and `STALE_EVENT_STATUS`.
    stored_filled: dict[int, tuple[int, str]] = {}
    stale_market_ids: set[int] = set()
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_EVENT_HOURS)
    try:
        stored_rows = await session.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.market_metadata,
                Event.commence_time,
                Event.status,
            )
            .outerjoin(Event, FuturesMarket.event_id == Event.id)
            .where(
                FuturesMarket.id.in_(
                    {
                        mid
                        for entries in addressable.values()
                        for mid, _oid in entries
                    }
                )
            )
        )
        for stored_market_id, metadata, commence_time, event_status in stored_rows.all():
            if _is_stale(commence_time, event_status, stale_cutoff):
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
        # PER ROW, NOT PER CONDITION ID. A condition id stays in the ask while
        # ANY of its rows is still unmapped, and only the rows that are already
        # known are dropped from it — they are seeded into `filled` above, so
        # they stay subscribed without being re-asked. Shrinking by condition id
        # is what made a sibling unreachable for good: the first leg to be
        # stored took the whole id out of the ask with it.
        addressable = {
            cid: unstored
            for cid, entries in addressable.items()
            if (unstored := [e for e in entries if e[1] not in stored_filled])
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
        # AGE ALONE DOES NOT DROP A LEG. The event must ALSO still be sitting at
        # `STALE_EVENT_STATUS` — the status the corpses never left. An event the
        # graph has moved to 'live' keeps its leg however old its start time
        # reads, because that column is the rest of the system saying the game
        # is happening now, and overruling it on a clock would drop the live
        # winner line this ship exists to reach. Measured 2026-09-17 07:5xZ:
        # 2,996 of 2,996 slate legs past the bound are 'scheduled' and no live
        # event of that age exists at all, so the guard costs zero legs here.
        #
        # ONLY A POSITIVELY KNOWN OLD START ON A POSITIVELY KNOWN 'scheduled'
        # EVENT DROPS A LEG: a NULL start time, a NULL status, an unlinked
        # market, or a failed read all KEEP it. This refuses rather than
        # guesses, the same way `token_for_outcome` does.
        #
        # COUNTED IN OUTCOME ROWS, which is what the sentence says and what the
        # previous version of this line did NOT report: it counted dict entries
        # while one entry stood for a whole condition id, so "dropped N of M
        # outcomes" was in condition ids and any threshold read off it was in
        # the wrong unit. The filter is per row for the same reason the shrink
        # above is.
        before = sum(len(entries) for entries in addressable.values())
        addressable = {
            cid: kept_entries
            for cid, entries in addressable.items()
            if (kept_entries := [e for e in entries if e[0] not in stale_market_ids])
        }
        after = sum(len(entries) for entries in addressable.values())
        logger.info(
            "Polymarket outcome token top-up: dropped %d of %d outcome legs "
            "whose event started more than %dh ago; %d remain askable across "
            "%d condition ids",
            before - after,
            before,
            STALE_EVENT_HOURS,
            after,
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
        #
        # CAPPED IN CONDITION IDS, deliberately and unchanged: `max_outcomes`
        # bounds the ASK, and Gamma is asked one query parameter per condition
        # id however many of our rows ride on it. Counting legs here would
        # shrink the request for no reason — the sibling leg this ship reaches
        # is answered by a response the pass was already paying for. The log
        # states both numbers so the two units are never read as one.
        cursor = await load_topup_cursor()
        kept, next_cursor = select_ask_window(
            sorted(addressable), max_outcomes, cursor
        )
        # Saved BEFORE the ask, not after it: a Gamma failure must cost this
        # slice one pass, not hold the window at the same slice until Gamma
        # recovers — which is the livelock this replaces, with a different cause.
        await save_topup_cursor(next_cursor)
        logger.warning(
            "Polymarket outcome token top-up: %d condition ids needed tokens "
            "(%d outcome legs), capped at %d (%d deferred to the next recycle; "
            "window resumed after %s, stops at %s)",
            len(addressable),
            sum(len(entries) for entries in addressable.values()),
            max_outcomes,
            len(addressable) - max_outcomes,
            cursor or "the front",
            next_cursor,
        )
        addressable = {cid: addressable[cid] for cid in kept}

    # Our own name for each outcome — the signal `token_for_outcome` attributes
    # on. Read HERE rather than widened into the `outcomes` argument on purpose:
    # the caller is `polymarket_ws`, another lane's file, and this keeps the
    # repair inside one module. One batched `IN`, and a name we cannot read
    # simply leaves that outcome on the Yes path exactly as before.
    name_by_outcome: dict[int, str] = {}
    try:
        name_rows = await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.name).where(
                FuturesOutcome.id.in_(
                    [
                        oid
                        for entries in addressable.values()
                        for _mid, oid in entries
                    ]
                )
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
            "Polymarket outcome token top-up: Gamma failed for %d condition "
            "ids; keeping the %d already-stored legs subscribed and retrying "
            "the rest next recycle",
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
    reattributed = 0
    for market in fetched:
        entries = addressable.get(getattr(market, "condition_id", "") or "")
        if not entries:
            continue
        # EVERY row on this condition id, not one of them. One Gamma answer
        # carries both books of a binary, and each is the book for exactly one
        # of our rows; `token_for_outcome` decides which by that row's own name
        # and still refuses anything it cannot attribute.
        yes_token = yes_token_of(market)
        for market_id, outcome_id in entries:
            token = token_for_outcome(market, name_by_outcome.get(outcome_id))
            if not token:
                continue
            if token != yes_token:
                # Unreachable through the Yes path: either the market names no
                # "Yes" at all, or this row's book is the other side of one that
                # does. The second case is the inversion `reattributed` counts.
                named_fallback += 1
                if yes_token:
                    reattributed += 1
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
    # `reattributed` is apart from both because it is the only counter that is
    # a REPAIR rather than a yield: a leg whose market does name a "Yes" and
    # whose book is the other side of it. Those are the rows the old ordering
    # handed the YES token to, so a non-zero here is the inversion being caught
    # in flight — and a zero on a slate full of `_yes`/`_no` pairs is this
    # attribution having gone dark, which no total would show.
    # ASKED IS IN CONDITION IDS, MAPPED IS IN OUTCOME LEGS, and they are labelled
    # so because they are different units and the pass is judged on both.
    logger.info(
        "Polymarket outcome token top-up: %d condition ids asked (%d outcome "
        "legs), %d returned by Gamma, %d newly mapped across %d markets (%d not "
        "reachable via the Yes path, of which %d re-attributed off a named Yes), "
        "%d already stored, %d subscribable",
        len(addressable),
        sum(len(entries) for entries in addressable.values()),
        len(fetched),
        len(filled) - len(stored_filled),
        len(by_market),
        named_fallback,
        reattributed,
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
