"""Marquee-pinning tests (Queue #223 Item 2).

The pin pass moves in-progress, calendar-flagged marquee concepts/tournaments to
the very top, preserving everyone else's order, and NEVER empties the feed
(gotcha #42/#43 — the guard must be provable in both directions).

C185: the pin is no longer its own pass. `_pin_marquee_items` was one of two
prefix-writers whose sequential composition let a live game displace the pinned
marquee, so it was folded into `compose_lead` as the FIRST slice and deleted.
These tests now exercise that slice directly, with the tonight's-games prefix
switched off — which is exactly the old pass's behaviour, so the guarantees
below are unchanged rather than merely re-expressed. The cases where the two
prefixes INTERACT (the actual defect) live in
`tests/evals/test_discover_lead_order_contract.py`, bound to C185's corpus."""

from datetime import datetime, timedelta, timezone

from app.utils.tonights_games import compose_lead
from app.utils.majors_calendar import (
    calendar_entry_by_concept_key,
    load_calendar,
    marquee_concept_keys,
    marquee_pin_state,
)


def pin_only(items):
    """The marquee prefix in isolation — the old `_pin_marquee_items` exactly."""
    return compose_lead(items, include_tonights_games=False)


class TestPinPass:
    def test_pins_marquee_to_top(self):
        items = [
            {"type": "futures", "score": 99},
            {"type": "event", "score": 90},
            {"type": "concept", "score": 40, "_marquee_pin": True, "data": {"name": "TdF"}},
        ]
        out = pin_only(items)
        assert out[0]["data"]["name"] == "TdF"
        assert [i["type"] for i in out] == ["concept", "futures", "event"]

    def test_no_pin_is_identity(self):
        items = [{"type": "futures", "score": 1}, {"type": "event", "score": 2}]
        assert pin_only(items) == items

    def test_multiple_pins_preserve_relative_order(self):
        items = [
            {"type": "futures", "score": 99},
            {"type": "concept", "score": 50, "_marquee_pin": True, "data": {"name": "A"}},
            {"type": "tournament", "score": 30, "_marquee_pin": True, "data": {"name": "B"}},
        ]
        out = pin_only(items)
        assert [i["data"]["name"] for i in out[:2]] == ["A", "B"]
        assert out[2]["type"] == "futures"

    def test_never_empties_the_feed(self):
        # Even an all-pinned list stays fully populated (both directions guarded).
        items = [
            {"type": "concept", "_marquee_pin": True, "data": {}},
            {"type": "tournament", "_marquee_pin": True, "data": {}},
        ]
        assert len(pin_only(items)) == 2
        # And a flood of non-pinned items survives untouched.
        big = [{"type": "futures", "score": i} for i in range(50)]
        assert len(pin_only(big)) == 50

    def test_malformed_item_does_not_crash(self):
        # A missing _marquee_pin key is falsy; a bad item type is tolerated.
        items = [{"type": "futures"}, {"nonsense": True}]
        assert pin_only(items) == items

    def test_marquee_still_leads_when_the_games_prefix_is_ON(self):
        """C185's regression pin, at this suite's own altitude.

        The old pass was correct in isolation and wrong in composition, so a
        suite that only ever ran it in isolation could not have caught the
        defect. This case is the reason the file is not purely a rename.
        """
        items = [
            {"type": "futures", "score": 99},
            {
                "type": "event",
                "score": 35,
                "data": {"status": "live", "home_team_data": {"logo": "x"}, "name": "game"},
            },
            {"type": "concept", "score": 40, "_marquee_pin": True, "data": {"name": "TdF"}},
        ]
        out = compose_lead(items, include_tonights_games=True)
        assert out[0]["data"]["name"] == "TdF"
        assert out[1]["data"]["name"] == "game"


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


class TestMarqueePinWindow:
    """#235 Item 4: the T+36h post-settlement WHAT-HIT pin window.

    Uses a synthetic single-entry calendar so the assertions don't drift as real
    dates pass. Settlement = midnight UTC after the ``end`` day."""

    KEY = "event:test:marquee"
    ENTRIES = {
        KEY: {
            "concept_key": KEY,
            "marquee": True,
            "start": "2026-07-04",
            "end": "2026-07-26",  # settlement anchor = 2026-07-27 00:00 UTC
        },
        "event:test:not-marquee": {
            "concept_key": "event:test:not-marquee",
            "marquee": False,
            "start": "2026-07-04",
            "end": "2026-07-26",
        },
    }
    SETTLEMENT = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)

    def _state(self, now):
        return marquee_pin_state(self.KEY, now, entries=self.ENTRIES)

    def test_live_during_event(self):
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        assert self._state(now) == "live"

    def test_live_on_finish_day(self):
        # The whole end day still reads live (the finish happens that afternoon).
        now = datetime(2026, 7, 26, 17, 0, tzinfo=timezone.utc)
        assert self._state(now) == "live"

    def test_still_pinned_at_t_plus_12h(self):
        now = self.SETTLEMENT + timedelta(hours=12)
        assert self._state(now) == "whathit"  # guard direction 1: still pinned

    def test_gone_by_t_plus_48h(self):
        now = self.SETTLEMENT + timedelta(hours=48)
        assert self._state(now) is None  # guard direction 2: dropped

    def test_boundary_at_36h_is_inclusive_exclusive(self):
        # Exactly at +36h the window has closed (half-open [settlement, +36h)).
        assert self._state(self.SETTLEMENT + timedelta(hours=36)) is None
        assert self._state(self.SETTLEMENT + timedelta(hours=35, minutes=59)) == "whathit"

    def test_before_event_is_none(self):
        now = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
        assert self._state(now) is None

    def test_non_marquee_never_pins(self):
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        assert marquee_pin_state("event:test:not-marquee", now, entries=self.ENTRIES) is None

    def test_unknown_key_is_none(self):
        now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
        assert marquee_pin_state("event:test:absent", now, entries=self.ENTRIES) is None

    def test_naive_now_is_treated_as_utc(self):
        now = datetime(2026, 7, 20, 12, 0)  # naive
        assert self._state(now) == "live"

    def test_real_tdf_entry_resolves(self):
        # Against the live calendar, the TdF concept keys have a valid marquee entry.
        entries = calendar_entry_by_concept_key()
        during = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
        assert marquee_pin_state(
            "event:cycling:tour-de-france-2026", during, entries=entries
        ) == "live"
