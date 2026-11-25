// The one line shown after a card.
//
// WHO IT IS ABOUT, from playtesting: the person who was FARTHEST from the
// answer, or someone who was DEAD ON. Never anyone in between, and never
// whoever happens to be leading.
//
// WHEN IT SHOWS (429: A). The first set on the live page showed a line on
// nearly every card, and eleven of twelve got the lowest rating: "the roasting
// was not funny or entertaining". The lines that had been laughed at in the
// file versions were short and turned on the subject itself. So a line now has
// to be earned:
//
//   • someone dead on gets one, unless somebody else missed by 30 or more;
//   • otherwise the farthest person gets the card's own line, but only if they
//     scored NOTHING on the card (a miss of 20 or more on a chance card). In
//     real play the farthest of three people is 12 or more off on four cards in
//     five, so a lower bar would put a line back on nearly every card;
//   • a two-slider card counts a miss of 40 or more on either slider as well,
//     and has its own line for having the two the wrong way round;
//   • when nobody earned a line, a line about the table may show (everyone too
//     high, three closest in a row, the Coin beat everybody), never on two
//     cards running;
//   • otherwise the card says nothing.
//
// Lines call players by first name. Every template reads correctly for one
// name or several: `{has}`, `{is}`, `{was}` and `{s}` follow the number of
// names. `{d}` is how many points off the guess was.

import { COIN_NAME, duoParts, isValidGuess, joinNames, missFor, pointsFor, spokenNames } from "./engine";
import type { GamePack, PackCard, PlayerEntry, RoastLine } from "./types";

/** On a two-slider card, a miss this big on either slider earns a line even if the other slider scored. */
const DUO_EARNED_MISS = 40;
const HOWLER = 30;

/** Whether a guess was bad enough for a line: it scored nothing. */
export function earnsLine(card: PackCard, guess: number): boolean {
  if (pointsFor(card, guess) === 0) return true;
  return card.kind === "duo" && missFor(card, guess) >= DUO_EARNED_MISS;
}

const EXACT_LINES = [
  "{n} said {g}. The world says {w}. Either {n} {is} a genius or {n} {is} the world.",
  "Dead on at {g}. {n} {has} clearly played this before.",
  "{n} matched the world to the point. Check {n} for notes.",
];

const HOT_LINE = "{n} {has} been the closest three cards running. Somebody check {n}’s phone.";
const ALL_HIGH_LINE = "Every one of you guessed too high. In this room, everything happens.";
const ALL_LOW_LINE = "Every one of you guessed too low. According to this room, nothing ever happens.";
const COIN_LINE = "The Coin beat {n} on that one. It was not even listening.";

interface Slot {
  /** The player's whole name, as the game keeps it. */
  name: string;
  /** What a line calls them. */
  said: string;
  guess: number;
  points: number;
}

/**
 * How a list of names is said. One to three are named; more than three are
 * "Ann, Bo and 2 others"; and when `everyone` is true for three or more, it is
 * "all of you", because a line that names the whole table names nobody.
 */
export function sayNames(names: string[], everyone: boolean): string {
  if (everyone && names.length >= 3) return "all of you";
  if (names.length > 3) return `${names[0]}, ${names[1]} and ${names.length - 2} others`;
  return joinNames(names);
}

/**
 * Fill a template. `names` decides singular or plural. `everyone` says the
 * names are the whole table. `{n}` at the start of a sentence is capitalised.
 */
export function fillLine(
  template: string,
  names: string[],
  values: Record<string, string | number> = {},
  everyone: boolean = false,
): string {
  const many = names.length > 1;
  const said = sayNames(names, everyone);
  const map: Record<string, string> = {
    s: many ? "" : "s",
    has: many ? "have" : "has",
    is: many ? "are" : "is",
    was: many ? "were" : "was",
  };
  Object.entries(values).forEach(([key, value]) => {
    map[key] = String(value);
  });
  return template.replace(/\{(\w+)\}/g, (whole, key: string, at: number) => {
    if (key === "n") {
      const before = template.slice(0, at).trimEnd();
      const opensSentence = before === "" || /[.!?]$/.test(before);
      return opensSentence ? said.charAt(0).toUpperCase() + said.slice(1) : said;
    }
    return key in map ? map[key] : whole;
  });
}

function unit(card: PackCard): string {
  return card.kind === "count" ? "" : "%";
}

function shown(card: PackCard, value: number): string {
  return `${value}${unit(card)}`;
}

function exactLine(card: PackCard, slots: Slot[], index: number): RoastLine | null {
  if (card.kind === "duo") return null;
  const worst = Math.max(...slots.map((s) => missFor(card, s.guess)));
  if (card.kind === "chance" && worst >= HOWLER) return null;
  const exact = slots.filter((s) => s.guess === card.answer);
  if (exact.length === 0) return null;
  return {
    text: fillLine(
      EXACT_LINES[index % EXACT_LINES.length],
      exact.map((s) => s.said),
      { g: shown(card, card.answer), w: shown(card, card.answer) },
      exact.length === slots.length,
    ),
    rule: "exact",
    names: exact.map((s) => s.name),
  };
}

