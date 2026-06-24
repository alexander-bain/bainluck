#!/usr/bin/env python3
"""Claim or move a Bain Luck GitHub issue on the execution Project board.

This is intentionally a thin wrapper around `gh` so agent threads can follow the
same lock protocol without memorizing Project field IDs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


REPO = "alexander-bain/bainluck"
OWNER = "alexander-bain"
PROJECT_NUMBER = "1"
STATUS_FIELD = "Status"

STATUS_TO_LABEL_ACTIONS = {
    "In Progress": {
        "add": ["in-progress"],
        "remove": ["needs-agent"],
    },
    "Ready": {
        "add": ["needs-agent"],
        "remove": ["in-progress", "blocked"],
    },
    "Needs User": {
        "add": ["needs-user"],
        "remove": ["needs-agent", "in-progress"],
    },
    "Review / Verify": {
        "add": [],
        "remove": ["needs-agent", "in-progress"],
    },
    "Done": {
        "add": [],
        "remove": ["needs-agent", "in-progress"],
    },
}


def _run(args: list[str], *, capture: bool = False) -> str:
    proc = subprocess.run(
        args,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() if proc.stderr else ""
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(args)}\n{stderr}")
    return proc.stdout if capture and proc.stdout else ""


def _gh_json(args: list[str]) -> Any:
    output = _run(["gh", *args, "--format", "json"], capture=True)
    return json.loads(output)


def _project_fields() -> tuple[str, str, dict[str, str]]:
    project = _gh_json(["project", "list", "--owner", OWNER])
    projects = project.get("projects", [])
    target = next((p for p in projects if str(p.get("number")) == PROJECT_NUMBER), None)
    if not target:
        raise SystemExit(f"Could not find project {PROJECT_NUMBER} for {OWNER}")

    fields = _gh_json(["project", "field-list", PROJECT_NUMBER, "--owner", OWNER]).get("fields", [])
    status_field = next((f for f in fields if f.get("name") == STATUS_FIELD), None)
    if not status_field:
        raise SystemExit(f"Could not find {STATUS_FIELD!r} field on project {PROJECT_NUMBER}")

    options = {o["name"]: o["id"] for o in status_field.get("options", [])}
    return target["id"], status_field["id"], options


def _issue_url(issue_number: int) -> str:
    return f"https://github.com/{REPO}/issues/{issue_number}"


def _graphql_project_item_id(issue_number: int) -> str | None:
    """Resolve the Project item id from the ISSUE side via GraphQL.

    Querying `issue.projectItems` returns only the handful of project items for
    THIS issue, so it works no matter how many items are on the board. The old
    approach (`gh project item-list --limit 200`) silently missed any issue past
    the 200-item cap — and the board now has 400+ items — so freshly-created
    issues' cards never moved.
    """
    owner, repo = REPO.split("/", 1)
    query = (
        "query($owner:String!,$repo:String!,$number:Int!){"
        "repository(owner:$owner,name:$repo){issue(number:$number){"
        "projectItems(first:20){nodes{id project{number}}}}}}"
    )
    output = _run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={issue_number}",
        ],
        capture=True,
    )
    # NOTE: dict.get(k, {}) still returns None when the key exists with a null
    # value (e.g. issue not found → "issue": null), so guard each hop with `or {}`.
    payload = json.loads(output) or {}
    repository = (payload.get("data") or {}).get("repository") or {}
    issue = repository.get("issue") or {}
    nodes = (issue.get("projectItems") or {}).get("nodes") or []
    for node in nodes:
        if str((node.get("project") or {}).get("number")) == PROJECT_NUMBER:
            return node["id"]
    return None


def _project_item_id(issue_number: int) -> str:
    item_id = _graphql_project_item_id(issue_number)
    if item_id:
        return item_id

    # Not on the board yet — add it, then re-resolve from the issue side.
    _run(["gh", "project", "item-add", PROJECT_NUMBER, "--owner", OWNER, "--url", _issue_url(issue_number)])
    item_id = _graphql_project_item_id(issue_number)
    if not item_id:
        raise SystemExit(f"Added issue #{issue_number}, but could not find its project item")
    return item_id


def _edit_labels(issue_number: int, *, add: list[str], remove: list[str]) -> None:
    for label in add:
        _run(["gh", "issue", "edit", str(issue_number), "--repo", REPO, "--add-label", label])
    for label in remove:
        _run(["gh", "issue", "edit", str(issue_number), "--repo", REPO, "--remove-label", label])


def set_status(issue_number: int, status: str, *, owner: str | None, comment: str | None) -> None:
    project_id, field_id, options = _project_fields()
    option_id = options.get(status)
    if not option_id:
        valid = ", ".join(sorted(options))
        raise SystemExit(f"Unknown status {status!r}. Valid statuses: {valid}")

    item_id = _project_item_id(issue_number)
    _run(
        [
            "gh",
            "project",
            "item-edit",
            "--project-id",
            project_id,
            "--id",
            item_id,
            "--field-id",
            field_id,
            "--single-select-option-id",
            option_id,
        ]
    )

    label_actions = STATUS_TO_LABEL_ACTIONS.get(status, {"add": [], "remove": []})
    _edit_labels(issue_number, add=label_actions["add"], remove=label_actions["remove"])

    if comment or status == "In Progress":
        if comment:
            body = comment
        else:
            active_owner = owner or "current agent thread"
            body = (
                f"Active owner/context: {active_owner}. "
                "Marked In Progress as a collision-avoidance lock; other agents should avoid overlapping work unless coordinated."
            )
        _run(["gh", "issue", "comment", str(issue_number), "--repo", REPO, "--body", body])

    print(f"Issue #{issue_number} -> {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Claim or move a Bain Luck GitHub issue.")
    parser.add_argument("issue", type=int, help="GitHub issue number")
    parser.add_argument(
        "status",
        choices=["Inbox", "Ready", "In Progress", "Needs User", "Review / Verify", "Done"],
        help="Project status to set",
    )
    parser.add_argument("--owner", help="Human/agent/context claiming the issue")
    parser.add_argument("--comment", help="Explicit comment body to add")
    args = parser.parse_args()

    set_status(args.issue, args.status, owner=args.owner, comment=args.comment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
