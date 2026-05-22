# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Bain Luck** is a prediction market discovery platform that translates betting and prediction markets into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130". Started with sports odds, now covers economics, politics, tech, culture, weather, and more via the Discover feed.

**North Star**: The most engaging way to explore what the world thinks will happen.
**Target User**: Casual fans who want probability-first context — not betting advice.
**Live Site**: https://bainluck.com (Discover is the default landing page) | **Sports Feed**: https://bainluck.com/sports

---

## The #1 Technical Challenge: Semantic Matching

The core magic of Bain Luck is **perfect semantic understanding** of every event, market, and source — then grouping and matching them so the user sees one unified view. This is the hardest technical problem in the product and the biggest leverage point.

There are 4 layers of matching, measured by `scripts/audit_event_matching.py`:

| Layer | What it measures | Audit | Status (April 24) |
|-------|-----------------|-------|-------------------|
| **L1: Event Existence** | Every game exists with all sources | `--self-check` | ✅ 100% |
| **L2: Market → Event** | Game markets linked via event_id | `--self-check` | ✅ 100% |
| **L3: Futures Surfacing** | Season futures on event detail pages | `--self-check` | ✅ 100% (MLB/NBA/NHL) |
| **L4: Market Completeness** | Every market type showing per game | `--l4-deep` | ✅ Verified live (April 24) |

Plus **Grid Accuracy** (`scripts/audit_grid_accuracy.py`): 51/51 (100%).

**Hill-climb playbook**: `docs/hill-climb-guide.md` — measure → fix biggest bucket → re-measure → repeat.

**Philosophy**: Any metric below target for markets that SHOULD match is a bug, not a feature gap. Distinguish "our bug" from "upstream gap" (Kalshi liquidity, Polymarket coverage).

---

## Linked Reference Docs

| Doc | Purpose | When to update |
|-----|---------|---------------|
| `docs/backlog.md` | Strategic backlog: priorities, rationale, and long-term context | When items ship, are added, or reprioritized |
| `docs/github-workflow.md` | GitHub Issues/Project operating model and backlog sync rules | When issue labels, templates, project columns, or agent handoff rules change |
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin | When architecture changes |
| `docs/gotchas-reference.md` | Full gotcha catalog and incident learnings | When new gotchas discovered |
| `docs/quality-audit.md` | Audit script usage, check catalog | When checks added/removed |
| `docs/hill-climb-guide.md` | Matching accuracy hill-climb playbook | When layers/gotchas change |
| `docs/feature-reference.md` | Detailed feature documentation | When features ship |
| `docs/completed-features.md` | Shipped features log | When features ship |
| `docs/design-system.md` | Visual design system: colors, type, motion, voice, components | When design tokens or patterns change |

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 5,000+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS App | SwiftUI (shared codebase, 108 Swift files) | TestFlight / direct |

**Key External Services:**
- **The Odds API** — Sports odds data (~$119/mo, 5M monthly quota — monitor closely)
- **Kalshi** — Prediction market data (free, API key required)
- **Polymarket** — Prediction market data (free, no API key)
- **StatPal** — Schedules, rosters, injuries, play-by-play (~$99/mo)
- **DataGolf** — Golf predictions, live in-play probabilities, leaderboards (~$30/mo)
- **MLB Stats API** — Live baseball win probability (free, no key)
- **ESPN** — Team colors, logos, live game data, win probability (free, undocumented)
- **OpenAI** — GPT-4o-mini for LLM classification + market hook descriptions (~$10/mo)
- **Pexels** — Free stock photos for Discover feed cards (200 req/hr)
- **TMDB** — Movie/TV metadata, posters, cast info (free tier, client-side via `frontend/lib/tmdb.ts`)
- **Firebase Auth** — Google + Apple Sign-In (free tier)

---

## Development Workflow

- **Deployments from GitHub**: `git push origin master` triggers CI; Vercel deploys frontend from GitHub, and Heroku deploy runs through the serialized CI `deploy` job after tests pass.
- **Database migrations**: `alembic revision --autogenerate -m "description"`, applied on Heroku release
- **Backend tests**: `cd backend && python3 -m pytest tests/ -v` (5,000+ tests)
- **Single test**: `cd backend && python3 -m pytest tests/test_feed_scoring.py::TestFeedBaseScoring::test_live_nba -v`
- **Integration tests**: `cd backend && python3 -m pytest tests/integration/ -v` (590+ contract tests)
- **Smoke test (MANDATORY before push)**: `cd backend && python3 -m pytest tests/test_startup.py -v` (<1s, catches import errors)
- **Frontend build (MANDATORY before push)**: `cd frontend && npm run build` — catches BOTH TypeScript AND ESLint errors. Vercel runs this exact command; `tsc --noEmit` alone is NOT sufficient.
- **Frontend tests**: `cd frontend && npx jest` (single: `npx jest --testPathPattern=DiscoverCard`)
- **Procfile validates imports**: Release phase runs `python3 -c "from app.main import app"` before Alembic. If the app can't import, the release fails and the broken code never reaches the web dyno.
- **CI runs both**: GitHub Actions runs backend pytest + frontend `npm run build` on every push to master, then serializes Heroku deploys with deploy-job concurrency.

