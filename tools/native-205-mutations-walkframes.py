#!/usr/bin/env python3
"""native/205 — mutation battery for the walk rig's no-op frame guard.

Each mutant rewrites `frame_check` in `tools/native-walk.sh` and asks whether
that script's own `--selftest` notices. A mutant the selftest does not notice is
a hole in the guard, not a curiosity.

WHY THIS BATTERY CAN BE HONEST ABOUT ITS OWN SUBJECT. The thing under test is a
PURE function and `--selftest` drives that same function — not a copy of it — so
a mutant applied to the shipped file is graded by the shipped rule. That is the
whole reason the guard was written in the house `--selftest` shape
(`tools/native-gates.sh`) instead of as a separate test that restates the logic.

THE MUTANT THIS BATTERY EXISTS FOR IS M6. A no-op guard has one failure mode
that matters and it is not "it misses a twin" — it is "it calls everything a
twin", because that fails CLOSED and looks like diligence. A rig that refuses
every frame stops the walk on its first honest shot. Only the `new frame`
control in the selftest can catch that, and M6 is what proves that control is
load-bearing rather than decorative.

This battery mutates a COPY in a temp directory and never touches the worktree,
so it cannot leave a dirty tree behind if it is killed mid-run — the failure
native/205's own restock warned about.

Usage:  python3 -u tools/native-205-mutations-walkframes.py
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = REPO / "tools" / "native-walk.sh"

# (name, needle, replacement, what it breaks, the selftest case that must redden)
MUTANTS = [
    (
        "M1 hash comparison removed",
        '    [ "$_h" = "$_fc_hash" ] || continue\n',
        "",
        "every ledger row matches, so the first row is always the twin",
        "new frame",
    ),
    (
        "M2 same-path exemption removed",
        '    [ "${_q:-}" = "$_fc_path" ] && continue\n',
        "",
        "a re-shoot of one path becomes a twin of itself",
        "re-shoot of same path",
    ),
    (
        "M3 same/other walk collapsed",
        '    if [ "$_p" = "$_fc_params" ]; then\n'
        "      FRAME_VERDICT=DUP_SAME_WALK\n"
        "    else\n"
        "      FRAME_VERDICT=DUP_OTHER_WALK\n"
        "    fi\n",
        "    FRAME_VERDICT=DUP_OTHER_WALK\n",
        "a before/after filed twice is reported as a dead scroll",
        "twin, same walk",
    ),
    (
        "M4 matched on path instead of frame",
        '    [ "$_h" = "$_fc_hash" ] || continue\n',
        '    [ "$_q" = "$_fc_path" ] || continue\n',
        "the same frame under another name stops being a twin",
        "twin under another dir",
    ),
    (
        "M5 guard gutted, always NEW",
        '  [ -f "$_fc_ledger" ] || return 0\n',
        "  return 0\n",
        "the guard never fires at all — the pre-2026-09-17 behaviour",
        "twin, different route",
    ),
    (
        "M6 guard refuses everything",
        "  FRAME_VERDICT=NEW; FRAME_TWIN=\"\"; FRAME_TWIN_PARAMS=\"\"\n",
        '  FRAME_VERDICT=DUP_OTHER_WALK; FRAME_TWIN="?"; FRAME_TWIN_PARAMS="?"\n',
        "fails closed on every frame and halts the walk on its first honest shot",
        "new frame",
    ),
    (
        "M7 params ignored when classifying",
        '    if [ "$_p" = "$_fc_params" ]; then\n',
        '    if [ "$_p" != "$_fc_params" ]; then\n',
        "the two verdicts are swapped, so each diagnosis names the wrong cause",
        "twin, same walk",
    ),
]


def run_selftest(script: Path):
    """Return (exit_code, stdout). The selftest prints one line per case."""
    proc = subprocess.run(
        ["bash", str(script), "--selftest"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    if not TARGET.exists():
        print(f"BATTERY FAULT: {TARGET} not found")
        return 2

    source = TARGET.read_text()

    # The baseline must be GREEN, or every "kill" below is just a broken script.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "native-walk.sh"
        base.write_text(source)
        code, out = run_selftest(base)
        if code != 0:
            print("BATTERY FAULT: the UNMUTATED selftest is already red.\n")
            print(out)
            return 2
        baseline_cases = re.findall(r"^  ok    (\S.*?)\s*->", out, re.M)
        print(f"baseline: selftest GREEN, {len(baseline_cases)} cases\n")

    killed = 0
    for name, needle, replacement, breaks, expect_case in MUTANTS:
        occurrences = source.count(needle)
        if occurrences == 0:
            print(f"  BATTERY FAULT  {name}: NEEDLE-NOT-FOUND — grading nothing")
            continue
        if occurrences > 1:
            print(f"  BATTERY FAULT  {name}: needle matches {occurrences}x — grading code nobody chose")
            continue

        with tempfile.TemporaryDirectory() as td:
            mutant = Path(td) / "native-walk.sh"
            mutant.write_text(source.replace(needle, replacement))

            # A mutant must still be a valid script; a syntax error would redden
            # the selftest for a reason that has nothing to do with the rule.
            syn = subprocess.run(["bash", "-n", str(mutant)], capture_output=True, text=True)
            if syn.returncode != 0:
                print(f"  BATTERY FAULT  {name}: mutant does not parse — {syn.stderr.strip()}")
                continue

            code, out = run_selftest(mutant)

        if code == 0:
            print(f"  SURVIVED  {name}")
            print(f"            breaks: {breaks}")
            print("            the selftest passed anyway — this is a HOLE")
            continue

        # A kill is not enough: the RIGHT case must be the one that reddened,
        # otherwise the battery is crediting an accident.
        reddened = re.findall(r"^  FAIL  (\S.*?)\s*->", out, re.M)
        reddened = [c.strip() for c in reddened]
        if expect_case not in reddened:
            print(f"  MIS-KILL  {name}: died, but on {reddened or '<no named case>'},")
            print(f"            not on the case that owns it ({expect_case!r})")
            continue

        killed += 1
        print(f"  killed    {name}")
        print(f"            by: {expect_case}  (breaks: {breaks})")

    print(f"\n{killed}/{len(MUTANTS)} mutants killed by the case that owns each one")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
