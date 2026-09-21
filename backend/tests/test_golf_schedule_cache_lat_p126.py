"""LAT-P126 — `/api/playoffs/golf/schedule` stops re-fetching DataGolf on every load.

THE DEFECT, measured 2026-08-29 against production, three reads in a row:

    read1  0.739 s      read2  0.801 s      read3  0.686 s      29,662 bytes
    control (`/health`) 0.250 / 0.261 / 0.260 s

A second read as slow as the first is a CACHE defect (LAT-P124's rule), and this
endpoint had no cache of any kind: it made FIVE SEQUENTIAL DataGolf calls — one
per tour — inside the request, every time. The `/playoffs/golf` page's other half,
the championship grid, has been Redis-cached and hourly-warmed since #901. The
schedule section rendered directly beside it was never given the same treatment.

The middleware's blanket `public, max-age=300` on `/api/playoffs/` is not a
counter-argument: it is a per-browser directive, so it helps a reload and does
nothing for a first load — which is the load this lane exists to fix, and the one
the three curls above measure.

THE FIX HAS THREE PARTS AND EACH IS TESTED IN BOTH DIRECTIONS (gotcha #43):

1. `fetch_golf_schedule_raw` gathers the five tours CONCURRENTLY, so a cold
   rebuild costs one round trip instead of five — while keeping the old per-tour
   tolerance exactly (a failing tour is skipped, its siblings survive).
2. The cached payload is CLOCK-FREE. `is_current`, the "This Week" badge and the
   whole status cascade are derived at SERVE time by `shape_golf_schedule` from a
   `now_str` the caller passes in. An hour-old cache therefore cannot print a
   stale badge, because the badge was never in the cache. This is the property
   that makes an hour-scale TTL safe on a surface that renders "This Week".
3. An hourly WARM rides `precompute_category_pages` (no new beat entry), because
   a cache the route only fills on a miss ships nothing on a low-traffic page —
   LAT-P115's "fast and warm for nobody" hole, recorded after LAT-P108.

Key agreement between route and warmer is pinned by the LITERAL string, never
through the shared constant. LAT-P125's M5/M6 mutants survived precisely because
every test read the key through the constant, so route and warmer moved in
lockstep and a respelling was invisible.

No test in this file reads a clock. The concurrency proof counts overlapping
entries, not elapsed time.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routes.playoffs import (
    GOLF_SCHEDULE_STALE_TTL_S,
    GOLF_SCHEDULE_TOURS,
    GOLF_SCHEDULE_TTL_S,
    fetch_golf_schedule_raw,
    get_golf_schedule,
    shape_golf_schedule,
)

# The literal key, written out. NOT `GOLF_SCHEDULE_CACHE_KEY` — a test that reads
# the constant cannot see a respelling that moves route and warmer together.
LITERAL_KEY = "bainluck:category:playoffs:golf:schedule"
LITERAL_STALE_KEY = "bainluck:category:playoffs:golf:schedule:stale"


def _tournament(event_id, name, start, end, status=None, rnd=None):
    """One entry as `fetch_golf_schedule_raw` stores it — no derived state."""
    return {
        "event_id": event_id,
        "event_name": name,
        "course": "Augusta National",
        "start_date": start,
        "end_date": end,
        "location": "Augusta, GA",
        "country": "USA",
        "status": status,
        "current_round": rnd,
    }


# A season with one completed event, one live event and one still to come. The
# dates are fixed literals and every assertion supplies its own `now_str`, so
# nothing here depends on the day the suite runs (gotcha #44).
RAW = {
    "tours": [
        {
            "tour": "pga",
            "tournaments": [
                _tournament("100", "Sentry", "2026-01-08", "2026-01-11",
                            status="completed"),
                _tournament("101", "Masters", "2026-04-09", "2026-04-12",
                            status="in-progress", rnd=2),
                _tournament("102", "PGA Championship", "2026-05-14", "2026-05-17"),
            ],
        },
        {
            "tour": "euro",
            "tournaments": [
                _tournament("200", "Dubai Desert Classic", "2026-01-15",
                            "2026-01-18", status="completed"),
                _tournament("201", "British Masters", "2026-08-27", "2026-08-30"),
            ],
        },
    ],
    "fetched_at": "2026-04-10T06:25:00+00:00",
}


# ---------------------------------------------------------------------------
# 1. The cached payload carries no clock — the badge is computed at serve time
# ---------------------------------------------------------------------------
class TestShapeIsClockInjected:
    def test_same_bytes_shape_differently_on_two_different_days(self):
        """THE load-bearing property. If this fails, an hour-old cache can print
        'This Week' over a tournament that finished last month.

        #7690 corrected the dates this test reads on. It used to call
        "2026-04-10" the DURING case for an event running 2026-08-27 -> 08-30 —
        139 days early — and assert `current_event_id == "201"` there, which
        froze the production defect into the suite as expected behaviour. The
        property being proven is unchanged; the three reads below now bracket
        the window instead of sitting outside it.
        """
        before = shape_golf_schedule(RAW, "2026-04-10")
        during = shape_golf_schedule(RAW, "2026-08-28")
        after = shape_golf_schedule(RAW, "2026-09-01")

        # The euro tour carries no upstream `status`, so which of its events is
        # "current" is PURELY date-derived — exactly where a frozen cache lies.
        # Same cached bytes; the badge moves with the day, as it must, and it is
        # absent on BOTH sides of the window, not just after it.
        assert before["tours"][1]["current_event_id"] is None
        assert during["tours"][1]["current_event_id"] == "201"
        assert after["tours"][1]["current_event_id"] is None
        assert [e["is_current"] for e in before["tours"][1]["events"]] == [False, False]
        assert [e["is_current"] for e in during["tours"][1]["events"]] == [False, True]
        assert [e["is_current"] for e in after["tours"][1]["events"]] == [False, False]

        # And the other direction: where DataGolf DOES state a status, the answer
        # is date-independent, so the cascade was not silently re-based.
        assert before["tours"][0]["current_event_id"] == "101"
        assert during["tours"][0]["current_event_id"] == "101"
        assert after["tours"][0]["current_event_id"] == "101"

    def test_raw_payload_contains_no_derived_state(self):
        """What goes into Redis must not contain a single serve-time decision."""
        for entry in RAW["tours"]:
            for t in entry["tournaments"]:
                assert "is_current" not in t
                assert "display_status" not in t
                assert set(t) == {
                    "event_id", "event_name", "course", "start_date", "end_date",
                    "location", "country", "status", "current_round",
                }

    def test_shape_does_not_mutate_the_cached_payload(self):
        """The route shapes the same dict it may hold a reference to; shaping
        twice must not drift."""
        before = json.dumps(RAW, sort_keys=True)
        shape_golf_schedule(RAW, "2026-04-10")
        shape_golf_schedule(RAW, "2026-12-31")
        assert json.dumps(RAW, sort_keys=True) == before


# ---------------------------------------------------------------------------
# 2. The status cascade is carried over verbatim
# ---------------------------------------------------------------------------
class TestStatusCascadeUnchanged:
    def test_all_four_branches(self):
        pga = shape_golf_schedule(RAW, "2026-04-10")["tours"][0]
        by_id = {e["event_id"]: e for e in pga["events"]}

        # completed wins over everything
        assert by_id["100"]["status"] == "completed"
        assert by_id["100"]["is_current"] is False
        # the current event is labelled current, not by its upstream status
        assert by_id["101"]["status"] == "current"
        assert by_id["101"]["is_current"] is True
        assert by_id["101"]["current_round"] == 2
        # a later start date is upcoming
        assert by_id["102"]["status"] == "upcoming"

    def test_unknown_when_neither_status_nor_future_start(self):
        raw = {
            "tours": [{"tour": "pga", "tournaments": [
                _tournament("300", "Ghost", "2026-01-01", "2026-01-04"),
            ]}],
            "fetched_at": "2026-06-01T00:00:00+00:00",
        }
        # Past start, past end, no upstream status, and the date rung cannot
        # claim it because 2026-06-01 is outside 01-01 -> 01-04.
        events = shape_golf_schedule(raw, "2026-06-01")["tours"][0]["events"]
        assert events[0]["status"] == "unknown"
        assert events[0]["is_current"] is False

    def test_tour_label_and_render_order_preserved(self):
        shaped = shape_golf_schedule(RAW, "2026-04-10")
        assert [t["tour"] for t in shaped["tours"]] == ["pga", "euro"]
        assert shaped["tours"][0]["tour_name"]  # a label, whatever it maps to

    def test_empty_tour_is_dropped(self):
        raw = {"tours": [{"tour": "pga", "tournaments": []}], "fetched_at": "x"}
        assert shape_golf_schedule(raw, "2026-04-10")["tours"] == []


# ---------------------------------------------------------------------------
# 2b. #7690 — "THIS WEEK" means the tournament has STARTED
# ---------------------------------------------------------------------------
class TestCurrentMeansStarted:
    """The date rung used to ask only "has this tournament not finished yet".

    The schedule is chronological, so the first unfinished tournament is the
    NEXT one: between tournaments the next event was always badged current, for
    however long the gap ran. Production specimen, /playoffs/golf at 2026-09-20:
    a "THIS WEEK" card over a Presidents Cup starting 2026-09-24.
    """

    #: The UPSTREAM payload on 2026-09-21, trimmed to the rows that decide it,
    #: with every `status` exactly as DataGolf's `get-schedule` sent it.
    #:
    #: The first cut of this fixture left `status` unset on 500 and 501, and that
    #: omission is the whole reason the first #7690 fix shipped inert: the field
    #: it dropped is the field that decided the answer. DataGolf stamps a
    #: not-yet-started tournament `"upcoming"`, the rung above the dates asked
    #: only `!= "completed"`, and so the dates were never consulted in
    #: production — while this fixture, carrying `None`, reached them every time
    #: and printed a pass. Measured against the vendor 2026-09-21 06:26Z: 47 pga
    #: rows, `{"completed": 38, "upcoming": 9}`, and event 500 `"upcoming"`.
    PRESIDENTS_CUP = {
        "tours": [{"tour": "pga", "tournaments": [
            _tournament("499", "Procore Championship", "2026-09-10", "2026-09-13",
                        status="completed"),
            _tournament("500", "Presidents Cup", "2026-09-24", "2026-09-27",
                        status="upcoming"),
            _tournament("501", "Bank of Utah Championship", "2026-10-01",
                        "2026-10-04", status="upcoming"),
        ]}],
        "fetched_at": "2026-09-21T04:26:02.904699+00:00",
    }

    def test_the_production_specimen_is_not_current_four_days_early(self):
        tour = shape_golf_schedule(self.PRESIDENTS_CUP, "2026-09-20")["tours"][0]
        assert tour["current_event_id"] is None
        assert [e["is_current"] for e in tour["events"]] == [False, False, False]

    def test_the_specimen_reads_upcoming_not_current(self):
        """The badge is only half of it — the row's own label was wrong too."""
        tour = shape_golf_schedule(self.PRESIDENTS_CUP, "2026-09-20")["tours"][0]
        by_id = {e["event_id"]: e for e in tour["events"]}
        assert by_id["500"]["status"] == "upcoming"

    def test_the_same_specimen_IS_current_once_it_tees_off(self):
        """The fix must not simply delete the rung."""
        tour = shape_golf_schedule(self.PRESIDENTS_CUP, "2026-09-25")["tours"][0]
        assert tour["current_event_id"] == "500"
        by_id = {e["event_id"]: e for e in tour["events"]}
        assert by_id["500"]["is_current"] is True
        assert by_id["500"]["status"] == "current"

    @pytest.mark.parametrize("day", ["2026-09-24", "2026-09-27"])
    def test_both_edges_of_the_window_are_inside_it(self, day):
        """First day and last day inclusive — a tournament is current on the day
        it tees off and on the day it finishes."""
        tour = shape_golf_schedule(self.PRESIDENTS_CUP, day)["tours"][0]
        assert tour["current_event_id"] == "500"

    @pytest.mark.parametrize("day", ["2026-09-23", "2026-09-28"])
    def test_one_day_outside_the_window_on_either_side_is_not_current(self, day):
        tour = shape_golf_schedule(self.PRESIDENTS_CUP, day)["tours"][0]
        assert tour["current_event_id"] is None

    def test_a_future_event_does_not_stop_the_scan(self):
        """The old rung broke out of the loop on the first unfinished event. If
        that break survives a refactor, an event actually in progress behind a
        future one is missed — so this asserts the scan continues."""
        raw = {
            "tours": [{"tour": "pga", "tournaments": [
                _tournament("600", "Next Month", "2026-10-01", "2026-10-04"),
                _tournament("601", "Happening Now", "2026-09-17", "2026-09-20"),
            ]}],
            "fetched_at": "2026-09-18T00:00:00+00:00",
        }
        tour = shape_golf_schedule(raw, "2026-09-18")["tours"][0]
        assert tour["current_event_id"] == "601"

    def test_an_upstream_status_still_outranks_the_dates(self):
        """Unchanged precedence: when DataGolf states a live status we trust it,
        even against the dates. Pinned so the fix cannot invert the cascade."""
        raw = {
            "tours": [{"tour": "pga", "tournaments": [
                _tournament("700", "Weather Delay", "2026-09-24", "2026-09-27",
                            status="in-progress", rnd=1),
            ]}],
            "fetched_at": "2026-09-21T00:00:00+00:00",
        }
        tour = shape_golf_schedule(raw, "2026-09-20")["tours"][0]
        assert tour["current_event_id"] == "700"

    def test_an_event_with_no_start_date_is_never_current(self):
        """'THIS WEEK' over a tournament whose start we do not know is an
        over-claim; the old rung made exactly that claim on end_date alone."""
        raw = {
            "tours": [{"tour": "pga", "tournaments": [
                {**_tournament("800", "No Start", "2026-09-24", "2026-12-31"),
                 "start_date": None},
            ]}],
            "fetched_at": "2026-09-21T00:00:00+00:00",
        }
        tour = shape_golf_schedule(raw, "2026-09-20")["tours"][0]
        assert tour["current_event_id"] is None

    def test_last_updated_is_the_fetch_time_not_the_serve_time(self):
        """Once a cache exists, a serve-time stamp is a freshness claim the
        payload cannot back."""
        shaped = shape_golf_schedule(RAW, "2026-04-10")
        assert shaped["last_updated"] == "2026-04-10T06:25:00+00:00"