### Key Admin URLs
```
https://bainluck.com/admin              — Operations dashboard
https://api.bainluck.com/docs           — API docs (Swagger)
https://api.bainluck.com/api/admin/prediction-markets/link-rate?secret=$ADMIN_TOKEN  — Link rate health
```

---

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models (30 models)
│   │   ├── routes/              # API endpoints
│   │   ├── services/            # External API clients + event_registry.py
│   │   ├── config/              # win_prob_sources.py, league_configs.py
│   │   ├── tasks/               # Celery tasks (27 modules)
│   │   └── utils/               # Pure logic (sport_keys.py, prediction_market_matching.py, etc.)
│   ├── alembic/                 # Database migrations
│   └── tests/                   # 5,000+ pytest items
├── frontend/
│   ├── app/                     # Next.js app router (30+ pages, incl. /discover, /weather)
│   ├── components/              # React components (DiscoverCard, OddsChart, MarketMap, etc.)
│   └── lib/                     # API client, types, utilities
├── ios/Bain Luck/               # iOS + macOS app (SwiftUI, 108 Swift files)
└── docs/                        # Documentation
```

---

## Core Architecture

**Event Registry** (`services/event_registry.py`): Unified `find_or_create_event()` with 4-step cascade: exact source ID → cross-source ID → structured match (sport + time ± 4h + teams) → create. All 5 source tasks wired up. ESPN is a first-class source.

**Probability Aggregation** (`utils/aggregation.py`): `compute_aggregate_probability()` reads from `Event.win_probability_sources` JSONB. Source weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via `select+update` pattern (NOT ORM attribute assignment — silently fails due to session caching).

**Prediction Market Matching** (`tasks/prediction_market_matching.py`): Hourly task links Kalshi/Polymarket game markets to events. Three-phase: Link (Pass 1 ticker scan + Pass 2 general scan) → Re-validate (Phase 1.5) → Snapshot writing (Phase 2). Per-market commit to avoid deadlocks with live polling task. Link rate tracked at `/api/admin/prediction-markets/link-rate`.

**Source-Agnostic Resilience**: System works when any single source goes dark (validated during March 2026 Odds API quota exhaustion).

**Prediction Market Pipeline** (Kalshi/Polymarket → event detail page):
1. `poll_kalshi_markets` (every 2h) / `poll_polymarket_markets` (every 1h) — ingest ALL markets (minus crypto). Both paginate unfiltered.
2. `match_prediction_markets` (every 15 min) — link game markets to events via `event_id` FK. Pass 1: Kalshi ticker scan. Pass 2: Polymarket name matching.
3. `poll_live_prediction_markets` (every 2 min, realtime queue) — live price updates for linked markets.
4. Game-markets endpoint: loads via `event_id` FK + fallback (unlinked markets matching both team names + game ticker prefix or `category="game_prop"`).

**Discover Feed Ranking & Explanation Pipeline** (`routes/feed.py`, `utils/feed_market_quality.py`, `utils/feed_reasons.py`, `scripts/audit_feed_quality.py`):
- The feed builds multiple candidate pools (sports, non-sports volume, movement, enriched, soon-resolving), scores with futures highlights, then applies market-quality caps/diversity before returning cards.
- Quality classifier suppresses narrow commodity/finance ladders, repetitive dated buckets, social-count filler, and weak explanation cards. It separately boosts compelling public stories: politics, geopolitics, Fed/economics, AI/tech, health outbreaks, entertainment, and sports personnel.
- Deterministic futures explanations are now first-class. Do not rely on LLM hooks to make the first page understandable: headlines should name the mover/leader/source disagreement from existing outcome data (e.g., "Yes side up 32.5 points from opening").
- Personalization is intentionally bounded and latency-safe: recent Discover interactions produce small category plus feature/entity/archetype affinities for signed-in users and anonymous sessions. Right swipe is `like` / "more like this"; left swipe is `unlike` / "less like this" and should be treated as a soft downrank, not a permanent hard dismissal. Category dismiss penalty escalates: 3+ swipes -> -0.40 (0.60x), 5+ -> -0.60 (0.40x), 8+ -> -0.80 (0.20x). Feature dislike penalty caps at -0.25. Semantic dismiss propagation compares candidate topic/region/team/term tokens against the 50 most recent dismiss/unlike token sets, ignores generic category/type/archetype/format overlap, and applies only a soft `semantic_dismiss:-0.30` multiplier penalty above 0.60 Jaccard similarity. `MIN_MULTIPLIER` is 0.15.
- Dismiss signal propagates to story keys and group IDs: dismissing one "Will Russia capture [village]?" market suppresses all markets sharing the same `story:russia_ukraine` key. `recent_dismissed_story_keys` and `recent_dismissed_group_ids` are populated during personalization context loading.
- Discover event demotion in Discover mode (`event_pct < 0.3`): non-exceptional events are capped at score 35 so futures can compete. "Exceptional" requires: EI >= 85 (any league), EI >= 70 AND Tier 1/2 league, headline exception keyword AND Tier 1/2, or score >= 90 AND EI >= 50. Headline keywords like "upset"/"comeback"/"historic" only count for major leagues — a Ligue 2 upset is not exceptional. "elimination"/"buzzer"/"walk-off" are exceptional regardless of tier.
- Election allowlist: `_MAJOR_ELECTION_RE` in `futures_highlights.py` lists elections that deserve the full politics base score (US federal, 25 major countries, supranational). Elections with "election/winner/nominee" that don't match get `FOREIGN_LOCAL_ELECTION_PENALTY = -30`. Obscure elections (UK boroughs, by-elections) get a separate `-20` penalty via `_OBSCURE_ELECTION_PATTERNS`.
- Soccer league allowlist: `_TOP_TIER_SOCCER_RE` in `feed_market_quality.py` matches EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, Europa League, MLS, FIFA World Cup, Copa America, Copa Libertadores, Liga MX. Non-matching soccer futures get `story:minor_soccer_leagues` (capped at 1).
- Geopolitics story caps: `story:russia_ukraine` (cap 2) now catches Russia + capture/enter/advance/territory AND Russia + Putin/president/regime/fall. `story:middle_east_conflict` (cap 4) catches Iran/Israel/Gaza/Hormuz.
- Category base scores in `futures_highlights.py`: politics 50, geopolitics 55, economics 50, tech 50, entertainment 52, culture 48, health 42, weather 38, crypto 35. Sports get `SPORTS_CATEGORY_BASE = 18.5`. Entertainment has dedicated compelling patterns for awards shows, TV series, and media platforms.
- LLM enrichment is intentionally bounded and async. `enrich_market_hooks` only targets feed-shaped candidates and Celery runs small batches (`limit=100` every 6h). `enrich_discover_llm_metadata` adds cached structured metadata under `FuturesMarket.market_metadata["discover_llm"]` for feed-shaped candidates (`limit=125` every 6h), and feed ranking consumes only that cached metadata. Never run LLM calls inside `GET /api/feed` or grind through the full open-market backlog (~56K markets).
- Daily LLM eval is advisory only: `evaluate_discover_with_llm` grades the top 50 Discover futures, compares against Polymarket email highlights, and writes `llm_proposed_*` review rows for admin inspection. These rows do not affect ranking unless a human later records an accepted promote/downrank decision.
- Offline interestingness calibration has a pure scorer in `utils/market_interestingness.py` and a local-input script at `scripts/calibrate_interestingness.py` for CSV/JSON/JSONL labeled rows. It is a scaffold for review and tuning, not a feed-ranking integration; do not wire it into production ranking without an audit-backed rollout.
- Current production audit target: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20`. Use `python3 scripts/audit_feed_quality.py` to measure.

