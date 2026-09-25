"""#8591: an LPGA card on the golf hub is dated by ESPN's LPGA calendar.

DataGolf's schedule has no LPGA, so an LPGA card never met a schedule row and the
hub fell back to the card's earliest market commence. On 2026-09-25 `/hub/golf`
dated the Walmart NW Arkansas Championship (played Sep 25-27) "Mon, Sep 21", the
day its market opened. ESPN's lpga scoreboard carries the whole season in
`leagues[0].calendar`; a dateless women's card now takes its dates from there,
only when the name and the card's own market window both agree on ONE entry.

No test here reaches the network: the ESPN wire is a MockTransport.
"""

import inspect
from types import SimpleNamespace

import httpx
import pytest

from app.routes import golf as golf_mod
from app.services.espn_api import ESPNAPIService, reset_espn_authority_state

# ESPN's lpga calendar as served 2026-09-25 10:2xZ (a slice of its 32 entries).
_CALENDAR = [
    {"name": "The Standard Portland Classic", "start": "2026-08-13T07:00Z", "end": "2026-08-16T07:00Z"},
    {"name": "Solheim Cup", "start": "2026-09-11T07:00Z", "end": "2026-09-13T07:00Z"},
    {"name": "Walmart NW Arkansas Championship pres. by P&G",
     "start": "2026-09-25T07:00Z", "end": "2026-09-27T07:00Z"},
    {"name": "LOTTE Championship pres. by Hoakalei",
     "start": "2026-10-01T07:00Z", "end": "2026-10-04T07:00Z"},
    {"name": "BMW Ladies Championship", "start": "2026-10-22T07:00Z", "end": "2026-10-25T07:00Z"},
    {"name": "U.S. Women's Open pres. by Ally", "start": "2026-06-04T07:00Z", "end": "2026-06-07T07:00Z"},
]


def _card(key="nw_arkansas_championship_womens", is_womens=True,
          commence="2026-09-21T15:01:14+00:00", resolution="2026-09-28T03:59:00+00:00",
          start=None, end=None):
    # The production row `/api/golf` served 2026-09-25 10:2xZ, before the fix.
    return {
        "key": key,
        "is_womens": is_womens,
        "commence_time": commence,
        "resolution_date": resolution,
        "start_date": start,
        "end_date": end,
    }


def _fill(card, calendar=_CALENDAR):
    golf_mod._fill_dates_from_espn_lpga_calendar([card], calendar)
    return card


def test_the_nw_arkansas_card_is_dated_by_espn_not_by_its_market_opening():
    card = _fill(_card())
    assert card["start_date"] == "2026-09-25T00:00:00+00:00"
    assert card["end_date"] == "2026-09-27T00:00:00+00:00"


def test_control_without_a_calendar_the_card_stays_dateless():
    card = _fill(_card(), calendar=[])
    assert card["start_date"] is None and card["end_date"] is None


def test_market_fields_are_left_as_they_were():
    card = _fill(_card())
    assert card["commence_time"] == "2026-09-21T15:01:14+00:00"
    assert card["resolution_date"] == "2026-09-28T03:59:00+00:00"


@pytest.mark.parametrize("start,end", [
    ("2026-09-24T00:00:00+00:00", None),
    (None, "2026-09-28T00:00:00+00:00"),
])
def test_it_fills_and_never_overrules(start, end):
    card = _fill(_card(start=start, end=end))
    assert (card["start_date"], card["end_date"]) == (start, end)


def test_a_mens_card_is_never_dated_from_the_lpga_calendar():
    card = _fill(_card(is_womens=False))
    assert card["start_date"] is None


def test_every_distinctive_word_must_be_in_espns_label():
    # "Albertsons Boise Open presented by Chevron" is a Korn Ferry event that the
    # women's regex flags on "Chevron"; ESPN's LPGA calendar has no such event.
    card = _fill(_card(key="albertsons_boise_open_presented_by_chevron",
                       commence="2026-08-10T00:00:00+00:00",
                       resolution="2026-08-16T00:00:00+00:00"))
    assert card["start_date"] is None


def test_a_card_whose_key_names_only_generic_words_is_refused():
    # `u_s_women_s_open` leaves nothing distinctive once `u`, `s`, `women`, `open`
    # are dropped, so it cannot claim any one entry.
    card = _fill(_card(key="u_s_women_s_open",
                       commence="2026-05-20T00:00:00+00:00",
                       resolution="2026-06-08T00:00:00+00:00"))
    assert card["start_date"] is None


