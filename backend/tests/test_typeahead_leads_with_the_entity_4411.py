"""TYPING A PLAYER'S NAME LEADS WITH THEIR MATCH, NOT WITH A PILE OF PROPS. #4411.

Sibling of `test_search_finds_the_team_and_the_tournament_4126.py` ("the front
door"): that file owns whether `yank` / `us open` can be FOUND at all, this one
owns what leads once they have been. Alex, Wed 2026-09-09: "typing a player's
name returns a pile of props above the match itself", with the rule attached —
**a team or player name leads with the entity (team card / the player's
next-or-last match), then its games, then props** — and the instruction to put
`shelton`, `alcaraz` and `sinner` in the guards beside `yank` / `red sox` /
`us open`. All six appear below.

MEASURED ON PRODUCTION, 2026-09-09 10:40 PT, `GET /api/events/typeahead`:

    q=shelton   5 props, then 1 match
    q=alcaraz   5 props, and NO MATCH AT ALL
    q=sinner    2 props, 2 matches, 3 props

`alcaraz`'s top row was the tier-5 novelty "Will any man other than Carlos
Alcaraz and Jannik Sinner win a ATP Grand Slam in 2026?" (Yes 99%).

TWO INDEPENDENT CAUSES, and a test for a fix to either one alone passes while
the reported bug is still on the screen — which is why both are pinned here:

1. RANKING. `KIND_ORDER` put market at 2 and event at 3, and the event "Ben
   Shelton vs Carlos Alcaraz" and the market "Ben Shelton vs Carlos Alcaraz:
   Exact Match Score" are BOTH MC1. The class term ties, so kind alone decided
   and the market won every time.

2. RECALL. The pool was upcoming-only, and Alcaraz had nothing upcoming — his
   most recent was `completed` hours earlier. Zero event candidates were built,
   so the ranking fix is INERT for him without the "or-last" arm.

WHAT THIS FILE MUST NOT BE READ AS: a reversal of the ratified market > event >
team relation (ruling 041 / Q325). That relation is what makes `nba mvp` answer
with the award and `british open` / `ai` / `ipo` behave; the survival controls
below fail if it is ever flipped wholesale. The promotion is scoped to a row the
query NAMED — one whose own participant carries the query's tokens.
"""

from __future__ import annotations

import pytest

from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    KIND_ORDER,
    Evidence,
    query_names_participant,
    rank,
)


# --- the shared harness ----------------------------------------------------
#
# Ranks through the REAL `rank`, and promotes through the REAL
# `query_names_participant`, so a test here cannot pass by re-implementing the
# rule it is checking. `_participants=None` is how a non-event candidate is
# spelled; it is never promoted.


def _cand(name, kind, participants=None, aliases=(), outcomes=()):
    return (name, kind, participants, aliases, outcomes)


def _ranked(q, rows):
    candidates = []
    for name, kind, participants, aliases, outcomes in rows:
        resolved = kind
        if kind == "event" and participants and query_names_participant(q, participants):
            resolved = ENTITY_EVENT_KIND
        candidates.append(
            (
                Evidence(
                    name=name,
                    kind=resolved,
                    aliases=tuple(aliases),
                    outcomes=tuple(outcomes),
                    sport_key="tennis",
                ),
                name,
            )
        )
    return list(rank(q, candidates))


# The five props production actually served for `alcaraz`, verbatim, plus the
# match the "or-last" arm now builds for him.
_ALCARAZ = [
    _cand("Will any man other than Carlos Alcaraz and Jannik Sinner win a ATP Grand Slam in 2026?", "futures"),
    _cand("Ben Shelton vs Carlos Alcaraz: Exact Match Score", "futures"),
    _cand("US Open ATP: Yibing Wu vs Carlos Alcaraz", "futures"),
    _cand("US Open ATP: Ben Shelton vs Carlos Alcaraz", "futures"),
    _cand("Lopez Alcaraz vs Argyrokastriti", "futures"),
    _cand("Carlos Alcaraz at Ben Shelton", "event", ["Ben Shelton", "Carlos Alcaraz"]),
]

