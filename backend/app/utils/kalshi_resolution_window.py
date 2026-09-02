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
