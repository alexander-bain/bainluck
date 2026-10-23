# Product lanes and delivery

PILLARS: DISCOVER · MATCHING · FORMATTING · TRUTH.
SHIP: Discover improvements, useful event hubs and live-price fixes reach users promptly, with a visible owner and next action.

Approved by Alex on September 29, 2026. This replaces program-file priority selection for future build assignments. Preserve active work until its normal handoff; do not interrupt workers to change labels. `config/lane-ownership.json` is the tracked responsibility map. Lane names remain compatible with existing launchers; no worktree or process rename is required.

Operational controls, descriptive window names, persistent pause and laptop capacity: [Fleet controls](fleet-controls.md). Those controls do not change ownership or waive release gates.

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

For the queued Live, Watch and Discover ships, one candidate contains at most three already reviewed, compatible ready offers. Three is a cap, not a target: deliberate waiting for hypothetical additional members is zero minutes. Required gates, an active deployment and a named resource or attended hold remain real dependencies; record their owner and release trigger separately from batching. Tests/tools/docs-only riders retain the existing prohibition on a standalone server release. Outages, P0 security and named kickoff-critical work keep their existing priority and do not wait for an ordinary batch. Preserve active work and the sole Integrator; this does not limit productive lane concurrency.

If a member fails, is withdrawn or moves to a new head, form a new ordered composition and validate its resulting source through the existing gates. Previous component or composition results cannot authorize a different merged commit. Full tests on the pushed master remain required before Heroku deployment; component PR success is not a substitute. Drain the next ready candidate afterward, and never cancel active master CI or deployment to create a batch slot.

Prepare acceptance alongside implementation, before the offer: name the exact source, acceptance owner, release/carriage trigger, eligible specimen or explicit unavailable state, concrete command or reader journey, bounded resource/time allowance, stop/cleanup conditions and evidence destination. Refresh the packet when its source or release inputs change; preparation does not establish acceptance.

Once Integrator verifies that trigger, its next handoff is one actionable receipt to the named acceptance owner in the existing inbox, before optional work or cycle cleanup. Include the issue, exact source and release, required worker/surface carriage proof, release and receipt times, prepared acceptance packet and exact next action. Preserve receipt identity and consumed/running state; unchanged evidence does not dispatch duplicate work. Missing carriage or a newer incompatible release holds acceptance with its specific blocker. Keep source, release and reader acceptance separate. CI infrastructure holds use the bounded [recovery disposition](ci-recovery.md); an absent required check remains a hold.

The shared transition command accepts delivery fields, for example:

```sh
python3 scripts/claim_issue.py 123 'Review / Verify' --owner 'Discover' --stage Review --next-step 'Integrator reviews PR; then verify the served card' --evidence 'Exact source and focused results linked in issue'
```

An ownership transfer uses `--expected-owner` with the current exact value; it does not silently replace someone else. `scripts/issue_progress.py ISSUE... --output <generated-path>` renders a bounded progress projection from current records; it creates no timer. Keep existing hand-maintained YOUR-TURN sections separate unless their owner explicitly migrates them.

An idle worker with an eligible Ready assignment is a dispatch defect. Spare coding capacity should fix useful nonblocking bugs when it can do so without distracting v3. Absence of v3 work alone is not a reason to idle; no invented audit, duplicate shopping or self-generated architecture program.

The current coordinator owns the next handoff. When a worker returns a result or a dependency changes, prepare one scoped next bug from existing issues for each eligible idle lane when possible, with an owner, exact files, isolated worktree, acceptance and one lane routing label. Protect current v3 work and shared Native/Xcode/deploy resources; return the lane at a safe boundary when v3 needs it. Overflow PRs queue behind the critical path; cap new work when review or integration WIP backs up. Record actual collisions, resource limits, review capacity or missing scoped work as the reason for a wait. Alex should not have to assign routine follow-through.

Codex availability is not a dependency for already-authorized work or qualified direct offers to Integrator. If Codex is unavailable, continue within existing ownership, scope, review checkpoints and gates, using the existing issue and handoff. Integrator continues its normal qualified-offer handling within existing authority. This adds no merge, release, production or Apple permission; silence never grants approval, a gate waiver, scope expansion or ownership transfer.

