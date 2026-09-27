"""#9211 — a club's game that finished today sits right behind its next game.

`chiefs` on production 2026-09-27: 13 upcoming games printed above that
afternoon's 24–10 win. The behaviour is proven on a real Postgres in
`tests/integration/test_search_todays_final_behind_next_pg_9211.py` (strawman,
no-final-day control and the #8738 leader case). This file pins the helper and
the wiring.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

from sqlalchemy import case, literal_column
from sqlalchemy.dialects import postgresql

from app.models.models import Event
from app.routes import events as ev
from app.routes.events import _todays_final_order_key

# 2026-09-28 02:30Z is still Sunday 9/27 in the East — the evening slate.
NOW = datetime(2026, 9, 28, 2, 30, tzinfo=timezone.utc)
STATUS = case((literal_column("x") == 1, 7), else_=8)


def _sql(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheKey:
    def test_disarmed_off_a_club_query(self):
        assert _todays_final_order_key(False, STATUS, (Event.id,), NOW) is None

    def test_today_is_the_eastern_day_not_the_utc_one(self):
        # Sunday 9/27 in the East is [04:00Z Sun, 04:00Z Mon) under EDT. The UTC
        # day (9/28) would drop every game of the evening slate.
        sql = _sql(_todays_final_order_key(True, STATUS, (Event.id,), NOW))
        assert "events.commence_time >= '2026-09-27 04:00:00+00:00'" in sql, sql
        assert "events.commence_time < '2026-09-28 04:00:00+00:00'" in sql, sql

    def test_the_eastern_day_follows_standard_time_in_winter(self):
        winter = datetime(2026, 12, 7, 3, 0, tzinfo=timezone.utc)  # Sun 12/6 ET
        sql = _sql(_todays_final_order_key(True, STATUS, (Event.id,), winter))
        assert "events.commence_time >= '2026-12-06 05:00:00+00:00'" in sql, sql
        assert "events.commence_time < '2026-12-07 05:00:00+00:00'" in sql, sql

    def test_no_per_row_timezone_cast(self):
        # A range on the raw column, which its index can serve; and no
        # `timezone` token for #5688's named-day guard to read as its key.
        sql = _sql(_todays_final_order_key(True, STATUS, (Event.id,), NOW))
        assert "timezone" not in sql, sql

    def test_only_a_result_is_lifted_not_a_suspension(self):
        sql = _sql(_todays_final_order_key(True, STATUS, (Event.id,), NOW))
        assert "events.status IN ('completed', 'closed')" in sql, sql
        assert "suspended" not in sql, sql

    def test_the_next_game_is_ranked_by_the_tiers_own_keys(self):
        sql = _sql(
            _todays_final_order_key(
                True, STATUS, (Event.commence_time.asc(), Event.id.desc()), NOW
            )
        )
        assert (
            "row_number() OVER (PARTITION BY CASE WHEN (x = 1) THEN 7 ELSE 8 END "
            "ORDER BY events.commence_time ASC, events.id DESC) = 1"
        ) in sql, sql

    def test_three_bands_live_and_next_then_todays_final_then_the_rest(self):
        sql = _sql(_todays_final_order_key(True, STATUS, (Event.id,), NOW))
        assert sql.startswith("CASE WHEN ("), sql
        assert sql.endswith("THEN 1 ELSE 2 END"), sql
        assert sql.count("THEN 0") == 2, sql


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_armed_by_the_club_test_8942_already_paid_for(self):
        assert "_todays_final_order_key(\n        not tag_boost_keys," in self.SRC

    def test_the_window_orders_by_the_upcoming_tiers_keys(self):
        start = self.SRC.index("_todays_final_key = _todays_final_order_key(")
        call = self.SRC[start:start + 500]
        lead = call.index("_team_card_lead_key")
        rank = call.index("search_rank.desc()")
        soon = call.index("Event.commence_time.asc()")
        assert lead < rank < soon

    def test_the_key_sits_directly_above_status_order(self):
        start = self.SRC.index("query = query.order_by(")
        block = self.SRC[start:start + 2400]
        split = block.index("_split_terms_key,) if _split_terms_key is not None")
        key = block.index(
            "*( (_todays_final_key,) if _todays_final_key is not None else () ),"
        )
        status = block.index("status_order,")
        assert split < key < status
