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
    _as_utc_date,
    calendar_entry_by_concept_key,
    fixture_marquee_pinned,
    load_calendar,
    marquee_concept_keys,
    marquee_fixture_entries,
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
                # `game_clock` alongside `home_team_data` for the same reason
                # the logo is here: this case is about the marquee keeping the
                # top slot, so the game beneath it has to be one the lead is
                # allowed to promote at all (#4872's substance bar).
                "data": {
                    "status": "live",
                    "home_team_data": {"logo": "x"},
                    "game_clock": "60'",
                    "name": "game",
                },
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


class TestFixturePinWindow:
    """#4541: a marquee GAME pins its own event card.

    The concept pin above can only ever reach a ``type: "concept"`` card, so the
    Sports tab had no way to lead with a fixture: the NFL season opener scored 66
    against 98s and sat at rank 30 seven minutes after kickoff, because the
    scoring model reads drama and a 0-0 first quarter has none.

    Synthetic entries, so these assertions do not rot as real dates pass. The
    tail is anchored on the game's OWN kickoff rather than the calendar day —
    a day-anchored tail would hold a 00:20 UTC kickoff at the top of the tab for
    thirteen hours after the final whistle.
    """

    KICKOFF = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
    ENTRIES = [
        {
            "name": "Test Kickoff Game",
            "marquee": True,
            "fixture": {"sport_key": "americanfootball_nfl"},
            "start": "2026-09-10",
            "end": "2026-09-10",
        }
    ]

    def _pinned(self, now, sport_key="americanfootball_nfl", commence=None):
        return fixture_marquee_pinned(
            sport_key,
            self.KICKOFF if commence is None else commence,
            now,
            entries=self.ENTRIES,
        )

    def test_pinned_at_the_reported_49_minutes_before_kickoff(self):
        """CERT-2432's required repair, and #4541's own headline specimen.

        The issue was filed on the opener buried at **23:31Z, 49 minutes before
        the 00:20Z kickoff** — which is 29 minutes before the kickoff's UTC
        midnight. The first version of this window opened at the `start` day's
        00:00 UTC, so it missed the exact measurement the issue exists for. A US
        primetime game belongs to the next UTC day, so a midnight-anchored lead
        opens LATE, not early.

        Both ends of the window are now anchored on the kickoff and no calendar
        midnight appears in the maths.
        """
        assert self._pinned(datetime(2026, 9, 9, 23, 31, tzinfo=timezone.utc)) is True

    def test_pinned_before_kickoff_same_utc_day(self):
        # The tab must lead with it BEFORE it starts, not only once it is live.
        assert self._pinned(datetime(2026, 9, 10, 0, 5, tzinfo=timezone.utc)) is True

    def test_lead_boundary_is_half_open(self):
        assert self._pinned(self.KICKOFF - timedelta(hours=6)) is True
        assert self._pinned(self.KICKOFF - timedelta(hours=6, minutes=1)) is False

    def test_the_window_does_not_key_on_the_calendar_day_at_either_end(self):
        """The general form of the CERT-2432 defect, stated once.

        A game kicking off just after midnight UTC and one kicking off just
        before it are the same game to a reader, and the pin must treat their
        T-49min identically. Under a day-anchored lead the first is unpinned and
        the second is pinned — the boundary would be an artefact of the clock,
        not of the fixture.
        """
        just_after_midnight = datetime(2026, 9, 10, 0, 20, tzinfo=timezone.utc)
        entries_before = [dict(self.ENTRIES[0], start="2026-09-09", end="2026-09-09")]
        just_before_midnight = datetime(2026, 9, 9, 23, 40, tzinfo=timezone.utc)

        after = fixture_marquee_pinned(
            "americanfootball_nfl",
            just_after_midnight,
            just_after_midnight - timedelta(minutes=49),
            entries=self.ENTRIES,
        )
        before = fixture_marquee_pinned(
            "americanfootball_nfl",
            just_before_midnight,
            just_before_midnight - timedelta(minutes=49),
            entries=entries_before,
        )
        assert after is before is True

    def test_pinned_while_live(self):
        assert self._pinned(self.KICKOFF + timedelta(minutes=7)) is True

    def test_still_pinned_inside_the_tail(self):
        assert self._pinned(self.KICKOFF + timedelta(hours=5)) is True

    def test_released_once_the_tail_expires(self):
        # Guard direction 2 — the pin must let go, or a finished game owns the tab.
        assert self._pinned(self.KICKOFF + timedelta(hours=6, minutes=1)) is False

    def test_tail_boundary_is_half_open(self):
        assert self._pinned(self.KICKOFF + timedelta(hours=6)) is False
        assert self._pinned(self.KICKOFF + timedelta(hours=5, minutes=59)) is True

    def test_not_pinned_the_afternoon_before(self):
        """The window still has a floor — it just is not midnight.

        This case used to read 23:00Z, chosen because it was before the kickoff
        day's UTC midnight. That made it a test OF the midnight anchor rather
        than of the floor, and CERT-2432 showed the anchor was the bug: 23:00Z is
        inside T-6h and is now correctly pinned. Re-pointed at a time that is
        genuinely outside the lead so the assertion means what its name says.
        """
        assert self._pinned(datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)) is False

    def test_next_days_game_in_the_same_league_is_not_pinned(self):
        # THE TRAP THIS EXISTS FOR: a sport_key match is not a fixture match. The
        # entry names one UTC day, and the following night's NFL game must not
        # inherit its pin.
        next_night = datetime(2026, 9, 11, 0, 35, tzinfo=timezone.utc)
        assert self._pinned(next_night + timedelta(minutes=25), commence=next_night) is False

    def test_another_sport_the_same_night_is_not_pinned(self):
        assert self._pinned(self.KICKOFF + timedelta(minutes=7), sport_key="baseball_mlb") is False

    def test_naive_datetimes_are_read_as_utc(self):
        assert (
            fixture_marquee_pinned(
                "americanfootball_nfl",
                self.KICKOFF.replace(tzinfo=None),
                (self.KICKOFF + timedelta(minutes=7)).replace(tzinfo=None),
                entries=self.ENTRIES,
            )
            is True
        )

    def test_missing_inputs_return_false_not_an_exception(self):
        # Called directly rather than through `_pinned`, whose `commence=None`
        # means "use the default kickoff" and so cannot express an absent one.
        now = self.KICKOFF + timedelta(minutes=7)
        assert fixture_marquee_pinned(None, self.KICKOFF, now, entries=self.ENTRIES) is False
        assert fixture_marquee_pinned(
            "americanfootball_nfl", None, now, entries=self.ENTRIES
        ) is False

    def test_unusable_entries_return_false_not_an_exception(self):
        # A bad calendar edit must never be able to crash or empty the feed.
        now = self.KICKOFF + timedelta(minutes=7)
        for bad in (
            {"marquee": True, "fixture": {"sport_key": "americanfootball_nfl"}},  # no dates
            {"marquee": True, "fixture": {"sport_key": "americanfootball_nfl"},
             "start": "not-a-date", "end": "2026-09-10"},
            {"marquee": True, "fixture": "americanfootball_nfl",  # not a mapping
             "start": "2026-09-10", "end": "2026-09-10"},
        ):
            assert fixture_marquee_pinned(
                "americanfootball_nfl", self.KICKOFF, now, entries=[bad]
            ) is False


