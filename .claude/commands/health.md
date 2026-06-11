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
source .env.claude && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/celery-debug" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); q=d.get('queue_lengths',{}); print(f'  bg={q.get(\"background\",0)} rt={q.get(\"realtime\",0)}')"
```

#### Batch 2: Data quality endpoints

```bash
# Admin dashboard — extract quota, source coverage, database metrics
# Note: source_coverage is a list of per-sport dicts, not a dict with .sources
# quota is nested: quota.current.{remaining,used,total,health}, quota.budget.{projected_eom,projected_surplus,pace_48h_daily,days_remaining}
# database keys: active_events, live_events, snapshots_last_hour, db_size_mb, growth_rate_mb_per_day
source .env.claude && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/dashboard" | python3 -c "
import json,sys
d=json.load(sys.stdin)
qc=d.get('quota',{}).get('current',{}); qb=d.get('quota',{}).get('budget',{})
print(f'QUOTA: used={qc.get(\"used\",\"?\")} remaining={qc.get(\"remaining\",\"?\")} health={qc.get(\"health\",\"?\")}')
print(f'  projected_eom={qb.get(\"projected_eom\",\"?\")} surplus={qb.get(\"projected_surplus\",\"?\")} daily={qb.get(\"pace_48h_daily\",\"?\")} days_left={qb.get(\"days_remaining\",\"?\")}')
db=d.get('database',{})
print(f'DB: events={db.get(\"active_events\",\"?\")} live={db.get(\"live_events\",\"?\")} snaps/h={db.get(\"snapshots_last_hour\",\"?\")} size={db.get(\"db_size_mb\",\"?\")}MB growth={db.get(\"growth_rate_mb_per_day\",\"?\")}MB/d')
sc=d.get('source_coverage',[])
tier1=[s for s in sc if s.get('sport','') in ('basketball_nba','icehockey_nhl','baseball_mlb','americanfootball_nfl')]
for s in tier1:
    print(f'  {s[\"sport\"]:25s} live={s.get(\"live\",0)} oa={s.get(\"odds_api\",0)} espn={s.get(\"espn\",0)} kalshi={s.get(\"kalshi\",0)} pm={s.get(\"polymarket\",0)} snaps24h={s.get(\"snapshots_24h\",0)}')
"

# Link rate health — structure: {overall: {link_rate_pct, open_total, open_linked}, kalshi: {totals, by_sport}, polymarket: {totals, by_sport}}
source .env.claude && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/prediction-markets/link-rate" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ov=d.get('overall',{})
print(f'LINK RATE: open={ov.get(\"open_linked\",\"?\")}/{ov.get(\"open_total\",\"?\")} ({ov.get(\"link_rate_pct\",\"?\")}%) all={ov.get(\"link_rate_all_pct\",\"?\")}%')
for src in ('kalshi','polymarket'):
    s=d.get(src,{})
    t=s.get('totals',{})
    print(f'  {src}: open={t.get(\"open_linked\",\"?\")}/{t.get(\"open_total\",\"?\")} ({t.get(\"link_rate_pct\",\"?\")}%)')
    for sp in s.get('by_sport',[]):
        if sp.get('link_rate',0) < 100 and sp.get('open_total',0) > 0:
            print(f'    {sp[\"sport\"]:15s} {sp.get(\"open_linked\",0)}/{sp.get(\"open_total\",0)} ({sp.get(\"link_rate\",0)}%)')
"

# is_winner backfill coverage — target is 100% for every source (any gap is a bug)
source .env.claude && curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "https://api.bainluck.com/api/admin/backfill-winners/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for s in d.get('sources',[]):
    resolved=s.get('resolved',0); hw=s.get('has_winner',0)
    pct=round(100*hw/max(resolved,1),1)
    flag=' 🔴' if pct<100 else ''
    print(f'  {s[\"source\"]:12s} {pct}% ({hw}/{resolved}){flag}')
"

# Calibration metrics (public, cached)
curl -s "https://api.bainluck.com/api/calibration" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'MCE={d.get(\"mce_closing_line\",\"?\")}pp  outcomes={d.get(\"total_outcomes\",\"?\")}  winners={d.get(\"total_winners\",\"?\")}  closing_line_cov={d.get(\"closing_line_coverage\",\"?\")}')"
```

#### Batch 3: Grid health (active leagues only)

```bash
# Check each active grid — the endpoint returns a teams array (no health_score/fill_rate fields)
# Check team count and sample championship probabilities to verify data freshness
for league in nba nhl mlb; do
  source .env.claude && curl -s "https://api.bainluck.com/api/playoffs/$league" \
    | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    teams=d.get('teams',[])
    champs=[t for t in teams if t.get('championship') and t['championship'] > 0.01]
    top=sorted(champs, key=lambda t: t.get('championship',0), reverse=True)[:3]
    names=', '.join(f'{t.get(\"name\",\"?\")}: {round(t[\"championship\"]*100,1)}%' for t in top)
    col_sum=sum(t.get('championship',0) for t in teams)
    print(f'$league: {len(teams)} teams, champ_sum={round(col_sum*100,1)}%, top=[{names}]')
except Exception as e:
    print(f'$league: FAILED ({e})')
" 2>/dev/null || echo "$league: FAILED"
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
- is_winner coverage per source (target: 100% — any gap is a bug)
- Flag any source below 100% as 🔴

**G. Source Coverage (Tier 1 leagues — target 100%)**
- For each Tier 1 sport (basketball_nba, icehockey_nhl, baseball_mlb, americanfootball_nfl): check the % of events with data from each source (Odds API, ESPN, Kalshi, Polymarket, StatPal)
- Flag any Tier 1 source below 100% as 🔴 — every gap is a bug
- Dashboard source_coverage is a list of per-sport dicts with fields: sport, total, live, odds_api, espn, kalshi, polymarket, etc. Calculate percentages as `source_count / total * 100`
- Also check: average sources per live event, any source with 0 recent snapshots

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
