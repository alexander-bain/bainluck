# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + `GET /api/admin/prediction-markets/tier1-compliance`

**Current state (May 11, 2026):** Overall Kalshi open link rate: **93.9%**. Link-rate denominator fixed (removed season futures pollution). NHL `tb_nhl`/`uta_nhl` abbreviation fixes deployed. StatPal playoff parser bug fixed — all NBA/NHL playoff games now flowing from `tournament.week`. Tier 1 event coverage monitoring task added (hourly). Event merge task fixed for duplicate-with-data cases (43K backlog draining).

**Target: 100%** Tier 1 compliance — every MLB/NBA/NHL/NFL/PGA event with all sources linked.

**Audit tooling:** `scripts/audit_grid_accuracy.py` (51/51, 100%), `scripts/audit_event_matching.py`, Tier 1 compliance endpoint

---

## Tier 0 — Semantic Matching Accuracy (ACTIVE HILL-CLIMB)

### Four-Layer Matching Audit System

All 4 layers at 100% (April 24): Event Existence, Market→Event Linking, Futures Surfacing, Market Completeness. **Next:** Monitor during live games for regression.

**Files:** `backend/scripts/audit_event_matching.py`, `Manus/prompts/event_matching_ground_truth.md`

### Kalshi Outcome Alternation — Sawtooth Oscillation (HIGH PRI, ACTIVE)

**Problem:** Kalshi game-winner probability oscillates between two stable values (e.g., 40%↔60%) across every poll cycle. Visible in Rockies @ Reds (284 snapshots, 66 big jumps), Nationals @ Phillies (115 snaps, 33 jumps), Nationals @ Pirates (116 snaps, 21 jumps). Pattern is a clean sawtooth, NOT random noise — two different probabilities are being written alternately.

**Hypothesis:** Phase 2 (every 15 min) and the live poller (every 2 min) both write snapshots for the same Kalshi game market, but `find_moneyline_outcome` selects a different outcome in each path. A Kalshi game market has two outcomes ("Colorado" and "Cincinnati"). If one path picks "Colorado" (`yes_is_home=True`, writes `home_prob = colorado_prob`) and the other picks "Cincinnati" (`yes_is_home=False`, writes `home_prob = 1 - cincinnati_prob`), they'd write complementary values that don't quite match (different bid/ask, rounding).

**Investigation needed:**
1. Compare what `find_moneyline_outcome` returns for the same market in Phase 2 vs live poller — do they use the same outcome selection logic? Both call the same function, but the outcome data may differ (Phase 2 reads from `FuturesOutcome.current_probability` written by the regular poller; live poller fetches fresh from Kalshi API).
2. Check if the Kalshi game market's two outcomes ("Colorado" and "Cincinnati") have probabilities that sum to exactly 1.0. If not, the inversion (`1 - yes_prob`) produces a different value than the complementary outcome's price.
3. Add logging to snapshot writes: log the outcome_name and yes_is_home for every Kalshi snapshot so we can trace which outcome is being selected.

**Files:** `backend/app/tasks/prediction_market_matching.py` (Phase 2 ~line 800, live poller ~line 1670), `backend/app/utils/prediction_market_matching.py` (`find_moneyline_outcome` ~line 645)

### Double-Header Date Matching (HIGH PRI)

**Problem:** `extract_game_date_from_ticker` strips the time component and returns midnight UTC. For double-headers (two games between the same teams on the same day), both games' Kalshi markets parse to the same date, so the 18h threshold can't distinguish them. The HHMM portion of the ticker (e.g., `1340` vs `1910` for a 1:40 PM and 7:10 PM double-header) is available but not used.

**Fix approach:** Parse the full datetime from the ticker (including HHMM) and compare to the event's `commence_time` with a tighter window (±3h instead of ±18h). Fall back to date-only when HHMM isn't parseable.

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

**Current production state (May 13):**
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

