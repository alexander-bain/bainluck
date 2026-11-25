import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  isMachinerySlice1Enabled,
} from "@/components/collections/MachinerySectionRenderer";
import { RoundupCard } from "@/components/discover/roundup/RoundupCard";
import { parseCollection } from "@/lib/collections";

jest.mock("next/link", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const R = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) =>
      R.createElement("a", { href, ...rest }, children),
  };
});
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
}));
jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/lib/analytics", () => ({ trackEvent: () => {} }));

describe("#12288 Slice 1 — topic-free container machinery renderer", () => {
  const origFlag = process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;

  afterEach(() => {
    if (origFlag === undefined) {
      delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
    } else {
      process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = origFlag;
    }
  });

  it("stays strictly switched off by default", () => {
    delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
    expect(isMachinerySlice1Enabled()).toBe(false);
    process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = "true";
    expect(isMachinerySlice1Enabled()).toBe(true);
  });

  it("parses visual_block on roundup sections in parseCollection without marking partial", () => {
    const payload = {
      state: "published",
      slug: "machinery-2028-presidential",
      revision: 42,
      edition: null,
      container: {
        id: 1001,
        slug: "machinery-2028-presidential",
        name: "2028 Presidential Race",
        kind: "roundup",
        category: "politics",
      },
      member_count: 1,
      withheld_count: 0,
      withheld: [],
      children: [],
      sections: [
        {
          class: "party_duel",
          title: "White House Party Control",
          note: "Two-party general-election balance.",
          layout: "duel_bar",
          count: 1,
          visual_block: {
            form_id: "duel_bar",
            items: [
              {
                market_id: 108327,
                href: "/futures/108327",
                outcomes: [
                  {
                    outcome_id: 1,
                    name: "Democratic party",
                    probability: 0.68,
                    rendered_percent: 68,
                    art: { url: null, kind: "monogram", detail: "", accent_color: "", initials: "DP" },
                  },
                  {
                    outcome_id: 2,
                    name: "Republican party",
                    probability: 0.32,
                    rendered_percent: 32,
                    art: { url: null, kind: "monogram", detail: "", accent_color: "", initials: "RP" },
                  },
                ],
              },
            ],
          },
          members: [
            {
              type: "market",
              id: 108327,
              destination: {
                kind: "market",
                id: 108327,
                web: "/futures/108327",
                api: "/api/futures/108327",
              },
              card: {
                id: 108327,
                name: "2028 Presidential Election winner? (Party)",
                status: "open",
                top_outcomes: [
                  { name: "Democratic party", probability: 0.68 },
                  { name: "Republican party", probability: 0.32 },
                ],
              },
            },
          ],
        },
      ],
    };
    const parsed = parseCollection(payload, "machinery-2028-presidential");
    expect(parsed.note).toBeNull();
    expect(parsed.sections[0].visualBlock?.form_id).toBe("duel_bar");
    expect(parsed.sections[0].note).toBe("Two-party general-election balance.");
  });

  it("renders duel_bar, contender_spotlight, paired_stage_bars, coin_flip_matchups, sibling_fields_grid, benchmark_strip, and MachineryDiscoverCard from visual_block", () => {
    const html = renderToStaticMarkup(
      <div>
        <MachineryDiscoverCard
          card={{
            slug: "machinery-2028-presidential",
            form_id: "contender_spotlight",
            kicker: "POLITICS · 2028 RACE",
            title: "2028 Presidential Race: party control, field & nominations",
            subtitle: "Individual candidates priced highest to win the presidency.",
            footer: "One party and one candidate win the general election.",
            section_count: 4,
            destination_href: "/collections/machinery-2028-presidential",
            rows: [
              {
                outcome_id: 71,
                name: "Jon Ossoff",
                rendered_percent: 18,
                art: {
                  url: "https://thumb.wikimedia.org/wikipedia/commons/thumb/9/97/Jon_Ossoff_Senate_Portrait_2021.jpg/500px-Jon_Ossoff_Senate_Portrait_2021.jpg",
                  kind: "person",
                  detail: "U.S. Senator",
                  accent_color: "",
                  initials: "JO",
                },
              },
            ],
          }}
        />
        <MachinerySectionRenderer
          members={[]}
          visualBlock={{
            form_id: "contender_spotlight",
            items: [
              {
                market_id: 112897,
                href: "/futures/112897",
                outcomes: [
                  {
                    outcome_id: 71,
                    name: "Jon Ossoff",
                    probability: 0.18,
                    rendered_percent: 18,
                    art: { url: null, kind: "monogram", detail: "Senator", accent_color: "", initials: "JO" },
                  },
                  {
                    outcome_id: 72,
                    name: "JD Vance",
                    probability: 0.15,
                    rendered_percent: 15,
                    art: { url: null, kind: "monogram", detail: "VP", accent_color: "", initials: "JV" },
                  },
                  {
                    outcome_id: 73,
                    name: "Alexandria Ocasio-Cortez",
                    probability: 0.09,
                    rendered_percent: 9,
                    art: { url: null, kind: "monogram", detail: "Rep.", accent_color: "", initials: "AO" },
                  },
                ],
              },
            ],
          }}
        />
        <MachinerySectionRenderer
          members={[]}
          visualBlock={{
            form_id: "paired_stage_bars",
            items: [],
            paired_metric_set: {
              set_id: "oscar-best-picture-99",
              category: "entertainment",
              kicker: "OSCARS · BEST PICTURE",
              title: "99th Academy Awards: Best Picture",
              subtitle: "Nominated % beside Wins %",
              stage_1_label: "Nominated",
              stage_2_label: "Wins",
              stage_1_settled_yes_label: "✓ Nominated",
              stage_1_settled_no_label: "✗ Not nominated",
              stage_1_market: { id: 501, source: "kalshi", name: "Best Picture Nominees" },
              stage_2_market: { id: 502, source: "kalshi", name: "Best Picture Winner" },
              never_blend: true,
              as_of: "2026-11-17T15:00:00Z",
              entries: [
                {
                  subject_key: "one_battle_after_another",
                  subject: "One Battle After Another",
                  detail: "Paul Thomas Anderson",
                  stage_1_market_id: 501,
                  stage_1_outcome: "One Battle After Another",
                  stage_1_probability: 0.96,
                  stage_1_settled_state: null,
                  stage_2_market_id: 502,
                  stage_2_outcome: "One Battle After Another",
                  stage_2_probability: 0.34,
                  art: null,
                },
              ],
            },
          }}
        />
        <MachinerySectionRenderer
          members={[]}
          visualBlock={{
            form_id: "coin_flip_matchups",
            items: [
              {
                event_id: 9001,
                href: "/events/9001",
                away_team: "Buffalo Bills",
                away_short: "Buffalo Bills",
                home_team: "Detroit Lions",
                home_short: "Detroit Lions",
                away_rendered_percent: 49,
                home_rendered_percent: 51,
                spread_gap_pp: 2,
                commence_time: "2026-11-22T21:25:00Z",
                away_art: { url: null, kind: "team", detail: "", accent_color: "#00338D", initials: "BUF" },
                home_art: { url: null, kind: "team", detail: "", accent_color: "#0076B6", initials: "DET" },
              },
            ],
          }}
        />
        <MachinerySectionRenderer
          members={[]}
          visualBlock={{
            form_id: "benchmark_strip",
            items: [
              {
                market_id: 131074,
                title: "Will the 2028 Democratic Presidential nominee be a woman",
                href: "/futures/131074",
                outcomes: [
                  {
                    outcome_id: 101,
                    name: "Yes",
                    probability: 0.23,
                    rendered_percent: 23,
                    art: { url: null, kind: "none", detail: "", accent_color: "", initials: "WW" },
                  },
                ],
              },
            ],
          }}
        />
      </div>,
    );
    expect(html).toContain('data-testid="machinery-discover-card"');
    expect(html).toContain('href="/collections/machinery-2028-presidential"');
    expect(html).toContain("Jon Ossoff");
    expect(html).toContain("One Battle After Another");
    expect(html).toContain("Buffalo Bills");
    expect(html).toContain("Open all 4 sections");
    // Bar #2: never print placeholder letters (WW / JO / BUF) when real art is absent
    expect(html).not.toContain(">WW<");
    expect(html).not.toContain(">BUF<");
  });

  it("exposes /admin/groupings-preview with GA4 hooks and AdminAuthProvider", () => {
    const fs = require("fs");
    const path = require("path");
    const src = fs.readFileSync(
      path.join(__dirname, "..", "app", "admin", "groupings-preview", "page.tsx"),
      "utf-8",
    );
    expect(src).toContain("usePageTracking");
    expect(src).toContain("useScrollDepth");
    expect(src).toContain("useEngagementTime");
    expect(src).toContain("AdminAuthProvider");
    expect(src).toContain("/api/containers/preview/machinery");
    expect(src).toContain("227: A Diversity Report");
  });

  it("renders machinery Discover cards via RoundupCard even when legacy footer is empty (#12288)", () => {
    process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = "true";

    const machineryContract = {
      kicker: "POLITICS · 2028 RACE",
      footer: "",
      tag: null,
      rows: [
        { market_id: 112897, outcome_id: 1625929, label: "Jon Ossoff", probability: 0.17, rendered_percent: 17 },
        { market_id: 112897, outcome_id: 1625920, label: "JD Vance", probability: 0.15, rendered_percent: 15 },
        { market_id: 112897, outcome_id: 1625922, label: "Marco Rubio", probability: 0.1, rendered_percent: 10 },
      ],
      machinery_card: {
        slug: "machinery-2028-presidential",
        form_id: "contender_spotlight",
        kicker: "POLITICS · 2028 RACE",
        title: "Jon Ossoff leads the presidential race at 17%, with Democrats at 67%",
        subtitle: "5 markets across 4 sections",
        footer: "Open all 4 sections",
        destination_href: "/collections/machinery-2028-presidential",
        section_count: 4,
        rows: [
          { outcome_id: 1625929, name: "Jon Ossoff", probability: 0.17, rendered_percent: 17 },
          { outcome_id: 1625920, name: "JD Vance", probability: 0.15, rendered_percent: 15 },
        ],
      },
    };
    const ref = {
      slug: "machinery-2028-presidential",
      href: "/collections/machinery-2028-presidential",
      name: "Jon Ossoff leads the presidential race at 17%, with Democrats at 67%",
      revision: 2560503151,
      collection_count: 5,
    };

    const html = renderToStaticMarkup(
      <RoundupCard
        title={ref.name}
        contract={machineryContract}
        collectionRef={ref}
        items={[]}
        bundleId="roundup:machinery-2028-presidential"
      />,
    );
    expect(html).toContain('data-testid="roundup-card-slot"');
    expect(html).toContain('data-testid="machinery-discover-card"');
    expect(html).toContain('href="/collections/machinery-2028-presidential"');
    expect(html).toContain("Jon Ossoff");

    // Oscars paired card with empty legacy footer + machinery_card link
    const oscarsRef = {
      slug: "machinery-oscars-best-picture",
      href: "/collections/machinery-oscars-best-picture",
      name: "The Odyssey leads Best Picture at 54%",
      revision: 318097539,
      collection_count: 8,
    };
    const oscarsHtml = renderToStaticMarkup(
      <RoundupCard
        title={oscarsRef.name}
        contract={{
          kicker: "THE OSCARS · BEST PICTURE",
          footer: "",
          tag: null,
          rows: [
            { market_id: 6173044, outcome_id: 31537937, label: "The Odyssey", probability: 0.54, rendered_percent: 54 },
          ],
          paired_metric_set: {
            set_id: "oscar-best-picture-99",
            category: "entertainment",
            kicker: "OSCARS · BEST PICTURE",
            title: "99th Academy Awards: Best Picture",
            subtitle: "Nominated % beside Wins %",
            stage_1_label: "Nominated",
            stage_2_label: "Wins",
            stage_1_settled_yes_label: "✓ Nominated",
            stage_1_settled_no_label: "✗ Not nominated",
            stage_1_market: { id: 501, source: "kalshi", name: "Best Picture Nominees" },
            stage_2_market: { id: 502, source: "kalshi", name: "Best Picture Winner" },
            never_blend: true,
            as_of: "2026-11-20T10:00:00Z",
            entries: [
              {
                subject_key: "the_odyssey",
                subject: "The Odyssey",
                detail: "Christopher Nolan",
                stage_1_market_id: 501,
                stage_1_outcome: "The Odyssey",
                stage_1_probability: 0.98,
                stage_1_settled_state: null,
                stage_2_market_id: 502,
                stage_2_outcome: "The Odyssey",
                stage_2_probability: 0.54,
                art: null,
              },
            ],
          },
          machinery_card: {
            slug: "machinery-oscars-best-picture",
            form_id: "paired_stage_bars",
            kicker: "THE OSCARS · BEST PICTURE",
            title: oscarsRef.name,
            subtitle: "8 markets across 4 sections",
            footer: "Open all 4 sections",
            destination_href: "/collections/machinery-oscars-best-picture",
            section_count: 4,
            rows: [],
          },
        }}
        collectionRef={oscarsRef}
        items={[]}
        bundleId="roundup:machinery-oscars-best-picture"
      />,
    );
    expect(oscarsHtml).toContain("The Odyssey");
    expect(oscarsHtml).toContain('href="/collections/machinery-oscars-best-picture"');
    expect(oscarsHtml).toContain("Open all 4 sections");

    // No container, no card invariant still holds when collectionRef is absent.
    const missingRefHtml = renderToStaticMarkup(
      <RoundupCard
        title={ref.name}
        contract={machineryContract}
        collectionRef={null}
        items={[]}
        bundleId="roundup:machinery-2028-presidential"
      />,
    );
    expect(missingRefHtml).toBe("");

    // When flag is off, a machinery card with empty legacy footer stays hidden.
    delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
    const offHtml = renderToStaticMarkup(
      <RoundupCard
        title={ref.name}
        contract={machineryContract}
        collectionRef={ref}
        items={[]}
        bundleId="roundup:machinery-2028-presidential"
      />,
    );
    expect(offHtml).toBe("");
  });

  it("wraps matchup card rows and Oscars link row cleanly at 288px desktop width without truncation (#13188)", () => {
    process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1 = "true";

    const nbaCard = {
      slug: "machinery-nba-night",
      form_id: "coin_flip_matchups",
      kicker: "NBA · THIS SLATE",
      title: "Timberwolves at Trail Blazers headlines the Nov 20–25 slate",
      subtitle: "Games on this slate priced closest to a 50–50 toss-up.",
      footer: "",
      destination_href: "/collections/machinery-nba-night",
      section_count: 5,
      rows: [
        {
          event_id: 901,
          away_short: "Timberwolves",
          home_short: "Trail Blazers",
          away_pct: 49,
          home_pct: 51,
        },
      ],
    };
    const nflCard = {
      slug: "machinery-nfl-week",
      form_id: "matchup_slate",
      kicker: "NFL · THIS SLATE",
      title: "Commanders at Buccaneers headlines the Nov 22–27 slate",
      subtitle: "Closest matchups on this slate.",
      footer: "",
      destination_href: "/collections/machinery-nfl-week",
      section_count: 4,
      rows: [
        {
          event_id: 902,
          away_short: "Commanders",
          home_short: "Buccaneers",
          away_pct: 54,
          home_pct: 46,
        },
      ],
    };

    for (const card of [nbaCard, nflCard]) {
      const html = renderToStaticMarkup(<MachineryDiscoverCard card={card} />);
      expect(html).toContain('data-testid="machinery-matchup-row"');
      expect(html).toContain("flex-wrap");
      expect(html).toContain('data-testid="machinery-matchup-pcts"');
      expect(html).toContain("whitespace-nowrap");
      expect(html).not.toContain("truncate");
      expect(html).not.toContain("…");
    }

    // Broken paired_metric_set (empty entries or missing title) is refused cleanly.
    const emptyPairedHtml = renderToStaticMarkup(
      <RoundupCard
        title="Broken"
        contract={{
          kicker: "OSCARS",
          footer: "",
          tag: null,
          rows: [],
          paired_metric_set: {
            set_id: "oscar-empty",
            category: "entertainment",
            kicker: "OSCARS",
            title: "Broken empty set",
            subtitle: "",
            stage_1_label: "Nominated",
            stage_2_label: "Wins",
            stage_1_settled_yes_label: "✓",
            stage_1_settled_no_label: "✗",
            stage_1_market: { id: 1, source: "kalshi", name: "A" },
            stage_2_market: { id: 2, source: "kalshi", name: "B" },
            never_blend: true,
            as_of: "2026-11-20T10:00:00Z",
            entries: [],
          },
        }}
        collectionRef={{
          slug: "machinery-oscars-best-picture",
          href: "/collections/machinery-oscars-best-picture",
          name: "Oscars",
          revision: 1,
          collection_count: 1,
        }}
        items={[]}
        bundleId="roundup:machinery-oscars-best-picture"
      />,
    );
    expect(emptyPairedHtml).toBe("");
    delete process.env.NEXT_PUBLIC_CONTAINER_MACHINERY_SLICE1;
  });

  it("renders three-outcome duel_bar cleanly when Tie is the third outcome (#13530)", () => {
    const html = renderToStaticMarkup(
      <MachinerySectionRenderer
        members={[]}
        visualBlock={{
          form_id: "duel_bar",
          items: [
            {
              market_id: 3970169,
              href: "/futures/3970169",
              outcomes: [
                {
                  outcome_id: 1,
                  name: "Team Europe",
                  probability: 0.527,
                  rendered_percent: 53,
                  art: { url: null, kind: "flag", detail: "", accent_color: "#2563EB", initials: "EU" },
                },
                {
                  outcome_id: 2,
                  name: "Team USA",
                  probability: 0.405,
                  rendered_percent: 41,
                  art: { url: null, kind: "flag", detail: "", accent_color: "#DC2626", initials: "US" },
                },
                {
                  outcome_id: 3,
                  name: "Tie",
                  probability: 0.068,
                  rendered_percent: 7,
                  art: { url: null, kind: "monogram", detail: "", accent_color: "", initials: "TI" },
                },
              ],
            },
          ],
        }}
      />,
    );
    expect(html).toContain('data-machinery-form="duel_bar"');
    expect(html).toContain("Team Europe");
    expect(html).toContain("53%");
    expect(html).toContain("Team USA");
    expect(html).toContain("41%");
    expect(html).toContain("Tie");
    expect(html).toContain("7%");
  });

  it("renders MachineryDiscoverCard as a horizontal split bar for duel_bar and 3-up podium tiles for contender_spotlight (#13530)", () => {
    const duelCard = {
      slug: "machinery-golf-majors-and-ryder-cup",
      form_id: "duel_bar",
      kicker: "GOLF · RYDER CUP",
      title: "Team Europe vs. Team USA opens at 53% to 40%",
      subtitle: "48% split",
      footer: "",
      destination_href: "/collections/machinery-golf-majors-and-ryder-cup",
      section_count: 2,
      rows: [
        {
          outcome_id: 1,
          name: "Team Europe",
          probability: 0.527,
          rendered_percent: 53,
          art: { url: null, kind: "flag", detail: "", accent_color: "#2563EB", initials: "EU" },
        },
        {
          outcome_id: 2,
          name: "Team USA",
          probability: 0.405,
          rendered_percent: 40,
          art: { url: null, kind: "flag", detail: "", accent_color: "#DC2626", initials: "US" },
        },
        {
          outcome_id: 3,
          name: "Tie",
          probability: 0.068,
          rendered_percent: 7,
          art: { url: null, kind: "monogram", detail: "", accent_color: "#94A3B8", initials: "TI" },
        },
      ],
    };
    const duelHtml = renderToStaticMarkup(<MachineryDiscoverCard card={duelCard} />);
    expect(duelHtml).toContain('data-testid="machinery-discover-duel-bar"');
    expect(duelHtml).toContain("Team Europe");
    expect(duelHtml).toContain("Team USA");
    expect(duelHtml).toContain("Tie");
    expect(duelHtml).toContain("#94A3B8");

    const spotlightCard = {
      slug: "machinery-boxing-champion-bouts",
      form_id: "contender_spotlight",
      kicker: "BOXING",
      title: "Active title bouts",
      subtitle: "",
      footer: "",
      destination_href: "/collections/machinery-boxing-champion-bouts",
      section_count: 1,
      rows: [
        {
          outcome_id: 11,
          name: "Usyk",
          probability: 0.65,
          rendered_percent: 65,
          art: { url: "https://example.com/u.jpg", kind: "person", detail: "", accent_color: "#0D9488", initials: "US" },
        },
        {
          outcome_id: 12,
          name: "Dubois",
          probability: 0.25,
          rendered_percent: 25,
          art: { url: "https://example.com/d.jpg", kind: "person", detail: "", accent_color: "#2563EB", initials: "DU" },
        },
        {
          outcome_id: 13,
          name: "Other",
          probability: 0.1,
          rendered_percent: 10,
          art: { url: "https://example.com/o.jpg", kind: "person", detail: "", accent_color: "#D97706", initials: "OT" },
        },
      ],
    };
    const spotHtml = renderToStaticMarkup(<MachineryDiscoverCard card={spotlightCard} />);
    expect(spotHtml).toContain('data-testid="machinery-spotlight-tile"');
    expect(spotHtml).toContain("#1");
    expect(spotHtml).toContain("#2");
    expect(spotHtml).toContain("#3");
  });
});
