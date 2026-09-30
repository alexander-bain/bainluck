"""#9919 — a series leg the venue has already ruled out reaches the card as a result.

THE SPECIMEN, production 2026-09-30 ~20:15Z. `/events/15321907` (BOS @ NYY, Wild
Card Game 2), Bigger Picture → SERIES → *Series Exact Score: Boston vs New York
Yankees*: NYY 2-0 54% · NYY 2-1 27% · BOS 2-1 19% · **BOS wins 2-0 ---**. The
Yankees won Game 1; Kalshi `62455755`'s BOS 2-0 leg is stored `is_winner =
false`, `resolution_source = 'api_settlement'`, `current_probability 0`, on a
market still `open`. `series_markets[].outcomes[]` carried no grade, so the
leg's `probability: None` printed as "no number" for a question already answered.

The rule is the league and hub cards' own (`_outcome_is_settled`, #3868 /
CERT-2222 / #3617), read over the WHOLE field, so the controls are that rule's
own refusals: a retraction (`ungradeable_result`) and a FALSE nobody licensed
(no source) stay live, and a live leg stays live.

SYNTHETIC ROWS, LABELLED: the #9042 file's harness (a football fixture so the
sport net applies unchanged); ids and prices are invented, the shape is the
specimen's.
"""

import pytest

from tests.integration.test_route_related_futures_cfl_7851 import (
    _football_event,
    _get,
    _outcome,
)

from tests.integration.test_route_related_futures_settled_before_kickoff_9042 import (
    AWARD,
    DUKE_AWARD,
    SERIES,
    STAN_AWARD,
    _market,
    _session,
)

LIVE_20, LIVE_21, LOSER, RETRACTED, UNLICENSED = 99191001, 99191002, 99191003, 99191004, 99191005
_EVENT_IDS = iter(range(9919001, 9919100))


def _leg(id, market, name, p, *, is_winner=None, source=None):
    o = _outcome(id, market, name, p)
    o.is_winner = is_winner
    o.resolution_source = source
    return o


async def _series_legs(monkeypatch, legs_spec):
    """The #9042 harness's page: one award rail (so the build is not an `empty`
    exit) and the series card under test, with the page's refusal switched off."""
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    event.status = "live"
    award_m = _market(AWARD, "College Football Playoff Champion")
    series_m = _market(SERIES, "Series Exact Score: Duke vs Stanford")
    series_m.source = "kalshi"
    series_m.mutually_exclusive = True
    series_m.status = "open"
    series_m.resolution_date = None
    candidates = [
        _leg(DUKE_AWARD, award_m, "Duke Blue Devils", 0.21),
        _leg(STAN_AWARD, award_m, "Stanford Cardinal", 0.09),
    ]
    legs = [_leg(i, series_m, n, p, **kw) for i, n, p, kw in legs_spec]

    async def no_refusal(db, board):
        return set()

    monkeypatch.setattr("app.routes.league_futures._page_withheld_outcome_ids", no_refusal)
    body = await _get(
        monkeypatch, _session(event, [award_m, series_m], candidates, legs), event_id
    )
    (card,) = [m for m in body["series_markets"] if m["market_id"] == SERIES]
    return {o["outcome_id"]: o for o in card["outcomes"]}


# The specimen's field: two live legs, the leg Game 1 ruled out, and the rule's
# own two refusals beside it.
SPECIMEN = [
    (LIVE_20, "DUKE wins 2-0", 0.555, {}),
    (LIVE_21, "DUKE wins 2-1", 0.275, {}),
    (LOSER, "STAN wins 2-0", 0.0, {"is_winner": False, "source": "api_settlement"}),
    (RETRACTED, "STAN wins 2-1", 0.17, {"is_winner": False, "source": "ungradeable_result"}),
    (UNLICENSED, "DUKE wins 3-0", 0.0, {"is_winner": False}),
]


@pytest.mark.asyncio
async def test_the_ruled_out_leg_is_served_settled_and_lost(monkeypatch):
    legs = await _series_legs(monkeypatch, SPECIMEN)
    assert legs[LOSER]["settled"] is True
    assert legs[LOSER]["is_winner"] is False
    # Its number is unchanged: the card draws the result from the grade.
    assert legs[LOSER]["probability"] is None


@pytest.mark.asyncio
async def test_control_live_legs_stay_live_and_keep_their_price(monkeypatch):
    legs = await _series_legs(monkeypatch, SPECIMEN)
    for oid, p in ((LIVE_20, 0.555), (LIVE_21, 0.275)):
        assert legs[oid]["settled"] is False
        assert legs[oid]["is_winner"] is None
        assert legs[oid]["probability"] == pytest.approx(p)


@pytest.mark.asyncio
async def test_control_a_retraction_is_not_a_loss(monkeypatch):
    """`ungradeable_result` asserts no winner (CERT-2222); it must not read Lost."""
    legs = await _series_legs(monkeypatch, SPECIMEN)
    assert legs[RETRACTED]["settled"] is False
    assert legs[RETRACTED]["probability"] == pytest.approx(0.17)


@pytest.mark.asyncio
async def test_control_a_false_nobody_licensed_is_not_a_loss(monkeypatch):
    """`is_winner` defaults FALSE; with no source on an open market it means nobody looked."""
    legs = await _series_legs(monkeypatch, SPECIMEN)
    assert legs[UNLICENSED]["settled"] is False


@pytest.mark.asyncio
async def test_a_crowned_leg_is_served_settled_and_won(monkeypatch):
    """The clinching game: the series card carries the winner as a result too."""
    legs = await _series_legs(
        monkeypatch,
        [
            (LIVE_20, "DUKE wins 2-0", 1.0, {"is_winner": True, "source": "api_settlement"}),
            (LOSER, "STAN wins 2-0", 0.0, {"is_winner": False, "source": "api_settlement"}),
        ],
    )
    assert legs[LIVE_20]["settled"] is True and legs[LIVE_20]["is_winner"] is True
    assert legs[LOSER]["settled"] is True and legs[LOSER]["is_winner"] is False


@pytest.mark.asyncio
async def test_control_a_stamped_loss_the_book_still_prices_live_is_not_a_loss(monkeypatch):
    """#3617: with nobody crowned, a FALSE stamp on a leg its own book still prices
    as a contender (0.20 ≤ p < 0.97) has nothing to be a loss against. The field is
    read WHOLE, so this needs the route to pass the real `_field_has_a_winner`."""
    legs = await _series_legs(
        monkeypatch,
        [
            (LIVE_20, "DUKE wins 2-0", 0.5, {}),
            (LOSER, "STAN wins 2-1", 0.45, {"is_winner": False, "source": "api_settlement"}),
        ],
    )
    assert legs[LOSER]["settled"] is False
    assert legs[LOSER]["probability"] == pytest.approx(0.45)
