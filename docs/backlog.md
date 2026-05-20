# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

## Current Priority: Calibration & Data Quality

**"Do prediction markets predict anything?"** — the calibration page is the proof. This workstream makes the data trustworthy, expands the sample size, and fixes per-category accuracy.

**Monitor:** `/calibration` page, `GET /api/calibration`, `GET /api/admin/backfill-winners/status`

**Open items (ordered by priority):**
1. **Verify golf/hockey MCE drop (May 19)** — closing line fixes shipped May 18, awaiting backfill recompute
2. **Outcome count expansion (Subproject F)** — add spreads/totals from odds_snapshots to calibration (10-20x more data points)
3. ~~**is_winner coverage → 95%+**~~ — ✅ DONE May 19. Kalshi 95.6%, Polymarket 95.8%, DataGolf 95.0% (see Workstream: is_winner Backfill below)
4. **Non-NHL hockey calibration** — AHL/SHL/DEL markets excluded; need event linkage or commence_time derivation
5. **Time-horizon calibration** — evaluate non-event markets (elections, economics) at T-30/T-7/T-1 days before resolution
6. **Source "fair fight" comparison** — methodology for comparing accuracy controlling for market difficulty

**Full details:** See `Workstream: is_winner Backfill` and `Workstream: Calibration Accuracy` (Subprojects A-F) below.

---

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + `GET /api/admin/prediction-markets/tier1-compliance`

**Current state (May 18, 2026):** Overall Kalshi open link rate: **85.9%**, Polymarket: **60.7%**. Sawtooth oscillation fixed: 32 markets unlinked, 16,477 bad snapshots deleted. Date-only ticker window widened (-6h/+30h) to fix 49 tier-1 gaps from UTC/US timezone mismatch. Soccer/WNBA abbreviations added. Unsupported leagues excluded from link rate. StatPal playoff parser bug fixed. Event merge task fixed. **Next hill-climb target:** link rate denominator accuracy — season futures miscounted as game markets inflate the denominator, and cross-sport league misclassification pollutes per-sport breakdowns.

**Target: 100%** Tier 1 compliance — every MLB/NBA/NHL/NFL/PGA event with all sources linked.

**Audit tooling:** `scripts/audit_grid_accuracy.py` (51/51, 100%), `scripts/audit_event_matching.py`, Tier 1 compliance endpoint

---

## Tier 0 — Semantic Matching Accuracy (ACTIVE HILL-CLIMB)

### Four-Layer Matching Audit System

All 4 layers at 100% (April 24): Event Existence, Market→Event Linking, Futures Surfacing, Market Completeness. **Next:** Monitor during live games for regression.

**Files:** `backend/scripts/audit_event_matching.py`, `Manus/prompts/event_matching_ground_truth.md`

### Kalshi Linking Failure — Soccer, Basketball, Hockey (FIXED for current games)

**Problem (discovered May 14):** Kalshi game markets for soccer, basketball, and hockey had low link rates well below headline.

**Root causes found & fixed (May 14-15):**
1. ✅ Zero team abbreviation mappings for soccer/WNBA — added ~130 soccer + 25 WNBA abbreviations
2. ✅ Soccer game tickers miscategorized as futures — moved to correct map
3. ✅ Date-only ticker time window too narrow (±18h) — fixed to asymmetric -6h/+30h for UTC/US timezone offset
4. ✅ Unsupported leagues inflating denominator — 7 leagues added to `_UNSUPPORTED_LEAGUE_PREFIXES`
5. ✅ `kxdimayorgame` misclassified as esports — corrected to soccer_other
6. ✅ Playoff series wrong-game linkage — Phase 2 unlinks game markets >30h from event (scoped to traditional sports, not esports)
7. ✅ Pass 1 processing order — sorted by `updated_at DESC` so current games are processed first
8. ✅ Force-link admin endpoint — `POST /api/admin/prediction-markets/force-link` for manual linking
9. ✅ Match-trace diagnostic — `GET /api/admin/prediction-markets/match-trace` traces full pipeline

**Verified:** Tonight's Game 6 SAS-MIN market linked successfully (score 29.625, guard passed). Tier-1 gaps are all PAST games — current/upcoming games link correctly.

**May 18 follow-up shipped:** Tier-1 gaps already excludes settlement-open Kalshi markets for closed games, and the headline link-rate endpoint now also excludes stale open/unlinked Kalshi game markets using the game date embedded in the ticker plus a 36-hour grace window.

**Files:** `backend/app/utils/sport_keys.py`, `backend/app/tasks/prediction_market_matching.py`

### Link Rate Denominator Accuracy & League Misclassification

**Problem (discovered May 18 health check):** The link rate endpoint reports misleadingly low rates for several sport/source combinations because the denominator includes markets that *cannot* be linked (season futures, non-game markets) and because league classification errors put markets under the wrong sport.

**May 18 slices shipped:** `link-rate` now uses a stricter Kalshi denominator prefix set, excludes the esports sport bucket from event-link health metrics, filters obvious season/non-game market names from Kalshi and Polymarket denominator queries, and skips impossible sport/league bucket combinations via `is_valid_sport_league_pair()`. It also excludes stale open/unlinked Kalshi game markets whose ticker game date is more than 36 hours old, preventing settlement-open closed games from depressing the headline health rate. Production follow-up aligned the Polymarket denominator with the matcher’s `is_game_level_market()` predicate after samples showed tennis/hockey tournament labels such as `Internationaux de Strasbourg (Doubles): ... vs ...` and `World Championships: Czechia vs. Italy` were counted by broad SQL `vs` matching even though the matcher never scans them. The endpoint now reports excluded Polymarket counts and samples under `denominator_diagnostics`. Guardrail tests cover unsupported esports, season/futures name filters, stale settlement-open game markets, Polymarket matcher-predicate filtering, and the exact impossible pairs from this item (`esports/PGA`, `esports/MLB`, `cricket/EPL`, `cricket/FIFA_WC`, `cricket/UCL`, `tennis/PGA`).

**Four distinct issues:**

**1. Kalshi basketball link rate inflated denominator (open rate 53.4%)**
- 247 open markets, only 132 linked. The unlinked 115 likely include season futures (MVP, division winners, playoff qualifiers) that Kalshi labels `category="game_prop"` but are season-level markets with no corresponding event to link to.
- **Diagnosis:** Query unlinked Kalshi basketball markets and classify each as `game_level` (should be linked — real gap) vs `season_level` (should not be in the game-market denominator). If most are season-level, this is a denominator fix in the link rate endpoint, not a matching fix.
- **Fix path:** Either (a) exclude markets whose ticker matches known season-level patterns from the link rate denominator, or (b) fix `compute_market_tier()` so these markets aren't categorized as `game_prop` in the first place (see gotcha #16).

**2. Kalshi baseball link rate inflated denominator (open rate 30.8%)**
- Only 13 open markets total, 4 linked. Tiny sample magnifies the percentage. Same root cause as basketball — season futures likely counted as game markets.
- **Fix path:** Same as #1. Verify by inspecting the 9 unlinked markets.

**3. Polymarket esports near-zero link rate (open rate 0.9%, 2,310 open / 21 linked)**
- Breakdown: LOL (526 open, 0 linked), DOTA (339 open, 0 linked), VALORANT (80 open, 22 linked), generic esports (2,310 open, 21 linked).
- **Root cause:** No Odds API events exist for LoL, DOTA, or most esports tournaments. These markets *cannot* be linked because there's no event to link to — this is an upstream coverage gap, not a matching bug.
- **Fix path:** Either (a) exclude esports leagues without Odds API coverage from the link rate denominator (add to `_UNSUPPORTED_LEAGUE_PREFIXES`), or (b) create events from Kalshi/Polymarket data directly so linking can happen (larger scope, lower priority).

**4. Cross-sport league misclassification (taxonomy pollution)**
- The link rate endpoint shows impossible combinations: `esports` league `PGA`, `cricket` league `EPL`, `cricket` league `FIFA_WC`, `cricket` league `UCL`, `tennis` league `PGA`, `esports` league `MLB`.
- **Root cause:** `league_classification.py` or the LLM taxonomy enrichment task (`enrich_taxonomy_llm`) is assigning wrong `llm_sport_category` or league values. Likely a regex/ticker-prefix ordering issue similar to gotcha #32 (greedy ticker prefix matching).
- **Fix path:** Audit `league_classification.py` classification logic. For each misclassified league combo, trace back to the market's ticker prefix and fix the classification rule. Add a CI test that asserts no impossible sport/league combinations exist.

**Impact:** These issues don't affect users directly (the markets still display correctly). They make the link rate dashboard unreliable as a health metric — we can't tell real matching gaps from denominator noise. Fixing the denominator is prerequisite to the next hill-climb iteration.

**Remaining hill-climb approach:**
1. Re-measure production link rate after deploy and inspect `polymarket.denominator_diagnostics.sample_excluded_open` plus remaining unlinked open markets per source/sport
2. Classify remaining misses as `game_level` vs `season_level` vs `unsupported_league`
3. Fix any remaining taxonomy rules where the market itself is misclassified, not just filtered from health metrics
4. Use the corrected rate to target real matching bugs

**Audit endpoint:** `GET /api/admin/prediction-markets/link-rate?secret=$ADMIN_TOKEN`

**Files:** `backend/app/routes/admin_matching.py` (link rate endpoint), `backend/app/utils/league_classification.py`, `backend/app/utils/sport_keys.py`, `backend/app/tasks/prediction_market_matching.py`

### ~~Kalshi Sawtooth Oscillation~~ — FIXED (May 14)

### ~~Double-Header Date Matching~~ — FIXED (May 14)

### ~~Stat Model Lacks Pregame Prior~~ — FIXED (May 13)

### ~~Game-Markets Query Missing Kalshi Props~~ — FIXED (May 13)

---

## Tier 0.25 — Cross-Source Market Matching for Non-Sport Categories

**Problem:** Non-sport markets (politics, entertainment, economics, weather) from Kalshi and Polymarket show as separate cards even when they're the same question.

**Current state (May 18):** All 4 category pages (politics, entertainment, economics, weather) have cross-source matching. Shared utility extracted to `utils/cross_source_matching.py` (May 18) — 26 unit tests, ~200 lines of copy-paste removed from route files. Matching is exact-string only via `normalize_question()` (strip punctuation, lowercase, trim).

**Remaining:** Canonical market key coverage incomplete. Exact-string matching misses paraphrased questions (e.g., "Will the US enter a recession in 2026?" vs "US recession in 2026?"). Next steps:
1. Audit match rate: what % of Kalshi/Polymarket pairs on category pages actually pair up?
2. If low, add fuzzy matching (token overlap / Jaccard similarity) to `find_cross_source_markets()`
3. Backfill NULL `canonical_market_key` values

**Target:** <10% unmatched duplicates across all category pages.

**Files:** `utils/cross_source_matching.py` (shared), `routes/politics.py`, `routes/entertainment.py`, `routes/economics.py`, `routes/weather.py`
**Parallel Safety:** Yellow

---

## Tier 0.5 — Feed & Navigation Quality

### 0ga4. GA4 Configuration — MOSTLY DONE (May 14)

