"""#2199 — refresh prices for high-value open futures markets that the
discovery polls structurally cannot reach.

THE DEFECT THIS EXISTS FOR
--------------------------
Price capture for an *already-known* futures market was, until this module, a
side effect of a *discovery* scan. Both discovery scans are bounded, and both
orderings put already-known markets last:

* **Polymarket** (`_poll_polymarket_markets`). Gamma capped offset pagination at
  2000 in July 2026, so #219E flipped the scan to ``order=startDate&ascending=
  false`` — newest-listed first — to stop the *new*-market starvation. Measured
  2026-08-25: the deepest reachable page (offset 1900-1999) had an oldest
  ``startDate`` of **the same day**, and 73/100 events on page 0 were crypto
  up/down five-minute binaries the poll then discards. The entire reachable
  universe is roughly the last ten hours of listings. The 2026 Men's US Open
  Winner field has ``startDate = 2026-01-02`` — seven months deep in a tail the
  poll can never reach. #219E did not fix the starvation, it mirrored it:
  oldest-first starved new markets, newest-first starves old-but-live ones.
  Gotcha #41: a bounded sweep needs BOTH bounds.

* **Kalshi** (`_poll_kalshi_markets`). ``_partition_new_events_first`` defers
  every already-known event behind every new one, and the 480s processing
  deadline truncates the run long before the tail. The comment justifying that
  ordering says deferring existing rows is safe because "kalshi_ws + live poll
  keep them fresh anyway". That premise is false for futures:
  ``poll_live_prediction_markets`` is scoped to markets *linked to live events*
  and an outright championship field has no ``event_id``.

Measured blast radius (production, 2026-08-25): of the **907** tier-1 `open`
markets above a $10K volume floor with a future resolution date, **900** had
received no price snapshot in six hours. Not a tennis problem — the Super Bowl
LXI, 2028 presidential, MLB / NBA / UCL / Premier League championship and March
Madness fields were all dark.

WHAT THIS TASK IS, AND IS NOT
-----------------------------
It is a **price refresh**, and nothing else. It selects markets that already
exist in our DB, fetches those specific markets by id, and writes
``futures_outcomes`` price columns plus a ``futures_odds_snapshots`` row.

It deliberately does NOT create markets, create outcomes, categorise, re-tier,
group, or touch ``event_id``. Discovery stays the polls' job. This separation is
the actual fix: refresh coverage no longer depends on a discovery ordering, so
the two can never starve each other again.

TWO ARMS, BECAUSE THERE ARE TWO KINDS OF VALUABLE
--------------------------------------------------
The sweep selects on **value** (tier 1 above a volume floor) and, since
2026-08-27, also on **identity** (any market a committed tournament register
renders — :func:`app.utils.tournament_register.registered_market_ids`).

The second arm exists because the first one cannot express the US Open props
section. Measured 2026-08-27: every one of the three markets behind that
section was tier 5 — ``sinner-competes`` 215h stale, both ``*-second-major``
837h — and the eight curated Polymarket props were tier 2/5 with ``volume``
NULL. The predicate admitted **none of them, ever**. The page did exactly what
it was built to do (``propIsDark`` rotated the dark cards out) and rendered its
honest empty state, so the only symptom was an empty section and nothing
anywhere was red. A curated market's value is the curation; a volume floor
cannot see it.

The arms keep separate clocks and this is the second half of the same fix. The
class window and the *renderer's* ``LIVE_PRICE_STALE`` bound are both 6h, so the
sweep only became interested in a market once it had already breached the gate
the page renders through — it could not arrive before the dark window, only
after. Registered rows use :data:`REGISTERED_REFRESH_MINUTES` instead, which is
a sub-interval of the hourly beat, so they are re-priced hours before they could
go dark. Do not collapse the two constants back into one: that lockstep IS the
defect.

Registered rows are selected first, sorted to the head of each source loop, and
never truncated by ``budget`` — both loops stop on the wall clock, so head
position is what makes "curated rows cannot be starved by the class" a
guarantee rather than a tendency. The arm is bounded by what is committed on
disk (81 markets, 5 Kalshi + 76 Polymarket over 72 Gamma events, ≈9 extra HTTP
calls per beat), so no upstream can grow it.

STARVATION GUARDS (gotcha #41 — an ordering needs both bounds)
--------------------------------------------------------------
* **Value floor and liveness floor**, not a bare "oldest first": tier 1, volume
  at or above :data:`HIGH_VALUE_VOLUME_FLOOR`, plus every clause of
  ``app.utils.futures_liveness.LIVE_MARKET_SQL``. The registered arm drops the
  value floor and keeps the liveness bounds verbatim, so a curated row is not a
  licence to re-animate the stale-open population.

  **#2222 corrected what "liveness" means here, and the correction is load
  bearing.** This module used to say the resolution-date bound "is what keeps
  the dead out of the queue". It is not: ``status='open'`` survives settlement
  (gotcha #33) and ``resolution_date`` was measurably wrong by one to two years
  on every market in #2222's population, so nineteen settled markets — the
  Champions League and Premier League winner fields, Eurovision, eight
  elections — sat at the head of this queue permanently, were attempted every
  run, wrote zero, and held ``futures-price-freshness`` red for a month. The two
  bounds that actually see settlement (our own ``is_winner`` flag, and a venue
  positively saying the market is over) live in ``futures_liveness`` with the
  full reasoning, and the guard imports the same string.
* **Ordered by value, not by staleness.** Oldest-capture-first looks right and
  is a trap here: a market that can never be priced (a stale-settled book
  returning no bid, ask or trade) has a NULL last-capture forever, so it would
  hold the head of the queue permanently and starve everything behind it. Volume
  DESC has no such fixed point.
* **Per-market attempt markers** in Redis with a TTL equal to the staleness
  window, so one run cannot re-attempt what the previous run just tried and the
  tail rotates into view. An *attempt* is marked, not a success — otherwise the
  unpriceable market is back at the front on the very next run.

VERDICT
-------
Enrolled in :data:`app.utils.task_verdict.ENFORCED_TASKS` from birth, per #1884.
The failure this task must never report as green is precisely the one it was
built to end: a run that fetched markets, wrote no snapshots, and returned.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.utils.futures_liveness import (
    LIVE_MARKET_SQL,
    VENUE_SETTLED_KEY,
    VENUE_SETTLED_NOW_SQL,
)

logger = logging.getLogger(__name__)


class _VenueSettled:
    """Sentinel: the venue answered, and its answer is "this market is over".

    Distinct from ``None`` (the venue could not be asked, or does not know this
    id) and from ``[]`` (the venue has a book and every quote in it was refused
    by a price guard). All three used to arrive as an empty priced list and be
    counted as ``unpriceable`` — one word for three different facts, and the
    word implied the market was still live and merely awkward. #2222 lived in
    that conflation for a month.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "VENUE_SETTLED"


