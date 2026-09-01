"""#2396 — the clock sweep must grade ITSELF before it grades a target.

``scripts/clock_sweep.py`` reported ``5 failed, 12 passed`` at all 12 faked
clocks on ``tests/test_sentinel_durable_evidence_298.py`` — identically before
and after a real repair — while that fixture passes 17/17 at the real clock.
The target was clock-invariant the whole time. The fault was the harness: it
replaced ``datetime.datetime`` with a plain SUBCLASS, so every
``isinstance(value, datetime)`` in the tree started answering "no" about
genuine datetimes and their callers reported good values as unparseable.

A red that means the same thing whether or not the target has a problem is not
a finding (gotcha #53). These guards hold the line that makes the tool
readable: the self-check must go RED on a broken harness and GREEN on a sound
one, and a harness fault must never be dressed up as a conclusion about the
target.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "clock_sweep.py"
_SPEC = importlib.util.spec_from_file_location("clock_sweep_2396", SCRIPT_PATH)
clock_sweep = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules[_SPEC.name] = clock_sweep
_SPEC.loader.exec_module(clock_sweep)


# Points that matter: an ordinary instant, a midnight boundary, and a far-future
# one (where a calendar-expiring fixture — and a sloppy patch — come apart).
_INSTANTS = [
    datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
    datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc),
    datetime(2027, 10, 4, 16, 0, tzinfo=timezone.utc),
]


def _probe(patch_source: str, instant: datetime):
    """Run the self-check body under an ARBITRARY patch and return the process."""
    iso = instant.isoformat()
    return clock_sweep._run(
        patch_source.format(fake=iso) + clock_sweep._SELF_CHECK_TAIL.format(fake=iso)
    )


# --- The self-check is green only on a sound harness -------------------------


@pytest.mark.parametrize("instant", _INSTANTS)
def test_self_check_passes_under_the_shipped_patch(instant):
    """Positive control: the harness we actually ship is sound at every point."""
    assert clock_sweep._self_check_problems(instant) == []


@pytest.mark.parametrize("instant", _INSTANTS)
def test_the_shipped_patch_moves_the_clock_and_keeps_type_identity(instant):
    """Both halves, asserted on the real child process rather than inferred.

    The clock must MOVE (or the sweep proves nothing) and a datetime must still
    BE a datetime (or the sweep's red is its own).
    """
    iso = instant.isoformat()
    body = (
        "from datetime import datetime, timezone\n"
        "print('NOW', datetime.now(timezone.utc).isoformat())\n"
        "print('ISINSTANCE', isinstance(datetime.now(timezone.utc), datetime))\n"
        "print('ISINSTANCE_REAL', isinstance(_real.now(timezone.utc), datetime))\n"
    )
    proc = clock_sweep._run(clock_sweep._PATCH.format(fake=iso) + body)
    assert proc.returncode == 0, proc.stderr
    out = dict(
        line.split(" ", 1) for line in proc.stdout.strip().splitlines() if " " in line
    )
    assert out["NOW"] == instant.isoformat(), "the harness did not move the clock"
    assert out["ISINSTANCE"] == "True"
    # The case that actually broke: a datetime the harness did NOT mint — the
    # shape every DB row and every fromisoformat() hands you.
    assert out["ISINSTANCE_REAL"] == "True"


# --- ...and RED on each way it can be broken ---------------------------------


@pytest.mark.parametrize("instant", _INSTANTS)
def test_self_check_catches_the_2396_type_identity_fault(instant):
    """THE PLANT: drop the metaclass and the self-check must go red.

    This is the exact defect that cost eleven cycles. If this test ever passes
    because the mutation stopped applying, the assertion below catches that
    first — a plant that no longer plants is a vacuous guard.
    """
    legacy = clock_sweep._PATCH.replace(", metaclass=_FakeMeta", "")
    assert legacy != clock_sweep._PATCH, (
        "the mutation did not apply — _PATCH no longer spells the metaclass this "
        "way, so this guard would be testing nothing"
    )

    proc = _probe(legacy, instant)
    assert proc.returncode != 0, "the old subclass-only patch must NOT read as sound"
    assert "isinstance" in proc.stdout, proc.stdout
    assert "type identity" in proc.stdout, proc.stdout


@pytest.mark.parametrize("instant", _INSTANTS)
def test_self_check_catches_a_harness_that_never_moved_the_clock(instant):
    """A no-op harness must not self-certify.

    Without this, every other assertion in the self-check would pass vacuously
    against the real clock and the tool would report a sweep it never performed.
    """
    proc = _probe("import sys\n", instant)
    assert proc.returncode != 0
    assert "clock did not move" in proc.stdout, proc.stdout


def test_self_check_reports_a_crash_instead_of_reading_it_as_sound():
    """A patch that dies before printing is a fault, not an empty problem list."""
    proc = clock_sweep._run("import sys\nraise SystemExit(3)\n")
    assert proc.returncode == 3  # sanity: the child really did die early

    # The driver turns that into a non-empty problem list rather than [].
    original = clock_sweep._run
    try:
        clock_sweep._run = lambda source: proc
        assert clock_sweep._self_check_problems(_INSTANTS[0]) != [], (
            "a self-check that exits non-zero without printing must still be a fault"
        )
    finally:
        clock_sweep._run = original


# --- A harness fault must never be dressed up as a finding -------------------


def test_a_harness_fault_yields_no_conclusion_and_never_runs_the_target(
    monkeypatch, capsys
):
    """Exit 2, say so, and do not touch the target.

    The old tool's failure mode was a confident sentence — "the target reads the
    clock" — printed on evidence that could not distinguish the target from the
    tool.
    """
    monkeypatch.setattr(
        clock_sweep, "_self_check_problems", lambda inst: ["type identity broken"]
    )
    ran: list[str] = []
    monkeypatch.setattr(
        clock_sweep, "_run", lambda source: ran.append(source) or pytest.fail("ran")
    )
    monkeypatch.setattr(sys, "argv", ["clock_sweep.py", "tests/whatever.py"])

    rc = clock_sweep.main()
    out = capsys.readouterr().out

    assert rc == 2, "a harness fault is its own exit code, not the target's 1"
    assert "HARNESS FAULT" in out
    assert "NO CONCLUSION" in out
    assert "reads the clock" not in out, (
        "the tool claimed something about the target while its own patch was broken"
    )
    assert ran == [], "the target must not be run under a harness known to be unsound"


class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _scripted_run(monkeypatch, codes):
    """Stub ``_run`` to return ``codes`` in order; first call is the BASELINE.

    ``clock_sweep`` runs the target once unpatched before it sweeps, so a stub
    that returns one fixed code cannot tell the two apart — which is exactly the
    conflation CERT-625 was about.
    """
    monkeypatch.setattr(clock_sweep, "_self_check_problems", lambda inst: [])
    seen: list[str] = []
    it = iter(codes)

    def _fake_run(source):
        seen.append(source)
        code = next(it, codes[-1])
        summary = {0: "2 passed", 1: "1 failed, 1 passed"}.get(code, "no tests ran")
        return _Proc(code, f"===== {summary} =====")

    monkeypatch.setattr(clock_sweep, "_run", _fake_run)
    return seen


def test_a_sound_harness_still_reaches_a_verdict_about_the_target(monkeypatch, capsys):
    """The gate must not become a blanket refusal — the tool still has a job.

    Guards that only prove a thing is blocked can pass while the ship stops
    working, so this asserts the green path still runs the target and grades it:
    green at the real clock, red under a faked one, verdict ``1``.
    """
    seen = _scripted_run(monkeypatch, [0, 1])
    monkeypatch.setattr(
        sys, "argv", ["clock_sweep.py", "tests/whatever.py", "--offsets", "0", "--no-future"]
    )

    rc = clock_sweep.main()
    out = capsys.readouterr().out

    assert rc == 1
    assert seen, "a sound harness must actually run the target"
    assert "tests/whatever.py" in seen[0]
    assert "reads the clock" in out
    assert "HARNESS FAULT" not in out


def test_an_invariant_target_is_green_end_to_end(monkeypatch, capsys):
    seen = _scripted_run(monkeypatch, [0, 0])
    monkeypatch.setattr(
        sys, "argv", ["clock_sweep.py", "tests/whatever.py", "--offsets", "0", "--no-future"]
    )

    assert clock_sweep.main() == 0
    out = capsys.readouterr().out
    assert "invariant to wall-clock time" in out
    assert len(seen) == 3, "one baseline plus two swept points"


# --- CERT-625: pytest's exit code is not a boolean ---------------------------


@pytest.mark.parametrize(
    "code,verdict",
    [(0, "PASS"), (1, "FAIL"), (2, "FAULT"), (3, "FAULT"), (4, "FAULT"), (5, "FAULT"), (137, "FAULT")],
)
def test_only_exit_1_is_a_test_result(code, verdict):
    """gotcha #54: `1` is a result; everything else is a story about the harness."""
    assert clock_sweep._classify(code)[0] == verdict


def test_an_invalid_target_is_a_fault_not_a_clock_finding(monkeypatch, capsys):
    """A typo'd nodeid used to print "the target reads the clock" twelve times."""
    _scripted_run(monkeypatch, [4])
    monkeypatch.setattr(
        sys, "argv", ["clock_sweep.py", "tests/nope.py", "--offsets", "0", "--no-future"]
    )

    rc = clock_sweep.main()
    out = capsys.readouterr().out

    assert rc == 2, "a usage error is a harness fault, not the target's 1"
    assert "HARNESS FAULT" in out
    assert "NO CONCLUSION" in out
    assert "reads the clock" not in out


def test_an_already_red_target_yields_no_conclusion(monkeypatch, capsys):
    """An always-failing, clock-free target is not a time bomb.

    Without a real-clock baseline, "fails at all 12 points" is indistinguishable
    from clock dependence — so a plain `assert False` was reported as one.
    """
    seen = _scripted_run(monkeypatch, [1])
    monkeypatch.setattr(
        sys, "argv", ["clock_sweep.py", "tests/broken.py", "--offsets", "0", "--no-future"]
    )

    rc = clock_sweep.main()
    out = capsys.readouterr().out

    assert rc == 2
    assert "ALREADY RED at the real clock" in out
    assert "NO CONCLUSION" in out
    assert "reads the clock" not in out
    assert len(seen) == 1, "the sweep must not run once the baseline is red"


def test_a_fault_at_one_swept_point_poisons_the_whole_sweep(monkeypatch, capsys):
    """Baseline green, one point a real FAIL, one point exit 3.

    The target may well read the clock — but this run cannot say so, and saying
    so anyway is the class CERT-625 blocked.
    """
    _scripted_run(monkeypatch, [0, 1, 3])
    monkeypatch.setattr(
        sys, "argv", ["clock_sweep.py", "tests/whatever.py", "--offsets", "0,1", "--no-future"]
    )

    rc = clock_sweep.main()
    out = capsys.readouterr().out

    assert rc == 2
    assert "HARNESS FAULT" in out
    assert "INTERNAL ERROR" in out
    assert "reads the clock" not in out


def test_the_pytest_tail_is_self_contained(monkeypatch):
    """The baseline runs it WITHOUT `_PATCH`, so it cannot borrow that import.

    Regression pin: the first draft of the baseline crashed with
    `NameError: name 'sys' is not defined` and the crash read as "already red".
    """
    proc = clock_sweep._run(
        clock_sweep._PYTEST_TAIL.format(args=["--version"])
    )
    assert "NameError" not in proc.stderr, proc.stderr[-400:]


def test_self_check_only_stops_before_the_target(monkeypatch, capsys):
    monkeypatch.setattr(clock_sweep, "_self_check_problems", lambda inst: [])
    monkeypatch.setattr(
        clock_sweep, "_run", lambda source: pytest.fail("target must not run")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["clock_sweep.py", "tests/whatever.py", "--self-check-only", "--no-future"],
    )

    assert clock_sweep.main() == 0
    assert "target not run" in capsys.readouterr().out


# --- The fixture that carried the false red ----------------------------------


def test_the_sweeps_own_anchor_offsets_do_not_branch_on_the_clock():
    """Gotcha #44: offset FIRST, then truncate — asserted on the tool's own math."""
    anchor = datetime(2026, 8, 31, 0, 0, tzinfo=timezone.utc)
    points = clock_sweep._points(anchor, [-8.0, 0.0, 8.0])
    assert points == [
        anchor - timedelta(hours=8),
        anchor,
        anchor + timedelta(hours=8),
    ]
