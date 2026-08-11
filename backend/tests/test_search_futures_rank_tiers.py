"""LAT-P033 / #1732 — regression guard for how the futures page is RANKED.

Somebody types `fed` and gets Vladimir Fedoseev's chess tournament, Julie
Fedorchak's House race and the Polish Confederation party. Measured on production
2026-08-11 (v3770 `cd84f690`): `/api/events/search?q=fed` returned EIGHT futures,
FOUR of them substring collisions inside proper nouns, while "Who will be
confirmed as Fed Chair?" (58.9M volume) and "How many Fed rate cuts in 2026?"
(44.5M) did not appear at all.

TWO independent defects put them there, and each is guarded separately below,
because either one alone reproduces the symptom:

1. **The expansion REPLACED its term in the rank tsquery.** `fts_q` was built as
   ``exp if exp else term``, so `fed` (which expands to `federal reserve`) ranked
   against ``'feder' & 'reserv'`` — BOTH words required in the market NAME. Of the
   316 open markets whose name matches the query, **5 scored above zero and 311
   scored exactly 0.0**. With the relevance signal dead, `market_tier` decided the
   page — and that is a market-QUALITY prior, not a relevance signal, so tier-1
   "FedEx St. Jude Championship Winner" beat tier-2 "Who will be confirmed as Fed
   Chair?" at 3.6x less volume.

2. **The name/outcome tier was enforced too late to matter.**
   `_rerank_search_futures` has always put name-matches above outcome-only
   matches, but it runs AFTER the SQL `.limit(20)`. It reorders the page; it
   cannot refill it. When the LIMIT cut ACROSS the tiers, the name matches it
   would have promoted were never fetched.

These assert SHAPE, not wall-clock, and deliberately not response bodies: the
defect is an ORDERING property, and an ordering property is exactly what survives
a test that only checks that some rows came back. LAT-P002 was REVERTED after
shipping a futures change that returned HTTP 200 with the primary result class
missing — it read as "no matches" and survived a full deploy verification.
"""

import inspect

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.routes import events as events_route

SEARCH_SRC = inspect.getsource(events_route.search_events)
SEARCH_CODE = "\n".join(
    line for line in SEARCH_SRC.splitlines() if not line.lstrip().startswith("#")
)


