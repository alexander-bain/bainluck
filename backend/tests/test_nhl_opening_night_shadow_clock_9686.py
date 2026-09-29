"""NHL opening night shows each game once, even where Polymarket lists the wrong minute — #9686.

**SHIP: on NHL opening night (Oct 6), Islanders @ Rangers and Golden Knights @
Kraken each show ONCE, as their NHL card, with Polymarket's price on it.**
(Pillar: MATCHING.)

#7904 made the Polymarket `icehockey_other` shadows hand their markets to the NHL
row and fold — but only at the venue's minute. Gamma lists two opening-night
games off ESPN's start (read 2026-09-29 21:2xZ):

    Gamma 994277 Islanders vs. Rangers       00:00Z   ESPN 401892452  23:30Z   30 min
    Gamma 994283 Golden Knights vs. Kraken   01:40Z   ESPN 401892454  01:00Z   40 min

so the matcher's 15-minute window found no NHL row (`phase15_catchall_shadow_
left_alone`) and the fold's exact minute never paired them: the Rangers' home
opener as an unpriced NHL card beside `OTHER HOCKEY · Rangers v Islanders` at
8:00 PM ET.

WHAT EACH TEST DEFENDS:

* the ship, both halves, at both measured drifts (30 and 40 min);
* 🔴 the bound is a bound: 90 min moves/folds, 91 does not;
* 🔴 exactly one NHL row in the window — two (a split-squad pair) refuse, and a
  row three hours away (the doubleheader shape) is never reached;
* 🔴 soccer keeps its own clock on both halves (#5918's 30-minute re-mints);
* 🔴 the fold widens ONLY for a shadow that carries nothing: a priced shadow, or
  one carrying any provider id, stays two cards at another minute.
"""

from datetime import timedelta

import pytest

from app.utils.event_twin_fold import CATCHALL_SHADOW_KICKOFF_DRIFT, fold_twin_events
from tests.test_nhl_reversed_shadow_shows_once_7904 import (
    BLUES,
    PUCK_DROP,
    SHARKS,
    _market,
    _new_rail,
    _Row,
    _run_phase15,
    _shadow,
    _SPORT_IDS,
)


def _nhl_row_at(session, nhl, offset, *, espn_id="401891825"):
    """The NHL row, `offset` from the venue's minute (the shadow's and the market's)."""
    from app.models.models import Event

    e = Event(
        sport_id=nhl.id, home_team_name=BLUES, away_team_name=SHARKS,
        commence_time=PUCK_DROP + offset, status="scheduled", espn_id=espn_id,
        commence_time_source="espn",
    )
    session.add(e)
    session.flush()
    return e


# --------------------------------------------------------------------------
# Half 1 — the matcher moves the shadow's market across the venue's wrong minute
# --------------------------------------------------------------------------


@pytest.mark.parametrize("minutes", [-30, -40, 40], ids=["rangers", "kraken", "later"])
@pytest.mark.asyncio
async def test_a_shadow_listed_off_espns_minute_hands_its_market_to_the_nhl_row(minutes):
    """🔴 THE SHIP. Master's 15-minute window left these on the shadow."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Sharks", home="Blues")
    real = _nhl_row_at(session, nhl, timedelta(minutes=minutes))
    market = _market(session, shadow)

    stats, link_changes = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == real.id, (
        f"a shadow {minutes} min off ESPN kept its market (event_id="
        f"{market.event_id}, shadow={shadow.id}, nhl={real.id})"
    )
    assert stats["funnel"]["phase15_catchall_shadow_named"] == 1
    assert link_changes


@pytest.mark.parametrize(
    ("minutes", "moves"), [(90, True), (-90, True), (91, False), (-91, False)],
)
@pytest.mark.asyncio
async def test_the_window_is_the_shared_bound(minutes, moves):
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Sharks", home="Blues")
    real = _nhl_row_at(session, nhl, timedelta(minutes=minutes))
    market = _market(session, shadow)

    await _run_phase15(session)

    session.refresh(market)
    assert (market.event_id == real.id) is moves
    assert CATCHALL_SHADOW_KICKOFF_DRIFT == timedelta(minutes=90)


@pytest.mark.asyncio
async def test_two_nhl_rows_in_the_window_leave_the_market_alone():
    """🔴 The finder still needs exactly ONE — a wider window must not pick."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Sharks", home="Blues")
    _nhl_row_at(session, nhl, timedelta(minutes=-30), espn_id="401891825")
    _nhl_row_at(session, nhl, timedelta(minutes=60), espn_id="401891826")
    market = _market(session, shadow)

    stats, _ = await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id
    assert stats["funnel"]["phase15_catchall_shadow_left_alone"] == 1


@pytest.mark.asyncio
async def test_a_doubleheader_distance_is_never_reached():
    """🔴 #8547's pair was 3.0h apart — the other game of the pair, never this one."""
    session, nhl, other = _new_rail()
    shadow = _shadow(session, other, away="Sharks", home="Blues")
    _nhl_row_at(session, nhl, timedelta(hours=-3))
    market = _market(session, shadow)

    await _run_phase15(session)

    session.refresh(market)
    assert market.event_id == shadow.id


