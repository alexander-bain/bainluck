# Instant Answers — Program Strategy

**Written:** 2026-07-06 by Fable, in live session with Alex. This is the canonical strategy doc for the Instant Answers program. Triage (Lane 1), Triage 2 (Lane 2), and Ops threads should treat this as a first-class sequence source alongside `.claude/handoff/SEQUENCE.md`. Repo hygiene: the first code session that touches the tree should commit this doc and link it from `docs/backlog.md` under a new "Instant Answers" workstream.

---

## 1. The problem, in the founder's words

> "When I want to look up something like 'What team will LeBron James go to next?', I find myself wanting to go to Kalshi instead of my own product."

That reflex is the whole strategy. Kalshi wins that moment on three things: **certainty** (Alex knows the market exists there), **routing** (Google and habit take him there), and **directness** (the market page *is* the answer). Bain Luck loses despite holding structurally better cards:

- **Aggregation** — we blend Kalshi + Polymarket + sportsbooks + models into one probability. Any single-source page is strictly worse information.
- **Semantic grouping** — `group_id` turns ten sub-markets into one question. Kalshi shows the user a ticker list; we can show an answer.
- **Probability-first UI** — no order books, no bid/ask, no trading clutter. Our target user wants the answer, not a position.

**North star:** for any question prediction markets can answer, Bain Luck answers it faster and more clearly than the source markets themselves.

## 2. Decisions taken (2026-07-06, Alex)

| Decision | Call |
|---|---|
| Scope | **All categories, entity-first.** LeBron, Fed chair, and Best Picture use the same mechanism. Do not build sports-only plumbing. |
| Primary wedge (v1) | **Search-as-answer.** Typing "lebron" into Bain Luck must show the answer (e.g. Lakers 62%, Cavs 18%…) directly in typeahead/results — not a link list. |
| North-star metric | **The Alex test** — does Alex stop opening Kalshi? Operationalized in §5; the time-to-answer benchmark is the between-interview instrument, not the goal. |
| Lane priority | **Split lanes.** Calibration recovery keeps Lane 1 (A-lane). Instant Answers code runs through Lane 2, which graduates from read-only to a code lane after the Phase-0 baseline. File-disjointness rules in §6. |

## 3. Why we lose today — four failure classes

Every lost question falls into exactly one bucket. Phase 0 measures the mix; later phases each attack one bucket. All future work items should name their bucket.

1. **MISSING** — the market isn't in our DB, or exists but isn't linked/grouped (bad `group_id`, no `llm_sport_category`, orphaned sub-markets). We poll ALL Kalshi/Polymarket markets, so true ingest gaps should be rare; expect most MISSING to be *linking* failures. This is the same semantic-matching muscle as the sports L1–L4 layers — extend the hill-climb discipline, don't invent a new one.
2. **UNFINDABLE** — ingested, but `/api/events/search` misses it or ranks it poorly for the natural query. Root causes to expect: no entity-alias handling ("LeBron" vs market names like "Where will LeBron James play in 2026-27?"), FTS weighting tuned for events not futures, no question-shaped query handling.
3. **SLOW** — findable but the path is slower than Kalshi's (latency, clicks, page weight).
4. **UNREADABLE** — found fast, but the answer isn't instantly graspable (user must assemble it from outcome rows; multi-candidate binaries not normalized — gotcha #23; no clear leader/mover statement).

## 4. Phases

### Phase 0 — Baseline (STAGED: Lane 2 Queue L2-33, 2026-07-06)
Read-only. A 25-question benchmark of entity-shaped questions across all categories. Per question: coverage (in DB?), findability (search rank + latency), time-to-answer traces on bainluck.com vs kalshi.com (steps + seconds to *seeing* the probability), readability. Output: per-question table, bucket counts, 5 worst traces. The benchmark set is committed at `.claude/handoff/instant_answers_benchmark_v1.md` and is **frozen** — every future re-measure uses the same 25 questions so the trend is real. Phase 0's bucket mix sizes Phases 1–2.

### Phase 1 — Make existing search functional + consumable (the wedge; Lane 2 code)
**Framing correction (Alex, 2026-07-06): this is NOT a new feature.** Kalshi doesn't have an "answers" feature — it has a functional search box and a market page that's easy to consume. Bain Luck already has both surfaces, and the data is already in the payload: `/api/events/search` futures results carry `top_outcomes` (top 5 with probability + 24h movement, `_format_futures_for_search`). Phase 1 is a **repair-and-polish list on the existing search → market page path**, not a new surface. Do not invent new page types, card systems, or "answer" abstractions.

The two repair classes:
1. **Consumable at first contact** — the probability must be visible the moment the market appears. Today the typeahead returns futures suggestions with name only (no probabilities); the number should be in the dropdown row and the search-results row, one tap from the detail page. Data-plumbing is trivial; this is payload + rendering work.
2. **Functional for person/entity queries** — "lebron", "where will lebron go" must find and rank the right grouped market. FTS + aliases + fuzzy already exist; fix only what Phase 0 proves broken (question-scaffold handling, person aliases, futures ranking/dedup). Do NOT preemptively build alias infrastructure.

