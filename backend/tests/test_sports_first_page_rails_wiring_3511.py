"""#3511 — the SPORTS display chain caps a repeated finished rail. Wiring arm.

`test_sports_first_page_rails_3511.py` grades the rule; this grades the WIRING,
which is the half that was broken. `diversify_discover_first_page` has capped
repeated archetypes at 3 since #850, but it is invoked under `if discover_mode:`
— so the one surface whose cards are ALL `sports_story`, and therefore all one
archetype, is the one surface it never reaches.

Asserting on the chain's OUTPUT rather than on a call, for the reason
`test_feed_live_first_page_wiring_2709.py` gives: `get_feed` serves
`feed_items[offset : offset + limit]`, a pure prefix, so the first twenty items
of what this returns ARE the first page a reader is sent.

RED ARM — run, not asserted. The `if not discover_mode:` block that calls
`cap_repeated_finished_rails` was DELETED from `apply_discover_display_chain`
(leaving `finished_rail_cap_meta = None` and the import in place; reverting the
import too gives a collection error, which grades as "the harness never ran",
not as red). **6 failed, 9 passed:**

    test_the_sports_chain_runs_a_rail_cap_at_all ..................... FAILED
    test_one_rail_cannot_take_the_sports_first_page .................. FAILED
    test_the_chain_reports_what_it_swapped ........................... FAILED
    test_every_rail_is_capped_not_just_the_worst_offender ............ FAILED
    test_both_passes_fire_when_the_live_games_are_out_of_the_caps_reach FAILED
    test_the_rail_cap_runs_BEFORE_the_live_hoist ..................... FAILED

Both #2709 controls — `test_every_buried_live_game_reaches_the_first_page_deep`
and `..._shallow` — stayed GREEN under the deletion, which is the point of
having them: they prove the live-first-page guarantee is the hoist's and does
not quietly depend on this ship.

A weaker red arm was tried first and is recorded because it is a trap for the
next reader: neutering the block to `if False:` leaves the call in the source,
so `test_the_rail_cap_runs_BEFORE_the_live_hoist` — which reads the AST — stayed
green and only 5 of the 6 fired. A guard that reads source needs the source
actually removed.
"""

from __future__ import annotations

import ast
import inspect

from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils.sports_first_page_rails import (
    FINISHED_RAIL_FIRST_PAGE_CAP,
    finished_rail_key,
)

SPORTS = {"event_pct": 0.6, "include_events": True, "my_teams_only": False}
DISCOVER = {"event_pct": 0.15, "include_events": True, "my_teams_only": False}


def _finished(i: int, score: float, headline: str) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": headline,
        "data": {
            "id": i,
            "status": "completed",
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "home_score": 2,
            "away_score": 1,
            "current_odds": {"home_probability": 0.33, "away_probability": 0.67},
        },
    }


def _live(i: int, score: float) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": "Live",
        "data": {
            "id": i,
            "status": "live",
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "current_odds": {"home_probability": 0.5, "away_probability": 0.5},
        },
    }


def _market(i: int, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"Leads at {i}%",
        "data": {"id": 9000 + i, "name": f"Market {i}", "top_outcomes": []},
    }


def _reported_pool() -> list[dict]:
    """The 2026-09-07 04:40Z shape: nine same-rail results outranking everything.

    Finished upsets score high (the upset bonus is +20) and the overnight slate
    scored under the `min_score` gate, so the repeats are at the TOP of the pool
    by rank — which is why "let scores decide" cannot fix this and a reorder is
    the whole intervention.
    """
    upsets = [_finished(100 + i, 98.0 - i, "Recent upset") for i in range(9)]
    line_moves = [_finished(200 + i, 80.0 - i, "Line moving") for i in range(4)]
    markets = [_market(i, 60.0 - i) for i in range(20)]
    return upsets + line_moves + markets


def _live_on_page(items: list[dict], limit: int = 20) -> list[dict]:
    return [
        it for it in items[:limit] if (it.get("data") or {}).get("status") == "live"
    ]


def _rail_counts(items: list[dict], limit: int = 20) -> dict:
    counts: dict[str, int] = {}
    for it in items[:limit]:
        rail = finished_rail_key(it)
        if rail:
            counts[rail] = counts.get(rail, 0) + 1
    return counts


