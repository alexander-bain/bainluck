"""Guards for LAT-P029 Items 1 and 2 — the recall class and the length cap.

These pin BEHAVIOUR of the pure alias layer and the surface's declared bound, not
wall-clock numbers, so they are deterministic in CI. The compiled-SQL assertions
check the arms actually reach the query, which is the part a refactor silently
drops.

Deliberately asserting LITERALS, not the constants under test: LAT-P026 shipped a
TTL guard that read the same constant it checked and therefore pinned nothing, and
LAT-P027 shipped a desync test that passed for the wrong reason until a mutation
exposed it. A test that imports `_TYPEAHEAD_MAX_QUERY_CHARS` and asserts the cap
equals `_TYPEAHEAD_MAX_QUERY_CHARS` cannot fail.
"""

from __future__ import annotations

import pytest

from app.routes.events import (
    _QUERY_PHRASE_ALIASES,
    _alias_futures_arms,
    _phrase_alias_alternatives,
    _strip_search_scaffolding,
    typeahead_search,
)


# --------------------------------------------------------------------------
# Item 1 — the alias layer
# --------------------------------------------------------------------------

def test_march_madness_reaches_the_phrase_the_corpus_actually_uses() -> None:
    """The measured defect: the market is named "…College Basketball Champion"."""

    alternatives = _phrase_alias_alternatives(["march", "madness"])
    assert ["college", "basketball"] in alternatives
    assert ["ncaa", "tournament"] in alternatives


@pytest.mark.parametrize(
    "query",
    [
        ["march", "madness"],
        ["final", "four"],
        ["big", "dance"],
        ["ncaa", "tournament"],
        ["ncaa", "basketball"],
    ],
)
def test_every_name_for_the_tournament_reaches_college_basketball(query: list[str]) -> None:
    """The CLASS, not one string — each colloquial name resolves to the corpus phrase."""

    assert ["college", "basketball"] in _phrase_alias_alternatives(query)


def test_alias_is_a_span_so_it_composes_with_the_rest_of_the_query() -> None:
    """"2027 march madness winner" must keep 2027 and winner, not drop them.

    A whole-query-only match would fix the bare alias and leave every qualified
    form broken, which is the same one-entry-at-a-time trap the token synonym
    table was already in.
    """

    assert ["2027", "college", "basketball", "winner"] in _phrase_alias_alternatives(
        ["2027", "march", "madness", "winner"]
    )


def test_ordinary_queries_produce_no_alternatives_and_therefore_no_extra_sql() -> None:
    """The no-alias path must be free — this is a latency lane."""

    for query in (["red", "sox"], ["inflation"], ["taylor", "swift"], ["super", "bowl"]):
        assert _phrase_alias_alternatives(query) == []
        assert _alias_futures_arms(query) == []


def test_an_alias_never_returns_itself_as_an_alternative() -> None:
    """A duplicate arm is duplicate work for zero recall."""

    for alternative in _phrase_alias_alternatives(["ncaa", "tournament"]):
        assert alternative != ["ncaa", "tournament"]


def test_alias_arms_filter_on_market_name_and_require_every_token() -> None:
    """Compiled SQL: one ANDed ILIKE per canonical token, on futures_markets.name.

    Guards the two ways this silently stops working — the arm targeting the wrong
    column, and the tokens being OR'd (which would match every market containing
    "college" OR "basketball" and flood the surface).
    """

    arms = _alias_futures_arms(["march", "madness"])
    assert len(arms) == 2
    rendered = str(arms[0].compile(compile_kwargs={"literal_binds": True})).lower()
    assert "futures_markets.name" in rendered
    assert "%college%" in rendered and "%basketball%" in rendered
    assert " and " in rendered
    assert " or " not in rendered


def test_scaffolding_stripping_composes_with_the_alias() -> None:
    """The route aliases the STRIPPED terms, so the two layers must compose."""

    stripped = _strip_search_scaffolding("will march madness be decided".split())
    assert "will" not in stripped
    assert ["college", "basketball", "decided"] in _phrase_alias_alternatives(stripped)


