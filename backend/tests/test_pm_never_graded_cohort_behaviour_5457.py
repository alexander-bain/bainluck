"""#5457 — the never-graded cohort predicate, graded on ROWS instead of on its own text.

`futures_outcomes.is_winner` has column default `false`, so a market nobody ever
graded is indistinguishable, to any reader keyed on that column, from a market
graded as all-losers. The only honest discriminator is `resolution_source`.

`repair_pm_never_graded.POPULATION_HAVING_SQL` is the predicate that draws that
line, and it is the safety rail under a 274,262-market cohort (live census,
2026-09-12 04:2xZ): a repair keyed on "every outcome is a loser, so write the
winner" would fabricate winners onto every one of them.

WHY THIS FILE EXISTS BESIDE `test_repair_pm_never_graded.py`
------------------------------------------------------------
That file's cohort test is a SUBSTRING SCAN::

    assert "bool_and(fo.resolution_source IS NULL)" in POPULATION_HAVING_SQL
    assert "bool_or(fo.is_winner) IS NOT TRUE" in POPULATION_HAVING_SQL

A source scan proves the text is PRESENT, not that it RUNS — and not that it
classifies anything correctly. `test_the_substring_guard_cannot_see_the_defect_
this_file_catches` below demonstrates that directly: it builds a one-character
mutant (`AND` -> `OR`) that passes all three of those assertions and then counts
a genuinely-graded all-losers market as never-graded. That mutant is the exact
shape of the fabrication this cohort exists to prevent.

METHOD
------
There is no local Postgres, so the REAL `_CENSUS_SQL` string is executed
verbatim against SQLite with `bool_or`/`bool_and` registered as aggregates. The
production predicate itself is under test — not a paraphrase of it — so a future
edit to `POPULATION_HAVING_SQL` is graded by what it SELECTS.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.tasks.repair_pm_never_graded import (
    POPULATION_HAVING_SQL,
    _CENSUS_SQL,
)


class _BoolOr:
    """Postgres `bool_or`: TRUE if any input is true, else FALSE."""

    def __init__(self) -> None:
        self.value = False

    def step(self, x) -> None:
        if x:
            self.value = True

    def finalize(self) -> bool:
        return self.value


class _BoolAnd:
    """Postgres `bool_and`: TRUE unless some input is false."""

    def __init__(self) -> None:
        self.value = True

    def step(self, x) -> None:
        if not x:
            self.value = False

    def finalize(self) -> bool:
        return self.value


#: (market_id, source, status, external_id, category)
#: Every market carries NO winner, so `is_winner` alone cannot tell any of them
#: apart. `resolution_source` is the only thing that differs.
_MARKETS = [
    # IN the cohort: nothing ever graded these.
    (1, "polymarket", "resolved", "0xaaa", "soccer"),
    (2, "polymarket", "resolved", "0xbbb", "tennis"),
    # OUT: something ran, looked, and wrote "loser" on every leg. A wrong
    # answer, not a missing one — and it needs the OPPOSITE fix.
    (3, "polymarket", "resolved", "0xccc", "soccer"),
    # OUT: partially graded. Left to the authority ladder rather than half
    # rewritten here — `bool_and` is what makes that true.
    (4, "polymarket", "resolved", "0xddd", "tennis"),
    # OUT: graded, with a winner crowned.
    (5, "polymarket", "resolved", "0xeee", "soccer"),
    # OUT: ungraded but a winner is already crowned — `bool_or(is_winner) IS
    # NOT TRUE` is the conjunct that holds this one out.
    (6, "polymarket", "resolved", "0xfff", "soccer"),
    # OUT: not this source.
    (7, "kalshi", "resolved", "0x111", "soccer"),
    # OUT: `status='open'`. Every rail here keys on `status='resolved'`, so this
    # exclusion is real and worth pinning — but it is a SMALL tail, not a hole:
    # 139 never-graded Polymarket markets carried a PAST `resolution_date` with
    # `status='open'` on 2026-09-12 (production db-query), and 82 of those were
    # under two days old, i.e. ordinary settlement lag. Only ~56 were older than
    # a week. Stated with the `< NOW()` bound because without it the same query
    # returns 28,228 — markets that simply have not resolved yet, for which
    # `status='open'` and no grade is the correct state and not a defect.
    (8, "polymarket", "open", "0x222", "soccer"),
    # OUT: not a condition-id market.
    (9, "polymarket", "resolved", "213569", "soccer"),
]

#: (market_id, is_winner, resolution_source)
_OUTCOMES = [
    (1, 0, None),
    (1, 0, None),
    (2, 0, None),
    (2, 0, None),
    (3, 0, "api_settlement"),
    (3, 0, "api_settlement"),
    (4, 0, None),
    (4, 0, "api_settlement"),
    (5, 1, "api_settlement"),
    (5, 0, "api_settlement"),
    (6, 1, None),
    (6, 0, None),
    (7, 0, None),
    (7, 0, None),
    (8, 0, None),
    (8, 0, None),
    (9, 0, None),
    (9, 0, None),
]


def _census(sql: str) -> dict[str, int]:
    """Run a census statement against the fixture and return {category: markets}."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.create_aggregate("bool_or", 1, _BoolOr)
        conn.create_aggregate("bool_and", 1, _BoolAnd)
        conn.execute(
            "CREATE TABLE futures_markets ("
            "id INTEGER, source TEXT, status TEXT, external_id TEXT,"
            " llm_sport_category TEXT)"
        )
        conn.execute(
            "CREATE TABLE futures_outcomes ("
            "market_id INTEGER, is_winner INTEGER, resolution_source TEXT)"
        )
        conn.executemany("INSERT INTO futures_markets VALUES (?,?,?,?,?)", _MARKETS)
        conn.executemany("INSERT INTO futures_outcomes VALUES (?,?,?)", _OUTCOMES)
        return {row[0]: row[1] for row in conn.execute(sql).fetchall()}
    finally:
        conn.close()


