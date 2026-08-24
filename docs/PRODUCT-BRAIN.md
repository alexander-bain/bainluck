# PRODUCT BRAIN — the load-bearing judgment for staging Bain Luck lanes
# Purpose: everything an agent (Codex / Fable / Opus) needs to stage work WELL — the rulings AND the WHY behind them.
# This externalizes Fable's private memory into the repo so the sharpest available reasoner can stage. Read this + CLAUDE.md + docs/PRD.md.
# Owner: whoever stages. A NEW RULING IS A NEW FILE: write `docs/rulings/NNN-<slug>.md` and add ONE line to the `## RULINGS INDEX` section at the bottom of this file. Do NOT append ruling prose into this file's body any more — that shared append region is what detached three commits' patch-ids permanently and made `git cherry` lie to the Integrator (ruling 001, #1621). See `docs/rulings/README.md` for the exact shape. Everything already below stays where it is: NEVER regenerate, "consolidate", rewrite, or trim this file wholesale — doing so silently dropped ratified rulings TWICE (see the RE-RESTORED markers below). If you are staging a "docs task", it does not authorize touching this file's existing sections. CI-guarded: backend/tests/test_product_brain_integrity.py turns master red if any ruling section disappears, the doc shrinks below its banked section count, or the ruling index and `docs/rulings/` fall out of sync in either direction.

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

---

## RULING — 2026-08-08: USAGE-WEIGHTED PRIORITY for the UX program (Alex)

### The north star: the KALSHI-PREFERENCE TEST

The UX program's north star is now a single falsifiable question: **a non-gambler doing real
tasks — find tonight's game, read the probability, understand what moved, check a future —
should prefer Bain Luck to Kalshi.**

Not "should be able to do it on Bain Luck". Should *prefer* to. The test is comparative and
it is run against a real competitor, so it cannot be passed by adding a feature; it is only
passed by being faster, clearer, or more pleasant at a task someone actually does.

### Every UX payoff sentence now states WHO and HOW OFTEN

A queue's visible-payoff sentence must additionally answer, for the **real** user base
(family and friends, low double digits, over the next few months):

- **WHO** hits this path?
- **HOW OFTEN** do they hit it?

This is a hard requirement on the payoff sentence, not a section elsewhere in the queue. A
payoff sentence that cannot name who hits it and how often is a payoff sentence describing
work nobody asked for.

### The ordering rule

**Likely-daily-path work outranks unlikely-scenario work regardless of severity.**

Severity is not frequency, and the UX program had been ordering by severity alone. A P1 that
fires on a path no one in a low-double-digit user base will walk this quarter loses to a P3
sitting on the nightly "what's the score" path. That is a deliberate inversion of the usual
instinct, and it is correct here precisely *because* the user base is small and known: with
low double digits of real users, "could affect anyone" and "will affect someone this week"
are wildly different quantities, and only the second one buys anything.

### The one exception

**The data-corruption class stays priority-eligible at any likelihood.** Corruption is not
weighted by frequency because it is not self-correcting: an unlikely path that silently
writes bad data compounds, survives the session, and is often undiscoverable afterwards. A
slow page is annoying every time and costs nothing permanently; a rare cross-account write
is invisible once and permanent.

### Application, immediately

- **UX-P017 (account switch) — FINISH IT.** Both exceptions apply at once: it is the
  corruption class, and shared family devices make it a likely path for exactly this user
  base rather than an unlikely one. Not a carve-out; it qualifies twice on the new rule.
- **The next THREE UX cycles come from a Kalshi gap list.** Run the preference test
  task-by-task, write down every point at which Kalshi is faster, clearer, or more pleasant,
  and stage from that list **in order of daily-path frequency** — not in order of how bad
  each gap looks.

### Why this ruling exists

The UX lane had been mining the board, and the board is ordered by severity and by whoever
filed most recently. That reliably produces defensible work and unreliably produces work
anybody notices. A gap list generated by *using the product against the competitor* is
ordered by what a real person actually hits, which is the only ordering that can move a
preference test.


---

## RULING — 2026-08-08(b): the preference test is a PROGRAM goal the UX lane ADMINISTERS, not a UX work queue (Alex)

Amends the 2026-08-08(a) usage-weighted ruling above. That ruling stands in full; this one
fixes the unit it was attached to.

### What went wrong with (a)

(a) made the Kalshi-preference test the UX lane's north star and sent cycles 19–21 to a gap
list built from it. Within two cycles the lane was blocked with nothing to do:

| gap | outcome |
|---|---|
| search 2–17s | `app/routes/events.py` — latency lane's file, #1494 in flight |
| zero games on the landing page | designed behaviour; needs a product ruling |
| `game-markets` 2.25s | **also `app/routes/events.py`** |
| `/events/{id}` 307 | withdrawn — a site-wide apex→www redirect, not a gap |

Three of four were structurally untouchable by the lane that found them.

### The actual error, stated precisely

**A lane is a code-ownership boundary. A north star is a user-outcome boundary. They do not
align, and (a) assumed they did.**

"Faster" is one of the three things the preference test measures, and in this codebase
backend latency for all four north-star tasks lives almost entirely in ONE file that another
lane owns. So the test will keep surfacing work the UX lane cannot do — not occasionally, but
as its normal output.

A secondary error is worth naming because it caused the first: the gap list was built by
**timing HTTP endpoints**. Any gap an endpoint timer finds is backend latency by
construction. The measurement method silently determined the ownership of everything it
found.

### The ruling

1. **Search latency stays with the latency lane.** They own the file, they built the
   `?debug_timing=1` instrument the diagnosis depended on, and they have a fix in flight. Two
   lanes in one hot file is precisely the collision the lane model exists to prevent, and the
   fix — query plans, index strategy, `DISTINCT ON` vs lateral — is not a UX skill and is
   invisible in the UI.

2. **The preference test is a PROGRAM-level goal.** The UX lane administers it:
   - runs the four tasks and keeps `PROGRAM-UX-KALSHI-GAPS.md` current;
   - **reports the whole scorecard every cycle, regardless of who owns each fix**;
   - carries an explicit **OWNER** on every row, routed to whichever lane owns the file;
   - **stages only its own subset** — client-side costs in `frontend/`.

3. **A round whose top gaps route elsewhere is a NORMAL round, not a block.** UX-P020
   reported `blocked`; under this ruling that same state is a routed round plus a UX tier.

### The risk this creates, and the guard

**Risk:** UX degenerates into a reporting function — it writes lists, other lanes do the
work.

**Guard:** UX must still ship its own tier every cycle. If the client-side tier turns out too
thin to sustain a lane, that is a signal that **UX's remit is smaller than one full-time
lane** — it is NOT a reason to hand UX the backend file. Re-opening the file split would
recreate the collision this ruling exists to avoid.

Whether the tier is thick enough is **not yet known.** It rests on one unmeasured candidate
(the event page fetching `history`, `game-markets` and `team-progression` on mount whether or
not the game has started) and un-interrogated route weights (`/sports` 291 kB, `/search`
272 kB, on a 160 kB shared baseline). Those measurements are owed from a fresh window and
decide the question.

### Why this is the right shape

The lane model is about avoiding write collisions. It was never a claim that each lane can
independently move a user outcome. Pretending otherwise makes a lane either idle or
trespassing — UX-P020 chose idle and said so, which is the correct behaviour and also the
signal that the structure needed this amendment.

### Still open

The landing-page question (should the default surface lead with games during a live season?)
remains unruled. It interacts with the guard above: if games get floored into the default
feed, that is UX-ownable work in `frontend/` and it materially thickens the UX tier.


---

## RULING — 2026-08-08(c): Fable runs the objective pass; Alex gets only judgment calls (Alex)

Completes (a) and (b). (a) set the north star, (b) set who administers it, (c) sets **who
does the looking**.

### The split

- **Fable runs the objective pass, browser-side.** It delivers the **mechanical gap list plus
  screenshots**. This is not a preference — it is the only party that can. Agent sessions
  cannot launch a browser, and `kalshi.com` returns **HTTP 429 in 0.06s** to scripted access,
  so the comparative column is permanently out of reach for the UX lane on its own.
- **Alex receives ONLY judgment calls**, presented as **multiple choice with BOTH screenshots
  attached** — ours and Kalshi's, side by side.
- **The UX lane administers** (per (b)): owner per row, routing, the scorecard, and staging
  the `frontend/` subset.

### Why the multiple-choice constraint is the load-bearing part

