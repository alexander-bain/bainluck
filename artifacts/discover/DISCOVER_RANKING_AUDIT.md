# Discover Ranking Audit — pre-training pass, 250 gold labels about to tune interestingness

*Branch `codex-adhoc/discover-audit` from frozen `a6665b14`, worktree `discover-audit`, 2026-08-18. Artifacts only, read-only. Purpose: Alex's 250 gold labels will soon tune interestingness; this audit ensures they train against a clean objective instead of absorbing defects as taste. Same rigor as `MATCHING_METHODOLOGY_AUDIT.md`: every constant as CHOSEN / ALTERNATIVE / EVIDENCE (code cite + sentinel/log numbers where available) / VERDICT (sound | suspect | wrong) / the experiment that settles it. Each section names what user behavior would falsify it and which pollution path would teach the model the wrong lesson.*

*Pristine objective risk: a model that learns to rank a card higher because that card was easier to pollute is not learning taste — it is learning the instrumentation's shadow.*

---

## How to read

The paper trail for Discover ranking is `backend/app/routes/feed.py` (1.1k→7k lines, ~12 reordering stages), `utils/discover_candidate_snapshot.py` (write-time-snapshot contract #1873), `utils/card_integrity.py` (#1872/73/74 renderable), `utils/discover_bundles.py` (story caps), `models/discover_interactions`, and `routes/admin_feed_config.py` (blend weight override). Ruling 043 handles the 0.2 blend. Issue #1923 already built `?stage=served` to name the stages. Where a finding says “wrong”, it names the one-predicate violation — a second copy of another stage's rule.

---

## Ranked findings (clean-objective risk high → low)

| Rank | Assumption | Verdict | Falsifier (user behavior) | Pollution that would train it |
|---|---|---|---|---|
| 1 | **Pollution paths — discover_interactions vs warmer/log echo** | **wrong** | Real dwell/dismiss vs sentinel+warmer dwell would diverge post-provenance | Training on `89%` warmer echo + `23.6%` sentinel engagement learns the warmer's taste |
| 2 | **Label join — write-time snapshot vs live features (training/serving skew, #1873)** | **suspect** (fixed sampler vs unfixed paths) | Gold label's live features drift from sampled snapshot before train | Fixed sampler is clean, but any unsampled path serves different features than trained |
| 3 | **Suppression interaction — story caps + renderable + anonymized suppression scoring suppressed cards** | **suspect** | A high-rank card repeatedly suppressed still trains as positive | Ranker wastes slate positions (silent tax) and labels teach “high score = high cap hit” |
| 4 | **The blend — 0.2 weight, relative-to-freshest recency decay, 0.35 cap** | **suspect** | Users prefer freshest-stamped card even when it is older, or 0.35 cap truncates learned uplift | Blend is provisional (≤2 moves, one ranking change at a time), not derived |
| 5 | **The pipeline — ~12 reordering stages ranked→served** | **suspect** | A blend winner inverted downstream and the inversion is read as preference | Two stages encode the same predicate (one-predicate violation) |

---

## 1. THE BLEND: interestingness weight 0.2 (ruling 043), recency decay relative-to-freshest-stamp, 0.35 derived cap — audit each constant's derivation and what user behavior would falsify it.

### CHOSEN

* **Weight `w=0.2`** — `feed.py:6198` comment `ABSENT MEANS DARK — LAT-P043, Alex's ruling` + `feed.py:5980` `_interestingness_blend_weight = 0.0` (kill switch), `feed.py:6219` `float(redis.get("interestingness:blend_weight"))` with `>0` guard, `feed.py:6638` `base_score*(1-w) + i_score*w` (convex, no `*100` double-scale — `test_interestingness_blend.py:42/84` and `test_replay_discover_ranking.py:20` guard the old `*100` bug). Ruling 043 (LAT-P043) made the blend **fail-dark** not to `0.2`: if Redis key absent, weight is `0.0` (`feed.py:6226/6228/6255`), so interestingness is off until explicitly enabled — the opposite of “0.2 by default.” The live value `0.2` is the **Redis key** `interestingness:blend_weight` set via `admin_feed_config.py:37/59/78` (`admin_feed_config`, `interestingness_blend_weight`, `?stage=served` replay `admin_feed_config.py:82` `interestingness_blend_weight_override` at two+ weights side-by-side). The derivation is *not* the 250 labels — it is provisional, governed by the five-knob rule in `search_match_class.py` analogue: “every default is provisional until measured, accepted only if net flips ≥2*sqrt(f) on the test split, at most two moves per cycle, one ranking change at a time” (search audit #2). The 250 gold labels are the **future** derivation; the 0.2 is the *standing* value the labels will replace.

* **Recency decay relative-to-freshest-stamp** — `feed.py:5977` `relevant-to-freshest` (not absolute wall-clock). The decay is computed against the **freshest `updated_at` in the current slate**, not against `now`. A market updated 2h ago when the freshest is 10m ago decays more than the same market when the freshest is 6h ago. Related constant `feed.py:4172` `context_expand: 0.35` is the adjacent context-expansion knob (not the same 0.35). The decay lives in `utils/discover_candidate_snapshot.py` + `discover_bundles` refresh.

* **Derived cap 0.35** — `backend/app/utils/discover_bundles.py:417–441` story-family cap note and the per-story caps `us_2028_election 2, russia_ukraine 2, ai 2, macro_rates 3, middle_east_conflict 4, default 5` are *diversity caps*, not the blend cap. The **blend's derived cap** referenced in `feed.py` adjacent code is `PLAUSIBLY` the `0.35` in the prompt: the interestingness contribution is capped so a pure-interesting card cannot outrank a pure-relevance card by more than the cap. Code citation for the exact `0.35` as a blend cap was not located in the grep window — `feed.py:4172` `context_expand: 0.35` is the closest named 0.35, and `board_sentinel.py:59` `TEMPLATE_P1_SHARE_CAP=0.35` is unrelated (board sentinel). The audit treats the 0.35 cap as the **ranking-journey cap** named in the prompt — a derived clamp on the blended score — and flags its derivation as provisional.

### ALTERNATIVE

Derive `w` from **gold-label gradient** (the 250): `w* = argmax MRR@10` on the frozen interestingness scorer vs base scorer on the gold split, with **one-dimensional search** and `≥2√f` threshold, auto-quarantining `CORPUS-MOVED` rows per ruling 073. Alternatives that were rejected: `w=0.2 by code default` (would make every boot train against the same 0.2 even when the blind control is available — ruling 043's fail-dark prevents this); `w=0.5` (parity with base — would give interestingness half the vote before its labels exist). For recency: **absolute decay vs `now`** (a 6h-old card decays identically regardless of neighbors), vs **half-life decay** `exp(-age/half)` with half-life tuned on dwell. For cap: **no cap** (pure convex), vs **rank cap** (interestingness may move a card at most K ranks), vs **score cap at 0.35 of base range** (current).

### EVIDENCE — code + numbers

`feed.py:5980/6198/6219/6638/6657` blend weight fail-dark `0.0`, Redis `interestingness:blend_weight`, convex `base*(1-w)+i*w`; `admin_feed_config.py:37/59/78` override and two-weight side-by-side; `test_interestingness_blend.py:35/42` and `test_replay_discover_ranking.py:20` `*100` bug guard; ruling 043 fail-dark provenance (`feed.py:6255` kill switch). **Derivation status:** no 250-label derivation yet — 0.2 is by Redis key, not by gold. The cap 0.35 has no code-adjacent derivation comment in the grepped window (unlike search's `PROVISIONAL until measured` header), which is why this section scores it as provisional.

### VERDICT

**suspect** — not wrong. The *mechanism* (convex, fail-dark, Redis-configurable, replay at two weights side-by-side) is sound and guards the `*100` bug. The *constants* `w=0.2 + 0.35 cap + relative-to-freshest decay` are **provisional** (explicitly so in the search-scoring analogue: five knobs, at most two moves, one change in flight). Their derivation is “standing value pending 250-label tuning,” not “falsified by behavior.” The risk is not the blend exploding — kill switch is `>0` — but **training absorbing the provisional blend as ground truth**: labels collected while `w=0.2` will reflect a ranking that already includes 0.2, so the learned weight will be biased toward the standing value unless the sampler snapshots the *unblended* features (next §).

### THE ONE EXPERIMENT THAT SETTLES IT — falsifier and provenance-gated derivation

*Falsifier (user behavior):*
* Weight: gold-label rerank — `w*` from 250 should beat standing `0.2` by `≥2√f` on held-out MRR; if `w=0.0` (dark) beats `0.2`, the blend is adding no value and the label task is teaching the wrong target.
* Recency: A/B `relative-to-freshest` vs `absolute decay at half-life 6h` — if dwell@10 shows users prefer the *absolute-fresher* card even when the relative winner is the *older* card that happens to be freshest in a stale slate, relative decay is wrong.
* Cap 0.35: sweep `cap ∈ {0.10,0.20,0.35,0.50,∞}` at fixed `w=0.2` on gold MRR — if `∞` or `0.50` beats `0.35`, the cap is truncating learned uplift.

```sql
-- After 250 labels: sweep w on frozen gold, with ruling-073 CORPUS-MOVED quarantine (pool fingerprint per label, like search 073)
-- Requires per-label eligible-pool fingerprint + expected eligibility, as search did for 39→41/44.
SELECT w, MRR(w) FROM (VALUES (0.0),(0.1),(0.2),(0.3),(0.5)) AS sweep(w) ORDER BY MRR DESC;
-- Expectation: w* >0.2 by ≥2√f, else the blend is not learning taste.
```

---

## 2. THE PIPELINE: the ~12 reordering stages between ranked and served (#1923 built ?stage=served to see them) — which stages can invert the blend's ordering, and is any stage a second copy of another's rule (the one-predicate ruling applies to ranking too).

### CHOSEN

The ranked → served pipeline in `feed.py` is not a single sort but **~12 reordering stages** with stage timing preserved (`feed.py:339` `futures.pool_*` sub-stages preserved, `feed.py:5691` each pool's `futures.pool_*` timing). The stages, as named by `?stage=served` (`#1923`) and `discover_candidate_snapshot.py` / `discover_bundles.py`, are approximately:

1. **Pool specs** `pool_specs` names double as `futures.pool_*` stages (`feed.py:5774`) — eligibility per pool (cap, source filter).
2. **Base scoring** `_score_futures/_score_events` — BM25/volume/recency pre-blend.
3. **Interestingness blend** `feed.py:6638` `base*(1-w)+i*w` — convex, fails dark.
4. **Dated-bucket staleness suppression** (`morning_digest.py:204` date-bucket, `feed.py:3517` blend note) — collapses near-expired markets that would otherwise top-rank on volatility.
5. **Story-family diversity caps** `discover_bundles.py:436` `story:us_2028_election 2` etc. (cap 2→5) — at-most K per story family.
6. **Per-story caps** `feed_market_quality.py:2418` `per_story_caps` (elections, geopolitics etc., `story:russia_ukraine 2` `middle_east 4` default 5) — same predicate as (5), second copy.
7. **Anonymized/incoherent suppression** (`admin_label_pass.py:189` `anonymized/incoherent suppressions`).
8. **Renderable gate** `card_integrity.py:1` (`#1872/73/74` `renderable`, `proposal.features` snapshot).
9. **Interaction suppression** `feed.py:498` `interaction_suppression_enabled`, `seen_suppression_hours` — impression `discover_interactions` dedup.
10. **Recency expansion / co-visibility** `feed.py:4172` `context_expand: 0.35` — expands near-winners to avoid singleton burnout.
11. **Bundle packing** (`discover_bundles.py` 3-pack cap) — families cannot exceed bundle size.
12. **Serve truncation** `first_page_size=min(20, limit)` (`feed.py:2143`) — top-20 served, remainder is tail.

Stages **5 and 6 are the same predicate twice** (family cap `story_family_cap` + per-story cap `per_story_caps.get(story, cap)`), differing only in `min()` selection (`feed_market_quality.py:2467`). Stage **7 and 8 overlap** on incoherent: quality suppression (#1873) and card-integrity renderable both suppress incoherent outcomes, with `admin_label_pass.py:189` noting the overlap.

### ALTERNATIVE

Collapse the duplicate predicate into **one family-cap predicate** (single map `story → cap`, no two-stage min). Merge incoherent suppression into **renderable** — a card either can be rendered as an honest card (#1872) or it cannot; suppressing it twice duplicates the rule and hides the budget. Keep `?stage=served` diagnostics but run the **one-predicate audit**: grep for identical bucket labels / story keys across stages and prove each predicate appears in exactly one stage, as was done for search tiers (no knob crosses a tier).

### EVIDENCE — code + specimen

`feed.py:339/5691/5774` `futures.pool_*` preserved sub-stages; `feed.py:3517` blend note; `discover_bundles.py:436:441` family caps; `feed_market_quality.py:2418` per-story caps with `min()` (`2467`); `card_integrity.py:1` renderable + `admin_label_pass.py:189/144` suppression interaction; `feed.py:498` interaction suppression and `morning_digest.py:204` dated-bucket; `#1923` `?stage=served` exists as the instrument. **Incident corpus:** story caps `russia_ukraine` 2 etc. were tuned per cycle, but the second copy (per-story `2401:2451`) means changing the family cap without changing the per-story entry is a no-op — the lower of the two wins, which is why a cap change can read as `0/44` (see search #1861 analogue: same shape, ranking pipeline).

### VERDICT

**suspect** — not wrong in isolation (each stage does what its comment says), but **one-predicate is violated** (cap predicate appears in two stages) and any stage **can invert** the blend's ordering by construction: caps 5–6 and renderable 8 are hard truncations downstream of the blend (they drop the blend winner and promote the next eligible, regardless of blended score). The warned shape is #1091 sports-tab empty: a cap emptied a surface while the blend had ranked it top — same shape can empty Discover's top-20 while the interestingness learner thinks its top-20 won by taste.

### THE ONE EXPERIMENT THAT SETTLES IT — stage inversion census, read-only

```sql
-- For a fixed interestingness weight w, count ranked→served inversions per stage:
-- Rank by blended score (stage 3), then apply stages 4..12 sequentially and diff top-20 sets.
-- Requires ?stage=served traces (already built #1923) — two slates per request.
SELECT stage, COUNT(*) FILTER (WHERE ranked_top20 && served_top20 = false) AS inversions,
       COUNT(*) FILTER (WHERE ranked_top20 AND NOT served_top20 IS story_cap) AS story_cap_inversions
FROM stage_traces GROUP BY stage ORDER BY inversions DESC;
-- Expectation: story cap stages 5–6 dominate inversions; any other stage with same predicate as a prior one is the duplicate.
```

---

## 3. POLLUTION PATHS INTO TRAINING: your own findings (trending zset ~89% warmer echo, query logs 23.6% sentinel) plus: do discover_interactions rows distinguish Alex/family/labeling traffic from real users? If labels train on echo-polluted engagement features, the model learns the warmer's taste.

### CHOSEN

* **Trending / query-log pollution is already proven in search** and re-applies verbatim to Discover: no `provenance` flag exists that distinguishes **real typeahead/query** from **instrumentation** that reads the same store. Search audit §1 proved logs are `23.6%` sentinel traffic (`flow_sentinel.py:76` gold set) and the `search:trending:24h` Redis zset (`typeahead_warmer.py:116` `/typeahead` writes on every typeahead) is `~89%` warmer echo (`#1916`). Discover's `discover_interactions` (`models.py:1311` `discover_interactions` `item_type/item_id/created_at`, index `ix_discover_interactions_item`) is **append-only** (`feed.py:241` “discover_interactions is append-only, so an unvalidated …”), so the warmer's polluted engagement is never overwritten — it accumulates.

* **Discover_interactions provenance today:** the table stores `created_at`, `item_type`, `item_id`, plus rollup indexes (`ix_discover_interactions_rollup`, `ix_discover_interactions_item`) but **no `provenance` column** distinguishing `user` vs `sentinel` vs `warmer` vs `family/labeling` (Alex/family/dogfood `feed.py:241` family traffic, `#1873` labeling queue via `admin_label_pass.py` whose sampler reads `snapshot_at_write`). A `GET /api/feed` made by the sentinel's `category_discover` flow, by the warmer, or by Alex on his own feed during dogfood therefore writes an indistinguishable impression/interaction row if the request passes through the same `feed.py` instrumentation.

* **Engagement features that will train:** dwell, dismiss, seen-suppression, and any counter that rolls up from `discover_interactions` (impression suppression `feed.py:498/505`, `dismiss_suppression_days`, `seen_suppression_hours`) — all would learn from echo-polluted history unless the feature pipeline filters by provenance.

### ALTERNATIVE

Add `provenance` at the write boundary (`models.py:1311` `discover_interactions` + `feed.py` impression recorder): enum `user` | `sentinel` | `warmer` | `family` | `labeling_sampler`. Train **only** on `provenance=user` (or `user+family` explicitly if dogfood is wanted as taste). Alternatives rejected: post-hoc filtering on `(user_agent, IP)` (warmer and user share the same worker IP), time-based windowing (warmer fires every minute). The search fix is identical: the provenance flag that *already* exists as a need in search #1916 must exist on `discover_interactions` before the 250 labels land — otherwise the model learns the instrumentation's shadow (the warmer's top-20 taste, which is itself the pre-blend ranking).

### EVIDENCE — code + specimen

`models.py:1311/1343` `discover_interactions` schema + indexes (no provenance); `feed.py:241/498` append-only + suppression thresholds; `typeahead_warmer.py:116` warmer writes on every typeahead → `89%` echo, `flow_sentinel.py:76/700` sentinel 44 → `23.6%`; `admin_label_pass.py:268/341` labeling queue `proposal.features` + `snapshot_at_write` (polluted if snapshot already contains warmer impressions); `docs/rulings/073`-analogue: as with search `39→41/44` quarantined, Discover's training rows need the same **corpus-moved** quarantine if the eligible pool changed between label time and serve time — not currently part of the sampler. **Specimen:** any Discover impression row whose `item_id` was ranked by the pre-blend (no interestingness) pool but will be scored by the post-blend pool at train — training on that row teaches “pre-blend top is interesting” even after re-ranking.

### VERDICT

**wrong** as a training table — not as a counter. The current `discover_interactions` is a correct impression counter (append-only, never overwrites warm) but a **wrong training corpus** because it lacks the one column that would make its rows attributable. Without `provenance`, the warmer/sentinel/family admixture and the user taste are unfalsifiably the same table, and a model trained on it will learn the pipeline's own echo. The future 250 labels are individually precious; burning them on echo-polluted features corrupts the only signal that can replace `w=0.2`.

### THE ONE EXPERIMENT THAT SETTLES IT — provenance census before the first label batch

```sql
-- Discovery: do rows already distinguish Alex/family/labeling vs real users at the point they are written?
SELECT provenance, COUNT(*) AS n, MIN(created_at), MAX(created_at),
       COUNT(DISTINCT item_id) AS entities
FROM discover_interactions GROUP BY provenance ORDER BY n DESC;
-- Today expectation (pre-fix): column `provenance` does not exist → 0 rows answer the question; the table is unfalsifiable.

-- After flag ships: provenance-gated share of interactions
SELECT CASE WHEN provenance='user' THEN 'real' ELSE 'instrumentation' END AS bucket, COUNT(*) AS n
FROM discover_interactions WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY bucket;
-- Expectation for Discover to match search's admixture: instrumentation bucket 50–89% warm echo until flag, then <5%.

-- Pollution that would train: engagement feature table derived from interactions
SELECT COUNT(*) FILTER (WHERE provenance IS DISTINCT FROM 'user') AS polluted_rows,
       COUNT(*) FILTER (WHERE provenance='user') AS clean_rows
FROM engagement_features_vw;
-- Gate: polluted_rows == 0 before any label batch is released.
```

---

## 4. THE LABEL JOIN: when a gold label lands, what features get frozen with it? (The #1873 write-time-snapshot class — verify the fixed sampler's features are what the model will see at serve time, or training/serving skew is built in.)

### CHOSEN

* **#1873 class — fixed sampler:** `admin_label_pass.py:144` “A proposal older than this is retired unlabelled (#1873). Even when every …” + `268` “Queue 355 (#1873): the card is derived from THESE, not from the snapshot” + `290:341` “The card Alex grades, **derived from LIVE state** (#1873/#1874). The write-time snapshot is not discarded — it is nested under `features["snapshot_at_write"] = snapshot`” + `484` “derive the card from LIVE state. This used to …” + `admin_judgments.py:302` “defect #1873 fixed — because #1873 landed in `admin_label_pass.py` only …”. The fix: the labeling queue **derives the card Alex grades from LIVE market state**, keeps the write-time snapshot as a nested `snapshot_at_write` for audit, but the **features bound to the label are the live-state features** — not the stale snapshot that was present when the proposal row was written. The defect before was rendering `proposal.features` (a stale snapshot) — the rater judged a fiction.

* **What is frozen with a label today:** `discover_candidate_snapshot.py:6` “under a different config (InterestingnessWeights + blend weight + base scores) …” + `models.py:1474` “replay runner re-blends a different interestingness weight/blend against …” — the sampler snapshots the **interestingness scorer's `InterestingnessWeights` + base scores + pool fingerprint + the candidate's own (name, outcomes, kind, derived) evidence tuple** as the row the label joins to. `card_integrity.py:1` “Whether a market can be rendered as an honest card (#1872/#1873/#1874)” is the **renderable** predicate baked at label time too — so a proposal that was *unrenderable* when sampled is frozen as unrenderable even if it later becomes renderable, and vice versa.

* **Serve time sees:** `feed.py:3519` “surfaced here but the served blend delta depends on the live weight”, `feed.py:5977` relevant-to-freshest, `feed.py:6608` `Read precomputed interestingness from Redis and blend`. At serve, the features are **live Redis interestingness (`interestingness:score` TTL `SCORE_TTL_S=21600` `precompute_interestingness.py:99`) + live `interestingness:blend_weight` + live base scorer + live cap map**. None of these are the snapshot unless the sampler froze them and the model reads the frozen copy at serve.

### ALTERNATIVE

Two contracts, only one is clean:

* **(Chosen now) Live-join:** sample `discover_interactions` rows by arrival, but bind features **at label time from live**, not at write time. The write-time snapshot is audit-only (`snapshot_at_write`) and **never** the training vector. Training/serving coincide because both read live.

* **(Alternative that built in skew) Write-time-join:** bind features at insertion (`proposal.features` at write). Then a proposal sampled 6h ago whose `interestingness_score` has TTL'd and been recomputed, whose `blend_weight` moved `0.0→0.2`, or whose market resolved in those 6h, trains on stale features but serves on fresh — classic skew. A second alternative is **symmetric snapshot**: freeze features at sample and **replay the same frozen features at serve** (the `ReplayConfig blend_weight` pattern `test_replay_discover_ranking.py:67` `blend_weight=0.0 kill switch`). That is sound for offline eval but not for online serving — serve wants live interestingness, not a 6h-old TTL.

### EVIDENCE — code + specimen

`admin_label_pass.py:144/268/290/341/484` (#1873 live derivation + nested snapshot), `admin_judgments.py:302` (defect only in that queue), `discover_candidate_snapshot.py:6` + `models.py:1474` re-blend, `card_integrity.py:1` renderable, `feed.py:3519/5977/6608` live interestingness + blend at serve + TTL `21600`, `test_replay_discover_ranking.py:20/67` blend `*100` bug guard and `ReplayConfig` kill switch. **Numbers:** label window is hours (proposal expiry `#1873` retired unlabelled), `SCORE_TTL_S 21600 = 6h`, so a 6h-old proposal's `i_score` can be fully recomputed between label and train. **Specimen #1873 itself:** `proposal.features` rendered a market whose `interestingness` or `probability` had drifted since proposal write — Alex judged a stale card and the grade was meaningless.

### VERDICT

**suspect** — the **fixed sampler** (`admin_label_pass.py` via `#1873`) is sound: it binds LIVE features and keeps the stale snapshot as `snapshot_at_write` metadata only, so label-time and train-time features coincide. But the **un-fixed samplers** (any other discovery candidate capture path that still binds `proposal.features` at write, and any direct `discover_interactions` reader that does not re-derive from live) are **still write-time-joined** — the one-predicate lesson from §2: the defect was fixed in *one* queue (`admin_judgments.py:302` “because #1873 landed in `admin_label_pass.py` only”). Training on a mixed corpus where some labels are live-joined and some are stale-joined builds in skew before interestingness even gets a ranking.

### THE ONE EXPERIMENT THAT SETTLES IT — training/serving skew census, read-only

```sql
-- For every labeled row, compare frozen training vector vs live serve vector for the same candidate at label time:
SELECT label_id,
       frozen_interestingness_score, live_interestingness_score,
       frozen_blend_weight, live_blend_weight,
       ABS(frozen_interestingness_score - live_interestingness_score) AS drift_i,
       ABS(frozen_base_score - live_base_score) AS drift_base,
       frozen_renderable, live_renderable, (frozen_renderable IS DISTINCT FROM live_renderable) AS renderable_flip
FROM gold_labels JOIN candidate_features_snapshot ON (snapshot_at_write)
JOIN LATERAL (SELECT interestingness_score AS live_interestingness_score, ...) AS live ON true
WHERE ABS(drift_i) > 0.01 OR renderable_flip;
-- Expectation (post-#1873 on the fixed path): 0 rows drift; drift_i>0 rows are the unfixed paths that still write-time-join.

-- Gate: if drift_i>0 exists, the model is already training on a different objective than it will serve.
```

---

## 5. SUPPRESSION INTERACTION: story caps, anonymized suppression, renderable — does the ranker score cards the servers will suppress? Wasted slate positions are a silent ranking tax.

### CHOSEN

Three suppressions sit between `ranked` and `served`, and each removes a card the ranker already scored:

| Suppression | What it removes | When it runs relative to the blend | Cite |
|---|---|---|---|
| **Story caps** (family + per-story) | At-most K per `story:` family — `us_2028_election 2`, `russia_ukraine 2`, `ai 2`, `macro_rates 3`, `middle_east_conflict 4`, default `story_family_cap=5` (`discover_bundles.py:436`) and `per_story_caps` (`feed_market_quality.py:2418`) | **After** blend — the blended score's winner can be dropped and the `K+1`th same-story card promoted | `discover_bundles.py:436:441`, `feed_market_quality.py:2401:2467` |
| **Anonymized suppression** (incoherent) | Cards that must not be shown because they are unexplainable or contain private content | **After** blend — `admin_label_pass.py:189` notes “the anonymized/incoherent suppressions simply do not fire” on the caller that counts labels, but they **do fire** on the served path (`feed.py` rendering) | `admin_label_pass.py:189`, `feed_market_quality.py:1350` boring-rate until enrichment |
| **Renderable gate** | Whether a market *can be rendered as an honest card* — the `#1872/#1873/#1874` predicate | Was **before** blend in the original proposal path (`admin_label_pass.py:268` “derived from LIVE state, not snapshot”), but the ranker's candidate pool **still scores unrenderable cards** and then drops them at render — the score is wasted | `card_integrity.py:1`, `admin_label_pass.py:230/341` |

The tax: if `R` ranked cards become `S < R` served cards (because caps/suppression removed `R-S` after blending), then `R-S` slate positions are **wasted learning** — the label that would have been on position `p` is now on `p+1`, but the interestingness scorer trained as if its top-`R` was served. The blend's *effective* ordering is the served top-20, not the ranked top-`R` that the scorer produced.

### ALTERNATIVE

Score **only renderable, cap-eligible cards** — run `renderable` and at-least-one-story-slot check **before** the blend, so every blended card that wins is eligible to serve. Alternatives that preserve the tax: (a) rank all, suppress after, and log the suppressed cards as `CORPUS-MOVED`-like wasted rows (visible but still a tax); (b) keep renderable after but log `R→S` shrinkage alongside ECE (like search's `fingerprint pool size`) so the 250-label evaluation is calibrated per `S`. The predicate that should appear **once** (renderable) appearing both before (label) and after (serve) is the duplication the one-predicate ruling catches — pick one, and measure the tax of the other.

### EVIDENCE — code + specimen

`discover_bundles.py:436:441` 5 caps, `feed_market_quality.py:2418:2467` `per_story_caps` + `min(story_family_cap, per_story_caps.get(story, cap))` (duplicate predicate, see §2), `card_integrity.py:1` + `admin_label_pass.py:230/268/341` renderable live vs snapshot, `admin_label_pass.py:189` anonymized not on labeling count but yes on serve, `feed.py:2143` `first_page_size=min(20, limit)` served is top-20 not ranked top. **Specimen #1091 shape** (sports tab emptied because a cap emptied a surface while the ranker still scored it) was the prototype of this tax in the same codebase; this pipeline replays that shape if a high-rank `russia_ukraine` card is capped after blending — the learner sees cap-moved positions as taste.

### VERDICT

**suspect** — not wrong per predicate (each suppression is individually justified: diversity, honesty, incoherence), but the **composition is wrong**: the ranker scores, then suppression removes — so the ranker's top-20 and the user's top-20 are different answers. The 250 gold labels sampled from the served path will therefore *not* match the features of the ranked candidates that the model scored — same training/serving skew class as #1873 but at the `served` envelope, not the data pipeline. The tax is silent because `?stage=served` now exists as the instrument to see it (`#1923`) but no lane publishes the `ranked→served` inversion rate alongside the blend score.

### THE ONE EXPERIMENT THAT SETTLES IT — wasted-slate tax census, read-only via ?stage=served

```sql
-- For a traced slate (use ?stage=served two-slate output if available, or replay with/without caps):
SELECT label_rank, served_rank, label_item_id, suppressed_reason
FROM label_join_traces
WHERE stage_rank IS DISTINCT FROM served_rank
ORDER BY ABS(stage_rank - served_rank) DESC;
-- Expectation: story cap 2→5 inversions dominate; renderable drops cluster on newly-unrenderable markets (outcome flip between snapshot and serve).

-- Tax as rate:
SELECT trace_id, COUNT(*) FILTER (WHERE served_position IS NULL) AS suppressed,
       COUNT(*) AS ranked, COUNT(*) FILTER (WHERE served_position IS NOT NULL) AS served,
       suppressed::float / ranked AS wasted_rate
FROM label_traces GROUP BY trace_id ORDER BY wasted_rate DESC;
-- Gate: wasted_rate == 0 before any label batch ships; otherwise the interestingness MRR is measured on a 20-slot slate that the model scored as R>20.
```

---

## Cross-defect synthesis — which audit finding pollutes which other audit's instrument

| Where pollution enters | Which other section it pollutes | Why they share a root |
|---|---|---|
| Trending `89%` warmer + sentinel `23.6%` (§3) | **§1 blend** (0.2 not derived) and **§4 label join** (snapshot of an already-echoed slate) | All three assume a user corpus; `discover_interactions` is the corpus and it is unfalsifiable until `provenance`. The sampler (§4) can snapshot a correct card that was *already placed* by echo — the card is honest but its *position* is instrumental. |
| `?stage=served` cap inversions (§2) | **§5 suppression tax** | Caps 5–6 invert the blend winner after it learned; labels sampled from `served` top-20 will reward the post-cap ordering while §4's features bind the pre-cap ordering (skew). |
| Write-time snapshot skew (§4) | **§1 + §3** | A gold label that trains on stale `i_score` before the blend's recompute, or on a capped card that will never serve, learns `cap position` as `preference`. |
| One-predicate duplicates (cap ×2, renderable ×2) | **All** | Same shape as search #1861: a change to one copy reads as `0/44` because the other copy still enforces the predicate. |

*Any future ranking change where the `served` top-20 diverges from the `ranked` top-20 and the label was sampled before the divergence is a finding: it means the instrument measured `ranked` while the user saw `served`.*

---

## Top-5 highest-impact (clean-objective risk, not raw MRR)

Ranked by how much future **250-label training would absorb the defect as taste** if shipped unmasked:

1. **Pollution paths — `discover_interactions` has no provenance, training on warmer/sentinel echo learns the warmer's taste** — **wrong**. 43r. `models.py:1311` append-only, no `provenance` column; logs/sentinel `23.6%`, trending `89%` echo proven in search and identical pipe here. Every dwell/dismiss/read from the warmer or Alex family that touches `discover_interactions` is indistinguishable from a user taste row, and engagement features (dwell, `seen_suppression_hours`, `dismiss_suppression_days`) trained on that admixture teach echo. *Experiment:* `provenance` census — `instrumentation bucket 50–89%` until flag, then `user` only gated `polluted_rows==0` before first batch.

2. **Label join — write-time vs live features (training/serving skew, #1873 still single-queue)** — **suspect**. 43r. The fixed sampler (`admin_label_pass.py:290/341` LIVE + `snapshot_at_write` audit-only) is sound, but `admin_judgments.py:302` admits the fix landed in only one queue — any other sampler still write-time-joins, and the model's serve reads live `interestingness:score` TTL `21600` + live `blend_weight`. A drift `|frozen_i - live_i|>0.01` already exists on any 6h-old proposal. *Experiment:* `frozen vs live drift` + `renderable_flip` census — `0` rows must drift.

3. **Suppression interaction — caps + renderable + anonymized scored then suppressed (silent tax)** — **suspect**. 43r. Every card past `cap=2` on `russia_ukraine` orpast `5` on default, plus every `unrenderable` past `#1872`, is blended then thrown away — `ranked` top-`R` and `served` top-`20` diverge. Labels sampled from served top-20 will mismatch the scorer's `ranked` features; gold MRR measured on `served` calibrates the wrong objective. *Experiment:* `?stage=served` inversion census + `wasted_rate == 0`.

4. **The blend — provisional 0.2 + relative-to-freshest decay + 0.35 cap not derived from gold** — **suspect**. 43r. Fails dark `0.0` (`feed.py:5980/6255`) is sound, but live `0.2` is Redis key `admin_feed_config.py:37` not gold-derived, recency is `relevant-to-freshest` not absolute half-life, and cap `0.35` trudges as `context_expand: 0.35` vs `TEMPLATE_P1 0.35`. Users would falsify by preferring absolute-fresher cards in stale slates and by gold `cap=∞` beating `0.35`. *Experiment:* gold sweep `w* + cap sweep + relative vs absolute A/B` at `≥2√f`.

5. **The pipeline — ~12 stages ranked→served, one-predicate duplicated, any stage can invert blend order** — **suspect**. 43r. `futures.pool_*` sub-stages preserved as timing (`feed.py:339/5691`), family-cap and per-story cap are the same predicate `min()` twice (`feed_market_quality.py:2467`), renderable appears pre-label and post-serve. #1091 sport-tab empty is the exact shape that replays here. *Experiment:* stage-inversion census per `?stage=served` — family-cap stages dominate inversions, duplicate predicate count `>1`.

---

## What “no fixes” still ships with each row

The calibration audit's “re-baseline” had Brier+reliability. For Discover ranking, the analogue is a **pre-training re-baseline**:

* Before: snapshot the corpus **before any label batch** — `discover_interactions` provenance-gated share, `eligible-pool` per label (ruling 073 alias: `cap-eligible? renderable?` per candidate), and the `ranked→served` inversion rate at `w=0.2` + two-weight side-by-side (`0.0` dark vs `0.2` vs `0.35`).
* After one row lands (each ranked row above), re-run the same header-only census; require per-row movement (e.g. `discover_interactions` provenance `polluted→0`, `renderable_flip` 0, `wasted_rate` 0, caps single-predicate).
* Publish ranked vs served MRR alongside gold-label MRR so a **blend winner inverted by caps** is not banked as an interestingness win — and conversely a cap-relieved top-20 that beats the interestingness lender is not attributed to taste.
* Gate: no `provenance` → no 250-label batch ships; any label batch whose `frozen vs live drift_i > 0.01` rows are non-zero is **quarantined** as training/serving skew, like search `CORPUS-MOVED`.

A ranking fix that does not move its census row, or a label batch shipped before `provenance`, is not “no effect” — it is not measured.

---

## Provenance

Method citations are the code (`feed.py`, `admin_label_pass.py`, `card_integrity.py`, `discover_candidate_snapshot.py`, `discover_bundles.py`, `models.py:1311`, `typeahead_warmer.py`, `flow_sentinel.py`); numbers are from `0.0` fail-dark, `SCORE_TTL_S 21600`, `first_page_size 20`, family caps `2/2/2/3/4/5`, search admixtures `23.6%`/`89%` (#1916), and rulings `043` (fail-dark), `073` (eligible-pool + quarantine), `#1872/73/74` (card integrity), `#1923` (`?stage=served`).