def _compile(expr) -> str:
    return str(
        select(expr).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# ---------------------------------------------------------------------------
# Defect 1 — the expansion must WIDEN the rank query, never replace the term
# ---------------------------------------------------------------------------

def test_expansion_is_ored_with_its_term_not_substituted_for_it():
    """`fed` must still rank the lexeme `fed`, not only `federal reserve`."""
    sql = _compile(events_route._expanded_tsquery([("fed", "federal reserve")]))

    assert "'fed'" in sql, (
        "#1732 reintroduced: the original term is gone from the rank tsquery, so "
        "every market actually NAMED 'Fed ...' scores zero"
    )
    assert "'federal reserve'" in sql, "the expansion must still contribute"
    assert "||" in sql, (
        "term and expansion are no longer ORed — an AND here requires both "
        "readings in one name and matches almost nothing"
    )


def test_a_term_with_no_expansion_is_unchanged():
    """The no-expansion path must stay byte-identical in meaning.

    `red sox` compiled to ``websearch_to_tsquery('red sox')`` before and
    ``websearch_to_tsquery('red') && websearch_to_tsquery('sox')`` now; Postgres
    resolves both to ``'red' & 'sox'``. This pins that the rewrite did not quietly
    change queries it was never meant to touch — which is most of them.
    """
    sql = _compile(events_route._expanded_tsquery([("red", None), ("sox", None)]))

    assert "'red'" in sql and "'sox'" in sql
    assert "&&" in sql, "multi-term recall is an AND; an OR here would widen every query"
    assert "||" not in sql, "nothing to OR — neither term has an expansion"


def test_multi_term_ands_across_terms_and_ors_within_one():
    """`nba champion` -> ``'nba' & ('champion' | 'winner')``.

    The per-term OR must be GROUPED. Ungrouped, Postgres binds `&` tighter than
    `|` and the query means ``('nba' & 'champion') | 'winner'`` — which matches
    every market named "... Winner" in the database.

    SQLAlchemy emits those parentheses structurally, from the expression tree, so
    this property cannot be broken by dropping the `.self_group()` call (LAT-P033
    mutation-tested that: the compiled SQL is byte-identical either way). What it
    CAN be broken by is someone rebuilding this as a hand-written string, which is
    how `fts_q` — the thing this replaced — was built. So the emitted form is
    pinned here rather than assumed.
    """
    sql = _compile(events_route._expanded_tsquery([("nba", None), ("champion", "winner")]))

    assert "&& (" in sql, (
        "the expansion OR is no longer parenthesised as a unit; `&` binds tighter "
        "than `|`, so this now matches every market named '... Winner'"
    )
    or_group = sql[sql.index("&& (") :]
    assert "||" in or_group, "the OR is not inside the group the AND applies to"
    assert "'champion'" in or_group and "'winner'" in or_group
    # The AND term must sit OUTSIDE that group, not inside it.
    assert "'nba'" not in or_group, "the ANDed term was pulled into the OR group"


def test_empty_expansion_list_does_not_produce_a_rank_expression():
    assert events_route._expanded_tsquery([]) is None


# ---------------------------------------------------------------------------
# Defect 2 — the tier must be enforced in SQL, where the LIMIT is applied
# ---------------------------------------------------------------------------

def test_futures_order_by_carries_the_name_match_tier():
    """Without this key the LIMIT cuts across tiers and the reranker cannot recover."""
    assert "_futures_name_tier" in SEARCH_CODE, (
        "#1732 reintroduced: the futures ORDER BY no longer separates name matches "
        "from outcome-only matches, so outcome collisions take page-1 slots from "
        "markets the query is actually about"
    )
    assert "_futures_name_tier.asc()" in SEARCH_CODE


def test_the_tier_key_sorts_ahead_of_the_rank():
    """Tier before rank. Behind it, the key is decorative.

    `ts_rank_cd` is 0.0 for the overwhelming majority of name matches (311 of 316
    for `fed`), so a tier applied after the rank never breaks the tie it exists to
    break.
    """
    order_by = SEARCH_CODE[SEARCH_CODE.index("futures_query = ("):]
    order_by = order_by[order_by.index(".order_by("):]

    tier_at = order_by.index("_futures_name_tier")
    rank_at = order_by.index("futures_search_rank")
    assert tier_at < rank_at, (
        "the name-match tier is sorted AFTER ts_rank_cd, so it only ever breaks "
        "ties among rows that already scored equally — which is not the defect"
    )


def test_league_ticker_recall_outranks_outcome_only_collisions():
    """Tier 1 exists so award markets are not demoted into the junk.

    "nfl mvp" reaches "MVP Winner?" by ticker prefix (KXNFLMVP) with no "nfl" in
    the name. It is not a name match, but it is not a substring collision either,
    and collapsing those two into one bucket would sink a real answer.
    """
    assert "league_ticker_match is not None" in SEARCH_CODE
    assert "_futures_tier_whens.append((league_ticker_match, 1))" in SEARCH_CODE


def test_the_replaced_rank_string_is_gone():
    """The `exp if exp else term` rank string must not come back.

    Deleted rather than deprecated: a second path that still works is a second
    path that still gets used. The /typeahead copy (`ta_fts_q`) is deliberately
    untouched — it feeds `_fts_filter`, a WHERE predicate, so changing it moves
    RECALL rather than ranking.
    """
    assert "fts_q = " not in SEARCH_CODE, (
        "the substituting rank string is back in search_events; it is the whole of #1732"
    )
    assert "_expanded_tsquery(expanded)" in SEARCH_CODE


# ---------------------------------------------------------------------------
# The property both defects violated
# ---------------------------------------------------------------------------

def test_ranking_change_did_not_touch_recall():
    """This queue reorders the candidate set; it must not filter it.

    #1732 named two naive fixes to resist, both of which DELETE rows: dropping the
    outcome arm for short terms, and word-boundary matching. The arms in
    `_futures_where_or` are the recall contract, so a guard that only checked the
    ordering would not notice a fix that quietly shed a result class.
    """
    arms_at = SEARCH_CODE.index("_futures_where_or = [")
    arms = SEARCH_CODE[arms_at : SEARCH_CODE.index("]", arms_at)]

    assert "futures_name_match" in arms
    assert "futures_outcome_match" in arms, (
        "the outcome arm was dropped from recall — that is the naive fix #1732 "
        "explicitly refused, not the ranking fix"
    )
    assert "league_ticker_match" in arms


def test_the_python_reranker_still_runs_after_the_sql_tier():
    """SQL and Python must agree, not compete.

    The SQL tier fixes WHICH rows reach the page; `_rerank_search_futures` still
    owns ordering within it (volume, narrower-scope demotion, wrong-league). This
    pins that the SQL key did not become an excuse to delete the reranker.
    """
    assert "_rerank_search_futures(futures_markets_raw, expanded)" in SEARCH_CODE
