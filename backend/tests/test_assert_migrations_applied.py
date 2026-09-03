"""Guards for the release-phase head assertion (#2741, #2724).

The defect class this closes: the Procfile's ``|| echo`` swallows every Alembic
failure, so a migration that never applied still produces a SUCCESSFUL release
and the web dyno boots new code against the old schema. Since #2724 bounded the
migration's lock wait, an exhausted retry is the expected outcome of the exact
contention being fixed — so the swallowed path stopped being theoretical, which
is why CERT-789 blocked the lock work without this.

Two things are guarded, and they fail separately:

* the comparison itself is correct (:class:`TestDescribe`, :class:`TestMain`), and
* the release command actually RUNS it (:class:`TestTheProcfileRunsTheGuard`) —
  every other test here stays green if the Procfile line is reverted.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "assert_migrations_applied.py"
PROCFILE = BACKEND / "Procfile"


def _load():
    spec = importlib.util.spec_from_file_location("_assert_migrations_guard", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_assert_migrations_guard"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_assert_migrations_guard", None)
    return module


class TestDescribe:
    def test_a_database_at_head_is_reported_ok(self):
        m = _load()
        assert m.describe({"abc"}, {"abc"}).startswith("OK:")

    def test_a_database_behind_head_names_both_sides(self):
        m = _load()
        out = m.describe({"old"}, {"new"})
        assert "RELEASE FAILED" in out
        # Naming only one side leaves the operator guessing which is which.
        assert "old" in out and "new" in out
        assert "never applied:  new" in out

    def test_an_empty_database_is_a_failure_not_a_pass(self):
        # A brand-new/reset database has applied nothing. "No rows" must not
        # read as "nothing to do" — that is gotcha #53's shape.
        m = _load()
        assert m.describe(set(), {"new"}).startswith("RELEASE FAILED")

    def test_a_revision_unknown_to_this_build_is_reported_separately(self):
        m = _load()
        out = m.describe({"from_the_future"}, {"new"})
        assert "unknown to this build: from_the_future" in out

    def test_the_failure_text_points_at_both_causes(self):
        m = _load()
        out = m.describe({"old"}, {"new"})
        assert "#2741" in out, "the operator needs to know the exit code was hidden"
        assert "#2724" in out, "exhausted lock retries are the expected new cause"


class TestMain:
    def _run(self, applied, heads):
        m = _load()
        with mock.patch.object(m, "database_revisions", return_value=applied), (
            mock.patch.object(m, "script_heads", return_value=heads)
        ):
            return m.main()

    def test_at_head_exits_zero(self):
        assert self._run({"abc"}, {"abc"}) == 0

    def test_behind_head_exits_nonzero_so_the_release_fails(self):
        assert self._run({"old"}, {"new"}) == 1

    def test_nothing_applied_exits_nonzero(self):
        assert self._run(set(), {"new"}) == 1


class TestTheProbeCannotHangTheRelease:
    def test_the_connection_carries_bounded_timeouts(self):
        # This runs straight after a migration that may have been fighting for
        # locks. A watchdog free to hang is the defect it exists to catch.
        m = _load()
        args = m._connect_args("postgresql://u:p@db.example.com:5432/x")
        assert "lock_timeout" in args["options"]
        assert "statement_timeout" in args["options"]

    def test_ssl_is_required_for_a_remote_database(self):
        m = _load()
        args = m._connect_args("postgresql://u:p@db.example.com:5432/x")
        assert args.get("sslmode") == "require"

    def test_a_local_database_is_not_forced_through_ssl(self):
        m = _load()
        args = m._connect_args("postgresql://postgres:postgres@localhost:5432/bainluck")
        assert "sslmode" not in args


class TestTheProcfileRunsTheGuard:
    """The guard is worthless if the release command does not invoke it."""

    def _release_line(self) -> str:
        for line in PROCFILE.read_text().splitlines():
            if line.startswith("release:"):
                return line
        raise AssertionError("Procfile has no release: line")

    def test_the_release_command_invokes_the_assertion(self):
        assert "scripts/assert_migrations_applied.py" in self._release_line(), (
            "the release phase does not run the head assertion; a swallowed "
            "Alembic failure would deploy new code against the old schema (#2741)"
        )

    def test_the_assertion_runs_after_the_upgrade_not_before(self):
        # Before the upgrade it would assert the OLD state and pass every time.
        line = self._release_line()
        assert line.index("alembic upgrade heads") < line.index(
            "scripts/assert_migrations_applied.py"
        )

    def test_the_assertion_is_chained_with_and_so_its_exit_code_counts(self):
        # `;` or `|| echo` around it would reproduce the very bug it closes.
        line = self._release_line()
        tail = line[line.index("scripts/assert_migrations_applied.py") :]
        assert "||" not in tail, "the assertion's own failure must not be swallowed"
        prefix = line[: line.index("python3 scripts/assert_migrations_applied.py")]
        assert prefix.rstrip().endswith("&&"), (
            "the assertion must be chained with && or its exit code cannot fail "
            "the release"
        )

    def test_the_script_the_procfile_names_exists(self):
        # A release command naming a path that is not there fails every deploy.
        assert SCRIPT.exists()
