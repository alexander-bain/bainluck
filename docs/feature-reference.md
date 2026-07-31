# Feature Reference
## Key Features

### Excitement Index (EI) — Game Excitement Metric
1-100 score measuring how exciting a game is, based on the standard Game Excitement Index (GEI) formula from sports analytics.

**Formula:**
```
EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|
```
The raw value represents the total "distance traveled" by the win probability curve, normalized to regulation game length. A raw EI of 4.0 means the probability traveled 400% total distance.

**Typical raw EI ranges:**
- 1.0-2.0: Uneventful (blowout or minimal swings)
- 2.0-3.5: Average game
- 3.5-5.0: Exciting game
- 5.0+: Incredible drama

**Scoring:** Raw EI is mapped to 1-100 using a sqrt transform: `score = min(100, sqrt(raw_ei / 2.5) * 100)`. This maps: 0→0, ~0.16→25, ~0.63→50, ~1.41→75, 2.5→100. The time normalization ratio `T_regulation / T_actual` is capped at 2.0x to prevent games with thin data coverage from getting inflated scores. Users see the 0-100 score (percentile when available, raw otherwise).

**Multi-source aggregation:** Before EI calculation, snapshots from multiple bookmakers (5-11 per event) are aggregated into 30-second time buckets using median probability (`_aggregate_snapshots` in `excitement_index.py`). This prevents bookmaker disagreements from being counted as odds movements. Minimum 3 aggregated time buckets required.

**Metadata stored alongside score:**
- `raw_ei`: Raw EI value (e.g., 3.45)
- `lead_changes`: Number of 50% crossings
- `comeback_factor`: Lowest probability the winning team had (0-1)
- `snapshot_count`: Number of aggregated time buckets used

**Data quality levels:**
- `good` (15+ buckets): Full confidence
- `limited` (5-14 buckets): Acceptable
- `minimal` (3-4 buckets): Low confidence — stored for live games but not for completed events

**Labels:** Incredible (90+), Must-Watch (80+), Exciting (70+), Engaging (60+), Competitive (50+), Average (40+), Quiet (25+), Flat (<25)

**References:** Brian Burke (Advanced Football Analytics), Mike Beuoy (Inpredictable), FiveThirtyEight, Luke Benz (ncaahoopR)

**Files:**
- Algorithm: `backend/app/utils/excitement_index.py` (standard GEI formula)
- Legacy: `backend/app/utils/pulse.py` (backward-compat aliases: `PulseDataPoint = EIDataPoint`, `calculate_pulse = calculate_ei`)
- Frontend: `frontend/components/EIBadge.tsx` (primary), `frontend/components/PulseBadge.tsx` (deprecated wrapper)

**Admin Endpoints:**
- `GET /api/admin/ei/status` - Check calculation status
- `GET /api/admin/ei/distributions` - Score distribution analysis
- `GET /api/admin/ei/diagnosis` - Per-sport breakdown and snapshot distribution
- `POST /api/admin/ei/recalculate?limit=100` - Trigger batch recalc

**After algorithm changes:** Force-recalculate stored scores since `raw_ei` values are computed once and cached:
```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/ei/recalculate?limit=500"
curl "https://api.bainluck.com/api/admin/ei/distributions"
```

**Hall of Fame filtering:** The `ei-rankings` endpoint requires 20+ distinct minute-level time buckets. Completed events with `data_quality == "minimal"` never get a stored EI score.

**Migration note (Feb 2026):** The codebase migrated from a proprietary "Pulse" metric (weighted components: heart rate, amplitude, arrhythmia, vitals, lead changes, time weight) to the standard GEI formula. Database columns were renamed (`raw_gei` → `raw_ei`, `gei_components` → `ei_metadata`, `gei_percentiles` → `ei_percentiles`). Old events still have Pulse-format metadata in `ei_metadata` — the frontend handles both formats with optional fields. Backend serves both `"ei"` and `"pulse"` keys in API responses for backward compatibility. `/pulse` routes redirect to `/ei`.

### Highlights (Event Ranking)
Scores events 0–100 to decide what appears in the homepage Highlights section. Events need ≥30 points. This is **Level 1 (snapshot scoring)** of a multi-level ranking system — see "Ranking & Feed Evolution" in `docs/PRD.md` for the full roadmap toward the iOS feed tab.

**Key design rule:** Pre-game closeness (e.g., 51/49) doesn't award points unless there's trend evidence — the line moved ≥5% from opening, tightened from lopsided to close, or the game is starting soon. This prevents aggregation noise from surfacing uninteresting events.

**Labels:** "Upset brewing" and "Close game" are live-only. "Line moving" requires ≥15% swing from opening. "Close matchup" requires starting soon. "Championship game" and "Playoff game" show for pre-game events with matching `llm_importance`.

**Two-level scoring:**
- **Level 1** (always): Opening odds vs current (two points in time). Flags: live, close, upset, starting soon, line movement.
- **Level 2** (when snapshots available): Time-series analysis from `odds_snapshots`. Computes `TimeSeriesMetrics` (volatility RMS, lead changes, recent momentum). Only for live events with 3+ aggregated time buckets. Batch SQL query in the feed endpoint keeps it fast.

**League tier system (critical for anonymous feed quality):**
4-tier system that ensures major leagues dominate the anonymous feed:
- **Tier 1** (+20 pts): NBA, NFL, MLB, NHL, EPL, La Liga, Champions League
- **Tier 2** (+10 pts): NCAAF, NCAAB, WNBA, MLS, Bundesliga, Serie A, Ligue 1, MMA, tennis Grand Slams, golf Majors
- **Tier 3** (-5 pts): Liga MX, Brazilian Serie A, boxing — small penalty keeps them below threshold without other signals
- **Tier 4** (-45 pts): Everything not in the map (minor leagues, obscure international, regular-season tennis/golf)

**Event importance scoring:**
The `llm_importance` field on events (populated by ESPN `season.type` and LLM text classification) feeds into `compute_highlight()`:
- **Championship** (+25 pts): Championship/final games — always surfaces
- **Playoff** (+15 pts): Postseason/playoff games — significant boost
- **Exhibition** (-20 pts): Preseason/all-star — deprioritized
- **Regular season** / **None**: No change (backward compatible)

A playoff NFL game scores 30 (live+close) + 20 (tier 1) + 15 (playoff) = **65** base. A preseason NBA game scores 30 + 20 + (-20) = **30** base. A far-future playoff NBA game scores 20 (tier 1) + 15 (playoff) = **35** even without any odds signals. Championship stakes weighting gives additional multiplicative boost to teams with >10% championship odds.

**Feed sections (homepage):** Live Now → Just Happened → Upcoming → Top Markets. Completed events surface for 24h with EI-based score boost (≥80 EI: +25 pts, ≥60: +15 pts). Sections replace the earlier Highlights/Live/Upcoming/Starting Soon split.

**Feed min_score thresholds:**
- Anonymous/default: 30 (events) / 40 (futures)
- Personalized with positive affinity: 10
- "If it's wild" sports (0.1 affinity): 55 — requires genuinely unusual event, not just live+close
- "Nah" sports (0.0 affinity): **hard filtered** — skipped entirely unless championship/playoff
- My Teams (`my_teams_only=true`): 0 (show everything for followed teams)

**Feed reason text:** `backend/app/utils/feed_reasons.py` generates one-line explanations. Returns empty string when the card UI already tells the story — avoids repeating scores (finished events), odds (upcoming events), or team names visible on the card. Only adds text for genuinely insightful context: upset quantification ("Won as 35% underdog"), line movement ("Lakers odds shifted 15%"), game state ("Virtually even", "Tight game"), or timing ("Starting soon").

**Files:** `backend/app/utils/highlights.py`, `backend/app/utils/futures_highlights.py`, `backend/app/utils/feed_reasons.py`, `frontend/app/page.tsx` (feed rendering), `frontend/components/FeedCard.tsx` (card rendering)

### Odds Polling
- Live games: Every 30 seconds
- Upcoming games: Every 2-5 minutes based on proximity
- Event discovery: Every 15 minutes (beat schedule), but per-sport frequency varies by league tier via Redis gating:
  - **Tier 1** (NBA, NFL, MLB, NHL, EPL): Every 15 min
  - **Tier 2** (NCAAB, NCAAF, WNBA, MLS, MMA): Every 30 min
  - **Tier 3** (Liga MX, Boxing, Eredivisie): Every 2 hours
  - **Tier 4** (minor leagues, unlisted sports): Every 4 hours

**Key tasks:** `poll_all_odds` in `backend/app/tasks/odds_polling.py`, `_discover_events` in `backend/app/tasks/sports.py`

**Discovery tier gating:** Uses Redis keys `bainluck:last_discover:{sport_key}` with tier-based intervals from `LEAGUE_TIERS` in `highlights.py`. Same pattern as `poll_all_odds` per-sport gating. Constants in `tasks/config.py` (`DISCOVER_TIER1_INTERVAL` through `DISCOVER_TIER4_INTERVAL`). Saves ~53% of discovery API calls (~1.9M billed requests/month).

### Probability Display by Game Status
Different game statuses show different probability data to users:
- **Scheduled**: Current betting consensus (`current_odds`) with probability bar
- **Live**: Current live odds (big) + "Opened X/Y" reference from `opening_odds` (small) + probability bar
- **Completed/Closed**: Score with winner bolded + opening odds probability bar (shows what was expected) + "Opened X/Y" label + date/time for freshness context. No probability numbers — the score tells the story. Reason text only appears for genuinely insightful context (e.g., "Won as 35% underdog" for upsets), otherwise hidden.

**Opening odds** are the last pregame consensus — `_maybe_set_opening_odds` in `tasks/odds_polling.py` updates them with the cross-bookmaker average on every poll while the event is scheduled, then freezes when the game starts. Stored on the `Event` model.

**Stale bookmaker filtering**: `filter_stale_bookmaker_snapshots()` in `app/utils/odds_filtering.py` uses `_effective_time()` which prefers `valid_until` over `captured_at` (correctly handles write-time dedup). Two-layer filtering: (1) exclude bookmakers not confirmed since `commence_time`, (2) for live events, exclude bookmakers >10 min older than the freshest bookmaker. Runs for ALL non-scheduled statuses (live, completed, closed). Has 23 regression tests in `tests/test_stale_bookmaker_filter.py`.

**Frontend cross-check** (event detail page only): Compares `current_odds` against the history endpoint's latest time-bucketed consensus. If they diverge >5% for live games, trusts history. This catches cases where the backend filter doesn't fully solve the stale bookmaker problem.

**Surfaces**: EventCard (homepage) and event detail page both implement the status-based pattern. TV mode still uses raw `current_odds` (not yet updated).

**Files:** `backend/app/utils/odds_filtering.py`, `frontend/app/events/[id]/page.tsx`, `frontend/components/EventCard.tsx`

### Search
- Endpoint: `GET /api/events/search?q=celtics`
- Searches events, teams, futures markets, and outcome names while preserving broad ILIKE matching for recall
- Ranking uses query-time PostgreSQL full-text search when available: event/team names are weighted strongest, futures market names next, and outcome names after that
- No stored `ts_vector` migration exists yet; current ranking is expression-based so deploys do not rewrite large tables or require trigger maintenance
- Events ordered: Live → Upcoming → Completed, with secondary sort by weighted relevance and highlight/interestingness signals
- Returns `results` (events) and `futures` (markets) arrays
- Tag-based filtering via `tags` query parameter (uses GIN indexes when available)

### Kalshi Integration
Kalshi is a prediction market that provides structured event data including timing (when events start/end).

**Why Kalshi?** The Odds API doesn't provide `commence_time` for futures markets. Kalshi does, so futures from Kalshi will have proper start dates displayed.

**Files:**
- `backend/app/services/kalshi_api.py` - API client
- `backend/app/tasks/kalshi.py` - `poll_kalshi_markets` task (runs hourly at :45)

**Category Filter (IMPORTANT):**
Kalshi has thousands of markets (politics, economics, etc.) but we only want sports.
To stay within rate limits, we filter to specific categories.

**To change which categories are fetched**, edit this line in `backend/app/tasks/kalshi.py`:
```python
sports_categories = ["Sports", "Golf", "Football", "Basketball", "Baseball", "Hockey", "Tennis"]
```

**Rate Limiting:**
- Kalshi has strict rate limits (~10 req/sec)
- We add 0.5s delay between paginated requests
- Limited to 10 pages max per poll
- If you see 429 errors, wait a minute and try again

**Admin Endpoints:**
```bash
# Trigger a poll (queues background task, returns task_id)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/kalshi/poll"
# Response: {"status": "queued", "task_id": "abc123...", "message": "..."}

# Check task status (use task_id from above)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/kalshi/task/abc123"
# Response: {"task_id": "abc123", "state": "SUCCESS", "result": {...}}
```

**Note:** Polling runs as a background Celery task to avoid Heroku's 30-second HTTP timeout.

**Data Model:**
- Kalshi events → `futures_markets` table (source="kalshi")
- Kalshi markets → `futures_outcomes` table
- Stores bid/ask spreads: `yes_bid`, `yes_ask`, `last_price`
- Populates `commence_time` (event start) and `resolution_date` (market close)

### Polymarket Integration
Polymarket is the world's largest prediction market (~$9B valuation). Unlike Kalshi, it requires **no API key** for read access and has significantly better rate limits and sports coverage.

