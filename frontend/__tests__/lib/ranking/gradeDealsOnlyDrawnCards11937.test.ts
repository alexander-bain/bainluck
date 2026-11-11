/**
 * #11937: /grade never deals a card it can't draw, and says how many it left out.
 */
import { drawnOnly, leftOutLine, type GradeDeck, type GradeDeckItem } from "@/lib/ranking/gradeSession";

const item = (position: number, drawn: boolean): GradeDeckItem => ({
  position,
  item_key: `futures:${position}`,
  title: `Market ${position}`,
  probability: 0.4,
  card: drawn ? ({ type: "futures", data: {} } as never) : null,
});

const deck = (items: GradeDeckItem[], left_out_no_drawing?: number): GradeDeck => ({
  switch_on: true,
  slate_id: "s",
  surface: "discover",
  captured_at: null,
  ranker_version: "v",
  mode: "spread",
  items,
  left_out_no_drawing,
});

describe("drawnOnly", () => {
  it("keeps only cards with a stored drawing, in their order and positions", () => {
    const out = drawnOnly(deck([item(1, true), item(2, false), item(3, true), item(40, false)], 0));
    expect(out.items.map((i) => i.position)).toEqual([1, 3]);
    expect(out.left_out_no_drawing).toBe(2);
  });
  it("adds to the count the server already left out", () => {
    expect(drawnOnly(deck([item(1, true), item(2, false)], 20)).left_out_no_drawing).toBe(21);
  });
  it("leaves a fully drawn deck alone", () => {
    const out = drawnOnly(deck([item(1, true), item(2, true)]));
    expect(out.items).toHaveLength(2);
    expect(out.left_out_no_drawing).toBe(0);
  });
});

describe("leftOutLine", () => {
  it("names how many cards were left out and why", () => {
    expect(leftOutLine(deck([], 12))).toBe("12 cards left out: no stored drawing");
    expect(leftOutLine(deck([], 1))).toBe("1 card left out: no stored drawing");
  });
  it("says nothing when none were", () => {
    expect(leftOutLine(deck([], 0))).toBe("");
    expect(leftOutLine(deck([]))).toBe("");
  });
});