**Next phases:**
1. Fix the iOS Xcode package-resolution blocker before TestFlight: `xcodebuild -list -project "ios/Bain Luck/Bain Luck.xcodeproj"` currently fails resolving `app-check` with "Missing or empty JSON output from manifest compilation". This blocks reliable native compile verification.
2. Automate the Polymarket email-highlight ground truth pipeline:
   - Keep the Apps Script as the Gmail parser, with a clean `Audit Export` tab using stable columns.
   - Configure production with `POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID` and `POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME=Audit Export` so backend jobs read the restricted sheet through the shared Firebase service account.
   - Add a scheduled backend/admin import path that fetches the export and persists a snapshot, so audit/admin metrics do not depend on fetching Google Sheets during the request.
   - Alert or surface an admin warning when the export is stale for more than 48 hours, row count drops sharply, or parse coverage changes unexpectedly.
3. Add persisted matching diagnostics for email-highlight rows: matched `futures_markets.id`, current Discover rank, score bucket, missing reason, category/story family, and whether the card had usable image/context/explanation treatment.
4. Use email-highlight misses as an audit signal first, not a direct ranking boost. Tune candidate pools, story mixing, explanation/media treatment, and fun-market surfacing only after reviewing false positives and duplicate-family risk.
5. Use the aggregate feedback review queue daily during TestFlight: accept only human-reviewed ranking changes at first, prioritizing high-dismiss/high-rank downrank candidates, high-open/share/context-expand low-rank promote candidates, and rage-shake reports where Discover context identifies repeated or stale cards.
6. Add account-level preference sync so web/native local tuning can merge into server-side profiles after sign-in.
7. Graduate from category-only personalization to story-family/entity personalization once engagement volume is sufficient.
8. Use engagement opportunity signals, repeat/stale launch-health signals, rage-shake context, and Polymarket email-highlight misses to tune ranking, card design, and explanation/media treatment.

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
1. **Lower staleness threshold further** — drop from 95% to 90% leader probability for sports futures. Risk: some interesting markets between 90-95% get hidden.
2. **Add an "effectively settled" heuristic** — for sports futures, if the leader has been ≥90% for >24h with no movement, treat as settled regardless of exact probability.
3. **Cross-reference game results** — when a team is eliminated (completed playoff series), mark all their "will they advance" markets as stale. Most robust but requires connecting futures markets to series outcomes.

**Recommended:** Start with option 2 (time-at-high-probability heuristic). Option 1 is too blunt. Option 3 is ideal but complex.

**Files:** `backend/app/routes/feed.py` (staleness filters ~line 2131), `backend/app/utils/feed_market_quality.py`
**Parallel Safety:** Yellow

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

### PRD Update Needed

**Problem:** `docs/PRD.md` (1,865 lines) is stale. Still describes the product as "primarily a second screen for casual sports fans" and focuses on sports. The product has evolved to be a prediction market discovery platform covering sports, politics, economics, entertainment, weather, and more. Key additions not reflected: Discover feed, Higher/Lower games, category pages, TestFlight, calibration, daily digest, friend challenges.

**Action:** Major rewrite to reflect current product vision, user flows, and feature set. Consider splitting into sections: Overview, User Journeys, Features, Architecture, Metrics.

**Files:** `docs/PRD.md`
**Parallel Safety:** Green

### Calibration Page — User-Facing `/calibration` or `/about/calibration`

**Current state (May 14):** MCE **3.8pp** (down from 5.2pp before `is_multi` fix), Brier **0.1745** (30% better than random), **151,060 outcomes** across 3 sources. 8 of 10 probability buckets within 5pp of perfect calibration. Worst buckets: 40-50% at -7.8pp, 60-70% at +7.1pp. Per-source: Odds API 2.4pp (N=15,916), Polymarket 5.2pp (N=97,104), Kalshi 5.5pp (N=38,040). Static HTML report at `calibration_report.html`. `is_winner` backfill task running every 6h. Next.js page exists at `/calibration` (19KB `page.tsx`).