**Why Polymarket?** Three strategic reasons:
1. **More sports markets** — 3,294+ active sports markets with NHL and UFC partnerships, extensive soccer coverage (EPL, La Liga, UCL, Bundesliga, Serie A, MLS, etc.)
2. **Wildcard categories** — Politics, entertainment, crypto, weather, and geopolitics markets that expand Bain Luck beyond sports into "probability of anything"
3. **Built-in historical data** — `/prices-history` endpoint provides time-series data (configurable granularity) without requiring us to poll and store every snapshot

**API Architecture (4 services, only 2 needed):**
| Service | Base URL | Purpose | Auth |
|---------|----------|---------|------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Market discovery, metadata, tags, sports | **None** |
| **CLOB API** | `https://clob.polymarket.com` | Prices, order book, price history | **None** (read) |
| Data API | `https://data-api.polymarket.com` | User positions (not needed) | Yes |
| WebSocket | `wss://ws-subscriptions-clob.polymarket.com` | Real-time updates (not needed for polling) | Varies |

**Key Gamma API endpoints:**
- `GET /events` — List events with filtering (tag_id, series_id, active, closed, volume, liquidity)
- `GET /sports` — Discover supported sports/leagues with series_id and tag_id metadata
- `GET /markets` — List markets with filtering
- `GET /tags` — Discover all categories

**Key CLOB API endpoints:**
- `GET /prices-history?market={token_id}&interval=max&fidelity=60` — Historical price time series
- `GET /midpoint?token_id=X` — Mid-market price
- `GET /price?token_id=X&side=buy` — Best bid/ask

