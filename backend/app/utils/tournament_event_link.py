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

═══ THE SECOND CHANNEL: THE AUTHORITY'S OWN EVENT ID (#2693 step 2) ═══

The channel above starts at a *register matchup*, and ``build_slate`` retires a
matchup the moment its match starts.  So the Finished list — the one surface
made entirely of matches that have already started — is the one the channel
above structurally cannot serve: measured on production 2026-09-02, **118 of
its 235 rows carry no matchup at all**, only ``espn:{competition_id}``, and
every one of them rendered as dead text.

Those rows are not id-less.  ``espn:184739`` IS an id, it is the authority's,
and since lane1/057 (#2693 step 0) put an ``espn_id`` on 196 of the 200 US Open
``events`` rows there is now something for it to dereference to:

    ESPN competition id  ->  events.espn_id  ->  events.id

One indexed lookup, no name, no time window — the same posture as the market
channel, through a different id.  Measured on the same payload, 47 of the 118
resolve and the other 71 are qualifying matches for which no ``events`` row
exists at all: a coverage fact, not a join failure, and the reason the count is
published rather than the gap being papered over.

**It refuses on ambiguity, and that refusal is load-bearing.**  ``espn_id`` had
no unique constraint when this was written — 196 ids were worn by 430 rows —
so an id naming two events must resolve to neither.  Picking one would put a
reader on a coin-flip page while looking perfectly well.  The refusal is
counted as ``ESPN_ID_AMBIGUOUS``, which is also the alarm that says the step-2
repair has regressed.

Nothing here reads a probability, and nothing here writes.  Identity only —
the same rule ``tournament_register`` states about itself.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

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

#: Named refusals of the authority-id channel.  Same rule as above: a
#: competition id that does not resolve is COUNTED, never dropped silently.
ESPN_UNRESOLVED_REASONS = (
    #: No ``events`` row carries this competition id. Almost all of these are
    #: qualifying matches we hold no market for and therefore never created.
    "NO_EVENT_FOR_ESPN_ID",
    #: Two or more rows carry it. Resolves to neither — see the module
    #: docstring, and #2693 step 2, which is what drives this to zero.
    "ESPN_ID_AMBIGUOUS",
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


async def resolve_espn_competition_events(
    session: AsyncSession,
    competition_ids: Sequence[str],
    sport_keys: Sequence[str],
) -> dict[str, Any]:
    """ESPN competition id -> ``events.id``, for the ids a results feed names.

    ONE QUERY, bounded twice over: by the competition ids the caller actually
    holds (a few hundred at most) and by ``sport_keys``, which is the
    tournament spec's own named list.  The sport bound is not an optimisation —
    it is what stops a tennis competition id from resolving to a baseball row
    should the two id spaces ever collide, and it is named in
    ``REGISTERED_TOURNAMENTS`` rather than inferred from the slug for the same
    reason every other bound on this page is.

    Returns::

        {
          "by_espn":       {competition_id: event_id},
          "unresolved":    {competition_id: reason},
          "reason_counts": {reason: n},
        }

    An id carried by two events resolves to NEITHER.  ``espn_id`` is not unique
    yet (#2693 step 2), and a link that guesses between two rows is worse than
    no link: it is wrong half the time and looks right every time.
    """
    from app.models.models import Event, Sport  # noqa: PLC0415 — task-code import

    wanted = [str(cid) for cid in dict.fromkeys(competition_ids) if cid]
    by_espn: dict[str, int] = {}
    unresolved: dict[str, str] = {}
    if not wanted or not sport_keys:
        return {"by_espn": by_espn, "unresolved": unresolved, "reason_counts": {}}

    rows = await session.execute(
        select(Event.espn_id, Event.id)
        .join(Sport, Sport.id == Event.sport_id)
        .where(Event.espn_id.in_(wanted), Sport.key.in_(list(sport_keys)))
    )

    claims: dict[str, list[int]] = {}
    for espn_id, event_id in rows.all():
        claims.setdefault(str(espn_id), []).append(int(event_id))

    for competition_id in wanted:
        found = claims.get(competition_id) or []
        if not found:
            unresolved[competition_id] = "NO_EVENT_FOR_ESPN_ID"
        elif len(set(found)) > 1:
            unresolved[competition_id] = "ESPN_ID_AMBIGUOUS"
            logger.warning(
                "tournament event link: espn competition %s names %s events (%s) — "
                "all dropped; #2693 step 2 has regressed",
                competition_id, len(set(found)), ", ".join(str(e) for e in sorted(set(found))),
            )
        else:
            by_espn[competition_id] = found[0]

    reason_counts: dict[str, int] = {}
    for reason in unresolved.values():
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "by_espn": by_espn,
        "unresolved": unresolved,
        "reason_counts": dict(sorted(reason_counts.items())),
    }
