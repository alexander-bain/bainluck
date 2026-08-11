"use strict";

/**
 * UX-P057 — the audit packs run one at a time, and that cannot be undone quietly.
 *
 * THE DEFECT. A scheduled sweep expands its matrix into two full browser packs
 * and, with no `max-parallel`, GitHub starts them in the same second. Measured
 * on both runs that filed the surviving issues:
 *
 *   run 31473736725  tournament-inventory  08:33:30Z   deploy-smoke+consent  08:33:30Z
 *   run 31372562742  tournament-inventory  09:00:04Z   deploy-smoke+consent  09:00:04Z
 *
 * Two packs against one 60/min public API produce HTTP 429, and the graders do
 * exactly the right thing with a 429: report it as a failed request and as a
 * console error. Twelve open issues therefore describe nothing but the rail
 * rate-limiting itself and filing the result — the crying-wolf state #1648
 * exists to end, arriving through a different door.
 *
 * WHY A GUARD AND NOT JUST THE FIX. This was already believed to be handled, by
 * the pack-in-the-concurrency-key change (#1691) — and that belief was wrong in
 * two independent ways: the key governs separate DISPATCHES rather than legs of
 * one run, and its purpose was the opposite of serialising (it stopped packs
 * cancelling each other, which is what allows them to overlap). A belief that
 * survived a cycle because nothing asserted it is exactly what a contract test
 * is for.
 *
 * Dependency-free (`node --test`), like every fixture in this directory: it must
 * run before Playwright is installed.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..", "..", "..");
const workflowPath = path.join(repoRoot, ".github", "workflows", "browser-audit.yml");
const raw = fs.readFileSync(workflowPath, "utf8");

/** The `strategy:` block of the audit job, without a YAML parser. */
function strategyBlock(text) {
  const start = text.indexOf("\n    strategy:");
  assert.notEqual(start, -1, "the audit job must declare a strategy block");
  const after = text.slice(start + 1);
  const lines = after.split("\n");
  const out = [lines[0]];
  for (const line of lines.slice(1)) {
    // The block ends at the next key indented at the same level (4 spaces).
    if (/^ {4}\S/.test(line)) break;
    out.push(line);
  }
  return out.join("\n");
}

describe("UX-P057: the browser-audit packs are serialized", () => {
  const strategy = strategyBlock(raw);

  it("declares max-parallel: 1 on the pack matrix", () => {
    assert.match(
      strategy,
      /^\s*max-parallel:\s*1\s*$/m,
      "without max-parallel the matrix legs start in the same second and 429 each other",
    );
  });

  it("keeps fail-fast: false — serialising must not start cancelling", () => {
    // These two settings answer different questions. Serialising changes WHEN a
    // leg runs; fail-fast would change WHETHER it runs at all. A red smoke pack
    // must still leave the tournament pack's evidence intact.
    assert.match(strategy, /^\s*fail-fast:\s*false\s*$/m);
  });

  it("still runs both packs on a scheduled sweep", () => {
    // The other direction (gotcha #43): serialising must not become a way to
    // quietly drop a pack. Cheaper legs are not the goal; non-overlapping ones are.
    assert.match(strategy, /deploy-smoke\+consent/);
    assert.match(strategy, /tournament-inventory/);
  });

  it("records WHY, with the measurement, next to the setting", () => {
    // A bare `max-parallel: 1` reads as a cost control and is one cleanup away
    // from deletion. The run ids are the reason it exists.
    assert.match(strategy, /31473736725|31372562742/);
  });

  /**
   * The concurrency key is NOT the mechanism, and saying so here stops the next
   * reader concluding that #1691 already covered this and removing the setting.
   */
  it("does not rely on the concurrency group, which serialises nothing", () => {
    assert.match(raw, /group:\s*browser-audit-/);
    const concurrency = raw.slice(raw.indexOf("\nconcurrency:"));
    assert.doesNotMatch(
      concurrency.slice(0, concurrency.indexOf("\njobs:")),
      /max-parallel/,
      "the matrix limit belongs to the job strategy, not the concurrency block",
    );
  });
});
