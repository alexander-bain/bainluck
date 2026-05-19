# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

## Current Priority: Calibration & Data Quality

**"Do prediction markets predict anything?"** — the calibration page is the proof. This workstream makes the data trustworthy, expands the sample size, and fixes per-category accuracy.

**Monitor:** `/calibration` page, `GET /api/calibration`, `GET /api/admin/backfill-winners/status`

**Open items (ordered by priority):**
1. **Verify golf/hockey MCE drop (May 19)** — closing line fixes shipped May 18, awaiting backfill recompute
2. **Outcome count expansion (Subproject F)** — add spreads/totals from odds_snapshots to calibration (10-20x more data points)
3. **is_winner coverage → 95%+** — currently 92.7% Kalshi, 92.7% Polymarket (see Workstream: is_winner Backfill below)
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

**Problem:** Kalshi game-winner probability oscillated between two stable values across every poll cycle. 55 events affected, ~16K+ bad snapshots.

**Root cause:** Multiple Kalshi markets from different games (e.g., tournament Game 1 + Game 2 between same teams) cross-linked to the same event, causing alternating home_prob writes.

**All fixed:**
- ✅ Prevention guard: `_check_duplicate_kalshi_linkage` blocks linking when a different game's market is already linked
- ✅ Phase 2 multi-game detection: scans and unlinks wrong markets spanning multiple dates
- ✅ Historical cleanup: `POST /api/admin/sawtooth-fix` unlinked 32 markets and deleted 16,477 bad snapshots
- ✅ Diagnosis endpoints: `GET /api/admin/sawtooth-diagnosis` + `GET /api/admin/sawtooth-audit`
- ✅ Devig averaging for future snapshots

**Remaining:** Verify on live games that new data is clean.

### ~~Double-Header Date Matching~~ — FIXED (May 14)

HHMM-aware tickers now use tight ±3h window. Date-only tickers use asymmetric -6h/+30h window (accounts for UTC vs US timezone offset). Both prevent cross-linkage of doubleheader games.

**Files:** `backend/app/utils/prediction_market_matching.py` (`extract_game_date_from_ticker` ~line 893), `backend/app/tasks/prediction_market_matching.py` (Phase 2 date validation)

### ~~Stat Model Lacks Pregame Prior~~ — FIXED (May 13)

Model now starts at sportsbook consensus probability (via inverse-normal-CDF conversion to derive an equivalent spread) instead of 50%. The prior naturally fades as game evidence accumulates. 11 new tests, all pass.

**Files:** `backend/app/utils/win_probability.py` (`compute_statistical_win_prob`), `backend/app/tasks/espn_sync.py`

### ~~Game-Markets Query Missing Kalshi Props~~ — FIXED (May 13)

Root cause: status and `llm_sport_category` filters were excluding linked markets from the game-markets query. Removed both filters from the linked query path. Overtime, half winners, player props, points leaders now show on event detail pages for all linked events.

**Files:** `backend/app/routes/events.py` (game-markets query)

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

**~~0u-R1. Gate "upset" event demotion bypass on league tier~~** — SHIPPED May 18

The `is_exceptional` check in `feed.py:626` lets any event with "upset" in its headline keep its full score in Discover mode. The headline generator labels nearly every recently-completed game as "Recent upset" — including Ligue 2, Brazilian Série B, and Chilean Primera División. This causes 17 of 50 Discover items to be foreign soccer events, crowding out entertainment/politics/tech.

**Fix shipped:** Discover event demotion now uses a shared helper in normal ranking and debug traces. Keyword exceptions (`upset`, `comeback`, `historic`, etc.) require major-league context via `get_league_tier(...) <= 2` or `tier:1`/`tier:2` tags. Raw `score >= 90` also requires EI/event-interest score >= 50. Regression tests cover low-tier soccer upset demotion, NBA upset preservation, and high raw score without EI demotion.

**Files:** `backend/app/routes/feed.py` (~line 626)

**~~0u-R2. Fix Russia-war story key to catch territory markets~~** — SHIPPED May 18

10 near-identical "Will Russia capture [village]?" markets all score 100 and consume ~10 of ~20 futures slots. They don't share the existing `story:russia_ukraine` key because they only mention "Russia" (the key requires both "Russia" AND "Ukraine"). Add a broader `story:russia_war` key that matches Russia + capture/territory/advance/offensive keywords. Cap at 2.

**Fix shipped:** Russia/Russian + capture/seize/occupy/annex/advance/offensive/territory/frontline/place keywords now map to the existing capped `story:russia_ukraine` family. Tests prove Ukraine-omitted territory markets group together and diversify to the top 2 variants.

**Files:** `backend/app/utils/feed_market_quality.py` (`_story_key()`, `per_story_caps`)

**~~0u-R3. Fix frontend localStorage dismiss persistence~~** — SHIPPED May 18

`handleDismiss` in `discover/page.tsx:537` calls `setDismissed()` but never writes to localStorage. Dismissed items reappear on every page refresh. One-line fix: persist the updated set to localStorage inside the callback.

**Fix shipped:** `handleDismiss` now writes the updated dismissed-id set to `discover_dismissed` in localStorage. `npm run build` passed after clearing generated `.next` cache from a full local disk.

**Files:** `frontend/app/discover/page.tsx` (~line 537)

**~~0u-R4. Election allowlist: penalize non-major elections~~** — SHIPPED May 18

Instead of blocklisting obscure elections (whack-a-mole), define `_MAJOR_ELECTION_RE` — an allowlist of elections that deserve the full politics base score (US federal, UK/French/German/Canadian/Brazilian/Indian national, EU Parliament). Markets containing "election/winner/nominee" that don't match get `FOREIGN_LOCAL_ELECTION_PENALTY = -30`.

**Fix shipped:** Politics/election futures now receive `FOREIGN_LOCAL_ELECTION_PENALTY = -30` when they look election-related but do not match the major-election allowlist. Tests cover Andalusia-style regional election penalty and US presidential election preservation.

**Files:** `backend/app/utils/futures_highlights.py`

**~~0u-R5. Soccer league allowlist: penalize non-top-tier soccer futures~~** — SHIPPED May 18

Define `_TOP_TIER_SOCCER_RE` — EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, Europa League, MLS, FIFA World Cup, Copa Libertadores, Copa America, Liga MX. Soccer futures not matching this AND not already caught by `_MINOR_LEAGUE_PATTERNS` get `OBSCURE_SOCCER_PENALTY = -20`. Add story keys and caps: `story:foreign_local_elections` (cap 1), `story:minor_soccer_leagues` (cap 1).

**Fix shipped:** Futures highlight scoring now applies `OBSCURE_SOCCER_PENALTY = -20` to soccer futures that are neither minor-pattern matches nor top-tier allowlist matches. Feed market quality now groups non-top-tier soccer into `story:minor_soccer_leagues` with a cap of 1. Focused tests cover the top-tier allowlist, Chilean Primera Division penalty, story key, and cap.

**Files:** `backend/app/utils/futures_highlights.py`, `backend/app/utils/feed_market_quality.py`

**~~0u-R6. Steeper swipe penalty escalation~~** — SHIPPED May 18

Current max category penalty is -0.40 (0.60x multiplier). A 100-score market becomes 60 — still prominent after 20+ swipes. Add escalation tiers: 5+ swipes → -0.60 (0.40x), 8+ swipes → -0.80 (0.20x). Lower `MIN_MULTIPLIER` from 0.30 to 0.15 (only reachable after 8+ negative swipes). Increase `FEATURE_DISLIKE_MAX_PENALTY` from -0.12 to -0.25.

**Fix shipped:** `PersonalizationContext` now carries `discover_category_negative_counts`; category dislike penalties escalate at 5+ and 8+ negative swipes, `MIN_MULTIPLIER` is 0.15, and feature dislike caps at -0.25. Tests cover escalation tiers, feature dislike capping, and bounded multipliers.

**Files:** `backend/app/utils/personalization.py`, `backend/app/routes/feed.py` (`_build_discover_category_affinities()`)

**~~0u-R7. Story-key propagation of dismiss signal~~** — SHIPPED May 18

Currently dismissing market #12345 only suppresses that exact ID. Add `recent_dismissed_story_keys` and `recent_dismissed_group_ids` to `PersonalizationContext`. Compute `_story_key()` from each dismissed market's `item_name` during context loading. Suppress all markets matching a dismissed story_key or group_id.

