"""AN INTERIOR SUBSTRING MUST NOT OUTRANK A REAL PREFIX. #4572.

═══ WHAT WAS MEASURED ═══

Production `GET /api/events/search?q=yank`, 2026-09-10 01:35Z (#4572):

    0  M15 Hurghada: Ma**yank** Sharma vs Luis Klaus     <- a $15k ITF qualifier
    1  Istanbul 3: Timofey Skatov vs **Yank**i Erel
    2  Istanbul 3: **Yank**i Erel vs Radu Albot
    3  Colorado Rockies vs. New York **Yank**ees …       <- the actual answer

Slot 0's only connection to the query is four letters sitting in the MIDDLE of
an unrelated first name.

═══ THE MECHANISM, AND WHY THE FILED ONE WAS WRONG ═══

The issue blamed the substring ILIKE recall arm. That arm is real, but it is not
what ordered this list, and a fix aimed there would have been aimed at recall —
the one thing that must not move. Measured on production 2026-09-10:

    to_tsvector('english', '…New York Yankees…')  ->  'yanke'
    to_tsvector('english', '…Mayank Sharma…')     ->  'mayank'
    …@@ websearch_to_tsquery('english','yank')    ->  false  for BOTH

`Yankees` stems to `yanke`, which is not the lexeme `yank`, so the word test
rejects the REAL answer too. Both rows therefore sit in tier 2 with `ts_rank_cd`
**0.0**, and the page is decided by `market_tier`, `volume`, `updated_at` and
`id` — none of which is about the query. That is the pathology LAT-P111 and
`_expanded_tsquery` both document: when the relevance signal is structurally
dead, whatever sorts next decides the page.

═══ THE FIX, AND THE REFUSAL IT DOES NOT BREAK ═══

A DISCOUNTED last-token prefix score is added to the futures rank. A prefix is a
strictly stronger claim than the substring that admitted the row:

    to_tsvector('…New York Yankees…') @@ to_tsquery('yank:*')  ->  true
    to_tsvector('…Mayank Sharma…')    @@ to_tsquery('yank:*')  ->  false   (interior)

🔴 **Prefix matching is refused in `events.py`, in writing, naming this very
query.** `_futures_name_match_term`'s LAT-P037 docstring: "`to_tsquery('re:*')`
… even fix `yank` -> Yankees (#1757). It also matches `fed:*` -> `federico`,
which is the entire defect LAT-P033/LAT-P034 measured and closed."

That refusal is about **RECALL** — a prefix arm in the WHERE *fetches* rows that
are not answers. This change puts its prefix nowhere near a WHERE clause. The
candidate set, the tier CASE and every arm in `_futures_where_or` are unchanged,
so the LAT-P002 revert shape (`f98d8104` — the arm whose emptying reverted a
ship) is structurally out of reach. `TestTheRefusalStillHolds` is the control,
and it is the most important class in this file.

═══ WHAT IS TESTED HERE, AND WHAT CANNOT BE ═══

These are the PURE halves — the tsquery builder and the compiled recall SQL —
which need no Postgres and run in every CI job. The ORDERING claim itself is
Postgres semantics (`ts_rank_cd`, English stemming, the ORDER BY) and is guarded
in `tests/integration/test_search_recall_contract.py`, which the `search-recall`
job runs against a real database:

    test_an_interior_substring_does_not_outrank_a_real_prefix
    test_the_prefix_rank_did_not_buy_its_ordering_with_recall

The rank arithmetic behind that guard, measured on production so the numbers are
read rather than asserted:

    row                              rank_before   prefix   rank_after
    Colorado Rockies vs. NY Yankees        0.0        0.4        0.2
    M15 Hurghada: Mayank Sharma            0.0        0.0        0.0

and the `fed` control, which is the case the refusal exists to protect:

    Federal Reserve … decision?            0.4        0.4        0.6   tier 0
    Federico Coria vs Thiago Tirante       0.0        0.4        0.2   tier 2
    Russian Federation to win?             0.0        0.4        0.2   tier 2

The junk rises, and it cannot matter: `_futures_name_tier` is the FIRST ORDER BY
key and this score is folded into the SECOND, so a tier-2 row cannot cross a
tier-0 one however it scores. Even ignoring the tier, 0.6 > 0.2.
"""

