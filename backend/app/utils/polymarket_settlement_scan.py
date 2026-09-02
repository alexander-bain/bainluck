"""Which Polymarket rows are finished, and which Gamma event answers for them.

Two pure pieces, both extracted because the resolved-status sync (#2637) needs
exactly what the price-refresh path already needed, and a second copy of either
is how settlement truth drifts:

``GAMMA_EVENT_ID_EXPR``
    The one expression that maps a ``futures_markets`` row to the Gamma **event**
    id that can be addressed for it. Polymarket rows arrive from two ingest
    branches under two keying conventions and this reconciles them; see the
    constant's own note.

``settled_legs``
    The venue's own statement about which legs of an event are over, read off a
    raw Gamma event payload.

WHY THIS MODULE EXISTS (#2637). ``_sync_polymarket_resolved_status`` used to page
``/events?closed=true`` by offset. Gamma caps ``offset`` at 2000 and, with no
``order``, serves oldest-first — so every run re-read the same ~2,000 events from
2021 and nothing newer could ever be marked resolved. 32,090 finished markets
across 22,092 events were still carried as ``open``, some since 2020.

The replacement addresses events **by id from our own rows**, so the population is
bounded by our database rather than by Gamma's ordering and no crypto flood can
crowd it out. That inverts one thing which this module exists to get right: a
paged ``closed=true`` scan could take every condition id it saw, because the
filter had already vouched for them. A direct-addressed fetch has no such filter
and returns live markets alongside settled ones, so **the closed test has to move
onto each leg**. Measured against live Gamma 2026-09-02 on a 460-event sample of
the stuck population:

* 162 events were closed; **0 of their 1,255 markets** were unclosed. So
  "event closed ⇒ every leg closed" holds, and a per-leg rule loses nothing on
  the population the old scan could see.
* 297 events were still open — and 8 of them carried **closed legs anyway**
  (event ``92611``, "Which states will Donald Trump visit in 2026?": 24 of 50
  legs ``closed`` + ``umaResolutionStatus: resolved``, quoting a terminal
  ``["1", "0"]``, while the other 26 quote live mid prices like
  ``["0.535", "0.465"]``). The old scan could not see those legs at all, and an
  event-level rule would either miss all 24 or resolve all 26 live ones.

So the rule is per-leg venue truth, and only that. It is never staleness: the
same sample's still-open set is "Illinois Senate Election Winner" (ends
2026-11-03), "Liga MX: 2026-27 Largest Goal Differential" (ends 2027-06-13),
"Negative GDP growth in 2026?" — long-horizon futures whose ``commence_time`` is
legitimately far in the past. 407 of the sample's 779 stuck rows are that class.
Anything keyed on age resolves them all, wrongly, and manufactures exactly the
resolved-but-never-graded cohort #2637 warns about.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Maps a ``futures_markets`` row to its Gamma **event** id. Not an alias and not
#: source-guarded — callers add both — so the one definition can serve a SELECT
#: list and a GROUP BY without being retyped.
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
#: ``/events?id=0x...`` does not resolve a condition id, so without this the whole
#: sub-market convention is unreachable by any id-addressed path.
#:
#: It covers the population completely: measured on production 2026-09-02, all
#: 40,004 unresolved Polymarket rows yield an id under it (22,092 distinct), and
#: all 22,092 are numeric — so ``::bigint`` ordering over the result is safe.
GAMMA_EVENT_ID_EXPR = """COALESCE(
                 NULLIF(fm.market_metadata->>'polymarket_event_id', ''),
                 NULLIF(substring(fm.group_id FROM '^polymarket:(.+)$'), ''),
                 CASE WHEN fm.external_id ~ '^[0-9]+$' THEN fm.external_id END
             )"""

#: Ids per Gamma ``/events?id=..&id=..`` request. **Measured 2026-09-02, and both
#: halves bite:** 101 ids → HTTP 422 ``expected array length <= 100``, and a
#: request for 100 ids with no explicit ``limit`` returns **20** events, silently
#: — Gamma's default page size truncates the batch and the missing 80 are
#: indistinguishable from ids it does not know (gotcha #53). Callers must send
#: ``limit`` alongside the ids; :meth:`PolymarketAPIService.get_events_by_ids`
#: does.
GAMMA_MAX_IDS_PER_REQUEST = 100

#: A leg quoting at or beyond this is a settled winner; ``1 - x`` and below is a
#: settled loser. Same envelope the winner writes already used — the split is by
#: the same test rather than a second invented one, so a leg can never be
#: resolved down one branch and graded down the other.
TERMINAL_PRICE_EPSILON = 0.05


@dataclass(frozen=True)
class SettledLegs:
    """The venue's statement about one event, reduced to what a writer needs."""

    #: Gamma's event id, as a string.
    event_id: str
    #: The event's own ``closed`` flag. Recorded, never the resolution key —
    #: see the module docstring for the 8-of-297 case it would miss.
    event_closed: bool
    #: Condition ids of legs Gamma reports ``closed``. These, and only these,
    #: may be marked resolved.
    settled_condition_ids: tuple[str, ...]
    #: Condition ids of legs still trading. Carried so a caller can say how much
    #: of an event it deliberately left alone, rather than inferring it.
    open_condition_ids: tuple[str, ...]
    #: ``condition_id -> (yes_price, no_price)`` for settled legs whose
    #: ``outcomePrices`` parsed. A settled leg may be absent here: closed is not
    #: the same as gradable, and the caller must keep the two apart.
    settlement_prices: dict[str, tuple[float, float | None]]

    @property
    def terminal_condition_ids(self) -> tuple[str, ...]:
        """Settled legs whose price proves a winner, in input order.

        The rest are closed with no readable result — resolvable, but with no
        grade to write. ``resolved_write_gate`` stamps those differently and the
        distinction must survive to it.
        """
        return tuple(
            cid
            for cid in self.settled_condition_ids
            if cid in self.settlement_prices
            and (
                self.settlement_prices[cid][0] >= 1.0 - TERMINAL_PRICE_EPSILON
                or self.settlement_prices[cid][0] <= TERMINAL_PRICE_EPSILON
            )
        )


