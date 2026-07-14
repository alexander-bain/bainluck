# Bain Luck — Unified Product & Engineering Strategy (June 2026)

**Author:** Founding engineer / head of product
**Date:** June 9, 2026
**Status:** Operating document for the next 12 months. Every claim about current behavior carries a `file:line` citation. Anything not yet built is marked **[PROPOSED]**. Anything I could not verify against code or a query is marked **[UNVERIFIED]** with the exact evidence that would settle it.

---

## Basis of analysis — what I read and what I could not find

I read CLAUDE.md in full (gotchas #1–#37, quota guard, CI table), `docs/backlog.md` (1,276 lines), `docs/architecture-reference.md`, `docs/gotchas-reference.md` (#16–#105), `docs/discover-labeling.md`, `docs/design-system.md`, and `docs/app-store-launch-plan.md`; then the implementation line-by-line: `services/event_registry.py`, `utils/aggregation.py`, `utils/cross_source_matching.py`, `utils/futures_highlights.py`, `utils/personalization.py`, `utils/discover_card_archetypes.py`, `utils/market_interestingness.py`, the ranking spine of `routes/feed.py` (entry point at :835, candidate pools at :4531–4715, demotion at :587–663, interestingness blend at :4752–5028, review nudges at :1444–1489), `utils/feed_market_quality.py` (classifier :565–722, story caps :1589–1655), the key models in `models/models.py`, the resolution core of `tasks/backfill_winners.py` (incl. the disabled passes at :2444–2478), `tasks/prediction_market_matching.py` (phases at :359–1099), the Celery beat schedule in `tasks/__init__.py:1425–1500`, the full admin surface (12 pages under `frontend/app/admin/`, 16 `routes/admin*.py` files totaling 20,453 lines), `routes/admin_judgments.py` end-to-end, and the native targets (123 iOS Swift files, 9 Watch files, 4 Widget files, `ios/shortcuts/`). **GitHub Issues:** incorporated from a full export at `docs/github-issues-export.json` (403 issues, 44 open, exported June 9, 2026 via `gh issue list --state all`). The headline figures for #754/#804/#805/#826 are now **verified against the issue bodies**, which contain the production audits themselves (e.g., #754's June 3 per-ticker-prefix breakdown). I still could not run live production queries from this environment, so time-sensitive claims ship with their reproduction query via `GET /api/admin/query` (`routes/admin_data_quality.py`, documented in `docs/architecture-reference.md:545–568`).

---

# 1. System reality check

## 1.1 Current-state architecture map

```
                         ┌──────────────────────── INGESTION ────────────────────────┐
 Odds API ──(quota guard,│ tasks/odds_polling.py     tiered 32s/64s/128s             │
 5M/mo)                  │ tasks/espn_sync.py        60s, 4 passes incl. box scores  │
 ESPN ───────────────────│ tasks/statpal_sync.py     schedules/rosters/period        │
 StatPal ────────────────│ tasks/kalshi.py           2h, ALL markets (minus crypto)  │
 Kalshi ─────────────────│ tasks/polymarket.py       1h, event decomposition         │
 Polymarket ─────────────│ tasks/datagolf.py         hourly + 5min live              │
 DataGolf / MLB ─────────└───────────────┬───────────────────────────────────────────┘
                                         ▼
                ┌──────────────── IDENTITY & MATCHING ────────────────┐
                │ services/event_registry.py   find_or_create_event() │
                │   cascade: source-ID → structured(±28h) → create    │
                │ tasks/prediction_market_matching.py                 │
                │   P1.1 ticker scan → P1.2 general → P1.5 revalidate │
                │   → P2 snapshots (per-market commit) → P3 history   │
                │ utils/cross_source_matching.py (category pages)     │
                │ team_identity_mapping / matching_overrides tables   │
                └──────────────────────┬──────────────────────────────┘
                                       ▼
        ┌────────────── TRUTH LAYER ──────────────┐   ┌────────── UNDERSTANDING ──────────┐
        │ Event.win_probability_sources (JSONB)   │   │ enrich_market_hooks (6h, 100)     │
        │ utils/aggregation.py weighted blend     │   │ enrich_discover_llm_metadata      │
        │ odds/win_prob/futures snapshots         │   │   (6h, 125) → market_metadata     │
        │ tasks/backfill_winners.py (~30 phases)  │   │ precompute_interestingness (2h)   │
        │ routes/calibration.py  (MCE 2.3pp)      │   │ feed_market_quality classifier    │
        └──────────────────┬──────────────────────┘   └──────────────┬────────────────────┘
                           ▼                                         ▼
                ┌────────────────────── RANKING (routes/feed.py) ──────────────────────┐
                │ 9 candidate pools → futures_highlights scoring → quality adjust →    │
                │ interestingness blend (w=0.2) → personalization multiplier →         │
                │ review nudges (+8/−18) → event demotion → caps/diversity → first-    │
                │ page mix → editorial tail backfill                                   │
                └──────────┬──────────────────────────┬────────────────────────────────┘
                           ▼                          ▼
            ┌── SURFACES ────────────┐    ┌── SIGNAL CAPTURE ───────────────────┐
            │ Web Next.js (/discover │    │ discover_interactions (swipes/opens)│
            │  /sports /politics …)  │    │ user_predictions (Higher/Lower)     │
            │ iOS/iPad/macOS SwiftUI │    │ ranking_judgments + pairwise labels │
            │ Watch + Widget + Siri  │    │ curation_signals (→ score_adj)      │
            │ 12 admin pages         │    │ discover_review_decisions           │
            └────────────────────────┘    └─────────────────────────────────────┘
```

## 1.2 Maturity matrix

| Subsystem | What works | What's half-built | Biggest correctness risk | Biggest complexity sink | Evidence |
|---|---|---|---|---|---|
| **Matching / identity** | 4-step event cascade with advisory lock, ±28h window, completed/closed statuses, doubleheader tiebreak; Kalshi link rate 85.9% | "Step 2 cross-source ID" of the documented cascade is a no-op comment, not code; link-rate denominator still polluted by season futures | A repeat of the May 2026 incident class: one status/window filter regression silently orphans events for weeks (gotcha #32/#87) | `tasks/prediction_market_matching.py` is 2,454 lines with time-budget logic interleaved into matching logic | `event_registry.py:135–138` ("This step is implicit"), `:194–195` advisory lock, `:204` status filter, `:40` `_MATCH_WINDOW=28h`; link rate: `docs/backlog.md:88` |
| **Aggregation** | Single entry point `compute_aggregate_probability()` with 3-tier fallback; PM sources excluded post-final; resilience validated in March 2026 quota outage | Weights are hand-set, never empirically derived (backlog "P2 — DS", `docs/backlog.md:1223`) | The module docstring promises a weighted **median** ("outlier-resistant"), but the production function is a weighted **mean** — a single stale source CAN drag the aggregate | Two parallel aggregate implementations (time-series median :113–226 vs. scalar mean :273–325) with confusingly similar names | `aggregation.py:8–13` vs `:305–313`; `:270`/`:296` completed-game exclusion |
| **Calibration** | Overall MCE 2.3pp; closing-line vs opening cohorts; CIs; virtual-market reconstruction `(is_grouped OR eligible >= 3)` | Hockey 22.7 / golf 16.7 / football 19.3 MCE; non-NHL hockey excluded entirely | ~6,070 known-wrong `pass2_guess` winners already measured (19% error rate) sitting in the truth layer until #754 cleanup completes | `backfill_winners.py` is 4,531 lines and ~30 named phases vs. the "7 phases" CLAUDE.md describes | `calibration.py:903` is_multi rule; `backfill_winners.py:2444–2449` ("3,865 Kalshi + 2,205 Polymarket wrong winners as of June 4"); MCE: `docs/backlog.md:66` |
| **Feed ranking** | Audit targets clean (boring/ladder/dup@20 = 0, explanation 20/20); deterministic explanations; 9 candidate pools; story caps; bounded review nudges | Interestingness blend shipped (w=0.2) but weights never calibrated against the labeled data it was built for | Dead-code allowlist: the strict `_MAJOR_ELECTION_RE` is silently overridden by a much looser redefinition 100 lines later, so the −30 foreign-election penalty rarely fires as designed | `routes/feed.py` is 5,927 lines; scoring, tracing, debug, and ground-truth audit all live in the request module | `futures_highlights.py:199–219` vs `:319–329` (duplicate regex, second wins); `feed.py:5012–5028` blend; targets: `docs/backlog.md:309` |
| **Content/LLM understanding** | Bounded async enrichment (hooks 100/6h, metadata 125/6h); ranking reads only cached metadata; never in `GET /api/feed` | `discover_llm` metadata exists but only nudges scores; no persisted entity graph, no normalized story keys in DB (story keys recomputed per request) | Stale hooks contradicting live prices (BR47 — flat 33% outcomes under a "100%" hook) | 60+ regexes across `futures_highlights.py` + `feed_market_quality.py` encode editorial taste as patterns that drift from each other | `tasks/__init__.py:1433–1445`; `feed_market_quality.py:454–562` `_story_key()` recomputed at request time; BR47: `docs/backlog.md:541–543` |
| **Personalization** | Bounded multipliers [0.15, 3.0]; dismiss escalation −0.40/−0.60/−0.80; semantic dismiss soft −0.30 @ >0.60 Jaccard; works for anonymous sessions | Web/native local tuning not merged into server profiles after sign-in (backlog item 9, `docs/backlog.md:422`) | Story-key blast radius: one dismiss suppresses an entire story family for 14 days (gotcha #81) — invisible to the user, hard to debug | Affinity derivation logic lives inside `feed.py` (`_load_personalization_context` :2729, ~390 lines), not the personalization module | `personalization.py:462–468` floors, `:535–539` semantic; `feed.py:666–689` story/group propagation |
| **Onboarding / growth** | iOS 5-step onboarding writing to `user_favorites`/`user_preferences`; web Discover with session-based suppression and swipe hints; GA4 hooks everywhere | Web has NO onboarding flow — category selections exist but the "first 30 seconds" redesign is blocked (#482); activation funnel never measured end-to-end | Cold-start first page is decided entirely by editorial constants — zero signal capture before the first swipe | None — the surface is thin, which is the problem | `routes/user.py:420` onboarding endpoint; `frontend/app/page.tsx:1` re-exports discover; #482: `docs/backlog.md:42` |
| **Admin / ops** | 12 pages, 16 route files, deep diagnostics (link rate, backfill status, discover-quality hill-climb console, match-trace) | No jobs-to-be-done organization; `/admin/story` is a 93-line stub; feed-review's backend endpoint not found by audit | An operator can't see "is the truth layer healthy?" in one place — correctness status is spread across ≥6 endpoints | 20,453 lines of admin routes; `admin_data_quality.py` alone is 5,507 lines; backlog item 24 already flags endpoint sprawl | `ls frontend/app/admin` (12 pages); `wc -l routes/admin*.py` = 20,453; `docs/backlog.md:1168–1182` |
| **Labeling** | Real schema: `ranking_judgments` (snapshot context at review time), `discover_pairwise_labels`, eval runs persisted; Good/Bad/Skip flow rebuilt (#587) | Labels feed **evals only** — no label-driven ranking change has shipped (#596) and no reranker (#597); gold-set thresholds in `docs/discover-labeling.md:194–203` (100–200 labels) not yet met **[UNVERIFIED — count via SQL below]** | Single-reviewer bias: `reviewer` defaults to `"alex"` — the entire gold set is one person's taste | Three overlapping label stores (judgments, pairwise, review decisions) with different ranking semantics | `models.py:1460–1503` (`reviewer ... default="alex"` :1500), `:1415–1457`, `:1525–1567`; ranking isolation verified in §6.1 |
| **Native apps** | 123-file iOS/iPad/macOS app, Watch (3 tabs + 4 complication families), Widget (3 families, 5–15min timelines), deep links, auth, rage-shake | Futures browser hidden pending iOS-7; Watch embedded in submission (flagged risk); visionOS untested but enabled; zero crash reporting (#839) | Apple already rejected build 1 (#678 — account deletion + new-user sign-in 500, fixed in `67bb31b`); 5.3.4 (gambling) was NOT raised in round one but remains the resubmission tail risk | Shared SwiftUI across 5 form factors with platform conditionals in `MainTabView.swift` | `MainTabView.swift:60–162` (sidebar; Calibration :113); `BainLuckComplication.swift:117–156`; `BainLuckWidget.swift:33–39,107`; `docs/app-store-launch-plan.md:64–77`; #678 body |

## 1.3 Three places the implementation contradicts the documented intent

These are the three most consequential drifts. Each one would cause an engineer who trusts CLAUDE.md to write wrong code today.

**Contradiction 1 — Discover category base scores in CLAUDE.md are wrong, every single number.**
CLAUDE.md states: *"Category base scores in `futures_highlights.py`: politics 50, geopolitics 55, economics 50, tech 50, entertainment 52, culture 48, health 42, weather 38, crypto 35."* The code says politics **45.0**, geopolitics **45.0**, economics **42.0**, tech **42.0**, entertainment **40.0**, culture **38.0**, health **38.0**, weather **32.0**, crypto **28.0** (`futures_highlights.py:87–97`). Only `SPORTS_CATEGORY_BASE = 18.5` (`:98`) matches. Worse, the doc's *ordering* is wrong: it claims geopolitics (55) outranks politics (50); in code they're tied at 45. Anyone "rebalancing the feed per CLAUDE.md" starts from numbers that don't exist.

**Contradiction 2 — CLAUDE.md says cross-source matching "is exact-string only — paraphrased questions won't match." It hasn't been since May 18.**
`utils/cross_source_matching.py:118–138` implements `_is_conservative_near_match()` — token-canonicalized Jaccard ≥ 0.72 with containment ≥ 0.85, exact-numeric and over/under direction guards — and a second matching pass at `:214–245` pairs unmatched Kalshi/Polymarket questions through it. The backlog records this as shipped (#443, `docs/backlog.md:21,178`). The CLAUDE.md "Cross-Source Market Matching" paragraph was never updated. An engineer scoping the paraphrase-matching project CLAUDE.md implies is still open would re-build something that exists.

**Contradiction 3 — CLAUDE.md says the interestingness scorer "is a scaffold… do not wire it into production ranking without an audit-backed rollout." It is wired into production ranking, today, at 20% weight.**
The doc: *"Offline interestingness calibration has a pure scorer… It is a scaffold for review and tuning, not a feed-ranking integration."* The code: `precompute_interestingness` runs every 2 hours (`tasks/__init__.py:1481–1485`), caches per-market scores in Redis, and `_score_futures` blends them with `blended = base*(1−w) + i_score*100*w`, default `w = 0.2`, capped at `pre_blend + 15` (`feed.py:4757–4769, 5012–5028`). The backlog marks #440 "[shipped] Wire calibrated market interestingness into Discover ranking" (`docs/backlog.md:18`). The doc's own prerequisite — calibrate weights against labels first (0u-N1 steps 1–2, `docs/backlog.md:360–369`) — is recorded as *not done*, meaning we shipped the integration while skipping the calibration the doc demanded. This is both a doc bug and a process finding.

**Runner-up drifts** (real, but lower blast radius): (a) `event_registry.py`'s own docstrings still say "±4h" twice (`:11`, `:185`) while `_MATCH_WINDOW` is 28h (`:40`) — the docstring describes the exact bug that caused the May 2026 incident; (b) CLAUDE.md's Discover demotion spec ("EI ≥ 70 AND Tier 1/2", "score >= 90 AND EI >= 50", and "'elimination'/'buzzer'/'walk-off' are exceptional regardless of tier") does not match `feed.py:587–624`, which requires EI ≥ 80 with major-league context, has no score≥90 branch, and gates ALL drama keywords — including elimination/buzzer/walk-off — on major-league context (`:611–616`); (c) CLAUDE.md says the backfill task "runs 7 phases" while `_backfill_all_winners` (`backfill_winners.py:3428–3874`) runs roughly 30 named phases; (d) the in-file comment "Cap score at 100" sits directly above `min(98, …)` (`futures_highlights.py:696–697`), and `curation_score_adj` is added *after* the cap (`:719–721`), so curated scores can exceed 98 — probably intended, but undocumented.

**Artifact — doc-drift ledger (fix in one PR):**

| Doc location | Stale claim | Code truth | Fix |
|---|---|---|---|
| CLAUDE.md "Category base scores" | politics 50 … crypto 35 | 45/45/42/42/40/38/38/32/28 | Update numbers or, better, reference the constant |
| CLAUDE.md "Cross-Source Market Matching" | "exact-string only" | conservative paraphrase pass live | Rewrite paragraph |
| CLAUDE.md "Offline interestingness calibration" | "not a feed-ranking integration" | blended at w=0.2, every request | Rewrite + record calibration debt |
| CLAUDE.md "Discover event demotion" | EI≥70 / score≥90 / tier-free drama keywords | `feed.py:587–624` thresholds | Update spec |
| CLAUDE.md "Calibration Pipeline … 7 phases" | 7 phases | ~30 phases | Describe phase *groups* |
| `event_registry.py:11,185` | "± 4h" | ±28h (`:40`) | Fix docstrings |
| `futures_highlights.py:199–219` | strict election allowlist | dead code — overridden at `:319` | Delete one regex (see §10) |
| `docs/backlog.md:1076` | "No prior App Store submission attempted" | Apple already rejected a build; #678 is the *resubmission* checklist | Update backlog + launch plan (see §7.3) |
| `docs/backlog.md:42,1213` | #482 first-30-seconds redesign "[blocked]" | #482 CLOSED June 2 — modal removed, contextual swipe teaching shipped | Update backlog status |

---

# 2. The moat — with a falsifiable strength score

**Scoring rubric (defined here, used in every row):**
- **5** — asset accumulates automatically with usage/time, is stored durably, is already consumed by the product, and cannot be reconstructed by a competitor without months of wall-clock time.
- **4** — durable and consumed, but a well-funded competitor could approximate it within ~2 quarters.
- **3** — durable but *not yet consumed* by the product (latent moat), or consumed but easily replicated.
- **2** — exists but is small, single-sourced, or partially evaporates.
- **1** — illusory: either reconstructable from public data in days, or not actually captured.

| Asset | Exactly what produces it | Durable or evaporates? (proof) | Score | Competitor action that neutralizes it |
|---|---|---|---|---|
| **Resolved-outcome calibration history** | `backfill_winners.py` writes `futures_outcomes.calibration_probability` (`models.py:777`), `is_winner` (`:788`), `resolution_source` (`:789`); snapshots in `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots` (`models.py:285,378,829`). 232,625 outcomes / 161,972 markets as of May 19 (`docs/backlog.md:813`) | **Durable** — tables, plus the public `/calibration` page consuming them (`calibration.py:802`). Snapshot retention via `collapse_snapshots` keeps it bounded | **5** | They can't backfill the past: Kalshi candlesticks exist for settled markets (gotcha #99) but Polymarket CLOB history thins out, and *closing-line* identification requires our commence-time fix archaeology (gotchas #63/#67). Time is the moat. Neutralized only if Kalshi/Polymarket ship first-party calibration pages |
| **Cross-source identity graph** | `events` rows holding `external_id` + `espn_id` + `statpal_fixture_id` claims (`event_registry.py:235–250`), `team_identity_mapping` (`models.py:901`), `teams.alternate_names`, `canonical_market_key` (`models.py:657`), `group_id` (`:683`), ~400 hand-won ticker/abbreviation map entries in `sport_keys.py` | **Durable** — DB rows + code constants. The corrections encode incident learnings (e.g., `_KALSHI_TEAM_ABBREVS`, gotcha #51) | **4** | A competitor scoping only Kalshi+Polymarket (no sportsbooks, no ESPN/StatPal) doesn't need most of it. It defends the *multi-source* product, not the feed |
| **Labeled judgments (human editorial)** | `ranking_judgments` (`models.py:1460–1503`) with full card snapshots at review time; `discover_pairwise_labels` (`:1415–1457`); eval runs (`:1525–1567`) | **Durable**, but **latent**: §6.1 proves labels do not touch production ranking; only evals read them | **3** | Today: hire one good editor for a month. The moat only materializes when labels close the loop (#596/#597) and when reviewer diversity > 1 (the default reviewer is literally `"alex"`, `models.py:1500`) |
| **Semantic-match corrections** | `matching_overrides` (`models.py:1015–1026`), force-link endpoint (`docs/backlog.md:116`), backfill-link failure flags in `market_metadata` (`docs/backlog.md:786`) | **Durable** | **3** | Same shape as identity graph; small N. Compounds only while we keep playing in long-tail sports |
| **Interaction / affinity signal** | `discover_interactions` append-only (`models.py:1125–1155`), `user_predictions` (`:1092`), `user_seen_markets` (`:1110`); affinities are *derived per-request* in `_load_personalization_context` (`feed.py:2729`) from the last 30 days | **Raw events durable; derived state evaporates by design** (recomputed each request — acceptable, since it's recomputable). The real limitation is N: a friends-and-family TestFlight population | **2** | Any consumer app with distribution gets this in a week of scale. This is a *future* moat that requires users first — circular with growth |
| **Editorial ground-truth corpora** | Polymarket email highlights (Apps Script → sheet → `utils/polymarket_email_ground_truth.py`), `external_curator_ground_truth_items` (`models.py:1234`), `featured_market_captures` (`:1365`), daily diagnostics snapshots (`:1185`) | **Durable** and consumed by audits (email-hit@20/@50 in `scripts/audit_feed_quality.py:128`) | **3** | It's built from *their* marketing emails and public posts — a competitor harvests the identical corpus. The defensible part is the matching of corpus → our market IDs, not the corpus |
| **Curation signals** | `curation_signals` (`models.py:1506–1522`) → `curation_score_adj` +15/−25 applied directly to markets (`admin_judgments.py` curation handler) → consumed at `futures_highlights.py:719–721` and iOS Share-Sheet shortcut (`ios/shortcuts/README.md:10–34`) | **Durable and consumed** — the only human-signal loop that is fully closed today | **3** | One curator's taste; replicable by any one curator. Its value is the *pipework*, which generalizes to kid labels (§6) |

## 2.1 The 90-day fork challenge

*"A well-funded team forks Kalshi+Polymarket public data and ships a feed in 90 days — which of our moats still stand on day 91, and which were illusions?"*

Concretely, on day 91 the competitor will have: live prices, volumes, categories, images, LLM hooks, and a swipeable feed. Our editorial regex layer (`feed_market_quality.py`, `futures_highlights.py`) buys them maybe 3 weeks to replicate at "pretty good," because its outputs are visible in our feed and reverse-engineerable.

**What still stands:**
1. **Calibration history (score 5).** They have day-91 prices; they do not have our resolved history with closing-line discipline, the commence-time corrections (gotchas #63/#67/#94/#97), or a defensible `/calibration` page. "Do prediction markets predict anything?" is the trust engine of a probability-first product (`docs/backlog.md:62`), and it cannot be bought, only accrued. Caveat from §8: this moat is only as strong as `is_winner` integrity — corrupted resolution is a moat with a hole in it.
2. **Multi-source aggregation for sports (score 4).** Forking Kalshi+Polymarket gives them two thin sources. Our sports event pages blend sportsbook consensus (weight 3.0), ESPN (1.5), stat model, MLB, DataGolf (`aggregation.py:29–37`) on a unified event spine. Replicating means paying The Odds API/StatPal AND solving event identity — the part that took us an incident-scarred quarter (gotcha #87/#89).

**What turns out to be illusion on day 91:**
- **The Discover ranking constants themselves.** Every base score and boost is legible from the outside; nothing about `CATEGORY_BASE_SCORES` is secret. The *process* that tunes them (audits + ground truth + labels) is the moat, and per §6.1 that loop isn't closed yet.
- **Interaction signal at current scale.** With a TestFlight-sized population, our affinity data confers no ranking advantage a competitor can't out-collect in their launch week.
- **LLM enrichment.** GPT-4o-mini hooks at $10/mo (CLAUDE.md services table) are a commodity; theirs will be equivalent on day 7.

**Single highest-leverage flywheel, defended:** *resolved-outcome truth + the human/label loop feeding ranking.* The calibration asset compounds daily without product work; the label pipeline (latent, score 3) is the only asset that can make the feed itself defensible — but only once #596/#597 close the loop and labels actually move ranking. That's why §8 and §9 allocate to correctness and the label loop together: the moat is "we provably know what these markets mean and whether they were right," and both halves of that sentence are currently under-built (one corrupted, one unconsumed).

---

# 3. Content understanding

## 3.1 Artifact — every derived understanding field per market, today

| Field | Where computed | Freshness / TTL | How shallow |
|---|---|---|---|
| `llm_sport_category` (`models.py:636`) | LLM taxonomy enrichment (`enrich_taxonomy_llm`, referenced `docs/backlog.md:149`) | Once at ingestion; rarely refreshed | Single flat string; known cross-sport pollution ("cricket/EPL", "esports/PGA") per `docs/backlog.md:147–150` |
| `market_tier` (`:639`) | Polling-time upsert via `MarketMatchingRule` | At poll | NULL for most markets (gotcha #38) — the field designed to separate championships from props mostly doesn't exist |
| `market_type` (`:642`) | Pattern classification at poll | At poll | Regex-on-name; same blind spots as tier |
| `llm_gender` / `llm_level` / `llm_league` (`:647–653`) | LLM metadata enrichment | Once | Coarse enums; league misclassification feeds link-rate denominator noise |
| `canonical_market_key` (`:657`) | Key builder during polling | At poll | `{sport}:{league}:{category}:{season}` — too weak for dedupe in generic cases, hence `_canonical_key_safe_for_dedupe()` guards (`feed.py:741–765`); NULL backfill incomplete (`docs/backlog.md:183`) |
| `category_tags` / `market_tags` (`:661–664`) | `update_event_tags` task + poll | 2 min (events) / poll | Namespaced strings; no entity normalization ("Taylor Swift" vs "Swift") |
| `group_id` / `group_type` (`:683–686`) | `tasks/polymarket.py` decomposition; backfill phases 0a/0b (`backfill_winners.py:3513–3517`) | At poll + 6h backfill | Source-scoped (`polymarket:{event.id}`); no cross-source grouping — that's `canonical_market_key`'s under-delivered job |
| `image_url` (`:692`) | `enrich_market_images` (200/4h, `tasks/__init__.py:1476–1480`) | Until leader changes | Pexels keyword match; `image_fit` failures are a tracked label axis (`docs/discover-labeling.md:41`) |
| `hook_description` + `hook_generated_at` + `hook_leader_at_generation` (`:695–701`) | `enrich_market_hooks` (100/6h, `tasks/__init__.py:1433–1438`) | Regenerated when leader changes | Can contradict live data (BR47, `docs/backlog.md:541–543`); 250-char blurb with no structured claims |
| `market_metadata->discover_llm` | `enrich_discover_llm_metadata` (125/6h, `tasks/__init__.py:1440–1445`) | 6h batches, feed-shaped candidates only | topic/subtopic/entities/archetype/audience scope/salience/junk flags/comparison axes (`docs/backlog.md:322`) — the richest signal we have, but entities are free-text and consumed only as bounded nudges |
| `is_editorial_recall` (`:705`) | Set during polling (precomputed 44-ILIKE flag) | At poll | Boolean; recall terms hand-listed (`feed.py:390–423`) |
| `curation_score_adj` (`:710`) | Curation signal handler (+15/−25) | Accumulates forever | Unbounded accumulation — 5 demotes = −125 with no decay **(flagged in §10)** |
| `volume`, `volume_24h`, `max_movement_24h`, `open_interest`, `liquidity` (`:713–723`) | Polling + `update_max_movement` (10 min, `tasks/__init__.py:1495–1499`) | 10 min – 1h | Polymarket sub-market volume NULL (gotcha #64) |
| Interestingness score | `precompute_interestingness` → Redis `interestingness:{id}` (2h, `tasks/__init__.py:1481–1485`) | 2h, Redis (evaporates on flush) | 8 deterministic signals (`market_interestingness.py:23–31`); weights never calibrated (§1.3 C3) |
| `quality_class` / `family_key` / `story_key` | `classify_market_quality()` **per request** (`feed_market_quality.py:565–701`) | Request-time, never stored | Regex stack; story keys (`:454–562`) exist only inside a request — dismiss propagation depends on recomputing them identically |
| Editorial archetype | `editorial_archetype()` per request (`feed_market_quality.py:725–805`) | Request-time | First-match-wins regex chain |
| Card archetype contract | `classify_discover_card_archetype()` (`discover_card_archetypes.py:172–253`) | Request-time | Deterministic rendering hints; good contract, not persisted |

Reading the table top to bottom, the diagnosis writes itself: **we understand markets as regex hits and one flat category string, recomputed per request; the only deep understanding (`discover_llm`) is cached but unnormalized.** Nothing links "Taylor Swift engagement market" to "Taylor Swift album market" except string luck.

## 3.2 [PROPOSED] Richer understanding schema

**Storage location:** extend the existing `futures_markets.market_metadata->'discover_llm'` JSONB rather than adding a table. Justification against the guardrails: (a) it's already written by a bounded async task that never runs in the request path (CLAUDE.md LLM rules; `tasks/__init__.py:1440–1445` "Async/cached only"); (b) feed ranking already reads this exact location, so no new query; (c) JSONB writes here follow the established Core-SQL pattern (gotcha #4/#46); (d) no migration risk (gotcha #31). One real column is added because it must be indexable: `story_key` (String, indexed) on `futures_markets` — promoting the request-time `_story_key()` output to a persisted column written at enrichment time.

```jsonc
// market_metadata.discover_llm — v2 [PROPOSED]; v1 fields retained
{
  "v": 2,
  "topic": "entertainment.music",            // existing
  "entities": [                               // UPGRADED: normalized, not free text
    {"name": "Taylor Swift", "slug": "taylor-swift", "kind": "person", "salience": 0.9}
  ],
  "story_key": "story:taylor_swift",          // mirrors new indexed column
  "audience_scope": "broad",                  // existing enum, aligned to label axis (docs/discover-labeling.md:42)
  "stakes": "low|medium|high",                // NEW — maps to resolution_importance label axis (:43)
  "claim": {                                   // NEW — structured restatement of the question
    "subject": "taylor-swift", "predicate": "announces_engagement", "by": "2026-12-31"
  },
  "kid_safe": true,                            // NEW — content gate input for §6 (politics/geopolitics/health ⇒ false)
  "explanation_seed": "Up 12 pts since the Eras finale", // NEW — deterministic-checkable hook ingredient
  "junk_flags": ["dated_bucket"],              // existing
  "enriched_at": "2026-06-09T09:10:00Z",
  "prompt_version": "discover_llm_v2"          // required by docs/discover-labeling.md:191
}
```

## 3.3 What each new signal changes in ranking/cards — and the eval that proves it

| New signal | Precise behavior change | Offline eval (script + expected delta) |
|---|---|---|
| Persisted `story_key` column | (1) `diversify_quality_families` (`feed_market_quality.py:1589–1655`) reads the column instead of request-time regex — story caps stop silently missing markets whose names drift from `_story_key()` patterns (`:454–562`); (2) dismiss propagation (`feed.py:666–689`) matches on stored keys, making the 14-day suppression auditable via SQL | `scripts/audit_feed_quality.py`: `duplicate-family-rate@20` stays 0 while `category-spread@20` (printed at `:102`) rises — expect +1–2 categories in top 20, because today's caps under-trigger on unmatched names. Also a new ratchet: % of top-50 futures with non-null story_key ≥ 90% |
| Normalized `entities[]` | `_discover_feature_tokens` (`feed.py:3118`) emits `entity:{slug}` from the stored slugs instead of name-derived tokens — semantic dismiss (`personalization.py:511–540`) and feature affinity stop fragmenting on spelling variants | Replay last 30 days of `discover_interactions` dismiss token sets: measure % of dismiss-pairs whose Jaccard crosses 0.60 before vs after slug normalization. Expect higher recall of true repeats with zero increase in cross-category false positives (the generic-prefix guard `personalization.py:503–508` is unchanged) |
| `stakes` | New input to `quality_score_adjustment` (`feed_market_quality.py:704–722`): `stakes=high` adds a bounded +6; `stakes=low` AND `audience_scope=niche` adds −10 to replace three of the hand regexes (`_OBSCURE_PROCEDURAL_RE`, parts of `_BORING_PATTERNS`) | Gold-set eval `scripts/evaluate_discover_label_gold_set.py` (persisted to `discover_label_eval_runs`, `models.py:1525–1567`): `boring-rate@20` stays 0; `broad-appeal@20` (metric defined `docs/discover-labeling.md:165`) increases. Ship only if `tapworthy@20` non-decreasing |
| `claim` (structured restatement) | Card layer: deterministic headline builder (`utils/feed_reasons.py`) can render "X by DATE — 62% and rising" without parsing the market name; admin gets contradiction detection: if `claim.by < now` and market still open → stale blocker (extends `_market_title_implied_stale_blocker`, `feed.py:1765`) | `explanation-coverage@20` stays 20/20 (`audit_feed_quality.py:86`) with the *generic-snippet* count (`snippet-issues@20`, `:98`) decreasing; stale: `stale_impression_rate` on `/admin/discover-quality` trends to 0 |
| `kid_safe` | No ranking change. Gates the §6 labeling queue only — enforced in `utils/labeling_queue.py` at queue build, never in `GET /api/feed` | Manual audit of 200 gated cards: 0 politics/geopolitics/health/war items pass the gate |

**LLM-boundedness check (required by the prompt):** every proposed signal is written by the existing `enrich_discover_llm_metadata` batch (125/6h, feed-shaped candidates only). Nothing runs in `GET /api/feed`; nothing grinds the ~56K open-market backlog — the candidate selector stays the same, only the output schema widens. Entity slug normalization is deterministic post-processing (lowercase/strip), not an extra LLM call. The one debt this creates: markets outside feed-shaped candidates never get v2 metadata — acceptable, because nothing outside the feed consumes it.

---

# 4. Growth surface (onboarding + cold start)

## 4.1 First-session trace — web

1. `frontend/app/page.tsx:1` is a one-line re-export of `app/discover/page.tsx` — Discover IS the landing page.
2. A session ID is minted client-side and stored as `localStorage["bainluck_session_id"]` (`frontend/lib/discoverInteractions.ts:42`; same key in `app/daily/page.tsx:105–108`), sent as the `x-session-id` header; the backend reads it in `_session_id_from_request` (`feed.py:167`, cookie fallback first).
3. The page calls `GET /api/feed` with `event_pct: 0.15` hard-coded client-side (`frontend/app/discover/page.tsx:482, 511`) — which is also what arms the `event_pct < 0.3` demotion branch on the backend (`feed.py:1194`). For a fresh session the response is the **global editorial feed**: `_load_personalization_context` returns a default `PersonalizationContext` (no favorites, no affinities), and both multiplier functions early-return 1.0 for anonymous-no-history (`personalization.py:142–148, 276–282`).
4. The user sees the daily-challenge card (5-guess goal), a first-time swipe hint (a "peek" animation nudging the first card ~30px), and cards. There is **no onboarding modal, no category picker, no sign-in gate** — and that is a *deliberate product decision*, not a gap: #482 (closed June 2) records the May 29 decision to **remove** the blocking category modal and "teach the swipe mechanic contextually on the first card," on the thesis that "every card is a micro-preference signal" (#482 body, `docs/github-issues-export.json`).
5. First interactions begin writing signal immediately: swipes/opens POST to `/api/feed/interactions` (`feed.py:247–248`) into `discover_interactions` keyed by session_id; Higher/Lower guesses POST to `/api/predictions` into `user_predictions` (`models.py:1092–1107`, session_id nullable-user).

## 4.2 First-session trace — iOS

1. `@main struct Bain_LuckApp` (`Bain_LuckApp.swift:18`) instantiates `AuthManager` / `NavigationCoordinator` / `PinManager` (`:28–30`) → `ContentView.swift:8` renders `MainTabView()` unconditionally.
2. `Views/WelcomeView.swift:1–40` is a 4-page carousel (Welcome/Accuracy/Discover/Sign-in) firing `AnalyticsService.trackScreen(name:"welcome", type:"onboarding")` (`:39`); it is presented from `Views/DiscoverView.swift:775` — i.e., the welcome flow hangs off the Discover surface, not the app root.
3. `Views/OnboardingView.swift` runs the 5-step flow (location → follow teams → alma maters → sport affinities at 1.0/0.3/0.1/0.0 → rivals); `OnboardingViewModel.submitOnboarding()` (`OnboardingViewModel.swift:102–141`) POSTs to `/api/me/onboarding` (`APIClient.swift:574`).
4. Backend `routes/user.py:420 submit_onboarding` replaces onboarding-sourced `user_favorites` rows and writes `user_preferences.sport_affinities` (JSONB) + `home_location` + `onboarding_completed` (`models.py:446–497`).
5. First feed: `fetchGroupedFeed` (`APIClient.swift:343`) — now personalized via the affinity path below.

## 4.3 Cold-start quality assessment

For a user we know nothing about, the first page is decided by, in order:

1. **Candidate pools** (`feed.py:4531–4715`): sports (80, tier-ordered), sports postseason (80), sports editorial recall (80), non-sports by volume (120), by movement (100), enriched (100), editorial recall (80), soon-resolving (80), external-curator recall (80).
2. **Base scores**: `CATEGORY_BASE_SCORES` — politics/geopolitics 45 … crypto 28, sports 18.5 (`futures_highlights.py:87–98`) — plus boosts/penalties (boring −25 `:251`, cultural gravity +18/+10 `:311–312`, postseason story +40 `:255`, micro-bet −20 `:632–636`).
3. **Quality adjustment** (suppress −100 / low −35 / compelling +12..+42, `feed_market_quality.py:704–722`), interestingness blend (w=0.2, `feed.py:5012–5028`), event demotion to ≤35 (`feed.py:627–632`), caps (exact family 1, per-story 1–5, `feed_market_quality.py:1592–1632`), first-page mixer and editorial tail backfill (`feed.py:1213–1220`).

**How good is that page, actually?** By our own audit, editorially clean: boring/ladder/duplicate@20 = 0, explanation 20/20 (`docs/backlog.md:309`). But it is *identically clean for everyone* — a 12-year-old Warriors fan, a macro trader, and a Swiftie get the same page, and the only lever they're offered is swiping after the fact. Category dismiss needs 3+ swipes per category to reach −0.40 (`personalization.py:462–468`), so a sports-only user has to swipe away politics, geopolitics, economics, AND tech ~3x each — roughly 12 negative actions — before the feed visibly bends. Cold start is an editorial product, not a personalized one, and the personalization ramp is intentionally slow. That's the growth bug: the slow ramp that protects quality for engaged users is exactly wrong for the first 60 seconds.

## 4.4 Redesign — capture signal that maps onto EXISTING fields (no parallel system)

**Constraint first:** #482 (closed June 2) already litigated this. A blocking category modal existed, measured badly, and was deliberately removed in favor of contextual swipe teaching. Any redesign that re-introduces pre-content friction is re-fighting a decided question — so the design below works **entirely within the swipe-as-signal thesis** and attacks the actual residual problem from §4.3: the affinity ramp is too slow (≈12 negative actions before the feed visibly bends).

**The move, in three swipe-native pieces:**
1. **Fast-lane the first swipes.** Weight interactions from young sessions (<20 total interactions) 2x when deriving category affinities, so 1–2 swipes per category — not 3+ — start bending the feed.
2. **Make the first page a deliberate category probe.** The first 8 cards for a zero-signal session should maximize *category information gain* (one strong card each from sports/entertainment/world/economics/weather…) rather than being the same global editorial top-8. This is a first-page mixer tweak, not a new system: `diversify_discover_first_page` (`feed_market_quality.py:972`) already reorders the first page; give it a `cold_start=True` mode that widens category spread when the personalization context is empty.
3. **One inline, dismissible "more like this?" chip-row card** at position ~6 (a card *in* the feed, not a modal over it) offering category chips. A tap writes the same interaction rows a swipe would. Skippable by scrolling past — zero blocking UI, consistent with the #482 decision.

**Artifact — field mapping table (every write target already exists):**

| Captured signal | Write target (existing) | Read path (existing, unchanged) |
|---|---|---|
| Chip-row taps (e.g., 🏀 NBA, 🎬 entertainment, 🌍 world) | Anonymous: `discover_interactions` rows `action='like', item_type='category', category=<pick>` (`models.py:1133–1137` — schema already permits; `_build_discover_category_affinities` (`feed.py:2997`) already aggregates by category) | `discover_category_affinities` → `_category_affinity_bonus` (`personalization.py:446–459`), bounded +0.18 |
| Sport picks for signed-in users | `user_preferences.sport_affinities` via the **existing** `POST /api/me/onboarding` (`routes/user.py:420`) with only `sportAffinities` populated | `_lookup_sport_affinity` (`personalization.py:551–582`), ±0.5/−0.6 |
| Team pick (optional typeahead, reuses `searchTeams`, `APIClient.swift:569` / web equivalent) | `user_favorites` rows `relation_type='follow'` (`models.py:446–473`) | `FOLLOW_BONUS 0.8` (`personalization.py:40`) |
| First-swipe fast lane | No new store — change `_build_discover_category_affinities` (`feed.py:2997`) to weight interactions from sessions with <20 total interactions 2x | Same bounded caps; MIN_MULTIPLIER 0.15 unchanged |

[PROPOSED] code touched: one chip-row card component on `frontend/app/discover/page.tsx`, one branch each in `_build_discover_category_affinities` (`feed.py:2997`) and `diversify_discover_first_page` (`feed_market_quality.py:972`), zero schema changes, zero new endpoints (web uses the existing interactions endpoint anonymously — critically, this works **before sign-in**, which iOS onboarding does not).

**GA4 events** (respecting the 3 mandatory hooks `usePageTracking`/`useScrollDepth`/`useEngagementTime`, which stay untouched): `onboarding_start` / `onboarding_step` / `onboarding_complete` already exist in the taxonomy (`docs/backlog.md:224, 278`) — fire them from the web sheet with `platform=web` so the existing onboarding funnel exploration (`docs/backlog.md:223–226`) covers both platforms; add `step_name='category_picker'`.

**A/B-able activation metric (one, with definition):** **A1 = % of new sessions that record ≥5 `prediction_submit` OR ≥3 `feed_card_action(detail_click)` events within the first 7 days, by first-touch cohort.** Numerator and denominator both derivable from GA4 (`prediction_submit` is already a key event, `docs/backlog.md:278`) and first-party from `user_predictions` + `discover_interactions` keyed by session_id — so the experiment survives ad-blockers. Variant A: current cold start. Variant B: fast-lane weighting + cold-start probe page + chip-row card. Guardrail: `boring-rate@20=0` must hold per-variant (run `scripts/audit_feed_quality.py` against a session seeded with each variant's picks).

---

# 5. Operator surface (admin)

## 5.1 Artifact — keep / merge / kill inventory

**Frontend pages** (12 = 11 dirs + root, `frontend/app/admin/`):

| Page | Operator job it serves | Verdict |
|---|---|---|
| `page.tsx` (root ops dashboard) | "Is production healthy right now?" — quota, workers, storage | **Keep** as the entry hub; absorb alert states from others |
| `discover-quality/` (2,145 lines, the largest) | "Is the feed good, and what's the next fix?" — hill-climb console, launch health, engagement, ground truth, review queue | **Keep** — this is the model for jobs-to-be-done admin |
| `labeling/` (404 lines) | "Label cards" — Good/Bad/Skip flow (#587 rebuild) | **Keep**; becomes the host for §6 kid mode |
| `labeling-coverage/` (469 lines) | "Where are labels thin?" | **Merge into `labeling/`** — coverage is a tab of the labeling job, not a separate job |
| `eval/` | "Did label-measured quality regress?" — reads `discover_label_eval_runs` | **Merge into `labeling/`** (same job: label → eval → tune) |
| `feed-review/` | Card review | **Kill/merge** — overlaps the review queue inside discover-quality; its dedicated backend endpoint wasn't found by the audit (NOT FOUND) |
| `bug-reports/` | Rage-shake triage, status flow, fix emails | **Keep** |
| `matching/` | Link-rate, match traces, force-link | **Keep**, but fold into the Correctness Console below as a tab |
| `source-intelligence/` | Per-source audits (5 audit endpoints) | **Merge** into Correctness Console |
| `analytics/` | Engagement rollups | **Keep**, thin |
| `taxonomy/` | Category/league fixes | **Keep** — directly serves the #826-class misclassification work |
| `story/` (93 lines) | Stub | **Kill** until story pages are a real product surface |

**Backend route files** (16 files, 20,453 lines total — `wc -l routes/admin*.py`): `admin.py` (the rump of the 8,684-line split, #480), `admin_data_quality.py` (5,507), `admin_matching.py` (3,882), `admin_judgments.py` (1,651), plus analytics/backfill_linkage/backfill_odds/celery/engagement/events/llm_diagnosis/providers/source_health/taxonomy/teams/utils. Verdict: the split already happened along the right seams; the remaining debt is backlog item 24's endpoint catalog (`docs/backlog.md:1168–1182`) — classify each endpoint `public_product / admin_dashboard / admin_diagnostic / agent_debug / temporary_backfill / obsolete` and delete the resolved-incident one-offs. `admin_data_quality.py` alone holding 5,507 lines of backfill triggers is the strongest signal that "temporary_migration_or_backfill" endpoints never die.

## 5.2 Gap analysis tied to live issues

- **#738 (calibration math epic) + #754/#806:** the data exists (`GET /api/admin/backfill-winners/status` with `stuck_diagnosis`, `docs/backlog.md:726`; pass2 inflow via `scripts/audit_pass2_inflow.py`) but there is **no admin page** for it — the most important workstream in the tracker is operated via curl. Coverage thresholds ("any gap is a bug", CLAUDE.md health check) exist only in a markdown checklist, not as rendered red/green.
- **#826 (source coverage):** six commits of fixes (`git log --grep "#826"`: ingest-ALL-games, WPS backfill + pagination, event-level coverage monitoring `a082d1c6`) added an event-level source-coverage endpoint — again, endpoint-only. An operator cannot see "MLB events with Kalshi data: X%" trend without re-querying.
- **#828 (stale-card / feedback-loop contract):** the *observability* half is built — `/admin/discover-quality` shows stale-impression rate, repeat rate, root-cause labels, trend panels (`docs/backlog.md:329–330, 399–402`). But the issue body (P0, open) is blunt that *enforcement* is not: title-implied stale blockers "appear as trace/advisory metadata without blocking `_score_futures`," review feedback "does not always affect ranking durably" (exact-id, latest-500-window lookups — confirmed at `feed.py:1481–1482`), and the fallback response cache "can keep serving a frozen feed after feedback" (the stale-key path at `feed.py:969–977`). Companion issue #834 (durable serving penalties for rejected cards) is the fix vehicle. The contract part — blockers page, not wait to be read — goes through the alerts plan below.

## 5.3 Redesigned admin IA — by jobs-to-be-done

```
/admin
├─ Health        (job: "is prod up?")          ← root dashboard + celery + Sentry states
├─ Correctness   (job: "is the truth right?")  ← NEW, spec below
├─ Discover      (job: "is the feed good?")    ← discover-quality (unchanged) + feed-review absorbed
├─ Labels        (job: "teach the ranker")     ← labeling + labeling-coverage + eval merged
├─ Inbox         (job: "what do users say?")   ← bug-reports + (future) curation signal log
└─ Catalog       (job: "is metadata right?")   ← taxonomy + teams
```

## 5.4 The single highest-value new operator view: the **Correctness Console** [PROPOSED]

One page that answers "can we trust our own numbers today?" — the question §8 shows we currently answer by running five curl commands.

**Data shown (top to bottom):**
1. **Resolution integrity strip:** per-source market-level winner coverage (the `BOOL_OR(is_winner)` metric, gotcha #100), count of outcomes by `resolution_source` with `pass2_guess`-family highlighted, and 14-day pass2 inflow sparkline.
2. **Calibration strip:** overall + per-category MCE with N, red when N>100 category exceeds 10pp (the existing session-start threshold, `docs/backlog.md:891`).
3. **Coverage strip:** event-level source coverage per Tier-1 sport (the #826 monitor), link rate with `denominator_diagnostics`, snapshot distribution (`sparse_pct`, `median_snapshots`).
4. **Drift strip:** grid health (column sums ≈ 100%, the #471 failure), aggregation source-diversity alert state (`tasks/monitoring.py` daily sample).

**Existing endpoints it composes (no new queries):** `GET /api/admin/backfill-winners/status`, `GET /api/calibration` + `/calibration/diagnostics` + `/calibration/snapshot-health` (`calibration.py:154, 461, 802`), `GET /api/admin/prediction-markets/link-rate`, the event-level source-coverage endpoint (commit `a082d1c6`), `GET /api/admin/audit/all`, `GET /api/admin/snapshots/distribution` (`docs/backlog.md:707–712`).

**Pages it absorbs:** `matching/` and `source-intelligence/` become tabs 3 and 4.

**Which current dashboards become alerts instead:** anything with a hard threshold stops being a page someone must remember to read — background queue >50 (`docs/backlog.md:904`), is_winner market-level coverage <100% on any source, MCE category >10pp at N>100, stale_impression_rate >0 (#828's launch blocker), grid column sum outside 90–110%, pass2 inflow >0/day — note this last one is already an open P0 asking for exactly this check (#806, whose body observes the count "has oscillated and sometimes increased" since the disable; SQL in the issue, script at `scripts/audit_pass2_inflow.py:17–26`). Wire through the existing Sentry alert-rule scaffolding (`scripts/setup_sentry_alerts.py`, gotcha #86) or the daily digest task. The console renders state; alerts own urgency.

---

# 6. Human-signal engine (including the kids)

## 6.1 How a label is captured today — and whether it changes ranking (proof)

Trace: `frontend/app/admin/labeling/page.tsx` (Good/Bad/Skip card flow) → `POST` to `routes/admin_judgments.py` (1,651 lines, 12 endpoints, admin-secret/Bearer gated) → a `ranking_judgments` row (`models.py:1460–1503`) storing the label plus the full scoring context at review time (`score_at_review`, `category_at_review`, `archetype_at_review`, `quality_class_at_review`, `headline_at_review` — `:1487–1491`) and `reviewer` defaulting to `"alex"` (`:1500`). Pairwise comparisons land in `discover_pairwise_labels` with card snapshots (`:1415–1457`).

**Does any of it affect ranking? Three paths, two of which do:**

| Path | Affects production ranking? | Proof |
|---|---|---|
| `ranking_judgments` / `discover_pairwise_labels` | **No.** Consumed only by export + eval scripts (`scripts/export_discover_labeled_dataset.py`, `evaluate_discover_label_gold_set.py` → `discover_label_eval_runs`) | Zero references to either table in `routes/feed.py`, `utils/feed_scoring.py`, `utils/feed_market_quality.py`, `utils/futures_highlights.py` (audit grep). The only feed-side use is *exclusion of already-reviewed cards from the labeling queue* via `exclude_reviewed` (`feed.py:884–890, 1233–1248`) — hygiene, not ranking |
| Curation signals | **Yes, directly.** `signal='boost'` → +15, `'demote'` → −25, written straight onto `futures_markets.curation_score_adj` (Core SQL UPDATE in `admin_judgments.py`, `BOOST_ADJ=15 / DEMOTE_ADJ=-25`) and added to every future highlight score at `futures_highlights.py:719–721` (after the 98 cap) | Verified both ends in code |
| Review decisions | **Yes, bounded.** Human `accepted_promote` → +8 (capped 98), `accepted_downrank` → −18, applied per request from the latest 500 decisions (`feed.py:1444–1489`). LLM-proposed rows are written as `llm_proposed_{action}` (`tasks/enrich_markets.py:911,976`) and are **excluded** by the `decision.in_(["accepted_promote","accepted_downrank"])` filter (`feed.py:1477–1479`) until a human accepts — exactly the advisory contract `docs/discover-labeling.md:3–5` demands | Verified both ends in code |

So the honest summary: **the rich label corpus is ranking-inert; only the two blunt human override channels are live.** #596 (first label-driven ranking tune) and #597 (learned reranker) are the missing conversion step — and per §2, the moat depends on them.

## 6.2 The kid-labeler — design with gating requirements

Context: the in-house labeler pool is real — Oliver (15), Dexter (12), Daphne (8) — and `docs/discover-labeling.md:196` needs 100–200 labeled cards per eval cycle, 1,000–2,000 before a reranker. The rollout vehicle is **#671 (open, verified)**: "Add non-admin reviewer access and onboarding for friends-and-family labeling." Its remaining scope is exactly what the kid-labeler needs — a reviewer role/allowlist separate from full admin, gated labeling endpoints, reviewer onboarding states (not approved / approved / disabled), access limited to labeling queues only, reviewer provenance on judgment rows, and "basic abuse/quality controls: rate limits, disable reviewer, and optionally require agreement checks before using labels in gold sets" (#671 body). The kid profile is therefore a *specialization* of #671's reviewer role (adds the content gate + restricted label axes), not a new access system. What's already done per the issue: `reviewer=native` resolves to the authenticated admin email on Bearer-token requests.

**(a) Content-safety filter — gating, named signals, enforcement point.**
A card enters the kid queue only if ALL hold:
1. `llm_sport_category IN ('basketball','football','baseball','hockey','soccer','golf','tennis','mma','weather','entertainment','culture','tech')` — explicitly excluding `politics`, `geopolitics`, `economics`, `health`, `crypto` (the column: `models.py:636`).
2. Kalshi ticker prefix NOT in a deny set built from the existing maps in `utils/sport_keys.py` (the ~150-entry `KALSHI_TICKER_TO_SPORT_KEY` / ~250-entry futures map give us prefix→sport ground truth; deny anything mapping outside the allowlist).
3. No taxonomy tag in `market_tags` (`models.py:664`) from a deny list (`category:politics`, war/conflict terms), and name fails `_RUSSIA_WAR_TERRITORY_RE` / `_OUTBREAK_RE` (`feed_market_quality.py:329, 243`) — reusing the exact regexes ranking already trusts.
4. **[PROPOSED]** `discover_llm.kid_safe == true` (§3.2) as a second, independent gate once v2 metadata ships; until then rules 1–3 stand alone.
**Enforcement point:** inside `utils/labeling_queue.py` at queue-build time, behind a `labeler_profile='kid'` parameter on the existing labeling batch endpoint in `admin_judgments.py`. It is a server-side filter on the labeling surface only — it never touches `GET /api/feed`, and a kid account is just a `reviewer` value, not a feed mode.

**(b) Label-quality controls — where each lives:**

| Control | Mechanism | Where |
|---|---|---|
| Honeypots | Seed each batch with ~10% gold cards: known-`kill` (resolved/stale cards from effective-settlement followups) and known-`love` (email-highlight hits already in ground truth). Score agreement per batch | Batch builder in `utils/labeling_queue.py`; gold IDs from `discover_review_decisions` accepted rows + `featured_market_captures` (`models.py:1365`) |
| Inter-rater agreement | Route ~20% of cards to ≥2 reviewers; compute Cohen's κ per label axis per reviewer pair | `reviewer` column already exists (`models.py:1500`); overlap assignment in the batch exporter `scripts/export_discover_labeling_batch.py`; κ computed in `scripts/analyze_ranking_judgments.py` (exists) |
| Per-labeler reliability | Store honeypot hit-rate + κ in `label_metadata` JSONB (`models.py:1493`) per judgment; weight labels by reliability at export time | `scripts/export_discover_labeled_dataset.py` gains a `--reliability-weight` flag [PROPOSED] |
| Axis restriction | Kid UI exposes ONLY the axes the decision table below trusts them on — fewer buttons than the adult flow | `labeling/page.tsx` profile branch |

**(c) The fun layer — built on existing primitives, no new game system:** the kid labeling session IS a Higher/Lower session with two extra taps. Each card: (1) play the existing guess (writes `user_predictions`, `models.py:1092–1107`, streaks/badges already shipped — `docs/backlog.md:1163`); (2) tap 😍/😐/💤 (= `love/fine/boring` → `overall_label` + `boring`); (3) optional "I don't get it" chip (= `clarity='confusing'`). Streak mechanics, daily-challenge framing (`/daily` page), and friend-challenge codes (`BL-xxx`) are reused as-is; a "family leaderboard" is just a filtered prediction-stats view. Sessions of 20 cards ≈ 3 minutes; 3 kids × 5 sessions/week ≈ 300 labels/week — hitting the `docs/discover-labeling.md:196` gold-set threshold in under two weeks.

**(d) Pipeline from validated kid labels → the reranker (unblocking #596/#597):** kid judgments land in the same `ranking_judgments` table with `reviewer='oliver'|'dexter'|'daphne'` and `surface='discover_kid'` → reliability-weighted export (`export_discover_labeled_dataset.py`) → gold-set eval (`evaluate_discover_label_gold_set.py` → `discover_label_eval_runs`) → **#596:** hill-climb the interestingness weights (`scripts/calibrate_interestingness.py` against the labeled CSV — finally executing 0u-N1 steps 1–2, `docs/backlog.md:360–369`) and write the tuned weights + blend into the Redis keys the feed already reads (`interestingness:blend_weight`, `feed.py:4758`) → **#597:** only after 1,000+ single-card and 500+ pairwise labels (the doc's own threshold, `docs/discover-labeling.md:201–203`), train the offline reranker on pairwise rows, deployed as a re-scoring of the top-100 candidates in the existing `precompute_interestingness` task — never in the request path.

**(e) Honest verdict — what kid signal may and may not touch:**

| Label axis | Trust kid signal? | Why |
|---|---|---|
| `clarity` ("do I get it in 5 seconds?") | **Yes — best-in-class** | A 12-year-old confused by a card is the strongest possible `needs_context` signal for a casual-fan product |
| `boring` / tapworthy on sports, entertainment, weird-news | **Yes** (within the gated subset) | Target-user proxy; Dexter's meteorologist-comparison idea (`docs/backlog.md:1231`) already shaped the roadmap once |
| `image_fit` | **Yes** | Pure perception, no domain knowledge needed |
| `audience_scope` / `resolution_importance` | **Partial** — collect, weight low | Kids systematically under-rate stakes outside their world |
| Pairwise rank order within kid-safe categories | **Partial** — use for reranker features, never as sole signal | Taste, not truth; require adult-overlap κ before inclusion |
| **Resolution truth / is_winner anything** | **Never** | Correctness is §8's domain; no human vibes, only authoritative settlement |
| **Political/geopolitical ranking** | **Never** — structurally impossible | The safety gate removes these categories from the queue entirely, so the question can't arise |

---

# 7. Multi-platform

Form-factor thesis: a probability is the most glanceable data type in consumer software — one number, always changing, always resolvable. Each Apple surface is good at a different *glance distance*.

## 7.1 Per-platform audit and redesign

**iPad (and large iPhone landscape)**
- *Current state:* `NavigationSplitView` sidebar with Discover/Sports/Browse/Search/My Stuff plus Quick Links (Weather, Economics, Politics, Entertainment, Preferences, **Calibration** — `MainTabView.swift:60–121`, Calibration at `:113`); Futures browser route exists but is hidden from navigation pending iOS-7 (`MainTabView.swift:147`; `docs/app-store-launch-plan.md:17–18`; `docs/backlog.md:1062`).
- *Unique strength:* enough width for **two correlated charts at once** — the thing the event-detail page does best (OddsChart + ScoreDifferentialChart share a domain; `docs/backlog.md:957`).
- *Redesign:* "Game Day Split" — `NavigationSplitView` detail pane shows `EventDetailView` while the sidebar column becomes a live-game rail. Reuses `EventDetailViewModel` and `FeedViewModel` (both audit-rated high-reuse) and the existing `GET /api/feed?mode=sports` fast path (`feed.py:851–857`); zero new endpoints. SwiftUI structure: the existing `iPadLayout` (`MainTabView.swift:60`) gains a third column option; models stay `nonisolated Decodable` per gotcha #26.

**Mac (Catalyst/native SwiftUI)**
- *Current state:* menu-bar extra with live game count, secondary EventDetail window, command menu, `pollLiveGames()` in `Bain_LuckApp.swift:154–185` (`MainTabView.swift:124–161`). One backlog item left: MAC-12 Today-view widgets (`docs/backlog.md:965–968`).
- *Unique strength:* **ambient persistence** — a Mac is on all day; the menu-bar extra is the only surface that can deliver "Knicks just crossed 50%" without being opened.
- *Redesign:* upgrade the menu-bar extra from a count to a 3-row probability ticker (top live game by EI, top pinned market, streak status), clicking through via the existing `NavigationCoordinator.handleURL` deep links (`NavigationCoordinator.swift:40–130`). Reuses `WidgetAPIClient`-style fetches; `@MainActor` only on the async refresh per the iOS rules.

**Watch**
- *Current state:* 9 files / 1,177 lines; three tabs — `WatchGuessView` (Higher/Lower), `WatchGlancesView` (streak + top markets), `WatchLiveView` (`WatchTabView.swift:6–10`); 4 complication families with 15-min timelines (`BainLuckComplication.swift:93–156`); session-ID auth only, `WatchAPIClient.fetchFeed(limit:10)` (`:73`).
- *Unique strength:* the **wrist-glance probability** — a complication showing one number you care about is the purest expression of the product; and Higher/Lower is a perfect 10-second wrist game.
- *Redesign:* make the complication user-pinned: complication reads the user's first pinned market (`user_pins`, `models.py:498–520`) via a `pins`-aware glance endpoint that already exists for My Stuff; `WatchGuessView` counts toward the same daily challenge (`user_predictions` accepts session_id today — `models.py:1099`). Risk note: the launch plan flags the embedded Watch app as a submission risk and recommends unembedding for 1.0 if unreliable (`docs/app-store-launch-plan.md:64–70`) — ship 1.0 without it, re-embed in 1.1.

**Widget**
- *Current state:* 4 files / 961 lines; small/medium/large families (`BainLuckWidget.swift:107`); adaptive timeline — 5-min refresh with live games, 15-min without (`:33–39`); fetches live games + discover items (`:45–60`).
- *Unique strength:* the **home-screen probability tile** — the single highest-frequency impression surface we own; for most users the widget will be seen 20x more often than the app is opened.
- *Redesign:* small widget becomes "My Number" (pinned market or followed team's next game probability, from `user_favorites`); medium adds the day's Higher/Lower teaser as a deep link into `/daily` (route exists: `NavigationCoordinator` `daily` → dailyChallenge). Reuses `WidgetAPIClient` + existing endpoints only.

**Shortcuts / Siri**
- *Current state:* `ios/shortcuts/README.md:10–34` documents **admin curation shortcuts** (boost/demote via `api.bainluck.com/api/admin/curation-signal`, admin token in query string). No user-facing App Intents found (NOT FOUND in audit) — today, Shortcuts is an operator tool, not a user surface.
- *Unique strength:* **voice-queryable numbers** — "Hey Siri, what are the Celtics' chances?" is a perfect probability-product interaction.
- *Redesign [PROPOSED]:* an `AppIntent` ("Get Probability") hitting `GET /api/events/search` (weighted FTS already ranks team names at weight A — `docs/backlog.md:1033`) and returning the aggregate probability as a spoken sentence + snippet view. New Swift target file; reuses `SearchViewModel` formatting and `APIClient`.

## 7.2 Delight-per-effort ranking

| Rank | Item | Delight | Effort | Why this order |
|---|---|---|---|---|
| 1 | Widget "My Number" small/medium | Very high — daily ambient touchpoint | Low (existing client + endpoints) | Highest impression-frequency surface; pure reuse |
| 2 | Mac menu-bar probability ticker | High for the desk-worker persona | Low | Infrastructure exists (`Bain_LuckApp.swift:154–185`) |
| 3 | Watch pinned-market complication | High but small audience | Medium | Complication scaffolding exists; needs pin wiring |
| 4 | Siri "Get Probability" intent | High novelty, real utility | Medium | New target, but search endpoint is ready |
| 5 | iPad Game Day Split | Medium (power users) | Medium-high | Worth doing after the above; biggest layout work |

## 7.3 App Store risk — called explicitly (updated against #678)

**The docs are behind reality here.** `docs/backlog.md:1076` says "No prior App Store submission attempted," but #678 (open, P0, `needs-user`) is titled *"Resubmit to App Store after addressing reviewer feedback + sign-in fix"* — Apple **already rejected a build**. The materially good news in the rejection: the recorded feedback was *compliance-shaped, not category-shaped* — an account-deletion flow was required (added overnight), and a separate new-user sign-in 500 (lazy-load of `user.preferences` on a freshly created User; fixed server-side in commit `67bb31b`, found on a family device) needed verification. There is no indication in #678 that the 5.3.4 gambling classification — the §9 existential-risk scenario — was raised. That defense (`docs/app-store-launch-plan.md:140–163`: no money, no wagers, FiveThirtyEight/ESPN comparisons, Guideline 4.7 fallback) remains untested but survived round one.

Remaining pre-resubmission gates, per the #678 checklist: verify Google AND Apple sign-in for *new* users on a physical device, verify account deletion, bump the build, CI green. Standing risks for the resubmission: (1) a different reviewer raising 5.3.4 on round two — unhedged except by the prepared defense; (2) embedded Watch app crash = whole-submission rejection (`docs/app-store-launch-plan.md:64–70`) — still recommend unembedding for 1.0; (3) visionOS enabled-but-untested (`:72–77`) — still recommend removal. Decision unchanged: resubmit with Watch and visionOS stripped, both return in 1.1. The §6 kid-labeler timeline rides TestFlight and #671 regardless of review outcome.

---

# 8. Correctness foundation

This is the credibility bedrock: the product's one-sentence promise is a *number*, and the biggest issue cluster in the tracker says parts of the number factory are broken — concretely, **16 of the 44 open issues carry `area:calibration`, including five of the eight open P0s** (#683, #698, #738, #806, #826; counts from `docs/github-issues-export.json`).

## 8.1 Quantified state of correctness

**Structural note the issue export makes clear:** #804, #805, #802, #816, and #803 are not separate problems alongside #754 — they are the **decomposition** of it (each body opens "Parent: #754"). The 71,896 pass2_guess outcomes break down as: 34,797 no-event + 13,021 no-score + 861 MLB total-bases + 1,696 NCAAB first-half + 298 broadcast-mention + the linked-with-scores remainder (25,782 outcomes on 6,574 markets, resolvable from scores we already hold — #754 body, "Event linkage" table). Don't double-count these when sizing the work.

| Problem | Magnitude (verified from issue bodies, `docs/github-issues-export.json`) | Our-bug vs upstream-gap (with the code path that proves it) | Verification query |
|---|---|---|---|
| **pass2_guess corruption** (#754, P1; inflow audit #806, P0) | **71,896** outcomes with guess-family resolution: Kalshi 48,740 / Polymarket 23,083 / DataGolf 73 (June 3 audit in #754). **4,900 actively corrupt** (winners with cal_prob < 0.50: 3,164 Kalshi @6.5% + 1,736 Polymarket @7.5%). The in-code June 4 measure is harsher: 19% error among guesses checked against settlement (3,865 + 2,205 wrong — `backfill_winners.py:2444–2449`); the two measures use different denominators (cal_prob contradiction vs settlement check). Passes 2–3/5–7 now DISABLED (`:2444–2449, 2478`) | **Our bug, fully.** We inferred winners from midrange `current_probability` (`_backfill_from_current_probability`, `:2391–2397`); Kalshi retains authoritative settlement for all ages (gotcha #101). #754 also names three of our bugs that *blocked re-resolution* (HAVING guard in `_resolve_kalshi_from_scores` et al.). Cleanup converts guesses to `api_settlement` (`_backfill_kalshi_winners_targeted`, `:243–276`; Phase 2b, `:3400`). #806 (P0) asks the exact inflow question §5.4 turns into an alert — and notes the count has *oscillated upward* despite the disable, so a writer may still exist | `SELECT resolution_source, COUNT(*) FROM futures_outcomes WHERE resolution_source IN ('pass2_guess','binary_higher_wins','multi_max_prob','pass2_loser','pass3_threshold') GROUP BY 1;` + #806's by-day inflow SQL / `scripts/audit_pass2_inflow.py` |
| **No-event sub-bucket** (#804, P1) | **34,797** pass2 outcomes on markets with no `event_id`: Kalshi 14,770 (NCAAB small conferences — North Dakota State, Middle Tennessee — plus ATP/CS2/indexes/weather) + Polymarket 19,954 (mostly esports/tennis/soccer) + DG 73 | **Mixed, mostly upstream-shaped — now confirmed by the issue's own breakdown:** the dominant buckets are leagues The Odds API doesn't cover, so no event can exist to link (LoL/DOTA precedent: `docs/backlog.md:142–145`). Residual our-bug slice: ~2,148 KXNCAAMBTOTAL where ESPN *does* cover the conference and event creation would unlock score-based resolution (#804 path 3). The matcher's `past_cutoff` skip (`prediction_market_matching.py:1138,1175`) is intentional and covered by the historical backfill | #804 lists four resolution paths, each marked UNVERIFIED for throughput — measure: `SELECT fm.source, fm.llm_sport_category, COUNT(fo.id) FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id WHERE fo.resolution_source='pass2_guess' AND fm.event_id IS NULL GROUP BY 1,2 ORDER BY 3 DESC;` |
| **No-score sub-bucket** (#805, P1, with #802/#816) | **13,021** pass2 outcomes on event-linked markets where the event has NULL scores (Kalshi 7,180 / Polymarket 5,841); biggest single bucket: 1,357 NCAAB **women's** games — "ESPN has the scores, the sync just didn't cover these events" (#805 body). Plus #802: 861 MLB total-bases (ESPN box scores lack doubles/triples) and #816: 1,696 NCAAB 1H (need halftime scores) | **Our bug for the women's-NCAAB class** (#805 says it flatly; fixes landing: `817c5b1d`, `aae4f9e0`); **upstream-ish for #802** — ESPN's box score genuinely lacks the stat, so it needs an alternative source, which is a sourcing decision, not a bug | `SELECT s.key, COUNT(*) FROM events e JOIN sports s ON s.id=e.sport_id WHERE e.status IN ('completed','closed') AND e.home_score IS NULL GROUP BY 1 ORDER BY 2 DESC;` + #805's espn_id-presence check |
| **Source coverage** (#826, P0) | Event-level coverage, production June 9: **MLB 17% Kalshi / 14% Polymarket** (431 events), NBA 19/19, NHL 40/40, WNBA 15/28 — while the link-rate metric reads 100%. "83% of MLB event detail pages are missing Kalshi probabilities… the core value prop" (#826 body) | **Reclassified: mixed, split unknown — and measuring the split is the issue's own ask.** Our ingestion bugs were real and are fixed (commits `ebe630c5`, `d0b7fda0`, plus WPS backfill `57d49d68`/`e90de40d`/`b49c238b`), but #826's root-cause section says Kalshi/Polymarket *create markets for only some games* ("a typical MLB day has 15 games but Kalshi might only have moneylines for 5–8"). The deeper finding is **metric direction**: we tracked "% of source markets linked" (denominator: their markets) when the user-facing truth is "% of our events with source data" (denominator: our events). Gotcha #53's 100%-achievable-denominator rule was satisfied by the wrong fraction | Post-fix re-measure via the event-level coverage endpoint (commit `a082d1c6`); then per-day raw-API spot-check (#826 step 2) to split residual gap into "not ingested" vs "doesn't exist upstream" |
| **Calibration math epic** (#738, P0) | MCE: overall 2.3pp but hockey 22.7 / golf 16.7 / football 19.3 (`docs/backlog.md:66`); winner coverage last measured: Kalshi 97.4% (1,401 needed), Polymarket 99.7% (281), DataGolf 100%; the status endpoint itself times out at Heroku's 30s limit (#738 body). Sub-issues: #651 (348K missing calibration_probability), #683 (150K+ zero-snapshot), #697, #698; plus #762 (DataGolf 15.4pp "likely a calculation bug") and #818 (golf props at 90%+ with no pre-game history) | **Our bug in the pipeline, not the markets:** every root cause found so far was ours — commence_time semantics (gotchas #63/#67), Part C settlement contamination (`docs/backlog.md:835–845`), DataGolf model-prediction-as-settlement (`:830–831`), spread devig display (`:842–846`). #738's acceptance criteria demand what this section recommends: 20 externally-verified spot-checks per source and "no metric in the dashboard is misleading" | Per-category MCE from `GET /api/calibration`; #738's 20-market manual spot-check per source; fix the status-endpoint timeout so the metric is even observable |

**The one architectural change that recovers the most:** an explicit, enforced **resolution authority ladder** — `api_settlement > game_score/leaderboard > clean_resolution(0/1 prices) > NULL; never guess`. Three-quarters of it already exists as scattered behavior (the disable at `:2444`, the NOT-IN guard lists at `:150–152, 520–523`, the targeted re-resolution); make it structural: a single `RESOLUTION_AUTHORITY` ordering in `backfill_winners.py` that every phase consults before writing `is_winner`, a CI test asserting no phase writes a lower-authority source over a higher one, and the pass2-inflow=0 alert from §5.4. This single change converts ~30 ad-hoc phases into a policy, retires the #754 class permanently, and is what makes the §2 calibration moat real rather than hole-y.

## 8.2 The hard call: correctness vs growth allocation

**Call: 60% correctness / 40% growth for Q3 2026, with a hard pivot to 40/60 once four exit gates hold.**

The reasoning, concretely and not piously:
1. **The product's differentiation IS the number.** The pitch (`docs/product-pitch.md` thesis: probability context without gambling pressure) and the #1 priority workstream ("Do prediction markets predict anything?" — `docs/backlog.md:62`) both stake the brand on trustworthy probabilities. A feed company can defer correctness; a *calibration-page* company cannot — the calibration page is the marketing.
2. **The errors are user-visible at exactly the wrong moments.** Hockey at 22.7pp MCE means the proof-of-accuracy page currently proves *inaccuracy* for an entire sport; the Manus sweep found grid columns summing to 8.8%/181.6% (`docs/backlog.md:455–462`). First impressions on launch traffic (App Store, §7.3) will include these surfaces.
3. **Correctness work is currently cheap and convergent.** The remaining work is mechanical (re-resolve via settlement APIs that provably retain data — gotcha #101's 100% hit rate), parallel-safe (backfill = Green in the Parallel Work Protocol), and has a natural completion state. Growth work is open-ended; correctness debt is finite right now and compounds if deferred (every new market resolved wrongly is future cleanup).
4. **But not 100/0:** the §4 cold-start fix and §7 widget are low-effort, high-information growth bets that also generate the interaction signal §6 needs. Starving them delays the label flywheel a full quarter.

**Exit gates (all four, measured, then rebalance to 40/60):** market-level winner coverage = 100% on Kalshi/Polymarket/DataGolf (`backfill-winners/status`); pass2-family inflow = 0/day for 14 consecutive days (`audit_pass2_inflow.py`); every N>100 calibration category ≤ 10pp MCE; Tier-1 event-level source coverage ≥ 90% (#826 monitor).

---

# 9. Synthesis

**Thesis (one sentence):** Bain Luck wins by being the only place where the world's prediction markets are *unified, explained, and provably calibrated* — and by converting a family-scale human judgment loop into feed quality no scaled competitor can match without rebuilding our resolved-outcome history.

## 9.1 Three-horizon roadmap — every item names the moat it deepens or the correctness risk it retires

**Horizon 1 — this quarter (Q3 2026):**

| Item | Moat deepened / risk retired |
|---|---|
| Resolution authority ladder + pass2 cleanup to zero (§8.1) | Retires #754/#806 corruption; makes the calibration moat (score 5) real |
| Correctness Console + threshold alerts (§5.4) | Retires the "silent regression" risk class (#826/#828 recurrence) |
| Doc-drift ledger PR (§1.3 artifact) | Retires the "agents build from stale spec" risk — cheap, do it first |
| App Store **re**submission per the #678 checklist (sign-in verified on device, account deletion, Watch/visionOS stripped — §7.3) | Unblocks distribution + the TestFlight labeler pool (#671/#678); P0 and `needs-user` — it's waiting on Alex, not on code |
| Kid-labeler v1: safety gate + honeypots + 😍/😐/💤 flow (§6.2) | Converts the labeled-judgment moat from latent (3) toward consumed |
| #596 first label-driven tune: calibrate interestingness weights against labels, ship via existing Redis blend | Closes the label→ranking loop — the single moat-defining step |
| Cold-start fast-lane + probe page + chip-row card, A/B on metric A1 (§4.4, within the #482 no-modal decision) | Deepens interaction-signal moat (2→3); retires the cold-start activation risk |
| Verify Heroku pg:backups + log drain (#842) and add Crashlytics (#839) | Cheap insurance on the score-5 moat itself — the calibration history is irreplaceable-by-definition, so an unverified backup schedule is an existential bug, not an ops chore |

**Horizon 2 — the year:**

| Item | Moat / risk |
|---|---|
| Calibration sample 10–20x via spreads/totals resolution from `odds_snapshots` (Subproject F, `docs/backlog.md:848–855`) | Deepens the score-5 moat with the highest-quality data class |
| `discover_llm` v2: normalized entities + persisted story_key + stakes (§3.2–3.3) | Deepens content-understanding; retires story-cap misses and dismiss-fragmentation |
| Reranker prototype (#597) gated on 1,000/500 label thresholds, run inside `precompute_interestingness` | The feed itself becomes label-trained — the moat competitors can't fork |
| Widget "My Number" + Mac ticker + Watch pinned complication (§7.2 ranks 1–3) | Deepens daily-touchpoint retention; feeds interaction signal |
| Admin IA consolidation + endpoint catalog kill-list (backlog item 24, §5.1) | Retires operator-error and silent-cost risk in 20K lines of admin surface |
| Email/preference compliance before any broadened sends (`docs/backlog.md:641–657`) | Retires a legal risk that gates every future retention channel |
| Time-horizon calibration (T-30/T-7/T-1) for non-event markets (#477) | Deepens calibration moat into the non-sports half of the catalog |
| Cross-source `canonical_market_key` backfill + match-rate audit (`docs/backlog.md:180–185`) | Deepens identity-graph moat into non-sports categories |

**Horizon 3 — multi-year:**

| Item | Moat / risk |
|---|---|
| Public calibration API / embeddable accuracy badges | Converts the score-5 asset into distribution (every citation links back) |
| Per-user calibration ("you were 73% accurate") as the retention spine | Marries interaction signal to the truth layer — both moats at once |
| Empirically derived aggregation weights via retrospective Brier (backlog P2-DS, `docs/backlog.md:1223`) | Retires the §1.2 weighted-mean/median ambiguity with evidence, not philosophy |
| Semantic search (pgvector, P6, `docs/backlog.md:1042–1047`) gated on real query traces per the FTS runbook | Deepens understanding moat only when traces justify it — the runbook discipline already exists |

## 9.2 Three existential risks, each with an instrumentable early warning

1. **Upstream access risk — Kalshi/Polymarket restrict free data or ship our product themselves.** They own the data and the audience; our §2 analysis says most feed-layer assets are forkable. *Early warning to instrument:* per-source poll failure/429 rates and markets-found deltas in the existing ingestion metrics (`docs/backlog.md` source-ingestion logging; `tasks/kalshi.py`/`polymarket.py` structured logs) — alert on a 20% week-over-week drop in `markets_found` or sustained 429s; plus a quarterly manual check of their product surfaces (a "discover feed" shipping inside Kalshi's app is the tell).
2. **App Store classification risk — the gambling-adjacent label sticks on resubmission (#678).** Round one is informative: Apple rejected for compliance items (account deletion) and did *not* raise 5.3.4 — but reviewer variance is real and a different reviewer can raise it on round two, and a 5.3.4 rejection that survives appeal cuts off the native growth plan, the Watch/Widget moats, and the TestFlight→public labeler pipeline. *Early warning:* track rejection-reason taxonomy of comparable apps (Kalshi's own iOS listing status, prediction-market app removals) monthly, and keep the web PWA path warm (GA4 platform split already exists) so distribution risk is hedged before it materializes.
3. **Trust collapse risk — we ship a wrong number at a viral moment.** One screenshot of "Bain Luck said 1.6% when Kalshi said 20%" (the literal #471 Knicks bug, `docs/backlog.md:459`) at scale undoes the calibration story. *Early warning:* the §5.4 drift strip as alerts — grid column-sum bounds, cross-source divergence >15pp on any top-50 Discover card (computable from `canonical_source_counts` + outcome probabilities already loaded in `_score_futures`), and the aggregation source-diversity alert (`tasks/monitoring.py`) — all paging, not dashboarded.

---

# 10. Adversarial self-audit

**The five weakest or least-supported claims in this document, and what would settle each:**

1. **The §8.1 cleanup-throughput assumptions.** The magnitudes themselves are now verified against the issue-body audits (`docs/github-issues-export.json`), but the *rates* are not: #804 marks all four of its resolution paths "UNVERIFIED" for throughput (e.g., "14,770 / 89 per run = 166 runs = 13+ days… UNVERIFIED whether the cursor actually reaches these series"), and #806 reports the pass2 count has oscillated *upward* since the passes were disabled — meaning an unidentified writer may still exist and the H1 "cleanup to zero" item could be open-ended rather than mechanical. *Settles it:* run #806's by-day inflow SQL for 7 days and the §8.1 by-source count twice a week apart; if inflow > 0 or the drain rate implies > 6 weeks, §8.2's "correctness work is cheap and convergent" premise needs revisiting before the 60/40 split is locked.
2. **"The loose `_MAJOR_ELECTION_RE` redefinition neuters the −30 election penalty" (§1.3, §1.2 feed row).** I verified the second definition wins at import time (`futures_highlights.py:319–329` vs `:199–219`), but not the *behavioral* magnitude — the loose regex still requires election keywords plus a listed country/office, so some penalty coverage survives. *Settles it:* a 20-line pytest comparing both regexes against the last 90 days of politics-category market names (`SELECT name FROM futures_markets WHERE llm_sport_category='politics'`), counting penalty flips; also explains whether `tests/test_futures_highlights.py` (CI table, May 18) is asserting the loose behavior — if so, tests have locked in the bug.
3. **"Kid labels reach gold-set volume in under two weeks" (§6.2c).** The 300 labels/week arithmetic assumes sustained engagement from three children — an assumption every parent should distrust. *Settles it:* a 2-week pilot measured by `SELECT reviewer, COUNT(*), MIN(created_at), MAX(created_at) FROM ranking_judgments WHERE surface='discover_kid' GROUP BY 1` plus honeypot hit-rates; if weekly volume <100 or honeypot agreement <80%, the §9 H1 plan must fall back to adult labeling (Alex + LLM-judge calibration per `docs/discover-labeling.md:171–192`).
4. **"The interestingness blend (w=0.2) is net-positive for feed quality" (assumed throughout §3/§9).** It shipped without the label calibration its own plan required (§1.3 C3); I found no eval comparing blended vs unblended ranking. *Settles it:* set `interestingness:blend_weight=0` in Redis (the kill switch at `feed.py:4758` exists for exactly this), run `scripts/audit_feed_quality.py` + email-hit@20 both ways, and keep whichever wins. This is a 30-minute experiment we should run before tuning anything else.
5. **"Calibration history is a score-5 moat" (§2).** Strength-5 assumes competitors can't reconstruct closing lines retroactively. Gotcha #99 cuts the other way: Kalshi's batch candlestick API returns 100–177 hourly candles for settled markets — a competitor could rebuild substantial Kalshi history. *Settles it:* sample 200 settled markets ≥6 months old across both sources and measure what fraction of *closing-line* prices are recoverable from public history APIs alone (Polymarket CLOB `/prices-history` + Kalshi candlesticks). If >70% recoverable, the moat is really the Odds API sportsbook history + the identity graph, and §2's flywheel defense needs rewriting around that.

**One place where two of my own recommendations are in tension — and the resolution:**

§6.2 builds the labeling flywheel on *kid-gated, sports-and-entertainment-heavy* labels, while §3.3 and the editorial direction of the feed (category base scores, election allowlists, geopolitics story caps) treat *politics/geopolitics/economics* as the core of Discover's non-sports identity — those categories are precisely the ones the kid gate excludes. Tuning interestingness weights (#596) on a kid-skewed gold set would systematically downrank the geopolitics/macro content that the email ground truth says adults find most compelling — one training signal pushing against the product's own editorial calibration. *Resolution:* stratify, don't blend. Kid labels train only the axes §6.2e trusts them on (`clarity`, `image_fit`, `boring` within gated categories), and #596's weight calibration runs per-category with kid labels zero-weighted outside the gate; adult labels (Alex + calibrated LLM judge + email ground truth) own politics/geopolitics/economics. `scripts/calibrate_interestingness.py` already accepts arbitrary labeled CSVs, so stratified runs are a flag, not a feature. A document that resolved this by "collect more labels" would be ducking it; the honest answer is that the kid pipeline is a *clarity-and-fun* engine, not a general-purpose ranking oracle, and §9's roadmap entry for #596 should say so explicitly.

---

*End of document. The next required action is not strategic: run the five §10 verification queries, fix the §1.3 doc-drift ledger in one PR, and turn the §8.1 exit gates into alerts. Strategy documents rot exactly the way CLAUDE.md's category base scores did — by being right once.*

