# PRODUCT BRAIN — the load-bearing judgment for staging Bain Luck lanes
# Purpose: everything an agent (Codex / Fable / Opus) needs to stage work WELL — the rulings AND the WHY behind them.
# This externalizes Fable's private memory into the repo so the sharpest available reasoner can stage. Read this + CLAUDE.md + docs/PRD.md.
# Owner: whoever stages. APPEND-ONLY: add each new ruling as a NEW dated `## RULINGS — <date>` section at the bottom. NEVER regenerate, "consolidate", rewrite, or trim this file wholesale — doing so silently dropped ratified rulings TWICE (see the RE-RESTORED markers below). If you are staging a "docs task", it does not authorize touching this file's existing sections. CI-guarded: backend/tests/test_product_brain_integrity.py turns master red if any ruling section disappears or the doc shrinks below its banked section count.

## HOW TO USE THIS
The queue-file mechanics live in `.claude/handoff/README.md` + `FABLE-STANDIN.md`. THIS doc is the judgment layer: the standing rulings, the reasoning behind them, and the failure modes to avoid. The ordered backlog is `plan_next_10_queues.md`; pre-written specs are in `READY-FIXES.md`; deep strategy in `.claude/handoff/strategy_*.md`.

## THE ONE RULE ABOVE ALL
**Product / taste / ranking / design / calibration-interpretation calls are ALEX'S.** Elicit them via multiple-choice; NEVER guess. If the next step needs a judgment, stage the mechanical/unblocked work and leave a "⚠️ NEEDS ALEX RULING: <question + options>" note. A guessed taste call that shipped had to be reverted (the quantile-bins incident) — Alex would rather a lane idle than ship a guess. Recommendation ≠ ruling; presenting options does NOT authorize acting on your favorite.

## STANDING RULINGS (respect, don't extend; each has its WHY)
1. **THE BLEND IS THE PRODUCT.** One number per question. Source divergence is a DATA BUG to fix, not a feature to show. WHY: the anti-Kalshi thesis — we're the world's honest single guess, not a comparison shopping tool. Deliberate comparison surfaces are the rare exception (category-page spotlights, playoffs source lines), flagged not defaulted. Corollary: the hero and the chart must show the SAME number (the 57-vs-20 bug violated this).
2. **SETTLED MEANS SETTLED.** One system-wide settled language: heroes show winners, cards show results, props show the script GRADED, charts show the completed journey frozen. WHY: a settled thing showing live-looking prices (Tiger in R3, two riders at 90% on a finished stage, a 100% prop rendered live) is the "app isn't doing what it's supposed to" failure Alex hunts.
3. **NO GAMBLING ENTICEMENTS.** Probabilities only — NEVER American odds / betting formats (-150/+130), never dollar volume as social proof. WHY: the positioning thesis. "Probability, not betting. The world's honest guess."
4. **NO SMOOTHING, EVER, on charts.** Movement IS the product; smoothing (bezier, EMA) HIDES real movement = hides a data bug we should fix. Fixed 0-100 axis default; explicit labeled tap-to-zoom for low-prob series (never silent auto-scale). WHY: an ugly jagged line is honest; a smooth one lies.
5. **NOTHING > UNHELPFUL.** Silence beats filler. A commentary box that states the obvious, an empty chart frame, an unexplained "EI" chip — remove it. Annotations are explainability-GATED: name a real cause with confidence, or say nothing. WHY: Alex's repeated dogfood complaint — filler erodes trust faster than absence.
6. **ASSUME OUR BUG BEFORE SOURCE BIAS** (calibration). Order: capture → linkage → grading → denominator/normalization → ONLY THEN source-bias. WHY: proven right by the #251 audit — the "miscalibration" was a normalization artifact (fields summing to 4.56), not sources being wrong. Never stage a "conclude source bias" branch; never re-weight sources before the denominator fixes land.
7. **STORY IS THE RANKING UNIT.** Rank stories, not markets (a tournament = 1 story, a game slate = 1 story). WHY: the Monday-after-a-major bug — WNBA games beat the just-ended World Cup because we ranked individual markets. Group_id is the ranking unit, not just a dedup tool.
8. **INCLUDE EVERYTHING; exclude only phantoms.** We ingest/calibrate ALL markets & props (1.28M calibration outcomes across every shape). The ONLY legit exclusions: never-traded illiquid placeholders (a "50%" ask nobody touched that never resolves true — counting it POISONS calibration) and un-normalized field sums (which we NORMALIZE, not drop). WHY: Alex 2026-07-28 — "why would we exclude anything we don't absolutely have to?" Answer: we don't, except phantoms.

