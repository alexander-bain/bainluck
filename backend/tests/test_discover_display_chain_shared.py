"""#1923 — the Discover display chain is ONE function, and the ratification
instrument runs it.

The blend-ratification endpoint (`/api/admin/interestingness-side-by-side`)
scored with the feed's own scorer and then stopped at the sort. `get_feed` runs
eleven more stages after that sort, and interleaves an events pool the endpoint
did not build. So `positions_changed` was computed over a list nobody is served
in that order — it could support "this weight is not inert" and could not
support "this weight is worth N", which is the distinction Alex's blend re-rule
(#1815) turns on.

The fix that matters is not the new mode. It is that there is now exactly one
display chain and both callers call it. These tests pin that, because the
failure they prevent is silent: a drifted ratification artifact carries Alex's
authority while describing a page Discover does not build (#257's shared-payload
lesson, one layer up).
"""

import ast
import inspect

import pytest

import app.routes.admin_feed_config as cfg_module
import app.routes.feed as feed_module
from app.routes.feed import PersonalizationContext, apply_discover_display_chain

# Every stage that lives INSIDE the chain. If one of these names appears in a
# caller's own body, that caller has started keeping its own copy.
_CHAIN_STAGES = (
    "_demote_non_exceptional_discover_events",
    "_filter_discover_event_noise",
    "balance_discover_event_category_mix",
    "_ensure_feed_diversity",
    "diversify_discover_first_page",
    "backfill_discover_editorial_tail",
    "assemble_discover_comparison_bundles",
    "assemble_geopolitics_theme_bundles",
    "assemble_awards_theme_bundles",
    "assemble_swings_theme_bundles",
    "compose_lead",
)


def _called_names(fn) -> set[str]:
    """Names this function's own body calls (not names it merely mentions)."""
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


class TestThereIsOnlyOneDisplayChain:
    def test_get_feed_delegates_instead_of_inlining_the_chain(self):
        called = _called_names(feed_module.get_feed)
        assert "apply_discover_display_chain" in called, (
            "get_feed must call the shared chain, not inline it"
        )
        leaked = sorted({s for s in _CHAIN_STAGES if s in called})
        assert not leaked, (
            f"get_feed still calls display-chain stages directly: {leaked}. "
            "Two copies of this chain is the defect #1923 exists to remove."
        )

    def test_the_admin_instrument_calls_the_shared_chain_not_a_second_copy(self):
        called = _called_names(cfg_module.interestingness_side_by_side)
        assert "apply_discover_display_chain" in called, (
            "stage=served must run the SAME function get_feed runs"
        )
        leaked = sorted({s for s in _CHAIN_STAGES if s in called})
        assert not leaked, (
            f"the ratification instrument re-implements chain stages {leaked}. "
            "A drifted artifact is worse than no artifact — it would carry "
            "Alex's authority while describing a page Discover does not build."
        )

    def test_the_chain_still_contains_every_stage_it_is_supposed_to(self):
        # The mirror of the two tests above: extraction must not have QUIETLY
        # dropped a stage. A missing stage would make both callers agree — on
        # the wrong page.
        called = _called_names(apply_discover_display_chain)
        missing = sorted({s for s in _CHAIN_STAGES if s not in called})
        assert not missing, f"the display chain lost stages during extraction: {missing}"

    def test_the_chain_does_no_io(self):
        # It is called from an admin route per weight and from the hot feed
        # path. An await in here would make the "pure reordering" claim false
        # and would put a DB round-trip inside a loop.
        assert not inspect.iscoroutinefunction(apply_discover_display_chain)
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Await, ast.AsyncFor))]


def _futures(i: int, score: float, category: str = "politics") -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "data": {
            "id": i,
            "name": f"market {i}",
            "llm_sport_category": category,
            "outcomes": [{"name": "Yes", "probability": 0.5}],
        },
    }


def _event(i: int, score: float) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"e{i}",
        "data": {
            "id": i,
            "status": "live",
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "home_team_data": {"logo": "x"},
            "away_team_data": {"logo": "y"},
        },
    }


