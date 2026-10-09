"""Polymarket WebSocket consumer task.

Streams live prices and resolution events from Polymarket's CLOB WebSocket.
No auth required. Runs alongside the Kalshi WS consumer on the same dyno.

Events:
  - best_bid_ask: price updates → FuturesOutcome.current_probability
  - last_trade_price: trade executions → FuturesOutcome.current_probability
  - market_resolved: settlement → FuturesMarket resolved + is_winner
"""

import asyncio
import contextlib
import json
import logging
import math
import os
import time
from collections.abc import Collection, Iterator, Mapping
from typing import Any, Optional
from datetime import datetime, timezone

from app.tasks.kalshi_ws import (
    FINAL_FLUSH_ATTEMPTS,
    PRICE_FLUSH_SECONDS,
    SUBSCRIPTION_REFRESH_SECONDS,
)
from app.tasks.polymarket import _poly_book_is_untradeable
from app.tasks.ws_consumer_sessions import owns_consumer_sessions  # #2471
from app.utils.market_quote_push import queue_market_change
from app.utils.market_settlement import settled_values
from app.utils.repair_lock_budget import (
    SET_LOCK_TIMEOUT_SQL,
    is_lock_timeout,
    lock_timeout_value,
)

logger = logging.getLogger(__name__)

# Ordinary chunks retain their whole rollback boundary; the final drain has
# no later periodic retry and keeps its existing database wait behavior.
PRICE_CHUNK_LOCK_TIMEOUT_MS = 500


class _PMCatalogFlushBoundary:
    """Catalog handover waits for both disjoint flushes without serializing them."""

    def __init__(self):
        self.condition = asyncio.Condition()
        self.active = 0
        self.changing = False

    @contextlib.asynccontextmanager
    async def flushing(self):
        async with self.condition:
            await self.condition.wait_for(lambda: not self.changing)
            self.active += 1
        try:
            yield
        finally:
            async with self.condition:
                self.active -= 1
                self.condition.notify_all()

    @contextlib.asynccontextmanager
    async def updating(self):
        async with self.condition:
            self.changing = True
            try:
                await self.condition.wait_for(lambda: self.active == 0)
            except BaseException:
                self.changing = False
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            async with self.condition:
                self.changing = False
                self.condition.notify_all()


def pm_non_speaking_metadata(metadata: Any) -> bool:
    """Only the shared venue-label refutation can exclude a loaded question."""
    from types import SimpleNamespace
    from app.utils.content_understanding import venue_label_refutes_full_contest_winner

    return venue_label_refutes_full_contest_winner(
        SimpleNamespace(market_metadata=metadata)
    )


class _PMHeadlineEvents(Mapping[int, int]):
    """Live owner-map view; only venue-refuted questions leave WIN cohorts."""

    def __init__(self, events: Mapping[int, int], non_speakers: Collection[int]):
        self.events = events
        self.non_speakers = non_speakers

    def __getitem__(self, outcome_id: int) -> int:
        if outcome_id in self.non_speakers:
            raise KeyError(outcome_id)
        return self.events[outcome_id]

    def __iter__(self) -> Iterator[int]:
        return (oid for oid in self.events if oid not in self.non_speakers)

    def __len__(self) -> int:
        return sum(1 for _ in self)


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


#: #9733. The smallest order Polymarket accepts on a market is 5 shares
#: (Gamma ``orderMinSize``), so a trade smaller than that can only be the
#: leftover of an order someone else mostly filled. On the tape of market
#: 61380825 ("Yankees advance to the ALCS", condition ``0x8bd936dd…``, read
#: 2026-09-30) every trade at an absurd price was such a leftover — No 0.38 × 2
#: (the one that set No = Yes = 0.38 and printed "No 38%" on search), No 0.29
#: × 0.5, No 0.04 × 1.77, Yes 0.48 × 0.87 — while the trades at the market's
#: real price were 3.3 shares and up.
MIN_PRICE_SETTING_TRADE_SHARES = 5.0


def trade_sets_a_price(msg: dict) -> bool:
    """False for a ``last_trade_price`` smaller than the venue's smallest order.

    Such a leftover is a real execution but not a price: nobody could have
    placed an order at that size, so its price tells a reader nothing about
    the market. A frame that states no size, or a size that is not a number, is
    let through exactly as before — this rule refuses only what it can read.
    """
    size = msg.get("size")
    if size is None:
        return True
    try:
        return float(size) >= MIN_PRICE_SETTING_TRADE_SHARES
    except (TypeError, ValueError):
        return True


def trade_prints_outside_wide_book(prob: float, books: tuple) -> bool:
    """True for a trade that swept through a book too wide to price anything.

    #9913. PHI @ ATL, 2026-09-30 18:54Z: the Braves series token's book was
    0.12 × 5 / 0.11 × 394 bid, 0.73 ask, and a 20-share SELL printed at 0.1125,
    the average of 0.12 × 5 and 0.11 × 15 (the tick is a cent, so no resting
    order sat at 0.1125). It cleared #9733's size floor, became Braves 11% and,
    through ``with_complements``, Phillies 89%, while Kalshi read Atlanta 71%.

    A trade fills at resting prices, so it prints at the edge of the book it
    hit or, when it eats more than the top level, beyond it. Beyond the edge of
    a book wider than ``_poly_book_is_untradeable``'s bar means someone emptied
    what little was left, which says nothing about the market's price.

    ``books`` is ``(latest, previous)`` for the token, each ``(bid, ask)`` or
    None. The venue does not promise whether the post-trade book arrives before
    or after the trade: before, the latest book already lacks the level the
    trade ate (0.11 bid, and 0.1125 sits inside it), so the previous book is
    read too, but only when the latest is also wide. A market whose book has
    come back tight is priced by its midpoint and is not second-guessed here.
    """
    latest = books[0] if books else None
    if latest is None or not _poly_book_is_untradeable(*latest):
        return False
    for book in books:
        if book is None or not _poly_book_is_untradeable(*book):
            continue
        bid, ask = book
        if prob < bid or prob > ask:
            return True
    return False


def with_complements(
    targets: list, prob: float, complement_of: dict
) -> list[tuple[int, float]]:
    """``(leg, price)`` for each leg a tick prices, then each one's complement.

    #9733 follow-on. A price for one token of a binary is also a price for the
    other: ``1 - p``. Writing both keeps a Yes/No pair adding to 100 whichever
    token the venue quoted last. Before this, a leg whose own quotes were
    refused or silent kept an old number beside a sibling that moved (Kittle
    524.5+ receiving yards served Yes 77% / No 10%).

    ``complement_of`` holds only the pairs ``complement_pairs`` proved. Any
    other leg comes back alone, at the tick's price, exactly as before. A
    complement that is itself one of ``targets`` keeps its own price.
    """
    priced = [(oid, prob) for oid in targets]
    named = set(targets)
    for oid in targets:
        other = complement_of.get(oid)
        if other is not None and other not in named:
            priced.append((other, round(1.0 - prob, 6)))
            named.add(other)
    return priced


def books_with_complements(
    targets: list, bid: float, ask: float, complement_of: dict
) -> list[tuple[int, float, float]]:
    """``(leg, bid, ask)`` for each leg a book speaks for, then each complement.

    #9934. ``with_complements``' twin for a book instead of a price: the other
    leg of a proved binary is quoted ``1 - ask`` bid, ``1 - bid`` ask. A missing
    bid (0) becomes an ask of 1.0, which ``book_refutes_price`` can never exceed.
    """
    judged = [(oid, bid, ask) for oid in targets]
    named = set(targets)
    for oid in targets:
        other = complement_of.get(oid)
        if other is not None and other not in named:
            judged.append((other, round(1.0 - ask, 6), round(1.0 - bid, 6)))
            named.add(other)
    return judged


async def withdraw_book_refuted_prices(session, books: dict) -> list:
    """Withdraw each held price its leg's current wide book prices out (#9934).

    WHAT A READER SAW. ``/events/15321782`` (PHI @ ATL, Wild Card G2, Top 10th,
    PHI 4–3, 2026-09-30 21:06Z): the Polymarket series card read Braves 93 /
    Phillies 8 while Kalshi read Atlanta 55. The Braves leg held 0.925 from a
    trade at 20:29Z, when ATL led 3–1. By 21:08Z the Braves token's book was
    0.28 bid / 0.91 ask: anyone could buy Braves at 91c, so 92.5 was no longer a
    price. ``handle_price`` refuses a wide book's midpoint (#1578), which is
    right, and that refusal was the only thing it did with the book.

    THE RULE IS #9399's, ported to the socket. ``books`` is ``{leg: (bid, ask)}``
    from the latest wide book per leg. Each stored ``current_probability`` is
    asked ``book_refutes_price`` — #5121's predicate with its half-cent
    tolerance and its empty-book carve-out — and a refuted one is withdrawn:
    the two rendered columns go to NULL, ``price_changed_at`` moves (a price
    going away is a move), ``last_updated`` does not (no price is fresher than
    the one withdrawn), and a crowned or graded row is never touched. Each
    UPDATE re-asserts the value it read. A price inside the book is kept: a
    skip is still a skip.

    Returns the withdrawn rows as ``(id, market_id, last_updated)``.
    """
    if not books:
        return []
    from sqlalchemy import select, update
    from app.models.models import FuturesOutcome
    from app.utils.kalshi_empty_book import book_refutes_price
    from app.utils.price_change_stamp import price_changed_at_value

    table = FuturesOutcome.__table__
    rows = (
        await session.execute(
            select(table.c.id, table.c.current_probability).where(
                table.c.id.in_(sorted(books)),
                table.c.current_probability.isnot(None),
                table.c.is_winner.isnot(True),
                table.c.resolution_source.is_(None),
            )
        )
    ).all()
    withdrawn = []
    for outcome_id, stored in rows:
        bid, ask = books[outcome_id]
        if not book_refutes_price(bid, ask, float(stored)):
            continue
        result = await session.execute(
            update(table)
            .where(
                table.c.id == outcome_id,
                table.c.current_probability == stored,
                table.c.is_winner.isnot(True),
                table.c.resolution_source.is_(None),
            )
            .values(
                current_probability=None,
                current_american_odds=None,
                price_changed_at=price_changed_at_value(
                    table.c.current_probability, table.c.price_changed_at, None
                ),
            )
            .returning(table.c.id, table.c.market_id, table.c.last_updated)
        )
        withdrawn.extend(result.all())
    return withdrawn


class _PMPriceWriteResult:
    """A committed acknowledgement; only written rows may stage fresh receipts."""

    def __init__(self, written_ids):
        self.written_ids = tuple(written_ids)


PM_QUOTE_LIVENESS_SECONDS = 30.0