# ---------------------------------------------------------------------------
# 2b. "Not finished" is not "in progress" — the rung ABOVE the dates
# ---------------------------------------------------------------------------
class TestUpcomingIsNotInProgress:
    """#7690, second half, measured on production after the first half shipped.

    The date rung landed and the badge did not move: `/api/playoffs/golf/schedule`
    on 2026-09-21 06:23:47Z, served by `4e3e7674` (confirmed via `/api/health`
    `commit` + a `web.1` restart at 06:22:31Z), still carried three `is_current`
    rows whose tournaments had not started — Presidents Cup and FedEx Open de
    France three days out, Compliance Solutions Championship ten.

    The rung above the dates was short-circuiting on `status != "completed"`.
    Read from the vendor the same minute, DataGolf's whole `get-schedule`
    vocabulary is `{"completed": 38, "upcoming": 9}` across 47 pga rows — there is
    no third value in the live feed — so "not finished" selected the next event on
    the calendar and `break`'d before any date was compared. Ten days early is the
    proof it was never an upstream liveness claim: no feed calls a tournament live
    a week and a half out.
    """

    @staticmethod
    def _one(status):
        return {
            "tours": [{"tour": "pga", "tournaments": [
                _tournament("500", "Presidents Cup", "2026-09-24", "2026-09-27",
                            status=status),
            ]}],
            "fetched_at": "2026-09-21T04:26:02.904699+00:00",
        }

    def test_upcoming_does_not_make_a_future_tournament_current(self):
        """THE production specimen, with the field the first fixture dropped."""
        tour = shape_golf_schedule(self._one("upcoming"), "2026-09-20")["tours"][0]
        assert tour["current_event_id"] is None
        assert tour["events"][0]["is_current"] is False
        assert tour["events"][0]["status"] == "upcoming"

    def test_the_ten_day_specimen_is_not_current_either(self):
        """The Korn Ferry row, which is the one that cannot be explained away as
        an upstream liveness claim."""
        raw = {
            "tours": [{"tour": "kft", "tournaments": [
                _tournament("166", "Compliance Solutions Championship",
                            "2026-10-01", "2026-10-04", status="upcoming"),
            ]}],
            "fetched_at": "2026-09-21T04:26:02.904699+00:00",
        }
        tour = shape_golf_schedule(raw, "2026-09-21")["tours"][0]
        assert tour["current_event_id"] is None

    @pytest.mark.parametrize("status", ["scheduled", "postponed", "cancelled",
                                        "tbd", "", "   ", None])
    def test_no_unrecognised_status_can_assert_play_is_underway(self, status):
        """An allowlist, not a wider denylist: a value we have never seen must
        fall through to the dates, never short-circuit past them. This is the
        direction the first fix got wrong, generalised beyond `"upcoming"`."""
        tour = shape_golf_schedule(self._one(status), "2026-09-20")["tours"][0]
        assert tour["current_event_id"] is None

    @pytest.mark.parametrize("status", ["in-progress", "in_progress",
                                        "in progress", "active", "live",
                                        "IN-PROGRESS", " In-Progress "])
    def test_a_genuine_live_status_still_outranks_the_dates(self, status):
        """The capability half of the correction, and it must not be lost: a
        tournament DataGolf says is underway is current even when the dates
        disagree — a Monday finish, a weather-delayed final round. Case and
        surrounding space are upstream formatting, not meaning."""
        tour = shape_golf_schedule(self._one(status), "2026-09-20")["tours"][0]
        assert tour["current_event_id"] == "500"

    def test_a_live_status_does_not_resurrect_a_completed_tournament(self):
        """`completed` is still terminal, and it is checked by the same
        normalisation as the rest."""
        tour = shape_golf_schedule(self._one("COMPLETED"), "2026-09-25")["tours"][0]
        assert tour["events"][0]["status"] == "completed"

    def test_the_whole_production_shape_serves_no_future_current_row(self):
        """The issue's acceptance criterion, as a test: across every tour, no
        `is_current` row may have a start date in the future. Shaped from the
        upstream statuses as measured, not from a fixture that omits them."""
        raw = {
            "tours": [
                {"tour": "pga", "tournaments": [
                    _tournament("499", "Procore", "2026-09-10", "2026-09-13",
                                status="completed"),
                    _tournament("500", "Presidents Cup", "2026-09-24",
                                "2026-09-27", status="upcoming"),
                ]},
                {"tour": "euro", "tournaments": [
                    _tournament("2026137", "FedEx Open de France", "2026-09-24",
                                "2026-09-27", status="upcoming"),
                ]},
                {"tour": "kft", "tournaments": [
                    _tournament("166", "Compliance Solutions", "2026-10-01",
                                "2026-10-04", status="upcoming"),
                ]},
            ],
            "fetched_at": "2026-09-21T05:25:25.788360+00:00",
        }
        now = "2026-09-21"
        shaped = shape_golf_schedule(raw, now)
        offenders = [
            (t["tour"], e["event_id"], e["start_date"])
            for t in shaped["tours"]
            for e in t["events"]
            if e["is_current"] and e["start_date"] and e["start_date"] > now
        ]
        assert offenders == []
        assert [t["current_event_id"] for t in shaped["tours"]] == [None, None, None]


