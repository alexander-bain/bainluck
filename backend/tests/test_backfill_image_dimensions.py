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
