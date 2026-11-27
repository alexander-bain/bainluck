// /guess — THE SET IS HELD TO ITS RULES (425: C, 426: A, 429: A, 430: A).
//
// The set is generated from a public read, so no number in it is typed. This
// file is what stops a hand edit, or a later set, from breaking a promise the
// page makes to a player:
//   • THREE STEPS OF FIVE, EASIEST FIRST: taps with two things to choose from,
//     then taps with four, then sliders;
//   • a tap card is never a coin toss: an above-or-below card is well away from
//     50, the two halves of a which-is-more-likely card are well apart, a
//     favorite leads, and the four numbers on a pick-the-number card are far
//     enough apart to tell;
//   • the right answer is not always in the same place;
//   • the cards of ours (they put markets side by side) are a minority and
//     never two in a row;
//   • every slider line is short, and a slider carries a line for exactly the
//     ways a player can earn one (no line that can never show);
//   • every line of copy passes the site's copy bans, and a market is never
//     called a "question".

import { ALL_COPY_BANS, findBannedCopy } from "@/lib/copyBans";
import {
  coinGuess,
  FULL_POINTS,
  fullGuess,
  fullPoints,
  isTap,
  kindLabel,
  maxGuess,
  optionCount,
  pointsFor,
  startGuess,
  stepIsTaps,
  stepMax,
  stepRange,
} from "@/lib/guess/engine";
import { GUESS_PACK } from "@/lib/guess/pack";
import type { PackCard } from "@/lib/guess/types";

const cards = GUESS_PACK.cards;

/** The miss on a chance card at which a line is earned: the guess scored nothing. */
const EARNED_MISS = 20;
const LONGEST_LINE = 110;
const SIDE_GAP = 8;
const VERSUS_GAP = 8;
const LEAD_GAP = 5;
const OPTION_GAP = 10;

function linesOf(card: PackCard): string[] {
  if (card.kind === "chance" || card.kind === "count") return [card.roastHigh ?? "", card.roastLow ?? ""].filter(Boolean);
  if (card.kind === "duo") return [card.roastFlip ?? "", card.roastFar].filter(Boolean);
  return [];
}

function copyOf(card: PackCard): string[] {
  const out = [card.prompt, card.sub ?? "", card.short, card.context, kindLabel(card), ...linesOf(card)];
  if (card.kind === "versus" || card.kind === "leader") card.options.forEach((o) => out.push(o.label, o.short));
  if (card.kind === "chance") {
    if (card.given) out.push(card.given.text, card.given.label, card.given.answerLabel);
    (card.parts ?? []).forEach((p) => out.push(p.label));
  }
  if (card.kind === "count") out.push(card.noun);
  if (card.kind === "duo") card.parts.forEach((p) => out.push(p.label, p.short));
  return out.filter(Boolean);
}

/** Every percent a card prints when its answer is shown. */
function percentsOf(card: PackCard): number[] {
  if (card.kind === "side" || card.kind === "chance") return [card.answer];
  if (card.kind === "four") return [...card.options];
  if (card.kind === "versus" || card.kind === "leader") return card.options.map((o) => o.percent);
  return [];
}