**Fix shipped:** Discover personalization context now records recently dismissed story keys and grouped futures IDs. `_score_futures()` skips candidates sharing a dismissed group_id or story_key outside My Teams mode. Tests cover group propagation, story-key propagation, and My Teams bypass behavior.

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/personalization.py`

**0u-R8. Tests for all ranking fixes** — PARTIAL May 18

Unit tests for: league-gated event demotion (Ligue 2 upset demoted, NBA upset kept), Russia-war story key matching and cap, election/soccer allowlists, escalated penalty tiers, story-key dismiss propagation.

**May 18 coverage shipped:** R1-R7 now have focused tests/build coverage.

**Files:** `backend/tests/test_feed_market_quality.py`, `backend/tests/test_personalization.py`, new test files as needed

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

**~~0u-N2. Strengthen LLM metadata consumption~~** — SHIPPED May 18

The `discover_llm` enrichment already produces `audience_scope` (broad/mainstream/niche/local/specialist) and `junk_flags` (local_election, low_tier_sports, etc.) but the penalty in `_discover_llm_score_adjustment()` is too small (-4 for niche scope, -4 to -16 for junk flags). Steps:
1. Increase `audience_scope` penalties: niche → -15, local → -25, specialist → -20
2. Increase `junk_flags` penalties: `local_election` → -20, `low_tier_sports` → -15
3. Add new junk flags to the LLM prompt: `minor_soccer`, `procedural_politics`, `commodity_ladder`
4. Re-run enrichment for feed-shaped candidates and measure impact on `audit_feed_quality.py`

**Fix shipped:** `_discover_llm_score_adjustment()` now applies stronger bounded penalties for niche/local/specialist scope and specific junk flags (`local_election`, `low_tier_sports`, `minor_soccer`, `procedural_politics`, `commodity_ladder`), with the lower bound widened to -30. The enrichment prompt now explicitly names the new junk flags. Tests cover local junk, new flag penalties, and niche scope.

**Files:** `backend/app/routes/feed.py` (`_discover_llm_score_adjustment()`), LLM enrichment prompt

**~~0u-N3. Category-aware event-vs-futures balancing~~** — SHIPPED May 18

Currently events and futures compete on raw score, and events dominate because live games score 80-100 from basic signals. The first-page diversity caps `sports_culture` events at 3, but this only applies to the first 20 items. Steps:
1. Add a per-category event budget beyond the first page (e.g., max 5 soccer events, max 5 baseball events in the full feed)
2. Allow high-scoring futures to "promote" into event slots when available events are low-tier (score < 50 after demotion)
3. Add a "category hunger" signal: categories with zero items in the top 20 get a +15 urgency bonus for their best candidate
4. Enforce the entertainment cap of 3 is treated as a *floor* (guarantee at least 1 entertainment item in top 20 if any score >= 80)

**Files:** `backend/app/routes/feed.py` (post-scoring ranking), `backend/app/utils/feed_market_quality.py` (first-page diversity)

**Fix shipped:** Discover mode now runs a pure post-demotion balancing pass that defers low-score events and over-budget sport buckets behind futures without mutating visible scores. First-page mixing also gives strong missing categories a slot, including an entertainment floor when a candidate scores 80+. Tests cover over-budget soccer events, low-score event deferral, and entertainment floor behavior.

**~~0u-N4. Semantic similarity for dismiss propagation~~** — SHIPPED May 18

Story-key propagation (R7) handles cases where dismissed markets share an explicit key. For the long tail, add lightweight semantic similarity so dismissing "Chilean Primera Division champion" also suppresses "Who wins the Chilean league?" Steps:
1. Extract entity/topic tokens from dismissed market names (reuse existing `_discover_feature_tokens()`)
2. For each candidate market, compute Jaccard similarity of feature tokens against dismissed items
3. If similarity > 0.6, apply a -0.30 soft penalty (not a hard filter)
4. Cap computation cost: only compare against the 50 most recent dismisses

**Fix shipped:** `_load_personalization_context()` now records semantic token sets for the 50 most recent Discover dismiss/unlike actions. `_discover_semantic_tokens()` keeps compact topic/region/team/term tokens, normalizes winner/champion language to `term:win`, and bridges league phrasing such as "Primera Division" ↔ "league". `compute_event_multiplier()` and `compute_futures_multiplier()` compare candidate tokens against those recent dismisses with Jaccard similarity, ignore generic category/type/archetype/format tokens, and apply a bounded `semantic_dismiss:-0.30` multiplier penalty when similarity is greater than 0.60. This is intentionally a soft downrank; group_id and story_key matches remain the only hard related-dismiss suppression path.

**Files:** `backend/app/routes/feed.py` (scoring loop), `backend/app/utils/personalization.py`

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
1. Fix the iOS Xcode package-resolution blocker before TestFlight: `xcodebuild -list -project "ios/Bain Luck/Bain Luck.xcodeproj"` currently fails resolving `app-check` with "Missing or empty JSON output from manifest compilation". This blocks reliable native compile verification.
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
   - Add a small trend panel for repeat/stale rates over the last 1h/24h/7d so we can tell whether fixes are working.
4. Automate ranking progress after manual hill-climb sessions:
   - Convert repeated manual fixes into durable rules: auto-hide stale root-cause classes, auto-cap repeat families, and auto-promote/downrank only when a reviewed pattern has enough impressions and confidence.
   - Add a background job that writes daily Discover ranking deltas: repeat/stale rates, cards fixed, cards newly offending, top root causes, and whether automated rules improved or regressed the launch-health metrics.
   - Add guardrails before automation can affect ranking globally: minimum impression counts, max score delta, expiry windows, and an admin rollback path for any automated rule.
5. Automate the Polymarket email-highlight ground truth pipeline:
   - Keep the Apps Script as the Gmail parser, with a clean `Audit Export` tab using stable columns.
   - Configure production with `POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID` and `POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME=Audit Export` so backend jobs read the restricted sheet through the shared Firebase service account.
   - Add a scheduled backend/admin import path that fetches the export and persists a snapshot, so audit/admin metrics do not depend on fetching Google Sheets during the request.
   - Alert or surface an admin warning when the export is stale for more than 48 hours, row count drops sharply, or parse coverage changes unexpectedly.
   - ✅ First external-curator source lane shipped as an advisory local-input parser: `EXTERNAL_CURATOR_GROUND_TRUTH_PATHS` accepts CSV/JSON/JSONL exports, keeps only public URL metadata, performs no scraping/network calls, dedupes rows, and feeds audit/admin debug alongside email highlights. Source health/freshness diagnostics now report per-curator row counts, latest dates, stale flags, and platform mix in `/admin/discover-quality`. `scripts/normalize_external_curator_ground_truth.py` normalizes manually collected social/newsletter exports or copied one-market-per-line text into canonical CSV/JSONL for production config. Next: persist reviewed curator rows.
6. Add persisted matching diagnostics for email-highlight rows: matched `futures_markets.id`, current Discover rank, score bucket, missing reason, category/story family, and whether the card had usable image/context/explanation treatment. May 18 slices: added `discover_ground_truth_diagnostics` plus `scripts/snapshot_discover_ground_truth_diagnostics.py` to persist current debug API hit/miss rows for combined, email, and external-curator ground truth under a run ID; added a daily background task plus admin trigger/read endpoints so production can queue snapshots without Heroku CLI access; added `/admin/discover-quality` run trends, row drilldown, inline pipeline traces, quick filters, and pagination. Next: persist reviewed curator rows and add a non-request-time import snapshot for email/curator ground truth.
7. Use email-highlight misses as an audit signal first, not a direct ranking boost. Tune candidate pools, story mixing, explanation/media treatment, and fun-market surfacing only after reviewing false positives and duplicate-family risk. May 18 slices: added a bounded `nonsports_editorial_recall` candidate pool for low-volume high-texture terms (aliens/UFO, AI labs/models, awards/TV, health/weather risks) so these markets enter scoring while still passing through normal quality caps; then promoted absurd-but-real public-interest markets while demoting daily public-equity direction filler. May 18 follow-up: expanded recall terms for measured misses (`recession`, `Spotify`, `Billboard`, `Rotten Tomatoes`, `Xi Jinping`, `SpaceX/Starship`) and added a sports editorial recall pool for mainstream futures such as FIFA World Cup, Champions League, Super Bowl, NBA Finals, Stanley Cup, and World Series, with a `story:fifa_world_cup` cap. A tail backfill now preserves ranks 1-20 but can swap up to six strong recall stories into ranks 21-50 when they are eligible but stuck below same-score clusters; 2028 presidential markets and reviewed major US civic-power stories such as LA Mayor / Virginia redistricting / 2026 midterms are included in that tail lane. Audit matching now treats `Recession this year?` and `US recession by end of 2026?` as equivalent so the hill-climb metric does not count represented macro stories as false misses. The DB trace also distinguishes exact/source-equivalent misses from loose related markets, so World Cup squad/final props no longer look like ranking failures for exact World Cup winner ground-truth rows, and admin/debug bucket counts are recomputed after DB trace root causes are attached. SpaceX IPO, Spotify/Billboard, and text-matched FIFA World Cup markets now share story keys so represented sibling variants are classified correctly even when upstream categories are loose.
8. Use the aggregate feedback review queue daily during TestFlight: accept only human-reviewed ranking changes at first, prioritizing high-dismiss/high-rank downrank candidates, high-open/share/context-expand low-rank promote candidates, and rage-shake reports where Discover context identifies repeated or stale cards.
9. Add account-level preference sync so web/native local tuning can merge into server-side profiles after sign-in.
10. Add comparison-game cards as part of the Discover game cadence, pairing high-interest markets across categories and recording those guesses separately from Higher/Lower cards.
11. Use engagement opportunity signals, repeat/stale launch-health signals, rage-shake context, and Polymarket email-highlight misses to tune ranking, card design, and explanation/media treatment.

**Files:** `backend/app/routes/feed.py`, `backend/app/routes/admin.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/app/utils/personalization.py`, `backend/app/utils/polymarket_email_ground_truth.py`, `backend/scripts/audit_feed_quality.py`, `frontend/app/discover/page.tsx`, `frontend/app/admin/discover-quality/page.tsx`, `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`, `ios/Bain Luck/Bain Luck/Views/BugReportView.swift`
**Parallel Safety:** Yellow

### ~~0n. Navigation Redesign~~ — DONE (May 11-12)

Shipped across web and native. Discover is default landing page (`/`). Sports at `/sports`. Desktop: Discover | Sports | Browse (dropdown) | My Stuff. Mobile bottom nav: Discover | Sports | Search | My Stuff. Native: Discover | Sports | Browse | Search | My Stuff. Browse dropdown/tab has Politics, Entertainment, Economics, Weather. About behind user menu. Footer removed. Tab persistence deferred.

### ~~0s. League Pages — ALL PHASES SHIPPED~~

**Phase 1 (backend):** ✅ SHIPPED (May 6)
**Phase 2 (frontend):** ✅ SHIPPED (May 6)
**Phase 3: Cross-sport generalization** — ✅ SHIPPED May 17. MoversRibbon, sport-aware layout applied to NHL, MLB, NFL.
**Phase 4: iOS parity** — ✅ SHIPPED (May 13) — LeagueGridView with all market sections.

**Files:** `backend/app/routes/leagues.py`, `ios/.../Views/LeagueGridView.swift`

### ~~0r. Golf Data Quality Issues~~ — FIXED May 18

**Problem:** Tour misclassification (Hainan = Asian Tour, not PGA Tour) — fixed by preserving DataGolf event-level `tour` metadata and using it before defaulting generic tournament names to PGA Tour.

**Guardrail:** `Hainan Open` with `tour="asian"` now classifies as Asian Tour even if an external ID looks like PGA.

**Files:** `backend/app/tasks/datagolf.py`, `backend/app/routes/golf.py`
**Parallel Safety:** Green

---

## Rage Shake Triage #7 (May 17) — Bugs #49-58

10 bug reports. Consolidated into 6 distinct issues. All touch feed.py or the Discover feed — hand off to Discover thread.

### ~~BR57/58. All Outcomes Show Equal Odds (33%/26%/26%/26%)~~ — FIXED May 17

Feed normalization now renormalizes to displayed outcomes only, preventing Billboard/multi-outcome markets from showing artificially equal probabilities.

**Files:** `backend/app/routes/feed.py` (top_outcomes_data normalization)

### ~~BR49. Yes/No Display on Non-Binary Multi-Outcome Markets~~ — FIXED May 17

Feed now detects "Yes"/"No" top outcomes on non-binary questions and falls back to the market name or leading named outcome.

**Files:** `backend/app/routes/feed.py` (outcome display), `ios/.../Views/DiscoverView.swift`

### ~~BR50. Sparse Snapshot Chart on Market Detail~~ — FIXED May 17

Sparse chart handling improved — markets with limited snapshot data now display appropriately.

**Files:** `backend/app/tasks/kalshi.py` (polling frequency), futures detail page

### ~~BR51. PGA Championship: Playoff — Missing Trend Line + Search Issue~~ — FIXED May 17

Binary chart rendering and multi-word search matching both fixed.

**Files:** `ios/.../Views/FuturesDetailView.swift` (chart rendering), `backend/app/routes/events.py` (search)

### ~~BR52/53. My Stuff "Your Teams' Odds" — Wrong Player/Team Associations~~ — FIXED May 17

Team matching now uses sport-scoped matching — WNBA players no longer match to NHL teams based on city name. Year context added to playoff progression display.

**Files:** `ios/.../Views/MyStuffView.swift`, backend user/feed endpoints

### ~~BR54/56. Feed Quality — Low-Interest Cards, Repetitive, Missing Spotify/Netflix #1~~ — FIXED May 17

Feed quality classifier updated: minor sports suppressed more aggressively, Netflix/Spotify #1 markets no longer filtered by dedup, dismiss signals now apply stronger personalization penalties.

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/personalization.py`

### ~~WATCH-1. Apple Watch App Mostly Black, Occasionally Shows Malformed Content~~ — FIXED May 17

Reliability fixes shipped: reduced feed request limit, aggressive timeout with retry, improved error handling, and decode stability improvements.

**Files:** `ios/Bain Luck/BainLuckWatch Watch App/` (8 Swift files)

---

## Manus Sweep Findings (May 15, 2026)

10-module automated audit. Results in `Manus/audit_results/2026-05-15/`. Sweep ran during a deploy-triggered outage, so some findings are outage artifacts. Real findings below.

### ~~MS15-1. Cross-Game Market Contamination~~ — FIXED May 15

Polymarket group_id lookup in game-markets had no time window filter. In playoff series, Game 1's sub-markets leaked onto Game 2's page. Fixed: added ±12h commence_time filter to match the unlinked fallback query.

### ~~MS15-2. O/U Monotonicity Violation~~ — FIXED May 15

Frontend monotonicity enforcement referenced original values instead of corrected ones. Backend dropped violating items instead of capping. Fixed both + added 0% threshold filtering.

### ~~MS15-3. Weather Data 26 Days Stale~~ — FIXED May 15

Hardcoded fallback data replaced with loading skeletons. Dynamic date and market counts now pulled from live API response.

### ~~MS15-4. NBA Grid OKC 105.2% Conference Win~~ — FIXED May 15

Normalization pushed OKC above 100%. Fixed: post-normalization cap at 100% in playoff_grid.py + defense-in-depth caps in playoffs.py. Regression test added.

### ~~MS15-5. Chart Timing Score 52/100~~ — FIXED May 16

**Problem:** Charts terminate prematurely (e.g., 8th inning cutoff in baseball). Missing game state markers for AFL. Charts start too early for some events.

**Status:** Fixed May 16; no active parallel work remains on this audit item.

