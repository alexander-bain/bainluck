"use strict";

/**
 * #1909 / #1663 — the consent pack may not grade a page it never let settle.
 *
 * THE DEFECT, stated exactly. Every consent journey ended with
 *
 *     mainRegionNonBlank: await mainNonBlank(page)
 *
 * where `mainNonBlank` was one instantaneous `innerText` read against a private
 * `> 40`. `consent.two_tabs` reloads tab A when it adopts the denial, so that
 * read fired while the feed was in flight and reported a LOADING PLACEHOLDER as
 * a blank page. #1663 is that finding, it is the only user-visible one in all
 * thirteen consent issues, and it kept arriving with a screenshot of a skeleton
 * attached — which is why cycle 83 could fix #1909's copy and its 429 retry and
 * still not close it. The remaining criterion was always the rail's.
 *
 * WHY A SOURCE ASSERTION. The polling lives in a Playwright spec and cannot be
 * executed here — no browser, and `e2e/node_modules` is not installable in the
 * sandbox. What CAN be asserted without either is that the conversion is still
 * in place, and that is the regression worth blocking: the legacy field still
 * exists in `FinishInput` and still works, so a future edit can revert to it in
 * one line and nothing would notice. The behaviour of the classifier those
 * measurements are handed to is executed, next door, in
 * `contentState.contract.test.js`.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SPEC = path.join(__dirname, "..", "specs", "consent.spec.ts");

// A path typo must not read as a clean pass (gotcha #54's cousin) — this whole
// file is worthless if it is pointed at nothing.
test("the consent pack is where this test thinks it is", () => {
  assert.ok(fs.existsSync(SPEC), `consent pack not found at ${SPEC}`);
});

const src = fs.readFileSync(SPEC, "utf8");
const journeyIds = src.match(/journeyId: "[a-z_.]+"/g) || [];

test("every journey hands over MEASUREMENTS, not a pre-computed verdict", () => {
  assert.ok(journeyIds.length >= 11, `expected the full pack, found ${journeyIds.length}`);
  const handovers = src.match(/mainRegion: await settledMainRegion\(page\)/g) || [];
  assert.equal(
    handovers.length,
    journeyIds.length,
    "every journey must hand the evaluator raw measurements — a journey left on " +
      "the legacy boolean is a second grader for one question (ruling 021)"
  );
});

test("the legacy pre-computed boolean is GONE from this pack", () => {
  // Not "mostly gone". The field is still supported for surfaces not yet
  // converted, so one line reintroduces the defect.
  assert.ok(
    !src.includes("mainRegionNonBlank"),
    "consent.spec.ts must not use the legacy `mainRegionNonBlank` field"
  );
  assert.ok(
    !/const text = await readContentRegionText\(page\);\s*return text\.trim\(\)\.length > 40;/.test(src),
    "the instantaneous `> 40` read is the defect itself and must not return"
  );
});

test("the region is polled until it stops LOADING, and the wait is bounded", () => {
  assert.ok(
    src.includes('classifyMainRegion(observation).state === "loading"'),
    "the settle loop must key on the classifier's own loading state, not on a " +
      "second opinion about what loading looks like"
  );
  assert.ok(/SETTLE_TIMEOUT_MS\s*=\s*[\d_]+/.test(src), "the settle wait must be bounded");
  // An unbounded wait would hang the pack; a wait that THROWS on timeout would
  // convert a stuck page into an infra error and hide it. Returning the last
  // observation is what makes "the page never resolved" a reportable finding.
  assert.ok(
    /return observation;\s*}/.test(src),
    "on timeout the last observation must be RETURNED so a stuck page is graded, not swallowed"
  );
  assert.ok(
    !/throw new Error\([^)]*settle/i.test(src),
    "a region that never settles is a finding to report, not an exception to raise"
  );
});

test("the skeleton selector is the one both / and /discover render", () => {
  // L2-239's lesson: `/` and `/discover` are the same component, but the route
  // segment gives `/discover` a second `discover-skeleton` marker. Measuring the
  // marker's own text is what makes the two grade identically, so the pack must
  // use that selector rather than inventing a narrower one.
  assert.ok(src.includes('[data-testid="discover-skeleton"]'));
});


// ---------------------------------------------------------------------------
// UX-P095 — the pack must not be all-or-nothing, and every navigation must be
// attributed. Source assertions, for the same reason the file's header gives:
// the spec needs a browser, the property does not.
// ---------------------------------------------------------------------------

test("the consent pack does not run in SERIAL mode", () => {
  // Measured on run 32177161167: `consent.grant` failed and the eight journeys
  // after it, on BOTH projects, ended "skipped" -> `infra_error`. Sixteen of
  // twenty-two journeys never ran because one did not pass. Sequencing was the
  // requirement; serial mode also buys fate-sharing, and Playwright already runs
  // one file's tests in order in one worker unless `fullyParallel` is set.
  const src = fs.readFileSync(SPEC, "utf8");
  assert.ok(
    !/describe\.configure\(\s*\{[^}]*mode:\s*["']serial["']/.test(src),
    "serial mode makes one red journey skip the rest of the pack — the M1 " +
      "evidence that retires seven issues can then never be gathered"
  );
  assert.ok(
    /RATE_LIMIT_COOLDOWN_MS/.test(src) && /afterEach/.test(src),
    "the pacing that serial mode was standing in for must still be here"
  );
});

test("every navigation in the pack is an ATTRIBUTED harness action", () => {
  // Ruling 021's carve-out, condition 1: an abort is only excusable when the
  // action that caused it can be named. A bare `page.goto` produces an
  // unattributed abort, which is graded — the safe direction, but a silent
  // one, so it is asserted rather than left to review.
  const src = fs.readFileSync(SPEC, "utf8");
  const bare = [...src.matchAll(/await\s+(?:page|tabB|opened)\.goto\(/g)];
  const attributed = [...src.matchAll(/duringInstrumentAction\(/g)];
  assert.ok(attributed.length > 0, "the pack must attribute its navigations");
  // The one legitimate bare `goto` is inside a `duringInstrumentAction` span
  // (tab B, in the two-tab journey), so at most one may appear.
  assert.ok(
    bare.length <= 1,
    `${bare.length} unattributed navigation(s) — route them through go() or ` +
      "duringInstrumentAction, or their aborts stay graded"
  );
  assert.ok(
    /INSTRUMENT_NAVIGATION_ABORT/.test(src),
    "a pack that attributes its aborts must also declare the allowance, or the " +
      "attribution buys nothing"
  );
});
