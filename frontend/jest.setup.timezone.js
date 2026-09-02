"use strict";

/**
 * #2462 — the unit suite renders wall-clock copy, so it needs a fixed zone.
 *
 * ## What was wrong
 *
 * Three suites assert rendered date/time strings — `Yesterday 8:10 PM`,
 * `Starts Thu, Aug 13` — against fixed instants. The instants are fixed; the
 * *renderer* was not. CI runs UTC, so those strings were authored in UTC and
 * are green there, while `npx jest` on a machine in US/Pacific produced
 * `Yesterday 1:10 PM` and `Starts Wed, Aug 12`: 13 failures across
 * `discoverSettledCardRecency`, `discoverTournamentCardTiming` and
 * `gameTimeLabel`, on a verified-clean tree.
 *
 * This is the gotcha #44 family ("test anchors must not branch on the clock")
 * expressed in *timezone* rather than in *the moment*. The anchor is frozen and
 * the assertion is still non-deterministic, because the environment that
 * formats it is not.
 *
 * ## Why pin the environment rather than weaken the assertions
 *
 * The product renders in the viewer's zone, so `toLocaleString`-shaped output
 * IS the thing under test. Rewriting the assertions to be zone-independent
 * would test a formatting of the instant that no user ever sees. Pinning the
 * test environment instead makes the local run identical to the CI run, and —
 * the actual point — makes CI's implicit UTC assumption *explicit* and
 * enforced, instead of an accident of where the runner happens to live.
 *
 * ## This file VERIFIES the pin; it does not apply it
 *
 * The assignment lives in `jest.config.js`, and the obvious-looking version of
 * this file — `process.env.TZ = "UTC"` right here — is wrong. Jest builds each
 * test file's `vm` realm BEFORE running `setupFiles`, and that realm's `Date`
 * keeps the zone it was born with. Assigning here is a **silent no-op**:
 * measured under `TZ=US/Pacific`, `new Date(0).getTimezoneOffset()` was still
 * 480 after the assignment, and all 13 failures stayed exactly as they were
 * while the config claimed the zone was pinned. (A probe in bare `node` says
 * the assignment works — the realm is the difference, so bare `node` is the
 * wrong instrument for this question.)
 *
 * So the pin happens at config load, before any realm exists, and this file is
 * the half that proves it took effect *inside* the realm. That split matters:
 * a pin nobody verifies is exactly the "green badge over a gate that is not
 * running" failure mode `__tests__/lib/ciJestGate.test.ts` exists to prevent,
 * and this check has already earned its place by catching the no-op above.
 *
 * `setupFiles` (not `setupFilesAfterEach`) so the check runs before the module
 * under test is imported — a module that formats a date at import time would
 * otherwise capture the wrong zone before any later hook could complain.
 */

// The epoch renders as a different calendar DAY in every zone west of London,
// which makes it the cheapest unambiguous probe: any zone offset at all moves
// it off `Thu Jan 01 1970 00:00:00 GMT+0000`.
const probe = new Date(0);
if (probe.getTimezoneOffset() !== 0) {
  throw new Error(
    "#2462: setting process.env.TZ='UTC' did not retime Date in this realm " +
      `(getTimezoneOffset() === ${probe.getTimezoneOffset()}, expected 0). ` +
      "The suite's wall-clock assertions would fail by that offset. The pin is " +
      "`process.env.TZ` at the top of `frontend/jest.config.js`; if jest has " +
      "changed when it builds the test realm, that assignment no longer lands " +
      "early enough. Fall back to pinning the zone outside the process — run " +
      "jest as `TZ=UTC npx jest`, and set it in the `test:ci` script too.",
  );
}
