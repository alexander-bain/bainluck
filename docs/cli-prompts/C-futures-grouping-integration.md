# Prompt C: Futures Grouping — Wire It Into the UI

## Context

You are working on Bain Luck, a sports odds visualization app. Read `CLAUDE.md` for full context.

Three futures grouping components were built but **never connected to any page**:
- `frontend/components/CombinedMarketCard.tsx` — cross-source market comparison (e.g., same championship from Polymarket + Kalshi + Odds API)
- `frontend/components/ProgressionTable.tsx` — tournament progression (playoff round markets)
- `frontend/components/ThresholdGrid.tsx` — threshold variants (e.g., "Bitcoin > $80K" / "$90K" / "$100K")

The backend endpoints are ready:
- `GET /api/futures/groups/{group_id}` — returns all markets in a group with outcomes and threshold detection
- `GET /api/futures/groups?limit=50&group_type=...` — lists all groups
- Market records have `group_id` and `group_type` columns populated during Kalshi/Polymarket polling

Your job is to **wire these components into visible pages** so users actually see grouped futures.

## Step 1: Add Grouped Markets to Futures Detail Page

Read `frontend/app/futures/[id]/page.tsx`.

When viewing a single futures market that belongs to a group, the page should show a "Same Market, Multiple Sources" section if the group has markets from 2+ different sources.

### 1a. Fetch group data

After loading the main market, check if it has a `group_id`. If so, fetch the group:
```tsx
const groupData = market.group_id
  ? await fetch(`${API_URL}/api/futures/groups/${encodeURIComponent(market.group_id)}`)
      .then(r => r.ok ? r.json() : null)
      .catch(() => null)
  : null;
```

### 1b. Show CombinedMarketCard when multi-source

If the group has markets from 2+ distinct sources, render `CombinedMarketCard` above the outcomes table:

```tsx
{groupData && groupData.sources.length >= 2 && (
  <section className="mb-8">
    <h2 className="text-lg font-semibold text-text-primary mb-3">
      Cross-Source Comparison
    </h2>
    <p className="text-sm text-text-muted mb-4">
      This market is tracked by {groupData.sources.length} sources — see how their odds compare
    </p>
    <CombinedMarketCard
      title={groupData.group_title}
      markets={groupData.markets}
      sources={groupData.sources}
    />
  </section>
)}
```

### 1c. Show ThresholdGrid when threshold variants exist

If `groupData.threshold_groups` has entries, show a ThresholdGrid:

```tsx
{groupData?.threshold_groups && Object.keys(groupData.threshold_groups).length > 0 && (
  <section className="mb-8">
    <h2 className="text-lg font-semibold text-text-primary mb-3">
      Related Thresholds
    </h2>
    {Object.entries(groupData.threshold_groups).map(([stem, outcomes]) => (
      <ThresholdGrid
        key={stem}
        outcomes={outcomes}
        stem={stem}
      />
    ))}
  </section>
)}
```

Check the ThresholdGrid props interface and adjust the data mapping if needed — the API returns `threshold_value`, `threshold_unit`, `threshold_direction`, `probability`, and `name` per outcome.

## Step 2: Grouped Futures on Homepage "Top Markets" Section

Read `frontend/app/page.tsx`. The feed groups items into sections including "Top Markets".

### 2a. Deduplicate grouped futures in the feed

Currently, if Polymarket and Kalshi both have "NBA Championship Winner", they appear as **two separate cards** in the feed. This is confusing.

In the `groupFeedIntoSections()` function (or wherever feed items are processed), deduplicate futures that share the same `canonical_market_key`:
- Keep the market with the most outcomes (usually Polymarket for NegRisk events)
- Add a small badge showing "3 sources" or "Polymarket + Kalshi" on the winning card
- This dedup should only apply to the feed — the individual futures pages should still show all sources via CombinedMarketCard

```tsx
function deduplicateGroupedFutures(items: FeedItem[]): FeedItem[] {
  const seen = new Map<string, FeedItem>();
  const result: FeedItem[] = [];

  for (const item of items) {
    if (item.type === 'futures' && item.data.canonical_market_key) {
      const key = item.data.canonical_market_key;
      const existing = seen.get(key);
      if (existing) {
        // Keep the one with more outcomes, track source count
        const existingCount = existing.data.outcome_count ?? 0;
        const newCount = item.data.outcome_count ?? 0;
        if (newCount > existingCount) {
          // Replace, but track that we merged
          seen.set(key, { ...item, _sourceCount: (existing._sourceCount ?? 1) + 1 });
          // Remove old from result
          const idx = result.indexOf(existing);
          if (idx !== -1) result[idx] = seen.get(key)!;
        } else {
          // Keep existing, increment count
          existing._sourceCount = (existing._sourceCount ?? 1) + 1;
        }
      } else {
        seen.set(key, { ...item, _sourceCount: 1 });
        result.push(item);
      }
    } else {
      result.push(item);
    }
  }
  return result;
}
```

**IMPORTANT:** Check that `canonical_market_key` is actually returned in the feed API response. If it's not, you'll need to add it to the feed endpoint in `backend/app/routes/feed.py` — add `FuturesMarket.canonical_market_key` to the columns selected for futures items.

