// L2-195 — the prefix-stable per-round deck (C39 P1). Proves that appending a page
// (even one carrying a newly-preferred/liked card) never reorders the existing
// prefix, so the card/question under the child's current index cannot change.

import { mergeStableDeck } from "@/lib/play/stableDeck";
import type { FeedItem } from "@/lib/types";

// A futures card whose name carries a token so affinity ordering can act on it.
function card(id: number, name: string): FeedItem {
  return {
    type: "futures",
    score: 1,
    reason: "",
    headline: null,
    data: {
      id,
      name,
      top_outcomes: [{ name, probability: 0.6 }],
    } as unknown as FeedItem["data"],
  };
}

function keys(items: FeedItem[]): number[] {
  return items.map((it) => (it.data as { id: number }).id);
}

describe("mergeStableDeck", () => {
  it("first round applies full affinity ordering (delight up front)", () => {
    const pool = [card(1, "Weather storm"), card(2, "Baseball MLB"), card(3, "Random")];
    const deck = mergeStableDeck([], pool, ["baseball"]);
    // The liked (baseball) card floats to the front on the FIRST batch.
    expect(keys(deck)[0]).toBe(2);
    expect(new Set(keys(deck))).toEqual(new Set([1, 2, 3]));
  });

  it("appending a liked card NEVER reorders the already-shown prefix", () => {
    const round1 = mergeStableDeck([], [card(1, "Random one"), card(2, "Random two")], ["baseball"]);
    const prefix = keys(round1); // [1, 2] — no baseball yet, original order
    expect(prefix).toEqual([1, 2]);

    // Page 2 arrives with a newly-liked baseball card. Old behavior floated it to
    // the front of the whole pool; stable merge appends it AFTER the frozen prefix.
    const pool2 = [card(1, "Random one"), card(2, "Random two"), card(3, "Baseball MLB"), card(4, "Random four")];
    const round2 = mergeStableDeck(round1, pool2, ["baseball"]);
    expect(keys(round2).slice(0, 2)).toEqual([1, 2]); // prefix unchanged
    expect(keys(round2)).toEqual([1, 2, 3, 4]); // new batch appended, affinity within it
  });

  it("affinity orders WITHIN the appended batch only", () => {
    const round1 = mergeStableDeck([], [card(1, "Random")], ["baseball"]);
    const pool2 = [card(1, "Random"), card(2, "Random"), card(3, "Baseball MLB")];
    const round2 = mergeStableDeck(round1, pool2, ["baseball"]);
    // Within the new batch [2,3], the liked (3) floats ahead of 2.
    expect(keys(round2)).toEqual([1, 3, 2]);
  });

  it("re-serving the same pool returns the SAME reference (idempotent, no render loop)", () => {
    const pool = [card(1, "a"), card(2, "b")];
    const deck = mergeStableDeck([], pool, []);
    const again = mergeStableDeck(deck, pool, []);
    expect(again).toBe(deck);
  });

  it("dedups cards already in the prefix", () => {
    const round1 = mergeStableDeck([], [card(1, "a"), card(2, "b")], []);
    const round2 = mergeStableDeck(round1, [card(1, "a"), card(2, "b"), card(3, "c")], []);
    expect(keys(round2)).toEqual([1, 2, 3]);
  });

  it("skips malformed (identity-less) items rather than admitting duplicates", () => {
    const malformed = { type: "futures", score: 1, reason: "", headline: null, data: {} } as unknown as FeedItem;
    const deck = mergeStableDeck([], [card(1, "a"), malformed, malformed], []);
    expect(keys(deck)).toEqual([1]);
  });
});
