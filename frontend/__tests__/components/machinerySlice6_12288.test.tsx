/**
 * #12288 Slice 6 website tests:
 * 2a. First section never repeats the page headline (Oscars embedded paired card & section 0 heading).
 * 2c. Failed or partial reads render an explicit error state, never an empty or shorter grouping.
 * 2d. Website draws the same served shape as iPhone: shared left edge via invisible art-slot spacer
 *     when some sibling rows lack art (flush left when zero rows have art, zero monogram letters),
 *     and one distinct colour per line in a chart.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AwardCategoryPairedCard } from "@/components/discover/forms/AwardCategoryPairedCard";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  resolveDistinctChartSeries,
  type MachineryCardContract,
  type MachineryHistorySeries,
} from "@/components/collections/MachinerySectionRenderer";
import {
  PreviewGroupingColumn,
  type MachineryPreviewEntry,
} from "@/components/collections/MachineryPreviewColumn";
import { PAIRED_METRIC_REGISTER, type PairedMetricSet } from "@/lib/discover/visualForms";
import type { MachineryVisualBlock } from "@/lib/collections";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
    }) => R.createElement("a", { href, ...rest }, children),
  };
});
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
}));
jest.mock("@/hooks", () => ({
  usePageTracking: () => {},
  useScrollDepth: () => {},
  useEngagementTime: () => {},
}));
jest.mock("@/components/admin/AdminAuthProvider", () => ({
  useAdminAuth: () => ({ secret: "test", clearSecret: () => {} }),
}));

describe("#12288 Slice 6 — Website parity, error states, and non-repeating first-section headlines", () => {
  const baseOscarsSet: PairedMetricSet =
    PAIRED_METRIC_REGISTER["oscars-2027-best-picture"];

  it("2a: suppresses duplicate inner paired-card header inside container sections and suppresses duplicate section-0 headline", () => {
    const vb: MachineryVisualBlock = {
      form_id: "paired_stage_bars",
      initial_visible_limit: 3,
      paired_metric_set: {
        ...baseOscarsSet,
        title: "The Odyssey leads Best Picture at 54%, with 6 contenders at 75%+ to be nominated",
      },
      items: [],
    };
    const sectionHtml = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={vb} members={[]} />,
    );
    // Section renderer omits the embedded paired card's kicker and title so page headline never prints twice
    expect(sectionHtml).not.toContain(baseOscarsSet.kicker);
    expect(sectionHtml).not.toContain(
      "The Odyssey leads Best Picture at 54%, with 6 contenders at 75%+ to be nominated",
    );
    // Contender bars and legend still render cleanly
    expect(sectionHtml).toContain('data-testid="legend-swatch-stage-1"');
    expect(sectionHtml).toContain("The Odyssey");

    // PreviewGroupingColumn also suppresses section 0's <h3> if it repeats parsedHub.title
    const headline =
      "The Odyssey leads Best Picture at 54%, with 6 contenders at 75%+ to be nominated";
    const okEntry: MachineryPreviewEntry = {
      slug: "machinery-oscars-best-picture",
      status: "ok",
      definition: {
        slug: "machinery-oscars-best-picture",
        name: headline,
        category: "entertainment",
        kicker: "OSCARS · BEST PICTURE",
        footer: "",
      },
      feed_item: null,
      container: {
        slug: "machinery-oscars-best-picture",
        state: "published",
        revision: 1,
        member_count: 1,
        container: {
          id: 101,
          slug: "machinery-oscars-best-picture",
          name: headline,
          kind: "roundup",
        },
        sections: [
          {
            class: "lead",
            title: headline,
            note: "Nominated and Wins side by side.",
            layout: "paired_stage_bars",
            count: 1,
            members: [
              {
                type: "market",
                id: 6173044,
                destination: {
                  kind: "market",
                  id: 6173044,
                  web: "/futures/6173044",
                  api: "/api/futures/6173044",
                },
                card: {
                  id: 6173044,
                  name: "Oscars 2027: Best Picture Winner",
                  status: "open",
                  source: "kalshi",
                  top_outcomes: [
                    { id: 1, name: "The Odyssey", probability: 0.54 },
                  ],
                },
              },
            ],
            visual_block: vb,
          },
        ],
      },
      diversity_report: null,
    };

    const colHtml = renderToStaticMarkup(
      <PreviewGroupingColumn entry={okEntry} viewport="390" />,
    );
    const occurrences = colHtml.split(headline).length - 1;
    expect(occurrences).toBe(1);
  });

  it("2c: renders an explicit alert error state (never an empty or shorter grouping) on failed or partial reads", () => {
    const failedEntry: MachineryPreviewEntry = {
      slug: "machinery-nfl-week",
      status: "error",
      error: "Couldn't load this grouping right now. Please try again.",
      definition: {
        slug: "machinery-nfl-week",
        name: "NFL Slate",
        category: "sports",
        kicker: "NFL · THIS SLATE",
        footer: "",
      },
      feed_item: null,
      container: null,
      diversity_report: null,
    };

    const errHtml = renderToStaticMarkup(
      <PreviewGroupingColumn entry={failedEntry} viewport="390" onRetry={() => {}} />,
    );
    expect(errHtml).toContain('role="alert"');
    expect(errHtml).toContain('data-testid="machinery-error-machinery-nfl-week"');
    expect(errHtml).toContain("Couldn&#x27;t load this grouping right now. Please try again.");
    expect(errHtml).toContain("Try again");
    expect(errHtml).not.toContain("Container page ·");

    // Partial/corrupted member inside an otherwise 'published' container also triggers the error state
    // rather than rendering a shorter grouping with missing members.
    const partialEntry: MachineryPreviewEntry = {
      ...failedEntry,
      status: "ok",
      error: null,
      container: {
        slug: "machinery-nfl-week",
        state: "published",
        revision: 1,
        member_count: 2,
        container: {
          id: 202,
          slug: "machinery-nfl-week",
          name: "NFL Slate",
          kind: "roundup",
        },
        sections: [
          {
            class: "slate",
            title: "Slate",
            layout: "sibling_fields_grid",
            count: 2,
            members: [
              {
                type: "market",
                id: 7001,
                destination: {
                  kind: "market",
                  id: 7001,
                  web: "/futures/7001",
                  api: "/api/futures/7001",
                },
                card: {
                  id: 7001,
                  name: "AFC North Champion",
                  status: "open",
                  source: "kalshi",
                  top_outcomes: [{ id: 1, name: "Ravens", probability: 0.55 }],
                },
              },
              // Invalid destination triggers partial=true in parseCollection
              {
                type: "market",
                id: 7002,
                destination: { kind: "broken" },
                card: {},
              },
            ],
            visual_block: {
              form_id: "sibling_fields_grid",
              initial_visible_limit: 3,
              items: [],
            },
          },
        ],
      },
    };

    const partialHtml = renderToStaticMarkup(
      <PreviewGroupingColumn entry={partialEntry} viewport="390" onRetry={() => {}} />,
    );
    expect(partialHtml).toContain('role="alert"');
    expect(partialHtml).toContain('data-testid="machinery-error-machinery-nfl-week"');
    expect(partialHtml).not.toContain("AFC North Champion");
  });

  it("2d: aligns sibling outcome names with an invisible spacer when some rows lack art, renders flush left when none have art, and never prints monogram letters", () => {
    const mixedArtBlock: MachineryVisualBlock = {
      form_id: "sibling_fields_grid",
      initial_visible_limit: 3,
      items: [
        {
          market_id: 901,
          title: "Democratic Running Mate",
          href: "/futures/901",
          scale_ordered: false,
          leader_outcome_id: 1,
          outcomes: [
            {
              outcome_id: 1,
              name: "Josh Shapiro",
              probability: 0.24,
              rendered_percent: 24,
              art: {
                url: "https://upload.wikimedia.org/shapiro.jpg",
                kind: "person",
                detail: "",
                accent_color: "#2563EB",
                initials: "JS",
              },
            },
            {
              outcome_id: 2,
              name: "Andy Beshear",
              probability: 0.16,
              rendered_percent: 16,
              art: {
                url: null,
                kind: "none",
                detail: "",
                accent_color: "",
                initials: "AB",
              },
            },
          ],
        },
        {
          market_id: 902,
          title: "Unpictured Sibling Market",
          href: "/futures/902",
          scale_ordered: false,
          leader_outcome_id: 3,
          outcomes: [
            {
              outcome_id: 3,
              name: "Option Alpha",
              probability: 0.6,
              rendered_percent: 60,
              art: {
                url: null,
                kind: "none",
                detail: "",
                accent_color: "",
                initials: "OA",
              },
            },
            {
              outcome_id: 4,
              name: "Option Beta",
              probability: 0.4,
              rendered_percent: 40,
              art: {
                url: null,
                kind: "none",
                detail: "",
                accent_color: "",
                initials: "OB",
              },
            },
          ],
        },
      ],
    };

    const html = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={mixedArtBlock} members={[]} />,
    );
    // Market 901 has 1 real headshot + 1 invisible width-matching spacer; Market 902 has 0 spacers (flush left)
    const spacerMatches = html.match(/data-testid="machinery-avatar-spacer"/g) ?? [];
    expect(spacerMatches).toHaveLength(1);
    // Zero monogram initials anywhere
    expect(html).not.toContain(">AB<");
    expect(html).not.toContain(">OA<");
    expect(html).not.toContain('data-testid="award-paired-art-fallback"');

    // Discover card with mixed art also reserves spacer for artless sibling row
    const mixedCard: MachineryCardContract = {
      slug: "machinery-2028-presidential",
      form_id: "contender_spotlight",
      kicker: "2028 · WHITE HOUSE",
      title: "Jon Ossoff leads the presidential race at 18%",
      subtitle: "",
      footer: "",
      section_count: 4,
      destination_href: "/collections/machinery-2028-presidential",
      rows: [
        {
          outcome_id: 11,
          name: "Jon Ossoff",
          rendered_percent: 18,
          art: { url: "https://upload.wikimedia.org/ossoff.jpg", kind: "person" },
        },
        {
          outcome_id: 12,
          name: "Unpictured Candidate",
          rendered_percent: 9,
          art: { url: null, kind: "none", initials: "UC" },
        },
      ],
    };
    const cardHtml = renderToStaticMarkup(<MachineryDiscoverCard card={mixedCard} />);
    expect(cardHtml).toContain('data-testid="machinery-avatar-spacer"');
    expect(cardHtml).not.toContain(">UC<");
  });

  it("2d: assigns distinct line colours when chart series share duplicate or empty colours", () => {
    const rawSeries: MachineryHistorySeries[] = [
      {
        outcome_id: 1,
        name: "Line A",
        current_pct: 52,
        color: "#2563EB",
        points: [
          { t: "2026-11-11T00:00:00Z", pct: 44 },
          { t: "2026-11-18T00:00:00Z", pct: 52 },
        ],
      },
      {
        outcome_id: 2,
        name: "Line B",
        current_pct: 31,
        color: "#2563eb",
        points: [
          { t: "2026-11-11T00:00:00Z", pct: 38 },
          { t: "2026-11-18T00:00:00Z", pct: 31 },
        ],
      },
      {
        outcome_id: 3,
        name: "Line C",
        current_pct: 17,
        color: "",
        points: [
          { t: "2026-11-11T00:00:00Z", pct: 18 },
          { t: "2026-11-18T00:00:00Z", pct: 17 },
        ],
      },
    ];

    const deduped = resolveDistinctChartSeries(rawSeries);
    const uniqueColors = new Set(deduped.map((s) => s.color.toLowerCase()));
    expect(uniqueColors.size).toBe(3);

    const chartBlock: MachineryVisualBlock = {
      form_id: "probability_history_chart",
      initial_visible_limit: 3,
      items: [
        {
          market_id: 500,
          title: "Rate Path",
          href: "/futures/500",
          start_iso: "2026-11-11T00:00:00Z",
          end_iso: "2026-11-18T00:00:00Z",
          y_min: 10,
          y_max: 60,
          series: rawSeries,
        },
      ],
    };
    const svgHtml = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={chartBlock} members={[]} />,
    );
    const strokes = Array.from(
      svgHtml.matchAll(/<path[^>]*stroke="([^"]+)"/g),
      (m) => m[1].toLowerCase(),
    );
    expect(strokes).toHaveLength(3);
    expect(new Set(strokes).size).toBe(3);
  });

  it("wraps contender_spotlight podium subtitles without line-clamp-1 truncation", () => {
    const spotlightBlock: MachineryVisualBlock = {
      form_id: "contender_spotlight",
      initial_visible_limit: 3,
      items: [
        {
          market_id: 8103,
          title: "MVP",
          href: "/futures/8103",
          outcomes: [
            {
              outcome_id: 1,
              name: "Victor Wembanyama",
              probability: 0.43,
              rendered_percent: 43,
              art: {
                url: "https://a.espncdn.com/i/headshots/nba/players/full/5104157.png",
                kind: "person",
                detail: "Center · San Antonio",
                accent_color: "#111827",
                initials: "VW",
              },
            },
            {
              outcome_id: 2,
              name: "Luka Dončić",
              probability: 0.38,
              rendered_percent: 38,
              art: {
                url: "https://a.espncdn.com/i/headshots/nba/players/full/3945274.png",
                kind: "person",
                detail: "Guard · LA Lakers",
                accent_color: "#552583",
                initials: "LD",
              },
            },
            {
              outcome_id: 3,
              name: "Shai Gilgeous-Alexander",
              probability: 0.19,
              rendered_percent: 19,
              art: {
                url: "https://a.espncdn.com/i/headshots/nba/players/full/4278073.png",
                kind: "person",
                detail: "Guard · Oklahoma City",
                accent_color: "#007AC1",
                initials: "SG",
              },
            },
          ],
        },
      ],
    };
    const html = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={spotlightBlock} members={[]} />,
    );
    expect(html).toContain("Center · San Antonio");
    expect(html).toContain("Guard · Oklahoma City");
    expect(html).not.toContain("line-clamp-1");
  });

  it("wraps paired_stage_bars subject and studio credit detail without truncate ellipsis", () => {
    const html = renderToStaticMarkup(
      <AwardCategoryPairedCard
        set={{
          set_id: "oscars-2027-best-picture",
          title: "Best Picture",
          kicker: "OSCARS 2027",
          subtitle: "99th Academy Awards",
          category: "entertainment",
          stage_1_label: "Nominated",
          stage_2_label: "Wins",
          stage_1_settled_yes_label: "Nominated",
          stage_1_settled_no_label: "Not nominated",
          never_blend: true,
          as_of: "2026-11-18T00:00:00Z",
          stage_1_market: { id: 5165726, source: "kalshi", name: "Best Picture Nominees" },
          stage_2_market: { id: 6173044, source: "kalshi", name: "Best Picture Winner" },
          entries: [
            {
              subject_key: "film:you-can-see-everything",
              subject: "You Can See Everything",
              detail: "Nathan Fielder & Lance Oppenheim · Blow Out Productions",
              stage_1_market_id: 5165726,
              stage_1_outcome: "You Can See Everything",
              stage_1_probability: 0.89,
              stage_1_settled_state: null,
              stage_2_market_id: 6173044,
              stage_2_outcome: "You Can See Everything",
              stage_2_probability: 0.21,
              art: {
                url: "https://image.tmdb.org/t/p/w185/sample.jpg",
                kind: "tmdb_poster",
                adult: false,
                kid_safe_vetted: true,
              },
            },
          ],
        }}
        surface="collection"
        showHeader={false}
      />,
    );
    expect(html).toContain("Nathan Fielder &amp; Lance Oppenheim · Blow Out Productions");
    expect(html).not.toContain("block truncate text-xs text-text-muted");
    expect(html).not.toContain("block truncate text-sm font-semibold");
  });

  it("253: A: omits Toss-up badge when show_toss_up_tag is false", () => {
    const vb: MachineryVisualBlock = {
      form_id: "coin_flip_matchups",
      initial_visible_limit: 3,
      items: [
        {
          event_id: 14969890,
          away_short: "Ravens",
          home_short: "Panthers",
          away_pct: 43,
          home_pct: 57,
          commence_time: "2026-11-22T18:00:00+00:00",
          is_toss_up: false,
          show_toss_up_tag: false,
        },
      ],
    };
    const html = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={vb} members={[]} />,
    );
    expect(html).toContain("Ravens");
    expect(html).toContain("43%");
    expect(html).toContain("57%");
    expect(html).not.toContain("Toss-up");
  });

  it("#13097 batch-1 wording: benchmark_strip uses visualBlock.item_noun ('cities', 'couples') and falls back to 'benchmarks'", () => {
    const makeItems = () =>
      [1, 2, 3, 4].map((n) => ({
        market_id: 9000 + n,
        title: `Entry ${n}`,
        outcomes: [{ outcome_id: n, name: "Yes", rendered_percent: 40 - n }],
      }));

    const citiesHtml = renderToStaticMarkup(
      <MachinerySectionRenderer
        visualBlock={{
          form_id: "benchmark_strip",
          initial_visible_limit: 3,
          item_noun: "cities",
          items: makeItems(),
        }}
        members={[]}
      />,
    );
    expect(citiesHtml).toContain("Show all 4 cities (+1 more)");
    expect(citiesHtml).not.toContain("benchmarks");

    const couplesHtml = renderToStaticMarkup(
      <MachinerySectionRenderer
        visualBlock={{
          form_id: "benchmark_strip",
          initial_visible_limit: 3,
          item_noun: "couples",
          items: makeItems(),
        }}
        members={[]}
      />,
    );
    expect(couplesHtml).toContain("Show all 4 couples (+1 more)");
    expect(couplesHtml).not.toContain("benchmarks");

    const defaultHtml = renderToStaticMarkup(
      <MachinerySectionRenderer
        visualBlock={{
          form_id: "benchmark_strip",
          initial_visible_limit: 3,
          items: makeItems(),
        }}
        members={[]}
      />,
    );
    expect(defaultHtml).toContain("Show all 4 benchmarks (+1 more)");
  });

  it("252: A: bootFeedPath appends machinery=1 only when NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 is true", () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { bootFeedPath } = require("@/lib/discover/feedBoot");
    const prev = process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
    try {
      delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
      expect(bootFeedPath()).not.toContain("machinery=1");
      process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = "true";
      expect(bootFeedPath()).toContain("machinery=1");
    } finally {
      if (prev === undefined) {
        delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
      } else {
        process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = prev;
      }
    }
  });

  it("343: A: renders 3-team contender_spotlight card tiles with team crests and no initials fallback", () => {
    const spotlightCard: MachineryCardContract = {
      slug: "machinery-march-madness-2027",
      form_id: "contender_spotlight",
      kicker: "SPORTS · COLLEGE BASKETBALL",
      title: "Houston leads the Dec 7 AP poll #1 team at 54%",
      subtitle: "Full AP Poll #1 race alongside teams contending for the 2027 Final Four.",
      footer: "",
      section_count: 2,
      destination_href: "/collections/machinery-march-madness-2027",
      rows: [
        {
          outcome_id: 1,
          name: "Houston",
          rendered_percent: 54,
          art: { url: "https://a.espncdn.com/i/teamlogos/ncaa/500/248.png", kind: "team_logo" },
        },
        {
          outcome_id: 2,
          name: "Duke",
          rendered_percent: 10,
          art: { url: "https://a.espncdn.com/i/teamlogos/ncaa/500/150.png", kind: "team_logo" },
        },
        {
          outcome_id: 3,
          name: "Michigan St.",
          rendered_percent: 7,
          art: { url: "https://a.espncdn.com/i/teamlogos/ncaa/500/127.png", kind: "team_logo" },
        },
      ],
    };
    const html = renderToStaticMarkup(<MachineryDiscoverCard card={spotlightCard} />);
    const tileMatches = html.match(/data-testid="machinery-spotlight-tile"/g) ?? [];
    expect(tileMatches).toHaveLength(3);
    expect(html).toContain("/teamlogos/ncaa/500/248.png");
    expect(html).toContain("/teamlogos/ncaa/500/150.png");
    expect(html).toContain("/teamlogos/ncaa/500/127.png");
    expect(html).toContain("Open all 2 sections");
    expect(html).not.toContain('data-testid="machinery-avatar-initials"');
  });
});
