"""
Create GitHub Issues from rage-shake bug reports.

Event-driven: enqueued after each bug report submission.
The issue lands on the project board Inbox so /triage picks it up.

Pure formatting functions live here. The Celery task wrapper lives in
tasks/__init__.py following the same pattern as send_bug_fixed_email_task.
"""

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "alexander-bain/bainluck"
PROJECT_ID = os.environ.get("GITHUB_PROJECT_ID", "PVT_kwHOC0ai9c4BYbAV")
STATUS_FIELD_ID = os.environ.get("GITHUB_STATUS_FIELD_ID", "PVTSSF_lAHOC0ai9c4BYbAVzhTg_gk")
INBOX_OPTION_ID = os.environ.get("GITHUB_INBOX_OPTION_ID", "f75ad846")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://bainluck.com")

CATEGORY_TO_AREA = {
    "ios": "area:native",
    "ui": "area:frontend",
    "data_quality": "area:data",
    "performance": "area:backend",
    "feature_request": "area:frontend",
}

SEVERITY_TO_PRIORITY = {
    "P0": "priority:p0",
    "P1": "priority:p1",
    "P2": "priority:p2",
    "P3": "priority:p3",
}


def compute_severity(description: str | None) -> str:
    desc = (description or "").lower()
    if re.search(r"data loss|wrong data|incorrect|duplicate|security", desc):
        return "P0"
    if re.search(r"crash|broken|can't|cannot|500|error|blank|missing|won't load", desc):
        return "P1"
    if re.search(r"ugly|weird|minor|typo|color|font|spacing|alignment", desc):
        return "P3"
    return "P2"


def compute_root_cause(description: str | None) -> str:
    desc = (description or "").lower()
    if re.search(r"odds|probability|percent|%|number", desc):
        return "Data display / aggregation issue"
    if re.search(r"chart|graph|axis|line", desc):
        return "Chart rendering issue"
    if re.search(r"load|slow|spinner|blank", desc):
        return "Performance / loading issue"
    if re.search(r"twice|duplicate|repeated", desc):
        return "Duplicate data rendering"
    if re.search(r"source|attribution|kalshi|polymarket|espn", desc):
        return "Source display / attribution issue"
    if re.search(r"layout|overlap|cut off|truncat", desc):
        return "Layout / responsive issue"
    return "UI/display issue"


def format_issue_title(description: str | None) -> str:
    if not description or not description.strip():
        return "[Bug Report] No description (screenshot only)"
    clean = description.strip().replace("\n", " ")
    if len(clean) > 80:
        clean = clean[:77] + "..."
    return f"[Bug Report] {clean}"


def format_issue_body(
    report_id: int,
    description: str | None,
    category: str | None,
    app_state: dict | None,
    has_screenshot: bool,
) -> str:
    desc = description or "(no description)"
    severity = compute_severity(description)
    cat = category or "other"
    root_cause = compute_root_cause(description)

    state = app_state or {}
    platform = state.get("platform", "unknown")
    device = state.get("device_model", "?")
    os_version = state.get("os_version", "?")
    page = state.get("current_page") or state.get("current_tab", "?")
    network = state.get("network", "?")
    user_name = state.get("user_name", "")
    user_id = state.get("user_id", "")
    user_display = user_name if user_name and user_name != "anonymous" else (f"user {user_id}" if user_id else "anonymous")

    admin_url = f"{FRONTEND_URL}/admin/bug-reports"

    lines = [
        "## Bug Report",
        "",
        f"**Severity:** {severity} (auto)  ",
        f"**Category:** {cat} (auto)  ",
        f"**Root Cause (estimated):** {root_cause}",
        "",
        "### Description",
        desc,
        "",
        "### Device Context",
        "| Field | Value |",
        "|-------|-------|",
        f"| Platform | {platform} {os_version}, {device} |",
        f"| Page | {page} |",
        f"| Network | {network} |",
        f"| User | {user_display} |",
        "",
    ]

    if has_screenshot:
        lines.append("### Screenshot")
        lines.append(f"[View screenshot + full app state →]({admin_url})")
        lines.append("")

    lines.append("---")
    lines.append(f"*Auto-created from rage shake (report #{report_id}). [Admin detail →]({admin_url})*")

    return "\n".join(lines)


