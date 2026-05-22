#!/usr/bin/env python3
"""Create Sentry alert rules for Bain Luck production monitoring.

One-shot, idempotent script: checks existing rules by name before creating.
Designed to run from GitHub Actions (where the token has proper scopes) or
locally if you have a token with alerts:write scope.

Requires env vars:
    SENTRY_AUTH_TOKEN  — with project:read + alerts:write scopes
    SENTRY_ORG         — Sentry organization slug
    SENTRY_PROJECT     — Sentry project slug

Usage:
    # Via GitHub Actions (preferred — token scopes already correct):
    gh workflow run setup-sentry-alerts.yml

    # Locally:
    SENTRY_ORG=alexander-bain SENTRY_PROJECT=bainluck \
      SENTRY_AUTH_TOKEN=... python3 scripts/setup_sentry_alerts.py

    # Dry run (show what would be created):
    SENTRY_ORG=alexander-bain SENTRY_PROJECT=bainluck \
      SENTRY_AUTH_TOKEN=... python3 scripts/setup_sentry_alerts.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

SENTRY_BASE = "https://us.sentry.io/api/0"

# ---------------------------------------------------------------------------
# Alert rule definitions
# ---------------------------------------------------------------------------
# Each rule is a dict matching the Sentry POST /projects/{org}/{project}/rules/
# schema. "name" is used for idempotency checks.

ALERT_RULES: list[dict[str, Any]] = [
    {
        "name": "P0: Sustained 503s — possible outage",
        "conditions": [
            {
                "id": "sentry.rules.conditions.event_frequency.EventFrequencyCondition",
                "interval": "5m",
                "value": 10,
            },
        ],
        "filters": [
            {
                "id": "sentry.rules.filters.tagged_event.TaggedEventFilter",
                "key": "status_code",
                "match": "eq",
                "value": "503",
            },
        ],
        "actions": [
            {
                "id": "sentry.mail.actions.NotifyEmailAction",
                "targetType": "IssueOwners",
            },
        ],
        "actionMatch": "all",
        "filterMatch": "all",
        "frequency": 300,  # 5-min cooldown
    },
    {
        "name": "P1: Error rate spike — single issue >100 events in 24h",
        "conditions": [
            {
                "id": "sentry.rules.conditions.event_frequency.EventFrequencyCondition",
                "interval": "1d",
                "value": 100,
            },
        ],
        "filters": [],
        "actions": [
            {
                "id": "sentry.mail.actions.NotifyEmailAction",
                "targetType": "IssueOwners",
            },
        ],
        "actionMatch": "all",
        "filterMatch": "all",
        "frequency": 3600,  # 1-hour cooldown
    },
    {
        "name": "P1: New high-frequency issue — >50 events in 1h",
        "conditions": [
            {
                "id": "sentry.rules.conditions.first_seen_event.FirstSeenEventCondition",
            },
            {
                "id": "sentry.rules.conditions.event_frequency.EventFrequencyCondition",
                "interval": "1h",
                "value": 50,
            },
        ],
        "filters": [],
        "actions": [
            {
                "id": "sentry.mail.actions.NotifyEmailAction",
                "targetType": "IssueOwners",
            },
        ],
        "actionMatch": "all",
        "filterMatch": "all",
        "frequency": 3600,  # 1-hour cooldown
    },
]


# ---------------------------------------------------------------------------
# Sentry API helpers
# ---------------------------------------------------------------------------

def _sentry_request(
    method: str,
    path: str,
    *,
    token: str,
    data: dict | None = None,
) -> Any:
    url = f"{SENTRY_BASE}{path}"
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Sentry API {method} {path} failed: {exc.code}\n{detail}"
        )


def list_rules(org: str, project: str, token: str) -> list[dict]:
    return _sentry_request("GET", f"/projects/{org}/{project}/rules/", token=token)


def create_rule(
    org: str, project: str, token: str, rule: dict[str, Any]
) -> dict:
    return _sentry_request(
        "POST", f"/projects/{org}/{project}/rules/", token=token, data=rule
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Create Sentry alert rules")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making API calls",
    )
    args = parser.parse_args()

    token = os.getenv("SENTRY_AUTH_TOKEN", "")
    org = os.getenv("SENTRY_ORG", "")
    project = os.getenv("SENTRY_PROJECT", "")

    if not token:
        print("ERROR: SENTRY_AUTH_TOKEN is required", file=sys.stderr)
        return 1
    if not org or not project:
        print("ERROR: SENTRY_ORG and SENTRY_PROJECT are required", file=sys.stderr)
        return 1

    print(f"Sentry org={org} project={project}")
    print(f"Rules to configure: {len(ALERT_RULES)}")
    print()

    if args.dry_run:
        for rule in ALERT_RULES:
            print(f"  [DRY RUN] Would create: {rule['name']}")
            print(f"            Conditions: {len(rule['conditions'])}")
            print(f"            Filters: {len(rule['filters'])}")
            print(f"            Cooldown: {rule['frequency']}s")
            print()
        return 0

    # Fetch existing rules for idempotency
    try:
        existing = list_rules(org, project, token)
    except RuntimeError as exc:
        print(f"ERROR listing existing rules: {exc}", file=sys.stderr)
        print(
            "\nThe token likely lacks 'alerts:read' scope. "
            "Create a new token at https://sentry.io/settings/auth-tokens/ "
            "with scopes: project:read, alerts:read, alerts:write",
            file=sys.stderr,
        )
        return 1

    existing_names = {r["name"] for r in existing}
    print(f"Existing rules ({len(existing)}):")
    for r in existing:
        print(f"  - {r['name']} (id={r['id']})")
    print()

    created = 0
    skipped = 0
    failed = 0

    for rule in ALERT_RULES:
        name = rule["name"]
        if name in existing_names:
            print(f"  SKIP (already exists): {name}")
            skipped += 1
            continue

        try:
            result = create_rule(org, project, token, rule)
            print(f"  CREATED: {name} (id={result.get('id', '?')})")
            created += 1
        except RuntimeError as exc:
            print(f"  FAILED: {name}")
            print(f"    {exc}", file=sys.stderr)
            failed += 1

    print()
    print(f"Done: {created} created, {skipped} skipped, {failed} failed")

    if failed:
        return 1

    # Verify by listing all rules
    print()
    print("Verification — all rules after setup:")
    try:
        final_rules = list_rules(org, project, token)
        for r in final_rules:
            print(f"  [{r['id']}] {r['name']}")
    except RuntimeError:
        print("  (could not list rules for verification)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
