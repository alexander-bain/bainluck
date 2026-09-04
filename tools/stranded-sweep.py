#!/usr/bin/env python3
"""stranded-sweep.py — find work that has been sitting unmerged and unreviewed.

D52 (Alex, 2026-09-03 3:50pm): the integrator sweeps 7-day-stale unmerged work.
RESCUE (rebase + re-stage) before close; close ONLY what is superseded or already
on master, with a comment saying which. Alex's bar, in his words:

    "I hope we aren't throwing away work very often."

So the default is REPORT ONLY. Nothing is closed, rebased or staged without
`--apply`, and even then the rescue path is capped so one run cannot churn every
branch in the repo. Anything the script cannot classify with evidence is called
RESCUE, never CLOSE — erring toward keeping work is the whole point.

  ./tools/stranded-sweep.py                  # the list, no writes  (run this first)
  ./tools/stranded-sweep.py --apply          # close the closable, rescue the rest
  ./tools/stranded-sweep.py --apply --max-rescues 3
  ./tools/stranded-sweep.py --days 14        # a different staleness bar

WHAT "STALE" MEANS HERE
  A PR is stale when it has had no activity for --days AND no GREEN cert row in
  that window. A PR opened yesterday with no cert yet is not stranded, it is new;
  a PR with a GREEN from this morning is not stranded, it is waiting on a merge.

WHAT THE CLASSES MEAN
  ON_MASTER   every commit is already upstream by patch-id (`git cherry`), or the
              tip is an ancestor of origin/master. The work SHIPPED; the PR is a
              leftover. Closable.
  SUPERSEDED  a later ledger row says "supersedes" and names this branch's cert.
              Closable, and the comment names the row that replaced it.
  RESCUE      everything else. Rebase onto origin/master, run the focused tests
              for what it changed, re-stage the review. Never closed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HANDOFF = REPO / ".claude" / "handoff"
CERT_LOG = HANDOFF / "CODEX-CERT-LOG.md"
MASTER = "origin/master"


def git(*args, check=True):
    p = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=180
    )
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {p.returncode}: {p.stderr.strip()}")
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def gh_json(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} -> {p.returncode}: {p.stderr.strip()}")
    return json.loads(p.stdout)


# ───────────────────────────────────────────────────────── the cert ledger ───


CERT_ROW = re.compile(r"^\|\s*(CERT-[0-9A-Za-z-]+)[^|]*\|\s*([0-9]{4}-[0-9]{2}-[0-9]{2})[^|]*\|(.*)$")


def load_cert_rows():
    """Ledger rows as (cert_id, date, rest_of_row). Append-only file, oldest first."""
    rows = []
    if not CERT_LOG.exists():
        return rows
    for line in CERT_LOG.read_text(errors="replace").splitlines():
        m = CERT_ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3)))
    return rows


def lane_key(branch):
    """'lane1/088-a-tennis-card-has-a-face' -> 'lane1/088'.

    The ledger's lane column writes the SHORT form. Matching on the sha alone
    misses roughly 40% of rows (measured), so the lane key is the primary handle
    and the sha is the backstop.
    """
    m = re.match(r"^(?:program/)?([a-z0-9]+)[/-](\d+)", branch)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def rows_for(branch, sha, rows):
    key = lane_key(branch)
    short = sha[:8]
    out = []
    for cid, date, rest in rows:
        hay = rest
        if (key and key in hay) or short in hay or branch in hay:
            out.append((cid, date, rest))
    return out


def superseded_by(my_rows, all_rows):
    """A LATER row that says 'supersedes' and names one of my cert ids.

    Standing notice 18: a supersedes row is what revokes a token. It is also the
    only evidence this script will accept for closing work that is not on master.
    """
    mine = {cid for cid, _, _ in my_rows}
    for cid, date, rest in all_rows:
        if cid in mine:
            continue
        m = re.search(r"supersedes[:\s]+(CERT-[0-9A-Za-z-]+)", rest, re.I)
        if m and m.group(1) in mine:
            return cid, date, m.group(1)
    return None


# ─────────────────────────────────────────────────────────── git questions ───


def resolve_ref(branch, sha, pr=None):
    """A ref this machine can actually read, or None.

    Most PR heads here have no LOCAL branch — dependabot's never do, and neither
    do other lanes' branches until someone fetches them. The first version of
    this script passed the bare branch name to git, both queries failed silently,
    and every one of those PRs came out as "RESCUE, 0 files not on master" — a
    verdict that contradicts its own evidence. An unreadable ref is now its own
    verdict, never a rescue and never a close.

    Last resort, `refs/pull/N/head`: when a PR's branch has been DELETED from the
    remote, no amount of `git fetch origin` brings it back and the PR sat
    permanently UNRESOLVED — "run git fetch and re-run" was advice that could
    never work (measured on #998, branch `fix/887-mrbdgf0e`, deleted, 58d stale).
    GitHub keeps the head reachable under refs/pull regardless, so the sweep can
    read and judge these instead of skipping them forever.
    """
    for ref in (sha, f"origin/{branch}", branch):
        rc, _, _ = git("cat-file", "-e", f"{ref}^{{commit}}", check=False)
        if rc == 0:
            return ref
    if pr is not None:
        local = f"refs/stranded-sweep/pr{pr}"
        rc, _, _ = git("fetch", "--quiet", "origin",
                       f"+refs/pull/{pr}/head:{local}", check=False)
        if rc == 0:
            rc, _, _ = git("cat-file", "-e", f"{local}^{{commit}}", check=False)
            if rc == 0:
                return local
    return None


def content_is_on_master(ref):
    """Is every one of this ref's commits already upstream?

    `git cherry` compares PATCH IDs, so it still says yes after the work was
    rebased, squashed or cherry-picked onto master under a different sha — which
    is the normal way work lands here. The ancestor test alone would call such a
    branch stranded and the script would then 'rescue' something already shipped.
    """
    rc, _, _ = git("merge-base", "--is-ancestor", ref, MASTER, check=False)
    if rc == 0:
        return True, "tip is an ancestor of origin/master"
    rc, out, _ = git("cherry", MASTER, ref, check=False)
    if rc != 0:
        return False, ""
    unmerged = [l for l in out.splitlines() if l.startswith("+")]
    if out and not unmerged:
        return True, f"all {len(out.splitlines())} commits have a patch-id equivalent upstream"
    if not out:
        return True, "no commits relative to origin/master"
    return False, f"{len(unmerged)} commit(s) not upstream"


def changed_files(ref):
    rc, out, _ = git("diff", "--name-only", f"{MASTER}...{ref}", check=False)
    if rc != 0:
        return None                      # unknown, NOT "zero" — see resolve_ref
    return [l for l in out.splitlines() if l.strip()]


def focused_tests(files):
    """The tests to re-run for a rescued branch.

    Deliberately NOT `pytest -k <lane-name>`: a -k band named after your feature
    misses the route suites that actually exercise it. This picks files instead —
    the startup smoke test always, every changed test file, and any test file
    whose name contains a changed module's stem.
    """
    picks = {"tests/test_startup.py"}
    backend_tests = REPO / "backend" / "tests"
    stems = set()
    for f in files:
        if f.startswith("backend/tests/") and f.endswith(".py"):
            picks.add(f[len("backend/"):])
        elif f.startswith("backend/app/") and f.endswith(".py"):
            stems.add(Path(f).stem)
    for stem in stems:
        if not stem or stem == "__init__":
            continue
        for t in backend_tests.rglob(f"*{stem}*.py"):
            picks.add(str(t.relative_to(REPO / "backend")))
    return sorted(picks)


# ───────────────────────────────────────────────────────────────── sweep ────


def classify(pr, rows, days):
    branch = pr["headRefName"]
    sha = pr["headRefOid"]
    updated = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - updated).days

    mine = rows_for(branch, sha, rows)
    greens = [
        (cid, date) for cid, date, rest in mine
        if "GREEN" in rest and "TOKEN GRANTED" in rest
    ]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    fresh_green = [g for g in greens if g[1] >= cutoff]

    rec = {
        "pr": pr["number"],
        "branch": branch,
        "sha": sha[:8],
        # The FULL oid, for --force-with-lease: an abbreviated sha is not a
        # lease git will honour, and a lease that silently degrades to a plain
        # force is worse than no lease at all.
        "sha_full": sha,
        "age_days": age,
        "certs": len(mine),
        "last_cert": f"{mine[-1][0]} ({mine[-1][1]})" if mine else "-",
        "greens": len(greens),
    }

    if age < days:
        rec.update(verdict="ACTIVE", why=f"updated {age}d ago (bar is {days}d)")
        return rec
    if fresh_green:
        rec.update(verdict="AWAITING_MERGE",
                   why=f"GREEN {fresh_green[-1][0]} on {fresh_green[-1][1]} — merge it, do not sweep it")
        return rec

    if branch.startswith("dependabot/"):
        # Real stale work, and Alex should still see it — but never OURS to
        # rescue: dependabot rebases its own branches, and a force-push from
        # this script would fight it. Listed, counted, never touched.
        rec.update(verdict="BOT", why=f"dependabot PR, stale {age}d — merge or close it by hand")
        return rec

    ref = resolve_ref(branch, sha, pr=pr["number"])
    if ref is None:
        rec.update(verdict="UNRESOLVED",
                   why=f"no readable ref for {branch}@{sha[:8]} — not on origin and "
                       f"refs/pull/{pr['number']}/head did not resolve; NOT swept either way")
        return rec

    on_master, evidence = content_is_on_master(ref)
    if on_master:
        rec.update(verdict="ON_MASTER", why=evidence)
        return rec

    sup = superseded_by(mine, rows)
    if sup:
        rec.update(verdict="SUPERSEDED", why=f"{sup[0]} ({sup[1]}) supersedes {sup[2]}")
        return rec

    files = changed_files(ref)
    if files is None:
        rec.update(verdict="UNRESOLVED", why=f"cannot diff {ref} against {MASTER}")
        return rec
    if not files:
        # Nothing to rescue: the branch has no net change against master, whatever
        # its commit list says. Reporting this as RESCUE was the defect the first
        # run surfaced — "0 file(s) not on master" is a closable state, not a
        # stranded one, and a rescue verdict that contradicts its own evidence
        # sends a human chasing work that is not there.
        rec.update(verdict="ON_MASTER", why="no net diff against origin/master")
        return rec

    rec.update(verdict="RESCUE",
               why=f"{len(files)} file(s) not on master, no GREEN in {days}d, nothing supersedes it",
               files=files, ref=ref)
    return rec


def do_close(rec, dry):
    body = {
        "ON_MASTER": (
            "Closed by the stranded sweep (D52): this branch's changes are already on "
            f"master — {rec['why']}. Nothing is being thrown away; the work shipped. "
            "Reopen if that reading is wrong."
        ),
        "SUPERSEDED": (
            f"Closed by the stranded sweep (D52): {rec['why']}. The replacement carries "
            "this work. Reopen if that reading is wrong."
        ),
    }[rec["verdict"]]
    if dry:
        print(f"    would close #{rec['pr']} with: {body[:90]}...")
        return False
    subprocess.run(["gh", "pr", "close", str(rec["pr"]), "--comment", body],
                   check=True, timeout=120)
    print(f"    closed #{rec['pr']}")
    return True


def do_rescue(rec, dry):
    """Rebase onto master, run the focused tests, report what to re-stage.

    Runs in a throwaway worktree, never in a shared tree: every destructive git
    verb takes -C, and -C pins the DIRECTORY, not the branch (gotcha #51). A
    conflict is reported for a human and the branch is left exactly as it was.
    """
    branch = rec["branch"]
    ref = rec.get("ref", branch)
    tests = focused_tests(rec.get("files") or [])
    if dry:
        print(f"    would rebase {branch} onto {MASTER}, then run: pytest {' '.join(tests)}")
        print(f"    then re-stage with: tools/stage-cert.sh <SUBJ> {lane_key(branch)} {branch} <sha> <pr> <issue>")
        return False

    wt = Path(f"/tmp/stranded-sweep-{os.getpid()}-{branch.replace('/', '-')}")
    git("worktree", "add", "--detach", str(wt), ref)
    try:
        p = subprocess.run(["git", "-C", str(wt), "rebase", MASTER],
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            subprocess.run(["git", "-C", str(wt), "rebase", "--abort"], capture_output=True)
            print(f"    CONFLICT rebasing {branch} — left untouched, needs a human:\n"
                  f"      {p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr.strip()[:200]}")
            return False
        # cwd is the REBASED WORKTREE's backend, never REPO's. This ran in the
        # shared checkout in the first version, which is the worst shape a gate
        # can take: it tests a tree the rescue did not produce, then moves the
        # branch and calls the untested rebase green. The shared tree also holds
        # other lanes' uncommitted work, so its result is not even reproducible.
        t = subprocess.run(["python3", "-m", "pytest", "-q", *tests],
                           cwd=str(wt / "backend"), capture_output=True, text=True, timeout=1800)
        new_sha = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip()
        # Exit code 1 is a real test failure; ANYTHING ELSE is a story about the
        # harness (pytest 2/3/4/5, 127, 137/143 = the gate never ran), and must
        # not be read as "the rescued branch is broken".
        if t.returncode == 0:
            # PUBLISH BEFORE ANNOUNCING. The first version moved only the LOCAL
            # branch and then printed a `stage-cert.sh` line naming `new_sha`.
            # That sha existed nowhere but this laptop's object store: the PR
            # head never moved, CI never saw it, and a grader on any other
            # machine got "no readable ref" — the exact UNRESOLVED failure this
            # same script reports for PRs whose branch was deleted. A rescue that
            # cannot be fetched has not rescued anything (gotcha #154: a rebase
            # is not complete until the commits are on a pushed ref).
            #
            # --force-with-lease, not --force: the rebase started from `ref`, so
            # if someone moved the branch while we were running, the lease fails
            # and we leave their work alone rather than overwriting it.
            pushed = subprocess.run(
                ["git", "-C", str(wt), "push",
                 f"--force-with-lease=refs/heads/{branch}:{rec['sha_full']}",
                 "origin", f"HEAD:refs/heads/{branch}"],
                capture_output=True, text=True, timeout=300)
            if pushed.returncode != 0:
                print(f"    {branch}: rebased and green at {new_sha[:8]} but PUSH FAILED — "
                      "the branch is NOT rescued, and the sha is local-only:")
                print("      " + (pushed.stderr.strip().splitlines() or ["(no stderr)"])[-1])
                return False
            git("branch", "-f", branch, new_sha)
            print(f"    rescued {branch} -> {new_sha[:8]}, focused tests green ({len(tests)} file(s)), pushed")
            print(f"      re-stage: tools/stage-cert.sh <SUBJ> {lane_key(branch)} {branch} {new_sha} "
                  f"https://github.com/alexander-bain/bainluck/pull/{rec['pr']} <issue>")
            return True
        kind = "FAILED" if t.returncode == 1 else f"DID NOT RUN (exit {t.returncode})"
        print(f"    {branch}: rebase clean but focused tests {kind} — branch left untouched")
        print("      " + "\n      ".join(t.stdout.strip().splitlines()[-6:]))
        return False
    finally:
        subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(wt)],
                       capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="staleness bar (default 7, D52)")
    ap.add_argument("--apply", action="store_true",
                    help="actually close/rescue. Without it nothing is written.")
    ap.add_argument("--max-rescues", type=int, default=5,
                    help="cap rescues per run so one sweep cannot churn the repo")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    if not args.no_fetch:
        # A stale origin/master makes everything look unmerged (and this repo's
        # local master ref goes stale constantly across shared worktrees).
        # ALL remote branches, not just master: most PR heads have no local ref,
        # and a narrow fetch leaves them unreadable (they then come out UNRESOLVED).
        git("fetch", "origin", "--quiet", check=False)

    rows = load_cert_rows()
    prs = gh_json("pr", "list", "--state", "open", "--limit", "300",
                  "--json", "number,headRefName,headRefOid,updatedAt,title")
    recs = [classify(pr, rows, args.days) for pr in prs]

    order = ["RESCUE", "ON_MASTER", "SUPERSEDED", "UNRESOLVED", "BOT", "AWAITING_MERGE", "ACTIVE"]
    recs.sort(key=lambda r: (order.index(r["verdict"]), -r["age_days"]))

    mode = "APPLY" if args.apply else "REPORT ONLY — nothing will be written"
    print(f"\nSTRANDED SWEEP (D52) — {mode}")
    print(f"{len(prs)} open PRs, staleness bar {args.days}d, ledger rows {len(rows)}\n")
    print(f"{'PR':>6}  {'AGE':>4}  {'VERDICT':<15} {'BRANCH':<52} WHY")
    print("-" * 150)
    for r in recs:
        if r["verdict"] == "ACTIVE":
            continue
        print(f"{r['pr']:>6}  {r['age_days']:>3}d  {r['verdict']:<15} {r['branch'][:52]:<52} {r['why']}")

    counts = {v: sum(1 for r in recs if r["verdict"] == v) for v in order}
    print("\nCOUNTS: " + "  ".join(f"{v}={counts[v]}" for v in order))
    print(f"  closable (already shipped or replaced): {counts['ON_MASTER'] + counts['SUPERSEDED']}")
    print(f"  to rescue (real work, still stranded):  {counts['RESCUE']}")
    print(f"  dependabot, for a human to merge/close:  {counts['BOT']}")
    print(f"  unreadable refs (fetch and re-run):      {counts['UNRESOLVED']}")

    if not args.apply:
        print("\nNo changes made. Re-run with --apply to close the closable and rescue the rest.")
        return 0

    closed = rescued = 0
    print("\nAPPLYING:")
    for r in recs:
        if r["verdict"] in ("ON_MASTER", "SUPERSEDED"):
            closed += do_close(r, dry=False)
    for r in recs:
        if r["verdict"] == "RESCUE":
            if rescued >= args.max_rescues:
                print(f"    --max-rescues {args.max_rescues} reached; {counts['RESCUE'] - rescued} "
                      "left for the next run")
                break
            rescued += do_rescue(r, dry=False)
    print(f"\nDONE: {closed} closed, {rescued} rescued.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