import inspect

from sqlalchemy.dialects import postgresql

from app.routes import events
from app.routes.events import (
    _event_name_match,
    _futures_name_match_term,
    _last_token_prefix_tsquery,
    _team_prefix_tsquery,
    _SEARCH_FUTURES_PREFIX_RANK_WEIGHT,
    _SEARCH_TEAM_PREFIX_RANK_WEIGHT,
)


def _sql(clause) -> str:
    """Compile to Postgres SQL with literals inlined, so an assertion can read
    the actual tsquery string rather than a bind marker."""
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestThePrefixTsqueryDiscriminates:
    """The builder, at the boundary that decides whether the fix engages."""

    def test_yank_builds_a_prefix_tsquery(self):
        assert _sql(_last_token_prefix_tsquery("yank")) == "to_tsquery('english', 'yank:*')"

    def test_only_the_last_token_is_a_prefix(self):
        """`nba champion`: `nba` must still match as a whole word. A prefix on
        every token would reopen every case the FTS gate closed."""
        assert (
            _sql(_last_token_prefix_tsquery("nba champion"))
            == "to_tsquery('english', 'nba & champion:*')"
        )

    def test_a_two_character_query_gets_no_prefix_arm_at_all(self):
        """🔴 THE NO-OP CASE, and it is a real guard rather than a formality.

        `re` is below `_has_extractable_trigram` — the ONE cliff this surface
        has (LAT-P013/LAT-P037 replaced `len(term)` with the alnum-run rule so a
        second copy could not drift). Below it there is no word to be right
        about. Returning None here is what makes the compiled SQL BYTE-IDENTICAL
        to before the change for this whole class of query, which is why `re`
        cannot have regressed: there is nothing to regress.
        """
        assert _last_token_prefix_tsquery("re") is None

    def test_an_empty_query_is_none_not_a_match_nothing_predicate(self):
        """The return contract. A caller that treated None as a clause would
        AND a match-nothing into the rank and silently zero it."""
        assert _last_token_prefix_tsquery("") is None
        assert _last_token_prefix_tsquery("   ") is None


class TestOneCopyOfTheRule:
    """The two consumers must never disagree about what a prefix IS.

    This file has already paid twice for a duplicated boundary rule — the
    `_SEARCH_MIN_OUTCOME_MATCH_CHARS` drift between /search and /typeahead that
    LAT-P013 reconciled, and the `len(term)` copy LAT-P037 replaced. #4572 made
    the teams helper (#4126) a second caller rather than a second copy.
    """

    def test_the_teams_helper_delegates_rather_than_reimplementing(self):
        for q in ("yank", "yanks", "red sox", "super bowl", "nba champion"):
            assert _sql(_team_prefix_tsquery(q)) == _sql(_last_token_prefix_tsquery(q)), (
                f"the teams and futures prefix rules have drifted on {q!r} — "
                "that is the LAT-P013 defect for the third time"
            )

    def test_the_boundary_agrees_on_both_surfaces(self):
        assert _team_prefix_tsquery("re") is None
        assert _last_token_prefix_tsquery("re") is None


class TestTheDiscountIsARealDiscount:
    """The weight carries an invariant, not just a number."""

    def test_strictly_between_zero_and_one(self):
        """Above 0 so a prefix-only row is ORDERED rather than left to a
        tiebreak that is not about the query; below 1 so a whole-lexeme match —
        which earns on BOTH terms — always stays above a row that merely starts
        the same way. `yankees` must still answer with the Yankees."""
        assert 0 < _SEARCH_FUTURES_PREFIX_RANK_WEIGHT < 1

    def test_each_surface_multiplies_by_its_own_constant(self):
        """Same VALUE today, deliberately separate NAMES — the Teams population
        is curated and strips individual-sport athletes, the futures feed does
        not, so tuning one must not silently move the other.

        Asserted on the call sites rather than on the values, because while the
        two numbers are equal a value comparison cannot tell a wired-up constant
        from an unused one and would pass on a route that multiplied by the
        Teams weight.
        """
        team_src = inspect.getsource(events._team_search_rank)
        assert "_SEARCH_TEAM_PREFIX_RANK_WEIGHT" in team_src
        assert "_SEARCH_FUTURES_PREFIX_RANK_WEIGHT" not in team_src

        route_src = inspect.getsource(events.search_events)
        assert "_SEARCH_FUTURES_PREFIX_RANK_WEIGHT" in route_src
        assert "_SEARCH_TEAM_PREFIX_RANK_WEIGHT" not in route_src


