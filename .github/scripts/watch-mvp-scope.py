#!/usr/bin/env python3
"""#13027 (251: A): decide whether a PR or push really touches Watch/app paths.

Why this exists:
  Server-only PRs (#12962, #12970) merged master into their branches. Each merge
  commit carried 300+ files (hitting GitHub's 300-file filter cap and including
  ios/** and watch-mvp.yml from master), so GitHub's `on: pull_request: paths:`
  filter started all nine macOS Watch MVP jobs even though the PR's actual 3-dot
  diff against master touched only backend/ files.

How this works:
  - Reads the single-source-of-truth `paths:` list directly from
    `.github/workflows/watch-mvp.yml` (no second list to drift).
  - For `pull_request`, computes the true 3-dot PR diff:
      git diff --name-only --no-renames $(git merge-base BASE HEAD) HEAD
  - For `push`, computes `git diff --name-only --no-renames BEFORE HEAD`.
  - Fails closed toward `relevant=true` on any error, empty diff, missing commit,
    or unparseable workflow, so a real Watch/app change is never skipped.
  - Emits `relevant=false` ONLY when the diff succeeds with >=1 changed file and
    zero changed files match any pattern in `watch-mvp.yml`.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ZERO_SHA = "0" * 40


def extract_watch_paths(workflow_text: str) -> list[str]:
    """Extract the union of `pull_request.paths` and `push.paths` from watch-mvp.yml without PyYAML."""
    lines = workflow_text.splitlines()
    in_on = False
    in_trigger = False
    in_paths = False
    seen: set[str] = set()
    paths: list[str] = []

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_on = stripped == "on:"
            in_trigger = False
            in_paths = False
            continue
        if not in_on:
            continue
        if indent == 2:
            in_trigger = stripped in ("pull_request:", "push:")
            in_paths = False
            continue
        if not in_trigger:
            continue
        if indent == 4:
            in_paths = stripped == "paths:"
            continue
        if in_paths and indent >= 6 and stripped.startswith("- "):
            item = stripped[2:].strip()
            if (item.startswith("'") and item.endswith("'")) or (
                item.startswith('"') and item.endswith('"')
            ):
                item = item[1:-1]
            if item and item not in seen:
                seen.add(item)
                paths.append(item)
        elif in_paths and indent < 6:
            in_paths = False

    return paths


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a GitHub Actions `paths:` glob into a full-string regex."""
    out: list[str] = ["^"]
    i = 0
    n = len(pattern)
    while i < n:
        if pattern[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif pattern[i : i + 3] == "/**" and i + 3 == n:
            out.append("(?:/.*)?")
            i += 3
        elif pattern[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def find_matching_paths(changed_files: list[str], patterns: list[str]) -> list[str]:
    compiled = [_glob_to_regex(p) for p in patterns]
    return [f for f in changed_files if any(rx.match(f) for rx in compiled)]


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def decide_scope(
    *,
    repo: Path,
    event_name: str,
    base_sha: str,
    head_sha: str,
    workflow_path: Path | None = None,
) -> tuple[bool, str]:
    """Return (relevant, reason). Fails closed toward (True, ...)."""
    wf = workflow_path or (repo / ".github" / "workflows" / "watch-mvp.yml")
    try:
        patterns = extract_watch_paths(wf.read_text(encoding="utf-8"))
    except OSError as exc:
        return True, f"workflow unreadable ({exc}) — failing toward relevant=true"

    if not patterns:
        return True, "empty path list in watch-mvp.yml — failing toward relevant=true"

    if not head_sha or head_sha == ZERO_SHA:
        return True, "missing head sha — failing toward relevant=true"
    if not base_sha or base_sha == ZERO_SHA:
        return True, "missing or zero base sha — failing toward relevant=true"

    try:
        _git(repo, "cat-file", "-e", f"{base_sha}^{{commit}}")
        _git(repo, "cat-file", "-e", f"{head_sha}^{{commit}}")
    except subprocess.CalledProcessError:
        return True, "base or head commit unavailable — failing toward relevant=true"

    if event_name == "pull_request":
        try:
            diff_base = _git(repo, "merge-base", base_sha, head_sha)
        except subprocess.CalledProcessError:
            return True, "git merge-base failed — failing toward relevant=true"
    elif event_name == "push":
        diff_base = base_sha
    else:
        return True, f"event {event_name!r} is not pull_request/push — failing toward relevant=true"

    try:
        raw_diff = _git(repo, "diff", "--name-only", "--no-renames", diff_base, head_sha)
    except subprocess.CalledProcessError:
        return True, "git diff failed — failing toward relevant=true"

    changed = [line.strip() for line in raw_diff.splitlines() if line.strip()]
    if not changed:
        return True, "empty diff — failing toward relevant=true"

    matches = find_matching_paths(changed, patterns)
    if matches:
        sample = ", ".join(matches[:3])
        extra = f" (+{len(matches) - 3} more)" if len(matches) > 3 else ""
        return True, f"{len(matches)}/{len(changed)} changed file(s) match Watch/app paths: {sample}{extra}"

    return False, f"0/{len(changed)} changed file(s) match Watch/app paths (merge-base {diff_base[:10]}..{head_sha[:10]})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Decide whether Watch MVP jobs should run.")
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--workflow", default=None)
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args(argv)

    relevant, reason = decide_scope(
        repo=Path(args.repo),
        event_name=args.event,
        base_sha=args.base,
        head_sha=args.head,
        workflow_path=Path(args.workflow) if args.workflow else None,
    )
    val = "true" if relevant else "false"
    print(f"watch-scope: relevant={val} ({reason})", file=sys.stderr)
    print(val)

    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"relevant={val}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