function farLine(card: PackCard, slots: Slot[]): RoastLine | null {
  // The farthest is whoever missed by most (on a two-slider card, on either slider).
  const worstMiss = Math.max(...slots.map((s) => missFor(card, s.guess)));
  const first = slots.find((s) => missFor(card, s.guess) === worstMiss) as Slot;
  if (!earnsLine(card, first.guess)) return null;
  // People who made the very same guess are named together.
  const group = slots.filter((s) => s.guess === first.guess);
  const names = group.map((s) => s.name);
  const said = group.map((s) => s.said);
  const everyone = group.length === slots.length;

  if (card.kind === "duo") {
    const [a, b] = duoParts(first.guess);
    const [wa, wb] = [card.parts[0].answer, card.parts[1].answer];
    const flipped = a !== b && wa !== wb && a > b !== wa > wb;
    if (flipped && card.roastFlip) {
      return { text: fillLine(card.roastFlip, said, { d: worstMiss }, everyone), rule: "flip", names };
    }
    const second = Math.abs(b - wb) > Math.abs(a - wa);
    const part = card.parts[second ? 1 : 0];
    return {
      text: fillLine(card.roastFar, said, { part: part.short, g: `${second ? b : a}%`, w: `${part.answer}%`, d: worstMiss }, everyone),
      rule: "far",
      names,
    };
  }

  const values = { g: first.guess, w: card.answer, d: worstMiss };
  const template = first.guess > card.answer ? card.roastHigh : card.roastLow;
  if (!template) return null;
  return { text: fillLine(template, said, values, everyone), rule: "far", names };
}

function tableLine(pack: GamePack, index: number, people: PlayerEntry[], slots: Slot[], coin: PlayerEntry | null): RoastLine | null {
  const card = pack.cards[index];

  if (coin) {
    const coinPoints = pointsFor(card, coin.guesses[index] ?? null);
    const best = Math.max(...slots.map((s) => s.points));
    if (coinPoints - best >= 5) {
      return { text: fillLine(COIN_LINE, slots.map((s) => s.said), {}, true), rule: "coin", names: slots.map((s) => s.name) };
    }
  }

  if (card.kind === "chance" && slots.length >= 2) {
    if (slots.every((s) => s.guess - card.answer >= 5)) return { text: ALL_HIGH_LINE, rule: "allhigh", names: slots.map((s) => s.name) };
    if (slots.every((s) => card.answer - s.guess >= 5)) return { text: ALL_LOW_LINE, rule: "alllow", names: slots.map((s) => s.name) };
  }

  if (index >= 2 && people.length >= 2) {
    // The one player who was closest, alone, on each of the last three cards.
    const closestOn = (i: number): string | null => {
      const scored = people
        .filter((p) => isValidGuess(pack.cards[i], p.guesses[i] ?? null))
        .map((p) => ({ name: p.name, points: pointsFor(pack.cards[i], p.guesses[i]) }));
      if (scored.length < 2) return null;
      const top = Math.max(...scored.map((s) => s.points));
      const winners = scored.filter((s) => s.points === top);
      return winners.length === 1 ? winners[0].name : null;
    };
    const three = [closestOn(index - 2), closestOn(index - 1), closestOn(index)];
    if (three[0] !== null && three[0] === three[1] && three[1] === three[2]) {
      const slot = slots.find((s) => s.name === three[0]);
      if (slot) return { text: fillLine(HOT_LINE, [slot.said]), rule: "hot", names: [slot.name] };
    }
  }
  return null;
}

const TABLE_RULES: RoastLine["rule"][] = ["coin", "allhigh", "alllow", "hot"];

export function isTableLine(line: RoastLine | null): boolean {
  return line !== null && TABLE_RULES.includes(line.rule);
}

/**
 * The line for card `index`, or null. `people` are the human players (never the
 * Coin) in the order they joined; only those who answered the card count.
 * `coin` is passed only when the Coin is on the board. `previousWasTable`
 * keeps lines about the whole table from showing on two cards in a row.
 */
export function roastFor(
  pack: GamePack,
  index: number,
  people: PlayerEntry[],
  coin: PlayerEntry | null,
  previousWasTable: boolean,
): RoastLine | null {
  const card = pack.cards[index];
  const humans = people.filter((p) => p.name !== COIN_NAME);
  const spoken = spokenNames(humans.map((p) => p.name));
  const slots: Slot[] = humans
    .filter((p) => isValidGuess(card, p.guesses[index] ?? null))
    .map((p) => ({
      name: p.name,
      said: spoken.get(p.name) ?? p.name,
      guess: p.guesses[index] as number,
      points: pointsFor(card, p.guesses[index]),
    }));
  if (slots.length === 0) return null;

  const own = exactLine(card, slots, index) ?? farLine(card, slots);
  if (own) return own;
  if (previousWasTable) return null;
  return tableLine(pack, index, humans, slots, coin);
}

/** Every line of card `0..upTo`, in order, with the back-to-back rule applied. Lets any phone rebuild what was shown. */
export function roastHistory(
  pack: GamePack,
  upTo: number,
  people: PlayerEntry[],
  coin: PlayerEntry | null,
): (RoastLine | null)[] {
  const out: (RoastLine | null)[] = [];
  for (let i = 0; i <= upTo && i < pack.cards.length; i += 1) {
    out.push(roastFor(pack, i, people, coin, i > 0 && isTableLine(out[i - 1])));
  }
  return out;
}
