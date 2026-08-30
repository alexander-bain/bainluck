"""UX-P169 — the golf page stops hiding what is coming up.

═══ THE DEFECT ═══

`/categories/golf` renders an "Upcoming" section gated on
`data.upcoming_events.length > 0`, so an empty list removes the section from the
page entirely. On 2026-08-29 that list was empty, and it was empty because the
backend built it from the `events` table filtered to `Sport.key ILIKE 'golf_%'`.

That pool is banked in this test's fixture. It has SIX rows in all of history,
every one `status='closed'` and in the past, and they are not tournaments:

    Phoenix Fuel Masters vs Timplados Hotshots   <- Philippine BASKETBALL
    Im vs oigawa                                 <- mis-ingested names
    seo vs Sim                                   <- mis-ingested names
    Europe Team Captain vs 2027 Ryder Cup        <- a prop
    Hole-in-One vs Arnold Palmer Invitational    <- a prop
    U.S. Team Captain vs 2027 Ryder Cup          <- a prop

So the section could only ever show nothing, or — had one of those rows been in
the future — nonsense. Meanwhile the DataGolf schedule, which knew about twenty
future tournaments with the nearest five days away, was already loaded by the
same request and already serialized into the same payload as `pga_schedule`,
with no consumer anywhere in the frontend or the app.

The Tour Championship, the only current event, ended 2026-08-30 — the day after
capture. From that day the page had nothing forward-looking on it at all.

═══ CLOCK DISCIPLINE (gotcha #44) ═══

Two different techniques, because the two layers need different ones:

  * The helper takes `now` as a PARAMETER, so tests over the real banked
    schedule pass a frozen literal (`frozen_now` in the fixture). No branch on
    the wall clock.
  * `get_golf` reads its own clock, so the end-to-end test builds its schedule
    by OFFSETTING from the real now — offset first, then assert. It is
    clock-independent by construction rather than by anchoring.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.routes.golf import _upcoming_from_schedule, _MAX_UPCOMING, get_golf

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "uxp169_golf_schedule.json").read_text()
)
SCHEDULE = FIXTURE["schedule"]
FROZEN_NOW = datetime.fromisoformat(FIXTURE["frozen_now"])


# ============================================================================
# The banked BEFORE is what we claim it is
# ============================================================================


class TestTheBankedBeforeIsWhatWeClaim:
    def test_the_section_was_empty_in_production(self):
        assert FIXTURE["served_before"]["upcoming_events"] == []

    def test_the_events_table_pool_is_six_closed_past_rows(self):
        pool = FIXTURE["events_table_pool"]
        assert len(pool) == 6, pool
        assert all(r["status"] == "closed" for r in pool), pool
        assert all(
            datetime.fromisoformat(r["commence_time"]) < FROZEN_NOW for r in pool
        ), pool

    def test_the_pool_the_old_code_drew_from_contains_a_basketball_game(self):
        """Not a rhetorical flourish — this is why the source had to change."""
        names = [
            f"{r['home_team_name']} vs {r['away_team_name']}"
            for r in FIXTURE["events_table_pool"]
        ]
        assert "Phoenix Fuel Masters vs Timplados Hotshots" in names, names

    def test_the_schedule_beside_it_knew_about_future_tournaments(self):
        future = [
            s
            for s in SCHEDULE
            if s.get("start_date")
            and datetime.fromisoformat(s["start_date"]) > FROZEN_NOW
        ]
        assert len(future) == 20, len(future)

    def test_the_only_current_event_ended_the_day_after_capture(self):
        assert FIXTURE["served_before"]["current_event_name"] == "Tour Championship"
        assert (
            FIXTURE["served_before"]["current_event_end_date"][:10] == "2026-08-30"
        )


# ============================================================================
# The helper
# ============================================================================


class TestTheSectionNamesWhatIsComing:
    @pytest.fixture
    def upcoming(self):
        return _upcoming_from_schedule(SCHEDULE, FROZEN_NOW)

    def test_it_is_no_longer_empty(self, upcoming):
        assert upcoming, "the whole ship is that this list is not empty"

    def test_it_names_the_next_tournament(self, upcoming):
        assert upcoming[0]["name"] == "Omega European Masters"
        assert upcoming[0]["start_date"][:10] == "2026-09-03"

    def test_every_entry_is_in_the_future(self, upcoming):
        assert all(
            datetime.fromisoformat(e["start_date"]) > FROZEN_NOW for e in upcoming
        )

    def test_a_completed_tournament_never_appears(self, upcoming):
        """The schedule is mostly the season already played."""
        names = [e["name"] for e in upcoming]
        assert "Sony Open in Hawaii" not in names, names
        assert "The Masters" not in names, names

    def test_it_is_bounded_for_display(self, upcoming):
        assert len(upcoming) == _MAX_UPCOMING


class TestTheOrderIsChronological:
    """⚠️ The schedule arrives GROUPED BY TOUR. This is the load-bearing sort."""

    def test_the_raw_schedule_really_is_out_of_order(self):
        """If this ever fails the sort has become untested, not unnecessary."""
        future = [
            s
            for s in SCHEDULE
            if s.get("start_date")
            and datetime.fromisoformat(s["start_date"]) > FROZEN_NOW
        ]
        raw = [s["start_date"] for s in future]
        assert raw != sorted(raw), "input is already sorted — this guard is vacuous"

    def test_the_served_order_is_chronological(self):
        dates = [
            e["start_date"] for e in _upcoming_from_schedule(SCHEDULE, FROZEN_NOW)
        ]
        assert dates == sorted(dates), dates

    def test_the_two_tours_are_interleaved_by_date_not_grouped(self):
        tours = [e["tour"] for e in _upcoming_from_schedule(SCHEDULE, FROZEN_NOW)]
        assert len(set(tours)) > 1, tours
        # grouped-by-tour would put every 'pga' before every 'dp_world'
        assert tours != sorted(tours, key=lambda t: (t or "")), tours


class TestEachRowCarriesWhatThePagePrints:
    @pytest.fixture
    def first(self):
        return _upcoming_from_schedule(SCHEDULE, FROZEN_NOW)[0]

    def test_it_carries_a_name_and_both_dates(self, first):
        assert first["name"]
        assert first["start_date"] and first["end_date"]

    def test_it_carries_somewhere_to_say(self, first):
        assert first["location"] == "Crans-Montana, Switzerland"

    def test_the_tour_label_reuses_the_shipped_mapping(self, first):
        """`euro` is DataGolf's code; the reader is owed 'DP World Tour'."""
        assert first["tour"] == "dp_world"
        assert first["tour_label"] == "DP World Tour"

    def test_a_pga_row_is_labelled_too(self):
        rows = _upcoming_from_schedule(SCHEDULE, FROZEN_NOW)
        pga = [e for e in rows if e["tour"] == "pga"]
        assert pga, rows
        assert pga[0]["tour_label"] == "PGA Tour"


