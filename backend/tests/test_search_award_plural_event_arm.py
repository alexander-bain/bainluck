"""The pure half of `oscars` no longer reaching fighters named Oscar.

The route-level proof (both endpoints, real Postgres, with a strawman) is
`tests/integration/test_search_award_plural_event_arm_pg.py`.
"""

from app.routes.events import (
    _PERSON_NAME_AWARD_PLURALS,
    _SEARCH_TERM_SYNONYMS,
    _apply_search_synonyms,
    _event_arm_expanded,
    _names_person_name_award,
    expand_search_terms,
)


def _expanded(q: str):
    return _apply_search_synonyms(expand_search_terms(q.split()))


def test_the_market_arms_keep_the_singular():
    assert ("oscars", "oscar") in _expanded("oscars")
    assert ("tonys", "tony") in _expanded("tonys")


def test_the_event_arms_drop_it():
    assert _event_arm_expanded(_expanded("oscars")) == [("oscars", None)]
    assert _event_arm_expanded(_expanded("Tonys")) == [("Tonys", None)]


def test_every_other_expansion_passes_through_unchanged():
    for q in ("emmys", "grammys", "champion", "superbowl", "president", "eagles"):
        assert _event_arm_expanded(_expanded(q)) == _expanded(q), q
    assert not _names_person_name_award(_expanded("emmys"))


def test_only_the_one_way_entries_are_person_names():
    """The set is the plurals the synonym table expands ONE way because the
    singular is a first name — a two-way entry would not belong here."""
    for plural in _PERSON_NAME_AWARD_PLURALS:
        singular = _SEARCH_TERM_SYNONYMS[plural]
        assert singular not in _SEARCH_TERM_SYNONYMS, plural


def test_a_multi_word_query_is_caught_by_any_term():
    assert _names_person_name_award(_expanded("oscars best picture"))
    assert _event_arm_expanded(_expanded("oscars 2027"))[0] == ("oscars", None)
