"""CAL-P120 — guards for the ``odds_api_bookmaker`` cell fold.

The instrument these guards protect exists because the CAL-P112/114/117/118
family cannot reach this source at all: all three of those fold the
``futures_markets``-rooted population chain, and ``futures_markets`` holds no
``odds_api_bookmaker`` rows. This source is aggregated in
``backfill_winners._precompute_bookmaker_calibration()`` and cached in Redis
before the producer ever sees it.

Two claims in the CAL-P120 write-up are load-bearing, and both are pinned here
rather than described:

1. **The fold reproduces the published cell exactly.** ``ece_of`` applied to the
   real published NBA buckets must return the board's own 5.18 pp / +1.03 pp. If
   the arithmetic ever drifts, every number in §6g is wrong and this goes red.
2. **Chunk boundaries cannot change a row's value**, because every grouping in
   the statement is per-event and the chunking is on ``commence_time``, which
   partitions events. So chunk results ADD. ``merge_buckets`` is the place that
   assumption is cashed, and it is tested on split-then-merge.

The third thing worth a guard is the failure behaviour: a chunk that times out
or truncates must SPLIT, never retry and never be dropped (gotcha #53 — a
silently short answer reads as a small class, which on this board would read as
"this cell is fine").
"""

from __future__ import annotations

import importlib.util
import math
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "calibration_bookmaker_cell_fold",
    pathlib.Path(__file__).resolve().parents[1] / "scripts"
    / "calibration_bookmaker_cell_fold.py",
)
fold_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fold_mod)


# The published odds_api_bookmaker/basketball_nba cell, copied from the live
# /api/calibration payload at 2026-08-29T00:36:47Z. These are the numbers the
# board's rank-5 row is made of, so they are the right thing to pin.
PUBLISHED_NBA = {
    0: {"n": 170, "winners": 0, "sum_prob": 14.0039},
    1: {"n": 754, "winners": 38, "sum_prob": 113.0659},
    2: {"n": 638, "winners": 87, "sum_prob": 159.8917},
    3: {"n": 1066, "winners": 339, "sum_prob": 371.2116},
    4: {"n": 1274, "winners": 649, "sum_prob": 571.5774},
    5: {"n": 1533, "winners": 773, "sum_prob": 858.4873},
    6: {"n": 1530, "winners": 1037, "sum_prob": 995.0621},
    7: {"n": 1568, "winners": 1241, "sum_prob": 1177.2659},
    8: {"n": 1277, "winners": 1052, "sum_prob": 1088.6844},
    9: {"n": 376, "winners": 375, "sum_prob": 346.4478},
}


class TestReproducesThePublishedCell:
    def test_ece_and_gap_match_the_board(self):
        n, ece, gap = fold_mod.ece_of(PUBLISHED_NBA)
        assert n == 10186
        assert round(ece, 2) == 5.18
        assert round(gap, 2) == 1.03

    def test_empty_cell_is_zero_not_a_crash(self):
        assert fold_mod.ece_of({}) == (0, 0.0, 0.0)

    def test_a_perfectly_calibrated_cell_scores_zero(self):
        perfect = {3: {"n": 100, "winners": 35, "sum_prob": 35.0}}
        n, ece, gap = fold_mod.ece_of(perfect)
        assert (n, round(ece, 6), round(gap, 6)) == (100, 0.0, 0.0)

    def test_ece_is_absolute_but_gap_is_signed(self):
        """Two bins erring in opposite directions cancel in the gap and do not
        cancel in the ECE. A rule that quietly used the signed error would read
        a badly-calibrated cell as a clean one."""
        both_ways = {
            2: {"n": 100, "winners": 15, "sum_prob": 25.0},   # over-predicted
            7: {"n": 100, "winners": 85, "sum_prob": 75.0},   # under-predicted
        }
        n, ece, gap = fold_mod.ece_of(both_ways)
        assert round(gap, 6) == 0.0
        assert round(ece, 2) == 10.0

    def test_ece_is_weighted_by_bin_population(self):
        """A tiny wild bin must not outvote a large clean one."""
        lopsided = {
            0: {"n": 1, "winners": 1, "sum_prob": 0.05},      # 95pp error, n=1
            5: {"n": 999, "winners": 550, "sum_prob": 549.9},  # ~0pp, n=999
        }
        _, ece, _ = fold_mod.ece_of(lopsided)
        assert ece < 0.2


