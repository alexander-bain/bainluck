"""#9522 — a dropdown row for a 1-on-1 match reads "Michelsen v Alcaraz", never "at".

THE DEFECT, production 2026-09-29 ~02:10Z, `GET /api/events/typeahead?q=alcaraz`:
`Michelsen at Alcaraz` (15320475, tennis_atp). Also `Norrie at Zverev`,
`Qinwen Zheng at Iga Swiatek`, and MMA's `Conor McGregor at Paddy Pimblett`.
A tennis match or a fight has no home side, so "at" says something false.

The route behaviour is `tests/integration/test_typeahead_individual_sport_v_pg_9522.py`
(real Postgres). This file pins the rule and that BOTH event pools spend it.
"""

from __future__ import annotations

import inspect

from app.routes import events as ev_mod

rule = ev_mod._typeahead_event_text


class TestOneOnOneSportsReadV:
    def test_the_production_specimen(self):
        assert rule("Michelsen", "Alcaraz", "tennis_atp") == "Michelsen v Alcaraz"

    def test_every_tennis_key(self):
        """`tennis_other` and the per-tournament keys are tennis too."""
        for key in ("tennis_wta", "tennis_other", "tennis_atp_us_open"):
            assert rule("A", "B", key) == "A v B", key

    def test_a_fight(self):
        assert (
            rule("Conor McGregor", "Paddy Pimblett", "mma_mixed_martial_arts")
            == "Conor McGregor v Paddy Pimblett"
        )
        assert rule("A", "B", "boxing_boxing") == "A v B"

    def test_away_stays_first(self):
        """The web prints a finished row's score away-first (`finalScoreText`);
        swapping the names would put each number under the wrong player."""
        assert rule("Away", "Home", "tennis_atp").startswith("Away ")


class TestTeamSportsKeepAt:
    def test_the_control(self):
        assert (
            rule("Boston Red Sox", "New York Yankees", "baseball_mlb")
            == "Boston Red Sox at New York Yankees"
        )

    def test_no_sport_keeps_at(self):
        """An event with no sport row is not evidence of a 1-on-1 match."""
        assert rule("A", "B", None) == "A at B"

    def test_table_tennis_is_not_tennis(self):
        """The prefix is `tennis_`, so a sport key merely containing it is not one."""
        assert rule("A", "B", "table_tennis_ittf") == "A at B"


def test_both_event_pools_spend_the_rule():
    """The primary pool and the fuzzy pool each built `"{away} at {home}"`
    inline; a pool left on the old literal would print "at" for the very
    rows this ship fixes, only when that arm happened to match."""
    src = inspect.getsource(ev_mod.typeahead_search)
    assert src.count('"text": _typeahead_event_text(') == 2, src.count(
        '"text": _typeahead_event_text('
    )
    assert "at {event.home_team_name}" not in src
