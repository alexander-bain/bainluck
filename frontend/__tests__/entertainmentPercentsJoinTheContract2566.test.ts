/**
 * #2566 — /ENTERTAINMENT NEVER ADOPTED THE PERCENT CONTRACT.
 *
 * Three reader-visible defects, one file, two functions, one cause: the page has
 * its own `ProbPct` and `YesNoBar` and neither ever called the shared helpers.
 * It is the next named site in the open census #3892, and the browse hubs took
 * the same medicine two days earlier in #6233.
 *
 * Seen on production 2026-09-16 at 390px (discover/140 shop, notice 21 / D48):
 *
 *   1. #2566 itself — the YES label was painted INSIDE the fill, which is a flex
 *      item whose width is the probability, inside a 28px `overflow: hidden`
 *      track. "Puka Nacua and Sara Saffari: Engaged in 2026?" and "Will Dune:
 *      Part Three be delayed?" both drew `YES 2%` as `YI` over `2%`, cut
 *      mid-glyph. Filed 2026-09-01 against desktop 1280w; still live, and worse
 *      at phone width because the track is narrower.
 *
 *   2. The bar printed 101%. `YesNoBar` is handed `no = 100 - prob`, an exact
 *      complement, and rounded each side on its own.
 *
 *   3. `ProbPct` was `Math.round(value)`, so a real price printed `0%`.
 *
 * ## Measured on `GET /api/entertainment`, 2026-09-16
 *
 *   511 outcome rows rendered through `ProbPct`
 *     9 nonzero rows printing `0%`                      <- defect 3
 *     0 other integers move when the contract is adopted <- the blast radius
 *    18 binary cards rendered through `YesNoBar`
 *     4 of them (22%) printing 101                       <- defect 2
 *
 * ## What these guards are for
 *
 * Each arm pins a direction where a plausible wrong fix passes: the four real
 * 101s total 100, an off-band pair is NOT forced to 100 (gotcha #23), the 502
 * rows that were already right are byte-identical, the boundary markers survive
 * the pair rule rather than being overwritten by it, and — for the clipping —
 * the fill carries the width while the labels do not, which is the whole of the
 * layout fix and the only part a number cannot assert.
 */
import fs from "fs";
import path from "path";

import { formatProbability } from "@/lib/api";
import { probabilityParts } from "@/lib/probabilityDisplay";
import { renderedDuelPercents } from "@/lib/renderedPercent";

/**
 * `YesNoBar`'s rule, extracted exactly as the page applies it — including the
 * `/100`, because this page's wire is a PERCENT and the contract takes a
 * probability. A paraphrase that skipped the divide would pass while the page
 * fed the helper a 3.5 and got nonsense.
 */
function printedBar(yesPercent: number): [string, string] {
  const noPercent = 100 - yesPercent;
  const [yesPct, noPct] = renderedDuelPercents(yesPercent / 100, noPercent / 100);
  return [
    formatProbability(yesPercent / 100, { rendered: yesPct }),
    formatProbability(noPercent / 100, { rendered: noPct }),
  ];
}

const integerSum = (printed: string[]) =>
  printed.reduce((t, s) => t + (s.endsWith("%") ? parseInt(s.replace(/[^0-9]/g, ""), 10) : 0), 0);

/** `ProbPct`'s rule, same extraction. */
const printedRow = (percent: number) => {
  const { marker, digits } = probabilityParts(percent / 100);
  return `${marker ?? ""}${digits}%`;
};

