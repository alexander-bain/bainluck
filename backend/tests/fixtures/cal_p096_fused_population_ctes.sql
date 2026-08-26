market_info AS (
                SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
                    fm.commence_time,
                    COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
                    fm.mutually_exclusive,
                    fm.market_type,
                    fm.llm_league,
                    -- Queue 299 rung 4: the shape classifier's PERSISTED
                    -- exclusivity evidence (app.utils.market_shape semantics v2,
                    -- Queue #260). These three carry the only proof a market is
                    -- a single-winner exhaustive partition; the
                    -- ``mutually_exclusive`` column above defaults to True and
                    -- is set for Yes/No claims and duels alike, so it is not
                    -- evidence and no longer gates normalization.
                    fm.market_metadata->'shape'->>'exhaustive' AS shape_exhaustive,
                    fm.market_metadata->'shape'->>'expected_winners' AS shape_expected_winners,
                    fm.market_metadata->'shape'->>'outcome_relation' AS shape_relation
                FROM futures_markets fm
                WHERE fm.status = 'resolved'
                  
                  -- #994 symmetric exclusion: DataGolf markets whose full field
                  -- the historical API genuinely can't return (event not found)
                  -- are dropped ENTIRELY — winners AND losers — so participation
                  -- can never be one-sidedly assumed. Recovery flags these; the
                  -- residual is expected to be ~0 (golf history never ages out).
                  AND NOT COALESCE(
                      (fm.market_metadata->>'datagolf_recovery_residual')::boolean,
                      false)
            ),
            -- Queue 299: ONE per-market structural scan feeding every shape and
            -- result-authority rung. Counts are over ALL outcomes of the market
            -- (never the eligibility-filtered subset) — the same basis the
            -- malformed-binary rule always used, so the shape and winner
            -- cardinality reflect the market as captured, not as published.
            -- Replaces the three separate full scans that previously computed
            -- malformed_binaries / esports_multi_bundles / mex_win_counts.
            market_result_shape AS (
                SELECT fo.market_id,
                    mi.category,
                    mi.market_type,
                    COUNT(*) AS n_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS win_count,
                    -- Queue 299 rung 2: captured draw/no-result authority.
                    COUNT(*) FILTER (
                        WHERE lower(btrim(fo.name)) IN ('abandoned', 'draw', 'drawn', 'no result', 'no-result', 'tie', 'tied')
                    ) AS draw_member_count
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                GROUP BY fo.market_id, mi.category, mi.market_type
            ),
            -- L2-79 Item 1: malformed 2-outcome mex binaries (winner count != 1).
            malformed_binaries AS (
                SELECT mrs.market_id, mrs.win_count
                FROM market_result_shape mrs
                JOIN market_info mi ON mi.market_id = mrs.market_id
                WHERE mi.mutually_exclusive = true
                  AND mrs.n_outcomes = 2
                  AND mrs.win_count <> 1
            ),
            -- Queue 299 rung 1: markets that graded NOBODY a winner. is_winner
            -- has a False default, so an all-loser market is UNKNOWN truth (an
            -- omitted draw graded as two losses, an orphan half, or a market
            -- nothing ever graded) — not a set of confident losses. Generalizes
            -- the malformed-binary both-false leg to every shape and size.
            no_winner_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.n_outcomes >= 2 AND mrs.win_count = 0
            ),
            -- Queue 299 rung 2: draw-capable duels with no draw member. The
            -- category answers only "can this contest be drawn?" (sport rules,
            -- exactly as the events-curve soccer rule does); the SHAPE test is
            -- evidence-based, so ladders, Yes/No claims and genuinely 2-way
            -- questions are untouched, as are duels that DO carry a draw.
            draw_authority_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.category IN ('cricket', 'soccer')
                  AND mrs.market_type = 'duel'
                  AND mrs.n_outcomes = 2
                  AND mrs.draw_member_count = 0
            ),
            -- Queue 299 rung 3: a declared partition that captured <=1 member.
            -- Field-shape only — a standalone Yes/No claim with one outcome is a
            -- complete, scoreable prediction and is deliberately NOT caught.
            orphan_partition_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.market_type = 'field' AND mrs.n_outcomes <= 1
            ),
            -- Queue 299 rung 4b: the category-independent non-exclusive bundle
            -- (>=3 outcomes, >=2 winners). MEASUREMENT ONLY outside esports —
            -- see NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT for why a blanket
            -- exclusion is not shipped (it would delete 81% of hockey and 47%
            -- of tennis, both well-calibrated).
            nonexclusive_bundle_markets AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.n_outcomes >= 3 AND mrs.win_count >= 2
            ),
            -- Queue #159 (#1010): esports malformed-MULTI "match bundle" markets —
            -- the >=3-outcome sibling of malformed_binaries and the exclusion-side
            -- complement of #157's counter-class guard. Polymarket flattens a whole
            -- match (cumulative Total-Kills Over ladders per game, per-game winners,
            -- first-blood props) into one non-partition market; because the Over
            -- rungs are cumulative, a high-kill game legitimately resolves many YES
            -- (gotcha #17), so the market has >=2 winners and its prices neither
            -- sum to 1 (multiple partitions mashed — can't be normalized) nor
            -- bucket as a clean prediction (OPS-557: n=93,629, winrate 0.395 vs cp
            -- 0.487 = +9.2pp, avg per-market cp-sum 17.9). Counts ALL outcomes,
            -- mirroring malformed_binaries. Read-side only (gotcha #21) — the
            -- many-YES ladder grading is CORRECT, so exclude, never re-grade.
            -- Queue 299: re-expressed over the shared market_result_shape scan
            -- (identical membership) so the esports EXCLUSION and the
            -- category-independent bundle CENSUS derive from one structural
            -- test rather than two copies of it.
            esports_multi_bundles AS (
                SELECT mrs.market_id
                FROM market_result_shape mrs
                WHERE mrs.category = 'esports'
                  AND mrs.n_outcomes >= 3
                  AND mrs.win_count >= 2
            ),
            -- L2-79 Item 2: golf FIELD/winner one-sided-ask placeholder markets —
            -- mutually-exclusive golf markets with >=2 outcomes in the >=0.80 band
            -- (structurally impossible for genuine mex probabilities). Same
            -- eligibility predicate as the main outcome scan so the band count
            -- reflects the published population.
            golf_placeholder_markets AS (
                SELECT fo.market_id
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                WHERE mi.category = 'golf'
                  AND mi.mutually_exclusive = true
                  AND mi.event_id IS NULL
                  AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.8
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Only sources whose winner is established INDEPENDENTLY of the
                  -- market's own price may grade a published forecast; guess,
                  -- structural-void, price-derived (clean_resolution /
                  -- settlement_sync) and unknown sources fail closed. Single
                  -- source of truth = resolution_authority.
                  AND fo.resolution_source IN ('api_settlement', 'box_score', 'box_score_bound', 'clob_authoritative', 'clob_field_repair', 'clob_never_graded', 'clob_ordinal', 'datagolf_matchup', 'datagolf_played_lost', 'datagolf_settlement', 'date_passed', 'game_score', 'leaderboard', 'poly_total_score', 'scoring_plays')
                  -- Queue #267 (C44 #1): evidence-backed liquidity, not the volume
                  -- proxy. A never-bid/never-traded Kalshi placeholder is not a real
                  -- band member, so it must not inflate the >=2 over-subscription
                  -- count; a bid-bearing volume=0 outcome IS real and must count.
                  AND (mi.source <> 'kalshi' OR EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0)))
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 2
            ),
            -- Queue #157 (#1012): multi-candidate normalization support.
            -- mex_win_counts: winner count over ALL outcomes of each mex market
            -- (the structure test — genuine partitions have exactly 1 winner;
            -- multi-winner = ladder/independent, zero-winner = void).
            -- #254: also trust market_type='field' (the shape classifier's
            -- ">2 outcomes, one winner" signal) — 65K field markets have the
            -- mutually_exclusive flag UNSET and were escaping this gate raw
            -- (sum ~4.56). The win_count=1 / >=3 / sum>1.15 guards below keep a
            -- mis-shaped or multi-winner field from being normalized anyway.
            -- Queue 299: the winner cardinality now comes from the shared
            -- market_result_shape scan (same count over ALL outcomes), and the
            -- ``mutually_exclusive = true OR market_type = 'field'`` admission
            -- test is REPLACED by proved exclusivity in mex_field_candidates
            -- below — the column defaults to True and is set for Yes/No claims
            -- and duels alike, so it never was evidence of a partition.
            -- Queue #262 Item 1: split the old single mex_norm_markets into a
            -- structural CANDIDATE detection (terminal price) + a price-expression
            -- DIVISOR, so a horizon can normalize on its snapshot yet still measure
            -- completeness against the FULL terminal field.
            --
            -- mex_field_candidates: markets that are genuine partition FIELDS — a
            -- STRUCTURAL roster identity independent of the horizon (mex/field,
            -- exactly one winner, >=3 terminal-eligible outcomes). Carries the full
            -- terminal-eligible member count so horizon completeness can require
            -- every member to be present.
            --
            -- Queue #263 Item 1: the cp-SUM > threshold gate is a PRICE-STATE
            -- decision, not a roster identity, so it MUST be evaluated on the price
            -- expression the surface finalizes on — NOT the terminal probability.
            -- It moved out of candidate detection and into ``normalized`` below,
            -- gated on ``mnm_cp_sum`` (the mex_field_divisor sum over COALESCE(fo.calibration_probability, fo.opening_probability)).
            -- This makes field qualification horizon-honest: a terminal-low/horizon-
            -- high field qualifies at the horizon, a terminal-high/horizon-low field
            -- does not. On the headline path COALESCE(fo.calibration_probability, fo.opening_probability) == terminal cp, so
            -- mnm_cp_sum == the old terminal SUM and the qualified set + count equal
            -- the old mex_norm_markets membership + COUNT exactly.
            mex_field_candidates AS (
                SELECT fo.market_id,
                    COUNT(*) AS terminal_eligible_n
                FROM futures_outcomes fo
                JOIN market_info mi ON mi.market_id = fo.market_id
                JOIN market_result_shape mrs ON mrs.market_id = fo.market_id
                -- Queue 299 rung 4: PROVED exclusivity only. The persisted shape
                -- classifier must positively assert an exhaustive single-winner
                -- field with an exclusive outcome relation; a default-true
                -- ``mutually_exclusive`` flag, an ``unknown`` relation and a
                -- cumulative-threshold ladder (gotcha #17 co-winners) are all
                -- refused. Mirrors market_exclusivity_is_proved().
                WHERE mi.market_type = 'field'
                  AND mi.shape_exhaustive = 'true'
                  AND mi.shape_expected_winners = '1'
                  AND mi.shape_relation IN ('competitors', 'exclusive_ranges')
                  AND mrs.win_count = 1
                  AND fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist),
                  -- identical to the ranked_outcomes / golf-placeholder scans so
                  -- candidate detection matches the published population.
                  AND fo.resolution_source IN ('api_settlement', 'box_score', 'box_score_bound', 'clob_authoritative', 'clob_field_repair', 'clob_never_graded', 'clob_ordinal', 'datagolf_matchup', 'datagolf_played_lost', 'datagolf_settlement', 'date_passed', 'game_score', 'leaderboard', 'poly_total_score', 'scoring_plays')
                  -- Queue #267 (C44 #1): the field ROSTER counts evidence-bearing
                  -- members only (matching the is_liquid survivor gate), so a
                  -- bid-bearing volume=0 member is part of the partition and a
                  -- never-bid/never-traded Kalshi phantom is not — instead of the
                  -- volume proxy that dropped real bid-bearing volume=0 members.
                  AND (mi.source <> 'kalshi' OR EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0)))
                GROUP BY fo.market_id
                HAVING COUNT(*) >= 3
            ),
            -- mex_field_divisor: per-market normalization divisor = sum of the
            -- CURVE PRICE over the eligible members PRESENT at this price
            -- expression (all terminal members on the headline; only members with
            -- a horizon snapshot when curve_price_join joins horizon_price). On the
            -- headline path cp_sum equals the old mex_norm_markets cp_sum exactly.
            mex_field_divisor AS (
                SELECT fo.market_id,
                    SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS cp_sum,
                    COUNT(*) AS present_eligible_n
                FROM futures_outcomes fo
                JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                JOIN market_info mi ON mi.market_id = fo.market_id
                
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  AND fo.resolution_source IN ('api_settlement', 'box_score', 'box_score_bound', 'clob_authoritative', 'clob_field_repair', 'clob_never_graded', 'clob_ordinal', 'datagolf_matchup', 'datagolf_played_lost', 'datagolf_settlement', 'date_passed', 'game_score', 'leaderboard', 'poly_total_score', 'scoring_plays')
                  -- Queue #267 (C44 #1): the divisor sums the SAME evidence-bearing
                  -- roster as mex_field_candidates / the is_liquid survivors, so for
                  -- a COMPLETE field the divisor equals the survivor sum and the
                  -- normalized partition still sums to ~1.0 (a phantom's price can
                  -- never inflate the divisor). Replaces the volume proxy.
                  AND (mi.source <> 'kalshi' OR EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0)))
                GROUP BY fo.market_id
            ),
            group_sizes AS (
                SELECT group_id, source, COUNT(*) AS group_size
                FROM market_info
                WHERE group_id IS NOT NULL
                GROUP BY group_id, source
            ),
            event_sizes AS (
                SELECT event_id, source, COUNT(*) AS event_size
                FROM market_info
                WHERE event_id IS NOT NULL
                GROUP BY event_id, source
            ),
            virtual_market AS (
                SELECT
                    mi.market_id, mi.source, mi.category, mi.event_id,
                    CASE WHEN gs.group_size >= 3
                         THEN 'g:' || mi.group_id
                         WHEN es.event_size >= 3
                         THEN 'e:' || mi.event_id::text
                         ELSE 'm:' || mi.market_id::text
                    END AS vm_id,
                    COALESCE(gs.group_size >= 3, false)
                      OR COALESCE(es.event_size >= 3, false) AS is_grouped,
                    mi.mutually_exclusive,
                    mi.market_type,
                    mi.llm_league
                FROM market_info mi
                LEFT JOIN group_sizes gs
                  ON gs.group_id = mi.group_id AND gs.source = mi.source
                LEFT JOIN event_sizes es
                  ON es.event_id = mi.event_id AND es.source = mi.source
            ),
            vm_stats AS (
                SELECT
                    vm.vm_id, vm.source, vm.category, vm.is_grouped,
                    vm.mutually_exclusive,
                    COUNT(DISTINCT vm.market_id) AS market_count,
                    COUNT(*) AS total_outcomes,
                    COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
                    COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                                      AND fo.opening_probability > 0
                                      AND fo.opening_probability < 1) AS eligible
                FROM virtual_market vm
                JOIN futures_outcomes fo ON fo.market_id = vm.market_id
                GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
                         vm.mutually_exclusive
            ),
            clean_vms AS (
                SELECT * FROM vm_stats
                WHERE eligible >= 1
                  AND has_winner >= 1
            ),
            ranked_outcomes AS MATERIALIZED (
                SELECT
                    -- Queue #157 (#1012): raw curve price + the per-market
                    -- normalization divisor. The actual normalization (cp /
                    -- mnm.cp_sum) is DEFERRED to the ``normalized`` CTE below,
                    -- because it is gated on FIELD COMPLETENESS (Queue #257 Item
                    -- 1) which can only be aggregated once these per-outcome
                    -- exclusion flags exist. Carry market_id so completeness can
                    -- be computed per market.
                    COALESCE(fo.calibration_probability, fo.opening_probability) AS raw_cp,
                    -- Queue #262 Item 1: candidate membership (structural, terminal)
                    -- vs divisor (price-expression). is_mex_normalized keys on the
                    -- candidate so an incomplete horizon field is dropped WHOLE even
                    -- when <3 members are present at the snapshot.
                    mfc.market_id AS candidate_market_id,
                    mfd.cp_sum AS mnm_cp_sum,
                    fo.market_id AS market_id,
                    -- Queue #259 Item 2: carry outcome identity + per-market shape
                    -- so the cohort sweep selects the SAME final rows (row identity)
                    -- with its cohort keys, instead of re-deriving the population.
                    fo.id AS outcome_id,
                    fo.name AS outcome_name,
                    vm.market_type AS market_type,
                    vm.llm_league AS llm_league,
                    fo.is_winner AS is_winner,
                    (fo.calibration_probability IS NOT NULL
                     AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved,
                    cv.vm_id, cv.source, cv.category,
                    cv.eligible, cv.is_grouped,
                    (cv.is_grouped OR cv.eligible >= 3) AS is_multi,
                    -- #940 phase-1: never-bid/never-traded Kalshi placeholders are
                    -- excluded from the published set (read-side only, gotcha #21).
                    (vm.source <> 'kalshi' OR EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0))) AS is_liquid,
                    (vm.source = 'polymarket'
     AND COALESCE(fo.calibration_probability, fo.opening_probability) >= 0.45
     AND COALESCE(fo.calibration_probability, fo.opening_probability) <= 0.55
     AND NOT EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0))) AS is_poly_placeholder,
                    -- Queue #220/221 Item 3: all-bands poly never-traded flag (for
                    -- the exclusion-symmetry census; does NOT gate the curve).
                    (vm.source = 'polymarket'
     AND NOT EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id
          AND (fos.yes_bid > 0 OR fos.last_price > 0))) AS is_poly_never_traded,
                    -- L2-79 Item 1: malformed 2-outcome mex binary (winner count
                    -- 0 = void, or 2 = impossible). mb.win_count carries which.
                    (mb.market_id IS NOT NULL) AS is_malformed_binary,
                    mb.win_count AS malformed_win_count,
                    -- Queue #159 (#1010): esports match-bundle exclusion flag.
                    (emb.market_id IS NOT NULL) AS is_esports_bundle,
                    -- Queue 299 rung 1: the market graded NOBODY — UNKNOWN truth,
                    -- not a set of losses (is_winner's default is False).
                    (nwm.market_id IS NOT NULL) AS is_no_winner_market,
                    -- Queue 299 rung 2: draw-capable duel with no draw member.
                    (dam.market_id IS NOT NULL) AS is_draw_authority_missing,
                    -- Queue 299 rung 3: a 'field' that captured <=1 member.
                    (opm.market_id IS NOT NULL) AS is_orphan_partition,
                    -- Queue 299 rung 4b: category-independent non-exclusive
                    -- bundle. CENSUS ONLY — this flag does NOT gate ``deduped``
                    -- outside esports (which keeps its own measured exclusion).
                    (nbm.market_id IS NOT NULL) AS is_nonexclusive_bundle,
                    -- L2-79 Item 2: golf one-sided-ask placeholder — this outcome
                    -- sits in the >=0.80 band of an over-subscribed golf mex market.
                    (gpm.market_id IS NOT NULL
                     AND COALESCE(fo.calibration_probability, fo.opening_probability)
                         >= 0.8) AS is_golf_placeholder,
                    -- Queue #186 (#941, corrects #167): Kalshi player-prop
                    -- threshold "<subject>: N+" OVER captures. EXCLUDED when
                    -- (A) category='hockey' (NHL goal-family is corrupt at every
                    -- price band — illiquid degenerate capture, resolution sane)
                    -- or (B) the curve price is in the degenerate settlement-
                    -- collapse band (>= 0.90), which resolves 0.11–0.48 across
                    -- every series (gotcha #14/#21). Queue #263 Item 1: the band
                    -- reads COALESCE(fo.calibration_probability, fo.opening_probability) (terminal COALESCE(cp, opening) on the
                    -- headline, the horizon snapshot on a horizon) so each horizon
                    -- classifies on its OWN price, not the terminal probability.
                    -- The 2026-07-13 verify disproved #167's no-live-bid keep:
                    -- real-bid rows are corrupt too (scorer + non-scorer both cp
                    -- 0.995). Curve price, not bid, is the honest discriminator;
                    -- below-band liquid series stay (SAVE all possible). Read-side
                    -- only, no regrade (sign-flip premise disproven).
                    (cv.source = 'kalshi'
     AND fo.name ~ '^.+:[[:space:]]*[0-9]+[+][[:space:]]*$'
     AND ((cv.category = 'hockey'
            AND COALESCE(fo.calibration_probability, fo.opening_probability)
                >= 0.5)
          OR COALESCE(fo.calibration_probability, fo.opening_probability)
             >= 0.9)) AS is_kalshi_prop_threshold,
                    -- Queue #183 Item 4 (#182 twin): weather wide-spread fabricated
                    -- midpoint. A wide Kalshi weather book (ask-bid >= 0.50) with no
                    -- trade has no real price discovery at its midpoint. Weather-gated
                    -- (tech miscalibration is genuine per #182 census — kept).
                    (vm.source = 'kalshi'
     AND cv.category = 'weather'
     AND fo.current_yes_bid IS NOT NULL AND fo.current_yes_ask IS NOT NULL
     AND (fo.current_yes_ask - fo.current_yes_bid) >= 0.5
     AND NOT EXISTS (
        SELECT 1 FROM futures_odds_snapshots fos
        WHERE fos.outcome_id = fo.id AND fos.last_price > 0)) AS is_weather_wide_spread,
                    -- Queue 300D Item 1 (C126 P1). Distance from 50% ALONE is not
                    -- a total order: complementary binary sides are routinely
                    -- equidistant (0.40 / 0.60), and with no secondary key
                    -- PostgreSQL may return either tied row across plans or
                    -- rebuilds. ``deduped`` publishes only ``rn = 1``, so the
                    -- observation identity, its winner label and its bucket could
                    -- all move with no source-data or methodology change — and a
                    -- staged execution can never be proved equivalent to an
                    -- oracle that is itself unstable.
                    --
                    -- Alex's 2026-08-03 ruling is the tie AUTHORITY: after
                    -- distance from 50%, break exact ties by the immutable
                    -- canonical outcome ID. Deliberately NOT a Yes/No or
                    -- favourite/underdog preference — any side preference would be
                    -- a product decision about which half of a book we believe,
                    -- and this is only a determinism rule.
                    ROW_NUMBER() OVER (
                        PARTITION BY cv.vm_id
                        ORDER BY ABS(fo.opening_probability - 0.5), fo.id
                    ) AS rn,
                    -- The one-time delta instrument. RANK over the DISTANCE ONLY
                    -- is 1 for every row tied at the minimum, so ``rn = 2 AND
                    -- rn_distance_rank = 1`` marks exactly those questions whose
                    -- representative the new authority had to choose. Its ORDER BY
                    -- is a prefix of ``rn``'s, so PostgreSQL satisfies both windows
                    -- from one sort and this costs no extra pass over the heaviest
                    -- CTE in the product.
                    RANK() OVER (
                        PARTITION BY cv.vm_id
                        ORDER BY ABS(fo.opening_probability - 0.5)
                    ) AS rn_distance_rank
                FROM futures_outcomes fo
                JOIN virtual_market vm ON vm.market_id = fo.market_id
                JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
                
                LEFT JOIN malformed_binaries mb ON mb.market_id = fo.market_id
                LEFT JOIN esports_multi_bundles emb ON emb.market_id = fo.market_id
                LEFT JOIN no_winner_markets nwm ON nwm.market_id = fo.market_id
                LEFT JOIN draw_authority_markets dam ON dam.market_id = fo.market_id
                LEFT JOIN orphan_partition_markets opm ON opm.market_id = fo.market_id
                LEFT JOIN nonexclusive_bundle_markets nbm ON nbm.market_id = fo.market_id
                LEFT JOIN golf_placeholder_markets gpm ON gpm.market_id = fo.market_id
                LEFT JOIN mex_field_candidates mfc ON mfc.market_id = fo.market_id
                LEFT JOIN mex_field_divisor mfd ON mfd.market_id = fo.market_id
                WHERE fo.opening_probability IS NOT NULL
                  AND fo.opening_probability > 0 AND fo.opening_probability < 1
                  -- Queue #261 Item 1: calibration-truth eligibility (allowlist).
                  -- Replaces the scattered NOT-IN denylist with the single
                  -- resolution_authority contract: price-derived (clean_resolution
                  -- / settlement_sync) can no longer grade its own forecast, all
                  -- guess-family is excluded, and unknown sources fail closed.
                  AND fo.resolution_source IN ('api_settlement', 'box_score', 'box_score_bound', 'clob_authoritative', 'clob_field_repair', 'clob_never_graded', 'clob_ordinal', 'datagolf_matchup', 'datagolf_played_lost', 'datagolf_settlement', 'date_passed', 'game_score', 'leaderboard', 'poly_total_score', 'scoring_plays')
                  -- Queue #267 (C44 #1): NO standalone volume gate here. The Kalshi
                  -- evidence predicate (is_liquid = KALSHI_LIQUIDITY_EXISTS) is
                  -- computed as a per-outcome flag above and filtered in ``deduped``
                  -- (WHERE ro.is_liquid). Keeping ALL candidates in ranked_outcomes
                  -- is what makes kalshi_included / kalshi_excluded honest: a
                  -- never-bid/never-traded phantom is COUNTED as excluded here, not
                  -- silently removed at eligibility; a bid-bearing volume=0 row now
                  -- survives is_liquid and reaches the curve (the C44 #1 fix).
            ),
            -- Queue #257 Item 1: FIELD-COMPLETENESS aggregation. For each
            -- normalization CANDIDATE market (mex/field, single winner over all
            -- outcomes, >=3 eligible, sum > threshold), count eligible members,
            -- survivors (those passing EVERY per-outcome published exclusion), and
            -- whether the winner survived. Queue #262 Item 1: eligible_n is the FULL
            -- terminal-eligible member count (mfc.terminal_eligible_n), NOT the
            -- present-outcome COUNT — so a horizon field with a member missing at
            -- the snapshot (present < terminal) is INCOMPLETE and dropped whole. On
            -- the headline path present == terminal, so eligible_n equals the old
            -- COUNT(*) over ranked_outcomes exactly and behavior is unchanged.
            field_completeness AS (
                SELECT ro.market_id,
                    MAX(mfc.terminal_eligible_n) AS eligible_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                          -- Queue 299: the new rungs are published per-outcome
                          -- exclusions too, so a field that loses a member to
                          -- one of them is PARTIAL and must be dropped whole
                          -- rather than normalized over its survivors.
                          AND NOT ro.is_no_winner_market
                          AND NOT ro.is_draw_authority_missing
                          AND NOT ro.is_orphan_partition
                    ) AS survivor_n,
                    COUNT(*) FILTER (
                        WHERE ro.is_winner
                          AND ro.is_liquid AND NOT ro.is_poly_placeholder
                          AND NOT ro.is_malformed_binary
                          AND NOT ro.is_esports_bundle
                          AND NOT ro.is_golf_placeholder
                          AND NOT ro.is_kalshi_prop_threshold
                          AND NOT ro.is_weather_wide_spread
                          AND NOT ro.is_no_winner_market
                          AND NOT ro.is_draw_authority_missing
                          AND NOT ro.is_orphan_partition
                    ) AS survivor_win_n
                FROM ranked_outcomes ro
                JOIN mex_field_candidates mfc ON mfc.market_id = ro.market_id
                GROUP BY ro.market_id
            ),
            -- Queue #257 Item 1: apply normalization ONLY to COMPLETE candidate
            -- fields (survivor_n = eligible_n AND winner survived AND >=3), so a
            -- published field sums to ~1.0 over its survivors. A candidate whose
            -- field is PARTIAL (a member was excluded) is flagged
            -- is_field_incomplete and dropped from the curve by ``deduped`` —
            -- never normalized over survivors. mnm.cp_sum equals the survivor sum
            -- exactly when complete, so cp / mnm_cp_sum normalizes to ~1.
            -- Queue #263 Item 1: a market is a genuine normalization FIELD when it
            -- is a structural partition candidate (mex_field_candidates) AND its
            -- curve-price sum clears the field threshold ON THE PRICE EXPRESSION
            -- (mnm_cp_sum = mex_field_divisor's SUM over COALESCE(fo.calibration_probability, fo.opening_probability): terminal cp
            -- on the headline, the horizon snapshot on a horizon). Moving the sum
            -- gate off terminal candidate detection makes qualification horizon-
            -- honest. On the headline mnm_cp_sum == the old terminal SUM, so
            -- ``is_field`` reduces to the old candidate membership exactly and a
            -- structural-but-below-threshold market keeps flowing to the multi pool
            -- (neither normalized nor dropped) exactly as before.
            normalized AS (
                SELECT ro.*,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > 1.15
                     AND fc.survivor_n = fc.eligible_n
                     AND fc.survivor_win_n = 1
                     AND fc.survivor_n >= 3) AS is_mex_normalized,
                    (ro.candidate_market_id IS NOT NULL
                     AND ro.mnm_cp_sum > 1.15
                     AND NOT (fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3)) AS is_field_incomplete,
                    CASE WHEN ro.candidate_market_id IS NOT NULL
                              AND ro.mnm_cp_sum > 1.15
                              AND fc.survivor_n = fc.eligible_n
                              AND fc.survivor_win_n = 1
                              AND fc.survivor_n >= 3
                         THEN ro.raw_cp / ro.mnm_cp_sum
                         ELSE ro.raw_cp
                    END AS adj_opening_probability
                FROM ranked_outcomes ro
                LEFT JOIN field_completeness fc ON fc.market_id = ro.market_id
            ),
            -- Queue #259 Item 1: mode-price detection is a PLACEHOLDER heuristic
            -- for the non-partition multi pool; a COMPLETE normalized field
            -- (is_mex_normalized) is a genuine partition summing to ~1.0, so its
            -- prices must NOT drive (nor be removed by) mode detection — else a
            -- uniform field (10 members @ 0.10) would be wiped. Incomplete fields
            -- are dropped anyway; exclude both so only publishable rows vote.
            --
            -- #2098 / RULING 125 — the mode is a fact about ONE SOURCE's legs,
            -- so it may only delete THAT source's legs.
            --
            -- ``vm_id`` is source-blind on its ``e:`` arm (``'e:' || event_id``,
            -- while ``event_sizes`` counts per ``(event_id, source)``), so two
            -- sources carrying >=3 resolved markets on one event share a vm_id.
            -- Every neighbouring aggregate is source-scoped deliberately —
            -- ``vm_stats`` GROUPs BY ``(vm_id, source)``, ``clean_vms`` JOINs on
            -- both — and this one was not: it grouped on ``vm_id`` alone and the
            -- join below matched on ``vm_id`` alone. A mode detected among one
            -- source's legs therefore DELETED the other source's legs sitting at
            -- the same price. Measured whole-domain (CAL-P087,
            -- ``artifacts/cal-p087/ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json``):
            -- 35 rows over 2 vm_ids; on ``e:14887630`` FOUR Polymarket legs
            -- deleted TWENTY-THREE Kalshi legs.
            --
            -- Ruling 125: a join that can DELETE a row must carry every
            -- dimension that identifies the row. Note this is three lines, not
            -- the two the staged spec named — ``mode_prices`` must also PROJECT
            -- ``source``, or the new join conjunct cannot be written.
            --
            -- Guarded by ``tests/integration/
            -- test_calibration_mode_price_source_scope_pg.py`` against a real
            -- Postgres, two-armed: it also executes the REVERTED SQL and asserts
            -- the suppression comes back, so green means red-first was proved
            -- rather than that nothing objected.
            mode_prices AS (
                SELECT vm_id, source, adj_opening_probability AS mode_price
                FROM normalized
                WHERE is_multi AND eligible >= 3 AND is_liquid
                  AND NOT is_mex_normalized AND NOT is_field_incomplete
                GROUP BY vm_id, source, adj_opening_probability, eligible
                HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
            ),
            deduped AS (
                SELECT ro.* FROM normalized ro
                LEFT JOIN mode_prices mp
                  ON mp.vm_id = ro.vm_id
                  AND mp.source = ro.source
                  AND mp.mode_price = ro.adj_opening_probability
                WHERE ro.is_liquid AND NOT ro.is_poly_placeholder
                    AND NOT ro.is_malformed_binary
                    AND NOT ro.is_esports_bundle
                    AND NOT ro.is_golf_placeholder
                    AND NOT ro.is_kalshi_prop_threshold
                    AND NOT ro.is_weather_wide_spread
                    -- Queue 299 rungs 1-3 (#1012): result authority before
                    -- shape. A market that graded nobody, a draw-capable duel
                    -- with no draw member, and a 'field' with <=1 captured
                    -- member are all UNKNOWN truth — excluded, never published
                    -- as confident losses and never re-graded (gotcha #21).
                    AND NOT ro.is_no_winner_market
                    AND NOT ro.is_draw_authority_missing
                    AND NOT ro.is_orphan_partition
                    AND NOT ro.is_field_incomplete
                    AND
                    CASE
                        -- Queue #259 Item 1 INVARIANT FIX: a COMPLETE normalized
                        -- field is a partition that sums to ~1.0 over EXACTLY its
                        -- survivor members (field_completeness proved every eligible
                        -- member survived every per-outcome exclusion). The mode /
                        -- extreme-tail filters below are placeholder heuristics for
                        -- the NON-partition multi pool; applying them here would drop
                        -- a member (a 0.001-normalized tail, or a uniform field's
                        -- modal price) and publish <1.0 — the exact defect C14 found
                        -- (0.99/0.20/0.001 -> tail dropped -> ~99.9%). Publish every
                        -- member of a complete field so the partition still sums to 1.
                        WHEN ro.is_mex_normalized THEN true
                        WHEN ro.is_multi
                            THEN ro.adj_opening_probability > 0.005
                             AND ro.adj_opening_probability < 0.98
                             AND mp.vm_id IS NULL
                        ELSE ro.rn = 1
                    END
            )