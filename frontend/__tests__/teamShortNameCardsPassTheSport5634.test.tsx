/**
 * #5634 (club half) — the cards hand the sport to the name rule.
 *
 * WHAT THE READER SAW: `/sport/soccer/soccer_germany_bundesliga/team/union-berlin`,
 * 390px, 2026-09-27 23:40Z — both upcoming-game bars were labelled **"Berlin"**
 * ("Berlin · Elversberg 58%", "Berlin · Dortmund 79%"). The football whole-name
 * rule already existed (`keepsWholeClubName`), but it is opened by the SPORT, and
 * the team card, the league/sports card's finished score strip, its "Opened"
 * footer, the Discover card's winner line and the sportsbook table's column
 * headers all called `teamShortNames` without one — so they printed the
 * last-word rule's city while the event hero two clicks away said
 * "Union Berlin".
 *
 * Two guards: the team card rendered with the real shape (both directions — the
 * sport is what moves the label), and a census of every call site, so a new
 * sport-less caller has to be named here rather than slip past.
 */

import * as fs from "fs";
import * as path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { UpcomingGameCard } from "@/components/TeamGameCards";
import type { TeamGameBrief } from "@/lib/api";

/** Every text node the card paints, trimmed — one entry per element. */
function texts(el: React.ReactElement): string[] {
  return renderToStaticMarkup(el)
    .split(/<[^>]+>/)
    .map((t) => t.replace(/&amp;/g, "&").trim())
    .filter(Boolean);
}

function game(sportKey: string | null): TeamGameBrief {
  return {
    id: 15313589,
    home_team: "Union Berlin",
    away_team: "Elversberg",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: "2099-10-10T13:30:00Z",
    sport_key: sportKey,
    is_home: true,
    opponent: "Elversberg",
    win_probability: 0.42,
  } as TeamGameBrief;
}

describe("#5634 — the team page's bar names the club, not its city", () => {
  it("a Bundesliga game labels Union Berlin's end of the bar 'Union Berlin'", () => {
    const t = texts(
      <UpcomingGameCard game={game("soccer_germany_bundesliga")} teamName="Union Berlin" teamColor={null} />,
    );
    expect(t).toContain("Union Berlin");
    expect(t).not.toContain("Berlin");
  });

  it("the sport is what moved it: the same card without one keeps the shipped 'Berlin'", () => {
    const t = texts(<UpcomingGameCard game={game(null)} teamName="Union Berlin" teamColor={null} />);
    expect(t).toContain("Berlin");
    expect(t).not.toContain("Union Berlin");
  });

  it("an MLB card is unchanged by the sport: 'Red Sox', not the full name", () => {
    const mlb = {
      ...game("baseball_mlb"),
      home_team: "Boston Red Sox",
      away_team: "Kansas City Royals",
      opponent: "Kansas City Royals",
    };
    const t = texts(<UpcomingGameCard game={mlb} teamName="Boston Red Sox" teamColor={null} />);
    expect(t).toContain("Red Sox");
  });
});

/** Every `teamShortName(s)(` call outside the helper, with its argument count. */
function callSites(): Array<{ file: string; args: number }> {
  const root = path.join(__dirname, "..");
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(path.join(root, dir), { withFileTypes: true })) {
      const rel = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (!/^(node_modules|__tests__|\.next)$/.test(e.name)) walk(rel);
      } else if (/\.tsx?$/.test(e.name) && rel !== path.join("lib", "teamShortName.ts")) {
        files.push(rel);
      }
    }
  };
  ["app", "components", "lib"].forEach(walk);

  const out: Array<{ file: string; args: number }> = [];
  for (const file of files) {
    const src = fs.readFileSync(path.join(root, file), "utf8");
    const re = /\bteamShortNames?\(/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(src))) {
      let i = m.index + m[0].length;
      let depth = 1;
      const start = i;
      for (; i < src.length && depth > 0; i++) {
        if ("([{".includes(src[i])) depth++;
        else if (")]}".includes(src[i])) depth--;
      }
      const inner = src.slice(start, i - 1).trim().replace(/,\s*$/, "");
      let d = 0;
      let args = inner ? 1 : 0;
      for (const c of inner) {
        if ("([{".includes(c)) d++;
        else if (")]}".includes(c)) d--;
        else if (c === "," && d === 0) args++;
      }
      out.push({ file, args });
    }
  }
  return out;
}

describe("#5634 — every name-painting call site passes the sport, or is named here", () => {
  // The only callers allowed to omit it, each for a stated reason:
  //  - RelatedFutures: title/playoff/win-total pairs of US leagues (no football
  //    club reaches them), plus `MatchupGrid`, declared and never called.
  //  - SeriesProbability: best-of playoff series, a US-league shape.
  //  - DuelKernel: a presentation kernel that is deliberately handed no sport key
  //    (see its `DuelKernelProps` docstring).
  const SPORTLESS_ALLOWED: Record<string, number> = {
    [path.join("components", "RelatedFutures.tsx")]: 5,
    [path.join("components", "SeriesProbability.tsx")]: 1,
    [path.join("components", "discover", "kernels", "DuelKernel.tsx")]: 1,
  };

  it("the census found the call sites (not vacuous)", () => {
    expect(callSites().length).toBeGreaterThanOrEqual(20);
  });

  it("the sport-less set is exactly the named one", () => {
    const sportless: Record<string, number> = {};
    for (const { file, args } of callSites()) {
      // The sport is the third argument of both forms.
      if (args < 3) sportless[file] = (sportless[file] ?? 0) + 1;
    }
    expect(sportless).toEqual(SPORTLESS_ALLOWED);
  });

  it.each([
    ["components/TeamGameCards.tsx", 1],
    ["components/EventCard.tsx", 2],
    ["components/FeedCard.tsx", 1],
    ["components/discover/EventCard.tsx", 1],
    ["components/BookmakerTable.tsx", 1],
  ])("%s passes the sport at all %i of its call sites", (file, n) => {
    const sites = callSites().filter((s) => s.file === path.normalize(file));
    expect(sites).toHaveLength(n);
    for (const s of sites) expect(s.args).toBe(3);
  });
});
