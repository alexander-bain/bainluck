"""CI guard: docs/PRODUCT-BRAIN.md must retain its authoritative ruling sections.

PRODUCT-BRAIN.md is the standing JUDGMENT layer. Twice it has regressed: a
wholesale rewrite dropped ruling sections that were only ever restored in the
working tree and never banked in git, so the rewrite won by default. This test
turns master RED the instant any of the CI-guarded ruling markers disappears,
making an overwrite impossible to merge silently.

Append-only guidance alone failed twice. This is the enforcement.

If you are INTENTIONALLY removing/renaming a ruling section, that requires an
explicit Alex ruling — update the marker list below IN THE SAME CHANGE and say
so in the commit message. Do not delete a marker to make the test pass.
"""

import re
from pathlib import Path

import pytest

PRODUCT_BRAIN = (
    Path(__file__).resolve().parents[2] / "docs" / "PRODUCT-BRAIN.md"
)

# The four markers Alex named explicitly (2026-08-03). Each anchors one
# CI-guarded ruling section carrying "DO NOT REMOVE (CI-guarded)" in the doc.
REQUIRED_MARKERS = [
    "morning MC round",
    "second MC round",
    "PRODUCT-FIRST RESET",
    "PROGRAM LAYER",
]

# The forensic finding (2026-08-03): nothing SCRIPTS the clobbering. It is a
# staging agent doing a wholesale "consolidation" rewrite that silently drops
# ruling sections. Pinning only the four markers above would let a rewrite drop
# ANY OTHER load-bearing section undetected. So we also pin every standing
# ruling / judgment section header. Dash-free substrings are used where possible
# so an em-dash encoding difference cannot cause a false failure.
STRUCTURAL_MARKERS = [
    "THE ONE RULE ABOVE ALL",
    "STANDING RULINGS",
    "SIX RELIABILITY FAILURE CLASSES",
    "THE LANES & THE PROTECTED SPLIT",
    "STAGING RULES v3",
    "2026-07-27 (evening batch",
    "2026-07-28 late MC round",
]

# UX-P010 (2026-08-07). The marker lists above stop a WHOLESALE rewrite, but they
# named nothing after 2026-07-28, so every ruling from the entire program era was
# unguarded. That gap is not theoretical: on 2026-08-07 the ux worktree and the
# master worktree had BOTH accreted two rulings the other lacked (this tree:
# mover headlines + post-deploy rail invocation; master, unpushed: per-WINDOW
# lane ownership + the Invariant-2 amendment). Four load-bearing rulings, none
# of them guarded, one merge away from being dropped silently by whichever side
# won a conflict — which is precisely the failure mode this file exists for, and
# the same one the doc header records happening TWICE.
PROGRAM_ERA_MARKERS = [
    "THE PROGRAM LAYER",
    "handoff inbox",
    "Board-visible completion",
    "Integration ordering is the Integrator",
    "CONTINUOUS LANES v1",
    "Mover headlines are legitimate",
    "A rail is not shipped until it has been invoked post-deploy",
    "THE MASTER WORKTREE IS INTEGRATOR-ONLY",
    "THE LOCK IS PER-WORKTREE",
    "SUCCESSOR BRANCHES ARE THE DOCUMENTED DEFAULT",
]

# LAT-P008b (2026-08-08): the two rulings the note below waited on are now on
# master and verified present in the doc from this branch, so they are guarded
# rather than deferred. The ⚠️ INTEGRATOR hand-off note they carried is
# discharged and removed — an instruction that has been carried out is worse
# than useless left in place, because the next reader re-does it.
DEFERRED_NOW_GUARDED = [
    "LANE OWNERSHIP IS PER-WINDOW",
    "INVARIANT 2 AMENDED",
]

# LAT-P008b (2026-08-08). Alex rulings banked from the latency window. The
# synthetic-traffic ruling is the load-bearing one: it kills the PERMANENT
# BLOCKER pattern, where an acceptance criterion can only be satisfied by a
# condition the product does not have yet (users, a season, a vendor). #1500 sat
# unclosable on exactly that for several cycles while being the sole stated
# blocker on #1459.
RULINGS_2026_08_08 = [
    "SYNTHETIC TRAFFIC IS REAL TRAFFIC",
    "PERMANENT BLOCKER",
    "THREE-WINNER REPAIR",
]

