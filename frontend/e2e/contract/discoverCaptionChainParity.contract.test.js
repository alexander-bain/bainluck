"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #4265 — the third leg of the futures caption-chain parity gate.
 *
 * Web and iOS build a futures card's caption from the same four served strings
 * and used to resolve them differently. Neither runner can see the other's
 * language, so both are held against
 * `fixtures/discover/caption-chain-record-2026-09-09.json`:
 *
 *   - jest: `frontend/__tests__/components/discoverCaptionChain4265.test.ts`
 *     READS the record and asserts `feedContextSnippet` reproduces every row.
 *   - XCTest: `BainLuckTests/DiscoverCaptionParityTests.swift` carries a LITERAL
 *     copy of the table (an XCTest resolving a `#filePath`-relative JSON is
 *     host-filesystem-dependent) and asserts `DiscoverCaption.feedCaption`
 *     reproduces it.
 *
 * This file cannot call Swift and does not import TypeScript. It does the two
 * things it uniquely can, exactly as `calibrationSurfaceParity.contract.test.js`
 * does for CAL-P043:
 *
 *   1. **Parses the Swift table back out of the Swift file** and asserts it is
 *      the record, row for row. A row edited on one side without the other goes
 *      red here.
 *   2. **Asserts both clients are still BOUND to the record** — that the checks
 *      exist, name it, and have not been quietly unhooked, and that neither
 *      client's caption chain has gone back to an operator that reads an empty
 *      string as a value. A gate that can be deleted without anything turning
 *      red is the failure mode this card is about.
 */

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const RECORD_PATH = path.join(
  REPO_ROOT,
  "fixtures",
  "discover",
  "caption-chain-record-2026-09-09.json",
);
const SWIFT_TEST = path.join(
  REPO_ROOT,
  "ios",
  "Bain Luck",
  "BainLuckTests",
  "DiscoverCaptionParityTests.swift",
);
const SWIFT_HELPER = path.join(
  REPO_ROOT,
  "ios",
  "Bain Luck",
  "Bain Luck",
  "Utilities",
  "DiscoverCaption.swift",
);
const SWIFT_CALL_SITE = path.join(
  REPO_ROOT,
  "ios",
  "Bain Luck",
  "Bain Luck",
  "Views",
  "DiscoverView.swift",
);
const WEB_UTILS = path.join(
  REPO_ROOT,
  "frontend",
  "components",
  "discover",
  "utils.ts",
);
const WEB_TEST = path.join(
  REPO_ROOT,
  "frontend",
  "__tests__",
  "components",
  "discoverCaptionChain4265.test.ts",
);

const read = (p) => fs.readFileSync(p, "utf8");
const record = JSON.parse(read(RECORD_PATH));

/** Decode one Swift string literal (or `nil`) as the value it denotes. */
function swiftScalar(raw) {
  const token = raw.trim();
  if (token === "nil") return null;
  assert.match(token, /^".*"$/s, `not a Swift string literal: ${token}`);
  return token
    .slice(1, -1)
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\");
}

/** Every `Row(...)` in the Swift table, as plain objects. */
function parseSwiftRows(source) {
  const table = source.slice(
    source.indexOf("private static let rows: [Row] = ["),
  );
  const rows = [];
  // Field order is fixed by the struct; the parser reads the LABELS, not
  // positions, so a reordered literal is still read correctly (and a renamed
  // field fails loudly rather than silently shifting values by one).
  const pattern =
    /Row\(name:\s*("(?:[^"\\]|\\.)*")\s*,\s*contextSummary:\s*(nil|"(?:[^"\\]|\\.)*")\s*,\s*headline:\s*(nil|"(?:[^"\\]|\\.)*")\s*,\s*reason:\s*(nil|"(?:[^"\\]|\\.)*")\s*,\s*hookDescription:\s*(nil|"(?:[^"\\]|\\.)*")\s*,\s*expected:\s*(nil|"(?:[^"\\]|\\.)*")\s*\)/gs;
  let match;
  while ((match = pattern.exec(table)) !== null) {
    rows.push({
      name: swiftScalar(match[1]),
      context_summary: swiftScalar(match[2]),
      headline: swiftScalar(match[3]),
      reason: swiftScalar(match[4]),
      hook_description: swiftScalar(match[5]),
      expected: swiftScalar(match[6]),
    });
  }
  return rows;
}

describe("#4265 futures caption chain — the record binds both clients", () => {
  it("the record itself is non-empty and carries its production rows", () => {
    // Guard the guard: a record silently emptied makes every comparison below
    // trivially true.
    assert.equal(record.rows.length, 12);
    assert.equal(
      record.rows.filter((r) => r.name.startsWith("prod-")).length,
      5,
    );
  });

  it("the Swift table is the record, row for row", () => {
    const swiftRows = parseSwiftRows(read(SWIFT_TEST));
    // If the regex ever stops matching, this is what catches it — an empty
    // parse must never read as agreement.
    assert.equal(
      swiftRows.length,
      record.rows.length,
      `parsed ${swiftRows.length} Swift rows, record has ${record.rows.length}`,
    );
    for (const [i, expected] of record.rows.entries()) {
      const actual = swiftRows[i];
      assert.equal(actual.name, expected.name, `row ${i} name`);
      for (const field of [
        "context_summary",
        "headline",
        "reason",
        "hook_description",
        "expected",
      ]) {
        assert.equal(
          actual[field],
          expected[field],
          `row ${expected.name} field ${field}`,
        );
      }
    }
  });

  it("both clients are still bound to the record by name", () => {
    assert.match(
      read(WEB_TEST),
      /caption-chain-record-2026-09-09\.json/,
      "web's jest check no longer reads the record",
    );
    assert.match(
      read(SWIFT_TEST),
      /caption-chain-record-2026-09-09\.json/,
      "the Swift check no longer names the record",
    );
    assert.match(
      read(SWIFT_TEST),
      /DiscoverCaption\.feedCaption\(/,
      "the Swift check no longer exercises the shipped helper",
    );
  });

  it("neither client's futures chain reads an empty string as a value", () => {
    // The regression this card exists to stop. On iOS the operator was `??`,
    // which is nil-coalescing: `context_summary: ""` won the chain outright and
    // three cards in the 2026-09-09 edition rendered with no caption at all.
    const callSite = read(SWIFT_CALL_SITE);
    const cardLine = callSite
      .split("\n")
      .find((line) => line.includes("NativeFuturesDiscoverCard(data:"));
    assert.ok(cardLine, "the futures card call site moved — re-anchor this gate");
    assert.match(
      cardLine,
      /DiscoverCaption\./,
      "the futures card no longer routes its caption through DiscoverCaption",
    );
    assert.doesNotMatch(
      cardLine,
      /item\.contextSummary\s*\?\?/,
      "`??` is back on the caption chain — that is #4265",
    );

    // And the helper must still trim, or `\"   \"` captions a card with a blank.
    assert.match(
      read(SWIFT_HELPER),
      /trimmingCharacters\(in:\s*\.whitespacesAndNewlines\)/,
      "DiscoverCaption stopped trimming",
    );
    assert.match(
      read(WEB_UTILS),
      /function firstMeaningful\(/,
      "web's futures chain no longer goes through firstMeaningful",
    );
  });
});