**Search** (`routes/events.py`):
`GET /api/events/search` preserves broad ILIKE matching for events, futures markets, and typeahead, but ranks with query-time PostgreSQL full-text search when available. Event/team text is weighted A, futures market names B, and outcome names C via correlated aggregation. There is no stored `ts_vector` migration yet; keep future indexing work Postgres-specific and prove it improves real search traces before adding triggers or table rewrites.

**Cross-Source Market Matching** (`utils/cross_source_matching.py`):
Shared utility for finding markets that appear on both Kalshi and Polymarket about the same question. `normalize_question()` strips punctuation and lowercases; `find_cross_source_markets()` groups by normalized question, filters to Kalshi+Polymarket pairs, and ranks by probability disagreement (delta). Used by all 4 category pages. Matching is exact-string only — paraphrased questions won't match.

**Themed Dashboard Pages** (politics, entertainment, weather, economics) — all 5 native category pages polished (Politics, Entertainment, Weather, Economics, Preferences):
Each category page follows the same pattern:
- Backend route (`routes/politics.py`, `routes/entertainment.py`) queries `FuturesMarket` by `llm_sport_category` + Kalshi ticker prefixes, classifies into sub-themes, builds structured response with enriched market rows
- Cross-source matching via shared `find_cross_source_markets()` from `utils/cross_source_matching.py`
- `_classify_kind()` assigns rendering hints (`spotify`, `rt`, `boxoffice`, `reality`, `binary`, `multi`, etc.) based on ticker prefix → name regex → outcome count fallback
- `_group_threshold_markets()` groups binary markets sharing an entity but differing by threshold (e.g., multiple "Movie X RT score ≥ N" markets) into heatmap-ready groups
- Frontend: CSS module (`politics.module.css`, `entertainment.module.css`), typed data from `lib/api.ts`, section components with tabbed sub-views
- Markets enriched with: `volume_24h`, `resolution_date`, `image_url`, `hook_description`, per-outcome `probability_change_24h`
- TMDB client (`lib/tmdb.ts`): client-side movie poster lookup with localStorage cache, used by entertainment CoverTile component

