"use strict";

/**
 * L2-233 — no unit test may touch the network.
 *
 * `jest.config.js` sets `testEnvironment: "node"`, which means every test file
 * gets a real Node global scope: a real `fetch`, a real `http`/`https`. Nothing
 * in the suite currently uses them — all 21 `fetch` references across the 19
 * files that mention it are `global.fetch = jest.fn(...)` mock assignments, and
 * there is not one bare `fetch(` call. That is a property worth freezing rather
 * than a coincidence worth relying on.
 *
 * WHY IT MATTERS NOW. Before this queue the suite ran only on a laptop, where a
 * test that quietly reached api.bainluck.com would pass and nobody would care.
 * From now on it decides whether a commit deploys, so a live call would make
 * the deploy gate depend on production being up — a green build would mean "the
 * API answered", and a red one could be someone else's outage. A gate that can
 * be reddened by a third party is not a gate.
 *
 * WHAT IS ENFORCED. `fetch`, `XMLHttpRequest`, and `http`/`https` `request`/`get`
 * throw on call. A test that legitimately needs one keeps doing exactly what the
 * 19 existing files already do — assign its own mock, which replaces the thrower.
 *
 * WHAT IS NOT. A raw `net.Socket` still opens a socket. Closing that too means
 * patching the transport every one of these paths is built on, which breaks
 * jest's own worker IPC. No test in the suite does it; the census above is the
 * honest boundary of this guard, not an oversight.
 *
 * `setupFiles` (not `setupFilesAfterEach`) so the patch is in place before the
 * module under test is even imported — an import-time request is exactly the
 * kind that would otherwise slip through.
 */

const BLOCKED = (what) =>
  new Error(
    `${what} was called in a unit test. Network access is blocked here (L2-233): ` +
      "the frontend suite gates deploys, so a live call would make the gate depend on " +
      "production being reachable. Assign a mock — `global.fetch = jest.fn(...)` — the " +
      "way the existing suites do.",
  );

globalThis.fetch = function blockedFetch() {
  throw BLOCKED("fetch()");
};

globalThis.XMLHttpRequest = function BlockedXMLHttpRequest() {
  throw BLOCKED("new XMLHttpRequest()");
};

for (const mod of ["http", "https"]) {
  // eslint-disable-next-line @typescript-eslint/no-var-requires, global-require
  const lib = require(`node:${mod}`);
  for (const method of ["request", "get"]) {
    lib[method] = function blockedRequest() {
      throw BLOCKED(`${mod}.${method}()`);
    };
  }
}
