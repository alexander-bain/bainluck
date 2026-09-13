// #5749 — A CARD'S REASON BADGE MUST BE ABOUT THE GAME, NOT ABOUT WHAT THE TEAM IS CALLED.
//
// Found by discover/049 mystery-shopping production `/sports` at 390px on 2026-09-12. A live
// NCAAF card carried:
//
//     ⚡ Kentucky Wildcats leading after starting at 24%
//
// The ⚡ bolt and the yellow "something wild is happening" pill are not about the game. They
// fired because the team is called the Wildcats: `reasonStyle` classified the RENDERED sentence
// by bare substring, and every reason is a template with a team or market name interpolated
// into it, so the classifier was reading the name too.
//
//     "kentucky wildcats leading after starting at 24%".includes("wild")  →  true
//
// Measured reach on production `teams` (read-only SELECT, 2026-09-12): "wild" appears in 16
// distinct team names and "even" in 11 — 27 of 5,592 (0.48%) could style their own cards.
// `close`, `tight`, `odds` and `upset` measured 0. The worst is the Minnesota Wild, an NHL team
// whose every card in every state claimed a lead change, and Benevento, an Italian club that
// was always "virtually even" no matter what its card said.
//
// ## What this file asserts, and why it is a property and not a list of 27 strings
//
// The law is NAME-INVARIANCE: swapping the team out of a reason template must not change the
// badge. A list of the 27 names would go stale the first time a club is promoted, and would
// pass just as happily against a classifier that special-cased "Wildcats". Arm 2 renders the
// same templates with a neutral team and with each hijacker and asserts the badges are equal,
// which is the sentence the fix actually has to be true of.
//
// Word boundaries are NOT this fix and arm 3 is what says so: `\bwild\b` still matches
// "Minnesota Wild". The keyword has to be pinned to the words the template puts around it
// ("wild GAME"), because that is the part a name cannot forge.
//
// Both directions per gotcha #43: the hijack stops AND the families are proved still reachable
// (arm 4), including the case that separates "name suppressed" from "family suppressed" — a
// Minnesota Wild card whose reason really IS a movement reason still gets its ↕ badge.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));

function makeData(): FeedEventData {
  return {
    id: 15310999,
    external_id: "evt-15310999",
    sport: "americanfootball_ncaaf",
    sport_name: "NCAAF",
    home_team: "Kentucky Wildcats",
    away_team: "Alabama Crimson Tide",
    commence_time: "2026-09-12T19:30:00.000Z",
    status: "live",
    home_score: 14,
    away_score: 10,
    opening_odds: { away_probability: 0.76, home_probability: 0.24 },
  } as unknown as FeedEventData;
}

function render(reason: string): string {
  const item = {
    type: "event",
    score: 50,
    reason,
    headline: "",
    data: makeData(),
  } as unknown as FeedItem;
  return renderToStaticMarkup(<FeedCard item={item} />);
}

/**
 * The badge family a reason renders as, read off the pill's own colour token.
 *
 * Deliberately NOT the icon glyph: two families could share a glyph, and the colour is what a
 * reader actually perceives as "this card is flagged". `"plain"` is the unstyled `<p>` branch.
 */
function badgeFamily(reason: string): string {
  const html = render(reason);
  const m = /<span class="inline-flex[^"]*\b(?:text-(\w+)-500)\b[^"]*"/.exec(html);
  if (m) return m[1];
  // Prove it really took the plain branch rather than failing to render at all.
  expect(html).toContain("text-xs text-text-secondary");
  return "plain";
}

/** Team names measured on production that contain a classifier keyword. */
const HIJACKERS = [
  "Kentucky Wildcats", // "wild" — 16 names
  "Arizona Wildcats",
  "Abilene Christian Wildcats",
  "Minnesota Wild", // the one word boundaries do not save
  "Benevento", // "even" — 11 names
];

const NEUTRAL = "Atlanta Braves";

/** Real `feed_reasons.py` templates, as a function of the name interpolated into them. */
const TEMPLATES: Array<(name: string) => string> = [
  (n) => `${n} leading after starting at 24%`,
  (n) => `${n} odds shifted 12% since open`,
  (n) => `${n} odds shifted up 5 points today in moneyline`,
  (n) => `Big odds movement in ${n} moneyline`,
  (n) => `Odds shifting in ${n} total points`,
  (n) => `${n} moneyline has shifted since Tuesday`,
  (n) => `New favorite: ${n} (54%)`,
  (n) => `Multiple ranking changes in Will ${n} win the title?`,
];

describe("#5749 — a reason badge is classified by the template, not by the team's name", () => {
  // ARM 1 FIRST, the reader-visible specimen, verbatim from the production card.
  it("arm 1: the Wildcats card no longer claims something wild is happening", () => {
    expect(badgeFamily("Kentucky Wildcats leading after starting at 24%")).toBe("plain");
    // The same sentence about a team with an innocent name always took the plain branch. The
    // two agreeing is the whole point: the card is styled by what it says, not who is in it.
    expect(badgeFamily("Oklahoma State Cowboys leading after starting at 8%")).toBe("plain");
  });

  it("arm 2: name-invariance — swapping the team cannot change the badge", () => {
    for (const template of TEMPLATES) {
      const expected = badgeFamily(template(NEUTRAL));
      for (const hijacker of HIJACKERS) {
        expect({ template: template(hijacker), family: badgeFamily(template(hijacker)) }).toEqual({
          template: template(hijacker),
          family: expected,
        });
      }
    }
  });

  it("arm 3: word boundaries alone would not have been enough — Minnesota Wild", () => {
    // `\bwild\b` matches "Minnesota Wild", so a boundary-only fix leaves the NHL team claiming a
    // lead change on every card. This arm fails against that weaker fix and is the reason the
    // patterns are phrases.
    expect(badgeFamily("Minnesota Wild leading after starting at 44%")).toBe("plain");
    expect(badgeFamily("Minnesota Wild (54%) leads Dallas Stars")).toBe("plain");
  });

  it("arm 4: the families are all still reachable — the names were suppressed, not the feature", () => {
    // Vacuity control. Without this, every arm above would pass against a `reasonStyle` that
    // returned `plain` for everything, which is not a fix, it is a deletion.
    expect(badgeFamily("Wild game")).toBe("yellow"); // ⚡ the only served reason in that family
    expect(badgeFamily("Virtually even")).toBe("blue"); // ⚖
    expect(badgeFamily("Tight game")).toBe("blue");
    expect(badgeFamily("Starting soon — close matchup")).toBe("blue");
    expect(badgeFamily("Upset result")).toBe("orange"); // ⚠
    expect(badgeFamily("Won as 24% underdog")).toBe("orange");
    expect(badgeFamily("Big odds movement in Braves moneyline")).toBe("purple"); // ↕
    expect(badgeFamily("Shifted since Tuesday")).toBe("purple");
    expect(badgeFamily("Starting soon")).toBe("green"); // 🕐

    // The control that separates "the name stopped mattering" from "the Wild stopped being
    // styled": a Minnesota Wild card whose reason genuinely IS a movement reason keeps its ↕.
    expect(badgeFamily("Minnesota Wild odds shifted 8% since open")).toBe("purple");
    expect(badgeFamily("Big odds movement in Minnesota Wild vs Dallas Stars moneyline")).toBe("purple");
  });
});
