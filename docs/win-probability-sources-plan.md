# Win Probability Sources — Staged Integration Plan

## Current State

OddsTracker already has two win probability sources:
1. **Betting odds** (The Odds API) — market-implied probabilities from 5-11 sportsbooks, polled every 30s during live games
2. **ESPN model** — ESPN's predictive model, polled every 60s during live games via undocumented API

### What already supports multi-source

| Layer | Current Support | Notes |
|-------|----------------|-------|
| `Event.win_probability_sources` | JSONB dict `{"espn": 0.58, "betting": 0.62}` | Already source-generic |
| `ESPNSnapshot` table | Captures ESPN history every 60s | ESPN-specific — needs generalization |
| API response | Returns `espn.probability_sources` dict | Structured but ESPN-centric |
| Frontend chart | Two lines: solid (betting) + orange dashed (ESPN) | Hardcoded for exactly 2 sources |
| Frontend types | `ESPNData`, `ESPNHistoryPoint` | ESPN-specific interfaces |

### What needs to change

1. **Snapshot table** — `ESPNSnapshot` only stores ESPN data. Adding MoneyPuck/FanGraphs/etc. each as their own table doesn't scale. Need a generic `win_prob_snapshots` table.
2. **API response** — History endpoint returns `espn_history` as a flat array. Need a source-keyed structure like `win_prob_history: { espn: [...], moneypuck: [...] }`.
3. **Frontend chart** — Hardcoded to render exactly ESPN orange dashed + betting solid. Needs to render N sources dynamically with distinct colors/styles.
4. **Scraper infrastructure** — No framework for adding new scrapers. Each source will need: HTTP client, parser, Celery task, error handling, rate limiting.
5. **Source metadata** — No registry of sources. Need to track: display name, type (model vs market), sports covered, chart color, attribution URL, polling interval, active/inactive status.

---

## Source Assessment

### Tier 1 — High value, likely feasible (start here)

| Source | Sport | Type | Data Access | Polling Feasibility | Notes |
|--------|-------|------|-------------|---------------------|-------|
| **MoneyPuck** | NHL | Model (game-state) | Public JSON/HTML | Good — structured data, moderate traffic site | Live in-game win probability charts. Likely parseable JSON endpoints behind their charts. |
| **FanGraphs** | MLB | Model (win expectancy) | Public HTML/API | Good — well-established, likely has JSON endpoints | Live scoreboard with WPA. Large site, probably tolerant of moderate polling. |
| **Pro-Football-Reference** | NFL | Model (game-state) | Public HTML + calculator endpoint | Moderate — Sports Reference sites can be aggressive about scraping | Win prob calculator endpoint may accept game state params. |
| **Inpredictable** | NBA/WNBA | Model (game-state) | Public HTML | Moderate — smaller site, be polite with rate limits | Live win probability pages. May need HTML parsing. |

### Tier 2 — Valuable but harder or narrower

| Source | Sport | Type | Data Access | Notes |
|--------|-------|------|-------------|-------|
| **Baseball Savant** | MLB | Model (Statcast) | Public HTML | MLB's official Statcast data. May have JSON feeds behind the gamefeed UI. |
| **CollegeFootballData.com** | NCAA FB | Model | Public API (free tier) | Has a documented API with auth. Win probability calculator. |
| **KenPom** | NCAA BB | Model (pregame + in-game) | Paid subscription | Excellent pregame projections. In-game data may require scraping behind paywall. |
| **Baseball-Reference** | MLB | Model (WPA) | Public HTML | Redundant with FanGraphs for MLB. Lower priority unless FanGraphs proves unreliable. |
| **Hockey-Reference** | NHL | Model | Public HTML | Redundant with MoneyPuck for NHL. |

### Tier 3 — Commercial / long-term

| Source | Sport | Type | Data Access | Notes |
|--------|-------|------|-------------|-------|
| **Opta / Stats Perform** | Soccer + multi | Model | Licensed API | Enterprise pricing. Would give soccer coverage (EPL, Champions League, etc). Best-in-class quality. |
| **CricViz WinViz** | Cricket | Model | Licensed | Niche in US but massive globally. Only worth pursuing if cricket user demand emerges. |
| **Tennis Abstract** | Tennis | Model | Public HTML | Point-by-point forecasts. Very niche, interesting for tennis detail pages. |

