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

from tests import ruling_ledger

DOCTRINE = Path(__file__).resolve().parents[2] / "docs" / "doctrine.md"

#: `### 12. Two measurements never computed side by side ...`
CLAUSE_RE = re.compile(r"^### (?P<num>\d+)\. (?P<title>.+)$", re.MULTILINE)

#: A claim line in the ledger's `## DOCTRINE CLAUSES` section:
#: `14   claimed-by ux   2026-08-19  — claimed  — **Two measurements ...**`
#:
#: ONE OR TWO DIGITS, which is what keeps this parser and the RULINGS one from
#: reading each other's lines even if a section boundary ever slipped: a ruling
#: claim opens with exactly three digits, a clause claim with one or two.
CLAUSE_CLAIM_RE = re.compile(r"^(?P<num>\d{1,2})\s+")

#: The clause series gained a ledger section on 2026-08-19 (UX-P103), and this
#: gate on 2026-08-20 (UX-P108, Fable's ruling). Clauses 1-13 were banked before
#: either existed and cannot be retro-claimed by the lanes that wrote them —
#: several of those lanes are long finished.
#:
#: A TRACKED CONSTANT rather than "whatever the ledger happens to start at":
#: deriving the floor from the ledger would make the gate vacuous the moment the
#: ledger lost a row, which is the same self-defeating shape as a baseline
#: computed from the thing it is meant to constrain.
CLAUSE_CLAIM_FLOOR = 14


