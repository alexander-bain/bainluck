"""One predicate for "is this provider's row the same GAME INSTANCE as ours?".

Why this module exists (#1947 / #1945, queue 367)
-------------------------------------------------
Three separate ingest sites paired a provider row to one of our event rows using
a **team-pair key with no date component**, and all three wrote to whatever came
back:

* ``espn_helpers.sync_scheduled_events`` — matched every ``scheduled`` row for a
  sport (no time window at all) against today's ESPN scoreboard by team name and
  stamped ``event.espn_id = ee.espn_id``.
* ``statpal_sync.sync_statpal_schedules`` — ``live_by_teams[home+away]``, then
  wrote the live score onto whatever fixture shared that key.
* ``statpal_sync.sync_statpal_live_scores`` — ``fixture_by_teams[home+away]``
  against every ``status='live'`` row, unbounded in time.

In MLB the same two clubs play a three- or four-game series, so the team pair is
not a game. On 2026-08-17 that stamped the Aug-17 game's ``espn_id`` and final
score onto five genuinely-scheduled Aug-19/20 rows, which then rendered LIVE
40-66h before first pitch (#1947's attended mini-census; ruling 079 — the rows
are real games, so the repair is a correction, never a deletion).

Two aphorisms from ``docs/doctrine.md`` are load-bearing here:

* **Label equality is not identity.** ``"Tigers @ Pirates"`` names a matchup;
  only a matchup *plus an instant* names a game.
* **Could-not-check never renders as nothing-to-report.** A missing date on
  either side is ``UNKNOWN``, never ``SAME`` — so the verdict is three-valued and
  each caller states in its own code what it does with ``UNKNOWN``, rather than
  inheriting a default someone else picked.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

# A day/night doubleheader is the tightest legitimate "two different games, same
# clubs, same day" case in the sports we carry: MLB game 1 ~13:05 local, game 2
# ~19:05 local, so ~6h apart. Consecutive games of a series are ~24h apart. 12h
# sits in the empty band between the two and separates them without needing to
# know which case it is looking at.
#
# Ruling 082: consistency is the requirement, not the constant. If this number
# ever needs to change, change it HERE — every pairing site reads it from this
# module, and a site that hard-codes its own is the defect returning.
SAME_GAME_MAX_SEPARATION = timedelta(hours=12)

# Tolerate commence-time jitter around first pitch. Shared with the ESPN
# premature-live guard (#1207), which is re-exported from ``espn_helpers`` so
# there is exactly one implementation of it.
PREGAME_LIVE_GRACE = timedelta(minutes=15)


class Pairing(str, Enum):
    """Three-valued verdict on whether two rows describe the same game instance."""

    SAME = "same"
    DIFFERENT = "different"
    UNKNOWN = "unknown"  # a time is missing — we could not check, so we did not


def pair_verdict(
    our_commence: datetime | None,
    their_start: datetime | None,
    max_separation: timedelta = SAME_GAME_MAX_SEPARATION,
) -> Pairing:
    """Do these two start times describe the same game instance?

    ``UNKNOWN`` when either side has no time. It is deliberately NOT ``SAME``:
    the whole defect class this module exists for is a check that could not run
    reading as a check that passed.
    """
    if our_commence is None or their_start is None:
        return Pairing.UNKNOWN
    if abs((their_start - our_commence).total_seconds()) <= max_separation.total_seconds():
        return Pairing.SAME
    return Pairing.DIFFERENT


class IdCurrency(str, Enum):
    """Three-valued verdict on whether a provider id still names the row it is on.

    A provider id is a *claim* that a row and a provider record are the same game.
    That claim can go stale — a row keeps the previous night's Odds API event id and
    the scores endpoint happily answers for it — and once it is stale, every read
    that trusts it is reading about a different game (#1981).
    """

    CURRENT = "current"        # the bound row IS the game the provider record describes
    STALE = "stale"            # the bound row is a DIFFERENT game — the id no longer names it
    UNVERIFIABLE = "unverifiable"  # a time is missing — we could not check, so we did not
    UNBOUND = "unbound"        # no row of ours holds this provider id


def external_id_currency(
    our_commence: datetime | None,
    their_start: datetime | None,
    row_found: bool = True,
    max_separation: timedelta = SAME_GAME_MAX_SEPARATION,
) -> IdCurrency:
    """Is the provider id on this row still current, i.e. does it still name this game?

    This is ``pair_verdict`` asked in the direction a *writer* needs it. A writer that
    has looked a row up BY a provider id cannot then use that id as evidence the row is
    the right one — that is circular, and it is the whole of #1981: the Odds API scores
    block compared the SCORE RECORD's commence to ``now`` and never to the row's own, so
    a row carrying the previous night's event id was stamped with the previous night's
    final every 300 seconds.

    Ruling (b)(2), queue 371: **stale-``external_id`` ownership goes with the writer.**
    The writer re-verifies, re-binds, or nulls a stale id; **it never compares against
    one.** This function is the re-verification arm — call it before any write that was
    addressed by a provider id, and treat anything but ``CURRENT`` as a refusal.

    ``UNVERIFIABLE`` is deliberately NOT ``CURRENT``, for the same reason
    ``Pairing.UNKNOWN`` is not ``Pairing.SAME``: a check that could not run must never
    read as a check that passed (doctrine: *could-not-check never renders as
    nothing-to-report*).
    """
    if not row_found:
        return IdCurrency.UNBOUND
    verdict = pair_verdict(our_commence, their_start, max_separation)
    if verdict is Pairing.SAME:
        return IdCurrency.CURRENT
    if verdict is Pairing.DIFFERENT:
        return IdCurrency.STALE
    return IdCurrency.UNVERIFIABLE


def live_write_is_premature(
    event_commence: datetime | None,
    now: datetime | None,
    grace: timedelta = PREGAME_LIVE_GRACE,
) -> bool:
    """True when live state is about to be written onto a row that has not started.

    A row whose own ``commence_time`` is still meaningfully in the future cannot
    legitimately hold a live score, a period, or ``status='live'`` — whatever the
    provider says, it is talking about a different game. This is the guard ESPN
    already had (#1207) and StatPal did not.
    """
    if event_commence is None or now is None:
        return False
    return event_commence > now + grace