---

## Staged Rollout

### Phase 0: Generalize the Infrastructure (do first, before any new sources)

**Goal**: Make the data model, API, and frontend source-agnostic so adding each new source is just "write a scraper + register it."

#### Data Model

**A. New `win_prob_snapshots` table** (replaces future ESPN-specific snapshots):

```sql
CREATE TABLE win_prob_snapshots (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    source VARCHAR(30) NOT NULL,           -- "espn", "moneypuck", "fangraphs", etc.
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    home_win_probability NUMERIC(5,4),     -- 0.0000 - 1.0000
    away_win_probability NUMERIC(5,4),
    draw_probability NUMERIC(5,4),         -- For soccer
    game_state JSONB,                      -- Source-specific: {clock, period, score, ...}

    -- Indexes
    INDEX ix_winprob_event_source (event_id, source),
    INDEX ix_winprob_captured (captured_at)
);
```

This replaces `ESPNSnapshot` for new data. Existing `espn_snapshots` table can remain for historical data (or be migrated).

**Key design decisions:**
- `game_state` is JSONB rather than typed columns because each source provides different context (ESPN has clock/period, MoneyPuck has shot counts, FanGraphs has inning/outs/bases)
- `draw_probability` is a first-class column for soccer sources
- `source` is a short string key, not a FK — keeps it simple, no need for a registry table initially

**B. Source metadata** — start with a Python config dict (not a DB table). Simpler to deploy and modify:

```python
# backend/app/config/win_prob_sources.py
WIN_PROB_SOURCES = {
    "espn": {
        "display_name": "ESPN",
        "source_type": "model",        # "model" or "market"
        "sports": ["basketball_nba", "football_nfl", "baseball_mlb", "hockey_nhl", ...],
        "color": "#f97316",             # Orange (current)
        "dash_pattern": "6 3",
        "attribution_url": "https://www.espn.com",
        "poll_interval": 60,
        "active": True,
    },
    "betting": {
        "display_name": "Betting Consensus",
        "source_type": "market",
        "sports": ["*"],                # All sports
        "color": "#1e40af",             # Dark blue (current)
        "dash_pattern": None,           # Solid
        "attribution_url": None,
        "poll_interval": 30,
        "active": True,
    },
    "moneypuck": {
        "display_name": "MoneyPuck",
        "source_type": "model",
        "sports": ["hockey_nhl"],
        "color": "#10b981",             # Green
        "dash_pattern": "4 4",
        "attribution_url": "https://moneypuck.com",
        "poll_interval": 60,
        "active": False,                # Until scraper is built
    },
    # ... more sources added as they come online
}
```

**C. Extend `Event.win_probability_sources`** — already JSONB, just document the expanded schema:

```json
{
  "espn": 0.58,
  "betting": 0.62,
  "moneypuck": 0.55,
  "_meta": {
    "espn": {"updated_at": "2026-02-08T20:15:00Z", "type": "model"},
    "moneypuck": {"updated_at": "2026-02-08T20:14:30Z", "type": "model"}
  }
}
```

#### API Changes

**History endpoint** — change from:
```json
{
  "history": [...],
  "espn_history": [...]
}
```

To:
```json
{
  "history": [...],
  "win_prob_history": {
    "espn": [{"timestamp": "...", "home_probability": 0.58, "game_state": {...}}],
    "moneypuck": [{"timestamp": "...", "home_probability": 0.55, "game_state": {...}}]
  },
  "win_prob_sources": {
    "espn": {"display_name": "ESPN", "type": "model", "color": "#f97316", "snapshot_count": 45},
    "moneypuck": {"display_name": "MoneyPuck", "type": "model", "color": "#10b981", "snapshot_count": 42}
  },
  "espn_history": [...]  // Keep for backwards compatibility during transition
}
```

**Current event endpoint** — `win_probability_sources` already works, just needs more sources writing to it.

#### Frontend Changes

**Types** — add generic interfaces:

