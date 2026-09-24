"""#8427 — the no-database half of the `superbowl` recall guard.

The route-level proof is `tests/integration/test_search_superbowl_joined_pg_8427.py`,
which SKIPS without `SEARCH_TEST_DATABASE_URL` (CI's `search-recall` job has one).
This file runs everywhere, so deleting the entry reddens the ordinary backend
shards too, not only the one job that can see Postgres. Literals, not the table
read back into the assertion.
"""

from app.routes import events as events_route
from app.utils.name_normalization import expand_search_terms


def test_the_joined_spelling_expands_to_the_venues_two_words():
    expanded = events_route._apply_search_synonyms(
        expand_search_terms(["nfl", "Superbowl", "winner"])
    )
    assert ("Superbowl", "super bowl") in expanded
    assert ("winner", "champion") in expanded  # untouched neighbour


def test_the_spaced_form_is_not_rewritten():
    # One-way: "super" / "bowl" each already match the venue's name. (`super` keeps
    # its own unrelated diacritic fold to `süper` for Süper Lig; not asserted here.)
    expanded = events_route._apply_search_synonyms(expand_search_terms(["super", "bowl"]))
    assert all(exp != "superbowl" for _, exp in expanded)
    assert ("bowl", None) in expanded