describe("#2566 the four binary cards a reader saw printing 101", () => {
  /**
   * The served YES prices behind the four cards, read off `/api/entertainment`
   * on the same load as the screenshots. Every one is a half-cent quote, which
   * is why both sides rounded up at once.
   */
  it.each([
    ["PBD Podcast reaches 10M subscribers", 3.5, "3%", "97%"],
    ["MrBeast reaches 600M subscribers", 5.5, "5%", "95%"],
    ["Elon Musk visits Mars in his lifetime", 10.5, "10%", "90%"],
    ["Dantes banned from Twitch this year", 12.5, "12%", "88%"],
  ])("%s totals 100, not 101", (_name, yes, expectedYes, expectedNo) => {
    expect(printedBar(yes as number)).toEqual([expectedYes, expectedNo]);
    expect(integerSum(printedBar(yes as number))).toBe(100);
  });

  it("per-side rounding really did total 101 — the defect, stated", () => {
    // What the bar did before this change, on the first of the four.
    expect(Math.round(3.5) + Math.round(96.5)).toBe(101);
  });

  /**
   * The FAVOURITE is the side that survives, not whichever side is drawn first.
   * YES and NO sit in fixed positions here, so rounding the left side and
   * deriving the right would make a 3.5% YES print `4% / 96%` — an answer that
   * depends on which side the layout happens to put first, which is exactly why
   * #2831 routes fixed-position pairs through the duel helper.
   */
  it("the favourite survives rounding, not the left-hand side", () => {
    expect(printedBar(3.5)[0]).toBe("3%");
    expect(printedBar(96.5)[1]).toBe("3%");
  });
});

describe("#2566 the bar only moves the cards that were wrong", () => {
  /**
   * 14 of the 18 binary cards already totalled 100. A fix that renormalises
   * everything would move numbers on cards no reader ever saw break.
   */
  it.each([
    ["a 2% YES — the clipped specimen", 2, "2%", "98%"],
    ["a 97% YES", 97, "97%", "3%"],
    ["an even market", 50, "50%", "50%"],
    ["a 6.7% YES", 6.7, "7%", "93%"],
  ])("%s is unchanged", (_name, yes, expectedYes, expectedNo) => {
    expect(printedBar(yes as number)).toEqual([expectedYes, expectedNo]);
  });

  /**
   * gotcha #23 — `renderedDuelPercents` self-gates on the [0.99, 1.01] band, so
   * two independent binaries are never normalised into a pair. This caller's
   * pair is an exact complement by construction, so the guard is about the
   * helper staying the helper: swapping in a plain `100 - round(yes)` would pass
   * every case above and silently claim a total on a pair that has none.
   */
  it("an off-band pair keeps its own total", () => {
    const [a, b] = renderedDuelPercents(0.62, 0.475);
    expect([a, b]).toEqual([62, 48]);
  });
});

describe("#2566 the boundary rule composes with the pair rule", () => {
  /**
   * UX-P046 runs on the PROBABILITY, not on the integer the pair rule chose, so
   * a 0.4% YES prints `<1%` rather than the `0%` it would have printed before —
   * and its NO side prints `>99%` rather than claiming certainty. Neither rule
   * outranks the other; a fix that computed the pair and then formatted with a
   * bare template would lose both markers.
   */
  it("a sub-point YES prints <1% and its NO prints >99%", () => {
    expect(printedBar(0.4)).toEqual(["<1%", ">99%"]);
  });

  it("the rows a market really has priced at zero still print 0%", () => {
    // Exact zero IS the boundary, so it is printed plainly (probabilityDisplay).
    expect(printedRow(0)).toBe("0%");
  });
});

