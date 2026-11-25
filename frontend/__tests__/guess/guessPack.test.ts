// /guess — THE FIRST SET IS HELD TO ITS RULES (425: C, 426: A).
//
// The set is generated from a public read, so no number in it is typed. This
// file is what stops a hand edit, or a later set, from breaking a promise the
// page makes to a player:
//   • the answer to every card follows from the numbers on the card, by rule;
//   • no answer is a toss-up (two options a point apart would be a coin flip
//     dressed as knowledge);
//   • every line of copy passes the site's copy bans, and a market is never
//     called a "question";
//   • most cards are of a kind only we can make.

import { ALL_COPY_BANS, findBannedCopy } from "@/lib/copyBans";
import { ORDER_PERMS, pointsFor, rightOrder } from "@/lib/guess/engine";
import { GUESS_PACK } from "@/lib/guess/pack";
import type { PackCard } from "@/lib/guess/types";

const cards = GUESS_PACK.cards;

function copyOf(card: PackCard): string[] {
  const out = [card.prompt, card.sub ?? "", card.short, card.context];
  if (card.kind === "chance" || card.kind === "count") out.push(card.roastHigh ?? "", card.roastLow ?? "");
  else out.push(card.roastWrong);
  if (card.kind === "pick" || card.kind === "ladder") card.options.forEach((o) => out.push(o.label, o.short));
  if (card.kind === "count" || card.kind === "order") card.items.forEach((o) => out.push(o.label, o.short));
  return out.filter(Boolean);
}

