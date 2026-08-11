"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * CAL-P043 (#1643, codex C236) — the native/web calibration SURFACE parity gate.
 *
 * ## What this file used to be, and why it was replaced
 *
 * It was a VACUOUS gate. Its central test — "the native fixture records the same
 * production response web's fixture does" — opened the native fixture and
 * compared it against constants declared beside it in the same file. It never
 * opened web's fixture, never ran web code, and never read a web-computed value.
 * Both clients could disagree completely while it stayed green, and it was cited
 * as coverage for calibration exit-exam item 5.
 *
 * That was not a missing assertion. It was structural: the one production
 * payload existed as TWO hand-maintained copies in two languages, and there was
 * no artifact either client could be held against. A test given one copy can
 * only compare it to itself.
 *
 * ## What replaces it
 *
 * `fixtures/calibration/` now holds the payload once, plus the parity record
 * both surfaces must reproduce from it — for BOTH cohort-toggle states. Each
 * client asserts in its own runner that it reproduces the record
 * (`calibrationSurfaceParity.test.ts` in jest, `CalibrationParityTests.swift` in
 * XCTest), so neither can drift without going red, and re-baselining the record
 * to match a drifted client turns the other client red.
 *
 * This file is the third leg. It cannot call Swift and it cannot import
 * TypeScript, so it does the two things it uniquely can:
 *
 *   1. **Recomputes the record from the payload with its own arithmetic.** Plain
 *      JS, no imports from either client. If the record and both clients shared
 *      one wrong idea of what ECE means, this still fails.
 *   2. **Asserts both clients are still BOUND to the record** — that the checks
 *      exist, name it, and have not been quietly unhooked. A gate that can be
 *      deleted without anything turning red is the failure mode this whole card
 *      is about.
 *
 * ## Why the gate lives here and not in jest
 *
 * Same reason as L2-232's: it reads a Swift file. jest runs in the frontend
 * package and asserting on iOS sources from there is a layering accident. These
 * `node --test` contract fixtures run FIRST in the browser-audit workflow,
 * before any install, precisely so cross-cutting invariants like this one cannot
 * be skipped by a dependency failure.
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
const NATIVE_PARITY_TESTS = path.join(
  REPO_ROOT, "ios", "Bain Luck", "BainLuckTests", "CalibrationParityTests.swift",
);
const WEB_PAGE = path.join(REPO_ROOT, "frontend", "app", "calibration", "page.tsx");
const WEB_PARITY_LIB = path.join(REPO_ROOT, "frontend", "lib", "calibrationParity.ts");
const WEB_CONTRACT_LIB = path.join(REPO_ROOT, "frontend", "lib", "calibrationContract.ts");
const WEB_PARITY_TEST = path.join(
  REPO_ROOT, "frontend", "__tests__", "lib", "calibrationSurfaceParity.test.ts",
);
const WEB_FIXTURE = path.join(
  REPO_ROOT, "frontend", "__tests__", "lib", "calibrationProdFixture.ts",
);

const SHARED_DIR = path.join(REPO_ROOT, "fixtures", "calibration");
const SHARED_PAYLOAD = path.join(SHARED_DIR, "prod-2026-08-02.json");
const SHARED_RECORD = path.join(SHARED_DIR, "parity-record-2026-08-02.json");

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    // A missing file must be LOUD — the L2-232 rule. A guard that silently
    // skips is decoration: the run stays green and nobody learns it stopped
    // running.
    assert.fail(
      `calibration surface-parity gate could not read ${path.relative(REPO_ROOT, file)}: ` +
        `${err.message}. If the file moved, update this fixture — do not delete the check.`,
    );
  }
}

const PAYLOAD = JSON.parse(read(SHARED_PAYLOAD));
const RECORD = JSON.parse(read(SHARED_RECORD));

// ---------------------------------------------------------------------------
// This gate's OWN arithmetic. Deliberately written out rather than imported:
// the whole value of a third implementation is that it shares no code with the
// two it is checking.
// ---------------------------------------------------------------------------

