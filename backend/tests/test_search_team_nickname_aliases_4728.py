"""#4728 — colloquial TEAM nicknames reach the team's markets, and only theirs.

The defect, measured on production 2026-09-10, is a recall hole with a truth
defect sitting inside it. `pats`, `revs`, `niners` and `bucs` are how 245 logged
searches asked for four franchises, and every one of them returned ZERO of that
franchise's open markets:

    query    the team's open markets    what the query actually returned
    pats     31                         3  (all Kor*pats*ch, WTA doubles)
    revs     15                         0
    niners   36                         0  (2 events: UTEP *Miners*)
    bucs     41                         5  (all Cristina *Bucs*a, WTA tennis)

So the fan gets none of their team and a handful of tennis players whose surname
happens to contain the nickname.

The team ROW already resolves for all four — `teams.alternate_names` carries
these aliases, backfilled from `CURATED_TEAM_ALIASES` — which is what made the
gap easy to miss. The page names the right team and shows none of its markets.

WHY NOT A PREFIX ARM. `pat:*` matches `patriot`, and also `federico` for `fed`:
that is the exact defect LAT-P033/LAT-P034 closed and LAT-P037 refuses in full.
This is a curated, franchise-anchored alias — no prefix, no stemmer change.

WHY THE SPORT SCOPE IS THE LOAD-BEARING HALF. Of 53 open `%patriot%` markets on
2026-09-10, only 31 were New England's. The rest were Caribbean Premier League
cricket (St. Kitts and Nevis Patriots), Boyaca Patriotas, and the Patriot League.
Matching the plural token drops the Patriotas and the League on spelling, but 15
cricket rows survive it. Scoping to the franchise's own sport takes the false
positives to 0. `revs`, `niners` and `bucs` measured 0 either way — the scope
costs them nothing and is what makes the mechanism safe to extend to the next
nickname, which may not be so lucky.
"""

from __future__ import annotations

import inspect

import pytest

from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _canonical_market_token,
    team_nickname_search_expansions,
)
from app.routes.events import (
    _team_nickname_futures_arms,
    search_events,
    typeahead_search,
)


def _sql(arm) -> str:
    """The arm's compiled SQL, literals inlined so assertions can read values."""
    return str(arm.compile(compile_kwargs={"literal_binds": True}))


# --------------------------------------------------------------------------
# The derivation
# --------------------------------------------------------------------------
def test_the_derived_expansions_are_exactly_these() -> None:
    """Pinned value-by-value, because the derivation is implicit by design.

    `_canonical_market_token` takes the LAST word of the team name — venues drop
    the city ("Jets vs. Patriots", "SF 49ers vs LA Rams"), so the last word is
    the token that reaches market names. That rule is right for all five current
    entries and could be wrong for a future one, so the values are pinned here
    rather than trusted: a new entry whose last word does not reach its markets
    fails this test instead of quietly under-matching in production.
    """

    assert team_nickname_search_expansions() == {
        "pats": ("Patriots", "football"),
        "revs": ("Revolution", "soccer"),
        "niners": ("49ers", "football"),
        "bucs": ("Buccaneers", "football"),
        "sixers": ("76ers", "basketball"),
    }


def test_an_alias_already_inside_its_token_gets_no_arm() -> None:
    """`9ers` is in `49ers`, so the plain ILIKE arm already reaches those rows.

    Verified on production 2026-09-10: `?q=9ers` returns 10 real 49ers markets
    while `?q=niners` returns 0. An arm for `9ers` would be a duplicate probe for
    zero extra recall — the same reasoning `_phrase_alias_alternatives` applies
    when it drops an alternative identical to the query.
    """

    assert "9ers" in CURATED_TEAM_ALIASES[("americanfootball_nfl", "San Francisco 49ers")]
    assert "9ers" not in team_nickname_search_expansions()
    assert "niners" in team_nickname_search_expansions()


def test_every_expansion_carries_a_sport_and_no_arm_can_be_unscoped() -> None:
    """The invariant, asserted on the data rather than on one example.

    An expansion with no category would build an arm with no sport term — the
    cross-league fan-out the (sport_key, name) key exists to prevent. The
    derivation SKIPS an unmappable sport prefix rather than emitting a bare
    alias, so this must hold for every row now and for every row added later.
    """

    for alias, (token, category) in team_nickname_search_expansions().items():
        assert token, f"{alias} derived an empty token"
        assert category, f"{alias} would build an UNSCOPED arm"


def test_the_canonical_token_is_the_last_word() -> None:
    assert _canonical_market_token("New England Patriots") == "Patriots"
    assert _canonical_market_token("San Francisco 49ers") == "49ers"
    assert _canonical_market_token("Philadelphia 76ers") == "76ers"


# --------------------------------------------------------------------------
# The arm
# --------------------------------------------------------------------------
def test_a_query_with_no_nickname_produces_no_arm() -> None:
    """The no-cost path, and it is the overwhelming majority of queries.

    [] means the UNION is byte-identical to today's, so no query pays for a
    feature it does not use. This is also what keeps the keystroke surface from
    inheriting a second index probe on every letter typed.
    """

    for query in (["nba", "champion"], ["fed"], ["patriots"], ["yank"], []):
        assert _team_nickname_futures_arms(query) == [], query


