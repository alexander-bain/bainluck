# Web embedded market stream #9524 / final winner quote #9544

SOURCE PASS for the exact seven-file SHA256 snapshot in the adjacent JSON, on base 05ded4f9d5eebccba718e990e3f86c4f970eae7e.

Independent source review covered new hook, fetch, reconciler, event-page wiring, final winner rendering, and regression-test source. Shared scheduler and stream-controller dependencies were inspected without modifications. No duplicate gates, production reads, captures, or author-file edits were performed.

All four initial findings are resolved: first final winner quotes may appear at unchanged known revisions; representative whole-book selection changes do not invent withdrawal fences; actual winner-book withdrawal uses all constituents and requires an advance from that book; raw nonunit venue vectors retain their scalar percentages. Final winner quotes are validated against their own canonical event, stream market set, exact outcome bindings, complete side set, and valid contributor identities. Terminal IDs clear both held and incoming quotes before unrelated regression refusals.

Regression source now covers first-final quiet quotes, A-to-B-to-A book selection, one-own-constituent restoration versus unrelated revision, initial missing membership/binding, delayed invalid binding versus explicit closure, and raw 50/51 and 50/49 rendering. Existing coverage retains final scores/grades, clock ordering, missing-row withdrawals, nested matchups, source age honesty, navigation cleanup, hidden-page behavior, all 101 IDs reaching the shared stream hook, fresh fetch, and 429 cooldown.

Shared dependencies provide all-ID 50-market batching, one in-flight read plus trailing coalescing, two-second dispatch pacing (approximately 30 reads/minute against the 60/minute embedded budget), hidden abort/generation fences, 60-second REST fallback, and bounded transport recovery.

This is source review only. Executable tests/build/typecheck are author-owned; CI, deployment, held-page browser proof, and production acceptance remain separate gates.

Post-review bookkeeping: the gameMarketsStream9524 test fixture cast changed only from `as LiveGameMarkets` to `as unknown as LiveGameMarkets` to resolve TS2352. Reversing that single replacement exactly reproduces the previously reviewed SHA256. The other six files remain unchanged. Source PASS retained; no reviewer gates rerun. Author reports 56 focused/adjacent tests, build, and typecheck passing; local 390px component evidence is not held-page or production acceptance.
