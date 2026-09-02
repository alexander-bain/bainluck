"""Guards for the image-dimension backfill task.

Two classes of defect matter here and neither is about arithmetic:

1. A run that measures nothing must not read as healthy. The whole reason
   `_tracked_run` classifies a returned summary is that "it returned" is not
   "it worked" — a backfill whose host is unreachable returns a tidy dict of
   zeros and, without a terminal, that used to look like success.
2. One unreachable photo must never wipe the pass. Sweeps in this tree are
   required to be per-item fault-isolated, and the guard asserts the healthy
   siblings actually survive rather than just that no exception escaped.
"""

import pytest

from app.tasks import image_dimensions_backfill as task_module


class _FakeStream:
    def __init__(self, status, chunks):
        self.status_code = status
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _FakeClient:
    """Stands in for httpx.AsyncClient, keyed by URL."""

    def __init__(self, responses):
        self.responses = responses
        self.requested = []

    def stream(self, method, url, headers=None):
        self.requested.append(url)
        entry = self.responses[url]
        if isinstance(entry, Exception):
            raise entry
        return _FakeStream(*entry)


# A real production AVIF header (622x350), reused from the parser guards.
from tests.test_image_dimensions import REAL_AVIF_HEADER, REAL_SIZE  # noqa: E402


class TestMeasureUrl:
    async def test_reads_dimensions_from_a_streamed_prefix(self):
        client = _FakeClient({"u": (200, [REAL_AVIF_HEADER, b"\x00" * 5000])})
        assert await task_module._measure_url(client, "u") == REAL_SIZE

    async def test_stops_reading_once_the_size_is_known(self):
        """The saving is closing the stream early, since the host ignores Range."""
        tail_seen = []

        class _Counting(_FakeStream):
            async def aiter_bytes(self):
                yield REAL_AVIF_HEADER + b"\x00" * 4096
                tail_seen.append(True)
                yield b"\x00" * 100000

        client = _FakeClient({"u": (200, [])})
        client.stream = lambda m, u, headers=None: _Counting(200, [])
        assert await task_module._measure_url(client, "u") == REAL_SIZE
        assert not tail_seen, "kept reading after the dimensions were known"

    async def test_non_200_yields_none(self):
        client = _FakeClient({"u": (404, [b""])})
        assert await task_module._measure_url(client, "u") is None

    async def test_unparseable_body_yields_none_not_a_guess(self):
        client = _FakeClient({"u": (200, [b"nonsense" * 100])})
        assert await task_module._measure_url(client, "u") is None


class TestTerminalTruth:
    """A summary must say what happened; a bare counter dict proves nothing."""

    @pytest.mark.parametrize(
        "urls,measured,expected",
        [
            (0, 0, "no_work"),
            (3, 3, "complete"),
            (3, 1, "partial"),
            (3, 0, "failed"),
            (1, 0, "failed"),
        ],
    )
    def test_terminal_reflects_the_outcome(self, urls, measured, expected):
        # Calls the real classifier. Re-deriving the rule here instead would
        # only ever test this test.
        assert task_module._terminal_for(urls, measured) == expected

    def test_a_fully_failed_pass_never_reads_green(self):
        """The false-GREEN defect this vocabulary exists for."""
        from app.utils.task_verdict import NOT_GREEN, verdict_for

        summary = {"urls": 5, "measured": 0, "terminal": task_module._terminal_for(5, 0)}
        # The label _tracked_run passes for this task; enrolment is what makes
        # the verdict authoritative rather than a legacy unknown.
        assert verdict_for("backfill_image_dims", summary).verdict in NOT_GREEN

    def test_a_drained_pass_is_authoritative_and_not_green(self):
        """The steady state. Honest, and still not a reason to read healthy."""
        from app.utils.task_verdict import NOT_GREEN, verdict_for

        summary = {"urls": 0, "measured": 0, "terminal": task_module._terminal_for(0, 0)}
        verdict = verdict_for("backfill_image_dims", summary)
        assert verdict.verdict in NOT_GREEN
        assert verdict.authoritative, (
            "an unenrolled task classifies as a legacy unknown and still reads "
            "GREEN — enrolment in ENFORCED_TASKS is what makes the terminal bite"
        )

    def test_a_complete_pass_reads_green(self):
        """The control: the enrolment must not make every outcome not-green."""
        from app.utils.task_verdict import NOT_GREEN, verdict_for

        summary = {"urls": 5, "measured": 5, "terminal": task_module._terminal_for(5, 5)}
        assert verdict_for("backfill_image_dims", summary).verdict not in NOT_GREEN

    def test_every_exit_path_stamps_a_terminal(self):
        """A classifier the task forgets to call is a guard that never fires."""
        import ast
        import inspect
        import textwrap

        source = textwrap.dedent(
            inspect.getsource(task_module.backfill_image_dimensions)
        )
        tree = ast.parse(source)
        returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
        assert returns, "no return statements found — re-point this guard"
        assert source.count("_terminal_for(") == len(returns), (
            f"{len(returns)} return paths but "
            f"{source.count('_terminal_for(')} terminal stamps — an unstamped "
            f"exit would be recorded as an unverified success"
        )


