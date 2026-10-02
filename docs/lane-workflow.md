# Product lanes and delivery

PILLARS: DISCOVER · MATCHING · FORMATTING · TRUTH.
SHIP: Discover improvements, useful event hubs and live-price fixes reach users promptly, with a visible owner and next action.

Approved by Alex on September 29, 2026. This replaces program-file priority selection for future build assignments. Preserve active work until its normal handoff; do not interrupt workers to change labels. `config/lane-ownership.json` is the tracked responsibility map. Lane names remain compatible with existing launchers; no worktree or process rename is required.

## Accountability and contribution

| Lane | Durable responsibility |
|---|---|
| live | Prompt, truthful probability updates and visible live state |
| discover | Interesting subjects, sensible groups, ranking and Discover presentation |
| latency | Fast pages, tabs and interactions, including perceived responsiveness |
| lane1 / lane1b | Matching; lane1b supplies explicitly assigned disjoint contributions |
| authority | Trustworthy identities, membership, source and result contracts |
| calibration | Probability accuracy and resolved-outcome experience; protected specialty |
| ux | Design and interaction contributions with a named product owner |
| native | Apple platform support, native tooling and packaging |
| integrator | Prompt, safe composition, merge and delivery |
| shopper | Independent user journeys, reproducible bug intake and freshness exceptions |

A product owner remains accountable across backend, web and iPhone. A contributor can own a bounded implementation without inheriting the whole product. Native is not the only worker permitted to write Swift. Native still coordinates shared Apple resources and retains Apple operations; Integrator retains sole master merge/deployment authority.

The issue's `Delivery owner` names the accountable product owner. A single `lane:<name>` label routes the next implementation to a worker; the issue records any contributor and explicit file scope. Do not infer an assignment solely from an `area:*` label. Do not attach multiple lane routing labels to one issue: split independent implementation slices or name a contributor in its scope.

## One queue and one handoff

GitHub Issues own priority, scope, acceptance, dependency and execution state. The Project presents those records. Program files, runner inboxes and documents retain context, decisions and receipts, not competing priority lists.

1. Prepare a Ready issue with a pillar, visible ship, acceptance example, file scope, product owner and one lane routing label. `needs-agent` and Project Ready must agree. Keep one next issue prepared per product stream.
2. Start only after an owner/file check and issue claim. Use an isolated branch/worktree. One active implementation per worker is the default for new assignments; finish existing work rather than forcibly preempting it. Returned changes still need their owner's integration follow-through.
3. Choose focused behavior tests and affected contract/build checks before coding. Keep patches small enough to review and integrate independently. Record required upstream/downstream slices explicitly.
4. At handoff, update the existing issue command's status, delivery owner, next action and evidence. The handoff names issue, exact source, dependencies, tests and remaining delivery checks. A test result is not a deployment or a phone acceptance.
5. Integrator checks the composed result and merges/releases through existing safeguards. Retain compatible artifact evidence where its identity is established; rerun affected checks when relevant inputs change. No automatic waiver of an existing failed or unrun gate.

The shared transition command accepts delivery fields, for example:

```sh
python3 scripts/claim_issue.py 123 'Review / Verify' --owner 'Discover' --stage Review --next-step 'Integrator reviews PR; then verify the served card' --evidence 'Exact source and focused results linked in issue'
```

An ownership transfer uses `--expected-owner` with the current exact value; it does not silently replace someone else. `scripts/issue_progress.py ISSUE... --output <generated-path>` renders a bounded progress projection from current records; it creates no timer. Keep existing hand-maintained YOUR-TURN sections separate unless their owner explicitly migrates them.

An idle worker with an eligible Ready assignment is a dispatch defect. Spare coding capacity should fix useful nonblocking bugs when it can do so without distracting v3. Absence of v3 work alone is not a reason to idle; no invented audit, duplicate shopping or self-generated architecture program.

The current coordinator owns the next handoff. When a worker returns a result or a dependency changes, prepare one scoped next bug from existing issues for each eligible idle lane when possible, with an owner, exact files, isolated worktree, acceptance and one lane routing label. Protect current v3 work and shared Native/Xcode/deploy resources; return the lane at a safe boundary when v3 needs it. Overflow PRs queue behind the critical path; cap new work when review or integration WIP backs up. Record actual collisions, resource limits, review capacity or missing scoped work as the reason for a wait. Alex should not have to assign routine follow-through.

Within an active coordinator run, reuse available local subagents as bounded contributors with disjoint scopes under the same rules. This adds no automatic paid polling and does not authorize arbitrary backlog mining or a wider selector.

