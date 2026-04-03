# Related Futures API Data Quality Investigation
## Event 5541994 (Lakers vs Celtics)

### Executive Summary

I cannot directly access the production API due to network egress restrictions in this environment. However, through code analysis of `/backend/app/routes/events.py` (the `get_related_futures` endpoint), I've identified **several potential data quality issues** that could manifest in the API response. These are architectural issues, not implementation bugs.

---

## Key Findings

### 1. **Duplicate Stat Props from Different Markets** ⚠️

**Issue:** Two different futures markets can both match the same outcome name pattern, creating what appears to be duplicates to the user.

**Example:** Two separate markets in the database could exist:
- Market A: "Payton Pritchard 3-pointers" (source: DraftKings, probability: 8.5%)
- Market B: "Pritchard 3-pointers" (source: Kalshi, probability: 9.2%)

Both outcomes would be returned because:
1. Both markets are marked as "open" (line 1811)
2. Both contain "Pritchard" and "3-pointer" in the market or outcome name
3. The outcome matching uses `or_(*match_conditions)` (line 1916) which is very inclusive

**Code Location:** `backend/app/routes/events.py`, lines 1810-1917

**Current Deduplication:** The endpoint dedupes at the **outcome ID level** only (line 1956-1958):
```python
seen_ids = set()
for outcome in outcomes:
    if outcome.id in seen_ids:
        continue
    seen_ids.add(outcome.id)
```

This prevents the same outcome row from appearing twice, but **does NOT prevent different outcome rows from different markets with identical or near-identical names**.

---

### 2. **Probable Duplicate MVP Entries** ⚠️

**Issue:** Multiple sources (Kalshi, Polymarket, The Odds API) may all have "Jaylen Brown MVP" markets, each with slightly different probabilities reflecting their respective market valuations.

**Example:**
```
Market X (Kalshi): "NBA MVP Winner 2025-26" → Outcome: "Jaylen Brown" (probability: 18.5%)
Market Y (Polymarket): "NBA MVP Winner 2025-26" → Outcome: "Jaylen Brown" (probability: 19.2%)
Market Z (The Odds API): "NBA MVP 2025-26" → Outcome: "Jaylen Brown" (probability: 17.8%)
```

All three would be returned because:
1. All match the sport filter (basketball → "basketball" category)
2. All contain "Jaylen Brown" in the outcome name
3. All are "open" status

**Why This Happens:**
- The matching logic intentionally uses OR conditions to maximize recall (find ALL relevant markets)
- There is NO deduplication by market name + outcome name combo
- The endpoint expects to show price divergence across sources (a feature), but doesn't clearly label the source to the user

**Code Location:** Lines 1800-1917

---

### 3. **Game Props Matching Issues** ⚠️

**Issue:** Game props (e.g., "Celtics vs Lakers: Total Rebounds") could be incorrectly matched to team-specific markets.

**Example Problem:**
- Market: "Celtics vs Lakers: Total Rebounds > 45.5"
- This market's name contains both team names
- But it's a game stat prop, not a team-specific market
- The endpoint would still return it if outcomes in the market matched player names by coincidence

**Code Location:** Lines 1888-1905 - the market name matching logic

**Why This Matters:**
- Game props have outcomes like "Over 45.5" or "Under 45.5"
- These are generic outcome names that don't represent player/team accomplishments
- They shouldn't be displayed as "championships/awards" alongside MVP markets

---

### 4. **Non-Sports Markets Potentially Showing Up** ⚠️

**Issue:** The sport filter uses three OR conditions (lines 1800-1812):
```python
sport_filters = [
    FuturesMarket.external_id.like(f"{sport_prefix}%"),     # OddsAPI sport key
    FuturesMarket.llm_sport_category == llm_category,        # LLM category
]
if compatible_sport_ids:
    sport_filters.append(FuturesMarket.sport_id.in_(compatible_sport_ids))
```

**Problem:** If `llm_sport_category` is `NULL` or miscategorized, a market could slip through. For basketball:
- `sport_prefix = "basketball"`
- `llm_category = "basketball"`
- But a market with `external_id = "something_random"` and `llm_sport_category = NULL` would **fail all three filters and be excluded** ✓ (actually this is correct)

