"""The lane-lock writer must REPLACE its `status:` line, never compound it (ruling 071).

WHY THIS EXISTS — the measured failure, not a hypothetical.

`scripts/claim_lane_lock.py` located the status line with ``^status:\\s*(\\S+)``.
That matches ``status:`` plus the FIRST TOKEN only, so ``m.end()`` stopped after
the word ``HELD``/``RELEASED`` and both writers did::

    text[:m.start()] + "status: NEW   # stamp." + text[m.end():]

which re-appended everything already on the line. Every claim and every release
therefore **compounded** it. Measured on the real handoff directory 2026-08-16:

    LANE-calibration.lock   12 `status:` lines, 10 `owner_pid:` lines
    LANE-lane1.lock          6 `status:` lines,  5 `owner_pid:` lines
    LANE-latency.lock        1 line carrying ~35 welded stamps

Ruling 071 makes a lock with more than one `status:` line MALFORMED, and a
malformed lock reads as **HELD** (fail-safe, because the alternative resolves an
undefined case toward a second writer on master). So this regex was quietly
fencing lanes out of their own work — and the ruling's own consequence §2 is
that the fix belongs to the MECHANISM, not to lane discipline. Ask a tired lane
to remember to rewrite a header cleanly and it will comply ninety times and
compound it on the ninety-first.

These tests pin both halves: the writer replaces, and the reader refuses to act
on an already-malformed file rather than guessing which line is the truth.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim_lane_lock.py"

CLEAN_LOCK = """# LANE LOCK — test

lane: test
status: RELEASED   # seed stamp.
owner_pid: 1
owner_identity: seed-identity
"""


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


def _status_lines(path: Path) -> list[str]:
    return [l for l in path.read_text().splitlines() if l.startswith("status:")]


@pytest.mark.skipif(not SCRIPT.exists(), reason="claim_lane_lock.py not present")
def test_repeated_claim_release_does_not_compound_the_status_line(tmp_path) -> None:
    """Three full cycles must leave ONE status line carrying ONE stamp.

    The pre-fix code left one line with SEVEN stamps after exactly this loop —
    which is how a real lock reached twelve.
    """
    lock = tmp_path / "LANE-test.lock"
    lock.write_text(CLEAN_LOCK)

    for i in range(3):
        claimed = _run("claim", str(lock), "--queue", f"q{i}", "--identity", f"window-{i}")
        assert claimed.returncode == 0, (
            f"claim {i} did not run (exit {claimed.returncode}). Exit codes other than "
            f"0/1 mean the harness could not check, not that the check failed — "
            f"gotcha #124. stderr:\n{claimed.stderr}"
        )
        released = _run("release", str(lock), "--identity", f"window-{i}")
        assert released.returncode == 0, (
            f"release {i} did not run (exit {released.returncode}). stderr:\n{released.stderr}"
        )

    lines = _status_lines(lock)
    assert len(lines) == 1, (
        f"after 3 claim/release cycles the lock has {len(lines)} `status:` lines:\n"
        + "\n".join(lines)
        + "\n\nRuling 071: more than one makes the lock MALFORMED, which reads as HELD "
        "and fences the owning lane out of its own work."
    )
    stamps = lines[0].count("#")
    assert stamps <= 1, (
        f"the status line accumulated {stamps} stamps:\n  {lines[0]}\n\n"
        "The writer must REPLACE the whole line. Retained history belongs BELOW "
        "the header, never welded into the status line itself."
    )


@pytest.mark.skipif(not SCRIPT.exists(), reason="claim_lane_lock.py not present")
@pytest.mark.parametrize(
    "body,what",
    [
        (
            "# LANE LOCK\n\nstatus: RELEASED   # a.\nstatus: HELD   # b.\nowner_pid: 1\n",
            "two status: lines",
        ),
        (
            "# LANE LOCK\n\nstatus: HELD   # a.\nowner_pid: 1\nowner_pid: 2\n",
            "two owner_pid: lines",
        ),
    ],
)
def test_an_already_malformed_lock_is_refused_and_left_untouched(tmp_path, body, what) -> None:
    """A malformed lock must be refused, and NOT written to.

    Pre-fix, this exact input returned exit 0 and printed `CLAIMED` — it wrote
    into a lock whose own state was ambiguous, which is the single-writer
    hazard ruling 071 exists to close.
    """
    lock = tmp_path / "LANE-bad.lock"
    lock.write_text(body)
    before = lock.read_text()

    result = _run("claim", str(lock), "--queue", "qx", "--identity", "test-window-01")

    assert result.returncode != 0, (
        f"a lock with {what} was CLAIMED (exit 0). Ruling 071: it is MALFORMED and "
        f"must read as HELD.\nstdout: {result.stdout}"
    )
    assert "MALFORMED" in (result.stderr + result.stdout), (
        f"refused, but not as MALFORMED — the reason must name the rule so the "
        f"owner knows to collapse the line.\nstderr: {result.stderr}"
    )
    assert lock.read_text() == before, "a refused claim must not modify the lock"


@pytest.mark.skipif(not SCRIPT.exists(), reason="claim_lane_lock.py not present")
def test_the_status_regex_consumes_the_whole_line() -> None:
    """Pin the regex itself, because the defect is invisible in behaviour once fixed.

    A future edit that reverts `.*$` would restore silent compounding, and the
    behavioural tests above would keep passing for one cycle before a lock grew
    a second line. Cheap to assert directly.
    """
    src = SCRIPT.read_text()
    assert re.search(r'\^status:\\s\*\(\\S\+\)\.\*\$', src), (
        "the status-line regex no longer consumes the whole line. It must be "
        r'`^status:\s*(\S+).*$` — without the trailing `.*$`, re.sub/slice writers '
        "re-append the remainder of the line and the lock compounds on every release."
    )
