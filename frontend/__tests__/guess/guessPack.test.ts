// /guess — THE SET IS HELD TO ITS RULES (425: C, 426: A, 429: A).
//
// The set is generated from a public read, so no number in it is typed. This
// file is what stops a hand edit, or a later set, from breaking a promise the
// page makes to a player:
//   • EVERY CARD IS A SLIDER. The first set on the live page mixed sliders with
//     pick-one and put-in-order cards, and the sliders were the fun;
//   • some cards are ours (they put markets side by side) and they are a
//     minority that can grow: at least four, never more than half, never two
//     in a row;
//   • an answer that is worked out (the rest of a field, a count) follows from
//     numbers on the card;
//   • every line is short, and a card carries a line for exactly the ways a
//     player can earn one (no line that can never show);
//   • every line of copy passes the site's copy bans, and a market is never
//     called a "question".

import { ALL_COPY_BANS, findBannedCopy } from "@/lib/copyBans";
import { duoParts, FULL_POINTS, fullGuess, kindLabel, maxGuess, pointsFor, startGuess } from "@/lib/guess/engine";
import { GUESS_PACK } from "@/lib/guess/pack";
import type { PackCard } from "@/lib/guess/types";

const cards = GUESS_PACK.cards;

/** The miss on a chance card at which a line is earned: the guess scored nothing. */
const EARNED_MISS = 20;
const LONGEST_LINE = 110;

function linesOf(card: PackCard): string[] {
  if (card.kind === "duo") return [card.roastFlip ?? "", card.roastFar].filter(Boolean);
  return [card.roastHigh ?? "", card.roastLow ?? ""].filter(Boolean);
}

function copyOf(card: PackCard): string[] {
  const out = [card.prompt, card.sub ?? "", card.short, card.context, kindLabel(card), ...linesOf(card)];
  if (card.kind === "chance") {
    if (card.given) out.push(card.given.text, card.given.label, card.given.answerLabel);
    (card.parts ?? []).forEach((p) => out.push(p.label));
  }
  if (card.kind === "count") out.push(card.noun);
  if (card.kind === "duo") card.parts.forEach((p) => out.push(p.label, p.short));
  return out.filter(Boolean);
}

