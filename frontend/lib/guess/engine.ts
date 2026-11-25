// Scoring and standings for /guess. Pure functions, no React, no network.
//
// The one rule a player meets: a slider pays 20 points, less one for every
// point off. A count card loses `step` for each one off. A duo card is two
// sliders and pays the average of the two.
//
// Two house entries sit beside the players. THE COIN always says 50% (and half
// on a count); it is the opponent a person has when playing alone or first.
// TOGETHER is the group's average guess scored as if it were one more player,
// so a group can see whether it was smarter than its members.

import type { GamePack, PackCard, PlayerEntry } from "./types";

export const FULL_POINTS = 20;

/** A duo guess packs two percents into one number: `first * DUO_BASE + second`. */
export const DUO_BASE = 101;

export const COIN_NAME = "The Coin";
export const TOGETHER_NAME = "Together";

export function packDuo(first: number, second: number): number {
  return first * DUO_BASE + second;
}

export function duoParts(guess: number): [number, number] {
  return [Math.floor(guess / DUO_BASE), guess % DUO_BASE];
}

/** The largest value a guess on this card can take. */
export function maxGuess(card: PackCard): number {
  switch (card.kind) {
    case "chance":
      return 100;
    case "count":
      return card.max;
    case "duo":
      return packDuo(100, 100);
  }
}

export function isValidGuess(card: PackCard, guess: number | null): guess is number {
  if (guess === null || !Number.isInteger(guess) || guess < 0 || guess > maxGuess(card)) return false;
  return card.kind !== "duo" || duoParts(guess)[0] <= 100;
}

/**
 * How far a guess is from the answer, in the card's own units. On a duo card it
 * is the larger of the two misses, which is the one a line would be about.
 */
export function missFor(card: PackCard, guess: number): number {
  if (card.kind === "duo") {
    const [a, b] = duoParts(guess);
    return Math.max(Math.abs(a - card.parts[0].answer), Math.abs(b - card.parts[1].answer));
  }
  return Math.abs(guess - card.answer);
}

function sliderPoints(miss: number, step: number): number {
  return Math.max(0, FULL_POINTS - step * miss);
}

export function pointsFor(card: PackCard, guess: number | null): number {
  if (!isValidGuess(card, guess)) return 0;
  switch (card.kind) {
    case "chance":
      return sliderPoints(Math.abs(guess - card.answer), 1);
    case "count":
      return sliderPoints(Math.abs(guess - card.answer), card.step);
    case "duo": {
      const [a, b] = duoParts(guess);
      const first = sliderPoints(Math.abs(a - card.parts[0].answer), 1);
      const second = sliderPoints(Math.abs(b - card.parts[1].answer), 1);
      return Math.round((first + second) / 2);
    }
  }
}

/** The guess that earns full points. */
export function fullGuess(card: PackCard): number {
  return card.kind === "duo" ? packDuo(card.parts[0].answer, card.parts[1].answer) : card.answer;
}

/** Where every slider starts: the middle. It is also what the Coin says. */
export function startGuess(card: PackCard): number {
  if (card.kind === "chance") return 50;
  if (card.kind === "count") return Math.round(card.max / 2);
  return packDuo(50, 50);
}

/** A small seeded generator, so the win chances are the same on every phone. */
export function seeded(seed: string): () => number {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i += 1) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The Coin's guess: the middle of every slider. */
export function coinGuess(pack: GamePack, index: number): number {
  return startGuess(pack.cards[index]);
}

export function coinEntry(pack: GamePack): PlayerEntry {
  return {
    name: COIN_NAME,
    guesses: pack.cards.map((_, index) => coinGuess(pack, index)),
    ratings: pack.cards.map(() => 0),
    good: pack.cards.map(() => false),
    from: "house",
  };
}

function mean(values: number[]): number {
  return Math.round(values.reduce((sum, v) => sum + v, 0) / values.length);
}

/** The group's one guess on a card: the rounded average of every slider. */
export function togetherGuess(card: PackCard, guesses: number[]): number | null {
  const valid = guesses.filter((g) => isValidGuess(card, g));
  if (valid.length === 0) return null;
  if (card.kind === "duo") {
    const pairs = valid.map(duoParts);
    return packDuo(mean(pairs.map((p) => p[0])), mean(pairs.map((p) => p[1])));
  }
  return mean(valid);
}

export function togetherEntry(pack: GamePack, players: PlayerEntry[]): PlayerEntry {
  return {
    name: TOGETHER_NAME,
    guesses: pack.cards.map((card, index) =>
      togetherGuess(
        card,
        players.map((p) => p.guesses[index]).filter((g): g is number => g !== null),
      ),
    ),
    ratings: pack.cards.map(() => 0),
    good: pack.cards.map(() => false),
    from: "house",
  };
}

/** Points on each card, 0 where the card is not answered. */
export function pointsByCard(pack: GamePack, entry: PlayerEntry): number[] {
  return pack.cards.map((card, index) => pointsFor(card, entry.guesses[index] ?? null));
}

/** Total points over the first `upTo` cards. */
export function totalPoints(pack: GamePack, entry: PlayerEntry, upTo: number = pack.cards.length): number {
  return pointsByCard(pack, entry)
    .slice(0, upTo)
    .reduce((sum, p) => sum + p, 0);
}