describe("/guess — the set", () => {
  it("has three full steps of five, unique ids, and at least three cards for every topic", () => {
    expect(GUESS_PACK.steps.length).toBe(3);
    expect(GUESS_PACK.perRound).toBe(5);
    expect(cards.length).toBe(GUESS_PACK.perRound * GUESS_PACK.steps.length);
    expect(new Set(cards.map((c) => c.id)).size).toBe(cards.length);
    expect(GUESS_PACK.topics.length).toBe(3);
    for (const topic of GUESS_PACK.topics) {
      expect(cards.filter((c) => c.topic === topic).length).toBeGreaterThanOrEqual(3);
    }
    for (const card of cards) expect(GUESS_PACK.topics).toContain(card.topic);
    expect(GUESS_PACK.code).toMatch(/^[a-z0-9]{2}$/);
    expect(GUESS_PACK.asOf).toMatch(/PT$/);
    for (const step of GUESS_PACK.steps) {
      expect(step.name.length).toBeGreaterThan(0);
      expect(step.how.length).toBeGreaterThan(0);
    }
    expect(new Set(GUESS_PACK.steps.map((s) => s.name)).size).toBe(3);
  });

  it("goes from easy to hard: two to choose from, then four, then sliders", () => {
    const kindsIn = (step: number) => {
      const [from, to] = stepRange(GUESS_PACK, step);
      return new Set(cards.slice(from, to).map((c) => c.kind));
    };
    expect([...kindsIn(0)].sort()).toEqual(["side", "versus"]);
    expect([...kindsIn(1)].sort()).toEqual(["four", "leader"]);
    expect([...kindsIn(2)]).toEqual(["chance"]);
    expect(stepIsTaps(GUESS_PACK, 0)).toBe(true);
    expect(stepIsTaps(GUESS_PACK, 1)).toBe(true);
    expect(stepIsTaps(GUESS_PACK, 2)).toBe(false);
    cards.slice(0, 5).forEach((c) => expect(isTap(c) && optionCount(c)).toBe(2));
    cards.slice(5, 10).forEach((c) => expect(isTap(c) && optionCount(c)).toBe(4));
  });

  it("every card can be answered for full points, and starts with nothing tapped or in the middle", () => {
    for (const card of cards) {
      expect(pointsFor(card, fullGuess(card))).toBe(fullPoints(card));
      expect(fullGuess(card)).toBeLessThanOrEqual(maxGuess(card));
      if (isTap(card)) {
        expect(startGuess(card)).toBeNull();
      } else {
        // The middle is never the answer: the Coin cannot score full points by sitting still.
        expect({ card: card.id, coin: pointsFor(card, startGuess(card)) < FULL_POINTS }).toEqual({ card: card.id, coin: true });
      }
    }
  });

  it("the harder the card, the more it is worth: 10, 15, 20 a card, so the steps are worth 50, 75 and 100", () => {
    expect(cards.map(fullPoints)).toEqual([10, 10, 10, 10, 10, 15, 15, 15, 15, 15, 20, 20, 20, 20, 20]);
    expect([0, 1, 2].map((step) => stepMax(GUESS_PACK, step))).toEqual([50, 75, 100]);
  });

  it("a card's flavor matches what is on it, and only the side-by-side cards are ours", () => {
    for (const card of cards) {
      if (isTap(card)) expect(card.flavor).toBe(card.kind);
      if (card.kind === "chance") {
        expect(card.flavor).toBe("straight");
        expect(card.extras.length).toBe(2);
      }
      if (card.kind === "side" || card.kind === "four") expect(card.extras.length).toBe(2);
      expect({ card: card.id, ours: card.ours }).toEqual({ card: card.id, ours: card.kind === "versus" });
    }
    const ours = cards.filter((c) => c.ours);
    expect(ours.length).toBeGreaterThanOrEqual(1);
    expect(ours.length).toBeLessThanOrEqual(cards.length / 2);
    for (let i = 1; i < cards.length; i += 1) {
      expect({ at: i, both: cards[i - 1].ours && cards[i].ours }).toEqual({ at: i, both: false });
    }
  });

  it("every percent the set prints is a whole number from 1 to 99", () => {
    for (const card of cards) {
      for (const percent of percentsOf(card)) {
        expect({ card: card.id, percent, ok: Number.isInteger(percent) && percent >= 1 && percent <= 99 }).toEqual({ card: card.id, percent, ok: true });
      }
    }
  });

  it("an above-or-below card is never close to 50, and the set has one of each answer", () => {
    const sides = cards.filter((c) => c.kind === "side");
    expect(sides.length).toBeGreaterThanOrEqual(2);
    for (const card of sides) {
      if (card.kind !== "side") continue;
      expect({ card: card.id, clear: Math.abs(card.answer - 50) >= SIDE_GAP }).toEqual({ card: card.id, clear: true });
    }
    expect(new Set(sides.map(fullGuess)).size).toBe(2);
  });

  it("a which-is-more-likely card has two halves well apart", () => {
    for (const card of cards) {
      if (card.kind !== "versus") continue;
      expect(card.options.length).toBe(2);
      const [a, b] = card.options.map((o) => o.percent);
      expect({ card: card.id, apart: Math.abs(a - b) >= VERSUS_GAP }).toEqual({ card: card.id, apart: true });
      expect(card.options[fullGuess(card)].percent).toBe(Math.max(a, b));
    }
  });

  it("a pick-the-number card offers four numbers, smallest first, far enough apart, and one is the world's", () => {
    for (const card of cards) {
      if (card.kind !== "four") continue;
      expect(card.options.length).toBe(4);
      expect([...card.options].sort((a, b) => a - b)).toEqual(card.options);
      for (let i = 1; i < 4; i += 1) {
        expect({ card: card.id, gap: card.options[i] - card.options[i - 1] >= OPTION_GAP }).toEqual({ card: card.id, gap: true });
      }
      expect(card.options.filter((o) => o === card.answer).length).toBe(1);
      expect(card.options[fullGuess(card)]).toBe(card.answer);
    }
  });

  it("a pick-the-favorite card has four names and a favorite that leads", () => {
    for (const card of cards) {
      if (card.kind !== "leader") continue;
      expect(card.options.length).toBe(4);
      const sorted = card.options.map((o) => o.percent).sort((a, b) => b - a);
      expect({ card: card.id, leads: sorted[0] - sorted[1] >= LEAD_GAP }).toEqual({ card: card.id, leads: true });
      expect(card.options[fullGuess(card)].percent).toBe(sorted[0]);
      expect(new Set(card.options.map((o) => o.label)).size).toBe(4);
      // A field with one winner cannot add to more than 100.
      if (!card.independent) expect(sorted.reduce((s, p) => s + p, 0)).toBeLessThanOrEqual(100);
    }
  });

  it("the right answer moves around, so 'always the second one' is not a way to win", () => {
    const places = (kind: PackCard["kind"]) => cards.filter((c) => c.kind === kind).map(fullGuess);
    expect(new Set(places("four")).size).toBe(places("four").length);
    expect(new Set(places("leader")).size).toBe(places("leader").length);
    expect(new Set(places("versus")).size).toBe(places("versus").length);
    // And the Coin, which taps without looking, is not handed a perfect step.
    for (let step = 0; step < 2; step += 1) {
      const [from, to] = stepRange(GUESS_PACK, step);
      let right = 0;
      for (let i = from; i < to; i += 1) if (coinGuess(GUESS_PACK, i) === fullGuess(cards[i])) right += 1;
      expect({ step, perfect: right === to - from }).toEqual({ step, perfect: false });
    }
  });

  it("the Coin is an ordinary coin: its taps are real options, and it lands where a coin should", () => {
    const taps = GUESS_PACK.coinTaps ?? [];
    expect(taps.length).toBe(cards.length);
    cards.forEach((card, i) => {
      if (isTap(card)) {
        expect({ card: card.id, tap: taps[i], ok: Number.isInteger(taps[i]) && (taps[i] as number) >= 0 && (taps[i] as number) < optionCount(card) }).toEqual({
          card: card.id,
          tap: taps[i],
          ok: true,
        });
        expect(coinGuess(GUESS_PACK, i)).toBe(taps[i]);
      } else {
        expect(taps[i]).toBeNull();
        expect(coinGuess(GUESS_PACK, i)).toBe(startGuess(card));
      }
    });
    const rightIn = (step: number) => {
      const [from, to] = stepRange(GUESS_PACK, step);
      let right = 0;
      for (let i = from; i < to; i += 1) if (coinGuess(GUESS_PACK, i) === fullGuess(cards[i])) right += 1;
      return right;
    };
    // About half of five two-way taps, about a quarter of five four-way ones. Never a lucky coin, never a hopeless one.
    expect([2, 3]).toContain(rightIn(0));
    expect(rightIn(1)).toBe(1);
  });

  it("every slider answer is a whole percent from 1 to 99 and off the middle", () => {
    for (const card of cards) {
      if (card.kind !== "chance") continue;
      expect(Number.isInteger(card.answer)).toBe(true);
      expect(card.answer).toBeGreaterThanOrEqual(1);
      expect(card.answer).toBeLessThanOrEqual(99);
      expect(Math.abs(card.answer - 50)).toBeGreaterThanOrEqual(5);
    }
  });

  it("a slider carries a line for exactly the directions a player can earn one in, a tap card carries none, and every line is short", () => {
    for (const card of cards) {
      if (card.kind === "chance") {
        expect({ card: card.id, high: Boolean(card.roastHigh) }).toEqual({ card: card.id, high: card.answer + EARNED_MISS <= 100 });
        expect({ card: card.id, low: Boolean(card.roastLow) }).toEqual({ card: card.id, low: card.answer - EARNED_MISS >= 0 });
        expect(pointsFor(card, card.answer >= 50 ? card.answer - EARNED_MISS : card.answer + EARNED_MISS)).toBe(0);
      }
      if (isTap(card)) expect(linesOf(card)).toEqual([]);
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
    const texts = [...GUESS_PACK.steps.flatMap((s) => [s.name, s.how])];
    for (const text of texts) {
      expect({ text, hits: findBannedCopy(text, ALL_COPY_BANS).map((h) => h.ban.id) }).toEqual({ text, hits: [] });
    }
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