def test_the_same_name_outside_the_cards_market_window_does_not_match():
    # A card for NEXT year's edition, opened after this year's was played.
    card = _fill(_card(commence="2026-09-29T00:00:00+00:00",
                       resolution="2027-09-27T00:00:00+00:00"))
    assert card["start_date"] is None


def test_three_days_of_slack_each_side_and_no_more():
    # ESPN start 2026-09-25: a market opened on the 28th is inside, the 29th is not;
    # a market resolving on the 22nd is inside, the 21st is not.
    assert _fill(_card(commence="2026-09-28T00:00:00+00:00"))["start_date"]
    assert not _fill(_card(commence="2026-09-29T00:00:00+00:00"))["start_date"]
    assert _fill(_card(commence="2026-09-01T00:00:00+00:00",
                       resolution="2026-09-22T00:00:00+00:00"))["start_date"]
    assert not _fill(_card(commence="2026-09-01T00:00:00+00:00",
                           resolution="2026-09-21T00:00:00+00:00"))["start_date"]


def test_two_candidate_entries_leave_the_card_as_it_was():
    twice = _CALENDAR + [{"name": "NW Arkansas Championship",
                          "start": "2026-09-26T07:00Z", "end": "2026-09-28T07:00Z"}]
    card = _fill(_card(), calendar=twice)
    assert card["start_date"] is None


def test_a_card_with_no_market_dates_is_refused():
    card = _fill(_card(commence=None, resolution=None))
    assert card["start_date"] is None


def test_the_fill_runs_after_the_stale_filter_in_get_golf():
    # A calendar date may tell a surviving row when it is; it may not be the reason
    # a finished row survives (#8139's property 2, same here).
    src = inspect.getsource(golf_mod.get_golf)
    assert "_fill_dates_from_espn_lpga_calendar(" in src
    assert src.index("_filter_stale_tournaments(") < src.index("_fill_dates_from_espn_lpga_calendar(")


# ── the ESPN read ─────────────────────────────────────────────────────────────


_BOARD = {
    "leagues": [{"calendar": [
        {"id": "401835161", "label": "Walmart NW Arkansas Championship pres. by P&G",
         "startDate": "2026-09-25T07:00Z", "endDate": "2026-09-27T07:00Z"},
    ]}],
    "events": [],
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
async def test_golf_calendar_parses_espns_shape(espn_state):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=_BOARD)

    service = _service(handler)
    try:
        calendar = await service.get_golf_calendar("lpga")
    finally:
        await service.close()
    assert seen == ["/apis/site/v2/sports/golf/lpga/scoreboard"]
    assert calendar == [{
        "name": "Walmart NW Arkansas Championship pres. by P&G",
        "start": "2026-09-25T07:00Z",
        "end": "2026-09-27T07:00Z",
    }]


@pytest.mark.asyncio
async def test_golf_calendar_dark_is_none_not_empty(espn_state):
    service = _service(lambda request: httpx.Response(500))
    try:
        assert await service.get_golf_calendar("lpga") is None
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_calendar_caches_an_hour_and_a_dark_espn_retries_in_five_minutes(
    monkeypatch, espn_state,
):
    calls = []
    dark = [True]

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503) if dark[0] else httpx.Response(200, json=_BOARD)

    import app.services.espn_api as espn_mod

    real = espn_mod.ESPNAPIService
    monkeypatch.setattr(
        espn_mod, "ESPNAPIService",
        lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handler)}),
    )
    monkeypatch.setattr(golf_mod, "_espn_lpga_calendar_cache", {"data": None, "ts": 0, "ttl": 0})
    clock = [1_000_000.0]
    monkeypatch.setattr(golf_mod, "time", SimpleNamespace(time=lambda: clock[0]))

    assert await golf_mod._get_espn_lpga_calendar() == []
    n_dark = len(calls)
    clock[0] += golf_mod._ESPN_LPGA_CALENDAR_DARK_RETRY - 1
    await golf_mod._get_espn_lpga_calendar()
    assert len(calls) == n_dark  # dark result held briefly

    dark[0] = False
    reset_espn_authority_state()
    clock[0] += 2
    assert len(await golf_mod._get_espn_lpga_calendar()) == 1
    n_ok = len(calls)
    clock[0] += golf_mod._ESPN_LPGA_CALENDAR_TTL - 1
    await golf_mod._get_espn_lpga_calendar()
    assert len(calls) == n_ok  # served from the hour cache
