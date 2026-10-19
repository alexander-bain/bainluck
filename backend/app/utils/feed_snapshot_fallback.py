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

Postgres only: ``DISTINCT ON`` and the JSONB operator. The real-server gate is
``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``.
"""

WITHDRAWAL_MARKER_KEY = "live_source_withdrawal"

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
