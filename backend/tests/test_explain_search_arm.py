"""Guard `scripts/explain_search_arm.py` against silently drifting from the route.

The script's whole value is that its output IS the production arm. A copy that
has quietly diverged is worse than no copy: it produces a plan for a query
nobody runs, and the number it yields gets recorded in an issue as if it
described production. That is the failure this file exists to prevent, and it
is the same failure #1794 already paid three cycles for in the other direction
(a number recorded with no query at all).

So the assertions here are about CORRESPONDENCE with `app.routes.events`, not
about any particular SQL text. A block of expected SQL pinned in a test would
have to be updated by hand every time the recall arms change -- i.e. by the
same hand that changed them, at the same moment, which guards nothing.
"""

from __future__ import annotations

import re

import pytest

from app.routes import events as E
from scripts.explain_search_arm import build_futures_arm, compile_sql


def _sql(query: str, arm: str = "all") -> str:
    stmt, *_ = build_futures_arm(query, arm)
    return compile_sql(stmt)


class TestArmCompiles:
    @pytest.mark.parametrize(
        "query",
        [
            "fed",                 # single term WITH a synonym expansion
            "march madness",       # multi-term, exercises the phrase-alias arms
            "us recession 2026",   # contains a sub-3-char term (the LAT-P010 path)
            "nba champion",        # the query that regressed 6,387ms -> 701ms
            "yankees",             # single term, no expansion
        ],
    )
    def test_compiles_to_runnable_sql(self, query: str) -> None:
        sql = _sql(query)
        assert sql.lstrip().upper().startswith("SELECT")
        # A leading WITH is refused by the query-plan rail, so the script would
        # emit something the only available production path cannot run.
        assert not sql.lstrip().upper().startswith("WITH")
        assert ";" not in sql

    @pytest.mark.parametrize("query", ["fed", "march madness", "yankees"])
    def test_no_doubled_percent_survives(self, query: str) -> None:
        """`%%` is the silent-failure mode, not a cosmetic one.

        Left doubled, every ILIKE matches a literal percent sign, the query
        returns nothing, and the resulting plan looks FAST. A measurement taken
        on that plan is not merely wrong, it is wrong in the flattering
        direction.
        """
        assert "%%" not in _sql(query)


class TestCorrespondenceWithRoute:
    def test_uses_the_routes_window_not_a_literal(self) -> None:
        assert f"LIMIT {E._SEARCH_FUTURES_WINDOW}" in _sql("fed")

    def test_open_and_unresolved_filter_is_pushed_into_every_arm(self) -> None:
        """AND distributes over UNION; unfiltered arms cost 6,387ms vs 701ms.

        See the comment at `events.py:3031`. The outer copy is deliberate
        redundancy, so the predicate must appear once per arm PLUS once
        outside it.
        """
        sql = _sql("fed")
        n_arms = sql.count("UNION") + 1
        assert sql.count("futures_markets.status = 'open'") >= n_arms + 1

    def test_name_arm_alone_is_a_strict_subset(self) -> None:
        """`--arm name` is the decomposition that isolates the outcome arm's cost."""
        full = _sql("fed")
        name_only = _sql("fed", arm="name")
        assert "futures_outcomes" in full
        assert "futures_outcomes" not in name_only
        assert "UNION" not in name_only

    def test_synonym_expansion_reaches_both_recall_and_rank(self) -> None:
        """LAT-P033/#1732: an expansion must WIDEN its term, never replace it.

        `fts_q` was once `exp if exp else term`, which zeroed the rank of 311
        of the 316 `fed` name matches. Both sides must mention both strings.
        """
        sql = _sql("fed")
        assert "'%fed%'" in sql and "'%federal reserve%'" in sql
        rank = sql[sql.index("ts_rank_cd"):]
        assert "'fed'" in rank and "'federal reserve'" in rank

    def test_ranks_on_the_name_vector_only(self) -> None:
        """#993 Slice-Speed dropped the correlated string_agg(outcome names).

        It cost ~151ms per candidate row and outcome text was weight C.
        """
        sql = _sql("fed")
        assert "string_agg" not in sql
        assert "setweight" in sql

    def test_name_match_tier_is_enforced_in_sql_ahead_of_rank(self) -> None:
        """LAT-P033/#1732: the reranker runs AFTER the LIMIT, so it cannot fix
        a page boundary that cut across tiers. The ORDER BY must carry the
        tier first."""
        sql = _sql("fed")
        order = sql[sql.rindex("ORDER BY"):]
        assert order.index("CASE WHEN") < order.index("ts_rank_cd")

    def test_timestamp_is_the_only_nondeterminism(self) -> None:
        """Two compiles a moment apart must differ only in `now()`.

        Anything else varying means the output cannot be diffed across cycles,
        which is the entire point of recording it.
        """
        strip = lambda s: re.sub(
            r"'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(\.\d+)?\+00:00'", "'TS'", s
        )
        assert strip(_sql("fed")) == strip(_sql("fed"))
