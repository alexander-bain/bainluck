# Event Taxonomy & Intelligent Tagging System — Implementation Prompt

## For: Claude Code CLI sessions working on the Bain Luck codebase

---

## What We're Asking For

Build a unified, LLM-powered event and futures taxonomy system that organizes every record in our database along multiple dimensions — enabling faceted search, intelligent category pages, better ranking, and natural language queries like "show me close NBA playoff games this week" or "what college upsets happened yesterday."

Today we have ~15 classification fields scattered across Event, FuturesMarket, Sport, and Team models, plus 3+ code-level classification systems (LEAGUE_TIERS, LEAGUE_CLASS, highlight scoring) that compute classification at request time but never persist it. The taxonomy system consolidates all of this into a single queryable structure on each record, enriched by LLM intelligence that can infer contextual tags no regex will ever capture (rivalry games, elimination scenarios, Cinderella stories, legacy moments, etc.).

---

## Why We Want It

Three product capabilities unlock once taxonomy is in place:

### (a) Faceted Search & Natural Language Discovery
Users should be able to filter and discover events along any combination of dimensions. "NBA playoff games tonight" combines sport (basketball), league (NBA), competition phase (playoff), and timing (tonight). "College upsets this weekend" combines level (college), narrative (upset), and timing (weekend). Today this requires custom backend logic for every query pattern. With taxonomy, it's a GIN-indexed JSONB query.

Beyond faceted search, good taxonomy is the foundation for natural language search powered by an LLM query parser. The user types "what's the most exciting game on right now?" and the system translates that to `status=live, sort by raw_ei DESC, limit 1`. The taxonomy provides the vocabulary the query parser maps natural language onto.

### (b) Intelligent Category & Event Detail Pages
The Oscars landing page (`/oscars`) is a hand-built, heavily-customized category page. It's beautiful, but it took significant effort and only works for one event. With taxonomy, we can auto-generate rich category pages for any tag or tag combination: "March Madness," "Conference Championship Weekend," "Tonight's Primetime Games," "Rivalry Week," "Your Teams in the Playoffs." Event detail pages also get richer — the system knows "this is an elimination game in a historic rivalry between two Power 4 schools, and the home team is on a 12-game win streak."

### (c) Smarter Ranking
The highlight scoring system (`compute_highlight()`) already uses ~15 signals, but they're computed fresh every request. Persisted taxonomy tags let the feed query be `WHERE 'playoff' = ANY(tags) AND 'tier_1' = ANY(tags)` instead of joining to sports, looking up LEAGUE_TIERS dicts, and computing flags. More importantly, the LLM-generated contextual tags (rivalry, elimination, Cinderella, primetime) become ranking inputs that no amount of rule-writing would produce. A "rivalry elimination game on Monday Night Football" should rank higher than "regular season Tuesday night game between two .500 teams" — and the taxonomy makes that expressible.

---

## Current State: What Exists Today

Before building anything new, understand what classification data we already have. This is important because Phase 1 is about consolidating and persisting what we already compute, and Phase 2 adds LLM intelligence on top.

### Database Fields (already persisted)

**On Event:**
- `status` (scheduled/live/completed/closed) — indexed
- `llm_importance` (playoff/championship/regular_season/exhibition) — from ESPN `season.type`
- `llm_gender` (men/women/mixed/unknown) — LLM-classified
- `llm_level` (professional/college/amateur/youth) — LLM-classified
- `llm_league` (NFL/NBA/EPL/etc.) — LLM-classified, freeform string
- `sport_id` → FK to Sport table (canonical sport key like `basketball_nba`)
- `raw_ei` + `ei_metadata` — Excitement Index score and components
- `opening_home_probability` / `opening_away_probability` / `opening_favorite` — baseline for movement detection
- `espn_id`, `statpal_fixture_id` — external IDs enabling enrichment
- `broadcast_info` — e.g., "ESPN, ESPN+" (enables primetime detection)
- `commence_time` — enables temporal classification

**On FuturesMarket:**
- `llm_sport_category` — one of 23 categories (indexed)
- `market_tier` — 1-5 (championship → props)
- `category` — championship/mvp/division/prop/award
- `canonical_market_key` — cross-source dedup key (indexed)
- `category_tags` — JSONB array for multi-category membership (THIS IS THE CLOSEST THING TO WHAT WE WANT, but only on futures, not events)
- `llm_gender`, `llm_level`, `llm_league` — same as Event
- `source` — odds_api/kalshi/polymarket
- `event_id` — game-level market → event link
- `mutually_exclusive` — whether exactly one outcome wins

**On Sport:**
- `key` — canonical sport key (e.g., `basketball_nba`)
- `group` — sport grouping (e.g., "basketball") — underused

**On Team:**
- `location` — ESPN location field (city/region/school) for metro alias expansion
- `roster_players` — JSONB array of player names
- `standings_data`, `season_stats` — JSONB from StatPal

### Code-Level Classification (computed at request time, NOT persisted)

**LEAGUE_TIERS** (`highlights.py`): 4-tier system mapping ~70 sport keys to major/minor ranking weights. Tier 1 (+20 pts): NBA, NFL, MLB, NHL, EPL, La Liga, Champions League. Tier 2 (+10): NCAAF, NCAAB, WNBA, MLS, etc. Tier 3 (-5): Liga MX, boxing, etc. Tier 4 (-45): everything else.

