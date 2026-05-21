# Alert Intake

Bain Luck uses a safe alert intake loop for production errors and failed CI.
The loop creates or updates GitHub issues with enough context for an agent to
investigate, but it does not edit code, commit, push, deploy, or resolve Sentry.

## What It Watches

- GitHub Actions `workflow_run` failures for `CI` and `Social Ground Truth`
- Sentry unresolved prod issues on an hourly schedule
- Manual runs from the `Alert Intake` workflow

## Required GitHub Secrets

The GitHub Actions failure intake works with the built-in `GITHUB_TOKEN`.
Sentry intake also needs these repository secrets:

- `SENTRY_AUTH_TOKEN` with read-only `project:read`, `event:read`, and `org:read`
- `SENTRY_ORG`
- `SENTRY_PROJECT`

If the Sentry token lacks read permission, the workflow fails loudly instead of
silently dropping alerts.

## Dedupe

Issues are deduped with hidden body markers:

- `sentry:<short-id>` for Sentry issues
- `github-actions:<run-id>` for workflow failures

If the same alert appears again while the issue is open, the workflow appends a
comment with the latest context instead of creating another issue.

## Agent Contract

Generated issues include an `Agent Prompt` section. The intended workflow is:

1. Open the GitHub issue.
2. Start a coding-agent thread with the prompt.
3. Confirm whether a newer commit already fixed the alert.
4. Make a narrow fix with focused tests.
5. Push only after verification passes.

This is intentionally conservative. Auto-PR or auto-deploy can be added later,
but only after the intake issues are consistently high-signal.
