#!/usr/bin/env python3
"""One event, one snapshot. Standard library only. No scheduler or polling loop."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

from model import build, instant, iso, public_title, PACIFIC, TRUSTED

REPO = "alexander-bain/bainluck"
RELEASE = "factory-data"
ASSET_URL = f"https://github.com/{REPO}/releases/download/{RELEASE}/factory.json"


class GitHub:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def request(self, endpoint, data=None, method=None, raw=False):
        if not self.token:
            command = ["gh", "api", endpoint]
            if method:
                command += ["--method", method]
            if data is not None:
                command += ["--input", "-"]
            result = subprocess.run(
                command,
                input=json.dumps(data) if data is not None else None,
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout) if result.stdout else None
        body = json.dumps(data).encode() if data is not None else None
        url = (
            endpoint
            if endpoint.startswith("https://")
            else f"https://api.github.com/{endpoint}"
        )
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
        return content if raw else json.loads(content) if content else None

    def pages(self, endpoint, field=None):
        result = []
        for page in range(1, 1001):
            separator = "&" if "?" in endpoint else "?"
            data = self.request(
                f"repos/{REPO}/{endpoint}{separator}per_page=100&page={page}"
            )
            rows = data[field] if field else data
            result.extend(rows)
            if len(rows) < 100:
                return result
        raise RuntimeError("GitHub pagination did not finish")


def read_public(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def safe_comment(comment):
    body = comment.get("body", "")
    return {
        "created_at": comment["created_at"],
        "updated_at": comment["updated_at"],
        "association": comment.get("author_association"),
        "fable_accept": body.startswith("**Fable look")
        and bool(re.search(r"\bACCEPT\b", body)),
    }


def collect_pull(api, summary, cached=None, refresh=False):
    number = summary["number"]
    core = {
        k: summary.get(k)
        for k in (
            "number",
            "title",
            "draft",
            "state",
            "updated_at",
            "merged_at",
            "merge_commit_sha",
        )
    }
    core["title"] = public_title(core["title"])
    core.update(
        branch=summary["head"]["ref"],
        head_sha=summary["head"]["sha"],
        fable_needed=bool(
            re.search(r"Fable\s*:\s*needed", summary.get("body") or "", re.I)
        ),
    )
    # Files and commit topology are immutable at one head. Mutable evidence
    # for EVERY open change is refreshed together below, even if GitHub drops
    # an intermediate pending workflow from its concurrency group.
    if (
        cached
        and cached["head_sha"] == core["head_sha"]
        and cached.get("files_complete")
        and (cached.get("merged_at") or cached.get("commits_complete"))
    ):
        return {**cached, **core}
    pull = {
        **core,
        "files_complete": False,
        "checks_complete": False,
        "reviews_complete": False,
        "comments_complete": False,
        "commits_complete": False,
    }
    prefix = f"pulls/{number}"
    try:
        details = api.request(f"repos/{REPO}/{prefix}")
        pull["merged_at"] = details.get("merged_at")
        pull["merge_commit_sha"] = details.get("merge_commit_sha")
        files = api.pages(f"{prefix}/files")
        pull["files"] = [f["filename"] for f in files]
        pull["files"] += [
            f["previous_filename"] for f in files if f.get("previous_filename")
        ]
        pull["files_complete"] = len(files) == details["changed_files"]
        if pull["merged_at"]:
            return pull
        commits = api.pages(f"{prefix}/commits")
        pull["commits"] = [
            {
                "sha": c["sha"],
                "parents": len(c["parents"]),
                "at": c["commit"]["committer"]["date"],
            }
            for c in commits
        ]
        pull["commits_complete"] = len(commits) == details["commits"]
    except (urllib.error.URLError, subprocess.CalledProcessError, KeyError) as error:
        # Missing evidence preserves the pull and earlier station, never green.
        print(
            f"Could not finish evidence for change #{number}: {type(error).__name__}",
            file=sys.stderr,
        )
    return pull


def refresh_open_evidence(api, pulls):
    active = [p for p in pulls if p["state"] == "open"]
    fields = """headRefOid
      reviews(last:100) { totalCount nodes { author { __typename login } state submittedAt commit { oid } } }
      comments(last:100) { totalCount nodes { body createdAt updatedAt authorAssociation } }
      commits(last:1) { nodes { commit { oid statusCheckRollup { contexts(first:100) {
        totalCount nodes {
          ... on CheckRun { name status conclusion startedAt completedAt checkSuite { app { slug } } }
          ... on StatusContext { context state createdAt }
        }
      } } } } }
    """
    for start in range(0, len(active), 15):
        batch = active[start : start + 15]
        selections = " ".join(
            f"p{p['number']}:pullRequest(number:{p['number']}){{{fields}}}"
            for p in batch
        )
        data = api.request(
            "graphql",
            {
                "query": f'query {{ repository(owner:"alexander-bain",name:"bainluck") {{ {selections} }} }}'
            },
        )
        if data.get("errors"):
            raise RuntimeError("GitHub could not reconcile all open-change checks")
        for pull in batch:
            node = data["data"]["repository"][f"p{pull['number']}"]
            if not node or node["headRefOid"] != pull["head_sha"]:
                pull.update(
                    checks_complete=False, files_complete=False, reviews_complete=False
                )
                continue
            reviews = node["reviews"]
            pull["reviews"] = [
                {
                    "login": "claude[bot]",
                    "commit_id": r["commit"]["oid"],
                    "state": r["state"],
                    "submitted_at": r["submittedAt"],
                }
                for r in reviews["nodes"]
                if is_review_bot(r.get("author")) and r.get("commit")
            ]
            pull["reviews_complete"] = reviews["totalCount"] <= 100
            comments = node["comments"]
            pull["comments"] = [
                safe_comment(
                    {
                        "body": c["body"],
                        "created_at": c["createdAt"],
                        "updated_at": c["updatedAt"],
                        "author_association": c["authorAssociation"],
                    }
                )
                for c in comments["nodes"]
            ]
            pull["comments_complete"] = comments["totalCount"] <= 100
            commit = node["commits"]["nodes"][-1]["commit"]
            contexts = (commit.get("statusCheckRollup") or {}).get(
                "contexts", {"nodes": [], "totalCount": 0}
            )
            checks = []
            for check in contexts["nodes"]:
                if "context" in check:
                    checks.append(
                        {
                            "name": check["context"],
                            "app": "commit-status",
                            "started_at": check["createdAt"],
                            "state": (
                                "in_progress"
                                if check["state"] in {"PENDING", "EXPECTED"}
                                else "completed"
                            ),
                            "conclusion": (
                                "success" if check["state"] == "SUCCESS" else "failure"
                            ),
                        }
                    )
                elif check["name"] != "Update the factory":
                    checks.append(
                        {
                            "name": check["name"],
                            "app": check["checkSuite"]["app"]["slug"],
                            "started_at": check["startedAt"],
                            "finished_at": check["completedAt"],
                            "state": check["status"].lower(),
                            "conclusion": (check["conclusion"] or "").lower(),
                        }
                    )
            pull["checks"] = checks
            pull["checks_complete"] = contexts["totalCount"] <= 100


def is_review_bot(author):
    # REST calls the account claude[bot]. GraphQL identifies the same account
    # as a Bot with login claude. A human account named claude is insufficient.
    return bool(
        author
        and author.get("__typename") == "Bot"
        and author.get("login") in {"claude", "claude[bot]"}
    )


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def contains(commit, ancestor):
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, commit], capture_output=True
    )
    return result.returncode == 0


def history_signals(api, midnight):
    """Read actual status contexts on master ancestry, including batched merges."""
    first_parent = set(git("rev-list", "--first-parent", "origin/master").splitlines())
    receipts = []
    latest = {}
    cursor = None
    while True:
        query = """query($cursor:String) { repository(owner:"alexander-bain",name:"bainluck") {
          defaultBranchRef { target { ... on Commit { history(first:100,after:$cursor) {
            pageInfo {hasNextPage endCursor} nodes { oid committedDate
              statusCheckRollup { contexts(first:100) { nodes {
                ... on StatusContext { context state createdAt }
              } } }
            }
          } } } }
        } }"""
        data = api.request("graphql", {"query": query, "variables": {"cursor": cursor}})
        if data.get("errors"):
            raise RuntimeError("GitHub could not return deployment status history")
        history = data["data"]["repository"]["defaultBranchRef"]["target"]["history"]
        nodes = history["nodes"]
        for node in nodes:
            if node["oid"] not in first_parent:
                continue
            contexts = (
                (node.get("statusCheckRollup") or {})
                .get("contexts", {})
                .get("nodes", [])
            )
            for context in contexts:
                line = {
                    "Vercel": "Website",
                    "Bain Luck | TestFlight from master": "Apps",
                }.get(context.get("context"))
                if not line:
                    continue
                signal = {
                    "line": line,
                    "commit": node["oid"],
                    "at": context["createdAt"],
                    "kind": "reported",
                    "state": context["state"].lower(),
                    "committed_at": node["committedDate"],
                }
                latest.setdefault(line, signal)
                if signal["state"] == "success":
                    receipts.append(signal)
        older = nodes and instant(nodes[-1]["committedDate"]) < midnight
        found_success = all(
            any(d["line"] == line for d in receipts) for line in ("Website", "Apps")
        )
        if not history["pageInfo"]["hasNextPage"] or (older and found_success):
            break
        cursor = history["pageInfo"]["endCursor"]
    return receipts, latest


def collect(api, previous=None, cache=None, event=None):
    previous, cache, event = previous or {}, cache or {}, event or {}
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(PACIFIC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    coverage = []
    receipts, latest = history_signals(api, midnight)
    try:
        health = read_public("https://api.bainluck.com/api/health")
        deployed = git("rev-parse", "--verify", f"{health['commit']}^{{commit}}")
        if health.get("status") == "ok":
            receipts.append(
                {
                    "line": "Server",
                    "commit": deployed,
                    "at": iso(now),
                    "kind": "observed",
                }
            )
    except (urllib.error.URLError, KeyError, subprocess.CalledProcessError):
        coverage.append("Server deployment could not be confirmed.")
    # Every merge newer than the oldest deployed source might still be in Ship.
    # There is no fixed seven/thirty-day cutoff which could hide an old backlog.
    dates = [midnight]
    for line in ("Website", "Apps", "Server"):
        successes = [r for r in receipts if r["line"] == line]
        if not successes:
            raise RuntimeError(
                f"No deployed {line} baseline. Retaining the previous snapshot."
            )
        last = max(successes, key=lambda d: d["at"])
        dates.append(instant(git("show", "-s", "--format=%cI", last["commit"])))
    floor = min(dates)
    summaries = api.pages("pulls?state=open&sort=updated&direction=desc")
    for page in range(1, 1001):
        rows = api.request(
            f"repos/{REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}"
        )
        summaries += [
            p for p in rows if p.get("merged_at") and instant(p["merged_at"]) >= floor
        ]
        if len(rows) < 100 or instant(rows[-1]["updated_at"]) < floor:
            break
    numbers = {p["number"] for p in summaries}
    for old in previous.get("changes", []):
        if old["station"] == "Ship" and old["number"] not in numbers:
            summaries.append(api.request(f"repos/{REPO}/pulls/{old['number']}"))
    affected = {
        (event.get("pull_request") or {}).get("number"),
        (event.get("issue") or {}).get("number"),
    }
    affected.update(
        p["number"] for p in (event.get("workflow_run") or {}).get("pull_requests", [])
    )
    sha = event.get("sha") or (event.get("workflow_run") or {}).get("head_sha")
    full = not event or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    with ThreadPoolExecutor(max_workers=4) as workers:
        pulls = list(
            workers.map(
                lambda p: collect_pull(
                    api,
                    p,
                    cache.get(str(p["number"])),
                    full or p["number"] in affected or p["head"]["sha"] == sha,
                ),
                summaries,
            )
        )
    refresh_open_evidence(api, pulls)
    # A reported live time refines the server observation only after ancestry
    # independently proves this exact merged change was deployed.
    comments = api.pages(f"issues/12779/comments?since={iso(floor)}")
    positions = {
        sha: i
        for i, sha in enumerate(
            git("rev-list", "--first-parent", "origin/master").splitlines()
        )
    }
    for receipt in receipts:
        receipt["contains"] = []
        for pull in pulls:
            if not pull.get("merged_at"):
                continue
            merge_sha = pull["merge_commit_sha"]
            on_main = merge_sha in positions and receipt["commit"] in positions
            included = (
                positions[merge_sha] >= positions[receipt["commit"]]
                if on_main
                else contains(receipt["commit"], merge_sha)
            )
            if included:
                receipt["contains"].append(merge_sha)
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        match = re.search(
            r"\blive\s+#(\d+)\s*\((server|website|apps)\)", comment["body"], re.I
        )
        if not match:
            continue
        number, line = int(match[1]), match[2].title()
        pull = next(
            (p for p in pulls if p["number"] == number and p.get("merged_at")), None
        )
        proof = next(
            (
                r
                for r in receipts
                if r["line"] == line
                and pull
                and pull["merge_commit_sha"] in r["contains"]
            ),
            None,
        )
        if proof and pull["merged_at"] <= comment["created_at"] <= proof["at"]:
            receipts.append(
                {
                    **proof,
                    "at": comment["created_at"],
                    "kind": "reported",
                    "contains": [pull["merge_commit_sha"]],
                }
            )
    runs = api.request(
        f"repos/{REPO}/actions/runs?branch=master&event=push&per_page=30"
    )["workflow_runs"]
    ci = next((r for r in runs if r["name"] == "CI"), None)
    tests = "unknown"
    if ci:
        jobs = api.pages(f"actions/runs/{ci['id']}/jobs", "jobs")
        test_jobs = [
            j for j in jobs if re.search(r"test|build|typecheck", j["name"], re.I)
        ]
        if any(j["conclusion"] in {"failure", "timed_out"} for j in test_jobs):
            tests = "failing"
        elif ci["conclusion"] == "success":
            tests = "passing"
        elif ci["status"] != "completed":
            tests = "running"
    master = {
        "tests": tests,
        "testflight": latest.get("Apps", {}).get("state", "unknown"),
    }
    flight_run = next((r for r in runs if r["name"] == "TestFlight release"), None)
    if flight_run and flight_run["conclusion"] in {"failure", "cancelled", "timed_out"}:
        master["testflight"] = flight_run["conclusion"]
    return {
        "captured_at": iso(datetime.now(timezone.utc)),
        "pulls": pulls,
        "deployments": receipts,
        "master": master,
        "coverage": coverage,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    api = GitHub()
    previous, cache, release = {}, {}, None
    if args.previous:
        previous = json.loads(args.previous.read_text())
    if args.publish:
        try:
            release = api.request(f"repos/{REPO}/releases/tags/{RELEASE}")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        if release:
            assets = api.request(f"repos/{REPO}/releases/{release['id']}/assets")
            asset = next((a for a in assets if a["name"] == "factory.json"), None)
            asset = asset or next(
                (a for a in assets if a["name"] == "factory-next.json"), None
            )
            if asset:
                previous = read_public(
                    asset["browser_download_url"] + "?v=" + asset["updated_at"]
                )
                cache = previous.pop("_collector", {})
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text()) if event_path else None
    snapshot = collect(api, previous, cache, event)
    result = build(snapshot, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_text(json.dumps(snapshot, indent=2) + "\n")
    if args.publish:
        if release is None:
            release = api.request(
                f"repos/{REPO}/releases",
                {
                    "tag_name": RELEASE,
                    "target_commitish": git("rev-parse", "origin/master"),
                    "name": "The Factory data",
                    "body": "Public event snapshots for /factory.",
                    "make_latest": "false",
                    "prerelease": True,
                },
                method="POST",
            )
        result["_collector"] = {str(p["number"]): p for p in snapshot["pulls"]}
        args.output.write_text(json.dumps(result, separators=(",", ":")) + "\n")
        # gh uses the SAME built-in token as every API call. Upload completes
        # before the stable-name swap. Readers retain their previous ISR page
        # during the brief swap, rather than interpreting a 404 as an empty floor.
        temporary = args.output.with_name("factory-next.json")
        temporary.write_bytes(args.output.read_bytes())
        subprocess.run(
            [
                "gh",
                "release",
                "upload",
                RELEASE,
                str(temporary),
                "--clobber",
                "--repo",
                REPO,
            ],
            check=True,
        )
        assets = api.request(f"repos/{REPO}/releases/{release['id']}/assets")
        for asset in assets:
            if asset["name"] == "factory.json":
                api.request(
                    f"repos/{REPO}/releases/assets/{asset['id']}", method="DELETE"
                )
        uploaded = next(a for a in assets if a["name"] == "factory-next.json")
        api.request(
            f"repos/{REPO}/releases/assets/{uploaded['id']}",
            {"name": "factory.json"},
            method="PATCH",
        )
    print(
        json.dumps(
            {
                "changes": len(result["changes"]),
                "captured_at": result["generated_at"],
                "published": args.publish,
            }
        )
    )


if __name__ == "__main__":
    main()
