# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. This is the canonical list — no other doc should duplicate it.

**How to use this doc:**
- When items ship, move them to `docs/completed-features.md` with a date and brief description
- When new work is discovered (bugs, ideas, follow-ups), add it here in the right section
- When priorities change, reorder within sections
- Mark items with **SHIPPED** and date when done, then move to completed-features on next cleanup pass

**Item format:**
Each item includes metadata for parallel work planning. `Layer` identifies what part of the codebase it touches. `Touches` lists specific files. `Parallel Safety` indicates whether it's safe to run alongside other work. `Prompt` is a ready-to-paste prompt for starting the item in a Claude Code session.

**Related docs:**
- `docs/completed-features.md` — shipped features log
- `docs/PRD.md` — product vision, ideas under exploration, open questions
- `docs/golf-product-strategy.md` — golf-specific product strategy
- `.claude/plans/mighty-churning-blum.md` — strategic codebase health plan (code review, testing, iOS parity audit)

---

## Quick Reference: What Can Run In Parallel

| If you're working on... | Safe parallel candidates |
|------------------------|------------------------|
| Name normalization (#2) | Items 3, 5 (all Green) |
| API base class (#3) | Items 2, 5 (all Green) |
| iOS parity (#5) | ANYTHING — always safe |
| God function refactoring (#6) | Items 2, 3, 5 |
| Golf data quality (#7) | Items 2, 3, 5 |
| Game prop linking (#1C) | Items 2, 3, 5 |
| No good parallel candidate? | Brainstorm B1 design decisions, or iOS parity (#5) |

---

## Tier 1 — High Leverage, Do Next

### 1. ESPN + Source Coverage — SHIPPED April 16
**Status:** COMPLETE. All acceptance criteria met.

**What shipped:**
- All 6 sources (betting, espn, stat_model, mlb, kalshi, polymarket) now write to `win_probability_sources` via select+update pattern
- Feed response includes `win_probability_sources`
- `espn_win_prob_home` written atomically with `win_probability_sources["espn"]`
- ESPN match rate: 100% for completed events (NBA, NHL, MLB)
- Live events show 3-4 sources (was 1)
- Root cause: ORM attribute assignment silently failed due to session caching; fixed by using SQLAlchemy `update()` statements

---

### 1B. Event Detail Page Quality Issues (discovered April 16, mostly fixed)

**SHIPPED (April 16):**
- Baseball markers: T3/B5 format ✓
- Wrong sport props: strict sport_id + llm_sport_category filter ✓
- Title Odds card: removed ✓
- Awards card: renamed to "Season Awards" ✓
- Playoff tier: qualifiers reclassified to tier 4 (3,263 markets) ✓
- City name patterns: "Texas", "Houston", etc. now included in ILIKE matching ✓
- Chart domain sync: ScoreDiff now uses OddsChart's exact domain ✓
- "More Baseball" ghost text: hidden during loading ✓

**REMAINING (2 items):**

#### R1. Player prop cards need headshots — **NAME MATCHING FIXED April 19**
Stat suffix stripping shipped (e.g., "Mitch Keller: 3+" → "mitch keller"). Headshots will appear once MLB roster data has ESPN IDs populated (verify after next `sync_rosters` run).
**Layer:** backend-routes, frontend-components
**Touches:** `backend/app/routes/events.py` (related-futures serialization ~L3050), `frontend/components/RelatedFutures.tsx` (StatPropsSection)
**Parallel Safety:** Yellow

**Problem:** Player prop cards show text-only (colored initials circle). The `PlayerStatCard.tsx` component already has `PlayerAvatar` with a 4-step fallback chain: (1) direct `headshotUrl` prop, (2) ESPN headshot via `espnPlayerId`, (3) Wikipedia image search, (4) initials. The data just isn't being passed.

**Root cause:** The Related Futures endpoint at `routes/events.py` builds a `player_metadata` dict (line ~2851) from team rosters, mapping `player_name_lower → {espn_id, headshot, name}`. But this metadata is never included in the serialized response. The frontend `StatPropsSection` component passes `headshotUrl` and `espnPlayerId` to `PlayerStatCard`, but they're always undefined because the API doesn't include them.

**Exact fix:**
1. In `routes/events.py`, find the Related Futures response serialization (~line 3050-3100 where each future is built as a dict). For outcomes that match a player in `player_metadata`, add `espn_player_id` and `headshot_url` to the response dict:
```python
# After building the future dict, check player_metadata
outcome_name_lower = outcome.name.lower()
player_meta = player_metadata.get(outcome_name_lower)
if player_meta:
    future_dict["espn_player_id"] = player_meta.get("espn_id")
    future_dict["headshot_url"] = player_meta.get("headshot")
```
2. In `frontend/components/RelatedFutures.tsx`, in `StatPropsSection` (~L820-1099), pass these through to `PlayerStatCard`:
```tsx
<PlayerStatCard
  ...existing props...
  espnPlayerId={future.espn_player_id}
  headshotUrl={future.headshot_url}
  sportKey={sportKey}
/>
```

**Verification:** Load any live NBA game → Player Props section should show ESPN headshot photos instead of colored initial circles.

---

#### R2. Missing 2nd inning marker on baseball chart — **ROOT CAUSE FIXED April 17**
**Status:** Backend dedup fix shipped in `tasks/snapshots.py` — snapshots now written when inning/period changes even if probability is flat. No frontend interpolation needed. Verify on next baseball game that all innings appear.

---

#### R3. Playoff Path sparse — Kalshi short names not matching as alternate_names
**Layer:** backend-tasks, backend-admin
**Touches:** `backend/app/tasks/team_linking.py` or new admin script, Team.alternate_names column
**Parallel Safety:** Green (data fix, no code behavior changes)

**Problem:** Kalshi uses city-only names as outcome labels ("Texas", "Houston", "Seattle", "A's"). The city name pattern fix (shipped April 16) added city names to the ILIKE search. But teams with non-city short names like "A's" (Athletics) or abbreviated cities like "Los Angeles D" (Dodgers) vs "Los Angeles A" (Angels) still don't match.

**Root cause:** `_team_name_patterns()` generates ["full name", "mascot", "city"]. For "Athletics", this gives ["Athletics"]. Kalshi's outcome is "A's" — not in the pattern list. For "Los Angeles Dodgers", the patterns are ["Los Angeles Dodgers", "Dodgers", "Los Angeles"] — but Kalshi uses "Los Angeles D" which doesn't match any of these.

**The complete list of Kalshi MLB outcome names that DON'T match our team patterns:**
- "A's" → needs alias on Athletics team record
- "Los Angeles D" → needs alias on Dodgers
- "Los Angeles A" → needs alias on Angels  
- "Chicago C" → needs alias on Cubs
- "Chicago WS" → needs alias on White Sox
- "New York Y" → needs alias on Yankees
- "New York M" → needs alias on Mets

**Exact fix:** Use the `/admin/teams/add-alias` endpoint (already built) to add each alias. OR better: write a one-time script that queries the Kalshi playoff qualifiers market (id=266), gets all 30 outcome names, and for each one, finds the matching team in our DB and adds the Kalshi name as an alternate_name. This is 30 API calls and ensures EVERY team has its Kalshi name.

```python
# Pseudocode for the script:
# 1. GET /api/futures/266 → get all 30 outcomes
# 2. For each outcome name (e.g., "A's", "Los Angeles D"):
#    a. Try names_match against all 30 MLB teams
#    b. If match found and outcome name not in team.alternate_names, add it
#    c. If no match, log for manual review
```

This could also be an admin endpoint: `/admin/teams/sync-kalshi-aliases?sport=baseball_mlb` that does this automatically.

**Also need:** Run the same process for NBA, NHL, NFL. Kalshi uses similar abbreviations across all sports ("GS" for Golden State, "OKC" for Oklahoma City, etc.).

**Verification:** After adding aliases, hit the Related Futures endpoint for any MLB game. The Playoff Path should show 4 rows (Make Playoffs, Division, AL/NL Champ, World Series) instead of 1.
- Best/worst record: Kalshi `kxmlbbestrecord/worstrecord`

---

### 1C. Game Prop → Event Linking — **PARTIALLY SHIPPED April 19-20**

**Status:** Core linking infrastructure shipped. 1,784+ markets newly linked. Link rate dashboard deployed at `/admin` and via `GET /api/admin/prediction-markets/link-rate`.

**What shipped (April 19-20):**
- Ticker-derived team names for game props ("WSH Capitals" → "Capitals" from ticker)
- `_expand_team_search_terms()` for ILIKE pattern expansion
- `_SPORT_ABBREV_SUFFIX` derived from all ~150 ticker prefixes (was 7)
- `_TICKER_DATE_RE` fixed for digit-containing prefixes (KXNBA2D, KXNBA3PT)
- `sport_id` propagation on all 5 linking paths + Phase 1.5 backfill
- `llm_sport_category` correction from ticker on link + backfill
- " - More Markets" Polymarket suffix stripping
- Phase 2 deadlock fix (per-market commit + rollback on deadlock)
- Matching frequency 4h → 1h, limit 200 → 500
- Link rate API endpoint + admin dashboard visualization
- 19 new tests (315 total prediction market matching tests)

**Current link rates (April 20, 2026):**

| Sport | Kalshi (open) | Polymarket (open) | Target | Blocking issue |
|-------|--------------|-------------------|--------|----------------|
| Basketball | 67.7% | 89.5% | >90% | See 1C-a |
| Baseball | 68.6% | 71.2% | >90% | See 1C-a |
| Hockey | 26.6% | 50.0% | >80% | See 1C-b |
| Soccer | 33.2% | 98.5% | varies | See 1C-c |
| MMA | 75.4% | 25.0% | >80% | See 1C-d |
| Tennis | 51.6% | 0.3% | 50%+ | See 1C-e |
| Esports | 13.5% | 3.9% | ~20% | See 1C-f |
| Golf | 1.4% | — | N/A | See 1C-g |
| Football | 0.0% | — | N/A | Offseason |
| Cricket | — | 20.7% | 50%+ | See 1C-h |

**Monitor:** `GET /api/admin/prediction-markets/link-rate?secret=$ADMIN_SECRET` or admin dashboard.

---

#### 1C-a. Basketball + Baseball: 70% → 90%+ link rate
**Layer:** backend-tasks
**Touches:** `tasks/prediction_market_matching.py`
**Parallel Safety:** Yellow
**Impact:** HIGH — these are the two biggest sport categories on Kalshi

**Problem:** ~30% of Kalshi basketball/baseball game props remain unlinked despite team name fixes. Diagnosis shows two remaining causes:

1. **Markets created before events exist.** Kalshi creates game prop markets 2-7 days before games. Our events are created from The Odds API discovery task, which runs on a shorter horizon. When the matching task scans these markets, there's no event to link to. On the NEXT run (after events are created), the market may not be re-scanned if it was already processed.

2. **`llm_sport_category` misclassification.** The Kalshi polling task sets `llm_sport_category` from its own LLM classification, which is often wrong (MLB games tagged "basketball"). Our fix corrects this ON LINK, but markets that failed to link on the first attempt still have the wrong category, and the `get_related_futures()` sport filter rejects them even if they later get linked.

**Fix:**
1. In `_match_prediction_markets()` Phase 1, don't skip markets that were already processed in a previous run if they're still unlinked. Currently Pass 1 (ticker scan) queries `event_id IS NULL` so it DOES re-scan — but some markets fail because the event didn't exist yet. The fix is to ensure the hourly cadence keeps retrying. This may already be working with the 4h→1h change — monitor for a few days to see if rates climb naturally.

2. Add a one-time backfill SQL to fix `llm_sport_category` for all Kalshi markets based on their ticker prefix:
```sql
-- Run via admin endpoint or migration
UPDATE futures_markets fm
SET llm_sport_category = CASE
    WHEN external_id ILIKE 'kxnba%' THEN 'basketball'
    WHEN external_id ILIKE 'kxnfl%' THEN 'football'
    WHEN external_id ILIKE 'kxnhl%' THEN 'hockey'
    WHEN external_id ILIKE 'kxmlb%' THEN 'baseball'
    WHEN external_id ILIKE 'kxncaab%' OR external_id ILIKE 'kxncaamb%' THEN 'basketball'
    WHEN external_id ILIKE 'kxncaaf%' THEN 'football'
    WHEN external_id ILIKE 'kxncaawb%' THEN 'basketball'
    WHEN external_id ILIKE 'kxwnba%' THEN 'basketball'
    WHEN external_id ILIKE 'kxmlsgame%' OR external_id ILIKE 'kxmls%' THEN 'soccer'
    WHEN external_id ILIKE 'kxufc%' THEN 'mma'
    WHEN external_id ILIKE 'kxboxing%' THEN 'boxing'
    WHEN external_id ILIKE 'kxatp%' OR external_id ILIKE 'kxwta%' THEN 'tennis'
    WHEN external_id ILIKE 'kxlol%' OR external_id ILIKE 'kxcs2%' OR external_id ILIKE 'kxvalorant%' THEN 'esports'
    ELSE llm_sport_category
END
WHERE source = 'kalshi'
  AND external_id IS NOT NULL
  AND llm_sport_category != CASE ... END;  -- only update wrong ones
```

**Acceptance criteria:** Basketball open link rate >85%, Baseball open link rate >85% on the link-rate dashboard.

**Prompt:**
> Write an admin endpoint `POST /api/admin/prediction-markets/fix-sport-categories` that runs the SQL above to bulk-fix `llm_sport_category` for all Kalshi markets based on their ticker prefix. Return the count of rows updated per sport. Then monitor `/api/admin/prediction-markets/link-rate` to see if rates improve.
>
> INTERFERENCE RULES: Do NOT modify the matching pipeline logic. This is a data fix only.

---

#### 1C-b. Hockey: 27% → 80%+ link rate
**Layer:** backend-tasks
**Touches:** `tasks/prediction_market_matching.py`, `utils/prediction_market_matching.py`
**Parallel Safety:** Yellow
**Impact:** MEDIUM — NHL playoffs happening now, lots of active props

**Problem:** NHL game props have two specific issues beyond the general category fix (1C-a):

1. **Kalshi NHL props use abbreviated city names** that don't match our event names. Examples from diagnostics:
   - Market: `"MIN at DAL: Total Points"` → team_a="MIN", team_b="DAL"
   - Our event: "Minnesota Wild at Dallas Stars"
   - "MIN" is 3 chars, below the `_expand_team_search_terms` threshold (5 chars), and doesn't ILIKE-match "Minnesota Wild"

2. **Playoff series markets are classified as game-level.** `"Game 2: Minnesota at Dallas: Total Points"` has a "Game N:" prefix that gets captured as part of team_a ("Game 2: Minnesota") instead of being stripped.

**Fix:**
1. Add a `_CITY_ABBREV_TO_NAME` map for common 2-3 letter city abbreviations used by Kalshi: `{"MIN": "Minnesota", "DAL": "Dallas", "PHX": "Phoenix", "OKC": "Oklahoma City", "WSH": "Washington", "NJ": "New Jersey", "LA": "Los Angeles", "NY": "New York", "CHI": "Chicago", "DET": "Detroit", "BOS": "Boston", "ATL": "Atlanta", "MIA": "Miami", "SF": "San Francisco", "SEA": "Seattle", ...}`. Use this in `_expand_team_search_terms()` to expand abbreviations.

2. Add a `_GAME_NUMBER_PREFIX_RE` pattern like `r'^Game\s+\d+\s*:\s*'` and strip it in `_normalize_variants()` before matchup extraction.

**Verification:** Check link-rate after fix. NHL open link rate should jump from ~27% to >70%.

**Prompt:**
> Fix two NHL linking issues:
>
> 1. In `utils/prediction_market_matching.py`, add `_CITY_ABBREV_TO_NAME` dict mapping 2-3 letter city abbreviations to full city names. Update `_expand_team_search_terms()` to check if the team name is a known abbreviation and add the full name as an ILIKE term. For example, `_expand_team_search_terms("MIN")` should return `["MIN", "Minnesota"]`.
>
> 2. In `_normalize_variants()`, add stripping for "Game N:" prefix pattern. Add `_GAME_NUMBER_PREFIX_RE = re.compile(r'^Game\s+\d+\s*:\s*', re.IGNORECASE)` and strip it from the base name alongside " - More Markets".
>
> Add tests for both. Run: `python3 -m pytest tests/test_prediction_market_matching.py -v`
>
> INTERFERENCE RULES: Do NOT modify `tasks/prediction_market_matching.py` — these are pure utility function changes.

---

#### 1C-c. Soccer: 33% → varies by league
**Layer:** backend-tasks, backend-services
**Touches:** `tasks/prediction_market_matching.py`, `services/event_registry.py`
**Parallel Safety:** Yellow
**Impact:** LOW-MEDIUM — most soccer users are on Polymarket (98.5% linked)

**Problem:** Kalshi soccer is 33% because we don't create events for many leagues they cover:
- Liga MX (Mexican): Kalshi tickers `KXLIGAMXGAME-...` → we have no Liga MX events
- Saudi Pro League: `KXSAUDIPLGAME-...` → no events
- Danish Superliga: `KXDENSUPERLIGAGAME-...` → no events
- USL (US lower division): `KXUSLGAME-...` → no events
- Allsvenskan (Swedish): `KXALLSVENSKANGAME-...` → no events

These are all leagues NOT covered by The Odds API. Events could be auto-created from prediction markets (the infrastructure exists in `_create_event_from_prediction_market()`), but these sport keys are blocked by `_ODDS_API_COVERED_PREFIXES` because they're classified as generic "soccer" which IS covered.

**Fix:** Add new sport key entries for these specific leagues so auto-creation works:
1. Add to `sport_keys.py`: `"kxligamxgame": "soccer_liga_mx"`, `"kxsaudiplgame": "soccer_saudi_pro"`, etc.
2. These sport keys don't need Odds API coverage — they'll only be created from prediction markets
3. Update `_ODDS_API_COVERED_PREFIXES` to NOT block these specific keys (only block `soccer_usa_mls` and `soccer_epl` which ARE covered)

**Alternative (simpler):** Accept lower soccer link rate on Kalshi. Polymarket soccer is already 98.5%. The ROI of adding minor league support is low unless users specifically want Liga MX or Saudi Pro League odds.

**Recommendation:** Don't fix yet. Monitor whether users actually visit events from these leagues.

---

#### 1C-d. MMA: Polymarket 25% → 70%+
**Layer:** backend-utils
**Touches:** `utils/prediction_market_matching.py`
**Parallel Safety:** Green
**Impact:** MEDIUM — UFC events are popular

**Problem:** Polymarket MMA markets use fighter names (e.g., "Oliveira vs. Holloway") which match fine. But 75% of markets are for specific bout outcomes (method of finish, rounds, distance) that are structured as separate markets, not as outcomes within the fight market. Our matching only looks for "vs" patterns — these secondary markets have names like "Does Oliveira vs Holloway go the distance?" which should match but may fail due to the "Does...?" prefix.

**Investigation needed:** Sample 20 unlinked Polymarket MMA markets to identify the actual name patterns:
```bash
curl "https://api.bainluck.com/api/admin/prediction-markets/debug?secret=$ADMIN_SECRET&sample_size=30&source=polymarket" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for s in d.get('sample_game_level',[]):
    if s.get('llm_sport_category')=='mma': print(s['name'])
"
```

**Likely fix:** Add "Does X vs Y...?" pattern to `_normalize_variants()` or `_WILL_WIN_RE`. Also Polymarket bout markets may need `_strip_trailing_paren()` for "(Lightweight, Main Card)" suffixes — this exists but may not fire for all variants.

**Prompt:**
> Diagnose why 75% of Polymarket MMA markets aren't linking. Sample unlinked markets via the debug endpoint. Identify the name patterns that fail matchup extraction. Add regex patterns and/or stripping logic to handle them. Add tests.

---

#### 1C-e. Tennis: Kalshi 52% → 70%+
**Layer:** backend-utils
**Touches:** `utils/prediction_market_matching.py`
**Parallel Safety:** Green
**Impact:** LOW — tennis is niche on the site

**Problem:** Kalshi tennis tickers (`KXATPMATCH-...`, `KXWTAMATCH-...`) are game-level match markets. 52% open link rate means about half are matching. The failures are likely due to:
- Player name format differences: Kalshi uses "Sinner vs. Djokovic" but our events (from Odds API) use "Jannik Sinner vs Novak Djokovic" (full names). "Sinner" is ≥5 chars so `_expand_team_search_terms` should produce it, but the full name match in `_score_candidates` may fail because `_fuzzy_team_match("Sinner", "Jannik Sinner")` should work (substring match). Need to investigate specific failing cases.
- Prop markets (set winners, game totals) may fail because they're classified as game-level but have different name formats.

**Polymarket tennis is 0.3%** — almost nothing links. This is likely because Polymarket tennis markets are for individual matches with generic names, and we don't create events for most ATP/WTA matches (only major tournaments).

**Fix:** Investigate specific failing Kalshi matches first. The Polymarket rate won't improve without adding ATP/WTA event creation from prediction markets.

---

#### 1C-f. Esports: ~14% / ~4% — structural limit
**Layer:** backend-services
**Parallel Safety:** Green
**Impact:** LOW — esports is not a priority

**Problem:** Hundreds of leagues (LoL LCK/LEC/LCS, CS2 IEM/Blast, Valorant VCT, Dota DPC). No centralized event source — we don't poll any esports data API. Markets are for specific map winners, series results, total maps. Our event creation is limited to auto-creation from prediction markets, which works for "Team A vs Team B" but not "Team A vs Team B Map 1".

**Realistic target:** ~20% link rate. Focus on series-level markets (which DO look like game matchups) and accept that map-level/total-maps markets won't link.

**Fix (low priority):**
1. Strip " Map N" suffix from esports market names before matchup extraction
2. Auto-create events from esports prediction markets (unblock in `_ODDS_API_COVERED_PREFIXES`)

---

#### 1C-g. Golf: 1.4% — not a bug
**Impact:** NONE

Golf Kalshi markets are futures (tournament winner, top 5, make cut), NOT game-level matchups. They're correctly classified as futures via `compute_market_tier()` and appear in the golf grid/tournament pages. The low "link rate" is expected because they don't have `event_id` — they have `sport_id` and appear via market tier queries instead. No action needed.

---

#### 1C-h. Cricket: Polymarket 21% → 50%+
**Layer:** backend-services
**Parallel Safety:** Green
**Impact:** LOW — cricket is niche

**Problem:** We don't have a cricket odds source — no events to link to. Polymarket cricket markets are for IPL, international test matches, T20 World Cup. Auto-creation from prediction markets works but is blocked for "cricket_other" sport keys.

**Fix:** Unblock cricket in `_ODDS_API_COVERED_PREFIXES` to allow auto-creation. Add cricket event sources if IPL viewership grows.

---

### 2. Name Normalization Consolidation
**Layer:** backend-utils, backend-routes, backend-tasks, backend-services
**Touches:** `utils/name_normalization.py` (primary), `routes/playoffs.py`, `routes/golf.py`, `routes/oscars.py`, `services/datagolf_api.py`, `tasks/mlb_sync.py`
**Depends on:** Nothing
**Conflicts with:** Any work touching playoffs.py, golf.py, or oscars.py routes
**Parallel Safety:** Yellow (touches multiple files but changes are mechanical)

**Problem:** 6 independent team/name normalization implementations scattered across the codebase. Each handles diacritics, casing, and suffix stripping slightly differently. Bug fixes in one don't propagate to others.

**Current implementations:**
- `utils/name_normalization.py:normalize_name()` — canonical, 22 lines
- `routes/playoffs.py:_normalize_team_name()` — local duplicate with `_strip_diacritics()`, 12 lines
- `routes/golf.py:_normalize_golfer_name()` — golfer-specific (Last, First format), 25 lines
- `routes/oscars.py:_normalize_nominee_name()` — nominee-specific, 15 lines
- `services/datagolf_api.py:strip_diacritics()` — standalone diacritic function
- `tasks/mlb_sync.py:_normalize_team()` — trivial lowercase-only, 8 lines

**Acceptance criteria:**
- All normalization goes through `utils/name_normalization.py`
- Sport-specific variants (golf, oscars) are exported functions from the same module
- Zero duplicate `_strip_diacritics()` or `unicodedata.normalize("NFD", ...)` outside the canonical module
- All existing tests pass
- Add tests for each variant function

**Prompt:**
> Consolidate all team/name normalization into `utils/name_normalization.py`. There are 6 independent implementations:
>
> 1. Read each implementation listed above. Understand what each does differently.
> 2. Extend `utils/name_normalization.py` to cover all cases:
>    - `normalize_name()` — general purpose (already exists)
>    - `normalize_golfer_name()` — handles "Last, First" format + DataGolf quirks
>    - `normalize_nominee_name()` — Oscars nominee cleaning
>    - `normalize_category()` — Oscars category extraction
>    - Ensure `strip_diacritics()` is a public function others can import
> 3. Update all callers to import from the canonical module. Delete the local implementations.
> 4. Add tests in `tests/test_name_normalization.py` for each new variant.
> 5. Run `python3 -m pytest tests/ -v` to verify nothing breaks.
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py` or `tasks/prediction_market_matching.py`.

---

### 3. API Client Base Class
**Layer:** backend-services
**Touches:** `services/odds_api.py`, `services/kalshi_api.py`, `services/polymarket_api.py`, `services/statpal_api.py`, `services/espn_api.py`, `services/datagolf_api.py`, `services/mlb_api.py`, NEW: `services/base_api.py`
**Depends on:** Nothing
**Conflicts with:** Any work modifying a specific API service file
**Parallel Safety:** Yellow (touches many files but changes are structural, not behavioral)

**Problem:** All 7 API services duplicate identical `__init__`, `close()`, and HTTP client management. No shared retry/timeout logic. When we add a new service, we copy-paste the same boilerplate.

**Acceptance criteria:**
- New `services/base_api.py` with `BaseAPIClient` class
- All 7 services inherit from it
- Shared: `__init__` (api_key from env), `close()`, `_get()` with timeout, `_post()` if needed
- Configurable per-service: base_url, default timeout, custom headers
- All existing tests pass
- Net reduction of ~100-140 lines of duplicated code

**Prompt:**
> Extract a base API client class from our 7 duplicate service implementations.
>
> 1. Read all 7 API services: `services/odds_api.py`, `kalshi_api.py`, `polymarket_api.py`, `statpal_api.py`, `espn_api.py`, `datagolf_api.py`, `mlb_api.py`
> 2. Identify the common patterns: `__init__` with env var API key, `httpx.AsyncClient` creation, `close()` method, `_get()` helper
> 3. Create `services/base_api.py` with a `BaseAPIClient` that handles all shared logic
> 4. Refactor each service to inherit from `BaseAPIClient`. Keep all service-specific methods unchanged.
> 5. Run `python3 -m pytest tests/ -v` to verify nothing breaks.
>
> Don't over-abstract. The base class should handle boilerplate, not business logic. Each service keeps its own methods.
>
> INTERFERENCE RULES: If another thread is actively modifying a specific service file (e.g., `espn_api.py`), skip that service and note it for later.

---

### 4. API Contract Tests — **SHIPPED April 19**
**Status:** COMPLETE. 27 integration tests across 3 endpoints (feed, playoffs, events). Mock DB + httpx AsyncClient infrastructure in `tests/integration/conftest.py`.

---

### 5. iOS Search & Futures Parity — **SHIPPED April 16** (not build-verified)
**Layer:** ios
**Touches:** `ios/Bain Luck/Views/SearchView.swift`, `ios/Bain Luck/Models/`, `ios/Bain Luck/Services/APIClient.swift`, potentially new Views
**Depends on:** Nothing
**Conflicts with:** Nothing (iOS is fully isolated)
**Parallel Safety:** Green — can ALWAYS run in parallel

**Status:** Commit `7620535`. Search filters + recent searches + FuturesListView shipped. NOT build-verified (SPM sandbox issue). Dynamic league list skipped (no backend endpoint). See `memory/project_ios_parity_april16.md` for full change log.

**Acceptance criteria:**
- ~~Search: sport/status filter chips below search bar (match web patterns)~~ DONE
- ~~Search: recent searches stored in UserDefaults, shown when search field is empty~~ DONE
- ~~Futures: browsable futures section accessible from main navigation~~ DONE (iPad sidebar)
- League list: fetched from API, not hardcoded — SKIPPED (no backend endpoint)

**Prompt:**
> Close the iOS feature gaps for TestFlight readiness. The iOS app is at `ios/Bain Luck/`. Key patterns:
> - Models: `nonisolated struct X: Decodable, Sendable` (NOT Codable, NOT without nonisolated)
> - ViewModels: `final class XViewModel: ObservableObject` — NO @MainActor on class, only on async methods
> - API: `Services/APIClient.swift` with snake_case JSON decoding
>
> Tasks:
> 1. **Search filters**: Read `Views/SearchView.swift`. Add filter chips for sport and status below the search bar. Look at how `SportFilterChips` works in `Views/Feed/FeedView.swift` for the pattern. Store recent searches in UserDefaults (max 10).
> 2. **Futures browsing**: Create a `FuturesListView` that fetches and displays futures markets. Add it as a section or tab accessible from main navigation. Reference the web's `frontend/app/futures/page.tsx` for what to show.
> 3. **Dynamic league list**: Read `Views/LeaguesView.swift`. Replace the hardcoded league array with an API fetch. Check if there's an existing endpoint (look at `routes/sports.py`).
>
> After each change, verify the project builds: `cd "ios/Bain Luck" && xcodebuild -scheme "Bain Luck" -destination 'platform=iOS Simulator,name=iPhone 16' build 2>&1 | tail -20`
>
> INTERFERENCE RULES: None — iOS is fully isolated from backend and frontend.

---

## Tier 2 — Important But Bigger Scope

### 6. Break Up God Functions
**Layer:** backend-routes, backend-tasks
**Touches:** Varies per sub-task (one function per session)
**Depends on:** Nothing (Event Registry is shipped)
**Conflicts with:** Any work on the same route/task file
**Parallel Safety:** Yellow (one function at a time, check conflicts)

**Problem:** 5 functions over 400 lines. Hard to understand, test, and modify without bugs.

**Sub-tasks (do one per session):**

**6a. `get_playoff_grid()` (847 lines in `routes/playoffs.py`)**

**Prompt:**
> Read `routes/playoffs.py`, function `get_playoff_grid()`. It's 847 lines doing: team resolution, market discovery, grid building, probability merging, monotonicity enforcement, and response formatting. Extract into: `services/playoff_grid.py` with functions like `resolve_teams()`, `discover_markets()`, `build_grid()`, `merge_probabilities()`, `enforce_monotonicity()`. The route handler should be <50 lines calling these service functions. Add tests for each extracted function. Run existing tests to verify: `python3 -m pytest tests/test_playoff_grid.py -v`
>
> INTERFERENCE RULES: Do NOT modify other route files.

**6b. `get_related_futures()` (771 lines in `routes/events.py`)**

**Prompt:**
> Read `routes/events.py`, function `get_related_futures()`. Extract market filtering, grouping, and formatting into `services/related_futures.py`. The route handler should orchestrate calls to service functions. Keep the tier-aware loading logic. Run tests after.
>
> INTERFERENCE RULES: Do NOT modify other route files or task files.

**6c. `_sync_espn_live_events()` (804 lines in `tasks/espn_sync.py`)**

**Prompt:**
> Read `tasks/espn_sync.py`, function `_sync_espn_live_events()`. Extract into: ESPN event matching, game state parsing, snapshot creation, win probability extraction. Each becomes a testable function. The main sync function becomes an orchestrator.
>
> INTERFERENCE RULES: Do NOT modify other task files.

**6d. `_match_prediction_markets()` (622 lines in `tasks/prediction_market_matching.py`)**

**Prompt:**
> Read `tasks/prediction_market_matching.py`. Event Registry is now shipped. Delete duplicate matching logic that's been replaced by the registry. Simplify to: fetch markets → registry lookup → write snapshots. Run tests: `python3 -m pytest tests/test_prediction_market_matching.py -v`
>
> INTERFERENCE RULES: Do NOT modify `services/event_registry.py`.

---

### 7. Golf Data Quality Pass
**Layer:** backend-routes, backend-tasks
**Touches:** `routes/golf.py`, `tasks/datagolf.py`, `utils/futures_categorization.py`
**Depends on:** Nothing
**Conflicts with:** Any work on golf.py
**Parallel Safety:** Yellow

**Known bugs (2 remaining):**
1. Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not currently reproducible
2. ~~"Augusta National Invitational" ghost tournament~~ **SHIPPED April 19** — added "invitational" to `_NON_WINNER_MARKET_RE`
3. ~~Categories page chart showing "Yes" (Polymarket binary label)~~ **SHIPPED April 17**
4. ~~"To win" label on card probabilities~~ Already fixed (shows "Win")
5. ~~H2H matchups filtered out on tournament detail~~ Working as designed (routed to separate h2h section)
6. ~~Make Cut column missing on tournament detail~~ Column exists, renders when data present
7. ~~ATP Monte-Carlo "Masters" markets leaking into golf~~ **SHIPPED April 17**

**Prompt:**
> Fix 7 golf data quality bugs. Read `routes/golf.py`, `tasks/datagolf.py`, and `utils/futures_categorization.py`.
>
> Bugs to fix (in order — each is small and independent):
> 1. **Tour misclassification**: Hainan Open classified as PGA Tour. DataGolf provides a `tour` field — use it to set correct tour. Check `tasks/datagolf.py` for where tour is set.
> 2. **Ghost tournament**: "Augusta National Invitational" appears as a tournament. Find where it's created and add a filter/blocklist.
> 3. **"Yes" label**: Polymarket binary markets show "Yes" instead of golfer name on categories page chart. Trace from `routes/golf.py` response → frontend rendering.
> 4. **"To win" label**: Card probabilities show "To win" text. Find the label source and remove/replace.
> 5. **H2H matchups filtered**: Tournament detail page filters out " vs " markets around line 608 of `golf.py`. Remove this filter — H2H matchups should appear.
> 6. **Make Cut column**: Tournament detail grid is missing a "Make Cut" column. Check if make-cut markets exist in the data, add column if so.
> 7. **Monte-Carlo leak**: ATP Monte-Carlo Masters tennis markets appear in golf data. Add sport/category gate in `utils/futures_categorization.py`.
>
> After each fix, run: `python3 -m pytest tests/ -k golf -v`
>
> INTERFERENCE RULES: Do NOT modify files outside golf-related code.

---

### 8. Site Navigation Hierarchy (B1)
**Layer:** frontend, backend-routes
**Touches:** `frontend/app/` (new route structure), `frontend/components/Navigation/`, `backend/app/routes/sports.py`
**Depends on:** Golf strategy decisions (default PGA Tour? hero layout?)
**Conflicts with:** Any frontend page work
**Parallel Safety:** Red (restructures frontend routing)

**Problem:** Current URL structure is flat (`/playoffs/nba`, `/categories/golf`). Need hierarchy: `/basketball/nba`, `/golf/pga-tour`. Team sports get grid+games+futures tabs. Individual sports get tour hub → tournament detail.

**Status:** NOT STARTED. Blocked on golf strategy decisions.

**Open design decisions:**
- Default to PGA Tour only? (Recommendation: yes, "All Tours" toggle)
- Golf home hierarchy? (Recommendation: hero -> majors -> upcoming -> completed)
- Don't kill `/playoffs/golf` yet — wait until golf pages are really humming

**Prompt:**
> [NOT READY — needs design decisions first]

---

### 9. External API Fixture Tests — **SHIPPED April 19**
**Status:** COMPLETE. 77 tests across 4 services (Kalshi 21, Odds API 15, ESPN boxscore 30, DataGolf 11) + 3 JSON fixture files.

---

### 16. Playoff Series Matchup Markets
**Layer:** backend-routes, backend-config, backend-tasks
**Touches:** `config/league_configs.py`, `utils/tournament_stages.py`, `routes/playoffs.py`
**Depends on:** Nothing (grid infrastructure exists)
**Conflicts with:** Grid/playoffs work
**Parallel Safety:** Yellow

**Opportunity:** Polymarket has rich playoff series matchup markets (e.g., "Celtics vs Cavaliers" series winner). Source: `polymarket.com/sports/nba/props`. These are perfect for two surfaces:

1. **Championship grid**: New column(s) showing current-round series win probability per team. Could be a "Current Round" or "Series" column that dynamically updates as rounds progress.
2. **Event detail pages**: Related Futures section could show the series matchup market alongside individual game odds, giving users the "bigger picture" context for any playoff game.

**Implementation sketch:**
- **Stage classification**: Add a `series` or `current_round` stage to `tournament_stages.py` for basketball/hockey. Patterns: `r"vs\b"`, `r"series\b"`, `r"advance\b"` (careful not to collide with game-level "vs" — filter by market type/source).
- **Grid column**: Add `GridColumn(key="current_round", label="Series", order=1.5)` — between make_playoffs and conference. Only show when fill rate is meaningful (playoff season).
- **Ingestion**: Polymarket polls should already pick these up. Verify they're classified as the right `llm_sport_category`. May need name-pattern matching to route into the grid.
- **Event detail**: Match series markets to events by team names + playoff round. Show "Series: Celtics 72% — Cavaliers 28%" on any Celtics playoff game detail page.
- **Trend data**: These markets move fast during series — trend charts would be very engaging.

**Open questions:**
- Should the grid show current-round only, or all active series?
- How to handle series that span multiple rounds (team advances, new matchup appears)?
- Should series markets appear as a grid column or as a separate "Active Series" section below the grid?

**Prompt:**
> Read `routes/playoffs.py` (grid builder) and `config/league_configs.py`. Polymarket has playoff series matchup markets (e.g., "Celtics vs Cavaliers"). These need to:
> 1. Be classified into a new "current_round" stage in `tournament_stages.py`
> 2. Appear in the championship grid as a dynamic column showing series win probability
> 3. Appear in event detail pages as Related Futures for playoff games
>
> Start by checking what series markets exist in the DB: query `futures_markets` for Polymarket markets with "vs" or "series" in the name and `llm_sport_category` in ('basketball', 'hockey'). Then design the classification patterns and grid column.
>
> INTERFERENCE RULES: Do NOT modify event matching, score tracking, or non-playoff routes.

---

## Tier 3 — Valuable But Can Wait

### 10. Evolution Chart: Combined Probability
**Layer:** backend-routes, frontend | **Parallel Safety:** Yellow
**Depends on:** Source coverage crisis fixed (#1)
Chart shows single-source data. Grid shows merged probability. Chart should show merged trend over time. Requires time-series aggregate computation.
**Status:** DEFERRED — fix source coverage first so there's multi-source data to merge.

### 11. Line Movement Explainer v2
**Layer:** backend-services, frontend | **Parallel Safety:** Green
Currently disabled. Only stated the obvious ("Team X won, odds went up"). Needs: key moment identification, causal analysis, context from scoring plays. Not blocking anything.

### 12. Freshness-Weighted Blending
**Layer:** backend-utils | **Parallel Safety:** Yellow
Stale prediction market prices weighted equally with fresh model data. Need time-decay weighting. Design notes in memory. Waiting on more eval data.

### 13. DS/Analytics Infrastructure
**Layer:** backend-models, migrations | **Parallel Safety:** Red (migrations)
Add analytical columns (`ended_at`, `final_home_probability`, `event_results`, `season`). Denormalize `sport_group`. Create `v_completed_events` view. Enables "Who's Right?" Brier score analysis. Low urgency.

### 14. Related Futures for Golf Tournaments
**Layer:** backend-routes | **Parallel Safety:** Yellow
Tournament detail pages have no "Bigger Picture" section. Markets exist on Kalshi/Polymarket (Top 5, Make Cut, H2H, round leaders, nationality props). Need "Related Futures for Tournament" endpoint. Must match by tournament key (NOT `ILIKE '%Masters%'` which leaks esports). Exclude markets already in grid columns.

### 15. Golf Evolution Chart Redesign
**Layer:** frontend | **Parallel Safety:** Green
Multiple problems: "24 Hours" and "Today" time ranges make no sense for golf, round markers needed, tournament-aware time ranges. DataGolf's evolution plot is the gold standard.

---

## Tier 4 — Someday / Maybe

- **Entity pages** (`/[sport]/[league]/[team]`) — Depends on B1. SEO upside.
- **Win totals column** in championship grid
- **Awards/props cards** on league pages (MVP, DPOY, ROY)
- **TV Mode v2** — Design complete, prototype at `docs/tv-mode-prototype.jsx`
- **"The Market Was Wrong" v2** — AI narrative generation
- **MoneyPuck for NHL** — Infrastructure ready (stub configured)
- **Related Futures Phase 5** — Bidirectional: futures detail shows relevant events
- **Non-Sports Categories** — Audit politics, entertainment, crypto, weather markets
- **iOS beyond parity** — App Store submission, widgets, background refresh, share extension, push notifications
- **Apple Watch app** — Glanceable live probabilities
- **Apple TV app** — Natural fit for TV Mode
- **Weather visualization** — Prediction market weather maps
- **"What Are the Odds?" game** — Probability guessing game

---

## Architecture Initiatives (Reference)

### B1: Site Navigation Hierarchy — NOT STARTED (see Item 8 above)

### B2: League Context Service — SHIPPED April 14-15
`LeagueContextService` in `services/league_context.py`. Redis-cached (5-min TTL), dynamic columns from `league_configs.py`. Powers Playoff Path card + team-progression endpoint.

**Remaining follow-ups:** Extract `market_discovery.py` + `team_resolution.py` from `playoffs.py` (cleanup, not blocking). Orphaned event detection.

### B3: Eval Page v2 — NOT STARTED (Tier 3)
Group by market. Three card types: market-column assignment, source disagreement, interesting futures.

### B4: Trade Volume — SHIPPED April 14-15
All 3 phases complete. Internal signal only — NEVER user-facing.

### Event Registry — SHIPPED April 16
All 5 phases. Unified event matching via `find_or_create_event()`. Removed ~430 lines of scattered dedup spaghetti.

---

## Housekeeping

- **May 1, 2026**: Delete `frontend/_to-delete/` if nothing broke
- **May 1, 2026**: Delete `docs/archive/` if nothing referenced
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches (old feature/claude branches from Jan-Mar 2026)
