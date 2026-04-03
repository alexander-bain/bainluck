# Championship Grids — Session 1 Kickoff

Paste this into Claude Code CLI to start the session:

---

I'm starting implementation of the Championship Grids project. Read `docs/championship-grids-project.md` for the full plan, paying special attention to the **Phase 0 Data Audit Results** section and the **CLI Workflow Instructions** section (commit/push/deploy protocol).

This project adds playoff/tournament progression grid pages that show every team's probability of reaching each playoff round, with data from multiple sources (Odds API, Kalshi, Polymarket). Think MoneyPuck.com/predictions.htm for NHL, or DataGolf.com/predictions for golf.

## This session has TWO tracks:

### Track A: Investigate the March Madness data gap (URGENT — tournament is happening NOW)

The data audit found ZERO NCAA tournament-level futures markets in production — no championship outrights, no Final Four, no round-by-round. But we have hundreds of individual game props from Kalshi. Something is wrong with our data pipeline.

**Investigate in this order:**

1. Check what the Odds API has available for NCAA basketball:
```bash
curl "https://api.bainluck.com/api/futures/available"
```
Look for sport keys containing `ncaab` or `ncaa`. The Odds API should have `basketball_ncaab_championship_winner` outrights.

2. Check if our polling tasks are fetching NCAA outrights. Look at:
   - `backend/app/tasks/futures.py` — what sport keys does `poll_all_futures` iterate over?
   - `backend/app/tasks/config.py` — is there a list of sport keys for futures polling?
   - The beat schedule in `backend/app/tasks/__init__.py` — is futures polling running?

3. Search Kalshi for NCAA tournament markets that might exist but aren't categorized:
```bash
curl "https://api.bainluck.com/api/futures/browse?category=basketball&limit=200" | python3 -c "import json,sys; data=json.load(sys.stdin); [print(f'{m[\"id\"]}: {m[\"name\"]} ({m[\"source\"]})') for m in data.get('markets',[]) if any(kw in m.get('name','').lower() for kw in ['ncaa','march','madness','tournament','final four','sweet','elite','bracket','college basketball'])]"
```

4. Check Polymarket directly for NCAA markets:
```bash
# Search our DB for any polymarket basketball futures
curl "https://api.bainluck.com/api/futures/browse?category=basketball&source=polymarket&limit=100"
```

5. If markets exist on the source APIs but aren't being ingested, fix the pipeline:
   - Add missing sport keys to the futures polling config
   - Ensure Kalshi category filter includes NCAA/college basketball terms
   - Ensure Polymarket tag-to-category mapping covers March Madness
   - Trigger a manual poll to ingest the data
   - Verify the markets appear in the DB

6. If markets DON'T exist on our sources, investigate alternatives:
   - Check if `the-odds-api.com` has `basketball_ncaab` outrights (check their docs/API explorer)
   - Check Kalshi's website directly (kalshi.com) for March Madness markets
   - Check Polymarket's website for NCAA tournament markets
   - Report what you find — we may need to add a new data source or accept the gap

**Commit after:** fixing any pipeline issues. Deploy and verify the new markets appear.

### Track B: Build the playoff grid backend + golf grid (Phase 1)

Golf has the best data (3 sources, 5 columns). Build the architecture with golf, then NBA/NHL follow the same pattern.

**Step 1: Create league config file**

Create `backend/app/config/league_configs.py` with config structures for all 4 leagues. Read the "Data Architecture" section of `docs/championship-grids-project.md` for the schema. Each league needs:
- Grid column definitions (key, label, order, whether sequential)
- Market matching rules (regex patterns to map futures market names → grid columns)
- Team sort order
- Conference/region grouping config

