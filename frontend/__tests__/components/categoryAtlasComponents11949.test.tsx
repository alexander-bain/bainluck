import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  FieldBoard,
  BinaryRow,
  ThresholdLadderCard,
  RaceCard,
  BucketDistribution,
  ReleaseCard,
  AtlasCategoryJourneyChart,
} from "@/components/atlas/CategoryAtlasComponents";
import EconomicsAtlasView from "@/components/economics/EconomicsAtlasView";
import EntertainmentAtlasView from "@/components/entertainment/EntertainmentAtlasView";
import PoliticsAtlasView from "@/components/politics/PoliticsAtlasView";
import {
  MidtermsAtlasChamberControl,
  MidtermsAtlasMemberCard,
} from "@/components/collections/MidtermsAtlasSection";

describe("CategoryAtlasComponents (#11949 Order 7)", () => {
  it("FieldBoard renders contenders on a 0-100 track and settled rows with ✓ Won / ✗ Lost", () => {
    const html = renderToStaticMarkup(
      React.createElement(FieldBoard, {
        meta: {
          kicker: "2028 PRESIDENTIAL",
          marketTitle: "Who will win the 2028 Presidential Election?",
          sourceLabels: ["Kalshi", "Polymarket"],
        },
        outcomes: [
          { id: 1, label: "JD Vance", probability: 0.28, renderedPercent: 28 },
          { id: 2, label: "Gavin Newsom", probability: 0.19, renderedPercent: 19 },
          {
            id: 3,
            label: "Withdrawn Candidate",
            probability: 0,
            renderedPercent: 0,
            isSettled: true,
            settledResult: "lost",
          },
        ],
      })
    );
    expect(html).toContain("data-testid=\"atlas-field-board\"");
    expect(html).toContain("JD Vance");
    expect(html).toContain("28%");
    expect(html).toContain("Gavin Newsom");
    expect(html).toContain("19%");
    expect(html).toContain("✗ Lost");
  });

  it("BinaryRow renders a single ink bar and replaces settled 100% with ✓ Won", () => {
    const openHtml = renderToStaticMarkup(
      React.createElement(BinaryRow, {
        meta: {
          marketTitle: "Will the Fed cut rates in December?",
          source: "kalshi",
        },
        outcome: {
          id: "open-1",
          label: "Yes",
          probability: 0.64,
          renderedPercent: 64,
        },
      })
    );
    expect(openHtml).toContain("data-testid=\"atlas-binary-row\"");
    expect(openHtml).toContain("Will the Fed cut rates in December");
    expect(openHtml).toContain("64%");

    const settledHtml = renderToStaticMarkup(
      React.createElement(BinaryRow, {
        meta: {
          marketTitle: "Above 1 inch of rain — Austin",
        },
        outcome: {
          id: "settled-1",
          label: "Austin",
          probability: 1.0,
          renderedPercent: 100,
          isSettled: true,
          settledResult: "won",
        },
      })
    );
    expect(settledHtml).toContain("✓ Won");
    expect(settledHtml).not.toContain(">100%<");
  });

  it("ThresholdLadderCard renders cumulative rungs on a 0-100 scale with settled words", () => {
    const html = renderToStaticMarkup(
      React.createElement(ThresholdLadderCard, {
        meta: {
          kicker: "ROTTEN TOMATOES",
          marketTitle: "Project Hail Mary",
          subtitle: "Tomatometer thresholds",
        },
        rungs: [
          { id: "r1", label: "Above 60", probability: 0.92, renderedPercent: 92 },
          { id: "r2", label: "Above 75", probability: 0.78, renderedPercent: 78 },
          {
            id: "r3",
            label: "Above 50",
            probability: 1.0,
            renderedPercent: 100,
            isSettled: true,
            settledResult: "won",
          },
        ],
      })
    );
    expect(html).toContain("data-testid=\"atlas-threshold-ladder\"");
    expect(html).toContain("Project Hail Mary");
    expect(html).toContain("Above 75");
    expect(html).toContain("78%");
    expect(html).toContain("✓ Won");
  });

  it("RaceCard renders open contenders and settled winner badge", () => {
    const html = renderToStaticMarkup(
      React.createElement(RaceCard, {
        meta: {
          kicker: "CHAMBER CONTROL",
          marketTitle: "2026 Senate Control",
        },
        settledWinner: "Republicans",
        contenders: [
          {
            id: "rep",
            label: "Republicans",
            probability: 1.0,
            renderedPercent: 100,
            isSettled: true,
            settledResult: "won",
          },
          {
            id: "dem",
            label: "Democrats",
            probability: 0.0,
            renderedPercent: 0,
            isSettled: true,
            settledResult: "lost",
          },
        ],
      })
    );
    expect(html).toContain("data-testid=\"atlas-race-card\"");
    expect(html).toContain("Republicans");
    expect(html).toContain("✓ Won");
  });

  it("BucketDistribution renders mutually exclusive bands in value order", () => {
    const html = renderToStaticMarkup(
      React.createElement(BucketDistribution, {
        meta: {
          kicker: "AMERICAS · °F",
          marketTitle: "New York daily high",
        },
        buckets: [
          { id: "b1", label: "50°–51°F", probability: 0.15, renderedPercent: 15 },
          { id: "b2", label: "52°–53°F", probability: 0.52, renderedPercent: 52 },
          { id: "b3", label: "54°–55°F", probability: 0.33, renderedPercent: 33 },
        ],
      })
    );
    expect(html).toContain("data-testid=\"atlas-bucket-distribution\"");
    expect(html).toContain("52°–53°F most likely · 52%");
    expect(html.indexOf(">50°–51°F<")).toBeLessThan(html.indexOf(">52°–53°F<"));
    expect(html.indexOf(">52°–53°F<")).toBeLessThan(html.indexOf(">54°–55°F<"));
  });

  it("ReleaseCard renders when releaseAt is present and refuses when releaseAt is missing", () => {
    const refusedHtml = renderToStaticMarkup(
      React.createElement(ReleaseCard, {
        meta: { marketTitle: "Next CPI Release" },
        releaseAt: null,
        shape: "ladder",
        outcomes: [{ id: 1, label: "Above 2.5%", probability: 0.45, renderedPercent: 45 }],
      })
    );
    expect(refusedHtml).toBe("");

    const validHtml = renderToStaticMarkup(
      React.createElement(ReleaseCard, {
        meta: { marketTitle: "November CPI Release" },
        releaseAt: "2026-11-12T13:30:00Z",
        shape: "ladder",
        outcomes: [{ id: 1, label: "Above 2.5%", probability: 0.45, renderedPercent: 45 }],
      })
    );
    expect(validHtml).toContain("data-testid=\"atlas-release-card\"");
    expect(validHtml).toContain("November CPI Release");
    expect(validHtml).toContain("PT");
    expect(validHtml).toContain("45%");
  });

  it("AtlasCategoryJourneyChart renders a 0-100 multi-series SVG journey when points >= 2", () => {
    const html = renderToStaticMarkup(
      React.createElement(AtlasCategoryJourneyChart, {
        series: [
          {
            label: "JD Vance",
            points: [
              { observedAt: "2026-10-01T00:00:00Z", probability: 0.25 },
              { observedAt: "2026-11-01T00:00:00Z", probability: 0.28 },
            ],
          },
        ],
      })
    );
    expect(html).toContain("data-testid=\"atlas-category-journey-chart\"");
    expect(html).toContain("JD Vance");
  });

  it("PoliticsAtlasView (#11949 Order 8) renders FieldBoard hero with journey chart, settled Chamber Control RaceCards, and retires CrossSourceSpotlight", () => {
    const html = renderToStaticMarkup(
      React.createElement(PoliticsAtlasView, {
        data: {
          total_markets: 120,
          updated_at: "2026-11-05T19:00:00Z",
          by_source: { kalshi: 80, polymarket: 40 },
          cross_source: [
            {
              q: "Should not render under S-A",
              kalshi: 52,
              poly: 48,
              delta: 4,
              category: "presidential",
              kalshi_market_id: 1,
              poly_market_id: 2,
            },
          ],
          themes: {
            presidential: {
              count: 10,
              headline_q: "Who wins the 2028 presidential election?",
              has_dual_source: true,
              kalshi_market_id: 101,
              poly_market_id: 102,
              candidates: [
                {
                  name: "JD Vance",
                  party: "R",
                  kalshi: 29,
                  poly: 27,
                  merged: 28,
                  change_7d: 1.2,
                  history: [
                    { t: "2026-10-01T00:00:00Z", p: 25 },
                    { t: "2026-11-01T00:00:00Z", p: 28 },
                  ],
                },
                {
                  name: "Gavin Newsom",
                  party: "D",
                  kalshi: 19,
                  poly: 19,
                  merged: 19,
                  change_7d: -0.5,
                  history: [
                    { t: "2026-10-01T00:00:00Z", p: 20 },
                    { t: "2026-11-01T00:00:00Z", p: 19 },
                  ],
                },
              ],
              side_markets: [],
            },
            congressional: {
              count: 5,
              chamber_control: {
                senate: {
                  market_id: 108620,
                  gop: 100,
                  dem: 0,
                  winner: "Republican Party",
                } as unknown as import("@/lib/api").ChamberControl,
                house: {
                  market_id: 108621,
                  gop: 0,
                  dem: 100,
                  winner: "Democratic Party",
                } as unknown as import("@/lib/api").ChamberControl,
              },
              senate_map: null,
              markets: [
                {
                  q: "How many Senate seats will Republicans hold?",
                  prob: 45,
                  src: "kalshi",
                  market_id: 301,
                  outcome_count: 3,
                  top_outcomes: [
                    { name: "53 seats", prob: 45 },
                    { name: "51 seats", prob: 20 },
                    { name: "52 seats", prob: 35 },
                  ],
                },
              ],
            },
            gubernatorial: { count: 0, markets: [] },
            policy: { count: 0, markets: [] },
            scotus: { count: 0, markets: [] },
            international: { count: 0, markets: [] },
            other: { count: 0, markets: [] },
          },
        },
      })
    );
    expect(html).toContain("data-testid=\"politics-atlas-view\"");
    expect(html).toContain("data-testid=\"atlas-field-board\"");
    expect(html).toContain("data-testid=\"atlas-category-journey-chart\"");
    // Cross-source spotlight is retired under S-A
    expect(html).not.toContain("Should not render under S-A");
    // Settled chamber control renders ✓ Won
    expect(html).toContain("Senate Control");
    expect(html).toContain("✓ Won");
    // Numeric seat counts ordered ascending: 51 -> 52 -> 53
    expect(html.indexOf(">51 seats<")).toBeLessThan(html.indexOf(">52 seats<"));
    expect(html.indexOf(">52 seats<")).toBeLessThan(html.indexOf(">53 seats<"));
  });

  it("EconomicsAtlasView (#11949 Order 9) orders numeric brackets ascending and renders BucketDistribution and ThresholdLadderCard without venue or LIVE pills", () => {
    const html = renderToStaticMarkup(
      React.createElement(EconomicsAtlasView, {
        data: {
          total_markets: 95,
          updated_at: "2026-11-05T19:00:00Z",
          by_source: { kalshi: 70, polymarket: 25 },
          themes: {
            fed: {
              count: 4,
              fomc_meetings: [
                {
                  mo: "Dec",
                  date: "Dec 16, 2026",
                  dist: [
                    [65, "4.25%–4.50%"],
                    [25, "4.00%–4.25%"],
                    [10, "4.50%–4.75%"],
                  ],
                },
              ],
              rate_cuts: [
                [50, "2 cuts"],
                [20, "1 cut"],
                [30, "3 cuts"],
              ],
              side_markets: [],
            },
            inflation: {
              count: 1,
              cpi_releases: [
                {
                  q: "November YoY CPI",
                  mo: "Nov",
                  is_next: true,
                  brackets: [
                    [55, "2.5%–2.6%"],
                    [20, "2.3%–2.4%"],
                    [25, "2.7%–2.8%"],
                  ],
                },
              ],
              side_markets: [],
            },
            jobs: { count: 0, markets: [] },
            recession: {
              count: 1,
              main_q: "U.S. recession in 2026?",
              main_prob: 22,
              side_markets: [],
              gdp_quarters: [],
            },
            markets: {
              count: 1,
              today: [{ sym: "S&P 500", prob: 58, dir: "up" }],
              stocks: [],
              side_markets: [],
            },
            energy: { count: 0, gas: [], oil: [] },
            metals: { count: 0, cards: [], markets: [] },
            housing: {
              count: 1,
              mortgage_dist: {
                q: "30-year fixed mortgage rate",
                src: "kalshi",
                kind: "ladder",
                rows: [
                  [82, "Above 6.0%"],
                  [44, "Above 6.5%"],
                ],
              },
              markets: [],
            },
            trade: { count: 0, markets: [] },
            government: { count: 0, markets: [], distributions: [] },
          },
        } as unknown as import("@/lib/api").EconData,
      })
    );
    expect(html).toContain("data-testid=\"economics-atlas-view\"");
    expect(html.indexOf(">1 cut<")).toBeLessThan(html.indexOf(">2 cuts<"));
    expect(html.indexOf(">2 cuts<")).toBeLessThan(html.indexOf(">3 cuts<"));
    expect(html.indexOf(">2.3%–2.4%<")).toBeLessThan(html.indexOf(">2.5%–2.6%<"));
    expect(html).not.toContain("● LIVE");
  });

  it("EntertainmentAtlasView (#11949 Order 10) uses probability-first headline, groups Billboard Watch under SONG / CHART WEEK, and omits Vol $ chrome", () => {
    const html = renderToStaticMarkup(
      React.createElement(EntertainmentAtlasView, {
        data: {
          total_markets: 60,
          updated_at: "2026-11-05T19:00:00Z",
          by_source: { kalshi: 45, polymarket: 15 },
          trending: [
            {
              q: "Will Dune: Part Three open above $100M?",
              prob: 72,
              src: "kalshi",
              market_id: 901,
              external_id: "KXDUNE",
              kind: "binary",
              top_outcomes: [{ name: "Yes", prob: 72, delta_24h: 0 }],
              outcome_count: 2,
              volume_24h: 18500,
              resolution_date: "2026-12-18",
              image_url: null,
              hook: null,
            },
          ],
          themes: {
            music: {
              count: 2,
              spotify_race: [],
              billboard_watch: [],
              billboard_groups: [
                {
                  title: "Billboard Hot 100 — Nov 14 Chart Week",
                  image_url: null,
                  thresholds: [
                    { label: "Above 30", prob: 40, market_id: 910 },
                    { label: "Above 15", prob: 75, market_id: 911 },
                  ],
                },
              ],
              album_drops: [],
              artist_streaming: [],
              side_markets: [],
            },
            movies_tv: {
              count: 1,
              rt_groups: [
                {
                  title: "Project Hail Mary Rotten Tomatoes score",
                  image_url: null,
                  thresholds: [
                    { label: "Above 80", prob: 68, market_id: 920 },
                    { label: "Above 60", prob: 91, market_id: 921 },
                  ],
                },
              ],
              rt_markets: [],
              box_office_groups: [],
              box_office: [],
              reality_tv: [],
              side_markets: [],
            },
            tech_culture: { count: 0, markets: [] },
          },
          cultural_moments: [],
        },
      })
    );
    expect(html).toContain("data-testid=\"entertainment-atlas-view\"");
    expect(html).toContain("What the world thinks will happen in pop culture");
    expect(html).not.toContain("betting");
    expect(html).not.toContain("Vol $");
    expect(html).toContain("SONG / CHART WEEK");
    expect(html.indexOf(">Above 15<")).toBeLessThan(html.indexOf(">Above 30<"));
    expect(html.indexOf(">Above 60<")).toBeLessThan(html.indexOf(">Above 80<"));
  });

  it("MidtermsAtlasSection (#11949 Order 8) renders settled chamber RaceCards and orders numeric seat brackets ascending", () => {
    const chamberHtml = renderToStaticMarkup(
      React.createElement(MidtermsAtlasChamberControl, {
        senate: { market_id: 108620, gop: 100, dem: 0, winner: "Republicans" },
        house: { market_id: 108621, gop: 0, dem: 100, winner: "Democrats" },
      })
    );
    expect(chamberHtml).toContain("data-testid=\"midterms-atlas-party-control\"");
    expect(chamberHtml).toContain("Senate Control");
    expect(chamberHtml).toContain("House Control");
    expect(chamberHtml).toContain("✓ Won");

    const seatsHtml = renderToStaticMarkup(
      React.createElement(MidtermsAtlasMemberCard, {
        sectionTitle: "Senate Seats",
        member: {
          key: "futures:555",
          id: 555,
          href: "/futures/555",
          item: {
            type: "futures",
            data: {
              id: 555,
              name: "How many Senate seats will Republicans hold?",
              probability: 0.45,
              source: "kalshi",
              resolution_date: "2026-11-04",
              outcome_count: 3,
              top_outcomes: [
                { name: "53 seats", probability: 0.45 },
                { name: "51 seats", probability: 0.2 },
                { name: "52 seats", probability: 0.35 },
              ],
            } as unknown as import("@/lib/types").FeedFuturesData,
          },
        } as unknown as import("@/lib/collections").CollectionMember,
      })
    );
    expect(seatsHtml.indexOf(">51 seats<")).toBeLessThan(seatsHtml.indexOf(">52 seats<"));
    expect(seatsHtml.indexOf(">52 seats<")).toBeLessThan(seatsHtml.indexOf(">53 seats<"));
  });
});
