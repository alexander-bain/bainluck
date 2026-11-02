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

test("the weekly summary preserves the browser family's shared priority and area", () => {
  const {SUMMARY_LABELS} = require('../helpers/weeklySummary');
  assert.deepEqual(SUMMARY_LABELS.filter(label=>label.startsWith('priority:')),['priority:p3']);
  assert.ok(SUMMARY_LABELS.includes('area:frontend'));
  assert.ok(SUMMARY_LABELS.includes('program:ux'));
  const source = fs.readFileSync(SCRIPT,'utf8');
  assert.match(source,/labels:SUMMARY_LABELS/);
  assert.ok(!source.includes('Still failing on'), 'per-issue comments must stay retired');
});
