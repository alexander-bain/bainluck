/**
 * #6238 — THE CARD FAMILY STOPS PRINTING THE DRAW AS AN AWAY-TEAM WIN.
 *
 * ## What was wrong
 *
 * Every probability this site draws for a match comes from one pair, and the
 * pair is `home` and `1 − home`. On a two-outcome sport that is exactly right.
 * In soccer `1 − P(home)` is "the home team does not win" — away win **or**
 * draw — so the figure printed under the away crest silently absorbs the entire
 * draw probability.
 *
 * `lib/drawPricedWinner.ts` shipped the rule (ux/1266, ux/1292) and TWO files
 * called it: the event hero and the chart. Measured 2026-09-16, every CARD
 * surface still derived the complement unguarded. On `/sports` at 390px, six
 * live soccer cards all summed to exactly 100 — including Sevilla v Deportivo
 * printed **74% / 26% at half-time in a 0–0**, a scoreline with no room at all
 * for the outcome the match was actually in.
 *
 * ## What this file pins
 *
 * All six surfaces named in the issue, each in BOTH arms:
 *
 *   * a draw-priced sport → the away figure is gone and the HOME figure stays;
 *   * a two-way sport → byte-for-byte the old behaviour, both sides printed.
 *
 * The control arm is not decoration. Withholding is a rule that REMOVES, and an
 * empty surface passes every refusal assertion ever written — so each surface
 * is also asserted to still BE a surface on the sport the ship is not about.
 *
 * ## 🔴 THE REGRESSION THIS SHIP COULD EASILY HAVE SHIPPED, PINNED
 *
 * `FeedCard`'s chips, its bar and its `Opened X/Y` footer were each gated on
 * BOTH sides being non-null. Passing the away value through `printableAway` —
 * the one-line change the helper invites — renders NOTHING on a soccer card,
 * deleting the home number, which is correct and is the one thing the card
 * exists to say. Three assertions below fail on that version and pass on this
 * one. Same shape was checked on the other five.
 *
 * ## What it does NOT claim
 *
 * The home number this keeps is the blend. #1011 (released 2026-09-16) repaired
 * it at the source; before that it was itself draw-dropped. This is the RENDER
 * half only — a client inventing an away price out of a complement — and no
 * assertion here should be read as proving the retained figure is well-sourced.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import fs from "fs";
import path from "path";
import type { FeedItem, FeedEventData, Event, EventConceptChild } from "@/lib/types";

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
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import FeedCard from "@/components/FeedCard";
import EventCard from "@/components/EventCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { DuelKernel } from "@/components/discover/kernels/DuelKernel";
import MatchupDuel from "@/components/event/MatchupDuel";
import { awayIsTheComplement, sportPricesADraw } from "@/lib/drawPricedWinner";

/**
 * A draw-priced league and a two-way one.
 *
 * `soccer_spain_la_liga` is the Sevilla specimen's own key and
 * `americanfootball_nfl` is the control. Both are asserted against
 * `sportPricesADraw` first, so if the vocab declaration ever moves, this file
 * fails at its premise rather than silently testing two identical arms — the
 * way a withholding suite goes vacuous.
 */
const DRAW_SPORT = "soccer_spain_la_liga";
const TWO_WAY_SPORT = "americanfootball_nfl";

/**
 * VISIBLE TEXT ONLY.
 *
 * 🔴 The first cut of this file asserted `expect(html).not.toContain("26%")` on
 * raw markup and failed on a component that was behaving correctly: the
 * withheld bar renders its unattributed remainder as `style="width:26%"`, and a
 * bare percent substring cannot tell a printed figure from a CSS width. It
 * would also have passed for the wrong reason in the other direction — a
 * surface that stopped printing the number but kept a 26%-wide away-coloured
 * segment is still making the claim.
 *
 * Tags (and therefore every style and data attribute) are stripped, so these
 * assertions read what a person reads. Geometry is asserted separately, on raw
 * markup, where a width IS the thing under test.
 */
function text(html: string): string {
  return html.replace(/<[^>]*>/g, " ");
}

/** Deliberately not 50/50 and not each other: `74` must never appear as `26`. */
const HOME_PROB = 0.74;
const AWAY_PROB = 0.26;
const HOME_TEXT = "74%";
const AWAY_TEXT = "26%";

