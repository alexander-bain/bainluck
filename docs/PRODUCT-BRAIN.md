# PRODUCT BRAIN — the load-bearing judgment for staging Bain Luck lanes
# Purpose: everything an agent (Codex / Fable / Opus) needs to stage work WELL — the rulings AND the WHY behind them.
# This externalizes Fable's private memory into the repo so the sharpest available reasoner can stage. Read this + CLAUDE.md + docs/PRD.md.
# Owner: whoever stages. Update when Alex issues a new ruling (append + date it). Last consolidated 2026-07-28.

## HOW TO USE THIS
**GitHub Issues is the only priority source; this doc holds judgment, never status.**

The queue-file mechanics live in `.claude/handoff/README.md` + `FABLE-STANDIN.md`. THIS doc is the judgment layer: the standing rulings, the reasoning behind them, and the failure modes to avoid. Priority and ordering come from the [GitHub Issues board](https://github.com/alexander-bain/bainluck/issues) — not from this doc and not from any planning file. Pre-written specs are in `READY-FIXES.md`; deep strategy in `.claude/handoff/strategy_*.md`.

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

## RULINGS — 2026-07-30 afternoon (via Fable; THE PRODUCT-FIRST RESET)
Context: Alex's concern, validated by a live sweep — three of four staged
queues were plumbing while the live site showed a 10s cold load, a 17-day-old
settled event under "Upcoming," 0% heroes, a broken make-the-cut sort, and
mangled titles. Process was begetting process. Two new STAGING LAWS:

- **THE VISIBLE-PAYOFF RULE.** Every staged queue must state, in one
  plain-English sentence at the top, what ALEX WILL SEE CHANGE on the site or
  app after it ships ("After this: cold loads show cards in under 3 seconds").
  If the sentence cannot be written, the queue is PLUMBING and plumbing is
  capped at ONE lane-session per day across all lanes. Verification-of-
  verification counts as plumbing. WHY: queues had drifted to being staged
  from reports about process debt instead of from the product.
- **THE WEEKLY PRODUCT SCOREBOARD.** A standing weekly sweep (Fable, Chrome,
  Mondays) measures what Alex feels: cold-load seconds, time to first card,
  jank count from a standard sweep (stale-under-Upcoming, 0%/mismatched
  heroes, sort/label/title errors), and design ships that week. Lanes are
  judged on moving these numbers, not on tests passed or cards closed.
  Scoreboard lands at repo root as _SCOREBOARD-<date>.md, short and plain.
- Considered and NOT ratified today (revisit only if Alex raises them):
  a security done-bar ruling and a Review/Verify backlog bankruptcy.
