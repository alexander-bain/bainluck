"""Keep a near-kickoff Polymarket match on the venue's CURRENT start (#9418).

The Polymarket twin of ``refresh_dated_fixture_starts`` (#3562), for the same
reason that task exists: the discovery poll cannot reach the rows a reader is
looking at.

## The specimen

Angelini v Johns, ATP Challenger Bari, event 15319927, 2026-09-28:

    our commence_time   12:35Z   commence_time_source = polymarket_venue
    Gamma /events/1091219  startTime 13:50Z, ended 16:53:42Z, FT 4-6 7-6 7-5
    group's stored venue_game_start  12:35Z, parent last rewritten 11:29Z

Nothing reports on a Challenger match (no ESPN id, no StatPal fixture), so the
staleness arm gives it the unobserved tennis bound: 12:35 + 3.0h + 0.5h = 16:05Z.
It suspended the row in the middle of the third set, both venue live feeds drop
a suspended row, and the page froze at 16:10Z while Kalshi and Polymarket moved
every few seconds. Against the venue's own 13:50Z start the bound is 17:20Z and
the match finished inside it.

The #6073 re-date rail exists for exactly this and did not fire, because the
stamp it reads was stale: the hourly poll pages Gamma newest-LISTING-first and
stops at the offset-2000 cap, so a match listed the day before falls out of it
hours before it is played. Order-of-play slippage — a later start published on
the morning — is the ordinary case in tennis, and it lands after the poll has
stopped looking. A second row read the same way at the same time (Piros v
Hassan, 15320362: ours 15:00Z, venue 16:10Z, parent last rewritten 13:26Z) and
badged LIVE seventy minutes before play.

## What a pass does

For every unfinished row whose start Polymarket owns and which kicks off inside
the window, read the group's Gamma record BY ID (the poll's window is the thing
being routed around), and:

1. write the record's fixture instant to the group's ``venue_game_start`` — the
   value the poll itself would have written had it reached the event, parsed by
   the poll's own parser so the two can never disagree about the string;
2. re-date the event through the #6073 decision functions, verbatim — the same
   authority door, pairing check, unmoved-row read, ``unstart_when_future`` and
   conditional write Phase 1.5 uses. Phase 1.5 is not the rail this depends
   on: its priority order fills the fresh slice with finished rows before any
   link to a row with no ``external_id``, so a live tennis link waits on the
   shard rotation. But it must AGREE with this, which is why step 1 exists: a
   re-date over a stale stamp would be moved straight back the next time Phase
   1.5 did reach the row.

## What it does not do

* It does not treat a price tick, or Gamma's ``live`` flag, as play. It moves a
  DATE, and only to the instant the venue published.
* It does not widen any bound. The unobserved tennis bound is unchanged; it is
  measured from a start that is now the right one.
* It does not resume a row already suspended. A correction that puts the start
  in the future un-starts it (``unstart_when_future``), exactly as Phase 1.5
  does; a past start leaves ``suspended`` where it is. With the pass every five
  minutes the correction lands hours before the bound, so the gap is the rows
  suspended before it shipped.
* Records must agree. An event linked to two Gamma groups that publish two
  different instants is held — the venue has not told one story.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from app.utils.event_completion import POLYMARKET_VENUE_COMMENCE_SOURCE

#: How far back a row's start may sit and still be refreshed. A tennis row with
#: nothing observing it leaves the live board at 3.5h, so six covers the whole
#: live life of the rows this is for with margin; it matches Phase 1.5's own
#: venue-instant lookback.
LOOKBACK = timedelta(hours=6)

#: How far ahead. Order of play for tomorrow is published this evening; a day is
#: enough to have the right start before the row can go live on the wrong one.
LOOKAHEAD = timedelta(hours=24)

#: Agreement tolerance between two groups' instants for one event. Gamma reports
#: whole minutes; the re-date's own no-op floor is one minute.
AGREEMENT_TOLERANCE = timedelta(minutes=1)

#: Starts Polymarket owns — the two values the #6073 authority door lets the
#: venue instant overwrite. The door is still asked per row; this only keeps
#: rows it would refuse out of the Gamma read.
POLYMARKET_OWNED_SOURCES = ("polymarket", POLYMARKET_VENUE_COMMENCE_SOURCE)

GROUP_ID_PREFIX = "polymarket:"

#: One key, merged — never a whole-blob rewrite, so a poll writing the rest of
#: the metadata at the same moment loses nothing. ``IS DISTINCT FROM`` makes an
#: agreeing group a zero-row statement rather than a churned one.
STAMP_VENUE_GAME_START_SQL = """
    UPDATE futures_markets
       SET market_metadata = COALESCE(market_metadata, '{}'::jsonb)
                             || jsonb_build_object('venue_game_start', CAST(:stamp AS text))
     WHERE group_id = :group_id
       AND source = 'polymarket'
       AND (market_metadata->>'venue_game_start') IS DISTINCT FROM CAST(:stamp AS text)
"""


def gamma_event_id_from_group(group_id) -> Optional[str]:
    """``'polymarket:1091219'`` → ``'1091219'``; any other shape → ``None``."""
    if not isinstance(group_id, str) or not group_id.startswith(GROUP_ID_PREFIX):
        return None
    tail = group_id[len(GROUP_ID_PREFIX):].strip()
    return tail if tail.isdigit() else None


def stamp_for(instant: Optional[datetime]) -> Optional[str]:
    """The string the poll writes: ``game_start_time.isoformat()``, verbatim."""
    return instant.isoformat() if instant is not None else None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def row_fixture_start(instants: Iterable[Optional[datetime]]) -> Optional[datetime]:
    """One event's instant from every group it is linked to, or ``None``.

    Every group must have answered, and all answers must agree to within
    :data:`AGREEMENT_TOLERANCE`. A group with no instant, or two groups a
    real distance apart, holds the row: an absent answer may be the one that
    disagrees.
    """
    seen = list(instants)
    if not seen or any(i is None for i in seen):
        return None
    first = _aware(seen[0])
    if any(abs(_aware(i) - first) >= AGREEMENT_TOLERANCE for i in seen[1:]):
        return None
    return seen[0]