**iOS Authentication** (`ios/.../Services/AuthManager.swift`):
Backend-session-token pattern, NOT typical Firebase client auth. iOS SDK handles OAuth popup (Apple native / Google GID SDK) → raw credential sent to Bain Luck backend (`POST /api/auth/apple` or `/api/auth/google-access-token`) → backend verifies with identity provider, creates Firebase user, issues PyJWT session token (HS256, 30-day TTL) → iOS stores in Keychain, sends as `Bearer` on all API calls. Originated as Safari ITP workaround; iOS uses the same flow. Silent Google restore on token expiry. Apple credential revocation checked on foreground.

**Native iOS/macOS Code Organization** (`ios/Bain Luck/Bain Luck/`):
SwiftUI views live under `Views/`, shared UI under `Components/`, cross-platform helpers under `Utilities/`, API/auth/navigation under `Services/`, and all `ObservableObject` view models under `ViewModels/`. View models use `@MainActor` on async mutating methods rather than class-wide isolation unless a specific class needs it. Published state that views only read should be `private(set)`; fields bound from views, such as search query or selected filters, remain mutable. String-copy/share logic should go through `copyToClipboard`, `eventShareURL`, and `futuresShareURL`. The iPad/macOS sidebar intentionally keeps the 🍀 Bain Luck title and Calibration entry point; the unfinished Futures browser entry point is hidden from production navigation until iOS-7 is rebuilt.

**Market Grouping via `group_id`** (`FuturesMarket.group_id`):
Markets that belong to the same real-world question (e.g., "Who wins Best Picture?" with 10 nominee sub-markets on Polymarket) share a `group_id`. This powers: Discover feed dedup (one card per question, not 10), cross-source matching on category pages, calibration curve accuracy, and related-market grouping on detail pages. Set during polling (`tasks/polymarket.py`: `f"polymarket:{event.id}"` for multi-market events). `market_metadata->>'polymarket_event_id'` stores the Polymarket event ID for backfilling `group_id` on markets that were ingested before the grouping logic was added.

**Calibration Pipeline** (`routes/calibration.py`, `tasks/backfill_winners.py`):
Public endpoint at `GET /api/calibration` (1h cache) returns pre-aggregated calibration buckets across 3 sources (Kalshi, Polymarket, Odds API) with `price_moved` dimension for trading activity analysis. Uses `calibration_probability` (closing line) not `opening_probability`. Virtual market reconstruction via `(is_grouped OR eligible >= 3)`. `backfill_winners` task (every 6h) runs 7 phases: group_id backfill, null untradeable (≤2 snapshots), closing lines, calibration prices (Parts A/B/C), `is_winner`. `backfill_polymarket_history` (every 6h) fetches historical prices from Polymarket's CLOB API for outcomes with sparse snapshots. Frontend page at `/calibration` with ECE metric and "Does Trading Activity Matter?" section. MCE 2.7pp as of May 14. See `docs/architecture-reference.md` for full details.

**Rage Shake Bug Reporting** (`ios/.../Services/ShakeDetector.swift`, `ios/.../Views/BugReportView.swift`, `routes/admin.py`, `frontend/app/admin/bug-reports/`):
Shake phone or `Cmd+Shift+F` (macOS) → screenshot + app state (page, device, network, user) → `POST /api/feedback/bug-report` → admin page at `/admin/bug-reports`. Authenticated submissions use optional auth so anonymous reports still work but signed-in reports store `user_id` and `user_email` at submission time. Auto-diagnosis generates severity (P0-P3), root cause, deterministic category, and a Claude Code prompt with screenshot download command. Status flow: new → reviewed (auto on click) → actioned (added to backlog) / dismissed / fixed. Admin PATCH enqueues `send_bug_fixed_email` only when a report transitions to fixed/actioned with a resolution summary, a captured email, and no prior notification. Gmail sends multipart text+HTML through OAuth with header-injection validation.

