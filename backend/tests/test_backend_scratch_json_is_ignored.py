"""Guard: measurement scratch dropped directly into `backend/` is ignored.

WHAT THIS PREVENTS
------------------
A probe run from a `cd backend` shell writes its JSON beside the code. Nothing in
`.gitignore` caught that, so the file sat untracked-and-unignored in a lane's
worktree and rode the next offer. MEASURED 2026-09-17: the desk bounced live/348
at 09:05Z for exactly this — four scratch json files under a merge offer that
said three files — live/349 hit it again on the re-offer, and int409 recorded it
as "still true and still unowned". A bounce costs the desk a merge cycle and the
lane a session, for a file nobody meant to commit.

This is the same family as `test_scratch_checkouts_are_ignored.py`, one directory
shallower: untracked AND unignored is the combination that bites.

WHY THE PATTERN IS NON-RECURSIVE
--------------------------------
`/backend/*.json` is anchored by its slash and `*` does not cross one, so it
reaches files sitting DIRECTLY in `backend/` and nothing below. That matters
because 253 tracked json files live in this tree and every one of them is at
least one directory deeper — `backend/tests/evals/fixtures` (128),
`backend/tests/fixtures` (68), `backend/scripts/evals` (43), `backend/app/data`
(8), `backend/scripts` (3), `backend/data/tournament_registers` (2). A recursive
`backend/**/*.json` would have swallowed all 253.

WHY THIS IS NOT VACUOUS
-----------------------
Three controls, because a positive assertion alone is satisfied by a `.gitignore`
containing `*`: a nested fixture must stay VISIBLE, a non-json file at the same
depth must stay VISIBLE, and no tracked file may be matched by the new pattern.
Git's answer is read as a VALUE — 0 ignored, 1 not ignored, anything else is git
failing to answer and raises rather than passing (gotcha #54).

`--no-index` IS LOAD-BEARING and is copied here deliberately from the sibling
guard, which measured the trap: without it `git check-ignore` SKIPS every path in
the index, so a sweep over `ls-files` can never report an offender and passes
against a `.gitignore` containing `*`. The first cut of this file's blast-radius
check was written without the flag and reported a clean zero for that reason.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A name that has deliberately never existed, so this asserts the FAMILY and not
# one scratch file someone already deleted.
SCRATCH_PATH = "backend/.probe-scratch-999.json"

# The pattern's exact reach, as git resolves it: one path segment after
# `backend/`, ending in `.json`.
DIRECT_BACKEND_JSON = re.compile(r"^backend/[^/]+\.json$")


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


def test_scratch_json_directly_in_backend_is_ignored():
    assert is_ignored(SCRATCH_PATH), (
        f"{SCRATCH_PATH} is not ignored. Measurement scratch written by a probe "
        "run from `cd backend` then rides the next merge offer — which is what "
        "bounced live/348 on 2026-09-17."
    )


def test_a_nested_fixture_is_still_visible():
    """The control that decides whether the pattern is safe at all.

    Every legitimate json in this tree is nested. If this goes red, the pattern
    became recursive and 253 tracked fixtures just became invisible to `git add`.
    """
    assert not is_ignored("backend/app/data/polymarket_blurbs.json")
    assert not is_ignored("backend/tests/fixtures/__does_not_exist__.json")


def test_a_non_json_file_at_the_same_depth_is_still_visible():
    """The pattern is scoped by extension as well as by depth."""
    assert not is_ignored("backend/requirements.txt")
    assert not is_ignored("backend/run_kalshi_ws.py")


def test_the_pattern_matches_no_tracked_file():
    """An over-broad ignore pattern is its own silent hazard.

    A tracked file that `.gitignore` also matches keeps being tracked, so nothing
    visibly breaks — until someone re-adds it, or a tool asks git what belongs to
    the repo and believes the answer.

    Scoped to this pattern's own reach rather than asserting the repo-wide
    invariant: MEASURED 2026-09-17, 227 tracked files are already matched by
    `.gitignore` (`Manus/**`, `.claude/**`, …). Those are the deliberate "ignore
    the directory, force-add the few that belong" idiom, not defects, so a
    repo-wide assertion would be red on arrival for unrelated reasons.
    """
    tracked = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert tracked.returncode == 0, tracked.stderr
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
        p for p in check.stdout.split("\0") if p and DIRECT_BACKEND_JSON.match(p)
    ]
    assert not offenders, (
        f"{len(offenders)} TRACKED file(s) are matched by the /backend/*.json "
        f"ignore pattern: {offenders[:10]}"
    )
