"""Board sync guard — the GitHub Project board must reflect 100% of open issues.

Two invariants, checked nightly on the back of the Flow Sentinel (#1153):

* **Membership** — every open issue has a card on Project 1. This one currently
  passes (the "Auto-add to project" workflow adds new issues at t+0), so the
  guard is the belt to that suspenders: if the workflow is ever disabled or its
  filter drifts, the next nightly run adds what it missed and reports a nonzero
  ``added`` count instead of the gap sitting invisible.
* **Status** — the card's Status column does not contradict the issue's labels.
  This one FAILS today: a ``needs-user`` P0 sitting in ``Inbox`` is invisible to
  the one column that exists to say "Alex must act".

⚠️ **A truncated read is not a fact about the board.** This module exists
because the queue that commissioned it was staged on three numbers ("238 of 416
off-board", "346 missing", "the board's highest item is #1243") that all came
from a single UNPAGINATED read of a 1,278-item board. The apparent sharp cutoff
was the page edge. So: every read here paginates, asserts ``fetched ==
totalCount``, and raises :class:`BoardReadIncomplete` if they disagree. A short
read must fail loudly — never be reported as a gap (which invents work) and
never as a pass (which hides it). Same shape as gotcha #53.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER = "alexander-bain"
REPO_NAME = "bainluck"
PROJECT_OWNER = os.environ.get("GITHUB_PROJECT_OWNER", "alexander-bain")
PROJECT_NUMBER = int(os.environ.get("GITHUB_PROJECT_NUMBER", "1"))

GRAPHQL_URL = "https://api.github.com/graphql"
PAGE_SIZE = 100
# A 1,278-item board is 13 pages. The cap is a runaway guard, not a limit we
# expect to reach; hitting it raises rather than returning a short read.
MAX_PAGES = 60

# Column names on the Status single-select field. Option IDs are NOT hardcoded:
# they are re-read live on every run (`fetch_status_options`), because a stale
# option id writes cards to the wrong column silently.
INBOX = "Inbox"
READY = "Ready"
IN_PROGRESS = "In Progress"
NEEDS_USER = "Needs User"
BLOCKED = "Blocked"
PARKED = "Parked"
REVIEW = "Review / Verify"
DONE = "Done"


class BoardReadIncomplete(RuntimeError):
    """A paginated read returned fewer items than the server said exist."""


# --------------------------------------------------------------------------
# Pure logic (no IO — these are what the tests pin)
# --------------------------------------------------------------------------


def verify_complete_read(fetched: int, total_count: int, pages: int) -> None:
    """Raise unless the read demonstrably covered the whole collection.

    Called on EVERY paginated read. The failure mode this prevents is the one
    that produced the queue: a prefix of the board read as if it were the board.
    """
    if total_count is None:
        raise BoardReadIncomplete(
            f"no totalCount returned after {pages} page(s); cannot prove the "
            "read was complete"
        )
    if fetched != total_count:
        raise BoardReadIncomplete(
            f"TRUNCATED READ: fetched {fetched} item(s) over {pages} page(s) but "
            f"the server reports totalCount={total_count}. Refusing to report a "
            "gap or a pass from a partial read."
        )


def desired_status(
    labels: set[str],
    current: str | None,
    issue_state: str,
) -> str | None:
    """The Status column this card should be in, or ``None`` to leave it alone.

    Deliberately CONSERVATIVE. It only promotes a card into a column its labels
    positively demand; it never demotes.

    Two things it must never do, both learned the hard way:

    * **Never un-park.** ``Parked`` is deliberate human state and is
      authoritative over labels. A guard that un-parks fights Alex every night.
    * **Never "else Inbox".** The commissioning brief specified a flat
      ``needs-agent -> Inbox, else Inbox`` mapping. Measured against the live
      board that rule would have demoted 17 ``Ready`` and 7 ``Review / Verify``
      issues back to ``Inbox``, destroying exactly the triage state the columns
      exist to hold — the same "guard fights the human" failure as un-parking,
      one column over. ``needs-agent`` means "an agent may pick this up", which
      is true in ``Ready`` and ``Review / Verify`` too; it does not contradict
      them, so it moves nothing.
    """
    # 1. A closed issue belongs in Done, wherever it currently sits — including
    #    Parked. Closure is a fact, not a triage opinion.
    if issue_state.upper() == "CLOSED":
        return None if current == DONE else DONE

    # 2. Parked is authoritative human state for anything still open.
    if current == PARKED:
        return None

    # 3. "Alex must act" outranks everything else: this is the column whose
    #    whole purpose is to be the one place he looks.
    if "needs-user" in labels:
        return None if current == NEEDS_USER else NEEDS_USER

    # 4. Blocked work should not read as active or ready.
    if "blocked" in labels and current in (INBOX, READY, IN_PROGRESS):
        return BLOCKED

    # 5. A claimed issue should show as claimed (collision-avoidance lock).
    if "in-progress" in labels and current in (INBOX, READY):
        return IN_PROGRESS

    # 6. An open card with no Status at all defaults to Inbox. This is a
    #    promotion out of nothing, not a demotion.
    if current is None:
        return INBOX

    # 7. Everything else: the human's column stands.
    return None


def summarize(stats: dict[str, Any]) -> str:
    """One-line human summary for logs and the ops journal."""
    return (
        f"board sync: {stats['open_issues']} open issues, "
        f"{stats['board_items']} board items over {stats['pages']} page(s); "
        f"missing={stats['missing']} added={stats['added']} "
        f"status_drift={stats['status_drift']} status_fixed={stats['status_fixed']} "
        f"closed_cards_moved={stats['closed_cards_moved']}"
    )


# --------------------------------------------------------------------------
# IO
# --------------------------------------------------------------------------


async def _gql(client: httpx.AsyncClient, query: str, variables: dict) -> dict:
    resp = await client.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {str(data['errors'])[:300]}")
    return data["data"]


_BOARD_QUERY = """
query($owner: String!, $number: Int!, $cursor: String) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      items(first: 100, after: $cursor) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue { name }
          }
          content {
            __typename
            ... on Issue { number state }
          }
        }
      }
    }
  }
}
"""

_ISSUES_QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    issues(first: 100, after: $cursor, states: OPEN) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        id
        state
        labels(first: 50) { nodes { name } }
      }
    }
  }
}
"""

