// UX-P161 — the golf field stops telling a reader a live golfer has no chance.
//
// ## The defect, measured rather than assumed
//
// UX-P046 established the rule once — "rounding may never move a probability
// across a boundary it is not on", so a value strictly inside (0, 1) may never
// print `0%` — and put it in `formatProbabilityPercent`. The golf category page
// never adopted it. Every printed probability there was its own
// `Math.round(p * 100)`, and `TournamentCard` used a THIRD idiom,
// `(p * 100).toFixed(0)`.
//
// Measured on production 2026-08-29, `GET /api/golf`: the Rogers Charity Classic
// field is 15 named PGA Tour Champions professionals — Billy Andrade, K.J. Choi,
// Scott McCarron — each carrying a real Kalshi probability of 0.003, and the
// tournament detail list printed `0%` on all 15. The page ranks them 1 through
// 15 and then tells the reader every single one is impossible. That is
// UX-P046's own specimen pathology ("that card tells a reader nothing, and what
// little it does say is false") on a named category surface.
//
// ## Why this file renders instead of checking the rule
//
// `probabilityDisplay.test.ts` already proves `formatProbability` returns `<1%`,
// and it stayed green for the entire time this page printed `0%`. A pure-lib
// assertion cannot see a render, so every assertion below drives
// `renderToStaticMarkup` over the SHIPPED `GolferRow`, and the plants at the
// bottom prove the assertions can fail.
//
// ## The entity trap
//
// `renderToStaticMarkup` escapes the two strings this rule exists to produce:
// `<1%` serialises as `&lt;1%` and `>99%` as `&gt;99%`. Asserting on the raw
// glyphs would pass vacuously against markup that never contained them, so
// every assertion goes through `text()` below.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { GolfGolfer, GolfTournament } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/categories/golf",
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { GolferRow } from "@/components/golf/GolferRow";
import TournamentCard from "@/components/TournamentCard";

/** Rendered markup with the entities this rule's own output produces decoded. */
function text(el: React.ReactElement): string {
  return renderToStaticMarkup(el)
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

const golfer = (over: Partial<GolfGolfer> = {}): GolfGolfer => ({
  name: "K.J. Choi",
  probability: 0.003,
  american_odds: null,
  opening_probability: null,
  movement_24h: null,
  rank: 6,
  sources: { kalshi: 0.003 },
  ...over,
});

const row = (g: GolfGolfer, showSourceBreakdown = false) =>
  text(
    <GolferRow
      golfer={g}
      tournamentKey="rogers-charity-classic"
      showSourceBreakdown={showSourceBreakdown}
    />,
  );

describe("UX-P161 — the golf field row honours the probability floor", () => {
  it("prints <1% for the exact production specimen, not 0%", () => {
    // Billy Andrade / K.J. Choi / Scott McCarron, Rogers Charity Classic,
    // 2026-08-29: probability 0.003, single Kalshi source.
    const html = row(golfer());
    expect(html).toContain("<1%");
    expect(html).not.toContain(">0%<");
  });

  it("prints <1% on the per-source breakdown too", () => {
    // The per-source line is the reader's evidence that the number is real. A
    // source that priced this golfer must not be quoted as pricing them at zero.
    const html = row(golfer({ sources: { kalshi: 0.003, polymarket: 0.004 } }), true);
    // Two sources, both sub-1%, plus the row itself.
    expect(html.match(/<1%/g)?.length).toBeGreaterThanOrEqual(3);
    expect(html).not.toContain(": 0%");
  });

  it("still prints a plain 0% for a genuinely zero probability", () => {
    // Zero IS the boundary. The rule is that rounding may not MOVE a value
    // across a boundary, not that `0%` may never appear.
    const html = row(golfer({ probability: 0 }));
    expect(html).toContain("0%");
    expect(html).not.toContain("<1%");
  });

  it("prints >99% rather than a false certainty", () => {
    const html = row(golfer({ probability: 0.996, rank: 1 }));
    expect(html).toContain(">99%");
    expect(html).not.toContain("100%<");
  });

  it("leaves an ordinary mid-field number exactly as it was", () => {
    // Scottie Scheffler, Tour Championship, same production pull: 0.187 -> 19%.
    // The floor must be invisible everywhere it does not apply.
    expect(row(golfer({ name: "Scottie Scheffler", probability: 0.187, rank: 1 })))
      .toContain("19%");
  });

  it("keeps the bar geometry floored at 2%, unchanged by the copy fix", () => {
    // `pct` remains the width. A bar MAY round to nothing — it is geometry, not
    // a claim — and the existing 2% minimum is what keeps the sub-1% row
    // visible at all. Fixing the text must not quietly restyle the page.
    expect(row(golfer())).toContain("width:2%");
    expect(row(golfer({ probability: 0.42 }))).toContain("width:42%");
  });
});

describe("UX-P161 — the tournament card's prop outcomes honour the same floor", () => {
  // `TournamentCard` is the main `/categories/golf` grid AND the Discover
  // tournament card. Its prop-outcome row used a THIRD idiom — `.toFixed(0)` —
  // which floors sub-1% to `0` exactly like the other two. Clean on the
  // 2026-08-29 production pull (4 rendered outcome rows, none sub-1%), so this
  // is the structural half of the fix: guarded before it bites, not after.
  const tournament = {
    key: "the_open",
    slug: "the-open-championship",
    name: "The Open Championship",
    is_major: true,
    schedule_status: "upcoming",
    golfers: [
      { name: "Scottie Scheffler", probability: 0.12, rank: 1, movement_24h: null },
    ],
    market_ids: [6],
    source_count: 2,
    prop_markets: [
      {
        name: "The Open Championship: Hole in One",
        source: "kalshi",
        outcomes: [
          { name: "Yes", probability: 0.004 },
          { name: "No", probability: 0.996 },
        ],
      },
    ],
  } as unknown as GolfTournament;

  it("prints <1% and >99% instead of 0% and 100%", () => {
    const html = text(<TournamentCard tournament={tournament} />);
    expect(html).toContain("<1%");
    expect(html).toContain(">99%");
    expect(html).not.toContain(">0%<");
  });
});

// ── Plants: proof the assertions above can fail ──────────────────────────────
//
// Each reproduces exactly what this page did before the queue, and asserts the
// guard's own predicate rejects it. If `GolferRow` regresses to any of these
// three idioms, the corresponding test above goes red.
describe("UX-P161 plants — the pre-queue idioms are rejected", () => {
  const specimen = 0.003;

  it("the golf page's own Math.round idiom prints the false 0%", () => {
    const printed = `${Math.round(specimen * 100)}%`;
    expect(printed).toBe("0%");
    expect(printed).not.toContain("<1%");
  });

  it("TournamentCard's toFixed(0) idiom prints the same false 0%", () => {
    const printed = `${(specimen * 100).toFixed(0)}%`;
    expect(printed).toBe("0%");
    expect(printed).not.toContain("<1%");
  });

  it("the top-end idiom claims a certainty the value does not have", () => {
    const printed = `${Math.round(0.996 * 100)}%`;
    expect(printed).toBe("100%");
    expect(printed).not.toContain(">99%");
  });
});