class TestChunksAdd:
    """Chunking is on commence_time and every grouping is per-event, so the sum
    over chunks IS the whole fold. If merge_buckets ever stopped adding, the
    instrument would silently under-count exactly the way a dropped chunk does.
    """

    def test_split_then_merge_equals_the_whole(self):
        whole = [{"bucket_idx": b, "n": v["n"], "winners": v["winners"],
                  "sum_prob": v["sum_prob"]} for b, v in PUBLISHED_NBA.items()]
        halves = []
        for row in whole:
            halves.append({**row, "n": row["n"] // 2,
                           "winners": row["winners"] // 2,
                           "sum_prob": row["sum_prob"] / 2})
            halves.append({**row, "n": row["n"] - row["n"] // 2,
                           "winners": row["winners"] - row["winners"] // 2,
                           "sum_prob": row["sum_prob"] / 2})
        merged = fold_mod.merge_buckets(halves)
        assert {b: v["n"] for b, v in merged.items()} == \
               {b: v["n"] for b, v in PUBLISHED_NBA.items()}
        assert fold_mod.ece_of(merged)[0] == 10186

    def test_the_same_bucket_from_two_chunks_is_summed_not_overwritten(self):
        merged = fold_mod.merge_buckets([
            {"bucket_idx": 4, "n": 10, "winners": 4, "sum_prob": 4.5},
            {"bucket_idx": 4, "n": 7, "winners": 3, "sum_prob": 3.2},
        ])
        assert merged[4] == {"n": 17, "winners": 7, "sum_prob": pytest.approx(7.7)}


class TestFailureBehaviour:
    """A chunk that cannot be answered must be narrowed, never retried and never
    dropped. Both failure modes are the same bug — the window is too wide — and
    only one of them is loud."""

    def _driver(self, monkeypatch, fail_until_days):
        calls = []

        def fake(sql, limit=fold_mod.ROW_CAP):
            lo = sql.split("e.commence_time >= '")[1][:10]
            hi = sql.split("AND e.commence_time < '")[1][:10]
            calls.append((lo, hi))
            from datetime import date
            width = (date.fromisoformat(hi) - date.fromisoformat(lo)).days
            if width > fail_until_days:
                raise fold_mod.QueryTimeout("statement_timeout")
            return [{"bucket_idx": 1, "n": width, "winners": 0, "sum_prob": 0.0}]

        monkeypatch.setattr(fold_mod, "db_query", fake)
        return calls

    def test_a_timing_out_window_is_split_and_every_day_is_still_counted(
            self, monkeypatch):
        from datetime import date
        calls = self._driver(monkeypatch, fail_until_days=8)
        rows = fold_mod.collect("basketball_nba", date(2026, 1, 1), date(2026, 2, 2), "bucket")
        # 32 days, answerable only at <= 8 — nothing may be lost to the splitting.
        assert sum(r["n"] for r in rows) == 32
        assert any((date.fromisoformat(h) - date.fromisoformat(l)).days > 8
                   for l, h in calls), "the wide window should have been attempted"

    def test_truncation_splits_the_same_way_as_a_timeout(self, monkeypatch):
        from datetime import date
        seen = []

        def fake(sql, limit=fold_mod.ROW_CAP):
            lo = sql.split("e.commence_time >= '")[1][:10]
            hi = sql.split("AND e.commence_time < '")[1][:10]
            width = (date.fromisoformat(hi) - date.fromisoformat(lo)).days
            seen.append(width)
            if width > 4:
                raise fold_mod.Truncated("1000 rows")
            return [{"bucket_idx": 0, "n": width, "winners": 0, "sum_prob": 0.0}]

        monkeypatch.setattr(fold_mod, "db_query", fake)
        rows = fold_mod.collect("x", date(2026, 1, 1), date(2026, 1, 17), "bucket")
        assert sum(r["n"] for r in rows) == 16
        assert max(seen) > 4 and min(seen) <= 4

    def test_an_unanswerable_single_day_raises_instead_of_returning_short(
            self, monkeypatch):
        """The one outcome that must never happen: an empty answer that reads as
        a small class."""
        from datetime import date

        def always_timeout(sql, limit=fold_mod.ROW_CAP):
            raise fold_mod.QueryTimeout("statement_timeout")

        monkeypatch.setattr(fold_mod, "db_query", always_timeout)
        with pytest.raises(RuntimeError, match="cannot narrow further"):
            fold_mod.collect("x", date(2026, 1, 1), date(2026, 1, 3), "bucket")


