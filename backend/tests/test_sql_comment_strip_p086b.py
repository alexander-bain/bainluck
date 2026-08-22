"""CAL-P086B (#2076) — the comment stripper that made the pushdown premise testable.

Every case here is a way a naive ``re.sub(r'--.*$', '')`` produces a statement
that still parses and is a DIFFERENT QUERY. That is the failure mode worth
testing: a stripper that breaks the SQL is caught by the first 400; a stripper
that silently truncates a literal is not caught by anything, and the plan you
then measure describes a query nobody will ever run.

The last two tests bind the module to its actual subject — the frozen
calibration population builder — so the tool cannot pass its unit tests while
failing on the only statement it was written for.
"""

from __future__ import annotations

import pytest

from app.utils.sql_comment_strip import count_statement_separators, strip_sql_comments


class TestLineComments:
    def test_removes_a_line_comment_and_keeps_the_newline(self):
        assert strip_sql_comments("SELECT 1 -- hi\nFROM t") == "SELECT 1 \nFROM t"

    def test_removes_a_semicolon_that_lives_inside_a_comment(self):
        sql = "SELECT 1 -- see foo(); bar();\nFROM t"
        stripped = strip_sql_comments(sql)
        assert count_statement_separators(sql) == 2
        assert count_statement_separators(stripped) == 0

    def test_a_comment_at_end_of_input_without_a_newline(self):
        assert strip_sql_comments("SELECT 1 -- trailing") == "SELECT 1 "


class TestStringLiterals:
    def test_a_double_dash_inside_a_literal_is_data(self):
        sql = "SELECT 'a--b' AS x FROM t"
        assert strip_sql_comments(sql) == sql

    def test_an_escaped_quote_does_not_end_the_literal(self):
        # If '' is read as close-then-open, the scanner leaves string state here
        # and eats ``-- not a comment`` as SQL AND the real comment as data.
        sql = "SELECT 'it''s -- fine' AS x -- gone\nFROM t"
        assert strip_sql_comments(sql) == "SELECT 'it''s -- fine' AS x \nFROM t"

    def test_a_semicolon_inside_a_literal_survives(self):
        sql = "SELECT 'a;b' AS x FROM t"
        assert strip_sql_comments(sql) == sql
        assert count_statement_separators(strip_sql_comments(sql)) == 1

    def test_a_block_comment_marker_inside_a_literal_is_data(self):
        sql = "SELECT '/* not a comment */' AS x FROM t"
        assert strip_sql_comments(sql) == sql


class TestBlockComments:
    def test_removes_a_block_comment(self):
        assert strip_sql_comments("SELECT /* x */ 1") == "SELECT  1"

    def test_postgres_block_comments_nest(self):
        # A non-nesting scanner ends at the first ``*/`` and leaves ``c */``.
        assert strip_sql_comments("SELECT /* a /* b */ c */ 1") == "SELECT  1"

    def test_unterminated_block_comment_consumes_the_rest(self):
        assert strip_sql_comments("SELECT 1 /* oops") == "SELECT 1 "


class TestQuotedIdentifiersAndDollarQuotes:
    def test_a_double_dash_inside_a_quoted_identifier_is_data(self):
        sql = 'SELECT "a--b" FROM t'
        assert strip_sql_comments(sql) == sql

    def test_a_dollar_quoted_body_is_data(self):
        sql = "SELECT $$a -- b; /* c */$$ AS x"
        assert strip_sql_comments(sql) == sql

    def test_a_tagged_dollar_quote_is_data(self):
        sql = "SELECT $tag$a -- b$tag$ AS x"
        assert strip_sql_comments(sql) == sql


class TestIdempotenceAndSafety:
    def test_stripping_twice_changes_nothing_more(self):
        sql = "SELECT 'a--b' -- c\n/* d */ FROM t"
        once = strip_sql_comments(sql)
        assert strip_sql_comments(once) == once

    def test_a_statement_with_no_comments_is_returned_verbatim(self):
        sql = "SELECT a, b FROM t WHERE c = 'x' GROUP BY 1, 2"
        assert strip_sql_comments(sql) == sql


class TestAgainstTheRealSubject:
    """The only statement this tool was written for."""

    @staticmethod
    def _fold_sql() -> str:
        from app.utils.calibration_published_twin import published_population_fold_sql

        return published_population_fold_sql()

    def test_the_frozen_fold_carries_semicolons_and_all_of_them_are_in_comments(self):
        sql = self._fold_sql()
        assert count_statement_separators(sql) >= 1, (
            "if the builder stops carrying semicolons this tool is no longer "
            "load-bearing for #2076 — delete it rather than leaving a passing "
            "test that proves nothing"
        )
        assert count_statement_separators(strip_sql_comments(sql)) == 0

    def test_stripping_the_fold_preserves_every_sql_token_that_matters(self):
        """Not a length check — a *content* check. A stripper that ate a CTE
        would still reduce the semicolon count to zero."""
        sql = self._fold_sql()
        stripped = strip_sql_comments(sql)
        for name in (
            "market_info",
            "virtual_market",
            "clean_vms",
            "field_completeness",
            "normalized",
            "mode_prices",
            "deduped",
        ):
            assert f"{name} AS (" in stripped, name
        assert stripped.count("FROM deduped d") == 1
        # The population's own literals must survive intact. These are the
        # values actually present (checked, not assumed — the first draft of
        # this test asserted ``'odds_api'`` and was WRONG: the frozen
        # population carries no source allowlist at all, which is itself a fact
        # #2076 needs, since a source predicate would be entirely NEW SQL).
        for literal in ("'kalshi'", "'polymarket'", "'resolved'", "'uncategorized'"):
            assert literal in stripped, literal

    def test_the_stripped_fold_is_shorter_but_not_empty_of_sql(self):
        sql = self._fold_sql()
        stripped = strip_sql_comments(sql)
        assert 0 < len(stripped) < len(sql)
        assert stripped.lstrip().upper().startswith("WITH ")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT 'a' -- x\n",
        "/* only a comment */",
        "",
    ],
)
def test_never_raises(sql):
    strip_sql_comments(sql)
