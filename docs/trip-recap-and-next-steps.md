# Italy Trip Recap & Next Steps

**Trip dates**: April 3-10, 2026 (Italy, phone + iPad only)
**Recap written**: April 13, 2026
**Consolidates**: `travel-guide.md`, `italy-trip-masters-plan.md`, `TODO.md` (originals archived to `docs/archive/`)

---

## What Shipped Before the Trip (April 1-3)

A massive push in the 48 hours before departure. ~50 commits across April 1-3, all deployed to production:

### Golf Product (biggest area of work)
- **Evolution chart redesign**: DataGolf-style interactive highlight with sidebar player list, color dots, add/remove. Three new components: `EvolutionChart.tsx`, `EvolutionView.tsx`, `EvolutionLeaderboard.tsx`
- **Position toggle**: Top 20 / Top 10 / Top 5 / Win switching between Kalshi position markets
- **Unified 9-column leaderboard grid**: Score/Today/Thru/Win/Top5/Top10/Top20 always visible
- **Bubble Watch / Cut Line section**: Shows players near projected cut line with make-cut probabilities
- **Tournament cards in feed**: Golf tournaments surfaced as proper feed items with hero probability cards
- **Golf tournament detail page**: Redesigned header, leaderboard, bubble watch
- **Masters tournament grid** added to championship grids
- **Non-winner market filter**: Removed "End of Round 1 Leader", "Make the Cut", etc. from hero probabilities
- **Prop market display**: Captains picks, participation, placement markets shown with proper labels
- **Ultra-lightweight Masters page** at `/masters/lite`
- **Golf routing cleanup**: `/playoffs/golf` and `/categories/golf` routing fixed

### Eval System
- **Bain-in-the-Loop eval page** at `/admin/eval` — mobile-friendly card-based evaluation
- **Eval decisions persist to backend** and create real matching overrides
- **Diagnostic context**: Cross-column comparison, peer comparison, disagreement flags, visual bars
- **Raw market names surfaced** in eval cards for transparency

### Admin & Infrastructure
- **Admin dashboard fixes**: UTC quota chart, grid health scores, eval page link
- **Grid page performance**: Fixed 20s blank screen (loading skeleton)
- **Chart axes visibility**: Fixed white-on-white bug in light mode

### Data Quality
- **MLB championship grid**: Fixed missing columns, all 30/30 teams across 4 columns
- **Tiger Woods odds**: Removed manual odds cap, flagged for data investigation
- **Make the Cut filter**: Fixed regex matching
- **Golf category page**: Fixed Tiger odds, Ryder Cup captains, tournament dates
- **Cross-tournament contamination**: Fixed in golf grid matching
- **Seed markets**: Excluded from playoff grids
- **Golfer name dedup**: Fixed + removed probability renormalization

### Repo Housekeeping
- **Stale docs archived** to `docs/archive/`
- **Dead code moved** to `frontend/_to-delete/` (scheduled for May 1 deletion review)
- **Travel guide + TODO.md created** for trip-period reference

---

## What Happened During the Trip (April 3-12)

### Cowork Sessions (confirmed via transcripts)

**BainLuck-related:**

1. **API Quota Optimization** ("Reduce API budget overages")
   - Designed tier-aware API params: Live=full, Soon=single-region, Later=h2h-only (83% cost reduction per "later" event)
   - Per-sport adaptive slowdown via Redis unchanged-odds counter
   - Futures polling reduced from hourly to every 2 hours
   - Estimated savings: 50-85K requests/day (~2-3M monthly vs previous 3.6-4.5M)
   - **STATUS: Code was committed in the Cowork sandbox but NOT pushed to GitHub.** These changes need to be re-implemented or cherry-picked.

2. **Dual Worker Infrastructure** ("Audit worker tasks")
   - Split single Celery worker into `worker-realtime` (Standard-2X, 1GB) and `worker-background` (Standard-1X, 512MB)
   - Queue routing: odds/ESPN/MLB/StatPal live plays on realtime; everything else on background
   - New `scoring_plays` table for persistent play-by-play history
   - StatPal sync writes full play history
   - Line movement endpoint uses scoring_plays for richer LLM explanations
   - **STATUS: DEPLOYED to production** (commit ae1c76a, pushed from laptop before trip). Heroku formation confirmed: web (1X), worker-realtime (2X), worker-background (1X), scheduler (1X). ~$125/mo.
   - **NOTE: This commit is NOT in the local sandbox** — it was pushed directly from the laptop. Need `git pull` to sync.