# CAL-P015 (2026-08-08). The re-issued batch. Alex ruled these, they were lost
# with the window that heard them, and he had to issue them a THIRD time. That
# is this file's failure mode arriving from a new direction: not a consolidation
# rewrite dropping a banked section, but a ruling that never got banked at all,
# so there was nothing for the guard to protect. Pinning them the moment they
# land is what makes the next re-ask unnecessary.
RULINGS_2026_08_08_REISSUED = [
    "re-issued batch",
    "PROP-THRESHOLD BANDS",
    "COVERAGE DENOMINATOR: PUBLISH BOTH",
    "RETIRE OR REWRITE THE CAL-P010 BRANCH",
    "PREDECESSOR'S QUEUE-ID",
    "FRESH-WINDOW MEASUREMENT PASS",
]

# CAL-P021 (2026-08-09). The exit exam. Guarded harder than a normal ruling for
# a structural reason: this one is a GATE, so the incentive to quietly soften it
# is real in a way it is not for a ruling that merely describes how to work. The
# seven items are pinned individually, so dropping one — the cheapest possible
# way to pass — fails CI rather than passing the exam.
RULING_EXIT_EXAM = [
    "THE CALIBRATION EXIT EXAM",
    "volume-proven trading",
    "matched-bucket comparison",
    # Substrings chosen to sit inside ONE line of the doc: the ruling text is
    # wrapped, so "no massive-error category left unexplained" spans a newline
    # and would never match however intact the ruling is — a guard that can
    # only fail is worse than no guard.
    "massive-error category",
    "per-source panels",
    "native app's calibration surface",
    "actually firing",
    "786K recoverable cohort",
]

# CAL-P022 (2026-08-09). The three exit-exam unblocks, taken in one sitting.
# Banked the same window they were heard in, which is the whole lesson of the
# 2026-08-08 re-issued batch: a ruling that dies with its window costs Alex a
# third telling. Ruling 9 in particular is pinned by its LADDER, because the
# cheap way to get it wrong is to keep tier 1 and quietly drop tier 3 — which
# would republish "unknown" as "untraded", the exact dishonesty it forbids.
# Ruling 001 (2026-08-09). The index section itself must be pinned, or a
# consolidation rewrite could drop the index while leaving docs/rulings/ intact
# — which would pass every per-file check below (they iterate the directory and
# look for lines in a section that no longer exists... which does fail, but with
# a confusing "no index line" error per file). Pinning the header gives the
# clear failure first.
RULINGS_INDEX_MARKERS = [
    "RULINGS INDEX",
    "docs/rulings/",
]

RULINGS_2026_08_09 = [
    "the three exit-exam unblocks",
    "RULING 9 RESOLVED",
    "movement_inferred",
    "Never collapsed into \"untraded\"",
    "N is MEASURED, not chosen",
    "BOUNDED PILOT FIRST",
    "PAUSE; specimens first",
]

ALL_MARKERS = (
    REQUIRED_MARKERS
    + STRUCTURAL_MARKERS
    + PROGRAM_ERA_MARKERS
    + DEFERRED_NOW_GUARDED
    + RULINGS_2026_08_08
    + RULINGS_2026_08_08_REISSUED
    + RULING_EXIT_EXAM
    + RULINGS_2026_08_09
    + RULINGS_INDEX_MARKERS
)

#: The exam is a separate FILE, so the marker guard above cannot protect it —
#: deleting `docs/CALIBRATION-EXIT-EXAM.md` would leave PRODUCT-BRAIN's ruling
#: intact and pointing at nothing. Guarded by its own test below.
EXIT_EXAM = PRODUCT_BRAIN.parent / "CALIBRATION-EXIT-EXAM.md"

#: One per exam item. A scoreboard that loses a row is how a seven-item gate
#: silently becomes a six-item one.
EXIT_EXAM_ITEMS = [
    "Ruling 9 shipped",
    "matched-bucket comparison",
    "Cricket and entertainment",
    "per-source panels",
    "consistent with web",
    "proven by drill",
    "786K recoverable",
]


