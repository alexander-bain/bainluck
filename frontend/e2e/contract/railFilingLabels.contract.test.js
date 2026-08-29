"use strict";

/**
 * Q434 — the browser-audit sweep filer emits a `priority:*`.
 *
 * On 2026-08-28 this rail filed #2249 and #2250, and both landed on the board with
 * no priority label. The label list was a bare literal inside
 * `scripts/file-sweep-findings.js` — the side-effecting shell that no test loads —
 * so nothing could have caught it. It now lives in the pure, contract-tested helper.
 *
 * `priority:p3` is not a guess: BOARD-TAXONOMY.md names the family default in so
 * many words — "Family defaults: parked -> p3, Browser-audit -> p3".
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { FILING_LABELS } = require("../helpers/sweepFiling");

const SCRIPT = path.join(__dirname, "..", "scripts", "file-sweep-findings.js");

test("the filer emits exactly one priority label", () => {
  const priorities = FILING_LABELS.filter((l) => l.startsWith("priority:"));
  assert.deepEqual(priorities, ["priority:p3"]);
});

test("the filer emits area, type and the source labels", () => {
  for (const required of ["type:bug", "area:frontend", "alert-intake", "program:ux"]) {
    assert.ok(FILING_LABELS.includes(required), `missing ${required}`);
  }
});

test("every label is a non-empty string with no stray whitespace", () => {
  for (const label of FILING_LABELS) {
    assert.equal(typeof label, "string");
    assert.equal(label, label.trim());
    assert.ok(label.length > 0);
  }
});

test("the filing script consumes the shared constant, not its own literal", () => {
  const source = fs.readFileSync(SCRIPT, "utf8");
  assert.ok(
    source.includes("FILING_LABELS"),
    "file-sweep-findings.js no longer imports FILING_LABELS"
  );
  assert.ok(
    !/const LABELS = \[/.test(source),
    "file-sweep-findings.js re-declared its own LABELS literal — the drift this test exists to stop"
  );
});

test("the shared constant is what reaches `gh issue create`", () => {
  // The shell flatMaps LABELS into `--label` pairs. Pin that wiring, so moving the
  // constant into the helper cannot be undone by a rename at the call site.
  const source = fs.readFileSync(SCRIPT, "utf8");
  assert.ok(
    /LABELS\.flatMap\(\(l\) => \["--label", l\]\)/.test(source),
    "the --label expansion no longer reads LABELS"
  );
});
