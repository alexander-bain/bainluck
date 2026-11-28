#!/usr/bin/env python3
"""Read the floor once and publish only changed content. Standard library only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import urllib.parse

from model import build, instant, iso, public_title, PACIFIC, TRUSTED
from ci_queue import machine_queue
from crew import add_crew_week, add_day_replay
from daily_picture import (
    DAILY_PICTURE_ENABLED, asset_label, asset_name, gallery, metered_picture,
)
from events import add_events
from journeys import add_journeys
from signs import add_signs, switched_off, wrong_numbers
from notes import ModelBudget, make_notes
from speech import make_speech
from signals import LANE_UPDATE_WINDOW, commands_from, crew_posts_from, is_test_file, lane_updates_from

REPO = "alexander-bain/bainluck"
RELEASE = "factory-data"
NOW_LINES_ISSUE_FILE = ".github/now-lines-issue.txt"
NOW_LINES_CUTOVER = instant("2026-11-24T05:00:00Z")  # Nov 23 at 9:00 PM Pacific.
READ_FAILURES = (OSError, HTTPException, ValueError)
FABLE_ACCEPT_SHA = re.compile(
    r"^\*\*Fable(?: look)?(?:\*\*)?[ :—–-]+(?:\*\*)?ACCEPT(?:ED)?\s+at\s+`?([a-f0-9]{7,40})\b",
    re.I,
)
RELEASE_HOLD = re.compile(
    r"(?<!\bnot )(?<!\bno longer )(?<!\bwas )(?<!\bno need to )"
    r"\b(?:holds?(?:\s+(?:the\s+)?merge)?|held|do not merge)\s+(?:"
    r"for\s+(?:the\s+)?1\.0\.8\b"
    r"|until\b[^\n]{0,80}?\b1\.0\.7\b[^\n]{0,40}?\b(?:app store|upload|freeze))",
    re.I,
)


def retry_read(read):
    for next_attempt in (2, 3):
        try:
            return read()
        except READ_FAILURES as error:
            if isinstance(error, urllib.error.HTTPError):
                if error.code != 408 and not 500 <= error.code <= 599:
                    raise
                error.close()
                reason = f"HTTP {error.code}"
            else:
                reason = type(error).__name__
            print(
                f"FACTORY_READ_RETRY {reason}. Attempt {next_attempt} of 3 in 20 seconds.",
                file=sys.stderr,
            )
            time.sleep(20)
    return read()


class GitHub:
    def __init__(self, token=None, read_only=True):
        self.token = (
            token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        )
        if not self.token:
            self.token = subprocess.check_output(
                ["gh", "auth", "token"], text=True
            ).strip()
        self.read_only = read_only
        self.api_calls = 0
        self.api_calls_by_resource = {"core": 0, "graphql": 0}
        self.public_reads = 0
        self.rates = {}
        self.lock = threading.Lock()
        self.started_at = time.monotonic()

    def request(self, endpoint, data=None, method=None, binary=None, timeout=30, content_type=None):
        method = method or ("POST" if data is not None or binary is not None else "GET")
        graphql_read = (
            endpoint == "graphql"
            and data
            and not re.search(r"\bmutation\b", data.get("query", ""))
        )
        is_read = method == "GET" or (method == "POST" and graphql_read)
        if self.read_only and not is_read:
            raise RuntimeError("This collector run has read-only API access")
        body = (
            binary
            if binary is not None
            else json.dumps(data).encode() if data is not None else None
        )
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
                "Content-Type": content_type or (
                    "application/octet-stream"
                    if binary is not None
                    else "application/json"
                ),
            },
        )
        def send():
            with self.lock:
                self.api_calls += 1
                self.api_calls_by_resource[
                    "graphql" if endpoint == "graphql" else "core"
                ] += 1
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    self._remember_rate(response.headers)
                    content = response.read()
                return json.loads(content) if content or is_read else None
            except urllib.error.HTTPError as error:
                self._remember_rate(error.headers)
                raise

        return retry_read(send) if is_read else send()

    def _remember_rate(self, headers):
        remaining = headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            with self.lock:
                self.rates[headers.get("X-RateLimit-Resource", "core")] = int(remaining)

    def public_json(self, url):
        def read():
            with self.lock:
                self.public_reads += 1
            return read_public(url)

        return retry_read(read)

    def metrics(self):
        try:
            limits = self.request("rate_limit")["resources"]
            self.rates.setdefault("core", limits["core"]["remaining"])
            self.rates.setdefault("graphql", limits["graphql"]["remaining"])
        except (OSError, HTTPException, ValueError, KeyError):
            # Keep the last response-header budgets if the final meter read fails.
            pass
        return {
            "phase": "collector",
            "github_api_calls": self.api_calls,
            "api_calls_by_resource": self.api_calls_by_resource,
            "public_reads": self.public_reads,
            "rate_limit_remaining": self.rates.get("core"),
            "graphql_remaining": self.rates.get("graphql"),
            "elapsed_seconds": round(time.monotonic() - self.started_at, 2),
        }

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
    fable = body.startswith("**Fable")
    heading = body.partition("\n")[0]
    changes = fable and bool(re.search(r"\bCHANGES\b", heading))
    at_sha = FABLE_ACCEPT_SHA.match(heading) if not changes else None
    return {
        "created_at": comment["created_at"],
        "updated_at": comment["updated_at"],
        "association": comment.get("author_association"),
        "fable_changes": changes,
        **({"fable_accept_sha": at_sha[1].lower()} if at_sha else {}),
        "fable_accept": fable
        and not changes
        and bool(
            re.search(r"\bACCEPT\b|\bno look needed\b", body, re.I)
            or re.search(r"\bACCEPTED\b", heading)
        ),
    }


def hold_for_108(body):
    # Current release instructions sometimes wrap the version in Markdown.
    return bool(RELEASE_HOLD.search(re.sub(r"[`*_]", "", body or "")))


def collect_pull(api, summary, cached=None):
    number = summary["number"]
    core = {
        k: summary.get(k)
        for k in (
            "number",
            "created_at",
            "title",
            "draft",
            "state",
            "updated_at",
            "merged_at",
            "merge_commit_sha",
        )
    }
    core["title"] = public_title(core["title"])
    login = (summary.get("user") or {}).get("login")
    core["title_trusted"] = summary.get("author_association") in TRUSTED and not (
        login
        and re.search(rf"(?<![\w-]){re.escape(login)}(?![\w-])", core["title"], re.I)
    )
    body = summary.get("body") or ""
    core.update(
        branch=summary["head"]["ref"],
        head_sha=summary["head"]["sha"],
        fable_needed=bool(re.search(r"Fable\s*:\s*needed", body, re.I)),
        fable_not_needed=bool(re.search(r"Fable\s*:\s*not needed", body, re.I)),
        hold_for_108=hold_for_108(body),
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
                "merge_from_master": len(c["parents"]) > 1
                and all(
                    contains("origin/master", parent["sha"])
                    for parent in c["parents"][1:]
                ),
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


def annotate_test_commits(api, pulls, cache):
    """Read filenames only for new commits that could extend an earlier review."""
    for pull in pulls:
        if pull.get("merged_at"):
            continue
        reviews = [
            r["submitted_at"]
            for r in pull.get("reviews", [])
            if r.get("state") == "APPROVED" and r.get("submitted_at")
        ]
        accepts = [
            c["created_at"]
            for c in pull.get("comments", [])
            if c.get("fable_accept") and c.get("association") in TRUSTED
        ]
        cutoffs = reviews + accepts
        if not cutoffs:
            continue
        cached_commits = {
            c["sha"]: c for c in cache.get(str(pull["number"]), {}).get("commits", [])
        }
        for commit in pull.get("commits", []):
            old = cached_commits.get(commit["sha"], {})
            if "test_only" in old:
                commit["test_only"] = old["test_only"]
            if (
                commit["parents"] > 1
                and "merge_from_master" not in commit
                and commit["at"] > min(cutoffs)
            ):
                details = api.request(f"repos/{REPO}/commits/{commit['sha']}")
                commit["merge_from_master"] = len(details["parents"]) > 1 and all(
                    contains("origin/master", parent["sha"])
                    for parent in details["parents"][1:]
                )
            if (
                "test_only" not in commit
                and commit["parents"] == 1
                and commit["at"] > min(cutoffs)
            ):
                files = api.pages(f"commits/{commit['sha']}", "files")
                commit["test_only"] = (
                    bool(files)
                    and len(files) < 3000
                    and all(
                        is_test_file(f["filename"])
                        and (
                            not f.get("previous_filename")
                            or is_test_file(f["previous_filename"])
                        )
                        for f in files
                    )
                )


def refresh_open_evidence(api, pulls):
    active = [p for p in pulls if p["state"] == "open"]
    fields = """headRefOid
      timelineItems(last:1,itemTypes:[READY_FOR_REVIEW_EVENT,REOPENED_EVENT]) { nodes {
        ... on ReadyForReviewEvent { createdAt }
        ... on ReopenedEvent { createdAt }
      } }
      reviews(last:100) { totalCount nodes { author { __typename login } state submittedAt commit { oid } } }
      comments(last:100) { totalCount nodes { body createdAt updatedAt authorAssociation } }
      commits(last:1) { nodes { commit { oid statusCheckRollup { contexts(first:100) {
        totalCount nodes {
          ... on CheckRun { name status conclusion startedAt completedAt checkSuite {
            app { slug } workflowRun { workflow { name } }
          } }
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
            intake = node["timelineItems"]["nodes"]
            pull["review_resumed_at"] = intake[0]["createdAt"] if intake else None
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
                    pending = check["state"] in {"PENDING", "EXPECTED"}
                    checks.append(
                        {
                            "name": check["context"],
                            "app": "commit-status",
                            "started_at": check["createdAt"],
                            "finished_at": None if pending else check["createdAt"],
                            "state": "in_progress" if pending else "completed",
                            "conclusion": (
                                "success" if check["state"] == "SUCCESS" else "failure"
                            ),
                        }
                    )
                elif check["name"] != "Update the factory":
                    suite = check["checkSuite"]
                    workflow = (
                        (suite.get("workflowRun") or {}).get("workflow") or {}
                    ).get("name")
                    checks.append(
                        {
                            "name": check["name"],
                            "app": suite["app"]["slug"],
                            "ci": workflow == "CI",
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


def read_now_lines_issue() -> int:
    path = Path(__file__).resolve().parents[2] / NOW_LINES_ISSUE_FILE
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        # The Factory workflow's sparse checkout omits the shared issue file.
        raw = git("show", f"HEAD:{NOW_LINES_ISSUE_FILE}")
    if not re.fullmatch(r"[1-9][0-9]*", raw):
        raise ValueError(f"Invalid issue number in {NOW_LINES_ISSUE_FILE}")
    return int(raw)


def contains(commit, ancestor):
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, commit], capture_output=True
    )
    return result.returncode == 0


def deployment_start(context):
    """Use a provider's explicit start message or the master deploy job."""
    description = (context.get("description") or "").strip().lower()
    if context.get("state") == "PENDING":
        if (
            context.get("context") == "Vercel"
            and description == "vercel is deploying your app"
        ):
            return "Website", context["createdAt"]
        if (
            context.get("context") == "Bain Luck | TestFlight from master"
            and description == "in progress"
        ):
            return "Apps", context["createdAt"]
    suite = context.get("checkSuite") or {}
    workflow = ((suite.get("workflowRun") or {}).get("workflow") or {}).get("name")
    if (
        context.get("name") == "deploy"
        and workflow == "CI"
        and context.get("status") in {"IN_PROGRESS", "COMPLETED"}
        and context.get("conclusion") != "SKIPPED"
        and context.get("startedAt")
    ):
        return "Server", context["startedAt"]
    return None


def history_signals(api, midnight, injury_since):
    """Read actual status contexts on master ancestry, including batched merges."""
    first_parent = set(git("rev-list", "--first-parent", "origin/master").splitlines())
    receipts = []
    starts = []
    latest = {}
    cursor = None
    reports = None
    # Each commit can carry 100 nested checks. Keep pages small enough for
    # GitHub to finish the query and follow the cursor to the same receipts.
    while True:
        query = """query($cursor:String,$reports:String!,$firstPage:Boolean!) {
          reports: search(query:$reports,type:ISSUE,first:100) @include(if:$firstPage) {
            issueCount pageInfo { hasNextPage } nodes { ... on Issue { number title createdAt } }
          }
          repository(owner:"alexander-bain",name:"bainluck") {
          defaultBranchRef { target { ... on Commit { history(first:24,after:$cursor) {
            pageInfo {hasNextPage endCursor} nodes { oid committedDate
              statusCheckRollup { contexts(first:100) { nodes {
                ... on StatusContext { context state createdAt description }
                ... on CheckRun { name status startedAt conclusion checkSuite {
                  workflowRun { workflow { name } }
                } }
              } } }
            }
          } } } }
        } }"""
        search = f'repo:{REPO} is:issue in:title "Wrong number" created:>={injury_since[:10]}'
        data = api.request(
            "graphql",
            {
                "query": query,
                "variables": {
                    "cursor": cursor,
                    "reports": search,
                    "firstPage": cursor is None,
                },
            },
        )
        errors = data.get("errors") or []
        if any(error.get("path", [])[:1] != ["reports"] for error in errors):
            raise RuntimeError("GitHub could not return deployment status history")
        if cursor is None and not errors:
            reports = data["data"].get("reports")
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
                start = deployment_start(context)
                if start:
                    starts.append(
                        {"line": start[0], "at": start[1], "commit": node["oid"]}
                    )
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
    return receipts, latest, starts, reports


def master_checks(api, runs, completed, pulls):
    ci = completed[0] if completed else None
    latest = next((run for run in runs if run["name"] == "CI"), None)
    if latest and (not ci or latest["id"] > ci["id"]):
        if latest["status"] == "completed":
            ci = latest
        elif latest.get("run_attempt", 1) > 1:
            # A rerun removes the failed run from the completed list.
            attempt = latest["run_attempt"] - 1
            endpoint = f"repos/{REPO}/actions/runs/{latest['id']}/attempts/{attempt}"
            ci = None
            try:
                prior = api.request(endpoint, timeout=5)
            except READ_FAILURES:
                prior = None
            if (
                prior
                and prior.get("id") == latest["id"]
                and prior.get("run_attempt") == attempt
                and prior.get("head_sha") == latest["head_sha"]
                and prior.get("status") == "completed"
            ):
                ci = prior

    conclusion = ci.get("conclusion") if ci else None
    result = {
        "tests": {"failure": "failing", "timed_out": "failing", "success": "passing"}.get(
            conclusion, "unknown"
        ),
        "tests_at": ci.get("updated_at") if ci else None,
    }
    if conclusion != "failure" or not ci.get("head_sha") or not ci.get("run_attempt"):
        return result

    # A failed workflow can include jobs unrelated to the server release.
    pull = next(
        (p for p in pulls if p.get("merge_commit_sha") == ci["head_sha"]
         and p.get("merged_at") and any(path.startswith("backend/") for path in p.get("files", ()))),
        None,
    )
    if not pull:
        return result
    endpoint = f"repos/{REPO}/actions/runs/{ci['id']}/attempts/{ci['run_attempt']}/jobs?per_page=100"
    try:
        jobs = api.request(endpoint, timeout=5).get("jobs", [])
    except READ_FAILURES:
        return result
    if (
        any(job.get("name") == "deploy" and job.get("conclusion") == "skipped" for job in jobs)
        and any(
            job.get("conclusion") == "failure"
            and re.fullmatch(r"backend-tests(?: \([0-9]+\))?", job.get("name", ""))
            for job in jobs
        )
    ):
        result["blocked_server_release"] = pull["number"]
    return result


def collect(api, previous=None, cache=None, open_summaries=None):
    previous, cache = previous or {}, cache or {}
    now_lines_issue = read_now_lines_issue()
    now = datetime.now(timezone.utc)
    midnight = now.astimezone(PACIFIC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    coverage = []
    injury_since = previous.get("observed_since") or iso(now)
    receipts, latest, starts, injury_reports = history_signals(
        api, midnight, injury_since
    )
    try:
        health = api.public_json("https://api.bainluck.com/api/health")
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
    summaries = (
        open_summaries
        if open_summaries is not None
        else api.pages("pulls?state=open&sort=updated&direction=desc")
    )
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
        if (
            old["station"] == "Ship"
            and old.get("merged_at")
            and old["number"] not in numbers
        ):
            summaries.append(api.request(f"repos/{REPO}/pulls/{old['number']}"))
            numbers.add(old["number"])
    with ThreadPoolExecutor(max_workers=4) as workers:
        pulls = list(
            workers.map(
                lambda p: collect_pull(
                    api,
                    p,
                    cache.get(str(p["number"])),
                ),
                summaries,
            )
        )
    refresh_open_evidence(api, pulls)
    annotate_test_commits(api, pulls, cache)
    # A reported live time refines the server observation only after ancestry
    # independently proves this exact merged change was deployed.
    last_read = (
        previous.get("generated_at") if previous.get("injury_clock") else injury_since
    )
    command_since = floor
    # Retain the cutover window until a snapshot from this issue is published.
    if previous.get("signals", {}).get("now_lines_issue") != now_lines_issue:
        command_since = min(command_since, NOW_LINES_CUTOVER)
    comments_since = min(command_since, instant(last_read), now - LANE_UPDATE_WINDOW)
    comments = api.pages(f"issues/{now_lines_issue}/comments?since={iso(comments_since)}")
    commands = commands_from(
        comment for comment in comments
        if instant(comment.get("updated_at", comment["created_at"])) >= command_since
    )
    positions = {
        sha: i
        for i, sha in enumerate(
            git("rev-list", "--first-parent", "origin/master").splitlines()
        )
    }
    for receipt in [*receipts, *starts]:
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
    merged = {p["number"]: p for p in pulls if p.get("merged_at")}
    for post in commands:
        if post["kind"] != "live":
            continue
        for number in post["numbers"]:
            pull = merged.get(number)
            if not pull or instant(post["at"]) < instant(pull["merged_at"]):
                continue
            proof = next(
                (
                    r
                    for r in receipts
                    if r["line"] == post["line"]
                    and pull["merge_commit_sha"] in r["contains"]
                    and instant(post["at"]) <= instant(r["at"])
                ),
                None,
            )
            if proof:
                receipts.append(
                    {
                        **proof,
                        "at": post["at"],
                        "kind": "reported",
                        "contains": [pull["merge_commit_sha"]],
                    }
                )
    runs = api.request(
        f"repos/{REPO}/actions/runs?branch=master&event=push&per_page=30"
    )["workflow_runs"]
    completed = api.request(
        f"repos/{REPO}/actions/workflows/ci.yml/runs?branch=master&event=push&status=completed&per_page=1"
    )["workflow_runs"]
    master = {
        **master_checks(api, runs, completed, pulls),
        "now_lines_issue": now_lines_issue,
        "testflight": latest.get("Apps", {}).get("state", "unknown"),
        "successful_runs": [
            {"started_at": run["run_started_at"], "finished_at": run["updated_at"]}
            for run in {r["id"]: r for r in runs + completed}.values()
            if run["name"] == "CI"
            and run["conclusion"] == "success"
            and run.get("run_started_at")
            and run.get("updated_at")
        ],
    }
    try:
        active = api.request(
            f"repos/{REPO}/actions/workflows/ci.yml/runs?branch=master&event=push&status=in_progress&per_page=100"
        )
    except READ_FAILURES:
        active = None
    active_ci = active.get("workflow_runs") if isinstance(active, dict) else None
    if isinstance(active_ci, list) and all(
        isinstance(run, dict) and run.get("status") == "in_progress"
        and isinstance(run.get("run_started_at"), str) and run["run_started_at"]
        for run in active_ci
    ):
        master["oldest_running_ci_at"] = min((run["run_started_at"] for run in active_ci), default=None)
    flight_run = next((r for r in runs if r["name"] == "TestFlight release"), None)
    if flight_run and flight_run["conclusion"] in {"failure", "cancelled", "timed_out"}:
        master["testflight"] = flight_run["conclusion"]
    captured = datetime.now(timezone.utc)
    return {
        "captured_at": iso(captured),
        "crew_posts": crew_posts_from(comments, captured),
        "lane_updates": lane_updates_from(comments, captured),
        "pulls": pulls,
        "deployments": receipts,
        "deploy_starts": starts,
        "injury_source": {
            "from": injury_since,
            "wrong_numbers": wrong_numbers(injury_reports, injury_since),
            "switches": switched_off(comments, injury_since),
        },
        "master": master,
        "coverage": coverage,
        "commands": reconcile_commands(commands, pulls, previous),
        "hold_commands": previous.get("signals", {}).get("commands", []) + commands,
    }


def reconcile_commands(commands, pulls, previous):
    commands = previous.get("signals", {}).get("commands", []) + commands
    latest = {}
    routes = {}
    merged = {p["number"]: p.get("merged_at") for p in pulls}
    for command in sorted(commands, key=lambda c: c["at"]):
        command = dict(command)
        kind, line = command["kind"], command["line"]
        if kind == "stuck":
            for number in command["numbers"]:
                if number in merged and not merged[number]:
                    latest[(kind, number)] = command
            continue
        if kind == "merging":
            command["resolved"] = command.get("resolved", False) or any(
                merged.get(number) and merged[number] >= command["at"]
                for number in command["numbers"]
            )
            # Keep route evidence for each collected change even when another
            # announcement becomes the latest on that line.
            for number in command["numbers"]:
                if number in merged and (
                    not merged[number] or command["at"] <= merged[number]
                ):
                    routes[(number, line)] = command
        latest[(kind, line)] = command

    def command_key(command):
        return (
            command["at"],
            command["kind"],
            command["line"] or "",
            tuple(command.get("numbers", [])),
        )

    retained = {command_key(c): c for c in (*latest.values(), *routes.values())}
    return [retained[key] for key in sorted(retained)]


def floor_changed(previous, current):
    def content(snapshot):
        visible = {
            key: value
            for key, value in snapshot.items()
            if key not in {"generated_at", "read_expires_at", "_collector"}
        }
        visible["changes"] = sorted(
            visible.get("changes", []),
            key=lambda change: (change["number"], change.get("line")),
        )
        visible["jams"] = sorted(
            visible.get("jams", []), key=lambda jam: (jam["key"], jam["started_at"])
        )
        if visible.get("notes"):
            visible["notes"] = {
                k: v for k, v in visible["notes"].items() if k != "snapshot_at"
            }
        return visible

    return not previous or content(previous) != content(current)


def authorize_publication():
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_REF") != "refs/heads/master"
    ):
        raise RuntimeError("Publication requires a master GitHub Actions run")
    if os.environ.get("GITHUB_EVENT_NAME") in {
        "pull_request",
        "pull_request_review",
        "pull_request_target",
    }:
        raise RuntimeError("Pull request events cannot publish")
    if git("branch", "--show-current") != "master" or not contains(
        "origin/master", git("rev-parse", "HEAD")
    ):
        raise RuntimeError("Publication requires the checked-out master commit")
    if not os.environ.get("GITHUB_TOKEN"):
        raise RuntimeError("Publication requires the built-in GitHub token")


def read_published(api):
    try:
        release = api.request(f"repos/{REPO}/releases/tags/{RELEASE}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, {}, {}
        raise
    assets = {a["name"]: a for a in release["assets"]}
    asset = assets.get("factory.json") or assets.get("factory-next.json")
    if not asset:
        return release, {}, {}
    previous = api.public_json(
        asset["browser_download_url"] + "?v=" + asset["updated_at"]
    )
    # Existing v1 releases can be consumed once, then written as two assets.
    cache = previous.pop("_collector", {})
    cache_asset = assets.get("factory-cache.json")
    if cache_asset:
        payload = api.public_json(
            cache_asset["browser_download_url"] + "?v=" + cache_asset["updated_at"]
        )
        if payload.get("generated_at") == previous.get("generated_at"):
            cache = payload.get("pulls", {})
        if "crew_week" in payload:
            cache["crew_week"] = payload["crew_week"]
    return release, previous, cache


def publish_asset(api, release, name, payload):
    temporary = name.removesuffix(".json") + "-next.json"
    assets = api.request(f"repos/{REPO}/releases/{release['id']}/assets")
    for asset in assets:
        if asset["name"] == temporary:
            api.request(f"repos/{REPO}/releases/assets/{asset['id']}", method="DELETE")
    url = release["upload_url"].split("{")[0] + "?name=" + urllib.parse.quote(temporary)
    uploaded = api.request(
        url, method="POST", binary=json.dumps(payload, separators=(",", ":")).encode()
    )
    for asset in assets:
        if asset["name"] == name:
            api.request(f"repos/{REPO}/releases/assets/{asset['id']}", method="DELETE")
    api.request(
        f"repos/{REPO}/releases/assets/{uploaded['id']}", {"name": name}, method="PATCH"
    )


def publish_daily_picture(api, release, picture):
    if not DAILY_PICTURE_ENABLED:
        return None
    record, content = picture
    query = urllib.parse.urlencode({"name": asset_name(record), "label": asset_label(record)})
    url = release["upload_url"].split("{")[0] + "?" + query
    return api.request(url, method="POST", binary=content, content_type="image/webp")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--cache-input", type=Path)
    parser.add_argument("--cache-output", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if args.publish:
        authorize_publication()
    measurement = os.getenv("FACTORY_MEASURE_PICTURE", "false") == "true"
    if measurement and (
        not args.publish or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
    ):
        parser.error("A picture measurement requires a manual master run")
    api = GitHub(read_only=not args.publish)
    note_stats = {
        "tokens_in": 0,
        "tokens_out": 0,
        "day_calls": None,
        "day_cost_usd": None,
    }
    speech_stats = note_stats.copy()
    picture_stats = {"status": "off"}
    try:
        previous = json.loads(args.previous.read_text()) if args.previous else {}
        cache_file = json.loads(args.cache_input.read_text()) if args.cache_input else {}
        cache = cache_file.get("pulls", {})
        if "crew_week" in cache_file:
            cache["crew_week"] = cache_file["crew_week"]
        release, summaries = None, None
        if args.publish:
            release, previous, cache = read_published(api)

        def save_meter(body):
            api.request(
                f"repos/{REPO}/releases/{release['id']}", {"body": body}, method="PATCH"
            )

        key = os.environ.get("OPENAI_API_KEY") if args.publish else None
        budget = ModelBudget((release or {}).get("body") or "", save_meter if release else None)
        if measurement:
            # Keep the sample separate from the public snapshot and gallery.
            picture, picture_stats = metered_picture(previous, budget, key, sample=True)
            if picture:
                _, content = picture
                sample = args.output.with_name("factory-measured-picture.webp")
                try:
                    sample.parent.mkdir(parents=True, exist_ok=True)
                    sample.write_bytes(content)
                except OSError:
                    picture_stats["status"] = "write-failed"
                    raise
            return

        if args.publish:
            summaries = api.pages("pulls?state=open&sort=updated&direction=desc")
        snapshot = collect(api, previous, cache, summaries)
        result = build(snapshot, previous)
        if posts := snapshot.get("crew_posts"):
            result["crew_posts"] = posts
        if updates := snapshot.get("lane_updates"):
            result["lane_updates"] = {
                lane: {**update, "text": public_title(update["text"])}
                for lane, update in updates.items()
            }
        add_events(result, snapshot, previous, cache)
        add_journeys(result, previous)
        add_day_replay(result, previous)
        crew_week = add_crew_week(result, snapshot["pulls"], cache.get("crew_week"))
        add_signs(result, snapshot, previous)
        result["signals"]["checks_queue"] = machine_queue(api, REPO, datetime.now(timezone.utc))

        result["notes"], note_stats = make_notes(
            result, snapshot["pulls"], previous.get("notes") or {}, budget, key
        )
        result["speech"], speech_stats = make_speech(
            result, previous.get("speech") or {}, budget, key
        )
        if args.publish and release:
            assets = list(release.get("assets", []))
            today = budget.now.astimezone(PACIFIC).date().isoformat()
            today_asset = asset_name({"day": today})
            if DAILY_PICTURE_ENABLED and any(
                asset.get("name") == today_asset and asset.get("state") == "uploaded" for asset in assets
            ):
                picture_stats = {"status": "already-published"}
            elif DAILY_PICTURE_ENABLED:
                picture, picture_stats = metered_picture(result, budget, key)
                if picture:
                    try:
                        uploaded = publish_daily_picture(api, release, picture)
                    except urllib.error.HTTPError as error:
                        picture_stats["status"] = (
                            "upload-unconfirmed" if error.code == 408 or error.code >= 500
                            else "upload-failed"
                        )
                    except READ_FAILURES:
                        # A lost reply can follow a successful upload. Keep the
                        # paid reservation and let the next read reconcile it.
                        picture_stats["status"] = "upload-unconfirmed"
                    else:
                        if (
                            isinstance(uploaded, dict)
                            and uploaded.get("name") == asset_name(picture[0])
                            and uploaded.get("label") == asset_label(picture[0])
                            and uploaded.get("state") == "uploaded"
                        ):
                            assets.append(uploaded)
                            picture_stats["status"] = "published"
                        else:
                            picture_stats["status"] = "upload-unconfirmed"
            if records := gallery(assets, budget.now):
                result["pictures"] = records
        meter = budget.state()
        if meter:
            result["model_usage"] = {"day": meter["day"], "calls": meter["calls"]}
        changed = floor_changed(previous, result)
        cache_payload = {
            "schema_version": 1,
            "generated_at": result["generated_at"],
            "pulls": {str(p["number"]): p for p in snapshot["pulls"]},
            "crew_week": crew_week,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, separators=(",", ":")) + "\n")
        if args.capture:
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            args.capture.write_text(json.dumps(snapshot, indent=2) + "\n")
        if args.cache_output:
            args.cache_output.write_text(
                json.dumps(cache_payload, separators=(",", ":")) + "\n"
            )
        if args.publish and changed:
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
            publish_asset(api, release, "factory-cache.json", cache_payload)
            publish_asset(api, release, "factory.json", result)
        print(
            json.dumps(
                {
                    "changes": len(result["changes"]),
                    "captured_at": result["generated_at"],
                    "floor_changed": changed,
                    "published": args.publish and changed,
                }
            )
        )
    finally:
        print("FACTORY_NOTES " + json.dumps(note_stats))
        print("FACTORY_SPEECH " + json.dumps(speech_stats))
        print("FACTORY_PICTURE " + json.dumps(picture_stats))
        print("FACTORY_METRICS " + json.dumps(api.metrics()))


if __name__ == "__main__":
    main()