**Files:** `frontend/components/OddsChart.tsx`, `backend/app/routes/events.py` (chart data)
**Parallel Safety:** Green

### ~~MS15-6. MLS Page Infinite Loading~~ — NOT REPRODUCIBLE, CLOSED

Investigated May 15. APIs return correctly (200, valid data). Frontend has proper timeout/retry/finally. Likely transient issue during the Manus sweep (deploy-triggered outage or cold dyno). Closing as not reproducible.

### ~~MS15-7. Inconsistent Error States Across Pages~~ — FIXED May 16

**Problem:** 3 different error handling patterns across league pages, category pages, and hub pages. No unified error component. MLS never errors, NBA shows "Failed to load", economics shows "Loading...".

**Status:** Being fixed by another agent. Do not start parallel work on error state components.

**Files:** Frontend components (various)
**Parallel Safety:** Red (active work)

### ~~MS15-8. Deploy Crash — Rapid Pushes Kill Heroku Dyno~~ — FIXED May 15

CI workflow now has a `deploy` job with `concurrency: group: heroku-deploy, cancel-in-progress: true`. Only deploys after both test jobs pass. Step-level secrets check replaced with shell-level (May 16). CI-gated deploy is working.

---

## Manus Sweep Findings (May 11, 2026) — MOSTLY RESOLVED

10-module automated audit. Results in `Manus/audit_results/2026-05-11/`. 10 of 14 resolved, 4 open.

**Resolved:** ~~MS-1~~ (false alarm), ~~MS-2~~ (false alarm), ~~MS-3~~ (prop monotonicity), ~~MS-4~~ (politics misclassification), ~~MS-5~~ (Spotify normalization), ~~MS-6~~ (economics monotonicity), ~~MS-7~~ (chart stale tails), ~~MS-9~~ (soccer halftime), ~~MS-10~~ (NCAAB settled markets), ~~MS-12~~ (golf grid monotonicity), ~~BUG-NBA~~ (not a bug), ~~BUG-DUP~~ (event merge task handles it).

### ~~MS-8. MLB Chart Rendering Failure~~ — FIXED May 17

Chart gap handling improved — MLB charts no longer show massive data gaps.

**Files:** `backend/app/routes/events.py`

### ~~MS-11. Completed Market Shows Stale Live Probability~~ — FIXED May 17

Stale probability display on completed markets resolved.

**Files:** `backend/app/routes/events.py`

### MS-13. Missing Sport Coverage (INFO)

UFC/MMA, Tennis, F1, Esports have upstream markets but no dedicated pages. Feature gap, not bug.

### ~~MS-14. EPL/UFC/Tennis Pages Non-Functional~~ — RESOLVED (May 13)

EPL grid loads correctly now (`/api/playoffs/epl` returns data). UFC and Tennis don't have league configs and aren't in the Browse tab navigation (removed when pills were changed to specific leagues). No dead-end paths remain.

---

## ~~Rage Shake Triage (May 7-8)~~ — ALL 14 ITEMS RESOLVED

All 16 bug reports triaged, 14 new items identified, all resolved May 8 across two parallel sessions. Details in `docs/completed-features.md`.

**Only remaining from original triage:** RS-5 (iPad sign-in) is FIXED but needs TestFlight build to verify on physical device.

---

## ~~Rage Shake Triage #3 (May 11) — Bugs #25-30~~ — ALL 6 FIXED (May 12)

~~BR25~~ (stale 45% Yes — staleness threshold lowered to 95%), ~~BR26~~ (lowercase "nba" — `.uppercased()`), ~~BR27~~ (probabilities >100% — feed normalization when sum >105%), ~~BR28~~ ("2 sources" badge — now shows "KALSHI + POLYMARKET" via `sources` array), ~~BR29~~ (guess cards on closed events — status + probability checks), ~~BR30~~ (stale Met Gala — 14-day NULL resolution_date filter). Details in `docs/completed-features.md`.

---

## Rage Shake Triage #6 (May 16) — Bugs #41-48

8 bug reports. BR41 dismissed (transient outage from May 15 deploy crash). 7 real issues consolidated into 5 distinct problems.

### ~~BR42/43. My Stuff Shows Low-Tier Junk~~ — FIXED May 16

Added tier filter to `my_teams_only` feed: only Tier 1/2 sports (11 sport keys: NBA, NHL, MLB, NFL, NCAAB, WNBA, NCAAF, EPL, MLS, UCL, MMA) shown in My Stuff. Tier 3 (NCAA hockey, esports, minor soccer) excluded at SQL level. "Boston" substring matching still works but only for major leagues.

### ~~BR44/46. Stale Celtics NBA Finals Card~~ — FIXED May 16

Added "soft-settled binary" filter: sports binary markets with leader ≥60% and <2pp 24h movement are suppressed. Protects underdog rises (leader opened <50%) and non-sports markets (politics/economics excluded). 5 unit tests. Catches the entire BR31/BR44/BR46 class of stale elimination markets.

### ~~BR45. Sign-In Server Error 500~~ — FIXED May 16

**Problem:** Anonymous user on iPhone 15,4 (iOS 26.0.0) sees "Server error (500). Please try again." on My Stuff sign-in page. Different from BR40 (which was 401 audience mismatch, now fixed). This is a 500 — backend crash during auth endpoint.

**Root cause:** `User.created_at` was None after flush — the column lacked a server default. Fixed in commit `4cc1239`.

**Files:** `backend/app/routes/auth.py`, `backend/app/services/firebase_auth.py`
**Parallel Safety:** Green

### BR47. Netflix Show Outcomes All 33% — INVESTIGATED May 16, NOT A CODE BUG

Not a normalization bug — probabilities are genuinely flat in the database (`current_probability` ≈ 0.33 for all 3 outcomes). The "100%" in the hook description is stale — generated by LLM enrichment when one show was dominant, but prices have since equalized. Fix: re-run hook enrichment for this market, or add staleness detection that regenerates hooks when data contradicts them.

### ~~BR48. US House Probabilities Don't Sum to 100% (102%)~~ — FIXED May 16

Lowered normalization threshold from 1.05 to 1.01 for 2-outcome binary markets. Multi-outcome markets stay at 1.05 (small overages from independent sources are expected).

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

9 bug reports from May 14-15 TestFlight users. Consolidated into 6 distinct issues + 1 recurring tool bug.

### BR38/33/35/34. Feed API Failures — Discover, Sports, and Challenges All Down (P1)

**Problem:** Four separate reports from two devices (iPhone18,1 anonymous, iPhone18,2 Alex) all showing the same symptom: feed endpoints returning errors.
- BR38 (Alex, Discover): "Couldn't load Discover. Pull to retry."
- BR33 (anonymous, Discover): Same — "Couldn't load Discover. Pull to retry." with onboarding tooltip still showing
- BR35 (anonymous, Sports): "Couldn't Load Feed — Server error (500). Try again in a moment."
- BR34 (anonymous, Discover challenge): "No challenge cards right now" — Today's Challenge shows "Question 1 of 1" but has no cards. Challenge card selection depends on the feed working, so this is downstream of the feed failure.

**Root cause (investigate):** The Discover feed (`GET /api/feed`) and Sports feed are both failing. Could be:
1. A database query timeout or connection pool exhaustion (check Heroku pg:info connections)
2. A crash in `routes/feed.py` from a bad market/outcome causing an unhandled exception (check Sentry)
3. A Celery task holding DB connections and starving the web dyno
4. Transient — all 4 reports are from a ~20 minute window (May 14 6:47-7:00 PM ET). Could have been a brief outage that self-resolved.

**Investigation steps:**
1. Check Sentry for 500 errors on `/api/feed` and `/api/sports-feed` around May 14 6:45-7:05 PM ET
2. Check Heroku logs for that time window: `heroku logs --since 2026-05-15T01:45:00Z --until 2026-05-15T02:00:00Z -a bainluck`
3. Check current feed health: `curl -s https://api.bainluck.com/api/feed | head -c 200`
4. If transient, add better error context to the iOS error states (show the actual error message from the API, not just "Couldn't load")

**Files:** `backend/app/routes/feed.py`, `ios/.../Views/DiscoverView.swift`, `ios/.../Views/FeedView.swift`
**Parallel Safety:** **RED — collides with Discover thread.** Do not fix in parallel with feed.py work.

### ~~BR40. iOS Sign-In Rejected (401)~~ — FIXED (May 15)

Root cause: Apple Sign-In audience mismatch. Backend validated JWT against `APPLE_SERVICES_ID` (`com.bainluck.web`) but iOS sends `aud = "com.bainluck.Bain-Luck"` (bundle ID). Apple Sign-In from iOS had never worked. Fix: accept both web Services ID and iOS bundle ID as valid audiences via `valid_audiences` list in `auth.py`. Google Sign-In unaffected (uses access token verification, not JWT audience).

### ~~BR39. Preferences Pill Buttons Text Wrapping~~ — FIXED (May 15)

Added `.lineLimit(1)` + `.fixedSize()` to pill button Text in `PreferencesView.swift`. Category name truncates instead of pills wrapping.

### ~~BR37. Economics Page Parse Error — iOS~~ — FIXED (May 15)

Three Decodable mismatches: `EconomicsMarket.prob` Int→Double, `CPIRelease.peakIs` String?→Int?, added missing `sideMarkets` field for recession/markets/energy themes.

### ~~BR36. Politics Probabilities Don't Sum to 100%~~ — FIXED (May 15)

Added `_normalize_outcome_probs()` to `politics.py` (same >105% threshold as feed). Applied to `_market_row()` (all theme sections) and `_build_presidential()` (nominee merging with per-source normalization). 14 new tests.

### ~~BR32. My Stuff Shows Irrelevant "Top Markets"~~ — FIXED (May 15)

Root cause: My Stuff fetched generic futures from feed endpoint. Even with team filtering, card displayed global top-3 outcomes instead of user's team. Fix: set `includeFutures: false` (matching web behavior), team futures shown only via dedicated "Your Teams' Odds" section. Added `MyTeamFuturesCard` for personalized display.

### ~~BR-MARKUP. Rage Shake Annotation Coordinate Offset~~ — FIXED (May 15)

Root cause: PKCanvasView overlay used `.frame(maxHeight: 300)` without width constraint, so canvas was wider than rendered image. Three fixes: explicit frame sizing matching screenshot aspect ratio, PKCanvasView scroll/inset lockdown, independent scaleX/scaleY with retina-aware rendering.

---

## Rage Shake Triage #8 (May 17) — Bugs #60-75

Claude CLI failed to process these because screenshot image handling returned `API Error: 400 Could not process image`. Items were added from text-only report context; screenshots should be reviewed later with the links below.

### ~~BR60. Yes/No Markets Should Not Show Top-5/Top-10 Framing~~ — FIXED (May 17)

**Problem:** Binary yes/no market cards show "top 5" or "top 10" framing, which makes no sense for two-outcome markets.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/60/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_60.jpg`

**Files:** `backend/app/routes/feed.py`, `ios/.../Views/DiscoverView.swift`
**Parallel Safety:** Yellow

**Fix:** Binary `No` labels now preserve side semantics instead of falling back to the bare positive market topic.

### ~~BR61. Native Discover Card Question Truncated~~ — FIXED (May 17)

**Problem:** Question text truncates on a native Discover card.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/61/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_61.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`
**Parallel Safety:** Yellow

**Fix:** Native Discover card, guess-card, compact-row, and grouped-card text now allows more lines with fixed vertical sizing on narrow screens.

### BR62. Better Aggregation for Related/Clustered Markets (P2)

**Problem:** Related markets need a better aggregation/surfacing model so users see one coherent question or cluster instead of fragmented market rows.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/62/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_62.jpg`

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/feed_market_quality.py`, category routes
**Parallel Safety:** Red (touches feed ranking/grouping)

**Progress May 17:** Discover feed now emits `group_id`/`group_type`, and native Discover grouping prefers backend grouping IDs/canonical keys instead of the fragile first-three-words title fallback. Full cross-surface aggregation remains open.

### ~~BR63. Prediction Stats Empty Despite Weeks of Predictions~~ — FIXED (May 17)

