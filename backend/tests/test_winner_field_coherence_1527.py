"""CAL-P006 (#1527): a single-winner market must have exactly one winner.

Production held 214+ open soccer markets whose EVERY outcome — Home, Away *and*
Draw — was ``is_winner=true`` at ``current_probability=1.0``, a field summing to
300%, still being re-stamped daily. Verified in production 2026-08-07 on
Europa League market 55254886: three legs, all 1.0, all crowned
``clean_resolution``, ``last_updated`` that morning; and all 72 of each leg's
snapshots since first ingest (2026-07-13, ~2 years after the fixture) at exactly
1.000000.

Three links, each independently sufficient to have stopped it:

1. **Capture.** The Polymarket poller accepted an impossible field. Per-leg
   guards cannot catch it — ``_resolve_market_probability`` is permissive at the
   extremes on purpose — so the check has to be at field level.
2. **Grading.** ``_backfill_polymarket_winners`` grew the single-winner guard for
   the Women's Wimbledon two-winner bug (Queue #167/#999, see
   ``test_wimbledon_both_winner_167.py``). Its two siblings —
   ``_backfill_from_current_probability`` (ALL sources) and the Kalshi
   event-fallback — never did, and the class simply walked through them. This is
   drift between sites, which is why the rule now lives in ONE module.
3. **Detection.** ``_collapse_bywhen_ladder_winners`` repairs exactly this
   invariant violation but only for date ladders — it requires a winner whose
   name parses as a date, so a 1X2 is ``skipped_no_date`` by design.

NOTE on non-vacuity: a module-wide "is the guard present" assertion would have
PASSED before this fix, because the #167 sibling already contained the same
predicate elsewhere in the same file. The grader tests below therefore assert the
guard inside each grader's OWN SQL block.
"""

import inspect

import pytest

import app.tasks.backfill_winners as backfill_winners
import app.tasks.census_winner_fields as census_mod
import app.tasks.flow_sentinel as flow_sentinel
import app.tasks.polymarket as polymarket
from app.routes.admin_repairs import _REPAIRS
from app.tasks.census_winner_fields import classify_defect, summarize
from app.tasks.flow_sentinel import freshly_written_incoherent_fields
from app.utils.winner_field_coherence import (
    INCOHERENT_FIELD_HAVING_SQL,
    NEAR_CERTAIN_PROB,
    count_near_certain,
    field_is_incoherent,
    winners_are_incoherent,
)


def _block(src: str, start: str, end: str) -> str:
    """The source between two anchors — so a guard can be pinned to ONE site."""
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------
class TestFieldCoherenceRule:
    def test_the_production_shape_is_incoherent(self):
        # Europa League 55254886: Slavia Praha / Anderlecht / Draw, all 1.0.
        assert field_is_incoherent([1.0, 1.0, 1.0], mutually_exclusive=True)

    def test_a_settled_1x2_is_coherent(self):
        # What the same market SHOULD look like: exactly one certain leg.
        assert not field_is_incoherent([1.0, 0.0, 0.0], mutually_exclusive=True)

    def test_a_normal_pregame_field_is_coherent(self):
        assert not field_is_incoherent([0.45, 0.3, 0.25], mutually_exclusive=True)

    def test_non_mutex_fields_are_never_judged(self):
        # gotcha #23: independent binaries legitimately sum far past 100% — five
        # teams can each be ~certain to make the playoffs. Judging these would
        # suppress real markets, so mutual exclusivity gates the whole rule.
        assert not field_is_incoherent(
            [1.0, 1.0, 1.0, 0.99], mutually_exclusive=False
        )

    def test_single_leg_is_never_incoherent(self):
        # Nothing to contradict.
        assert not field_is_incoherent([1.0], mutually_exclusive=True)

    def test_none_probabilities_are_ignored_not_counted(self):
        assert count_near_certain([1.0, None, None]) == 1
        assert not field_is_incoherent([1.0, None, None], mutually_exclusive=True)

    @pytest.mark.parametrize(
        "probs,expected",
        [
            ([NEAR_CERTAIN_PROB, NEAR_CERTAIN_PROB], True),   # exactly at the bar
            ([NEAR_CERTAIN_PROB - 0.001, 1.0], False),        # just under
        ],
    )
    def test_the_bar_is_inclusive(self, probs, expected):
        assert field_is_incoherent(probs, mutually_exclusive=True) is expected

    def test_bar_matches_what_the_graders_crown_at(self):
        # The graders set is_winner = (current_probability >= 0.95). If the bar
        # here drifted from that, capture and grading would disagree about which
        # legs are "certain" — the exact drift that caused #1527.
        assert NEAR_CERTAIN_PROB == 0.95
        assert f">= {NEAR_CERTAIN_PROB}" in INCOHERENT_FIELD_HAVING_SQL

    def test_winner_count_rule(self):
        assert winners_are_incoherent(3, mutually_exclusive=True)
        assert not winners_are_incoherent(1, mutually_exclusive=True)
        assert not winners_are_incoherent(0, mutually_exclusive=True)
        # Non-mutex markets can legitimately have many winners.
        assert not winners_are_incoherent(3, mutually_exclusive=False)