**Push Notifications Foundation** (`routes/notifications.py`, `services/firebase_push.py`):
Device-token registration, token listing, and admin send-test are covered with Firebase mocks and admin redaction tests. The current production surface is still foundation/test tooling; do not treat it as a shipped daily notification system until a real scheduling and preference flow lands.

---

## Product Priorities (ordered)

1. **Discover feed** — Social prediction market feed with Higher/Lower games, images, LLM hooks, category filtering, daily challenges, and prediction streaks (`/discover`)
2. **Best aggregated event probabilities** — Probability-first event detail pages with multi-source charts, market maps, player props, and championship path
3. **Cross-source comparison** — Compare across ALL probability sources (sportsbooks, Kalshi, Polymarket, ESPN, stat models)
4. **Related futures** — Season futures, awards, playoff path, and series probability on every event page
5. **Team/league-level odds** — Championship grids + league market sections (series, awards, props)
6. **Multi-platform** — Full parity between web, iOS, and macOS (shared SwiftUI codebase)

**Work tracking split**: `docs/backlog.md` is the strategic backlog; GitHub Issues are the execution queue for scoped work.

## GitHub Issues + Project Workflow

`docs/backlog.md` is the strategic source of truth for priorities, rationale, and workstream context. GitHub Issues are the execution queue for scoped work packets. The GitHub Project board is status and ownership tracking.

Use this split consistently:

- Put rough ideas, long-term context, and strategic priority changes in `docs/backlog.md`.
- Create/update GitHub Issues only for work that is scoped enough to execute or delegate.
- Label issues with one or more `area:*` labels, one or more `type:*` labels, a `priority:*` label when useful, and routing labels such as `needs-agent`, `needs-user`, `blocked`, or `alert-intake`.
- When promoting a backlog item to an issue, link the issue from the backlog and include a `Backlog source` section in the issue body.
- GitHub issue `created` date is the promotion date, not necessarily the original discovery date. When porting older backlog items, preserve the original source date or backlog section date in the issue body.
- When closing a product issue, update `docs/backlog.md` in the same change if the corresponding backlog item shipped, changed, or became obsolete.
- Do not duplicate full backlog prose into issues. Issues should contain outcome, scope, acceptance criteria, verification, and a link back to the backlog.
- Alert-intake issues can be closed without backlog edits if they are stale/superseded CI failures or purely operational alerts; leave a closing comment with the reason.
- Treat the Project `In Progress` column plus the `in-progress` label as a collision-avoidance lock. When a person, Codex thread, Claude thread, or subagent starts an issue, run `python3 scripts/claim_issue.py ISSUE_NUMBER "In Progress" --owner "<thread/context>"` before editing files. This moves the Project card, adds `in-progress`, removes `needs-agent`, and comments with the active owner/context. Before starting or delegating work, check `In Progress` for overlapping files or pipeline ownership.

Canonical labels and project columns are documented in `docs/github-workflow.md`. If a user asks for "the next thing to work on," prefer open issues labeled `needs-agent`, especially `priority:p0`/`priority:p1`, before mining the whole backlog.

---

## Quota Guard System

The Odds API quota (5M/month) is the project's most constrained resource. Circuit breaker in `tasks/redis_state.py`:

| Remaining | Mode | Behavior |
|-----------|------|----------|
| >50K | Normal | All sports poll at configured intervals |
| 20K-50K | LIVE_ONLY | Only live games polled |
| <20K | FULL_STOP | All polling stopped except priority sports |

**Sport-tier polling**: Tier 1 (NBA/NHL/MLB/NFL/NCAAB): 32s live, us+us2. Tier 2 (WNBA/EPL/MLS/UCL/MMA/NCAAF): 64s, us. Tier 3 (everything else): 128s, us. Config in `SPORT_POLLING_TIERS`.

---

## Code Style

- **Python**: Type hints, Black formatting, Ruff linting
- **TypeScript**: Strict mode, interfaces in `lib/types.ts`
- **Swift**: `nonisolated struct` for models, `@MainActor` only on async methods

### Frontend Design System (MANDATORY)

The site is **light mode only**. Use design system tokens from `globals.css`: `bg-surface-card`, `text-text-primary`, `text-text-secondary`, `text-text-muted`, `border-surface-border`, `text-accent-live`, `text-accent-brand`, `text-accent-danger`. Never use raw Tailwind dark classes.

### Analytics (MANDATORY)

Every frontend page needs 3 GA4 hooks before any conditional return: `usePageTracking`, `useScrollDepth`, `useEngagementTime`.

---

