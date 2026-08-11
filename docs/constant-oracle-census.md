# Constant-oracle (tautological) assertion census

> **Generated. Do not hand-edit.**
> `cd backend && python3 scripts/audit_constant_oracle_census.py --artifact > docs/constant-oracle-census.md`
>
> Tracking issue: **#1766**. Authorizing queue for tranche 1: **331**.

## THE RULE — fix-on-touch

**If you touch a line listed in this census, fix it in the same change.**

That is Alex's standing disposition for every row outside tranche 1. There is no
scheduled sweep coming for them; a rule recorded only in a queue report expires with
the session, so it is recorded here, where the person editing the line will find it.
`docs/gotchas-reference.md` carries the one-line pointer.

"Fix it" means: **make the assertion fail when the production constant changes.**
Either assert an independent literal in place, or pin the constant's value in a
companion assertion. Then prove it by mutating the constant and watching the test go red.

**Do NOT delete or weaken an assertion to make it non-tautological.** A branch-selection
assertion that happens to reference a constant is fine and stays — see "Not every hit is
a defect" below.

## The defect

A test that asserts a production value against **the same imported constant the
production code reads** cannot detect a change to that value. Mutating the constant moves
the implementation and the oracle together, so the test stays green while a threshold,
TTL, wire token, state name or sample-size gate changes underneath it.

```python
# production
HUB_PRIMARY_TTL = 180

# test — passes for ANY value of HUB_PRIMARY_TTL, pins nothing
assert ttl_written == hub_route.HUB_PRIMARY_TTL
```

**LAT-P026 is the recorded escape.** That exact shape let the mutation `180 → 60` survive
the suite until the expectation became a literal. The landed correction, with its
rationale, is at `backend/tests/test_hub_cache_swr.py:236-240`.

## Not every hit is a defect

An assertion that tests **branch selection** — "the fallback path returns the default",
"this row classifies as foreign" — is legitimately written against the constant and is
not claiming to pin a value. It is a defect only when the value is *itself the contract*
**and nothing else pins it**.

The discriminator is not readable from the assertion. It is:

> Does **any** test go red when the production constant is mutated?

So this census is a **triage input, not a verdict**. Two constants here already had
companion literal pins before tranche 1 began, and their rows are not defects:
`_DEFAULT_MIN_CATEGORY_OUTCOMES` (pinned at `test_calibration_min_sample_gate.py:69`) and
`MEX_NORMALIZE_THRESHOLD` (pinned at `test_calibration_mex_normalization.py:61`).

## This count is a FLOOR, not a total

Any completeness claim against it is false by construction. Deliberately not counted:

* **helper-mediated assertions** where the production call happens inside a test helper —
  including `test_hub_cache_swr.py:163,198,216,232,253,287`
* **frontend / TypeScript** constant oracles — never scanned
* method calls on objects returned by a helper, where the callable cannot be resolved
  back to a production module

## Provenance

Reproduces C272/B3 (CODEX run 2026-08-11, `.claude/handoff/CODEX-REPORT.md:15516-15522`),
which reported **200 assertions across 42 files** but published *concentrations* — only
~133 rows across 12 of the 42 files were ever enumerated with line numbers. That prose is
not a work list, so this scanner re-derives the census from the tree instead of
transcribing it.

Agreement with B3 on the files B3 did enumerate is exact for
`test_db_session_identity_300b.py` (15), `test_highlights.py` (13),
`test_personalization.py` (45), `test_market_shape.py` (9),
`test_line_movement.py` (4) and `test_calibration_min_sample_gate.py` (5).
This scan also reaches the two-step `x = prod_call(...)` / `assert CONST in x` shape that
B3's direct-call requirement excluded, which is why its total is higher.


## Totals

- **239 assertion lines** (254 file/line/constant rows) across **48 files**
- **71 lines in tranche 1** (calibration / settlement / admin / 300B) across 13 files
- 168 lines outside tranche 1 → **fix-on-touch**

## Tranche 1 disposition (queue 331, 2026-08-11)

Every constant reachable from the tranche-1 files was graded **by mutation**: change the
production constant, run every test that could plausibly detect it, record red or green.
36 distinct constants were graded.

### Mutation-blind → fixed (20)

Each was changed with the **entire** relevant suite staying green. Each now has an
independent literal pin, and each was re-mutated afterwards to confirm it goes red.

