"""CI guard: CLAUDE.md stays readable in one tool call, and no trim deletes a rule.

Two failure classes, one guard.

1. SIZE. The file read tool truncates at 40,000 characters and says nothing.
   Above that limit every lane reads CLAUDE.md silently short — the 2026-08-24
   trim happened because a 72.6k file had been losing its tail (the credential
   rule, the Quick Reference) with no error and no signal. The 2026-08-24 trim
   landed at 39,549: correct, and 451 characters from the same silent failure.
   So the ceiling this test enforces is not the hard limit; it is the hard limit
   minus a reserve, so that crossing it is a scheduled trim rather than an
   incident nobody notices.

2. RULE LOSS. A trim is supposed to move prose and keep rules. The way that goes
   wrong is not malice, it is a rewrite that drops a sentence nobody re-reads.
   MUST_SURVIVE below pins one distinctive substring per load-bearing rule. If
   you are INTENTIONALLY removing or rewording one, that is an Alex ruling:
   update the marker IN THE SAME CHANGE and say so in the commit message. Do not
   delete a marker to make the test pass.

The Gotchas Hot List gets a structural check instead of 54 markers: the entries
must stay contiguously numbered from 1, so dropping one turns master red without
pinning every entry's wording.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
OVERFLOW = REPO_ROOT / "docs" / "claude-md-overflow-2026-08-24.md"

# The tool limit. Above this the file is read truncated, silently.
HARD_LIMIT = 40_000
# The reserve the 2026-08-28 trim bought (Alex's ship: >= 4,000 characters free).
# CI trips here, with 2,000 characters still in hand, so a trim is never urgent.
CI_CEILING = 38_000

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
    assert size < CI_CEILING, (
        f"CLAUDE.md is {size:,} bytes — only {free:,} below the {HARD_LIMIT:,}-char "
        f"tool read limit, past the {CI_CEILING:,} CI ceiling. Every lane is close to "
        f"reading it silently truncated. Trim it: move narrative, rationale, examples "
        f"and code-authoritative enumerations to docs/claude-md-overflow-2026-08-24.md "
        f"(append a dated section) and leave a one-line pointer. Move prose, never rules."
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
    text = _unwrapped(_claude_md())
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