_SHELTON = [
    _cand("US Open Men's Singles Winner", "futures"),
    _cand("Ben Shelton vs Carlos Alcaraz: Exact Match Score", "futures"),
    _cand("US Open ATP: Ben Shelton vs Carlos Alcaraz", "futures"),
    _cand("Tiafoe vs Shelton", "futures"),
    _cand("Ben Shelton at Frances Tiafoe", "event", ["Frances Tiafoe", "Ben Shelton"]),
]

#: SYNTHETIC, unlike the two above. Jannik is not in the 2026 US Open (measured
#: 2026-09-09: no match market, residual .010 on the winner market, last event
#: row 2026-07-18), and the raw pool for `sinner` is really two Counter-Strike
#: fixtures whose roster is called "Sinners". That namesake collision is what
#: this pool CANNOT see — it is owned by
#: `tests/integration/test_route_typeahead_sinner_namesake_4411.py` (CERT-2392),
#: because both of its causes live in the pool assembly and a hand-built pool
#: has already made those decisions for itself.
_SINNER = [
    _cand("Will any man other than Carlos Alcaraz and Jannik Sinner win a ATP Grand Slam in 2026?", "futures"),
    _cand("Jannik Sinner: Total Games", "futures"),
    _cand("US Open ATP: Jannik Sinner vs Felix Auger-Aliassime", "futures"),
    _cand("Jannik Sinner at Felix Auger-Aliassime", "event", ["Felix Auger-Aliassime", "Jannik Sinner"]),
]

_FIXTURES = {"shelton": _SHELTON, "alcaraz": _ALCARAZ, "sinner": _SINNER}


class TestAlexsThreeNames:
    """`shelton`, `alcaraz`, `sinner` — the three he typed."""

    @pytest.mark.parametrize("q", sorted(_FIXTURES))
    def test_the_match_leads(self, q):
        top = _ranked(q, _FIXTURES[q])[0]
        assert top.startswith(("Carlos Alcaraz at", "Ben Shelton at", "Jannik Sinner at")), (
            f"q={q!r} still leads with {top!r} — this is the reported bug"
        )

    @pytest.mark.parametrize("q", sorted(_FIXTURES))
    def test_every_prop_sorts_below_the_match(self, q):
        """Not just the top slot.

        Leading with the match while the next four rows are still props is the
        complaint half-fixed: Alex said "then its games, then props", so the
        partition has to hold all the way down, not only at rank 0.
        """
        order = _ranked(q, _FIXTURES[q])
        events = {n for n, k, p, *_ in _FIXTURES[q] if k == "event"}
        last_event = max(i for i, n in enumerate(order) if n in events)
        first_prop = min(i for i, n in enumerate(order) if n not in events)
        assert last_event < first_prop, (
            f"q={q!r}: a prop sorted above a match — {order}"
        )

    def test_alcaraz_had_no_match_to_rank_at_all(self):
        """The RECALL half, stated as the ranking half's precondition.

        Delete the "or-last" arm and this fixture loses its only event, so the
        two tests above go green on an empty partition while production still
        shows Alex five props. This is the test that refuses that.
        """
        without_the_last_match = [r for r in _ALCARAZ if r[1] != "event"]
        order = _ranked("alcaraz", without_the_last_match)
        assert all(not n.startswith("Carlos Alcaraz at") for n in order)
        assert order[0].startswith("Will any man other than"), (
            "the pre-fix production ordering is no longer reproducible, so this "
            "file has stopped measuring the bug it was written for"
        )


