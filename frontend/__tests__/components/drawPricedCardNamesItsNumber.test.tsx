/**
 * #6238 FOLLOW-ON — WHEN THE DUEL COLLAPSES TO ONE NUMBER, THE NUMBER SAYS WHOSE IT IS.
 *
 * PILLAR: TRUTH / FORMATTING · SHIP: page one stops printing an unattributed
 * percentage two lines above a sentence about the other team.
 *
 * ## The specimen, production 2026-09-18 19:37Z, 390px, page one RANK 1
 *
 * `artifacts-discover/shop-1940Z/phone-top.png` — Elche CF @ Espanyol, La Liga,
 * LIVE at 33', crest strip reading **Elche 2 – Espanyol 0**, and beneath it:
 *
 *     Win Probability  ▮▮▮                      24%
 *     Elche CF leading after starting at 46%
 *
 * 24% is ESPANYOL's (`current_odds.home_probability` 0.2467). The caption names
 * ELCHE. Two numbers about two different teams in adjacent lines, neither one
 * labelled, and the card reads as "the team two goals up is a 24% chance, down
 * from 46%" — a move that never happened, about a team the number is not about.
 *
 * ## Why the withhold created this
 *
 * #6238 was right to delete the away figure on a draw-priced sport: it was
 * `1 − home`, the draw wearing the away team's name. But it left a reasoning
 * note saying the survivor "needs no renaming" because `justify-between` keeps
 * it hard right under the home crest. Position naming works while there are two
 * of them. With one number left, the crest strip is a separate block above the
 * fold of the card's text, and the reader has no marker at all.
 *
 * ## What this pins
 *
 * The collapsed arm names its number, the two-sided arm is untouched, and the
 * name is the HOME team's — a transposed label would read as a true sentence
 * about the wrong side, which is the failure mode this whole family is about.
 */

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
jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import { sportPricesADraw } from "@/lib/drawPricedWinner";

const DRAW_SPORT = "soccer_spain_la_liga";
const TWO_WAY_SPORT = "americanfootball_nfl";

/** The Elche card's own stored pair. */
const HOME_PROB = 0.2467; // Espanyol
const AWAY_PROB = 0.7533; // 1 − home: the complement #6238 withholds

const OWNER = 'data-testid="event-card-probability-owner"';

function card(sport: string): string {
  const item = {
    type: "event",
    data: {
      id: 15306048,
      external_id: "da3d3fec3e0b6b939910427a76ecfb76",
      sport,
      sport_name: "La Liga - Spain",
      home_team: "Espanyol",
      away_team: "Elche CF",
      commence_time: "2026-09-18T19:00:00+00:00",
      status: "live",
      home_score: 0,
      away_score: 2,
      current_odds: { home_probability: HOME_PROB, away_probability: AWAY_PROB },
    } as unknown as FeedEventData,
  } as FeedItem;
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

describe("#6238 follow-on — the collapsed duel names its survivor", () => {
  it("PREMISE: the two arms really are two arms", () => {
    // Without this the control below is the same card twice, which is how a
    // withholding suite goes vacuous (#6238's own note).
    expect(sportPricesADraw(DRAW_SPORT)).toBe(true);
    expect(sportPricesADraw(TWO_WAY_SPORT)).toBe(false);
  });

  it("the draw-priced card labels its one number with the home team", () => {
    const html = card(DRAW_SPORT);
    expect(html).toContain(OWNER);
    const owner = html.match(
      /data-testid="event-card-probability-owner"[^>]*>([^<]*)</,
    );
    expect(owner).not.toBeNull();
    expect(owner![1]).toBe("Espanyol");
  });

  it("the label is not the away team — a transposed name reads as true", () => {
    const owner = card(DRAW_SPORT).match(
      /data-testid="event-card-probability-owner"[^>]*>([^<]*)</,
    );
    expect(owner![1]).not.toBe("Elche CF");
  });

  it("the label sits with the number it names, not across the strip", () => {
    // Adjacency is the entire repair: the away slot is where a label would be
    // read as the away team's. The owner span must come AFTER the "Win
    // Probability" caption and immediately BEFORE the home figure.
    const html = card(DRAW_SPORT);
    const caption = html.indexOf("Win Probability");
    const owner = html.indexOf(OWNER);
    const figure = html.indexOf('data-testid="event-card-home-probability"');
    expect(caption).toBeGreaterThan(-1);
    expect(owner).toBeGreaterThan(caption);
    expect(figure).toBeGreaterThan(owner);
  });

  it("CONTROL: #6238's withhold is intact — no away figure came back", () => {
    const html = card(DRAW_SPORT);
    expect(html).not.toContain('data-testid="event-card-away-probability"');
    expect(html).toContain('data-away-withheld="true"');
  });

  it("CONTROL: a two-sided card is named by position and gets no label", () => {
    const html = card(TWO_WAY_SPORT);
    expect(html).not.toContain(OWNER);
    expect(html).toContain('data-testid="event-card-away-probability"');
    expect(html).toContain('data-testid="event-card-home-probability"');
  });

  it("CONTROL: the number itself is unchanged on both arms", () => {
    // A label is not a licence to move the figure. 25% is `renderedPercent`
    // of the stored 0.2467 and is what production served.
    for (const sport of [DRAW_SPORT, TWO_WAY_SPORT]) {
      const figure = card(sport).match(
        /data-testid="event-card-home-probability"[^>]*data-rendered-percent="(\d+)"/,
      );
      expect(figure).not.toBeNull();
      expect(figure![1]).toBe("25");
    }
  });
});
