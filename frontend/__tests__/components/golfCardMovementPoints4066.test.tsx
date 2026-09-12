/**
 * #4066 D1 clause (a) / CERT-2721 repair
 * `4066-DISCOVER-GOLF-CARD-RENDERS-MOVEMENT-AS-POINTS`
 *
 * A FIRST-TEN DISCOVER CARD SAYS A MOVE IN THE UNIT THE NUMBER IS IN.
 *
 * ── WHAT THE BLOCKED COMMIT FIXED, AND THE HALF IT MISSED ───────────────────
 *
 * `913af5613` fixed the backend `reason` sentence: `_score_golf_tournaments`
 * stopped printing `(up 10.0% today)` and started delegating to
 * `feed_reasons._points`, so the served string now reads `(up 10 points today)`.
 *
 * That is one of the two places the number reaches the reader. The card ALSO
 * renders `movement_24h` itself: `DiscoverCard` -> `discover/TournamentCard`
 * -> `MovementBadge` (`components/discover/shared.tsx`), whose visible body was
 *
 *     {pts}%
 *
 * while `pts` was `Math.abs(Math.round(movementPoints(m)))` -- already POINTS.
 * So the green pill on the hero kept saying "10%" no matter what the backend
 * sentence said, and CERT-2721 blocked on exactly this.
 *
 * The badge's own `aria-label` has always read `Up 10 points in the last 24h`.
 * The component stated the correct unit to a screen reader and the wrong one to
 * the eye -- the spec was sitting next to the bug.
 *
 * ── THE SPECIMEN IS REAL ────────────────────────────────────────────────────
 *
 * `GET https://api.bainluck.com/api/feed`, 2026-09-12 13:27Z, the Amgen Irish
 * Open tournament card:
 *
 *     reason : "DP World Tour: Shane Lowry leads at 47.7% (up 10.0% today)"
 *     leader : {"name":"Shane Lowry","probability":0.478,"movement_24h":0.1}
 *
 * `movement_24h: 0.1` is a probability delta, so Lowry went 37.8% -> 47.8%: TEN
 * POINTS. Rendered "10%" a reader gets about 4.8 points, under half the move.
 *
 * ── WHY THIS ENTERS AT `DiscoverCard` ───────────────────────────────────────
 *
 * The defect is not inside `MovementBadge`'s markup in isolation -- it is what
 * the default Discover path actually draws. A test that rendered `MovementBadge`
 * directly would pass on a tree where `TournamentCard` had been rewired to some
 * other badge. So the test enters where the payload does: `DiscoverCard` with an
 * untouched `type:"tournament"` item of the shape `/api/feed` serves.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. the served card prints the move in POINTS and no longer prints `10%`;
 *  2. the number is READ FROM THE PAYLOAD, not baked in -- a different
 *     `movement_24h` changes the rendered figure (a `toContain("10")` on one
 *     string cannot tell a wired prop from a hard-coded one);
 *  3. the accessible label and the visible text agree on the unit, which is the
 *     specific disagreement that made this defect survive review;
 *  4. SIGN. A downward move still renders as a down move, in points;
 *  5. FLOOR CONTROL. A sub-threshold move still renders no badge at all, so
 *     "no percent anywhere" cannot be satisfied by suppressing the badge.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { FeedTournamentData, FeedItem } from "@/lib/types";

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

import DiscoverCard from "../../components/DiscoverCard";

/** The production specimen, Amgen Irish Open, read 2026-09-12 13:27Z. */
function tournamentItem(movement24h: number | null): FeedItem {
  return {
    type: "tournament",
    score: 78,
    reason: "DP World Tour: Shane Lowry leads at 47.7% (up 10 points today)",
    headline: null,
    data: {
      key: "amgen_irish_open",
      name: "Amgen Irish Open",
      tour: "dpworld",
      tour_label: "DP World Tour",
      is_major: false,
      golfers: [
        { name: "Shane Lowry", probability: 0.478, rank: 1, movement_24h: movement24h },
        { name: "Rory McIlroy", probability: 0.161, rank: 2, movement_24h: null },
      ],
      market_ids: [60481964],
      source_count: 2,
    } as unknown as FeedTournamentData,
  } as unknown as FeedItem;
}

function draw(movement24h: number | null): string {
  return renderToStaticMarkup(
    <DiscoverCard
      groupedItem={{ type: "single", item: tournamentItem(movement24h) }}
      positionIndex={0}
    />,
  );
}

/**
 * WHAT THE EYE SEES — text nodes only, with every tag and therefore every
 * attribute removed.
 *
 * This matters more than it looks. The badge's `title`/`aria-label` ALREADY
 * said "Up 10 points in the last 24h" on the blocked commit, so a positive
 * assertion against the raw markup (`toMatch(/10 points/)`) passes on the
 * broken tree -- it is reading the label, not the badge. Measured: with the
 * defect restored, 3 of these 5 arms stayed green for exactly that reason.
 * The visible claim has to be checked against visible text.
 */
function visible(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
}

describe("#4066 D1(a) — the Discover golf card states a move in points", () => {
  it("prints the leader's move in POINTS, never as a percent", () => {
    const seen = visible(draw(0.1));

    // The badge says points, IN THE TEXT — not just in its accessible label.
    expect(seen).toMatch(/10\s*(pts|points)/);

    // And the wrong unit is gone. Scoped to the movement figure: the card
    // legitimately prints "47.7%" for the PROBABILITY, so a bare
    // `not.toContain("%")` would fail on a correct card and would be testing
    // the wrong claim entirely.
    expect(seen).not.toMatch(/10(\.0)?\s*%/);
  });

  it("reads the figure from the payload rather than baking it in", () => {
    // A different move must move the number. Guards against a literal.
    const seen = visible(draw(0.235));
    expect(seen).toMatch(/2[34]\s*(pts|points)/);
    expect(seen).not.toMatch(/\b10\s*(pts|points)/);
  });

  it("the accessible label and the visible text agree on the unit", () => {
    // This disagreement is why the bug survived: `aria-label` was already
    // correct while the eye saw a percent.
    const html = draw(0.1);
    expect(html).toContain("10 points in the last 24h"); // the label, in the markup
    expect(visible(html)).toMatch(/10\s*(pts|points)/); // and the eye agrees
  });

  it("a downward move still renders, in points", () => {
    const html = draw(-0.1);
    expect(visible(html)).toMatch(/10\s*(pts|points)/);
    expect(visible(html)).not.toMatch(/10(\.0)?\s*%/);
    expect(html).toContain("Down 10 points in the last 24h");
  });

  it("CONTROL: a sub-threshold move renders no badge, so arm 1 cannot pass by suppression", () => {
    // BADGE_MIN_MOVEMENT_POINTS is 2, so a 1-point move is below the bar. If a
    // future edit satisfied "no percent" by dropping the badge entirely, arm 1
    // would still pass -- this arm is what notices the difference, by proving
    // the badge is absent HERE and present above.
    const html = draw(0.01);
    expect(visible(html)).not.toMatch(/1\s*(pts|points)/);
    expect(html).not.toMatch(/in the last 24h/);
  });
});