# ---------------------------------------------------------------------------
# Grading: all three price-crowners, each pinned inside its OWN block
# ---------------------------------------------------------------------------
class TestEveryPriceCrownerCarriesTheGuard:
    def test_backfill_from_current_probability_pass1(self):
        # THE bug: this pass runs over ALL sources and had no winner-count cap,
        # so it crowned every leg at >= 0.95. Pinned to its own block because the
        # module already contained the same predicate for a different grader —
        # a module-wide assertion would have passed before the fix.
        src = inspect.getsource(backfill_winners)
        block = _block(src, "# Pass 1: Clean resolution", "RETURNING fo.is_winner")
        assert "INCOHERENT_FIELD_HAVING_SQL" in block
        assert "GROUP BY fm.id, fm.mutually_exclusive" in block

    def test_kalshi_event_fallback_pass(self):
        src = inspect.getsource(backfill_winners)
        block = _block(src, "WITH market_check AS (", "RETURNING fo.is_winner")
        assert "INCOHERENT_FIELD_HAVING_SQL" in block
        assert "GROUP BY fm.id, fm.mutually_exclusive" in block

    def test_the_shared_fragment_is_the_167_predicate(self):
        # The fragment the two sites interpolate must BE the guard, not a
        # placeholder — otherwise the tests above pin an empty string in place.
        assert "NOT (fm.mutually_exclusive" in INCOHERENT_FIELD_HAVING_SQL
        assert "> 1)" in INCOHERENT_FIELD_HAVING_SQL
        assert "current_probability" in INCOHERENT_FIELD_HAVING_SQL

    def test_polymarket_pass_still_carries_the_167_guard(self):
        # Regression on the sibling that already had it — CAL-P006 must not have
        # traded one site's guard for another's.
        src = inspect.getsource(backfill_winners)
        block = _block(src, "WITH cleanly_resolved AS (", "RETURNING fo.is_winner")
        assert "NOT (fm.mutually_exclusive" in block

    def test_all_three_use_the_shared_fragment(self):
        # One rule, three call sites: the shared SQL fragment must appear at least
        # twice (the two CAL-P006 sites; #167's is hand-written and predates it).
        src = inspect.getsource(backfill_winners)
        assert src.count("INCOHERENT_FIELD_HAVING_SQL") >= 3  # import + 2 uses


# ---------------------------------------------------------------------------
# Capture: refuse an impossible field before it is ever stored
# ---------------------------------------------------------------------------
class TestPollerRefusesIncoherentFields:
    def test_guard_runs_before_any_write(self):
        src = inspect.getsource(polymarket)
        guard = src.index("if field_is_incoherent(")
        # It must short-circuit BEFORE ranking and BEFORE the outcome upsert,
        # otherwise the impossible price is already stored.
        assert guard < src.index("outcome_data.sort(")
        assert guard < src.index("# Upsert outcomes with ranks")
        # ...and before the snapshot write, or the 1.0 field still lands in
        # price history even if the outcome row is spared.
        assert guard < src.index("# Create snapshot")

    def test_guard_skips_the_event_and_counts_it(self):
        src = inspect.getsource(polymarket)
        block = _block(src, "if field_is_incoherent(", "outcome_data.sort(")
        assert "continue" in block
        assert "incoherent_fields_skipped" in block

    def test_guard_is_gated_on_neg_risk(self):
        # negRisk IS the mutual-exclusivity signal (it is what populates
        # FuturesMarket.mutually_exclusive at ingest). Without this gate the
        # guard would suppress legitimate independent-binary fields.
        src = inspect.getsource(polymarket)
        block = _block(src, "if field_is_incoherent(", "outcome_data.sort(")
        assert "mutually_exclusive=bool(event.neg_risk)" in block
        assert "mutually_exclusive=event.neg_risk" in src  # the ingest mapping