/** Bin the rows by `bucket_idx` and return each bin's n and signed error (pp). */
function binErrors(rows) {
  const bins = new Map();
  for (const b of rows) {
    const cur = bins.get(b.bucket_idx) || { n: 0, winners: 0, sumProb: 0 };
    cur.n += b.n;
    cur.winners += b.winners;
    cur.sumProb += b.sum_prob;
    bins.set(b.bucket_idx, cur);
  }
  return [...bins.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([, v]) => ({
      n: v.n,
      // Both clients round each bucket's error to one decimal BEFORE weighting.
      error: Math.round((v.winners / v.n - v.sumProb / v.n) * 1000) / 10,
    }));
}

const eceOf = (bins) => {
  const total = bins.reduce((s, b) => s + b.n, 0);
  return total ? bins.reduce((s, b) => s + (b.n / total) * Math.abs(b.error), 0) : 0;
};
const mceOf = (bins) =>
  bins.length ? bins.reduce((s, b) => s + Math.abs(b.error), 0) / bins.length : 0;

/** The cohort predicate, stated once here and mirrored by both clients. */
const keepFor = (includeNeverMoved) => (b) =>
  includeNeverMoved || b.price_moved !== false;

const TOLERANCE = 1e-6;
const near = (a, b, what) =>
  assert.ok(
    Math.abs(a - b) < TOLERANCE,
    `${what}: this gate computed ${a}, the record says ${b} (delta ${Math.abs(a - b)})`,
  );