However, if `llm_sport_category = "entertainment"` (e.g., a mislabeled Oscars market), it would:
- Fail the `external_id` filter (no "basketball" prefix)
- Fail the `llm_sport_category` filter ("entertainment" ≠ "basketball")
- Fail the `sport_id` filter (if sport_id is NULL or wrong)
- **Be correctly excluded** ✓

So this is actually working as intended for non-sports markets.

---

### 5. **"Cover of NBA2K" and Similar Novelty Markets** ⚠️

**Issue:** Novelty/entertainment markets like "NBA Cover of NBA2K" might exist and be matched if they:
1. Have market names containing player names (e.g., "Will Jaylen Brown be on the cover?")
2. Have outcomes like "Yes" / "No"

**Example:**
- Market: "Will Jaylen Brown be on the NBA2K25 cover?"
- Outcome: "Yes" (probability: 12%)
- This would match because "Jaylen Brown" is in the market name

**Should It Show?**
- From a UX perspective: Maybe not - it's not a traditional award/championship
- Current behavior: Yes, if it passes the sport filter and the market name contains a player name

**Code Location:** Lines 1892-1905

---

### 6. **"Win Totals" Markets** ⚠️

**Issue:** Season win total markets (e.g., "Celtics 2025-26 Win Total Over/Under 52.5") would be matched if:
1. The market name contains "Celtics" (passes team name matching at line 1893-1894)
2. The outcomes are "Over 52.5" and "Under 52.5"

**Current Behavior:** These would be returned as "away_futures" (if matched to the away team) with outcome names like "Over 52.5".

**Problem:**
- The UI likely displays these as if they were player awards or championship odds
- Outcome names like "Over 52.5" don't make sense in that context
- No indication that this is a season stat, not a game-specific market

---

### 7. **Zero-Probability Markets** ⚠️

**Issue:** Awards markets with outcome probabilities near 0% could indicate:
1. **Legitimate low-probability events** (e.g., injury comeback, surprise winner)
2. **Stale/illiquid markets** (no active trading, default 50% probabilities)
3. **Resolved markets** (outcome already decided, but market not marked as "closed")

**Code Behavior:**
- The endpoint filters to `FuturesMarket.status == "open"` (line 1811)
- It does NOT filter by probability > 0
- Markets with 0% probability are still returned

**Why This Matters:**
- A 0% probability award market is useless for display
- It might indicate data quality issues upstream in the futures polling tasks

---

## Architectural Issues to Address

### Issue A: Source Transparency
**Problem:** The endpoint returns outcomes from Kalshi, Polymarket, and The Odds API without clear visual indication of source.

**Impact:** User sees "Jaylen Brown MVP: 18.5%, 19.2%, 17.8%" without knowing they're three different markets.

**Fix:** The response DOES include `"source": market.source` (line 2011), so the frontend can group or label by source. **Current code is correct** - it's a frontend display responsibility.

---

### Issue B: Outcome Name Quality
**Problem:** Outcome names vary by source:
- Kalshi: "Boston" / "Boston Celtics" (abbreviated)
- Polymarket: "Boston Celtics" / "BOS" (varies)
- The Odds API: Full name

**Impact:** Two "identical" outcomes could have slightly different names, creating UI confusion.

**Fix:** No normalization is applied in the endpoint. Consider normalizing outcome names during the polling tasks instead.

---

### Issue C: Market Name Matching is Too Broad
**Problem:** The regex at lines 1892-1905 matches ANY outcome in a market if the market name contains a team name.

**Example:** Market "Celtics vs Lakers Rebounds" with outcomes "Over 215" and "Under 215" would BOTH match to the Celtics, even though they're game stats not team-specific.

**Impact:** Game props are mixed with awards.

**Fix Needed:**
```python
# Only match outcomes in game props markets if they are actual prop outcomes
# (e.g., "Over X" / "Under X"), not "Yes" / "No" or player names
if market.category == "game_prop":
    if not _is_prop_outcome(outcome.name):
        continue
```

---

### Issue D: Duplicate Deduplication is Outcome-Level Only
**Problem:** The endpoint dedupes by outcome ID, not by (market, outcome_name) pairs.

**Impact:** Same player/award from two different markets both appear.

