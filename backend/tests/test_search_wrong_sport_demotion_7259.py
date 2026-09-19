"""#7259 — a bare club name must not answer with another SPORT's club.

WHAT A READER SAW. `https://bainluck.com/search?q=astros`, production `816a57c6`,
2026-09-19 16:42Z. The section headed **ANSWERS**, card titled **ASTROS**, was
headlined:

    Dorados de Chihuahua vs Astros de Jalisco    Dorados de Chihuahua 38%   Sep 20

above four genuine Houston Astros markets inside the same card, and the answer it
printed named neither the query nor even the *Astros de Jalisco* half of its own
title. The page's own TEAMS section had resolved the query to exactly one club —
Houston Astros (MLB) — and all 39 games below agreed.

THE ROW IS NOT MISLABELLED, and that mattered more than anything else here. The
first reading was that an LLM had filed a *Liga Mexicana de Béisbol* fixture as
`basketball`, which would have made any category-keyed fix a fix keyed on a data
error: right on this specimen, wrong in general, and inert the day the label was
corrected. The row disproves it —

    id 61496478  source kalshi
    external_id KXLNBPGAME-26SEP201915DORAST
    llm_sport_category basketball
    canonical_market_key basketball::championship:2026

`KXLNBP` is Kalshi's series for the **LNBP**, Liga Nacional de Baloncesto
Profesional, Mexico's professional BASKETBALL league, and Astros de Jalisco is an
LNBP basketball club. So `basketball` is correct, the disagreement with the
query's `baseball` is real, and the guard rests on true data.

WHY THE EXISTING DEMOTION COULD NOT SEE IT. `_demote_wrong_league` keys on a
league token IN THE QUERY (`nba` ⇒ demote `wnba`). A bare club name carries no
league token, so the arm never engages. The cousin here is a club-name cousin
across SPORTS, and the query text does not contain the signal that separates
them. `_rerank_search_futures`' other two signals are name-match then volume, and
the LNBP market is a name-match (`astros` is a substring of `Astros de Jalisco`)
whose volume beat the Houston markets' — it won on signal 2 with nothing to check
it.

THE SIGNAL IS THE PAGE'S OWN GAMES, not a string. `_search_sport_facets` groups
the whole matched event set by sport, and for `q=astros` returns exactly one
facet: `baseball_mlb` × 39. One facet or nothing — that unanimity is the safety
argument, and it is why the guard cannot arm on `giants` (MLB *and* NFL) or on
`trump` (no games at all).

These are unit tests over the two pure helpers plus positional guards on the
route. The reranker is pure and its contract is an ORDERING, so ordering is what
is asserted; the route-level facts that no unit test can see (that the argument
is bound before the pill tally is discarded, that typeahead deliberately passes
nothing) are read off the AST rather than asserted about a response body.
"""

import ast
import inspect

from app.routes import events as events_route
from app.routes.events import (
    _demote_wrong_sport,
    _rerank_search_futures,
    _resolved_search_sport_category,
)

SEARCH_SRC = inspect.getsource(events_route.search_events)


class _M:
    """The three attributes the reranker and the demotion actually read."""

    def __init__(self, id, name, llm_sport_category=None, volume=None):
        self.id = id
        self.name = name
        self.llm_sport_category = llm_sport_category
        # `volume`, the attribute `_market_volume` actually reads — not the
        # `volume_24h` the serialized payload prints. A double named for the wire
        # key would have sorted every fixture as volume 0 and the specimen test
        # would have passed on insertion order alone.
        self.volume = volume
        self.external_id = None
        self.market_metadata = None

    def __repr__(self):  # readable assertion output
        return f"<{self.id} {self.name!r} {self.llm_sport_category}>"


# The specimen pair, by id, with the volumes that produced the defect: the LNBP
# market outranked the Houston ones on volume alone.
DORADOS = _M(61496478, "Dorados de Chihuahua vs Astros de Jalisco", "basketball", 9_000)
HOUSTON_F5 = _M(
    61413602, "Atlanta Braves vs. Houston Astros - First 5 Innings Winner", "baseball", 800
)
HOUSTON_ALCS = _M(
    61380831,
    "Will Houston Astros advance to the ALCS in the 2026 MLB Playoffs?",
    "baseball",
    120,
)

_ASTROS = [("astros", None)]


# ─────────────────────────── the resolved category ───────────────────────────


