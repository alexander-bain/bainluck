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

### Game-Markets Query Missing Kalshi Props (HIGH PRI)

**Problem:** The event detail page's game-markets section returns empty for many events that actually have 15-20 linked Kalshi markets (spreads, totals, overtime, half winners, player props, points leaders). These are correctly linked via `event_id` in `futures_markets` but don't appear in the API response.

**Example:** Event 14594073 (Knicks @ Hawks, Apr 23) has 18 linked Kalshi markets and 1 Polymarket market (verified via `GET /api/source-intelligence/linked-markets?event_id=14594073`), but `GET /api/events/14594073` returns `game_markets: {}` (empty).

**Interesting market types being hidden:**
- **Overtime** (`KXNBAOVERTIME-*`): "Will the game go to overtime?" — great for close games
- **Half winners** (`KXNBA1HWINNER-*`, `KXNBA2HWINNER-*`): "Who wins the 1st/2nd half?" with 3-way (home/away/tie)
- **Half spreads/totals** (`KXNBA1HSPREAD-*`, `KXNBA2HTOTAL-*`): Half-level market structure
- **Points leader** (`KXNBAPTSLEADER-*`): "Who scores the most?" — multi-outcome
- **Player props** (`KXNBAPTS-*`, `KXNBAREB-*`, `KXNBAAST-*`, `KXNBA3PT-*`, `KXNBABLK-*`, `KXNBASTL-*`): Already have these from Polymarket decomposition, but Kalshi versions may have different structure

**Where to investigate:**
- The game-markets query lives in `backend/app/routes/events.py` — search for the section that builds the `game_markets` response (around the `game-markets` or `odds-history` endpoint).
- The query likely filters by `status` (dropping resolved markets), or by `market_tier`, or by `category`, or has a time-window filter on `commence_time` that uses Kalshi's `commence_time` (which is the resolution date, not the game date — gotcha #9/19).
- These markets all have `category="game_prop"` and `market_tier=5` and `status="resolved"` — the status filter is the most likely culprit since the game is completed.
- For LIVE games, these markets should appear. Check if there's a `status.in_(["open", "active"])` filter that excludes resolved props on completed games.
- The Polymarket "Hawks vs. Knicks" market (id=12460776) has `tier=1, category="championship"` which is misclassified — it's a game market, not a championship. This is a separate classification bug in `compute_market_tier()`.

**Fix approach:** The game-markets endpoint should return ALL linked markets for an event regardless of market status (resolved markets on completed games are still valuable for viewing). Consider grouping by type (overtime, half, player props) for display.

**Files:** `backend/app/routes/events.py` (game-markets query), `backend/app/utils/prediction_market_matching.py` (market tier classification)
**Parallel Safety:** Yellow (different route from source-intelligence work)

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

### 0u. Discover Feed Quality + Personalization — ACTIVE

**Problem:** The worst Discover feed quality failures are now fixed, but the product should keep improving toward a world-class personalized prediction feed across web and native.

**Current production state (May 11):**
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

**Next phases:**
1. Automate the Polymarket email-highlight ground truth pipeline:
   - Keep the Apps Script as the Gmail parser, with a clean `Audit Export` tab using stable columns.
   - Configure production with `POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID` and `POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME=Audit Export` so backend jobs read the restricted sheet through the shared Firebase service account.
   - Add a scheduled backend/admin import path that fetches the export and persists a snapshot, so audit/admin metrics do not depend on fetching Google Sheets during the request.
   - Alert or surface an admin warning when the export is stale for more than 48 hours, row count drops sharply, or parse coverage changes unexpectedly.
