// THE LEAGUE PAGE'S CARD HEADER STOPS SAYING "PRO FOOTBALL" — #7397, the SEAM.
//
// Photographed on production, `/sport/americanfootball/nfl` at 390px,
// 2026-09-20 ~07:45Z. The page's own title is NFL. At y≈18,900, four consecutive
// card headers:
//
//     PRO FOOTBALL: NEW YORK J TOTAL WINS
//     PRO FOOTBALL: JACKSONVILLE TOTAL WINS
//     PRO FOOTBALL: ATLANTA TOTAL WINS
//     PRO FOOTBALL: LOS ANGELES R TOTAL WINS
//
// ── WHY A FRONTEND TEST FOR A BACKEND FIX ──
//
// Neither half of this is provable alone, and each half looks fine on its own.
//
// The backend now rewrites the venue's league phrase in `league_futures.py`, and
// `backend/tests/test_league_page_league_vocabulary_7397.py` pins that payload.
// But the payload is not what a reader sees: `LeagueMarketSection` renders
// `cleanMarketName(market.name)`, and `cleanMarketName` strips a LEADING league
// prefix — `/^(NBA|NHL|MLB|NFL|WNBA|MLS)[:\s]+/i`. So the header a person reads
// is a COMPOSITION of the two, and it is the composition that was broken:
//
//   today   "Pro Football: New York J Total Wins"  -> no prefix match, nothing
//                                                     stripped -> the venue's
//                                                     word is painted in full
//   fixed   "NFL: New York J Total Wins"           -> prefix matches -> the
//                                                     reader gets the clean
//                                                     "New York J Total Wins"
//
// Note what that regex already contains: NFL, and WNBA. The frontend was built
// expecting our league vocabulary and the backend had been handing it the
// venue's — which is also why the fix improves the page rather than merely
// renaming the lie. No frontend change is needed or made here.
//
// ── THE ARM THAT MATTERS MOST ──
//
// The first attempt at the backend fix rewrote `Women's Pro Basketball` (the
// WNBA, 58 markets) to `Women's NBA`. `cleanMarketName` does NOT rescue that:
// the string does not START with `NBA`, so nothing is stripped and the page
// paints "WOMEN'S NBA MVP WINNER" in full. That case is asserted below as a
// negative, because it is the one a reader would have complained about.

import { cleanMarketName } from "@/lib/leagueCards";

/**
 * The backend's rewrite, transcribed. Kept deliberately SMALL and dumb: this
 * file is not re-testing the Python rules (that is
 * `test_search_league_vocabulary_7397.py`, 118 arms) — it is feeding this seam
 * the exact strings the route now serves, so the composition is what is pinned.
 */
const SERVED: Array<{ venue: string; served: string; reads: string }> = [
  // The four stacked cards in the screenshot.
  {
    venue: "Pro Football: New York J Total Wins",
    served: "NFL: New York J Total Wins",
    reads: "New York J Total Wins",
  },
  {
    venue: "Pro Football: Jacksonville Total Wins",
    served: "NFL: Jacksonville Total Wins",
    reads: "Jacksonville Total Wins",
  },
  {
    venue: "Pro Football: Atlanta Total Wins",
    served: "NFL: Atlanta Total Wins",
    reads: "Atlanta Total Wins",
  },
  {
    venue: "Pro Football: Los Angeles R Total Wins",
    served: "NFL: Los Angeles R Total Wins",
    reads: "Los Angeles R Total Wins",
  },
  // A space rather than a colon after the league word.
  {
    venue: "Pro Football Championship MVP?",
    served: "NFL Championship MVP?",
    reads: "Championship MVP?",
  },
  // The WNBA page, 23 rows of this shape.
  {
    venue: "Women's Pro Basketball MVP Winner",
    served: "WNBA MVP Winner",
    reads: "MVP Winner",
  },
  {
    venue: "Women's Pro Basketball: Las Vegas Aces Total Wins",
    served: "WNBA: Las Vegas Aces Total Wins",
    reads: "Las Vegas Aces Total Wins",
  },
];

const VENUE_WORD = /\bPro (Football|Basketball|Hockey|Baseball)\b/i;

describe("the league page card header, end to end", () => {
  it.each(SERVED)(
    "$venue -> reader sees $reads",
    ({ served, reads }) => {
      expect(cleanMarketName(served)).toBe(reads);
    },
  );

  it.each(SERVED)(
    "$venue: no header still carries the venue's league word",
    ({ served }) => {
      expect(cleanMarketName(served)).not.toMatch(VENUE_WORD);
    },
  );

  // THE BEFORE. Without this the suite would pass just as happily against a
  // page that was never broken, and would not show what the fix is worth.
  it.each(SERVED)(
    "$venue: the venue name was NOT cleaned up by the frontend alone",
    ({ venue }) => {
      expect(cleanMarketName(venue)).toMatch(VENUE_WORD);
    },
  );

  it("the frontend cannot rescue a wrongly-renamed league", () => {
    // What the first, defective backend sha would have served. The strip is
    // anchored at the start, so a qualifier in front of the league token means
    // nothing is removed and the whole wrong sentence is painted.
    expect(cleanMarketName("Women's NBA MVP Winner")).toBe(
      "Women's NBA MVP Winner",
    );
    expect(
      cleanMarketName("Women's NBA: Las Vegas Aces Total Wins"),
    ).toBe("Women's NBA: Las Vegas Aces Total Wins");
  });

  it("a WNBA header is never reduced to an NBA one", () => {
    // `WNBA` contains `NBA`, so an anchored-but-sloppy strip could take the
    // wrong three letters and leave a header claiming the wrong league.
    const out = cleanMarketName("WNBA: Las Vegas Aces Total Wins");
    expect(out).toBe("Las Vegas Aces Total Wins");
    expect(out).not.toMatch(/\bNBA\b/);
  });

  it("an ordinary title is untouched", () => {
    // The control. A strip that ate more than the league prefix would pass
    // every assertion above while quietly shortening unrelated headers.
    expect(cleanMarketName("Most Regular Season Wins")).toBe(
      "Most Regular Season Wins",
    );
    expect(cleanMarketName("Coach of the Year Winner")).toBe(
      "Coach of the Year Winner",
    );
  });
});