class TestResolvedCategory:
    def test_one_facet_resolves_to_the_mapped_llm_category(self):
        """`baseball_mlb` → `baseball`, the value the column actually holds."""
        facets = [{"key": "baseball_mlb", "name": "MLB", "count": 39}]
        assert _resolved_search_sport_category(facets) == "baseball"

    def test_the_prefix_is_TRANSLATED_not_compared(self):
        """🪤 The loudest possible false positive, and the reason the map exists.

        `SPORT_PREFIX_TO_LLM_CATEGORY` is not the identity. The stored column
        holds the map's OUTPUTS — measured over the 43 distinct values on open
        markets, `football` 6,004 rows with no `americanfootball`, `hockey` 623
        with no `icehockey`. Compare the raw prefix instead and EVERY NFL market
        is 'wrong sport' on every NFL query, silently, because `americanfootball`
        != `football`.
        """
        assert (
            _resolved_search_sport_category(
                [{"key": "americanfootball_nfl", "name": "NFL", "count": 12}]
            )
            == "football"
        )
        assert (
            _resolved_search_sport_category(
                [{"key": "icehockey_nhl", "name": "NHL", "count": 4}]
            )
            == "hockey"
        )
        # And the guard is inert for an NFL market on an NFL query, which is the
        # consequence that would have been broken.
        nfl = _M(1, "Super Bowl LX Winner", "football", 50)
        assert _demote_wrong_sport([nfl, HOUSTON_F5], "football") == [nfl, HOUSTON_F5]

    def test_two_facets_resolve_to_nothing(self):
        """`giants` is MLB and NFL. No unanimity, no demotion."""
        facets = [
            {"key": "baseball_mlb", "name": "MLB", "count": 20},
            {"key": "americanfootball_nfl", "name": "NFL", "count": 14},
        ]
        assert _resolved_search_sport_category(facets) is None

    def test_no_facets_resolve_to_nothing(self):
        """`trump` matches no games; `sport_facets` can also be None outright."""
        assert _resolved_search_sport_category([]) is None
        assert _resolved_search_sport_category(None) is None

    def test_an_unmapped_key_resolves_to_nothing_rather_than_a_neighbour(self):
        """🪤 `.get` with no fallback. A prefix miss is an ABSENCE, never a
        silent substitution — and `_sport_facet_labels` folds a sport-less row to
        the literal `"unknown"`, so that case lands here by construction."""
        assert _resolved_search_sport_category([{"key": "unknown", "count": 3}]) is None
        assert (
            _resolved_search_sport_category([{"key": "quidditch_pro", "count": 3}])
            is None
        )
        assert _resolved_search_sport_category([{"key": "", "count": 3}]) is None
        assert _resolved_search_sport_category([{"count": 3}]) is None


# ──────────────────────────────── the demotion ────────────────────────────────


class TestDemoteWrongSport:
    def test_the_specimen_pair_by_id(self):
        """THE ISSUE'S ACCEPTANCE CRITERION, on the reranker as the route calls it.

        Volume order alone puts Dorados first; with the resolved category it
        lands last, below both Houston markets.
        """
        markets = [DORADOS, HOUSTON_F5, HOUSTON_ALCS]
        out = _rerank_search_futures(markets, _ASTROS, "baseball")
        assert [m.id for m in out] == [61413602, 61380831, 61496478]
        assert out[0].id != 61496478, "the LNBP market still headlines the card"

    def test_the_STRAWMAN_the_defect_reproduces_without_the_signal(self):
        """Without the resolved category the reranker MUST still produce the bug.

        A guard whose specimen passes both with and without the fix is vacuous —
        it would be pinning the fixture's own insertion order, not the ordering
        rule. This is the same three rows through the same call, and the only
        thing that changes is the third argument.
        """
        markets = [DORADOS, HOUSTON_F5, HOUSTON_ALCS]
        unfixed = _rerank_search_futures(markets, _ASTROS, None)
        assert unfixed[0].id == 61496478, (
            "the defect did not reproduce with the signal withheld — this "
            "fixture no longer demonstrates #7259 and the test above proves "
            "nothing"
        )

    def test_a_null_category_is_never_demoted(self):
        """FAIL-OPEN. NULL is 4,391 open markets: the absence of a claim, not a
        claim of difference. It keeps its place."""
        unknown = _M(2, "Astros Something", None, 10_000)
        out = _demote_wrong_sport([unknown, HOUSTON_F5], "baseball")
        assert [m.id for m in out] == [2, 61413602]

    def test_the_literal_other_category_is_never_demoted(self):
        """`other` (368 open markets) is the corpus's written-down 'nobody said'.
        Treating it as a disagreement would demote on the absence of evidence."""
        other = _M(3, "Astros Novelty", "other", 10_000)
        out = _demote_wrong_sport([other, HOUSTON_F5], "baseball")
        assert [m.id for m in out] == [3, 61413602]

    def test_no_resolved_category_is_an_exact_identity(self):
        """The `None` path returns the list it was given, unchanged."""
        markets = [DORADOS, HOUSTON_F5]
        assert _demote_wrong_sport(markets, None) is markets
        assert _demote_wrong_sport(markets, "") is markets

    def test_it_is_a_STABLE_partition(self):
        """Within each side, input order survives — so the volume sort the
        reranker applied upstream is not scrambled by the partition."""
        a = _M(10, "A", "baseball", 5)
        b = _M(11, "B", "baseball", 4)
        w1 = _M(12, "W1", "basketball", 3)
        w2 = _M(13, "W2", "soccer", 2)
        out = _demote_wrong_sport([w1, a, w2, b], "baseball")
        assert [m.id for m in out] == [10, 11, 12, 13]

    def test_nothing_is_dropped(self):
        """It reorders. Every input id is still present on the way out."""
        markets = [DORADOS, HOUSTON_F5, HOUSTON_ALCS]
        out = _demote_wrong_sport(markets, "baseball")
        assert sorted(m.id for m in out) == sorted(m.id for m in markets)

    def test_a_single_market_short_circuits(self):
        one = [DORADOS]
        assert _demote_wrong_sport(one, "baseball") is one

    def test_case_and_whitespace_do_not_defeat_it(self):
        messy = _M(14, "Astros Whatever", "  BasketBall ", 10_000)
        out = _demote_wrong_sport([messy, HOUSTON_F5], "baseball")
        assert [m.id for m in out] == [61413602, 14]


