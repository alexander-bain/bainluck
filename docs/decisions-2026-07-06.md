# Binding Decisions — 2026-07-06 (Alex × Fable judgment session)

Eight decisions taken by Alex in structured interview, 2026-07-06. These are **binding** on all lanes (Triage/Triage 2/Ops/staging). Each section states the decision, the rationale in Alex's terms, and the routing. Referenced from `SEQUENCE.md`; commit this doc in the next code session.

---

## D1. Product positioning: NO gambling enticements — probabilities only (STANDING RULE)

**Decision (Alex, verbatim intent):** Bain Luck should have *zero* enticements to gamble. Kalshi and Polymarket are full of them — the product thesis is that if you want to see probabilities *without feeling compelled to gamble*, Bain Luck is the great product. **"We shouldn't really have 'odds' anywhere if they're not in the form of a probability."**

**What this binds:**
- No American odds (−150/+130), decimal odds, or spread-style prices anywhere in the UI. Probability (%) is the only quantity format on any surface.
- Audit + sweep: `american_odds` fields currently flow through payloads and UI (search top_outcomes, detail pages, odds tables). Payloads may keep the fields (API consumers), but rendered surfaces drop them. Book/market mechanics language ("bet", "payout", "odds") leaves UI copy.
- This joins the blend-only rule as a top-tier design-system constraint. Add to `docs/design-system.md` voice/values section when touched.

**Routing:** product queue ("no-odds sweep") — sequenced after L2-35/36; Alex-directed so it runs despite the pause (see D5 scope). Update `CLAUDE.md` Frontend Design System section when it ships.

## D2. Calibration liquidity methodology: ONE principled rule, not per-source magic numbers

**Decision:** Alex rejected the provisional per-source dollar cutoffs (Kalshi ≥$100 / Poly ≥$10k) as methodologically unprincipled. The exclusion criterion must be **source-agnostic in form**; any per-source numbers must be *derived* from a single shared principle.