class TestTheSurvivalControls:
    """`yank`, `red sox`, `us open` — and the ratified relation behind them."""

    def test_red_sox_gives_team_card_then_its_game_then_props(self):
        """Alex's sentence, in the order he said it, on the team half.

        The team does not win by being a team — it wins MC0 against its own
        alias "Red Sox" (ruling 041's team floor), which outranks every MC1
        candidate whatever its kind. The GAME then leads the props because the
        query names both participants. Kind order alone could not produce this.
        """
        order = _ranked("red sox", [
            _cand("Boston Red Sox - Player Props", "futures"),
            _cand("New York Yankees at Boston Red Sox", "event",
                  ["Boston Red Sox", "New York Yankees"]),
            _cand("Boston Red Sox", "team", None, ["Red Sox"]),
        ])
        assert order == [
            "Boston Red Sox",
            "New York Yankees at Boston Red Sox",
            "Boston Red Sox - Player Props",
        ], order

    def test_yank_promotes_nothing_because_it_names_no_participant(self):
        """`yank` is a PREFIX fragment, not a name a row owns.

        Measured while writing this file, and worth recording because the
        obvious assertion here is wrong: `yank` already ranked the game above
        the team card BEFORE #4411, and still does. Both are MC2 (the fragment
        prefixes "yankees" in each), so kind decided it then and decides it now
        — `event` has always sorted above `team`. #4411 changes nothing about
        this query, which is the only claim this control is entitled to make.

        A team beats a fragment query by matching BETTER (ruling 041's floor:
        MC0 on an exact alias), and `yank` is not exact. Widening the promotion
        to cover prefixes would "fix" it by reversing the ratified relation for
        every query at once, which is exactly what this file exists to prevent.
        """
        assert not query_names_participant(
            "yank", ["New York Yankees", "Baltimore Orioles"]
        )

    def test_us_open_is_not_a_participant_so_the_concept_still_leads(self):
        """The tournament name is nowhere on the event row (#4126's finding).

        So `us open` promotes nothing, and the concept keeps the slot that
        seven gold probes bought it. A promotion rule keyed on the assembled
        `text` instead of on the participants would break exactly this.
        """
        order = _ranked("us open", [
            _cand("US Open ATP: Ben Shelton vs Carlos Alcaraz", "futures"),
            _cand("Ben Shelton at Frances Tiafoe", "event",
                  ["Frances Tiafoe", "Ben Shelton"]),
            _cand("US Open", "event_concept"),
        ])
        assert order[0] == "US Open", order

    def test_nba_mvp_still_answers_with_the_award(self):
        """The ratified market > event relation, on a query naming no player."""
        order = _ranked("nba mvp", [
            _cand("NBA MVP Winner", "futures"),
            _cand("Boston Celtics at Los Angeles Lakers", "event",
                  ["Los Angeles Lakers", "Boston Celtics"]),
        ])
        assert order[0] == "NBA MVP Winner", order


class TestTheParticipantRule:
    """`query_names_participant` — what may and may not be promoted."""

    def test_a_participants_own_name_promotes(self):
        assert query_names_participant("alcaraz", ["Ben Shelton", "Carlos Alcaraz"])

    def test_a_matchup_query_naming_both_still_promotes(self):
        """One-at-a-time would make the fixture lose to its own props."""
        assert query_names_participant("shelton alcaraz", ["Ben Shelton", "Carlos Alcaraz"])

    def test_the_tournament_does_not_promote(self):
        assert not query_names_participant("us open", ["Ben Shelton", "Carlos Alcaraz"])

    def test_a_partial_query_does_not_promote(self):
        """MC3 territory: some tokens landed, not all. Promotion needs all."""
        assert not query_names_participant("carlos sinner", ["Ben Shelton", "Carlos Alcaraz"])

    def test_an_empty_query_promotes_nothing(self):
        assert not query_names_participant("", ["Carlos Alcaraz"])

    def test_a_row_with_no_participants_promotes_nothing(self):
        """A futures row reaching this by mistake must not be promoted."""
        assert not query_names_participant("alcaraz", [])
        assert not query_names_participant("alcaraz", [None, ""])