**Problem:** GA4 custom dimensions, key events, audiences, explorations, and dashboards are not configured in the GA4 console. The events are being sent from code (web and iOS), but GA4 needs manual configuration to make the data useful in reports.

**Completed (May 14):**
- ✅ All 11 custom dimensions created (Sport, League, Event ID, Event Status, Source Section, Position Index, Is Live, Is Close Game, Platform, App Version, Days Since Install)
- ✅ 2 key events marked (onboarding_complete, event_detail_view)
- ✅ 3 audiences created (Sports Enthusiasts, NBA Fans, Power Users)
- ✅ `prediction_submit` event fires on both web and iOS (code shipped May 14)
- ✅ iOS event names aligned with web GA4 taxonomy
- ✅ Screen tracking added to all 20+ iOS views
- ✅ All web pages have 3 mandatory GA4 hooks

**Remaining (come back in 24-48h):**
- Star `prediction_submit` as key event once it appears in the events list
- Create "Prediction Players" audience (prediction_submit count >= 3 in 7 days)
- ✅ "Discover Browsers" audience created (page_path = "/" or contains "/discover")
- ✅ Retention cohort exploration created (first_visit, any return event, daily)

### 0ga4b. GA4 Deep-Dive Explorations (MEDIUM PRI)

Build GA4 Explorations to answer product questions we can't see in our admin dashboard. These require data to accumulate (give it 1-2 weeks after May 14 setup), then build as Explorations.

**Discover Feed Deep Dive:**
- Funnel: feed_card_impression → feed_card_action (detail_click) → time_on_page. Where do users drop off?
- Free-form: top categories by impression volume vs action rate — what content gets shown vs what gets engaged?
- Segment comparison: authenticated vs anonymous engagement rates
- Card position analysis: does position_index correlate with action rate?

**Onboarding Deep Dive:**
- Funnel: onboarding_start → onboarding_step (by step_name) → onboarding_complete. Which step has the biggest drop-off?
- Cohort: users who completed onboarding vs didn't — do they retain better?
- Breakdown by platform (web vs iOS) — is one onboarding flow worse?

