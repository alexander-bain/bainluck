"""#9938 — the Series card stops printing a print the live book does not anchor.

THE SPECIMEN, production 2026-09-30 21:14Z. `/events/15321782` (PHI @ ATL, Wild
Card Game 2, Bottom 10th, PHI 4–3, hero ATL 18%). Bigger Picture → Series Exact
Score printed **"ATL wins 2-0 52%"**: stored 0.72 on a 0.01 / 0.81 book, squeezed
by #9901 alongside ATL 2-1 0.34 (0.02 / 0.58) and PHI 2-1 0.40 (0.37 / 0.43).

SYNTHETIC ROWS, LABELLED: the #9919 file's harness (a football fixture so the sport
net applies unchanged). Prices and books are the specimen's; ids are invented.

Controls: the same board before and after the game is played keeps every price
(the rule is asked only during play), and the surviving leg is never squeezed up.
"""

import inspect

import pytest

from tests.integration.test_route_related_futures_cfl_7851 import (
    _football_event,
    _get,
)
from tests.integration.test_route_related_futures_series_leg_lost_9919 import _leg
from tests.integration.test_route_related_futures_settled_before_kickoff_9042 import (
    AWARD,
    DUKE_AWARD,
    SERIES,
    STAN_AWARD,
    _market,
    _session,
)

ATL_20, ATL_21, PHI_21, PHI_20 = 99381001, 99381002, 99381003, 99381004
_EVENT_IDS = iter(range(9938001, 9938100))

# (id, name, stored price, bid, ask, extra)
SPECIMEN = [
    (ATL_20, "ATL wins 2-0", 0.72, 0.01, 0.81, {}),
    (ATL_21, "ATL wins 2-1", 0.34, 0.02, 0.58, {}),
    (PHI_21, "PHI wins 2-1", 0.40, 0.37, 0.43, {}),
    (PHI_20, "PHI wins 2-0", 0.0, 0.0, 1.0, {"is_winner": False, "source": "api_settlement"}),
]


async def _series_card(monkeypatch, *, event_status):
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    event.status = event_status
    award_m = _market(AWARD, "College Football Playoff Champion")
    series_m = _market(SERIES, "Series Exact Score: Philadelphia vs Atlanta")
    series_m.source = "kalshi"
    series_m.mutually_exclusive = True
    series_m.status = "open"
    series_m.resolution_date = None
    candidates = [
        _leg(DUKE_AWARD, award_m, "Duke Blue Devils", 0.21),
        _leg(STAN_AWARD, award_m, "Stanford Cardinal", 0.09),
    ]
    award_m.outcomes = candidates
    legs = []
    for oid, name, p, bid, ask, kw in SPECIMEN:
        leg = _leg(oid, series_m, name, p, **kw)
        leg.current_yes_bid = bid
        leg.current_yes_ask = ask
        legs.append(leg)
    series_m.outcomes = legs

    # The market's own page refuses nothing here, so what moves is this rule alone.
    async def no_refusal(db, board):
        return set()

    monkeypatch.setattr("app.routes.league_futures._page_withheld_outcome_ids", no_refusal)
    body = await _get(
        monkeypatch, _session(event, [award_m, series_m], candidates, legs), event_id
    )
    (card,) = [m for m in body["series_markets"] if m["market_id"] == SERIES]
    return {o["outcome_id"]: o for o in card["outcomes"]}


@pytest.mark.asyncio
async def test_during_play_the_unanchored_prints_are_withheld(monkeypatch):
    legs = await _series_card(monkeypatch, event_status="live")
    assert legs[ATL_20]["probability"] is None
    assert legs[ATL_21]["probability"] is None
    # Named and in place, like every refused series leg (#9008).
    assert legs[ATL_20]["name"] == "ATL wins 2-0"
    assert legs[ATL_20]["settled"] is False


@pytest.mark.asyncio
async def test_during_play_the_tradeable_leg_keeps_its_raw_price(monkeypatch):
    """The squeeze abstains on a refused leg, so PHI 2-1 is never inflated toward 100%."""
    legs = await _series_card(monkeypatch, event_status="live")
    assert legs[PHI_21]["probability"] == pytest.approx(0.40)


@pytest.mark.asyncio
async def test_during_play_the_ruled_out_leg_still_reads_lost(monkeypatch):
    legs = await _series_card(monkeypatch, event_status="live")
    assert legs[PHI_20]["settled"] is True
    assert legs[PHI_20]["is_winner"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["scheduled", "completed"])
async def test_control_off_the_field_every_price_is_served(monkeypatch, status):
    legs = await _series_card(monkeypatch, event_status=status)
    for oid in (ATL_20, ATL_21, PHI_21):
        assert legs[oid]["probability"] is not None, (status, oid)


def test_both_rail_call_sites_ask_during_play():
    """The team-futures rail and the series card are both fed by this helper; a
    call site that forgets the flag serves the print on half the page."""
    from app.routes import events as events_route

    src = inspect.getsource(events_route._build_related_futures)
    calls = src.count("await _related_futures_withheld_ids(")
    asked = src.count('live_play=event.status == "live"')
    assert calls == 2
    assert asked == calls
