"""#9211 — the dropdown's today's-final arm, without a database.

The route behaviour is `tests/integration/test_typeahead_todays_final_pg_9211.py`
(real Postgres, strawman and control). This file pins what a session double can:
the placement rule, the statement's clauses, and the Eastern day boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.routes import events as ev_mod


def _row(name: str, status: str = "scheduled"):
    return SimpleNamespace(name=name, status=status)


def _names(rows) -> list[str]:
    return [r.name for r in rows]


def _is_next(r) -> bool:
    return r.name.startswith("team") and r.status in ("live", "scheduled")


class TestPlacement:
    def test_the_final_sits_directly_behind_the_next_game(self):
        rows = [_row("namesake"), _row("team_next"), _row("other")]
        out = ev_mod._place_todays_finals(rows, [_row("final", "completed")], _is_next)
        assert _names(out) == ["namesake", "team_next", "final", "other"]

    def test_with_no_next_game_the_final_leads(self):
        rows = [_row("namesake"), _row("other")]
        out = ev_mod._place_todays_finals(rows, [_row("final", "completed")], _is_next)
        assert _names(out) == ["final", "namesake", "other"]

    def test_a_next_game_too_deep_for_the_cut_moves_up_with_its_final(self):
        """Both must survive `_EVENT_POOL_SIZE`, and next still precedes final."""
        rows = [_row(f"namesake{i}") for i in range(5)]
        rows.insert(4, _row("team_next"))
        finals = [_row("final", "completed")]
        out = ev_mod._place_todays_finals(rows, finals, _is_next)
        kept = _names(out[: ev_mod._EVENT_POOL_SIZE])
        assert "team_next" in kept and "final" in kept, kept
        assert kept.index("final") == kept.index("team_next") + 1
        assert sorted(_names(out)) == sorted(_names(rows) + ["final"])

    def test_a_doubleheader_keeps_both_finals_inside_the_cut(self):
        rows = [_row(f"namesake{i}") for i in range(4)] + [_row("team_next", "live")]
        finals = [_row("final2", "completed"), _row("final1", "completed")]
        out = ev_mod._place_todays_finals(rows, finals, _is_next)
        assert _names(out[: ev_mod._EVENT_POOL_SIZE])[-3:] == [
            "team_next", "final2", "final1",
        ]


class TestStatement:
    NOW = datetime(2026, 9, 27, 21, 31, tzinfo=timezone.utc)

    def _sql(self) -> str:
        stmt = ev_mod._lead_team_todays_final_query(560, "Kansas City Chiefs", self.NOW)
        return str(
            stmt.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )

    def test_finished_rows_only_inside_todays_eastern_window(self):
        sql = self._sql()
        assert "events.status IN ('completed', 'closed')" in sql
        # Midnight Eastern (EDT, UTC-4) on the 27th, and `now` as the ceiling.
        assert "events.commence_time >= '2026-09-27 00:00:00-04:00'" in sql
        assert "events.commence_time <= '2026-09-27 21:31:00+00:00'" in sql

    def test_selected_by_identity_never_by_substring(self):
        sql = self._sql()
        assert "events.home_team_id = 560" in sql
        assert "events.away_team_name = 'Kansas City Chiefs'" in sql
        assert "LIKE '%" not in sql.split("event_tags")[0], sql

    def test_newest_first_bounded_and_twin_free(self):
        sql = self._sql()
        assert "ORDER BY events.commence_time DESC" in sql
        assert f"LIMIT {ev_mod._LEAD_TEAM_TODAYS_FINAL_LIMIT}" in sql
        assert "event_tags IS NULL" in sql


class TestEasternDay:
    def test_after_midnight_utc_it_is_still_yesterday_in_new_york(self):
        now = datetime(2026, 9, 28, 3, 0, tzinfo=timezone.utc)  # 23:00 EDT 9/27
        start = ev_mod._eastern_day_start(now)
        assert start.isoformat() == "2026-09-27T00:00:00-04:00"

    def test_winter_offset(self):
        now = datetime(2026, 12, 6, 18, 0, tzinfo=timezone.utc)
        assert ev_mod._eastern_day_start(now).isoformat() == "2026-12-06T00:00:00-05:00"
