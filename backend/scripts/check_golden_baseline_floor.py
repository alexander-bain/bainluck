#!/usr/bin/env python3
"""#3564: refuse a golden baseline whose floor drops without naming what fell.

WHY THIS EXISTS. ``matching_golden_baseline.json`` is a whole-file generated
artifact. When two branches both regenerate it, git has no way to tell a
deliberate re-derivation from a silent revert: the merged blob is simply one
side's file. On 2026-09-06 integrator/239 caught exactly this by hand -- a
branch carrying ``passing_count: 665`` over master's ``668``, with **no
conflict, no reviewable diff line, and ``git merge-tree`` exit 0**. The
regression was real and the textual gate could not see it. It had to be read by
hand a second time on the repaired branch to confirm the drop was then honest.

This automates that read. It is deliberately NOT "the floor may never fall":
lowering it is legitimate when the REPLAY HARNESS changes (a re-capture at a new
candidate cap re-asks the question, so some pairs genuinely stop passing). What
is never legitimate is lowering it *silently*. So there are two rules, and the
second is the one the bounce actually needed:

    1. every pair that stops passing is named, by market id, in reset_reason;
    2. a drop names the target's own floor, proving it was measured against the
       floor of record and not against a stale branch point.

CERT-2152 satisfied (1) -- it named all eight fallen pairs -- and failed (2): it
was re-derived on its branch point's 649 and reported "649 -> 665, no
regressions" while replacing master's 668. Both are claims a reader can falsify.
"665 is the honest number" is not.

    python3 scripts/check_golden_baseline_floor.py                  # vs origin/master
    python3 scripts/check_golden_baseline_floor.py --target master
    python3 scripts/check_golden_baseline_floor.py --proposed <sha>  # a merged tree

Exit codes follow gotcha #124 -- ``1`` is a result, anything else is a story
about the harness: 0 = accept, 1 = floor moved without naming what moved,
2 = a ref or blob could not be read (the check never ran; do NOT read that as a
pass).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
#: Path inside the git tree, i.e. relative to the repository root, not backend/.
BLOB_PATH = "backend/tests/fixtures/matching_golden_baseline.json"
WORKTREE_PATH = REPO_ROOT / "tests" / "fixtures" / "matching_golden_baseline.json"


class BlobUnreadable(Exception):
    """A ref or blob could not be resolved -- the comparison never happened."""


@dataclass
class Verdict:
    ok: bool
    #: Pairs passing in the target that do not pass in the proposal.
    fell: list[str] = field(default_factory=list)
    #: Pairs passing in the proposal that did not pass in the target.
    rose: list[str] = field(default_factory=list)
    #: Pairs the target adjudicated that the proposal drops entirely.
    dropped: list[str] = field(default_factory=list)
    #: Pairs the proposal adds to the corpus.
    added: list[str] = field(default_factory=list)
    target_passing: int = 0
    proposed_passing: int = 0
    problems: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"target   passing {self.target_passing}",
            f"proposed passing {self.proposed_passing} "
            f"({self.proposed_passing - self.target_passing:+d})",
            f"fell {len(self.fell)} · rose {len(self.rose)} · "
            f"dropped {len(self.dropped)} · added {len(self.added)}",
        ]
        if self.fell:
            lines.append("  fell:    " + " ".join(self.fell))
        if self.rose:
            lines.append("  rose:    " + " ".join(self.rose))
        if self.dropped:
            lines.append("  dropped: " + " ".join(self.dropped))
        if self.problems:
            lines.append("")
            lines.extend(self.problems)
        return "\n".join(lines)


def _passing(baseline: dict) -> set[str]:
    return {k for k, v in baseline.get("pairs", {}).items() if v}


def _names_number(text: str, number) -> bool:
    """Is ``number`` present in ``text`` as a standalone run of digits?

    Word-anchored on purpose. A plain substring test reads ``668`` inside the
    market id ``59700668`` and a floor drop then certifies itself -- the same
    false positive that made a loose ``supersedes`` grep hit the string
    ``362146`` during a merge gate.
    """
    return re.search(rf"(?<!\d){re.escape(str(number))}(?!\d)", text) is not None


def _check_self_consistent(baseline: dict, which: str) -> list[str]:
    """A header that disagrees with its own body cannot be ratcheted against.

    ``passing_count`` and ``pair_count`` are labels the fixture writes ABOUT
    itself. A partial regeneration can leave either one describing the previous
    body, and then every comparison below is against a number nobody measured.
    Same defect class as the capture cap: never trust a self-description you can
    recompute.
    """
    problems = []
    pairs = baseline.get("pairs")
    if not isinstance(pairs, dict) or not pairs:
        return [f"{which} baseline has no `pairs` map -- nothing to compare"]
    counted = sum(1 for v in pairs.values() if v)
    if baseline.get("passing_count") != counted:
        problems.append(
            f"{which} baseline is internally inconsistent: passing_count says "
            f"{baseline.get('passing_count')} but {counted} pairs are true. "
            "Re-record it before comparing -- the header describes a body that "
            "is not there."
        )
    if baseline.get("pair_count") != len(pairs):
        problems.append(
            f"{which} baseline is internally inconsistent: pair_count says "
            f"{baseline.get('pair_count')} but the map holds {len(pairs)} pairs."
        )
    return problems


def compare_baselines(target: dict, proposed: dict) -> Verdict:
    """Decide whether ``proposed`` may replace ``target``.

    Pure: no git, no filesystem, no clock. Everything the CLI decides, it
    decides here, so the rule is testable against real recorded blobs.

    The gate is PER PAIR, not on the headline count. Eight pairs falling while
    eight others rise leaves ``passing_count`` unchanged and is exactly as much
    of a regression as a visible drop -- the aggregate is merely the part that
    is easy to eyeball.
    """
    problems: list[str] = []
    problems += _check_self_consistent(target, "target")
    problems += _check_self_consistent(proposed, "proposed")
    if problems:
        # Comparing two blobs when one misdescribes itself produces a confident
        # wrong answer, which is worse than refusing.
        return Verdict(
            ok=False,
            target_passing=len(_passing(target)),
            proposed_passing=len(_passing(proposed)),
            problems=problems,
        )

    t_pairs, p_pairs = target["pairs"], proposed["pairs"]
    t_pass, p_pass = _passing(target), _passing(proposed)

    dropped = sorted(set(t_pairs) - set(p_pairs))
    added = sorted(set(p_pairs) - set(t_pairs))
    # A pair the proposal drops entirely cannot "fall" -- it is a corpus change,
    # reported on its own line so the two are never conflated.
    fell = sorted((t_pass & set(p_pairs)) - p_pass)
    rose = sorted((p_pass - set(added)) - t_pass)

    verdict = Verdict(
        ok=True,
        fell=fell,
        rose=rose,
        dropped=dropped,
        added=added,
        target_passing=len(t_pass),
        proposed_passing=len(p_pass),
    )

    reason = proposed.get("reset_reason") or ""
    must_name = fell + [m for m in dropped if m in t_pass]

    # THE CATCH THAT MATTERS, and the one the CERT-2152 bounce actually needed.
    # That blob DID name all eight fallen pairs -- naming alone would have let
    # it through. Its real defect was the floor it measured itself against: it
    # was re-derived on its own stale branch point (649) and reported
    # "649 -> 665, no regressions" while replacing master's 668. The pairs it
    # named were the ones that fell against 649.
    #
    # So a drop must also acknowledge the target's own number. Recomputing
    # fell/rose here already ignores the proposal's narrative; this makes the
    # narrative itself falsifiable, and costs no schema change.
    if verdict.proposed_passing < verdict.target_passing and not _names_number(
        reason, verdict.target_passing
    ):
        verdict.problems.append(
            f"the floor drops {verdict.target_passing} -> "
            f"{verdict.proposed_passing}, but `reset_reason` never mentions "
            f"{verdict.target_passing}, the floor it is replacing. A baseline "
            "re-derived on a stale branch point reports a RISE against a number "
            "nobody is defending -- that is the CERT-2152 bounce exactly. State "
            f"the target's floor ({verdict.target_passing}) in the reason, and "
            "re-record on top of the target if you have not."
        )

    if must_name:
        unnamed = [m for m in must_name if not _names_number(reason, m)]
        if not reason:
            verdict.problems.append(
                f"{len(must_name)} golden pair(s) stop passing and the proposed "
                "baseline carries no `reset_reason`. A whole-file generated "
                "artifact merges without a conflict, so this drop would land "
                "invisibly (#3564, the CERT-2152 bounce). Re-record with "
                "`scripts/matching_golden_baseline.py --reset '<why>'` and name "
                "every pair below in the reason:\n    " + " ".join(must_name)
            )
        elif unnamed:
            verdict.problems.append(
                f"{len(unnamed)} of {len(must_name)} pair(s) that stop passing "
                "are not named in `reset_reason`. A reason that does not name "
                "them is not falsifiable -- a reader cannot tell a deliberate "
                "re-derivation from a silent revert:\n    " + " ".join(unnamed)
            )

    verdict.ok = not verdict.problems
    return verdict


def read_blob(ref: str | None) -> dict:
    """Load the baseline from a git ref, or from the working tree when None."""
    if ref is None:
        try:
            return json.loads(WORKTREE_PATH.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BlobUnreadable(f"working tree {WORKTREE_PATH}: {exc}") from exc
    try:
        proc = subprocess.run(
            ["git", "show", f"{ref}:{BLOB_PATH}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    except OSError as exc:  # git absent, or cwd gone
        raise BlobUnreadable(f"could not run git: {exc}") from exc
    if proc.returncode != 0:
        raise BlobUnreadable(
            f"`git show {ref}:{BLOB_PATH}` exited {proc.returncode}: "
            f"{proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BlobUnreadable(f"{ref}:{BLOB_PATH} is not valid JSON: {exc}") from exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--target",
        default="origin/master",
        help="the ref whose floor is being defended (default: origin/master)",
    )
    ap.add_argument(
        "--proposed",
        default=None,
        metavar="REF",
        help="the ref to judge; omit to judge the working tree. Point this at a "
        "locally merged tree to reproduce the merge desk's read.",
    )
    args = ap.parse_args()

    try:
        target = read_blob(args.target)
        proposed = read_blob(args.proposed)
    except BlobUnreadable as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        print(
            "The comparison did NOT run. Do not read this as a pass.",
            file=sys.stderr,
        )
        return 2

    verdict = compare_baselines(target, proposed)
    print(f"target   = {args.target}")
    print(f"proposed = {args.proposed or '(working tree)'}")
    print(verdict.report())
    print()
    print("ACCEPT: the floor is defended" if verdict.ok else "REFUSE: see above")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