# ─────────────────── the route facts a unit test cannot see ───────────────────


def _calls_named(src, name):
    return [
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == name
    ]


class TestTheRouteWiring:
    def test_the_category_is_bound_BEFORE_the_pill_tally_is_discarded(self):
        """🪤 THE TRAP THIS SHIP WAS ONE LINE FROM FALLING INTO.

        `search_events` nulls `sport_facets` when `total_pages <= 1`, so that a
        single-page query serves the page-local tally and stays byte-identical to
        its pre-#5514 behaviour. That is a DISPLAY decision. Derive the resolved
        category after it — at the futures stage, where it is consumed — and the
        guard reads None on every query returning no more than `per_page` games,
        which is most club queries. It would still have passed the specimen
        above, because `astros` happens to return 39 games and spill onto page
        two, while doing nothing at all for the class.

        So the ORDER of these two statements is the fix, and it is asserted by
        line number rather than by hope.
        """
        lines = SEARCH_SRC.splitlines()
        bind = [
            i
            for i, ln in enumerate(lines)
            if "_resolved_sport_category = _resolved_search_sport_category(" in ln
        ]
        discard = [
            i
            for i, ln in enumerate(lines)
            if ln.strip() == "sport_facets = None" and "total_pages" in lines[i - 1]
        ]
        assert len(bind) == 1, f"expected exactly one binding, found {len(bind)}"
        assert discard, "the `total_pages <= 1` nulling of `sport_facets` moved"
        assert bind[0] < discard[0], (
            "`_resolved_sport_category` is now bound AFTER `sport_facets` is "
            "discarded for single-page queries — the demotion is inert on every "
            "query whose games fit on one page"
        )

    def test_both_search_rerank_call_sites_pass_the_category(self):
        """The window and its refill must be partitioned on the same answer; a
        refill that ranked without it would append wrong-sport rows underneath a
        page that had just excluded them."""
        passing = [
            c
            for c in _calls_named(SEARCH_SRC, "_rerank_search_futures")
            if len(c.args) >= 3
            and isinstance(c.args[2], ast.Name)
            and c.args[2].id == "_resolved_sport_category"
        ]
        assert len(passing) == 2, (
            "expected the window AND the refill to pass the resolved category, "
            f"found {len(passing)}"
        )

    def test_the_typeahead_twin_is_DELIBERATELY_left_without_the_signal(self):
        """#3394's standing lesson is a fix landing on one endpoint while its
        copy keeps the defect — so the twin is checked, and the answer is
        recorded here rather than left to be rediscovered as an oversight.

        Two independent reasons, either sufficient. (1) The signal does not exist
        on that endpoint: the argument is `_search_sport_facets`' grouped tally
        over the matched EVENT set, and `/typeahead` never runs that statement.
        (2) The defect does not manifest there: measured on production
        2026-09-19, `/typeahead?q=astros` returns the LNBP market (61496478)
        SECOND, below `MLB World Series Champion 2026` (114584), because that
        endpoint's ORDER BY leads with `market_tier` and tier 1 beats the tier-5
        cousin before the reranker is reached. #7259 is a wrong-HEADLINE defect
        on /search's ANSWERS card and that surface has no such headline.

        This FAILS if someone threads a category into the typeahead call — not
        because doing so would be wrong forever, but because it would need its
        own measurement and its own definition of the query's sport, and a second
        definition is how the two surfaces drift apart.
        """
        ta_src = inspect.getsource(events_route.typeahead_search)
        for call in _calls_named(ta_src, "_rerank_search_futures"):
            assert len(call.args) < 3 and not call.keywords, (
                "the typeahead reranker call now passes a resolved sport "
                "category; see this test's docstring for why that needs its own "
                "measurement first"
            )