class TestFixtureEntriesOnTheShippedCalendar:
    """Structural guards over whatever fixture entries the real calendar carries.

    Deliberately NOT "there is at least one fixture entry" — the NFL 2026 opener
    is a dated entry that will be removed when it is no longer knowable-future
    work, and a test demanding its permanent presence would turn routine calendar
    hygiene into a red build. These assert that every fixture entry that IS
    present is well-formed, which stays true forever and still catches the edit
    that matters.
    """

    def test_every_fixture_entry_is_well_formed(self):
        for entry in marquee_fixture_entries():
            fixture = entry["fixture"]
            assert isinstance(fixture, dict), entry.get("name")
            assert fixture.get("sport_key"), entry.get("name")
            start = _as_utc_date(entry.get("start"))
            end = _as_utc_date(entry.get("end"))
            assert start is not None, entry.get("name")
            assert end is not None, entry.get("name")
            assert start <= end, entry.get("name")

    def test_fixture_entries_are_marquee_only(self):
        assert all(e.get("marquee") for e in marquee_fixture_entries())

    def test_concept_pin_and_fixture_pin_do_not_overlap(self):
        # An entry is one or the other. A concept_key entry pins a concept card;
        # a fixture entry pins an event card. Carrying both would pin twice for
        # one occasion and put the same story at ranks 1 and 2.
        assert all(not e.get("concept_key") for e in marquee_fixture_entries())


class TestPinnedFixtureLeadsTheTab:
    """The end-to-end property: a pinned event card leads, and costs nothing."""

    def _feed(self):
        return [
            {"type": "futures", "score": 95, "data": {"name": "Super Bowl Winner"}},
            {"type": "event", "score": 98, "data": {"name": "routine MLB coin flip"}},
            {"type": "concept", "score": 80, "data": {"name": "Vuelta"}},
            {"type": "event", "score": 66, "_marquee_pin": True,
             "data": {"name": "NFL season opener"}},
            {"type": "event", "score": 91, "data": {"name": "finished MLB game"}},
        ]

    def test_low_scoring_marquee_game_leads_the_98s(self):
        out = pin_only(self._feed())
        assert out[0]["data"]["name"] == "NFL season opener"

    def test_nothing_is_dropped_or_duplicated(self):
        items = self._feed()
        out = pin_only(items)
        assert len(out) == len(items)
        assert sorted(i["data"]["name"] for i in out) == sorted(
            i["data"]["name"] for i in items
        )

    def test_everyone_elses_order_is_preserved(self):
        out = pin_only(self._feed())
        assert [i["data"]["name"] for i in out[1:]] == [
            "Super Bowl Winner",
            "routine MLB coin flip",
            "Vuelta",
            "finished MLB game",
        ]

    def test_no_score_is_touched(self):
        # The pin buys position, not points — the card still reads 66.
        out = pin_only(self._feed())
        assert out[0]["score"] == 66

    def test_unpinned_feed_is_returned_unchanged(self):
        items = self._feed()
        for i in items:
            i.pop("_marquee_pin", None)
        assert pin_only(items) == items
