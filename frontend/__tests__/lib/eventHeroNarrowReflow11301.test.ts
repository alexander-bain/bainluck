// #11301 (Direction 199 unified headline) — BELOW 360px COMPETITOR ROWS REFLOW CLEANLY.
//
// On `EventPageHeadline199.tsx`, each competitor row keeps its single-line table
// anatomy at 360px and up, and below 360px (`max-[359px]:*`) wraps the crest +
// name stack onto a full-width top line (`max-[359px]:basis-full`) with the
// right-aligned numeric columns beneath (`max-[359px]:ml-auto`), matching iOS
// `stacksRowsVertically` at `.accessibility2` Dynamic Type.

import fs from "fs";
import path from "path";

const HEADLINE = path.resolve(
  __dirname,
  "../../components/event/EventPageHeadline199.tsx",
);
const PAIR = path.resolve(__dirname, "../../components/EventHeroProbabilityPair.tsx");

function executableSource(file: string): string {
  return fs
    .readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|\s)\/\/.*$/, "$1"))
    .join("\n");
}

describe("#11301 the event headline reflows below 360px instead of colliding", () => {
  const headline = executableSource(HEADLINE);
  const pair = executableSource(PAIR);

  it("lets each competitor row wrap below 360px only", () => {
    expect(headline).toContain(
      'className="flex items-center justify-between gap-2 min-w-0 max-[359px]:flex-wrap"',
    );
  });

  it("gives the identity stack full width below 360px and right-aligns the numeric strip beneath it", () => {
    expect(headline).toContain(
      'className="flex items-center gap-2 min-w-0 flex-1 max-[359px]:basis-full"',
    );
    expect(headline).toContain(
      'className="flex items-baseline shrink-0 max-[359px]:ml-auto"',
    );
  });

  it("keeps EventHeroProbabilityPair's own narrow reflow intact", () => {
    expect(pair).toContain(
      'className="flex items-baseline max-[359px]:w-full max-[359px]:[&>:first-child]:ml-auto max-[359px]:[&>:last-child]:mr-auto"',
    );
  });
});
