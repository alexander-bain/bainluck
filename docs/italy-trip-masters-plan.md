# Italy Trip Plan — Masters Week (April 3-10, 2026)

Alex is traveling in Italy April 3-10. No laptop, but has phone + iPad with internet. Can use Claude.ai, GitHub web UI, and bainluck.com. **Both frontend AND backend auto-deploy from GitHub** (Heroku auto-deploy confirmed working April 2). Full deployment capability from phone/iPad.

---

## Pre-Flight Checklist (April 2)

### Must Complete Today
- [x] Push the Kalshi non-winner market filter fix (`golf.py` — committed, needs push)
- [x] Verify Heroku auto-deploy — **CONFIRMED WORKING** (April 2, 2026)
- [x] Give feedback on Masters prototype mockup (design decisions captured in memory)
- [x] Fix MLB championship grid (missing columns, missing teams — 30/30 across all 4 columns now)
- [x] Fix admin dashboard (quota chart UTC, grid health scores, eval page link)
- [x] Fix grid page loading (was 20s blank screen, now shows skeleton immediately)
- [x] Fix chart axis visibility (white-on-white bug)
- [ ] Smoke-test golf page on phone: `bainluck.com/categories/golf`
- [ ] Test bainluck.com on phone (Safari/Chrome) — note any mobile UX issues

### Should Complete Today
- [ ] Build matching eval admin page (`/admin/matching-eval`)
- [ ] Review Masters tournament detail page: `bainluck.com/categories/golf/tournaments/the-masters`
- [ ] Verify DataGolf live polling will activate for Masters (check Redis gate + schedule detection)

---

## Masters Tournament Timeline

| Date | Event | BainLuck Should Show |
|------|-------|---------------------|
| Apr 7-8 | Practice rounds | Pre-tournament odds, Evolution chart building up |
| Apr 9 (Thu) | Round 1 | Current event = Masters, live DataGolf probs, leaderboard |
| Apr 10 (Fri) | Round 2 + Cut | Cut line drama, bubble watch (if built) |
| Apr 11 (Sat) | Round 3 (Moving Day) | Big movers, odds shifts |
| Apr 12 (Sun) | Final Round | Live win probability changes, champion crowned |

**Auto-detection**: The system will automatically detect Masters as the current event on April 9 based on DataGolf schedule dates (April 9-12).

---

## What Alex Can Do From Phone/iPad

### 1. Product Testing & QA (Highest Value)

Use bainluck.com during the Masters and note issues in a Google Doc or Apple Notes:

**Check each round:**
- Does the golf page show Masters as current event?
- Are the golfer probabilities reasonable? (Scheffler ~15-20%, Rory ~8-10%, etc.)
- Do the odds update live during play? (DataGolf polls every 5 min)
- Does the Evolution chart show sensible movements?
- Are the Movers showing real movement?
- Does the championship grid (`/playoffs/golf`) update during the tournament?
- Mobile layout: anything cut off, overlapping, or hard to tap?

**Known things to watch for:**
- DataGolf source should appear alongside Kalshi/Polymarket/Odds API
- If odds seem stale (same numbers for >30 min during active play), note it
- If probabilities don't sum to ~100%, note it
- If eliminated/cut players still show high odds, note it

### 2. Manual Matching Curation (Medium-High Value)

**What**: Go through Kalshi.com and Polymarket.com, identify which markets map to which championship grid columns for each sport.

**Format**: Create a Google Sheet with these columns:

| Source | Market Title | Market URL or ID | League | Grid Column | Notes |
|--------|-------------|------------------|--------|-------------|-------|
| Kalshi | "NBA Championship Winner" | INXNBA-26-... | nba | win | ✅ Clear match |
| Kalshi | "Eastern Conference Champion" | INXNBAEC-... | nba | conference | ✅ |
| Polymarket | "Will [team] make NBA playoffs?" | 0x... | nba | make_playoffs | ✅ |
| Kalshi | "NBA Finals MVP" | ... | nba | — | Not a grid column, skip |

**Priority leagues:**
1. **NBA** (playoffs starting ~April 12) — most urgent
2. **NHL** (playoffs starting ~April 19)
3. **MLB** (season underway, pennant race)
4. **Golf** (Masters + majors)

**What to capture per market:**
- Exact market title as shown on Kalshi/Polymarket
- The ticker/ID if visible in the URL
- Which grid column it belongs to (e.g., "make_playoffs", "first_round", "conference", "win")
- Whether it's a clean match or ambiguous
- Any markets that are interesting but don't fit current grid columns

**Why this is valuable**: The `matching_overrides` DB table already exists. Once you return, we can bulk-import your curated mappings and the grids will be 100% accurate for these markets, no fuzzy matching needed.

### 3. Quality Evaluation (If Eval Page is Built)

If we build the `/admin/matching-eval` page today:
- Open `bainluck.com/admin/matching-eval` on phone
- See proposed market-to-column matches
- Tap Yes/No/Wrong for each
- Feedback stored in DB, used to improve matching algorithm

### 4. Non-Sports Trending Futures Research

When browsing Kalshi or Polymarket, note interesting non-sports markets:

**What to look for:**
- Politics: election markets, policy bets, confirmation hearings
- Entertainment: Oscars, Emmys, box office, streaming milestones
- Culture/events: papal election, space launches, tech product launches
- Finance: rate cuts, IPOs, crypto milestones
- Weather/climate: hurricane season, temperature records

**Format** (Google Doc or Sheet):

