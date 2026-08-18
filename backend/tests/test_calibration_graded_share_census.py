"""The graded-share census rail (CAL-P068 item 2).

The selection-bias rule shipped in CAL-P067 and rendered nothing, because it had
no denominator. This is the denominator.

What the suite actually guards is not the arithmetic — it is the two ways a
census can lie:

1. **A skipped page counted as zero.** The whole population cannot be aggregated
   in one query (measured this window: the single-category version, and even a
   bare ``count(*)`` on resolved markets, both hit ``statement_timeout``), so it
   is paged. A page that fails must be COUNTED and NAMED, never silently
   dropped — gotcha #53, and ruling 075's second clause.

2. **A partial census used as a denominator.** This is the dangerous one and it
   fails in one direction only: a denominator missing part of its own population
   is too SMALL, which makes every graded share too LARGE, which flips cells from
   NOT-PROVABLE to provable. An incomplete census must therefore be unusable, not
   merely caveated.
"""

import pytest

from app.tasks.calibration_graded_share import (
    CELL_POPULATION,
    PAGE_MARKETS,
    UNIT_OUTCOMES,
    census_from_payload,
    run_graded_share_census,
)
from app.utils.calibration_provability import GradedShareCensus


class _FakeSession:
    """Replays market pages and per-page aggregates; can be told to fail a page."""

    def __init__(self, pages, aggs, fail_agg_on=()):
        self.pages = list(pages)
        self.aggs = list(aggs)
        self.fail_agg_on = set(fail_agg_on)
        self._page_i = 0
        self._agg_i = 0
        self.rolled_back = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SET LOCAL statement_timeout" in sql:
            return _Result([])
        if "FROM futures_markets" in sql and "ORDER BY id" in sql:
            page = self.pages[self._page_i] if self._page_i < len(self.pages) else []
            self._page_i += 1
            return _Result([(i,) for i in page])
        # the outcome aggregate
        idx = self._agg_i
        self._agg_i += 1
        if idx in self.fail_agg_on:
            raise RuntimeError("statement_timeout")
        return _Result(self.aggs[idx] if idx < len(self.aggs) else [])

    async def rollback(self):
        self.rolled_back += 1


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


async def test_a_complete_census_is_usable_and_sums_across_pages():
    session = _FakeSession(
        pages=[[1, 2, 3], []],
        aggs=[[("soccer", 100, 25), ("hockey", 50, 50)]],
    )
    out = await run_graded_share_census(session, max_pages=5)
    assert out["complete"] is True
    assert out["usable_as_denominator"] is True
    assert out["pages_failed"] == 0
    assert out["by_category"]["soccer"] == {"total_outcomes": 100, "graded_outcomes": 25}
    assert out["unit"] == UNIT_OUTCOMES
    assert out["population"] == CELL_POPULATION
    assert out["reason"] is None


async def test_a_failed_page_is_counted_and_NAMED_never_dropped():
    """A hole you cannot name is a hole you cannot go back and fill."""
    session = _FakeSession(
        pages=[[1, 2, 3], [10, 11, 12], []],
        aggs=[[("soccer", 100, 25)], [("soccer", 10, 10)]],
        fail_agg_on={0},
    )
    out = await run_graded_share_census(session, max_pages=5)
    assert out["pages_failed"] == 1
    assert out["failed_ranges"] == [[0, 3]]
    assert out["complete"] is False
    assert out["usable_as_denominator"] is False
    assert "failed" in out["reason"]
    assert session.rolled_back == 1


async def test_an_incomplete_census_is_unusable_as_a_denominator():
    """The one-directional failure: a short denominator inflates every share and
    would flip cells from NOT-PROVABLE to provable."""
    # A FULL page (a short page would legitimately mean "end of population"),
    # so the run stops on max_pages with the population still un-walked.
    session = _FakeSession(
        pages=[list(range(1, PAGE_MARKETS + 1))],
        aggs=[[("soccer", 100, 25)]],
    )
    out = await run_graded_share_census(session, max_pages=1)
    assert out["exhausted"] is False
    assert out["usable_as_denominator"] is False
    assert census_from_payload(out) is None


async def test_the_cursor_resumes_where_the_previous_call_stopped():
    first = _FakeSession(pages=[[1, 2, 5]], aggs=[[("soccer", 10, 5)]])
    out1 = await run_graded_share_census(first, max_pages=1)
    assert out1["cursor"] == 5

    second = _FakeSession(pages=[[6, 7], []], aggs=[[("soccer", 4, 4)]])
    out2 = await run_graded_share_census(second, max_pages=5, start_cursor=out1["cursor"], prior=out1)
    # totals composed across both calls
    assert out2["by_category"]["soccer"] == {"total_outcomes": 14, "graded_outcomes": 9}
    assert out2["complete"] is True
    assert out2["pages_ok"] == 2


