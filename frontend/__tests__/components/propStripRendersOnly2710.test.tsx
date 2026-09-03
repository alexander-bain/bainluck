// UX-P276 / #2710 — THE STRIP MUST PRINT IT, not merely compute it.
//
// `marketCategoryLabel2710` and `propStripAdmission2710` prove the two pure
// rules. Only this file proves the /sports props strip renders them, which is
// the codebase's own standing lesson (#2060): a contract test cannot tell a
// rendered field from a declared one, and wrapping a branch in `{false && (`
// leaves every string intact.
//
// THE FIXTURE IS THE MEASURED SHAPE. `GET /api/futures/grouped-feed?
// sports_only=true&limit=20` on 2026-09-03 returned market rows carrying a raw
// `category` and, among them, rows with `outcomes: []`. Both are reproduced
// verbatim below, because a fixture missing either would prove nothing.
//
// EVERY SELECTOR HERE EXISTS ON THE PARENT. The absence checks key on the raw
// enum string and on "No outcomes available" — both of which master renders —
// rather than on any marker this diff introduces. A population selected by a
// new attribute is vacuously green on the parent (ux/1040), and this file is
// specifically about what master puts on screen.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});
jest.mock("@/components/EntityImage", () => ({
  __esModule: true,
  default: () => null,
}));

import GroupedFeedRenderer from "@/components/GroupedFeedRenderer";
import type { GroupedFeedItem } from "@/lib/types";

function market(
  id: number,
  name: string,
  category: string | null,
  probabilities: Array<number | null>,
): GroupedFeedItem {
  return {
    type: "market",
    market: {
      id,
      name,
      source: "polymarket",
      category,
      sport: "tennis",
      outcomes: probabilities.map((probability, i) => ({
        id: id * 100 + i,
        name: i === 0 ? "Yes" : "No",
        probability,
      })),
    },
  } as GroupedFeedItem;
}

/** A priced card carrying the raw category Alex reported. */
const PRICED_GAME_PROP = market(
  1,
  "Will Aryna Sabalenka advance to the Round of 16?",
  "game_prop",
  [0.92, 0.08],
);
/** The row that rendered "No outcomes available". */
const OUTCOMELESS = market(2, "CFB: Ole Miss vs. LSU", "championship", []);
/** Alex's "every outcome is a dash". */
const ALL_UNPRICED = market(3, "Next Michigan head coach?", "championship", [null, null]);
/** The other three raw enums the live strip carried. */
const PLACEMENT = market(4, "Top 10 Finish", "placement", [0.31, 0.69]);
const MAKE_CUT = market(5, "To Make The Cut", "make_cut", [0.44, 0.56]);

function render(items: GroupedFeedItem[]): string {
  return renderToStaticMarkup(<GroupedFeedRenderer items={items} compact />);
}

/** Count rendered market cards by their titles, which both arms print. */
function renderedTitles(html: string, all: GroupedFeedItem[]): string[] {
  return all
    .map((i) => (i as { market: { name: string } }).market.name)
    .filter((n) => html.includes(n));
}

describe("#2710 — the chip says what the market is, not what the column holds", () => {
  it("prints 'Game Props', and the raw enum is nowhere in the markup", () => {
    const html = render([PRICED_GAME_PROP]);
    expect(html).toContain("Game Props");
    expect(html).not.toContain("game_prop");
  });

  it("humanises every raw enum the live strip carried", () => {
    const html = render([PRICED_GAME_PROP, PLACEMENT, MAKE_CUT]);
    expect(html).toContain("Game Props");
    expect(html).toContain("Placement");
    expect(html).toContain("Makes the Cut");
    for (const raw of ["game_prop", "make_cut"]) {
      expect(html).not.toContain(raw);
    }
  });

  it("CONTROL: the market's own name still renders untouched", () => {
    // Green on the parent too. If this goes red the fixture stopped reaching
    // the card and every absence check above became vacuous.
    const html = render([PRICED_GAME_PROP]);
    expect(html).toContain("Will Aryna Sabalenka advance to the Round of 16?");
  });

  it("CONTROL: a priced card still prints its probability", () => {
    // Green on the parent too — the ship must not disturb what the card shows.
    const html = render([PRICED_GAME_PROP]);
    expect(html).toContain("92%");
  });
});

describe("#2710 — a card with no number is not shown", () => {
  it("never renders 'No outcomes available'", () => {
    const html = render([PRICED_GAME_PROP, OUTCOMELESS]);
    expect(html).not.toContain("No outcomes available");
  });

  it("drops the outcomeless row and keeps the priced one", () => {
    const items = [PRICED_GAME_PROP, OUTCOMELESS];
    const html = render(items);
    expect(renderedTitles(html, items)).toEqual([
      "Will Aryna Sabalenka advance to the Round of 16?",
    ]);
  });

  it("drops an all-unpriced row — Alex's 'Yes —, No —'", () => {
    const items = [PRICED_GAME_PROP, ALL_UNPRICED];
    const html = render(items);
    expect(renderedTitles(html, items)).toEqual([
      "Will Aryna Sabalenka advance to the Round of 16?",
    ]);
  });

  it("a strip of nothing but numberless rows renders the empty state, not bare cards", () => {
    const html = render([OUTCOMELESS, ALL_UNPRICED]);
    expect(html).toContain("No grouped markets found");
    expect(html).not.toContain("No outcomes available");
    expect(html).not.toContain("CFB: Ole Miss vs. LSU");
  });

  it("CONTROL: an all-priced strip loses nothing", () => {
    // Green on the parent too — this is what proves the admission narrows
    // rather than shrinks.
    const items = [PRICED_GAME_PROP, PLACEMENT, MAKE_CUT];
    expect(renderedTitles(render(items), items)).toHaveLength(3);
  });
});
