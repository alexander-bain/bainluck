"""#5100 — last night's important result is findable this morning.

The placement half of #4681. Its admission half already works: measured on
production 2026-09-11 10:26Z, both selected marquee finals were SERVED and both
carried ``discover_marquee_final: true`` — at positions 133 and 134 of 135, i.e.
page seven at ``FEED_PAGE_LIMIT = 20``.

Every test here asserts BOTH directions (gotcha #43), because the two failure
modes are opposite and a suite that only proves promotion would green-light a
pass that seats the whole Tuesday-night Superettan slate onto page one — which is
#4681's own acceptance criterion 3, broken from the other side.
"""

import pytest

from app.utils.discover_final_seating import (
    DISCOVER_FINAL_SEAT_FLOOR,
    seat_marquee_finals,
)

FIRST_PAGE = 20


def _final(event_id: int, *, sport: str = "americanfootball_nfl") -> dict:
    """A finished game card, shaped like the #4681 specimen."""
    return {
        "type": "event",
        "score": 39,
        "headline": None,
        "reason": "",
        "data": {
            "id": event_id,
            "sport": sport,
            "status": "completed",
            "home_team": f"Home {event_id}",
            "away_team": f"Away {event_id}",
            "home_score": 13,
            "away_score": 10,
        },
    }


def _futures(key: str) -> dict:
    return {"type": "futures", "score": 50, "data": {"id": None, "name": key}}


def _deck(*, finals_at: dict[int, dict], size: int = 40) -> list[dict]:
    """A deck of `size` futures with the given finals spliced in at fixed slots."""
    items: list[dict] = [_futures(f"f-{n}") for n in range(size)]
    for position, card in sorted(finals_at.items()):
        items[position] = card
    return items


class TestTheSelectedFinalReachesPageOne:
    def test_a_final_ranked_last_is_seated_on_page_one(self):
        final = _final(14780138)
        items = _deck(finals_at={39: final})

        out, meta = seat_marquee_finals(items, {14780138}, first_page_size=FIRST_PAGE)

        assert out.index(final) < FIRST_PAGE, (
            "the whole ship: a selected marquee final the reader would meet on "
            "page seven is on page one"
        )
        assert meta["seated"] == 1
        assert meta["unseated"] == 0

    def test_it_is_seated_at_the_floor_and_never_into_the_lead(self):
        final = _final(14780138)
        items = _deck(finals_at={39: final})
        lead_before = items[:DISCOVER_FINAL_SEAT_FLOOR]

        out, _ = seat_marquee_finals(items, {14780138}, first_page_size=FIRST_PAGE)

        assert out.index(final) == DISCOVER_FINAL_SEAT_FLOOR
        assert out[:DISCOVER_FINAL_SEAT_FLOOR] == lead_before, (
            "`compose_lead` owns the prefix under C185; a second prefix writer "
            "is the failure `feed.py` already documents"
        )

    def test_two_finals_take_consecutive_seats_in_their_ranked_order(self):
        first, second = _final(101), _final(102)
        items = _deck(finals_at={30: first, 35: second})

        out, meta = seat_marquee_finals(items, {101, 102}, first_page_size=FIRST_PAGE)

        assert out.index(first) == DISCOVER_FINAL_SEAT_FLOOR
        assert out.index(second) == DISCOVER_FINAL_SEAT_FLOOR + 1
        assert meta["seated"] == 2


class TestTheOrdinaryTailIsNotReadmitted:
    """#4681 acceptance criterion 3, from the placement side."""

    def test_a_finished_game_the_arm_did_not_select_is_never_moved(self):
        selected, ordinary = _final(101), _final(999, sport="soccer_sweden_superettan")
        items = _deck(finals_at={30: selected, 31: ordinary})

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert out.index(selected) == DISCOVER_FINAL_SEAT_FLOOR
        assert out.index(ordinary) >= FIRST_PAGE, (
            "only the ids the arm chose are seated — a pass that promoted every "
            "finished card would turn Discover into the scoreboard"
        )
        assert meta["seated"] == 1

    def test_an_empty_selection_is_a_no_op(self):
        items = _deck(finals_at={39: _final(101)})
        before = list(items)

        for empty in (None, set()):
            out, meta = seat_marquee_finals(items, empty, first_page_size=FIRST_PAGE)
            assert out == before
            assert meta["seated"] == 0

    def test_a_non_event_card_carrying_the_same_id_is_not_seated(self):
        impostor = {"type": "futures", "score": 9, "data": {"id": 101}}
        items = _deck(finals_at={39: impostor})

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert out.index(impostor) == 39
        assert meta["seated"] == 0


class TestItPromotesAndNeverDemotes:
    def test_a_final_already_on_page_one_is_left_where_it_ranked(self):
        """A game inside the 1.5h fresh window ranks on its own merit.

        Seating it would move it DOWN to the floor — this pass demoting the very
        card it exists to promote.
        """
        final = _final(101)
        items = _deck(finals_at={2: final})

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert out.index(final) == 2
        assert meta["already_on_page"] == 1
        assert meta["seated"] == 0

    def test_a_final_at_the_last_slot_of_page_one_is_left_alone(self):
        final = _final(101)
        items = _deck(finals_at={FIRST_PAGE - 1: final})

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert out.index(final) == FIRST_PAGE - 1
        assert meta["already_on_page"] == 1


