"""#10090 — the Polymarket half of the 30-second poll, read off CLOB token prices.

WHY. Speed's ship: Polymarket prices off the socket refresh in about 30 s, not
about 14 min. The first build read Gamma ``/events``, and that cannot get there:
20 nested events measured 1.6 MB (non-game) to 3.3 MB (game) on 2026-10-30, so a
30 s rotation over the off-socket population would move roughly 0.5-1 GB of JSON
every 30 s. A CLOB top-of-book read is about 110 bytes per token.

SHIPPED DARK. ``VENUE_POLL_30S_PM_SOURCE`` = ``gamma`` (default, the first
build exactly) or ``clob``. It only matters when ``VENUE_POLL_30S_ENABLED``
already runs the Polymarket venue. Turning it on is Alex's word.

THE POPULATION HAS NO TOKENS, SO THE PASS LEARNS THEM
-----------------------------------------------------
With the socket's open-contract arm on (the production default), the poll's
population excludes every market with a persisted token key, because the socket
streams those. What is left, measured 2026-10-30: 6,643 markets and 67,904
legs, all without a token key, 99.3% of the legs bare condition ids (negRisk
fields, game "More Markets" parents). A leg's token is read once from Gamma
``/markets?condition_ids=`` (the token top-up's read, 40 per request, measured
6.3 KB per condition and 90.6% resolved on a 3,912-condition sample) and kept in
a Redis hash, never in the database: a stored token would move the market onto
the open socket at its next recycle, which changes socket scope, and that is not
this module's to change. Tokens never change for a condition, so the hash only
grows; a condition Gamma does not return is retried after
``TOKEN_MISS_RETRY_S``.

Which token is the leg's book is the socket's own rule
(``polymarket_open_contracts.contract_key``): a bare or ``_yes`` leg is token 0
of its condition, a ``_no`` or ``_side1`` leg is token 1. Token 0 is read; the
token-1 leg is its complement (below), as ``with_complements`` prices it on the
socket.

PRICING IS THE SOCKET'S BOOK RULE, BY REUSE
-------------------------------------------
Gamma ``outcomePrices`` and a CLOB book are different instruments, so this path
maps the CLOB onto the rule the socket already applies to a book
(``polymarket_ws`` ``handle_price``), not a new one — :func:`socket_book_price`:

* both sides must be quoted: a side with no order gets no quote in the socket's
  snapshot extractor (``_snapshot_quotes``), so a one-sided or empty book is not
  a price;
* bid above ask is refused, as ``_price_change_quotes`` refuses it;
* a book ``_poly_book_is_untradeable`` (#1578, gotcha 19's wide-spread guard)
  is not a price — the socket withdraws on it, the poll falls back (below);
* the price is the midpoint, refused outside (0, 1);
* the complementary leg is ``with_complements`` / ``books_with_complements``
  (#9733 / #9934): ``1 - p`` over ``(1 - ask, 1 - bid)``.

The item then goes through ``futures_price_refresh._write_prices`` with the
first build's :class:`~app.tasks.venue_poll_30s.PollWrite`, so its out-of-range,
empty-book (#6676/#9083), unknown-leg and settled-leg refusals, the newer-writer
guard, write-on-change and the history bound all hold unchanged. Two Gamma-path
refusals cannot fire on a price this rule accepts, and tests prove it over every
integer-cent book rather than asserting it: the parent-book refusal (#10298:
the book prices the raw value out — a midpoint sits inside its book) and the
empty-book midpoint (#6676: its spread is far past the untradeable bar).

NO USABLE BOOK → THE GAMMA READING, ON ITS OWN SLOWER ROTATION
--------------------------------------------------------------
A leg whose token is unknown, or whose book the rule above refuses, is never
written "no price". :func:`clob_pass` returns the population cut down to exactly
those legs, and the first build's Gamma rotation prices them on its own cursor
(``polymarket_gamma``) with its own resolver (gotcha 19's ``lastTradePrice``,
#10298, field coherence, venue-settled). A CLOB-priced leg is never handed to
Gamma, so the two instruments never alternate on one row. On the 3,545 resolved
tokens of the sample, 76% read a usable book; 14% had no bid and 10% were wider
than the untradeable bar — the long tails of fields, which the socket also
declines today. The CLOB rotation (``polymarket_clob``) keeps the Gamma
rotation's cursor rules: a 429 keeps its place, a group that failed with its
full wall (or the pass's first group, which had all the time there was) is
passed and counted (``clob_groups_failed``), and a unit too big for the whole
budget is counted (``clob_units_oversize``) and left to Gamma.

COST, at the measured sizes (2026-10-30)
----------------------------------------
* CLOB ``/prices``: published 500 items per request and 500 requests per 10 s
  (Cloudflare-throttled, queued not rejected; docs.polymarket.com "Rate
  Limits"). A BUY and a SELL item per token, so 250 tokens a request: ~61,000
  resolved tokens are ~245 requests per full rotation, 82 per 10 s = 16% of
  the limit; ~13.5 MB up and ~6.7 MB down per rotation; 0.29 s per request,
  ``CLOB_CONCURRENCY`` at a time, inside the pass budget less
  ``GAMMA_RESERVE_S``.
* Gamma ``/markets`` (300 per 10 s): ``TOKEN_REQUESTS_PER_PASS`` reads per pass
  until the hash is warm — about 1,690 reads and 425 MB once, then only new
  conditions.
* Redis: one hash, ~61,000 fields of ~170 bytes, about 10 MB of the 500 MB
  instance.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from app.tasks.venue_poll_30s import (
    _KEY_PREFIX,
    _MIN_REQUEST_S,
    REQUEST_TIMEOUT_S,
    Unit,
    _env_float,
    _env_int,
    _redis,
    _write_group,
    backoff_remaining,
    clear_backoff,
    is_rate_limited,
    pack_requests,
    read_cursor,
    rotate,
    start_backoff,
    write_cursor,
)

logger = logging.getLogger(__name__)

PM_SOURCE_ENV = "VENUE_POLL_30S_PM_SOURCE"

#: ``POST /prices`` takes 500 items; each token is a BUY and a SELL item.
CLOB_TOKENS_PER_REQUEST = 250
#: A full rotation of today's population is ~245 requests.
CLOB_REQUESTS_PER_PASS = _env_int("VENUE_POLL_30S_PM_CLOB_REQUESTS", 300)
#: Reads in flight. Measured 0.29 s a read sequentially: 8 at a time puts a full
#: rotation (~245 reads) near 9 s of wall, a burst well inside 500 per 10 s.
CLOB_CONCURRENCY = max(1, _env_int("VENUE_POLL_30S_PM_CLOB_CONCURRENCY", 8))
#: Seconds of the pass kept back for the Gamma reading of the legs the CLOB
#: could not price, so a slow CLOB pass can never starve that rotation.
GAMMA_RESERVE_S = _env_float("VENUE_POLL_30S_PM_GAMMA_RESERVE_S", 6.0)

#: Gamma ``/markets?condition_ids=`` — the token top-up's own batch size.
TOKEN_CONDITIONS_PER_REQUEST = 40
TOKEN_REQUESTS_PER_PASS = _env_int("VENUE_POLL_30S_PM_TOKEN_REQUESTS", 24)
TOKEN_CONCURRENCY = 4
TOKEN_MISS_RETRY_S = 3600
TOKEN_HASH_TTL_S = 30 * 86400
_TOKEN_KEY = f"{_KEY_PREFIX}:pm_token0"
_MISS = "-"

#: The CLOB has its own Cloudflare limit, so its 429 backs off only itself.
CLOB_BACKOFF_VENUE = "polymarket_clob"


def pm_source(environ=None) -> str:
    """``clob`` only when ``VENUE_POLL_30S_PM_SOURCE`` says so; else ``gamma``."""
    raw = (environ if environ is not None else os.environ).get(PM_SOURCE_ENV, "")
    return "clob" if raw.strip().lower() == "clob" else "gamma"


# ── the socket's book rule ─────────────────────────────────────────────────────

#: Stand-in leg ids, so the complement is computed by the socket's own helpers.
_YES, _NO = 0, 1


def socket_book_price(bid: Optional[float], ask: Optional[float]) -> tuple[str, Optional[float]]:
    """The socket's decision on one token's top of book: ``("price", p)`` or a refusal.

    Refusals: ``no_book`` (a side unquoted), ``crossed`` (bid above ask),
    ``wide`` (``_poly_book_is_untradeable``), ``out_of_range`` (midpoint not in
    (0, 1)). See the module docstring for where each comes from in
    ``polymarket_ws``.
    """
    from app.tasks.polymarket import _poly_book_is_untradeable

    if bid is None or ask is None:
        return "no_book", None
    if bid > ask:
        return "crossed", None
    if _poly_book_is_untradeable(bid, ask):
        return "wide", None
    prob = (bid + ask) / 2
    if prob <= 0 or prob >= 1:
        return "out_of_range", None
    return "price", prob


def clob_item(condition_id: str, bid: float, ask: float, prob: float) -> dict:
    """A ``_write_prices`` item for one condition priced off its token-0 book.

    ``no`` (the ``_no`` / ``_side1`` leg) is the socket's complement of the
    same book, computed by ``with_complements`` / ``books_with_complements``.
    """
    from app.tasks.polymarket_ws import books_with_complements, with_complements

    (_y, yes_p), (_n, no_p) = with_complements([_YES], prob, {_YES: _NO})
    (_y, yes_bid, yes_ask), (_n, no_bid, no_ask) = books_with_complements(
        [_YES], bid, ask, {_YES: _NO}
    )
    return {
        "external_id": condition_id,
        "probability": yes_p,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "last_price": None,
        "no": {
            "probability": no_p,
            "yes_bid": no_bid,
            "yes_ask": no_ask,
            "last_price": None,
        },
    }


# ── tokens ────────────────────────────────────────────────────────────────────


def leg_condition(ext: str) -> Optional[str]:
    """The condition a leg prices off, when the socket's rule can place it.

    ``contract_key`` must read the leg (a ``0x`` condition and a token index),
    or the leg is not CLOB-priceable here and goes to the Gamma reading.
    """
    from app.tasks.polymarket_open_contracts import contract_key

    key = contract_key(ext)
    return key[0] if key is not None else None


#: condition → (token or None, retry-after epoch for a miss)
_TOKENS: dict[str, tuple[Optional[str], float]] = {}


def _parse_cached(raw) -> tuple[Optional[str], float]:
    value = raw.decode() if isinstance(raw, bytes) else str(raw)
    if value.startswith(_MISS):
        try:
            return None, float(value[len(_MISS):])
        except ValueError:
            return None, 0.0
    return value, float("inf")


def cached_tokens(conditions, *, now: float) -> dict[str, Optional[str]]:
    """What the cache knows: condition → token, or None for a fresh miss.

    A condition absent from the result is unknown (never asked, or a miss due
    for a retry). Redis is read only for conditions this process has not seen.
    """
    wanted = [c for c in conditions if c not in _TOKENS]
    if wanted:
        try:
            rc = _redis()
            for i in range(0, len(wanted), 1000):
                chunk = wanted[i : i + 1000]
                for cond, raw in zip(chunk, rc.hmget(_TOKEN_KEY, chunk)):
                    if raw is not None:
                        _TOKENS[cond] = _parse_cached(raw)
        except Exception as exc:  # noqa: BLE001 — unknown, so asked again
            logger.warning("venue_poll_pm_clob: token cache unreadable: %s", exc)
    out: dict[str, Optional[str]] = {}
    for cond in conditions:
        held = _TOKENS.get(cond)
        if held is None:
            continue
        token, retry_after = held
        if token is not None or now < retry_after:
            out[cond] = token
    return out


def store_tokens(found: dict[str, Optional[str]], *, now: float) -> None:
    if not found:
        return
    mapping = {}
    for cond, token in found.items():
        if token is None:
            _TOKENS[cond] = (None, now + TOKEN_MISS_RETRY_S)
            mapping[cond] = f"{_MISS}{now + TOKEN_MISS_RETRY_S:.0f}"
        else:
            _TOKENS[cond] = (token, float("inf"))
            mapping[cond] = token
    try:
        rc = _redis()
        rc.hset(_TOKEN_KEY, mapping=mapping)
        rc.expire(_TOKEN_KEY, TOKEN_HASH_TTL_S)
    except Exception as exc:  # noqa: BLE001 — this process still holds them
        logger.warning("venue_poll_pm_clob: tokens not saved: %s", exc)


def token0_of(market) -> Optional[str]:
    """Token 0 of a Gamma market: the book of its first outcome, or None.

    Only a two-token condition: any other shape has no ``contract_key`` token
    the socket would place, so it is refused rather than guessed.
    """
    tokens = [str(t) for t in (getattr(market, "clob_token_ids", None) or []) if str(t)]
    return tokens[0] if len(tokens) == 2 else None


async def resolve_tokens(service, conditions: list[str], *, deadline: float, stats: dict) -> None:
    """Ask Gamma for up to ``TOKEN_REQUESTS_PER_PASS`` batches of unknown tokens.

    A 429 stops the asking for this pass (gotcha 36); the conditions stay
    unknown and their legs take the Gamma reading meanwhile.
    """
    batches = [
        conditions[i : i + TOKEN_CONDITIONS_PER_REQUEST]
        for i in range(0, len(conditions), TOKEN_CONDITIONS_PER_REQUEST)
    ][:TOKEN_REQUESTS_PER_PASS]
    if not batches:
        return
    gate = asyncio.Semaphore(TOKEN_CONCURRENCY)

    async def ask(batch):
        async with gate:
            left = deadline - time.monotonic()
            if left < _MIN_REQUEST_S:
                return batch, None
            markets = await asyncio.wait_for(
                service.get_markets_by_conditions(batch, batch_size=len(batch)),
                timeout=min(REQUEST_TIMEOUT_S, left),
            )
            return batch, markets

    found: dict[str, Optional[str]] = {}
    for result in await asyncio.gather(*(ask(b) for b in batches), return_exceptions=True):
        if isinstance(result, BaseException):
            key = "token_rate_limited" if is_rate_limited(result) else "token_errors"
            stats[key] = stats.get(key, 0) + 1
            continue
        batch, markets = result
        if markets is None:
            continue
        stats["token_requests"] = stats.get("token_requests", 0) + 1
        by_condition = {m.condition_id: token0_of(m) for m in markets if m.condition_id}
        for cond in batch:
            found[cond] = by_condition.get(cond)
    store_tokens(found, now=time.time())
    stats["tokens_resolved"] = stats.get("tokens_resolved", 0) + sum(
        1 for t in found.values() if t
    )
    stats["tokens_missed"] = stats.get("tokens_missed", 0) + sum(
        1 for t in found.values() if not t
    )


# ── one pass ──────────────────────────────────────────────────────────────────


def _leg_conditions(unit: Unit) -> list[str]:
    seen: dict[str, None] = {}
    for legs in unit.legs.values():
        for _oid, ext in legs:
            cond = leg_condition(ext)
            if cond is not None:
                seen.setdefault(cond, None)
    return list(seen)


def fallback_units(units: list[Unit], priced: set[str]) -> list[Unit]:
    """Each unit cut down to the legs whose condition the CLOB did not price."""
    out = []
    for unit in units:
        legs = {}
        for market_id, market_legs in unit.legs.items():
            rest = [(oid, ext) for oid, ext in market_legs if leg_condition(ext) not in priced]
            if rest:
                legs[market_id] = rest
        if legs:
            out.append(Unit(unit.key, legs))
    return out


async def clob_pass(session, service, units: list[Unit], *, deadline: float, offset: float, stats: dict) -> list[Unit]:
    """Price every leg the CLOB has a usable book for; return the rest.

    The returned units hold exactly the legs to read from Gamma: a token
    unknown or missed, a refused book, a token the CLOB did not answer, or a
    unit this pass did not reach (budget, deadline, 429, error) — those keep
    their last price until a pass reaches them, the same as the first build.
    """
    now = time.time()
    conditions = list(dict.fromkeys(c for u in units for c in _leg_conditions(u)))
    known = cached_tokens(conditions, now=now)
    unknown = [c for c in conditions if c not in known]
    stats["clob_conditions"] = len(conditions)
    stats["clob_tokens_unknown"] = len(unknown)
    if unknown:
        await resolve_tokens(service, unknown, deadline=deadline, stats=stats)
        known = cached_tokens(conditions, now=time.time())
    token_of = {c: t for c, t in known.items() if t}
    priced: set[str] = set()

    if backoff_remaining(CLOB_BACKOFF_VENUE) > 0:
        stats["clob_stopped"] = "backoff"
        return fallback_units(units, priced)

    def tokens_of(unit: Unit) -> list[str]:
        return list(dict.fromkeys(
            token_of[c] for c in _leg_conditions(unit) if c in token_of
        ))

    ordered = rotate(units, read_cursor("polymarket_clob"))
    # A unit too big for the whole budget falls back to Gamma like any unread unit.
    groups = pack_requests(
        ordered, tokens_of, CLOB_TOKENS_PER_REQUEST, CLOB_REQUESTS_PER_PASS,
        stats, oversize_key="clob_units_oversize",
    )
    gate = asyncio.Semaphore(CLOB_CONCURRENCY)

    async def read(chunks):
        """One group's reads → (tops, fetched_at); fetched_at is the first send."""
        tops: dict = {}
        fetched_at = None
        for chunk in chunks:
            async with gate:
                left = deadline - time.monotonic()
                if left < _MIN_REQUEST_S:
                    raise _OutOfTime(started=fetched_at is not None)
                sent = datetime.fromtimestamp(time.time() - offset, timezone.utc)
                fetched_at = fetched_at or sent
                wall = min(REQUEST_TIMEOUT_S, left)
                try:
                    tops.update(
                        await asyncio.wait_for(service.get_book_tops(chunk), timeout=wall)
                    )
                except asyncio.TimeoutError:
                    if wall < REQUEST_TIMEOUT_S:
                        raise _OutOfTime(started=True) from None
                    raise
                stats["clob_requests"] = stats.get("clob_requests", 0) + 1
        return tops, fetched_at

    last_key = None
    stop = None
    for start in range(0, len(groups), CLOB_CONCURRENCY):
        window = groups[start : start + CLOB_CONCURRENCY]
        if deadline - time.monotonic() < _MIN_REQUEST_S:
            stop = "budget"
            break
        results = await asyncio.gather(*(read(c) for _u, c in window), return_exceptions=True)
        for gi, ((group_units, chunks), result) in enumerate(zip(window, results), start):
            if isinstance(result, BaseException):
                if stop is None:
                    stop = _stop_reason(result, stats, first=gi == 0)
                    if stop in ("timeout", "fetch_error"):
                        # The same rule as the Gamma rotation (lane1 R2/R5 on
                        # #11789): a group that failed with all the time it
                        # could have is passed, so it costs one read per
                        # rotation and never stops the rotation there.
                        stats["clob_groups_failed"] = stats.get("clob_groups_failed", 0) + 1
                        last_key = group_units[-1].key
                continue
            if stop:
                # Groups are written in order so the cursor names a contiguous
                # prefix; a later group's read after a stop is discarded.
                continue
            tops, fetched_at = result
            found = _price_group(group_units, token_of, tops, priced, stats)
            await _write_group(session, "polymarket", group_units, found, fetched_at, stats)
            last_key = group_units[-1].key
            stats["clob_units_done"] = stats.get("clob_units_done", 0) + len(group_units)
        if stop:
            break
    stats["clob_stopped"] = stop or "done"
    write_cursor("polymarket_clob", last_key)
    if stop != "rate_limited":
        clear_backoff(CLOB_BACKOFF_VENUE)
    stats["clob_legs_priced"] = sum(
        1 for u in units for legs in u.legs.values() for _o, ext in legs
        if leg_condition(ext) in priced
    )
    return fallback_units(units, priced)