**Problem:** User has made predictions for weeks but native stats screen shows no stats.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/63/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_63.jpg`

**Files:** `backend/app/routes/user.py`, `ios/.../Views/PredictionStatsView.swift`, `ios/.../Services/APIClient.swift`
**Parallel Safety:** Yellow

**Fix:** Prediction stats/resolutions routes now resolve optional auth and include authenticated user predictions instead of falling back to anonymous session-only lookup.

### ~~BR64. Discover Ranking Fine-Tuning Section Is Confusing~~ — FIXED (May 17)

**Problem:** Native Discover exposes a fine-tuning/ranking section that feels confusing; users should not have to manage ranking manually.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/64/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_64.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`
**Parallel Safety:** Yellow

**Fix:** Removed the native Discover tuning/debug toolbar menu and simplified the feed-shaping banner language.

### ~~BR65. Baseball Game State Shows Half Indicators~~ — FIXED (May 17)

**Problem:** Baseball markets/events show `HT` and `2H` game state indicators; baseball should show innings.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/65/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_65.jpg`

**Files:** `backend/app/routes/events.py`, `ios/.../Views/EventDetailView.swift`, `ios/.../Views/LeagueGridView.swift`
**Parallel Safety:** Yellow

**Fix:** Normalized baseball live state in backend event/feed payloads so baseball uses inning labels and suppresses basketball-style half indicators.

### ~~BR66. Native Sports Feed Runs Out After Live Cards~~ — FIXED (May 17)

**Problem:** On iOS Sports tab, after scrolling past a few "Live Now" cards, there is nothing else to see. The feed should continue with upcoming, recent, and relevant non-live sports content instead of feeling empty once live cards are exhausted.

**Context:** iPhone18,2, iOS 26.5.0, current page `Feed`, `live_game_count=3`, submitted May 17 2026 2:04 PM.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/66/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_66.jpg`

**Investigation notes:**
1. Check whether `FeedView` only renders live sections for the current response shape or fails to request/fill additional sections after live games.
2. Compare native Sports feed structure against web `/sports`: live, upcoming, recent/completed, leagues/market sections.
3. Confirm backend `/api/feed` or sports endpoint returns enough non-live items for native, and whether native filters them out.

**Files:** `ios/.../Views/FeedView.swift`, `ios/.../Services/APIClient.swift`, `backend/app/routes/feed.py`
**Parallel Safety:** Yellow

**Fix:** Native Sports feed now fetches an event-only supplemental page and appends non-live event rows behind the ranked feed so scrolling past live cards does not empty the tab.

### ~~BR68. Final Score Displays As `final 0.0`~~ — FIXED (May 17)

**Problem:** Native UI displays `final 0.0` at the top of a market/event card, which is confusing and likely a score/status formatting bug.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/68/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_68.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`, `ios/.../Views/EventDetailView.swift`, backend event response shape if value is wrong
**Parallel Safety:** Yellow

**Fix:** Native Discover no longer shows/submits futures guess cards when the leader probability is missing, preventing stored `0.0` actual probabilities.

### ~~BR69. Calibration Data Looks Wrong/Unimpressive~~ — FIXED (May 17)

**Problem:** Calibration page/data appears wrong enough to undermine trust. Need verify calibration buckets, labels, sample sizes, and whether native/web are presenting the right cohort by default.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/69/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_69.jpg`

**Files:** `backend/app/routes/calibration.py`, `backend/app/tasks/backfill_winners.py`, `ios/.../Views/CalibrationView.swift`
**Parallel Safety:** Yellow

**Fix:** Public calibration now only includes settled-looking futures outcomes, preventing default unresolved loser rows from polluting buckets.

### ~~BR70. My Stuff Category Section Formatting Is Noisy~~ — FIXED (May 17)

**Problem:** My Stuff category section looks poorly formatted and highlights too many weird/low-value categories. Native should match the cleaner web treatment instead of surfacing every odd category token.

**Context:** iPhone18,2, iOS 26.5.0, current page `My Stuff`, submitted May 17 2026 2:30 PM.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/70/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_70.jpg`

**Investigation notes:**
1. Compare native My Stuff category rendering against the web My Stuff/category summary design.
2. Restrict highlighted categories to a small curated set, merge synonyms, and hide noisy/internal categories.
3. Tighten spacing, typography, and wrapping for the category section on iPhone-width screens.

**Files:** `ios/.../Views/MyStuffView.swift`, `ios/.../Views/PreferencesView.swift` if shared category chips are reused
**Parallel Safety:** Green

**Fix:** Native My Stuff now filters noisy/internal team-future rows, renames the generic section to `Team Markets`, and tightens row wrapping/probability layout.

### ~~BR72. Missing Early-Inning Game State Indicators~~ — FIXED (May 17)

**Problem:** Native sports/game UI is missing game state indicators for the first few innings.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/72/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_72.jpg`

**Files:** `backend/app/routes/events.py`, `ios/.../Views/EventDetailView.swift`, `ios/.../Views/FeedView.swift`
**Parallel Safety:** Yellow

**Fix:** Same backend normalization as BR65 now emits `Top 1st`, `Bottom 2nd`, etc. from baseball source data.

### ~~BR73. Remove Native Discover Category Filter Pills~~ — FIXED (May 17)

**Problem:** Native Discover category pills are unnecessary and visually noisy; ranking should be good enough that users do not need manual category filters.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/73/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_73.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`
**Parallel Safety:** Yellow

**Fix:** Removed native Discover category filter state and pill row; ranking owns category mix.

### ~~BR74. Pull-To-Refresh Does Not Produce New Discover Cards~~ — FIXED (May 17)

**Problem:** Repeated pull-to-refresh on native Discover does not produce new cards.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/74/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_74.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`, `backend/app/routes/feed.py`
**Parallel Safety:** Red (feed pagination/seen-state)

**Fix:** Pull-to-refresh resets native Discover presentation state (`visibleCount`, dismissed cards, impression dedupe) before reloading.

### ~~BR75. Native Discover Names Truncated~~ — FIXED (May 17)

**Problem:** Names are truncated in native Discover card UI.

**Screenshot:** `curl -s "https://api.bainluck.com/api/admin/bug-reports/75/screenshot?secret=$ADMIN_TOKEN" -o /tmp/bug_75.jpg`

**Files:** `ios/.../Views/DiscoverView.swift`
**Parallel Safety:** Yellow

**Fix:** Same native Discover text expansion as BR61 gives outcome names, subject names, and compact-card names more vertical room.

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

**Goal:** When a bug report is resolved, automatically notify the filer with a personal, LLM-written email explaining what was fixed and thanking them. Creates a retention loop that encourages more bug reports.

**Phases:**

### Phase 1: Backend data foundations — ✅ DONE (May 18)
- ~~Add `resolution_summary` text field to `BugReport` model~~ — ✅ SHIPPED May 16 (migration: `add_bugreport_cat`)
- ~~Add `backlog_ref` field~~ — ✅ SHIPPED May 16 (migration: `add_bugreport_cat`)
- ~~Look up and store the filer's email at submission time~~ — ✅ SHIPPED May 18. Authenticated submissions store `user_email` directly on `BugReport`; anonymous reports remain email-free.
- ~~Update the admin PATCH endpoint to accept `resolution_summary` alongside `status`~~ — ✅ SHIPPED May 16

### Phase 2: "Your bug was fixed" email (NEXT)

**May 18 slices shipped:** `send_bug_fixed_email` now has eligibility gates for missing/invalid email, already-sent reports, unresolved reports, and missing resolution summaries; stable prompt input/body builders; Gmail/OpenAI side-effect seams for tests; Celery task registration; multipart plain-text+HTML Gmail messages; sender/recipient validation; CR/LF header-injection rejection; and automated-email suppression headers (`Auto-Submitted`, `Precedence`, `X-Auto-Response-Suppress`). Admin bug-report PATCH now enqueues `app.tasks.send_bug_fixed_email` only on transition to `fixed`/`actioned` with a non-empty resolution summary and no prior notification. `List-Unsubscribe` was intentionally not added because there is no existing one-click unsubscribe URL/token path. Remaining integration: finalize preferences, unsubscribe, and production delivery/compliance settings before broad user-facing sends.

**Email provider decision:** Gmail API via Google Workspace. `bainluck.com` domain is on Google Workspace (set up May 12). Send as `bugs@bainluck.com` (or whichever address you create).

**Implementation steps:**
1. Create a Google Cloud service account with domain-wide delegation, grant it the `https://www.googleapis.com/auth/gmail.send` scope for `bugs@bainluck.com` (or your chosen sender). Add the service account JSON key as a Heroku config var (`GOOGLE_SERVICE_ACCOUNT_JSON`).
2. ~~Create `backend/app/tasks/bug_notifications.py` — a Celery task `send_bug_fixed_email`~~ — ✅ first task slice shipped May 18
3. ~~In the admin PATCH endpoint, when `status` changes to `"fixed"`/`"actioned"` and `resolution_summary` is provided, enqueue the Celery task~~ — ✅ shipped May 18
   - Look up the bug report's `user_email` and `description`
   - If `user_email` exists and `notification_sent_at` is NULL, enqueue the Celery task
4. The Celery task:
   - Calls OpenAI GPT-4o-mini with a prompt:
     ```
     Write a short, warm email (3-4 sentences) to {first_name} thanking them for reporting a bug in Bain Luck.
     Bug they reported: "{description}"
     What we fixed: "{resolution_summary}"
     Tone: personal, grateful, specific. End with encouragement to keep reporting bugs.
     Do not use subject line — just the body. No gambling references.
     ```
   - Sends via Gmail API: from `bugs@bainluck.com`, subject "Your bug report was fixed 🍀"
   - Sets `notification_sent_at = now()` on the BugReport row
5. Add `send_bug_fixed_email` to Celery beat or call it inline (inline is fine for <100/day volume)

**Safeguards:**
- Only send if `user_email` is not NULL and `notification_sent_at` is NULL (no double-sends)
- Only send when transitioning TO `"fixed"` status (not on re-saves)
- Log all sends for audit

**Files:** `backend/app/tasks/bug_notifications.py` (new), `backend/app/routes/admin.py` (trigger), `backend/app/tasks/__init__.py` (register task)
**Dependencies:** Google Workspace (done), service account with domain-wide delegation + Gmail send scope, OpenAI API key (already configured)

### Phase 3: Automation (LATER)
- When a commit message references "BR{N}" (e.g., "Fix BR27: normalize probabilities"), automatically mark the corresponding bug report as `fixed`
- Surface unresolved bug reports in the admin dashboard with age badges

**Files:** `backend/app/models/models.py` (BugReport), `backend/app/routes/admin.py` (PATCH endpoint), `backend/app/routes/feedback.py` (submission), new `backend/app/tasks/bug_notifications.py`
**Parallel Safety:** Green

---

## Rage Shake Triage #2 (May 11) — Bugs #18-24

