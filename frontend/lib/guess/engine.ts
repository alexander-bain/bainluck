// Scoring and standings for /guess. Pure functions, no React, no network.
//
// The rules a player meets:
//   • a slider card pays 20 points less one for every point off (a count card
//     loses `step` for each one off);
//   • a pick or ladder card pays 20 for the answer, a few for the next best;
//   • an order card pays by how many of the three pairs are the right way round.
//
// Two house entries sit beside the players. THE COIN always says 50% and picks
// at random; it is the opponent a person has when playing alone or first.
// TOGETHER is the group's average guess scored as if it were one more player,
// so a group can see whether it was smarter than its members.

import type { GamePack, PackCard, PlayerEntry } from "./types";

export const FULL_POINTS = 20;

/** Every way to rank three things, surest first. A guess on an order card is an index into this. */
export const ORDER_PERMS: readonly (readonly [number, number, number])[] = [
  [0, 1, 2],
  [0, 2, 1],
  [1, 0, 2],
  [1, 2, 0],
  [2, 0, 1],
  [2, 1, 0],
];

const ORDER_POINTS = [0, 5, 12, FULL_POINTS] as const;

export const COIN_NAME = "The Coin";
export const TOGETHER_NAME = "Together";

/** Item indices of an order card, surest first. */
export function rightOrder(card: PackCard): number[] {
  if (card.kind !== "order") return [];
  return card.items
    .map((item, index) => ({ index, percent: item.percent ?? 0 }))
    .sort((a, b) => b.percent - a.percent)
    .map((x) => x.index);
}

/** How many of the three pairs a ranking has the right way round. */
export function pairsRight(card: PackCard, guess: number): number {
  if (card.kind !== "order") return 0;
  const perm = ORDER_PERMS[guess];
  if (!perm) return 0;
  const place = new Map<number, number>();
  perm.forEach((item, position) => place.set(item, position));
  let right = 0;
  for (let a = 0; a < card.items.length; a += 1) {
    for (let b = a + 1; b < card.items.length; b += 1) {
      const pa = card.items[a].percent ?? 0;
      const pb = card.items[b].percent ?? 0;
      const aFirst = (place.get(a) ?? 0) < (place.get(b) ?? 0);
      if (pa > pb === aFirst) right += 1;
    }
  }
  return right;
}

/** How far a slider guess is from the answer. `null` for cards without a slider. */
export function missFor(card: PackCard, guess: number): number | null {
  if (card.kind === "chance" || card.kind === "count") return Math.abs(guess - card.answer);
  return null;
}

export function pointsFor(card: PackCard, guess: number | null): number {
  if (guess === null || !Number.isFinite(guess)) return 0;
  switch (card.kind) {
    case "chance":
      return Math.max(0, FULL_POINTS - Math.abs(guess - card.answer));
    case "count":
      return Math.max(0, FULL_POINTS - card.step * Math.abs(guess - card.answer));
    case "pick":
    case "ladder":
      if (guess === card.answer) return FULL_POINTS;
      return card.partial[String(guess)] ?? 0;
    case "order":
      return ORDER_POINTS[pairsRight(card, guess)] ?? 0;
  }
}

/** The largest value a guess on this card can take. */
export function maxGuess(card: PackCard): number {
  switch (card.kind) {
    case "chance":
      return 100;
    case "count":
      return card.max;
    case "pick":
    case "ladder":
      return card.options.length - 1;
    case "order":
      return ORDER_PERMS.length - 1;
  }
}

export function isValidGuess(card: PackCard, guess: number | null): guess is number {
  return guess !== null && Number.isInteger(guess) && guess >= 0 && guess <= maxGuess(card);
}

/** A small seeded generator, so the Coin and the win chances are the same on every phone. */
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

/** The Coin's guess: 50% on a chance card, half on a count card, a seeded random pick otherwise. */
export function coinGuess(pack: GamePack, index: number): number {
  const card = pack.cards[index];
  if (card.kind === "chance") return 50;
  if (card.kind === "count") return Math.round(card.max / 2);
  const roll = seeded(`${pack.code}:coin:${card.id}`)();
  return Math.min(maxGuess(card), Math.floor(roll * (maxGuess(card) + 1)));
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

/**
 * The group's one guess on a card: the rounded average on a slider, the most
 * picked option on a pick or ladder (a tie goes to whoever in the tie guessed
 * first), and on an order card the ranking by average position.
 */
export function togetherGuess(card: PackCard, guesses: number[]): number | null {
  const valid = guesses.filter((g) => isValidGuess(card, g));
  if (valid.length === 0) return null;
  if (card.kind === "chance" || card.kind === "count") {
    return Math.round(valid.reduce((sum, g) => sum + g, 0) / valid.length);
  }
  if (card.kind === "pick" || card.kind === "ladder") {
    const tally = new Map<number, number>();
    valid.forEach((g) => tally.set(g, (tally.get(g) ?? 0) + 1));
    let best = valid[0];
    for (const g of valid) {
      if ((tally.get(g) ?? 0) > (tally.get(best) ?? 0)) best = g;
    }
    return best;
  }
  const positionSum = [0, 0, 0];
  valid.forEach((g) => {
    ORDER_PERMS[g].forEach((item, position) => {
      positionSum[item] += position;
    });
  });
  const ranked = [0, 1, 2].sort((a, b) => positionSum[a] - positionSum[b] || a - b);
  return ORDER_PERMS.findIndex((perm) => perm.every((item, i) => item === ranked[i]));
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
  if (guess === null || !isValidGuess(card, guess)) return "";
  switch (card.kind) {
    case "chance":
      return `${guess}%`;
    case "count":
      return `${guess} of ${card.max}`;
    case "pick":
    case "ladder":
      return card.options[guess].short;
    case "order":
      return ORDER_PERMS[guess].map((item) => card.items[item].short).join(", then ");
  }
}

/** The guess that earns full points. */
export function fullGuess(card: PackCard): number {
  if (card.kind === "order") {
    const right = rightOrder(card);
    return ORDER_PERMS.findIndex((perm) => perm.every((item, i) => item === right[i]));
  }
  return card.answer;
}

/** A short name for what the card asks the player to do. */
export function kindLabel(card: PackCard): string {
  switch (card.kind) {
    case "chance":
      return "Guess the chance";
    case "count":
      return "How many?";
    case "ladder":
      return "By what year?";
    case "order":
      return "Put them in order";
    case "pick":
      if (card.flavor === "pair") return "This or that";
      if (card.flavor === "field") return "Name the favorite";
      if (card.flavor === "longshot") return "Find the long shot";
      return "Find the match";
  }
}
