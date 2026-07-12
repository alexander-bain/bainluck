"""Queue #167 (#941 / #1054): curve-side Kalshi player-prop threshold
DEGENERATE-capture exclusion.

Kalshi player-prop markets are single-sided "Player: N+" OVER outcomes (points,
assists, goals, total bases, hits, HR, strikeouts, rebounds, blocks, ...). They
are polled near/after game time, and Kalshi's commence_time ≈ resolution time
(gotcha #14), so when the last snapshot before commence_time is a settled no-bid
quote (yes_bid=0, yes_ask≈1.00), the cal-price writer stamps that degenerate
price as the "closing line" — "6+ total bases" at 0.96, physically impossible as
a real OVER.

The mandatory verify-before pass (#1054 evidence + Queue #167 db-query trace,
2026-07-12) sub-classed the whole "Player: N+" cohort by LIVE-BID presence and
proved the poison is EXCLUSIVELY the no-live-bid rows:
  * current_yes_bid > 0  → 83,355 outcomes, a genuine calibration diagonal
      across every decile (cp 0.07→wr 0.09, 0.44→0.41, 0.67→0.64, 0.97→0.995;
      class ECE 0.023 / MCE 0.062). Real live/pre-resolution prices — KEPT.
  * current_yes_bid = 0/NULL → 69,457 outcomes, cp 0.97 vs winrate 0.19
      (MCE 0.78). Degenerate post-settlement captures — EXCLUDED, never
      re-graded (no Under/No sibling to flip, no honest pre-game price).
Excluding only the no-bid rows takes the class from ECE 0.123/MCE 0.779 to
ECE 0.023/MCE 0.062 while retaining 83K honest data points ("SAVE all possible",
gotcha #21). The structural signature (source=kalshi + "<subject>: N+" name + no
live bid) is self-maintaining and mirrors the writer-side guard in
backfill_winners._compute_calibration_prices.

Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
This suite covers the canonical predicate (including the live-bid keep rule), the
rule text, the corrections-log entry, that BOTH the precompute task and the route
fallback embed the exclusion, and that the writer-side capture guard is present.
"""

import importlib
import inspect

from app.tasks import precompute_calibration

# NB: ``app.tasks.backfill_winners`` the *name* is shadowed by the celery task
# proxy of the same name, so import the module object explicitly.
backfill_winners = importlib.import_module("app.tasks.backfill_winners")
from app.tasks.precompute_calibration import (
    CALIBRATION_CORRECTIONS,
    KALSHI_PROP_THRESHOLD_NAME_RE,
    KALSHI_PROP_THRESHOLD_RULE_TEXT,
    outcome_is_kalshi_prop_threshold,
)


class TestKalshiPropThresholdPredicate:
    def test_degenerate_no_bid_threshold_names_excluded(self):
        # Single-sided "<subject>: N+" OVER outcomes with NO live bid are the
        # excluded (degenerate post-settlement) cohort. current_yes_bid None or 0.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0) is True
        assert outcome_is_kalshi_prop_threshold("kalshi", "Colson Montgomery: 6+", None) is True
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+", 0) is True
        # Multi-digit thresholds (unlikely but structurally valid).
        assert outcome_is_kalshi_prop_threshold("kalshi", "Some Player: 12+", 0) is True
        # Tolerant of extra spacing around the colon/plus.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Nikola Jokic:  3+ ", 0) is True
        # Default (unknown bid) is conservative → treated as degenerate/excluded.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+") is True

    def test_real_bid_threshold_rows_kept(self):
        # A "Player: N+" prop that carried a REAL live YES bid is a genuine
        # prediction (the 83K near-diagonal cohort) — it must NOT be excluded.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+", 0.44) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.67) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "Nikola Jokic: 3+", 0.99) is False

    def test_non_threshold_kalshi_outcomes_kept(self):
        # Genuine game/series/economic markets don't use the "N+" OVER shape.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Yes", 0) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "No", 0) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "New York Yankees", 0) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "3.0% to 3.5%", 0) is False
        # A bare "N+" with no "<subject>:" prefix is not the prop shape.
        assert outcome_is_kalshi_prop_threshold("kalshi", "5+", 0) is False
        # Under/No is explicitly the wrong side — but no such rows exist in the
        # class anyway (0 Under/No across 122,580); still, don't match them.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Under 5.5", 0) is False

    def test_scoped_to_kalshi_only(self):
        # Polymarket / odds_api threshold-shaped names are handled by their own
        # corrections (poly sign-flip); this filter is kalshi-scoped.
        assert outcome_is_kalshi_prop_threshold("polymarket", "Aaron Judge: 4+", 0) is False
        assert outcome_is_kalshi_prop_threshold("odds_api", "Aaron Judge: 4+", 0) is False

    def test_none_and_empty_safe(self):
        assert outcome_is_kalshi_prop_threshold(None, "Aaron Judge: 4+", 0) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", None, 0) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "", 0) is False
        assert outcome_is_kalshi_prop_threshold(None, None, 0) is False

    def test_sql_regex_has_no_backslash_escape(self):
        # POSIX bracket [+] is a literal plus, so no backslash survives the
        # f-string into the SQL ~ operator (a stray \+ would be a SQL syntax
        # landmine). Guard it.
        assert "\\" not in KALSHI_PROP_THRESHOLD_NAME_RE
        assert "[+]" in KALSHI_PROP_THRESHOLD_NAME_RE