**LEAGUE_CLASS** (`league_classification.py`): pro_major, pro_minor, college, international, other. Plus POWER_4_TEAMS set (~67 schools).

**EventFlags** (from `compute_highlight()`): 11+ boolean flags — `is_live`, `is_close_matchup`, `is_very_close`, `is_blowout`, `favorite_switched`, `is_starting_soon`, `is_starting_very_soon`, `is_recently_finished`, `is_upset`, `is_volatile`, `has_lead_changes`, `has_recent_momentum`. Also `league_tier`, `is_playoff`, `is_championship`.

**Highlight labels**: "Upset brewing", "Close game", "Line moving", "Close matchup", "Championship game", "Playoff game", "Lead change", "Odds shifting fast", "Wild game", etc.

**Frontend sportCategories.ts**: 33 categories with tiers, 100+ league display names, 200+ subcategory display names, pattern-based tier overrides.

**200+ regex patterns** in `futures_categorization.py` for rule-based sport categorization.

### External Source Classification Data

- **ESPN**: `season.type` (1=exhibition, 2=regular, 3=postseason) → maps to `llm_importance`
- **Polymarket**: Event tags (160+ tag-to-category map in `polymarket.py`)
- **Kalshi**: Category filtering (Sports, Golf, Football, etc.)
- **StatPal**: Standings data, injury reports, play-by-play

### What's Missing

1. **No `event_tags` on Event model.** FuturesMarket has `category_tags` JSONB, but Events have nothing equivalent.
2. **No contextual/narrative tags.** We don't know "this is a rivalry game" or "elimination scenario" or "Cinderella story." These require either cultural knowledge (LLM) or cross-referencing standings/series data.
3. **No competitive structure tags.** Head-to-head vs. field, single game vs. series, tournament bracket position — all inferred, never tagged.
4. **No temporal tags.** "Primetime," "weekend showcase," "opening day," "rivalry week" — computable from `commence_time` + `broadcast_info` but never persisted.
5. **No audience/accessibility tags.** "Casual-friendly," "national interest," "local interest only" — valuable for ranking but currently implicit in league tier.
6. **Code-level classification isn't queryable.** LEAGUE_TIERS, EventFlags, highlight labels — all computed per-request, never stored.

---

## Proposed Phasing

### Phase 1: Consolidate & Persist (Materialized Tags)
**Effort: 2-3 sessions. No LLM cost. No new external data.**

Add `event_tags` JSONB column to Event model (mirroring `category_tags` on FuturesMarket). Populate it from existing classification data that's currently scattered across fields or computed at request time.

**What goes in `event_tags`:**
```python
# Deterministic tags from existing fields — examples:
{
    "sport": ["basketball"],           # from sport.group or sport.key prefix
    "league": ["nba"],                 # from llm_league or sport.key
    "league_tier": ["tier_1"],         # from LEAGUE_TIERS[sport_key]
    "league_class": ["pro_major"],     # from LEAGUE_CLASS[sport_key]
    "level": ["professional"],         # from llm_level
    "gender": ["mens"],               # from llm_gender
    "importance": ["playoff"],         # from llm_importance
    "status": ["live"],               # from status field
    "market_signal": ["close_matchup", "line_moving"],  # from compute_highlight() flags
    "timing": ["primetime", "weekend"],  # from commence_time + broadcast_info
}
```

**Implementation steps:**

1. **Alembic migration**: Add `event_tags` JSONB column with GIN index to `events` table. Also add GIN index on `futures_markets.category_tags` if not already present.
   ```sql
   ALTER TABLE events ADD COLUMN event_tags JSONB DEFAULT '{}';
   CREATE INDEX ix_events_event_tags ON events USING GIN (event_tags);
   ```

2. **Tag computation utility** (`backend/app/utils/event_taxonomy.py`): Pure function `compute_event_tags(event, sport_key, highlight_result=None) -> dict` that takes an Event and returns a tag dict. Sources:
   - `sport.key` → parse prefix for sport tag, lookup LEAGUE_TIERS for tier tag, lookup LEAGUE_CLASS for class tag
   - `llm_importance` → importance tag
   - `llm_level` → level tag
   - `llm_gender` → gender tag
   - `llm_league` → league tag
   - `status` → status tag
   - `commence_time` + `broadcast_info` → timing tags (primetime = ESPN/ABC/FOX/NBC + Friday-Sunday evening; weekend = Sat/Sun; etc.)
   - If `highlight_result` provided: extract flag-based tags (close_matchup, upset, volatile, lead_changes, etc.)
   - `opening_home_probability` vs current odds → line_moving, favorite_switched tags
   - `raw_ei` → excitement tier tag (if computed): incredible/exciting/competitive/flat

3. **Celery task** (`backend/app/tasks/taxonomy.py`): `update_event_tags` task that:
   - For live events: runs every 2-5 minutes (tags change — score updates, highlight flags change)
   - For recently completed events: runs once after completion (final tags: upset result, EI label)
   - For upcoming events within 24h: runs hourly (timing tags, line movement)
   - For older events: runs daily or on-demand (backfill)
   - Can be triggered via admin endpoint for bulk backfill

