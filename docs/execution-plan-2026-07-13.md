# Execution Plan — 2026-07-13 → early August (the Opus marching orders)

**Written by Fable with Alex on 2026-07-13. Fable access ends 2026-07-19; from then on, the staging brain is Opus. This document is the plan of record. If a session doesn't know what to do next: read this, read `.claude/handoff/QUEUE.md`, read `docs/backlog.md` — in that order.**

---

## 0. Standing rules (never violate; full register in memory + CLAUDE.md)

1. **Probabilities only, never odds** — the anti-gambling-enticement thesis. Any American odds rendering anywhere is a P1 bug.
2. **The blend is the product** — one clean blended number; source divergence is a data-quality bug to fix upstream, not a feature to display (three deliberate exceptions: category-page cross-source sections, playoffs Sources line, My Stuff dots).
3. **No chart smoothing, ever.** Fixed 0–100 axis. Ugly movement = data bug to fix.
4. **Assume our bug, not source bias** — capture, linkage (gotcha #14), grading, denominator, field-misuse first. "Source model bias" is the last hypothesis and never a queue branch.
5. **Sentinels over Alex's eyeball** — Alex exits detection loops; his eyeball is the SHIP gate only. If Alex catches a problem class twice, build the sentinel.
6. **Alex runs lanes, not commands** — every trigger/read is a queue Item 0 in a fresh window. Alex fires lanes, answers MC interviews, walks ship gates, does Mac-only actions (xcodebuild, TestFlight, App Store, board GUI).
7. **Never suggest stopping.** Always end with what's next. Quote times in PT.
8. **One CLI session per queue.** Flip `approved→running` as the FIRST action (anti-collision, learned r172). Never overwrite an approved/running queue. Never stack commits on gated work.
9. **Verify before re-grade** — prove a resolver bug before staging any "stored value is wrong" fix (bitten twice: #938a, #942).

## 1. The unifying goal (from Alex, verbatim-critical, 2026-07-13)

> "It's too often the case that the app just isn't doing what it's supposed to do. The event I'm looking for doesn't show up in a search, or shows up twice because sources haven't merged. The adjacent markets/futures don't appear on the event page, or they aren't formatted in a legible way; the content is already resolved but is showing up as though it isn't; or the interface is just worse than Kalshi, so I end up feeling like I should just use their app and get bombarded with enticements to gamble... where what I *want* is to use my own app and have it be clean, fast, and intuitive."

**"Fast and natural" = RELIABILITY, not aesthetics.** The design program is a trust program.

**Definition of success (Alex-ratified 2026-07-13):**
- **Flow sentinel green** — a scripted acceptance sentinel continuously runs ~20 real user flows (search → event page → props/adjacent futures → state correctness → chart renders) against production and files evidence-packed issues on failure, per the calibration-sentinel pattern (`design_calibration_sentinel.md`).
- **Kalshi-free fortnight** — Alex logs 14 straight days of daily phone use where Bain Luck answered every question and he never opened Kalshi.

**Surface priority: iPhone app first.** Alex currently consumes most on his laptop browser *because he's debugging* — that usage should wither as the cockpit + sentinels absorb detection. All reliability fixes must land on iOS parity, not web-only.

**The six failure classes → owning workstream:**

| # | Failure class | Workstream | Anchor |
|---|--------------|-----------|--------|
| 1 | Search misses the event | Instant Answers | `docs/strategy-instant-answers.md` |
| 2 | Duplicate unmerged events | Universal Matching (Epic A verticals) | #1018 chain, `strategy_universal_matching_and_surfaces.md` |
| 3 | Props/adjacent futures missing from event page | L4 completeness + related-futures surfacing | `scripts/audit_event_matching.py --l4-deep` |
| 4 | Illegible formatting | Per-surface design passes (design system) | `docs/design-system.md` |
| 5 | Resolved shown as live / stale state | State-correctness sentinel + resolution pipeline | gotcha #33, resolution-authority ladder |
| 6 | Interface worse than Kalshi | Kalshi-parity UX: instant finding, cleaner market pages, better charts, live/settled clarity (all four confirmed by Alex) | chart principles, #883 pattern |

## 2. Programs (priority order)

### P1 — Calibration done + backfill on autopilot
- **Gate:** Alex's D5 skeptical walk of /calibration (the declared done bar; also the App Store gate). Findings route to lanes; sentinel (#1054) owns future detection once the two tokens (#1055) land.
- **Measurement:** Queue #179 ships `GET /api/admin/backfill-progress` (snapshot density by settlement month, June-gap ledger recovered/pending/permanently-aged-out per gotcha #35, per-phase throughput, worker load). Ops corroborates cold, then it replaces "#1052 unmeasurable" as the standing read.
- **Success definition (Alex-ratified 2026-07-13, TWO-TIER):**
  - *Calibration SLA (internal grading floor):* ≥95% of resolved outcomes settled after Jul-2 carry calibration_probability; density ≥15 points for poly/datagolf, cal-prob-coverage (or ≥6 points) for kalshi (2h polling cadence = physics, not failure). June freeze window closed as 91.6%-of-recoverable; never-ingested remainder accepted as a known loss (gotcha #35).
  - *No-embarrassing-charts SLA (user-facing — Alex: "if a user pulled up an event page and the graph had only 15 points, that'd look embarrassing"):* every chart a user can open renders ≥1 point per open hour at provider-candle granularity (kalshi candlesticks API + poly CLOB history backfills — the candlestick project's real purpose). Measured as % of user-visible charts below the bar via the `chart_density` tile (#180 Item 5); becomes a flow-sentinel check. Live game charts are exempt-by-construction (32s betting polls + ESPN).
  - Project the finish date from measured throughput; re-project weekly.
- **Autopilot bar:** all backfill phases beat-scheduled, budget-guarded, idempotent; zero manual triggers needed in a normal week; sentinel files regressions.

### P2 — App Store re-submission (#678)
Path: D5 walk → xcodebuild (L2-82 native cal tab) → TestFlight on Alex's phone → dogfood days (start the Kalshi-free-fortnight log simultaneously) → resubmit. Held intentionally on cal credibility; do NOT push "just ship it." Dogfood notes feed the flow-sentinel script.

### P3 — Reliability/design program (the §1 table)
Run as continuous lane work: each week, the flow sentinel (build it first — it's the program's measurement) surfaces the top failure; lanes fix the biggest bucket; re-measure. Hill-climb discipline (`docs/hill-climb-guide.md`) applied to user flows instead of matching layers. Kalshi-parity UX items go through Claude Design briefs (light mode, probability-first, no smoothing) with Alex MC-interviewed on taste calls only.

### P4 — Discover always-interesting + morning digest
- Ranking: finish RANK weight fitting after Alex's grading batches (replay harness + gold set are live; blend calibration is the open item).
- Stale content: soon-resolving/settled markets must never render as open cards — fold into the state-correctness sentinel.
- **Notifications v1 = MORNING DIGEST ONLY** (Alex's explicit pick; not movers/resolutions/streaks). Scope: content selection reuses feed ranking; build scheduling + per-user preference flow + send path on the existing push foundation (`routes/notifications.py`, currently foundation-only). One daily brief: the 3–5 most interesting probabilities, personalized.

### P5 — Admin cockpit (Alex's leverage surface)
L2-102 ships v1: health tiles / "Waiting on you" with exact actions / quick-eval queue. Iterate toward: every agent-blocked-on-Alex item appears there with a one-click unblock, and every quick-eval task (label passes, promote/downrank reviews, bug-report triage) is doable inline in under a minute per item.

### P6 — Codex trial (decide by 2026-07-18)
- **Candidates:** (a) admin db-query JSONB serialization fix (return real JSON, not Python repr — small, precisely specified, flagged in #178's report); (b) combat ticker grammar adapter (fighter surnames from KXBOXING/KXUFCFIGHT tickers; acceptance = engine `mkt=[]` residual closes in `audit_resolution_engine.py`).
- **Protocol:** same brief format as a queue; Codex works a branch; compare on spec adherence, gotcha compliance, first-try CI green, review burden. Gotcha #30 (Codex push policy) applies.
- **Decision rule:** if review burden < the time saved, Codex becomes a second execution lane for file-safe, well-specified issues (LANE-MAP split); otherwise review-only or drop. Evidence in a `#887` comment.

### P7 — Secondary Apple surfaces (watch/iPad/Mac; post-iPhone-bar)
Folded from `.claude/handoff/plan-addendum-apple-surfaces.md` (Alex MC interview, 2026-07-13). **Timing: AFTER iPhone hits the flow-sentinel + Kalshi-free bar (weeks 2–3).** Standing rules (probabilities-only, blend-is-the-product, no smoothing) apply on every surface.

Alex's rulings (verbatim-critical):
- **The Apple Watch app EXISTS today** and is his TOP-priority secondary surface (CLAUDE.md was stale — platform line corrected in Queue #184). Watch purpose: "glanceable info about teams/events I'm following, and also a mini-discover feed for a few items that are highly likely to be interesting and can serve as **cocktail banter**."
- Mac/iPad: "parity in the near-term, without anything that makes it *feel* like a second-class citizen" + a roadmap to make each **truly great**, not just non-embarrassing.

- **Step 0 (cheap, do first):** audit the existing watch/iPad/Mac surfaces — what each shows, does it build, does it share payload-v2; per-device defect/greatness list. Issue: [#1080](https://github.com/alexander-bain/bainluck/issues/1080). (CLAUDE.md platform line → iOS/iPadOS/macOS/watchOS: done in Queue #184.)
- **Watch (priority):** W1 followed glances (complication + Smart Stack, 2–3 followed team/event probabilities, reuses My Stuff follows); W2 banter feed (3 cards/day from the Discover interestingness pipeline — same selection the morning digest uses, one content brain two surfaces; prefetch alongside the digest push); W3 live wrist win-prob (Live Activity/Smart Stack, gated on W1/W2).
- **iPad (truly-great):** parity + per-release smoke now; then multi-column live view (chart + markets + play-by-play — the Open second-screen scenario), Discover-as-grid, Stage-Manager-safe (gotcha #27), pointer/keyboard affordances.
- **Mac (truly-great):** parity + smoke now; then menu-bar glance, keyboard-first nav/search (Instant Answers as a global shortcut), admin cockpit as a first-class Mac surface.
- **Quality machinery:** extend the flow sentinel per-form-factor once iPhone is green; the watch gets a data-freshness/glance-staleness check (its embarrassing-chart equivalent).

## 3. This week (Fable's last: through Sat 2026-07-19)

| Day | Event | Owner |
|-----|-------|-------|
| Mon 7/13 | #179 measurement + L2-102 cockpit + r174; Alex: tokens → D5 walk → xcodebuild → dogfood | lanes + Alex |
| Tue–Wed | Backfill success-definition ratified; flow-sentinel v1 staged; Codex trial fired; grading batch #1 | lanes + Alex MC |
| Thu 7/16 | **The Open tees off (Royal Birkdale)** — live-day runbook pre-staged in L2-101's report; the sprint machinery's public exam | Lane 2 + ops dailies |
| Fri | Open cut day; digest v1 staged; Opus dry-run: one full staging cycle written by Opus, reviewed by Fable | lanes |
| Sat 7/18 | **Jul-18 card = #1024/A5 final acceptance** (headliner 14792807 enriching betting→multi-source live) | ops verdict |
| Sun 7/19 | Fable close-out: plan deltas folded into this doc; memory consolidated; queues left `approved` | Fable |

## 4. Operating model for Opus (read carefully; this is the handoff)

- The bus is `.claude/handoff/` (protocol: its README). Three lanes: QUEUE.md (/triage, backend), QUEUE-2.md (/triage2, frontend/display, file-disjoint), OPS-QUEUE.md (/ops, read-only monitoring + GitHub writes). Stage all three each cycle; digest all three reports before restaging.
- Queue sizing: ONE focused CLI session. Fresh terminal window per prod-heavy queue (guardrail taint is conversation-cumulative). First runner flips `approved→running` before any reads.
- Every "X isn't working" report to Alex must include exact fix steps in the same message. Every report to Alex ends with what's next.
- Prefer MC interviews (AskUserQuestion form) for any Alex judgment call; render grading tables in chat, never point him at files.
- Ops journal = #887. Court list (things only Alex can do) relayed verbatim every round until cleared.
- When something is proven, close the paperwork the same day — a proven-but-open epic drifts (learned: #1018 sat proven-but-open for 3 rounds).
- Weekly: re-project P1's finish date; re-run the flow sentinel trend; check this doc for drift and update it in the same change.

## 5. Tech debt register (schedule during natural openings, not as interrupts)

1. Admin db-query JSONB repr → real JSON (Codex candidate (a)) — bites every audit-tool consumer.
2. `typescript.ignoreBuildErrors: true` (gotcha #10) — the flip to enforced `tsc --noEmit` in CI is an infra decision; propose once flow sentinel is green.
3. Chronic high-volume Sentry errors (firstSeen May): datagolf_freshness watchdog SQL, transition_event_statuses TypeError, discover_events MultipleResultsFound — burn down one per week.
4. Settled-blend cosmetic fold for pre-Jul combat events (#179 Item 3's task covers; verify it drained).
5. Search `ts_vector` stored index — only with real search-trace evidence (per CLAUDE.md).
6. Hub-lister horizon cap for non-combat domains if far-future padding recurs (golf/tennis exempt by design).

## 6. Decision log pointers

- `docs/decisions-2026-07-06.md` — cal done bar register
- `.claude/handoff/ALEX-GO-1020.md` — the entity-registry GO
- `.claude/handoff/strategy_universal_matching_and_surfaces.md` — Epic A/B plan of record
- `.claude/handoff/discover_ranking_audit_2026-07-08.md` — RANK phases
- `.claude/handoff/calibration_page_audit_2026-07-09.md` — cal page audit + payload v2 rule
- `.claude/handoff/design_calibration_sentinel.md` — the sentinel pattern (template for the flow sentinel)
- Memory index (Cowork): standing rules with verbatim Alex quotes — the "why" behind every rule above.
