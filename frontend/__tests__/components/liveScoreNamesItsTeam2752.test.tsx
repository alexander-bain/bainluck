// THE LIVE SCORE NAMES ITS OWN TEAM — ux/1041, #2752 (p1).
//
// THE DEFECT. `FeedCard` printed the live score as a bare `{home_score} -
// {away_score}` pair in the header slot, on a card that lists the AWAY team
// above the HOME team, stacks its probability chips away-over-home, and labels
// itself "{away} at {home}". So the one element that carried its meaning purely
// in its position carried it the opposite way from everything around it.
//
// Measured on production `6af4de00` (#2752): a card reading "3 - 2" above
// "St. Louis Cardinals 17% / Los Angeles Dodgers 83%" while the DODGERS led 3-2
// — the card showed the side it priced at 17% as the one ahead. That is the
// fixture below, unchanged.
//
// WHY THE ASSERTIONS READ PAIRS AND NOT POSITIONS. The near-miss a reader would
// most likely write is "swap the two operands", which produces the right digits
// and still leaves a bare pair that says nothing about whose they are — and the
// fix a *later* reader might write is a correct label over swapped digits. A
// test that only checks the printed order cannot tell those apart from the ship.
// So every ordering claim here is checked against the accessible sentence, which
// names each team beside its own number, and both are compared to the fixture's
// own values rather than to a literal.
//
// WHY THE SUSPENDED ARM IS IN THIS FILE. #2786 shipped `suspendedSummary(...,
// "home-away")` for this card and justified it as "matching the live branch
// immediately below it". Its rule — the suspended score reads in the card's own
// order — is right; its reference was the broken element, so the inversion
// propagated. Both arms render into ONE slot, so they move together or the
// inherited `suspendedScoreOrderFollowsTheCard2786` guard goes red.
//
// THE SCORES ARE DELIBERATELY DISTINCT (away 2, home 3) AND SO ARE THE
// PROBABILITIES. An equal pair would make every ordering assertion here pass for
// free, which is the trap #2786's own file names.
//
// EVERY EXTRACTOR ASSERTS ITS OWN YIELD before it is compared, so a renamed
// class or a dropped attribute goes red instead of quietly comparing two empty
// lists.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { suspendedSummary } from "@/lib/eventState";
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

// ---------------------------------------------------------------------------
// The production specimen, #2752: event 15300843 on `/sports`, 2026-09-03.
// ---------------------------------------------------------------------------

const AWAY_TEAM = "St. Louis Cardinals";
const HOME_TEAM = "Los Angeles Dodgers";
const AWAY_SCORE = 2;
const HOME_SCORE = 3;
const AWAY_PROB = 0.17;
const HOME_PROB = 0.83;

const COMMENCE_IN_THE_PAST = new Date(Date.now() - 2 * 3600_000).toISOString();

function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15300843,
    external_id: "evt-15300843",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: HOME_TEAM,
    away_team: AWAY_TEAM,
    commence_time: COMMENCE_IN_THE_PAST,
    status: "live",
    away_score: AWAY_SCORE,
    home_score: HOME_SCORE,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: COMMENCE_IN_THE_PAST,
      home_probability: HOME_PROB,
      away_probability: AWAY_PROB,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  } as unknown as FeedEventData;
}