3 fixed (#19, #20, #24), 1 waiting on matching cycle (#18), 3 new backlog items (#21, #22, #23).

### BR18. Missing Kalshi for TB vs BOS — WAITING ON MATCHING CYCLE

**Problem:** Kalshi has a Rays vs Red Sox game market but it's not linked on bainluck. Same `tb` abbreviation issue as NHL — `tb_mlb` → "Rays" entry exists in `sport_keys.py` but the matching task needs to re-process unlinked markets.

**Action:** Wait for next `match_prediction_markets` cycle (runs every 15 min). If still unlinked after a cycle, investigate whether the ticker prefix mapping for `tb` is being used correctly for MLB vs NHL disambiguation.

**Files:** `backend/app/utils/sport_keys.py`, `backend/app/tasks/prediction_market_matching.py`
**Parallel Safety:** Yellow

### ~~BR21. iPad Futures Browser Needs Photos/Emojis~~ — FIXED (May 13)

Added image thumbnails and category emoji to FuturesListView rows. Navigation now uses shared `RouteDestination` instead of duplicated route code, matching the TestFlight route consistency fix.

**Files:** `ios/.../Views/FuturesListView.swift`

### ~~BR22. Weather Page Needs City Search~~ — FIXED (May 13)

City search added to both web and iOS. Users can now filter city forecast cards by typing.

### ~~BR23. Weather Cities Need Clickable Probability Graphs~~ — FIXED (May 13)

City cards now link to `FuturesDetailView` (web: `/futures/{marketId}`, iOS: `Route.futuresDetail`). Backend exposes `marketId` per city. No new chart needed — reuses existing futures probability timeline.

### BR-PIN. Cross-Platform Pin Sync + My Stuff Display — PARTIALLY DONE (May 13)

**Completed (May 13):**
- ✅ Web pin sync fixed — was localStorage-only, now syncs events + futures pins to server for signed-in users
- ✅ Cross-device persistence verified working (pin on web, appears on iOS after refresh)

**Remaining:**
1. **My Stuff display:** Pinned events and markets should appear as a dedicated section on My Stuff (web + iOS), showing current probabilities and status
2. **Real-time feel:** After pinning, the item should appear in My Stuff immediately (optimistic update), not after a refresh
3. **iOS → server sync:** Verify `PinManager.syncLocalToServer()` runs on sign-in and that reverse (server → local) also works

**Files:** `ios/.../Services/PinManager.swift`, `ios/.../Views/MyStuffView.swift`, `frontend/app/my-stuff/page.tsx`, `backend/app/routes/user.py` (pin endpoints)
**Parallel Safety:** Yellow

### ~~BR-NAV. Native App Tab Redesign~~ — DONE (May 11), merged into 0n above

### NATIVE-DESIGN. Native Category Pages Are Broken/Ugly (HIGH-PRI)

**Problem:** The iOS/macOS category pages (Economics, Entertainment, Weather, Politics, Preferences) are visually broken and unpolished. Key issues from May 11 screenshots:

1. **Economics** — Shows "Error: The data couldn't be read because it isn't in the correct format." Page is completely broken.
2. **Entertainment** — Dense wall of text, no visual hierarchy, market cards are plain white boxes with no images or color. Looks like a database dump.
3. **Weather** — City forecast grid is an overwhelming spreadsheet of temperature buckets and percentages. No visual design — just raw data tables. Needs temperature visualization (gauges, color gradients) instead of text lists.
4. **Politics** — Best of the bunch (has senate map, color-coded candidates) but market cards below the hero are still plain text lists with no visual richness.
5. **Preferences** — Functional but boring. The interest selector (Love/Big/Wild/Nah) looks like a data table. Needs card-based design with visual weight.

**Claude Design Handoffs (web reference for native parity):**
- Entertainment: `https://api.anthropic.com/v1/design/h/NVy7_G25Hw2F2WPBkuQqJg?open_file=Entertainment.html`
- Politics v1: `https://api.anthropic.com/v1/design/h/nEWFwz9OLZG7YqV9JxY6lw?open_file=Politics+Page.html`
- Politics v2: `https://api.anthropic.com/v1/design/h/RrDcEtPZy_66ZWaWEGhscw?open_file=Politics+Page.html`
- Economics: `https://api.anthropic.com/v1/design/h/eIsTOAYPL_It9o3O4zleDw?open_file=handoff%2Feconomics%2Freference%2FEconomics.html`
- Weather: `https://api.anthropic.com/v1/design/h/S18AFhL5cujQX0CfDqlkBA`

**Completed (May 11-13):**
- ✅ Economics data parsing error fixed (removed `rateCuts` field — backend sends nested arrays, iOS expected market objects, field unused in view)
- ✅ Economics page polished to match Politics/Entertainment design (May 13)
- ✅ Politics, Entertainment, and Weather pages polished (May 13)
- ✅ Preferences page polished (May 13) — ALL 5 NATIVE-DESIGN PAGES COMPLETE

**Files:** `ios/.../Views/EconomicsView.swift`, `ios/.../Views/EntertainmentView.swift`, `ios/.../Views/WeatherView.swift`, `ios/.../Views/PoliticsView.swift`, `ios/.../Views/PreferencesView.swift`

---

## Tier 1 — High Leverage, Do Next

### Bug Report Admin Improvements — MOSTLY DONE (May 16)

1. ~~**Burndown chart**~~ — ✅ SHIPPED (May 13). SVG burndown chart + summary stats (open/closed/avg resolution time) on admin bug reports page.
2. ~~**Category tagging**~~ — ✅ SHIPPED May 16. Added `category` field to `BugReport` model + admin dropdown. Also shipped lifecycle fields (`resolution_summary`, `backlog_ref`). Migration: `add_bugreport_cat`.
3. ~~**Resolution time tracking**~~ — ✅ SHIPPED (May 13). Included in burndown summary stats.
4. ~~**Auto-categorization**~~ — ✅ deterministic admin backfill shipped May 18. The bug-report list fills missing categories from the existing rule-based classifier only when metadata is decisive; ambiguous reports stay uncategorized. GPT-assisted categorization remains optional later if deterministic coverage proves too low.

**Files:** `frontend/app/admin/bug-reports/page.tsx`, `backend/app/models/models.py` (BugReport), `backend/app/routes/admin_engagement.py`, `backend/app/routes/feedback.py`
**Parallel Safety:** Green

### ~~PRD Update~~ — DONE (May 15)

Rewritten from 310→249 lines. Vision, Target Users, User Journeys, Feature Map, Data Architecture, Metrics, Principles, Non-Goals. Present tense.

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

**Current state (May 17, 2026):**
| Source | Resolved | has_winner | Coverage | Target |
|--------|----------|------------|----------|--------|
| Kalshi | ~70K | ~61K | **88%** | 95%+ |
| Polymarket | ~81K | ~74K | **92%** | 95%+ |
| DataGolf | 80 | 76 | **95%** | ✅ |

**What shipped (May 15):**
- ✅ 3-pass probability detection: mutually-exclusive (prob sum ~1.0, max wins), independent thresholds (prob sum >1.5, each >0.50 wins), all-losers (max ≤0.10). Resolved ~75K outcomes in one call.
- ✅ Kalshi API targeted lookup via `GET /events/{ticker}` (coded, not yet run to completion — deploys keep killing it)
- ✅ Synchronous endpoint: `POST /api/admin/backfill-winners/probability-only` bypasses Celery

**Remaining (ordered):**
1. **[P1] Run Kalshi API targeted lookup to completion** — The full `backfill_winners` task includes this as Phase 2. Needs a clean 10-minute window without deploys. Will resolve the 5,860 Kalshi markets at exactly 0.500. Trigger: `POST /api/admin/backfill-winners` (Celery) or wait for scheduled run (every 6h at :45).
2. **[P2] Investigate 4,450 Polymarket all-losers** — Winning outcome not in our DB. Sample some to understand: are these decomposed sub-markets where we only have part of the event? Or markets where Polymarket added the winner after we stopped polling? Low MCE impact since they're already marked `is_winner=false`.
3. **[P2] DataGolf last 4** — 4 markets with midrange probs. Likely need settlement from DataGolf tournament results. Low priority (N=4).

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

**Current state (May 18, 2026):** MCE CI [2.86pp, 5.01pp]. 62,569 outcomes, 26,275 winners. Active trading ECE 4.5pp, opening-price ECE 7.6pp. Golf MCE 27.8pp (broken closing lines from bad commence_time). Hockey MCE 12.1pp (broken closing lines from Polymarket listing dates). Wilson CIs per bucket shipped.

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

**Subproject B: Golf calibration (MCE 27.8pp)** — FIX SHIPPED May 18
**Root cause:** Kalshi `commence_time` = market listing date, not tournament start. Part A grabbed mid-tournament prices as "closing lines." Fix: Part A now JOINs `events` table and uses `events.commence_time` (the real tournament start from DataGolf) for event-linked markets. Reset step NULLs old bad calibration prices so next backfill recomputes with correct logic.
1. **ACTION (May 19):** Verify golf MCE drops after backfill_winners runs. Check `/calibration` page.
2. Verification: `curl "https://api.bainluck.com/api/calibration/bucket-debug?secret=$ADMIN_TOKEN&source=kalshi&category=golf&bucket=5"` — calibration_probability should be pre-tournament prices, not mid-round.

**Subproject C: Hockey calibration (MCE 12.1pp)** — FIX SHIPPED May 18
**Root cause:** Polymarket `commence_time` = market listing date. Part C rescued with settlement prices (0.05% / 99.95%), not predictions. Fix: Part A now uses `events.commence_time` for event-linked NHL game markets. Part C restricted to event-linked markets only, preventing settlement price contamination. Non-NHL hockey (AHL, SHL, DEL, KHL) without `event_id` uses opening price.
1. **ACTION (May 19):** Verify hockey MCE drops after backfill_winners runs.
2. **BACKLOG: Expand calibration to non-NHL hockey.** Currently excluded because these markets lack `event_id` (no linked events in our system). To include: either create events for these leagues via a new data source, or build a mechanism to derive commence_time from the market name/ticker (e.g., parse "Jets vs. Avalanche" + date). Low priority — focus on NHL accuracy first.

**Subproject E: Non-event market closing lines** — FIX SHIPPED May 18
**Root cause:** Part C rescue grabbed settlement prices for ALL markets, including elections, economics, entertainment. A "Will Taylor Swift get pregnant?" market at 10% opening got `calibration_probability = 0.05%` (settlement) instead of 10% (the actual prediction). Fix: Part C now restricted to event-linked markets only. Non-event markets use opening price after initial trading settles (Part B). Methodology note updated on `/calibration` page.

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

**Goal:** Background queue depth stays < 50. Tasks drain faster than they accumulate.

**Monitor:** `GET /api/admin/celery-debug?secret=$ADMIN_TOKEN` → `queue_lengths.background`. Also in session startup health check.

**What happened (May 15):** Background queue backed up to 400+ tasks. Root cause: 35 tasks/hour at concurrency=2, with long-running tasks (match_prediction_markets 14.5 min, poll_kalshi 11 min) consuming both slots. Backfill tasks sat in queue for hours and never ran.

**What shipped:**
- ✅ Reduced discover_events, compute_gei_batch, merge_duplicate_events from 10-15 min to 30 min intervals (~35 → ~23 tasks/hour)
- ✅ `POST /api/admin/celery-purge-background` — emergency queue purge (365 tasks cleared)
- ✅ `GET /api/admin/celery-debug` — worker ping, active tasks, queue depths, task name distribution
- ✅ Added to session startup health check in CLAUDE.md

**If queue > 50 again:**
1. Check `celery-debug` → `active` to see what's blocking (which tasks, how long running)
2. If a single task is stuck: check its `time_start` vs time_limit. If past time_limit, the worker may be zombie — restart: `heroku ps:restart worker-background -a bainluck`
3. Purge: `POST /api/admin/celery-purge-background` (safe — all tasks are periodic and will re-fire)
4. If chronic: consider upgrading background dyno to Standard-2X ($25/mo more) for concurrency=4

**Files:** `backend/app/tasks/__init__.py` (beat schedule), `backend/app/routes/admin.py` (debug + purge endpoints)
**Parallel Safety:** Green

### ~~Production Observability — Latency, Crash Rate, Quality Indicators~~ — SHIPPED May 17

Latency tracking middleware shipped: per-request timing, p50/p95/p99 percentiles, endpoint-level breakdown, admin stats endpoint for monitoring.

**Files:** `backend/app/main.py`, `backend/app/routes/admin.py`

### ~~Manus Sweep May 6~~ — ALL 12/12 FIXED (May 7)

All issues resolved. Details in `docs/completed-features.md`.

### 0e-3. GA4 Console Configuration

Not code — configuration in the GA4 property (analytics.google.com):
1. **Custom definitions**: Register `sport`, `league`, `event_id`, `event_status`, `source_section`, `position_index`, `is_live`, `is_close_game` as custom dimensions
2. **Key events (conversions)**: Mark `sign_up`, `onboarding_complete`, `event_detail_view` as key events
3. **Audiences**: Create "Sports Enthusiasts" (3+ event_detail_view / 7d), "NBA Fans" (sport=basketball_nba 5+), "Power Users" (5+ sessions / 7d)
4. **Funnels** (Explore): Acquisition, Onboarding, Retention
5. **Dashboards**: DAU by platform, top sports by engagement time, feed CTR, onboarding completion rate

**Parallel Safety:** Green (no code changes)

### ~~0f-4e. Slow Headshot Loading (~60s)~~ — FIXED (May 8)

In-memory response cache for game-markets endpoint. Completed games cached indefinitely, live games 30s TTL. Eliminates roster queries on repeated loads.

### ~~0f-13c-native. 2nd Half Margin/Total Maps Not Showing~~ — FIXED (May 15)

Root cause: backend didn't include `period` field in game-markets response. Frontend/iOS had to guess from market names but Kalshi strips period indicators. Fix: `_extract_period_from_ticker()` derives period from Kalshi ticker prefix, added `period` field to response. Web/iOS both use `derivePeriod()` with backend-first fallback. Added missing 2H ticker entries for NHL/MLB/NCAAB/NCAAF. 27 new tests.

### ~~0f-13h. Player Award Headshots Missing on WEB~~ — ALREADY FIXED

Both `AwardCard` and `AwardCompactRow` in `RelatedFutures.tsx` already use the `PlayerHeadshot` component (lines 474, 2002). Verified May 13.

### ~~BR1-2. Source Attribution Looks Duplicated~~ — RESOLVED

The v2 rewrite (`sourcesToggle`) shows a single collapsible "Individual Sportsbooks" dropdown, collapsed by default. No duplication. Verified May 13.

### ~~0f-3. Live Box Score Integration for Player Props~~ — PARTIALLY FIXED (May 8)

Box score was already wired. Fixed the name matching: now strips Jr/Sr/III/IV suffixes before exact last-name comparison (was substring match causing false positives). Remaining: verify matching accuracy on live games with unusual names.

**Files:** `frontend/components/PlayerPropsDashboard.tsx`

### ~~0f-3d Issue 4: Series Markets~~ — SHIPPED (May 13)

Series markets now loaded as a dedicated `series_markets` array via display-time team name query (Option 2 — no linking needed). New `display_category="series"` classification. Backend, web, and iOS rendering all shipped.

**Files:** `backend/app/routes/events.py`, `frontend/components/RelatedFutures.tsx`, `ios/.../Views/EventDetailView.swift`

### ~~0f. Event Detail Below-the-Fold Redesign — TradeWatch Rethink~~ — SHIPPED May 17

TradeWatch redesigned with improved layout and data presentation.

**Files:** `frontend/app/events/[id]/page.tsx`

### 0t-2. Period Markers for Non-ESPN Events — PARTIALLY FIXED (May 11)

**Problem:** 21/45 completed events have no game state indicators (period/quarter/inning vertical lines on charts). All are non-ESPN events: soccer, tennis, KBO/NPB baseball.

**May 11 fix:** StatPal livescores now writes `raw_status` (e.g., "Q3", "1H", "HT") to `Event.period` every 30 seconds during live games. This gives period markers for all StatPal-covered sports (NBA, NHL, MLB, NFL, soccer). Previously this data was normalized to "live" and discarded.

**May 18 guardrails:** Added tests proving StatPal preserves live raw period statuses (`Q3`, `1H`, `HT`) and `_sync_statpal_livescores()` writes `fixture.raw_status` into `Event.period`. No production change needed.

**Remaining gap:** Non-ESPN, non-StatPal events (KBO/NPB baseball, some tennis) still have no period source. Soccer synthetic halftime fallback (`commence_time + 47min`) still exists as a backup for non-live games.

**Files:** `backend/app/services/statpal_api.py` (raw_status), `backend/app/tasks/statpal_sync.py` (write to Event.period)
**Parallel Safety:** Green

### ~~0t-3. Chart Domain Mismatch~~ — LIKELY FIXED

`sharedChartDomain` (computed in `events/[id]/page.tsx` lines 382-488) already passes identical `chartStartTime`, `chartEndTime`, and `sharedTicks` to both OddsChart and ScoreDifferentialChart. Game-end source filtering clips post-game prediction market drift. Needs live verification.

### ~~1b-monitor. Hockey Kalshi Link Rate~~ — FIXED (May 11)

**May 8-11 fixes:**
1. Fixed link-rate denominator — removed `event_id IS NOT NULL` clause that pulled in season futures, and reverted series tickers from game-level map. Guardrail tests added.
2. Fixed NHL team abbreviations — `tb_nhl` → "Lightning" (was mapping to NFL Buccaneers), `uta_nhl` → "Mammoth" (was "Utah Hockey").
3. Hockey Kalshi open rate was 80.5% → denominator cleaned → honest rate 74.6% → abbreviation fixes deployed → matching task re-processing.

**Files:** `backend/app/utils/sport_keys.py`, `backend/app/utils/prediction_market_matching.py`, `backend/app/routes/admin.py`

### macOS Polish (2 remaining of 7)

| # | Item | Effort | Files | Safety |
|---|------|--------|-------|--------|
| ~~MAC-1~~ | ~~Live-updating title bar~~ | ✅ SHIPPED May 8 | `Bain_LuckApp.swift` | |
| ~~MAC-3~~ | ~~Keyboard navigation~~ | ✅ SHIPPED May 8 | `FeedView.swift` | |
| ~~MAC-5~~ | ~~Menu bar extra (live scores)~~ | ✅ SHIPPED May 8 | `MenuBarView.swift` (new) | |
| ~~MAC-6~~ | ~~Push notifications~~ | ✅ SHIPPED May 17 | `Bain_LuckApp.swift` (AppDelegate, UNUserNotificationCenterDelegate) | |
| ~~MAC-8~~ | ~~Right-click context menus~~ | ✅ SHIPPED May 8 | Various SwiftUI views | |
| ~~MAC-9~~ | ~~Share button + universal links~~ | ✅ DONE — ShareLink cross-platform, MyStuffView context menus improved. | Various | |
| MAC-12 | macOS widgets (Today view) | 3-4h | New widget extension | Green |

---

## Tier 2 — Important But Bigger Scope

### 2. God Functions — Deeper Extraction

**First pass shipped:** 5 functions, 82 tests, 4 utility modules (April 21).

**Remaining targets:** `get_golf` (686L), `_match_prediction_markets` (649L), ~~`operations_dashboard` (595L)~~ (SHIPPED May 17), `_build_golf_tour_grid` (549L), `_get_march_madness_data` (406L).

**Large route files:** `admin.py` (8,684L), `events.py` (5,042L), `playoffs.py` (3,539L), `futures.py` (2,866L), `golf.py` (2,294L).

**Parallel Safety:** Yellow

### ~~3. Golf Data Quality~~ — FIXED May 18

All known golf data-quality bugs fixed. May 18 fix preserves DataGolf event-level `tour` metadata and uses it for generic tournament names such as Hainan Open before falling back to PGA Tour.

### ~~4. Site Navigation Hierarchy (B1)~~ — SHIPPED May 17

Canonical `/sport/[sport]/[league]` URL pattern shipped. Navigation uses consistent sport-aware hierarchy.

**Files:** Frontend routing, `frontend/app/sport/`

### 5. Playoff Series Matchup Markets

Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification in `tournament_stages.py`, grid column, event detail display, trend charts. Timely with NBA/NHL playoffs in progress.

**Files:** `backend/app/config/league_configs.py`, `backend/app/utils/tournament_stages.py`, `backend/app/routes/playoffs.py`, `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### 6. API Route + Guardrail Test Coverage — ONGOING

~~110~~ ~~158~~ ~~210~~ ~~218~~ 590+ integration/route contract tests and 4,450+ backend tests collected. May 17 expansion added health/sports, golf, search, calibration, market moves, futures detail/list, futures browse, category pages, related futures, feed, events, playoffs, predictions, seeded event detail, seeded feed coverage, and broad root-level guardrail suites. Seeded-data tests added (May 8):
- ✅ Feed: scoring/ordering, event data shape, futures data shape, sport filter, pagination (16 tests)
- ✅ Events: detail response shape, current_odds structure, game-markets sections, related-futures, history (17 tests)
- ✅ Playoffs: column data, probability sums, monotonicity, and overround normalization guardrails
- ✅ Related futures: market grouping, dedup, gender filtering, debug counters
- ✅ Category/futures routes: mocked non-empty contracts, envelope shape, filtering/sorting/pagination behavior
- ✅ Feed/events/playoffs routes: parameter validation, empty envelopes, mocked scored items, live-odds provider errors, playoff grid and league-futures contracts
- ✅ Predictions and seeded routes: submit validation, anonymous persistence, detailed stats/resolutions, event detail nested contracts, seeded feed pagination and nested field stability
- ✅ Game-market/related-futures grouping guardrails: period serialization, linked-market filter bypass, fallback period derivation, related-futures dedup/grouping, player metadata, and market `group_id` precedence/canonical fallback
- ✅ Matching/categorization guardrails: market label cleanup, futures category/tier classification, name normalization, roster diacritics, and same-city team ambiguity handling
- ✅ Discovery signal guardrails: anonymous/session personalization, bounded repeated unlikes, sport-key/category routing, Polymarket email ground-truth parsing, and series probability invariants
- ✅ Source matching/quality guardrails: event-registry source claim and duplicate prevention, Kalshi ticker parsing/category fallbacks, aggregate probability fallbacks, completed-game prediction-market exclusion, and feed-quality suppression/preservation rules
- ✅ Market ingestion/quota guardrails: prediction-market sport gates, unsupported-league handling, Polymarket placeholder/no-liquidity parsing, Odds API quota-sensitive parameters and partial-failure behavior, rate-limit fail-open/bucket separation, and bookmaker consensus math
- ✅ Deterministic display guardrails: feed-reason stale-copy suppression, futures highlight Yes/No humanization, baseball/live game-state labels, playoff probability normalization, and binary spread/total interpolation
- ✅ Quota/context scoring guardrails: polling tier/quota behavior, Odds API helper parsing/dedupe, league context response shape, excitement-index edge cases, and Power 4 team matching false-positive fixes for ambiguous school names
- ✅ Probability/momentum guardrails: event taxonomy feed facets, win-probability clamping and final-state overrides, line-movement threshold/order handling, pulse noisy-source resistance, and NCAA seed-matchup helper behavior
- ✅ Auth/preferences resilience guardrails: Apple Sign-In web/native audience handling, Redis quota-state fail-open/malformed cache behavior, onboarding category-interest round trips, and stale bookmaker outlier filtering
- ✅ Calibration/identity guardrails: calibration SQL/output shape, Discover LLM metadata cache fallbacks, feed independent-binary normalization shape, and team identity alias/sport-scope matching
- ✅ Provider parser guardrails: DataGolf malformed payload fallbacks, ESPN name punctuation/diacritic matching, MLB live/win-probability parsing, and ESPN boxscore stat-row resilience
- ✅ Retention/taxonomy guardrails: snapshot over-collapse prevention, scoring-play wall-clock assignment, taxonomy cache/no-LLM fallbacks, and destructive-SQL safeguards in retention collapse queries
- ✅ May 18 docs sync: verified the guardrail commits were already pushed, carried gotchas 71-75 into `CLAUDE.md`, and fixed the stale gotchas-reference range header.
- ✅ May 18 guardrails: playoff championship overround normalization, StatPal raw-period preservation, DataGolf tour metadata classification, bug-report categorization, and line-movement prompt focus.
- ✅ May 18 notification route contracts: device-token registration/upsert shape, admin list redaction, Firebase send-test payloads, invalid-token hints, and unconfigured Firebase errors.

**Files:** `tests/integration/test_route_feed_scoring.py`, `tests/integration/test_route_events_seeded.py`, `tests/integration/test_route_feed_seeded.py`, `tests/integration/test_route_predictions.py`, `tests/integration/test_route_category_pages.py`, `tests/integration/test_route_futures.py`, `tests/integration/test_route_futures_browse.py`, `tests/integration/test_route_related_futures.py`, `tests/integration/test_route_feed.py`, `tests/integration/test_route_events.py`, `tests/integration/test_route_playoffs.py`, plus focused backend guardrail tests under `backend/tests/` and `backend/app/utils/league_classification.py`
**Parallel Safety:** Green

---

## Tier 3 — Valuable But Can Wait

### Operational Health

| # | Item | What | Files | Safety |
|---|------|------|-------|--------|
| ~~9~~ | ~~**Structured Logging**~~ | ✅ DONE May 15. `python-json-logger`, production-only via `DYNO` env var. | `app/main.py`, `app/tasks/__init__.py` | |
| ~~11~~ | ~~**Hardcoded Conference Maps → Data-Driven**~~ | ✅ DONE May 17 — playoff grouping now reads conference/division labels from `Team.standings_data` with tolerant string/object parsing; large hardcoded fallback maps removed. | `routes/playoffs.py`, `tests/test_playoff_grid.py` | |

### Product Features

| # | Item | What | Depends on | Safety |
|---|------|------|-----------|--------|
| ~~12~~ | ~~**Evolution Chart: Combined Probability**~~ | ✅ DONE May 18 — optional dashed Combined line sums currently selected/visible outcomes while preserving existing per-outcome chart behavior. | | |
| ~~13~~ | ~~**Line Movement Explainer v2**~~ | ✅ DONE May 18 — largest-movement focus, before/after probabilities, nearby scoring-play ordering, and anti-filler prompt instructions. | | |
| 14 | **Freshness-Weighted Blending** | Time-decay for stale prediction market prices | More eval data | Yellow |
| 15 | **DS/Analytics Infrastructure** | Analytical columns, `v_completed_events` view, Brier scores | Migration slot | Red |
| 16 | **Golf Tournament Related Futures** | "Bigger Picture" section on tournament detail | Nothing | Yellow |
| ~~17~~ | ~~**Golf Evolution Chart Redesign**~~ | ✅ DONE — Round markers R1-R4, time range picker, tournament-aware. | | |

### ~~18. Non-Sports Category Pages~~ — ALL SHIPPED (May 7)

Economics, Politics, Entertainment all live on web + iOS. Details in `completed-features.md`.

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

### ~~P5b. Trending/Popular Searches~~ — ALREADY SHIPPED

Fully implemented: Redis `ZINCRBY` tracking on every search (24h TTL), `GET /api/search/trending` endpoint (top 5), web trending chips in SearchBar, iOS trending chips in SearchView with fallback. Verified May 13.

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

| # | Item | Description | Files | Safety |
|---|------|-------------|-------|--------|
| ~~iOS-4~~ | ~~Dead/stale views cleanup~~ | ✅ Audited May 16 — all 89 Swift files are live and referenced. No dead code found. | `ios/.../Views/` | Green |
| ~~iOS-6~~ | ~~Feed `limit=200` override~~ | ✅ VERIFIED May 17 — native Sports feed build passed with supplemental event backfill. | `FeedView.swift` | Green |
| iOS-7 | Rebuild native Futures browser before re-exposing — partial | Native Futures entry points remain hidden from production navigation. May 17 groundwork added grouped category structure, polished market rows, loading/error/empty states, and stable row sizing; still needs final product review before re-exposure. | `FuturesListView.swift`, `FuturesBrowseComponents.swift`, `MainTabView.swift`, `LeaguesView.swift` | Yellow |
| ~~iOS-GD12~~ | ~~Trevor Story missing headshot~~ | ✅ SHIPPED May 8 — generic silhouette fallback when matched_player has no URL | `RelatedFuturesView.swift` | |

---

## iOS Code Quality (multi-wave cleanup)

**Goal:** Bring the iOS codebase to a state you'd be comfortable showing a senior engineer. Audited May 17 — full report at `docs/ios-code-quality-plan.md`.

**Approach:** 6 independent waves. Each wave is a single session, touches specific files, and can ship on its own. No wave depends on another. Pick any wave when you have time.

### Wave 1: Crash Risks (30 min, do first)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-1~~ | ~~Force-unwrap URLs~~ | `EventDetailView.swift`, `FeedView.swift`, `DiscoverView.swift` | ✅ DONE May 17 — `ShareLink` URLs now fall back to `https://bainluck.com` instead of force-unwrapping. |
| ~~CQ-2~~ | ~~Unstable FeedItem.id~~ | `FeedModels.swift` line 79 | ✅ DONE May 17 — UUID fallback replaced with deterministic identity from feed fields. |
| ~~CQ-3~~ | ~~AuthManager thread safety~~ | `AuthManager.swift` | ✅ DONE May 17 — `AuthManager` is main-actor isolated. |

### Wave 2: Kill Duplication (2 hours, biggest quality win)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-4~~ | ~~Extract clipboard utility~~ | `Utilities/Clipboard.swift`, native card menus | ✅ DONE May 17 — shared `copyToClipboard(_:)` replaces duplicated string-copy pasteboard blocks. Bug-report screenshot pasteboard read remains intentional. |
| ~~CQ-5~~ | ~~Extract share URL builders~~ | `Utilities/ShareURLs.swift`, native share links | ✅ DONE May 17 — shared `eventShareURL(_:)` and `futuresShareURL(_:)` preserve Discover native-card UTM links and Feed/My Stuff plain links. |
| ~~CQ-6~~ | ~~Unify guess cards~~ | `DiscoverView.swift`, `DailyChallengeCard.swift` | ✅ DONE May 17 — `NativeGuessCard` now handles both futures and event questions through typed content initializers; duplicate `NativeEventGuessCard` removed. |
| ~~CQ-7~~ | ~~Shared context menu~~ | `Components/CardContextMenu.swift` | ✅ DONE May 17 — shared Feed/Discover context menu now owns copy probability, copy link, share, pin/unpin, macOS new-window, and Less Like This actions. |

### Wave 3: Split DiscoverView (2 hours)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-8~~ | ~~Extract DiscoverViewModel~~ | `ViewModels/DiscoverViewModel.swift` | ✅ DONE May 17 — moved the Discover state/load/personalization class out of `DiscoverView.swift`. View-local profile/debug helpers remain with the view. |
| ~~CQ-9~~ | ~~Extract discover cards~~ | `Components/DiscoverFuturesCard.swift`, `Components/DiscoverEventCard.swift` | ✅ DONE May 17 — moved `NativeFuturesDiscoverCard` and `NativeEventDiscoverCard` out of `DiscoverView.swift`. |
| ~~CQ-10~~ | ~~Extract daily challenge card~~ | `Components/DailyChallengeCard.swift` | ✅ DONE May 17 — moved `NativeDailyChallengeCard` and `NativeChallengeSheet` out of `DiscoverView.swift`. |
| ~~CQ-11~~ | ~~Extract resolution card~~ | `Components/ResolutionCard.swift` | ✅ DONE May 17 — moved `NativeResolutionCard` out of `DiscoverView.swift`. |

**Result:** DiscoverView.swift drops from 2,259 → ~300 lines.

### Wave 4: File Organization (1 hour)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-12~~ | ~~Create ViewModels/ directory~~ | All native view models | ✅ DONE May 17 — moved embedded `ObservableObject` view models out of view files into `ViewModels/`. |
| ~~CQ-13~~ | ~~Extract EventDetailViewModel~~ | ✅ DONE May 17 — added `ViewModels/EventDetailViewModel.swift`; `EventDetailView.swift` now owns view rendering only. | Public API and behavior preserved. |
| ~~CQ-14~~ | ~~Split Extensions.swift~~ | ✅ DONE May 17 — split into `Utilities/ColorExtensions.swift`, `Utilities/FormattingUtilities.swift`, `Utilities/SportDisplayNames.swift`, `Utilities/FlagUtilities.swift`, `Utilities/FlowLayout.swift` | APIs preserved; existing filesystem-synchronized Xcode project picked up new files without pbxproj edits. |

### Wave 5: Access Control + Naming (1 hour, ongoing)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-15~~ | ~~`private(set)` on ViewModel properties~~ | All ViewModel files | ✅ DONE May 17 — read-only view-model-owned published state is now `private(set)`; binding/externally-assigned fields remain mutable. |
| CQ-16 | `private` on view helpers | All View files | PARTIAL May 18 — obvious view-local environment objects, native guess-card/profile stored properties, and Futures Detail/Leagues/My Stuff view-local fields tightened; deeper helper-method sweep remains. |
| CQ-17 | Stop abbreviating | All files (search-replace) | PARTIAL May 18 — `vm` → `viewModel` completed in Economics, Weather, Friend Challenge, Futures List, Calibration, Politics, Entertainment, Preferences, Search, Futures Detail, League Grid, and Sport Category views. Additional low-risk local abbreviation cleanup landed in Menu Bar, Search, Market Map, Discover Event Card, and Related-by-Tag components. Remaining: broader `ct`, `ap`/`hp`, `gm`, and similar cleanup in small low-conflict slices. |
| ~~CQ-18~~ | ~~PinManager.isAuthenticated~~ | `PinManager.swift` | ✅ DONE May 17 — changed to `private(set)` access. |

### Wave 6: Doc Comments (1 hour, ongoing)

| # | Item | Files | What to do |
|---|------|-------|------------|
| ~~CQ-19~~ | ~~Document model types~~ | All files in `Models/` | ✅ DONE May 17 — added concise `///` comments to native model structs/enums. |
| ~~CQ-20~~ | ~~Document services~~ | `APIClient.swift`, `AuthManager.swift`, `NavigationCoordinator.swift` | ✅ DONE May 17 — added endpoint/session/navigation purpose comments to public service APIs. |
| ~~CQ-21~~ | ~~Remove dead code~~ | `EventDetailView.swift` | ✅ DONE May 17 — removed disabled tag placeholder views and now-unused tag helpers. |

- CQ-20 slice done May 17: tightened public method doc comments in `NavigationCoordinator.swift`.
- CQ-20 slice done May 17: documented `AuthManager` session responsibilities and auth entry points.
- CQ-20 slice done May 17: added endpoint-purpose doc comments to callable methods in `APIClient.swift`.
- CQ-19 slice done May 17: added concise model type doc comments in `AuthModels.swift` and `CommonTypes.swift`.
- CQ-19 slice done May 17: added concise model type doc comments in `EventModels.swift` and `FeedModels.swift`.
- CQ-14 done May 17: split `Components/Extensions.swift` into focused utility files under the existing `Utilities/` directory.

### What NOT to do

- Don't adopt TCA, MVVM-C, or any architecture framework — the app ships
- Don't add localization — single market (US)
- Don't refactor navigation — it works across iPhone/iPad/Mac
- Don't add SwiftLint yet — fix patterns manually first, lint later

**Parallel Safety:** Green (all waves are iOS-only, no backend changes)

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
| AS-11 | Launch screen check | Low | TODO | SwiftUI auto-generates one — verify it's not blank white on first launch. |
| AS-15 | Final native navigation smoke check | Medium | TODO | Before upload, verify Futures browser is hidden, Calibration is visible, 🍀 sidebar title is preserved, and market detail pages still open from Discover/search/category/weather/link flows. |

### Nice to Have (post-launch)

| # | Item | Notes |
|---|------|-------|
| AS-12 | App preview video (15-30s) | Helps conversion, not required |
| AS-13 | Promotional text (170 chars) | Updatable without new build |
| AS-14 | In-app review prompt | `SKStoreReviewController` after a few sessions |

### Already Done

- [x] App icon (1024x1024 + Mac sizes)
- [x] Bundle ID (`com.bainluck.Bain-Luck`)
- [x] Privacy manifest (`PrivacyInfo.xcprivacy`)
- [x] Privacy policy page (`bainluck.com/privacy`)
- [x] Sign in with Apple + Google
- [x] Push notification entitlement
- [x] Associated domains / universal links
- [x] TestFlight builds uploading
- [x] Web/native parity (5 features shipped May 15-16)
- [x] All Xcode warnings resolved
- [x] Native code quality sweep completed
- [x] Futures browser entry point hidden pending iOS-7
- [x] Calibration visible in native navigation
- [x] 🍀 Bain Luck sidebar branding preserved
- [x] App Store release notes and review notes drafted in `docs/app-store-launch-plan.md`

**Files:** `ios/Bain Luck/Bain Luck/Bain Luck.entitlements`, `ios/Bain Luck/Bain Luck/Views/AboutView.swift`
**Parallel Safety:** Green

---

## Discover Feed Enhancement

### Discover Feed Enhancement

| # | Item | Description | Files | Safety |
|---|------|-------------|-------|--------|
| ~~DN-9~~ | ~~Swipe to dismiss (iOS)~~ | ✅ SHIPPED May 8 — horizontal-only `SwipeToDismiss` no longer blocks vertical scroll; records local/server dismiss signals. | `ios/.../DiscoverView.swift` | |
| ~~DN-10~~ | ~~Onboarding categories → server~~ | ✅ SHIPPED May 17 — category selections now wired to `useCategoryInterests` hook, persisted server-side on completion. Previously selections were lost on onboarding finish. | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Green |
| ~~DN-11~~ | ~~Grouped market cards~~ | ✅ SHIPPED — markets with name prefix collapse into expandable cards on web/native. | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | |
| ~~D-4a~~ | ~~Click/view tracking~~ | ✅ SHIPPED May 8 — first-party `discover_interactions` table + `/api/feed/interactions` records impressions, opens, dismisses, likes, shares, and expands across web/native. | `routes/feed.py`, `app/discover/page.tsx`, `DiscoverView.swift` | |
| D-10a | Dismiss persistence | Persist dismissed IDs server-side for cross-device continuity. Local web/native dismiss persistence exists; server-side dismissal hides only via interaction scoring today, not hard exclusion. | `routes/feed.py`, `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Yellow |
| ~~D-10b~~ | ~~Like/dismiss → ranking~~ | ✅ SHIPPED May 17 — right swipe/like gives bounded "more like this" boosts; left swipe/unlike gives bounded soft downranks; backend ranking now uses category plus feature/entity/archetype affinities for signed-in and session users. | `routes/feed.py`, `utils/personalization.py`, `app/discover/page.tsx`, `DiscoverView.swift` | |
| D-6 | Push notifications for moves | Foundation shipped (May 13-17): DeviceToken model, iOS token capture, backend registration endpoint, test send endpoint. Actual production push sending not yet implemented. | New migration, `tasks/notifications.py`, FCM setup | Green |
| D-7 | Live game companion mode | NEEDS DESIGN. On iPhone, companion mode is basically just the chart full-screen (what else fits?). On iPad/Mac, the current event detail page IS already a great second screen — so what's really different? Key features: aggressive auto-refresh (10s), screen stays awake (scoped idle timer), simplified layout hiding below-the-fold. Design brief needed before building. | `app/events/[id]/companion/page.tsx` (new), `ios/.../CompanionModeView.swift` (new) | Green |
| ~~D-8~~ | ~~Daily digest email~~ | ✅ SHIPPED (May 13) — Celery beat scheduled at 8am ET. | `tasks/daily_digest.py`, email templates | |
| ~~D-9~~ | ~~Friend challenges~~ | ✅ SHIPPED May 14 — backend scaffold plus `/challenge/[id]` frontend landing page for loading, accepting, viewing participants/results, and sharing challenge links. | `routes/challenges.py`, `app/challenge/[id]/page.tsx` | |

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

Fully live on iOS/macOS. Admin page at `/admin/bug-reports`.

### ~~22. Interestingness-Powered Discovery Feed~~ — MOSTLY SHIPPED

Discover feed already has LLM blurbs (`hook_description`), Pexels images (`image_url`), probability bars, and quality scoring. Remaining: formal `interestingness_score` column + calibration against email ground truth (captured in item 20).

### 23. Prediction Market Game / Social Picks

Higher/Lower game is live in Discover. Daily challenge card shipped. Dedicated `/daily` page and basic friend challenge landing page shipped May 14. Shareable prediction scorecards shipped May 17 (OG image generation, `/discover/scorecard`). Remaining: richer head-to-head challenge creation/discovery, ambient screensaver, and portfolio mode.

**Depends on:** Auth (shipped), preferences (shipped).
**Parallel Safety:** Green

---

## Platform Parity Checklist

**iOS/Mac gaps (web has, native doesn't):**

| Priority | Feature | Web Component | Effort |
|----------|---------|--------------|--------|
| ~~Medium~~ | ~~Game Segments (quarter/half breakdown)~~ | ~~`GameSegments.tsx`~~ | ✅ SHIPPED May 18 — native event detail derives segment scoring from ESPN history snapshots for live/final games. |
| Medium | Total Points Spectrum (spread+total viz) | `TotalPointsSpectrum.tsx` | Medium |
| Medium | Series Probability (playoff series outcomes) | `SeriesProbability.tsx` | Small |
| Low | Evolution Chart (championship race over time) | `EvolutionChart.tsx` | Medium |
| ~~Low~~ | ~~Line Movement Explainer~~ | ~~`LineMovementExplainer.tsx`~~ | ✅ SHIPPED May 18 — native event detail fetches `/api/events/{id}/line-movement` and renders a compact explainer when analysis text exists. |
| ~~Low~~ | ~~Weather page~~ | ~~16 components~~ | ✅ SHIPPED May 6 + polished May 13 |
| ~~Low~~ | ~~Economics page~~ | ~~`/economics`~~ | ✅ SHIPPED May 6 + polished May 13 |
| Low | Explore / faceted browser | `/explore` | Medium |

**Web gap (iOS has, web doesn't):** ~~EI Rankings standalone page~~ — dead `eiRankings` route removed May 13. No gap.

---

## Strategic

### Expert Review / Audit — ✅ COMPLETED May 14

Four VP-level audits completed via Claude subagents. Full results in conversation history. Key findings integrated into backlog below.

### Post-Audit Priority Stack (May 14)

**P0 — Security & Reliability:**
- [x] ~~Gate 24 unprotected admin GET endpoints with `_check_admin_secret`~~ — DONE May 15. 20 GET endpoints gated.
- [ ] Split `get_db()` into read-only (no commit) and `get_db_rw()` (commits) — every GET request currently issues unnecessary COMMIT

**P0 — Product (Growth):**
- [x] **Dedicated `/daily` page** — Shipped May 14: 5 curated questions/day, progress, streak/local completion tracking, countdown timer, replay, and shareable text summary. Scorecard images shipped May 17.
- [x] ~~**Shareable prediction scorecards**~~ — SHIPPED May 17. OG image generation via Next.js `ImageResponse`, share button on `/discover/stats`, scorecard page at `/discover/scorecard`. "I got 4/5 — can you beat me?" with unique daily URL.
- [ ] **Redesign first 30 seconds** — Hero headline for first visit ("What does the world think will happen?"), first card is always a guess card (force interaction in 5 seconds), progressive disclosure toward sign-up.

**P1 — Engineering:**
- [x] ~~**Add API rate limiting**~~ — DONE May 15. ASGI middleware: 60/min anonymous, 120/min authenticated, admin exempt. Redis storage in prod, in-memory fallback for dev. Graceful degradation if Redis down. 23 tests.
- [ ] **Split `admin.py`** (11K lines, 174 handlers) — Needs robust plan before starting. Split into `admin_celery.py`, `admin_matching.py`, `admin_taxonomy.py`, `admin_engagement.py`, `admin_data_quality.py`.

**P1 — DS (Calibration Integrity):**
- [x] ~~**Confidence intervals on calibration metrics**~~ — DONE May 15. Wilson CIs, bootstrap MCE CI, error bars, CI table column.
- [ ] **Separate closing-line from opening-price cohorts** — Report closing-line-only as primary metric, blended as secondary. The `price_moved` dimension already supports this.
- [ ] **Confidence tiers on Discover cards** — Signal bars (high/medium/low) based on data-driven thresholds from trading activity analysis. Plan approved.

**P1 — Design:**
- [x] ~~**Eliminate hardcoded colors**~~ — DONE May 15. ~200 replacements across 35 files mapped to design tokens. Skipped intentional brand colors (Oscars gold, Masters green, chart/viz colors).
- [x] ~~**Decompose DiscoverCard.tsx**~~ — DONE May 15. 1,041→12 files under `components/discover/`. Main file is 91-line thin dispatcher. Public API unchanged.
- [x] ~~**Remove max-width constraint**~~ — DONE May 15. Global content 1200→1600px, sport pages 5xl→7xl, calibration 4xl→6xl, search xl→3xl. Text-heavy/admin pages left narrow.
- [x] ~~**Define formal button system**~~ — DONE May 15. `components/ui/button.tsx`: primary/ghost/text variants, sm/md/lg sizes, focus-visible ring. Applied to 10 buttons across 4 pages.

**P2 — DS:**
- [ ] **Empirically derive aggregation weights** — Retrospective Brier score analysis per source, make weights context-dependent (NFL vs K-League)
- [ ] **Stat model evaluation framework** — Validate `base_std` constants against actual data, weekly Brier comparison
- [ ] **Proactive data quality monitoring** — Calibration drift alerts, source freshness SLOs, upstream API contract tests

**P2 — Product:**
- [x] ~~**Archive dead pages**~~ — DONE May 15. Deleted `/oscars`, `/pulse`, `/ei`, `/explore`, `/masters` + orphaned OscarsModal, oscarsData, 9 API functions, 10 type interfaces. Routes 39→34.
- [ ] **Actually send push notifications** — Device token capture is built but sends nothing. One daily push: "Today's challenge is ready. Streak: 7 days."
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

### ~~BUG: Alcaraz Shows as "ATP Indian Wells" Team in Search~~ — FIXED (May 15)

Added `_INDIVIDUAL_SPORT_PREFIXES` (tennis, MMA, boxing, golf) and filtered individual-sport "teams" from search/typeahead results. Athletes still appear via event and futures results. All search tests pass.

### ~~BUG: French Open / US Open Futures Show "Player B 100%" Placeholder Names~~ — FIXED (May 15)

Polymarket creates placeholder sub-markets with "Player B/S/N" names and `outcomePrices=["1","0"]` before real candidates are announced. Three-layer fix: (1) ingestion prevention via `_is_placeholder_outcome()` in polymarket.py, (2) search display filtering in events.py, (3) `_GARBAGE_OUTCOME_RE` applied to 5 additional futures.py code paths. 9 new tests.

### ~~About Page Polish~~ — v2 SHIPPED May 16

**Status:** v2 shipped with scroll-triggered animations, dynamic API data (live market/event/source counts), refined typography, and hover effects. All 5 v2 items addressed.

**Files:** `frontend/app/about/page.tsx`
**Parallel Safety:** Green

### Run Another Manus Sweep (May 14)

Last sweep: May 11 (10 modules, 10/14 resolved). Time for a fresh sweep to catch regressions and new issues from the past 3 days of shipping.

---

## Housekeeping

### Other Housekeeping
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches

### Mystery Shopper Findings (April 22, 2026 — Manus AI Audit)

**Critical (user-facing, broken):**

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| M1 | Golf tournaments: 100%/0% probability | **Fixed** May 7 | DataGolf UniqueViolation fix |
| M2 | Event detail doesn't load on mobile | **Needs verification** | May have been transient |
| M3 | Future golf majors marked as "LIVE" | **Fixed** | DataGolf schedule fix |
| M4 | Player props showing 97-98% uninteresting thresholds | Open | Filter needed for props where interesting side <5% |

**Warning (data quality):**

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| M5 | Tiger Woods -57.5% daily change | **Fixed** | Stale trend data filtering |
| M6 | Weather: LA showing 33°F | **Fixed** | Weather staleness + C/F fix |
| M7 | Economics: recession showing "30" without % | **Likely fixed** | ProbNum component has `suffix="%"` default |
| M8 | Economics: CPI distribution sums >100% | Open | Independent binary markets as distribution |
| M9 | Weather: stale featured market | **Fixed** May 7 | 7-day staleness + 6h grace |
| M10 | "Projected final: 3 – -1" notation | **Likely fixed** | Guard: `> 0` on both scores filters negatives |
| M11 | Half/quarter/period markets not displayed | **Fixed** May 8 | RS-11: inning pattern classification |
| M12 | Halftime/spread markets missing | **Fixed** May 8 | RS-11 + half patterns in _classify_game_market |
