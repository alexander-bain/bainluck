"""Guards for the trigram GIN pending-list flush (LAT-P109, #2255).

The class of defect this file exists to catch is the one gotcha #53 names: a
maintenance pass that *returns* while flushing nothing, and reads as healthy
because it did not raise. Every assertion below is about what the SUMMARY
proves, what a single bad index does to its siblings, and where the budget
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

    def __init__(self, *, pages=7, fail_on=(), pages_by_index=None, on_flush=None):
        self._on_flush = on_flush
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
        if self._on_flush is not None:
            self._on_flush(sql)
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


def _flushed(session) -> list[str]:
    """The index each issued flush named, in issue order."""
    out = []
    for sql in session.statements:
        if "gin_clean_pending_list" in sql:
            out.append(sql.split("gin_clean_pending_list('", 1)[1].split("'", 1)[0])
    return out


@pytest.fixture(autouse=True)
def _both_switches_default(monkeypatch):
    monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
    monkeypatch.delenv("EVENTS_GIN_FLUSH_ENABLED", raising=False)


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


class TestTheWritePathPool:
    """#10090 Holder A: `ix_events_event_tags` is flushed for its writers. An
    `events` writer that crosses the pending-list limit merges the list inside
    its own single-row UPDATE, with the row locked, and nothing else was keeping
    this list down."""

    def test_the_write_path_pool_is_event_tags_exactly(self):
        assert gpl.WRITE_PATH_GIN_INDEXES == ("ix_events_event_tags",)

    def test_the_pass_visits_the_write_path_first_then_every_search_index(self):
        """First, so a slow trigram flush cannot starve it under the soft limit;
        and the search pool is carried whole, so this ship cannot quietly drop
        one of the seven the cold-search measurement rests on."""
        assert gpl.FLUSHED_GIN_INDEXES == (
            gpl.WRITE_PATH_GIN_INDEXES + gpl.SEARCH_TRIGRAM_INDEXES
        )
        assert isinstance(gpl.FLUSHED_GIN_INDEXES, tuple)
        assert len(gpl.FLUSHED_GIN_INDEXES) == len(set(gpl.FLUSHED_GIN_INDEXES))

    def test_event_tags_is_the_first_flush_the_events_pass_issues(self, monkeypatch):
        session = FakeSession(pages=2)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_events_gin_pending_lists())
        flushes = [s for s in session.statements if "gin_clean_pending_list" in s]
        assert flushes[0] == (
            "SELECT gin_clean_pending_list('ix_events_event_tags'::regclass) AS pages"
        )
        assert len(flushes) == len(gpl.EVENTS_GIN_INDEXES)
        assert summary["per_index"]["ix_events_event_tags"] == 2
        assert summary["terminal"] == "complete"

    def test_a_failed_event_tags_flush_leaves_every_events_trigram_flush_standing(
        self, monkeypatch
    ):
        session = FakeSession(pages=5, fail_on=("ix_events_event_tags",))
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_events_gin_pending_lists())
        assert [e["index"] for e in summary["errors"]] == ["ix_events_event_tags"]
        assert summary["per_index"] == {
            n: 5 for n in gpl.EVENTS_GIN_INDEXES if n != "ix_events_event_tags"
        }
        assert summary["terminal"] == "partial"
        assert not classify_summary(summary).is_green


class TestTheEventsPass:
    """#10090: the `background` beat delivered 37 of 720 fires in a day, so the
    `events` GIN lists get their own beat on `realtime`. Each index has exactly
    one owning pass, and one switch puts everything back as it was."""

    def test_the_two_passes_partition_the_pool(self):
        events, background = gpl.EVENTS_GIN_INDEXES, gpl.BACKGROUND_GIN_INDEXES
        assert isinstance(events, tuple) and isinstance(background, tuple)
        assert not set(events) & set(background), "an index flushed by two passes"
        assert set(events) | set(background) == set(gpl.FLUSHED_GIN_INDEXES)
        assert len(events) + len(background) == len(gpl.FLUSHED_GIN_INDEXES)

    def test_the_events_pass_is_every_events_index_event_tags_first(self):
        assert gpl.EVENTS_GIN_INDEXES[0] == "ix_events_event_tags"
        assert set(gpl.EVENTS_GIN_INDEXES) == {
            n for n in gpl.FLUSHED_GIN_INDEXES if n.startswith("ix_events_")
        }

    def test_the_background_pass_keeps_pool_order(self):
        assert gpl.BACKGROUND_GIN_INDEXES == tuple(
            n for n in gpl.FLUSHED_GIN_INDEXES if n in gpl.BACKGROUND_GIN_INDEXES
        )

    def test_the_events_pass_flushes_exactly_its_five_in_order(self, monkeypatch):
        session = FakeSession(pages=4)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_events_gin_pending_lists())
        assert _flushed(session) == list(gpl.EVENTS_GIN_INDEXES)
        assert summary["terminal"] == "complete"
        assert summary["total"] == len(gpl.EVENTS_GIN_INDEXES)
        assert summary["budget_skipped"] == []
        assert classify_summary(summary).is_green

    def test_the_background_pass_leaves_the_events_lists_to_the_events_beat(
        self, monkeypatch
    ):
        """A background flush on an `events` index would wait on the events
        pass's metapage lock (a forced cleanup waits; only writers skip)."""
        session = FakeSession(pages=4)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert _flushed(session) == list(gpl.BACKGROUND_GIN_INDEXES)
        assert not any(n.startswith("ix_events_") for n in _flushed(session))
        assert summary["terminal"] == "complete"

    @pytest.mark.parametrize("raw", ["0", "false", "off"])
    def test_the_events_switch_off_hands_all_eight_back_to_background(
        self, monkeypatch, raw
    ):
        monkeypatch.setenv("EVENTS_GIN_FLUSH_ENABLED", raw)

        @asynccontextmanager
        async def _explode():
            raise AssertionError("a disabled events pass must not open a session")
            yield  # pragma: no cover

        monkeypatch.setattr("app.tasks.base.get_task_session", _explode)
        events = _run(gpl._flush_events_gin_pending_lists())
        assert events["terminal"] == "skipped"
        assert not classify_summary(events).is_green

        session = FakeSession(pages=1)
        _patch_session(monkeypatch, session)
        background = _run(gpl._flush_gin_pending_lists())
        assert _flushed(session) == list(gpl.FLUSHED_GIN_INDEXES)
        assert _flushed(session)[0] == "ix_events_event_tags"
        assert background["terminal"] == "complete"

    def test_the_search_switch_still_turns_off_both_passes(self, monkeypatch):
        monkeypatch.setenv("SEARCH_GIN_FLUSH_ENABLED", "0")

        @asynccontextmanager
        async def _explode():
            raise AssertionError("a disabled pass must not open a session")
            yield  # pragma: no cover

        monkeypatch.setattr("app.tasks.base.get_task_session", _explode)
        assert _run(gpl._flush_events_gin_pending_lists())["terminal"] == "skipped"
        assert _run(gpl._flush_gin_pending_lists())["terminal"] == "skipped"

    def test_no_flush_starts_after_the_pass_budget(self, monkeypatch):
        """Bounds how long one fire holds a realtime slot: budget + one flush.
        Each fake flush costs 12 s against the 20 s budget, so two run and the
        remaining three are named, not silently dropped."""
        clock = {"t": 1000.0}
        monkeypatch.setattr(gpl.time, "perf_counter", lambda: clock["t"])

        def _advance(_sql):
            clock["t"] += 12.0

        session = FakeSession(pages=3, on_flush=_advance)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_events_gin_pending_lists())
        assert gpl.EVENTS_PASS_BUDGET_S == 20.0
        assert _flushed(session) == list(gpl.EVENTS_GIN_INDEXES[:2])
        assert summary["budget_skipped"] == list(gpl.EVENTS_GIN_INDEXES[2:])
        assert summary["terminal"] == "partial"
        assert not classify_summary(summary).is_green

    def test_the_background_pass_has_no_pass_budget(self, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(gpl.time, "perf_counter", lambda: clock["t"])

        def _advance(_sql):
            clock["t"] += 30.0

        session = FakeSession(pages=3, on_flush=_advance)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert _flushed(session) == list(gpl.BACKGROUND_GIN_INDEXES)
        assert summary["budget_skipped"] == []


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
        assert summary["completed"] == len(gpl.BACKGROUND_GIN_INDEXES)
        assert summary["total"] == len(gpl.BACKGROUND_GIN_INDEXES)
        assert summary["pages_cleaned"] == 11 * len(gpl.BACKGROUND_GIN_INDEXES)
        assert summary["errors"] == []
        assert classify_summary(summary).is_green
        assert session.savepoints == len(gpl.BACKGROUND_GIN_INDEXES)

    def test_one_bad_index_must_not_wipe_the_pass(self, monkeypatch):
        """Gotcha #42, in its maintenance-task form. The healthy siblings are
        asserted BY NAME — a test that only checked `errors` would pass on a
        pass that aborted after the failure."""
        monkeypatch.delenv("SEARCH_GIN_FLUSH_ENABLED", raising=False)
        session = FakeSession(pages=3, fail_on=("ix_futures_name_trgm",))
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "partial"
        assert summary["completed"] == len(gpl.BACKGROUND_GIN_INDEXES) - 1
        assert [e["index"] for e in summary["errors"]] == ["ix_futures_name_trgm"]
        for name in gpl.BACKGROUND_GIN_INDEXES:
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
        session = FakeSession(fail_on=gpl.FLUSHED_GIN_INDEXES)
        _patch_session(monkeypatch, session)
        summary = _run(gpl._flush_gin_pending_lists())
        assert summary["terminal"] == "failed"
        assert summary["completed"] == 0
        assert len(summary["errors"]) == len(gpl.BACKGROUND_GIN_INDEXES)
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
        assert summary["pages_cleaned"] == 480 + (len(gpl.BACKGROUND_GIN_INDEXES) - 1)


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

    def test_the_events_beat_is_on_realtime_every_two_minutes(self):
        """#10090: `background` delivered 37 of 720 fires; the events lists ride
        the queue that delivers its period."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["flush-events-gin-pending-lists"]
        assert entry["task"] == "app.tasks.flush_events_gin_pending_lists"
        assert entry["schedule"] == 120.0
        options = entry["options"]
        assert options["queue"] == "realtime"
        assert (
            0 < options["expires"] <= entry["schedule"]
        ), "an expires longer than the period cannot discard a superseded fire"
        route = celery_app.conf.task_routes["app.tasks.flush_events_gin_pending_lists"]
        assert route == {"queue": "realtime"}, "beat options and task_routes must agree"
        assert "app.tasks.flush_events_gin_pending_lists" in celery_app.tasks

    def test_the_events_task_holds_its_slot_at_most_budget_plus_one_flush(self):
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.flush_events_gin_pending_lists"]
        worst = gpl.EVENTS_PASS_BUDGET_S + gpl.PER_INDEX_TIMEOUT_MS / 1000.0
        assert worst < task.soft_time_limit < task.time_limit
        assert task.time_limit < celery_app.conf.task_time_limit

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