```typescript
interface WinProbHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  draw_probability?: number | null;
  game_state?: Record<string, unknown>;
}

interface WinProbSourceMeta {
  display_name: string;
  type: "model" | "market";
  color: string;
  dash_pattern?: string;
  snapshot_count: number;
}

// In EventHistoryResponse:
win_prob_history?: Record<string, WinProbHistoryPoint[]>;
win_prob_sources?: Record<string, WinProbSourceMeta>;
```

**OddsChart** — refactor from hardcoded ESPN line to dynamic source rendering:

```tsx
// Instead of one hardcoded ESPN <Line>, iterate over sources:
{Object.entries(winProbSources).map(([key, meta]) => (
  <Line
    key={key}
    dataKey={`winProb_${key}`}
    name={meta.display_name}
    stroke={meta.color}
    strokeDasharray={meta.dash_pattern}
    strokeWidth={2}
    dot={false}
    connectNulls
  />
))}
```

**Source legend** — add toggleable legend showing which sources are active, with color chips matching the chart lines. Include model vs market labels.

**Tooltip** — group by type in the tooltip:
```
Betting Consensus:  62% Lakers
ESPN Model:         58% Lakers
MoneyPuck:          55% Lakers
```

#### Migration Strategy

1. Create `win_prob_snapshots` table via Alembic
2. Backfill existing `espn_snapshots` → `win_prob_snapshots` (source="espn")
3. Update `sync_espn_live_events` to write to both tables during transition
4. Update API to read from new table
5. Update frontend to use new response format
6. Eventually drop `espn_snapshots` reads (keep table for archival)

---

### Phase 1: First New Source — MoneyPuck (NHL)

**Why first**: MoneyPuck is likely the easiest to integrate. It's a public site focused specifically on NHL analytics with visible win probability charts, suggesting structured data behind the UI. NHL is a major sport with good OddsTracker coverage.

**Tasks:**
1. Reverse-engineer MoneyPuck's data endpoints (check network tab for JSON APIs behind their charts)
2. Build `MoneyPuckService` in `backend/app/services/moneypuck_api.py`
3. Add Celery task `poll_moneypuck_win_prob` (60s interval during live NHL games)
4. Register source in config
5. Verify end-to-end: scraper → DB → API → chart with green line alongside orange ESPN + solid betting

**Estimated complexity**: Medium. Main risk is whether MoneyPuck has clean JSON endpoints or requires HTML parsing.

---

### Phase 2: MLB + NFL Coverage

**FanGraphs (MLB)**:
- Build `FanGraphsService` — parse live scoreboard for win expectancy
- FanGraphs has well-structured pages; their GameCenter likely has JSON behind it
- MLB season is long (April–October), so this gets heavy use

**Pro-Football-Reference (NFL)**:
- PFR has a documented win probability calculator
- NFL is high-value but only ~5 months of live games
- Sports Reference sites are protective of scraping — may need to be conservative with polling frequency (every 2-3 minutes instead of 60s)

---

### Phase 3: College Sports + NBA Depth

**CollegeFootballData.com (NCAA FB)**:
- Has a documented, free public API — easiest integration from a technical standpoint
- Requires API key registration
- Win probability calculator endpoint

**Inpredictable (NBA/WNBA)**:
- Adds a model-based source to complement ESPN for basketball
- Smaller site — need to be respectful with rate limits
- May require HTML parsing

**KenPom (NCAA BB)**:
- Paid subscription required — need to evaluate if worth the cost
- Excellent pregame projections could be valuable even without live data

---

### Phase 4: Commercial / International (if demand warrants)

**Opta / Stats Perform (Soccer)**:
- Enterprise licensing conversation required
- Would unlock soccer coverage (EPL, La Liga, Champions League, etc.)
- Only pursue if user analytics show soccer demand

**CricViz (Cricket)**:
- Only if cricket users appear in analytics
- Massive international market but niche in US

---

## UI/UX Considerations

### Source Type Labeling

ChatGPT's note about model vs market sources is important. Users should clearly understand what they're looking at:

- **Market-implied** (betting odds): "What the betting market thinks" — aggregated from real money positions. Tends to be well-calibrated but can react slowly to in-game events.
- **Model-based** (ESPN, MoneyPuck, FanGraphs): "What the model calculates" — derived from game state (score, time, situation). Reacts instantly to plays but can be noisy or model-specific.

