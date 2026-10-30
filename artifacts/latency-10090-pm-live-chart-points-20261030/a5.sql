WITH r AS (SELECT id, captured_at, event_id FROM win_prob_snapshots WHERE id > (SELECT max(id) FROM win_prob_snapshots) - 30000
  AND source='polymarket' AND game_state->>'poll_type'='ws_fast_lane')
SELECT count(*) AS rows, max(captured_at) AS newest_captured, min(captured_at) AS oldest_captured_in_window,
 (SELECT captured_at FROM r ORDER BY id DESC LIMIT 1) AS captured_of_highest_id, max(id) AS max_id, now() AS at
FROM r