def test_the_real_census_sql_runs_and_selects_only_the_never_graded_markets():
    """Both directions, on the production string: markets 1 and 2 are IN, and
    every other shape carrying the same all-false `is_winner` is OUT."""
    assert _census(_CENSUS_SQL) == {"soccer": 1, "tennis": 1}


@pytest.mark.parametrize(
    "market_id, category, why",
    [
        (1, "soccer", "no leg carries a resolution_source"),
        (2, "tennis", "no leg carries a resolution_source"),
    ],
)
def test_a_never_graded_market_is_classified_ungraded(market_id, category, why):
    """Direction 1 — the cohort must CONTAIN the markets nobody graded. A
    predicate that quietly drops them reads as "already drained"."""
    assert _census(_CENSUS_SQL).get(category, 0) >= 1, why


def test_a_genuinely_graded_all_losers_market_is_not_in_the_cohort():
    """Direction 2 — market 3 has `is_winner=false` on every leg, exactly like
    market 1, and differs ONLY by carrying a source. It must not be counted, or
    the repair would overwrite a real verdict."""
    soccer_only = [m for m in _MARKETS if m[4] == "soccer"]
    assert len(soccer_only) > 1, "fixture must not make this vacuous"
    # Markets 3, 5, 6, 8 and 9 are all soccer and all excluded; only market 1 counts.
    assert _census(_CENSUS_SQL)["soccer"] == 1


def test_a_partially_graded_market_is_left_to_the_authority_ladder():
    """`bool_and` (not `bool_or`) is what holds market 4 out. Tennis contains
    markets 2 (never graded) and 4 (half graded); only 2 may be counted."""
    assert _census(_CENSUS_SQL)["tennis"] == 1


def test_the_substring_guard_cannot_see_the_defect_this_file_catches():
    """The point of this file, stated as an executable claim.

    A one-character mutation of the conjunction passes every assertion in
    `test_the_population_is_the_never_graded_cohort_not_the_mis_graded_one`
    and then counts the genuinely-graded all-losers market as never-graded —
    i.e. it hands a 274,262-market write rail a population containing markets
    that already have a verdict.
    """
    mutant_having = POPULATION_HAVING_SQL.replace(
        "   AND bool_and(fo.resolution_source IS NULL)",
        "   OR bool_and(fo.resolution_source IS NULL)",
    )
    assert mutant_having != POPULATION_HAVING_SQL, "the mutation must apply"

    # The existing substring guard is blind to it: all three assertions hold.
    assert "bool_and(fo.resolution_source IS NULL)" in mutant_having
    assert "bool_or(fo.is_winner) IS NOT TRUE" in mutant_having
    assert "pass2_loser" not in mutant_having

    mutant_sql = _CENSUS_SQL.replace(POPULATION_HAVING_SQL, mutant_having)
    assert mutant_sql != _CENSUS_SQL, "the mutant must reach the census SQL"

    # ...and this file is not: the graded all-losers market is now swept in.
    assert _census(mutant_sql)["soccer"] > _census(_CENSUS_SQL)["soccer"]


def test_is_winner_alone_cannot_separate_the_classes():
    """The mechanism sentence of #5457, pinned. Every market in the fixture that
    the cohort accepts and every market it rejects for having a source share the
    SAME `is_winner` picture — all false. Any guard keyed on `is_winner` would
    have to treat markets 1 and 3 identically; `resolution_source` is the only
    column that tells them apart."""
    winners = {m: set() for m in (1, 3)}
    sources = {m: set() for m in (1, 3)}
    for market_id, is_winner, source in _OUTCOMES:
        if market_id in winners:
            winners[market_id].add(bool(is_winner))
            sources[market_id].add(source)

    assert winners[1] == winners[3] == {False}, "is_winner cannot discriminate"
    assert sources[1] != sources[3], "resolution_source is the discriminator"
