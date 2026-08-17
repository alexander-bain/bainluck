"""CAL-P056 (#1852): the backward repair's judgment, tested where it lives.

The rule this suite is built to (CAL-P055's ratified doctrine): a double that
cannot express the predicate never certified it. So nothing here executes the
PostgreSQL fragments against SQLite — ``COUNT(*) FILTER (WHERE ...)`` and
``INTERVAL`` are not SQLite grammar, and a suite that "passed" by rewriting them
would be certifying a different query than the one that ships. The SQL was
adjudicated against PRODUCTION PostgreSQL through the read-only ``db-query`` rail
on 2026-08-14, with the shipping constants imported and interpolated verbatim;
the numbers are in the CAL-P056 report. What IS tested here is every decision the
rail makes, which is pure and therefore testable exactly as it runs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
    REPAIRABLE_SOURCE,
    RETENTION_BAND_SQL,
    RETRACTION_SOURCE,
    WRITING_VERDICTS,
    classify_leg,
    classify_market,
)
from app.utils.kalshi_retention import AT_RISK_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS
from app.utils.resolution_authority import (
    AUTHORITATIVE_SOURCES,
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
    KNOWN_SOURCES,
    OVERWRITABLE_WINNER_SOURCES,
    authority_tier,
    calibration_truth_class,
    is_calibration_truth_eligible,
    is_downgrade,
)

FINALIZED = "finalized"


class TestClassifyLeg:
    """One leg, one verdict — the unit of repair is the leg, never the market."""

    def test_venue_said_no_confirms_our_loss(self):
        assert (
            classify_leg(False, REPAIRABLE_SOURCE, FINALIZED, "no") == "confirmed_loss"
        )

    def test_venue_said_yes_restores_the_winner(self):
        assert (
            classify_leg(False, REPAIRABLE_SOURCE, FINALIZED, "yes")
            == "restore_winner"
        )

    @pytest.mark.parametrize("result", ["scalar", "", "  ", "SCALAR", None])
    def test_unmappable_result_retracts_the_fabricated_loss(self, result):
        assert (
            classify_leg(False, REPAIRABLE_SOURCE, FINALIZED, result)
            == "retract_fabricated"
        )

    @pytest.mark.parametrize("status", ["closed", "active", "inactive", None, ""])
    def test_a_status_that_carries_no_result_retracts_too(self, status):
        # MEASURED (kalshi_market_status): only determined/finalized carry a
        # result, and `closed` is precisely the terminal state that does not.
        assert (
            classify_leg(False, REPAIRABLE_SOURCE, status, "no")
            == "retract_fabricated"
        )

    def test_a_win_the_venue_never_declared_is_named_not_excused(self):
        assert (
            classify_leg(True, REPAIRABLE_SOURCE, FINALIZED, "scalar")
            == "unsupported_winner"
        )
        assert "unsupported_winner" not in WRITING_VERDICTS

    def test_leg_absent_from_the_venue_is_never_written(self):
        verdict = classify_leg(
            False, REPAIRABLE_SOURCE, FINALIZED, "no", present_at_venue=False
        )
        assert verdict == "not_at_venue"
        assert verdict not in WRITING_VERDICTS

    @pytest.mark.parametrize(
        "foreign", sorted(AUTHORITATIVE_SOURCES - {REPAIRABLE_SOURCE})
    )
    def test_another_rails_tier3_cohort_is_left_alone(self, foreign):
        assert (
            classify_leg(False, foreign, FINALIZED, "scalar") == "foreign_authority"
        )

    @pytest.mark.parametrize("weak", [None, "clean_resolution", "pass2_loser"])
    def test_a_leg_with_no_fabricated_badge_is_not_this_rails_problem(self, weak):
        assert classify_leg(False, weak, FINALIZED, "scalar") == "not_repairable"

    def test_the_live_specimen_splits_150_correct_from_2_fabricated(self):
        """KXPGAR1LEAD-COPC26, probed live 2026-08-14: 152 finalized legs,
        result no x150 / scalar x2 / yes x0. A per-MARKET repair would have
        rewritten 150 true rows to fix 2; this is why the unit is the leg."""
        venue = [{"status": FINALIZED, "result": "no"}] * 150 + [
            {"status": FINALIZED, "result": "scalar"}
        ] * 2
        verdicts = [
            classify_leg(False, REPAIRABLE_SOURCE, m["status"], m["result"])
            for m in venue
        ]
        assert verdicts.count("confirmed_loss") == 150
        assert verdicts.count("retract_fabricated") == 2
        assert sum(1 for v in verdicts if v in WRITING_VERDICTS) == 2


class TestClassifyMarket:
    def test_a_failed_lookup_is_unknown_never_absent(self):
        verdict, _ = classify_market(None, age_days=1.0)
        assert verdict == "unknown"

    def test_empty_past_the_measured_bound_is_a_declared_exclusion(self):
        verdict, detail = classify_market(
            [], age_days=PROVABLY_PURGED_AGE_DAYS + 0.5
        )
        assert verdict == "purged_declared_exclusion"
        assert detail["purge_bound_days"] == PROVABLY_PURGED_AGE_DAYS

    def test_empty_inside_retention_is_a_different_fact(self):
        # gotcha #53: the same empty 200 means two different things, and folding
        # them together hides a live upstream defect behind a known one.
        verdict, _ = classify_market([], age_days=PROVABLY_PURGED_AGE_DAYS - 0.5)
        assert verdict == "unexplained_absence"

    def test_the_boundary_is_derived_from_the_measured_constant(self):
        """Tight on BOTH sides of the bound, so the split moves if and only if a
        re-probe moves the constant — never because someone typed a day count."""
        assert (
            classify_market([], age_days=PROVABLY_PURGED_AGE_DAYS)[0]
            == "purged_declared_exclusion"
        )
        assert (
            classify_market([], age_days=PROVABLY_PURGED_AGE_DAYS - 0.01)[0]
            == "unexplained_absence"
        )

    def test_unknown_age_never_claims_purged(self):
        assert classify_market([], age_days=None)[0] == "unexplained_absence"

    def test_two_winners_on_a_mutex_field_fails_closed(self):
        venue = [
            {"ticker": "A", "status": FINALIZED, "result": "yes"},
            {"ticker": "B", "status": FINALIZED, "result": "yes"},
            {"ticker": "C", "status": FINALIZED, "result": "no"},
        ]
        verdict, detail = classify_market(venue, 3.0, mutually_exclusive=True)
        assert verdict == "contradictory_venue"
        assert detail["yes_count"] == 2

    def test_two_winners_on_an_independent_field_is_legitimate(self):
        venue = [
            {"ticker": "A", "status": FINALIZED, "result": "yes"},
            {"ticker": "B", "status": FINALIZED, "result": "yes"},
        ]
        verdict, detail = classify_market(venue, 3.0, mutually_exclusive=False)
        assert verdict == "answered"
        assert detail["venue_yes_legs"] == 2

    def test_an_all_no_answer_is_answered_not_an_exclusion(self):
        venue = [{"ticker": "A", "status": FINALIZED, "result": "no"}] * 4
        verdict, detail = classify_market(venue, 3.0)
        assert verdict == "answered"
        assert detail["venue_yes_legs"] == 0


class TestRetractionSourceIsClassified:
    """The retraction has to behave like a retraction, not like a grade."""

    def test_it_is_a_known_source(self):
        assert RETRACTION_SOURCE in KNOWN_SOURCES

    def test_it_can_never_grade_the_published_curve(self):
        assert not is_calibration_truth_eligible(RETRACTION_SOURCE)
        assert RETRACTION_SOURCE not in CALIBRATION_TRUTH_ELIGIBLE_SOURCES
        assert calibration_truth_class(RETRACTION_SOURCE) == "structural_void"

    def test_it_sits_below_the_badge_it_replaces(self):
        assert authority_tier(RETRACTION_SOURCE) < authority_tier(REPAIRABLE_SOURCE)

    def test_a_real_venue_result_overwrites_it_again(self):
        # The retraction must be reversible BY EVIDENCE: the ordinary graders
        # guard on AUTHORITATIVE_SOURCES, and this is not one of them.
        assert RETRACTION_SOURCE not in AUTHORITATIVE_SOURCES
        assert not is_downgrade(RETRACTION_SOURCE, REPAIRABLE_SOURCE)

    def test_writing_it_over_api_settlement_is_a_downgrade_by_the_ladder(self):
        # Stated, not hidden: this IS the exception, and it is exercised in
        # exactly one module. If the ladder ever stops calling it a downgrade,
        # that is a change to the ladder and this test should fail loudly.
        assert is_downgrade(REPAIRABLE_SOURCE, RETRACTION_SOURCE)

    def test_a_price_derived_crowner_may_not_supersede_it(self):
        assert RETRACTION_SOURCE not in OVERWRITABLE_WINNER_SOURCES


class TestSqlContracts:
    """The fragments are single-sourced, so the census and the repair cannot
    drift from each other. Adjudicated against production PostgreSQL, not here."""

    def test_the_population_excludes_single_leg_markets(self):
        assert "COUNT(*) >= 2" in POPULATION_HAVING_SQL

    def test_the_population_requires_zero_winners_and_a_full_api_badge(self):
        assert "COUNT(*) FILTER (WHERE fo.is_winner) = 0" in POPULATION_HAVING_SQL
        assert "'api_settlement'" in POPULATION_HAVING_SQL

    def test_the_retention_bands_are_the_measured_constants_not_literals(self):
        assert f"INTERVAL '{PROVABLY_PURGED_AGE_DAYS} days'" in RETENTION_BAND_SQL
        assert f"INTERVAL '{AT_RISK_AGE_DAYS} days'" in RETENTION_BAND_SQL

    def test_no_hand_rolled_day_count_in_the_repair_sql(self):
        """Gotcha #35: a predicate cannot consume a range written in prose, and
        three recovery rails were written by people who cited the gotcha and
        still typed a number. Any INTERVAL '<n> days' in the shipping SQL must
        be one of the measured constants."""
        src = Path(__file__).resolve().parents[1] / (
            "app/tasks/repair_kalshi_fabricated_loss.py"
        )
        text_ = src.read_text()
        found = {int(m) for m in re.findall(r"INTERVAL '(\d+) days'", text_)}
        assert found <= {AT_RISK_AGE_DAYS, PROVABLY_PURGED_AGE_DAYS}, found


class TestRailRegistration:
    """The catalog docstring and the registry must name the same repairs — the
    'add it HERE in the same commit' note alone has already failed twice."""

    def test_both_new_repairs_are_registered_and_documented(self):
        from app.routes import admin_repairs

        for name in ("kalshi-fabricated-loss-census", "kalshi-fabricated-loss"):
            assert name in admin_repairs._REPAIRS
            assert name in (admin_repairs.__doc__ or "")

    def test_the_census_entry_points_at_a_never_writing_callable(self):
        from app.routes import admin_repairs

        module, fn = admin_repairs._REPAIRS["kalshi-fabricated-loss-census"]
        assert fn == "census"
        assert module == "app.tasks.repair_kalshi_fabricated_loss"


class TestLiveVenueSpecimens:
    """Real venue answers, captured 2026-08-14 from four markets this database
    had recorded as all-losers, replayed through the SHIPPING mapper.

    These are not invented shapes. Each ticker was selected by running the
    shipping work-selection SQL against production PostgreSQL and then asking
    Kalshi what it actually declared. Between them they exercise every verdict
    that matters, and two of the four turn out to be entirely CORRECT as stored —
    which is the argument for a per-leg repair, made by data rather than by
    assertion.
    """

    SPECIMENS = (
        # ticker, mutex, expected leg verdicts (assuming every stored leg is an
        # api_settlement loss, which is what the population predicate guarantees)
        ("KXUSLGAME-26JUL24BIRNEW", True, {"retract_fabricated": 3}),
        ("KXARGPREMDIVSPREAD-26JUL28BANCAS", False, {"confirmed_loss": 5}),
        (
            "KXRDDT-26JULDAU",
            False,
            {"restore_winner": 3, "confirmed_loss": 7},
        ),
        (
            "KXPGAR1LEAD-COPC26",
            True,
            {"confirmed_loss": 150, "retract_fabricated": 2},
        ),
    )

    @staticmethod
    def _venue():
        import json

        path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "kalshi_fabricated_loss_specimens_p056.json"
        )
        return json.loads(path.read_text())

    @pytest.mark.parametrize("ticker,mutex,expected", SPECIMENS)
    def test_the_mapper_reproduces_the_live_answer(self, ticker, mutex, expected):
        from collections import Counter

        venue = self._venue()[ticker]
        verdict, _ = classify_market(venue, age_days=6.0, mutually_exclusive=mutex)
        assert verdict == "answered"

        got = Counter(
            classify_leg(False, REPAIRABLE_SOURCE, m["status"], m["result"])
            for m in venue
        )
        assert dict(got) == expected

    def test_the_all_loser_shape_is_not_the_defect(self):
        """Across these four markets, 162 of 170 stored losses are CORRECT — the
        venue really did say no. A repair judging by market shape would have
        rewritten all 162 to fix the 8 that are wrong. One whole specimen
        (KXARGPREMDIVSPREAD) needs no write at all."""
        from collections import Counter

        venue = self._venue()
        totals: Counter = Counter()
        untouched = 0
        for ticker, _mutex, _ in self.SPECIMENS:
            got = Counter(
                classify_leg(False, REPAIRABLE_SOURCE, m["status"], m["result"])
                for m in venue[ticker]
            )
            totals += got
            if not any(v in WRITING_VERDICTS for v in got):
                untouched += 1

        assert totals["confirmed_loss"] == 162
        assert sum(totals[v] for v in WRITING_VERDICTS) == 8
        assert sum(totals.values()) == 170
        assert untouched == 1

    def test_a_scalar_settlement_is_the_dominant_fabrication(self):
        venue = self._venue()
        scalar = sum(
            1
            for legs in venue.values()
            for m in legs
            if str(m["result"]).lower() == "scalar"
        )
        assert scalar == 5  # 3 USL legs + 2 PGA legs


class TestApplyDiscipline:
    def test_the_write_cap_is_a_module_constant_not_a_parameter(self):
        import inspect

        from app.tasks import repair_kalshi_fabricated_loss as mod

        assert isinstance(mod.APPLY_MARKET_CAP, int)
        assert "apply_market_cap" not in inspect.signature(mod.repair).parameters

    def test_only_two_verdicts_can_ever_write(self):
        assert WRITING_VERDICTS == {"restore_winner", "retract_fabricated"}

    def test_the_repair_writes_no_prices(self):
        from pathlib import Path as _P

        src = (
            _P(__file__).resolve().parents[1]
            / "app/tasks/repair_kalshi_fabricated_loss.py"
        ).read_text()
        for price_col in (
            "calibration_probability",
            "current_probability",
            "opening_probability",
        ):
            assert f"SET {price_col}" not in src
            assert f"{price_col} =" not in src
