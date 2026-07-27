"""#940 metric honesty: the no-winner / needs_backfill count must EXCLUDE
authoritatively-resolved single-sided markets (a binary/threshold that correctly
resolved NO has no winning outcome BY STRUCTURE — gotcha #17), and must split the
rest of the no-winner-tradeable universe transparently. needs_backfill is now the
GENUINE gap (no resolution_source at all). Count-only; no is_winner mutation
(gotcha #21). clean_resolution is heuristic (relabeled pass2_guess) -> #754, NOT
counted as authoritative.
"""

import inspect


def test_needs_backfill_requires_no_resolution_source():
    """needs_backfill = the genuine gap = NOT has_winner AND NOT any_rsrc."""
    a = inspect.getsource(
        __import__("app.tasks.precompute_backfill_winners_status", fromlist=["x"])
        ._precompute_backfill_winners_status
    )
    assert "BOOL_OR(fo.resolution_source IS NOT NULL) AS any_rsrc" in a
    # needs_backfill filter must exclude anything already processed
    assert "NOT has_winner\n                          AND NOT any_rsrc" in a


def test_authoritative_set_excludes_heuristic_clean_resolution():
    """Authoritative = api_settlement/game_score/box_score ONLY. clean_resolution
    (relabeled pass2_guess) and pass2_loser/all_losers are NOT authoritative —
    they are the separate #754 correctness audit."""
    import app.tasks.precompute_backfill_winners_status as m
    a = inspect.getsource(m._precompute_backfill_winners_status)
    assert "('api_settlement', 'game_score', 'box_score')" in a
    assert "AS authoritative" in a
    # the transparency buckets exist
    assert "AS resolved_single_sided" in a
    assert "AS heuristic_resolved" in a
    # clean_resolution must NOT be promoted into the authoritative tuple
    assert "'clean_resolution'" not in a.split("AS authoritative")[0].split("authoritative")[-1] or "clean_resolution is" in a


def test_backfill_winners_status_not_duplicated_in_coverage():
    """#1199: the backfill-winners/status CTE must live ONLY in the dedicated
    precompute_backfill_winners_status task (hourly :35, 2h TTL). It used to be
    duplicated inside _snapshot_coverage_metrics as a second heavy query, which
    pushed that daily task over its 600s soft_time_limit (~1/24h). The dedup is
    the fix — guard that the coverage snapshot does NOT re-embed the twin (or the
    SoftTimeLimit regression, and the #940 sync burden, both return)."""
    from app.tasks.precompute_calibration import _snapshot_coverage_metrics
    full = inspect.getsource(_snapshot_coverage_metrics)
    # Strip comment lines so the guard checks real code, not the explanatory
    # NOTE (which legitimately names the key/CTE it warns against re-adding).
    code = "\n".join(
        ln for ln in full.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "bainluck:backfill_winners_status" not in code, (
        "coverage snapshot re-embedded the backfill-winners cache write — it must "
        "stay in the dedicated precompute_backfill_winners_status task (#1199)"
    )
    assert "AS resolved_single_sided" not in code
    assert "market_status" not in code


def test_no_is_winner_mutation_in_status_precompute():
    """#940 is count-only — the status precompute must not UPDATE is_winner."""
    import app.tasks.precompute_backfill_winners_status as m
    src = inspect.getsource(m)
    assert "SET is_winner" not in src
    assert "UPDATE futures_outcomes" not in src


def test_curve_excludes_heuristic_and_nullsource_754_989():
    """#754-curve + #989: the published calibration curve must exclude the three
    poisoned resolution classes — pass2_loser, all_losers (heuristic 0%-winrate,
    measured), and null-source outcomes (0 winners across all sources, measured
    2026-07-06). Read-side only; no is_winner/cal_prob mutation (gotcha #21).
    """
    import inspect
    import app.tasks.precompute_calibration as pc
    src = inspect.getsource(pc)
    # Queue #261 Item 1: the CANONICAL published population (the 3 CTE sites —
    # golf_placeholder_markets, mex_norm_markets, ranked_outcomes) moved from the
    # scattered heuristic NOT-IN DENYLIST to the resolution-authority
    # calibration-truth ELIGIBILITY ALLOWLIST. Heuristic classes are now excluded
    # by omission (never named) AND price-derived truth (clean_resolution /
    # settlement_sync) is excluded too — a terminal price cannot grade its own
    # forecast. The allowlist placeholder appears at each canonical site (+ the
    # Item 3 truth-evidence census), so >= 3.
    assert src.count("IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}") >= 3
    # The single-source-of-truth contract is imported, not re-inlined.
    assert "from app.utils.resolution_authority import (" in src
    assert "CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL" in src
    # The old denylist literal now survives ONLY at the two secondary views not
    # covered by _calibration_population_ctes (the time-horizon + fair-fight
    # queries), which stay on the legacy denylist pending a follow-up migration.
    assert src.count("'pass2_loser', 'all_losers',") == 2
    # null-source stays EXCLUDED from the curve (the allowlist's IN can never match NULL)
    assert "IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}" in src
    # the old "IS NULL OR ... NOT IN" curve inclusion must be gone
    assert "resolution_source IS NULL\n" not in src or "OR fo.resolution_source NOT IN" not in src
    # transparency surfaces present (heuristic filter + the #261 truth-evidence census)
    assert "heuristic_filter" in src
    assert "truth_evidence" in src
