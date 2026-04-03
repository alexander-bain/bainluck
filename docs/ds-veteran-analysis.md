# What a 20-Year DS Veteran Would Do With the BainLuck Database

## Context
If a seasoned data scientist got access to our DB, what analyses would excite them as a sports fan, as a product expert, and what advice would they give to make future analyses easier? This isn't a code implementation plan — it's a strategic analysis of the analytical goldmine sitting in the database and the gaps preventing us from exploiting it fully.

---

## Part 1: The Sports Fan Analyses ("This data is incredible")

### 1. "Who's Right?" — Source Accuracy Leaderboard
**The single most exciting analysis.** You have independent probability estimates from 6+ sources (sportsbooks, ESPN model, BainLuck stat model, Kalshi, Polymarket, MLB Stats API) on the same events. For every completed game, compute the **Brier score** of each source's pre-game probability against the actual outcome. Segment by sport, game importance, and how close the game was. This answers: Is ESPN's model better than the sportsbook consensus? Are prediction markets sharper for NBA but worse for NFL? Is the BainLuck aggregate better than any single source?

**Why it's a big deal:** This is publishable-quality research. FiveThirtyEight built a brand on exactly this kind of analysis. BainLuck could become the authority on "which probability source to trust."

**Data already exists:** `win_prob_snapshots` (per-source), `events` (outcome), `odds_snapshots` (per-bookmaker). Just needs the query.

### 2. "Source Disagreement as Alpha"
When sources disagree by >10pp on the same game, who turns out to be right — the outlier or the consensus? The `win_probability_sources` JSONB already captures the latest reading per source. Cross-reference with outcomes to test whether "smart money" (the contrarian source) has predictive value.

**Blog post title:** "When the Models Disagree, Who Should You Believe?"

### 3. Excitement Index Archaeology
The EI (total probability travel distance + lead changes + comeback factor) creates a structured drama dataset.

- **"Most Exciting Games of 2025-26"** — Trivial query on `raw_ei DESC`. Great content.
- **"Do Upsets Produce More Exciting Games?"** — Correlate opening odds with EI. Hypothesis: toss-up games are more exciting than blowouts, but massive upsets (20% favorite wins) are the *most* exciting.
- **"Sport-by-Sport Drama Profiles"** — Compare EI distributions across NBA, NFL, MLB, NHL. Does hockey produce more consistently close games? Does baseball have more variance?

### 4. The Shape of Comebacks
Combine `scoring_plays` + `win_prob_snapshots` to reconstruct the full narrative arc of every game. Find games where the eventual winner's probability dipped below 15%, then trace which specific plays drove the comeback. This is FiveThirtyEight-style win probability charts, but annotated with play-by-play.

**Why this matters for the product:** If you can identify the "turning point play" algorithmically, that's a feature — "The play that changed everything: LeBron's 3-pointer at 4:32 in Q4 swung win probability from 22% to 51%."

### 5. Futures Season Arcs
`futures_odds_snapshots` tracks championship/award odds over time per bookmaker and prediction market. Chart how a team's championship probability evolved through the season. Overlay with key events (injuries via `scoring_plays` context, trade deadlines, win streaks). This is the "stock ticker for sports" — something no consumer product does well today.

**Blog post title:** "The Rise and Fall of Championship Contenders, Told in Odds"

### 6. Bookmaker Behavioral Fingerprints
With per-bookmaker data in `odds_snapshots`, you can characterize each bookmaker's behavior:
- Who moves first? (leader vs. follower)
- Who has the tightest vig? (market confidence proxy)
- Who's systematically biased toward home teams?
- Do DraftKings and FanDuel converge over time, or do they stay independent?

### 7. Home Field Advantage Quantification
With `venues`, `events`, and `opening_home_probability`, measure actual home win rate minus expected home win probability, by sport and by venue. Which arenas have the biggest home field advantage *after controlling for team quality*?

### 8. Prediction Market vs. Sportsbook Efficiency (Futures)
For resolved futures outcomes (`is_winner = true`), compare opening probabilities from Kalshi/Polymarket vs. sportsbook consensus. Are prediction markets systematically over-confident on longshots? Do they have informational advantages for certain market types (politics-adjacent like awards, vs. pure sports)?

---

## Part 2: The Product Expert Analyses ("Here's what you're missing")

