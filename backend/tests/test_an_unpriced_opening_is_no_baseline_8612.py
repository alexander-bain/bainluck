"""#8612 — a card measures no lifetime move from an opening that was never a price.

Discover card 40, 2026-09-25 12:15Z: "Kanye West performs in Russia by October
31: 8% chance, down 86.3 points since Aug 19". The 0.94 opening (outcome
220051242) was stored off a 16c/96c book. Card 73 was the untraded midpoint:
Starship, 0.495 on 2c/97c, "up 37 points since Jul 31".

`update_max_movement`'s A10 lists such legs under
`market_metadata['unpriced_opening_ids']`
(`tests/integration/test_unpriced_opening_pg_8612.py` proves the SQL on real
Postgres). This file pins the reader: `unpriced_opening_ids` parses the list
fail-open, and `_biggest_move_from_opening`, the single place every serving
path gets its "since <date>" subject from, refuses a listed leg.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.routes.feed import _biggest_move_from_opening
from app.utils.futures_highlights import MODERATE_SURPRISE_THRESHOLD
from app.utils.futures_market_snapshot import (
    UNPRICED_OPENING_METADATA_KEY,
    unpriced_opening_ids,
)

KANYE = 220051242
OPENED = datetime(2026, 8, 19, 14, 2, 4, tzinfo=timezone.utc)


class _Market:
    """A plain carrier: the reader reads `__dict__`, never `getattr`."""

    def __init__(self, metadata, opened_at=OPENED):
        self.market_metadata = metadata
        self.opening_baseline_at = opened_at


def _leg(oid, name, opening, current):
    return {"id": oid, "name": name, "opening_probability": opening,
            "probability": current}


class TestTheReaderParsesFailOpen:
    def test_the_list_is_read_as_ids(self):
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [KANYE, 7]})
        assert unpriced_opening_ids(m) == frozenset({KANYE, 7})

    def test_absent_malformed_and_non_object_refuse_nothing(self):
        for metadata in (None, {}, {UNPRICED_OPENING_METADATA_KEY: "220051242"},
                         {UNPRICED_OPENING_METADATA_KEY: {"220051242": True}}, []):
            assert unpriced_opening_ids(_Market(metadata)) == frozenset(), metadata

    def test_a_bool_or_string_entry_is_not_an_id(self):
        # `True == 1`, so a bool left in would refuse outcome 1.
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [True, "5", 9]})
        assert unpriced_opening_ids(m) == frozenset({9})

    def test_the_key_is_the_one_the_sweep_writes(self):
        import inspect

        import app.tasks as tasks_mod

        src = inspect.getsource(tasks_mod.update_max_movement)
        assert "UNPRICED_OPENING_METADATA_KEY" in src
        assert UNPRICED_OPENING_METADATA_KEY == "unpriced_opening_ids"


class TestTheBinarySpecimen:
    def test_the_kanye_card_states_no_lifetime_move(self):
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [KANYE]})
        name, change, _ = _biggest_move_from_opening(
            [_leg(KANYE, "Yes", 0.94, 0.077)], m
        )
        assert name == "Yes"
        assert change is None, (
            f"a 0.94 opening off a 16c/96c book produced a {change} move"
        )

    def test_control_an_unlisted_opening_still_speaks(self):
        # The same leg with nothing listed — the pre-#8612 answer, unchanged.
        m = _Market({})
        _, change, opened_at = _biggest_move_from_opening(
            [_leg(KANYE, "Yes", 0.94, 0.077)], m
        )
        assert round(change, 3) == -0.863
        assert opened_at == OPENED

    def test_a_listing_for_another_leg_does_not_silence_this_one(self):
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [KANYE + 1]})
        _, change, _ = _biggest_move_from_opening(
            [_leg(KANYE, "Yes", 0.395, 0.065)], m
        )
        assert round(change, 3) == -0.33

    def test_a_yes_no_pair_refuses_the_affirmative_by_its_id(self):
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [1]})
        name, change, _ = _biggest_move_from_opening(
            [_leg(1, "Yes", 0.495, 0.865), _leg(2, "No", 0.505, 0.135)], m
        )
        assert (name, change) == ("Yes", None)


class TestTheBoard:
    def test_a_refused_biggest_mover_hands_the_sentence_to_a_real_one(self):
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [1]})
        name, change, _ = _biggest_move_from_opening(
            [_leg(1, "Boca Juniors", 0.95, 0.10),
             _leg(2, "Atletico Mineiro", 0.10, 0.449),
             _leg(3, "Racing", 0.20, 0.25)],
            m,
        )
        assert name == "Atletico Mineiro"
        assert round(change, 3) == 0.349

    def test_the_next_leg_must_clear_the_surprise_rung_itself(self):
        # The `*_surprise` reason licensing the sentence was raised by the
        # refused leg, so a sub-rung runner-up may not inherit it.
        m = _Market({UNPRICED_OPENING_METADATA_KEY: [1]})
        name, change, _ = _biggest_move_from_opening(
            [_leg(1, "Boca Juniors", 0.95, 0.10),
             _leg(2, "Racing", 0.20, 0.20 + MODERATE_SURPRISE_THRESHOLD / 2)],
            m,
        )
        assert (name, change) == (None, None)

    def test_control_with_nothing_listed_the_biggest_mover_still_wins(self):
        name, change, _ = _biggest_move_from_opening(
            [_leg(1, "Boca Juniors", 0.95, 0.10),
             _leg(2, "Racing", 0.20, 0.25)],
            _Market({}),
        )
        assert name == "Boca Juniors"
        assert round(change, 3) == -0.85


class TestTheSlice:
    def test_each_ten_minute_run_takes_the_next_twelfth(self):
        from app.tasks import OPENING_BOOK_SLICES, _opening_book_slice

        assert OPENING_BOOK_SLICES == 12
        assert [_opening_book_slice(t) for t in (0, 599, 600, 6600, 7200)] == [
            0, 0, 1, 11, 0,
        ]
