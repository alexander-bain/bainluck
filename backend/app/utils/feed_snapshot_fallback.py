"""The last stored reading a feed card falls back to when the blend has none.

── WHAT THE FALLBACK IS FOR ─────────────────────────────────────────────────────

``routes/feed.py`` serves a card's ``current_odds`` from
``compute_aggregate_probability``. When that returns None, the feed reads the
newest non-NULL ``win_prob_snapshots`` row for the event instead, which is how
pregame Kalshi/Polymarket readings that exist only in history still reach a
card. That stays as it is.

── WHY A WITHDRAWAL HAS TO STOP IT (#11254) ─────────────────────────────────────

Live's withdrawal path (#10090) removes a venue from
``Event.win_probability_sources`` once its quote is gone. In the same commit it
writes one history row for that venue: ``home_win_probability`` NULL, and
``game_state`` ``{"live_source_withdrawal": true}``. If that venue was the only
contributor, the blend goes to None, and an "ignore NULL rows" fallback skips
the marker and lands on the venue's previous reading. The card then shows the
retired number (0.82 in the attempt86 lab) as the current probability, on the
same page where the event detail has already dropped it.

So an explicit withdrawal row for source S retires S's own rows captured at or
before it. It does NOT retire:

* other sources' readings. Their last value is still theirs, and the old
  fallback served them.
* a later reading from S. A venue that quotes again is back.
* an ordinary NULL row, or a ``live_source_withdrawal`` that is missing, false
  or the STRING ``"true"``. Live's history reader accepts only JSON ``true``, so
  this one does too. A NULL alone has never meant "withdrawn" and must not
  start meaning it here.

── WHY IT READS IN TWO PASSES (#1459) ───────────────────────────────────────────

The statement keeps the newest valid row per event by reading EVERY history
row for each id, and production has no ``(event_id, captured_at)`` index. On a
cold dyno that full-history scan was 13.9 s of the events stage after release
v5793. ``read_snapshot_fallbacks`` first runs the same statement over the last
``SNAPSHOT_FALLBACK_RECENT_WINDOW`` only, then runs the unchanged statement for
the ids that pass left unanswered. The answer is the same:

* an event with a valid reading inside the window has its newest valid reading
  inside the window, because every in-window row is newer than every row
  before it;
* whether an in-window row is retired is decided the same way in both passes.
  Only a withdrawal captured at or after the row can retire it, and such a
  withdrawal is in the window too. A source whose latest withdrawal is before
  the window retires none of its in-window rows under either statement;
* an event with no valid in-window reading gets exactly the old statement.

Rows tied on ``captured_at`` were unordered before and are unordered now; the
two passes do not change which rows tie.

Postgres only: ``DISTINCT ON`` and the JSONB operator. The real-server gate is
``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

WITHDRAWAL_MARKER_KEY = "live_source_withdrawal"

#: #1459: how far back pass 1 reads. Correctness does not depend on it (any
#: window gives the same answer); it decides how many ids pass 1 answers.
SNAPSHOT_FALLBACK_RECENT_WINDOW = timedelta(hours=3)

SNAPSHOT_FALLBACK_SQL = f"""
    WITH retired AS (
        SELECT event_id, source, max(captured_at) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
          AND home_win_probability IS NULL
          AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
        GROUP BY event_id, source
    )
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM win_prob_snapshots s
    LEFT JOIN retired r
      ON r.event_id = s.event_id AND r.source = s.source
    WHERE s.event_id = ANY(:ids)
      AND s.home_win_probability IS NOT NULL
      AND (r.withdrawn_at IS NULL OR s.captured_at > r.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
"""

#: #1459 pass 1: ``SNAPSHOT_FALLBACK_SQL`` with both reads bounded below by
#: ``:since``. The withdrawal CTE is bounded too: a withdrawal before the window
#: retires no in-window row, so leaving it out changes nothing but the cost.
SNAPSHOT_FALLBACK_RECENT_SQL = f"""
    WITH retired AS (
        SELECT event_id, source, max(captured_at) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
          AND captured_at >= :since
          AND home_win_probability IS NULL
          AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
        GROUP BY event_id, source
    )
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM win_prob_snapshots s
    LEFT JOIN retired r
      ON r.event_id = s.event_id AND r.source = s.source
    WHERE s.event_id = ANY(:ids)
      AND s.captured_at >= :since
      AND s.home_win_probability IS NOT NULL
      AND (r.withdrawn_at IS NULL OR s.captured_at > r.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
"""


async def read_snapshot_fallbacks(
    db: Any, ids: Sequence[int], *, now: datetime
) -> dict[int, Any]:
    """``{event_id: home_win_probability}``, the same answer as one
    ``SNAPSHOT_FALLBACK_SQL`` over ``ids``, read in two passes (#1459).

    ``now`` is the request's clock; pass 1 reads from ``now`` minus
    ``SNAPSHOT_FALLBACK_RECENT_WINDOW``. Both passes run on ``db`` in order and
    nothing is caught: a cancelled or failed pass raises to the caller exactly
    as the single statement did, and no partial answer is returned.
    """
    from sqlalchemy import text

    if not ids:
        return {}
    since = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    since = since - SNAPSHOT_FALLBACK_RECENT_WINDOW
    answered: dict[int, Any] = {}
    recent = await db.execute(
        text(SNAPSHOT_FALLBACK_RECENT_SQL), {"ids": list(ids), "since": since}
    )
    for row in recent.all():
        answered[row.event_id] = row.home_win_probability
    rest = [event_id for event_id in ids if event_id not in answered]
    if rest:
        older = await db.execute(text(SNAPSHOT_FALLBACK_SQL), {"ids": rest})
        for row in older.all():
            answered[row.event_id] = row.home_win_probability
    return answered


# ── #1480: ONE ANSWER FOR EVERY READER OF THE SAME CANDIDATE SET ─────────────
#
# The answer depends only on ``ids``: the recent window changes which pass
# answers an id, never the answer (see "WHY IT READS IN TWO PASSES"). So
# `/api/feed` reuses one answer per id set through `principal_independent_cache`
# instead of each Sports/Discover miss re-reading it, and the key has no clock.

#: The shared-artifact namespace the answer is reused under.
SNAPSHOT_FALLBACK_SHARED_NAMESPACE = "event_snapshot_fallback"


def snapshot_fallback_share_key(ids: Sequence[int]) -> tuple:
    """The shared-cache key for one fallback id set.

    The two statements' digest rotates the key if either changes; ``"v1"`` is
    the answer's shape.
    """
    from app.utils.principal_independent_cache import digest_of

    return (
        "v1",
        digest_of([SNAPSHOT_FALLBACK_SQL, SNAPSHOT_FALLBACK_RECENT_SQL]),
        digest_of(str(event_id) for event_id in ids),
    )


async def read_snapshot_fallback_artifact(
    db: Any, ids: Sequence[int], *, now: datetime
) -> dict[int, float]:
    """`read_snapshot_fallbacks` as plain floats, the form that is shared.

    The caller rounds ``float(home)`` either way, so a float here gives the
    card the same number a ``Decimal`` would. Nothing is caught.
    """
    return {
        event_id: float(home)
        for event_id, home in (
            await read_snapshot_fallbacks(db, ids, now=now)
        ).items()
    }