def test_known_limit_a_conversational_wrapper_still_under_matches() -> None:
    """Recorded as a LIMIT, not a pass: "who wins march madness" is not solved.

    The alias substitutes its span and keeps the surrounding terms, which is the
    right call — dropping "2027" from "2027 march madness winner" would answer a
    different question. `_SEARCH_SCAFFOLDING` removes "who", but NOT "wins", so
    "wins" survives into an ANDed ILIKE that "Men's 2027 College Basketball
    Champion" does not satisfy.

    Two layers own this, and neither is the alias table: the scaffolding list
    (which changes the predicate for EVERY query) and `_SEARCH_TERM_SYNONYMS`
    (whose one-token->one-STRING shape cannot express "wins" ~ winner ~ champion
    at once). Both are wider blast radius than this queue, so the gap is pinned
    here as visible and deliberate rather than assumed fixed.
    """

    stripped = _strip_search_scaffolding("who wins march madness".split())
    assert stripped == ["wins", "march", "madness"]
    alternatives = _phrase_alias_alternatives(stripped)
    assert ["wins", "college", "basketball"] in alternatives
    assert ["college", "basketball"] not in alternatives


def test_the_alias_tokens_actually_match_the_live_market_name() -> None:
    """Ground the fix in the string production really holds, not in a guess.

    MEASURED 2026-08-10 21:26 PT against deployed master: the NCAA men's
    tournament championship market is named exactly this, and `college basketball`
    is the query that reaches it. The arm ANDs one substring ILIKE per canonical
    token, so this asserts the predicate the arm builds is satisfied by the real
    row — the part a unit test on tuples alone cannot tell you.
    """

    live_market_name = "Men's 2027 College Basketball Champion".casefold()
    for alternative in _phrase_alias_alternatives(["march", "madness"]):
        if alternative == ["college", "basketball"]:
            assert all(token in live_market_name for token in alternative)
            break
    else:  # pragma: no cover - the loop above must find it
        pytest.fail("no alternative targeted the live market name")


def test_both_surfaces_actually_wire_the_alias_arms_in() -> None:
    """The helper being correct is not the same as the route calling it.

    Every other test here exercises `_alias_futures_arms` directly, so deleting
    the two `.extend(...)` lines in the route would leave them all green and ship
    the defect back. This asserts the call site exists on BOTH surfaces, which is
    also what stops the /search-vs-/typeahead drift the file's own comments record
    (the twin fix that reached one surface and not the other for three cycles).
    """

    import inspect

    from app.routes.events import search_events

    for route in (search_events, typeahead_search):
        source = inspect.getsource(route)
        assert "_alias_futures_arms(terms)" in source, (
            f"{route.__name__} no longer adds the alias recall arms"
        )


def test_alias_table_maps_phrases_to_phrases_not_tokens_to_tokens() -> None:
    """The structural point: a one-token map could not have expressed this class.

    If someone "simplifies" this back into `_SEARCH_TERM_SYNONYMS`-shaped data,
    the class becomes inexpressible again and the defect returns.
    """

    assert _QUERY_PHRASE_ALIASES, "the alias table must not be emptied"
    for alias, canonicals in _QUERY_PHRASE_ALIASES.items():
        assert isinstance(alias, tuple) and len(alias) >= 2, alias
        assert all(term == term.lower() for term in alias), alias
        for canonical in canonicals:
            assert isinstance(canonical, tuple) and canonical, (alias, canonical)


# --------------------------------------------------------------------------
# Item 2 — the length cap
# --------------------------------------------------------------------------

def _typeahead_q_bounds() -> tuple[int, int]:
    """Read the bound off the DECLARED route parameter, not off a module constant.

    FastAPI keeps the constraints in `Query(...).metadata` as annotated-types
    markers; reading them here means the test breaks if someone changes the route
    signature, which is the thing being guarded.
    """

    metadata = typeahead_search.__defaults__[0].metadata
    minimum = next(m.min_length for m in metadata if hasattr(m, "min_length"))
    maximum = next(m.max_length for m in metadata if hasattr(m, "max_length"))
    return minimum, maximum


def test_typeahead_accepts_the_real_57_character_user_query() -> None:
    """The measured 422. Boundary was exact: 50 -> 200, 51 -> 422."""

    query = "Where will Taylor Swift and Travis Kelce's Wedding occur?"
    assert len(query) == 57
    _, maximum = _typeahead_q_bounds()
    assert maximum >= len(query), "a real gold-set query must not be refused outright"


def test_typeahead_cap_is_two_hundred_and_still_bounded() -> None:
    """Literal, not the constant under test — see the module docstring."""

    minimum, maximum = _typeahead_q_bounds()
    assert (minimum, maximum) == (2, 200)


def test_typeahead_keeps_its_short_query_floor() -> None:
    """`min_length=2` is load-bearing: LAT-P010 measured `%re%` at 6,830ms.

    Raising the ceiling must not be mistaken for removing the floor — the floor is
    the end where the measured cost actually lives.
    """

    minimum, _ = _typeahead_q_bounds()
    assert minimum == 2