def _read_product_brain() -> str:
    assert PRODUCT_BRAIN.exists(), (
        f"docs/PRODUCT-BRAIN.md is missing at {PRODUCT_BRAIN}. This file is the "
        "authoritative judgment layer and must never be deleted."
    )
    return PRODUCT_BRAIN.read_text(encoding="utf-8")


@pytest.mark.parametrize("marker", ALL_MARKERS)
def test_product_brain_retains_ruling_marker(marker: str) -> None:
    text = _read_product_brain()
    assert marker in text, (
        f"docs/PRODUCT-BRAIN.md is missing the CI-guarded ruling marker "
        f"{marker!r}. This ruling section has regressed before. Restore it from "
        f"git history (commit 47ece922 banked the authoritative version) rather "
        f"than regenerating the file wholesale. If this removal is intentional, "
        f"it needs an explicit Alex ruling and this marker list must be updated "
        f"in the same change."
    )


def test_product_brain_all_markers_present_together() -> None:
    # Guards against a partial rewrite that keeps some sections but drops others.
    text = _read_product_brain()
    missing = [m for m in ALL_MARKERS if m not in text]
    assert not missing, (
        f"docs/PRODUCT-BRAIN.md lost {len(missing)} authoritative ruling "
        f"section(s): {missing}. See git history commit 47ece922."
    )


def test_product_brain_is_not_a_wholesale_regeneration() -> None:
    # The clobbering is a "consolidation" rewrite. A healthy doc keeps its full
    # accreted ruling history; a wholesale regeneration collapses it. If the doc
    # ever shrinks below the banked baseline's section count, treat it as a
    # regression regardless of which specific markers survived.
    text = _read_product_brain()
    ruling_sections = [
        line for line in text.splitlines() if line.startswith("## ")
    ]
    # Baseline banked in commit 47ece922 had 16 "## " sections. Allow growth
    # (new rulings append), never silent collapse. Raised to 31 by LAT-P008b:
    # a floor that never tracks the real count stops guarding the sections added
    # since it was written — the same gap PROGRAM_ERA_MARKERS was created to fix.
    # Raised to 36 by CAL-P015 (master carried 35; the re-issued batch adds one).
    assert len(ruling_sections) >= 36, (
        f"docs/PRODUCT-BRAIN.md has only {len(ruling_sections)} '## ' sections; "
        f"the guarded floor is 36. A wholesale "
        f"'consolidation' rewrite has collapsed the accreted ruling history. "
        f"Restore from git and append the new ruling instead of regenerating."
    )


# ---------------------------------------------------------------------------
# CAL-P021 — the exit exam is a gate, and a gate needs its own guard.
# ---------------------------------------------------------------------------
def test_exit_exam_document_exists() -> None:
    assert EXIT_EXAM.exists(), (
        f"docs/CALIBRATION-EXIT-EXAM.md is missing at {EXIT_EXAM}. Alex's "
        "2026-08-09 ruling makes this document the rotation trigger for the "
        "calibration slot: the slot rotates when this file shows all seven "
        "items green with linked proof. Deleting it does not pass the exam."
    )


@pytest.mark.parametrize("item", EXIT_EXAM_ITEMS)
def test_exit_exam_retains_every_item(item: str) -> None:
    text = EXIT_EXAM.read_text(encoding="utf-8")
    assert item in text, (
        f"exam item {item!r} is missing from docs/CALIBRATION-EXIT-EXAM.md. "
        "All seven items are required together — dropping one is the cheapest "
        "way to 'pass', so it fails here instead."
    )


def test_exit_exam_keeps_a_scoreboard_row_per_item() -> None:
    """Seven items, seven scoreboard rows.

    The scoreboard is what Alex reads first; an item that survives in prose but
    vanishes from the table is invisible in the one sitting the ruling grants.
    """
    text = EXIT_EXAM.read_text(encoding="utf-8")
    # Anchored to the scoreboard's own row shape (`| N | `). A looser test
    # also counts the bucket table and the evidence log, which is how it first
    # reported 20 rows for a 7-row table.
    numbered = re.findall(r"^\| [1-7] \| ", text, re.MULTILINE)
    assert len(numbered) == 7, (
        f"the exam scoreboard has {len(numbered)} numbered rows, expected 7."
    )


