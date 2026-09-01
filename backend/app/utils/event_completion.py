"""When did a game actually END, and is it safe to call it over?

Two staleness nets close events on elapsed wall-clock when no data source caught
the finish: ``espn_sync._transition_event_statuses_impl`` and
``odds_polling.detect_and_close_stale_events``. Both used ``now()`` as the
completion time and neither checked whether the game was still being played.
That combination is the PRODUCER of the CAL-P002 defect class:

  * A game that runs long (extra innings, overtime, a rain delay) exceeds its
    sport's max duration while still in progress. The net closes it, keeps
    whatever score the last poll happened to have written, and grades the blend
    to 1.0/0.0 off that mid-game number. An NBA row was found holding a literal
    halftime score, 45-56, for a game that finished 87-109 — with the derived
    "winner" inverted, which is what calibration then grades against.
  * ``completed_at = now()`` is a backend processing timestamp, not a game-end
    time (gotcha #22). It is wrong by however long the net took to notice, and
    it is what chart domains and "settled" language stand on.

``espn_sync``'s docstring has always PROMISED the missing guard — "live → closed:
commence_time + max_duration has passed AND no score updates in the last 30 min"
— but no such check was ever written. This module implements it, and derives the
completion time from the same evidence, so one query answers both questions.

The evidence is the last real post-commence snapshot from any source. If a source
captured something in the last ``STILL_ACTIVE_MINUTES``, the game is very likely
still being played and closing it would freeze a mid-game score. If nothing has
been captured for longer than that, the last capture is the best available
estimate of when the game ended.

Shared by both nets and by ``scripts/repair_event_final_scores.py`` so the
producer and the repair can never drift on what "when did this end" means.

It also answers the question one step earlier in the same chain — *did it
START?* — because both nets measure elapsed time from ``commence_time`` and
neither ever asked whether that field held a start anybody reported. See
``commence_time_is_a_reported_start``.
"""
from datetime import timedelta

# ── Is this commence_time a START, or a stand-in for one? (q076) ─────────────
#
#: The one ``events.commence_time_source`` value that says, in the writer's own
#: words, that no schedule published a time for this fixture.
#:
#: ``prediction_market_matching.auto_create_commence_time`` stamps it when it
#: falls back to the DATE parsed out of a Kalshi ticker, because Kalshi's own
#: ``commence_time`` is a close/resolution time (gotcha #14) and disagreed with
#: it. A ticker date has no time-of-day, so the value it resolves to is
#: **midnight UTC** — a day, rendered as an instant.
#:
#: This is provenance, not a heuristic. q066b established that CLUSTERING is not
#: a placeholder signature (a Saturday 3pm card genuinely is ten simultaneous
#: kickoffs, and ESPN's real order of play gives 15:05Z to three US Open matches
#: at once), so nothing here looks at the hour, the date, or how many rows share
#: a stamp. It reads the field where the writer already recorded what it did.
TICKER_DERIVED_COMMENCE_SOURCE = "kalshi_ticker"

#: Every provenance that means "derived because nothing published one". A set of
#: one today; named so a future derived source joins the rule instead of
#: inheriting the clock by omission.
DERIVED_COMMENCE_SOURCES = frozenset({TICKER_DERIVED_COMMENCE_SOURCE})


def commence_time_is_a_reported_start(commence_time_source) -> bool:
    """May a clock be run from this event's ``commence_time``?

    False ⇒ the field holds a stand-in, and every rule that reads it as an
    instant is reading something nobody reported. ``scheduled → live`` on
    ``commence_time <= now`` is such a rule, and it is the first domino: a row
    promoted off a stand-in then has ``hours_since_start`` measured from it, and
    the staleness nets settle it at the sport's maximum duration with whatever
    score it never had.

    MEASURED, production 2026-09-01. Of every event ever stamped
    ``kalshi_ticker``, **705 are ``closed`` and all 705 carry no score** — 468 of
    them in the preceding seven days. Not "mostly"; the whole population. This
    provenance has never once produced a settled row with a result, so declining
    to start its clock cannot cost a single real one. The 181 still ``scheduled``
    include 40 US Open matches — Alcaraz, Sabalenka, Swiatek, Osaka, Medvedev,
    Pegula — stamped ``2026-09-02T00:00:00Z``, i.e. midnight UTC of a ticker
    date, for matches played in the AFTERNOON of September 2. Each one holds live
    Kalshi markets and would have gone LIVE at 5:00 pm PT on the 1st and FINAL,
    unscored, before midnight.

    ── WHY REFUSING IS THE WHOLE FIX, AND NOT HALF OF ONE ──

    The obvious alternative is to promote such a row when some source has
    captured a post-commence snapshot, mirroring
    :func:`game_may_still_be_running`. It does not work HERE, and the asymmetry
    is worth stating because it looks like it should. That guard asks "is a game
    we know started still going?", where a snapshot after a REAL start is
    evidence of play. This one would ask "did a game start?", where a snapshot
    after a MIDNIGHT STAND-IN is evidence of nothing — Kalshi prices tomorrow's
    match all night, so every row would qualify and the guard would be a no-op
    that reads as a safeguard.

    So the honest answer is the plain one, and it is ``derive_completed_at``'s
    own principle one field over: **we do not have a start, so we do not act as
    if we do.** ``commence_time`` is ``NOT NULL`` and load-bearing for ordering
    and windowing, so the row keeps its stand-in and simply stops driving state
    off it. It is not stranded: ``_SOURCE_PRIORITY`` ranks this provenance 0 and
    "an unknown current source confers no immunity", so the moment odds_api,
    ESPN or StatPal publishes a real time onto the row, the source changes with
    it and the clock starts normally.

    A ``None`` source is deliberately NOT derived. Most of the table predates the
    column, and treating unknown provenance as un-startable would freeze the
    ordinary promotion path for nearly every event on the site — the opposite
    error, and a far larger one.
    """
    return commence_time_source not in DERIVED_COMMENCE_SOURCES


