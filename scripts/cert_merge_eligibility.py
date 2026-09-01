#!/usr/bin/env python3
"""Which cert-granted commits are ACTUALLY merge-eligible right now.

Channel one of the Integrator's two-channel sweep. Channel two is
``scripts/sweep_ready_tokens.py`` (ruling 109), which reads the ``READY-*``
tokens. This reads ``CODEX-CERT-LOG.md``, which is the merge authority.

WHY THIS IS A SCRIPT AND NOT A PARAGRAPH
========================================
The same three mistakes have been made by consecutive Integrators, each one
recorded in a handoff file and then re-made by the next window because a
paragraph is not a check:

1. **A GREEN grant is not authority. The LATEST verdict on the bytes is.**
   INT-196 merged ``lane1/q473`` on ``CERT-564 -- GREEN, token granted for
   7f3bad02``. Nine hours after that green, ``CERT-617`` graded the *same sha*
   **BLOCK -- TOKEN WITHHELD**: the widened 300-second collapse suppressed the
   only ``live`` row and kept the richer ``scheduled`` one. A scan that stops
   at "is there a green?" merges a ship the cert bus has already rejected, and
   it looks like diligence while doing it. The merge was caught and reverted
   before it was pushed. It should not have depended on someone remembering.

2. **Bare shas.** The grant sentence is written by hand and its shape drifts:
   ``Token granted for `abc1234` ``, ``Token granted for abc1234 against ...``,
   ``@ abc1234``. INT-193 widened a tight regex to "backticked"; CERT-589 wrote
   no backticks and was lost anyway. Three consecutive cycles lost three
   different ships to three shapes of one regex. So: take EVERY word-bounded
   hex run and over-report. Adjudicating a false hit costs a minute.

3. **Supersession by rebase is invisible to a sha sweep.** A branch that is
   rebased and re-certified lands under a *different* sha, so the original
   grant's sha is forever "granted and unmerged" while its content is shipped.
   Those rows are noise, but they are indistinguishable from real work until
   someone checks the content — which is why they are REPORTED here rather
   than filtered out. An unexplained row is the point; a hidden one is a trap.

Exit status is 0 when there is nothing to merge and 1 when at least one commit
is eligible, so a runner can branch on it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field

CERT_LOG = ".claude/handoff/CODEX-CERT-LOG.md"

# Deliberately NOT anchored on backticks or on the word "granted" — see reason 2.
SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b")
CERT_ID_RE = re.compile(r"\|\s*(CERT-\d+)")


@dataclass
class Verdict:
    """One banked cert row. ``order`` is file position, which is chronological."""

    order: int
    cert_id: str
    date: str
    granted: bool
    shas: set[str] = field(default_factory=set)


def _git(repo: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout.strip()


def read_verdicts(repo: str) -> list[Verdict]:
    """Every row in the cert log that carries a token verdict, in file order."""
    with open(f"{repo}/{CERT_LOG}", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")

    verdicts = []
    for order, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        granted = "TOKEN GRANTED" in line
        if not granted and "TOKEN WITHHELD" not in line:
            continue
        cert_id = CERT_ID_RE.match(stripped)
        columns = line.split("|")
        verdicts.append(
            Verdict(
                order=order,
                cert_id=cert_id.group(1) if cert_id else "(unnumbered)",
                date=columns[2].strip() if len(columns) > 2 else "?",
                granted=granted,
                shas=set(SHA_RE.findall(line)),
            )
        )
    return verdicts


def eligible(repo: str, base: str = "origin/master") -> tuple[list, list]:
    """Split granted-and-unmerged shas into (eligible, overturned).

    A sha is eligible when the LATEST verdict row mentioning it is a grant.
    """
    verdicts = read_verdicts(repo)

    candidates = set()
    for verdict in verdicts:
        if not verdict.granted:
            continue
        for sha in verdict.shas:
            if _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
                continue  # a tree hash, a base sha, or a commit we do not have
            if _git(repo, "merge-base", "--is-ancestor", sha, base)[0] == 0:
                continue  # already shipped
            candidates.add(sha)

    good, overturned = [], []
    for sha in sorted(candidates):
        chain = [v for v in verdicts if sha in v.shas]
        latest = max(chain, key=lambda v: v.order)
        (good if latest.granted else overturned).append((sha, chain, latest))
    return good, overturned


def _render(sha: str, chain: list[Verdict], latest: Verdict) -> str:
    out = [f"  {sha[:9]}"]
    for verdict in chain:
        mark = "GREEN" if verdict.granted else "BLOCK"
        out.append(f"     {verdict.cert_id:<10} {verdict.date:<22} {mark}")
    out.append(
        f"     => LATEST {latest.cert_id} "
        f"{'GREEN' if latest.granted else 'BLOCK'}"
    )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/master")
    args = parser.parse_args()

    good, overturned = eligible(args.repo, args.base)

    print(f"cert merge eligibility — against {args.base}")
    print(
        "Every granted sha not yet on master, with its FULL verdict chain. "
        "The latest verdict decides."
    )

    if overturned:
        print(f"\n── OVERTURNED ({len(overturned)}) — a later BLOCK on the same bytes. DO NOT MERGE.")
        for sha, chain, latest in overturned:
            print(_render(sha, chain, latest))

    if not good:
        print("\n── ELIGIBLE (0) — nothing to merge.")
        print(
            "\nAn integrator cycle that pushes nothing is a real outcome. Note that rows "
            "here can still be supersession-by-rebase noise: the branch was rebased and "
            "re-certified under a different sha, so the original grant reads unmerged "
            "forever. Adjudicate by CONTENT before calling one owed."
        )
        return 0

    print(f"\n── ELIGIBLE ({len(good)}) — latest verdict is a grant, sha not on master.")
    for sha, chain, latest in good:
        print(_render(sha, chain, latest))
    print(
        "\nEligible is not merged. Each still needs: the READY token to resolve to this "
        "exact head (ruling 085 — a moved head withdraws it), the never-merge closure "
        "(ruling 109), re-gating on the materialised merge if master moved, and the "
        "Integrator lock (ruling 017)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
