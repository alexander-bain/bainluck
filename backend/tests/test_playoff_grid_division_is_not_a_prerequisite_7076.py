"""#7076 — winning the division is not how you reach the pennant.

Alex saw it on his phone (TestFlight 1.0(15), 2026-09-18): the Red Sox event
page showed Division 1% and World Series 1% and no useful AL Championship
number, while My Stuff showed the right one.

**The markets were selected correctly. A monotonicity clamp overwrote them.**
`/api/playoffs/mlb` — the grid that `league_context` turns into
`/api/events/{id}/team-progression` — served Boston::

    make_playoffs 0.9903   division 0.0065   pennant 0.0065   championship 0.0065

with every per-source entry rewritten to 0.0065 as well, while Boston's real
rows in the same database were kalshi 274 = 0.115 / polymarket 199045 = 0.122
for the pennant. `(0.010 + 0.003) / 2 = 0.0065` — the served value for all
three stages is the *division* blend.

The rule being enforced was "a sequential column is <= the column before it",
and MLB's column order is make_playoffs -> **division** -> pennant ->
championship. Read out loud that is "you cannot win the pennant unless you win
your division", which wild cards falsify every October. 10 of 30 MLB teams were
served a pennant identical to their division cell on 2026-09-19, including the
Yankees at 6.25%.

Tampa Bay is the control that was in the same payload the whole time: they lead
the AL East, so 0.943 >= 0.3507 never violated the bad rule and their four
stages stayed distinct. **Any fix that also moves Tampa is the wrong fix.**

The bound is now declared by the league (`GridColumn.depends_on`) instead of
being inferred from column order, and the route's hand-inlined second copy of
the clamp is gone — it was the copy that ran first.
"""

import re
from types import SimpleNamespace

import pytest

from app.config.league_configs import (
    LEAGUE_CONFIGS,
    MLB_CONFIG,
    NBA_CONFIG,
    NFL_CONFIG,
    NHL_CONFIG,
)
from app.utils.playoff_grid import enforce_monotonicity, monotonic_pairs


def _cell(prob, *sources):
    return {
        "merged_probability": prob,
        "sources": [{"source": s, "probability": p} for s, p in sources],
        "trend_24h": None,
        "state": "live",
    }


def _boston():
    """Boston's stored rows on 2026-09-19, blended, before any clamp.

    pennant  = (0.115 + 0.122) / 2, championship = (0.0435 + 0.0577) / 2 —
    both far above the division blend (0.010 + 0.003) / 2.
    """
    return {
        "name": "Boston Red Sox",
        "cells": {
            "make_playoffs": _cell(0.9903, ("polymarket", 0.9855), ("kalshi", 0.995)),
            "division": _cell(0.0065, ("polymarket", 0.003), ("kalshi", 0.010)),
            "pennant": _cell(0.1185, ("kalshi", 0.115), ("polymarket", 0.122)),
            "championship": _cell(0.0506, ("polymarket", 0.0435), ("odds_api", 0.0577)),
        },
    }


def _tampa():
    """The healthy contrast, from the same production payload."""
    return {
        "name": "Tampa Bay Rays",
        "cells": {
            "make_playoffs": _cell(0.995, ("kalshi", 0.995)),
            "division": _cell(0.943, ("polymarket", 0.941), ("kalshi", 0.945)),
            "pennant": _cell(0.3507, ("polymarket", 0.3384), ("kalshi", 0.363)),
            "championship": _cell(0.0935, ("polymarket", 0.0935), ("kalshi", 0.101)),
        },
    }


def _yankees():
    """A third team, also clamped in production (6.25% pennant AND World Series).

    Their real pennant is above their division cell for the same reason
    Boston's is, and their championship is genuinely below their pennant — so
    this row proves the fix keeps the bound it should keep while dropping the
    one it should not.
    """
    return {
        "name": "New York Yankees",
        "cells": {
            "make_playoffs": _cell(0.97, ("kalshi", 0.97)),
            "division": _cell(0.0625, ("kalshi", 0.0625)),
            "pennant": _cell(0.19, ("kalshi", 0.19)),
            "championship": _cell(0.085, ("kalshi", 0.085)),
        },
    }


