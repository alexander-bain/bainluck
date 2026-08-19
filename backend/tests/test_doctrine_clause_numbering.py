"""`docs/doctrine.md` has clause numbers and, until now, nothing checking them.

FOUR RENUMBERS IN TWO CYCLES, ONE CLAUSE. The UX lane's "a line in a spec needs
a fixture ON the line" was banked as clause 6, renumbered to 10 when master grew
clauses 6-9, renumbered to 11 on-branch when master minted its own 10, and moved
again to 12 inside the Integrator's merge when latency-64 also minted an 11.
Then this cycle's new clause, banked as 12 against a master that had 11 as its
highest, landed on a master whose 12 was the UX clause from the merge before —
and `git` **auto-merged it cleanly**, because two `### 12.` headings in different
parts of a file are not a textual conflict.

That is the whole problem in one sentence: **the failure mode is a clean merge.**
The rulings series has a claim guard (`RULING-CLAIMS.md`) and an integrity test
that checks the index against the directory in both directions. The doctrine
series had neither, so its only protection was that somebody would notice — and
on the fifth occasion, inside an automated merge, nobody was reading.

These tests are cheap and they run wherever the ruling tests run.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCTRINE = Path(__file__).resolve().parents[2] / "docs" / "doctrine.md"

#: `### 12. Two measurements never computed side by side ...`
CLAUSE_RE = re.compile(r"^### (?P<num>\d+)\. (?P<title>.+)$", re.MULTILINE)


def _clauses() -> list[tuple[int, str]]:
    text = DOCTRINE.read_text()
    return [(int(m.group("num")), m.group("title")) for m in CLAUSE_RE.finditer(text)]


def test_doctrine_file_exists_and_has_clauses():
    assert DOCTRINE.exists(), f"docs/doctrine.md is missing at {DOCTRINE}"
    clauses = _clauses()
    assert clauses, (
        "no `### N. Title` clause headings found in docs/doctrine.md. Either the "
        "file lost its clauses or the heading shape changed — if the shape "
        "changed, this regex has to change with it, or every check below "
        "silently passes over an empty list."
    )


def test_no_two_clauses_share_a_number():
    clauses = _clauses()
    seen: dict[int, str] = {}
    duplicates = []
    for num, title in clauses:
        if num in seen:
            duplicates.append((num, seen[num], title))
        seen[num] = title
    assert not duplicates, (
        "docs/doctrine.md has duplicate clause numbers: "
        + "; ".join(f"### {n}. is BOTH '{a}' AND '{b}'" for n, a, b in duplicates)
        + ". This is what a clean merge looks like when two lanes both bank the "
        "next free number — git sees two headings in different parts of a file "
        "and has nothing to conflict on. Renumber YOUR clause upward (the later "
        "lane moves its own, same rule as docs/rulings/README.md) and claim the "
        "number in .claude/handoff/RULING-CLAIMS.md first."
    )


def test_clause_numbers_ascend_without_gaps():
    numbers = [n for n, _ in _clauses()]
    assert numbers == sorted(numbers), (
        f"docs/doctrine.md clause numbers are out of order: {numbers}. Keep both "
        "sides of a merge and sort by number — the same mechanical resolution "
        "the RULINGS INDEX uses."
    )
    expected = list(range(1, len(numbers) + 1))
    assert numbers == expected, (
        f"docs/doctrine.md clause numbers are {numbers}, expected {expected}. A "
        "gap means a clause was deleted or a number was skipped; doctrine is "
        "never retired by deletion, for the same reason rulings are not."
    )


def test_every_clause_has_a_body():
    """A heading with nothing under it is a clause that was lost in a merge."""
    text = DOCTRINE.read_text()
    parts = CLAUSE_RE.split(text)
    # split() with 2 groups yields: [pre, num, title, body, num, title, body, ...]
    bodies = parts[3::3]
    numbers = parts[1::3]
    empty = [n for n, b in zip(numbers, bodies) if len(b.strip()) < 40]
    assert not empty, (
        f"docs/doctrine.md clauses {empty} have no body (under 40 characters). "
        "A heading whose paragraph was dropped in a conflict resolution reads "
        "exactly like a clause nobody bothered to write."
    )
