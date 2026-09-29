#!/usr/bin/env python3
"""Update one issue at a work transition, verifying each GitHub write.

The host-local lock serializes cooperating callers. GitHub's separate issue and
Project APIs are NOT transactional: a remote writer can still race between a
read and write. We reread before each write and stop on drift/partial failure;
we never claim success or roll back over another writer's work.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

REPO = "alexander-bain/bainluck"
OWNER = "alexander-bain"
PROJECT_NUMBER = "1"
ROUTING_LABELS = {"in-progress", "needs-agent", "needs-user", "blocked", "parked"}
STATUS_LABELS = {
    "Inbox": set(),
    "Ready": {"needs-agent"},
    "In Progress": {"in-progress"},
    "Needs User": {"needs-user"},
    "Review / Verify": set(),
    "Blocked": {"blocked"},
    "Parked": {"parked"},
    "Done": set(),
}
STATUS_TO_LABEL_ACTIONS = {
    status: {"add": sorted(labels), "remove": sorted(ROUTING_LABELS - labels)}
    for status, labels in STATUS_LABELS.items()
}


def _run(args: list[str], *, capture: bool = False) -> str:
    proc = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if proc.returncode:
        raise RuntimeError(f"Command failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout if capture else ""


def _json(args: list[str]) -> Any:
    return json.loads(_run(["gh", *args], capture=True))


def _graphql(query: str, **variables: Any) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]
    payload = _json(args)
    if payload.get("errors") or not payload.get("data"):
        raise RuntimeError(f"GraphQL read failed: {payload.get('errors', payload)}")
    return payload["data"]


def _complete(connection: dict | None, label: str) -> list:
    if not isinstance(connection, dict) or not isinstance(
        connection.get("nodes"), list
    ):
        raise RuntimeError(f"Missing {label}; refusing an incomplete read")
    if connection.get("pageInfo", {}).get("hasNextPage") is not False:
        raise RuntimeError(f"Truncated {label}; refusing an incomplete read")
    return connection["nodes"]


def read_issue(issue_number: int) -> dict:
    """Read exact issue-side Project membership, not a capped board-wide list."""
    owner, repo = REPO.split("/")
    query = """query($owner:String!,$repo:String!,$number:Int!){
      repository(owner:$owner,name:$repo){issue(number:$number){id title url state
        labels(first:100){nodes{name} pageInfo{hasNextPage}}
        comments(last:100){nodes{body}}
        projectItems(first:100){pageInfo{hasNextPage} nodes{id project{number owner{
          ... on User{login} ... on Organization{login}}}
          fieldValues(first:100){pageInfo{hasNextPage} nodes{
            ... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2Field{name}}}
            ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2SingleSelectField{name}}}
          }}}}}}}"""
    issue = (
        _graphql(query, owner=owner, repo=repo, number=issue_number).get("repository")
        or {}
    ).get("issue")
    if not issue:
        raise RuntimeError(f"Issue #{issue_number} not found")
    labels = {node["name"] for node in _complete(issue.get("labels"), "labels")}
    items = [
        node
        for node in _complete(issue.get("projectItems"), "project memberships")
        if str(node["project"]["number"]) == PROJECT_NUMBER
        and node["project"]["owner"]["login"] == OWNER
    ]
    if len(items) > 1:
        raise RuntimeError("Duplicate Project cards; refusing ambiguous status")
    fields = {}
    if items:
        for value in _complete(items[0].get("fieldValues"), "Project fields"):
            if "field" in value:
                fields[value["field"]["name"]] = value.get(
                    "text", value.get("name", "")
                )
    return {
        "number": issue_number,
        "title": issue["title"],
        "url": issue["url"],
        "state": issue["state"],
        "labels": sorted(labels),
        "fields": fields,
        "item_id": items[0]["id"] if items else None,
        "comments": [c["body"] for c in issue["comments"]["nodes"]],
    }


def _project_fields() -> tuple[str, dict]:
    query = """query($owner:String!,$number:Int!){user(login:$owner){projectV2(number:$number){
      id fields(first:100){pageInfo{hasNextPage} nodes{
      ... on ProjectV2Field{id name}
      ... on ProjectV2SingleSelectField{id name options{id name}}
    }}}}}"""
    project = (
        _graphql(query, owner=OWNER, number=PROJECT_NUMBER).get("user") or {}
    ).get("projectV2")
    if not project:
        raise RuntimeError("Project unavailable")
    return project["id"], {
        f["name"]: f
        for f in _complete(project["fields"], "field definitions")
        if "name" in f
    }


def _owner(snapshot: dict) -> str | None:
    if snapshot["fields"].get("Delivery owner"):
        return snapshot["fields"]["Delivery owner"]
    if (
        snapshot["fields"].get("Status") == "In Progress"
        or "in-progress" in snapshot["labels"]
    ):
        for body in reversed(snapshot["comments"]):
            match = re.match(r"Active owner/context: (.+?)\. Marked In Progress", body)
            if match:
                return match[1]
        raise RuntimeError(
            "Active claim has no readable owner; coordinate before updating"
        )
    return None


@contextmanager
def _issue_lock(issue_number: int):
    # Same pathname across worktrees; no process-local or per-checkout lock.
    path = Path(tempfile.gettempdir()) / f"bainluck-issue-{issue_number}.lock"
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _identity(snapshot: dict) -> dict:
    return {
        key: snapshot[key]
        for key in ("state", "labels", "fields", "item_id", "comments")
    }


def set_status(
    issue_number: int,
    status: str,
    *,
    owner: str | None = None,
    comment: str | None = None,
    expected_owner: str | None = None,
    stage: str | None = None,
    next_step: str | None = None,
    outcome: str | None = None,
    evidence: str | None = None,
    release_target: str | None = None,
) -> dict:
    if status not in STATUS_LABELS:
        raise RuntimeError(f"Unknown status {status!r}")
    with _issue_lock(issue_number):
        current = read_issue(issue_number)
        active_owner = _owner(current)
        if expected_owner is not None and active_owner != expected_owner:
            raise RuntimeError(
                f"Owner changed: expected {expected_owner!r}, found {active_owner!r}"
            )
        if active_owner and owner != active_owner and expected_owner != active_owner:
            raise RuntimeError(
                f"Owned by {active_owner!r}; use that --owner or an explicitly coordinated --expected-owner handoff"
            )
        if status == "In Progress" and not (owner or active_owner):
            raise RuntimeError("In Progress requires --owner")
        # Establish ownership before status so a partial claim remains recoverable.
        wanted = {"Delivery owner": owner} if owner is not None else {}
        wanted["Status"] = status
        for key, value in [
            ("Delivery owner", owner),
            ("Delivery stage", stage),
            ("Next step", next_step),
            ("User outcome", outcome),
            ("Evidence checked", evidence),
            ("Release target", release_target),
        ]:
            if value is not None:
                wanted[key] = value
        project_id, definitions = _project_fields()
        for name, value in wanted.items():
            if name not in definitions:
                raise RuntimeError(f"Missing Project field {name!r}; no writes made")
            if "options" in definitions[name] and value not in {
                o["name"] for o in definitions[name]["options"]
            }:
                raise RuntimeError(f"Unknown {name} option {value!r}; no writes made")

        def apply(
            command: list[str], verify, *, changed: tuple[str, ...] = ("fields",)
        ) -> None:
            nonlocal current
            if _identity(read_issue(issue_number)) != _identity(current):
                raise RuntimeError(
                    "Concurrent issue/Project change; stopped before next write"
                )
            _run(command)
            updated = read_issue(issue_number)
            if not verify(updated) or any(
                updated[k] != current[k] for k in _identity(current) if k not in changed
            ):
                raise RuntimeError(
                    "Write readback mismatch; partial update may remain. Inspect issue before retrying"
                )
            current = updated

        if not current["item_id"]:
            apply(
                [
                    "gh",
                    "project",
                    "item-add",
                    PROJECT_NUMBER,
                    "--owner",
                    OWNER,
                    "--url",
                    current["url"],
                ],
                lambda s: bool(s["item_id"]),
                changed=("item_id", "fields"),
            )
            added_owner = _owner(current)
            if added_owner and added_owner != (owner or active_owner):
                raise RuntimeError(
                    "Project membership acquired another owner; stopping"
                )
        for name, value in wanted.items():
            if current["fields"].get(name) == value:
                continue
            field = definitions[name]
            command = [
                "gh",
                "project",
                "item-edit",
                "--project-id",
                project_id,
                "--id",
                current["item_id"],
                "--field-id",
                field["id"],
            ]
            if "options" in field:
                option = next(o["id"] for o in field["options"] if o["name"] == value)
                command += ["--single-select-option-id", option]
            else:
                command += ["--text", value]
            before = dict(current["fields"])
            before[name] = value
            apply(command, lambda s: s["fields"] == before)
        labels = set(current["labels"])
        desired = (labels - ROUTING_LABELS) | STATUS_LABELS[status]
        if labels != desired:
            command = ["gh", "issue", "edit", str(issue_number), "--repo", REPO]
            for label in sorted(desired - labels):
                command += ["--add-label", label]
            for label in sorted(labels - desired):
                command += ["--remove-label", label]
            apply(
                command,
                lambda s: set(s["labels"]) == desired
                and all(s["fields"].get(k) == v for k, v in wanted.items()),
                changed=("labels",),
            )
        body = comment
        if not body and status == "In Progress":
            body = (
                f"Active owner/context: {owner or active_owner}. Marked In Progress as a "
                "collision-avoidance lock; other agents should avoid overlapping work unless coordinated."
            )
        if body and body not in current["comments"]:
            apply(
                [
                    "gh",
                    "issue",
                    "comment",
                    str(issue_number),
                    "--repo",
                    REPO,
                    "--body",
                    body,
                ],
                lambda s: body in s["comments"]
                and all(s["fields"].get(k) == v for k, v in wanted.items()),
                changed=("comments",),
            )
        final = read_issue(issue_number)
        if _identity(final) != _identity(current):
            raise RuntimeError(
                "Concurrent change at final readback; inspect issue before retrying"
            )
        current = final
        if (
            any(current["fields"].get(k) != v for k, v in wanted.items())
            or set(current["labels"]) != desired
        ):
            raise RuntimeError("Final readback mismatch; partial update may remain")
        print(f"Issue #{issue_number} -> {status} (read back)")
        return current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", type=int)
    parser.add_argument("status", choices=list(STATUS_LABELS))
    parser.add_argument(
        "--owner", help="Accountable delivery owner/context (retained across stages)"
    )
    parser.add_argument(
        "--expected-owner", help="Exact previous owner, only for a coordinated handoff"
    )
    parser.add_argument("--comment")
    parser.add_argument("--stage", help="Existing Delivery stage option")
    parser.add_argument("--next-step")
    parser.add_argument("--outcome")
    parser.add_argument("--evidence")
    parser.add_argument("--release-target")
    args = vars(parser.parse_args())
    issue = args.pop("issue")
    try:
        set_status(issue, **args)
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        print(
            f"Status update failed: {exc}\nGitHub writes are not transactional; inspect current state before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
