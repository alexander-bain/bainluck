"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

/**
 * #8959: the website and the phone say the same thing about how current the
 * accuracy numbers are.
 *
 * Web decides its banner in `frontend/lib/calibrationStaleness.ts` and prints
 * the body in `app/calibration/page.tsx`. The phone's copy is a port of both,
 * in `Utilities/CalibrationStaleness.swift`. Until #8959 the phone decoded
 * `cache` alone, so a main-tier payload saying "the market data behind this is
 * 15 hours old" reached the website and not the app — and the one state the app
 * did render still used wording web had retired (#4113, #5042).
 *
 * Neither runner can read the other's code, so this file reads all three
 * sources and requires web and native to carry each sentence. Reword one
 * surface only and this goes red. `CalibrationStalenessTests8959.swift` pins
 * the assembled Swift banner on the real production envelope.
 */

const repo = path.resolve(__dirname, "..", "..", "..");
const read = (rel) => fs.readFileSync(path.join(repo, rel), "utf8");

// TS/JSX: collapse whitespace and resolve the one entity the banner uses.
const webText = (src) => src.replace(/&rsquo;/g, "’").replace(/\s+/g, " ");
// Swift: join `"…" + "…"` literals and collapse whitespace.
const swiftText = (src) => src.replace(/"\s*\+\s*"/g, "").replace(/\s+/g, " ");

const webLib = webText(read("frontend/lib/calibrationStaleness.ts"));
const webPage = webText(read("frontend/app/calibration/page.tsx"));
const swift = swiftText(read("ios/Bain Luck/Bain Luck/Utilities/CalibrationStaleness.swift"));
const swiftVM = read("ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift");
const swiftView = read("ios/Bain Luck/Bain Luck/Views/CalibrationView.swift");

// Headlines, the cadence clause and the input sentence — web's lib owns these.
const LIB_SENTENCES = [
  "Showing the last complete snapshot.",
  "The curve is current. The data behind it is older.",
  "We can't confirm the curve is current. The data behind it is older.",
  "We can't confirm how current the data behind this is.",
  "We can't confirm how current this is.",
  "The curve rebuilds hourly.",
  "Hourly rebuilds have not produced a new snapshot.",
  "come and gone without a new snapshot.",
  '"hourly rebuild has"',
  '"hourly rebuilds have"',
  "The market data behind it is being gathered again from scratch, so it has no date to show.",
  "We couldn’t read when the market data behind it was last staged.",
  '"served_bank_empty"',
  '"moments"',
];

// The banner body — web's page owns these.
const PAGE_FRAGMENTS = [
  "These numbers were built",
  "and are not being refreshed right now.",
  "The curve was rebuilt on schedule, but the market data behind it was last staged ",
  "The market data behind it was last staged ",
  ". So it describes the market as of then, not now.",
  "We’d rather say so than call these numbers current.",
];

describe("#8959 staleness banner copy: web and native carry the same words", () => {
  for (const s of LIB_SENTENCES) {
    it(`lib + native both carry ${s}`, () => {
      assert.ok(webLib.includes(s), `calibrationStaleness.ts no longer carries ${s}`);
      assert.ok(swift.includes(s), `CalibrationStaleness.swift has drifted from web: ${s}`);
    });
  }

  for (const s of PAGE_FRAGMENTS) {
    it(`page + native both carry ${s}`, () => {
      assert.ok(webPage.includes(s), `page.tsx banner no longer carries ${s}`);
      assert.ok(swift.includes(s), `CalibrationStaleness.swift banner has drifted from web: ${s}`);
    });
  }

  // The retired wording must not survive on the phone. #5042 retired "without
  // one succeeding" (the count measures the artifact, not failed runs) and the
  // old native-only stall sentence never existed on web at all.
  it("native no longer carries the cadence wording web retired (#5042)", () => {
    for (const src of [swift, swiftVM]) {
      assert.ok(!src.includes("without one succeeding"), "retired #5042 wording is back");
      assert.ok(!src.includes("not currently succeeding"), "native-only stall sentence is back");
    }
  });

  // The defect's mechanism: the view must take its headline from the decision,
  // not hard-code the last-good lead, or every other state renders under it.
  it("the native view renders the decided headline, not a hard-coded one", () => {
    assert.ok(!swiftView.includes('Text("Showing the last complete snapshot.")'),
      "CalibrationView hard-codes the last-good headline again");
    assert.ok(swiftView.includes("viewModel.staleBannerHeadline"),
      "CalibrationView no longer reads the decided headline");
  });

  // …and the decision must read the fields web reads, or it is a port in name only.
  it("the native decision reads availability and the staged block", () => {
    assert.ok(/availability:\s*data\.availability/.test(swiftVM), "view model ignores availability");
    assert.ok(/staged:\s*data\.staged/.test(swiftVM), "view model ignores the staged block");
  });
});