# ---------------------------------------------------------------------------
# Census
# ---------------------------------------------------------------------------
class TestCensusClassification:
    def test_the_production_row_is_both_classes(self):
        assert classify_defect(winners=3, near_certain=3) == [
            "multi_winner",
            "incoherent_field",
        ]

    def test_capture_defect_before_grading_catches_up(self):
        # 55254930 in production: three legs at 1.0, none crowned yet.
        assert classify_defect(winners=0, near_certain=3) == ["incoherent_field"]

    def test_grading_defect_without_a_certain_field(self):
        assert classify_defect(winners=2, near_certain=1) == ["multi_winner"]

    def test_healthy_market_has_no_class(self):
        assert classify_defect(winners=1, near_certain=1) == []

    def test_summarize_counts_only_the_bogus_winners(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        rows = [
            {"winners": 3, "near_certain": 3, "llm_sport_category": "soccer",
             "last_written": now},
            {"winners": 2, "near_certain": 2, "llm_sport_category": "soccer",
             "last_written": now - timedelta(days=30)},
            {"winners": 0, "near_certain": 3, "llm_sport_category": None,
             "last_written": None},
        ]
        out = summarize(rows, fresh_cutoff=now - timedelta(hours=48))
        assert out["defect_markets"] == 3
        # 3 winners -> 2 bogus, 2 winners -> 1 bogus, 0 winners -> 0.
        assert out["bogus_winner_outcomes"] == 3
        assert out["by_class"] == {"multi_winner": 2, "incoherent_field": 3}
        assert out["by_category"]["soccer"] == 2
        assert out["by_category"]["(none)"] == 1
        # Only the row written inside the horizon counts as producer-live.
        assert out["written_recently"] == 1

    def test_scan_is_bounded(self):
        # #1527's own aggregate was cancelled by the statement timeout three
        # times; two more attempts died the same way staging this queue. The
        # census must bound the window and carry its own timeout.
        assert census_mod.MAX_SCAN >= census_mod.DEFAULT_SCAN
        src = inspect.getsource(census_mod)
        assert "SET LOCAL statement_timeout" in src
        # Bounded by a market-id WINDOW, not by a defect count.
        assert "LIMIT :scan" in src

    def test_census_never_writes(self):
        src = inspect.getsource(census_mod)
        for verb in ("UPDATE ", "INSERT ", "DELETE "):
            assert verb not in src.upper().replace("UPDATE FUTURES_OUTCOMES FO\n", "")

    def test_registered_on_the_repair_rail(self):
        assert _REPAIRS["winner-field-coherence"] == (
            "app.tasks.census_winner_fields",
            "census",
        )

    def test_census_signature_accepts_the_rail_params(self):
        # The dispatcher passes through only params the callable names.
        params = inspect.signature(census_mod.census).parameters
        for p in ("limit", "offset", "newest_first", "apply"):
            assert p in params


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------
class TestSentinelFailsOnlyOnLiveProduction:
    def test_fresh_write_is_a_failure(self):
        fresh = freshly_written_incoherent_fields(
            [{"market_id": 55254886, "written_recently": True, "winners": 3,
              "legs": 3, "near_certain": 3, "source": "polymarket",
              "category": "soccer", "name": "Europa League: Slavia vs Anderlecht",
              "field_sum": 3.0, "classes": ["multi_winner", "incoherent_field"],
              "last_written": "2026-08-07 13:05:52+00:00"}]
        )
        assert len(fresh) == 1
        assert fresh[0]["market_id"] == 55254886

    def test_standing_backlog_is_not_a_failure(self):
        # Repairing the existing population is an authority-gated write
        # (gotcha #21). Alarming on it nightly would make the flow permanently
        # RED for something no agent may fix — the cry-wolf the grid health
        # score was retired for.
        assert freshly_written_incoherent_fields(
            [{"market_id": 1, "written_recently": False, "winners": 3, "legs": 3}]
        ) == []

    def test_empty_and_missing_input_are_safe(self):
        assert freshly_written_incoherent_fields([]) == []
        assert freshly_written_incoherent_fields(None) == []

    def test_flow_is_registered_with_label_and_title(self):
        assert flow_sentinel._FLOW_AREA_LABELS["winner_field_coherence"] == (
            "area:calibration"
        )
        assert "winner_field_coherence" in flow_sentinel._FLOW_TITLES
        src = inspect.getsource(flow_sentinel._run_flow_sentinel)
        assert '("winner_field_coherence", _run_winner_field_coherence)' in src

    def test_zero_walked_is_unknown_not_pass(self):
        # An empty window is not evidence of health.
        src = inspect.getsource(flow_sentinel._run_winner_field_coherence)
        assert "if walked == 0:" in src
        assert "_unknown_flow" in src

    def test_measurement_failure_is_skipped_not_filed(self):
        src = inspect.getsource(flow_sentinel._run_winner_field_coherence)
        assert "ADMIN_TOKEN unset" in src
        assert "census dry-run failed" in src

    def test_it_measures_through_the_census_not_its_own_sql(self):
        # Guard and census must share ONE definition of the defect.
        src = inspect.getsource(flow_sentinel._run_winner_field_coherence)
        assert "/api/admin/repairs/winner-field-coherence" in src
        assert '"apply": "false"' in src
