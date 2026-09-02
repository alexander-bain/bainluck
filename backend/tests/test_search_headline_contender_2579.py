"""UX-P259/#2579 — search finds the tournament a player can win.

RED-FIRST. Every test that asserts the new behaviour imports
`app.utils.search_headline_contender` INSIDE the test body, never at module
scope, so on clean master the file COLLECTS and the new-behaviour tests fail
individually instead of the whole module erroring at import time. A module-level
import would make the red arm a collection error, which grades as "the harness
never ran" rather than "the defect is present" (gotcha #124's lesson applied to
red-first).

The controls in `TestControlsGreenInBothArms` must pass on clean master AND on
this branch. They are what proves the red arm is measuring the fix and not a
broken checkout.

THE CORPUS FIXTURES BELOW ARE REAL. Every row in `LIVE_CONTENDER_CORPUS` was read
out of production on 2026-09-01 with `db-query`, including the volumes. They are
the replay that chose the rule: `market_tier <= 2` and a substring outcome match
were both tried against this corpus first and both were rejected by it.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

# --------------------------------------------------------------------------
# Real production rows, 2026-09-01. (market_name, outcome_name, probability,
# volume, market_tier). See the module docstring of the helper for provenance.
# --------------------------------------------------------------------------
LIVE_CONTENDER_CORPUS = {
    # The bug report's own case, and its siblings.
    "Alcaraz": [
        ("2026 Men’s US Open Winner (Tennis)", "Carlos Alcaraz", 0.355, 4108808, 1),
        ("US Open Men's Singles Winner", "Carlos Alcaraz", 0.365, 470270, 1),
        ("Cincinnati Open: Winner", "Carlos Alcaraz", 0.370, None, 1),
        ("#1 Searched Athlete on Google 2026?", "Carlos Alcaraz", 0.050, 900000, 2),
    ],
    "Sabalenka": [
        ("2026 Women’s US Open Winner (Tennis)", "Aryna Sabalenka", 0.235, 5819053, 1),
        ("US Open Women's Singles Winner", "Aryna Sabalenka", 0.225, 67491, 1),
        ("WTA Toronto Winner", "Aryna Sabalenka", 0.060, 61326, 1),
        ("WTA 1000 Toronto: Winner", "Aryna Sabalenka", 0.210, 840, 1),
    ],
    # Ambiguous names: a real, tradeable market exists for a DIFFERENT person.
    "Trump": [
        ("Snooker China Open 2026: Winner", "Judd Trump", 0.190, 140, 1),
    ],
    "Jordan": [
        ("NASCAR Winn-Dixie 250 Team Winner", "Jordan Anderson Racing", 0.080, 2534, 1),
        ("MO-04 House winner?", "Jordan Herrera", 0.074, 2273, 1),
        ("OH-04 House winner?", "Jim Jordan", 0.9445, 1437, 1),
        ("Grammys 2027: Best New Artist Winner", "Jordan Ward", 0.250, 40, 1),
    ],
    # #993's own regression case: listed as a longshot, not a contender.
    "LeBron": [
        (
            "Who will announce Presidential run before 2028?",
            "LeBron James",
            0.050,
            500000,
            2,
        ),
        ("Jimmy Fallon: Guests in 2026", "LeBron James", 0.085, 300000, 2),
    ],
    # LAT-P032/#1732's measured substring collisions. NONE is a whole word.
    "fed": [
        ("Chess Candidates 2026: Winner", "Russian Federation", 0.120, 800000, 1),
        ("ND-AL House winner?", "Julie Fedorchak", 0.910, 500000, 1),
        ("Tchaikovsky Competition Winner", "Vladimir Fedoseev", 0.200, 400000, 1),
    ],
}


class _StubMarket:
    """Duck-typed stand-in for a FuturesMarket row."""

    def __init__(self, market_id, name="", volume=0, market_tier=1):
        self.id = market_id
        self.name = name
        self.volume = volume
        self.market_tier = market_tier

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Market {self.id} {self.name!r}>"


def _apply_rule(term):
    """Replay the FULL rule over the live corpus for `term`.

    Mirrors the two halves as they are wired: the whole-word pattern decides
    which outcome rows match, `is_contender_outcome` decides which of those are
    contenders, and `market_tier == HEADLINE_MARKET_TIER` gates the market.
    Returns the market names that would earn a reserved slot.
    """
    import re

    from app.utils.search_headline_contender import (
        HEADLINE_MARKET_TIER,
        contender_word_pattern,
        is_contender_outcome,
    )

    pattern = contender_word_pattern(term)
    if pattern is None:
        return []
    # Postgres \m / \M are word boundaries; \b is Python's equivalent here
    # because every generated pattern is alphanumeric runs joined by \s+.
    py_pattern = pattern.replace(r"\m", r"\b").replace(r"\M", r"\b")
    admitted = []
    for market_name, outcome_name, probability, volume, tier in LIVE_CONTENDER_CORPUS[
        term
    ]:
        if tier != HEADLINE_MARKET_TIER:
            continue
        if not re.search(py_pattern, outcome_name, re.IGNORECASE):
            continue
        if not is_contender_outcome(probability, volume):
            continue
        admitted.append(market_name)
    return admitted


# ==========================================================================
# RED on clean master — the defect itself.
# ==========================================================================
class TestTheDefect:
    def test_alcaraz_reaches_a_us_open_winner_market(self):
        """#2579: typing the favourite's name must reach the tournament board."""
        admitted = _apply_rule("Alcaraz")
        assert any("US Open" in name and "Winner" in name for name in admitted), (
            "no US Open winner market earned a slot for 'Alcaraz' — this is the "
            f"reported defect. Admitted: {admitted}"
        )

    def test_sabalenka_reaches_a_us_open_winner_market(self):
        admitted = _apply_rule("Sabalenka")
        assert any(
            "US Open" in name and "Winner" in name for name in admitted
        ), f"admitted: {admitted}"

    def test_headline_contender_is_promoted_to_the_front_of_the_page(self):
        from app.utils.search_headline_contender import promote_headline_contenders

        page = [_StubMarket(i, name=f"prop {i}") for i in range(10)]
        winner = _StubMarket(999, name="US Open Men's Singles Winner")

        rows, promoted = promote_headline_contenders(page, [winner])

        assert promoted == 1
        assert rows[0] is winner, "the answer must lead the page, not trail it"
        assert len(rows) == 10, "promotion must not grow the page"
        assert page[-1] not in rows, "the WEAKEST name match loses its slot"

    @pytest.mark.parametrize("endpoint", ["search_events", "typeahead_search"])
    def test_both_seams_wire_the_promotion(self, endpoint):
        """AST guard: each NAMED endpoint must call the promoter itself.

        Walks each function's own AST rather than scanning the file for a
        substring — a substring is satisfied by the import line, by a comment,
        or by the SIBLING endpoint, and none of those put the fix on the surface
        under test. #2579 was reported against the header DROPDOWN and confirmed
        on `/search`; #2580/#2623 is the precedent that a search fix which lands
        at one seam leaves the user still looking at the bug.
        """
        from app.routes import events

        source = inspect.getsource(getattr(events, endpoint))
        tree = ast.parse(inspect.cleandoc(source))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "promote_headline_contenders" in called, (
            f"{endpoint} does not call promote_headline_contenders — the helper "
            f"exists but this surface does not use it. Calls found: {sorted(called)}"
        )

    def test_the_dropdown_promotes_into_the_visible_five(self):
        """The typeahead pool is cut to 5. A promotion that lands at rank 6 is
        invisible, so the promoted row must reach the FRONT of the ranked list
        the pool loop consumes — not merely be present in it."""
        from app.utils.search_headline_contender import promote_headline_contenders

        ranked = [_StubMarket(i, name=f"Alcaraz prop {i}") for i in range(20)]
        winner = _StubMarket(999, name="2026 Men's US Open Winner (Tennis)")

        rows, promoted = promote_headline_contenders(ranked, [winner])

        assert promoted == 1
        assert rows[:5][0] is winner, "promoted row missed the visible five"


