/**
 * #6761 — a bout we hold no price for stops drawing a 50/50 bar.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `TwoSidedTimeline` prints the two probabilities honestly: `formatProbability(null)` is `"-"`.
 * The split bar underneath was computed from `aPct`, which fell back to **50** on a null
 * probability — so a bout with no price rendered a clean, even, two-colour bar, pixel-identical
 * to a genuinely 50/50 priced bout, directly beneath two dashes. One state, two surfaces, and
 * the louder one was inventing the number the quieter one declined to give.
 *
 * Routed by discover/156 with production captures at 390px. Rare today; #2602 (venue-listed
 * fight cards) makes it the common case — 11 of 11 bouts on UFC Fight Night 26 Sep, 4 of 5 on
 * Dana White's Contender Series. The line predates #2602 and this is not a regression of it.
 *
 * ═══ WHAT IS GUARDED ═══
 *
 * Three states:
 *
 *   both priced      → bar, split at a's price
 *   NEITHER priced   → NO BAR (the ship)
 *   only ONE priced  → bar, split at the price we hold — the bar is NOT dropped
 *
 * 🪤 The third case needs no code of its own, and an earlier version of this file "proved" a
 * `100 - b` fallback that could never run. `fieldOrder` sorts on `probability ?? -1` descending,
 * so a priced competitor always sorts ahead of an unpriced one and the priced side IS `a`. The
 * test below pins the ORDERING fact, because that is what makes the one-line fix complete: if
 * the sort ever stopped pushing nulls last, `aPct` would start withholding a bar on a bout we
 * do have a price for, and nothing else in the file would notice.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("swr", () => ({ __esModule: true, default: () => ({ data: undefined }) }));
jest.mock("@/components/FuturesChart", () => ({
  __esModule: true,
  FuturesChart: () => null,
}));
jest.mock("../../components/event/FighterAvatar", () => ({
  __esModule: true,
  default: () => null,
}));

import TwoSidedTimeline from "../../components/event/TwoSidedTimeline";

type Competitor = { name: string; probability: number | null };

function render(a: Competitor, b: Competitor): string {
  return renderToStaticMarkup(
    <TwoSidedTimeline
      // `fieldOrder` sorts the pair; both arms carry the fields it reads.
      competitors={[a, b] as never}
      label="Head to head"
      evolutionMarketId={null}
    />,
  );
}

/** The split bar, addressable since #6761 so a guard can tell "no bar" from "bar off-screen". */
const BAR = 'data-testid="two-sided-split-bar"';

/** Every `width:N%` in the markup, in order — the split the reader actually sees. */
function widths(html: string): string[] {
  return Array.from(html.matchAll(/width:\s*([\d.]+)%/g)).map((m) => m[1]);
}

describe("#6761 — the split bar never invents a price", () => {
  test("BOTH priced: the bar is drawn and split at the a-side price", () => {
    const html = render({ name: "Alpha", probability: 0.68 }, { name: "Beta", probability: 0.32 });
    expect(html).toContain(BAR);
    expect(widths(html)).toEqual(["68", "32"]);
  });

  test("🔴 NEITHER priced: NO BAR AT ALL — this is the defect", () => {
    const html = render({ name: "Alpha", probability: null }, { name: "Beta", probability: null });
    expect(html).not.toContain(BAR);
    // Nothing draws a 50/50 anywhere on the section.
    expect(widths(html)).toEqual([]);
    // And the honest dashes above it survive — the fix withholds the bar, not the row.
    expect(html).toContain("-");
  });

  test.each([
    ["the unpriced side passed first", null, 0.8, ["80", "20"]],
    ["the unpriced side passed second", 0.8, null, ["80", "20"]],
  ] as [string, number | null, number | null, string[]][])(
    "only ONE side priced (%s): the bar survives, split at the price we hold",
    (_label, pa, pb, expected) => {
      const html = render({ name: "Alpha", probability: pa }, { name: "Beta", probability: pb });
      // Withholding here would throw away a price we actually have.
      expect(html).toContain(BAR);
      expect(widths(html)).toEqual(expected);
    },
  );

  test("the ORDERING fact the one-line fix rests on: a priced side always sorts first", () => {
    // `aPct` reads only `a`. That is complete ONLY because `fieldOrder` puts nulls last, so
    // `a.probability == null` implies both sides are unpriced. Pin it here: if this flips, the
    // component starts withholding the bar from half-priced bouts and no other test can see it.
    const { fieldOrder } = jest.requireActual("../../lib/eventConceptDisplay");
    const sorted = fieldOrder([
      { name: "Unpriced", probability: null },
      { name: "Priced", probability: 0.4 },
    ]);
    expect(sorted.map((c: { name: string }) => c.name)).toEqual(["Priced", "Unpriced"]);
  });

  test("the unpriced case is not confused with a real 50/50", () => {
    // The whole complaint is that these two rendered identically. They must not now.
    const even = render({ name: "Alpha", probability: 0.5 }, { name: "Beta", probability: 0.5 });
    const unpriced = render({ name: "Alpha", probability: null }, { name: "Beta", probability: null });
    expect(widths(even)).toEqual(["50", "50"]);
    expect(even).toContain(BAR);
    expect(unpriced).not.toEqual(even);
  });
});
