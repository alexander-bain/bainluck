"""#4775 / authority/104 — the schedules summary stops printing two different
"fetched" counts and calling them the same thing.

WHAT IS BROKEN. One payload, one sport, production 2026-09-10 12:0xZ:

    GET /api/admin/task-metrics?task=statpal_schedules
    {
      "terminal": "complete",
      "sports_asked": 1,
      "total_fixtures_fetched": 16,
      "sports": [{"sport": "americanfootball_nfl",
                  "fixtures_fetched": 374, "live_games": 16}]
    }

One sport asked, and the top-level total reads 16 while that sport's own count
reads 374. Neither number is a miscount: `total_fixtures` increments INSIDE the
`-1d/+7d` window filter, and the per-sport `fixtures_fetched` is everything the
venue served. The names are the defect — `total_fixtures_fetched` actually means
"fetched AND inside the sync window", and nothing in the payload says so.

WHY IT MATTERS ENOUGH TO PIN. This is the #2907 class one level up from the
venue: an operator diagnosing a quiet StatPal reads the top-level number first,
and `16` says the venue served 16 NFL rows on a day it served 374. The
coincidence that `live_games` is ALSO 16 makes the wrong reading look
corroborated. Gotcha #53's shape: the field is honest about a quantity nobody
asked for.

WHAT THIS FILE PINS. Both counts survive, under names that cannot be confused:
`total_fixtures_fetched` is the venue's own total and reconciles with the
per-sport rows; `total_fixtures_in_window` is the filtered one and says so. The
second group is the control that keeps the FILTER — a "fix" that simply stopped
filtering would satisfy the first group and break the pass.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.services import statpal_api


# `Event`/`Team` carry Postgres JSONB/ARRAY columns that sqlite cannot render as
# DDL. The repo's standing shim (see `test_statpal_schedules_zero_yield_2907`),
# so the rail below can create the real tables from the real models. Without it
# every test in this file fails on the DDL and the red says nothing about the
# defect — a vacuous red is not a red (gotcha #124's cousin).
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


def _wire_one_sport(monkeypatch, sport_key="americanfootball_nfl"):
    """The smallest DB rail the pass will run against: one `Sport` row.

    Mirrors `test_statpal_schedules_zero_yield_2907.py` deliberately — this
    file's subject is the COUNTERS, not row writing, and every fixture it
    serves lands on a branch that writes nothing.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.models import Base, Event, Sport, Team, TeamIdentityMapping

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__,
            Team.__table__, TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    session.add(Sport(key=sport_key, name=sport_key))
    session.commit()

    class _AsyncShim:
        def __init__(self, s):
            self._s = s

        async def execute(self, *a, **kw):
            return self._s.execute(*a, **kw)

        async def flush(self, *a, **kw):
            return self._s.flush(*a, **kw)

        async def commit(self):
            return self._s.commit()

        async def rollback(self):
            return self._s.rollback()

        def add(self, obj):
            return self._s.add(obj)

        def __getattr__(self, name):
            return getattr(self._s, name)

    class _Ctx:
        async def __aenter__(self):
            return _AsyncShim(session)

        async def __aexit__(self, exc_type, *_):
            if exc_type:
                session.rollback()
            return False

    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session


def _fixture(idx, start_time):
    """A well-formed fixture. Every one of these is in the PAST with no event
    row behind it, so the pass counts it and then skips it — the counters are
    exercised without the create path being reachable at all.
    """
    return statpal_api.StatPalFixture(
        fixture_id=f"sp-{idx}",
        home_team=f"Home {idx}",
        away_team=f"Away {idx}",
        start_time=start_time,
    )


def _stub_venue_serving(monkeypatch, fixtures):
    """A StatPal that serves exactly `fixtures` on the schedule read."""
    class _Service:
        async def get_fixtures_result(self, sport, *a, **k):
            return statpal_api.StatPalFixtureFetch(
                list(fixtures), "ok", sport, "season-schedule"
            )

        async def get_fixtures(self, *a, **k):
            return (await self.get_fixtures_result(*a, **k)).fixtures

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            pass

    monkeypatch.setattr(statpal_api, "StatPalAPIService", _Service)
    monkeypatch.setattr(statpal_api, "is_available", lambda: True)


def _served_split():
    """Two fixtures inside the `-1d/+7d` window, three far outside it.

    The out-of-window rows sit in the PAST (60 and 90 days back) rather than the
    future so that no arm of the pass can reach the registry: the split has to
    be visible in the counters alone.
    """
    now = datetime.now(timezone.utc)
    inside = [
        _fixture(1, now - timedelta(hours=2)),
        _fixture(2, now - timedelta(hours=20)),
    ]
    outside = [
        _fixture(3, now - timedelta(days=60)),
        _fixture(4, now - timedelta(days=75)),
        _fixture(5, now - timedelta(days=90)),
    ]
    return inside + outside


