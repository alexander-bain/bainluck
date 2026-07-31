# Bain Luck — Issue-Linked Roadmap, Q3 2026

Using the strategy document I just produced (`docs/unified-strategy-2026-06.md`), this converts its conclusions into a prioritized, dependency-aware execution plan reconciled against the real tracker — every issue number below is a real open issue verified in `docs/github-issues-export.json` (exported June 9, 2026; 44 open). Labels are exclusively the canonical set from `docs/github-workflow.md:10–50`. Per the project rule (`docs/gotchas-reference.md` #90), no verification plan below accepts "code merged" — done means measured production evidence.

**Reconciliation basis.** I read `docs/github-workflow.md` in full (labels :10–50, Project columns :52–63, backlog markers :69–92, the `scripts/claim_issue.py` lock :107–113, weekly sweep :115–129) and the CLAUDE.md GitHub-workflow section. I inspected the full bodies of: #830, #829, #828, #823, #723, #745, #678, #671, #651, #600, #598, #597, #596, #587, #490, #454, #738, #826, #806, #698, #683, #754, #827, #825, #818, #816, #807, #805, #804, #803, #802, #762, #824, #833, #834, #835, #836, #837, #838, #841, #842, #843 — and titles/labels of the remaining open items (#839, #840). Two things the mega-prompt's issue list did not include but the tracker does, and which materially change reconciliation: **#833 and #834 are open children of #828** that already own pieces of the strategy's "feedback contract" recommendations, and the **#835–#843 infra batch** already owns backups, crash reporting, and monitor wiring. One number I could NOT verify as open: #453 (referenced as the blocker inside #454's body); it is absent from the open set, so I treat it as closed and do not rely on it.

---

## 1. Reconciliation matrix

Rows are the strategy doc's thrusts; resolution rule applied throughout: if an open issue owns it, extend that issue — never duplicate.

| Strategic thrust (strategy §) | Already covered | Partially covered (issue + precise gap) | Net-new | Conflicts with existing |
|---|---|---|---|---|
| Resolution authority ladder; never-guess policy (§8.1) | — | #754 owns the *cleanup* (drain pass2_guess), #806 owns the *inflow audit*; the gap is the **structural enforcement**: a single authority ordering consulted by every phase + a CI guard so no phase writes a lower-authority source over a higher one (`backfill_winners.py` NOT-IN lists at :150–152, :520–523 are today's scattered version) | **#845** | None — #845 is the policy #754/#806 implicitly assume |
| pass2 decomposition drains (§8.1) | #804, #805, #816, #802, #803 (all "Parent: #754") | #805's gap: it says "No pipeline currently targets this" — needs the concrete women's-NCAAB ESPN score backfill commitment (→ extend-comment E-805). #804's gap: path 3 (create events for NCAAB small conferences) is a product decision → extend-comment E-804, `needs-user` | — | — |
| Source-coverage truth + metric direction flip (§8.1 #826 row) | #826 owns the metric flip + alerting ask | Gap: the issue's step 2 ("understand the gap: ingested-but-unlinked vs doesn't-exist-upstream") has no measurement plan → extend-comment E-826 | — | — |
| Correctness Console (§5.4) | — | #738's acceptance criterion "no metric in the dashboard is misleading" and its broken status endpoint are inputs; #841 owns the *Sentry monitor* slice of my alert list | **#846/2b** (split: status-endpoint timeout fix; console page) | Mild overlap with #841 — resolved by scoping #846/#847 to the page and threshold computation, and routing the two free Sentry monitors through #841 (extend-comment E-841) |
| Stale-card/feedback serving contract (§5.2) | #828 (P0) + children #833 (movement freshness) + #834 (durable serving penalties) own ALL of it | — | — | **Strategy doc said #828 was "mostly closed" — wrong; corrected in the revision.** Roadmap treats #828/#833/#834 as the canonical owners; nothing new filed |
| Label loop → ranking (#596 execution) (§6.2d, §2 flywheel) | #596 owns the tune; #597 the reranker; #587 the parent | #596's gap: no concrete mechanism named — the strategy supplies one (calibrate `scripts/calibrate_interestingness.py` weights on the labeled export, ship via the existing `interestingness:blend_weight` Redis key, stratified by reviewer cohort) → extend-comment E-596 | — | — |
| Interestingness blend baseline (§10 item 4) | — | — | **#848** (blend on/off measured comparison — the calibration #596 needs a baseline anyway) | Possible conflict with #596 if run concurrently — same Redis key + `feed.py:4757–4769`; serialized below |
| Kid-labeler (§6.2) | — | #671 owns reviewer access/onboarding/rate-limits — exactly the substrate; #600 owns the labeling UI design pass; #587 owns the taxonomy/loop | **#849** (kid profile = content gate + restricted axes + honeypots/agreement), depends-on #671 | None if #849 stays a *profile of* #671's reviewer role rather than a parallel access path |
| Cold-start fast-lane + probe page + chip-row card (§4.4) | — | #454 owns the GA4 reporting the A/B metric needs (Discover funnel, onboarding comparison) — gap: A1 metric definition → extend-comment E-454 | **#850/5b** (backend; frontend) | **Must respect closed #482's no-modal decision** — #851 is an in-feed card, not a modal; this is stated in the issue body to prevent re-litigating |
| discover_llm v2: persisted story_key, entity slugs, stakes, kid_safe (§3.2–3.3) | — | #834 will consume persisted story keys (penalties by story key); #830's audit ratchets can consume archetype/story coverage metrics | **#852/6b** (split: story_key column + consumers; entity slugs + semantic tokens). stakes/kid_safe ride 6b | Migration touches `models.py` → Red zone; serialized below |
| Election-allowlist dead regex (§1.3 runner-up, §10 item 2) | — | — | **#854** (delete/merge duplicate `_MAJOR_ELECTION_RE`, add behavioral test) | Check `tests/test_futures_highlights.py` — if it asserts the loose behavior, the test changes too (noted in issue) |
| Doc-drift ledger (§1.3 artifact) | — | — | **#855** (one PR fixing all 9 ledger rows) | None |
| Ops insurance: backups, crash reporting, monitors (§9 H1) | #842 (pg:backups + drain), #839 (Crashlytics), #841 (Sentry monitors) | — | — | — |
| App Store resubmission (§7.3) | #678 owns it (P0, needs-user) | Gap: strategy adds "strip Watch + visionOS" to the checklist → extend-comment E-678 | — | — |
| Quota/WebSocket/source-cost work (§1.2 ingestion) | #835, #836, #837, #838, #843 own all of it | — | — | Strategy's 60/40 allocation implies #836/#837 (p2 perf) wait behind correctness P0s — priority kept, sequencing noted |
| Calibration sample 10–20x via spreads/totals (§9 H2; backlog Subproject F) | — | Backlog-only today (`docs/backlog.md:848–855`) | Deliberately **NOT filed** (see §5 NOT-now: premature until #845 + #651/#683 land) | — |
| Widget/Mac/Watch/Siri redesigns (§7.2) | — | — | Deliberately **NOT filed** (see §5: gated on #678 + #839) | — |

**Open issues the strategy implies we should down-prioritize or close:**

- **#803 (298 KXNBAMENTION broadcast mentions)** — close-leaning. The strategy's authority ladder says unresolvable-without-authoritative-data stays `is_winner=NULL` and excluded, which is the issue's own path 3 ("accept unresolvable"). 298 outcomes is 0.4% of the #754 population; the settled-events API path (its path 2) is already covered by the generic Kalshi settlement drain in #754. Recommend: comment + close as absorbed-by-#754, or relabel `priority:p3`. Backlog edit required on close (workflow :104).
- **#490 (confidence tiers)** — keep open but explicitly sequence AFTER the correctness exit gates (§8.2): shipping a user-facing "confidence" badge while hockey reads 22.7pp MCE and #738's spot-checks haven't run would put the brand's weakest claim on every card. It is already `needs-user`; add the dependency note (extend-comment E-490).
- **#824 (CI alert, alert-intake)** — triage per the weekly sweep rule (`docs/github-workflow.md:118`): head of master has moved since `fa95564`; if the current head's CI run is green, close with the standard alert-intake closing comment, no backlog edit needed (workflow :105).
- **#745 (someday: line-moved explanations)** — correctly parked at p3; no action, explicitly NOT promoted this quarter.

---

## 2. Prioritized quarter plan with dependency graph

Ordering principle: leverage × dependency. Correctness items lead not because of the 60/40 allocation alone but because three of them (#806, #845, #698/#683) are *upstream of the moat itself* — every week of delay adds wrongly-resolved rows that later need re-cleaning — while the highest-leverage growth items (#678, #848) cost near-zero engineering.

**Theme A — Correctness foundation** (~60% of agent capacity)
1. #806 — find/kill the pass2 writer (P0, the tap before the drain)
2. #845 — resolution authority ladder + CI guard
3. #698 — Polymarket settlement-price sync (P0, exact fix already specified in-issue)
4. #683 — Kalshi snapshot history via trades API (P0)
5. #651 — cal_prob backfill for 348K Kalshi outcomes (consumes #683's output)
6. #762 / #818 / #827 — golf & volume calibration fixes (#827 is #818's named child-fix)
7. E-805 / E-804 — score backfill + no-event decisions
8. E-826 — coverage-gap split measurement
9. #825 — Polymarket tennis linking (1,898 markets)
10. #807 — Score Differential empty SVG (P1 user-facing regression; independent)

**Theme B — Operator & admin**
11. #846 — fix `backfill-winners/status` timeout (instrumentation prerequisite)
12. #847 — Correctness Console page
13. E-841 — Sentry uptime + cron monitors wired to the console's thresholds
14. #842 / #839 — backups verified, Crashlytics added (needs-user, cheap)

**Theme C — Human-signal & labeling**
15. E-678 — App Store resubmission checklist additions (needs-user; calendar-critical)
16. #671 — non-admin reviewer access (the gate for everything kid-related)
17. #849 — kid labeler profile (gate + honeypots + restricted axes)
18. #848 — interestingness blend baseline (before, not after, weight tuning)
19. E-596 — label-driven weight calibration (consumes #848 baseline + #849/adult labels)
20. #597 — stays `blocked` on its own documented thresholds

**Theme D — Content understanding**
21. #854 — election regex dead-code fix (small, early, safe)
22. #852 — persisted `story_key` (then #834 consumes it)
23. #853 — entity slugs + stakes + kid_safe in `discover_llm` v2

**Theme E — Growth & onboarding**
24. #850 — cold-start fast-lane + probe-page mixer mode
25. #851 — chip-row card + GA4 events
26. E-454 — A1 activation metric added to the GA4 report set

**Theme F — Discover/native product (continuing work, already owned)**
27. #823 (in-progress) → #829 → #830 → #598 — bundles → native parity → audit ratchets → QA
28. #833 / #834 — under #828, serialized with #852 where story keys overlap

**Theme G — Moat & docs**
29. #855 — doc-drift PR
30. #835 — quota audit (protects the most constrained resource; independent)

### Dependency edges ("X blocks Y")

- #806 blocks #845 (the ladder's CI guard asserts inflow=0; can't assert while a writer is loose)
- #845 blocks #754's close (cleanup without enforcement re-corrupts), and #754 blocks #804/#805/#816/#802/#803 closes (they are its decomposition)
- #683 blocks #651 (cal_prob needs snapshot history to compute closing lines)
- #698 blocks #738's Polymarket spot-check criterion (settlement prices must be written before validation makes sense)
- #846 blocks #847 (console can't render a timing-out endpoint)
- #845 + #651 + #698 block #738's acceptance checklist (the epic verifies the corrected pipeline, not the broken one)
- #678 blocks #671's friends-and-family rollout breadth (TestFlight distribution), and #671 blocks #849 (kid profile is a reviewer-role specialization)
- #848 blocks E-596 execution (tuning without an on/off baseline is uninterpretable)
- #849 + E-596 block #597's unblock (its own documented label thresholds)
- #852 blocks the story-key slice of #834 (durable penalties keyed on persisted story keys)
- #850 blocks #851 (frontend card writes interactions the backend branch must weight)
- E-454 blocks the #850/#851 A/B *readout* (not the build)
- #823 blocks #829 (native renders the bundle metadata), #829 blocks #830's native-coverage ratchets being meaningful, #829 blocks #598's next QA build

### Critical path

**#806 → #845 → #754 drain (with #698, #683→#651 in parallel lanes) → #738 acceptance → #847 console green → correctness exit gates (§8.2) → rebalance to 40/60.** On the growth/labeling side the critical path is **#678 → #671 → #849 → E-596**, and it is mostly `needs-user` at the head — meaning Alex's personal queue, not agent capacity, is the binding constraint there.

### Parallel Work Protocol (Red-zone serializations)

- **`tasks/backfill_winners.py`:** #845, #754 drain phases, #762, #818/#827 all write here → strictly serialize; one owner thread at a time via `scripts/claim_issue.py` (workflow :107–113).
- **`tasks/polymarket.py`:** #698 (lines 1216–1238) and #837 (WebSocket) → serialize; do #698 first (P0 vs p2).
- **`routes/feed.py` + Redis ranking keys:** #848, E-596, #850, #834 → #848 before E-596 (same `interestingness:blend_weight` key); #850 and #834 touch disjoint functions (`_build_discover_category_affinities` vs serving penalties) but the same file — claim sequentially, Yellow-at-best.
- **`models.py` + Alembic migration:** #852 is the only migration this quarter (single `story_key` column) — never parallel with any other migration (CLAUDE.md Parallel Work Protocol: two Alembic migrations = never).
- **`utils/feed_market_quality.py`:** #850 (mixer cold-start mode), #852 (story-key read path), #833 (movement freshness) → claim sequentially.

---

## 3. The issues — paste-ready

### #845 — Enforce a resolution authority ladder in backfill_winners; CI guard against downgrade writes

**Labels:** `area:calibration`, `type:quality`, `priority:p0`, `blocked` (by #806)

**Problem.** `is_winner` writes are governed by ~30 ad-hoc phases with scattered NOT-IN guard lists (`tasks/backfill_winners.py:150–152, 520–523`) and disabled guess passes (`:2444–2449, 2478`). Nothing structurally prevents a phase (or a future contributor) from overwriting an authoritative settlement with a heuristic, which is how 71,896 guess-resolved outcomes accumulated (#754) and why the count has oscillated upward even after the disable (#806).

**Scope.**
- In: a single `RESOLUTION_AUTHORITY` ordering (`api_settlement > game_score | datagolf_leaderboard > clean_resolution > NULL; guess-family = never-write`) in `tasks/backfill_winners.py`; one helper that every `is_winner`/`resolution_source` write goes through; replace the per-phase NOT-IN lists with the helper; a pytest in `backend/tests/` asserting (a) no phase writes a lower-authority source over a higher one and (b) no code path can emit a guess-family `resolution_source` (catches the #806 writer class permanently).
- Out: draining the existing 71,896 (that is #754); new resolution data sources; schema changes.

**Acceptance criteria.**
- [ ] All `resolution_source` writes in `backfill_winners.py` route through the authority helper (grep shows zero raw writes)
- [ ] New tests fail if a downgrade write or guess-family write is introduced; wired into CI (note `tests/test_tasks_wiring.py` allowlist untouched — no new beat task)
- [ ] 14 consecutive days of zero guess-family inflow in production after deploy

**Verification (measured).** `python3 scripts/audit_pass2_inflow.py` daily for 14 days = 0 new rows; `GET /api/admin/backfill-winners/status` shows `resolution_source` mix shifting only toward higher authority; `GET /api/admin/query?sql=SELECT resolution_source, COUNT(*) ... GROUP BY 1` snapshot before/after.

**Files.** `backend/app/tasks/backfill_winners.py`; new `backend/tests/test_resolution_authority.py`.

**Relationships.** Depends-on #806 (writer must be identified first). Blocks #754 close. Relates #738 (epic's "prove the math" criterion). Backlog source: `docs/backlog.md` → "Workstream: is_winner Backfill" (add line, see §6).

**Agent-sizing.** One focused session (refactor + tests, no data migration). ✔

---

### #846 — Fix /api/admin/backfill-winners/status 30s timeout

**Labels:** `area:admin-ops`, `area:calibration`, `type:perf`, `priority:p1`, `needs-agent`

**Problem.** The single most important correctness endpoint times out at Heroku's 30s limit (#738 body: "Status endpoint currently timing out"), making winner-coverage unobservable — the metric CLAUDE.md's session-startup checklist requires.

**Scope.** In: move the expensive aggregation into a Celery-precomputed Redis cache read by the endpoint (the exact pattern already used by `GET /api/admin/snapshots/distribution`, `docs/backlog.md:707–712`, and by category pages per gotcha #95); update `tests/test_tasks_wiring.py` allowlist for the new beat entry. Out: changing what the endpoint reports.

**Acceptance criteria.**
- [ ] `GET /api/admin/backfill-winners/status` returns < 2s in production (CLAUDE.md latency threshold)
- [ ] Data freshness ≤ 1h, with a `computed_at` field in the response

**Verification (measured).** Timed production curl via `$BAINLUCK_API` before/after; endpoint payload shows `computed_at`; background queue stays < 50 (`GET /api/admin/celery-debug`).

**Files.** `backend/app/routes/admin.py` (status endpoint), `backend/app/tasks/monitoring.py` (precompute task), `backend/app/tasks/__init__.py` (beat entry), `backend/tests/test_tasks_wiring.py`.

**Relationships.** Blocks #847. Relates #738 (its current-state numbers come from this endpoint). Backlog source: is_winner Backfill workstream "Monitor" line.

**Agent-sizing.** One session. ✔

### #847 — Correctness Console: one admin page answering "can we trust our numbers today?"

**Labels:** `area:admin-ops`, `area:calibration`, `type:feature`, `priority:p1`, `blocked` (by #846)

**Problem.** Correctness status is spread across ≥6 endpoints operated via curl; the #738 epic demands "no metric in the dashboard is misleading," and #826 proved the flagship metric (link rate) measured the wrong direction while event pages sat 83% bare. There is no single operator view of resolution integrity, calibration health, coverage, and drift.

**Scope.**
- In: new `frontend/app/admin/correctness/page.tsx` composing EXISTING endpoints only — `GET /api/admin/backfill-winners/status` (winner coverage by source, market-level `BOOL_OR` metric per gotcha #100, resolution_source mix, pass2 inflow sparkline), `GET /api/calibration` + `/api/calibration/diagnostics` + `/api/calibration/snapshot-health` (MCE per category with N, red at >10pp for N>100), `GET /api/admin/prediction-markets/link-rate` (with `denominator_diagnostics`), the event-level source-coverage data (#826, commit `a082d1c6`), `GET /api/admin/audit/all` (grid health), `GET /api/admin/snapshots/distribution`. Threshold states (red/green) per the CLAUDE.md session-startup thresholds. Absorbs `/admin/matching` and `/admin/source-intelligence` as tabs (their pages stay until parity, then a follow-up removes them).
- Out: any new backend aggregation (#846 covers the one broken endpoint); alerting delivery (E-841 owns the two free Sentry monitors; further alert channels are a later issue).

**Acceptance criteria.**
- [ ] One page shows: winner coverage per source, guess-family count + 14-day inflow, per-category MCE with N, Tier-1 event-level source coverage, link rate + denominator diagnostics, grid health, snapshot sparse %
- [ ] Every tile has an explicit threshold and red/amber/green state matching CLAUDE.md "Thresholds for immediate action"
- [ ] Page loads < 3s (composed from cached endpoints)
- [ ] 3 GA4 hooks present (`usePageTracking`, `useScrollDepth`, `useEngagementTime` — mandatory per CLAUDE.md)

**Verification (measured).** Two weeks of session-startup health checks run from the console instead of curl, with at least one real regression caught and linked (the #826-class test: would this page have caught 17% MLB coverage? — demonstrate by checking the coverage tile against `GET /api/admin/query` ground truth once).

**Files.** `frontend/app/admin/correctness/page.tsx` (new), `frontend/app/admin/layout.tsx` (nav), no backend changes.

**Relationships.** Depends-on #846. Relates #738, #826, #806, #841. Backlog source: new line under "Current Priority: Calibration & Data Quality" (§6).

**Agent-sizing.** One session (pure frontend composition). ✔

---

### #848 — Measure the interestingness blend: production baseline on vs off

**Labels:** `area:discover-ranking`, `type:quality`, `priority:p1`, `needs-user`

**Problem.** The interestingness blend shipped at `blend_weight=0.2` (`routes/feed.py:4757–4769, 5012–5028`; #440 closed) without the label-calibration step its own plan required (`docs/backlog.md:360–369`) and without any measured on/off comparison. Before #596 tunes weights, we need to know whether the blend helps at all — the kill switch already exists.

**Scope.** In: with Alex's go-ahead (`needs-user`: brief production ranking change), set Redis `interestingness:blend_weight=0`, capture `python3 scripts/audit_feed_quality.py` (all @20 metrics + `email-hit@20/@50` + `curator-hit@20`), restore `0.2`, capture again; three runs each at different times of day; record the decision (keep 0.2 / set 0 / tune) in the issue and `docs/backlog.md`. Out: changing the blend formula; weight tuning (that's E-596).

**Acceptance criteria.**
- [ ] Six audit runs captured (3 on / 3 off) with metric tables in the issue
- [ ] Explicit recorded decision with the deltas
- [ ] `boring-rate@20 = 0` maintained in whichever configuration is kept

**Verification (measured).** The audit outputs themselves (`scripts/audit_feed_quality.py` prints boring/ladder/duplicate/explanation/email-hit metrics — `:83–130`); Redis key state confirmed via `GET /api/admin/query` is not applicable (Redis) — confirm via the `interestingness` field exposure on feed items (`feed.py:5289`).

**Files.** None (runtime Redis key + audit runs); issue comment is the artifact.

**Relationships.** Blocks E-596 execution. Relates #440 (closed), #587. Backlog source: 0u-N1 line (§6 updates it).

**Agent-sizing.** One short session. ✔ `good-first-agent-task` candidate except for the needs-user gate.

---

### #849 — Kid-labeler profile: content-gated queue, restricted axes, honeypots, agreement scoring

**Labels:** `area:discover-ranking`, `area:admin-ops`, `type:feature`, `type:quality`, `priority:p1`, `blocked` (by #671)

**Problem.** The labeling loop needs volume (100–200 labels per eval cycle, 1,000–2,000 before #597 — `docs/discover-labeling.md:196–203`) and the only standing labeler pool is family. #671 builds the reviewer role; what's missing is a kid-safe profile of it: a hard content gate, fewer/simpler label axes, and quality controls so the labels are usable in gold sets.

**Scope.**
- In: (1) `labeler_profile='kid'` parameter on the labeling-queue builder (`backend/app/utils/labeling_queue.py` + the candidate endpoint in `backend/app/routes/admin_judgments.py`) enforcing ALL of: `llm_sport_category` allowlist (sports + weather + entertainment + culture + tech; politics/geopolitics/economics/health/crypto excluded), Kalshi ticker-prefix deny derived from `utils/sport_keys.py` maps, name fails `_RUSSIA_WAR_TERRITORY_RE`/`_OUTBREAK_RE` (`utils/feed_market_quality.py:329, 243`); (2) ~10% honeypot seeding per batch (known-`kill` from effective-settlement followups; known-`love` from email ground-truth hits), honeypot hit-rate stored in `ranking_judgments.label_metadata` (`models.py:1493`); (3) ~20% two-reviewer overlap assignment in `scripts/export_discover_labeling_batch.py`, agreement computed in `scripts/analyze_ranking_judgments.py`; (4) kid UI variant of `frontend/app/admin/labeling/page.tsx`: 😍/😐/💤 (= `overall_label` love/fine + `boring`) and an "I don't get it" chip (= `clarity='confusing'`) only.
- Out: reviewer auth/onboarding (that is #671); any ranking change from kid labels (gold-set only until E-596); native labeling parity (#605 territory per `docs/backlog.md:358`).

**Acceptance criteria.**
- [ ] Zero politics/geopolitics/health/war cards in 200 sampled kid-queue cards (manual audit checklist in issue)
- [ ] Honeypot hit-rate and per-reviewer agreement visible in `scripts/analyze_ranking_judgments.py` output
- [ ] Kid-submitted judgments carry `surface='discover_kid'` + reviewer provenance
- [ ] Gate enforced server-side at queue build — `GET /api/feed` untouched (verify zero diffs to `routes/feed.py`)

**Verification (measured).** Two-week pilot: `GET /api/admin/query?sql=SELECT reviewer, COUNT(*) FROM ranking_judgments WHERE surface='discover_kid' GROUP BY 1` shows ≥200 labels; honeypot agreement ≥80% for at least one kid reviewer; `python3 scripts/evaluate_discover_label_gold_set.py` runs green on a kid-inclusive export (rows in `discover_label_eval_runs`).

**Files.** `backend/app/utils/labeling_queue.py`, `backend/app/routes/admin_judgments.py`, `frontend/app/admin/labeling/page.tsx`, `backend/scripts/export_discover_labeling_batch.py`, `backend/scripts/analyze_ranking_judgments.py`.

**Relationships.** Depends-on #671; relates #587 (parent loop), #600 (design pass should cover the kid variant — note added there via #600's existing scope), #596/#597 (consumers). Backlog source: new line under 0u "Human labeling" block (§6).

**Agent-sizing.** Borderline — split if needed into #849a (backend gate + honeypots) and #849b (kid UI + overlap/agreement), with 4a blocking 4b. Filed as one issue with the split noted so the owner decides.

---

### #850 — Cold-start signal: fast-lane young-session swipes + first-page category probe

**Labels:** `area:discover-ranking`, `type:feature`, `priority:p1`, `needs-agent`

**Problem.** A zero-signal session needs ~12 negative swipes before the feed visibly bends (3+ dismisses per category to reach −0.40, `utils/personalization.py:462–468`), and the first page is identical for everyone. #482 (closed) deliberately removed modal onboarding in favor of swipe-as-signal — so the fix is to make early swipes worth more and the first page more informative, not to add friction back.

**Scope.** In: (1) in `_build_discover_category_affinities` (`routes/feed.py:2997`), weight interactions 2x when the session's total interaction count is < 20; (2) `cold_start=True` mode in `diversify_discover_first_page` (`utils/feed_market_quality.py:972`) that widens category spread across the first 8 cards when the personalization context is empty; bounded-caps unchanged (`MIN_MULTIPLIER 0.15`, category cap +0.18). Out: any new store/endpoint; the chip-row card (#851); iOS changes.

**Acceptance criteria.**
- [ ] Unit tests: a session with 2 same-category dismisses under 20 total interactions reaches the −0.40 floor behavior that previously took 3+
- [ ] First-page category spread for an empty context ≥ 5 distinct `_discover_category_group` buckets (assert via test on the mixer)
- [ ] `boring-rate@20=0`, `duplicate-family-rate@20=0` unchanged

**Verification (measured).** `python3 scripts/audit_feed_quality.py` before/after (category distribution@20 line, `:105`); production: `GET /api/admin/discover-engagement` dismiss-rate for sessions' first 20 interactions trending down over 2 weeks.

**Files.** `backend/app/routes/feed.py` (`_build_discover_category_affinities`), `backend/app/utils/feed_market_quality.py` (`diversify_discover_first_page`), tests in `backend/tests/test_personalization.py` / `test_feed_discover_affinities.py`.

**Relationships.** Blocks #851 readout. Relates closed #482 (constraint, cited in body), #454 (metric reporting). Backlog source: replaces the dormant "Redesign first 30 seconds" P0-Product line (§6).

**Agent-sizing.** One session. ✔

### #851 — Inline "more like this?" chip-row card + activation events

**Labels:** `area:discover-ranking`, `type:feature`, `priority:p2`, `blocked` (by #850)

**Problem.** Swipes teach categories one card at a time; an optional in-feed chip-row card (position ~6, scroll-past dismissible — NOT a modal, per #482's decision) lets a motivated new user hand us 3 categories in one gesture, writing the same `discover_interactions` rows ranking already reads.

**Scope.** In: one card component on `frontend/app/discover/page.tsx`; taps POST existing `/api/feed/interactions` (`routes/feed.py:247`) as `action='like', item_type='category'`; GA4 `onboarding_step` events with `step_name='category_chip_row'`, `platform=web` (taxonomy already exists, `docs/backlog.md:224–278`); shows once per session, never for sessions with ≥20 interactions. Out: backend changes (#850's aggregation already consumes category rows); iOS parity (follow-up after readout).

**Acceptance criteria.**
- [ ] Card renders for fresh sessions only; dismiss-by-scroll; zero blocking UI
- [ ] Chip taps visible in `discover_interactions` (`item_type='category'`) and in GA4 as `onboarding_step`
- [ ] 3 mandatory GA4 hooks untouched on the page

**Verification (measured).** `GET /api/admin/query?sql=SELECT category, COUNT(*) FROM discover_interactions WHERE item_type='category' GROUP BY 1` shows real volume within a week of deploy; A1 metric comparison (per E-454) after 4 weeks: % of new sessions with ≥5 `prediction_submit` or ≥3 detail clicks in 7 days, variant vs holdback.

**Files.** `frontend/app/discover/page.tsx`, `frontend/lib/discoverInteractions.ts`, `frontend/lib/api.ts`.

**Relationships.** Depends-on #850; readout depends on E-454. Backlog source: same line as #850 (§6).

**Agent-sizing.** One session. ✔

---

### #852 — Persist story_key on futures_markets; caps and dismiss-propagation read the column

**Labels:** `area:discover-ranking`, `type:quality`, `priority:p1`, `needs-agent`

**Problem.** Story keys are recomputed per request by regex (`utils/feed_market_quality.py:454–562`) and exist nowhere in the DB. Story caps silently miss markets whose names drift from the patterns, dismiss propagation (14-day suppression, `routes/feed.py:666–689`) is unauditable by SQL, and #834's durable serving penalties want a stable key to penalize by.

**Scope.** In: nullable indexed `story_key` String column on `futures_markets` (single Alembic migration — revision ID ≤32 chars per gotcha #1, **no** CREATE INDEX CONCURRENTLY per gotcha #31; index is small, regular CREATE INDEX is safe); written during `enrich_discover_llm_metadata` batches and during quality classification backfill (Celery, background queue); `diversify_quality_families` (`feed_market_quality.py:1589–1655`) and dismiss propagation prefer the column, regex as fallback for NULL. Out: new story keys; #834's penalty mechanics (it consumes the column).

**Acceptance criteria.**
- [ ] Migration applied; ≥90% of top-50 Discover futures have non-null `story_key` within a week (backfill task working)
- [ ] Caps + dismiss propagation read the column first (tests in `tests/test_feed_dismiss_propagation.py` extended)
- [ ] `duplicate-family-rate@20=0` holds; `category-spread@20` non-decreasing

**Verification (measured).** `GET /api/admin/query?sql=SELECT COUNT(*) FILTER (WHERE story_key IS NOT NULL)::float/COUNT(*) FROM futures_markets WHERE status='open'`; `python3 scripts/audit_feed_quality.py` before/after.

**Files.** `backend/app/models/models.py` (FuturesMarket), `backend/alembic/versions/` (new), `backend/app/tasks/enrich_markets.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/routes/feed.py`, `backend/tests/test_feed_dismiss_propagation.py`.

**Relationships.** Blocks the story-key slice of #834. Relates #828, #830 (ratchet can assert story-key coverage). **Red zone:** the quarter's only migration; never parallel with another migration. Backlog source: new line under 0u next-wave (§6).

**Agent-sizing.** One session. ✔

### #853 — discover_llm v2: normalized entity slugs, stakes, kid_safe

**Labels:** `area:discover-ranking`, `type:feature`, `priority:p2`, `blocked` (by #852 for schema version coherence)

**Problem.** `discover_llm` entities are free text, so semantic-dismiss tokens fragment on spelling variants; there's no stakes signal to replace brittle boring-regexes; and the kid gate (#849) wants a second, independent `kid_safe` flag. All written by the existing bounded batch — never request-time, never full-backlog (CLAUDE.md LLM rules).

**Scope.** In: extend the `enrich_discover_llm_metadata` prompt/schema (`backend/app/tasks/enrich_markets.py`, 125/6h cadence unchanged, `tasks/__init__.py:1439–1444`) with `entities[{name,slug,kind,salience}]` (slug = deterministic post-processing, no extra LLM call), `stakes`, `kid_safe`, `prompt_version`; `_discover_feature_tokens` (`routes/feed.py:3118`) emits `entity:{slug}` when available; bounded `stakes` nudge in `quality_score_adjustment` (`feed_market_quality.py:704–722`, +6/−10 capped). Out: persisted entity table; any request-path LLM; replacing the regex stack wholesale.

**Acceptance criteria.**
- [ ] v2 metadata on ≥80% of feed-shaped candidates within 2 weeks (cadence math: 125×4/day vs candidate pool size)
- [ ] Semantic-dismiss replay shows higher repeat-recall with no cross-category false-positive increase (generic-prefix guard `utils/personalization.py:503–508` untouched)
- [ ] Gold-set eval non-regressing: `boring-rate@20=0`, `broad-appeal@20` non-decreasing (`scripts/evaluate_discover_label_gold_set.py`)

**Verification (measured).** `GET /api/admin/query` coverage count on `market_metadata->'discover_llm'->>'v' = '2'`; `python3 scripts/audit_feed_quality.py` + gold-set eval run rows in `discover_label_eval_runs`; OpenAI spend stays ~$10/mo (CLAUDE.md services table) — check the billing dashboard once.

**Files.** `backend/app/tasks/enrich_markets.py`, `backend/app/routes/feed.py` (`_discover_feature_tokens`), `backend/app/utils/feed_market_quality.py` (`quality_score_adjustment`), tests in `backend/tests/test_personalization.py`.

**Relationships.** Depends-on #852 (schema version + story_key mirror); feeds #849 (`kid_safe` second gate). Relates #587. Backlog source: same 0u next-wave block (§6).

**Agent-sizing.** One session. ✔

---

### #854 — Fix duplicate _MAJOR_ELECTION_RE: strict election allowlist is dead code

**Labels:** `area:discover-ranking`, `type:bug`, `priority:p2`, `needs-agent`, `good-first-agent-task`

**Problem.** `utils/futures_highlights.py` defines `_MAJOR_ELECTION_RE` twice — a strict country+office allowlist at `:199–219` and a much looser keyword set at `:319–329`. The second assignment wins at import, so the documented allowlist behavior (CLAUDE.md, gotcha #80) is dead code and the −30 `FOREIGN_LOCAL_ELECTION_PENALTY` under-fires. (`FOREIGN_LOCAL_ELECTION_PENALTY` is also defined twice, `:221`/`:253` — same value, harmless, clean up anyway.)

**Scope.** In: decide intended semantics (the strict regex matches gotcha #80's documented intent), delete the other, run both regexes against the last 90 days of politics-category market names and attach the flip-count table to the issue; check whether `tests/test_futures_highlights.py` asserts the loose behavior and fix accordingly. Out: changing penalty values; new election patterns.

**Acceptance criteria.**
- [ ] One `_MAJOR_ELECTION_RE`, one `FOREIGN_LOCAL_ELECTION_PENALTY`
- [ ] Behavioral test: a named obscure foreign election gets −30; a US presidential market does not
- [ ] Flip-count table attached (how many markets change classification)

**Verification (measured).** `python3 scripts/audit_feed_quality.py` before/after (no regression in @20 metrics; expect possible improvement in category mix); flip-count via `GET /api/admin/query` on politics market names.

**Files.** `backend/app/utils/futures_highlights.py`, `backend/tests/test_futures_highlights.py`.

**Relationships.** Relates gotcha #80 (doc) — update the gotcha text in the same PR if semantics change. Backlog source: none needed (bug, not strategy); note in `docs/gotchas-reference.md` instead.

**Agent-sizing.** One short session. ✔

---

### #855 — Doc-drift PR: reconcile CLAUDE.md/docstrings with shipped behavior (9 items)

**Labels:** `area:admin-ops`, `type:docs`, `priority:p2`, `needs-agent`, `good-first-agent-task`

**Problem.** Nine places where docs contradict shipped code, enumerated with citations in `docs/unified-strategy-2026-06.md` §1.3 (category base scores; "exact-string only" cross-source matching; interestingness "scaffold"; demotion thresholds; "7 phases"; `event_registry.py` ±4h docstrings; cap-at-100 comment; backlog "[blocked] #482" vs closed; backlog "No prior App Store submission attempted" vs #678). Agents and contributors build from these texts; CLAUDE.md says they OVERRIDE default behavior, which makes staleness actively harmful.

**Scope.** In: the 9 ledger rows, one PR; prefer referencing constants over copying numbers (e.g., "see `CATEGORY_BASE_SCORES`"). Out: any behavior change.

**Acceptance criteria.**
- [ ] All 9 ledger rows fixed; CLAUDE.md numbers match code or reference it
- [ ] `python3 scripts/audit_backlog_github_sync.py --dry-run` shows no new drift warnings for the touched backlog lines

**Verification (measured).** The sync audit output (read-only, `docs/github-workflow.md:123–129`); spot-grep that CLAUDE.md no longer contains the stale literals (e.g., "geopolitics 55").

**Files.** `CLAUDE.md`, `docs/backlog.md`, `backend/app/services/event_registry.py` (docstrings only), `docs/gotchas-reference.md`.

**Relationships.** Relates #678, closed #482, closed #440 (the three status corrections). Backlog source: housekeeping; no backlog line needed.

**Agent-sizing.** One short session. ✔

---

### Extend-comments for existing issues (paste as comments — not new issues)

**E-596 (comment on #596):**
> Concrete mechanism proposal from `docs/unified-strategy-2026-06.md` §6.2d: (1) export labeled rows via `scripts/export_discover_labeled_dataset.py` with reliability weights from honeypot/agreement metadata (#849); (2) hill-climb `InterestingnessWeights` (`utils/market_interestingness.py:23–31`) with `scripts/calibrate_interestingness.py` against the export, **stratified by reviewer cohort** — kid labels weight only clarity/boring/image axes within kid-safe categories, adult + email/curator ground truth own politics/geopolitics/economics (see strategy §10 tension resolution); (3) ship via the existing Redis keys the feed already reads (`interestingness:blend_weight`, per-market `interestingness:{id}` from `precompute_interestingness`), bounded by the existing `pre_blend+15` cap (`routes/feed.py:5024`); (4) before/after on the same gold set per this issue's acceptance criteria. Baseline prerequisite: #848's on/off measurement — without it, weight deltas are uninterpretable. Verification stays as written here, plus `python3 scripts/evaluate_discover_label_gold_set.py` rows in `discover_label_eval_runs`.

**E-678 (comment on #678):**
> Two pre-resubmission additions from strategy §7.3: (1) unembed the Watch app for 1.0 (a Watch crash rejects the whole submission — `docs/app-store-launch-plan.md:64–70`; re-embed in 1.1); (2) drop visionOS from SUPPORTED_PLATFORMS until tested on hardware (`:72–77`). Both reduce reviewer surface for round two. Round-one feedback was compliance-shaped (account deletion, sign-in) — 5.3.4 remains unraised; keep the Guideline 4.7 defense ready as written in the launch plan.

**E-804 (comment on #804):**
> Decision needed (`needs-user`): path 3 (create events for NCAAB small conferences from ESPN) is the only path that converts ~2,148 KXNCAAMBTOTAL outcomes to score-resolvable — but it permanently widens the event-creation surface to conferences The Odds API doesn't cover. Options: (a) approve small-conference ESPN event creation (scoped task, uses `services/event_registry.py` `find_or_create_event` with espn claims); (b) accept these as unresolvable (`is_winner=NULL`, excluded — consistent with the #845 authority ladder). Throughputs for paths 1/2/4 are marked UNVERIFIED in this issue — measure with two weekly snapshots of `GET /api/admin/query?sql=SELECT fm.source, COUNT(fo.id) FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id WHERE fo.resolution_source='pass2_guess' AND fm.event_id IS NULL GROUP BY 1` before deciding to build anything new.

**E-805 (comment on #805):**
> Concrete commitment for the biggest bucket: the 1,357 women's-NCAAB outcomes are pure our-bug ("ESPN has the scores — the sync just didn't cover these events"). Plan: one-time targeted backfill using the existing `_backfill_box_scores` `priority_calibration` mode, after first answering this issue's own open question — how many of the 13K events have `espn_id`? `GET /api/admin/query?sql=SELECT COUNT(*) FILTER (WHERE espn_id IS NOT NULL), COUNT(*) FROM events e WHERE e.home_score IS NULL AND e.status IN ('completed','closed') AND EXISTS (SELECT 1 FROM futures_markets fm WHERE fm.event_id=e.id)`. Events without `espn_id` route through the ESPN ID backfill that commit `aae4f9e0` fixed. Verification: this issue's outcome count via the same query trending to <1,000, and is_winner coverage on `GET /api/admin/backfill-winners/status`.

**E-826 (comment on #826):**
> Step-2 measurement plan (split "not ingested" vs "doesn't exist upstream"): for one full MLB day, list our events, then check the raw Kalshi `GET /events?series_ticker=KXMLBGAME` and Polymarket Gamma responses for that date; classify each of our events as {source has market & we ingested, source has market & we missed, source has no market}. Repeat for one NBA + one NHL day. This converts the issue's "horrifying" 17% into an actionable split: the middle bucket is our residual bug (post-`ebe630c5`/`d0b7fda0`), the last bucket bounds what coverage can ever reach — which should then become the alert threshold (e.g., alert at <0.8× upstream-possible coverage, not <100%). Trend via the event-level coverage endpoint (commit `a082d1c6`), rendered on the Correctness Console (#847).

**E-841 (comment on #841):**
> From strategy §5.4: point the free **cron monitor** at `match_prediction_markets` (15-min beat; its silent death is the highest-blast-radius scheduled failure — link rate decays within hours). The **uptime monitor** dependency is already satisfied: #506 is closed and `GET /health` exists (`routes/health.py:43`, plus `/health/ready` at `:90`) — point it there now. The #847 Correctness Console renders threshold states, and the alert *thresholds* to wire later are: market-level winner coverage <100%, pass2 inflow >0/day (#806), MCE >10pp at N>100, Tier-1 event-level source coverage drop (#826), grid column sums outside 90–110% (`GET /api/admin/audit/all`).

**E-454 (comment on #454):**
> Add one report to the set: the A1 activation metric — % of new sessions recording ≥5 `prediction_submit` OR ≥3 `feed_card_action(detail_click)` within 7 days, by first-touch cohort and platform. This is the readout metric for the cold-start work (#850/5b) and is computable both in GA4 (prediction_submit is already a key event) and first-party (`user_predictions` + `discover_interactions` by session_id) so it survives ad-blockers. Definition source: `docs/unified-strategy-2026-06.md` §4.4.

**E-490 (comment on #490):**
> Sequencing note from strategy §8.2: hold this behind the correctness exit gates (winner coverage 100%, pass2 inflow 0×14d, all N>100 categories ≤10pp MCE, Tier-1 coverage ≥90%). A user-facing confidence badge computed from a pipeline that currently reads 22.7pp MCE on hockey would put our weakest claim on every card. Keep `needs-user` for the visual-treatment decision, but the real blocker is upstream correctness — suggest adding `blocked` referencing #738.

---

## 4. Critical path — the issues that unlock the most, in order

1. **#806** (pass2 inflow audit, P0) — unblocks: #845 (its CI guard needs the writer identified), and makes #754's drain non-Sisyphean. Smallest issue with the largest downstream fan-out.
2. **#845** (authority ladder) — unblocks: #754 close → thereby #804/#805/#816/#802/#803 closes; makes #738's acceptance checkable; protects every future resolved row.
3. **#683** (Kalshi snapshot history, P0) — unblocks: #651 (348K cal_prob backfill), the hockey/golf MCE targets inside #738, and #818's NULL-cal_prob diagnosis.
4. **#698** (Polymarket settlement sync, P0) — unblocks: #738's Polymarket spot-check criterion; shrinks #754's Polymarket bucket (4,848 all-losers + 1,347 midrange named in-issue).
5. **#846 → #847** (status endpoint + Correctness Console) — unblocks: the §8.2 exit-gate *measurement* itself, E-841's alert thresholds, and the operating cadence for items 1–4 (you can't manage a hill-climb you can't see).
6. **#678** (App Store resubmission, needs-user) — unblocks: #671 rollout breadth → #849 (kid labels) → E-596 → eventually #597. The entire human-signal flywheel queues behind a checklist that is waiting on Alex, not on code.
7. **#671** (reviewer access) — unblocks: #849, #600's design pass having a real second persona, and the `docs/discover-labeling.md:196` label-volume thresholds.
8. **#848** (blend baseline) — unblocks: E-596 being interpretable; potentially saves the whole tuning effort if the blend turns out net-negative.

## 5. Explicit NOT-now list

| Strategy item | Why premature | Promotion trigger | Lives meanwhile |
|---|---|---|---|
| Calibration sample 10–20x via spreads/totals resolution (strategy §9 H2) | The resolution pipeline is mid-surgery (#845, #754); adding 10–20x volume through a corrupted path multiplies cleanup | #845 shipped + #651/#683 done + `GET /api/admin/backfill-winners/status` green at 100% market-level coverage | `docs/backlog.md` "Subproject F: Outcome count expansion" (already there, :848–855) |
| Learned reranker (#597) | Already correctly `blocked`; thresholds unmet | 1,000–2,000 single-card + 500+ pairwise labels with agreement data (its own body; `docs/discover-labeling.md:201–203`) — measure via `GET /api/admin/query` count on `ranking_judgments`/`discover_pairwise_labels` | Stays open + `blocked` (no change) |
| Widget "My Number", Mac menu-bar ticker, Watch pinned complication, Siri intent (strategy §7.2) | App not yet approved (#678); zero crash reporting (#839) means new surfaces ship blind; Watch is being *removed* from the 1.0 submission | #678 approved AND #839 shipped | New `[idea]` lines under "iOS App — Web Parity & Polish" (§6 below) |
| Admin IA consolidation (Health/Correctness/Discover/Labels/Inbox/Catalog regroup, strategy §5.3) | #847 should prove the jobs-to-be-done pattern on one page before a 12-page reorganization; endpoint catalog (backlog item 24) is the real prerequisite | #847 shipped + backlog item 24's endpoint catalog produced | `docs/backlog.md` item 24 (already there, :1168–1182) |
| Per-user calibration / public calibration API (strategy §9 H3) | Depends on correctness exit gates and on user volume that doesn't exist pre-launch | Exit gates + post-launch DAU baseline | New `[idea]` line in backlog Strategic section (§6) |
| Closing-line recoverability moat audit (strategy §10 item 5) | Valuable skepticism, zero product urgency | Next quarterly strategy review | Strategy doc §10 (where it is) |
| Cross-source `canonical_market_key` backfill + paraphrase-match audit (Tier 0.25) | Real, but behind correctness and labeling in leverage; no open issue owns it yet | Category-page duplicate complaints recur OR `find_cross_source_markets` match-rate audit (backlog Tier 0.25 step 1) shows <50% pairing | `docs/backlog.md` Tier 0.25 (already there, :174–188) |
| Kid-labeler native parity | Web flow first; note #605 (native labeling parity) is already CLOSED, so the native substrate exists — the kid variant is a follow-up screen, not new plumbing | #849 pilot hits its 2-week volume/agreement bar | New `[idea]` line in the backlog 0u labeling block when triggered |

## 6. Backlog deltas (exact edits to docs/backlog.md)

Per `docs/github-workflow.md:92–104` — issue links added on promotion; closed-issue lines updated in the same change; markers from the canonical set.

**(a) In `## Active GitHub Execution Queue` — fix two stale lines:**
```md
- [shipped] Redesign first 30 seconds — modal removed, contextual swipe teaching. Issue: #482 (closed Jun 2)
```
(replaces the current `[blocked] Redesign first 30 seconds — hero headline. Issue: #482` line at :42)

```md
- [active] App Store RE-submission — round-one rejection feedback addressed; verify sign-in + account deletion on device, strip Watch/visionOS. Issue: #678
```
(replaces `[blocked] Finish App Store submission checklist. Issue: #445` at :23 — #445 is CLOSED in the export; #678 is its successor, so the stale line goes)

**(b) In `## Active GitHub Execution Queue` — add new lines on issue creation (fill #s when filed):**
```md
- [ready] Resolution authority ladder: structural never-guess enforcement + CI guard. Issue: ##845 (depends #806)
- [ready] Fix backfill-winners/status timeout via Celery precompute. Issue: ##846
- [ready] Correctness Console admin page (composes existing correctness endpoints). Issue: ##847
- [ready] Interestingness blend on/off production baseline. Issue: ##848 (needs-user)
- [ready] Kid-labeler profile: content gate, restricted axes, honeypots, agreement. Issue: ##849 (blocked by #671)
- [ready] Cold-start signal: fast-lane young-session swipes + first-page category probe. Issue: ##850
- [ready] Discover chip-row category card + activation events. Issue: ##851 (blocked by ##850)
- [ready] Persist story_key column; caps + dismiss propagation read it. Issue: ##852
- [ready] discover_llm v2: entity slugs, stakes, kid_safe. Issue: ##853
- [ready] Fix duplicate _MAJOR_ELECTION_RE dead-code allowlist. Issue: ##854
- [ready] Doc-drift reconciliation PR (9 items from strategy §1.3). Issue: ##855
```

**(c) In `## Current Priority: Calibration & Data Quality` — amend the "Open items" list:**
```md
0. **Enforce resolution authority ladder** — structural never-guess policy + CI guard; prerequisite for closing #754 and its child buckets. Issue: ##845. Strategy: docs/unified-strategy-2026-06.md §8.1.
```
(insert before current item 1; renumber or leave as item 0)

**(d) In the `0u` Discover block, update the 0u-N1 line (`:360–369`):**
```md
**0u-N1. Wire market_interestingness into feed ranking — STATUS CORRECTION (Jun 9):** the blend SHIPPED via Redis (#440 closed, default weight 0.2, feed.py:5012–5028) but steps 1–2 (label calibration) were skipped. Remaining work: measured on/off baseline (Issue: ##848), then label-calibrated weights (Issue: #596 — see mechanism comment there). Do not tune weights before the baseline exists.
```

**(e) Under `## iOS App — Web Parity & Polish`, add ideas (NOT promoted):**
```md
| iOS-W1 | [idea] Widget "My Number": pinned market / followed-team probability on systemSmall. Trigger: #678 approved + #839 shipped | Green |
| iOS-W2 | [idea] Mac menu-bar probability ticker (extends Bain_LuckApp pollLiveGames). Same trigger | Green |
| iOS-W3 | [idea] Watch pinned-market complication; re-embed Watch in 1.1. Same trigger | Green |
| iOS-W4 | [idea] Siri "Get Probability" App Intent over /api/events/search. Same trigger | Green |
```

**(f) Under `## Strategic`, add:**
```md
### Strategy Document (Jun 9, 2026)
Operating strategy: `docs/unified-strategy-2026-06.md`. Roadmap reconciliation: `docs/issue-roadmap-2026-q3.md`. Correctness exit gates for the 60/40→40/60 rebalance are defined in strategy §8.2 and rendered by the Correctness Console (Issue: ##847).
- [idea] Per-user calibration + public calibration API/badges (strategy §9 H3). Trigger: exit gates + post-launch DAU baseline.
```

**(g) On closing #803 (if the close-as-absorbed recommendation is accepted):** update the Calibration workstream's open-items list in the same commit, replacing the 803 bucket mention with: `KXNBAMENTION (298) accepted as unresolvable under the authority ladder; excluded from calibration denominators.`

## 7. Adversarial self-audit

**(a) The three weakest verification plans, and the instrumentation that fixes each:**

1. **#847 (Correctness Console)** — "two weeks of health checks run from the console + one regression caught" is observational, not a clean signal; nothing fails if the console is merely ignored. *Fix:* E-841's monitors ARE the instrumentation — once the cron/uptime monitors and (later) threshold alerts fire from the same computations the console renders, "console correctness" becomes "alert fired when it should have," which is measurable. No additional issue needed beyond E-841; if its two free monitors prove insufficient, file a follow-up for Sentry alert rules via the existing `scripts/setup_sentry_alerts.py` (gotcha #86) — that script is real and idempotent.
2. **#851 (chip-row card)** — the A1 readout depends on E-454's GA4 reports, which sit `in-progress` (their former blocker #453 is closed, so they are executable but not done). If GA4 reporting slips, #851 ships with no readout. *Fix:* the first-party fallback is already in the A1 definition (`user_predictions` + `discover_interactions` by session_id); make it primary, GA4 secondary — concretely, add a small SQL rollup to the **existing** `GET /api/admin/discover-engagement` endpoint (`routes/admin_engagement.py`) reporting A1 by week. That slots inside E-454's scope as written; if the endpoint owner disagrees, it becomes a one-session `area:admin-ops`/`type:quality`/`priority:p2` instrumentation issue.
3. **#849 (kid labeler)** — "zero unsafe cards in 200 sampled" is a manual audit, and honeypot hit-rate only works if the honeypot pool is genuinely unambiguous. *Fix:* the honeypots themselves are the instrumentation, but their quality needs a check: seed the first batch only from cards with an existing **unanimous adult judgment** in `ranking_judgments` (query: same market_id, ≥2 reviewers, same `overall_label`), measurable via `scripts/analyze_ranking_judgments.py`. That constraint is now written into #849's scope ("known-kill / known-love" sources); if adult double-labeled cards number <30, run one adult overlap session first — which #671's agreement-checks bullet already anticipates.

**(b) Where the roadmap's ordering contradicts the strategy doc — reconciled:**

The strategy's allocation argument (§8.2) says 60% correctness, yet the critical path's items 6–7 (#678 → #671) are distribution/labeling, and §2 of this roadmap puts #848/#850/#851 (growth-and-feed work) inside the first wave. Reconciliation: the 60/40 split allocates *agent engineering capacity*, and the apparent contradiction dissolves on inspection — #678 and #671's head-of-line work is `needs-user` (Alex's checklist, near-zero agent hours), #848 is an audit run, and #850 is one session. The correctness lane (items 1–5) still consumes the clear majority of engineering time. One genuine tension remains: #853 (discover_llm v2) is content-understanding work the strategy placed in Horizon 2, pulled earlier here because #849 wants `kid_safe`. Resolution: #849 ships with rules-only gating (its rules 1–3 stand alone, as its body states); #853 stays priority:p2 and slips to Q4 without blocking anything — the dependency is soft and is documented as such in both issue bodies.

**(c) The single biggest way this roadmap could be locally reasonable but globally wrong:**

It assumes the binding constraint is *internal* (correctness debt, label volume, operator visibility) when it may be *external*: nobody is using the product, and no amount of calibration integrity changes that — a perfectly-resolved 232K-outcome history with zero DAU is a beautifully audited ghost ship. The roadmap spends roughly one issue (#850/#851) on demand generation. **Detection:** instrument the disconfirming signal now — weekly A1 (per E-454) plus raw new-session counts from `discover_interactions` (`GET /api/admin/query?sql=SELECT DATE(created_at), COUNT(DISTINCT session_id) FROM discover_interactions GROUP BY 1`). Decision rule, set in advance: if four weeks after #678's approval new-session volume is flat and A1 is <5%, the Q4 plan inverts — growth/distribution becomes the 60 and correctness the 40, regardless of whether the exit gates have been hit. The strategy's own thesis (§9: calibration is the trust engine *for users who show up*) makes this inversion legitimate rather than a betrayal of it.

---

*Process note: when filing, use `python3 scripts/claim_issue.py <N> "In Progress" --owner "<thread>"` before touching files (workflow :107–113), and run `python3 scripts/audit_backlog_github_sync.py --dry-run` after the §6 backlog edits land.*