function render(over: Partial<FeedEventData> = {}): string {
  const data = makeData(over);
  return renderToStaticMarkup(
    <FeedCard
      item={
        { type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem
      }
    />,
  );
}

/** Rendered text with tags and SSR comment separators removed. */
function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * The two digits the live score prints, in the order it prints them.
 *
 * Anchored on the `data-testid`, not on a Tailwind class: a restyle must not be
 * able to blind this file, and a stray sibling must not be able to feed it.
 */
function visiblePair(html: string): string[] {
  const cell = html.match(
    /<span[^>]*data-testid="feed-card-live-score"[^>]*>([\s\S]*?)<\/span>/,
  );
  expect(cell).not.toBeNull();
  const digits = text(cell![1]).match(/^(\d+) - (\d+)$/);
  // The cell must be exactly a pair. A partial match would let a third number
  // creep in and still satisfy the ordering claims below.
  expect(digits).not.toBeNull();
  return [digits![1], digits![2]];
}

/**
 * The accessible sentence, as `[team, score]` PAIRS in spoken order.
 *
 * This is the half a position-only extractor cannot see: right digits under the
 * wrong names, and wrong digits under the right names, are different bugs and
 * both are silent to `visiblePair` alone.
 */
function spokenPairs(html: string): Array<[string, string]> {
  const cell = html.match(
    /<span[^>]*data-testid="feed-card-live-score"[^>]*aria-label="([^"]*)"/,
  );
  expect(cell).not.toBeNull();
  const sides = cell![1].split(", ");
  // The extractor reports its own yield. Two sides, always — a join that lost a
  // side would otherwise make the comparisons below vacuously agree.
  expect(sides).toHaveLength(2);
  return sides.map((side) => {
    const m = side.match(/^(.+) (\d+)$/);
    expect(m).not.toBeNull();
    return [m![1], m![2]] as [team: string, score: string];
  });
}

/** The probability chips, in the order the column stacks them. */
function chipOrder(html: string): string[] {
  const found = Array.from(
    html.matchAll(/font-mono text-sm font-bold[^"]*"[^>]*>(\d+)%</g),
  ).map((m) => m[1]);
  expect(found).toHaveLength(2);
  return found;
}

// ---------------------------------------------------------------------------
// The fixture is capable of failing
// ---------------------------------------------------------------------------

describe("the fixture can express the defect", () => {
  it("gives the two sides different scores and different prices", () => {
    // Without this, an inverted card and a correct one render identically and
    // every assertion in this file is green on both arms for free.
    expect(AWAY_SCORE).not.toEqual(HOME_SCORE);
    expect(AWAY_PROB).not.toEqual(HOME_PROB);
    // And the leader is the side with the LOWER price, which is what made the
    // production card contradict itself rather than merely read oddly.
    expect(HOME_SCORE).toBeGreaterThan(AWAY_SCORE);
    expect(HOME_PROB).toBeGreaterThan(AWAY_PROB);
  });
});

// ---------------------------------------------------------------------------
// The ship
// ---------------------------------------------------------------------------

describe("a LIVE card's score reads in the card's own order", () => {
  it("prints the away number first, which is 2 and not 3", () => {
    // The user-visible claim, stated plainly so the failure message names it.
    // The Dodgers (home) had scored 3; the card printed "3 - 2" above a list
    // that starts with the Cardinals.
    expect(visiblePair(render())).toEqual([String(AWAY_SCORE), String(HOME_SCORE)]);
  });

  it("says which team each number belongs to, away first", () => {
    expect(spokenPairs(render())).toEqual([
      [AWAY_TEAM, String(AWAY_SCORE)],
      [HOME_TEAM, String(HOME_SCORE)],
    ]);
  });

  it("prints the same digits it speaks, in the same order", () => {
    // The two are derived from one ordered list in the component, so this is a
    // check on that construction rather than on two independent strings — and it
    // is what catches "right numbers, wrong names" and its mirror.
    const html = render();
    expect(visiblePair(html)).toEqual(spokenPairs(html).map(([, score]) => score));
  });

  it("agrees with the order of the probability chips beside it", () => {
    // The chips were already away-over-home. This is the invariant the bare pair
    // broke, and it is stated as a relation between two rendered things so it
    // survives a change to either.
    const html = render();
    const [firstScore] = visiblePair(html);
    const [firstChip] = chipOrder(html);
    expect(firstScore).toBe(String(AWAY_SCORE));
    expect(firstChip).toBe(String(Math.round(AWAY_PROB * 100)));
  });

  it("agrees with the order the card's own link label declares", () => {
    // `aria-label="{away} at {home}"` is the card's written-down convention and
    // predates this ship; the score now matches it.
    const html = render();
    expect(html).toContain(`aria-label="${AWAY_TEAM} at ${HOME_TEAM} - Live"`);
    expect(spokenPairs(html)[0][0]).toBe(AWAY_TEAM);
  });
});

describe("the SUSPENDED line moves with the live branch, because they share a slot", () => {
  it("prints the away number first too", () => {
    const html = render({ status: "suspended" });
    expect(text(html)).toContain(
      suspendedSummary(AWAY_SCORE, HOME_SCORE, "away-home"),
    );
  });

  it("prints the same two numbers, in the same order, as the live branch", () => {
    // #2786's guarantee, restated from this side: the numbers must not change
    // places the moment play stops. It is what forces both arms to be fixed
    // together — fixing only one of them fails here and in #2786's own file.
    const suspended = text(render({ status: "suspended" })).match(
      /last score (\d+)-(\d+)/,
    );
    expect(suspended).not.toBeNull();
    expect([suspended![1], suspended![2]]).toEqual(visiblePair(render()));
  });
});

// ---------------------------------------------------------------------------
// #2689 — the SAME CARD's opening pair, one line away
//
// Shipped together because the alternative is worse than either bug: fixing the
// score alone leaves one card carrying two bare ordered pairs that count in
// OPPOSITE directions. `Opened {home}/{away}` sat under away-first rows, and
// since `renderedDuelPercents` publishes an exact complement, reading it
// backwards crosses 50% on every match that did not open even — so it inverts
// the favourite by construction and the "10 of 10" in #2689 cannot decay.
// ---------------------------------------------------------------------------

const OPENED_AWAY_PCT = 11;
const OPENED_HOME_PCT = 89;
const OPENING_ODDS = {
  home_probability: OPENED_HOME_PCT / 100,
  away_probability: OPENED_AWAY_PCT / 100,
  favorite: "home",
};

function openedPair(html: string): string[] {
  const cell = html.match(
    /<span[^>]*data-testid="feed-card-opened"[^>]*>([\s\S]*?)<\/span>/,
  );
  expect(cell).not.toBeNull();
  const digits = text(cell![1]).match(/^Opened (\d+)\/(\d+)$/);
  expect(digits).not.toBeNull();
  return [digits![1], digits![2]];
}

function openedSpoken(html: string): Array<[string, string]> {
  const cell = html.match(
    /<span[^>]*data-testid="feed-card-opened"[^>]*aria-label="([^"]*)"/,
  );
  expect(cell).not.toBeNull();
  const sides = Array.from(cell![1].matchAll(/(.+?) opened at (\d+)%/g)).map(
    (m) => [m[1].replace(/^,\s*/, ""), m[2]] as [string, string],
  );
  expect(sides).toHaveLength(2);
  return sides;
}

