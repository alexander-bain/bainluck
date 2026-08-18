"""#1982 — the Discover rank trace must report the SERVED disposition.

`GET /api/admin/discover-quality/trace/{market_id}` is, by its own code comment,
"the explainability substrate all later RANK eval work reads". It was reading a
different feed than the one production serves:

* `rank_phases.returned` / `returned_rank` came from a PARTIAL re-implementation
  of the display chain — no noise filter, no category-mix balance, **no bundles,
  no lead composition**. Measured on the #1982 specimen (market 59150635, "Will
  Meta (META) close above $540"): the probe said 17, production served 16 — the
  exact offset of the bundle/lead prefix the probe omits. At the time of filing
  it said `returned: false`, rank 76/77, for the same card on the first screen.

* `final_ranking.final_futures_rank` was `rank_phases["raw_futures_rank"]` — the
  card's index in the **unsorted** raw candidate pool. `_score_futures` returns
  candidate-pool order and never sorts, so that number was never a rank. It read
  81 of 81 for a card at position 16, and `_suggest_trace_fix` branches on it at
  `> 50`, so the instrument's recommendation was computed from it too.

An instrument that is confidently wrong is worse than a missing one: it sends
every investigation that reads it after a phantom, which is exactly what it did
to the #1958 diagnosis in PROGRAM UX cycle 95.

These tests pin both halves of the fix — the disposition comes from the SHARED
chain, and the raw-pool position is no longer exported as a rank.
"""

import ast
import inspect

import pytest

import app.routes.feed as feed_module
from app.routes.feed import (
    PersonalizationContext,
    _discover_rank_phase_trace,
    apply_discover_display_chain,
)


def _mover(market_id: int, score: float, *, swing: float = 0.30) -> dict:
    """A futures card that qualifies for the "biggest swings" bundle.

    Two of these FOLD into one bundle card in the served chain and stay two
    separate cards in the partial probe — which is what makes the two builds
    disagree by a knowable amount.
    """
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"mover {market_id}",
        "data": {
            "id": market_id,
            "name": f"Will thing {market_id} happen?",
            "status": "open",
            "llm_sport_category": "politics",
            "top_outcomes": [
                {
                    "name": "Yes",
                    "probability": 0.45,
                    "probability_change_24h": swing,
                }
            ],
        },
    }


def _plain(market_id: int, score: float, category: str = "economics") -> dict:
    """A futures card that qualifies for no bundle — it just holds a position."""
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"plain {market_id}",
        "data": {
            "id": market_id,
            "name": f"Will other thing {market_id} happen?",
            "status": "open",
            "llm_sport_category": category,
            "top_outcomes": [{"name": "Yes", "probability": 0.40}],
        },
    }


# The target sits BELOW two movers, so folding the movers into one bundle shifts
# it up by exactly one in the served build relative to the partial probe.
TARGET_ID = 59150635


def _specimen_pool() -> list[dict]:
    return [
        _mover(9001, 95.0),
        _mover(9002, 94.0),
        _plain(9003, 93.0),
        _plain(TARGET_ID, 92.0, category="finance"),
        _plain(9005, 91.0),
        _plain(9006, 90.0),
    ]


async def _run_trace(
    monkeypatch, pool: list[dict], *, market_id: int = TARGET_ID, limit: int = 20
):
    """Run the trace over a fixed pool, with no database and no Redis.

    Awaited by the caller rather than driven with `run_until_complete`: the
    suite runs under pytest-asyncio auto mode, and grabbing the ambient loop
    here passed in isolation and failed the moment another async test had
    already run in the same session.
    """

    async def _fake_score_futures(db, now, sport_filter=None, ctx=None, my_teams_only=False, **kw):
        # Return copies: the display chain mutates item dicts in place, and the
        # trace runs two builds over the same pool.
        import copy

        return copy.deepcopy(pool)

    monkeypatch.setattr(feed_module, "_score_futures", _fake_score_futures)

    from datetime import datetime, timezone

    return await _discover_rank_phase_trace(
        None,
        datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc),
        market_id,
        include_events=False,
        event_pct=0.15,
        limit=limit,
    )


def _served_rank(pool: list[dict], market_id: int, *, limit: int = 20) -> int | None:
    """The ORACLE: what the page actually does.

    Deliberately `apply_discover_display_chain` — the same function `get_feed`
    calls. The claim under test is "the trace reports the served build", so the
    served build is the correct oracle, not an independent reimplementation.
    """
    import copy

    items, _meta = apply_discover_display_chain(
        copy.deepcopy(pool),
        limit=limit,
        ctx=PersonalizationContext(),
        event_pct=0.15,
        include_events=False,
        my_teams_only=False,
    )
    for idx, item in enumerate(items[:limit], start=1):
        if (item.get("data") or {}).get("id") == market_id:
            return idx
    return None


class TestTheSpecimenActuallyDiverges:
    """If the two builds agreed on this pool, every test below would pass
    vacuously — a fixture that cannot expose the bug proves nothing."""

    async def test_the_partial_probe_and_the_served_build_disagree_here(self, monkeypatch):
        trace = await _run_trace(monkeypatch, _specimen_pool())
        assert trace["probe_returned_rank"] is not None
        assert trace["returned_rank"] is not None
        assert trace["probe_returned_rank"] != trace["returned_rank"], (
            "the fixture no longer distinguishes the partial probe from the "
            "served chain, so it cannot catch #1982 regressing"
        )