export function answeredCount(entry: PlayerEntry): number {
  return entry.guesses.filter((g) => g !== null).length;
}

export interface Standing {
  entry: PlayerEntry;
  points: number;
  /** 1 for first. Players level on points share a place. */
  place: number;
}

/** Standings over the first `upTo` cards, highest first. Ties keep the order the players joined in. */
export function standings(pack: GamePack, entries: PlayerEntry[], upTo: number = pack.cards.length): Standing[] {
  const rows = entries.map((entry, order) => ({ entry, points: totalPoints(pack, entry, upTo), order }));
  rows.sort((a, b) => b.points - a.points || a.order - b.order);
  let place = 0;
  let lastPoints: number | null = null;
  return rows.map((row, i) => {
    if (row.points !== lastPoints) {
      place = i + 1;
      lastPoints = row.points;
    }
    return { entry: row.entry, points: row.points, place };
  });
}

export interface TopicWin {
  topic: string;
  /** Everyone level on the best average for the topic. Empty when nobody scored in it. */
  names: string[];
  average: number;
}

/** Who did best on each topic, by average points on that topic's cards. A loser overall can still win one. */
export function topicWins(pack: GamePack, players: PlayerEntry[]): TopicWin[] {
  return pack.topics.map((topic) => {
    const indices = pack.cards.map((card, i) => (card.topic === topic ? i : -1)).filter((i) => i >= 0);
    const averages = players.map((p) => {
      const played = indices.filter((i) => p.guesses[i] !== null);
      if (played.length === 0) return { name: p.name, average: -1 };
      const sum = played.reduce((s, i) => s + pointsFor(pack.cards[i], p.guesses[i]), 0);
      return { name: p.name, average: sum / played.length };
    });
    const best = Math.max(-1, ...averages.map((a) => a.average));
    return {
      topic,
      names: best > 0 ? averages.filter((a) => a.average === best).map((a) => a.name) : [],
      average: best,
    };
  });
}

export interface TogetherReport {
  together: number;
  coin: number;
  /** The best single player's total. */
  best: number;
  /** How many of the players the group's average beat. */
  beat: number;
  /** Leaving this player out raises the group's score the most; null when nobody drags it down. */
  without: { name: string; score: number } | null;
}

/**
 * The group against the Coin, and the one player whose guesses cost the group
 * the most. `without` is only named when there are at least three players and
 * leaving that player out adds at least five points.
 */
export function togetherReport(pack: GamePack, players: PlayerEntry[]): TogetherReport {
  const together = totalPoints(pack, togetherEntry(pack, players));
  const coin = totalPoints(pack, coinEntry(pack));
  const totals = players.map((p) => totalPoints(pack, p));
  let without: TogetherReport["without"] = null;
  if (players.length >= 3) {
    for (let i = 0; i < players.length; i += 1) {
      const rest = players.filter((_, j) => j !== i);
      const score = totalPoints(pack, togetherEntry(pack, rest));
      if (score - together >= 5 && (without === null || score > without.score)) {
        without = { name: players[i].name, score };
      }
    }
  }
  return {
    together,
    coin,
    best: totals.length ? Math.max(...totals) : 0,
    beat: totals.filter((t) => together > t).length,
    without,
  };
}

/** A person's name as the game keeps it: letters, digits, spaces and hyphens, at most 12 characters. */
export function cleanName(raw: string): string {
  return raw
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N} -]/gu, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 12)
    .trim();
}

/**
 * What a line calls each player: the first word of their name, unless two
 * players would then be called the same thing, in which case everyone keeps
 * their whole name. "Sam Lee said 29%" reads like a summons.
 */
export function spokenNames(names: string[]): Map<string, string> {
  const first = names.map((n) => n.split(" ")[0]);
  const clash = new Set(first.map((f) => f.toLowerCase())).size !== first.length;
  return new Map(names.map((n, i) => [n, clash ? n : first[i]]));
}

/** "Ann", "Ann and Bo", "Ann, Bo and Cy". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function emptyEntry(pack: GamePack, name: string, from: PlayerEntry["from"]): PlayerEntry {
  return {
    name,
    guesses: pack.cards.map(() => null),
    ratings: pack.cards.map(() => 0),
    good: pack.cards.map(() => false),
    from,
  };
}

/** A guess in words, as it is shown beside a player's name. */
export function guessLabel(card: PackCard, guess: number | null): string {
  if (!isValidGuess(card, guess)) return "";
  switch (card.kind) {
    case "chance":
      return `${guess}%`;
    case "count":
      return `${guess} of ${card.max}`;
    case "duo": {
      const [a, b] = duoParts(guess);
      return `${a}% and ${b}%`;
    }
  }
}

/** A short name for what the card asks the player to do. Kept short: it shares one line of a phone with the topic. */
export function kindLabel(card: PackCard): string {
  switch (card.flavor) {
    case "straight":
      return "Guess the chance";
    case "given":
      return "With a clue";
    case "rest":
      return "Not the favorites";
    case "count":
      return "How many?";
    case "duo":
      return "Two at once";
  }
}
