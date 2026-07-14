# GitHub Workflow

This repo uses two layers on purpose:

- `docs/backlog.md` is the strategic source of truth: what matters, why it matters, and how workstreams relate.
- GitHub Issues are the execution queue: scoped packets of work that a person, Codex thread, Claude thread, or subagent can pick up.

Avoid duplicating full descriptions in both places. The backlog should link to active issues; issues should link back to the relevant backlog section.

## Labels

Use one or more area labels to describe where the user feels the work:

- `area:discover-ranking`
- `area:event-details`
- `area:sports`
- `area:categories`
- `area:search`
- `area:calibration`
- `area:admin-ops`
- `area:native`
- `area:auth`
- `area:infra`

Use one or more type labels to describe the engineering shape:

- `type:bug`
- `type:feature`
- `type:quality`
- `type:perf`
- `type:design`
- `type:ops`
- `type:docs`
- `type:alert`

Use priority labels sparingly:

- `priority:p0` production broken or user-blocking
- `priority:p1` high user impact
- `priority:p2` important but not urgent
- `priority:p3` polish or cleanup

Use routing labels to manage handoffs:

- `needs-agent` ready for an agent thread
- `in-progress` actively owned by a human/agent thread; avoid overlapping work
- `needs-user` blocked on Alex input or credentials
- `blocked` blocked by another issue or external dependency
- `good-first-agent-task` intentionally small and low-risk
- `alert-intake` generated or updated by alert automation

## Project Board

Use one GitHub Project for the repo, with these statuses:

- Inbox
- Ready
- In Progress
- Needs User
- Review / Verify
- Done

Do not create separate projects for Discover, native, latency, or admin. Use labels for those. Cross-cutting work, such as Discover latency, should have both an area label (`area:discover-ranking`) and a type label (`type:perf`).

## Automated Issue Intake (sentinel era)

A growing share of issues are **filed by automation, not by hand**. Several backend systems open evidence-packed issues through the shared `bug_report_github` client, each with fingerprint dedup (a recurring problem updates its existing issue instead of spawning duplicates):

- **Flow Sentinel** (daily) — one issue per failing user-facing flow (search, duplicate events, event completeness, resolved-state, chart density, category/Discover). First real catch was #1085.
- **Calibration Sentinel** (weekly) — one issue per broken calibration cohort.
- **Rage-shake bug reports** — user shake / `Cmd+Shift+F` reports that get auto-diagnosed (severity, root cause, category, Claude Code prompt).
- **CI / Sentry alert intake** — GitHub Actions failures and Sentry issues (Sentry intake needs a scoped token: `project:read`, `event:read`, `org:read`).

Conventions for these:
- They carry the **`alert-intake`** label (plus `area:*`/`type:*`/`priority:*`), and land in **Inbox** for triage — treat Inbox as the automation firehose, not a human backlog.
- They may be **closed without backlog edits** when stale, superseded, or purely operational — leave a closing comment with the reason (see Maintenance Rules).
- **Hard dependency:** backend issue-filing silently no-ops if `GITHUB_TOKEN` is unset on Heroku. If auto-filing "stops working," check that rail FIRST before debugging filing logic (memory `project_github_token_unset`).
- Full system detail (files, beats, endpoints, thresholds) lives in `docs/architecture-reference.md` → "Reliability Machinery"; the quality-loop framing is in `docs/quality-audit.md` → "Automated Sentinels".

## Backlog Sync

Every active product issue should have a backlog parent, but not every backlog idea needs an issue.

Recommended backlog markers:

- `[idea]` not ready for execution
- `[ready]` scoped enough to become or already have an issue
- `[active]` currently being worked
- `[blocked]` waiting on dependency or user action
- `[shipped]` done; move meaningful items to `docs/completed-features.md`

Example:

```md
### Discover Ranking

Goal: Make the first page consistently surprising, timely, and culturally alive.

Active execution:
- [active] Tune external curator recall. Issue: #123
- [ready] Add daily Kalshi/Polymarket front-page capture. Issue: #124

Ideas:
- [idea] Learn from repeated dismissals by market archetype
```

When an issue opens from a backlog item, add the issue number to the backlog line. When an issue closes, update or remove the backlog line in the same PR/commit if the change is meaningful.

## Maintenance Rules

When working in this repo, keep these invariants true:

- New ideas start in `docs/backlog.md` unless they are already scoped enough for execution.
- Create a GitHub issue when a backlog item has a clear outcome, likely scope, acceptance criteria, and owner/agent path.
- Do not bulk-port vague backlog sections into GitHub. Split only the next actionable slice.
- Every issue created from the backlog should include a `Backlog source` section and an `area:*`, `type:*`, and `priority:*` label when possible.
- GitHub `created` date means the date the item was promoted into the execution queue, not the date the underlying bug/idea was discovered. When porting older backlog items, include the original source date or backlog section date in the issue body.
- Every active product issue should be linked from `docs/backlog.md`, usually under `Active GitHub Execution Queue` or the relevant workstream.
- When closing a product issue, update `docs/backlog.md` in the same change if the backlog line is now shipped, obsolete, or materially changed.
- Alert-generated issues can be closed without backlog edits when they are stale, superseded, or purely operational. Leave a closing comment explaining why.
- Prefer moving project cards to `Ready` only after the issue has enough scope for an agent. Keep rough captures in `Inbox`.
- Treat `In Progress` as an ownership lock. When a human, Codex thread, Claude thread, or subagent starts work, move the issue to `In Progress`, add `in-progress`, remove `needs-agent`, and leave a short comment naming the active owner/context. Do not assign another agent to overlapping files until the issue moves to `Review / Verify` or `Done`.
- Preferred claim command:
  ```bash
  python3 scripts/claim_issue.py 435 "In Progress" --owner "Codex Discover thread"
  ```
  The helper updates the GitHub Project status, labels, and ownership comment together.