describe("the opening pair reads in the card's own order too", () => {
  it("prints the away percent first, which is 11 and not 89", () => {
    expect(openedPair(render({ opening_odds: OPENING_ODDS } as Partial<FeedEventData>))).toEqual([
      String(OPENED_AWAY_PCT),
      String(OPENED_HOME_PCT),
    ]);
  });

  it("says which side opened where, away first", () => {
    expect(
      openedSpoken(render({ opening_odds: OPENING_ODDS } as Partial<FeedEventData>)),
    ).toEqual([
      [AWAY_TEAM, String(OPENED_AWAY_PCT)],
      [HOME_TEAM, String(OPENED_HOME_PCT)],
    ]);
  });

  it("does not hand the favourite's number to the underdog", () => {
    // The user-visible harm, stated as the relation rather than as two literals:
    // the bigger opening number must be spoken for the team that actually opened
    // as favourite. Reversed, this card called an 11% underdog an 89% favourite.
    const spoken = openedSpoken(render({ opening_odds: OPENING_ODDS } as Partial<FeedEventData>));
    const favourite = spoken.reduce((a, b) => (Number(a[1]) >= Number(b[1]) ? a : b));
    expect(favourite[0]).toBe(HOME_TEAM);
    expect(favourite[1]).toBe(String(OPENED_HOME_PCT));
  });

  it("prints the same digits it speaks, in the same order", () => {
    const html = render({ opening_odds: OPENING_ODDS } as Partial<FeedEventData>);
    expect(openedPair(html)).toEqual(openedSpoken(html).map(([, pct]) => pct));
  });

  it("CONTROL: the pair is still one rounded complement, summing to 100", () => {
    // UX-P166's rule, which this ship does not touch. Same two integers, same
    // pair — only the order they are printed in moved.
    //
    // ⚠️ READ OFF THE VISIBLE TEXT, NOT OFF `openedPair`. The first version of
    // this used the extractor above, which selects on a `data-testid` THIS DIFF
    // ADDS — so on the parent it selected nothing and the "control" failed for a
    // reason that had nothing to do with the claim. It was arm-dependent while
    // wearing a CONTROL label, and only counting the red arm showed it. Any
    // predicate that picks its population with a marker the parent lacks has the
    // same problem, absence-assertions and presence-assertions alike.
    const digits = text(
      render({ opening_odds: OPENING_ODDS } as Partial<FeedEventData>),
    ).match(/Opened (\d+)\/(\d+)/);
    expect(digits).not.toBeNull();
    expect(Number(digits![1]) + Number(digits![2])).toBe(100);
  });

  it("CONTROL: a FINISHED card still has no opening footer at all", () => {
    // ux/1036 dropped it there in favour of the per-team priors, and that is
    // unchanged. Green on the parent.
    const html = render({
      status: "completed",
      opening_odds: OPENING_ODDS,
    } as Partial<FeedEventData>);
    expect(html).not.toContain('data-testid="feed-card-opened"');
    expect(text(html)).not.toContain("Opened ");
  });
});