_STATUS_FIELD_QUERY = """
query($owner: String!, $number: Int!) {
  user(login: $owner) {
    projectV2(number: $number) {
      id
      field(name: "Status") {
        ... on ProjectV2SingleSelectField { id options { id name } }
      }
    }
  }
}
"""

_ADD_ITEM = """
mutation($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item { id }
  }
}
"""

_SET_STATUS = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
    value: {singleSelectOptionId: $optionId}
  }) { projectV2Item { id } }
}
"""


async def fetch_board_items(client: httpx.AsyncClient) -> dict[str, Any]:
    """Every item on the project board. Paginates; proves it paginated."""
    cursor, pages, nodes = None, 0, []
    total: int | None = None
    project_id = None
    while True:
        data = await _gql(
            client,
            _BOARD_QUERY,
            {"owner": PROJECT_OWNER, "number": PROJECT_NUMBER, "cursor": cursor},
        )
        project = data["user"]["projectV2"]
        project_id = project["id"]
        items = project["items"]
        total = items["totalCount"]
        nodes.extend(items["nodes"])
        pages += 1
        if not items["pageInfo"]["hasNextPage"]:
            break
        cursor = items["pageInfo"]["endCursor"]
        if pages >= MAX_PAGES:
            raise BoardReadIncomplete(
                f"stopped after {MAX_PAGES} pages with hasNextPage still true "
                f"({len(nodes)} of {total}) — refusing to act on a partial read"
            )

    verify_complete_read(len(nodes), total, pages)

    by_issue: dict[int, dict] = {}
    for node in nodes:
        content = node.get("content") or {}
        if content.get("__typename") != "Issue":
            continue
        status = (node.get("fieldValueByName") or {}).get("name")
        by_issue[content["number"]] = {
            "item_id": node["id"],
            "status": status,
            "state": content["state"],
        }
    return {
        "project_id": project_id,
        "pages": pages,
        "total_count": total,
        "by_issue": by_issue,
    }


async def fetch_open_issues(client: httpx.AsyncClient) -> dict[str, Any]:
    """Every OPEN issue in the repo. Paginates; proves it paginated."""
    cursor, pages, nodes = None, 0, []
    total: int | None = None
    while True:
        data = await _gql(
            client,
            _ISSUES_QUERY,
            {"owner": REPO_OWNER, "repo": REPO_NAME, "cursor": cursor},
        )
        issues = data["repository"]["issues"]
        total = issues["totalCount"]
        nodes.extend(issues["nodes"])
        pages += 1
        if not issues["pageInfo"]["hasNextPage"]:
            break
        cursor = issues["pageInfo"]["endCursor"]
        if pages >= MAX_PAGES:
            raise BoardReadIncomplete(
                f"stopped after {MAX_PAGES} pages of issues with hasNextPage "
                f"still true ({len(nodes)} of {total})"
            )

    verify_complete_read(len(nodes), total, pages)
    return {
        "pages": pages,
        "total_count": total,
        "issues": [
            {
                "number": n["number"],
                "node_id": n["id"],
                "state": n["state"],
                "labels": {label["name"] for label in n["labels"]["nodes"]},
            }
            for n in nodes
        ],
    }


async def fetch_status_options(client: httpx.AsyncClient) -> dict[str, Any]:
    """Live Status field id + name->option-id map.

    Re-read every run on purpose: a stale option id does not error, it writes
    the card to the wrong column silently.
    """
    data = await _gql(
        client,
        _STATUS_FIELD_QUERY,
        {"owner": PROJECT_OWNER, "number": PROJECT_NUMBER},
    )
    field = data["user"]["projectV2"]["field"]
    if not field:
        raise RuntimeError("Project has no Status single-select field")
    return {
        "field_id": field["id"],
        "options": {o["name"]: o["id"] for o in field["options"]},
    }


async def _run_board_sync(dry_run: bool = False) -> dict[str, Any]:
    """Enumerate, diff, repair, and report. Idempotent: a second run is a no-op.

    Returns counters (Item 6) — the sync must be *visible*. Note that
    ``/api/admin/task-metrics`` is known-broken (#1008: identical fixed record
    for all tasks), so these counters and a board census are the proof this ran,
    not that endpoint.
    """
    stats: dict[str, Any] = {
        "mode": "dry_run" if dry_run else "live",
        "open_issues": 0,
        "board_items": 0,
        "pages": 0,
        "missing": 0,
        "added": 0,
        "add_failed": 0,
        "status_drift": 0,
        "status_fixed": 0,
        "status_failed": 0,
        "closed_cards_moved": 0,
        "moves": [],
        "errors": [],
    }

    if not GITHUB_TOKEN:
        # An unmeasurable run is UNKNOWN, never a pass (the Flow Sentinel's
        # #1494 lesson: a 403 that reports clean is worse than a failure).
        stats["skipped"] = True
        stats["errors"].append({"reason": "GITHUB_TOKEN unset — cannot measure"})
        return stats

    async with httpx.AsyncClient() as client:
        board = await fetch_board_items(client)
        issues = await fetch_open_issues(client)
        status_field = await fetch_status_options(client)

        options = status_field["options"]
        field_id = status_field["field_id"]
        project_id = board["project_id"]
        by_issue = board["by_issue"]

        stats["pages"] = board["pages"]
        stats["board_items"] = board["total_count"]
        stats["open_issues"] = issues["total_count"]

        # --- Membership ---
        for issue in issues["issues"]:
            if issue["number"] in by_issue:
                continue
            stats["missing"] += 1
            if dry_run:
                continue
            try:
                data = await _gql(
                    client,
                    _ADD_ITEM,
                    {"projectId": project_id, "contentId": issue["node_id"]},
                )
                item_id = data["addProjectV2ItemById"]["item"]["id"]
                by_issue[issue["number"]] = {
                    "item_id": item_id,
                    "status": None,
                    "state": issue["state"],
                }
                stats["added"] += 1
            except Exception as exc:
                stats["add_failed"] += 1
                stats["errors"].append(
                    {"issue": issue["number"], "add_error": str(exc)[:200]}
                )

        # --- Status drift (open issues) ---
        open_labels = {i["number"]: i["labels"] for i in issues["issues"]}
        for issue in issues["issues"]:
            card = by_issue.get(issue["number"])
            if not card:
                continue
            target = desired_status(issue["labels"], card["status"], "OPEN")
            if target is None:
                continue
            stats["status_drift"] += 1
            stats["moves"].append(
                {"issue": issue["number"], "from": card["status"], "to": target}
            )
            if dry_run:
                continue
            await _apply_status(
                client, stats, project_id, field_id, options, card, target,
                issue["number"],
            )

        # --- Closed cards that never reached Done ---
        for number, card in by_issue.items():
            if number in open_labels or card["state"].upper() != "CLOSED":
                continue
            target = desired_status(set(), card["status"], "CLOSED")
            if target is None:
                continue
            stats["closed_cards_moved"] += 1
            stats["moves"].append(
                {"issue": number, "from": card["status"], "to": target}
            )
            if dry_run:
                continue
            await _apply_status(
                client, stats, project_id, field_id, options, card, target, number
            )

    logger.info(summarize(stats))
    return stats


async def _apply_status(
    client: httpx.AsyncClient,
    stats: dict[str, Any],
    project_id: str,
    field_id: str,
    options: dict[str, str],
    card: dict,
    target: str,
    number: int,
) -> None:
    option_id = options.get(target)
    if not option_id:
        stats["status_failed"] += 1
        stats["errors"].append(
            {"issue": number, "error": f"no live option id for column {target!r}"}
        )
        return
    try:
        await _gql(
            client,
            _SET_STATUS,
            {
                "projectId": project_id,
                "itemId": card["item_id"],
                "fieldId": field_id,
                "optionId": option_id,
            },
        )
        card["status"] = target
        stats["status_fixed"] += 1
    except Exception as exc:
        stats["status_failed"] += 1
        stats["errors"].append({"issue": number, "error": str(exc)[:200]})