- Before spawning subagents, inspect `In Progress` and avoid splitting work across issues that touch the same files or ranking/matching pipeline unless write scopes are explicitly disjoint.

Suggested weekly sweep:

1. List open issues by `needs-agent`, `needs-user`, and `alert-intake`.
2. Close stale alert issues whose head CI/deploy is now green or whose production error is resolved.
3. Promote only the top few ready backlog items into issues.
4. Remove shipped/obsolete items from `Active GitHub Execution Queue`.
5. Keep `docs/completed-features.md` for meaningful shipped product work, not every ops cleanup.

Run the advisory backlog/GitHub sync audit before making those edits:

```bash
python3 scripts/audit_backlog_github_sync.py --dry-run
```

The audit is read-only. It compares `docs/backlog.md` issue references against fetched GitHub issue state, labels, and Project status, then prints drift to review manually. `.github/workflows/backlog-sync-audit.yml` runs the same advisory audit weekly and writes findings to the job summary. Use `--issue-fixture path/to/issues.json` for fixture-based checks and `--fail-on-warn` only in contexts where warning-level drift should fail the command.

## Handoff Execution Lanes (queues, atomic claim, drive mode, cranks)

Beyond the `In Progress` label lock, there is a queue-based execution system in `.claude/handoff/` (full protocol: `.claude/handoff/README.md`). It exists because parallel lanes (interactive sessions, the headless crank, subagents) collided on 2026-06-11 — stashed WIP, skipped priorities, unverified "shipped" claims. This directory lives inside `.claude/` and is **gitignored — never commit it**.

The loop: **Fable** (the Cowork desktop "staging brain") and **Alex** decide priorities together; Fable writes `.claude/handoff/QUEUE.md` (and `QUEUE-2.md` for a disjoint parallel lane); a CLI session runs `/triage` (or `/triage2`), executes the queue end-to-end (claim → implement → gates → push/deploy), writes `REPORT.md`, flips the queue to `done`, and posts a run-log comment on the ops journal issue **#887** (Alex's phone-visible log).

Key rules, all before any repo work:
- **Atomic claim.** The flip-first rule is not atomic (two sessions reading `approved` at the same instant both think they own it — this happened on Queue #180). Claiming now requires: (1) read `status:` — if not `approved`, abort; (2) write `status: running` **and** an `owner:` line (your PID + mode) in the same save; (3) wait ~3s, **re-read**, and abort if the `owner:` line isn't yours (last-writer-wins detection).
- **Drive mode.** When drive mode is ON (Alex at his desk), **headless cranks must not claim** — interactive sessions own the lanes. Cranks check drive-mode state before claiming and exit silently if set. The one exception where a `running` queue executes: the crank that spawned the session already won the atomic claim on the session's behalf (its `owner:` equals `$BAINLUCK_CRANK_CLAIM`).
- **Lane disjointness.** `QUEUE.md` (Lane 1) and `QUEUE-2.md` (Lane 2) must be file-disjoint; use explicit-path `git add` (never `git add -A`/`.`) and check `git log origin/master..HEAD` before committing so a sibling lane's commit doesn't ride your push (gotcha in CLAUDE.md hot-list; catalog #115).
- **Gates are mandatory per item:** claim via `claim_issue.py` (any item with an issue number), backend `test_startup.py` + targeted tests, frontend `npm run build` for FE changes, real `xcodebuild ... build` quoting `BUILD SUCCEEDED` for any `ios/` change, clean `git status`, and the final push's CI run recorded (red or unchecked CI = "PUSHED-CI-PENDING", not shipped).

This lane discipline is the source of truth when it is active; do not execute `SEQUENCE.md` priority items ad-hoc from an interactive plan — they get staged as queues with briefs, gates, and live-proof requirements.

## Agent Usage

Good prompts:

- "Work the oldest open `needs-agent` issue."
- "Triage open `alert-intake` issues and fix the highest-priority one."
- "Find `area:discover-ranking` + `type:quality` issues that are safe to parallelize."
- "Promote the ready Discover backlog items into scoped GitHub issues."

Good agent handoff prompt:

- "Before editing files, claim the GitHub issue with `python3 scripts/claim_issue.py ISSUE_NUMBER \"In Progress\" --owner \"<thread name>\"`; check current `In Progress` issues for overlapping files; when done, move the issue to `Review / Verify` or `Done`."

Before parallel agent work, make sure each issue has a narrow scope and distinct write set.