class TestTheSpecimen:
    def test_boston_keeps_a_pennant_that_beats_its_division(self):
        team = _boston()
        fixes = enforce_monotonicity([team], MLB_CONFIG.columns)

        assert fixes == 0
        cells = team["cells"]
        assert cells["pennant"]["merged_probability"] == 0.1185
        assert cells["championship"]["merged_probability"] == 0.0506
        # The reader's actual complaint: four questions, four answers.
        served = [cells[k]["merged_probability"] for k in
                  ("make_playoffs", "division", "pennant", "championship")]
        assert len(set(served)) == 4

    def test_bostons_source_rows_are_not_rewritten_to_the_division_blend(self):
        """The clamp rewrote `sources[].probability` too, so all three source

        marks on the page asserted an agreement at 0.0065 that no venue made.
        """
        team = _boston()
        enforce_monotonicity([team], MLB_CONFIG.columns)

        pennant_sources = {
            s["source"]: s["probability"] for s in team["cells"]["pennant"]["sources"]
        }
        assert pennant_sources == {"kalshi": 0.115, "polymarket": 0.122}

    def test_tampa_is_untouched(self):
        """The healthy contrast from the same payload must not move at all."""
        before = _tampa()
        after = _tampa()
        fixes = enforce_monotonicity([after], MLB_CONFIG.columns)

        assert fixes == 0
        assert after == before

    def test_the_third_team_keeps_its_ladder(self):
        team = _yankees()
        enforce_monotonicity([team], MLB_CONFIG.columns)
        cells = team["cells"]

        assert cells["pennant"]["merged_probability"] == 0.19
        assert cells["championship"]["merged_probability"] == 0.085

    def test_all_three_teams_together_in_one_pass(self):
        """The real call site passes every team in the league at once."""
        teams = [_boston(), _tampa(), _yankees()]
        assert enforce_monotonicity(teams, MLB_CONFIG.columns) == 0

    def test_idempotent(self):
        team = _boston()
        enforce_monotonicity([team], MLB_CONFIG.columns)
        first = {k: v["merged_probability"] for k, v in team["cells"].items()}
        enforce_monotonicity([team], MLB_CONFIG.columns)
        second = {k: v["merged_probability"] for k, v in team["cells"].items()}
        assert first == second


class TestTheBoundsThatRemain:
    """Dropping the wrong bound must not drop the right ones."""

    def test_pennant_above_make_playoffs_is_still_capped(self):
        team = _boston()
        team["cells"]["make_playoffs"] = _cell(0.30, ("kalshi", 0.30))
        team["cells"]["pennant"] = _cell(0.55, ("kalshi", 0.55), ("polymarket", 0.60))

        fixes = enforce_monotonicity([team], MLB_CONFIG.columns)

        assert fixes >= 1
        assert team["cells"]["pennant"]["merged_probability"] == 0.30
        assert all(
            s["probability"] <= 0.30 for s in team["cells"]["pennant"]["sources"]
        )

    def test_championship_is_still_capped_at_the_pennant(self):
        team = _boston()
        team["cells"]["championship"] = _cell(0.40, ("odds_api", 0.40))

        enforce_monotonicity([team], MLB_CONFIG.columns)

        assert team["cells"]["championship"]["merged_probability"] == 0.1185

    def test_division_is_still_capped_at_make_playoffs(self):
        team = _boston()
        team["cells"]["division"] = _cell(0.999, ("kalshi", 0.999))

        enforce_monotonicity([team], MLB_CONFIG.columns)

        assert team["cells"]["division"]["merged_probability"] == 0.9903

    def test_a_cap_still_cascades(self):
        """make_playoffs caps the pennant, and the capped pennant caps the title."""
        team = _boston()
        team["cells"]["make_playoffs"] = _cell(0.20, ("kalshi", 0.20))
        team["cells"]["pennant"] = _cell(0.55, ("kalshi", 0.55))
        team["cells"]["championship"] = _cell(0.45, ("kalshi", 0.45))

        enforce_monotonicity([team], MLB_CONFIG.columns)

        assert team["cells"]["pennant"]["merged_probability"] == 0.20
        assert team["cells"]["championship"]["merged_probability"] == 0.20


