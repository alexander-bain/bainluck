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
    KALSHI_PROP_THRESHOLD_DEGENERATE_BAND,
    KALSHI_PROP_THRESHOLD_NAME_RE,
    KALSHI_PROP_THRESHOLD_RULE_TEXT,
    kalshi_prop_threshold_exclude_sql,
    outcome_is_kalshi_prop_threshold,
)


class TestKalshiPropThresholdPredicate:
    def test_degenerate_settlement_band_excluded(self):
        # Queue #186: the honest discriminator is the CURVE PRICE, not the bid.
        # A "<subject>: N+" OVER outcome whose curve price sits in the degenerate
        # settlement-collapse band (>= 0.90) is a post-game quote, not a
        # prediction — it resolves 0.11–0.48 across every series. Excluded.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+", 0.96) is True
        assert outcome_is_kalshi_prop_threshold("kalshi", "Colson Montgomery: 6+", 0.99) is True
        # Boundary: exactly 0.90 is degenerate.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Some Player: 12+", 0.90) is True
        # Tolerant of extra spacing around the colon/plus.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Nikola Jokic:  3+ ", 0.98) is True
        # Default (unknown price) is conservative → treated as degenerate/excluded.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+") is True

    def test_below_band_liquid_rows_kept(self):
        # Below the degenerate band the liquid NBA/MLB series are an honest
        # diagonal (opening 0.647→wr 0.600, 0.749→0.734) — they must be KEPT
        # ("SAVE all possible", gotcha #21). The disproven #167 rule wrongly
        # excluded no-bid rows and kept real-bid ones; now it's purely the price.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+", 0.44) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "Nikola Jokic: 3+", 0.67) is False
        # Just below the band.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Some Player: 2+", 0.899) is False

    def test_hockey_goal_family_honest_band_recovered(self):
        # Queue #194 (#1089): the NHL goal-family (KXNHLGOAL/PTS/AST) is honest
        # below 0.50 (forensic gaps 3.1/2.2/4.0pp) and degenerate at/above it
        # (32.6pp → 79.3pp). The honest low band is RECOVERED (kept); only the
        # degenerate >=0.50 split is dropped. Corrects #941's wholesale drop.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.10, "hockey") is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.45, "hockey") is False
        # Boundary: exactly 0.50 is degenerate → excluded.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.50, "hockey") is True
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.67, "hockey") is True
        assert outcome_is_kalshi_prop_threshold("kalshi", "Connor Bedard: 1+", 0.98, "hockey") is True
        # Non-hockey below-band rows are still kept even though a category is given.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Aaron Judge: 4+", 0.44, "baseball") is False
        # Category alone (non-threshold name) never matches.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Yes", 0.1, "hockey") is False

    def test_non_threshold_kalshi_outcomes_kept(self):
        # Genuine game/series/economic markets don't use the "N+" OVER shape.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Yes", 0.96) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "No", 0.96) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "New York Yankees", 0.96) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "3.0% to 3.5%", 0.96) is False
        # A bare "N+" with no "<subject>:" prefix is not the prop shape.
        assert outcome_is_kalshi_prop_threshold("kalshi", "5+", 0.96) is False
        # Under is explicitly the wrong side and never matches the OVER shape.
        assert outcome_is_kalshi_prop_threshold("kalshi", "Under 5.5", 0.96) is False

    def test_scoped_to_kalshi_only(self):
        # Polymarket / odds_api threshold-shaped names are handled by their own
        # corrections (poly sign-flip); this filter is kalshi-scoped.
        assert outcome_is_kalshi_prop_threshold("polymarket", "Aaron Judge: 4+", 0.96) is False
        assert outcome_is_kalshi_prop_threshold("odds_api", "Aaron Judge: 4+", 0.96) is False

    def test_none_and_empty_safe(self):
        assert outcome_is_kalshi_prop_threshold(None, "Aaron Judge: 4+", 0.96) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", None, 0.96) is False
        assert outcome_is_kalshi_prop_threshold("kalshi", "", 0.96) is False
        assert outcome_is_kalshi_prop_threshold(None, None, 0.96) is False

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
        assert "settlement" in t or "commence_time" in t or "post-game" in t
        assert "n+" in t or "over" in t
        # Read-side guarantee (gotcha #21).
        assert "never" in t and "mutate" in t
        # Frames the disproven sign-flip premise.
        assert "sign-flip" in t or "polymarket" in t
        # Names the corrected curve-price discriminator + the hockey class.
        assert "curve price" in t or ">= 0.90" in t or "band" in t
        assert "hockey" in t