def test_exit_exam_records_the_ruling_nine_inference_as_an_inference() -> None:
    """The one place this lane read a decision INTO Alex's wording.

    Item 1 requires "ruling 9 shipped"; RULINGS-NEEDED.md item 9 was still open
    with options A and B. A was inferred. That inference must stay visible and
    labelled — if it silently hardens into a quoted ruling, a wrong turn becomes
    unauditable, and the correction costs a cycle instead of a line.
    """
    text = EXIT_EXAM.read_text(encoding="utf-8")
    assert "inference" in text.lower()
    assert "Option A" in text


# ---------------------------------------------------------------------------
# Ruling 001 (2026-08-09) — one file per ruling, and an index that cannot drift.
#
# The named failure this structure fixes: PRODUCT-BRAIN was append-only into ONE
# shared region, so two lanes banking a ruling the same day always conflicted,
# and the only correct resolution is keep-both. A commit merged through a
# conflict resolution has a DIFFERENT PATCH-ID FOREVER, so `git cherry` reports
# it `+` (not upstream) on every future cycle. INT-027 hit three of these in one
# cycle (b0ad31d7, 8e046686, aef2f57c) and MINTED A FOURTH resolving CAL-P021 —
# the class grew every docs-banking cycle. Separate files share no region, so
# they cannot conflict, so no patch-id is detached.
#
# These tests guard the one thing the split can still get wrong: the index and
# the directory drifting apart. Checked in BOTH directions, deliberately. A
# one-directional check (every line has a file) would let a ruling be filed and
# never indexed — invisible to every reader of PRODUCT-BRAIN, which is the only
# place anyone looks.
# ---------------------------------------------------------------------------

RULINGS_DIR = PRODUCT_BRAIN.parent / "rulings"

#: `- [001](rulings/001-some-slug.md) — 2026-08-09 — Title (Author)`
INDEX_LINE_RE = re.compile(
    r"^- \[(?P<num>\d{3})\]\(rulings/(?P<filename>\d{3}-[a-z0-9-]+\.md)\) — ",
    re.MULTILINE,
)

#: `001-some-slug.md`. Enforced so the index regex above can never silently stop
#: matching a file that is present but named `1-Some_Slug.md`.
RULING_FILENAME_RE = re.compile(r"^(?P<num>\d{3})-[a-z0-9-]+\.md$")

#: `# RULING 001 — Title`
RULING_HEADING_RE = re.compile(r"^# RULING (?P<num>\d{3}) — .+$", re.MULTILINE)


def _ruling_files() -> list:
    """Every ruling file, README excluded (it is the convention, not a ruling)."""
    if not RULINGS_DIR.is_dir():
        return []
    return sorted(
        p for p in RULINGS_DIR.glob("*.md") if p.name != "README.md"
    )


def _index_entries() -> list:
    """(number, filename) for each index line, in document order."""
    text = _read_product_brain()
    return [
        (m.group("num"), m.group("filename"))
        for m in INDEX_LINE_RE.finditer(text)
    ]


def test_rulings_directory_exists_with_its_convention_doc() -> None:
    assert RULINGS_DIR.is_dir(), (
        f"docs/rulings/ is missing at {RULINGS_DIR}. Ruling 001 makes this the "
        "home for every ruling from 2026-08-09 onward; deleting it does not "
        "revert the ruling, it just loses the rulings."
    )
    assert (RULINGS_DIR / "README.md").exists(), (
        "docs/rulings/README.md is missing. It carries the file shape and the "
        "two collision protocols; without it the next lane invents its own "
        "format and the index regex stops matching."
    )


