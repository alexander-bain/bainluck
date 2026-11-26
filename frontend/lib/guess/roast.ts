// The one line shown after each card.
//
// THE RULE, from playtesting: a line is about the person who was FARTHEST from
// the answer, or about someone who was DEAD ON. Never about anyone in between,
// and never about whoever happens to be leading. Three rounds of testing found
// that a line aimed at the leader read as random, and that plain praise was not
// funny. So:
//
//   slider cards   someone dead on gets the line, unless somebody else missed
//                  by 30 or more (a howler beats a bullseye); otherwise the
//                  farthest person gets the card's own line, if they missed by
//                  enough to deserve it;
//   pick cards     everyone who made the worst pick is named together;
//   order cards    everyone with the fewest pairs right.
//
// When nobody earned a line, an "event" line may show instead (everyone too
// high, three good cards running, the Coin beat everybody), but never on two
// cards in a row. When there is nothing true and specific to say, the card
// shows no line at all.
//
// Every template is written so it reads correctly for one name or several:
// `{has}`, `{is}`, `{was}` and `{s}` follow the number of names.

import { COIN_NAME, joinNames, pairsRight, pointsFor } from "./engine";
import type { GamePack, PackCard, PlayerEntry, RoastLine } from "./types";

const CHANCE_FAR = 10;
const CHANCE_HOWLER = 30;
const COUNT_FAR = 2;

const EXACT_LINES = [
  "{n} hit it on the nose: {w}. Everybody else may take a moment.",
  "{n} said {g}. The world says {w}. Suspicious.",
  "Dead on, {n}. Nobody likes a show-off.",
];

const HOT_LINE = "{n} {has} landed three cards running. Somebody check {n} for notes.";
const COLD_LINE = "{n} {has} scored nothing three cards running. It can only go up.";
const ALL_HIGH_LINE = "Every one of you guessed too high. The world was not that excited.";
const ALL_LOW_LINE = "Every one of you guessed too low. The world believed and you did not.";
const COIN_LINE = "The Coin beat {n} on that one. It has never heard of any of this.";

interface Slot {
  name: string;
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
  return card.kind === "chance" ? "%" : "";
}

/** How bad a pick is: 0 for the answer, larger the farther it sits from what was asked for. */
export function pickBadness(card: PackCard, option: number): number {
  if (card.kind === "ladder") return Math.abs(option - card.answer);
  if (card.kind !== "pick") return 0;
  const picked = card.options[option]?.percent ?? 0;
  const answer = card.options[card.answer]?.percent ?? 0;
  if (card.flavor === "longshot") return picked - answer;
  if (card.flavor === "match") return Math.abs(picked - (card.target ?? 0)) - Math.abs(answer - (card.target ?? 0));
  return answer - picked;
}

function sliderLine(card: PackCard, slots: Slot[], index: number): RoastLine | null {
  if (card.kind !== "chance" && card.kind !== "count") return null;
  const far = card.kind === "chance" ? CHANCE_FAR : COUNT_FAR;
  const misses = slots.map((s) => Math.abs(s.guess - card.answer));
  const worst = Math.max(...misses);
  const exact = slots.filter((_, i) => misses[i] === 0);

  if (exact.length > 0 && !(card.kind === "chance" && worst >= CHANCE_HOWLER)) {
    const names = exact.map((s) => s.name);
    return {
      text: fillLine(
        EXACT_LINES[index % EXACT_LINES.length],
        names,
        { g: `${exact[0].guess}${unit(card)}`, w: `${card.answer}${unit(card)}` },
        names.length === slots.length,
      ),
      rule: "exact",
      names,
    };
  }
  if (worst < far) return null;

  // Everyone who shares the worst miss AND the same guess is named together.
  const first = slots[misses.indexOf(worst)];
  const group = slots.filter((s, i) => misses[i] === worst && s.guess === first.guess);
  const template = first.guess > card.answer ? card.roastHigh : card.roastLow;
  const names = group.map((s) => s.name);
  return {
    text: fillLine(template ?? "{n} said {g}. The world says {w}.", names, { g: first.guess, w: card.answer }, names.length === slots.length),
    rule: "far",
    names,
  };
}