# ==========================================================================
# The clauses that keep the documented regressions out. These encode WHY the
# rule is shaped the way it is; loosening any clause turns one of these red.
# ==========================================================================
class TestTheRuleRejectsWhatItMust:
    @pytest.mark.parametrize("term", ["Trump", "Jordan"])
    def test_ambiguous_name_earns_no_slot(self, term):
        """A real market for a DIFFERENT person must not take the top slot.

        Judd Trump (snooker, volume 140) and four unrelated Jordans (max volume
        2,534) are all tier-1 markets where that person is a genuine contender.
        Only the VOLUME floor separates them from the US Open board, which is
        why the floor is what earns the front-of-page placement.
        """
        assert _apply_rule(term) == [], (
            f"'{term}' promoted {_apply_rule(term)} — an ambiguous-name market "
            "reached the page, which would be a regression, not a fix"
        )

    def test_fed_substring_collisions_earn_no_slot(self):
        """LAT-P032/#1732 measured these as 35% of the `fed` page. Whole-word
        matching is what keeps them out — every one is high-volume and tier 1,
        so no other clause would."""
        assert _apply_rule("fed") == []

    def test_a_longshot_listing_earns_no_slot(self):
        """#993: a market that lists you as an option is not a market about you."""
        assert _apply_rule("LeBron") == []

    def test_tier_two_is_not_headline(self):
        """`<= 2` was replayed and rejected: it promoted Vogue cover models and
        Taylor Swift's wedding guests."""
        from app.utils.search_headline_contender import HEADLINE_MARKET_TIER

        assert HEADLINE_MARKET_TIER == 1
        assert "#1 Searched Athlete on Google 2026?" not in _apply_rule("Alcaraz")

    def test_volume_null_market_earns_no_slot(self):
        """ "Cincinnati Open: Winner" carries volume NULL and resolution_date NULL
        — a stale market (#2510) that would otherwise have outranked the US Open
        DURING the US Open, because its price is the highest of the three."""
        assert "Cincinnati Open: Winner" not in _apply_rule("Alcaraz")

    def test_short_term_never_reaches_the_corpus(self):
        """Cost guard: a sub-3-char term is unservable by a pg_trgm GIN and would
        seq-scan a 3.9M-row table."""
        from app.utils.search_headline_contender import contender_word_pattern

        assert contender_word_pattern("re") is None
        assert contender_word_pattern("la") is None
        assert contender_word_pattern("") is None
        assert contender_word_pattern("!!") is None
        assert contender_word_pattern("fed") is not None  # 3 chars IS servable

    def test_pattern_cannot_carry_a_regex_metacharacter(self):
        """The pattern is interpolated into a Postgres regex. It is built from
        alphanumeric runs only, so no metacharacter can survive."""
        from app.utils.search_headline_contender import contender_word_pattern

        # Long enough to clear the alnum-run gate, so the metacharacters really
        # do have to be stripped rather than the whole term being refused.
        pattern = contender_word_pattern("alcaraz.*|(x)$")
        assert pattern is not None
        body = pattern.removeprefix(r"\m").removesuffix(r"\M")
        for meta in ".*|()[]{}^$?+\\":
            assert meta not in body.replace(
                r"\s+", ""
            ), f"{meta!r} survived: {pattern!r}"

    def test_multi_term_query_requires_every_term(self):
        from app.utils.search_headline_contender import contender_patterns

        assert contender_patterns([("carlos", None), ("alcaraz", None)]) is not None
        # One unservable term makes the whole query ineligible rather than
        # silently widening the lane to the surviving term.
        assert contender_patterns([("carlos", None), ("de", None)]) is None
        assert contender_patterns([]) is None

    def test_probability_and_volume_floors_are_boundaries(self):
        from app.utils.search_headline_contender import (
            MIN_CONTENDER_PROBABILITY,
            MIN_CONTENDER_VOLUME,
            is_contender_outcome,
        )

        assert is_contender_outcome(MIN_CONTENDER_PROBABILITY, MIN_CONTENDER_VOLUME)
        assert not is_contender_outcome(
            MIN_CONTENDER_PROBABILITY - 0.001, MIN_CONTENDER_VOLUME
        )
        assert not is_contender_outcome(
            MIN_CONTENDER_PROBABILITY, MIN_CONTENDER_VOLUME - 1
        )
        assert not is_contender_outcome(None, MIN_CONTENDER_VOLUME)
        assert not is_contender_outcome(0.5, None)


