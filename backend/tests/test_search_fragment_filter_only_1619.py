"""#1619 — a fragment term stops lying to the planner when a sibling can drive the scan.

`f1 champion`'s futures NAME arm cost 766-1,750 ms on production (2026-10-01). `f1`
has no extractable trigram, so `ix_futures_name_trgm` cannot narrow on it — but the
planner still priced its ILIKE as selective and folded that into the bitmap's row
estimate. Believing the bitmap tiny, it skipped ANDing it with an open-markets
index and rechecked 83,000 candidates of every status on the heap (52,435 blocks)
for 6 open answers.

The fix spells the fragment's two tests on `lower(name)`, which no index serves, so
they run as a filter and the trigram term drives the scan. Postgres's ILIKE on a
multibyte database IS `lower(text) LIKE lower(pattern)` and `~*` ignores case on
both sides, so the rows are identical: production returned the same 6 ids (count +
md5) for `f1 champion`/`f1 winner` and the same 4 for `us open`, at 191-471 ms /
8-24 ms.

These run on the compiled SQL — no Postgres. The real-database twin is
`tests/integration/test_search_recall_contract.py::
test_a_fragment_term_matches_a_word_start_not_an_infix` (`us open` reaches this
path through the route).
"""
from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.dialects import postgresql

from app.models import FuturesMarket
from app.routes import events as events_route


def _compile(clause) -> str:
    return str(
        select(FuturesMarket.id)
        .where(clause)
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )


def _expanded(q: str):
    terms = events_route._strip_search_scaffolding(q.split())
    return events_route._apply_search_synonyms(events_route.expand_search_terms(terms))


def _arm_sql(q: str) -> str:
    return _compile(and_(*events_route._futures_multi_term_name_conditions(_expanded(q))))


def _old_arm_sql(q: str) -> str:
    """The pre-#1619 arm: every term in its default (index-driving) shape."""
    return _compile(and_(*[
        events_route._futures_name_match_term(t, e) for t, e in _expanded(q)
    ]))


def test_the_production_specimen_spells_its_fragment_as_a_filter():
    sql = _arm_sql("f1 champion")
    assert "lower(futures_markets.name) LIKE lower('%%f1%%')" in sql, sql
    assert "lower(futures_markets.name) ~* '(^|[^[:alnum:]])f1'" in sql, sql
    # the fragment no longer appears in an index-servable spelling...
    assert "futures_markets.name ILIKE '%%f1%%'" not in sql, sql
    assert "futures_markets.name ~* '(^|[^[:alnum:]])f1'" not in sql.replace(
        "lower(futures_markets.name) ~*", ""
    ), sql
    # ...and the trigram term still does, so something drives the scan.
    assert "futures_markets.name ILIKE '%%champion%%'" in sql, sql
    assert "futures_markets.name ILIKE '%%winner%%'" in sql, sql


def test_us_open_takes_the_same_path():
    sql = _arm_sql("us open")
    assert "lower(futures_markets.name) LIKE lower('%%us%%')" in sql, sql
    assert "futures_markets.name ILIKE '%%open%%'" in sql, sql


def test_the_filter_keeps_both_halves_of_the_word_start_rule():
    """#8689's word-start regex survives the respelling — only the subject moves."""
    old = _old_arm_sql("f1 champion")
    new = _arm_sql("f1 champion")
    assert old.count("(^|[^[:alnum:]])f1") == new.count("(^|[^[:alnum:]])f1") == 1


def test_no_trigram_sibling_means_no_change():
    """All fragments: the fragment's ILIKE is the only scan there is."""
    assert _arm_sql("f1 gp") == _old_arm_sql("f1 gp")
    assert "lower(" not in _arm_sql("f1 gp")


def test_a_query_without_a_fragment_is_byte_identical():
    for q in ("nba champion", "world series", "lebron james"):
        assert _arm_sql(q) == _old_arm_sql(q), q


def test_a_fragment_carrying_an_expansion_keeps_its_shape():
    """`la` -> `los angeles` is a term the index CAN narrow on; it is not demoted."""
    expanded = _expanded("la lakers")
    assert any(e for t, e in expanded if t == "la"), expanded
    assert _arm_sql("la lakers") == _old_arm_sql("la lakers")


def test_the_default_shape_is_untouched_for_every_other_caller():
    """`_build_word_start_ilike` is shared with the team arms; its default is unchanged."""
    sql = _compile(events_route._build_word_start_ilike(FuturesMarket.name, "us", None))
    assert "futures_markets.name ILIKE '%%us%%'" in sql, sql
    assert "lower(" not in sql, sql
