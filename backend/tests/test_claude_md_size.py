"""Day 0 instruction contract: <=15 KB, unchanged archive and complete hot list.

Alex's release-loop reset moves reference detail into docs without losing any
original text. The archive digest guards that move; entrypoint markers guard
pillars, product rules and gates. Existing rule markers must remain present in
the entrypoint or its unchanged reference archive. AGENTS is only a pointer.
"""

import hashlib
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
OVERFLOW = REPO_ROOT / "docs" / "claude-md-overflow-2026-08-24.md"
DAY0_ARCHIVE = REPO_ROOT / "docs" / "release-loop" / "claude-before-day0-20261101.md"
DAY0_ARCHIVE_SHA256 = "d8da3faf040645fa1dac8ff09c288971edce57bed22dcd52b8c163c61891590a"

# The tool limit. Above this the file is read truncated, silently.
HARD_LIMIT = 40_000
# Alex's Day 0 instruction ceiling is 15 KB, counted as bytes.
CI_CEILING = 15_000

MUST_SURVIVE = [
    # -- the constitution -------------------------------------------------
    "Every future queue in this repo serves a named user-visible ship.",
    "append it to `.claude/handoff/PARKED-MEASUREMENTS.md`",
    "**Certs, audits, sentinels and probes are never the ship.**",
    "build lanes BUILD",
    "An idle build lane is a signal, not a failure",
    "a queue names its PILLAR and its SHIP",
    "**MATCHING · DISCOVER · FORMATTING · TRUTH**",
    "**Architecture-only programs are forbidden**",
    "must stay under 40,000 characters",
    # -- matching / sentinels ---------------------------------------------
    "**RED means REAL.**",
    "an id-less claim NEVER absorbs",
    "Any metric below target for markets that SHOULD match is a bug",
    # -- workflow gates ----------------------------------------------------
    "the Integrator alone rebases, gates, merges, pushes and verifies master",
    "Gates prove something about the commit you tested, not the commit you push.",
    "tests/test_startup.py",
    "the **ESLint gate**",
    "the **TypeScript gate**",
    # -- architecture rules ------------------------------------------------
    "never run LLM calls inside `GET /api/feed`",
    "left-swipe is a soft downrank, never a hard dismissal",
    "COALESCE(calibration_probability, opening_probability)",
    "Anonymous submission must keep working",
    "beat schedule is the authority",
    # -- lanes and handoff -------------------------------------------------
    "`~/bainluck/YOUR-TURN.md`",
    "the fix's author never runs its cert",
    "the cert window never audits its own prior cert subjects",
    "NEVER a verdict",
    # -- issues ------------------------------------------------------------
    "GitHub Issues is the single source of truth",
    "claim_issue.py",
    # -- quota -------------------------------------------------------------
    "FULL_STOP",
    "`SPORT_POLLING_TIERS` is the authority",
    # -- style / analytics -------------------------------------------------
    "light mode only",
    "usePageTracking",
    "**single source of truth** for sport key translation maps",
    # -- credentials -------------------------------------------------------
    "Credentials NEVER go in tracked files",
    "gitleaks is the backstop",
    # -- practice ----------------------------------------------------------
    "audit_matching_quality.py",
    "**Never parallelize**",
    "every fix adds a guard test for its class",
    "Run `/health` at the start of every session",
    # -- db-query guardrails ------------------------------------------------
    "sql_read_guard.py",
    "pg_terminate_backend",
]


def _claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def _unwrapped(text: str) -> str:
    """Collapse whitespace so a marker matches across CLAUDE.md's hard line wraps."""
    return re.sub(r"\s+", " ", text)


def test_claude_md_fits_in_one_read_with_headroom():
    size = len(_claude_md().encode("utf-8"))
    free = HARD_LIMIT - size
    assert size <= CI_CEILING, (
        f"CLAUDE.md is {size:,} bytes, past the {CI_CEILING:,}-byte Day 0 ceiling. "
        "Move reference detail unchanged into docs and retain pillars, product rules, "
        "the complete gotcha hot list and required gates."
    )


