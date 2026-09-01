"""UX-P243 — negative control for the CERT-624 repair in `feed_reasons.py`.

Each mutant reverts ONE clause of the repair and must be KILLED by the guard
suite. A mutant that survives means the guard is not testing what it claims.

Two separate assertions per mutant, per UX-P239-4:
  * the file's sha256 CHANGED           -> the edit landed at all;
  * the original text is GONE           -> it landed AS THE MUTATION DESCRIBED,
                                           not merely alongside it.
A malformed replacement that re-emits the anchor passes the first and fails the
second, and would otherwise be scored as a real result.

Run from the backend/ root of an rsync COPY, never the tree a suite is using
(UX-P239-5): stale-copy execution reads as a genuine finding.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

SOURCE = Path("app/utils/feed_reasons.py")
SUITE = "tests/test_feed_reasons_negation_leader.py"

# (label, find, replace)
MUTANTS: list[tuple[str, str, str]] = [
    (
        "M1 the interrogative comes off the QUESTION only (the literal CERT-624 bug)",
        "    restatement_tokens = _comparable_tokens(restatement)\n"
        "    question_tokens = _comparable_tokens(market_name)",
        "    restatement_tokens = _normalized_copy_tokens(restatement)\n"
        "    question_tokens = _comparable_tokens(market_name)",
    ),
    (
        "M2 the interrogative comes off NEITHER side",
        "    restatement_tokens = _comparable_tokens(restatement)\n"
        "    question_tokens = _comparable_tokens(market_name)",
        "    restatement_tokens = _normalized_copy_tokens(restatement)\n"
        "    question_tokens = _normalized_copy_tokens(market_name)",
    ),
    (
        "M3 the interrogative list reverts to the round-1 narrow set",
        r'    r"^(?:will|would|does|do|did|is|are|was|were|can|could|should|has|have|had)\b",'
        "\n    re.IGNORECASE,",
        r'    r"^(?:will|would|does|do|is|are|can)\b", re.IGNORECASE',
    ),
    (
        "M4 mid-word truncation tolerance removed (exact equality on the fragment)",
        "        return question_tokens[head].startswith(restatement_tokens[head])",
        "        return question_tokens[head] == restatement_tokens[head]",
    ),
    (
        "M5 truncation tolerance becomes a WILDCARD (fragment never checked)",
        "        return question_tokens[head].startswith(restatement_tokens[head])",
        "        return True",
    ),
    (
        "M6 the tokens BEFORE the fragment are no longer required to match",
        "        if restatement_tokens[:head] != question_tokens[:head]:\n"
        "            return False\n",
        "",
    ),
    (
        "M7 the whole predicate short-circuits to False (nothing is ever rewritten)",
        "    marker = _NEGATION_PREFIX_RE.match(text)\n    if not marker:",
        "    marker = None\n    if not marker:",
    ),
    (
        "M8 the whole predicate short-circuits to True (everything is rewritten)",
        "    restatement = text[marker.end() :].strip()\n"
        "    if len(restatement) < _MIN_RESTATEMENT_CHARS:\n"
        "        return False\n",
        "    return True\n",
    ),
    (
        "M9 the collapse is dropped at the call site (label passes through)",
        '        return "No"\n    return label',
        "        return label\n    return label",
    ),
    (
        "M10 the truncation marker is never recognised",
        "    if restatement.endswith(_TRUNCATION_MARKER):",
        "    if False:",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "-x", "--no-header"],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout[-400:]


def main() -> int:
    original = SOURCE.read_text()
    original_sha = sha256(SOURCE)

    baseline_rc, baseline_tail = run_suite()
    if baseline_rc != 0:
        print(f"HARNESS FAULT: the unmutated suite is not green (exit {baseline_rc}).")
        print(baseline_tail)
        return 2
    print(f"baseline: suite GREEN on unmutated source (sha {original_sha[:12]})\n")

    killed = survived = malformed = 0
    for label, find, replace in MUTANTS:
        if find not in original:
            print(f"MALFORMED  {label}\n           anchor not present in source")
            malformed += 1
            continue

        SOURCE.write_text(original.replace(find, replace, 1))

        # (a) it applied at all, and (b) it applied AS DESCRIBED.
        if sha256(SOURCE) == original_sha:
            print(f"MALFORMED  {label}\n           sha unchanged: edit did not land")
            malformed += 1
            SOURCE.write_text(original)
            continue
        if find in SOURCE.read_text():
            print(f"MALFORMED  {label}\n           anchor still present after edit")
            malformed += 1
            SOURCE.write_text(original)
            continue

        rc, tail = run_suite()
        SOURCE.write_text(original)

        if rc == 0:
            print(f"SURVIVED   {label}   <-- THE GUARD DOES NOT COVER THIS")
            survived += 1
        elif rc == 1:
            print(f"killed     {label}")
            killed += 1
        else:
            print(f"HARNESS FAULT ({rc})  {label}\n{tail}")
            malformed += 1

    if sha256(SOURCE) != original_sha:
        print("\n🔴 SOURCE NOT RESTORED — do not trust this run.")
        return 2

    print(
        f"\nkilled {killed}/{len(MUTANTS)}  survived {survived}  malformed {malformed}"
    )
    print(f"source restored, sha256 identical: {original_sha[:12]}")
    return 0 if survived == 0 and malformed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