class TestTheRefusalStillHolds:
    """🔴 THE CONTROL. The refusal is about RECALL, and #4572 is ordering-only.

    A change that widened the predicate instead of the rank would fix `yank` and
    reopen `fed` -> `federico`. Without this class it would go green.
    """

    def test_the_prefix_reaches_the_rank_and_nothing_else(self):
        """🔴 THE CLAIM THE WHOLE CHANGE RESTS ON, asserted rather than promised.

        "Ordering only" is what makes this permissible against a refusal written
        in capitals three times in `events.py`. The two compiled-SQL controls
        below cover the shared recall HELPERS; this covers the route body, where
        a later edit could reuse the already-built tsquery in a predicate and
        pass every other test in this file.

        A source scan is the honest instrument here: the futures WHERE is
        assembled from a dozen locals inside a 900-line handler, so there is no
        single object to compile and read.
        """
        route_src = inspect.getsource(events.search_events)
        uses = [
            line.strip()
            for line in route_src.splitlines()
            if "_futures_prefix_tsquery" in line and not line.strip().startswith("#")
        ]
        assert uses, (
            "the prefix rank is gone from the route — #4572 has been reverted "
            "without this suite noticing"
        )
        forbidden = (".where(", ".filter(", "and_(", "or_(", "candidate_filter")
        for line in uses:
            assert not any(token in line for token in forbidden), (
                f"the #4572 prefix tsquery reached a PREDICATE: {line!r}. It is "
                "permitted in the ORDER BY only — in a WHERE it fetches rows "
                "that are not answers, which is exactly what LAT-P037 refuses."
            )
        # Whitespace-flattened, because the fold spans four physical lines and a
        # per-line test cannot see it — the first draft of this assertion failed
        # against the very code it was written for.
        flat = " ".join(route_src.split())
        fold = "futures_search_rank = futures_search_rank +"
        assert fold in flat, (
            "the prefix score is no longer ADDED to the futures rank. If it is "
            "now assigned outright, the discount is gone and a prefix-only row "
            "can outrank a whole-lexeme match — `yankees` stops answering with "
            "the Yankees."
        )
        assert "_futures_prefix_tsquery" in flat[flat.index(fold):][:320], (
            "the prefix tsquery is built but is not what the rank is folding in, "
            "so it orders nothing"
        )

    def test_the_futures_name_arm_never_gets_a_prefix(self):
        """LAT-P037/#1757. This is the arm the refusal names."""
        for term in ("fed", "yank", "re", "sun"):
            sql = _sql(_futures_name_match_term(term, None))
            assert ":*" not in sql, (
                f"a prefix arm leaked into the FUTURES NAME RECALL predicate for "
                f"{term!r}. #4572 adds its prefix to the ORDER BY only — a prefix "
                "here fetches rows that are not answers, which is the entire "
                "defect LAT-P033/LAT-P034 measured and closed."
            )

    def test_the_futures_name_arm_keeps_its_expansion_form_too(self):
        """The expanded call is a different code path and needs its own read —
        `fed` carries the expansion `federal reserve` in production."""
        sql = _sql(_futures_name_match_term("fed", "federal reserve"))
        assert ":*" not in sql

    def test_the_event_predicate_keeps_its_trigram_servable_recall_arm(self):
        """LAT-P002/#1494 (1c). Read precisely: the predicate DOES contain an
        FTS conjunct, AND-ed beside the ILIKE, and that is fine — what LAT-P002
        removed was an FTS arm inside the top-level OR, where one unindexable
        branch forces a seq scan of `events` (the ~20s median; 252 -> 90ms).

        So the guard is: the ILIKE recall arm survives, and #4572 added nothing.
        """
        sql = _sql(_event_name_match("yankees", None))
        assert "ILIKE" in sql.upper(), "the trigram-servable recall arm is gone"
        assert ":*" not in sql, "a prefix arm leaked into the event predicate"
