"""#10163 — two long terms split across outcomes must each be a WHOLE word.

`wild card` served "NCAAB Championship Winner" because `_multi_term_outcome_match`
accepted `wild` inside Kentucky Wildcats and `card` inside Louisville Cardinals,
two different outcomes. The all-long arm is now:

    id = ANY(ARRAY(outcomes WHERE %wild%))          -- the substring arm, unchanged:
    AND id = ANY(ARRAY(outcomes WHERE %card%))      -- it still drives the scan
    AND ( EXISTS(this market's outcome WHERE %wild% AND %card%)       -- one outcome
          OR ( EXISTS(this market's outcome WHERE wild is a whole word)
               AND EXISTS(this market's outcome WHERE card is a whole word) ) )

The refinement probes by `market_id`, not by trigram: a second trigram scan read
2-2.7x the substring arm on production 2026-10-02. The recall half on real
Postgres is `tests/integration/test_search_recall_contract.py` (#10163 rows);
these guards need no server.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes import events as events_route

ARRAY_ARM = "= ANY (array((SELECT futures_outcomes.market_id"
PROBE = "EXISTS (SELECT futures_outcomes.id"
CORRELATED = "futures_outcomes.market_id = futures_markets.id"


def _sql(expanded) -> str:
    return str(
        select(FuturesMarket.id)
        .where(events_route._multi_term_outcome_match(expanded))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _probes(sql: str) -> list[str]:
    return [p.split("))")[0] for p in sql.split(PROBE)[1:]]


def _whole_word(term: str) -> str:
    return f"~* '(^|[^[:alnum:]]){term}([^[:alnum:]]|$)'"


class TestEveryTermLong:
    def test_the_substring_arm_still_drives(self):
        sql = _sql([("wild", None), ("card", None)])
        assert sql.count(ARRAY_ARM) == 2, sql
        arrays = [p.split("))")[0] for p in sql.split(ARRAY_ARM)[1:]]
        assert sorted("%%wild%%" in a for a in arrays) == [False, True], arrays
        assert all("~*" not in a for a in arrays), arrays

    def test_one_outcome_holding_every_term_matches_by_substring(self):
        probes = _probes(_sql([("wild", None), ("card", None)]))
        one = [p for p in probes if "%%wild%%" in p and "%%card%%" in p]
        assert len(one) == 1, probes
        assert "~*" not in one[0] and CORRELATED in one[0], one

    def test_split_across_outcomes_each_term_is_a_whole_word(self):
        probes = _probes(_sql([("wild", None), ("card", None)]))
        for term in ("wild", "card"):
            whole = [p for p in probes if _whole_word(term) in p]
            assert len(whole) == 1 and CORRELATED in whole[0], (term, probes)

    def test_the_two_rules_are_alternatives_not_both_required(self):
        sql = _sql([("wild", None), ("card", None)])
        refinement = sql[sql.index(PROBE) - 2:]
        assert re.search(r"\)\) OR \(EXISTS", refinement), refinement

    def test_an_expansion_is_a_whole_word_too(self):
        probes = _probes(_sql([("nfl", None), ("champion", "winner")]))
        whole = [p for p in probes if _whole_word("champion") in p]
        assert len(whole) == 1 and _whole_word("winner") in whole[0], probes

    def test_a_regex_metacharacter_is_escaped(self):
        # Literal binds double the backslash `_regex_escape` adds: `inc\\.`.
        probes = _probes(_sql([("inc.", None), ("apple", None)]))
        assert any("inc\\\\.([^[:alnum:]]|$)" in p for p in probes), probes


class TestOtherShapesAreUnchanged:
    def test_a_short_term_beside_a_long_one_keeps_the_9646_anchor(self):
        sql = _sql([("cy", None), ("young", None)])
        assert PROBE not in sql and sql.count(ARRAY_ARM) == 1, sql

    def test_every_term_short(self):
        sql = _sql([("f1", None), ("us", None)])
        assert PROBE not in sql and sql.count(ARRAY_ARM) == 2, sql

    def test_outcome_whole_word_keeps_its_own_sql(self):
        """The regex moved into `_outcome_whole_word_regex`; the split and club
        arms that call `_outcome_whole_word` compile exactly as before."""
        sql = str(
            events_route._outcome_whole_word("yank").compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert sql == (
            "futures_outcomes.name ILIKE '%%yank%%' AND (futures_outcomes.name "
            "~* '(^|[^[:alnum:]])yank([^[:alnum:]]|$)')"
        ), sql
