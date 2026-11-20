# Sibling-Family Exam Receipt (November 2026 — #12374)

- **Date:** 2026-11-10
- **Model:** `gpt-4o-mini`
- **Split:** `12` `dev` cards + `20` set-aside `test` cards (`32` total across 3 passes = `96` proposer evaluations)
- **Overall Exam Verdict:** **PASS**
- **Licence (`licences.sibling_family`):** **PASS**
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
| `card_vs_single_member` | `test` | Rated Better on >= 85% of held-out test cards (95% CI reported) and Worse on <= 10% | — | — | — | Better 20/20 (83.9–100.0% CI — the interval's low end is 83.9%, which is what 20 cards from one grader can show; 109-A: amazing+fine->better), Strict 'Amazing' 20/20 (100.0%), Worse 0/20 (0.0–16.1% CI), Graded 20/20 | **PASS** |
| `relation_truth` | `test` | 100% of member rows share the stated sibling_of parent and vary on the stated axis; 0 duplicate members | 20/20 (PASS) | 20/20 (PASS) | 20/20 (PASS) | — | **PASS** |
| `freshness_and_count` | `test` | 100% of held-out test cards have 3-6 live, unsettled members | 20/20 (PASS) | 20/20 (PASS) | 20/20 (PASS) | — | **PASS** |
| `run_to_run_stability` | `all` | Across 3 runs, >= 90% of proposed cards agree on their member set | — | — | — | 32/32 (89.3–100.0% CI) | **PASS** |

## Held-Out `test` Split Detail (20 Set-Aside Cards, 95% Wilson CI)

- **Card vs single member (`Better`):** `20/20` (`100.0%`, 95% CI `83.9%–100.0%` — the interval's low end is `83.9%`, which is what `20` cards from one grader can show), graded `20/20` on `/grade/groupings?slate=sibling-family-exam-test-2026-11` (#12373, #12374)
- **Dev split human grades (`#12500`):** `6` of `12` `dev` cards graded by `alex bain` on `2026-11-09` (`6/6` better under Decide `109-A`, `3/6` strict `Amazing`, `6` `dev` ungraded), matched strictly by `family_slug`. All `20` held-out `test` cards on `/grade/groupings?slate=sibling-family-exam-test-2026-11` were graded `amazing` (`20/20` better, `0/20` worse) by `alex bain` on `2026-11-10`; `licences.sibling_family` is `PASS` under Decide `117-A`.
- **Relation truth (`sibling_of` parent + axis variation + 0 duplicates):** `20/20` (`100.0%`, 95% CI `83.9%–100.0%`)
- **Freshness and count (`3–6` live, unsettled members):** `20/20` (`100.0%`, 95% CI `83.9%–100.0%`)

## Record Hashes

- `dataset_sha256`: `b7f92afbfd524a1f034f67db549dc3bf69febe2f373a42c1c1c1e8af610ca1aa`
- `scorer_sha256`: `754d2509bc7c12333255d328d86486815ded63f42543540d70d2156497af69f7`
