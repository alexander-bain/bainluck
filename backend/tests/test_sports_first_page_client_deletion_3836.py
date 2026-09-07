"""#3836 — the Sports first page stops spending slots the browser deletes.

THE FINDING, MEASURED ON PRODUCTION 2026-09-07
-----------------------------------------------
`GET /api/feed?limit=20&mode=sports` served four finished games — slots 11, 13,
14 and 15, aged 15.3h, 20.3h, 14.1h and 12.3h since `commence_time` — that
`frontend/lib/discover/feedFreshness.ts` deletes before paint. Those slots are
not recovered: `FEED_PAGE_LIMIT` is 20 and `nextFeedRequest` marches
`0 -> 20 -> 40` with no overlap. The reader's first screen was a sixteen-card
page wearing a twenty-card budget.

WHAT THIS FILE HAS TO PROVE, BEYOND "THE SWAP HAPPENS"
-------------------------------------------------------
Three ways this ship could be worse than the defect, each with its own class:

1. It recreates #3805 by swapping in a fourth card on a rail already at cap.
2. It empties the surface (#1091 / gotcha #43) by trading away the last game
   the client would have rendered — the client's own `keptToAvoidEmptyGames`
   reprieve never fires if the backend removed the games first.
3. It shortens or reorders the page, which the swap-not-drop contract shared
   with `enforce_first_page_quality_floor` and `hoist_live_events_into_first_page`
   forbids.

`test_client_deletion_mirror_3836.py` grades the deletion PREDICATE and its
drift guard; this file grades the PASS and its WIRING.

RED ARM — run, not asserted. The `if sports_mode and not my_teams_only:` block
that calls `swap_client_deleted_finished_off_first_page` was DELETED from
`apply_discover_display_chain` (leaving `client_deletion_swap_meta = None` and
the import, since reverting the import gives a collection error, which grades as
"the harness never ran" rather than as red). Run together with the #3805 and
#2709 wiring files, **6 failed, 54 passed:**

    test_the_sports_chain_runs_a_client_deletion_swap_at_all ......... FAILED
    test_the_first_page_stops_carrying_cards_the_client_deletes ...... FAILED
    test_the_reader_gets_twenty_cards_not_sixteen .................... FAILED
    test_the_chain_reports_what_it_swapped ........................... FAILED
    test_the_swap_runs_AFTER_the_rail_cap_and_BEFORE_the_live_hoist .. FAILED
    test_both_passes_fire_when_the_page_is_repetitive_AND_doomed ..... FAILED

EVERY `TestPass` TEST STAYED GREEN under that deletion, and that is the correct
split rather than a gap: they call the pass directly, so they grade the rule and
cannot grade the wiring. The wiring is what the six above are for — the same
division `test_sports_first_page_rails_3511.py` and its `_wiring_` sibling use.

Two negative-space tests also stayed green and should not be read as coverage:
`test_discover_is_not_touched_by_this_pass` and `test_my_stuff_is_not_reordered`
assert `meta[...] is None`, which is exactly what a deleted call produces. They
are there to catch the pass being widened, not to catch it being removed.

Both control files stayed GREEN under the deletion — the #3805 control
`test_one_rail_cannot_take_the_sports_first_page` and the #2709 control
`test_every_buried_live_game_reaches_the_first_page_deep` — which is the point
of running them in the same arm: neither of those guarantees quietly depends on
this ship.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone

from app.routes import feed as feed_module
from app.routes.feed import PersonalizationContext, apply_discover_display_chain
from app.utils.sports_first_page_rails import (
    CLIENT_COMPLETED_MAX_AGE_HOURS,
    FINISHED_RAIL_FIRST_PAGE_CAP,
    client_deletes_finished_card,
    swap_client_deleted_finished_off_first_page,
)

NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

SPORTS = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": True,
}
DISCOVER = {
    "event_pct": 0.15,
    "include_events": True,
    "my_teams_only": False,
    "sports_mode": False,
}
MY_STUFF = {
    "event_pct": 0.6,
    "include_events": True,
    "my_teams_only": True,
    "sports_mode": False,
}
#: `mode` and `my_teams_only` are independent query parameters, so
#: `?mode=sports&my_teams_only=true` is a request a client can actually send.
#: CERT-2190 blocked the rail cap for reordering exactly this shape.
MY_STUFF_VIA_SPORTS_MODE = {**MY_STUFF, "sports_mode": True}


def _iso(hours_ago: float, *, base: datetime = NOW) -> str:
    return (base - timedelta(hours=hours_ago)).isoformat()


def _finished(i: int, score: float, headline: str, hours_ago: float) -> dict:
    """A finished game. `hours_ago` decides whether the client keeps it."""
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": headline,
        "data": {
            "id": i,
            "status": "completed",
            "commence_time": _iso(hours_ago),
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
            "commence_time": _iso(1.0),
            "home_team": f"Home {i}",
            "away_team": f"Away {i}",
            "current_odds": {"home_probability": 0.5, "away_probability": 0.5},
        },
    }


def _scheduled(i: int, score: float) -> dict:
    return {
        "type": "event",
        "score": score,
        "_rank_score": score,
        "_sort_time": 0,
        "headline": None,
        "data": {
            "id": i,
            "status": "scheduled",
            "commence_time": _iso(-10.0),
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


def _ids(items) -> list:
    return [(it.get("type"), (it.get("data") or {}).get("id")) for it in items]


def _doomed_on_page(items, limit: int = 20, *, now: datetime = NOW) -> list:
    return [
        (it.get("data") or {}).get("id")
        for it in items[:limit]
        if client_deletes_finished_card(it, now=now)
    ]


def _measured_pool(*, live_now: bool = False) -> list[dict]:
    """The 2026-09-07 shape: a window holding four cards the client deletes.

    Scores descend in construction order so the served order IS this order —
    the same device `_reported_pool` uses in the #3511 file, and for the same
    reason: this ship is a reorder, so a fixture whose order is decided
    elsewhere would grade the ranker instead.
    """
    window: list[dict] = []
    score = 100.0
    if live_now:
        window.append(_live(1, score))
        score -= 1
    # Slots the client keeps.
    for i in range(6):
        window.append(_market(i, score))
        score -= 1
    for i in range(4):
        window.append(_scheduled(300 + i, score))
        score -= 1
    # The four the client deletes — three on one rail, one on another, exactly
    # the measured mix. Ages are the measured ages.
    for i, (hrs, rail) in enumerate(
        [
            (15.3, "Recent upset"),
            (20.3, "Recent upset"),
            (14.1, "Line moving"),
            (12.3, "Recent upset"),
        ]
    ):
        window.append(_finished(400 + i, score, rail, hrs))
        score -= 1
    # Pad the window out to twenty with cards the client keeps.
    while len(window) < 20:
        window.append(_market(100 + len(window), score))
        score -= 1

    # The tail the production pull actually offered: plenty of admissible cards,
    # plus doomed ones that must never be chosen as replacements.
    tail: list[dict] = []
    for i in range(3):
        tail.append(_finished(500 + i, score, "Recent upset", 30.0 + i))
        score -= 1
    tail.append(_finished(600, score, "Recent upset", 2.0))  # fresh result
    score -= 1
    for i in range(8):
        tail.append(_market(200 + i, score))
        score -= 1
    for i in range(4):
        tail.append(_scheduled(700 + i, score))
        score -= 1
    return window + tail


class TestThePremise:
    """Asserted, not assumed. If the fixture ever stops reproducing the measured
    page, these go red and name the drift instead of letting the ship become a
    silent no-op with everything else green."""

    def test_the_pool_really_does_put_four_doomed_cards_on_page_one(self):
        assert len(_doomed_on_page(_measured_pool())) == 4

    def test_and_the_tail_really_does_offer_admissible_replacements(self):
        tail = _measured_pool()[20:]
        assert sum(1 for it in tail if not client_deletes_finished_card(it, now=NOW)) >= 4

    def test_the_rail_cap_would_NOT_have_caught_this(self):
        """The measurement that re-scoped this ship. Exactly three cards share
        the "Recent upset" rail on page one — exactly the cap — so
        `cap_repeated_finished_rails` is inert here and the page still loses
        four slots. Teaching only the cap about the 8h rule would have shipped
        nothing on this payload.

        This grades the MEASURED page, which is the claim being made. Inside the
        full chain the cap does fire on this fixture, because the interleaver
        reshapes the window before either pass sees it — that is a fixture
        artifact, not a contradiction, and `test_both_passes_fire_when_the_page
        _is_repetitive_AND_doomed` covers the two coexisting.
        """
        from app.utils.sports_first_page_rails import (
            cap_repeated_finished_rails,
            finished_rail_key,
        )

        pool = _measured_pool()
        rails = [finished_rail_key(it) for it in pool[:20]]
        assert rails.count("Recent upset") == FINISHED_RAIL_FIRST_PAGE_CAP
        _out, cap_meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert cap_meta["over_cap_before"] == 0
        assert cap_meta["swapped"] == 0


class TestThePass:
    def test_the_doomed_cards_leave_the_first_page(self):
        out, meta = swap_client_deleted_finished_off_first_page(
            _measured_pool(), first_page_size=20, now=NOW
        )
        assert _doomed_on_page(out) == []
        assert meta["client_deleted_before"] == 4
        assert meta["swapped"] == 4
        assert meta["client_deleted_after"] == 0
        assert meta["unswapped"] == 0
        assert meta["declined_to_keep_a_game"] is False

    def test_the_page_keeps_its_length_and_its_cards(self):
        """Swap, never drop. Nothing is deleted and nothing is invented — the
        multiset of cards is identical, only the order moved."""
        pool = _measured_pool()
        out, _meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert len(out) == len(pool)
        assert sorted(map(str, _ids(out))) == sorted(map(str, _ids(pool)))

    def test_a_replacement_is_never_itself_a_card_the_client_deletes(self):
        """The failure mode that would make this pass cosmetic: trading a
        15h-old card for a 30h-old one improves the payload and changes nothing
        on screen."""
        pool = _measured_pool()
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["swapped"] == 4
        moved_in = [it for it in out[:20] if it not in pool[:20]]
        assert len(moved_in) == 4
        assert all(not client_deletes_finished_card(it, now=NOW) for it in moved_in)

    def test_a_replacement_cannot_push_a_rail_over_the_3805_cap(self):
        """Undoing the pass that ran immediately before this one is the most
        expensive way to get this wrong, because #3805's own guards would stay
        green — they grade the cap's output, not this pass's."""
        window = [_market(i, 100.0 - i) for i in range(16)]
        # Three survivors already at cap, plus one doomed card to trigger a swap.
        window += [_finished(10 + i, 60.0 - i, "Recent upset", 1.0) for i in range(3)]
        window.append(_finished(20, 50.0, "Line moving", 19.0))
        # A tail of nothing but fresh same-rail results: every one is
        # admissible by age and every one is refused by the cap.
        tail = [_finished(30 + i, 40.0 - i, "Recent upset", 1.0) for i in range(6)]
        out, meta = swap_client_deleted_finished_off_first_page(
            window + tail, first_page_size=20, now=NOW
        )
        assert meta["replacements_available"] == 0
        assert meta["swapped"] == 0
        assert meta["unswapped"] == 1
        assert _ids(out) == _ids(window + tail), (
            "with nothing admissible to trade, the page must come back exactly "
            "as it arrived — a page that kept one doomed card is better than a "
            "page that recreated #3805"
        )

    def test_a_rail_freed_by_a_departing_card_can_be_reused(self):
        """The complement of the test above, and the reason rails are counted
        against the SURVIVORS rather than against the window as served. On the
        measured payload all three "Recent upset" cards were the doomed ones, so
        counting the window as-served would have refused the best replacement in
        the tail — a fresh result — for a rail that is about to be empty."""
        pool = _measured_pool()
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["swapped"] == 4
        page_ids = {(it.get("data") or {}).get("id") for it in out[:20]}
        assert 600 in page_ids, (
            "the fresh 'Recent upset' result at id 600 should have been "
            "admitted: all three same-rail cards on page one were doomed, so "
            "the rail it wants is free"
        )

    def test_the_best_replacement_goes_to_the_earliest_doomed_slot(self):
        """Reading order is the point of a ranked page. Pairing the weakest slot
        with the best card inverts it — that inversion is the CERT-2190 repair
        recorded in the rail cap, and this pass must not reintroduce it."""
        # A live game at the top so the #1091 refusal is not what is being
        # measured here — without it, swapping both finished cards away would
        # leave the window gameless and the pass would (correctly) decline,
        # which grades a different rule than the one this test is about.
        window = [_live(999, 200.0)] + [_market(i, 100.0 - i) for i in range(17)]
        window.append(_finished(1, 50.0, "Line moving", 30.0))  # slot 18
        window.append(_finished(2, 49.0, "Line moving", 31.0))  # slot 19
        tail = [_market(90, 40.0), _market(91, 30.0)]
        out, meta = swap_client_deleted_finished_off_first_page(
            window + tail, first_page_size=20, now=NOW
        )
        assert meta["swapped"] == 2
        assert (out[18].get("data") or {}).get("id") == 9090
        assert (out[19].get("data") or {}).get("id") == 9091

    def test_live_and_scheduled_games_are_never_displaced(self):
        pool = _measured_pool(live_now=True)
        out, _meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        survivors = {
            (it.get("data") or {}).get("id")
            for it in out[:20]
            if (it.get("data") or {}).get("status") in ("live", "scheduled")
        }
        originals = {
            (it.get("data") or {}).get("id")
            for it in pool[:20]
            if (it.get("data") or {}).get("status") in ("live", "scheduled")
        }
        assert originals <= survivors


class TestItRefusesToEmptyTheSurface:
    """#1091 / gotcha #43, asserted in BOTH directions — that the pass declines
    when it must, and that it does NOT decline when a game survives. A guard
    with only the first half would be satisfied by a pass that never runs."""

    def _all_games_doomed_pool(self) -> list[dict]:
        window = [_market(i, 100.0 - i) for i in range(17)]
        window += [_finished(10 + i, 50.0 - i, "Recent upset", 20.0 + i) for i in range(3)]
        tail = [_market(50 + i, 30.0 - i) for i in range(6)]
        return window + tail

    def test_it_declines_rather_than_hand_the_reader_a_gameless_sports_page(self):
        pool = self._all_games_doomed_pool()
        assert all(
            client_deletes_finished_card(it, now=NOW)
            for it in pool[:20]
            if it.get("type") == "event"
        )
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["declined_to_keep_a_game"] is True
        assert meta["swapped"] == 0
        assert meta["unswapped"] == 3
        assert _ids(out) == _ids(pool), "declining means UNTOUCHED, not partly applied"

    def test_the_stale_games_it_declined_to_move_are_still_there_for_the_clients_reprieve(
        self,
    ):
        """The whole reason declining is right: the client's own guard carries
        these three. If the backend had traded them for futures, that reprieve
        would have nothing to reprieve and /sports would render zero games."""
        pool = self._all_games_doomed_pool()
        out, _meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert sum(1 for it in out[:20] if it.get("type") == "event") == 3

    def test_one_surviving_game_is_enough_to_let_the_pass_run(self):
        """The other direction. Add a single live game and the same pool is
        swapped normally — so the decline above is a response to the emptiness
        condition, not the pass being broken."""
        pool = self._all_games_doomed_pool()
        pool.insert(0, _live(999, 200.0))
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["declined_to_keep_a_game"] is False
        assert meta["swapped"] > 0
        assert _doomed_on_page(out) == []


class TestItIsHarmlessWhereItShouldBe:
    def test_a_page_with_nothing_doomed_is_returned_untouched(self):
        pool = [_market(i, 100.0 - i) for i in range(10)] + [
            _finished(1, 50.0, "Recent upset", 1.0)
        ]
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["client_deleted_before"] == 0
        assert meta["swapped"] == 0
        assert out is pool

    def test_an_empty_page_is_not_an_error(self):
        out, meta = swap_client_deleted_finished_off_first_page(
            [], first_page_size=20, now=NOW
        )
        assert out == []
        assert meta["client_deleted_before"] == 0

    def test_a_doomed_card_beyond_the_window_is_left_alone(self):
        """The pass reasons about the first page only. A 40h-old result at slot
        30 is the client's problem and paginating past it is the reader's
        choice; hunting it here would be a filter, not a first-page pass."""
        pool = [_market(i, 100.0 - i) for i in range(20)]
        pool.append(_finished(1, 10.0, "Recent upset", 40.0))
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["client_deleted_before"] == 0
        assert _ids(out) == _ids(pool)

    def test_a_short_page_uses_its_real_length_as_the_window(self):
        pool = [_finished(1, 50.0, "Line moving", 20.0), _market(2, 40.0)]
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        # Window is the whole list, so there is no tail to trade with and the
        # page comes back intact rather than reordered into nothing.
        assert meta["client_deleted_before"] == 1
        assert meta["swapped"] == 0
        assert _ids(out) == _ids(pool)

    def test_a_malformed_card_cannot_take_the_page_down(self):
        """gotcha #42 — one bad item never wipes a pass. The healthy siblings
        must still be swapped."""
        pool = _measured_pool()
        pool.insert(5, {"type": "event", "headline": None, "data": None})
        pool.insert(9, None)  # type: ignore[arg-type]
        out, meta = swap_client_deleted_finished_off_first_page(
            pool, first_page_size=20, now=NOW
        )
        assert meta["swapped"] > 0
        assert len(out) == len(pool)


class TestWiring:
    """Asserting on the chain's OUTPUT rather than on a call, for the reason
    `test_feed_live_first_page_wiring_2709.py` gives: `get_feed` serves
    `feed_items[offset : offset + limit]`, a pure prefix, so the first twenty
    items of what the chain returns ARE the first page a reader is sent."""

    def _chain(self, pool, surface):
        return apply_discover_display_chain(
            pool, limit=20, ctx=PersonalizationContext(), **surface
        )

    def test_the_sports_chain_runs_a_client_deletion_swap_at_all(self):
        """Separate from the count on purpose: "the pass never ran" and "the
        pass ran and chose badly" are different defects and one assertion would
        report them identically."""
        _out, meta = self._chain(_measured_pool(), SPORTS)
        assert meta["client_deletion_swap"] is not None

    def test_the_first_page_stops_carrying_cards_the_client_deletes(self):
        out, _meta = self._chain(_measured_pool(), SPORTS)
        assert _doomed_on_page(out, now=datetime.now(timezone.utc)) == []

    def test_the_reader_gets_twenty_cards_not_sixteen(self):
        """The ship, stated the way a reader would experience it. Four of the
        twenty slots used to be deleted before paint; after this, twenty cards
        survive the client's own freshness gate."""
        out, _meta = self._chain(_measured_pool(), SPORTS)
        now = datetime.now(timezone.utc)
        rendered = [it for it in out[:20] if not client_deletes_finished_card(it, now=now)]
        assert len(rendered) == 20

    def test_the_chain_reports_what_it_swapped(self):
        """Relational, not absolute, and deliberately so. The exact count of
        doomed cards in the SERVED window is not 4 — the chain interleaves by
        `event_pct` before this pass runs, so it sees a window the fixture did
        not hand it. Pinning 4 here would be pinning an artifact of the
        interleaver; `TestThePass` grades the exact numbers by calling the pass
        directly, which is where they mean something.
        """
        _out, meta = self._chain(_measured_pool(), SPORTS)
        swap = meta["client_deletion_swap"]
        assert swap["client_deleted_before"] > 0, (
            "the fixture must still reach this pass with doomed cards on page "
            "one, or every other assertion here is vacuous"
        )
        assert swap["swapped"] == swap["client_deleted_before"]
        assert swap["unswapped"] == 0
        assert swap["declined_to_keep_a_game"] is False
        assert swap["max_age_hours"] == CLIENT_COMPLETED_MAX_AGE_HOURS

    def test_discover_is_not_touched_by_this_pass(self):
        """Discover runs the identical client rule, but its first page is
        composed by `compose_lead` + `diversify_discover_first_page` and it
        carried zero event cards when this was measured. Widening a pass to a
        surface with no reading behind it is how a narrow fix becomes an
        unreviewable one — so the gate is asserted, not left to chance."""
        _out, meta = self._chain(_measured_pool(), DISCOVER)
        assert meta["client_deletion_swap"] is None

    def test_my_stuff_is_not_reordered(self):
        """CERT-2190 blocked the rail cap for exactly this: `not discover_mode`
        is TRUE for My Stuff, whose contract is to show everything matching and
        skip diversity work entirely."""
        _out, meta = self._chain(_measured_pool(), MY_STUFF)
        assert meta["client_deletion_swap"] is None

    def test_my_stuff_asked_for_via_mode_sports_is_still_my_stuff(self):
        """`mode` and `my_teams_only` are independent parameters, so
        `?mode=sports&my_teams_only=true` is reachable — and it is a My Stuff
        request."""
        pool = _measured_pool()
        out, meta = self._chain(pool, MY_STUFF_VIA_SPORTS_MODE)
        assert meta["client_deletion_swap"] is None
        assert _doomed_on_page(out, now=datetime.now(timezone.utc)), (
            "the control is only meaningful if My Stuff would otherwise have "
            "been changed by this pass"
        )

    def test_the_swap_runs_AFTER_the_rail_cap_and_BEFORE_the_live_hoist(self):
        """Position is the contract, and it is read from the source rather than
        inferred from an output, because two passes can produce the same page on
        one fixture and different pages on the next.

        AFTER the cap: the cap's departures free rails a replacement may take.
        BEFORE the hoist: that pass is Alex's P1 criterion and keeps the last
        word on first-page membership.
        """
        tree = ast.parse(inspect.getsource(feed_module.apply_discover_display_chain))
        order = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        for name in (
            "cap_repeated_finished_rails",
            "swap_client_deleted_finished_off_first_page",
            "hoist_live_events_into_first_page",
        ):
            assert name in order, f"{name} is not called in the display chain"
        assert order.index("cap_repeated_finished_rails") < order.index(
            "swap_client_deleted_finished_off_first_page"
        ) < order.index("hoist_live_events_into_first_page")

    def test_both_passes_fire_when_the_page_is_repetitive_AND_doomed(self):
        """The two passes coexisting is its own claim. A page can be both nine
        copies of one story and full of cards the client deletes, and fixing
        either one must not disarm the other."""
        upsets = [_finished(100 + i, 98.0 - i, "Recent upset", 1.0) for i in range(9)]
        doomed = [_finished(200 + i, 80.0 - i, "Line moving", 20.0 + i) for i in range(4)]
        markets = [_market(i, 60.0 - i) for i in range(20)]
        _out, meta = self._chain(upsets + doomed + markets, SPORTS)
        assert meta["finished_rail_cap"]["swapped"] > 0
        assert meta["client_deletion_swap"]["swapped"] > 0

    def test_the_swap_does_not_cost_the_page_its_live_game(self):
        """#2709's guarantee is the hoist's, but this pass runs before it and
        could in principle spend the slot the hoist needs. It cannot: it only
        displaces finished cards."""
        pool = _measured_pool(live_now=True)
        out, _meta = self._chain(pool, SPORTS)
        live_ids = {
            (it.get("data") or {}).get("id")
            for it in out[:20]
            if (it.get("data") or {}).get("status") == "live"
        }
        assert 1 in live_ids
