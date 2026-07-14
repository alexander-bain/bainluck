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

`backend/scripts/audit_feed_quality.py` — Discover-specific quality audit for ranking, variety, and explanation coverage.

```bash
# Discover feed precision and variety:
cd backend && python3 scripts/audit_feed_quality.py

# Include Polymarket email-highlight ground truth from a downloaded sheet CSV:
POLYMARKET_EMAIL_GROUND_TRUTH_CSV_PATH=/path/to/polymarket_email_ground_truth.csv \
  python3 scripts/audit_feed_quality.py

# Or from a published/exportable CSV URL. The URL must be readable without
# an interactive Google login; a browser-only download can still return 401
# from backend/audit jobs if the sheet is private.
POLYMARKET_EMAIL_GROUND_TRUTH_CSV_URL="https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0" \
  python3 scripts/audit_feed_quality.py

# Or from a private Google Sheet shared with the Firebase service account:
POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID="..." \
POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME="Audit Export" \
FIREBASE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}' \
  python3 scripts/audit_feed_quality.py
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

## Discover Feed Quality Checks

The Discover audit is mandatory before and after ranking, explanation, hook-enrichment, personalization, or card-display changes that affect `/discover`.

Personalization changes should also run focused unit coverage for `tests/test_personalization.py`, `tests/test_feed_discover_affinities.py`, and `tests/test_feed_dismiss_propagation.py` so category penalties, feature affinities, story/group suppression, and semantic-dismiss soft penalties stay bounded.

Targets:
- `boring-rate@20=0/20`
- `ladder/bucket-rate@20=0/20`
- `duplicate-family-rate@20=0/20`
- `explanation-coverage@20=20/20`
- `positive-archetypes@20>=5/6`
- `strict-variety@20>=4/5`
- `fun-market-presence@10=true`
- `category-spread@20>=6`, max category count `<=5`
- `snippet-issues@20` should trend down; current checks flag overlong snippets, title repetition, generic resolution copy, and context without concrete signals.
- Discover cards should use top-level `context_summary` for visible copy and reserve full `hook_description` text for expansion.
- Optional Polymarket email ground truth reports `email-hit@20` / `email-hit@50` when `POLYMARKET_EMAIL_GROUND_TRUTH_CSV_PATH`, `POLYMARKET_EMAIL_GROUND_TRUTH_CSV_URL`, or `POLYMARKET_EMAIL_GROUND_TRUTH_URL` is set. Stable export headers are preferred: `date`, `source`, `market_name`, `category`, `leader`, `leader_probability`, `resolution_date`, `email_subject`, `llm_category`, `hook`, `interestingness`, `timeliness`, `shareability`.
- Private Google Sheets are supported through `POLYMARKET_EMAIL_GROUND_TRUTH_SPREADSHEET_ID` + `POLYMARKET_EMAIL_GROUND_TRUTH_SHEET_NAME` when `FIREBASE_SERVICE_ACCOUNT_JSON` or `GOOGLE_APPLICATION_CREDENTIALS_JSON` is configured. If a CSV export URL returns 401 and service-account credentials are present, the loader falls back to the Sheets API using the spreadsheet id parsed from the URL.
- The email ground-truth loader records raw row count, loaded row count, latest email date, and stale status (`>2d` old). `/admin/discover-quality` surfaces those diagnostics when the feed debug endpoint is configured. If the export is private, the audit/admin UI reports the HTTP error instead of failing the whole feed debug request.
- Keep email ground truth evaluative until the hit/miss profile is understood; email-highlighted markets must not bypass quality filters.
- Async Discover LLM metadata is also evaluative/supporting: `market_metadata->discover_llm` may nudge ranking within tight deterministic bounds, but no feed request may call OpenAI. The daily `evaluate_discover_with_llm` job writes advisory `llm_proposed_*` review decisions only; those proposals must not affect ranking until accepted by a human.
- Offline interestingness scoring lives in `backend/app/utils/market_interestingness.py` with local calibration support in `backend/scripts/calibrate_interestingness.py`. Treat it as a review scaffold for labeled CSV/JSON/JSONL rows; it should not change feed ranking until audit output, precision/recall on labels, and qualitative traces are reviewed.

Related admin surfaces:
- `/admin/discover-quality` for feed audit, hook coverage, timing, ground-truth traces, engagement, and opportunity signals.
- `/api/feed?debug=true&secret=...` for current feed stage timings and quality metadata.
- `/api/admin/discover-quality/trace/{market_id}` for per-market ranking/quality trace.
- `/api/admin/discover-engagement` for first-party impression/action rollups, including context expansion counts/rates and Today’s Challenge starts/completions/completion rate.

## Automated Sentinels (the always-on arm of the ratchet)

The scripts above are run-on-demand. Two Celery **sentinels** now run the same "define a problem once, catch it forever" loop automatically and **auto-file evidence-packed GitHub issues** when they regress. Full architecture (files, beats, endpoints, thresholds) is in `docs/architecture-reference.md` → "Reliability Machinery"; the operating contract for the issues they file is in `docs/github-workflow.md` → "Automated issue intake". Summary:

| Sentinel | Cadence | Guards | Files issues as |
|----------|---------|--------|-----------------|
| **Flow Sentinel** (`tasks/flow_sentinel.py`) | daily 07:10 UTC | the user-facing half of the matching table + Alex's six failure classes (search gold set, duplicate events, event completeness, resolved-state, chart density, category/Discover) | one deduped, fingerprinted issue per failing flow, `alert-intake` + `needs-agent`, P1/P2 |
| **Calibration Sentinel** (`tasks/calibration_sentinel.py`) | weekly Mon 06:20 UTC | calibration accuracy — MCE across `category × source × series-family × structure × provenance` cohorts on the RAW population | one issue per broken cohort (never writes market data, gotcha #21) |

Run them on demand: `POST /api/admin/flow-sentinel/run` (params `file_issues`, `canary`, `inline`) and `POST /api/admin/calibration-sentinel/run`; last-run results at `GET /api/admin/{flow-sentinel,calibration-sentinel}/last`. The **admin cockpit** (`GET /api/cockpit`, rendered in `/admin`) surfaces the Flow Sentinel scorecard plus green/amber/red autopilot tiles.

Two operating notes that gate trust in the sentinels:
- **`GITHUB_TOKEN` must be set on Heroku** or backend issue-filing silently no-ops — check this FIRST before debugging filing logic (memory `project_github_token_unset`).
- **A sentinel green depends on the beat actually firing.** Code presence ≠ firing; confirm via the cockpit `fires/24h` autopilot tiles (this is the standing watch on the dedicated cal-price beat).

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