describe("/guess — the first set", () => {
  it("has two full rounds, unique ids, and a topic with at least three cards for every topic", () => {
    expect(cards.length).toBe(GUESS_PACK.perRound * 2);
    expect(new Set(cards.map((c) => c.id)).size).toBe(cards.length);
    for (const topic of GUESS_PACK.topics) {
      expect(cards.filter((c) => c.topic === topic).length).toBeGreaterThanOrEqual(3);
    }
    for (const card of cards) expect(GUESS_PACK.topics).toContain(card.topic);
  });

  it("is mostly cards of a kind only we can make, in at least five different shapes", () => {
    expect(cards.filter((c) => c.ours).length).toBeGreaterThan(cards.length / 2);
    const shapes = new Set(cards.map((c) => (c.kind === "pick" ? `pick:${c.flavor}` : c.kind)));
    expect(shapes.size).toBeGreaterThanOrEqual(5);
    // No two cards in a row ask for the same thing in the same way.
    for (let i = 1; i < cards.length; i += 1) {
      const a = cards[i - 1];
      const b = cards[i];
      const shape = (c: PackCard) => (c.kind === "pick" ? `pick:${c.flavor}` : c.kind);
      expect(`${i}:${shape(a)}→${shape(b)}`).not.toBe(`${i}:${shape(a)}→${shape(a)}`);
    }
  });

  it("every chance answer is a whole percent from 1 to 99", () => {
    for (const card of cards) {
      if (card.kind !== "chance") continue;
      expect(Number.isInteger(card.answer)).toBe(true);
      expect(card.answer).toBeGreaterThanOrEqual(1);
      expect(card.answer).toBeLessThanOrEqual(99);
    }
  });

  it("every pick answer follows from the numbers on the card, and never by a whisker", () => {
    for (const card of cards) {
      if (card.kind !== "pick") continue;
      const percents = card.options.map((o) => o.percent as number);
      percents.forEach((p) => expect(Number.isInteger(p)).toBe(true));
      const score = percents.map((p) => {
        if (card.flavor === "longshot") return -p;
        if (card.flavor === "match") return -Math.abs(p - (card.target as number));
        return p;
      });
      const ranked = score.map((s, i) => ({ s, i })).sort((a, b) => b.s - a.s);
      expect(card.answer).toBe(ranked[0].i);
      expect(ranked[0].s - ranked[1].s).toBeGreaterThanOrEqual(card.flavor === "match" ? 8 : 6);
      if (card.flavor === "pair") {
        expect(card.options.length).toBe(2);
        expect(card.partial).toEqual({});
      } else {
        expect(card.options.length).toBe(4);
        expect(card.partial).toEqual({ [String(ranked[1].i)]: 8 });
      }
      if (card.flavor === "match") expect(typeof card.target).toBe("number");
    }
  });

  it("every ladder rises, and its answer is the first rung at 50% or more, clear of the line", () => {
    for (const card of cards) {
      if (card.kind !== "ladder") continue;
      const rungs = card.options.filter((o) => o.percent !== null).map((o) => o.percent as number);
      expect([...rungs].sort((a, b) => a - b)).toEqual(rungs);
      rungs.forEach((p) => expect(p < 46 || p > 53).toBe(true));
      const first = rungs.findIndex((p) => p >= 50);
      expect(card.answer).toBe(first === -1 ? rungs.length : first);
      expect(card.options[card.options.length - 1].percent).toBeNull();
    }
  });

  it("every count answer is the number of items at 50% or more, with none on the line", () => {
    for (const card of cards) {
      if (card.kind !== "count") continue;
      const percents = card.items.map((o) => o.percent as number);
      percents.forEach((p) => expect(p < 46 || p > 53).toBe(true));
      expect(card.answer).toBe(percents.filter((p) => p >= 50).length);
      expect(card.max).toBe(card.items.length);
      expect(pointsFor(card, card.answer)).toBe(20);
      expect(pointsFor(card, card.answer + 1)).toBe(20 - card.step);
    }
  });

  it("every order card has three items at least six points apart, and exactly one ranking earns full points", () => {
    for (const card of cards) {
      if (card.kind !== "order") continue;
      expect(card.items.length).toBe(3);
      const sorted = card.items.map((o) => o.percent as number).sort((a, b) => b - a);
      expect(sorted[0] - sorted[1]).toBeGreaterThanOrEqual(6);
      expect(sorted[1] - sorted[2]).toBeGreaterThanOrEqual(6);
      const full = ORDER_PERMS.map((_, i) => pointsFor(card, i)).filter((p) => p === 20);
      expect(full.length).toBe(1);
      const right = rightOrder(card);
      const index = ORDER_PERMS.findIndex((perm) => perm.every((item, i) => item === right[i]));
      expect(pointsFor(card, index)).toBe(20);
    }
  });

  it("a slider card has a line ready for every direction a player can miss by ten", () => {
    for (const card of cards) {
      if (card.kind !== "chance") continue;
      if (card.answer + 10 <= 100) expect(card.roastHigh).toBeTruthy();
      if (card.answer - 10 >= 0) expect(card.roastLow).toBeTruthy();
    }
  });

  it("roast templates use only the tokens the game fills", () => {
    const known = new Set(["n", "g", "w", "pick", "pp", "s", "has", "is", "was"]);
    for (const card of cards) {
      const lines =
        card.kind === "chance" || card.kind === "count" ? [card.roastHigh ?? "", card.roastLow ?? ""] : [card.roastWrong];
      for (const line of lines) {
        for (const match of line.matchAll(/\{(\w+)\}/g)) expect(known.has(match[1])).toBe(true);
      }
    }
  });

  it("no line of copy trips the site's copy bans, calls a market a question, or names a supplier", () => {
    for (const card of cards) {
      for (const text of copyOf(card)) {
        expect({ card: card.id, text, hits: findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id) }).toEqual({
          card: card.id,
          text,
          hits: [],
        });
        if (text !== "Which is more likely?") expect(text).not.toMatch(/\bquestions?\b/i);
        expect(text).not.toMatch(/kalshi|polymarket/i);
        expect(text).not.toMatch(/\b(stale|blend|priced|curated|cohort|bids?)\b/i);
      }
    }
    expect(GUESS_PACK.asOf).toMatch(/PT$/);
  });
});