/**
 * 🔴 THE CLOCK IS PINNED, AND THIS FILE IS WHY (gotcha #44).
 *
 * Nothing in #6238 is about time — these cards are specimens of a RENDER rule,
 * and `commence_time` is here only because a card needs one. It was written as
 * the literal `2026-09-20T18:40:00Z`, which was comfortably in the future on
 * 2026-09-16 when the ship landed and became the past at 18:40Z on 2026-09-20.
 * `EventCard` then stopped drawing chips for a pre-game match and rendered
 * "No result reported · Sep 20" instead, so three assertions that had never
 * been touched went red — on every branch at once, because the bomb is in the
 * fixture rather than in anyone's diff.
 *
 * The anchor is therefore fixed and `now` is pinned an hour BEFORE it: the
 * suite's subject is a card awaiting kick-off, and that is the only property of
 * the instant any assertion here depends on. Offset first, no clock branch —
 * an anchor containing an `if` is not fixed.
 *
 * The three describes below that still passed at 18:40Z were not safe either,
 * merely later: the card surfaces suppress on their own `commence_time`-relative
 * windows, so they would have fired on their own schedule. One pin covers all
 * four fixtures.
 */
const KICKOFF = "2026-09-20T18:40:00Z";
const BEFORE_KICKOFF = Date.parse(KICKOFF) - 60 * 60 * 1000;

beforeEach(() => {
  jest.useFakeTimers().setSystemTime(BEFORE_KICKOFF);
});

afterEach(() => {
  jest.useRealTimers();
});

describe("#6238 the two arms are genuinely different", () => {
  it("the draw-priced key is declared and the control key is not", () => {
    expect(sportPricesADraw(DRAW_SPORT)).toBe(true);
    expect(sportPricesADraw(TWO_WAY_SPORT)).toBe(false);
  });
});

/**
 * ═══ THE SECOND HALF OF THE RULE, AND IT CAME FROM LOOKING AT THE PAGE ═══
 *
 * The first cut of this ship withheld the away figure on every draw-priced
 * sport, full stop. A BEFORE screenshot of `/sports` showed the cost: the Lyon
 * v Anderlecht card's footer read `Opened 40/32`, which sums to 72 — that pair
 * is NOT a complement, it is de-vigged across the whole quoted board (#1011),
 * and the missing ~28 points ARE the draw. A blanket withhold deleted a real,
 * sourced away price.
 *
 * Measured the same minute over all 13 live soccer cards:
 *
 *   `current_odds`  — 13/13 sum to exactly 1.0000  → derived, withhold
 *   `opening_odds`  — 11/13 sum to 0.68–0.94       → sourced, KEEP
 *
 * So the question is per PAIR, not per sport, and the two pairs on one card
 * legitimately answer differently. `awayIsTheComplement` is the predicate; these
 * are the assertions that stop the blanket version coming back.
 */
describe("#6238 a genuinely priced away leg is KEPT — withholding is for the complement", () => {
  it("the predicate separates the two pairs the same card carries", () => {
    // Lyon @ Anderlecht as production served it, both pairs.
    expect(awayIsTheComplement(0.041, 0.959, DRAW_SPORT)).toBe(true); // current
    expect(awayIsTheComplement(0.4, 0.329, DRAW_SPORT)).toBe(false); // opening
  });

  it("an absent away IS withheld, so the surface keeps its shape", () => {
    expect(awayIsTheComplement(null, 0.74, DRAW_SPORT)).toBe(true);
  });

  it("but an absent away on a TWO-WAY sport is not — that render is untouched", () => {
    expect(awayIsTheComplement(null, 0.74, TWO_WAY_SPORT)).toBe(false);
  });

  it("FeedCard prints the whole opening pair when it is not a complement", () => {
    // The Lyon card. `Opened 40/32` is an honest line and must survive — this
    // repo already keeps a pair summing to 97 on purpose (openedPairCapture's
    // THIN specimen), for exactly this reason.
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(DRAW_SPORT, {
          status: "live",
          opening_odds: { home_probability: 0.329, away_probability: 0.4 },
        } as unknown as Partial<FeedEventData>)}
      />,
    );
    expect(text(html)).toContain("40/33");
    expect(text(html)).not.toMatch(/Opened \D+ \d+%$/);
  });

  it("and still withholds it when the opening pair IS a complement", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(DRAW_SPORT, {
          status: "live",
          opening_odds: { home_probability: 0.71, away_probability: 0.29 },
        } as unknown as Partial<FeedEventData>)}
      />,
    );
    expect(text(html)).not.toContain("71/29");
    expect(text(html)).toContain("71%");
  });

  it("the chips still withhold on the same card, because THAT pair is derived", () => {
    // The two loci on one card, answering differently and both correctly. This
    // is the assertion that would fail if anyone re-simplified the rule back to
    // one per-card question.
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(DRAW_SPORT, {
          status: "live",
          opening_odds: { home_probability: 0.329, away_probability: 0.4 },
        } as unknown as Partial<FeedEventData>)}
      />,
    );
    expect(html).toContain('data-testid="feed-card-away-withheld"');
    expect(text(html)).not.toContain(AWAY_TEXT);
  });
});