#: See :class:`_VenueSettled`. Compared by identity (``is``), never truthiness.
VENUE_SETTLED = _VenueSettled()

#: Only markets at or above this traded volume are refreshed. The floor is what
#: makes the sweep bounded; the guard in ``routes/admin_futures_freshness.py``
#: asserts the invariant over exactly this same set, so fix and guard cannot
#: disagree about what they cover.
HIGH_VALUE_VOLUME_FLOOR = 10_000

#: A high-value open market older than this is stale. Matches the 6h
#: ``LIVE_PRICE_STALE`` contract that ``utils/tournament_register.py`` already
#: enforces at the render boundary (UX-P130), so the producer and the renderer
#: use one definition of stale rather than two.
STALE_AFTER_HOURS = 6

#: How stale a REGISTERED market may get before the sweep re-prices it.
#:
#: The class window above and the renderer's own bound are both 6h, and that
#: lockstep is a defect for a curated page: the sweep only becomes interested in
#: a market once it has *already* breached the gate the page renders through, so
#: the beat is always one cycle behind the thing it exists to prevent. A
#: registered market should be re-priced hours before it could go dark, not an
#: hour after it did.
#:
#: **45 minutes, not 60, and the 15 is the whole point.** The beat is hourly at
#: ``:50`` and the window is evaluated against ``NOW()`` at the moment the run
#: reaches the query — a few seconds *later* each hour than the capture it is
#: testing. At exactly 60 the previous run's own snapshot is still inside the
#: window (``21:50:10`` is newer than ``NOW() - 1h`` when now is ``22:50:05``),
#: so the market fails the staleness test, is skipped, and refreshes every
#: *other* hour. The same margin keeps the attempt marker from outliving its
#: next beat. Any sub-interval value works; this one leaves 15 minutes of slack
#: for a late or slow run.
#:
#: It is deliberately NOT ``STALE_AFTER_HOURS``: that constant is the *renderer's*
#: definition of stale and the freshness guard reads it. This is a *producer*
#: interval. Collapsing the two back into one constant is what created the
#: lockstep.
REGISTERED_REFRESH_MINUTES = 45

#: Markets refreshed per run. 900 was the whole standing backlog when this
#: shipped; the budget exists so a bad day cannot turn one run into a wall-clock
#: overrun, not because the full set is unaffordable.
DEFAULT_MARKET_BUDGET = 500

#: Polymarket ids per Gamma ``/events?id=..&id=..`` request. Verified against the
#: live API 2026-08-25: repeated ``id`` params return the full nested markets
#: payload for each event.
POLYMARKET_ID_BATCH = 20

#: Wall budget, well under the task's 540s soft limit. Bounds the LOOP; each
#: individual HTTP call is separately bounded by the service clients' timeouts.
_TIME_BUDGET_S = 420.0

_ATTEMPT_KEY_PREFIX = "bainluck:futures_price_refresh:attempted:"


def _attempt_key(market_id: int) -> str:
    return f"{_ATTEMPT_KEY_PREFIX}{market_id}"


# --- selection ---------------------------------------------------------------

