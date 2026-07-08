#!/usr/bin/env python3
"""
Crank Journal — Autonomous Run Log

Posts a summary comment to a pinned GitHub issue after each queue execution
in the Fable ↔ CLI autonomous crank loop.

Usage:
    python crank_journal.py --queue <queue_number> --items <items_json> --commits <commits_json> --ci-run <ci_run_id> --ci-status <ci_status> --branch-head <branch_head_sha>

Environment variables:
    GITHUB_TOKEN: GitHub personal access token with repo scope
    GITHUB_REPOSITORY: Repository in format "owner/repo"
    ISSUE_NUMBER: Pinned issue number to post comments to
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_github_headers():
    """Return headers for GitHub API requests."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def post_comment(owner, repo, issue_number, body):
    """Post a comment to a GitHub issue."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = get_github_headers()
    payload = {"body": body}

    logger.info(f"Posting comment to issue #{issue_number} in {owner}/{repo}")
    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        logger.info(f"Comment posted successfully: {response.json().get('html_url')}")
    else:
        logger.error(f"Failed to post comment: {response.status_code} {response.text}")
        sys.exit(1)


def format_comment(queue_number, items, commits, ci_run_id, ci_status, branch_head):
    """
    Format the summary comment for the crank journal.

    Args:
        queue_number (int): Queue execution number.
        items (list): List of dicts with keys 'number', 'title', 'status' (SHIPPED/BLOCKED/SKIPPED).
        commits (list): List of commit SHAs.
        ci_run_id (str): CI run ID.
        ci_status (str): CI run status (e.g., success, failure, pending).
        branch_head (str): Branch head SHA.

    Returns:
        str: Formatted comment body.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [f"**Queue {queue_number}** — {timestamp}", "", "Items:"]
    for item in items:
        lines.append(f"- #{item['number']} {item['title']} — {item['status']}")

    lines.append("")
    lines.append("Commits:")
    for sha in commits:
        lines.append(f"- {sha}")

    lines.append("")
    lines.append(f"CI: run ID {ci_run_id} — status: {ci_status}")
    lines.append(f"Branch head: {branch_head}")

    return "\n".join(lines)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Post crank journal summary comment")
    parser.add_argument("--queue", type=int, required=True, help="Queue execution number")
    parser.add_argument("--items", type=str, required=True, help="JSON array of items with number, title, status")
    parser.add_argument("--commits", type=str, required=True, help="JSON array of commit SHAs")
    parser.add_argument("--ci-run", type=str, required=True, help="CI run ID")
    parser.add_argument("--ci-status", type=str, required=True, help="CI run status")
    parser.add_argument("--branch-head", type=str, required=True, help="Branch head SHA")
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse JSON inputs
    try:
        items = json.loads(args.items)
        commits = json.loads(args.commits)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        sys.exit(1)

    # Validate items structure
    for item in items:
        if not all(k in item for k in ("number", "title", "status")):
            logger.error(f"Item missing required fields: {item}")
            sys.exit(1)
        if item["status"] not in ("SHIPPED", "BLOCKED", "SKIPPED"):
            logger.error(f"Invalid status '{item['status']}' for item #{item['number']}")
            sys.exit(1)

    # Get repository info from environment
    repo_full = os.environ.get("GITHUB_REPOSITORY")
    if not repo_full:
        logger.error("GITHUB_REPOSITORY environment variable not set")
        sys.exit(1)

    try:
        owner, repo = repo_full.split("/")
    except ValueError:
        logger.error(f"Invalid GITHUB_REPOSITORY format: {repo_full}")
        sys.exit(1)

    issue_number = os.environ.get("ISSUE_NUMBER")
    if not issue_number:
        logger.error("ISSUE_NUMBER environment variable not set")
        sys.exit(1)

    try:
        issue_number = int(issue_number)
    except ValueError:
        logger.error(f"Invalid ISSUE_NUMBER: {issue_number}")
        sys.exit(1)

    # Format and post comment
    body = format_comment(
        queue_number=args.queue,
        items=items,
        commits=commits,
        ci_run_id=args.ci_run,
        ci_status=args.ci_status,
        branch_head=args.branch_head,
    )

    post_comment(owner, repo, issue_number, body)


if __name__ == "__main__":
    main()