@pytest.mark.asyncio
async def test_a_soccer_shadow_keeps_the_fifteen_minute_window():
    """🔴 The finder is asked with `_PM_VENUE_SAME_GAME` for soccer, the shared
    bound for everything else — captured at the call, not inferred."""
    from unittest.mock import patch

    from app.models.models import Sport
    from app.tasks import prediction_market_matching as task_mod

    asked = []

    async def _finder(*a, window=None, **k):
        asked.append((k.get("within_sport"), window))
        return None

    for key in ("soccer_other", "icehockey_other"):
        session, _nhl, _other = _new_rail()
        sport = session.query(Sport).filter_by(key=key).one_or_none()
        if sport is None:
            sport = Sport(key=key, name=key)
            session.add(sport)
            session.flush()
        shadow = _shadow(session, sport, away="Sharks", home="Blues")
        market = _market(session, shadow)
        market.llm_sport_category = key.split("_")[0]  # no cross-sport refusal
        session.commit()
        with patch.object(task_mod, "_venue_confirmed_covered_fixture", new=_finder):
            await _run_phase15(session)

    assert ("soccer", task_mod._PM_VENUE_SAME_GAME) in asked
    assert ("icehockey", CATCHALL_SHADOW_KICKOFF_DRIFT) in asked


# --------------------------------------------------------------------------
# Half 2 — the fold joins the emptied shadow across the venue's wrong minute
# --------------------------------------------------------------------------


_SPORT_IDS.setdefault("soccer_other", 45)
_SPORT_IDS.setdefault("soccer_usa_mls", 46)


def _nhl_card(offset, *, id=15169788, **kw):
    fields = dict(away=SHARKS, home=BLUES, sport_key="icehockey_nhl",
                  espn_id="401891825", sources={"kalshi": 0.53})
    fields.update(kw)
    row = _Row(id, **fields)
    row.commence_time = PUCK_DROP + offset
    return row


def _empty_shadow(**kw):
    fields = dict(away="Sharks", home="Blues", sport_key="icehockey_other")
    fields.update(kw)
    return _Row(15308567, **fields)


@pytest.mark.parametrize("minutes", [-30, -40, 30], ids=["rangers", "kraken", "later"])
def test_an_emptied_shadow_off_espns_minute_folds_onto_the_nhl_card(minutes):
    """🔴 THE SHIP's second half: one card, the NHL row's."""
    result = fold_twin_events([_nhl_card(timedelta(minutes=minutes)), _empty_shadow()])

    assert [row.id for row in result.events] == [15169788]
    assert result.survivor_of == {15308567: 15169788}


def test_an_emptied_reversed_shadow_off_the_minute_folds_too():
    shadow = _empty_shadow(away="Blues", home="Sharks")
    result = fold_twin_events([_nhl_card(timedelta(minutes=-40)), shadow])

    assert [row.id for row in result.events] == [15169788]


def test_identical_names_at_another_minute_fold_when_empty():
    """The exact-identity pass owns the same minute; nothing else reached this."""
    shadow = _empty_shadow(away=SHARKS, home=BLUES)
    result = fold_twin_events([_nhl_card(timedelta(minutes=-30)), shadow])

    assert [row.id for row in result.events] == [15169788]


@pytest.mark.parametrize("minutes", [91, -91])
def test_the_fold_stops_at_the_bound(minutes):
    result = fold_twin_events([_nhl_card(timedelta(minutes=minutes)), _empty_shadow()])

    assert sorted(row.id for row in result.events) == [15169788, 15308567]


@pytest.mark.parametrize(
    "shadow_kw",
    [
        {"sources": {"polymarket": 0.5425}},
        {"opening_home_probability": 0.54},
        {"espn_id": "401892452"},
        {"statpal_fixture_id": "652999"},
        {"external_id": "4b675b1d1c46d02ad5a8887c956e93cf"},
    ],
    ids=["priced", "opening_line", "espn_id", "statpal_id", "external_id"],
)
def test_only_an_empty_id_less_shadow_is_asked_across_the_drift(shadow_kw):
    """🔴 A priced shadow's home number could land on the wrong club, and a row
    somebody scheduled is not a shadow — both stay two cards at another minute."""
    result = fold_twin_events(
        [_nhl_card(timedelta(minutes=-30)), _empty_shadow(**shadow_kw)]
    )

    assert sorted(row.id for row in result.events) == [15169788, 15308567]


def test_two_nhl_cards_in_the_window_refuse_the_fold():
    """🔴 A split-squad pair (#7942): the shadow cannot say which one it is."""
    left = _nhl_card(timedelta(minutes=-30))
    right = _nhl_card(timedelta(minutes=45), id=15169799, espn_id="401891899")

    result = fold_twin_events([left, right, _empty_shadow()])

    assert sorted(row.id for row in result.events) == [15169788, 15169799, 15308567]


def test_a_soccer_catchall_keeps_the_exact_minute():
    """🔴 #5918's 30-minute re-mint class lives in `soccer_other`."""
    league = _Row(15320001, away="LA Galaxy", home="Seattle Sounders FC",
                  sport_key="soccer_usa_mls", espn_id="700001")
    league.commence_time = PUCK_DROP - timedelta(minutes=30)
    claim = _Row(15320002, away="LA Galaxy", home="Seattle Sounders FC",
                 sport_key="soccer_other")

    result = fold_twin_events([league, claim])

    assert sorted(row.id for row in result.events) == [15320001, 15320002]


def test_the_same_minute_fold_is_unchanged():
    """Control: master's case — an emptied shadow at the NHL row's own minute."""
    result = fold_twin_events([_nhl_card(timedelta(0)), _empty_shadow()])

    assert [row.id for row in result.events] == [15169788]