If the next action genuinely requires a coordinator decision, record the exact question, source identity, accountable decision owner and reactivation condition once in the existing issue/handoff. Continue other already-authorized nonconflicting work where available; do not repeat unchanged reminders or redispatch the same dependency. Keep status and evidence current for resumption. Use normal handbacks to consume this guidance; do not add outage detection, a replacement coordinator, automatic takeover, a new queue/reporting system or runner restart.

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

For the queued #994/#683/#9483 product fixes, #11075 adds early feedback before
publication. Once #11076 and #11077 are integrated, validate frontend dependencies
with `bash scripts/setup-worktree-deps.sh "$PWD" /path/to/compatible-worktree`
when frontend gates are needed, then run `bash tools/pre-offer-gate.sh origin/master HEAD`
on the clean committed candidate. Borrow only an install the helper validates;
otherwise use an exact-lock private install, never `npm ci` through a shared
dependency symlink. See [the supported early-check scope](https://github.com/alexander-bain/bainluck/blob/fdb317b01456cddf24e859a04ec503ef8c263631/docs/pre-offer-checks.md).
The offer records the builder, exact head/base, early-check receipt, dependency
setup result/source and responsible non-author reviewer. These checks supplement
focused product gates, hosted CI and full exact-composed-tree CI before the
Integrator pushes master; they do not establish delivery or acceptance.

Reuse a qualified independent review for the same source and scope instead of
asking another reviewer to repeat it. Name any additional mandatory review's
distinct scope; security, product, resource and release responsibilities remain
separate. Changed relevant inputs require review of that change. Before editing
an overlapping file, coordinate with its existing claimant: sequence the slices,
or intentionally stack them with explicit dependency and review boundaries.
Keep unrelated features independent. Adoption requires one real product offer
using these checks and an integration/delivery receipt or a named external hold;
documentation or a tooling PR alone does not complete #11078.

Use focused feedback while implementing, affected build/type/integration checks before merging, and broader regression plus representative user journeys on the actual release candidate. Unknown dependency scope takes the broader path. Test selection and caching must preserve coverage, source identity and failures; fewer tests is not itself a success criterion.

Before starting the next expensive final qualification phase and again before offering a candidate, read the existing inbox/context for applicable issue/source review returns and superseding corrections. Bind the disposition to the current source/tree and review scope; a finding on an ancestor still applies when its affected input remains. A concrete `CHANGE REQUIRED` prevents starting the next final phase on that candidate until its owner resolves the correction and applicable review. A frozen SHA does not preserve a reversed acceptance. Pending review alone does not bar useful disjoint or diagnostic work.

Leave an owner decision boundary between independent expensive final phases while relevant review is outstanding. Let healthy running commands finish; retain their actual-source passes, failures and no-results. Do not kill or rewrite active chains to consume a note. Earlier results transfer only when their actual inputs and scope remain valid under existing gate rules. Record the proceed/repair decision in the existing short handoff; add no watcher, collector or duplicate review.

For a queued UI change whose risky assumption needs mounted evidence, author and existing reviewer identify the smallest meaningful positive/negative specimens before broad final qualification. Resolve those focused cases first (for example visible-top versus covered-bottom geometry, a short viewport or actual large text when relevant); source/formula success is not a runtime verdict. Use complete existing fixtures and actual current-source renders, never data reconstructed from screenshots. This is sequencing of affected checks, not a universal device matrix or additional certification. All mandatory final source/build/test/security/release and applicable reader/device checks remain.

Prefer behavior and shared contract tests. Extend existing test families for the same failure class. Consolidate duplicate checks only with retained coverage identified. Keep DB race tests on real DB semantics and genuine UI tests on their UI runtime. Move independent native logic out of simulator-only tests as the corresponding product change warrants it.

Keep the monorepo. Extract coherent components from shared route/view files while implementing an already-queued visible feature: collection membership, feedback, ranking, live state or presentation. Give those components explicit interfaces and direct tests. No speculative repository split or architecture-only initiative.

#9658 and #9659 own the current native harness/provenance improvements; #9670 owns database CI distribution. Do not implement competing variants. Required contexts and deployment authority remain in force.
