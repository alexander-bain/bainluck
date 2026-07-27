"""Queue #158 (#1011): curve-side SOCCER 2-WAY (draw-omission) exclusion.

Soccer game-odds are 3-way (home/draw/away), but the events table has no draw
column, so every soccer moneyline row was stored as a 2-way home/away split
summing to ~1.0 — structurally dropping the ~25% draw mass. That over-predicts
home/away by 7-18pp uniformly across all ~20 leagues (ops-lane census #1010/#1011:
EPL 0.573 predicted vs 0.397 actual = 17.6pp; Switzerland 15.0pp; Turkey 7.6pp).
The draw was never captured so these rows can't be reconstructed/re-graded; they
are excluded from the published curve, league-scoped by the soccer_* sport key.
Forward fix (3-way capture into a draw column) is #1011's separate schema step.

Read-side only (gotcha #21) — never mutates scores / probabilities. This suite
covers the canonical predicate, the rule text, the corrections-log entry, and that
BOTH the precompute task and the route fallback embed the exclusion so a cache
miss is not silently soccer-inflated.
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    CALIBRATION_CORRECTIONS,
    SOCCER_2WAY_EXCLUDE_PATTERN,
    SOCCER_2WAY_RULE_TEXT,
    category_is_soccer_2way_excluded,
)


class TestSoccer2WayPredicate:
    def test_soccer_leagues_excluded(self):
        # Every soccer_* league key is the excluded 2-way-capture cohort.
        assert category_is_soccer_2way_excluded("soccer_epl") is True
        assert category_is_soccer_2way_excluded("soccer_spain_la_liga") is True
        assert category_is_soccer_2way_excluded("soccer_uefa_champs_league") is True
        assert category_is_soccer_2way_excluded("soccer_switzerland_superleague") is True

    def test_non_soccer_sports_untouched(self):
        # 2-way sports with no draw (basketball/baseball/hockey/etc.) stay in.
        assert category_is_soccer_2way_excluded("basketball_nba") is False
        assert category_is_soccer_2way_excluded("baseball_mlb") is False
        assert category_is_soccer_2way_excluded("icehockey_nhl") is False
        assert category_is_soccer_2way_excluded("americanfootball_nfl") is False

    def test_none_and_empty_safe(self):
        assert category_is_soccer_2way_excluded(None) is False
        assert category_is_soccer_2way_excluded("") is False

    def test_bare_soccer_token_not_a_league_key(self):
        # The exclusion is league-scoped ('soccer_<league>'); a bare 'soccer'
        # category is not an events sport key and must not be matched.
        assert category_is_soccer_2way_excluded("soccer") is False

    def test_pattern_constant(self):
        assert SOCCER_2WAY_EXCLUDE_PATTERN == "soccer_%"


class TestRuleText:
    def test_rule_describes_the_exclusion(self):
        t = SOCCER_2WAY_RULE_TEXT.lower()
        assert "3-way" in t
        assert "draw" in t
        assert "soccer_*" in t or "soccer" in t
        assert "never mutates" in t
        # Rule must name BOTH excluded moneyline sources.
        assert "odds_api_bookmaker" in t
        # And clarify spreads/totals are kept.
        assert "spreads/totals" in t


class TestCorrectionsLog:
    def test_soccer_correction_present(self):
        titles = [c["title"].lower() for c in CALIBRATION_CORRECTIONS]
        assert any("soccer" in t and "draw" in t for t in titles)


class TestPrecomputeQueryEmbedsExclusion:
    def test_main_query_excludes_soccer_leagues(self):
        src = inspect.getsource(
            precompute_calibration.compute_calibration_payload
        )
        # The events-curve moneyline query league-scopes the exclusion.
        assert "s.key NOT LIKE 'soccer_%'" in src
        # Transparency count query + payload surface.
        assert "soccer_2way_excluded" in src
        assert '"soccer_2way_filter"' in src

    def test_bookmaker_source_also_excludes_soccer(self):
        # The per-bookmaker source (odds_api_bookmaker) has the SAME 2-way
        # draw-omission bug and dominates the soccer_* lines — it must be
        # filtered on the consumption side too, else the D5 win is lost.
        src = inspect.getsource(
            precompute_calibration.compute_calibration_payload
        )
        assert "bookmaker_soccer_excluded" in src
        # The consumption filter uses the canonical predicate.
        assert "category_is_soccer_2way_excluded(row.get(\"category\"))" in src

    def test_exclusion_is_read_side_only(self):
        # Guardrail (gotcha #21): the exclusion must never mutate scores/probs.
        src = inspect.getsource(
            precompute_calibration.compute_calibration_payload
        ).lower()
        assert "update events" not in src
        assert "update futures_outcomes" not in src
        assert "delete from events" not in src


class TestRouteFallbackDelegatesToSharedPath:
    def test_route_fallback_delegates_to_shared_payload(self):
        # Queue #257 Item 1: the cold-cache fallback no longer carries its own
        # copy of the CTE chain — it delegates to the ONE shared
        # compute_calibration_payload, so it inherits the soccer 2-way exclusion
        # (and every other) by construction. A cache miss can never diverge.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route.public_calibration)
        assert "compute_calibration_payload" in src