class TestPromotionMechanics:
    def test_cap_is_respected(self):
        from app.utils.search_headline_contender import (
            MAX_HEADLINE_SLOTS,
            promote_headline_contenders,
        )

        page = [_StubMarket(i) for i in range(10)]
        contenders = [_StubMarket(100 + i) for i in range(6)]
        rows, promoted = promote_headline_contenders(page, contenders)
        assert promoted == MAX_HEADLINE_SLOTS
        assert len(rows) == 10

    def test_a_row_already_on_the_page_does_not_spend_a_slot(self):
        from app.utils.search_headline_contender import promote_headline_contenders

        already = _StubMarket(7, name="US Open Men's Singles Winner")
        page = [_StubMarket(i) for i in range(5)] + [already]
        rows, promoted = promote_headline_contenders(page, [already])
        assert promoted == 0
        assert rows == page

    def test_the_two_source_pair_never_lands_on_the_page_twice(self):
        """Alex's standing ruling: the blend is the product — one number per
        question, source divergence is a data bug, not a feature to show.

        Kalshi's "US Open Men's Singles Winner" and Polymarket's "2026 Men's US
        Open Winner (Tennis)" are ONE question that the route's dedup key does
        not merge (measured — the two names normalize to different keys). They
        are also the top two rows the live contender query returns for
        `Alcaraz`, so a cap above 1 opens the page with the same market twice at
        two different prices. The cap is what prevents that today.
        """
        from app.utils.search_headline_contender import promote_headline_contenders

        kalshi = _StubMarket(1, name="US Open Men's Singles Winner")
        polymarket = _StubMarket(2, name="2026 Men's US Open Winner (Tennis)")
        page = [_StubMarket(50 + i) for i in range(10)]

        rows, promoted = promote_headline_contenders(page, [polymarket, kalshi])

        assert promoted == 1
        assert rows[0] is polymarket, "the higher-volume source leads"
        assert kalshi not in rows, (
            "both sources for one tournament reached the page — that is the "
            "blend-is-the-product ruling broken inside search"
        )

    def test_dedup_key_is_honoured_when_supplied(self):
        """The cap is today's guard; the key is the durable one. Both work, so
        raising the cap after #2163's cross-source merge is a one-line change."""
        from app.utils.search_headline_contender import promote_headline_contenders

        first = _StubMarket(1, name="US Open Men's Singles Winner")
        same_question = _StubMarket(2, name="2026 Men's US Open Winner (Tennis)")
        other = _StubMarket(3, name="ATP 1000 Montreal: Winner")
        page = [_StubMarket(50 + i) for i in range(10)]

        rows, promoted = promote_headline_contenders(
            page,
            [first, same_question, other],
            cap=2,
            dedup_key=lambda m: "usopen-mens" if "US Open" in m.name else m.name,
        )
        assert promoted == 2
        assert [m.id for m in rows[:2]] == [1, 3], (
            "the duplicate question must collapse and free its slot for a "
            f"DIFFERENT one; got {[m.name for m in rows[:2]]}"
        )

    def test_empty_contenders_is_a_no_op(self):
        from app.utils.search_headline_contender import promote_headline_contenders

        page = [_StubMarket(i) for i in range(10)]
        rows, promoted = promote_headline_contenders(page, [])
        assert promoted == 0
        assert rows is page

    def test_promotion_never_exceeds_the_page_slice(self):
        from app.utils.search_headline_contender import (
            MAX_HEADLINE_SLOTS,
            promote_headline_contenders,
        )

        for page_len in range(0, 11):
            page = [_StubMarket(i) for i in range(page_len)]
            contenders = [_StubMarket(100 + i) for i in range(4)]
            rows, _ = promote_headline_contenders(page, contenders)
            assert len(rows) <= max(page_len, MAX_HEADLINE_SLOTS) <= 10
            assert len({m.id for m in rows}) == len(rows), "duplicate row emitted"


