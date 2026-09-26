"""#8841 clause 2 — ESPN's `timeValid=false` date is not a start time.

WHAT IS AT STAKE
================
Production, 2026-09-26: the Red Sox at Yankees Wild Card games (rows 15319235 /
15319236, StatPal-created, `commence_time_source='statpal'`, 20:00Z) have no
announced start. ESPN lists them as 401907924 / 401907963 with the date-only
placeholder `2026-09-29T04:00Z` and `timeValid=false` — measured the same day on
both payload shapes:

    scoreboard  competitions[0].timeValid = False   (event level: absent)
    summary     header.timeValid          = False   (header.competitions[0]: absent)

`_parse_event` ignored the flag. ESPN outranks StatPal in the start-time ranking
(#8653), so on game day, if ESPN still says `timeValid=false`, every ESPN rail
would move the row to 04:00Z — midnight Eastern, 9 PM Pacific the evening
BEFORE — and clear authority's new `start_is_tbd` with it (the stamp no longer
equals StatPal's placeholder).

The rule: `ESPNEvent.date` keeps the placeholder (the Eastern DATE is right and
matching needs it); every rail that WRITES ESPN's clock reads
`utils.espn_start_time.espn_start_time`, which is None when `timeValid=false`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService, espn_time_valid
from app.utils.espn_start_time import espn_start_time

#: The specimen, verbatim.
PLACEHOLDER = datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)       # ESPN T04:00Z
STATPAL_STAMP = datetime(2026, 9, 29, 20, 0, tzinfo=timezone.utc)    # StatPal 369024
SPECIMEN_ESPN_ID = "401907924"


def _competitor(side, name, abbr, team_id):
    return {
        "homeAway": side,
        "team": {
            "id": team_id, "name": name.split()[-1], "abbreviation": abbr,
            "displayName": name, "shortDisplayName": name.split()[-1],
            "location": name.rsplit(" ", 1)[0],
        },
    }


def _competition(**extra):
    return {
        "id": SPECIMEN_ESPN_ID,
        "date": "2026-09-29T04:00Z",
        "competitors": [
            _competitor("home", "New York Yankees", "NYY", "10"),
            _competitor("away", "Boston Red Sox", "BOS", "2"),
        ],
        "status": {"type": {"name": "STATUS_SCHEDULED", "shortDetail": "TBD"}},
        **extra,
    }


def _board_event(**competition_extra):
    """The scoreboard shape: `timeValid` on competitions[0], not the event."""
    return {
        "id": SPECIMEN_ESPN_ID,
        "name": "Boston Red Sox at New York Yankees",
        "shortName": "BOS @ NYY",
        "date": "2026-09-29T04:00Z",
        "season": {"type": 3},
        "status": {"type": {"name": "STATUS_SCHEDULED", "shortDetail": "TBD"}},
        "competitions": [_competition(**competition_extra)],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. The parser reads the flag on both payload shapes
# ─────────────────────────────────────────────────────────────────────────────


class TestTheParserReadsTimeValid:
    def test_scoreboard_shape_false(self):
        ee = ESPNAPIService()._parse_event(_board_event(timeValid=False))
        assert ee is not None
        assert ee.time_valid is False
        # The date survives — matching and board-day reads need it.
        assert ee.date == PLACEHOLDER
        assert espn_start_time(ee) is None

    def test_summary_shape_false(self):
        """`get_event` spreads `header` into the top level; `timeValid` rides it."""
        header = {"id": SPECIMEN_ESPN_ID, "timeValid": False, "season": {"type": 3}}
        ee = ESPNAPIService()._parse_event({"competitions": [_competition()], **header})
        assert ee is not None
        assert ee.time_valid is False
        assert espn_start_time(ee) is None

    def test_get_event_carries_the_header_flag(self, monkeypatch):
        """Through the real `get_event`, from a summary body shaped as measured."""
        service = ESPNAPIService()
        body = {
            "header": {
                "id": SPECIMEN_ESPN_ID,
                "timeValid": False,
                "season": {"type": 3},
                "competitions": [_competition()],
            }
        }

        async def _fake_get(_url, *a, **k):
            return body

        monkeypatch.setattr(service, "_get", _fake_get)
        ee = asyncio.run(service.get_event("baseball_mlb", SPECIMEN_ESPN_ID))
        assert ee is not None and ee.time_valid is False
        assert espn_start_time(ee) is None

    def test_announced_start_is_a_start(self):
        ee = ESPNAPIService()._parse_event(_board_event(timeValid=True))
        assert ee.time_valid is True
        assert espn_start_time(ee) == PLACEHOLDER

    def test_absent_flag_reads_valid(self):
        """No payload without the key changes behaviour."""
        ee = ESPNAPIService()._parse_event(_board_event())
        assert ee.time_valid is True
        assert espn_start_time(ee) == PLACEHOLDER

    @pytest.mark.parametrize(
        "competition,event,expected",
        [
            ({"timeValid": False}, {}, False),
            ({}, {"timeValid": False}, False),
            ({"timeValid": True}, {"timeValid": False}, True),  # competition wins
            ({}, {}, True),
            ({"timeValid": None}, {}, True),
        ],
    )
    def test_espn_time_valid(self, competition, event, expected):
        assert espn_time_valid(competition, event) is expected

    def test_a_fake_without_the_flag_keeps_its_date(self):
        class _Fake:
            date = STATPAL_STAMP

        assert espn_start_time(_Fake()) == STATPAL_STAMP


# ─────────────────────────────────────────────────────────────────────────────
# 2. ESPN's live pass — `update_event_fields_from_espn`, on a real (sqlite) row
# ─────────────────────────────────────────────────────────────────────────────


def _live_pass(*, time_valid: bool):
    """ESPN updates the StatPal-stamped Wild Card row with the placeholder date."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.models import (
        Base, ESPNSnapshot, Event, ScoreSnapshot, Sport, WinProbSnapshot,
    )
    from app.services.espn_api import ESPNEvent, ESPNTeam
    from app.utils.espn_helpers import update_event_fields_from_espn
    from tests.test_start_time_follows_the_registry_ranking_8653 import (
        _AsyncShim, _utc_on_load,
    )

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__, Sport.__table__, ScoreSnapshot.__table__,
            ESPNSnapshot.__table__, WinProbSnapshot.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)
    _utc_on_load(session)
    sport = Sport(key="baseball_mlb", name="MLB")
    session.add(sport)
    session.flush()
    session.add(Event(
        sport_id=sport.id,
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        commence_time=STATPAL_STAMP,
        commence_time_source="statpal",
        status="scheduled",
        espn_id=SPECIMEN_ESPN_ID,
        win_probability_sources={},
    ))
    session.commit()
    row = session.execute(select(Event)).scalar_one()

    def _team(espn_id, display, short, abbr):
        return ESPNTeam(
            espn_id=espn_id, name=short, abbreviation=abbr,
            display_name=display, short_name=short, nickname=short,
            primary_color=None, secondary_color=None, logo_url=None,
            logo_url_dark=None, record=None, location=display.rsplit(" ", 1)[0],
        )

    ee = ESPNEvent(
        espn_id=SPECIMEN_ESPN_ID,
        name="Boston Red Sox at New York Yankees",
        short_name="BOS @ NYY",
        date=PLACEHOLDER,
        status="scheduled",
        status_detail="TBD",
        period=None,
        clock=None,
        home_team=_team("10", "New York Yankees", "Yankees", "NYY"),
        away_team=_team("2", "Boston Red Sox", "Red Sox", "BOS"),
        home_score=None,
        away_score=None,
        venue=None,
        broadcasts=[],
        home_win_probability=None,
        season_type=3,
        time_valid=time_valid,
    )
    asyncio.run(update_event_fields_from_espn(_AsyncShim(session), row, ee, set(), {}))
    session.commit()
    session.expunge_all()
    return session.execute(select(Event)).scalar_one()


