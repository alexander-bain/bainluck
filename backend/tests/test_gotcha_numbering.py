"""`docs/gotchas-reference.md` numbers must be unique — UX-P070.

WHY THIS EXISTS. On 2026-08-13 two lanes banked a gotcha numbered **126**:

* `LAT-P043` — "A kill switch whose OFF position is 'the key is absent' fails OPEN"
  (merged first, so it is the one on `master`).
* `UX-P069` — "An absence check must first prove the resource EXISTS" (unmerged).

`.claude/handoff/RULING-CLAIMS.md` exists precisely to stop this, and it worked exactly
as designed: UX-P069 fetched, checked master's highest (125), and swept every remote
branch before claiming. **It lost anyway, because a ledger binds only the lanes that
read it** — and a lane that has not yet written its entry is invisible to a branch sweep
as well. There is no read-side fix available to a careful lane.

What made it dangerous is that **nothing would have caught it**. The append region is
conflict-prone, so the standing resolution is KEEP BOTH (ruling 037) — which here would
have silently produced two entries numbered 126, plus two live cross-references
(``See gotcha #126.``) pointing ambiguously at either one. CI asserts the rulings index
in both directions; the gotcha ledger had no equivalent.

DELIBERATELY NOT CONTIGUITY. This asserts uniqueness only. A program branch legitimately
holds a *gap* — this branch has 123, 124, 127, 128 because master's 125 and 126 arrive at
merge — so a contiguity assertion would be red on every unmerged branch and green only
after integration, which is the worst possible time for a check to change its mind.
"""

import re
from collections import Counter
from pathlib import Path

import pytest

GOTCHAS = Path(__file__).resolve().parents[2] / "docs" / "gotchas-reference.md"

# A banked gotcha is a bolded, numbered list item at the start of a line.
_ENTRY_RE = re.compile(r"^(\d{1,4})\.\s+\*\*", re.M)


def _numbers() -> list[int]:
    return [int(m) for m in _ENTRY_RE.findall(GOTCHAS.read_text(encoding="utf-8"))]


def test_the_reference_file_is_present_and_parses():
    """A positive anchor, so the assertions below cannot pass vacuously.

    Gotcha #128's own lesson, applied to its own file: a negative assertion ("no
    duplicates") over an empty or unparsed list passes for the wrong reason.
    """
    assert GOTCHAS.is_file(), GOTCHAS
    nums = _numbers()
    assert len(nums) > 50, f"only parsed {len(nums)} entries — the format changed"


def test_gotcha_numbers_are_unique():
    dupes = {n: c for n, c in Counter(_numbers()).items() if c > 1}
    assert not dupes, (
        f"duplicate gotcha number(s): {sorted(dupes)}. Two lanes banked the same number. "
        "Resolution (RULING-CLAIMS.md): whichever entry is already on master keeps it; the "
        "unmerged claimant renumbers and updates every `gotcha #N` cross-reference."
    )


@pytest.mark.parametrize("stale", [126])
def test_no_cross_reference_points_at_a_renumbered_gotcha(stale):
    """The renumber is only done when the references move with it.

    UX-P070 moved UX-P069's 126 to 127 and had to fix two live citations. A renumber that
    leaves a `See gotcha #126.` behind is worse than the collision: the number now resolves,
    confidently, to somebody else's entry.
    """
    root = Path(__file__).resolve().parents[2]
    hits = []
    for path in list(root.glob("backend/**/*.py")) + list(root.glob("docs/**/*.md")):
        # The ledger and this guard both cite the old number ON PURPOSE — they are the
        # record OF the renumber. (Caught on this test's first run, by itself.)
        if path.name in ("gotchas-reference.md", Path(__file__).name):
            continue
        if "node_modules" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"gotcha #{stale}\b", text):
            hits.append(str(path.relative_to(root)))
    assert not hits, f"stale citation of renumbered gotcha #{stale} in: {hits}"
