"""THE DROPDOWN'S POOL IS CHOSEN BY THE QUERY, NOT BY VOLUME. #4723.

═══ WHAT WAS MEASURED ═══

Production `GET /api/events/typeahead?q=nfl`, 2026-09-10 08:45Z — five futures
suggestions, four of them inflation:

    NFL Champion 2027                       <- the only real one
    How high will inflation get in 2026?    <- i-NFL-ation
    Inflation in August 2026 (CPI YoY)      <- i-NFL-ation
    How high will inflation get this year?  <- i-NFL-ation
    Brazil Annual Inflation 2026            <- i-NFL-ation

`q=pats` (94 log hits) offered five Huergo/Kor**patsch** tennis-doubles rows and
no Patriots; `q=nba` offered WNBA, Caribbea**n**-Premier-League and Vuelta a
Espana (via Tri**nba**go Knight Riders); the `q=ipo` pool was led by Vuelta a
Espana. `GET /api/events/search` is CLEAN on all of these — the two surfaces
share `_rerank_search_futures` but NOT the candidate query, and the LOOK rig
cannot type, so the dropdown is only ever visible through an API read. That is
why this sat unseen.

═══ THE MECHANISM: THE POOL, NOT THE RERANKER ═══

The typeahead futures query ordered its candidates by `market_tier`, `volume`
and nothing else — a market-QUALITY prior and a popularity prior, neither about
what the user typed — then took 20. `_rerank_search_futures` runs AFTER that
LIMIT, so it can only reorder rows SQL already chose. Measured for `nfl`:

    pool slot   tier   volume       name
    0           1      41,558,524   NFL Champion 2027
    1           1      —            NFL Super Bowl Winner
    2-19        2      1,317,277…   18 inflation markets

**18 of 20 slots were imposters**, while **181** genuine open NFL futures sat
below the cut — counted on production 2026-09-10 09:20Z as open markets whose
NAME whole-lexeme-matches `nfl` (`@@ websearch_to_tsquery('english','nfl')`),
against 257 by bare `ILIKE '%nfl%'`; the gap between those two numbers is the
imposter class itself. No amount of reranking fills five good slots out of two.
This is LAT-P033's page-boundary argument (`fed`: 7 of 20 junk, 311 name
matches scoring 0.0) on the surface that never got the fix.

🔴 So `_rerank_search_futures._name_match` is NOT the fix, and that is the
finding rather than an aside. It is a plain `t in n` substring test and it does
class "i**nfl**ation" as a name match — but tightening it refills the same slots
from the same poisoned pool.

═══ WHY TWO KEYS, AND WHY THIS ORDER ═══

#4723 proposed ONE key: the last-token prefix test #4572 added to /search.
Measured on production, prefix-alone is not enough and on one real query it is
**worse than live**:

    q=fed (73 log hits)   prefix-alone            word-then-prefix
    0                     Next German federal…    Who will be confirmed as Fed Chair?
    1                     Brazil Federal District…How many Fed rate cuts in 2026?
    2                     Next Canadian federal…  Fed decision in Sep 2026?

`fed:*` prefixes `feder`, so the one-key form hands the page to the
Con-fed-eration / Fed-erico class that `_expanded_tsquery` documents at length.
Same shape on `nfl`, where prefix-alone trades i-NFL-ation for Netflix (NFLX) —
a genuine prefix that is not the answer.

A whole-lexeme key above the prefix key answers both: 5/5 Federal Reserve
markets for `fed`, 5/5 real NFL markets for `nfl`, 20/20 NBA for `nba`, 5/5 IPO
for `ipo`. It is the cheap analogue of what /search already runs
(`_futures_name_tier` + `futures_search_rank`), a boolean `@@` rather than a
`ts_rank_cd` because this surface is on a keystroke budget and the pool only
needs the name matches SEPARATED from the collisions — `market_tier`/`volume`
below still order them, and the reranker sorts the survivors by volume anyway.

═══ WHAT IS TESTED HERE, AND WHAT CANNOT BE ═══

These are the PURE halves — placement, provenance and the refusal — which need
no Postgres and run in every CI job. The ORDERING claim is Postgres semantics
and is guarded in `tests/integration/test_search_recall_contract.py`, which the
`search-recall` job runs against a real database:

    test_the_typeahead_pool_is_chosen_by_the_query_not_by_volume
    test_a_genuine_prefix_that_is_not_the_answer_does_not_take_the_pool
    test_the_typeahead_pool_keys_did_not_buy_their_ordering_with_recall

═══ WHAT #4723 DOES NOT FIX ═══

`pats` — the query that opened the issue. Measured on production 2026-09-10:
**53 open Patriots futures, ZERO containing the substring `pats`**;
`websearch_to_tsquery('pats')` is the lexeme `pat` while "Patriots" stems to
`patriot`, so no whole-word arm reaches them either; and no alias expands
`pats`. They are not in the candidate set AT ALL, so no ORDER BY can reach
them — only a recall change could, and a prefix arm in the WHERE is precisely
what LAT-P037 refuses. Same class, same log: `revs` (91 hits) and `niners` (60
hits) return ZERO futures candidates. That is a RECALL gap and has its own
issue; the recall CONTROL in the integration file pins the half #4723 owns.
"""

