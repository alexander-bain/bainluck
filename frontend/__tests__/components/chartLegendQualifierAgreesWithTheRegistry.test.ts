/**
 * live/076 — #3563: THE CHART LEGEND'S QUALIFIER AGREES WITH THE REGISTRY'S
 * NOUN, WHATEVER NUMBER THAT NOUN IS.
 *
 * Measured on production 2026-09-06, under the plot on
 * `https://bainluck.com/events/15305578` (Cerundolo v Blockx), in the
 * sportsbooks-only legend, at 390px and again at desktop width:
 *
 *     ── Sportsbooks        ── Each sportsbooks
 *
 * `OddsChart` composed the second entry as
 * `Each {sourceLabel("betting").toLowerCase()}`, and the registry's noun for
 * that supplier is the plural "Sportsbooks" — so the two halves made a
 * non-sentence on every sportsbooks-only event page.
 *
 * ## What this guard pins, and what it deliberately does not
 *
 * It does NOT pin the sentence. Pinning the string would freeze a copy call and
 * would have been just as green the day before the bug was filed, because the
 * old string was also exactly what the old code produced.
 *
 * What it pins is the COMPOSITION — that the qualifier agrees with no number,
 * so it survives a registry that holds labels of both ("Sportsbooks" beside
 * "Kalshi", "DataGolf", "Bain Luck Model"). That is the property the defect
 * actually violated, and it is the one a future registry edit can silently
 * break again. `Each of the {label}` would fix the screen today and fail this
 * guard, correctly: it only reads while the noun stays plural.
 *
 * ## Two arms
 *
 * The **library arm** proves the rule on the composer. The **source arm**
 * proves the page spends it — a pure function nothing renders is the classic
 * way this class of fix passes its own test and changes nothing on screen.
 * `OddsChart` is Recharts and server-renders to an empty box (the constraint
 * established by `eventChartLabelling.test.tsx`), so the legend cannot be
 * rendered here; the scan therefore RAISES if it cannot find the block it is
 * checking, because a source guard that silently matches nothing is how a
 * renamed variable turns this file green by making it vacuous.
 */

import { readFileSync } from "fs";
import { join } from "path";

import { SOURCE_COLORS, separateLinesLabel, sourceLabel } from "@/lib/sourceColors";

/**
 * Words that only read correctly in front of a noun of one particular number.
 * "Each"/"every"/"a"/"an" demand a singular; "all" and "individual" demand a
 * plural. The defect was the first of these; "Individual sportsbooks" was
 * #2442's original defect on this very legend, so both directions are barred.
 */
const NUMBER_AGREEING_DETERMINERS = ["each", "every", "all", "individual", "a", "an"];

describe("#3563 — the separate-lines qualifier agrees with no number", () => {
  /** The defect itself, on the source it was measured on. */
  it("no longer reads 'Each sportsbooks' for the sportsbook supplier", () => {
    const phrase = separateLinesLabel("betting");

    expect(phrase.toLowerCase()).not.toContain("each sportsbooks");
    expect(phrase).toBe("Sportsbooks, separately");
  });

  /**
   * The property, over the whole registry rather than the one source that
   * happened to be filed. Every label the registry holds — of either number —
   * must compose into a phrase that leads with the label EXACTLY as the
   * registry spells it (#2442: one name per supplier, not a re-cased second
   * spelling of it) and carries no word that agrees with a number.
   */
  it("composes every registry label without a determiner and without re-spelling it", () => {
    const keys = Object.keys(SOURCE_COLORS);
    // A registry that has stopped holding sources would make every assertion
    // below vacuously true.
    expect(keys.length).toBeGreaterThan(5);

    for (const key of keys) {
      const label = sourceLabel(key);
      const phrase = separateLinesLabel(key);

      // Leads with the registry's own spelling, untouched.
      expect(phrase.startsWith(label)).toBe(true);
      expect(phrase).not.toBe(label);

      // Nothing in the words this function ADDS may agree with a number. Only
      // the added tail is checked — a registry label is free to contain any
      // word it likes ("Per-Bookmaker (Odds API)").
      const added = phrase.slice(label.length);
      for (const determiner of NUMBER_AGREEING_DETERMINERS) {
        expect(added.toLowerCase().split(/[^a-z]+/)).not.toContain(determiner);
      }
    }
  });

  /**
   * The number-agnosticism made concrete: the same composer over a singular
   * noun and a plural one produces two phrases that are both grammatical, and
   * differ ONLY by the noun. `Each of the {label}` fails this pair.
   */
  it("reads for a singular noun and a plural noun alike", () => {
    expect(separateLinesLabel("kalshi")).toBe("Kalshi, separately");
    expect(separateLinesLabel("odds_api")).toBe("Sportsbooks, separately");

    const tail = (key: string) =>
      separateLinesLabel(key).slice(sourceLabel(key).length);
    expect(tail("kalshi")).toBe(tail("odds_api"));
  });

  /** It inherits the registry's fallback path, so a source the registry has
   *  never heard of is still named rather than left blank. */
  it("falls through to the payload's name for an unknown source", () => {
    expect(separateLinesLabel("pinnacle_model", "Pinnacle Model")).toBe(
      "Pinnacle Model, separately"
    );
  });
});

describe("#3563 — and the chart spends it", () => {
  const SOURCE = readFileSync(
    join(__dirname, "../../components/OddsChart.tsx"),
    "utf8"
  );

  it("uses the composer in the sportsbooks-only legend", () => {
    // RAISE rather than pass if the block moved — see the file header.
    const legend = SOURCE.indexOf("{/* Bookmaker legend (sportsbooks-only mode) */}");
    const nextLegend = SOURCE.indexOf("{/* Lead changes legend", legend);
    if (legend < 0 || nextLegend < 0) {
      throw new Error(
        "sportsbooks-only bookmaker legend not found in OddsChart — this guard " +
          "cannot check what it cannot locate; find the block and re-anchor it."
      );
    }
    // Bounded by the NEXT legend entry: a window that runs past this block
    // reads its neighbours' code and reports their strings as this one's.
    const block = SOURCE.slice(legend, nextLegend);

    // The RENDERED text only. The block's comment quotes the old composition
    // verbatim, on purpose, so a scan over the whole block would match the
    // history lesson and call it the defect.
    const rendered = block.slice(block.indexOf("<span"));
    expect(rendered).toContain('{separateLinesLabel("betting")}');

    // The old composition, gone from what renders: a determiner interpolated
    // in front of the registry's noun, and the lowercasing that re-spelled it.
    expect(rendered).not.toContain(".toLowerCase()");
    expect(rendered).not.toMatch(/Each\s*\{/);
  });

  it("imports the composer it renders", () => {
    expect(SOURCE).toContain("separateLinesLabel");
    expect(SOURCE).toMatch(/import \{[^}]*separateLinesLabel[^}]*\} from "@\/lib\/sourceColors"/);
  });
});
