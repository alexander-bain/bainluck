-- INERT REVIEW MATERIAL: NOT ADMITTED; no caller exists for this packet.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '500ms';
EXPLAIN (FORMAT JSON)
SELECT
    COUNT(*) AS total_resolved,
    COUNT(fo.calibration_probability) AS has_cal_prob,
    COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL
                     AND fm.commence_time IS NOT NULL) AS needs_cal_with_commence,
    COUNT(*) FILTER (WHERE fo.calibration_probability IS NULL
                     AND fm.commence_time IS NULL) AS needs_cal_without_commence,
    AVG(ABS(fo.calibration_probability - fo.opening_probability))
        FILTER (WHERE fo.calibration_probability IS NOT NULL) AS avg_price_shift
FROM futures_outcomes fo
JOIN futures_markets fm ON fo.market_id = fm.id
WHERE fm.status = 'resolved'
  AND fo.opening_probability IS NOT NULL
  AND fo.opening_probability > 0 AND fo.opening_probability < 1;
ROLLBACK;