@pytest.mark.parametrize(
    "alias,token,category",
    [
        ("pats", "Patriots", "football"),
        ("revs", "Revolution", "soccer"),
        ("niners", "49ers", "football"),
        ("bucs", "Buccaneers", "football"),
    ],
)
def test_the_arm_matches_the_token_and_pins_the_sport(alias, token, category) -> None:
    arms = _team_nickname_futures_arms([alias])
    assert len(arms) == 1, f"{alias} produced {len(arms)} arms"
    sql = _sql(arms[0])
    assert token.lower() in sql.lower(), f"{alias} did not expand to {token}"
    assert "llm_sport_category" in sql, (
        f"{alias} built an UNSCOPED arm — this is the cross-sport fan-out: "
        "unscoped, `pats` serves 15 Caribbean Premier League cricket markets "
        "to a New England Patriots fan"
    )
    assert category in sql, f"{alias} was not scoped to {category}"


def test_the_arm_is_case_insensitive_on_the_typed_nickname() -> None:
    """A user typing `Pats` gets the same recall as one typing `pats`."""

    assert len(_team_nickname_futures_arms(["Pats"])) == 1
    assert len(_team_nickname_futures_arms(["PATS"])) == 1


def test_the_alias_composes_with_the_rest_of_the_query() -> None:
    """"pats win total" -> "Patriots win total", not just "Patriots".

    The surrounding terms are KEPT and ANDed, so the alias widens one token
    rather than discarding what else was typed. An alias that dropped the other
    terms would answer `pats win total` with every Patriots market there is.
    """

    arms = _team_nickname_futures_arms(["pats", "win", "total"])
    assert len(arms) == 1
    sql = _sql(arms[0]).lower()
    assert "patriots" in sql
    assert "win" in sql and "total" in sql, (
        f"the alias discarded the rest of the query: {sql}"
    )


def test_the_arm_is_name_only() -> None:
    """Like its `_alias_futures_arms` sibling: no outcome subquery.

    The outcome arm is the expensive half of futures recall — a subquery over
    3.2M `futures_outcomes` rows — and this class is missed by NAME. An alias is
    a cheap recall additive; it does not buy a second full search. This matters
    most on /typeahead, which pays it per keystroke.
    """

    sql = _sql(_team_nickname_futures_arms(["pats"])[0])
    assert "futures_outcomes" not in sql, (
        f"the nickname arm grew an outcome subquery: {sql}"
    )


# --------------------------------------------------------------------------
# The call sites
# --------------------------------------------------------------------------
def test_both_surfaces_actually_wire_the_nickname_arms_in() -> None:
    """The helper being correct is not the same as the route calling it.

    Every test above exercises `_team_nickname_futures_arms` directly, so
    deleting the two `.extend(...)` lines would leave them all green and ship the
    defect back. This is also what stops the /search-vs-/typeahead drift this
    file's neighbours record — the twin fix that reached one surface and not the
    other for three cycles.
    """

    for route in (search_events, typeahead_search):
        source = inspect.getsource(route)
        assert "_team_nickname_futures_arms(terms)" in source, (
            f"{route.__name__} no longer adds the nickname recall arms"
        )


def test_search_wires_the_nickname_arms_into_all_three_places() -> None:
    """🔴 RECALL ALONE IS NOT THE FIX, and this is the test that says so.

    `/search` uses its futures arms in THREE places, and the first shipped
    version of #4728 wired only the first:

      1. `_futures_where_or`    — the candidate set (recall)
      2. `_futures_tier1_arms`  — the arms `_fetch_futures_window` actually
                                  fetches the 20-row window from
      3. `_futures_tier_whens`  — the relevance tier that orders that window

    With only (1), the real-Postgres gate returned an **empty** futures list for
    `pats` and `revs`: the rows were in the candidate set and no query ever
    fetched them. Every unit test passed, because the helper was right and the
    route did call it.

    This is not a new lesson — the comment at `_futures_tier_whens` records
    LAT-P029 making the same mistake with the phrase aliases, where recall alone
    got `nba finals` from "unreachable" to "on the page", "which sounds like the
    fix and is not". A nickname with no tier lands in tier 2 with the
    outcome-only collisions and is ranked by `market_tier`, a market-QUALITY
    prior that is not about the query at all.

    A source guard rather than a behavioural one on purpose: the behaviour needs
    a real Postgres (it is covered in `tests/integration/`), while the wiring is
    exactly the thing a later refactor drops by accident.
    """

    source = inspect.getsource(search_events)
    assert "_futures_nickname_arms = _team_nickname_futures_arms(terms)" in source
    for wiring, what in (
        ("_futures_where_or.extend(_futures_nickname_arms)", "the candidate set"),
        ("list(_futures_nickname_arms)", "the tier-1 window arms"),
        ("or_(*_futures_nickname_arms)", "the relevance tier"),
    ):
        assert wiring in source, (
            f"the nickname arms are no longer wired into {what} — with recall "
            "alone the rows are candidates that nothing fetches, and `pats` "
            "returns an empty futures list while every unit test stays green"
        )