class TestCorrectionsLog:
    def test_kalshi_prop_correction_present(self):
        titles = [c["title"].lower() for c in CALIBRATION_CORRECTIONS]
        assert any("kalshi" in t and ("prop" in t or "threshold" in t) for t in titles)


class TestCanonicalExcludeSql:
    """Queue #188 Item 3: the SQL predicate is now rendered from ONE shared helper
    so every read-path honours the identical rule and no hand-typed literal can
    drift (the route used to hardcode ``0.90`` + the regex; source_intelligence
    had no guard at all)."""

    def test_render_carries_corrected_discriminator(self):
        frag = kalshi_prop_threshold_exclude_sql(
            source="cv.source",
            name="fo.name",
            category="cv.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
        )
        # Kalshi-scoped, "<subject>: N+" name shape, curve-price band + hockey class.
        assert "cv.source = 'kalshi'" in frag
        assert KALSHI_PROP_THRESHOLD_NAME_RE in frag
        assert "cv.category = 'hockey'" in frag
        # The band comes from the constant, never a hand-typed literal.
        assert str(KALSHI_PROP_THRESHOLD_DEGENERATE_BAND) in frag
        assert "COALESCE(fo.calibration_probability, fo.opening_probability)" in frag

    def test_render_respects_caller_aliases(self):
        # source_intelligence uses different aliases (fm.source / am.category).
        frag = kalshi_prop_threshold_exclude_sql(
            source="fm.source",
            name="fo.name",
            category="am.category",
            calibration_probability="fo.calibration_probability",
            opening_probability="fo.opening_probability",
        )
        assert "fm.source = 'kalshi'" in frag
        assert "am.category = 'hockey'" in frag


class TestPrecomputeQueryEmbedsExclusion:
    def test_main_query_excludes_kalshi_prop_thresholds(self):
        src = inspect.getsource(
            precompute_calibration._precompute_calibration_main
        )
        # The structural flag on the "<subject>: N+" kalshi outcome.
        assert "is_kalshi_prop_threshold" in src
        # The exclusion is applied in the deduped filter.
        assert "NOT ro.is_kalshi_prop_threshold" in src
        # Queue #188 Item 3: the corrected discriminator (curve-price band + hockey
        # class) is now rendered from the shared helper, not inlined — so it cannot
        # drift from the route or source_intelligence copies.
        assert "kalshi_prop_threshold_exclude_sql" in src
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
        # Queue #188 Item 3: the route no longer hardcodes the band/regex — it
        # renders the predicate from the shared helper, so it cannot drift.
        assert "kalshi_prop_threshold_exclude_sql" in src


class TestSourceIntelligenceHonorsExclusion:
    """Queue #188 Item 3: the Kalshi↔Polymarket fair-fight MCE was the one
    calibration read-path that read Kalshi cal prices raw — the corrupt
    #941/#186 prop-threshold rows (NHL goal-family + >=0.90 band) leaked
    straight into Kalshi's MCE. It must still honour the exclusion so the fair
    fight is not poisoned.

    Queue #197/#198: the canonical impl now lives in the precompute task
    (`_query_futures_fair_fight_impl`); the dead route-level duplicate that
    predated #195 (and hung 240s+) was removed. The #197 profile rewrite swapped
    the `kalshi_prop_threshold_exclude_sql` helper for an inlined
    `resolution_source NOT IN (...)` guard-list + `volume != 0` predicate, so
    these assertions track the impl's actual exclusion mechanism."""

    def test_fair_fight_applies_shared_exclusion(self):
        from app.tasks.precompute_calibration import _query_futures_fair_fight_impl

        src = inspect.getsource(_query_futures_fair_fight_impl)
        # Excludes the guess/threshold resolution families that poisoned the
        # Kalshi curve (#754/#941/#186) so they cannot leak into the fair fight.
        assert "resolution_source NOT IN" in src
        assert "pass3_threshold" in src  # the prop-threshold class (#186)
        assert "pass2_guess" in src      # the guess family (#754)
        # And drops zero-volume placeholder rows (illiquid one-sided capture).
        assert "COALESCE(fo.volume, -1) != 0" in src

    def test_fair_fight_is_read_side_only(self):
        # Gotcha #21: the fair-fight query must never mutate resolutions/prices.
        from app.tasks.precompute_calibration import _query_futures_fair_fight_impl

        src = inspect.getsource(_query_futures_fair_fight_impl).lower()
        assert "update futures_outcomes" not in src
        assert "update futures_markets" not in src
        assert "delete from futures_outcomes" not in src
