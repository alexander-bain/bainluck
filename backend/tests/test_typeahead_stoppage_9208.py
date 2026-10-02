"""#9208 — a called-off dropdown row carries ESPN's word, without a database.

The route behaviour is `tests/integration/test_typeahead_stoppage_pg_9208.py`
(real Postgres). This file pins the rule: which rows get the word, and which
never do.
"""

from __future__ import annotations

import inspect

from app.routes import events as ev_mod
from app.routes import teams as teams_mod

rule = ev_mod._typeahead_stoppage


class TestCalledOffRows:
    def test_a_canceled_row_carries_the_word(self):
        assert rule("suspended", "Canceled") == {"stoppage": "Canceled"}

    def test_a_postponed_row_carries_the_word(self):
        assert rule("suspended", "Postponed") == {"stoppage": "Postponed"}

    def test_the_british_spelling_reads_as_the_one_word(self):
        assert rule("suspended", "cancelled") == {"stoppage": "Canceled"}


class TestNeverAStoppage:
    def test_a_rain_delay_holds_a_period_not_a_stoppage(self):
        assert rule("suspended", "7") == {}
        assert rule("suspended", "Top 7th") == {}

    def test_a_suspended_row_with_no_period_carries_none(self):
        assert rule("suspended", None) == {}

    def test_a_live_row_left_holding_the_word_carries_none(self):
        """Only a row SERVED as suspended speaks; the gate is the served status."""
        assert rule("live", "Postponed") == {}
        assert rule("scheduled", "Canceled") == {}
        assert rule("completed", "Canceled") == {}


def test_the_dropdown_and_the_team_brief_share_one_allowlist():
    """Two surfaces, one word: both read `authority_stoppage_label`."""
    assert ev_mod.authority_stoppage_label is teams_mod.authority_stoppage_label


def test_the_primary_pool_spends_the_rule_on_the_served_status():
    """The rule must see the SERVED status, the one the row prints."""
    src = inspect.getsource(ev_mod.typeahead_search)
    assert (
        '**_typeahead_stoppage(_ta_served_status, getattr(event, "period", None)),'
        in src
    )