Alex's 2026-08-08 pass produced fifteen findings in one sitting. Most needed no judgment at
all — an overlapping label, a two-tick axis, a control that does nothing are simply broken,
and asking about them wastes the scarcest input in the system. A handful genuinely did need
taste (should the default surface lead with games? is a team page a better answer than
tonight's game?).

Mixing the two turns a five-minute decision into a triage session. **The objective pass is
what separates them**, and it can only be run by whoever holds a browser.

### The standing anti-pattern this forbids

Do not ask Alex to go run the comparison. The lane asked exactly that in UX-P018 and got it —
but at the cost of Alex doing mechanical work a browser-capable agent should have done, and
of the findings arriving as prose to be mined rather than as decisions to be made.

Ask **Fable** for the objective pass. Bring Alex only what needs taste, already paired with
its evidence.

---

## RULINGS — 2026-08-08(d): Alex's batch on the preference-test findings

Four decisions, closing everything the UX lane had open. (a) set the north star, (b) who
administers it, (c) who does the looking; (d) is the first batch of judgment calls the (c)
process was built to produce.

### 1. The landing page LEADS WITH TONIGHT'S GAMES during a live season

**Ruled:** during a live season, `bainluck.com` leads with **tonight's games — live or
starting soon** — with the Discover mix **below**.

This closes GAP 2. The finding was that the default surface returned **55 cards with ZERO
game events** while 18 games were live; the first twelve cards on an August evening were led
by *"Will the U.S. confirm that aliens exist?"* and *"Hantavirus pandemic in 2026?"*.

That was **designed behaviour** — the Discover event demotion caps non-exceptional events at
score 35 so futures can compete — which is exactly why the lane refused to "fix" it and asked
instead. The design was right for a pure discovery surface and wrong once *"find tonight's
game"* became a north-star task. Discover is not being demoted; it is being placed **below**
the thing a returning user most often came for.

Note what this does NOT say: it is not "show every game", and it is not a scoreboard. Live or
imminent games lead; the discovery mix keeps the page.

### 2. Search RELEVANCE is `program:ux`; latency owns COST

**Ruled:** #1590 is `program:ux`. **Search relevance is product quality. Latency owns cost.
Shared-file work coordinates via declared rebases, as usual.**

This is the resolution of the boundary question that blocked UX-P020 outright. Ruling (b)
correctly sent search *latency* to the latency lane, and the lane then over-read it: because
`app/routes/events.py` held the latency work, the lane treated the whole FILE as foreign and
concluded it had nothing to do.

**A file is not an owner.** Two lanes can hold different concerns in one file — cost and
quality are different questions with different judgment behind them — and the coordination
mechanism for that already exists and is boring: declared rebases. The lane's instinct to
avoid collisions was right; converting it into "I cannot work here" was not.

### 3. TRUTH VIOLATIONS OUTRANK ALL POLISH

**Ruled:** #1588 and #1589 lead the queue.

- **#1588** — a first-inning prop still quoting **52% "No"** after a first-inning run scored.
- **#1589** — playoff odds showing **63%** where reality is **~90%**, a 27-point error.

These are not slow, ugly, or confusing. They are the product **stating something false**, with
a confident number attached, on a page the user is reading while they can see the truth with
their own eyes. That outranks every legibility and speed item on the list regardless of
frequency — and it is a sharpening of the usage-weighted rule in (a), not an exception to it:
frequency weighting decides among things that are *merely imperfect*. A false number is not on
that scale.

#1588 is additionally a direct violation of the standing **"settled means settled"** ruling.

### 4. Fable settles the /sports blank-sections question post-merge

**Ruled:** after `program/ux-9` merges, **Fable re-checks the `/sports` blank-sections symptom
in Chrome** to settle whether UX-P022's storage guard was the cause.

The lane found a coherent mechanism — UX-P017 dropped a `try/catch`, and the new call sites
run inside a `useEffect` on a page that only reads preferences, where a throw unmounts the
subtree — and fixed it, while explicitly **refusing to claim it as the confirmed cause**,
because it could not drive a browser. That refusal is the correct behaviour, and (c) is why:
the party with the browser settles it.

## RULING — 2026-08-08: SYNTHETIC TRAFFIC IS REAL TRAFFIC when organic traffic is structurally absent (Alex)

**DO NOT REMOVE (CI-guarded).**

> Synthetic traffic satisfies "under real traffic" criteria whenever organic traffic is
> structurally absent — on a pre-launch app, agent-generated load is the real traffic.

### What this resolves

#1500's acceptance criterion 4 read: *"Over one hour of production traffic, the `miss` bucket
sample count is > 0 and its max is within measurement error of a header-observed cold request in
the same window."*

LAT-P008 satisfied it — rail **8,534.3 ms** vs header **8,504.75 ms** (Δ 29.6 ms), and
**2,109.2 ms** vs **2,057.96 ms** (Δ 51.2 ms) — but with traffic the window generated itself. The
rail had independently reported `/api/feed` `samples: 0, no_samples_in_window: true` for the
preceding hour.

So the criterion could not be met by waiting. **There was no organic feed traffic to wait for, and
on a pre-launch app there never will be.** The window declined to close on its own judgment and
escalated. That escalation was correct; the underlying criterion was not.

### The pattern this exists to kill: the PERMANENT BLOCKER

A criterion that can only be satisfied by a condition the product does not yet have is not a
quality bar — it is a permanent blocker wearing one. It does not raise rigour; it converts a
finished piece of work into an issue that can never close, and it silently blocks everything
downstream. #1500 was the **sole stated blocker on #1459**, the largest remaining latency item, and
it sat "deployed but not closeable" for several cycles on exactly this.

**The test for any acceptance criterion is: can this be satisfied by work?** If satisfying it
requires waiting for users, funding, a season, a vendor, or any other thing outside the lane's
control, the criterion is mis-specified. Rewrite it to name the *property* being verified, not the
*population* it is verified against.

Here the property was "the rail captures a cold miss and reports it accurately". A curl exercises
the same middleware a browser does, so the property was fully testable all along; only the wording
made it look otherwise.

### How to apply

1. Synthetic load counts as real traffic **when organic load is structurally absent**. It is not a
   general licence — where organic traffic exists, use it; it carries mix, concurrency and cache
   behaviour a scripted probe does not.
2. **Say which it was.** A closing comment that verified synthetically states so, and quotes the
   numbers. The point of the ruling is that synthetic evidence is *sufficient*, not that the
   distinction is *uninteresting*.
3. When staging a criterion, do not write "under real traffic", "after N users", or "over one hour
   of production traffic" unless the lane can produce that condition. Name the property instead.

### Precedent

Same family as the Manus retirement's "found by a browser ≠ requires a browser": the evidence
requirement had been quietly fused to the tool that first produced it. Here it had been fused to a
user population that does not exist yet.

---

## RULINGS — 2026-08-08 (Alex, batch): banked here because a gitignored handoff file is not a record

Recorded by the latency window; these were issued in-session and would otherwise live only in
`.claude/handoff/ALEX-DECISIONS-2026-08-08.md`, which is gitignored. This doc's own header records
the failure mode twice over: rulings that were "only ever restored in the working tree and never
banked in git".

### THREE-WINNER REPAIR — authorization extended, specimen-gated

Authorization **extended to all 1,885 markets**, same attended capped-batch discipline. Gated on a
**specimen check: the dry-run must show 10 eyeballed specimens per category**, each proving a
genuine single-winner market graded incoherently, **before any category's writes run**. Politics has
legitimate multi-winner structures — **do not repair correct data**; a category that cannot produce
10 clean specimens does not run. Prerequisite: CAL-P007's write path deployed and probed at its
documented default first, per the rail rule above.

WHY the specimen gate: a count cannot distinguish "incoherently graded" from "legitimately
multi-winner". Only looking can. The same move settled LAT-P007 in the other direction — a count
said dropping a query arm would change 17 of 20 visible rows, and looking showed all 17 were
substring accidents, so the "dangerous" change was a precision improvement.

### CALIBRATION CYCLE ORDER

prop-threshold coverage completion → table-tennis 47pp diagnosis → purged-tier reconciliation queue
→ broad Polymarket families. Operational sequencing, not standing judgment; recorded for continuity.

---

## RULINGS — 2026-08-08(e): Alex's second batch

### 1. Prop-cliff bands: TIGHTEN PER MEASURED CLIFF — `program:calibration`

**Ruled:** each affected series' degenerate band is set **where its own measured cliff
begins** — not at a shared constant. Shipped as a **versioned methodology change**: a
population version bump, with **published per-series exclusion counts**. Counts are never
silent. **Fixture-first.**

**#1140 / #1141 still close only on a post-deploy sentinel run showing suppression** — the
calibration lane's own bar, which this ruling does not relax.

Two things worth naming because they generalise past this card:

- **"Per measured cliff" beats a shared constant** for the same reason the UX lane's marker
  spacing did (UX-P022): one constant applied across series that behave differently is only
  right for the series it was tuned on. A threshold has to be derived from the thing it
  bounds.
- **A silent exclusion count is a silent denominator change.** This repo has been bitten by
  exactly that (`project_cal_coverage_denominator`, `project_calibration_pass2loser_poison`):
  a population that quietly changes shape makes every before/after comparison across the
  boundary meaningless. Publishing the counts is what keeps the metric legible.

Owner: **calibration lane**. Recorded here, routed on the cards; the UX lane does not execute
it.

### 2. #1589 precedes the landing page

**Ruled:** the playoff-odds error (63% shown, ~90% actual) is done **before** the
lead-with-games landing-page change.

A straight application of (d)(3) rather than a new rule: truth violations outrank polish, and
a wrong number outranks a better arrangement of correct ones. Worth recording anyway, because
the landing-page work was already pre-staged and the tempting move is to finish what is
queued rather than re-sort against a ruling made after it was staged. **A standing ruling
re-orders work already in the queue.**

### 3. Codex C175's four client parity P1s → UX/native queue

**Ruled:** routed to the UX/native queue via the board.

The class: `/search` and `/typeahead` now emit an additive `degraded` stage list, and **every
client decodes it and throws it away** — web full search, native full search, both web
typeahead surfaces, and native typeahead. All four then replace prior results with a partial
and present it as complete.

The sharp edge, in Codex's words: *a typed degraded success is more destructive than a hard
failure*, because thrown errors preserve or fall back while an HTTP-200 partial takes the
success path. **This is the false-absence bug #1494 kept fixing server-side, reintroduced
client-side.** The backend now tells the truth; the clients discard it.

### 4. LINEAGE: ancestry < patch-id < content

**Ruled:** recorded as a standing rule. It earned it three times in one day.

To answer *"is this change already on master?"* there are three tests, in increasing strength:

| test | command | fails when |
|---|---|---|
| **ancestry** | `git merge-base --is-ancestor <sha> origin/master` | the commit was merged as a **rebased copy** — i.e. normally, here |
| **patch-id** | `git cherry origin/master <branch>` | the Integrator **resolved a conflict** during the rebase, changing the diff |
| **content** | `git diff <sha> origin/master -- <paths>` | essentially never — it asks the question you actually mean |

**Ancestry is the weakest and the most tempting**, because it is one command and returns a
clean boolean. In this repo it is also usually WRONG: Invariant 4 gives rebasing to the
Integrator, so merged work reaches master as a rebased copy with a different SHA. `2309d434`
reported "not an ancestor" while every line of it was on master.

The three occasions today:

1. **UX-P017's stack** — ancestry said the prior UX branches were unmerged; a file-by-file
   content check proved P012/P013/P015 were fully present, which is what let cycle 17 branch
   fresh instead of stacking on spent branches.
2. **INT-019's handoff correction** — `git cherry` (patch-id) reduced `program/ux-8` to one
   commit, catching a stale "STACKED, unmerged" declaration the lane had published.
3. **UX-P022/P023's rebase instructions** — a plain merge conflicted precisely because master
   held rebased copies; the isolating `--onto` base had to be derived from that fact.

**The rule:** never report merge state from ancestry alone. Use patch-id to reduce a stack,
and content to settle whether a change is present. And per UX-P016's lesson, a rebase
instruction is **tested, not asserted** — "the files are disjoint" is not the same claim as
"it applies cleanly".

---

## RULINGS — 2026-08-08 (Alex, re-issued batch): the owed calibration calls, and two process fixes

**Re-issued after two delivery failures.** These were ruled, and then lost with the window that
heard them. They are banked here — the one home that outlives a window — expressly so that no
future window re-asks them. That is this doc's founding failure mode, recorded in its own header:
rulings "only ever restored in the working tree and never banked in git".

### (1) THREE-WINNER APPLY — re-issued unchanged; already banked, not restated

The authorization above in **"RULINGS — 2026-08-08 (Alex, batch)"** stands verbatim and needs no
amendment: **all 1,885 markets**, attended capped batches, gated on the specimen check — **10
eyeballed specimens per category** proving genuine single-winner markets graded incoherently
**before any category's writes run**. **Politics has legitimate multi-winner structures — do not
repair correct data**; a category that cannot produce 10 clean specimens does not run. Re-issue
confirmed 2026-08-08; the earlier section is the text, this line is the receipt that it survived
the re-ask.

### (2) PROP-THRESHOLD BANDS: TIGHTEN PER MEASURED CLIFF, PER SERIES

Ruled 2026-08-09 as issued; re-issued into this batch. Three parts, all required together:

- **Tighten per measured cliff, per series** — not one global band. Each series gets the band its
  own measured cliff supports.
- **Versioned methodology change** — the band change carries a population/methodology version.
- **Published per-series exclusion counts** — every series states how many outcomes its band
  excluded.

WHY all three and not just the first: a global band is a guess applied uniformly to series whose
settlement behaviour differs, and the cliff is *measurable*, so measuring beats guessing (the same
move as the retention cliff — a predicate cannot consume a range written in prose, gotcha #35).
Versioning is what keeps the curve comparable: silently changing an exclusion rule makes today's
ECE incomparable with yesterday's while both call themselves ECE. And an exclusion nobody can
count is indistinguishable from a defect — the published count is what lets a reader tell a
deliberate band from a silent data loss (gotcha #51).

### (3) COVERAGE DENOMINATOR: PUBLISH BOTH FIGURES, NAMED

Publish **both**, each with its denominator in its name:

- **"92.2% of priced outcomes"**
- **"~56% of all resolved, including purged/recoverable"**

Per the standing publish-both-counts doctrine. **The deprecated alias stays until nothing reads
it** — removal is gated on readers, not on a date.

WHY: neither number alone is honest. 92.2% flatters by silently dropping outcomes that never had
a price; ~56% understates by counting rows Kalshi permanently deleted and we can never grade.
Naming both makes the *gap between them* the visible quantity — and that gap is the recoverable
backlog, which is the thing anyone reading a coverage figure actually wants to know. This is
CAL-P014's rule applied to its own headline: a coverage percentage must publish its own
denominator.

### (4) RETIRE OR REWRITE THE CAL-P010 BRANCH

End the chronic `git cherry` false positive. INT-016 merged `bd5ecd3c` **with a `#51 → #53`
renumbering edit**, so its patch-id differs from master's copy permanently; every calibration cycle
since has been told the commit is unmerged, re-verified it by content, and dropped it again.
Retire the branch or rewrite it so its content matches what master carries.

WHY this is worth a ruling rather than another note: a false positive that recurs **by
construction** is not a warning, it is noise that trains the reviewer to skip the check — and the
check is real the one time it fires honestly. Three cycles have now each spent review time
rediscovering the same non-defect. The ladder this established stands and is worth keeping:
**ancestry < patch-id < content** — a conflict-resolved merge defeats the first two.

### (5) LANES DECLARE THE PREDECESSOR'S QUEUE-ID, NOT A BASE SHA

Ratifies the Integrator's request (raised at INT-019, repeated at INT-021). A queue's handoff
declares its predecessor as a **queue-id** (`CAL-P014`), not as `base: <sha>`.

WHY: **three consecutive integration cycles corrected a stale `base:` SHA.** A SHA goes stale the
instant the Integrator rebases the branch underneath it; a queue-id never does. The Integrator
resolves lineage by content regardless — so the SHA field carries risk without carrying
information, which is the definition of a field to delete.

### (6) THE FRESH-WINDOW MEASUREMENT PASS FRONT-LOADS THE OWED PROD READS

The next measurement pass runs in a **fresh window** and takes these reads **first**, before
anything else touches production:

- **GAP 1 warm timing** (`/api/events/search` vs `/typeahead`)
- **CAL-P012 published counts** (the purged tier, read off `/api/calibration`)
- **UX-P023 closed-window props**

WHY first and not last: the `data_exfiltration` guardrail taints a session after a handful of
credentialed calls, so a prod read placed at the *end* of a cycle — as verification usually is —
is the read most likely to be blocked. Three payoffs are owed right now for exactly that reason,
each from a cycle whose code shipped fine. Front-loading converts "verification we could not
reach" into Item 0. Companion trap, twice hit: a pass taken minutes after a deploy reads as a
regression. **The warm second pass is the honest number.**

---

## RULINGS — 2026-08-08(f): defunct-provider cleanup, and how evidence rails get watched

### 1. A consumption census precedes any replace/retire call

**Ruled:** before retiring a data pipeline, **trace end-to-end what reads its output**. Nothing
user-visible consumes it → retire, with the evidence attached. Something real does → stage the
replacement.

Ordered for `social-ground-truth.yml` and immediately vindicated. The census (UX-P027,
`.claude/handoff/SOCIAL-GROUND-TRUTH-CENSUS.md`) found the uploaded rows drive a **live
candidate-pool recall lane in Discover** (`_external_curator_recall_market_ids`, `feed.py:706`,
called at `:3259` and `:5625`). Retiring the pipeline would have **silently removed a live
recall lane**, not merely stopped a feed.

**The part worth generalising:** the FIRST consumer the census found was debug-only —
`external_curator_items` inside `if debug:` at `feed.py:2197`, landing in `debug_payload` and
touching nothing. Stopping there would have produced "diagnostics only → retire", the wrong
answer. The live consumer was 1,500 lines earlier in the same file and read the ORM model
directly rather than through the report helpers, so it did not appear in a grep for those
helpers.

**A census is only worth the exhaustiveness of its grep.** "I found the consumer" is not the
same claim as "I found all of them" — the same distinction as ancestry-vs-content in the
lineage rule, one level up.

It also surfaced a state nobody had named: the pipeline stopped producing 2026-07-28 but the
lane never stopped reading, so Discover is recalling against a **frozen corpus** — not inert,
not current, and silent about which.

### 2. An evidence rail must be watched BY CONSTRUCTION

**Ruled** for `browser-audit.yml` (#1598): repair it, schedule it via **GitHub Actions cron —
not a Cowork scheduled task** — and wire red runs into **sentinel auto-filing**. Adopt Codex's
**C181 jank-classification pack** as its finding vocabulary. Rendered-proof obligations (the
#1574c class) route to this rail once green; **Fable remains the on-demand verifier**.

The failure this closes is subtler than the one it replaces. The retired Manus sweep lied —
it reported `success` having collected nothing. Its replacement does the opposite: its header
states *"the one thing this workflow must never do is report GREEN without evidence"*, and it
delivers, failing loudly and correctly. It had still been **red and unnoticed since
2026-08-03**, because it is manual-dispatch with no alert path.

**A rail that fails honestly into an empty room is not much better than one that lies.**
Honest failure is necessary and not sufficient; someone — or something — has to be listening.
Hence cron plus auto-filing: watched by construction, not by remembering.

"Not a Cowork scheduled task" is deliberate: the watching must live in the same system as the
thing being watched, so it cannot drift out of the repo or die with a session.

### 3. The #1497 deletion deviation is RATIFIED

**Ruled:** deleting `manus-sweep.yml` outright — against #1497's "do not delete the workflows"
— was correct. **The rollback-surface premise died with the provider.** Preserving
dispatchability for an API that returns `USER_IS_DEACTIVATED` preserves nothing.

The general form: **when a card's suggested scope rests on a premise, and the premise dies,
the scope dies with it.** Re-derive from the intent — here, *don't destroy history* — which
was fully honoured by keeping `Manus/audit_results/` and the scripts.

**Also ratified as a reusable template:** the lane's nine "lead, not a measurement" issue notes
are the standard pattern for defunct-evidence cleanup. When a provider dies, every issue citing
its findings gets a note saying the artifact is readable but **the reproduction path is gone**,
so the finding is a lead to re-establish rather than evidence to act on — plus any known
window in which the provider was already lying (here, degradation from 2026-07-28, three days
before the visible 403).

---

## RULING: Integrator single-writer + throughput (Alex, 2026-08-09)

- INVARIANT: exactly ONE integrator session; only it pushes master. Never a second
  integrator, never a pushing subagent. (Named failure: PRODUCT-BRAIN lost-updates.)
- STANDING SCOPE (no "go" needed, ever): merge CI-green program branches; run
  suites/gates; deploy; file issues; fix test-only/eval breakage. Anything outside
  scope = file needs-user issue and END the wait, never idle. (Named failure:
  44-min "awaiting go" stall, int-024.)
- BATCHING: multiple waiting branches with disjoint files merge in ONE cycle —
  one combined suite, one CI run, one deploy. (Named failure: latency-11/-12
  queued as two round-trips.)
- PIPELINING: while CI runs on a pushed merge, prep + focused-test the next
  branch locally; push only after previous CI is green. (Named failure: ~10-min
  integrator idle per cycle.)
- SUBAGENTS: allowed inside the integrator session for READ-ONLY work only —
  parallel test shards, conflict scouting, post-deploy probes. Read in parallel,
  write in series.

---

## RULING — 2026-08-09: THE CALIBRATION EXIT EXAM (Alex) — the slot rotates on evidence, not on effort

**DO NOT REMOVE (CI-guarded).**

> The calibration slot rotates to Discover only when a single evidence document
> (`docs/CALIBRATION-EXIT-EXAM.md`) shows all seven items below, **each with linked proof**.
> Alex reviews the exam **in one sitting**; his pass is the rotation trigger.

1. **Ruling 9 shipped** and the published count reflects **volume-proven trading** — *both
   figures named*.
2. The **trading-activity section led by the matched-bucket comparison**; the raw cross-cohort
   tiles demoted or removed.
3. **Cricket and entertainment** each get a named diagnosis cycle ending in a fix, a documented
   exclusion, or a proven *"the market is genuinely bad here"* — **no massive-error category left
   unexplained**.
4. The **source graph redesigned for legibility** — per-source panels, not overlaid lines.
5. The **native app's calibration surface verified consistent with web**.
6. **Monitoring proven by drill** — the publish-age watchdog and the sentinel guards observed
   **actually firing**, not merely merged.
7. **Backfill recovery measurably progressing** against the 786K recoverable cohort, with the
   capture-floor re-measure on **~2026-08-15**.

### What this changes about how the lane finishes

The lane has run twenty cycles and shipped continuously. What it has NOT done is assemble its
work into one thing a reader can judge in a sitting — every payoff lives in a separate report,
several are "owed post-deploy", and the reader has to reconstruct the state from twenty
documents. **The exam is the deliverable now, not the queues.** A cycle that ships code and does
not move an exam item has not moved the lane toward rotation.

Note the shape of the seven: three are *numbers that must be published and true* (1, 3, 7), two
are *legibility* (2, 4), one is *cross-surface consistency* (5), and one is *proof the alarms
work* (6). Only item 7 has a date, and only because it waits on elapsed time.

### "Observed actually firing, not merely merged" is the general form

Item 6 restates, for monitoring, the rule this doc already banks as *"a rail is not shipped until
it has been invoked post-deploy"*. It is called out separately because monitoring is the case
where the gap is most dangerous and least visible: a watchdog that was merged but never fired
looks exactly like a watchdog with nothing to report. The 2026-08-02 publish failure went
unnoticed for eight days behind precisely that ambiguity.

### The sequencing constraint the exam creates (read before staging any of it)

Items 1 and 3 both change what the published curve plots, so both carry a
`CALIBRATION_POPULATION_VERSION` bump — and a bump takes `/calibration` **dark** until the next
successful beat, because `snapshot_verdict` refuses a cached artifact whose version is not the
deployed one. The already-staged CAL-P019 carries a third bump for the same reason.

**No version bump may ship until the build is publishing again.** Shipping one against a build
that cannot publish re-creates the 2026-08-02 outage exactly. That makes CAL-P016's convergence
the critical path for most of the exam, not merely one queue among several.

### Ruling 9 is hereby OPTION A, by implication — flagged, not assumed silently

`RULINGS-NEEDED.md` item 9 offered **A** (approve a versioned volume-based well-traded bar) or
**B** (keep the snapshot-movement bar). Item 1 says ruling 9 is *shipped* and the published count
reflects *volume-proven* trading with *both figures named* — B ships nothing and names no
figures, and "both figures" is A's own before/after-counts requirement. So A is selected.

Recorded as an inference rather than a quotation, because it is one, and a one-line correction
from Alex is cheaper than a lane blocking on a question he has effectively already answered.
A's conditions carry over intact: before/after counts **by source**, sources with no volume
concept **excluded**, NULL **explicitly UNKNOWN** (never "untraded"), and a published population
version.

---

## RULINGS — 2026-08-09(b): the three exit-exam unblocks (Alex, in session)

**DO NOT REMOVE (CI-guarded).**

Three decisions the exam was blocked on, taken in one sitting after the lane walked through each.
Banked immediately: rulings lost with the window that heard them is this lane's named failure mode
(Alex had to issue the 2026-08-08 batch a THIRD time).

### 1. RULING 9 RESOLVED — the well-traded ladder: volume where we have it, hardened movement where we don't

**Ruled (Alex, refining Option A):** *"Use volume when we have it, and infer volume from multiple
price moves otherwise."*

This supersedes the A/B choice in `RULINGS-NEEDED.md` item 9, which offered only "volume bar" or
"keep the movement bar". The ruling is better than either, because it is **per-row rather than
per-source** and it replaces the weak proxy instead of merely falling back to it. The published
definition becomes an ordered ladder, each row carrying HOW it was classified:

1. `volume_proven` — `volume` is populated; traded iff `> 0`.
2. `movement_inferred` — no volume, but the outcome has enough price observations for the test to
   mean something, and shows **>= N distinct price changes**.
3. `unknown` — neither. Published as its own count. **Never collapsed into "untraded".**

Alex's "both figures named" is satisfied by publishing all three counts, by source.

**Two engineering constraints the lane applies (not new decisions — consequences of the ruling):**

- **`price_moved` today is NOT a count of moves.** It is a two-point comparison,
  `calibration_probability IS DISTINCT FROM opening_probability` — *did it close away from its
  open*. A market that traded all day and returned to its opening price reads as **untraded**. So
  tier 2 is a NEW measurement built from `futures_odds_snapshots` (`outcome_id`, `probability`,
  `captured_at`), not a tweak to the existing flag. The existing bar being weaker than it looks is
  an argument FOR the ruling, not against it.
- **Tier 2 is gated on observation density.** An outcome with 3 snapshots can show at most 2 moves
  however much it traded; classifying it untraded would be a sampling artifact presented as a
  finding — gotcha #53's shape exactly ("an empty 200 is not an absence"). Below the density
  threshold the row is `unknown`, not `untraded`.

**N is MEASURED, not chosen.** On the overlap population — rows carrying both volume and adequate
snapshots — measure how well ">= N moves" predicts "volume > 0". That fixes N empirically and
yields a precision figure to publish alongside the counts. If the proxy turns out weak, that is a
finding to report, not a number to ship.

**Context that shapes how loudly this is presented:** the lane measured the trading-activity effect
on 2026-08-09 and it is SMALL — within a probability bucket, moved and unmoved differ by 1-2pp,
except the 35-50% mid band where traded outcomes over-predict by 5.7pp vs 1.4pp. Sharpening the
definition sharpens a mostly-small signal with one real spike. The section should say so.

### 2. Polymarket recovery — BOUNDED PILOT FIRST, not the full run

**Ruled:** grade a capped batch (~5K outcomes), attended, then **measure the effect on the
published Polymarket curve and report before going further.**

The cohort is 273,438 resolved outcomes with no `resolution_source` at all, 90.1% already priced.
The Polymarket curve is 191,738 observations, so a full run could **more than double it** — and
Polymarket is the worst-calibrated source (2.72pp vs Kalshi 0.82pp). A content change that large
is measured on 5K, not discovered on 246K.

The pilot reports: before/after ECE by bucket, the cleanly-resolvable vs ambiguous split (the
sample says ~64.3% clean), and what happened to the ~36% that did not resolve cleanly.

### 3. Winner-field defects — PAUSE; specimens first

**Ruled:** nothing runs until Alex sees **10 eyeballed specimens per category** from a fresh
dry-run. This is the gate he asked for on 2026-08-08 and whose output has never been produced.

Standing correction recorded with it, because the lane had reported this wrongly: the 2026-08-08
extension to **all 1,885 multi-winner markets** was already given, and the "~9x the approved 214+"
alarm compared two different things. **3,585 is the count of defect MARKETS across two classes** —
`multi_winner` (1,885; a wrong WINNER, which `winner-field-repair` fixes) and `incoherent_field`
(the rest; impossible PRICES summing past 100%, which that rail cannot fix and which is a separate
read-side exclusion question).

Also recorded: Alex's "politics has legitimate multi-winner structures" concern is **already
structurally enforced**, not merely gated by specimens. `repair_winner_field` fails closed — it
writes only where the CLOB returns exactly one winner across the legs, so a genuinely multi-winner
market returns several and is SKIPPED with a recorded reason. It cannot convert correct data into
incorrect data. The pause is for Alex's own eyes on the evidence, not because the rail is unsafe.

---

## RULINGS INDEX — `docs/rulings/`

**DO NOT REMOVE (CI-guarded).** Every ruling from 2026-08-09 onward lives in its own file under
`docs/rulings/`. This section is the index, and `backend/tests/test_product_brain_integrity.py`
asserts it matches the directory **in both directions** — a file with no line here fails CI, and
a line here with no file fails CI.

To bank a ruling: add the file, add one line below in ascending number order, run the test. The
exact shape and the two collision cases are in `docs/rulings/README.md`.

Everything ABOVE this section is the pre-migration archive and stays exactly where it is. It was
not migrated on purpose: rewriting the file whose whole job is to survive rewrites would be the
failure this document already records happening twice.

- [001](rulings/001-ruling-files-replace-product-brain-appends.md) — 2026-08-09 — Ruling appends become one file per ruling (Fable)
- [002](rulings/002-eval-registry-canonical-contracts.md) — 2026-08-09 — Eval registry: canonical contracts by domain (Alex)
- [003](rulings/003-clients-format-never-adjudicate.md) — 2026-08-09 — Clients format, never adjudicate (Alex)
- [004](rulings/004-one-slo-per-program.md) — 2026-08-09 — One SLO per program (Alex)
- [005](rulings/005-extract-on-touch.md) — 2026-08-09 — Extract-on-touch (Alex)
- [006](rulings/006-process-artifact-hygiene.md) — 2026-08-09 — Process artifact hygiene (Alex)
- [007](rulings/007-native-riders.md) — 2026-08-09 — Native riders, and the deferred slot rotation (Alex)
- [008](rulings/008-lock-validity-is-pid-alive.md) — 2026-08-09 — Lock validity is the owner pid being alive (Alex)
- [009](rulings/009-precompute-calibration-freeze.md) — 2026-08-09 — precompute_calibration.py is frozen until the publish converges (Alex)
- [010](rulings/010-sentry-keep-sdk-modular-init.md) — 2026-08-09 — Sentry: keep the SDK, spike a modular init (Alex)
- [011](rulings/011-well-traded-is-volume-when-present.md) — 2026-08-09 — Well-traded means volume evidence WHEN PRESENT (Alex)
- [012](rulings/012-measured-ux-attention-satisfies-the-tier.md) — 2026-08-09 — Measured UX attention satisfies the every-cycle UX tier (Alex)
- [013](rulings/013-explicit-release-frees-a-lock.md) — 2026-08-09 — An explicit RELEASED frees a lock, regardless of pid liveness (Alex)
- [014](rulings/014-verification-infrastructure-inherits-usage-weight.md) — 2026-08-09 — Verification infrastructure inherits the usage weight of what it verifies (Alex)
- [015](rulings/015-holds-must-reach-the-lane.md) — 2026-08-09 — A hold must be written where the lane actually reads (Alex)
- [016](rulings/016-discover-charter-first-queue.md) — 2026-08-10 — Discover charter addendum: the first queue is one arc (Alex)
- [017](rulings/017-any-master-push-holds-the-lock.md) — 2026-08-10 — Any session that pushes master holds the integrator lock (Alex)
- [018](rulings/018-barred-files-integrator-is-the-lanes-hands.md) — 2026-08-10 — A barred file makes the Integrator the lane's HANDS, never a second author (Alex)
- [019](rulings/019-interestingness-tuning-global-until-stratum-gate.md) — 2026-08-10 — Interestingness tuning is global-only until a stratum clears the gate on both sides (Alex)
- [020](rulings/020-lock-and-base-sha-both-gate-a-master-push.md) — 2026-08-10 — A master push needs BOTH the lock and base-SHA equality; a HELD lock never yields to a claim (Alex)
- [021](rulings/021-two-graders-one-input-share-the-decision.md) — 2026-08-10 — Two graders reading one input must share the DECISION, not just the predicate (Fable)
- [022](rulings/022-one-shared-lock-claim-primitive.md) — 2026-08-10 — One shared lock-claim primitive; hand-rolled claim logic is deleted (Alex)
- [023](rulings/023-codex-gets-its-own-branch-and-worktree.md) — 2026-08-10 — Codex gets a dedicated branch and worktree; shared-tree passengers become unrepresentable (Alex)
- [024](rulings/024-one-combined-invalidation-window.md) — 2026-08-10 — The post-publish window is ONE combined invalidation event (Alex)
- [025](rulings/025-availability-envelope.md) — 2026-08-10 — The availability envelope: substitute content must declare itself (Alex)
- [026](rulings/026-freshness-is-one-architecture.md) — 2026-08-11 — Freshness is one architecture, not five mechanisms (Alex)
- [027](rulings/027-entity-pages-render-a-declared-tier.md) — 2026-08-11 — Entity pages render a backend-declared tier; chrome is earned by counts (Alex)
- [028](rulings/028-a-hold-is-declared-never-implied.md) — 2026-08-11 — Readiness is a literal token; a hold is DECLARED, never implied by silence (Alex)
- [029](rulings/029-schedule-adherence-grades-deliveries.md) — 2026-08-11 — Schedule adherence grades DELIVERIES; a gate-skip is healthy (Alex)
- [030](rulings/030-census-runs-before-the-staged-work.md) — 2026-08-12 — The census runs BEFORE the staged work, and may re-decide it (Fable)
- [031](rulings/031-assigned-identity-beats-inferred.md) — 2026-08-12 — Assigned identity beats inferred, and identity precedes the page (Fable)
- [032](rulings/032-a-gate-verifies-only-where-it-runs.md) — 2026-08-11 — A gate verifies only where it runs: a branch is evidence, master is verification (Alex)
- [033](rulings/033-a-go-file-binds-only-its-addressee.md) — 2026-08-12 — A GO file binds only its addressee; others treat it as read-only context (Alex)
- [034](rulings/034-sweep-by-branch-confirm-by-content.md) — 2026-08-12 — The poll sweeps by branch and confirms by content; the ready token is advisory (Alex)
- [035](rulings/035-ratification-is-of-priority-never-diagnosis.md) — 2026-08-12 — Ratification is of PRIORITY, never of DIAGNOSIS; a root cause is a hypothesis (Alex)
- [036](rulings/036-assigned-state-beats-inferred.md) — 2026-08-12 — Assigned STATE beats inferred; part-level inference is monotone and may only add settledness (Alex)
- [037](rulings/037-a-certified-gate-run-is-not-voided-by-adjacency.md) — 2026-08-12 — A certified gate run is not voided to resolve a textual adjacency; the resolution travels to the Integrator (Alex)
- [038](rulings/038-circular-authority-is-never-tier-3.md) — 2026-08-12 — Circular authority: a grade computed from our own data is never tier-3 (Alex)
- [039](rulings/039-a-lookup-must-never-throw.md) — 2026-08-12 — A lookup must never throw; an interim tie-break carries its own expiry (Alex)
- [040](rulings/040-two-defects-two-left-edges.md) — 2026-08-12 — Two defects, two left edges: a sweep reports per defect, never one blended number (Alex)
- [041](rulings/041-search-ranks-by-match-class-on-owned-evidence.md) — 2026-08-12 — Search ranks by MATCH CLASS, and an entity ranks only on evidence it OWNS (Alex)
- [042](rulings/042-dereference-the-id-never-the-label.md) — 2026-08-13 — Dereference the id, never the label; a check built on a label measures the labeller (Fable)
- [043](rulings/043-taste-enables-a-signal-labels-tune-it.md) — 2026-08-13 — Taste may ENABLE a signal; only labels may TUNE it (Alex)
- [044](rulings/044-rendered-green-is-not-communicates-green.md) — 2026-08-13 — Rendered-green is not communicates-green (Fable)
- [045](rulings/045-monotone-protects-the-direction-not-the-input.md) — 2026-08-12 — Monotonicity protects the DIRECTION, never the INPUT; a parent settles children only when atomic in time (program-ux, AMENDS 036 — awaiting Alex ratification)
- [046](rulings/046-a-stacked-change-is-measured-on-its-own-deploy.md) — 2026-08-13 — A stacked change is measured on its OWN deploy; an ungradable measurement is a lost one (Alex)
- [047](rulings/047-one-card-system.md) — 2026-08-13 — One card system: every surface renders events/markets through the shared cards; league pages get no bespoke variants, and a new card type needs a design ruling first (Alex)
- [048](rulings/048-an-id-less-claim-never-absorbs.md) — 2026-08-14 — An id-less claim NEVER absorbs; it creates with provenance and id-keyed reconciliation drains the duplicates — design, not thresholds, after five #1801 blocks (Fable)
- [049](rulings/049-a-criterion-that-cannot-fail-is-not-evidence.md) — 2026-08-14 — An acceptance criterion that cannot fail after the fix is not evidence; and a claim you have already committed is corrected IN the record, never left to stand (Fable)
- [050](rulings/050-a-control-that-cannot-fail-is-not-a-control.md) — 2026-08-13 — A control that cannot fail is not a control: read the null prediction, and arm it with a HALT (Alex)
- [051](rulings/051-below-the-floor-a-source-is-absent-not-stale.md) — 2026-08-14 — Below its evidence floor a source is ABSENT, not stale: sportsbook consensus floors at 3 books, then drops and re-weights — never freezes (Alex)
- [052](rulings/052-measure-the-instruction-before-you-obey-it.md) — 2026-08-14 — Measure the instruction before you obey it; ship the payoff sentence and name the words you skipped (Alex)
- [053](rulings/053-a-binary-card-leads-with-the-side-its-question-names.md) — 2026-08-14 — A binary card leads with the side its own question names; series keep both (Alex)
- [054](rulings/054-honoring-a-remove-ruling-means-measuring-its-sites.md) — 2026-08-14 — Honoring a remove-ruling means measuring its sites, not counting its lines (Alex)
- [055](rulings/055-a-conflict-resolution-that-changes-a-decision-is-a-decision.md) — 2026-08-14 — A conflict resolution that changes a decision is a decision, and is recorded like one; a duplicate number renumbers, never keep-both (Alex)
- [056](rulings/056-unmeasured-is-not-ineffective.md) — 2026-08-14 — Unmeasured is not ineffective: a null read indicts the instrument until the probe set is shown to discriminate that change class — and the fix is an OUTCOME-EVIDENCE probe class, not a caveat (Alex)
- [057](rulings/057-the-provability-floor-is-derived-from-detection-power.md) — 2026-08-14 — A cell's provability floor is DERIVED from detection power, never chosen; an under-powered cell is UNPROVABLE, never GREEN (Fable)
- [058](rulings/058-a-column-default-is-not-an-observation.md) — 2026-08-14 — A column default is not an observation; aggregate on provenance, exclude and COUNT the ungraded, and declare the resulting metric shift as correction (Fable)
- [059](rulings/059-a-double-cannot-adjudicate-the-engine-it-doubles.md) — 2026-08-14 — A double cannot adjudicate the engine it doubles; engine-semantics claims run against the real engine or are not made (Fable)
- [060](rulings/060-never-grow-a-graded-cohort-in-place.md) — 2026-08-14 — Never grow a graded cohort in place: a new probe class ships in `canary` and enters the graded split only at a deliberate, announced re-baseline (Alex)
- [061](rulings/061-a-derived-figure-is-an-interim-with-an-expiry.md) — 2026-08-14 — A derived figure is an interim, and an interim carries an expiry: the payload publishes what the client renders, and the derivation is deleted the day it does (Alex, extends 003)
- [062](rulings/062-branch-where-the-dependency-lives.md) — 2026-08-14 — A branch bases where its dependency lives, and disjointness is measured at content level, never read off merge-tree's conflict count (Alex)
- [063](rulings/063-a-gate-that-reads-shared-state-names-it.md) — 2026-08-14 — A gate that reads shared mutable state names what it read, and fails only on ambiguity that could change its verdict (Alex)
- [064](rulings/064-the-sandwich-is-permanent-doctrine.md) — 2026-08-14 — The sandwich is permanent doctrine for this program: read before, deploy alone, read twice, against a control armed in advance — it has now paid three times in three different failure classes (Alex)
- [065](rulings/065-report-the-mutation-split.md) — 2026-08-14 — Report the mutation split, never the flattering aggregate: "killed here, owed to CI" beats a false 8/8, and "owed" is a state with an addressee (Alex)
- [066](rulings/066-a-deferred-read-owes-a-receipt.md) — 2026-08-14 — A deferred read owes a receipt, not an assertion: a deferral is the one decision that leaves no diff, so it must emit a falsifiable artifact with a named exit condition (Alex)
- [067](rulings/067-extract-the-state-and-pin-it-against-its-old-self.md) — 2026-08-14 — A `@State` defect is extracted into a value and pinned against its old self; the trigger is any behaviour visible only in a SEQUENCE (Fable)
- [068](rulings/068-a-premise-waiting-item-is-re-anchored-at-every-run-start.md) — 2026-08-14 — A premise-waiting item is RE-ANCHORED at every run start: a bound naming something that did not exist when it was written is a liveness claim that decays, and a gate that cannot fire must never look like a gate that passed (Alex; renumbered from 053 per 069)
- [069](rulings/069-the-ledger-is-the-allocator.md) — 2026-08-14 — The ledger is the allocator: a number is held by the first CLAIM, not the first merge, and a renumber target is MEASURED at renumber time, never quoted from a document (Fable, extends 055)
- [070](rulings/070-premise-checks-run-against-origin-master.md) — 2026-08-15 — Premise-checks run against `origin/master`, never your own base: the error is directional, so landed work always reads as MISSING (Alex, on the queue-357 acceptance; sibling of 068)
- [071](rulings/071-a-malformed-lock-reads-as-held.md) — 2026-08-15 — A lock file with more than one `status:` or `owner_pid:` line is MALFORMED and reads as HELD, fail-safe; repair belongs to the owner while its pid is alive, takeover only per 008 (Fable, extends 008 + 013)
- [072](rulings/072-a-fixture-that-agrees-with-the-bug-is-the-bug.md) — 2026-08-17 — A fixture encoding the code's own assumption cannot falsify it: wire-shape fixtures are CAPTURED from production verbatim, never authored, never trimmed, and counted against the served count rather than the parse (Fable via #1886, where five bundle test files all passed over a decoder that dropped every live bundle card)
- [073](rulings/073-corpus-moved.md) — 2026-08-17 — CORPUS-MOVED: a disposition change with no code change is a corpus event, not a ranking result; per-probe eligible-pool fingerprints, quarantine the delta, and the baseline moves only by an explicit re-baseline naming the expired specimens (Fable)
- [074](rulings/074-a-green-pass-names-the-work-it-did.md) — 2026-08-17 — a green pass names the WORK IT DID, never the time it took (a completion metric counts work performed, not requests answered — the refresh-ahead hole joins the instruments-that-lie taxonomy); and a bar is set UNDER a re-derived ceiling, never above a quoted one (Fable)
- [075](rulings/075-a-derived-budget-may-never-fall-below-the-measured-floor.md) — 2026-08-17 — A derived budget may never fall below the phase's own measured floor: below it the component REFUSES loudly and marks itself unrunnable, never run-and-timeout, because a killed phase appends nothing to the ledger its next budget is derived from (#1680's self-locking ratchet; the row-delete was a restart, not a cure). Second clause, banked as doctrine: "could not check" must never render as "nothing to report" (Alex, owed out of q359, banked by q360)
- [076](rulings/076-planner-cost-cannot-rank-two-statements.md) — 2026-08-17 — planner cost ranks PLANS FOR ONE STATEMENT; across two statements it is not a comparison — a query-rewrite flip is gated on MEASURED, PAIRED, ALTERNATING runtimes plus buffers, with plan shape as a necessary precondition and cost as corroboration only; and a rewrite measured worse is DELETED, never parked behind an off flag (Fable, after step 5.3 ranked `UNION` vs `OR` backwards and would have shipped a 4.8× regression with a green certificate)
- [077](rulings/077-check-the-cause-before-working-the-symptom.md) — 2026-08-17 — a SYMPTOM filed as its own issue must be checked against the open issue list for its CAUSE before it is worked, searching the symptom's own `area:`/`program:` labels first; when the cause is already filed, mark the symptom blocked on it and comment the evidence onto the CAUSE, where the acceptance lives; and exhaust the reachable evidence before requesting the unreachable (latency, after #1922 was staged as a warmer defect for a whole window while #1609 had named the queue-level cause nine days earlier under the same `program:latency` label — the cost of not looking is not a duplicate issue, it is a fix aimed at the symptom, which downgrades a p1 without anyone deciding to)
- [078](rulings/078-a-shared-eligibility-predicate-gets-one-implementation-and-a-contract-test.md) — 2026-08-17 — A shared eligibility predicate gets ONE implementation, imported by every surface, and a contract test that asserts the CALL per surface by name (an AST call node, never a substring — the first version of that very test was satisfied by the docstring describing the call). Four-for-four across three windows: #1924 web-behind-iOS, #1933 native-behind-web, `market_identity_disputed`, and `enforce_live_requires_start`, which shipped with ZERO importers while the surface it governed served four wrong MLB cards. A rule with no consumer is a document, and a document cannot fail a build (Fable)
- [079](rulings/079-a-refused-population-is-admitted-by-evidence-never-by-widening-the-constant.md) — 2026-08-18 — A refused population is admitted by ATTENDED EVIDENCE per member, gathered OUTSIDE the predicate — never by widening the constant that refused it; the census inverted its own verdict on first run, proving the four "MLB duplicates" are five REAL scheduled games wearing another game's espn_id and score, so widening `MAX_ABSORPTION_SEPARATION_SECONDS` would have deleted them (Alex, #1947)
- [080](rulings/080-provider-anchors-are-a-table-and-a-migration-slot-is-integrator-owned.md) — 2026-08-18 — `event_provider_anchors` is RATIFIED as a table, not two more scalar columns (cardinality: Kalshi tickers vs Polymarket nested condition_ids, `id_kind` gates absorption) — and a migration slot is an INTEGRATOR-OWNED ARTIFACT that a lane requests and never takes, carrying four conditions: table-only, GIN out of band (gotcha #31, an Alex action), backfill as a task, rev-id ≤32 (Alex, #1946)
- [081](rulings/081-a-clause-that-pays-out-in-its-own-banking-window-is-doctrine.md) — 2026-08-18 — A clause that pays out INSIDE ITS OWN BANKING WINDOW is doctrine immediately, without ruling 064's three-payout bar: ruling 078's clause 3 is permanent — assert on an `ast.Call` node, never a source substring, and RUN THE MUTANT — because its own author, minutes after writing it, wrote a guard satisfied by the docstring explaining the call (Fable, #1947)
- [082](rulings/082-consistency-is-the-requirement-not-the-constant.md) — 2026-08-18 — Consistency is the requirement, not the constant: where a figure is displayed, enforced and derived, R5 certifies that the three AGREE and certifies nothing about the value — the R4 ceiling fix is accepted as shipped and the 5,500/day specimen it falsified was the thing that was wrong; a constant may be retired BY a ratified change in derivation, never to avoid one (Alex, #1894)
- [083](rulings/083-a-guard-that-cannot-tell-two-cases-apart-is-given-evidence-not-a-wider-band.md) — 2026-08-18 — A guard that cannot tell two cases apart is given EVIDENCE, not a wider band (ruling 079's clause, restated for a threshold): the publish gate could not separate a methodology change from sixteen days of growth, so the artifact now STATES its population predicate and the ±5% band is relaxed only where the code proves the qualifying rule did not move. And a version bump is an OPERATOR ACT that carries its own rollover declaration or accepts a dark page — q268 is the LAST bump that may mean "time passed" (Fable, #1955/#1680)
- [084](rulings/084-authority-lives-where-it-is-read.md) — 2026-08-18 — AUTHORITY LIVES WHERE IT IS READ: a rule's authoritative statement sits at the point it is CONSUMED, because any copy upstream of the read is a second policy that drifts silently — a threshold resolves at CALL time (cycle 89), a rule with N implementations needs a test NAMING every copy and its grader must never be the permissive one (cycle 90), an assertion may only count the population its ID names (cycle 91, `page_view_exactly_once` matching on HOST). Reference implementation `contracts/feed_card_admission.json` (#1951), whose first run found a live defect three agreeing implementations had hidden; fourth instance #1948, where the cache tier's 'the route serves the mirror' comment stayed true for one of two consumers (Fable)
- [085](rulings/085-a-ready-whose-branch-head-moved-is-withdrawn-not-re-gated.md) — 2026-08-18 — A READY whose branch head moved is WITHDRAWN, not re-gated by the Integrator: the token names a branch AND a head SHA, and gate evidence is a claim about one tree, so when the head moves the certificate certifies nothing. The Integrator posts a withdrawal notice naming both SHAs and moves on; the LANE re-issues at the new head. Re-gating is not cheap (INT-085 lost 24 minutes to calibration-66 while cohort-views took three SHAs in an hour), it relocates authorship of the evidence to a party that did not author the change, and it rewards the behaviour that caused it. Corollary: a READY with NO `status:` line is not a quieter request, it is silence — it never enters the sweep at all (Fable, #1621)
- [086](rulings/086-the-working-gauge-nobody-reads.md) — 2026-08-18 — the working gauge nobody reads is the same as no gauge: a correct, tested instrument with no consumer outside its own test suite counts as ABSENT, wiring it to a read surface is part of building it, a window owing a read must check for a SECOND gauge before owing it again, and a gauge wired on an unmerged branch is not yet a reader (Fable, after `get_hard_kill_census()` sat with ZERO production consumers for two months while eight consecutive latency windows honestly re-owed a `hard_kills` read its blind twin could not answer)
- [087](rulings/087-an-exclusion-is-only-safe-where-a-mutation-can-red-it.md) — 2026-08-18 — AN EXCLUSION IS ONLY SAFE WHERE A MUTATION CAN RED IT: every exclusion/allowlist/carve-out ships with a named runnable edit that widens it and turns a SPECIFIC test red, because an exclusion is the one predicate that gets quieter as it gets more wrong — widen a grader and it fails loudly, widen an exclusion and everything goes green (gotcha #53 one level up: a green run cannot tell 'nothing was wrong' from 'nothing was looked at'). A test that asserts the exclusion FIRES is not a sensor; only widening it to always-apply asks whether anything is still graded. Charter case UX-P095's third-party abort, whose reported no-sensor gap did NOT survive the mutation (15 reds); census of all seven carve-outs in `navigationAborts.js` is 7/7 covered, thinnest `isInstrumentInduced` at 1 (Fable)
- [088](rulings/088-a-lane-may-rebase-when-arriving-un-rebased-is-guaranteed-red.md) — 2026-08-18 — A lane MAY rebase — rule 4 notwithstanding — when arriving un-rebased is GUARANTEED-RED, provided the exception is documented in the report, the gates re-run green on the new base, and BOTH bases are named. This is the pattern, not a pardon. "Guaranteed-red" means demonstrated (a `merge-tree` conflict, a named collision in a shared append region, a constant whose merged value is neither side's), never anticipated; one rebase, not a chase; base drift is disclosed, never absorbed. Charter case LAT-P068, which hit BOTH a ruling-number collision and a `MINIMUM_BANKED_RULINGS` conflict whose correct merged value was neither side's (Fable, #1609/#1621 — the directive said 087, but 087 was already claimed by `ux`, so this moved to 088)
- [089](rulings/089-a-budget-derived-only-from-successes-cannot-be-corrected-by-the-failures-it-causes.md) — 2026-08-18 — A budget derived only from SUCCESSES cannot be corrected by the failures it causes, so the window's unallocated time goes to the phase that is starving on it: two consecutive q268 beats were cancelled by the build's OWN 159,637 ms statement timeout (measured reads 159,801 and 159,767 — overheads of 164 ms and 130 ms), a cap derived from ten pre-bump completions that every subsequent failure records a FLOOR against and a floor may never raise. Phase budgets still derive from measurement (ruling 075), with the 1,380,000 ms window as ceiling and the ~72% no phase claimed assigned to the bottleneck — chosen by truncation evidence, never by name, with `budget_basis`/`slack_assigned_ms` keeping the measurement recoverable (Fable, #1977/#1680)
- [090](rulings/090-a-population-is-a-contamination-vector-not-a-symptom.md) — 2026-08-19 — A POPULATION IS A CONTAMINATION VECTOR, NOT A SYMPTOM: rows broken by different writers are different populations even when they present identically, and grafting the odd ones onto a reviewed object as exceptions destroys the review — the repair does not fit (writing an `espn_id` that is already correct is a no-op reporting success) and the address stops meaning what Alex approved. Two small reviewed objects beat one large object with a footnote. Charter case: #1981's three `external_id`-only victims, flagged by queue 370 for assignment rather than folded into #1947, and ruled onto #1981's population (Fable)
- [091](rulings/091-stale-id-ownership-goes-with-the-writer.md) — 2026-08-19 — STALE-ID OWNERSHIP GOES WITH THE WRITER: a writer that finds a row BY a provider id may not use that id as evidence the row is the right one — it re-verifies against an independent signal, re-binds, or nulls, and NEVER compares against a stale id. The circle is invisible because it is spelled across two statements (#1981: found by `external_id`, then asked whether the SCORE RECORD's commence had passed, never the row's own — the previous night's final onto the next night's game every 300s). Deferring a stale id to a cleanup queue leaves the writer reading it and the cleanup spent on arrival. Null only where the column tolerates it — `events.external_id` is UNIQUE. Gotcha #32 closes into this (Fable)
- [092](rulings/092-a-deriver-may-not-emit-a-credential-it-cannot-cite.md) — 2026-08-19 — A DERIVER MAY NOT EMIT A CREDENTIAL IT CANNOT CITE: code deriving a reviewed object must not stamp it with a human approval — omit the field, because a missing credential prompts the question while a forged one answers it. A ruling NUMBER is a citation and stays true wherever copied; "Alex approved" is true only of the rows it was written for. Charter case: `create_events_from_truth` stamped every plan with an approval dated 2026-08-17, which population 3 inherited a window later for four games Alex had never seen. Provenance goes ON the artifact, recorded by whoever takes the MC — free, because content addresses cover rows, not context (Fable)
- [093](rulings/093-a-cert-block-outranks-a-held-age.md) — 2026-08-19 — A CERT BLOCK OUTRANKS A HELD AGE: when a certification returns BLOCK on an item also aging in the HELD table, the row is RE-WRITTEN onto the cert's findings — not re-aged, not released. Age is a proxy for "nobody is looking"; a BLOCK is direct evidence somebody looked and found something, and direct evidence outranks its own proxy. The two failures look identical in the age column and are opposites: a stale gate should be released, a blocked one fixed. Charter case: the 341 row at age 13, re-gated onto `C-APPLY-PRE-CREATE`'s two findings with the age left running (Fable)
- [094](rulings/094-a-shared-tree-is-not-a-measurement.md) — 2026-08-19 — A SHARED TREE IS NOT A MEASUREMENT: every code finding is read from a detached worktree at a freshly fetched `origin/master` and names its SHA. A stale shared tree does not fail, it AGREES WITH ITSELF — `~/bainluck` at `6f0d724c` (a true ancestor of master) reads exactly as though PR #1971 never landed, so the reading is honest and the conclusion false, with no symptom to notice. The READ-direction twin of gotcha #51: the tree a read lands in is invisible in the read, and the shared tree is the one nobody owns (Fable)
- [095](rulings/095-a-census-of-a-moving-population-is-fiction.md) — 2026-08-19 — A CENSUS OF A MOVING POPULATION IS FICTION: before a repair censuses, it must FREEZE the population or PROVE stillness — N >= 3 reads spanning > 300 s with identity fields unchanged — and a merged writer-fix is not a stopped writer, only a DEPLOYED one is. The failure is hard to see because a census over a moving population SUCCEEDS: it returns rows, mints an artifact, and digests stably, because a digest over fiction is a perfectly good digest. Charter case is queue 371's eight-flapper repair, re-read ~50 minutes apart, where the rows' IDENTITY had moved — `15199901` from commence 08-18 22:40 to 08-19 16:35 `live` 4-1, sixteen hours before first pitch — so a plan bound by (sport, commence_time, teams) would have addressed a different row than it described, and a per-row CAS derived from the same moved fields could match the WRONG row. A census that cannot prove stillness produces a REFUSAL, not a smaller census: narrowing to the rows that held still selects for rows between writes, a sample biased toward looking calm (Fable, #1981/#1989)
- [096](rulings/096-a-read-only-endpoint-is-not-a-safe-endpoint.md) — 2026-08-19 — A read-only endpoint is not a safe endpoint: "read-only" bounds what a handler can CORRUPT and says nothing about what it CONSUMES, and on a single-loop web dyno the loop is the thing worth protecting. Blocking work never runs inline in an `async def`; an endpoint that will be POLLED needs a memo, not just a timeout (a timeout bounds one request, cadence is the load); a window that polls production owns the load it creates and names it in its own evidence. Charter case: two READ-ONLY samplers on `/api/admin/celery-debug` (20s and 8s) took the whole API — `/api/health` included — to 503 at the H12 ceiling for ~10 minutes while `heroku ps` reported the web dyno `up` with uptime unbroken; killing them by pid restored p50 to 0.23s in 25 seconds with no restart. Gotcha #39 is the same defect in `tasks/` and was never carried across to `routes/`. The safety review asked what the endpoint writes when it should have asked what it occupies (latency lane, self-reported, #1609)
- [097](rulings/097-no-statistic-rescues-a-bad-pair.md) — 2026-08-19 — NO STATISTIC RESCUES A BAD PAIR, AND A TIE PRINTS THE MIDPOINT: a two-source pair whose spread exceeds a MEASURED sanity threshold does not blend — render the primary source's own value and flag the pair to matching as a suspected mis-link, because a 51.5pp gap (AL West Houston: kalshi 0.575 vs polymarket 0.060) is one reading about a different question, and a mean (31.75%) is not more correct than the median (6%), only differently wrong. Threshold DERIVED — Tukey fence Q3+1.5*IQR = 0.3946 on the live 76, adopted 0.40, identical selection. 'Primary' = highest EFFECTIVE weight after decay, never base authority, or the gate reprints the stale pregame line over a live blowout and rebuilds #240; consequence is that it changes ZERO of 76 heroes and buys the flag plus the never-a-mixture invariant. Clause 2: a two-source EQUAL-WEIGHT merge prints the MIDPOINT (futures_source_merge only; the events aggregator's heavier-source tiebreak stands) — measured, median == min on 3 of 3 with delta == -spread/2 exactly, so an always-downward tiebreak is a systematic discount and the sort order it reads carries no meaning. Gate FIRST: the midpoint is the first genuine mixture we print, and ungated it would render 31.75% as a finding (Fable)
- [098](rulings/098-a-control-and-its-metric-are-counted-on-one-window.md) — 2026-08-19 — A CONTROL AND THE METRIC THAT GRADES IT ARE COUNTED ON ONE WINDOW, AND THE WINDOW IS NAMED IN BOTH: `enforce_first_page_quality_floor` protects the first twenty SERVED cards and was doing so perfectly (0 boring futures in the served top-20, matching the server's own `debug_summary.boring_count`), while `audit_feed_quality.py` / `census_boring_rate.py` filter to `type == "futures"` first and grade a different twenty — offset by the 4-6 bundle cards the page interleaves, so every card the metric flagged (Maine State Senate #17, META $540 #18, 2Y Treasury #20) sat at SERVED position 22, 23, 24, past the fold of the page the metric names. Both numbers correct about their own window; only one has a screen behind it. Three obligations: the window is part of the metric's NAME (print `[SERVED]` / `[futures-only]`), the offset is MEASURED per read (`non_futures_in_served_window`) never assumed equal, and a metric is never renamed into its replacement (the futures-only number stays labelled, or every prior cycle's comparison dies). The failure mode is that BOTH readings are defensible, so the gap lives exactly where no artifact holds both numbers at once (Fable)
- [099](rulings/099-measure-the-baseline-before-judging-the-read.md) — 2026-08-19 — MEASURE THE BASELINE BEFORE JUDGING THE READ: a single measurement is not evidence until the distribution it came from has been measured, and the reading is reported as a POSITION IN THAT DISTRIBUTION rather than a number against an intuition. Charter case is a CORRECTION, not a catch: a post-#2005 recovery probe read 14.85 s and was on its way to being written up as incomplete recovery, when 14.85 s is the **36th percentile of that rail's own cold distribution** — a below-median cold read. The class survives careful work because the finding is specific, quantified and reproducible; only the comparison is invalid. Post-incident is when everyone is primed to read the next number as a symptom, so the baseline is least likely to be measured exactly when it is most load-bearing. Same shape as `reference_post_deploy_latency_not_evidence` and gotcha #49's lifetime Sentry count — a real number against the wrong distribution. Obligation runs both ways: the honest intermediate state is UNJUDGED (Fable, ratifying lane1 q375 — renumbered 096->098->099: 096 AND 097 were both taken on master in this cycle, and 098 was then found CLAIMED BY UX in the ledger with a fresh-fetch sweep on record while lane1 had no entry — the ledger claim wins, not seniority, per the INT-090 hold on PR #2008; 099 verified free against master `bac5fce7` across 461 refs, holders_found 0)
- [100](rulings/100-a-metric-and-its-early-warning-are-different-jobs.md) — 2026-08-19 — A METRIC AND ITS EARLY WARNING ARE DIFFERENT JOBS, AND BOTH ARE REPORTED: ruling 098 proved the two `boring-rate@20` windows measure different twenties and refused to let either stand in for the other, but did not say which one the metric TARGETS — and an unassigned role cost a cycle arguing 0.00% against 6.00% for the same named metric on the same day. Assigned: `boring-rate@20` targets the SERVED window, because what users see is the product truth, and it reads 0.00% with `enforce_first_page_quality_floor` doing its job. The futures-only rate is RETAINED as the SUPPLY metric — not demoted — because it measures the pool the floor must screen and is therefore the early warning for pages the floor cannot save. The reason it cannot be dropped: a floor working hard and a floor with nothing to do read IDENTICALLY on the served number (both 0.00%) and diverge only on the input, so reporting only the green grade hides the day supply worsens faster than a twenty-slot floor can absorb. Obligation is both numbers, every audit, named windows AND named roles, shipped in all three instruments and asserted on the ROLES rather than the surrounding prose. No new doctrine clause: this is a specialisation of clause 14, and restating it would be the duplication clause 14 prevents (Fable)
- [101](rulings/101-group-dont-cull-and-a-travelled-bar-ends-at-the-resolution.md) — 2026-08-19 — GROUP, DON'T CULL; AND A TRAVELLED BAR MAY NOT END ANYWHERE BUT THE RESOLUTION: Alex's verdict on the four cycle-99 expand captures. (1) Density fails — "a comical number of rows … but the answer shouldn't just be to nuke or hide valuable outcomes" — so ZERO outcomes are removed and the count comes down by grouping: ladders collapse to one row per player+stat with rungs inside it (#1639's dedupe learning as UI), rows group by market family / player with per-group expand, and the off-script-first fold is ratified by silence. (2) The post-game travelled bar ends at the LAST TRADED PRICE, not the resolution, which is *settled means settled* violated by a chart — a market that settles YES whose last trade printed 0.82 draws a bar ending at 82% on a question already answered. Post-game renders pregame mark + resolved outcome ("18% → HIT" / "71% → MISSED") with surprise = |resolution − pregame mark|; the red/green line is explicitly APPROVED in-game and lives only there. Gated on a diagnosis first: if the payload lacks resolution on those rows it routes to GRADING, not UI, or the fix ships a bar that still cannot reach 0/100. (3) Screenshot durability option 2 ratified — the integrator commits `docs/screenshots/` on its next master write, the program branch stays untouched (executed at `7be90eab`). Mocks before build, back to Alex once more (Alex, relayed by Fable)
- [102](rulings/102-a-worker-ships-with-a-test-that-starts-it.md) — 2026-08-19 — A WORKER SHIPS WITH A TEST THAT STARTS IT: every worker/consumer/task/script carries at least one IMPURE test that drives the real entry point a human would call, through the real wiring, over a stub — caller-not-helper applies to us, not just codex. Pure tests prove the DECISIONS and zero facts about whether the code runs. Charter case: `cohort_cell_census` (#1978) merged with **37 tests, all pure**, passed CI and a clean integration, deployed at v3863, and died in **73 ms on every invocation** — `get_task_session` is an `@asynccontextmanager` and the worker hand-drove it as a bare async generator. 17,093 green tests over a worker that had never run, plus two more defects behind it (`resume=True` never resumed; `GET .../last` could not read a partial census), all three found within minutes of the first real start. The rule is deliberately weak enough to be followed — there is no local Postgres here, so it asks for `main()` over a stub, not an integration suite. It paid out in the window that banked it: CAL-P077's own new reader obeyed the rule, its impure test covered the fold path and not the two side probes, and one `statement_timeout` on an uncovered branch killed a 49-cell sweep after 30 cells. General clause to doctrine: **a green suite over code that has never executed is evidence about the suite, not about the code** (Fable, CAL-P077 ruling (a))
- [103](rulings/103-a-price-captured-after-the-answer-is-not-a-price.md) — 2026-08-20 — A PRICE CAPTURED AFTER THE ANSWER IS NOT A PRICE: the hindsight-capture exclusion (`MC-PACK-CAL-P077-HINDSIGHT-CAPTURE.md` policy C) is APPROVED, GATED ON CERT. `opening_captured_at > resolution_date` means our first look at the row postdates the market's resolution, so the row carries the answer wearing a price's clothes — phantoms under standing ruling 8. Exclusion is the measured-only-sound option, not the fallback: re-pricing was measured UNAVAILABLE over the whole population (481 of 35,976 hindsight rows — 1.34% — have any snapshot before their own `resolution_date`; hockey/cm 0 of 1,259), and a policy cannot be preferred over one that cannot execute. The apply fires only when ALL THREE hold: `C-APPLY-PRE-WHICHPRICE` passes its named attacks, `program/calibration-74` is deployed, and the scoped GO file exists. The ruling-009 exception is GRANTED and scoped to EXACTLY ONE exclusion CTE in `_calibration_population_ctes`, CAL-P039 GO-file shape — read-side, whole markets (the 101 mixed markets in 464,777 go whole too), reversible in one commit, nothing else in the frozen file opened. Costs ruled accepted and named rather than discovered: 9.3% of the curve removed, the headline moves 3.763 → 1.766 pp, `politics/container_member` gets WORSE by +0.28 pp, and two cells fall below `MIN_CELL_N` into an ABSENCE WITH A REASON, never a fixed cell. General clause owed to doctrine: a row-dropping fix is graded on the rows it KEEPS and on the cells where the mechanism is ABSENT — policy D is the proof, discarding 69% of the population to make the pooled curve WORSE (+0.073 pp). A fallback price is not a bad price; a hindsight price is (Alex, via Fable, on CAL-P077)
- [104](rulings/104-hold-the-ttl-at-65-and-record-that-the-input-moved.md) — 2026-08-20 — HOLD THE TYPEAHEAD TTL AT 65 s, AND RECORD THAT ITS INPUT MOVED: Alex holds the ratified 65 s. MARGINAL is recorded as the honest grade rather than reconciled away, the foreclosure on re-deriving the TTL upward stands, and the TTL was never the repair. LAT-P075 shipped 45 → 65 under GO ruling 4 and disclosed in the same commit that the input moved between derivation and shipping — `PASS_ONLY_WALL_MAX_S` 53.920 (n=17) → 61.282 (n=26) on the first read of the deployed instrument — which drops the same grader from SAFE to MARGINAL (75 s would be SAFE). That move was seen and ruled on, so a future window reading MARGINAL beside a ratified 65 must not conclude the ratification is stale and "fix" it. Holding is right because the grade is not the objective: raising the TTL buys head-cold coverage by serving staler entries and cannot buy much (time-weighted head-cold 49.7% at 45 s, 38.9% at 65 s, and zeroing it needs TTL ≥ 553 s), so a TTL chosen to survive a regressed period is a decision to serve stale data instead of fixing the period. General clause: a sampled maximum is a LOWER BOUND and a threshold derived from one inherits that — third instance in this program (42.6 → 53.9 → 61.3), so a later upward revision is the estimator behaving as designed, not a regression in the estimate. Pinned by `test_the_ring_wall_grades_the_ratified_ttl_marginal`; the derivation is CLOSED (Alex, via Fable)
- [105](rulings/105-suppress-structural-rungs.md) — 2026-08-20 — SUPPRESS STRUCTURAL RUNGS: near-certain ladder rungs whose certainty is explained by their POSITION in their own ladder are filtered out of the five-row script rail; conviction ranking is unchanged among what remains and every suppressed rung stays reachable in "See all N" — rail capacity, never a taxonomy loss. The predicate is a CONJUNCTION and never the price half alone (near-certain NO + a lower rung exists; near-certain YES + a higher rung exists; a family of one is NEVER structural at any price), because the population itself proves a cutoff cannot work: event `15199902` carries three "3+ hits" questions all priced EXACTLY 6.0%, and only the two with a 2+ rung beneath them are arithmetic. `PROP_STRUCTURAL_CERTAINTY = 0.44` is p95 of the same 183-question distribution `PROP_SCRIPT_CONVICTION` took p90 of — one step TIGHTER because this constant REMOVES where the other three ESCALATE, and a wrongly suppressed row is a market off the rail while a wrongly escalated one is merely loud. ⚠️ Reported against itself: the before/after capture shows three rungs one point less extreme stepping into the freed slots, identical at every cut from 0.44 down to 0.35 — the residual is that CONVICTION RANKING systematically selects a ladder's extreme rungs, and the two candidate remedies (a per-ladder cap; ranking a ladder by its PIVOT rung) are named, not taken (Alex, #195)
- [106](rulings/106-one-direction-and-the-number-is-ours.md) — 2026-08-20 — EVERY SCRIPT ROW QUOTES THE CHANCE IT HAPPENS, AND THE NUMBER IS OURS: "market says YES/NO" is dropped entirely and every pregame row prints one quantity — Stowers "5% chance", Schwarber "55% chance" — with the centred bar unchanged as ruled. Three faults in one four-word phrase, each invisible to a green suite because every ROW was individually correct: the number silently changed SUBJECT down the page (55% = chance of yes, the next row's 95% = chance of no); "NO" read as a VERDICT on a page where nothing has happened, borrowing the settled register from two elements down the same screen (#1650); and "market says" hands our one blended number to somebody else against the standing *blend is the product* doctrine. Guarded by the UX-P106 differential census on a NEW AXIS — flip the price across the coin flip and the token delta must be EMPTY — with the census helpers extracted to one shared implementation; it paid out twice against its own author on the day (a "market" attribution surviving in an sr-only header, and every number announced TWICE per row to a screen reader). General clause: **a number is not readable until its subject is fixed across every row that prints it** — per-row correctness is not what a reader consumes, and no test written one row at a time can see it (Alex, #195/#2011/#1650)
- [107](rulings/107-an-unlabelled-unit-invites-its-own-misread.md) — 2026-08-20 — AN UNLABELLED UNIT INVITES ITS OWN MISREAD: the grey "NN pts" is dropped from the settled prop card, which stays RANKED by surprise and is simply no longer annotated with it. #2011 put the ranking key at the row's right edge and reasoned correctly that an unsigned number avoids reading as a price move — but "not a price move" is not "legible", and the first person to read the page asked what 93 meant. Nothing is lost and that is the bar it had to pass: the row still says `marked 93% → MISS` and the sentence above it still says "was marked 93% — and it missed". Ruling 5 is *nothing beats unhelpful*, not *less is more*. Survives ONLY in the detail view's screen-reader line as "93 pts from the mark", where the referent is attached and the failure mode therefore absent. General clause: **a unit the reader has not been taught is not information, whatever it measures** — an order is explained by prose or by nothing, never by exposing its sort key (Alex, #195/#2011)
- [108](rulings/108-a-dry-run-gates-only-what-it-executes.md) — 2026-08-20 — A DRY RUN GATES ONLY WHAT IT EXECUTES: a dry run that never executes the write gates NOTHING about the write — not weakly, nothing — because a dry run is evidence about the paths it ran and the write is not one of them. Charter case is the 328-game CREATE wave (#1947), which fired four times across four windows behind four gates that were each genuinely met and honestly verified (merged ancestry proved against the deployed release SHA, plan_hash re-derived identical on the deployed tree, census `still_missing 328` / `gate.passes true`) and died four times one layer deeper in the same write: #2013's `AmbiguousParameterError` (`:truth_id` in two inferred-type positions, cast in neither), then #2023's live espn_id minting loop, then #2026's `DataError: expected a datetime … got 'str'` — nine consecutive sub-second `apply=true` calls, zero rows written. `CAST(:commence_time AS timestamptz)` sat in the statement throughout and could not help, because asyncpg type-checks the PYTHON argument before the statement reaches the server. Each failure was invisible to every upstream gate for the identical structural reason: the dry run is green BECAUSE it never executes the INSERT. So the finding is not the fourth bug — it is that the rail has no test that executes its INSERT against a real driver, and no fifth attempt fires on gate-green plus a parameter fix. Four obligations: a gate names what it EXECUTED; a write path is gated by executing it against the real driver on real infrastructure (#1884 shipped with 39 green unit tests and threw `asyncpg.DataError` on its first statement); a gate is proved RED before it is trusted, preferably via a negative control inside the test so the red-first proof cannot rot away from it; and a helper is not a call site — assert the value that reaches the driver. Same family as ruling 032 and `task_verdict`, one step earlier: "it was checked" is not "it was executed" (Fable, granting lane1 q379's age-5 escalation and going further)
- [109](rulings/109-a-ready-token-is-void-while-its-branch-contains-a-never-merge-ancestor.md) — 2026-08-20 — A READY TOKEN IS VOID WHILE ITS BRANCH CONTAINS A NEVER-MERGE ANCESTOR: naming a HEAD never-merge retires that head and nothing else, because ancestry travels — every branch containing it inherits the refusal whether or not anyone noticed, and its ready token is VOID (not deprioritised, not merge-later) until the branch is REBUILT without the ancestor. Charter case: INT-092 retired `codex-adhoc/prov-core` and `provenance-r5`, and the constraint ran through neither of them — it ran through `codex-adhoc/provenance` @ `02cd7ad8`, still advertising `ready_for_integration`, which four further live tokens contained (coldfeed, ingestion-audit, perf-r2, perf1974). All five merge-tree exit 1 on one conflict: `add_disc_interactions_provenance.py`, a migration production has ALREADY RUN (`alembic_version` = `add_disc_int_provenance`), so the revision can never re-run and the edit can never apply. **The fix is not a longer never-merge list** — a hand-maintained list is remembered, and remembering is what failed. The containment check is now COMPUTED in Phase 0 (`scripts/sweep_ready_tokens.py`), and it is a SET INTERSECTION, not an ancestry test: this cycle shipped the ancestry version first and it returned clean on all five, because the poison sits UPSTREAM of them; reversing it marks the whole repo void, since master is an ancestor of every never-merge head. Forbidden set = `rev-list origin/master..<nm head>`; VOID iff the candidate's own `rev-list` intersects it. Ruling 017 one level up — gates prove something about the commit you tested, and a token proves something about a diff, but the thing merged is a BRANCH, which is its whole history (Fable, INT-094 directive)
- [110](rulings/110-the-heavy-lane-gets-a-scoped-two-task-exception-with-its-falsifier-armed.md) — 2026-08-20 — THE `heavy` LANE GETS A SCOPED TWO-TASK EXCEPTION, WITH ITS FALSIFIER ARMED IN CODE: the standing "heavy is calibration-only" rule is relaxed for `backfill_market_shapes` and `precompute_backfill_progress` BY NAME — not a class, not a prefix — and the grant is conditional on a predicate that ships in the same commit (`app/utils/heavy_routing_falsifier.py`, `GET /api/admin/heavy-move/falsifier`), with the pre-move baseline pinned from production BEFORE the change and REVERT obliging the same window. Granted on a corrected number: LAT-P076's 26-sample slot census priced the two movers at 56% of one background slot, and duration x run-count measurement puts them at 18.9% observed — the census overstates ~3x. The asymmetry is why the falsifier is not ceremony: both movers run far below schedule (31 of 72 fires, 45 of 96) BECAUSE they are starved, so `heavy` can inherit up to 41.5% of a slot while `background` sheds 19%, pushing the protected lane from rho 0.59-0.81 to ~0.80-1.02. Two of the seven watched calibration beats are ALREADY censored at their 600s soft limit with zero successes in 24h and are excluded from the grade rather than counted as safety; INCONCLUSIVE is never HOLD. Trap recorded: #1800's identifier split produced THREE false NO-DATA reads in one window, and a falsifier built on them would have been blind on 3 of 7 subjects while reporting itself armed. General clause: a conditional grant ships with its condition executable, or it is an unconditional grant (Fable, LAT-P077 directive)
- [111](rulings/111-movement-first-with-a-per-ladder-cap.md) — 2026-08-20 — THE SCRIPT RAIL RANKS MOVEMENT FIRST, WITH A PER-LADDER CAP: rows with real pregame travel (`|now − opened|`) rank first as a strict TIER; conviction fills the remaining slots; at most ONE row per player-ladder family anywhere in the rail; ruling 105's structural filter stays underneath as an unconditional floor. AMENDS the 105-family RANKING, never the filter, and the argument is UX-P107's own sweep: from 0.44 down to 0.35 the Phillies rail kept the SAME SHAPE at every value, because the rung population is a continuum and conviction ranking selects a ladder's extreme rungs BY CONSTRUCTION — the defect's unit was the LADDER while every rule on the rail had the ROW as its subject, so no per-row threshold could ever reach it. Alex's card `15199886` went from three flat rows including a double-Turner ladder (7.0% / 7.0% / 8.0%, all 0.0 pt) to five distinct ladders every one of which moved (27.7 / 16.5 / 14.5 / 4.0 / 2.0 pt). `PROP_TRAVEL_FLOOR = 0.005` is EXTRACTED, not introduced — it is the line that already types `direction`, so the movement tier is exactly the set of rows whose own bar draws a journey, which is what keeps a screenshot able to check the ranking. THREE COSTS REPORTED, NOT DISCOVERED LATER: a two-point move outranks an unmoved 93% favourite; the P106 coherence overlap weakens 2 → 1 (structurally, since the settled key is maximised by the marks this ruling stops leading with); and the floor still removes five MOVED Brady Singer rungs on `14788546`, one of 34.0 pts — implemented as ruled and flagged back rather than re-litigated. Pregame only; live and settled rails verified byte-identical as controls (Alex, #195)
- [112](rulings/112-movement-overrides-the-structural-floor.md) — 2026-08-20 — MOVEMENT OVERRIDES THE STRUCTURAL FLOOR: a structural rung (ruling 105) whose travel clears the movement floor is RAIL-ELIGIBLE; the per-ladder cap still applies, so no ladder floods the rail. AMENDS 111, which amends 105 — the 105 predicate is untouched for the THIRD time; what changes is that the filter is no longer unconditional at the rail's selection step. Ruled on the residual UX-P108 flagged back rather than re-litigated, the second consecutive ruling made off a cost the implementing lane reported against its own work. THE FLOOR ASKS WHERE A RUNG SITS AND CANNOT SEE HOW IT GOT THERE: on `14788546` Brady Singer's whole strikeout ladder collapsed onto the 5% floor before first pitch — 5+ went 39.0% → 5.0%, a 34.0-pt move, the second largest on a 100-question card — so it is structural BECAUSE of where it landed, and it landed there by travelling. An arithmetic certainty that BROKE is the loudest thing the market said about that game. THE CAP IS WHAT MAKES IT AFFORDABLE AND IT ALREADY EXISTED: five Singer rungs are structural AND moved, so un-capped readmission puts three on a five-row rail — 111's own defect — while the cap admits ONE and the travel sort makes it the pivot; neither ruling is safe without the other, and that mutual dependency is asserted rather than left in prose. MEASURED: rail position 2, `structuralSuppressed` 8 → 3 (the three rungs that never moved are still removed, and the count now reports what the loop SKIPS rather than what carries the flag), one row in and one out. CONTROLS READ AT THE RENDERED LAYER (ruling 050): four payloads × three states, rail and expand, all `cmp`-identical including Alex's own `15199886` — whose three structural rungs are all flat, so it could have moved and did not — and including the Singer card's own expand, which is 111's stay-reachable clause. COST REPORTED: a moved structural rung now spends its ladder's one slot, so a ladder whose biggest mover is a collapsed rung cannot also show the rung the market has a live view about; zero on the specimen (Singer's 2+ is flat at conviction 0.040), covered synthetically, and preferring the pivot rung inside a ladder would be a further ruling (Alex, #195)
- [113](rulings/113-a-merge-offer-is-a-branch-with-a-green-gate-not-a-file.md) — 2026-08-20 — A MERGE OFFER IS A BRANCH WITH A GREEN GATE, NOT A FILE: Phase 0 sweeps READY tokens AND open PRs with passing CI, and reports either source being unavailable as NOT RUN rather than clean. Charter case is two consecutive Integrator cycles missing live merge-eligible work that Fable then had to name by hand — #2049 and #2050 were CI-green while `READY-lane1-382.md` read `branch: None` to the sweep (two branches under `## Branch N` headings, and `sweep_ready_tokens.py` parses only line-leading fields), and #2054/#2055 had no token at all, with #2055 gating Tranche A's 31 applies. Third token-shape defect in three cycles, after calibration-75's missing `status:` and rebaseline's `base:` naming a commit not in its own history — the pattern is not carelessness, it is that a token is a hand-written assertion about a branch while the branch is the thing that is true. This is ruling 109 one level up and the same move: "also check the PR list" is prose and will be forgotten, so the check is COMPUTED in the sweep's own output. The NOT-RUN half is load-bearing because the PR source is a network call — `gh` missing, unauthenticated or rate-limited all produce an empty list indistinguishable from "no PRs are open" (gotcha #53). Adds a source, removes nothing; ruling 034 still governs — confirm by CONTENT before merging, whichever source surfaced it (Fable, approving the Integrator's INT-100 proposal)
- [114](rulings/114-a-settled-cards-quiet-rows-stay.md) — 2026-08-21 — A SETTLED CARD'S QUIET ROWS STAY: NO TAIL, NO DROP. On a settled card, rows that never moved are neither folded into an "and N others" summary nor removed — they render as they are. A settled card is a RECORD, and a record with the boring parts removed is not a shorter record, it is a different one: a row that never moved is a fact about the question (nobody doubted this), so a tail converts that fact into a count and a drop asserts it never existed. Same shape as gotcha #53 and ruling 086 — the reader cannot tell a SUPPRESSED row from an ABSENT one, so a card that quietly hides its quiet rows looks exactly like a card whose data is incomplete, which is the failure the settled work existed to end. The cost being optimised away is visual tidiness on a card the reader has already chosen to open: no latency claim, no correctness claim, and it does not outrank the record. SCOPED to the settled card — live and pregame surfaces keep ranking and capping, because the settled card has stopped being a ranking and started being a result. Ruled as a STANDING instruction so the boundary case stops re-litigating itself each cycle (Alex, #2060)
- [115](rulings/115-a-missing-status-is-malformed-not-not-ready.md) — 2026-08-21 — A MISSING `status:` IS MALFORMED, NOT NOT-READY: the READY sweep fails LOUD on a token that states no status — `is_ready(None)` RAISES rather than answering `False`, MALFORMED is a report line, and the header states coverage as a ratio so a half-blind sweep can never again print a confident list of only what it could see. A token with no `status:` has not said "no", it has said nothing, and folding absence into a negative renders silence in the same bytes as a decision. Charter case is the cycle that banked it, measured: INT-103's Phase 0 read 178 tokens and returned 3 LIVE-READY against SIX real merge offers — `program/ux-99` (three commits including the only consumer of ux-98's `graded_card` rename), PR #2062 and PR #2063 were all invisible to the token half, and ux-99 was invisible to ruling 113's PR source too because it has no PR, so the only thing that surfaced the ordering constraint the whole directive was built on was Fable naming it by hand. Fifth instance in five cycles and the fourth in which somebody wrote it down — INT-102 put the fix request in its own queue file ("#2062 needs a `status:` field before the sweep can see it") and one cycle later the field was still absent, which is why the remedy is not another instruction to lanes: the READER is the only party present at every sweep. Inferring ready from the filename stays refused (it would revive all 178 historical tokens); absence is REPORTED, not guessed. Malformed tokens are still resolved against git and carry the verdict they WOULD have had, so bookkeeping stays distinguishable from a lane's work with nobody looking, and only the latter reds `--strict`. Rulings 109 and 113's move applied a third time to the same instrument — prose is forgotten, a section of the sweep's own output is run. General clause to doctrine: **absence is a value, and a parser that folds it into a negative has answered a question it was never asked** — gotcha #53 one level in, where a missing field and a field saying no reach the reader as the same byte (Fable, INT-103 directive; the Integrator's proposal adopted verbatim)
- [116](rulings/116-gotcha-numbers-claim-through-the-ledger.md) — 2026-08-21 — GOTCHA NUMBERS CLAIM THROUGH `RULING-CLAIMS.md`, AND COLLISIONS RENUMBER AT MERGE BY COUNTING THE MERGED TREE: the 2026-08-12 scope clause already covered gotchas and had not been used for one since 2026-08-18, so on 2026-08-21 three lanes reached INT-105 holding FOUR new gotchas competing for TWO numbers — #2070 claimed 145, latency-72 claimed 146, and ux-101 claimed both. Each measured master correctly (max 144) and each was right about master; none could see the other two. LAT-P079 swept 538 local and remote refs and reported `holders_found = 0` for 146 while `program/ux-101` held it, which is the whole argument: **a ref sweep measures what has been pushed, a ledger records what has been decided**, and on a day with three concurrent writers only the second question matters. Resolution is mechanical and preserves every entry: earlier ledger claim keeps its number (absent a claim, merge order decides), the later claimant renumbers ITS OWN entries into the next free numbers COUNTED IN THE MERGED TREE, never into a historical gap (ruling 088), and the order is chosen to minimise cross-reference breakage — here ux-101 had zero self-references so it moved to 147/148 and nothing else in the tree changed. General clause: **a number is not free because your measurement says so, it is free because nobody has claimed it** — measurement answers a question about the past, concurrency is a question about the present. Ruling 088's *count, never author* applied to the tree itself. The real fix is the ruling-001 treatment (one file per gotcha) and it is still not staged (Fable, banked by the Integrator INT-105)
- [117](rulings/117-the-clock-task-cutover-is-measure-then-decide.md) — 2026-08-21 — THE CLOCK-TASK CUTOVER IS MEASURE-THEN-DECIDE: no coverage change to a live producer during a freeze, and the decision comes back carrying the number its own gate produced. Ratifies CAL-P086A's deferral of codex's [P0] "stop the generic clock task resolving prediction-market sources" — legitimate ONLY because the deferring change shipped the counter that ends it (48 h of `resolution_gate` stamps grouped by producer, clock starting at DEPLOY, addressee Fable). General clause, routed to doctrine: a deferral is legitimate when it ships the instrument that ends it; one that leaves the size as unknowable as it found it is a decision not to do the work, recorded in the vocabulary of doing it later (Fable, extends 066)
- [118](rulings/118-the-status-field-is-a-closed-vocabulary.md) — 2026-08-22 — THE `status:` FIELD IS A CLOSED VOCABULARY: a READY token's status may only take a value from a published set — anything else is `UNKNOWN-STATUS`, reported by name with the offending value QUOTED, and `--strict` reds on all of it; human prose moves to a `note:` field the sweep parses and prints. Ruling 115 closed the case where a token says nothing; this closes the case it left open, where a token says something no reader understands, and they are the same defect through the same line of code — `status in READY_VALUES` answered `False` for every unrecognised value, so the token was dropped at the identical `continue` that discards honestly-merged work: not deprioritised, unseen. Measured the day it was banked: 14 of 194 tokens wore 11 distinct hand-written statuses, and the enforcement's FIRST RUN found two sitting over unmerged work that no prior sweep could see — `READY-lane1-q353-process.md` (`BLOCKED_RENUMBER`, actually LIVE-READY) and `READY-calibration-38.md` (a ⛔ sentence, actually MOVED-HEAD). The specimen that settles the design is `merged + DDL HALF NOW DISCHARGED — INT-075…`: it STARTS with a vocabulary word and is not equal to one, so a literal-bytes grep for `status: merged` skips it — which is why the reader must REFUSE the value rather than normalise it to its first word, since repairing it in the reader fixes the report while leaving the prose in the machine field, and the prose in the machine field IS the defect. `excused` enters the vocabulary as its second half: `READY-calibration-52.md` omitted `status:` deliberately and documented it, and the lane was not sloppy — there was no word for what it meant, so the vocabulary supplies one, with a one-entry by-name allowlist as a bridge that prints its own reason and should shrink to empty. `--strict` reds on ALL unknown statuses but only on malformed ones over live work, deliberately: a missing status can be an ancient merged token, so gating all 12 would make the gate permanently red and therefore ignored, while an unknown status was TYPED by someone and is fixed by one word plus a `note:` line. 9 new tests, ALL NINE red-first against the pre-change script (the 4 passing under the same filter are pre-existing ruling-115 cases this leaves alone). General clause to doctrine: **a closed vocabulary is what makes a field readable by anything other than its author** — an open string field in a machine-read record does not fail when someone writes prose into it, it succeeds silently into a reader that has no branch for the value, and the fix is never 'tell people the convention', because conventions are advisory to the writer and invisible to the reader (Fable, INT-109 directive pasted and reviewed by Alex; banked and enforced by the Integrator)
- [119](rulings/119-a-falsifier-whose-control-fires-grounds-nothing.md) — 2026-08-22 — THE ROUTING IS HELD: A FALSIFIER WHOSE CONTROL FIRES GROUNDS NOTHING. Ruling 110's falsifier read REVERT at the 2026-08-21 18:09 PDT horizon read, and 110's grant obliges a revert in the SAME window that reads one. That obligation is DISCHARGED WITHOUT REVERTING, because the read is UNATTRIBUTABLE, on three grounds. (1) THE CONTROL FIRES: the pre-move half of the same 50-deep ring reads p50 391.2s against the pinned 214.7s = 1.82x, over the very same 1.25x DEGRADE_P50_RATIO that produced the REVERT — a shift visible in samples that PREDATE the move cannot have been caused by it, and LAT-P079 credited #1866's gain only because its own control did not move, so waiving that standard for an unfavourable read would be choosing rather than measuring. (2) A p50 ON A BIMODAL DISTRIBUTION IS A MODE-SELECTOR, NOT A LOCATION: 21 samples in 78-205s, one at 391.2s, 28 in 924-1404s, essentially nothing between, so the median reports which mode holds the majority and jumps discontinuously as the mix crosses 50% — 8 of 9 post-move samples in the slow mode is a MIX, not a slowdown, and a 1.25x threshold has no resolution here. (3) COVERAGE WAS ONE BEAT OF SEVEN, MISCOUNTED AS THREE: the grader excluded only (pre_horizon, censored), so two beats with ZERO runs in 24h were counted as coverage — `no_new_runs` is not coverage, it is the purest form of learning nothing (gotcha #53), and the grader committed the very defect it was written to avoid. WHAT THIS DOES NOT DO: it voids ONE reading, does not certify the routing, does not grade P4/P5 (both PRE_HORIZON until the 24h counters clear the move at 09:08 PDT 2026-08-22), and leaves 110's falsifier armed and its grant conditional. The defect exposed is MIN_POST_MOVE_SAMPLES = 8, which is DISPERSION-BLIND — a sample-count judgement made without reference to any beat's dispersion, the same class as #2071 one level up: grading on a statistic the distribution does not support. Separately real and NOT the routing's: precompute_calibration_main is failing 3 runs in 5, visible in the PRE-move arm too, filed as #2102. General clause OFFERED not claimed: a falsifier whose control fires grounds nothing — a treatment and a control that move together are one unexplained shift, not one attributable effect, and the correct output is VOID rather than a verdict in either direction (Fable directive 2026-08-22, reviewed by Alex)
- [120](rulings/120-a-derived-write-carries-the-key-that-reverses-it.md) — 2026-08-22 — A DERIVED WRITE CARRIES THE KEY THAT REVERSES IT: the backfill provenance key is BLESSED — `polymarket_event_id_source = 'group_id_backfill_q390'` stays ON for the 489k-row `polymarket_event_id` apply. It buys two things: the write becomes **exactly reversible** (the undo is a predicate over the source key, not a reconstruction of which rows a statement touched), and it **permanently distinguishes a DERIVED id from one CAPTURED AT MINT**. The deviation from "the audit's exact UPDATE" (one key where this writes two) was correctly flagged rather than buried, and is dispositioned as an improvement in the direction provenance doctrine already points — gotcha #32's CREATE arm already tags the row it creates, ruling 048 already turns on telling an id-anchored claim from an id-less one. **The gate does not move: the apply stays gated AFTER the mint fix deploys; this records the bless, it does not fire it.** General clause: **a bulk write that cannot be identified afterwards is a bulk write that cannot be undone** — and the sharper half, **derived data and captured data that look identical will be read identically**, which is gotcha #53's two-states-report-identically moved from a response body to a table; the merge always resolves toward the more confident reading. Scoped: reversibility is a property of the statement (additive `||`, guarded by `NOT (market_metadata ? 'polymarket_event_id')`) and the key only makes it addressable (Fable, pasted and reviewed by Alex, queue 391)
- [121](rulings/121-the-shared-tree-stays-on-master.md) — 2026-08-14 — `~/bainluck` stays on master, always: branch work lives ONLY in per-queue worktrees and master-writes ONLY in the Integrator's dedicated detached tree; `-C` pins the directory, never the branch (Alex)
- [122](rulings/122-four-rounds-in-one-design-is-a-design-question.md) — 2026-08-23 — FOUR ROUNDS INSIDE ONE DESIGN IS A DESIGN QUESTION, NOT A MERGE CADENCE: Tranche A's 60,889-row prune is PARKED after the fourth consecutive certification BLOCK (R1-R4), and no round 5 runs until a premise-first design one-pager — lane4, NO CODE — survives review. The two attended applies stay HELD indefinitely: track the age so the item cannot go quiet, and STOP escalating it. The signal is not the count of rounds, it is the SHAPE of their failures: the allowlist DELETED rows it should have kept (R3's distinct-game candidate whose only observation was `opening_home_spread=-1.5`) and the deny-by-default rebuild that answered it KEEPS EVERY ROW INCLUDING THE ONES IT EXISTS TO DELETE (R4: `event_tags` is parent-substance while every candidate must carry `provenance:unanchored`, so the population is mathematically empty, `deletable=0`, all 31 batches a permanent `no_work`). Two corrections failing in OPPOSITE directions bound the truth between them and locate it in neither — the design is under-specified, not insufficiently narrowed, and window 389 had already predicted the first half in writing. Both were green, and part of that green was over SQL PostgreSQL cannot execute (`varchar = integer` on the new pseudo-FK guards, 111 tests passing because the fakes assert table names appear in a string and never ask a database to type-check it — gotcha #122), so further rounds inside the same harness cannot distinguish weak assurance from none. R3's self-oracular defect recurred in R4: the schema-minus-denylist oracle subtracts the production denylist, so a denylist entry cannot be adjudicated by the test that reads it. What is parked is the RAIL, never the census (2,565 / 60,889 stands, and must be re-derived at fire time, not carried). Corollary on the age: an escalation against a question nobody is answering is noise — the 383 row escalated at 5, was answered with a rebuild, blocked, escalated at 6, and a third would report urgency to a lane that has already done the only thing urgency asks for. R4's quoted 1,230 withheld / 59,659 deletable price is RETIRED, not stale — the tables v4 added had no FK to `events.id` at all (Fable directive 2026-08-23, pasted and reviewed by Alex)
- [123](rulings/123-a-baseline-describes-the-regime-we-run-in.md) — 2026-08-23 — A BASELINE DESCRIBES THE REGIME WE RUN IN: ruling 110's straddling baseline is RE-PINNED, entirely from post-v3874 samples, and every one of the seven now DECLARES which regime it pins in a field the endpoint prints and a test enforces. `precompute_calibration_main` was pinned at p50 214.7s / p95 1302.1s / max 1357.2s — three numbers that cannot describe one population. #2102 dated the boundary exactly: v3874 (`724fd22c`, 2026-08-20 10:45:57 PDT) carried CAL-P078's rolling re-stage, `units_this_beat` went 0 -> every-unit, and the beat stepped 7.74x (regime A p50 163.2s n=7, regime B p50 1263.3s n=43, confirmed to the millisecond in the phase ledger: 8 units x 141,283ms = 86% of the run). So 3-24 of the 50 samples behind the pin were ALREADY SLOW when it was taken — a mixture statistic across a regime boundary, reading 6.05x against a perfectly healthy beat and holding the panel at REVERT. A FALSIFIER STUCK ON REVERT IS EXACTLY AS UNWATCHED AS ONE STUCK ON HOLD, which is why this is a ruling and not a constant edit — LAT-P079 already withdrew a staged fix whose condition was never false, and this is that failure with the sign flipped. RE-PINNED to p50 1187.8s / p95 1396.4s / max 1397.8s, n=22, from LAT-P081's byte-pinned ring artefact restricted to samples BOTH post-v3874 AND pre-routing-change. The double restriction is the design: post-v3874 is the regime we run in, pre-move is what keeps a falsifier a falsifier, and today's ring cannot supply it — it has rolled fully over (48 of 50 post-move), so regime B n pre-move now yields n=2. The window was 22.4h wide, has passed, and survives in exactly one committed artefact, which is the argument for committing artefacts. SIX PIN A SINGLE REGIME, each cross-checked by splitting its live ring at v3874 — and one of the six (`precompute_backfill_winners_status`) can only say so by the ABSENCE of a step, its pre-arm having rolled away, recorded as such because 'I checked and it did not move' and 'I could not check' are different claims (gotcha #53). WHAT IT DOES NOT DO: it does not certify the routing. With the artefact removed the panel STILL READS REVERT, on a different beat — `precompute_source_intelligence` at 1.53x — and ruling 119's control test was applied before this was written and does NOT fire (pre-move arm 17.5s against the pinned 17.5s = 1.00x), so unlike the reading 119 voided this one is attributable on 119's own standard. ESCALATED, NOT EXECUTED, with the counter-argument stated so it can be refused: every post-move sample lies inside the pre-move envelope, the p95 FELL (32.6s -> 31.0s), n=8, and DEGRADE_P50_RATIO is a pure ratio with no absolute floor — it fires at +4.4s on this beat and would need +297s on the beat a user-facing page waits on, 67x more sensitive to the beat that matters least. SEPARATELY, P4 IS NOW READABLE AND CONFIRMS RULING 110's CENTRAL PREDICTION: both movers run at ~100% of schedule (73.8/day vs 72, and 96.5/day vs 96, rate-corrected against each counter's own 9.1h and 10.2h window) against 31/72 and 45/96 before the move — 'starved rather than idle' CONFIRMED, while the old instrument graded both `flat_or_fell`, i.e. FAILED, for sitting at schedule (#2110) (Fable directive 2026-08-23, pasted and reviewed by Alex)
- [124](rulings/124-a-threshold-trippable-by-one-observation-is-not-a-threshold.md) — 2026-08-23 — A THRESHOLD THAT CAN BE TRIPPED BY A SINGLE OBSERVATION IS NOT A THRESHOLD: Gate 5's `published_only_in_scope` gets a MIN-N FLOOR — a cell with `n <= 2` is REPORTED in the gate output and can never ALONE force `disagrees`. CAL-P086B was right to make an in-scope published cell with no twin row force `disagrees` (before it, `agrees` was reachable over 28.8% of the curve and a fold that produced NOTHING read as agreement — Gate 5 was meetable by a timeout). But it also made the verdict answer to the KEY SET rather than to tolerance, and the rule is not tolerance-scaled: one thin bucket forces `disagrees` at any bound, including the 100 pp bound the bank's own 128/128 drift pins, so there is no setting of the instrument at which a two-row bucket stops deciding the gate. General clause: wherever a gate's subject is a SET rather than a magnitude it must state a minimum cell occupancy, because the tail of any partitioned population is populated by ones and twos — a property of partitioning, not of correctness — so such a rule can never go green for reasons unrelated to what it grades. SAFE ONLY BECAUSE THE DISCOUNTED SET IS A MINORITY, and that is measured, not assumed: 159 of 608 in-scope keys are thin, so **449 survive and Gate 0 still reads RED** — `agrees`-by-timeout stays dead, pinned by a test that reads CAL-P087's frozen artifact rather than restating it. Two obligations travel with it: the floor is REPORTED never silent (`published_only_in_scope_below_floor`, and the union keeps every row — gotcha #53 on the instrument's own output), and an UNDISCLOSED `n` is NOT a thin cell and is never discounted, the same asymmetry `tolerance_pp` already uses one level up. That second clause was not in the directive — an existing CAL-P078 fixture publishing a bucket with no `n` caught the first implementation treating undisclosed as zero, which is the argument for banking a floor WITH its implementation rather than ahead of it (Fable, directive pasted and reviewed by Alex; amends CAL-P086B's split)
- [125](rulings/125-a-row-deleting-join-must-carry-every-dimension-that-identifies-the-row.md) — 2026-08-23 — A JOIN THAT CAN DELETE A ROW MUST CARRY EVERY DIMENSION THAT IDENTIFIES IT: #2098's unchunked behaviour is WRONG. `_calibration_population_ctes()` builds `vm_id` with no source (`'e:' || event_id`), while `mode_prices` groups on `vm_id` alone and `deduped` joins on `mp.vm_id = ro.vm_id` — so a mode price computed from one venue's legs suppresses another venue's legs for the same event. Every neighbouring aggregate (`group_sizes`, `event_sizes`, `virtual_market`, `vm_stats`) is source-scoped deliberately; these two are the exceptions, and the exception is the defect. IT FIRES, and CAL-P087 measured it rather than resolving it in the reassuring direction: **35 rows on 2 vm_ids**, whole `event_id` domain, 0 unswept ranges, 559 chunks, 1,788 s. Charter specimen `e:14887630` — a four-leg Polymarket market DELETES 23 Kalshi legs at p = 0.01, because polymarket's `eligible 4` clears the `GREATEST(eligible*0.5, 2)` floor while kalshi's `eligible 120` needs 60 and has 23, and the join carries no source. The measurement CORRECTS the issue's own upper bound 1,271 → 35 (the `g:` arm wins before the `e:` arm), which is the second clause: an unmeasured upper bound is not a finding, and measuring it moved the number by a factor of 36 — downward. General clause: wherever a join's key is COARSER than the identity of the rows it can eliminate, the join silently picks a winner across a dimension nobody declared — and a row-DELETING join is the one place a missing dimension cannot be absorbed downstream, because the evidence of the mistake is the thing that was removed (gotcha #53 at the level of a SQL predicate). Corollary: an id assembled from a source-scoped table's columns is not source-scoped merely because its inputs were. THE FIX IS NOT A DRIVE-BY — `AND mp.source = ro.source` touches the FROZEN builder under ruling 009 and needs its own exception, its own re-baseline declaration, a stated curve movement (it ADDS rows back, so ruling 103 / doctrine 18 govern in reverse) and its own cert, sequenced AFTER the apply blockers. Banked AHEAD of the fix by design, so the judgment is settled before the certification starts (Fable, directive pasted and reviewed by Alex; consumes the ruling CAL-P087 deliberately declined to make)
- [126](rulings/126-a-ratio-with-no-floor-is-sharpest-where-it-matters-least.md) — 2026-08-23 — A RATIO WITH NO ABSOLUTE FLOOR IS SHARPEST WHERE IT MATTERS LEAST, so #2116 is decided DO NOT REVERT and `DEGRADE_P50_RATIO` gains a materiality floor in absolute seconds, scaled by what CONSUMES the beat. Ruling 110's grant, its four-step revert and its falsifier all stand; only the definition of "degrades measurably" moves. The defect: a pure multiple makes required absolute effect scale with the subject's own baseline, so the SMALLEST subject is the MOST sensitive and the ranking of sensitivities is the exact reverse of the ranking of consequence — measured here at +4.4s to fire REVERT on `precompute_source_intelligence` (17.5s) against +297s on `precompute_calibration_main` (1187.8s), the one beat a user-facing page waits on: 67x backwards. THE CLAUSE THIS BANKS IS THAT ATTRIBUTION IS NOT SUFFICIENCY. Ruling 119's control test was applied first and did NOT fire — the pre-move arm read 1.00x, as clean as a control gets — so the reading was real; it was just SMALL, and the old predicate had no way to say so. An instrument that only asks "is this real?" acts on every real effect, and every sufficiently sensitive instrument finds real effects. The floor's scaling is a MEASURED consumer classification, not a taste dial, in ruling 123's shape (a field the endpoint prints and a test enforces): `user_page` 30s — `precompute_calibration_main` ONLY, `frontend/lib/api.ts:2118` from the public /calibration page; `operator_panel` 60s — source_intelligence, fair_fight, backfill_winners_status, all rendered only under /admin; `no_reader` 120s — time_horizon (public route, ZERO frontend callers), coverage_metrics, calibration_prices. THREE GUARDS, because a floor is a way to make a gate quieter and this program has twice come close to minting a gate that cannot go red: a ratio trip under the floor grades `immaterial`, a NAMED state that is printed, counted and carried into the panel's top-level reason and never folded into `hold` (the one thing a floor must not buy is silence); the floor gates the RATIO only, leaving #2071's observation-side censor untouched; and the floor is CAPPED at the point the censor takes over so it can never by itself make a beat ungradeable (it binds on exactly one beat — coverage_metrics, 120s declared, 107.9s applied — and says so). RE-GRADE, against live production task-metrics through the offline mirror: REVERT -> HOLD, with `precompute_source_intelligence` at 1.347x but +6.1s against a 60s floor. THE RESIDUAL IS STATED RATHER THAN CLAIMED FIXED: the floor is a MINIMUM, so the ratio still governs slow beats and the spread narrows from 67x to ~5x without INVERTING — survivable only because `precompute_calibration_main`'s ratio trip (1484.8s) sits ABOVE its own censor point (1470s), so the user-facing beat is watched by the censor and always was. Inverting it needs a per-consumer CEILING, which TIGHTENS revert and is therefore a decision about ruling 110's grant that a lane must not make inside the window that produced the reading a floor suppresses (Fable directive 2026-08-23, LAT-P083 item 1, pasted and reviewed by Alex)
- [127](rulings/127-the-latency-program-reports-two-user-facing-numbers.md) — 2026-08-23 — PROGRAM CHARTER AMENDMENT: THE LATENCY PROGRAM REPORTS TWO USER-FACING NUMBERS, AND INSTRUMENT WORK MUST NAME THE DECISION IT UNBLOCKS. Named failure: dozens of cycles, `MEASURED_WALL_MAX_S` never lowered, and three cycles spent proving another program's 7.74x step wasn't ours. General clause: a performance program is graded on what users feel, not on what its instruments can prove — instruments are how a claim survives an adversary, not the deliverable, and a lane that can only report on the health of its own measuring equipment has become an instrumentation program, a transition invisible from inside because instrument work is always correct, always necessary-looking, and always produces a green result to report. NOT_REFUTED is not a win; only the deltas are. (1) HEADLINE METRIC — every report OPENS with feed p50 and typeahead p50 and their deltas since the previous cycle, and a cycle that does not move them says why in ONE line. The measurement is defined once, here, and pinned to a named instrument and a named input; changing either resets the series and must publish both numbers for one overlapping cycle, because a delta between two measurements is a delta of instruments. `feed p50` is ORGANIC — `/api/admin/latency-stats`, where /api/feed is `always_sampled` so it is a census not a sample — reported ALWAYS with `n`, `newest_sample_age_s`, and the `by_cache_status` split, because /api/feed is bimodal with nothing in between (measured hit 12.8ms / stale_hit 15.3ms / miss 5,497.6ms) so a p50 over mixed cache states is a statement about the HIT RATE and will move three orders of magnitude on a change no user waits on. `typeahead p50` is a PROBE, because organic volume cannot carry it — /typeahead had NO samples in the window at all this cycle at a 1/10 sample rate — reported as p50 AND cold-share together, since a warm p50 is ~13ms and will not move whatever happens. The probe set is FROZEN in `docs/audits/latency/headline-probe-terms.txt`, and EVERY TERM MUST ALREADY BE IN THE REAL SEARCH HEAD: /typeahead writes to the trending counter the warmer heads from, so probing a term is a VOTE for it, and LAT-P082's two synthetic probe strings became 2 of the warmer's 40 slots in an otherwise-empty zset. General form: an instrument that writes to the system it reads must be composed of inputs the system already contains. (2) INSTRUMENT TEST — instrument work is permitted only when it unblocks a NAMED decision and the report names it; a fix that unblocks nothing is deferred however correct it is. The test is "without this, X cannot be decided" for an X someone is waiting on, and it is NOT satisfied by "the number would be wrong" — a number nobody is about to act on can be wrong indefinitely at no cost. (3) LATENCY BUDGET FLAG — a `beat_cost` declaration on the `migration_slot` / `beat_schedule_change` pattern: any change from ANY program that raises a measured beat cost past the declared threshold must declare it in its PR and READY token and the Integrator refuses the merge without it, with threshold, measurement and enforceable spec owned by this lane and written into `docs/doctrine.md` so enforcement needs no judgement. First client is calibration's re-stage class: CAL-P078 moved `precompute_calibration_main` 163s -> 1,263s (7.74x) undeclared, costing three latency cycles and one falsifier baseline that read ~6x against a healthy beat. The flag does not forbid the change — that re-stage was correct and would have been approved — it makes a regime change arrive ANNOUNCED. Spec ships this cycle or next; enforcement begins the cycle AFTER it is in doctrine, because a gate that refuses merges before its threshold is published refuses them for a reason nobody can read. The falsifier panel, the #2107 watch and the materiality floors all STAY — they are what makes item 1 honest (Fable, PROGRAM CHARTER AMENDMENT 2026-08-23, Alex ruled; pasted and reviewed by Alex)
- [128](rulings/128-a-gate-is-bounded-in-both-directions-or-in-neither.md) — 2026-08-24 — A GATE IS BOUNDED IN BOTH DIRECTIONS OR IN NEITHER: the per-consumer CEILING is APPROVED as instrument work, and it passes ruling 127's instrument test by naming the decision it unblocks — "when does a user-facing regression revert". Ruling 126 measured the gap and refused to close it inside its own window: the materiality floor fixed the SIGN of the sensitivity inversion (67.9x -> 4.95x) and could not fix the DIRECTION, because a floor is a MINIMUM and the ratio still governs above it, leaving `precompute_calibration_main` — the one beat a public page waits on — needing +297.0s to trip revert while `precompute_source_intelligence`, which no user waits on, tripped at +6.1s. THE GENERAL CLAUSE: a gate bounded in one direction is not a looser version of a gate bounded in both — it is a gate whose sensitivity ranking is set by something other than consequence, and the two bounds must come from ONE measured classification, because two independently-authored tables drift and the first symptom of drift is a band with a hole in it. Built as `CONSUMER_CEILING_S`, keyed identically to 126's `CONSUMER_FLOOR_S` with a test asserting the key sets are EQUAL, and the bands TILE — user_page [30,60], operator_panel [60,120], no_reader [120,240], each class's ceiling IS the next looser class's floor, so no absolute delta falls between two bands and the only thing deciding how many seconds of regression a beat is allowed is which class consumes it. Applied trip is `min(max(p50 x ratio, p50 + floor), p50 + ceiling)`. FOUR GUARDS, mirror images of 126's three, because a ceiling is a way to make a gate LOUDER and this program has now come close to minting a gate that cannot go red AND one that cannot go green: the ceiling is capped by #2071's censor exactly as the floor is and says so when it binds; the applied ceiling can never fall below the applied floor over any production pin; `ceiling_exceeded` reads a SIGNED delta and never `abs()` — an improvement of -400s grades `hold` and a test pins it, since `abs()` is the classic way a tightened gate starts reverting on improvements; and the ceiling arm is a NAMED verdict carrying `ratio_exceeded=False` so a ceiling revert can never be read in the panel as a ratio revert. MEASURED over the seven live pins: spread 67.9x -> 4.95x -> 2.00x, and `user_page` moves from WORST (+297.0s) to JOINT-BEST (+60.0s) — the inversion 126 could not perform, performed, by declaring a bound in seconds rather than tuning a multiple. Red-first gate `test_falsifier_consumer_ceiling.py` (13 tests) recorded honestly at exit 2 first — a collection error, not a failing test, per gotcha #54's amendment — then green; 96 pass across all four falsifier suites. It does NOT re-open ruling 110's grant, does NOT touch the observation-side censor, and does not by itself revert anything: the re-graded panel still reads HOLD, the correct state for an instrument whose job is to be ABLE to go red for the right reason (Fable directive 2026-08-24, LAT-P084 item 2, pasted and reviewed by Alex)
- [129](rulings/129-coalescing-moves-cost-between-buckets-without-removing-it.md) — 2026-08-24 — COALESCING MOVES COST BETWEEN BUCKETS WITHOUT REMOVING IT: a request that waits out another request's build has NOT been served from cache, so any metric reading the MISS bucket to estimate what users wait for undercounts by exactly the coalesced population — and undercounts MOST when concurrency is highest, i.e. worst exactly when it matters. General form: an optimisation that redistributes a cost across bookkeeping categories will be recorded as an improvement by any instrument keyed on one category; ask what LEFT the bucket, not what is in it. Found re-measuring Fable's charge decontaminated on the post-T0 slug (v3886, window 17:25:24Z-18:17:53Z, complete, no release straddle, six lane probes subtracted per ruling 127): a fifth cache-status bucket `other` had appeared, n=11 of 42 at p50 2,897.6ms with a 2,093.3ms FLOOR. Identified without guessing — the middleware buckets to `other` exactly when X-Feed-Cache is outside {miss,hit,stale_hit,error}, feed.py sets seven such values, and the distribution excludes six: `last_good`/`unavailable` are only reachable AFTER the wait budget is exhausted so neither can floor at 2.09s, the three `disabled*` variants need a debug/filter param or the cache off while hits are being served, leaving `coalesced`, which returns the instant the leader finishes and is therefore bounded above by the leader's build (p50 5,046.8ms) and floored by the waiter's arrival. Then CONFIRMED rather than inferred: three concurrent anonymous GET /api/feed at 18:17:37Z returned miss/leader 6.560s, miss/leader 6.618s, and coalesced/coalesced 6.632s — the coalesced waiter was the SLOWEST of the three while sitting in the fast-sounding bucket. THE CORRECTED HEADLINE: build-paying share = (6 miss + 11 coalesced)/42 = 40.5% (Wilson 95% CI 27.0-55.5%), against a MISS share of only 14.3%. Fable's '37.5% at 4,121ms, better than a third of feed requests eat four seconds' is right in its conclusion and wrong in its arithmetic, and the two errors cancelled. Second finding free with the first, and the obvious explanation was the WRONG one: TWO leaders for one anon key, but `heroku ps` shows exactly ONE web dyno — the cause is `WEB_CONCURRENCY: 2`, which uvicorn honours as its worker count, so the single dyno runs TWO worker processes each with its own event loop and its own process-global `_inflight` (begin_build has no await between its get and its set, so two same-key leaders in one loop are impossible; the probes simply landed on different workers). THE PROCESS COUNT IS `dynos x WEB_CONCURRENCY`, NOT `dynos` — any capacity or process-global argument reasoning from `heroku ps` alone is wrong by the concurrency factor, and `heroku ps` is the instrument everyone reaches for. This DISCOUNTS #2143's projection: its shared store is process-global too, so each artifact is built twice per TTL window, once per worker — a warm request saves what is projected, but the COLD-BUILD RATE is 2x a one-process model. This is gotcha #53's shape one level up (an empty 200 is a response shape, not an absence; a bucket label is a code path, not a cost class) and it is why ruling 127 requires the feed headline to carry its by_cache_status split — a bare p50 of 36.9ms hides it completely, and so does a miss share. Consequences: #2143's addressable population grows 2.8x, since the lever shortens the LEADER's build and a waiter's wait is bounded by that same build; and no future latency report may quote a miss share as a wait share — quote miss+coalesced, and identify any new non-standard X-Feed-Cache value BEFORE reporting a number over it, because `other` is an unread measurement, never a residual. It does NOT say coalescing is wrong — without it 12 concurrent cold requests would be 12 builds; the metric is wrong, not the mechanism — and it does not close #2143 or grade any fix, since this lane cannot deploy and n=42 leaves the CI wide (LAT-P084 item 1, Fable directive 2026-08-24, pasted and reviewed by Alex)
- [130](rulings/130-a-window-that-straddles-a-release-is-inconclusive.md) — 2026-08-24 — A WINDOW THAT STRADDLES A RELEASE IS INCONCLUSIVE, NOT A RESULT: a measurement window containing a deploy measures two different systems and reports one number, so it gets a THIRD verdict alongside pass and fail and never counts toward a streak in either direction. Not "fail" — a failure inside it is unattributable and may belong to the retired slug. Not "pass" — a clean straddling window is a clean reading of a system that no longer exists for part of its duration, which is what `post_deploy_latency_not_evidence` was written about. General form: a streak counts consecutive observations of ONE system, so a window spanning a change of system is not an observation of either — it is not a link in the chain and it does not break the chain. Generalises the LAT-P085 dated-streak fix from arm B (where it was written as a property of the daily banking loop) to BOTH arms of the #2107 watch, because it is a property of any interval compared against a target and arm A has the same exposure with none of the same code. Two silent failure directions, both real: FALSE BREAK — a release ships a fix, the straddling window still holds pre-fix errors, the counter resets to zero, and seven days becomes eight then nine indefinitely as long as the deploy cadence beats the streak length, which it does; and FALSE BANK — a release ships a REGRESSION late in a window clean until then, the rate stays under threshold on the strength of the pre-release majority, and the streak certifies a slug that was live for forty minutes of it. Direction 2 is the worse one and is exactly what a "be conservative, count it as a failure" shortcut does NOT fix, which is why INCONCLUSIVE is a third value and not a re-labelling of one of the two. Binds: both arms emit it and both exclude it from the seven; an INCONCLUSIVE window is LOGGED not dropped, because a run that silently discards windows and a run with nothing to report look identical (gotcha #53) and a streak stuck at 3/7 because every window straddles a deploy must say so out loud; and the verdict is decided by the release boundary, not by a heuristic about whether the release "could have" affected the metric. It does NOT extend, retry, or interpolate across the boundary — the window is discarded and the next starts after the release, and a streak that takes longer to certify because deploys keep landing is reporting a true fact about the deploy cadence, whose fix is a deploy-free date (hence #2107's day-1 re-run being scheduled rather than forced), not a softer verdict (LAT-P086 item 0a, Fable directive 2026-08-24, pasted and reviewed by Alex)
- [131](rulings/131-index-ddl-with-no-code-half-runs-attended-outside-alembic.md) — 2026-08-24 — INDEX DDL WITH NO CODE HALF RUNS ATTENDED, OUTSIDE ALEMBIC: an index whose benefit requires no application change does not belong in the migration chain — it is DDL, not a schema contract, and it runs as an attended `psql` session against production with a named operator watching, built with `CREATE INDEX CONCURRENTLY`, preceded by its preconditions and followed by its verification query, rolled back with `DROP INDEX CONCURRENTLY`. Gotcha #31 already forbids CONCURRENTLY inside Alembic (Heroku's ~5-minute release timeout; the May 22 `odds_snapshots` outage); this says the rest of it — the alternative is NOT "put it in Alembic without CONCURRENTLY", which trades a timeout for an ACCESS EXCLUSIVE lock on a live table, but take it out of the release path entirely. General form: couple a change to the deploy only when the deploy is what makes it CORRECT; an index that helps query text already running in production has no such coupling, and binding it to a release buys nothing while inheriting the release's timeout, lock behaviour, irreversibility and unattendedness. The qualifying test is that there is NO CODE REVERT TO COORDINATE — the three `teams` FTS GINs serve `to_tsvector(...) @@ websearch_to_tsquery(...)` arms `/api/events/search` already emits unmodified, with no branch and no flag, and the result set is provably identical either way (which is also why the spec chose three separate indexes over one concatenated `setweight` vector: a combined vector would let `'red' & 'sox'` match ACROSS columns and widen recall). Contrast LAT-P058's golf indexes, which qualified until the IMMUTABLE fallback appeared whose predicate did not match the query's ILIKE — at that point the DDL acquires a code half and this clause stops applying. ATTENDED means watching the three things that break an online build, none of which is a property of the index: CONCURRENTLY waits TWICE for every transaction that can see the table so one long query stalls it indefinitely and unattended that is indistinguishable from slow; a failed build leaves an INVALID index (`indisvalid=false`) the planner never uses but every write still maintains, costing forever and silently; and `statement_timeout` must be 0 with a non-trivial `lock_timeout` (LAT-P058's execution record found '5s' FAILS here) — session GUCs being exactly what a migration runner denies you. Binds: the proposing lane writes the exact copy-paste block (session GUCs, preconditions with abort conditions, DDL, post-create verification) in one fenced block in the report; the verification query is not optional and is not "did it error" — it must read `indisvalid` from the catalog AND confirm the planner USES the index on a real specimen, because a valid index the planner declines is the same non-event as no index (gotcha #53); `migration_slot: none` is declared explicitly either way; and until the DDL has run the pre-registered red STAYS red, since a lane does not get to mark a lever done because it wrote the command for it. Does NOT cover schema changes — columns, constraints, types, anything the code depends on the shape of — which stay in Alembic unconditionally: if removing the object would make a deployed query WRONG rather than SLOW, it has a code half (LAT-P086 item 0b, Fable directive 2026-08-24, pasted and reviewed by Alex)
