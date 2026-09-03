"""#2709 (Alex P1) — the SPORTS display chain puts live games on the first page.

This is the red arm for the ship. `test_live_first_page.py` grades the rule;
this file grades the WIRING, which is the half that was actually broken — the
rule's Discover twin (`lead_with_tonights_games`) has existed since
2026-08-08 and `compose_lead` is invoked as
`compose_lead(items, include_tonights_games=discover_mode)`, so the sports
surface never reached it.

Asserting on the chain's OUTPUT rather than on a call is deliberate.
`get_feed` serves `feed_items[offset : offset + limit]`, a pure prefix of this
list, so the first twenty items of what this returns ARE the first page a reader
is sent — there is no transform in between for a defect to hide in
(ux/1006's lesson #3).

RED ARM: delete the `if not discover_mode:` block in
`apply_discover_display_chain` and keep the import. Reverting the import too
gives a collection error, which grades as "the harness never ran", not as red.
"""

from __future__ import annotations

import ast
import inspect

from app.routes.feed import PersonalizationContext, apply_discover_display_chain

# Sports mode, spelled the way `discover_mode` reads it: an events-led page.
SPORTS = {"event_pct": 0.6, "include_events": True, "my_teams_only": False}
DISCOVER = {"event_pct": 0.15, "include_events": True, "my_teams_only": False}


def _game(i: int, score: float, status: str, prob: float = 0.56) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"e{i}",
        "data": {
            "id": i,
            "status": status,
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "home_team_data": {"logo": "x"},
            "away_team_data": {"logo": "y"},
            "current_odds": {"home_probability": prob, "away_probability": 1 - prob},
        },
    }


def _reported_pool() -> list[dict]:
    """The shape of the reported defect, at the scores production actually had.

    Measured on the served payload of 2026-09-03: finished MLB games score 98,
    live US Open matches score 95. So completed beats live on every comparison
    and the live rows sink below the twenty-item window — not by a tuning
    accident but deterministically, which is why "raise the live score" is not
    the fix and a magnitude test would not have caught it.
    """
    finished = [_game(100 + i, 98.0, "completed") for i in range(24)]
    live = [_game(200 + i, 95.0, "live") for i in range(6)]
    return finished + live


def _live_slots(items: list[dict], limit: int = 20) -> list[int]:
    return [
        i + 1
        for i, it in enumerate(items[:limit])
        if (it.get("data") or {}).get("status") == "live"
    ]


class TestSportsFirstPage:
    def test_the_pool_really_does_bury_every_live_game(self):
        """The precondition, asserted rather than assumed.

        If a future scoring change lifts live above completed on its own, this
        goes red and tells the next reader the ship's premise has moved —
        instead of the ship silently becoming a no-op with everything green.
        """
        pool = _reported_pool()
        pool.sort(key=lambda it: it["_rank_score"], reverse=True)
        assert _live_slots(pool) == [], "the fixture cannot express the defect"

    def test_live_games_reach_the_first_page_on_sports(self):
        out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert len(_live_slots(out)) == 6, (
            "every live game must be on the first page — Alex's acceptance "
            "criterion is rail count == live count"
        )
        assert meta["live_first_page"]["hoisted"] > 0
        assert meta["live_first_page"]["unhoisted"] == 0

    def test_the_first_page_still_holds_the_rest_of_the_surface(self):
        """The cap is load-bearing: half the page is still everything else."""
        out, _ = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        finished = [
            it for it in out[:20] if (it.get("data") or {}).get("status") == "completed"
        ]
        assert len(finished) >= 10, "a live slate must not evict the whole page"

    def test_nothing_is_dropped_by_the_sports_chain(self):
        pool = _reported_pool()
        out, _ = apply_discover_display_chain(
            pool, limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert {it["data"]["id"] for it in out} == {it["data"]["id"] for it in pool}


class TestDiscoverIsUnchanged:
    def test_CONTROL_discover_does_not_invoke_the_sports_pass(self):
        """Discover's lead is `compose_lead`'s job and stays that way. This ship
        ANSWERS the `include_tonights_games=discover_mode` gate rather than
        deleting it, so Discover must report no live-first-page pass at all."""
        _out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **DISCOVER
        )
        assert meta["live_first_page"] is None, (
            "None means the pass never ran; 0 would mean it ran and did nothing"
        )

    def test_CONTROL_the_quality_floor_is_still_discover_only(self):
        _out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert meta["first_page_quality_floor"] is None


class TestChainContract:
    def test_CONTROL_the_chain_still_does_no_io(self):
        """The pass must not have put a round trip in the hot feed path."""
        assert not inspect.iscoroutinefunction(apply_discover_display_chain)
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        assert not [
            n for n in ast.walk(tree) if isinstance(n, (ast.Await, ast.AsyncFor))
        ]

    def test_CONTROL_the_callers_list_is_not_reordered_underneath_them(self):
        original = _reported_pool()
        snapshot = [id(x) for x in original]
        apply_discover_display_chain(
            original, limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert [id(x) for x in original] == snapshot
