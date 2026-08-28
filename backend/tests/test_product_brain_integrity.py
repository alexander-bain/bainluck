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
import warnings
from pathlib import Path

import pytest

from tests import ruling_ledger

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

# Q427 (2026-08-28). The four pillars are declared SUPREME over every codebase,
# architecture and UX decision, and they are the FIRST section in the doc — which
# is exactly where a "consolidation" rewrite starts. Every named failure this file
# records is a load-bearing section that was unguarded at the moment it was
# dropped, so the section is pinned in the same change that writes it rather than
# after the first loss. Each pillar is pinned individually: dropping one of four
# while keeping the heading is the cheapest way to hollow out a constitution.
PILLARS_2026_08_28 = [
    "THE FOUR PILLARS",
    "These four are supreme",
    "**MATCHING.**",
    "**DISCOVER.**",
    "**FORMATTING.**",
    "**TRUTH.**",
    "RIDER RULE",
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
    + PILLARS_2026_08_28
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


# ---------------------------------------------------------------------------
# Queue 357 (2026-08-15) — THE NON-VACUITY FLOOR.
#
# Every consistency test above is a comparison between docs/rulings/ and the
# PRODUCT-BRAIN index. Both are quantified over what exists, so both are
# VACUOUSLY TRUE when nothing exists: delete the whole directory and the whole
# index in one commit and the both-directions check — the one deliberately
# written in both directions so a filed-but-unindexed ruling cannot hide — goes
# green, because there is no file to be unindexed and no line to be unfiled.
#
# That is not a hypothetical. It was reported this cycle as an observed state
# ("the index stops at 047, and the gate is green because BOTH SIDES ARE
# EMPTY"). Measurement said otherwise — 64 files, 64 index lines, zero drift in
# either direction — so the sync gate was doing its job. But the hole the report
# named is real and independent of whether it had been fallen into yet: a
# symmetric check cannot distinguish "consistent" from "absent", and the failure
# it would miss is the exact one the doc header records happening TWICE (a
# wholesale rewrite silently dropping ratified rulings).
#
# So the floor is what makes the symmetry mean something. It is deliberately a
# TRACKED CONSTANT rather than a read of RULING-CLAIMS.md: the ledger is
# gitignored, absent on every CI runner and inside every linked worktree, so a
# floor derived from it would skip precisely where a wholesale rewrite gets
# merged. A floor that cannot run in CI is the same vacuity one level up.
#
# It ratchets, like frontend/typecheck-baseline.json: bank a ruling, raise the
# number in the same commit. There is no slack in it on purpose — slack is
# permission to delete exactly that many rulings. A ruling is never retired by
# deletion (it is superseded by a later ruling), and renumbering preserves the
# count, so nothing legitimate ever lowers this.
# ---------------------------------------------------------------------------

#: Measured on `origin/master` @ `cabc791a`: 64 ruling files, 64 index lines,
#: plus ruling 068 banked in the same commit as this floor. Gaps are expected
#: and fine (057-059 reserved-not-minted) — the floor counts what is BANKED,
#: never the highest number claimed.
#:
#: Raised 65 -> 66 by INT-071 when `program/ux-69` landed ruling **067** in the
#: same cycle as q357's 068. 067 was the "held by an in-flight lane" gap this
#: comment used to name; the lane landed, so the gap closed. The ratchet asserts
#: EQUALITY (`test_the_floor_tracks_reality_and_is_raised_when_a_ruling_is_banked`),
#: so this is not optional bookkeeping — merging 067 without this line is red.
#:
#: Raised 67 -> 68 by LAT-P060 banking **073** (CORPUS-MOVED). ⚠️ INTEGRATOR: two other
#: lanes hold an independent 67 -> 68 edit on this same line right now — `lane1/q358` (070)
#: and `program/ux-72` (072). All three merged, the correct value is **70**, which is NOBODY'S
#: side of the conflict. Resolve by COUNTING `docs/rulings/[0-9][0-9][0-9]-*.md` in the merged
#: tree; taking "ours" or "theirs" is wrong in every ordering. This is the one shared append
#: region ruling 001 did not remove — separate ruling FILES cannot conflict, but the equality
#: ratchet that counts them re-creates the collision on a single line.
#:
#: Raised 68 -> 69 by LAT-P061 banking **074** (a green pass names the work it did) on
#: `program/latency-56`, stacked on `-55`. ⚠️ INTEGRATOR: the three-way collision named above is
#: now FOUR-way and the arithmetic is unchanged in kind — `lane1/q358` (070) and `program/ux-72`
#: (072) still hold independent `67 -> 68` edits, and this branch carries `-55`'s 073 plus this
#: 074. **With all four merged the correct value is 71**, which is again nobody's side.
#: **Resolve by COUNTING `docs/rulings/[0-9][0-9][0-9]-*.md` in the merged tree.** Do not take
#: ours, do not take theirs, and do not add the deltas — two lanes each writing `67 -> 68` is one
#: ruling each, not two on top of 68.
#: Raised 71 -> **73** by INT-080 merging TWO independent rulings in one wave:
#: **075** (a derived budget may never fall below the phase's own measured floor, `lane1/q360`)
#: and **076** (planner cost cannot rank two statements, `program/latency-57`). Both branches were
#: cut from `origin/master` `1eb968ee` (71 files) and each independently wrote `71 -> 72`; two
#: lanes each writing `71 -> 72` is one ruling each, NOT two on top of 72. Resolved the documented
#: way — by COUNTING `docs/rulings/[0-9][0-9][0-9]-*.md` in the merged tree, which is 73, and which
#: is again nobody's side. This is the collision #1910 exists to make impossible.
#: RESOLVED BY COUNTING, seventh consecutive cycle. HEAD said 83, program/latency-61 said 82,
#: and neither is the merged truth. Documented rule: COUNT
#: `docs/rulings/[0-9][0-9][0-9]-*.md` in the MERGED tree. Measured here: **85**.
#:
#: 84 = the 83 that stood after the ux wave, plus latency's **086** (the working gauge nobody
#: reads is the same as no gauge), which FILLS the last open gap above 060. The only remaining
#: gaps are **057-059**, still reserved for program/calibration-53's renumber, which is blocked
#: and unmerged. Every number 060-087 is now banked.
#:
#: For the record, because three lanes raced for numbers in one session and all three landed
#: correctly in the end: 084 is ux's (authority lives where it is read), 085 is the
#: integrator's (a READY whose branch head moved is withdrawn), 086 is latency's, 087 is ux's
#: second. The allocation came from RULING-CLAIMS.md, not from counting files — counting files
#: is how you get the FLOOR, reading the ledger is how you get the NUMBER.
#:
#: INT-087 merge (program/latency-62 = LAT-P069) raises 84 -> **85 BY COUNTING**, eighth
#: consecutive cycle and the same rule. HEAD said 84, the branch said 83, and — as every time —
#: neither is the merged truth. The branch banks **088** (a lane may rebase when arriving
#: un-rebased is guaranteed-red; Fable, #1609/#1621); master separately holds **084** and **087**,
#: which the branch does not. Union of `docs/rulings/[0-9][0-9][0-9]-*.md` across both sides,
#: counted rather than added: 85. The branch's own comment states the rule it is resolved by —
#: "COUNT, never take a side" (#1910) — and its warning came true: `ux` did merge first
#: (`c5eecff4`), so the merged tree holds both files and the count is higher again.
#: Gaps 057-059 remain reserved for program/calibration-53's blocked renumber. Every number
#: 060-088 is now banked.
#:
#: INT-088 lands #1991's **095** (a census of a moving population is fiction) and #1988's
#: **090-094** (Fable's five queue-371 rulings) in the same cycle. 86 -> **92 BY COUNTING**:
#: the two branches each carried their own floor bump against different bases (#1991 said 87
#: from a base of 86; #1988 said 90 from a base of 85, already stale by one when it was written),
#: so neither number could simply be taken. 92 is the counted union of docs/rulings/[0-9]{3}-*
#: on the merged tree, not an increment of either claim — COUNT, do not add.
#: Gaps 057-059 remain reserved for program/calibration-53's blocked renumber.
#: INT-090 merge (program/latency-64 onto master @ 50601960): HEAD said 92, the branch said 84,
#: and — for the ninth consecutive cycle — neither is the merged truth. Resolved the documented
#: way, by COUNTING `docs/rulings/[0-9][0-9][0-9]-*.md` in the MERGED tree: **93**, which is
#: master's 92 plus latency's **096** (a read-only endpoint is not a safe endpoint; the
#: measurement is load). COUNT, never add, never take a side (#1910, ruling 088).
#:
#: Raised 93 -> **94** in the SAME cycle by `program/ux-89` banking **097** (no statistic
#: rescues a bad pair; a tie prints the midpoint) — renumbered from 096 by the ux lane on its
#: own branch, per Fable's INT-090 ruling (b): 096 was already burned into filed issue #1994,
#: and the cited number stays while the uncited one moves. Counted on the merged tree again
#: rather than incremented: 94 files match `docs/rulings/[0-9][0-9][0-9]-*.md` here.
#:
#: Raised 95 -> **96** by the INT-092 merge of queue 375 banking **099** (measure the baseline
#: before judging the read) — authored as 096, renumbered to 098 on the branch, and landing as
#: **099** because 098 was taken by `program/ux-90` while 375 waited. ELEVENTH consecutive cycle
#: where neither side of this line was the merged truth: master said 95 and the branch said 95,
#: and the merged tree holds 96 — two branches each raising 94 -> 95 against different bases sum
#: to 96, never 95. COUNT, never add, never take a side (#1910, ruling 088).
#:
#: Also corrected here: master's prose tail stopped at "94 files match" while its constant
#: already read 95, because ux-90's 098 bumped the number without banking a paragraph. The
#: uncommented bump is what made this conflict unreadable — both sides showed 95 and neither
#: said why — so the rule earns a corollary: the paragraph IS the audit trail, and a constant
#: raised silently leaves the next resolver counting files to find out what happened.
#:
#: Raised to **98** by the INT-092 combined merge of `program/ux-91` banking **100** (a metric
#: and its early warning are different jobs) and **101** (group, don't cull). TWELFTH consecutive
#: cycle, and the SECOND time INT-092 resolved this identical conflict — q375 banked 099 hours
#: earlier in the same session. HEAD said 96, the branch said 97, the merged tree holds 98.
#: Neither side was wrong about itself; neither was the truth. COUNT (#1910, ruling 088).
#:
#: Two collisions in one Integrator session is the argument for #2009's LEDGER half rather than
#: its test half: the test caught both, but it caught them at MERGE time, after the number had
#: already been minted twice. A number claimed at AUTHORING time cannot collide.
#:
#: Raised to **99** by CAL-P077, banking ruling **102** ("a worker ships with a test that starts
#: it", Fable ruling (a), #1978). THIRTEENTH consecutive cycle. COUNTED against the rebased base
#: `6e314028`, not inferred: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = **98** before
#: this ruling's file, **99** after. The branch first wrote 97 against base `62846ab8` (96 files);
#: master then landed ux's 100 and 101 and moved to 98; the merged tree holds **99**. Neither
#: side was wrong about itself and neither was the truth — count, never add, never take a side.
#:
#: 102 was claimed in `RULING-CLAIMS.md` at authoring time and verified free by sweeping **470**
#: local and remote refs for `docs/rulings/102-*`, holders_found 0 — which is #2009's ledger half
#: doing exactly what the note above asks for. The claim held through this rebase: ux took 100
#: and 101, not 102, so no renumber was owed and the index reads 099 -> 100 -> 101 -> 102 with no
#: gap.
#:
#: Raised to **100** by the INT-094 combined merge — CAL-P077's **102** (above) and lane1
#: q380's **108** ("a dry run gates only what it executes", Fable, #1947/#1796) in one push.
#: FOURTEENTH consecutive cycle, and the first one where the collision was CALLED IN ADVANCE:
#: Fable's directive named the double-claim on 102 and adjudicated it before the merge — the
#: ledger's claim (`RULING-CLAIMS.md`, digest `b6471e51`, claims=74) wins, so calibration KEEPS
#: 102 and q380's dry-run ruling renumbered. It went to **108**, NOT to 103: the directive said
#: "the next free number", and 103-107 are all claimed-and-unmerged (103 calibration/CAL-P078,
#: 104 latency, 105-107 ux) with the FILES already written on those branches. Measured, not
#: assumed — 489 local and remote refs swept for `docs/rulings/1[0-9][0-9]-`, and the integrity
#: gate below refused 103 by name before the sweep did. Both sides wrote 99 and both were right
#: about themselves; the merged tree holds **100**. COUNTED with
#: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = 100 (ruling 088 — count, never add,
#: never take a side, never eyeball).
#:
#: Note what the ledger bought here that the test could not. The test still catches a repeat, but
#: it catches it at MERGE time with the number already minted twice and two files on disk. The
#: claim caught it at ADJUDICATION time, so the renumber was a rename and one index line rather
#: than a cycle of archaeology. That is #2009's ledger half paying out on the first collision
#: after it was approved.
#:
#: Raised to **101** by INT-094 banking ruling **109** ("a READY token is void while its branch
#: contains a never-merge ancestor", Fable's INT-094 directive) on top of the 102 + 108 pair
#: above — three rulings in one push, so the delta anyone would have GUESSED is wrong twice over.
#: COUNTED: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = 101.
#:
#: Raised to **106** by the INT-095 three-lane merge, in ONE push: calibration-75 banks **103**
#: ("a price captured after the answer is not a price"), latency-69 banks **104** ("hold the TTL
#: at 65"), and ux-94 banks **105**, **106** and **107**. Five rulings across three lanes, and
#: every lane arrived carrying a floor that was correct about ITSELF and wrong about the merge:
#: latency wrote 99, calibration wrote 100, ux wrote 101, master already held 101. No two of
#: those agree and none of them is the answer. COUNTED, three times — once after each merge —
#: with `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'`: 102 -> 103 -> 106. The index runs
#: 102..109 with no gap and no duplicate; 108 and 109 were INT-094's, which is why the numbers
#: are not contiguous with the lanes' own. Ruling 088 — count, never add, never take a side.
#:
#: Raised to **107** by the INT-097 four-branch merge (codex-adhoc/rebaseline,
#: codex-adhoc/subcohort2, calibration-76, ux-95). Only ux-95 banks a ruling: **111**
#: ("movement first with a per-ladder cap"). COUNTED:
#: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = 107. The index now reads
#: ...109 -> 111 with **110 missing on purpose** — it is claimed-and-unmerged on
#: `program/latency-70`. A numeric gap is not a missing ruling and is never closed by
#: renumbering; the invariant this file enforces is file-count == index-count in BOTH
#: directions, which holds at 107/107.
#:
#: Raised to **108** by INT-100 merging `program/ux-96` ALONE (Fable's instruction; depth 0, ux-95
#: already in), which banks ruling **112** ("movement overrides the structural floor"). COUNTED:
#: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = 108. The index reads ...109 -> 111 -> 112;
#: **110 is still missing on purpose**, claimed-and-unmerged on `program/latency-70`.
#:
#: Raised to **109** by INT-101 banking ruling **113** ("a merge offer is a branch with a green
#: gate, not a file", Fable, approving this lane's own proposal after the sweep missed live
#: merge-eligible PRs two cycles running). COUNTED:
#: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = 109. 110 remains claimed-and-unmerged on
#: `program/latency-70`, so the index still reads ...109 -> 111 -> 112 -> 113 with one gap.
#:
#: Raised to **110** by LAT-P077 banking ruling **110** ("the `heavy` lane gets a scoped
#: two-task exception, with its falsifier armed in code", Fable's LAT-P077 directive, #1609).
#: SECOND rebase of this branch in one window: it first wrote 100 against a tree of 99, then
#: 107 against master's 106, and master reached 109 (ux banking 111-113) before it could merge.
#: Three different correct-about-themselves floors from ONE branch in ONE window, which is the
#: cleanest demonstration yet that this constant cannot be authored — only counted.
#: COUNTED on the rebased tree: `ls docs/rulings/ | grep -cE '^[0-9]{3}-.*\.md$'` = **110**.
#: Ruling 088 — count, never add, never take a side.
#:
#: No number collision: 110 was claimed in `RULING-CLAIMS.md` and verified free across 490 refs,
#: and master went on to take 111, 112 and 113 — so the index reads 110..113 with no gap.
#:
#: Raised to **112** by INT-104 merging `program/calibration-80`, `program/ux-100` and
#: `program/latency-71`. Only ux-100 banks a ruling: **114** ("a settled card's quiet rows
#: stay: no tail, no drop", Alex, #2060). The branch arrived carrying 109 and master held 111,
#: so neither side's number was right — SIXTEENTH consecutive cycle in which that is true.
#: latency-71 AMENDS `docs/rulings/110-*.md` in place and adds no file, so it moves nothing.
#: COUNTED on the merged tree: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **112**.
#: The index now reads 110..115 with no gap — 114 was the last hole and this merge fills it.
#: Ruling 088 / #1910 — count, never add a delta, never take a side.
#:
#: Raised to **113** by INT-105 banking ruling **116** (gotcha numbers claim through
#: `RULING-CLAIMS.md`; collisions renumber at merge by counting the merged tree — Fable,
#: 2026-08-21, after three lanes banked #145/#146 simultaneously in one cycle). No other
#: branch in this eight-branch merge adds a ruling file; `latency-72` AMENDS `110-*.md` and
#: this cycle adds a SECOND AMENDMENT to `103-*.md`, and an amendment moves no count.
#: COUNTED on the merged tree: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **113**.
#: 116 was verified free against the ledger AND the merged tree before it was written;
#: `lane1/q353-process`, which was told to renumber its colliding 056 upward, is redirected
#: to **117** in the same turn. Ruling 088 / #1910 — count, never add a delta.
#:
#: Raised to **119** by INT-110's post-freeze drain. FOUR branches in this merge add ruling
#: files, and the collision CAL-P086B declared in advance is the reason this comment exists:
#: `program/calibration-53` banks **057/058/059** and raised the constant to 116;
#: `program/calibration-84` banks **117** and raised it to 114. Both were ready, both were
#: independent, and — as -84's own note predicted verbatim — **neither side's number was
#: right**. `int/int-109` then banks **118**, and `lane1/q353-process` banks **121**.
#: COUNTED on the merged tree: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **119**.
#: Ruling 088 / #1910 — count, never add a delta, never take a side.
#:
#: ⚠️ **119 IS A COUNT, NOT A CEILING, AND THIS CYCLE IS THE CASE THAT SEPARATES THEM.**
#: The highest-numbered file here is **121**, and 119/120 are absent — not lost, HELD.
#: `program/latency-74` holds **119** and `lane1` holds **120** in `RULING-CLAIMS.md`; both
#: are banked on branches outside this merge (latency-74 is suspended), so their files land
#: later and the gap closes from the middle. A reader who "fixes" 121 down to 119 to make the
#: series contiguous silently takes a number another lane has claimed — which is precisely the
#: collision ruling 116 exists to prevent, arrived at from the tidy direction.
#:
#: `q353-process` is the whole argument for claiming through the ledger rather than measuring
#: the tree. Its ruling was written as **056** on 2026-08-14 and spent five cycles being
#: redirected — to 116 (INT-104), then 117 (ruling 116's own text), then 119 (Fable's INT-110
#: directive) — and every one of those targets was taken by another lane before it merged.
#: It landed only when the lane stopped taking the next free number and took the next
#: **claimed-free** one. Fable's directive said 119; the ledger, written after it, records 119
#: to `latency` and 120 to `lane1`, so **121 is correct and the directive is superseded by the
#: instrument it asked us to verify against** ("renumber 119, ledger-verified" — the ledger
#: is the authority, and it had moved).
#:
#: INT-111 (wave 2, 2026-08-23): `program/latency-74` lands the HELD **119**, closing the
#: gap from the middle exactly as the note above predicted. COUNTED on the merged tree =
#: **120**. The branch declared 114 and HEAD 119; as ever, neither side's number was right.
#:
#: INT-111 (wave 2, cont.): `program/calibration-86` banks **124** and **125** (renumbered
#: from 122/123, which were lost to a claim race). COUNTED on the merged tree = **122**.
#: The branch declared 116 against a base of 119 — a third specimen of the stale-declared
#: floor. Alex, INT-111: ignore EVERY declared value; the ledger and the tree are the only
#: authorities.
#:
#: INT-112 (wave 3, 2026-08-24): `program/latency-75` @ `10209343` banks **123**.
#: COUNTED on the FINAL merged tree (all three merges applied — latency-75 pinned,
#: ux-107 amended, calibration-87 added): `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l`
#: = **123**, cross-checked index <-> files in BOTH directions (123 = 123, no orphan
#: file, no orphan index line, ascending, no duplicates).
#:
#: Alex, INT-112: "every declared value so far has been wrong" — declared this wave
#: were 119 (master), 121, and 123. The counted answer happens to equal one of them,
#: and that is a coincidence, not a corroboration: the branch side of this very merge
#: declared **115**, which is four BELOW master's own floor. Count the tree; never
#: read a declaration, not even a lucky one.
#:
#: STILL A COUNT, NOT A CEILING. Highest file is **125**; **120** and **122** are
#: absent and HELD, not lost — 120 is claimed by `lane1` in `RULING-CLAIMS.md` and 122
#: was surrendered in a claim race (calibration-86 renumbered 122/123 -> 124/125).
#: Do not "tidy" 125 down to 123.
#:
#: INT-113 (wave 3, 2026-08-24): **129**, COUNTED on this merged tree, not derived.
#: Batch 1 merged latency-75's held tail (rulings **126**, **127**) and, on Alex's
#: mid-cycle addendum, `program/latency-76` WHOLE (**128**, **129**). Increment 2 then
#: merged PR #2106 (**120**) and PR #2115 (**122**). Count over the wave: 123 -> 129.
#:
#: FOUR specimens of the stale-declared floor in a single wave, and the fourth is the
#: one worth keeping, because it is the integrator's own. Batch 1 resolved HEAD's **125**
#: against the branch's **119** by counting **127**, and this comment SAID 127 -- and then
#: went stale ninety minutes later, inside the same cycle, when #2106 and #2115 landed.
#: The number written by the person holding the merge lock, who had just finished
#: explaining why declared numbers go stale, went stale the same way. That is ruling 088
#: at its most literal: a declaration is a measurement of a tree that no longer exists by
#: the time the merge resolves it, and nobody is standing outside that.
#:
#: THE HELD GAP IS NOW CLOSED, and the closing is the point. Batch 1 recorded that **120**
#: and **122** were "absent and HELD, not lost -- 120 claimed by `lane1` in
#: `RULING-CLAIMS.md`, 122 surrendered in a claim race (calibration-86 renumbered
#: 122/123 -> 124/125)", and that the count therefore correctly trailed the highest file
#: by two. Both holders then banked. The claim ledger was right about both, which is the
#: evidence that a HELD number is a real reservation and not a bookkeeping error: the
#: correct response to a gap is to find its holder, never to renumber down into it.
#:
#: So the count now EQUALS the highest number for the first time in many waves -- 129
#: files, numbered 1..129 with nothing missing in the range. Do not read that as an
#: invariant. It is a coincidence of this tree, and the next claim race breaks it again.
#: STILL A COUNT, NOT A CEILING. Next free number is **130**.
#:
#: Verified index <-> files in BOTH directions on the merged tree: 129 files, 129 index
#: lines, zero orphans either way, ascending, no duplicates, contiguous 1..129.
#: INT-116 (2026-08-24): **131**, COUNTED on this merged tree, not derived.
#: `program/latency-77` (LAT-P086) banks **130** ("a window that straddles a release is
#: inconclusive") and **131** ("index DDL with no code half-runs, attended, outside Alembic").
#: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **131** on the merged tree.
#: The lane claimed both in `RULING-CLAIMS.md` after a `git fetch` in the same turn and swept
#: 575 local and remote refs for `docs/rulings/13[01]-` — holders_found = 0.
#:
#: A FIFTH specimen of the stale-declared floor, and the cleanest one yet, because BOTH sides
#: of this conflict were wrong in the SAME direction and for the same reason. HEAD said **129**
#: and the branch said **121**; the branch's own comment is scrupulous — it counted its tree
#: rather than adding a delta, exactly as ruling 088 demands — and it was still 10 low, because
#: it counted against `origin/master` = `b5c2a750` and master has moved twice since (`56b71ac6`,
#: then `ea07f81e`). Method was not the failing. Correct method applied to a tree that expired
#: before the merge resolved is still a stale declaration, which is the whole of ruling 088:
#: the tree you count must be the tree you are landing, and only the merge knows what that is.
#:
#: STILL A COUNT, NOT A CEILING. The count equals the highest file again — 131 files numbered
#: 1..131, nothing missing in the range — for the second wave running. That is still a
#: coincidence of this tree and not an invariant; the next claim race reopens a gap, and the
#: correct response to a gap is to find its holder in `RULING-CLAIMS.md`, never to renumber
#: down into it. Next free number is **132**.
#:
#: Verified index <-> files in BOTH directions on the merged tree: 131 files, 131 index lines,
#: zero orphans either way, ascending, no duplicates, contiguous 1..131.
#:
#: Q405 (2026-08-24) — 131 -> **133 by COUNTING THIS TREE** (`ls docs/rulings/[0-9][0-9][0-9]-*.md`
#: = 133 files, 133 index lines), never by adding a delta, per ruling 088's corollary. The two new
#: numbers are 132 (capture plays fix-first) and 133 (cert depth tiers by blast radius), both Alex
#: rulings banked from the Q405 addendum. Claimed against `origin/master` = `1410960f` after a
#: `git fetch` in the SAME turn: highest ruling FILE on master **131**, all 582 local AND remote
#: refs swept for `docs/rulings/13[23]-` — holders_found = 0. Still a count and not a ceiling: the
#: count equals the highest file for the third wave running, which remains a property of this tree
#: rather than an invariant.
#:
#: Q406 (2026-08-25) — 133 -> **134 by COUNTING THIS TREE** (`ls docs/rulings/[0-9][0-9][0-9]-*.md`
#: = 134 files, 134 index lines), never by adding a delta. The new number is 134 (build lanes BUILD;
#: measurement is its own lane), Alex's SHIP-directive ruling. Claimed against `origin/master` =
#: `1410960f` after a `git fetch` in the SAME turn: highest ruling FILE on master **131**, all 585
#: local AND remote refs swept for `docs/rulings/134-` — holders_found = 0. Banked onto THIS branch
#: rather than the CLAUDE.md branch on purpose: 132 and 133 live here, so this is the only tree
#: where the count reads 134. On `lane1/q406-ship-doctrine` (CLAUDE.md only, off master) the same
#: bump would read 132 and hand the Integrator a floor that disagrees with its own file count.
#:
#: LAT-P088 (2026-08-24) raises it 131 -> **132** by banking ruling **135** ("a release
#: narrows the window; it does not disqualify the day"). COUNTED on THIS REBASED TREE:
#: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **132**, never a delta added to 131.
#: Claimed after `git fetch` in the same turn: `origin/master` = `ff199795`, merged-tree
#: ruling files **131**, merged-tree max **131**; all **586** local and remote refs
#: (`git for-each-ref refs/heads refs/remotes`) swept for `docs/rulings/135-`,
#: holders_found = 0.
#:
#: THE GAP IS BACK, AND THIS ENTRY IS ITS SIXTH SPECIMEN FROM A NEW ANGLE. The count is
#: **132** while the highest file is **135**: 132, 133 and 134 are absent and HELD by
#: `lane1/q405-rulings-132-133`, claimed-and-unmerged. Do not tidy 135 down into them —
#: the note above already says the correct response to a gap is to find its holder in
#: `RULING-CLAIMS.md`. Two waves of count-equals-highest were, as predicted verbatim
#: there, a coincidence of those trees and not an invariant.
#:
#: The number is 135 and NOT 134 because this lane computed 134 as next-free, then
#: re-swept before writing and found q405 had banked 134 in the interim — inside the same
#: session. The parenthetical "next free 132" in this lane's OWN `READY-latency-LAT-P087.md`,
#: written about an hour earlier, is likewise stale. And this floor itself is the specimen:
#: it was set to **122** against a base of `3af21254`, correctly counted from that tree by
#: ruling 088's method, and was 10 low by the time it was committed, because the Integrator
#: merged LAT-P087 into master WHILE THIS SESSION RAN. Correct method, expired tree — the
#: sixth time in seven waves, and the first where the tree expired under a live lane rather
#: than between cycles. Re-count at merge; never derive from this line.
#:
#: INT-121 (2026-08-25) — the two sides of this conflict were 132 (LAT-P088, banking 135
#: onto a tree without 132-134) and 134 (Q405+Q406, banking 132-134 onto a tree without
#: 135). Resolved per ruling 088 by COUNTING THE MERGED TREE and taking NEITHER side:
#: `ls docs/rulings/[0-9][0-9][0-9]-*.md | wc -l` = **135**, contiguous 1..135, max 135,
#: 135 index lines. Both sides were correct about their own tree and both were wrong about
#: this one, which is the exact failure mode ruling 088 was written for. THE GAP IS CLOSED:
#: this merge is the one that fills 132, 133 and 134 underneath the already-banked 135, so
#: count-equals-highest is true again here — still a property of this tree, not an invariant.
#: LAT-P099 banks 137 (the headline is the cold path a user walks). Raised by
#: COUNTING THIS TREE — 137 files, 137 index lines — never by adding a delta.
#: UX-P146 banks 138 ("price" is not a word we say to readers; the word is
#: PROBABILITY). Raised by COUNTING THIS TREE — 138 files, 138 index lines —
#: never by adding a delta.
#: UX-P149 banks 140 (an inference may reach a user surface only where an
#: independently-pinned population can replay it as a test). Raised by
#: COUNTING THIS TREE — 140 files, 140 index lines — never by adding a delta.
MINIMUM_BANKED_RULINGS = 142


def test_the_rulings_directory_is_not_empty() -> None:
    """The floor, directory side.

    Without this, `test_every_ruling_file_has_exactly_one_index_line` passes
    over zero files.
    """
    count = len(_ruling_files())
    assert count >= MINIMUM_BANKED_RULINGS, (
        f"docs/rulings/ holds {count} rulings, below the banked floor of "
        f"{MINIMUM_BANKED_RULINGS}. Rulings are never retired by deletion — a "
        "ruling is superseded by a later ruling, and the superseded file stays. "
        "If you genuinely banked one and this still fails, you deleted another. "
        "Restore it from git; do not lower this number to go green."
    )


def test_the_rulings_index_is_not_empty() -> None:
    """The floor, index side.

    Without this, `test_every_index_line_points_at_a_file_that_exists` passes
    over zero lines — so a rewrite that dropped the index while leaving the
    directory intact would clear every check but the section-header pin.
    """
    count = len(_index_entries())
    assert count >= MINIMUM_BANKED_RULINGS, (
        f"the RULINGS INDEX has {count} lines, below the banked floor of "
        f"{MINIMUM_BANKED_RULINGS}. An unindexed ruling is invisible to every "
        "reader of PRODUCT-BRAIN, which is the only place anyone looks."
    )


def test_the_floor_tracks_reality_and_is_raised_when_a_ruling_is_banked() -> None:
    """The ratchet's other direction, and the reason the floor stays honest.

    A floor left below reality accumulates silent headroom — after ten banked
    rulings it would permit deleting ten. Same failure as the typecheck
    baseline drifting above the real error count, which is why that gate fails
    on one FEWER error too.

    So: bank a ruling, raise this number in the same commit.
    """
    banked = len(_ruling_files())
    assert banked == MINIMUM_BANKED_RULINGS, (
        f"{banked} rulings are banked but MINIMUM_BANKED_RULINGS is "
        f"{MINIMUM_BANKED_RULINGS}. Raise it to {banked} in this same commit. "
        "The gap between them is headroom to delete rulings undetected, which "
        "is the whole thing this floor exists to remove."
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
#
# ---------------------------------------------------------------------------
# UX-P079 (2026-08-14) — RULING 063. The gate above is correct about WHERE it
# reads and was wrong about HOW. Its verdict is a function of an untracked file
# that six lanes append to and that the Integrator annotates IN PLACE while
# holding the master-write lock. On 2026-08-14 it answered RED and then GREEN
# inside a single UX-P078 window with no action from that lane, and at the RED
# moment it named `docs/rulings/048-an-id-less-claim-never-absorbs.md` — a file
# merged into master hours earlier and untouched by the branch under test. CI
# saw neither state, because `.claude/` is gitignored and this gate skips on a
# runner. Reproduced exactly before it was changed, not taken on report.
#
# The offending line was well-formed English and unreadable to the parser:
#
#     048  claimed-by lane1  2026-08-14  — **MERGED `a06bf5e5`** (INT-068, …) —
#
# Three defects, in the order they did damage:
#
#   D1  A PARTIAL PARSE VANISHED INSTEAD OF BURNING. The status token failed, so
#       the whole line was dropped and its NUMBER went with it. 048 then read as
#       never-claimed and the file check accused an innocent file. The number
#       and the status are independent facts; one being unreadable must never
#       delete the other.
#   D2  THE PARSER REJECTED MEANING IT COULD PLAINLY READ. Status was anchored
#       immediately after the dash run, lowercase only, so decoration rejected
#       the line. A shared prose ledger written by six lanes WILL accrue
#       decoration — this one's claim lines have grown from one line to full
#       paragraphs with bold, backticks and bracketed provenance. A parser that
#       treats punctuation as semantics manufactures shared-state failures at a
#       steady rate.
#   D3  THE VERDICT DID NOT NAME THE STATE IT READ. Two runs, two answers, and
#       nothing in either output identified which snapshot produced it. "The
#       suite was green" was not a falsifiable claim about anything.
#
# THE FIX IS THE SHAPE OF THE WORKTREE INVARIANT (ruling 063, Alex 2026-08-14):
# that invariant made a command's target EXPLICIT IN THE COMMAND instead of
# inherited from invisible session state. Here, the shared state becomes
# explicit in the VERDICT, and the verdict depends only on ambiguity that is
# real:
#
#   F1  Layered parse. A claim-shaped line ALWAYS burns its number, whatever
#       follows it.
#   F2  Status is resolved by MEANING: exactly one of claimed/merged/abandoned
#       as a whole word, case-insensitively, inside the STATUS FIELD (the first
#       dash-delimited segment after the date). Bounded to that field on
#       purpose — these paragraphs narrate, and line 060 says "claimed-and-
#       UNMERGED" in its prose.
#   F3  An unresolved status counts as a LIVE claim. The permissive reading is
#       the safe one for the direction that actually did harm: it can never
#       accuse a file whose claim line is sitting right there.
#   F4  A line fails the run ONLY IF resolving it could change THIS run's
#       verdict — i.e. only if a ruling file in this tree sits on that number,
#       because only then does burned-vs-live change an answer. That single
#       sentence is what stops one lane's typo from redding every other lane's
#       suite, and it is the whole of ruling 063 in operational form.
#   F5  Every ledger-derived verdict NAMES ITS SNAPSHOT — path, mtime, digest,
#       claim count, deviation count — in its failure messages and once per
#       session where a PASSING run can see it too.
#   F6  The parser is separated from the file read, so it can be tested at all.
#       Until now this gate had zero test coverage precisely because its input
#       was unmockable shared state. That is not incidental to the defect; it is
#       the same defect. The self-tests at the bottom of this file pin the
#       2026-08-14 lines VERBATIM.
#
# WHAT WAS DELIBERATELY TRADED AWAY: the old
# `test_ruling_claims_ledger_parses_in_the_documented_format` asserted that NO
# claim-shaped line deviates from the canonical shape, and that assertion is
# gone. It was a PROXY for anti-vacuity, not anti-vacuity itself. The real
# anti-vacuity properties — the ledger yields claims at all, and no claim-shaped
# line is ever silently dropped — are asserted directly below and are strictly
# stronger. Deviations are still counted and still reported in the snapshot
# notice; they are simply no longer fatal to a lane that did not write them.
# ---------------------------------------------------------------------------

#: Relative to a worktree root. Untracked by design — see the block above.
RULING_CLAIMS_RELPATH = ruling_ledger.RULING_CLAIMS_RELPATH

#: Layer 1 — the NUMBER, parsed alone and first. Anything in the RULINGS section
#: that opens with three digits is a claim on that number, and F1 says it burns
#: the number no matter how the rest of the line reads.
CLAIM_NUMBER_RE = re.compile(r"^(?P<num>\d{3})\s")

#: Layer 2/3 — lane and date, each optional and each parsed independently so a
#: missing one cannot take the others down with it.
CLAIM_LANE_RE = re.compile(r"\bclaimed-by\s+(?P<lane>\S+)")
CLAIM_DATE_RE = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")

#: A dash RUN that is acting as a field delimiter: em dash, en dash or hyphen,
#: at the start of the remainder or surrounded by whitespace. The whitespace
#: requirement is what keeps `id-less` and `claimed-by` from splitting.
DASH_DELIMITER_RE = re.compile(r"(?:\s+|^)[—–\-]+(?:\s+|$)")

#: Layer 4 — the three states a claim can be in. Whole word, case-insensitive.
STATUS_WORD_RE = re.compile(r"\b(claimed|merged|abandoned)\b", re.IGNORECASE)

#: Status values the parser can return that are NOT one of the three states.
STATUS_UNKNOWN = "unknown"  # no status word in the status field
STATUS_AMBIGUOUS = "ambiguous"  # two or more DIFFERENT status words in it

#: The canonical shape, kept ONLY to count deviations for the snapshot notice.
#: It is no longer a gate — see "WHAT WAS DELIBERATELY TRADED AWAY" above.
CANONICAL_CLAIM_RE = re.compile(
    r"^(?P<num>\d{3})\s+claimed-by\s+(?P<lane>\S+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+[—-]+\s*"
    r"(?P<status>claimed|merged|abandoned)\b"
)


def _main_worktree_root() -> Path:
    """The main worktree's root, derived from the git common dir.

    In a LINKED worktree, `<root>/.git` is a FILE reading `gitdir: <path>`, and
    that dir holds a `commondir` file pointing back at the main `.git`. The main
    `.git`'s parent is the main worktree root — which is where the untracked
    ledger actually lives. Done with pathlib rather than a `git` subprocess:
    nothing else in this file shells out, and a test that shells out fails
    differently (and more confusingly) when git is absent than when it is.
    """
    return ruling_ledger.main_worktree_root(PRODUCT_BRAIN.parents[1])


def _find_ruling_claims_ledger():
    """The ledger path, or None. Current tree first, then the main worktree."""
    return ruling_ledger.find_ledger(PRODUCT_BRAIN.parents[1])


#: Re-exported so this module's public surface is unchanged by the extraction.
LedgerSnapshotNotice = ruling_ledger.LedgerSnapshotNotice


def _ledger_snapshot(ledger: Path) -> str:
    """A one-line identity for the ledger state a verdict was derived from.

    The digest covers the RULINGS SECTION ONLY, not the whole file: the GOTCHAS
    section and the prose header change for reasons that cannot affect a ruling
    verdict, and a digest that moves for irrelevant reasons is one nobody
    compares.
    """
    text = ledger.read_text(encoding="utf-8")
    claims, dropped = _parse_ledger_claims(text)
    deviations = sum(1 for c in claims if not c["canonical"])
    return ruling_ledger.snapshot(
        ledger,
        "RULINGS",
        f"claims={len(claims)} deviations={deviations} dropped={len(dropped)}",
    )


def _announce_snapshot(ledger: Path) -> None:
    text = ledger.read_text(encoding="utf-8")
    claims, dropped = _parse_ledger_claims(text)
    deviations = sum(1 for c in claims if not c["canonical"])
    ruling_ledger.announce(
        ledger,
        "RULINGS",
        "RULINGS",
        f"claims={len(claims)} deviations={deviations} dropped={len(dropped)}",
    )


def _require_ruling_claims_ledger() -> Path:
    ledger = ruling_ledger.require(
        PRODUCT_BRAIN.parents[1], "ruling", "docs/rulings/NNN-<slug>.md"
    )
    _announce_snapshot(ledger)
    return ledger


def _ledger_rulings_section(text: str) -> list:
    """Lines of the `## RULINGS` section only.

    Bounded by the next `## ` heading, because the file carries a second
    monotonic series (`## GOTCHAS`) whose numbers share the same line format and
    would otherwise be parsed as ruling claims — which would make gotcha 125
    look like a claim on ruling 125 and silently bless a file that has none.
    `### ` sub-headings inside the section (the live-collision writeup) do NOT
    terminate it and carry no claim-shaped lines.

    The bounding rule itself now lives in `ruling_ledger.section_lines`, because
    the DOCTRINE CLAUSES series needs the same bound for the same reason.
    """
    return ruling_ledger.section_lines(text, "RULINGS")


def _status_field(line: str, after: int) -> str:
    """The first dash-delimited segment following the date (or the lane).

    Bounded on purpose (F2). Searching the WHOLE line for a status word looks
    more tolerant and is actually worse: these claim lines are paragraphs that
    narrate their own provenance, and several of them contain the words
    "claimed" and "merged" in prose long after the status field. Ruling 048's
    live line does exactly that — status `merged`, then "Claimed after a
    `git fetch` in the same turn" further along — so a whole-line search would
    report it AMBIGUOUS and re-create the failure this parser exists to end.
    """
    remainder = line[after:]
    parts = [p for p in DASH_DELIMITER_RE.split(remainder) if p.strip()]
    return parts[0] if parts else remainder


def _parse_claim_line(line: str):
    """One claim-shaped line → a dict, parsed in independent layers (F1).

    Returns None only when the line does not open with three digits. Every
    layer below that is optional: a line that yields a NUMBER yields a claim,
    because the number is the fact the ledger exists to record and no failure
    to read the decoration around it may delete that fact.
    """
    number_match = CLAIM_NUMBER_RE.match(line)
    if not number_match:
        return None

    lane_match = CLAIM_LANE_RE.search(line)
    date_match = CLAIM_DATE_RE.search(line)

    after = date_match.end() if date_match else (
        lane_match.end() if lane_match else number_match.end()
    )
    field = _status_field(line, after)
    found = {m.group(1).lower() for m in STATUS_WORD_RE.finditer(field)}
    if not found:
        status = STATUS_UNKNOWN
    elif len(found) == 1:
        status = found.pop()
    else:
        status = STATUS_AMBIGUOUS

    return {
        "num": int(number_match.group("num")),
        "lane": lane_match.group("lane") if lane_match else None,
        "date": date_match.group("date") if date_match else None,
        "status": status,
        "canonical": bool(CANONICAL_CLAIM_RE.match(line)),
        "raw": line,
    }


def _parse_ledger_claims(text: str) -> tuple:
    """(claims, dropped) from ledger TEXT — no file, no shared state (F6).

    `dropped` should always be empty and is returned so a test can say so out
    loud. It is the direct assertion of the property D1 violated: a claim-shaped
    line is never silently discarded.
    """
    claims = []
    dropped = []
    for line in _ledger_rulings_section(text):
        if not CLAIM_NUMBER_RE.match(line):
            continue
        parsed = _parse_claim_line(line)
        if parsed is None:  # pragma: no cover — unreachable by construction
            dropped.append(line)
        else:
            claims.append(parsed)
    return claims, dropped


def _ledger_claims() -> tuple:
    """(claims, dropped) for the ledger this machine actually holds."""
    return _parse_ledger_claims(
        _require_ruling_claims_ledger().read_text(encoding="utf-8")
    )


def _unresolved(claims) -> list:
    """Claims whose status could not be read as one of the three states."""
    return [c for c in claims if c["status"] in (STATUS_UNKNOWN, STATUS_AMBIGUOUS)]


def test_ruling_claims_ledger_parses_in_the_documented_format() -> None:
    """Anti-vacuity guard, and it runs first for a reason.

    Every other assertion below is vacuously true against a ledger this parser
    cannot read: zero claims means zero repeats, and a floor derived from
    nothing waves every file through. A gate that passes hardest when it is
    broken is the failure this whole file exists to prevent.

    RULING 063 changed WHICH property is asserted here. It used to be "no line
    deviates from the canonical shape" — a proxy for anti-vacuity that a lane
    could trip by adding bold to someone else's status field, and did. The two
    properties asserted now are the real thing and are strictly stronger: the
    ledger yields claims at all, and NO CLAIM-SHAPED LINE IS EVER DROPPED.
    Deviations from the canonical shape are still counted, and still reported in
    the per-session snapshot notice — they are simply not fatal to a lane that
    did not write them.
    """
    ledger = _require_ruling_claims_ledger()
    claims, dropped = _ledger_claims()

    assert not dropped, (
        "these lines in the RULINGS section start with three digits and were "
        f"DROPPED by the parser rather than burning their number: {dropped}. "
        "That is defect D1 of 2026-08-14 returning: a dropped line makes a "
        "claimed number read as unclaimed, and the file check then accuses an "
        "innocent ruling file. A claim-shaped line must always yield its "
        f"number.\n  {_ledger_snapshot(ledger)}"
    )
    assert claims, (
        f"{RULING_CLAIMS_RELPATH} exists but its `## RULINGS` section yielded "
        "zero claims. Either the section heading was renamed (this parser keys "
        "on a line starting `## RULINGS`) or the section is empty. Until it "
        "yields claims, this gate is blessing every ruling file in the tree.\n"
        f"  {_ledger_snapshot(ledger)}"
    )


def test_an_unreadable_status_fails_only_when_it_could_change_this_verdict() -> None:
    """RULING 063, in operational form. The one sentence the whole fix reduces to.

    An unreadable status means the parser cannot tell LIVE from BURNED. That
    matters if and only if a ruling file in THIS tree sits on that number,
    because burned-vs-live is the only answer it changes. When no file occupies
    the number, the ambiguity is inert here and belongs to whichever lane owns
    the line — reporting it is right, failing this run for it is not.

    This is the structural half of the fix. Without it, any lane can turn every
    other lane's suite red by mistyping a status in a shared untracked file, and
    the reddened lane has no way to tell that from a defect in its own branch.
    That is precisely what cost the UX-P078 window: RED, then GREEN, with no
    action in between.
    """
    ledger = _require_ruling_claims_ledger()
    claims, _ = _ledger_claims()
    unresolved = _unresolved(claims)
    if not unresolved:
        return

    occupied = {int(p.name[:3]) for p in _ruling_files()}
    blocking = [c for c in unresolved if c["num"] in occupied]

    assert not blocking, (
        "the status field is unreadable on ledger line(s) whose number a ruling "
        "file in this tree OCCUPIES, so this run cannot tell a live claim from "
        "a burned one for: "
        f"{[(c['num'], c['status'], c['lane']) for c in blocking]}.\n\n"
        "Fix the STATUS FIELD of those lines — it is the first dash-delimited "
        "segment after the date, and it must contain exactly one of "
        "claimed / merged / abandoned. Decoration around the word is fine "
        "(`— **MERGED `sha`** —` reads correctly); two different status words "
        "in one field is not.\n\n"
        "Lines whose number NO file occupies are deliberately not fatal — see "
        f"ruling 063.\n  {_ledger_snapshot(ledger)}\n"
        + "\n".join(f"    {c['raw'][:160]}" for c in blocking)
    )


def test_ruling_claims_ledger_is_ascending_with_no_repeated_number() -> None:
    """The same defect one layer up: two live claims on one number.

    `abandoned` lines are excluded from both checks on purpose. The ledger's own
    rule is append-only — an abandonment is recorded by APPENDING a second line
    for that number, which is legitimately both a repeat and out of order. It is
    a burn record, not a claim, so it does not join the monotonic sequence (it
    still burns the number for the file check below).
    """
    ledger = _require_ruling_claims_ledger()
    claims, _ = _ledger_claims()
    live = [
        (c["num"], c["lane"]) for c in claims if c["status"] != "abandoned"
    ]
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
        "`abandoned` rather than deleting the line.)\n"
        f"  {_ledger_snapshot(ledger)}"
    )
    assert numbers == sorted(numbers), (
        f"{RULING_CLAIMS_RELPATH} claims are out of order: {numbers}. Keep them "
        "ascending and append-only — the whole value of the ledger is that "
        "`the last line + 1` is a safe read, and it stops being one the moment "
        "a number is inserted out of sequence.\n"
        f"  {_ledger_snapshot(ledger)}"
    )


#: Words that carry no identity. A claim and a file that share only these share
#: nothing: "a gate is not the one that runs" and "a claim is not the one that
#: runs" would agree on every token in this set and on no fact.
_TITLE_STOPWORDS = frozenset(
    """
    a an and are as at be because before but by can cannot did do does for from
    had has have how in into is it its must never no not of on one only or our
    over own same so than that the their them then there these they this those
    to two up was what when where which who whose why will with you your
    """.split()
)


def _title_tokens(text: str) -> set:
    """Distinctive words in a ruling title or slug. Lowercased, stopwords out."""
    return {
        tok
        for tok in re.findall(r"[a-z0-9]+", (text or "").lower())
        if tok not in _TITLE_STOPWORDS and len(tok) > 2
    }


def _assert_the_claim_is_for_THIS_ruling(path, num, claims, ledger) -> None:
    """A claim on the NUMBER is not a claim BY YOU (queue 371 item 3).

    The gate this guards used to read `if num in live_claims: continue` — it
    passed as long as the number was claimed **by anyone**. That admits the exact
    collision the ledger exists to prevent, one step further along:

        lane A claims 085 for "a READY whose branch head moved is withdrawn"
        lane B writes docs/rulings/085-something-else.md and never claims

    085 is in `live_claims`, so the file walks straight past the check. The
    unclaimed-number case is caught; the **claim-jumping** case — the one where
    two lanes both believe they hold 085 — is not, and it is the more dangerous
    of the two, because lane A has already cited 085 in prose that now points at
    lane B's ruling.

    There is no author field on a ruling file, so "is this claimant YOU" is
    checked the only way the artifacts allow and the only way that matters: the
    claim must be **for this ruling**. A claim whose title shares no distinctive
    word with the file's slug is a claim on someone else's work.

    A claim carrying NO title fails too, and deliberately: it names a number and
    nothing else, so it cannot answer the question. Could-not-check never renders
    as nothing-to-report.
    """
    claim = next((c for c in claims if c["num"] == num), None)
    if claim is None:  # pragma: no cover — caller already matched on num
        return

    raw = claim["raw"]
    # The title region starts after the FIRST status word that follows the date —
    # the same anchoring `_parse_claim_line` uses, and for the same two reasons.
    # Searching from the start of the line matches `claimed` inside `claimed-by`,
    # so the "title" would begin at the LANE. Splitting on the LAST status word
    # instead eats any title that ends in one ("...; branch not yet merged").
    # Either way the check reads empty because of its own parser rather than
    # because the ledger said nothing, which is the failure it exists to catch.
    date_hit = CLAIM_DATE_RE.search(raw)
    after_date = date_hit.end() if date_hit else 0
    status_hit = STATUS_WORD_RE.search(raw, after_date)
    title_region = raw[status_hit.end():] if status_hit else raw[after_date:]
    claim_tokens = _title_tokens(title_region)
    file_tokens = _title_tokens(path.stem[4:])  # drop the "NNN-" prefix

    if not claim_tokens:
        pytest.fail(
            f"ruling {num:03d} is claimed in {RULING_CLAIMS_RELPATH} but the "
            "claim line carries NO TITLE, so it cannot be checked against "
            f"docs/rulings/{path.name}. A claim that names a number and nothing "
            "else records that the number is taken; it does not record WHAT it "
            "was taken for, which is the only thing that distinguishes your "
            "claim from someone else's.\n\n"
            f"  claim: {raw.strip()}\n\n"
            "FIX: complete the line with the ruling's short title:\n"
            f"  {num:03d}  claimed-by <lane>  <YYYY-MM-DD>  — <status> — "
            "<short title>\n"
            f"  {_ledger_snapshot(ledger)}"
        )

    if claim_tokens & file_tokens:
        return

    pytest.fail(
        f"docs/rulings/{path.name} sits on ruling number {num:03d}, which IS "
        f"claimed in {RULING_CLAIMS_RELPATH} — but claimed for a DIFFERENT "
        f"ruling, by {claim['lane'] or 'an unnamed lane'}:\n\n"
        f"  claim: {raw.strip()}\n"
        f"  file:  {path.name}\n\n"
        "A claim on the NUMBER is not a claim BY YOU. Two lanes both holding "
        "085 is the 2026-08-12 double-write with the ledger's own permission "
        "slip attached: the number-is-claimed check passes, both trees are "
        "green, and the lane that claimed FIRST has already cited 085 in prose "
        "that now points at this file.\n\n"
        "FIX: if the number really is yours, the claim line is wrong — correct "
        "its title. If it is not, `git fetch`, claim the next free number, and "
        "renumber THIS file plus its PRODUCT-BRAIN index line; the lane that "
        "claimed SECOND is the one that moves.\n"
        f"  {_ledger_snapshot(ledger)}"
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
    ledger = _require_ruling_claims_ledger()
    claims, _ = _ledger_claims()
    assert claims, "no claims parsed; see the anti-vacuity test above"

    floor = min(c["num"] for c in claims)
    # F3: an UNREADABLE status counts as LIVE. The permissive reading is the
    # safe one for this direction — it can never accuse a file whose claim line
    # is sitting right there in the ledger, which is the 2026-08-14 failure. The
    # burned-vs-live ambiguity it defers is caught by
    # test_an_unreadable_status_fails_only_when_it_could_change_this_verdict,
    # which fires on exactly the numbers where the deferral would matter.
    live_claims = {
        c["num"]: c["lane"] for c in claims if c["status"] != "abandoned"
    }
    burned = {c["num"] for c in claims if c["status"] == "abandoned"}

    for path in _ruling_files():
        num = int(path.name[:3])
        if num < floor:
            continue  # predates the ledger (rulings 001–028)
        if num in live_claims:
            _assert_the_claim_is_for_THIS_ruling(path, num, claims, ledger)
            continue
        if num in burned:
            pytest.fail(
                f"docs/rulings/{path.name} sits on ruling number {num:03d}, "
                f"which is BURNED in {RULING_CLAIMS_RELPATH} — it was claimed "
                "and then abandoned, and an abandoned number is never reused. "
                "A file on a burned number is exactly as broken as an unclaimed "
                "one, because the lane that burned it may already have cited it "
                "elsewhere. Claim the next free number in the ledger and "
                "renumber this file plus its PRODUCT-BRAIN index line.\n"
                f"  {_ledger_snapshot(ledger)}"
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
            "is the one that moves.\n\n"
            "BEFORE YOU CHASE THIS IN YOUR OWN DIFF: this gate reads SHARED "
            "MUTABLE STATE — an untracked ledger in the MAIN worktree that "
            "every live lane appends to. Quote the snapshot below in your "
            "report, and re-read it before concluding anything, because it can "
            "change under you mid-window (ruling 063).\n"
            f"  {_ledger_snapshot(ledger)}"
        )


# ---------------------------------------------------------------------------
# UX-P079 / RULING 063 — THE GATE'S OWN SELF-TESTS.
#
# Until now the ledger gate had ZERO test coverage, and that was not an
# oversight: its only input was a file on the machine that no test could supply.
# `_parse_ledger_claims(text)` exists so the parser can be exercised against
# text, which is what makes the rest of this section possible. Separating the
# parser from the shared file IS part of the fix, not preparation for it.
#
# The first specimen below is the 2026-08-14 ledger VERBATIM. A synthetic
# paraphrase would have been easier to write and would prove nothing: the whole
# lesson is that the real line was readable English the parser refused, so the
# real line is what must be pinned.
# ---------------------------------------------------------------------------

#: The exact status field INT-068 wrote while merging 048/049/051, which redded
#: two tests in every worktree on the machine. Reproduced before it was fixed.
HISTORICAL_2026_08_14_LEDGER = """# RULING-CLAIMS

## RULINGS — `docs/rulings/NNN-<slug>.md`

047  claimed-by ux-59          2026-08-13  — claimed  — ONE CARD SYSTEM
048  claimed-by lane1          2026-08-14  — **MERGED `a06bf5e5`** (INT-068, 2026-08-14) — An id-less claim NEVER absorbs
049  claimed-by calibration    2026-08-14  — **MERGED `a06bf5e5`** (INT-068, 2026-08-14) — A criterion that cannot fail is not evidence
051  claimed-by lane1          2026-08-14  — **MERGED `a06bf5e5`** (INT-068, 2026-08-14) — Below the floor a source is absent

## GOTCHAS — `docs/gotchas-reference.md`
125  claimed-by lane1          2026-08-13  — merged   — a gotcha, not a ruling
"""


def _statuses(text: str) -> dict:
    claims, _ = _parse_ledger_claims(text)
    return {c["num"]: c["status"] for c in claims}


def test_the_2026_08_14_ledger_state_no_longer_accuses_an_innocent_file() -> None:
    """The regression, pinned to the real specimen (F7).

    On the day, this exact text produced two failures, one of them naming
    `docs/rulings/048-an-id-less-claim-never-absorbs.md` — a file that had
    merged into master hours earlier and was untouched by the branch under test.
    """
    claims, dropped = _parse_ledger_claims(HISTORICAL_2026_08_14_LEDGER)

    assert not dropped, "a claim-shaped line was dropped — defect D1 is back"
    assert {c["num"] for c in claims} == {47, 48, 49, 51}, (
        "every claim-shaped line must burn its number regardless of how its "
        "status field is decorated (F1)"
    )
    assert _statuses(HISTORICAL_2026_08_14_LEDGER)[48] == "merged", (
        "`— **MERGED `a06bf5e5`** (INT-068, 2026-08-14) —` is unambiguous "
        "English and must parse as merged (F2). This assertion is the whole "
        "finding: the parser refused a line whose meaning it could read, and a "
        "shared prose ledger written by six lanes will always accrue decoration."
    )
    live = {c["num"] for c in claims if c["status"] != "abandoned"}
    assert 48 in live, (
        "ruling 048 must read as LIVE-CLAIMED against the 2026-08-14 ledger. "
        "This is the assertion that makes the false accusation structurally "
        "impossible rather than merely unlikely."
    )


def test_the_gotchas_section_is_still_not_read_as_ruling_claims() -> None:
    """The section boundary predates this change and must survive it.

    Gotcha 125 sharing the claim line format is why `_ledger_rulings_section`
    exists; a looser parser is exactly the kind of change that would quietly
    re-merge the two series and bless a ruling file at 125 that nobody holds.
    """
    assert 125 not in _statuses(HISTORICAL_2026_08_14_LEDGER)


def test_a_number_burns_even_when_everything_after_it_is_unreadable() -> None:
    """F1, at its limit: number present, nothing else legible."""
    text = "## RULINGS\n\n061  \xa1\xa1 who wrote this \xa1\xa1\n"
    claims, dropped = _parse_ledger_claims(text)
    assert not dropped
    assert [c["num"] for c in claims] == [61]
    assert claims[0]["status"] == STATUS_UNKNOWN
    assert claims[0]["lane"] is None
    assert claims[0]["canonical"] is False


def test_status_is_read_from_the_status_field_not_from_the_prose() -> None:
    """F2's bound, and the reason it is a bound rather than a whole-line search.

    Ruling 048's real ledger line says `— merged —` and then, paragraphs later,
    "Claimed after a `git fetch` in the same turn". A whole-line search finds
    both words, calls it AMBIGUOUS, and re-creates the failure. Line 060's real
    text is the mirror image: status `claimed`, prose containing
    "claimed-and-UNMERGED" — where `merged` must NOT match inside `UNMERGED`.
    """
    merged_then_prose = (
        "## RULINGS\n\n"
        "048  claimed-by lane1  2026-08-14  — merged — [LANDED `a06bf5e5`] "
        "An id-less claim NEVER absorbs. Claimed after a `git fetch` in the "
        "SAME turn: origin/master = `1ac0aa08`.\n"
    )
    assert _statuses(merged_then_prose)[48] == "merged"

    claimed_then_unmerged = (
        "## RULINGS\n\n"
        "060  claimed-by latency  2026-08-14  — claimed  — NEVER GROW A GRADED "
        "COHORT IN PLACE. 048, 049 and 051 are all claimed-and-UNMERGED.\n"
    )
    assert _statuses(claimed_then_unmerged)[60] == "claimed", (
        "`merged` must not match inside `UNMERGED` — the word boundary is "
        "load-bearing, and prose after the status field is not the status"
    )


def test_two_different_status_words_in_one_field_is_ambiguous() -> None:
    """The one case the parser must refuse to guess at."""
    text = (
        "## RULINGS\n\n"
        "062  claimed-by ux-65  2026-08-14  — claimed then abandoned — title\n"
    )
    assert _statuses(text)[62] == STATUS_AMBIGUOUS


def test_abandoned_still_burns_and_still_parses_when_decorated() -> None:
    """The burn record must survive the same decoration a merge note gets."""
    text = (
        "## RULINGS\n\n"
        "030  claimed-by ux-50  2026-08-11  — claimed  — first take\n"
        "030  claimed-by ux-50  2026-08-11  — **ABANDONED** (renumbered to 032) — first take\n"
    )
    claims, _ = _parse_ledger_claims(text)
    assert [c["status"] for c in claims] == ["claimed", "abandoned"]


def test_the_canonical_shape_is_counted_but_never_fatal() -> None:
    """What ruling 063 traded away, asserted so the trade cannot be undone by
    accident. A deviation is DATA — it appears in the snapshot notice — and it
    is not a verdict."""
    canonical = "029  claimed-by latency  2026-08-11  — merged   — Short title"
    decorated = "048  claimed-by lane1  2026-08-14  — **MERGED `a06bf5e5`** — t"
    claims, _ = _parse_ledger_claims(f"## RULINGS\n\n{canonical}\n{decorated}\n")
    assert [c["canonical"] for c in claims] == [True, False]
    assert [c["status"] for c in claims] == ["merged", "merged"], (
        "both lines mean the same thing; only one of them is canonical, and "
        "that difference must not change the verdict"
    )


def _digest_of(snapshot: str) -> str:
    """The `digest=` field, found BY NAME.

    UX-P108: this used to be `snapshot.split()[1]`, and adding a `section=`
    field to the shared snapshot silently moved the digest to index 2 — a
    positional read of a self-describing string, which is the punctuation-over-
    meaning parse ruling 063 forbids one file over. Fixed at the read.
    """
    for field in snapshot.split():
        if field.startswith("digest="):
            return field
    raise AssertionError(f"no digest= field in snapshot: {snapshot!r}")


def test_the_snapshot_names_the_state_a_verdict_came_from(tmp_path) -> None:
    """F5. A verdict that cannot name its input is not falsifiable.

    Asserted on the DIGEST specifically: mtime alone moves when a lane rewrites
    the file identically, and a path alone never moves at all. The digest is
    scoped to the RULINGS section so that GOTCHAS churn — a different series in
    the same file — cannot make two identical ruling verdicts look different.
    """
    ledger = tmp_path / "RULING-CLAIMS.md"
    ledger.write_text(HISTORICAL_2026_08_14_LEDGER, encoding="utf-8")
    first = _ledger_snapshot(ledger)

    assert "digest=" in first and "mtime=" in first
    assert "claims=4" in first, first
    assert "dropped=0" in first, first
    assert "deviations=3" in first, (
        "the three decorated lines must be COUNTED as deviations even though "
        "they parse and do not fail — that is the whole shape of the trade"
    )

    ledger.write_text(
        HISTORICAL_2026_08_14_LEDGER.replace(
            "125  claimed-by lane1          2026-08-13  — merged   — a gotcha, not a ruling",
            "126  claimed-by lane1          2026-08-14  — merged   — another gotcha",
        ),
        encoding="utf-8",
    )
    assert _digest_of(_ledger_snapshot(ledger)) == _digest_of(first), (
        "a GOTCHAS-only edit must not move the RULINGS digest, or nobody will "
        "compare two digests that differ for reasons they do not care about"
    )

    # Appended INSIDE the RULINGS section. Appending to the END of the file puts
    # the line under `## GOTCHAS`, where it is correctly not a ruling claim and
    # correctly does not move the digest — which this test caught on its first
    # run, and which is the section boundary doing its job.
    ledger.write_text(
        HISTORICAL_2026_08_14_LEDGER.replace(
            "\n\n## GOTCHAS",
            "\n052  claimed-by latency  2026-08-14  — claimed  — a real new claim"
            "\n\n## GOTCHAS",
        ),
        encoding="utf-8",
    )
    assert _digest_of(_ledger_snapshot(ledger)) != _digest_of(first), (
        "a new RULINGS claim MUST move the digest — otherwise the snapshot "
        "cannot distinguish the RED state from the GREEN one it became"
    )


def _with_ledger(monkeypatch, text, tmp_path):
    ledger = tmp_path / "RULING-CLAIMS.md"
    ledger.write_text(text, encoding="utf-8")
    monkeypatch.setitem(globals(), "_require_ruling_claims_ledger", lambda: ledger)
    return ledger


def _ledger_with_every_ruling_claimed(extra_line: str = "") -> str:
    """A ledger that claims every ruling file this tree holds.

    Built from `_ruling_files()` rather than hardcoded, so it cannot go stale the
    next time a lane banks a ruling — the same staleness trap the ledger's own
    floor-not-oracle header describes.

    Each claim's TITLE is the file's own slug, because since queue 371 the gate
    also checks that a claim is for THIS ruling and not merely on its number. A
    fixture titled `t` would be a fixture in which every claim is a claim-jump.
    """
    body = "\n".join(
        f"{int(p.name[:3]):03d}  claimed-by lane1  2026-08-12  — merged   — "
        f"{p.stem[4:].replace('-', ' ')}"
        for p in _ruling_files()
    )
    return f"# L\n\n## RULINGS\n\n{body}{extra_line}\n\n## GOTCHAS\n125  x\n"


def test_an_unreadable_status_is_inert_on_a_number_no_file_occupies(
    monkeypatch, tmp_path
) -> None:
    """RULING 063's operational rule, first half — and the half that IS the fix.

    A lane must NOT be failed by ambiguity in shared state that changes no answer
    on its own branch. Without this, one typo in an untracked file reds every
    live lane's suite and none of them can tell it from a defect of their own.
    """
    unoccupied = max(int(p.name[:3]) for p in _ruling_files()) + 9
    _with_ledger(
        monkeypatch,
        _ledger_with_every_ruling_claimed(
            f"\n{unoccupied:03d}  claimed-by ux-65  2026-08-14  — ?? illegible ?? — t"
        ),
        tmp_path,
    )

    claims, dropped = _ledger_claims()
    assert not dropped
    assert any(
        c["num"] == unoccupied and c["status"] == STATUS_UNKNOWN for c in claims
    ), "the line must still be READ and its number still burned (F1/F3)"

    test_an_unreadable_status_fails_only_when_it_could_change_this_verdict()
    test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed()


def test_an_unreadable_status_is_fatal_on_a_number_a_file_occupies(
    monkeypatch, tmp_path
) -> None:
    """The other half. The permissiveness above is SCOPED, not general.

    On an occupied number the parser genuinely cannot tell burned from live, and
    that ambiguity does change an answer — so it fails, and it names the number.
    """
    occupied_path = min(_ruling_files(), key=lambda p: int(p.name[:3]))
    occupied = int(occupied_path.name[:3])
    title = occupied_path.stem[4:].replace("-", " ")
    canonical = f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged   — {title}"
    illegible = f"{occupied:03d}  claimed-by lane1  2026-08-12  — ?? none ?? — {title}"
    _with_ledger(
        monkeypatch,
        _ledger_with_every_ruling_claimed().replace(canonical, illegible),
        tmp_path,
    )

    with pytest.raises(AssertionError) as exc:
        test_an_unreadable_status_fails_only_when_it_could_change_this_verdict()
    assert str(occupied) in str(exc.value)
    assert "digest=" in str(exc.value), (
        "even this failure must name the snapshot it came from (F5) — a verdict "
        "about shared mutable state that cannot identify the state is the "
        "unfalsifiable-green defect wearing a different hat"
    )


def test_a_claim_by_ANOTHER_lane_on_the_same_number_is_caught(
    monkeypatch, tmp_path
) -> None:
    """Queue 371 item 3: the guard must check the number is claimed by THIS
    claimant, not by anyone.

    The cross-claimant collision, staged exactly: the ledger holds a live claim
    on an occupied number, but the claim is for a DIFFERENT ruling. Before the
    fix this passed — `if num in live_claims: continue` asked only whether the
    number was taken, so lane B's file walked past lane A's claim and both lanes
    left believing they held it.
    """
    occupied_path = min(_ruling_files(), key=lambda p: int(p.name[:3]))
    occupied = int(occupied_path.name[:3])
    title = occupied_path.stem[4:].replace("-", " ")
    mine = f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged   — {title}"
    theirs = (
        f"{occupied:03d}  claimed-by ux-53  2026-08-12  — merged   — "
        "quantum bicycle repair for underwater philately"
    )
    _with_ledger(
        monkeypatch,
        _ledger_with_every_ruling_claimed().replace(mine, theirs),
        tmp_path,
    )

    with pytest.raises(pytest.fail.Exception) as exc:
        test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed()
    message = str(exc.value)
    assert "claimed for a DIFFERENT ruling" in message
    assert "ux-53" in message, "the failure must name WHO holds the number"
    assert occupied_path.name in message
    assert "digest=" in message, "a verdict names the snapshot it came from (F5)"


def test_a_claim_with_no_title_cannot_certify_a_file(monkeypatch, tmp_path) -> None:
    """The unverifiable case is a refusal, not a pass.

    A claim line that carries a number and no title records that the number is
    taken and nothing about what it was taken FOR — so it cannot distinguish
    your claim from a claim-jump. Could-not-check never renders as
    nothing-to-report.
    """
    occupied_path = min(_ruling_files(), key=lambda p: int(p.name[:3]))
    occupied = int(occupied_path.name[:3])
    title = occupied_path.stem[4:].replace("-", " ")
    titled = f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged   — {title}"
    bare = f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged"
    _with_ledger(
        monkeypatch,
        _ledger_with_every_ruling_claimed().replace(titled, bare),
        tmp_path,
    )

    with pytest.raises(pytest.fail.Exception) as exc:
        test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed()
    assert "carries NO TITLE" in str(exc.value)


def test_a_matching_claim_still_passes(monkeypatch, tmp_path) -> None:
    """Both directions (gotcha #43). The guard must not fail the honest case.

    Same number, same lane, a title that is a re-wording of the file's slug
    rather than a copy of it — which is what a real ledger line looks like.
    """
    occupied_path = min(_ruling_files(), key=lambda p: int(p.name[:3]))
    occupied = int(occupied_path.name[:3])
    slug_words = occupied_path.stem[4:].split("-")
    distinctive = next(
        (w for w in slug_words if w not in _TITLE_STOPWORDS and len(w) > 2),
        slug_words[-1],
    )
    title = occupied_path.stem[4:].replace("-", " ")
    exact = f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged   — {title}"
    reworded = (
        f"{occupied:03d}  claimed-by lane1  2026-08-12  — merged   — "
        f"on {distinctive}, restated in other words (landed `abc1234`)"
    )
    _with_ledger(
        monkeypatch,
        _ledger_with_every_ruling_claimed().replace(exact, reworded),
        tmp_path,
    )

    test_every_ruling_file_at_or_above_the_ledger_floor_is_claimed()


def test_the_snapshot_notice_fires_once_per_session(monkeypatch, tmp_path) -> None:
    """F5's delivery mechanism, not just its string.

    `_ledger_snapshot` being correct is worthless if nothing emits it on a
    PASSING run — that is the exact gap that made "the suite was green"
    unfalsifiable. Pinned so a future cleanup cannot drop the warning and leave
    the helper behind looking like coverage.
    """
    # Patched one layer DOWN from the other tests on purpose: they replace
    # `_require_ruling_claims_ledger`, which is the function that emits, so
    # patching it there would test the stub instead of the seam.
    #
    # UX-P108 moved that seam into `ruling_ledger`, so the patch moved with it.
    # The once-per-session latch is now a SET keyed by series rather than a
    # bool, because the clause gate reads a different section of the same file
    # and its snapshot must not be suppressed by this one having already fired —
    # two verdicts from two sections need two receipts.
    ledger = tmp_path / "RULING-CLAIMS.md"
    ledger.write_text(_ledger_with_every_ruling_claimed(), encoding="utf-8")
    monkeypatch.setattr(ruling_ledger, "find_ledger", lambda _root: ledger)
    monkeypatch.setattr(ruling_ledger, "_ANNOUNCED", set())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _require_ruling_claims_ledger()
        _require_ruling_claims_ledger()

    notices = [w for w in caught if issubclass(w.category, LedgerSnapshotNotice)]
    assert len(notices) == 1, (
        f"expected exactly one notice per session, got {len(notices)} — one per "
        "test would be noise nobody reads, and zero is the defect"
    )
    assert "digest=" in str(notices[0].message)
    assert "SHARED MUTABLE STATE" in str(notices[0].message)
