---
description: Run a full site health check — link rates, grid health, quota, tests, deploy status — with plain-English analysis and recommended actions.
allowed-tools: Bash, Read, Grep, Glob
---

# Health Check

Run a comprehensive Bain Luck health check. Query all admin endpoints, analyze results, and produce an actionable briefing. Optionally file GitHub Issues for problems found.

**Important:** Source `.env.claude` before every curl command. The admin token variable is `$ADMIN_TOKEN` (not `$ADMIN_SECRET`).

## Steps

### 1. Gather data (run all in parallel where possible)

Group these into parallel batches. Every `curl` must be prefixed with `source /Users/bain/bainluck/.env.claude &&`.

#### Batch 1: Production infrastructure

```bash
# Sentry — new/high-frequency errors (last 24h)
source .env.claude && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://us.sentry.io/api/0/projects/alexander-bain/bainluck/issues/?query=is:unresolved&limit=5&sort=date" \
  | python3 -c "import json,sys; [print(f'  {i[\"shortId\"]:12s} {i[\"count\"]:>5s} evts  {i[\"title\"][:60]}') for i in json.load(sys.stdin)]"

# Heroku — dyno status + DB connections
heroku apps:info -a bainluck 2>&1 | grep "Dynos:"
heroku pg:info -a bainluck 2>&1 | grep "Connections:"

# CI — last 3 runs
gh run list --repo alexander-bain/bainluck --limit 3

# Celery queue health
source .env.claude && curl -s "https://api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); q=d.get('queue_lengths',{}); print(f'  bg={q.get(\"background\",0)} rt={q.get(\"realtime\",0)}')"
```

#### Batch 2: Data quality endpoints

```bash
# Admin dashboard (quota, sources, futures, database, workers)
source .env.claude && curl -s "https://api.bainluck.com/api/admin/dashboard?secret=$ADMIN_TOKEN"

# Link rate health
source .env.claude && curl -s "https://api.bainluck.com/api/admin/prediction-markets/link-rate?secret=$ADMIN_TOKEN"

# is_winner backfill coverage — all sources should be >95%
source .env.claude && curl -s "https://api.bainluck.com/api/admin/backfill-winners/status?secret=$ADMIN_TOKEN"

# Calibration metrics (public, cached)
curl -s "https://api.bainluck.com/api/calibration" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'MCE={d.get(\"mce_closing_line\",\"?\")}pp  outcomes={d.get(\"total_outcomes\",\"?\")}  winners={d.get(\"total_winners\",\"?\")}  closing_line_cov={d.get(\"closing_line_coverage\",\"?\")}')"
```

#### Batch 3: Grid health (active leagues only)

```bash
# Check each active grid — extract health_score and fill_rate
for league in nba nhl mlb; do
  source .env.claude && curl -s "https://api.bainluck.com/api/playoffs/$league" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'$league: health={d.get(\"health_score\",\"?\")} fill={d.get(\"fill_rate\",\"?\")} teams={len(d.get(\"teams\",[]))}')" 2>/dev/null || echo "$league: FAILED"
done
```

#### Batch 4: Endpoint latency spot-checks

```bash
# Spot-check 5 key user-facing endpoints for latency
for endpoint in \
  "https://api.bainluck.com/api/feed" \
  "https://api.bainluck.com/api/events/live" \
  "https://api.bainluck.com/api/weather/featured" \
  "https://api.bainluck.com/api/politics" \
  "https://api.bainluck.com/api/calibration"; do
  TIME=$(curl -s -o /dev/null -w "%{time_total}" "$endpoint" 2>/dev/null)
  echo "  ${endpoint##*/}: ${TIME}s"
done
```

#### Batch 5: Local checks

```bash
# Test count
cd /Users/bain/bainluck/backend && python3 -m pytest tests/ --co -q 2>&1 | tail -1

# Git status
git -C /Users/bain/bainluck log --oneline -3
git -C /Users/bain/bainluck status --short | head -10

# Feed quality audit (if script exists)
cd /Users/bain/bainluck/backend && python3 scripts/audit_feed_quality.py 2>&1 | tail -10

# Manus audit — last run
cat /Users/bain/bainluck/Manus/audit_results/latest/manifest.json 2>/dev/null \
  | python3 -c "import json,sys; m=json.load(sys.stdin); tasks=m.get('tasks',{}); done=sum(1 for t in tasks.values() if t.get('status')=='complete'); print(f'Last Manus: {m.get(\"date\",\"?\")} — {done}/{len(tasks)} complete')" \
  || echo "No Manus audit results"
```