class TestRuleText:
    def test_rule_describes_the_exclusion(self):
        t = KALSHI_PROP_THRESHOLD_RULE_TEXT.lower()
        assert "kalshi" in t
        assert "player-prop" in t or "player prop" in t
        # Names the capture mechanism (gotcha #14) and the no-regrade stance.
        assert "post-settlement" in t or "commence_time" in t
        assert "n+" in t or "over" in t
        # Read-side guarantee (gotcha #21).
        assert "never" in t and "mutate" in t
        # Frames it as the Kalshi twin of the poly sign-flip.
        assert "sign-flip" in t or "polymarket" in t
        # Names the refined live-bid discriminator (keeps the good cohort).
        assert "bid" in t


class TestCorrectionsLog:
    def test_kalshi_prop_correction_present(self):
        titles = [c["title"].lower() for c in CALIBRATION_CORRECTIONS]
        assert any("kalshi" in t and ("prop" in t or "threshold" in t) for t in titles)


class TestPrecomputeQueryEmbedsExclusion:
    def test_main_query_excludes_kalshi_prop_thresholds(self):
        src = inspect.getsource(
            precompute_calibration._precompute_calibration_main
        )
        # The structural flag on the "<subject>: N+" kalshi outcome.
        assert "is_kalshi_prop_threshold" in src
        # The exclusion is applied in the deduped filter.
        assert "NOT ro.is_kalshi_prop_threshold" in src
        # Refined signature: only the no-live-bid (degenerate) rows are excluded;
        # the real-bid diagonal cohort is kept.
        assert "current_yes_bid" in src
        # Transparency count + payload surface.
        assert "kalshi_prop_threshold_excluded" in src
        assert '"kalshi_prop_threshold_filter"' in src

    def test_exclusion_is_read_side_only(self):
        # Guardrail (gotcha #21): the exclusion must never mutate is_winner/cp.
        src = inspect.getsource(
            precompute_calibration._precompute_calibration_main
        ).lower()
        assert "update futures_outcomes" not in src
        assert "update futures_markets" not in src
        assert "delete from futures_outcomes" not in src


class TestWriterSideCaptureGuard:
    def test_part_a_guards_threshold_no_bid_capture(self):
        # Queue #167 writer-side guard: the cal-price writer (Part A) must refuse
        # to stamp a degenerate no-bid snapshot as the closing line for Kalshi
        # threshold props, and must not fall back to the (degenerate) opening.
        src = inspect.getsource(
            backfill_winners._compute_calibration_prices
        )
        # The threshold flag is threaded into needs_cal.
        assert "is_threshold" in src
        # Threshold rows only take a snapshot that carried a real resting YES bid
        # (a last_price gate would let the ~0.99 settled trade back in).
        assert "NOT nc.is_threshold OR fos.yes_bid > 0" in src
        # Threshold rows never fall back to the opening (CASE → NULL).
        assert "WHEN nc.is_threshold THEN NULL" in src


class TestRouteFallbackEmbedsExclusion:
    def test_route_fallback_mirrors_exclusion(self):
        # The cold-cache fallback in routes/calibration.py must stay in sync so a
        # cache miss is not silently prop-inflated.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route)
        assert "is_kalshi_prop_threshold" in src
        assert "NOT ro.is_kalshi_prop_threshold" in src