**Rate Limits:** ~1,000 calls/hour (Cloudflare throttling, much more generous than Kalshi's ~10 req/sec)

**Data Model Mapping:**
| Polymarket | Bain Luck DB |
|------------|----------------|
| Event | `FuturesMarket` (source="polymarket") |
| Event.id | `FuturesMarket.external_id` |
| Event.title | `FuturesMarket.name` |
| Event.tags | Used for `llm_sport_category` / categorization |
| Market (per outcome) | `FuturesOutcome` |
| Market.conditionId | `FuturesOutcome.external_id` |
| Market.outcomePrices[0] | `FuturesOutcome.current_probability` |
| Market.lastTradePrice | Snapshot `last_price` |
| CLOB bid/ask | `current_yes_bid` / `current_yes_ask` |

**Parsing gotcha:** `outcomes`, `outcomePrices`, and `clobTokenIds` are returned as **stringified JSON arrays** (e.g., `"[\"Yes\", \"No\"]"`) and must be parsed with `json.loads()`.

**NegRisk events:** Multi-outcome events (e.g., "NBA Championship Winner") have one binary market per team, each with Yes/No shares. Maps naturally to our FuturesOutcome model (same as Kalshi multi-market events).

**Files:**
- `backend/app/services/polymarket_api.py` — API client (Gamma + CLOB, no API key needed)
- `backend/app/tasks/polymarket.py` — Polling task with streaming pagination (batched commits, page cap warning)
- `backend/tests/test_polymarket.py` — 69 tests (tag mapping, name extraction, API parsing)

**Polling architecture:** Events are fetched page-by-page (100 per page, 0.3s delay) and processed in batches of 50 to limit memory. Categorization uses a 160+ entry tag-to-category map with fallback to `futures_categorization.py` rules + league detection. Stats include `pages_fetched`, `unique_events_seen`, and `hit_page_cap` for monitoring.

**Admin endpoints:**
```bash
# Trigger a poll
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/polymarket/poll"

# Backfill price history (fetches CLOB /prices-history for outcomes with <24 snapshots)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/polymarket/backfill-history?limit=50"

# Check task status
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/polymarket/task/{task_id}"
```

**Non-sports categories to enable:**
| Category | Examples |
|----------|---------|
| Politics | Elections, approval ratings, policy decisions |
| Entertainment | Oscars, box office, Nobel Prize, reality TV |
| Crypto | Bitcoin price targets, ETF approvals |
| Economy | Fed rate cuts, inflation, GDP |
| Tech/AI | AI benchmarks, SpaceX launches |
| Weather | Daily temperatures, natural disasters |

**Legal note:** Polymarket's ToS prohibits US persons from *trading*, but the read-only API is globally accessible. Our integration only displays probabilities — no trading functionality.

**Comparison to Kalshi:**
| Dimension | Kalshi | Polymarket |
|-----------|--------|------------|
| Auth | API key required | None (fully public) |
| Rate limits | Strict (~10 req/sec) | Generous (~1,000/hr) |
| Sports markets | Hundreds | 3,294+ |
| Price format | Cents (0-100) | Decimal (0.00-1.00) native |
| Historical prices | None (must poll) | Built-in `/prices-history` |
| Non-sports | Limited | Extensive (politics, crypto, weather, etc.) |
| Liquidity | Lower | Highest in market |

### Sport Categorization (Futures)
Futures markets are categorized using a hybrid approach: pattern matching rules + LLM fallback.

**How it works:**
1. Check `llm_sport_category` from database (cached LLM result)
2. Try prefix matching on sport key (e.g., `golf_masters` → Golf)
3. Try regex patterns on market name (e.g., "College Football Playoff" → Football)
4. Handle sport-specific awards (AL MVP → Baseball, Hart Trophy → Hockey, etc.)
5. Use athlete name detection for ambiguous markets like "US Open"
6. Fall back to LLM (GPT-4o-mini) for uncategorized markets
7. LLM always returns a category (never NULL) — defaults to "other"

**Supported categories (23):**
football, basketball, baseball, hockey, golf, tennis, soccer, mma, motorsports, boxing, cricket, rugby, aussierules, horse_racing, olympics, esports, entertainment, politics, lacrosse, chess, poker, darts, other

**Files:**
- Frontend patterns: `frontend/lib/sportCategories.ts`
- Backend patterns: `backend/app/utils/futures_categorization.py`
- LLM service: `backend/app/services/llm.py`

**To add new patterns**, edit `SPORT_PATTERNS` in `sportCategories.ts` or `futures_categorization.py`:
```python
# Backend
SPORT_PATTERNS = [
    (re.compile(r"\b(mlb|world.series)\b", re.I), "baseball"),
    (re.compile(r"\bcollege.football\b", re.I), "football"),
    # Add new patterns here...
]
```

**Important:** Pattern order matters — more specific patterns (e.g., `defensive.player.of.the.year` → football) should come before broader ones (e.g., `defensive.player` → basketball). The LLM handles everything patterns miss, so only add patterns for high-volume categories to save API costs.

**Known limitation:** Some Kalshi markets have ambiguous names like "MVP Winner?" without any sport context. These correctly categorize as "other" since there's no way to determine the sport. Improving Kalshi category pass-through would help here.

**Admin endpoints:**
```bash
# Check categorization status
curl "https://api.bainluck.com/api/admin/futures/categorization-status"

# Trigger LLM categorization (requires OPENAI_API_KEY)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/futures/categorize?limit=50"

# Dry run (preview without saving)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/futures/categorize?dry_run=true"

# View uncategorized markets (diagnostic)
curl "https://api.bainluck.com/api/admin/futures/uncategorized"

# Force-categorize all remaining via LLM
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/futures/force-categorize?limit=100"
```

**Debug endpoints:**
```bash
# See futures count by source (odds_api vs kalshi vs polymarket)
curl "https://api.bainluck.com/api/futures/debug/sources"

# See sport linking for futures
curl "https://api.bainluck.com/api/futures/debug/sport-mapping"
```

### Pinned Events & Futures
Users can pin events and futures markets they want to track closely. Pinned items appear in dedicated sections at the top of the homepage.

**Features:**
- Pin/unpin events and futures from any card or detail page
- Pinned sections appear above Highlights on homepage
- Maximum 6 pinned events + 6 pinned futures
- Works for events outside the 7-day window (e.g., Super Bowl weeks away)
- Cross-tab sync via localStorage storage events
- Separate limits for events vs futures

**Storage:**
Currently uses localStorage (no auth required). When Firebase Auth is added, this can be upgraded to database-backed storage for cross-device sync.

```javascript
// localStorage keys
bainluck_pinnedEvents    // Array of event IDs
bainluck_pinnedFutures   // Array of futures market IDs
```

### Roster Sync (ESPN + MLB Stats API)
Team rosters are synced daily using ESPN's roster endpoints and MLB Stats API for baseball. SportsDataIO was previously used but has been fully removed.

**Task:** `backend/app/tasks/roster_sync.py` (`_sync_rosters`)
- Uses ESPN `/teams/{id}/roster` endpoint for NBA, NFL, NHL, NCAAB, NCAAF, WNBA, MLS, EPL
- Uses MLB Stats API for baseball
- Beat schedule: daily at 7:00 AM UTC (`sync-rosters-daily`)
- Stores deduplicated, sorted player name list on `Team.roster_players` JSONB column

**Admin endpoints:**
```bash
# Trigger roster sync (all sports or specific)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/rosters/sync"
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/rosters/sync?sport_key=basketball_nba"

# Check task status
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/rosters/task/{task_id}"
```

### Related Futures (Event → Futures Linking)
Shows championship odds, MVP odds, award futures, upcoming game moneylines, and game-specific stat props relevant to teams playing in a specific game. The "Bigger Picture" section on event detail pages.

**Endpoint:** `GET /api/events/{id}/related-futures`

**Matching strategy (hybrid):**
1. **Name ILIKE** — Team names, short names (≥4 chars), alternate names, and roster player names matched against `FuturesOutcome.name`
2. **team_id lookup** — Supplementary matching via `FuturesOutcome.team_id` (populated by backfill task)
3. **Market name ILIKE** — Team names matched against `FuturesMarket.name` for game props where outcome names are generic ("Over 218.5")
4. Combined via OR for maximum recall

**Sport filtering (triple strategy via OR):**
- `FuturesMarket.external_id LIKE prefix%` (e.g., "basketball%")
- `FuturesMarket.llm_sport_category` matches mapped category
- `FuturesMarket.sport_id` matches compatible sport IDs

**Game-specific stat prop filtering (backend):**
Stat prop markets (e.g., "Boston at Golden State: Points") are tied to a single game. The backend filters these so they only appear on the correct event's detail page. Detection uses `_GAME_STAT_PROP_RE` (regex matching ": Points", ": Rebounds", ": Double Doubles", etc.). Matching uses `event_id` equality or ±6h temporal proximity on `commence_time`/`resolution_date`. Game moneylines (e.g., "Lakers vs Nuggets") are NOT filtered — they pass through as "Upcoming Games" context. Season-long markets (championship, MVP, awards) always show.

**Key helpers** (in `events.py`):
- `_SPORT_PREFIX_TO_LLM_CATEGORY` — Maps sport key prefixes to LLM categories
- `_GAME_STAT_PROP_RE` / `_GAME_MATCHUP_RE` — Module-level compiled regex for game-specific market detection
- `_is_stat_prop_market()` / `_stat_prop_matches_event()` — Per-request closures using event commence_time
- `_team_name_patterns()` — Builds ILIKE-safe patterns from team names
- `_escape_like()` — Escapes `%`, `_`, `\` for safe ILIKE patterns

**Frontend tier system (`effectiveTier()` in `RelatedFutures.tsx`):**
Pattern-based tier detection overrides backend `market_tier` when needed. Checked in priority order:
1. **Tier 6 (stat props)**: `STAT_PROP_PATTERNS` — ": Points", ": Rebounds", ": Double Doubles", etc. + "Team at Team: Stat" format. Displayed as Player Stats cards with semi-circular SVG gauges and headshots.
2. **Tier 5 (game markets)**: `GAME_MARKET_PATTERNS` — "vs.", "–", "Moneyline", "Game N". Displayed in dense 2-column Upcoming Games grid.
3. **Tier 3 (awards)**: `AWARD_PATTERNS` — 18 patterns including MVP, Golden Boot/Glove, Cy Young, Rookie, Player of Year, etc. Displayed as player-centric rows with headshots. Deduplicated by `normalizeName(outcome) + "::" + shortAwardLabel(market)`.
4. **Tier 4 (downgraded)**: `NOT_CHAMPIONSHIP_PATTERNS` — 14 patterns preventing non-championship markets from being hero cards (Win Totals, Make Playoffs, Seeding, Over/Under wins, Cover of NBA 2K, etc.)
5. **Tier 1-2 (backend)**: Trust backend `market_tier` for championship/conference if no pattern overrides.

**Title Comparison bar:** Uses `findBestChampionship()` which prefers markets with "championship" in the name over other tier-1 markets, preventing "Make Playoffs" (94%) from displaying instead of actual championship odds (2%).

**Cross-sport false positive prevention:** `GameMarketsGrid` verifies the market name contains the team name (or short name ≥4 chars) before displaying. Catches backend sport-filter leaks like hockey markets appearing on basketball event pages.

**Player headshots:** `PlayerHeadshot` component with priority chain: `matched_player.headshot` (direct ESPN URL from roster) → ESPN `espn_id` → Wikipedia → colored initials fallback. The `matched_player` metadata comes from `Team.roster_players` JSONB (populated by daily roster sync).

**LLM Summary:** `generate_related_futures_summary()` in `llm.py` generates a 2-3 sentence casual summary of championship/award implications using GPT-4o-mini. Cached in `LineMovementAnalysis` table with `analysis_type="related_futures"`. TTL: 2 hours for live/scheduled games, never expires for completed. Returned as `"summary": str | null` in the endpoint response. Gracefully degrades when `OPENAI_API_KEY` is not set.

**Files:**
- Backend endpoint: `backend/app/routes/events.py` (related-futures section + stat prop filtering + LLM summary caching)
- Frontend component: `frontend/components/RelatedFutures.tsx` (~1200 lines — tier detection, stat prop cards, award cards, game grid, headshots, dedup)
- LLM generation: `backend/app/services/llm.py` (`generate_related_futures_summary`)
- Team linking utility: `backend/app/utils/team_linking.py`
- Tests: `backend/tests/test_team_linking.py` (11 tests for helpers)

### ESPN Integration
ESPN's undocumented API provides team data (colors, logos) and live game info (clock, period, win probability).

**Data Enrichment:**
- **Teams**: ESPN ID, primary/secondary colors, logos (small/large), alternate names, current record
- **Events**: ESPN ID, venue, broadcast info, game clock, period, ESPN win probability, season type (→ `llm_importance`)
- **Venues**: Name, city, state, country, capacity

**Automatic Sync (Celery task `sync_espn_live_events`):**
- Runs every 60 seconds
- Auto-creates Team records with colors, logos, and alternate names from ESPN scoreboard data
- Updates live events with game clock, period, broadcast info, and win probability
- Also pre-populates team data for scheduled events (so colors/logos appear before games go live)
- Parses `season.type` (1=preseason, 2=regular, 3=postseason) and writes to `llm_importance` on both live and scheduled events (won't downgrade "championship" to "playoff")
- ESPN win probability is **only available during live games** — cannot be backfilled after a game ends
- Team colors/logos persist in the `teams` table and apply to all events (past and present) via name lookup
- Mapped sports: NBA, NCAAB, WNCAAB, NFL, NCAAF, NHL, MLB, MLS, EPL (see `ESPN_SPORT_MAPPING` in `tasks/config.py`)

**Team Logo Backfill (Celery task `backfill_team_logos`, every 6h):**
Fills in logos/colors for teams missing them by matching against ESPN's `/teams` endpoint.

**Matching strategy:** Token-overlap scoring via `_team_name_match_score()` in `espn_sync.py`. Splits both names into word sets, removes stopwords (`the`, `of`, `fc`, etc.), computes `min(overlap/words_a, overlap/words_b)`. Threshold: `> 0.5` (strictly greater). This prevents false positives from:
- Shared mascots: "Air Force Falcons" vs "Atlanta Falcons" → score 0.33 (rejected)
- Partial location: "Eastern Kentucky Colonels" vs "Kentucky Wildcats" → score 0.33 (rejected)
- State disambiguation: "South Carolina State" vs "South Carolina" → score 0.5 (rejected at strict >)

**Safety guards:**
- ESPN lookup dict excludes `et.name` (mascot-only like "Buckeyes") and `et.nickname` — only uses `display_name` and `short_name`
- `espn_id` is only set from exact dict matches or ESPN ID matches, never from fuzzy scoring — prevents bad IDs that live sync would reinforce
- Live sync `names_match()` left unchanged — its two-team gate (both home AND away must match) already prevents false positives

**Files:**
- ESPN client: `backend/app/services/espn_api.py`
- Celery sync task: `backend/app/tasks/espn_sync.py` (`_sync_espn_live_events`)
- Team lookup in API: `backend/app/routes/events.py` (`_build_team_lookup`)
- Model columns on teams: `espn_id`, `primary_color`, `secondary_color`, `logo_url_small`, `logo_url_large`, `alternate_names`, `current_record`
- Model columns on events: `espn_id`, `venue_id`, `broadcast_info`, `game_clock`, `period`, `espn_win_prob_home`, `win_probability_sources`

**Frontend display:**
- Team logos and colors on EventCard and event detail page
- Team-colored probability bar
- Broadcast info badge
- ESPN win probability badge (live games only)
- ESPN trend line on OddsChart (orange dashed line)

**Admin endpoints:**
```bash
# Sync team data from ESPN (colors, logos)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/sync-teams?sport_key=basketball_nba"

# Check team sync status
curl "https://api.bainluck.com/api/admin/espn/teams-status"

# Sync live event data (clock, period, win prob)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/sync-live-events?sport_key=basketball_nba"

# Test team name matching
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/match-teams?our_team_name=Lakers&sport_key=basketball_nba"

# Fix incorrect commence_time values using ESPN as source of truth
# (backfills completed events — the live sync task handles new ones automatically)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/fix-commence-times?limit=500"
# Check task status:
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/task/{task_id}"

# Validate existing ESPN ID assignments and clear bad matches
# (one-time cleanup — uses token-overlap scoring to detect mismatched logos)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/espn/cleanup-bad-matches"
```

### Authentication & Personalization
Firebase Auth provides Google and Apple Sign-In. The app works fully without login; auth unlocks personalization features.

**Architecture:**
- **Frontend (Google)**: Google Identity Services (GIS) OAuth popup → access token → Firebase `signInWithCredential` or backend custom token exchange
- **Frontend (Apple)**: Firebase `signInWithPopup` with `OAuthProvider('apple.com')` → Firebase handles Apple OAuth through its own verified domain (`bainluck-26a47.firebaseapp.com`). No domain verification required on `bainluck.com`.
- **Backend**: `firebase-admin` verifies ID tokens → upserts user in `users` table → returns profile
- **Auth dependencies**: `get_current_user` (required auth) and `get_optional_user` (optional auth) FastAPI dependencies
- **Anonymous-first**: All existing endpoints work without auth. Personalization is an overlay, not a gate.
- **Pin sync**: Pins migrate from localStorage to `user_pins` table on first login. localStorage continues as fallback for anonymous users.

**Safari compatibility (critical — Google 3-tier auth fallback):**
Safari ITP blocks `identitytoolkit.googleapis.com`, breaking both `signInWithCredential` AND `signInWithCustomToken`. The solution is a 3-tier fallback with fast timeouts (4s) to prevent hanging:
1. **`signInWithCredential`** (4s timeout) — works on Chrome/Firefox
2. **Backend custom token → `signInWithCustomToken`** (4s timeout) — works when only credential auth is blocked
3. **Backend-only auth** — when Firebase client SDK is fully blocked, the backend issues a PyJWT session token (HS256, 1hr TTL) signed with `ADMIN_SECRET`. Frontend stores in localStorage and uses directly as Bearer token. Backend `verify_id_token()` accepts both Firebase ID tokens and backend session tokens.

**Apple Sign-In implementation notes:**
- Uses Firebase's `signInWithPopup` with `OAuthProvider('apple.com')` — Firebase's domain is already verified with Apple, so no domain verification file is needed on `bainluck.com`.
- Requires `browserPopupRedirectResolver` in `initializeAuth` config — Firebase v10's modular SDK doesn't include it by default with custom persistence. Without it, `signInWithPopup` throws `auth/argument-error`.
- Firebase Auth module is pre-loaded via `preloadFirebaseAuth()` when the sign-in dropdown opens (UserMenu) or sign-in prompt mounts (My Stuff) to prevent popup blockers from blocking the popup due to async `import()` delay.
- After `signInWithPopup` succeeds, user state is read directly from `getCurrentFirebaseUser()` instead of relying on `onAuthStateChanged` — because first-time sign-in defers Firebase SDK loading, so the auth state listener isn't subscribed yet.
- Backend registration uses `/api/auth/google` (Firebase ID token) since `signInWithPopup` returns a Firebase token, not a raw Apple JWT.
- Apple Developer Console requires: App ID with Sign in with Apple enabled, Services ID (`com.bainluck.web`), Apple provider enabled in Firebase Console with Team ID + Key ID + .p8 private key.

**Auth persistence fix:** Firebase uses `initializeAuth` with explicit `browserLocalPersistence` (localStorage) and `browserPopupRedirectResolver` instead of the default `indexedDBLocalPersistence`. Safari ITP aggressively clears IndexedDB for cross-origin resources, causing sign-out on hard refresh.

This requires `FIREBASE_SERVICE_ACCOUNT_JSON` and `ADMIN_SECRET` on the backend.

**Key files for Safari auth (Google):**
- `frontend/lib/firebase.ts` — 3-tier Google sign-in with `withTimeout()`, `BackendAuthData` localStorage fallback, Apple `signInWithPopup` with preloaded module
- `backend/app/services/firebase_auth.py` — `create_session_token()`, `verify_session_token()`, `verify_apple_id_token()`, updated `verify_id_token()` to accept both Firebase and session tokens
- `backend/requirements.txt` — Added `PyJWT>=2.8.0`

**Key files:**
- `backend/app/services/firebase_auth.py` — Firebase Admin SDK init, token verification, `get_or_create_firebase_user`, `create_custom_token`, `verify_apple_id_token`
- `backend/app/dependencies/auth.py` — `get_current_user` / `get_optional_user` FastAPI dependencies
- `backend/app/routes/auth.py` — `POST /api/auth/google`, `POST /api/auth/google-access-token` (Safari fallback), `POST /api/auth/apple`, `GET /api/auth/me`, `GET /api/auth/status`, profile management
- `backend/app/routes/user.py` — Pin CRUD (`/api/me/pins`), team search (`/api/me/teams/search`)
- `frontend/lib/firebase.ts` — Firebase app config, GIS OAuth flow (Google), `signInWithPopup` (Apple), `preloadFirebaseAuth()`, backend fallback
- `frontend/hooks/useAuth.ts` — Reactive auth state, token management, `getCurrentFirebaseUser` for immediate state after popup
- `frontend/components/AuthProvider.tsx` — Auth context provider, wires token to API client
- `frontend/components/UserMenu.tsx` — Header sign-in button / user avatar dropdown (Preferences links to `/preferences`)
- `frontend/hooks/usePinSync.ts` — One-way localStorage → server pin migration on first login
- `frontend/app/my-stuff/page.tsx` — "My Teams" page: team-filtered feed (sign-in prompt → onboarding prompt → team feed)
- `frontend/app/preferences/page.tsx` — Settings editor (teams, interests, pinned items, account)
- `frontend/app/onboarding/page.tsx` — 5-step onboarding flow (location → follow → alma maters → sports+beyond → rivals)
- `frontend/components/OnboardingBanner.tsx` — Dismissable CTA banner for authenticated users without preferences

**Database tables:**
- `users` — Firebase UID, email, display name, photo URL
- `user_preferences` — Home location, sport affinities (JSONB), onboarding state, raw onboarding responses
- `user_favorites` — Team relationships with type (follow/local/alma_mater/rival), source, and weight
- `user_pins` — Server-side pin storage (events + futures)

**Environment variables:**
- Backend: `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON` (**required** for Safari sign-in — enables `create_custom_token` and `get_user_by_email`), `APPLE_SERVICES_ID` (enables Apple Sign-In backend verification)
- Frontend: `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

**City → Teams mapping:** ESPN's `location` field on team objects maps cities/regions/schools to teams. The `Team.location` column stores this. A static metro alias map (`METRO_ALIASES` in `user.py`, ~30 entries) groups brand names to metro areas ("New England" → "Boston", "Golden State" → "Bay Area").

**Onboarding flow (shipped):**
5-step single-page stepper at `/onboarding` — invitational (not forced), triggered by CTA banner on homepage for authenticated users who haven't completed onboarding.

Steps:
1. **"Where do you follow sports?"** — Location autocomplete → metro alias expansion → team chips (all selected by default, toggleable)
2. **"Any other favorite teams?"** — General team search, any location. Gets biggest feed boost (+0.5 follow bonus).
3. **"Any alma maters?"** — School autocomplete filtered to college sports (ncaa/wncaab keywords). Falls back to events table for teams without Team records (auto-creates them).
4. **"What do you care about?"** — Grid of sport cards + "Beyond Sports" section (Politics, Entertainment, Crypto, Economics, Tech, Weather, Geopolitics, Culture) with 4-level selector: "Love it" (1.0), "Playoffs only" (0.3), "If it's wild" (0.1), "Nah" (0.0)
5. **"Any rivals?"** — Team autocomplete, "teams you love to hate"

Endpoints:
- `POST /api/me/onboarding` — Batch save all onboarding data (deletes existing onboarding favorites, inserts new, expands sport affinities, sets `onboarding_completed=True`)
- `GET /api/me/preferences` — Returns preferences + favorites with team names/logos, compresses sport affinities to frontend keys
- `GET /api/me/teams/by-location?q=Boston` — Location search with metro alias expansion
- `GET /api/me/teams/search?q=Harvard` — Team search with events table fallback for auto-creation
- `POST /api/me/favorites` — Add single favorite (for inline editing on preferences page)
- `DELETE /api/me/favorites/{team_id}?relation_type=follow` — Remove favorite
- `PUT /api/me/preferences/sport-affinities` — Update sport affinities

**Sport affinity key mapping:** Frontend uses simple keys ("football", "basketball") that expand to backend sport_key format ("americanfootball_nfl", "americanfootball_ncaaf") via `SPORT_AFFINITY_MAPPING` in `user.py`. Non-sports categories (politics, entertainment, crypto, etc.) map to their category name directly. Compression takes the max weight when multiple backend keys map to the same frontend category. Round-trip tested: expand → compress returns original values.

**Full plan:** `docs/auth-personalization-plan.md`

**Page architecture (tabs + settings):**
| Tab/Page | URL | Purpose |
|----------|-----|---------|
| Feed | `/` | Personalized broad discovery feed (events + futures ranked by interestingness) |
| Search | `/search` | Typeahead search results |
| My Stuff | `/my-stuff` | **Team-only filtered feed** — shows only games/futures for user's followed teams |
| Preferences | `/preferences` | **Settings editor** — teams, interests, pinned items, account |

My Stuff has 3 render states:
1. **Not authenticated** → sign-in prompt (no API call)
2. **Authenticated, no teams** → onboarding prompt (links to `/onboarding`)
3. **Has teams** → calls `GET /api/feed?my_teams_only=true` with 15s refresh, wider time windows (24h recent, 7 days upcoming), no min score, no diversity enforcement

UserMenu dropdown "Preferences" links to `/preferences` (not `/my-stuff`). Bottom nav "My Stuff" links to `/my-stuff`.

### Snapshot Data Retention
Consecutive identical snapshot rows are collapsed into single rows with `captured_at` (first seen) and `valid_until` (last confirmed) timestamps. Lossless — original time series is fully reconstructable.

**Tables covered:** `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots`

**Write-time dedup:** `odds_snapshots` and `futures_odds_snapshots` had this since Jan 2026. `win_prob_snapshots` gained it in Feb 2026. Checks last row per (event, bookmaker/source) before inserting; bumps `reading_count` if value unchanged.

**Retroactive collapse:** Celery task `collapse_snapshots` processes one table per invocation. Runs daily via beat schedule (6:30/6:35/6:40 UTC for odds/winprob/futures respectively). Uses pure SQL with PostgreSQL window functions (LAG, SUM) and CTEs — zero rows loaded into Python, constant memory usage regardless of dataset size.

**Admin endpoints:**
```bash
# Trigger collapse for one table (table: odds, winprob, futures)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/snapshots/collapse?table=odds&limit=500"

# Check task status
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/snapshots/task/{task_id}"

# View current row counts
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/snapshots/stats"
```

**Files:** `backend/app/tasks/retention.py` (`_collapse_snapshots_impl`, `_collapse_table_for_partition`), `backend/app/routes/admin.py` (snapshot endpoints), `backend/tests/test_snapshot_collapse.py` (13 tests)

### Multi-Source Win Probability
The chart can display win probabilities from multiple independent sources, each as a labeled line with its own color and dash pattern.

**Architecture:**
- **Source registry**: `backend/app/config/win_prob_sources.py` — Python dict (not DB table) defining display_name, color, dash_pattern, methodology, attribution for each source
- **Generic storage**: `win_prob_snapshots` table with `source` column (replaces ESPN-specific storage for new sources)
- **Bain Luck Model**: nflfastR-inspired statistical model in `backend/app/utils/win_probability.py`. Uses normal distribution: score diff + time remaining + pregame spread. Sport-specific params: NFL base_std=13.45, NBA/NCAAB=12.0, NHL=2.5
- **Dual compute paths**: Stat model computes in both ESPN sync (every 60s) AND odds polling (every 30-60s) for redundancy
- **Frontend**: OddsChart.tsx renders N sources dynamically; legend labels link to `/events/[id]/models` detail page

**Current sources (5+1):**
- **Betting Odds** (market, solid dark line) — consensus from 5-15 sportsbooks via The Odds API
- **ESPN** (model, orange dashed) — ESPN's proprietary predictor, only available during live games
- **Bain Luck Model** (model, purple dashed) — our statistical model, attribution to nflfastR/PFR methodology
- **Kalshi** (market, green `#22c55e`) — prediction market prices from game-level Kalshi markets
- **Polymarket** (market, blue `#3b82f6`) — prediction market prices from game-level Polymarket markets
- **MLB Model** (model, source key `"mlb"`, teal `#0d9488`) — MLB Stats API live win probability (see MLB integration below)

**Supported sports for stat model:** NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL

**Adding a new source:** Add entry to `WIN_PROB_SOURCES` dict in `win_prob_sources.py`, write snapshots to `win_prob_snapshots` with the source key, and the chart/API pick it up automatically.

### MLB Stats API Integration
MLB's official Stats API (`statsapi.mlb.com`) provides live win probability data during baseball games — no API key required.

**Architecture:**
- **API client**: `backend/app/services/mlb_api.py` — `MLBAPIService` with game schedule, live game filtering, context metrics win probability, and play-by-play history
- **Sync task**: `backend/app/tasks/mlb_sync.py` — Celery task that polls live MLB games every 2 minutes, matches to our events, writes `win_prob_snapshots` with source `"mlb"`
- **Team matching**: `_name_matches()` uses suffix, mascot extraction, and containment matching (handles "Red Sox" vs "Boston Red Sox")
- **Source config**: `WIN_PROB_SOURCES["mlb"]` — display name "MLB Model", color teal `#0d9488`

**Key endpoints:**
- `GET /api/v1/schedule?sportId=1&date=YYYY-MM-DD` — Today's MLB games
- `GET /api/v1/game/{gamePk}/contextMetrics` — Live win probability (percentage, e.g., 65.3)
- `GET /api/v1/game/{gamePk}/winProbability` — Play-by-play win probability history

**Admin endpoints:**
```bash
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/mlb/sync"
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/mlb/task/{task_id}"
```

**Files:** `backend/app/services/mlb_api.py`, `backend/app/tasks/mlb_sync.py`, `backend/tests/test_mlb_api.py` (33 tests)

**ESPN matching resilience (Feb 2026):** The stat model prefers ESPN `game_clock` and `period` data but now has two fallback layers when ESPN name matching fails (common for college teams):
1. **Multi-signal ESPN matching**: ESPN ID first (set during scheduled pre-sync), then name matching, then commence_time proximity (±6h, exactly 1 candidate)
2. **Wall-clock time estimation**: `estimate_seconds_remaining_from_wall_clock()` maps elapsed wall time to game-clock time using sport-specific average durations. Less precise than ESPN clock data but sufficient for a reasonable win probability estimate.

**Known issues (Feb 2026):**
- Wall-clock estimation is approximate — it doesn't account for overtime, delays, or pace variation. ESPN clock data is always preferred when available.
- Stat model can only compute during live games — it cannot be backfilled after a game ends (requires real-time score data).
- PFR is NOT viable as a live data source (no API, ToS blocks scraping, not real-time)

**Sport key aliasing:** The Odds API uses `americanfootball_nfl`/`americanfootball_ncaaf`/`icehockey_nhl` as sport keys, but the stat model's `SPORT_PARAMS` uses `football_nfl`/`football_ncaaf`/`hockey_nhl`. The `_normalize_sport_key()` function in `win_probability.py` handles this mapping. Basketball keys match natively. If you add a new sport, make sure to test with the actual database sport key.

**Files:** `backend/app/config/win_prob_sources.py`, `backend/app/utils/win_probability.py`, `backend/tests/test_win_probability.py` (67 tests), `frontend/components/OddsChart.tsx`, `frontend/app/events/[id]/models/page.tsx`

### Prediction Market → Event Matching
Links Kalshi and Polymarket game-level markets (e.g., "NBA: Celtics at Warriors") to Event records so they appear as win probability trend lines on the OddsChart.

**Architecture:**
- **Detection**: `utils/prediction_market_matching.py` — regex-based game-level detection, fuzzy team name matching, Kalshi ticker parsing
- **Matching task**: `tasks/prediction_market_matching.py` — Celery task that links FuturesMarkets to Events and writes `win_prob_snapshots`
- **Source registry**: `win_prob_sources.py` already has Kalshi (green `#22c55e`) and Polymarket (blue `#3b82f6`) entries
- **Beat schedule**: `match_prediction_markets` runs every 15 min at `:05, :20, :35, :50`; `poll_live_prediction_markets` runs every 2 min (only fetches prices for markets linked to live events)

**Two-pass matching strategy (Phase 1):**
1. **Pass 1 — Targeted ticker scan**: Queries `FuturesMarket` by Kalshi game ticker patterns (`KXNBAGAME%`, `KXNFLGAME%`, etc.) with no limit. Uses `extract_matchup_with_ticker_fallback()` which tries name-based extraction first, then ticker abbreviation parsing, with `_find_event_by_sport_and_time()` as last resort when both fail.
2. **Pass 2 — Matchup-prioritized scan**: Two sub-queries to maximize game-level coverage: (a) markets with matchup name patterns (`% vs.%`, `% vs %`, `% – %`) get full scan budget (500), (b) remaining non-matchup markets get 20% budget (100) for edge cases. This prevents non-game markets (politics, crypto, weather — 13,000+ Polymarket markets) from crowding out game markets like "Celtics vs. Lakers". Result: 4x more game-level detections (392 vs 90) and 143 new links per run vs 0.

**Polymarket CLOB price history backfill:** When a Polymarket market is first linked to an event, the matching task automatically backfills `win_prob_snapshots` from Polymarket's `/prices-history` endpoint. This fills in the trend line from market creation (typically days before the game) rather than starting from the link timestamp. Uses fidelity=30 (30-minute intervals) for smooth chart rendering.

**Kalshi game ticker format**: `KXNBAGAME-26FEB19BOSGSW` = sport prefix + date + team abbreviations. Supported prefixes (12 sports): `kxnbagame`, `kxnflgame`, `kxnhlgame`, `kxmlbgame`, `kxncaabgame`, `kxncaafgame`, `kxwnbagame`, `kxmlsgame`, `kxsoccergame`, `kxufcfight`, `kxboxingfight`, `kxlolgame`.

**Ticker abbreviation parsing (Feb 2026):** `extract_teams_from_ticker()` parses team abbreviations directly from Kalshi tickers. Example: `KXNBAGAME-26FEB21DETCHI` → `("Pistons", "Bulls")`. This is the primary matching path for generic-named Kalshi markets like "Professional Basketball Game" which have no team names in the title. Maps 100+ abbreviations across NBA (30), NFL (~30), NHL (~32), MLB (~30) with sport-specific disambiguation suffixes. The extracted team names feed into `_find_matching_event()` for fuzzy matching against event team names. The combined function `extract_matchup_with_ticker_fallback()` is used across all 4 matching codepaths (Pass 1 link, Pass 2 link, Phase 2 snapshots, live polling snapshots).

**Sport+time fallback (last resort)**: When both name extraction and ticker abbreviation parsing fail, `get_sport_prefix_from_ticker()` maps the ticker to a sport_key prefix, then `_find_event_by_sport_and_time()` finds events within ±6 hours. Only links if exactly 1 event matches (avoids ambiguity). This fails when multiple games exist in the same sport on the same day — the ticker abbreviation parser above was built to solve this.

**Dash matchup false positive prevention**: The regex `Team A – Team B` pattern is validated by `_looks_like_team_name()` to reject false positives like "English Premier League – 2nd Place" or "The Masters - Winner".

**Both-teams matching gate**: `_score_candidates` requires BOTH `team_a` and `team_b` to fuzzy-match the event when both are available. Prevents "Thunder vs. Pistons" matching "Bulls vs. Pistons" and "Pistons vs. Bulls" matching "Georgia Southern vs South Florida Bulls".

**Sport category scoring**: `_score_candidates` adds a +5 bonus when the market's sport (from ticker prefix or `llm_sport_category` via `_SPORT_CATEGORY_TO_KEY_PREFIX`) matches the event's sport. Prevents cross-sport mislinks.

**Polymarket matchup-named outcome fallback**: `find_moneyline_outcome` handles Polymarket outcomes named with the full matchup (e.g., "Pistons vs. Bulls" instead of a single team name). Checks that both matchup teams appear in the outcome name and rejects outcomes with ":" (spreads/totals).

**Phase 1.5 stale link cleanup**: Scans ALL linked markets (not just completed/closed events) and verifies both teams match. Mislinked markets are re-linked to a better match or unlinked entirely.

**Admin endpoints:**
```bash
# Trigger matching
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/match"

# Check status (linked vs unlinked counts)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/status"

# Debug funnel (where markets drop off)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/debug?sample_size=100"

# Trigger live price poll (normally runs every 2 min automatically)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/poll-live"

# Manual link (fallback when auto-matching fails)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/link?market_id=123&event_id=456"

# Backfill Polymarket win_prob_snapshots from CLOB price history
# (fills in trend line from market creation, not just current price)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/backfill-history?market_id=130740&event_id=5541994"
```

**Files:**
- `backend/app/utils/prediction_market_matching.py` — Detection regex, fuzzy matching, team mapping, ticker parsing, ticker abbreviation extraction, ticker fragment matching (NCAAB/NCAAF), prop/spread outcome filter, `_SPORT_CATEGORY_TO_KEY_PREFIX` mapping
- `backend/app/tasks/prediction_market_matching.py` — Celery task: two-pass link + snapshot phases, both-teams gate, sport scoring, orphaned snapshot cleanup on unlink/re-link, fragment-based disambiguation, matchup-prioritized scan (Pass 2a/2b), Polymarket CLOB price history backfill on first link
- `backend/tests/test_prediction_market_matching.py` — 291 tests (ticker detection, ticker abbreviation parsing, ticker fragment matching, name building, false positives, sport prefix mapping, ticker fallback, live poll wiring, matchup-name outcome fallback, prop/spread outcome filtering, integration)

### Matching Quality Audits (LLM-based)
Three daily Celery tasks that use GPT-4o-mini to audit matching quality across the system. Each samples records, asks the LLM to verify correctness, and stores structured findings for admin review. Report-only (Phase 1) — no automatic corrections.

**Three audit types:**

1. **Canonical Key Dedup** (`audit_canonical`, 9:00 UTC) — Phase 1: checks groups sharing a `canonical_market_key` for false positives (different markets wrongly grouped). Phase 2: checks unkeyed markets for false negatives (should have a canonical key). Stores findings with `analysis_type="audit_canonical"`.

2. **Prediction Market → Event Links** (`audit_pred_market`, 9:15 UTC) — Phase 1: verifies existing `event_id` links on `FuturesMarket` records (wrong game, wrong sport). Phase 2: finds unlinked game-level markets (name contains "vs", "at", or Kalshi game ticker patterns). Stores with `analysis_type="audit_pred_market"`.

3. **Related Futures Coverage** (`audit_related_fut`, 9:30 UTC) — Phase 1: checks if major-sport events have championship futures for both teams. Phase 2: finds high-probability `FuturesOutcome` records missing `team_id`. Stores with `analysis_type="audit_related_fut"`.

**Learnings log:** Each finding includes `pattern_category` (recurring issue ID) and `suggested_rule` (deterministic fix the LLM recommends). The patterns endpoint aggregates these across runs — when a pattern appears 3+ times, it's a strong signal to add a deterministic rule.

**Storage:** Results stored in `LineMovementAnalysis` table (event_id nullable) with 7-day TTL. One row per audit run with all findings aggregated in `movement_data` JSONB.

**Admin endpoints:**
```bash
# Trigger audits (background Celery task)
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/canonical-keys?limit=50"
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/prediction-market-links?limit=50"
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/related-futures?limit=30"

# Check task status
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/task/{task_id}"

# Get latest results
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/canonical-keys"
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/prediction-market-links"
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/related-futures"

# Aggregate recurring patterns (ranked by frequency, with suggested rules)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/audit/patterns?days=30"
```

**Phase 2 graduation criteria (when to enable auto-fix):**
1. Run audits 2+ weeks, manually spot-check ≥20 findings per type
2. LLM accuracy ≥90% on verified findings
3. Pattern distribution stabilizes (same top 5-10 patterns account for >80%)
4. Prefer implementing deterministic rules from `suggested_rule` over auto-fix
5. Only auto-fix reversible actions (clear canonical key, unlink event_id, set team_id)
6. Dry run validation for 1 week before enabling real writes

**Cost:** ~$0.02/day at current volumes (~24K tokens/day). Can increase sample sizes 10x and stay under $1/day.

**Files:**
- Audit tasks: `backend/app/tasks/matching_audit.py`
- LLM helper: `backend/app/services/llm.py` (`audit_match`)
- Task wrappers: `backend/app/tasks/__init__.py`
- Admin endpoints: `backend/app/routes/admin.py` (audit section)
- Tests: `backend/tests/test_matching_audit.py` (22 tests)

### Team Auto-Creation from Events
The `_discover_events()` task (runs every 15 min) now batch-creates Team records for any teams found in events that don't yet have entries in the `teams` table. This ensures college teams (Harvard, Brown, Stanford, etc.) get Team records even without ESPN scoreboard matching. The `search_teams` endpoint also falls back to searching the events table and auto-creating Team records for matches.

### Canonical Identity System
Centralized team identity resolution replacing ad-hoc fuzzy name matching scattered across 6+ consumer modules. Three layers:

**1. Sport key translations (`utils/sport_keys.py`):**
Pure data module with 10 translation dicts mapping between Odds API keys, ESPN paths, StatPal identifiers, Kalshi tickers, LLM categories, and win-prob model keys. 7 accessor functions. Imports nothing from the codebase — zero circular-import risk. Consumer modules import dicts or functions they need.

**2. Team identity service (`services/team_identity.py`):**
Singleton `TeamIdentityService` with 5-step resolution cascade:
1. Exact match on `team_identity_mapping` by `(source, source_id, sport_key)`
2. Exact match by `(source, source_name, sport_key)`
3. Fuzzy name match on `team_identity_mapping.source_name` (any source, using `normalize_name()`)
4. Fuzzy name match on `teams.name` / `teams.alternate_names`
5. Return `None`

Auto-registration: when fuzzy matching succeeds (steps 3-4), the mapping is registered so subsequent lookups are O(1) indexed. Sources: `odds_api`, `espn`, `statpal`, `kalshi`, `polymarket`, `futures`, `mlb`.

**3. Schedule-first event creation (StatPal integration):**
StatPal creates Event records ~1 week ahead with `statpal_fixture_id` (indexed). When Odds API later discovers the same game, `_discover_events()` in `sports.py` attaches the `external_id` to the existing event instead of creating a duplicate. `commence_time_source` tracks which system set the time — StatPal's times are preferred over Odds API.

**Consumers (6 modules integrated):**
- `espn_sync.py` — registers ESPN identities on team upsert
- `statpal_sync.py` — primary lookup by `statpal_fixture_id`, registers on enrichment path
- `sports.py` — registers Odds API identities on team auto-creation and StatPal attachment
- `roster_sync.py` — identity service fast path for MLB matching before name-based fallback
- `prediction_market_matching.py` — registers market team identities on successful link
- `team_linking.py` — identity service fast path before name matching for futures outcomes

**Supplement pattern:** The identity service supplements existing fuzzy matching — it doesn't replace it. Each consumer tries the identity service first (fast, indexed), falls back to existing matching logic, then registers the mapping on fallback success.

**Backfill task** (`tasks/team_identity_backfill.py`): One-time population from ESPN IDs, team primary/alternate names, abbreviations, and Kalshi ticker abbreviations.

**Files:**
- Service: `backend/app/services/team_identity.py`
- Backfill: `backend/app/tasks/team_identity_backfill.py`
- Sport keys: `backend/app/utils/sport_keys.py`
- Model: `TeamIdentityMapping` in `backend/app/models/models.py`
- Tests: `backend/tests/test_sport_keys.py`, `backend/tests/test_team_identity.py`

### League Page — Today's Games + Market Sections

The league page (`/sport/[sport]/[league]`) is a one-stop destination for everything happening in a league.

**Today's Games**: Fetches from `/api/feed` with `sport={sport_key}`, `include_futures=false`, limit 30. Events sorted live → scheduled → completed, rendered via `FeedCard` in a 2-column grid. Section hidden when no events. Header adapts: "Live & Today's Games" when any game is live.

**Market Sections**: Fetches from `/api/leagues/{sport_key}`. Returns open futures grouped into 5 sections (series, awards, playoff_props, season_stats, novelty). Rendered via `LeagueMarketCard` in a 3-column grid with top-3 outcomes per market, probability bars for series markets, and 24h movement indicators. Championship/conference/division markets are excluded (already on the grid).

**Page layout order**: Header → Hero Tournament (golf only) → Today's Games → Evolution Chart → Championship Grid → Market Sections → Upcoming/Completed Tournaments (golf only).

**Files:**
- Backend: `backend/app/routes/league_futures.py`
- Frontend: `frontend/app/sport/[sport]/[league]/page.tsx`
- API client: `fetchLeagueMarkets()` in `frontend/lib/api.ts`

### Discover Feed Quality, Ranking, and Personalization (Updated May 17, 2026)

The Discover feed is a social prediction-market feed across sports, politics, geopolitics, economics, tech, culture, entertainment, health, and weather. It is separate from the homepage sports feed: `/discover` calls `/api/feed` with a low event mix (`event_pct=0.15`) so the most interesting public stories can beat routine games.

**Candidate pools and scoring:**
- Candidate pools include sports events, non-sports volume leaders, movement leaders, enriched markets, soon-resolving markets, and targeted postseason sports stories.
- Futures use `compute_futures_highlight()` plus quality/archetype classification in `feed_market_quality.py`. Entertainment/culture base scoring is intentionally strong enough for public-story markets, and compelling pattern recognition includes award shows, prestige/reality TV, box office, Rotten Tomatoes, Netflix/HBO/Disney+, Spotify, and Billboard markets.
- Deterministic explanations in `feed_reasons.py` generate first-page headlines from outcome data: named movers, opening-probability surprises, leader changes, source disagreement, and resolving-soon context.
- LLM hooks (`hook_description`) are helpful enrichment, not a first-page dependency.
- Async Discover LLM metadata enrichment writes compact structured metadata to `FuturesMarket.market_metadata["discover_llm"]`: topic, subtopic, entities, archetype, audience scope, salience score, junk flags, and comparison axes. The feed never calls OpenAI at request time; it only consumes cached metadata for bounded deterministic score nudges and swipe-personalization feature tokens.
- Celery schedule: `enrich_discover_llm_metadata` runs every 6h with `limit=125`; `generate_discover_comparison_candidates` runs daily and caches cross-category game-pair candidates in Redis; `evaluate_discover_with_llm` runs daily, grades the top 50 Discover futures, compares against Polymarket email highlights, and writes advisory `llm_proposed_*` rows to `discover_review_decisions`.

**Quality gates and mixer:**
- Suppresses narrow commodity/finance ladders, dated buckets, social-count filler, low-signal repeats, stale/no-movement cards, and game-market noise.
- First-page mixer caps category, archetype, and story-family overload. It preserves scores as much as possible while ensuring texture: world event, tech frontier, macro signal, culture moment, health/weather risk, sports story, and weird/absurd items.
- Production target: `boring-rate@20=0`, `ladder/bucket-rate@20=0`, `duplicate-family-rate@20=0`, `explanation-coverage@20=20/20`, `positive-archetypes@20>=5/6`, `strict-variety@20>=4/5`, `category-spread@20>=6`, max category count `<=5`.

**Observability and admin tools:**
- `backend/scripts/audit_feed_quality.py` measures precision/variety and prints top-card reasons plus missing ground-truth buckets.
- `/api/feed?debug=true&secret=...` returns debug summary, per-card quality metadata, and stage timings.
- `/api/admin/discover-quality/trace/{market_id}` explains base eligibility, candidate pool membership, scoring, rank phases, caps, and suggested fixes for one market.
- `/admin/discover-quality` combines quality metrics, timing, hook coverage, missing-ground-truth traces, engagement metrics, and ranking opportunities.
- `/api/admin/discover-engagement` summarizes first-party web/native impressions/actions by surface/category/item type and returns promote/investigate/downrank opportunity signals.
- LLM eval proposals are review-only. `llm_proposed_promote`, `llm_proposed_downrank`, and `llm_proposed_investigate` do not affect ranking unless an admin later records an accepted promote/downrank decision.

**Shareability:**
- Web Discover cards share stable UTM detail URLs with card-specific share text.
- Event/futures detail pages have dynamic metadata, generated OG image routes, shared-link landing CTAs, and `shared_link_open` analytics.
- Native context menus use the same UTM URL shape.

**Personalization layers:**
- Anonymous web/native: local category profile from impressions, opens, dismisses, likes/shares, and expands; re-ranks only within five-card windows after the first three cards.
- Authenticated/backend session ranking: existing favorites, pins, sport affinities, and roster-player matching remain primary. Recent first-party Discover interactions add tiny bounded category and feature/entity/archetype deltas; right swipe is `like` / "more like this", left swipe is `unlike` / "less like this". Repeated hard dismisses can escalate category penalty, while `unlike` stays a soft downrank. Related-dismiss behavior has two layers: shared `group_id`/story-key matches can suppress related futures, and lightweight semantic similarity applies only a `-0.30` multiplier penalty when candidate tokens match one of the 50 most recent dismisses above 0.60 Jaccard similarity.
- The engagement-derived signal is intentionally conservative and cannot override quality caps or explicit "Nah" sport filtering.

**Native parity:**
- iOS/macOS Discover has redesigned event/futures cards, redesigned Higher/Lower cards, fifth-card game cadence, native share links, local tuning menu, Firebase Analytics parity, and first-party engagement capture.

**Key files:**
- Backend: `backend/app/routes/feed.py`, `backend/app/tasks/enrich_markets.py`, `backend/app/tasks/__init__.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/app/utils/personalization.py`, `backend/scripts/audit_feed_quality.py`
- Web: `frontend/app/discover/page.tsx`, `frontend/components/DiscoverCard.tsx`, `frontend/lib/discoverInteractions.ts`, `frontend/app/admin/discover-quality/page.tsx`
- Native: `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`

### Polymarket Cross-Source Player Props

Polymarket game events contain player props (Points O/U, Assists O/U, Rebounds O/U) alongside moneylines, spreads, and totals. These are decomposed into per-sub-market FuturesMarket rows during polling, linked to events via `event_id` propagation from parent markets, and classified by the game-markets endpoint alongside Kalshi props.

**Pipeline:** `poll_polymarket_markets` (decomposition) → `match_prediction_markets` (linking + propagation) → `game-markets` endpoint (classification) → `PlayerPropsDashboard` (display).

**Key files:**
- Decomposition: `backend/app/tasks/polymarket.py` (non-neg_risk multi-market branch)
- Propagation: `backend/app/tasks/prediction_market_matching.py` (3 linking paths)
- Backfill: `backend/scripts/backfill_polymarket_submarkets.py`
- Display: `frontend/components/PlayerPropsDashboard.tsx`

**Admin endpoints:**
```bash
# Check identity mapping status (total mappings, per-source counts)
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/team-identity/status"

# Trigger one-time backfill from existing data
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/team-identity/backfill"

# Search mappings across all sources
curl "https://api.bainluck.com/api/admin/team-identity/search?q=celtics&secret=any"

# View all mappings for a specific team
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/team-identity/team/123"

# Find teams without identity mappings
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/team-identity/unmapped?sport_key=basketball_nba"

# Check task status
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/team-identity/task/{task_id}"
```

### Oscars Landing Page
Visual-first landing page for the 98th Academy Awards (March 2, 2026) at `/oscars`. Aggregates prediction market odds from Polymarket and Kalshi, enriched with movie posters and headshots from TMDB.

**Backend:** `GET /api/oscars` — Queries all Oscar-related `FuturesMarket` records, groups by 24 award categories (regex-based extraction from market names), merges nominees across sources with diacritics-aware dedup, normalizes probabilities to sum to 100%, and orders by ceremony presentation.

**Key data quality handling:**
- **Kalshi 0.5 filtering**: Illiquid binary markets default to 50/50 — filtered out as noise
- **Diacritics dedup**: `_strip_diacritics()` using `unicodedata.normalize("NFD")` ensures Skarsgård = Skarsgard
- **Name normalization**: Strips "The " prefix, colon subtitles ("F1: The Movie" → "F1"), role/film info after " - " or " for "
- **"Tie" outcome filtering**: Removed from all categories
- **Boxing false positive filter**: `_is_oscars_market()` rejects markets with " vs " (e.g., "Oscar Duarte vs...")
- **NegRisk trivia dedup**: Skips trivia markets where all outcomes share the same name
- **Cap at 10 nominees** per category after probability normalization

**Frontend:** Gold-themed page with sections:
1. **Hero** — Countdown timer to ceremony, gold gradient background
2. **Best Picture Spotlight** — Horizontal poster row from TMDB, probabilities underneath
3. **Major Awards** (6 categories) — Headshots + probability bars with source breakdown
4. **Craft Awards** (17 categories) — Compact expandable rows
5. **Trivia** — Non-award markets ("most nominations at 99th Oscars")

**TMDB integration** (`frontend/lib/tmdb.ts`): Client-side only (TMDB has CORS headers). Uses Read Access Token (v4) as Bearer auth via `NEXT_PUBLIC_TMDB_API_KEY`. Progressive enrichment — odds render first, images load async via `Promise.allSettled`. localStorage cache with 24h TTL. Graceful fallback to colored initial circles if no token or fetch fails.

**Files:**
- Backend: `backend/app/routes/oscars.py`
- Frontend: `frontend/app/oscars/page.tsx`
- TMDB client: `frontend/lib/tmdb.ts`
- Static data: `frontend/lib/oscarsData.ts`
- Types: `OscarsResponse`, `OscarsCategory`, `OscarsNominee` in `frontend/lib/types.ts`

### TV Mode (Second-Screen Experience)
Fullscreen browser-first second-screen experience at `/tv` for live games, elections, award shows, and ambient futures display. Designed for phone, iPad, and TV/monitor with a cascaded density hierarchy — every screen shows as much data as possible, bigger screens show MORE.

**Signature element:** Probability numbers "breathe" — a CSS scale/glow animation whose speed maps to the EI score. `beatMs(p) = Math.max(550, 2000 - p * 14.5)`. An EI-91 thriller visibly throbs faster than an EI-42 blowout.

**Design language:** Dark void (#09090b), team colors as the only palette, glowing numbers via text-shadow, no UI chrome in display mode, jumbotron typography.

**Cascaded density hierarchy (v4):**

| Feature | Phone | iPad | TV/Monitor |
|---------|-------|------|------------|
| Breathing probability numbers | ✅ 56px | ✅ 56px | ✅ 80px |
| Multi-source chart (Odds, ESPN, Kalshi, Polymarket) | ✅ w/ gridlines | ✅ w/ gridlines | ✅ w/ gridlines |
| Score + teams + records | ✅ | ✅ | ✅ large |
| Probability bar | ✅ | ✅ | ✅ |
| EI ring | ✅ 58px inline | ✅ 72px sidebar | ✅ 100px sidebar |
| Context (opened, line, divergence) | ✅ | ✅ sidebar | ✅ sidebar |
| Championship impact | ✅ | ✅ sidebar | ✅ sidebar |
| Related futures | ✅ up to 3 | ✅ all | ✅ all |
| Other live games panel | — | ✅ 140px | ✅ 200px |
| Trending futures panel | — | ✅ top 2 | ✅ top 4 w/ bars |
| Score-by-period breakdown | — | — | ✅ header |
| EI component breakdown | — | — | ✅ (raw_ei/lead_changes/comeback) |
| Source comparison strip | — | — | ✅ below chart |
| Sparklines in other games | — | — | ✅ |

**Two modes:**
- **Live mode**: Single event focus filling the screen. Navigate between games via arrows/swipe. Auto-switches to highest-EI game when spike >85.
- **Ambient mode**: 8-second rotation through interesting futures (championships, elections, crypto) with crossfade. Auto-activates when no live games.

**Smart behaviors:** Auto-switch on EI spikes, auto-ambient when no live games, `wakeLock` API to prevent screen dimming, keyboard shortcuts (arrows, space, F).

**Device frames:** Phone 390×780 (with notch), iPad 900×600, TV 1280×720. Scale-to-fit based on viewport width.

**iOS v2 features (documented, not built):** Lock Screen Live Activities (persistent probability bar), Dynamic Island (EI dot + score), StandBy mode (giant numbers on MagSafe charger), Apple Watch complications (probability ring), widget gallery (small/medium/large), haptic feedback mapped to EI rhythm, Siri integration ("What's the most exciting game right now?").

**Files:**
- Prototype: `tv-mode-prototype.jsx` (interactive React component with device switching, mode toggling, EI slider)
- Design plan: `docs/archive/tv-mode-plan.md` (archived 2026-07-31; full spec including iOS v2 features, implementation phases)

**Implementation plan (4 phases):**
1. Route + core layout: `/tv` route, device detection, LiveView, wire to events/history APIs
2. Multi-source + context: win probability sources, opening odds, line movement, related futures, divergence
3. Ambient + polish: futures rotation, auto-switch, keyboard shortcuts, wakeLock, fullscreen
4. Smart features: game start notifications, EI spike alerts, optional heartbeat audio, multi-game split screen

### iOS App (SwiftUI)
Native iOS app built with SwiftUI, targeting iOS 17+. Connects to the same production API as the web frontend.

**Architecture:**
- **MVVM** with `ObservableObject` view models under `ios/Bain Luck/Bain Luck/ViewModels/`
- **Async/await** networking via `APIClient.swift`
- **Firebase Auth** — Google Sign-In (via `GoogleSignIn-iOS` SPM) + Apple Sign-In (native `AuthenticationServices`)
- **Firebase Analytics** — screen views, event interactions, search queries
- **SwiftUI Navigation** — `NavigationCoordinator` with `Route` enum for deep linking
- **Shared native utilities** — clipboard, share URLs, formatting, sport labels, flag URLs, flow layout, and color helpers live under `Utilities/`

**Key features (shipped):**
- Section-based feed (Live Now, Just Happened, Upcoming, Top Markets) with 30s auto-refresh
- Filter chips (sport categories, Starting Soon, Primetime/National TV)
- Multi-source odds chart (`OddsChartView`) with period markers, All/Since Start toggle, team colors
- Event detail: score, probability bar, odds chart, related futures ("Bigger Picture"), line movement explainer, scoring plays
- Search with suggestions, EI Rankings (Hall of Fame)
- Swipe-to-pin on cards, compact pin buttons
- Apple Sign-In + Google Sign-In with Keychain token storage
- Native onboarding flow (location → teams → alma maters → sports → rivals)
- Preferences page with app icon selection
- iPad-native layout (sidebar navigation + max-width detail views). Sidebar keeps the 🍀 Bain Luck title and Calibration quick link; the unfinished Futures browser remains hidden from visible production navigation while iOS-7 is rebuilt.
- Hidden Futures browser partial rebuild: grouped category rail, polished market rows, reusable browse components, and loading/error/empty states.
- Category pages navigable from filter chips
- Skeleton loading states, haptic feedback, live tab badge
- Native Discover: swipe feedback, daily challenge, grouped market cards, resolution cards, native share sheets, first-party interaction capture, and bounded local personalization.

**Files:**
- App: `ios/Bain Luck/Bain Luck/` (108 Swift files)
- View models: `ios/Bain Luck/Bain Luck/ViewModels/`
- Utilities: `ios/Bain Luck/Bain Luck/Utilities/`
- SPM dependencies: `GoogleSignIn-iOS`, `firebase-ios-sdk`
- Not in App Store yet — TestFlight distribution

**iOS-specific gotchas:**
- `@ViewBuilder` closures cannot contain `let` bindings — use computed properties or extract to subfunctions
- `Combine` import needed for `URLSession.DataTaskPublisher` even with async/await
- Firebase `GIDSignIn` requires URL scheme in Info.plist (`REVERSED_CLIENT_ID`)
- Chart aggregation uses 60s buckets (vs web's 30s) for smoother rendering on smaller screens
- Extracted Swift files need their own imports and visibility. If a view model moves out of a view file, add `Foundation` for `localizedDescription`/string helpers and make shared helpers module-visible when needed.

### Golf Landing Page
Bespoke category page for golf at `/categories/golf`. Aggregates tournament odds from Polymarket, Kalshi, and The Odds API with rich tournament context.

**Backend:** `GET /api/golf` — Queries golf-categorized `FuturesMarket` records, groups by tournament, merges cross-source golfer odds with diacritics-aware dedup, detects current/in-progress tournaments, computes 24h biggest movers from `FuturesOddsSnapshot` history.

**Key data quality handling:**
- **Non-golf false positive filter** (`_NON_GOLF_RE`): Regex rejects esports "Masters", entertainment "Oscar" props, other-sport markets that LLM miscategorized as golf
- **Tennis ticker filter**: Strips Kalshi tennis tickers that match generic "game" patterns
- **TGL/HSBC separation**: Team Golf League and HSBC events split into own sections
- **Current event detection**: Uses DataGolf schedule dates with importance-aware tiebreaking — when multiple tournaments share the same date window, prefers Majors > Signature Events > Other tour events. `_SIGNATURE_EVENTS` set contains 12 PGA Tour elevated-purse events (Arnold Palmer Invitational, Genesis Invitational, Players Championship, Memorial, etc.). `_tournament_importance()` returns 3/2/1 for major/signature/other. Fallback heuristic also weights importance before proximity and odds movement.
- **Clean slugs** (`_clean_slug()`): Strips sponsor suffixes ("Presented By X", "Sponsored By X", "Hosted By X", "Powered By X") before generating URL slugs. Applied in tournament enrichment, `_build_current_event()`, and detail endpoint lookup. Example: "Arnold Palmer Invitational Presented By Mastercard" → `arnold-palmer-invitational`.
- **Golfer odds merging**: Cross-source dedup by `_strip_diacritics()` + name normalization
- **24h movement**: Computed from `FuturesOddsSnapshot` rows, aggregated per golfer, used for biggest movers section and sparkline charts

**Frontend sections:** Current Tournament spotlight → Major tournaments grid → Other tournaments (split into individual markets with odds trend sparklines) → Biggest Movers

**Files:**
- Backend: `backend/app/routes/golf.py`
- Frontend: `frontend/app/categories/golf/page.tsx`
- Static data: `frontend/lib/golfData.ts` (major tournaments, venues, emoji)
- Types: `GolfResponse`, `GolfTournament`, `GolfGolfer`, `GolfMover`, `GolfCurrentEvent` in `frontend/lib/types.ts`

### Politics Page
Political prediction markets dashboard at `/politics` aggregating elections, policy, and governance markets from Kalshi + Polymarket.

**Backend:** `GET /api/politics` in `routes/politics.py` — queries markets where `llm_sport_category IN ('politics', 'elections')`, filters resolved markets (≥95% binary Yes/No or past resolution_date), sorts by interestingness.

**Sub-themes:** Elections (presidential, congressional, gubernatorial), Policy & Legislation, Governance & Approval, International Politics

**Quality filters:**
- Skip binary markets with Yes/No leader ≥95% (resolved)
- Skip markets with resolution_date in the past
- Filter garbage outcomes via pattern matching
- Sort by probability decisiveness (15-85% range preferred)

**Frontend:** `app/politics/page.tsx` — purple theme (#9333ea), Capitol building hero image, election countdown timers, responsive grid layout

**Data sources:** 500+ political markets from Kalshi + Polymarket

### Entertainment Page
Entertainment and culture prediction markets dashboard at `/entertainment` covering awards, box office, music, and pop culture.

**Backend:** `GET /api/entertainment` in `routes/entertainment.py` — queries markets where `llm_sport_category IN ('entertainment', 'culture')`, same data quality filters as politics page.

**Sub-themes:** Awards Season (Oscars, Grammys, Emmys, Golden Globes), Box Office, Music & Culture, Reality TV, Celebrity & Pop Culture

**Quality filters:**
- Same pattern as politics (resolved markets, garbage outcomes, past dates)
- Additional filter for "player A/AB/L" Polymarket garbage data

**Frontend:** `app/entertainment/page.tsx` — pink/magenta theme (#ec4899), spotlight imagery, award season context

**Data sources:** 300+ entertainment markets from Kalshi + Polymarket

**Common architecture:** Both politics and entertainment pages follow the same pattern — themed backend route with quality filtering, themed frontend with SWR data fetch, probability-first UI with no gambling language, light mode only.

### Category Pages Infrastructure
Generic category landing pages at `/categories/[slug]`. Each category page shows a feed of events and futures filtered to that sport/category.

**Routes:**
- `/categories/golf` — Custom bespoke golf page (see above)
- `/categories/[slug]` — Generic category page for any sport slug (e.g., `basketball`, `soccer`)
- `/categories` — Category index page
- `/politics` — Themed politics dashboard (not under `/categories`)
- `/entertainment` — Themed entertainment dashboard (not under `/categories`)
- `/weather` — Themed weather dashboard (not under `/categories`)

**Frontend:** Generic categories use the feed API with category filtering, reusing `EventCard` and `FuturesCard` components. Themed pages (politics, entertainment, weather) have custom routes and components. iOS category pages navigate from filter chips via `SportCategoryView.swift`.

### Odds Chart Redesign
Multiple chart improvements shipped across web and iOS:
- **Period markers**: Vertical dashed lines at half/quarter/period boundaries using ESPN period data. `_compute_period_boundaries()` fills gaps even when ESPN misses early periods. Shows on both web and iOS charts.
- **Auto-zoom Y-axis**: Chart Y-axis auto-scales to the data range (±5% padding) instead of fixed 0-100%. Prevents flat-looking charts for one-sided games.
- **Smart start time**: Chart starts from first meaningful odds movement rather than hours of flat pre-game data. `_find_smart_start_time()` scans for first >2% change.
- **Team color labels**: Chart legend uses team primary colors instead of generic label colors.
- **Score diff line**: Compact score differential displayed below win probability (moved from overlay).

**Files:** `frontend/components/OddsChart.tsx`, `ios/Bain Luck/Bain Luck/Components/OddsChartView.swift`

### ESPN Box Scores
ESPN box score data is now parsed and stored on events during live sync.

**Data:** `Event.box_score_data` JSONB column stores structured box score (leaders, stats by period). Populated by `espn_sync.py` from ESPN's game summary endpoint. Used by iOS event detail for scoring context and by the line movement LLM prompt for richer game state.

**Files:** `backend/app/tasks/espn_sync.py` (box score parsing), `backend/app/models/models.py` (`box_score_data` column)

### Live Stat Prop Tracking
Box score stats (points, rebounds, assists) are tracked during live games and used to project pace toward stat prop over/under totals.

**Architecture:** During live games, `espn_sync.py` captures player stats from ESPN box scores. The iOS event detail page uses these stats to show semi-circular gauge components with current stat value vs. prop line, plus pace projections. Helps users understand if a player is on track to hit their stat prop.

**Files:** `backend/app/tasks/espn_sync.py` (stats capture), `ios/Bain Luck/Bain Luck/Views/EventDetailView.swift` (stat prop gauges)

### Duplicate Event Handling
Defense-in-depth system preventing and cleaning up duplicate events from StatPal + Odds API race conditions.

**Prevention (Layer 1):** `_find_statpal_event_for_odds_api()` in `sports.py` matches StatPal-created events (no `external_id`) to incoming Odds API events by team names + time proximity (±6h). Debug logging traces all match candidates.

**Prevention (Layer 2):** `_find_existing_event_by_teams()` in `sports.py` — broader dedup safety net that searches ALL events (not just StatPal orphans) with matching teams + time proximity (±3h). Applied in `_discover_events()`, `poll_all_odds()`, and `_poll_sport_odds()` after the StatPal check fails.

**Cleanup:** Admin endpoint `POST /api/admin/events/merge-duplicates-sql` finds orphan events (same sport, team names, time proximity, no odds snapshots) and merges them:
- Case A: Keeper has `external_id`, orphan doesn't (StatPal vs Odds API)
- Case B: Both `external_id` NULL — keep lowest ID (StatPal vs StatPal dupes)
- Absorbs metadata (statpal_fixture_id, commence_time_source, team_id, espn_id) from orphan before deleting
- Explicitly clears FK references from 4 non-CASCADE tables + nullifies `futures_markets.event_id` before delete
- March 2026 cleanup removed 5,735 orphan events (54 + 5,681)

**Monitoring:** `GET /api/admin/events/duplicates` lists current duplicate pairs.

**Files:** `backend/app/tasks/sports.py` (prevention), `backend/app/tasks/odds_polling.py` (prevention), `backend/app/routes/admin.py` (merge endpoint)

### Odds API Quota Monitoring
Passive monitoring system for The Odds API usage (5M monthly quota).

**Passive capture:** `odds_api.py` reads `x-requests-remaining` and `x-requests-used` from API response headers and stores in Redis (`bainluck:odds_api:remaining`, etc.) with 25h TTL.

**Daily activity inference:** `GET /api/admin/odds-api/daily-activity` endpoint infers API usage from snapshot creation counts per day (since the API doesn't provide historical usage data).

**Admin dashboard:** `GET /api/admin/odds-api/quota` returns current remaining/used counts from Redis.

**Files:** `backend/app/services/odds_api.py` (header capture), `backend/app/tasks/redis_state.py` (Redis storage), `backend/app/routes/admin.py` (quota + daily-activity endpoints)

### Graduated Live Scoring
Replaced flat "+30 for live" in highlight scoring with graduated scoring based on game closeness:
- Live + close (within 10%): +35
- Live + moderately close (within 20%): +30
- Live + lopsided: +20

Combined with **championship stakes weighting**: events where a team has >10% championship odds get a multiplicative boost. This was previously in the Ideas Backlog as "Futures stake weighting for event importance" — now shipped.

**Files:** `backend/app/utils/highlights.py` (`compute_highlight`)

### EI Calibration (March 2026)
The EI scaling constant was iteratively calibrated:
- Started at 8.0 (too compressed — most games clustered 30-50)
- Dropped to 4.0 (better spread but still compressed)
- Settled on **2.5** (good distribution: blowouts ~20-30, average ~40-55, exciting ~65-85, incredible 90+)
- Time normalization ratio `T_regulation / T_actual` capped at **2.0x** to prevent games with thin data coverage from getting inflated scores

**Admin diagnosis endpoint:** `GET /api/admin/ei/diagnosis` shows per-sport breakdown and snapshot distribution to help tune constants.

**Files:** `backend/app/utils/excitement_index.py` (scaling constant), `backend/app/routes/admin.py` (diagnosis endpoint)

### Probability Timeline (Futures Charts)
Time-bucketed probability history for futures markets with many outcomes (golf tournaments, championship races, awards).

**Endpoint:** `GET /api/futures/{market_id}/probability-timeline?top=10&hours=168`

**Architecture:**
- Queries `futures_odds_snapshots` for the market's outcomes
- Aggregates into time buckets (default 30 min, auto-scales based on time range)
- Returns top N outcomes by current probability, plus a "Field" remainder
- Used by `TournamentChart` component on futures detail pages

**Response shape:**
```json
{
  "market_id": 123,
  "market_name": "NBA Championship Winner 2025-26",
  "hours": 168,
  "top": 10,
  "bucket_seconds": 1800,
  "timeline": [{"timestamp": "2026-03-01T00:00:00Z", "outcomes": {"Celtics": 0.22, "Thunder": 0.18, "Field": 0.15}}],
  "outcomes": [{"id": 456, "name": "Celtics", "current_probability": 0.22}]
}
```

**Frontend:** `TournamentChart.tsx` — custom SVG multi-line chart. Fetches `top=50` from API and filters client-side to Top 5/10/All via toggle. Re-aggregates "Field" probability for non-displayed outcomes. Position-based color palette (10 colors), leader gets thicker stroke (2.5px), interactive crosshair tooltip with nearest-bucket snapping. Replaces `EvolutionView` for markets with >10 outcomes.

**Files:**
- Backend endpoint: `backend/app/routes/futures.py` (probability-timeline section)
- Frontend component: `frontend/components/TournamentChart.tsx`
- Types: `ProbabilityTimelineResponse`, `TimelineEntry`, `TimelineOutcomeMeta` in `frontend/lib/types.ts`
- API client: `fetchProbabilityTimeline()` in `frontend/lib/api.ts`

### Series Probability
Computes the probability of winning a best-of-N elimination series (NBA Playoffs, World Series, Stanley Cup) given current game-by-game win probability and series score.

**Algorithm:** Negative binomial distribution — given P(win each remaining game), compute P(reaching `games_to_win` before opponent). Handles series tied, one team leading, and clinch scenarios.

**API:** Available via `GET /api/futures/{market_id}/series-probability?team_games_won=2&opponent_games_won=1&game_win_prob=0.55&games_to_win=4`

**Files:**
- Algorithm: `backend/app/utils/series_probability.py` (`compute_series_win_prob`, `series_probability_table`)
- Tests: `backend/tests/test_series_probability.py` (37 tests)

### Market Grouping System
Groups related futures markets for unified display. Two strategies:

**1. Source hierarchy recovery:**
Markets sharing the same `canonical_market_key` from different sources (Polymarket, Kalshi, Odds API) are the same market. During Kalshi/Polymarket polling, `canonical_market_key` is now set on ingest (`tasks/kalshi.py`, `tasks/polymarket.py`) using sport+league+type+season patterns.

**2. Threshold variant detection:**
Markets differing only by a numeric threshold (e.g., "Will Bitcoin exceed $80,000?" / "$90,000?" / "$100,000?") are grouped into progressions. `_THRESHOLD_RE` regex extracts thresholds with units ($, °F, points, etc.). `detect_threshold_group()` clusters markets by normalized base name.

**Frontend components (3):**
- `CombinedMarketCard.tsx` — Cross-source comparison card showing same market from multiple sources
- `ProgressionTable.tsx` — Table of threshold variants sorted by value with probability bars
- `ThresholdGrid.tsx` — Grid display for threshold variant markets

**Admin endpoints:**
```bash
# Discover and backfill canonical market keys
curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/market-grouping/backfill-keys"

# View grouped markets
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/market-grouping/groups"

# Detect threshold progressions
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/market-grouping/thresholds"
```

**API endpoints:**
- `GET /api/futures/grouped/{canonical_key}` — Combined view of a market across sources
- `GET /api/futures/thresholds/{group_id}` — Threshold progression for a group

**Files:**
- Grouping logic: `backend/app/utils/market_grouping.py`
- API endpoints: `backend/app/routes/futures.py` (grouped/thresholds sections)
- Admin endpoints: `backend/app/routes/admin.py` (market-grouping section)
- Kalshi key assignment: `backend/app/tasks/kalshi.py`
- Polymarket key assignment: `backend/app/tasks/polymarket.py`
- Frontend: `frontend/components/CombinedMarketCard.tsx`, `ProgressionTable.tsx`, `ThresholdGrid.tsx`
- Tests: `backend/tests/test_market_grouping.py` (315 tests), `backend/tests/test_futures_timeline.py` (20 tests)

---

## Current Programs (mid-July → 2026-07-31, through Queue 289 / L2-220 / C96)

The newest layer, on top of the mid-May → mid-July programs documented below.

### Discover Cold-Load Speed Rail (#1459 / #1472 / #1475 / #1480)
`GET /api/feed` is governed by one absolute request deadline with single-owner singleflight — a
slow candidate pool degrades honestly instead of queueing behind itself (Queues 271, 277, 280).
The expensive candidate-ID pool is computed **once, user-independently**, and shared across cold
requests (Queues 278, 285); the editorial global-ID materialization was removed from the hot path
(Queue 273). Candidate-base identity is v2: **dedupe + sort only, deliberately no case/NFC
folding** (folding was rejected as collision-prone), with a truthful switch, monotonic
publication, and per-service-tier monotonicity (Queues 288, 289).

Two traps this program produced, worth carrying forward:
- A deep call-site bound turns one 500 into another 500 — bound at the boundary, not inside.
- A cache-tier test that resets the tier between write and read is testing the store *below* it.

Open residual: deployed p95 + provenance proof are still owed on #1459 / #1475. Monotonicity was
verified in Redis but **not** in L0 / process-last-good.

Native and web clients pair with this: bounded first page, classified retries, first-card
telemetry, immutable render-generation tokens, and principal-bound response caches so a
signed-out payload can never render for a signed-in principal (L2-201, L2-206 → L2-214).

### Feed Trust & Card Authority
Every cache path reports its state truthfully and every card declares its authority (Queues 275,
283; #1483, #1487). Live/upcoming concept cards **fail closed** — suppressed until they can lead
with a real result rather than rendering an empty predictive shell (L2-215); the durable fix
(backend concept-outcome inlining) is still open. The admin candidate-pool trace had drifted from
the real pool definitions; both now read a single spec (Queue 286).

### Calibration Durability
The calibration route no longer 503s under a contended precompute: publication is durable and the
route falls back to last-good while reporting the drift (Queue 272, #1459; precompute limit raised
900→1500s). A DB `statement_timeout` backstop bounds the precompute itself (Queue 274, #1479), and
resolved cohorts are immutable with recorded provenance so a later pass cannot silently re-grade
stored values (Queue 284). This is the machinery half of the calibration "done" bar — the drag was
never accuracy.

### Telemetry Consent Authority (#1453)
One emission authority replaced the scattered per-call consent checks on web, and revoke now
actually stops emission rather than only flipping a flag (L2-219, L2-220). Paired with the native
search privacy boundary, the Google access-token audience boundary (Queue 282), and Play session
anonymization (L2-214).

### Sentinel Filing Ownership
The Daily Health Check filer is marker-based and owns exactly its own issue via an evidence
fingerprint, failing closed on a cold create — this stopped the #1477 clobber (Queues 276, 279).
Coverage is now measured against a named expectation instead of inferred from absence: the
expected-event inventory + named-event recovery ledger (#1467) and the Tier-1 Polymarket event +
prop discovery ledger (#1468).

**Manus is permanently retired** (Alex ruling 2026-07-31). The browser-verification collection
really died ~07-28; C96 staged the replacement rail and #1497 is the retirement packet. No doc or
runbook should instruct reviving it, and the key must not be rotated or reactivated.

---

## Recent Programs (mid-May → mid-July 2026)

The features below shipped after the mid-May snapshot above. They map to the programs in the archived `docs/archive/execution-plan-2026-07-13.md` (P1–P7) and the six failure classes the reliability program hunts.

### Event Concept Pages + Hubs (unified tournament/card/ceremony surfaces)
Tournaments, fight cards, ceremonies, and elections render as ONE event-framed page at `/event/<domain>/<slug>` — the H1 is the *event*, not a market. This is the "event concepts + hubs" priority (#5): one matching engine and entity registry underneath, one page pattern on top.

**Backend — generic concept envelope:**
- `GET /api/event/{key}` (`backend/app/routes/event.py`) — parses `event:<domain>:<slug>` via `parse_event_key`, dispatches to a per-domain adapter, returns the generic envelope (404 if no adapter/event).
- `backend/app/utils/event_concept.py` — the domain-parameterized core: `EventConceptAdapter` Protocol, `register_adapter`/`get_adapter` registry. Envelope shape: `event / primary{kind,label,competitors,evolution_market_id} / sections / children / movers`. `primary.kind` is `"winner_field"` (golf/tennis/F1 leaderboard) or `"co_equal_list"` (UFC card, awards, elections).
- Registered adapters: golf (delegates to `routes/golf.py`; includes the fused live leaderboard `fuse_golf_live` + per-competitor history `attach_competitor_history`), tennis (`event_tennis.py`), F1 (`event_f1.py`), UFC (`event_ufc.py`), boxing (`event_boxing.py`), awards (`event_awards.py`), elections (`event_election.py`).

**Backend — competition hubs:**
- `GET /api/hub/{competition}` (`backend/app/routes/hub.py`) — config-driven landing pages. `HUB_CONFIGS` covers `mma`, `boxing`, `golf`, `tennis`, `esports`. Composes an "upcoming" rail (`_UPCOMING_LISTERS`) + futures/awards/props sections (from `league_futures.get_league_futures`). Combat hubs split fights vs props via `_PROP_CLASSIFIERS`. Whole-hub Redis cache (3 min + 24h stale fallback); 90-day horizon cap on `ufc`/`boxing` rails.

**Frontend — slug routing, canonical, redirect:**
- `frontend/app/event/[domain]/[slug]/page.tsx` — colon-free URL (L2-113, replacing the `event%3A...` form). Reconstructs the API key from the two decoded segments, injects `<link rel="canonical">` to the pretty slug, and does a client 301-equivalent `router.replace(...)` when the backend returns a prettier self-resolving slug (combat = headliner + date). Legacy-key decode-before-redirect: commit `7f9553a1`.
- Section components in `frontend/components/event/`: `EventHeader`, `MatchupsRail` (the bout grid — responsive on desktop, not horizontal scroll), `EventLeaderboard` (fused winner-field + golf-live + settled "Won"), `RaceToTitleChart`, `TwoSidedTimeline` (combat), `EventProps`, `SettledPathChart`, `FighterAvatar`, `Sparkline`, `FreshnessChip`.

See `docs/design-system.md` → "Concept-page patterns" for the visual spec.

### Settled-State System ("settled means settled")
One system-wide rule: a finished event/market/prop/chart shows its result, never a stale live affordance. Live percentages, movement pills, "Opened X/Y", and trend arrows are gated behind `!isFinished`/`!resolved` and *replaced* by a result.

- **Heroes** show winners: settled event hero renders the winner short-name + a "Won" chip instead of the giant percentage (`app/events/[id]/page.tsx`); settled futures hero (`components/FuturesHero.tsx`) shows the winning outcome + "Won"/"Resolved".
- **Cards** show results: `EventFeedCard` "FINAL" pill (hides prob chips/bar), `FuturesFeedCard` "RESOLVED" + "{winner}: {opening%} → Won", Discover `EventCard` "{winner} won". `formatFinishedDate` guards against printing a future date beside FINAL (gotcha #14).
- **Props** render GRADED: `components/PlayerPropsDashboard.tsx` states `pre|live|done|settled`; a graded `StatBox` shows actual-vs-line with a "HIT"/"MISS" pill (prefers authoritative server grade, gotcha #37), and settled-but-ungradeable shows "Resolved · grading unavailable" rather than a misleading ~100%/0% bar (L2-112).
- **Charts** show the completed journey with the domain ending at the real last-snapshot time, not the backend processing timestamp (gotcha #22/#46); settled concept chart = `components/event/SettledPathChart.tsx`.

Backend correctness guards: the Flow Sentinel `resolved_state` flow asserts settled events never render live and `completed_at >= commence_time` (gotcha #32/#46). The 439-row inverted `completed_at < commence_time` class was read-side healed (#189) and data-repaired (Queue #191).

### Flow Sentinel (reliability measurement machine)
A scripted acceptance sentinel that continuously exercises real user flows against production and auto-files evidence-packed issues on regression — the measurement half of the reliability/design program (#1078, Queue #185). This is "sentinels over Alex's eyeball": Alex exits the detection loop.

- Task: `backend/app/tasks/flow_sentinel.py` (`_run_flow_sentinel`). Celery `app.tasks.flow_sentinel`, beat `flow-sentinel-daily` at **07:10 UTC daily** (soft 840s / hard 900s), background queue.
- Runs **seven flows** against `https://api.bainluck.com`: `search_gold_set`, `duplicate_events`, `event_completeness`, `sports_feed_events` (the #1091 empty-Sports-tab guard), `resolved_state`, `chart_density`, `category_discover`. Search is scored against a frozen 25-query gold set (frozen 2026-07-06) + a canary query; files only on regressions.
- Auto-files ONE deduped GitHub issue per failing flow (`flow-sentinel-fingerprint:<sha1[:12]>` dedupe; re-runs comment instead of re-filing). Labels: `alert-intake`, `needs-agent`, an `area:*`, `priority:p1|p2` (chart_density capped at P2). Requires `GITHUB_TOKEN` on Heroku (see gotchas).
- Endpoints: `POST /api/admin/flow-sentinel/run?inline=true&file_issues=false`, `GET /api/admin/flow-sentinel/last`. Scorecard cached at `bainluck:flow_sentinel:last` (14-day TTL), surfaced on the cockpit.

### Calibration Sentinel (weekly cohort-mining detector)
Weekly detector that mines resolved-outcome cohorts for miscalibration classes and files evidence packs, so calibration regressions get caught without a human eyeballing curves (#1054).

- Task: `backend/app/tasks/calibration_sentinel.py` (`_run_calibration_sentinel`). Celery `app.tasks.calibration_sentinel`, beat `calibration-sentinel-weekly` at **Monday 06:20 UTC**.
- Mines cohorts across **category × source × series-family × structure × table-provenance**, computes **n-weighted MCE** on the RAW un-excluded population, with a new-format early-warning tier (series first seen <30d get looser floors). Builds per-cohort evidence packs (bucket cp-vs-winrate, sample rows, placeholder census), classifies overlap vs known shipped exclusions and suppresses already-explained cohorts.
- Files one deduped issue per cohort fingerprint (`sentinel-fingerprint:<sha1[:12]>`, capped at 6/run). Never writes market data (gotcha #21). Endpoint `POST /api/admin/calibration-sentinel/run` (live/backtest); cached at `bainluck:calibration_sentinel:last`.

### Admin Cockpit (Alex's leverage surface)
A read-only ops landing view that absorbs the detection loop (P5; L2-102). `GET /api/admin/cockpit` (`backend/app/routes/admin_cockpit.py`, `_check_admin_secret`, 5-min Redis cache, `?bust=1` to bypass). Four groups:
1. **Health tiles** with green/amber/red bands (`_status_from_pct`): link rate, grid health, background queue, feed boring-rate, newest-market age, plus autopilot beat tiles (`calibration_prices`, `backfill_combat_wps`). Each RED is annotated `tracked` / `artifact` / `untracked` (`_red_sub_context`) so a known red doesn't read as a fresh alarm.
2. **"Waiting on you"** — GitHub `needs-user` issues when `GITHUB_TOKEN` is set, else a static fallback list.
3. **Eval queue** — pending `llm_proposed_*` review rows + new bug-report count, with inline verdict via `/api/admin/label-pass/verdict`.
4. **Flow Sentinel scorecard** — per-flow pass/fail with tracked-issue links.

Frontend: `frontend/components/admin/AdminCockpit.tsx`. Tile/badge conventions documented in `docs/design-system.md` → "Cockpit tile conventions".

### Backfill Progress + Dedicated Cal-Price Task
The measurement + autopilot half of the calibration program (P1).

- **Backfill-progress census** (#179/#1052): `backend/app/tasks/precompute_backfill_progress.py` (`_precompute_backfill_progress`), cached at `bainluck:backfill_progress` (30-min TTL); beat `precompute-backfill-progress` every 15 min. Computes snapshot density by source × settlement month, the success cohort (settled after Jul-2 with `calibration_probability` + ≥15 history points), the `chart_density` tile (`BAR_POINTS_PER_HOUR=1.0`, the no-embarrassing-charts SLA), and the June-freeze recovery ledger (recovered / pending / permanently-aged-out per gotcha #35). Endpoint `GET /api/admin/backfill-progress`, consumed by the Flow Sentinel `chart_density` flow.
- **Dedicated cal-price task** (#180): `app.tasks.compute_calibration_prices` (`_compute_calibration_prices` in `backend/app/tasks/backfill_winners.py`), beat `compute-calibration-prices` at minutes :10 of hours 2/8/14/20. Extracted from `backfill_winners` because it budget-guarded out (`stopped_before: calibration_prices`) on every run; now monotonic + resumable per 100K batch (see gotcha: budget-guard starvation).

### End-of-Feed Grace
The Discover feed no longer stops abruptly when the pool is exhausted. `frontend/components/discover/EndOfFeedCard.tsx` renders a "You're all caught up" card with a markets-explored count, a "Refresh feed" affordance, and category-exploration links. Wired in `frontend/app/discover/page.tsx` for both the empty state and the true end (`has_more=false`), the web sibling of the #1087 thin-pool lesson.

### Settlement / Resolution Timeliness
There is no single "rapid grading" component; settled-state correctness comes from several cooperating pieces:
- Forward settlement capture at ingest: `_poll_kalshi_markets` sets `is_winner`/`resolution_source='api_settlement'` when `market.result` is present (the earliest, freshest grade; gotcha #33/#35 make this the only reliable window).
- `app.tasks.transition_event_statuses` (`espn_sync.py`, every 60s) drives scheduled→live→closed transitions; `app.tasks.mark_resolved_futures` (every 6h) marks futures resolved when `resolution_date` passes.
- `backfill_winners` + dedicated integrity siblings (`regrade_polymarket_under_signflip`, `correct_both_winner_guess_side`, etc.) backfill and correct historical grades under the resolution-authority ladder (`app/utils/resolution_authority.py`).

### The Open Golf Sprint (coverage machinery)
The golf-coverage sprint (P3, timed to The Open at Royal Birkdale) is deadline-budget + resumable-cursor work, not a hardcoded tournament list:
- `kalshi_api.py` `get_events()` carries a `deadline` budget with #969 backoff caps (429 backoff capped at 10s, never sleeps past the deadline, returns the input cursor for resume) + orjson decode + reduced page size to keep the GIL hold sub-second (gotcha #38, #995).
- `kalshi.py` `_backfill_from_settled_events` dynamically discovers all series with unresolved markets (replaced a hardcoded list); `_backfill_candlestick_snapshots` uses a resumable series cursor (gotcha #34); `_backfill_volume_only` runs a priority series list first.
- Golf-specific fixes: `_fix_golf_commence_times` (#189, gated by Redis `golf_commence_fix:enabled`, gotcha #14), `_fix_golf_round_leader_dates` (#1088, per-round dates), and the DataGolf live-poll contamination fix (commit `04e665e6`, Queue #191 — stopped one event's in-play board being blasted onto all open tour markets).

---
