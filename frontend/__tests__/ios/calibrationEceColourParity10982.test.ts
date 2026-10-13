/**
 * #10982 — the same Accuracy error is the same colour on the website and the
 * iPhone, or CI says so.
 *
 * THE BUG. On the served default Accuracy view, AFL 5.1, NRL 5.6 and Lacrosse
 * 6.9 were orange on a 390px web page and blue in the installed app, and
 * Entertainment through Tech at 3.1–3.8 were blue on web and green in the app.
 * Web colours the hero, the cohort row and every category cell `< 3` green,
 * `< 5` blue, else orange. The app's own `eceQualityLabel` cuts at 3 and 5 too.
 * Only `CalibrationViewModel.eceColor` used `< 4` / `< 8`. Each surface was
 * internally consistent and neither knew about the other.
 *
 * SO THIS GUARDS THE COUPLING. It reads both files as source and requires every
 * web colour ladder and the Swift `eceColor` to share one pair of cut-points.
 * Against the old Swift bands it fails on the cut-point comparison.
 *
 * It lives in jest because jest is a deploy gate and the Swift test target is
 * not reachable from CI (notice 10's iOS clause). The colours themselves are
 * asserted by `CalibrationEceColour10982Tests`.
 */

import { readFileSync } from "fs";
import { join } from "path";

const WEB = join(__dirname, "../../app/calibration/page.tsx");
const IOS_VM = join(
  __dirname,
  "../../../ios/Bain Luck/Bain Luck/ViewModels/CalibrationViewModel.swift",
);

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

/** A missing file must be LOUD: a guard that silently skips is decoration. */
function read(file: string): string {
  try {
    return readFileSync(file, "utf8");
  } catch (err) {
    throw new Error(
      `#10982 ECE colour parity gate could not read ${file}: ${String(err)}. ` +
        `If the file moved, update this guard — do not delete the check.`,
    );
  }
}

const web = stripComments(read(WEB));
const ios = stripComments(read(IOS_VM));

/**
 * Every `X < a ? "text-green-600" : X < b ? "text-blue-600" : "text-orange-600"`
 * on the page, as `[a, b]`. The variable is captured so the guard can say which
 * value each ladder colours.
 */
const webLadders = [
  ...web.matchAll(
    /([\w.]+)\s*<\s*([\d.]+)\s*\?\s*"text-green-600"\s*:\s*\1\s*<\s*([\d.]+)\s*\?\s*"text-blue-600"\s*:\s*"text-orange-600"/g,
  ),
].map((m) => ({ value: m[1], cuts: [Number(m[2]), Number(m[3])] }));

const iosColour = ios.match(
  /func eceColor\(_ ece: Double\) -> Color \{\s*ece\s*<\s*([\d.]+)\s*\?\s*\.green\s*:\s*\(\s*ece\s*<\s*([\d.]+)\s*\?\s*\.blue\s*:\s*\.orange\s*\)\s*\}/,
);
const iosLabel = ios.match(
  /var eceQualityLabel: String \{[\s\S]*?v\s*<\s*([\d.]+)\s*\?\s*"Excellent"\s*:\s*v\s*<\s*([\d.]+)\s*\?\s*"Very Good"/,
);

describe("#10982 — one ECE colour on the website and the iPhone", () => {
  it("reads every colour ladder the page draws", () => {
    // The hero, the Combined cohort row and the category cell. An extractor
    // that returns [] would make the comparisons below pass on nothing.
    expect(webLadders.map((l) => l.value)).toEqual(
      expect.arrayContaining(["cohortECE", "cm.ece"]),
    );
    expect(webLadders.length).toBeGreaterThanOrEqual(3);
  });

  it("uses one pair of cut-points everywhere on the web", () => {
    const distinct = new Set(webLadders.map((l) => l.cuts.join("/")));
    expect([...distinct]).toEqual(["3/5"]);
  });

  it("gives the app's eceColor the website's cut-points", () => {
    expect(iosColour).not.toBeNull();
    const cuts = [Number(iosColour![1]), Number(iosColour![2])];
    expect(cuts).toEqual(webLadders[0].cuts);
  });

  it("keeps the app's colour and its own quality word on the same cuts", () => {
    // `eceQualityLabel` already said "Very Good" at 4.5 while `eceColor`
    // painted 3.5 green. The label's first two cuts are the colour's.
    expect(iosLabel).not.toBeNull();
    expect([Number(iosLabel![1]), Number(iosLabel![2])]).toEqual([
      Number(iosColour![1]),
      Number(iosColour![2]),
    ]);
  });
});