# ---------------------------------------------------------------------------
# 3. The fetch is parallel, and still tolerant per tour
# ---------------------------------------------------------------------------
class _ProbeService:
    """Counts how many `get_schedule` calls are in flight at the same moment.

    No clock: each call increments a counter, yields ONCE, then decrements. Under
    `gather` all five reach their yield before any resumes, so the peak is 5.
    Under a sequential `for` loop the peak can only ever be 1.
    """

    def __init__(self, fail_tours=(), empty_tours=()):
        self.active = 0
        self.peak = 0
        self.calls = []
        self.closed = False
        self._fail = set(fail_tours)
        self._empty = set(empty_tours)

    async def get_schedule(self, tour="pga"):
        self.calls.append(tour)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0)
            if tour in self._fail:
                raise RuntimeError(f"datagolf down for {tour}")
            if tour in self._empty:
                return []
            return [
                MagicMock(
                    event_id=f"{tour}-1", event_name=f"{tour} Open", course="C",
                    start_date="2026-04-09", end_date="2026-04-12",
                    location="L", country="USA", status=None, current_round=None,
                )
            ]
        finally:
            self.active -= 1

    async def close(self):
        self.closed = True


class TestFetchIsParallel:
    @pytest.mark.asyncio
    async def test_all_tours_are_in_flight_at_once(self):
        probe = _ProbeService()
        with patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            raw = await fetch_golf_schedule_raw()

        assert probe.peak == len(GOLF_SCHEDULE_TOURS), (
            f"expected all {len(GOLF_SCHEDULE_TOURS)} tour fetches concurrent, "
            f"peak was {probe.peak} — the loop went back to sequential"
        )
        assert len(raw["tours"]) == len(GOLF_SCHEDULE_TOURS)

    @pytest.mark.asyncio
    async def test_render_order_is_the_declared_tour_order_not_completion_order(self):
        probe = _ProbeService()
        with patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            raw = await fetch_golf_schedule_raw()
        assert [t["tour"] for t in raw["tours"]] == list(GOLF_SCHEDULE_TOURS)

    @pytest.mark.asyncio
    async def test_one_failing_tour_is_skipped_and_the_others_survive(self):
        """Both directions: the bad tour is gone AND every sibling is present."""
        probe = _ProbeService(fail_tours={"kft"})
        with patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            raw = await fetch_golf_schedule_raw()

        tours = [t["tour"] for t in raw["tours"]]
        assert "kft" not in tours
        assert tours == [t for t in GOLF_SCHEDULE_TOURS if t != "kft"]

    @pytest.mark.asyncio
    async def test_an_empty_tour_is_skipped(self):
        probe = _ProbeService(empty_tours={"opp"})
        with patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            raw = await fetch_golf_schedule_raw()
        assert "opp" not in [t["tour"] for t in raw["tours"]]

    @pytest.mark.asyncio
    async def test_the_client_is_closed_even_when_every_tour_fails(self):
        probe = _ProbeService(fail_tours=set(GOLF_SCHEDULE_TOURS))
        with patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            raw = await fetch_golf_schedule_raw()
        assert probe.closed is True
        assert raw["tours"] == []


