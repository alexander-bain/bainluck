/**
 * Ruling 194-A (Alex, 2026-11-14):
 * - On the website, college teams print the school, not the mascot
 *   (Duke, Alabama, Gonzaga, Ole Miss; never Blue Devils, Crimson Tide,
 *   Bulldogs, Rebels).
 * - The badge shown when a logo is missing uses the served abbreviation
 *   (DUKE, ALA), not letters made from the mascot.
 * - Professional teams are unchanged.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), prefetch: jest.fn() }),
  usePathname: () => "/events/990194",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "990194" }),
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

import {
  collegeSchoolName,
  discoverCrestBadge,
  isCollegeSport,
  servedCollegeAbbreviation,
  shippableCrestBadge,
  teamCrestInitials,
  teamShortName,
  teamShortNames,
} from "@/lib/teamShortName";
import EventCard183A, { buildUnifiedCardFromEvent } from "@/components/EventCard183A";
import TeamNameLink from "@/components/TeamNameLink";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

describe("Ruling 194-A — college teams print the school, never the mascot", () => {
  it("recognizes every NCAA sport key and rejects professional leagues", () => {
    for (const key of [
      "americanfootball_ncaaf",
      "americanfootball_ncaaf_fcs",
      "basketball_ncaab",
      "basketball_wncaab",
      "baseball_ncaa",
      "lacrosse_ncaa",
    ]) {
      expect(isCollegeSport(key)).toBe(true);
    }
    for (const key of [
      null,
      undefined,
      "",
      "americanfootball_nfl",
      "basketball_nba",
      "basketball_wnba",
      "baseball_mlb",
      "icehockey_nhl",
      "soccer_epl",
      "tennis_atp",
    ]) {
      expect(isCollegeSport(key)).toBe(false);
    }
  });

  it("prints the school for Alex's named specimens and tricky live NCAA names", () => {
    const cases: Array<[string, string, string]> = [
      ["basketball_ncaab", "Duke Blue Devils", "Duke"],
      ["americanfootball_ncaaf", "Alabama Crimson Tide", "Alabama"],
      ["basketball_ncaab", "Gonzaga Bulldogs", "Gonzaga"],
      ["americanfootball_ncaaf", "Ole Miss Rebels", "Ole Miss"],
      ["basketball_ncaab", "North Carolina Tar Heels", "North Carolina"],
      ["americanfootball_ncaaf", "Notre Dame Fighting Irish", "Notre Dame"],
      ["americanfootball_ncaaf", "Penn State Nittany Lions", "Penn State"],
      ["americanfootball_ncaaf", "Wake Forest Demon Deacons", "Wake Forest"],
      ["americanfootball_ncaaf", "Georgia Tech Yellow Jackets", "Georgia Tech"],
      ["basketball_ncaab", "St. John's Red Storm", "St. John's"],
      ["basketball_ncaab", "Cornell Big Red", "Cornell"],
      ["basketball_ncaab", "DePaul Blue Demons", "DePaul"],
      ["basketball_ncaab", "Syracuse Orange", "Syracuse"],
      ["americanfootball_ncaaf", "Stanford Cardinal", "Stanford"],
      ["basketball_ncaab", "Harvard Crimson", "Harvard"],
      ["americanfootball_ncaaf", "Miami (OH) RedHawks", "Miami (OH)"],
      ["basketball_ncaab", "NC State Wolfpack", "NC State"],
      ["americanfootball_ncaaf", "Texas Longhorns", "Texas"],
      ["basketball_wncaab", "Alabama Crimson Tide (W)", "Alabama"],
      ["basketball_wncaab", "Ole Miss Rebels (W)", "Ole Miss"],
    ];
    for (const [sport, full, expectedSchool] of cases) {
      expect(teamShortName(full, null, sport)).toBe(expectedSchool);
      // Idempotence: feeding a mascot-less school back in leaves it intact.
      expect(collegeSchoolName(expectedSchool)).toBe(expectedSchool);
      expect(teamShortName(expectedSchool, null, sport)).toBe(expectedSchool);
    }
  });

  it("preserves mascot-less multi-word schools served directly by venues", () => {
    for (const bareSchool of [
      "Virginia Tech",
      "Georgia Tech",
      "Boston University",
      "Abilene Christian",
      "Cal State Northridge",
      "Central Arkansas",
      "Charleston Southern",
      "Detroit Mercy",
      "Rhode Island",
      "San Diego",
      "Saint Louis",
      "Seton Hall",
      "St. Bonaventure",
      "UC Santa Barbara",
    ]) {
      expect(teamShortName(bareSchool, null, "basketball_wncaab")).toBe(bareSchool);
    }
  });

  it("separates Bulldogs vs Bulldogs by school without falling back to airport codes", () => {
    expect(
      teamShortNames(
        { name: "Gonzaga Bulldogs", abbreviation: "GONZ" },
        { name: "Georgia Bulldogs", abbreviation: "UGA" },
        "basketball_ncaab",
      ),
    ).toEqual({ home: "Gonzaga", away: "Georgia" });

    expect(
      teamShortNames(
        { name: "Ole Miss Rebels", abbreviation: "MISS" },
        { name: "Virginia Tech Hokies", abbreviation: "VT" },
        "americanfootball_ncaaf",
      ),
    ).toEqual({ home: "Ole Miss", away: "Virginia Tech" });
  });

  it("leaves professional teams completely unchanged", () => {
    expect(teamShortName("Boston Celtics", null, "basketball_nba")).toBe("Celtics");
    expect(teamShortName("Boston Red Sox", null, "baseball_mlb")).toBe("Red Sox");
    expect(teamShortName("Portland Trail Blazers", null, "basketball_nba")).toBe("Trail Blazers");
    expect(teamShortName("Vegas Golden Knights", null, "icehockey_nhl")).toBe("Golden Knights");
    expect(teamShortName("Kansas City Chiefs", null, "americanfootball_nfl")).toBe("Chiefs");
  });
});

describe("Ruling 194-A — missing-logo badge uses the served abbreviation", () => {
  it("uses served college abbreviations (DUKE, ALA, GONZ, MISS) across all badge helpers", () => {
    expect(shippableCrestBadge("Duke Blue Devils", "basketball_ncaab", "DUKE")).toBe("DUKE");
    expect(shippableCrestBadge("Alabama Crimson Tide", "americanfootball_ncaaf", "ALA")).toBe("ALA");
    expect(discoverCrestBadge("Gonzaga Bulldogs", "basketball_ncaab", "GONZ")).toBe("GONZ");
    expect(discoverCrestBadge("Ole Miss Rebels", "americanfootball_ncaaf", "MISS")).toBe("MISS");
    expect(teamCrestInitials("Duke Blue Devils", "basketball_ncaab", "DUKE")).toBe("DUKE");
    expect(teamCrestInitials("Alabama Crimson Tide", "americanfootball_ncaaf", "ALA")).toBe("ALA");
    expect(teamCrestInitials("Texas A&M Aggies", "americanfootball_ncaaf", "TA&M")).toBe("TA&M");
    expect(teamCrestInitials("Miami (OH) RedHawks", "americanfootball_ncaaf", "M-OH")).toBe("M-OH");
  });

  it("falls back to school letters — never mascot letters — when abbreviation is absent or a full name", () => {
    expect(servedCollegeAbbreviation("BOSTON UNIVERSITY")).toBe("");
    expect(servedCollegeAbbreviation("DARTMOUTH")).toBe("");
    expect(shippableCrestBadge("Gonzaga Bulldogs", "basketball_ncaab", null)).toBe("GON");
    expect(shippableCrestBadge("Duke Blue Devils", "basketball_ncaab", null)).toBe("DUK");
    expect(shippableCrestBadge("Alabama Crimson Tide (W)", "basketball_wncaab", null)).toBe("ALA");
    expect(
      shippableCrestBadge("Boston University Terriers", "basketball_ncaab", "BOSTON UNIVERSITY"),
    ).toBe("BU");
  });

  it("renders school names and served-abbreviation badges on game cards without logos", () => {
    const ncaafEvent = {
      id: 990194,
      sport: "americanfootball_ncaaf",
      sport_name: "NCAAF",
      home_team: "Alabama Crimson Tide",
      away_team: "Duke Blue Devils",
      commence_time: "2026-11-21T20:30:00Z",
      status: "scheduled",
      home_score: null,
      away_score: null,
      home_team_data: { abbreviation: "ALA", primary_color: "#9E1B32" },
      away_team_data: { abbreviation: "DUKE", primary_color: "#003087" },
      current_odds: { home_probability: 0.68, away_probability: 0.32 },
      opening_odds: { home_probability: 0.64, away_probability: 0.36 },
    } as unknown as Event;

    const cardHtml = renderToStaticMarkup(
      <EventCard183A card={buildUnifiedCardFromEvent(ncaafEvent)} surface="standard" />,
    );
    expect(cardHtml).toContain(">Duke<");
    expect(cardHtml).toContain(">Alabama<");
    expect(cardHtml).not.toContain("Blue Devils");
    expect(cardHtml).not.toContain("Crimson Tide");
    expect(cardHtml).toContain(">DUKE<");
    expect(cardHtml).toContain(">ALA<");

    const feedItem = {
      type: "event",
      headline: "",
      reason: "",
      context_summary: null,
      score: 60,
      data: {
        ...ncaafEvent,
      } as unknown as FeedEventData,
    } as unknown as FeedItem;

    const discoverHtml = renderToStaticMarkup(
      <DiscoverEventCard
        item={feedItem}
        data={feedItem.data as FeedEventData}
        liked={false}
        setLiked={() => {}}
        trending={false}
      />,
    );
    expect(discoverHtml).toContain(">DUKE<");
    expect(discoverHtml).toContain(">ALA<");
    expect(discoverHtml).toContain("Duke @ Alabama");
    expect(discoverHtml).not.toContain("Blue Devils");
    expect(discoverHtml).not.toContain("Crimson Tide");

    const collegeLinkHtml = renderToStaticMarkup(
      <TeamNameLink name="Gonzaga Bulldogs" sportKey="basketball_ncaab" />,
    );
    expect(collegeLinkHtml).toContain(">Gonzaga<");
    expect(collegeLinkHtml).not.toContain("Bulldogs");

    const proLinkHtml = renderToStaticMarkup(
      <TeamNameLink name="Boston Celtics" sportKey="basketball_nba" />,
    );
    expect(proLinkHtml).toContain(">Boston Celtics<");
  });
});
