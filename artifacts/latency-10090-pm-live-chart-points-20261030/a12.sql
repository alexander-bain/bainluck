SELECT s.event_id, s.source, count(*) AS rows, min(s.captured_at) AS first_cap, e.status, e.commence_time
FROM win_prob_snapshots s JOIN events e ON e.id=s.event_id
WHERE s.event_id IN (15331415, 15331477, 15335016, 15338302) AND s.source IN ('polymarket','kalshi')
GROUP BY 1,2,5,6 ORDER BY 1,2