function pickLine(card: PackCard, slots: Slot[]): RoastLine | null {
  if (card.kind !== "pick" && card.kind !== "ladder") return null;
  const wrong = slots.filter((s) => s.guess !== card.answer);
  if (wrong.length === 0) return null;
  let worst = wrong[0];
  for (const s of wrong) {
    if (pickBadness(card, s.guess) > pickBadness(card, worst.guess)) worst = s;
  }
  const group = wrong.filter((s) => s.guess === worst.guess);
  const names = group.map((s) => s.name);
  const picked = card.options[worst.guess];
  const answer = card.options[card.answer];
  return {
    text: fillLine(
      card.roastWrong,
      names,
      { pick: picked?.short ?? "", pp: picked?.percent ?? "", w: answer?.percent ?? "" },
      names.length === slots.length,
    ),
    rule: "wrong",
    names,
  };
}

function orderLine(card: PackCard, slots: Slot[]): RoastLine | null {
  if (card.kind !== "order") return null;
  const right = slots.map((s) => pairsRight(card, s.guess));
  const fewest = Math.min(...right);
  if (fewest >= 3) return null;
  const names = slots.filter((_, i) => right[i] === fewest).map((s) => s.name);
  return { text: fillLine(card.roastWrong, names, {}, names.length === slots.length), rule: "wrong", names };
}

function eventLine(
  pack: GamePack,
  index: number,
  people: PlayerEntry[],
  slots: Slot[],
  coin: PlayerEntry | null,
): RoastLine | null {
  const card = pack.cards[index];

  if (coin && slots.length > 0) {
    const coinPoints = pointsFor(card, coin.guesses[index] ?? null);
    const bestPerson = Math.max(...slots.map((s) => s.points));
    if (coinPoints > bestPerson && coinPoints - bestPerson >= 5) {
      const names = slots.map((s) => s.name);
      return { text: fillLine(COIN_LINE, names, {}, true), rule: "coin", names };
    }
  }

  if (card.kind === "chance" && slots.length >= 2) {
    if (slots.every((s) => s.guess - card.answer >= 5)) {
      return { text: ALL_HIGH_LINE, rule: "allhigh", names: slots.map((s) => s.name) };
    }
    if (slots.every((s) => card.answer - s.guess >= 5)) {
      return { text: ALL_LOW_LINE, rule: "alllow", names: slots.map((s) => s.name) };
    }
  }

  if (index >= 2) {
    const lastThree = (p: PlayerEntry) =>
      [index - 2, index - 1, index].map((i) => (p.guesses[i] === null ? null : pointsFor(pack.cards[i], p.guesses[i])));
    const hot = people.filter((p) => lastThree(p).every((v) => v !== null && v >= 15));
    if (hot.length > 0 && hot.length < Math.max(2, people.length)) {
      const names = hot.map((p) => p.name);
      return { text: fillLine(HOT_LINE, names), rule: "hot", names };
    }
    const cold = people.filter((p) => lastThree(p).every((v) => v === 0));
    if (cold.length > 0 && cold.length < Math.max(2, people.length)) {
      const names = cold.map((p) => p.name);
      return { text: fillLine(COLD_LINE, names), rule: "cold", names };
    }
  }
  return null;
}

const EVENT_RULES: RoastLine["rule"][] = ["coin", "allhigh", "alllow", "hot", "cold"];

export function isEventLine(line: RoastLine | null): boolean {
  return line !== null && EVENT_RULES.includes(line.rule);
}

/**
 * The line for card `index`, or null. `people` are the human players (never the
 * Coin) in the order they joined; only those who answered the card count.
 * `coin` is passed only when the Coin is on the board. `previousWasEvent`
 * keeps event lines from showing on two cards in a row.
 */
export function roastFor(
  pack: GamePack,
  index: number,
  people: PlayerEntry[],
  coin: PlayerEntry | null,
  previousWasEvent: boolean,
): RoastLine | null {
  const card = pack.cards[index];
  const slots: Slot[] = people
    .filter((p) => p.name !== COIN_NAME && p.guesses[index] !== null && p.guesses[index] !== undefined)
    .map((p) => ({ name: p.name, guess: p.guesses[index] as number, points: pointsFor(card, p.guesses[index]) }));
  if (slots.length === 0) return null;

  const own = sliderLine(card, slots, index) ?? pickLine(card, slots) ?? orderLine(card, slots);
  if (own) return own;
  if (previousWasEvent) return null;
  return eventLine(pack, index, people, slots, coin);
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
    out.push(roastFor(pack, i, people, coin, i > 0 && isEventLine(out[i - 1])));
  }
  return out;
}
