"""Guards for the trigram GIN pending-list flush (LAT-P109, #2255).

The class of defect this file exists to catch is the one gotcha #53 names: a
maintenance pass that *returns* while flushing nothing, and reads as healthy
because it did not raise. Every assertion below is about what the SUMMARY
proves, what a single bad index does to its six siblings, and where the budget
is bounded — not about the number of pages Postgres happened to reclaim.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

from app.tasks import gin_pending_lists as gpl
from app.utils.task_verdict import classify_summary


# --------------------------------------------------------------------------
# A fake session that records the SQL it was handed. It is deliberately dumb:
# the thing under test is the loop's damage containment and its summary, and a
# real engine would only prove that asyncpg still works.
# --------------------------------------------------------------------------
class _Row:
    def __init__(self, pages):
        self.pages = pages


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Nested:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._session.savepoints += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._session.rollbacks += 1
        return False


class FakeSession:
    """Records statements; raises for any index named in ``fail_on``."""

    def __init__(self, *, pages=7, fail_on=(), pages_by_index=None):
        self.statements: list[str] = []
        self.savepoints = 0
        self.rollbacks = 0
        self._pages = pages
        self._pages_by_index = pages_by_index or {}
        self._fail_on = set(fail_on)

    def begin_nested(self):
        return _Nested(self)

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.statements.append(sql)
        if "gin_clean_pending_list" not in sql:
            return _Result(None)
        for name in self._fail_on:
            if name in sql:
                raise RuntimeError(f"boom: {name}")
        for name, pages in self._pages_by_index.items():
            if name in sql:
                return _Result(_Row(pages))
        return _Result(_Row(self._pages))


def _patch_session(monkeypatch, session):
    @asynccontextmanager
    async def _fake():
        yield session

    monkeypatch.setattr("app.tasks.base.get_task_session", _fake)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------
class TestThePool:
    def test_the_pool_is_a_frozen_literal_with_no_duplicates(self):
        pool = gpl.SEARCH_TRIGRAM_INDEXES
        assert isinstance(pool, tuple), "a list would let a caller mutate the pool"
        assert len(pool) == len(set(pool))
        assert pool, "an empty pool would make every pass a vacuous success"

    def test_the_pool_names_the_indexes_the_measurement_was_taken_on(self):
        """Membership is an explicit edit, so a silent re-base is impossible.

        These seven are the trigram GIN indexes `/api/events/search` touches,
        verified against `pg_indexes` on production 2026-08-28. If one is
        renamed or dropped this test is the thing that says so, rather than a
        pass that quietly flushes six.
        """
        assert set(gpl.SEARCH_TRIGRAM_INDEXES) == {
            "ix_futures_outcomes_name_trgm",
            "ix_futures_name_trgm",
            "ix_events_home_trgm",
            "ix_events_away_trgm",
            "ix_events_home_team_name_trgm",
            "ix_events_away_team_name_trgm",
            "ix_teams_name_trgm",
        }


# --------------------------------------------------------------------------
# The statement the pool builds
# --------------------------------------------------------------------------
class TestTheStatement:
    def test_an_index_outside_the_pool_is_refused_before_any_sql_is_built(self):
        """The name is interpolated, so the ONLY thing standing between this and
        arbitrary SQL is that check. It is asserted, not trusted."""
        session = FakeSession()
        with pytest.raises(ValueError):
            _run(gpl._flush_one(session, "ix_not_ours; DROP TABLE events"))
        assert session.statements == [], "it must refuse BEFORE issuing anything"

    def test_the_bound_is_on_the_flush_itself_not_the_loop_boundary(self):
        """The longest uninterrupted operation is one flush, so the timeout goes
        immediately before it — the budget-guard shape (#1494 / gotcha #124's
        sibling). A per-pass bound would let one index eat the whole budget."""
        session = FakeSession()
        _run(gpl._flush_one(session, "ix_teams_name_trgm"))
        assert len(session.statements) == 2
        assert "SET LOCAL statement_timeout" in session.statements[0]
        assert str(gpl.PER_INDEX_TIMEOUT_MS) in session.statements[0]
        assert "gin_clean_pending_list" in session.statements[1]
        assert "ix_teams_name_trgm" in session.statements[1]

    def test_a_null_page_count_is_zero_and_not_a_crash(self):
        session = FakeSession(pages=None)
        assert _run(gpl._flush_one(session, "ix_teams_name_trgm")) == 0


# --------------------------------------------------------------------------
# The pass
# --------------------------------------------------------------------------
class TestThePass:
    def test_a_clean_pass_flushes_every_index_and_reads_green(self, monkeypatch):
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(pages=11)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "complete"
        assert summary["completed"] == len(gpl.SEARCH_TRIGRAM_INDEXES)
        assert summary["total"] == len(gpl.SEARCH_TRIGRAM_INDEXES)
        assert summary["pages_cleaned"] == 11 * len(gpl.SEARCH_TRIGRAM_INDEXES)
        assert summary["errors"] == []
        assert classify_summary(summary).is_green
        assert session.savepoints == len(gpl.SEARCH_TRIGRAM_INDEXES)

    def test_one_bad_index_must_not_wipe_the_pass(self, monkeypatch):
        """Gotcha #42, in its maintenance-task form. The healthy siblings are
        asserted BY NAME — a test that only checked `errors` would pass on a
        pass that aborted after the failure."""
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(pages=3, fail_on=("ix_futures_name_trgm",))
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "partial"
        assert summary["completed"] == len(gpl.SEARCH_TRIGRAM_INDEXES) - 1
        assert [e["index"] for e in summary["errors"]] == ["ix_futures_name_trgm"]
        for name in gpl.SEARCH_TRIGRAM_INDEXES:
            if name == "ix_futures_name_trgm":
                assert name not in summary["per_index"]
            else:
                assert summary["per_index"][name] == 3
        assert session.rollbacks == 1, "the failure must roll back its OWN savepoint"
        assert not classify_summary(summary).is_green

    def test_a_pass_that_flushed_nothing_is_never_green(self, monkeypatch):
        """ "It returned" is not "it worked" (gotcha #53). Every index failing is
        a FAILED pass, not a complete one with an empty ledger."""
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(fail_on=gpl.SEARCH_TRIGRAM_INDEXES)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "failed"
        assert summary["completed"] == 0
        assert len(summary["errors"]) == len(gpl.SEARCH_TRIGRAM_INDEXES)
        assert not classify_summary(summary).is_green

    def test_zero_pages_reclaimed_is_still_a_complete_pass(self, monkeypatch):
        """The steady state this task is trying to REACH is "nothing to flush".
        A pass that finds every list already empty has done its job, so it must
        not be reported as damage — the units are indexes visited, never pages."""
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(pages=0)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "complete"
        assert summary["pages_cleaned"] == 0
        assert classify_summary(summary).is_green

    def test_the_summary_reports_pages_per_index_so_a_move_can_be_attributed(
        self, monkeypatch
    ):
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(
            pages=1, pages_by_index={"ix_futures_outcomes_name_trgm": 480}
        )
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["per_index"]["ix_futures_outcomes_name_trgm"] == 480
        assert summary["pages_cleaned"] == 480 + (len(gpl.SEARCH_TRIGRAM_INDEXES) - 1)


# --------------------------------------------------------------------------
# The switch
# --------------------------------------------------------------------------
class TestTheSwitch:
    @pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off", " Off "])
    def test_falsey_values_disable_it(self, monkeypatch, raw):
        monkeypatch.setenv("SEARCH_GIN_FLUSH_ENABLED", raw)
        assert gpl.gin_flush_enabled() is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "anything"])
    def test_everything_else_leaves_it_on(self, monkeypatch, raw):
        monkeypatch.setenv("SEARCH_GIN_FLUSH_ENABLED", raw)
        assert gpl.gin_flush_enabled() is True

    def test_it_defaults_on_so_the_var_is_rollback_only(self, monkeypatch):
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        assert gpl.gin_flush_enabled() is True

    def test_disabled_opens_no_session_and_is_not_green(self, monkeypatch):
        """A disabled pass must be visibly `skipped`, never a silent success —
        the same shape `warm_search_head` uses so an operator reading
        task-metrics can tell "off" from "working"."""
        monkeypatch.setenv("SEARCH_GIN_FLUSH_ENABLED", "0")

        @asynccontextmanager
        async def _explode():
            raise AssertionError("a disabled pass must not open a session")
            yield  # pragma: no cover

        monkeypatch.setattr("app.tasks.base.get_task_session", _explode)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "skipped"
        assert summary["skip_reason"] == "disabled"
        assert not classify_summary(summary).is_green


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------
class TestWiring:
    def test_the_beat_entry_exists_and_is_bounded(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["flush-search-gin-pending-lists"]
        assert entry["task"] == "app.tasks.flush_search_gin_pending_lists"
        period = entry["schedule"]
        assert period == 120.0
        options = entry["options"]
        assert (
            options["queue"] == "background"
        ), "maintenance must not contend with the realtime price poll"
        assert (
            0 < options["expires"] <= period
        ), "an expires longer than the period cannot discard a superseded fire"

    def test_the_task_is_registered_under_the_name_the_beat_dispatches(self):
        from app.tasks import celery_app

        assert "app.tasks.flush_search_gin_pending_lists" in celery_app.tasks

    def test_the_soft_limit_leaves_room_under_the_global_sigkill(self):
        """`task_time_limit` is a hard SIGKILL (300s) that would be recorded as
        `no_data` rather than as a failure — every bound here must sit under it,
        and the per-index bound under the task's own."""
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.flush_search_gin_pending_lists"]
        assert task.soft_time_limit < task.time_limit
        assert task.time_limit < celery_app.conf.task_time_limit
        assert gpl.PER_INDEX_TIMEOUT_MS / 1000.0 < task.soft_time_limit
