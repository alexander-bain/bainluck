"""Which ``events`` row is this registered matchup — answered by id, never by name.

═══ WHY THIS MODULE EXISTS ═══

Alex, 2026-08-28: *"I thought that tournaments were containers for related
events."*  That is the ruled data model, and it is also what the database
holds.  UX-P149 built a bespoke match page on the premise that a tennis
matchup has nowhere to live — *"tennis matches have no `events` row (zero
exist for any registered matchup)"*.  That was true when it was measured and
is not true now: the Odds API began carrying US Open main-draw singles on
**2026-08-27 21:05 UTC**, and 94 standard ``events`` rows exist for the 96
registered R128 fixtures.  A whole parallel surface was built in the window
between the census and the ingest.

So a match is an event like any other, the tournament is curation on top, and
the click-through goes to ``/events/{id}``.  This module is the join that makes
that possible.

═══ THE CHANNEL IS AN ID, AND ONLY AN ID ═══

The obvious join — two player names and a date — is the one thing this module
must not do.  Gotcha #32 / ruling 048: an id-less claim never absorbs, because
a duplicate is visible and reversible and a wrong correspondence is neither.
A link is a weaker claim than an absorption, but it fails the same way: a
reader who taps "Djokovic vs Navone" and lands on a different match has been
lied to by a surface whose whole posture is that identity is pinned.

The id path already exists and needs nothing built:

    register matchup
      -> its pinned match-winner ``market_id``      (register-owned, or filled
                                                     by Q426's link overlay)
      -> ``futures_markets.event_id``               (set by the matching layer)
      -> ``events.id``

Every hop is a primary-key or indexed-column lookup.  No name comparison, no
time window, no category test — the same posture ``_load_match_group`` takes
for the sibling props, and for the same reason.

Measured against production 2026-08-28: 134 Kalshi/Polymarket markets carry an
``event_id`` pointing at one of the 94 US Open events, covering **90** of them.
The six R128 fixtures that do not dereference get no link, which is the correct
output: a missing link is a smaller harm than a wrong one, and
``unresolved_reasons`` counts them by name so the gap is never silent.

═══ WHAT IT REFUSES ═══

* ``NO_PINNED_MARKET``  — the matchup's source blocks pin no market id (the
  committed register's R128 blocks are all ``status: "missing"`` until the
  Q426 overlay fills them).
* ``MARKET_NOT_FOUND``  — a pinned id with no row.  Pinned identity that has
  gone stale is a register finding, not something to route around.
* ``MARKET_UNLINKED``   — the market exists and carries no ``event_id``.  The
  matching layer has not claimed it; this module does not get to guess.
* ``EVENT_DISAGREEMENT`` — two pinned markets for one matchup dereference to
  two different events.  Exactly the case where a name-matcher would pick one
  and look right.  Both are dropped: if the ids disagree, we do not know.

Nothing here reads a probability, and nothing here writes.  Identity only —
the same rule ``tournament_register`` states about itself.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Named refusals.  Every matchup that does not resolve lands in exactly one of
#: these, and the caller publishes the counts — NO SILENT CAPS (gotcha #53: a
#: zero-yield join that reports nothing reads as "there was nothing to find").
UNRESOLVED_REASONS = (
    "NO_PINNED_MARKET",
    "MARKET_NOT_FOUND",
    "MARKET_UNLINKED",
    "EVENT_DISAGREEMENT",
)


def pinned_market_ids(matchup: dict[str, Any]) -> list[int]:
    """The match-winner market ids this matchup pins, across its sources.

    A ``status: "missing"`` block pins nothing by construction, so it
    contributes nothing rather than contributing a ``None`` the caller has to
    filter.  ``kind`` is checked because a register may one day pin a
    non-match market on a matchup; only the match-winner market is the thing
    whose ``event_id`` answers "which event is this".
    """
    ids: list[int] = []
    for block in matchup.get("sources") or []:
        if not isinstance(block, dict):
            continue
        if block.get("status") == "missing":
            continue
        if block.get("kind") not in (None, "match"):
            continue
        market_id = block.get("market_id")
        # `bool` is an `int` in Python and `True` would index row 1.
        if isinstance(market_id, int) and not isinstance(market_id, bool):
            ids.append(market_id)
    return ids


def _resolve_one(
    matchup: dict[str, Any], market_events: dict[int, Optional[int]]
) -> tuple[Optional[int], Optional[str]]:
    """One matchup -> ``(event_id, None)`` or ``(None, reason)``.

    Pure, so the refusal table is testable without a database.  Returns never
    both and never neither.
    """
    # A register-owned `event_id` OUTRANKS the dereference. It is a decision a
    # human wrote down against the evidence; the dereference is a decision the
    # matching layer made. When the register has spoken there is nothing to
    # resolve. (`validate_matchup` already rejects a non-positive-int here, so
    # a bad value never reaches this line.)
    pinned = matchup.get("event_id")
    if isinstance(pinned, int) and not isinstance(pinned, bool) and pinned > 0:
        return pinned, None

    market_ids = pinned_market_ids(matchup)
    if not market_ids:
        return None, "NO_PINNED_MARKET"

    found = [mid for mid in market_ids if mid in market_events]
    if not found:
        return None, "MARKET_NOT_FOUND"

    event_ids = {market_events[mid] for mid in found if market_events[mid] is not None}
    if not event_ids:
        return None, "MARKET_UNLINKED"
    if len(event_ids) > 1:
        # THE ONE CASE A NAME MATCHER WOULD GET "RIGHT" AND BE WRONG ABOUT.
        # Two pinned ids disagreeing is the register and the matching layer
        # contradicting each other about one fixture. Picking a side here would
        # bury that; refusing surfaces it as a counted finding.
        return None, "EVENT_DISAGREEMENT"

    return event_ids.pop(), None


async def resolve_matchup_events(
    session: AsyncSession, register: dict[str, Any]
) -> dict[str, Any]:
    """Every matchup in the register -> its ``events`` row, by id.

    ONE QUERY, bounded by the register.  The pinned market ids across the whole
    register are a list of at most a few hundred integers, so this is a single
    primary-key ``IN (...)`` and never a scan — the same shape as the price
    load ``get_tournament`` already runs.

    Returns::

        {
          "by_matchup":  {matchup_key: event_id},
          "by_event":    {event_id: matchup_key},
          "unresolved":  {matchup_key: reason},
          "reason_counts": {reason: n},
        }

    ``by_event`` is the direction the event page needs (it knows an id and asks
    whether it is part of a tournament) and it is built here rather than
    inverted at the call site so both surfaces read one map.  An event claimed
    by two matchups keeps neither: that is ``EVENT_DISAGREEMENT`` seen from the
    other end, and the same refusal applies.
    """
    from app.models.models import FuturesMarket  # noqa: PLC0415 — task-code import

    matchups = [m for m in (register.get("matchups") or []) if isinstance(m, dict)]

    all_ids = sorted({mid for m in matchups for mid in pinned_market_ids(m)})
    market_events: dict[int, Optional[int]] = {}
    if all_ids:
        rows = await session.execute(
            select(FuturesMarket.id, FuturesMarket.event_id).where(
                FuturesMarket.id.in_(all_ids)
            )
        )
        market_events = {int(mid): eid for mid, eid in rows.all()}

    by_matchup: dict[str, int] = {}
    unresolved: dict[str, str] = {}
    # event_id -> the matchup keys claiming it, so a double claim is visible
    # rather than last-write-wins.
    claims: dict[int, list[str]] = {}

    for matchup in matchups:
        key = matchup.get("matchup_key")
        if not isinstance(key, str) or not key:
            continue
        event_id, reason = _resolve_one(matchup, market_events)
        if event_id is None:
            unresolved[key] = reason or "NO_PINNED_MARKET"
            continue
        by_matchup[key] = event_id
        claims.setdefault(event_id, []).append(key)

    by_event: dict[int, str] = {}
    for event_id, keys in claims.items():
        if len(keys) == 1:
            by_event[event_id] = keys[0]
            continue
        # One event, two matchups: the same event offered as two different
        # matches. Drop every claimant — see the module docstring.
        for key in keys:
            by_matchup.pop(key, None)
            unresolved[key] = "EVENT_DISAGREEMENT"
        logger.warning(
            "tournament event link: event %s claimed by %s matchups (%s) — all dropped",
            event_id, len(keys), ", ".join(sorted(keys)),
        )

    reason_counts: dict[str, int] = {}
    for reason in unresolved.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "by_matchup": by_matchup,
        "by_event": by_event,
        "unresolved": unresolved,
        "reason_counts": dict(sorted(reason_counts.items())),
    }
