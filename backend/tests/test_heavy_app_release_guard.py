"""The heavy app's release phase must never run Alembic (#5003).

WHY THIS EXISTS

``bainluck-heavy`` is a second Heroku app that runs the ``worker-heavy`` dyno
against the **same** Postgres as the primary app. Both deploy the same code, so
both run the same ``release:`` command. Migrations must be owned by exactly one
app: two apps racing ``alembic upgrade heads`` on one database is how you get a
half-applied migration and a lock nobody owns.

The switch is ``HEAVY_APP=1``, set on the heavy app only::

    heroku config:set HEAVY_APP=1 -a bainluck-heavy

WHAT STAYS ON, DELIBERATELY

* The **import check** runs on both apps. It is the thing that stops a broken
  import reaching a dyno, and the heavy app boots the same code.
* ``scripts/assert_migrations_applied.py`` runs on both apps. On the heavy app
  it is the fail-closed half of "migrations in one app only": if the primary
  has not yet applied a migration this code needs, the heavy release FAILS
  rather than booting workers against a schema they do not match. That means
  **deploy order matters** — primary first, then heavy.

WHY THESE TESTS EXECUTE THE LINE INSTEAD OF GREPPING IT

A test that only asserts ``"HEAVY_APP" in release_line`` passes just as happily
if the branch is inverted, if the variable is compared to the wrong value, or
if the ``else`` arm loses its upgrade. It reads as a guard and guards nothing.
So the two tests that matter here run the real release command under ``bash``
with stub executables on ``PATH`` and observe whether ``alembic`` was actually
invoked — in **both** directions, because "it skipped" is only half the claim.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
PROCFILE = BACKEND / "Procfile"


def _release_line() -> str:
    for line in PROCFILE.read_text().splitlines():
        if line.startswith("release:"):
            return line[len("release:") :].strip()
    raise AssertionError("Procfile has no release: line")


def _run_release(tmp_path: Path, heavy_app: str | None) -> tuple[int, bool, str]:
    """Run the real release command with stubbed binaries.

    Returns (exit code, whether `alembic` was invoked, combined output).
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    marker = tmp_path / "alembic_ran"

    # `alembic` records that it was called, then succeeds.
    (stub_dir / "alembic").write_text(
        f'#!/bin/sh\necho "stub alembic $*" >> "{marker}"\nexit 0\n'
    )
    # `python3` stands in for both the import check and the head assertion.
    (stub_dir / "python3").write_text('#!/bin/sh\necho "stub python3 $*"\nexit 0\n')
    for stub in stub_dir.iterdir():
        stub.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env.pop("HEAVY_APP", None)
    if heavy_app is not None:
        env["HEAVY_APP"] = heavy_app

    proc = subprocess.run(
        ["bash", "-c", _release_line()],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, marker.exists(), proc.stdout + proc.stderr


class TestTheHeavyAppSkipsAlembic:
    """Both directions. Either one alone is a test that cannot fail usefully."""

    def test_heavy_app_1_does_not_run_alembic(self, tmp_path):
        code, alembic_ran, out = _run_release(tmp_path, "1")
        assert code == 0, f"release failed on the heavy app: {out}"
        assert not alembic_ran, (
            "HEAVY_APP=1 still invoked alembic — two apps upgrading one database "
            f"is the defect this guard exists to stop. Output:\n{out}"
        )

    def test_the_primary_app_still_runs_alembic(self, tmp_path):
        # The half that catches a guard which skips for EVERYONE. Without this,
        # deleting `alembic upgrade heads` outright would pass the test above.
        code, alembic_ran, out = _run_release(tmp_path, None)
        assert code == 0, f"release failed on the primary app: {out}"
        assert alembic_ran, (
            "the primary app did not run alembic upgrade — the guard is not "
            f"conditional, it is an unconditional skip. Output:\n{out}"
        )

    @pytest.mark.parametrize("value", ["0", "", "true", "yes", "2"])
    def test_only_the_exact_value_1_skips_the_upgrade(self, tmp_path, value):
        # A truthy-string check (`if [ -n "$HEAVY_APP" ]`) would silently skip
        # migrations on any app where someone set HEAVY_APP=0 to mean "off".
        _, alembic_ran, out = _run_release(tmp_path, value)
        assert alembic_ran, (
            f"HEAVY_APP={value!r} skipped the upgrade; only the exact value '1' "
            f"may skip it. Output:\n{out}"
        )


class TestTheRestOfTheReleasePhaseIsUnchanged:
    def test_the_head_assertion_still_runs_on_the_heavy_app(self):
        # Fail-closed: heavy must refuse to boot against a schema it does not
        # match. The assertion sits outside the branch, so it runs for both.
        line = _release_line()
        tail = line[line.index("scripts/assert_migrations_applied.py") :]
        assert "fi" not in tail, (
            "the head assertion moved inside the HEAVY_APP branch; the heavy app "
            "would then boot workers against an unmigrated schema"
        )

    def test_the_import_check_runs_before_the_branch(self):
        line = _release_line()
        assert line.index("from app.main import app") < line.index("HEAVY_APP"), (
            "the import check must run on both apps, before the branch"
        )

    def test_the_switch_is_named_exactly_as_alex_is_told_to_set_it(self):
        # The alex-inbox note tells him `heroku config:set HEAVY_APP=1`. A
        # rename here without a rename there is a silent no-op on production.
        assert "HEAVY_APP" in _release_line()
