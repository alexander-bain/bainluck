/**
 * #7226 — the Discover golf card's movement badge may only say "24h" about a
 * move that is one. Sub-issue of #4079; the client half of #7179.
 *
 * ── WHAT A READER SAW ───────────────────────────────────────────────────────
 *
 * Production 2026-09-19 13:29Z, 390px, the *Biltmore Championship Asheville*
 * card (`artifacts-discover/7179-aftercheck/FRAME-discover-biltmore-1331Z.png`):
 *
 *     27%   Neal Shipley
 *           ▲ 17 pts          <- announced "Up 17 points in the last 24h"
 *
 * `MovementBadge` (`components/discover/shared.tsx`) gives every badge it draws
 * that accessible label. So the card asserts a 24-hour move.
 *
 * ── WHY THAT IS THE #4079 CLASS ─────────────────────────────────────────────
 *
 * `movement_24h` on a golfer is TWO measurements sharing one field name. The
 * golf aggregation subtracts a 23-25h `FuturesOddsSnapshot` when one is in
 * range, and falls back to the per-write `probability_change_24h` when it is
 * not — a delta since the last write, which may be a minute or a month old.
 * #7179 added `movement_is_dated` so a surface can ask which it got.
 *
 * The server sentence asked. The badge could not:
 *
 *   server `reason`   `(up 16.6 points today)`   gated  (routes/feed.py)
 *   client badge      `▲ 17 pts`, "last 24h"     UNGATED
 *
 * and it could not be gated, because the flag was not on the wire for this
 * card. Measured 2026-09-19 18:10Z, after #7179 was live:
 *
 *   GET /api/golf                 movement_is_dated on 135/135 golfers
 *                                 (108 dated, 27 NOT — a populated refusal)
 *   GET /api/feed?category=golf   golfer keys = movement_24h, name,
 *                                 probability, rank.  Flag absent everywhere.
 *
 * The two surfaces measurably disagreed on 2026-09-19: at 13:08Z the server had
 * refused to date Shipley's move while the badge condition (>= 2 points) was
 * met, so the card announced "Up 20 points in the last 24h" in the same minute
 * its own sentence declined to say "today".
 *
 * ── WHY THE TEST ENTERS AT `DiscoverCard` ───────────────────────────────────
 *
 * Same reason as its sibling `golfCardMovementPoints4066.test.tsx`: a test that
 * rendered `MovementBadge` directly would pass on a tree where `TournamentCard`
 * had been rewired to draw some other badge, and the defect is what the default
 * Discover path actually draws. So the payload enters where the real one does.
 *
 * ── THE ARMS ────────────────────────────────────────────────────────────────
 *
 *  1. DATED — the badge draws, in points, with its 24h label. Without this the
 *     suite is satisfiable by deleting the badge, which is not the fix.
 *  2. UNDATED — no badge, and specifically no "last 24h" claim anywhere.
 *  3. ABSENT — a payload built before the producer shipped carries no key at
 *     all, and that refuses too. This is the arm that matters in the up-to-2h
 *     `last_good` window after a deploy, and the one a `?? true` default or a
 *     truthiness check would silently break.
 *  4. CONTROL: the rest of the card is untouched. This ship narrows what the
 *     card may SAY about the move — it must not drop the card, the hero
 *     percentage, the leader's name or the tournament. An undated move is still
 *     a shown card, and #7179's selection/ranking rule depends on that.
 *  5. CONTROL: the floor still applies to a DATED move. `movement_is_dated`
 *     gates the claim; it does not promote a sub-threshold move into a badge.
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

import DiscoverCard from "../../components/DiscoverCard";

/**
 * The production specimen, Biltmore Championship Asheville, read 2026-09-19.
 *
 * `dated: undefined` OMITS the key entirely — that is a pre-producer payload,
 * which is a different input from `false` and is arm 3.
 */
