Fable: needed (reader-visible | destructive | eval) OR Fable: not needed
<!-- 119-A (#12539): keep exactly one of the two on this first line. "needed" when the PR changes what a reader sees or a number a reader sees (web, phone, Watch), deletes or rewrites stored data or is migration-class, or changes an eval, a gate, an exam, a licence or grades. Otherwise "not needed": the PR merges on claude[bot]'s approval and green CI. The Tier-B approval check blocks a "not needed" PR that touches a listed path (tools/release/tier_b.cjs, FABLE_PATHS). -->

## Summary

<!-- 1-3 bullet points: what changed and why -->

## Test plan

- [ ] Smoke test: `cd backend && python3 -m pytest tests/test_startup.py -v`
- [ ] Verified on live site / simulator
- [ ] No regressions in related features