class TestEspnLivePass:
    def test_the_specimen_keeps_its_statpal_stamp(self):
        """THE GUARD. `timeValid=false` must not move 20:00Z to 04:00Z."""
        got = _live_pass(time_valid=False)
        assert got.commence_time == STATPAL_STAMP, (
            "ESPN's timeValid=false date is midnight Eastern, not a start; "
            f"the row moved to {got.commence_time} (#8841)."
        )
        assert got.commence_time_source == "statpal"

    def test_control_an_announced_espn_start_still_corrects(self):
        """The same inputs with the flag flipped DO move — the rail is live."""
        got = _live_pass(time_valid=True)
        assert got.commence_time == PLACEHOLDER
        assert got.commence_time_source == "espn"


# ─────────────────────────────────────────────────────────────────────────────
# 3. ESPN's scheduled pass — `sync_scheduled_events`
# ─────────────────────────────────────────────────────────────────────────────


def _scheduled_pass(monkeypatch, *, time_valid: bool):
    """#8653's rig, flag on the ESPN reading. 35 minutes apart, so the #1947
    same-game window allows the move and only the flag can refuse it."""
    from app.utils import espn_helpers
    from tests.test_start_time_follows_the_registry_ranking_8653 import (
        ESPN_START, OUR_STALE_START, _Row,
    )

    class _Team(_Row):
        def __init__(self, name):
            super().__init__(display_name=name, name=name)

    class _Sport:
        id = 53232
        key = "baseball_mlb"

    event = _Row(
        id=15319235, espn_id=SPECIMEN_ESPN_ID, sport=_Sport(), sport_id=_Sport.id,
        home_team_name="Boston Red Sox", away_team_name="Chicago Cubs",
        home_team_normalized=None, away_team_normalized=None,
        home_team_id=1, away_team_id=2,
        commence_time=OUR_STALE_START, commence_time_source="statpal",
        broadcast_info=None, llm_importance=None, status="scheduled",
    )
    ee = _Row(
        espn_id=SPECIMEN_ESPN_ID,
        home_team=_Team("Boston Red Sox"), away_team=_Team("Chicago Cubs"),
        date=ESPN_START, broadcasts=[], season_type=None, time_valid=time_valid,
    )

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    calls = {"n": 0}

    class _Session:
        async def execute(self, *_a, **_k):
            calls["n"] += 1
            return _Result([event] if calls["n"] == 1 else [])

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(espn_helpers, "upsert_team", _noop)
    monkeypatch.setattr(espn_helpers, "register_espn_team_identities", _noop)
    asyncio.run(espn_helpers.sync_scheduled_events(_Session(), "baseball_mlb", [ee], {}))
    return event, OUR_STALE_START, ESPN_START


