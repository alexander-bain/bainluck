# Independent bounded GET lease review

Scope: deterministic local tests only. No production changes, frozen packet edits, browser, network, full app build, or push. Candidate module seam is supplied by the implementer; tests and generated results stay in this directory.

## Invariant

For a response whose server-side remaining lease is R milliseconds at snapshot, a request dispatched at monotonic time S may authorize display only before S + R, never receipt + R. Arrival exactly at the deadline abstains. The response's remaining budget may be reduced conservatively but never enlarged. Client wall clock offset or jump must not change this bound. Existing epoch, sequence, revoke, committed-floor, observation-time, request-cancellation, and pending UI rules continue to hold.

## Deterministic adversarial matrix

1. Positive admission before request-start plus remaining lease and refusal at the exact boundary.
2. Delayed response consumes budget; response transit never grants fresh TTL.
3. Large positive/negative client wall offsets and forward/backward wall jumps have identical monotonic results.
4. A stalled expiry timer cannot admit a response or render an overlay after its deadline.
5. Aborted, superseded, old-event, disposed, or inactive requests cannot deliver authority even when fetch ignores abort.
6. Duplicate response and equal-sequence response with inflated TTL cannot extend held authority or revive expired state.
7. Newer revoke, newer sequence, newer epoch, or committed-floor adoption defeats an older captured response.
8. Invalid, absent, non-finite, negative, or malformed lease/timing metadata fails closed without losing valid newer authority.
9. The original display observation timestamp remains unchanged.
10. Existing pending timeout and no-probability state remain separate from expiry authority and GET success.

Testing uses real candidate modules bundled in memory only, with independent deterministic clocks and explicit time advancement. A negative control must demonstrate the old arrival/wall-clock-sensitive policy when relevant. Test expectations are not computed by calling the candidate's helper under test.