class TestChainContract:
    def test_reviewed_count_is_none_when_not_requested_not_zero(self):
        # `0` would read as "filtering ran and matched nothing", which is a
        # different fact from "filtering was never asked for" (gotcha #53).
        _items, meta = apply_discover_display_chain(
            [_futures(1, 90.0)],
            limit=10,
            ctx=PersonalizationContext(),
            event_pct=0.15,
        )
        assert meta["reviewed_filtered_count"] is None

    def test_reviewed_count_is_zero_when_requested_and_nothing_matched(self):
        _items, meta = apply_discover_display_chain(
            [_futures(1, 90.0)],
            limit=10,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            reviewed_keys=set(),
        )
        assert meta["reviewed_filtered_count"] == 0

    def test_the_callers_list_is_not_reordered_underneath_them(self):
        # The admin instrument reuses one events pool across weights. If the
        # chain sorted the caller's list in place, weight 2 would start from
        # weight 1's ordering and the comparison would be against a moving base.
        original = [_futures(1, 10.0), _futures(2, 90.0)]
        snapshot = [id(x) for x in original]
        apply_discover_display_chain(
            original, limit=10, ctx=PersonalizationContext(), event_pct=0.15
        )
        assert [id(x) for x in original] == snapshot

    def test_my_teams_only_skips_the_quota_stages_but_not_the_demotion(self):
        # This pins `get_feed`'s ACTUAL shape, which is not the shape you would
        # guess: `my_teams_only` gates `_ensure_feed_diversity`, the first-page
        # re-pick, the bundles and the lead — but the Discover event demotion is
        # gated on `event_pct < 0.3` ALONE. Extraction preserved that exactly.
        #
        # It is unreachable in production (a My Stuff request never carries a
        # Discover `event_pct`), which is precisely why it must be pinned rather
        # than tidied: an extraction is the wrong moment to change behaviour,
        # and an untested asymmetry is how the next reader "fixes" it by
        # accident. #1091 is the standing lesson about editing a feed gate.
        items = [_event(1, 95.0), _futures(2, 60.0)]
        out, _meta = apply_discover_display_chain(
            items,
            limit=10,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            my_teams_only=True,
        )
        assert len(out) == 2, "My Stuff must show everything matching"
        assert next(i for i in out if i["type"] == "event")["score"] == 35

    def test_discover_mode_demotes_a_routine_event(self):
        items = [_event(1, 95.0), _futures(2, 60.0)]
        out, _meta = apply_discover_display_chain(
            items, limit=10, ctx=PersonalizationContext(), event_pct=0.15
        )
        ev = next(i for i in out if i["type"] == "event")
        assert ev["score"] == 35 and ev["_rank_score"] == 35.0, (
            "the Discover demotion did not survive extraction"
        )
        # NOT an ordering assertion. `compose_lead` legitimately hoists a live
        # game to the front afterwards (the tonight's-games prefix), so a
        # demoted event can still lead the page — asserting otherwise would
        # pin a bug into the suite.
        assert {i["type"] for i in out} == {"event", "futures"}

    def test_timing_callback_fires_for_every_recorded_stage(self):
        seen = []
        apply_discover_display_chain(
            [_futures(1, 90.0)],
            limit=10,
            ctx=PersonalizationContext(),
            event_pct=0.15,
            timing_cb=seen.append,
        )
        assert seen == ["ranking", "reviewed_filter", "bundles", "lead_composition"], (
            "get_feed's per-stage timings are built from these callbacks; "
            f"got {seen}"
        )


