#!/usr/bin/env python3
"""UX-P231 mutation battery — is the FENCE actually guarded?

The ship is a scope, not a pattern, so the mutants are all ways of getting the
scope wrong: putting the group back where the ruling took it from, quietly
emptying it, or re-spelling the derived list so it drifts.

Two mutants are SCORED SURVIVORS and are argued rather than hidden — see their
`expect` field. A battery that only lists kills is a battery whose author chose
the mutants after seeing the guard.

Every edit is proven to apply, sources restore inside `finally:`, and the restore
is verified byte-for-byte by sha256.

Run from `frontend/`:  python3 scripts/uxp231_fence_battery.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

LIB = Path("lib/copyBans.ts")

TEST_PATTERN = "noReadingCopyClaims|shippedCopyBans|tournamentPlainLanguage"

FENCED = """export const ALL_COPY_BANS: CopyBan[] = [
  ...JARGON_BANS,
  ...TRADING_VOCAB_BANS,
  ...VENUE_BANS,
  ...FUTURE_PROMISE_BANS,
];"""

DERIVED = """export const NO_READING_COPY_BANS: CopyBan[] = [
  ...ALL_COPY_BANS,
  ...HISTORY_CLAIM_BANS,
];"""

# (id, find, replace, expect, what it models)
MUTANTS: list[tuple[str, str, str, str, str]] = [
    (
        "A",
        FENCED,
        FENCED.replace("  ...FUTURE_PROMISE_BANS,\n", "  ...FUTURE_PROMISE_BANS,\n  ...HISTORY_CLAIM_BANS,\n"),
        "KILL",
        "THE CONDEMNED BYTES: the group back in the codebase-wide list, which is "
        "the state six certs blocked",
    ),
    (
        "B",
        DERIVED,
        DERIVED.replace("  ...HISTORY_CLAIM_BANS,\n", ""),
        "KILL",
        "the fence is empty — the rule silently disabled everywhere while the "
        "export still exists, which is the quietest way to 'close' this subject",
    ),
    (
        "C",
        DERIVED,
        """export const NO_READING_COPY_BANS: CopyBan[] = [
  ...HISTORY_CLAIM_BANS,
];""",
        "KILL",
        "the fenced list drops the codebase-wide groups, so the no-reading "
        "components stop being checked for jargon, price and venue names",
    ),
    (
        "D",
        DERIVED,
        """export const NO_READING_COPY_BANS: CopyBan[] = [
  ...JARGON_BANS,
  ...TRADING_VOCAB_BANS,
  ...VENUE_BANS,
  ...HISTORY_CLAIM_BANS,
];""",
        "KILL",
        "the derived list re-spelled by hand and one group lost in the copy — "
        "the exact drift `concept_sources` and UX-P177's `cycling` paid for",
    ),
    (
        "E",
        "export const HISTORY_CLAIM_BANS: CopyBan[] = [",
        "export const HISTORY_CLAIM_BANS: CopyBan[] = [].concat([",
        "KILL",
        "the group emptied at the source — a re-scope that is really a deletion",
    ),
    (
        "F",
        "export function findBannedCopy(text: string, bans: CopyBan[] = ALL_COPY_BANS)",
        "export function findBannedCopy(text: string, bans: CopyBan[] = NO_READING_COPY_BANS)",
        "KILL",
        "the fence defeated at the DEFAULT argument, so every consumer that does "
        "not name a list is back to the condemned scope",
    ),
    (
        "G",
        "  bans: CopyBan[] = ALL_COPY_BANS\n): BundleCopyHit[] {",
        "  bans: CopyBan[] = NO_READING_COPY_BANS\n): BundleCopyHit[] {",
        "KILL",
        "the same defeat one layer down: the BUNDLE scanner silently re-adopts "
        "the group it cannot scope",
    ),
    (
        "H",
        DERIVED,
        """export const NO_READING_COPY_BANS: CopyBan[] = [
  ...JARGON_BANS,
  ...TRADING_VOCAB_BANS,
  ...VENUE_BANS,
  ...FUTURE_PROMISE_BANS,
  ...HISTORY_CLAIM_BANS,
];""",
        "SURVIVE",
        "SCORED SURVIVOR, ARGUED: the derived list re-spelled by hand but "
        "CORRECTLY. It is identical today and the identity test rightly passes. "
        "The hazard is drift on the NEXT group added, which is a future edit, "
        "not a present defect — mutant D is that future edit and it is killed.",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    return subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    ).returncode


def main() -> int:
    original = LIB.read_text()
    original_sha = sha(LIB)

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    wrong: list[str] = []
    try:
        for mid, find, repl, expect, why in MUTANTS:
            if original.count(find) != 1:
                print(f"{mid}: ANCHOR NOT UNIQUE ({original.count(find)} hits) — battery invalid")
                return 2
            mutated = original.replace(find, repl)
            assert mutated != original, f"{mid}: mutation is a no-op"
            LIB.write_text(mutated)
            assert sha(LIB) != original_sha, f"{mid}: file unchanged on disk"
            assert repl in LIB.read_text(), f"{mid}: mutant text absent after write"

            code = run_guards()
            LIB.write_text(original)
            assert sha(LIB) == original_sha, f"{mid}: restore not byte-identical"

            got = "KILL" if code != 0 else "SURVIVE"
            ok = got == expect
            if not ok:
                wrong.append(mid)
            mark = "OK " if ok else "***"
            print(f"{mark} {mid}: expected {expect}, got {got} (exit {code}) — {why}")
    finally:
        LIB.write_text(original)
        assert sha(LIB) == original_sha, f"RESIDUE: {LIB} not restored"
        print("\nsource restored, sha256 verified")

    killed = sum(1 for m in MUTANTS if m[3] == "KILL")
    print(f"\n{killed} predicted kills, {len(MUTANTS) - killed} scored survivors, "
          f"{len(wrong)} unexpected")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
