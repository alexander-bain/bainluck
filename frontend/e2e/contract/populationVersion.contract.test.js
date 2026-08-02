"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * L2-232 — the backend/frontend population-version parity gate.
 *
 * ## What broke, twice, on 2026-08-02
 *
 * `/api/calibration` stamps its payload with a `population_version`, and BOTH
 * sides validate it. That is correct, and it is also a tripwire strung between
 * two independently-deployed systems:
 *
 *   1. Q299 bumped the backend constant q267 -> q299. Every serve tier
 *      re-validates version, so the moment the dyno booted, the live Redis key
 *      AND the 7-day durable last-good both became `wrong_version` — and the
 *      replacement could not exist until the next hourly precompute. The public
 *      page served `no_trustworthy_snapshot` for roughly ninety minutes, until
 *      `dc79c9b4` rolled the constant back.
 *
 *   2. The same day, L2-231 shipped `expectedPopulationVersion = "q299"` into
 *      the iOS build. The server then rolled BACK to q267 — so the app started
 *      refusing a perfectly valid payload. The client's constant, not the data,
 *      took the surface down.
 *
 * Both are the same shape: one side changed a version the other side had
 * hard-coded, and the disagreement was only discovered in production.
 *
 * ## What this gate does
 *
 * It fails the build when the backend's published `CALIBRATION_POPULATION_VERSION`
 * is not in the frontend's `COMPATIBLE_POPULATION_VERSIONS`. That turns a dark
 * page into a red CI run, which is the entire point: the bump cannot reach
 * production ahead of the client that has to label it.
 *
 * ## Why it lives HERE and not in jest
 *
 * `npx jest` is not wired into any GitHub Actions workflow — `ci.yml` runs
 * backend pytest, `npm run build` (ESLint only; `ignoreBuildErrors: true` means
 * it is not even a TypeScript gate), and this `node --test` suite. So a jest
 * assertion is a local gate and a code-review aid, not something that can stop
 * a merge. This suite is the frontend's only always-on CI gate that can execute
 * arbitrary checks, it needs no install and no network, and a cross-system
 * version contract is exactly the kind of invariant that has to be enforced
 * where it cannot be skipped.
 *
 * Both files are read as TEXT and matched with a narrow regex rather than
 * imported: one is Python, the other is TypeScript, and this runner is plain
 * Node with no dependencies (deliberately — see `ci.yml`'s note on why this job
 * does no `npm ci`). The literals are simple, and the shape assertions below
 * fail loudly if either declaration is ever restructured, so a silent no-op is
 * not one of the outcomes.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const BACKEND_FILE = path.join(
  REPO_ROOT, "backend", "app", "tasks", "precompute_calibration.py",
);
const FRONTEND_FILE = path.join(REPO_ROOT, "frontend", "lib", "calibrationContract.ts");
const NATIVE_FILE = path.join(
  REPO_ROOT, "ios", "Bain Luck", "Bain Luck", "ViewModels", "CalibrationViewModel.swift",
);

function read(file) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (err) {
    // A missing file must be LOUD. Silently skipping is how a guard becomes
    // decoration: the run stays green and nobody learns the check stopped
    // running. If either path moves, this assertion names it.
    assert.fail(
      `L2-232 parity gate could not read ${path.relative(REPO_ROOT, file)}: ${err.message}. ` +
        "If the file moved, update this fixture — do not delete the check.",
    );
  }
}

/**
 * The backend's currently published population version.
 *
 * Matches only an ASSIGNMENT at column zero, so the long explanatory comment
 * block above the constant (which quotes both "q299" and "q267" in prose)
 * cannot be mistaken for the declaration.
 */
function backendVersion(source) {
  const matches = [...source.matchAll(/^CALIBRATION_POPULATION_VERSION\s*=\s*"([^"]+)"/gm)];
  assert.equal(
    matches.length, 1,
    `expected exactly one top-level CALIBRATION_POPULATION_VERSION assignment, found ` +
      `${matches.length}. The parity gate reads it textually; if the declaration ` +
      "changed shape, update this fixture.",
  );
  return matches[0][1];
}