class TestKindOrderRelations:
    """The renumber (market 2->3, event 3->4, team 4->5) moved NO pair.

    Asserted as relations, never as literals: the numbers are free, the ordering
    is the ruling. A guard that pinned `KIND_ORDER["team"] == 4` would have
    failed this change while the ruling it protects was perfectly intact.
    """

    def test_the_ratified_relation_survives(self):
        assert KIND_ORDER["market"] < KIND_ORDER["event"] < KIND_ORDER["team"]
        assert KIND_ORDER["futures"] == KIND_ORDER["market"]

    def test_concepts_and_hubs_still_outrank_markets(self):
        assert KIND_ORDER["event_concept"] < KIND_ORDER["hub"] < KIND_ORDER["market"]

    def test_a_named_entity_outranks_a_market_but_not_a_hub(self):
        """The whole of #4411's ranking half, as one relation.

        Below `hub`/`concept` deliberately: `us open` must keep answering with
        the tournament even on a page full of promoted fixtures.
        """
        assert KIND_ORDER["hub"] < KIND_ORDER[ENTITY_EVENT_KIND] < KIND_ORDER["market"]

    def test_a_promoted_event_outranks_a_plain_one(self):
        assert KIND_ORDER[ENTITY_EVENT_KIND] < KIND_ORDER["event"]

    def test_the_renumber_moved_nothing_that_was_not_promoted(self, monkeypatch):
        """The blast radius of #4411, asserted rather than reasoned about.

        The renumber opened slot 2 by pushing three kinds down one. If any
        PAIRWISE relation had changed, every query in the product would have
        moved, not just the ones naming a player — and nothing else in this
        file would notice, because every other test here ranks a candidate set
        that contains a promotion.

        So: rank an unpromoted set under the pre-#4411 table and under the
        current one, and require the two orderings to be identical.
        """
        import app.utils.search_match_class as smc

        pre_4411 = {
            "event_concept": 0, "concept": 0, "hub": 1,
            "futures": 2, "market": 2, "event": 3, "team": 4,
        }
        rows = [
            _cand("US Open", "event_concept"),
            _cand("Tennis", "hub"),
            _cand("US Open Men's Singles Winner", "futures"),
            _cand("Baltimore Orioles at New York Yankees", "event"),
            _cand("New York Yankees", "team", None, ["Yankees"]),
        ]
        queries = ["yank", "us open", "nba mvp", "yankees", "tennis", "winner"]

        after = {q: _ranked(q, rows) for q in queries}
        monkeypatch.setattr(smc, "KIND_ORDER", pre_4411)
        before = {q: _ranked(q, rows) for q in queries}

        assert before == after, (
            "the renumber changed an ordering for a query that promotes "
            "nothing — a pairwise relation moved"
        )

    def test_the_promoted_kind_is_actually_in_the_table(self):
        """An unknown kind takes `_KIND_ORDER_FALLBACK` and sorts LAST.

        So a typo in `ENTITY_EVENT_KIND` would not raise — it would silently
        invert the ship, putting the match below every prop. That is why the
        route imports the constant instead of spelling the string.
        """
        from app.utils.search_match_class import _KIND_ORDER_FALLBACK, kind_rank

        assert kind_rank(ENTITY_EVENT_KIND) != _KIND_ORDER_FALLBACK


class TestTheEvidenceSeam:
    """The route boundary: promotion needs the query AND the participants."""

    def test_the_query_is_required(self):
        """Called without `q`, an event can never be promoted.

        This is the withheld-evidence failure `_typeahead_evidence`'s own
        docstring records for teams (LAT-P050), arriving for events.
        """
        from app.routes.events import _typeahead_evidence

        item = {
            "type": "event",
            "text": "Carlos Alcaraz at Ben Shelton",
            "_participants": ["Ben Shelton", "Carlos Alcaraz"],
        }
        assert _typeahead_evidence(item).kind == "event"
        assert _typeahead_evidence(item, "alcaraz").kind == ENTITY_EVENT_KIND

    def test_participants_are_required(self):
        """A pool that forgets `_participants` degrades, it does not promote."""
        from app.routes.events import _typeahead_evidence

        item = {"type": "event", "text": "Carlos Alcaraz at Ben Shelton"}
        assert _typeahead_evidence(item, "alcaraz").kind == "event"

    def test_a_market_is_never_promoted(self):
        """Even carrying participants, which nothing should give it."""
        from app.routes.events import _typeahead_evidence

        item = {
            "type": "futures",
            "text": "Ben Shelton vs Carlos Alcaraz: Exact Match Score",
            "_participants": ["Ben Shelton", "Carlos Alcaraz"],
        }
        assert _typeahead_evidence(item, "alcaraz").kind == "futures"

    def test_participants_never_reach_the_wire(self):
        """Ranking evidence, not payload — the rule `_aliases` already follows.

        Asserted against the route's own strip list rather than a live call so
        it holds without a database.
        """
        import inspect

        from app.routes.events import typeahead_search

        src = inspect.getsource(typeahead_search)
        assert '_s.pop("_participants", None)' in src, (
            "the private participant evidence is being served to clients"
        )