/** Every `data-testid` literal the web calibration page declares. */
function webTestIds(source) {
  const ids = new Set();
  for (const m of source.matchAll(/data-testid=["{]?["']([^"']+)["']/g)) ids.add(m[1]);
  for (const m of source.matchAll(/testId=["']([^"']+)["']/g)) ids.add(m[1]);
  return ids;
}

/** The hook names the native surface declares, by constant name. */
function nativeHooks(source) {
  const hooks = {};
  for (const m of source.matchAll(/static let (\w+Hook)\s*=\s*"([^"]+)"/g)) {
    hooks[m[1]] = m[2];
  }
  return hooks;
}

describe("the shared fixture is shared — there is one payload, not two", () => {
  it("the native embed is byte-equal to the shared payload", () => {
    // Native still embeds the payload as a Swift string literal rather than
    // reading the JSON: an XCTest reading a `#filePath`-relative file is
    // host-filesystem-dependent, and trading a verifiable duplicate for an
    // unverifiable load path is a bad trade. So the duplicate is CHECKED rather
    // than hoped. If the iOS test target ever gains a resource bundle, delete
    // the embed and this test with it.
    const src = read(NATIVE_FIXTURE);
    const m = src.match(/static let json = """([\s\S]*?)"""/);
    assert.ok(m, "CalibrationProdFixture must embed its payload as `static let json`");

    let embedded;
    try {
      embedded = JSON.parse(m[1]);
    } catch (err) {
      assert.fail(`the native fixture's embedded payload is not valid JSON: ${err.message}`);
    }
    assert.deepEqual(
      embedded, PAYLOAD,
      "the Swift embed has drifted from fixtures/calibration/prod-2026-08-02.json. " +
        "The JSON is authoritative; regenerate the embed from it.",
    );
  });

  it("web holds no second copy of the rows", () => {
    // The old `calibrationProdFixture.ts` was 68 hand-transcribed object
    // literals. Two copies of one payload is the root cause this card is about,
    // so a re-inlined copy has to fail here rather than be noticed by a reader.
    const src = read(WEB_FIXTURE);
    assert.match(
      src, /prod-2026-08-02\.json/,
      "web's fixture must read the shared payload, not declare its own rows",
    );
    const inlined = [...src.matchAll(/bucket_idx:\s*\d+/g)].length;
    assert.equal(
      inlined, 0,
      `web's fixture declares ${inlined} inline bucket literals. It must read ` +
        "fixtures/calibration/prod-2026-08-02.json instead.",
    );
  });

  it("the record names the payload it was derived from", () => {
    assert.equal(RECORD.payload_fixture, "prod-2026-08-02.json");
    assert.ok(fs.existsSync(path.join(SHARED_DIR, RECORD.payload_fixture)));
  });
});

describe("the record survives an independent recomputation", () => {
  it("the surface counts are the payload's own", () => {
    const rows = PAYLOAD.buckets;
    const sum = (pred) => rows.filter(pred).reduce((a, b) => a + b.n, 0);
    const s = RECORD.surface;

    assert.equal(s.full_n, sum(() => true));
    assert.equal(s.moved_n, sum((b) => b.price_moved === true));
    assert.equal(s.unchanged_n, sum((b) => b.price_moved === false));
    assert.equal(s.not_applicable_n, sum((b) => b.price_moved === null));
    assert.equal(s.markets, PAYLOAD.total_markets);
    assert.equal(s.population_version, PAYLOAD.population_version);
    assert.equal(s.cache_status, PAYLOAD.cache.status);
    assert.equal(s.generated_at, PAYLOAD.cache.generated_at);

    // The partition invariant. Three cohorts that did not reconcile would still
    // render as three plausible numbers on both surfaces.
    assert.equal(s.moved_n + s.unchanged_n + s.not_applicable_n, s.full_n);
    assert.equal(s.full_n, PAYLOAD.total_outcomes);
    assert.equal(s.reconciles, true);
  });

  it("both cohorts' ECE, MCE and Brier recompute to the recorded values", () => {
    assert.equal(RECORD.cohorts.length, 2, "the record must carry both toggle states");

    for (const c of RECORD.cohorts) {
      const rows = PAYLOAD.buckets.filter(keepFor(c.include_never_moved));
      const bins = binErrors(rows);

      assert.equal(c.n, rows.reduce((a, b) => a + b.n, 0), `${c.key}: cohort n`);
      near(eceOf(bins), c.ece, `${c.key}: ECE`);
      near(mceOf(bins), c.mce, `${c.key}: MCE`);
      near(
        rows.reduce((a, b) => a + b.sum_sq_err, 0) / rows.reduce((a, b) => a + b.n, 0),
        c.brier, `${c.key}: Brier`,
      );
    }
  });

  it("the two cohort states are genuinely different figures", () => {
    // Without this, a surface that rendered the toggle but ignored it would
    // reproduce both records and pass. C236 asked for both states by name;
    // this is what makes asking for them worth anything.
    const [def, all] = RECORD.cohorts;
    assert.equal(def.include_never_moved, false);
    assert.equal(all.include_never_moved, true);
    assert.notEqual(def.n, all.n);
    assert.ok(
      Math.abs(def.ece - all.ece) > 0.01,
      `the two cohorts' ECEs are ${def.ece} and ${all.ece} — too close for the ` +
        "toggle to be observable in this record",
    );
    // The default cohort is moved + not-applicable, and must never be everything.
    assert.equal(def.n, RECORD.surface.moved_n + RECORD.surface.not_applicable_n);
    assert.notEqual(def.n, RECORD.surface.full_n);
    assert.equal(all.n, RECORD.surface.full_n);
  });
});

describe("both clients are bound to the record", () => {
  it("web's gate calls the production builder against it", () => {
    const src = read(WEB_PARITY_TEST);
    assert.match(src, /parity-record-2026-08-02\.json/,
      "web's parity test must load the shared record");
    assert.match(src, /buildCalibrationParity/,
      "web's parity test must call the PRODUCTION builder — asserting against a " +
        "constant is the defect this card exists to fix");
    // Both states, or the toggle is ungraded on web.
    assert.match(src, /RECORD\.cohorts/);
  });

  it("web's page renders and publishes from that same builder", () => {
    const page = read(WEB_PAGE);
    assert.match(page, /buildCalibrationParity/,
      "the page must build its parity record with the shared builder");
    assert.match(page, /data-parity=/,
      "the page must publish the parity record as data");
    // Ruling 003: the published value is the rendered value. A page that
    // computed the record separately from the figures it draws could publish a
    // number nobody can see.
    assert.match(page, /parityValue\(parity\)/);

    // C236's second P1: MCE existed only inside the ECE card's detail PROSE.
    assert.match(page, /data-ece=\{cohortECE\}/);
    assert.match(page, /data-mce=\{cohortMCE\}/);
  });

  it("the page's bucket math is importable, not private to the component", () => {
    // The reason the old gate could not read a web value: `aggregateBuckets` and
    // `brierScore` were unexported functions inside a "use client" page.
    const lib = read(WEB_PARITY_LIB);
    for (const fn of ["aggregateBuckets", "brierScore", "buildCalibrationParity", "parityValue"]) {
      assert.match(lib, new RegExp(`export function ${fn}\\b`), `${fn} must be exported`);
    }
    const page = read(WEB_PAGE);
    assert.doesNotMatch(
      page, /^function (aggregateBuckets|brierScore)\(/m,
      "the page must import this math, not redeclare it — two copies is how the " +
        "published record drifts from the rendered one",
    );
  });

  it("native's expectations ARE the record, value for value", () => {
    // This is the load-bearing half of the cross-language binding, and it is
    // why the record is worth having.
    //
    // Native's expectations are Swift literals rather than a file read — an
    // XCTest reading a `#filePath`-relative JSON is host-filesystem-dependent,
    // and a duplicate that is CHECKED beats a load path that is not. So the
    // check is here: parse the constants out of the Swift source and require
    // them to equal the record. A constant edited without the record fails
    // here; a record edited without the constant fails here too.
    const src = read(NATIVE_PARITY_TESTS);
    const consts = {};
    for (const m of src.matchAll(/static let (\w+) = ("?[\w.:+\-_]+"?)\s*$/gm)) {
      const raw = m[2];
      consts[m[1]] = raw.startsWith('"')
        ? raw.slice(1, -1)
        : Number(raw.replace(/_/g, ""));
    }

    const s = RECORD.surface;
    const [def, all] = RECORD.cohorts;
    const expected = {
      publishedPopulationVersion: s.population_version,
      publishedGeneratedAt: s.generated_at,
      publishedCacheStatus: s.cache_status,
      publishedContractState: s.contract_state,
      publishedMarkets: s.markets,
      publishedFullN: s.full_n,
      publishedMovedN: s.moved_n,
      publishedUnchangedN: s.unchanged_n,
      publishedNotApplicableN: s.not_applicable_n,
      defaultCohortN: def.n,
      defaultECE: def.ece,
      defaultMCE: def.mce,
      defaultBrier: def.brier,
      allCohortN: all.n,
      allECE: all.ece,
      allMCE: all.mce,
      allBrier: all.brier,
    };

    for (const [name, want] of Object.entries(expected)) {
      assert.ok(
        name in consts,
        `CalibrationParityTests must declare \`static let ${name}\` — it is how ` +
          "native is bound to the shared record",
      );
      if (typeof want === "number") {
        near(consts[name], want, `native's ${name}`);
      } else {
        assert.equal(consts[name], want, `native's ${name}`);
      }
    }

    assert.match(src, /includeThin: true/,
      "native's parity test must exercise the cohort toggle; a record for one " +
        "state leaves the other ungraded");

    // Declaring a constant is not asserting on it. Without this, native could
    // carry a perfect copy of the record and never compare anything to it —
    // which is a tidier version of the exact defect this card is about. Found
    // by mutation: neutering native's toggle test left the gate green when the
    // only check was that the string `includeThin: true` appeared somewhere.
    for (const name of [
      "defaultCohortN", "defaultECE", "defaultMCE", "defaultBrier",
      "allCohortN", "allECE", "allMCE", "allBrier",
    ]) {
      const uses = [...src.matchAll(new RegExp(`Self\\.${name}\\b`, "g"))].length;
      assert.ok(
        uses > 0,
        `CalibrationParityTests declares \`${name}\` but never asserts against it. ` +
          "A record nothing is compared to is decoration.",
      );
    }
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
    assert.match(vm, /var reconciles:\s*Bool/);
  });
});

describe("the two surfaces publish the same protocol", () => {
  it("native declares a hook for every figure web publishes as data", () => {
    const hooks = nativeHooks(read(NATIVE_VIEW));
    const ids = webTestIds(read(WEB_PAGE));

    // Deliberately a hard-coded list and not "whatever native happens to
    // declare": a gate derived entirely from one side cannot notice that side
    // dropping one.
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

    for (const name of ["generatedAtHook", "outcomesHook", "eceHook", "brierHook"]) {
      assert.ok(
        ids.has(hooks[name]),
        `native hook ${name}="${hooks[name]}" has no matching data-testid/testId on ` +
          `frontend/app/calibration/page.tsx. Web's ids: ${[...ids].sort().join(", ")}`,
      );
    }
  });

  it("the parity descriptor carries the same keys in both languages", () => {
    // C236's second P1 in its general form: matching NAMES concealing different
    // value protocols. Comparing the key sets of the two `key=value` builders is
    // what makes the two descriptors interchangeable rather than merely
    // similarly named.
    const keysOf = (src, fnPattern, label) => {
      const start = src.search(fnPattern);
      assert.ok(start >= 0, `could not find ${label}'s parity-value builder`);
      const body = src.slice(start, start + 2000);
      return new Set([...body.matchAll(/\b([a-z_]+)=\\?\(?/g)].map((m) => m[1]));
    };

    const nativeKeys = keysOf(read(NATIVE_VIEW), /static func provenanceValue/, "native");
    const webKeys = keysOf(read(WEB_PARITY_LIB), /export function parityValue/, "web");

    const expected = [
      "population", "contract", "cache", "generated", "cohort_n", "full_n",
      "moved_n", "unchanged_n", "not_applicable_n", "markets", "ece", "mce",
      "brier", "reconciles",
    ];
    for (const k of expected) {
      assert.ok(nativeKeys.has(k), `native's provenance value is missing \`${k}=\``);
      assert.ok(webKeys.has(k), `web's parity value is missing \`${k}=\``);
    }
  });

  it("both surfaces judge the population contract in the same vocabulary", () => {
    // The divergence the vacuous gate hid: web published
    // `data-contract-state="match"` and native published `"matched"` for the
    // SAME payload. Two clients, one field name, different values — and nothing
    // compared them, exactly as C236 predicted.
    //
    // Web's vocabulary is authoritative because the live browser-audit rail
    // asserts on it (`e2e/specs/calibration.spec.ts` requires the rendered state
    // to be one of `["match", "unverified"]`).
    const webStates = new Set(
      [...read(WEB_CONTRACT_LIB).matchAll(/state = "([a-z]+)"/g)].map((m) => m[1]),
    );
    assert.ok(webStates.has("match"), "web must still publish `match`");

    const nativeStates = new Set(
      [...read(NATIVE_VIEWMODEL).matchAll(/state = "([a-z]+)"/g)].map((m) => m[1]),
    );
    assert.ok(nativeStates.size > 0, "native must publish a contract state");

    for (const s of nativeStates) {
      assert.ok(
        webStates.has(s),
        `native publishes contract state "${s}", which web never publishes. ` +
          `Web's vocabulary is ${[...webStates].sort().join(", ")} and is the one ` +
          "the browser-audit rail grades on.",
      );
    }
    assert.equal(
      RECORD.surface.contract_state, "match",
      "the record must carry web's spelling, since that is what ships publicly",
    );
  });
});