// ── FeedCard: three representations on one card ──────────────────────────────

function feedCard(sport: string, over: Partial<FeedEventData> = {}): FeedItem {
  const data: Record<string, unknown> = {
    id: 15313639,
    external_id: "feed-6238",
    sport,
    sport_name: "League",
    home_team: "Sevilla FC",
    away_team: "Deportivo Alaves",
    commence_time: KICKOFF,
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: { home_probability: HOME_PROB, away_probability: AWAY_PROB },
    ...over,
  };
  return { type: "event", data: data as unknown as FeedEventData } as FeedItem;
}

describe("#6238 FeedCard — the surface six live specimens were photographed on", () => {
  it("withholds the away chip and KEEPS the home chip on a draw-priced sport", () => {
    const html = renderToStaticMarkup(<FeedCard item={feedCard(DRAW_SPORT)} />);
    // 🔴 The trap: the obvious one-line fix renders neither of these.
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).not.toContain(AWAY_TEXT);
  });

  it("holds the away SLOT open so the surviving number keeps its row", () => {
    // This column is two stacked slots and their ORDER is the only thing naming
    // them. Dropping the top one moves the home number off the home row, which
    // is a misattribution rather than a cosmetic loss — so the slot stays and
    // takes the em-dash the site already uses for "no reading here".
    const html = renderToStaticMarkup(<FeedCard item={feedCard(DRAW_SPORT)} />);
    expect(html).toContain('data-testid="feed-card-away-withheld"');
  });

  it("keeps the home chip when the away value is ABSENT, not just withheld", () => {
    // 🔴 THIS IS THE ASSERTION THAT MAKES THE GATE LOAD-BEARING, and it took a
    // mutation run to find. The gate was widened from "both sides non-null" to
    // "home non-null, away satisfied by a value OR by the withholding" — but
    // reverting that widening did NOT fail any other test in this file, because
    // every other fixture carries a real away float and the gate passes on it.
    //
    // The case the widening actually buys is this one: a draw-priced card whose
    // payload has no away figure at all. On the old gate the whole chip block
    // disappeared and the reader lost the HOME number too — the exact deletion
    // this ship exists not to cause, arriving through the payload instead of
    // through the rule.
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(DRAW_SPORT, {
          current_odds: { home_probability: HOME_PROB, away_probability: null },
        } as unknown as Partial<FeedEventData>)}
      />,
    );
    expect(text(html)).toContain(HOME_TEXT);
    expect(html).toContain('data-testid="feed-card-away-withheld"');
  });

  it("CONTROL: a two-way sport prints both chips, unchanged", () => {
    const html = renderToStaticMarkup(<FeedCard item={feedCard(TWO_WAY_SPORT)} />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).toContain(AWAY_TEXT);
    expect(html).not.toContain('data-testid="feed-card-away-withheld"');
  });

  it("draws the bar with NO away segment, and still draws a bar", () => {
    // A bar split 74/26 is the same claim in pixels, and it is the element a
    // reader parses without reading. Asserting only "no away segment" would
    // pass on a card that draws no bar at all, so both halves are read.
    const html = renderToStaticMarkup(<FeedCard item={feedCard(DRAW_SPORT)} />);
    expect(html).toContain('data-testid="feed-card-prob-bar"');
    expect(html).toContain('data-bar-segment="home"');
    expect(html).not.toContain('data-bar-segment="away"');
  });

  it("CONTROL: a two-way sport keeps both bar segments", () => {
    const html = renderToStaticMarkup(<FeedCard item={feedCard(TWO_WAY_SPORT)} />);
    expect(html).toContain('data-bar-segment="home"');
    expect(html).toContain('data-bar-segment="away"');
  });

  it("names its survivor in the `Opened` footer rather than printing a bare number", () => {
    // Losing the pair loses the positional attribution that let both numbers go
    // unnamed. `Opened 71` would inherit the away position and read as the away
    // team's, so the footer names the side — native's wording.
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(DRAW_SPORT, {
          status: "live",
          opening_odds: { home_probability: 0.71, away_probability: 0.29 },
        } as Partial<FeedEventData>)}
      />,
    );
    expect(text(html)).toContain("Opened");
    expect(text(html)).toContain("71%");
    expect(text(html)).not.toContain("71/29");
    expect(text(html)).not.toContain("29%");
  });

  it("CONTROL: a two-way sport keeps the unnamed `Opened X/Y` pair", () => {
    const html = renderToStaticMarkup(
      <FeedCard
        item={feedCard(TWO_WAY_SPORT, {
          status: "live",
          opening_odds: { home_probability: 0.71, away_probability: 0.29 },
        } as Partial<FeedEventData>)}
      />,
    );
    expect(text(html)).toContain("29/71");
  });
});

