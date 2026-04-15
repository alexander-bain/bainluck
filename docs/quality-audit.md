# Quality Audit System ("Quality Ratchet")

A self-reinforcing data quality loop. The goal: define a problem once, it's fixed forever. New issues get added to the quality definition so they're caught going forward.

## The Script

`backend/scripts/audit_matching_quality.py` — comprehensive page health audit with deterministic + LLM checks.

```bash
# Quick scan (free, ~5s):
python3 scripts/audit_matching_quality.py --skip-llm --save

# Full audit with LLM + compare against last baseline:
OPENAI_API_KEY=... python3 scripts/audit_matching_quality.py --compare --save

# Grid-only or event-only:
python3 scripts/audit_matching_quality.py --skip-event --grid nba --skip-llm
python3 scripts/audit_matching_quality.py --skip-grid --event-id 12086896 --skip-llm
```

## Health Score

- Starts at 100, penalized per finding: critical = -10, warning = -3, info = -1
- `--save` persists results to `scripts/audit_results/` with timestamps
- `--compare` shows delta vs last run: FIXED / NEW / PERSISTENT findings

## When to Use Deterministic vs LLM Checks

- **Deterministic** (preferred): Probability sums, missing data fields, fill rates, source disagreements, monotonicity, duplicates, trend anomalies. These are free, instant, and 100% reliable.
- **LLM** (semantic): Label clarity ("is this name understandable to a casual fan?"), team-market matching ("is this player on this team?"), category correctness. These cost ~$0.01/run but can have false positives — tune the prompt and re-run.

## Current Checks

| Check | Type | Category | What it catches |
|-------|------|----------|----------------|
| `hero_probability_sum` | Deterministic | Event | Home + away odds not summing to ~100% |
| `feed_detail_mismatch` | Deterministic | Event | Feed vs detail page probability inconsistency |
| `missing_team_logo` | Deterministic | Event | Missing logos in event data |
| `matchup_prob_sum` | Deterministic | Futures | Matchup probs inflated (NegRisk market sum check) |
| `duplicate_label` | Deterministic | Futures | Same market from same source appearing twice |
| `cross_source_visual_dupe` | Deterministic | Futures | Same label from different sources (visual clutter) |
| `win_total_resolved` | Deterministic | Futures | Near-resolved win total thresholds (noise) |
| `label_clarity` | LLM | Futures | Unclear/misleading market labels |
| `team_matching` | LLM | Futures | Market incorrectly associated with team |
| `game_state_missing` | Deterministic | Event | Live/completed event with no period boundaries for charts |
| `game_state_weak_source` | Deterministic | Event | Period data only from fallback sources |
| `grid_fill_rate` | Deterministic | Grid | Columns with low data coverage |
| `grid_single_source` | Deterministic | Grid | Columns using only 1 source when more available |
| `grid_team_identity` | Deterministic | Grid | Teams missing logo, team_id, record |
| `grid_source_disagreement` | Deterministic | Grid | >15pp source disagreement |
| `grid_monotonicity` | Deterministic | Grid | Later round prob > earlier round prob |
| `grid_universal_decline` | Deterministic | Grid | >75% of teams trending same direction |
| `grid_prob_sum` | Deterministic | Grid | Championship probs not summing to ~100% |

## Adding New Checks

Add a function to the audit script following the pattern:
```python
def check_my_new_issue(data: dict, report: AuditReport):
    """Check for [description of the issue]."""
    if problem_detected:
        report.add(AuditFinding(
            check="my_new_issue",
            severity=SEVERITY_WARNING,  # critical/warning/info
            category="grid",            # event_detail/related_futures/grid
            description="Human-readable description of the problem",
            details={"key": "value"},   # Stable keys for fingerprinting
        ))
```
Then call it from `audit_event_detail()` or `audit_championship_grid()`. Update this table.
