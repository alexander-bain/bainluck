// #4537 — a Discover crest tile never paints a badge in UNSHIPPABLE_BADGES.
//
// `teamCrestBadge`'s last-word rule has always produced a handful of these for
// real production team names — "Cockfosters FC" COC, "Avispa Fukuoka" FUK,
// "Nigeria" NIG, "Detroit Pistons" PIS — and both Discover duel cards (the
// EventCard tile and DuelKernel's Crest) painted its value verbatim whenever
// the team has no logo. #4466 only promised not to INTRODUCE one; #7270 closed
// the event hero with `shippableCrestBadge`. This closes the two Discover tiles.
//
// Both directions (gotcha #43): the specimens stop painting the slur, AND every
// name whose badge is clean today — including the doubles-pair fragment #4535
// owns — paints exactly the badge it paints on master.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedItem, FeedEventData } from "@/lib/types";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
}));

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { EventCard } from "../../components/discover/EventCard";
import { DuelKernel } from "../../components/discover/kernels/DuelKernel";
import { discoverCrestBadge, teamCrestBadge } from "@/lib/teamShortName";

// Real production names (the #4537 census and #7270's) and the badge
// `teamCrestBadge` gives each of them on master.
const SPECIMENS: Array<[string, string]> = [
  ["Cockfosters FC", "COC"],
  ["Avispa Fukuoka", "FUK"],
  ["Nigeria", "NIG"],
  ["Detroit Pistons", "PIS"],
  ["Titan Italia Titans", "TIT"],
];

const UNSHIPPABLE = [
  "ASS", "FAG", "FUC", "FUK", "CUM", "COC", "COK", "CNT", "KKK",
  "NIG", "SHT", "TIT", "TWA", "WTF", "JIZ", "PIS", "SEX", "HOE",
];

function eventItem(awayTeam: string, homeTeam: string): FeedItem {
  return {
    type: "event",
    headline: "",
    reason: "",
    context_summary: null,
    score: 48,
    data: {
      id: 15300001,
      status: "scheduled",
      commence_time: "2026-09-26T10:00:00Z",
      away_team: awayTeam,
      home_team: homeTeam,
      sport: "soccer_japan_j_league",
      // No logo on either side: the lettered tile is what the reader gets.
      home_team_data: {},
      away_team_data: {},
    } as unknown as FeedEventData,
  } as unknown as FeedItem;
}

/** The text of every lettered 64px tile in the markup, in DOM order. */
function tiles(html: string): string[] {
  return [...html.matchAll(/<div class="[^"]*\bh-16\b[^"]*\bplace-items-center\b[^"]*"[^>]*>([^<]*)<\/div>/g)]
    .map(m => m[1]);
}

function renderEventCard(awayTeam: string, homeTeam: string): string {
  const item = eventItem(awayTeam, homeTeam);
  return renderToStaticMarkup(
    <EventCard
      item={item}
      data={item.data as FeedEventData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

function renderDuel(awayTeam: string, homeTeam: string): string {
  return renderToStaticMarkup(
    <DuelKernel
      state="upcoming"
      awayTeam={awayTeam}
      homeTeam={homeTeam}
      awayColor="#132448"
      homeColor="#BD3039"
      gradientKey="soccer"
      categorySlug="soccer"
      categoryLabel="J1 League"
      categoryEmoji="⚽"
      awayProb={0.5}
      homeProb={0.3}
      stateLabel="Sat 7:00 PM"
    />,
  );
}

describe("#4537 — the specimens still discriminate on master's rule", () => {
  // Control: without it, a later change to `teamCrestBadge` that stops emitting
  // these would leave every assertion below passing for the wrong reason.
  it.each(SPECIMENS)("teamCrestBadge(%s) is still %s", (name, slur) => {
    expect(teamCrestBadge(name)).toBe(slur);
  });
});

describe("#4537 — discoverCrestBadge never returns an unshippable badge", () => {
  it.each(SPECIMENS)("%s does not paint %s", (name, slur) => {
    const badge = discoverCrestBadge(name);
    expect(badge).not.toBe(slur);
    expect(UNSHIPPABLE).not.toContain(badge);
  });

  it("falls back to the event hero's clean initials", () => {
    expect(discoverCrestBadge("Cockfosters FC")).toBe("CF");
    expect(discoverCrestBadge("Avispa Fukuoka")).toBe("AF");
    expect(discoverCrestBadge("Detroit Pistons")).toBe("DP");
    // Both candidates unshippable: an empty tile, never a slur (notice 34).
    expect(discoverCrestBadge("Titan Italia Titans")).toBe("");
  });

  it("leaves every clean badge exactly as master paints it", () => {
    const clean = [
      "Paris Saint Germain", "Paris Saint-Germain", "New York Mets",
      "Boston Red Sox", "Ipswich Town", "Real Madrid", "Al Sadd SC",
      "Arizona State Sun Devils", "Kansas Jayhawks", "Warrington Town FC",
      // #4535's doubles fragments keep master's value: the whitespace case is
      // that issue's decision, not this one's.
      "Ho / Liutarevich", "de Minaur / Peers", "Hunter / Krawczyk",
    ];
    for (const name of clean) {
      expect([name, discoverCrestBadge(name)]).toEqual([name, teamCrestBadge(name)]);
    }
    expect(discoverCrestBadge("Ho / Liutarevich")).toBe("HO ");
    expect(discoverCrestBadge(null)).toBe("");
    expect(discoverCrestBadge("")).toBe("");
  });
});

describe("#4537 — the Discover tiles as rendered", () => {
  it("the EventCard tile does not paint FUK or COC", () => {
    const painted = tiles(renderEventCard("Avispa Fukuoka", "Cockfosters FC"));
    expect(painted).toEqual(["AF", "CF"]);
  });

  it("the DuelKernel crest does not paint NIG or PIS", () => {
    const painted = tiles(renderDuel("Nigeria", "Detroit Pistons"));
    expect(painted).toHaveLength(2);
    for (const badge of painted) expect(UNSHIPPABLE).not.toContain(badge);
    expect(painted).toEqual([discoverCrestBadge("Nigeria"), "DP"]);
  });

  it("an ordinary fixture's tiles are unchanged", () => {
    // The tile reader is a positive control too: it must find both tiles.
    expect(tiles(renderEventCard("New York Mets", "Boston Red Sox"))).toEqual(["NYM", "BRS"]);
    expect(tiles(renderDuel("Real Madrid", "Ipswich Town"))).toEqual(["MAD", "IPS"]);
  });
});