class TestEligibility:
    """WHICH rows the pass claims, run against a real engine.

    CERT-709 follow-up `LAT-P193-TMDB-HEIGHT-ELIGIBILITY`. `enrich_tmdb` writes
    a width it can read out of the TMDB path and leaves the height for this task
    to measure. While the selector filtered on `image_width IS NULL`, that
    handoff could never complete — the rows the writer created were precisely
    the rows the reader excluded, so the height it promised would never arrive.

    The guard executes the task's OWN `_SELECT_SQL` on sqlite rather than
    restating the predicate, so narrowing the filter back reddens it instead of
    leaving the test agreeing with itself.
    """

    @staticmethod
    def _select(rows):
        import re
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE futures_markets ("
            " image_url TEXT, image_width INT, image_height INT,"
            " status TEXT, volume_24h REAL)"
        )
        conn.executemany(
            "INSERT INTO futures_markets VALUES (?,?,?,?,?)",
            rows,
        )
        sql = re.sub(r":limit\b", "?", task_module._SELECT_SQL)
        return [r[0] for r in conn.execute(sql, (50,)).fetchall()]

    def test_a_tmdb_row_with_a_width_and_no_height_is_still_claimed(self):
        """The defect. Width known, height NULL — exactly what enrich_tmdb writes."""
        claimed = self._select([("tmdb.jpg", 780, None, "open", 10.0)])
        assert claimed == ["tmdb.jpg"], (
            "a row with a declared width and an unmeasured height was skipped; "
            "enrich_tmdb writes exactly this shape, so the height its comment "
            "promises the backfill will measure would never be written"
        )

    def test_a_never_measured_row_is_claimed(self):
        """The control: the original population must not stop being eligible."""
        assert self._select([("pexels.jpg", None, None, "open", 1.0)]) == ["pexels.jpg"]

    def test_a_fully_measured_row_is_not_claimed(self):
        """The other direction — the pass must still drain rather than loop."""
        assert self._select([("done.jpg", 525, 350, "open", 1.0)]) == []

    def test_resolved_markets_are_never_claimed(self):
        """101k resolved rows never render; sizing them is the cost that was cut."""
        assert self._select([("old.jpg", None, None, "resolved", 999.0)]) == []

    def test_highest_volume_open_market_is_sized_first(self):
        claimed = self._select(
            [
                ("quiet.jpg", None, None, "open", 1.0),
                ("loud.jpg", None, None, "open", 500.0),
            ]
        )
        assert claimed[0] == "loud.jpg"


class _CapturingSession:
    """Records every statement the task issues, and how many times."""

    def __init__(self, log):
        self.log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        self.log.append((str(statement), params))

        class _Result:
            rowcount = 3

            def all(self_inner):
                return []

        return _Result()

    async def commit(self):
        return None


class TestWriteBudget:
    """CERT-709 follow-up `LAT-P193-BACKFILL-INDEX-BUDGET`.

    `futures_markets.image_url` has no index, so what a pass costs is set by how
    many times it looks a url up. One statement per measured url made that 150
    scans of the table per pass; joining the batch makes it one. The guard
    counts statements, which is the quantity the follow-up actually questioned —
    asserting `== 1` rather than `<= N`, so a silent regression to per-url
    writes cannot pass by being merely "not worse".
    """

    async def test_a_whole_batch_is_written_in_one_statement(self, monkeypatch):
        log = []
        monkeypatch.setattr(
            task_module, "get_task_session", lambda: _CapturingSession(log)
        )
        sized = [(f"u{i}", 900, 600) for i in range(150)]

        stored, rows = await task_module._store_dimensions(sized)

        assert len(log) == 1, (
            f"150 measured urls produced {len(log)} statements — the batch join "
            f"is what removes the need for an index on image_url"
        )
        assert stored == 150
        assert rows == 3

    async def test_an_empty_batch_writes_nothing(self):
        assert await task_module._store_dimensions([]) == (0, 0)

    async def test_the_payload_binds_as_a_cast_never_a_double_colon(self):
        """`:payload::jsonb` is skipped by SQLAlchemy's bind regex and reaches
        asyncpg unbound — the #144/#994 failure mode. Compile and look."""
        from sqlalchemy.dialects import postgresql

        compiled = task_module._STORE_SQL_TEXT.compile(
            dialect=postgresql.asyncpg.dialect()
        )
        assert "payload" in compiled.params, (
            "the payload never bound — spell the cast `CAST(:payload AS jsonb)`, "
            "not `:payload::jsonb`"
        )

    async def test_a_failed_batch_falls_back_instead_of_losing_every_read(
        self, monkeypatch
    ):
        """The reads are already paid for; a bad flush must not discard them."""
        calls = []

        def _session():
            calls.append(1)
            if len(calls) == 1:
                class _Boom(_CapturingSession):
                    async def execute(self, statement, params=None):
                        raise RuntimeError("batch exploded")

                return _Boom([])
            return _CapturingSession([])

        monkeypatch.setattr(task_module, "get_task_session", _session)
        stored, rows = await task_module._store_dimensions(
            [("a", 1, 2), ("b", 3, 4)]
        )
        assert stored == 2, "a failed batch discarded reads it had already paid for"
        assert rows == 6


class TestPassAccounting:
    """A photo read but not persisted is a failure of the pass, not a success."""

    async def test_unwritable_reads_are_counted_failed_not_measured(
        self, monkeypatch
    ):
        async def _store_nothing(sized):
            return 0, 0

        monkeypatch.setattr(task_module, "_store_dimensions", _store_nothing)
        monkeypatch.setattr(
            task_module, "get_task_session", lambda: _CapturingSession([])
        )

        class _Urls(_CapturingSession):
            async def execute(self, statement, params=None):
                class _R:
                    def all(self_inner):
                        return [("u",)]

                return _R()

        monkeypatch.setattr(task_module, "get_task_session", lambda: _Urls([]))
        monkeypatch.setattr(
            task_module,
            "_measure_url",
            lambda client, url: _coro(task_module_REAL_SIZE),
        )

        stats = await task_module.backfill_image_dimensions(limit=1)
        assert stats["measured"] == 0
        assert stats["failed"] == 1
        assert stats["terminal"] == "failed", (
            "a pass that persisted nothing reported a healthy terminal"
        )


task_module_REAL_SIZE = REAL_SIZE


async def _coro(value):
    return value
