// #7270 — THE EVENT HERO PAINTED `ASS` ON A LIVE BIG 12 GAME.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// Production, 390px, in play: `/events/15311215`, Arizona State v Kansas. The
// home crest tile read `ASS`, the away tile `KJ`. Neither team has a logo of
// either kind, so the lettered fallback is what the page draws.
//
// `app/events/[id]/page.tsx` carried its own INLINE copy of the initials rule
// at both tiles and never called `lib/teamShortName.ts`, so `UNSHIPPABLE_BADGES`
// — a list that names "ASS" as its reason to exist — was never consulted.
// "Arizona State Sun Devils" is A·S·S·D cut to three.
//
// ── WHY THIS GUARD RENDERS THE PAGE ──────────────────────────────────────────
//
// The defect was never in a helper. Both helpers were correct and one of them
// already refused this exact badge; the page simply did not ask. A unit test on
// `shippableCrestBadge` would have passed on every day this bug was live, and
// would pass again the moment someone re-inlines the expression. So the
// assertion is on the page's own markup, with the specimen's real names.
//
// ── THE OTHER HALF, WHICH IS WHY THE OBVIOUS FIX WAS NOT TAKEN ───────────────
//
// The reported repair was to swap the inline copy for `teamCrestBadge`. Over
// all 30,340 distinct `events` team names that swap fixes 29 unshippable badges
// and introduces 73 reader-visible new ones, because `teamCrestBadge` badges a
// short name by its last word: "Nigeria" -> `NIG`, "Detroit Pistons" -> `PIS`,
// "Fuchs" -> `FUC`, "Titans" -> `TIT`. The second describe block is the part of
// this guard that fails if someone later "simplifies" the helper into that
// swap, which is the likeliest way this page regresses.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { shippableCrestBadge, teamCrestBadge } from "@/lib/teamShortName";

const EVENT = {
  id: 15311215,
  sport: "americanfootball_ncaaf",
  sport_title: "NCAAF",
  sport_name: "NCAAF",
  home_team: "Arizona State Sun Devils",
  away_team: "Kansas Jayhawks",
  home_score: 10,
  away_score: 7,
  status: "live",
  commence_time: "2026-09-19T17:00:00+00:00",
  win_probability_sources: {},
};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    const isEvent = Array.isArray(key) && key[0] === "event";
    return {
      data: isEvent ? EVENT_HOLDER.value : undefined,
      error: undefined,
      isLoading: false,
      mutate: () => undefined,
    };
  },
}));

jest.mock("@/hooks", () => ({
  ...jest.requireActual("@/hooks"),
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
  usePinnedEvents: () => ({
    isPinned: () => false,
    togglePin: () => undefined,
    isMaxReached: false,
  }),
}));

jest.mock("@/hooks/useLiveEventStream", () => ({
  __esModule: true,
  useLiveEventStream: () => ({ frame: null, connected: false }),
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/events/15311215",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "15311215" }),
}));

const EVENT_HOLDER: { value: unknown } = { value: EVENT };

// eslint-disable-next-line @typescript-eslint/no-var-requires
const EventDetailPage = require("@/app/events/[id]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

function draw(): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(EventDetailPage, { params: { id: "15311215" } }),
    ),
  );
}

/**
 * The crest tiles' letters, read off the page rather than recomputed.
 *
 * The lettered fallback is the only `font-extrabold` span in the hero, and it
 * is the element the inline expression used to fill. Reading the markup is what
 * makes this a guard about the PAGE: recomputing the badge here would assert
 * that the helper agrees with itself.
 */
function crestLetters(html: string): string[] {
  return Array.from(html.matchAll(/<span[^>]*font-extrabold[^>]*>([^<]*)<\/span>/g))
    .map(m => m[1].trim())
    .filter(Boolean);
}

