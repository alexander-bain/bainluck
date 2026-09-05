"""CAL-P129 — the measured-sigma overlay must not vanish because of a CWD.

CAL-P128 shipped a measured-SE ledger and wired the board to report it. The
wiring works, and it worked in the session that built it, because that session
ran ``python3 backend/scripts/calibration_scorecard.py`` from the repository
root. Run the identical command the way CLAUDE.md documents every other backend
script — ``cd backend && python3 scripts/...`` — and the entire overlay is gone:

    from repo root   queued_cells_measured 12   refuted 2   at_bar_if_applied 31
    from backend/    queued_cells_measured  0   refuted 0   at_bar_if_applied 29

No error, no banner, no non-zero exit. A complete, plausible, well-formed board
that silently omits the finding the previous session shipped — and omits it in
the direction that makes the queue look longer and every refuted cell look real.

Two defects compose to produce that, and this file pins both:

1. **``LEDGER_PATH`` was relative**, so it resolved against the caller's working
   directory. A path to a COMMITTED artifact is a property of the repository,
   not of where someone happened to stand.
2. **``load()`` degraded silently on a missing file** — ``return {"entries":
   {}}`` — directly under a docstring that says *"Refusing beats degrading"* and
   a call-site comment naming gotcha #53. The malformed case was covered and
   raises; the absent case is the one that actually fires, and it did not.

The load-bearing guard is :class:`TestTheBoardReadsTheSameFromEitherDirectory`,
which drives the real script as a subprocess from two working directories and
compares the served output. Everything else here is a unit-level statement of
why that end-to-end guard passes; none of them can replace it, because both
defects are invisible to any test that imports the module and never chdirs.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
_SCRIPTS = _BACKEND / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ledger_mod = _load("calibration_sigma_ledger")

#: A payload captured from the served ``/api/calibration`` at population ``q268``
#: — the same body CAL-P128 measured against. Pinned rather than fetched: a test
#: that needs the network fails for the wrong reason.
_PAYLOAD = _REPO / "artifacts" / "cal-p126" / "payload-q268.json"


def _run_scorecard(cwd: pathlib.Path) -> dict:
    """Drive the real script from ``cwd`` and return its JSON result.

    Uses ``--out`` rather than parsing stdout: stdout carries the human board
    after the JSON and splitting on prose is how a guard starts asserting
    against its own formatting.
    """
    out = cwd / f".p129-scorecard-{os.getpid()}.json"
    script = os.path.relpath(_SCRIPTS / "calibration_scorecard.py", cwd)
    payload = os.path.relpath(_PAYLOAD, cwd)
    try:
        proc = subprocess.run(
            [sys.executable, script, "--payload", payload, "--out", out.name],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            f"scorecard exited {proc.returncode} from {cwd}\n"
            f"--- stderr ---\n{proc.stderr[-4000:]}"
        )
        return json.loads(out.read_text())
    finally:
        out.unlink(missing_ok=True)


class TestTheLedgerPathIsAPropertyOfTheRepositoryNotOfTheCaller:
    def test_ledger_path_is_absolute(self):
        assert ledger_mod.LEDGER_PATH.is_absolute(), (
            "LEDGER_PATH points at a COMMITTED artifact. A relative default "
            "resolves against whatever directory the caller stood in, which is "
            "how the whole overlay went missing."
        )

    def test_ledger_path_points_at_the_committed_ledger(self):
        """MOVED by CAL-P1002, and the move made this guard stricter.

        The ledger was committed at ``artifacts/calibration-scorecard/``. Heroku
        builds this app through ``subdir-heroku-buildpack`` with
        ``PROJECT_PATH=backend``, so the repo-root ``artifacts/`` tree is not in
        the slug — and once D62 made the app READ the ledger, that path would
        have been present in every test and absent on every production request.
        CAL-P129's own defect (a path resolved somewhere real code never looks)
        in the one environment that serves readers.

        So the assertion is now two, not one: the exact path, AND that it is
        inside ``backend/`` — which is the property that survives if anyone ever
        tidies the file somewhere prettier.
        """
        assert ledger_mod.LEDGER_PATH == (
            _BACKEND / "app" / "data" / "calibration_measured_sigma.json"
        )
        assert _BACKEND in ledger_mod.LEDGER_PATH.parents, (
            "PROJECT_PATH=backend — a ledger outside backend/ is not deployed, "
            "so the app would read it fine locally and never in production."
        )

    def test_ledger_path_does_not_move_when_the_cwd_does(self, tmp_path, monkeypatch):
        before = ledger_mod.LEDGER_PATH
        monkeypatch.chdir(tmp_path)
        reloaded = _load("calibration_sigma_ledger")
        assert reloaded.LEDGER_PATH == before

    def test_the_committed_ledger_is_actually_there_and_loads(self):
        """The path being absolute is worth nothing if it is absolute and wrong."""
        led = ledger_mod.load(ledger_mod.LEDGER_PATH)
        assert led.get("schema") == ledger_mod.SCHEMA
        assert len(led.get("entries") or {}) >= 12, (
            "CAL-P128 banked fourteen measured cells; the ledger the board "
            "reads by default must be that ledger, not an empty stub."
        )


class TestAMissingLedgerIsLoudNotEmpty:
    def test_load_raises_on_a_missing_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ledger_mod.load(tmp_path / "nope.json")

    def test_load_returns_empty_only_when_absence_is_asked_for(self, tmp_path):
        led = ledger_mod.load(tmp_path / "nope.json", missing_ok=True)
        assert led == {"schema": ledger_mod.SCHEMA, "entries": {}}

    def test_missing_ok_defaults_to_false(self):
        """The safe behaviour is the DEFAULT, not an option a caller remembers."""
        import inspect

        sig = inspect.signature(ledger_mod.load)
        assert sig.parameters["missing_ok"].default is False

    def test_a_malformed_ledger_still_raises(self, tmp_path):
        """The half CAL-P128 got right must not regress while fixing the other."""
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema": 1, "entries": {"kalshi/x": {}}}))
        with pytest.raises(ValueError):
            ledger_mod.load(bad)

    def test_build_can_still_start_from_no_ledger_at_all(self, tmp_path):
        """``--build`` legitimately runs before any ledger exists.

        Making absence loud must not make the first build impossible; the
        build path is the one caller entitled to ``missing_ok``.
        """
        artifacts = sorted((_REPO / "artifacts" / "cal-p128").glob("sigma-*.json"))
        if not artifacts:
            pytest.skip("no sigma artifacts committed to build from")
        proc = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS / "calibration_sigma_ledger.py"),
                "--build",
                *[str(a) for a in artifacts],
                "--out",
                str(tmp_path / "fresh.json"),
                "--show",
            ],
            cwd=_REPO,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-3000:]
        assert (tmp_path / "fresh.json").exists()

    def test_build_refuses_a_missing_artifact_instead_of_shortening_the_ledger(
        self, tmp_path
    ):
        """Third instance of the same class.

        ``--build a.json b.json typo.json`` used to filter the typo out and
        report success, writing a ledger one cell short. A cell must not lose
        its measurement because nobody decided to drop it.
        """
        real = sorted((_REPO / "artifacts" / "cal-p128").glob("sigma-*.json"))
        if not real:
            pytest.skip("no sigma artifacts committed to build from")
        out = tmp_path / "short.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS / "calibration_sigma_ledger.py"),
                "--build",
                str(real[0]),
                str(tmp_path / "typo.json"),
                "--out",
                str(out),
            ],
            cwd=_REPO,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 1, proc.stdout[-2000:]
        assert "typo.json" in proc.stdout
        assert not out.exists(), "refused, so nothing may have been written"


class TestTheBoardReadsTheSameFromEitherDirectory:
    """The end-to-end guard. Both defects are invisible without a chdir."""

    @pytest.fixture(scope="class")
    def both(self):
        if not _PAYLOAD.exists():
            pytest.skip(f"captured payload missing: {_PAYLOAD}")
        return _run_scorecard(_REPO), _run_scorecard(_BACKEND)

    def test_the_measured_sigma_block_is_identical(self, both):
        root, backend = both
        assert root["measured_sigma"] == backend["measured_sigma"], (
            "The board reported a different overlay from two directories. That "
            "is the CAL-P129 defect, and it is silent."
        )

    def test_the_overlay_is_populated_not_merely_equal(self, both):
        """Two identically-empty overlays would satisfy the test above."""
        root, _ = both
        ms = root["measured_sigma"]
        assert ms["decides"] is True
        assert ms["material_cells_measured"] + ms["material_cells_carried"] >= 12
        assert ms["cells_refuted"] >= 1
        assert ms["refuted_excess_outcomes"] > 0

    def test_the_whole_result_is_identical_apart_from_nothing(self, both):
        root, backend = both
        assert root == backend

    def test_the_needle_is_the_same_from_both_directories(self, both):
        """CAL-P129's claim, unchanged: whatever the needle reads, a chdir must
        not change it. What it reads DID change — D62 made the measured sigma
        decide, so the captured q268 payload now scores one cell higher — and
        the row basis is asserted beside it so this test cannot be satisfied by
        two identically-broken runs.
        """
        root, backend = both
        assert root["counts"]["cells_at_bar"] == backend["counts"]["cells_at_bar"]
        assert root["counts"]["cells_at_bar_row_basis"] == 29, (
            "the pre-D62 reading of this captured payload, kept as the anchor"
        )
        assert root["counts"]["cells_at_bar"] > 29, (
            "and the measurement moved it — a run where it did not would mean "
            "the ledger silently failed to load"
        )
        assert root["done"] is False


class TestOptingOutIsStillPossibleAndStillExplicit:
    def test_no_sigma_ledger_yields_the_pre_p128_board(self):
        if not _PAYLOAD.exists():
            pytest.skip(f"captured payload missing: {_PAYLOAD}")
        out = _REPO / f".p129-nosigma-{os.getpid()}.json"
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS / "calibration_scorecard.py"),
                    "--payload",
                    str(_PAYLOAD),
                    "--no-sigma-ledger",
                    "--out",
                    str(out),
                ],
                cwd=_BACKEND,
                capture_output=True,
                text=True,
                timeout=300,
            )
            assert proc.returncode == 0, proc.stderr[-3000:]
            res = json.loads(out.read_text())
            assert res["measured_sigma"]["decides"] is False
            assert res["measured_sigma"]["material_cells_measured"] == 0
            assert res["counts"]["cells_at_bar"] == 29
        finally:
            out.unlink(missing_ok=True)

    def test_a_bad_explicit_ledger_path_fails_loudly(self, tmp_path):
        """``--sigma-ledger /does/not/exist`` must not read as 'no measurements'."""
        if not _PAYLOAD.exists():
            pytest.skip(f"captured payload missing: {_PAYLOAD}")
        proc = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS / "calibration_scorecard.py"),
                "--payload",
                str(_PAYLOAD),
                "--sigma-ledger",
                str(tmp_path / "absent.json"),
            ],
            cwd=_BACKEND,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode != 0