## THE SIX RELIABILITY FAILURE CLASSES (priority 1 — "the app does what it's supposed to")
search miss · unmerged duplicates · missing/illegible event props · stale resolved-state · sub-Kalshi UX · (and the meta: any of these reaching Alex's dogfood before a sentinel catches it). Success = the Flow Sentinel stays green AND Alex can go a fortnight without falling back to Kalshi.

## HOW ALEX WORKS (operational)
- **Fire lanes, not commands.** Alex runs /triage /triage2 /ops (+ lane4=codex) in terminals; he does NOT run curls or repairs. Everything he must do personally = a needs-user issue with LITERAL steps, surfaced in chat (the board alone doesn't get read). NUDGE repeatedly on blockers; don't soften to once-and-done.
- **Elicit judgment via multiple-choice** (AskUserQuestion) — he finds it far easier than open prose and it surfaces richer answers. Options are FOR HIM TO PICK.
- **Fable verifies "is it WORKING" itself** (via Chrome MCP, liberally); Alex is for "is it GOOD" (taste) + native-device checks. Sentinels for detection, not Alex's eyeball.
- **Timezone: Pacific.** Quote clock times in PT.
- **He's fast + happy in structured grading flows** (label-pass, cluster adjudication) — route batch judgment to those, not to prose.

## THE LANES & THE PROTECTED SPLIT
- Lane 1 triage = backend. Lane 2 triage2 = frontend + iOS (every pixel + native — labeling/admin UI stays here for design continuity). Lane 3 ops = read-only prod verification (front-load reads; guardrail taints after ~4-8 credentialed calls; fresh convo per prod-heavy round; prefer the ops-snapshot endpoint). Lane 4 codex = read-only audits + the FENCED eval workshop (writes only backend/scripts/evals/ + tests/evals/, commits `codex:` prefix, NEVER pushes — a Claude lane reviews+pushes).
- Codex is elite at adversarial audits (it found a live admin-takeover in one mission) — point it at CODE, never at rulings.

## GOTCHAS THAT BITE THE STAGING ROLE (mechanics-level ones are in CLAUDE.md's Hot List — reference the # in acceptance criteria)
- NEVER overwrite a `running` queue (corrupts a live session — the #1 historical mistake).
- Don't stage ops-verification same-timestamp as the code it verifies (ops "verifies vapor"). Gate: "if <queue> done, else skip."
- Size queues: 1 substantial + ≤3 small; overflow to the chain.
- Held files are held deliberately (e.g. the TdF Sunday exam) — don't promote early.
- Repairs run through the admin-POST rail (dry-run→apply, census in response), NEVER detached one-offs (gotcha #48 graveyard).

## CURRENT ARC (as of 2026-07-28, update as it moves)
Just shipped: #252 security P0 (auth-bypass closed), L2-179 native concept-card rescue, #251 calibration audit (headline: normalization artifact, not source bias). In flight: #253 running; #254 chained (field normalization + golf-by-shape re-cut + Alex's pre-R4 high-prob calibration cohort); r271 ops (kid-taste extraction + #252 re-verify + the TdF exam scorecard we still owe). Backlog order: plan_next_10_queues.md. Open needs-user: kids'-session notes, iOS #490 glance, watchOS runtime.

## RULINGS — 2026-07-27
- **Play feedback:** Fix old/stale cards at Discover and eval eligibility rather than asking children to classify staleness. Do not change the binary vote design merely to accommodate a defect we control. Reassess “interesting but I need to know more” only after the stale-card fix is live and observed; any later kid-facing wording must be age-appropriate, not internal language such as “need context.”
- **GitHub Project status:** Add separate `Blocked` and `Parked` Status options. `Blocked` means scoped work awaiting a dependency; `Parked` means intentionally deferred. Move those cards out of Inbox accordingly; labels remain routing metadata, not substitutes for column truth.

## STAGING RULES v3 (ratified 2026-07-27 PM — mechanics in .claude/handoff/README.md "Process v3")
- **Rulings runway before deep chains:** batch every pending ⚠️ NEEDS ALEX RULING
  into `.claude/handoff/RULINGS-NEEDED.md`; clear it in ONE MC round before
  staging chains >2 deep. A queue containing an unstated judgment call is a
  staging defect, not a convenience.
- **Premise gate on chained queues:** a queue staged N-deep is a prediction. Its
  Item 0 must re-verify the prediction; PREMISE-BROKEN is an honest report
  state, improvised scope is a violation.
- **Fixture-first for diagnosis-class fixes:** stage the Codex eval/fixture
  mission first; the Claude fix queue consumes it. Never stage a fix queue that
  starts by re-diagnosing what Codex already traced.
- **Review/Verify is a contract, not a parking lot:** staging may not move a
  card to Review/Verify without the evidence bundle (SHA + report queue_id + CI
  + per-area live proof). 73 cards lingered because entry was free.
- **Unattended mutation ceiling:** chains and night runs may apply only
  allowlisted, census-matched, bounded repairs named in the active brief.
  Re-grading stored values NEVER runs unattended (verify-before-regrade; #938a,
  #942).

## RULINGS — 2026-07-27 (evening batch, via Fable MC round)
- **Process v3 ratified in full** (all six autonomy changes as modified in
  Fable's verdicts: premise gate, double-gated zombie reset, auto-close scoped
  to fingerprinted alerts only, rescue rail halved to strict-apply).
- **Rescue-rail allowlist:** `/api/admin/calibration/rescue` and
  `/api/admin/calibration/events-funnel` approved for apply=true under strict
  rules (brief-named + exact census match + bounded rows + evidence to #887).
  Re-grades of stored values remain attended-only, always.
- **First presentation kernel: COHORT-COMPARE.** Same question-shape across
  ontology-generated peer sets (division playoff odds, movie thresholds, Fed
  meetings). Design lane prototypes this before ladder/heatmap, race/field, or
  stage/bracket. Respect blend-is-product; commentary on comparisons is
  data-grounded or silent.
- **Filing defaults: P2 + needs-triage at birth** for all sentinel/watchdog/
  alert-intake issues. Priority is earned at triage. P0 escalation classes
  unchanged. `needs-agent` is applied at triage, not filing.

## RULINGS — 2026-07-28 late MC round (via Fable)
- **Auto-close after GREEN = 24h of continuous GREEN (Review/Verify + alert-intake).** Both Review/Verify cards and sentinel alert-intake issues must observe 24h continuous GREEN before auto-close. RED clears clock. Implementation: Redis `sentinel:filing:first_green:{marker}:{fp}` with 7d TTL, comment on first GREEN and periodic remaining, close only after elapsed >=24h. Project stays Review/Verify until close moves to Done. Rationale: prevents flappy close/reopen on transient GREEN reads; gives human window.
- **Board sentinel owns surface-only REDs for aging + calibration warmth (C35) — does NOT own closure yet.** Review/Verify residence >7d (168h) and calibration cache cold (`bainluck:calibration:main` + last_good missing) or drift (generated_at >2h behind `task_metrics:precompute_calibration_main:last_success_at`) are Board Sentinel REAL defects. They surface in board-sentinel OWN issue and task-health, but MUST NOT auto-close target issues until Alex explicitly says "board sentinel owns closure path" for reviewers. Codex Review/Verify audit stays mechanical.
- **MLB total bases (861 KXMLBTB #802) = Park until football.** No authoritative closing-line source exists for total-bases prop; do not invent one. Park the issue until football-season work when we can revisit source contracts. Document as no-authority + exclude from calibration (do not count as 860K+ phantom that poisons).
- **NCAAB 1H (1696 #816) = Doc as no-authority + exclude.** Same pattern: no authoritative source, doc as no-authority and exclude from calibration population, not a bug.
- **Soccer 3-way draw (#1081?) = Ship 3-way next week.** Closing-draw column requires manual psql migration (gotcha #31) + settlement sync update. Chosen: ship next week, queue after calibration warmth restore, with schema migration acceptance and backfill plan.
- **Native chart UX (Kalshi/ESPN gap) = Faster live + Scrub wins.** Users go to Kalshi/ESPN during big games because our 260pt mirrored -0.55..0.55 delta chart with .monotone smoothing and faint sources (opacity 0.5) is unusable. Choose faster live + scrub: single 0-100 zero-centered? No — keep native live speed via faster chart path + scrub affordance for history, remove smoothing, fix mirrored delta, raise contrast. Design lane owns visuals; backend provides precomputed chart payload with cache.
- **Taint Kit Item 0 mandatory + Rulings Runway clearing before deep chains (Process v3 hardening).** Every prod-heavy queue's Item 0 must be ops-snapshot endpoint + fresh-context subagents capturing ALL evidence later items need (no flagged db-query/admin curls after Item 0). Before staging chain >2 deep, clear RULINGS-NEEDED.md via one batched MC round with Alex. Guardrail taint after ~4-8 admin calls requires fresh terminal and ops-snapshot Taint Kit.
- **Included in calibration population vs excluded — re-ratified:** Include everything except phantoms (never-traded illiquid placeholders + un-normalized field sums that we normalize not drop). MLB total bases and NCAAB 1H are documented no-authority exclusions, not ranking gaps to fill with guesswork.

## RULINGS — 2026-07-30 morning MC round (via Fable) — RE-RESTORED 2026-08-03; ratified 07-30; DO NOT REMOVE (CI-guarded)
- **Source experiments: ESPN predictor + futures endpoints FIRST** (zero-weight shadow; low-context pick — re-present before spend beyond ESPN; NOAA/MoneyPuck/Wikidata unruled, not rejected).
- **Conditional / nested markets: SUPPRESS from all surfaces** until a parent-condition contract ships.
- **Entity-image ambiguity (TMDB): strict score margin**; ambiguous stays gradient-only; no human queue.
- **Event-history completeness (C52/#1467): label-first**, derive minima from a labeled set, ratify later.
- **Meaningful-trade prop bar (C51/#1468): trades OR candles, cutoff from measured census**; `threshold_pending` until ratified.
- **Rendered-good-enough closure: BOTH** deterministic checks AND a saved rendered artifact.
- **Live-concept cards: stage the backend concept-enrichment queue** (inline top outcomes; #1486 positive half).

## RULINGS — 2026-07-30 second MC round (via Fable) — RE-RESTORED 2026-08-03; ratified 07-30; DO NOT REMOVE (CI-guarded)
- **Price alone never decides surfacing** (99% ≠ done; suppress only on authoritative lifecycle signals; price-only `effectively_resolved`/`soft_settled_binary` must not masquerade as settlement; no content-policy suppression of near-certain cards is approved).
- **Past-date titles: hide only when title AND linked-event calendar agree**; title alone = review flag.
- **Native stays challenge-first**; no /play browse or new game surfaces until Daily/Friend Challenges are executed well; check /play discoverability on web.
- **No native competition-hub top-level journey**; existing league/sport/tournament routes are the equivalent.

## RULINGS — 2026-07-30 afternoon: THE PRODUCT-FIRST RESET — RE-RESTORED 2026-08-03; DO NOT REMOVE (CI-guarded)
- **VISIBLE-PAYOFF RULE**: every queue states in one plain sentence what Alex will SEE change; no sentence = plumbing, capped at ONE lane-session/day total; verification-of-verification is plumbing.
- **WEEKLY PRODUCT SCOREBOARD**: Monday Chrome sweep (cold-load seconds, time to first card, jank count, visible ships) → _SCOREBOARD-<date>.md; lanes judged on these numbers.
- Priority order (08-01): finish calibration fast (web + native + publish gate), then latency, accuracy, usability.
- Considered, NOT ratified: security done-bar; R/V bankruptcy.

## RULING — 2026-08-03: THE PROGRAM LAYER (via Fable MC; lanes stay as-is)
Lanes remain FILE-COLLISION boundaries (backend / frontend+iOS / ops / eval) — never reorganize lanes by domain. The roadmap layer on top is programs:
- Every queue's frontmatter carries `program:` — `calibration` | `latency` | `native` | `ux` | `plumbing` (extend only by Alex ruling).
- Staging enforces a weekly mix; plumbing keeps its one-session/day cap; **UX floor: ≥1 Lane 2 session per day carries `program: ux`**.
- Monday scoreboard reports cycles-by-program so portfolio drift is a weekly number, not a feeling.

## RULINGS — 2026-08-03 (needs-user queue clear, via MC round)
- **External curation = a bounded auto-applied SOURCE, not a human-gated queue** (#1533/#1534). Polymarket email (and next Kalshi trending, Wikipedia pageviews) feed Discover as bounded, kill-switched, shadow-first signals through one shared "curation intake" (freshness + on-brand + match-confidence gates; cap ±20 / 14-day TTL / `eval_promote:enabled`). The human becomes a weekly filter spot-audit, not a per-pick gate. This is a source under "the blend is the product," NOT a guessed taste call — the distinction the old human-gate conflated.
- **"Well-traded" must be labeled honestly and graded from source volume where present** (#1463/#1530). The `price_moved` bar is a price-inequality, not proof of a trade; Kalshi's ~88% "fail" is ~65% capture artifact. Relabel now; add a **versioned** volume-based bar (`FuturesOutcome.volume>0`, backup open_interest; **NULL=unknown, never untraded**; exclude odds_api/DataGolf; dual-report snapshot+volume). Never let NULL masquerade as untraded.
- **Calibration headline keeps 2:1:1 family weighting** (#1464) — moneyline home+away = 2 rows, spread/total = 1 each. Ruled keep-as-is; revisit only if the combined headline ECE is shown to mislead.
- **Confidence shows as signal bars (1-3)** (#490) — compact cell-signal glyph next to the probability on Discover cards + event detail; thresholds stay data-driven.

## RULINGS — 2026-08-04: OPERATING MODEL v4 (ratified by Alex; supersedes process MECHANICS only — the standing product rulings above are untouched)

**META-RULE that governs this whole model — no new process without a NAMED FAILURE it fixes.** Every element below cites the specific incident/failure class it prevents; an element that cannot name one does not get added, and an existing rule that no longer maps to a live failure is a candidate for removal. WHY: process accretes for its own sake (the v3 hardening churn) until each rule must earn its keep against a real incident.

**FOUR HOMES — one job each, no overlap. A fact lives in exactly one home.**
1. **Board (GitHub Issues/Project) = the SOLE record of priorities, ideas, and completion.** Program parent issues with sub-issues underneath; status via the ruled columns (Inbox / In Progress / Blocked / Parked / Review-Verify / Done). Named failure: docs↔board drift — priority/status/completion lived at once in docs, backlog snapshots, `SEQUENCE.md` and queue files and drifted (the retired `backlog.md`; the repeated "board and SEQUENCE must not drift" incidents). One record ⇒ no drift.
2. **PRODUCT-BRAIN = rulings ONLY** (append-only, CI-guarded). No ordering, no status, no priorities. Named failure: rulings got mixed with ordering and were twice clobbered by "consolidation" rewrites (the RE-RESTORED markers above). Rulings-only + the integrity guard prevents both.
3. **Monday scoreboard = the progress TRUTH.** Cold-load seconds, time-to-first-card, jank count, visible ships, cycles-by-program → `_SCOREBOARD-<date>.md`. Named failure: lanes judged on feeling; portfolio drift was "a feeling, not a number" (the PRODUCT-FIRST RESET). A measured weekly number replaces vibes.
4. **Execution = program worktrees** (defined next).

**EXECUTION CONTAINER:**
- **At most THREE live program worktrees**, all inside a single `~/bainluck-dev/` container (one directory per live program). UX is the pilot; **latency and calibration stand up next**. Named failure: scattered/ad-hoc worktrees collide and break tooling — a worktree outside the writable container was unusable this session (writes hard-denied), and the 2026-06-11 lane collision stashed WIP and skipped priorities. One container + a hard cap fixes discoverability, sandbox-rooting, and collision.
- **Integrator = the SOLE master-pusher**, merging the live programs into master DAILY. Named failure: multiple pushers produce non-linear history and a sibling lane's fresh commit rides your push (gotcha #47). One pusher ⇒ one linear master.
- **Codex = the cross-cutting ADVERSARIAL reviewer of EVERY merge** (never a program owner, never a pusher). Named failure: unverified "shipped" claims reached master (2026-06-11); Codex is elite at adversarial audits. A review gate on every merge catches false-green before it lands.
- **Programs remain the roadmap layer OVER the unchanged file-collision lanes** (backend / frontend+iOS / ops / eval). v4 does NOT reorganize lanes by domain — this re-affirms the 2026-08-03 PROGRAM LAYER ruling.

**ANTI-IDLE — caps order, never stop.** The caps above are a WIP CEILING, not a reason to sit idle: within the caps a lane always pulls the next capped item. Named failure: idle lanes and agents that stop mid-run (the standing "never stop" rule). Caps bound work-in-progress; they never license idling.

**Migration actions this ruling authorizes:** migrate the UX pilot worktree into `~/bainluck-dev/`; stand up latency and calibration worktree slots next; file one parent issue per program on the board and re-parent existing open issues under them.

## RULING — 2026-08-05: Bind the Discover game card to the blend (approved as UX pilot cycle 3)

**Ruling.** The Discover game card and the event-detail hero must ALWAYS show the same number, and that number is the blend. The card is bound to the same aggregate/blend probability the hero renders — no separate card-only probability path may diverge from it.

WHY: this is standing ruling #1 ("THE BLEND IS THE PRODUCT … the hero and the chart must show the SAME number — the 57-vs-20 bug violated this") applied to the third surface. A card that shows a different number than the hero it links to is the same "the app isn't doing what it's supposed to" trust break. One blend, every surface: card == hero == chart. Divergence is a DATA/PLUMBING bug to fix at the source, never a per-surface display choice.

Approved by Alex as **UX pilot cycle 3**.

## RULING — 2026-08-05: The handoff inbox — how program lanes deliver completion artifacts

**Ruling.** Programs write completion artifacts to `~/.handoff-inbox/<program>-<queue-id>.md`. The consumer that HAS write access to the destination — the Integrator, for `~/bainluck/.claude/handoff/` — files it as its **Phase-0 step** and then deletes the inbox copy. An inbox file is a **HANDOFF IN FLIGHT, never a second source of truth**: the queue file's `status:` line in `~/bainluck` remains the ONLY authoritative state, and only the Integrator writing that line changes it. A stale inbox file means a handoff was never consumed — investigate it, never read it as current state.

**Named failure this closes: the cycle-1 and cycle-3 write-denies.** Both cost a cycle to the same root cause, discovered from opposite ends. Cycle 1 blocked because a session rooted in the master worktree could not WRITE the program worktree, and `/add-dir` did not fix it. OPERATING MODEL v4 responded by inverting the launch (root IN the worktree, `--add-dir ~/bainluck`) — and cycle 3 then blocked because a session rooted in the worktree cannot write the HANDOFF files. v4 did not fix the problem; it swapped which side is read-only. UX-P003 finished its code and gates and still could not claim its own queue or file its own report, and shipped them through a hand-run `/tmp` script.

**The measured mechanism (UX-P003 diagnostic, 2026-08-05).** The deny is the sandbox, not settings and not a hook:
- No `deny` rule and no `additionalDirectories` in ANY settings file in scope. An allow-list entry matching the failing command **verbatim** (`Bash(touch .../HEARTBEAT-LANE1)`) did not help — the permission layer is not the gate and cannot open it.
- The only `PreToolUse` hook in scope is `agent-security-guardrails`, wrapped `2>/dev/null || true`, so it can never block.
- Three independent syscall paths (Write tool, bash redirect, Python `open`) all return **`EPERM` / errno 1** — a kernel refusal, not a harness message. `dangerouslyDisableSandbox: true` does not lift it.
- `permissions.additionalDirectories` was TESTED mid-session and did not grant write. **That result was an artifact of WHEN it was tested — see the resolution below.**
- The write boundary: `~/bainluck`, `~/bainluck-dev` and its non-primary worktrees are DENIED; the session's primary root, `/tmp`, `~/.claude`, and **dot-prefixed paths in `~`** are writable. Non-dot paths in `~` are denied — which is why the inbox is `~/.handoff-inbox/` and not the `~/handoff-inbox/` this ruling originally named. The leading dot is a mechanical necessity, not a design change.

**RESOLUTION — verified fresh-session 2026-08-05. Cross-root writes ARE configurable; the deny is closed from both ends.**
- A `.claude/settings.json` containing `permissions.additionalDirectories`, **present at session LAUNCH**, DOES grant cross-root writes. Verified on a fresh launch: a write to `~/bainluck/.claude/handoff/` from the UX worktree session succeeded (exit 0, no prompt, no `EPERM`).
- **`--add-dir` alone does NOT** grant it, and **neither does editing a settings file mid-session** — settings are read at launch only. Every earlier negative result came from one of those two paths, which is why the mechanism looked like an unconfigurable kernel boundary.
- The fix is therefore a **settings file, in place before launch, on each side** — not a script, not a flag. The UX container carries `additionalDirectories: ["/Users/bain/bainluck"]`; `~/bainluck/.claude/settings.local.json` carries `additionalDirectories: ["/Users/bain/bainluck-dev"]`, closing the Integrator's side at its next launch.
- **`~/.handoff-inbox/` remains the documented fallback**, unchanged in shape and unchanged in status: an artifact there is still a HANDOFF IN FLIGHT, never a second source of truth. It is what a lane uses when it finds itself launched without the settings file in scope — a condition that is now diagnosable in one write test rather than costing a cycle.

WHY the inbox survives its own fix: the direct-write path depends on a launch-time condition a lane cannot verify before it is already running, so the protocol keeps a route that works when that condition is absent. What changed is the default — direct write first, inbox on failure — not the guarantee. The strict "in flight, never truth" rule is what keeps the inbox from becoming the third place a queue's status lives: the failure mode that the single-source-of-truth rule exists to prevent, and the reason docs never carry ordering.

## RULING — 2026-08-06: Board-visible completion — a cycle is not done until the board says so

**Ruling.** Every queue completion — program cycles, Codex runs, integrations — posts a comment
on its **program parent issue** (#1544–#1550) carrying the **queue id**, **verdict**, **branch
head SHA**, and the report's **key lines**. **A cycle is NOT complete until that comment exists.**
The LAT-P001 comment on #1545 is the model. Routing is by the program the work belongs to, not by
who executed it: a Codex run that audits Discover comments on the Discover parent.

**Named failure this closes: local handoff files are invisible to everyone who is not this
terminal.** `.claude/handoff/` is gitignored and machine-local, so the cloud coordinator, every
fresh session, and Alex on any other surface cannot see that a cycle finished, what its verdict
was, or which SHA carries it. Completion has been living in a place only one window can read
while the board — ruled in v4 as **the SOLE record of priorities, ideas, and completion** — stayed
silent. Three cycles ran with a queue file saying `done` and a parent issue saying nothing.

WHY the comment and not a status column flip: the column says *that* something finished; the
comment says *what* finished, *with which verdict*, and *at which SHA* — the three facts a fresh
session needs to avoid re-doing or contradicting the work. It also makes a PREMISE-BROKEN or
PARTIAL verdict durable, which a green column actively hides. This is the same single-source
discipline as the handoff-inbox ruling above: one authoritative home per fact, and the board is
that home for completion.

**Companion mechanic (same ruling):** the **Integrator self-writes its INT claim artifact at
Phase 0**. Pre-staging it is dropped. This ends the three-cycles-running "unstaged Integrator
queue" exception — the Integrator was the one lane whose claim artifact someone else had to
create for it, which is why it kept running without one.

## RULING — 2026-08-06: Integration ordering is the Integrator's call, not a question for Alex

**(Fable ruling; Alex may veto.)**

**Ruling.** When multiple program queues are simultaneously `ready_for_integration`, the
Integrator decides the order **without asking anyone**, by this ladder:

1. **Disjoint queues before colliding ones; smallest diff first.** A queue that touches no file
   another ready queue touches merges immediately, smallest first.
2. **Among colliding queues, first-certified merges first.** The later-certified queue rebases
   **in its own worktree** and **re-certifies** — the Integrator does not carry someone else's
   rebase, and a rebased branch is not certified until its gates are re-run on the new base.
3. **A P0 security queue jumps the line**, ahead of both rules above.

**Escalate to Alex ONLY when two colliding queues are both P0.** Nothing else about ordering is
a human decision.

**Named failure: INT-005 stalled on a human scheduling answer with three healthy queues
waiting.** Nothing was broken, nothing was ambiguous about the *work* — the lane simply had no
authority to pick an order, so certified, gate-green queues sat idle waiting on a question that
had an obvious mechanical answer. That is the ANTI-IDLE rule's exact failure mode arriving
through a gap in delegated authority rather than through a WIP cap.

WHY this ladder and not "merge whatever is oldest": ordering only matters when queues collide,
and the only real cost in a collision is *who re-runs gates*. Rule 1 gets the free merges out of
the way so a collision never blocks unrelated work. Rule 2 puts the rebase cost on the queue that
certified later — the one whose base was already stale — and forbids the Integrator from
rebasing-and-shipping without re-certification, which would be a merge of code no gate ever saw
in that combination. Rule 3 exists because a P0 security fix waiting behind a diff-size heuristic
is the one case where the cheapest order is the wrong one.

**Corollary (already in force):** the Integrator self-writes its claim artifact at Phase 0
(PROGRAM-LANES Invariant 10), so choosing an order needs no external staging step either.

## RULING — 2026-08-06: CONTINUOUS LANES v1 (Alex) — a lane never idles between cycles

**1. NO IDLE AFTER COMPLETION.** When a lane posts its completion comment it does **not stop**.
It takes its next work immediately:
- a **pre-staged NEXT queue** if one exists; otherwise
- it **SELF-STAGES**: pick the highest-priority open board issue carrying your program's label,
  write your own queue for it per the standing template (one-sentence visible payoff, hard
  guardrails, acceptance criteria, board-visible completion), **post that queue text to your
  program parent as a QUEUE comment for the record**, and execute it.

Self-staging is not a licence to invent scope: the queue must trace to an open, labelled board
issue, and posting it as a comment before execution is what keeps a self-staged cycle as
auditable as a Fable-staged one.

**2. STACKING.** Never wait for your previous cycle to merge. Build cycle N+1 **on your own
branch head**. If an integration bounces, rebase before continuing.

**3. THE ONLY STOP CONDITIONS.** Four, and nothing else:
- **an unstated judgment call** — post `⚠️ NEEDS RULING` to the parent issue and stop;
- **context budget ~70% spent** — certify what is done, post `HANDOFF-RELAUNCH`, stop;
- **the plumbing daily cap**;
- **PREMISE-BROKEN**.

A lane that stops for any other reason has stopped incorrectly. "Waiting for the merge",
"waiting for someone to stage the next thing", and "waiting to be told what is next" are not
stop conditions — they are the failure this ruling names.

**Named failure: 2026-08-06 — four healthy lanes sat idle between cycles while only the
Integrator worked, with the HUMAN as the message bus.** Every lane had finished cleanly and
every lane stopped, so the one person the whole model exists to protect became the scheduler,
hand-carrying "you're done, here's the next thing" to four terminals. The cost is not the idle
minutes; it is that Alex's surface was supposed to stay fixed (fire lanes, MC rounds, dogfood,
design runs, ship-gate eyeballs) and this quietly added dispatcher to it.

WHY self-staging and not "wait for Fable": staging is only a bottleneck when the next item is
*unknown*, and it usually is not — the board already carries a labelled, prioritised queue of
open issues per program. Reading the top of your own label is mechanical. What genuinely needs a
human is a taste/ranking/design call, and that already has its own stop condition and its own
escalation path (THE ONE RULE ABOVE ALL is untouched by this ruling: a self-staged queue that
turns out to need a judgment call posts ⚠️ NEEDS RULING and stops, exactly like a staged one).

This supersedes the ANTI-IDLE clause of OPERATING MODEL v4 by making it concrete: the caps bound
work-in-progress, and a lane at completion always has a next move it can make on its own.

## RULING — 2026-08-07: LANE OWNERSHIP IS PER-WINDOW (Fable; amends CONTINUOUS LANES v1)

**One window per lane is the standing default.** A lane name is not a lock. Ownership belongs to
a specific *window* — a single running session — and must be provable, not asserted.

**The mechanism.** A queue's `status: running` line MUST carry a **session nonce**: the window's
start timestamp plus a random suffix. The owning window refreshes a `heartbeat:` alongside it as
it works.

```
status: running
owner: <lane> (window 2026-08-07T14:22PT-a3f9)
heartbeat: 2026-08-07T15:04PT
```

**The rule.** A window that opens a queue and finds `status: running` with a heartbeat **under 30
minutes old STOPS and reports** — *even when the owner line names its own lane*. That last clause
is the whole point: "I am the calibration lane, this says the calibration lane owns it, therefore
it is me" is exactly the reasoning that fails. A stale heartbeat (>30 min) means the prior window
died; the new one may take the lane, and must rewrite the nonce to its own before touching
anything.

**Named failure: 2026-08-07 — two calibration windows executed CAL-P002B concurrently.** Nothing
was corrupted, but only by luck and good manners: both happened to converge on the same fix and
neither pushed over the other. The protocol had no way for either to know the other existed,
because the queue only ever identified an owner by *lane*, and both windows correctly believed
they were that lane. Duplicate work is the mild outcome; two windows committing divergent fixes
to one branch, or one rebasing under the other, is the outcome the nonce prevents.

This interacts with CONTINUOUS LANES v1 rather than weakening it: a lane still never idles between
cycles, and a self-staging window still takes its next work immediately — it just stamps the nonce
when it claims, so the *second* window discovers the collision instead of racing into it. Add
"queue is already running under a live heartbeat" to the lane's stop conditions.

## RULING — 2026-08-07: INVARIANT 2 AMENDED — successor branches; a lane never waits for integration (Alex)

**One queue per branch holds. A lane never waits for integration.**

When a lane finishes a queue whose branch is not yet merged, it opens a **successor branch from
its own unmerged head** — `program/<name>-2`, `-3`, … — declares the **stack order** in its
handoff, and continues. The Integrator merges stacks in declared order. **A bounce of branch N
pauses only N+1's merge, not the lane's work.**

**Why this shape and not the two obvious alternatives.** Piling successive queues onto one branch
(what the calibration lane did on 2026-08-07 with three cycles on `program/calibration`) keeps the
lane hot but destroys per-queue certification: the Integrator can no longer take cycle 3 without
cycles 1 and 2, and a problem anywhere in the stack bounces all of it. Waiting for the merge keeps
certification clean but idles the lane, which is the exact failure CONTINUOUS LANES v1 exists to
prevent. Successor branches get both: **certification stays atomic per queue**, and the lane never
blocks.

The real payoff is what it does to the conversation. Integration lag stops being an interactive
question — "is my stuff merged yet, can I start the next thing?" — and becomes a **queue-depth
number the Integrator reports**. Depth is then a metric Alex can read at a glance and act on when
it climbs, instead of a scheduling negotiation conducted per lane, per cycle.

Interacts with the other standing rulings rather than replacing them: CONTINUOUS LANES v1 still
says a lane takes its next work immediately (this is the branching mechanics for doing so);
Invariant 4 is untouched (the Integrator alone rebases, merges and pushes); the per-WINDOW
ownership nonce ruling above is orthogonal and still applies to each successor queue.
## RULINGS — 2026-08-07: the shared master tree (Alex) — two rules from a destroyed-WIP incident

Both rules come out of one event: a `/program latency` window ran `git reset --hard origin/master`
meaning it for `~/bainluck-dev/latency`, the shell's cwd was `~/bainluck`, and it executed in the
shared master worktree. Two local commits came back from the reflog; **nine files of uncommitted
work did not, and never could** — unstaged content has no object in the database, so there was
nothing for reflog, `fsck`, or `lost-found` to return. Filed as #1575.

### 1. DESTRUCTIVE GIT TAKES `-C`

In any session with more than one worktree in scope, `reset`, `checkout`, `clean`, and `rebase`
MUST use the explicit `git -C <path> …` form. A bare invocation that relies on an inherited
working directory is forbidden for these verbs, however obvious the cwd seems.

WHY: cwd is *session* state, not *command* state. It is set by a previous, unrelated call —
frequently one issued in the same parallel block, where ordering is not guaranteed — so the
directory a destructive command lands in is not visible in the command itself. `git -C` moves
the target from invisible session state into the command text, where review can see it. This is
the write-direction twin of gotcha #47, which already covers the read direction (`git log
origin/master..HEAD` before committing in a shared tree).

**Named failure: 2026-08-07** — a `cd`-less `git reset --hard` sent in the same block as a
`cd ~/bainluck` inherited that cwd and reset the master worktree.

### 2. NO ORPHAN WIP

Uncommitted changes in the shared master tree must be committed to a named branch, or stashed
with a message, **within the session that made them**. Leaving dirty tracked files in `~/bainluck`
across sessions is not a neutral parking state.

The Integrator enforces this at Phase 0: anything dirty in the master tree older than 24h gets
committed to a `rescue/<date>` branch rather than tiptoed around. Rescuing it costs one commit;
the alternative is what happened.

WHY: orphan WIP is worse than lost work — it is a standing tax with no owner. Every integration
since 2026-08-05 had to read those nine files and prove its own diff was disjoint from them, and
no cycle could say who owned them or whether they were finished. They imposed that cost on every
lane while being one wrong cwd away from deletion the entire time — and then they were deleted.

**Named failure: 2026-08-07** — nine files (Board Sentinel, sentinel filing, the calibration
publish gate, `/calibration` page math, and their tests) dirty in the shared tree since at least
Aug 5, matching no approved queue, destroyed with no recoverable diff.

**Corollary for the redo:** do not reconstruct lost work by archaeology. Re-do it from *intent*
in a deliberately scoped queue, or rule it unneeded. A diff nobody can describe is not a
requirement.
## RULING — 2026-08-07: Mover headlines are legitimate — UX-P005 class (c) closed as designed behaviour (Alex)

**Ruling.** A Discover card headline may name a **mover** rather than the **leader** when the movement is
the more interesting fact, **provided the movement is visible on click-through**. This is designed
behaviour, not a defect. UX-P005 class (c) is **CLOSED**; no card copy is to be rewritten for it, and no
future queue may re-file it as a contradiction.

**The specimens this closes** (UX-P005 census, 2026-08-06 — 4 cards): Big Brother S28 headlined
*"Rick Devens up 10.0 points today"* above a list led by Dee Valladares @ 23.5%; Fed Decision in
September; two Netflix movie cards. Zero cards claimed a *false favourite* — every `"X leads at N%"`
headline matched its list leader. What the census actually found was movement framing, which is a
different thing.

**The one condition, and it is a real gate.** The proviso is load-bearing: a mover headline is a
**promise that the movement is there to be found**. Tapping the card must surface the move — the
outcome's change, its direction, its window — not just a static list the headline appears to contradict.
A mover headline over a click-through that cannot show the movement IS a defect, and it is a defect of
the *detail surface*, not of the copy. That is the only form in which class (c) may be re-opened.

WHY this is not a contradiction: the leader and the mover answer different questions — *who is winning*
and *what just changed*. A card that always leads with the leader is a standings table; the feed's job
is to be the most engaging way to explore what the world thinks will happen, and "who moved 10 points
today" is frequently the more engaging answer. The North Star favours the interesting true fact over
the ranked one. Nothing here weakens **THE BLEND IS THE PRODUCT** — a mover headline still quotes the
blend, and a headline probability that disagrees with the list's is still a data bug.

**Named failure this closes: a taste call answered twice in conversation and recorded zero times.**
UX-P005 correctly refused to rewrite copy on an unstated judgment call and posted ⚠️ NEEDS RULING —
that was the right move. The failure is downstream of it: the answer was given and never written here,
so the next census will surface the same 4 cards and the next lane will stop on the same question. An
unrecorded ruling is an unmade ruling. **Any ruling given verbally is not in force until it is appended
to this file** — the lane that receives one appends it as part of the cycle that received it.

## RULING — 2026-08-07: A rail is not shipped until it has been invoked post-deploy at its documented default (from INT-007; Fable-endorsed)

**Ruling.** When a queue's deliverable is an **operational rail** — an endpoint, task, repair, or sentinel
that exists to be *run* — the cycle may not be claimed until that rail has been **invoked on production
after deploy, at its documented default invocation**, with the response recorded in the report. Green
gates, a green CI run, and a verified deploy SHA are **necessary and not sufficient**. The default
invocation specifically: not a scoped-down call, not a subset that happens to work, not the smallest
input that returns 200. If the rail also documents a resumable contract ("re-invoke until N is 0"), a
second invocation must be shown to *move* the counter.

**Named failure: CAL-P002 / INT-006 — code integrated and deployed, payoff zero.** The repair merged as
`28193e9c` with every gate green: 10,931 backend tests, typecheck at baseline, build clean, deploy
verified on both surfaces. It was also **completely unusable**. `_CANDIDATE_SQL` carried no `LIMIT` and
ran two correlated `MAX()` subqueries per row before the `limit` slice was applied, so `limit` bounded
the *output* and not the *scan*. Every unscoped call hit the Heroku 30s router timeout and wrote nothing:
`?limit=25` — the documented default, and the exact command in the handoff — **H12 at 30.3s**. So did
`?limit=3`. So did the Flow Sentinel's own guard call, `?limit=6&newest_first=true`, which meant the
sentinel that was supposed to watch the repair would have reported `unknown` every night indefinitely.
A second defect compounded it: the selection predicate is unchanged by the repair, so `groups_remaining`
could never fall and the documented "re-invoke until 0" contract could never terminate.

**One curl would have caught all of it.** Not a test — a test would have had to model Heroku's router
timeout and production's row counts to see this. The whole failure lives in the gap between "the code
is correct" and "the thing runs where it has to run", and only running it there closes that gap.

WHY this is not already covered by "board-visible completion": that ruling governs *whether the world
can see a cycle finished*, this one governs *whether it finished*. And it is the direct rail-shaped
analogue of the standing evidence bar — **never close on "code shipped"; require measured production
evidence**. INT-006 was scrupulous about every gate that existed and still shipped a zero-payoff cycle,
because none of those gates was the one that mattered. The default invocation is the gate that matters,
and it costs one call.

**Corollary — scope down only downward, never in the claim.** A rail that works scoped
(`?sport=lacrosse_pll` @ 1.4s) and fails unscoped is a **failing rail**, and the report says so in the
verdict line. INT-006 got this exactly right — it recorded `PAYOFF BLOCKED` rather than `INTEGRATED`,
which is why CAL-P002B could be staged against a true premise instead of a claimed one. That honesty is
the behaviour this ruling makes mandatory rather than admirable.

## RULINGS — 2026-08-07 (Alex, batch): where lanes work, how they lock, how they branch

Three process rulings issued together. All three come from failures that had already happened;
none is speculative hardening.

### (a) THE MASTER WORKTREE IS INTEGRATOR-ONLY

**Named failures: the nine-file WIP loss (#1575), and four fast-forward breaks in a single
integration cycle.**

Every lane works in a worktree. Nobody else edits, stages, or commits in `~/bainluck`.

- Codex moves its eval commits out of master onto a `codex/evals` branch, merged by the
  Integrator like any other lane's branch.
- The remaining master-side legacy queues migrate to worktrees.
- **WIP found in the master worktree is FILED, not preserved silently.** Quietly stashing or
  carrying someone's uncommitted work is how the nine-file loss happened; an issue with the
  diff attached is recoverable, a stash in a shared tree is not.

WHY this and not "be careful in master": the master worktree is the one tree every lane can
reach, so it is the only place where one lane's mistake lands on another lane's work. Making
it single-writer removes the shared mutable state rather than asking five actors to
coordinate around it. It also makes fast-forward breakage attributable — if only the
Integrator commits there, a non-fast-forward means the Integrator's own sequence is wrong,
not that somebody wandered in.

### (b) THE LOCK IS PER-WORKTREE, NOT PER-QUEUE

**Named failure: the 2026-08-07 double-window collision that the per-WINDOW nonce did NOT
catch** (surfaced by the ux lane; write-up in
`.claude/handoff/PROGRAM-UX-COLLISION-2026-08-07T1143PT.md`).

A window claims the WORKTREE, in a `LANE-<name>.lock` it refreshes for its whole life — not a
`status: running` field on whichever queue happens to be open.

WHY the nonce ruling was not enough, stated plainly because it is subtle: the per-WINDOW
ruling asked the OWNING window to stamp the record, and the owner is the one party with no
incentive to — it already knows it owns the lane. That is structurally the same defect
Invariant 10 fixed for the Integrator ("a lane creates its own claim artifact"), reappearing
one level down. It also left a specific hole the queue-scoped design could never close:
between posting a completion and staging the next queue, a continuous lane owns the worktree
while NO queue file says `running` at all — the lane is most claimable at exactly the moment
it looks unclaimed. A worktree-scoped lock is one read to check and stays valid across the
staging gap.

The second window in that collision found the file-based check CLEAN and only noticed
because `git rev-parse HEAD` returned two different SHAs six minutes apart — the sibling had
rebased the branch underneath it. A compliant window would have raced straight in.

### (c) SUCCESSOR BRANCHES ARE THE DOCUMENTED DEFAULT; ONE HANDOFF VOCABULARY

Successor branches (`program/<name>-2`, `-3`, …) are no longer an amendment to read past —
they are the default shape, documented as such. The ux lane converts.

Handoff vocabulary standardizes on **`ready_for_integration`**. Not `done`, not "lane idle
pending Integrator". INT-009 accepted a stack whose queues said `done` and recorded the
deviation rather than refusing on wording; that judgment was right in the moment and is
exactly the kind of per-cycle discretion a shared vocabulary should make unnecessary.

WHY one word matters: the Integrator's Phase-0 refusal conditions are mechanical. A refusal
condition that has to be evaluated on intent instead of on a token is not a gate, it is a
conversation — and it will eventually be resolved the wrong way by whoever is in a hurry.
