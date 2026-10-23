-- INERT REVIEW MATERIAL: NOT ADMITTED; no caller exists for this packet.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '500ms';
EXPLAIN (FORMAT JSON)
SELECT
    COUNT(*) FILTER (WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1)) AS total_resolved,
    COUNT(fo.calibration_probability) FILTER (WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1)) AS has_cal_prob,
    COUNT(*) FILTER (WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1) AND fo.calibration_probability IS NULL
                     AND fm.commence_time IS NOT NULL) AS needs_cal_with_commence,
    COUNT(*) FILTER (WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1) AND fo.calibration_probability IS NULL
                     AND fm.commence_time IS NULL) AS needs_cal_without_commence,
    AVG(ABS(fo.calibration_probability - fo.opening_probability))
        FILTER (WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1) AND fo.calibration_probability IS NOT NULL) AS avg_price_shift,
    COUNT(*) FILTER (WHERE (fo.resolution_source IN ('binary_higher_wins', 'multi_max_prob', 'pass2_guess', 'pass3_threshold'))) AS guess_family_outcomes,
    COUNT(*) FILTER (WHERE fo.resolution_source = 'binary_higher_wins') AS gf_binary_higher_wins,
    COUNT(*) FILTER (WHERE fo.resolution_source = 'multi_max_prob') AS gf_multi_max_prob,
    COUNT(*) FILTER (WHERE fo.resolution_source = 'pass2_guess') AS gf_pass2_guess,
    COUNT(*) FILTER (WHERE fo.resolution_source = 'pass3_threshold') AS gf_pass3_threshold
FROM futures_outcomes fo
JOIN futures_markets fm ON fo.market_id = fm.id
WHERE (fm.status = 'resolved' AND fo.opening_probability IS NOT NULL AND fo.opening_probability > 0 AND fo.opening_probability < 1) OR (fo.resolution_source IN ('binary_higher_wins', 'multi_max_prob', 'pass2_guess', 'pass3_threshold'));
ROLLBACK;