### 2. Analyze and present results

For each section, present:
- **Status**: 🟢 Good / 🟡 Needs attention / 🔴 Problem
- **Key metrics** on one line
- **Issues found** (if any) — specific, not vague

#### Sections (in priority order):

**A. Production Stability**
- Sentry: any issue >100 events in 24h → 🔴
- Heroku: dyno up, DB connections reasonable (<18)
- CI: last 3 runs passing
- Celery: background queue >50 → 🔴, >20 → 🟡

**B. Endpoint Latency**
- Target: all user-facing endpoints under 1s
- Flag anything over 2s as 🔴, over 1s as 🟡
- Note: `/api/feed` is the most critical — it's the landing page

**C. Odds API Quota**
- Current usage vs 5M monthly budget
- Projected end-of-month surplus/deficit
- Circuit breaker mode (Normal / LIVE_ONLY / FULL_STOP)

**D. Game Prop Link Rate**
- Target: 100% for Tier 1 leagues (NBA, NHL, MLB, NFL)
- Per-league breakdown for Kalshi and Polymarket
- For any league below 100%: classify unlinked markets as (1) bug to fix or (2) math error (season futures counted as linkable)

**E. Championship Grid Health**
- Target: 100% for every grid
- Per-grid: health score, fill rate, team count
- For any grid below 100%: name the specific columns/teams with gaps

**F. Calibration & Backfill Pipeline**
- MCE (target: <3pp)
- Closing line coverage
- is_winner coverage per source (target: >95%)
- Flag any source below 80% as 🔴

**G. Source Coverage**
- Average sources per live event
- Any source that went dark (0 recent snapshots)
- Kalshi/Polymarket ingestion recency — when was the last successful poll?

**H. Feed Quality**
- boring-rate@20 (target: 0)
- ladder/bucket-rate@20 (target: 0)
- duplicate-family-rate@20 (target: 0)
- explanation-coverage@20 (target: 20/20)

**I. Database & Infrastructure**
- DB size and connection count
- Snapshot volume trends
- Worker task health

**J. Test Suite & Deploys**
- Total test count, any failures
- Last 3 commits
- Uncommitted changes

**K. Manus QA Audit**
- Last audit date — flag if >7 days old
- Module completion rate
- Key findings from completed reports (scan `Manus/audit_results/latest/*.md` for lines containing "critical", "broken", "crash", "error", "0/100", "0%")

### 3. Summary table

Present a single summary table:

```
| Area                  | Status | Key Metric              |
|-----------------------|--------|-------------------------|
| Production Stability  | 🟢/🟡/🔴 | ...                  |
| Endpoint Latency      | ...    | ...                     |
| Odds API Quota        | ...    | ...                     |
| Link Rate             | ...    | ...                     |
| Grid Health           | ...    | ...                     |
| Calibration Pipeline  | ...    | ...                     |
| Source Coverage        | ...    | ...                     |
| Feed Quality          | ...    | ...                     |
| Database & Infra      | ...    | ...                     |
| Tests & Deploys       | ...    | ...                     |
| Manus QA              | ...    | ...                     |
```

### 4. Top 3 recommendations

1. **Highest-impact action** to take right now
2. **Something to monitor** over the next few days
3. **Structural improvement** for the next session

### 5. File issues (optional — ask first)

After presenting findings, if there are any 🔴 or 🟡 items:

1. Ask: "Want me to file GitHub Issues for the problems found?"
2. If yes, for each problem:
   - Check for an existing open issue covering the same problem (`gh issue list --search "KEYWORD" --state open`)
   - If no existing issue: create one with appropriate labels (`area:*`, `type:*`, `priority:*`, `needs-agent` or `needs-user`)
   - If existing issue: comment with updated status from this health check
   - Add all new issues to the project board (`gh project item-add 1 --owner alexander-bain`)
3. Report what was filed/updated

Keep the whole output concise — aim for a briefing readable in 60 seconds. Don't dump raw JSON; extract the metrics that matter.
