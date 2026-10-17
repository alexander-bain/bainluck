"use strict";

/**
 * #3961 — a storage fault installed on a Storage INSTANCE is a dead fault.
 *
 * THE DEFECT, stated exactly. `consent.storage_failure` simulated a refusing
 * store with
 *
 *     Object.defineProperty(window.localStorage, "setItem", { value: swallow })
 *
 * (This file carries that text on purpose and excludes itself from the walk.)
 * Storage is a WebIDL object with a named property setter, so that call does not
 * shadow the method — it STORES AN ITEM named "setItem" whose value is the
 * function's source, and every real `localStorage.setItem(...)` still reaches the
 * prototype. Plain assignment (`localStorage.setItem = fn`) takes the same named
 * setter. Measured in Chromium (Playwright 1.48.2): with the old installation the
 * app's verified writer returned `'saved'` and "none" was persisted. The journey
 * went red every day from at least 9/2 on `expect(stored).toBeNull()`, which read
 * as a product privacy defect; the product was right and the fault never ran.
 *
 * WHY A SOURCE ASSERTION. No browser runs here. The behavioural proof lives in
 * the spec itself — a positive control writes the consent key through the app's
 * own write path and requires the readback to be null before the journey is
 * graded. What this file blocks is the CLASS: any e2e file that installs a
 * Storage fault as an own property, which syntax alone makes look correct.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const E2E = path.join(__dirname, "..");
const SPEC = path.join(E2E, "specs", "consent.spec.ts");

/** An own-property shim on a Storage instance: defineProperty(ies) or assignment. */
const INSTANCE_SHIM = new RegExp(
  [
    String.raw`definePropert(?:y|ies)\(\s*(?:window\.|globalThis\.|self\.)?(?:localStorage|sessionStorage)\s*,`,
    String.raw`(?:window\.|globalThis\.|self\.)?(?:localStorage|sessionStorage)\.(?:setItem|getItem|removeItem|clear|key)\s*=(?!=)`,
  ].join("|"),
);

function e2eSources(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) e2eSources(full, out);
    else if (/\.(?:[cm]?js|ts)$/.test(entry.name) && full !== __filename) out.push(full);
  }
  return out;
}

test("the guard bites on the installation that hid #3961 (not vacuous)", () => {
  const original = `
    const real = window.localStorage.setItem.bind(window.localStorage);
    Object.defineProperty(window.localStorage, "setItem", {
      configurable: true,`;
  assert.match(original, INSTANCE_SHIM);
  assert.match("localStorage.setItem = () => {};", INSTANCE_SHIM);
  // …and passes the prototype-level form the spec now uses.
  assert.doesNotMatch(
    'const proto = Object.getPrototypeOf(window.localStorage);\nObject.defineProperty(proto, "setItem", {',
    INSTANCE_SHIM,
  );
  assert.doesNotMatch('if (localStorage.getItem(k) === "none")', INSTANCE_SHIM);
});

test("no e2e file installs a Storage fault as an own property of the instance", () => {
  const files = e2eSources(E2E);
  assert.ok(files.includes(SPEC), `walk did not reach ${SPEC} — a path typo must not pass`);
  const offenders = files
    .filter((f) => INSTANCE_SHIM.test(fs.readFileSync(f, "utf8")))
    .map((f) => path.relative(E2E, f));
  assert.deepEqual(
    offenders,
    [],
    "a Storage instance's named setter swallows this — patch Storage.prototype instead (#3961)",
  );
});

test("consent.storage_failure proves its fault before grading, and keeps its verdict", () => {
  const src = fs.readFileSync(SPEC, "utf8");
  const start = src.indexOf('test("consent.storage_failure');
  assert.ok(start >= 0, "consent.storage_failure journey not found");
  const end = src.indexOf("\ntest(", start + 1);
  const body = src.slice(start, end < 0 ? undefined : end);

  assert.match(body, /Object\.getPrototypeOf\(window\.localStorage\)/, "fault must be prototype-level");
  const control = body.indexOf("storage fault is not installed");
  const click = body.indexOf("name: TURN_OFF");
  assert.ok(control >= 0, "the positive control on the real write path is gone");
  assert.ok(control < click, "the positive control must run before the choice it qualifies");
  // The substantive assertions #3961 must not weaken.
  assert.match(body, /expect\(await storedConsent\(page\)\)\.toBeNull\(\)/);
  assert.match(body, /toContain\("would not save"\)/);
  assert.match(body, /telemetryExpectation: NOTHING_ALLOWED/);
});
