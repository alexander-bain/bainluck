#!/usr/bin/env python3
"""Flip lane queue entries to `merged` — keyed on BRANCH HEADS, never on text.

INT-038 wrote a flip step that matched any handoff file *mentioning* a landed
queue id, and it wrongly marked UX-P052 `merged` while UX-P052 was still
unmerged. It was reverted in ~2 minutes, but the class is expensive: **the
ready-set is the Integrator's work queue**, so a falsely-`merged` entry makes
real work invisible, and a falsely-`ready` one makes the Integrator
content-verify a list of ghosts. INT-034 spent a whole cycle undoing exactly
that drift — 15 `ready_for_integration` entries of which 0 were real.

The fix is to stop matching prose. A queue file DECLARES the branch and head it
was built from::

    completed: ... program/ux-38 @ 130d8d1c (base origin/master 10968d84) ...
    branch: program/ux-39

So the question "did this queue land?" has an answer that does not involve
reading English: **take the head SHA the file declares, and ask git whether its
CONTENT is on master.** That is checkable, and it is wrong in a way that shows
up immediately rather than a cycle later.

Content, not ancestry, because a cherry-picked or rebased commit lands under a
different SHA — `git branch --merged` says NOT merged even when the work is
there (the patch-id lesson). We compare the branch's tree-level diff against
master instead: if every file the commit added or changed matches master's
content, it landed.

Usage::

    python3 scripts/flip_merged_queues.py --dry-run
    python3 scripts/flip_merged_queues.py --apply --landed 130d8d1c=3b793509 ...

``--landed OLD=NEW`` records where a declared head actually came to rest, so the
annotation carries the landing SHA a future reader needs.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HANDOFF = Path(__file__).resolve().parents[1] / ".claude" / "handoff"
REPO = Path(__file__).resolve().parents[1]

#: `program/ux-38 @ 130d8d1c` — the shape every lane queue uses to declare a head.
DECLARED = re.compile(r"(?P<branch>(?:program|lane\d)/[\w./-]+)\s*@\s*(?P<sha>[0-9a-f]{7,40})")


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True
    ).stdout.strip()


def content_is_on_master(sha: str) -> tuple[bool, str]:
    """Is the CONTENT of `sha` present on origin/master?

    Compares each file the commit touched against master's version of that file.
    Deliberately not `git cherry` (false `+` forever once a commit has gone
    through a conflict resolution) and not `--merged` (SHA identity dies on
    rebase).
    """
    if not _git("cat-file", "-t", sha):
        return False, f"{sha} is not an object in this repo"
    files = [f for f in _git("show", "--pretty=", "--name-only", sha).splitlines() if f]
    if not files:
        return False, f"{sha} touches no files"
    missing = []
    for f in files:
        # Compare BLOB HASHES, not decoded text. `git show <sha>:<path>` on a PNG
        # or an .ico raises UnicodeDecodeError under text=True, and a queue flip
        # must not depend on whether a commit happened to touch a binary. An
        # empty result means the path is absent on that side, which compares
        # unequal exactly as it should.
        on_branch = _git("rev-parse", f"{sha}:{f}")
        on_master = _git("rev-parse", f"origin/master:{f}")
        if not on_branch or on_branch != on_master:
            missing.append(f)
    if missing:
        return False, f"{len(missing)}/{len(files)} files differ from master (e.g. {missing[0]})"
    return True, f"all {len(files)} files match origin/master"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--landed",
        action="append",
        default=[],
        help="OLD=NEW — the SHA a declared head actually landed as",
    )
    args = ap.parse_args()
    if not (args.apply or args.dry_run):
        ap.error("pass --apply or --dry-run")

    landed = dict(p.split("=", 1) for p in args.landed)

    changed = 0
    for path in sorted(HANDOFF.glob("*QUEUE*.md")):
        text = path.read_text()
        status = re.search(r"(?m)^status:\s*(\S+)", text)
        if not status or status.group(1) != "ready_for_integration":
            continue
        heads = DECLARED.findall(text[: text.find("\n## ") if "\n## " in text else len(text)])
        if not heads:
            print(f"SKIP  {path.name}: ready, but declares no `branch @ sha` — cannot verify")
            continue

        verdicts = [(b, s, *content_is_on_master(s)) for b, s in heads]
        if not all(v[2] for v in verdicts):
            for b, s, ok, why in verdicts:
                print(f"KEEP  {path.name}: {b} @ {s} -> {'LANDED' if ok else 'NOT LANDED'} ({why})")
            continue

        note = ", ".join(f"{b} @ {s} -> {landed.get(s, s)}" for b, s, _o, _w in verdicts)
        print(f"FLIP  {path.name}: {note}")
        changed += 1
        if args.apply:
            new = text[: status.start(1)] + "merged" + text[status.end(1):]
            new = new.replace(
                "\nstatus: merged",
                f"\nstatus: merged   # verified by CONTENT on origin/master: {note}",
                1,
            )
            path.write_text(new)

    print(f"\n{changed} queue file(s) {'flipped' if args.apply else 'would flip'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
