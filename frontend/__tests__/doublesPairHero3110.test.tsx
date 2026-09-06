/**
 * #3110 — a doubles hero names BOTH players, or it is not naming the match.
 *
 * THE DEFECT, photographed on production 2026-09-06 at 390px
 * (`/events/15305555`, the US Open women's doubles final):
 *
 *     [S/T]  Townsend        Krawczyk  [H/K]
 *
 * The chips beside the names knew it was a pair. The names did not: the hero
 * ran each side through `teamShortName`, whose last-word rule treats the "/"
 * as an ordinary token and returns the final one, so "Siniakova / Townsend"
 * became "Townsend" and the final read as a singles match between two people
 * who were not playing singles.
 *
 * THE POPULATION, measured before the fix rather than sampled
 * (`fixtures/doublesPairNames3110.json`, admin db-query, production
 * 2026-09-06): 252 distinct pair sides across 30 days of events, and 0 rows in
 * `teams`. 233 of the 252 (92.5%) lose a player under the parent rule. The 19
 * that survive do so BY ACCIDENT — "Arnaldi / Struff J-L" keeps both players
 * because its trailing token reduces to <= 2 characters, not because anything
 * knew it was a pair — which is why the population, not a handful of names, is
 * what this file asserts.
 *
 * WHAT MUST NOT MOVE. The separator that means "and" is a SPACED slash. An
 * unspaced one belongs to one entity's own name, and three real ones are in
 * the data: "Bodo/Glimt" (a club, event 15296763), plus
 * "Scranton/Wilkes-Barre RailRiders" and "W-B/Scranton Penguins" in the
 * UX-1065 corpus. Those still shorten to "RailRiders" and "Penguins", and the
 * corpus arm below proves the fix cannot reach ANY of the 4,701 names UX-1065
 * measured — 0 of them carry a spaced slash.
 *
 * WHY THE ASSERTION IS "BOTH SIDES SURVIVE" AND NOT "EQUALS THE INPUT" IN THE
 * POPULATION ARM: an equality would also be satisfied by a helper that had
 * simply stopped shortening everything. Each name is checked for the presence
 * of each of its own sides, which a last-word rule cannot pass, and the
 * CONTROL arm holds the shortening it must keep doing.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import {
  teamShortName,
  teamShortNames,
  isDoublesPair,
} from "@/lib/teamShortName";
import pairs from "./fixtures/doublesPairNames3110.json";
import corpus from "./fixtures/teamNames.ux1065.json";

const PAIR_NAMES: string[] = (pairs as { names: string[] }).names;
const UX1065_NAMES: string[] = (corpus as { names: string[] }).names;

// ───────────────────────────────────────────────────────────────────────────
// THE SHIP — the hero the reader photographed
// ───────────────────────────────────────────────────────────────────────────

describe("#3110: the doubles hero names both players", () => {
  it("the US Open women's doubles final is not a match between Townsend and Krawczyk", () => {
    const pair = teamShortNames(
      { name: "Siniakova / Townsend" },
      { name: "Hunter / Krawczyk" },
    );
    expect(pair).toEqual({
      home: "Siniakova / Townsend",
      away: "Hunter / Krawczyk",
    });
  });

  it("every pair the issue reported keeps both players", () => {
    // The three events named in #3110, as the backend serves them.
    expect(teamShortName("Krawietz / Puetz")).toBe("Krawietz / Puetz");
    expect(teamShortName("Faria / Walton")).toBe("Faria / Walton");
    expect(teamShortName("Bolelli / Vavassori")).toBe("Bolelli / Vavassori");
    expect(teamShortName("Neel / Olmos")).toBe("Neel / Olmos");
    expect(teamShortName("Shibahara / Tararudee")).toBe("Shibahara / Tararudee");
  });

  it("all 252 measured pair sides keep BOTH of their own players", () => {
    expect(PAIR_NAMES).toHaveLength(252);
    const lost: string[] = [];
    for (const name of PAIR_NAMES) {
      const out = teamShortName(name);
      const sides = name.split(" / ");
      expect(sides.length).toBeGreaterThanOrEqual(2);
      if (!sides.every((side) => out.includes(side))) lost.push(`${name} -> ${out}`);
    }
    expect(lost).toEqual([]);
  });

  it("a name that survived the parent rule BY ACCIDENT now survives on purpose", () => {
    // "J-L" reduces to 2 characters, so `isNonDistinctiveTrailingWord` bailed
    // out and returned the full string. Right answer, wrong reason — and it
    // held only for as long as the second player's last token stayed short.
    expect(teamShortName("Arnaldi / Struff J-L")).toBe("Arnaldi / Struff J-L");
    expect(isDoublesPair("Arnaldi / Struff J-L")).toBe(true);
  });

  it("a pair does not reach the abbreviation rescue and print its chip twice", () => {
    // Unreachable today (0 of the 252 pairs has a `teams` row, so there is no
    // abbreviation to rescue with) and asserted so it stays that way: the hero
    // already draws "S/T" and "H/K" as chips above these names.
    const pair = teamShortNames(
      { name: "Siniakova / Townsend", abbreviation: "S/T" },
      { name: "Hunter / Krawczyk", abbreviation: "H/K" },
    );
    expect(pair).toEqual({
      home: "Siniakova / Townsend",
      away: "Hunter / Krawczyk",
    });
  });
});

// ───────────────────────────────────────────────────────────────────────────
// CONTROLS — green on the parent too. These are what must NOT move.
// ───────────────────────────────────────────────────────────────────────────

describe("#3110 CONTROL: an unspaced slash belongs to one team's own name", () => {
  it("CONTROL the two slashed names in the UX-1065 corpus still shorten", () => {
    expect(UX1065_NAMES).toContain("Scranton/Wilkes-Barre RailRiders");
    expect(UX1065_NAMES).toContain("W-B/Scranton Penguins");
    expect(teamShortName("Scranton/Wilkes-Barre RailRiders")).toBe("RailRiders");
    expect(teamShortName("W-B/Scranton Penguins")).toBe("Penguins");
  });

  it("CONTROL a slashed CLUB name is returned whole and unreformatted", () => {
    // Event 15296763, Bayern Munich v Bodo/Glimt on Sep 10. Byte-for-byte: a
    // rule that split on "/" and rejoined with " / " would rename the club.
    expect(teamShortName("Bodo/Glimt")).toBe("Bodo/Glimt");
    expect(isDoublesPair("Bodo/Glimt")).toBe(false);
  });

  it("CONTROL the fix cannot reach a single name UX-1065 measured", () => {
    const reachable = UX1065_NAMES.filter((n) => isDoublesPair(n));
    expect(reachable).toEqual([]);
    expect(UX1065_NAMES).toHaveLength(4701);
  });

  it("CONTROL the American convention still shortens", () => {
    expect(teamShortName("Los Angeles Lakers")).toBe("Lakers");
    expect(teamShortName("Tampa Bay Buccaneers")).toBe("Buccaneers");
    expect(teamShortName("Ipswich Town")).toBe("Ipswich Town");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// RENDERED MARKUP — the claim is about a card, not about a helper
// ───────────────────────────────────────────────────────────────────────────

/**
 * The winner label is the content of the one span that ends in " won" — the
 * positive extraction UX-1065's own file uses, for the same reason: a
 * substring search over this card is UNSATISFIABLE, because its title line
 * prints both FULL names ("Hunter / Krawczyk @ Siniakova / Townsend") whatever
 * the short-name helper does. A test that only looked for "Siniakova" anywhere
 * in the markup passes on the parent and proves nothing; this one is red there.
 */