2. Add persisted matching diagnostics for email-highlight rows: matched `futures_markets.id`, current Discover rank, score bucket, missing reason, category/story family, and whether the card had usable image/context/explanation treatment.
3. Use email-highlight misses as an audit signal first, not a direct ranking boost. Tune candidate pools, story mixing, explanation/media treatment, and fun-market surfacing only after reviewing false positives and duplicate-family risk.
4. Add account-level preference sync so web/native local tuning can merge into server-side profiles after sign-in.
5. Add a runtime kill switch/config cap for interaction personalization if production engagement data is noisy.
6. Graduate from category-only personalization to story-family/entity personalization once engagement volume is sufficient.
7. Use engagement opportunity signals and Polymarket email-highlight misses to tune ranking, card design, and explanation/media treatment.

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/app/utils/personalization.py`, `backend/app/utils/polymarket_email_ground_truth.py`, `backend/scripts/audit_feed_quality.py`, `frontend/app/discover/page.tsx`, `frontend/app/admin/discover-quality/page.tsx`, `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`
**Parallel Safety:** Yellow

### ~~0n. Navigation Redesign~~ — DONE (May 11-12)

Shipped across web and native. Discover is default landing page (`/`). Sports at `/sports`. Desktop: Discover | Sports | Browse (dropdown) | My Stuff. Mobile bottom nav: Discover | Sports | Search | My Stuff. Native: Discover | Sports | Browse | Search | My Stuff. Browse dropdown/tab has Politics, Entertainment, Economics, Weather. About behind user menu. Footer removed. Tab persistence deferred.

### 0s. League Pages — Phases 3 & 4 REMAINING

**Phase 1 (backend):** ✅ SHIPPED (May 6) — `GET /api/leagues/{sport_key}` returns series, awards, props grouped by market type.

**Phase 2 (frontend):** ✅ SHIPPED (May 6) — 4 new components: SeriesCard, AwardCard, PropGroupCard, LeagueMarketSection. Wired into league page below championship grid.

**Phase 3: Cross-sport generalization** — Apply same sectioned layout to NHL (series, Conn Smythe, playoff props), MLB (pennant races, awards, World Series props), NFL (division winners, MVP, draft props). Each sport gets the same sections, populated by the same league-scoped endpoint.

**Phase 4: iOS parity** — Port the new sections to `LeagueView.swift`. Reuse existing card components where possible.

**Files:** `backend/app/routes/leagues.py`, `ios/.../Views/LeagueView.swift`
**Parallel Safety:** Yellow (backend endpoint exists; frontend touches league page)

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

### BR23. Weather Cities Need Clickable Probability Graphs

**Problem:** Feature request from your son. City forecast cards show a current probability (e.g., "72% chance above 80°F") but no historical context. Users can't see how the probability has changed over time.

**Fix:** Each city forecast card should link to a detail view showing a probability timeline chart (similar to how event detail pages show win probability over time). This requires:
1. Historical data: check if `futures_odds_snapshots` has historical data for weather markets
2. A city weather detail page or modal with a time-series chart
3. Click/tap handler on the city card to navigate to the detail

**Files:** `frontend/app/weather/page.tsx`, `ios/.../Views/WeatherView.swift`, possibly new `frontend/app/weather/[market_id]/page.tsx`
**Parallel Safety:** Green

### BR-PIN. Cross-Platform Pin Sync + My Stuff Display

**Problem:** When a signed-in user pins a market or event, the pin should be persistent and visible across all platforms (web, iOS, macOS). Currently pins may be stored locally or only synced one way. Pinned items should show prominently on the My Stuff tab.

**Requirements:**
1. **Server-side persistence:** Pins stored in the `user_pins` table (already exists) must be the source of truth for signed-in users
2. **Cross-platform sync:** Pinning on web should show on iOS/macOS and vice versa. `PinManager` already has `syncLocalToServer()` — verify it runs on sign-in and that the reverse (server → local) also works
3. **My Stuff display:** Pinned events and markets should appear as a dedicated section on My Stuff (web + iOS), showing current probabilities and status
4. **Real-time feel:** After pinning, the item should appear in My Stuff immediately (optimistic update), not after a refresh

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
- ✅ Politics, Entertainment, and Weather pages polished (May 13)

**Remaining:**
- Design pass on Economics and Preferences: use the Claude Design handoffs above as the visual target

**Files:** `ios/.../Views/EconomicsView.swift`, `ios/.../Views/EntertainmentView.swift`, `ios/.../Views/WeatherView.swift`, `ios/.../Views/PoliticsView.swift`, `ios/.../Views/PreferencesView.swift`
**Parallel Safety:** Green (each page is independent)

---

## Tier 1 — High Leverage, Do Next

### Calibration Page — User-Facing `/calibration` or `/about/calibration`

**Current state (May 11, end of day):** MCE **4.8pp**, Brier **0.1745** (30% better than random), **181K outcomes** across 3 sources (Kalshi, Polymarket, Odds API). 7 of 10 probability buckets within 5pp of perfect calibration. Static HTML report at `calibration_report.html`. `is_winner` backfill task running every 6h (52K of 131K markets backfilled).

**Data pipeline shipped:**
- ✅ Backend calibration endpoint (`GET /api/admin/calibration-data`) with virtual market reconstruction from `group_id` + `event_id` fallback
- ✅ Odds API ground-truth integration (13,806 outcomes from completed games with scores)
- ✅ `is_winner` backfill task (`backfill_winners`, every 6h) — sets winner flag from settlement data
- ✅ Backfill status endpoint (`GET /api/admin/backfill-winners/status`)
- ✅ Default-price filter for large field markets (50%+ of outcomes sharing same opening_probability)
- ✅ Static HTML report builder with SVG charts, external studies, methodology section
- ✅ Admin proxy route for browser-accessible triggers (`/api/admin-proxy`)

**Per-category calibration (✓ = MCE < 8pp):**
- ✓ Weather (4.5pp), Tennis (3.6pp), Esports (3.8pp), Politics (6.4pp), Soccer (7.7pp), MMA (7.8pp), Geopolitics (6.2pp)
- ~ Golf (8.4pp, was 20pp), Basketball (8.7pp), Entertainment (9.6pp), Economics (9.3pp), Baseball (10.4pp)
- ✗ Football (25.9pp, n=532 — Polymarket sub-markets without group_id/event_id), Hockey (17.0pp), Cricket (12.0pp)

**Remaining work to make it user-facing:**

1. **Build live Next.js page** at `/calibration` — render SVG calibration curve from the endpoint. Category tabs, source comparison, external studies section. The data pipeline is done; this is frontend work.

2. **Closing line capture** — snapshot probabilities at event start time from `futures_odds_snapshots`. Currently uses first-seen price (can be weeks early). Academic gold standard for calibration.

3. **Kalshi API settlement backfill** — 79K Kalshi markets have intermediate `current_probability` (not cleanly 0/1). Kalshi API returns `result='yes'|'no'` for settled markets. First attempt failed (API paginates by recency, our DB has older events). Fix: query by specific event ticker, not paginate all settled.

4. **Fix 40-50% bucket** (MCE -14.7pp) — Polymarket sub-markets without `group_id`. Fix: backfill `group_id` via Gamma API.

5. **Football + hockey** — Football (n=532) is too small and structurally broken. Hockey (17pp) needs investigation. Both will improve as `is_winner` backfill coverage grows.

6. **Default-price filter for S&P/Nasdaq ladders** — Kalshi economics markets have 400 outcomes all at `opening_probability = 0.500` (placeholder, no real trading). The existing `mode_prices` filter catches these for `is_multi AND eligible >= 20`, but some slip through (markets with fewer siblings or where mode_price isn't quite 50%). Tighten: flag any market where 50%+ of outcomes have identical `opening_probability` regardless of market size.

7. **Nightly refresh** — Celery task to refresh and cache calibration data.

8. **`commence_time` grouping attempt reverted** — Tried grouping ungrouped markets by `(source, category, commence_time)` but too loose: would group unrelated S&P + Nasdaq + Gold markets. The right fix is `group_id` backfill from the Polymarket Gamma API, querying resolved events to get their group structure.

**External studies:** Arrow et al. (2008, Science), Berg/Nelson/Rietz (2008), Tetlock/Gardner (2015), Wolfers/Zitzewitz (2004, JEP), Metaculus track record.

**Files:** `backend/app/routes/admin.py`, `backend/app/tasks/backfill_winners.py`, `backend/scripts/build_calibration_report_svg.py`
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

### BR1-2. Source Attribution Looks Duplicated — NEEDS DESIGN (Rage Shake Bug #1 confirms)

**Problem:** The source list (sportsbooks contributing to the aggregate) appears to show twice — once as a static list and once inside a collapsible dropdown.

**Design question:** How should source attribution work? Options:
- Show just the count ("Aggregated from 12 sportsbooks") with dropdown for details
- Show the dropdown only, collapsed by default
- Inline chips for the top 3 sources + "+9 more" expander

**Files:** `ios/.../Views/EventDetailView.swift` (~line 824), `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (design brief needed)