4. **Also normalize `category_tags` on FuturesMarket**: Ensure futures use the same tag vocabulary and structure as events. Currently `category_tags` is a flat array of strings. Consider migrating to the same `{dimension: [values]}` dict structure as `event_tags` for consistency, OR keep the flat array and add `event_tags` as a flat array too (simpler, still GIN-queryable). **Decision: use flat array for both.** A flat array `["basketball", "nba", "tier_1", "professional", "playoff", "live", "close_matchup"]` is simpler to query with `@>` operator and matches the existing `category_tags` pattern. Dimension prefixes in the tag name provide structure without nested objects (e.g., `"tier:1"`, `"level:professional"`, `"timing:primetime"`).

   Actually — reconsider. A dict with dimension keys is more expressive for faceted search (you can query "all tier_1 events" without scanning sport tags). But it's harder to query with GIN for cross-dimension filters. **Recommendation: use a flat array with namespaced tags** like `["sport:basketball", "league:nba", "tier:1", "level:professional", "importance:playoff", "status:live", "signal:close_matchup", "timing:primetime"]`. This gives you the queryability of a flat GIN array with the semantic clarity of dimensions. You can query `event_tags @> '["sport:basketball", "importance:playoff"]'` efficiently.

5. **Wire into feed endpoint**: Replace (or supplement) the current `compute_highlight()` call with tag-based filtering where possible. Start with the simplest win: the league tier check. Instead of looking up LEAGUE_TIERS at query time, filter on `event_tags @> '["tier:1"]'`.

6. **Admin endpoints**:
   - `POST /api/admin/taxonomy/backfill?secret=any&limit=500` — Backfill tags for existing events
   - `GET /api/admin/taxonomy/status?secret=any` — Tag coverage stats (how many events have tags, distribution by dimension)
   - `GET /api/admin/taxonomy/vocabulary?secret=any` — List all unique tags currently in use and their counts

7. **Tests**: Test the `compute_event_tags()` function with various event configurations (live NBA playoff game, completed college upset, scheduled exhibition, etc.). Test GIN index queries. Test tag stability (same event produces same tags on repeated computation). Aim for 30+ tests.

8. **Update CLAUDE.md**: Add Event Taxonomy section documenting the tag format, dimensions, computation task, and admin endpoints.

**What Phase 1 enables:**
- Tag-based feed filtering (replace some highlight score computation with tag queries)
- Admin visibility into how events are classified
- Foundation for Phase 2 LLM enrichment
- Simple frontend filters (e.g., "show only playoff games" = `event_tags @> '["importance:playoff"]'`)

**What Phase 1 does NOT do:**
- No new intelligence — tags are derived from existing fields only
- No contextual tags (rivalry, elimination, Cinderella)
- No natural language search
- No category landing pages

---

### Phase 2: LLM Enrichment (Contextual Intelligence)
**Effort: 3-4 sessions. LLM cost: ~$1-3/day at current volume.**

Add LLM-generated contextual tags that capture narrative, stakes, audience, and cultural significance — things no regex or field lookup can determine.

**Tag dimensions to add (LLM-generated):**

```
Dimension 8: "stakes" — What's on the line?
  Examples: elimination, clinching, seeding, meaningless, must_win,
            playoff_implications, relegation, promotion, title_defense

Dimension 9: "narrative" — What story is this game telling?
  Examples: rivalry, historic_rivalry, revenge_game, cinderella,
            upset_alert, comeback, legacy_moment, debut, return_from_injury,
            farewell_tour, record_chase, streak (win/loss), rematch,
            david_vs_goliath, redemption

Dimension 10: "audience" — Who cares about this?
  Examples: national_interest, local_interest, casual_friendly,
            hardcore_only, crossover_appeal, viral_potential

Dimension 11: "competitive_structure" — How is the competition organized?
  Examples: head_to_head, field, bracket, series, round_robin,
            single_elimination, best_of_7, group_stage, knockout,
            individual_vs_individual, team_vs_team
```

**Implementation steps:**

1. **LLM tagging function** in `backend/app/services/llm.py`: `generate_event_tags(event_context: dict) -> dict` that takes enriched event context and returns contextual tags. The prompt should:
   - Receive: team names, sport, league, importance, current odds, opening odds, commence_time, broadcast_info, standings_data (if available from StatPal), series info (if available), team records, recent results context
   - Return: structured JSON with tags for stakes, narrative, audience, competitive_structure dimensions
   - Use GPT-4o-mini (cheap, fast, good enough for classification)
   - Include 5-10 few-shot examples in the prompt covering different sports and scenarios
   - Instruct the LLM to ONLY use tags from a provided vocabulary (prevents tag drift/hallucination)

2. **Tag vocabulary management**: Define a canonical set of allowed tags per dimension in a Python dict (`ALLOWED_TAGS` in `event_taxonomy.py`). The LLM prompt includes this vocabulary. Any LLM-returned tag not in the vocabulary is dropped. This prevents tag proliferation while still letting the LLM choose intelligently among options.