Start with these configs based on the audit:
- **Golf:** Columns: Make Cut | Top 20 | Top 10 | Top 5 | Winner. NOT sequential (finishing top 5 doesn't require "surviving" top 10). Match by tournament name + column keyword in market name.
- **NBA:** Columns: Make Playoffs | Conference | Champion. Match "Make Playoffs" markets, "Conference" or "Eastern/Western" markets, "Championship" or "Champion" markets. Conference grouping: East/West.
- **NHL:** Columns: Make Playoffs | Division | Conference | Stanley Cup. Match similarly. Conference grouping: East/West.
- **NCAA:** Columns: R64 | R32 | Sweet 16 | Elite 8 | Final Four | Champion. Sequential. Region grouping: East/West/South/Midwest. (Config ready for when data exists.)

**Step 2: Create the playoff grid endpoint**

Create `backend/app/routes/playoffs.py` with `GET /api/playoffs/{league_slug}`.

Reference these existing files for patterns:
- `backend/app/routes/oscars.py` — cross-source odds aggregation, nominee dedup, probability normalization
- `backend/app/routes/golf.py` — per-sport landing page, tournament detection, movers computation
- `backend/app/routes/futures.py` — probability-timeline endpoint for trend data

The endpoint should:
1. Load the league config
2. Query `FuturesMarket` + `FuturesOutcome` for markets matching the league's sport
3. For each grid column, find matching markets using the config's regex patterns
4. For each team/player, build the grid row by collecting probabilities across columns
5. Merge multi-source probabilities (median across sources, like Oscars page does)
6. Include per-source breakdown in each cell
7. Compute 24h movers from `FuturesOddsSnapshot` (reuse golf movers logic)
8. Include a trend chart dataset for the championship column (reuse probability-timeline bucket logic)
9. Include team metadata (logos, colors, records from Team table)
10. Return the self-describing response shape from the project doc

Register the router in `main.py` and `routes/__init__.py`.

**Step 3: Write tests**

Write tests for:
- League config validation (columns are ordered, patterns compile)
- Market-to-column matching accuracy (test with real market names from the audit)
- Probability consistency checking (champion ≤ conference ≤ make_playoffs for sequential columns)
- Multi-source merging (median computation, normalization)

**Step 4: Verify with production data**

After deploying the endpoint:
```bash
curl "https://api.bainluck.com/api/playoffs/golf" | python3 -m json.tool | head -100
curl "https://api.bainluck.com/api/playoffs/nba" | python3 -m json.tool | head -100
curl "https://api.bainluck.com/api/playoffs/nhl" | python3 -m json.tool | head -100
```

Check: Do the right teams appear? Are probabilities reasonable? Are multiple sources showing? Are movers computed? Flag any data quality issues.

## Key files to read first:
- `docs/championship-grids-project.md` (full project plan + data audit results)
- `backend/app/models/models.py` (FuturesMarket, FuturesOutcome, Team models)
- `backend/app/routes/oscars.py` (reference for cross-source aggregation)
- `backend/app/routes/golf.py` (reference for per-sport landing page + movers)
- `backend/app/routes/futures.py` (probability-timeline endpoint)
- `backend/app/utils/market_grouping.py` (canonical key matching)
- `backend/app/tasks/futures.py` (futures polling — for Track A investigation)
- `backend/app/tasks/kalshi.py` (Kalshi polling — for Track A investigation)
- `backend/app/tasks/polymarket.py` (Polymarket polling — for Track A investigation)

## IMPORTANT — Commit/Push/Deploy Protocol:

After completing each logical unit of work, proactively:
1. **Commit** with a descriptive message — don't wait for me to ask
2. **Push to master** — `git push origin master`
3. **Verify deployment:**
   - Heroku: `heroku releases -a bainluck --num 1` then `curl -s https://api.bainluck.com/health/ready | python3 -m json.tool`
   - Vercel: `curl -s -o /dev/null -w "%{http_code}" https://bainluck.com`
4. **Tell me** the deployment status before moving on

If auto-deploy doesn't trigger within 2 minutes of push:
- Heroku: `git push heroku master`
- Vercel: should auto-deploy, but check `vercel ls` if needed

Start with Track A (March Madness investigation) since it's time-sensitive, then move to Track B.