def _clauses() -> list[tuple[int, str]]:
    text = DOCTRINE.read_text()
    return [(int(m.group("num")), m.group("title")) for m in CLAUSE_RE.finditer(text)]


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, drop markdown emphasis and trailing stop.

    Parse for MEANING, not punctuation (ruling 063). The ledger's titles are
    written inside `**bold**` and the doctrine headings are not; a comparison
    that treated an asterisk as significant would manufacture a failure on every
    correctly-claimed clause.
    """
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", "")).strip().lower().rstrip(".")


def _clause_claims() -> tuple[list, list]:
    """(claims, dropped) from the ledger's DOCTRINE CLAUSES section.

    `dropped` is returned rather than swallowed so a test can assert it is
    empty: ruling 063's "a partial parse must BURN, never VANISH". A claim-shaped
    line this parser cannot fully read still burns its number — the number is the
    fact the ledger exists to record, and no failure to read the prose around it
    may delete that fact.
    """
    ledger = ruling_ledger.require(
        DOCTRINE.parents[1], "doctrine clause", "a `### N.` clause in docs/doctrine.md"
    )
    ruling_ledger.announce(ledger, "DOCTRINE CLAUSES", "DOCTRINE CLAUSES")
    claims, dropped = [], []
    for line in ruling_ledger.section_lines(
        ledger.read_text(encoding="utf-8"), "DOCTRINE CLAUSES"
    ):
        m = CLAUSE_CLAIM_RE.match(line)
        if not m:
            continue
        try:
            claims.append({"num": int(m.group("num")), "raw": line})
        except ValueError:  # pragma: no cover — unreachable by the regex
            dropped.append(line)
    return claims, dropped


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


# ---------------------------------------------------------------------------
# THE LEDGER CLAIM — Fable ruling, 2026-08-20, banked by UX-P108
# ---------------------------------------------------------------------------
#
#   "doctrine-CLAUSE numbers now claim through RULING-CLAIMS.md exactly like
#    ruling numbers. A clause banked without a ledger claim is a staging defect
#    from here on."
#
# The tests above catch a COLLISION once both clauses are in one tree. They
# cannot catch the thing that actually costs cycles: two live lanes each about
# to write the same next number, neither able to see the other, because the
# collision does not exist yet. That is what the ledger is for, and until this
# ruling the clause series had a section in it that nothing checked.
#
# Named failures behind the ruling: one UX clause wore FIVE numbers in two
# cycles (6 -> 10 -> 11 -> 12 -> 13 -> 14), and three consecutive UX windows
# skipped a payable clause rather than risk a sixth renumber.
#
# ⚠️ THIS IS A LOCAL GATE. `.gitignore` ignores `.claude/`, so the ledger never
# reaches CI — `ruling_ledger.require` SKIPS there, by design and loudly. It
# fires at authoring time on the lane's own machine, which is earlier than CI
# and is the only moment at which the information is still actionable.


def test_clause_claim_parser_is_not_vacuous():
    """Runs first, for the same reason the rulings gate's does.

    A parser that yields zero claims blesses everything: zero claims means zero
    UNCLAIMED clauses too, and the gate below would pass over a tree in which
    nothing was ever claimed. So assert the ledger yields claims AT ALL, and
    that no claim-shaped line was silently discarded on the way.
    """
    claims, dropped = _clause_claims()
    assert not dropped, (
        f"claim-shaped lines in the DOCTRINE CLAUSES section were dropped: "
        f"{dropped}. Ruling 063: a partial parse must BURN the number, never "
        "make it vanish — a line this parser cannot read is still a claim."
    )
    assert claims, (
        "the ledger's `## DOCTRINE CLAUSES` section yielded ZERO claims. Either "
        "the heading was renamed (this parser keys on `## DOCTRINE CLAUSES`) or "
        "the line format changed. Until it yields claims, the gate below is "
        "blessing every clause in the tree."
    )


def test_every_clause_above_the_floor_is_claimed_in_the_ledger():
    """The ruling, enforced.

    One direction only, deliberately. A clause CLAIMED but not yet written is
    the normal and desirable state — that is a lane reserving a number ahead of
    banking it, which is the whole mechanism. A clause WRITTEN but not claimed
    is the staging defect.
    """
    claimed = {c["num"] for c in _clause_claims()[0]}
    unclaimed = [
        (n, t) for n, t in _clauses() if n >= CLAUSE_CLAIM_FLOOR and n not in claimed
    ]
    assert not unclaimed, (
        "docs/doctrine.md clauses written WITHOUT a ledger claim: "
        + "; ".join(f"### {n}. {t}" for n, t in unclaimed)
        + f".\n\nFable ruling 2026-08-20: a clause banked without a claim in "
        f"{ruling_ledger.RULING_CLAIMS_RELPATH} is a staging defect. Claim the "
        "number in the `## DOCTRINE CLAUSES` section of the ledger in the MAIN "
        "worktree BEFORE writing the heading — the number is allocated by the "
        "claim, not by the file (ruling 069). Do not commit the ledger."
    )
    # Non-vacuity: the floor must not have drifted above every clause in the
    # tree, which would make the assertion above trivially true.
    assert [n for n, _ in _clauses() if n >= CLAUSE_CLAIM_FLOOR], (
        f"no clause in docs/doctrine.md is at or above CLAUSE_CLAIM_FLOOR "
        f"({CLAUSE_CLAIM_FLOOR}), so this gate checked nothing."
    )


def test_a_claim_is_for_ITS_clause_and_not_merely_on_the_number():
    """A claim-jump: the right number, somebody else's clause.

    The rulings gate learned this one the expensive way — three lanes each held
    a claim on 053/054/055 for three entirely different subjects, and every
    number-only check passed. Matching the TITLE is what separates "this clause
    is claimed" from "this number is taken by something".

    Titles are compared normalised (see `_normalise`), because the ledger writes
    them bolded and the heading does not; verified against the three live rows
    (14, 15, 16) at the time this gate was written.
    """
    by_num = {c["num"]: c["raw"] for c in _clause_claims()[0]}
    mismatched = []
    for num, title in _clauses():
        if num < CLAUSE_CLAIM_FLOOR or num not in by_num:
            continue
        if _normalise(title) not in _normalise(by_num[num]):
            mismatched.append((num, title))
    assert not mismatched, (
        "ledger claims whose title does not match the clause they are supposed "
        "to cover: "
        + "; ".join(f"### {n}. {t}" for n, t in mismatched)
        + ". Either the clause was renamed after it was claimed (update the "
        "ledger row) or this number is claimed by a DIFFERENT lane's clause, "
        "which is a collision — the later claim renumbers (ruling 055)."
    )