## Database Schema (Key Tables)

```
events              — Games with teams, scores, EI, win_probability_sources (JSONB)
odds_snapshots      — Historical odds per bookmaker (write-time dedup)
win_prob_snapshots  — Multi-source win probability history
futures_markets     — Championship/award/prop markets (market_tier, event_id, image_url, hook_description)
futures_outcomes    — Individual outcomes within markets
teams               — Team data (ESPN colors/logos, rosters, alternate_names)
team_identity_mapping — Cross-source team identity index
user_predictions    — Higher/Lower guesses (session_id, user_id, market_id, guess, correct)
user_seen_markets   — Tracks which markets a user/session has been shown (dedup in feed)
users               — Firebase Auth users (Google + Apple Sign-In)
```

**Key columns**: `Event.win_probability_sources` (JSONB, all 6 sources), `FuturesMarket.market_tier` (1-5), `FuturesMarket.event_id` (nullable FK — game props linked to events), `FuturesMarket.llm_sport_category`, `FuturesMarket.image_url` (Pexels), `FuturesMarket.hook_description` (LLM-generated).

---

## Sport Key Architecture

`utils/sport_keys.py` is the **single source of truth** for all sport key translation maps. Imports nothing (zero circular-import risk). Key maps: `SPORT_LEAGUE_MAP` (28 entries), `KALSHI_TICKER_TO_SPORT_KEY` (~150 entries), `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` (~250 entries), `SPORT_PREFIX_TO_LLM_CATEGORY` (11 entries).

---

## Gotchas Hot List

The full gotcha catalog lives in `docs/gotchas-reference.md`. Keep this section short: only include rules that frequently prevent production incidents or wasted agent time.

1. **Alembic revision IDs must be <=32 characters** and Alembic uses psycopg2, not asyncpg.
2. **Admin endpoints require mounting** in both `main.py` and `routes/__init__.py`; admin write endpoints also need `_check_admin_secret`.
3. **`sport_keys.py` imports nothing** — it is pure shared data and must stay circular-import safe.
4. **JSONB ORM assignment can silently fail** — use SQLAlchemy Core `update()` for `Event.win_probability_sources` and similar JSONB writes.
5. **Do not mix ORM field assignment with Core SQL updates** in the same session unless you understand the flush ordering. Prefer Core SQL for both writes in task code.
6. **Async SQLAlchemy rollback expires ORM objects** — `expire_on_commit=False` does not prevent this. In async Celery loops that commit/rollback per item, copy ORM rows into scalar refs before the loop and use Core `update()` after rollback boundaries.
7. **Python 3.12+ redundant imports can cause `UnboundLocalError`** when a local import shadows a module-level name.
8. **Never delete a migration file that has already run on Heroku**; missing migration files can block every later release.
9. **GitHub Actions cannot use `secrets.*` in step-level `if`**. Put secret checks inside the shell `run` block.
10. **Vercel runs `next build`, not just TypeScript**. Always run `npm run build` for frontend changes because ESLint/rules-of-hooks failures deploy-block.
11. **The Odds API bills per `events * market_types * regions`**, not per HTTP request. Check quota behavior before widening markets or regions.
12. **Celery beat schedule test has an allowlist**. When adding scheduled tasks, update `tests/test_tasks_wiring.py`.
13. **Phase 2 prediction-market matching commits per market** to avoid deadlocks with live polling. After rollback boundaries, do not keep using live ORM objects.
14. **Kalshi `commence_time` is often resolution/close time, not game start**. Use ticker-derived dates for game matching and DataGolf/start-date fixes for golf.
15. **Do not time-window already linked prediction markets**. If `event_id` is set, trust it; time windows belong only on fallback/unlinked queries.
16. **Kalshi ticker abbreviations need explicit mapping**. Prefer ticker-derived team names over market-name abbreviations for game matching.
17. **Kalshi threshold outcomes are OVER probabilities** unless the outcome explicitly starts with "Under" or equals "No".
18. **Polymarket game events contain nested sub-markets**, not one market with many outcomes. Decompose each sub-market by `condition_id`.
19. **Polymarket midpoint can be stale in blowouts**. If spread is wide, use `lastTradePrice`; if there is no trade and no bid, skip.
20. **Polymarket API `group_id` scan is expensive**. Short-circuit when there are no null `group_id` rows before scanning the API.
21. **Calibration resolution data is fragile**. Never bulk-reset `is_winner` on resolved markets unless a confirmed alternative source can immediately re-resolve them.
22. **Completed/closed event times are not game-end times**. Use the last real source snapshot for chart domains, not backend processing timestamps.
23. **Discover independent binary markets need normalization** when displaying multi-candidate probabilities; Kalshi candidate binaries can sum well over 100%.
24. **Discover event demotion exceptions must be tier-gated**. Generic "upset"/"comeback" headlines only count as exceptional for major leagues.
25. **Dismiss propagation has blast radius**. Story keys suppress all matching markets for 14 days; semantic dismiss must ignore generic category/type/format tokens.
26. **iOS models should be `Decodable`, `nonisolated`, and use `Double` for probability fields**. Avoid class-wide `@MainActor` on view models unless necessary.
27. **iPad Stage Manager can return a background scene**. Filter for foreground-active `UIWindowScene` and key window.
28. **Extracted Swift files need their own imports and visibility fixes**. Remove duplicate class definitions after extraction.
29. **Bug reports must keep anonymous submission working** while using optional auth to capture `user_id` and storing `user_email` at submission time.
30. **Codex command policy may reject literal `git push`**. Use `git -c push.default=simple push origin master` or the explicit HTTPS remote form.
31. **Never use CREATE INDEX CONCURRENTLY in Alembic migrations** — Heroku's release phase has a timeout (~5 min). CONCURRENTLY on large tables hangs the release, causing a full outage. Create large indexes manually via psql, not in the migration chain. (Caused a May 22 outage on odds_snapshots index.)

