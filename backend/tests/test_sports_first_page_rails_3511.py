"""#3511 — one story does not get nine cards on the Sports first page.

This file grades the RULE. `test_sports_first_page_rails_wiring_3511.py` grades
the wiring, which is the other half: `diversify_discover_first_page`'s repeat cap
runs under `if discover_mode:` and the games-led surface never reached it.

THE FIXTURE IS THE MEASURED PAGE. `_reported_page()` is the served payload of
2026-09-07 04:40Z, slot for slot: 20 cards, ten of them finished, nine of the
ten headlined "Recent upset". Every assertion below is a statement about that
page and not about a shape invented to make a cap look necessary.

RED ARM — falsified, not assumed. `cap_repeated_finished_rails` was stubbed to
`return items, empty_meta` (pre-ship: no cap) and this file re-run. **5 failed,
11 passed.** The five reds:

    test_the_repeated_rail_is_capped_on_the_first_page ....... FAILED
    test_the_surplus_cards_are_the_weakest_of_their_rail ..... FAILED
    test_the_page_still_shows_results ........................ FAILED
    test_a_thin_pool_keeps_its_repeats_rather_than_shrinking . FAILED
    test_a_tail_of_the_same_rail_cannot_recreate_the_problem . FAILED

The last two are worth naming, because a first draft of this docstring listed
them as controls and running the arm proved that wrong. They assert on `meta`,
and a stub that reports a clean pass while keeping nine repeats is exactly the
silent cap gotcha #53 forbids — so they are ship arms, not controls, and the
distinction was measured rather than reasoned about.

The eleven that stayed green are the real controls, and they are the ones that
matter: `test_no_card_is_ever_dropped`,
`test_live_and_upcoming_games_are_never_counted`,
`test_upcoming_games_sharing_a_headline_are_never_counted`,
`test_unlabelled_finished_cards_are_not_one_shared_rail` and
`test_the_window_is_the_page_not_the_pool` all pass with the pass disabled,
because membership never changes and only ORDER moves.
"""

from __future__ import annotations

from app.utils.sports_first_page_rails import (
    FINISHED_RAIL_FIRST_PAGE_CAP,
    cap_repeated_finished_rails,
    finished_rail_key,
)


def _event(i: int, status: str, headline: str | None) -> dict:
    return {
        "type": "event",
        "headline": headline,
        "data": {"id": i, "status": status},
    }


def _futures(i: int) -> dict:
    return {"type": "futures", "headline": "Leads at 14%", "data": {"id": 9000 + i}}


# The served page of 2026-09-07 04:40Z, in served order. `U` is a finished card
# headlined "Recent upset", `L` a finished card headlined "Line moving".
_MEASURED_WINDOW = [
    ("concept", None),
    ("live", "Upset brewing"),
    ("completed", "Recent upset"),
    ("futures", None),
    ("scheduled", "Line moving"),
    ("completed", "Recent upset"),
    ("futures", None),
    ("completed", "Recent upset"),
    ("completed", "Recent upset"),
    ("futures", None),
    ("completed", "Line moving"),
    ("completed", "Recent upset"),
    ("futures", None),
    ("completed", "Recent upset"),
    ("completed", "Recent upset"),
    ("completed", "Recent upset"),
    ("completed", "Recent upset"),
    ("futures", None),
    ("futures", None),
    ("futures", None),
]


def _reported_page() -> list[dict]:
    """The measured window, plus the tail the served feed actually carried.

    The tail matters as much as the window: slots 21-33 of the served payload
    were futures/concept cards, which is why a swap had somewhere to go. A
    fixture with a window and no tail cannot tell "the cap fired" from "the cap
    had nothing to trade", and those are different verdicts (gotcha #53).
    """
    items: list[dict] = []
    for i, (kind, headline) in enumerate(_MEASURED_WINDOW):
        if kind in ("futures", "concept"):
            items.append(_futures(i))
        else:
            items.append(_event(i, kind, headline))
    items += [_futures(100 + i) for i in range(13)]
    return items


def _rails(items: list[dict], limit: int = 20) -> list[str]:
    return [r for r in (finished_rail_key(it) for it in items[:limit]) if r]


def _ids(items: list[dict]) -> set:
    return {(it["type"], it["data"]["id"]) for it in items}


