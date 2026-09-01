#!/usr/bin/env python3
"""UX-P239 mutation battery — does the guard catch the defect class, or two cards?

The ship: a Discover card's explanation never takes the No-side restatement of
the card's own question as its grammatical subject. Each mutant below is a
plausible way to get that wrong, in two families:

  * the PREDICATE is wrong  (A, B, C, D, E, K) — it fires on the wrong labels,
    or stops firing on the two live specimens;
  * the predicate is right and a CALL SITE was missed  (F, G, H, I) — the shape
    a predicate-only test cannot see, and the shape CERT-606 and CERT-610 both
    blocked this lane for in the last two days.

For every mutant we PROVE the edit applied (sha changed AND the original text is
gone from disk), run the guards, and require a non-zero exit. Sources are
restored inside `finally:` and the restore is verified byte-for-byte by sha256 —
UX-P210 stranded a mutant for want of exactly that.

⚠️ `__pycache__` is cleared around every run. A stale `.pyc` makes a mutant look
like it never applied and produces phantom results in both directions.

⚠️ Never run this while another pytest is in flight in this worktree — a source
edit under a running collector produces phantom failures that belong to neither
tree.

Run from `backend/`:  python3 scripts/uxp239_mutation_battery.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

REASONS = Path("app/utils/feed_reasons.py")
TARGETS = (REASONS,)

TESTS = [
    "tests/test_feed_reasons_negation_leader.py",
    "tests/test_feed_reasons.py",
    "tests/test_feed_card_probability_authority.py",
    "tests/test_futures_highlights.py",
]

# (id, file, find, replace, what it models)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "A",
        REASONS,
        '    if _negates_market_question(label, market_name):\n        return "No"\n    return label',
        "    return label",
        "the whole ship as a no-op: the predicate is computed and discarded",
    ),
    (
        "B",
        REASONS,
        '    restatement = text[marker.end() :].strip()\n    if len(restatement) < _MIN_RESTATEMENT_CHARS:\n        return False\n\n    restatement_tokens = _normalized_copy_tokens(restatement)\n    question_tokens = _normalized_copy_tokens(market_name)\n    if question_tokens and _LEADING_INTERROGATIVE_RE.match((market_name or "").strip()):\n        question_tokens = question_tokens[1:]\n    if not restatement_tokens or not question_tokens:\n        return False\n\n    # Prefix-tolerant in BOTH directions: either side may be the truncated one.\n    shorter, longer = sorted((restatement_tokens, question_tokens), key=len)\n    return longer[: len(shorter)] == shorter',
        "    return True",
        "the restatement test dropped for a bare prefix regex — the 'No change' "
        "false positive this predicate exists to prevent",
    ),
    (
        "C",
        REASONS,
        "    if len(restatement) < _MIN_RESTATEMENT_CHARS:\n        return False\n",
        "",
        "the minimum-restatement floor removed: a one-or-two-letter remainder "
        "buys a rewrite",
    ),
    (
        "D",
        REASONS,
        '    if question_tokens and _LEADING_INTERROGATIVE_RE.match((market_name or "").strip()):\n        question_tokens = question_tokens[1:]\n',
        "",
        "the leading interrogative left in place — 'will' becomes the question's "
        "first token and BOTH live specimens stop matching",
    ),
    (
        "E",
        REASONS,
        "    shorter, longer = sorted((restatement_tokens, question_tokens), key=len)\n    return longer[: len(shorter)] == shorter",
        "    return restatement_tokens == question_tokens",
        "prefix tolerance replaced by exact equality — the 40-char truncation "
        "that produced both specimens defeats it",
    ),
    (
        "K",
        REASONS,
        '    if _negates_market_question(label, market_name):\n        return "No"',
        '    if _negates_market_question(label, market_name):\n        return "Yes"',
        "the right side detected and the WRONG one named — the inversion this "
        "ship exists to remove, reintroduced one word over",
    ),
    (
        "J",
        REASONS,
        r'_NEGATION_PREFIX_RE = re.compile(r"^\s*(?:no|not)\s*[:\-–—]?\s+", re.IGNORECASE)',
        r'_NEGATION_PREFIX_RE = re.compile(r"^\s*(?:no|not)\s*[:\-–—]?\s*", re.IGNORECASE)',
        "the separator requirement loosened to `\\s*` — 'Norway' and 'No. 1 seed' "
        "parse as negations of something",
    ),
    (
        "F",
        REASONS,
        "    # Same single point as `generate_futures_reason`, and before the closure\n    # below captures it.\n    leader_name = _answering_side_label(leader_name, market_name)\n",
        "",
        "CALL SITE MISSED: `generate_futures_context_summary` — the exact field "
        "both live cards served the defect in",
    ),
    (
        "G",
        REASONS,
        "    leader_name = _answering_side_label(leader_name, market_name)\n    top_mover_name = _answering_side_label(top_mover_name, market_name)\n    top_surprise_name = _answering_side_label(top_surprise_name, market_name)\n\n    if \"stale_past_resolution\" in reasons:\n        return \"\"\n\n    # Leader change (most interesting)",
        '    if "stale_past_resolution" in reasons:\n        return ""\n\n    # Leader change (most interesting)',
        "CALL SITE MISSED: `generate_futures_reason` — the `reason` field",
    ),
    (
        "H",
        REASONS,
        "    leader_name = _answering_side_label(leader_name, market_name)\n    top_mover_name = _answering_side_label(top_mover_name, market_name)\n    top_surprise_name = _answering_side_label(top_surprise_name, market_name)\n\n    if \"stale_past_resolution\" in reasons:\n        return \"\"\n\n    if \"leader_change\" in reasons:",
        '    if "stale_past_resolution" in reasons:\n        return ""\n\n    if "leader_change" in reasons:',
        "CALL SITE MISSED: `generate_futures_headline` — the compact card text",
    ),
    (
        "I",
        REASONS,
        "    top_mover_name = _answering_side_label(top_mover_name, market_name)\n    top_surprise_name = _answering_side_label(top_surprise_name, market_name)\n\n    if \"stale_past_resolution\" in reasons:\n        return \"\"\n\n    # Leader change (most interesting)",
        '    if "stale_past_resolution" in reasons:\n        return ""\n\n    # Leader change (most interesting)',
        "ARGUMENT MISSED: only `leader_name` normalized, so the identical defect "
        "stays reachable through the movement branches",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clear_pycache() -> None:
    for d in Path("app").rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run_guards() -> int:
    clear_pycache()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS, "-q", "--no-header"],
        capture_output=True,
        text=True,
    )
    clear_pycache()
    return proc.returncode


def main() -> int:
    originals = {p: p.read_text() for p in TARGETS}
    original_shas = {p: sha(p) for p in TARGETS}

    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    try:
        for mid, path, find, repl, why in MUTANTS:
            src = originals[path]
            if src.count(find) != 1:
                print(
                    f"{mid}: ANCHOR NOT UNIQUE in {path} "
                    f"({src.count(find)} hits) — battery invalid"
                )
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            # Prove it applied: the file on disk differs, and it differs the way
            # the mutant says. A no-op mutant that "survives" is a broken mutant,
            # not a finding about the guard.
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"
            assert find not in path.read_text(), f"{mid}: original text still present"

            code = run_guards()
            path.write_text(src)
            assert sha(path) == original_shas[path], f"{mid}: restore not byte-identical"

            if code != 0:
                killed.append(mid)
                print(f"{mid}: KILLED (exit {code}) — {why}")
            else:
                survived.append(mid)
                print(f"{mid}: *** SURVIVED *** — {why}")
    finally:
        for path, src in originals.items():
            path.write_text(src)
            assert sha(path) == original_shas[path], f"RESIDUE: {path} not restored"
        clear_pycache()
        print("\nall sources restored, sha256 verified")

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print(f"SURVIVORS: {', '.join(survived)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
