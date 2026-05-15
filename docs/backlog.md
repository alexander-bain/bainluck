# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + `GET /api/admin/prediction-markets/tier1-compliance`

**Current state (May 14, 2026):** Overall Kalshi open link rate: **82.3%** (denominator now excludes unsupported leagues). Sawtooth oscillation fixed: 32 markets unlinked, 16,477 bad snapshots deleted. Date-only ticker window widened (-6h/+30h) to fix 49 tier-1 gaps from UTC/US timezone mismatch. Soccer/WNBA abbreviations added. Unsupported leagues excluded from link rate. StatPal playoff parser bug fixed. Event merge task fixed.

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

**Remaining:** Tier-1 gaps endpoint denominator should exclude markets for closed games (these are open on Kalshi for settlement but the game has ended).

**Files:** `backend/app/utils/sport_keys.py`, `backend/app/tasks/prediction_market_matching.py`

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

**Current state (May 7):** Politics page now has cross-source matching built in:
- Presidential hero merges candidates across Kalshi + Polymarket by name
- Cross-source spotlight section finds markets on both platforms (normalized question matching), ranked by disagreement
- **Remaining:** Entertainment, economics, weather pages still show duplicates. Canonical market key coverage incomplete.

**Remaining phases:** Apply same approach to entertainment/economics/weather → Audit script for coverage → Backfill NULL canonical keys.

**Target:** <10% unmatched duplicates across all category pages.

**Files:** `tasks/kalshi.py`, `tasks/polymarket.py`, `routes/politics.py` (done), `routes/entertainment.py`, `routes/economics.py`
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

4. **Run the setup script** (Claude will write `backend/scripts/setup_ga4.py`):
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

