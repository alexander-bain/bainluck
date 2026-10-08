# #10708 inactive native-scope preparation

PILLARS: TRUTH / FORMATTING. SHIP: reviewed Watch/native fixes can reach testers sooner while retaining their correctness checks.

Pickup: **2026-10-08 00:01:14 UTC**. Root-held reservation9638. Issue10708 was guarded In Progress / root / Building and read back before edits; REST owner comment6049290818 and slice disposition6049293773 were checked. New isolated branch `codex/10708-native-scope-prep` in `/Users/bain/.codex-personal/worktrees/10708-native-scope-prep/bainluck`, exact base **29e7d471b62b459cd896b4a5edfe857ddc401351**. Remote master matched that base at pickup and final source check. No overlapping dirty claimed files or nested AGENTS instructions were found. This scope is disjoint from #10717.

## Four source files

- `.github/scripts/ci-change-scope.sh`: complete caller-supplied BASE HEAD range, `--no-renames`, one bucket; pure ios returns `native`, mixed/unknown/unusable/empty candidate returns `full`. Frontend manifest parsing errors/emptiness now explicitly return full. Existing frontend cross-tier decisions remain guarded.
- `.github/ci-native-backend-readers.txt`: nineteen known direct-signal readers/conservative over-inclusions, explicitly INACTIVE and not a claim of transitive completeness. Retains mutation guard and the roster guard.
- `.github/scripts/ci-native-backend-readers.sh`: executable resolver, strict UTF-8 and64KiB bound; normalized single backend-relative test paths only; no traversal/absolute/options/globs/whitespace-containing paths/duplicates/missing files; validates every row before emitting one exact line. Any refusal emits no partial list and exits nonzero.
- `backend/tests/test_ci_cross_tier_manifest.py`: direct test-body signal guard with strict read/parse failure, honest missed-shape controls, whole-range/mixed/move/fallback fixtures, resolver refusal controls, and a bounded preflight for26 reviewed required native files plus one Watch Swift glob. Missing/empty files, empty glob, Watch deletion and moved fixture refuse. The actual skip-bearing LeaguesView source guard is executed against a missing scratch input and demonstrated to skip; the explicit preflight independently rejects that omission. No app/native files are mutated.

**Inactive boundary verified:** current workflow still accepts only `full|frontend` and normalizes `native` to `full`. `.github/workflows/ci.yml`, all #10717 files, production/deploy predicates and product source are unchanged. This implementation activates no reduced backend/DB selection and establishes no speed saving.

## Gates

Final focused command from backend/: `python3 -m pytest tests/test_ci_cross_tier_manifest.py tests/test_ci_deploy_base_7610.py -q` — **88 passed,0 skipped,3 warnings,52.19s, exit0**. Raw log retained here. Three warnings are existing Pydantic deprecation and two invalid-escape SyntaxWarnings exposed by strict source parsing; no test failure or skip was accepted. Earlier source iteration passed84 tests; four additional refusal cases and directory-pinned scratch Git commands justified the final repeat.

`bash -n` for both scripts, Python compilation and source diff whitespace gate passed. Resolver execution is exercised by the focused suite with exact-output and no-partial-output controls. No Apple/browser/full suite, native parity assertion/mutation execution, live DB, production probe, workflow CI rerun, push, merge or source offer. Startup was not run because no carrying push is proposed here; hosted exact-head CI/security and independent source review remain unpaid before delivery.

## Explicit activation holds

1. The direct signal detector is not an arbitrary Python dependency analyzer. Joinpath-native JSON, dynamic path/extension construction, imported helpers, indirect subprocess scripts and inherited-root Swift globs are retained synthetic misses, not proof of current unrostered readers. Before activation, conservatively map test owners through local imports/conftest/shared fixtures/helpers/literal scripts and retain full coverage for unresolved reach. Parse/read failures now refuse the direct guard.
2. Concrete current edges still require that inventory: mutation guard invokes `backend/scripts/evals/scan_mutation_residue.py`, whose transitive harvest reaches mutation scripts/native inputs; Watch fresh-face receipt reads `tools/watch-ui-journey.sh` and invokes `tools/watch_iphone_receipt.py`. Keeping the owners rostered does not prove every indirect owner is discovered.
3. Database target indirect native reach is not established by direct grep. Reduced DB/search aggregate selection remains blocked until its conservative dependency boundary is accepted.
4. Mutation Pass B still defaults to `origin/master...HEAD`, while the classifier uses caller BASE HEAD. On a master checkout those can differ or Pass B can be empty. No scanner rewrite or exact-range residue guarantee was added to this four-file slice.
5. After #10717 handback, Root must separately assign workflow adoption/guards from its exact carrier. Required contexts, current frontend/Jest/contract/Apple/security/refusal/release behavior remain in force. An eligible carrying native candidate must prove actual roster execution, no missing native evidence, intended aggregates and elapsed/queue time. No source acceptance, activation safety, adoption or forecast saving is promoted to a delivery result here.

Return source for the existing independent review. Root alone releases9638, updates GitHub status, and assigns any activation follow-up. Production delivery continues independently.