#: ``NOT EXISTS`` with a time bound rather than ``MAX(captured_at)``: the
#: aggregate form timed out at 10s in production over the 179M-row snapshot
#: table, because it must read every snapshot for every candidate. The EXISTS
#: form rides ``idx_fos_outcome_captured`` (outcome_id, captured_at) and stops at
#: the first row inside the window.
#: The Gamma **event** id, which is not always ``external_id``.
#:
#: Polymarket rows arrive from two ingest branches with two keying conventions,
#: and this expression is the only place that difference is reconciled:
#:
#: * negRisk **field** rows (one market, many outcomes — the US Open winner
#:   fields) carry the event id directly in ``external_id`` (``'139236'``).
#: * decomposed **sub-market** rows (one market per question — every curated
#:   prop) carry a ``0x`` *condition* id there instead; their event id lives in
#:   ``market_metadata->>'polymarket_event_id'`` and in ``group_id``.
#:
#: ``/events?id=0x...`` does not resolve a condition id, so before this the whole
#: sub-market convention was unreachable by the refresh path even when selected.
_POLY_EVENT_ID_SQL = """
        CASE WHEN fm.source = 'polymarket' THEN COALESCE(
                 NULLIF(fm.market_metadata->>'polymarket_event_id', ''),
                 NULLIF(substring(fm.group_id FROM '^polymarket:(.+)$'), ''),
                 CASE WHEN fm.external_id ~ '^[0-9]+$' THEN fm.external_id END
             ) END AS poly_event_id
"""

_CANDIDATE_SQL = text(
    f"""
    SELECT fm.id, fm.source, fm.external_id, fm.volume,
           {_POLY_EVENT_ID_SQL},
           fm.market_metadata->>'{VENUE_SETTLED_KEY}' AS venue_settled_since
      FROM futures_markets fm
     WHERE {LIVE_MARKET_SQL}
       AND fm.market_tier = 1
       AND fm.volume >= :volume_floor
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :stale_hours)
           )
     ORDER BY fm.volume DESC
     LIMIT :scan_limit
    """
)

#: Registered markets, selected by identity instead of by value.
#:
#: No tier bound and no volume floor — that is the entire point, and both
#: omissions are load-bearing rather than lax. The liveness bounds are kept
#: verbatim from the class query: ``status='open'`` plus a future resolution date
#: (gotcha #33 — a settled Kalshi market keeps ``status='open'``, so the date is
#: what actually keeps the dead out of the queue), so this arm cannot re-animate
#: the stale-open population the US Open slate census fenced off.
#:
#: The set is bounded by what is committed on disk, not by anything a market can
#: do to itself, so no upstream can grow it.
_REGISTERED_CANDIDATE_SQL = text(
    f"""
    SELECT fm.id, fm.source, fm.external_id, fm.volume,
           {_POLY_EVENT_ID_SQL},
           fm.market_metadata->>'{VENUE_SETTLED_KEY}' AS venue_settled_since
      FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND {LIVE_MARKET_SQL}
       AND NOT EXISTS (
             SELECT 1
               FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(mins => :stale_minutes)
           )
     ORDER BY fm.id
    """
)


def _rows_to_markets(rows, *, registered: bool) -> list[dict]:
    return [
        {
            "id": mid,
            "source": source,
            "external_id": external_id,
            "volume": volume,
            "poly_event_id": poly_event_id,
            # Carried so a successful write knows whether there is a stamp to
            # clear, and can skip the UPDATE for the ~900 markets that never had
            # one. Selected, not re-queried.
            "venue_settled_since": venue_settled_since,
            "registered": registered,
        }
        for (
            mid,
            source,
            external_id,
            volume,
            poly_event_id,
            venue_settled_since,
        ) in rows
    ]


# --- the venue-settled stamp --------------------------------------------------

#: FIRST observation only. Without ``IS NULL`` every run would push the stamp
#: forward and the confirmation window could never elapse — the market would be
#: retried forever, which is precisely the state #2222 describes.
_STAMP_VENUE_SETTLED_SQL = text(
    f"""
    UPDATE futures_markets
       SET market_metadata = COALESCE(market_metadata, '{{}}'::jsonb)
             || jsonb_build_object('{VENUE_SETTLED_KEY}', {VENUE_SETTLED_NOW_SQL})
     WHERE id = :mid
       AND market_metadata->>'{VENUE_SETTLED_KEY}' IS NULL
    """
)

#: A price arrived, so whatever the venue said before is no longer true. Clearing
#: is what makes the bound reversible without anyone intervening, and it is why a
#: transient upstream outage costs a market nothing.
_CLEAR_VENUE_SETTLED_SQL = text(
    f"""
    UPDATE futures_markets
       SET market_metadata = market_metadata - '{VENUE_SETTLED_KEY}'
     WHERE id = :mid
       AND market_metadata->>'{VENUE_SETTLED_KEY}' IS NOT NULL
    """
)


async def _stamp_venue_settled(session, market_id: int) -> None:
    """Record that a source said this market is over. Core UPDATE, gotcha #4."""
    await session.execute(_STAMP_VENUE_SETTLED_SQL, {"mid": market_id})


async def _clear_venue_settled(session, market_id: int) -> None:
    await session.execute(_CLEAR_VENUE_SETTLED_SQL, {"mid": market_id})