function winnerLabelOf(markup: string): string {
  const hits = [...markup.matchAll(/>([^<>]*?)\s+won<\/span>/g)].map((m) => m[1].trim());
  if (hits.length !== 1) {
    throw new Error(`expected exactly 1 winner label, found ${hits.length}: ${JSON.stringify(hits)}`);
  }
  return hits[0];
}

describe("#3110: the rendered duel card", () => {
  function settledDoublesCard() {
    const { DuelKernel } = require("@/components/discover/kernels/DuelKernel");
    return renderToStaticMarkup(
      React.createElement(DuelKernel, {
        state: "settled",
        homeTeam: "Siniakova / Townsend",
        awayTeam: "Hunter / Krawczyk",
        homeScore: 2,
        awayScore: 0,
        categorySlug: "tennis",
        categoryLabel: "Tennis",
        categoryEmoji: "*",
      }),
    );
  }

  it("a settled doubles card says the PAIR won, not one of its players", () => {
    expect(winnerLabelOf(settledDoublesCard())).toBe("Siniakova / Townsend");
  });

  it("the crest fallback still paints three letters of a player", () => {
    // It painted "TOW" before and paints "SIN" now: three characters of the
    // first surname instead of the second. Pinned because it moved.
    const markup = settledDoublesCard();
    expect(markup).toContain(">SIN<");
    expect(markup).toContain(">HUN<");
  });
});

// ───────────────────────────────────────────────────────────────────────────
// THE HERO IS ON THIS PATH — the photographed surface cannot be rendered here
// ───────────────────────────────────────────────────────────────────────────

describe("#3110: the event hero reaches the helper this file fixes", () => {
  it("the event page shortens its hero names through teamShortNames", () => {
    const code = readFileSync(
      join(process.cwd(), "app/events/[id]/page.tsx"),
      "utf8",
    );
    expect(code).toContain('from "@/lib/teamShortName"');
    // The hero passes the SERVED names through, which is what makes the
    // population arm above a statement about `/events/15305555`.
    expect(code).toMatch(
      /teamShortNames\(\s*\{\s*name:\s*event\.home_team,[\s\S]{0,200}?name:\s*event\.away_team,/,
    );
  });
});