# #885: reporter provenance. Alex's directive — "clarify whether the shake came
# from me or anyone else; bugs from anyone serious, but feature requests /
# product misunderstandings from anyone else taken with a grain of salt."
def _owner_emails() -> set[str]:
    raw = os.environ.get("ADMIN_USER_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_owner_email(email: str | None) -> bool:
    """True if the reporter's email is an owner/admin email (ADMIN_USER_EMAILS)."""
    if not email:
        return False
    return email.strip().lower() in _owner_emails()


# Categories that are NOT bugs — a feature request / product misunderstanding.
# From a non-owner these are taken "with a grain of salt": no individual issue.
_NON_BUG_CATEGORIES = {"feature_request"}


def should_file_individual_issue(category: str | None, is_owner: bool) -> bool:
    """#885 routing policy. Owner → always an individual issue. Non-owner → an
    individual issue only for BUG categories; a non-owner feature-request /
    product-misunderstanding is NOT filed individually (it stays in the admin
    staging archive / a future weekly digest)."""
    if is_owner:
        return True
    return (category or "") not in _NON_BUG_CATEGORIES


def build_labels(
    category: str | None, severity: str, is_owner: bool = False
) -> list[str]:
    labels = ["bug-report", "needs-agent"]
    area = CATEGORY_TO_AREA.get(category or "")
    if area:
        labels.append(area)
    priority = SEVERITY_TO_PRIORITY.get(severity)
    if priority:
        labels.append(priority)
    # #885: provenance — owner vs external reporter
    labels.append("reporter:owner" if is_owner else "reporter:external")
    return labels


# #975 (#885 follow-up): cross-report dedup. A stable fingerprint of
# page + category + estimated diagnosis. Two DIFFERENT reports of the SAME
# underlying problem share a fingerprint, so the second accretes evidence on the
# first's issue instead of filing a duplicate. The diagnosis (compute_root_cause)
# is included so two unrelated bugs on the same page+category do NOT false-collapse.
def compute_fingerprint(
    app_state: dict | None, category: str | None, description: str | None
) -> str:
    import hashlib

    state = app_state or {}
    page = (state.get("current_page") or state.get("current_tab") or "").strip().lower()
    cat = (category or "other").strip().lower()
    diagnosis = compute_root_cause(description).strip().lower()
    raw = f"{page}|{cat}|{diagnosis}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def comment_on_issue(issue_number: int, body: str) -> None:
    """Append a comment to an existing GitHub issue (recurrence dedup)."""
    resp = httpx.post(
        f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()


def close_issue(issue_number: int, comment: str | None = None) -> None:
    """Close an OPEN GitHub issue, optionally leaving a recovery comment first.

    Used by the shared sentinel filing rail (app/tasks/sentinel_filing.py) for the
    RED→GREEN lifecycle: when a sentinel re-checks GREEN, its canonical open issue
    is commented + closed so the board self-heals. The comment is posted before the
    close so the audit trail (why it closed) survives on the issue timeline. A
    comment failure is non-fatal — the close still proceeds (a closed issue with no
    recovery note is still the correct terminal state)."""
    if comment:
        try:
            comment_on_issue(issue_number, comment)
        except Exception as exc:  # pragma: no cover - defensive, close still runs
            logger.warning("close_issue: recovery comment failed on #%d: %s", issue_number, exc)
    resp = httpx.patch(
        f"https://api.github.com/repos/{REPO}/issues/{issue_number}",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"state": "closed", "state_reason": "completed"},
        timeout=30,
    )
    resp.raise_for_status()


def format_digest_body(reports: list[dict], week_label: str) -> str:
    """#975: roll up the past week's external feature-requests into one issue.

    `reports` is a list of dicts with keys: id, page, description, user_email.
    """
    lines = [
        f"## External feature-requests — week of {week_label}",
        "",
        f"{len(reports)} external (non-owner) feature-request / product-feedback "
        "shake(s) this week. These are NOT individually filed (taken with a grain "
        "of salt per #885); reviewed in aggregate here.",
        "",
        "| Report | Page | Summary |",
        "|--------|------|---------|",
    ]
    for r in reports:
        desc = (r.get("description") or "(no description)").replace("\n", " ").strip()
        if len(desc) > 100:
            desc = desc[:97] + "..."
        page = r.get("page") or "?"
        lines.append(f"| #{r['id']} | {page} | {desc} |")
    lines.append("")
    lines.append("*Auto-generated weekly digest (rage-shake v2, #885/#975).*")
    return "\n".join(lines)


def create_github_issue(title: str, body: str, labels: list[str]) -> tuple[int, str]:
    resp = httpx.post(
        f"https://api.github.com/repos/{REPO}/issues",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"title": title, "body": body, "labels": labels},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["number"], data["node_id"]


def add_to_project_board(issue_node_id: str) -> None:
    query = """
    mutation($projectId: ID!, $contentId: ID!) {
        addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
            item { id }
        }
    }
    """
    resp = httpx.post(
        "https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "query": query,
            "variables": {"projectId": PROJECT_ID, "contentId": issue_node_id},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    item_id = data.get("data", {}).get("addProjectV2ItemById", {}).get("item", {}).get("id")

    if item_id and STATUS_FIELD_ID and INBOX_OPTION_ID:
        _set_project_status(item_id)


def _set_project_status(item_id: str) -> None:
    query = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
        updateProjectV2ItemFieldValue(input: {
            projectId: $projectId,
            itemId: $itemId,
            fieldId: $fieldId,
            value: {singleSelectOptionId: $optionId}
        }) {
            projectV2Item { id }
        }
    }
    """
    resp = httpx.post(
        "https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "query": query,
            "variables": {
                "projectId": PROJECT_ID,
                "itemId": item_id,
                "fieldId": STATUS_FIELD_ID,
                "optionId": INBOX_OPTION_ID,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
