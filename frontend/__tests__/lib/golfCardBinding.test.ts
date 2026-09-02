/**
 * UX-P271 (#2661; CERT-746 repair): the page names the card it is holding.
 *
 * UX-P270 shipped a page-side fingerprint of the card's win numbers and refetched
 * progression when it changed. CERT-746 withheld the token because that
 * fingerprint is computed from the card response ALONE, and so is structurally
 * blind to the failure it needs to catch:
 *
 *     `/api/golf` is served `public, max-age=300, stale-while-revalidate=60` while
 *     the progression request carries no `Cache-Control` at all. The page can
 *     therefore be showing a card up to 360s old against a table that read a newer
 *     one — and in exactly that case the fingerprint is perfectly STABLE, because a
 *     stale card hashes to the same string every time.
 *
 * A fingerprint over one of two clocks cannot detect that they disagree. So the
 * page sends a server-issued receipt naming the snapshot it is holding, and reacts
 * when the endpoint reports binding to a different one.
 *
 * WHY THESE ARE PURE TESTS. jest here cannot run effects, so the convergence
 * decision was lifted out of the component into `shouldRebindGolfCard` rather than
 * left as a condition inside the effect. Expressed inline it would be the single
 * most important unguarded branch in the ship — the one that decides whether a
 * user looking at two numbers ever stops looking at two numbers.
 *
 * The receipt itself is deliberately opaque here and never recomputed in
 * TypeScript: deriving it client-side would mean reimplementing the participant
 * name normalizer, and a second normalizer that drifts is precisely how UX-P270
 * nearly dropped both Højgaards.
 */

import {
  golfCardWinFingerprint,
  golfCardWinReceipt,
  shouldRebindGolfCard,
} from "../../lib/golfCardFingerprint";
import { fetchProgression, fetchGolfData } from "../../lib/api";
import type { GolfResponse } from "../../lib/types";

const OLD_RECEIPT = "a1b2c3d4e5f60718";
const NEW_RECEIPT = "0918f6e5d4c3b2a1";

function golfPayload({
  receipt = OLD_RECEIPT as string | null | undefined,
  currentKey = "omega-european-masters",
  includeReceiptField = true,
}: {
  receipt?: string | null;
  currentKey?: string | null;
  includeReceiptField?: boolean;
} = {}): GolfResponse {
  const tournament: Record<string, unknown> = {
    key: "omega-european-masters",
    name: "Omega European Masters",
    is_major: false,
    commence_time: null,
    resolution_date: null,
    market_ids: [59863411],
    golfers: [
      { name: "Ryan Gerard", probability: 0.085 },
      { name: "Matt Wallace", probability: 0.058 },
    ],
  };
  if (includeReceiptField) tournament.win_receipt = receipt;

  return {
    tournaments: [
      // A decoy FIRST, so "reads the right tournament" cannot pass by reading [0].
      {
        key: "biltmore-championship",
        name: "Biltmore Championship Asheville",
        is_major: false,
        commence_time: null,
        resolution_date: null,
        market_ids: [1],
        golfers: [],
        win_receipt: "deadbeefdeadbeef",
      },
      tournament,
    ],
    current_event: currentKey
      ? { key: currentKey, market_ids: [59863411] }
      : null,
  } as unknown as GolfResponse;
}

// =============================================================================
describe("golfCardWinReceipt — which card is on screen", () => {
  it("returns the receipt of the CURRENT tournament, not the first one", () => {
    expect(golfCardWinReceipt(golfPayload())).toBe(OLD_RECEIPT);
  });

  it("is null when the payload predates UX-P271 and carries no receipt", () => {
    // The 7,200s transition window: an unstamped payload must degrade to the
    // previous behaviour, never to a thrown error or a fabricated receipt.
    expect(golfCardWinReceipt(golfPayload({ includeReceiptField: false }))).toBeNull();
  });

  it("is null when the tournament publishes no golfers to bind to", () => {
    expect(golfCardWinReceipt(golfPayload({ receipt: null }))).toBeNull();
  });

  it("is null when there is no current event", () => {
    expect(golfCardWinReceipt(golfPayload({ currentKey: null }))).toBeNull();
  });

  it("is null for no payload at all", () => {
    expect(golfCardWinReceipt(null)).toBeNull();
  });

  it("CONTROL (green on the parent too): the value fingerprint still works", () => {
    // The receipt supplements the fingerprint, it does not replace it — a card
    // with no receipt must still drive a refetch when its numbers move.
    const before = golfCardWinFingerprint(golfPayload({ includeReceiptField: false }));
    expect(before).toContain("Matt Wallace=0.058");
  });
});

