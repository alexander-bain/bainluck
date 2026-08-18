# Search Methodology Audit — do the instruments measure the right things?

*Branch `codex-adhoc/search-audit` from frozen `a6665b14`, worktree `search-audit`, 2026-08-18. Artifacts only, read-only. Same rigor as `MATCHING_METHODOLOGY_AUDIT.md` and `METHODOLOGY_AUDIT.md`: every constant / threshold / ordering assumption as CHOSEN / ALTERNATIVE / EVIDENCE (code cite + sentinel/log numbers where available) / VERDICT (sound | suspect | wrong) / the experiment that settles it. Specimen set = 44-probe gold set, flow sentinel reads, typeahead warmer, and the answer-first pack that photographs the dropdown.*

*The system is well-instrumented — the question is whether the instruments are pointed at the right sky.*

---

## How to read

The search audit is not a recall chase. LAT-P059 (ruling 073) proved the score can move two probes (39→41/44, MRR 0.891→0.934) with **no code change at all** because three distractors resolved and left the eligible pool. The probe set is frozen, the corpus is live, and the world moves underneath. Every section below has a gate experiment that distinguishes `CORPUS-MOVED` from `REAL`.

---

## Ranked findings (well-instrumented → mis-instrumented)

| Rank | Assumption | Verdict | Specimen | Gate |
|---|---|---|---|---|
| 1 | **Grading gaps as a class — which change classes the gold set structurally CANNOT grade** | **wrong** (green means nothing) | #1867 (MC3 undisriminating, grades MC2 by accident) + #1861 (deployed change moved zero probes) | Grading-gap census SQL (§3) |
| 2 | **Gold-set representativeness — 44 probes vs real distribution + provenance-blocked quantification** | **suspect** (biased + blocked) | Query logs 23.6% sentinel traffic, trending zset ~89% warmer echo (#1916) | Provenance-gated real-distribution census (§1) |
| 3 | **Tier ordering MC0→MC5 + kind market>event>team — is exact-unfolded>prefix>fragment always right?** | **suspect** | Three entity-type inversions (exact team vs prefix market) + never-traded fragment class | Inverted-order probe pack (§2) |
| 4 | **Answer-first contract — what “answer” means and whether the envelope guarantees it per entity class** | **suspect** (photographed but not guaranteed) | Desktop vs phone dropdown both photograph `red sox` now, but only futures with `probability` owes an answer; teams/games/hubs have no answer by definition | Answer-envelope census (§5) |
| 5 | **Fingerprint integrity — ruling 073 per-probe eligible-pool fingerprints, what corpus changes would it miss** | **sound** with caveat | LAT-P059 `39→41/44` quarantined as CORPUS-MOVED; `61de6598` producer blob `46/46 exact` | Fingerprint miss census (§4) |

---

## 1. GOLD SET REPRESENTATIVENESS: 44 probes — how does their distribution compare to real user queries? Caveat: logs 23.6% sentinel, trending zset ~89% warmer echo (#1916) — quantify what CAN be said and what is blocked on provenance.

### CHOSEN

* **44 probes**, frozen 2026-07-06 (`flow_sentinel.py:76` `FROZEN 2026-07-06`, `.claude/handoff/instant_answers_benchmark_v1.md`), each `(natural query, expected_found)` where `expected_found=True` means baseline OK+UNREADABLE (a top result existed) and `False` means UNFINDABLE+MISSING (baseline miss). Appended canary `CANARY_QUERY = "zzqx nonexistent sentinel canary entity 99"` is injected as `expected_found=True` in canary mode to prove detect→evidence→file (`flow_sentinel.py:76/113`). A second set `GOLD_SET_TOP1` (~50 family-phrased queries, Queue #246 `unambiguous correct top-1`) measures **top-1 correctness**, distinct from findability (`flow_sentinel.py:118`).

* **Distribution as frozen:** the 44 are curated to cover the two failure families measured 2026-08-12 21:48Z on v3792 (`search_match_class.py:8` `entity_top_1 30/44, 14 failures, 11 in owned-evidence + fragment classes`): `super bowl`, `world series`, `wwe`, `stranger things`, `british open` → `Brito`, `ai` → `Kaiserslautern`, `ipo` → `Asteras Tripolis`. Entity-type mix is concept-heavy (the Emmys concept won Super Bowl before owned-evidence). Tier coverage is MC0–MC5, largely short queries (1–2 tokens) because typeahead is the triggering surface (`search_match_class.py:42:49` tiers). League coverage is MLB/NBA/NHL/EPL-heavy — prominent sport keys (`search_match_class.py:124` `PROMINENT_SPORT_KEYS` 8 leagues) get within-tier boost.

* **Real-distribution observability is blocked on provenance.** Two blockers proven in #1916: (a) **query logs are 23.6% sentinel traffic** — the flow sentinel's own `/typeahead` reads register as user queries, so raw log counts overstate head queries that the sentinel polls; (b) **trending zset `search:trending:24h` is ~89% warmer echo** — `typeahead_warmer.py:116` `search:trending:24h` — the Redis zset `/typeahead` itself writes on every typeahead, and the warmer's `89%` mode is the warmer echoing its own writes, not users. Both cauterize any “compare 44 to real” until a `provenance=user` flag separates them.

### ALTERNATIVE

Keep 44 frozen as a **canary** for corruption (its job is findability, not representation) and treat real representativeness as a *separate* stratified sample drawn from **provenance-gated** logs/zset tails — e.g., `provenance=user AND NOT sentinel` filtered logs vs `trending` filtered to `warmer_echo=0`. A second alternative is to expand not by adding probes uniformly but by **stratifying on the two axes the scorer cannot tune across** (match class MC0–5, kind market/event/team/concept/hub) — so a class empty in real logs but empty in gold is a known gap, not an average.

### EVIDENCE — code + numbers

`flow_sentinel.py:76/113/118/700` frozen 44 + top-1 set + `_run_search_gold_set` regressions/recoveries/transport (`search_found` `event_concepts|results|futures|futures_families`); `search_match_class.py:8` 30/44 with 11/14 in owned-evidence+fragment; `typeahead_warmer.py:116` trending zset echo `~89%`; logs `23.6%` sentinel (claimed premise, blocked on flag — not re-measured here); `docs/rulings/073-corpus-moved.md` (fingerprint per probe, 39→41/44 quarantined). **What CAN be said:** entity-type mix of 44 is concept+market heavy, query-length mix is short-head, league mix is prominent-league heavy — all *curated to the failure families*, not sampled from logs. What is **blocked:** whether that matches real user length/league/type distribution — any number read off unflagged logs/zset is `sentinel+wamer` admixture.

### VERDICT

**suspect** — not wrong (the 44 were never claimed to be a random sample; they were frozen as a **regression canary** on measured failures), but treated as a representativeness instrument they are biased, and the measurement to correct that bias is **blocked on the provenance flag** (#1916). Until `provenance=user` ships, every sentence of the form “our users search like …” is unfalsifiable on the same corpus that would settle it.

### THE ONE EXPERIMENT THAT SETTLES IT — provenance-gated census, read-only

```sql
-- Real distribution (unblocked) after provenance flag ships:
-- For each of (entity type, tier, league, query length) buckets, compare 44's bucket share to provenance-gated logs' share.
-- Until flag, blocked — report as QUARANTINED and do not publish the comparison.
SELECT
  CASE WHEN query LIKE '%sentinel%' OR provenance='sentinel' THEN 'sentinel_traffic' ELSE 'real' END AS prov,
  COUNT(*) AS n, 100.0*COUNT(*) / SUM(COUNT(*)) OVER () AS pct
FROM query_logs WHERE captured_at > NOW() - INTERVAL '7 days' GROUP BY prov;
-- Expect: sentinel ≈23.6% before flag; after flag, real distribution is prov='real' only.
SELECT COUNT(*) AS total_zset, COUNT(*) FILTER (WHERE warmer_echo IS DISTINCT FROM 1) AS user_trending
FROM trending_zset_daily WHERE day > NOW() - INTERVAL '7 days';
-- Expect: warmer echo ≈89% before flag; after flag, provenance-gated trending is the real tail.
```

---

## 2. TIER ORDERING: the MC0→MC5 lexicographic scorer — audit the ordering's assumptions (is exact-unfolded > prefix > fragment always right? what query classes would invert it?) and the kind order market>event>team.

### CHOSEN

* **Tier lexicographic:** `search_match_class.py:24:49` five tiers + UNRANKABLE, invariant `docs/search-scoring-spec.md` + ruling 041/Q325. The order is **inviolable**: `MC0 exact full-alias UNFOLDED` (casefold+whitespace only, no accent/plural/punct strip `_exact_key`) `>` `MC1 every token present folded` (`_fold_token` casefold+accent+one plural `s`, `_TOKEN_RE [0-9a-z]+`, `_fold_text`) `>` `MC2 last-token prefix` (`PREFIX_MIN_LEN=2`, typeahead user still typing) `>` `MC3 partial tokens` (`PARTIAL_MIN_COVERAGE=0.5`) `>` `MC4 outcome-only` (market own outcomes, not parent) `>` `MC5 fragment/trigram` (`TRIGRAM_FLOOR=0.30`, `MIN_FRAGMENT_LEN=3`). No knob may lift a lower class above a higher one (`:11` `property 1`). Within-class knobs (`PROMINENT_SPORT_KEYS` 8 leagues, fragment credit) tune only *within* a tier.

* **Kind order within a tier:** `KIND_ORDER` `event_concept:0, concept:0, hub:1, futures/market:2, event:3, team:4` (`:66`). Ratified text was `market > event > team`; `concept`/`hub`/`event_concept` above `market` were **measured, not chosen**: first draft put concept below its member market and lost 7 gold probes (`grammys → "Grammy Winner: Best New Artist"` vs The Grammys, `world cup → 2030 Champion` vs 2026 tournament, `us open` identical market vs concept — all same class, concept tighter, kind decided at `:53`).

* **Owned-evidence-only:** `Evidence.derived=True` is UNRANKABLE, not low-ranked — demotion still won (`concept:event:awards:emmys` won `super bowl` when markets were absent, `search_match_class.py:8`). `match_class` now excludes derived concepts; `derived` is the load-bearing field.

* **MC0 reconstruction:** `casefold` is the one judgment inside MC0 (flagged), accent kept UNFOLDED `São Paulo` ≠ `Sao Paulo` at MC0, they meet at MC1 (`_fold_token`). LAT-P058 `#1881` accent asymmetry: MC5 trigram before fix was accent-sensitive (`koln 0.0000` vs `köln 1.0000` vs Köln), fixed by `_fold_text` for MC5 credit, not for `_exact_key`.

### ALTERNATIVE

The tier order is **assumed total** but three query classes invert it:

* **Single-token exact team (1 token, MC0 or MC1) vs multi-token prefix market (MC2):** user types `celtics` (MC0 team: Boston Celtics). A market `Celtics to win Eastern Conference +400` that matches by prefix on last token `celtic` as `MC2` should not outrank the team — it does not, tier holds. The inversion is the reverse: `celt` (prefix `celt-` on market's last token) as MC2 market vs team `Celtics` MC1? Both are high — but MC1 *all tokens present* outranks MC2 *last prefix only* by invariant, even when MC2's prefix is 6/7 chars and MC1's `all tokens` is one short token `celt`. **No such inversion is shipped as a test** — the knob `PREFIX_MIN_LEN` could gate it but does not cross tiers.

* **Fragment *correctness* (provenance):** `search_match_class.py:24` `Brito` for `british open` (fragment `brit-ish` → `Brito`) correctly loses — MC5 loses to any MC0–4. But `ai` → `Kaiserslautern` is the *same* loss carried to the extreme: a 2-char query under `MIN_FRAGMENT_LEN=3` still entered MC5 with weak credit before that knob; now below threshold it is uncredited but still MC5. Raunchy short-query fragments are correctly low, but a **never-traded market counted in the eligible pool** can be the only available answer — MC5 valid but untraded (never priced) is allowed to win when it should be void (see #1867 later: MC3 grading gap).

* **Kind order market > event for never-traded markets:** a never-traded market (no price, `probability` null) outranks a live event by `market 2 > event 3` *within the same tier*, even though the team/event is the **only answerable page** and the market has no answer. The spec's kind order is for ranked candidates, but the eligible pool built for a probe includes never-traded futures that then *define* the top-1 by kind — a class the gold set cannot grade per #1867 (next §).

### EVIDENCE — code + specimen

`search_match_class.py:66:124` tiers/kind/knobs (`TRIGRAM_FLOOR 0.30, MIN_FRAGMENT_LEN 3, PREFIX_MIN_LEN 2, PARTIAL_MIN_COVERAGE 0.5, PROMINENT_SPORT_KEYS 8`); `docs/search-scoring-spec.md` reconstruction; `flow_sentinel.py:113` 44 probes; `search-answer.spec.ts:23` `red sox` phone rail. **Incident corpus:** §2's “seven gold probes” `grammys`, `world cup`, `us open` were concept>market inversions that *supported* kind order as shipped; `ai`, `ipo`, `british open` were fragment wins that *supported* tier order as shipped — so the shipped order is **measured**, not theorized on the 44. Unmeasured: no probe in 44 tests “exact short team vs prefix long market” — the assumed MC1>MC2 ordering there is unprobed.

### VERDICT

**suspect** — not wrong (the ordering fixed both measured families 30→41/44 on v3792), but **assumed total** where it is only measured on the 44's slice. Three classes would invert it and are not probed: (a) short exact team vs long prefix market (MC0/MC1 vs MC2), (b) fragment correctness when the only answerable candidate is untraded (MC5 valid but unpriced), (c) kind order `market > event` when the market is never-traded and the event is the only answerable surface. Each is one probe to add, not a reorder.

### THE ONE EXPERIMENT THAT SETTLES IT — inverted-order probe pack, read-only

```sql
-- For each MC contrast, add one family-phrased probe whose gold-expected kind is the LOWER tier's kind, so a tier violation is a regression.
-- Candidates already named: (a) "celtics" expect team (MC0 team vs MC2 market), (b) "ai" expect market but NOT Kaiserslautern (fragment-correctness control), (c) a never-traded-only family where expected is event_concept (kind inversion under same tier).
-- Run: scripts/evals/search_gold_set with --compare-against LAT-P059 graded artifact; ruling 073 eligible-pool fingerprint per probe, so corpus move is quarantined.
-- Expectation: tier holds for (a)–(b), market>event inverts for (c) when the market is never-traded → that one probe is the never-traded class that the gold set today cannot see (#1867).
```

---

## 3. GRADING GAPS AS A CLASS: #1867 (can't discriminate MC3, grades MC2 by accident) and #1861 (a deployed change moved zero probes) — census which change classes the gold set structurally CANNOT grade, so we know when a green gold run means nothing.

### CHOSEN

The gold set **grades findability (did anything surface, any tier) + top-1 among kinds** (`GOLD_SET` 44 `expected_found`, `GOLD_SET_TOP1 ~50` family-phrased unambiguous `market>event>team`). It **does not grade**: per-tier discrimination inside MC3 (partial coverage), prefix quality inside MC2, outcome-only vs fragment boundary (MC4 vs MC5), within-tier knob moves, never-traded eligibility, derived-vs-owned boundary, or answer-first per surface. That is why #1861 (deployed change moved **zero** probes) and #1867 exist.

* **#1867 — MC3 undisriminating, grades MC2 by accident:** `search_match_class.py:45/47` MC2 `last-token prefix` and MC3 `partial tokens ≥0.5` are **adjacent in tier** and share the token-set `_TOKEN_RE` + `_fold_token`. A change that moves a query from `MC2` to `MC3` (or tunes `PARTIAL_MIN_COVERAGE 0.5` or `PREFIX_MIN_LEN 2`) lands in the same scored region: the gold set sees only `found/not-found` and `kind` at top-1, not *which tier* it found via. A regression from MC1→MC2 is invisible if top-1 kind stays `market`; an improvement MC4→MC3 that fixes future-outcome over-match is counted only if the expected top-1 kind flips. The lane grades MC3 **by whether MC2's prefix probe moved**.

* **#1861 — deployed change moved zero probes (structurally ungradable):** a within-tier knob move (`TRIGRAM_FLOOR`, `PROMINENT_SPORT_KEYS`, `PARTIAL_MIN_COVERAGE`), a never-traded filter, or a derived-concept exactness fix (`_exact_key` casefold judgment) touches a surface the 44 never enter — e.g., the shipped order `event_concept 0 > market 2` fixed 7 probes that shared a class, but the next 7 that sit **inside MC3** share `≥0.5` coverage and the `market>event` tie-break does not fire across tiers (kind only breaks ties *inside* a class). The run is green and means nothing.

### ALTERNATIVE

Keep 44 as the **canary** (corruption detector, not quality grader) and ship **tier-local gold sets** that *can* grade: `MC0_exact_unfolded` probes that fail if accent/plural moves into MC0 (`_exact_key`), `MC2_last_prefix` probes that fail if `PREFIX_MIN_LEN` drifts, `MC3_partial` probes that fail if `PARTIAL_MIN_COVERAGE` drifts, `outcome-only` probes that fail if a concept derived from a market ranks (known-answer + owned-evidence flag), `never-traded` probes whose expected is the *event* not the market. Each mini-set is 4–6 probes with a single tier/knob as its lord — so #1861's change would have been graded as “moves 3/6 MC3 probes, p=0.12” rather than “moves 0/44, green”.

### EVIDENCE — code + specimen

`search_match_class.py:117:124` five knobs that tune *within* a class, none crosses a tier; `flow_sentinel.py:198` `search_found` `event_concepts|results|futures|futures_families` (any non-empty is FOUND, tier invisible); `docs/rulings/073-corpus-moved.md` corpus-moved quarantine proves the only movement until now that *did* register was not code + moved pool `39→41` with `CANARY_QUERY` proving file path; #1867/#1861 specimens (narrated above) are themselves the evidence that the canary stayed quiet while the user-visible tier moved. **Numbers:** 44 can grade at most `44` dispositions; `PARTIAL_MIN_COVERAGE 0.5` threshold and `TRIGRAM_FLOOR 0.30` together define three equivalence regions inside MC3/MC5 that 44 cannot discriminate — the lane tuned one of them and shipped green.

### VERDICT

**wrong** as a grader. The 44 are **sound as a corruption canary** (they proved v3792's two families) and **wrong as a quality grader** for any change that lives *inside* a tier or in the eligibility boundary — which is precisely where all post-073 work lives (fingerprint quarantines corpus moves, so remaining moves are within-tier knob or eligibility). A green gold run on a within-tier change is not “no effect” — it is “no coverage”. The lane has no tier-local sets, so every future knob move will look like #1861.

### THE ONE EXPERIMENT THAT SETTLES IT — grading-gap census, read-only

```sql
-- Census of change classes by what the current instrument CAN and CANNOT grade:
-- For each region touched by a ranking change, check whether the gold set contains a probe whose expected tier+kind would flip.
-- Write the census, not the grade: enumerate the class, note CANNOT.
-- Stored as docs/search-gaps-census.md (like calibration's derived_map gap), not as a grade.
-- Probe packs to add (4–6 each): MC0_exact (accent/punct), MC2_prefix (PREFIX_MIN_LEN), MC3_partial (PARTIAL_MIN_COVERAGE 0.5), MC4_outcome_only (derived vs owned), never-traded-only family (market>event when market unpriced).
-- Check: scripts/evals/search_gold_set --suite=canary (44) + --suite=mc3_partial (6) + --suite=never_traded (4) --compare-against LAT-P059 graded artifact
-- Expectation: 44 still green, mc3_partial moves 2–3 dispositions → the change was real, the canary was silent, the gap is proved.
```

---

## 4. FINGERPRINT INTEGRITY: ruling 073's implementation — what corpus changes would it miss?

### CHOSEN

Ruling 073 (2026-08-17, Fable, #993/#1545, `docs/rulings/073-corpus-moved.md`):

> per-probe eligible-pool fingerprints; unchanged-code disposition changes quarantine as CORPUS-MOVED; baseline moves only by explicit re-baseline naming the expired specimens.

Mandatory per probe: **eligible-pool fingerprint** (stable digest over identities of candidates the probe *could* have ranked), **pool size** (shrink visible without digest), **expected entity's own eligibility** (target-left-pool is void, not FAIL). Verdict table: `no code change + pool fingerprint unchanged ⇒ REAL`; `no code + pool changed ⇒ CORPUS-MOVED (quarantined, excluded from score)`; `code changed + pool unchanged ⇒ REAL`; `both changed ⇒ CONFOUNDED (report both, attribute neither)` — the honest verdict for any ranking change shipped Tuesday and read Thursday. Implementor note in the ruling: the fingerprint is `sha1(pool identities)` with per-probe pool definition matching the scorer's own eligible set (the `Evidence`-level pool, not the raw corpus table).

Banked baseline stays `39/44, MRR 0.8913043478260869`; the `41/44, 0.9347826086956522` read against `producer blob 61de6598, 46/46 exact, 0 regressions` was **QUARANTINED**, not banked — because three top-ranked distractors had left the eligible pool (`FedEx St. Jude Championship Winner` — resolved, outranked Fed Chair market on token `fed`; Stanley Cup Carolina **Hurricane**s — resolved, outranked hurricane market on `hurricane`; `event:15191951` — closed 2026-08-15, between the two reads). Fourth occurrence of specimens pinned to live markets expiring, first in the flattering direction — hence the ruling's asymmetry note: worse-looking moves get investigated, better-looking get banked, so the guard must be mechanical.

### ALTERNATIVE

Per-probe fingerprint on **rendered evidence**, not just identities. Alternatives the ruling explicitly rejected: (a) run-level corpus hash (“did anything anywhere change?” — always yes on a live corpus, says nothing); (b) re-pinning probes to dodge expiry (a probe pinned to a live market is **correct** — user-facing ranking runs over live; a dead target makes the probe void, not the market wrong). A stronger alternative the ruling leaves open: **fingerprint the evidence tuple itself** `(Evidence.name, owned_names, derived, kind)` per candidate after folding, so a corpus move that *renames* a candidate (alias drift) without leaving the pool still flips the fingerprint — otherwise the pool's identities are stable but the *ranking matter* moved.

### EVIDENCE — code + numbers

`docs/rulings/073-corpus-moved.md` three clauses verbatim plus four-row verdict table and `Docs/state` implementation sketch (per-probe `eligible-pool fingerprint + pool size + expected eligibility`); `flow_sentinel.py:17/198` `search_found` across `event_concepts|results|futures|futures_families` and `canary` + `_run_search_gold_set` hedging; LAT-P059 three-row `passes/MRR/regressions` table (`39→41`, `0.891→0.934`, `46/46 exact` producer). **What the implementation must survive:** the fourth row `both changed ⇒ CONFOUNDED` is the common Tuesday→Thursday case — without per-probe pool size, a shrink is invisible when digest comparison is unavailable; without `expected eligibility`, a resolved target is a false FAIL.

### VERDICT

**sound** with caveat. The *per-probe eligible-pool + size + expected eligibility* triple and the four-row table are the right primitive (run-level hash would have missed the three expiries, and the quarantined `41/44` proves the guard fires in the flattering direction for the first time). The caveat is **identity vs evidence**: the ruling says “identities of the candidates,” not “evidence tuples.” A corpus change that **renames** a candidate (new alias, accent fold drift, outcome text edit) without adding/removing its identity leaves the identity fingerprint unchanged but the match class for that candidate can move tiers (MC0 vs MC1) — so the ruling would class the move as `REAL` when it is `CONFOUNDED` by evidence drift. The fix is one field wider: fingerprint the `(identity + owned evidence)` tuple, already described in the implementation note as the scorer's `Evidence`-level pool.

### THE ONE EXPERIMENT THAT SETTLES IT — fingerprint miss census, read-only

```sql
-- For each gold probe, compare last two reads' per-probe pool fingerprint and per-candidate evidence hash (Evidence.name+aliases+derived+kind folded):
-- Cases: (a) fingerprint changed, evidence hash unchanged → correctly quarantined as CORPUS-MOVED (the three expiries on LAT-P059).
--        (b) fingerprint unchanged, evidence hash changed → would be called REAL under identity-only fingerprint but is CONFOUNDED by alias/evidence drift — this is what identity-only would MISS.
-- Stored as sentinel's per-probe row: {probe, fingerprint_before, fingerprint_after, pool_size_before/after, evidence_hash_before/after, verdict}.
-- Check: re-run scripts/evals/search_gold_set against cached LAT-P059 artifact and against production, with --evidence-hash flag (derive from scored Evidence).
-- Expectation: (b) >0 on any window where an alias or outcome text was edited — that is move #4's CONFOUNDED row, currently called REAL.
```

---

## 5. THE ANSWER-FIRST CONTRACT: desktop and phone both photograph the answer row now — audit what "answer" means across surfaces and whether the envelope guarantees it for every entity class.

### CHOSEN

* **“Answer” means one thing:** `frontend/e2e/specs/search-answer.spec.ts:94` “a futures suggestion with **at least one non-null probability** owes an answer.” Not any futures row, not any market, not a related market — the **priced** futures suggestion's leader line, photographed as `[data-testid="search-answer"]` with text `Name 67%` (`PERCENT /\d{1,3}\s*%/`). The oracle is the **payload**, not a second reading of the screen: the journey `deriveOwed` counts `suggestions` of `type:"futures"` with `top_outcomes[].probability != null` independently of the DOM import (`lib/searchSuggestionDisplay.ts` is the implementation, the journey restates the one rule to avoid the constant-oracle trap — `gotcha #121`). Inventory-independent: if the fixed query `red sox` returns no priced futures at all, the journey asserts the **HONEST-EMPTY** direction — zero answer rows, no fabrication — and records the zero rather than passing silently (`:56` “nothing fails when a rendered feature quietly stops rendering”).

* **Both surfaces now photograph it:** UX-P086 (#1620) was desktop-only Slice A; phone `MobileSearchOverlay` was never wired. UX-P035 extracted `lib/searchSuggestionDisplay.ts` and wired both dropdowns (`1e940a35`), but the photograph never collected — eight consecutive cycles staged a false premise because the instrument was never run. `MobileSearchOverlay.tsx:235/238` and `__tests__/searchDropdownParity.test.ts:90` mark `[data-testid="search-suggestion"]` / `search-answer` so the browser rail can photograph THIS surface; the rail photographs what ships. The pack `search-answer.spec.ts` runs on **both projects** (phone vs desktop by `md:hidden` / `hidden md:block` mutual exclusion `layout.tsx`, `openDropdown` on `MobileSearchTrigger` trigger) and asserts (a) `answer_first_row` with `journeyId search.answer_first_row.{surface}` and (b) `answer_row_adjacency` — answer rows **must not displace** the rest (teams/games/hubs must survive alongside futures, the same shape that emptied the Sports tab `#1091`).

* **Envelope guarantee:** the journey's envelope is **“price is present → answer rendered”** — and it is checked by **photograph**, not by unit-test marker presence. `searchDropdownParity.test.ts:112` marks `data-testid` for the rail; `search-answer.spec.ts:177/239` photographs the viewport and `readContentRegionText` at the same `path /` and `QUERY=red sox` (durable inventory: team unpriced row proves fallback + priced futures prove answer). Coverage note: `contentMode:"none"` — Discover card check inapplicable; fixed query not random; `independent-binary fields gotcha #23` photographed as-is (`K6` market `Next Red Sox Manager` at three `100%` outcomes is not suppressed); `RSC_PREFETCH_ABORT` allowed.

### ALTERNATIVE

The contract as written is **narrow**: only `type:"futures"` with at least one priced outcome owes an answer — so **teams, games, hubs, concepts, unpriced futures** explicitly owe *no* answer (they must render the row via `market_type_label` fallback or just the title, and `blankSubtitles` asserts no empty line). Alternatives that would be broader but are explicitly out of scope: (a) a team as answer (no probability, so no percentage — would require a different predicate than `PERCENT`); (b) `#1620` ruled `K6` three-100% outcomes out of scope — suppressing it would hide legitimate independent-binary fields (e.g., `Top 5` `make_cut` fields); (c) answer-first per kind (market > event > team) rather than per priced future. The alternative the audit recommends is a **separate answer envelope per entity class** (priced future → percentage, unpriced future → label, team/game/hub → no answer, concept derived → UNRANKABLE so never answers).

### EVIDENCE — code + specimen

`search_match_class.py:24:49` tier+kind order (why answer lives only on futures: only futures have a probability); `MobileSearchOverlay.tsx:235` / `__tests__/searchDropdownParity.test.ts:90` / `e2e/specs/search-answer.spec.ts:23` rail marks + restated `deriveOwed` (`total/answersOwed/unpricedFutures`); `e2e/specs/search-answer.spec.ts:62:177` whole journey (rows vs answers, `PERCENT`, `fetchOwed` `rate-limit 429` not empty-200 gotcha #53, `mainRegionNonBlank` 40-char, `independent-binary #23` “photographs what ships”). **Incident corpus:** #1620 phone surface never got Slice A — the shipped code existed (`1e940a35` ancestor) but the photograph `answer_visible_typeahead surface=mobile 0→non-zero` was **never collected**, so the issue stayed open eight days — that is the corridor (#1626 `UX-P036 divergence section`, `event-page.spec.ts:13` “none of them could photograph it”) that the rail now closes, and the specific way a shipped UX fix rots.

### VERDICT

**suspect** — not wrong (the predicate “priced future with `probability` → answer `Name N%`” is precise, and the pack photographs it on *both* surfaces with independent oracle and adjacency guard). But the **envelope guarantee is `witnessed, not enforced`**: exactly **one** fixed term `red sox` on **one** path `/` is photographed; a futures type whose priced outcomes regress to unpriced (e.g., sparse `manual_bookmakers` #219-E) would fall back to `market_type_label` and render with *zero answers* — and that is **recorded** as honest-empty, not flagged as lost coverage. No envelope ties “answer owed **for every** entity class that could owe it” — only one durable-inventory term is witnessed. The failure mode left is not “the answer never photographs” — that just closed — it is “the answer photographs on `red sox` while vanishing on another futures type whose inventory just emptied.”

### THE ONE EXPERIMENT THAT SETTLES IT — per-entity-class answer envelope census, header-only/photograph

```sql
-- Inventory census: which entity kinds owe answers at inventory time, by kind?
SELECT kind, COUNT(*) AS candidates,
       COUNT(*) FILTER (WHERE has_price) AS priced,
       COUNT(*) FILTER (WHERE NOT has_price) AS unpriced
FROM suggestion_pool WHERE source='typeahead' GROUP BY kind;
-- Expectation: futures priced >0 (durably, on red sox), teams/games 0 — so answer is scoped to futures priced, by construction.
-- Envelope proof: re-run search-answer pack nightly on two terms (one durable team+priced-futures term, one sparse futures type) and record answersOwed vs answersRendered per surface — zero averaged over time is a drift signal, not an upstream-inventory gap.
```

```bash
# Photograph, not unit-mark: the two surfaces are the instrument
npx playwright test e2e/specs/search-answer.spec.ts --project=mobile --project=desktop --reporter=json
# Expect: journeyId search.answer_first_row.{mobile,desktop} and search.answer_row_adjacency.{mobile,desktop} all green on / with red sox; any non-zero blankSubtitles or displaced teams is the defect.
```

---

## Cross-probe synthesis — each specimen EXPLAINED by which assumption

| Specimen (this cycle) | Which § explains it | Why the mapping is exact |
|---|---|---|
| LAT-P059 `39/44→41/44` with **0 code change** (`61de6598` `46/46 exact`) + FedEx St. Jude / Carolina Hurricane / `event:15191951` expiry | §4 Fingerprint (quarantined as CORPUS-MOVED) + §1 Representativeness blocked | Per-probe `eligible-pool fingerprint` vs `evidence hash` classifies `no code + pool changed` as quarantined, not improvement; run-level hash would have banked it. The asymmetry (worse looks→investigated, better→banked) is the tell. |
| 23.6% sentinel traffic in logs + 89% warmer echo in trending | §1 Representativeness | Both cauterize any comparison of 44 to “real users” until `provenance` ships; no fix to the scorer changes the admixture. Fix §1 provenance flag, then re-read. |
| #1867 MC3 undiscriminating + #1861 zero-probe change | §3 Grading gaps | Gold grades `found vs not-found + kind@top1`, not per-tier MC3 coverage / prefix quality / outcome-only boundary. Any change inside MC3 or a knob (`PARTIAL_MIN_COVERAGE 0.5`) lands in that gap — a green run means nothing. Fix §3 tier-local packs. |
| `british open`→`Brito`, `ai`→`Kaiserslautern`, `super bowl`→Emmys concept | §2 Tier ordering + §3 grading | Fragment and derived-concept wins are the measured failures (`30/44` on v3792) that `MC5` bottom + `derived UNRANKABLE` + tier order fixed; the shipped kind `event_concept 0 > market 2 > event 3 > team 4` is measured on 7 probes. |
| Phone dropdown never showed answer (`#1620` + `#993 Slice A missing on phone`) | §5 Answer-first | Both dropdowns share `searchSuggestionDisplay` now (`1e940a35`), but the photograph `answer_visible_typeahead surface=mobile` was never collected — eight cycles staged a false premise. Rail now photographs `red sox` on both surfaces + adjacency, witnessed not enforced for every futures type. |

*Any future probe movement not mapped to one of these rows is a finding: either a new tier/knob region was added with no probe covering it, or a corpus move was called REAL because fingerprint was run-level not per-probe.*

---

## Top-5 highest-impact (instrument mis-aim, not raw recall)

Ranked by how many future **green gold runs would be false**:

1. **Grading gaps — within-tier knob and never-traded eligibility invisible to 44** — **wrong**. 43r. `search_match_class.py:117` five knobs + `TRIGRAM_FLOOR 0.30` define MC3/MC5 equivalence regions the 44 never enter; `market 2 > event 3` makes never-traded-only families look correct. #1867/#1861 are not incidents — they are proof the canary is silent within the tier it is asked to guard. *Experiment:* tier-local mini-sets `mc3_partial (6)` + `never_traded (4)` — moves 2–3 dispositions while 44 stays green.

2. **Gold-set representativeness — 44 as canary mistaken for sample, quantification blocked on provenance** — **suspect**. 43r. LAT-P060 banked on 073 after proving the 41/44 read was flattering corpus movement; without `provenance=user`, the “real” distribution is 23.6% sentinel + 89% echo. A green 44 cannot be read as “our users see this.” *Experiment:* provenance-gated log/zset census after flag — then re-stratify.

3. **Tier order assumed total — three inversions unprobed** — **suspect**. 43r. `celtics` exact team vs prefix market MC2, short-query fragment correctness with never-traded pool, `market>event` when market is unpriced. All respect `MC0>…>MC5` but the ordering is measured only on the 44's short-head queries — no probe tests the short-exact vs long-prefix boundary. *Experiment:* inverted-order probes where expected kind is the lower tier's kind.

4. **Answer-first — one term photographed, envelope not per entity class** — **suspect**. 43r. `search-answer.spec.ts:94` `red sox` witnesses one priced-futures family on one path; sparse futures types average zero answers and are recorded not flagged, teams/games/hubs correctly owe no answer but have no envelope. A futures type that loses its priced inventory would still pass on `red sox`. *Experiment:* per-kind inventory census + nightly two-term dual photograph.

5. **Fingerprint — identity-only vs evidence-tuple, CONFOUNDED row invisible** — **sound** with caveat. 43r. Per-probe `eligible-pool` + `pool size` + `expected eligibility` correctly quarantined LAT-P059 `39→41` as `CORPUS-MOVED` and closed the run-level hash miss; but a rename/alias edit without identity churn leaves fingerprint flat while `MC0` vs `MC1` moves tier — called `REAL` when it is `CONFOUNDED`. *Experiment:* evidence-hash `(identity+owned evidence)` census alongside identity fingerprint — the miss rate is the rename-without-expiry class.

---

## What “no fixes” still ships with each row

The calibration audit's re-baseline had before/after Brier+reliability. For search, the analogue is a **tier-local gold pack + per-probe fingerprint row** — each row's gate experiment is also its proof:

* Before: snapshot the probe verdict row `{probe, cohort=MC3 etc., fingerprint, pool_size, evidence_hash, verdict}` before the fix.
* After one tier lands (tier-local set or provenance flag), re-run `search_gold_set` **with the same graded artifact comparison** and ruling-073 table; require tier-local probes move while `GOLD_SET 44 + CANARY` may stay green — the move proves the probe, the still-green 44 proves it was the gap.
* Publish tier-local MRR alongside 44's MRR so a within-tier knob that improves `mc3_partial 2/6→5/6` is banked on that tier, not on the admixture that `41/44` would average.

A search knob move that does not move its tier-local pack and does not move its eligible-pool fingerprint is not “no effect” — it is not measured.

---

## Provenance

Method citations are the code (`search_match_class.py`, `flow_sentinel.py`, `typeahead_warmer.py`, `search-answer.spec.ts`); numbers are from `30/44` measured `2026-08-12 21:48Z v3792`, `39/44` vs `41/44` LAT-P059 `61de6598 46/46 exact`, `23.6%` sentinel / `~89%` warmer (#1916), `PRTRIGRAM_FLOOR 0.30` / `PARTIAL_MIN_COVERAGE 0.5` knobs, and rulings `041/Q325` tiers + `073` corpus-moved (`docs/rulings/073-corpus-moved.md`).

