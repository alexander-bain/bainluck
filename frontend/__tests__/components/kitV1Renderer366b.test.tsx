/**
 * #13551 (Rulings 366: B, 367: A, and Fable's 7 rules) — Kit v1 renderer tests.
 */
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { KitCardRenderer } from "@/components/discover/kit/KitCardRenderer";
import type { KitV1CardSpec } from "@/components/discover/kit/types";

const IMG = "https://a.espncdn.com/i/teamlogos/ncaa/500/61.png";

const SAMPLE_CARDS: KitV1CardSpec[] = [
  {
    kit_version: 1,
    look: "scoreboard_grid",
    kicker: "SPORTS · COLLEGE FOOTBALL",
    common_headline: "College Football Playoff and SEC Championship leaders",
    stat_caption: "Georgia leads the college football national championship at 34%",
    refusal_reason: null,
    data: {
      columns: [
        { key: "181", label: "National Championship" },
        { key: "233", label: "SEC Championship" },
      ],
      rows: [
        { rank: 1, name: "Georgia", image_url: IMG, image_kind: "team", cells: { "181": 34, "233": 68 } },
        { rank: 2, name: "Texas", image_url: IMG, image_kind: "team", cells: { "181": 11, "233": 26 } },
        { rank: 3, name: "Alabama", image_url: IMG, image_kind: "team", cells: { "181": 10, "233": 3 } },
        { rank: 4, name: "Tennessee", image_url: IMG, image_kind: "team", cells: { "181": 4, "233": 3 } },
      ],
    },
  },
  {
    kit_version: 1,
    look: "dated_tiles",
    kicker: "GEOPOLITICS",
    common_headline: "Middle East ceasefire and leadership timelines",
    stat_caption: "US x Iran ceasefire climbs to 81% by Dec 31",
    refusal_reason: null,
    data: {
      aligned: true,
      columns: [
        { key: "2026-11-30", label: "Nov 30 '26" },
        { key: "2026-12-31", label: "Dec 31 '26" },
      ],
      rows: [
        {
          name: "US x Iran Ceasefire",
          image_url: "https://flagcdn.com/w320/us.png",
          image_kind: "flag",
          cells: { "2026-11-30": 66, "2026-12-31": 81 },
        },
      ],
    },
  },
  {
    kit_version: 1,
    look: "countdown",
    kicker: "SAME DEADLINE",
    common_headline: "By December 31",
    stat_caption: "Next Claude Opus leads at 85%",
    refusal_reason: null,
    data: {
      days_left: 38,
      deadline_label: "all of these end on Dec 31",
      rows: [{ name: "Next Claude Opus", p: 85, image_url: IMG, image_kind: "topic" }],
    },
  },
  {
    kit_version: 1,
    look: "road_ahead",
    kicker: "NBA · NEXT 3 GAMES",
    common_headline: "Boston Celtics: next 3 games",
    stat_caption: "Boston opens at 79% in Washington",
    refusal_reason: null,
    data: {
      team_name: "Boston Celtics",
      team_abbr: "BOS",
      team_color: null,
      team_image_url: "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
      rows: [
        {
          opponent_name: "Washington Wizards",
          opponent_abbr: "WSH",
          opponent_color: null,
          opponent_image_url: "https://a.espncdn.com/i/teamlogos/nba/500/wsh.png",
          home_or_away: "at",
          day: "Tue Nov 24",
          clock: "5:00 PM PT",
          team_p: 79,
        },
      ],
    },
  },
  {
    kit_version: 1,
    look: "bubble_line",
    kicker: "HOCKEY · NHL PLAYOFFS",
    common_headline: "2026–27 NHL Playoffs picture",
    stat_caption: "Washington sits at 54% inside the bubble",
    refusal_reason: null,
    data: {
      band_low: 25,
      band_high: 75,
      band_label: "in doubt",
      low_count: 10,
      high_count: 13,
      doubt_summary: "WSH 54% · NYR 47%",
      points: [
        { name: "Washington Capitals", abbr: "WSH", p: 54, lane: 0, in_doubt: true, color: null, image_url: IMG },
        { name: "Edmonton Oilers", abbr: "EDM", p: 98, lane: null, in_doubt: false, color: null, image_url: IMG },
      ],
    },
  },
  {
    kit_version: 1,
    look: "one_in_n",
    kicker: "ODD · SIDE QUESTS",
    common_headline: "Elon Musk's wildest side quests",
    stat_caption: "Visiting Mars leads at 12% (1 in 8)",
    refusal_reason: null,
    data: {
      rows: [
        {
          name: "Will Elon Musk visit Mars in his lifetime?",
          p: 12,
          one_in_n: 8,
          image_url: "https://image.tmdb.org/t/p/w185/i5a0XRXLfu0meGB3g5Sy4qP8pY.jpg",
          image_kind: "person",
        },
      ],
    },
  },
  {
    kit_version: 1,
    look: "single_sport_slate",
    kicker: "NBA · THIS SLATE",
    common_headline: "Tonight's NBA Slate",
    stat_caption: "Pistons at Magic headlines",
    refusal_reason: null,
    data: {
      sport_key: "basketball_nba",
      league_label: "NBA",
      rows: [
        {
          away: { name: "Memphis Grizzlies", abbr: "MEM", color: null, image_url: IMG, p: 49 },
          home: { name: "Charlotte Hornets", abbr: "CHA", color: null, image_url: IMG, p: 51 },
          day: "Mon Nov 23",
          clock: "4:00 PM PT",
          status: "live",
          score: [28, 32],
        },
      ],
    },
  },
  {
    kit_version: 1,
    look: "calendar_strip",
    kicker: "CULTURE · 2026",
    common_headline: "When will Spotify release 2026 Wrapped?",
    stat_caption: "Spotify Wrapped is most likely to arrive on Wednesday, December 2 (67%)",
    refusal_reason: null,
    data: {
      month_span_label: "Nov 27 – Dec 4",
      show_percent: true,
      ladder_rule_note: "The percent in a day is the chance it arrives that day: one rung of the ladder minus the rung before it.",
      ladder_footer: "Served ladder: 18% before Dec 2 · 85% before Dec 3",
      days: [
        { dow: "Tue", day_num: "1", month_abbr: "Dec", daily_pct: 6, is_peak: false },
        { dow: "Wed", day_num: "2", month_abbr: "Dec", daily_pct: 67, is_peak: true },
      ],
    },
  },
];