3. **v0 Design Prompt** ("Code audit and prediction site improvements")
   - Generated a detailed v0.dev prompt for FeedCard/EventCard visual redesign
   - Submitted to v0, got back generated code
   - **STATUS: Exploration only.** v0 output not integrated. Prompt saved to `docs/v0-prompt.md`. Good reference for future visual polish.

4. **Git Sync Attempt** ("Sync local git and audit website")
   - Tried to sync local repo + review oscars pool code
   - **Hit wall**: Cowork sandbox can't authenticate with GitHub (no credentials)
   - Confirmed local repo was behind on oscars pool commits

**Side Projects:**

5. **TeeBox App** ("Build golf tee box tracking app")
   - Built complete Next.js app for tracking golf bag tee-time usage at a club
   - Pushed to GitHub (`alexander-bain/teebox`), deployed to Vercel
   - Custom domain `teebox.alexbain.com` configured via Squarespace CNAME
   - Discussed GHIN/NCGA integration (no public API — need USGA GPA Program approval)
   - Discussed auth options for club staff (PIN code recommended over Google Auth for shared iPad)
   - **STATUS: Deployed and live.** Phase 2 would be Jonas Club Software integration for member directory + score posting.

6. **Golf Rules IQ** ("Build interactive golf rules learning game")
   - Designed full spec for a spaced-repetition golf rules learning app
   - Created CLAUDE.md project spec, KICKOFF-PROMPT.md, and working React prototype
   - SM-2 algorithm, Firebase backend, scoring system all spec'd out
   - **STATUS: Spec complete, not yet built.** Ready for Claude Code CLI session.

7. **Moon Haven Lodge Audit** ("Improve Moon Haven Lodge website")
   - Full digital audit of the Tahoe rental property website
   - Key finding: migrate off Google Sites to Lodgify/OwnerRez ($30-60/mo)
   - Recommendations: branded email, Google reviews, UTM tracking, Google Vacation Rentals listing
   - **STATUS: Report delivered.** Action items are non-code.

8. **Financial Analysis** ("Analyze financial health and retirement timeline")
   - Deep analysis of WWB trusts (07, 09, 2012) — PE positions, inter-trust loans, liquid vs illiquid
   - Built interactive Marimekko charts of net worth (by asset type, by entity, over time)
   - **STATUS: Complete.** Charts delivered as React artifacts.

9. **STR Tax Forms** ("Prepare rental property tax forms")
   - Updated addendum for short-term rental tax filing
   - **STATUS: Complete.**

10. **March Madness Bracket Analysis** ("Analyze March Madness bracket leverage")
    - Scraped 127 brackets from family pool, identified leverage picks
    - **STATUS: Complete.** (Tournament is over.)

---

## What DIDN'T Get Done (Trip Plan vs Reality)

Comparing against the original trip plan's success criteria:

| Planned | Status | Notes |
|---------|--------|-------|
| Phase 1 golf cleanup (tour classification, LIVE badge, card labels) | **Not done** | Items still open in TODO.md |
| Masters tournament working well on BainLuck | **Unknown** | No QA notes captured; need to check if it worked |
| Mobile smoke test (phone Safari) | **Not done** | Still pending |
| Curated Kalshi/Polymarket market mappings for NBA + NHL | **Not done** | Trip was busy with other projects |
| 10-20 interesting non-sports markets list | **Not done** | |
| UX bug/improvement list from mobile testing | **Not done** | |
| Strategy decisions (kill /playoffs/golf? PGA Tour default? etc.) | **Not decided** | Still pending your call |

---

## Known Walls / Blockers Hit

1. **Cowork sandbox can't git push/pull**: Every session that tried to deploy code hit this wall. Changes made in Cowork are committed locally in the sandbox but can't reach GitHub. The dual worker infrastructure was deployed because you ran `git push` from your actual laptop terminal.