class TestTheStatementItselfCarriesTheClaims:
    """The write-up's exactness argument rests on properties of the SQL text, so
    the SQL text is asserted rather than trusted."""

    def test_the_sport_key_and_both_time_bounds_are_scoped(self):
        sql = fold_mod._BODY.format(sport_key="basketball_nba",
                                    lo="2026-01-01", hi="2026-02-01")
        assert "s.key = 'basketball_nba'" in sql
        assert "e.commence_time >= '2026-01-01'" in sql
        assert "e.commence_time < '2026-02-01'" in sql

    def test_the_window_is_half_open_so_chunks_cannot_double_count(self):
        assert "e.commence_time >= '{lo}'" in fold_mod._BODY
        assert "e.commence_time < '{hi}'" in fold_mod._BODY

    def test_every_grouping_is_per_event(self):
        """This is the whole reason chunk boundaries are harmless here and are
        NOT harmless on the Polymarket rail, whose virtual_market test groups
        across markets."""
        assert "GROUP BY event_id" in fold_mod._TAIL_GAME
        assert "os.event_id = eb.event_id" in fold_mod._BODY
        assert "virtual_market" not in fold_mod._BODY

    def test_the_producers_own_eligibility_and_devig_are_carried_verbatim(self):
        b = fold_mod._BODY
        assert "e.status IN ('completed', 'closed')" in b
        assert "e.home_score != e.away_score" in b
        assert "os.captured_at < ee.commence_time" in b
        assert "ORDER BY os.captured_at DESC" in b and "LIMIT 1" in b
        assert "NULLIF(cl.home_win_probability::float + cl.away_win_probability::float, 0)" in b

    def test_the_published_price_filter_is_on_both_tails(self):
        for tail in (fold_mod._TAIL_BUCKET, fold_mod._TAIL_GAME):
            assert "prob > 0.01 AND prob < 0.99" in tail

    def test_the_bucket_tail_is_the_producers_ten_deciles(self):
        assert "LEAST(FLOOR(prob * 10)::int, 9)" in fold_mod._TAIL_BUCKET


class TestTheEffectiveSampleArithmetic:
    """The finding is a variance claim, so the variance arithmetic gets a guard.

    ``won`` is a function of ``event_id`` alone, so the intra-cluster
    correlation on the RESPONSE is exactly 1, and the design effect for a
    clustered mean, 1 + (m - 1) * rho, collapses to the cluster size m.
    """

    @staticmethod
    def se_pp(n):
        return 50.0 / math.sqrt(n)

    def test_design_effect_with_icc_one_is_the_cluster_size(self):
        m = 17.78
        assert 1 + (m - 1) * 1.0 == pytest.approx(m)

    def test_nba_falls_from_established_to_not_established(self):
        excess = 5.18 - 2.5
        assert round(excess / self.se_pp(10186), 1) == 5.4    # what the board prints
        assert round(excess / self.se_pp(573), 2) == 1.28     # per game
        assert excess / self.se_pp(573) < 2.0                 # SIGMA_GATE

    def test_the_p_half_conservatism_cannot_absorb_the_clustering(self):
        """The convention's docstring says a cell it clears is clear 'by at least
        the margin shown'. On this source that is false, and this pins by how
        much: the conservatism is ~1.2x and the deflation needed is ~4.2x."""
        conservatism = 0.4954 / 0.4190          # convention vs true-p SE, measured
        deflation = math.sqrt(10186 / 573)
        assert conservatism < 1.25
        assert deflation > 4.0
        assert deflation / conservatism > 3.0

    def test_all_six_cells_fall_below_the_gate_at_game_grain(self):
        # (published ECE, games) measured 2026-08-29; bar 2.5, gate 2.0
        cells = {
            "basketball_nba": (5.18, 573),
            "baseball_mlb_preseason": (8.24, 217),
            "icehockey_nhl": (3.89, 495),
            "basketball_wncaab": (6.05, 583),
            "basketball_wnba": (4.81, 300),
            "basketball_euroleague": (5.39, 162),
        }
        for name, (ece, games) in cells.items():
            sigma = (ece - 2.5) / self.se_pp(games)
            assert sigma < 2.0, f"{name} would still be established at {sigma:.2f} sigma"

    def test_the_point_estimate_is_not_what_moved(self):
        """Guards against the finding being misread as 'the cell is fine'. The
        ECE barely changes; only its significance does."""
        assert abs(5.32 - 5.18) < 0.2
        assert 5.32 > 2.5