async def _clear_if_stamped(session, market: dict, stats: dict) -> None:
    """A price landed, so retract any standing venue-settled claim.

    Guarded on the value the selector already read, so the ~900 markets that
    never carried a stamp cost no extra statement. Failure to clear must never
    lose the price that was just committed: the write is already durable at this
    point, and a stamp that survives one run is retracted by the next.
    """
    if not market.get("venue_settled_since"):
        return
    try:
        await _clear_venue_settled(session, market["id"])
        await session.commit()
        stats["venue_settled_cleared"] += 1
    except Exception as exc:
        await session.rollback()
        stats["errors"].append(f"clear venue-settled {market['external_id']}: {exc}")


async def _scan_candidates(
    session, *, volume_floor: int, stale_hours: int, scan_limit: int
) -> list[dict]:
    """Stale high-value markets, most valuable first.

    Scans wider than one run's budget on purpose: the caller then drops markets
    already attempted inside the staleness window, and without the headroom a run
    whose top-N were all just attempted would do nothing while the tail stayed
    dark.
    """
    rows = (
        await session.execute(
            _CANDIDATE_SQL,
            {
                "volume_floor": volume_floor,
                "stale_hours": stale_hours,
                "scan_limit": scan_limit,
            },
        )
    ).fetchall()
    return _rows_to_markets(rows, registered=False)


async def _scan_registered_candidates(
    session, *, market_ids: list[int], stale_minutes: int
) -> list[dict]:
    """Stale markets a committed tournament register renders, at any tier or volume."""
    if not market_ids:
        return []
    rows = (
        await session.execute(
            _REGISTERED_CANDIDATE_SQL,
            {"market_ids": market_ids, "stale_minutes": stale_minutes},
        )
    ).fetchall()
    return _rows_to_markets(rows, registered=True)


def _load_attempt_skips(market_ids: list[int]) -> set[int]:
    """Market ids attempted inside the current staleness window.

    Best-effort. Gotcha #39: only ever through ``get_redis_client()``, which is
    socket-timeout bounded — an unbounded sync client here would freeze the
    async task. A Redis outage degrades this to "no rotation", which is strictly
    better than not running.
    """
    if not market_ids:
        return set()
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        values = rc.mget([_attempt_key(mid) for mid in market_ids])
    except Exception:
        return set()
    return {mid for mid, val in zip(market_ids, values) if val}


def _mark_attempted(market_ids: list[int], ttl_seconds: int) -> None:
    """Record an ATTEMPT, not a success.

    A market whose book cannot be priced would otherwise return to the head of
    the queue on every single run and starve the tail behind it — the same
    fixed-point failure the volume ordering above avoids.
    """
    if not market_ids:
        return
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        pipe = rc.pipeline()
        for mid in market_ids:
            pipe.setex(_attempt_key(mid), ttl_seconds, "1")
        pipe.execute()
    except Exception:
        pass


# --- writing -----------------------------------------------------------------


