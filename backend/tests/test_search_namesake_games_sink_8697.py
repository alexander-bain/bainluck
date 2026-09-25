"""#8697 — a resolved team's games lead the games list; a namesake sinks.

`chiefs` on production 2026-09-25: the TEAMS card said Kansas City Chiefs and
the first GAMES card was Exeter Chiefs v Gloucester (Other Rugby, unpriced),
because `search_rank` tied on "chiefs" and the tie broke by kickoff.

The behaviour itself is proven on a real Postgres in
`tests/integration/test_search_recall_contract.py` (resolved team leads, the
strawman without the key reproduces the defect, a no-team query keeps kickoff
order). This file pins the key's contract and the handler wiring, which need no
database.
"""

from __future__ import annotations

import inspect

from sqlalchemy.dialects import postgresql

from app.routes import events as ev
from app.routes.events import (
    _EVENT_SPORT_PREFIX_CATEGORY,
    _SEARCH_SPORT_LLM_CATEGORIES,
    _event_teamless_sport_order_key,
)


def _sql(expr) -> str:
    return str(
        expr.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


class TestTheKey:
    def test_disarmed_evidence_adds_no_key(self):
        assert _event_teamless_sport_order_key(None) is None
        assert _event_teamless_sport_order_key(frozenset()) is None

    def test_a_football_team_sinks_rugby_and_keeps_football(self):
        sql = _sql(_event_teamless_sport_order_key(frozenset({"football"})))
        assert "split_part(sports.key, '_', 1) IN" in sql
        assert "'rugby'" in sql
        assert "'esports'" in sql
        assert "'americanfootball'" not in sql

    def test_two_real_clubs_keep_both_sports(self):
        """`giants`: NFL and MLB clubs — neither sport sinks."""
        sql = _sql(_event_teamless_sport_order_key(frozenset({"football", "baseball"})))
        assert "'americanfootball'" not in sql
        assert "'baseball'" not in sql
        assert "'icehockey'" in sql

    def test_the_team_only_rugby_prefixes_sink_with_rugby(self):
        sql = _sql(_event_teamless_sport_order_key(frozenset({"football"})))
        assert "'rugbyleague'" in sql and "'rugbyunion'" in sql

    def test_a_rugby_club_keeps_every_rugby_prefix(self):
        """`warriors` resolves New Zealand Warriors (rugbyleague ⇒ `rugby`)."""
        sql = _sql(_event_teamless_sport_order_key(frozenset({"rugby", "basketball"})))
        for prefix in ("'rugby'", "'rugbyleague'", "'rugbyunion'", "'basketball'"):
            assert prefix not in sql

    def test_every_sport_category_matched_means_nothing_to_sink(self):
        assert _event_teamless_sport_order_key(frozenset(_SEARCH_SPORT_LLM_CATEGORIES)) is None

    def test_it_is_a_key_not_a_filter(self):
        sql = _sql(_event_teamless_sport_order_key(frozenset({"football"})))
        assert sql.startswith("CASE WHEN") and "THEN 1 ELSE 0 END" in sql

    def test_the_prefix_map_reads_the_team_vocabulary(self):
        """Game and club judged in ONE vocabulary: both maps, no third."""
        assert _EVENT_SPORT_PREFIX_CATEGORY["rugby"] == "rugby"
        assert _EVENT_SPORT_PREFIX_CATEGORY["rugbyunion"] == "rugby"
        assert _EVENT_SPORT_PREFIX_CATEGORY["americanfootball"] == "football"


class TestTheHandlerWiring:
    SRC = inspect.getsource(ev.search_events)

    def test_the_evidence_is_read_before_the_games_order_by(self):
        read = self.SRC.index("_early_team_rows = (await db.execute(_search_team_rows_q([]))).all()")
        key = self.SRC.index("_teamless_sport_key = _event_teamless_sport_order_key(")
        order = self.SRC.index("*( (_teamless_sport_key,) if _teamless_sport_key is not None else () ),")
        assert read < key < order

    def test_the_key_sits_under_the_day_boost_and_over_status(self):
        start = self.SRC.index("_day_boost = _intent_day_order_key(_intent, now)")
        block = self.SRC[start:start + 900]
        day = block.index("(_day_boost,)")
        key = block.index("(_teamless_sport_key,)")
        status = block.index("status_order,")
        assert day < key < status

    def test_the_evidence_read_is_shed_safe(self):
        start = self.SRC.index("_early_team_rows: list | None = None")
        block = self.SRC[start:self.SRC.index('_mark("team_evidence")')]
        assert "_evidence_savepoint = await db.begin_nested()" in block
        assert "_recover_search_session" not in block
        assert 'degraded.append("teams")' in block

    def test_the_teams_stage_reuses_the_evidence_rows_unless_roster_ids_change_it(self):
        start = self.SRC.index("team_search_q = _search_team_rows_q(_roster_team_ids)")
        block = self.SRC[start:self.SRC.index('_mark("teams")')]
        assert "if _early_team_rows is not None and not _roster_team_ids:" in block
        assert "_team_result_rows = _early_team_rows" in block
        assert "team_search_result = await db.execute(team_search_q)" in block

    def test_one_teams_statement_builder(self):
        """The evidence read and the stage compile the SAME statement."""
        assert self.SRC.count("def _search_team_rows_q(") == 1
        assert self.SRC.count(".limit(_SEARCH_TEAM_WINDOW)") == 1