**Data pipeline shipped:**
- ✅ Backend calibration endpoint (`GET /api/calibration`, public, 1h cache) with virtual market reconstruction from `group_id` + `event_id` fallback
- ✅ Odds API ground-truth integration (15,916 outcomes from completed games with scores)
- ✅ `is_winner` backfill task (`backfill_winners`, every 6h) — sets winner flag from settlement data
- ✅ Backfill status endpoint (`GET /api/admin/backfill-winners/status`) — includes `calibration_probability` coverage, `group_id` health, orphan samples
- ✅ Default-price filter for large field markets (50%+ of outcomes sharing same opening_probability)
- ✅ Static HTML report builder with SVG charts, external studies, methodology section
- ✅ Admin proxy route for browser-accessible triggers (`/api/admin-proxy`)
- ✅ `calibration_probability` backfilled to 100% coverage — uses closing line (last snapshot before event start) when available, falls back to `opening_probability`. Methodologically correct: closing line IS what the market predicted. Backfill was stuck due to poison rows (outcomes without snapshots blocked batches); fixed with LEFT JOIN + COALESCE fallback in single CTE.
- ✅ `is_multi` classification fix — markets with 3+ eligible outcomes now treated as multi-outcome regardless of group size: `(cv.is_grouped OR cv.eligible >= 3)` instead of just `cv.is_grouped`. Highest-impact single change: MCE 5.2pp → 3.8pp.
- ✅ Cache-bust parameter on calibration endpoint for fresh data without waiting for cache expiry.
- ✅ A/B test confirmed closing line prices are methodologically correct even though they give worse MCE than opening prices. Opening prices flatter the metric with placeholder noise.

**Remaining work:**

1. **Live Next.js page polish** — Page exists at `/calibration` (19KB `page.tsx`) but needs enhancement: category tabs, source comparison, external studies section, mobile-responsive layout.

2. ~~**Closing line capture**~~ — ✅ DONE. `calibration_probability` column backfilled to 100% coverage. Uses last snapshot before event start (closing line) when available, falls back to `opening_probability`.

3. **Kalshi API settlement backfill** — 58K Kalshi markets have intermediate `current_probability` (not cleanly 0/1). Kalshi API returns `result='yes'|'no'` for settled markets. First attempt failed (API paginates by recency, our DB has older events). Fix: query by specific event ticker, not paginate all settled.

4. ~~**Fix 40-50% bucket**~~ — PARTIALLY DONE. Investigation revealed orphans are legitimate single-market events (46% of resolved Polymarket markets). The real fix was changing `is_multi` classification: markets with 3+ eligible outcomes now treated as multi-outcome regardless of group size. MCE dropped from 5.2pp to 3.8pp. The 40-50% bucket improved but is still the worst at -7.8pp.

5. **Football + hockey** — Football (n=532) is too small and structurally broken. Hockey (17pp) needs investigation. Both will improve as `is_winner` backfill coverage grows.

