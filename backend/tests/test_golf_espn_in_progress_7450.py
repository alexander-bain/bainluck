"""#7450: a golf tournament being played reads as being played.

DataGolf's `get-schedule` status never says `in-progress`. On 2026-09-25, day two
of both, the Presidents Cup and the FedEx Open de France were served `upcoming`
by `/api/golf`, `/api/hub/golf` and `/api/event/event:golf:presidents-cup`.
ESPN's scoreboard said `STATUS_IN_PROGRESS` (state `in`) for both. The schedule
now carries ESPN's word, and only when tour, key and dates all agree.

No test here reaches the network: the ESPN wire is a MockTransport, and the
schedule tests stub both fetches.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.routes import golf as golf_mod
from app.services.espn_api import ESPNAPIService, reset_espn_authority_state
from app.utils.event_concept import _golf_status


def _entry(name="Presidents Cup", key="presidents_cup", tour="pga",
           status="upcoming", start="2026-09-24", end="2026-09-27"):
    return {
        "name": name,
        "key": key,
        "start_date": f"{start}T00:00:00+00:00" if start else None,
        "end_date": f"{end}T00:00:00+00:00" if end else None,
        "venue": "Medinah Country Club (No. 3)",
        "location": "Medinah, IL",
        "status": status,
        "round": "",
        "tour": tour,
    }


def _espn(name="Presidents Cup", state="in", status="STATUS_IN_PROGRESS",
          start="2026-09-24T04:00Z", end="2026-09-27T04:00Z"):
    # The shape `ESPNAPIService.get_golf_scoreboard` returns, values as ESPN
    # served them on 2026-09-25 07:3xZ.
    return {"name": name, "start": start, "end": end, "state": state, "status": status}


def _status_after(entry, espn_by_tour):
    [out] = golf_mod._overlay_espn_in_progress([entry], espn_by_tour)
    return out["status"]


# ── the ship ──────────────────────────────────────────────────────────────────


def test_espn_in_play_makes_the_presidents_cup_live():
    [out] = golf_mod._overlay_espn_in_progress([_entry()], {"pga": [_espn()]})
    assert out["status"] == "in-progress"
    # What the hub rail and the event page print: `_golf_status` reads the
    # schedule status the golf route copies onto `schedule_status`.
    assert _golf_status({**out, "schedule_status": out["status"]}) == "live"


def test_control_without_espn_the_same_entry_stays_upcoming():
    # The defect as served: DataGolf's `upcoming` inside its own dates.
    entry = _entry()
    assert _status_after(entry, {}) == "upcoming"
    assert _golf_status({**entry, "schedule_status": entry["status"]}) == "upcoming"


def test_dp_world_board_is_espn_eur_and_schedule_euro():
    entry = _entry(name="FedEx Open de France", key="fedex_open_de_france", tour="euro")
    board = {"euro": [_espn(name="FedEx Open de France")]}
    assert _status_after(entry, board) == "in-progress"


def test_weather_suspension_is_still_being_played():
    board = {"pga": [_espn(status="STATUS_PLAY_SUSPENDED")]}  # state stays `in`
    assert _status_after(_entry(), board) == "in-progress"


# ── what must NOT turn live ───────────────────────────────────────────────────


@pytest.mark.parametrize("state,status", [
    ("pre", "STATUS_SCHEDULED"),
    ("post", "STATUS_FINAL"),
    ("post", "STATUS_CANCELED"),
    (None, None),
])
def test_only_espn_state_in_counts(state, status):
    board = {"pga": [_espn(state=state, status=status)]}
    assert _status_after(_entry(), board) == "upcoming"


def test_a_finished_board_never_completes_an_entry_from_here():
    # Scope: this rail only says "being played". A `post` never writes
    # `completed`, so it cannot drop a card from `_filter_stale_tournaments`.
    board = {"pga": [_espn(state="post", status="STATUS_FINAL")]}
    assert _status_after(_entry(), board) == "upcoming"


def test_completed_entry_is_left_alone():
    assert _status_after(_entry(status="completed"), {"pga": [_espn()]}) == "completed"


def test_another_tours_board_does_not_speak_for_this_entry():
    assert _status_after(_entry(tour="euro"), {"pga": [_espn()]}) == "upcoming"


def test_a_different_tournament_name_does_not_match():
    board = {"pga": [_espn(name="Ryder Cup")]}
    assert _status_after(_entry(), board) == "upcoming"


def test_same_name_outside_the_entrys_dates_does_not_match():
    # Last edition's name on ESPN, this edition's dates in the schedule.
    board = {"pga": [_espn(start="2024-09-26T04:00Z", end="2024-09-29T04:00Z")]}
    assert _status_after(_entry(), board) == "upcoming"


def test_one_day_of_timezone_slack_each_side_and_no_more():
    assert _status_after(_entry(), {"pga": [_espn(start="2026-09-23T22:00Z")]}) == "in-progress"
    assert _status_after(_entry(), {"pga": [_espn(start="2026-09-28T01:00Z")]}) == "in-progress"
    assert _status_after(_entry(), {"pga": [_espn(start="2026-09-22T23:00Z")]}) == "upcoming"
    assert _status_after(_entry(), {"pga": [_espn(start="2026-09-29T01:00Z")]}) == "upcoming"


@pytest.mark.parametrize("entry", [_entry(start=None), _entry(end=None)])
def test_an_entry_missing_a_date_is_refused(entry):
    assert _status_after(entry, {"pga": [_espn()]}) == "upcoming"


def test_an_espn_event_missing_its_start_is_refused():
    assert _status_after(_entry(), {"pga": [_espn(start=None)]}) == "upcoming"


def test_sponsor_suffix_folds_the_same_way_as_the_schedule_key():
    entry = _entry(name="Arnold Palmer Invitational", key="arnold_palmer_invitational")
    board = {"pga": [_espn(name="Arnold Palmer Invitational presented by Mastercard")]}
    assert _status_after(entry, board) == "in-progress"


def test_the_cached_entries_are_never_mutated():
    # The entries belong to the hour-long schedule cache; a status that lasts
    # only as long as play must not be written into it.
    entry = _entry()
    sibling = _entry(name="Ryder Cup", key="ryder_cup")
    schedule = [entry, sibling]
    out = golf_mod._overlay_espn_in_progress(schedule, {"pga": [_espn()]})
    assert entry["status"] == "upcoming"
    assert out[0] is not entry and out[0]["status"] == "in-progress"
    assert out[1] is sibling
    assert [e["key"] for e in out] == ["presidents_cup", "ryder_cup"]


# ── the schedule loader ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_loader_applies_espn_to_the_datagolf_schedule(monkeypatch):
    monkeypatch.setattr(golf_mod, "_get_datagolf_schedule", AsyncMock(return_value=[_entry()]))
    monkeypatch.setattr(golf_mod, "_get_espn_golf_scoreboards",
                        AsyncMock(return_value={"pga": [_espn()]}))
    [out] = await golf_mod._get_golf_schedule()
    assert out["status"] == "in-progress"


@pytest.mark.asyncio
async def test_loader_keeps_the_schedule_when_espn_raises(monkeypatch):
    schedule = [_entry()]
    monkeypatch.setattr(golf_mod, "_get_datagolf_schedule", AsyncMock(return_value=schedule))
    monkeypatch.setattr(golf_mod, "_get_espn_golf_scoreboards",
                        AsyncMock(side_effect=RuntimeError("boom")))
    assert await golf_mod._get_golf_schedule() == schedule


@pytest.mark.asyncio
async def test_loader_does_not_ask_espn_when_datagolf_is_empty(monkeypatch):
    espn = AsyncMock(return_value={"pga": [_espn()]})
    monkeypatch.setattr(golf_mod, "_get_datagolf_schedule", AsyncMock(return_value=[]))
    monkeypatch.setattr(golf_mod, "_get_espn_golf_scoreboards", espn)
    assert await golf_mod._get_golf_schedule() == []
    espn.assert_not_called()


# ── the ESPN read ─────────────────────────────────────────────────────────────


_BOARD = {
    "events": [{
        "id": "401824815",
        "name": "Presidents Cup",
        "date": "2026-09-24T04:00Z",
        "endDate": "2026-09-27T04:00Z",
        "status": {"type": {"name": "STATUS_IN_PROGRESS", "state": "in"}},
    }],
}


@pytest.fixture
def espn_state():
    reset_espn_authority_state()
    yield
    reset_espn_authority_state()


def _service(handler):
    return ESPNAPIService(timeout=1.0, rate_limit_delay=0.0,
                          transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_golf_scoreboard_parses_espns_shape(espn_state):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=_BOARD)

    service = _service(handler)
    try:
        events = await service.get_golf_scoreboard("pga")
    finally:
        await service.close()
    assert seen == ["/apis/site/v2/sports/golf/pga/scoreboard"]
    assert events == [{
        "name": "Presidents Cup",
        "start": "2026-09-24T04:00Z",
        "end": "2026-09-27T04:00Z",
        "state": "in",
        "status": "STATUS_IN_PROGRESS",
    }]


@pytest.mark.asyncio
async def test_golf_scoreboard_dark_is_none_not_empty(espn_state):
    service = _service(lambda request: httpx.Response(500))
    try:
        assert await service.get_golf_scoreboard("pga") is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_scoreboards_skip_a_dark_tour_and_cache_for_five_minutes(monkeypatch, espn_state):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if "/eur/" in request.url.path:
            return httpx.Response(503)
        return httpx.Response(200, json=_BOARD)

    import app.services.espn_api as espn_mod

    real = espn_mod.ESPNAPIService
    monkeypatch.setattr(
        espn_mod, "ESPNAPIService",
        lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handler)}),
    )
    monkeypatch.setitem(golf_mod._espn_golf_cache, "data", None)
    monkeypatch.setitem(golf_mod._espn_golf_cache, "ts", 0)
    clock = [1_000_000.0]
    monkeypatch.setattr(golf_mod, "time", SimpleNamespace(time=lambda: clock[0]))

    by_tour = await golf_mod._get_espn_golf_scoreboards()
    assert set(by_tour) == {"pga", "liv"}  # the dark DP World board is absent
    assert len(calls) == 3

    clock[0] += golf_mod._ESPN_GOLF_TTL - 1
    await golf_mod._get_espn_golf_scoreboards()
    assert len(calls) == 3  # served from cache

    clock[0] += 2
    await golf_mod._get_espn_golf_scoreboards()
    assert len(calls) == 6  # expired, re-read