def test_ruling_001_is_present() -> None:
    """The ruling that created the directory must live in the directory.

    Self-demonstration is the point: if 001 can be banked as a file and read
    back, the mechanism works. It is also the only ruling whose absence would
    make every other test here look arbitrary.
    """
    matches = [p for p in _ruling_files() if p.name.startswith("001-")]
    assert len(matches) == 1, (
        f"expected exactly one 001-* ruling file, found {[p.name for p in matches]}"
    )
    text = matches[0].read_text(encoding="utf-8")
    assert "patch-id" in text, (
        "ruling 001 no longer explains the patch-id detachment it exists to fix. "
        "That WHY is the whole ruling — without it this is just a folder."
    )


@pytest.mark.parametrize("path", _ruling_files() or [None])
def test_every_ruling_file_is_well_formed(path) -> None:
    if path is None:
        pytest.skip("no ruling files yet")
    m = RULING_FILENAME_RE.match(path.name)
    assert m, (
        f"{path.name} does not match NNN-<slug>.md (three digits, then a "
        "lowercase hyphenated slug). The index regex keys on this shape, so a "
        "differently-named file would be invisible to the consistency check."
    )
    text = path.read_text(encoding="utf-8")
    heading = RULING_HEADING_RE.search(text)
    assert heading, (
        f"{path.name} has no `# RULING NNN — Title` heading on its own line."
    )
    assert heading.group("num") == m.group("num"), (
        f"{path.name} is numbered {m.group('num')} in its filename but "
        f"{heading.group('num')} in its heading. A renumbering that touched one "
        "and not the other is exactly how two rulings end up sharing a number."
    )
    assert re.search(r"^date: \d{4}-\d{2}-\d{2}$", text, re.MULTILINE), (
        f"{path.name} has no `date: YYYY-MM-DD` line. An undated ruling cannot "
        "be ordered against the ruling it supersedes."
    )
    assert re.search(r"^author: \S+", text, re.MULTILINE), (
        f"{path.name} has no `author:` line. Who ruled it decides whether it can "
        "be overridden by a lane or only by Alex."
    )


def test_every_ruling_file_has_exactly_one_index_line() -> None:
    """Directory → index. A ruling nobody can find has not been banked."""
    indexed = [filename for _, filename in _index_entries()]
    for path in _ruling_files():
        count = indexed.count(path.name)
        assert count == 1, (
            f"docs/rulings/{path.name} has {count} index lines in "
            "docs/PRODUCT-BRAIN.md, expected exactly 1. Add "
            f"`- [{path.name[:3]}](rulings/{path.name}) — <date> — <title> "
            "(<author>)` to the RULINGS INDEX section, in number order. A filed "
            "but unindexed ruling is invisible to every reader of PRODUCT-BRAIN, "
            "which is the only place anyone looks."
        )


def test_every_index_line_points_at_a_file_that_exists() -> None:
    """Index → directory. A line pointing at nothing is worse than no line."""
    present = {p.name for p in _ruling_files()}
    for num, filename in _index_entries():
        assert filename in present, (
            f"the RULINGS INDEX links rulings/{filename}, which does not exist. "
            "Either the file was deleted (restore it from git — a ruling is not "
            "retired by deletion, it is superseded by a later ruling) or the "
            "line was written before the file."
        )
        assert filename.startswith(num), (
            f"index line [{num}] links {filename}; the number and the file "
            "disagree."
        )


def test_ruling_numbers_are_unique() -> None:
    """Two lanes both reading `041` as the max is the expected collision.

    The protocol is in docs/rulings/README.md: the later-merged lane renumbers
    ITS OWN file upward, never the other one. Renaming a brand-new file costs
    nothing — no reader has cited it, and no patch-id matters because the file
    did not exist upstream either way.
    """
    numbers = [p.name[:3] for p in _ruling_files()]
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, (
        f"duplicate ruling numbers: {duplicates}. The later-merged lane "
        "renumbers its own file upward and updates its index line."
    )


def test_index_is_sorted_ascending() -> None:
    """Sorted order is what makes a conflict resolution mechanical.

    The index line is the one shared-file edit this structure did NOT eliminate,
    and two lanes appending adjacent lines still conflict. Sorted-by-number makes
    the resolution "keep both, sort" — no judgment, nothing droppable — instead
    of a decision about which wording survives.
    """
    numbers = [num for num, _ in _index_entries()]
    assert numbers == sorted(numbers), (
        f"the RULINGS INDEX is out of order: {numbers}. Keep it ascending by "
        "number so a merge conflict resolves by sorting rather than by judgment."
    )