### 9. The Glaring Gap: No User Behavior Data
**This is the single biggest finding.** You compute feed scores, personalization multipliers, and EI badges — but you never learn what users actually do. You have zero click-through data, zero dwell time, zero scroll depth from your own backend. GA4 captures some of this on the frontend, but it's not queryable alongside your odds/events data.

**What you need (a new table):**
```
analytics_events:
  user_id (nullable), session_id, event_type, target_type, target_id,
  metadata (JSONB: feed_position, score, reason, sport_key, personalized, etc.),
  created_at
```

Event types: `feed_impression`, `card_tap`, `detail_view`, `chart_interaction`, `source_toggle`, `pin`, `share`, `search`

Without this, every product question is unanswerable: Does EI drive engagement? Does personalization help? Which feed reasons work? What's the conversion funnel?

### 10. Personalization: Tuned or Guessed?
The personalization weights (`FOLLOW_BONUS=0.8`, `RIVAL_LOSING_BONUS=0.5`, `NAH_AFFINITY_PENALTY=-0.6`) are hand-tuned constants. A veteran would immediately ask: "Are these calibrated from user behavior data?" No — they're guesses. With analytics events (#9), you could learn optimal weights via a simple logistic regression on click probability.

**Suggested A/B tests (when you have the instrumentation):**
- Personalized feed vs. unpersonalized: does session duration increase?
- Aggressive "Nah" suppression vs. soft suppression: do users discover new interests when you occasionally surface non-preferred sports?
- Rival schadenfreude: are rival-losing items actually tapped more often?

### 11. Feed Effectiveness Metrics
**What % of items with score >= X actually get seen?** (Requires scroll tracking.)
**What's the CTR by item type?** (Events vs. futures, live vs. scheduled, with EI badge vs. without.)
**Does the "reason" text matter?** (Compare CTR on items with compelling reasons vs. generic ones.)
**Diversity constraints: do they help or hurt?** (The feed enforces sport diversity — but does it improve session engagement vs. pure relevance ranking?)

### 12. EI Validation
The Excitement Index is a carefully designed metric, but it's never been validated against user perception. A veteran would want to know:
- Do high-EI games get more page views?
- Do users who discover games via EI badges come back more often?
- Is EI calibrated well cross-sport? (A "75 EI" NBA game should feel as exciting as a "75 EI" MLB game.)

Without analytics events, the best proxy is correlating EI with social media mentions or TV viewership (external data).

### 13. Data Quality Health Dashboard
Track these continuously:
- **Odds freshness**: % of live events with at least one odds snapshot in the last 5 minutes
- **Source coverage by sport**: Which sources are providing data for which sports right now?
- **Team identity matching rate**: % of events with both `home_team_id` and `away_team_id` linked (unlinked = no personalization, no logos)
- **EI computation coverage**: % of completed events with non-NULL `raw_ei`
- **Opening odds capture rate**: % of events that have `opening_home_probability` set before game start

---

## Part 3: Infrastructure Advice ("Here's what to fix")

### Priority 1: Schema Additions That Unlock 80% of Analyses

#### A. `ended_at` on `events`
Currently game end time comes from `statpal_end_time` (nullable, not always populated). Many analyses need "how long did this game last?" and "what was the probability at game end?" Add a materialized `ended_at` column, backfilled from StatPal or estimated from last snapshot timestamp.

#### B. `final_home_probability` / `final_away_probability` on `events`
Store the last known aggregate probability before game end. This enables instant upset detection, Brier score computation, and "how wrong were the markets?" queries without re-aggregating from snapshots every time.

#### C. `event_results` summary table (or denormalized columns)
Every analytical query repeats `CASE WHEN home_score > away_score THEN 'home' ELSE 'away' END`. Materialize this:
- `winner` (home/away/draw)
- `final_margin` (absolute score difference)
- `is_upset` (opening favorite lost)
- `total_points`
- `ei_percentile`

#### D. `season` column on `events`
You have ~2 months of data. When you have 2+ seasons, every cross-season analysis will require deriving the season from `commence_time` + sport-specific season boundaries. Add `season TEXT` now (e.g., '2025-26', '2026') — costs nothing, saves major pain later.

#### E. `sport_group` on `events` (denormalized from `sports`)
Many queries want "all basketball" or "all football" but have to join through `sports` and pattern-match on `key LIKE 'basketball%'`. Denormalize as `sport_group` (basketball, football, baseball, hockey, soccer, golf, etc.).

### Priority 2: Fix Technical Debt That Blocks Analysis