# A source captured something this recently ⇒ the game is still being played, so
# a wall-clock timeout is NOT evidence that it is over. Deliberately the same 30
# minutes the espn_sync docstring has always claimed.
STILL_ACTIVE_MINUTES = 30

# One batched query for a whole candidate set: the most recent snapshot from any
# source that lands at or after the event's own commence_time. Pre-commence rows
# are excluded because a pregame line says nothing about when play ended.
LAST_POST_COMMENCE_SNAPSHOT_SQL = """
    SELECT x.event_id, MAX(x.captured_at) AS last_snap
    FROM (
        SELECT w.event_id, w.captured_at
          FROM win_prob_snapshots w
          JOIN events e ON e.id = w.event_id
         WHERE w.event_id = ANY(:event_ids) AND w.captured_at >= e.commence_time
        UNION ALL
        SELECT o.event_id, o.captured_at
          FROM odds_snapshots o
          JOIN events e ON e.id = o.event_id
         WHERE o.event_id = ANY(:event_ids) AND o.captured_at >= e.commence_time
    ) x
    GROUP BY x.event_id
"""


def game_may_still_be_running(last_snapshot, now) -> bool:
    """Is there live evidence that this game has NOT finished?

    True ⇒ hold off. A wall-clock timeout on a game something is still reporting
    on is the frozen-score producer: closing here writes a mid-game score into a
    settled event and grades the blend off it.

    No snapshot at all is NOT evidence of activity — that is the ordinary case
    for an event whose sources went quiet, and it must stay closeable or the
    staleness net stops doing its job.
    """
    if last_snapshot is None or now is None:
        return False
    return (now - last_snapshot) < timedelta(minutes=STILL_ACTIVE_MINUTES)


def derive_completed_at(last_snapshot, commence_time, now=None):
    """Best available game-end time, or None to leave it unset.

    The last real post-commence snapshot (gotcha #22 — never a backend
    processing timestamp). Returns None rather than guessing when there is no
    such snapshot: a NULL ``completed_at`` is a visible gap the repair can fill,
    whereas a plausible-looking ``now()`` is a wrong value nothing will ever
    question.

    Never returns a time that precedes the start (gotcha #46) — that inversion
    means an earlier game's data merged onto this event, and stamping it would
    manufacture the very invariant violation the audit hunts for.
    """
    if last_snapshot is None or commence_time is None:
        return None
    if last_snapshot < commence_time:
        return None
    return last_snapshot


#: Statuses a staleness net can put an event into. Both are "we stopped hearing
#: about it", neither is "a source told us it finished".
_NET_SETTLED_STATUSES = ("closed", "completed")


def settlement_is_a_staleness_artifact(
    status, home_score, away_score, new_commence, completed_at
) -> bool:
    """Did a staleness net settle an event that had not been played? (q066b)

    Three facts have to hold at once, and the conjunction is what makes it safe:

    1. **The row is settled** — ``closed`` or ``completed``.
    2. **It carries no score.** This is the load-bearing one. Every net in this
       codebase settles on ELAPSED WALL-CLOCK, never on a result, so a settled
       row with no score is a row nothing ever reported a finish for. A scored
       row is left alone no matter what else is true: a real result outranks any
       schedule correction, and gotcha #21 says never bulk-disturb resolution.
    3. **The owning provider has since moved the start PAST the recorded
       completion.** ``completed_at < new_commence`` is the #46 inversion, read
       here from the other side: normally it means a wrong-sibling fold and the
       correction must be refused, but on an unscored row it means the settlement
       timestamp predates the game it claims to have ended — so the settlement is
       the wrong field, not the start.

    Same class of evidence as ``espn_helpers.espn_replay_unsettles`` (ESPN
    reporting IN PROGRESS on a row we call settled), reached through a different
    door: there the live source contradicts the state, here the SCHEDULE source
    does. Both are proof the settled state is wrong, and both clear it.

    The producing shape, measured on the live US Open slate 2026-09-01: The Odds
    API published all of Aug 31's matches at one session-start default of
    15:00:00Z, the clock promoted them to ``live`` at 15:00, the staleness nets
    closed them during an ordinary poll gap, and 35 matches sat marked finished
    with no result while bookmakers were still actively pricing them — nine of
    them being played the following day.
    """
    if status not in _NET_SETTLED_STATUSES:
        return False
    if home_score is not None or away_score is not None:
        return False
    if completed_at is None or new_commence is None:
        return False
    return completed_at < new_commence
