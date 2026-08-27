"use strict";

/**
 * UX-P144 — the consent ledger must watch OUR OWN telemetry, not just other
 * people's.
 *
 * THE DEFECT, stated exactly. `TELEMETRY_HOSTS` / `TELEMETRY_PATHS` in
 * `e2e/fixtures/audit.ts` decide what the recorder is even capable of seeing,
 * and every entry was a third-party collector: googletagmanager,
 * google-analytics, analytics.google, and the two Vercel beacon paths. So
 * "telemetry" had quietly come to mean "somebody else's telemetry".
 *
 * `POST /api/feed/interactions` is ours. It records every card a reader scrolls
 * past, keyed to their session id, so the server can personalise their feed —
 * the same class of collection the banner asks about. The recorder never saw
 * it, so `NOTHING_ALLOWED` could never assert its absence, so `consent.decline`
 * and `consent.untouched` passed their telemetry ledger green while the page
 * was still POSTing the reader's scroll.
 *
 * HOW IT SURFACED INSTEAD, and why that was worse. The client sent one request
 * per card impression against an endpoint that accepts fifty, so an ordinary
 * scroll spent the 60/min anonymous budget on impression beacons. Those 429s
 * are cross-origin and a 429 the browser cannot read reaches the page as an
 * opaque CORS error. One client defect therefore arrived on the board as ~20
 * separate `console.no_errors` / `network.no_unexpected_failures` issues across
 * the `consent.*` journeys — a family of symptoms describing the wreckage,
 * where one assertion naming the destination would have said what happened.
 *
 * WHY A SOURCE ASSERTION. The recorder runs inside Playwright and cannot be
 * executed here — no browser, and `e2e/node_modules` is not installable in the
 * sandbox. What CAN be asserted is that the ledger has not gone blind again,
 * and that is the regression worth blocking: deleting one string from an array
 * restores the exact silence this cost a cycle to find, and nothing else in the
 * suite would notice. The runtime behaviour of the rule matcher these entries
 * feed is executed next door in `telemetryLedger.contract.test.js`; the client
 * gate and the batching contract are executed in
 * `__tests__/lib/discoverInteractionsConsent.test.ts`.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const AUDIT = path.join(__dirname, "..", "fixtures", "audit.ts");
const SPEC = path.join(__dirname, "..", "specs", "consent.spec.ts");
const CLIENT = path.join(__dirname, "..", "..", "lib", "discoverInteractions.ts");

/** The first-party rail this whole file exists to keep in view. */
const RAIL = "/api/feed/interactions";

// A path typo must not read as a clean pass (gotcha #54's cousin) — every
// assertion below is worthless if it is pointed at nothing.
test("all three files are where this test thinks they are", () => {
  for (const p of [AUDIT, SPEC, CLIENT]) {
    assert.ok(fs.existsSync(p), `not found at ${p}`);
  }
});

const auditSrc = fs.readFileSync(AUDIT, "utf8");
const specSrc = fs.readFileSync(SPEC, "utf8");
const clientSrc = fs.readFileSync(CLIENT, "utf8");

test("the recorder can SEE the first-party rail", () => {
  const paths = auditSrc.match(/const TELEMETRY_PATHS = \[([\s\S]*?)\]/);
  assert.ok(paths, "TELEMETRY_PATHS not found in audit.ts");
  assert.ok(
    paths[1].includes(RAIL),
    `TELEMETRY_PATHS must include ${RAIL}. Without it the recorder never ` +
      "observes our own behavioural telemetry, and every consent journey's " +
      "absence claim is a claim about third parties only.",
  );
});

test("the denial ledger ASSERTS the first-party rail is absent", () => {
  const nothing = specSrc.match(/const NOTHING_ALLOWED[\s\S]*?\n};/);
  assert.ok(nothing, "NOTHING_ALLOWED not found in consent.spec.ts");
  assert.match(
    nothing[0],
    new RegExp(`pathPrefix: "${RAIL}"[^}]*expect: "absent"`),
    `NOTHING_ALLOWED must assert ${RAIL} is ABSENT. A denial that only ` +
      "silences other people's telemetry is not the denial the banner offered.",
  );
});

test("every denial journey uses that ledger — none opted out", () => {
  const journeyIds = specSrc.match(/journeyId: "[a-z_.]+"/g) || [];
  const denials = specSrc.match(/telemetryExpectation: NOTHING_ALLOWED/g) || [];
  // The pack is one grant journey plus the denials. If a journey ever hands
  // over its own inline expectation, this count drops and the new object has
  // to be reviewed rather than silently trusted.
  assert.ok(journeyIds.length >= 11, `expected the full pack, found ${journeyIds.length}`);
  assert.equal(
    denials.length,
    journeyIds.length - 1,
    "every journey but consent.grant must carry NOTHING_ALLOWED — an inline " +
      "expectation is how one journey quietly stops asserting what the rest do.",
  );
});

test("the grant journey ALLOWLISTS the rail rather than leaving it unlisted", () => {
  // The ledger is exhaustive by default, so an unlisted destination reds the
  // journey under `no_unlisted_destinations` — the same failure with a name
  // that points at the wrong thing.
  assert.match(
    specSrc,
    new RegExp(`id: "discover_interactions_allowed_on_grant"[\\s\\S]{0,200}pathPrefix: "${RAIL}"`),
    "consent.grant must allowlist the rail explicitly; on a grant it firing " +
      "is the reader's choice working, not a finding.",
  );
});

test("the client reads the consent authority before it sends", () => {
  assert.match(
    clientSrc,
    /getTelemetryConsent/,
    "discoverInteractions.ts must consult the telemetry consent authority. " +
      "It is the only rail on Discover that ever shipped without one.",
  );
  assert.match(
    clientSrc,
    /mayCaptureDiscoverInteraction\(getTelemetryConsent\(\)\)/,
    "the gate must be read at FLUSH time, not only at enqueue time — a reader " +
      "can revoke while a batch is still queued (consent.grant_then_revoke, " +
      "consent.deferred_event), and a queued event must not land after a revoke.",
  );
});

test("the client batches to the server's own documented cap", () => {
  // Mirrors `DiscoverInteractionBatch.interactions` (max_length=50) in
  // backend/app/routes/feed.py. One request per card impression is what spent
  // the reader's 60/min budget and produced the CORS family.
  assert.match(
    clientSrc,
    /const MAX_BATCH = 50;/,
    "MAX_BATCH must mirror the endpoint's max_length=50 — the cap is a " +
      "contract with the server, not a tuning knob.",
  );
});