def _parse_outcome_prices(raw_prices: object) -> tuple[float, float | None] | None:
    """``outcomePrices`` → ``(yes, no)``. ``None`` when it says nothing usable.

    Gamma sends a JSON-encoded string array (``'["1", "0"]'``); some payloads
    carry a real list. Anything else, or an unparseable pair, is absence — never
    an exception, because one malformed leg must not lose the other 99 events in
    the batch.
    """
    try:
        if isinstance(raw_prices, str):
            prices = json.loads(raw_prices)
        elif isinstance(raw_prices, list):
            prices = raw_prices
        else:
            return None
        if not prices:
            return None
        yes_price = float(prices[0])
        no_price = float(prices[1]) if len(prices) > 1 else None
        return yes_price, no_price
    except (json.JSONDecodeError, ValueError, IndexError, TypeError):
        return None


def settled_legs(raw_event: dict) -> SettledLegs | None:
    """Read one raw Gamma event payload into :class:`SettledLegs`.

    ``None`` when the payload carries no event id — there is nothing to key on,
    and a caller must not guess. An event with no markets is not ``None``: it is
    a real answer meaning "nothing of this event is settled", and collapsing the
    two would let a parse failure read as a settlement.

    ``closed is True`` is the test, deliberately, not truthiness — a missing key,
    ``None``, or the string ``"false"`` must all fail it. Resolution is a
    one-way write; it fails closed.
    """
    event_id = raw_event.get("id")
    if event_id is None or str(event_id) == "":
        return None

    settled: list[str] = []
    still_open: list[str] = []
    prices: dict[str, tuple[float, float | None]] = {}

    for market in raw_event.get("markets") or []:
        if not isinstance(market, dict):
            continue
        condition_id = market.get("conditionId")
        if not condition_id:
            continue
        if market.get("closed") is True:
            settled.append(condition_id)
            parsed = _parse_outcome_prices(market.get("outcomePrices", "[]"))
            if parsed is not None:
                prices[condition_id] = parsed
        else:
            still_open.append(condition_id)

    return SettledLegs(
        event_id=str(event_id),
        event_closed=raw_event.get("closed") is True,
        settled_condition_ids=tuple(settled),
        open_condition_ids=tuple(still_open),
        settlement_prices=prices,
    )


# --- the durable instrument --------------------------------------------------

#: How far past its start a Polymarket market must be before being carried
#: ``open`` is worth counting. 48h, from #2637's own verification clause.
STALE_OPEN_AGE_HOURS = 48

#: Where the sync leaves its last run summary for the needle endpoint to read.
#: The census can count the class but cannot tell open from finished; only the
#: sweep asked the venue, so only the sweep can say.
SYNC_SUMMARY_KEY = "bainluck:polymarket_resolved_sync:last"

#: Counts the class #2637 named, so it cannot hide again.
#:
#: The predicate is the issue's verbatim one — ``status='open'`` and a
#: ``commence_time`` more than 48h past — kept verbatim so the series stays
#: comparable to the 31,462 it was filed against (32,538 when this was built).
#:
#: **There is deliberately no "but these ones are fine" subtraction here, and
#: the first attempt at one is why.** Many of these rows are legitimately open
#: long-horizon futures, so the obvious refinement is to excuse the ones whose
#: ``resolution_date`` is still in the future. Measured 2026-09-02 on the 460
#: event sample: of the 371 stuck rows behind events **Gamma itself reports
#: closed** — finished, by the venue's own statement — **265 (71%) carry a
#: future ``resolution_date``**. The filter would have excused 71% of the actual
#: defect and called the remainder "the part with no innocent reading".
#:
#: ``resolution_date`` is a hint written at ingest, not a settlement fact. The
#: only thing that can tell an open market from a finished one is the venue, and
#: that answer costs an HTTP call — so it belongs to the sync, which already
#: makes it (``events_fully_open`` vs ``settled_legs_seen``), not to a SQL
#: census pretending to derive it. The census counts the class; the sync says
#: how much of it is real.
STALE_OPEN_CENSUS_SQL = f"""
    SELECT
        count(*) AS stale_open,
        count(DISTINCT {GAMMA_EVENT_ID_EXPR}) AS distinct_events,
        count(*) FILTER (WHERE {GAMMA_EVENT_ID_EXPR} IS NULL) AS unaddressable,
        min(fm.commence_time) AS oldest_commence
    FROM futures_markets fm
    WHERE fm.source = 'polymarket'
      AND fm.status = 'open'
      AND fm.commence_time < now() - make_interval(hours => :stale_hours)
"""


@dataclass(frozen=True)
class StaleOpenCensus:
    """The needle: finished-looking Polymarket markets still carried as open."""

    stale_open: int
    distinct_events: int
    #: Rows carrying no Gamma event id, so the id-addressed sweep cannot reach
    #: them at all. Measured 0 of 40,004 on 2026-09-02. A nonzero value is a
    #: DIFFERENT bug from a stubborn ``stale_open`` — an ingest one — and must
    #: not be read as the same thing.
    unaddressable: int = 0
    oldest_commence: object = None

    def needle_line(self, at: str) -> str:
        """The machine-readable line a lane report ends with (NEEDLE-SPEC)."""
        return (
            f"NEEDLE-AUX: polymarket-stale-open {self.stale_open} markets "
            f"across {self.distinct_events} events @ {at}"
        )