class TestItDegradesQuietly:
    def test_no_schedule_is_an_empty_list_not_a_crash(self):
        assert _upcoming_from_schedule(None, FROZEN_NOW) == []
        assert _upcoming_from_schedule([], FROZEN_NOW) == []

    def test_an_entry_with_no_start_date_is_skipped(self):
        assert _upcoming_from_schedule([{"name": "x", "key": "x"}], FROZEN_NOW) == []

    def test_an_unparseable_start_date_is_skipped_not_raised(self):
        bad = [{"name": "x", "key": "x", "start_date": "not-a-date"}]
        assert _upcoming_from_schedule(bad, FROZEN_NOW) == []

    def test_a_naive_start_date_does_not_raise(self):
        soon = (FROZEN_NOW + timedelta(days=3)).replace(tzinfo=None).isoformat()
        out = _upcoming_from_schedule(
            [{"name": "x", "key": "x", "start_date": soon}], FROZEN_NOW
        )
        assert len(out) == 1

    def test_an_unknown_tour_code_leaves_the_label_absent_not_wrong(self):
        soon = (FROZEN_NOW + timedelta(days=3)).isoformat()
        out = _upcoming_from_schedule(
            [{"name": "x", "key": "x", "start_date": soon, "tour": "quidditch"}],
            FROZEN_NOW,
        )
        assert out[0]["tour"] is None
        assert out[0]["tour_label"] is None


# ============================================================================
# The real route — so deleting the CALL SITE goes red, not just the helper
# ============================================================================


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _Session:
    async def execute(self, *_args, **_kwargs):
        return _Result([])


def _offset_schedule():
    """Built by OFFSETTING from the real clock — see the module docstring."""
    now = datetime.now(timezone.utc)
    return [
        {
            "name": "Yesterday Invitational",
            "key": "yesterday_invitational",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": now.isoformat(),
            "venue": "Old Course",
            "location": "Past, XX",
            "tour": "pga",
        },
        {
            "name": "Later Championship",
            "key": "later_championship",
            "start_date": (now + timedelta(days=30)).isoformat(),
            "end_date": (now + timedelta(days=33)).isoformat(),
            "venue": "Late Club",
            "location": "Later, YY",
            "tour": "euro",
        },
        {
            "name": "Sooner Open",
            "key": "sooner_open",
            "start_date": (now + timedelta(days=5)).isoformat(),
            "end_date": (now + timedelta(days=8)).isoformat(),
            "venue": "Soon Links",
            "location": "Sooner, ZZ",
            "tour": "pga",
        },
    ]


@pytest.fixture
def served(monkeypatch):
    """Drive the real `get_golf` with a schedule and no markets."""

    async def _schedule():
        return _offset_schedule()

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _schedule)

    import asyncio

    return asyncio.run(get_golf(_Session()))


class TestTheServedGolfPage:
    def test_the_route_serves_the_upcoming_tournaments(self, served):
        """Deleting the call site in `get_golf` turns this red."""
        assert served["upcoming_events"], served["upcoming_events"]

    def test_the_route_does_not_serve_a_tournament_already_underway(self, served):
        names = [e["name"] for e in served["upcoming_events"]]
        assert "Yesterday Invitational" not in names, names

    def test_the_route_serves_them_soonest_first(self, served):
        names = [e["name"] for e in served["upcoming_events"]]
        assert names == ["Sooner Open", "Later Championship"], names

    def test_the_route_no_longer_reads_the_events_table(self, served):
        """The old shape's keys are gone; the new ones are present."""
        row = served["upcoming_events"][0]
        assert "id" not in row and "commence_time" not in row, row
        assert {"name", "start_date", "end_date", "tour_label"} <= set(row), row
