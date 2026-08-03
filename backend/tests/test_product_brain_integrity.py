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

ALL_MARKERS = REQUIRED_MARKERS + STRUCTURAL_MARKERS


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
    # (new rulings append), never silent collapse.
    assert len(ruling_sections) >= 16, (
        f"docs/PRODUCT-BRAIN.md has only {len(ruling_sections)} '## ' sections; "
        f"the banked baseline (commit 47ece922) had 16. A wholesale "
        f"'consolidation' rewrite has collapsed the accreted ruling history. "
        f"Restore from git and append the new ruling instead of regenerating."
    )