def chunk_price_update_stmt(chunk: dict, force_ids=None):
    """#10664: a flush chunk's price writes as ONE UPDATE ... RETURNING.

    ``write_chunk`` awaited one UPDATE per outcome — 500 round trips for a full
    chunk before its commit and publication. One statement now preserves:

    * the SAME set clause: the price bound as ``NUMERIC(7, 6)`` and compared as
      ``FLOAT`` through :func:`price_changed_at_value`, exactly as the per-row
      statement binds them, so rounding and the change-stamp cannot drift;
    * the SAME row-lock order: ``locked`` takes the row locks one at a time in
      chunk order (``ORDER BY ord ... FOR UPDATE``; LockRows runs above the
      Sort), as the per-row loop did, so the binary-pair and lock-cycle work
      that reasons about that order still holds;
    * returned-row attribution: a buffered id whose row is gone joins nothing
      and returns nothing; ``ord`` names only rows actually written. Unchanged
      database prices are acknowledged without locks/writes unless the caller
      forces a first observation or a bounded real liveness write.

    One parameter per column (arrays), so the prepared statement is shared by
    every chunk size.
    """
    from sqlalchemy import (
        ARRAY,
        Boolean,
        Float,
        Integer,
        Numeric,
        bindparam,
        cast,
        column,
        func,
        or_,
        select,
        update,
    )
    from app.models.models import FuturesOutcome
    from app.utils.price_change_stamp import price_changed_at_value, quote_moved_column

    table = FuturesOutcome.__table__
    prices = list(chunk.values())
    forced = set(chunk) if force_ids is None else force_ids
    given = (
        func.unnest(
            bindparam("chunk_ids", list(chunk), type_=ARRAY(Integer)),
            bindparam("chunk_prices", prices, type_=ARRAY(Numeric(7, 6))),
            bindparam("chunk_compare", prices, type_=ARRAY(Float)),
            bindparam("chunk_force", [oid in forced for oid in chunk], type_=ARRAY(Boolean)),
        )
        .table_valued(
            column("id", Integer),
            column("price", Numeric(7, 6)),
            column("compared", Float),
            column("force_write", Boolean),
            with_ordinality="ord",
        )
        .render_derived(name="given")
    )
    locked = (
        select(table.c.id, given.c.ord, given.c.price, given.c.compared)
        .join_from(given, table, table.c.id == given.c.id)
        # Compare against the DATABASE value at its stored precision. A local
        # repeated tick still repairs a price changed by another writer. Put
        # this before LockRows so an unchanged row does not acquire a lock.
        .where(or_(
            given.c.force_write,
            table.c.current_probability.is_distinct_from(
                cast(given.c.price, table.c.current_probability.type)
            ),
        ))
        .order_by(given.c.ord)
        .with_for_update(of=table)
        .cte("locked")
        .prefix_with("MATERIALIZED")
    )
    return (
        update(table)
        .where(table.c.id == locked.c.id)
        .values(
            current_probability=locked.c.price,
            last_updated=func.now(),
            price_changed_at=price_changed_at_value(
                table.c.current_probability, table.c.price_changed_at, locked.c.compared
            ),
        )
        .returning(
            locked.c.ord,
            table.c.id,
            table.c.market_id,
            table.c.last_updated,
            quote_moved_column(table),
        )
    )


def _pm_lock_isolated_chunks(
    chunks: list[list[int]],
    retry_events: set[int],
    event_by_outcome: dict[int, int],
    market_by_outcome: dict[int, int],
    complement_of: dict[int, int],
    chunk_rows: int,
) -> list[list[int]]:
    """Isolate admitted event cohorts only after their ordinary lock failure.

    The caller passes separately planned headline and prop transactions. Never
    admit another buffered row or change the open cap here. Within the admitted
    population a whole question and its complements stay indivisible; an
    oversized question keeps one transaction rather than exposing half of it.
    Unaffected rows retain their original chunks and order, ahead of the
    retried cohorts they share no event with.
    """
    if not retry_events:
        return chunks
    admitted = [oid for chunk in chunks for oid in chunk]
    parents = {oid: oid for oid in admitted}

    def root(oid):
        while parents[oid] != oid:
            parents[oid] = parents[parents[oid]]
            oid = parents[oid]
        return oid

    def join(left, right):
        parents[root(right)] = root(left)

    first_by_market = {}
    for oid in admitted:
        market = market_by_outcome.get(oid)
        if market is not None:
            if market in first_by_market:
                join(first_by_market[market], oid)
            else:
                first_by_market[market] = oid
        other = complement_of.get(oid)
        if other in parents:
            join(oid, other)
    units = {}
    for oid in admitted:
        units.setdefault(root(oid), []).append(oid)
    groups = {}
    group_by_outcome = {}
    for unit in units.values():
        events = frozenset(
            event_by_outcome[oid] for oid in unit if oid in event_by_outcome
        )
        if events.isdisjoint(retry_events):
            continue
        groups.setdefault(events, []).append(unit)
        group_by_outcome.update(dict.fromkeys(unit, events))
    packed = {}
    for events, event_units in groups.items():
        packed[events] = []
        current = []
        for unit in event_units:
            if current and len(current) + len(unit) > chunk_rows:
                packed[events].append(current)
                current = []
            current.extend(unit)
        if current:
            packed[events].append(current)
    # A retried cohort is the one most likely still held, and each attempt can
    # wait the full chunk lock budget. Its retained rows also lead the buffer,
    # so first-appearance placement put that wait ahead of the fresh unrelated
    # remainder. Run the remainder first; a cohort sharing an event with a
    # remainder chunk is released ahead of it, in order, so overlapping events
    # keep their write order.
    result = []
    emitted = set()
    held = []
    for chunk in chunks:
        remainder = [oid for oid in chunk if oid not in group_by_outcome]
        remainder_emitted = False
        for oid in chunk:
            events = group_by_outcome.get(oid)
            if events is None:
                if not remainder_emitted:
                    remainder_events = {
                        event_by_outcome[o] for o in remainder if o in event_by_outcome
                    }
                    last = max(
                        (i for i, cohort in enumerate(held)
                         if not cohort.isdisjoint(remainder_events)),
                        default=-1,
                    )
                    for cohort in held[: last + 1]:
                        result.extend(packed[cohort])
                    del held[: last + 1]
                    result.append(remainder)
                    remainder_emitted = True
            elif events not in emitted:
                # Each cohort keeps its first-appearance order among cohorts;
                # the unaffected remainder keeps its original transaction.
                held.append(events)
                emitted.add(events)
    for cohort in held:
        result.extend(packed[cohort])
    return result


def standalone_open_outcome_ids(
    outcome_ids,
    open_outcome_ids,
    event_id_by_outcome: dict,
    complement_of: dict,
) -> set[int]:
    """#10090: the buffered legs no blend reads — open, with no event, and a
    binary partner (if any) with none either.

    These leave the game flush for their own loop, so a standalone chunk's
    write never holds the next game quote. A bridged leg (#10091) feeds its
    event's blend and stays; a pair with one bridged side stays whole on the
    game side (CERT-3868: one transaction or wait together). Read at flush
    time: admission bridges a leg before it marks it open, with no await
    between, so a leg is never standalone ahead of its bridge.
    """
    def eventless_open(oid) -> bool:
        return oid in open_outcome_ids and event_id_by_outcome.get(oid) is None

    standalone: set[int] = set()
    for oid in outcome_ids:
        other = complement_of.get(oid)
        if eventless_open(oid) and (other is None or eventless_open(other)):
            standalone.add(oid)
    return standalone


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


#: #9418: what one ``market_resolved`` push may write, decided before any write.
#:
#: ``winner`` — the CLOB names exactly one winning token and it is a leg of this
#: market; ``void`` — the venue closed the market and paid every token 0.5, so
#: it named no outcome; ``unconfirmed`` — anything else (CLOB unreachable, not
#: yet flipped, disagreeing with the push, a token we cannot place). Only
#: ``winner`` grades; ``void`` records the void; ``unconfirmed`` grades nothing
#: and leaves the market to the Gamma rail, which reads the venue's prices.
WS_RESOLUTION_WINNER = "winner"
WS_RESOLUTION_VOID = "void"
WS_RESOLUTION_UNCONFIRMED = "unconfirmed"

#: Ceiling on the CLOB read behind one resolution. The read retries a 429 at
#: most twice with ≤10 s waits; past this the verdict is ``unconfirmed``.
RESOLUTION_CLOB_TIMEOUT_S = 25.0

#: Polymarket's payout on a void: every token settles at exactly half.
_VOID_PAYOUT = 0.5


def ws_resolution_verdict(
    push_winning_asset_id, clob_market, market_outcome_ids, asset_to_outcome
):
    """Decide what a ``market_resolved`` push may write (#9418). Pure.

    🔴 THE PUSH'S LABEL IS NEVER READ. ``winning_outcome`` is the venue's
    display word for the winning side — ``"Over"``, ``"Stefan Kozlov"``,
    ``"Yes"`` — and the old writer graded a leg only when that word was literally
    yes/no AND the leg's id ended ``_yes``/``_no``. Every other market (totals,
    named sides, and every ``{condition}``/``_side1`` leg) was written with
    BOTH legs ``is_winner=False`` under the tier-3 ``clob_authoritative`` stamp:
    2,471 of the 2,618 markets this socket settled on production 2026-09-30/10-01,
    10 of 12 sampled having a real venue winner (BOS@NYY "O/U 3.5", Over paid
    1/0, both legs stored lost). The winner is named by TOKEN instead, through
    ``asset_to_outcome`` — the same token→leg map every price tick is routed by
    (Q489/#8403), so a leg is graded by the contract it is, never by its
    position or its name.

    🔴 THE TOKEN IS CONFIRMED AGAINST THE CLOB BEFORE IT GRADES. The push's
    ``winning_asset_id`` is optional in the venue's schema and a void is not
    documented on it, so on its own it cannot tell a winner from a void. CLOB
    ``/markets/{condition}`` can: exactly one token ``winner: true`` is a result,
    and every token ``winner: false`` at price 0.5 on a closed market is a void
    (Kozlov v Kim, 15320860: both 0.5, Gamma's "Completed Match" No). Anything
    between — a CLOB that has not flipped yet, two winners, a winner that is not
    the pushed token — is ``unconfirmed``: a wrong tier-3 grade is never
    overwritten by the Gamma rail's void skip, so declining is the only safe
    answer.

    Returns ``(kind, winner_outcome_id)``; the id is set only for ``winner``.
    """
    unconfirmed = (WS_RESOLUTION_UNCONFIRMED, None)
    if not isinstance(clob_market, dict):
        return unconfirmed
    tokens = clob_market.get("tokens")
    if not isinstance(tokens, list) or len(tokens) < 2:
        return unconfirmed
    winners = [t for t in tokens if isinstance(t, dict) and t.get("winner") is True]
    if not winners:
        if clob_market.get("closed") is not True:
            return unconfirmed
        try:
            prices = [float(t.get("price")) for t in tokens]
        except (TypeError, ValueError, AttributeError):
            return unconfirmed
        if all(abs(p - _VOID_PAYOUT) < 1e-9 for p in prices):
            return (WS_RESOLUTION_VOID, None)
        return unconfirmed
    if len(winners) != 1:
        return unconfirmed
    token = str(winners[0].get("token_id") or "")
    if not token:
        return unconfirmed
    if push_winning_asset_id and str(push_winning_asset_id) != token:
        return unconfirmed
    owner = asset_to_outcome.get(token)
    if owner is None or owner not in set(market_outcome_ids):
        return unconfirmed
    return (WS_RESOLUTION_WINNER, owner)


#: Re-asks after a push the venue had not yet confirmed (#9418 after-check),
#: seconds after the previous ask. Measured 2026-10-01 05:3x–06:0xZ on 16 of 16
#: pushes: Gamma closes the market at T, records `umaResolutionStatus:
#: "resolved"` with 0/1 `outcomePrices` by ~T+10 s, the socket push lands at
#: ~T+60 s — and CLOB `/markets` still reads `closed: false`, no winner, more
#: than five minutes later. The first ask therefore almost always answers from
#: Gamma; these cover a Gamma read that is itself a few seconds behind. Total
#: 220 s, inside the 600 s recycle; a recycle that cancels the wait leaves the
#: market where it is today (resolved, ungraded, the Gamma rail's).
RESOLUTION_RECHECK_DELAYS_S = (10.0, 30.0, 60.0, 120.0)


