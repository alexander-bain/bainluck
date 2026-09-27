"""#9040 — among finished games the newest day leads, above #8738's card leader.

`texas` on production 2026-09-27: the card led with Texas Rangers and every
Rangers final in the 30-day window sorted above Texas @ Tennessee from the same
night (page 3). The behaviour is proven on a real Postgres in
`tests/integration/test_search_settled_day_over_lead_club_pg_9040.py` (strawman
and upcoming-tier control included). This file pins the helper and the wiring.
"""

from __future__ import annotations

import inspect

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import _SEARCH_SETTLED_STATUSES, _settled_day_order_key


def _sql(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheKey:
    def test_disarmed_with_the_lead_key(self):
        assert _settled_day_order_key(None) is None
        assert _settled_day_order_key(frozenset()) is None

    def test_it_is_the_eastern_day_of_a_finished_game_newest_first(self):
        sql = _sql(_settled_day_order_key(frozenset({"baseball_mlb"})))
        assert sql == (
            "CASE WHEN (events.status IN ('completed', 'closed', 'suspended')) "
            "THEN CAST(timezone('America/New_York', events.commence_time) AS DATE) "
            "END DESC NULLS LAST"
        ), sql

    def test_the_status_set_is_the_settled_one(self):
        assert set(_SEARCH_SETTLED_STATUSES) == {"completed", "closed", "suspended"}

    def test_it_does_not_read_the_lead_sports(self):
        """The day orders every finished game alike; the leader orders within it."""
        a = _sql(_settled_day_order_key(frozenset({"baseball_mlb"})))
        b = _sql(_settled_day_order_key(frozenset({"basketball_nba", "soccer_epl"})))
        assert a == b


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_armed_from_the_same_leader_as_8738(self):
        leader = self.SRC.index(
            "_team_card_lead_sports = _team_card_lead_sport_keys(_early_team_rows, _q_identity)"
        )
        lead = self.SRC.index("_team_card_lead_order_key(_team_card_lead_sports)")
        day = self.SRC.index("_settled_day_order_key(_team_card_lead_sports)")
        assert leader < lead and leader < day

    def test_the_day_sits_under_status_and_over_the_card_leader(self):
        start = self.SRC.index("_day_boost = _intent_day_order_key(_intent, now)")
        block = self.SRC[start:start + 1600]
        status = block.index("status_order,")
        day = block.index("*( (_settled_day_key,) if _settled_day_key is not None else () ),")
        lead = block.index("*( (_team_card_lead_key,) if _team_card_lead_key is not None else () ),")
        rank = block.index("search_rank.desc(),")
        assert status < day < lead < rank