**The framework (Fable, per Alex's direction to design it):**
- **Principle:** an outcome belongs in the headline curve iff its market had an **informative price** — evidence that a real counterparty priced it. Not "enough dollars," which is unit- and venue-dependent.
- **Rule form (phase 2):** informative-price = **≥ K distinct trades before close** (K identical across sources; trade-count is unit-free), with the already-shipped phase-1 rule (ever-bid or ever-traded) as the K=1 floor. Where trade counts are unavailable, the fallback is a **shared percentile** rule (e.g., exclude the bottom-X% of traded value *within each source*, same X) — the per-source dollar figure is then a derived artifact, documented as such, not a chosen threshold.
- **Choosing K (or X):** fit empirically — smallest K where included-set calibration plateaus **on both sources with the same K**. If no single K works for both, the criterion is wrong — redesign it, don't fork the numbers.
- **Validation protocol (freeze-then-measure, benchmark-style):** state the rule before measuring; then show for EACH source: MCE(included) < MCE(all); the excluded mass contains the miscalibration (excluded-set MCE ≫ included); and the included curves are stable under ±1 step of K. Publish included/excluded counts (mirrors #940 transparency).

**Routing:** methodology validation = ops/Lane-2 read-only analysis once the volume/trade backfill populates; implementation = Lane-1 code queue after. Supersedes the round-76 provisional cutoffs.

## D3. /calibration default display

**Decision:** well-priced tier is the DEFAULT headline curve; the full everything-included view stays one visible click away, with excluded counts stated on-page. Honest headline, nothing hidden.

**Routing:** ships with D2's implementation queue (calibration route + frontend toggle).

## D4. #940 all-No groups: RESOLVE them — don't define them away

**Decision:** Alex rejected the "terminal state vs backlog" framing: *"Why wouldn't we resolve them?"* The ~7,900 Kalshi grouped events where every held sub-market resolved No are **coverage work**: fetch/ingest the missing winner-candidate markets so each group is complete.

**Honest constraint (gotcha #35):** Kalshi market data ages out ~2–3 months post-settlement. The policy: attempt recovery for every group; a group is marked unrecoverable ONLY after a fetch attempt proves the data is gone, and those get a documented count (same discipline as the poly void floor). needs_backfill continues counting them until attempted.

**Routing:** Lane-1 code queue (candidate #119) after #118 — Kalshi winner-candidate ingestion for all-No groups, liquid-first (~7,237), per-batch commits, aged-out documented.

## D5. Recovery pause: NOT lifted — and the Done bar is redefined

**Decision:** calibration is not "fixed" while the public /calibration page shows janky charts (datagolf's systematic offset, golf's high-end hook, totals' noise). Internal MCE wins don't lift the pause; **the public page has to look credible**.

**Operationalized (Alex chose eyeball + guardrail):** each ops cycle posts fresh screenshots of every /calibration chart; the pause lifts when (a) Alex says it looks credible AND (b) no source/category with n≥1,000 shows systematic bias >5pp across adjacent buckets. Both conditions, not either.

**Scope note:** the pause blocks staging *new* product surfaces (#883 etc.). Explicitly Alex-directed programs run regardless: Instant Answers (running), the D1 no-odds sweep.

**Routing:** ops standing item from round 85 (screenshot pack + guardrail table). The golf/datagolf diagnosis (D8) is now on the pause-lift critical path.

## D6. #883 futures-detail: PARITY-FIRST, not a redesign concept

**Decision:** the bar is parity with Kalshi/Polymarket on the basics — *"understanding the basic odds of an outcome, and how it's trended over time."* Today we're worse: less detailed, and often showing bogus answers ("Candidate A 100%"). Reach parity, then find small ways to be better. Combined with D1, the differentiator is: **as good at the answer, with zero gambling enticements.**

**The parity checklist (audit against Kalshi + Polymarket detail pages):**
1. Correct current probability — no placeholder outcomes, no un-normalized 100% artifacts (extend the L2-34 normalization/placeholder fixes to detail surfaces).
2. Probability history chart at parity quality (range, granularity, resolution clarity).
3. Complete, readable outcome list (all real candidates, ranked, movement).
4. Market metadata parity: resolution date, what resolves it, volume/activity signal (as probability-relevant context, not gambling bait — D1).
5. Then betterments: the #871 deterministic movement sentence, related markets, blend quality. Blend-only rule unchanged.

**Routing:** stage as an AUDIT first (screenshot side-by-sides vs Kalshi/Poly on ~10 markets → gap list), then fix queues. Gated by D5 pause EXCEPT the bogus-answer fixes (those are data-quality, always in scope).

## D7. #990: run the bigint migration THIS WEEK

**Decision:** low-traffic window this week, using the round-84 runbook (manual psql, not Alembic — gotcha #31). Volume feeds search ranking, which Instant Answers now depends on.

**Routing:** ALEX-NEXT top item once the runbook posts; ops verifies the frozen market's volume moves after.

## D8. Chart-jank diagnosis: promoted to the pause-lift critical path

Per D5, the datagolf/golf/totals anomalies are now blocking. Diagnosis hypotheses to test (read-only first, verify-before-regrade):
- **datagolf** (whole curve above diagonal): test the void-filter survivorship hypothesis — excluding did-not-play (mostly losers) inflates survivors' actual win rate. If confirmed, the fix is methodological (denominator/display), not a re-grade.
- **golf category** (predicted 95% → actual 36%): row-trace the high-bucket cohort — stale/late capture vs resolution linkage (gotcha #14) vs genuine losses.
- **totals 75%→0% bucket:** count it — if n<~30 it's noise, document; if not, check for a residual inverted class.

**Routing:** ops round 85 headline items; findings route to Lane-1 code queues only with row-level proof.

---

*Also standing from this session's earlier decisions: Instant Answers program (`docs/strategy-instant-answers.md` — all-categories entity-first, search-as-answer, the Alex test, split lanes; Phase 1 framing: repair, not feature).*
