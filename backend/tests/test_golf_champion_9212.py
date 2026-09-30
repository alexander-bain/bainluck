"""#9212: a finished golf tournament serves who won, not a live leader at a price.

Seen on production 2026-09-27 21:27Z, `/sports` at 390px: the FedEx Open de
France card read "● LIVE" and "100.0% Matthew Fitzpatrick · Leader" hours after
the final round ended. `/api/feed?mode=sports` had nothing that said "decided":
`schedule_status` was DataGolf's `upcoming` (it never moves, #7450), the server
headline read "Live", and the reason read "Fitzpatrick leads at 100.0%".

The venues' grades cannot be the signal (read on production 23:4xZ): Kalshi's
winner row went `resolved` at 14:15Z with no winner; Polymarket graded
Fitzpatrick at 23:38Z; our DataGolf winner market was graded off the round-3
leaderboard at 02:15Z, before the final round. ESPN's scoreboard said
`STATUS_FINAL` with Fitzpatrick `order` 1 — the authority.

This is the SERVE half: the golf base carries `champion` and the feed item
serves it. The card and its section read it in ux's half (TournamentCard,
feedSections), which is the consumer of this field.

No test reaches the network: ESPN is a MockTransport and the golf base is stubbed.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.routes import golf as golf_mod
from app.services.espn_api import (
    ESPNAPIService,
    espn_golf_champion,
    reset_espn_authority_state,
)


# ── ESPN's word: who won ─────────────────────────────────────────────────────


def _competitor(order, name, *, winner=None, team=False):
    c = {"order": order, "score": "-20"}
    if winner is not None:
        c["winner"] = winner
    c["team" if team else "athlete"] = {"displayName": name}
    return c


def _event(status="STATUS_FINAL", state="post", competitors=None, name="FedEx Open de France"):
    # Shaped as ESPN's golf/eur scoreboard served it 2026-09-27 23:5xZ.
    return {
        "name": name,
        "date": "2026-09-24T04:00Z",
        "endDate": "2026-09-27T04:00Z",
        "status": {"type": {"name": status, "state": state, "completed": state == "post"}},
        "competitions": [{
            "competitors": competitors if competitors is not None else [
                _competitor(1, "Matt Fitzpatrick"),
                _competitor(2, "Angel Hidalgo"),
                _competitor(3, "Matthieu Pavon"),
            ],
        }],
    }


def test_stroke_play_final_names_order_one():
    assert espn_golf_champion(_event()) == "Matt Fitzpatrick"


def test_team_final_names_the_side_espn_flags():
    # Presidents Cup, same board read: USA order 1 winner true, INTL winner false.
    event = _event(name="Presidents Cup", competitors=[
        _competitor(1, "USA", winner=True, team=True),
        _competitor(2, "INTL", winner=False, team=True),
    ])
    assert espn_golf_champion(event) == "USA"


def test_the_flag_outranks_the_order():
    event = _event(competitors=[
        _competitor(1, "A Golfer"),
        _competitor(2, "The Winner", winner=True),
    ])
    assert espn_golf_champion(event) == "The Winner"


@pytest.mark.parametrize("status,state", [
    ("STATUS_IN_PROGRESS", "in"),
    ("STATUS_PLAY_SUSPENDED", "in"),
    ("STATUS_SCHEDULED", "pre"),
    ("STATUS_CANCELED", "post"),
    (None, None),
])
def test_only_a_final_has_a_champion(status, state):
    # The leaderboard still has an order 1 in every one of these.
    assert espn_golf_champion(_event(status=status, state=state)) is None


@pytest.mark.parametrize("competitors", [
    [],
    [_competitor(1, "One"), _competitor(1, "Two")],
    [_competitor(2, "Nobody First")],
    [_competitor(1, "")],
])
def test_no_single_answer_is_no_champion(competitors):
    assert espn_golf_champion(_event(competitors=competitors)) is None


@pytest.fixture
def espn_state():
    reset_espn_authority_state()
    yield
    reset_espn_authority_state()


@pytest.mark.asyncio
async def test_the_scoreboard_read_carries_the_champion(espn_state):
    board = {"events": [_event(), _event(name="Other", status="STATUS_IN_PROGRESS", state="in")]}
    service = ESPNAPIService(timeout=1.0, rate_limit_delay=0.0,
                             transport=httpx.MockTransport(lambda r: httpx.Response(200, json=board)))
    try:
        events = await service.get_golf_scoreboard("eur")
    finally:
        await service.close()
    assert [(e["name"], e["status"], e["champion"]) for e in events] == [
        ("FedEx Open de France", "STATUS_FINAL", "Matt Fitzpatrick"),
        ("Other", "STATUS_IN_PROGRESS", None),
    ]


# ── the schedule overlay ─────────────────────────────────────────────────────


def _entry(name="FedEx Open de France", key="fedex_open_de_france", tour="euro",
           status="upcoming", start="2026-09-24", end="2026-09-27"):
    return {
        "name": name,
        "key": key,
        "start_date": f"{start}T00:00:00+00:00" if start else None,
        "end_date": f"{end}T00:00:00+00:00" if end else None,
        "venue": "Le Golf National",
        "location": "Guyancourt, France",
        "status": status,
        "round": "",
        "tour": tour,
    }


def _board_event(name="FedEx Open de France", status="STATUS_FINAL", champion="Matt Fitzpatrick",
                 start="2026-09-24T04:00Z"):
    # The shape `get_golf_scoreboard` returns.
    return {"name": name, "start": start, "end": "2026-09-27T04:00Z",
            "state": "post" if status == "STATUS_FINAL" else "in",
            "status": status, "champion": champion}


def _overlaid(entry, board):
    [out] = golf_mod._overlay_espn_champion([entry], board)
    return out


def test_a_final_carries_its_champion_onto_the_entry():
    out = _overlaid(_entry(), {"euro": [_board_event()]})
    assert out["champion"] == "Matt Fitzpatrick"


def test_the_status_is_left_alone_so_the_card_survives():
    # `completed` is what `_filter_stale_tournaments` drops. The evening a
    # tournament ends the reader needs its result, so the card must stay.
    out = _overlaid(_entry(), {"euro": [_board_event()]})
    assert out["status"] == "upcoming"
    t = {**out, "schedule_status": out["status"]}
    now = datetime(2026, 9, 27, 23, 50, tzinfo=timezone.utc)
    assert golf_mod._filter_stale_tournaments([t], now) == [t]


def test_control_without_espn_there_is_no_champion():
    assert "champion" not in _overlaid(_entry(), {})


@pytest.mark.parametrize("board", [
    {"pga": [_board_event()]},                                   # another tour
    {"euro": [_board_event(name="Ryder Cup")]},                  # another tournament
    {"euro": [_board_event(start="2025-09-25T04:00Z")]},         # last edition
    {"euro": [_board_event(status="STATUS_IN_PROGRESS", champion=None)]},
    {"euro": [_board_event(status="STATUS_IN_PROGRESS")]},       # not final, whatever it names
    {"euro": [_board_event(champion=None)]},                     # final, no single answer
])
def test_what_must_not_crown_the_entry(board):
    assert "champion" not in _overlaid(_entry(), board)


def test_the_cached_entries_are_never_mutated():
    entry, sibling = _entry(), _entry(name="Ryder Cup", key="ryder_cup")
    out = golf_mod._overlay_espn_champion([entry, sibling], {"euro": [_board_event()]})
    assert "champion" not in entry
    assert out[0] is not entry and out[0]["champion"] == "Matt Fitzpatrick"
    assert out[1] is sibling


@pytest.mark.asyncio
async def test_the_loader_applies_both_overlays(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(golf_mod, "_get_datagolf_schedule", AsyncMock(return_value=[_entry()]))
    monkeypatch.setattr(golf_mod, "_get_espn_golf_scoreboards",
                        AsyncMock(return_value={"euro": [_board_event()]}))
    [out] = await golf_mod._get_golf_schedule()
    assert out["champion"] == "Matt Fitzpatrick"


# ── the tournament entry spells the champion as its own field row does ───────


def _tournament_entry(golfer_names):
    return {"key": "fedex_open_de_france", "name": "FedEx Open de France",
            "golfers": [{"name": n} for n in golfer_names]}


def test_enrich_copies_the_champion_in_the_cards_spelling():
    t = _tournament_entry(["Matthew Fitzpatrick", "Angel Hidalgo"])
    sched = {**_entry(), "champion": "Matt Fitzpatrick"}
    golf_mod._enrich_with_schedule([t], {"fedex_open_de_france": sched})
    assert t["champion"] == "Matthew Fitzpatrick"


def test_a_champion_the_card_does_not_list_keeps_espns_name():
    t = _tournament_entry(["Angel Hidalgo"])
    golf_mod._enrich_with_schedule([t], {"fedex_open_de_france": {**_entry(), "champion": "Matt Fitzpatrick"}})
    assert t["champion"] == "Matt Fitzpatrick"


def test_enrich_without_a_champion_serves_none():
    t = _tournament_entry(["Matthew Fitzpatrick"])
    golf_mod._enrich_with_schedule([t], {"fedex_open_de_france": _entry()})
    assert t["champion"] is None


# ── the feed item ────────────────────────────────────────────────────────────

# Inside the tournament's window, with the winner's movement still on the row —
# the two arms that kept the card LIVE after the final putt.
_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)


def _base_tournament(champion):
    t = {
        "key": "fedex_open_de_france",
        "name": "FedEx Open de France",
        "slug": "fedex-open-de-france",
        "tour": "dp_world",
        "tour_label": "DP World Tour",
        "is_major": False,
        "is_tour_event": True,
        "schedule_status": "upcoming",
        "commence_time": (_FEED_NOW - timedelta(days=3)).isoformat(),
        "resolution_date": _FEED_NOW.isoformat(),
        "start_date": (_FEED_NOW - timedelta(days=3)).isoformat(),
        "end_date": _FEED_NOW.isoformat(),
        "market_names": ["DP World Tour: Open de France Winner"],
        "market_ids": [61814765],
        "golfers": [{
            "id": 1, "name": "Matthew Fitzpatrick", "probability": 1.0,
            "movement_24h": 0.1695, "movement_is_dated": True, "rank": 1,
        }],
    }
    if champion is not None:
        t["champion"] = champion
    return t


def _card(monkeypatch, champion):
    import app.utils.golf_base as golf_base
    from app.routes import feed as feed_module

    async def _fake_base(db, now, stages=None):
        return ([_base_tournament(champion)], "fresh")

    monkeypatch.setattr(golf_base, "get_golf_base", _fake_base)
    items = asyncio.run(feed_module._score_golf_tournaments(None, _FEED_NOW, None, None))
    assert len(items) == 1, f"card dropped, so nothing about it is tested: {items}"
    return items[0]


def test_a_decided_card_serves_its_champion(monkeypatch):
    card = _card(monkeypatch, "Matthew Fitzpatrick")
    assert card["data"]["champion"] == "Matthew Fitzpatrick"
    assert card["headline"] == "Final"
    assert card["reason"] == "DP World Tour: Matthew Fitzpatrick won"


def test_a_decided_card_is_not_live(monkeypatch):
    from app.routes.feed import _tournament_is_live
    decided = _base_tournament("Matthew Fitzpatrick")
    assert _tournament_is_live(decided, _FEED_NOW) is False
    assert "leads" not in _card(monkeypatch, "Matthew Fitzpatrick")["reason"]
    assert "today" not in _card(monkeypatch, "Matthew Fitzpatrick")["reason"]


def test_control_the_same_card_without_a_champion_is_the_defect_as_served(monkeypatch):
    # The frame #9212 photographed: in the window, 100% "leader", LIVE.
    from app.routes.feed import _tournament_is_live
    assert _tournament_is_live(_base_tournament(None), _FEED_NOW) is True
    card = _card(monkeypatch, None)
    assert card["data"].get("champion") is None  # `.get`: green on the parent too
    assert card["headline"] == "Live"
    assert card["reason"].startswith("DP World Tour: Matthew Fitzpatrick leads at 100.0%")
