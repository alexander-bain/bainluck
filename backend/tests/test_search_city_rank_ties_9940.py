"""#9940 — a club query's text-rank key reads "covers every word", then kickoff.

The route proof (`new york` on real Postgres, with the strawman) is
`tests/integration/test_search_city_rank_ties_pg_9940.py`. These pin the two
controls the Postgres fixture cannot: a query that names no club keeps today's
`search_rank.desc()` byte for byte, and in a club query a row that misses a
word of the query still sorts under every row that covers them all.
"""

from sqlalchemy import column, select
from sqlalchemy.dialects import postgresql

from app.routes.events import _search_rank_order_key


def _sql(key) -> str:
    return str(
        select(column("id")).order_by(key).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def test_no_card_keeps_the_raw_rank_byte_for_byte():
    rank = column("r")
    assert _sql(_search_rank_order_key(rank, names_a_club=False)) == _sql(rank.desc())


def test_a_club_query_ranks_by_covering_every_word():
    sql = _sql(_search_rank_order_key(column("r"), names_a_club=True))
    assert "CASE WHEN (r > 0) THEN 0 ELSE 1 END" in sql, sql
    assert "DESC" not in sql, sql


def test_a_row_missing_a_word_still_sorts_under_the_rows_that_cover_them():
    """Evaluated, not just read: covering rows (rank 2.5, 1.5, 1.0) all key 0 and
    tie, so kickoff decides them; a rank-0 row keys 1 and sorts after."""
    import sqlite3

    key = _search_rank_order_key(column("r"), names_a_club=True)
    expr = str(key.compile(compile_kwargs={"literal_binds": True}))
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (name TEXT, r REAL, kickoff INT)")
    con.executemany(
        "INSERT INTO t VALUES (?, ?, ?)",
        [("derby", 2.5, 6), ("new-home", 1.5, 18), ("tonight", 1.0, 0), ("miss", 0.0, -1)],
    )
    order = [n for (n,) in con.execute(f"SELECT name FROM t ORDER BY {expr}, kickoff")]
    assert order == ["tonight", "derby", "new-home", "miss"], order
