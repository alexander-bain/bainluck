#!/usr/bin/env python3
"""Generate the web + native mirrors of contracts/category-acronyms.json.

#1930 acceptance requires ONE shared acronym list across web and native, not
two copies that drift. This script is the single writer: it reads the JSON
authority and rewrites both generated files byte-identically. A jest parity
test (frontend/__tests__/categoryAcronymParity1930.test.ts) enforces that the
checked-in mirrors match this output, so hand-editing a mirror fails CI.

Usage (repo root):  python3 scripts/generate_category_acronyms.py [--check]
  --check: exit 2 when a mirror differs instead of rewriting it.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTHORITY = ROOT / "contracts" / "category-acronyms.json"
TS_OUT = ROOT / "frontend" / "lib" / "categoryAcronyms.generated.ts"
SWIFT_OUT = (
    ROOT / "ios" / "Bain Luck" / "Bain Luck" / "Utilities" / "CategoryAcronyms.generated.swift"
)


def load_authority() -> list[str]:
    data = json.loads(AUTHORITY.read_text())
    tokens = data["acronyms"]
    assert tokens == sorted(tokens), "authority list must stay sorted"
    assert len(set(tokens)) == len(tokens), "authority list must be duplicate-free"
    return tokens


def render_ts(tokens: list[str]) -> str:
    body = ",\n  ".join(f'"{t}"' for t in tokens)
    return (
        "// Code generated from contracts/category-acronyms.json by\n"
        "// scripts/generate_category_acronyms.py — do not edit by hand.\n"
        "// #1930: the single shared category-acronym list (web mirror).\n"
        "export const CATEGORY_ACRONYMS: readonly string[] = [\n"
        f"  {body},\n"
        "];\n"
    )


def render_swift(tokens: list[str]) -> str:
    body = ",\n    ".join(f'"{t}"' for t in tokens)
    return (
        "import Foundation\n"
        "\n"
        "// Code generated from contracts/category-acronyms.json by\n"
        "// scripts/generate_category_acronyms.py — do not edit by hand.\n"
        "// #1930: the single shared category-acronym list (native mirror).\n"
        "// Merged into `knownAcronyms` in TextFormatting.swift; platform-local\n"
        "// extras (brands, region codes) stay there.\n"
        "nonisolated let categoryAcronyms: Set<String> = [\n"
        f"    {body},\n"
        "]\n"
    )


def main() -> int:
    tokens = load_authority()
    outputs = [(TS_OUT, render_ts(tokens)), (SWIFT_OUT, render_swift(tokens))]
    if "--check" in sys.argv:
        dirty = [str(p) for p, want in outputs if p.read_text() != want]
        if dirty:
            print("stale mirrors: " + ", ".join(dirty))
            return 2
        print("mirrors in sync")
        return 0
    for path, want in outputs:
        path.write_text(want)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