// ---------------------------------------------------------------------------
// CONTROLS — green on this branch AND on the parent. Verified by running the
// red arm and counting: these must survive it.
// ---------------------------------------------------------------------------

describe("CONTROL: the rest of the card is untouched", () => {
  it("still lists the away team above the home team", () => {
    // The reference the ship aligns to. If this ever inverts, the fix above is
    // wrong rather than the card, and this file should say so first.
    const rendered = text(render());
    expect(rendered.indexOf(AWAY_TEAM)).toBeGreaterThanOrEqual(0);
    expect(rendered.indexOf(AWAY_TEAM)).toBeLessThan(rendered.indexOf(HOME_TEAM));
  });

  it("still stacks the probability chips away over home", () => {
    expect(chipOrder(render())).toEqual([
      String(Math.round(AWAY_PROB * 100)),
      String(Math.round(HOME_PROB * 100)),
    ]);
  });

  it("still prints a FINISHED card's scores away-first, and not through this cell", () => {
    // The finished branch was already correct and is deliberately NOT changed
    // here — it was the reference #2752 named. Folding the live branch into its
    // per-row treatment is the named follow-up, on top of #2747/PR #2810.
    //
    // ⚠️ WRITTEN TO SURVIVE THAT PR, WHICH IS TOKEN-GRANTED AND UNMERGED. It
    // moves the settled score out of the team rows and into the right-hand
    // column, still stacked away-over-home. So this asserts the ORDER of the two
    // score-treated elements rather than "the number sits next to the name" —
    // the first phrasing was green here and would have gone red the day #2810
    // merged, with no textual conflict to warn anyone. Both markups match the
    // class prefix below; the probability chips do not, because they render a
    // `%` between the digits and the closing tag.
    const html = render({ status: "completed" });
    expect(html).not.toContain('data-testid="feed-card-live-score"');
    const scores = Array.from(
      html.matchAll(/font-mono text-sm[^"]*"[^>]*>(\d+)</g),
    ).map((m) => m[1]);
    expect(scores).toHaveLength(2);
    expect(scores).toEqual([String(AWAY_SCORE), String(HOME_SCORE)]);
  });

  it("still shows a start time, and no score, on a SCHEDULED card", () => {
    const html = render({
      status: "scheduled",
      commence_time: new Date(Date.now() + 3 * 3600_000).toISOString(),
      away_score: null,
      home_score: null,
    } as Partial<FeedEventData>);
    expect(html).not.toContain('data-testid="feed-card-live-score"');
    expect(text(html)).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });

  it("renders no score cell at all when a live card has none", () => {
    // Fail-closed: the ordered list is null when either side is missing, so the
    // slot falls through rather than printing "null - 3".
    const html = render({ away_score: null } as Partial<FeedEventData>);
    expect(html).not.toContain('data-testid="feed-card-live-score"');
    expect(text(html)).not.toContain("null");
  });
});
