"""Which Kalshi timestamp becomes ``resolution_date`` — measured, not assumed. Pure.

CAL-P989 (#2660, #1818, #2644). Kalshi publishes four timestamps per market and the
poller wrote the one that is a legal backstop::

    resolution_date = max(expiration_time)      # app/tasks/kalshi.py

``expiration_time`` is the LATEST POSSIBLE expiry. For a market that
``can_close_early`` — 99.7% of them (CAL-P061, ``kalshi_resolution_date_provenance``)
— it equals ``latest_expiration_time``, so taking ``max()`` across sub-markets makes
it a max of backstops. ``close_time`` is when trading ACTUALLY stopped.

MEASUREMENT (2026-09-02, live public Kalshi API, n=179 events sampled by
``md5(external_id)`` from the 10,187 Kalshi rows that are ``status='open'`` with a
future ``resolution_date`` — the exact population #1818's repair cannot see)::

    cohort                       n     close_time    expiration_time   expected_exp
                                       in the past   in the past       in the past
    ------------------------------------------------------------------------------
    settled at venue            49     39  (80%)      0   (0%)          34  (69%)
    still active               130      0   (0%)      0   (0%)           -

Read the ``expiration_time`` column: **0 of 49** markets that Kalshi has already
finalized have a stored date in the past, which is why ``status != 'resolved' AND
past resolution_date`` selects none of them and why ux-041 found 11/11 settled
markets resolving "in the future". Switching to ``close_time`` makes **39 of 49**
visible with **zero** still-active markets wrongly moved into the past.

WHY NOT ``expected_expiration_time``. It is the right field for the OTHER defect
(#2644: tier-1 championship futures printing 2029 — ``KXSB-27`` stores 2029-02-13
while the venue expects 2027-02-14) but it is a PREDICTION made before the event.
On the settled cohort it scores worse than ``close_time`` (34/49 vs 39/49) because
it is the date Kalshi *guessed*, not the date trading stopped. #2644 is a separate
ship with a separate hazard (13 markets where "expected" is LATER than what we
store, so a blanket preference moves those the wrong way); this module deliberately
does not touch it.

WHY NOT ``settlement_ts``. CAL-P061 named it "the truth", and it is — where it
exists. Measured on this population it is ``None`` on the finalized
``KXWTASETWINNER`` markets that motivated #2660, so a rail built on it would no-op
on the very rows it was written for. ``close_time`` is populated on 100% of them.

THE RESIDUAL, NAMED RATHER THAN ROUNDED AWAY. 10 of the 49 settled markets have a
``close_time`` that is still in the future — Kalshi finalized them EARLY, before
scheduled close. No date field can reach those; only venue ``status`` can, which is
``_backfill_from_settled_events``'s job (gotcha #33). This fix is 80% of the
cohort, not 100%, and must not be reported as the whole of #1818.

**AMENDMENT, CAL-P1019 / #2722.** That residual now has a second reader here:
:func:`derive_venue_settlement`. The same payload this module reads for dates
carries the venue's ``status`` per leg, and the sweep was discarding it — so a
market Kalshi had already finalised kept ``status='open'`` in our rows and went on
renting a dead last-trade price as a live probability (#2660's card). Reading it
costs no extra venue call and writes no grade. It does not retire
``_backfill_from_settled_events``, which enumerates settled events series by
series; it is the second, non-date-gated way in.

NO DATA LOSS. The backstop keeps its own column (``FuturesMarket.expiration_time``),
so every consumer that genuinely wants "the last date this could possibly resolve"
still has it, and the 421/421 provenance reproduction in CAL-P061 stays checkable.

BLAST RADIUS, STATED BECAUSE IT IS REAL. ``resolution_date`` moves EARLIER by a
median of 7.06 days on the settled cohort (p90 27.9, max 361.6). Consumers that do
retention arithmetic on it — ``app/tasks/kalshi_cliff.py`` against
``PROVABLY_PURGED_AGE_DAYS``/``AT_RISK_AGE_DAYS`` — will therefore see these markets
as OLDER than they did. That is a correction, not a regression: Kalshi's retention
clock runs from settlement, and the backstop date made every settled market look
younger than it was, so the at-risk warning fired late. It is still a behaviour
change and is guarded in ``tests/test_kalshi_resolution_window_989.py``.

Pure module: no DB, no network, no implicit clock. Every input is a parameter, so
no test here can be turned green or red by the wall clock (gotcha #44).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Protocol, Sequence


class _HasWindow(Protocol):
    """The two fields this derivation reads off a Kalshi sub-market."""

    close_time: Optional[datetime]
    expiration_time: Optional[datetime]


@dataclass(frozen=True)
class ResolutionWindow:
    """What the poller should store for one Kalshi event.

    ``resolution_date`` is the user-facing "when does this resolve" and the column
    every ``past resolution_date`` predicate reads. ``expiration_time`` is the
    venue's legal backstop, preserved so nothing that wanted it has to guess.
    """

    #: ``max(close_time)`` — when trading actually stops. Falls back to the
    #: backstop when the venue sent no ``close_time`` at all.
    resolution_date: Optional[datetime]

    #: ``max(expiration_time)`` — exactly what ``resolution_date`` used to hold.
    expiration_time: Optional[datetime]

    #: True when the fallback fired, i.e. this event carried no ``close_time`` on
    #: any sub-market and the value is still a backstop. Callers that want to
    #: count how much of the population the fix could not improve read this
    #: rather than re-deriving it by comparing the two dates (which cannot
    #: distinguish "fell back" from "close == expiration", 73% of active rows).
    used_expiration_fallback: bool


#: The venue statuses that mean "Kalshi says this market is over".
#:
#: CAL-P1019 / #2722 — THE RESIDUAL NAMED ABOVE, ANSWERED. The 10 of 49 settled
#: markets whose ``close_time`` is still in the future cannot be reached by any
#: date field, only by the venue's own ``status``. That status arrives on the
#: SAME payload this module already reads for dates
#: (``/events/{ticker}?with_nested_markets=true``) and was being discarded.
#:
#: MEASURED SHAPE, live public Kalshi API 2026-09-05 (``/events?status=settled``,
#: nested markets), e.g. ``KXG7LEADEROUT-45JAN01-MCAR``::
#:
#:     status "finalized", result "no",
#:     close_time 2026-07-20T14:22:46Z, expiration_time 2045-01-01T15:00:00Z
#:
#: WHY ONLY THESE TWO WORDS. ``settled`` and ``finalized`` are the venue's
#: terminal states — the market is over and Kalshi has said what happened.
#: ``closed`` is deliberately NOT here: it means trading stopped with the result
#: still pending, and our ``status='resolved'`` is the gate a dozen grading and
#: calibration queries read (``fm.status = 'resolved'`` appears 14 times in
#: ``backfill_winners.py`` alone), so admitting a pending market would open those
#: paths on a market with nothing to grade. ``determined`` is excluded for the
#: same reason: payouts are not final and the venue may still move it.
VENUE_SETTLED_STATUSES = frozenset({"settled", "finalized"})


@dataclass(frozen=True)
class VenueSettlement:
    """Whether the VENUE considers one event over. A status read, never a grade.

    This carries no winner, no result and no price on purpose. Moving a date and
    a grade in one pass is how #1852 happened, and #2722 restates the line for
    this ship: whatever fixes it writes ``status``, and must still not write
    grades. The caller therefore has nothing here it could accidentally grade
    with.
    """

    #: True only when the event has legs and EVERY leg is terminal at the venue.
    settled: bool

    #: How many legs the venue sent, and how many of them are terminal. Reported
    #: so a partially-settled event is legible as a real, expected state rather
    #: than as a failed read.
    legs_total: int
    legs_settled: int

    #: Which of the four outcomes this was, in one word, for the run's report.
    reason: str


def derive_venue_settlement(statuses: Sequence[Optional[str]]) -> VenueSettlement:
    """Read the venue's settlement fact off one event's leg statuses.

    ``statuses`` is ``[m.get("status") for m in event["markets"]]`` — strings,
    not dicts, so this module stays free of the payload's shape and a guard can
    state its cases in four words each.

    ALL legs must be terminal. An event is one row for us
    (``futures_markets.external_id`` is the event ticker) but many markets at the
    venue, and a Kalshi event can finalise leg by leg — a tennis set-winner event
    settles its first-set leg while the match is still running. Flipping the row
    on the first terminal leg would mark a live market over, which is the same
    class of defect as #2351 (one leg's answer written to every sibling), read
    from the other direction.

    An unreadable status is not a settlement. A missing or unknown word answers
    ``False`` rather than being treated as "probably over": the cost of waiting
    one more sweep is a day, and the cost of being wrong is a live market showing
    as resolved.
    """
    legs = [(s or "").strip().lower() for s in statuses]
    if not legs:
        # 200-with-no-markets. Gotcha #53: an empty list is a response shape, not
        # a fact about settlement.
        return VenueSettlement(False, 0, 0, "no_legs")

    settled_legs = sum(1 for s in legs if s in VENUE_SETTLED_STATUSES)
    if any(not s for s in legs):
        return VenueSettlement(False, len(legs), settled_legs, "status_absent")
    if settled_legs == len(legs):
        return VenueSettlement(True, len(legs), settled_legs, "settled")
    if settled_legs:
        return VenueSettlement(False, len(legs), settled_legs, "partially_settled")
    return VenueSettlement(False, len(legs), settled_legs, "open_at_venue")


def _max_or_none(values: Iterable[Optional[datetime]]) -> Optional[datetime]:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def derive_resolution_window(markets: Sequence[_HasWindow]) -> ResolutionWindow:
    """Derive ``(resolution_date, expiration_time)`` for one Kalshi event.

    ``markets`` is the event's sub-market list. Both aggregations use ``max()``
    across sub-markets: an event resolves when its LAST leg does, which is the
    same aggregation the poller has always used for the backstop, so the
    preserved ``expiration_time`` column reproduces the old ``resolution_date``
    value exactly (CAL-P061's 421/421 stays checkable).

    Falls back to the backstop only when NO sub-market carries a ``close_time``.
    A partial event — some legs with a close, some without — uses the max over
    the legs that have one, because a missing ``close_time`` is an absent field,
    not an assertion that the leg runs forever.
    """
    close_max = _max_or_none(m.close_time for m in markets)
    expiration_max = _max_or_none(m.expiration_time for m in markets)

    if close_max is None:
        return ResolutionWindow(
            resolution_date=expiration_max,
            expiration_time=expiration_max,
            used_expiration_fallback=True,
        )

    return ResolutionWindow(
        resolution_date=close_max,
        expiration_time=expiration_max,
        used_expiration_fallback=False,
    )
