// Scoring and standings for /guess. Pure functions, no React, no network.
//
// The rules a player meets:
//   • a tap with two things to choose from pays 10 points when it is right, a
//     tap with four pays 15, and a wrong tap pays nothing;
//   • a slider pays 20 points, less one for every point off. A count card loses
//     `step` for each one off. A duo card is two sliders and pays the average.
//
// THE HARDER THE CARD, THE MORE IT IS WORTH: 10, 15, 20. With every card at 20,
// five two-way taps swung the total further than five sliders did, so a lucky
// Easy step all but decided the game before the part that takes judgment. At
// 10, 15 and 20 the three steps of five are worth 50, 75 and 100, and a step
// can still be read on its own ("4 of 5 on Easy").
//
// Two house entries sit beside the players. THE COIN flips for every tap and
// leaves every slider in the middle; it is the opponent a person has when
// playing alone or first. TOGETHER is the group's one answer on each card (the
// most common tap, the average slider) scored as if it were one more player,
// so a group can see whether it was smarter than its members.

import type { GamePack, PackCard, PlayerEntry, TapCard } from "./types";

/** What a slider pays for dead on. */
export const FULL_POINTS = 20;
/** What a right tap pays: less than a slider, and less still when there are only two things to tap. */
export const TWO_WAY_POINTS = 10;
export const FOUR_WAY_POINTS = 15;

/** A duo guess packs two percents into one number: `first * DUO_BASE + second`. */
export const DUO_BASE = 101;

export const COIN_NAME = "The Coin";
export const TOGETHER_NAME = "Together";

/** A card counts for at most this many seconds of a player's time, so a phone left on the table is not a slow player. */
export const MAX_CARD_SECONDS = 120;

export function packDuo(first: number, second: number): number {
  return first * DUO_BASE + second;
}

export function duoParts(guess: number): [number, number] {
  return [Math.floor(guess / DUO_BASE), guess % DUO_BASE];
}

/** True for a card answered with one tap. */
export function isTap(card: PackCard): card is TapCard {
  return card.kind === "side" || card.kind === "versus" || card.kind === "four" || card.kind === "leader";
}

/** How many things there are to tap on a tap card. */
export function optionCount(card: TapCard): number {
  return card.kind === "side" ? 2 : card.options.length;
}

/** The most points this card can pay. */
export function fullPoints(card: PackCard): number {
  if (!isTap(card)) return FULL_POINTS;
  return optionCount(card) <= 2 ? TWO_WAY_POINTS : FOUR_WAY_POINTS;
}