5. **Manual console steps (API doesn't support):**
   - Funnel exploration: session_start → page_view → event_detail_view → prediction_submit → sign_up
   - Retention cohort: first visit date, any return event, daily granularity
   - Dashboard: DAU by platform, top sports by engagement, Discover feed CTR, onboarding completion rate, prediction accuracy distribution

**Fallback approach: Claude Desktop computer use**
If the API setup is too much overhead, the prompt at `docs/ga4-setup-prompt.md` can drive Chrome through the GA4 console UI. Requires Claude Desktop with computer use enabled and a working Claude Code binary (update to latest version first — v1.7196.0 had a broken binary).

**Fallback approach: Manual**
Follow `docs/ga4-setup-guide.md` step by step in the GA4 console. ~15 minutes.

**Files:** `docs/ga4-setup-guide.md`, `docs/ga4-setup-prompt.md`, `backend/scripts/setup_ga4.py` (to be written)
**Pip dependency:** `google-analytics-admin>=0.22.0`
**Parallel Safety:** Green (no runtime code changes)

### 0u. Discover Feed Quality + Personalization — ACTIVE

**Problem:** The worst Discover feed quality failures are now fixed, but the product should keep improving toward a world-class personalized prediction feed across web and native.

**Current production state (May 14):**
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
- ✅ Authenticated server-side personalization now applies tiny bounded category boosts/penalties from recent Discover interactions, layered on top of favorites, pins, sport affinities, and roster-player matching.
- ✅ Authenticated feed items now expose per-card `personalization_trace` diagnostics, and `/admin/discover-quality` renders multiplier, score delta, category-affinity delta, and reasons when present.
- ✅ Polymarket email-highlight sheet can now feed the Discover audit through CSV path/URL env vars, producing `email-hit@20` / `email-hit@50` coverage without changing ranking.
- ✅ Email ground-truth parsing now accepts stable `Audit Export` headers, records row count/latest-date/stale metadata, supports private Google Sheets via service-account auth, and surfaces export errors in audit/admin diagnostics instead of crashing.
- ✅ `/admin/discover-quality` now separates Polymarket email-highlight misses into a dedicated editorial audit panel with bucket counts, sheet scores, hooks, DB trace entry points, and recommended actions.
- ✅ `/admin/discover-quality` now includes a card-level human review queue for aggregate Discover feedback, segmented by web/native and signed-in/anonymous, with promote/downrank/investigate candidates by category, archetype, and market family.
- ✅ Anonymous and signed-in Discover requests use session/user interaction history to suppress recently seen cards and longer-lived dismisses, reducing repeated cards across visits.
- ✅ Low-signal regional US election/primary markets and niche sports families are downranked and story-capped so they cannot dominate Discover just because they are liquid or timely.
- ✅ TestFlight feedback loop is instrumented: `/admin/discover-quality` shows repeat-card rate, stale-impression rate, runtime suppression config, top repeated/stale cards, and persisted review decisions. Native rage-shake reports include visible Discover cards, current card, and recent Discover interactions.
- ✅ Discover launch-health admin is now a hill-climb console: stale impression rate and repeat rate are the primary launch blockers, top stale/repeated cards link to their detail pages, review decisions are idempotent, reviewed cards leave the queue, and promote/downrank decisions apply bounded feed score nudges.
- ✅ Sports futures staleness guard tightened: Discover now treats sports futures at 90%+ leader probability as effectively resolved unless the leader had a real underdog/surprise journey.
- ✅ Deterministic futures copy polish shipped: movement is described in probability points, source-disagreement and monthly-resolution snippets name the leader when available, and stale past-resolution cards suppress generated copy.
- ✅ Dedicated `/daily` page shipped: five curated Higher/Lower calls, progress, streak/local completion tracking, countdown, replay, prediction submission, and shareable text summary.
- ✅ Friend challenge landing page shipped at `/challenge/[id]`: loads existing challenge codes, handles Higher/Lower acceptance, participants/results states, and share/copy affordances.

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
   - Add root-cause labels for stale cards: closed market still open, past resolution date, no recent odds movement, completed event still ranked, missing resolved outcome.
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
6. Add persisted matching diagnostics for email-highlight rows: matched `futures_markets.id`, current Discover rank, score bucket, missing reason, category/story family, and whether the card had usable image/context/explanation treatment.
7. Use email-highlight misses as an audit signal first, not a direct ranking boost. Tune candidate pools, story mixing, explanation/media treatment, and fun-market surfacing only after reviewing false positives and duplicate-family risk.
8. Use the aggregate feedback review queue daily during TestFlight: accept only human-reviewed ranking changes at first, prioritizing high-dismiss/high-rank downrank candidates, high-open/share/context-expand low-rank promote candidates, and rage-shake reports where Discover context identifies repeated or stale cards.
9. Add account-level preference sync so web/native local tuning can merge into server-side profiles after sign-in.
10. Graduate from category-only personalization to story-family/entity personalization once engagement volume is sufficient.
11. Use engagement opportunity signals, repeat/stale launch-health signals, rage-shake context, and Polymarket email-highlight misses to tune ranking, card design, and explanation/media treatment.

**Files:** `backend/app/routes/feed.py`, `backend/app/routes/admin.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/app/utils/personalization.py`, `backend/app/utils/polymarket_email_ground_truth.py`, `backend/scripts/audit_feed_quality.py`, `frontend/app/discover/page.tsx`, `frontend/app/admin/discover-quality/page.tsx`, `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`, `ios/Bain Luck/Bain Luck/Views/BugReportView.swift`
**Parallel Safety:** Yellow

### ~~0n. Navigation Redesign~~ — DONE (May 11-12)

Shipped across web and native. Discover is default landing page (`/`). Sports at `/sports`. Desktop: Discover | Sports | Browse (dropdown) | My Stuff. Mobile bottom nav: Discover | Sports | Search | My Stuff. Native: Discover | Sports | Browse | Search | My Stuff. Browse dropdown/tab has Politics, Entertainment, Economics, Weather. About behind user menu. Footer removed. Tab persistence deferred.

### 0s. League Pages — Phase 3 REMAINING

**Phase 1 (backend):** ✅ SHIPPED (May 6)
**Phase 2 (frontend):** ✅ SHIPPED (May 6)
**Phase 3: Cross-sport generalization** — Apply same sectioned layout to NHL, MLB, NFL. Each sport gets the same sections.
**Phase 4: iOS parity** — ✅ SHIPPED (May 13) — LeagueGridView now fetches league markets in parallel and renders Playoff Series, Awards, Props, Season Stats, and More Markets sections below the grid. Uses slug-to-sport-key mapping for all 14 leagues.

**Files:** `backend/app/routes/leagues.py`, `ios/.../Views/LeagueGridView.swift`

### 0r. Golf Data Quality Issues

**Problem:** Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible. Other 6 bugs fixed (April 17-19).

**Action:** Monitor during next Asian Tour event. If reproducible, investigate DataGolf tournament metadata parsing.

**Files:** `backend/app/tasks/datagolf.py`, `backend/app/routes/golf.py`
**Parallel Safety:** Green

---

## Manus Sweep Findings (May 11, 2026)

10-module automated audit. Results in `Manus/audit_results/2026-05-11/`. 10 of 14 resolved, 4 open.

**Resolved:** ~~MS-1~~ (false alarm), ~~MS-2~~ (false alarm), ~~MS-3~~ (prop monotonicity), ~~MS-4~~ (politics misclassification), ~~MS-5~~ (Spotify normalization), ~~MS-6~~ (economics monotonicity), ~~MS-7~~ (chart stale tails), ~~MS-9~~ (soccer halftime), ~~MS-10~~ (NCAAB settled markets), ~~MS-12~~ (golf grid monotonicity), ~~BUG-NBA~~ (not a bug), ~~BUG-DUP~~ (event merge task handles it).

### MS-8. MLB Chart Rendering Failure (WARNING)

**Problem:** Rays vs Red Sox chart has massive gaps. Possibly a data gap in win_prob_snapshots.

**Files:** `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### MS-11. Completed Market Shows Stale Live Probability (WARNING)

**Problem:** Completed MLB game shows "Yes: 52%" for a settled market — upstream data lag from Kalshi. Low priority edge case.

**Files:** `backend/app/routes/events.py`
**Parallel Safety:** Yellow

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

**Current state (May 13):** Gmail API working, daily digest scheduled at 8am ET, only sending to Alex via env var. Bug fix notifications work with opt-in checkbox on rage shake form.

**Files:** `backend/app/models/models.py`, `backend/app/tasks/daily_digest.py`, `backend/app/tasks/bug_notifications.py`, `frontend/app/preferences/page.tsx`, `ios/.../Views/PreferencesView.swift`, new `backend/app/routes/unsubscribe.py`
**Parallel Safety:** Yellow

---

## Bug Report Lifecycle: Auto-Status + "Your Bug Was Fixed" Emails

**Goal:** When a bug report is resolved, automatically notify the filer with a personal, LLM-written email explaining what was fixed and thanking them. Creates a retention loop that encourages more bug reports.

**Phases:**

### Phase 1: Backend data foundations (DO NOW)
- Add `resolution_summary` text field to `BugReport` model — when we mark a bug fixed, store a short description of what was done (e.g., "Lowered staleness threshold from 97% to 95% so resolved markets no longer appear in Discover")
- Add `backlog_ref` field — ties the bug report to a backlog item ID (e.g., "BR27") so we can batch-resolve related reports
- Look up and store the filer's email at submission time (join `users` table via `user_id`) — store as `user_email` on the report so it's available without a join later
- Update the admin PATCH endpoint to accept `resolution_summary` alongside `status`

### Phase 2: "Your bug was fixed" email (NEXT)

**Email provider decision:** Gmail API via Google Workspace. `bainluck.com` domain is on Google Workspace (set up May 12). Send as `bugs@bainluck.com` (or whichever address you create).

**Implementation steps:**
1. Create a Google Cloud service account with domain-wide delegation, grant it the `https://www.googleapis.com/auth/gmail.send` scope for `bugs@bainluck.com` (or your chosen sender). Add the service account JSON key as a Heroku config var (`GOOGLE_SERVICE_ACCOUNT_JSON`).
2. Create `backend/app/tasks/bug_notifications.py` — a Celery task `send_bug_fixed_email`
3. In the admin PATCH endpoint (`routes/admin.py`), when `status` changes to `"fixed"` and `resolution_summary` is provided:
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

### Bug Report Admin Improvements — PARTIALLY DONE (May 13)

1. ~~**Burndown chart**~~ — ✅ SHIPPED (May 13). SVG burndown chart + summary stats (open/closed/avg resolution time) on admin bug reports page.
2. **Category tagging** — tag bugs by category (UI, data quality, performance, feature request, etc.) so we can spot patterns. Add a `category` field to `BugReport` model + admin UI dropdown.
3. ~~**Resolution time tracking**~~ — ✅ SHIPPED (May 13). Included in burndown summary stats.
4. **Auto-categorization** — use GPT-4o-mini to auto-suggest a category from the bug description when a report is filed.

**Files:** `frontend/app/admin/bug-reports/page.tsx`, `backend/app/models/models.py` (BugReport), `backend/app/routes/admin.py`
**Parallel Safety:** Green

### ~~PRD Update~~ — DONE (May 15)

Rewritten from 310→249 lines. Vision, Target Users, User Journeys, Feature Map, Data Architecture, Metrics, Principles, Non-Goals. Present tense.

### Workstream: is_winner Backfill (ACTIVE — monitor every session)

**Goal:** Every resolved outcome has correct `is_winner`. Without this, the calibration curve is built on a biased subset.

**Monitor:** `GET /api/admin/backfill-winners/status?secret=$ADMIN_TOKEN` → check `sources` array + `stuck_diagnosis`.

**Current state (May 15, 2026 evening):**
| Source | Resolved | has_winner | Coverage | Target |
|--------|----------|------------|----------|--------|
| Kalshi | 69,011 | 58,728 | **85%** | 95%+ |
| Polymarket | 79,854 | 68,167 | **85%** | 95%+ |
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

**Current state (May 15, 2026 evening):** MCE CI [1.6pp, 4.3pp] (target ≤3.0pp — likely met). 45,755 outcomes, 20,673 winners. Wilson CIs per bucket shipped. Per-source: Odds API 1.3pp, Kalshi 3.5pp, Polymarket 4.3pp. Golf MCE 17.8pp (commence_time fix deployed, awaiting recompute).

**Data pipeline shipped:**
- ✅ Public calibration endpoint (`GET /api/calibration`, 1h cache) with `price_moved` dimension
- ✅ Odds API ground-truth (18,568 outcomes from completed+closed games)
- ✅ `backfill_winners` (every 6h) — is_winner, calibration_probability, null untradeable (≤2 snaps)
- ✅ `backfill_polymarket_history` (every 6h) — CLOB API price history for zero-snap outcomes
- ✅ `backfill_kalshi_history` (every 6h) — candlesticks API price history for zero-snap outcomes
- ✅ Golf commence_time fix via DataGolf schedule (reuses `_normalize_tournament()`)
- ✅ `is_multi` fix, `status IN ('completed', 'closed')`, Part C rescue, 8 diagnostic endpoints

**Subproject A: Snapshot health** — ✅ EFFECTIVELY DONE
Zero-snap: 23K → 702 (0.2%). Remaining 702 are Polymarket esports/tennis with no CLOB history. No further action unless zero-snap regresses above 1K.

**Subproject B: Golf calibration (MCE 17.8pp)** — VERIFY
The commence_time fix deployed May 14. Verification steps:
1. `curl "https://api.bainluck.com/api/calibration/outcome-timeline?market_ext_id=KXPGATOP10-MAST26"` — DeChambeau should show `calibration_probability` ~44% (pre-tournament) not 13% (in-play)
2. If still 13%: the backfill_winners task hasn't recomputed calibration_probability yet. Trigger manually: `POST /api/admin/backfill-winners` and wait for Phase 0e.
3. After recompute: check golf MCE at `/calibration`. Should drop from 17.8pp to <5pp.

**Subproject C: Hockey commence_time (MCE 11.3pp)** — NEXT UP
Same root cause as golf: Kalshi uses `close_time` (resolution date) not game time.
1. For markets WITH `event_id`: copy `commence_time` from the linked Event. One SQL update:
   ```sql
   UPDATE futures_markets fm SET commence_time = e.commence_time
   FROM events e WHERE fm.event_id = e.id AND fm.source = 'kalshi'
   AND fm.commence_time != e.commence_time AND e.commence_time IS NOT NULL;
   ```
2. For markets WITHOUT `event_id`: use `extract_game_date_from_ticker()` (already works for hockey tickers). Add to `_fix_golf_commence_times()` or create `_fix_hockey_commence_times()` in `tasks/kalshi.py`.
3. Re-run calibration price backfill to recompute `calibration_probability` with corrected commence_time.
4. Verify: hockey MCE should drop from 11.3pp. Check at `/calibration`.

**Files:** `backend/app/tasks/kalshi.py` (`_fix_golf_commence_times`), `backend/app/utils/prediction_market_matching.py` (`extract_game_date_from_ticker`)

**Subproject D: Weather/Economics commence_time (MCE 10.1pp each)** — INVESTIGATE
Different pattern from golf/hockey. These markets resolve at specific clock times (e.g., "S&P price at 4pm"). The `close_time` might actually be correct.
1. Sample 10 weather + 10 economics outcomes: compare `commence_time`, `calibration_probability`, `opening_probability`, and snapshot timeline. Use `GET /api/calibration/outcome-timeline?outcome_id=<id>`.
2. If `calibration_probability = opening_probability` on most: the problem is price-stuck (no real price discovery), not commence_time. See Subproject E.
3. If `calibration_probability` is an in-play price: commence_time is wrong. Fix depends on the pattern — weather resolves at midnight UTC, economics at market close.
4. Check the snapshot-health data: Kalshi economics has 27.6% price-stuck rate. That alone could explain the 10.1pp MCE.

**Subproject E: Price-stuck outcomes** — INVESTIGATE
19,020 outcomes (6.5% of resolved) have `calibration_probability = opening_probability`. Worst categories: Kalshi crypto (31%), Kalshi economics (27.6%), Kalshi motorsports (26.4%), Kalshi wrestling (22.8%), Kalshi entertainment (20.4%), Kalshi geopolitics (20.2%).
1. These are outcomes where the price never moved from opening — no real price discovery happened.
2. Options: (a) exclude from calibration (same logic as `_null_untradeable_openings` but for stuck, not zero-snap), (b) accept as valid data points (opening price IS a prediction), (c) separate into cohort in the calibration report.
3. Decision needed: are these degrading MCE? Compare MCE with vs without price-stuck outcomes. If MCE improves >1pp by excluding, consider filtering.
4. Check: `mce_closing_line: 7.96pp` vs `mce_opening_price: 6.94pp` from the calibration API. Closing line being WORSE suggests our closing-line identification is pulling in-play prices for some categories (hockey, golf) which are noisy.

**Remaining calibration accuracy work:**

6. ~~**Confidence intervals on calibration metrics**~~ — ✅ DONE May 15. Wilson CIs per bucket, bootstrap MCE CI (1000 resamples), error bars on chart, CI column in table.
7. **Separate closing-line vs opening-price cohorts** — VP of DS recommendation.
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

### Production Observability — Latency, Crash Rate, Quality Indicators

We measure per-request latency (X-Response-Time header, slow-request logging >500ms/>1s) but have no aggregation, dashboards, or percentile tracking. Can't answer "what's our p50/p95?" or "which endpoints are slowest?" or "what's our crash rate over time?"

**Need:** A solution that tracks latency percentiles (p50/p95/p99), error/crash rates, endpoint-level breakdown, and trends over time. Options range from free (sample + store in Redis/Postgres, build admin dashboard) to paid (Sentry Performance, Datadog, New Relic). Evaluate tradeoffs and pick one.

**Parallel Safety:** Green

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

### 0f. Event Detail Below-the-Fold Redesign — TradeWatch Rethink

**Problem:** TradeWatch is one-sided and needs layout fix. Steps 1-5 shipped April 22. Only TradeWatch rethink remains (highest-prob destination only, disclaimer added).

**Files:** `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (frontend only)

### 0t-2. Period Markers for Non-ESPN Events — PARTIALLY FIXED (May 11)

**Problem:** 21/45 completed events have no game state indicators (period/quarter/inning vertical lines on charts). All are non-ESPN events: soccer, tennis, KBO/NPB baseball.

**May 11 fix:** StatPal livescores now writes `raw_status` (e.g., "Q3", "1H", "HT") to `Event.period` every 30 seconds during live games. This gives period markers for all StatPal-covered sports (NBA, NHL, MLB, NFL, soccer). Previously this data was normalized to "live" and discarded.

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
| MAC-6 | Push notifications | 2-3h | Various | Green |
| ~~MAC-8~~ | ~~Right-click context menus~~ | ✅ SHIPPED May 8 | Various SwiftUI views | |
| ~~MAC-9~~ | ~~Share button + universal links~~ | ✅ DONE — ShareLink cross-platform, MyStuffView context menus improved. | Various | |
| MAC-12 | macOS widgets (Today view) | 3-4h | New widget extension | Green |

---

## Tier 2 — Important But Bigger Scope

### 2. God Functions — Deeper Extraction

**First pass shipped:** 5 functions, 82 tests, 4 utility modules (April 21).

**Remaining targets:** `get_golf` (686L), `_match_prediction_markets` (649L), `operations_dashboard` (595L), `_build_golf_tour_grid` (549L), `_get_march_madness_data` (406L).

**Large route files:** `admin.py` (8,684L), `events.py` (5,042L), `playoffs.py` (3,539L), `futures.py` (2,866L), `golf.py` (2,294L).

**Parallel Safety:** Yellow

### 3. Golf Data Quality

1 remaining bug: Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible. All other 6 bugs fixed (April 17-19).

### 4. Site Navigation Hierarchy (B1)

`/basketball/nba` hierarchy instead of flat `/playoffs/nba`. Blocked on golf strategy decisions.

**Parallel Safety:** Red (restructures frontend routing)

### 5. Playoff Series Matchup Markets

Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification in `tournament_stages.py`, grid column, event detail display, trend charts. Timely with NBA/NHL playoffs in progress.

**Files:** `backend/app/config/league_configs.py`, `backend/app/utils/tournament_stages.py`, `backend/app/routes/playoffs.py`, `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### 6. API Route Contract Tests — Expand Coverage (PARTIALLY DONE May 8)

~~110~~ ~~158~~ ~~210~~ ~~218~~ 335+ contract tests shipped (124 new tests added May 13: playoffs, league futures, related futures, team progression). Seeded-data tests added (May 8):
- ✅ Feed: scoring/ordering, event data shape, futures data shape, sport filter, pagination (16 tests)
- ✅ Events: detail response shape, current_odds structure, game-markets sections, related-futures, history (17 tests)
- Playoffs: column data, probability sums, monotonicity
- Related futures: market grouping, dedup, gender filtering

**Files:** `tests/integration/test_route_feed_scoring.py` (new), `tests/integration/test_route_events_seeded.py` (new)
**Parallel Safety:** Green

---

## Tier 3 — Valuable But Can Wait

### Operational Health

| # | Item | What | Files | Safety |
|---|------|------|-------|--------|
| ~~9~~ | ~~**Structured Logging**~~ | ✅ DONE May 15. `python-json-logger`, production-only via `DYNO` env var. | `app/main.py`, `app/tasks/__init__.py` | |
| 11 | **Hardcoded Conference Maps → Data-Driven** | Pull from `Team.standings_data` instead of static dicts | `routes/playoffs.py` | Yellow |

### Product Features

| # | Item | What | Depends on | Safety |
|---|------|------|-----------|--------|
| 12 | **Evolution Chart: Combined Probability** | Multi-source merged trend line on charts | Nothing | Yellow |
| 13 | **Line Movement Explainer v2** | Causal analysis, key moment identification | Nothing | Green |
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

### P4c. Weighted `ts_vector` Full-Text Search

Team names weight A, market names weight B, outcome names weight C. Use PostgreSQL full-text search with weighted ranking.

**Files:** `backend/app/routes/events.py`, new migration for ts_vector columns
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
| iOS-4 | Dead/stale views cleanup | TournamentChartView/CardView — audit for staleness | `ios/.../Views/` | Green |
| iOS-6 | Feed `limit=200` override | Fixed April 22, needs build verification | `FeedView.swift` | Green |
| ~~iOS-GD12~~ | ~~Trevor Story missing headshot~~ | ✅ SHIPPED May 8 — generic silhouette fallback when matched_player has no URL | `RelatedFuturesView.swift` | |

---

## Discover Feed Enhancement

### Discover Feed Enhancement

| # | Item | Description | Files | Safety |
|---|------|-------------|-------|--------|
| ~~DN-9~~ | ~~Swipe to dismiss (iOS)~~ | ✅ SHIPPED May 8 — horizontal-only `SwipeToDismiss` no longer blocks vertical scroll; records local/server dismiss signals. | `ios/.../DiscoverView.swift` | |
| DN-10 | Onboarding flow | "Build Your Feed" modal with category selection on first launch. Web has modal; native has first-launch onboarding. Remaining: make category selection affect server profile directly. | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Green |
| ~~DN-11~~ | ~~Grouped market cards~~ | ✅ SHIPPED — markets with name prefix collapse into expandable cards on web/native. | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | |
| ~~D-4a~~ | ~~Click/view tracking~~ | ✅ SHIPPED May 8 — first-party `discover_interactions` table + `/api/feed/interactions` records impressions, opens, dismisses, likes, shares, and expands across web/native. | `routes/feed.py`, `app/discover/page.tsx`, `DiscoverView.swift` | |
| D-10a | Dismiss persistence | Persist dismissed IDs server-side for cross-device continuity. Local web/native dismiss persistence exists; server-side dismissal hides only via interaction scoring today, not hard exclusion. | `routes/feed.py`, `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Yellow |
| ~~D-10b~~ | ~~Like/dismiss → ranking~~ | ✅ PARTIALLY SHIPPED May 8 — interaction-derived category boosts/penalties affect authenticated backend ranking with tight caps; local web/native tuning remains anonymous fallback. Remaining entity/story-family scoring is tracked in 0u. | `routes/feed.py`, `utils/personalization.py` | |
| D-6 | Push notifications for moves | Foundation shipped (May 13): iOS token capture + backend endpoint. Actual push sending not yet implemented. | New migration, `tasks/notifications.py`, FCM setup | Green |
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

**Phases:** (1) Ground truth collection (Gmail → Apps Script → Sheet, 50-100 labeled markets), (2) Scoring formula (8 weighted features: decisiveness, multi-source, recency, movement, resolution proximity, category novelty, volume, LLM quality), (3) Calibration (hill-climb weights, Precision@20/Recall@50/NDCG), (4) Integration (explore page, feed ranking, trending, push, featured hero).

**Files:** `utils/market_interestingness.py` (new), `scripts/calibrate_interestingness.py` (new), Google Sheet
**Parallel Safety:** Green

### ~~21. Rage Shake~~ — SHIPPED

Fully live on iOS/macOS. Admin page at `/admin/bug-reports`.

### ~~22. Interestingness-Powered Discovery Feed~~ — MOSTLY SHIPPED

Discover feed already has LLM blurbs (`hook_description`), Pexels images (`image_url`), probability bars, and quality scoring. Remaining: formal `interestingness_score` column + calibration against email ground truth (captured in item 20).

### 23. Prediction Market Game / Social Picks

Higher/Lower game is live in Discover. Daily challenge card shipped. Dedicated `/daily` page and basic friend challenge landing page shipped May 14. Remaining: generated image scorecards, richer head-to-head challenge creation/discovery, ambient screensaver, and portfolio mode.

**Depends on:** Auth (shipped), preferences (shipped).
**Parallel Safety:** Green

---

## Platform Parity Checklist

**iOS/Mac gaps (web has, native doesn't):**

| Priority | Feature | Web Component | Effort |
|----------|---------|--------------|--------|
| Medium | Game Segments (quarter/half breakdown) | `GameSegments.tsx` | Small |
| Medium | Total Points Spectrum (spread+total viz) | `TotalPointsSpectrum.tsx` | Medium |
| Medium | Series Probability (playoff series outcomes) | `SeriesProbability.tsx` | Small |
| Low | Evolution Chart (championship race over time) | `EvolutionChart.tsx` | Medium |
| Low | Line Movement Explainer | `LineMovementExplainer.tsx` | Small |
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
- [x] **Dedicated `/daily` page** — Shipped May 14: 5 curated questions/day, progress, streak/local completion tracking, countdown timer, replay, and shareable text summary. Remaining scorecard-image work stays below.
- [ ] **Shareable prediction scorecards** — After completing daily challenge, generate image card: "I got 4/5 — can you beat me?" with unique daily URL. Text summary shipped May 14; image card remains.
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

### About Page Polish — v1 Shipped, Needs Professional Treatment (May 15)

**Status:** v1 shipped with two stories (Alcaraz AO SF, Scheffler Masters), SVG probability chart, comparison table, CTA. Functional but reads more like a blog post than a premium product page.

**Remaining for v2:**
1. **Story 2 visual upgrade** — Replace the golf table with a horizontal bar chart or visual that creates the same "aha" as Story 1's probability arc. Currently it's just a data table.
2. **Scroll-triggered animations** — Stories should fade/slide in as user scrolls. Use `IntersectionObserver` or `framer-motion`. Current version is fully static.
3. **Real data from our snapshots** — Story 1 uses hardcoded data points. Pull actual Kalshi snapshot data for the Alcaraz match (`kxatpmatch-26jan29alczve`) to make the chart authentic.
4. **Photos/imagery** — Match photos or player silhouettes would elevate the editorial feel. Check Pexels or licensed sources.
5. **Mobile typography** — Verify the hero headline and story cards look right on iPhone SE (375pt width).

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