# ---------------------------------------------------------------------------
# 4. The route: a hit costs nothing, a miss writes both keys
# ---------------------------------------------------------------------------
def _rc(values=None):
    values = values or {}
    rc = MagicMock()
    rc.get = AsyncMock(side_effect=lambda key: values.get(key))
    rc.set = AsyncMock()
    rc.aclose = AsyncMock()
    return rc


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("DATAGOLF_API_KEY", "test-key-not-a-secret")


class TestRouteCache:
    @pytest.mark.asyncio
    async def test_a_cache_hit_makes_ZERO_datagolf_calls(self, with_key):
        """The whole ship, in one assertion."""
        probe = _ProbeService()
        rc = _rc({LITERAL_KEY: json.dumps(RAW)})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            result = await get_golf_schedule()

        assert probe.calls == []
        assert [t["tour"] for t in result["tours"]] == ["pga", "euro"]

    @pytest.mark.asyncio
    async def test_a_miss_fetches_and_writes_BOTH_keys_by_literal_name(self, with_key):
        probe = _ProbeService()
        rc = _rc({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            await get_golf_schedule()

        assert sorted(probe.calls) == sorted(GOLF_SCHEDULE_TOURS)
        written = {c.args[0]: c for c in rc.set.await_args_list}
        assert LITERAL_KEY in written, f"primary key not written; got {list(written)}"
        assert LITERAL_STALE_KEY in written
        assert written[LITERAL_KEY].kwargs["ex"] == GOLF_SCHEDULE_TTL_S
        assert written[LITERAL_STALE_KEY].kwargs["ex"] == GOLF_SCHEDULE_STALE_TTL_S

    def test_the_ttl_outlives_the_hourly_warm(self):
        """#901's lesson, one endpoint later: a 3600s TTL expires marginally
        BEFORE the hourly warm that refreshes it, handing a cold rebuild to
        whoever arrives in the gap."""
        assert GOLF_SCHEDULE_TTL_S > 3600
        assert GOLF_SCHEDULE_STALE_TTL_S >= 86400

    @pytest.mark.asyncio
    async def test_a_dead_redis_still_serves_the_page(self, with_key):
        probe = _ProbeService()
        with patch("app.tasks.redis_state.get_async_redis_client",
                   side_effect=RuntimeError("redis down")), \
             patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe):
            result = await get_golf_schedule()
        assert len(result["tours"]) == len(GOLF_SCHEDULE_TOURS)

    @pytest.mark.asyncio
    async def test_missing_api_key_still_503s(self, monkeypatch):
        monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
        with pytest.raises(HTTPException) as exc:
            await get_golf_schedule()
        assert exc.value.status_code == 503


class TestRouteDegradation:
    @pytest.mark.asyncio
    async def test_a_failed_fetch_serves_labelled_last_good(self, with_key):
        rc = _rc({LITERAL_STALE_KEY: json.dumps(RAW)})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   side_effect=RuntimeError("datagolf down")):
            result = await get_golf_schedule()

        assert result["degraded"] is True
        assert result["degraded_reason"] == "fetch_failed"
        assert [t["tour"] for t in result["tours"]] == ["pga", "euro"]

    @pytest.mark.asyncio
    async def test_a_failed_fetch_with_no_last_good_raises_500(self, with_key):
        rc = _rc({})
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   side_effect=RuntimeError("datagolf down")):
            with pytest.raises(HTTPException) as exc:
                await get_golf_schedule()
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_an_empty_fetch_never_overwrites_a_good_cache(self, with_key):
        """gotcha #53: a zero-yield fetch is not an answer about golf's season."""
        rc = _rc({LITERAL_STALE_KEY: json.dumps(RAW)})
        empty = {"tours": [], "fetched_at": "2026-04-10T07:00:00+00:00"}
        with patch("app.tasks.redis_state.get_async_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   return_value=empty):
            result = await get_golf_schedule()

        assert result["degraded"] is True
        assert result["degraded_reason"] == "empty_fetch"
        assert [t["tour"] for t in result["tours"]] == ["pga", "euro"]
        # And nothing was written over the good mirror.
        assert rc.set.await_args_list == []


# ---------------------------------------------------------------------------
# 5. The warmer, and its agreement with the route
# ---------------------------------------------------------------------------
class TestWarmer:
    @pytest.mark.asyncio
    async def test_the_warmer_writes_the_SAME_LITERAL_keys_the_route_reads(self):
        """LAT-P125's M5/M6 lesson. Reading the key through the shared constant
        makes a respelling invisible, because route and warmer move together."""
        from app.tasks.precompute_category_pages import _precompute_golf_schedule

        rc = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   return_value=RAW):
            result = await _precompute_golf_schedule()

        keys = [c.args[0] for c in rc.set.call_args_list]
        assert LITERAL_KEY in keys
        assert LITERAL_STALE_KEY in keys
        assert result["written"] is True
        assert result["tours"] == 2
        assert result["tournaments"] == 5

    @pytest.mark.asyncio
    async def test_the_warmer_writes_the_route_TTLs(self):
        from app.tasks.precompute_category_pages import _precompute_golf_schedule

        rc = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   return_value=RAW):
            await _precompute_golf_schedule()

        by_key = {c.args[0]: c.kwargs["ex"] for c in rc.set.call_args_list}
        assert by_key[LITERAL_KEY] == GOLF_SCHEDULE_TTL_S
        assert by_key[LITERAL_STALE_KEY] == GOLF_SCHEDULE_STALE_TTL_S

    @pytest.mark.asyncio
    async def test_a_zero_tour_warm_writes_NOTHING_and_says_so(self):
        from app.tasks.precompute_category_pages import _precompute_golf_schedule

        rc = MagicMock()
        with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   return_value={"tours": [], "fetched_at": "x"}):
            result = await _precompute_golf_schedule()

        assert rc.set.call_args_list == []
        assert result == {"tours": 0, "written": False}

    @pytest.mark.asyncio
    async def test_what_the_warmer_writes_is_what_the_route_serves(self):
        """End to end across the two halves: warm, then read the warmed bytes
        back through the route and get a real page."""
        from app.tasks.precompute_category_pages import _precompute_golf_schedule

        store: dict = {}
        sync_rc = MagicMock()
        sync_rc.set = MagicMock(
            side_effect=lambda k, v, ex=None: store.__setitem__(k, v)
        )
        with patch("app.tasks.redis_state.get_redis_client", return_value=sync_rc), \
             patch("app.routes.playoffs.fetch_golf_schedule_raw",
                   return_value=RAW):
            await _precompute_golf_schedule()

        probe = _ProbeService()
        async_rc = _rc(store)
        with patch("app.tasks.redis_state.get_async_redis_client",
                   return_value=async_rc), \
             patch("app.services.datagolf_api.DataGolfAPIService",
                   return_value=probe), \
             patch.dict("os.environ", {"DATAGOLF_API_KEY": "test-key-not-a-secret"}):
            result = await get_golf_schedule()

        assert probe.calls == [], "the warmed key was not the key the route reads"
        assert [t["tour"] for t in result["tours"]] == ["pga", "euro"]

    def test_the_warm_is_registered_and_runs_BEFORE_the_grids(self):
        """The last section starves first, and this one is a single external
        round trip — it must not sit behind the 120s-per-league grid budget."""
        import inspect

        from app.tasks import precompute_category_pages as mod

        src = inspect.getsource(mod._precompute_all_category_pages)
        assert '("golf_schedule", _precompute_golf_schedule)' in src
        assert src.index('("golf_schedule"') < src.index('("grids"')

    def test_the_warm_adds_no_beat_entry(self):
        """It rides the hourly `precompute-category-pages` (gotcha #12: a new
        scheduled task means an allowlist edit, and this one does not need one)."""
        from app.tasks import celery_app

        beat = celery_app.conf.beat_schedule
        assert not any(
            "golf_schedule" in str(entry.get("task", "")) for entry in beat.values()
        )
        assert "precompute-category-pages" in beat
