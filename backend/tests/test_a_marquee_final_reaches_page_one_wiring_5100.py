"""#5100 wiring — the seating pass is IN the Discover chain, in the right place.

``test_a_marquee_final_reaches_page_one_5100.py`` grades the rule; this grades the
wiring, which is the half that decides whether a reader ever sees it.

**Why this file exists at all: #4681's own page-one guard does not bite.**
``test_finished_marquee_on_discover_4681.py::test_the_nfl_opener_is_on_page_one_after_the_final``
is green on master, while production served both selected finals at positions 133
and 134 of 135 on 2026-09-11. Measured, the difference is one property of the
fixture: ``_saturating_futures_pool`` builds futures in seven category groups and
**none of them is** ``sports_culture`` — the group the game card itself lands in.
An uncontested group is never capped by ``diversify_discover_first_page``, so the
specimen is selected on the first pass no matter how it ranks. Instrumented, it
holds position 8 with a score of 67, of 45, of 20, of 5 and of 1, and it holds it
in a 38-card deck and in a 211-card deck alike.

Add golf or tennis futures — real ``sports_culture`` cards, which every production
page one carries — and the same specimen falls to **position 64 of 65**, which is
the production reading. So the pools here contest the event's own group, and the
red arm below is real rather than an artefact of a thin fixture.

RED ARM — measured on the unwired tree, which is the state this file was written
against. **7 failed, 6 passed:**

    test_the_selected_final_reaches_page_one ............................ FAILED
    test_it_sits_at_the_seat_floor_and_not_in_the_lead .................. FAILED
    test_the_chain_reports_what_it_seated ............................... FAILED
    test_a_WARM_reader_gets_the_seat_too ................................ FAILED
    test_a_PINNED_marquee_keeps_the_top_and_the_final_still_seats ....... FAILED
    test_the_chain_reports_seating_nothing_for_an_ordinary_final ........ FAILED
    test_the_seating_runs_AFTER_the_lead_and_BEFORE_the_quality_floor ... FAILED

``..._reports_seating_nothing_for_an_ordinary_final`` is in that list and should
be read as a wiring assertion, not a tail assertion: with no pass wired there is
no ``final_seating`` key to read. That is exactly why the tail control next to it
reads PLACEMENT ONLY — ``test_an_ordinary_finished_game_never_reaches_page_one``
is green on both trees, so it can still testify that the routine finished tail
stays off page one. A control that goes red under the deletion is not a control.

The other controls — the sports surface, the My Stuff surface, the preserved deck
length and the caller's untouched list — are green on both trees too, which is the
point of having them: they prove the ship is the seating pass and not a side
effect of something else in the chain.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone

from app.routes.feed import (
    PersonalizationContext,
    apply_discover_display_chain,
)
from app.utils.discover_final_seating import DISCOVER_FINAL_SEAT_FLOOR
from app.utils.tonights_games import MARQUEE_PIN_KEY

NOW = datetime(2026, 9, 11, 10, 26, tzinfo=timezone.utc)

DISCOVER = {
    "event_pct": 0.15,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": False,
}
SPORTS = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": True,
}

#: Seven non-sports groups plus `sports_culture`, which is the one that matters —
#: see the module docstring. `golf` is a real production category and maps to
#: `sports_culture`, the same group `_discover_category_group` gives a game card.
_POOL_CATEGORIES = (
    "politics",
    "geopolitics",
    "economics",
    "tech",
    "entertainment",
    "weather",
    "misc",
    "golf",
)


def _futures(i: int, category: str, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": f"f{i}",
        "reason": "resolves within a month",
        "data": {
            "id": 10_000 + i,
            "name": f"market {i}",
            "llm_sport_category": category,
            "outcomes": [{"name": "Yes", "probability": 0.5}],
        },
    }


def _contested_pool(per_category: int = 8) -> list[dict]:
    """A pool that can fill page one WITHOUT borrowing the game's slot."""
    pool: list[dict] = []
    for category in _POOL_CATEGORIES:
        for _ in range(per_category):
            pool.append(_futures(len(pool), category, 79.0 + (len(pool) % 11)))
    return pool