describe("Kit v1 web renderer (366: B, 367: A, 7 rules)", () => {
  test("renders all 8 worked examples with expected labels and percents", () => {
    const rendered = SAMPLE_CARDS.map((c) => renderToStaticMarkup(<KitCardRenderer spec={c} />));
    expect(rendered[0]).toContain("Georgia");
    expect(rendered[0]).toContain(">4<");
    expect(rendered[1]).toContain("by Dec 31");
    expect(rendered[1]).toContain("81%");
    expect(rendered[2]).toContain("38");
    expect(rendered[2]).toContain("days left");
    expect(rendered[3]).toContain("at WSH");
    expect(rendered[4]).toContain("in doubt");
    expect(rendered[5]).toContain("1 in 8");
    expect(rendered[5]).toContain("12%");
    expect(rendered[6]).toContain("NBA");
    expect(rendered[6]).not.toContain("Rule 6");
    expect(rendered[6]).toContain("Live · 28–32");
    expect(rendered[7]).toContain("67%");
    expect(rendered[7]).toContain("Daily chance");
    expect(rendered[7]).not.toContain("367: A");
    expect(rendered[7]).toContain("one rung of the ladder minus the rung before it");
  });

  test("renders explicit Rule 1 fallback card when refusal_reason is present", () => {
    const html = renderToStaticMarkup(
      <KitCardRenderer
        spec={{
          kit_version: 1,
          look: null,
          fallback_today: true,
          refusal_reason: "Slate mixes >1 sport_key; keep today's card.",
        }}
      />,
    );
    expect(html).toContain("Rule 1 fallback");
    expect(html).toContain("Slate mixes &gt;1 sport_key");
  });

  test("uses light-mode semantic tokens only with zero dark classes or raw hexes", () => {
    const src = fs.readFileSync(
      path.join(process.cwd(), "components", "discover", "kit", "KitCardRenderer.tsx"),
      "utf-8",
    );
    expect(src).not.toMatch(/\bdark:/);
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,6}/);
  });
});