| Source | Market Title | Category | Why Interesting | Volume/Activity Level |
|--------|-------------|----------|----------------|---------------------|
| Kalshi | "Next Supreme Court retirement" | Politics | Timely, high public interest | High volume |
| Polymarket | "GPT-5 release date" | Tech | Tech-savvy audience overlap | Medium |

**What we'll do with this**: Build a "trending" or "featured" section on bainluck.com that surfaces the most interesting non-sports prediction markets. Your curation teaches us what "interesting" means → we can eventually automate detection using Kalshi volume data + category signals.

### 5. Frontend-Only Code Changes

Things you can change via Claude.ai + GitHub web commits (Vercel auto-deploys):
- Copy/text changes on any page
- Color adjustments, spacing, layout tweaks
- New static pages or landing pages
- Component styling changes
- Analytics event additions
- Bug fixes in React components

**How to do it:**
1. Open Claude.ai on iPad
2. Paste the file contents from GitHub (or describe the change)
3. Get Claude to generate the edited file
4. Commit directly to `master` branch via GitHub web UI
5. Vercel deploys automatically in ~60 seconds

**Things you CAN also do from phone** (Heroku auto-deploy confirmed):
- Backend Python changes
- Database migrations (auto-run on deploy)
- Celery task modifications
- API endpoint changes

### 6. Product Strategy & Design

Low-energy, high-value work for downtime:
- Draft PRD sections for upcoming features
- Sketch UI ideas (paper or iPad drawing app)
- Write user stories for features you want
- Competitive research: check FanDuel, DraftKings, ESPN, The Athletic during Masters
- Note what other apps/sites do well for live golf coverage

---

## Code Changes Ready to Implement (Post-Trip or via Claude.ai)

### Frontend (Can deploy from iPad)

1. **Masters-themed golf page** — Augusta green accents, azalea pink highlights during Masters week
2. **Bubble Watch / Cut Line section** — Show players near projected cut line with make-cut probabilities (DataGolf provides `make_cut` market data)
3. **Mobile golf improvements** — Any layout issues found during testing
4. **Non-sports category tabs** — If we identify good markets, add Politics/Entertainment tabs

### Backend (Needs Heroku push — or auto-deploy)

1. **Golf tournament detail missing dates/venue** — The `/api/golf/tournaments/{slug}` endpoint doesn't propagate schedule data for start_date, end_date, venue. Quick fix in `routes/golf.py` tournament detail response.
2. **Matching eval API endpoints** — `GET /api/admin/matching-candidates` and `POST /api/admin/matching-eval` for the eval page
3. **Non-sports futures surfacing** — Endpoint to serve curated/trending non-sports markets
4. **Kalshi volume tracking** — If their API exposes volume, track it for trending detection

---

## Matching Eval Page Spec (Build Today if Time)

### Purpose
A mobile-friendly admin page where Alex can evaluate matching quality by tapping Yes/No.

### Screens

**Screen 1: Grid Matching Eval**
For each championship grid, show proposed market-to-column matches:
```
NBA Championship Grid
┌─────────────────────────────────────────────┐
│ Kalshi: "Eastern Conference Champion"       │
│ → Column: "conference"                      │
│ Confidence: 87%                             │
│                                             │
│ [✅ Correct]  [❌ Wrong]  [🔄 Different Col] │
└─────────────────────────────────────────────┘
```

**Screen 2: "Is This Interesting?" Eval**
Show non-sports futures markets with current odds:
```
┌─────────────────────────────────────────────┐
│ Kalshi: "Will the Pope resign in 2026?"     │
│ Current: 8% Yes                             │
│ Category: Religion/Politics                 │
│                                             │
│ [🔥 Feature This]  [😐 Skip]  [🚫 Never]   │
└─────────────────────────────────────────────┘
```

### Technical
- Frontend: New page at `frontend/app/admin/matching-eval/page.tsx`
- Backend: Admin endpoints with `?secret=$ADMIN_SECRET` auth
- Storage: `matching_overrides` table (existing) + new `futures_curation` table
- Mobile-first: Big tap targets, swipe-friendly, works on phone

---

## Daily Routine in Italy

### Morning (with coffee, 15 min)
1. Open `bainluck.com/categories/golf` — check overnight odds updates
2. If Masters is live: check leaderboard, movers, evolution chart
3. Note any issues in your travel notes doc

### During Masters rounds (passive, when watching)
1. Keep bainluck.com open alongside TV/streaming
2. Compare what you see on BainLuck vs broadcast commentary
3. Note when probabilities feel right vs wrong vs delayed
4. If eval page exists: do a few evals during commercial breaks

### Evening (20 min, optional)
1. Browse Kalshi/Polymarket for interesting markets
2. Add any findings to the matching curation sheet
3. If inspired: use Claude.ai to draft a frontend change

---

## Success Criteria for the Trip

By April 10 (return), we should have:
- [ ] Masters tournament working well on BainLuck (live odds, current event, evolution chart)
- [ ] A curated Google Sheet of Kalshi/Polymarket market mappings for NBA + NHL playoff grids
- [ ] A list of 10-20 interesting non-sports markets to potentially feature
- [ ] A UX bug/improvement list from real-world mobile testing during Masters
- [ ] (Stretch) Matching eval feedback in the DB if the admin page was built

---

## Emergency Contacts

If something breaks during the trip:
- **Site down**: Check `bainluck.com/health` — if backend is down, Heroku may need a restart (Heroku dashboard on phone)
- **Quota exhaustion**: The Odds API quota guard should auto-protect, but check `/admin` dashboard
- **Data staleness**: DataGolf live polling may not activate if Redis gate isn't working — note it for post-trip fix
