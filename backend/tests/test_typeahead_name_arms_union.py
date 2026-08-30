"""The typeahead futures NAME arm reaches the UNION SPLIT, never as one OR — LAT-P140.

WHAT BROKE, AND WHY A HELPER TEST ALONE WOULD NOT HAVE CAUGHT IT.

`ix_futures_name_fts_open` landed in production 2026-08-29 and did exactly what
LAT-P096's spec predicted for SELECTIVE terms — `werder` 4,722 -> 5.7 ms, a
BitmapOr over both GINs. It did NOT fix the terms a person actually types. The
planner abandons both GINs whenever either half of `FTS(name) OR name ILIKE
'%q%'` is estimated non-selective, because the flat `ix_futures_markets_status`
scan has a FIXED cost (37,715) that a broad union exceeds. Measured that day:

    chi      1,283 rows  1,250.1 ms   no BitmapOr, ix_futures_markets_status
    chicago    220 rows    917.9 ms   no BitmapOr   <- row count is NOT the trigger
    winner   4,762 rows    881.5 ms   no BitmapOr
    yan        311 rows    115.0 ms   BitmapOr over both GINs

`chicago` (220 rows) falls back while `yan` (311 rows) does not, so no row-count
threshold expresses this. Splitting the OR into two UNION arms lets each half be
costed on its OWN selectivity: `chi` 1,250.1 -> 22.9 ms, IDENTICAL rows (count +
server-side md5 of the ORDER-BY-id id set, on all ten census terms).

⚠️ THE POINT OF THIS FILE IS THE RENDER, NOT THE HELPER. `_futures_name_arms`
can return a perfect two-element list and the route can still fold it back into
one `or_` before it reaches the UNION — in which case every shape assertion on
the helper stays green while production keeps paying 1,250 ms. That is the
`plant must hit the RENDER` rule this repo learned the hard way, so the
load-bearing assertions here read `typeahead_search`'s OWN SOURCE and the
compiled arm SELECTs, not just the helper's output.

It does not touch the database and it asserts no timings — a timing assertion
against a planner whose choice moves with table statistics is a flake, and the
production numbers are banked in `_futures_name_arms`' docstring instead.
"""

from __future__ import annotations

import inspect
import re

from sqlalchemy import or_, select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket
from app.routes.events import (
    _build_expanded_ilike,
    _build_futures_name_filter,
    _futures_name_arms,
    typeahead_search,
)

TERM = "chi"


def _sql(clause) -> str:
    return str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


def _arms(term: str = TERM) -> list:
    return _futures_name_arms(_build_expanded_ilike(FuturesMarket.name, term, None), term)


class TestTheSplitIsReal:
    """Two arms, and neither one carries both halves."""

    def test_there_are_exactly_two_arms(self):
        assert len(_arms()) == 2, (
            "the futures NAME arm is FTS + ILIKE. A third arm, or a collapse to "
            "one, is a recall change and belongs behind its own gate."
        )

    def test_the_fts_arm_is_fts_only(self):
        sql = _sql(_arms()[0])
        assert "to_tsvector" in sql and "websearch_to_tsquery" in sql
        assert "ILIKE" not in sql.upper(), (
            "the FTS arm carries an ILIKE, so this is still the OR wearing a "
            "list's clothes — the planner will cost the union, not the half, "
            "and `chi` goes back to 1,250 ms."
        )

    def test_the_ilike_arm_is_ilike_only(self):
        sql = _sql(_arms()[1])
        assert "ILIKE" in sql.upper()
        assert "to_tsvector" not in sql, (
            "the ILIKE arm carries a tsvector, so `ix_futures_name_trgm` cannot "
            "serve it alone — the exact defect the split exists to remove."
        )

    def test_no_single_arm_can_defeat_its_own_index(self):
        # The whole thesis in one assertion: no arm mixes the two predicates,
        # so no arm's plan can be chosen on the union's selectivity.
        for arm in _arms():
            sql = _sql(arm).upper()
            assert not ("TO_TSVECTOR" in sql and "ILIKE" in sql)


class TestTheHalvesCannotDrift:
    """`_build_futures_name_filter` stays the OR fold of these same arms."""

    def test_the_or_helper_is_exactly_this_list_folded(self):
        arms = _arms()
        assert _sql(_build_futures_name_filter(
            _build_expanded_ilike(FuturesMarket.name, TERM, None), TERM
        )) == _sql(or_(*arms)), (
            "`_build_futures_name_filter` and `_futures_name_arms` have drifted. "
            "They are ONE definition of what the halves are — the docstring's "
            "recall census (champions 405 -> 598) grades the OR form, and it "
            "stops grading the UNION form the moment these differ."
        )

    def test_expansion_still_reaches_the_ilike_arm(self):
        # `fed` -> `federal reserve`: the expansion rides the ILIKE half, and the
        # split must not drop it (that would be a silent recall loss, LAT-P033).
        arms = _futures_name_arms(
            _build_expanded_ilike(FuturesMarket.name, "fed", "federal reserve"), "fed"
        )
        assert "federal reserve" in _sql(arms[1]).lower()


class TestTheRenderActuallySplits:
    """Read the route's own source. A helper that is never used is not a fix."""

    def _source(self) -> str:
        return inspect.getsource(typeahead_search)

    def test_the_arm_list_seeds_the_union(self):
        src = self._source()
        assert re.search(r"ta_futures_where\s*=\s*\[\*\s*futures_name_arms\s*\]", src), (
            "`ta_futures_where` is no longer seeded from the split arm list. "
            "Whatever it is seeded from now reaches the UNION as ONE arm."
        )

    def test_typeahead_does_not_rebuild_the_or(self):
        assert "_build_futures_name_filter" not in self._source(), (
            "`/typeahead` calls the OR helper again. That is the 1,250 ms "
            "`chi` plan restored — the OR belongs to callers that are not on "
            "the keystroke path."
        )

    def test_the_arms_are_still_unioned_and_not_ord(self):
        src = self._source()
        assert "union(*_ta_arm_selects)" in src, (
            "the LAT-P007 UNION fold is gone; an OR across arms blocks the "
            "hash-semi-join transformation for every arm, not just this one."
        )
        assert re.search(r"or_\(\s*\*?\s*futures_name_arms", src) is None, (
            "the arms are being OR'd back together before the UNION sees them."
        )


class TestTheCompiledUnionBranchesStaySeparate:
    """Fold the arms the way the route does and check each SELECT branch."""

    def test_each_branch_carries_one_predicate_class(self):
        selects = [select(FuturesMarket.id).where(arm) for arm in _arms()]
        branch_sql = [_sql(s).upper() for s in selects]
        assert sum("TO_TSVECTOR" in b for b in branch_sql) == 1
        assert sum("ILIKE" in b for b in branch_sql) == 1
        for b in branch_sql:
            assert not ("TO_TSVECTOR" in b and "ILIKE" in b), (
                "a single UNION branch carries both predicates, so that branch "
                "is the old OR and the planner will fall back on it alone."
            )
