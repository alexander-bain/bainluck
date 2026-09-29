# TRUTH — held Discover cards show assigned results instead of stale forecasts

Issue #9515; companion to backend PR9546 and the #9484 live-price delivery program.

Full and grouped compact web cards switch to a result branch when the body carries an assigned resolved flag, terminal status, or named winner. They render the recorded winner, or an honest Resolved label for unnamed/all-loss results. The stale forecast caption, probability, movement and probability share text no longer survive the assigned terminal body. Navigation and existing actions are preserved. Dates and extreme prices never infer settlement.

## Validation

- Independent root SOURCE PASS; exact file bindings in INDEPENDENT-ROOT-SOURCE-REVIEW.json.
- New mounted/server-rendered regression suite: 12 PASS.
- Three adjacent futures hero suites: 23 PASS.
- Production build: PASS.
- Typecheck: PASS, 66 existing errors matches baseline66.
- Backend startup smoke: 4 PASS.
- Whitespace: PASS.

The test harness uses the existing minimal DOM with React act/createRoot; no dependency was added. Native intentional removal of terminal Discover cards is unchanged. No deployment, installed-device or held-production-page acceptance is claimed. Backend PR9546 plus this web companion need release and UX held-page390px confirmation before issue acceptance.
