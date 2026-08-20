"""Shared reader for `.claude/handoff/RULING-CLAIMS.md`.

EXTRACTED IN UX-P108, and the reason is a Fable ruling rather than tidiness:

    "doctrine-CLAUSE numbers now claim through RULING-CLAIMS.md exactly like
     ruling numbers. A clause banked without a ledger claim is a staging defect
     from here on."

Before that ruling the ledger had exactly one reader, in
`test_product_brain_integrity.py`, and it was written for the RULINGS series.
Giving the clause series its own copy is the defect doctrine clause 5 names —
one predicate, one implementation — and it is a copy that would be free to
disagree about the two things this file actually knows:

  * WHERE the ledger is. The gate runs from linked worktrees, where the file
    lives in the MAIN worktree and nowhere else; that walk is subtle enough
    (a `.git` FILE, a `commondir` pointer, both possibly relative) that a
    second implementation is a second chance to get it wrong.
  * WHEN it is absent LEGITIMATELY. `.gitignore` ignores `.claude/`, so the
    ledger never reaches CI or a fresh clone, and a guard that FAILS there
    instead of skipping turns master red for every contributor who has not
    got one.

Ruling 063 governs everything here, because this file reads SHARED MUTABLE
STATE that six live lanes append to. Its three requirements:

  1. parse for MEANING, not punctuation — a shared prose ledger accretes
     decoration, and a parser that rejects an unambiguous line manufactures
     failures at a steady rate;
  2. a partial parse must BURN, never VANISH — an unreadable field may not
     delete the fact its own line asserts;
  3. NAME THE SNAPSHOT — every verdict, pass or fail, states the path, mtime
     and digest of the state it consumed.

Only (1) and (3) live here; (2) belongs with each series' line parser, because
what a "field" is differs between them.
"""

from __future__ import annotations

import hashlib
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

#: Relative to a worktree root. Untracked by design — see the module docstring.
RULING_CLAIMS_RELPATH = Path(".claude") / "handoff" / "RULING-CLAIMS.md"


class LedgerSnapshotNotice(UserWarning):
    """Emitted once per series per session so a PASSING run also names what it read.

    F5 / ruling 063. A failure message can carry its own provenance, but a pass
    prints nothing, and "the suite was green" was exactly the claim that turned
    out to be unfalsifiable on 2026-08-14. pytest shows its warnings summary by
    default, so this lands in the output of every run that actually consumed the
    ledger — and in no run that did not.
    """


def main_worktree_root(repo_root: Path) -> Path:
    """The main worktree's root, derived from the git common dir.

    In a LINKED worktree, `<root>/.git` is a FILE reading `gitdir: <path>`, and
    that dir holds a `commondir` file pointing back at the main `.git`. The main
    `.git`'s parent is the main worktree root — which is where the untracked
    ledger actually lives. Done with pathlib rather than a `git` subprocess:
    nothing in these gates shells out, and a test that shells out fails
    differently (and more confusingly) when git is absent than when it is.
    """
    dot_git = repo_root / ".git"
    if dot_git.is_dir():
        return repo_root  # already the main worktree
    if not dot_git.is_file():
        return repo_root
    pointer = dot_git.read_text(encoding="utf-8").strip()
    if not pointer.startswith("gitdir:"):
        return repo_root
    worktree_gitdir = Path(pointer.split(":", 1)[1].strip())
    if not worktree_gitdir.is_absolute():
        worktree_gitdir = (repo_root / worktree_gitdir).resolve()
    commondir_file = worktree_gitdir / "commondir"
    if not commondir_file.is_file():
        return repo_root
    common = Path(commondir_file.read_text(encoding="utf-8").strip())
    if not common.is_absolute():
        common = (worktree_gitdir / common).resolve()
    return common.parent


def find_ledger(repo_root: Path):
    """The ledger path, or None. Current tree first, then the main worktree."""
    for root in (repo_root, main_worktree_root(repo_root)):
        candidate = root / RULING_CLAIMS_RELPATH
        if candidate.is_file():
            return candidate
    return None


def skip_message(series: str, artefact: str) -> str:
    """Why an absent ledger is a SKIP and not a failure, stated for one series."""
    return (
        f"LOCAL GATE, NOT A CI GATE — no {RULING_CLAIMS_RELPATH} found in this "
        "tree or in the main worktree. This is expected and correct on CI and "
        "in a fresh clone: .gitignore ignores `.claude/`, so the ledger is "
        "untracked and never reaches a runner or a linked worktree. The gate is "
        "designed to fire at AUTHORING time on the lane's own machine — earlier "
        f"than CI, which is the point. If you are a developer about to add "
        f"{artefact} and you see this skip locally, create the ledger in the "
        "MAIN worktree (~/bainluck/.claude/handoff/RULING-CLAIMS.md) and claim "
        f"your {series} number in it BEFORE writing the file. Do not commit the "
        "ledger to fix this."
    )


def section_lines(text: str, heading_prefix: str) -> list:
    """Lines of one `## <heading_prefix>…` section, bounded by the next `## `.

    The bound is load-bearing rather than defensive. The file carries THREE
    monotonic series — rulings, gotchas and doctrine clauses — whose claim lines
    share a line shape, so an unbounded scan makes gotcha 125 look like a claim
    on ruling 125 and silently blesses a file that has none. `### `
    sub-headings inside a section (the live-collision writeups) do NOT terminate
    it.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## " + heading_prefix):
            start = i + 1
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return lines[start:end]


def snapshot(ledger: Path, heading_prefix: str, detail: str = "") -> str:
    """A one-line identity for the ledger state a verdict was derived from.

    The digest covers the NAMED SECTION ONLY, not the whole file: the other
    series and the prose header change for reasons that cannot affect this
    verdict, and a digest that moves for irrelevant reasons is one nobody
    compares.
    """
    text = ledger.read_text(encoding="utf-8")
    section = "\n".join(section_lines(text, heading_prefix))
    digest = hashlib.sha256(section.encode("utf-8")).hexdigest()[:12]
    mtime = datetime.fromtimestamp(ledger.stat().st_mtime, tz=timezone.utc)
    return (
        f"ledger={ledger} section={heading_prefix!r} digest={digest} "
        f"mtime={mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        + (f" {detail}" if detail else "")
    )


#: One notice per SERIES per session, not one per test. Keyed by series so the
#: rulings gate announcing itself cannot silence the clause gate's own snapshot
#: — two verdicts derived from two different sections need two receipts.
_ANNOUNCED: set = set()


def announce(ledger: Path, series: str, heading_prefix: str, detail: str = "") -> None:
    if series in _ANNOUNCED:
        return
    _ANNOUNCED.add(series)
    warnings.warn(
        f"RULING-CLAIMS {series} ledger consumed by this run — "
        + snapshot(ledger, heading_prefix, detail)
        + ". This gate reads SHARED MUTABLE STATE in the main worktree "
        "(untracked, appended to by every live lane). Ruling 063: a verdict "
        "names the snapshot it came from, so quote this line rather than "
        "'the suite was green'.",
        LedgerSnapshotNotice,
        stacklevel=2,
    )


def require(repo_root: Path, series: str, artefact: str) -> Path:
    """The ledger, or a skip carrying the reason it is legitimately absent."""
    ledger = find_ledger(repo_root)
    if ledger is None:
        pytest.skip(skip_message(series, artefact))
    return ledger
