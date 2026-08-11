"""LAT-P036 — three named search-recall gaps, and the guard for each.

All three were carried across multiple cycles as ONE bullet. They are three
different defects in three different layers, and bundling them is why the first
two survived six cycles: a fix aimed at the wrong layer cannot land.

1. **#1761 — the English stemmer is asymmetric.** `president` stems to `presid`,
   the text "Presidential" to `presidenti`. Different lexemes, so `ts_rank_cd`
   over the name vector scored market 112897 — "Presidential Election Winner
   2028", **667M volume, the largest open market in the corpus** — exactly 0,
   while every market merely named "President" scored 0.4. Measured live: the
   query `president` led with **"Presidents Cup Winner", a GOLF market with 2,359
   volume**, purely because the real answer could not score.

2. **`nba finals` is not that bug at all.** Kalshi names the market "2026 Pro
   Basketball Champion" (id 350, ticker `KXNBA-26`); neither query word appears
   in the name, so no stemmer and no one-token synonym can ever reach it. It is
   an ALIAS problem. Getting it merely *recalled* was not the fix either — alias
   rows landed in tier 2 and sorted below five ticket-price markets.

3. **The wrong-league guard had gone blind.** `_demote_wrong_league` matches
   `\\bwnba\\b` in the market NAME, but Kalshi renamed the corpus to "Women's Pro
   Basketball". Counted on production 2026-08-11: 75 open markets with ticker
   `kxwnba%`, only 29 with the `wnba` token. 46 of 75 were invisible to the guard
   whose entire job is to catch them, and nothing failed when it stopped working.

These assert SHAPE and BEHAVIOUR, never wall-clock, so they are deterministic in
CI. Where a value is pinned it is written as a LITERAL rather than imported from
the module under test — LAT-P026 shipped a guard that read the same constant it
asserted and therefore pinned nothing.

NOTE ON THE BASE. This suite is written against master AFTER `e22576db`, the
revert of LAT-P035's futures word test. Nothing here depends on that word test:
all four behaviours guarded below are independent of it, which is exactly why
this queue was re-cut onto the post-revert base rather than stacked on the
reverted commit.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

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
# 1 — #1761, the stemmer asymmetry
# ---------------------------------------------------------------------------

def test_president_expands_to_presidential() -> None:
    """The one entry that closes #1761. Asserted as a literal pair, not by
    re-reading the table into the assertion."""
    assert events_route._SEARCH_TERM_SYNONYMS.get("president") == "presidential"


def test_the_expansion_reaches_the_rank_so_the_market_can_sort() -> None:
    """This is a RANK fix, and the rank is the arm that must carry the expansion.

    Recall was never the problem here: the substring ILIKE `%president%` always
    matched "Presidential Election Winner 2028". What failed was `ts_rank_cd`,
    which scored it 0 because `presid` != `presidenti`, so it sorted below every
    market merely NAMED "President" and never reached the page.
    """
    sql = _compile(events_route._expanded_tsquery([("president", "presidential")]))

    assert "'president'" in sql, "the original term was dropped from the rank query"
    assert "'presidential'" in sql, (
        "#1761 reintroduced: the rank query still only asks for 'president', which "
        "stems to 'presid' and cannot match the text lexeme 'presidenti'"
    )
    assert "||" in sql, (
        "the expansion REPLACED the term instead of widening it — that is #1732, "
        "and it zeroes the rank of every market named the other way"
    )


def test_the_expansion_also_widens_recall_and_cannot_narrow_it() -> None:
    """Additive by construction, which is what this arm's revert history demands.

    Every name containing "presidential" already contains "president", so the
    added ILIKE is a strict no-op on the substring half — it cannot remove a row
    that reaches the user today.
    """
    sql = _compile(
        events_route._build_expanded_ilike(
            events_route.FuturesMarket.name, "president", "presidential"
        )
    )

    # `literal_binds` doubles the LIKE wildcards (psycopg escaping).
    assert "'%%president%%'" in sql
    assert "'%%presidential%%'" in sql
    assert " OR " in sql, "the expansion must be ORed with the term, never replace it"


def test_the_synonym_is_one_directional_on_purpose() -> None:
    """`presidential` -> `president` is a DIFFERENT change and is refused here.

    It would widen `presidential` to the 86 open markets named "President" but
    not "Presidential" ("Putin out as President of Russia by...?") — a real
    recall expansion with no measured demand. The stemmer asymmetry runs one way,
    so the fix does too. Pinned so a later "let's make it symmetric" tidy-up has
    to argue with the reason rather than discover it.
    """
    assert "presidential" not in events_route._SEARCH_TERM_SYNONYMS, (
        "the reverse mapping was added without its own before/after measurement"
    )


# ---------------------------------------------------------------------------
# 2 — `nba finals`: an alias, and a tier that makes the alias worth having
# ---------------------------------------------------------------------------

def test_nba_finals_resolves_to_the_phrase_the_corpus_actually_uses() -> None:
    """Market 350 is named "2026 Pro Basketball Champion" — no `nba`, no `finals`."""
    assert ["pro", "basketball", "champion"] in events_route._phrase_alias_alternatives(
        ["nba", "finals"]
    )


def test_the_alias_composes_with_the_rest_of_the_query() -> None:
    """"2027 nba finals" must keep 2027 rather than being a whole-query-only match."""
    alternatives = events_route._phrase_alias_alternatives(["2027", "nba", "finals"])
    assert ["2027", "pro", "basketball", "champion"] in alternatives


def test_the_alias_arm_is_name_only_and_carries_the_champion_expansion() -> None:
    """Name-only is deliberate: the outcome arm is the expensive half of futures
    recall, and this class is missed by NAME. `champion` must still pick up its
    `winner` expansion so "…Champion" and "…Winner" phrasings both resolve."""
    arms = events_route._alias_futures_arms(["nba", "finals"])
    assert len(arms) == 1
    sql = _compile(arms[0])

    assert "futures_markets.name" in sql
    assert "futures_outcomes" not in sql, (
        "the alias arm grew an outcome subquery — that is a second full search, "
        "not a cheap recall additive"
    )
    assert "'%%pro%%'" in sql and "'%%basketball%%'" in sql
    assert "'%%winner%%'" in sql, "the champion->winner expansion was lost"


def test_alias_hits_are_tier_eligible() -> None:
    """Recall alone left market 350 at position 11, below five ticket-price rows.

    Alias rows rank against the LITERAL query (`'nba' && 'finals'`) and score 0,
    so without a tier the ordering fell through to `market_tier` — a market-
    QUALITY prior that is not about the query at all.
    """
    assert "if _futures_alias_arms:" in SEARCH_CODE, (
        "alias hits are no longer tiered; they sort with the outcome-only "
        "substring collisions and the aliased market cannot reach page one"
    )
    assert "_futures_tier_whens.append((or_(*_futures_alias_arms), 1))" in SEARCH_CODE


def test_an_alias_hit_does_not_outrank_a_literal_name_match() -> None:
    """Tier 1, never 0. Tier 0 means the name matches what the user TYPED; an
    alias matches a phrasing we substituted on their behalf."""
    assert "_futures_tier_whens = [(futures_name_match, 0)]" in SEARCH_CODE
    assert "_futures_alias_arms), 0))" not in SEARCH_CODE, (
        "alias hits were promoted to tier 0, where they tie with literal name matches"
    )


def test_the_no_alias_path_adds_no_tier_branch() -> None:
    """The overwhelming majority of queries have no alias and must compile the
    same SQL they did before. `_alias_futures_arms` returning [] is what makes the
    `if` above a genuine no-op rather than an always-true branch."""
    assert events_route._alias_futures_arms(["red", "sox"]) == []
    assert events_route._alias_futures_arms(["president"]) == []


def test_the_alias_arms_reach_recall_and_the_tier_from_one_list() -> None:
    """One list feeds both, so recall and tier cannot disagree about what an
    alias hit is — the bug class LAT-P033 fixed between SQL and Python."""
    assert "_futures_alias_arms = _alias_futures_arms(terms)" in SEARCH_CODE
    assert "_futures_where_or.extend(_futures_alias_arms)" in SEARCH_CODE


# ---------------------------------------------------------------------------
# 3 — the wrong-league guard had gone blind to the corpus
# ---------------------------------------------------------------------------

def _m(name: str, external_id: str | None = None):
    return SimpleNamespace(name=name, external_id=external_id)


NBA_QUERY = [("nba", None), ("finals", None)]


def test_wnba_is_demoted_by_ticker_when_the_name_no_longer_says_wnba() -> None:
    """The live corpus case: "Women's Pro Basketball Champion" / `KXWNBA-26`
    carries no `wnba` token at all, so the name test alone let it through."""
    nba = _m("2026 Pro Basketball Champion", "KXNBA-26")
    wnba = _m("Women's Pro Basketball Champion", "KXWNBA-26")

    assert events_route._demote_wrong_league([wnba, nba], NBA_QUERY) == [nba, wnba]


def test_the_name_test_still_fires_for_sources_without_a_kalshi_ticker() -> None:
    """The ticker is added ALONGSIDE the name test, not instead of it. A
    Polymarket row has no `kx…` external_id and must still be caught."""
    nba = _m("2026 Pro Basketball Champion", "KXNBA-26")
    wnba = _m("WNBA: 2026 MVP", "0xabc123")

    assert events_route._demote_wrong_league([wnba, nba], NBA_QUERY) == [nba, wnba]


def test_the_correct_league_ticker_is_never_demoted() -> None:
    """`kxnba` must not match the `kxwnba` prefix — the distinction the whole
    guard rests on. A prefix test that got this backwards would sink every real
    NBA market to the bottom of its own query."""
    nba = _m("2026 Pro Basketball Champion", "KXNBA-26")
    mvp = _m("Pro Basketball MVP Winner", "KXNBAMVP-27")

    assert events_route._demote_wrong_league([nba, mvp], NBA_QUERY) == [nba, mvp]


def test_an_explicit_wnba_query_keeps_its_own_markets() -> None:
    """Demotion is relative to what was asked for. Somebody typing `wnba mvp`
    must not have every result demoted."""
    wnba = _m("Women's Pro Basketball MVP Winner", "KXWNBAMVP-26")
    other = _m("Pro Basketball MVP Winner", "KXNBAMVP-27")

    assert events_route._demote_wrong_league(
        [wnba, other], [("wnba", None), ("mvp", None)]
    ) == [wnba, other]


def test_demotion_reorders_and_never_filters() -> None:
    """A stable partition over an already-fetched page. If this ever drops a row
    it becomes a recall change wearing a ranking change's clothes — which is the
    shape LAT-P002 was reverted for."""
    markets = [
        _m("Women's Pro Basketball Champion", "KXWNBA-26"),
        _m("2026 Pro Basketball Champion", "KXNBA-26"),
        _m("Women's Pro Basketball MVP Winner", "KXWNBAMVP-26"),
        _m("Pro Basketball MVP Winner", "KXNBAMVP-27"),
    ]
    out = events_route._demote_wrong_league(list(markets), NBA_QUERY)

    assert len(out) == len(markets)
    assert {id(m) for m in out} == {id(m) for m in markets}
    # Correct-league rows keep their relative order, and so do the demoted ones.
    assert [m.name for m in out] == [
        "2026 Pro Basketball Champion",
        "Pro Basketball MVP Winner",
        "Women's Pro Basketball Champion",
        "Women's Pro Basketball MVP Winner",
    ]


def test_a_market_with_no_external_id_does_not_crash_the_guard() -> None:
    """`external_id` is nullable. A None here used to be unreachable because the
    guard never read the column; it is reachable now."""
    nba = _m("2026 Pro Basketball Champion", "KXNBA-26")
    orphan = _m("Some Basketball Market", None)

    assert events_route._demote_wrong_league([nba, orphan], NBA_QUERY) == [nba, orphan]