// ── EventCard: /sport/[sport]/[league], team pages, search ───────────────────

function sharedEvent(sport: string, over: Partial<Event> = {}): Event {
  return {
    id: 15305837,
    sport,
    sport_name: "League",
    home_team: "Sevilla FC",
    away_team: "Deportivo Alaves",
    commence_time: KICKOFF,
    status: "scheduled",
    home_score: null,
    away_score: null,
    current_odds: {
      home_probability: HOME_PROB,
      away_probability: AWAY_PROB,
    },
    ...over,
  } as unknown as Event;
}

describe("#6238 EventCard — the shared league/team/search card", () => {
  it("withholds the away chip and keeps the home chip", () => {
    const html = renderToStaticMarkup(<EventCard event={sharedEvent(DRAW_SPORT)} />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).not.toContain(AWAY_TEXT);
  });

  it("CONTROL: a two-way sport prints both", () => {
    const html = renderToStaticMarkup(<EventCard event={sharedEvent(TWO_WAY_SPORT)} />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).toContain(AWAY_TEXT);
  });

  it("leaves the bar's remainder unattributed instead of painting it away-coloured", () => {
    const html = renderToStaticMarkup(<EventCard event={sharedEvent(DRAW_SPORT)} />);
    const remainder = html.match(/<div([^>]*data-bar-remainder="unattributed"[^>]*)>/);
    expect(remainder).not.toBeNull();
    // 🔴 The attribute alone proved nothing: a mutation that dropped the neutral
    // track class left the attribute in place and this test stayed green on a
    // segment painted with no background at all. What matters is the PAINT —
    // the neutral track, and no inline colour of its own.
    expect(remainder![1]).toContain("bg-surface-border/30");
    expect(remainder![1]).not.toContain("background-color");
  });

  it("CONTROL: a two-way sport paints a real away segment", () => {
    // 🔴 #7602 — THIS CONTROL WAS VACUOUS, AND THE OUTAGE PROVED IT.
    //
    // It used to be one negative assertion:
    //
    //     expect(html).not.toContain('data-bar-remainder="unattributed"');
    //
    // A card that renders NOTHING satisfies that, and so does a card rendering
    // the wrong thing entirely. On 2026-09-20 the clock crossed this file's
    // fixture kickoff, `EventCard` swapped the whole bar for "No result
    // reported · Sep 20", and its three siblings in this block went red — while
    // THIS test, the one whose job is to prove the rule does not over-reach,
    // stayed green through the entire outage. A control that passes in exactly
    // the broken state its siblings catch is confirming nothing.
    //
    // So it asserts the PAINT positively now, and it asserts the CONTRAST: the
    // two arms must disagree on this exact selector, which is the whole claim
    // the control exists to make.
    const segmentsOf = (html: string) =>
      html.match(/<div class="rounded-full[^"]*"[^>]*style="[^"]*width:[^"]*"[^>]*>/g) ?? [];

    const twoWay = segmentsOf(
      renderToStaticMarkup(<EventCard event={sharedEvent(TWO_WAY_SPORT)} />),
    );
    // Both halves of the bar are drawn — a rendered card, not an empty one.
    expect(twoWay).toHaveLength(2);

    const away = twoWay[1];
    expect(away).toContain("background-color");
    expect(away).not.toContain("bg-surface-border/30");
    expect(away).not.toContain("data-bar-remainder");

    // The contrast. Same selector, same position, draw-priced sport: the away
    // half is the neutral unattributed remainder. If this ever matched the
    // two-way shape the assertions above would be describing nothing.
    const drawPriced = segmentsOf(
      renderToStaticMarkup(<EventCard event={sharedEvent(DRAW_SPORT)} />),
    );
    expect(drawPriced).toHaveLength(2);
    expect(drawPriced[1]).toContain('data-bar-remainder="unattributed"');
    expect(drawPriced[1]).not.toContain("background-color");
  });
});