class _OutOfTime(Exception):
    """The pass's clock, not the CLOB: no time left to start a read, or a read
    cut short under a wall below ``REQUEST_TIMEOUT_S``. ``started``: the group
    had already sent a read."""

    def __init__(self, *, started: bool):
        super().__init__("pass budget")
        self.started = started


def _stop_reason(exc: BaseException, stats: dict, *, first: bool = False) -> str:
    if isinstance(exc, _OutOfTime):
        # The pass's first group had all the time the pass could give it: a
        # clipped read there is its own timeout, or that group wedges the
        # rotation whenever the pass budget is under one full wall.
        return "timeout" if first and exc.started else "budget"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if is_rate_limited(exc):
        stats["clob_backoff_started_s"] = start_backoff(CLOB_BACKOFF_VENUE)
        return "rate_limited"
    stats["errors"].append(f"clob: {str(exc)[:200]}")
    return "fetch_error"


def _price_group(group_units, token_of, tops, priced: set, stats: dict) -> dict:
    """``{unit key: [items]}`` for the conditions with a usable book; marks them priced."""
    found: dict[str, list[dict]] = {}
    for unit in group_units:
        items = []
        for cond in _leg_conditions(unit):
            token = token_of.get(cond)
            if token is None:
                continue
            top = tops.get(token)
            if top is None:
                stats["clob_tokens_absent"] = stats.get("clob_tokens_absent", 0) + 1
                continue
            verdict, prob = socket_book_price(*top)
            if verdict != "price":
                key = f"clob_refused_{verdict}"
                stats[key] = stats.get(key, 0) + 1
                continue
            items.append(clob_item(cond, top[0], top[1], prob))
            priced.add(cond)
        if items:
            found[unit.key] = items
    return found
