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
"""
from datetime import timedelta

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