import inspect

from sqlalchemy.dialects import postgresql

from app.routes import events
from app.routes.events import _last_token_prefix_tsquery


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _typeahead_src() -> str:
    return " ".join(inspect.getsource(events.typeahead_search).split())


def _relevance_keys_literal() -> str:
    """The list literal that builds the two keys, so their ORDER can be read."""
    flat = _typeahead_src()
    start = flat.index("_ta_futures_relevance_order_keys = (")
    return flat[start: flat.index("futures_query = (", start)]


def _typeahead_order_by() -> str:
    """The typeahead futures ORDER BY, flattened, anchored on a token that
    exists ONLY in that block.

    `.order_by(` appears several times in `typeahead_search` and the FIRST one
    belongs to the events query, so anchoring on it reads the wrong statement —
    the mistake #4572's placement test already had to correct one route over.
    """
    flat = _typeahead_src()
    marker = "*_ta_futures_relevance_order_keys,"
    assert marker in flat, (
        "the #4723 keys are not spliced into any ORDER BY — the typeahead pool "
        "is back to being chosen by `market_tier` and `volume`, which is the "
        "defect"
    )
    return flat[flat.index(marker):]


class TestThePoolIsOrderedByTheQueryFirst:
    """Placement IS the fix, and every direction of it is load-bearing."""

    def test_the_keys_sort_above_the_quality_priors(self):
        """Below `market_tier`/`volume` the keys would never fire: those are
        precisely what chose the 18 imposters."""
        order_by = _typeahead_order_by()
        keys_at = order_by.index("*_ta_futures_relevance_order_keys")
        tier_at = order_by.index("FuturesMarket.market_tier.asc()")
        volume_at = order_by.index("FuturesMarket.volume.desc()")

        assert keys_at < tier_at < volume_at, (
            "the #4723 keys have moved. They must sort ABOVE `market_tier` and "
            "`volume` — a pool chosen by a market-quality prior and a trading "
            "prior is the defect, not the baseline."
        )

    def test_a_sub_trigram_query_gets_no_relevance_keys_at_all(self):
        """🔴 THE LATENCY GATE, and it is a real guard rather than a formality.

        Both keys are computed per candidate row, and a sub-trigram query
        matches most of the table. Measured on production 2026-09-10 over
        `%re%`, INTERLEAVED across four rounds so ordering bias cannot fake it
        (the trap #4572 fell into and had to re-measure):

            baseline     899 /  465 /  524 /  397 ms
            + word key  1875 / 2189 / 1248 / 1077 ms

        **2-4x, every round**, on the surface that fires per keystroke and that
        already measured 12.06s for `q=re` before LAT-P010 — where the stage
        SHEDS rather than waits, so the cost is paid in missing suggestions.
        Above the cliff the same measurement shows nothing: `fed` 35.6→35.9ms.

        Binding both keys to `_last_token_prefix_tsquery`'s None contract makes
        the compiled SQL below the cliff byte-identical to before #4723, so that
        whole class cannot have regressed in ordering OR in latency. A change
        that hoists the word key out of this branch to "fix `re` too" has bought
        an ordering nobody asked for with a second of latency.
        """
        literal = _relevance_keys_literal()
        assert "[] if _ta_futures_prefix_tsquery is None" in literal, (
            "the #4723 keys are no longer gated on the shared boundary, or the "
            "sub-trigram branch no longer yields an EMPTY list — either way a "
            "2-char query now pays 2-4x for keys that cannot help it, and the "
            "byte-identical-SQL claim for `re`/`la`/`ai` is void"
        )
        # The contract that branch rests on, asserted rather than assumed.
        assert _last_token_prefix_tsquery("re") is None

    def test_the_whole_word_key_outranks_the_prefix_key(self):
        """🔴 THE MEASUREMENT, not a preference.

        Swap these two and `fed` regresses BELOW what production served before
        the fix: `fed:*` prefixes `feder`, so "Next German federal election
        winner?" takes slot 0 from "Who will be confirmed as Fed Chair?". The
        integration suite reproduces it with the NFLX rows.
        """
        literal = _relevance_keys_literal()
        assert literal.index("_expanded_tsquery(ta_expanded)") < literal.index(
            "_ta_futures_prefix_tsquery)"
        ), (
            "the PREFIX key now sorts above the WHOLE-WORD key. That is #4723 "
            "as originally filed, and it was measured worse than live on `fed` "
            "— re-read the production table in this file's docstring before "
            "keeping it."
        )


