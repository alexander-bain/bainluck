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

const BOARD_RULE = path.join(FRONTEND, "lib", "discover", "futuresBoard.ts");

// Each truncation site that renders an outcome list on a card of this family.
//
// #8025 MOVED THE FIRST ONE. The outcome_distribution branch used to slice
// inside `FuturesCard.tsx`; the rule now lives in `lib/discover/futuresBoard.ts`
// and BOTH cards read it — which is the point, because the browse card
// (`/sports`, `/categories/*`, `/my-stuff`) previously had no board at all and
// was therefore invisible to the old form of this guard. The entry follows the
// rule to its new home rather than being deleted with it.
const CALL_SITES = [
  {
    file: BOARD_RULE,
    // The named #1526 instance: the outcome_distribution board.
    forbidden: /\bpriced\s*\.slice\s*\(/,
    forbiddenWhy:
      "futuresBoard sliced the priced distribution rows without sorting — this " +
      "IS the #1526 Fed-September leader drop",
    // Its own sibling, so the relative specifier is the correct one here; the
    // alias form would be the odd spelling inside `lib/discover/`.
    imports: /from "\.\/leaderOrder"/,
  },
  {
    file: path.join(FRONTEND, "components", "FeedCard.tsx"),
    forbidden: /data\.top_outcomes\s*\.slice\s*\(/,
    forbiddenWhy:
      "FeedCard sliced top_outcomes without sorting; index 0 is styled as THE " +
      "favorite, so an unsorted slice bolds an also-ran",
    imports: /from "@\/lib\/discover\/leaderOrder"/,
  },
];

// #8025 — neither CARD may go back to reading the board itself. The rule is only
// shared while both cards call it, and a component that re-derives its own rows
// from `distribution_outcomes` is how the two surfaces drifted apart the first
// time. Asserted on CODE, with comments stripped: both files discuss the field
// by name in their docblocks, and a guard that cannot tell prose from a property
// access would either fire on a comment or be written loose enough to miss the
// real thing.
const BOARD_READERS_MUST_NOT = [
  path.join(FRONTEND, "components", "discover", "FuturesCard.tsx"),
  path.join(FRONTEND, "components", "FeedCard.tsx"),
];

function read(file) {
  assert.ok(fs.existsSync(file), `${path.relative(REPO_ROOT, file)} is missing`);
  return fs.readFileSync(file, "utf8");
}

/**
 * Source with `//` and block comments removed, so prose cannot match.
 *
 * LINE COMMENTS COME OFF FIRST, AND THE ORDER IS THE WHOLE TRICK. Doing block
 * comments first swallowed 120 lines of real code on the first run of this file.
 * The docblock above `const board` writes the browse surfaces as a glob ending
 * in a star; inside a line comment that opens a block-comment match, which then
 * closes on the next close-marker — a JSX comment forty lines further down. The
 * stripper then reported that `FuturesCard.tsx` does not call
 * `futuresDistributionBoard`, which is a false verdict that reads exactly like
 * the defect this guard hunts. `://` is spared so a URL in a string survives.
 */
function code(file) {
  return read(file)
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1")
    .replace(/\/\*[\s\S]*?\*\//g, " ");
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
        site.imports,
        `${rel} must import the shared helper rather than re-implement the sort`
      );
    });

    it(`${rel} has no bare unsorted outcome slice`, () => {
      const src = read(site.file);
      assert.doesNotMatch(src, site.forbidden, site.forbiddenWhy);
    });
  }

  for (const file of BOARD_READERS_MUST_NOT) {
    const rel = path.relative(REPO_ROOT, file);

    it(`${rel} reads the board through futuresBoard, never directly`, () => {
      assert.doesNotMatch(
        code(file),
        /\.distribution_outcomes\b/,
        `${rel} reads distribution_outcomes itself instead of calling ` +
          "futuresDistributionBoard — that is the second copy #8025 removed, " +
          "and it is how /sports and /discover came to draw different fields"
      );
      assert.match(
        code(file),
        /futuresDistributionBoard\s*\(/,
        `${rel} must ask the shared rule which rows the board has`
      );
    });
  }

  it("the comment stripper does not hide real code", () => {
    // Half of the pair above is `doesNotMatch`, so an over-eager stripper makes
    // it pass on a file that genuinely reads the field — and that is not a
    // hypothetical: see the docblock on `code()`. Both directions pinned, and
    // the statement that actually got eaten is named.
    assert.match(code(BOARD_RULE), /\.distribution_outcomes\b/);
    for (const file of BOARD_READERS_MUST_NOT) {
      assert.match(
        code(file),
        /const board = futuresDistributionBoard\(data\);/,
        `${path.relative(REPO_ROOT, file)}'s board statement did not survive the ` +
          "comment strip — the guards above are reporting on a mangled file"
      );
    }
    assert.doesNotMatch(
      code(BOARD_RULE),
      /One row of `discover_card\.distribution_outcomes`/,
      "the docblock survived the strip, so the guards above are reading prose"
    );
  });
});
