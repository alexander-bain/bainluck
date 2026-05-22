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
- Treat `In Progress` as an ownership lock. When a human, Codex thread, Claude thread, or subagent starts work, move the issue to `In Progress`, remove `needs-agent`, and leave a short comment naming the active owner/context. Do not assign another agent to overlapping files until the issue moves to `Review / Verify` or `Done`.
- Before spawning subagents, inspect `In Progress` and avoid splitting work across issues that touch the same files or ranking/matching pipeline unless write scopes are explicitly disjoint.

Suggested weekly sweep:

1. List open issues by `needs-agent`, `needs-user`, and `alert-intake`.
2. Close stale alert issues whose head CI/deploy is now green or whose production error is resolved.
3. Promote only the top few ready backlog items into issues.
4. Remove shipped/obsolete items from `Active GitHub Execution Queue`.
5. Keep `docs/completed-features.md` for meaningful shipped product work, not every ops cleanup.

## Agent Usage

Good prompts:

- "Work the oldest open `needs-agent` issue."
- "Triage open `alert-intake` issues and fix the highest-priority one."
- "Find `area:discover-ranking` + `type:quality` issues that are safe to parallelize."
- "Promote the ready Discover backlog items into scoped GitHub issues."

Before parallel agent work, make sure each issue has a narrow scope and distinct write set.