class TestPairs:
    def test_mlb_pairs(self):
        assert monotonic_pairs(MLB_CONFIG.columns) == [
            ("make_playoffs", "division"),
            ("make_playoffs", "pennant"),
            ("pennant", "championship"),
        ]

    @pytest.mark.parametrize("config", [NBA_CONFIG, NHL_CONFIG, NFL_CONFIG])
    def test_the_other_three_division_leagues(self, config):
        assert monotonic_pairs(config.columns) == [
            ("make_playoffs", "division"),
            ("make_playoffs", "conference"),
            ("conference", "championship"),
        ]

    def test_an_undeclared_column_still_follows_the_column_before_it(self):
        """No `depends_on` anywhere = exactly the behaviour this file replaced."""
        cols = [
            SimpleNamespace(key="make_playoffs", order=1, sequential=True),
            SimpleNamespace(key="division", order=2, sequential=True),
            SimpleNamespace(key="conference", order=3, sequential=True),
        ]
        assert monotonic_pairs(cols) == [
            ("make_playoffs", "division"),
            ("division", "conference"),
        ]

    def test_a_depends_on_that_names_no_earlier_column_degrades_and_warns(self, caplog):
        """A config typo must not 500 a grid page — and must not be silent."""
        cols = [
            SimpleNamespace(key="make_playoffs", order=1, sequential=True),
            SimpleNamespace(key="division", order=2, sequential=True),
            SimpleNamespace(
                key="conference", order=3, sequential=True, depends_on="make_playofs"
            ),
        ]
        with caplog.at_level("WARNING"):
            pairs = monotonic_pairs(cols)

        assert pairs[-1] == ("division", "conference")
        assert "make_playofs" in caplog.text

    def test_a_depends_on_naming_a_later_column_is_refused(self):
        """Forward references would make the walk order-dependent."""
        cols = [
            SimpleNamespace(key="make_playoffs", order=1, sequential=True),
            SimpleNamespace(
                key="division", order=2, sequential=True, depends_on="championship"
            ),
            SimpleNamespace(key="championship", order=3, sequential=True),
        ]
        assert monotonic_pairs(cols)[0] == ("make_playoffs", "division")

    def test_a_missing_bound_cell_skips_rather_than_reaching_further_back(self):
        """A team with no make_playoffs cell gets no bound on its pennant.

        Unchanged from the previous rule, which skipped a pair whose earlier
        cell was absent (`test_missing_intermediate_column_skipped`). Stated
        here because `depends_on` makes the skipped column a *declared* one.
        """
        team = _boston()
        del team["cells"]["make_playoffs"]
        team["cells"]["pennant"] = _cell(0.55, ("kalshi", 0.55))

        enforce_monotonicity([team], MLB_CONFIG.columns)

        assert team["cells"]["pennant"]["merged_probability"] == 0.55


class TestEveryLeagueConfig:
    """The class guard. A new league must not be able to reintroduce this."""

    def test_no_column_is_ever_bounded_by_a_division(self):
        offenders = []
        for slug, config in LEAGUE_CONFIGS.items():
            for bound, col in monotonic_pairs(config.columns):
                if bound == "division":
                    offenders.append(f"{slug}: {col} bounded by {bound}")
        assert offenders == [], (
            "A division title is never a prerequisite for a later round — "
            "declare depends_on on the column after it (#7076): " + "; ".join(offenders)
        )

    def test_every_declared_depends_on_resolves(self):
        """A typo degrades silently at runtime, so it is caught here instead."""
        for slug, config in LEAGUE_CONFIGS.items():
            seq = sorted(
                [c for c in config.columns if c.sequential], key=lambda c: c.order
            )
            keys = [c.key for c in seq]
            for i, col in enumerate(seq):
                declared = getattr(col, "depends_on", None)
                if declared is None:
                    continue
                assert declared in keys[:i], (
                    f"{slug}: column {col.key} declares depends_on={declared!r}, "
                    "which is not an earlier sequential column of this league"
                )

    def test_a_league_without_a_division_column_is_unaffected(self):
        """Soccer/MLS ladders are make_playoffs -> conference -> championship."""
        mls = LEAGUE_CONFIGS["mls"]
        assert all(
            getattr(c, "depends_on", None) is None for c in mls.columns
        )
        assert ("division", "conference") not in monotonic_pairs(mls.columns)


class TestTheRouteUsesTheSharedRule:
    """The route's per-team pass ran BEFORE the shared one and disagreed with it.

    A source-text guard, deliberately: the cell-building loop it lived in is
    400 lines inside an async DB-bound builder, and the thing worth asserting
    is precisely that a second copy of the rule does not exist to drift.
    """

    def _source(self):
        import inspect

        from app.routes import playoffs

        return inspect.getsource(playoffs)

    def test_the_route_holds_no_second_clamp(self):
        src = self._source()
        assert not re.search(
            r'curr_cell\["merged_probability"\]\s*=\s*prev_p', src
        ), "routes/playoffs.py has grown its own copy of the clamp again (#7076)"

    def test_the_route_calls_the_shared_one(self):
        assert "_grid_enforce_monotonicity(" in self._source()
