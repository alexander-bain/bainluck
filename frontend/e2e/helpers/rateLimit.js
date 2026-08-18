"use strict";

/**
 * #1908 M1 — a 429 the rail inflicted on ITSELF is "I could not check", never
 * "the product failed".
 *
 * THE MEASUREMENT THIS IS BUILT ON (cycle 82's census, run `32009921496`):
 * 52 × HTTP 429 from `api.bainluck.com` inside a 107-second consent pack, from
 * ONE runner IP, against a 60/min anonymous budget. It is not cumulative
 * exhaustion — the timeline falsifies that, because the LATER journeys are
 * clean. It is a rolling-window burst that lands exactly where a journey
 * multiplies page loads (`two_tabs` opens two tabs: 11 and 8 × 429;
 * `deferred_event` navigates: 6 and 6). No real user generates that traffic
 * shape, and every one of those paths is anonymous, so nothing in it is
 * evidence about the product.
 *
 * That single condition minted THIRTEEN open issues — #1658, #1662, #1663,
 * #1665, #1666, #1667, #1668, #1780, #1781, #1782, #1783, #1784, #1820 — because
 * the filer fingerprints on `reason_code : journey : url`, which is the right
 * grain for a product defect and the wrong grain for a systemic run condition:
 * one burst across 8 journeys × 2 projects × 2 reason codes mints up to 32
 * distinct fingerprints. The filer was working exactly as designed and producing
 * a backlog nobody could act on.
 *
 * WHY THIS IS A CLASSIFIER AND NOT A SUPPRESSION, which is the whole design:
 * `consent.two_tabs [desktop]` failed `content.main_region_nonblank` — the page
 * rendered BLANK under rate limiting — *alongside* its 12 × 429. That is #1909,
 * the one genuine product defect in all thirteen issues, and it was invisible
 * because it wore the same label as twelve pieces of rail noise. So this must
 * never mark a JOURNEY quiet. It marks the specific assertions whose failures
 * are entirely self-inflicted, and leaves every other assertion on that journey
 * grading exactly as before. Muting the journey would have buried the one bug
 * the census existed to find.
 *
 * Deliberately NOT an auth exemption for the rail: the consent claim is about
 * ANONYMOUS behaviour, so authenticating the runner would test a different
 * thing and quietly delete the coverage.
 */

/**
 * Hosts whose 429s are the rail's own traffic. First-party only — a 429 from a
 * third party is somebody else's budget and stays a real finding.
 */
const FIRST_PARTY_HOST_PATTERN = /(^|\.)bainluck\.com$/i;

/** HTTP status for "too many requests". The only status this module claims. */
const RATE_LIMITED_STATUS = 429;

function hostOf(url) {
  const text = String(url || "").trim();
  if (!text) return "";
  const match = /^[a-z][a-z0-9+.-]*:\/\/([^/?#]+)/i.exec(text);
  if (!match) return "";
  return String(match[1]).split("@").pop().split(":")[0].toLowerCase();
}

/** Is this host one of ours? */
function isFirstPartyHost(url) {
  const host = hostOf(url);
  return !!host && FIRST_PARTY_HOST_PATTERN.test(host);
}

/**
 * One failed request that is the rail throttling itself.
 *
 * Both conditions are required and neither is negotiable:
 *   - status is exactly 429 (a 500 under load is a real defect, and load is not
 *     an excuse for one), and
 *   - the host is first-party (a third party's 429 is a real integration
 *     finding about a budget we do not control).
 */
function isSelfInflictedRateLimit(failure) {
  if (!failure) return false;
  const status = Number(failure.status);
  if (status !== RATE_LIMITED_STATUS) return false;
  return isFirstPartyHost(failure.url);
}

/**
 * The console-channel ECHO of the same condition.
 *
 * Chromium logs a fetch failure for an aborted or throttled request, so one
 * rate-limit burst shows up on BOTH channels and the census counted the console
 * copies as a fourth mechanism until it checked the text: every one was
 * `Failed to fetch RSC payload for … TypeError: Failed to fetch`. #1666, #1682,
 * #1820 and #1782 are this echo, which is why picking them off individually
 * never worked — they have no independent cause to fix.
 *
 * GATED ON A 429 ACTUALLY HAVING BEEN OBSERVED in the same journey, and that
 * gate is the entire safety property. "Failed to fetch" is also what a genuinely
 * broken endpoint logs. Without the gate this would reclassify a real outage as
 * infrastructure — the exact cry-wolf inversion, muting instead of shouting.
 */
const ECHO_PATTERNS = [
  /failed to fetch rsc payload/i,
  /typeerror:\s*failed to fetch/i,
  /net::err_failed/i,
  /the server responded with a status of 429/i,
];

function isRateLimitEcho(text) {
  const value = String(text == null ? "" : text);
  if (!value) return false;
  return ECHO_PATTERNS.some((re) => re.test(value));
}

/**
 * Should `network.no_unexpected_failures` be classified INFRA for this journey?
 *
 * True only when there is at least one unexpected failure AND every one of them
 * is a self-inflicted 429. One genuine failure alongside the burst keeps the
 * whole assertion a product finding — the conservative direction, because a
 * missed product defect is unrecoverable and an extra filed issue is not.
 */
function networkFailuresAreSelfInflicted(unexpected) {
  const list = Array.isArray(unexpected) ? unexpected : [];
  if (list.length === 0) return false;
  return list.every(isSelfInflictedRateLimit);
}

/**
 * Should `console.no_errors` be classified INFRA for this journey?
 *
 * Requires the 429 to have been SEEN on the network channel in the same journey
 * (see `isRateLimitEcho`), and every unexpected console error to match the echo
 * shape.
 */
function consoleErrorsAreRateLimitEcho(unexpectedConsole, failedRequests) {
  const errors = Array.isArray(unexpectedConsole) ? unexpectedConsole : [];
  if (errors.length === 0) return false;
  const requests = Array.isArray(failedRequests) ? failedRequests : [];
  const sawRateLimit = requests.some(isSelfInflictedRateLimit);
  if (!sawRateLimit) return false;
  return errors.every(isRateLimitEcho);
}

/** Human-readable count for the assertion detail, so the number stays visible. */
function describeRateLimit(unexpected) {
  const list = Array.isArray(unexpected) ? unexpected : [];
  const n = list.filter(isSelfInflictedRateLimit).length;
  return (
    `${n} self-inflicted 429(s) on first-party hosts — the rail exceeded the ` +
    `60/min anonymous budget from one runner IP (#1908 M1). This is a runner ` +
    `condition, not a product defect: "could not check" is not "failed".`
  );
}

module.exports = {
  RATE_LIMITED_STATUS,
  consoleErrorsAreRateLimitEcho,
  describeRateLimit,
  isFirstPartyHost,
  isRateLimitEcho,
  isSelfInflictedRateLimit,
  networkFailuresAreSelfInflicted,
};
