"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * UX-P007 / #1526 — a Discover card must never drop its leader.
 *
 * ## Why this guard lives HERE
 *
 * The defect was pure renderer: `distribution_outcomes.slice(0, 4)` with no
 * sort. The backend was right, the API response was right, and the card threw
 * away the answer on the way to the screen — the Fed September card rendered
 * four also-rans totalling 47% while the 56% "No change" row never appeared.
 *
 * A behavioural test of the helper lives in the jest suite, but `npm run jest`
 * is NOT a CI gate in this repo (no workflow invokes it — that is what
 * `jestGate.contract.test.js` exists to record). So the assertion that must
 * actually block a deploy lives in the dependency-free `node --test` suite that
 * `ci.yml` runs as `e2e-contract`, which `deploy: needs:` already lists.
 *
 * ## What it asserts
 *
 * Only the wiring, read as text: that the truncation sites in the Discover card
 * family go through `leaderFirstSlice`, and that the helper still sorts
 * descending with a stable tie-break. HOW the ordering behaves is the jest
 * file's job. Re-introduce a bare `.slice(0, N)` over an outcome array and this
 * fails by name rather than shipping a card with no leader.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const FRONTEND = path.join(REPO_ROOT, "frontend");

const HELPER = path.join(FRONTEND, "lib", "discover", "leaderOrder.ts");

// Each truncation site that renders an outcome list on a Discover card.
const CALL_SITES = [
  {
    file: path.join(FRONTEND, "components", "discover", "FuturesCard.tsx"),
    // The named #1526 instance: the outcome_distribution branch.
    forbidden: /distributionRows\s*\.slice\s*\(/,
    forbiddenWhy:
      "FuturesCard sliced distribution_outcomes without sorting — this IS the " +
      "#1526 Fed-September leader drop",
  },
  {
    file: path.join(FRONTEND, "components", "FeedCard.tsx"),
    forbidden: /data\.top_outcomes\s*\.slice\s*\(/,
    forbiddenWhy:
      "FeedCard sliced top_outcomes without sorting; index 0 is styled as THE " +
      "favorite, so an unsorted slice bolds an also-ran",
  },
];

function read(file) {
  assert.ok(fs.existsSync(file), `${path.relative(REPO_ROOT, file)} is missing`);
  return fs.readFileSync(file, "utf8");
}

describe("#1526 — Discover cards truncate leader-first", () => {
  it("the shared helper exists and is exported", () => {
    const src = read(HELPER);
    assert.match(
      src,
      /export function leaderFirstSlice\b/,
      "leaderFirstSlice is the call sites' single entry point"
    );
    assert.match(src, /export function leaderFirst\b/);
  });

  it("the helper sorts DESCENDING by probability", () => {
    const src = read(HELPER);
    // pb - pa, not pa - pb. An inverted comparator would put the least likely
    // outcome first and still pass every "did it sort?" assertion.
    assert.match(
      src,
      /return\s+pb\s*-\s*pa\s*;/,
      "comparator must be descending (pb - pa) — ascending would surface the " +
        "LEAST likely outcome as the leader"
    );
  });

  it("the helper keeps ties in their incoming order", () => {
    const src = read(HELPER);
    assert.match(
      src,
      /return\s+a\.index\s*-\s*b\.index\s*;/,
      "equal probabilities must keep the backend's tie-break (rank, ladder " +
        "position, alphabetical) instead of being reshuffled"
    );
  });

  it("an unpriced row can never sort as the leader", () => {
    const src = read(HELPER);
    assert.match(
      src,
      /probability\s*\?\?\s*-1/,
      "null probability must sort below 0, not coerce to 0 and outrank a " +
        "genuine 0% row"
    );
  });

  for (const site of CALL_SITES) {
    const rel = path.relative(REPO_ROOT, site.file);

    it(`${rel} truncates through leaderFirstSlice`, () => {
      const src = read(site.file);
      assert.match(
        src,
        /leaderFirstSlice\s*\(/,
        `${rel} must truncate outcome rows through leaderFirstSlice`
      );
      assert.match(
        src,
        /from "@\/lib\/discover\/leaderOrder"/,
        `${rel} must import the shared helper rather than re-implement the sort`
      );
    });

    it(`${rel} has no bare unsorted outcome slice`, () => {
      const src = read(site.file);
      assert.doesNotMatch(src, site.forbidden, site.forbiddenWhy);
    });
  }
});
