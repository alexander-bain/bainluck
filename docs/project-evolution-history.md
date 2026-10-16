# Bain Luck — A Detailed Evolution History

*A chronological narrative of the project, from founding to May 13, 2026, written as source material for a 15-minute NotebookLM podcast. The story is reconstructed from the codebase's documentation: `PRD.md`, `completed-features.md`, `gotchas-reference.md`, `audit-and-strategy-march-2026.md`, `championship-grids-project.md`, the Alembic migration log, and inline references in `CLAUDE.md`. The current git history in this repository only goes back to May 13, 2026 (50 commits, all on one day), so the earlier eras are reconstructed from the rich documentation those commits sit on top of.*

---

## Part 1 — The Founding Idea

Bain Luck began with a single, almost stubborn product belief: most people will never learn what "-150" or "+130" means, and they shouldn't have to. The American odds format, the decimal odds format, the Kalshi cents-per-share CLOB price, the Polymarket midpoint — they are all just different ways of saying the same thing, which is "this is what the world thinks the probability is." So why not just show people the probability?

That is the founding north star of the project, and it has never moved. The PRD writes it in capital letters: **"The most engaging way to explore what the world thinks will happen."** The 10-second success moment is described as a user opening the app and immediately thinking, "Oh, I had no idea — that's only 23% likely?" It applies equally to a championship game, a presidential election, a Federal Reserve rate decision, and a movie's Rotten Tomatoes score.

The product is explicit about what it is *not*: it is not a sportsbook, not a pick-selling tout, not a fantasy analytics tool, not a heavy statistical platform, not a trading interface for prediction markets. The non-goals are kept short on purpose because the founder treated them as a fence around the product's clarity. The target user, as stated in the PRD, is "casual fans who want probability-first context — not betting advice." Power users are explicitly deprioritized. They may still find value, but the product will not optimize for them.

The first surface was simple: a sports feed showing live and upcoming games with probabilities and a single chart of how those probabilities had moved. That single page is the thing everything else grew out of.

---

## Part 2 — The MVP and the First Year of Plumbing (Phases 1–3)

Phase 1 of the PRD is labeled "MVP: Core visualization shipped to production." The bullets are quietly dramatic when you read them: project setup and CI/CD, database schema, integration with The Odds API, live win probability percentages, a mobile-optimized web UI, auto-refresh, an odds-movement chart with time range filters, per-bookmaker breakdowns rendered as gray lines on the same chart, sport and league filtering, and sorting by closeness and game time. From the first week the chart was the centerpiece — and it remains the centerpiece today.

Phase 2 was analytics and observability — Google Analytics 4 with the Measurement Protocol, a cross-platform User-ID model planned in advance for an iOS app that did not yet exist, GDPR-compliant Consent Mode v2, scroll-depth tracking, time-on-page, and chart interaction analytics. Even at this early stage the founder was instrumenting everything, because the bet was that personalization and ranking would eventually become the product's moat.

Phase 3 was reliability and data quality. This is where the project's most enduring scar tissue formed. The team added Sentry error tracking on both the FastAPI backend and the Celery workers. It built a dedicated event-discovery task that polls *all* sports rather than only the sports it already knows about. It added stale-data detection that auto-closes events stuck in "scheduled" forever. And it tackled what would become a defining problem: snapshot retention.

The retention story is worth lingering on, because it shows the project's pattern of fixing things twice. The first version did "lossless collapsing" — if three consecutive odds snapshots had identical values, only the first was kept and the rest were deleted. That worked, but it was implemented in Python and it pulled every row of the snapshot tables into memory on every Heroku worker run. The dyno OOM-killed itself with R14 errors. So they rewrote the retention task in pure SQL using PostgreSQL window functions — `LAG`, `SUM`, common table expressions — so the whole collapse runs in constant memory. Zero rows pulled into Python. It has never crashed since. This same pattern — "first build it the obvious way, then realize the obvious way doesn't survive production, then rewrite it as a SQL CTE" — shows up over and over in the codebase.

Around this same period the team did the first big refactor: the monolithic `tasks.py` file was 2,970 lines long, and it was broken up into a `tasks/` package with about fifteen modules. Crucially, every Celery task was pinned with an explicit `name=` parameter so that the rename didn't silently stop the beat schedule from running it. This nearly-invisible decision saved the project from a future outage. The team also extracted stale-bookmaker filtering into its own utility module with regression tests, and added a Celery heartbeat plus a `/health` endpoint.

There's an unsung casualty from this era: the original product included a Super Bowl one-off — a contest engine, a YouTube-API-driven commercial leaderboard, a TV mode, and a bunch of other party-mode code. After the Super Bowl shipped, all ~7,000 lines of it were ripped out. That Super Bowl-shaped hole in the codebase explains a lot of the comments that show up later about "removed in cleanup."

---

## Part 3 — Pulse Becomes the Excitement Index

The next major chapter was a proprietary game-excitement metric. The original version was called **Pulse**. It was a weighted composite of "heart rate," "amplitude," "arrhythmia," "vitals," "time weight," and "lead changes." It shipped in February 2026 with its own page at `/pulse`, a `PulseBadge` component on every game card, real-time updates on every poll cycle, batch recalculation for completed games every ten minutes, percentile scoring tuned against the historical distribution, and a Hall of Fame at `/pulse/hall-of-fame` for the top 25 highest- and lowest-Pulse games of all time.

Then the team made a conscious choice to abandon the bespoke metric and migrate to the standard formula used in academic papers — the GEI, or Game Excitement Index: `EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|`. In other words: scale the total absolute change in win probability by how much overtime was played. The migration was full-stack. The Alembic migration renamed `raw_gei` to `raw_ei`, `gei_components` to `ei_metadata`, `gei_percentiles` to `ei_percentiles`. The frontend `PulseBadge.tsx` became `EIBadge.tsx`. Routes became `/ei` and `/ei/hall-of-fame`, with `/pulse` redirecting for backward compatibility. The API kept serving both `"ei"` and `"pulse"` keys for a while so nothing broke. There are 80+ tests in `test_excitement_index.py`. The scaling constant was tuned three times — 8.0 down to 4.0 down to 2.5 — because the percentile distribution kept skewing wrong, and the time-normalization ratio was eventually capped at 2.0x to prevent triple-overtime games from saturating the chart.

This pulse-to-EI migration is the project's first really self-conscious moment. It's the moment the founder stopped trying to invent a proprietary metric and started trusting the literature.

---

## Part 4 — Pinned Items, Auth, and the First Personalization Layer

Also in February 2026, the team shipped pinned events and pinned futures. Six pins of each, stored in `localStorage` for anonymous users so that pinning didn't require creating an account. Pinned items appeared in their own section above the highlights. Cross-tab sync via the storage event. Search results were pinnable. The Super Bowl, sitting weeks in the future and outside the normal seven-day window, was deliberately reachable through the pin system.

Authentication came next. Phase 6.1 was Firebase Auth with Google Sign-In, but the team immediately ran into Safari's Intelligent Tracking Prevention, which broke Firebase's `signInWithPopup` flow. The fix was a 3-tier fallback that is still one of the most distinctive pieces of architecture in the codebase:

- **Tier 1 (Chrome/Firefox):** Google Identity Services `initTokenClient` opens an OAuth popup with a 4-second timeout, then calls Firebase `signInWithCredential` with another 4-second timeout.
- **Tier 2 (Safari ITP fallback):** If Tier 1 fails, the access token is sent to `POST /api/auth/google-access-token`. The backend verifies it with Google's OAuth token endpoint, creates a Firebase custom token via the Admin SDK, and the frontend calls `signInWithCustomToken`.
- **Tier 3 (Last resort):** If both fail, the backend returns a PyJWT session token that the frontend stores in localStorage and sends as an Authorization header on every subsequent request.

Auth persistence was switched from IndexedDB (browser-controlled) to localStorage (app-controlled) because IndexedDB was being purged unpredictably. This same backend-session-token pattern would later be reused on iOS — the SDK does the OAuth dance natively, the raw credential is sent to the backend, the backend issues a 30-day PyJWT, iOS stores it in the Keychain.

Phase 6.2 was the 5-step onboarding flow: pick your location, follow your teams, select your alma maters, choose 20 sport and non-sport interests, and name your rivals. Metro alias expansion meant typing "New England" auto-followed the Celtics, Patriots, Bruins, and Red Sox. The team-search fallback hit the events table for college teams that didn't exist in the `teams` table yet, and auto-created them. The settings editor moved to `/preferences`. `/my-stuff` became a team-filtered feed, with a `my_teams_only` parameter on the feed API.

Phase 6.3 was personalization in the ranking. Local teams got a 3.5x multiplier, alma maters 2.5x, followed teams 2.0x. Rivalry multipliers boosted live games where a rival was losing or had blown a lead. Sport affinity weighted the whole feed. Personalization badges started appearing on cards: "Your team," "Local," "Alma mater," "Rival losing." Non-sports categories — politics, entertainment, crypto, economics, tech, weather, geopolitics, culture — were promoted from tier 3 to tier 2 in the categorization weights.

---

## Part 5 — Phases 7 and 8: LLMs and ESPN

Phase 7 was the OpenAI integration. GPT-4o-mini was wired into `services/llm.py` with a generic `classify()` utility. Futures categorization became hybrid: 90+ regex patterns first, LLM fallback when nothing matched. Twenty-three sport categories. Zero uncategorized markets. LLM results were cached in the database in the `llm_sport_category` column to avoid re-billing. The team also added LLM-driven enrichment of gender, level, league, and importance metadata.

Phase 8 was ESPN. ESPN's API is technically undocumented, but the team built a client that pulled team colors, logos, alternate names, win probabilities, venue data, and live game state every sixty seconds. ESPN team-name matching had to handle unicode and accents for college teams — "Montréal" had to match "Montreal," and "Hawai'i" had to match "Hawaii." Mapped sports were NBA, NCAAB, WNCAAB, NFL, NCAAF, NHL, MLB, MLS, EPL. Team logos and team-colored probability bars started appearing on every event card. ESPN also became an authoritative time source — the `_discover_events()` task cross-references the ESPN schedule at discovery time to correct Odds API time errors before they enter the database.

By the end of Phase 8, the product had something that looked more like a real platform: live odds, multi-source visualization, team identity, personalization, auth, pinned items, an excitement metric, and the first piece of LLM intelligence. But the ranking algorithm was still snapshot-based — it scored what was happening *right now* and didn't understand momentum.

---

## Part 6 — The Ranking Levels and the Time-Series Awakening

The team thinks about ranking in three levels:
- **Level 1: Snapshot scoring.** What's happening right now? Live, close, near-tipoff, close to start time?
- **Level 2: Time-series aware scoring.** How volatile has this game been? How many lead changes? Has the line moved hard in the last ten minutes?
- **Level 3: Sport-specific and contextual scoring.** Is this a championship? Is the rival losing?

Level 2 shipped in late February. A new utility, `compute_time_series_metrics()`, read from `odds_snapshots` and computed RMS volatility, count of lead changes, and recent momentum — all in a batch SQL query for live events so the feed wasn't doing N+1 queries. New labels appeared on cards: "Lead change," "Odds shifting fast," "Wild game." Twenty-one new tests. This was the first time the feed felt *editorial* — it was telling users not just what was happening but what was *interesting* about it.

Around this time the project also began consolidating its win-probability sources behind a generic interface. A new table, `win_prob_snapshots`, replaced the older sport-specific snapshot tables. A `win_prob_sources` config module declared the source weights. The N-source chart was born — one line per source on the same chart, color-coded, with a per-bookmaker dropdown for the underlying spread.

The Bain Luck statistical model also shipped — an in-house win-probability model inspired by the open-source `nflfastR` package, supporting NFL, NCAAF, NBA, NCAAB, WNCAAB, and NHL. The model has its own page at `/events/[id]/models` explaining the methodology and attributing the inspiration. MLB Stats API was wired in to provide live baseball win probability with no API key required — initially registered under the source key `"fangraphs"` and later renamed to `"mlb"` (display name "MLB Model") in a coordinated backend-frontend-iOS migration with an Alembic step.

---

## Part 7 — Prediction Markets Arrive: Kalshi and Polymarket

The product's biggest expansion of identity came when prediction markets joined sportsbooks as first-class data sources. Kalshi shipped first, with an API client, a polling task, and the matching infrastructure that would consume more engineering attention than any other subsystem.

The matching problem is conceptually simple but operationally brutal: Kalshi has a market called "KXNBAGAME-26FEB21DETCHI" and the Bain Luck database has an event called "Detroit Pistons vs. Chicago Bulls" — they need to be linked. The linker has to handle:

- Kalshi's `commence_time` is the *resolution* date, not the game date (gotcha #9, source of countless time-window bugs).
- Kalshi creates separate "Team A win?" and "Team B win?" binary markets for the same game; both get linked to the same event and write competing snapshots that oscillate between 50% and 100% (gotcha #24).
- Kalshi's market names use abbreviations that fail SQL `ILIKE` matching: "A's" doesn't match "Athletics," "Chicago WS" doesn't match "Chicago White Sox" (gotcha #29).
- Some Kalshi markets are mislabeled in their `category` field — division-winner futures get tagged `"game_prop"` (gotcha #16).
- Sub-market threshold outcomes like "Aaron Judge: 1+ HRs" are *over* probabilities and should not be inverted (gotcha #18).

The first matching pass was a simple ticker scan. Then a second pass for general name matching. Then a "Phase 1.5" re-validation step that scrubbed stale links. Then a "Phase 2" that wrote snapshots. Phase 2 deadlocked with the live polling task and had to be rewritten with per-market commits and rollback-on-deadlock-detection (gotcha #11). The matching frequency was tightened from every 4 hours to every 1 hour, and the per-cycle limit was raised from 200 to 500. The team built `extract_teams_from_ticker()` to parse generic Kalshi ticker formats, and added 100+ team abbreviations across NBA, NFL, NHL, and MLB. The `_score_candidates()` function added a sport-validation hard rejection so KXNBA tickers couldn't link to baseball events just because of city-name collisions like "Boston" and "New York."

Polymarket was added next. Polymarket has a different data model — events contain dozens of nested sub-markets, each with its own `condition_id`. A "Magic vs. Pistons" event might contain forty sub-markets covering moneyline, spread, three different over/unders, and player props. The polling task had to *decompose* each event into separate `FuturesMarket` rows, one per sub-market, with the `event_id` propagated down. NegRisk markets — the multi-outcome championship-style markets — are different again: each sub-market is a candidate, and they share a `group_id` that the calibration pipeline would later use to reconstruct the virtual aggregate market.

The team also discovered that Polymarket's midpoint price is unreliable during blowouts. When the bid/ask spread is greater than 15 percentage points, the midpoint can sit at 38% while the sportsbook consensus is at 6%. The fix: use `lastTradePrice` instead, and skip outcomes entirely when there's no `lastTradePrice` and no bids (gotcha #20). This was a real divergence-badge bug — a 94-120 blowout was triggering a "Polymarket disagrees" warning that wasn't really disagreement, it was just stale liquidity.

By the end of this period, the link rate dashboard was tracking per-sport performance with painful honesty. Kalshi tennis went from 52% linked to 96%. Hockey from 27% to 52%. Baseball from 69% to 77%. The team published the metric publicly at `/api/admin/prediction-markets/link-rate` so anyone could see how the matching was holding up.

---

## Part 8 — The First iOS App

In March 2026 the iOS app shipped — a native SwiftUI codebase shared between iOS and macOS. The first version covered seven phases in 29 commits and 46 Swift files: a section-based feed, a multi-source odds chart with period markers (the same `Charts` framework used on web, but reimplemented natively), an event detail page with chart, related futures, line movement, and scoring plays, search, the EI rankings page, Apple and Google Sign-In, native onboarding, preferences, an iPad-native sidebar layout, category pages, filter chips, swipe-to-pin, haptic feedback, Firebase Analytics, and deep linking.

The iOS code has its own set of hard-won patterns. Models are `Decodable`, not `Codable`, and they're declared `nonisolated struct` so they can cross actor boundaries safely (gotcha #12). ViewModels never put `@MainActor` on the class — only on the individual async methods that touch UI state, because class-level `@MainActor` causes spurious recompiles on every property read (gotcha #13). The auth flow uses the same backend-issued PyJWT session token that web Tier 3 uses; iOS calls `POST /api/auth/apple` or `POST /api/auth/google-access-token`, the backend verifies with the identity provider, creates a Firebase user if needed, and returns a 30-day session token for the Keychain. Apple credential revocation is checked on every foreground.

iPad Stage Manager broke `UIApplication.shared.connectedScenes.first` because it could return a background scene. The fix was a careful filter chain that prefers foreground-active windows and the actual key window (gotcha #33). The Safari authentication fallback even has an iOS analog — if the silent Google restore fails on token expiry, the app falls through to the popup flow.

The codebase grew quickly. By May it would be 89 Swift files and would have full TestFlight distribution.

---

## Part 9 — Calibration, Tournament Charts, and Series Probability

A new shape of feature appeared in this era: features that were *honest about accuracy*. The team built a probability-timeline endpoint at `GET /api/futures/{market_id}/probability-timeline` that returns time-bucketed probability history. The new `TournamentChart.tsx` component rendered a tournament-shaped SVG with Top 5 / Top 10 / All toggles, a "Field" area fill, a position-based 10-color palette, and an interactive crosshair tooltip.

A `compute_series_win_prob()` utility was added to `utils/series_probability.py`. It uses a negative binomial distribution to model best-of-N series — given a per-game win probability and a current series score, what's the probability of winning the series? This shipped with 37 tests and an API endpoint, and would later become the basis for the dedicated "series_markets" array on event detail pages.

Behind the scenes the team also added market grouping — a `canonical_market_key` set during Kalshi and Polymarket polling so the frontend could detect threshold variants ("Movie X RT score ≥ 50, ≥ 60, ≥ 70") and render them as a single grouped card. Three new frontend components — `CombinedMarketCard`, `ProgressionTable`, `ThresholdGrid` — and an admin endpoint and an API endpoint and 315 tests.

This is also when the **calibration pipeline** had its first foundations laid, although the public report wouldn't ship until May. The idea was simple but expensive: take every resolved market, look at what its opening probability said, and check whether the actual outcome happened in line with the prediction. If markets that opened at 30% won about 30% of the time, the markets are well-calibrated; if they win 50% of the time, the market is biased. This metric — the Mean Calibration Error (MCE) and Brier score — would become the public face of the product's trustworthiness story.

---

## Part 10 — March 2026 Audit: The Strategic Pivot

In early March 2026, the project did something unusual: the founder commissioned a written code audit of his own work. The audit lives at `docs/audit-and-strategy-march-2026.md`, and it's an extraordinary document because it's so honest about what was wrong.

It opened with a list of critical issues: silent error swallowing because tasks were using `print()` instead of `logger.error()`; a 5,493-line `admin.py` file that contained every admin feature ever built; a Celery beat schedule using magic strings that could silently stop running tasks if a name changed. It listed architectural debt: an `Event` model with 159 columns, copy-pasted polling loops across four files, win probability snapshots being created via four different code paths, a dead `OddsAggregated` table that had been "Phase 2 someday" since January.

It diagnosed the frontend with the same honesty: `OddsChart.tsx` was 1,472 lines with nine cascading `useMemo` blocks; `RelatedFutures.tsx` was 1,513 lines with seven regex pattern arrays and fifteen helper functions; the CSS system had three sources of truth — `globals.css`, `design-tokens.css`, and `tailwind.config.ts` — and nobody knew which file to edit.

The strategy section pivoted hard. The honest diagnosis was that the founder had been "trying to improve design through code refactoring (CSS variables, design tokens, shadcn Card wrappers). That's plumbing, not design. No user will ever notice that `<div>` became `<Card>`." The recommendation was to start using v0.dev for component generation, study The Athletic, FiveThirtyEight, Smarkets, Action Network, and Linear as references, and make five concrete moves: kill the borders on cards, make probability numbers two to three times larger, let team colors bleed as gradient tints rather than badges, pick four typography sizes and use them consistently, and use v0.dev to redesign the EventCard.

This audit was the project's strategic inflection point. Almost every visual decision from March onward — the bigger probability numbers, the team-color gradients, the kind-classified cards on category pages, the editorial trending heroes — traces back to this document.

---

## Part 11 — Related Futures, Bigger Picture, and the Championship Grids

A major workstream in this era was answering the question "what do I get when I open an event detail page?" The original answer was just the chart. The new answer became the **Bigger Picture** section — a tier-grouped layout that surfaces every championship, conference, division, award, and stat-prop market related to the two teams playing.

Phases 1 through 3 of the related-futures work added the team-linking infrastructure: a `FuturesOutcome.team_id` foreign key, a `FuturesMarket.market_tier` column, a backfill task. The endpoint `GET /api/events/{id}/related-futures` shipped with hybrid matching — name `ILIKE` plus `team_id`, with a triple sport filter to prevent cross-sport contamination. The frontend added a "Bigger Picture" section with team colors, logos, and probability bars.

Phase 4 added an LLM-generated 2-3 sentence summary at the top of the section. `generate_related_futures_summary()` in `llm.py` produced a casual prose summary of the championship and award implications using GPT-4o-mini. The result was cached in the `LineMovementAnalysis` table with `analysis_type="related_futures"` — a 2-hour TTL for live games, never expires for completed games to keep the cache cheap.

Versions 3 through 6 of the design redesigned Bigger Picture as a **tier-grouped visual hierarchy**: championship hero at the top, then conference, then award rows with ESPN player headshots, then division, then a game grid, then stat prop cards with SVG gauges. Award dedup by player+award combo key handled cross-source duplicates. NOT_CHAMPIONSHIP_PATTERNS (14 patterns) downgraded misclassified markets — "Make Playoffs" should never display where "Win Championship" should. The `_is_stat_prop_market()` filter ensured that game-specific stat props only appeared on the correct event page via ±6h temporal proximity or `event_id` match.

Around the same time, the **championship grids** project shipped — league-level probability tables for every team's chances of winning the championship, conference, or division. This became its own workstream documented in `docs/championship-grids-project.md`. By April, the grids were live for 14+ leagues. Grid health became a tracked metric — a public audit script measured how complete each grid was. NHL went from 53.2% normalized to 100%. The MLB division-rule ordering was reordered. Stanley Cup qualifier markets got a pre-check to prevent championship misclassification. Play-in tournament markets were excluded from the conference column where they had been polluting the leaderboard with 3.5% probabilities for "Eastern Conference Play-In."

---

## Part 12 — The Quota Crisis and the Quota Guard

The Odds API costs about $119 a month and is rate-limited to 5 million events*market_types*regions per month — *not* per HTTP call (gotcha #6). In February 2026 the project hit the limit early. The fix was a circuit breaker in `tasks/redis_state.py` with three modes:

- **>50K remaining: Normal mode.** All sports poll at their configured intervals.
- **20K–50K remaining: LIVE_ONLY mode.** Only live games are polled.
- **<20K remaining: FULL_STOP mode.** All polling stops except for priority sports.

The team also introduced **sport-tier polling**. Tier 1 (NBA, NHL, MLB, NFL, NCAAB) polls every 32 seconds during live games using both the `us` and `us2` regions. Tier 2 (WNBA, EPL, MLS, UCL, MMA, NCAAF) polls every 64 seconds with just `us`. Tier 3 (everything else) polls every 128 seconds. The configuration lives in `SPORT_POLLING_TIERS`. Tiered discovery frequency was added on top — Tier 1 discovers new events every 15 minutes, Tier 2 every 30 minutes, Tier 3 every 2 hours, Tier 4 every 4 hours. This alone saved ~53% of discovery API calls, roughly 1.9 million billed requests per month.

Cache layers got more aggressive. Unknown sport keys are cached in Redis for 24 hours so a malformed lookup doesn't burn another quota call (this saves about 37,000 wasted requests per day). Score-fetching is skipped for ESPN-mapped sports when all events have an ESPN match (saves ~60–70% of the score API cost). The Odds API quota itself became visible — every response's `x-requests-remaining` header is captured passively, stored in Redis with a 25-hour TTL, and surfaced on an admin quota dashboard with daily-burn projections.

Then in **March 2026, the Odds API quota was completely exhausted**. The validation moment came: the system stayed up. Kalshi, Polymarket, ESPN, the Bain Luck stat model, and MLB Stats API kept feeding the win-probability charts. The product is "source-agnostic resilient." This is one of the most important architectural validations in the project's history because it proved that the multi-source bet had paid off.

---

## Part 13 — DataGolf, Golf, and a Whole New Category

In April 2026, golf became a first-class category. DataGolf was added as a new external service (~$30/month), providing pre-tournament predictions, live in-play probabilities, and leaderboards. The new `/categories/golf` page shipped — cross-source tournament odds aggregation across Polymarket, Kalshi, and the Odds API; current-event detection from odds movement; 24-hour biggest movers from snapshot history; sparkline charts; LPGA and TGL separation; a non-golf false-positive regex filter; and StatPal PGA schedule enrichment.

The category had bugs that taught the team new patterns. Augusta showed up as a "ghost tournament" because of stale Polymarket markets, and a `_clean_slug()` function was added to strip sponsor suffixes from tournament slugs. Importance-aware tiebreaking was added with `_SIGNATURE_EVENTS` and `_tournament_importance()` so that when two tournaments overlap, the Major beats the Signature event beats the regular event. DataGolf also had a long-running bug — 3,557 consecutive failures since April 22 due to a `UniqueViolation` — that was finally fixed in May with a Postgres advisory lock that prevented duplicate tournament insertions.

A bespoke market closure flow was added for golf: when a tournament completes, three layers of detection close out the market — schedule scan, completion detection, and stale market cleanup. The leaderboard reports "completed" instead of "live" when the tournament is done. M1, M2, M3, and M4 from the "Mystery Shopper" critical fix list were all about golf.

---

## Part 14 — Weather, Politics, Entertainment, Economics: The Non-Sports Pivot

April 19–20, 2026 was the **Weather Page**. A new top-level page at `/weather` with six sections, all live data: a hero rotator of the top five featured weather markets, a global temperature map of 49 cities with collision-resolved pins and a histogram distribution panel, cross-source comparison for 9 cities with both Kalshi and Polymarket data, a NYC 7-day rain forecast, monthly rainfall for 10 US cities with 24-hour movement deltas, a natural-events tracker with hurricane season strip and earthquake/tornado lists, a climate dashboard with 2026/2030/2050 horizon columns, and a wild-cards panel for rare events (supervolcano, solar storms). Continent outline SVGs on an abstract world map for visual identity. Six new API endpoints under `/api/weather/*` serving real data from 521 weather markets. SWR hooks with static fallback. GA4 page-type registered.

Then on May 6, 2026, the **politics and entertainment pages shipped**. These were quickly followed on May 7 by full v1 redesigns, because the first cuts weren't editorial enough. The politics v1 redesign added a presidential bar-race hero with R/D/I party badges (auto-detected from ~60 known names), dual Kalshi/Polymarket bars when both sources were available, an evolution chart showing the top 6 candidates over 30 days from real `FuturesOddsSnapshot` data, sparklines per candidate, a senate state map laid out in an 11-column geographic grid colored by Democratic win probability, chamber control cards for House and Senate, a cross-source spotlight showing markets where Kalshi and Polymarket disagreed by more than 5 percentage points, and category-themed market cards with colored top borders per theme.

The entertainment v1 redesign shipped at the same time with an editorial trending hero, a Spotify Race section laid out as horse-race contenders, a Billboard heatmap, a Rotten Tomatoes heatmap, album drop grids, artist streaming direction parsing (the ↑/↓ in market names became colored indicators), TMDB poster enrichment via a `useTMDBPoster` hook, and a cultural moments masonry feed.

Both pages had the same foundational pattern: a backend route queries `FuturesMarket` by `llm_sport_category` plus Kalshi ticker prefixes, classifies into sub-themes, builds a structured response with enriched market rows. A `_classify_kind()` function assigns rendering hints — `spotify`, `rt`, `boxoffice`, `reality`, `binary`, `multi` — based on ticker prefix, name regex, and outcome-count fallback. A `_group_threshold_markets()` function groups binary markets sharing an entity but differing by threshold into heatmap-ready groups. CSS modules, typed data from `lib/api.ts`, section components with tabbed sub-views.

The economics page rounded out the set. By mid-May all four non-sports category pages were live on web and had iOS counterparts.

There were category-specific bugs that taught new gotchas. Polymarket has French, UK, and Canadian presidential markets that contain "2028" and "presidential" — without filtering, the politics hero rendered Jean-Luc Mélenchon as the leading US candidate. A `_NON_US_RE` filter was added (gotcha #31). The entertainment `kind` classifier had a greedy `kxrt` ticker prefix that matched any ticker starting with those letters — political markets were getting classified as Rotten Tomatoes scores. Full prefixes like `kxrottentomatoes` were enforced (gotcha #32).

---

## Part 15 — The Discover Feed Breakthrough

If there's a single feature that defines the modern product, it's the **Discover feed**. The breakthrough moment was May 1, 2026. Up to that point, the feed had been ~85% sports because a `% at %` SQL filter — meant to catch sports event names — was killing 10,300 non-sports markets covering economics, politics, tech, and entertainment. Removing that one filter unlocked the entire non-sports inventory. The pool sort was changed from `tier + resolution` to `volume`. A micro-bet penalty was added for markets resolving in less than 24 hours. LLM hook descriptions and Pexels image enrichment tasks were scheduled four times daily. The combined ground truth — 295 Kalshi labels plus 4,680 Polymarket labels plus 146 from email — yielded 5,121 labeled markets the team could measure ranking against.

The feed went from 0% non-sports to ~85% non-sports in a single push.

A few days earlier, on April 29, the **`/discover` social feed prototype** had shipped — a mobile-first scrollable feed with hero visuals, probability bars, trend indicators, LLM headlines, and social actions (Like, Share, Dismiss). Category-specific gradient backgrounds for non-sports content — purple for economics, pink for culture, cyan for tech. Filters for resolved markets (≥95% leader) and stale events (>12h). It replaced search in the desktop nav, and on mobile it became one of four bottom tabs.

April 30 brought the **Higher/Lower game**. A `user_predictions` table tracked every guess. `POST /api/predictions` was auth-aware — `user_id` when logged in, `session_id` when anonymous. `GET /api/predictions/detailed-stats` returned total, correct, accuracy, current and best streak, category breakdown, 14-day trend, badges (First Guess, Hot Start, On Fire, Unstoppable, Centurion, Sharp Eye), and the user's recent 20 predictions. A stats page at `/discover/stats` rendered all of this with hero stats, badges, category accuracy bars, a trend chart, and prediction history. Shareable prediction cards with OG meta tags. A daily challenge card pinned at the top of the feed: "Make 5 predictions today" with a circular progress ring.

The same day, the team deployed an **animated probability counter** that counted up from 0 on scroll-into-view via `IntersectionObserver` and `requestAnimationFrame`, an 800ms ease-out cubic. A "Build Your Feed" onboarding modal with 12 category tiles for first-time visitors. A purple "Market Resolved" card type ready for backend wiring. Multi-day Discover enhancements: Pexels API images, LLM hook descriptions via GPT-4o-mini, category interleaving for diversity, staleness filtering, 20% non-sports quota, infinite scroll, category filter chips, trending badges, swipe gestures on mobile, market grouping with related markets collapsed into expandable cards, multi-column responsive layout, time-context labels, movement indicators.

May 7–8 was the **Discover Feed Ranking Breakthrough**. A new `feed_market_quality` classifier suppressed narrow commodity ladders, dated buckets, social-count filler, music-metric spam, and low-quality repeated families. Production audit metrics went to zero on `boring-rate@20`, `ladder/bucket-rate@20`, and `duplicate-family-rate@20`. The candidate pools widened to include non-sports volume, movement, enriched markets, and soon-resolving markets. Story-family diversity caps prevented the top of the feed from being five versions of the same story. Compelling-topic boosts gave priority to health outbreaks, AI/tech, geopolitics, elections, Fed/economics, entertainment, and sports personnel.

The single most impressive metric: deterministic Discover explanations moved `explanation-coverage@20` from **4/20 to 20/20** without relying on OpenAI hook generation at all. The feed now generates specific headlines from existing outcome data — named movers, opening-probability surprises, leader changes, source disagreement. "Yes side up 32.5 points from opening" is something the system can write itself.

A curated first-page mixer was added to apply category caps after scoring so politics and economics couldn't swallow the entire opening scroll. Archetype mixing capped editorial archetypes — `world_event`, `tech_frontier`, `macro_signal`, `culture_moment`, `health_weather_risk`, `sports_story` — with a required-texture pass that pulled strong tech, culture, weather, sports, or weird cards into the first page when available.

LLM hook enrichment was deliberately bounded. The team had previously planned to enrich all ~56,000 open markets with LLM hooks, which would have cost a fortune in OpenAI calls. Instead, `enrich_market_hooks` was scoped to only feed-shaped candidates, with a `limit=100` every six hours and a manual admin trigger capped at 250.

A `backend/scripts/audit_feed_quality.py` audit script reports on all of these metrics: boring rate, ladder/bucket rate, duplicate family rate, explanation coverage, ground-truth hit rate, category distribution, and top-card debug reasons. This script became the hill-climbing instrument that the team used to iterate the feed.

---

## Part 16 — The May Rage-Shake Marathons

Mid-May 2026 brought a new kind of work: **rage-shake bug reporting**. Shake an iOS device, or hit Cmd+Shift+B on macOS, and the app captures a screenshot with PencilKit finger/pencil markup overlay, plus automatic app state — current tab, app version, device model, OS version, user ID, session ID, live game count, timestamp. The screenshot is base64-encoded into a JSONB row in the `bug_reports` table. Admins triage at `/admin/bug-reports` with a split-pane layout, a decoded screenshot viewer, status toggles (New, Reviewed, Actioned, Dismissed), and an auto-diagnosis system that suggests severity (P0–P3), root cause, and a Claude Code prompt with a screenshot download command. It works for authenticated and anonymous users alike.

May 8 was the **Rage Shake Marathon — 14/14 bugs resolved in one night across two parallel Claude Code sessions**. The fixes ranged from iPad sidebar navigation that was getting stuck (RS-1), to a missing `timedelta` import that broke all six weather endpoints (RS-2), to false offline detection because `NWPathMonitor.currentPath` was being read before the monitor was started (RS-4, gotcha #35), to iPad sign-in failure because `connectedScenes.first` returned the wrong scene under Stage Manager (RS-5, gotcha #33), to a stale Met Gala market that was still showing in Discover two days post-event (RS-6, fixed with a fourth staleness filter for past `commence_time` plus no 24-hour movement).

May 11 added a second wave with another seven rage-shake fixes (RS-15 through RS-21), a TestFlight readiness pass with 14 fixes (swipe-to-navigate, idle timer disabled, error states, Watch app force-unwraps, entitlements cleanup, privacy manifest, privacy policy at `bainluck.com/privacy`), and a major native-UX pass that made Discover the default and leftmost iOS tab, added sticky category chips, replaced the old preferences wizard with a 4-card welcome onboarding, and redesigned the sign-in page with a 4-perk value proposition.

A `discover-quality` admin debug tool also shipped: `GET /admin/discover-quality/trace/{market_id}` explains why any market is or isn't appearing in the feed — eligibility, pool membership, staleness filters, quality score, suggested fixes. The admin frontend exposed it at `/admin/discover-quality`. First-party engagement capture started flowing into a `discover_interactions` table with open/dismiss/share rates by surface, category, and item type. Engagement-driven ranking opportunities surface promote/investigate/downrank recommendations from the data. Server-side personalization derives small bounded category boosts from a user's recent first-party Discover opens, shares, likes, expands, and dismisses.

---

## Part 17 — Calibration, Public Accountability, and the Hill-Climb

May 11, 2026 was also the **Public Calibration Pipeline** launch. The team had been building toward this for months. A new endpoint, `GET /api/admin/calibration-data`, returns pre-aggregated calibration buckets across three sources — Kalshi, Polymarket, and Odds API — covering 195,000 resolved outcomes. Odds API ground-truth integration produced 13,806 outcomes from 6,903 completed games where opening probabilities and final scores yielded calibration data points with known winners. **Virtual market reconstruction** grouped Polymarket multi-outcome events (e.g., "Who wins the presidency?") via `group_id` so they structurally match how Kalshi stores championship markets. Inverted field-price correction handled Kalshi multi-outcome markets where `opening_probability > 0.50` indicated the market was an inverted "No" price and needed flipping. Correlated threshold dedup collapsed player prop ladders ("HR 1+, 2+, 3+") to one calibration point per market, picked closest to 50%. A clean-resolution filter only included markets where 80%+ of outcomes resolved to near-0 or near-1.

The `is_winner` backfill task — `backfill_winners` — set the winner flag from `current_probability` on cleanly-resolved markets. The first run filled 52,000 of 131,000 markets. It runs every six hours. A backfill status endpoint shows progress per source. A static HTML report was built with SVG charts (no JavaScript dependencies) and a methodology and limitations section. The report builder script lives at `backend/scripts/build_calibration_report_svg.py`.

The headline result: **MCE of 4.8 percentage points, Brier score of 0.1745, which is 30% better than random.** Seven of ten probability buckets were within 5 percentage points of perfect calibration. The page is public at `/calibration`.

The same day, data-quality fixes immediately moved the metric. The winner-flag inversion bug was fixed — a multi-outcome market inversion was flipping winner detection backwards, causing the golf 0–10% bucket to show 44.6% actual when it should have been about 1%. An `event_id` fallback grouping was added for Polymarket sub-markets without `group_id`. The default-price filter caught Kalshi golf markets where 80 outcomes were all sitting at `opening_probability = 0.97` (no real trading) — the filter detects "50%+ of outcomes sharing the same price" and excludes them. Golf MCE improved from 20pp to 8.4pp.

The calibration page is the project's most public commitment to honesty. There's no other prediction-market product that publishes its own accuracy in this much detail.

---

## Part 18 — The Final Push: May 13, 2026 (the Day in the Git History)

The 50 commits in this repository all happened on a single day: May 13, 2026. They are the only commits visible in `git log --reverse`, which means they are the most recent layer of work on top of everything described above. They form a tight, focused list of polish work, but you can see the whole project's DNA in them.

Some highlights from May 13's commit timeline, in chronological order:

- **`Mark 0f-13h as already fixed (award headshots use PlayerHeadshot)`** — The day starts with a verification pass: the team already had `PlayerHeadshot` correctly wired in `RelatedFutures.tsx`. No new code, just confirming and updating the backlog.
- **`Add bulk date-mismatch unlink endpoint`** — A new admin endpoint to bulk-unlink Kalshi markets where the ticker date no longer matches the linked event's date. This is matching-quality plumbing.
- **`Polish iOS Entertainment page with visual card design`** — Visual parity work bringing the iOS entertainment page up to the design quality of the web version.
- **`Fix CI: add daily-digest to expected beat schedule entries`** — A test added back in April (`tests/test_tasks_wiring.py`) maintains an explicit allowlist of every Celery beat schedule entry. Adding a new scheduled task without updating this allowlist causes CI to fail. The fix here is to add the new `daily-digest` entry to that allowlist (gotcha #61).
- **`Simplify trading filter: require any snapshot exists (fast indexed lookup)`** — A query rewrite to make the calibration "untradeable outcomes" filter run on a fast indexed lookup instead of a heavy aggregation.
- **`Batch date-mismatch unlinks to avoid Heroku timeout`** — The bulk endpoint added two commits earlier hits Heroku's 30-second request timeout when processing thousands of mismatches. Batching restores it.
- **`Exclude untradeable outcomes via backfill, not query-time filter`** — A philosophical move: instead of filtering at every read, do the filtering once at backfill time. Reads stay fast.
- **`Add orphaned snapshot cleanup for unlinked markets`** — When a market is unlinked from an event, its `win_prob_snapshots` rows become orphans. A new cleanup task deletes them.
- **`Polish iOS Economics page to match Politics/Entertainment design`** — Continuing the iOS native-design pass.
- **`Mark MS-14 as resolved (EPL works, UFC/Tennis removed from nav)`** — Backlog hygiene.
- **`Wire up cross-platform pin sync for web (events + futures)`** — Web pin hooks (`usePinnedEvents.ts` and `usePinnedFutures.ts`) had been localStorage-only, which meant pins made on web were invisible on iOS. Now they sync to the server when the user is authenticated (gotcha #60).
- **`Use the right calibration price: closing line for sports, settled price for elections`** — A subtle but important distinction in how the calibration buckets are constructed. Sports markets close before the game starts, so the closing line is the "fair" price; political markets settle after a known event, so the settled price is the right anchor. The default eventually flipped back to opening probability after A/B testing showed closing-line MCE was actually worse.
- **`Add gotchas #58-62: feed normalization, staleness, pin sync, beat test, Gmail OAuth`** — The project's institutional memory grows. Five new gotchas added to the reference doc: feed probability normalization for independent binary markets when their sum exceeds 105% (the BR27 fix from May 12); the lowered 95% staleness threshold (from BR25); the cross-platform pin sync; the beat-schedule allowlist test; and the Gmail OAuth refresh-token configuration for the bug-fix notification email pipeline.
- **`Tighten date mismatch threshold from 36h to 18h`** — Followed shortly by **`Adaptive date threshold: 4h with HHMM, 18h without`**, because Kalshi tickers sometimes encode the hour and minute. When they do, the system can be much stricter about the date-match window.
- **`Update docs: May 13 shipped features, test counts, iOS file count`** — The team keeps the test counts and file counts in `CLAUDE.md` honest. By the end of the day, the test count was about 3,500 and the iOS app was 89 Swift files.
- **`Add bug admin improvements + PRD update backlog items, bulk-update bug statuses`** — The bug-report admin gets a bulk update endpoint. The PRD gets a refresh of priorities.
- **`Expand contract tests for playoff grids, league futures, related futures, and team progression`** — 124 new contract tests in one commit. The integration suite goes from 210 to about 335 tests.
- **`Update 0f-3d with investigation findings, recommend display-time query approach`** — The team keeps every backlog item updated with what was tried and what's still open.
- **`Clean partially-orphaned snapshots + capture remaining issues in backlog`** — A long-running cleanup is now mostly done, with leftover edge cases captured for follow-up.
- **`Remove status and category filters from linked game-markets query`** — A real bug fix. Linked Kalshi markets — overtime, half-winners, player props, points leaders — had been hidden from event detail pages because the game-markets endpoint was filtering by `status` and `llm_sport_category`. Removing both filters from the linked query path immediately surfaces all those markets.
- **`Add burndown chart and analytics to admin bug reports page`** — An SVG burndown chart on the admin bug reports page showing open vs. closed bugs over time, plus summary stats (total, open, closed, average resolution time).
- **`Polish iOS Preferences page with card-based design`** — All five iOS NATIVE-DESIGN pages (Politics, Entertainment, Weather, Economics, Preferences) are now complete.
- **`Add series markets as dedicated array on event detail page`** — Series markets (Series Winner, Series Exact Score, Series Spread, Series Total Games) get their own dedicated array via a display-time team-name query. New `display_category="series"` classification. Backend, web, and iOS all ship the rendering.
- **`Parse HHMM from Kalshi tickers + stat model pregame prior`** — Two improvements in one commit: ticker time-parsing (which feeds the adaptive-threshold change earlier in the day) and a pregame prior for the stat model that uses sportsbook opening odds.
- **`Use sportsbook opening odds as stat model pregame prior`** — Continuing that thread.
- **`Add calibration_probability coverage stats to backfill status endpoint`** — The calibration backfill becomes more transparent.
- **`Fix calibration_probability backfill: combine closing line + fallback in single CTE`** — Another window-function CTE rewrite, the same pattern that has shown up since the early retention work.
- **`Increase calibration_probability batch size to 200K per cycle`** — The backfill finally has the headroom to run quickly.
- **`Add cache-bust parameter to calibration endpoint for admin checks`** — So the admin can re-check the live results without waiting for the 1-hour cache to expire.
- **`Add use_opening parameter to calibration endpoint for A/B comparison`** — A literal A/B test for closing-line versus opening-probability calibration.
- **`Default calibration to opening_probability — closing line makes MCE worse`** — The A/B test settles it. Closing line is methodologically prettier but empirically worse, so opening probability stays.
- **`Use closing line (calibration_probability) as default — methodologically correct`** — The very last commit of the day flips that decision back. The methodologically correct choice wins, even at the cost of slightly worse MCE numbers.

That last back-and-forth — opening probability defaulted, then flipped back to closing line on the methodological argument — captures the project's whole personality. It's a product that publishes its own scorecard, then argues with itself in production about which scorecard is the right one.

---

## Part 19 — The Architecture That Holds It All Together

Stepping back from the chronological story, here's the architecture that all of this evolution produced:

**Backend.** FastAPI on Python 3.11+, hosted on Heroku, with about 3,500 pytest items and 335+ integration contract tests. PostgreSQL on Heroku Postgres. Celery on Heroku Redis with two worker pools — a "realtime" queue for live polling and a "background" queue for everything else. Twenty-seven task modules, including dedicated polling modules for each external source.

**External services.** The Odds API (~$119/month, the most constrained resource), Kalshi (free, API key required), Polymarket (free, no key), StatPal for schedules and rosters and play-by-play (~$99/month), DataGolf for golf predictions (~$30/month), MLB Stats API for live baseball win probability (free, no key), ESPN for team colors and logos and live game data and win probability (free, undocumented), OpenAI GPT-4o-mini for LLM classification and market hook descriptions (~$10/month), Pexels for free stock photos on Discover feed cards (200 requests/hour), TMDB for movie/TV metadata (free tier, client-side via `frontend/lib/tmdb.ts`), and Firebase Auth for Google and Apple Sign-In (free tier).

**Frontend.** Next.js 14 with the App Router, hosted on Vercel. Thirty-plus pages including `/discover`, `/sports`, `/politics`, `/entertainment`, `/weather`, `/economics`, `/calibration`, `/preferences`, `/my-stuff`, the championship grid pages, and the event detail pages. Strict TypeScript. A design system tokenized in `globals.css` — `bg-surface-card`, `text-text-primary`, `text-accent-live`, `text-accent-brand` — with no raw Tailwind dark classes (the site is light-mode only). Every page uses three GA4 hooks before any conditional return: `usePageTracking`, `useScrollDepth`, `useEngagementTime`.

**iOS and macOS.** A shared SwiftUI codebase with 89 Swift files, distributed via TestFlight. Models are `Decodable` and prefixed with `nonisolated`. ViewModels never carry class-level `@MainActor`. The auth flow uses the same backend-issued PyJWT pattern as the web Tier 3 fallback. The whole app uses Firebase Analytics for parity with the web GA4 tracking.

**Database schema.** Thirty SQLAlchemy models. Key tables: `events` (with the JSONB `win_probability_sources` column that holds all six sources), `odds_snapshots` with write-time dedup, `win_prob_snapshots` for multi-source history, `futures_markets` and `futures_outcomes`, `teams`, `team_identity_mapping` for cross-source identity, `user_predictions` for Higher/Lower guesses, `user_seen_markets` for dedup in the feed, `users` for Firebase Auth, `bug_reports` for rage-shake submissions, `discover_interactions` for first-party engagement.

**Event Registry.** The `services/event_registry.py` module's `find_or_create_event()` runs a 4-step cascade: exact source ID, then cross-source ID, then structured match (sport plus time within ±4 hours plus team match), then create. All five source tasks are wired up. ESPN is a first-class source.

**Probability Aggregation.** `utils/aggregation.py`'s `compute_aggregate_probability()` reads from the `Event.win_probability_sources` JSONB. Source weights are explicit: betting 3.0, ESPN 1.5, stat model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via `select+update`, never via ORM attribute assignment, because ORM attribute assignment for JSONB silently fails due to session caching (gotcha #8). Same class of bug as ORM-on-Core mixing (gotcha #22).

**Prediction Market Matching.** A three-phase task: Link (Pass 1 ticker scan, Pass 2 general scan), Re-validate (Phase 1.5), Snapshot writing (Phase 2). Per-market commit to avoid deadlocks with the live polling task. Link rate tracked at `/api/admin/prediction-markets/link-rate`.

**Quality audits.** Several public-facing audit scripts: `scripts/audit_event_matching.py` measures the 4-layer matching quality (event existence, market-to-event linking, futures surfacing, market completeness). `scripts/audit_grid_accuracy.py` measures championship grid completeness. `scripts/audit_feed_quality.py` measures feed precision metrics. `scripts/audit_event_timing.py` measures chart-domain alignment. The audit results are committed to the repo — the most recent run shows 100% on Layers 1 through 4 and 51/51 on grid accuracy.

**CI test coverage.** Six test files specifically guard against past mistakes: `test_startup.py` catches import errors that crash the web dyno; `test_tasks_wiring.py` enforces the Celery beat schedule allowlist; `test_alembic.py` catches multiple heads, deleted migrations, and orphaned revisions; the GitHub Actions `frontend-build` job runs `npm run build` to catch ESLint and TypeScript errors that Vercel would reject; integration tests cover feed scoring, event detail shape, and category page API shape.

---

## Part 20 — The 62 Gotchas: A Library of Hard-Won Lessons

The project's `gotchas-reference.md` file, combined with the inline gotchas in `CLAUDE.md`, is a 62-item library of things that bit the team. They are worth listing in summary, because they are the closest thing the project has to an autobiography:

1. Alembic revision IDs must be ≤32 characters.
2. Alembic uses psycopg2, not asyncpg, intentionally for the Heroku release phase.
3. Admin endpoints require mounting in both `main.py` AND `routes/__init__.py`.
4. `sport_keys.py` imports nothing — pure data, zero circular-import risk.
5. `Event.external_id` is nullable — StatPal creates events without an Odds API ID.
6. The Odds API bills per `events × market_types × regions`, not per HTTP call.
7. `Event.sport_id` is an integer FK to `sports.id`, not a string.
8. ORM attribute assignment for JSONB silently fails — always use SQLAlchemy `update()`.
9. Kalshi `commence_time` is the market resolution date, not the game date.
10. `llm_sport_category` from Kalshi polling is often wrong — derive from ticker prefix instead.
11. Phase 2 deadlocks with live polling — per-market commit + rollback on deadlock detection.
12. iOS models must be `Decodable` not `Codable`, and prefixed with `nonisolated`.
13. iOS ViewModels: NO `@MainActor` on the class — only on individual async methods.
14. Python 3.12+ redundant imports cause `UnboundLocalError`.
15. Safari breaks Firebase Google Auth — use GIS plus backend custom token fallback.
16. `compute_market_tier()` must check name patterns BEFORE `game_prop` category.
17. Kalshi market backfill must use `status=None` — live game markets have `status="active"`, not `"open"`.
18. Kalshi threshold outcomes ("2+", "Aaron Judge: 1+") are OVER probabilities — don't invert.
19. Don't time-window linked markets — if the matching task set `event_id`, trust it.
20. Polymarket midpoint unreliable during blowouts — use `lastTradePrice` when bid/ask spread > 15pp.
21. Polymarket game events have nested sub-markets — decompose into separate `FuturesMarket` rows.
22. ORM attribute assignment lost when mixed with Core SQL updates.
23. `completed_at` is a backend processing timestamp, not game-end time.
24. Kalshi dual markets cause probability oscillation — deduplicate by `(event_id, source)`.
25. `CurrentOdds.spread` is unsigned — use `home_spread` (signed from home perspective).
26. Pexels rate limit is 200 req/hr — target feed-visible markets first.
27. Never delete a migration file that has already run on Heroku.
28. Vercel builds run ESLint, not just TypeScript — `tsc --noEmit` is not sufficient.
29. Kalshi market names use abbreviations that fail `ILIKE` matching.
30. Admin write endpoints need `_check_admin_secret`.
31. `_is_headline_market` must filter non-US elections.
32. Entertainment `kind` classification: avoid greedy ticker prefixes.
33. iPad Stage Manager breaks `connectedScenes.first`.
34. Bug report admin status mismatch — backend `_VALID_STATUSES` must include `actioned`/`dismissed`.
35. `NWPathMonitor.currentPath` is unsatisfied until started.
36. StatPal `season-schedule` puts playoffs in `tournament.week`, not `tournament.match`.
37. StatPal livescores normalizes period to `"live"` — preserve `raw_status`.
38. Event merge task must reassign ALL FK tables before delete (eight tables, only two cascade).
58. Feed probability normalization for independent binary markets (Kalshi binaries can sum >100%).
59. Feed staleness threshold: 95%, not 97%.
60. Web pin hooks were localStorage-only.
61. Celery beat schedule test has an allowlist.
62. Gmail API OAuth refresh tokens via Google Workspace.

(Items 39 through 57 live in `docs/gotchas-reference.md` and cover similar terrain.)

Each one of these gotchas represents hours or days of debugging that the team turned into a one-line lesson. Together they are the institutional memory of the project — the kind of memory that you can hand to a new engineer or a Claude Code session and get them productive quickly.

---

## Part 21 — Where the Project Stands on May 13, 2026

As of the close of the day this git history captures, the product looks like this:

**The user-facing surfaces:**
- The Discover feed at `bainluck.com` is the default landing page, with social cards, Higher/Lower games, daily challenges, prediction streaks, category filters, and personalization.
- The sports feed at `bainluck.com/sports` covers live, upcoming, and recently completed games with multi-source probability charts.
- Four category dashboards — `/politics`, `/entertainment`, `/economics`, `/weather` — each with editorial heroes, themed visualizations, and full iOS counterparts.
- Event detail pages with multi-source probability charts, market maps, player props, series markets, and the Bigger Picture related-futures section.
- Championship grids for 14+ leagues at `/sport/[sport]/[league]`.
- A public calibration report at `/calibration` showing 4.8pp MCE across 181K resolved outcomes.
- A `/discover/stats` page for prediction streaks and accuracy.
- An iOS and macOS app distributed via TestFlight, with full feature parity to the web.
- A daily-digest email going out at 8am ET, scheduled via Celery beat.
- A bug-fix notification email pipeline using Gmail API OAuth.
- A friend-challenges backend scaffold with three API endpoints (UI not yet built).

**The engineering scoreboard:**
- 3,500+ backend pytest items.
- 335+ integration contract tests.
- 89 Swift files.
- 27 Celery task modules.
- 30 SQLAlchemy models.
- 62 documented gotchas.
- 100% on the Layer 1, 2, 3, and 4 matching audits (event existence, market-to-event linking, futures surfacing, market completeness).
- 51/51 on grid accuracy.
- Production audit metrics on Discover feed: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20`.

**The products' philosophical commitments:**
- Visual over numerical. Percentages and charts beat odds formats every time.
- Explain movement, not advice. Show what changed, not what to bet.
- Discovery-first. The feed surfaces what is interesting and surprising.
- Respect attention. No spammy notifications. Silence is sometimes the correct UX.
- Responsible by design. Betting is contextual information, not the call to action. Never show volume or trade data to users.
- Multi-platform native. Web, iOS, and macOS should each feel native, not like ports.

---

## Part 22 — The Story in One Paragraph (For the Podcast Cold Open)

Bain Luck started as a single page that converted American odds into clean percentages so casual fans could understand them at a glance. Over the course of about a year and a half it grew into a multi-source probability discovery platform spanning sports, politics, economics, weather, entertainment, technology, and culture — pulling from sportsbooks, Kalshi, Polymarket, ESPN, an in-house statistical model, MLB Stats API, DataGolf, and StatPal, then aggregating them into a single weighted probability per question. Along the way it survived an Odds API quota exhaustion that proved its multi-source bet had paid off, migrated its proprietary Pulse excitement metric to the academic Excitement Index, shipped a 3-tier Safari-aware authentication fallback, built a personalization layer that boosts your local team 3.5x, fought a long matching war against Kalshi's ticker abbreviations and Polymarket's nested sub-markets, learned to invert and dedupe and normalize and time-window every kind of edge case the data could throw at it, deployed an iOS app to TestFlight with 89 Swift files of full feature parity, ranked itself on its own accuracy with a public calibration report showing 4.8 percentage points of mean calibration error across 181,000 resolved outcomes, redesigned its category pages with editorial trending heroes inspired by The Athletic and FiveThirtyEight, and turned a single Discover feed into a social product with Higher/Lower games, daily challenges, and prediction streaks — all while keeping the founder's original promise to never become a sportsbook, never recommend a bet, never publish a tout. Today it runs on Heroku and Vercel, costs about $260 a month in external services, and ships from a 50-commit afternoon of polish that adds five more gotchas to the institutional memory and another 124 contract tests to the suite.

---

*End of evolution history. Total length suitable for a 15-minute spoken podcast at a normal cadence, with rich detail in every section so the NotebookLM hosts can pull quotes, anecdotes, and technical specifics naturally.*