def test_overflow_archive_still_holds_the_trimmed_prose():
    assert OVERFLOW.exists(), (
        "docs/claude-md-overflow-2026-08-24.md is the only copy of everything two "
        "trims removed from CLAUDE.md. It is an archive: never delete it."
    )
    text = OVERFLOW.read_text(encoding="utf-8")
    for heading in (
        "# CLAUDE.md overflow archive — 2026-08-24",
        "# Second trim — 2026-08-28",
    ):
        assert heading in text, f"overflow archive lost its {heading!r} section"


def test_every_load_bearing_rule_survives():
    text = _unwrapped(_claude_md() + "\n" + DAY0_ARCHIVE.read_text(encoding="utf-8"))
    missing = [m for m in MUST_SURVIVE if _unwrapped(m) not in text]
    assert not missing, (
        "CLAUDE.md lost load-bearing rule text:\n  "
        + "\n  ".join(repr(m) for m in missing)
        + "\n\nA trim moves prose and keeps rules. If this removal is intentional it "
        "needs an Alex ruling and a matching update to MUST_SURVIVE in the same change."
    )


def test_gotchas_hot_list_is_contiguously_numbered():
    """A dropped gotcha leaves a numbering hole. Catch it structurally."""
    text = _claude_md()
    start = text.index("## Gotchas Hot List")
    end = text.index("## CI Test Coverage", start)
    numbers = [
        int(n) for n in re.findall(r"^(\d+)\. \*\*", text[start:end], re.MULTILINE)
    ]
    assert numbers, "the Gotchas Hot List has no numbered entries"
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"Gotchas Hot List numbering is not contiguous from 1: {numbers}. "
        "An entry was dropped or renumbered — renumbering breaks every citation."
    )
    assert len(numbers) >= 54, (
        f"the Gotchas Hot List has {len(numbers)} entries, down from 54. "
        "Entries are rules; they move to docs/gotchas-reference.md only by ruling."
    )


def test_day0_trim_preserves_every_original_byte():
    assert DAY0_ARCHIVE.exists(), "Day 0 trim must archive the original instructions"
    assert hashlib.sha256(DAY0_ARCHIVE.read_bytes()).hexdigest() == DAY0_ARCHIVE_SHA256


def test_day0_trim_keeps_the_full_hot_list_in_claude():
    original = DAY0_ARCHIVE.read_text(encoding="utf-8")
    start = original.index("## Gotchas Hot List")
    end = original.index("## CI Test Coverage", start)
    assert original[start:end] in _claude_md(), "Hot List must remain unchanged in CLAUDE.md"


def test_day0_trim_keeps_product_rules_and_gates_at_the_entrypoint():
    text = _unwrapped(_claude_md())
    for marker in (
        "MATCHING · DISCOVER · FORMATTING · TRUTH",
        "Every future queue in this repo serves a named user-visible ship.",
        "Architecture-only programs are forbidden",
        "The blend is the product",
        "Settled means settled",
        "light mode only",
        "usePageTracking",
        "never run LLM calls inside `GET /api/feed`",
        "left-swipe is a soft downrank, never a hard dismissal",
        "tests/test_startup.py",
        "npm run build",
        "npm run typecheck",
        "One branch and one PR per change",
        "CI is the only integrator",
        "Nothing reaches master except through a merged PR",
        "Tier A merges on green",
        "Tier B (`tier-b`) merges after an independent review",
        "Tier C requires Alex's tap",
        "`live-path` is the two-minute lane",
        "NOW #11852 is the only priority list and status line",
        "Runner inboxes, YOUR-TURN.md and artifacts/ are retired",
    ):
        assert marker in text, f"entrypoint lost {marker!r}"


def test_agents_is_a_twenty_line_pointer():
    lines = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20
    assert "CLAUDE.md" in "\n".join(lines)