3. **Enrichment context assembly**: Before calling the LLM, assemble the richest possible context for the event:
   - Team records from `teams.current_record`
   - Standings from `teams.standings_data` (StatPal)
   - ESPN injuries/news from `espn_api.get_event_context()`
   - Series/bracket context if available
   - Historical matchup data if we have it (previous events between same teams)
   - The team's futures odds (championship probability provides "stakes" context — a 45% title favorite losing matters more than a 2% longshot)

4. **Celery task updates** (`taxonomy.py`):
   - LLM tagging runs ONCE per event lifecycle stage transition: (a) when event is first created/discovered, (b) when event goes live, (c) when event completes. NOT on every poll cycle — LLM tags are stable within a lifecycle stage.
   - Deterministic tags (Phase 1) still update frequently for live events.
   - LLM tags are merged into the same `event_tags` array alongside deterministic tags. Namespace prefix `"narrative:"`, `"stakes:"`, etc. distinguishes them.
   - Cache LLM results — don't re-tag an event that already has LLM tags for its current lifecycle stage.

5. **Cost management**:
   - GPT-4o-mini at ~500 tokens per event = ~$0.00015/event
   - ~500-1000 events/day across all sports = $0.075-0.15/day for event tagging
   - Futures markets: tag on creation only (they don't change lifecycle stages as often) = ~100-200/day = $0.015-0.03/day
   - Total: well under $1/day. Can scale to 10x before cost becomes meaningful.

6. **Also tag FuturesMarket**: Apply the same LLM enrichment to futures. Relevant dimensions: stakes (championship vs. prop), narrative (Cinderella team in championship market), audience (national vs. niche).

7. **Fallback and validation**:
   - If LLM call fails, event still has Phase 1 deterministic tags (graceful degradation)
   - Validate LLM output against allowed vocabulary before persisting
   - Log unexpected/rejected tags for vocabulary expansion review
   - Admin endpoint to review LLM tagging quality: show sample of recently tagged events with their full tag arrays

8. **Tests**: Test LLM prompt with mocked responses. Test vocabulary validation (reject unknown tags). Test lifecycle-stage caching (don't re-tag). Test context assembly. Test graceful degradation when LLM unavailable. 20+ tests.

**What Phase 2 enables:**
- Rich contextual tags on every event (rivalry, elimination, Cinderella, etc.)
- Narrative-aware ranking (rivalry + elimination + primetime = massive boost)
- Foundation for natural language search and category pages
- "Why is this interesting?" explanations derived from tags

**What Phase 2 does NOT do:**
- No user-facing search UI yet
- No category landing pages yet
- No query parser for natural language

---

### Phase 3: Query Layer & Search (Faceted Discovery)
**Effort: 3-4 sessions. No additional LLM cost beyond Phase 2.**

Build the API endpoints and frontend UI that let users discover events through taxonomy.

**Implementation steps:**

1. **Faceted search API endpoint**: `GET /api/events/discover` (or extend existing `/api/events` with tag filter params)
   ```
   GET /api/events/discover?tags=sport:basketball,importance:playoff&status=live&sort=ei_desc
   GET /api/events/discover?tags=narrative:rivalry,timing:primetime&limit=10
   GET /api/events/discover?tags=level:college,narrative:upset&status=completed&since=24h
   ```
   - Uses GIN index: `WHERE event_tags @> ARRAY['sport:basketball', 'importance:playoff']`
   - Combine with existing filters (status, commence_time range, sport_id)
   - Return tag facet counts in response: `{"facets": {"importance": {"playoff": 12, "championship": 3, "regular_season": 45}, ...}}`

2. **Natural language search endpoint**: `GET /api/events/search-nl?q=close NBA playoff games tonight`
   - LLM query parser: takes natural language, returns structured tag query + time filter + sort preference
   - Prompt includes the tag vocabulary so the LLM maps user language to valid tags
   - Falls back to existing trigram text search if tag mapping fails
   - Cost: one GPT-4o-mini call per search query (~$0.0001 per search, negligible)

3. **Tag browsing endpoint**: `GET /api/taxonomy/browse`
   - Returns the tag vocabulary organized by dimension, with current event counts per tag
   - Enables the frontend to build filter dropdowns/chips dynamically
   - Cache aggressively (tag counts change slowly)

4. **Frontend: filter bar on homepage**
   - Horizontal chip/pill bar below the header with quick filters: "Playoffs", "Live", "Rivalry", "Upsets", "Your Sports"
   - Tapping a filter adds it to the active tag query
   - Multiple filters combine with AND
   - Show result count updating as filters are toggled
   - Consider a "More Filters" expandable panel with all dimensions

5. **Frontend: enhanced search**
   - SearchBar.tsx already has typeahead. Extend it to parse known tag patterns: typing "NBA playoffs" should add tag filters, not just text search.
   - Natural language queries ("what's the most exciting game right now?") hit the NL search endpoint.

6. **Tests**: Test faceted query construction. Test NL query parser with diverse inputs. Test facet count aggregation. Test filter combination logic. 25+ tests.

---

### Phase 4: Category Pages & Ranking Integration (Product Polish)
**Effort: 3-5 sessions.**

Build auto-generated category landing pages and integrate taxonomy into the feed ranking system.

**Implementation steps:**

1. **Category page route**: `/category/[...tags]` (catch-all route)
   - `/category/basketball/nba` → all NBA events + futures
   - `/category/narrative/rivalry` → all rivalry games across sports
   - `/category/timing/primetime` → tonight's primetime games
   - `/category/importance/playoff` → all playoff games
   - Each page auto-generates: hero section, event cards filtered by tags, relevant futures, tag-aware context text

2. **"Collections" or "Moments" pages**: Curated tag combinations with editorial names
   - "March Madness" = `level:college + sport:basketball + importance:playoff`
   - "Rivalry Week" = `narrative:rivalry + timing:this_week`
   - "Championship Sunday" = `importance:championship + timing:today`
   - Define these as a small config (name → tag combination). The page content is auto-generated from the tag query.

3. **Taxonomy-informed ranking**:
   - Add tag-based scoring to `compute_highlight()` or its replacement
   - Narrative tags get scoring weights: `rivalry` +10, `elimination` +15, `cinderella` +10, `primetime` +5
   - Stakes tags: `must_win` +10, `clinching` +10, `meaningless` -10
   - Audience tags: `national_interest` +10, `casual_friendly` +5 (for anonymous users)
   - These supplement (don't replace) existing highlight scoring — the taxonomy makes the ranking inputs richer

4. **Event detail page enrichment**:
   - Show relevant tags as badges/pills on the event detail page
   - "Rivalry Game · Playoff · Primetime · National Interest"
   - Use tags to select which context to emphasize (rivalry → show head-to-head history, elimination → show series status, Cinderella → show seed/ranking)

5. **"What's Interesting Right Now?" widget**:
   - Uses taxonomy to generate a 1-2 sentence answer: "3 playoff games live, including a historic rivalry where the underdog leads. Plus: a Cinderella run in March Madness."
   - LLM generates from the current tag distribution, cached for 5 minutes

---

## What Success Looks Like

### Phase 1 Success
- Every event in the database has an `event_tags` array with 5-15 deterministic tags
- Tags are queryable via GIN index with <50ms query time
- Admin dashboard shows tag coverage: >95% of events tagged, tag distribution makes sense
- Feed endpoint uses at least one tag-based filter (replacing a code-level dict lookup)
- No regressions in feed latency or quality

### Phase 2 Success
- Live and upcoming events have contextual tags (narrative, stakes, audience) within 2 minutes of creation or status change
- LLM tagging accuracy >90% (validated by manual spot-check of 50+ events across sports)
- Tag vocabulary is stable — fewer than 5% of LLM-generated tags are rejected by vocabulary validation per week
- The "rivalry" tag correctly identifies 80%+ of well-known rivalries (Yankees/Red Sox, Michigan/Ohio State, etc.)
- Cost stays under $3/day

### Phase 3 Success
- Users can filter the feed by any tag dimension with sub-200ms response time
- Natural language search correctly parses 70%+ of common queries into tag filters
- Facet counts are accurate and update within 5 minutes of event changes
- Frontend filter bar is used by >10% of sessions (measured via GA4)

### Phase 4 Success
- At least 3 auto-generated category pages live (e.g., March Madness, Rivalry Games, Primetime)
- Taxonomy-informed ranking measurably improves feed quality (measured by engagement: click-through rate, time on page)
- Event detail pages show contextual tags that users find valuable (measured by scroll depth on enriched pages vs. non-enriched)

---

## Failure States to Watch For

### Tag Drift / Vocabulary Explosion
**Risk:** LLM generates slightly different tags over time ("rivalry" vs "rival" vs "rivals_game"), creating a sparse, inconsistent vocabulary.
**Mitigation:** Strict allowed vocabulary in the LLM prompt. Validation layer rejects unknown tags. Weekly admin review of rejected tags to decide whether to expand vocabulary.

### Stale Tags
**Risk:** Tags computed at event creation become wrong by game time (e.g., "meaningless" game becomes "clinching" due to other results).
**Mitigation:** Re-tag at lifecycle transitions (created → live → completed). For standings-dependent tags, also re-tag when standings data updates (daily). Flag events whose tags might be stale with a `tags_computed_at` timestamp.

### LLM Hallucination in Tags
**Risk:** LLM tags a random Tuesday game as "historic rivalry" when it isn't, or misidentifies an elimination scenario.
**Mitigation:** Few-shot examples in the prompt. Vocabulary constraint. For high-stakes tags (elimination, clinching), consider requiring corroborating data (standings confirm elimination scenario before the tag is allowed). Audit task (like existing matching audits) samples tagged events and verifies with LLM.

### Performance Regression
**Risk:** GIN index on JSONB doesn't perform as well as expected at scale, slowing feed queries.
**Mitigation:** Benchmark with realistic data volume before shipping to production. Consider a separate `event_tag_index` table with (event_id, tag) rows if GIN performance is insufficient — this gives you a traditional B-tree index on the tag column. Test with 100K+ events.

### Over-Indexing on Tags for Ranking
**Risk:** Tags become the primary ranking signal, and a misclassified tag (wrong importance, wrong narrative) causes a bad event to surface prominently.
**Mitigation:** Tags supplement existing highlight scoring, not replace it. The highlight score remains the primary sort key; tags add bonus points. Cap tag-based bonus at +30 points (less than the live-game base score of 30).

### Cost Creep
**Risk:** LLM tagging cost grows as event volume increases, or prompt engineering leads to longer prompts.
**Mitigation:** Tag per lifecycle stage, not per poll cycle. Cache aggressively. Monitor daily cost via OpenAI dashboard. Set hard budget alert at $5/day. GPT-4o-mini is already the cheapest viable model.

### Taxonomy Becomes Stale
**Risk:** The tag vocabulary was designed for the sports we cover today. New sports, new event types (e.g., esports tournaments have very different structures), or new Polymarket categories don't fit the existing dimensions.
**Mitigation:** The vocabulary is a Python dict, not a database table — easy to update. Quarterly review of rejected tags and uncategorized events to identify gaps. The LLM naturally handles novel events better than rules — the vocabulary just constrains it.

---

## Implementation Details to Consider

### Tag Format Decision
**Recommended: Namespaced flat array.**
```python
["sport:basketball", "league:nba", "tier:1", "level:professional",
 "importance:playoff", "status:live", "signal:close_matchup",
 "narrative:rivalry", "stakes:elimination", "audience:national_interest",
 "timing:primetime", "timing:weekend", "structure:head_to_head",
 "structure:best_of_7", "ei:exciting"]
```

**Why flat array over nested dict:**
- GIN index on JSONB arrays is well-optimized in PostgreSQL
- `@>` containment operator works perfectly: `event_tags @> ARRAY['sport:basketball', 'importance:playoff']`
- Simpler to merge deterministic + LLM tags (just concatenate arrays, deduplicate)
- Matches existing `category_tags` pattern on FuturesMarket
- Frontend can parse namespace with `tag.split(':')` for display grouping

**Why namespaced over bare tags:**
- Avoids ambiguity ("close" = close matchup? close to starting? market closing?)
- Enables dimension-specific queries (all `narrative:*` tags)
- Self-documenting

### Alembic Migration Considerations
- Column name: `event_tags` (not `tags` — too generic, could conflict)
- Default: `'[]'::jsonb` (empty array, not NULL — simplifies queries)
- GIN index: `CREATE INDEX ix_events_event_tags ON events USING GIN (event_tags jsonb_path_ops)` — `jsonb_path_ops` is faster for `@>` containment queries than the default GIN opclass
- Migration must be ≤32 char revision ID (see CLAUDE.md gotcha #2)
- Consider also adding the index on `futures_markets.category_tags` if it doesn't exist

### FuturesMarket Tag Alignment
The existing `category_tags` on FuturesMarket is a flat array without namespaces (e.g., `["basketball", "nba", "championship"]`). For consistency:
- **Option A**: Migrate `category_tags` to namespaced format (`["sport:basketball", "league:nba", "category:championship"]`) — cleaner, but requires updating all write paths (polymarket.py, kalshi.py, futures.py, futures_categorization.py).
- **Option B**: Keep `category_tags` as-is, add a new `market_tags` column with the namespaced format — avoids migration risk but creates inconsistency.
- **Option C**: Keep `category_tags` as-is for now, add `event_tags` on Events with namespaced format, align later — pragmatic, ships faster.
- **Recommendation: Option C** for Phase 1. Align in Phase 2 or later. Don't let schema consistency block the event-side work.

### Celery Task Architecture
- New task module: `backend/app/tasks/taxonomy.py`
- Beat schedule entry: `update-event-tags` every 2 minutes (only processes events that need tagging)
- Use Redis gating pattern (like `poll_all_odds`) to avoid redundant work
- Redis key per event: `bainluck:tags:{event_id}:stage:{status}` — skip if already tagged for current lifecycle stage
- For Phase 2 LLM tagging: separate Redis key `bainluck:llm_tags:{event_id}:stage:{status}` with longer TTL
- Backfill task for existing events (admin-triggered, process in batches of 100)
- The task should be instrumented with `_tracked_run()` for the Celery dashboard

### Integration with compute_highlight()
- Phase 1: `compute_event_tags()` and `compute_highlight()` are independent — tags are written by the Celery task, highlights are computed at query time. Some tags derive from highlight flags (close_matchup, upset, volatile), so the tag task needs to call `compute_highlight()` internally.
- Phase 3+: Consider replacing `compute_highlight()` with a tag-based scoring function that reads `event_tags` instead of recomputing flags. This would be a significant refactor — plan carefully and ensure no regressions.

### Frontend Considerations
- The `event_tags` array should be included in the event API response (already returned for futures as `category_tags`)
- Frontend can use tags for display (badges, filter chips) without parsing the event object itself
- Tag display names: maintain a frontend map (`TAXONOMY_DISPLAY_NAMES` in a new `lib/taxonomy.ts`) that maps tags like `"narrative:rivalry"` to display text like "Rivalry Game"
- Filter state: URL query params (e.g., `?tags=sport:basketball,importance:playoff`) for shareable filtered views

### LLM Prompt Design (Phase 2)
The prompt is the most important artifact in this project. It should:
- Define each dimension with 2-3 sentence explanation of what it captures
- List all allowed tags per dimension with brief definitions
- Include 8-12 few-shot examples spanning: major pro sport regular season, major pro sport playoff, college game, individual sport (tennis/golf), combat sport (MMA/boxing), non-sports (politics/entertainment), rivalry, blowout, upset, Cinderella, high-stakes, meaningless
- Instruct: "Return ONLY tags from the provided vocabulary. If no tag in a dimension applies, omit that dimension. Do not invent new tags."
- Instruct: "For the 'narrative' dimension, only assign tags you are confident about. It is better to return no narrative tag than to guess wrong."
- Use structured JSON output: `{"stakes": ["elimination"], "narrative": ["rivalry", "revenge_game"], "audience": ["national_interest"], "structure": ["best_of_7"]}`
- Keep prompt under 1500 tokens for cost efficiency

### Tag Vocabulary — Proposed Starting Set

**Dimension 1: sport** (deterministic, from sport_key prefix)
`basketball`, `football`, `baseball`, `hockey`, `soccer`, `tennis`, `golf`, `mma`, `boxing`, `cricket`, `rugby`, `aussierules`, `motorsports`, `horse_racing`, `lacrosse`, `esports`, `olympics`, `politics`, `entertainment`, `crypto`, `economics`, `weather`, `other`

**Dimension 2: league** (deterministic, from llm_league or sport_key)
`nba`, `nfl`, `mlb`, `nhl`, `ncaab`, `ncaaf`, `wnba`, `wncaab`, `mls`, `epl`, `la_liga`, `champions_league`, `bundesliga`, `serie_a`, `ligue_1`, `liga_mx`, `ufc`, `pga`, `atp`, `wta`, `f1`, `nascar`, `ipl`, `fifa_world_cup`, etc. (extensible)

**Dimension 3: tier** (deterministic, from LEAGUE_TIERS)
`1`, `2`, `3`, `4`

**Dimension 4: level** (deterministic, from llm_level)
`professional`, `college`, `amateur`, `youth`

**Dimension 5: gender** (deterministic, from llm_gender)
`mens`, `womens`, `mixed`

**Dimension 6: importance** (deterministic, from llm_importance)
`championship`, `playoff`, `regular_season`, `exhibition`, `preseason`, `all_star`

**Dimension 7: signal** (deterministic, from highlight flags — live events only)
`close_matchup`, `very_close`, `blowout`, `upset`, `upset_brewing`, `favorite_switched`, `line_moving`, `volatile`, `lead_changes`, `momentum_shift`, `starting_soon`, `just_finished`

**Dimension 8: timing** (deterministic, from commence_time + broadcast_info)
`primetime`, `weekday`, `weekend`, `morning`, `afternoon`, `evening`, `night`, `holiday`, `opening_day`, `season_finale`, `rivalry_week`

**Dimension 9: ei** (deterministic, from raw_ei score)
`incredible`, `must_watch`, `exciting`, `engaging`, `competitive`, `average`, `quiet`, `flat`

**Dimension 10: stakes** (LLM-generated, Phase 2)
`elimination`, `clinching`, `must_win`, `playoff_implications`, `seeding`, `relegation`, `promotion`, `title_defense`, `meaningless`, `tank_watch`

**Dimension 11: narrative** (LLM-generated, Phase 2)
`rivalry`, `historic_rivalry`, `revenge_game`, `cinderella`, `david_vs_goliath`, `upset_alert`, `comeback`, `legacy_moment`, `debut`, `return_from_injury`, `farewell_tour`, `record_chase`, `streak`, `rematch`, `redemption`, `trap_game`

**Dimension 12: audience** (LLM-generated, Phase 2)
`national_interest`, `regional_interest`, `local_only`, `casual_friendly`, `hardcore`, `crossover_appeal`, `viral_potential`

**Dimension 13: structure** (deterministic + LLM, Phase 2)
`head_to_head`, `field`, `bracket`, `series`, `round_robin`, `single_elimination`, `best_of_7`, `best_of_5`, `group_stage`, `knockout`, `medal_round`

---

## Product Changes to Consider After Each Phase

### After Phase 1 (Deterministic Tags)
- **Frontend quick filters**: Add filter chips on homepage feed ("Playoffs", "Live Now", "Tier 1 Only", "College"). These are simple tag queries.
- **Feed endpoint tag parameter**: `GET /api/feed?tags=importance:playoff,tier:1` — enable frontend filtering without new endpoints.
- **Admin taxonomy dashboard**: Page showing tag coverage, distribution, and event samples per tag. Useful for debugging and monitoring.
- **Consider**: Should the existing `/api/events?sport=basketball_nba` parameter be supplemented or replaced by tag-based filtering? Probably supplemented initially — don't break existing API consumers.

### After Phase 2 (LLM Enrichment)
- **"Why this is interesting" text**: Generate from tags. An event tagged `narrative:rivalry, stakes:elimination, audience:national_interest` gets: "Historic rivalry, elimination game, national spotlight." This replaces or enhances the current `feed_reasons.py` logic.
- **Richer EventCard display**: Show 1-2 tag badges on each card ("Rivalry · Elimination" or "Cinderella · Upset Alert"). Visual hierarchy: narrative tags are most interesting to display.
- **Push notification targeting** (future, for iOS app): "Your team is in an elimination game tonight" — tag-triggered notifications.
- **Consider**: Run a 2-week LLM tagging audit (like the existing matching audits) before building UI on top of tags. Verify quality before exposing to users.

### After Phase 3 (Faceted Search)
- **Filter-driven navigation**: Replace or supplement sport tabs with tag-based navigation. Instead of "NBA | NFL | MLB" tabs, consider "Sports | Playoffs | Rivalry Games | Tonight" or a combination.
- **Search enhancement**: SearchBar should show tag suggestions as the user types ("playoffs" shows a "Filter: Playoffs" chip alongside event results).
- **Shareable filtered views**: URL like `bainluck.com/?tags=sport:basketball,narrative:rivalry` that can be shared. The page title updates: "Basketball Rivalry Games — Bain Luck."
- **Consider**: A/B test filter bar adoption. Some users may find filters overwhelming. Start with 3-4 high-value filters, expand based on usage.

### After Phase 4 (Category Pages & Ranking)
- **Bespoke category landing pages**: `/march-madness`, `/rivalry-week`, `/primetime` — beautiful, auto-generated pages that rival the hand-built Oscars page.
- **"What to Watch" widget**: A summary card at the top of the homepage: "3 rivalry games tonight, including a potential elimination in the NBA playoffs. Plus: a Cinderella run in March Madness."
- **Personalized tag boosting**: User preferences influence which tags get ranking boosts. A user who follows college basketball sees `level:college` events boosted. A casual user sees `audience:casual_friendly` events boosted.
- **Tag-based notifications**: "Notify me when there's an upset" or "Alert me for all elimination games" — tag-subscriptions for push notifications.
- **Consider**: Landing pages for non-sports categories using the same system: `/politics` shows all political prediction markets with taxonomy-driven layout, `/entertainment` shows Oscars + box office + reality TV.

---

## CLAUDE.md Updates Required

After implementing each phase, update the CLAUDE.md file with:

1. **New section: "Event Taxonomy System"** — Add after the "Matching Quality Audits" section in Key Features. Include:
   - Tag format explanation (namespaced flat array)
   - Full tag vocabulary by dimension
   - How tags are computed (deterministic vs. LLM)
   - Celery task schedule
   - Admin endpoints
   - Files involved

2. **Update "Database Schema" section** — Add `event_tags` column to the events table description.

3. **Update "Key Files" table** — Add:
   - `backend/app/utils/event_taxonomy.py` — Tag computation (deterministic + LLM)
   - `backend/app/tasks/taxonomy.py` — Tag update Celery task
   - `frontend/lib/taxonomy.ts` — Tag display names and frontend utilities

4. **Update "Current Priorities" section** — Add taxonomy phases to the appropriate priority level.

5. **Update "Common Tasks" section** — Add:
   - "Check taxonomy status": `curl "https://api.bainluck.com/api/admin/taxonomy/status?secret=any"`
   - "Backfill event tags": `curl -X POST "https://api.bainluck.com/api/admin/taxonomy/backfill?secret=any&limit=500"`
   - "View tag vocabulary": `curl "https://api.bainluck.com/api/admin/taxonomy/vocabulary?secret=any"`

6. **Update test coverage notes** — Add taxonomy test counts.

7. **Update "Gotchas & Tips"** — Add:
   - "Event tags use namespaced flat arrays (e.g., `sport:basketball`), not nested dicts. Use `@>` for containment queries with the `jsonb_path_ops` GIN index."
   - "LLM tags are generated per lifecycle stage (created/live/completed), not per poll cycle. Check `bainluck:llm_tags:{event_id}:stage:{status}` Redis key before re-tagging."
   - "The tag vocabulary is defined in `event_taxonomy.py` ALLOWED_TAGS dict. To add new tags, update this dict AND the LLM prompt. Never add tags to the LLM prompt without adding them to ALLOWED_TAGS."

---

## Summary for the Implementer

**Start with Phase 1.** It's 2-3 sessions of work with zero LLM cost and immediate value. The key deliverables are:
1. Alembic migration adding `event_tags` JSONB + GIN index
2. `compute_event_tags()` utility function
3. Celery task to populate tags
4. Admin endpoints for monitoring
5. At least one feed query optimization using tags
6. 30+ tests

**Then Phase 2** adds the LLM magic. The key deliverable is the LLM prompt — spend real time on this. Test it against 50+ diverse events before deploying. The infrastructure (Celery task updates, caching, validation) is straightforward once the prompt is right.

**Phases 3-4** are product phases that build on the data foundation. They can be prioritized against other product work.

**The single most important design decision is the tag format.** Namespaced flat array in JSONB with `jsonb_path_ops` GIN index. This decision cascades into everything else — queries, API design, frontend display, LLM output format. Get this right and the rest follows naturally.

**The single biggest risk is tag quality.** Bad tags are worse than no tags — they'll surface wrong events and erode trust. Validate rigorously, audit regularly, and start conservative (fewer tags with high confidence > many tags with uncertain accuracy).
