"""Guard tests for Queue #204 Item 2: dead/flat lines excluded from divergence.

The source-intelligence "Dramatic Disagreements" corpus computes cross-source
win-probability divergence. A source whose live series never moves (a dead/stuck
feed — ESPN's MLB win-prob line flatlines near zero on ~36% of games it covers)
is not a live opinion, and a divergence measured against a dead line is not a
disagreement.

The fix requires every "rich source" — the bar for being a party to any counted
divergence — to be non-flat (STDDEV_POP over its live series >= FLAT_EPSILON).
Because ``_RICH_SOURCES_CTE`` gates all four corpus queries (coverage, accuracy,
disagreements, case studies), enforcing the floor there means both parties to
every counted divergence are alive.

These are SQL-shape guards (the corpus SQL only runs on Postgres — STDDEV_POP,
JSONB, correlated CTEs), matching the repo's compile-and-assert test style.
"""

from app.routes import source_intelligence as si


def test_flat_epsilon_is_a_small_positive_floor():
    # A real MLB game's win prob always moves more than a couple points over its
    # course, so the floor must be small enough to keep every live game and only
    # remove genuinely dead feeds.
    assert 0 < si.FLAT_EPSILON <= 0.05


def test_rich_sources_cte_enforces_non_flat_requirement():
    cte = si._RICH_SOURCES_CTE
    # The min-snapshot bar is still present...
    assert f"COUNT(*) >= {si.MIN_SNAPS}" in cte
    # ...AND the new non-flat (liveness) bar is applied to the same source group.
    assert "STDDEV_POP(wp.home_win_probability)" in cte
    assert f">= {si.FLAT_EPSILON}" in cte


def test_non_flat_requirement_lives_in_the_having_clause():
    # It must gate which (event, source) pairs qualify as "rich", not merely
    # appear somewhere in the string — i.e. it sits in the HAVING after the
    # snapshot-count floor.
    cte = si._RICH_SOURCES_CTE
    having_idx = cte.index("HAVING")
    stddev_idx = cte.index("STDDEV_POP(wp.home_win_probability)")
    assert stddev_idx > having_idx


def test_rich_sources_cte_is_shared_by_every_corpus_query():
    # The single leverage point: the same CTE fragment feeds coverage, accuracy,
    # disagreements, and case studies, so the liveness floor propagates to all of
    # them. If someone forks a private copy, this guard should be revisited.
    src = si.__file__
    with open(src) as fh:
        body = fh.read()
    # Used via f-string interpolation in each query builder.
    assert body.count("{_RICH_SOURCES_CTE}") >= 4
