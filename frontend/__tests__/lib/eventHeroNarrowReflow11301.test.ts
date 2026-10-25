// #11301 — BELOW 360px THE EVENT HERO REFLOWS INTO TWO TEAM CELLS AND A BAND.
//
// ═══ WHAT THIS FILE CAN AND CANNOT SEE ═══
//
// It CANNOT see the defect. The defect is geometric: on the retained 49ers –
// Commanders page (/events/14780563) at 312px the "77" ran 19px into the 49ers
// crest, and at 260px both chances covered both crests and the projected final
// crossed the neighbouring team names and records (Design's hero3 captures).
// That was measured in a real browser — text-run and crest boxes intersected
// inside the hero row: 2 overlaps at 312 and 8 at 260 before this change, 0 and
// 0 after, 0 and 0 at 375 on both builds. A test that reads class names cannot
// measure a layout.
//
// What this file DOES pin is the decision, so a revert is loud. The page has no
// render harness (see #5866's guard for the same constraint), and the whole
// change is class edits whose absence is invisible to every other test:
//   - the hero row may wrap below 360px;
//   - the two team columns each take half the row, in reading order;
//   - the centre block drops to its own full-width row beneath them;
//   - the probability pair spans that row so each figure sits under its own
//     team, and the en dash between them keeps its box but is not drawn;
//   - nothing changes at 360px and up, and the numerals keep their sizes.
//
// Comments are stripped first: this file's docblock and the page's comments
// both name every class below, so an unstripped scan would pass on a page whose
// JSX had been reverted and whose comment still described the fix.

import fs from "fs";
import path from "path";

const PAGE = path.resolve(__dirname, "../../app/events/[id]/page.tsx");
const PAIR = path.resolve(__dirname, "../../components/EventHeroProbabilityPair.tsx");

function executableSource(file: string): string {
  return fs
    .readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
}

describe("#11301 the event hero reflows below 360px instead of squeezing its centre", () => {
  const page = executableSource(PAGE);
  const pair = executableSource(PAIR);

  it("lets the hero row wrap below 360px only", () => {
    expect(page).toContain(
      'className="flex items-stretch justify-between max-[359px]:flex-wrap"',
    );
  });

  it("gives each team column half the row, home first", () => {
    const home = 'className="flex flex-col items-center flex-1 max-[359px]:basis-1/2 max-[359px]:order-1"';
    const away = 'className="flex flex-col items-center flex-1 max-[359px]:basis-1/2 max-[359px]:order-2"';
    expect(page.split(home)).toHaveLength(2);
    expect(page.split(away)).toHaveLength(2);
    expect(page.indexOf(home)).toBeLessThan(page.indexOf(away));
  });

  it("drops the centre block to its own full-width row beneath the teams", () => {
    expect(page).toContain(
      'className="flex flex-col items-center justify-center px-1 sm:px-4 min-w-0 max-[359px]:order-3 max-[359px]:basis-full max-[359px]:mt-3"',
    );
  });

  it("spreads the pair across that row so each figure sits under its own team", () => {
    expect(pair).toContain(
      'className="flex items-baseline max-[359px]:w-full max-[359px]:[&>:first-child]:ml-auto max-[359px]:[&>:last-child]:mr-auto"',
    );
    expect(pair).toContain(
      'className="text-lg font-light text-text-muted mx-1.5 self-center max-[359px]:mx-auto max-[359px]:invisible"',
    );
  });

  it("keeps the numeral sizes — the reflow buys room, it does not shrink the chances", () => {
    const numeral =
      'className="text-[34px] min-[360px]:text-[42px] min-[390px]:text-[48px] sm:text-[52px] font-black tracking-tight leading-none tabular-nums"';
    expect(pair.split(numeral)).toHaveLength(3);
  });

  it("scopes every reflow class to below 360px, so 360 and up keep the three-column anatomy", () => {
    const reflow = /(?<![\w\]:-])(flex-wrap|basis-1\/2|basis-full|order-[123]|invisible|w-full)(?![\w-])/g;
    const heroRow = page.slice(
      page.indexOf('justify-between max-[359px]:flex-wrap'),
      page.indexOf('max-[359px]:order-2"') + 'max-[359px]:order-2"'.length,
    );
    expect(heroRow.length).toBeGreaterThan(0);
    const pairBlock = pair.slice(pair.indexOf('max-[359px]:w-full'), pair.lastIndexOf("</div>"));
    for (const block of [heroRow, pairBlock]) {
      const unscoped = [...block.matchAll(reflow)].filter(
        (m) => !block.slice(Math.max(0, m.index! - 12), m.index).endsWith("max-[359px]:"),
      );
      expect(unscoped.map((m) => m[0])).toEqual([]);
    }
  });
});