// ── Discover's event card ────────────────────────────────────────────────────

function discoverItem(sport: string): FeedItem {
  return {
    type: "event",
    data: {
      id: 15308959,
      external_id: "disc-6238",
      sport,
      sport_name: "League",
      home_team: "Sevilla FC",
      away_team: "Deportivo Alaves",
      commence_time: KICKOFF,
      status: "scheduled",
      home_score: null,
      away_score: null,
      current_odds: { home_probability: HOME_PROB, away_probability: AWAY_PROB },
    } as unknown as FeedEventData,
  } as FeedItem;
}

/** This card takes the item AND its unwrapped `data` — it reads both. */
function renderDiscover(sport: string): string {
  const item = discoverItem(sport);
  return renderToStaticMarkup(
    <DiscoverEventCard
      item={item}
      data={item.data as FeedEventData}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("#6238 Discover's event card", () => {
  it("withholds the away figure and keeps the home one", () => {
    const html = renderDiscover(DRAW_SPORT);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).not.toContain(AWAY_TEXT);
    // The strip is `justify-between`, so with the away span gone the home
    // number stays hard right under the home crest. It is also LABELLED there
    // now — "needs no renaming" was this comment's original claim and page one
    // disproved it on 2026-09-18 (discover/198, `drawPricedCardNamesItsNumber`).
    // Both assertions below are unchanged; only the reasoning moved.
    expect(html).toContain('data-testid="event-card-home-probability"');
    expect(html).not.toContain('data-testid="event-card-away-probability"');
  });

  it("CONTROL: a two-way sport prints both figures", () => {
    const html = renderDiscover(TWO_WAY_SPORT);
    expect(html).toContain('data-testid="event-card-away-probability"');
    expect(text(html)).toContain(AWAY_TEXT);
  });

  it("paints the bar home-only on a draw-priced sport", () => {
    const html = renderDiscover(DRAW_SPORT);
    expect(html).toContain('data-away-withheld="true"');
  });
});

// ── DuelKernel ───────────────────────────────────────────────────────────────

describe("#6238 DuelKernel", () => {
  const props = {
    state: "upcoming" as const,
    awayTeam: "Deportivo Alaves",
    homeTeam: "Sevilla FC",
    awayProb: AWAY_PROB,
    homeProb: HOME_PROB,
    categorySlug: "sports",
    categoryLabel: "Soccer",
    categoryEmoji: "⚽",
  };

  it("withholds the away figure when told to, and keeps the home one", () => {
    const html = renderToStaticMarkup(<DuelKernel {...props} awayWithheld />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).not.toContain(AWAY_TEXT);
    expect(html).toContain('data-away-withheld="true"');
  });

  it("CONTROL: the default is unchanged, both sides printed", () => {
    const html = renderToStaticMarkup(<DuelKernel {...props} />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).toContain(AWAY_TEXT);
    expect(html).not.toContain('data-away-withheld="true"');
  });
});

// ── MatchupDuel: the event-concept (tournament bracket) duel ─────────────────

function matchupChild(): EventConceptChild {
  return {
    kind: "matchup",
    event_id: 15298551,
    status: "scheduled",
    commence_time: KICKOFF,
    home: { name: "Sevilla FC", probability: HOME_PROB },
    away: { name: "Deportivo Alaves", probability: AWAY_PROB },
  } as unknown as EventConceptChild;
}

describe("#6238 MatchupDuel — the concept page's bracket card", () => {
  it("withholds the away row's number on a draw-priced container", () => {
    // These rows name themselves (crest, then team, then the number), so the
    // withheld side renders nothing and nothing has to be renamed.
    const html = renderToStaticMarkup(<MatchupDuel child={matchupChild()} sport="soccer" />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).not.toContain(AWAY_TEXT);
    // Still a card: both teams are still named.
    expect(text(html)).toContain("Deportivo Alaves");
    expect(text(html)).toContain("Sevilla FC");
  });

  it("does not renormalise the split bar to a full-width home fill", () => {
    // 🔴 THE SPECIMEN HAS TO BE THE ONE WITH NO AWAY FLOAT, and a mutation run is
    // what said so. With a served pair summing to 1, `h / (h + a)` IS `h` — so
    // reintroducing the renormalisation changed nothing and the first version of
    // this test passed on the mutant.
    //
    // The divergence only appears when the away value is absent: the old
    // arithmetic reads `0.74 / 0.74` and paints a FULL-WIDTH home bar on a match
    // the home side is a 74% chance in. That is the loudest possible version of
    // the claim this ship removes, so it is the specimen worth pinning.
    const child = matchupChild();
    (child as { away?: unknown }).away = { name: "Deportivo Alaves" };
    const html = renderToStaticMarkup(<MatchupDuel child={child} sport="soccer" />);
    expect(html).toContain('data-away-withheld="true"');
    expect(html).toContain("width:74%");
    expect(html).not.toContain("width:100%");
  });

  it("CONTROL: an undeclared container keeps its two-sided reading", () => {
    const html = renderToStaticMarkup(<MatchupDuel child={matchupChild()} sport="mma" />);
    expect(text(html)).toContain(HOME_TEXT);
    expect(text(html)).toContain(AWAY_TEXT);
  });

  it("CONTROL: no sport at all is the same two-sided reading", () => {
    const html = renderToStaticMarkup(<MatchupDuel child={matchupChild()} />);
    expect(text(html)).toContain(AWAY_TEXT);
  });
});

// ── The share image ──────────────────────────────────────────────────────────

/**
 * The OG card is an edge-runtime route returning an `ImageResponse`, so it is
 * read as SOURCE rather than rendered. That is weaker than the assertions above
 * and is said out loud rather than dressed up: what it pins is that the route
 * asks the rule at all, and that the SCORE arm was not caught in the
 * withholding. It cannot see what the image looks like.
 */
describe("#6238 the share image asks the rule", () => {
  const OG = fs.readFileSync(
    path.join(__dirname, "../../app/events/[id]/opengraph-image.tsx"),
    "utf8",
  );

  it("decides `awayWithheld` from the declaration, not from a key test", () => {
    expect(OG).toMatch(/const awayWithheld = awayIsTheComplement\(/);
    expect(OG).not.toMatch(/sport.*\.startsWith\(["']soccer/);
  });

  it("withholds the away FORECAST but never the away SCORE", () => {
    // A settled scoreline is a result, not a forecast. Withholding it would
    // delete the one thing a finished share card exists to carry.
    expect(OG).toMatch(/const awayHero = final\s*\?\s*showScore\s*\?\s*`\$\{event\.away_score\}`/);
    expect(OG).toMatch(/:\s*awayWithheld\s*\n\s*\?\s*null/);
  });

  it("does not leave the bar painted full-width home", () => {
    // The track is the HOME colour and the away div is laid over it, so leaving
    // it whole draws 100% home — the loudest possible version of the claim.
    expect(OG).toMatch(/background: awayWithheld \? "#e2e8f0" : homeColor/);
  });
});