describe("#7270 the event hero cannot paint an unshippable crest badge", () => {
  it("draws ASD and JAY for the filed specimen, and nowhere paints ASS or KJ", () => {
    EVENT_HOLDER.value = EVENT;
    const letters = crestLetters(draw());

    // Positive first, so the test cannot pass by rendering nothing at all —
    // an empty hero would satisfy every "does not contain" assertion below.
    expect(letters.length).toBeGreaterThanOrEqual(2);
    // `ASD`, not `DEV`: "State" is a non-distinctive token, so the distinctive
    // set is Arizona/Sun/Devils. This is also what Discover already draws for
    // this team, which is the point of routing the hero through the helper.
    expect(letters).toContain("ASD");
    expect(letters).toContain("JAY");

    expect(letters).not.toContain("ASS");
    // `KJ` was not a slur, it was the same rule failing quietly: two initials
    // where the other surfaces all draw `JAY`.
    expect(letters).not.toContain("KJ");
  });

  it("keeps the page's badge equal to the helper's answer for both sides", () => {
    EVENT_HOLDER.value = EVENT;
    const letters = crestLetters(draw());
    expect(letters).toContain(shippableCrestBadge(EVENT.home_team, EVENT.sport));
    expect(letters).toContain(shippableCrestBadge(EVENT.away_team, EVENT.sport));
  });

  it("does not let the reported one-line swap back in, on either tile", () => {
    // The filed specimen cannot see this: `teamCrestBadge` and the safe badge
    // agree on "Arizona State Sun Devils" (both `ASD`), so a page rewritten to
    // call the bare helper passes every assertion above. A mutant proved that.
    // These two names are where the two rules DISAGREE, and both are real
    // production team names with no logo of either kind, so the lettered tile
    // is what a reader gets.
    EVENT_HOLDER.value = {
      ...EVENT,
      home_team: "Nigeria",
      away_team: "Gujarat Titans",
      sport: "soccer_africa_cup_of_nations",
    };
    const letters = crestLetters(draw());
    expect(letters.length).toBeGreaterThanOrEqual(2);
    expect(letters).toContain("N");
    expect(letters).toContain("GT");
    expect(letters).not.toContain("NIG");
    expect(letters).not.toContain("TIT");
  });

  it("paints no slur for a name whose initials spell one, on either tile", () => {
    // Al Sadd SC sat in the same measured set of 29 and is an away-tile case,
    // so the two call sites are both exercised by a real production name.
    EVENT_HOLDER.value = {
      ...EVENT,
      home_team: "Ana Sofia Sanchez",
      away_team: "Al Sadd SC",
      sport: "tennis_atp",
    };
    const letters = crestLetters(draw());
    expect(letters.length).toBeGreaterThanOrEqual(2);
    for (const badge of letters) {
      expect(badge).not.toBe("ASS");
    }
  });
});

describe("#7270 the repair is monotone — it may not introduce what it prevents", () => {
  // Every name here is a real production team name that `teamCrestBadge` alone
  // would badge with a slur. They are the reason the reported one-line swap was
  // refused; if a later change takes that swap, these fail.
  const SPOILED_BY_THE_HELPER: Array<[string, string]> = [
    ["Nigeria", "NIG"],
    ["Detroit Pistons", "PIS"],
    ["Gujarat Titans", "TIT"],
    ["Fuchs", "FUC"],
    ["Cocciaretto", "COC"],
    ["Avispa Fukuoka", "FUK"],
    ["Hoek", "HOE"],
  ];

  it.each(SPOILED_BY_THE_HELPER)(
    "%s is not badged %s",
    (name, slur) => {
      // The premise: this IS what the bare helper answers. Asserted rather than
      // described, so the table cannot quietly stop being about anything.
      expect(teamCrestBadge(name, null)).toBe(slur);
      expect(shippableCrestBadge(name, null)).not.toBe(slur);
    },
  );

  it("falls back to the value production already shows, never to a third invention", () => {
    // Monotone: measured over all 30,340 names, every badge returned is either
    // `teamCrestBadge`'s or the hero's shipped initials. These pin the shape.
    expect(shippableCrestBadge("Nigeria", null)).toBe("N");
    expect(shippableCrestBadge("Detroit Pistons", null)).toBe("DP");
    expect(shippableCrestBadge("Arizona State Sun Devils", null)).toBe("ASD");
    expect(shippableCrestBadge("Kansas Jayhawks", null)).toBe("JAY");
  });

  it("paints no space for a pair whose first surname is under three letters", () => {
    // `teamCrestBadge` once sliced the raw pair and yielded "DE " — #4466's
    // fragment class — and this surface's whitespace test was what kept it off
    // the hero. Since #4535 it counts letters across the space, so the hero
    // takes the preferred badge directly.
    expect(teamCrestBadge("de Minaur / Peers", "tennis_atp")).toBe("DEM");
    expect(shippableCrestBadge("de Minaur / Peers", "tennis_atp")).toBe("DEM");
  });

  it("returns nothing rather than a censored invention when no candidate is clean", () => {
    // SYNTHETIC name, and said so: this arm is unreachable on today's
    // population (0 of 30,340 names reach it), so there is no specimen to cite
    // and manufacturing one is the only way to hold the arm down. It is kept
    // because it is the only thing between a future name and this whole issue.
    // Both candidates must be unshippable at once, which needs the initials AND
    // the last word to spell the same kind of word.
    expect(teamCrestBadge("Titan Italia Titans", null)).toBe("TIT");
    expect(shippableCrestBadge("Titan Italia Titans", null)).toBe("");

    expect(shippableCrestBadge("", null)).toBe("");
    expect(shippableCrestBadge(null, null)).toBe("");
    expect(shippableCrestBadge(undefined, null)).toBe("");
  });
});
