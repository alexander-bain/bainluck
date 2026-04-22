---
description: Run a full site health check — link rates, grid health, quota, tests, deploy status — with plain-English analysis and recommended actions.
allowed-tools: Bash, Read, Grep, Glob
---

# Health Check

Run a comprehensive Bain Luck health check. Query all admin endpoints, analyze the results, and produce an actionable briefing with what's going well, what's not, and specific actions to improve.

## Steps

### 1. Gather data from all admin endpoints

Run these commands in parallel:

```bash
# Link rate health (game prop → event matching)
curl -s "https://api.bainluck.com/api/admin/prediction-markets/link-rate?secret=$ADMIN_SECRET"

# Overall matching status
curl -s "https://api.bainluck.com/api/admin/prediction-markets/status?secret=$ADMIN_SECRET"

# Admin dashboard (quota, database, tasks, coverage)
curl -s "https://api.bainluck.com/api/admin/dashboard?secret=$ADMIN_SECRET"

# Grid health for active leagues
curl -s "https://api.bainluck.com/api/playoffs/nba?secret=$ADMIN_SECRET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k: d[k] for k in ['health_score','fill_rate','source_breakdown'] if k in d}))"
curl -s "https://api.bainluck.com/api/playoffs/nhl?secret=$ADMIN_SECRET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({k: d[k] for k in ['health_score','fill_rate','source_breakdown'] if k in d}))"

# Test count
cd backend && python3 -m pytest tests/ --co -q 2>&1 | tail -1

# Git status
git log --oneline -3
git status --short | head -10

# Manus audit — last run date + status
cat Manus/audit_results/latest/manifest.json 2>/dev/null || echo "No Manus audit results"

# Manus audit — check task completion status via API (if key available)
source ~/.zshrc 2>/dev/null; if [ -n "$MANUS_API_KEY" ]; then
  for tid in $(cat Manus/audit_results/latest/manifest.json 2>/dev/null | python3 -c "import json,sys; [print(t['task_id']) for t in json.load(sys.stdin).get('tasks',{}).values()]" 2>/dev/null); do
    curl -s "https://api.manus.ai/v2/task.detail?task_id=$tid" -H "x-manus-api-key: $MANUS_API_KEY" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin).get('task',{}); print(f'  {d.get(\"title\",\"?\")[:50]}: {d.get(\"status\",\"?\")} ({d.get(\"credit_usage\",0)} credits)')" 2>/dev/null
  done
fi
```

### 2. Analyze and present results

For each section below, present:
- **Status**: 🟢 Good / 🟡 Needs attention / 🔴 Problem
- **Numbers**: The key metrics
- **What's going well**: Specific positive trends
- **What's not**: Specific issues
- **Recommended action**: One concrete next step

#### Sections to cover:

**A. Odds API Quota**
- Current usage vs budget
- Projected end-of-month surplus/deficit
- Daily burn rate trend
- Action: any tier adjustments needed?

**B. Game Prop Link Rate (Market ↔ Event matching)**
- Per-sport open link rates for Kalshi and Polymarket
- Compare against targets (>85% for major sports)
- Which sports improved vs degraded since last check
- Action: which sport to investigate next?

**C. Championship Grid Health**
- NBA and NHL grid health scores
- Fill rates by column (championship, conference, division, make_playoffs)
- Source diversity (Kalshi + Polymarket + Odds API)
- Action: any columns missing data?

**D. Source Coverage (Event ↔ Source matching)**
- Average sources per live event
- Any sources that went dark (0 snapshots recently)
- Action: any integrations need attention?

**E. Database & Infrastructure**
- DB size and growth rate
- Snapshots per hour (odds + win_prob)
- Worker task health (success/failure rates)
- Action: any retention or cleanup needed?

**F. Test Suite**
- Total test count
- Any failures
- Coverage gaps worth noting
- Action: any critical untested code?

**G. Recent Deploys**
- Last 3 commits
- Any uncommitted changes
- Action: anything that should be committed or reverted?

**H. Manus QA Audit**
- Last audit date (from `Manus/audit_results/latest/manifest.json`)
- Modules run and their status (complete/timeout/error)
- Key findings from the latest reports (scan `Manus/audit_results/latest/*.md`)
- Days since last audit — flag if >7 days
- Action: run `python3 scripts/manus_health_suite.py --smoke` if stale, or full suite with no flags
- Credit usage trend (from manifest)

### 3. Top 3 recommendations

End with a prioritized list:
1. The single highest-impact action to take right now
2. Something that should be monitored over the next few days
3. A structural improvement for the next session

Keep the whole output concise — aim for a briefing you can read in 60 seconds.