**Current Behavior is Actually Correct** for showing market divergence, but the frontend needs to make this clear through visual grouping/source badges.

---

## Recommendations

### Immediate Fixes (Low Effort, High Impact)

1. **Filter out zero-probability outcomes**
   ```python
   if outcome.current_probability is None or outcome.current_probability < 0.001:
       continue
   ```
   **Location:** Before line 1955

2. **Filter out game prop outcomes with non-award outcome names**
   ```python
   if market.category == "game_prop":
       if outcome.name.lower() in ("over", "under", "yes", "no", "true", "false"):
           continue
   ```
   **Location:** After market category check, before team matching

3. **Add market source/category to response for grouping**
   - Already done (line 2010-2011: `"source"` and `"category"`)
   - Frontend can use this to show "Same market, different source"

### Medium-Term Fixes

4. **Normalize outcome names during polling**
   - Edit `backend/app/tasks/kalshi.py`, `polymarket.py` to normalize team names
   - Use a shared name normalization utility

5. **Add outcome-level filtering for non-award categories**
   - Detect if outcome is a stat prop (e.g., "Under 215") vs award
   - Filter out non-award outcomes from display

6. **Add market liquidity filtering**
   ```python
   bm_count = bookmaker_counts.get(outcome.id, 0)
   if market.source == "kalshi" and bm_count == 0:
       continue  # Skip illiquid Kalshi markets
   ```

### UI/UX Improvements

7. **Group outcomes by market in frontend**
   - Show "Jaylen Brown MVP" with a dropdown showing all sources
   - Display probability divergence clearly

8. **Add category labels**
   - "Awards" (MVP, ROTY, etc.)
   - "Championships" (Champion, Conference, etc.)
   - "Stats" (Win Total, Rebounds, etc.) — consider hiding
   - "Novelty" (Cover, TikTok, etc.) — consider hiding

---

## Data Quality Metrics to Monitor

### Metrics to Track

1. **Duplicate Outcome Count**
   ```
   SELECT
     outcome_name,
     COUNT(DISTINCT market_id) as market_count,
     COUNT(*) as total_outcomes
   FROM futures_outcomes
   WHERE market_id IN (
     SELECT id FROM futures_markets
     WHERE status = 'open'
     AND llm_sport_category = 'basketball'
   )
   GROUP BY outcome_name
   HAVING COUNT(DISTINCT market_id) > 1
   ORDER BY market_count DESC;
   ```

2. **Zero-Probability Markets**
   ```
   SELECT
     COUNT(*) as zero_prob_count,
     SUM(CASE WHEN source = 'kalshi' THEN 1 ELSE 0 END) as kalshi_count
   FROM futures_outcomes
   WHERE current_probability = 0
   AND market_id IN (
     SELECT id FROM futures_markets WHERE status = 'open'
   );
   ```

3. **Stale Markets** (no bookmakers)
   ```
   SELECT
     COUNT(DISTINCT fo.id) as stale_outcomes
   FROM futures_outcomes fo
   LEFT JOIN futures_odds_snapshots fos
     ON fo.id = fos.outcome_id
   WHERE fos.outcome_id IS NULL
   AND fo.market_id IN (
     SELECT id FROM futures_markets WHERE status = 'open'
   );
   ```

---

## Implementation Plan

**Phase 1 (This Week):**
- Add zero-probability filter (recommendation #1)
- Add game prop outcome filter (recommendation #2)
- Test with event 5541994

**Phase 2 (Next Week):**
- Implement outcome name normalization in polling tasks
- Add liquidity filtering for Kalshi markets
- Add monitoring queries above

**Phase 3 (Optional):**
- Frontend grouping/source badges
- Category filtering/hiding in UI

---

## Caveats

I could not directly fetch the production API response for event 5541994 due to network egress restrictions. The above analysis is based on:
1. **Code inspection** of `backend/app/routes/events.py` (the related-futures endpoint)
2. **Model definitions** in `backend/app/models/models.py`
3. **Known data patterns** from prediction market polling tasks

To verify these findings, you would need to:
1. Run the monitoring queries above against the production database
2. Directly curl `https://api.bainluck.com/api/events/5541994/related-futures` and inspect the response
3. Compare duplicate entries by (source, market_id, outcome_id) to identify which are legitimate divergences vs data bugs