def _final(
    *,
    event_id: int = 14780138,
    score: int = 45,
    tier: str = "tier:1",
    hours_since_kickoff: float = 11.7,
    sport: str = "americanfootball_nfl",
) -> dict:
    """A finished marquee game as the decay leaves it by morning.

    ``score=45`` is not arbitrary: production's two specimens served 42 and 39
    after ``apply_completed_freshness_decay`` multiplied their ~93 and ~87 by the
    0.45 floor. This is a card at the bottom of the deck, which is the whole
    condition the ship addresses.
    """
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "_sort_time": 0,
        "headline": None,
        "reason": "",
        "data": {
            "id": event_id,
            "sport": sport,
            "status": "completed",
            "event_tags": [tier, "status:completed"],
            "home_team": "Seattle Seahawks",
            "away_team": "New England Patriots",
            "home_score": 13,
            "away_score": 10,
            "ei": {"score": 64},
            "home_team_data": {"logo": "h"},
            "away_team_data": {"logo": "a"},
            "commence_time": (NOW - timedelta(hours=hours_since_kickoff))
            .isoformat()
            .replace("+00:00", "Z"),
        },
    }


def _chain(items, **overrides):
    kwargs = {**DISCOVER, **overrides}
    return apply_discover_display_chain(
        items, limit=20, ctx=PersonalizationContext(), now=NOW, **kwargs
    )


def _position(items: list[dict], event_id: int) -> int | None:
    for index, item in enumerate(items):
        if (item.get("data") or {}).get("id") == event_id:
            return index
    return None


class TestTheShip:
    def test_the_selected_final_reaches_page_one(self):
        out, _ = _chain(_contested_pool() + [_final()])

        position = _position(out, 14780138)
        assert position is not None, "the selected final left the deck entirely"
        assert position < 20, (
            f"the final is at {position} of {len(out)} — off page one at "
            "FEED_PAGE_LIMIT = 20, which is the #4681 acceptance criterion this "
            "ship exists to finish"
        )

    def test_it_sits_at_the_seat_floor_and_not_in_the_lead(self):
        out, _ = _chain(_contested_pool() + [_final()])

        assert _position(out, 14780138) == DISCOVER_FINAL_SEAT_FLOOR, (
            "a result belongs in page one's back half — reaching page one and "
            "leading the deck are different claims, and this ship makes only "
            "the first"
        )

    def test_the_chain_reports_what_it_seated(self):
        _out, meta = _chain(_contested_pool() + [_final()])

        assert meta.get("final_seating") is not None, (
            "None means the pass never ran; a zero count would mean it ran and "
            "found nothing to do, and those are different facts (gotcha #53)"
        )
        assert meta["final_seating"]["seated"] == 1


class TestItHoldsForEveryReaderAndEveryLead:
    def test_a_WARM_reader_gets_the_seat_too(self):
        """Every other test here runs cold (an empty `PersonalizationContext`).

        Cold start tightens `diversify_discover_first_page`'s category caps to 2
        for the first eight cards, so a cold page one is composed differently
        from a warm one. The seating runs after that pass either way, and this
        is what says so rather than assuming it — the #4681 fixture's whole
        defect was a page-one claim that held for one composition only.
        """
        out, meta = _chain(_contested_pool() + [_final()], cold_start=False)

        assert _position(out, 14780138) == DISCOVER_FINAL_SEAT_FLOOR
        assert meta["final_seating"]["seated"] == 1

    def test_a_PINNED_marquee_keeps_the_top_and_the_final_still_seats(self):
        """The seat floor is below the lead, so a pin cannot be displaced.

        Asserted rather than reasoned: #5099's edition contract puts a pinned
        marquee ahead of every game in `compose_lead`'s order, and a placement
        pass that quietly cost it slot 0 would break that ship to deliver this
        one.
        """
        pinned = _futures(9_999, "golf", 95.0)
        pinned[MARQUEE_PIN_KEY] = True

        out, _ = _chain([pinned] + _contested_pool() + [_final()])

        assert out[0] is pinned, "the pinned marquee lost the top slot"
        assert _position(out, 14780138) == DISCOVER_FINAL_SEAT_FLOOR