/** The largest value a guess on this card can take. */
export function maxGuess(card: PackCard): number {
  if (isTap(card)) return optionCount(card) - 1;
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

/** The guess that earns full points. On a tap card it is the place of the right option. */
export function fullGuess(card: PackCard): number {
  switch (card.kind) {
    case "side":
      return card.answer > 50 ? 1 : 0;
    case "versus":
    case "leader": {
      let best = 0;
      card.options.forEach((option, i) => {
        if (option.percent > card.options[best].percent) best = i;
      });
      return best;
    }
    case "four":
      return card.options.indexOf(card.answer);
    case "duo":
      return packDuo(card.parts[0].answer, card.parts[1].answer);
    default:
      return card.answer;
  }
}

/**
 * How far a guess is from the answer, in the card's own units. On a duo card it
 * is the larger of the two misses, which is the one a line would be about. A
 * tap is either right (0) or not (1).
 */
export function missFor(card: PackCard, guess: number): number {
  if (isTap(card)) return guess === fullGuess(card) ? 0 : 1;
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
  if (isTap(card)) return guess === fullGuess(card) ? fullPoints(card) : 0;
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

/** Where a card starts: a slider in the middle, a tap card with nothing tapped. */
export function startGuess(card: PackCard): number | null {
  if (isTap(card)) return null;
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

/**
 * The Coin's guess: the middle of a slider, and a flip on a tap card. The flips
 * were made once, when the set was built, and ride in the set (`coinTaps`), so
 * the Coin taps the same thing on every phone and a group sees one Coin, not
 * several. A set that carries no flips gets them from a seeded draw instead.
 */
export function coinGuess(pack: GamePack, index: number): number {
  const card = pack.cards[index];
  if (!isTap(card)) return startGuess(card) as number;
  const drawn = pack.coinTaps?.[index] ?? null;
  if (isValidGuess(card, drawn)) return drawn;
  return Math.floor(seeded(`${pack.code}:coin:${card.id}`)() * optionCount(card));
}

/** What every entry starts with besides its guesses. */
function blankMarks(pack: GamePack): Pick<PlayerEntry, "ratings" | "good" | "times" | "fun"> {
  return {
    ratings: pack.cards.map(() => 0),
    good: pack.cards.map(() => false),
    times: pack.steps.map(() => 0),
    fun: 0,
  };
}

export function coinEntry(pack: GamePack): PlayerEntry {
  return {
    name: COIN_NAME,
    guesses: pack.cards.map((_, index) => coinGuess(pack, index)),
    ...blankMarks(pack),
    from: "house",
  };
}

function mean(values: number[]): number {
  return Math.round(values.reduce((sum, v) => sum + v, 0) / values.length);
}

/**
 * The group's one guess on a card: the rounded average of every slider, or the
 * most common tap. When taps are level, the earliest option on the card wins,
 * so every phone agrees.
 */
export function togetherGuess(card: PackCard, guesses: number[]): number | null {
  const valid = guesses.filter((g) => isValidGuess(card, g));
  if (valid.length === 0) return null;
  if (isTap(card)) {
    let best = 0;
    let bestCount = -1;
    for (let option = 0; option < optionCount(card); option += 1) {
      const count = valid.filter((g) => g === option).length;
      if (count > bestCount) {
        best = option;
        bestCount = count;
      }
    }
    return best;
  }
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
    ...blankMarks(pack),
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

// ---- steps -----------------------------------------------------------------

/** Which step a card belongs to, counted from 0. */
export function stepOf(pack: GamePack, index: number): number {
  return Math.min(pack.steps.length - 1, Math.floor(index / pack.perRound));
}

/** The cards of a step, as the first index and one past the last. */
export function stepRange(pack: GamePack, step: number): [number, number] {
  const from = step * pack.perRound;
  return [from, Math.min(pack.cards.length, from + pack.perRound)];
}

/** True when every card of the step is a tap, so its score reads as "4 of 5". */
export function stepIsTaps(pack: GamePack, step: number): boolean {
  const [from, to] = stepRange(pack, step);
  return pack.cards.slice(from, to).every(isTap);
}

export interface StepScore {
  points: number;
  /** Cards answered with full points. */
  right: number;
  /** Cards answered at all. */
  answered: number;
  cards: number;
}

export function stepScore(pack: GamePack, entry: PlayerEntry, step: number): StepScore {
  const [from, to] = stepRange(pack, step);
  let points = 0;
  let right = 0;
  let answered = 0;
  for (let i = from; i < to; i += 1) {
    const guess = entry.guesses[i] ?? null;
    if (!isValidGuess(pack.cards[i], guess)) continue;
    answered += 1;
    const got = pointsFor(pack.cards[i], guess);
    points += got;
    if (got === fullPoints(pack.cards[i])) right += 1;
  }
  return { points, right, answered, cards: to - from };
}

/** The most points a step can pay. */
export function stepMax(pack: GamePack, step: number): number {
  const [from, to] = stepRange(pack, step);
  return pack.cards.slice(from, to).reduce((sum, card) => sum + fullPoints(card), 0);
}

/** A step's score as a player reads it: "4 of 5" for taps, points for sliders, a dash when not played. */
export function stepScoreLabel(pack: GamePack, entry: PlayerEntry, step: number): string {
  const score = stepScore(pack, entry, step);
  if (score.answered === 0) return "–";
  return stepIsTaps(pack, step) ? `${score.right} of ${score.cards}` : String(score.points);
}

export interface StepWin {
  step: number;
  /** Everyone level on the most points in the step. Empty when nobody scored in it. */
  names: string[];
  points: number;
}

/** Who did best in each step. Someone who loses overall can still win one. */
export function stepWins(pack: GamePack, players: PlayerEntry[]): StepWin[] {
  return pack.steps.map((_, step) => {
    const scores = players.map((p) => ({ name: p.name, score: stepScore(pack, p, step) })).filter((s) => s.score.answered > 0);
    const best = Math.max(0, ...scores.map((s) => s.score.points));
    return { step, names: best > 0 ? scores.filter((s) => s.score.points === best).map((s) => s.name) : [], points: best };
  });
}

/** Seconds as a stopwatch reads: 0:42, 1:07. */
export function timeLabel(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * One plain sentence about who got a tap card, for the reveal. Facts only: it
 * is not a roast and is not rated. `names` are the people who answered, in the
 * order they joined, and `right` says which of them tapped the right thing.
 */
export function tapNote(names: string[], right: boolean[]): string {
  const winners = names.filter((_, i) => right[i]);
  if (names.length === 0) return "";
  if (names.length === 1) return winners.length === 1 ? "You got it." : "Not this time.";
  if (winners.length === names.length) return "Everybody got it.";
  if (winners.length === 0) return "Nobody got it.";
  if (winners.length === 1) return `Only ${winners[0]} got it.`;
  const losers = names.filter((_, i) => !right[i]);
  if (losers.length === 1) return `Everybody but ${losers[0]} got it.`;
  return `${joinNames(winners)} got it.`;
}

// ---- standings -------------------------------------------------------------

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
  /** How many of the players the group's answer beat. */
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
    ...blankMarks(pack),
    from,
  };
}

/** A guess in words, as it is shown beside a player's name. */
export function guessLabel(card: PackCard, guess: number | null): string {
  if (!isValidGuess(card, guess)) return "";
  switch (card.kind) {
    case "side":
      return guess === 1 ? "Above 50%" : "Below 50%";
    case "versus":
    case "leader":
      return card.options[guess].short;
    case "four":
      return `${card.options[guess]}%`;
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
    case "side":
      return "Above or below?";
    case "versus":
      return "Which is likelier?";
    case "four":
      return "Pick the number";
    case "leader":
      return "Pick the favorite";
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