def _price_list(raw) -> Optional[list]:
    """Gamma serves list fields as JSON strings (``'["0", "1"]'``) or lists."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, list) else None


def gamma_resolution_verdict(
    push_winning_asset_id, gamma_market, market_outcome_ids, asset_to_outcome
):
    """The same decision as :func:`ws_resolution_verdict`, read from Gamma. Pure.

    CLOB `/markets` flips ``winner`` minutes after the venue settles; Gamma's
    record of the same settlement is readable before the push even arrives
    (measured, see :data:`RESOLUTION_RECHECK_DELAYS_S`). It is the record the
    Gamma rail already grades from, so this is not a new authority, only an
    earlier read of it — under the same rules:

    - only a market Gamma calls ``closed`` with ``umaResolutionStatus ==
      "resolved"`` is read at all (a price at 0.999 is a market, not a result);
    - the winner is a TOKEN: ``clobTokenIds`` is index-aligned with
      ``outcomePrices``, exactly one price must be 1 and every other 0, and the
      token at that index must be the push's ``winning_asset_id`` when the push
      names one and must belong to a leg of THIS market via ``asset_to_outcome``
      — never a label, never a position in our rows;
    - every price at exactly 0.5 is a void;
    - anything else is ``unconfirmed``.
    """
    unconfirmed = (WS_RESOLUTION_UNCONFIRMED, None)
    if not isinstance(gamma_market, dict):
        return unconfirmed
    if gamma_market.get("closed") is not True:
        return unconfirmed
    if gamma_market.get("umaResolutionStatus") != "resolved":
        return unconfirmed
    tokens = _price_list(gamma_market.get("clobTokenIds"))
    raw_prices = _price_list(gamma_market.get("outcomePrices"))
    if not tokens or not raw_prices or len(tokens) != len(raw_prices) or len(tokens) < 2:
        return unconfirmed
    try:
        prices = [float(p) for p in raw_prices]
    except (TypeError, ValueError):
        return unconfirmed
    if all(abs(p - _VOID_PAYOUT) < 1e-9 for p in prices):
        return (WS_RESOLUTION_VOID, None)
    winners = [i for i, p in enumerate(prices) if abs(p - 1.0) < 1e-9]
    if len(winners) != 1:
        return unconfirmed
    if any(abs(p) >= 1e-9 for i, p in enumerate(prices) if i != winners[0]):
        return unconfirmed
    token = str(tokens[winners[0]] or "")
    if not token:
        return unconfirmed
    if push_winning_asset_id and str(push_winning_asset_id) != token:
        return unconfirmed
    owner = asset_to_outcome.get(token)
    if owner is None or owner not in set(market_outcome_ids):
        return unconfirmed
    return (WS_RESOLUTION_WINNER, owner)


async def settle_with_rechecks(ask, write, *, delays=None, sleep=None):
    """Write the first answer, then re-ask until the venue decides (#9418).

    ``ask()`` returns a verdict; ``write(verdict)`` applies it. The FIRST answer
    is always written — a settled market reads settled at once — and only an
    ``unconfirmed`` one is re-asked, on ``delays``; the first decided verdict
    is written over it and the loop stops. A write that fails on a re-ask
    propagates, like the first. Returns ``(final verdict, decided_late)``.
    """
    delays = RESOLUTION_RECHECK_DELAYS_S if delays is None else delays
    sleep = asyncio.sleep if sleep is None else sleep
    verdict = await ask()
    await write(verdict)
    if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
        return verdict, False
    for delay in delays:
        await sleep(delay)
        verdict = await ask()
        if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            await write(verdict)
            return verdict, True
    return verdict, False


async def _apply_ws_resolution(session, market_id, outcomes, verdict):
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

    #9418: ``verdict`` is :func:`ws_resolution_verdict`'s ``(kind, winner_id)``.
    Only ``winner`` writes a grade. ``void`` writes the venue's void the way the
    Kalshi sweep does (``venue_voided`` merged into ``market_metadata``, no grade
    — a void names NO outcome, #1852), which is what lets #5811's
    ``venue_closed_no_winner`` speak for a match both venues cancelled.
    ``unconfirmed`` marks the market resolved and grades nothing; the legs stay
    eligible for the Gamma rail exactly as an ungraded resolved market is.

    Module-level (not a closure) so the leakage contract is unit-testable.
    Returns the number of outcome winner-writes applied.
    """
    from sqlalchemy import select, text, update

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.tasks.kalshi_resolution_sweep import VOID_UPDATE_SQL
    from app.utils.resolution_authority import is_authoritative

    # A CLOB `market_resolved` push is the venue's own settlement delivered over
    # the socket — the same authority as the CLOB REST resolver
    # (`clob_resolve.py`). Stamp its registered tier-3 source so the winner write
    # carries audit-grade provenance, survives the authority ladder (a later
    # guess-family pass can no longer silently overwrite a NULL-source winner),
    # and is calibration-truth eligible. Do NOT invent a new source string.
    _WS_RESOLUTION_SOURCE = "clob_authoritative"

    kind, winner_id = verdict

    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id == market_id)
        .values(status="resolved", **settled_values(FuturesMarket.settled_at))
    )

    if kind == WS_RESOLUTION_VOID:
        # The Kalshi sweep's own statement, unforked: merged, never assigned, so
        # `shape` survives, and the two venues' voids are one fact to every
        # reader (`venue_closed_without_winner`, #7035's retirement).
        await session.execute(
            text(VOID_UPDATE_SQL),
            {"id": market_id, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        return 0

    if kind != WS_RESOLUTION_WINNER or winner_id is None:
        return 0

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

    written = 0
    for oid, _ext in outcomes:
        if is_authoritative(existing_sources.get(oid)):
            continue  # venue already settled authoritatively — leave it
        # Winner AND provenance in the SAME statement (Queue #284 Item 1): an
        # atomic write means a failed/partial apply can never leave is_winner set
        # with a NULL resolution_source. Deliberately NOT setting
        # calibration_probability here (Queue #261) — no price self-grading.
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.id == oid)
            .values(
                is_winner=(oid == winner_id),
                resolution_source=_WS_RESOLUTION_SOURCE,
            )
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
    from app.tasks.ws_slate import suspended_open_market_arm

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
        # #9484: an open market on a recently suspended event. Floored like the
        # scheduled arm, because nothing advances a suspended row out; this arm
        # also reads `futures_markets`, which every caller already joins.
        suspended_open_market_arm(),
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
        "| blend stamped=%d no_reading=%d throttled=%d errors=%d lock_skipped=%d "
        "unobserved=%d stale=%d | trades refused below_min=%d outside_wide_book=%d "
        "| held withdrawn=%d",
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
        # #5661: unchanged prices not re-dated because no writer re-read them.
        blend.get("unobserved_skipped", 0),
        # #8910: readings refused as older than the stored observation.
        blend.get("stale_readings_refused", 0),
        # #9733 / #9913: trades that were not a price. Counted in the consumer
        # and, until this line, never emitted.
        stats.get("trades_below_min_order", 0),
        stats.get("trades_outside_wide_book", 0),
        # #9934: held prices a wide book priced out, withdrawn.
        stats.get("held_prices_withdrawn", 0),
    )