---

## CI Test Coverage

| Test File | What It Catches | Added |
|-----------|----------------|-------|
| `tests/test_startup.py` | Import errors that crash the web dyno | Original |
| `tests/test_tasks_wiring.py` | Missing/duplicate Celery beat schedule entries | Apr 2026 |
| `tests/test_alembic.py` | Multiple heads, deleted migrations, orphaned revisions | May 7 |
| `.github/workflows/ci.yml` (frontend-build) | ESLint + TypeScript errors blocking Vercel | May 7 |
| `tests/integration/test_route_feed_scoring.py` | Feed scoring, ordering, event/futures data shape with seeded data | May 8 |
| `tests/integration/test_route_events_seeded.py` | Event detail response shape, game-markets sections, related futures | May 8 |
| `tests/integration/test_route_category_pages.py` | Weather, politics, entertainment, economics API response shapes | May 13 |
| `tests/integration/test_route_futures_browse.py` | Futures browse, categories, movers, compare response shapes | May 15 |
| `tests/integration/test_route_market_moves.py` | Market moves endpoint response shape and param validation | May 15 |
| `tests/test_politics_normalization.py` | Politics probability normalization for independent binary markets | May 15 |
| `tests/test_rate_limit.py` | Rate limiting middleware: thresholds, auth exemption, Redis fallback | May 15 |
| `backend/tests/test_*` guardrail suites | Discover scoring/personalization, matching, ingestion/quota, display, auth/preferences, calibration/identity, provider parsers, retention/taxonomy | May 17 |
| `tests/test_feed_discover_event_demotion.py` | Event demotion bypass: league-tier gating, EI thresholds, headline keyword exceptions | May 18 |
| `tests/test_feed_dismiss_propagation.py` | Story-key and group_id dismiss propagation in personalization context | May 18 |
| `tests/test_futures_highlights.py` | Election allowlist, soccer allowlist, non-major election penalty | May 18 |
| `tests/test_cross_source_matching.py` | Cross-source matching: normalization, pairing, delta computation, dedup | May 18 |
| `tests/test_personalization.py` + `tests/test_feed_discover_affinities.py` | Semantic dismiss soft penalty, generic-token guardrails, and semantic token extraction | May 18 |
| `tests/integration/test_route_auth.py` | Auth endpoint contract: Google/Apple sign-in, /me profile, validation | May 18 |
| `tests/integration/test_route_challenges.py` | Daily/friend challenge creation, acceptance, validation | May 18 |
| `tests/integration/test_route_league_futures.py` | League futures sections, sport key routing, market classification | May 18 |
| `tests/integration/test_route_notifications.py` | Device token registration, admin token management, push test | May 18 |
| `tests/integration/test_route_source_intelligence.py` | Source intelligence main + 5 audit endpoints, admin auth | May 18 |
| `tests/integration/test_route_teams.py` | Team detail page shape, 404 handling, championship path | May 18 |
| `tests/integration/test_route_user.py` | Pins, preferences, favorites, sport affinities, onboarding | May 18 |
| `tests/integration/test_route_sports.py` | Sports list, detail, hierarchy, hierarchy-detail, admin auth | May 18 |
| `tests/integration/test_route_weather.py` | All 7 weather endpoints, seeded data shapes, cross-source | May 18 |
| `tests/integration/test_route_economics.py` | Economics themes, Fed/CPI/recession seeded data, by-source | May 18 |
| `tests/integration/test_route_politics.py` | Politics themes, presidential normalization, SCOTUS/policy classification | May 18 |
| `tests/integration/test_route_entertainment.py` | Entertainment themes, empty DB defaults, HTTP methods | May 18 |
| `tests/integration/test_route_feedback.py` | Bug report submission, optional fields, minimal body | May 18 |

