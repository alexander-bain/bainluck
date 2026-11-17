# New Grouping Kinds Exam Receipt (November 2026 — #9937)

- **Date:** 2026-11-11
- **Slate:** `new-kinds-exam-test-2026-11` (`20` held-out cards, disjoint from the `10` calibration cards in `new-kind-proposals-2026-11.json`)
- **Grader:** `alex bain` (`evals/ranking/grades/2026-11-10-grouping-new-kinds-exam-test-2026-11-alex-bain.json`, `graded_on="8fd8af11"`)
- **Model:** `gpt-4o-mini` (`LEGACY_MODEL`, Decide 61-A)
- **Reader Reachability:** `False` (`UNLICENSED` until unified 1.0.8 grouping-primitives rollout under Direction `223` / `224`)
- **Issue Receipt:** https://github.com/alexander-bain/bainluck/issues/9937

## Exam Score Summary (`20/20` yes — `18 amazing`, `2 fine`, `0 no`)

| Kind | Positions | Graded | `amazing` | `fine` | `yes` (`amazing` + `fine`) | `no` | `80%+` bar (`>= 8/10`) | `6+ with 0 no` catalog bar | Exam Verdict |
|------|-----------|--------|-----------|--------|----------------------------|------|------------------------|----------------------------|--------------|
| `season_stat_leaders` | 1–10 | `10/10` | `8` | `2` | **`10/10` (`100.0%`)** | `0` | **PASS** | **PASS** | **PASS** |
| `qualification_stage_board` | 11–20 | `10/10` | `10` | `0` | **`10/10` (`100.0%`)** | `0` | **PASS** | **PASS** | **PASS** |
| **Total** | **1–20** | **`20/20`** | **`18`** | **`2`** | **`20/20` (`100.0%`)** | **`0`** | **PASS** | **PASS** | **PASS** |

### Separate Readout — Positions 18–20 (`bubble_50` Cutline Selection)

| Slice | Positions | Graded | `amazing` | `fine` | `no` | Verdict |
|-------|-----------|--------|-----------|--------|------|---------|
| `bubble_50` (closest to `50%` within `25%–75%`) | 18–20 | `3/3` | `3` | `0` | `0` | **PASS (`100.0%`)** |

## Pre-Licensing Selection Guards Enforced in `grouping_kind_proposer.py`

1. **No cliff-drop tail rows on `season_stat_leaders` (`apply_stat_leader_selection_guards`)**:
   - Positions `#08` (`96%, 88%, 87%, 85%, 3%`) and `#09` (`87%, 82%, 79%, 35%, 2%`) carried `2–3%` fifth rows because the venue only listed `5–6` binary player milestones at that threshold.
   - `apply_stat_leader_selection_guards` enforces `MIN_STAT_LEADER_ROW_PROBABILITY = 0.10` (`10%` floor) on `top_5` / `complete_group` rows (trimming `< 10%` cliff-drop tail rows when `>= 3` contenders clear `10%`, and refusing `fewer_than_3_rows_above_10pct` otherwise) and requires an explicit `market_qualifier` whenever a player `top_5` pool has fewer than `MIN_STAT_LEADER_TOP5_PLAYER_POOL = 8` contenders.
2. **Honest subset denominator when a venue covers fewer teams than the league (`compute_selection_carrying_title`)**:
   - Position `#10` printed `"Showing 5 of 21 teams"` because only `21` of `32` NFL teams had an open `9+ wins` market.
   - When `league_team_count > total_member_count` on a `teams` / `clubs` race, `compute_selection_carrying_title` prints `"Showing 5 of 21 teams with a 9+ win market"` (or `"with an open market"`), never implying the league itself has `21` teams.
3. **First-class `bubble_50` selection (`select_bubble_50_rows`)**:
   - Selects the `3–5` contenders closest to `50%` within `[25%, 75%]` and orders them highest-probability-first for display.
