"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * CAL-P026 — the native/web calibration SURFACE parity gate (exit exam item 5).
 *
 * ## What this gates, and why it is not already gated
 *
 * `populationVersion.contract.test.js` (L2-232) already pins one thing across
 * the language boundary: the set of population versions each client claims it
 * can label. That gate exists because a version disagreement took the public
 * page dark for ninety minutes and then took the iOS app dark for the rest of
 * the day.
 *
 * It does NOT gate the figures. Web publishes its headline numbers as
 * machine-readable attributes — `data-population-version`, `data-cache-status`,
 * `data-contract-state`, `data-generated-at`, `data-cohort-n`, `data-full-n`,
 * the partition counts — and `calibrationAuditHooks.test.tsx` fails CI when one
 * is dropped. Native published NOTHING: before CAL-P026 the whole calibration
 * surface carried zero `accessibilityIdentifier`s.
 *
 * So the exam's item 5 — "native and web showing the same population version,
 * the same generated-at, and the same headline figures" — was answerable only by
 * a human comparing two screenshots. That is a check that happens once. Web's
 * own source says as much, above its population-count hook: *"a native surface
 * reading the other one diverges silently. Both are published here as data so
 * the parity check reads numbers, not text."*
 *
 * ## Why the gate lives here and not in jest
 *
 * Same reason as L2-232's: it reads a Swift file. jest runs in the frontend
 * package and asserting on iOS sources from there is a layering accident. These
 * `node --test` contract fixtures run FIRST in the browser-audit workflow,
 * before any install, precisely so cross-cutting invariants like this one cannot
 * be skipped by a dependency failure.
 *
 * ## What this gate deliberately does NOT do
 *
 * It does not compare rendered numbers between the two surfaces — it cannot; one
 * of them is Swift. The numbers are pinned on each side against the SAME frozen
 * production payload (`CalibrationParityTests.swift` natively,
 * `calibrationMatchedBuckets.test.ts` and friends on web), and what this file
 * guarantees is the part those two cannot: that both sides are still talking
 * about the same payload, under the same names.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const NATIVE_VIEW = path.join(
  REPO_ROOT, "ios", "Bain Luck", "Bain Luck", "Views", "CalibrationView.swift",
);
const NATIVE_VIEWMODEL = path.join(
  REPO_ROOT, "ios", "Bain Luck", "Bain Luck", "ViewModels", "CalibrationViewModel.swift",
);
const NATIVE_FIXTURE = path.join(
  REPO_ROOT, "ios", "Bain Luck", "BainLuckTests", "CalibrationProdFixture.swift",
);
const WEB_PAGE = path.join(REPO_ROOT, "frontend", "app", "calibration", "page.tsx");

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    // A missing file must be LOUD — the L2-232 rule. A guard that silently
    // skips is decoration: the run stays green and nobody learns it stopped
    // running.
    assert.fail(
      `CAL-P026 surface-parity gate could not read ${path.relative(REPO_ROOT, file)}: ` +
        `${err.message}. If the file moved, update this fixture — do not delete the check.`,
    );
  }
}

/** The hook names the native surface declares, by constant name. */
function nativeHooks(source) {
  const hooks = {};
  for (const m of source.matchAll(
    /static let (\w+Hook)\s*=\s*"([^"]+)"/g,
  )) {
    hooks[m[1]] = m[2];
  }
  return hooks;
}

/** Every `data-testid` literal the web calibration page declares. */
function webTestIds(source) {
  const ids = new Set();
  for (const m of source.matchAll(/data-testid=["{]?["']([^"']+)["']/g)) ids.add(m[1]);
  for (const m of source.matchAll(/testId=["']([^"']+)["']/g)) ids.add(m[1]);
  return ids;
}

/**
 * The population version / generated-at the FROZEN native fixture records.
 *
 * Read from the declared constants rather than from the embedded JSON blob, so
 * a fixture regenerated without updating its own summary constants fails here
 * instead of quietly disagreeing with the tests that read them.
 */
function nativeFixtureFacts(source) {
  const version = source.match(
    /static let publishedPopulationVersion\s*=\s*"([^"]+)"/,
  );
  const cache = source.match(/static let servedCacheStatus\s*=\s*"([^"]+)"/);
  assert.ok(version, "CalibrationProdFixture must declare publishedPopulationVersion");
  assert.ok(cache, "CalibrationProdFixture must declare servedCacheStatus");

  const json = source.match(/static let json = """([\s\S]*?)"""/);
  assert.ok(json, "CalibrationProdFixture must embed its payload as `static let json`");
  let payload;
  try {
    payload = JSON.parse(json[1]);
  } catch (err) {
    assert.fail(`the native fixture's embedded payload is not valid JSON: ${err.message}`);
  }
  return { version: version[1], cacheStatus: cache[1], payload };
}

