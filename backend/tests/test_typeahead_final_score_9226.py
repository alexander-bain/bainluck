"""#9226 — a finished dropdown row carries its result, without a database.

The route behaviour is `tests/integration/test_typeahead_final_score_pg_9226.py`
(real Postgres). This file pins the rule: which rows get the score, and which
never do.
"""

from __future__ import annotations

import inspect

from app.routes import events as ev_mod

rule = ev_mod._typeahead_final_score


class TestFinishedRows:
    def test_a_completed_row_carries_both_scores(self):
        assert rule("completed", 10, 24) == {"home_score": 10, "away_score": 24}

    def test_a_closed_row_carries_both_scores(self):
        assert rule("closed", 3, 2) == {"home_score": 3, "away_score": 2}

    def test_nil_nil_is_a_result(self):
        """`0` is a score; a truthiness test would drop every shutout."""
        assert rule("completed", 0, 0) == {"home_score": 0, "away_score": 0}


class TestNeverAScore:
    def test_a_live_row_carries_none(self):
        """A cached dropdown would serve a live score stale between keystrokes."""
        assert rule("live", 1, 0) == {}

    def test_a_scheduled_row_carries_none(self):
        assert rule("scheduled", None, None) == {}

    def test_a_finished_row_with_no_report_carries_none(self):
        assert rule("completed", None, None) == {}

    def test_half_a_score_is_not_a_result(self):
        assert rule("completed", 7, None) == {}
        assert rule("completed", None, 7) == {}


def test_the_primary_pool_spends_the_rule_on_the_served_status():
    """The rule must see the SERVED status, the one the row prints, not the
    stored one, or the row could say "Final" and carry nothing, or the reverse."""
    src = inspect.getsource(ev_mod.typeahead_search)
    assert "_typeahead_final_score(\n                _ta_served_status,\n" in src
    assert '"status": _ta_served_status,' in src