async def test_a_short_final_page_ends_the_run():
    session = _FakeSession(pages=[[1, 2]], aggs=[[("soccer", 3, 3)]])
    out = await run_graded_share_census(session, max_pages=9)
    assert len(session.pages[0]) < PAGE_MARKETS
    assert out["exhausted"] is True
    assert out["complete"] is True


# =============================================================================
# census_from_payload — the gate between a census and a published verdict
# =============================================================================


def _complete(by_category):
    return {
        "schema": "calibration-graded-share/v1",
        "unit": UNIT_OUTCOMES,
        "population": CELL_POPULATION,
        "by_category": by_category,
        "usable_as_denominator": True,
    }


def test_a_complete_payload_becomes_a_typed_census():
    c = census_from_payload(
        _complete({"soccer": {"total_outcomes": 393_524, "graded_outcomes": 98_381}})
    )
    assert isinstance(c, GradedShareCensus)
    assert c.by_key == {"soccer": 393_524}
    assert c.unit == UNIT_OUTCOMES
    assert c.incoherence() is None


def test_the_typed_census_flips_soccer_exactly_as_the_ruling_says():
    """End to end: rail output -> census -> verdict, on the ruling's own cell."""
    from app.utils.calibration_provability import annotate_cells

    c = census_from_payload(
        _complete({"soccer": {"total_outcomes": 393_524, "graded_outcomes": 98_381}})
    )
    out = annotate_cells([{"category": "soccer", "n": 98_381, "mce": 3.54}], census=c)
    assert out[0]["provability"] == "not_provable_selection_biased"
    assert out[0]["graded_share"] == pytest.approx(0.25, abs=0.001)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "nope",
        {},
        {"usable_as_denominator": False, "by_category": {"soccer": {"total_outcomes": 10}}},
        _complete({}),
        _complete({"soccer": {"total_outcomes": 0, "graded_outcomes": 0}}),
        _complete({"soccer": "junk"}),
    ],
)
def test_anything_short_of_a_complete_census_yields_none(payload):
    assert census_from_payload(payload) is None


def test_a_census_that_yields_none_leaves_cells_unknown_not_provable():
    """The composition that matters: no usable census => unknown, never a pass."""
    from app.utils.calibration_provability import annotate_cells

    out = annotate_cells(
        [{"category": "soccer", "n": 98_381}],
        census=census_from_payload({"usable_as_denominator": False}),
    )
    assert out[0]["provability"] == "unknown"


# =============================================================================
# Route wiring — the rule is live the moment a complete census exists
# =============================================================================


def test_the_route_reads_the_census_artifact_and_the_rule_renders(monkeypatch):
    """CAL-P068 item 2's whole point: 'a ruling that renders nothing protects
    nobody'. With a complete census published, soccer flips on the page."""
    import json as _json

    from app.routes import calibration as route

    class _RC:
        def get(self, key):
            assert key == route.GRADED_SHARE_CACHE_KEY
            return _json.dumps(
                _complete(
                    {
                        "soccer": {"total_outcomes": 393_524, "graded_outcomes": 98_381},
                        "baseball": {"total_outcomes": 200_000, "graded_outcomes": 192_090},
                    }
                )
            )

    monkeypatch.setattr(route, "PROVABILITY_CENSUS", {})
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: _RC()
    )

    out = route.provability_payload_fields(
        [
            {"category": "soccer", "n": 98_381, "mce": 3.54},
            {"category": "baseball", "n": 192_090, "mce": 1.94},
        ]
    )
    by_cat = {c["category"]: c for c in out["by_category"]}
    assert by_cat["soccer"]["provability"] == "not_provable_selection_biased"
    assert by_cat["baseball"]["provability"] == "provable"
    assert out["provability_census"]["measured"] is True


def test_an_incomplete_census_leaves_the_page_exactly_as_it_was(monkeypatch):
    """The one-directional failure, at the route boundary: a short denominator
    must not quietly un-protect the page."""
    import json as _json

    from app.routes import calibration as route

    payload = _complete({"soccer": {"total_outcomes": 10, "graded_outcomes": 9}})
    payload["usable_as_denominator"] = False

    class _RC:
        def get(self, key):
            return _json.dumps(payload)

    monkeypatch.setattr(route, "PROVABILITY_CENSUS", {})
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda *a, **k: _RC())

    out = route.provability_payload_fields([{"category": "soccer", "n": 98_381}])
    assert out["provability_census"]["measured"] is False
    assert "provability" not in out["by_category"][0]


def test_a_census_read_failure_degrades_to_unmeasured_not_to_a_500(monkeypatch):
    from app.routes import calibration as route

    def boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(route, "PROVABILITY_CENSUS", {})
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", boom)
    assert route.load_provability_census() == {}