### 2b. Multi-source badge on FuturesCard

In `FuturesCard.tsx`, accept an optional `sourceCount` prop. When > 1, show a badge:
```tsx
{sourceCount > 1 && (
  <span className="text-xs text-text-muted bg-surface-elevated px-2 py-0.5 rounded-full">
    {sourceCount} sources
  </span>
)}
```

Place this in the card footer, next to the existing source/time display.

## Step 3: Threshold Markets Discovery Page

Create a new page that showcases threshold markets — these are some of the most interesting futures on the site (Bitcoin price targets, weather forecasts, etc.).

### 3a. Create `/categories/thresholds/page.tsx`

This page should:
1. Fetch threshold groups from the API: `GET /api/futures/groups?group_type=threshold&limit=30`
   - **NOTE:** If the API doesn't support `group_type=threshold` filtering (it may only have polymarket_event, kalshi_event, canonical), you'll need to fetch groups and filter client-side, OR add threshold detection to the groups listing endpoint
2. For each group, fetch the detailed data: `GET /api/futures/groups/{group_id}`
3. Render each group as a `ThresholdGrid` with a header showing the market name

Actually — simpler approach: instead of a standalone page, add threshold groups to existing category pages. The "Crypto" category page (`/categories/crypto`) should show Bitcoin/Ethereum threshold progressions. The "Economy" page should show Fed rate/inflation thresholds.

### 3b. Alternative: Threshold section on futures detail

When viewing any single threshold market (e.g., "Will Bitcoin exceed $100,000?"), the related thresholds section (from Step 1c) should be prominent and show the full progression. Add a mini ProgressionTable showing all threshold levels with the current market highlighted:

```tsx
// Highlight the current market's threshold in the grid
<ThresholdGrid
  outcomes={thresholdOutcomes}
  stem={stem}
  highlightedValue={currentMarketThreshold}  // Add this prop to ThresholdGrid
/>
```

In ThresholdGrid, when `highlightedValue` matches an outcome's `threshold_value`, add a ring highlight:
```tsx
className={cn(
  "border rounded-lg p-3",
  outcome.threshold_value === highlightedValue
    ? "border-accent-brand ring-1 ring-accent-brand/30"
    : "border-surface-border"
)}
```

## Step 4: ProgressionTable for Playoff Rounds

Read `frontend/components/ProgressionTable.tsx`.

On sports category pages (basketball, football, hockey), when there are multiple playoff round futures for the same team or same league, show them as a progression:
- "Make Playoffs" → "Win First Round" → "Win Conference" → "Win Championship"

### 4a. Detection logic

In the category page (or on the futures detail page for championship markets), look for related markets that form a progression:

```tsx
const PLAYOFF_PROGRESSION = [
  /make.playoffs/i,
  /first.round|round.of.32|wild.card/i,
  /second.round|round.of.16|divisional/i,
  /conference|semi.?final|elite.eight|final.four/i,
  /championship|super.bowl|world.series|stanley.cup|finals/i,
];

function detectProgression(markets: FuturesMarket[]): FuturesMarket[] | null {
  // Find markets that match 3+ stages for the same team/league
  // Return them ordered by stage
}
```

### 4b. Show ProgressionTable

If a progression is detected, render it:
```tsx
<ProgressionTable
  markets={progressionMarkets}
  title={`${teamName} Playoff Path`}
  showSource={true}
/>
```

Each row shows: stage name, top outcome (usually "Yes"), probability, source badge.

This is a reach feature — if the market data doesn't cleanly support progression detection, skip this step and note it as a TODO.

## Step 5: Verify API Returns Needed Data

Before doing frontend work, verify the backend returns what we need.

### 5a. Check feed endpoint includes canonical_market_key

Read `backend/app/routes/feed.py`. Check if `canonical_market_key` is included in the futures data returned by the feed endpoint. If not, add it:

In the futures query section, ensure `FuturesMarket.canonical_market_key` is selected and included in the response serialization.

### 5b. Check group endpoint handles URL-encoded group_ids

Group IDs contain colons (e.g., `polymarket:12345`, `canonical:basketball:NBA:championship:2025-26`). Verify the FastAPI endpoint properly decodes URL-encoded colons in the path parameter. If using `{group_id:path}`, it should work. Test with a curl:
```bash
curl "https://api.bainluck.com/api/futures/groups/polymarket%3A12345"
```

If it 404s, the endpoint may need `{group_id:path}` instead of `{group_id}` in the route definition.

## Verification

After all changes:
1. `cd frontend && npx next build` — zero errors
2. Open a futures market that exists on both Polymarket and Kalshi (e.g., NBA Championship) — should see "Cross-Source Comparison" section with CombinedMarketCard
3. Open homepage — duplicate futures from different sources should be deduplicated, winner card shows "2 sources" badge
4. If Bitcoin/crypto threshold markets exist — should see ThresholdGrid on the futures detail page
5. Check that no existing functionality is broken — pinning, search, event cards all still work

**Do NOT commit. Leave changes unstaged for review.**