### ~~0f-3. Live Box Score Integration for Player Props~~ — PARTIALLY FIXED (May 8)

Box score was already wired. Fixed the name matching: now strips Jr/Sr/III/IV suffixes before exact last-name comparison (was substring match causing false positives). Remaining: verify matching accuracy on live games with unusual names.

**Files:** `frontend/components/PlayerPropsDashboard.tsx`

### 0f-3d Issue 4: Series Markets Not Surfaced

**Problem:** Kalshi has rich series-level markets (Series Winner, Series Exact Score, Series Game Spread, Series Total Games) that should show on every game's event detail page during a playoff series.

**Two sub-problems:**
1. **Linking:** Series markets may not be linked to individual game events via `event_id`. The ticker team extraction had a parsing bug and series tickers (`KXMLBSERIES`, `KXNHLSERIES`, `KXNBASERIES`) need to be in `KALSHI_TICKER_TO_SPORT_KEY`.
2. **Display:** Even if linked, series markets need a dedicated "Series" section on the event detail page — separate from player props and game-level markets.

**Fix:**
- Debug ticker team extraction for series prefixes
- Add series market detection to `is_game_prop()` or create `is_series_prop()`
- Link series markets to ALL games in the series (not just one game)
- Add "Series Context" section to event detail page

**Files:** `backend/app/utils/prediction_market_matching.py`, `backend/app/tasks/prediction_market_matching.py`, `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow

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

### macOS Polish (4 remaining of 7)

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

~~110~~ ~~158~~ 210 contract tests shipped (52 added May 13). Seeded-data tests added (May 8):
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
| D-7 | Live game companion mode | Full-screen second-screen mode. Giant win prob, play-by-play, sparkline, alerts | `app/events/[id]/companion/page.tsx` (new), `ios/.../CompanionModeView.swift` (new) | Green |
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
| Low | Weather page | 16 components | Large |
| Low | Economics page | `/economics` | Medium |
| Low | Explore / faceted browser | `/explore` | Medium |

**Web gap (iOS has, web doesn't):** EI Rankings standalone page (iOS has `EIRankingsView.swift` with sport filters)

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