// =============================================================================
describe("shouldRebindGolfCard — converging when the table quoted another card", () => {
  const none: ReadonlySet<string> = new Set();

  it("rebinds when the endpoint bound to a DIFFERENT card than we sent", () => {
    // The whole point. The snapshot was evicted from the shared LRU, so the table
    // is quoting a card this page is not showing. Rendering it is the original
    // defect with a receipt attached.
    expect(shouldRebindGolfCard(OLD_RECEIPT, NEW_RECEIPT, none)).toBe(true);
  });

  it("does NOT rebind when the receipts match", () => {
    // The overwhelmingly common path. If this were true, every single page load
    // would issue a second uncached card fetch.
    expect(shouldRebindGolfCard(OLD_RECEIPT, OLD_RECEIPT, none)).toBe(false);
  });

  it("does NOT rebind when the same receipt has already been tried", () => {
    // The loop guard. An unresolvable snapshot stays unresolvable; retrying it
    // forever would hammer an uncached endpoint from every open golf tab.
    expect(shouldRebindGolfCard(OLD_RECEIPT, NEW_RECEIPT, new Set([OLD_RECEIPT]))).toBe(
      false
    );
  });

  it("still rebinds for a LATER, genuinely different mismatch", () => {
    // Converging replaces the card and therefore the receipt, so the attempted set
    // must not wedge the page against all future mismatches.
    expect(shouldRebindGolfCard(NEW_RECEIPT, "cafebabecafebabe", new Set([OLD_RECEIPT]))).toBe(
      true
    );
  });

  it("does NOT rebind when the response echoed no receipt", () => {
    // Non-golf progressions, and golf with no card available, echo null. Neither
    // is evidence of a mismatch.
    for (const echoed of [null, undefined, ""]) {
      expect(shouldRebindGolfCard(OLD_RECEIPT, echoed, none)).toBe(false);
    }
  });

  it("does NOT rebind when we had no receipt to send", () => {
    // A pre-UX-P271 card cannot be mismatched — there is nothing to compare — and
    // must not trigger an endless re-read.
    for (const sent of [null, undefined, ""]) {
      expect(shouldRebindGolfCard(sent, NEW_RECEIPT, none)).toBe(false);
    }
  });
});

// =============================================================================
describe("the receipt reaches the wire", () => {
  const originalFetch = global.fetch;

  function captureUrl() {
    const spy = jest.fn().mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({}),
    } as unknown as Response);
    global.fetch = spy;
    return spy;
  }

  afterAll(() => {
    global.fetch = originalFetch;
  });

  it("sends golf_card_receipt on the progression request", async () => {
    const spy = captureUrl();

    await fetchProgression(59863411, 40, OLD_RECEIPT);

    expect(spy.mock.calls[0][0]).toBe(
      `http://localhost:8000/api/futures/59863411/progression?top_n=40&golf_card_receipt=${OLD_RECEIPT}`
    );
  });

  it("CONTROL (green on the parent too): omits the param when there is no receipt", () => {
    // Every other caller of this endpoint — and any golf page holding a card from
    // before the deploy — must produce the byte-identical URL it produced before.
    const spy = captureUrl();

    return fetchProgression(59863411, 40).then(() => {
      expect(spy.mock.calls[0][0]).toBe(
        "http://localhost:8000/api/futures/59863411/progression?top_n=40"
      );
    });
  });

  it("omits the param for an empty receipt rather than sending a blank one", async () => {
    const spy = captureUrl();

    await fetchProgression(59863411, 40, "");

    expect(spy.mock.calls[0][0]).not.toContain("golf_card_receipt");
  });

  it("varies the card URL when re-reading past the HTTP cache", async () => {
    // A plain re-request can legally be answered from the very cache entry that
    // caused the mismatch: the response is `public, max-age=300,
    // stale-while-revalidate=60`, so it is storable and reusable. Varying the URL
    // varies the cache key, which is what actually reaches the origin.
    const spy = captureUrl();

    await fetchGolfData(NEW_RECEIPT);

    expect(spy.mock.calls[0][0]).toBe(
      `http://localhost:8000/api/golf?rebind=${NEW_RECEIPT}`
    );
  });

  it("CONTROL (green on the parent too): the ordinary card fetch is unchanged", async () => {
    // The 120s poll must keep hitting the cacheable URL. If it did not, this ship
    // would quietly convert a cached page into an origin request every two minutes.
    const spy = captureUrl();

    await fetchGolfData();

    expect(spy.mock.calls[0][0]).toBe("http://localhost:8000/api/golf");
  });
});
