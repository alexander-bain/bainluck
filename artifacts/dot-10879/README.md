# Settled all-HIT browser proof (#10879)

Code/source head: `55745e8866d0b73001da4ffb67abba95a79676c8`.
This evidence-only follow-up does not change application/test/config bytes.

## Reader journey

Cloud Chrome, Bain Luck signed out, 390 CSS-pixel viewport, DPR 3 through ordinary 300% browser zoom and window sizing (not device emulation). Open event 15327330, reach Player Props, select Points.

- BEFORE public https://www.bainluck.com/events/15327330 at 2026-10-11 13:56 UTC: Nylander `5 of 1 · HIT · needed 1+`, Matthews `4 of 1`, Paul `2 of 1`. MacKinnon `2 · HIT 2+ · MISS 3+`.
- AFTER https://bainluck-fwdndg9d9-alexander-bain.vercel.app/events/15327330 at 2026-10-11 14:18 UTC: Nylander `5 · HIT 3+`, Matthews `4 · HIT 3+`, Paul `2 · HIT 2+`. MacKinnon unchanged `2 · HIT 2+ · MISS 3+`.
- Search Nylander shows his Points `5 · HIT 3+`, Assists `3 · HIT 2+`, Goals split `2 · HIT 2+ · MISS 3+`. Clear search, switch Assists, return Points: result retained.
- Vercel's authenticated dashboard https://vercel.com/alexander-bain/bainluck/B6GZFGVV1KhxRn4ieZF38PSW5rGs showed Ready, Preview, branch `codex/dot-10879-settled-prop-hit-line`, exact source `55745e8866d0b73001da4ffb67abba95a79676c8`, completed 14:14:21 UTC.

[Before Points](points-before-390css.jpg) | [After Points](points-after-390css.jpg) | [Before story showing the higher HIT](story-before-390css.jpg)

The 11 selected Points rows in `frontend/__tests__/fixtures/settledAllHit10879.json` were re-fetched from the public game-markets endpoint at 14:18 UTC and are identical to the 13:57 capture. Original whole-payload SHA256: `61dd089e00aedb5f7a8be2fdaf2f38a31c02f5a0c04cbd827b7b5a56d67ddf1f`.

## Validation of source head

- Focused six related suites: 122 passed, including 32 new rendered tests.
- New regression suite on untouched base `8e9e8d29e36a540a517a605d56e48ca7c45a67e3`: 13 failures / 19 passes; same suite on fix: 32 passes.
- Full frontend Jest: 1,405 passed suites, 2 skipped; 21,036 passed tests, 7 skipped; exit 0. The broad prop regex matched the checkout path and selected all 1,407 suites; this run was allowed to finish.
- Production build/ESLint: exit 0. Local verification used temporary Sentry build telemetry=false, no runtime DSN/token, Next telemetry disabled. Tracked config restored byte-for-byte; no config change committed. Initial default telemetry transmission was rejected and not retried.
- Typecheck: exit 0, 66 errors matches existing baseline 66, no new errors.
- Backend startup smoke: 4 passed.
- git diff --check: clean. Independent source review: no correctness blocker.
- Explicit regressions cover typed HIT, unknown/incomplete grades, split, null/zero actual, two-rung coverage, Under-first/Under-only, contradictory duplicates, positive pre/live expectations, reversed order, compact/full surfaces.

Hosted checks are reported separately in the PR. These are preview results, not production verification. Issue remains open for independent Integrator review/composition and deployed-source verification.
