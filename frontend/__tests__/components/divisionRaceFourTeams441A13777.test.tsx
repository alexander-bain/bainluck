import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import MachinerySectionRenderer, {
  MachineryDiscoverCard,
  type MachineryCardContract,
} from "@/components/collections/MachinerySectionRenderer";
import type { MachineryVisualBlock } from "@/lib/collections";
import {
  describeMachineryOutcomeDisplay,
  ELIMINATED_LABEL,
  NO_RECENT_PROBABILITY_LABEL,
} from "@/lib/machineryOutcomeDisplay";
import { patchMachineryVisualBlock } from "@/lib/machineryVisualBlockPatch";
import type { FeedFuturesData, FeedItem } from "@/lib/types";

const NFL_ART = (abbr: string) => ({
  url: `https://a.espncdn.com/i/teamlogos/nfl/500/${abbr}.png`,
  kind: "team_logo",
  detail: "",
  accent_color: "#002244",
  initials: abbr.toUpperCase(),
});

describe("441: A (#13777) NFL division race four-team website rendering", () => {
  it("describes >=1%, <1%, settled-out Eliminated, and missing No recent probability states", () => {
    expect(
      describeMachineryOutcomeDisplay({
        probability: 0.525,
        rendered_percent: 53,
        unfloored_percent: 53,
        settled_out: false,
      }),
    ).toEqual({
      state: "live",
      label: "53%",
      barWidthPercent: 53,
      muted: false,
    });

    expect(
      describeMachineryOutcomeDisplay({
        probability: 0.01,
        rendered_percent: 1,
        unfloored_percent: 1,
        settled_out: false,
      }),
    ).toEqual({
      state: "live",
      label: "1%",
      barWidthPercent: 4,
      muted: false,
    });

    for (const p of [0.0099, 0.004, 0.0005]) {
      expect(
        describeMachineryOutcomeDisplay({
          probability: p,
          rendered_percent: 1,
          unfloored_percent: 0,
          settled_out: false,
        }),
      ).toEqual({
        state: "sub_one_percent",
        label: "<1%",
        barWidthPercent: 2,
        muted: true,
      });
    }

    // Settled out prints "Eliminated" with empty track even if a residue number arrived
    expect(
      describeMachineryOutcomeDisplay({
        probability: 0.005,
        rendered_percent: 1,
        settled_out: true,
      }),
    ).toEqual({
      state: "eliminated",
      label: ELIMINATED_LABEL,
      barWidthPercent: 0,
      muted: true,
    });

    // Missing/unpriced with settled_out: false prints "No recent probability" with empty track
    expect(
      describeMachineryOutcomeDisplay({
        probability: null,
        rendered_percent: null,
        settled_out: false,
      }),
    ).toEqual({
      state: "no_recent_probability",
      label: NO_RECENT_PROBABILITY_LABEL,
      barWidthPercent: 0,
      muted: true,
    });

    // Non-division cards omit settled_out and keep exact existing formatGroupedProbability behaviour
    expect(
      describeMachineryOutcomeDisplay({
        probability: 0.004,
        rendered_percent: 1,
        unfloored_percent: 0,
      }),
    ).toEqual({
      state: "live",
      label: "<1%",
      barWidthPercent: 4,
      muted: false,
    });
    expect(
      describeMachineryOutcomeDisplay({
        probability: 0.0099,
        rendered_percent: 1,
        unfloored_percent: 1,
      }),
    ).toEqual({
      state: "live",
      label: "1%",
      barWidthPercent: 4,
      muted: false,
    });
  });

  it("renders all four teams and exact labels on both MachineryDiscoverCard and SiblingFieldsGridBlock", () => {
    const outcomes = [
      {
        outcome_id: 846594,
        name: "Denver",
        probability: 0.525,
        rendered_percent: 53,
        unfloored_percent: 53,
        settled_out: false,
        art: NFL_ART("den"),
      },
      {
        outcome_id: 846593,
        name: "Kansas City",
        probability: 0.009,
        rendered_percent: 1,
        unfloored_percent: 1,
        settled_out: false,
        art: NFL_ART("kc"),
      },
      {
        outcome_id: 846592,
        name: "Los Angeles Chargers",
        probability: null,
        rendered_percent: null,
        unfloored_percent: null,
        settled_out: false,
        art: NFL_ART("lac"),
      },
      {
        outcome_id: 846591,
        name: "Las Vegas",
        probability: null,
        rendered_percent: null,
        unfloored_percent: null,
        settled_out: true,
        art: NFL_ART("lv"),
      },
    ];

    const card: MachineryCardContract = {
      slug: "machinery-afc-west-duel",
      form_id: "sibling_fields_grid",
      kicker: "SPORTS · NFL DIVISIONS",
      title: "Denver leads AFC West at 53%, with Chicago leading NFC North at 50%",
      subtitle: "All four AFC West teams in the division title race.",
      footer: "",
      scale_ordered: false,
      section_count: 2,
      destination_href: "/collections/machinery-afc-west-duel",
      rows: outcomes,
    };

    const cardHtml = renderToStaticMarkup(<MachineryDiscoverCard card={card} />);
    expect(cardHtml).toContain("Denver");
    expect(cardHtml).toContain("53%");
    expect(cardHtml).toContain("Kansas City");
    expect(cardHtml).toContain("&lt;1%");
    expect(cardHtml).toContain("Los Angeles Chargers");
    expect(cardHtml).toContain("No recent probability");
    expect(cardHtml).toContain("Las Vegas");
    expect(cardHtml).toContain("Eliminated");
    expect(cardHtml).not.toContain("<span>—</span>");

    const rowStates = Array.from(
      cardHtml.matchAll(/data-outcome-state="([^"]+)"/g),
      (m) => m[1],
    );
    expect(rowStates).toEqual([
      "live",
      "sub_one_percent",
      "no_recent_probability",
      "eliminated",
    ]);
    // Empty tracks for eliminated & no_recent_probability; filled bars only for live & sub_one_percent
    const rowBlocks = cardHtml.split('data-outcome-state="').slice(1);
    expect(rowBlocks[0]).toContain("width:53%");
    expect(rowBlocks[1]).toContain("width:2%");
    expect(rowBlocks[2]).not.toContain('style="width:');
    expect(rowBlocks[3]).not.toContain('style="width:');

    const vb: MachineryVisualBlock = {
      form_id: "sibling_fields_grid",
      initial_visible_limit: 4,
      items: [
        {
          market_id: 53675,
          title: "AFC West",
          href: "/futures/53675",
          scale_ordered: false,
          outcomes,
        },
      ],
    };
    const secHtml = renderToStaticMarkup(
      <MachinerySectionRenderer visualBlock={vb} members={[]} />,
    );
    expect(secHtml).toContain("Denver");
    expect(secHtml).toContain("53%");
    expect(secHtml).toContain("&lt;1%");
    expect(secHtml).toContain("No recent probability");
    expect(secHtml).toContain("Eliminated");

    const secStates = Array.from(
      secHtml.matchAll(/data-outcome-state="([^"]+)"/g),
      (m) => m[1],
    );
    expect(secStates).toEqual([
      "live",
      "sub_one_percent",
      "no_recent_probability",
      "eliminated",
    ]);
    const secBlocks = secHtml.split('data-outcome-state="').slice(1);
    expect(secBlocks[0]).toContain("width:53%");
    expect(secBlocks[1]).toContain("width:2%");
    expect(secBlocks[2]).not.toContain('style="width:');
    expect(secBlocks[3]).not.toContain('style="width:');
  });

  it("keeps non-division cards unchanged and prevents live patch from overwriting settled_out rows", () => {
    const regularCard: MachineryCardContract = {
      slug: "machinery-european-league-titles",
      form_id: "sibling_fields_grid",
      kicker: "SPORTS · SOCCER",
      title: "Arsenal leads Premier League at 73%",
      subtitle: "Title races across Europe.",
      footer: "",
      scale_ordered: false,
      section_count: 1,
      destination_href: "/collections/machinery-european-league-titles",
      rows: [
        {
          outcome_id: 1,
          name: "Arsenal",
          probability: 0.73,
          rendered_percent: 73,
          art: NFL_ART("den"),
        },
        {
          outcome_id: 2,
          name: "Underdog",
          probability: 0.008,
          rendered_percent: 1,
          unfloored_percent: 1,
          art: NFL_ART("kc"),
        },
      ],
    };
    const regHtml = renderToStaticMarkup(<MachineryDiscoverCard card={regularCard} />);
    expect(regHtml).toContain("73%");
    expect(regHtml).toContain("1%");
    expect(regHtml).not.toContain("Eliminated");
    expect(regHtml).not.toContain("No recent probability");

    const vb: MachineryVisualBlock = {
      form_id: "sibling_fields_grid",
      items: [
        {
          market_id: 53675,
          outcomes: [
            {
              outcome_id: 846594,
              name: "Denver",
              probability: 0.525,
              rendered_percent: 53,
              unfloored_percent: 53,
              settled_out: false,
              art: NFL_ART("den"),
            },
            {
              outcome_id: 846591,
              name: "Las Vegas",
              probability: null,
              rendered_percent: null,
              unfloored_percent: null,
              settled_out: true,
              art: NFL_ART("lv"),
            },
          ],
        },
      ],
    };
    const priced = new Map<string, FeedItem>([
      [
        "futures-53675",
        {
          type: "futures",
          score: 50,
          reason: "",
          headline: null,
          data: {
            id: 53675,
            name: "AFC West Division Winner",
            status: "open",
            source: "kalshi",
            top_outcomes: [
              { id: 846594, name: "Denver", probability: 0.57, rendered_percent: 57 },
              { id: 846591, name: "Las Vegas", probability: 0.005, rendered_percent: 1 },
            ],
          } as unknown as FeedFuturesData,
        } satisfies FeedItem,
      ],
    ]);
    const patched = patchMachineryVisualBlock(vb, priced);
    const patchedOutcomes = (patched.items?.[0]?.outcomes ?? []) as Array<Record<string, unknown>>;
    expect(patchedOutcomes[0].rendered_percent).toBe(57);
    expect(patchedOutcomes[0].unfloored_percent).toBe(57);
    expect(patchedOutcomes[1].settled_out).toBe(true);
    expect(patchedOutcomes[1].probability).toBeNull();
    expect(patchedOutcomes[1].rendered_percent).toBeNull();
  });
});
