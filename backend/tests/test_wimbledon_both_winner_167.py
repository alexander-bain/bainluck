"""Queue #167 Item 2 (#999): Women's Wimbledon two-winner grading fix.

Polymarket market 114157 "2026 Women's Wimbledon Winner" (a neg_risk,
mutually-exclusive single-champion market) resolved with TWO is_winner=true
outcomes: "Other" (current_probability 1.00) and "Linda Nosková" (0.9995), both
via clean_resolution. Authoritative Polymarket Gamma (event 139182) shows exactly
ONE market resolved YES — "Will Linda Nosková be the 2026 Women's Wimbledon
Winner?" (outcomePrices ['1','0'], umaResolutionStatus 'resolved'); every other
sub-market, including "Other", resolved NO. So this is a mis-grade, NOT an
intended won/reached-final pair.

Root cause: the clean_resolution pass (_backfill_polymarket_winners... price
path) sets is_winner = (current_probability >= 0.95) for a cleanly-resolved
Polymarket market with NO mutual-exclusivity single-winner guard. When a stale
neg_risk "Other"/catch-all quote is pinned near 1.0 (gotcha #19) it gets crowned
alongside the real champion.

Two-part fix (gotcha #21 — never guess a winner from a stale price):
  1. Prevention: clean_resolution never price-resolves a mutually-exclusive
     market with >1 near-certain (cp >= 0.95) outcome — those are deferred to
     authoritative Gamma settlement.
  2. Correction: the authoritative Gamma winner backfill (Phase 3) now also
     re-settles recent mutually-exclusive markets that were crowned with >1
     winner, so the envelope ends with exactly one champion. Recency-bounded to
     ~90 days because Gamma market data ages out (gotcha #35); older residual
     mis-grades are left for the curve-exclusion net.

Source-inspection tests (the established pattern for these SQL-embedded guards):
they pin the guard predicates in place so a refactor can't silently drop them.
"""

import inspect

import app.tasks.backfill_winners as backfill_winners


class TestCleanResolutionMexSingleWinnerGuard:
    def test_clean_resolution_defers_multi_winner_mex(self):
        # The price-based clean_resolution pass must refuse to crown >1
        # near-certain outcome in a mutually-exclusive market.
        src = inspect.getsource(backfill_winners)
        assert "cleanly_resolved AS (" in src
        # The mex guard: NOT (mutually_exclusive AND >1 outcome cp >= 0.95).
        assert "NOT (fm.mutually_exclusive" in src
        # The guard counts near-certain outcomes and requires more than one to
        # trip (the ">1 near-certain in a mex market" defer condition).
        assert ") > 1)" in src

    def test_group_by_carries_mutual_exclusive(self):
        # fm.mutually_exclusive must be a grouping column so the HAVING can
        # reference it directly.
        src = inspect.getsource(backfill_winners)
        assert "GROUP BY fm.id, fm.mutually_exclusive" in src


class TestPhase3ReSettlesMultiWinnerMex:
    def test_phase3_candidate_includes_multi_winner_mex(self):
        # The authoritative Gamma winner backfill must pull in mutually-exclusive
        # markets that were crowned with >1 winner so it can re-settle them.
        src = inspect.getsource(
            backfill_winners._backfill_polymarket_winners_from_api
        )
        assert "fm.mutually_exclusive" in src
        assert "SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) > 1" in src
        # Recency-bounded (gotcha #35 — Gamma market data ages out).
        assert "INTERVAL '90 days'" in src

    def test_phase3_stays_authoritative(self):
        # Phase 3 writes api_settlement from Gamma — it must never invent a winner
        # from a heuristic. Guardrail: the function still references the Gamma API.
        src = inspect.getsource(
            backfill_winners._backfill_polymarket_winners_from_api
        )
        assert "PolymarketAPIService" in src
        assert "api_settlement" in src