async def _write_prices(
    session,
    market_id: int,
    bookmaker: str,
    priced: list[dict],
    stats: dict,
) -> int:
    """Write price columns + one snapshot per outcome. Returns snapshots written.

    ``priced`` items: ``external_id``, ``probability``, ``yes_bid``, ``yes_ask``,
    ``last_price``, and optionally a ``no`` sub-dict of the same shape.

    TWO OUTCOME-ID CONVENTIONS, ONE WRITER. ``external_id`` on a priced item is
    the provider's own market key (a Kalshi ticker, a Polymarket condition id).
    How that key appears in ``futures_outcomes`` depends on which ingest branch
    minted the row:

    * **bare** — Kalshi tickers, and the outcomes of a Polymarket negRisk field
      (``0x…``, one outcome per contender).
    * **suffixed** — the legs of a decomposed Polymarket binary, written
      ``{condition_id}_yes`` / ``{condition_id}_no`` by the sub-market branch of
      ``tasks/polymarket.py``.

    Matching only the bare form is why every curated prop counted as
    ``unknown_outcomes``: the price arrived, found no row named after it, and was
    discarded — a refusal that looked exactly like "we do not hold this market".
    A market row carries one convention or the other, never both, so resolving
    bare-then-suffixed cannot double-write.

    Three refusals, each load-bearing:

    * **Never creates an outcome.** An id we do not already hold is discovery's
      job; creating one here would let a price-only path mint identity with no
      categorisation, tier or grouping. Counted as ``unknown_outcomes`` so the
      refusal is visible rather than silent.
    * **Never touches a settled outcome** (``is_winner`` TRUE). Gotcha #21: a
      settled book stops quoting, and re-pricing it can only corrupt resolved
      state.

      The predicate is ``IS NOT TRUE``, not ``IS NULL``, and the difference is
      the whole of #2199's first live failure. ``FuturesOutcome.is_winner`` is
      declared non-nullable with ``default=False`` (models.py), so **no
      production row is ever NULL** — unsettled is stored as ``FALSE``. Measured
      across every eligible tier-1 open market at the time: 0 NULL, 10,762
      FALSE, 42 TRUE. ``IS NULL`` therefore matched nothing, every priced item
      fell through to ``unknown_outcomes``, and the task wrote zero snapshots by
      construction and permanently. ``IS NOT TRUE`` keeps the settled refusal
      against the tri-state that actually exists.
    * **Never writes a NULL probability.** Gotcha #19 / the Kalshi spread guard:
      "no price" is refused upstream, and a refusal must not arrive here as a
      write.
    """
    from app.models.models import FuturesOddsSnapshot, FuturesOutcome
    from app.utils.odds_math import probability_to_american
    from app.utils.price_change_stamp import price_changed_at_value
    from sqlalchemy import func, update as sa_update

    if not priced:
        return 0

    existing = {
        row[1]: row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT id, external_id FROM futures_outcomes "
                    "WHERE market_id = :mid AND is_winner IS NOT TRUE"
                ),
                {"mid": market_id},
            )
        ).fetchall()
    }

    def _legs(item: dict) -> list[tuple[int, dict]]:
        """``(outcome_id, side)`` pairs, in whichever convention this market holds."""
        key = item["external_id"]
        bare = existing.get(key)
        if bare is not None:
            return [(bare, item)]
        legs: list[tuple[int, dict]] = []
        yes_id = existing.get(f"{key}_yes")
        if yes_id is not None:
            legs.append((yes_id, item))
        no_id = existing.get(f"{key}_no")
        no_side = item.get("no")
        if no_id is not None and no_side:
            legs.append((no_id, no_side))
        return legs

    now = datetime.now(timezone.utc)
    written = 0
    for item in priced:
        prob = item.get("probability")
        if prob is None or not (0 < prob < 1):
            continue

        legs = _legs(item)
        if not legs:
            stats["unknown_outcomes"] += 1
            continue

        for outcome_id, side in legs:
            side_prob = side.get("probability")
            if side_prob is None or not (0 < side_prob < 1):
                continue
            american = probability_to_american(side_prob)
            await session.execute(
                sa_update(FuturesOutcome)
                .where(FuturesOutcome.id == outcome_id)
                .values(
                    current_probability=side_prob,
                    current_american_odds=american,
                    current_yes_bid=side.get("yes_bid"),
                    current_yes_ask=side.get("yes_ask"),
                    last_updated=func.now(),
                    # #2024: `last_updated` records that a poll RAN; this records
                    # that the price MOVED. Both matter and they are not the same.
                    price_changed_at=price_changed_at_value(
                        FuturesOutcome.current_probability,
                        FuturesOutcome.price_changed_at,
                        side_prob,
                    ),
                )
            )
            await session.execute(
                pg_insert(FuturesOddsSnapshot).values(
                    outcome_id=outcome_id,
                    bookmaker=bookmaker,
                    probability=side_prob,
                    american_odds=american,
                    yes_bid=side.get("yes_bid"),
                    yes_ask=side.get("yes_ask"),
                    last_price=side.get("last_price"),
                    captured_at=now,
                )
            )
            written += 1

    return written


# --- source adapters ---------------------------------------------------------


async def _fetch_kalshi_prices(service, external_id: str):
    """Prices for one Kalshi event ticker.

    Three returns, because there are three different facts (see
    :class:`_VenueSettled`):

    * ``None`` — the event could not be read at all (404, or a parse failure).
    * :data:`VENUE_SETTLED` — the event reads fine and **carries no markets**.
      Kalshi keeps event rows forever and purges market rows (gotcha #35), so an
      event with an empty book is a settled contest whose book has aged out, and
      no number will ever come back from it. Measured 2026-08-30 on all eighteen
      Kalshi rows in #2222's population: HTTP 200, zero markets, unanimous.
      The control that makes that reading mean something is ``KXSB-27`` (live,
      73M volume, same unauthenticated call): **32** markets.
    * a list — the venue has a book; the list holds whatever survived the price
      guards, and may be empty if every quote was refused.

    The emptiness is read off the RAW payload, not off ``event.markets``.
    ``_parse_market`` drops a market it cannot parse, so a parsed-empty list is
    ambiguous between "no book" and "we failed to read the book" — and calling a
    parse failure a settlement is how a live market gets retired quietly.

    Two deliberate reuses rather than reimplementations:

    * ``service._parse_event`` for the payload. Kalshi v2 quotes prices in TWO
      formats — ``yes_bid_dollars`` as a decimal string, or legacy ``yes_bid`` as
      integer cents — and ``_parse_market`` already resolves the pair. Reading
      the raw dict here would mean re-deriving that, and a ``95`` arriving where
      ``0.95`` is expected is a coherent-looking wrong price, the worst kind.
    * ``_kalshi_yes_probability`` for the price itself — the same spread /
      one-sided-book guard the main poll applies, so this path cannot fabricate a
      price the poll would have refused.
    """
    from app.tasks.kalshi import _kalshi_yes_probability

    raw = await service.get_event(external_id, with_nested_markets=True)
    if not raw:
        return None
    if not (raw.get("markets") or []):
        return VENUE_SETTLED
    event = service._parse_event(raw)
    if not event:
        return None

    priced: list[dict] = []
    for market in event.markets:
        if not market.ticker:
            continue
        prob = _kalshi_yes_probability(
            market.yes_bid, market.yes_ask, market.last_price
        )
        if prob is None:
            continue
        priced.append(
            {
                "external_id": market.ticker,
                "probability": prob,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
                "last_price": market.last_price,
            }
        )
    return priced


