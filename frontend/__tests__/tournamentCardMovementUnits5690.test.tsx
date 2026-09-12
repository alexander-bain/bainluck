/**
 * #5690 — one `movement` field, two sources, two units, one `* 100`.
 *
 * ═══ WHAT A READER SAW ═══
 *
 * `/sport/golf/dpworld`, production 2026-09-12 17:56Z, 390px — the live Amgen
 * Irish Open card, final round:
 *
 *     76.5%   Shane Lowry
 *             Leader · -16 · H15   +2820.0 pts today
 *
 * A probability cannot move more than 100 points. `+2820.0` is not a large
 * number, it is an impossible one, and it sits on the same line as a 76.5% hero
 * — so the card contradicts itself in one glance.
 *
 * ═══ THE CAUSE, WHICH IS A UNIT SEAM AND NOT AN ARITHMETIC SLIP ═══
 *
 * `CardGolfer.movement` is consumed as a 0-1 probability DELTA — the render
 * multiplies by 100 through `formatMovementPoints`. `_buildLeader` fills it from
 * two different sources:
 *
 *   golfers arm      `g.movement_24h`       0.1656  -> 16.6 pts   ✅
 *   leaderboard arm  `lb.win_prob_change`   28.2    -> 2820.0 pts ❌
 *
 * `GET /api/golf/leaderboard?tour=euro` serves percent-scaled numbers, measured
 * at the source the same minute: `{"name": "Shane Lowry", "win_prob": 76.5,
 * "win_prob_change": 28.2}`.
 *
 * THE TELL WAS ALREADY IN THE CODE: `winProb` is taken raw on the leaderboard arm
 * and `* 100`-ed on the golfers arm, because whoever wrote it knew the two
 * sources disagree about PROBABILITY. The identical fact about MOVEMENT, one line
 * below, was missed.
 *
 * ═══ NOT A REGRESSION IN #5623 ═══
 *
 * #5623 changed `{(leader.movement * 100).toFixed(1)}%` to
 * `{formatMovementPoints(leader.movement)} pts`. Both multiply by 100, so the
 * magnitude is byte-identical across that ship — before it, this line read
 * "+2820.0%". #5623 did not cause this; its after-LOOK is how it was found.
 *
 * ═══ WHY THIS SUITE DRIVES BOTH ARMS ═══
 *
 * A test that only fed the leaderboard arm would pass on a "fix" that removed
 * the `* 100` at the render — which would silently break the golfers arm, the
 * COMMON path, the one that is currently right. The unit seam is only visible
 * when both arms are asked to describe the SAME move, so that is the shape here.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "../components/TournamentCard";
import type { GolfTournament, GolfLeaderboardPlayer } from "../lib/types";

/** Decode the few entities `renderToStaticMarkup` emits in this markup. */
const decode = (s: string) =>
  s.replace(/&#x27;|&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&");

function tournament(name: string, movement_24h: number, probability: number): GolfTournament {
  return {
    key: "amgen_irish_open",
    slug: "amgen-irish-open",
    name: "Amgen Irish Open",
    tour: "dp_world",
    tour_label: "DP World Tour",
    location: "Trump International Golf Links & Hotel Ireland",
    venue: null,
    start_date: "2026-09-10",
    end_date: "2026-09-13",
    commence_time: "2026-09-10T07:00:00Z",
    resolution_date: null,
    is_major: false,
    is_marquee: true,
    schedule_status: "live",
    source_count: 2,
    market_ids: [1],
    golfers: [{ name, probability, movement_24h, rank: 1 }],
  } as unknown as GolfTournament;
}

function lbPlayer(name: string, win_prob: number, win_prob_change: number | null): GolfLeaderboardPlayer {
  return {
    name,
    position: "1",
    score: "-16",
    thru: "15",
    win_prob,
    win_prob_change,
  } as unknown as GolfLeaderboardPlayer;
}

/** The magnitude and sign the leader caption prints, e.g. "+28.2" from "+28.2 pts today". */
function captionMove(markup: string): string {
  const m = /([-+]\d+\.\d+) pts today/.exec(decode(markup));
  if (!m) throw new Error(`card printed no "<n> pts today" caption: ${markup.slice(0, 400)}`);
  return m[1];
}

const renderWithLeaderboard = (win_prob: number, change: number | null) =>
  renderToStaticMarkup(
    <TournamentCard
      tournament={tournament("Shane Lowry", 0.0, win_prob / 100)}
      leaderboard={[lbPlayer("Shane Lowry", win_prob, change)]}
    />,
  );

const renderWithGolfersOnly = (probability: number, movement_24h: number) =>
  renderToStaticMarkup(
    <TournamentCard tournament={tournament("Shane Lowry", movement_24h, probability)} />,
  );

// ---------------------------------------------------------------------------

describe("#5690 — the two arms must agree on the unit", () => {
  test("THE PRODUCTION SPECIMEN: win_prob_change 28.2 prints +28.2 pts, not +2820.0", () => {
    expect(captionMove(renderWithLeaderboard(76.5, 28.2))).toBe("+28.2");
  });

  test("the golfers arm is UNCHANGED — 0.1656 still prints +16.6 pts", () => {
    // The common path, and the one a render-side "fix" would have broken.
    expect(captionMove(renderWithGolfersOnly(0.552, 0.1656))).toBe("+16.6");
  });

  test("BOTH ARMS DESCRIBE ONE MOVE THE SAME WAY — the seam, stated directly", () => {
    // 28.2 points expressed in each source's own units must reach the reader as
    // one string. This is the arm that fails for EITHER mis-scaling.
    const viaLeaderboard = captionMove(renderWithLeaderboard(76.5, 28.2));
    const viaGolfers = captionMove(renderWithGolfersOnly(0.765, 0.282));
    expect(viaLeaderboard).toBe(viaGolfers);
    expect(viaLeaderboard).toBe("+28.2");
  });

  test("a FALL keeps its sign through the normalisation", () => {
    // `formatMovementPoints` returns an absolute magnitude, so the sign is
    // composed at the call site; dividing by 100 must not disturb it.
    expect(captionMove(renderWithLeaderboard(2.5, -2.3))).toBe("-2.3");
  });

  test("no caption can exceed 100 points, over the whole live leaderboard", () => {
    // The class, not the specimen: a probability delta is bounded by 100 points,
    // so any caption above that is impossible whatever produced it.
    for (const change of [28.2, 8.1, -2.3, -8.1, 99.9, -99.9, 0.5]) {
      const printed = Number(captionMove(renderWithLeaderboard(50, change)));
      expect(Math.abs(printed)).toBeLessThanOrEqual(100);
      expect(Math.abs(printed)).toBeCloseTo(Math.abs(change), 1);
    }
  });

  test("a null change draws no caption rather than a zero", () => {
    const markup = renderWithLeaderboard(76.5, null);
    expect(decode(markup)).not.toMatch(/pts today/);
  });

  test("a change that rounds to nothing draws no caption", () => {
    // `isRenderedMove` on the normalised value: 0.004 points is 0.00004 as a
    // fraction, which prints "0.0" and must stay silent (#5652's class).
    const markup = renderWithLeaderboard(76.5, 0.004);
    expect(decode(markup)).not.toMatch(/pts today/);
  });

  test("the card still DRAWS the caption for a real move — not a guard satisfied by silence", () => {
    // gotcha #43's other direction: every assertion above about absence is also
    // satisfied by a card that stopped printing the line at all.
    expect(decode(renderWithLeaderboard(76.5, 28.2))).toMatch(/pts today/);
  });
});