2. **Heroku CLI bug with hyphenated process names**: `heroku ps:type worker-realtime=Standard-2X` fails. Workaround: use the Heroku API directly (`curl -n -X PATCH ...`).

3. **Quota optimization not deployed**: The tier-aware polling and adaptive slowdown work was done in a Cowork session but never pushed. Need to re-implement.

---

## Git State Right Now

- **Local master**: `5ae29d9` (April 3 — "Add consolidated travel guide")
- **Origin/master** (last known): Same commit — but **you likely pushed commits from your laptop during the trip** (e.g., the dual worker commit `ae1c76a`). Need to `git pull` to see what's actually on GitHub.
- **Unmerged branches**: ~90 remote branches exist, but none have commits newer than April 3 based on what's cached locally. Most are old feature/claude branches from January-March.
- **First step**: `git pull origin master` from your laptop to sync.

---

## Phase 1 / Phase 2 Breakdown

### Phase 1 (Done — shipped before trip)
- Evolution chart with position toggle
- Leaderboard (9-column grid)
- Bubble Watch / Cut Line
- Tournament cards in feed
- Non-winner market filter
- Eval page with backend persistence
- Dual worker infrastructure
- MLB grid fixes

### Phase 2 (Still To Do)

**Golf (next priority):**
- [ ] Tour classification fix (Hainan = Asian Tour, not PGA Tour)
- [ ] LIVE badge fix (date-based validation, not just leaderboard existence)
- [ ] Categories page chart fix ("Yes" binary → Kalshi player market)
- [ ] "To win" label on card probabilities
- [ ] "Augusta National Invitational" ghost tournament investigation
- [ ] Golf home redesign (hero card, majors section, tour filtering)
- [ ] H2H matchups on tournament detail
- [ ] Redirect `/playoffs/golf` → `/categories/golf`
- [ ] Mobile smoke test

**Infrastructure:**
- [ ] Re-implement quota optimization (tier-aware polling, adaptive slowdown, futures 2h interval)
- [ ] Freshness-weighted source blending (design notes exist, needs eval data)

**Strategy decisions still needed:**
- [ ] Kill `/playoffs/golf`? (Recommendation: yes, redirect to `/categories/golf`)
- [ ] Default to PGA Tour only? (Recommendation: yes, "All Tours" toggle)
- [ ] Golf home hierarchy? (Recommendation: hero → majors → upcoming → completed)
- [ ] Props on cards vs detail page only?
- [ ] Completed tournaments: final results vs pre-tournament odds?

**DS/Analytics (from ds-veteran-analysis.md):**
- [ ] Add `ended_at`, `final_home_probability`, `event_results`, `season` columns
- [ ] Denormalize `sport_group` on events
- [ ] Create `v_completed_events` analytical view
- [ ] First analysis: "Who's Right?" Brier score source accuracy

**Backlog:**
- [ ] TV Mode v2
- [ ] Non-sports categories (politics, entertainment)
- [ ] "Market Was Wrong" v2
- [ ] Hockey win probability model
- [ ] Matching eval admin page

---

## Immediate Next Steps (April 13)

1. **`git pull origin master`** — sync local repo with whatever was pushed during the trip
2. **Review the Masters**: Did it work? Check DataGolf data, evolution charts, leaderboard for the Masters tournament (April 9-12). The tournament is over — can we see the data?
3. **Re-implement quota optimization**: The tier-aware polling changes from the Cowork session need to be rebuilt (or I can do them now in this session)
4. **Golf Phase 2 cleanup**: Tour classification, LIVE badge, chart data fixes
5. **Make strategy decisions**: The 5 pending golf UX decisions from the travel guide

---

## Side Project Status

| Project | Status | Next Step |
|---------|--------|-----------|
| TeeBox | Live at teebox.alexbain.com | Jonas API integration for member directory |
| Golf Rules IQ | Spec complete | Claude Code CLI session to build Phase 1 |
| Moon Haven Lodge | Audit complete | Migrate off Google Sites (non-code) |

---

## Housekeeping Reminders

- [ ] **May 1**: Review and delete `frontend/_to-delete/` if nothing broke
- [ ] **May 1**: Review and delete `docs/archive/` if nothing was referenced
- [ ] **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