6. **Default-price filter for S&P/Nasdaq ladders** — Kalshi economics markets have 400 outcomes all at `opening_probability = 0.500` (placeholder, no real trading). The existing `mode_prices` filter catches these for `is_multi AND eligible >= 20`, but some slip through (markets with fewer siblings or where mode_price isn't quite 50%). Tighten: flag any market where 50%+ of outcomes have identical `opening_probability` regardless of market size.

7. **Nightly refresh** — Celery task to refresh and cache calibration data.

8. **`commence_time` grouping attempt reverted** — Tried grouping ungrouped markets by `(source, category, commence_time)` but too loose: would group unrelated S&P + Nasdaq + Gold markets. The right fix is `group_id` backfill from the Polymarket Gamma API, querying resolved events to get their group structure.

**External studies:** Arrow et al. (2008, Science), Berg/Nelson/Rietz (2008), Tetlock/Gardner (2015), Wolfers/Zitzewitz (2004, JEP), Metaculus track record.

**Files:** `backend/app/routes/admin.py`, `backend/app/routes/calibration.py`, `backend/app/tasks/backfill_winners.py`, `backend/scripts/build_calibration_report_svg.py`
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

### 0f-13c-native. 2nd Half Margin/Total Maps Not Showing (NATIVE ONLY)

**Problem:** Only 1st half maps show. 2nd half maps don't appear on either platform.

**Investigation needed:**
1. Check if Kalshi poll has run since adding 2H tickers to supplementary fetch
2. Check if 2H spread/total markets exist in `futures_markets` with `event_id` set
3. Check if `_classify_game_market()` returns `half_spread`/`half_total` for them
4. Check if frontend grouping logic picks them up

**Files:** `backend/app/services/kalshi_api.py`, `backend/app/routes/events.py`, `frontend/components/MarketMapSection.tsx`, `ios/.../Components/MarketMapSection`
**Parallel Safety:** Yellow

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
| 9 | **Structured Logging** | JSON logging for Heroku (python-json-logger or structlog) | `app/main.py`, `app/tasks/__init__.py` | Yellow |
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
| D-9 | Friend challenges | Backend scaffold shipped (May 13): table, model, 3 API endpoints. Frontend UI not yet built. | `routes/challenges.py`, `app/challenge/[id]/page.tsx` (new) | Green |

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

Higher/Lower game is live in Discover. Daily challenge card shipped. Remaining: (2) Wordle-style daily picks page, (3) head-to-head challenges, (4) ambient screensaver, (5) portfolio mode.

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

### Expert Review / Audit (Dexter + Alex, May 14)

**Goal:** Get external expert eyes on the product across four dimensions before scaling.

1. **VP of Engineering audit** — code quality, architecture, scalability, deployment practices
2. **VP of DS audit** — data pipeline correctness, calibration methodology, model quality
3. **VP of Product audit** — user flows, feature prioritization, product-market fit
4. **VP of Design audit** — visual polish, information hierarchy, accessibility, mobile UX

**Action:** Identify 1-2 candidates per dimension. Share repo access + live site + this backlog. Ask for a written assessment with top 3 recommendations.

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

### BUG: Alcaraz Shows as "ATP Indian Wells" Team in Search (May 14)

**Problem:** Searching "alcaraz" returns a team card "Carlos Alcaraz — ATP INDIAN WELLS". Alcaraz is a player, not a team. The Indian Wells tournament association is leaking into the team identity. The Odds API creates "team" entries for individual tennis players, and the league/tournament context sticks as the team's league label.

**Files:** `backend/app/routes/events.py` (search endpoint), `backend/app/models/models.py` (Team), team identity pipeline
**Parallel Safety:** Yellow

### BUG: French Open / US Open Futures Show "Player B 100%" Placeholder Names (May 14)

**Problem:** "2026 Men's French Open Winner" and "2026 Men's US Open Winner" futures in search show anonymized placeholder names ("Player B", "Player S", "Player N") all at 100%. Looks completely broken.

**Root cause (likely):** Polymarket outcome names are anonymized or the name parsing failed. The 100% probabilities on all outcomes suggest a rendering or data issue — these are open markets, not resolved.

**Files:** `backend/app/tasks/polymarket.py` (outcome name parsing), `backend/app/routes/events.py` (futures in search)
**Parallel Safety:** Yellow

### About Page: Visual "Why Probability?" Storytelling (May 14)

**Problem:** The product pitch has two compelling stories that need a premium, native, visual experience on the site — not screenshots or static text.

**Story 1: "Winning big, then barely surviving"** — Alcaraz vs Zverev, 2026 Australian Open SF. Alcaraz at 96% after two sets, adductor injury, probability crashes to 13%, Zverev serves for the match, Alcaraz breaks back and wins 7-5 in the 5th. The probability chart shows the entire drama that the 3-2 scoreline hides. Kalshi market: `kxatpmatch-26jan29alczve`, $27M volume.

**Story 2: "6th place, but the favorite"** — Scheffler at 2025 Masters Round 1. T6 at -2 but 19.0% win probability — more than 2x co-leader Burns at 8.6%. McIlroy (model's #1 at 24.4%) won. Probability identified the real contenders; the leaderboard didn't.

**Approach:** Build `/about` page with two interactive panels — animated probability charts, match photos, concise captions. Reconstruct timelines from our stored Kalshi/DataGolf snapshot data.

**Dependencies:** Verify we have Kalshi snapshot data for the AO match. May need Kalshi history API backfill.

**Files:** `frontend/app/about/page.tsx` (new), new chart components
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
