# Bain Luck Architecture Improvement Plan

**Created:** March 5, 2026
**Context:** Comprehensive audit of code architecture, design system, win probability charts, and futures grouping — with implementation plan, risk assessment, and CLI prompts.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phase 1: Backend Cleanup (No Frontend Changes)](#2-phase-1-backend-cleanup)
3. [Phase 2: Frontend Design System Foundation](#3-phase-2-frontend-design-system)
4. [Phase 3: Win Probability Chart Improvements](#4-phase-3-win-probability)
5. [Phase 4: Futures Grouping System](#5-phase-4-futures-grouping)
6. [Phase 5: Design Component Migration](#6-phase-5-design-component-migration)
7. [Implementation Order & Parallelization](#7-implementation-order)
8. [Risk Registry](#8-risk-registry)
9. [Pre-Implementation Checklist (Manual Steps)](#9-pre-implementation-checklist)
10. [CLI Prompts](#10-cli-prompts)

---

## 1. Executive Summary

### What We're Fixing

**Code Architecture (Phase 1):**
- `fangraphs` source key actually points to MLB Stats API — rename to `mlb`
- Team name matching exists in 4+ incompatible implementations — consolidate to one
- Market tier detection duplicated between backend and frontend — move to backend enum
- `LineMovementAnalysis` table used as junk drawer for 4 unrelated cache types
- Dead code that could crash if triggered (`tasks/pulse.py`, `fangraphs_api.py`, `gei.py`)
- Sport configuration scattered across 3+ files

**Design System (Phase 2):**
- Install shadcn/ui as component library foundation
- Set up CSS design tokens via Tailwind v4 `@theme` directive
- Install Framer Motion for live data animations
- Create team-color theming utility using CSS variables

**Win Probability Charts (Phase 3):**
- Fix stat model not running for college games (depends on ESPN name matching)
- Build multi-participant tournament chart (golf — data already exists)
- Add series probability computation for elimination tournaments
- Handle draw probability visualization for soccer
- Remove MoneyPuck stub or build the integration

**Futures Grouping (Phase 4):**
- Recover lost Polymarket NegRisk hierarchy during ingestion
- Recover lost Kalshi event hierarchy during ingestion
- Build threshold variant detection (temperature ranges, stat lines)
- Create three display components: threshold grid, progression table, combined market card

### Why This Order

Phase 1 (backend cleanup) and Phase 2 (design system setup) can run **in parallel** — they touch completely different files. Phase 3 (charts) depends on Phase 1 (the `fangraphs` → `mlb` rename). Phase 4 (futures grouping) depends on Phase 1 (data model changes) and Phase 2 (new display components). Phase 5 (component migration) depends on Phase 2 being complete.

---

## 2. Phase 1: Backend Cleanup

### 1.1 Rename `fangraphs` Source Key to `mlb`

**Why:** The source key `"fangraphs"` in `win_prob_sources.py` and throughout the codebase actually refers to MLB Stats API data populated by `mlb_api.py` and `mlb_sync.py`. A dead `fangraphs_api.py` stub file adds to the confusion. This will cause bugs when someone tries to add actual FanGraphs support.

**Files to change:**
- `backend/app/config/win_prob_sources.py` — rename dict key from `"fangraphs"` to `"mlb"`
- `backend/app/tasks/mlb_sync.py` — change `source="fangraphs"` to `source="mlb"` in snapshot writes
- `backend/app/routes/events.py` — any references to `"fangraphs"` source key
- `frontend/components/OddsChart.tsx` — if it references `"fangraphs"` by name
- `frontend/app/events/[id]/models/page.tsx` — source display

**Migration required:** Yes — need to update existing `win_prob_snapshots` rows:
```sql
UPDATE win_prob_snapshots SET source = 'mlb' WHERE source = 'fangraphs';
```

**Backward compatibility:** The API response currently returns source metadata keyed by source name. If any iOS app version caches `"fangraphs"` as a key, it will stop seeing MLB data. **Mitigation:** Add a temporary alias in `win_prob_sources.py` that maps `"fangraphs"` → `"mlb"` for 30 days, then remove.

**Risk:** LOW. The rename is mechanical. The migration is a simple UPDATE. The alias handles backward compat.

**Tests to verify:** `backend/tests/test_mlb_api.py` (33 tests), `backend/tests/test_win_probability.py` (67 tests)

### 1.2 Delete Dead Code

**Files to delete:**
- `backend/app/services/fangraphs_api.py` — 100% stub, returns empty list, no consumers
- `backend/app/services/moneypuck_api.py` — stub only, no integration
- `backend/app/utils/gei.py` — duplicate/abandoned GEI implementation
- `backend/app/tasks/pulse.py` — references deleted column names (`raw_gei`, `gei_components`), will crash if called

**Files to clean up:**
- `backend/app/models/models.py` — remove `GEIPercentile = EIPercentile` alias if nothing imports it
- Any imports of deleted files in `__init__.py` files

**Risk:** LOW. But verify no imports reference these files first:
```bash
grep -r "fangraphs_api\|moneypuck_api\|from.*gei import\|from.*tasks.pulse import" backend/
```

### 1.3 Consolidate Team Name Matching

**Problem:** Team name normalization and matching exists in 4+ incompatible implementations:
1. `utils/team_linking.py` — `_normalize_name()` using NFD unicode normalization
2. `routes/feed.py` — `_team_name_matches()` with reserve-suffix filtering and word boundaries
3. `tasks/espn_sync.py` — `_team_name_match_score()` with token-overlap scoring
4. `services/mlb_api.py` — `_name_matches()` with suffix/mascot/containment matching
5. `services/team_identity.py` — `normalize_name()` (different signature)

A fix in one (e.g., adding reserve suffix filtering) doesn't propagate to others.

**Solution:** Create `backend/app/utils/name_normalization.py`:

```python
"""Single source of truth for team name normalization and matching.

Every module that needs to compare team names should import from here.
Do NOT create new matching functions elsewhere.
"""

import re
import unicodedata

# Reserve/youth team suffixes to strip
_RESERVE_SUFFIX_RE = re.compile(
    r'\s*(reserves?|ii|b|u\d+|youth|academy|women|w)\s*$', re.I
)

def normalize_name(name: str) -> str:
    """Canonical name normalization: lowercase, strip diacritics, strip reserve suffixes."""
    # NFD decomposition to strip accents
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Lowercase, strip whitespace
    result = ascii_name.lower().strip()
    # Strip reserve suffixes
    result = _RESERVE_SUFFIX_RE.sub("", result).strip()
    return result

def names_match(name_a: str, name_b: str) -> bool:
    """Check if two team names refer to the same team.

    Uses normalized exact match first, then token-overlap scoring.
    """
    norm_a = normalize_name(name_a)
    norm_b = normalize_name(name_b)

    # Exact match after normalization
    if norm_a == norm_b:
        return True

    # Containment (handles "Boston Celtics" vs "Celtics")
    if norm_a in norm_b or norm_b in norm_a:
        return True

    # Token overlap scoring (handles "LA Lakers" vs "Los Angeles Lakers")
    return _token_overlap_score(norm_a, norm_b) > 0.5

def _token_overlap_score(a: str, b: str) -> float:
    """Token-overlap scoring from espn_sync.py, unified here."""
    stopwords = {"the", "of", "fc", "sc", "cf", "ac", "as", "us"}
    words_a = {w for w in a.split() if w not in stopwords and len(w) > 1}
    words_b = {w for w in b.split() if w not in stopwords and len(w) > 1}
    if not words_a or not words_b:
        return 0.0
    overlap = len(words_a & words_b)
    return min(overlap / len(words_a), overlap / len(words_b))
```

**Then update consumers:**
- `utils/team_linking.py` — import `normalize_name` from `name_normalization`
- `routes/feed.py` — import `names_match` from `name_normalization`, delete `_team_name_matches`
- `tasks/espn_sync.py` — import `_token_overlap_score` from `name_normalization`
- `services/mlb_api.py` — import `names_match` from `name_normalization`
- `services/team_identity.py` — import `normalize_name` from `name_normalization`
- `utils/prediction_market_matching.py` — already imports from `team_linking`, which will now delegate

**Risk:** MEDIUM. Name matching is used everywhere — a regression here affects event linking, prediction market matching, feed filtering, roster sync, and related futures. **Mitigation:** Write 30+ tests for `name_normalization.py` covering all known edge cases from each consumer module before changing any imports. Run the full test suite after each consumer migration.

**Test cases to port from existing implementations:**
- "Air Force Falcons" vs "Atlanta Falcons" → should NOT match (token overlap 0.33)
- "Boston Celtics" vs "Celtics" → should match (containment)
- "Skarsgård" vs "Skarsgard" → should match (diacritics)
- "Boston Celtics II" vs "Boston Celtics" → should match (reserve suffix stripped)
- "LA Lakers" vs "Los Angeles Lakers" → should match (common abbrev handling — may need abbrev map)
- "South Carolina State" vs "South Carolina" → should NOT match (0.5, strict >)

### 1.4 Add Backend Market Type Enum

**Problem:** Frontend `RelatedFutures.tsx` has ~130 lines of regex patterns (`effectiveTier()`, `STAT_PROP_PATTERNS`, `GAME_MARKET_PATTERNS`, `AWARD_PATTERNS`, `NOT_CHAMPIONSHIP_PATTERNS`) that override the backend's `market_tier` integer. The frontend and backend can disagree on what a market is.

**Solution:** Add `market_type` enum to `FuturesMarket` and compute it on the backend:

```python
# In models.py or a new enum file
class MarketType(str, Enum):
    CHAMPIONSHIP = "championship"
    CONFERENCE = "conference"
    DIVISION = "division"
    AWARD = "award"
    GAME_MARKET = "game_market"
    STAT_PROP = "stat_prop"
    SEASON_STAT = "season_stat"  # Win totals, make playoffs
    OTHER = "other"
```

Add `market_type` column to `FuturesMarket`. Compute it using the same patterns currently in the frontend but centralized in `backend/app/utils/market_classification.py`. Then the frontend can trust `market_type` directly instead of re-detecting.

**Migration:** Add column, backfill from existing `market_tier` + pattern matching, then simplify frontend.

**Risk:** LOW-MEDIUM. The patterns are well-tested in the frontend already. Main risk is missing a pattern during migration. **Mitigation:** Run frontend pattern detection on all existing markets, compare with backend classification, fix discrepancies before deploying.

### 1.5 Add `group_id` and `group_type` to FuturesMarket

**Purpose:** Support futures grouping (Phase 4) by adding the schema now.

```python
# In models.py, add to FuturesMarket:
group_id = Column(String(200), index=True, nullable=True)
group_type = Column(String(50), nullable=True)  # "negrisk", "kalshi_event", "progression", "threshold", "canonical"
group_position = Column(Integer, nullable=True)  # Order within group
```

**Migration:**
```python
# Alembic migration
op.add_column('futures_markets', sa.Column('group_id', sa.String(200), nullable=True))
op.add_column('futures_markets', sa.Column('group_type', sa.String(50), nullable=True))
op.add_column('futures_markets', sa.Column('group_position', sa.Integer, nullable=True))
op.create_index('ix_futures_markets_group_id', 'futures_markets', ['group_id'])
```

**Risk:** LOW. Nullable columns, no behavioral change until Phase 4 populates them.

### 1.6 Sport Configuration Consolidation (Optional, Lower Priority)

**Problem:** Sport parameters are scattered:
- Regulation times: `utils/excitement_index.py`
- ESPN sport mappings: `tasks/config.py`
- Sport key translations: `utils/sport_keys.py`
- League tiers: `utils/highlights.py`
- Wall-clock durations: `utils/win_probability.py`

**Solution:** Create `backend/app/config/sports.py` that imports from `sport_keys.py` and consolidates:

```python
SPORT_CONFIG = {
    "basketball_nba": {
        "display_name": "NBA",
        "regulation_seconds": 2880,
        "wall_clock_seconds": 9000,
        "league_tier": 1,
        "espn_path": "basketball/nba",
        "periods": 4,
        "period_name": "quarter",
    },
    # ... all sports
}
```

**Risk:** LOW but tedious. Many files import sport constants from their current locations. Can be done incrementally.

---

## 3. Phase 2: Frontend Design System

### 2.1 Install shadcn/ui

**Why:** shadcn/ui gives you professional-looking components that you own (files in your repo, not an npm dependency). Built on Radix UI (accessibility) + Tailwind (styling). CSS variable theming is perfect for team colors.

**Steps:**
1. Run `npx shadcn-ui@latest init` in `frontend/`
2. Select: TypeScript, New York style, CSS variables, `@/components/ui` path
3. Install specific components as needed: `npx shadcn-ui@latest add card badge button`

**What this gives you:** `components/ui/` folder with Card, Badge, Button, etc. Each is a file you can modify.

### 2.2 Set Up Design Tokens

Create `frontend/app/design-tokens.css` (imported in `globals.css`):

```css
@layer base {
  :root {
    /* STATUS COLORS */
    --color-status-live: 239 68 68;      /* red-500 */
    --color-status-upcoming: 139 92 246;  /* violet-500 */
    --color-status-completed: 107 114 128; /* gray-500 */
    --color-status-closed: 75 85 99;      /* gray-600 */

    /* EI SEVERITY */
    --color-ei-incredible: 239 68 68;     /* red */
    --color-ei-exciting: 249 115 22;      /* orange */
    --color-ei-average: 234 179 8;        /* yellow */
    --color-ei-quiet: 107 114 128;        /* gray */

    /* BRAND */
    --color-brand-primary: 15 23 42;      /* slate-900 */
    --color-brand-accent: 59 130 246;     /* blue-500 */

    /* DYNAMIC TEAM COLORS (set per-component via style prop) */
    --team-home-primary: 107 114 128;
    --team-home-secondary: 156 163 175;
    --team-away-primary: 107 114 128;
    --team-away-secondary: 156 163 175;

    /* SPACING SCALE */
    --space-xs: 0.25rem;
    --space-sm: 0.5rem;
    --space-md: 1rem;
    --space-lg: 1.5rem;
    --space-xl: 2rem;

    /* ANIMATION DURATIONS */
    --duration-fast: 150ms;
    --duration-normal: 300ms;
    --duration-slow: 500ms;
  }

  /* DARK MODE */
  .dark {
    --color-brand-primary: 241 245 249;   /* slate-100 */
  }
}
```

### 2.3 Install Framer Motion

```bash
cd frontend && npm install framer-motion
```

**Use for:**
- Probability number transitions (animatePresence when odds change)
- EI "breathing" ring animation
- Card entrance/exit animations
- Live badge pulse

### 2.4 Create Team Color Theming Utility

Create `frontend/lib/teamColors.ts`:

```typescript
/**
 * Apply team colors as CSS variables on a container element.
 * Components inside will automatically pick up --team-home-primary etc.
 */
export function teamColorStyle(
  homeColor?: string,
  awayColor?: string
): React.CSSProperties {
  return {
    '--team-home-primary': homeColor || '#6b7280',
    '--team-away-primary': awayColor || '#6b7280',
  } as React.CSSProperties;
}
```

**Risk for Phase 2:** LOW. All additive — no existing code changes. shadcn/ui components are new files. Design tokens are new CSS. Framer Motion is a new dependency.

---

## 4. Phase 3: Win Probability Chart Improvements

### 3.1 Fix Stat Model for College Games

**Problem:** `compute_statistical_win_prob()` only runs when ESPN sync provides `game_clock` and `period`. College teams frequently fail ESPN name matching, so the stat model never fires.

**Solution:** In `tasks/odds_polling.py`, when computing the stat model, if `game_clock` is unavailable, use `estimate_seconds_remaining_from_wall_clock()` (already implemented in `win_probability.py`). The code path exists but may not be fully wired.

**Files:** `backend/app/tasks/odds_polling.py`, `backend/app/utils/win_probability.py`
**Tests:** Run `test_win_probability.py` (67 tests) — they cover the wall-clock fallback.
**Risk:** LOW. The fallback is less precise but produces reasonable results.

### 3.2 Multi-Participant Tournament Chart (Golf)

**Problem:** OddsChart assumes two teams (home vs away). Golf needs N-participant probability timeline.

**What already exists:**
- `FuturesOddsSnapshot` stores per-golfer odds history by bookmaker
- `GET /api/futures/{market_id}/progression` endpoint discovers sibling markets
- `SPORT_STAGES["golf"]` has stage patterns (Make Cut → Top 20 → ... → Win)

**What to build:**

Backend:
- New endpoint: `GET /api/futures/{market_id}/probability-timeline`
- Aggregates `FuturesOddsSnapshot` rows by outcome over time
- Returns array of `{ timestamp, outcomes: [{ name, probability }] }` sorted by time
- Limits to top 10 outcomes by current probability (others grouped as "Field")

Frontend:
- New component: `TournamentChart.tsx`
- Multi-line Recharts line chart, one line per golfer
- Color lines by current position (leader = vivid, others = progressively lighter)
- Tooltip shows all golfer probabilities at hovered timestamp
- Toggle between "Top 5" / "Top 10" / "All" view

**Risk:** MEDIUM. New endpoint + new component, but no existing code changes. Data already exists.

### 3.3 Series Probability for Elimination Tournaments

**Problem:** Users see "Warriors 60% in Game 6" but not "Warriors 25% to win the series."

**Solution (no new tables needed):**

Create `backend/app/utils/series_probability.py`:

```python
def compute_series_win_prob(
    team_win_prob_this_game: float,
    team_games_won: int,
    opponent_games_won: int,
    games_to_win: int = 4,  # best-of-7
) -> float:
    """Compute probability of winning a best-of-N series.

    Uses binomial probability: given P(win each remaining game),
    what's P(reaching `games_to_win` before opponent does)?
    """
    from math import comb

    team_needs = games_to_win - team_games_won
    opp_needs = games_to_win - opponent_games_won

    if team_needs <= 0:
        return 1.0
    if opp_needs <= 0:
        return 0.0

    p = team_win_prob_this_game
    total_remaining = team_needs + opp_needs - 1

    # Sum over all ways team can win team_needs games
    # in the remaining total_remaining games
    prob = 0.0
    for wins in range(team_needs, total_remaining + 1):
        # Must win exactly `wins` out of `total_remaining`
        # AND the last game must be a win (clinch game)
        prob += comb(total_remaining - 1, wins - 1) * (p ** wins) * ((1 - p) ** (total_remaining - wins))

    return prob
```

**Frontend:** Add "Series: Warriors lead 3-2 | Series win prob: 75%" to event detail for playoff games. Requires detecting playoff context from `llm_importance="playoff"` and finding other games in the series (by same teams + similar `commence_time`).

**Link events:** Add nullable `series_id` column to `Event` model (populated by ESPN sync when it detects playoff series). Simple: if two events have the same two teams within a 14-day window and both are `llm_importance="playoff"`, they're the same series.

**Risk:** LOW for the math utility. MEDIUM for the frontend integration (needs series detection heuristic).

### 3.4 Draw Probability for Soccer (Lower Priority)

**Problem:** `WinProbSnapshot.draw_probability` exists in the data model but the chart only shows home vs away.

**Solution:** For events where draw probability is significant (>5%), switch to a 3-area stacked chart: home win (bottom), draw (middle), away win (top). This is a Recharts `AreaChart` with `stackId="1"`.

**Risk:** LOW. Additive frontend change, data already exists.

### 3.5 Clean Up MoneyPuck Stub

**Decision needed:** Either build the MoneyPuck integration (free NHL stats API) or remove the stub from `win_prob_sources.py`. A stub that returns no data confuses the source registry.

**Recommendation:** Remove for now. Add back when there's time to build the integration properly.

---

## 5. Phase 4: Futures Grouping System

### 4.1 Recover Polymarket NegRisk Hierarchy

**Problem:** Polymarket NegRisk events (temperature ranges, multi-outcome championship markets) have a parent event structure, but `tasks/polymarket.py` flattens them into independent `FuturesMarket` rows.

**Solution:** During ingestion in `tasks/polymarket.py`, set `group_id = f"polymarket:{polymarket_event_id}"` and `group_type = "negrisk"` when `neg_risk=True`. Store `polymarket_event_id` in `market_metadata` JSONB.

**Backfill:** For existing markets, query Polymarket's Gamma API to recover event IDs and update `group_id`.

**Risk:** LOW. Just storing additional metadata during ingestion.

### 4.2 Recover Kalshi Event Hierarchy

**Problem:** Kalshi events (containing multiple markets) are flattened during ingestion. The event ticker suffix links them but isn't stored.

**Solution:** In `tasks/kalshi.py`, extract the Kalshi event ticker and set `group_id = f"kalshi:{event_ticker}"` and `group_type = "kalshi_event"`.

**Existing helper:** `_extract_kalshi_suffix()` in `routes/futures.py` (line 45) already does the parsing — just move it to a shared utility.

**Risk:** LOW. Same pattern as Polymarket.

### 4.3 Build Threshold Variant Detection

**Problem:** Markets like "Temperature: 78°F vs 79°F vs 80°F" or "Player points: 25-34 vs 35-44" are separate rows with no grouping.

**Solution:** Create `backend/app/utils/market_grouping.py`:

```python
def detect_threshold_group(markets: list[FuturesMarket]) -> list[MarketGroup]:
    """Detect markets that differ only by numeric threshold.

    Strategy:
    1. Normalize market names by removing numbers
    2. Group by normalized name
    3. Within each group, extract numeric thresholds
    4. If thresholds are sequential/overlapping, it's a threshold group
    """
```

Run as a periodic Celery task (daily) or on-demand via admin endpoint.

**Risk:** MEDIUM. Regex-based threshold extraction can false-positive. Start with Polymarket NegRisk (already flagged) and expand cautiously.

### 4.4 Frontend Display Components

Three new components:

**ThresholdGrid.tsx:** For temperature, rainfall, score ranges. Horizontal bar of labeled segments with probability underneath each.

**ProgressionTable.tsx:** For tournament stages. Table with participants as rows and stages as columns, probability in each cell. Already has backend support via `GET /api/futures/{market_id}/progression`.

**CombinedMarketCard.tsx:** For game-level Kalshi events. Shows moneyline + spread + total in one compact card.

**Risk:** LOW. New components, no existing code changes.

---

## 6. Phase 5: Design Component Migration

Once Phase 2's design system is in place, incrementally migrate existing components:

1. `EventCard.tsx` → use shadcn Card + design tokens + team color CSS vars
2. `FuturesCard.tsx` → same treatment
3. `EIBadge.tsx` → use Framer Motion for breathing animation
4. `OddsChart.tsx` → integrate with design tokens for consistent colors
5. `ProbabilityBar.tsx` → team-colored with design tokens
6. Homepage layout → CSS Grid with responsive columns

**Strategy:** One component at a time. Each migration is a self-contained PR. Don't change behavior, only styling.

**Risk:** LOW per component. The risk is in doing too many at once and creating merge conflicts.

---

## 7. Implementation Order & Parallelization

### CLI Terminal Layout (4 windows)

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│  Terminal 1: Backend Cleanup        │  Terminal 2: Frontend Design System │
│  (Phase 1.1-1.5)                    │  (Phase 2.1-2.4)                   │
│                                     │                                     │
│  Can run SIMULTANEOUSLY             │  Can run SIMULTANEOUSLY             │
│  with Terminal 2                    │  with Terminal 1                    │
├─────────────────────────────────────┼─────────────────────────────────────┤
│  Terminal 3: Win Prob Charts        │  Terminal 4: Futures Grouping       │
│  (Phase 3.1-3.5)                    │  (Phase 4.1-4.4)                   │
│                                     │                                     │
│  AFTER Terminal 1 completes         │  AFTER Terminals 1 AND 2 complete  │
│  (depends on fangraphs rename)      │  (depends on schema + design)      │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Detailed Order

**Week 1: Foundation (Terminals 1 + 2 in parallel)**

| Day | Terminal 1 (Backend) | Terminal 2 (Frontend) |
|-----|---------------------|----------------------|
| Mon | 1.2 Delete dead code | 2.1 Install shadcn/ui |
| Mon | 1.1 Rename fangraphs→mlb | 2.2 Set up design tokens |
| Tue | 1.3 Consolidate name matching | 2.3 Install Framer Motion |
| Wed | 1.3 continued (tests) | 2.4 Team color theming |
| Thu | 1.4 Backend market type enum | (idle or start 5.1 EventCard) |
| Fri | 1.5 Add group_id schema | (idle or start 5.2 FuturesCard) |

**Week 2: Features (Terminals 3 + 4, sequential within each)**

| Day | Terminal 3 (Charts) | Terminal 4 (Grouping) |
|-----|--------------------|-----------------------|
| Mon | 3.1 Fix stat model for college | 4.1 Polymarket NegRisk recovery |
| Tue | 3.2 Tournament chart (backend) | 4.2 Kalshi event recovery |
| Wed | 3.2 Tournament chart (frontend) | 4.3 Threshold detection |
| Thu | 3.3 Series probability | 4.4 Frontend display components |
| Fri | 3.5 Remove MoneyPuck stub | Testing + polish |

### What Can Safely Parallel

**SAFE to parallel (no file conflicts):**
- Terminal 1 (backend/) + Terminal 2 (frontend/) — completely separate directories
- Phase 3.2 backend endpoint + Phase 4.1 Polymarket ingestion — different files
- Phase 3.3 series utility + Phase 4.3 threshold detection — different files

**NOT safe to parallel:**
- Phase 1.1 (fangraphs rename) + Phase 3.x (chart changes) — both touch `win_prob_sources.py`
- Phase 1.4 (market type enum) + Phase 4.x (grouping) — both modify `FuturesMarket` model
- Any two migrations — Alembic requires sequential revisions
- Phase 2.x + Phase 5.x — both modify frontend components

---

## 8. Risk Registry

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Name matching regression | Events link to wrong teams, prediction markets mislink, feed shows wrong games | Write 30+ tests for `name_normalization.py` BEFORE changing any imports. Run full test suite after each consumer migration. |
| Alembic migration conflicts | Deploy fails, database schema corruption | Run migrations sequentially, never in parallel. Test on a branch first. Keep revision IDs ≤32 chars. |
| `fangraphs` rename breaks iOS | iOS app stops showing MLB win probability | Add temporary alias mapping for 30 days. Check iOS caching behavior. |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Market type enum mismatch | Frontend shows wrong tier for some markets | Run classification on all existing markets before deploying. Compare with frontend's current `effectiveTier()` output. Log discrepancies. |
| shadcn/ui conflicts with existing Tailwind | Style regressions on existing components | Install shadcn/ui on a branch. Check for CSS class conflicts. |
| Futures grouping false positives | Unrelated markets grouped together | Start with source-native grouping (NegRisk, Kalshi events) before pattern-based detection. Manual review via admin endpoint. |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Dead code deletion breaks something | Task crash | Grep for imports before deleting. All tests pass before merge. |
| Design tokens don't apply | No visual change (harmless) | Check CSS specificity. Verify `@layer base` loads before component styles. |
| Tournament chart performance | Slow rendering for 100+ golfers | Limit to top 10, lazy-load the rest. |

### Gotchas to Watch For

1. **Alembic revision ID length**: Must be ≤32 characters. Use short names like `add_group_id` not `add_futures_market_group_id_and_type`.

2. **Celery task name pinning**: If you add new tasks, they MUST have `name="app.tasks.xxx"` parameter. Beat schedule uses string task names.

3. **Frontend `import` order**: shadcn/ui components import from `@/components/ui/`. Make sure your `tsconfig.json` `paths` config includes this alias.

4. **CSS variable format for Tailwind**: Tailwind v4's `@theme` expects raw RGB values (not `rgb(...)` or hex). Example: `--color-live: 239 68 68` not `--color-live: #ef4444`.

5. **Team color CSS variables must be set on a parent element**: Components using `var(--team-home-primary)` will fall back to the `:root` default (gray) if no parent sets the variable. Always wrap EventCards in a container that sets team colors.

6. **The `canonical_market_key` compute function returns None for many markets**: Don't assume `group_id` will always be set. The grouping system must handle ungrouped markets gracefully.

7. **Polymarket NegRisk events can have 50+ outcomes**: The threshold grid must handle large groups. Cap display at 10-15 segments with a "Show more" toggle.

8. **iOS app reads from the same API**: Any API response shape changes (new fields, renamed keys) should be additive. Never remove a field the iOS app might be using.

---

## 9. Pre-Implementation Checklist (Manual Steps for Alex)

These are things you should do BEFORE giving prompts to Claude:

### Required (5 minutes)

- [ ] **Install shadcn/ui**: Run in your `frontend/` directory:
  ```bash
  npx shadcn-ui@latest init
  ```
  When prompted: TypeScript=yes, style=New York, base color=Slate, CSS variables=yes, tailwind.config location=tailwind.config.ts, components alias=@/components, utils alias=@/lib/utils

- [ ] **Install Framer Motion**:
  ```bash
  cd frontend && npm install framer-motion
  ```

- [ ] **Install a few shadcn components**:
  ```bash
  npx shadcn-ui@latest add card badge button tooltip
  ```

### Recommended (15 minutes)

- [ ] **Create a Figma account** (free): figma.com — even if you don't design in it now, having it ready for the v0.dev workflow is valuable.

- [ ] **Try Vercel v0** (free): v0.dev — paste a description of one of your components and see what it generates. Good for rapid prototyping.

- [ ] **Check your Odds API quota**: `curl https://api.bainluck.com/health/ready` — if remaining < 1M, be cautious about any polling changes.

### Not Needed Now

- DataGolf API subscription (only needed if you want live golf leaderboard data — $99+/mo)
- Storybook setup (nice-to-have, not blocking)
- Figma design system (build this incrementally as components stabilize)

---

## 10. CLI Prompts

See `docs/cli-prompts/` directory for the actual prompts to submit to Claude Code CLI.

Each prompt is a self-contained file that can be copied and pasted directly.

**Prompt files:**
- `01-backend-cleanup.md` — Phase 1 (backend refactoring)
- `02-frontend-design-system.md` — Phase 2 (design system setup)
- `03-win-prob-charts.md` — Phase 3 (chart improvements)
- `04-futures-grouping.md` — Phase 4 (grouping system)
- `05-component-migration.md` — Phase 5 (design migration)

---

## Appendix: Reference Sites for Design Inspiration

| Site | What to Study |
|------|--------------|
| FiveThirtyEight (archived) | Probability visualization, forecast uncertainty display |
| FanDuel app | Card layouts, team color integration, live odds updates |
| Kalshi.com | Minimal chrome, data-forward design, market grouping |
| PredictIt | Simple prediction market UI, probability bars |
| ESPN Fantasy app | Team color theming, status badges, responsive data density |

## Appendix: Tech Stack Additions

| Tool | Purpose | Cost | Priority |
|------|---------|------|----------|
| shadcn/ui | Component library | Free | P0 (install now) |
| Framer Motion | Animation library | Free | P0 (install now) |
| Vercel v0 | AI design-to-code | Free | P1 (try it) |
| Storybook | Component documentation | Free | P2 (later) |
| Builder.io Figma plugin | Figma-to-React export | Free tier | P2 (later) |
| Nivo charts | Advanced data viz (D3-based) | Free | P3 (if Recharts isn't enough) |
