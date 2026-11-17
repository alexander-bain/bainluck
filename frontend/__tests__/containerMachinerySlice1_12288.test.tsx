import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  isMachinerySlice1Enabled,
} from "@/components/collections/MachinerySectionRenderer";
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
      </div>,
    );
    expect(html).toContain('data-testid="machinery-discover-card"');
    expect(html).toContain('href="/collections/machinery-2028-presidential"');
    expect(html).toContain("Jon Ossoff");
    expect(html).toContain("One Battle After Another");
    expect(html).toContain("Buffalo Bills");
    expect(html).toContain("Open all 4 sections");
  });
});
