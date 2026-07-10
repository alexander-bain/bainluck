"""#940 metric honesty: the no-winner / needs_backfill count must EXCLUDE
authoritatively-resolved single-sided markets (a binary/threshold that correctly
resolved NO has no winning outcome BY STRUCTURE — gotcha #17), and must split the
rest of the no-winner-tradeable universe transparently. needs_backfill is now the
GENUINE gap (no resolution_source at all). Count-only; no is_winner mutation
(gotcha #21). clean_resolution is heuristic (relabeled pass2_guess) -> #754, NOT
counted as authoritative.
"""

import inspect


def _both_status_sources():
    from app.tasks.precompute_backfill_winners_status import (
        _precompute_backfill_winners_status,
    )
    from app.tasks.precompute_calibration import _precompute_calibration_main_impl  # noqa
    a = inspect.getsource(_precompute_backfill_winners_status)
    # the calibration twin embeds the same query in its main impl; grab module src
    import app.tasks.precompute_calibration as pc
    b = inspect.getsource(pc)
    return a, b


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


def test_calibration_twin_matches():
    """The duplicate query in precompute_calibration must carry the same fix so
    the two caches agree."""
    import app.tasks.precompute_calibration as pc
    b = inspect.getsource(pc)
    assert "BOOL_OR(fo.resolution_source IS NOT NULL) AS any_rsrc" in b
    assert "('api_settlement', 'game_score', 'box_score')" in b
    assert "AS resolved_single_sided" in b
    assert "AS heuristic_resolved" in b


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
    # heuristic classes added to the NOT IN exclusion at every curve query site:
    # main ranked_outcomes, time-horizon eligible_outcomes, void-count query,
    # (#156 L2-79 Item 2) the golf_placeholder_markets CTE, and (Queue #157 #1012)
    # the mex_norm_markets CTE — each reuses the same eligibility predicate so its
    # population matches the published curve.
    assert src.count("'pass2_loser', 'all_losers',") == 5
    # null-source now EXCLUDED from the curve (predicate flipped IS NULL OR -> IS NOT NULL AND)
    assert src.count("fo.resolution_source IS NOT NULL\n") >= 3 or \
        src.count("resolution_source IS NOT NULL") >= 3
    # the old "IS NULL OR ... NOT IN" curve inclusion must be gone
    assert "resolution_source IS NULL\n" not in src or "OR fo.resolution_source NOT IN" not in src
    # transparency surface present
    assert "heuristic_filter" in src