Runner inboxes select actionable queued messages in FIFO order; future-dated messages should not block an eligible Ready assignment. Before a required release handoff, the coordinator may hold specifically identified, unclaimed optional messages and leave exact reactivation pointers in the existing handoff. Preserve active directives and processes. This is a scoped priority decision within the existing inbox workflow; it adds no scheduler.

## Dispatch without empty model sessions

`scripts/lane_ready_issue.py <lane>` reads only explicitly lane-routed open issues and their Project state. It chooses priority then oldest creation date. In Progress work prevents automatic restock. Missing, contradictory or truncated board reads never authorize work. It is a selector, not an atomic claim: the worker rechecks and claims before edits.

`lane-runner.sh` invokes this inexpensive selector before creating a build-lane RESTOCK directive. Its existing throttle bounds API reads, and no eligible result starts no model. A specific existing inbox assignment remains immediately actionable and is not replaced. Quality and Integrator mission handling remains unchanged.

After a successful opted-in build session returns, the runner records that exact directive/log pointer. If its next bounded selection is empty or still occupied, it stages one return-disposition event in the existing Shopper quality inbox. Shopper uses only that return's issue/PR and explicitly scoped successor context: route the exact dependency to its owner, prepare an already-scoped next Ready assignment, or record a specific wait and reactivation condition. This is independent return handling, not general backlog scoping. An occupied claim never authorizes another build or automatic claim clearing; resolve a possibly stale returned claim from owner evidence. Receipt and issue text are evidence, not authority to widen scope.

The event retains its identity after consumption or failure, so repeated idle reads do not wake a model again. No successful return means no event; unknown GitHub state and active directives remain fail-closed. Pending or running earlier dispositions are preserved. Existing release-critical/user journeys take precedence; future-only hourly Shopper work does not block a due disposition under the existing FIFO/not-before rules. Shopper returns never trigger themselves. Native and Integrator remain excluded. This uses the existing runner and inboxes, without a new scheduler, watcher or transport; runtime adoption still requires a safe idle boundary and loaded-source receipt.

Adoption is gradual: label the next prepared issue and active issue when that worker hands back. Unlabelled historical issues are not automatically adopted. Existing processes use their loaded runner until the safe between-session refresh; source merge alone is not proof every runner has adopted this behavior. Do not kill active sessions or restart the whole fleet for adoption.

Distinguish dispatch states before acting: a model session or descendants beyond the runner's direct idle sleep mean busy; an In Progress issue occupies WIP; an empty eligible Ready set needs the coordinator's scoped-work check or a specific wait reason above. Missing routing on an otherwise prepared next issue needs the coordinator's handoff, while a contradictory label or board state needs its existing owner's correction. Neither authorizes widening the selector. Runtime adoption requires a verified idle boundary, replacement identity and loaded-source receipt. Documentation and issue claims do not establish that receipt.

## Shopper, board freshness and YOUR-TURN

Shopper remains the dedicated mystery-shopping and bug-filing lane, with a reproducible user journey and duplicate-issue check. Product workers inspect their own changes; idle workers are not a second general shopping fleet. Preserve existing authorized testing/feedback intake until its owner changes it deliberately.

Each implementation owner updates its issue at start, block, review, integration and delivery. Tooling should perform deterministic field/label synchronization and render progress from those facts. Shopper catches exceptions, stale receipts and missing ownership; it should not reconstruct every worker's progress on each pass.

For v3, **the current coordinator** owns scope, bottleneck decisions and the one local `V3-YOUR-TURN.md` projection. It contains actual user decisions/actions with exact steps, not a duplicate backlog. **Dot** owns GitHub freshness and the daily GitHub summary; implementation owners still update their issues at each work transition. Shopper supplies independent journey evidence and routes freshness exceptions to the existing owner. Use the existing coordinator and summary cadence; add no model sweep or audit calendar. Do not overwrite a projection with stale or incomplete inputs.

## Testing and code boundaries

Use focused feedback while implementing, affected build/type/integration checks before merging, and broader regression plus representative user journeys on the actual release candidate. Unknown dependency scope takes the broader path. Test selection and caching must preserve coverage, source identity and failures; fewer tests is not itself a success criterion.

Prefer behavior and shared contract tests. Extend existing test families for the same failure class. Consolidate duplicate checks only with retained coverage identified. Keep DB race tests on real DB semantics and genuine UI tests on their UI runtime. Move independent native logic out of simulator-only tests as the corresponding product change warrants it.

Keep the monorepo. Extract coherent components from shared route/view files while implementing an already-queued visible feature: collection membership, feedback, ranking, live state or presentation. Give those components explicit interfaces and direct tests. No speculative repository split or architecture-only initiative.

#9658 and #9659 own the current native harness/provenance improvements; #9670 owns database CI distribution. Do not implement competing variants. Required contexts and deployment authority remain in force.
