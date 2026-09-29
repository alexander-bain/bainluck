#!/usr/bin/env python3
"""Choose one explicitly routed Ready issue; never claim it or launch a model.

Exit 0: print issue number. Exit 1: no eligible work or WIP occupied.
Exit 2: unknown/failed/truncated read. Fail closed on ambiguous state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
QUERY = """query($label:String!) {
 repository(owner:"alexander-bain", name:"bainluck") {
  issues(first:100, states:OPEN, labels:[$label], orderBy:{field:CREATED_AT,direction:ASC}) {
   pageInfo {hasNextPage}
   nodes {
    number createdAt labels(first:100) {pageInfo {hasNextPage} nodes {name}}
    projectItems(first:20) {
     pageInfo {hasNextPage}
     nodes {project {number owner {... on User {login} ... on Organization {login}}}
      fieldValues(first:30) {pageInfo {hasNextPage} nodes {
       ... on ProjectV2ItemFieldSingleSelectValue {name field {... on ProjectV2SingleSelectField {name}}}
      }}
     }
    }
   }
  }
 }
}"""


def select_issue(payload: dict, lane: str) -> int | None:
    if payload.get("errors"):
        raise ValueError("GitHub returned GraphQL errors")
    connection = payload["data"]["repository"]["issues"]
    if connection["pageInfo"]["hasNextPage"] is not False:
        raise ValueError("lane issue read is incomplete")
    ready = []
    occupied = False
    for issue in connection["nodes"]:
        labels = issue["labels"]
        projects = issue["projectItems"]
        if labels["pageInfo"]["hasNextPage"] is not False or projects["pageInfo"]["hasNextPage"] is not False:
            raise ValueError("issue ownership read is incomplete")
        names = {n["name"] for n in labels["nodes"]}
        if f"lane:{lane}" not in names:
            raise ValueError("response contains an unrouted issue")
        # A helper/contributor must not silently steal a second lane's assignment.
        if len([n for n in names if n.startswith("lane:")]) != 1:
            raise ValueError("multiple lane owners on an issue")
        matches = [p for p in projects["nodes"]
                   if p["project"]["number"] == 1
                   and p["project"]["owner"]["login"] == "alexander-bain"]
        if len(matches) != 1:
            raise ValueError("missing or ambiguous execution board item")
        fields = matches[0]["fieldValues"]
        if fields["pageInfo"]["hasNextPage"] is not False:
            raise ValueError("project field read is incomplete")
        statuses = [f["name"] for f in fields["nodes"] if f.get("field", {}).get("name") == "Status"]
        if len(statuses) != 1 or statuses[0] not in {
            "Inbox", "Ready", "In Progress", "Needs User", "Blocked", "Parked", "Review / Verify", "Done"
        }:
            raise ValueError("missing or unknown execution status")
        status = statuses[0]
        if status == "In Progress" or "in-progress" in names:
            occupied = True
        if status != "Ready" or "needs-agent" not in names:
            continue
        if names & {"in-progress", "blocked", "parked", "needs-user"}:
            continue
        priority = next((rank for rank in range(4) if f"priority:p{rank}" in names), 4)
        ready.append((priority, issue["createdAt"], issue["number"]))
    if occupied or not ready:
        return None
    return min(ready)[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lane")
    parser.add_argument("--fixture", type=Path, help="Offline GraphQL fixture; never call GitHub")
    parser.add_argument("--is-build-lane", action="store_true", help="Policy lookup only; no API call")
    args = parser.parse_args()
    try:
        policy = json.loads((ROOT / "config/lane-ownership.json").read_text())
        if not isinstance(policy, dict) or policy.get("schema_version") != 1 or not isinstance(policy.get("lanes"), dict):
            raise ValueError("malformed lane policy")
        entry = policy["lanes"].get(args.lane)
        if not isinstance(entry, dict) or entry.get("mode") not in {"build", "integration", "quality"}:
            raise ValueError("missing or unknown lane policy")
        if entry["mode"] in {"integration", "quality"}:
            return 1
        if args.is_build_lane:
            return 0
        if args.fixture:
            payload = json.loads(args.fixture.read_text())
        else:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={QUERY}", "-f", f"label=lane:{args.lane}"],
                capture_output=True, text=True, timeout=30, check=True,
            )
            payload = json.loads(result.stdout)
        number = select_issue(payload, args.lane)
        if number is None:
            return 1
        print(number)
        return 0
    except (KeyError, AttributeError, TypeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"lane dispatch unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
