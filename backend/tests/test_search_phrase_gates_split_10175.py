"""#10175 — a phrase that names a market does not split across outcomes.

`world series` served three Netflix boards: "A Different World: Season 1" and
"East of Eden: Limited Series" each carry one term as a whole word, so #10163's
split rule passed them. The split reading now also requires that no open market
NAME holds the typed phrase:

    ... OR ( NOT EXISTS(open futures_markets AS phrase_named WHERE name ILIKE '%world series%')
             AND <each term a whole word in some outcome> )

The check must be UNCORRELATED (aliased), or it asks whether THIS market's name
holds the phrase, which the outcome-only rows never do, and the gate is inert.
The real-Postgres half is `tests/integration/test_search_recall_contract.py`
(#10175 rows); these guards need no server.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes import events as events_route

NAMED = "EXISTS (SELECT phrase_named.id"


def _sql(expanded) -> str:
    return str(
        select(FuturesMarket.id)
        .where(events_route._multi_term_outcome_match(expanded))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _named_subquery(sql: str) -> str:
    start = sql.index(NAMED)
    depth = 0
    for i, ch in enumerate(sql[start + len("EXISTS "):], start + len("EXISTS ")):
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            return sql[start : i + 1]
    raise AssertionError(sql)


class TestEveryTermLong:
    def test_the_phrase_is_looked_up_in_open_market_names(self):
        sub = _named_subquery(_sql([("world", None), ("series", None)]))
        assert "phrase_named.name ILIKE '%%world series%%'" in sub, sub
        assert "phrase_named.status = 'open'" in sub, sub
        assert "phrase_named.resolution_date IS NULL" in sub, sub

    def test_the_lookup_is_uncorrelated(self):
        """Correlated to the outer row it would ask about the outcome-only market's
        own name, which never holds the phrase, so the gate would never fire."""
        sub = _named_subquery(_sql([("world", None), ("series", None)]))
        assert "futures_markets." not in sub, sub
        assert "futures_outcomes" not in sub, sub

    def test_it_gates_only_the_split_reading(self):
        sql = _sql([("world", None), ("series", None)])
        assert sql.count(NAMED) == 1, sql
        assert f"NOT ({NAMED}" in sql, sql
        before = sql[: sql.index(f"NOT ({NAMED}")]
        # The one-outcome substring probe is the OR's other side, ungated.
        assert before.rstrip().endswith("OR"), before[-200:]

    def test_the_phrase_is_the_typed_terms_never_their_expansions(self):
        sub = _named_subquery(_sql([("nfl", None), ("champion", "winner")]))
        assert "'%%nfl champion%%'" in sub and "winner" not in sub, sub


class TestOtherShapesAreUnchanged:
    def test_a_short_term_beside_a_long_one(self):
        assert NAMED not in _sql([("cy", None), ("young", None)])

    def test_every_term_short(self):
        assert NAMED not in _sql([("f1", None), ("us", None)])
