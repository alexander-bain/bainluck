"""#7381 — the SHAPE of `/typeahead`'s team word-start rule, and its escaping.

The behavioural half of this fix lives in
``tests/integration/test_search_recall_contract.py``, against a real Postgres,
because "does this predicate match the right rows" is a question only the engine
that owns ``ILIKE`` and ``~*`` can answer.

This file guards the two properties that a **green recall run cannot see**:

1. **The ILIKE half is still there, AND-ed.** Recall is identical whether the
   predicate is ``ILIKE '%nba%' AND name ~* '…'`` or the regex alone — the regex
   is strictly narrower, so deleting the ILIKE changes no row. It changes the
   PLAN: ``ix_teams_name_trgm`` can drive a bitmap scan for the ILIKE and cannot
   for the regex, so the "simplification" costs a sequential scan of 9,914 rows
   on every keystroke and every recall test still passes. That is precisely the
   class LAT-P002/#1494 shipped and had to revert.

2. **The term is regex-escaped.** A search term is user input. It reaches ``~*``
   as a bound parameter, so this is not an injection guard — it is a correctness
   one. Unescaped, ``st.`` matches a word starting ``st`` followed by ANY
   character, and ``c++`` is not a valid POSIX ERE at all: Postgres raises, and a
   keystroke 500s instead of returning nothing.
"""

import re

import pytest
from sqlalchemy import String, cast
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import operators

from app.models.models import Team
from app.routes import events as events_module
from app.routes.events import _build_word_start_ilike, _regex_escape