function tournamentItem(dated: boolean | undefined): FeedItem {
  const leader: Record<string, unknown> = {
    name: "Neal Shipley",
    probability: 0.279,
    rank: 1,
    movement_24h: 0.1662, // 16.6 points — comfortably over the 2-point floor
  };
  if (dated !== undefined) leader.movement_is_dated = dated;

  return {
    type: "tournament",
    score: 74,
    // The SERVER sentence is already gated (#7179), so it carries no "today"
    // clause here. The whole defect is that the badge disagreed with it.
    reason: "PGA Tour: Neal Shipley leads at 27.9%",
    headline: "Live",
    data: {
      key: "biltmore",
      name: "Biltmore Championship Asheville",
      tour: "pga",
      tour_label: "PGA Tour",
      is_major: false,
      golfers: [leader, { name: "Ricky Castillo", probability: 0.213, rank: 2, movement_24h: null }],
      market_ids: [60482001],
      source_count: 2,
    } as unknown as FeedTournamentData,
  } as unknown as FeedItem;
}

function draw(dated: boolean | undefined): string {
  return renderToStaticMarkup(
    <DiscoverCard
      groupedItem={{ type: "single", item: tournamentItem(dated) }}
      positionIndex={0}
    />,
  );
}

/** Text nodes only — every tag, and therefore every attribute, removed. */
function visible(html: string): string {
  return html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ");
}

describe("#7226 — the Discover golf badge dates its 24h claim", () => {
  it("draws the badge when the server says the move is dated", () => {
    const html = draw(true);
    expect(visible(html)).toMatch(/17\s*(pts|points)/);
    expect(html).toContain("Up 17 points in the last 24h");
  });

  it("draws NO badge when the move is the per-write fallback", () => {
    const html = draw(false);
    // The claim, in the accessible label AND in the markup at large.
    expect(html).not.toContain("in the last 24h");
    // And the number itself is gone from the eye's version, so this cannot be
    // satisfied by hiding the label and keeping the arrow.
    expect(visible(html)).not.toMatch(/17\s*(pts|points)/);
  });

  it("draws NO badge when the payload predates the flag (absent, not false)", () => {
    const html = draw(undefined);
    expect(html).not.toContain("in the last 24h");
    expect(visible(html)).not.toMatch(/17\s*(pts|points)/);
  });

  it.each([
    ["dated", true],
    ["undated", false],
    ["pre-flag", undefined],
  ] as const)(
    "CONTROL: a %s move still renders the whole card",
    (_label, dated) => {
      const html = draw(dated);
      const seen = visible(html);
      // The card, its hero and its leader survive in every case. Silencing a
      // claim is not allowed to become a ranking or suppression policy (#7179).
      expect(seen).toContain("Biltmore Championship Asheville");
      expect(seen).toContain("Neal Shipley");
      // The hero is still drawn. In static markup `AnimatedProbability` prints
      // its em-dash rather than a number — the counter has not started, and
      // #3119 made that the component's word for "no reading yet" precisely so
      // an off-screen hero would stop printing a confident `0%`. So the dash IS
      // the hero rendering correctly here, and asserting a `28%` that only a
      // browser produces would be asserting against the wrong renderer.
      expect(seen).toContain("—");
    },
  );

  it("CONTROL: refusing changes the badge and nothing else on the card", () => {
    // The sharpest form of the control. Whatever the two refusal paths do, they
    // must be the SAME thing, and they must differ from the dated render only
    // by the badge — not by a dropped hero, a reordered field, or a lost name.
    const undated = visible(draw(false));
    const preFlag = visible(draw(undefined));
    expect(undated).toBe(preFlag);

    const dated = visible(draw(true));
    expect(dated).not.toBe(undated); // else the gate is inert and arm 1 is a lie
    // Remove exactly the badge's visible text from the dated render; what is
    // left must be byte-identical to the refusal.
    expect(dated.replace(/\s*17\s*pts\s*/, " ").replace(/\s+/g, " ")).toBe(undated);
  });

  it("CONTROL: dated does not promote a sub-threshold move into a badge", () => {
    const item = tournamentItem(true);
    // 0.8 of a point — under the badge's 2-point floor.
    (item as unknown as { data: { golfers: { movement_24h: number }[] } }).data.golfers[0].movement_24h = 0.008;
    const html = renderToStaticMarkup(
      <DiscoverCard groupedItem={{ type: "single", item }} positionIndex={0} />,
    );
    expect(html).not.toContain("in the last 24h");
    expect(visible(html)).toContain("Neal Shipley");
  });
});
