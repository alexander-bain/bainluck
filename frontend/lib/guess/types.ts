// Types for /guess, the guessing game on bainluck.com (425: C, 426: A, 429: A, 430: A).
//
// THREE STEPS, EASIEST FIRST (430: A). A set is played in steps of five cards:
//
//   Easy    one tap: above or below 50% (`side`), or which of two is more
//           likely (`versus`)
//   Medium  one tap: the chance from four numbers (`four`), or the favorite
//           from four names (`leader`)
//   Hard    a slider (`chance`)
//
// The idea being tried: five quick taps is an unintimidating way in, and a
// person who would never drag a slider to "31%" will still say "below".
//
// The first set mixed sliders with pick-one, ladder and put-in-order cards, and
// played on the live page the sliders were the fun. The tap cards here are not
// those: each asks one plain thing, has a number behind it, and takes one tap.
// The slider kinds `count` and `duo` from set two are still understood by the
// page, though this set does not use them.
//
// Naming note: nothing here is called `GuessCard`. That name belongs to the
// held-back quiz surface, and `webQuizSwitchedOff12601.test.tsx` scans `app/`
// and `components/` for it. This game shares no code with that surface.

/** How a card is answered. The first four are taps; the last three are sliders. */
export type CardKind = "side" | "versus" | "four" | "leader" | "chance" | "count" | "duo";

/**
 * What the card is, for the label on it and for learning which kinds people
 * like. `straight` is a plain slider on one market. `given`, `rest`, `count`
 * and `duo` are sliders of ours from set two. The four tap kinds carry their
 * own name.
 */
export type CardFlavor = "side" | "versus" | "four" | "leader" | "straight" | "given" | "rest" | "count" | "duo";

interface CardBase {
  id: string;
  flavor: CardFlavor;
  /** True when the card puts two or more markets side by side, which no single market page shows. */
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

/** One thing a player can tap on a `versus` or `leader` card, and what the world gives it. */
export interface TapOption {
  label: string;
  /** A word or two, for the chip beside a player's name. */
  short: string;
  emoji: string;
  percent: number;
}

/** Tap above or below 50%. A guess is 1 for above, 0 for below. */
export interface SideCard extends CardBase {
  kind: "side";
  extras: string[];
  /** The world's percent. Never close to 50, so the side is not in doubt. */
  answer: number;
}

/** Tap the more likely of two. A guess is the place of the option tapped. */
export interface VersusCard extends CardBase {
  kind: "versus";
  options: [TapOption, TapOption];
}

/** Tap the world's percent out of four. A guess is the place of the number tapped. */
export interface FourCard extends CardBase {
  kind: "four";
  extras: string[];
  answer: number;
  /** Four percents, smallest first. One of them is `answer`. */
  options: number[];
}

/** Tap the favorite of four. A guess is the place of the option tapped. */
export interface LeaderCard extends CardBase {
  kind: "leader";
  options: TapOption[];
  /** True when more than one of the four can happen, so their chances do not share out 100. */
  independent: boolean;
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

export type TapCard = SideCard | VersusCard | FourCard | LeaderCard;
export type SliderCard = ChanceCard | CountCard | DuoCard;
export type PackCard = TapCard | SliderCard;

/** One step of a set: its name and a line on how its cards are answered. */
export interface StepInfo {
  name: string;
  how: string;
}

/** A dated edition of the game. Its numbers stay as they were read; `asOf` says when. */
export interface GamePack {
  id: string;
  /** Two characters that lead every share link, so a link from another edition is recognised. */
  code: string;
  asOf: string;
  /** Cards in a step. */
  perRound: number;
  /** One entry for each step, in the order they are played. */
  steps: StepInfo[];
  /**
   * What the Coin taps on each tap card, by card (null for a slider). Drawn at
   * random once, when the set is built, and kept only if the Coin lands where a
   * coin should: about half of the two-way taps and a quarter of the four-way
   * ones. So the Coin a person plays against alone is an ordinary coin, never a
   * lucky one. A set without this list lets the Coin flip for itself.
   */
  coinTaps?: (number | null)[];
  topics: string[];
  cards: PackCard[];
}

/**
 * One player's game. A guess is always one whole number: the place of the
 * option tapped (tap cards), a percent (chance), a count (count), or two
 * percents packed as `first * 101 + second` (duo). `null` means not answered.
 */
export interface PlayerEntry {
  name: string;
  guesses: (number | null)[];
  /** How funny this phone found the line on each card: 1 to 5, 0 for none given. */
  ratings: number[];
  /** Cards this phone marked as good at the end of a step. */
  good: boolean[];
  /**
   * Seconds this player spent deciding in each step, card face to lock-in.
   * Shown beside a score, never part of it.
   */
  times: number[];
  /** The step this phone called the most fun, counted from 1. 0 for none given. */
  fun: number;
  /** Where this entry came from. `server` is the group's stored board; `house` is the Coin. */
  from: "here" | "link" | "server" | "house";
}

/** The line shown after a card, and who it is about. */
export interface RoastLine {
  text: string;
  /** Which rule produced it, so ratings can be read by rule later. */
  rule: "far" | "flip" | "exact" | "coin" | "allhigh" | "alllow" | "hot";
  names: string[];
}