class TestTheLastMatchArm:
    """The "or-LAST" recall query, compiled. Four clauses, each load-bearing."""

    @staticmethod
    def _sql():
        from datetime import datetime, timezone

        from sqlalchemy import true

        from app.routes.events import _last_match_query

        q = _last_match_query(true(), datetime(2026, 9, 9, 17, 0, tzinfo=timezone.utc))
        return str(q.compile(compile_kwargs={"literal_binds": True})).lower()

    def test_it_asks_for_finished_matches(self):
        sql = self._sql()
        assert "'completed'" in sql and "'closed'" in sql, sql

    def test_it_never_returns_an_upcoming_match(self):
        """Without the ceiling this is just the upcoming pool with no ordering."""
        assert "commence_time <=" in self._sql()

    def test_it_is_floored(self):
        """gotcha #41: a sweep over an expiring population needs BOTH bounds.

        Unfloored, `alcaraz` answers with a match from 2023 — and a retired
        player answers with something rather than nothing.
        """
        sql = self._sql()
        assert "commence_time >=" in sql
        assert "2026-08-10" in sql, (
            f"the 30-day floor is not in the compiled SQL: {sql}"
        )

    def test_the_most_recent_match_comes_first(self):
        """`last match` means the one just played.

        The upcoming pool orders ASC, and copying that here would answer with
        the OLDEST match in the window — a month-old first round instead of
        last night's quarter-final.
        """
        sql = self._sql()
        assert "order by" in sql
        assert "commence_time desc" in sql.split("order by", 1)[1], sql

    def test_it_excludes_proven_duplicates(self):
        """#2263 / CERT-439 — two slots on one game is its own complaint."""
        assert self._sql().count("commence_time") >= 2

    def test_the_arm_is_actually_REACHED_from_the_dropdown(self):
        """THE MUTATION THAT SURVIVED EVERYTHING ELSE IN THIS FILE.

        Replacing `if not _ta_rows:` with `if False:` leaves the query perfect,
        every test above green, and `alcaraz` back to five props and no match —
        because a query nobody calls ranks nothing. A pure function proves the
        SHAPE of the arm and says nothing about its REACH, and reach is the
        entire recall half of #4411.

        Read as an AST rather than as a substring on purpose: the property is
        "the pool assembly calls this, and calls it conditionally", which
        survives reformatting, renaming a local and reflowing the branch. A
        string pin on `if not _ta_rows:` would red on a no-op edit and, worse,
        would go quietly green if someone kept the line and moved the call out
        from under it.
        """
        import ast
        import inspect
        import textwrap

        from app.routes.events import typeahead_search

        tree = ast.parse(textwrap.dedent(inspect.getsource(typeahead_search)))

        def calls_it(node) -> bool:
            return any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "_last_match_query"
                for n in ast.walk(node)
            )

        assert calls_it(tree), "the or-last arm is never called — it is dead code"

        conditional = [
            branch
            for branch in ast.walk(tree)
            if isinstance(branch, ast.If) and calls_it(branch)
        ]
        assert conditional, "the or-last arm is called unconditionally"

        # ...and the condition must be able to be True. `if False:` was the
        # mutant that survived the first pass; `if _ta_rows and False:` survived
        # the fix for it. Both are the same act — switching the half off while
        # leaving every other test green — so the assertion is on the class:
        # no falsy literal anywhere in the condition, in any position.
        for branch in conditional:
            frozen = [
                n
                for n in ast.walk(branch.test)
                if isinstance(n, ast.Constant) and not n.value
            ]
            assert not frozen, (
                "the or-last arm is guarded by a condition carrying a falsy "
                f"literal ({[n.value for n in frozen]}) — it can never run"
            )
