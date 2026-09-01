// #1602 (UX-P034): SSR guard for the matchups-&-props rail.
//
// The pure classifier is covered in __tests__/lib/matchupFamilies.test.ts. This
// asserts the RAIL actually consumes it — that a large field renders collapsed
// family headers instead of one flat grid, that every card is still in the
// document, and (the other direction of gotcha #43) that a normal-sized card
// renders exactly the flat grid it renders today, with no headers added.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import MatchupsRail from "@/components/event/MatchupsRail";
import type { EventConceptChild } from "@/lib/types";

const child = (market_name: string, probability = 0.55): EventConceptChild => ({
  market_id: Math.abs(hash(market_name)),
  market_name,
  probability,
  outcomes: [
    { name: `${market_name} A`, probability },
    { name: `${market_name} B`, probability: 1 - probability },
  ],
});

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return h;
}

/** The tennis shape in miniature: several families, well over the threshold. */
const BIG_FIELD: EventConceptChild[] = [
  ...Array.from({ length: 40 }, (_, i) => child(`Open: Player ${i} vs Rival ${i}`)),
  ...Array.from({ length: 20 }, (_, i) => child(`Open: Completed Match: P${i} vs R${i}`)),
  ...Array.from({ length: 12 }, (_, i) => child(`P${i} vs R${i}: Total Games`)),
  ...Array.from({ length: 6 }, (_, i) => child(`P${i} vs R${i}: Set 1 Winner`)),
];

/** A UFC card: 12 live bouts, one family. */
const SMALL_CARD: EventConceptChild[] = Array.from({ length: 12 }, (_, i) =>
  child(`Fighter ${i} vs Opponent ${i}`),
);

describe("MatchupsRail — a large field is bounded into family groups", () => {
  const html = renderToStaticMarkup(<MatchupsRail items={BIG_FIELD} />);

  it("renders a collapsed <details> header per family, with its count", () => {
    expect(html).toContain("Match winners (40)");
    expect(html).toContain("Completed matches (20)");
    expect(html).toContain("Combined score (12)");  // #2442: was "Game totals"
    expect(html).toContain("Set winners (6)");
  });

  it("opens none of them — no lead family, so no invented ranking", () => {
    // renderToStaticMarkup emits `open=""` for an open <details>. There should
    // be none among the family groups.
    expect(html).not.toContain("<details open");
  });

  it("still contains every card — grouping hides, it never drops", () => {
    for (const c of BIG_FIELD) {
      expect(html).toContain(c.market_name!);
    }
  });

  it("does not render the live cards as one flat grid", () => {
    // The old shape was a single grid div holding all 78. Each family now owns
    // its own grid, so there are as many grids as families.
    const grids = html.split("lg:grid-cols-3").length - 1;
    expect(grids).toBe(4);
  });
});

describe("MatchupsRail — a normal card is untouched (gotcha #43, other direction)", () => {
  const html = renderToStaticMarkup(<MatchupsRail items={SMALL_CARD} />);

  it("adds no family headers", () => {
    expect(html).not.toContain("Match winners (");
    expect(html).not.toContain("Other markets (");
  });

  it("renders one flat grid holding every bout", () => {
    expect(html.split("lg:grid-cols-3").length - 1).toBe(1);
    for (const c of SMALL_CARD) expect(html).toContain(c.market_name!);
  });

  it("keeps the section heading and the empty state", () => {
    expect(html).toContain("Matchups &amp; props");
    expect(renderToStaticMarkup(<MatchupsRail items={[]} />)).toBe("");
  });
});

describe("MatchupsRail — the settled tail groups too", () => {
  // 744 settled cards on the live tennis page: collapsed it costs no height,
  // but opening it would be the identical wall one click in.
  const settled: EventConceptChild[] = [
    ...Array.from({ length: 30 }, (_, i) => child(`Open: Done ${i} vs Rival ${i}`, 0.99)),
    ...Array.from({ length: 10 }, (_, i) => child(`D${i} vs R${i}: Total Games`, 0.99)),
  ];
  const html = renderToStaticMarkup(<MatchupsRail items={settled} />);

  it("keeps the Completed disclosure and groups inside it", () => {
    expect(html).toContain("Completed (40)");
    expect(html).toContain("Match winners (30)");
    expect(html).toContain("Combined score (10)");  // #2442: was "Game totals"
  });
});
