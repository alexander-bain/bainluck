#!/usr/bin/env python3
"""The Phase-0 READY sweep, with the never-merge containment check COMPUTED.

Ruling 109: **a READY token is VOID while its branch contains a never-merge
ancestor.** This script is the enforcement half of that ruling, and it exists
because the alternative — a list of never-merge heads that a human consults —
is a list a human forgets. INT-092 retired the two never-merge heads it could
see and the real constraint ran through a third one that was still advertising
``status: ready_for_integration``, so four further ready branches silently
carried an edit to a migration production had already run.

What it answers, per token:

* is the branch's head where the token says it is (**MOVED-HEAD** = withdrawn),
* is the branch already on master (**SPENT** = flip it to merged; the INT-034
  failure, where 15 of 15 ready entries were already-merged work),
* does the branch share any commit with the never-merge closure (**VOID**,
  ruling 109) — see :func:`never_merge_closure` for why this is a set
  intersection and not an ancestry test,
* otherwise **LIVE-READY**.

Two deliberate refusals, both gotcha #53 — an absent comparison is not evidence
of health:

* a token whose head cannot be resolved is **UNRESOLVED**, never clean;
* a run where the never-merge set is empty prints ``containment: NOT RUN`` and
  says so in the verdict, rather than reporting every branch as uncontained.

Usage::

    python3 scripts/sweep_ready_tokens.py
    python3 scripts/sweep_ready_tokens.py --json
    python3 scripts/sweep_ready_tokens.py --strict     # exit 1 if a VOID token still reads ready
    python3 scripts/sweep_ready_tokens.py --never-merge <sha> [--never-merge <sha> ...]

Exit codes: ``0`` swept, ``1`` ``--strict`` and a void-but-ready token exists,
``2`` the handoff directory does not exist.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

DEFAULT_HANDOFF_DIR = ".claude/handoff"

#: Values of a token's ``status:`` field that mean "merge me". `ready` is here
#: because `READY-lane1-380.md` used it while carrying three real branches with
#: three open PRs — a one-word deviation that hid live work from a literal-bytes
#: grep for the long form. Accept both, and REPORT the short one rather than
#: silently normalising it, so the token gets fixed.
READY_VALUES = {"ready_for_integration", "ready"}

#: Verdicts, most-blocking first. Order matters: a branch that is BOTH spent and
#: void is reported void, because the void is the fact that needs acting on.
VOID = "VOID"
UNRESOLVED = "UNRESOLVED"
MOVED_HEAD = "MOVED-HEAD"
SPENT = "SPENT"
LIVE_READY = "LIVE-READY"
HELD = "HELD"


def _clean(value: str) -> str:
    """Strip the markdown a token field is usually dressed in.

    Real tokens write ``branch: **`program/calibration-74`**``, so a naive
    ``split(":", 1)[1].strip()`` yields a branch name git has never heard of.

    Underscores are deliberately NOT stripped, though ``_x_`` is also markdown
    italics: the underscore is load-bearing inside the values this field carries
    (``ready_for_integration``, ``never_merge``). Stripping it turned every ready
    token into ``readyforintegration`` and the sweep reported an EMPTY ready set —
    caught on the first run of the impure test, which is the whole of ruling 102.
    """
    value = value.split("#", 1)[0]
    return value.replace("*", "").replace("`", "").strip()


def parse_token(text: str) -> dict:
    """Pull ``status`` / ``branch`` / ``head`` / ``never_merge`` out of a token. Pure.

    Only the FIRST occurrence of each field counts. Tokens quote other tokens in
    their prose (a report will happily contain the string ``status: merged``
    inside a paragraph about a previous cycle), and the header is the claim.
    """
    out = {"status": None, "branch": None, "head": None, "never_merge": False}
    for line in text.splitlines():
        stripped = line.strip()
        for key in ("status", "branch", "head", "never_merge"):
            if out.get(key) not in (None, False):
                continue
            prefix = key + ":"
            if not stripped.lower().startswith(prefix):
                continue
            value = _clean(stripped[len(prefix):])
            if key == "never_merge":
                out[key] = value.lower() in {"true", "yes", "1"}
            elif value:
                out[key] = value
    return out


def is_ready(status) -> bool:
    """Pure. A token with no ``status:`` field at all is NOT ready.

    `READY-calibration-75.md` shipped with no status field over real, gate-clean,
    unmerged work and was therefore invisible to the canonical sweep. That is a
    token defect to fix in the token — inferring ready from the filename would
    make every historical token in the directory live again.
    """
    if not status:
        return False
    return status.strip().lower() in READY_VALUES


def classify(token: dict, resolved_head, on_master: bool, shared) -> str:
    """Pure. `shared` = commits this branch has in common with the never-merge closure."""
    if token.get("never_merge"):
        return HELD
    if shared:
        return VOID
    if resolved_head is None:
        return UNRESOLVED
    if on_master:
        return SPENT
    token_head = token.get("head")
    if token_head and not resolved_head.startswith(token_head.lower()[:7]):
        return MOVED_HEAD
    return LIVE_READY


def _git(runner, repo, *args):
    """Return stdout, or None when git refuses. Never raises."""
    try:
        proc = runner(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _is_ancestor(runner, repo, ancestor, descendant) -> bool:
    try:
        proc = runner(
            ["git", "-C", repo, "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _commits_not_on_base(runner, repo, base, head):
    """``git rev-list base..head`` as a set. None when git refuses."""
    out = _git(runner, repo, "rev-list", f"{base}..{head}")
    if out is None:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def open_pull_requests(runner, repo, base):
    """Open PRs whose head is NOT already on ``base``, with their CI rollup.

    **Ruling 113: a merge offer is a branch with a green gate, not a file.** The
    token sweep above reads what lanes WROTE; this reads what they OFFERED. Two
    consecutive Integrator cycles missed live merge-eligible work because a PR
    is a real offer and no token described it — `#2049`/`#2050` sat behind a
    token the parser read as ``branch: None``, and `#2054`/`#2055` had no token
    at all while `#2055` gated 31 downstream applies.

    Returns ``(rows, error)``. **`error` is not optional decoration.** This is
    the one part of the sweep that makes a NETWORK call, and `gh` missing,
    unauthenticated, rate-limited or slow all produce an empty list that is
    indistinguishable from "no PRs are open" (gotcha #53). So the failure is
    returned as a REASON and rendered as ``NOT RUN``, never as an empty section.
    """
    fields = "number,title,headRefName,headRefOid,mergeable,mergeStateStatus,isDraft,statusCheckRollup"
    try:
        proc = runner(
            ["gh", "pr", "list", "--state", "open", "--limit", "100", "--json", fields],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return [], "gh not installed"
    except Exception as exc:  # noqa: BLE001 - the reason is the product here
        return [], f"gh could not run: {type(exc).__name__}"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return [], f"gh exited {proc.returncode}: {detail[0] if detail else 'no stderr'}"
    try:
        raw = json.loads(proc.stdout or "[]")
    except ValueError:
        return [], "gh returned output that is not JSON"

    rows = []
    for pr in raw:
        head = pr.get("headRefOid") or ""
        # Contained by CONTENT-bearing ancestry, same test the token sweep uses
        # for SPENT. A PR whose head is already on base is not an offer.
        if head and _is_ancestor(runner, repo, head, base):
            continue
        checks = pr.get("statusCheckRollup") or []
        concl = [c.get("conclusion") or c.get("state") or "" for c in checks]
        failed = [c for c in concl if c in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED")]
        pending = [c for c in concl if c in ("", "PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED")]
        if not checks:
            ci = "NO CHECKS"
        elif failed:
            ci = f"RED ({len(failed)})"
        elif pending:
            ci = f"PENDING ({len(pending)})"
        else:
            ci = "GREEN"
        rows.append({
            "number": pr.get("number"),
            "branch": pr.get("headRefName"),
            "head": head[:8],
            "draft": bool(pr.get("isDraft")),
            "mergeable": pr.get("mergeable"),
            "merge_state": pr.get("mergeStateStatus"),
            "ci": ci,
            "title": (pr.get("title") or "")[:60],
        })
    rows.sort(key=lambda r: r["number"] or 0)
    return rows, None


def never_merge_closure(runner, repo, base, heads):
    """Every commit reachable from a never-merge head and NOT already on ``base``.

    **This is the containment primitive, and plain head-ancestry is the wrong
    one** — which this cycle proved by shipping the wrong one first.

    Testing ``is-ancestor(never_merge_head, candidate)`` asks whether the
    candidate is DOWNSTREAM of the retired head. It answered "no" for all five
    contaminated branches, because the poison is not the retired head — it is
    `02cd7ad8`, an ANCESTOR of never-merge `provenance-r5`, sitting upstream of
    four branches that never touched `provenance-r5` at all.

    Reversing the test is not the fix either: `origin/master` is an ancestor of
    `provenance-r5` too, so "is an ancestor of a never-merge head" marks the
    entire repository void.

    The set that is actually forbidden is the never-merge lineage MINUS what is
    already shipped: `base..head`. A candidate is contaminated when its own
    `base..head` intersects it. Master's commits fall out by construction, and
    a branch is contaminated by the specific commits it shares — which are named
    in the report, so the finding can be checked rather than believed.
    """
    closure = set()
    unreadable = []
    for entry in heads:
        commits = _commits_not_on_base(runner, repo, base, entry["head"])
        if commits is None:
            unreadable.append(entry)
            continue
        closure |= commits
    return closure, unreadable


def sweep(handoff_dir, repo, runner=subprocess.run, extra_never_merge=(),
          include_prs=True,
          base="origin/master"):
    """Read every READY token, resolve it against git, apply ruling 109."""
    names = sorted(
        n for n in os.listdir(handoff_dir)
        if n.startswith("READY-") and n.endswith(".md")
    )

    tokens = []
    for name in names:
        path = os.path.join(handoff_dir, name)
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        parsed = parse_token(text)
        parsed["file"] = name
        tokens.append(parsed)

    # The never-merge SET first — the closure cannot be computed without it.
    never_merge = []
    for token in tokens:
        if not token.get("never_merge"):
            continue
        head = _git(runner, repo, "rev-parse", token["branch"]) if token.get("branch") else None
        head = head or token.get("head")
        if head:
            never_merge.append({"head": head, "source": token["file"]})
    for head in extra_never_merge:
        never_merge.append({"head": head, "source": "--never-merge"})

    closure, unreadable = never_merge_closure(runner, repo, base, never_merge)

    # Ruling 113: the second source. Never lets its own failure read as "none".
    pr_rows, pr_error = (([], "disabled") if not include_prs
                         else open_pull_requests(runner, repo, base))

    rows = []
    for token in tokens:
        if not (is_ready(token.get("status")) or token.get("never_merge")):
            continue
        branch = token.get("branch")
        resolved = _git(runner, repo, "rev-parse", branch) if branch else None
        if resolved is None and token.get("head"):
            resolved = _git(runner, repo, "rev-parse", "--verify", token["head"] + "^{commit}")

        shared = []
        if resolved and closure and not token.get("never_merge"):
            own = _commits_not_on_base(runner, repo, base, resolved)
            if own:
                shared = sorted(own & closure)

        on_master = bool(resolved) and _is_ancestor(runner, repo, resolved, base)
        rows.append({
            "file": token["file"],
            "branch": branch,
            "token_head": token.get("head"),
            "resolved_head": resolved,
            "status": token.get("status"),
            "status_is_short_form": (token.get("status") or "").strip().lower() == "ready",
            "verdict": classify(token, resolved, on_master, shared),
            "contains_never_merge": [c[:8] for c in shared],
        })

    return {
        "handoff_dir": handoff_dir,
        "base": base,
        "tokens_read": len(tokens),
        "never_merge_heads": [
            {"head": e["head"][:8], "source": e["source"]} for e in never_merge
        ],
        "closure_size": len(closure),
        "unreadable_never_merge_heads": [e["source"] for e in unreadable],
        # Obligation 4 of ruling 109: an unrun check is reported UNRUN, never clean.
        # A head we could not read makes the closure INCOMPLETE, so that is not
        # clean either — an under-read closure produces false LIVE-READY verdicts,
        # which is the exact failure the ruling was written about.
        "containment_ran": bool(never_merge) and not unreadable,
        "open_prs": pr_rows,
        "open_prs_error": pr_error,
        "rows": rows,
    }


def render(result) -> str:
    lines = []
    lines.append(f"READY sweep — {result['handoff_dir']} — {result['tokens_read']} token files read")
    if result["containment_ran"]:
        heads = ", ".join(
            f"{e['head']} ({e['source']})" for e in result["never_merge_heads"]
        )
        lines.append(
            f"never-merge containment: RAN against {len(result['never_merge_heads'])} head(s) "
            f"— {heads}; closure = {result['closure_size']} commit(s) not on {result['base']}"
        )
    elif result["unreadable_never_merge_heads"]:
        lines.append(
            "never-merge containment: INCOMPLETE — could not read "
            f"{result['unreadable_never_merge_heads']}. The closure is under-read, so a "
            "LIVE-READY verdict below may be false (ruling 109 obligation 4, gotcha #53)."
        )
    else:
        lines.append(
            "never-merge containment: NOT RUN — no head carries never_merge: true. "
            "This is NOT a clean result (ruling 109 obligation 4, gotcha #53)."
        )
    lines.append("")
    order = [VOID, UNRESOLVED, MOVED_HEAD, SPENT, LIVE_READY, HELD]
    for verdict in order:
        group = [r for r in result["rows"] if r["verdict"] == verdict]
        if not group:
            continue
        lines.append(f"── {verdict} ({len(group)})")
        for row in group:
            head = (row["resolved_head"] or "unresolved")[:8]
            line = f"   {row['file']:<44} {str(row['branch']):<38} {head}"
            if row["contains_never_merge"]:
                line += "  contains " + ",".join(row["contains_never_merge"])
            if row["status_is_short_form"]:
                line += "   [status: ready — short form, fix the token]"
            lines.append(line)
        lines.append("")
    # ---- ruling 113: the second source, and its NOT-RUN discipline ----
    err = result.get("open_prs_error")
    prs = result.get("open_prs") or []
    if err == "disabled":
        lines.append(
            "open PRs: NOT RUN — --no-prs was passed. This is NOT a clean result: a merge "
            "offer is a branch with a green gate, not a file (ruling 113)."
        )
    elif err:
        lines.append(
            f"open PRs: NOT RUN — {err}. This is NOT a clean result. An unreadable PR list "
            "and an empty PR list look identical (gotcha #53), so nothing below rules out a "
            "green, merge-eligible PR that no token describes (ruling 113)."
        )
    elif not prs:
        lines.append(
            f"open PRs: RAN against {result['base']} — none open whose head is not already "
            "upstream."
        )
    else:
        ready = [r for r in prs if r["ci"] == "GREEN" and not r["draft"]]
        lines.append(
            f"── OPEN PRs ({len(prs)}) — merge offers the token sweep cannot see (ruling 113); "
            f"{len(ready)} green and non-draft"
        )
        for r in prs:
            flag = "  [DRAFT]" if r["draft"] else ""
            lines.append(
                f"   #{str(r['number']):<6} {str(r['branch']):<38} {r['head']}  "
                f"{r['ci']:<12} {str(r['merge_state'] or '?'):<10}{flag}  {r['title']}"
            )
        lines.append("")
        lines.append(
            "   Ruling 034 still governs: a PR promotes a branch into the candidate set and "
            "does not decide readiness. Confirm by CONTENT before merging."
        )
    lines.append("")

    void_but_ready = [r for r in result["rows"] if r["verdict"] == VOID]
    if void_but_ready:
        lines.append(
            f"RULING 109: {len(void_but_ready)} token(s) are VOID — their branch contains a "
            "never-merge ancestor. Mark them void with the reason in the file. They re-earn "
            "ready only from a branch REBUILT without the ancestor."
        )
    return "\n".join(lines)


def main(argv=None, runner=subprocess.run, stdout=None) -> int:
    stdout = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--handoff-dir", default=DEFAULT_HANDOFF_DIR)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any VOID token is still advertising ready")
    parser.add_argument("--no-prs", action="store_true",
                        help="skip the open-PR source; reported as NOT RUN, never as clean")
    parser.add_argument("--never-merge", action="append", default=[],
                        help="an additional never-merge head, repeatable")
    parser.add_argument("--base", default="origin/master",
                        help="what counts as already-shipped when computing the closure")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.handoff_dir):
        print(f"no such handoff dir: {args.handoff_dir}", file=stdout)
        return 2

    result = sweep(args.handoff_dir, args.repo, runner=runner,
                   extra_never_merge=tuple(args.never_merge), base=args.base,
                   include_prs=not args.no_prs)
    print(json.dumps(result, indent=2) if args.json else render(result), file=stdout)

    if args.strict and any(r["verdict"] == VOID for r in result["rows"]):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