class TestTheScoreboardStillStaysOut:
    """#4681 acceptance criterion 3, from the placement side."""

    def test_an_ordinary_finished_game_never_reaches_page_one(self):
        """A true control: it reads placement only, so it is green with the
        seating block deleted AND green with it wired. A version that also read
        `meta["final_seating"]` would go red on the missing key under deletion
        and so would prove nothing about the tail."""
        ordinary = _final(
            event_id=999001,
            tier="tier:4",
            sport="soccer_sweden_superettan",
        )
        out, _ = _chain(_contested_pool() + [ordinary])

        position = _position(out, 999001)
        assert position is None or position >= 20, (
            "the routine finished tail belongs on Sports and My Stuff; a "
            "placement pass that promoted it would break #4681 from the other side"
        )

    def test_the_chain_reports_seating_nothing_for_an_ordinary_final(self):
        ordinary = _final(
            event_id=999001,
            tier="tier:4",
            sport="soccer_sweden_superettan",
        )
        _out, meta = _chain(_contested_pool() + [ordinary])

        assert meta["final_seating"]["seated"] == 0

    def test_CONTROL_the_sports_surface_does_not_seat(self):
        _out, meta = _chain(_contested_pool() + [_final()], **SPORTS)

        assert meta.get("final_seating") is None, (
            "Sports has its own finished rails (#3511, #3836) and orders results "
            "on their merits; Discover's two-card carve-out is not its rule"
        )

    def test_CONTROL_a_non_discover_surface_does_not_raise(self):
        """Gotcha #7 — `kept_final_ids` is assigned inside the Discover branch.

        Read after that branch without being bound above it, it is an
        `UnboundLocalError` on every Sports and My Stuff request. The file
        already carries this exact hazard note for `kept_kickoff_ids`.
        """
        for surface in (SPORTS, {**SPORTS, "my_teams_only": True}):
            out, _ = _chain(_contested_pool() + [_final()], **surface)
            assert out, "the chain returned nothing"


class TestNothingIsLost:
    def test_the_deck_keeps_every_card_it_was_given(self):
        items = _contested_pool() + [_final()]
        out, _ = _chain(items)

        assert len(out) == len(items), (
            "a pure reorder — #1091's lesson is that a feed pass which can drop "
            "a card eventually empties a surface"
        )

    def test_CONTROL_the_callers_list_is_not_reordered_underneath_them(self):
        items = _contested_pool() + [_final()]
        snapshot = [id(item) for item in items]

        _chain(items)

        assert [id(item) for item in items] == snapshot


class TestTheOrderIsTheContract:
    def test_the_seating_runs_AFTER_the_lead_and_BEFORE_the_quality_floor(self):
        """Both boundaries are load-bearing, and a comment claiming them is not
        a control.

        AFTER `compose_lead`: two passes that both write a prefix compose as
        last-writer-wins, which is the defect `compose_lead`'s own comment in
        `feed.py` was written to record. Seating first would simply be
        overwritten.

        BEFORE `enforce_first_page_quality_floor`: that pass is last "deliberately",
        because `boring-rate@20` is counted over the SERVED order. Seating after it
        would hand the reader a page one the floor never screened — two cards
        displaced off the window with no chance to swap a clean card back in.

        Ordered by line number rather than by `ast.walk`'s traversal, which is
        breadth-first and only happens to agree for calls at one nesting depth.
        """
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        watched = {
            "compose_lead",
            "seat_marquee_finals",
            "enforce_first_page_quality_floor",
        }
        calls = sorted(
            (
                (node.lineno, node.func.id)
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in watched
            ),
        )
        assert [name for _, name in calls] == [
            "compose_lead",
            "seat_marquee_finals",
            "enforce_first_page_quality_floor",
        ], f"call order changed: {calls}"

    def test_CONTROL_the_chain_still_does_no_io(self):
        assert not inspect.iscoroutinefunction(apply_discover_display_chain)
        tree = ast.parse(inspect.getsource(apply_discover_display_chain))
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Await, ast.AsyncFor))
        ]