async def _fetch_polymarket_prices(service, event_ids: list[str]) -> dict:
    """Prices for a batch of Polymarket event ids, keyed by event id.

    A value is either a list of priced items or :data:`VENUE_SETTLED`.

    THE SETTLED CHECK RUNS BEFORE THE COHERENCE GUARD, and the order is the
    point. #2222's Polymarket row (``86515``, the Alpha Arena field) is closed
    and resolved: Gamma still serves it, and every losing leg quotes
    ``lastTradePrice = 1`` on its own No token, so eight of nine legs resolve to
    ``1.0``. ``field_is_incoherent`` refuses the field — correctly, it is not a
    price — and the event lands in ``not_found``, forever, because a settled
    field can never become coherent again. Checked in this order the market is
    reported as what it is (over) instead of as what it looks like from inside
    the price rail (unreadable).

    Applies the same two field-level refusals as the ingest path:
    ``_resolve_market_probability`` (placeholder/evidence gate, gotcha #19) and
    ``field_is_incoherent`` (#1527 — a negRisk field with several near-certain
    legs is not a price at any leg, and capturing it poisons
    ``opening_probability`` permanently because opening is COALESCEd).
    """
    from app.tasks.polymarket import _resolve_market_probability, complementary_book
    from app.utils.winner_field_coherence import field_is_incoherent

    raw_events = await service.get_events_by_ids(event_ids)
    out: dict = {}
    for raw in raw_events:
        event = service._parse_event(raw)
        if not event or not event.markets:
            continue
        # The venue's own statement, taken before any price is looked at.
        # `event.markets` is known non-empty here, so `all()` cannot be
        # vacuously true — an empty parse must never read as a settlement.
        if event.closed or all(m.closed for m in event.markets):
            out[str(event.id)] = VENUE_SETTLED
            continue
        priced: list[dict] = []
        for market in event.markets:
            prob = _resolve_market_probability(market)
            if prob is None or prob <= 0:
                continue
            item = {
                "external_id": market.condition_id,
                "probability": prob,
                "yes_bid": market.best_bid,
                "yes_ask": market.best_ask,
                "last_price": market.last_trade_price,
            }

            # THE NO LEG. A decomposed binary stores two rows and the card is
            # only presented as live when BOTH are fresh, so refreshing Yes alone
            # leaves the prop exactly as dark as before — the write lands and the
            # user still sees nothing.
            #
            # It is the complement of the Yes price we ACCEPTED, never
            # ``outcome_prices[1]``, and the difference is not academic. Measured
            # against live Gamma 2026-08-27 on the four curated US Open prop
            # events: 92 priced markets, ``outcome_prices`` summed to exactly 1
            # in every single one — so whenever Yes came from ``outcome_prices``
            # the two rules agree exactly. They diverge only when Yes did NOT:
            # ``alcaraz-semifinals`` quoted ``[0.32, 0.68]`` over an untradeable
            # 0.11/0.53 book, so 0.32 was refused as a fabricated midpoint
            # (#1578) and Yes resolved to the 0.53 last trade. Writing 0.68
            # beside it would print a card whose two sides sum to 1.21 — and 0.68
            # is the complement of the very number we just refused.
            #
            # ``1 - accepted`` is coherent with what we publish by construction,
            # which is the same reasoning ``complementary_book`` applies to the
            # book: one binary CLOB addressed from the other token, an identity
            # rather than an estimate.
            no_bid, no_ask, no_last = complementary_book(
                market.best_bid, market.best_ask, market.last_trade_price
            )
            item["no"] = {
                "probability": 1.0 - prob,
                "yes_bid": no_bid,
                "yes_ask": no_ask,
                "last_price": no_last,
            }

            priced.append(item)
        if not priced:
            continue
        if field_is_incoherent(
            (p["probability"] for p in priced),
            mutually_exclusive=bool(event.neg_risk),
        ):
            logger.warning(
                "futures_price_refresh: polymarket event %s — incoherent negRisk "
                "field, refusing capture (#1527)",
                event.id,
            )
            continue
        out[str(event.id)] = priced
    return out


# --- entry point -------------------------------------------------------------


