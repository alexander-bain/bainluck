"""#1106 — a DataGolf outcome first seen after its tournament started stores no
opening, so its movement stops reading "100% at open".

WHAT WAS WRONG. Both DataGolf writers create an unseen outcome with
`opening_probability = prob`, whatever the clock says. The in-play beat meets
a make-cut field after the cut and every survivor "opened" at 1.0 (2026-08-14:
2,270 such openings across 102 markets; "Indianapolis - Make the Cut" had its
whole 57-player field opening at 1.0). Movement is `current - opening`, so
those rows read as if the market had been certain from the start.

THE RULE IS ON TIME, NOT VALUE. A pre-tournament 0.0 or 1.0 is a real price
and must stay the opening, so every post-start arm below runs beside a
pre-start control carrying the same 1.0. A guard written on the value would
pass the post-start arms and fail the 1.0 control.

The writers are driven for real over the #7935 / #7958 rigs (the same fake
session and real payload models), not read as source: the mutation this has
to survive — the bare `opening_probability=prob` coming back at one site —
leaves every word of the file in place.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import app.services.datagolf_api as datagolf_api
import app.tasks.base as task_base
import app.tasks.datagolf as datagolf
import app.tasks.redis_state as redis_state
from app.models.models import FuturesMarket, FuturesOutcome

from tests.test_datagolf_one_price_writer_per_phase_7935 import (  # noqa: E402
    EURO_EVENT_ID,
    PGA_EVENT_ID,
    _FakeRedis,
    _FakeService,
    _FakeSession,
    _player,
    _tournament,
)
from tests.test_datagolf_inplay_owner_pinned_to_event_7958 import (  # noqa: E402
    LIVE_EVENT_NAME,
    _run_live,
)

DataGolfPlayer = datagolf_api.DataGolfPlayer

NEW_PLAYER_ID = 55501
CONTROL_PLAYER_ID = 55502


# ------------------------------------------------------------ the helper --


class TestTheHelper:
    START = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def test_before_the_start_the_price_is_the_opening(self):
        now = self.START - timedelta(seconds=1)
        assert datagolf._creation_opening(0.42, self.START, now) == 0.42

    @pytest.mark.parametrize("prob", [0.0, 1.0])
    def test_a_pre_start_certainty_is_still_an_opening(self, prob):
        now = self.START - timedelta(hours=6)
        assert datagolf._creation_opening(prob, self.START, now) == prob

    @pytest.mark.parametrize("seconds_after", [0, 1, 86_400 * 2])
    def test_at_or_after_the_start_there_is_no_opening(self, seconds_after):
        now = self.START + timedelta(seconds=seconds_after)
        assert datagolf._creation_opening(0.42, self.START, now) is None
        assert datagolf._creation_opening(1.0, self.START, now) is None

    def test_an_unplaceable_start_fails_closed(self):
        """As the accuracy page's #5355 rule does for a NULL commence_time."""
        now = self.START - timedelta(days=3)
        assert datagolf._creation_opening(0.42, None, now) is None


# --------------------------------------- the pre-tournament poll (site 1) --


def _run_pre_tournament(monkeypatch, *, tour, event_id, start_offset, players):
    """The real `_poll_datagolf_markets` over an EMPTY world.

    Empty on purpose: the poll creates the markets itself, so `commence_time`
    is the one the writer derives from DataGolf's start date — the value the
    guard reads in production — rather than one a fixture chose.
    """
    session = _FakeSession({}, {}, {})
    service = _FakeService(
        {tour: [_tournament(tour, event_id, f"{tour} open", start_offset)]},
        {tour: players},
    )
    # No in-play ownership: an in-window event with no beat writing it is
    # exactly when this poll still creates outcomes after the start (#7935).
    redis = _FakeRedis({})

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(datagolf, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(datagolf_api, "DataGolfAPIService", lambda *a, **kw: service)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **kw: redis)
    monkeypatch.setattr(datagolf, "POLL_TOURS", [tour])

    asyncio.run(datagolf._poll_datagolf_markets())
    return session


def _created_make_cut(session, dg_id) -> FuturesOutcome:
    markets = {
        m.id: m for m in session.added if isinstance(m, FuturesMarket)
    }
    cut_ids = {
        mid for mid, m in markets.items() if m.external_id.endswith(":make_cut")
    }
    found = [
        o for o in session.added
        if isinstance(o, FuturesOutcome)
        and o.market_id in cut_ids
        and o.external_id == f"dg_{dg_id}"
    ]
    assert len(found) == 1, (
        f"the poll did not create exactly one make-cut leg for dg_{dg_id} "
        f"({len(found)}) — the rig is not exercising the creation branch"
    )
    return found[0]


class TestThePreTournamentPoll:
    def test_a_leg_created_mid_tournament_stores_no_opening(self, monkeypatch):
        session = _run_pre_tournament(
            monkeypatch, tour="pga", event_id=PGA_EVENT_ID, start_offset=-1,
            players=[_player(NEW_PLAYER_ID, "Late Alternate", 1.0)],
        )
        leg = _created_make_cut(session, NEW_PLAYER_ID)
        assert float(leg.current_probability) == 1.0, (
            "the live price must still be written — the guard is on the opening only"
        )
        assert leg.opening_probability is None, (
            "an outcome first seen a day into the tournament recorded "
            f"{leg.opening_probability} as its opening (#1106)"
        )

    def test_a_pre_start_certainty_is_kept_as_the_opening(self, monkeypatch):
        """The control that refuses a value-based guard."""
        session = _run_pre_tournament(
            monkeypatch, tour="euro", event_id=EURO_EVENT_ID, start_offset=7,
            players=[_player(CONTROL_PLAYER_ID, "Lock To Make It", 1.0)],
        )
        leg = _created_make_cut(session, CONTROL_PLAYER_ID)
        assert leg.opening_probability == 1.0

    def test_a_pre_start_ordinary_price_is_kept_as_the_opening(self, monkeypatch):
        session = _run_pre_tournament(
            monkeypatch, tour="euro", event_id=EURO_EVENT_ID, start_offset=7,
            players=[_player(CONTROL_PLAYER_ID, "Rasmus Hojgaard", 0.55)],
        )
        leg = _created_make_cut(session, CONTROL_PLAYER_ID)
        assert leg.opening_probability == 0.55


# --------------------------------------------------- the in-play beat (site 2) --


class TestTheInPlayBeat:
    def test_a_leg_the_beat_meets_first_stores_no_opening(self, monkeypatch):
        """The filed specimen: a make-cut survivor first seen post-cut at 1.0."""
        board = [
            DataGolfPlayer(
                dg_id=NEW_PLAYER_ID, player_name="Made The Cut", make_cut=1.0
            )
        ]
        _stats, session, _redis, _log, _outcomes, markets = _run_live(
            monkeypatch, board_event_name=LIVE_EVENT_NAME, board=board
        )
        cut_id = markets[
            datagolf._external_id("pga", PGA_EVENT_ID, "make_cut")
        ].id
        created = [
            o for o in session.added
            if isinstance(o, FuturesOutcome)
            and o.market_id == cut_id
            and o.external_id == f"dg_{NEW_PLAYER_ID}"
        ]
        assert len(created) == 1, "the beat did not create the new leg — nothing below means anything"
        leg = created[0]
        assert float(leg.current_probability) == 1.0
        assert leg.opening_probability is None, (
            "the in-play beat stored its post-cut certainty as the opening (#1106)"
        )
