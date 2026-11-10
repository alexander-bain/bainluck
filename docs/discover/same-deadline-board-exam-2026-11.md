# Grouping Kind Licences & Second-Kind Exam Receipt (November 2026 — #12375)

- **Date:** 2026-11-08
- **Issue:** https://github.com/alexander-bain/bainluck/issues/12375
- **Ruling / Brief:** https://github.com/alexander-bain/bainluck/issues/12221 (Part 1 rows 8 and 10, Decide 63-A, `docs/design/grouping-primitives.md` §5)

## 1. Kind Licence Registry Summary (`backend/data/grouping_licences.json`)

| Grouping Kind | Mode | Exam / Bar | Licence Status | Notes |
|---------------|------|------------|----------------|-------|
| `subject_sequence` | `rules_only` | No exam run yet (`exam_receipt: null`) | **HELD** | Held until a `subject_sequence` exam and human grading pass; `celtics-next-3-games` and `lakers-next-3-games` ship as hand-authored definitions |
| `sibling_family` | `model_proposer` | 20 set-aside `test` cards (#12374, 3/4 gates `PASS`, Gate 1 `0/20` graded) | **HELD** | Held for human grading on `/grade/groupings` (#12373) |
| `same_deadline_board` | `rules_proposer` | 20 coming calendar deadlines (Gates 2 & 3 `FAIL` at `7/20`, Gate 4 `PASS`, Gate 1 `HELD`) | **FAIL** | Only `7` of `20` coming calendar deadlines have 4–6 in-band binary markets across 3+ categories |

## 2. Second-Kind Exam: `same_deadline_board` (New Same-Deadline Boards for Each Coming Deadline)

- **Candidate coming deadlines evaluated:** `20` (`2026-11-15` through `2027-06-30`)
- **Model spend (Decide 61-A / 61-C):** `$0.0000` (rules-only deadline pool selector)
- **Overall Exam Verdict:** **FAIL**
- **Licence (`same_deadline_board`):** **FAIL**
- **Dataset SHA-256:** `0fd35a9afb51567a4db122b4a268a4f8b32822e55cfee27665102c736772a5e3`

| Gate | Bar | Observed (`k/n`) | 95% Wilson CI | Verdict |
|------|-----|------------------|---------------|---------|
| `card_vs_single_member` | Rated Better on >= 85% of set-aside deadline boards and Worse on <= 10% | `0/20` | `0.0%–16.1%` | **HELD** |
| `deadline_and_category_truth` | 100% of candidate deadline boards span >= 3 categories on the same calendar day with 0 excluded classes | `7/20` | `18.1%–56.7%` | **FAIL** |
| `freshness_and_count` | 100% of candidate deadline boards have 4-6 live, unsettled binary markets in [5%, 95%] | `7/20` | `18.1%–56.7%` | **FAIL** |
| `run_to_run_stability` | Across 3 runs, >= 90% of proposed deadline boards agree on their member set | `20/20` | `83.9%–100.0%` | **PASS** |

## 3. Reviewed Promotion & Suspension Proof (`grouping-primitives.md` §5)

- **Reviewed promotion (`promote_licensed_proposal_to_definition`):** Refuses unlicensed kinds (`HELD` / `FAIL` / `SUSPENDED`) or any kind without an `exam_receipt`. Once a kind earns `status: PASS` with its exam receipt, promotes proposals into `backend/data/containers/<slug>.json` with `authored_by.review_path = "tier-b-pr"`.
- **Suspension (`detect_served_card_violation` + `suspend_grouping_kind`):** `run_licensed_promotion_pass` inspects `served_cards` for truth violations (settled members, fewer than 2 rows, out-of-range probabilities); one wrong served card transitions the kind's licence to `SUSPENDED` (recording `suspended_by_card_slug`, `suspended_reason`, and `suspended_at`) and stops new cards (`stopped_reason = "kind_suspended"`, `promoted_definitions = []`).
