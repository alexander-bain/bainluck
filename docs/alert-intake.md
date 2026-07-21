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

## Channel Doctrine (the email/Sentry-only ban)

**No alert class may be email-only or Sentry-only. Board + cockpit, or it does
not count as alerting.** This doctrine was ratified after the THIRD email-only
incident (2026-07: the Polymarket creation freeze, #219E) — a real multi-day
outage that fired only into Sentry and email, where nobody in the execution loop
saw it. Sentry and email are *supplementary*; the load-bearing channels are:

1. **The GitHub board** — a deduped `alert-intake` issue an agent can pick up.
2. **The cockpit** — a RED tile so the state is visible at a glance.

Every watchdog/sentinel that emits an alert MUST wire BOTH:

- **GitHub rail** — file ONE deduped issue per episode via the shared
  `bug_report_github` helpers (`create_github_issue` + `add_to_project_board`),
  deduped by a hidden body fingerprint marker (see the freshness watchdog's
  `_file_watchdog_issue`, patterned on the flow/calibration sentinels and #215E).
- **Cockpit tile** — a RED status the operator sees without opening Sentry.

### Fingerprint on [alert-class, provider], never on the message

Sentry (and any dedup) MUST fingerprint on a STABLE key — `[alert_class,
provider]` — not the human message. The creation-stall message embedded the
staleness HOURS ("6.0h", then "11.5h"), so a single stall episode spawned a new
Sentry issue on every reading = un-triageable noise. Watchdog Sentry events now
set `scope.fingerprint = [alert_class, provider]` (see `_capture_fingerprinted`);
phase-block events group on the STALLED PHASE, not the drifting elapsed seconds.

### Detection caveat: a trickle can mask a freeze

`MAX(created_at)` age is fooled by a trickle — the poly freeze kept creating
~10/day, so newest-age stayed under the 6h threshold and the age-only signal
flapped instead of latching RED. The cockpit creation tile therefore also honors
the watchdog's active stall FLAG (not just the live age). A rate-vs-baseline
creation signal (created-in-last-Nh vs the source's trailing baseline) is the
durable detector for trickle-masked freezes — tracked as a follow-up.
