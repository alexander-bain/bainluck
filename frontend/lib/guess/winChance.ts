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
// CARDS COME IN THREE SORTS, AND EACH IS PLAYED OUT AS ITS OWN SORT (430: A).
// A two-way tap pays 10 or nothing about six times in ten; a four-way tap pays
// 15 far less often; a slider pays anything from 0 to 20. A card still to come
// draws only from cards of its own sort, so being five for five on Easy says
// nothing about the sliders at the end. Before the table has played a sort, the
// draw comes from the seed below.
//
// SOMEONE WHO STOPPED HAS STOPPED. A player who came in a link and has no answer
// on a later card is not going to answer it: their game was fixed when the link
// was made. So a person who sent just Easy is not played out through Medium and
// Hard as if they were still at the table. This reads only whether a later
// answer exists, never what it was.
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

import { FOUR_WAY_POINTS, isTap, optionCount, pointsFor, seeded, TWO_WAY_POINTS } from "./engine";
import type { GamePack, PackCard, PlayerEntry } from "./types";

const RUNS = 1500;

/** How slowly a player's own cards come to count: their weight is n / (n + OWN_AFTER). */
const OWN_AFTER = 24;

type Sort = "two" | "four" | "slider";
const SORTS: Sort[] = ["two", "four", "slider"];

function sortOf(card: PackCard): Sort {
  if (!isTap(card)) return "slider";
  return optionCount(card) <= 2 ? "two" : "four";
}

/**
 * What each sort of card tends to pay, used until the table has cards of its
 * own. The slider row is from real play on the live page: a wide spread, from
 * nothing to full marks. The two-way row is from the file rounds, where about
 * six guesses in ten landed on the right side of 50. The four-way row is a
 * starting guess between luck (one in four) and knowing (most of them).
 */
const SEED: Record<Sort, number[]> = {
  two: [TWO_WAY_POINTS, TWO_WAY_POINTS, TWO_WAY_POINTS, 0, 0],
  four: [FOUR_WAY_POINTS, FOUR_WAY_POINTS, 0, 0, 0],
  slider: [0, 0, 0, 3, 8, 9, 10, 12, 13, 15, 17, 18, 20, 20],
};

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

  // Each player's points so far, kept by sort of card.
  const own = entries.map((e) => {
    const by: Record<Sort, number[]> = { two: [], four: [], slider: [] };
    cards.forEach((card, i) => {
      if (i < done && e.guesses[i] !== null) by[sortOf(card)].push(pointsFor(card, e.guesses[i]));
    });
    return by;
  });
  const banked = own.map((by) => SORTS.reduce((sum, s) => sum + by[s].reduce((a, p) => a + p, 0), 0));
  // The table's cards so far, topped up with the seed so a single card never stands for everyone.
  const table = {} as Record<Sort, number[]>;
  SORTS.forEach((s) => {
    table[s] = [...own.flatMap((by) => by[s]), ...SEED[s]];
  });
  const still = cards.slice(done).map(sortOf);
  // For each player, whether each card still to come can be answered at all.
  const open = entries.map((e) => cards.slice(done).map((_, k) => e.from !== "link" || e.guesses[done + k] !== null));

  const random = seeded(`${pack.code}:win:${done}:${count}`);
  const wins = entries.map(() => 0);

  for (let run = 0; run < RUNS; run += 1) {
    let best = -1;
    let leaders: number[] = [];
    for (let p = 0; p < count; p += 1) {
      let score = banked[p];
      for (let k = 0; k < still.length; k += 1) {
        if (!open[p][k]) continue;
        const sort = still[k];
        const mine = own[p][sort];
        const useMine = mine.length / (mine.length + OWN_AFTER);
        const from = mine.length > 0 && random() < useMine ? mine : table[sort];
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