def test_index_section_is_the_last_section_so_appends_do_not_touch_rulings() -> None:
    """The index lives at the END, below the pre-migration archive.

    Not cosmetic. If the index sat above the archived rulings, every new index
    line would be an edit in the middle of the file and the diff would abut
    ruling prose — reintroducing, at one remove, the adjacency this ruling
    exists to remove.
    """
    text = _read_product_brain()
    headers = [
        line for line in text.splitlines() if line.startswith("## ")
    ]
    assert headers, "docs/PRODUCT-BRAIN.md has no '## ' sections at all"
    assert "RULINGS INDEX" in headers[-1], (
        f"the last '## ' section is {headers[-1]!r}, expected the RULINGS INDEX. "
        "A ruling section was appended below the index — that is the retired "
        "pattern. Move it to docs/rulings/NNN-<slug>.md and index it."
    )


# ---------------------------------------------------------------------------
# Q340 (2026-08-12) — the ledger gate: a ruling FILE written with no CLAIM.
#
# The named failure: rulings 035 and 036 were DOUBLE-WRITTEN. `ux-53`/`ux-54`
# claimed both numbers in `.claude/handoff/RULING-CLAIMS.md` and wrote their
# files; a second lane wrote DIFFERENT files at the same two numbers WITHOUT
# EVER CLAIMING. Neither side could see it — each was green locally, and master
# would have gone red only on the SECOND merge (in test_ruling_numbers_are_unique
# above, after the expensive half of the damage is already in ratified prose).
# It was caught by accident, by a plan window that happened to read both trees.
# It was the sixth numbering collision of that single day.
#
# Every test above compares docs/rulings/ against the PRODUCT-BRAIN index. Both
# live in the same commit, so a lane that writes its file AND its index line is
# green no matter who else is holding the number. The ledger is the only
# artifact that spans lanes, so it is the only thing that can catch this
# BEFORE a merge instead of at it.
#
# WHY THIS GATE SKIPS IN CI, AND WHY THAT IS NOT A DEFANGED TEST
# `.gitignore` ignores `.claude/`, so RULING-CLAIMS.md is untracked. It does not
# exist on a CI runner, and it does not exist inside a linked git worktree
# either (worktrees do not carry ignored files). A test that REQUIRED the ledger
# would fail 100% of CI runs and would be deleted within the day. So this is a
# LOCAL gate: it resolves the ledger from the MAIN worktree and skips cleanly
# when there is none. That still satisfies the instruction it was written for —
# "this should die before CI red, not at it" — because it fires at AUTHORING
# time, on the machine of the lane that is about to write the file, which is
# strictly earlier than CI.
#
# Do NOT "fix" the skip by committing the ledger. It is deliberately untracked
# working state shared by the windows on one machine; a tracked copy would be a
# single append region edited by every lane, which is the exact conflict class
# ruling 001 split docs/rulings/ apart to kill.
# ---------------------------------------------------------------------------

#: Relative to a worktree root. Untracked by design — see the block above.
RULING_CLAIMS_RELPATH = Path(".claude") / "handoff" / "RULING-CLAIMS.md"

#: `029  claimed-by latency        2026-08-11  — merged   — Short title`
#: The dash class is deliberately loose (em dash or hyphen): the marker lists at
#: the top of this file already note that an em-dash encoding difference must
#: never be the reason a guard fails.
CLAIM_LINE_RE = re.compile(
    r"^(?P<num>\d{3})\s+claimed-by\s+(?P<lane>\S+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+[—-]+\s*"
    r"(?P<status>claimed|merged|abandoned)\b"
)

#: Anything in the RULINGS section that opens with three digits is meant to be a
#: claim. If it does not parse, the parser has drifted from the format and the
#: gate is silently passing everything — louder to fail here.
CLAIM_SHAPED_RE = re.compile(r"^\d{3}\s")


