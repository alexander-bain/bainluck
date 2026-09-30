"""#5082 — `_typeahead_infix_only_event`, the event twin of #7381's word-start team arm.

The route drives it in `tests/integration/test_typeahead_team_query_other_sport_events_5082_pg.py`;
this file pins the helper's edges, each of which a looser or tighter rule gets wrong.
"""

from __future__ import annotations

from app.routes.events import _typeahead_infix_only_event as infix_only

PATS = [("pats", "patriots")]


def test_korpatsch_is_an_infix_row_for_pats():
    # The production specimen, 2026-09-28: Kor·pats·ch.
    assert infix_only(("Taylah Preston", "Tamara Korpatsch"), PATS, False)


def test_the_route_verdict_keeps_a_row_it_already_judged():
    # `9ers` inside "49ers" is the same shape as `pats` inside "Korpatsch";
    # the lead team's id or the curated nickname is what keeps it.
    assert not infix_only(("San Francisco 49ers", "Denver Broncos"), [("9ers", None)], True)
    assert infix_only(("San Francisco 49ers", "Denver Broncos"), [("9ers", None)], False)


def test_a_word_start_row_is_kept():
    assert not infix_only(("Houston Astros", "Chicago White Sox"), [("sox", None)], False)
    assert not infix_only(("Los Angeles Lakers", "Boston Celtics"), [("lak", None)], False)


def test_the_expansion_at_a_word_start_keeps_the_row():
    # `pats` is not in "New England Patriots", its expansion starts a word there.
    assert not infix_only(("Buffalo Bills", "New England Patriots"), PATS, False)


def test_a_row_only_the_stemmer_admitted_is_not_this_helpers_business():
    # No substring at all: `_typeahead_stem_only_event` owns that row.
    assert not infix_only(("Los Angeles Sparks", "Golden State Valkyries"), [("angels", None)], False)


def test_punctuation_and_underscore_start_a_word():
    assert not infix_only(("St. Louis Cardinals", "X"), [("louis", None)], False)
    assert not infix_only(("Team_Pats", "X"), PATS, False)


def test_every_term_must_start_a_word_somewhere():
    # Multi-word: `new` starts a word, `ork` only sits inside "York".
    assert infix_only(("New York Mets", "Atlanta Braves"), [("new", None), ("ork", None)], False)
    assert not infix_only(("New York Mets", "Atlanta Braves"), [("new", None), ("york", None)], False)


def test_empty_inputs_keep_the_row():
    assert not infix_only((None, None), PATS, False)
    assert not infix_only(("Tamara Korpatsch", "X"), [], False)
