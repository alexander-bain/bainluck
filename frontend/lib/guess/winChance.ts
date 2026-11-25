// Each player's chance of finishing first, after any card. Asked for in
// playtesting: "what are my chances of winning?"
//
// THIS IS AN ESTIMATE ABOUT THE GAME, NOT A NUMBER FROM THE WORLD. It is made
// by playing the rest of the game out many times. On each card still to come, a
// player scores a draw from their own cards so far, mixed with a plain starting
// guess that fades as their own record grows. The page labels it as our
// estimate.
//
// NOBODY'S LATER CARDS ARE LOOKED AT, even when they are known. Someone who
// played yesterday has guesses on every card, and the Coin's whole game can be
// worked out in advance, but using them would tell a person at card 1 how the
// people before them finished. A group plays one card at a time and learns one
// card at a time; the estimate does too.
//
// The draws are seeded by the edition and the card number, so every phone shows
// the same percentages for the same guesses, and the chart at the end matches
// what was shown along the way.

import { pointsFor, seeded } from "./engine";
import type { GamePack, PackCard, PlayerEntry } from "./types";

const RUNS = 1500;

/**
 * How much weight the starting guess keeps: a player's own record counts
 * n / (n + PRIOR_WEIGHT). Six means one good card does not make a favorite:
 * a player's own cards outweigh the starting guess only from the seventh on.
 */
const PRIOR_WEIGHT = 6;

/**
 * Plain starting guesses at what a card pays, before a player has a record of
 * their own. The slider list is set from playtesting, where a typical guess
 * missed by more than twenty points: most slider cards pay little or nothing.
 */
const PRIOR: Record<"slider" | "two" | "four" | "order", number[]> = {
  slider: [0, 0, 0, 0, 2, 4, 6, 9, 13, 17],
  two: [20, 0],
  four: [20, 8, 0, 0],
  order: [20, 12, 12, 5, 5, 0],
};

function priorKey(card: PackCard): keyof typeof PRIOR {
  if (card.kind === "chance" || card.kind === "count") return "slider";
  if (card.kind === "order") return "order";
  return card.options.length === 2 ? "two" : "four";
}

function isSlider(card: PackCard): boolean {
  return card.kind === "chance" || card.kind === "count";
}

/**
 * The chance each entry finishes first, given guesses on the first `upTo`
 * cards. The result lines up with `entries` and sums to 1. A tie for first is
 * shared equally. Before any card, everyone is exactly level; after the last,
 * whoever has the most points has all of it.
 */
export function winChances(pack: GamePack, entries: PlayerEntry[], upTo: number): number[] {
  const count = entries.length;
  if (count === 0) return [];
  if (count === 1) return [1];
  const cards = pack.cards;
  const total = cards.length;
  const done = Math.max(0, Math.min(upTo, total));
  if (done === 0) return entries.map(() => 1 / count);

  const banked = entries.map((e) => {
    let sum = 0;
    for (let i = 0; i < done; i += 1) sum += pointsFor(cards[i], e.guesses[i] ?? null);
    return sum;
  });
  const ownSlider = entries.map((e) =>
    cards.flatMap((card, i) => (i < done && isSlider(card) && e.guesses[i] !== null ? [pointsFor(card, e.guesses[i])] : [])),
  );
  const ownChoice = entries.map((e) =>
    cards.flatMap((card, i) => (i < done && !isSlider(card) && e.guesses[i] !== null ? [pointsFor(card, e.guesses[i])] : [])),
  );

  const random = seeded(`${pack.code}:win:${done}:${count}`);
  const wins = entries.map(() => 0);

  for (let run = 0; run < RUNS; run += 1) {
    let best = -1;
    let leaders: number[] = [];
    for (let p = 0; p < count; p += 1) {
      let score = banked[p];
      for (let i = done; i < total; i += 1) {
        const own = isSlider(cards[i]) ? ownSlider[p] : ownChoice[p];
        const useOwn = own.length > 0 && random() < own.length / (own.length + PRIOR_WEIGHT);
        const from = useOwn ? own : PRIOR[priorKey(cards[i])];
        score += from[Math.floor(random() * from.length)];
      }
      if (score > best) {
        best = score;
        leaders = [p];
      } else if (score === best) {
        leaders.push(p);
      }
    }
    for (const p of leaders) wins[p] += 1 / leaders.length;
  }
  return wins.map((w) => w / RUNS);
}

/** The chances after every card, for the chart at the end: `[afterCard][entry]`, starting level. */
export function winChanceHistory(pack: GamePack, entries: PlayerEntry[], upTo: number): number[][] {
  const out: number[][] = [];
  for (let i = 0; i <= upTo; i += 1) out.push(winChances(pack, entries, i));
  return out;
}