/** The versions the frontend build declares its labels can describe. */
function frontendVersions(source) {
  const decl = source.match(
    /COMPATIBLE_POPULATION_VERSIONS\s*:\s*readonly string\[\]\s*=\s*\[([^\]]*)\]/,
  );
  assert.ok(
    decl,
    "could not find the COMPATIBLE_POPULATION_VERSIONS array literal in " +
      "frontend/lib/calibrationContract.ts. The parity gate reads it textually; " +
      "if the declaration changed shape, update this fixture.",
  );
  return [...decl[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

/**
 * The versions the iOS build declares its labels can describe.
 *
 * Native is in scope here because native is the surface that actually broke:
 * L2-231's lone `expectedPopulationVersion = "q299"` shipped, the server rolled
 * back to q267, and the app spent the rest of the day refusing valid data. A
 * gate that watches only the web page would have been green through all of it.
 */
function nativeVersions(source) {
  const decl = source.match(
    /compatiblePopulationVersions\s*:\s*Set<String>\s*=\s*\[([^\]]*)\]/,
  );
  assert.ok(
    decl,
    "could not find the compatiblePopulationVersions set literal in " +
      "ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift. The parity " +
      "gate reads it textually; if the declaration changed shape, update this fixture.",
  );
  return [...decl[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

/** Every client that renders the calibration curve, and must therefore label it. */
function clients() {
  return [
    { name: "web (frontend/lib/calibrationContract.ts)", versions: frontendVersions(read(FRONTEND_FILE)) },
    { name: "native (ios/.../CalibrationViewModel.swift)", versions: nativeVersions(read(NATIVE_FILE)) },
  ];
}

describe("population-version parity between backend and every client", () => {
  it("reads a single well-formed version from each side", () => {
    const backend = backendVersion(read(BACKEND_FILE));
    const frontend = frontendVersions(read(FRONTEND_FILE));

    assert.match(
      backend, /^[a-z0-9][a-z0-9._-]{0,31}$/i,
      `backend population version ${JSON.stringify(backend)} is not a version token`,
    );
    assert.ok(frontend.length > 0, "the frontend compatible list must not be empty");
    assert.equal(
      new Set(frontend).size, frontend.length,
      `the frontend compatible list has duplicates: ${frontend.join(", ")}`,
    );
  });

  it("every client declares a non-empty, duplicate-free set", () => {
    for (const { name, versions } of clients()) {
      assert.ok(versions.length > 0, `${name}: the compatible list must not be empty`);
      assert.equal(
        new Set(versions).size, versions.length,
        `${name}: the compatible list has duplicates: ${versions.join(", ")}`,
      );
    }
  });

  it("web and native agree with each other", () => {
    // Two clients rendering the same curve under different contracts is the
    // divergence L2-231's parity matrix went looking for. Catch it in CI rather
    // than by comparing screenshots.
    const [web, native] = clients();
    assert.deepEqual(
      [...web.versions].sort(), [...native.versions].sort(),
      `web claims ${web.versions.join(", ")} but native claims ${native.versions.join(", ")}. ` +
        "The two surfaces must describe the same populations, or one of them is " +
        "labelling numbers the other refuses.",
    );
  });

  it("every client can label the population the backend publishes", () => {
    const backend = backendVersion(read(BACKEND_FILE));

    for (const { name, versions } of clients()) {
    assert.ok(
      versions.includes(backend),
      [
        "",
        `The backend now publishes population_version "${backend}", and ${name}`,
        `only claims to describe: ${versions.map((v) => `"${v}"`).join(", ")}.`,
        "",
        "Deployed as-is, that surface would refuse the live payload and show no curve",
        "— the 2026-08-02 outage, rebuilt on the client side.",
        "",
        "The fix is an ORDERED two-step, and the order is the whole safeguard:",
        "",
        `  1. Confirm that surface's labels are still true of the "${backend}"`,
        "     population — the hero copy, the cohort toggle, the category bar, and the",
        "     raw -> published reconciliation in the methodology section. If the bump",
        "     added exclusion classes the surface has no field or copy for, teach the",
        "     surface FIRST.",
        `  2. Add "${backend}" to COMPATIBLE_POPULATION_VERSIONS in`,
        "     frontend/lib/calibrationContract.ts AND to compatiblePopulationVersions in",
        "     ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift, and SHIP",
        "     THAT BEFORE the backend bump.",
        "",
        "Shipping the clients first means both versions are acceptable to them for the",
        "whole rollout window, so it does not matter whether Vercel or Heroku lands",
        "first. Reversed, there is a window where a deployed client refuses the",
        "deployed backend — and a shipped iOS build cannot be rolled back at all.",
        "",
        "Do not silence this check by widening the regex or deleting the assertion.",
        "",
      ].join("\n"),
    );
    }
  });
});