**Display approach**: Use a simple label in the chart legend:
- `Betting Consensus (market)` — solid line
- `ESPN (model)` — dashed line, orange
- `MoneyPuck (model)` — dashed line, green

Models get dashed lines. Markets get solid lines. This creates a visual grammar users learn once.

### Divergence as Signal

When sources disagree significantly, that's interesting information. A "Sources Diverge" indicator when the spread between sources exceeds ~10% would surface moments where the market and models disagree — which often corresponds to controversial plays, injury news, or the market pricing in information the model doesn't have.

This is a future feature, not part of initial rollout, but worth noting in the design.

### Source Availability Badge

Not every source covers every sport. The event card or detail page should show small badges/chips indicating which probability sources are active for this event:

```
[Betting] [ESPN] [MoneyPuck]     ← NHL game, 3 sources
[Betting] [ESPN]                 ← NBA game, 2 sources
[Betting] [FanGraphs] [Savant]   ← MLB game, 3 sources
[Betting]                        ← Tennis match, 1 source
```

### Chart Complexity Management

With 3-4 sources per event, the chart could get cluttered. Mitigation:
- Default to showing betting + "best model source" for the sport
- Allow toggling additional sources on/off via legend clicks
- Keep line styles distinct (solid/dashed/dotted, different colors)
- Consider a "consensus" mode that shows average ± range

---

## Technical Considerations

### Scraping Ethics & Sustainability

1. **Respect robots.txt** — check each source before building a scraper
2. **Rate limit conservatively** — 60s polling is fine for sites like MoneyPuck; Sports Reference sites may need 120-180s
3. **Set a proper User-Agent** — identify as OddsTracker, include contact email
4. **Cache aggressively** — don't re-fetch if the source data hasn't changed
5. **Graceful degradation** — if a source goes down or blocks us, the site should still work fine with remaining sources
6. **Terms of service** — review each source's ToS before scraping. Some explicitly prohibit automated access.

### Error Isolation

Each source scraper should be fully independent:
- Separate Celery tasks (one failing doesn't affect others)
- Independent error tracking (Sentry tags by source)
- Per-source circuit breakers (if a source returns errors 5x in a row, back off for 5 minutes)

### Data Volume

At 60s polling with 3 sources during a live game:
- 3 sources × 1 snapshot/min × 180 min (3-hour game) = 540 rows per game
- Current ESPN-only: ~180 rows per game
- 3x increase is manageable, especially with the planned snapshot pruning

### Polling Strategy

Not all sources need the same polling interval:
- **Betting odds** (The Odds API): 30s — already the fastest, API-metered
- **ESPN**: 60s — current, works well
- **Model sources**: 60s default — most update on each play, not more frequently
- **PFR/Sports Reference**: 120-180s — these sites are protective

Only poll sources that are relevant to currently live sports:
```python
# Don't poll MoneyPuck if no NHL games are live
active_sports = get_live_sport_keys()
if "hockey_nhl" in active_sports:
    poll_moneypuck.delay()
```

---

## Dependency on Current Priorities

Per CLAUDE.md, the current priorities are infrastructure & reliability (tests, data retention, cleanup). This plan should slot in **after** those are addressed:

1. First: test coverage for pulse.py, highlights.py (Priority 1)
2. First: data retention policy / snapshot pruning (Priority 3)
3. Then: Phase 0 of this plan (generalize infrastructure)
4. Then: Phase 1+ (new sources, one at a time)

The data retention policy is especially relevant — adding more sources means more snapshot rows, making pruning even more important.

---

## Summary: Recommended Sequence

| Step | What | Sports Gained | Effort |
|------|------|---------------|--------|
| Phase 0 | Generalize infrastructure (DB, API, chart) | None (refactor) | Medium |
| Phase 1 | MoneyPuck | NHL depth | Small-Medium |
| Phase 2a | FanGraphs | MLB depth | Small-Medium |
| Phase 2b | Pro-Football-Reference | NFL depth | Medium |
| Phase 3a | CollegeFootballData.com | NCAA FB | Small (has API) |
| Phase 3b | Inpredictable | NBA/WNBA depth | Medium |
| Phase 4 | Opta (commercial) | Soccer breadth | Large (licensing) |

After Phase 2, every major US sport has at least 2 win probability sources (betting + model). That's the meaningful milestone.