class TestReturnedDisposition:
    async def test_returned_rank_matches_the_served_page(self, monkeypatch):
        pool = _specimen_pool()
        trace = await _run_trace(monkeypatch, pool)
        assert trace["returned"] is True
        assert trace["returned_rank"] == _served_rank(pool, TARGET_ID)

    async def test_it_is_the_served_rank_and_not_the_probe_rank(self, monkeypatch):
        pool = _specimen_pool()
        trace = await _run_trace(monkeypatch, pool)
        assert trace["returned_rank"] != trace["probe_returned_rank"]
        assert trace["returned_rank"] == _served_rank(pool, TARGET_ID)

    async def test_final_futures_rank_is_a_rank_not_a_raw_pool_index(self, monkeypatch):
        pool = _specimen_pool()
        trace = await _run_trace(monkeypatch, pool)
        # The regression: `final_futures_rank` used to BE `raw_futures_rank`.
        # Build the pool so the raw index and the served rank differ, then pin
        # that the exported "final" rank tracks the page.
        assert trace["raw_futures_rank"] == 4, "fixture: target is 4th in pool order"
        assert trace["returned_rank"] == _served_rank(pool, TARGET_ID)
        assert trace["returned_rank"] != trace["raw_futures_rank"]

    async def test_the_served_score_is_reported(self, monkeypatch):
        trace = await _run_trace(monkeypatch, _specimen_pool())
        assert trace["served_item_score"] == 92.0


class TestDroppedDisposition:
    async def test_a_card_absent_from_the_page_reports_not_returned(self, monkeypatch):
        # limit=1 with the target 4th: the page cannot contain it.
        pool = _specimen_pool()
        trace = await _run_trace(monkeypatch, pool, limit=1)
        assert trace["returned"] is False
        assert trace["returned_rank"] is None
        assert _served_rank(pool, TARGET_ID, limit=1) is None

    async def test_a_dropped_card_still_reports_where_it_landed_in_the_assembly(
        self, monkeypatch
    ):
        # "not on the page" and "not in the build at all" are different facts
        # (gotcha #53). A dropped card keeps an assembled rank.
        trace = await _run_trace(monkeypatch, _specimen_pool(), limit=1)
        assert trace["assembled_rank"] is not None and trace["assembled_rank"] > 1

    async def test_a_market_that_is_not_in_the_pool_at_all_is_distinguishable(
        self, monkeypatch
    ):
        trace = await _run_trace(monkeypatch, _specimen_pool(), market_id=424242)
        assert trace["returned"] is False
        assert trace["returned_rank"] is None
        assert trace["assembled_rank"] is None
        assert trace["raw_futures_rank"] is None


class TestStructure:
    """The behavioural tests above pass if someone reimplements the chain a
    fourth time and happens to get the same answer on this pool. These do not."""

    def _called_names(self, fn) -> set[str]:
        tree = ast.parse(inspect.getsource(fn))
        out: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    out.add(f.id)
                elif isinstance(f, ast.Attribute):
                    out.add(f.attr)
        return out

    def test_the_trace_derives_its_disposition_from_the_shared_chain(self):
        called = self._called_names(feed_module._discover_rank_phase_trace)
        assert "apply_discover_display_chain" in called, (
            "the trace's returned/rank verdict must come from the same function "
            "get_feed calls — a per-phase probe is not a page (#1982)"
        )

    def test_the_trace_runs_the_same_pre_chain_preparation_get_feed_does(self):
        called = self._called_names(feed_module._discover_rank_phase_trace)
        assert "_suppress_zero_probability_cards" in called, (
            "get_feed drops all-0%/empty cards BEFORE the chain; a trace that "
            "skips it assembles a page with cards the server would have dropped"
        )

    def test_final_futures_rank_is_no_longer_wired_to_the_raw_pool_index(self):
        source = inspect.getsource(feed_module.build_discover_market_trace)
        assert '"final_futures_rank": rank_phases["raw_futures_rank"]' not in source, (
            "final_futures_rank must not be the unsorted raw-pool index again"
        )
        assert '"final_futures_rank": rank_phases["returned_rank"]' in source

    def test_the_raw_pool_index_is_still_reported_under_an_honest_name(self):
        source = inspect.getsource(feed_module.build_discover_market_trace)
        assert '"raw_pool_position": rank_phases["raw_futures_rank"]' in source, (
            "which pool found the card is useful — it just is not a rank"
        )


class TestItDeclaresWhatItCannotModel:
    """#1982 acceptance, verbatim: 'If the trace cannot model serve-time
    blending, it says so IN THE RESPONSE, rather than emitting a confident wrong
    returned verdict.'"""

    def test_the_declaration_exists_and_is_not_empty(self):
        source = inspect.getsource(feed_module.build_discover_market_trace)
        assert '"unmodeled_serve_time_terms"' in source

    @pytest.mark.parametrize(
        "term",
        ["personalization", "manual review decisions", "response cache"],
    )
    def test_it_names_the_terms_that_actually_differ(self, term):
        source = inspect.getsource(feed_module.build_discover_market_trace)
        assert term in source, (
            f"the trace does not disclose that it skips {term!r}; an undisclosed "
            "gap is how a wrong verdict reads as an authoritative one"
        )
