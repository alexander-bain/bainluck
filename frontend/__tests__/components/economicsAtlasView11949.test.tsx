import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import EconomicsAtlasView, { cleanSource } from "@/components/economics/EconomicsAtlasView";
import { findBannedCopy, JARGON_BANS, visibleTextFromHtml } from "@/lib/copyBans";

describe("EconomicsAtlasView (#11949 Order 9 + #12126/#12128 guards)", () => {
  it("cleanSource preserves a missing or blank source as null and never defaults to 'kalshi'", () => {
    expect(cleanSource(null)).toBeNull();
    expect(cleanSource(undefined)).toBeNull();
    expect(cleanSource("")).toBeNull();
    expect(cleanSource("   ")).toBeNull();
    expect(cleanSource("kalshi")).toBe("kalshi");
    expect(cleanSource("polymarket")).toBe("polymarket");
  });

  it("renders Fed, CPI release, and side markets while refusing blank labels, keeping missing source null, and avoiding banned copy", () => {
    const data: any = {
      total_markets: 5,
      themes: {
        fed: {
          count: 2,
          fomc_meetings: [
            {
              date: "Dec 18, 2026",
              mo: "December",
              dist: [
                [58, "4.25% - 4.50%"],
                [35, "   "],
                [42, "4.00% - 4.25%"],
              ],
              resolved: false,
            },
          ],
          rate_cuts: [
            [45, "2 cuts"],
            [35, "3 cuts"],
          ],
          side_markets: [
            {
              q: "Emergency rate cut in 2026?",
              prob: 12,
              leader: "Yes",
              src: "",
              market_id: 901,
            },
            {
              q: "   ",
              prob: 50,
              leader: "   ",
              src: "",
              market_id: 902,
            },
          ],
        },
        inflation: {
          count: 1,
          cpi_releases: [
            {
              mo: "November CPI",
              q: "Headline CPI YoY (Nov)",
              is_next: true,
              release_at: "2026-12-10T13:30:00Z",
              brackets: [
                [48, "2.5% - 3.0%"],
                [32, ""],
                [52, "2.0% - 2.5%"],
              ],
              src: "",
            },
          ],
          side_markets: [],
        },
        recession: {
          count: 1,
          main_q: "US recession in 2026?",
          main_prob: 24,
          side_markets: [],
          gdp_quarters: [],
        },
      },
    };

    const html = renderToStaticMarkup(
      React.createElement(EconomicsAtlasView, { data })
    );
    expect(html).toContain('data-testid="economics-atlas-view"');
    expect(html).toContain("4.00% - 4.25%");
    expect(html).toContain("4.25% - 4.50%");
    expect(html).toContain("2.0% - 2.5%");
    expect(html).toContain("2.5% - 3.0%");
    expect(html).toContain("Emergency rate cut in 2026?");
    expect(html).not.toContain("/futures/902");

    // Missing source stays null — never defaults to "Kalshi"
    expect(html).not.toMatch(/Kalshi/i);
    // No banned copy ("blend", etc.)
    expect(findBannedCopy(visibleTextFromHtml(html), JARGON_BANS)).toEqual([]);
  });
});