---

## Session Startup: Health Check

At the start of every session, run a quick production health scan (~10 seconds):

```bash
source .env.claude

# 1. Sentry — new/high-frequency errors since last session
curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://us.sentry.io/api/0/projects/alexander-bain/bainluck/issues/?query=is:unresolved&limit=5&sort=date" \
  | python3 -c "import json,sys; [print(f'  {i[\"shortId\"]:12s} {i[\"count\"]:>5s} evts  {i[\"title\"][:60]}') for i in json.load(sys.stdin)]"

# 2. Heroku — dyno status + DB connections
heroku apps:info -a bainluck 2>&1 | grep "Dynos:"
heroku pg:info -a bainluck 2>&1 | grep "Connections:"

# 3. CI — last 3 runs
gh run list --repo alexander-bain/bainluck --limit 3

# 4. Celery queue health — background queue > 50 = problem
curl -s "https://api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); q=d.get('queue_lengths',{}); bg=q.get('background',0); print(f'  Celery queues: bg={bg} rt={q.get(\"realtime\",0)}'); bg>50 and print('  ⚠️  BACKGROUND QUEUE BACKED UP — purge via POST /api/admin/celery-purge-background')"

# 5. is_winner backfill coverage — all sources should be >95%
curl -s "https://api.bainluck.com/api/admin/backfill-winners/status?secret=$ADMIN_TOKEN" \
  | python3 -c "import json,sys; [print(f'  {s[\"source\"]:12s} {round(100*s[\"has_winner\"]/max(s[\"resolved\"],1),1)}% ({s[\"has_winner\"]}/{s[\"resolved\"]})') for s in json.load(sys.stdin)['sources']]"
```

**Thresholds for immediate action:**
- Sentry issue >100 events in 24h → triage now
- Background queue >50 → purge + investigate (see `docs/backlog.md` Celery workstream)
- is_winner coverage <80% on any source → run `POST /api/admin/backfill-winners/probability-only`

**Available tools:** Heroku CLI (`heroku`), Sentry API (`$SENTRY_AUTH_TOKEN`), GitHub CLI (`gh`). All authenticated and working as of April 21, 2026.

---

## Quality Audit (mandatory practice)

When fixing ANY data quality, matching, or display issue:
1. Run audit BEFORE: `python3 scripts/audit_matching_quality.py --skip-llm --save`
2. Make fix
3. Add a check that catches this class of issue
4. Run audit AFTER: `python3 scripts/audit_matching_quality.py --skip-llm --compare --save`

---

## Parallel Work Protocol

- **Green** — iOS, docs, new test files, new utility files
- **Yellow** — Different routes, different tasks
- **Red** — Shared models, migrations, same route/task file
- **Never parallelize**: Two Alembic migrations, two sessions on same route file, two sessions on models.py

---

## Quick Reference

| What | Where |
|------|-------|
| Discover feed (default) | https://bainluck.com (also /discover) |
| Sports feed | https://bainluck.com/sports |
| Prediction stats | https://bainluck.com/discover/stats |
| Admin dashboard | https://bainluck.com/admin |
| Weather page | https://bainluck.com/weather |
| Politics page | https://bainluck.com/politics |
| Entertainment page | https://bainluck.com/entertainment |
| Economics page | https://bainluck.com/economics |
| Calibration page | https://bainluck.com/calibration |
| Calibration API | `GET /api/calibration` (public, 1h cache) |
| Backfill status | `GET /api/admin/backfill-winners/status` |
| Privacy policy | https://bainluck.com/privacy |
| Weather API | `GET /api/weather/{featured,cities,rain,events,climate,wildcards}` |
| Politics API | `GET /api/politics` |
| Entertainment API | `GET /api/entertainment` |
| League markets API | `GET /api/leagues/{sport_key}` (series, awards, props by league) |
| Hook coverage | `GET /api/admin/hook-coverage` |
| Grid health audit | `GET /api/admin/audit/all?secret=$ADMIN_TOKEN` |
| Link rate health | `GET /api/admin/prediction-markets/link-rate` |
| API docs | https://api.bainluck.com/docs |
| Backlog | `docs/backlog.md` |
| Shipped features | `docs/completed-features.md` |
| Architecture | `docs/architecture-reference.md` |
| Gotchas (full) | `docs/gotchas-reference.md` |
| Quality audit | `docs/quality-audit.md` |
| Hill-climb guide | `docs/hill-climb-guide.md` |
