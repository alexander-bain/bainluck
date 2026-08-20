"""CAL-P076 — the #1978 census worker actually runs, and actually resumes.

CAL-P075 shipped this worker with 37 tests and a green 17,093-test suite. All 37
are pure: SQL-string invariants and the pure fold. **Nothing started the worker.**
Three defects went to production behind that:

1. ``'_AsyncGeneratorContextManager' object has no attribute '__anext__'`` —
   ``get_task_session`` is an ``@asynccontextmanager`` and the worker hand-drove
   it as a bare async generator. Every production invocation died in **73 ms**
   before opening a connection (task-metrics, 2026-08-19T23:33:48Z).
2. The per-page checkpoint was written with envelope ``complete=False``, which
   ``decode_envelope`` types as MALFORMED/IncompleteArtifact. ``_read_checkpoint``
   requires ``read.ok``, so **``resume=True`` never resumed** — every invocation
   restarted at cursor 0 and the walk could not span two budgets.
3. Same cause: ``GET /admin/cohort-cell-census/last`` answered
   ``artifact_unreadable: malformed`` over a perfectly good partial census, in
   direct contradiction of its own docstring ("a partial read is a first-class
   answer here"). Observed live at 2026-08-19T23:55Z, mid-run.

The sibling ``save_main_checkpoint`` had the answer written on it the whole time:
*"The RECORD is whole; the build's own state is `terminal` above."*
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.tasks import cohort_cell_census_worker as W


class _Res:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _Session:
    """Answers the roster with nothing, so the walk completes in one empty page."""

    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        self.statements.append(" ".join(str(stmt).split()))
        return _Res()


class TestTheWorkerCanActuallyStart:
    @pytest.mark.asyncio
    async def test_the_session_is_entered_the_way_get_task_session_is_defined(
        self, monkeypatch
    ):
        """The regression test the 37 pure ones could not be.

        The fake here is a REAL ``@asynccontextmanager``, exactly like the thing
        it stands in for — so the old ``session_gen.__anext__()`` form fails this
        with the production AttributeError, and no amount of duck-typing the fake
        can hide it.
        """
        session = _Session()

        @asynccontextmanager
        async def _fake():
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake)

        written: list[tuple[dict, bool]] = []

        async def _write(payload, *, complete):
            written.append((payload, complete))
            return True

        async def _read():
            return None

        monkeypatch.setattr(W, "_write_checkpoint", _write)
        monkeypatch.setattr(W, "_read_checkpoint", _read)

        report = await W.run_cohort_cell_census(page_size=10, resume=False)

        assert report["complete"] is True
        assert report["pages_done"] == 0
        assert any("statement_timeout" in s for s in session.statements)
        assert written, "the run must checkpoint even when it finds nothing"


class TestTheCheckpointIsReadable:
    @pytest.mark.asyncio
    async def test_an_in_flight_checkpoint_is_a_WHOLE_record_of_a_partial_job(
        self, monkeypatch
    ):
        """The envelope's ``complete`` and the job's ``complete`` are different
        facts. Conflating them made every mid-walk cursor unreadable."""
        captured: dict = {}

        async def _publish(envelope):
            captured["envelope"] = envelope
            return {"status": "ok"}

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )

        ok = await W._write_checkpoint({"cursor": 42, "pages_done": 7}, complete=False)

        assert ok is True
        env = captured["envelope"]
        assert env.complete is True, "the ROW is a whole record of where the walk got to"
        assert env.payload["complete"] is False, "the JOB is not finished, and says so"
        assert env.payload["cursor"] == 42

    @pytest.mark.asyncio
    async def test_the_partial_census_is_readable_after_the_write(self, monkeypatch):
        """End to end through the real envelope decoder: write mid-walk, read it
        back. This is the assertion that fails on the shipped form, because
        ``decode_envelope`` refuses an envelope marked incomplete."""
        from app.utils import durable_state as ds
        from app.utils.cohort_cell_census import CENSUS_IDENTITY, CENSUS_SCHEMA

        store: dict = {}

        async def _publish(envelope):
            store["env"] = envelope
            return {"status": "ok"}

        async def _read(identity, **kw):
            env = store.get("env")
            if env is None:
                return ds.EnvelopeRead(status="missing", tier="durable")
            return ds.decode_envelope(
                {
                    "identity": env.identity,
                    "schema_version": env.schema_version,
                    "generation": env.generation,
                    "generated_at": env.generated_at,
                    "payload": env.payload,
                    "checksum": env.checksum,
                    "complete": env.complete,
                    "source": env.source,
                },
                tier="durable",
                expected_version=CENSUS_SCHEMA,
                max_age_s=30 * 86400,
            )

        monkeypatch.setattr(
            "app.services.durable_snapshots.publish_snapshot_standalone", _publish
        )
        monkeypatch.setattr(
            "app.services.durable_snapshots.read_snapshot_standalone", _read
        )

        await W._write_checkpoint(
            {"run_id": "abc", "cursor": 99, "pages_done": 3}, complete=False
        )
        prior = await W._read_checkpoint()

        assert prior is not None, "a mid-walk cursor must be resumable"
        assert prior["cursor"] == 99
        assert prior["complete"] is False
        assert store["env"].identity == CENSUS_IDENTITY

    @pytest.mark.asyncio
    async def test_the_walk_resumes_from_the_banked_cursor(self, monkeypatch):
        """The property the whole design is named for, asserted rather than
        assumed: a second invocation continues where the first stopped."""
        session = _Session()

        @asynccontextmanager
        async def _fake():
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake)

        async def _read():
            return {
                "run_id": "carried",
                "cursor": 12345,
                "pages_done": 8,
                "bins": {},
                "paged_totals": {"tennis/quantity": 8000},
                "roster_totals": {"tennis/quantity": 9000},
                "failed_ranges": [],
                "complete": False,
            }

        async def _write(payload, *, complete):
            return True

        monkeypatch.setattr(W, "_read_checkpoint", _read)
        monkeypatch.setattr(W, "_write_checkpoint", _write)

        report = await W.run_cohort_cell_census(page_size=10, resume=True)

        assert report["run_id"] == "carried"
        assert report["pages_done"] == 8, "the prior pages are carried, not re-walked"
        # The roster is NOT re-read on a resume — comparing a half-walked cursor
        # against a freshly-counted roster reports every cell as a mismatch.
        assert not any("GROUP BY 1, 2" in s for s in session.statements)