class TestNothingIsLostAndNothingIsInvented:
    def test_length_and_membership_are_preserved_exactly(self):
        items = _deck(finals_at={30: _final(101), 35: _final(102)})
        before_ids = sorted(id(item) for item in items)

        out, _ = seat_marquee_finals(items, {101, 102}, first_page_size=FIRST_PAGE)

        assert len(out) == len(items)
        assert sorted(id(item) for item in out) == before_ids, (
            "a pure reorder — #1091's lesson is that a feed pass which can drop "
            "a card eventually empties a surface"
        )

    def test_seating_is_idempotent(self):
        items = _deck(finals_at={39: _final(101)})

        once, _ = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)
        twice, meta = seat_marquee_finals(once, {101}, first_page_size=FIRST_PAGE)

        assert twice == once
        assert meta["seated"] == 0
        assert meta["already_on_page"] == 1

    def test_a_malformed_card_costs_placement_and_never_the_deck(self):
        """Gotcha #42 — one bad item must not wipe the pass."""
        items = _deck(finals_at={39: _final(101)})
        items[7] = {"type": "event", "data": ["not", "a", "dict"]}
        before = list(items)

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert out == before
        assert meta["seated"] == 0
        assert meta["unseated"] == 1


class TestTheShortfallIsLoud:
    """Gotcha #53 — "nothing to seat" and "nowhere to seat it" are opposite facts."""

    def test_more_finals_than_seats_reports_the_remainder(self):
        finals = {30 + n: _final(200 + n) for n in range(4)}
        items = _deck(finals_at=finals)

        out, meta = seat_marquee_finals(
            items,
            {200, 201, 202, 203},
            first_page_size=DISCOVER_FINAL_SEAT_FLOOR + 2,
            seat_floor=DISCOVER_FINAL_SEAT_FLOOR,
        )

        assert meta["seats_available"] == 2
        assert meta["seated"] == 2
        assert meta["unseated"] == 2
        assert len(out) == len(items)

    def test_a_floor_past_the_page_seats_nothing_and_says_so(self, caplog):
        items = _deck(finals_at={39: _final(101)})
        before = list(items)

        with caplog.at_level("WARNING"):
            out, meta = seat_marquee_finals(
                items, {101}, first_page_size=8, seat_floor=10
            )

        assert out == before
        assert meta["seated"] == 0
        assert meta["unseated"] == 1
        assert meta["seats_available"] == 0
        assert "no legal seat" in caplog.text, (
            "a misconfigured floor must not read like a night with no marquee "
            "final at all"
        )

    def test_a_deck_shorter_than_the_page_is_all_page_one(self):
        """The seats are bounded by the DECK, not by the page size asked for.

        Fourteen cards under a twenty-card page means the whole deck is page
        one, so the final at slot 13 is already findable and moving it to the
        floor would be a demotion.

        What this pins is ``seats_available``, not the already-on-page test: a
        short deck has four legal seats (10-13), not ten. The clamp only bites
        on capacity — a mutant dropping it from the position check survived this
        suite, because a position is always below the deck length, and the
        source says so where the clamp used to be.
        """
        final = _final(101)
        items = _deck(finals_at={13: final}, size=14)

        out, meta = seat_marquee_finals(items, {101}, first_page_size=FIRST_PAGE)

        assert meta["seats_available"] == 14 - DISCOVER_FINAL_SEAT_FLOOR
        assert out.index(final) == 13
        assert meta["already_on_page"] == 1
        assert meta["seated"] == 0

    def test_a_final_below_a_short_deck_page_is_still_seated(self):
        final = _final(101)
        items = _deck(finals_at={13: final}, size=14)

        out, meta = seat_marquee_finals(items, {101}, first_page_size=12)

        assert out.index(final) == DISCOVER_FINAL_SEAT_FLOOR
        assert meta["seated"] == 1


def test_the_seat_floor_is_ten_5100():
    """The number is load-bearing, so it may not move in silence.

    Ten because slots 0-9 are spoken for twice over: `compose_lead` owns the
    first `MAX_LEAD = 3` under C185, and clause (d)'s `FIRST_PAGE_WHY_NOW_WINDOW`
    governs the first ten as the page's "what is happening now" band. It is
    deliberately its OWN constant rather than a read of the why-now window —
    the two answer different questions, and retuning clause (d) must not move
    this ship.
    """
    assert DISCOVER_FINAL_SEAT_FLOOR == 10


@pytest.mark.parametrize("page_size", [12, 20, 40, 250])
def test_the_seat_position_never_moves_with_the_page_size(page_size):
    """#5101's rule, carried into this pass: the SEAT is a fixed slot.

    ``first_page_size`` may only decide WHETHER a final needs seating, never
    WHERE it sits. If the seat were sized off the page — a floor of
    ``page_size // 2``, say — the same card would land in a different slot for
    a caller asking 12 than for one asking 250, which is precisely the defect
    #5101 removed from the composition stages.

    The parameter is read by the assertion, not just by the id: a card ranked
    below every page size here needs seating under all of them, so the seat
    must come out identical every time.
    """
    final = _final(101)
    items = _deck(finals_at={299: final}, size=300)

    out, meta = seat_marquee_finals(items, {101}, first_page_size=page_size)

    assert meta["seated"] == 1, f"page_size={page_size} left the final unseated"
    assert (
        out.index(final) == DISCOVER_FINAL_SEAT_FLOOR
    ), f"page_size={page_size} moved the seat off the fixed floor"