describe("/guess — the set", () => {
  it("has two full rounds, unique ids, and at least three cards for every topic", () => {
    expect(cards.length).toBe(GUESS_PACK.perRound * 2);
    expect(new Set(cards.map((c) => c.id)).size).toBe(cards.length);
    for (const topic of GUESS_PACK.topics) {
      expect(cards.filter((c) => c.topic === topic).length).toBeGreaterThanOrEqual(3);
    }
    for (const card of cards) expect(GUESS_PACK.topics).toContain(card.topic);
    expect(GUESS_PACK.code).toMatch(/^[a-z0-9]{2}$/);
    expect(GUESS_PACK.asOf).toMatch(/PT$/);
  });

  it("every card is a slider that starts in the middle and can reach full points", () => {
    for (const card of cards) {
      expect(["chance", "count", "duo"]).toContain(card.kind);
      expect(pointsFor(card, fullGuess(card))).toBe(FULL_POINTS);
      expect(startGuess(card)).toBeLessThanOrEqual(maxGuess(card));
      // The middle is never the answer: the Coin cannot score full points by sitting still.
      expect({ card: card.id, coin: pointsFor(card, startGuess(card)) < FULL_POINTS }).toEqual({ card: card.id, coin: true });
    }
  });

  it("ours are a minority that can grow: at least four, at most half, never two in a row", () => {
    const ours = cards.filter((c) => c.ours);
    expect(ours.length).toBeGreaterThanOrEqual(4);
    expect(ours.length).toBeLessThanOrEqual(cards.length / 2);
    for (const card of cards) expect(card.ours).toBe(card.flavor !== "straight");
    for (let i = 1; i < cards.length; i += 1) {
      expect({ at: i, both: cards[i - 1].ours && cards[i].ours }).toEqual({ at: i, both: false });
    }
    // The four we are trying, one of each, so the marks at the end of a round compare kinds, not subjects.
    expect(ours.map((c) => c.flavor).sort()).toEqual(["count", "duo", "given", "rest"]);
  });

  it("a card's flavor matches what is on it", () => {
    for (const card of cards) {
      if (card.kind === "count") expect(card.flavor).toBe("count");
      if (card.kind === "duo") expect(card.flavor).toBe("duo");
      if (card.kind !== "chance") continue;
      expect(["straight", "given", "rest"]).toContain(card.flavor);
      expect(Boolean(card.given)).toBe(card.flavor === "given");
      expect(Boolean(card.parts)).toBe(card.flavor === "rest");
      expect(card.extras.length).toBe(2);
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

  it("a 'given' card shows a number that is a real hint and not the answer", () => {
    for (const card of cards) {
      if (card.kind !== "chance" || !card.given) continue;
      expect(Number.isInteger(card.given.percent)).toBe(true);
      expect(card.given.text).toContain(`${card.given.percent}%`);
      expect(Math.abs(card.given.percent - card.answer)).toBeGreaterThanOrEqual(5);
    }
  });

  it("a 'none of the favorites' card is the rest of a field that adds to exactly 100", () => {
    for (const card of cards) {
      if (card.kind !== "chance" || !card.parts) continue;
      expect(card.parts.length).toBe(3);
      const named = card.parts.reduce((sum, p) => sum + p.percent, 0);
      expect(card.answer).toBe(100 - named);
      // Named in order, strongest first.
      expect([...card.parts].sort((a, b) => b.percent - a.percent)).toEqual(card.parts);
    }
  });

  it("a count card pays 20 for the count and loses its step for each one off", () => {
    for (const card of cards) {
      if (card.kind !== "count") continue;
      expect(Number.isInteger(card.answer)).toBe(true);
      expect(card.answer).toBeGreaterThan(0);
      expect(card.answer).toBeLessThan(card.max);
      expect(pointsFor(card, card.answer + 1)).toBe(FULL_POINTS - card.step);
      expect(pointsFor(card, card.answer - 1)).toBe(FULL_POINTS - card.step);
      expect(pointsFor(card, card.answer > card.max / 2 ? 0 : card.max)).toBe(0);
    }
  });

  it("a two-number card has two numbers far enough apart to be worth telling apart", () => {
    for (const card of cards) {
      if (card.kind !== "duo") continue;
      const [a, b] = card.parts.map((p) => p.answer);
      expect(Math.abs(a - b)).toBeGreaterThanOrEqual(10);
      expect(duoParts(fullGuess(card))).toEqual([a, b]);
      expect(card.roastFar).toContain("{part}");
    }
  });

  it("a card carries a line for exactly the directions a player can earn one in, and every line is short", () => {
    for (const card of cards) {
      if (card.kind === "chance") {
        expect({ card: card.id, high: Boolean(card.roastHigh) }).toEqual({ card: card.id, high: card.answer + EARNED_MISS <= 100 });
        expect({ card: card.id, low: Boolean(card.roastLow) }).toEqual({ card: card.id, low: card.answer - EARNED_MISS >= 0 });
        expect(pointsFor(card, card.answer >= 50 ? card.answer - EARNED_MISS : card.answer + EARNED_MISS)).toBe(0);
      }
      if (card.kind === "count") {
        expect(Boolean(card.roastHigh)).toBe(true);
        expect(Boolean(card.roastLow)).toBe(true);
      }
      for (const line of linesOf(card)) {
        expect({ card: card.id, line, short: line.length <= LONGEST_LINE }).toEqual({ card: card.id, line, short: true });
      }
    }
  });

  it("roast templates use only the tokens the game fills", () => {
    const known = new Set(["n", "g", "w", "d", "part", "s", "has", "is", "was"]);
    for (const card of cards) {
      for (const line of linesOf(card)) {
        for (const match of line.matchAll(/\{(\w+)\}/g)) expect({ line, word: match[1], known: known.has(match[1]) }).toEqual({ line, word: match[1], known: true });
        if (card.kind !== "duo") expect(line).not.toContain("{part}");
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
        expect(text).not.toMatch(/\bquestions?\b/i);
        expect(text).not.toMatch(/kalshi|polymarket/i);
        expect(text).not.toMatch(/\b(stale|blend|priced?|curated|cohort|bids?|odds|bets?)\b/i);
      }
    }
  });
});
