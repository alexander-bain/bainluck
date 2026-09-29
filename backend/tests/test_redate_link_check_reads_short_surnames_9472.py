"""A Challenger match with a short-surname player reads LIVE only once it starts — #9472.

**SHIP: Tomic v Sun, Kozlov v Kim and every tennis row stored by a <=3-letter
surname move to the venue's start, instead of reading LIVE hours early.**
(Pillars: TRUTH, MATCHING.)

#9473 taught Phase 1.5's mislink arm to read `Cui` v `Jie Cui`. Its sibling, the
re-date link check (`phase15_link_is_valid_for_redate`), still asked
``_fuzzy_team_match`` of the RAW market name, whose containment floor is 4, so
every Polymarket leg on these rows was refused as ``teams_absent``. That check
gates both Phase 1.5's re-date and #9418's heavy refresher. Production
2026-09-29 04:26Z (live/754): the refresher reported ``refused_link: 3`` — the
three short-surname rows of 260 — and

    15320530  Tomic v Sun    commence 03:00Z, status live
              62853398 "Jingshan: Bernard Tomic vs Fajing Sun"
              venue_game_start 07:35Z
    15320860  Kozlov v Kim   commence 14:00Z
              62715379 "Columbus: Stefan Kozlov vs Aidan Kim"
              venue_game_start 21:00Z

WHAT EACH TEST DEFENDS:

* the ship — the refresher re-dates and un-starts the Tomic v Sun specimen;
* the check itself admits the production names, prefix and surname-only lines;
* 🔴 a market naming another player is still refused, straight or via prefix;
* 🔴 the arm is tennis-only — the same names on a non-tennis row stay refused.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.test_phase15_redates_polymarket_listing_stamp_6073 import (
    _AsyncShim as _Shim6073,
    _event as _event_6073,
    _market as _market_6073,
    _new_rail,
)
from tests.test_polymarket_fixture_start_refresh_9418 import (
    _Service,
    _event,
    _market,
    _rail,
    _run,
)

LISTING_START = datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)
VENUE_START = datetime(2026, 9, 29, 7, 35, tzinfo=timezone.utc)
GROUP = "polymarket:1092875"
MONEYLINE = "Jingshan: Bernard Tomic vs Fajing Sun"

SPECIMEN = {
    "id": "1092875",
    "title": MONEYLINE,
    "live": False,
    "ended": False,
    "startTime": "2026-09-29T07:35:00Z",
    "startDate": "2026-09-28T09:12:00Z",
    "endDate": "2026-10-06T08:00:00Z",
    "markets": [{"question": MONEYLINE, "gameStartTime": "2026-09-29 07:35:00+00"}],
}

#: (market name, row home, row away) — production, verbatim.
ADMITTED = [
    (MONEYLINE, "Tomic", "Sun"),
    ("Columbus: Stefan Kozlov vs Aidan Kim", "Kozlov", "Kim"),
    ("Tomic vs. Sun: Match O/U 22.5", "Tomic", "Sun"),
    ("Bernard Tomic vs. Fajing Sun: Total Sets O/U 2.5", "Tomic", "Sun"),
]


# ── The ship ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_refresher_moves_tomic_v_sun_to_the_venue_start_and_unstarts_it(monkeypatch):
    from app.models.models import Event

    session, sport = _rail()
    event = _event(session, sport, commence=LISTING_START, home="Tomic", away="Sun")
    _market(session, event, group=GROUP, name=MONEYLINE,
            external_id="1092875-parent", event_id=False, group_type="polymarket_event",
            stamp="2026-09-29T03:00:00+00:00")
    _market(session, event, group=GROUP, name=MONEYLINE,
            stamp="2026-09-29T03:00:00+00:00")

    stats = await _run(monkeypatch, session, _Service([SPECIMEN]),
                       datetime(2026, 9, 29, 4, 26, tzinfo=timezone.utc))

    row = session.get(Event, event.id)
    assert stats["refused_link"] == 0
    assert row.commence_time.replace(tzinfo=timezone.utc) == VENUE_START
    assert row.status == "scheduled"
    assert stats["redated_and_unstarted"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name,home,away", ADMITTED)
async def test_the_redate_link_check_admits_the_production_names(name, home, away):
    from app.tasks.prediction_market_matching import (
        _fuzzy_team_match,
        phase15_link_is_valid_for_redate,
    )

    # The precondition: the raw test alone refuses every one of these.
    assert not (_fuzzy_team_match(name, home) and _fuzzy_team_match(name, away))

    session, tennis = _new_rail()
    event = _event_6073(session, tennis)
    event.home_team_name, event.away_team_name = home, away
    session.flush()
    market = _market_6073(session, event, name=name)

    ok, why = await phase15_link_is_valid_for_redate(_Shim6073(session), market, event)
    assert (ok, why) == (True, "ok")


# ── Still refused ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("name", [
    "Jingshan: Bernard Tomic vs Alex Bolt",       # one player differs
    "Jingshan: Fajing Sun vs Yibing Wu",          # the short one agrees, the other not
    "Sun vs Sun",                                 # Kalshi's own broken line on this row
    "Set 1 Winner: Bernard Tomic vs Alex Bolt",   # prop the splitters cannot read
])
async def test_a_market_about_another_player_is_still_refused(name):
    from app.tasks.prediction_market_matching import phase15_link_is_valid_for_redate

    session, tennis = _new_rail()
    event = _event_6073(session, tennis)
    event.home_team_name, event.away_team_name = "Tomic", "Sun"
    session.flush()
    market = _market_6073(session, event, name=name)

    ok, why = await phase15_link_is_valid_for_redate(_Shim6073(session), market, event)
    assert (ok, why) == (False, "teams_absent")


@pytest.mark.asyncio
async def test_the_arm_is_tennis_only():
    from app.models.models import Sport
    from app.tasks.prediction_market_matching import phase15_link_is_valid_for_redate

    session, _tennis = _new_rail()
    table = Sport(key="basketball_other", name="Basketball (other)")
    session.add(table)
    session.flush()
    event = _event_6073(session, table)
    event.home_team_name, event.away_team_name = "Tomic", "Sun"
    session.flush()
    market = _market_6073(session, event, name=MONEYLINE)

    ok, why = await phase15_link_is_valid_for_redate(_Shim6073(session), market, event)
    assert (ok, why) == (False, "teams_absent")


# ── The pure helper ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,home,away,expected", [
    (MONEYLINE, "Tomic", "Sun", True),
    (MONEYLINE, "Sun", "Tomic", True),                    # either orientation
    ("Tomic vs. Sun: Match O/U 22.5", "Tomic", "Sun", True),
    (MONEYLINE, "Tomic", "Wu", False),
    ("Game Spread: Bernard Tomic (-2.5) vs Fajing Sun (+2.5)", "Tomic", "Sun", False),
    ("", "Tomic", "Sun", False),
    (None, "Tomic", "Sun", False),
])
def test_raw_name_helper(name, home, away, expected):
    from app.tasks.prediction_market_matching import _tennis_raw_name_players_agree

    assert _tennis_raw_name_players_agree("tennis_other", name, home, away) is expected


@pytest.mark.parametrize("sport_key", [None, "", "basketball_nba", "table_tennis"])
def test_raw_name_helper_refuses_off_tennis(sport_key):
    from app.tasks.prediction_market_matching import _tennis_raw_name_players_agree

    assert _tennis_raw_name_players_agree(sport_key, MONEYLINE, "Tomic", "Sun") is False
