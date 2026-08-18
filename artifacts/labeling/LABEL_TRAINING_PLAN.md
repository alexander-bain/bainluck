# Label Training Plan — from Alex's 250 gold labels to a deployed interestingness model

*Branch `codex-adhoc/label-plan` from `2098d7aa` (frozen provenance histogram-fix head, 2026-08-18), worktree `label-plan`. Artifacts only, read-only. This is the map from labels to launch-visible ranking. Purpose: Alex's label target (~250 by ~Aug 24) is days away and no end-to-end plan exists — without one, defects become training data.*

*Preconditions cited: provenance `discover_interactions.provenance` + parity `drift ≤0.01` (`test_discover_provenance.py`, `BACKFILL_HEURISTIC.md`, `81defc26`); label-join live derivation (#1873 `snapshot_at_write` quarantine); ranking audit `?stage=served` and blend `43` fail-dark `0.2`.*

---

## 1. DATASET: exact spec — gold labels joined to serve-time features

### What the dataset *is*

One training example = **one labeled Discover card** joined to the **features the ranker saw at serve time**, not at label time, not at write time, and never the echo's features.

| Field | Source | Why frozen this way |
|---|---|---|
| `label` | `overall_label` `love/fine/bad/kill` + `boring` flag + `clarity` `clear/needs_context/confusing` | `love/fine/bad/kill` is the compact editorial verdict (`discover-labeling.md:37`); `bad:confusing` is the defective-card era split — see *Quarantine* below |
| `tapworthy_score` `1–5` | Same row | Primary gold-set target (`discover-labeling.md:153` `tapworthy@20`) |
| `features` | **Live serve-time feature vector** — `base_score`, `interestingness_score` (Redis TTL 6h recomputed), `interestingness_blend_weight` at serve, `category`, `archetype`, `story_key`, `group_id`, `headline/hook+image snapshot`, `market_type`, `rank/score` position, `source/volume` | Your provenance + parity work (81defc26): `test_discover_provenance.py` parity `|frozen_rank - live_rank| ≤0.01` and per-component `|frozen_i - live_i| ≤0.01`; historical `BACKFILL_HEURISTIC.md` two-signal `89%/23.6%` attended-apply. The sampler builds from `discover_candidate_snapshot` (`add_disc_cand_snap` migration) and `admin_label_pass.py:290` `snapshot_at_write` is audit-only — the *feature join is live* (`#1873` fix). Any unsampled path that still binds `proposal.features` at write is training/serving skew by construction (`admin_judgments.py:302` “fixed in admin_label_pass only”). |
| `provenance_filter` | `discover_interactions.provenance = 'user'` via `add_disc_interactions_provenance.py` (`unknown` default, never `user` on absence; warmer/sentinel/gold_session/admin stamped at source; `frontend/lib/discoverInteractions.ts:248` now sends `X-Discover-Provenance: user`) | So Alex's taste is not the warmer's. `89%` warmer echo (`typeahead_warmer`) and `23.6%` sentinel admixture would otherwise teach “pre-blend top is interesting” as preference. |
| `renderable_gate` | `card_integrity.py` renderable + `#1872/#1873/#1874` field coherence; only renderable cards train | An anonymized `Person B/C/M` ladder that cannot form a field is not “bad taste” — it is an upstream pipeline miss (`525` markets) that honest-empty should exclude (`ruling 027`). |
| `pairwise` rows | `choice a/b/both/neither/skip` + `confidence` | Rank-order calibration, `pairwise-accuracy` (`discover-labeling.md:153`), `500+` needed before they drive the loss |

### The bad:confusing split (defective-card era) — which labels are usable vs quarantined

During the defective-card era a subset of labels were rendered from **stale proposal snapshots** (`#1873`: pool never stale, snapshot was; fix landed only in `admin_label_pass`). Cards that graded as `bad` but carried `would_be_interesting_if` + `fix_type` (`staleness`, `data_bug`, `bad_image`, `wrong_market_variant` …) or `reason_chip` `confusing/unclear` are **split on read**, not on write:

* **Quarantined** (not trained, but counted as a diagnostic): any label whose `prospect_snapshot` ≠ `live_card` on the fields the sampler joins — `snapshot_disagrees` flag in `admin_label_pass.py:290`, `rank/score` moved, `category/archetype` flipped, or `field_coherent` flipped from false→true after the snapshot TTL. These are the `confusing` half: the rater judged a fiction, and grading “would be interesting if not stale” as `bad` would teach the model that stale-card *taste* is bad, not that stale-card *timing* is bad. They flow to Issue triage (`create_issue_candidate`) and to `boring-rate` diagnostics, not to the `love vs bad/kill` training slice.
* **Usable** (trained): all labels where `snapshot_disagrees == false` and `renderable == true`, including `bad` that are *taste* bad (e.g., `too_niche`, `low_stakes`) — they are `bad` because the card is not interesting, not because it was incoherent when shown. The `bad`/`kill` collapsed positive-vs-negative vocabulary for the first GBM pass is `love|interesting|positive →1` vs `bad|kill|boring →0`; `fine` is held out from the binary and used only as a pairwise `both`/`neither` anchor.

### Expected `n` per class (with 250 as Alex's target)

The existing corpus at ruling 043 is `65` pairwise labels from `2` reviewers, `2026-05-22/23` — too correlated to tune anything (the lane returned `REFUSE_CLAIM`). Extrapolation from `discover-labeling.md:196` `100–200` per eval cycle, `1k–2k` before reranker:

| Slice | Expectation from 250 | Usable after quarantining `confusing` | Notes |
|---|---|---|---|
| Total single-card labels | 250 `tapworthy_score 1–5` / `love/fine/bad/kill` | ~**210–230** single-card usable | ~10–15% quarantine on `confusing` + stale-snapshot, higher early before the `admin_label_pass` fix swept the queue |
| `love` (positive) | ~80–100 | ~70–90 | Positive class for reranker; sparse tail — broad `love` is the signal, not per-category |
| `fine` (mid) | ~70–80 | — | Not in binary `love vs bad/kill`; used as pairwise `both`/`neither` calibration and as a `love@20` divisor |
| `bad`+`kill` (negative) | ~70–90 (`kill` ⊂ `bad`) | ~60–80 after removing `bad:confusing` | Primary negative; `kill` is a harder negative (kept separate for loss weighting) |
| `boring = true` | overlaps `bad/kill` | — | `boring-rate@20` diagnostic, not a class |
| Pairwise `a/b/both/neither` | ~80 of the 250 if pairwise surfaces land | ~60–70 | Adjacent-rank / tie / current-vs-near-miss / LLM-disagree sampling (`discover-labeling.md:82`). `500+` needed before they drive loss (preview #3) |
| Story/duplicate labels | ~30 triples (same-story) | — | Family-cap training, not interestingness |

At 250, the usable binary is roughly **`~80 love vs ~70 bad/kill`** — about `150` rows. That is small but not unusable if the eval is leave-one-session-out and the model class is simplest-first.

---

## 2. OBJECTIVE + MODEL CLASS: what the model predicts (per-card interestingness score feeding the blend), simplest-first candidates, and what the 0.35 cap and fail-dark contract require.

### What it predicts

`interestingness_score ∈ [0, 100]` per candidate card — the **same scale as `base_score`** — consumed only as `rank_score = base_score * (1 - w) + interestingness_score * w` (`feed.py:6638` convex, no `*100` double-scale — guarded by `test_interestingness_blend.py:42`). It is the per-card `i_score` that the blend interpolates, not a rank delta, not a pairwise logit.

### Simplest-first candidates (in order — do not skip a step)

| Step | Model | Features (audited set only) | Why this order |
|---|---|---|---|
| **2a** | **Calibrated logistic** (L2, Platt-scaled) over the audited features — `category`, `archetype`, `story_key` family, `market_type` (`claim/quantity/duel/field/container_member`), `volume`/`movement`, `source_disagreement`, `image/sentence length`, `headline length` | No text embeddings; no `provenance!=user` rows; no unrenderable rows | The smallest model whose calibration can be read (`probability → observed love rate` by score bin) — if `reliability ≈ w × calibration error`, the blend's math holds |
| **2b** | **GBM (LightGBM, ≤50 leaves, monotonic constraints)** over same features + `interestingness` sub-scores (`public_story`, `timely`, `close_probability`) | Same; monotone on “higher stakes → not less interesting” where the taxonomy says so | Non-linear but still inspectable (SHAP per-category); monotonic prevents a data bug becoming a promotion |
| **2c** | Pairwise GBM / LambdaRank only after `500+` pairwise | Add `choice` pairs | Listwise metrics need pairs; don't burn 250 singles on a pairwise loss |

No deep reranker, no LLM-as-feature until `2a/2b` is on the rails and agreement with Alex is `≥0.75` Cohen's κ (see §3). Rule 043 pins the *weight* (`0.2` taste) — the model tunes *what is interesting*, not how much the signal matters.

### What `0.35` cap and fail-dark require of its output

* **Output range `0–100` calibrated, not clipped to `0.35`.** The `+15` cap (`feed.py:6618`) is **deferred** until fresh labels exist (`043` “DEFERRED until fresh labels” — `+15` head-reaching is a quality claim, not a taste enable). At `w=0.2` the blend drifts *downward* for most cards (cached `i ≈48–50` vs `base 78–98` → `rank_score = base*0.8 + i*0.2` deflated `19/23` cards on v3798). The cap bounds *uplift* only, so today it is inert; when the model ships, its **uplift cap is still `+15`**, not `0.35` — `0.35` is the context-expand knob (`feed.py:4172`) misread as a cap. The artifact the model must respect is: `interestingness ∈ [0,100]` **and** `rank_score ≤ base + 15` at `w=0.2` if the `+15` cap is ever re-enabled — the model itself must not be taught to saturate at `0.35`.
* **Fail-dark (safe when unknown).** Redis key absence/unparsability/store-unreachable all resolve to `w=0.0` (`feed.py:5980` init `0.0`, `gotcha 126` kill-switch: absent is dark, not `0.2`). The model being absent is the same as `w=0.0`: Discover reverts to `base` with no interestingness subtraction. The model therefore must **not** be baked into `base`; it is only read as `i_score` at blend time, with `TTL 21600` recompute — a missing `i_score` is exempt (events/tournaments) and rises by not falling (`043` post-mortem), not a zero.
* **Parity:** trained `i_score` vs served `i_score` drift `|frozen_i - live_i| ≤ 0.01` (`test_discover_provenance: test_label_join_parity…`). A stale `i_score` that would have passed the `+15` uplift under training but not at serve is a measured failure, not a rounding.

---

## 3. EVAL PROTOCOL: holdout design at 250-label scale, Alex-agreement metric, and slate-level test.

### Gold-set fidelity (Ruling 073 packs along for the ride)

Every read — gold-set MRR, `tapworthy@20`, `pairwise-accuracy` — is **quarantined** with the eligible-pool fingerprint (`73-corpus-moved.md:39→41/44` flatteringly moved on `61de6598` `46/46 exact`). Per-probe `eligible-pool fingerprint + pool size + expected eligibility` and the `no code + pool changed → CORPUS-MOVED` (`quarantined, excluded from score`) / `both changed → CONFOUNDED` table. The 250 set will have its own fingerprints; the *same* ones the flow sentinel mines (`event_concepts|results|futures|futures_families`) are the eligible pool the fingerprint hashes.

### Holdout at `n=250` — leave-one-session-out, not random split

Labels within a session correlate (same screener mood, same slate adjacency). Random split leaks that correlation and overstates MRR by `~0.03–0.05` in simulation (`scripts/replay_discover_ranking.py`). So:

* **Sessions** are labeling sessions (batch `labeler + timestamp` window, not a calendar day). `250` across Alex's sessions will be ~`8–12` sessions (`discover-labeling.md:196` `20` cards/session ≈ `3` min). Leave-**one-session-out** `k = #sessions` is the holdout — train on `k-1` sessions, score on the held-out session, aggregate macro-averaged MRR.
* **Stratify by category** within each fold — a session that is entirely `election` cards must not be the held-out drawer for a model whose features include `story_key`.
* **Quarantined rows** (`confusing` + `snapshot_disagrees`) are excluded from both train and holdout — they are diagnostics, not taste.

### Alex-agreement metric (not crowd agreement — Alex's corpus is the target)

* **Single-card:** predicted `tapworthy_score` vs Alex's `tapworthy_score 1–5` — **Spearman ρ** and **pairwise-accuracy** on `love vs bad/kill` (binary). Report both; ρ rewards ordering of `fine` middles without collapsing them into `love`.
* **Against Alex, not majority crowd:** the 250 are Alex's by name — the Prolific run (next §) is the **audience** calibration, not a replacement. Alex-agreement is `agreement_with_alex` per `scripts/evals/rater_reliability.py:27 known_answer`.
* **Gate for the 8-way board sentinel / flow sentinel canary:** gold-set `tapworthy@20` and `boring-rate@20 == 0` and `duplicate-family-rate@20 == 0` (`discover-labeling.md:153`) still gate a shipped ranking, alongside the new `ρ` and `pairwise-accuracy`. A model that improves ρ but breaks `boring@20` does not ship — it goes in the MACHINE_FIX_QUEUE behind provenance.

### Slate-level test — does the reranked page beat the current blend on his *own* judgments?

The scorer is per-card, but the user sees a **page** of 20 (`feed.py:2143` `first_page_size = min(20, limit)`). So the last gate is a slate: for a held-out Alex session (a slate he actually judged), rerank its `label_join` candidates by `base*(1-w) + i_pred*w` vs `base*(1-0.2)+i_current*0.2`, score both slates on Alex's own `choice` / `tapworthy@20` / `boring-rate@20`, and require:

* `pairwise-accuracy ≥ 0.56` (i.e., `>½` with `p_value < 0.05` on `250` pairs — the same `≥2√f` seasoning the search scorer uses: `prob >= 2`),
* plus **no `kill` in top-20** (currently `0/361 all-100` on storage; `1874` is display-time `100%` triple — the honest-empty replaces it),
* plus the **fingerprint-quarantined** delta is **not** counted (a slate where three distractors resolved reads `41/44` flatteringly — that is `CORPUS-MOVED`, not a win).

If `ρ` is up but the slate test fails, the model learned a per-card noise that caps + suppression then inverted (`?stage=served` inversion census `feed.py:339` `futures.pool_*` stages; see Discover Ranking Audit §2/§5).

---

## 4. THE W* DECISION: how the trained score changes the #1815 weight question — the artifact Alex rules on becomes model-vs-current slates at stage=served, same MC protocol.

`#1815` Blend Ratification (`discover-ranking` `needs-user`, `taste` vs `quality` per `043`) was *before labels*: Alex ruled `0.2` ON from a side-by-side (≈ v3798 `13/25 moved, head untouched, two entrants at 23/25`) because labels did not yet exist to *tune* it. With a model, `#1815` re-asks: **keep `w=0.2` with the new `i_pred`, or change `w`?** The ruling that answers must again record whether it is `taste` or `quality`, and it must be evidenced by a slate:

* **Artifact Alex rules on:** two slates at `?stage=served` on the **same corpus** (`cap-eligible fingerprint`, rule 073 per-probe, `pool size` so a shrink is visible even without a digest) —
  * A: **current blend** `base*(1-0.2)+i_current*0.2` capped `+15` inert at `0.2`,
  * B: **model blend** `base*(1-w*)+i_pred*w*` with the trained `i` (same `+15` cap rule, same provenance filter `provenance=user`, same `is_renderable` gate),
  * both as **served top-20** (`is_rendered_card_or_named_empty` + `non_blank_photograph`) rather than `ranked` top-`R` (otherwise cap inversions from §2 are read as model wins).
* **Protocol is MC:** the search tier `MC0→MC5` mastered this — the same carve (“no knob may lift a lower-priority class above a higher one”, `search_match_class.py:11` property 1) applies to ranking. `MRR` and `pairwise-accuracy` are computed on **served** `?stage=served` traces (`feed.py:339` `timings`/`stage` identity-free map), not on pre-cap `ranked` traces.
* **Decision table:**

| Code changed? | Pool fingerprint changed? | Verdict (per 073) |
|---|---|---|
| no (`w=0.2`, `i_current`) | no | `REAL` — the slate the user saw, baseline |
| yes (`w*`, `i_pred`) | no | `REAL` — the model did this |
| no | yes | `CORPUS-MOVED` — quarantined, excluded from score |
| yes | yes | `CONFOUNDED` — report both, attribute neither |

The verdict line rule `043` enforces again: **enabling `i_pred` is `taste`** (side-by-side, one verifier suffices); **choosing `w*` (and re-enabling `+15`) is `quality`** — only labels may move it (`w* = argmax MRR@10` on the frozen scorer vs `base` on the gold split, `≥2√f` seasoning, at most two moves per cycle, one ranking change at a time — `search_match_class.py` seasoning). Alex's ruled `w*` artifact **names the expired specimens** that made the baseline move, or the baseline does not move.

---

## 5. GO/NO-GO: the criteria under which we ship, keep labeling, or conclude 250 labels are insufficient — with the Prolific audience-calibration run (ratified 08-10) slotted where it belongs.

### The gate before the gate

No label batch ships until **(a) provenance** (`discover_interactions.provenance`, slot `REQUESTED` `add_disc_int_provenance` `add_disc_int_market_type`) is `user`-gated for training **and** the `BACKFILL_HEURISTIC.md` dry-run for legacy `unknown` has run (instrumentation share measured), and **(b) parity** (`|frozen - live| ≤0.01` per `test_discover_provenance: test_label_join_parity…`) holds — otherwise the 250 are an **echo polluted** or **stale-snapshot** corpus and the GO below would bank a warp.

### Tri-state GO / KEEP LABELING / CONCLUDE INSUFFICIENT

| State | Criterion (all must hold; first fail decides) | Action |
|---|---|---|
| **GO — ship 2a (calibrated logistic) at w=0.2** | `ρ` holdout (leave-one-session-out) **≥0.50** Spearman **and** `pairwise-accuracy ≥0.62` on `love vs bad/kill` **and** slate-level pairwise beats current blend on held-out Alex slates **and** `boring-rate@20 == 0`, `duplicate@20 == 0`, `no kill in top-20` **and** the delta is `REAL` per 073 (no `CORPUS-MOVED`/`CONFOUNDED` quarantine consumes it) | Merge `i_pred` model artifact, keep `w=0.2` and `+15` inert (043), file side-by-side for `#1815` on top-`20` *served*, tag `model_vs_current` traces, gate on `ρ`/`pairwise` not on `MRR` alone |
| **KEEP LABELING** | `ρ ∈ [0.35,0.50)` or `pairwise-accuracy ∈ [0.56,0.62)` **or** `kill` in top-`20` but fixable via `#1872/#1873` repairs, **and** the `n` needed for `≥0.50` is `≤500` (power calc: `n ≈ 100` per class needed for `ρ=0.50, p<0.01` `t→r`; current usable `~150 binary` at 250, `~300 binary` at 500 doubles SE by `√2 → 0.41` clears the gate) | Do not ship a model that would be a subtraction (`current i ≈48–50` already deflates `19/23` cards at `0.2` per `043`); keep labeling to `500` **before** Prolific, keep `w=0.2` taste, file deterministic fix-bucket issues for the largest `bad` clusters (reranker training is not a substitute for `#1872` anonymized upstream fix `6,984` B/C/M on `525` markets) |
| **CONCLUDE INSUFFICIENT** | After `~500` usable labels `ρ <0.35` **and** `pairwise-accuracy <0.56` **and** no single feature (among `category, archetype, story_key, market_type`) explains `ρ≥0.30` alone (leave-one-feature-out) **and** the score is not spanned by deterministic ranking (`boring-rate`, `story caps`, `renderable`) | Declare the interestingness tail is **not learnable from card-intrinsic features at this `n`** at the `discover-ranking` program level; close `#587`’s “1k–2k before reranker” expectation (`discover-labeling.md:196`) as *rejected at this feature set*, pivot to (a) richer interaction signals (`provenance=user` dwell/dismiss, not just `love`), (b) audience-conditioned interestingness (Prolific strata — next row), or (c) deterministic interest triage queue (`fixable_interest_score 1–5`, `desired_entity_or_variant`) rather than a learned `i_score` |

### Prolific audience-calibration — where it is slotted

* **Ratified 2026-08-10** — not a replacement for Alex's `250`. Alex's corpus is the **target** distribution (his taste, not the crowd's): the model predicts `i` for the Discover *product* as Alex would judge `tapworthy@20` on the page he ships.
* **Where it slots:** **after** the hypothesis of insufficient is entertained, not before GO. Specifically: if 250 → KEEP LABELING (ρ in middle) the lane first asks “is our sampled distribution off?” and slots a **Prolific calibration run** (stratified by `audience_scope` `broad/category_fan/niche`) to answer `broad-appeal@20` (#1916-style): does the model tuned on Alex over-rank `niche` for `broad` audiences? Prolific is **calibration, not training** — it relabels a *held-out* slice of the gold slate (30–50 of the 250 + 30 fresh) on `audience_scope` to gate Prolific's own stratified `broad@20` before any Prolific row enters the training slice. The ratification's drawing right is therefore `30` calibration rows, not a second 250.
* **If GO fires**, Prolific is **deferred** — the shipped model's holdout `ρ≥0.50` already clears the corpus, and an additional crowd step before launch is canonical over-measurement. Shoe-horning it before GO would burn a week of Alex's labeling window (Aug 18→24) on a parallel corpus that dilutes the target.
* **If CONCLUDE INSUFFICIENT**, Prolific becomes the **pivot**: its strata can rescue the dataset by turning a single global `i` into `i_broad` / `i_niche` conditioned on `audience_scope`, without pretending that a crowd's `love` replaces Alex's.

### Rollout order (from `discover-labeling.md:196`)

`100–200` real cards → gold-set eval vs current ranking → fix largest deterministic bucket → re-run the same labeled eval before shipping → calibrate LLM judge vs human majority → **consider offline reranker only after ~1k single-card + 500 pairwise and repeated labels for agreement** (`203`) — the 250 is the *first* of that sequence, gated on `GO` above, and capped at GBM `≤50` leaves until agreement `≥0.75 κ`. No deep, no LLM-as-feature before `2a` is on the rails.