async def _refresh_stale_futures_prices(
    *,
    volume_floor: int = HIGH_VALUE_VOLUME_FLOOR,
    stale_hours: int = STALE_AFTER_HOURS,
    budget: int = DEFAULT_MARKET_BUDGET,
    registered_refresh_minutes: int = REGISTERED_REFRESH_MINUTES,
) -> dict:
    """Refresh prices for stale high-value open futures markets. See module docstring."""
    from app.tasks.base import get_task_session
    from app.utils.tournament_register import registered_market_ids

    started = time.monotonic()
    stats: dict = {
        "task": "futures_price_refresh",
        "candidates": 0,
        "markets_attempted": 0,
        "markets_priced": 0,
        "snapshots_written": 0,
        "unknown_outcomes": 0,
        "not_found": 0,
        "unpriceable": 0,
        # #2222. `venue_settled` is a source SAYING the market is over;
        # `venue_settled_cleared` is a market that came back and had its stamp
        # removed. Both are counted because the second is the evidence that the
        # first is reversible, and an irreversible retirement is the failure
        # mode this whole mechanism is engineered against.
        "venue_settled": 0,
        "venue_settled_cleared": 0,
        "errors": [],
        "by_source": {},
        "remaining_stale": None,
        "budget_hit": False,
        "registered_candidates": 0,
        "registered_attempted": 0,
        "registered_priced": 0,
    }

    async with get_task_session() as session:
        # Bound the longest single uninterrupted DB op rather than the loop
        # boundaries (gotcha: budget-guard-inner-op). A loop-boundary check
        # cannot interrupt a statement already blocked on a row lock held by the
        # live poller.
        await session.execute(text("SET statement_timeout = '60s'"))
        await session.execute(text("SET lock_timeout = '15s'"))

        # Registered first, and on a shorter clock. Two arms rather than one
        # loosened predicate: the class keeps its value floor (widening that
        # would pull the whole low-value tail into an hourly sweep and starve
        # exactly what it is meant to protect), while curated rows are selected
        # by identity because curation is their value floor.
        registered_scan = await _scan_registered_candidates(
            session,
            market_ids=sorted(registered_market_ids()),
            stale_minutes=registered_refresh_minutes,
        )
        class_scan = await _scan_candidates(
            session,
            volume_floor=volume_floor,
            stale_hours=stale_hours,
            scan_limit=max(budget * 3, budget + 50),
        )

        # A registered market that is ALSO tier-1 high-volume (every US Open
        # winner field is) appears in both. It must keep the registered
        # classification or it inherits the 6h attempt TTL and the shorter clock
        # is undone.
        registered_ids = {m["id"] for m in registered_scan}
        scan = registered_scan + [m for m in class_scan if m["id"] not in registered_ids]

        stats["candidates"] = len(scan)
        stats["registered_candidates"] = len(registered_scan)
        skip_ids = _load_attempt_skips([m["id"] for m in scan])
        selected = [m for m in scan if m["id"] not in skip_ids][:budget]

        if not selected:
            # Gotcha #53: an empty result is a response SHAPE, not an absence.
            # "Nothing stale" and "everything stale was just attempted" are
            # opposite states, so they get different terminals.
            stats["terminal"] = "complete" if not scan else "no_work"
            stats["reason"] = (
                "no stale high-value or registered markets"
                if not scan
                else "every stale market was attempted inside the current window"
            )
            stats["remaining_stale"] = len(scan)
            return stats

        # Registered ahead of the class WITHIN each source: both source loops are
        # truncated by the wall budget, so head position is what makes "curated
        # rows cannot be starved by the class" true rather than merely likely.
        selected.sort(key=lambda m: not m["registered"])
        kalshi_markets = [m for m in selected if m["source"] == "kalshi"]
        poly_markets = [m for m in selected if m["source"] == "polymarket"]
        attempted_ids: list[int] = []
        registered_attempted_ids: list[int] = []

        def _note_attempt(market: dict) -> None:
            stats["markets_attempted"] += 1
            if market["registered"]:
                stats["registered_attempted"] += 1
                registered_attempted_ids.append(market["id"])
            else:
                attempted_ids.append(market["id"])

        # --- Polymarket: batched by id, so the whole backlog costs ~25 calls ---
        if poly_markets:
            from app.services.polymarket_api import PolymarketAPIService

            poly_service = PolymarketAPIService()
            try:
                # MANY MARKETS PER EVENT, so this is a list and not a scalar.
                # A negRisk field is one market on one event, but the decomposed
                # binaries are one event per QUESTION GROUP — the eight curated
                # US Open props sit on four events, two of them sharing one.
                # Keying market-per-event would have silently dropped the second
                # prop of every pair.
                by_event: dict[str, list[dict]] = {}
                for market in poly_markets:
                    event_id = market.get("poly_event_id")
                    if not event_id:
                        # No resolvable Gamma event id: the row cannot be
                        # addressed, and saying so is the point (gotcha #53).
                        # Counted, marked attempted so it rotates, never retried
                        # into a 422 loop against `/events?id=0x…`.
                        _note_attempt(market)
                        stats["no_event_id"] = stats.get("no_event_id", 0) + 1
                        continue
                    by_event.setdefault(str(event_id), []).append(market)

                ids = list(by_event.keys())
                for i in range(0, len(ids), POLYMARKET_ID_BATCH):
                    if time.monotonic() - started > _TIME_BUDGET_S:
                        stats["budget_hit"] = True
                        break
                    chunk = ids[i : i + POLYMARKET_ID_BATCH]
                    try:
                        priced_by_event = await _fetch_polymarket_prices(
                            poly_service, chunk
                        )
                    except Exception as exc:  # one bad batch must not wipe the run
                        stats["errors"].append(f"polymarket batch {i}: {exc}")
                        continue
                    for event_id in chunk:
                        priced = priced_by_event.get(event_id)
                        for market in by_event[event_id]:
                            _note_attempt(market)
                            if priced is VENUE_SETTLED:
                                stats["venue_settled"] += 1
                                try:
                                    await _stamp_venue_settled(session, market["id"])
                                    await session.commit()
                                except Exception as exc:
                                    await session.rollback()
                                    stats["errors"].append(
                                        f"polymarket stamp {market['external_id']}: {exc}"
                                    )
                                continue
                            if priced is None:
                                stats["not_found"] += 1
                                continue
                            try:
                                written = await _write_prices(
                                    session, market["id"], "polymarket", priced, stats
                                )
                                await session.commit()
                            except Exception as exc:
                                await session.rollback()
                                stats["errors"].append(
                                    f"polymarket {market['external_id']}: {exc}"
                                )
                                continue
                            if written:
                                stats["markets_priced"] += 1
                                stats["snapshots_written"] += written
                                stats["by_source"]["polymarket"] = (
                                    stats["by_source"].get("polymarket", 0) + written
                                )
                                if market["registered"]:
                                    stats["registered_priced"] += 1
                                await _clear_if_stamped(session, market, stats)
                            else:
                                stats["unpriceable"] += 1
                    await asyncio.sleep(0.3)
            finally:
                await poly_service.close()

        # --- Kalshi: one call per event ticker; no batch endpoint exists ---
        if kalshi_markets:
            import os

            if not os.getenv("KALSHI_API_KEY"):
                stats["errors"].append("KALSHI_API_KEY not configured")
            else:
                from app.services.kalshi_api import KalshiAPIService

                kalshi_service = KalshiAPIService()
                for market in kalshi_markets:
                    if time.monotonic() - started > _TIME_BUDGET_S:
                        stats["budget_hit"] = True
                        break
                    _note_attempt(market)
                    try:
                        priced = await _fetch_kalshi_prices(
                            kalshi_service, market["external_id"]
                        )
                    except Exception as exc:
                        stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                        continue
                    if priced is VENUE_SETTLED:
                        stats["venue_settled"] += 1
                        try:
                            await _stamp_venue_settled(session, market["id"])
                            await session.commit()
                        except Exception as exc:
                            await session.rollback()
                            stats["errors"].append(
                                f"kalshi stamp {market['external_id']}: {exc}"
                            )
                        continue
                    if priced is None:
                        stats["not_found"] += 1
                        continue
                    try:
                        written = await _write_prices(
                            session, market["id"], "kalshi", priced, stats
                        )
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        stats["errors"].append(f"kalshi {market['external_id']}: {exc}")
                        continue
                    if written:
                        stats["markets_priced"] += 1
                        stats["snapshots_written"] += written
                        stats["by_source"]["kalshi"] = (
                            stats["by_source"].get("kalshi", 0) + written
                        )
                        if market["registered"]:
                            stats["registered_priced"] += 1
                        await _clear_if_stamped(session, market, stats)
                    else:
                        stats["unpriceable"] += 1
                    await asyncio.sleep(0.15)

        # Two TTLs, because there are two clocks. A registered market marked for
        # 6h would be unreachable for five hours after every refresh, which is
        # the lockstep this change exists to break — the shorter select window
        # would simply re-find it and the marker would veto it.
        _mark_attempted(attempted_ids, ttl_seconds=stale_hours * 3600)
        _mark_attempted(
            registered_attempted_ids,
            ttl_seconds=max(1, registered_refresh_minutes) * 60,
        )

        # Measure what is LEFT, so the run reports the invariant's state and not
        # just its own throughput. This is the number the guard reads.
        try:
            remaining = (
                await session.execute(
                    text(
                        f"""
                        SELECT COUNT(*) FROM futures_markets fm
                         WHERE {LIVE_MARKET_SQL}
                           AND fm.market_tier = 1
                           AND fm.volume >= :volume_floor
                           AND NOT EXISTS (
                                 SELECT 1 FROM futures_outcomes fo
                                   JOIN futures_odds_snapshots s
                                     ON s.outcome_id = fo.id
                                  WHERE fo.market_id = fm.id
                                    AND s.captured_at
                                        > NOW() - make_interval(hours => :stale_hours)
                               )
                        """
                    ),
                    {"volume_floor": volume_floor, "stale_hours": stale_hours},
                )
            ).scalar()
            stats["remaining_stale"] = int(remaining or 0)
        except Exception as exc:
            stats["errors"].append(f"remaining_stale census: {exc}")

    stats["elapsed_s"] = round(time.monotonic() - started, 1)
    stats["terminal"] = _terminal(stats)
    return stats


def _terminal(stats: dict) -> str:
    """The honest terminal. #1884: enrolled from birth, so this is the contract.

    A run that attempted markets and wrote nothing is ``failed``, not
    ``complete`` — that is the exact false-green this task exists to end
    (gotcha #53: "it returned" is not "it worked"). A budget- or error-truncated
    run that did write is ``partial``: real work banked, coverage not proven.
    """
    if stats["markets_attempted"] == 0:
        return "no_work"
    if stats["snapshots_written"] == 0:
        return "failed"
    if stats["budget_hit"] or stats["errors"]:
        return "partial"
    return "complete"
