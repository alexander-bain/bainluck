"use strict";

/**
 * L2-241 — bounded abort fields for a failed request (#1525 Shape A).
 *
 * The bare `{ url, method, status, failure }` failed-request record cannot tell
 * a navigation TEARDOWN (a request aborted in the first few ms, before its
 * response could ever have mattered) from a client-side TIMEOUT (aborted only
 * after a long wait). #1525 Shape A — the landing feed request aborts twice per
 * load, and an aborted feed is invisible to the backend's own metrics — needs
 * exactly that distinction to be triaged.
 *
 * These fields carry it and nothing more: no bodies, no headers, no unbounded
 * timing object. The shaping is a pure function (only the shared redaction
 * boundary is imported) so it is unit-testable without a browser, the same way
 * `journey.js` is — the collector in `fixtures/audit.ts` calls it, a contract
 * fixture drives it, and both take the same code path.
 */

const { redactUrl } = require("./redaction");

/**
 * net::ERR_ABORTED and its kin. A non-abort failure (a real connection error, a
 * name-resolution failure) gets NO abort packet — this is deliberately narrow so
 * an abort field only appears on an actual abort.
 */
const ABORT_RE = /ERR_ABORTED|(?:^|[^a-z])aborted(?:[^a-z]|$)/i;

/** @param {unknown} failureText */
function isAbort(failureText) {
  return typeof failureText === "string" && ABORT_RE.test(failureText);
}

/**
 * Bound a raw performance number into one small, redaction-safe integer field.
 * Playwright reports -1 for timing phases a failed request never reached, so
 * anything negative or non-finite becomes null rather than a misleading 0.
 *
 * @param {unknown} value
 * @returns {number|null}
 */
function boundedMs(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  return Math.round(value);
}

/**
 * Shape the bounded abort packet for a failed request, or null when the failure
 * is not an abort. `timing` is Playwright's `request.timing()` — phase offsets
 * (ms) relative to the request start, with -1 for phases that never fired. The
 * only timing fact we keep is how far the request got before it aborted: the
 * largest non-negative phase offset. A teardown shows a tiny (or null) elapsed
 * with mostly -1 phases; a timeout shows a large one.
 *
 * @param {{ failureText?: unknown, resourceType?: unknown, timing?: any, frameUrl?: unknown, isFeed?: unknown }} input
 * @returns {null | { aborted: true, resource_type: string|null, elapsed_before_abort_ms: number|null, is_feed_request: boolean, frame_url: string|null }}
 */
function describeAbort(input) {
  const o = input || {};
  if (!isAbort(o.failureText)) return null;
  const timing = o.timing || {};
  const offsets = [
    timing.requestStart,
    timing.responseStart,
    timing.responseEnd,
    timing.connectStart,
    timing.connectEnd,
    timing.domainLookupStart,
    timing.domainLookupEnd,
    timing.secureConnectionStart,
  ]
    .map(boundedMs)
    .filter((v) => v !== null);
  const elapsedBeforeAbortMs = offsets.length ? Math.max(...offsets) : null;
  return {
    aborted: true,
    resource_type:
      typeof o.resourceType === "string" && o.resourceType ? o.resourceType.slice(0, 40) : null,
    elapsed_before_abort_ms: elapsedBeforeAbortMs,
    is_feed_request: Boolean(o.isFeed),
    // The frame URL loses its query values like every other URL in the packet.
    frame_url: o.frameUrl ? redactUrl(o.frameUrl) : null,
  };
}

module.exports = { isAbort, boundedMs, describeAbort, ABORT_RE };