# ==========================================================================
# CONTROLS — must be green on clean master AND on this branch. If one of these
# is red, the red arm above is measuring a broken checkout, not the defect.
# ==========================================================================
class TestControlsGreenInBothArms:
    def test_search_route_still_exposes_the_futures_page_constants(self):
        from app.routes import events

        assert events._SEARCH_FUTURES_PAGE == 10
        assert events._SEARCH_FUTURES_WINDOW == 20

    def test_name_tier_still_leads_the_futures_order_by(self):
        """The fix must NOT have been implemented by reordering the window. #993's
        "name-match beats outcome-only-match" still governs slots 3-10, and
        LAT-P033 put that tier in SQL on purpose."""
        from app.routes import events

        source = inspect.getsource(events.search_events)
        assert "_futures_name_tier.asc()" in source
        assert "futures_search_rank.desc()" in source

    def test_query_name_match_helper_still_exists(self):
        """The route's OWN definition of outcome-only, reused by the new lane
        rather than re-implemented beside it."""
        from app.routes import events

        assert callable(events._query_name_match)

    def test_helper_module_is_pure(self):
        """No ORM, no I/O, no `app` imports — so the rule can be replayed over
        fixtures, which is how it was chosen."""
        path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "utils"
            / "search_headline_contender.py"
        )
        if not path.exists():
            pytest.skip("helper not present on this arm")
        tree = ast.parse(path.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        offenders = [m for m in imported if m.startswith("app") or m == "sqlalchemy"]
        assert not offenders, f"helper is no longer pure: {offenders}"
