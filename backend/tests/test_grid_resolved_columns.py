"""Championship-grid season-state resolved-column detection (#927 / Queue #54).

A column is "resolved" only when every team is decided (prob within ε of 0/1).
This is a derived display signal — it must flag settled columns (NBA make_playoffs
in mid-June) without eating live ones (MLB make_playoffs still a spread).
"""

from app.routes.playoffs import _grid_column_resolved


def _teams(*probs_by_key):
    """Build team rows: each arg is a dict {key: prob}."""
    return [{"cells": {k: {"merged_probability": p} for k, p in d.items()}} for d in probs_by_key]


class TestGridColumnResolved:
    def test_all_decided_is_resolved(self):
        teams = _teams({"mp": 1.0}, {"mp": 0.0}, {"mp": 0.995}, {"mp": 0.005})
        assert _grid_column_resolved(teams, "mp") is True

    def test_any_live_team_is_not_resolved(self):
        # One team mid-probability → column still live (e.g. MLB make_playoffs)
        teams = _teams({"mp": 1.0}, {"mp": 0.0}, {"mp": 0.62}, {"mp": 0.0})
        assert _grid_column_resolved(teams, "mp") is False

    def test_mlb_style_make_playoffs_stays_live(self):
        # Realistic MLB spread: nothing at 0/1 → not resolved
        teams = _teams({"mp": 0.95}, {"mp": 0.62}, {"mp": 0.30}, {"mp": 0.016})
        assert _grid_column_resolved(teams, "mp") is False

    def test_empty_column_not_resolved(self):
        # No cells for this key → nothing to collapse
        assert _grid_column_resolved(_teams({"other": 1.0}), "mp") is False
        assert _grid_column_resolved([], "mp") is False

    def test_epsilon_boundary(self):
        # 0.01 / 0.99 are inside ε; 0.02 is outside
        assert _grid_column_resolved(_teams({"mp": 0.01}, {"mp": 0.99}), "mp") is True
        assert _grid_column_resolved(_teams({"mp": 0.02}, {"mp": 0.99}), "mp") is False

    def test_present_but_unpriced_cell_refuses_the_column(self):
        # AMENDED #6442. This case asserted True under the name
        # "test_skips_missing_probabilities", on the reasoning that a cell with
        # no merged_probability "is ignored, not treated as live". That is
        # fault (a) of #6442 in miniature: an unpriced, ungraded cell is not
        # evidence that anything was decided, and skipping it is what let ONE
        # priced club of 36 resolve the UCL quarterfinal column. A cell that is
        # present carries no price and no settled state is UNKNOWN, and a
        # column containing an unknown is not decided.
        teams = [
            {"cells": {"mp": {"merged_probability": 1.0}}},
            {"cells": {"mp": {"merged_probability": None}}},
            {"cells": {"mp": {"merged_probability": 0.0}}},
        ]
        assert _grid_column_resolved(teams, "mp") is False

    def test_a_settled_state_decides_without_a_price(self):
        # The other half of the amendment: the register's terminal results are
        # the strongest evidence there is, and they carry no probability. The
        # old skip made a fully venue-settled column resolve only by accident
        # (empty probs -> False); now it resolves because it is settled.
        teams = [
            {"cells": {"mp": {"merged_probability": None, "state": "won"}}},
            {"cells": {"mp": {"merged_probability": None, "state": "eliminated"}}},
            {"cells": {"mp": {"merged_probability": 1.0}}},
        ]
        assert _grid_column_resolved(teams, "mp") is True
