// Each player's chance of finishing first, after any card. Asked for in
// playtesting: "what are my chances of winning?"
//
// THIS IS AN ESTIMATE ABOUT THE GAME, NOT A NUMBER FROM THE WORLD. It is made
// by playing the rest of the game out many times. The page labels it as our
// estimate.
//
// IT LEANED TOO HARD ON A FEW CARDS, AND THIS IS THE FIX (429: A). The first
// version treated each player's own cards so far as how they would go on
// playing, so two bad cards made someone a no-hoper. On the first live set the
// table's averages were within about two points a card of each other, while a
// single card swings by eight or so: most of what looks like form early on is
// luck. So on each card still to come a player now scores a draw from THE
// WHOLE TABLE'S cards so far, and only now and then from their own: their own
// record counts n / (n + OWN_AFTER), about a thirteenth after two cards and a
// third by the last. Early on a lead is worth the points in it and little more.
//
// It does not flatter. Someone thirty points behind two people with ten cards
// to go has a small chance, and the page shows a small number.
//
// NOBODY'S LATER CARDS ARE LOOKED AT, even when they are known. Someone who
// played yesterday has guesses on every card, but using them would tell a
// person at card 1 how the people before them finished.
//
// The draws are seeded by the edition and the card number, so every phone shows
// the same percentages for the same guesses, and the chart at the end matches
// what was shown along the way.

import { pointsFor, seeded } from "./engine";
import type { GamePack, PlayerEntry } from "./types";

const RUNS = 1500;

/** How slowly a player's own cards come to count: their weight is n / (n + OWN_AFTER). */
const OWN_AFTER = 24;

/**
 * What a slider tends to pay, used until the table has cards of its own. Set
 * from real play on the live page: a wide spread, from nothing to full marks.
 */
const SEED = [0, 0, 0, 3, 8, 9, 10, 12, 13, 15, 17, 18, 20, 20];

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

  const own = entries.map((e) =>
    cards.flatMap((card, i) => (i < done && e.guesses[i] !== null ? [pointsFor(card, e.guesses[i])] : [])),
  );
  const banked = own.map((points) => points.reduce((sum, p) => sum + p, 0));
  // The table's cards so far, topped up with the seed so a single card never stands for everyone.
  const table = [...own.flat(), ...SEED];

  const random = seeded(`${pack.code}:win:${done}:${count}`);
  const wins = entries.map(() => 0);

  for (let run = 0; run < RUNS; run += 1) {
    let best = -1;
    let leaders: number[] = [];
    for (let p = 0; p < count; p += 1) {
      let score = banked[p];
      const mine = own[p];
      const useMine = mine.length / (mine.length + OWN_AFTER);
      for (let i = done; i < total; i += 1) {
        const from = mine.length > 0 && random() < useMine ? mine : table;
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