class TestServedModeIsBounded:
    """`served` is a full Discover build per weight. It refuses rather than
    silently truncating — a bound that clips the request produces an artifact
    whose caption disagrees with its body."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "weights,limit",
        [("0,0.1,0.2", 20), ("0,0.2", 25), ("0,0.1,0.2,0.3", 25)],
    )
    async def test_refuses_an_unbounded_served_request(
        self, monkeypatch, weights, limit
    ):
        from fastapi import HTTPException

        monkeypatch.setattr(cfg_module, "_check_admin_secret", lambda *a, **k: True)
        with pytest.raises(HTTPException) as exc:
            await cfg_module.interestingness_side_by_side(
                request=None,
                secret=None,
                weights=weights,
                limit=limit,
                stage="served",
                db=None,
            )
        assert exc.value.status_code == 400
        assert "served" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_rejects_an_unknown_stage(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(cfg_module, "_check_admin_secret", lambda *a, **k: True)
        with pytest.raises(HTTPException) as exc:
            await cfg_module.interestingness_side_by_side(
                request=None,
                secret=None,
                weights="0,0.2",
                limit=10,
                stage="interleaved",
                db=None,
            )
        assert exc.value.status_code == 400

    def test_ranked_is_still_the_default(self):
        # ruling 069: a changed default silently re-bases every prior
        # comparison. Every artifact produced before #1923 must stay readable.
        sig = inspect.signature(cfg_module.interestingness_side_by_side)
        assert sig.parameters["stage"].default.default == "ranked"


class TestAbsorbedAndAmplified:
    """The two numbers the mode exists to produce.

    Tested against a stubbed chain, deliberately: the classifier is the new
    logic, and pinning it to the real chain's output would make these tests a
    fixture of today's quota settings rather than of the classification.
    """

    async def _run(self, monkeypatch, chain_impl):
        async def _score_futures(db, now, **kw):
            w = (kw.get("config") or {}).get(
                "interestingness_blend_weight_override", 0.0
            )
            # At weight 0 the order is 1,2,3. At any other weight, 2 and 1 swap.
            return (
                [_futures(1, 90.0), _futures(2, 80.0), _futures(3, 70.0)]
                if w == 0
                else [_futures(2, 95.0), _futures(1, 90.0), _futures(3, 70.0)]
            )

        async def _empty(*a, **k):
            return []

        async def _noop(*a, **k):
            return None

        monkeypatch.setattr(cfg_module, "_check_admin_secret", lambda *a, **k: True)
        monkeypatch.setattr(feed_module, "_score_futures", _score_futures)
        monkeypatch.setattr(feed_module, "_score_events", _empty)
        monkeypatch.setattr(feed_module, "_score_golf_tournaments", _empty)
        monkeypatch.setattr(feed_module, "_score_event_concepts", _empty)
        monkeypatch.setattr(feed_module, "enrich_event_team_data", _noop)
        monkeypatch.setattr(
            feed_module, "_dedupe_futures_by_canonical", lambda rows: rows
        )
        monkeypatch.setattr(
            feed_module, "_suppress_zero_probability_cards", lambda rows: (rows, 0)
        )
        monkeypatch.setattr(feed_module, "apply_discover_display_chain", chain_impl)
        return await cfg_module.interestingness_side_by_side(
            request=None,
            secret=None,
            weights="0,0.2",
            limit=5,
            stage="served",
            db=None,
        )

    @pytest.mark.asyncio
    async def test_a_swap_the_page_undoes_is_reported_as_absorbed(self, monkeypatch):
        # The chain re-imposes a fixed order — exactly what a per-category quota
        # does to two cards in the same group. The ranking delta is real and the
        # served page is byte-identical.
        def chain(items, **kw):
            return sorted(items, key=lambda i: i["data"]["id"]), {}

        out = await self._run(monkeypatch, chain)
        eff = out["interleave_effect"]["0.2"]
        assert eff["absorbed"] >= 2, out["interleave_effect"]
        assert eff["amplified"] == 0
        assert eff["registered_expectation_absorbed_gt_0"] is True
        # And the pre-interleave view still reports the movement, so the two
        # readings are visibly different rather than one overwriting the other.
        assert out["comparison"]["0.2"]["positions_changed"] >= 2
        assert out["served_comparison"]["0.2"]["identical"] is True

    @pytest.mark.asyncio
    async def test_a_card_the_page_moves_on_its_own_is_reported_as_amplified(
        self, monkeypatch
    ):
        # Card 3 never moves pre-interleave. The chain evicts it at one weight
        # and not the other — a second-order effect of some other card crossing
        # a boundary. `positions_changed` cannot see this at all.
        def chain(items, **kw):
            ids = [i["data"]["id"] for i in items]
            if ids[0] == 2:  # the weighted arm
                return [i for i in items if i["data"]["id"] != 3], {}
            return list(items), {}

        out = await self._run(monkeypatch, chain)
        eff = out["interleave_effect"]["0.2"]
        assert eff["amplified"] >= 1, out["interleave_effect"]
        assert any(c["card_key"] == "futures:3" for c in eff["amplified_cards"])

    @pytest.mark.asyncio
    async def test_the_events_pool_is_reported_not_assumed(self, monkeypatch):
        def chain(items, **kw):
            return list(items), {}

        out = await self._run(monkeypatch, chain)
        assert out["events_pool"]["events_scored_once"] is True
        assert out["events_pool"]["deep_copied_per_weight"] is True
        assert out["stage"] == "served"
        assert set(out["build_ms"]) == {"0.0", "0.2"}

    @pytest.mark.asyncio
    async def test_ranked_mode_gains_no_served_keys(self, monkeypatch):
        # An existing consumer of `ranked` must not have to learn new fields.
        def chain(items, **kw):  # pragma: no cover - must never be reached
            raise AssertionError("stage=ranked must not run the display chain")

        async def _score_futures(db, now, **kw):
            return [_futures(1, 90.0), _futures(2, 80.0)]

        monkeypatch.setattr(cfg_module, "_check_admin_secret", lambda *a, **k: True)
        monkeypatch.setattr(feed_module, "_score_futures", _score_futures)
        monkeypatch.setattr(
            feed_module, "_dedupe_futures_by_canonical", lambda rows: rows
        )
        monkeypatch.setattr(feed_module, "apply_discover_display_chain", chain)
        out = await cfg_module.interestingness_side_by_side(
            request=None,
            secret=None,
            weights="0,0.2",
            limit=5,
            stage="ranked",
            db=None,
        )
        assert out["stage"] == "ranked"
        for k in ("served_slates", "served_comparison", "interleave_effect", "events_pool"):
            assert k not in out
