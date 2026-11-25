// Types for /guess, the guessing game on bainluck.com (425: C, 426: A, 429: A).
//
// EVERY CARD IS ANSWERED WITH A SLIDER (429: A). The first set mixed sliders
// with pick-one, ladder and put-in-order cards. Played on the live page, the
// sliders were the fun: everyone lands somewhere different, the answer is a
// number, and being close pays. The pick cards were all-or-nothing and often
// the same for everybody. So those kinds are gone, and a card of ours is now a
// slider too.
//
// Naming note: nothing here is called `GuessCard`. That name belongs to the
// held-back quiz surface, and `webQuizSwitchedOff12601.test.tsx` scans `app/`
// and `components/` for it. This game shares no code with that surface.

/** What a player slides: one chance, one count, or two chances on one card. */
export type CardKind = "chance" | "count" | "duo";

/**
 * What the card is, for the label on it and for learning which kinds people
 * like. `straight` restates one market. The other four are ours: they put two
 * or more markets side by side, which no single market page shows.
 */
export type CardFlavor = "straight" | "given" | "rest" | "count" | "duo";

interface CardBase {
  id: string;
  flavor: CardFlavor;
  /** True for every flavor but `straight`. Kept as its own field so a reader of the set sees it at a glance. */
  ours: boolean;
  topic: string;
  emoji: string;
  prompt: string;
  /** A second, smaller line under the prompt. */
  sub?: string;
  /** A few words naming the card, for lists and charts. */
  short: string;
  /** One plain sentence on what the card is about, shown with the answer. */
  context: string;
}

/** A named piece of the answer, drawn as a bar when the answer is shown. */
export interface AnswerPart {
  label: string;
  percent: number;
}

/** Slide to the chance, 0 to 100. */
export interface ChanceCard extends CardBase {
  kind: "chance";
  extras: string[];
  answer: number;
  /**
   * A related number shown BEFORE the guess ("given this, guess that"). `text`
   * is the sentence on the card; `label` names it and `answerLabel` names the
   * thing being guessed, for the two bars shown with the answer.
   */
  given?: { text: string; percent: number; label: string; answerLabel: string };
  /** For a "none of the favorites" card: the favorites and what the world gives each, shown with the answer. */
  parts?: AnswerPart[];
  roastHigh?: string;
  roastLow?: string;
}

/** Slide to how many of a named set the world has at 50% or more. */
export interface CountCard extends CardBase {
  kind: "count";
  answer: number;
  max: number;
  /** Points lost for each one the count is off by. */
  step: number;
  /** What is being counted, plural ("teams"). */
  noun: string;
  roastHigh?: string;
  roastLow?: string;
}

/** One of the two sliders on a duo card. */
export interface DuoPart {
  label: string;
  short: string;
  emoji: string;
  answer: number;
}

/** Two chances on one card. A guess holds both: `first * 101 + second`. */
export interface DuoCard extends CardBase {
  kind: "duo";
  parts: [DuoPart, DuoPart];
  /** Shown when a player has the two the other way round from the world. */
  roastFlip?: string;
  /** Shown for the farthest player otherwise. `{part}` is the short name of the slider they missed by more. */
  roastFar: string;
}

export type PackCard = ChanceCard | CountCard | DuoCard;

/** A dated edition of the game. Its numbers stay as they were read; `asOf` says when. */
export interface GamePack {
  id: string;
  /** Two characters that lead every share link, so a link from another edition is recognised. */
  code: string;
  asOf: string;
  perRound: number;
  topics: string[];
  cards: PackCard[];
}

/**
 * One player's game. A guess is always one whole number: a percent (chance), a
 * count (count), or two percents packed as `first * 101 + second` (duo).
 * `null` means not answered yet.
 */
export interface PlayerEntry {
  name: string;
  guesses: (number | null)[];
  /** How funny this phone found the line on each card: 1 to 5, 0 for none given. */
  ratings: number[];
  /** Cards this phone marked as good at the end of a round. */
  good: boolean[];
  /** Where this entry came from. `house` is the Coin. */
  from: "here" | "link" | "house";
}

/** The line shown after a card, and who it is about. */
export interface RoastLine {
  text: string;
  /** Which rule produced it, so ratings can be read by rule later. */
  rule: "far" | "flip" | "exact" | "coin" | "allhigh" | "alllow" | "hot";
  names: string[];
}