class TestTheTwoFetchedCountsCannotDisagree:

    @pytest.fixture(autouse=True)
    def _no_pacing(self, monkeypatch):
        async def _sleep(_s):
            return None

        monkeypatch.setattr("app.tasks.statpal_sync.asyncio.sleep", _sleep)

    @pytest.mark.asyncio
    async def test_the_top_level_fetched_total_reconciles_with_the_per_sport_rows(
        self, monkeypatch
    ):
        """The defect, stated as arithmetic: two keys in one payload both read
        "fetched", and before this they differed by the window. 374 and 16 was
        the production reading; 5 and 2 is the same shape in miniature."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, _served_split())

        result = await _sync_statpal_schedules("americanfootball_nfl")

        per_sport = sum(d["fixtures_fetched"] for d in result["sports"])
        assert per_sport == 5
        assert result["total_fixtures_fetched"] == per_sport

    @pytest.mark.asyncio
    async def test_the_windowed_count_is_still_reported_and_names_its_window(
        self, monkeypatch
    ):
        """Nothing is lost. The filtered number an operator actually wants when
        asking "how many did this pass consider" is still there, under a name
        that says which pool it counted — the same rule #4732 landed on the
        standings rank."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, _served_split())

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["total_fixtures_in_window"] == 2

    @pytest.mark.asyncio
    async def test_the_window_still_filters(self, monkeypatch):
        """THE CONTROL, and the reason the group above is not enough on its
        own: deleting the `-1d/+7d` filter would make the two totals agree at 5
        and pass the first test, while sending sixty-day-old fixtures down the
        enrich path every night. The windowed count must stay STRICTLY below
        the fetched total on this input."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, _served_split())

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["total_fixtures_in_window"] < result["total_fixtures_fetched"]

    @pytest.mark.asyncio
    async def test_a_pass_where_everything_is_in_window_reports_both_equal(
        self, monkeypatch
    ):
        """The other control: when the window excludes nothing the two numbers
        AGREE. A repair that hard-coded a difference — or that reported the
        window count as a fraction of something — would fail here."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        now = datetime.now(timezone.utc)
        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, [
            _fixture(1, now - timedelta(hours=2)),
            _fixture(2, now - timedelta(hours=6)),
        ])

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["total_fixtures_fetched"] == 2
        assert result["total_fixtures_in_window"] == 2

    @pytest.mark.asyncio
    async def test_a_quiet_board_reports_zero_on_both_and_neither_key_is_absent(
        self, monkeypatch
    ):
        """Zero is a reading, not an absence — the standing rule this task's
        summary already applies to `fetch_failures` and `sports_unasked`. An
        absent key would make "the venue served nothing" indistinguishable from
        "this build does not report it"."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, [])

        result = await _sync_statpal_schedules("americanfootball_nfl")

        assert result["total_fixtures_fetched"] == 0
        assert result["total_fixtures_in_window"] == 0

    @pytest.mark.asyncio
    async def test_a_details_row_that_was_never_asked_does_not_break_the_total(
        self, monkeypatch
    ):
        """The trap this repair walked into, pinned so nobody walks back in.

        `details` does not hold one shape. The #4710 arm appends
        `{"sport": …, "status": "sport_not_found"}` for a mapped sport with no
        row — no `fixtures_fetched`, because nothing was asked. Deriving the
        top-level total with `d["fixtures_fetched"]` therefore raised
        `KeyError` and killed the ALL-SPORTS pass, which is the only form that
        reaches that arm. A sport nobody asked about contributes nothing to a
        count of what the venue served; it must not contribute an exception.
        """
        from app.tasks.statpal_sync import _sync_statpal_schedules

        # An invented map, for `test_statpal_sport_not_found_unasked_4710`'s
        # reason: the last live `sport_not_found` specimen (`golf_pga`) is being
        # retired by #4691, and a guard that sources its sports from the
        # production config would go green on the day that lands while
        # measuring nothing.
        rowed, unrowed = "americanfootball_nfl", "fictional_sport_with_no_row_4775"
        monkeypatch.setattr(
            "app.tasks.statpal_sync.STATPAL_SPORT_MAPPING",
            {rowed: "nfl", unrowed: "golf"},
        )
        _wire_one_sport(monkeypatch, sport_key=rowed)
        _stub_venue_serving(monkeypatch, _served_split())

        # The ALL-SPORTS form — no `sport_key` — because that is the only form
        # that reaches the `sport_not_found` arm at all.
        result = await _sync_statpal_schedules()

        assert any(d.get("status") == "sport_not_found" for d in result["sports"]), (
            "the specimen did not arrive: without an unasked details row this "
            "test cannot see the defect it exists for"
        )
        assert result["total_fixtures_fetched"] == 5
        assert result["total_fixtures_in_window"] == 2

    @pytest.mark.asyncio
    async def test_no_two_keys_in_the_payload_read_fetched_while_disagreeing(
        self, monkeypatch
    ):
        """#4775's acceptance bullet, asserted as the general rule rather than
        on the one pair that prompted it: whatever else the summary grows, two
        keys whose names both end in `fetched` may not disagree."""
        from app.tasks.statpal_sync import _sync_statpal_schedules

        _wire_one_sport(monkeypatch)
        _stub_venue_serving(monkeypatch, _served_split())

        result = await _sync_statpal_schedules("americanfootball_nfl")

        top_level = {
            k: v for k, v in result.items()
            if k.endswith("fixtures_fetched") and isinstance(v, int)
        }
        per_sport = sum(d["fixtures_fetched"] for d in result["sports"])
        assert top_level, "the fetched total must still be reported"
        assert set(top_level.values()) == {per_sport}, (
            f"keys reading 'fetched' disagree with the per-sport rows: "
            f"{top_level} vs {per_sport}"
        )