| module | constants | pin |
|---|---|---|
| `app/utils/db_session_identity.py` | `APPLICATION_NAME_MAX`, `TAG_SCHEMA`, `UNKNOWN_BUILD`, `CURRENT`, `SUPERSEDED`, `KIND_CURRENT_BEAT`, `KIND_SUPERSEDED_RUN`, `KIND_PREDEPLOY_RUN`, `KIND_UNCLASSIFIED`, `KIND_FOREIGN` | `tests/test_db_session_identity_300b.py::TestWireValuesArePinnedIndependently` |
| `app/utils/calibration_phase_ledger.py` | `BUDGET_SAFETY`, `TERMINAL_FAILED`, `TERMINAL_HARD_LOSS`, `TERMINAL_OVERLAP_REFUSED`, `GREEN`, `UNKNOWN`, `RED`, `FRESH`, `REFUSE`, `RESUME` | `tests/test_calibration_phase_ledger.py::TestLedgerVocabularyIsPinnedIndependently` |

The worst single case was `APPLICATION_NAME_MAX = 63`. It is not a value the project
chooses — Postgres truncates `application_name` at `NAMEDATALEN-1` = 63 bytes, silently,
and the tail it drops is the owner handle. Three assertions bounded the tag against the
constant (`len(tag) <= APPLICATION_NAME_MAX`), so widening the constant to 200 kept all
three green while every emitted tag would have been truncated on the way into
`pg_stat_activity` — defeating the identity contract the 300B work exists to provide.

### Already protected → left alone (16)

Graded, found detectable, **not touched**. Their census rows are branch-selection
assertions, which is what those assertions are for.

`PREDEPLOY` (pinned as a literal in `calibration_orphan_containment_contract.json`),
`PHASE_FUTURES`, `TERMINAL_COMPLETE`, `TERMINAL_PARTIAL`, `TERMINAL_CANCELLED`,
`STATUS_COMPLETE`, `STATUS_INCOMPLETE`, `STATUS_UNAVAILABLE`, `SENTINEL_COVERAGE_THRESHOLD`,
`KALSHI_HOCKEY_HONEST_BAND_MAX`, `KALSHI_PROP_THRESHOLD_DEGENERATE_BAND` (both caught
behaviourally by `test_hockey_goal_family_honest_band_recovered`), `MEX_NORMALIZE_THRESHOLD`,
`_DEFAULT_MIN_CATEGORY_OUTCOMES`, and the composite/structural constants
`REQUIRED_PHASES`, `REACHABILITY_TIER_KEYS`, `DRAW_CAPABLE_CATEGORIES`.

**This split is the argument for grading by mutation instead of by reading.** In one module,
`TERMINAL_COMPLETE`, `TERMINAL_PARTIAL` and `TERMINAL_CANCELLED` were protected while
`TERMINAL_FAILED`, `TERMINAL_HARD_LOSS` and `TERMINAL_OVERLAP_REFUSED` were not — six
constants declared on consecutive lines, used the same way, split three-three. Nothing in
the source distinguishes them; only the mutation does.

### Deferred (1)

`tests/test_calibration_staged_futures.py` (2 lines) is in tranche 1 by scope but was
**excluded**: it is in flight on `program/calibration-34/35/36/37`. Fix-on-touch applies —
the calibration lane owns it. Note that `tests/test_calibration_staged_futures_sql_300d.py`
is a *different* file and was cleared and included; match on path, never on a name that
looks like it belongs to your set.


## Rows

`tranche 1` marks Alex's authorized scope for queue 331. Everything else is fix-on-touch.

