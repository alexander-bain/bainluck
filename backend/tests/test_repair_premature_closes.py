"""#2444 — guards for the premature-close repair rail.

The rail writes to `events.status` and `events.completed_at`, so the things worth
pinning are its REFUSALS: what it must never touch, and the fact that it undoes a
fabricated completion rather than replacing it with a fresh guess.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import scripts.repair_premature_closes as rail

NOW = datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc)


def _row(event_id=1, travel=0.4, moves=200):
    return SimpleNamespace(
        id=event_id,
        commence_time=NOW - timedelta(hours=29),
        completed_at=NOW - timedelta(hours=23),
        home_team_name="Matteo Berrettini",
        away_team_name="Stan Wawrinka",
        sport_key="tennis_atp_us_open",
        hidden_moves=moves,
        travel=travel,
        last_hidden_at=NOW - timedelta(minutes=10),
    )


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return SimpleNamespace(rowcount=len(params["event_ids"]))
        return SimpleNamespace(all=lambda: self._rows)

    async def commit(self):
        self.committed = True


class TestTheSelectRefusesTheWrongRows:
    def test_it_only_looks_at_rows_the_staleness_nets_closed(self):
        # A 'completed' row came from a real scores feed reporting a real finish.
        # Un-settling one would undo a true result.
        assert "e.status = 'closed'" in rail._PREMATURE_CLOSES_SQL

    def test_it_never_considers_a_row_holding_a_real_score(self):
        # gotcha #21. Nothing this rail writes can destroy a stored result,
        # because it never selects a row that has one.
        sql = rail._PREMATURE_CLOSES_SQL
        assert "e.home_score IS NULL" in sql
        assert "e.away_score IS NULL" in sql

    def test_it_requires_hidden_movement_not_merely_a_confirmation(self):
        # THE distinction that keeps this rail off soccer/esports derivative rows
        # a blanket poller keeps touching after the match ends: 490 rows matched
        # a confirmation predicate, 36 match this one.
        sql = rail._PREMATURE_CLOSES_SQL
        assert "JOIN odds_snapshots" in sql
        assert "o.captured_at >" in sql, (
            "the join must be on a price CHANGE (captured_at), which is what the "
            "chart is clipping — not on valid_until, which a poller bumps on a "
            "market that is long over"
        )
        assert "valid_until" not in sql, (
            "valid_until answers the producer's question, not this rail's"
        )

    def test_both_movement_bars_are_actually_applied(self):
        sql = rail._PREMATURE_CLOSES_SQL
        assert ":min_moves" in sql and ":min_travel" in sql
        assert "HAVING" in sql
        assert rail._MIN_POST_CLOSE_MOVES >= 2
        assert rail._MIN_POST_CLOSE_TRAVEL > 0

    def test_the_post_close_window_reuses_the_shared_grace_period(self):
        # If this rail and the producer disagree on how long is "still active",
        # the repair starts undoing closes the producer would legitimately retake.
        from app.utils.event_completion import STILL_ACTIVE_MINUTES

        assert ":still_active_minutes" in rail._PREMATURE_CLOSES_SQL
        assert STILL_ACTIVE_MINUTES == 30


class TestTheRemedyUndoesRatherThanGuesses:
    def test_it_clears_completed_at_instead_of_writing_a_new_one(self):
        # Writing a replacement end time here would re-introduce the fabricated
        # -timestamp class this rail exists to remove. The FIXED net re-derives
        # it from correct evidence on the next pass.
        assert "completed_at = NULL" in rail._UNSETTLE_SQL
        assert "completed_at =" in rail._UNSETTLE_SQL
        assert "now()" not in rail._UNSETTLE_SQL

    def test_the_write_re_asserts_the_safety_predicates(self):
        # Addressed by primary key over proven ids, but a row could settle
        # legitimately between the SELECT and the UPDATE. The guard must hold at
        # write time too.
        sql = rail._UNSETTLE_SQL
        assert "id = ANY(:event_ids)" in sql
        assert "status = 'closed'" in sql
        assert "home_score IS NULL" in sql
        assert "away_score IS NULL" in sql


class TestTheRailItself:
    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing_and_does_not_commit(self):
        s = _Session([_row()])
        res = await rail.repair(s, apply=False, days=7, sport=None, limit=500)
        assert res["proven"] == 1
        assert res["unsettled"] == 0
        assert not s.committed
        assert not any(sql.strip().upper().startswith("UPDATE")
                       for sql, _ in s.statements)

    @pytest.mark.asyncio
    async def test_apply_unsettles_exactly_the_proven_ids(self):
        s = _Session([_row(event_id=15293846), _row(event_id=15293814)])
        res = await rail.repair(s, apply=True, days=7, sport=None, limit=500)
        assert res["unsettled"] == 2
        assert s.committed
        updates = [(sql, p) for sql, p in s.statements
                   if sql.strip().upper().startswith("UPDATE")]
        assert len(updates) == 1, "one statement for the whole set, not per row"
        assert updates[0][1]["event_ids"] == [15293846, 15293814]

    @pytest.mark.asyncio
    async def test_an_empty_population_never_reaches_a_write(self):
        # gotcha #53: a zero-yield run must be a quiet no-op, not an UPDATE with
        # an empty id list that a later predicate change could widen.
        s = _Session([])
        res = await rail.repair(s, apply=True, days=7, sport=None, limit=500)
        assert res["proven"] == 0 and res["unsettled"] == 0
        assert not any(sql.strip().upper().startswith("UPDATE")
                       for sql, _ in s.statements)

    @pytest.mark.asyncio
    async def test_the_sport_filter_arrives_as_a_finished_pattern(self):
        # gotcha #45 — a literal '%' built inside text() is a bind-param footgun.
        s = _Session([])
        await rail.repair(s, apply=False, days=7, sport="tennis", limit=500)
        assert s.statements[0][1]["sport_pattern"] == "tennis%"

    @pytest.mark.asyncio
    async def test_no_sport_filter_passes_null_not_a_bare_wildcard(self):
        s = _Session([])
        await rail.repair(s, apply=False, days=7, sport=None, limit=500)
        assert s.statements[0][1]["sport_pattern"] is None

    @pytest.mark.asyncio
    async def test_the_ledger_reports_what_was_hidden(self):
        # The rail's whole claim is "there is movement behind this fabricated
        # completion". It has to print the evidence, not just a count.
        s = _Session([_row(event_id=15293814, travel=0.9636, moves=375)])
        res = await rail.repair(s, apply=False, days=7, sport=None, limit=500)
        entry = res["ledger"][0]
        assert entry["hidden_moves"] == 375
        assert entry["hidden_travel"] == 0.964
        assert entry["event_id"] == 15293814
        assert res["by_sport"] == {"tennis_atp_us_open": 1}
