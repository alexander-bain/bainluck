#!/usr/bin/env python3
"""UX-P247 mutation battery — is the FENCE guarded, and is the LITERAL LIST real?

Two ships in one file, so two families of mutant.

UX-P231's ship was a SCOPE, and A-H are all ways of getting the scope wrong:
putting the group back where the ruling took it from, quietly emptying it, or
re-spelling the derived list so it drifts. Those are unchanged except where the
source moved under them.

UX-P247's ship (Alex, "COPY BAN", 2026-09-01) is that the group is a LITERAL
LIST and not a classifier, so I-N attack the two ways THAT can be wrong:

  * the list stops holding the sentences we served (I, J, K) — a regression
    guard that has quietly stopped guarding;
  * the list grows back toward a classifier (L, M, N) — a literal loosened into
    a pattern, or copied a shade too long so it bans the repair.

⚠️ L IS THE ONE WORTH READING. It widens `comparison-was-never-complete` by four
characters, to `this comparison was never complete` → `this comparison was`,
which still kills the condemned sentence and ALSO bans the sentence shipping
today. A battery that only checked "does the condemned sentence still fail"
would score it a kill and call the loosening safe.

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
  ...PRICE_FORMAT_BANS,
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
        "export const HISTORY_CLAIM_BANS: CopyBan[] = HISTORY_CLAIM_LITERALS.map(literalBan);",
        "export const HISTORY_CLAIM_BANS: CopyBan[] = [];",
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
  ...PRICE_FORMAT_BANS,
  ...HISTORY_CLAIM_BANS,
];""",
        "SURVIVE",
        "SCORED SURVIVOR, ARGUED: the derived list re-spelled by hand but "
        "CORRECTLY. It is identical today and the identity test rightly passes. "
        "The hazard is drift on the NEXT group added, which is a future edit, "
        "not a present defect — mutant D is that future edit and it is killed.",
    ),
    # ── UX-P247: the LITERAL LIST. Half attack it going empty, half attack it
    #    growing back into the classifier it replaced. ──
    (
        "I",
        '    literal: "No number ever reached us for",',
        '    literal: "No number ever reached us from",',
        "KILL",
        "the oldest condemned sentence stops being held — one preposition, and "
        "the list silently no longer covers the sentence CERT-537 was about",
    ),
    (
        "J",
        '    literal: "this comparison was never complete",',
        '    literal: "this comparison was never finished",',
        "KILL",
        "the TAIL of the same sentence stops being held. Its own mutant because "
        "the HEAD still fires on the full sentence, so a test asserting only "
        "'something fired' would score this a survivor",
    ),
    (
        "K",
        '    literal: "No number has reached us for",',
        '    literal: "No number has reached us toward",',
        "KILL",
        "the open-tense twin stops being held — the entry this change ADDED "
        "against the old suite's advice, so it is the one most likely to be "
        "quietly reverted by a reader who finds the old comment first",
    ),
    (
        "L",
        '    literal: "this comparison was never complete",',
        '    literal: "this comparison",',
        "KILL",
        "\U0001f534 THE LITERAL LOOSENED INTO A PATTERN. Still kills the condemned "
        "sentence \u2014 and also bans 'so this comparison is not complete', the copy "
        "on production RIGHT NOW. This is the only failure mode a literal list "
        "has, and only the shipping-today pins can see it. \u26a0\ufe0f FIRST DRAFT WAS "
        "'this comparison was', which SURVIVED: it is a loosening that happens "
        "to miss today's copy, so it modelled nothing. A survivor for the wrong "
        "reason is a broken mutant, not a finding.",
    ),
    (
        "M",
        '  return literal.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");',
        "  return literal;",
        "SURVIVE",
        "SCORED SURVIVOR, ARGUED: escaping stops, and no current literal holds a "
        "regex metacharacter, so nothing changes today. It is a real latent "
        "hazard the moment somebody adds a sentence ending in a full stop — and "
        "a mutant that cannot fail today should be SAID to be that rather than "
        "dressed up as a kill. N is what actually guards it.",
    ),
    (
        "N",
        '    literal: "No number ever reached us for",',
        '    literal: "No number ever reach.d us for",',
        "KILL",
        "N IS WHAT MAKES M SAFE: a metacharacter inside a literal. WITH escaping "
        "the '.' is a full stop and the entry stops matching, so the guard goes "
        "red. WITHOUT escaping the '.' is a wildcard and the entry still fires. "
        "So this kill is the proof that escaping is load-bearing on exactly the "
        "property M would break",
    ),
    (
        "O",
        '    seen: "a227c5c4 (UX-P211), replaced by fa8abe08 (UX-P212) after CERT-537",\n    why: "quantifies over all of history',
        '    seen: "because it felt like a claim somebody might make",\n    why: "quantifies over all of history',
        "KILL",
        "provenance replaced by a worry — the bar for adding a line. This is the "
        "accumulation route back to the classifier: one plausible paraphrase at "
        "a time, each added by somebody who was sure",
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
