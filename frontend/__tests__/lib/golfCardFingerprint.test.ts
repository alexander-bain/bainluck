/**
 * UX-P270 (#2661 / CERT-740): the table re-reads when the card's numbers move.
 *
 * The backend makes the progression endpoint adopt `GET /api/golf`'s win numbers,
 * so the two lists on `/categories/golf` publish the same number for the same
 * golfer. That agreement reaches the screen only if the page re-reads progression
 * when the card changes — the card refetches every 120s, the progression fetch was
 * one-shot (`if (progressionData) return`), so the first hourly precompute to land
 * mid-session moved the card and left the table quoting the previous one.
 *
 * The page keys that refetch on this fingerprint. Jest in this repo cannot run the
 * effect (see `frontend/jest.config.js` — components render, effects do not), so
 * the effect's CORRECTNESS is pinned here on the pure value it depends on: the
 * fingerprint must change when an adopted number changes and must not change
 * otherwise. A fingerprint that never changes silently restores the one-shot bug;
 * a fingerprint that always changes turns an hourly refetch into a 120s one
 * against an uncached endpoint.
 *
 * Prices are the real production values for Omega European Masters on 2026-09-02.
 */

import { golfCardWinFingerprint } from "@/lib/golfCardFingerprint";
import type { GolfGolfer, GolfResponse } from "@/lib/types";

const OMEGA_KEY = "omega-european-masters";

function golfer(name: string, probability: number): GolfGolfer {
  return {
    name,
    probability,
    american_odds: null,
    opening_probability: null,
    movement_24h: null,
    rank: 1,
    sources: {},
  };
}

/** The 15 golfers the card actually publishes for this tournament. */
const CARD_FIELD = [
  golfer("Ryan Gerard", 0.085),
  golfer("Matt Wallace", 0.058),
  golfer("Nicolai Højgaard", 0.044),
  golfer("Marco Penge", 0.04),
  golfer("Rasmus Højgaard", 0.04),
  golfer("Eugenio Chacarra", 0.033),
  golfer("Patrick Reed", 0.033),
  golfer("Keita Nakajima", 0.03),
  golfer("Harry Hall", 0.029),
  golfer("Thomas Detry", 0.025),
  golfer("Angel Ayora", 0.024),
  golfer("Casey Jarvis", 0.022),
  golfer("Daniel Hillier", 0.022),
  golfer("Sergio Garcia", 0.02),
  golfer("Jayden Schaper", 0.019),
];

function payload(field = CARD_FIELD, extra: Record<string, unknown> = {}) {
  return {
    tournaments: [
      { key: "biltmore", name: "Biltmore Championship Asheville", golfers: [golfer("Someone Else", 0.182)] },
      { key: OMEGA_KEY, name: "Omega European Masters", golfers: field },
    ],
    current_event: {
      key: OMEGA_KEY,
      name: "Omega European Masters",
      market_ids: [59863411, 59759220],
      top_golfers: field.slice(0, 5),
    },
    ...extra,
  } as unknown as GolfResponse;
}

describe("golfCardWinFingerprint", () => {
  describe("the ship: it moves when an adopted number moves", () => {
    it("changes when the leader's probability changes", () => {
      const before = golfCardWinFingerprint(payload());
      const moved = CARD_FIELD.map((g) =>
        g.name === "Ryan Gerard" ? golfer("Ryan Gerard", 0.091) : g
      );

      expect(golfCardWinFingerprint(payload(moved))).not.toBe(before);
    });

    it("changes when a golfer BELOW the top-5 slice moves", () => {
      // `current_event.top_golfers` is only 5 long, but the authority overrides
      // every golfer the card carries. Fingerprinting the short list would leave
      // rows 6-15 able to move without triggering a re-read.
      const before = golfCardWinFingerprint(payload());
      const moved = CARD_FIELD.map((g) =>
        g.name === "Sergio Garcia" ? golfer("Sergio Garcia", 0.031) : g
      );

      expect(golfCardWinFingerprint(payload(moved))).not.toBe(before);
    });

    it("changes when a golfer joins or leaves the card's field", () => {
      const before = golfCardWinFingerprint(payload());
      const shorter = CARD_FIELD.slice(0, 14);

      expect(golfCardWinFingerprint(payload(shorter))).not.toBe(before);
    });

    it("changes when the current tournament changes", () => {
      const omega = golfCardWinFingerprint(payload());
      const biltmore = golfCardWinFingerprint(
        payload(CARD_FIELD, {
          current_event: {
            key: "biltmore",
            name: "Biltmore Championship Asheville",
            market_ids: [59863406],
            top_golfers: [],
          },
        })
      );

      expect(biltmore).not.toBe(omega);
    });
  });

  describe("the cost control: it holds still when nothing adopted moved", () => {
    it("is stable across two identical payloads", () => {
      // The card is polled every 120s but rebuilt hourly, so the overwhelmingly
      // common case is an unchanged payload. If this were unstable the page would
      // hammer an uncached endpoint ~30x more often than it needs to.
      expect(golfCardWinFingerprint(payload())).toBe(
        golfCardWinFingerprint(payload())
      );
    });

    it("ignores a movement figure the table does not adopt", () => {
      const before = golfCardWinFingerprint(payload());
      const churned = CARD_FIELD.map((g) => ({ ...g, movement_24h: 0.02, rank: 9 }));

      expect(golfCardWinFingerprint(payload(churned))).toBe(before);
    });

    it("ignores another tournament's prices changing", () => {
      const before = golfCardWinFingerprint(payload());
      const other = payload();
      (other.tournaments as unknown as { key: string; golfers: unknown[] }[])[0].golfers =
        [golfer("Someone Else", 0.42)];

      expect(golfCardWinFingerprint(other)).toBe(before);
    });
  });

  describe("it never throws on a payload the page can actually receive", () => {
    it("returns null before the first fetch resolves", () => {
      expect(golfCardWinFingerprint(null)).toBeNull();
    });

    it("returns null when there is no current tournament", () => {
      const noEvent = payload(CARD_FIELD, { current_event: null });

      expect(golfCardWinFingerprint(noEvent)).toBeNull();
    });

    it("falls back to top_golfers when the tournament list omits the event", () => {
      const orphan = payload(CARD_FIELD, { tournaments: [] });

      expect(golfCardWinFingerprint(orphan)).toBe(
        CARD_FIELD.slice(0, 5)
          .map((g) => `${g.name}=${g.probability}`)
          .join("|")
      );
    });

    it("returns an empty fingerprint, not a throw, for a tournament with no golfers", () => {
      expect(golfCardWinFingerprint(payload([]))).toBe("");
    });
  });
});