def _main_worktree_root() -> Path:
    """The main worktree's root, derived from the git common dir.

    In a LINKED worktree, `<root>/.git` is a FILE reading `gitdir: <path>`, and
    that dir holds a `commondir` file pointing back at the main `.git`. The main
    `.git`'s parent is the main worktree root — which is where the untracked
    ledger actually lives. Done with pathlib rather than a `git` subprocess:
    nothing else in this file shells out, and a test that shells out fails
    differently (and more confusingly) when git is absent than when it is.
    """
    repo_root = PRODUCT_BRAIN.parents[1]
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


def _find_ruling_claims_ledger():
    """The ledger path, or None. Current tree first, then the main worktree."""
    for root in (PRODUCT_BRAIN.parents[1], _main_worktree_root()):
        candidate = root / RULING_CLAIMS_RELPATH
        if candidate.is_file():
            return candidate
    return None


def _require_ruling_claims_ledger() -> Path:
    ledger = _find_ruling_claims_ledger()
    if ledger is None:
        pytest.skip(
            "LOCAL GATE, NOT A CI GATE — no .claude/handoff/RULING-CLAIMS.md "
            "found in this tree or in the main worktree. This is expected and "
            "correct on CI and in a fresh clone: .gitignore ignores `.claude/`, "
            "so the ledger is untracked and never reaches a runner or a linked "
            "worktree. The gate is designed to fire at AUTHORING time on the "
            "lane's own machine — earlier than CI, which is the point. If you "
            "are a developer about to add docs/rulings/NNN-<slug>.md and you see "
            "this skip locally, create the ledger in the MAIN worktree "
            "(~/bainluck/.claude/handoff/RULING-CLAIMS.md) and claim your number "
            "in it BEFORE writing the file. Do not commit the ledger to fix this."
        )
    return ledger


