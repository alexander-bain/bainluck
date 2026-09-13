// #5866 — THE EVENT HERO'S CENTRE COLUMN MAY SHRINK, AND THE ROW MUST NOT BE
// SET BY IT.
//
// ═══ WHAT THIS FILE CAN AND CANNOT SEE ═══
//
// It CANNOT see the defect. The defect is geometric — at 320px on production
// the away crest's right edge sat 28.5px past the viewport, clipped rather than
// scrollable — and a test that reads class names cannot measure a layout. That
// instrument is `tools/hero-clip-probe.mjs`, which drives a real browser,
// reports `headroomPx` / `awayOffscreenPx`, and exits non-zero when the away
// column does not fit. It is in the repo for the same reason this file is not
// enough: run it, do not infer.
//
// What this file DOES pin is the decision, so a revert is loud. `app/events/[id]/page.tsx`
// has no render harness (see `sportsFinishedWiring.test.ts` for the same
// constraint on /sports), and the whole change is three class edits whose
// absence is invisible to every other test in the suite: the row's middle child
// stops being `flex-shrink-0`, and the two lines that can be the widest one
// gain `min-w-0` so they wrap instead of setting the column's width.
//
// Comments are stripped first: this file's own docblock names every class
// below, and the docblocks in the page name them too, so an unstripped scan
// would pass on a page whose JSX had been reverted and whose comment still
// described the fix.

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

describe("#5866 the hero's centre column does not dictate the row", () => {
  test("the centre column is shrinkable, and is no longer flex-shrink-0", () => {
    const code = executableSource(PAGE);
    // The centre column, by its own class list. `flex-shrink-0` here is the
    // defect: it pinned the column at its max-content width and left
    // `justify-between` to push the excess onto the away crest.
    expect(code).toMatch(
      /className="flex flex-col items-center px-1 sm:px-4 min-w-0"/,
    );
    expect(code).not.toMatch(
      /className="flex flex-col items-center px-2 sm:px-4 flex-shrink-0"/,
    );
  });

  test("the two widest lines may shrink, and the arrow beside one of them may not", () => {
    const code = executableSource(PAGE);
    // `+N pts <team> since open` — the line that is widest on a long club name,
    // and the one live/193 measured on the K League hero.
    expect(code).toMatch(/className="flex items-center gap-1\.5 mt-2 min-w-0"/);
    expect(code).toMatch(/w-3\.5 h-3\.5 flex-shrink-0/);
    // The source label line, same treatment.
    expect(code).toMatch(/className="mt-1 flex items-center gap-1\.5 min-w-0"/);
  });

  test("the giant pair steps down below 360px, and only below 360px", () => {
    const code = executableSource(PAIR);
    // A shrinkable column holding a pair that cannot wrap overlaps its
    // neighbours instead of pushing them off-screen — measured at 320px, "81"
    // printed across the Chargers crest. 390 and up must not move.
    const sized = code.match(
      /text-\[34px\] min-\[360px\]:text-\[48px\] sm:text-\[52px\]/g,
    );
    expect(sized).toHaveLength(2);
    expect(code).not.toMatch(/"text-\[48px\] sm:text-\[52px\]/);
  });
});
