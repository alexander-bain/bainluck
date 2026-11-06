import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/atlas/AtlasDetailsSheet", () => {
  const actual = jest.requireActual<
    typeof import("@/components/atlas/AtlasDetailsSheet")
  >("@/components/atlas/AtlasDetailsSheet");
  return {
    __esModule: true,
    default: (props: import("@/components/atlas/AtlasDetailsSheet").AtlasDetailsSheetProps) => {
      const forceOpen = Boolean(
        (globalThis as { __FORCE_ATLAS_SHEET_OPEN__?: boolean })
          .__FORCE_ATLAS_SHEET_OPEN__
      );
      return actual.default({ ...props, open: props.open || forceOpen });
    },
  };
});

import PoliticsAtlasView from "@/components/politics/PoliticsAtlasView";
import { ATLAS_STATE_COPY } from "@/components/atlas/atlasStateCopy";
import {
  MidtermsAtlasChamberControl,
  MidtermsAtlasMemberCard,
} from "@/components/collections/MidtermsAtlasSection";
import EconomicsAtlasView from "@/components/economics/EconomicsAtlasView";
import EntertainmentAtlasView from "@/components/entertainment/EntertainmentAtlasView";

describe("#11949 Category Atlas Views (Orders 8–11)", () => {
  afterEach(() => {
    delete (globalThis as { __FORCE_ATLAS_SHEET_OPEN__?: boolean })
      .__FORCE_ATLAS_SHEET_OPEN__;
  });

  it("Chamber control cards with no source field render 'Published source' (never 'Kalshi') and multi-source cards without venue labels render '2 sources'", () => {
    (globalThis as { __FORCE_ATLAS_SHEET_OPEN__?: boolean }).__FORCE_ATLAS_SHEET_OPEN__ =
      true;

    const chamberHtml = renderToStaticMarkup(
      React.createElement(MidtermsAtlasChamberControl, {
        senate: { market_id: 107867, gop: 100, dem: 0, winner: "Republicans" },
        house: { market_id: 107869, gop: 0, dem: 100, winner: "Democrats" },
      })
    );
    expect(chamberHtml).toContain("data-testid=\"atlas-details-attribution\"");
    expect(chamberHtml).toContain("Published source");
    expect(chamberHtml).not.toContain("Kalshi");

    const politicsChamberOnlyHtml = renderToStaticMarkup(
      React.createElement(PoliticsAtlasView, {
        data: {
          total_markets: 2,
          updated_at: "2026-11-05T18:00:00Z",
          themes: {
            presidential: {
              count: 1,
              headline_q: "Who wins the 2028 presidential election?",
              has_dual_source: true,
              kalshi_market_id: 101,
              poly_market_id: 102,
              candidates: [
                { name: "JD Vance", party: "R" as const, kalshi: 31, poly: 29, merged: 30 },
              ],
              side_markets: [],
            },
            congressional: {
              count: 2,
              chamber_control: {
                senate: {
                  market_id: 107867,
                  gop: 100,
                  dem: 0,
                  winner: "Republicans",
                  status: "resolved",
                },
                house: null,
              },
              markets: [],
            },
          },
        } as any,
      })
    );
    expect(politicsChamberOnlyHtml).toContain("Published source");
    expect(politicsChamberOnlyHtml).toContain("2 sources");
    expect(politicsChamberOnlyHtml).not.toContain("Both Kalshi and Polymarket");
    expect(politicsChamberOnlyHtml).not.toContain(">Kalshi<");
  });
  it("PoliticsAtlasView renders settled ✓ Won chamber control, ascending threshold ladders, and retires venue toggles", () => {
    const data = {
      total_markets: 5,
      updated_at: "2026-11-05T18:00:00Z",
      themes: {
        presidential: {
          count: 2,
          headline_q: "Who wins the 2028 presidential election?",
          has_dual_source: true,
          kalshi_market_id: 101,
          poly_market_id: 102,
          candidates: [
            { name: "JD Vance", party: "R" as const, kalshi: 31, poly: 29, merged: 30 },
            { name: "Gavin Newsom", party: "D" as const, kalshi: 21, poly: 19, merged: 20 },
          ],
          side_markets: [],
        },
        congressional: {
          count: 2,
          chamber_control: {
            senate: {
              market_id: 107867,
              gop: 100,
              dem: 0,
              winner: "Republicans",
              status: "resolved",
            },
            house: {
              market_id: 107869,
              gop: 0,
              dem: 100,
              winner: "Democrats",
              status: "resolved",
            },
          },
          markets: [
            {
              market_id: 301,
              q: "How many Senate seats will Republicans hold?",
              prob: 62,
              leader: "Above 52",
              src: "kalshi",
              top_outcomes: [
                { name: "Above 54", prob: 28, rendered_percent: 28 },
                { name: "Above 50", prob: 88, rendered_percent: 88 },
                { name: "Above 52", prob: 62, rendered_percent: 62 },
              ],
            },
          ],
        },
      },
      cross_source: [
        {
          q: "Should never render CrossSourceSpotlight in Atlas view",
          kalshi: 55,
          poly: 50,
          diff: 5,
        },
      ],
    };

    const html = renderToStaticMarkup(
      React.createElement(PoliticsAtlasView, { data: data as any })
    );

    expect(html).toContain("data-testid=\"politics-atlas-view\"");
    expect(html).toContain(">Politics<");
    expect(html).toContain("Chamber control &amp; races");

    // Settled chamber control cards show ✓ Won instead of 100%
    expect(html).toContain("✓ Won");

    // Threshold ladder rungs render in ascending numerical order (Above 50 -> Above 52 -> Above 54)
    expect(html).toContain("data-testid=\"atlas-threshold-ladder\"");
    expect(html.indexOf(">Above 50<")).toBeLessThan(html.indexOf(">Above 52<"));
    expect(html.indexOf(">Above 52<")).toBeLessThan(html.indexOf(">Above 54<"));

    // CrossSourceSpotlight and venue toggle pills are retired on the card face
    expect(html).not.toContain(
      "Should never render CrossSourceSpotlight in Atlas view"
    );
    expect(html).not.toMatch(/>Kalshi<|>Polymarket<|>Merged</);
    expect(html).not.toMatch(/questions/i);
    expect(html).not.toContain("Live probabilities");
  });

  it("MidtermsAtlasChamberControl and MidtermsAtlasMemberCard render settled ✓ Won and ascending ladders", () => {
    const html = renderToStaticMarkup(
      React.createElement(
        "div",
        null,
        React.createElement(MidtermsAtlasChamberControl, {
          senate: { market_id: 107867, gop: 100, dem: 0, winner: "Republicans" },
          house: { market_id: 107869, gop: 0, dem: 100, winner: "Democrats" },
        }),
        React.createElement(MidtermsAtlasMemberCard, {
          sectionTitle: "Senate races",
          member: {
            key: "market:109085",
            id: 109085,
            destination: "/futures/109085",
            item: {
              type: "futures",
              score: 1,
              data: {
                id: 109085,
                name: "Kansas Senate winner?",
                status: "resolved",
                settled_winner: "Roger Marshall",
                top_outcomes: [
                  { id: 1, name: "Roger Marshall", probability: 1, result: "yes" },
                  { id: 2, name: "Adam Hamilton", probability: 0, result: "no" },
                ],
              },
            },
          } as any,
        }),
        React.createElement(MidtermsAtlasMemberCard, {
          sectionTitle: "Margins",
          member: {
            key: "market:999",
            id: 999,
            destination: "/futures/999",
            item: {
              type: "futures",
              score: 1,
              data: {
                id: 999,
                name: "Senate seats threshold",
                status: "open",
                top_outcomes: [
                  { id: 11, name: "Above 53", probability: 0.35 },
                  { id: 12, name: "Above 51", probability: 0.72 },
                ],
              },
            },
          } as any,
        })
      )
    );

    expect(html).toContain("Roger Marshall");
    expect(html).toContain("✓ Won");
    expect(html).toContain("data-testid=\"atlas-threshold-ladder\"");
    expect(html.indexOf(">Above 51<")).toBeLessThan(html.indexOf(">Above 53<"));
  });

  it("EconomicsAtlasView orders numeric brackets ascending and withholds ReleaseCard when release_at is missing", () => {
    const futureReleaseIso = new Date(Date.now() + 48 * 3600 * 1000).toISOString();
    const baseThemes = {
      fed: {
        count: 1,
        fomc_meetings: [
          {
            mo: "Dec 2026",
            date: "Dec 18",
            dist: [
              [65, "4.25%–4.50%"],
              [35, "3.75%–4.00%"],
            ],
          },
        ],
        rate_cuts: [
          [55, "2 cuts"],
          [45, "1 cut"],
        ],
        side_markets: [],
      },
      inflation: {
        count: 1,
        cpi_releases: [
          {
            mo: "Oct 2026",
            q: "October CPI YoY",
            is_next: true,
            release_at: null,
            brackets: [
              [60, "2.6%"],
              [40, "2.4%"],
            ],
          },
        ],
        side_markets: [],
      },
    };

    const htmlWithoutRelease = renderToStaticMarkup(
      React.createElement(EconomicsAtlasView, {
        data: {
          total_markets: 3,
          updated_at: "2026-11-05T18:00:00Z",
          themes: baseThemes,
        } as any,
      })
    );

    // Without release_at, ReleaseCard is withheld and BucketDistribution renders instead
    expect(htmlWithoutRelease).not.toContain("data-testid=\"atlas-release-card\"");
    expect(htmlWithoutRelease).toContain("data-testid=\"atlas-bucket-distribution\"");
    expect(htmlWithoutRelease.indexOf(">3.75%–4.00%<")).toBeLessThan(
      htmlWithoutRelease.indexOf(">4.25%–4.50%<")
    );
    expect(htmlWithoutRelease.indexOf(">1 cut<")).toBeLessThan(
      htmlWithoutRelease.indexOf(">2 cuts<")
    );

    // With future release_at present on is_next CPI release, ReleaseCard renders
    const htmlWithRelease = renderToStaticMarkup(
      React.createElement(EconomicsAtlasView, {
        data: {
          total_markets: 3,
          updated_at: "2026-11-05T18:00:00Z",
          themes: {
            ...baseThemes,
            inflation: {
              count: 1,
              cpi_releases: [
                {
                  mo: "Oct 2026",
                  q: "October CPI YoY",
                  is_next: true,
                  release_at: futureReleaseIso,
                  brackets: [
                    [40, "2.4%"],
                    [60, "2.6%"],
                  ],
                },
              ],
              side_markets: [],
            },
          },
        } as any,
      })
    );
    expect(htmlWithRelease).toContain("data-testid=\"atlas-release-card\"");
  });

  it("EntertainmentAtlasView uses 'Lead pop-culture markets' heading, orders ladders ascending, and renders settled ✓ Won", () => {
    const data = {
      total_markets: 4,
      updated_at: "2026-11-05T18:00:00Z",
      trending: [
        {
          market_id: 801,
          q: "Best Actor winner at the Oscars?",
          prob: 100,
          leader: "Adrien Brody",
          status: "resolved",
          settled_winner: "Adrien Brody",
          src: "kalshi",
          top_outcomes: [
            { name: "Adrien Brody", prob: 100, rendered_percent: 100 },
            { name: "Timothée Chalamet", prob: 0, rendered_percent: 0 },
          ],
        },
      ],
      themes: {
        music: {
          count: 1,
          billboard_groups: [
            {
              title: "Hot 100 #1 song chart weeks",
              thresholds: [
                { market_id: 810, label: "Above 12 weeks", prob: 32 },
                { market_id: 811, label: "Above 8 weeks", prob: 78 },
              ],
            },
          ],
        },
        movies_tv: {
          count: 2,
          box_office_groups: [
            {
              title: "Wicked opening weekend box office",
              thresholds: [
                { market_id: 812, label: "$120M–$140M", prob: 32 },
                { market_id: 813, label: "$90M–$110M", prob: 68 },
              ],
            },
          ],
          rotten_tomatoes: [
            {
              market_id: 820,
              q: "Gladiator II Rotten Tomatoes score Above 75?",
              prob: 68,
              leader: "Yes",
              src: "kalshi",
              top_outcomes: [{ name: "Yes", prob: 68, rendered_percent: 68 }],
            },
          ],
        },
      },
    };

    const html = renderToStaticMarkup(
      React.createElement(EntertainmentAtlasView, { data: data as any })
    );

    expect(html).toContain(">Lead pop-culture markets<");
    expect(html).not.toMatch(/questions/i);
    expect(html).toContain("✓ Won");
    expect(html).toContain("data-testid=\"atlas-threshold-ladder\"");
    expect(html.indexOf(">Above 8 weeks<")).toBeLessThan(
      html.indexOf(">Above 12 weeks<")
    );
    expect(html.indexOf(">$90M–$110M<")).toBeLessThan(
      html.indexOf(">$120M–$140M<")
    );
    expect(html).not.toContain("Live probabilities");
  });

  it("TRUTH guards: never infers settlement from 99.5%+ price, matches #12123 'Republican Party'/'Democratic Party' winners, and prints 'No recent price' (never 0%) when prob is null", () => {
    // 1. 99.8% / 100% without a graded winner stays open (never ✓ Won)
    const ungradedHighPriceHtml = renderToStaticMarkup(
      React.createElement(
        "div",
        null,
        React.createElement(MidtermsAtlasChamberControl, {
          senate: { market_id: 107867, gop: 99.8, dem: 0.2 },
          house: null,
        }),
        React.createElement(MidtermsAtlasMemberCard, {
          sectionTitle: "Senate races",
          member: {
            key: "market:109999",
            id: 109999,
            destination: "/futures/109999",
            item: {
              type: "futures",
              score: 1,
              data: {
                id: 109999,
                name: "Ungraded resolved race",
                status: "resolved",
                settled_winner: null,
                top_outcomes: [
                  { id: 1, name: "Candidate A", probability: 0.999, result: null },
                  { id: 2, name: "Candidate B", probability: 0.001, result: null },
                ],
              },
            },
          } as any,
        })
      )
    );
    expect(ungradedHighPriceHtml).toContain("CHAMBER CONTROL · open");
    expect(ungradedHighPriceHtml).not.toContain("✓ Won");

    // 2. #12123 server strings 'Republican Party' and 'Democratic Party' match chamber contenders
    const partyStringsHtml = renderToStaticMarkup(
      React.createElement(MidtermsAtlasChamberControl, {
        senate: {
          market_id: 107867,
          gop: 100,
          dem: 0,
          winner: "Republican Party",
        },
        house: {
          market_id: 107869,
          gop: 0,
          dem: 100,
          winner: "Democratic Party",
        },
      })
    );
    expect(partyStringsHtml).toContain("CHAMBER CONTROL · settled");
    expect(partyStringsHtml).toContain("Republicans");
    expect(partyStringsHtml).toContain("Democrats");
    expect(partyStringsHtml).toContain("✓ Won");

    // 3. Missing price (prob: null / probability: null) prints 'No recent price', never '0%'
    const unpricedEconHtml = renderToStaticMarkup(
      React.createElement(
        "div",
        null,
        React.createElement(EconomicsAtlasView, {
          data: {
            total_markets: 1,
            updated_at: "2026-11-05T18:00:00Z",
            themes: {
              jobs: {
                count: 1,
                markets: [
                  {
                    market_id: 777,
                    q: "Unemployment rate above 4.5%?",
                    leader: "Yes",
                    prob: null,
                    src: "kalshi",
                  },
                ],
              },
            },
          } as any,
        }),
        React.createElement(MidtermsAtlasMemberCard, {
          sectionTitle: "Senate races",
          member: {
            key: "market:109888",
            id: 109888,
            destination: "/futures/109888",
            item: {
              type: "futures",
              score: 1,
              data: {
                id: 109888,
                name: "Unpriced Senate race",
                status: "open",
                top_outcomes: [
                  { id: 1, name: "Candidate X", probability: null },
                  { id: 2, name: "Candidate Y", probability: null },
                ],
              },
            },
          } as any,
        })
      )
    );
    expect(unpricedEconHtml).toContain(ATLAS_STATE_COPY.noRecentPrice);
    expect(unpricedEconHtml).not.toContain(">0%<");
  });
});
