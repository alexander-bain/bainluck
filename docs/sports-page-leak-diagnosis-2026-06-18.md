# /sports page leaking non-sports content — diagnosis & fix plan

**Date:** 2026-06-18 · **Author:** Fable (Cowork) code-path diagnosis, requested by Alex (live screenshot of bainluck.com/sports) · **Status:** issues drafted below, not yet filed (GitHub was read-only the session this was written)

Alex reported three things wrong on `/sports`: (1) a **Pinned** section full of Tech/Entertainment cards (aliens, Taylor Swift, Claude Fable), (2) an entire **"Player Props & Progressions"** section that's actually **esports** match-winners, and (3) **geopolitics** seen there earlier.

## Decided behavior (Alex, 2026-06-18)
- **Pinned** belongs on **My Stuff**, not Sports → remove the Pinned section from `/sports`.
- **esports is not a sport** → drop it from all `/sports` surfaces, but **keep it in Discover/Browse** (so do NOT remove it from `DISCOVER_SPORTS_CATEGORIES`; scope a sports-page-only set instead).
- **geopolitics / crypto / tech / entertainment** must never appear on `/sports`.
- **motorsports** stays a sport (F1/NASCAR) — only esports was flagged.

## Root causes

### Bug 1 — Pinned section renders on /sports regardless of category
`frontend/app/sports/page.tsx:275–329` renders a Pinned block from `usePinnedEvents()` / `usePinnedFutures()` (`page.tsx:47,51`) whenever the user has any pins, with no category filter. So Tech/Entertainment pins show on Sports. The pinned-item fetch wiring is `page.tsx:91–176`.

### Bug 2 — the "Player Props & Progressions" grouped feed is completely unfiltered
The section (`page.tsx:331–357`, title at `:342`) is fed by `fetchGroupedFeed({ limit: 20 })` (`page.tsx:86`) → `GET /api/futures/grouped-feed` (`backend/app/routes/futures.py:1477`). That endpoint only filters when a `category` or `sport` query param is passed (`futures.py` filters block) — and the sports page passes **neither**, so it returns ALL active/open futures grouped by type. That is the primary leak for both the esports cards and the geopolitics Alex saw. **Note:** the endpoint's `category` param filters `FuturesMarket.category` (e.g. "championship"), NOT `llm_sport_category` — so the fix is a new sports-category filter, not just passing `category="sports"`.

### Bug 3 — esports is classified as a sport
`DISCOVER_SPORTS_CATEGORIES` (`backend/app/routes/feed.py:407–422`) includes `"esports"` (and `"motorsports"`). The sports-mode feed (`_score_sports_mode_futures`, `feed.py:3968`) and `_is_sports_market_category` (`feed.py:1833`) filter on that set, so esports leaks into the main sports feed too. Even after Bug 2 is fixed, esports would still pass a "sports" filter until it's excluded from the sports-page surfaces. The constant is used in ~8 places incl. Discover pools (`feed.py:2241/2253/2272/3968/4646/4675/4687`), so it must stay intact for Discover; the exclusion must be sports-page-scoped.

## Fix plan → three issues

### Issue A — Remove the Pinned section from /sports (pinning lives on My Stuff)
Frontend. Delete the Pinned render block (`page.tsx:275–329`) and the now-unused pinned fetch/memo wiring (`page.tsx:91–176`, the `usePinned*` imports). Confirm My Stuff still surfaces pins. Keep the 3 mandatory GA4 hooks intact. Labels: `area:feed`/`area:discover` (confirm) · `type:bug` · `priority:p1`.

### Issue B — /sports grouped feed ("Player Props & Progressions") returns all categories
Backend + frontend. Give `/api/futures/grouped-feed` a real sports filter — accept a sports-category-set filter on `llm_sport_category` (the real sports, esports excluded) — and have `/sports` request only sports (`page.tsx:86`). Result: only sports player-props/progressions render. Labels: `area:feed` · `type:bug` · `priority:p1`.

### Issue C — esports treated as a sport on /sports (scope it out, keep Discover/Browse)
Backend. Add a sports-page-only category set, e.g. `SPORTS_PAGE_CATEGORIES = DISCOVER_SPORTS_CATEGORIES` minus `"esports"`, and use it in `_score_sports_mode_futures` (`feed.py:3968`) and the Issue-B grouped-feed sports filter. **Leave `DISCOVER_SPORTS_CATEGORIES` unchanged** so esports stays in Discover/Browse. Labels: `area:feed` · `type:bug` · `priority:p1`. (B + C are tightly coupled — likely one PR.)

## Filing note
Not filed automatically (GitHub integration read-only this session). File A–C from a host Claude Code session via `gh`, or use the paste-ready CLI prompt provided alongside this doc. All three are small, launch-page-facing — quick wins.