class TestEspnScheduledPass:
    def test_an_unannounced_start_does_not_move_the_row(self, monkeypatch):
        event, ours, _ = _scheduled_pass(monkeypatch, time_valid=False)
        assert event.commence_time == ours
        assert event.commence_time_source == "statpal"

    def test_control_an_announced_start_does(self, monkeypatch):
        event, _, espn = _scheduled_pass(monkeypatch, time_valid=True)
        assert event.commence_time == espn
        assert event.commence_time_source == "espn"


# ─────────────────────────────────────────────────────────────────────────────
# 4. The registry fold — the game-day path the issue names
# ─────────────────────────────────────────────────────────────────────────────


def _fold(*, placeholder: bool):
    from app.services.event_registry import (
        EventClaim, EventIdentity, _update_fields_by_priority,
    )
    from tests.test_start_time_follows_the_registry_ranking_8653 import _Row

    event = _Row(
        id=15319235,
        home_team_name="New York Yankees", away_team_name="Boston Red Sox",
        commence_time=STATPAL_STAMP, commence_time_source="statpal",
        completed_at=None, status="scheduled",
    )
    identity = EventIdentity(
        sport_key="baseball_mlb",
        home_team_name="New York Yankees",
        away_team_name="Boston Red Sox",
        commence_time=PLACEHOLDER,
        claim=EventClaim("espn", SPECIMEN_ESPN_ID, schedule_derived=True),
        commence_time_source="espn",
        status="scheduled",
        commence_time_is_placeholder=placeholder,
    )
    _update_fields_by_priority(event, identity, same_record=False)
    return event


class TestRegistryFold:
    def test_a_placeholder_claim_does_not_overwrite_the_clock(self):
        event = _fold(placeholder=True)
        assert event.commence_time == STATPAL_STAMP
        assert event.commence_time_source == "statpal"

    def test_control_a_real_espn_start_does(self):
        event = _fold(placeholder=False)
        assert event.commence_time == PLACEHOLDER
        assert event.commence_time_source == "espn"

    def test_the_default_is_not_a_placeholder(self):
        from app.services.event_registry import EventClaim, EventIdentity

        identity = EventIdentity(
            sport_key="baseball_mlb", home_team_name="a", away_team_name="b",
            commence_time=PLACEHOLDER, claim=EventClaim("espn", "1"),
        )
        assert identity.commence_time_is_placeholder is False

    def test_the_espn_claim_site_sets_the_flag_from_espn_start_time(self):
        """The only ESPN registry claim wires the flag, and from the one reader."""
        import inspect

        from app.utils import espn_helpers

        src = inspect.getsource(espn_helpers)
        claim_at = src.index('claim=_EC("espn", ee.espn_id, schedule_derived=True)')
        window = src[claim_at: claim_at + 600]
        assert "commence_time_is_placeholder=espn_start_time(ee) is None" in window


# ─────────────────────────────────────────────────────────────────────────────
# 5. The Odds-listing cross-reference — `select_espn_candidate`
# ─────────────────────────────────────────────────────────────────────────────


class TestCandidateSelection:
    def _pick(self, time_valid):
        from app.utils.espn_candidate_selection import select_espn_candidate
        from tests.test_start_time_follows_the_registry_ranking_8653 import _Row

        listing = STATPAL_STAMP
        ee = _Row(
            espn_id=SPECIMEN_ESPN_ID,
            home_team=_Row(display_name="New York Yankees", name="Yankees"),
            away_team=_Row(display_name="Boston Red Sox", name="Red Sox"),
            date=listing + timedelta(minutes=10),
            time_valid=time_valid,
        )
        return select_espn_candidate(
            [ee], "New York Yankees", "Boston Red Sox", listing,
        ), ee

    def test_the_id_joins_but_the_placeholder_is_no_start(self):
        (start, espn_id), _ = self._pick(False)
        assert espn_id == SPECIMEN_ESPN_ID
        assert start is None

    def test_control_an_announced_start_is_returned(self):
        (start, espn_id), ee = self._pick(True)
        assert espn_id == SPECIMEN_ESPN_ID
        assert start == ee.date
