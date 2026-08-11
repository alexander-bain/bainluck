"use strict";

/**
 * UX-P058 (#1610/#1612/#1614) — the ONE home for "is this console message a
 * statement about a REQUEST?", so the console channel and the network channel
 * cannot disagree about who grades sub-resource failures.
 *
 * THE DRIFT THIS CLOSES. `fixtures/audit.ts` states the rail's scoping rule where
 * it builds the response ledger: first-party 4xx/5xx are our defect, "third-party
 * noise is not graded". The console channel contradicted that rule, because
 * Chromium emits its generic resource-load error for EVERY failed sub-resource,
 * first- or third-party alike, and `msg.text()` carries NO URL to discriminate on.
 * So an ESPN logo or a Pexels image 404 red-ed a journey through the console
 * channel that the network channel deliberately ignored — two graders, one event
 * stream, two scopes. Tenth instance of the #1620 shape on this lane.
 *
 * It is also why #1610/#1612/#1614 sat open: the filed issue reads
 * `1 console error(s): Failed to load resource: ... 404` and no reader can learn
 * WHAT 404'd. A grader that reports an error it cannot attribute cannot be acted
 * on, so nobody acted.
 *
 * WHY A HELPER AND NOT A REGEX IN THE FIXTURE. While the decision lived inside
 * `audit.ts` the only way to exercise it was to dispatch the rail at production
 * and read a manifest — the same trap UX-P053 pulled `settledSpecimen.js` out of.
 * A rail whose only test is "dispatch it and see" cannot tell a broken predicate
 * from a quiet evening.
 */

/**
 * Chromium's generic sub-resource failure message, in both of its forms:
 *
 *   "Failed to load resource: the server responded with a status of 404 ()"
 *   "Failed to load resource: net::ERR_CONNECTION_REFUSED"
 *
 * Anchored at the start so a PAGE error that merely quotes the phrase — an app
 * throwing `new Error("... failed to load resource ...")` — is NOT swallowed. The
 * anchor is the whole reason this is a constant and not an `includes()`.
 */
const RESOURCE_LOAD_CONSOLE_RE = /^Failed to load resource\b/i;

/**
 * True when `text` is the browser's own resource-load complaint.
 *
 * Deliberately NOT status-aware: the transport form carries no status, and both
 * forms are already recorded — with a URL, and scoped to first-party — by the
 * `response` and `requestfailed` handlers in `fixtures/audit.ts`.
 */
function isResourceLoadConsoleError(text) {
  if (typeof text !== "string") return false;
  return RESOURCE_LOAD_CONSOLE_RE.test(text);
}

/**
 * Split captured console-error text into the channel that grades it.
 *
 * `scriptErrors` keep failing `console.no_errors` — that assertion goes back to
 * meaning what its name says. `resourceErrors` are recorded as evidence and graded
 * by `network.no_unexpected_failures`, which is the only ledger that can name a URL.
 *
 * COVERAGE IS PRESERVED, and that is the load-bearing claim rather than the noise
 * removal: a first-party 4xx/5xx still reds via the response handler, and a request
 * that dies before any response still reds via `requestfailed`. Nothing first-party
 * stops being graded; only the unattributable duplicate goes away.
 */
function partitionConsoleErrors(texts) {
  const scriptErrors = [];
  const resourceErrors = [];
  for (const text of Array.isArray(texts) ? texts : []) {
    if (isResourceLoadConsoleError(text)) resourceErrors.push(text);
    else scriptErrors.push(text);
  }
  return { scriptErrors, resourceErrors };
}

module.exports = {
  RESOURCE_LOAD_CONSOLE_RE,
  isResourceLoadConsoleError,
  partitionConsoleErrors,
};