class TestTheReportedPage:
    def test_the_fixture_really_does_express_the_defect(self):
        """The precondition, asserted rather than assumed. If the fixture stops
        carrying nine repeats, the ship arms below become vacuous passes."""
        assert _rails(_reported_page()).count("Recent upset") == 9

    def test_the_repeated_rail_is_capped_on_the_first_page(self):
        out, meta = cap_repeated_finished_rails(_reported_page(), first_page_size=20)
        assert _rails(out).count("Recent upset") == FINISHED_RAIL_FIRST_PAGE_CAP
        assert meta["swapped"] == 6
        assert meta["unswapped"] == 0

    def test_the_surplus_cards_are_the_weakest_of_their_rail(self):
        """Served order decides who stays: the three kept "Recent upset" cards
        must be the three that ranked highest, not an arbitrary three."""
        out, _ = cap_repeated_finished_rails(_reported_page(), first_page_size=20)
        kept = [
            it["data"]["id"]
            for it in out[:20]
            if finished_rail_key(it) == "Recent upset"
        ]
        assert kept == [2, 5, 7], "the top three by rank must be the survivors"

    def test_the_other_finished_rail_is_untouched(self):
        """One "Line moving" result is under the cap and must keep its slot. A
        cap that fires on a rail with one card is a cap on finished games, which
        is not what this is."""
        out, _ = cap_repeated_finished_rails(_reported_page(), first_page_size=20)
        assert _rails(out).count("Line moving") == 1

    def test_the_page_still_shows_results(self):
        """#1091's standing lesson. The reader came to a games surface; the fix
        for nine copies of one result is not zero results."""
        out, _ = cap_repeated_finished_rails(_reported_page(), first_page_size=20)
        finished = [it for it in out[:20] if finished_rail_key(it)]
        assert len(finished) == 4, "3 upsets + 1 line-moving result stay on page one"


class TestTheContract:
    def test_no_card_is_ever_dropped(self):
        pool = _reported_page()
        out, _ = cap_repeated_finished_rails(pool, first_page_size=20)
        assert _ids(out) == _ids(pool)
        assert len(out) == len(pool)

    def test_live_and_upcoming_games_are_never_counted(self):
        """Scoped to finished cards deliberately: every live game shares the
        headline "Live", so an unscoped cap would push live rows off the page to
        satisfy a diversity rule — the exact defect #2709 shipped the hoist to
        end."""
        pool = [_event(i, "live", "Live") for i in range(9)] + [
            _futures(i) for i in range(20)
        ]
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 0
        assert out == pool
        live_on_page = [
            it for it in out[:20] if (it.get("data") or {}).get("status") == "live"
        ]
        assert len(live_on_page) == 9, "all nine live games keep their slots"

    def test_upcoming_games_sharing_a_headline_are_never_counted(self):
        pool = [_event(i, "scheduled", "Line moving") for i in range(9)] + [
            _futures(i) for i in range(20)
        ]
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 0
        assert out == pool

    def test_a_thin_pool_keeps_its_repeats_rather_than_shrinking(self):
        """No tail to trade with: the page is returned exactly as it arrived and
        the shortfall is REPORTED, not swallowed. A shorter page is not an
        improvement on a repetitive one."""
        pool = [_event(i, "completed", "Recent upset") for i in range(9)]
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert out == pool
        assert meta["over_cap_before"] == 6
        assert meta["swapped"] == 0
        assert meta["unswapped"] == 6, "a kept repeat must not log as a clean pass"

    def test_a_tail_of_the_same_rail_cannot_recreate_the_problem(self):
        """The replacement rule is the half that is easy to get wrong: trading
        six "Recent upset" cards for six more is a no-op that reports success."""
        pool = (
            [_event(i, "completed", "Recent upset") for i in range(9)]
            + [_futures(i) for i in range(11)]
            + [_event(100 + i, "completed", "Recent upset") for i in range(20)]
        )
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 6
        assert meta["replacements_available"] == 0, (
            "every tail card is the SAME rail already at its cap — none is a "
            "legal replacement"
        )
        assert meta["swapped"] == 0
        assert meta["unswapped"] == 6
        assert _rails(out).count("Recent upset") == 9, "the page is unchanged"

    def test_unlabelled_finished_cards_are_not_one_shared_rail(self):
        """The served page carried eight headline-less finished cards and they
        are eight different games. Bucketing them together would cap cards that
        repeat nothing."""
        pool = [_event(i, "completed", None) for i in range(9)] + [
            _futures(i) for i in range(20)
        ]
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 0
        assert out == pool

    def test_an_empty_headline_is_not_a_rail(self):
        pool = [_event(i, "completed", "   ") for i in range(9)] + [
            _futures(i) for i in range(20)
        ]
        _out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 0

    def test_the_caller_list_is_not_mutated(self):
        pool = _reported_page()
        snapshot = [id(x) for x in pool]
        cap_repeated_finished_rails(pool, first_page_size=20)
        assert [id(x) for x in pool] == snapshot

    def test_it_survives_malformed_rows(self):
        """gotcha #42: one bad item must never wipe the pass."""
        pool = [
            {"type": "event", "headline": "Recent upset", "data": None},
            {"type": "event"},
            "not a dict",
            None,
        ] + [_event(i, "completed", "Recent upset") for i in range(9)]
        out, _ = cap_repeated_finished_rails(pool, first_page_size=20)
        assert len(out) == len(pool)

    def test_an_empty_pool_is_a_no_op(self):
        out, meta = cap_repeated_finished_rails([], first_page_size=20)
        assert out == []
        assert meta["over_cap_before"] == 0

    def test_the_window_is_the_page_not_the_pool(self):
        """Cards beyond the first page are not capped — the rule is about what a
        reader sees on one screen, and a second page of upsets is a second page
        they chose to scroll to."""
        pool = [_futures(i) for i in range(20)] + [
            _event(i, "completed", "Recent upset") for i in range(9)
        ]
        out, meta = cap_repeated_finished_rails(pool, first_page_size=20)
        assert meta["over_cap_before"] == 0
        assert out == pool
