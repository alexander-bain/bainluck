#!/usr/bin/env python3
"""Decide whether a master commit needs a Heroku release.

WHY THIS EXISTS (integrator/150, SHIP 2, 2026-09-08). The `deploy` job in
`.github/workflows/ci.yml` had no path filter of any kind. Measured over the
seven days to 2026-09-08: **549 master merges, 105 of them frontend-only by
path, and all 105 released Heroku.** Heroku serves the backend; Vercel deploys
the frontend, so every one of those 105 releases cycled the dynos to ship
bytes Heroku does not serve. A release restarts `worker-heavy`, and a restart
mid-rebuild kills a running calibration beat (the cause of record behind D45).

WHY AN ALLOWLIST, AND WHY IT FAILS CLOSED. The decision is "skip only when
every changed path is one Heroku demonstrably does not serve". A denylist --
"skip unless it looks backend-y" -- hands the skip to the first file class
nobody thought of: a new top-level directory, a `Procfile` move, a runtime
bump. So anything unrecognised deploys, and the caller is expected to hand us
an empty path list only when it genuinely could not resolve one, which we also
treat as "deploy".

WHY ONLY `frontend/`. That is the class the 105-merge baseline actually
measured. `ios/`, `docs/` and `tools/` are equally un-served by Heroku and are
the obvious next candidates -- but they get their own measurement before they
get a skip, because the cost of being wrong here is a backend fix that CI calls
green and never ships.

Usage:
    heroku_deploy_scope.py --paths-from <file>     # one path per line
    heroku_deploy_scope.py path/one path/two ...

Prints a human-readable rationale to stderr and `heroku_needed=0|1` to stdout.
Always exits 0: this is a decision, not a gate. A crash here must never be
readable as "no release needed", which is why the workflow treats a non-zero
exit as fail-closed rather than parsing partial output.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, Sequence

# Path prefixes Heroku does not serve. Every entry needs a reason that survives
# someone asking "why is it safe to NOT restart the dynos for this?".
#
#   frontend/ -- deployed by Vercel from the same push; the Heroku slug does not
#                contain it and no backend module imports from it.
#
# Adding a prefix is a product decision with a measurement behind it, not a
# tidy-up. See the module docstring.
HEROKU_IRRELEVANT_PREFIXES: tuple[str, ...] = ("frontend/",)


def heroku_needed(paths: Iterable[str]) -> bool:
    """True when this change must be released to Heroku.

    Fail-closed in both degenerate directions: an empty path list means the
    caller could not work out what changed, and a path that is not clearly
    inside the allowlist is treated as Heroku-relevant.
    """
    cleaned = [p.strip() for p in paths if p and p.strip()]
    if not cleaned:
        return True
    return any(not _is_heroku_irrelevant(path) for path in cleaned)


def _is_heroku_irrelevant(path: str) -> bool:
    # `startswith` on a prefix that ends in "/" cannot match a sibling file
    # ("frontend-notes.md" does not start with "frontend/"), which is the whole
    # reason the prefixes carry their trailing slash.
    return any(path.startswith(prefix) for prefix in HEROKU_IRRELEVANT_PREFIXES)


def _relevant(paths: Sequence[str]) -> list[str]:
    return [p for p in paths if not _is_heroku_irrelevant(p)]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="changed paths, one per argument")
    parser.add_argument(
        "--paths-from",
        help="file containing changed paths, one per line ('-' for stdin)",
    )
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if args.paths_from:
        if args.paths_from == "-":
            paths.extend(sys.stdin.read().splitlines())
        else:
            with open(args.paths_from, encoding="utf-8") as handle:
                paths.extend(handle.read().splitlines())

    paths = [p.strip() for p in paths if p and p.strip()]

    if not paths:
        print(
            "No changed paths were resolved. Deploying: an unresolved diff is "
            "not evidence that nothing changed.",
            file=sys.stderr,
        )
        print("heroku_needed=1")
        return 0

    print(f"{len(paths)} changed path(s):", file=sys.stderr)
    for path in paths:
        print(f"  {path}", file=sys.stderr)

    relevant = _relevant(paths)
    if relevant:
        print("\nHeroku-relevant path(s) present:", file=sys.stderr)
        for path in relevant:
            print(f"  {path}", file=sys.stderr)
        print("heroku_needed=1")
        return 0

    print(
        "\nFRONTEND-ONLY: every changed path is under a prefix Heroku does not "
        "serve. Vercel ships this commit; the dynos do not need to cycle.",
        file=sys.stderr,
    )
    print("heroku_needed=0")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI wrapper
    raise SystemExit(main())