def _sql(condition) -> str:
    return str(
        condition.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _bound_patterns(condition) -> list[str]:
    """The pattern strings as Postgres will RECEIVE them.

    Read from the bind parameters and not from the rendered SQL on purpose:
    `literal_binds` escapes the literal for the SQL grammar, doubling every
    backslash, so a rendered `\\\\.` is the single `\\.` the regex engine sees.
    Asserting on the rendered form tests SQLAlchemy's string quoting; asserting
    on the bind tests the pattern.
    """
    return [
        v
        for v in condition.compile(dialect=postgresql.dialect()).params.values()
        if isinstance(v, str)
    ]


class TestTheIlikeHalfSurvives:
    """Property 1 — the trigram-servable arm is AND-ed, never replaced."""

    def test_both_operators_are_present(self):
        sql = _sql(_build_word_start_ilike(Team.name, "nba", None))
        assert "ILIKE" in sql, (
            f"the trigram-servable ILIKE arm is gone: {sql}. The regex alone is "
            "correct and unindexable; this is the seq-scan regression that no "
            "recall assertion can fail on."
        )
        assert "~*" in sql, f"the word-boundary arm is gone: {sql}"

    def test_they_are_conjoined_not_disjoined(self):
        """OR-ing them would be a LOOSENING that reads like the fix.

        ``ILIKE '%nba%' OR name ~* '(^|…)nba'`` matches strictly more rows than
        the ILIKE alone, so every "must still match" test stays green while the
        defect — Pekanbaru — comes straight back.
        """
        sql = _sql(_build_word_start_ilike(Team.name, "nba", None))
        assert " AND " in sql and " OR " not in sql, (
            f"the two arms are not AND-ed: {sql}"
        )

    def test_an_expansion_is_a_pair_per_alternative(self):
        """With a synonym, each alternative carries BOTH arms — as a TREE.

        The wrong shape is ``(ilike_a OR ilike_b) AND (regex_a OR regex_b)``. It
        lets the TERM's ILIKE be satisfied by the EXPANSION's regex, so a row
        that merely contains the term as an infix is re-admitted whenever the
        query has a synonym — the defect, back, on exactly the queries that
        expand.

        This asserts the parse tree and not the rendered string on purpose. The
        two shapes are made of the same pieces: both render two ILIKEs, two
        regexes and an OR, so every count, substring and "is this operator
        present" assertion passes on both. Only the nesting differs, and a
        mutation run is what proved a count-based version of this test vacuous.
        """
        cond = _build_word_start_ilike(Team.name, "yank", "yankees")

        assert cond.operator is operators.or_, (
            "the top-level operator is not OR, so the two alternatives are not "
            f"independent pairs: {_sql(cond)}"
        )
        branches = list(cond.clauses)
        assert len(branches) == 2, f"expected one branch per alternative: {branches!r}"

        for alt, branch in zip(("yank", "yankees"), branches):
            assert getattr(branch, "operator", None) is operators.and_, (
                f"the {alt!r} branch is not a conjoined ILIKE+regex pair — the "
                f"arms have been hoisted out of it: {_sql(cond)}"
            )
            # Set EQUALITY, not containment. `yank` is a substring of `yankees`,
            # so "the other alternative does not appear in this branch" is
            # trivially false however the arms are wired, and a containment test
            # here reports a defect on the correct code. Equality also kills the
            # crossed pair — `yank`'s ILIKE conjoined with `yankees`' regex —
            # which satisfies every "is this arm present" assertion.
            assert _bound_patterns(branch) == [
                f"%{alt}%",
                f"(^|[^[:alnum:]]){alt}",
            ], (
                f"the {alt!r} branch is not exactly that alternative's own "
                f"ILIKE+regex pair: {_bound_patterns(branch)!r}"
            )

    def test_the_ilike_pattern_is_byte_identical_to_the_arm_it_narrows(self):
        """The ILIKE half is `_build_expanded_ilike`'s, unchanged.

        If the two drift, the AND is no longer "the old arm plus a filter" and
        the measured census — taken against `%term%` — stops describing what
        ships.
        """
        narrowed = _sql(_build_word_start_ilike(Team.name, "nba", None))
        original = _sql(events_module._build_expanded_ilike(Team.name, "nba", None))
        assert original.rstrip() in narrowed, (
            f"the ILIKE arm was rewritten rather than narrowed:\n"
            f"  original: {original}\n  narrowed: {narrowed}"
        )


class TestTheTermIsRegexEscaped:
    """Property 2 — a term is data, not a pattern."""

    @pytest.mark.parametrize(
        "term",
        ["c++", "st.", "a|b", "(x)", "[abc]", "a*", "a?", "a{2}", "a^b", "a$b", "a\\b"],
    )
    def test_every_metacharacter_survives_as_a_literal(self, term):
        escaped = _regex_escape(term)
        assert re.fullmatch(re.escape(term), term), "sanity: the term matches itself"
        # Postgres ERE and Python's `re` agree on this metacharacter set, so
        # compiling the escaped pattern here is a real test of it.
        assert re.search(f"(^|[^0-9A-Za-z]){escaped}", term), (
            f"{term!r} escaped to {escaped!r}, which no longer matches the term "
            "the reader typed"
        )

    def test_a_dot_stops_being_a_wildcard(self):
        """`st.` must not match "sty" — the defect an unescaped term ships."""
        escaped = _regex_escape("st.")
        assert not re.search(f"(^|[^0-9A-Za-z]){escaped}", "sty"), (
            "an unescaped full stop is matching any character"
        )
        assert re.search(f"(^|[^0-9A-Za-z]){escaped}", "st. louis")

    def test_an_ordinary_term_is_left_alone(self):
        """A rule that escapes everything is as wrong as one that escapes nothing."""
        for term in ["nba", "yankees", "d'or", "red sox", "49ers", "ostersunds"]:
            assert _regex_escape(term) == term, f"{term!r} was needlessly escaped"

    def test_the_escape_is_applied_by_the_builder(self):
        """The helper is only useful if the call site reaches it."""
        patterns = _bound_patterns(_build_word_start_ilike(Team.name, "st.", None))
        assert "(^|[^[:alnum:]])st\\." in patterns, (
            f"the builder bound an unescaped term: {patterns!r}"
        )


class TestBothTeamBranchesUseIt:
    """`typeahead_search` builds the team filter TWICE — once per branch of
    `is_multi_word` — and the route's own comments record `/search` and
    `/typeahead` drifting for three cycles by keeping two copies of one rule.

    The behavioural test for the multi-word branch is in the recall contract;
    this is the cheap structural backstop that fails in the unit shards, where
    no Postgres exists, if a later edit repairs only one of the two.
    """

    def test_no_team_column_is_left_on_the_bare_infix_arm(self):
        import inspect

        src = inspect.getsource(events_module.typeahead_search)
        # The alias arm reaches the builder wrapped in a cast, so each column is
        # matched by the text that follows the opening paren, not by an exact
        # argument spelling.
        for column in (
            "Team.name",
            "Team.abbreviation",
            "cast(Team.alternate_names, String)",
        ):
            assert f"_build_expanded_ilike({column}" not in src, (
                f"{column} is still filtered by the bare infix ILIKE in "
                "`typeahead_search` — #7381 repaired one branch and not the other."
            )
            assert f"_build_word_start_ilike({column}" in src, (
                f"{column} lost its word-start arm in `typeahead_search`"
            )
        # Both branches, not just one: three columns x two branches.
        assert src.count("_build_word_start_ilike(") == 6, (
            "expected the team filter in BOTH the multi-word and single-word "
            f"branches (3 columns each); found {src.count('_build_word_start_ilike(')}"
        )

    def test_the_events_and_futures_arms_are_deliberately_untouched(self):
        """#7381 is scoped to the team arm. The events arm (#4140) and the
        futures pool (#5082, #1758) are other shapes with other owners, and a
        sweep that "fixed" them here would ship an unmeasured recall change on
        the primary answer surface — which is how LAT-P002 was reverted.
        """
        import inspect

        src = inspect.getsource(events_module.typeahead_search)
        for column in (
            "Event.home_team_name",
            "Event.away_team_name",
            "FuturesMarket.name",
        ):
            assert f"_build_expanded_ilike({column}" in src, (
                f"{column} was moved onto the word-start rule. That is a recall "
                "change this fix never measured — it belongs to its own issue."
            )


def test_the_regex_anchors_a_word_start_and_not_a_string_start():
    """The anchor has to be `(^|non-alnum)`, not `^`.

    `^` alone is a prefix-of-the-NAME test, which drops "Red **Sox**" for `sox`
    and "Boston **Bruins**" for `bruins` — half the dropdown — while still
    passing a test that only asks whether Pekanbaru is gone.
    """
    sql = _sql(_build_word_start_ilike(Team.name, "sox", None))
    assert "(^|[^[:alnum:]])sox" in sql, (
        f"the anchor is not a word-start anchor: {sql}"
    )
    assert re.search("(^|[^0-9A-Za-z])sox", "Red Sox", re.I), "sanity"


def test_the_helper_works_on_the_cast_alternate_names_column():
    """The alias arm is a JSONB column cast to text, not a String column —
    `.op("~*")` has to survive the cast or the third arm silently never applies.
    """
    sql = _sql(_build_word_start_ilike(cast(Team.alternate_names, String), "nets", None))
    assert "~*" in sql and "ILIKE" in sql, sql
    assert "alternate_names" in sql, sql