Detailed slice-by-slice spec: `.claude/handoff/instant_answers_phase1_spec.md`. Display gotcha that binds all of it: independent candidate binaries need normalization (gotcha #23) before showing a distribution.

Acceptance: on the frozen benchmark, every non-MISSING question shows its probability within the search surface (no navigation) — UNREADABLE and UNFINDABLE buckets go to ~0 for covered questions.

### Phase 2 — Coverage & linking (bucket: MISSING; lane depends on files)
Driven entirely by Phase 0's MISSING list. Expected work: `group_id` backfill gaps, cross-source pairing misses (`cross_source_matching.py`), category/entity metadata gaps. Where fixes touch cal-owned files (`prediction_market_matching.py` is shared territory — check LANE-MAP.md), route through Lane 1's queue instead of Lane 2. Add an audit: `scripts/audit_instant_answers.py` mirroring the L1–L4 pattern — coverage% and findability% on the benchmark, runnable by any thread. **Any benchmark question that SHOULD match but doesn't is a bug, not a feature gap** — same philosophy as the matching layers.

### Phase 3 — Speed (bucket: SLOW; Lane 2)
Targets: typeahead answer p50 < 150ms server-side; full search results p50 < 400ms; entity answer visible < 2s from first keystroke on a cold phone. Likely work: cache the answer-card payloads (the grouped-market → top-outcomes projection is precomputable, same pattern as `precompute_interestingness`), FTS index work (Postgres-specific, and per the standing search rule: prove it improves real traces before adding triggers/table rewrites).

### Phase 4 — Entity pages (evidence-gated; Lane 2)
A page per person/topic aggregating every market about them — **only if** the benchmark/interviews show that search + the existing futures detail page still lose after Phases 1–3 (i.e. users need a destination, not just an answer). Team pages already exist; don't duplicate them. Default assumption per the Phase-1 framing correction: no new surfaces unless the evidence demands one. **Guardrail (standing Alex rule):** answer surfaces show the BLENDED probability only — no source-comparison/divergence UI; a divergence is a data-quality bug to fix, not a feature. Movement statements ("Lakers up 12 pts this week") reuse the deterministic explanation machinery from feed reasons / #871 line-move attribution, which gates on explainability.

### Phase 5 — Distribution (later; partially Alex-gated)
Programmatic, indexed, question-shaped pages ("Where will LeBron James play next season?") so Google routes new users to Bain Luck instead of Kalshi. Do NOT start until Phases 1–3 hold on the benchmark — sending Google traffic to a losing experience wastes the one first impression. SEO architecture choices (URL scheme, indexation strategy, canonical vs Discover cards) are **Alex-gated** — stage as a decision packet, not code.

### Phase 6 — Habit (later)
Follow entities; movement alerts ("LeBron→Lakers jumped 12 pts"). The push-notification foundation exists (`routes/notifications.py`) but is explicitly not a shipped scheduling/preference system — Phase 6 is what finally justifies building that flow. Sequenced last: alerts only help after the answer surface is worth returning to.

## 5. The Alex test — operationalized

The north star is subjective, so make it cheap and regular:

- **Cadence:** after each phase ships (and at least every 2 weeks while the program is active), Ops stages a **10-question MC interview** for Alex (his preferred format): 5 questions from the frozen benchmark + 5 fresh "what did you actually want to look up this week" questions. For each: "Did you try Bain Luck first? If not, why — MISSING / UNFINDABLE / SLOW / UNREADABLE / habit?"
- **Instrument between interviews:** the frozen 25-question time-to-answer benchmark, re-run by Ops each round the program is active — % of questions where Bain Luck is faster than Kalshi, plus bucket counts.
- **Definition of winning:** two consecutive interviews where Alex reports reaching for Bain Luck first on every answerable question, with "habit" as the only loss reason. Then Phase 5 (distribution) unlocks — the product has earned new users.

## 6. Operating model (for the threads)

- **Lane split:** Lane 1 (A-lane) = calibration recovery until its blocks clear (#116 → CLOB resolve → score recovery). Lane 2 = Instant Answers code. **File ownership:** Lane 2 owns `routes/events.py` (search), new entity/alias modules, frontend search + entity components. Lane 1 owns `precompute_calibration.py`, `backfill_winners.py`, `kalshi.py`, `prediction_market_matching.py`. Anything shared → serialize through Lane 1's queue. Update `LANE-MAP.md` when the first Phase-1 queue is staged.
- **Ops:** owns the benchmark re-runs, the Alex-test interviews, and live-proofs of shipped slices.
- **Staging:** Fable-successor staging threads should stage Phase slices in order, sized to one session, with the standard gates (CI green, live proof on bainluck.com, #887 journal, benchmark re-measure in the same or next ops round).
- **Standing guardrails that bind this program:** blended probability only on answer surfaces (no source compare); **NO gambling enticements — no odds anywhere unless expressed as a probability (Alex, 2026-07-06, D1 in `docs/decisions-2026-07-06.md`; the positioning thesis: parity on the answer, zero compulsion to gamble)**; margin-of-victory/turnout markets stay suppressed on discovery surfaces; no LLM calls in request paths; light mode design tokens; 3 GA4 hooks on every new page; quota guard untouched (this program is Kalshi/Polymarket/DB work, not Odds API).
- **Alex-gated items:** Phase 5 SEO architecture; any new paid data source; any homepage/navigation restructure.

## 7. Sequencing summary

```
NOW        Phase 0 baseline (L2-33, staged)          Lane 2, read-only
NEXT       Phase 1 search-as-answer slices 1–4       Lane 2, code
PARALLEL   Cal recovery: #116 → CLOB resolve         Lane 1 (unchanged)
THEN       Phase 2 coverage fixes (sized by P0)      Lane 2 (or 1 if cal files)
THEN       Phase 3 speed → Phase 4 entity pages      Lane 2
GATED      Phase 5 SEO (Alex) → Phase 6 alerts       after the Alex test is won
```

The program is done when the founder's reflex flips — and stays flipped.
