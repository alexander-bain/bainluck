"""Guard: the cert bus's scratch checkouts are ignored by the repo's own .gitignore.

WHAT THIS PREVENTS
------------------
The cert bus builds scratch trees BESIDE the repo it is grading, at the repo
root, named `cert-scratch-<id>/`. MEASURED on the shared master checkout
`~/bainluck` 2026-09-14: `cert-scratch-593/` held **4,798 untracked files** — a
whole second copy of the repo, including `backend/app/**` and `ios/**` — and
`git check-ignore` returned non-zero for every one of them. Untracked AND
unignored is the combination that bites:

  * a single `git add -A` at the shared tree, the tree the desk pushes master
    from, stages all 4,798 into a launch-week commit;
  * anything enumerating by filesystem or by an unscoped pathspec counts them.
    That has now cost two tools. `native-gates.sh` claimed 226 scratch `*.swift`
    copies as changed files awaiting proof (see
    `test_native_gates_tree_resolution.py`), and the iOS concept-admission
    registry read 585 scratch deciders and reddened a green sha at the desk.

Both tools were repaired at their own end — scoped pathspec, and `git ls-files`
respectively — and those repairs stand on their own; neither is weakened by this
line and neither is a substitute for it, because the next tool has not been
written yet. This is the root: make the family ignored once.

WHY THE OBVIOUS FIX WOULD HAVE MISSED IT
----------------------------------------
The natural reading of the registry failure was ".gitignore:127 already says
`.claude/`, and a filesystem walk has never heard of .gitignore" — which points
at teaching the walk to read .gitignore. That fix would have stayed RED on
`cert-scratch-593/`, because .gitignore did not cover it. The gap was in the
ignore file, not only in the readers of it.

WHY THIS IS NOT VACUOUS
-----------------------
`test_a_tracked_path_is_not_ignored` is the control: a `.gitignore` that ignored
everything would satisfy the positive assertion alone. And git's answer is read
as a VALUE — `check-ignore` says 0 for ignored, 1 for not ignored, anything else
is git failing to answer, which raises rather than passing (gotcha #54: a gate
that cannot run must never read as a gate that passed).
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A scratch id that is deliberately NOT one that has existed, so this asserts the
# family pattern and not a single hard-coded directory name.
SCRATCH_PATH = "cert-scratch-999/backend/app/main.py"


def is_ignored(path: str) -> bool:
    """True if the repo's .gitignore ignores `path`. Raises if git cannot answer."""
    p = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if p.returncode not in (0, 1):
        raise AssertionError(
            f"git check-ignore could not answer for {path!r} "
            f"(exit {p.returncode}): {p.stderr.strip()}"
        )
    return p.returncode == 0


def test_cert_scratch_checkouts_are_ignored():
    assert is_ignored(SCRATCH_PATH), (
        f"{SCRATCH_PATH} is not ignored. A cert-bus scratch checkout at the repo "
        "root is a second copy of the repo; unignored, one `git add -A` in the "
        "shared master tree stages thousands of files."
    )


def test_a_tracked_path_is_not_ignored():
    """The control. Without it, `.gitignore` containing `*` would pass above."""
    assert not is_ignored("backend/app/main.py")


def test_the_scratch_pattern_matches_no_tracked_file():
    """An over-broad ignore pattern is its own silent hazard.

    A tracked file that .gitignore also matches keeps being tracked, so nothing
    visibly breaks — until someone re-adds it, or a tool asks git what belongs to
    the repo and believes the answer.

    Scoped deliberately to the `cert-scratch-*` family rather than asserting the
    repo-wide invariant: MEASURED 2026-09-14, 228 tracked files are already
    matched by `.gitignore` (`.claude/commands/health.md`, `Manus/**`, …). Those
    are the deliberate "ignore the directory, force-add the few files that
    belong" idiom, not defects — so a repo-wide assertion here would be red on
    arrival for reasons that have nothing to do with the scratch checkouts. This
    guards the blast radius of the line this file exists for.
    """
    tracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert tracked.returncode == 0, tracked.stderr
    # `--no-index` is load-bearing and is the whole reason this test is not
    # vacuous: without it `git check-ignore` SKIPS every path that is in the
    # index, so a sweep of `ls-files` output can never report an offender and
    # passes against a `.gitignore` containing `*`. Measured here 2026-09-14 by
    # appending `*main.py` — the sweep stayed green until this flag was added.
    check = subprocess.run(
        ["git", "-C", str(REPO), "check-ignore", "--stdin", "-z", "--no-index"],
        input=tracked.stdout,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check.returncode not in (0, 1):
        raise AssertionError(
            f"git check-ignore could not answer (exit {check.returncode}): "
            f"{check.stderr.strip()}"
        )
    offenders = [
        p for p in check.stdout.split("\0") if p and p.startswith("cert-scratch-")
    ]
    assert not offenders, (
        f"{len(offenders)} TRACKED file(s) are matched by the cert-scratch "
        f"ignore pattern: {offenders[:10]}"
    )