describe("CAL-P026 — native/web calibration surface parity", () => {
  it("native declares a hook for every figure web publishes as data", () => {
    const hooks = nativeHooks(read(NATIVE_VIEW));
    const ids = webTestIds(read(WEB_PAGE));

    // The six the exam's side-by-side actually turns on. Deliberately a
    // hard-coded list and not "whatever native happens to declare": a gate
    // derived entirely from one side cannot notice that side dropping one.
    const required = [
      "surfaceHook",
      "generatedAtHook",
      "outcomesHook",
      "eceHook",
      "brierHook",
      "marketsHook",
    ];
    for (const name of required) {
      assert.ok(
        hooks[name],
        `CalibrationView.swift must declare \`static let ${name}\`. It is how the ` +
          "native surface is graded; without it exam item 5 goes back to being a " +
          "screenshot somebody eyeballs once.",
      );
    }

    // The names must MATCH web's, not merely exist. A native hook called
    // something else is still unusable for a side-by-side without a translation
    // table nobody maintains.
    for (const name of ["generatedAtHook", "outcomesHook", "eceHook", "brierHook"]) {
      assert.ok(
        ids.has(hooks[name]),
        `native hook ${name}="${hooks[name]}" has no matching data-testid/testId on ` +
          `frontend/app/calibration/page.tsx. Web's ids: ${[...ids].sort().join(", ")}`,
      );
    }
  });

  it("the native fixture records the same production response web's fixture does", () => {
    const facts = nativeFixtureFacts(read(NATIVE_FIXTURE));

    assert.equal(
      facts.payload.population_version, facts.version,
      "the fixture's summary constant disagrees with its own embedded payload",
    );
    assert.equal(
      facts.payload.cache.status, facts.cacheStatus,
      "the fixture's summary constant disagrees with its own embedded cache envelope",
    );

    // The partition the exam quotes for this payload (item 2), recomputed here
    // from the native fixture. It is the one arithmetic fact both surfaces must
    // agree on before any per-figure comparison means anything.
    const sum = (pred) =>
      facts.payload.buckets.filter(pred).reduce((a, b) => a + b.n, 0);
    const moved = sum((b) => b.price_moved === true);
    const unchanged = sum((b) => b.price_moved === false);
    const notApplicable = sum((b) => b.price_moved === null || b.price_moved === undefined);

    assert.equal(moved, 349310);
    assert.equal(unchanged, 263022);
    assert.equal(notApplicable, 40075);
    assert.equal(
      moved + unchanged + notApplicable, facts.payload.total_outcomes,
      "the activity partition must reconcile to the payload's own total_outcomes",
    );
  });

  it("native still publishes the parity descriptor the hooks read from", () => {
    const vm = read(NATIVE_VIEWMODEL);
    assert.match(
      vm, /struct Parity\b/,
      "CalibrationViewModel must expose the `Parity` descriptor. Both the surface's " +
        "accessibility hooks and CalibrationParityTests read it, so that one value is " +
        "the single source of truth rather than two derivations that can drift " +
        "(ruling 003).",
    );
    assert.match(vm, /var parity:\s*Parity\b/);

    // `reconciles` is the partition invariant web publishes as
    // `data-partition-reconciles`. Named explicitly because a descriptor that
    // carried the counts but not the invariant would let a broken partition
    // render as three plausible numbers.
    assert.match(vm, /var reconciles:\s*Bool/);
  });
});