def _ledger_rulings_section(text: str) -> list:
    """Lines of the `## RULINGS` section only.

    Bounded by the next `## ` heading, because the file carries a second
    monotonic series (`## GOTCHAS`) whose numbers share the same line format and
    would otherwise be parsed as ruling claims — which would make gotcha 125
    look like a claim on ruling 125 and silently bless a file that has none.
    `### ` sub-headings inside the section (the live-collision writeup) do NOT
    terminate it and carry no claim-shaped lines.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## RULINGS"):
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


def _ledger_claims() -> tuple:
    """((num, status, lane, raw), ...) plus any claim-shaped line that failed."""
    text = _require_ruling_claims_ledger().read_text(encoding="utf-8")
    claims = []
    malformed = []
    for line in _ledger_rulings_section(text):
        m = CLAIM_LINE_RE.match(line)
        if m:
            claims.append(
                (int(m.group("num")), m.group("status"), m.group("lane"), line)
            )
        elif CLAIM_SHAPED_RE.match(line):
            malformed.append(line)
    return claims, malformed


def test_ruling_claims_ledger_parses_in_the_documented_format() -> None:
    """Parser-drift guard, and it runs first for a reason.

    Every other assertion below is vacuously true against a ledger this parser
    cannot read: zero claims means zero repeats, and a floor derived from
    nothing waves every file through. A gate that passes hardest when it is
    broken is the failure this whole file exists to prevent, so the shape of the
    ledger is asserted before anything is concluded from its contents.
    """
    claims, malformed = _ledger_claims()
    assert not malformed, (
        "these lines in the RULINGS section of "
        f"{RULING_CLAIMS_RELPATH} start with a three-digit number but do not "
        f"match the documented claim format: {malformed}. The format is "
        "`NNN  claimed-by <lane>  <date>  — <status> — <title>` with status one "
        "of claimed/merged/abandoned. Fix the line — an unparseable claim is a "
        "number nobody is holding as far as this gate can tell."
    )
    assert claims, (
        f"{RULING_CLAIMS_RELPATH} exists but its `## RULINGS` section yielded "
        "zero parseable claims. Either the section heading was renamed (this "
        "parser keys on a line starting `## RULINGS`) or the line format "
        "changed. Until it parses, this gate is blessing every ruling file in "
        "the tree."
    )


def test_ruling_claims_ledger_is_ascending_with_no_repeated_number() -> None:
    """The same defect one layer up: two live claims on one number.

    `abandoned` lines are excluded from both checks on purpose. The ledger's own
    rule is append-only — an abandonment is recorded by APPENDING a second line
    for that number, which is legitimately both a repeat and out of order. It is
    a burn record, not a claim, so it does not join the monotonic sequence (it
    still burns the number for the file check below).
    """
    claims, _ = _ledger_claims()
    live = [(num, lane) for num, status, lane, _ in claims if status != "abandoned"]
    numbers = [num for num, _ in live]

    repeated = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not repeated, (
        f"{RULING_CLAIMS_RELPATH} has more than one LIVE claim on ruling "
        f"number(s) {repeated}: "
        f"{[(n, lane) for n, lane in live if n in repeated]}. Two lanes are "
        "holding the same number and one of them is about to write ratified "
        "prose that cannot merge. The lane that claimed SECOND renumbers "
        "upward — claim the new number here first, then rename its file and "
        "its PRODUCT-BRAIN index line. (An abandoned claim is exempt; mark it "
        "`abandoned` rather than deleting the line.)"
    )
    assert numbers == sorted(numbers), (
        f"{RULING_CLAIMS_RELPATH} claims are out of order: {numbers}. Keep them "
        "ascending and append-only — the whole value of the ledger is that "
        "`the last line + 1` is a safe read, and it stops being one the moment "
        "a number is inserted out of sequence."
    )


def test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed() -> None:
    """docs/rulings/ → ledger. The direction that catches the double-write.

    Only ONE direction is checked. A claimed number with NO file is explicitly
    LEGAL: the ledger's rule is "claim the number BEFORE you write the file", so
    status `claimed` means the file may not exist yet, and asserting otherwise
    would fail every lane during the window the ledger exists to protect.

    The floor is derived from the ledger's own lowest number rather than
    hardcoded: rulings 001–028 predate the ledger and were never claimed, and a
    hardcoded floor would need editing the day anyone backfills a claim.
    """
    claims, _ = _ledger_claims()
    assert claims, "no parseable claims; see the parser-drift test above"

    floor = min(num for num, _, _, _ in claims)
    live_claims = {
        num: lane for num, status, lane, _ in claims if status != "abandoned"
    }
    burned = {num for num, status, _, _ in claims if status == "abandoned"}

    for path in _ruling_files():
        num = int(path.name[:3])
        if num < floor:
            continue  # predates the ledger (rulings 001–028)
        if num in live_claims:
            continue
        if num in burned:
            pytest.fail(
                f"docs/rulings/{path.name} sits on ruling number {num:03d}, "
                f"which is BURNED in {RULING_CLAIMS_RELPATH} — it was claimed "
                "and then abandoned, and an abandoned number is never reused. "
                "A file on a burned number is exactly as broken as an unclaimed "
                "one, because the lane that burned it may already have cited it "
                "elsewhere. Claim the next free number in the ledger and "
                "renumber this file plus its PRODUCT-BRAIN index line."
            )
        pytest.fail(
            f"docs/rulings/{path.name} exists but ruling number {num:03d} was "
            f"NEVER CLAIMED in {RULING_CLAIMS_RELPATH}. This is the 2026-08-12 "
            "failure verbatim: two lanes wrote different rulings at 035 and 036 "
            "because one of them never claimed, both were green locally, and "
            "master would only have gone red on the second merge.\n\n"
            "FIX: `git fetch`, then APPEND a claim line to the `## RULINGS` "
            f"section of the ledger:\n"
            f"  {num:03d}  claimed-by <your-lane>  <YYYY-MM-DD>  — claimed — "
            "<short title>\n\n"
            "Append the line — do NOT start by renaming the file. Renumbering "
            "ratified prose is the expensive fix (the file, its heading, its "
            "index line, and every citation of it); the ledger line is the "
            "cheap one. Only renumber if the number turns out to be genuinely "
            "taken by another lane, in which case the lane that claimed SECOND "
            "is the one that moves."
        )
