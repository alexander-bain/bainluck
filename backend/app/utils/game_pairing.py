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
from typing import Any

#: The statuses on which a row is ASSERTING a result to a reader.
#:
#: Spelled here rather than imported from ``espn_tennis_anchor.SETTLED_STATUSES``
#: on purpose: this module imports nothing but the standard library (the same
#: discipline ``sport_keys.py`` keeps), and that module pulls
#: ``app.services.espn_tennis`` in behind it — which is exactly why
#: ``odds_polling`` imports its tennis predicate IN-FUNCTION. One vocabulary in
#: two places is only safe if a drift is loud, so
#: ``test_the_settled_vocabulary_agrees_with_the_tennis_rails`` pins the two
#: together and reds if either moves.
SETTLED_STATUSES_CLAIMING_A_RESULT = ("completed", "closed")

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


def clockless_write_defers_to_authority(
    event_status: str | None, espn_id: str | int | None
) -> bool:
    """Should the Odds API scores feed stand down from writing this live score?

    #6056, and a sibling of :func:`live_write_is_premature` above in both shape
    and purpose: a small statement about whether a writer may touch a row, kept
    out of the thousand-line polling loop so it can be argued with and tested.

    `events.home_score` has at least three unarbitrated writers and the Odds API
    scores feed is the only one carrying no clock and no period, so it cannot be
    ordered against the others by game time the way `game_state`'s
    `live_write_would_revert` orders ESPN and StatPal. What it CAN be given is a
    precedence: while a game is running and an authority feed is attached to the
    row, the feed that cannot say where the game is does not move the score.

    `odds_polling` already refuses to run the stat model on exactly this
    population, for exactly this reason ("Running both paths causes
    oscillation... they fight") — this is that judgement applied to the score
    write it sits beside.

    Both conditions are load-bearing and neither is a proxy for the other:

    * **`live` only.** A settled or scheduled row is not being fought over, and
      the write that lands a FINAL score must never be withheld — that is the
      one case where this feed noticing first matters more than the flicker.
    * **`espn_id` only.** A row ESPN does not cover — most college football,
      handball, the smaller soccer leagues — has no other score writer at all,
      and deferring there would mean deferring to nobody.
    """
    return event_status == "live" and bool(espn_id)


def clockless_write_repoisons_a_settled_final(
    *,
    event_status: Any,
    espn_id: Any,
    home_score: Any,
    away_score: Any,
    stored_home_score: Any = None,
    stored_away_score: Any = None,
) -> bool:
    """May the clockless feed CHANGE a final an authority already banked?

    #7147 / CERT-3145, and the arm
    :func:`clockless_write_defers_to_authority` deliberately does not cover.
    That guard is ``status == "live" and bool(espn_id)``, and its docstring says
    why ``completed`` is excluded, in as many words: *"the write that lands a
    FINAL score must never be withheld — that is the one case where this feed
    noticing first matters more than the flicker."*

    **That carve-out is right, and it is not what was happening.** Landing a
    final on a row that holds none, and OVERWRITING a final an ESPN-anchored row
    already holds, are two different writes that the single word ``completed``
    was covering as one. Measured on production 2026-09-19: event ``15313146``
    was repaired to ESPN's ``7-3`` at 22:37Z and was serving ``7-2`` again by
    23:15:07Z, with a freshly stamped ``score_history`` row to match. The
    cleanup ran, and the writer simply wrote the stale number back — so the
    repair was a deletion of today's residue, not a fix, and the reader saw the
    wrong final return within the hour.

    So the carve-out is kept and narrowed to the write it was written for:
    **a clockless write that would land a DIFFERENT pair on a settled,
    authority-anchored row that already states a result is refused.**

    ═══ WHY EACH CONDITION IS LOAD-BEARING ═══

    * **A write carrying neither side is not a write.** Refused first, so a pass
      that touched nothing can never increment the counter — the counter is the
      only way to tell this guard holding from the population being empty.
    * **Settled only**, read off :data:`SETTLED_STATUSES_CLAIMING_A_RESULT`. A
      ``live`` row is the sibling's business and a ``scheduled`` one is nobody's.
    * **``espn_id`` only.** Identical to the sibling's reasoning: a row ESPN does
      not cover has no other score writer, and deferring there defers to nobody.
      This is the "authoritative" in the ship's name — without an anchor there is
      no authority whose number this would be protecting.
    * **The row must ALREADY hold BOTH halves.** This is the carve-out, kept
      intact. A settled row with a ``NULL`` on either side is not stating a
      result yet, so this write is the one LANDING the final and must go
      through. Only a complete stored pair can be re-poisoned.
    * **The pair must actually DIFFER.** An agreeing write is a no-op; refusing
      it would spend a refusal on a pass that changed nothing and make the
      counter unreadable.

    ═══ IT JUDGES THE POST-WRITE PAIR, NOT THE PAYLOAD ═══

    The same correction CERT-2963 forced on the tennis predicate, for the same
    reason: ``odds_polling`` stores each side in an INDEPENDENT statement, so a
    payload carrying one side lands on top of whatever the row already holds.
    Stored ``7-3`` plus an incoming ``home=7, away=None`` is judged on the pair
    the row will HOLD — ``7-3``, unchanged, allowed — while stored ``7-3`` plus
    an incoming ``away=2`` will hold ``7-2`` and is refused. Asking the payload
    instead would answer about a score that will never exist.

    Returning ``True`` means **decline the score half of this write**, never the
    status: a game that finished, finished. Same trade as both sibling guards.
    """
    if home_score is None and away_score is None:
        return False
    if event_status not in SETTLED_STATUSES_CLAIMING_A_RESULT:
        return False
    if not espn_id:
        return False
    if stored_home_score is None or stored_away_score is None:
        return False
    effective_home = home_score if home_score is not None else stored_home_score
    effective_away = away_score if away_score is not None else stored_away_score
    return (effective_home, effective_away) != (stored_home_score, stored_away_score)