class TestOneCopyOfTheRule:
    """The prefix rule has one definition. This file has already paid twice for
    a duplicated boundary — the `_SEARCH_MIN_OUTCOME_MATCH_CHARS` drift between
    /search and /typeahead that LAT-P013 reconciled, and the `len(term)` copy
    LAT-P037 replaced. #4572 made the teams helper a caller rather than a copy;
    #4723 makes typeahead the third caller, not the second copy."""

    def test_typeahead_calls_the_shared_prefix_helper(self):
        src = inspect.getsource(events.typeahead_search)
        flat = " ".join(src.split())
        assert "_ta_futures_prefix_tsquery = _last_token_prefix_tsquery(q)" in flat, (
            "typeahead is no longer building its prefix through the shared "
            "helper. A second definition of what a prefix IS is the LAT-P013 "
            "defect for the third time."
        )

    def test_the_boundary_is_the_shared_one(self):
        """Below `_has_extractable_trigram` there is nothing to be right about,
        and the helper returns None so the ORDER BY keeps its old shape."""
        assert _last_token_prefix_tsquery("re") is None
        assert _sql(_last_token_prefix_tsquery("nfl")) == "to_tsquery('english', 'nfl:*')"

    def test_the_word_key_widens_its_expansion_instead_of_replacing_it(self):
        """#1732, which cost 311 of 316 `fed` name matches on /search.

        `ta_fts_q` sits three lines away and is built `exp if exp else term`, so
        an expansion REPLACES the term it was meant to widen — using it here
        would zero this key for every expanded query and silently leave the
        surface on the prefix-only ordering measured worse than live.
        """
        literal = _relevance_keys_literal()
        word_key = literal[: literal.index(".desc()")]
        assert "_expanded_tsquery(ta_expanded)" in word_key, (
            "the #4723 word key is not built from `_expanded_tsquery`"
        )
        assert "ta_fts_q" not in word_key, (
            "the word key is built from `ta_fts_q`, whose expansions REPLACE "
            "their terms — that is #1732 verbatim"
        )


class TestTheRefusalStillHolds:
    """🔴 THE CONTROL, and the most important class in this file.

    `events.py` refuses prefix MATCHING in writing (LAT-P037), and the refusal
    is about RECALL: a prefix arm in the WHERE fetches rows that are not
    answers (`fed:*` -> `federico`, the 25 rows LAT-P033/LAT-P034 closed).
    #4723 is permitted only because it puts both keys in the ORDER BY. A change
    that widened the predicate instead would pass every other test here and
    would be the LAT-P002 revert shape.
    """

    def test_neither_key_reaches_a_predicate(self):
        src = inspect.getsource(events.typeahead_search)
        uses = [
            line.strip()
            for line in src.splitlines()
            if (
                "_ta_futures_prefix_tsquery" in line
                or "_ta_futures_relevance_order_keys" in line
                or "_ta_futures_name_vector" in line
            )
            and not line.strip().startswith("#")
        ]
        assert uses, (
            "the #4723 keys are gone from the route — the change has been "
            "reverted without this suite noticing"
        )
        forbidden = (".where(", ".filter(", "and_(", "or_(", "candidate_filter", "append(")
        for line in uses:
            assert not any(token in line for token in forbidden), (
                f"a #4723 ORDER BY key reached a PREDICATE: {line!r}. In a WHERE "
                "it FETCHES rows that are not answers, which is exactly what "
                "LAT-P037 refuses — and it would make the candidate set differ "
                "from the one the cert measured."
            )

    def test_the_candidate_arms_are_untouched_by_the_ordering_keys(self):
        """The recall side is assembled above the ORDER BY and must not mention
        either key. `ta_futures_where` IS the candidate set."""
        src = inspect.getsource(events.typeahead_search)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "ta_futures_where" not in stripped:
                continue
            assert "prefix" not in stripped and "word_key" not in stripped, (
                f"a #4723 key was appended to the typeahead candidate arms: "
                f"{stripped!r}. Recall must be byte-identical."
            )
