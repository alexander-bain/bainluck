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

One pass over the event's rows (#11254 follow-through). A window over
``(event_id, source)`` carries each source's latest withdrawal onto its own
rows, so ``win_prob_snapshots`` is read once. The first version joined a
second, grouped read of the same rows to find the withdrawals. On production
that doubled the buffers the fallback touches (205k vs 103k for 263 events),
because no index covers the marker and every row's heap page is read to test
it. The answer is the same; the window rides ``ix_winprob_event_source``'s own
order, so it adds no sort.

Postgres only: ``DISTINCT ON``, ``FILTER`` and the JSONB operator. The
real-server gate is
``tests/integration/test_feed_snapshot_fallback_withdrawal_11254_pg.py``.
"""

WITHDRAWAL_MARKER_KEY = "live_source_withdrawal"

SNAPSHOT_FALLBACK_SQL = f"""
    SELECT DISTINCT ON (s.event_id) s.event_id, s.home_win_probability
    FROM (
        SELECT event_id, captured_at, home_win_probability,
               max(captured_at) FILTER (
                   WHERE home_win_probability IS NULL
                     AND game_state -> '{WITHDRAWAL_MARKER_KEY}' = CAST('true' AS jsonb)
               ) OVER (PARTITION BY event_id, source) AS withdrawn_at
        FROM win_prob_snapshots
        WHERE event_id = ANY(:ids)
    ) s
    WHERE s.home_win_probability IS NOT NULL
      AND (s.withdrawn_at IS NULL OR s.captured_at > s.withdrawn_at)
    ORDER BY s.event_id, s.captured_at DESC
"""