describe("#2566 the nine rows that printed 0% over a real price", () => {
  /**
   * The served specimens, all nine of them, from the same load. The first is the
   * top card on the page — "Which movie has biggest opening weekend in 2026?" —
   * whose third row is a film the market is actively pricing.
   */
  it.each([
    ["The Hunger Games: Sunrise on the Reaping (trending)", 0.1],
    ["Billboard 200 rank 13-15", 0.2],
    ["Billboard 200 rank 10-12", 0.1],
    ["Billboard 200 rank <10", 0.1],
    ["You Seem Pretty Sad for a Girl So in Love", 0.3],
    ["The Weeknd", 0.2],
    ["Morgan Wallen", 0.1],
    ["The Hunger Games: Sunrise on the Reaping (box office)", 0.1],
    ["a hundredth of a point", 0.01],
  ])("%s prints <1%%, not 0%%", (_name, percent) => {
    expect(printedRow(percent as number)).toBe("<1%");
    expect(printedRow(percent as number)).not.toBe("0%");
  });

  /**
   * THE BLAST RADIUS, PINNED. 502 of the 511 rows must render exactly as they
   * did. These are the values the page actually carries at each shape.
   */
  it.each([53, 47, 54, 12, 98, 27, 86, 2.1, 93.5, 65.5, 7.2, 99, 100])(
    "%s%% is byte-identical to what the page printed before",
    (percent) => {
      expect(printedRow(percent)).toBe(`${Math.round(percent)}%`);
    },
  );
});

describe("#2566 the page is actually wired to the rules", () => {
  /**
   * 🔴 THE LIMIT OF THIS ARM, STATED. Everything above exercises the real
   * helpers, and none of it proves this page calls them — which is exactly the
   * shape that let all three defects ship, since the rules have existed since
   * #2831 / UX-P046 and these two components simply never used them. `ProbPct`
   * and `YesNoBar` are file-local to a Next.js page module and are not exported;
   * exporting them purely to be testable would widen the module's surface for
   * the test's convenience. So this arm reads the SOURCE and says so, following
   * #6233's precedent on the hub page.
   */
  const PAGE = fs.readFileSync(
    path.join(__dirname, "..", "app", "entertainment", "page.tsx"),
    "utf8",
  );
  const CSS = fs.readFileSync(
    path.join(__dirname, "..", "app", "entertainment", "entertainment.module.css"),
    "utf8",
  );

  it("the bare per-side rounding — the defect itself — is gone", () => {
    expect(PAGE).not.toMatch(/YES \{Math\.round/);
    expect(PAGE).not.toMatch(/NO \{Math\.round/);
    expect(PAGE).not.toMatch(/\{Math\.round\(value\)\}/);
  });

  it("ProbPct prints through the UX-P046 split seam", () => {
    expect(PAGE).toMatch(/probabilityParts\(value \/ 100\)/);
  });

  it("the bar decides both sides together", () => {
    expect(PAGE).toMatch(/renderedDuelPercents\(yes \/ 100, no \/ 100\)/);
    expect(PAGE).toMatch(/formatProbability\(yes \/ 100, \{ rendered: yesPct \}\)/);
    expect(PAGE).toMatch(/formatProbability\(no \/ 100, \{ rendered: noPct \}\)/);
  });

  /**
   * THE CLIPPING FIX, WHICH NO NUMBER CAN ASSERT. The label may not live in a box
   * whose width is the probability. So: the width goes on the fill and on nothing
   * else, and the fill is positioned out of flow so the labels size to their text.
   */
  it("the width is on the fill, and the labels carry none", () => {
    expect(PAGE).toMatch(/className=\{s\.ynFill\} style=\{\{ width: `\$\{yes\}%` \}\}/);
    expect(PAGE).not.toMatch(/s\.ynYes\} style=\{\{ width/);
    expect(PAGE).not.toMatch(/s\.ynNo\} style=\{\{ width/);
  });

  it("the fill is a layer behind the labels, and the labels cannot wrap", () => {
    const fill = CSS.match(/\.ynFill \{[^}]*\}/)?.[0] ?? "";
    expect(fill).toMatch(/position: absolute/);
    for (const cls of [".ynYes", ".ynNo"]) {
      const block = CSS.match(new RegExp(`\\${cls} \\{[^}]*\\}`))?.[0] ?? "";
      expect(block).toMatch(/white-space: nowrap/);
      expect(block).toMatch(/position: relative/);
    }
    // The track, not the YES span, now carries the unfilled colour.
    expect(CSS.match(/\.ynBar \{[^}]*\}/)?.[0] ?? "").toMatch(/background: #F0F0F2/);
  });
});
