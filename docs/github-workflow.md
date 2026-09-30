# GitHub Workflow

GitHub Issues are the single source of truth for priority, scope, rationale and execution state. Project 1 shows ownership and delivery state. Documents preserve decisions and reference material; they are not another ordered backlog.

See [Product lanes and delivery](lane-workflow.md) for the September 29 ownership and dispatch model. Existing active work and release evidence remain valid. A single `lane:<name>` label routes the next worker; `Delivery owner` retains product accountability.

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
- Blocked
- Parked
- Review / Verify
- Done

Do not create separate projects for Discover, native, latency, or admin. Use labels for those. Cross-cutting work, such as Discover latency, should have both an area label (`area:discover-ranking`) and a type label (`type:perf`).

## Automated Issue Intake (sentinel era)

A growing share of issues are **filed by automation, not by hand**. Several backend systems open evidence-packed issues through the shared `bug_report_github` client, each with fingerprint dedup (a recurring problem updates its existing issue instead of spawning duplicates):

- **Flow Sentinel** (daily) — one issue per failing user-facing flow (search, duplicate events, event completeness, resolved-state, chart density, category/Discover). First real catch was #1085.
- **Grid Sentinel** (daily) — one issue per championship grid (MLB/NBA/NHL) with REAL defects.
- **Calibration Sentinel** (weekly) — one issue per broken calibration cohort.
- **Board Sentinel** (daily) — keeps the BOARD itself honest (Queue #258, extended by Queue #265): scans the WHOLE open Project population for routing invariants and files one deduped board-cleanup issue when board hygiene is RED.
- **Rage-shake bug reports** — user shake / `Cmd+Shift+F` reports that get auto-diagnosed (severity, root cause, category, Claude Code prompt).
- **CI / Sentry alert intake** — GitHub Actions failures and Sentry issues (Sentry intake needs a scoped token: `project:read`, `event:read`, `org:read`).

### Alert lifecycle (Queue #258 — one fingerprint, RED and GREEN)

All sentinels file through the **shared filing rail** (`backend/app/tasks/sentinel_filing.py`), which gives every fingerprint one durable lifecycle so GitHub `Ready` stays a trustworthy execution source:

- **Inbox is temporary intake, not a human backlog.** `alert-intake` cards land in Inbox for triage; they are not owned work until moved to `Ready`.
- **P2 is the default filing priority.** A sentinel escalates to P1/P0 only with threshold evidence embedded in the issue body and an explicit severity reason. The rail **never edits the labels of an existing issue** — a human-prioritized issue is never silently downgraded by a later P2-default re-observation (it is only commented on).
- **Fingerprint dedup on RED.** Each issue body carries a `<sentinel>-fingerprint:<hash>` marker. Before filing, the rail matches the fingerprint against **open `alert-intake` issues via the strongly-consistent REST list** (never the eventually-consistent `/search` index that let 5 dupes through — r252). A recurrence comments the lowest-numbered canonical issue instead of filing a duplicate. The list read is a **typed result** (`OpenIssuesResult{ok,issues,error,truncated}`), so a failed or truncated read is `ok=False` — it is **never** confused with a genuinely empty board. When the dedup source cannot be read, reconciliation performs an explicit `dedup_unknown_no_op` (Queue #266): it never files or closes blind.
- **Create is serialized per fingerprint.** A Redis idempotency claim (`SET NX EX`) plus a final re-read before create means two overlapping RED runs (the daily beat + a manual run) can never both file the same fingerprint — exactly one wins and files; the other returns `filing_deferred` (Queue #266). Degrades to unlocked when Redis is unreachable.
- **Auto-close on GREEN.** When a sentinel re-checks GREEN, the rail comments a recovery note and **closes exactly that fingerprint's canonical open issue** (matched by canonical DECLARATION only — see below — so a human-filed / marker-quoting lookalike is never auto-closed). GREEN with no open issue is a no-op. A later recurrence opens a fresh episode cleanly.
- **UNKNOWN is never GREEN.** An API / rate-limit / auth inability is classified UNKNOWN — it neither files a cleanup accusation nor falsely resolves an open issue. For the Board Sentinel this also covers: truncated REST/GraphQL pagination; a missing Project token; a **structurally malformed GraphQL payload** (a null/absent/wrong-typed `node`/`items`/`nodes`/`pageInfo` is a typed failure, never a "successfully empty board"); a duplicate Project card (whose specific column join is excluded and the run kept UNKNOWN); and the **inner deadline** elapsing. Each goes UNKNOWN, never a false GREEN or a filed accusation.
- **Population completeness is a trust gate.** The Board Sentinel runs **no** board-hygiene check and files/closes **nothing** unless the REST open-issue population read is COMPLETE (Queue #266). A total failure, a truncated read, or a deadline hit → the whole run is UNKNOWN. Only a complete, unambiguous population may RED honestly. (A Project/GraphQL read failure with a complete REST population is different: the column/membership/status checks go UNKNOWN, while the label/body checks on the complete population may still RED.)
- **Canonical-declaration ownership.** A fingerprint is *owned* only by the issue that DECLARES it — the `<marker>:<hash>` immediately followed by the `(dedupe key — do not remove)` annotation, **on a real line** (not inside a fenced code block, a blockquote, an indented code block, or a Markdown table). One shared parser (`sentinel_filing.declared_fingerprints`) backs dedup, recurrence, **and** close, so a board-cleanup or meta issue that merely QUOTES another alert's marker — even a full copied declaration inside an evidence table or code fence — is **not** a second owner and never trips duplicate-detection or auto-close (Queue #266).
- **Repository-safe Project join.** Project membership and Status are joined by (repository, issue number): a same-number issue from another repository can never satisfy Bain Luck membership or supply another repo's Status (Queue #266).
- **Recognized Status required.** An OPEN Project member whose Status is unset OR outside the documented column vocabulary (Inbox / Ready / In Progress / Needs User / Review / Verify / Blocked / Parked / Done) is a REAL routing defect (`missing_status`) — it is on the board but in no execution lane. When Ops adds a column, update `_KNOWN_STATUSES` in `board_sentinel.py` and this list together.
- **48h Inbox *residence* bar.** Any open card whose *time resident in Inbox* exceeds 48h is a Board Sentinel RED (board-wide). Residence is measured from when the sentinel FIRST observed the card in Inbox (persisted in Redis, cleared on exit), **not** the issue's creation date — an old issue just moved into Inbox is not instantly stale, and the first trustworthy scan gives a grace pass (Queue #266).
- **Whole-board population.** Since Queue #265 the Board Sentinel measures **every open Project issue**, not just `alert-intake`. It distinguishes `open_issues_scanned`, `open_project_items`, `open_alert_intake`, a `population_complete` flag, and an Inbox/status breakdown. Alert-only checks (duplicate fingerprints, template P1 share) stay scoped to `alert-intake`; routing checks run board-wide.
- **Board Sentinel checks** (`backend/app/tasks/board_sentinel.py`, thresholds Redis-tunable): duplicate DECLARED open-`alert-intake` fingerprints → target 0; untriaged Inbox **residence** (board-wide) → 48h; default/template P1 share among open `alert-intake` → cap 35% (past a 6-issue floor); blocked/parked cards in Inbox → target 0; any open issue missing every `area:*` label → target 0 (minus a tiny explicit meta allowlist: `epic`/`meta`/`tracking`); label ↔ Status parity for `blocked`/`parked`/`needs-user` in both directions → target 0; `needs-agent` on a blocked/parked card → target 0; any open issue absent from the Project board → target 0; any Project member with no recognized Status → target 0; Ready cards without an owner signal (`needs-agent`/`owner-ready`/`in-progress`/assignee) or under-scoped (< 200-char body) → target 0. Admin: `POST /api/admin/board-sentinel/run`, `GET /api/admin/board-sentinel/last`.
- **Inner deadline.** The board read runs in a worker thread bounded by a 120s inner budget (both paginators self-check the same monotonic deadline), well under the 840/900s Celery limits and short enough that the inline admin route never blocks unbounded. On timeout the run caches an honest UNKNOWN and performs no reconciliation (Queue #266).
- **Project-token requirement.** The whole-board scan reads the Project via the GitHub GraphQL API, which requires the Project-scoped token configured on Heroku. Without it (or without `GITHUB_TOKEN`), the Board Sentinel reports UNKNOWN — it never asserts the board is clean when it could not read it.
- **Cockpit fail-closed.** The cockpit Board tile renders GREEN only for a schema-valid `verdict="green"` payload with a complete, valid population count; a missing / misspelled / future verdict, malformed counts, or an incomplete population renders AMBER/UNKNOWN, never a false "board clean" (Queue #266).

Conventions for these:
- They carry the **`alert-intake`** label (plus `area:*`/`type:*`/`priority:*`), and land in **Inbox** for triage — treat Inbox as the automation firehose, not a human backlog.
- They may be **closed without backlog edits** when stale, superseded, or purely operational — leave a closing comment with the reason (see Maintenance Rules). Sentinels also auto-close their own issues on recovery (above).
- **Hard dependency:** backend issue-filing silently no-ops if `GITHUB_TOKEN` is unset on Heroku. If auto-filing "stops working," check that rail FIRST before debugging filing logic (memory `project_github_token_unset`).
- Full system detail (files, beats, endpoints, thresholds) lives in `docs/architecture-reference.md` → "Reliability Machinery"; the quality-loop framing is in `docs/quality-audit.md` → "Automated Sentinels".

## Work transitions and freshness

Ideas belong in GitHub as `type:idea`; promote only scoped, useful work to Ready. Each implementation issue names a product pillar, visible outcome, acceptance example, current owner and next step. Do not bulk-promote parked ideas or manufacture work to occupy a lane.

Use `scripts/claim_issue.py` for status transitions. It is the existing common entrypoint for Project status, routing labels and owner handoff. Check its `--help` for supported delivery fields. Owners update records at the event that changes them; scheduled model sweeps are not the synchronization mechanism.

- Before editing: resolve file overlaps, claim the issue, and use an isolated worktree.
- When blocked: name the actual dependency, its owner and the next action. Awaiting Apple review does not block unrelated implementation.
- When returning source: record exact source, test evidence and integration requirements. Keep built, merged, released and verified distinct.
- When shipped: preserve platform-specific delivery facts and close only the scope that is complete.
- At repeat/no-change transitions: avoid duplicate comments. Failed or partial writes must be reported honestly and retried from fresh state.

Shopper owns freshness exceptions and dedicated bug discovery; workers own their transitions. The v3 summary projection has one owner, Start App Update Post-Mortem, with V3 update work resolving scope and bottlenecks. `YOUR-TURN` is for actual user actions and decisions, with exact steps.

Historical `docs/backlog.md` and program files are reference only. Do not run the retired backlog-sync workflow as a prerequisite for claiming or shipping work.

## Handoff Execution Lanes (queues, atomic claim, drive mode, cranks)

Beyond the `In Progress` label lock, there is a queue-based execution system in `.claude/handoff/` (full protocol: `.claude/handoff/README.md`). It exists because parallel lanes (interactive sessions, the headless crank, subagents) collided on 2026-06-11 — stashed WIP, skipped priorities, unverified "shipped" claims. This directory lives inside `.claude/` and is **gitignored — never commit it**.

For new build assignments, the runner selects an explicitly lane-routed Ready GitHub issue using `scripts/lane_ready_issue.py`. It starts no model when work is absent, WIP is occupied, or state cannot be read reliably. Existing specific inbox assignments keep their owner; program prose is no longer a fallback priority queue.

A selection is not a lock. Re-read current state, resolve file overlap and claim via `scripts/claim_issue.py` before editing. Preserve active queue/resource ownership and Integrator's sole master merge/deployment authority. Never execute a stale or superseded queue merely because it exists.

Keep focused tests, applicable frontend build/type checks, real native build/runtime evidence when required, and current CI/release gates. No status transition substitutes for those checks. Use exact source evidence, not a historical pass from another tree. Shared Xcode/simulator capacity is coordinated separately from source-file ownership.

See [Product lanes and delivery](lane-workflow.md) for WIP, handoff and safe adoption rules. This supersedes the old Fable/QUEUE/SEQUENCE priority-dispatch instructions for future build work, not historical receipts or current claims.

## Agent Usage

Good prompts:

- "Work the next Ready issue explicitly routed to your lane."
- "Triage open `alert-intake` issues and fix the highest-priority one."
- "Find `area:discover-ranking` + `type:quality` issues that are safe to parallelize."
- "Promote the ready Discover backlog items into scoped GitHub issues."

Good agent handoff prompt:

- "Before editing files, claim the GitHub issue with `python3 scripts/claim_issue.py ISSUE_NUMBER \"In Progress\" --owner \"<thread name>\"`; check current `In Progress` issues for overlapping files; when done, move the issue to `Review / Verify` or `Done`."

Before parallel agent work, make sure each issue has a narrow scope and distinct write set.
