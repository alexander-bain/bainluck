"""Marquee-pinning tests (Queue #223 Item 2).

The pin pass moves in-progress, calendar-flagged marquee concepts/tournaments to
the very top, preserving everyone else's order, and NEVER empties the feed
(gotcha #42/#43 — the guard must be provable in both directions)."""

from app.routes.feed import _pin_marquee_items
from app.utils.majors_calendar import (
    calendar_entry_by_concept_key,
    load_calendar,
    marquee_concept_keys,
)


class TestPinPass:
    def test_pins_marquee_to_top(self):
        items = [
            {"type": "futures", "score": 99},
            {"type": "event", "score": 90},
            {"type": "concept", "score": 40, "_marquee_pin": True, "data": {"name": "TdF"}},
        ]
        out = _pin_marquee_items(items)
        assert out[0]["data"]["name"] == "TdF"
        assert [i["type"] for i in out] == ["concept", "futures", "event"]

    def test_no_pin_is_identity(self):
        items = [{"type": "futures", "score": 1}, {"type": "event", "score": 2}]
        assert _pin_marquee_items(items) == items

    def test_multiple_pins_preserve_relative_order(self):
        items = [
            {"type": "futures", "score": 99},
            {"type": "concept", "score": 50, "_marquee_pin": True, "data": {"name": "A"}},
            {"type": "tournament", "score": 30, "_marquee_pin": True, "data": {"name": "B"}},
        ]
        out = _pin_marquee_items(items)
        assert [i["data"]["name"] for i in out[:2]] == ["A", "B"]
        assert out[2]["type"] == "futures"

    def test_never_empties_the_feed(self):
        # Even an all-pinned list stays fully populated (both directions guarded).
        items = [
            {"type": "concept", "_marquee_pin": True, "data": {}},
            {"type": "tournament", "_marquee_pin": True, "data": {}},
        ]
        assert len(_pin_marquee_items(items)) == 2
        # And a flood of non-pinned items survives untouched.
        big = [{"type": "futures", "score": i} for i in range(50)]
        assert len(_pin_marquee_items(big)) == 50

    def test_malformed_item_does_not_crash(self):
        # A missing _marquee_pin key is falsy; a bad item type is tolerated.
        items = [{"type": "futures"}, {"nonsense": True}]
        assert _pin_marquee_items(items) == items


class TestSharedCalendar:
    def test_marquee_keys_include_tdf(self):
        keys = marquee_concept_keys()
        assert "event:cycling:tour-de-france-2026" in keys

    def test_marquee_keys_exclude_null_concept_entries(self):
        # Super Bowl / March Madness etc. carry concept_key: null — not pinnable.
        keys = marquee_concept_keys()
        assert all(k for k in keys)  # no empty/None keys

    def test_entry_lookup_by_concept_key(self):
        by_key = calendar_entry_by_concept_key()
        tdf = by_key.get("event:cycling:tour-de-france-2026")
        assert tdf is not None and tdf["marquee"] is True

    def test_calendar_loads(self):
        assert len(load_calendar()) >= 5
