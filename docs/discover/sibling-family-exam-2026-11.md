# Sibling-Family Exam Receipt (November 2026 — #12374)

- **Date:** 2026-11-08
- **Model:** `gpt-4o-mini`
- **Split:** `12` `dev` cards + `20` set-aside `test` cards (`32` total across 3 passes = `96` proposer evaluations)
- **Overall Exam Verdict:** **HELD**
- **Licence (`licences.sibling_family`):** **HELD**
- **Ruling / Brief:** https://github.com/alexander-bain/bainluck/issues/12221 (§3, Decide 61-A / 63-A)
- **Issue Receipt:** https://github.com/alexander-bain/bainluck/issues/12374

## Pre-Run Model Spend Printout (Decide 61-A)

```text
[sibling_family_exam 61-A] model=gpt-4o-mini cards=32 passes=3 calls=96 est_tokens=86400in/42240out estimated_cost=$0.0383 (run_cap=$5.00, month_spent=$0.0000/$30.00) status=OK
```

- **Estimated spend before run:** `$0.0383` (cap: `$5.00`/run, `$30.00`/Nov)
- **Actual usage-rated spend:** `$0.0167` (`58,434` input tokens, `13,224` output tokens across `96` replies)

## Gate Verdict Summary (`PASS`, `FAIL`, or `HELD` waiting for grades)

| Gate | Scope | Bar | Pass 1 | Pass 2 | Pass 3 | Across Passes | Verdict |
|------|-------|-----|--------|--------|--------|---------------|---------|
| `card_vs_single_member` | `test` | Rated Better on >= 85% of held-out test cards (95% CI reported) and Worse on <= 10% | — | — | — | Waiting for grades: 0 of 20 graded (20 ungraded) | **HELD** |
| `relation_truth` | `test` | 100% of member rows share the stated sibling_of parent and vary on the stated axis; 0 duplicate members | 20/20 (PASS) | 20/20 (PASS) | 20/20 (PASS) | — | **PASS** |
| `freshness_and_count` | `test` | 100% of held-out test cards have 3-6 live, unsettled members | 20/20 (PASS) | 20/20 (PASS) | 20/20 (PASS) | — | **PASS** |
| `run_to_run_stability` | `all` | Across 3 runs, >= 90% of proposed cards agree on their member set | — | — | — | 32/32 (89.3–100.0% CI) | **PASS** |

## Held-Out `test` Split Detail (20 Set-Aside Cards, 95% Wilson CI)

- **Card vs single member (`Better`):** Waiting for grades: `0` of `20` graded (`20` ungraded) on `/grade/groupings` (#12373)
- **Relation truth (`sibling_of` parent + axis variation + 0 duplicates):** `20/20` (`100.0%`, 95% CI `83.9%–100.0%`)
- **Freshness and count (`3–6` live, unsettled members):** `20/20` (`100.0%`, 95% CI `83.9%–100.0%`)

## Record Hashes

- `dataset_sha256`: `b7f92afbfd524a1f034f67db549dc3bf69febe2f373a42c1c1c1e8af610ca1aa`
- `scorer_sha256`: `754d2509bc7c12333255d328d86486815ded63f42543540d70d2156497af69f7`
