SELECT date_trunc('hour', s.captured_at) AS hr, count(*) AS rows, count(DISTINCT s.event_id) AS events, max(s.id) AS max_id
FROM win_prob_snapshots s
WHERE s.source = 'polymarket' AND s.captured_at >= now()-interval '8 hours'
 AND s.game_state->>'poll_type' = 'ws_fast_lane'
GROUP BY 1 ORDER BY 1
