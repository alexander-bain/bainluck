"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #8476: the website and the phone say the same thing about held-out rows.
 *
 * Web's "Held out, under review" card (`app/calibration/page.tsx`, CAL-P067
 * item 5) and the phone's copy of it (`CalibrationViewModel.quarantineCaption`,
 * `CalibrationView.quarantineSection`) are two hand-written copies in two
 * languages. Neither runner can read the other's code, so this file reads both
 * sources and requires each to carry the same words. Reword one surface only
 * and this goes red. `CalibrationQuarantineTests8476.swift` pins the assembled
 * Swift sentence, so a Swift-side change that keeps the fragments but breaks
 * the sentence is caught there.
 */

const repo = path.resolve(__dirname, "..", "..", "..");
const read = (rel) => fs.readFileSync(path.join(repo, rel), "utf8");

// JSX: collapse whitespace and resolve the one entity the sentence uses.
const webText = (src) => src.replace(/&mdash;/g, "—").replace(/\s+/g, " ");
// Swift: join `"…" + "…"` literals and resolve the escape the sentence uses.
const swiftText = (src) =>
  src.replace(/"\s*\+\s*"/g, "").replace(/\\u\{2014\}/g, "—").replace(/\s+/g, " ");

const web = webText(read("frontend/app/calibration/page.tsx"));
const swiftVM = swiftText(read("ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift"));
const swiftView = swiftText(read("ios/Bain Luck/Bain Luck/Views/CalibrationView.swift"));

const SENTENCE =
  "excluded from every curve on this page while we check them. They are not graded, " +
  "not counted, and not deleted — a held-out row is a stated exclusion we can " +
  "reverse, which is the difference between a quarantine and a quietly shorter denominator.";

describe("#8476 held-out card copy: web and native carry the same words", () => {
  it("web still prints the caption sentence this file pins", () => {
    assert.ok(web.includes(SENTENCE), "page.tsx no longer carries the pinned caption sentence");
  });

  it("native's caption carries the same sentence", () => {
    assert.ok(swiftVM.includes(SENTENCE),
      "CalibrationViewModel.quarantineCaption has drifted from web's caption");
  });

  it("both carry the singular/plural pair and the card title", () => {
    for (const [name, src] of [["web", web], ["native", swiftVM]]) {
      assert.ok(src.includes('"outcome is"') && src.includes('"outcomes are"'),
        `${name} lost the outcome is / outcomes are pair`);
    }
    assert.ok(web.includes("Held out, under review"), "web card title changed");
    assert.ok(swiftView.includes('"Held out, under review"'), "native card title differs from web");
  });

  it("guard is not vacuous: a one-word edit to either copy is detected", () => {
    const mutated = SENTENCE.replace("not deleted", "not removed");
    assert.ok(!web.includes(mutated) && !swiftVM.includes(mutated));
  });
});
