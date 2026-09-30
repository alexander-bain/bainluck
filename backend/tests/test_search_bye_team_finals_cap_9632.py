"""#9632 — the bye-finals cap's page arithmetic and probe, without a database.

The behaviour (`dodgers` on a postseason bye keeps its latest finals on page
one) is proven on a real Postgres in
`tests/integration/test_search_bye_team_finals_cap_pg_9632.py`, strawman and
four controls included. This file pins the partition — every raw row on exactly
one page, capped or not — and the probe's clauses.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import (
    _SEARCH_BYE_FINALS_CAP as CAP,
    _search_bye_finals_probe,
    _search_games_page_window,
    _search_games_total_pages,
)


def _pages(raw_total: int, per_page: int, capped: bool) -> list[range]:
    pages = _search_games_total_pages(raw_total, per_page, capped)
    out = []
    for page in range(1, pages + 1):
        offset, limit = _search_games_page_window(page, per_page, capped)
        out.append(range(offset, min(offset + limit, raw_total)))
    return out


class TestThePartition:
    @pytest.mark.parametrize("capped", [False, True])
    @pytest.mark.parametrize("per_page", [1, 5, 25, 100])
    @pytest.mark.parametrize("raw_total", [CAP + 1, 8, 25, 26, 31, 51, 250])
    def test_every_row_on_exactly_one_page_and_no_page_empty(
        self, raw_total, per_page, capped,
    ):
        pages = _pages(raw_total, per_page, capped)
        served = [i for page in pages for i in page]
        assert served == list(range(raw_total))
        assert all(len(page) > 0 for page in pages), pages

    def test_uncapped_is_the_plain_window(self):
        for page in (1, 2, 7):
            assert _search_games_page_window(page, 25, False) == ((page - 1) * 25, 25)
        assert _search_games_total_pages(31, 25, False) == 2

    def test_capped_page_one_holds_the_cap_and_page_two_follows_it(self):
        assert _search_games_page_window(1, 25, True) == (0, CAP)
        assert _search_games_page_window(2, 25, True) == (CAP, 25)
        assert _search_games_page_window(3, 25, True) == (CAP + 25, 25)
        # `dodgers` on 2026-09-29: 31 finals -> 3 on page one, 28 over two more.
        assert _search_games_total_pages(31, 25, True) == 3


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestTheProbe:
    SQL = _sql(_search_bye_finals_probe([ev.Event.home_team_name == "Los Angeles Dodgers"], [10707, 861]))

    def test_it_is_one_statement_of_two_exists(self):
        assert self.SQL.count("EXISTS") == 2, self.SQL
        assert "NOT (EXISTS" in self.SQL, self.SQL

    def test_something_to_play_is_live_or_scheduled_under_the_route_predicate(self):
        assert "events.status IN ('live', 'scheduled')" in self.SQL
        assert "events.home_team_name = 'Los Angeles Dodgers'" in self.SQL

    def test_a_live_futures_question_is_open_game_free_and_priced(self):
        assert "futures_outcomes.team_id IN (10707, 861)" in self.SQL
        assert "futures_markets.status = 'open'" in self.SQL
        assert "futures_markets.event_id IS NULL" in self.SQL
        assert "futures_outcomes.current_probability >= 0.01" in self.SQL


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_the_page_is_cut_by_the_window_and_counted_by_the_same_rule(self):
        assert "_search_games_page_window(page, per_page, _bye_finals_capped)" in self.SRC
        assert (
            "_search_games_total_pages(_raw_total_count, per_page, _bye_finals_capped)"
            in self.SRC
        )
        assert "query.offset(offset).limit(per_page)" not in self.SRC

    def test_armed_only_on_the_primary_count(self):
        """Every rescue arm fires on 0 and swaps `query`; the probe reads `event_conditions`."""
        taken = self.SRC.index("_primary_total_count = total_count")
        first_rescue = self.SRC.index("if total_count == 0 and not degraded")
        probe = self.SRC.index("_search_bye_finals_probe(event_conditions, _bye_team_ids)")
        assert taken < first_rescue < probe
        assert "_primary_total_count > _SEARCH_BYE_FINALS_CAP" in self.SRC