| file | lines | assertion lines | constants | tranche 1 |
|---|---|---|---|---|
| `tests/test_personalization.py` | 45 | 148,156,162,167,173,180,189,219,229,239,248,257,270,276,292,304,311,329,340,350,372,379,392,398,408,413,425,499,538,552,563,593,602,620,697,719,733,747,759,814,844,910,976,994,1011 | `ALMA_MATER_BONUS`, `FOLLOW_BONUS`, `HIGH_AFFINITY_BONUS`, `LOCAL_BONUS`, `LOW_AFFINITY_PENALTY`, `MAX_MULTIPLIER`, `MINOR_PRO_PENALTY`, `MIN_MULTIPLIER`, `NAH_AFFINITY_PENALTY`, `PINNED_BONUS`, `RIVAL_LOSING_BONUS`, `RIVAL_PLAYING_BONUS`, `ROSTER_PLAYER_BONUS` | no |
| `tests/test_calibration_phase_ledger.py` | 22 | 90,91,124,212,426,435,447,456,509,526,531,540,548,553,564,594,771,775,778,781,785,1049 | `BUDGET_SAFETY`, `FRESH`, `GREEN`, `INVALIDATE`, `RED`, `REFUSE`, `REQUIRED_PHASES`, `RESUME`, `TERMINAL_CANCELLED`, `TERMINAL_COMPLETE`, `TERMINAL_FAILED`, `TERMINAL_PARTIAL`, `UNKNOWN` | **yes** |
| `tests/test_db_session_identity_300b.py` | 15 | 78,80,82,84,86,113,114,128,147,170,191,192,265,312,333 | `APPLICATION_NAME_MAX`, `CURRENT`, `KIND_CURRENT_BEAT`, `KIND_FOREIGN`, `KIND_PREDEPLOY_RUN`, `KIND_SUPERSEDED_RUN`, `KIND_UNCLASSIFIED`, `PREDEPLOY`, `SUPERSEDED`, `UNKNOWN_BUILD` | **yes** |
| `tests/test_task_resumability.py` | 14 | 211,301,302,303,304,308,310,311,315,316,317,318,319,320 | `COMPLETE`, `FAILED`, `PARTIAL` | no |
| `tests/test_highlights.py` | 13 | 91,111,147,278,384,397,410,421,432,1145,1167,1269,1282 | `WEIGHTS` | no |
| `tests/test_hook_staleness.py` | 12 | 32,68,80,92,104,116,128,165,177,190,202,235 | `HOOK_PROB_METADATA_KEY`, `STALE_HOOK_MAX_AGE_DAYS` | no |
| `tests/test_classification_health.py` | 9 | 61,71,81,103,114,148,149,224,226 | `AUTHORITY_DISAGREE`, `GREEN`, `INVALID`, `MISSING`, `UNKNOWN`, `VERSION` | no |
| `tests/test_market_shape.py` | 9 | 46,64,82,94,126,143,147,155,183 | `SHAPE_CLAIM`, `SHAPE_CONTAINER_MEMBER`, `SHAPE_DUEL`, `SHAPE_FIELD`, `SHAPE_QUANTITY`, `SHAPE_UNSHAPED`, `SIDE_COMPETITORS`, `SIDE_THRESHOLD`, `SIDE_YES_NO` | no |
| `tests/test_calibration_reachability_tier.py` | 8 | 76,101,150,160,167,176,206,222 | `REACHABILITY_TIER_KEYS`, `STATUS_COMPLETE`, `STATUS_INCOMPLETE`, `STATUS_UNAVAILABLE` | **yes** |
| `tests/test_external_curator_freshness.py` | 7 | 29,34,48,59,60,65,71 | `CORPUS_CURRENT`, `CORPUS_EMPTY`, `CORPUS_STALE`, `CORPUS_UNKNOWN`, `RECALL_MAX_AGE_DAYS` | no |
| `tests/test_task_verdict.py` | 6 | 37,50,158,186,195,245 | `UNKNOWN` | no |
| `tests/test_calibration_horizon_honest_263.py` | 5 | 59,60,76,77,118 | `KALSHI_HOCKEY_HONEST_BAND_MAX`, `KALSHI_PROP_THRESHOLD_DEGENERATE_BAND`, `MEX_NORMALIZE_THRESHOLD` | **yes** |
| `tests/test_calibration_min_sample_gate.py` | 5 | 37,40,52,55,62 | `_DEFAULT_MIN_CATEGORY_OUTCOMES` | **yes** |
| `tests/test_calibration_sentinel_prop_threshold.py` | 5 | 65,66,107,145,146 | `KALSHI_HOCKEY_HONEST_BAND_MAX`, `KALSHI_PROP_THRESHOLD_DEGENERATE_BAND`, `KALSHI_PROP_THRESHOLD_NAME_RE`, `SENTINEL_COVERAGE_THRESHOLD` | **yes** |
| `tests/test_interestingness_trending.py` | 4 | 30,43,51,52 | `TRENDING_BONUS` | no |
| `tests/test_kalshi_trade_retention.py` | 4 | 93,100,108,114 | `AT_RISK_AGE_DAYS`, `PROVABLY_PURGED_AGE_DAYS` | no |
| `tests/test_line_movement.py` | 4 | 98,117,145,146 | `MAX_MOVEMENTS_PER_EVENT`, `SIGNIFICANT_MOVE_THRESHOLD` | no |
| `tests/test_overlap_census_walk_p030.py` | 4 | 40,43,56,59 | `WALK_FAST_S`, `WALK_SCAN_MAX`, `WALK_SCAN_MIN` | no |
| `tests/test_resolution_engine.py` | 4 | 326,327,328,329 | `LINK_CROSS_SOURCE`, `LINK_FAMILY`, `LINK_MARKET_CONCEPT`, `LINK_MARKET_EVENT` | no |
| `tests/test_eval_promote_apply.py` | 3 | 33,34,52 | `EVAL_ADJ_CAP`, `EVAL_PROMOTE_TTL_DAYS` | no |
| `tests/test_event_completion.py` | 3 | 41,48,53 | `STILL_ACTIVE_MINUTES` | no |
| `tests/test_reviewer_tier_gate.py` | 3 | 62,63,151 | `DEFAULT_TIER`, `GOLD_TIERS` | no |
| `tests/test_calibration_kalshi_prop_threshold.py` | 2 | 162,165 | `KALSHI_PROP_THRESHOLD_DEGENERATE_BAND`, `KALSHI_PROP_THRESHOLD_NAME_RE` | **yes** |
| `tests/test_calibration_sentinel.py` | 2 | 153,164 | `SENTINEL_COVERAGE_THRESHOLD` | **yes** |
| `tests/test_calibration_session_tagging_300b.py` | 2 | 241,246 | `KIND_CURRENT_BEAT`, `KIND_PREDEPLOY_RUN` | **yes** |
| `tests/test_calibration_staged_futures.py` | 2 | 1598,1634 | `REASON_UNENCODED_UNITS` | **yes** |
| `tests/test_clob_never_graded_cohort.py` | 2 | 53,77 | `_COHORT_NEVER_GRADED` | no |
| `tests/test_enrich_tmdb.py` | 2 | 32,39 | `TMDB_IMG` | no |
| `tests/test_grammar_adapters.py` | 2 | 76,417 | `ROLE_PARTICIPANT` | no |
| `tests/test_market_staleness.py` | 2 | 152,153 | `PROBABILITY_EXTREME_HIGH`, `PROBABILITY_EXTREME_LOW` | no |
| `tests/test_social_ground_truth_extraction.py` | 2 | 111,203 | `EXTRACTOR_VERSION` | no |
| `tests/integration/test_route_admin_cockpit.py` | 1 | 189 | `_WAITING_FALLBACK` | **yes** |
| `tests/test_calibration_result_authority_299.py` | 1 | 350 | `DRAW_CAPABLE_CATEGORIES` | **yes** |
| `tests/test_calibration_staged_futures_sql_300d.py` | 1 | 128 | `VM_ROSTER_MARKET_INFO_EXTRA` | **yes** |
| `tests/test_celery_result_retention.py` | 1 | 197 | `RESULT_CONSUMER_TASKS` | no |
| `tests/test_discover_engagement_rank_buckets.py` | 1 | 41 | `_ENGAGEMENT_RANK_BUCKETS` | no |
| `tests/test_discover_judge_rubric.py` | 1 | 93 | `_JUDGE_FALLBACK_FEW_SHOTS` | no |
| `tests/test_discover_llm_metadata.py` | 1 | 40 | `DISCOVER_LLM_SCHEMA_VERSION` | no |
| `tests/test_feed_cache.py` | 1 | 33 | `FEED_RESPONSE_STALE_TTL_SECONDS` | no |
| `tests/test_flow_sentinel_top1.py` | 1 | 97 | `GOLD_SET_TOP1` | no |
| `tests/test_grid_register_sentinel.py` | 1 | 327 | `REGISTER_LEAGUES` | no |
| `tests/test_search_latency_contract.py` | 1 | 510 | `_SEARCH_DEADLINE_MS` | no |
| `tests/test_sentinel_filing.py` | 1 | 251 | `_ALERT_LIST_MAX_PAGES`, `_PER_PAGE` | no |
| `tests/test_time_horizon_partial_publish.py` | 1 | 42 | `_HORIZONS` | no |
| `tests/test_tonights_games.py` | 1 | 103 | `MAX_LEAD` | no |
| `tests/test_watchdog_alert_dedupe.py` | 1 | 88 | `_WATCHDOG_MARKER` | no |
| `tests/test_win_prob_sources.py` | 1 | 99 | `WIN_PROB_SOURCES` | no |
| `tests/test_winner_field_repair_1527.py` | 1 | 141 | `WRITE_SOURCE` | no |