**Search Deep Dive:**
- Free-form: search_submit → search_result_click conversion rate
- Top queries with zero clicks (search intent we're not serving)
- Search → event_detail_view → return_visit chain (does search drive retention?)

**Event Detail Page Deep Dive:**
- Free-form: event_detail_view by sport, filtered to engagement_time > 30s — which sports hold attention?
- Chart interaction rate: chart_time_range events / event_detail_view — are users using charts?
- Segment: live games vs scheduled vs completed — where is engagement time highest?
- Path exploration: what do users do AFTER viewing an event detail? (feed → detail → back to feed? → another detail? → leave?)

**Cross-Platform Deep Dive:**
- User overlap: how many users appear on both web and iOS?
- Feature parity gaps: which events fire on web but not iOS (and vice versa)?
- DAU trend by platform with 7-day rolling average
- Retention by platform: is iOS retaining better than web?

**Prediction Game Deep Dive** (after prediction_submit starts flowing):
- Predictions per session distribution — how many guesses per visit?
- prediction_submit → share conversion — do correct guesses drive sharing?
- Daily challenge completion funnel: challenge_start → prediction_submit (x5) → challenge_complete
- Streak length vs return rate — do streaks drive retention?

**Files:** All console-only (GA4 Explorations). No code changes needed.
**Parallel Safety:** Green

**Preferred approach: Google Analytics Admin API (programmatic)**

The GA Admin API can create dimensions, key events, and audiences in one script run — no clicking through the console. Steps:

1. **Enable the API:** Go to [Google Cloud Console](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com) → enable "Google Analytics Admin API" for the Bain Luck project.

2. **Create a service account** (or reuse the existing Firebase one):
   - IAM & Admin → Service Accounts → Create
   - Grant it "Editor" role on the GA4 property (Admin → Property → Property Access Management → add the service account email)
   - Download the JSON key file

3. **Set env vars:**
   ```bash
   # Add to .env / Heroku config
   GA4_PROPERTY_ID=<numeric property ID from Admin → Property Settings>
   # Place the JSON key at a known path or base64-encode into an env var
   GA4_ADMIN_CREDENTIALS=/path/to/service-account-key.json
   ```

4. **Run the setup script** (`backend/scripts/setup_ga4.py` shipped May 18):
   - Uses `google-analytics-admin` Python SDK
   - Creates all 11 custom dimensions:
     - Event-scoped: sport, league, event_id, event_status, source_section, position_index, is_live, is_close_game
     - User-scoped: platform, app_version, days_since_install
   - Creates 5 key events: sign_up, onboarding_complete, event_detail_view, prediction_submit, challenge_start
   - Creates 5 audiences:
     - Sports Enthusiasts (event_detail_view count >= 3 in 7 days)
     - NBA Fans (sport = "basketball_nba", session count >= 5)
     - Power Users (sessions >= 5 in 7 days)
     - Prediction Players (prediction_submit count >= 3 in 7 days)
     - Discover Browsers (page_view where page = "/" or "/discover", count >= 5 in 7 days)
   - Idempotent — skips dimensions/events/audiences that already exist
   - Prints a summary of what was created vs skipped
   - Focused tests cover config validation and idempotent planning in `backend/tests/test_setup_ga4.py`

5. **Manual console steps (API doesn't support):**
   - Funnel exploration: session_start → page_view → event_detail_view → prediction_submit → sign_up
   - Retention cohort: first visit date, any return event, daily granularity
   - Dashboard: DAU by platform, top sports by engagement, Discover feed CTR, onboarding completion rate, prediction accuracy distribution

**Fallback approach: Claude Desktop computer use**
If the API setup is too much overhead, the prompt at `docs/ga4-setup-prompt.md` can drive Chrome through the GA4 console UI. Requires Claude Desktop with computer use enabled and a working Claude Code binary (update to latest version first — v1.7196.0 had a broken binary).

**Fallback approach: Manual**
Follow `docs/ga4-setup-guide.md` step by step in the GA4 console. ~15 minutes.

**Files:** `docs/ga4-setup-guide.md`, `docs/ga4-setup-prompt.md`, `backend/scripts/setup_ga4.py`
**Pip dependency:** `google-analytics-admin>=0.22.0`
**Parallel Safety:** Green (no runtime code changes)

### 0u. Discover Feed Quality + Personalization — ACTIVE

**Problem:** The worst Discover feed quality failures are now fixed, but the product should keep improving toward a world-class personalized prediction feed across web and native.

**Current production state (May 17):**
- ✅ Audit quality is clean: `boring-rate@20=0/20`, `ladder/bucket-rate@20=0/20`, `duplicate-family-rate@20=0/20`, `explanation-coverage@20=20/20`, `positive-archetypes@20=6/6`, `strict-variety@20=5/5`.
- ✅ Deterministic explanations are first-class and do not depend on LLM hooks for first-page comprehension.
- ✅ Hook enrichment is bounded to feed-shaped candidates only. Do **not** run hooks for the full open-market backlog.
- ✅ First-page category/archetype/story mixer caps politics/geopolitics/economics overload while preserving score order as much as possible.
- ✅ Discover debug/admin viewer exists at `/admin/discover-quality`: feed quality metrics, timing, hook coverage, ground-truth traces, per-market trace, engagement rates, top actioned cards, and promote/investigate/downrank opportunity signals.
- ✅ Web and native context snippets use concise `context_summary` copy with instant `See more` expansion; admin engagement tracks context expansion counts/rates.
- ✅ Web and native Today’s Challenge open as focused flows with explicit Next/Finish progression and first-party start/completion funnel metrics.
- ✅ Web shareability shipped: stable UTM share URLs, card-specific share copy, generated OG images, shared-link CTAs, and share/open analytics.
- ✅ Native parity pass shipped: redesigned event/futures/guess cards, fifth-card Higher/Lower cadence, share links, local category tuning, and Firebase analytics parity.
- ✅ First-party engagement capture shipped: web/native post impressions/actions to `/api/feed/interactions`, stored in `discover_interactions`.
- ✅ Server-side personalization now applies tiny bounded category and feature/entity/archetype boosts/penalties from recent Discover interactions for signed-in users and anonymous sessions, layered on top of favorites, pins, sport affinities, and roster-player matching.
- ✅ Authenticated feed items now expose per-card `personalization_trace` diagnostics, and `/admin/discover-quality` renders multiplier, score delta, category/feature-affinity deltas, and reasons when present.
- ✅ Web and native swipe semantics are explicit: right swipe records `like` / "more like this" and keeps the card; left swipe records `unlike` / "less like this" and only hides the card for the current session.
- ✅ Cheap LLM Discover intelligence shipped: async feed-shaped metadata enrichment writes topic/subtopic/entities/archetype/audience scope/salience/junk flags/comparison axes to `market_metadata->discover_llm`; ranking consumes only cached metadata with bounded nudges; daily LLM eval writes advisory admin-review proposals and compares against Polymarket email highlights.
- ✅ Polymarket email-highlight sheet can now feed the Discover audit through CSV path/URL env vars, producing `email-hit@20` / `email-hit@50` coverage without changing ranking.
- ✅ Email ground-truth parsing now accepts stable `Audit Export` headers, records row count/latest-date/stale metadata, supports private Google Sheets via service-account auth, and surfaces export errors in audit/admin diagnostics instead of crashing.
- ✅ `/admin/discover-quality` now separates Polymarket email-highlight misses into a dedicated editorial audit panel with bucket counts, sheet scores, hooks, DB trace entry points, and recommended actions.
- ✅ `/admin/discover-quality` now includes a card-level human review queue for aggregate Discover feedback, segmented by web/native and signed-in/anonymous, with promote/downrank/investigate candidates by category, archetype, and market family.
- ✅ Anonymous and signed-in Discover requests use session/user interaction history to suppress recently seen cards and longer-lived dismisses, reducing repeated cards across visits.
- ✅ Low-signal regional US election/primary markets and niche sports families are downranked and story-capped so they cannot dominate Discover just because they are liquid or timely.
- ✅ TestFlight feedback loop is instrumented: `/admin/discover-quality` shows repeat-card rate, stale-impression rate, runtime suppression config, top repeated/stale cards, and persisted review decisions. Native rage-shake reports include visible Discover cards, current card, and recent Discover interactions.
- ✅ Discover launch-health admin is now a hill-climb console: stale impression rate and repeat rate are the primary launch blockers, top stale/repeated cards link to their detail pages, review decisions are idempotent, reviewed cards leave the queue, and promote/downrank decisions apply bounded feed score nudges.
- ✅ Sports futures staleness guard tightened: Discover now treats sports futures at 90%+ leader probability as effectively resolved unless the leader had a real underdog/surprise journey.
- ✅ Regional/team personalization guardrails are covered: Red Sox/Boston interactions bridge to Massachusetts/New England topics, unlike remains a bounded soft downrank, low-signal sports are grouped/downranked, and regional public-interest markets can still qualify as compelling.
- ✅ Deterministic Discover explanation guardrails are covered: non-sports boosts, low-signal sports suppression, first-page diversity, named movers, source disagreement, opening-probability surprises, stale copy suppression, and context-summary fallbacks.
- ✅ Editorial quality scoring keeps improving: daily public-equity direction/threshold markets are now treated as low-quality Discover filler, absurd-but-real public-interest markets such as aliens/UFO disclosure are compelling, and futures story keys are preserved through final first-page mixing before response cleanup.
- ✅ Discover now has a conservative editorial tail backfill: ranks 1-20 stay untouched, but a few high-scoring recall stories such as Survivor, Spotify/Billboard, Rotten Tomatoes, recession, Xi Jinping, 2028 presidential, and FIFA World Cup can be swapped into ranks 21-50 when they would otherwise sit below saturated 100-score finance/politics cards.
- ✅ Web Discover no longer lets stale local `discover_dismissed` state collapse a healthy feed into a tiny sports-only residue after client hydration/refresh; legacy indefinite dismissals are cleared, new local dismissals expire after 6h, and local filtering is bypassed if it would leave fewer than 20 items.
- ✅ Sparse open-market history backfill now runs for feed-visible Kalshi/Polymarket markets so Discover charts have recent snapshots even when live polling missed a market.
- ✅ Live prediction market poll (every 2 min) now writes `FuturesOddsSnapshot` rows alongside `WinProbSnapshot`, giving game-linked markets 2-minute chart granularity.
- **ACTION (May 19):** Verify snapshot distribution improvement. Run `POST /api/admin/snapshots/distribution`, wait 2 min, then `GET` — Kalshi/Polymarket `avg_snapshots` should be >1. Spot-check a non-sports Discover market detail page (e.g., Taylor Swift, 2028 election) for a real trend line. If still sparse, check whether the `open_sparse` backfill ran (`heroku logs --app bainluck | grep "open_sparse"`).
- ✅ Deterministic futures copy polish shipped: movement is described in probability points, source-disagreement and monthly-resolution snippets name the leader when available, stale past-resolution cards suppress generated copy, and context snippets avoid repeating the card title prefix.
- ✅ Dedicated `/daily` page shipped: five curated Higher/Lower calls, progress, streak/local completion tracking, countdown, replay, prediction submission, and shareable text summary.
- ✅ Friend challenge landing page shipped at `/challenge/[id]`: loads existing challenge codes, handles Higher/Lower acceptance, participants/results states, and share/copy affordances.
- ✅ Shareable prediction scorecards shipped (May 17): OG image generation via Next.js `ImageResponse`, share button on `/discover/stats`, scorecard page at `/discover/scorecard`.
- ✅ Onboarding category selections now persist to server via `useCategoryInterests` hook (May 17). Previously selections were lost on completion.

**Immediate priority — Discover ranking fixes (May 18 health check findings):**

The following 8 items address three interconnected problems discovered in the May 18 health check: (a) foreign soccer events dominate the feed because the "upset" headline bypasses Discover event demotion regardless of league tier, (b) geopolitics floods futures slots with near-identical Russia-war markets, pushing entertainment to position 69+, and (c) left-swipe personalization is too weak to suppress high-scoring items.

**~~0u-R1~~ through ~~0u-R7~~** — ALL SHIPPED May 18. League-tier upset gating, Russia-war story key, localStorage dismiss persistence, election allowlist, soccer league allowlist, steeper swipe penalties, story-key dismiss propagation. All have focused test coverage (R8 partial).

---

**Next-wave ranking improvements (after R1-R8 ship):**

These items go deeper into ranking quality. They're ordered by expected impact and should be tackled after the immediate fixes land and we can measure the improved baseline.

**0u-N1. Wire `market_interestingness.py` into feed ranking**

The interestingness scoring scaffold (`utils/market_interestingness.py`, shipped May 18) has 8 calibrated signals (decisiveness, multi-source, recency, movement, resolution proximity, category novelty, volume, LLM quality) but is not yet consumed by the feed. Steps:
1. Export ground-truth labels from Polymarket email highlights + admin review decisions to CSV
2. Run `scripts/calibrate_interestingness.py` against labels, hill-climb weights for Precision@20/Recall@50
3. Add `interestingness_score` column to `FuturesMarket` (nullable float, backfilled by Celery task)
4. In `_score_futures()`, blend interestingness score with existing futures highlight score (e.g., `final = 0.6 * highlight + 0.4 * interestingness`)
5. A/B compare old vs blended ranking via admin Discover viewer

**Depends on:** Ground-truth labels (item 5 in existing next phases), calibration script (shipped)

**~~0u-N2~~, ~~0u-N3~~, ~~0u-N4~~** — ALL SHIPPED May 18. Stronger LLM metadata penalties, category-aware event-vs-futures balancing with entertainment floor, semantic dismiss propagation via Jaccard similarity.

**0u-N5. Engagement-calibrated ranking weights**

Use actual engagement data (clicks, shares, swipes) to calibrate ranking weights instead of hand-tuning. Steps:
1. Build a nightly export of Discover interactions joined with market metadata (category, score, position, interestingness components)
2. Compute engagement rate by score bucket and category — identify where the ranking over/under-values content
3. Use the interestingness calibration script to hill-climb weights against engagement as ground truth (complement email highlights)
4. Add an admin panel showing engagement-rate-by-category and score-vs-engagement scatterplot
5. Only apply engagement-derived weight changes after human review (no auto-tuning initially)

**Depends on:** GA4 data accumulation (2+ weeks), interestingness scaffold (shipped), admin review queue (shipped)

**Files:** `backend/scripts/calibrate_interestingness.py`, new export script, admin panel

**May 18 export/reporting slices shipped:** `backend/scripts/export_discover_interestingness.py` exports Discover interactions joined with futures/event metadata to CSV or JSONL, including impression/action counts, positive/negative engagement rates, labels, category share, probability, movement, volume, and source count. It is read-only, supports `--print-sql`, feeds directly into `scripts/calibrate_interestingness.py`, and now has `--summary` / `--summary-json` reporting for engagement by category and feed-score bucket plus over/under-ranked category opportunities. `/admin/discover-quality` also shows feed-score bucket engagement from `/api/admin/discover-engagement`. Remaining work: scheduled export/import, richer admin scatterplots, and human-reviewed weight changes.

---

**Next phases:**
1. Fix the iOS Xcode package-resolution blocker before TestFlight: `xcodebuild -resolvePackageDependencies` times out downloading Firebase binary targets from `dl.google.com` (abseil, grpc, FirebaseAnalytics, etc.). This is a network/environment issue, not a package version conflict — `app-check` 11.2.0 is a transitive dependency with zero direct usage in code. **Workaround:** Open in Xcode GUI (which uses a different download pipeline), or try on a different network. Deleting `Package.resolved` and re-resolving may also help if versions have drifted.
2. Hill-climb Discover launch health to zero before distributing TestFlight broadly:
   - Target `stale_impression_rate=0%`. Any currently stale card shown in Discover is a launch blocker.
   - Target `repeat_rate≈0%` for normal browsing sessions. Repeats after long windows are acceptable; repeated cards in short sessions are not.
   - Run focused hill-climb sessions before inviting friends/family: generate Discover sessions, capture the current repeat/stale rates, fix the biggest offender bucket, refresh/re-measure, and repeat until the launch-health scoreboard is clean.
   - Record each session's before/after rates and the fix category (`staleness rule`, `suppression window`, `data cleanup`, `family cap`, `card ranking`) so patterns become automatable.
   - Review the top stale/repeated cards from `/admin/discover-quality`, open detail links, then either fix the data source/staleness rule or tighten runtime guardrails.
   - Re-run the page after each change and keep a simple before/after note in this backlog item until both metrics are clean.
3. Make launch-health remediation more automatic:
   - Add one-click "hide this stale card now" / "suppress this repeat family" actions with explicit expiry.
   - ✅ Root-cause labels shipped May 18 for stale cards in feed quality debug and admin engagement launch-health output: closed/resolved market, non-open status, past resolution date, no recent market update, no recent movement, settled outcomes, effectively resolved leaders, soft-settled sports binaries, and completed-old events.
   - ✅ Added a small trend panel for repeat/stale rates over the last 1h/24h/7d so we can tell whether fixes are working.
4. Automate ranking progress after manual hill-climb sessions:
   - Convert repeated manual fixes into durable rules: auto-hide stale root-cause classes, auto-cap repeat families, and auto-promote/downrank only when a reviewed pattern has enough impressions and confidence.
   - Add a background job that writes daily Discover ranking deltas: repeat/stale rates, cards fixed, cards newly offending, top root causes, and whether automated rules improved or regressed the launch-health metrics.
   - Add guardrails before automation can affect ranking globally: minimum impression counts, max score delta, expiry windows, and an admin rollback path for any automated rule.
5. Automate the Polymarket email-highlight ground truth pipeline:
   - Keep the Apps Script as the Gmail parser, with a clean `Audit Export` tab using stable columns.
   - Configure production with `POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID` and `POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME=Audit Export` so backend jobs read the restricted sheet through the shared Firebase service account.
   - Add a scheduled backend/admin import path that fetches the export and persists a snapshot, so audit/admin metrics do not depend on fetching Google Sheets during the request.
   - Alert or surface an admin warning when the export is stale for more than 48 hours, row count drops sharply, or parse coverage changes unexpectedly.
   - ✅ First external-curator source lane shipped as an advisory local-input parser: `EXTERNAL_CURATOR_GROUND_TRUTH_PATHS` accepts CSV/JSON/JSONL exports, keeps only public URL metadata, performs no scraping/network calls, dedupes rows, and feeds audit/admin debug alongside email highlights. Source health/freshness diagnostics now report per-curator row counts, latest dates, stale flags, and platform mix in `/admin/discover-quality`. `scripts/normalize_external_curator_ground_truth.py` normalizes manually collected social/newsletter exports or copied one-market-per-line text into canonical CSV/JSONL for production config.
   - **Social ground truth definition:** curated image/caption posts from prediction-market editorial accounts that feature specific markets and explain why they are interesting. Initial target accounts: `@kalshi`, `@kalshisports`, `@kalshifacts`, `@polymarket`, `@polymarketsports`. These should be treated as *editorial ground truth* only after extraction identifies the referenced market/question, captures the account/post URL/date, preserves any caption/reason text, and stores evidence for human review. Do not rely on direct request-time Instagram scraping; use manual exports, screenshots, or approved capture tooling, then run OCR/vision/caption parsing offline into the external-curator schema.
   - ✅ Manus extraction scaffold shipped: `scripts/extract_social_ground_truth_with_manus.py` accepts approved CSV/JSON/JSONL IG post manifests with captions/OCR/image URLs, prompts Manus for strict JSONL extraction, preserves evidence/confidence/notes, and writes reviewable rows compatible with the external-curator lane. `scripts/review_social_ground_truth.py` now applies explicit accept/reject decisions and emits an accepted-only JSONL file for `EXTERNAL_CURATOR_GROUND_TRUTH_PATHS`, keeping social-derived rows gated before they affect ranking metrics.
   - ✅ Reviewed curator persistence scaffold shipped: `external_curator_ground_truth_items` stores accepted social/newsletter rows; `scripts/import_external_curator_ground_truth.py` imports accepted files; Discover debug/admin diagnostics merge DB rows with file-configured rows so reviewed social ground truth can survive dyno restarts without hot-path scraping. Admin can inspect persisted source health at `/api/admin/discover-external-curator-ground-truth/status` and queue imports at `/api/admin/discover-external-curator-ground-truth/import`; a daily background import now runs shortly before the diagnostics snapshot. `scripts/build_social_post_manifest.py` normalizes approved social capture exports into the Manus manifest shape, filters target handles by default, and requires caption/OCR/image evidence without scraping. `scripts/run_social_ground_truth_pipeline.py` chains capture manifest, Manus prompt/extraction, and review/accepted export for local daily operation. `scripts/run_daily_social_ground_truth.py` now adds a date-stamped operator wrapper that can fetch approved capture export URLs, produce manifest/prompt/review/accepted files, print next review/upload commands, and optionally upload accepted rows through the admin API. Manus API feasibility check found one-off tasks only (`task.create/detail/listMessages/stop`), no schedule endpoint; `.github/workflows/social-ground-truth.yml` now provides the controllable daily/manual scheduler once `SOCIAL_GROUND_TRUTH_CAPTURE_URL`, `MANUS_API_KEY`, and optionally `ADMIN_TOKEN` are configured. Next social-ground-truth work: wire an approved recurring capture/export source into this pipeline.
6. Add persisted matching diagnostics for email-highlight rows: matched `futures_markets.id`, current Discover rank, score bucket, missing reason, category/story family, and whether the card had usable image/context/explanation treatment. May 18 slices: added `discover_ground_truth_diagnostics` plus `scripts/snapshot_discover_ground_truth_diagnostics.py` to persist current debug API hit/miss rows for combined, email, and external-curator ground truth under a run ID; added a daily background task plus admin trigger/read endpoints so production can queue snapshots without Heroku CLI access; added `/admin/discover-quality` run trends, row drilldown, inline pipeline traces, quick filters, and pagination. Next: persist reviewed curator rows and add a non-request-time import snapshot for email/curator ground truth.
7. Use email-highlight misses as an audit signal first, not a direct ranking boost. Tune candidate pools, story mixing, explanation/media treatment, and fun-market surfacing only after reviewing false positives and duplicate-family risk. May 18 slices: added a bounded `nonsports_editorial_recall` candidate pool for low-volume high-texture terms (aliens/UFO, AI labs/models, awards/TV, health/weather risks) so these markets enter scoring while still passing through normal quality caps; then promoted absurd-but-real public-interest markets while demoting daily public-equity direction filler. May 18 follow-up: expanded recall terms for measured misses (`recession`, `Spotify`, `Billboard`, `Rotten Tomatoes`, `Xi Jinping`, `SpaceX/Starship`) and added a sports editorial recall pool for mainstream futures such as FIFA World Cup, Champions League, Super Bowl, NBA Finals, Stanley Cup, and World Series, with a `story:fifa_world_cup` cap. A tail backfill now preserves ranks 1-20 but can swap up to six strong recall stories into ranks 21-50 when they are eligible but stuck below same-score clusters; 2028 presidential markets and reviewed major US civic-power stories such as LA Mayor / Virginia redistricting / 2026 midterms are included in that tail lane. Audit matching now treats `Recession this year?` and `US recession by end of 2026?` as equivalent so the hill-climb metric does not count represented macro stories as false misses. The DB trace also distinguishes exact/source-equivalent misses from loose related markets, so World Cup squad/final props no longer look like ranking failures for exact World Cup winner ground-truth rows, and admin/debug bucket counts are recomputed after DB trace root causes are attached. SpaceX IPO, Spotify/Billboard, and text-matched FIFA World Cup markets now share story keys so represented sibling variants are classified correctly even when upstream categories are loose.
8. Use the aggregate feedback review queue daily during TestFlight: accept only human-reviewed ranking changes at first, prioritizing high-dismiss/high-rank downrank candidates, high-open/share/context-expand low-rank promote candidates, and rage-shake reports where Discover context identifies repeated or stale cards.
9. Add account-level preference sync so web/native local tuning can merge into server-side profiles after sign-in.
10. Add comparison-game cards as part of the Discover game cadence, pairing high-interest markets across categories and recording those guesses separately from Higher/Lower cards.
11. Use engagement opportunity signals, repeat/stale launch-health signals, rage-shake context, and Polymarket email-highlight misses to tune ranking, card design, and explanation/media treatment.

**Files:** `backend/app/routes/feed.py`, `backend/app/routes/admin.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/app/utils/personalization.py`, `backend/app/utils/polymarket_email_ground_truth.py`, `backend/scripts/audit_feed_quality.py`, `frontend/app/discover/page.tsx`, `frontend/app/admin/discover-quality/page.tsx`, `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`, `ios/Bain Luck/Bain Luck/Views/BugReportView.swift`
**Parallel Safety:** Yellow

### ~~0n. Navigation Redesign~~ — DONE (May 11-12)

### ~~0s. League Pages — ALL PHASES SHIPPED~~ (May 6-17)

### ~~0r. Golf Data Quality Issues~~ — FIXED (May 18)

---

## ~~Rage Shake Triage #7 (May 17) — Bugs #49-58~~ — ALL 7 FIXED (May 17)

---

## ~~Manus Sweep Findings (May 15, 2026)~~ — ALL 8 FIXED/CLOSED

---

## Manus Sweep Findings (May 11, 2026) — 13/14 RESOLVED

All resolved except MS-13 (info only). MS-8 (MLB charts), MS-11 (stale probability), MS-14 (EPL/UFC/Tennis) fixed May 13-17.

### MS-13. Missing Sport Coverage (INFO)

UFC/MMA, Tennis, F1, Esports have upstream markets but no dedicated pages. Feature gap, not bug.

---

## ~~Rage Shake Triage (May 7-8)~~ — ALL 14 ITEMS RESOLVED

---

## ~~Rage Shake Triage #3 (May 11) — Bugs #25-30~~ — ALL 6 FIXED (May 12)

---

## Rage Shake Triage #6 (May 16) — Bugs #41-48

8 reports, BR41 dismissed (transient). 4 of 5 distinct issues fixed: ~~BR42/43~~ (tier filter), ~~BR44/46~~ (soft-settled binary filter), ~~BR45~~ (sign-in 500, `created_at` server default), ~~BR48~~ (normalization threshold).

### BR47. Netflix Show Outcomes All 33% — INVESTIGATED May 16, NOT A CODE BUG

Not a normalization bug — probabilities are genuinely flat in the database. The "100%" in the hook description is stale. Fix: re-run hook enrichment or add staleness detection that regenerates hooks when data contradicts them.

---

## Rage Shake Triage #4 (May 13) — Bug #31

### BR31. Stale NBA Playoff Data in Discover Feed (P2)

**Problem:** Discover feed shows NBA markets with outdated playoff context — Knicks and Thunder have already advanced to the conference finals, Heat are eliminated, but cards still show stale probabilities that don't reflect these results. "The data we show in the Discover feed must never be stale."

**Root cause (likely):** This is a deeper version of BR29/BR30. The staleness filters (leader ≥95%, 14-day NULL resolution_date, 7-day no-movement) aren't catching all cases. Specific gaps:
1. **Sports futures that are "open" but effectively decided** — e.g., "Will the Heat make the finals?" is still `status=open` on Kalshi because the market hasn't settled, but the team is eliminated. The leader probability may be at 90-94% (below the 95% threshold).
2. **Playoff progression markets** — "Will X advance to round Y?" markets resolve based on game results, but Kalshi/Polymarket may lag hours or days in settling. During that lag, stale cards appear.
3. **No game-result cross-reference** — the feed doesn't check whether the teams in a futures market have been eliminated from the playoffs. It only checks the probability level and market status.

**Fix options (ordered by complexity):**
1. ~~**Lower staleness threshold further** — drop from 95% to 90% leader probability for sports futures. Risk: some interesting markets between 90-95% get hidden.~~ ✅ Shipped May 14 with an opening-probability guard so real underdog/surprise journeys can still surface.
2. **Add an "effectively settled" heuristic** — for sports futures, if the leader has been ≥90% for >24h with no movement, treat as settled regardless of exact probability.
3. **Cross-reference game results** — when a team is eliminated (completed playoff series), mark all their "will they advance" markets as stale. Most robust but requires connecting futures markets to series outcomes.

**Current status:** Initial hardening shipped via option 1 plus underdog-journey guard. Next best improvement remains option 2, then option 3 for playoff-series truth.

**Files:** `backend/app/routes/feed.py` (staleness filters ~line 2131), `backend/app/utils/feed_market_quality.py`
**Parallel Safety:** Yellow

---

## Rage Shake Triage #5 (May 15) — Bugs #32-40

9 reports, 6 of 7 distinct issues fixed: ~~BR40~~ (Apple Sign-In audience), ~~BR39~~ (pill wrapping), ~~BR37~~ (economics parse), ~~BR36~~ (politics normalization), ~~BR32~~ (My Stuff top markets), ~~BR-MARKUP~~ (annotation coordinates).

### BR38/33/35/34. Feed API Failures — Discover, Sports, and Challenges All Down (P1)

**Problem:** Four reports from a ~20 minute window (May 14 6:47-7:00 PM ET) — feed endpoints returning errors. Likely transient (deploy-triggered outage or connection pool exhaustion). Needs Sentry/Heroku log investigation for that window.

**Files:** `backend/app/routes/feed.py`, `ios/.../Views/DiscoverView.swift`, `ios/.../Views/FeedView.swift`
**Parallel Safety:** **RED — collides with Discover thread.**

---

## Rage Shake Triage #9 (May 19-20) — Bugs #76-83

### ~~BR83. Win Prob Chart Missing Period Markers~~ — FIXED May 20

Soccer halftime fallback in OddsChartView was overwriting numeric inning markers. Fixed by only applying fallback when no markers exist.

### ~~BR80. Futures Detail "Failed to Load Timeline"~~ — FIXED May 20

Shows "Limited price history available" instead of error on sparse markets.

### BR79. Discover Event Card Missing Sport Label + Lacrosse Display (P2)

**Problem:** Duke vs NC State lacrosse game (21-12) shows in Discover with no sport identifier. User can't tell what sport this is. Also says "Won as 29% underdog" which is confusing without sport context. Two sub-issues:
1. No sport label on Discover event cards (need sport badge like "LACROSSE" or sport icon)
2. Lacrosse scores (21-12) look unusual without context

**Screenshot:** `/tmp/bug_79.jpg`
**Files:** Native Discover event card component, `backend/app/routes/feed.py` (event card data)
**Parallel Safety:** Red (touches Discover card rendering — defer to Discover thread)

### BR78. Stale Golf Tournament in Discover (P2)

**Problem:** "Truist Championship Winner" with Rory McIlroy at 13% showing in Discover. Tournament may be completed/resolved but market still appears as active. Staleness filter should catch this.

**Screenshot:** `/tmp/bug_78.jpg`
**Files:** `backend/app/routes/feed.py` (staleness), `backend/app/utils/feed_market_quality.py`
**Parallel Safety:** Red (touches Discover ranking — defer to Discover thread)

### BR77. Stale Weather Market in Discover — 6 Days Past Resolution (P2)

**Problem:** "Will it rain in NYC on May 11, 2026?" showing in Discover on May 17 — 6 days after the resolution date. The staleness/resolution filter should catch markets past their resolution date.

**Screenshot:** `/tmp/bug_77.jpg`
**Files:** `backend/app/routes/feed.py` (staleness), `backend/app/utils/feed_market_quality.py`
**Parallel Safety:** Red (touches Discover ranking — defer to Discover thread)

### ~~BR76. Game Shows "Live" After Completion~~ — FIXED May 20

ESPN sync now transitions live → completed on post/final. StatPal does the same for finished. Fallback task tightened to per-sport max + 30min.

---

## Rage Shake Triage #8 (May 17) — Bugs #60-75

14 reports, 13 fixed. Fixed: ~~BR60~~ (Yes/No framing), ~~BR61/75~~ (text truncation), ~~BR63~~ (prediction stats auth), ~~BR64~~ (tuning section removed), ~~BR65/72~~ (baseball inning labels), ~~BR66~~ (sports feed supplemental page), ~~BR68~~ (final 0.0), ~~BR69~~ (calibration buckets), ~~BR70~~ (My Stuff categories), ~~BR73~~ (filter pills removed), ~~BR74~~ (pull-to-refresh state reset).

### BR62. Better Aggregation for Related/Clustered Markets (P2)

Related markets need better aggregation so users see one coherent question instead of fragmented rows. May 17 progress: Discover feed now emits `group_id`/`group_type`, native grouping prefers backend IDs. Full cross-surface aggregation remains open.

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/feed_market_quality.py`, category routes
**Parallel Safety:** Red (touches feed ranking/grouping)

---

## Email Infrastructure: Compliance + Provider Migration (PREREQUISITE for any user-facing email)

**Problem:** We're sending emails (bug fix notifications, daily digest) via Gmail API with OAuth. This works for sending to Alex only, but before sending to ANY other user we need proper compliance.

**Required before scaling beyond Alex:**
1. **Email preference model** — `email_preferences` JSONB column on `users` table: `{digest: bool, bug_updates: bool}`. Default all false (opt-in only, never default-on).
2. **Opt-in during onboarding/sign-up** — checkbox or toggle during the team-selection flow. Not pre-checked.
3. **Preference management** — toggles in web Preferences page and iOS PreferencesView. Each email type independently controllable.
4. **Unsubscribe link in every email** — one-click URL (e.g., `bainluck.com/unsubscribe?token=X`) that flips the preference without requiring sign-in. JWT or HMAC-signed token. Legally required (CAN-SPAM).
5. **List-Unsubscribe header** — RFC 8058 one-click unsubscribe header so Gmail/Apple Mail show the native unsubscribe button.
6. **Email provider migration** — Gmail API with OAuth refresh tokens is fragile for production (tokens expire, rate limits). Before scaling, migrate to a proper transactional email provider (SendGrid, Postmark, or AWS SES). Keep `bugs@bainluck.com` as from address via domain authentication.
7. **Digest task queries opted-in users** — replace `DAILY_DIGEST_RECIPIENTS` env var with a DB query of users where `email_preferences->>'digest' = 'true'`.

**Current state (May 18):** Gmail API working, daily digest scheduled at 8am ET, only sending to Alex via env var. Bug-fixed notification task is limited to one resolved bug report at a time and now refuses unresolved reports or reports without a resolution summary. There is still no persisted email preference model or one-click unsubscribe token/route, so `List-Unsubscribe` must not be added yet and emails must not be broadened beyond this lifecycle notification path.

**Files:** `backend/app/models/models.py`, `backend/app/tasks/daily_digest.py`, `backend/app/tasks/bug_notifications.py`, `frontend/app/preferences/page.tsx`, `ios/.../Views/PreferencesView.swift`, new `backend/app/routes/unsubscribe.py`
**Parallel Safety:** Yellow

---

## Bug Report Lifecycle: Auto-Status + "Your Bug Was Fixed" Emails

### ~~Phase 1: Backend data foundations~~ — DONE (May 18)

### Phase 2: "Your bug was fixed" email (NEXT)

Core Celery task shipped May 18: eligibility gates, Gmail multipart messages, admin PATCH auto-enqueue, header-injection rejection. **Remaining:** Google Cloud service account with domain-wide delegation for `bugs@bainluck.com`, finalize preferences/unsubscribe/compliance before broad sends.

**Dependencies:** Google Workspace (done), service account + Gmail send scope, OpenAI API key (configured)

### Phase 3: Automation (LATER)
- Auto-mark bug reports as `fixed` from commit messages referencing "BR{N}"
- Surface unresolved bug reports in admin dashboard with age badges

**Files:** `backend/app/tasks/bug_notifications.py`, `backend/app/routes/admin.py`, `backend/app/routes/feedback.py`
**Parallel Safety:** Green

---

## Rage Shake Triage #2 (May 11) — Bugs #18-24

Fixed: ~~BR19, BR20, BR21, BR22, BR23, BR24, BR-NAV~~. ~~NATIVE-DESIGN~~ all 5 pages polished (May 13).

### BR18. Missing Kalshi for TB vs BOS — WAITING ON MATCHING CYCLE

TB abbreviation in `sport_keys.py` exists but may not be disambiguating MLB vs NHL correctly. Wait for matching cycle; investigate if still unlinked.

### BR-PIN. Cross-Platform Pin Sync + My Stuff Display — PARTIALLY DONE (May 13)

Web pin sync fixed and cross-device persistence verified. **Remaining:** My Stuff dedicated pinned section (web + iOS), optimistic update after pinning, iOS→server sync verification.

**Files:** `ios/.../Services/PinManager.swift`, `ios/.../Views/MyStuffView.swift`, `frontend/app/my-stuff/page.tsx`, `backend/app/routes/user.py`
**Parallel Safety:** Yellow

---

## Tier 1 — High Leverage, Do Next

### ~~Bug Report Admin Improvements~~ — ALL DONE (May 13-18)

Burndown chart, category tagging, resolution time tracking, auto-categorization all shipped.

### ~~PRD Update~~ — DONE (May 15)

### ACTION ITEM: Check Snapshot Distribution Results (May 18)

**Deployed:** `GET /api/admin/snapshots/distribution` (reads from Redis cache, computed by Celery task).

**Steps:**
1. Trigger: `POST /api/admin/snapshots/distribution?secret=$ADMIN_TOKEN`
2. Wait 2-5 min for Celery to finish
3. Read: `GET /api/admin/snapshots/distribution?secret=$ADMIN_TOKEN`

**What to look for:** `sparse_pct` (outcomes with 0-5 snapshots) and `median_snapshots` per source. If Polymarket or Kalshi median < 20, the "flat line" chart problem is widespread and the history backfill tasks need their limits raised or cadence increased. If sparse_pct > 30% on any source, investigate whether the backfill is targeting the right outcomes.

**Context:** User reported flat-line charts on futures detail pages — single data point stretched across time. Zero-snapshot outcomes are down to 0.2%, but sparse snapshots (1-5) may still cause poor chart experiences.

**Files:** `backend/app/tasks/monitoring.py` (task), `backend/app/routes/admin_data_quality.py` (endpoints)

---

### Workstream: is_winner Backfill (ACTIVE — monitor every session)

**Goal:** Every resolved outcome has correct `is_winner`. Without this, the calibration curve is built on a biased subset.

**Monitor:** `GET /api/admin/backfill-winners/status?secret=$ADMIN_TOKEN` → check `sources` array + `stuck_diagnosis`.

**Current state (May 19, 2026):**
| Source | Resolved | has_winner | Tradeable | Coverage | Target |
|--------|----------|------------|-----------|----------|--------|
| Kalshi | ~68K | ~63K | ~66K | **95.6%** | ✅ |
| Polymarket | ~86K | ~80K | ~84K | **95.8%** | ✅ |
| DataGolf | 80 | 76 | 54 | **95.0%** | ✅ |

Coverage now excludes untradeable ghost markets (42K total) from the denominator — markets where ALL outcomes have null calibration + opening probability. These can never have a winner identified.

**What shipped (May 18-19):**
- ✅ Phase 3: Polymarket API settlement — fetches `/events/{event_id}` from Gamma API, matches by condition_id, sets is_winner from `outcomePrices`. Groups by event to avoid duplicate API calls. 500/run.
- ✅ Coverage metric fix — `needs_backfill` excludes untradeable ghost markets (all outcomes have null cal+open)
- ✅ Phase 2 limit: 2000 → 5000 per run
- ✅ DataGolf resolution from leaderboard — new `_backfill_datagolf_winners()` uses actual tournament positions, not model predictions. Pass 3 now excludes DataGolf (`source != 'datagolf'`).
- ✅ Snapshot distribution diagnostic on status endpoint

**Key investigation findings (May 18-19):**
- 58% of stuck Kalshi outcomes have ZERO snapshots (never polled). 43% of Polymarket similar. These are ghost markets.
- 27% of Polymarket stuck outcomes have 21+ snapshots — real trading data, but settlement price never captured. Phase 3 addresses these.
- Ghost markets do NOT contaminate calibration (verified: `opening_probability IS NOT NULL` filter, mode-price detection, and `_null_untradeable_openings()` all prevent leakage).
- Phase 3 initially failed because Gamma API `/markets/{condition_id}` doesn't work as a path param. Fixed to use `/events/{event_id}` + condition matching.

**Remaining (ordered):**
1. **[P1] Kalshi baseball/hockey calibration** — Kalshi shows +17pp error in baseball, +23pp in hockey. Suspected cause: Pass 2 arbitrarily picks highest-prob outcome as winner for markets stuck near 0.50. Phase 2 limit bump should help — check api_miss rate after next run.
2. **[P2] Polymarket all-losers (4,575)** — Winning outcome not in DB. Mostly NegRisk sub-markets. Phase 3 addresses some but many are truly missing-winner markets. Low MCE impact.
3. **[P2] Verify golf/DataGolf MCE improvement** — `_backfill_datagolf_winners()` shipped. Check after next backfill run.

**Guard rails against 3 failure states:**
- **Dropped/forgotten:** Check the status endpoint at session start. Coverage < 95% = P0.
- **Worker fails silently:** `stuck_diagnosis` section shows exactly what's stuck. If stuck_markets not decreasing between runs, investigate.
- **Backfill harms live tasks:** Background queue, soft_time_limit=600s, per-batch commits, DB connection monitoring.

**Files:** `backend/app/tasks/backfill_winners.py`, `backend/app/routes/admin.py` (status endpoint)
**Parallel Safety:** Green

### Workstream: Historical Event Linking Backfill (ACTIVE — runs automatically)

**Goal:** Every past-game Kalshi market linked to its event, so event detail pages show complete Kalshi data even for historical games.

**Monitor:** `GET /api/admin/prediction-markets/backfill-link-status?secret=$ADMIN_TOKEN`
- `remaining_to_try` = markets the backfill hasn't attempted yet. Should shrink to 0.
- `marked_no_match` = markets that genuinely have no matching event (obscure leagues, etc.)
- When `remaining_to_try == 0`, the backfill is complete.

**How it works (shipped May 15, 2026):**

The live matching task (`match_prediction_markets`, every 15 min) intentionally skips closed/completed events via a `past_cutoff` filter — it only cares about linkable games happening NOW. Past games' Kalshi markets stay unlinked. This backfill task fills that gap:

1. Queries unlinked Kalshi game markets with ticker dates >48h in the past
2. Runs `_find_historical_event()` — same scoring as live matching BUT:
   - **No status filter** — allows closed/completed events
   - **No past_cutoff** — doesn't care when the game ended
   - **Same -6h/+30h time window** around the ticker date
   - **Same team fuzzy matching + sport validation**
3. If linked → done (market.event_id set via Core SQL, not ORM)
4. If no match → sets `market_metadata->>'backfill_link_failed' = true` so the next run skips it
5. Processes 500 markets per run, 8x/day (every 3h), background queue — drains ~28K in ~7 days

**Idempotency:** The `backfill_link_failed` flag in `market_metadata` JSONB means each market is attempted exactly once. Already-linked markets are excluded by `event_id IS NULL`. To re-try failed markets (e.g., after adding new team abbreviations), clear the flag:
```sql
UPDATE futures_markets SET market_metadata = market_metadata - 'backfill_link_failed'
WHERE source = 'kalshi' AND event_id IS NULL AND market_metadata ? 'backfill_link_failed';
```

**What NOT to waste time on (lessons from May 14-15 investigation):**
- **Don't touch the live matching task's filters** — the `past_cutoff` and status filters are correct for live matching. Relaxing them causes cross-contamination with closed events.
- **Don't try to fix the tier1-gaps endpoint** — those 49 "gaps" are past-game markets. The endpoint's denominator includes them because they're status="open" on Kalshi (for settlement). The endpoint measures CURRENT linking, not historical. Leave it alone.
- **Don't try to link ALL past markets at once** — there are thousands. The batch approach (100/run, 2x/day) drains in ~2 weeks without impacting live operations.
- **Don't retry failed markets automatically** — if `_find_historical_event` returned None, the event doesn't exist (obscure leagues, cancelled games, etc.). The `backfill_link_failed` flag prevents wasted queries on every run.
- **ORM attribute assignment for event_id works** but the backfill uses Core SQL `update()` for safety (gotcha #8 / #22).
- **The duplicate linkage guard is NOT applied** in the backfill — it's only relevant for same-series playoff games, which are handled by the live task's Phase 2 wrong-game detection.

**Root cause recap (May 14-15):** The live matching task had 5 issues preventing linkage. All 5 were fixed for current games. The 6th issue — past games can't link because their events are closed — is what this backfill addresses. Full investigation trace in git history (commits `028d5f9` through `bb4c883`).

**Files:** `backend/app/tasks/prediction_market_matching.py` (`_backfill_historical_links`, `_find_historical_event`), `backend/app/tasks/__init__.py` (task registration + beat schedule), `backend/app/routes/admin.py` (status endpoint)
**Parallel Safety:** Green

---

### Workstream: Calibration Accuracy (ACTIVE — monitor every session)

**Goal:** MCE ≤3.0pp overall and per-category with N>100.

**Monitor:** `GET /api/calibration` → overall MCE. Frontend `/calibration` for per-category.

**Current state (May 19, 2026):** MCE 3.1pp (CI [1.9, 4.7]). 232,625 outcomes, 161,972 markets, 5 sources. Golf MCE 25.9pp (fixed: DataGolf model predictions were treated as settlement prices — leaderboard-based resolution shipped). Hockey MCE 12.5pp (Kalshi under-prediction, investigating). Spreads MCE 28.6pp → should drop after devig fix shipped.

**Data pipeline shipped:**
- ✅ Public calibration endpoint (`GET /api/calibration`, 1h cache) with `price_moved` dimension
- ✅ Closing-line cohort predicate fixed: `price_moved=True` now requires non-null `calibration_probability` that differs from opening price, so fallback opening-price rows do not pollute closing-line cohorts.
- ✅ Odds API ground-truth (18,568 outcomes from completed+closed games)
- ✅ `backfill_winners` (every 6h) — is_winner, calibration_probability, null untradeable (≤5 snaps + <2pp spread)
- ✅ `backfill_polymarket_history` (every 6h) — CLOB API price history for zero-snap outcomes
- ✅ `backfill_kalshi_history` (every 6h) — candlesticks API price history for zero-snap outcomes
- ✅ Golf commence_time fix via DataGolf schedule (reuses `_normalize_tournament()`)
- ✅ `is_multi` fix, `status IN ('completed', 'closed')`, Part C rescue, 8 diagnostic endpoints

**Subproject A: Snapshot health** — ✅ EFFECTIVELY DONE
Zero-snap: 23K → 702 (0.2%). Remaining 702 are Polymarket esports/tennis with no CLOB history. No further action unless zero-snap regresses above 1K.

**Subproject B: Golf calibration (MCE 25.9pp)** — TWO FIXES SHIPPED
**Root cause 1 (May 18):** Kalshi `commence_time` = market listing date, not tournament start. Part A grabbed mid-tournament prices as "closing lines." Fix: Part A now JOINs `events` table and uses `events.commence_time`.
**Root cause 2 (May 19):** DataGolf placement markets (make_cut, top_5, top_10, top_20) use model predictions in `current_probability`, NOT settlement prices. Pass 3 (independent thresholds) treated every player with >50% make_cut probability as a "winner" — even players who missed the cut. This is why bucket 9 showed 94.8% predicted but only 28.3% actual.
**Fix (May 19):** New `_backfill_datagolf_winners()` resolves from actual leaderboard positions stored in `market_metadata`. Handles ties (T5, T12), cut statuses (CUT, MC, WD, DQ). Pass 3 now excludes DataGolf (`source != 'datagolf'`). 18 tests for position parsing.
1. **ACTION:** Verify golf MCE drops after next backfill run.

**Subproject C: Hockey calibration (MCE 12.1pp)** — FIX SHIPPED May 18
**Root cause:** Polymarket `commence_time` = market listing date. Part C rescued with settlement prices (0.05% / 99.95%), not predictions. Fix: Part A now uses `events.commence_time` for event-linked NHL game markets. Part C restricted to event-linked markets only, preventing settlement price contamination. Non-NHL hockey (AHL, SHL, DEL, KHL) without `event_id` uses opening price.
1. **ACTION (May 19):** Verify hockey MCE drops after backfill_winners runs.
2. **BACKLOG: Expand calibration to non-NHL hockey.** Currently excluded because these markets lack `event_id` (no linked events in our system). To include: either create events for these leagues via a new data source, or build a mechanism to derive commence_time from the market name/ticker (e.g., parse "Jets vs. Avalanche" + date). Low priority — focus on NHL accuracy first.

**Subproject E: Non-event market closing lines** — FIX SHIPPED May 18
**Root cause:** Part C rescue grabbed settlement prices for ALL markets, including elections, economics, entertainment. A "Will Taylor Swift get pregnant?" market at 10% opening got `calibration_probability = 0.05%` (settlement) instead of 10% (the actual prediction). Fix: Part C now restricted to event-linked markets only. Non-event markets use opening price after initial trading settles (Part B). Methodology note updated on `/calibration` page.

**Subproject G: Spreads/Totals devig (MCE 28.6pp / 7.3pp)** — FIX SHIPPED May 19
**Root cause:** Calibration endpoint computed spread/totals implied probability from ONE side of the American odds without normalizing against the other side. Standard -110/-110 showed as 52.4% instead of true 50%. Moneylines were already devigged via `moneyline_to_probability(remove_juice=True)` — this gap only affected the calibration page.
**Fix:** Normalize `home_implied / (home_implied + away_implied)` for spreads, `over_implied / (over_implied + under_implied)` for totals. Both counter-side odds already stored on `events` table.
**Confirmed safe:** All user-facing probabilities across the site ARE devigged. Moneylines use `remove_vig()` in `odds_math.py`. Futures use per-bookmaker normalization. Kalshi/Polymarket are prediction markets (no vig). This was a calibration-display-only issue.
1. **ACTION:** Verify Spreads MCE drops from 28.6pp after deploy.

**Subproject F: Outcome count expansion** — NEXT PRIORITY
Currently 62K resolved outcomes from prediction markets only. The Odds API sportsbook data contributes just 2 points per game (home/away win). All spreads, totals, player props, 1H/2H lines in `odds_snapshots` are untapped. Steps:
1. Count resolved spreads/totals in `odds_snapshots` to size the opportunity
2. Add spread resolution logic: `away_score - home_score > spread_line` → covered
3. Add total resolution logic: `home_score + away_score > total_line` → over
4. Add as a new CTE in the calibration query alongside the existing events CTE
5. Player props (harder): need box score data from StatPal for individual stat lines
6. **Expected impact:** 10-20x increase in calibration sample size with the highest-quality data (sportsbook closing lines with unambiguous resolution)

**Subproject D: Weather/Economics calibration (MCE 10.1pp each)** — INVESTIGATED May 15
**Conclusion: price-stuck problem, NOT commence_time.** Key findings:
- Kalshi economics has 27.6% price-stuck rate (price never moved from opening)
- Economics 40-50% bucket: predicted 47%, actual 32% (−14.6pp error, n=1,311)
- Economics 50-60% bucket: predicted 51%, actual 66% (+14.9pp error, n=2,233)
- This is the classic price-stuck signature: opening prices near 50% never update
- commence_time IS correct for weather/economics (close_time = when trading ends = right value)
- Fix shipped: tightened `_null_untradeable_openings` Pass 3 (≤5 snaps + <2pp spread) to filter these out

**Remaining:** Verify MCE improvement after next backfill run. If still >5pp, consider further tightening the spread threshold or increasing the snapshot count threshold.

**Subproject E: Price-stuck outcomes** — INVESTIGATED May 15, PARTIALLY FIXED
**Analysis results:**
- Price-moved outcomes: MCE 16.3pp, N=22,115
- Price-unmoved outcomes: MCE 28.3pp, N=2,134 (dramatically worse)
- Worst unmoved categories: hockey 39.8pp, basketball 34.6pp, economics 33.3pp, entertainment 33.2pp
- Closing-line MCE (8.6pp) is much better than opening-price MCE (28.0pp) — validates the closing-line approach
- The high per-category MCEs in "moved" data (golf 30.5pp, esports 32.0pp) are from corrupted commence_time (golf/hockey fixes now deployed)

**Fix shipped:** Tightened `_null_untradeable_openings` Pass 3 to filter outcomes with ≤5 snapshots and <2pp price spread. This removes the thinnest price-stuck outcomes from calibration.

**Decision made:** Filter out (option a). Outcomes with no price discovery are noise, not signal. The opening price is a placeholder, not a prediction.

**Remaining:** After next backfill run, verify unmoved MCE drops and overall MCE CI tightens. If still high, consider raising the snapshot threshold from 5 to 10.

**Remaining calibration accuracy work:**

6. ~~**Confidence intervals on calibration metrics**~~ — ✅ DONE May 15.
7. ~~**Separate closing-line vs opening-price cohorts**~~ — ✅ ALREADY DONE. Frontend has Closing Line / Opening Price / All tabs. Default is closing line. API returns `mce_closing_line` and `mce_opening_price`.
8. **Source "fair fight" comparison** — Methodology for comparing accuracy controlling for market difficulty.
9. **Confidence tiers on Discover cards** — Signal bars (high/medium/low). Data-driven thresholds TBD.
10. **Volume field DQ on Polymarket sub-markets** — `volume = NULL` on decomposed sub-markets.

**Guard rails against 3 failure states:**
- **Dropped/forgotten:** Check per-category MCE at session start. Any N>100 category above 10pp = P1.
- **Regression:** If overall MCE drifts above 3.0pp, something changed. Check is_winner coverage + snapshot health.
- **is_winner blocks accuracy:** These workstreams are coupled. Low is_winner coverage → biased calibration sample.

**External studies:** Arrow et al. (2008, Science), Berg/Nelson/Rietz (2008), Tetlock/Gardner (2015), Wolfers/Zitzewitz (2004, JEP), Metaculus track record.

**Files:** `backend/app/routes/admin.py`, `backend/app/routes/calibration.py`, `backend/app/tasks/backfill_winners.py`
**Parallel Safety:** Green

---

### Workstream: Celery Queue Health (FIXED May 15 — monitor at session start)

**Monitor:** `GET /api/admin/celery-debug?secret=$ADMIN_TOKEN` → `queue_lengths.background`. Target: < 50.

**If queue > 50:** Check `celery-debug` active tasks, restart zombie workers (`heroku ps:restart worker-background`), purge if needed (`POST /api/admin/celery-purge-background`). Consider Standard-2X if chronic.

### ~~Production Observability~~ — SHIPPED (May 17)

### ~~Manus Sweep May 6~~ — ALL 12/12 FIXED (May 7)

### 0e-3. GA4 Console Configuration

Not code — configuration in the GA4 property (analytics.google.com):
1. **Custom definitions**: Register `sport`, `league`, `event_id`, `event_status`, `source_section`, `position_index`, `is_live`, `is_close_game` as custom dimensions
2. **Key events (conversions)**: Mark `sign_up`, `onboarding_complete`, `event_detail_view` as key events
3. **Audiences**: Create "Sports Enthusiasts" (3+ event_detail_view / 7d), "NBA Fans" (sport=basketball_nba 5+), "Power Users" (5+ sessions / 7d)
4. **Funnels** (Explore): Acquisition, Onboarding, Retention
5. **Dashboards**: DAU by platform, top sports by engagement time, feed CTR, onboarding completion rate

**Parallel Safety:** Green (no code changes)

### ~~0f-4e. Slow Headshot Loading~~ — FIXED (May 8)

### ~~0f-13c-native. 2nd Half Maps Not Showing~~ — FIXED (May 15)

### ~~0f-13h. Player Award Headshots Missing on WEB~~ — ALREADY FIXED (May 13)

### ~~BR1-2. Source Attribution Looks Duplicated~~ — RESOLVED (May 13)

### ~~0f-3. Live Box Score Integration for Player Props~~ — PARTIALLY FIXED (May 8)

Name matching fixed (Jr/Sr/III/IV suffix stripping). Remaining: verify matching accuracy on live games with unusual names.

### ~~0f-3d Issue 4: Series Markets~~ — SHIPPED (May 13)

### ~~0f. Event Detail Below-the-Fold Redesign~~ — SHIPPED (May 17)

### 0t-2. Period Markers for Non-ESPN Events — PARTIALLY FIXED (May 11)

**Problem:** 21/45 completed events have no game state indicators (period/quarter/inning vertical lines on charts). All are non-ESPN events: soccer, tennis, KBO/NPB baseball.

**May 11 fix:** StatPal livescores now writes `raw_status` (e.g., "Q3", "1H", "HT") to `Event.period` every 30 seconds during live games. This gives period markers for all StatPal-covered sports (NBA, NHL, MLB, NFL, soccer). Previously this data was normalized to "live" and discarded.

**May 18 guardrails:** Added tests proving StatPal preserves live raw period statuses (`Q3`, `1H`, `HT`) and `_sync_statpal_livescores()` writes `fixture.raw_status` into `Event.period`. No production change needed.

**Remaining gap (investigated May 18):** ~85% of live events have real-time period markers. The ~15% gap is:
- **Tennis (StatPal covered but likely bugged):** `raw_status` is only set when `_normalize_status()` returns `"live"`, but tennis set strings (S1/S2/etc.) may not be in the recognized live-status set, causing them to be silently dropped. **Fix:** Add tennis set strings to the live-status set, or change `raw_status` logic to capture any unrecognized status as period info.
- **KBO/NPB baseball, MiLB, boxing, cricket:** No real-time period source. Low volume. Synthetic fallback covers completed events.
- **Soccer synthetic halftime fallback still needed** for games completed before StatPal was polling. Harmless last resort.

**Files:** `backend/app/services/statpal_api.py` (raw_status), `backend/app/tasks/statpal_sync.py` (write to Event.period)
**Parallel Safety:** Green

### ~~0t-3. Chart Domain Mismatch~~ — LIKELY FIXED

`sharedChartDomain` (computed in `events/[id]/page.tsx` lines 382-488) already passes identical `chartStartTime`, `chartEndTime`, and `sharedTicks` to both OddsChart and ScoreDifferentialChart. Game-end source filtering clips post-game prediction market drift. Needs live verification.

### ~~1b-monitor. Hockey Kalshi Link Rate~~ — FIXED (May 11)

### macOS Polish (1 remaining of 7)

~~MAC-1, MAC-3, MAC-5, MAC-6, MAC-8, MAC-9~~ — all shipped.

| # | Item | Effort | Files | Safety |
|---|------|--------|-------|--------|
| MAC-12 | macOS widgets (Today view) | 3-4h | New widget extension | Green |

---

## Tier 2 — Important But Bigger Scope

### 2. God Functions — Deeper Extraction

**First pass shipped:** 5 functions, 82 tests, 4 utility modules (April 21).

**Remaining targets:** `get_golf` (686L), `_match_prediction_markets` (649L), ~~`operations_dashboard` (595L)~~ (SHIPPED May 17), `_build_golf_tour_grid` (549L), `_get_march_madness_data` (406L).

**Large route files:** `admin.py` (8,684L), `events.py` (5,042L), `playoffs.py` (3,539L), `futures.py` (2,866L), `golf.py` (2,294L).

**Parallel Safety:** Yellow

### ~~3. Golf Data Quality~~ — FIXED (May 18)

### ~~4. Site Navigation Hierarchy (B1)~~ — SHIPPED (May 17)

### 5. Playoff Series Matchup Markets

Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification in `tournament_stages.py`, grid column, event detail display, trend charts. Timely with NBA/NHL playoffs in progress.

**Files:** `backend/app/config/league_configs.py`, `backend/app/utils/tournament_stages.py`, `backend/app/routes/playoffs.py`, `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### 6. API Route + Guardrail Test Coverage — ONGOING

850+ integration/route contract tests and 5,000+ backend tests. Comprehensive guardrail suites cover feed scoring, events, playoffs, futures, category pages, predictions, matching, ingestion, display, auth, calibration, provider parsers, retention, notifications, and more. May 18-19 sprint added +456 tests across 15 files (total: 5,099).

**Parallel Safety:** Green

---

## Tier 3 — Valuable But Can Wait

### Operational Health

~~9. Structured Logging~~ — DONE (May 15). ~~11. Hardcoded Conference Maps~~ — DONE (May 17).

### Product Features

~~12. Evolution Chart Combined Probability~~ — DONE (May 18). ~~13. Line Movement Explainer v2~~ — DONE (May 18). ~~17. Golf Evolution Chart~~ — DONE. ~~18. Non-Sports Category Pages~~ — ALL SHIPPED (May 7).

| # | Item | What | Depends on | Safety |
|---|------|------|-----------|--------|
| 14 | **Freshness-Weighted Blending** | Time-decay for stale prediction market prices | More eval data | Yellow |
| 15 | **DS/Analytics Infrastructure** | Analytical columns, `v_completed_events` view, Brier scores | Migration slot | Red |
| 16 | **Golf Tournament Related Futures** | "Bigger Picture" section on tournament detail | Nothing | Yellow |

---

## Search — Phase 4c & Phase 5b & Phase 6 (REMAINING)

**Phases 1-3:** ✅ SHIPPED (team pages, typeahead enrichment, recent searches, mobile search, keyboard shortcuts)
**Phase 4a-b:** ✅ SHIPPED (`pg_trgm` extension, GIN trigram indexes, did-you-mean suggestions)
**Phase 4d:** ✅ SHIPPED (did-you-mean suggestions)
**Phase 5a, 5c-e:** ✅ SHIPPED (recent searches, results page redesign, mobile search, keyboard shortcut)

**REMAINING:**

### P4c. Weighted `ts_vector` Full-Text Search — FIRST SLICE SHIPPED May 18

Team names weight A, market names weight B, outcome names weight C. Use PostgreSQL full-text search with weighted ranking.

**May 18 first slice shipped:** `/api/events/search` now uses query-time PostgreSQL full-text ranking (`websearch_to_tsquery`, weighted vectors) without a migration. Event/team names rank at weight A, futures market names at B, and futures outcome names at C. Existing ILIKE matching/fallback behavior and typeahead remain unchanged. A stored/indexed `ts_vector` migration can come later only if production search latency needs it.

**Files:** `backend/app/routes/events.py`, future migration only if indexing becomes necessary
**Parallel Safety:** Yellow

### ~~P5b. Trending/Popular Searches~~ — SHIPPED (May 13)

### Phase 6: Semantic Search (2-3 weeks, aspirational)

- **P6a. Embedding-based search** — OpenAI embeddings for queries like "Will the Celtics repeat?" matching championship markets
- **P6b. pgvector extension** — Store embeddings in Postgres, nearest-neighbor search
- **P6c. Query intent classification** — Is the user looking for a team, game, market category, or asking a question?
- **P6d. Personalized ranking** — Boost results from leagues/teams the user has viewed or predicted on

**Files:** Various
**Parallel Safety:** Yellow

---

## iOS App — Web Parity & Polish

### iOS App — Web Parity & Polish

Shipped: ~~iOS-4~~ (dead views audit), ~~iOS-6~~ (feed limit), ~~iOS-GD12~~ (headshot fallback).

| # | Item | Description | Safety |
|---|------|-------------|--------|
| iOS-7 | Rebuild native Futures browser before re-exposing — partial. May 17 groundwork shipped; needs final product review before re-exposure. | Yellow |

---

## ~~iOS Code Quality (multi-wave cleanup)~~ — ALL 6 WAVES COMPLETE (May 17-19)

All 21 items (CQ-1 through CQ-21) shipped across 6 waves: crash risks, dedup extraction, DiscoverView split (2259→~300 lines), file organization, access control + naming, doc comments. Full plan at `docs/ios-code-quality-plan.md`.

---

## App Store Submission (ACTIVE — target: this week)

**Goal:** Get Bain Luck approved and live on the App Store.

**Current state:** TestFlight Build 3 uploaded. 5 parity features shipped (May 15-16). macOS + iOS builds clean. Native launch-readiness sweep is complete: the unfinished Futures browser entry point is hidden pending iOS-7, the 🍀 Bain Luck sidebar branding is preserved, Calibration remains visible, ViewModels/utilities/docs/access control cleanup is done, and APS entitlement is production-ready. No prior App Store submission attempted.

### Must Do (submission blockers)

| # | Item | Status | Effort | Where |
|---|------|--------|--------|-------|
| AS-1 | App Store Connect listing: name, subtitle, description, keywords | COPY READY | 30 min | Copy from `docs/app-store-launch-plan.md` into [App Store Connect](https://appstoreconnect.apple.com) |
| AS-2 | Screenshots: iPhone 6.7" (required), 6.1", iPad 13" | TODO | 1-2 hrs | Simulator or real device — Discover, Higher/Lower, event detail, championship grid, category page, Calibration |
| AS-3 | Age rating questionnaire | TODO | 5 min | App Store Connect |
| AS-4 | APS entitlement → production | ✅ DONE | 2 min | Changed in `Bain Luck.entitlements` |
| AS-5 | Privacy policy URL in App Store Connect | TODO | 1 min | Enter `https://bainluck.com/privacy` |
| AS-6 | Support URL in App Store Connect | TODO | 1 min | Enter `https://bainluck.com/about` or create a support page |
| AS-7 | "What's New" release notes | COPY READY | 5 min | Copy from `docs/app-store-launch-plan.md`; public copy does not mention hidden Futures browser |
| AS-8 | App Review notes | COPY READY | 5 min | Copy from `docs/app-store-launch-plan.md`; notes explain no demo account needed, no wagering, Futures browser hidden pending iOS-7, Calibration visible, 🍀 sidebar branding intentional, push optional |

### Should Do (rejection risk)

| # | Item | Risk | Status | Notes |
|---|------|------|--------|-------|
| AS-9 | Gambling disclaimer in App Review notes + About page | Medium | ✅ DONE | About copy exists and App Review notes now include an explicit no-wagering/no-payments disclaimer. |
| AS-10 | Verify IDFA/ATT not needed | Medium | ✅ DONE | No IDFA collection, no ATTrackingManager, no ad personalization. Privacy manifest correct. No ATT prompt needed. |
| AS-11 | Launch screen check | Low | ✅ PASS | SwiftUI auto-generated plain white launch screen, seamless transition to light-mode app. No storyboard needed. |
| AS-15 | Final native navigation smoke check | Medium | ✅ PASS | Code-verified May 18: Futures browser hidden (no sidebar entry), Calibration visible in Quick Links, 🍀 title preserved, market detail opens from search/all category pages/weather/Discover. |

### Nice to Have (post-launch)

| # | Item | Notes |
|---|------|-------|
| AS-12 | App preview video (15-30s) | Helps conversion, not required |
| AS-13 | Promotional text (170 chars) | Updatable without new build |
| AS-14 | In-app review prompt | `SKStoreReviewController` after a few sessions |

### Already Done

App icon, bundle ID, privacy manifest/policy, Sign-In (Apple + Google), push entitlement, universal links, TestFlight uploading, web/native parity, Xcode warnings, code quality sweep, Futures browser hidden, release notes drafted in `docs/app-store-launch-plan.md`.

**Parallel Safety:** Green

---

## Discover Feed Enhancement

### Discover Feed Enhancement

Shipped: ~~DN-9~~ (swipe dismiss), ~~DN-10~~ (onboarding categories), ~~DN-11~~ (grouped cards), ~~D-4a~~ (click tracking), ~~D-10b~~ (like/dismiss ranking), ~~D-8~~ (daily digest), ~~D-9~~ (friend challenges).

| # | Item | Description | Safety |
|---|------|-------------|--------|
| D-10a | Dismiss persistence | Persist dismissed IDs server-side for cross-device continuity | Yellow |
| D-6 | Push notifications for moves | Foundation shipped (token capture, registration). Actual production push not yet implemented. | Green |
| D-7 | Live game companion mode | NEEDS DESIGN. Aggressive auto-refresh, screen awake, simplified layout. | Green |

---

## Event Detail Parity Items (from April 29 Sweep #3)

Items 4, 5, 6, 8 remain (item 2 web x-axis alignment is done via `sharedChartDomain`):

- **1st half margin mismatch**: Web shows BOS +6.5, native shows BOS +1.0. Use spread threshold directly from period market with probability closest to 50%.
- **Half map FINAL values**: Derive half scores from ESPN history halftime data point.
- **2nd half maps missing**: Check if API returns 2H period markets; render if present.
- **Double/triple doubles → player props**: Sport-generic: scan `other` markets for player-named outcomes, inject into player prop cards.

**Files:** `frontend/components/OddsChart.tsx`, `frontend/components/ScoreDifferentialChart.tsx`, `frontend/components/MarketMapSection.tsx`, `ios/.../Components/MarketMapSection`
**Parallel Safety:** Yellow

---

## Tier 4 — Someday / Maybe

### 20. Market Interestingness Scoring

**Goal:** Algorithmic scorer calibrated against Kalshi/Polymarket marketing emails as ground truth.

**May 18 first slice shipped:** Added pure scoring utilities in `backend/app/utils/market_interestingness.py` and a local-input calibration scaffold in `backend/scripts/calibrate_interestingness.py`. It accepts CSV/JSON/JSONL rows, scores deterministic component signals, and reports optional labeled precision/recall metrics. No runtime feed ranking or database integration yet.

**Phases:** (1) Ground truth collection (Gmail → Apps Script → Sheet, 50-100 labeled markets), (2) Scoring formula (8 weighted features: decisiveness, multi-source, recency, movement, resolution proximity, category novelty, volume, LLM quality) — ✅ shipped May 18, (3) Calibration (hill-climb weights, Precision@20/Recall@50/NDCG), (4) Integration (explore page, feed ranking, trending, push, featured hero). **Feed integration plan:** see 0u-N1 in the Discover Feed Quality section for the step-by-step wiring into `_score_futures()`.

**Files:** `utils/market_interestingness.py` (new), `scripts/calibrate_interestingness.py` (new), Google Sheet
**Parallel Safety:** Green

### ~~21. Rage Shake~~ — SHIPPED

### ~~22. Interestingness-Powered Discovery Feed~~ — MOSTLY SHIPPED (remaining: formal `interestingness_score` column, see item 20)

### 23. Prediction Market Game / Social Picks

Higher/Lower game is live in Discover. Daily challenge card shipped. Dedicated `/daily` page and basic friend challenge landing page shipped May 14. Shareable prediction scorecards shipped May 17 (OG image generation, `/discover/scorecard`). Remaining: richer head-to-head challenge creation/discovery, ambient screensaver, and portfolio mode.

**Depends on:** Auth (shipped), preferences (shipped).
**Parallel Safety:** Green

---

## Platform Parity Checklist

Shipped: ~~Game Segments~~, ~~Line Movement Explainer~~, ~~Weather page~~, ~~Economics page~~. No web gaps.

**iOS/Mac gaps (web has, native doesn't):**

| Priority | Feature | Web Component | Effort |
|----------|---------|--------------|--------|
| Medium | Total Points Spectrum (spread+total viz) | `TotalPointsSpectrum.tsx` | Medium |
| Medium | Series Probability (playoff series outcomes) | `SeriesProbability.tsx` | Small |
| Low | Evolution Chart (championship race over time) | `EvolutionChart.tsx` | Medium |
| Low | Explore / faceted browser | `/explore` | Medium |

---

## Strategic

### ~~Expert Review / Audit~~ — COMPLETED (May 14)

### Post-Audit Priority Stack (May 14)

Shipped: ~~admin endpoint gating~~, ~~`/daily` page~~, ~~scorecards~~, ~~rate limiting~~, ~~calibration CIs~~, ~~hardcoded colors~~, ~~DiscoverCard decomposition~~, ~~max-width~~, ~~button system~~, ~~dead page archive~~.

**P0 — Security & Reliability:**
- [ ] Split `get_db()` into read-only (no commit) and `get_db_rw()` (commits) — every GET request currently issues unnecessary COMMIT

**P0 — Product (Growth):**
- [ ] **Redesign first 30 seconds** — Hero headline for first visit, first card is always a guess card, progressive disclosure toward sign-up.

**P1 — Engineering:**
- [ ] **Split `admin.py`** (11K lines, 174 handlers) — Split into `admin_celery.py`, `admin_matching.py`, `admin_taxonomy.py`, `admin_engagement.py`, `admin_data_quality.py`.

**P1 — DS (Calibration Integrity):**
- [ ] **Separate closing-line from opening-price cohorts** — Report closing-line-only as primary metric.
- [ ] **Confidence tiers on Discover cards** — Signal bars (high/medium/low) based on data-driven thresholds.

**P2 — DS:**
- [ ] **Empirically derive aggregation weights** — Retrospective Brier score analysis per source
- [ ] **Stat model evaluation framework** — Validate `base_std` constants, weekly Brier comparison
- [ ] **Proactive data quality monitoring** — Calibration drift alerts, source freshness SLOs

**P2 — Product:**
- [ ] **Actually send push notifications** — One daily push: "Today's challenge is ready. Streak: 7 days."
- [ ] **Weekly prediction accuracy report email** — "You were 73% accurate across 22 predictions this week."

### Weather: Meteorologist Forecast Comparison (Dexter idea, May 14)

**Problem:** The weather page shows Kalshi/Polymarket prediction market probabilities for temperature and rain, but doesn't show what an actual meteorologist forecasts. Users can't tell if the market is accurate without a reference point.

**Idea:** Pull real weather forecast data from a weather API and display it alongside market probabilities. "What does the market say vs what the meteorologist says." This is the weather equivalent of the calibration page — measuring prediction market accuracy against ground truth, but in real-time.

**API options:** Weather.gov (NWS API, free, US-only, official forecasts), OpenWeatherMap (free tier 1000 calls/day), AccuWeather, Tomorrow.io.

**Files:** `backend/app/routes/weather.py`, new weather API service, `frontend/app/weather/page.tsx`
**Parallel Safety:** Yellow
**Decision needed:** Which weather API to use. TBD.

### Product Pitch Document (Alex, May 14)

**Status:** Draft in `docs/product-pitch.md`. Core thesis: score doesn't tell the full story, odds are universally interesting, gambling gives odds but entices gambling, Bain Luck gives probability context without gambling pressure.

### Tech Debt + Repo Cleanup Audit (May 14)

**Status:** Audit running. Results will be added here when complete. Covers: large files, god functions, TODO/FIXME comments, unused dependencies, stale branches, untracked artifacts.

### Platform & API Features Audit (May 14)

**Status:** Audit running. Checking what free features we're leaving on the table across GitHub, Sentry, GA4, Vercel, Heroku, and all external APIs (StatPal, ESPN, TMDB, Odds API, Kalshi, Polymarket, DataGolf).

### ~~BUG: Alcaraz Search~~ — FIXED (May 15)

### ~~BUG: Placeholder Outcomes~~ — FIXED (May 15)

### ~~About Page Polish~~ — v2 SHIPPED (May 16)

### Run Another Manus Sweep (May 14)

Last sweep: May 11 (10 modules, 10/14 resolved). Time for a fresh sweep to catch regressions and new issues from the past 3 days of shipping.

---

## Housekeeping

### Other Housekeeping
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches

### Mystery Shopper Findings (April 22, 2026 — Manus AI Audit)

10/12 fixed. **Open:** M2 (mobile event detail — needs verification, likely transient), M4 (uninteresting prop thresholds — filter needed), M8 (CPI distribution >100% — independent binary markets).
