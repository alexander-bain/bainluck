WITH w AS (
 SELECT s.event_id, s.captured_at, s.home_win_probability AS v, s.game_state->>'poll_type' AS pt,
   lag(s.home_win_probability) OVER (PARTITION BY s.event_id ORDER BY s.captured_at) AS pv,
   e.commence_time, e.status
 FROM win_prob_snapshots s JOIN events e ON e.id=s.event_id
 WHERE s.source='kalshi' AND s.captured_at >= '2026-10-30 17:30:00+00' AND s.captured_at < '2026-10-30 18:30:00+00')
SELECT CASE WHEN captured_at < commence_time THEN 'pregame' ELSE 'after_start' END AS phase, COALESCE(pt,'(none)') AS writer,
 count(*) AS rows, count(*) FILTER (WHERE pv IS NOT NULL AND v=pv) AS unchanged, count(*) FILTER (WHERE pv IS NOT NULL AND v<>pv) AS moved, count(DISTINCT event_id) AS events
FROM w GROUP BY 1,2 ORDER BY 1,2