#### F. Normalize `ei_metadata` from Text to proper columns
`ei_metadata` is stored as a `Text` field containing JSON (not even JSONB). Every query touching `lead_changes` or `comeback_factor` requires `::json->>` casting. Since EI metadata has a fixed schema, promote to columns:
- `ei_lead_changes INTEGER`
- `ei_comeback_factor NUMERIC(5,4)`
- `ei_snapshot_count INTEGER`

#### G. Standardize all timestamps to TIMESTAMPTZ
Some tables use `DateTime` without timezone (`created_at` on `events`, `odds_aggregated`), others use `DateTime(timezone=True)`. This creates subtle bugs in time-range queries spanning DST boundaries.

#### H. Deprecate `espn_snapshots` in favor of `win_prob_snapshots`
Both tables capture ESPN win probability. `win_prob_snapshots` is the generalized version with a `source` column. Having both creates confusion about which to query. Migrate `espn_snapshots` data into `win_prob_snapshots` (using the `game_state` JSONB for clock/period/score context) and stop writing to the old table.

### Priority 3: Preserve Data Before It's Lost

#### I. Per-bookmaker summary before snapshot collapsing
The 48-hour collapse permanently destroys per-bookmaker granularity. Before collapsing, compute and store a per-event, per-bookmaker summary:
- min/max/avg probability
- spread range
- first/last captured_at
- snapshot count

This enables the "bookmaker behavioral fingerprint" analysis (#6) on historical data.

#### J. Archive EI percentile thresholds with timestamps
`ei_percentiles` is overwritten on each recomputation. As the dataset grows, the distribution boundaries shift. Store with `computed_at` or `season` to track how game excitement evolves across seasons.

### Priority 4: Make SQL Queries Easier

#### K. Create an analytical view: `v_completed_events`
```sql
CREATE VIEW v_completed_events AS
SELECT e.*, s.key AS sport_key, s.name AS sport_name, s.group AS sport_group,
  CASE WHEN home_score > away_score THEN 'home'
       WHEN away_score > home_score THEN 'away'
       ELSE 'draw' END AS winner,
  ABS(home_score - away_score) AS final_margin,
  (home_score + away_score) AS total_points,
  CASE WHEN opening_favorite = 'home' AND away_score > home_score THEN true
       WHEN opening_favorite = 'away' AND home_score > away_score THEN true
       ELSE false END AS is_upset
FROM events e JOIN sports s ON e.sport_id = s.id
WHERE e.status IN ('completed', 'closed') AND e.home_score IS NOT NULL;
```

#### L. Add `vig` (overround) tracking to `odds_snapshots`
The vig tells you how confident bookmakers are. Tight vig (2-3%) = high confidence. Wide vig (8-10%) = uncertain. This is analytically rich and currently discarded during odds→probability conversion.

### Priority 5: Future-Proofing

#### M. Build a "golden set" of validated games
Pick 50-100 completed games across sports. Manually verify: correct final scores, correct opening odds, correct team identity, play-by-play accuracy, EI reasonableness. Use as an end-to-end data quality regression suite.

#### N. Analytics event instrumentation (backend or frontend→backend pipeline)
This is the prerequisite for all product analyses (#9-12). Even a lightweight version (log card taps with feed position and target event_id) would be transformative.

---

## Summary: The 10 Things That Matter Most

| # | Recommendation | Type | Effort | Impact |
|---|---------------|------|--------|--------|
| 1 | **Analytics events table** (user behavior tracking) | Schema + instrumentation | Medium | Unlocks ALL product analysis |
| 2 | **"Who's Right?" Brier score analysis** | Query/content | Low | Best blog post you could write; data already exists |
| 3 | **`v_completed_events` analytical view** | Schema | Low | Saves every future query from boilerplate |
| 4 | **Result columns on events** (`ended_at`, `final_home_probability`, `winner`) | Schema | Low | Enables instant upset/accuracy queries |
| 5 | **Normalize `ei_metadata`** to proper columns | Schema | Low | Technical debt; blocks easy EI analysis |
| 6 | **`season` column on events** | Schema | Trivial | Costs nothing now, prevents pain later |
| 7 | **Per-bookmaker summary before collapse** | Retention | Medium | Preserves data you're permanently losing |
| 8 | **EI validation** (does high EI = more engagement?) | Analysis | Low-Medium | Validates a core product feature |
| 9 | **Futures season arc visualizations** | Content | Low | Compelling storytelling; data already exists |
| 10 | **Source disagreement analysis** | Query/content | Low | Tests a novel hypothesis with existing data |
