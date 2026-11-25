// Types for /guess, the guessing game on bainluck.com (425: C, 426: A).
//
// Naming note: nothing here is called `GuessCard`. That name belongs to the
// held-back quiz surface, and `webQuizSwitchedOff12601.test.tsx` scans `app/`
// and `components/` for it. This game shares no code with that surface.

/** What a player does with a card: slide to a number, pick one, or rank three. */
export type CardKind = "chance" | "count" | "pick" | "ladder" | "order";

/** The four flavors of a pick card. They share an input and differ in the rule that names the answer. */
export type PickFlavor = "pair" | "field" | "match" | "longshot";

/** One thing a player can pick, count or rank. `percent` is null only for a ladder's "not by then" rung. */
export interface CardOption {
  label: string;
  short: string;
  emoji: string;
  percent: number | null;
}

interface CardBase {
  id: string;
  /** True when the card compares or counts across markets; false when it restates one market. */
  ours: boolean;
  topic: string;
  emoji: string;
  prompt: string;
  /** A second, smaller line under the prompt. */
  sub?: string;
  /** A few words naming the card, for lists and charts. */
  short: string;
  /** One or two plain sentences on what the card is about, shown with the answer. */
  context: string;
}

/** Slide to the chance, 0 to 100. */
export interface ChanceCard extends CardBase {
  kind: "chance";
  extras: string[];
  answer: number;
  roastHigh?: string;
  roastLow?: string;
}

/** Slide to how many of the listed items the world has at 50% or more. */
export interface CountCard extends CardBase {
  kind: "count";
  items: CardOption[];
  answer: number;
  max: number;
  /** Points lost for each one the count is off by. */
  step: number;
  roastHigh?: string;
  roastLow?: string;
}

/** Pick one of two or four. */
export interface PickCard extends CardBase {
  kind: "pick";
  flavor: PickFlavor;
  /** For a "match" card: the reference percent the answer sits nearest to. */
  target?: number;
  options: CardOption[];
  answer: number;
  /** Option index (as a string key) to the points a near miss earns. */
  partial: Record<string, number>;
  roastWrong: string;
}

/** Pick the earliest rung the world has at 50% or more. */
export interface LadderCard extends CardBase {
  kind: "ladder";
  options: CardOption[];
  answer: number;
  partial: Record<string, number>;
  roastWrong: string;
}

/** Put three in order, the surest first. */
export interface OrderCard extends CardBase {
  kind: "order";
  items: CardOption[];
  roastWrong: string;
}

export type PackCard = ChanceCard | CountCard | PickCard | LadderCard | OrderCard;

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
 * One player's game. A guess is always one small whole number:
 * a percent (chance), a count (count), an option index (pick, ladder),
 * or an index into `ORDER_PERMS` (order). `null` means not answered yet.
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
  rule: "far" | "exact" | "wrong" | "coin" | "allhigh" | "alllow" | "hot" | "cold";
  names: string[];
}