def _log_open_contract_line(stats: dict, open_stats: dict) -> None:
    """#9484 — the open-contract client's minute line, beside the game line.

    Its own line so the game line's format (and every grep of it) is untouched.
    `written` is rows that took a price; `deferred` is open rows a periodic
    flush left buffered for the next one — non-zero is a backlog, not a loss.
    `bridged` is #10091's legs/events whose flushed price re-stamps the event
    blend (0/0 with no `bridge_error` = no such contract this run).
    """
    logger.info(
        "Polymarket WS open contracts: assets=%d shards=%d/%d served=%d/%d "
        "msgs=%d snapshot_quotes=%d written=%d deferred=%d "
        "bridged=%d/%d%s",
        stats.get("open_contract_assets", 0),
        open_stats.get("shards_connected", 0), open_stats.get("shards", 0),
        open_stats.get("assets_served", 0),
        open_stats.get("assets_subscribed", 0),
        open_stats.get("messages", 0),
        open_stats.get("book_snapshot_quotes", 0),
        stats.get("open_contract_prices_written", 0),
        stats.get("open_contract_flush_deferred", 0),
        stats.get("open_contract_bridged_outcomes", 0),
        stats.get("open_contract_bridged_events", 0),
        " bridge_error" if stats.get("open_contract_bridge_error") else "",
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


@owns_consumer_sessions("polymarket")
async def _run_polymarket_ws_consumer(*, sessions, stop=None):
    """Stream until cancellation; an explicit stop also runs the final drain."""
    # `text`/`or_`/`and_` left with `_slate_event_window`, which now owns the
    # only expression in this consumer that needed them.
    from sqlalchemy import select, update, func

    from app.models.models import (
        Event, FuturesMarket, FuturesOutcome,
    )
    from app.services.polymarket_ws import PolymarketWebSocket
    from app.tasks.live_blend_refresh import (
        DEFAULT_MIN_REFRESH_INTERVAL_S, LiveBlendRefresher, TailReceipts,
        adopt_handed_off,
        LOOP_REAP_TIMEOUT_S, event_ids_for_outcomes, hand_off_pending,
        reap_stopped_loops, run_flush_cadence,
    )
    from app.tasks.polymarket_token_topup import (
        topup_clob_tokens, topup_outcome_clob_tokens,
    )
    from app.tasks.ws_admission import (  # #9418
        unadmitted_live_events,
        watch_for_unadmitted_live_events,
    )
    from app.tasks.polymarket_open_contracts import (  # #9484
        FLUSH_CHUNK_ROWS, OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES,
        book_snapshot_prices_enabled,
        OPEN_CONTRACT_MAX_QUEUE, OPEN_FLUSH_CHUNKS_PER_FLUSH,
        open_contract_asset_map, open_contract_event_candidates,
        open_contract_markets_stmt, open_contract_outcome_stmts,
        open_contract_prices_enabled, plan_flush_chunks, tokens_by_contract,
    )
    from app.tasks.ws_open_contracts import (  # #10091: the Kalshi arm's twin
        open_contract_bridge_event_stmt, open_contract_event_bridge,
    )
    from app.tasks.ws_liveness import report as _report_liveness
    from app.utils.futures_rank import rerank_market_fields_stmt  # #6598
    from app.utils.price_change_stamp import price_changed_at_value
    from app.utils.price_change_stamp import quote_moved_column  # #9484
    # #2471: one engine for this run, a fresh session per operation; the
    # decorator disposes it after the final drain. Same call shape as the
    # task factory, so every site below is unchanged.
    get_task_session = sessions.session

    # #10662: opt in only this consumer. Removing the override restores both
    # the legacy shared timer and the existing blend floor. A faster healthy
    # timer must not also shorten the preexisting failed-write retry period.
    flush_period = PRICE_FLUSH_SECONDS
    blend_floor = DEFAULT_MIN_REFRESH_INTERVAL_S
    override = os.getenv("PM_WS_PRICE_FLUSH_SECONDS")
    if override is not None:
        try:
            flush_period = float(override)
        except ValueError as invalid_cadence:
            raise ValueError(
                "PM_WS_PRICE_FLUSH_SECONDS must be a positive finite number"
            ) from invalid_cadence
        if not math.isfinite(flush_period) or flush_period <= 0:
            raise ValueError(
                "PM_WS_PRICE_FLUSH_SECONDS must be a positive finite number"
            )
        blend_floor = flush_period

    # #9484 — every other unsettled Polymarket contract, for PRICES only, on a
    # second client (`app.tasks.polymarket_open_contracts`). Never added to the
    # settlement maps or to the maps the #9418 admission watcher reads as "this
    # event is subscribed". A failed read costs the arm, never the game slate.
    #
    # Returns ``(admission, failed, bridge, bridge_failed)``. The #10091 EVENT
    # BRIDGE is outcome → event for the admitted game-winner legs whose event is
    # still to be decided (`open_contract_event_candidates`), so the flush
    # re-stamps their event blend like a slate leg's. Its own read fails on its
    # own: a failed bridge costs the blend re-stamp, never the prices.
    async def read_open_contracts(
        taken_assets, excluded_market_ids, taken_tokens_by_contract=None
    ):
        if not open_contract_prices_enabled():
            return None, False, {}, False
        try:
            async with get_task_session() as session:
                market_rows = (
                    await session.execute(open_contract_markets_stmt())
                ).all()
                outcome_rows = []
                for stmt in open_contract_outcome_stmts(r[0] for r in market_rows):
                    outcome_rows.extend((await session.execute(stmt)).all())
            admission = open_contract_asset_map(
                market_rows, outcome_rows, taken_assets, excluded_market_ids,
                taken_tokens_by_contract,
            )
        except Exception:
            logger.exception(
                "Polymarket WS: open-contract admission read failed; "
                "streaming the linked slate only this run"
            )
            return None, True, {}, False
        candidates = open_contract_event_candidates(market_rows, admission)
        if not candidates:
            return admission, False, {}, False
        try:
            async with get_task_session() as session:
                admitted = (
                    await session.execute(
                        open_contract_bridge_event_stmt(candidates.values())
                    )
                ).scalars().all()
        except Exception:
            logger.exception(
                "Polymarket WS: open-contract event-bridge read failed; "
                "streaming their prices without the event blend this run"
            )
            return admission, False, {}, True
        return (
            admission, False, open_contract_event_bridge(candidates, admitted),
            False,
        )

    # Q504-b: see the Kalshi arm — reported before the slate work, so a stall in
    # the token top-up or the slate query is visible as an AGE rather than as a
    # silence indistinguishable from health.
    _report_liveness("polymarket", "loading_slate")

    # #9418: the admission floor is measured from here, the previous recycle.
    run_started_at = time.monotonic()
    ws = PolymarketWebSocket()

    async def load_game_slate():
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
        non_blend_market_ids: set[int] = set()

        async with get_task_session() as session:
            market_result = await session.execute(
                select(FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.market_metadata)
                .where(FuturesMarket.id.in_(list(market_ids)))
            )
            ext_by_market: dict[int, str] = {}
            for mid, mext, metadata in market_result.all():
                # Same authoritative refutation as shared WIN admission, using the
                # catalog metadata this token read already owns. Missing labels
                # remain conservative; titles and outcome names are never guessed.
                if pm_non_speaking_metadata(metadata):
                    non_blend_market_ids.add(mid)
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

        return {
            "asset_ids": asset_ids,
            "asset_to_outcome": asset_to_outcome,
            "asset_to_market": asset_to_market,
            "condition_to_market": condition_to_market,
            "market_ids": market_ids,
            "event_id_by_market": event_id_by_market,
            "outcomes_by_market": outcomes_by_market,
            "market_by_outcome": market_by_outcome,
            "non_blend_market_ids": non_blend_market_ids,
            "outcome_yes_token": outcome_yes_token,
            "unmapped_assets": unmapped_assets,
        }

    game_slate = await load_game_slate()
    asset_ids = game_slate["asset_ids"].copy()
    asset_to_outcome = game_slate["asset_to_outcome"].copy()
    asset_to_market = game_slate["asset_to_market"].copy()
    condition_to_market = game_slate["condition_to_market"].copy()
    market_ids = game_slate["market_ids"].copy()
    event_id_by_market = game_slate["event_id_by_market"].copy()
    outcomes_by_market = game_slate["outcomes_by_market"].copy()
    market_by_outcome = game_slate["market_by_outcome"].copy()
    non_blend_market_ids = game_slate["non_blend_market_ids"].copy()
    outcome_yes_token = game_slate["outcome_yes_token"].copy()
    unmapped_assets = game_slate["unmapped_assets"].copy()

    preread = None
    if not asset_ids:
        preread = await read_open_contracts(set(), market_ids)
        if preread[0] is None or not preread[0].asset_to_outcome:
            logger.info("Polymarket WS: no game or open-contract asset IDs")
            _report_liveness("polymarket", "no_asset_ids", legs=0)
            return {"status": "no_asset_ids" if market_ids else "no_markets"}

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
        # #9733: trades refused because they were smaller than the smallest
        # order the venue accepts (`trade_sets_a_price`).
        "trades_below_min_order": 0,
        # #9913: trades refused because they printed beyond the edge of a
        # book too wide to price (`trade_prints_outside_wide_book`).
        "trades_outside_wide_book": 0,
        # #9934: held prices withdrawn because a wide book priced them out
        # (`withdraw_book_refuted_prices`).
        "held_prices_withdrawn": 0,
        "resolutions": 0,
        # #9418: what each resolution was allowed to write
        # (`ws_resolution_verdict`). `unconfirmed` is graded by nobody here.
        "resolutions_winner": 0,
        "resolutions_void": 0,
        "resolutions_unconfirmed": 0,
        # #9418 after-check: decided by Gamma (CLOB not yet flipped), and
        # decided only on a re-ask after the first answer was `unconfirmed`.
        "resolutions_via_gamma": 0,
        "resolutions_confirmed_late": 0,
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
        # #9484: the open-contract arm. `open_contract_prices_written` counts
        # rows that TOOK a price, so "the arm is subscribed" and "the arm is
        # moving stored prices" are two numbers, not one; `_flush_deferred`
        # counts open rows a flush left buffered for the next one.
        "open_contract_assets": 0,
        "open_contract_admission_error": False,
        "open_contract_prices_written": 0,
        "open_contract_flush_deferred": 0,
        # #10091 event bridge, twin of the Kalshi socket's: admitted game-winner
        # legs (and their distinct events) whose flushed price re-stamps the
        # event blend. 0 with no error is "no such contract this run".
        "open_contract_bridged_outcomes": 0,
        "open_contract_bridged_events": 0,
        "open_contract_bridge_error": False,
        # #9484, twin of the Kalshi socket's: rows a flush wrote whose price
        # was already what it stored — written (liveness), but no market
        # invalidation sent. #10664: counts observations returned by completed
        # price statements. A failed atomic statement adds none; a later
        # rerank/commit failure may still leave these observations counted.
        "quotes_unchanged": 0,
    }

    # Buffered price updates
    price_buffer: dict[int, float] = {}
    buffer_lock = asyncio.Lock()
    catalog_boundary = _PMCatalogFlushBoundary()
    lock_retry_until: dict[int, float] = {}
    lock_retry_events: set[int] = set()
    successful_price_write_at: dict[int, float] = {}
    withdrawal_retry_until: dict[int, float] = {}
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
    non_blend_outcome_ids = {
        oid for oid, mid in market_by_outcome.items()
        if mid in non_blend_market_ids
    }
    blend_refresher = LiveBlendRefresher(
        "polymarket", min_refresh_interval_s=blend_floor,
        session_factory=get_task_session,  # #2471
    )
    # #837 receipt — every accepted input is stamped (seq, receive instant) as
    # it is buffered, so a held price can be followed from the socket to the
    # stamp that carried it. `input_marks` is keyed like `price_buffer` (one
    # entry per subscribed outcome) and holds the mark of the buffered value.
    tail_receipts = TailReceipts("polymarket")
    blend_refresher.receipts = tail_receipts
    # #9462 review: stamps the previous run still owed when it recycled. Its
    # prices are already stored; the first flush below stamps them.
    stats["blend_pending_adopted"] = adopt_handed_off(blend_refresher)
    input_marks: dict = {}

    # #9484: filled IN PLACE by `admit_open_contracts`, which the handlers and
    # the flush read through these same objects. Separate from the game maps so
    # nothing the #9418 watcher or the settlement handler reads can see them.
    open_asset_to_outcome: dict[str, int] = {}
    open_asset_to_market: dict[str, int] = {}
    # #9736: token → [(outcome_id, market_id)] of the other markets' legs that
    # name a token another leg owns. Each tick lands on the owner AND these.
    open_asset_mirrors: dict[str, list[tuple[int, int]]] = {}
    # #9733 follow-on: leg → the other leg of its binary (`complement_pairs`).
    open_complement_of: dict[int, int] = {}
    open_outcome_ids: set[int] = set()
    open_sockets: list = []
    open_run_task = None
    routing_generation = 0
    # #9913: token → (latest, previous) distinct top of book, wide or not, so
    # a trade can be read against the book it hit. One entry per subscribed
    # token; rebuilt from the subscribe snapshot on every recycle.
    books_by_asset: dict[str, tuple] = {}
    # #9934: leg → (bid, ask) of the latest wide book that speaks for it. The
    # flush asks whether the held price survives it; a tight book for the leg
    # clears the entry, since its midpoint is about to replace the price.
    withdraw_buffer: dict[int, tuple] = {}

    async def write_chunk(chunk: dict[int, float], *, final=False) -> _PMPriceWriteResult | bool | None:
        """One flush transaction: write, re-rank, commit, publish, un-buffer.

        #9484: the flush used to write its whole batch in ONE transaction, so a
        standalone flood would have held every linked quote behind it and one
        failure would have retried all of it. Each chunk now commits and
        publishes on its own; a failed chunk keeps only its own rows buffered.
        """
        # Q491 repair 2 (CERT-659 BLOCK) — THE BUFFER IS DELIBERATELY *NOT*
        # CLEARED HERE. Twin of the Kalshi socket: draining first and putting
        # the batch back on failure only covers the failures you thought to
        # catch, and `except Exception` never sees `CancelledError` (a
        # BaseException), so a recycle cancelling `flush_loop` between the drain
        # and the write lost the batch with `errors=0, requeued=0` — invisible.
        # Entries now leave only after the write lands, so nothing needs to be
        # "put back", because it was never taken away.
        from app.tasks.live_blend_refresh import _mono
        from app.tasks.polymarket_ws import _PMPriceWriteResult, PM_QUOTE_LIVENESS_SECONDS

        # None means a lock-held whole chunk, not a global cadence failure.
        # Newer ticks on its rows cannot bypass the existing two-second hold.
        if not final and any(lock_retry_until.get(oid, 0) > _mono() for oid in chunk):
            return None
        try:
            async with get_task_session() as session:
                if not final:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(PRICE_CHUNK_LOCK_TIMEOUT_MS)},
                    )
                # #10664: the chunk's price writes in ONE statement — the same
                # set clause, row-lock order and returned-row coverage as the
                # per-row UPDATEs it replaces (`chunk_price_update_stmt`).
                now = _mono()
                forced = {
                    oid for oid in chunk
                    if final or oid not in successful_price_write_at
                    or now - successful_price_write_at[oid] >= PM_QUOTE_LIVENESS_SECONDS
                }
                result = await session.execute(chunk_price_update_stmt(chunk, force_ids=forced))
                written_rows = sorted(result.all(), key=lambda r: r.ord)
                # #9484: only a row the UPDATE returned is evidence — a
                # buffered id whose row is gone signals nothing. And only
                # a row whose stored price moved: the same price again
                # still re-stamps `last_updated` (liveness), but a frame
                # for it sends every held page to re-read an unchanged row
                # (twin of the Kalshi socket's, ux #9526). Walked in chunk
                # order, so invalidations stage exactly as they did per row.
                for row in written_rows:
                    if not row.quote_moved:
                        stats["quotes_unchanged"] += 1
                        continue
                    queue_market_change(
                        session,
                        market_id=row.market_id,
                        source="polymarket",
                        outcome_observed_at={row.id: row.last_updated},
                    )

                # #6598 / CERT-3182, twin of the Kalshi socket's. Every price
                # above moved the value `rank` is derived from and this module
                # has never written that column, so a crossing mid-game left the
                # board numbered by whichever poll last saw it. One statement
                # for every market the chunk touched, in the same session as the
                # prices. `market_by_outcome` is the slate map already in memory
                # (plus the open contracts' legs) — no per-flush lookup on a
                # two-second cadence.
                reranked_markets = {
                    row.market_id for row in written_rows
                }
                if reranked_markets:
                    stats["ranks_rederived"] += (
                        await session.execute(
                            rerank_market_fields_stmt(sorted(reranked_markets))
                        )
                    ).rowcount
            stats["price_updates"] += len(written_rows)
            stats["open_contract_prices_written"] += sum(
                1 for row in written_rows if row.id in open_outcome_ids
            )
        except Exception as exc:
            # Q491 — THE SHIP. The chunk is still in `price_buffer`, so the next
            # flush retries it. Before Q491 the buffer was drained up front and
            # a failed write DISCARDED those prices outright: the socket only
            # refills an outcome when that market ticks again, and 86.7% of open
            # Polymarket markets never tick at all, so one transient error froze
            # a card at its old number indefinitely with no `last_updated`
            # either (#2024).
            #
            # Bounded by construction: the buffer is keyed by outcome_id over a
            # fixed subscription, so a long outage holds at most one entry per
            # subscribed outcome however many attempts are burned.
            stats["errors"] += 1
            stats["requeued"] += len(chunk)
            logger.exception(
                "Polymarket WS: flush error (%d retained for retry)", len(chunk)
            )
            if not final and is_lock_timeout(exc):
                until = _mono() + PRICE_FLUSH_SECONDS
                lock_retry_until.update(dict.fromkeys(chunk, until))
                lock_retry_events.update(
                    event_ids_for_outcomes(event_id_by_outcome, chunk)
                )
                return None
            return False

        for oid in chunk:
            lock_retry_until.pop(oid, None)
        successful_price_write_at.update(dict.fromkeys(
            (row.id for row in written_rows), _mono(),
        ))
        # #9484 — twin of the Kalshi socket's: the commit landed, so publish
        # before the buffer bookkeeping and the blend refresh can suppress it.
        await blend_refresher.publish_market_changes(session)

        # Q491 repair 2 — the write landed, so and only so do these entries
        # leave the buffer. The `== prob` test is what used to be `setdefault`:
        # `handle_price` may have buffered a FRESHER price for the same outcome
        # while this write was in flight, and that newer value is the truth, so
        # it must survive to the next flush rather than be dropped as "already
        # written". Same contract, enforced at removal instead of at re-queue.
        async with buffer_lock:
            for outcome_id, prob in chunk.items():
                if price_buffer.get(outcome_id) == prob:
                    del price_buffer[outcome_id]
        # A zero-return statement still acknowledged the unchanged inputs.
        # Clear only matching buffered values, but never stamp those inputs as
        # a new database observation or rerank their unchanged markets.
        return _PMPriceWriteResult(row.id for row in written_rows)

    async def flush_withdrawals(
        *,
        only_events: Optional[set[int]] = None,
        exclude_events: frozenset[int] | set[int] = frozenset(),
        standalone: Optional[bool] = None,
        final: bool = False,
    ) -> Optional[list[int]]:
        """#9934: withdraw the held prices the latest wide books priced out.

        Same bookkeeping as ``write_chunk``: an entry leaves the buffer only
        after its transaction lands, and only if no newer book replaced it
        meanwhile. Returns withdrawn ids, or None on non-lock failure. A held
        withdrawal returns no ids and keeps its book/cohort owed for retry.
        #10651: a finished game's work can run before unrelated price chunks.
        The tail excludes attempted events, so even a failure is tried once.
        #10090: ``standalone`` True/False takes only/no standalone legs, so
        each loop withdraws after its own prices; None (final drain) takes all.
        """
        from app.tasks.live_blend_refresh import _mono

        async with buffer_lock:
            held_events = (
                {
                    event_id_by_outcome.get(oid)
                    for oid, until in withdrawal_retry_until.items()
                    if oid in withdraw_buffer and until > _mono()
                }
                if not final else set()
            )
            alone = (
                standalone_open_outcome_ids(
                    withdraw_buffer, open_outcome_ids, event_id_by_outcome,
                    open_complement_of,
                )
                if standalone is not None
                else set()
            )
            books = {
                oid: book
                for oid, book in withdraw_buffer.items()
                if (standalone is None or (oid in alone) == standalone)
                and (only_events is None or event_id_by_outcome.get(oid) in only_events)
                and event_id_by_outcome.get(oid) not in exclude_events
                and event_id_by_outcome.get(oid) not in held_events
            }
        if not books:
            return []
        try:
            async with get_task_session() as session:
                if not final:
                    await session.execute(
                        SET_LOCK_TIMEOUT_SQL,
                        {"ms": lock_timeout_value(PRICE_CHUNK_LOCK_TIMEOUT_MS)},
                    )
                rows = await withdraw_book_refuted_prices(session, books)
                for row in rows:
                    if row.last_updated is None:
                        continue  # no observation stamp to push; REST serves it
                    queue_market_change(
                        session,
                        market_id=row.market_id,
                        source="polymarket",
                        outcome_observed_at={row.id: row.last_updated},
                    )
                # #6598: a withdrawn leg leaves the field `rank` orders.
                markets = sorted({row.market_id for row in rows})
                if markets:
                    stats["ranks_rederived"] += (
                        await session.execute(rerank_market_fields_stmt(markets))
                    ).rowcount
        except Exception as exc:
            stats["errors"] += 1
            logger.exception(
                "Polymarket WS: withdrawal error (%d retained for retry)", len(books)
            )
            if not final and is_lock_timeout(exc):
                # Keep the complete failed transaction; newer books on another
                # leg of its event must not bypass this eligibility cooldown.
                until = _mono() + PRICE_FLUSH_SECONDS
                withdrawal_retry_until.update(dict.fromkeys(books, until))
                return []
            return None
        for oid in books:
            withdrawal_retry_until.pop(oid, None)
        await blend_refresher.publish_market_changes(session)
        async with buffer_lock:
            for oid, book in books.items():
                if withdraw_buffer.get(oid) == book:
                    del withdraw_buffer[oid]
        stats["held_prices_withdrawn"] += len(rows)
        return [row.id for row in rows]

    async def _flush_prices(flush_started=None, final=False):
        """One flush. Non-lock failures return False for the cadence retry;
        lock-held whole chunks retain their own eligibility cooldown. #10090
        ``flush_started`` is this flush's start, for the refresher's floor."""
        import asyncio  # the pipelined stamp below; executed rigs bring no globals
        from app.tasks.polymarket_ws import _PMHeadlineEvents, _pm_lock_isolated_chunks

        headline_event_ids = _PMHeadlineEvents(
            event_id_by_outcome, () if final else non_blend_outcome_ids,
        )

        async with buffer_lock:
            batch = dict(price_buffer)
            if not final:
                # #10090: standalone legs are `flush_standalone`'s; the final
                # drain has no such loop after it, so it takes them too.
                for oid in standalone_open_outcome_ids(
                    batch, open_outcome_ids, event_id_by_outcome,
                    open_complement_of,
                ):
                    del batch[oid]
            batch_marks = {oid: input_marks[oid] for oid in batch if oid in input_marks}
            # #10090 / #837: events a held-price withdrawal may still touch
            # this flush. Their refresh waits for that transaction too.
            withdraw_cohort_ids = set(withdraw_buffer)
            withdraw_events = event_ids_for_outcomes(
                event_id_by_outcome, withdraw_cohort_ids,
            )
        unfinished_price_ids: set[int] = set()
        # Committed this flush, refresh not yet called.
        owed: list[int] = []
        wrote_all = True
        attempted_withdraw_events: set[int] = set()
        failed_price_events: set[int] = set()
        lock_deferred_events: set[int] = set()
        if batch:
            # #9484: every linked row, then a bounded number of open-contract
            # chunks, oldest-dirty first (the buffer's insertion order). Open
            # rows past the bound stay buffered and lead the next flush — none
            # dropped. The FINAL drain has no successor flush, so it takes
            # every row. CERT-3868: the two legs of a binary commit in one
            # transaction or wait together — never one side read beside the
            # other's old price.
            chunks = plan_flush_chunks(
                (oid for oid in batch if oid not in headline_event_ids.non_speakers),
                open_outcome_ids,
                FLUSH_CHUNK_ROWS,
                None if final else OPEN_FLUSH_CHUNKS_PER_FLUSH,
                open_complement_of,
            )
            # Split the known unrelated slate questions into their own normal
            # tail transactions. All linked prices still write; complement
            # pairs stay atomic and the existing open-contract cap is intact.
            if not final:
                # A typed rollback may have coupled unrelated events in one
                # ordinary chunk. Retry only its admitted event/question units;
                # fresh siblings then retain their own cooldown eligibility.
                chunks = _pm_lock_isolated_chunks(
                    chunks, lock_retry_events, event_id_by_outcome,
                    market_by_outcome, open_complement_of, FLUSH_CHUNK_ROWS,
                )
                prop_chunks = plan_flush_chunks(
                    (oid for oid in batch if oid in non_blend_outcome_ids),
                    set(), FLUSH_CHUNK_ROWS, None, open_complement_of,
                )
                chunks.extend(_pm_lock_isolated_chunks(
                    prop_chunks, lock_retry_events, event_id_by_outcome,
                    market_by_outcome, open_complement_of, FLUSH_CHUNK_ROWS,
                ))
            stats["open_contract_flush_deferred"] += len(batch) - sum(
                len(c) for c in chunks
            )
            # Preserve the existing planned-chunk boundary. Capped-out tail
            # and newer inputs still belong to later flushes; this exclusion
            # covers unfinished/failed writes admitted to THIS flush only.
            unfinished_price_ids = {oid for chunk in chunks for oid in chunk}
            # #10090 / #837: an event is refreshed once per flush, right after
            # the last transaction of this flush that can touch it. The refresh
            # used to wait for EVERY chunk, so a committed binary pair sat
            # unstamped behind an unrelated chunk's UPDATE (controlled replay
            # on 6443a89023: the pair committed and published, its event
            # waited until the later chunk's blocked row lock was released).
            # Refreshing after the FIRST chunk that touches an event instead
            # would stamp it half-written and leave the rest to the 2s
            # throttle, so an event a later chunk still writes waits for that
            # chunk, and one with a pending withdrawal waits for it.
            last_chunk_of_event: dict[int, int] = {}
            # Withdrawals judge the final stored price, including non-speakers.
            # Their maturity must therefore wait for every planned event price,
            # even when WIN readiness no longer waits for that prop's quote.
            last_price_chunk_of_event: dict[int, int] = {}
            for index, chunk_ids in enumerate(chunks):
                for oid in chunk_ids:
                    price_event_id = event_id_by_outcome.get(oid)
                    if price_event_id is not None:
                        last_price_chunk_of_event[price_event_id] = index
                    event_id = headline_event_ids.get(oid)
                    if event_id is not None:
                        last_chunk_of_event[event_id] = index
            # #10090 — PIPELINED STAMPS, twin of the Kalshi socket's. A chunk's
            # refresh used to finish before the next chunk's write could open,
            # so an event in a later chunk waited for every earlier chunk's
            # write AND stamp in turn. A safe independent chunk N+1's write
            # overlaps chunk N's stamp. Unchanged: writes stay strictly sequential, one in flight;
            # the refresher still runs ONE refresh at a time, in chunk order
            # (each joins the previous one before its receipts are staged); a
            # chunk's stamp starts only after its own write committed and
            # published; withdrawals still follow the stamp before them; and
            # no stamp outlives its flush, so the final drain never refreshes
            # beside it.
            stamping = None
            stamping_events = None

            async def stamp_done(*, cancel=False):
                nonlocal stamping, stamping_events
                if stamping is None:
                    return
                if cancel:
                    stamping.cancel()
                # Joined even when this flush is cancelled while it waits: the
                # stamp is cancelled too and still awaited, so it never outlives
                # the flush and the final drain never refreshes beside it.
                interrupted = None
                while not stamping.done():
                    try:
                        await asyncio.wait({stamping})
                    except asyncio.CancelledError as exc:
                        interrupted = exc
                        stamping.cancel()
                task, stamping = stamping, None
                stamping_events = None
                if not task.cancelled() and task.exception() is not None:
                    # `refresh` never raises; if it ever does, its write already
                    # committed, so say so rather than fail the flush after it.
                    logger.error(
                        "Polymarket WS: blend refresh raised after its write committed",
                        exc_info=task.exception(),
                    )
                if interrupted is not None:
                    raise interrupted

            try:
                for index, chunk_ids in enumerate(chunks):
                    async with buffer_lock:
                        withdraw_cohort_ids.update(withdraw_buffer)
                        withdraw_events = event_ids_for_outcomes(
                            event_id_by_outcome, withdraw_buffer,
                        )
                    if stamping is not None:
                        unwritten_events = {
                            eid for eid, last in last_chunk_of_event.items()
                            if last >= index
                        }
                        # refresh() also admits retry/deferred events. Their
                        # read must stay before the next write if any cohort
                        # or withdrawal is still unfinished. Unknown debt
                        # retains the serial path rather than assuming safety.
                        if stamping_events is None or not stamping_events.isdisjoint(
                            unwritten_events | withdraw_events
                        ):
                            await stamp_done()
                    # The plan freezes membership/caps, not a later chunk's
                    # prices. Adopt the newest values and their matching input
                    # marks together, after any preceding stamp has joined.
                    # Handlers update complementary legs under this same lock;
                    # newly buffered ids still belong to a successor flush.
                    async with buffer_lock:
                        current_chunk = {oid: price_buffer[oid] for oid in chunk_ids}
                        for oid in chunk_ids:
                            if oid in input_marks:
                                batch_marks[oid] = input_marks[oid]
                            else:
                                batch_marks.pop(oid, None)
                    wrote = await write_chunk(current_chunk, final=final)
                    # Join any safe overlapping stamp before this chunk's
                    # withdrawals, receipts or refresh.
                    await stamp_done()
                    # A wide book can arrive during the earlier write or this
                    # one. It must mature/hold this event before its fresh stamp.
                    async with buffer_lock:
                        withdraw_cohort_ids.update(withdraw_buffer)
                        withdraw_events = event_ids_for_outcomes(
                            event_id_by_outcome, withdraw_buffer,
                        )
                    if wrote:
                        unfinished_price_ids.difference_update(chunk_ids)
                        owed.extend(getattr(wrote, "written_ids", chunk_ids))
                    else:
                        if wrote is False:
                            wrote_all = False
                        else:
                            lock_deferred_events.update(
                                event_ids_for_outcomes(event_id_by_outcome, chunk_ids)
                            )
                        failed_price_events.update(
                            event_ids_for_outcomes(event_id_by_outcome, chunk_ids)
                        )
                    # #10651: finish this event's withdrawals once all of its
                    # planned price writes have completed successfully. An
                    # unrelated later chunk must not delay its coherent blend
                    # publication.
                    mature = {
                        eid
                        for eid in withdraw_events - attempted_withdraw_events
                        if last_price_chunk_of_event.get(eid, len(chunks)) <= index
                        and eid not in failed_price_events
                    }
                    if mature:
                        attempted_withdraw_events.update(mature)
                        early_withdrawn = await flush_withdrawals(
                            only_events=mature, final=final,
                        )
                        if early_withdrawn is None:
                            wrote_all = False  # retain the ordinary tail fallback
                        else:
                            owed.extend(
                                oid for oid in early_withdrawn if oid not in owed
                            )
                            withdraw_events.difference_update(mature)
                            async with buffer_lock:
                                withdraw_cohort_ids.update(withdraw_buffer)
                                withdraw_events.update(event_ids_for_outcomes(
                                    event_id_by_outcome,
                                    withdraw_cohort_ids.intersection(withdraw_buffer),
                                ))
                    ready: list[int] = []
                    held: list[int] = []
                    for oid in owed:
                        event_id = headline_event_ids.get(oid)
                        done = event_id is None or (
                            last_chunk_of_event.get(event_id, index) <= index
                            and event_id not in withdraw_events
                        )
                        (ready if done else held).append(oid)
                    owed = held
                    if ready:
                        # Q460 — THE SHIP: carry the committed prices through to
                        # `Event.win_probability_sources`, the JSONB the card
                        # renders. #837 receipt: the revisions these writes
                        # committed ride into this refresh, and only this one.
                        tail_receipts.stage(
                            [batch_marks[oid] for oid in ready if oid in batch_marks
                             and oid not in headline_event_ids.non_speakers]
                        )
                        refresh_events = event_ids_for_outcomes(
                            headline_event_ids, ready,
                        )
                        pending_reader = getattr(blend_refresher, "pending_event_ids", None)
                        unfinished_events = (
                            event_ids_for_outcomes(headline_event_ids, unfinished_price_ids)
                            | withdraw_events
                        )
                        # Capture BEFORE refresh consumes due debt and starts
                        # awaiting its database read; querying it later can miss
                        # the very in-flight cohort that needs the exclusion.
                        stamping_events = (
                            None if pending_reader is None
                            else (refresh_events | set(pending_reader())).difference(
                                unfinished_events,
                            )
                        )
                        stamping = asyncio.create_task(blend_refresher.refresh(
                            refresh_events, flush_started=flush_started,
                            defer_event_ids=unfinished_events,
                        ))
                        # One turn of the loop: the refresh takes this chunk's
                        # staged receipts and asks for its connection before
                        # the next write.
                        await asyncio.sleep(0)
            except asyncio.CancelledError:
                # A recycle mid-flush cancels the in-flight stamp too, exactly
                # as it cancelled a stamp it interrupted before, and joins it
                # before the flush ends. The refresher's cancellation path keeps
                # a stamp cancelled before its COMMIT owed for the hand-off.
                await stamp_done(cancel=True)
                raise
            finally:
                await stamp_done()
        # Keep isolation beyond cooldown expiry until every failed price row
        # has committed. A newer quote on a successful row may batch normally.
        lock_retry_events.intersection_update(
            event_ids_for_outcomes(event_id_by_outcome, lock_retry_until)
        )
        # #9934: after the prices, so a held number is judged as it now stands.
        # Events already attempted above wait for the next flush if their
        # withdrawal failed or a newer book arrived during the transaction.
        # All other withdrawals retain their ordinary after-price ordering.
        withdrawn = await flush_withdrawals(
            # A withdrawal on the held cohort would immediately reacquire its
            # blocked outcome locks and bypass the price eligibility cooldown.
            exclude_events=attempted_withdraw_events | lock_deferred_events,
            standalone=None if final else False,
            final=final,
        )
        if withdrawn is None:
            wrote_all = False
            withdrawn = []
        async with buffer_lock:
            withdraw_cohort_ids.update(withdraw_buffer)
            unfinished_events = (
                event_ids_for_outcomes(headline_event_ids, unfinished_price_ids)
                | event_ids_for_outcomes(
                    event_id_by_outcome,
                    withdraw_cohort_ids.intersection(withdraw_buffer),
                )
            )
        if not batch and not withdrawn:
            # #837 tail — a flush with no new prices still owes the stamps a row
            # lock deferred: those prices are already stored, so waiting for the
            # next venue tick would strand them on a quiet market. Free when
            # nothing is queued (no session is opened).
            await blend_refresher.refresh_pending(
                flush_started=flush_started, defer_event_ids=unfinished_events,
            )
            return wrote_all
        if not owed and not withdrawn:
            # A cohort excluded from an earlier chunk's stamp may now be
            # complete even when it contributed no additional ready inputs.
            await blend_refresher.refresh_pending(
                flush_started=flush_started, defer_event_ids=unfinished_events,
            )
            return wrote_all
        # The prices held for a withdrawal, and the withdrawal itself: one
        # refresh, never a second for an event the chunks already refreshed.
        if owed:
            tail_receipts.stage(
                [batch_marks[oid] for oid in owed if oid in batch_marks
                 and oid not in headline_event_ids.non_speakers]
            )
        await blend_refresher.refresh(
            event_ids_for_outcomes(headline_event_ids, owed)
            | event_ids_for_outcomes(event_id_by_outcome, withdrawn),
            flush_started=flush_started,
            defer_event_ids=unfinished_events,
        )
        return wrote_all

    async def _flush_standalone(flush_started=None):
        """#10090: write the standalone open legs, then their withdrawals.

        Their own loop, so a standalone chunk's UPDATE no longer holds the next
        game flush (the game loop starts a flush only when the last returns).
        These legs have no event, so nothing here refreshes a blend or stages a
        receipt. Same chunk plan, cap and buffer bookkeeping as the game flush;
        the two loops write disjoint rows. ``flush_started`` is unused.
        """
        async with buffer_lock:
            alone = standalone_open_outcome_ids(
                price_buffer, open_outcome_ids, event_id_by_outcome,
                open_complement_of,
            )
            batch = {oid: p for oid, p in price_buffer.items() if oid in alone}
        wrote_all = True
        if batch:
            chunks = plan_flush_chunks(
                batch,
                open_outcome_ids,
                FLUSH_CHUNK_ROWS,
                OPEN_FLUSH_CHUNKS_PER_FLUSH,
                open_complement_of,
            )
            stats["open_contract_flush_deferred"] += len(batch) - sum(
                len(c) for c in chunks
            )
            for chunk_ids in chunks:
                if await write_chunk({oid: batch[oid] for oid in chunk_ids}) is False:
                    wrote_all = False
        if await flush_withdrawals(standalone=True) is None:
            wrote_all = False
        return wrote_all

    async def flush_prices(flush_started=None, final=False):
        async with catalog_boundary.flushing():
            return await _flush_prices(flush_started, final=final)

    async def flush_standalone(flush_started=None):
        async with catalog_boundary.flushing():
            return await _flush_standalone(flush_started)

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
                # #9484: no successor flush, so no open-contract bound either.
                await flush_prices(final=True)
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

    async def join_flushes_then_drain():
        """#10090 review: both cancelled flush loops — the game flush with the
        stamp it joins on the way out, and the standalone flush — finish before
        the final drain reads the buffer.

        A cancelled write can still be rolling back, committing or publishing;
        draining beside it would capture the same buffer and write it again,
        and put two refreshes in the refresher. Live's c686 join (Kalshi):
        joined to COMPLETION, never to a timeout, with an error line each bound
        a loop overruns; `loops_stop` and the flushes' own DB bounds end them.
        A second cancellation landing on the join is recorded, not obeyed
        early: the join and the drain both still run, then it propagates.
        """
        flushes = {flush_task, standalone_task, admission_task, game_run_task}
        flushes.update(resolution_tasks)
        if open_run_task is not None:
            flushes.add(open_run_task)
        interrupted = None
        while not all(task.done() for task in flushes):
            try:
                await asyncio.wait(flushes, timeout=LOOP_REAP_TIMEOUT_S)
            except asyncio.CancelledError as exc:
                interrupted = exc
                continue
            running = sorted(t.get_name() for t in flushes if not t.done())
            if running:
                logger.error(
                    "Polymarket WS: cancelled producer/flush %s still running after "
                    "%.0fs; the final drain waits for it",
                    ", ".join(running), LOOP_REAP_TIMEOUT_S,
                )
        try:
            await drain_prices()
        finally:
            if interrupted is not None:
                raise interrupted

    # #9418: one CLOB client for the consumer's resolutions, made on first use
    # and closed with the consumer; and the in-flight resolution tasks, held so
    # a running settle is not garbage-collected and can be cancelled at exit.
    resolution_tasks: set = set()
    _resolution_service: list = []

    def resolution_service():
        if not _resolution_service:
            from app.services.polymarket_api import PolymarketAPIService

            _resolution_service.append(PolymarketAPIService())
        return _resolution_service[0]

    async def handle_price(msg: dict):
        """Handle best_bid_ask event."""
        asset_id = msg.get("asset_id", "")
        input_generation = routing_generation
        # #9484: a game-slate token, else an open contract's (never both —
        # the open map excludes every token the game socket carries).
        market_id = asset_to_market.get(asset_id) or open_asset_to_market.get(
            asset_id
        )
        if not market_id and asset_id not in open_asset_mirrors:
            return
        _note_raw(asset_id)

        best_bid = msg.get("best_bid")
        best_ask = msg.get("best_ask")
        if best_bid is None or best_ask is None:
            return

        try:
            bid_f = float(best_bid)
            ask_f = float(best_ask)
        except (ValueError, TypeError):
            return

        # #9913: kept before the width test below, because a wide book is the
        # one `handle_trade` needs to see.
        latest = books_by_asset.get(asset_id, (None,))[0]
        if latest != (bid_f, ask_f):
            books_by_asset[asset_id] = ((bid_f, ask_f), latest)

        # #1578: never stream a midpoint from a book nobody will trade inside.
        # This path matters most of the five, because it is the only one that
        # UPDATEs an outcome directly rather than going through the upsert — a
        # wide quote arriving here would overwrite a good stored price with a
        # phantom. Returning early leaves the existing value untouched; the
        # real-trade stream (handle_trade, below) is what moves an illiquid
        # market's price, which is correct.
        #
        # #9934: but the book is still evidence about the price we HOLD. A
        # held number the wide book prices out is queued for withdrawal.
        legs = books_with_complements(
            _tick_targets(asset_id), bid_f, ask_f, open_complement_of
        )
        if _poly_book_is_untradeable(bid_f, ask_f):
            async with buffer_lock:
                if input_generation != routing_generation:
                    return
                for outcome_id, leg_bid, leg_ask in legs:
                    withdraw_buffer[outcome_id] = (leg_bid, leg_ask)
            return
        if legs:
            async with buffer_lock:
                if input_generation != routing_generation:
                    return
                for outcome_id, _bid, _ask in legs:
                    withdraw_buffer.pop(outcome_id, None)

        prob = (bid_f + ask_f) / 2
        if prob <= 0 or prob >= 1:
            return

        # Q489: the outcome this ASSET is the book for — not "the market's first
        # outcome". `prob` here is the midpoint of THIS token's own book, so on
        # the No token it is P(No), which belongs on the No leg and nowhere else.
        targets = _tick_targets(asset_id)
        if not targets:
            return

        async with buffer_lock:
            if input_generation != routing_generation:
                return
            for outcome_id, leg_prob in with_complements(
                targets, prob, open_complement_of
            ):
                price_buffer[outcome_id] = leg_prob
                _mark_input(outcome_id, leg_prob, "price", msg)

    def _tick_targets(asset_id: str) -> list[int]:
        """Every leg a tick in this token prices: its owner, then its mirrors.

        #9736: a token two markets name (the NLDS board's Cubs leg and the
        standalone Cubs binary) is subscribed once; both legs are the same
        contract, so both take its price."""
        targets = []
        owner = asset_to_outcome.get(asset_id)
        if owner is None:
            owner = open_asset_to_outcome.get(asset_id)
        if owner is not None:
            targets.append(owner)
        targets.extend(
            oid for oid, _mid in open_asset_mirrors.get(asset_id, ())
            if oid != owner
        )
        return targets

    def _note_raw(asset_id):
        # #10090 — one venue message for each game this token prices, counted
        # before the price policy decides; never raises into the socket.
        try:
            for event_id in {
                event_id_by_outcome.get(oid) for oid in _tick_targets(asset_id)
            }:
                tail_receipts.note_raw(event_id)
        except Exception:
            return

    def _mark_input(outcome_id, prob, kind, msg):
        # Under `buffer_lock`, so seq order is buffer order. Never raises into
        # the socket: a receipt is evidence about the price, not the price.
        try:
            mark = tail_receipts.note_input(
                event_id_by_outcome.get(outcome_id), outcome_id, prob, kind,
                msg.get("timestamp"),
            )
        except Exception:
            return
        if mark is not None:
            input_marks[outcome_id] = mark

    async def handle_trade(msg: dict):
        """Handle last_trade_price event."""
        asset_id = msg.get("asset_id", "")
        input_generation = routing_generation
        # #9484: a game-slate token, else an open contract's (never both —
        # the open map excludes every token the game socket carries).
        market_id = asset_to_market.get(asset_id) or open_asset_to_market.get(
            asset_id
        )
        if not market_id and asset_id not in open_asset_mirrors:
            return
        _note_raw(asset_id)

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
        targets = _tick_targets(asset_id)
        if not targets:
            return

        # #9733: a leftover smaller than any order the venue accepts is not a
        # price. Counted, so a refusal is a number and not an absence.
        if not trade_sets_a_price(msg):
            stats["trades_below_min_order"] += 1
            return

        # #9913: nor is a trade that swept past the edge of a wide book. The
        # leg keeps the last price a book supported.
        if trade_prints_outside_wide_book(prob, books_by_asset.get(asset_id, ())):
            stats["trades_outside_wide_book"] += 1
            return

        async with buffer_lock:
            if input_generation != routing_generation:
                return
            for outcome_id, leg_prob in with_complements(
                targets, prob, open_complement_of
            ):
                price_buffer[outcome_id] = leg_prob
                _mark_input(outcome_id, leg_prob, "trade", msg)
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

        #9418: the winner is the leg owning the CLOB-confirmed winning TOKEN
        (:func:`ws_resolution_verdict`), never the push's label. The CLOB read is
        a network call, so it runs as its own task: the shard's reader is the
        caller here, and a slow venue must not hold up the price frames behind
        this one.
        """
        condition_id = msg.get("market", "")
        market_id = condition_to_market.get(condition_id)
        if not market_id:
            return
        task = asyncio.create_task(_settle_resolution(
            msg, condition_id, market_id,
            list(outcomes_by_market.get(market_id, [])), dict(asset_to_outcome),
        ))
        resolution_tasks.add(task)
        task.add_done_callback(resolution_tasks.discard)

    async def _ask_venue(winning_asset_id, condition_id: str, outcomes, token_owners):
        """One confirmation attempt: CLOB first, then Gamma when CLOB has not
        decided (#9418 after-check — CLOB lags the push by minutes, Gamma
        does not). Either read failing is an `unconfirmed` answer, not an error.
        """
        outcome_ids = [oid for oid, _ in outcomes]
        clob_market = None
        try:
            clob_market = await asyncio.wait_for(
                resolution_service().get_clob_market_by_condition(condition_id),
                timeout=RESOLUTION_CLOB_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "Polymarket WS: CLOB read for %s failed", condition_id[:20],
                exc_info=True,
            )
        verdict = ws_resolution_verdict(
            winning_asset_id, clob_market, outcome_ids, token_owners
        )
        if verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            return verdict
        try:
            gamma_market = await asyncio.wait_for(
                resolution_service().get_closed_gamma_market_raw(condition_id),
                timeout=RESOLUTION_CLOB_TIMEOUT_S,
            )
        except Exception:
            logger.warning(
                "Polymarket WS: Gamma read for %s failed", condition_id[:20],
                exc_info=True,
            )
            return verdict
        gamma_verdict = gamma_resolution_verdict(
            winning_asset_id, gamma_market, outcome_ids, token_owners
        )
        if gamma_verdict[0] != WS_RESOLUTION_UNCONFIRMED:
            stats["resolutions_via_gamma"] += 1
        return gamma_verdict

    async def _write_resolution(condition_id, market_id, outcomes, verdict, msg):
        async with get_task_session() as session:
            written = await _apply_ws_resolution(
                session, market_id, outcomes, verdict
            )
            # #9484: the terminal invalidation carries the `settled_at`
            # this transaction stored, read back inside it — the market is
            # resolved exactly as REST will now serve it.
            settled_at = (
                await session.execute(
                    select(FuturesMarket.settled_at).where(
                        FuturesMarket.id == market_id,
                        FuturesMarket.status == "resolved",
                    )
                )
            ).scalar_one_or_none()
            if settled_at is not None:
                queue_market_change(
                    session,
                    market_id=market_id,
                    source="polymarket",
                    outcome_observed_at={},
                    terminal=True,
                    updated_at=settled_at,
                )
        await blend_refresher.publish_market_changes(session)
        logger.info(
            "Polymarket WS: %s resolved (verdict=%s, label=%s, %d/%d outcomes "
            "written, no calibration scalar captured)",
            condition_id[:20], verdict[0], msg.get("winning_outcome", ""),
            written, len(outcomes),
        )

    async def _settle_resolution(msg: dict, condition_id: str, market_id: int, outcomes, token_owners):
        """Resolve now; grade as soon as the venue confirms the token.

        The market is marked resolved on the FIRST answer whatever it is, so
        a settled market reads settled at once (the pre-existing behaviour).
        If that answer is `unconfirmed`, the venue is asked again on
        :data:`RESOLUTION_RECHECK_DELAYS_S` and the first decided verdict is
        written over it — `settled_at` is COALESCEd, so the second write keeps
        the first time. A recycle that cancels the wait loses only the grade,
        which the Gamma rail then supplies, exactly as before.
        """
        winning_asset_id = msg.get("winning_asset_id")
        async def ask():
            return await _ask_venue(winning_asset_id, condition_id, outcomes, token_owners)

        writes = []

        async def write(verdict):
            await _write_resolution(condition_id, market_id, outcomes, verdict, msg)
            # Counted at the write, not after the re-asks: a recycle cancels
            # the wait, and the resolution it already committed still counts.
            # `resolutions_<kind>` is the FIRST answer, as before #9418's
            # re-ask; a grade written on a re-ask is `resolutions_confirmed_late`.
            if not writes:
                stats["resolutions"] += 1
                stats[f"resolutions_{verdict[0]}"] += 1
            else:
                stats["resolutions_confirmed_late"] += 1
            writes.append(verdict[0])

        try:
            await settle_with_rechecks(ask, write)
        except Exception:
            stats["errors"] += 1
            logger.exception("Polymarket WS: resolution error")

    ws.on_price = handle_price
    ws.on_trade = handle_trade
    ws.on_resolved = handle_resolved

    # #10090: start to start, like the Kalshi socket's; see `run_flush_cadence`.
    # #10657: set before the loop is cancelled, so a cancellation lost inside
    # a flush still ends the loop at its next turn (`run_flush_cadence`).
    loops_stop = asyncio.Event()

    async def flush_loop():
        await run_flush_cadence(
            flush_prices, flush_period, stop=loops_stop,
            failed_retry_interval_s=PRICE_FLUSH_SECONDS,
        )

    async def standalone_loop():
        await run_flush_cadence(
            flush_standalone, PRICE_FLUSH_SECONDS, stop=loops_stop,
        )

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
            open_connected = any(s.is_connected for s in open_sockets)
            if open_sockets:
                _log_open_contract_line(stats, open_sockets[0].stats)
            _report_liveness(
                "polymarket",
                (
                    "streaming"
                    if getattr(ws, "is_connected", False) or open_connected
                    else "disconnected"
                ),
                legs=len(asset_ids),
                msgs=ws_stats.get("messages", 0),
                served=ws_stats.get("assets_served", 0),
                stamped=blend["stamped"],
                no_reading=blend["no_reading"],
            )

    flush_task = asyncio.create_task(flush_loop(), name="polymarket-flush-loop")
    standalone_task = asyncio.create_task(
        standalone_loop(), name="polymarket-standalone-flush-loop"
    )
    stats_task = asyncio.create_task(stats_loop(), name="polymarket-stats-loop")

    _report_liveness("polymarket", "subscribing", legs=len(asset_ids))

    # #9462 review: the markets this run can actually attribute a tick to. A
    # market the slate SELECTED but whose tokens the top-up could not find is
    # not among them, however many of its event's props are streaming.
    legged_market_ids = {
        asset_to_market[a] for a in asset_to_outcome if a in asset_to_market
    }

    # One callback/buffer/session owner spans routine catalog refreshes. Only
    # changed subscriptions reconnect; unchanged open-contract shards keep
    # their books and receive queues instead of rebuilding the whole fleet.
    async def refresh_catalog(slate, open_read):
        nonlocal open_run_task, routing_generation
        admission, failed, bridge, bridge_failed = open_read
        stats["open_contract_admission_error"] = failed
        stats["open_contract_bridge_error"] = bridge_failed
        fresh_open_markets = (
            {}
            if admission is None
            else {
                oid: admission.asset_to_market[token]
                for token, oid in admission.asset_to_outcome.items()
            }
        )
        if admission is not None:
            fresh_open_markets.update(admission.mirrored_outcomes())
            for key, value in admission.counts.items():
                stats[f"open_contract_{key}"] = value
        async with catalog_boundary.updating():
            async with buffer_lock:
                routing_generation += 1
                # Keep accepted writes' ownership through their drain even if the
                # token has left the catalog. New inputs use ONLY the fresh maps.
                protected = set(price_buffer) | set(withdraw_buffer)
                current_outcomes = (
                    slate["market_by_outcome"].keys() | fresh_open_markets.keys()
                )
                old_debt = protected - current_outcomes
                for owners in (market_by_outcome, event_id_by_outcome):
                    for oid in owners.keys() - old_debt:
                        del owners[oid]
                asset_ids[:] = slate["asset_ids"]
                market_ids.clear()
                market_ids.update(slate["market_ids"])
                for name, target in (
                    ("asset_to_outcome", asset_to_outcome),
                    ("asset_to_market", asset_to_market),
                    ("condition_to_market", condition_to_market),
                    ("event_id_by_market", event_id_by_market),
                    ("outcomes_by_market", outcomes_by_market),
                ):
                    target.clear()
                    target.update(slate[name])
                market_by_outcome.update(slate["market_by_outcome"])
                market_by_outcome.update(fresh_open_markets)
                fresh_events = {
                    oid: event_id_by_market[mid]
                    for oid, mid in slate["market_by_outcome"].items()
                    if mid in event_id_by_market
                }
                event_id_by_outcome.update(bridge)
                event_id_by_outcome.update(fresh_events)
                non_blend_outcome_ids.intersection_update(old_debt)
                non_blend_outcome_ids.update(
                    oid
                    for oid, mid in slate["market_by_outcome"].items()
                    if mid in slate["non_blend_market_ids"]
                )
                open_outcome_ids.intersection_update(old_debt)
                open_outcome_ids.update(fresh_open_markets)
                for target, fresh in (
                    (
                        open_asset_to_market,
                        {} if admission is None else admission.asset_to_market,
                    ),
                    (
                        open_asset_to_outcome,
                        {} if admission is None else admission.asset_to_outcome,
                    ),
                    (
                        open_asset_mirrors,
                        {} if admission is None else admission.asset_mirrors,
                    ),
                ):
                    target.clear()
                    target.update(fresh)
                for oid in open_complement_of.keys() - old_debt:
                    del open_complement_of[oid]
                if admission is not None:
                    open_complement_of.update(admission.complement_of)
                live_assets = (
                    asset_to_outcome.keys()
                    | open_asset_to_outcome.keys()
                    | open_asset_mirrors.keys()
                )
                for token in books_by_asset.keys() - live_assets:
                    del books_by_asset[token]
                for held in (lock_retry_until, withdrawal_retry_until):
                    for oid in held.keys() - protected:
                        del held[oid]
                legged_market_ids.clear()
                legged_market_ids.update(
                    asset_to_market[a] for a in asset_to_outcome if a in asset_to_market
                )
            stats["assets_subscribed"] = len(asset_ids)
            stats["assets_mapped"] = len(asset_to_outcome)
            stats["assets_unmapped"] = len(slate["unmapped_assets"])
            stats["moneyline_legs_subscribed"] = len(slate["outcome_yes_token"])
            stats["open_contract_bridged_outcomes"] = len(bridge)
            stats["open_contract_bridged_events"] = len(set(bridge.values()))
            stats["open_contract_assets"] = len(open_asset_to_outcome)
            if not open_sockets:
                open_ws = PolymarketWebSocket(
                    max_concurrent_handshakes=OPEN_CONTRACT_MAX_CONCURRENT_HANDSHAKES,
                    max_queue=OPEN_CONTRACT_MAX_QUEUE,
                    price_book_snapshots=book_snapshot_prices_enabled(),
                )
                open_ws.on_price = handle_price
                open_ws.on_trade = handle_trade
                open_sockets.append(open_ws)
            open_ws = open_sockets[0]
            # Existing flag is re-read at the same catalog boundary as before.
            snapshot_prices = book_snapshot_prices_enabled()
            desired_open = sorted(open_asset_to_outcome)
            if open_run_task is None or open_run_task.done():
                if open_run_task is not None:
                    await asyncio.gather(open_run_task, return_exceptions=True)
                open_run_task = asyncio.create_task(
                    run_open_client(open_ws, desired_open, snapshot_prices),
                    name="polymarket-open-sockets",
                )
                # Start the owner before allowing an immediate second refresh.
                await asyncio.sleep(0)
            else:
                open_ws.update_asset_ids(
                    desired_open, price_book_snapshots=snapshot_prices
                )

    async def run_open_client(open_ws, desired_open, snapshot_prices):
        try:
            await open_ws.run_refreshable(
                desired_open,
                price_book_snapshots=snapshot_prices,
            )
        except Exception:
            stats["open_contract_admission_error"] = True
            logger.exception("Polymarket WS: open-contract client failed")

    async def read_catalog_open(slate):
        return await read_open_contracts(
            set(slate["asset_ids"]),
            slate["market_ids"],
            tokens_by_contract(
                slate["asset_to_outcome"],
                {
                    oid: ext
                    for pairs in slate["outcomes_by_market"].values()
                    for oid, ext in pairs
                },
            ),
        )

    async def admit_open_contracts():
        await refresh_catalog(
            game_slate,
            preread if preread is not None else await read_catalog_open(game_slate),
        )

    admission_task = asyncio.create_task(admit_open_contracts())

    # #9418: the slate's live arm, re-read while the socket runs — the slate
    # query above with `_slate_event_window()` narrowed to its live arm, so it
    # can only name an event that turned live after the slate was read.
    # #9462 review: read per MARKET, beside the reading the card renders, so
    # an event counts as subscribed only when the leg that feeds its displayed
    # number is mapped here (`unadmitted_live_events`).
    async def load_unadmitted_live_event_ids():
        async with get_task_session() as session:
            result = await session.execute(
                select(
                    FuturesMarket.event_id,
                    FuturesMarket.id,
                    Event.win_probability_sources["polymarket"],
                )
                .select_from(FuturesOutcome)
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.event_id.isnot(None),
                    Event.status == "live",
                    _slate_market_filter(),
                )
                .distinct()
            )
            return unadmitted_live_events(result.all(), legged_market_ids)

    def start_game_socket():
        # Reuse the open arm's per-shard owner for game quotes/resolutions.
        # Empty means no subscriptions here, never the legacy all-market run.
        return asyncio.create_task(
            ws.run_refreshable(asset_ids.copy()),
            name="polymarket-game-sockets",
        )

    game_run_task = start_game_socket()
    stop_task = asyncio.create_task(stop.wait()) if stop is not None else None
    watch_task = None
    exit_reason = "consumer_exit"
    try:
        while True:
            cycle_started_at = time.monotonic()
            watch_task = asyncio.create_task(
                watch_for_unadmitted_live_events(
                    load_unadmitted_live_event_ids,
                    event_id_by_market.values(),
                    arm="Polymarket",
                    started_at=run_started_at,
                ),
            )
            done, _ = await asyncio.wait(
                {game_run_task, watch_task}
                | ({stop_task} if stop_task is not None else set()),
                timeout=SUBSCRIPTION_REFRESH_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task is not None and stop_task in done:
                stats["status"] = "stopped"
                exit_reason = "shutdown"
                break
            if game_run_task in done:
                game_run_task.result()
                break
            admitted = None
            if watch_task in done:
                if watch_task.exception() is None:
                    admitted = watch_task.result()
                else:
                    logger.error(
                        "Polymarket WS admission watcher failed; keeping sockets to the timer",
                        exc_info=watch_task.exception(),
                    )
                    remaining = max(
                        0,
                        SUBSCRIPTION_REFRESH_SECONDS
                        - (time.monotonic() - cycle_started_at),
                    )
                    finished, _ = await asyncio.wait(
                        {game_run_task}
                        | ({stop_task} if stop_task is not None else set()),
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if stop_task is not None and stop_task in finished:
                        stats["status"] = "stopped"
                        exit_reason = "shutdown"
                        break
                    if finished:
                        game_run_task.result()
                        break
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
            watch_task = None
            # Loading does not close either client: quotes still reach these
            # same buffers while the database/top-up prepares the next slate.
            await admission_task
            if not open_asset_to_outcome and not open_asset_mirrors:
                # No open fleet to retain: preserve the game-only runner's
                # existing recycle/debt-handoff contract.
                stats["status"] = "resubscribe"
                if admitted:
                    stats["recycle_reason"] = "admission"
                    stats["admitted_event_ids"] = sorted(admitted)[:20]
                break
            try:
                fresh_slate = await load_game_slate()
                fresh_open = await read_catalog_open(fresh_slate)
                if fresh_open[1]:
                    stats["open_contract_admission_error"] = True
                    logger.warning(
                        "Polymarket WS open admission failed; retaining the current catalog"
                    )
                    run_started_at = time.monotonic()
                    continue
            except Exception:
                logger.exception(
                    "Polymarket WS catalog refresh failed; keeping subscriptions"
                )
                run_started_at = time.monotonic()
                continue
            # Install new callback ownership before subscribing new tokens.
            # The existing refreshable owner changes only affected shards, so
            # unrelated live games keep their connections, books and coverage.
            await refresh_catalog(fresh_slate, fresh_open)
            if game_run_task.done():
                # Loading/updating can yield while the retained client exits.
                # Propagate its failure (or end this run) just as the wait above.
                game_run_task.result()
                break
            ws.update_asset_ids(asset_ids.copy())
            run_started_at = time.monotonic()
            stats["catalog_refreshes"] = stats.get("catalog_refreshes", 0) + 1
            stats["recycle_reason"] = "admission" if admitted else "timer"
            if admitted:
                stats["admitted_event_ids"] = sorted(admitted)[:20]
            logger.info(
                "Polymarket WS refreshed game slate (%s); open catalog retained: %d assets",
                stats["recycle_reason"], len(open_asset_to_outcome),
            )
    except asyncio.CancelledError:
        # Real shutdown, not the planned recycle (CERT-491) — keep it travelling
        # so the runner stops instead of relaunching. Buffer still drains below.
        exit_reason = "shutdown"
        raise
    finally:
        loops_stop.set()
        flush_task.cancel()
        standalone_task.cancel()
        stats_task.cancel()
        # #9418: an unfinished settle rolls back; the market stays for the
        # Gamma rail, which is where an `unconfirmed` verdict leaves it anyway.
        for task in list(resolution_tasks):
            task.cancel()
        # #9484: cancelled here, awaited only after the drain below, so a
        # second cancellation landing on that await can never skip the drain.
        admission_task.cancel()
        game_run_task.cancel()
        if watch_task is not None:
            watch_task.cancel()
        if stop_task is not None:
            stop_task.cancel()
        if open_run_task is not None:
            open_run_task.cancel()
        # Q491 repair (CERT-654 BLOCK): the last flush has no successor, so it
        # must RETRY rather than requeue into a buffer nobody will read again.
        # #10090 review: only after both cancelled flushes have finished.
        try:
            await join_flushes_then_drain()
        finally:
            # #9462 review: the drain returns once the price BUFFER is empty,
            # but a price it (or the last flush) committed inside the 2 s
            # throttle is still owed its blend stamp. The next run adopts it.
            stats["blend_pending_carried"] = hand_off_pending(blend_refresher)
            await asyncio.gather(
                admission_task, game_run_task,
                *([watch_task] if watch_task is not None else []),
                *([stop_task] if stop_task is not None else []),
                *([open_run_task] if open_run_task is not None else []),
                return_exceptions=True,
            )
            # #10657: a loop that lost its cancellation ends here, after the
            # drain, rather than outliving the run on its closed sessions.
            stats["loops_unreaped"] = await reap_stopped_loops(
                "polymarket", (flush_task, standalone_task, stats_task),
            )
            # #9418: closed after the drain, never before it, so a cancellation
            # landing on this await cannot skip a flush.
            if _resolution_service:
                with contextlib.suppress(Exception):
                    await _resolution_service[0].close()
            # #837 receipt — the next run's refresher starts empty of chains,
            # so a held price still open here was never stamped by this run.
            # Said so; the stamp itself is carried above.
            with contextlib.suppress(Exception):
                tail_receipts.close_all(
                    "recycle_reset" if stats.get("status") == "resubscribe"
                    else exit_reason
                )

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
    if open_sockets:
        open_exit = open_sockets[0].stats
        stats["open_contract_shards"] = open_exit.get("shards", 0)
        stats["open_contract_assets_served"] = open_exit.get("assets_served", 0)
        stats["open_contract_messages"] = open_exit.get("messages", 0)
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