class TestSportsFirstPage:
    def test_the_pool_really_does_repeat_one_rail_nine_times(self):
        """The precondition, asserted rather than assumed — if scoring later
        stops floating nine same-rail results to the top, this goes red and
        tells the next reader the ship's premise moved, instead of the ship
        silently becoming a no-op with everything green."""
        pool = _reported_pool()
        pool.sort(key=lambda it: it["_rank_score"], reverse=True)
        assert _rail_counts(pool).get("Recent upset") == 9

    def test_the_sports_chain_runs_a_rail_cap_at_all(self):
        """Separate from the count on purpose. "The pass never ran" and "the
        pass ran and chose badly" are different defects and one assertion would
        report them identically."""
        _out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert (
            meta["finished_rail_cap"] is not None
        ), "sports mode never invoked the pass — this is the reported defect"

    def test_one_rail_cannot_take_the_sports_first_page(self):
        out, _meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert _rail_counts(out).get("Recent upset") == FINISHED_RAIL_FIRST_PAGE_CAP

    def test_the_chain_reports_what_it_swapped(self):
        """Seven, not six: the pool's four "Line moving" results are a rail too,
        and the cap is per-rail, not a special case for the loudest one."""
        _out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert meta["finished_rail_cap"]["swapped"] == 7
        assert meta["finished_rail_cap"]["unswapped"] == 0

    def test_every_rail_is_capped_not_just_the_worst_offender(self):
        out, _ = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert _rail_counts(out) == {"Recent upset": 3, "Line moving": 3}

    def test_the_page_still_shows_results(self):
        """#1091. The fix for nine copies of one result is not zero results."""
        out, _ = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert sum(_rail_counts(out).values()) >= 4

    def test_nothing_is_dropped_by_the_sports_chain(self):
        pool = _reported_pool()
        out, _ = apply_discover_display_chain(
            pool, limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert {(it["type"], it["data"]["id"]) for it in out} == {
            (it["type"], it["data"]["id"]) for it in pool
        }


class TestTheLiveHoistStillHasTheLastWord:
    """#2709 is Alex's P1 and this ship must not cost it a slot.

    The two passes touch the same twenty slots, so "they compose" is a claim
    that needs a control, not a comment. A live game buried under a wall of
    same-rail results is the case where both fire.
    """

    def _deep_live_pool(self) -> list[dict]:
        """Live games buried BELOW a market tail deeper than the cap's surplus.

        Sized on purpose. The cap has 15 slots of surplus and takes replacements
        in served order, so a 20-market tail absorbs all of them and the live
        rows are still beyond the window when the cap is done — which is the
        only arrangement where the hoist has anything left to do.
        """
        upsets = [_finished(100 + i, 98.0 - i, "Recent upset") for i in range(18)]
        markets = [_market(i, 60.0 - i) for i in range(20)]
        buried_live = [_live(300 + i, 30.0 - i) for i in range(4)]
        return upsets + markets + buried_live

    def _shallow_live_pool(self) -> list[dict]:
        """Live games inside the tail the cap itself reaches."""
        upsets = [_finished(100 + i, 98.0 - i, "Recent upset") for i in range(18)]
        markets = [_market(i, 60.0 - i) for i in range(10)]
        buried_live = [_live(300 + i, 50.0 - i) for i in range(4)]
        return upsets + markets + buried_live

    def test_both_passes_fire_when_the_live_games_are_out_of_the_caps_reach(self):
        _out, meta = apply_discover_display_chain(
            self._deep_live_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert meta["finished_rail_cap"]["swapped"] > 0
        assert (
            meta["live_first_page"]["hoisted"] > 0
        ), "the hoist must still fire after the cap has reordered the window"

    def test_every_buried_live_game_reaches_the_first_page_deep(self):
        out, meta = apply_discover_display_chain(
            self._deep_live_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert (
            len(_live_on_page(out)) == 4
        ), "the rail cap must not spend a slot the hoist needs — #2709 is P1"
        assert meta["live_first_page"]["unhoisted"] == 0

    def test_every_buried_live_game_reaches_the_first_page_shallow(self):
        """The cap's replacement walk can promote a live game itself, which is
        strictly good and must not read as the hoist having failed: what the
        surface owes the reader is the live game ON the page, not a particular
        pass taking credit for it."""
        out, meta = apply_discover_display_chain(
            self._shallow_live_pool(), limit=20, ctx=PersonalizationContext(), **SPORTS
        )
        assert len(_live_on_page(out)) == 4
        assert meta["live_first_page"]["live_in_window_after"] == 4
        assert meta["live_first_page"]["unhoisted"] == 0

    def test_the_rail_cap_runs_BEFORE_the_live_hoist(self):
        """Order is the contract, and a comment claiming it is not a control.

        The hoist displaces the WORST window slots for live games, so running it
        last can only improve on what the cap leaves; running it first would let
        the cap trade a hoisted live game back out.
        """
        src = inspect.getsource(apply_discover_display_chain)
        tree = ast.parse(src)
        calls = [
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id
            in ("cap_repeated_finished_rails", "hoist_live_events_into_first_page")
        ]
        assert calls == [
            "cap_repeated_finished_rails",
            "hoist_live_events_into_first_page",
        ], f"call order changed: {calls}"


class TestDiscoverIsUnchanged:
    def test_CONTROL_discover_does_not_invoke_the_sports_pass(self):
        """Discover already has `diversify_discover_first_page`. This ship
        ANSWERS the gate that kept it Discover-only rather than deleting it, so
        Discover must report no rail-cap pass at all."""
        _out, meta = apply_discover_display_chain(
            _reported_pool(), limit=20, ctx=PersonalizationContext(), **DISCOVER
        )
        assert (
            meta["finished_rail_cap"] is None
        ), "None means the pass never ran; 0 would mean it ran and did nothing"

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
