/**
 * #10868 — the soccer match screen's PRESENTATION TYPES (web), in a module that
 * imports nothing but other declaration-only modules.
 *
 * WHY THIS FILE EXISTS (the same reason as `hockeyJourneyTypes.ts`).
 * `settledVocabulary.test.tsx` enrols every component that transitively
 * imports `lib/propGrade.ts` as a surface that can state a settled PROP
 * verdict. The headline and the history chart state none, so their types live
 * here and their import graph says what they are. The components that DO state
 * prop verdicts (the story cards, All props) and the page that renders them
 * import the verdict words themselves and belong in that census.
 *
 * Declarations only. Built by `soccerMatch.ts` and `soccerMatchStories.ts`.
 */

import type { HockeyJourneyGuide, HockeyJourneyHistorySeries, HockeyJourneyLine } from "./hockeyJourneyTypes";

/** The screen's one phase (native `SoccerEventPagePhase10868`). */
export type SoccerMatchPhase = "before" | "live" | "final";

/** One printed value, or that slot's own absence words (native `SoccerSlotText11449`). */
export type SoccerSlot = { kind: "value"; text: string } | { kind: "unavailable"; text: string };

// ─── Header and headline (soccerMatch.ts) ───────────────────────────────────

export type SoccerMatchScore =
  /** The owner's figures, its provenance line and its spoken words. */
  | { kind: "actual"; home: string; away: string; context: string | null; spoken: string }
  | { kind: "unavailable"; text: string };

export interface SoccerMatchProjection {
  title: string;
  reading: SoccerSlot;
}

export interface SoccerMatchHeader {
  /** "Before kickoff", "In play", "Final · Valladolid won". */
  state: string;
  /** "Mon, Oct 12 · Kickoff 5:00 AM"; null draws none. */
  date: string | null;
  home: string;
  away: string;
  /** Read during play and after the final only; null before kickoff. */
  score: SoccerMatchScore | null;
  /** During play only; null otherwise. */
  clock: SoccerSlot | null;
  projection: SoccerMatchProjection | null;
}

/** What a row of readings is, and separately its dated source context. */
export interface SoccerReadingHeading {
  title: string;
  context: string | null;
}

/** One named outcome: its primary reading and, when a comparison row exists, its comparison reading. */
export interface SoccerOutcomeSlot {
  key: "home" | "draw" | "away";
  label: string;
  /** The served team colour when it clears the contrast floor; null for Draw or a pale colour. */
  tint: string | null;
  primary: SoccerSlot;
  /** Null only when there is no comparison row at all. */
  comparison: SoccerSlot | null;
}

export interface SoccerMatchHeadline {
  /** Home win, Draw, away win — always that order, never sorted. */
  outcomes: [SoccerOutcomeSlot, SoccerOutcomeSlot, SoccerOutcomeSlot];
  primaryHeading: SoccerReadingHeading;
  /** Null: no comparison row. */
  comparisonHeading: SoccerReadingHeading | null;
}

// ─── History (soccerMatch.ts) ───────────────────────────────────────────────

/** A key entry with no line: Draw and the away win, each with its own words. */
export interface SoccerHistoryAbsentEntry {
  id: string;
  key: "draw" | "away";
  name: string;
  words: string;
}

export interface SoccerMatchHistory {
  title: string;
  caption: string;
  /** The line the home series is read from; null when no history response is held. */
  line: HockeyJourneyLine | null;
  /** The only drawn series: the home win chance (its absence words when nothing is drawn). */
  home: HockeyJourneyHistorySeries;
  draw: SoccerHistoryAbsentEntry;
  away: SoccerHistoryAbsentEntry;
  domain: { lower: number; upper: number } | null;
  guides: HockeyJourneyGuide[];
  xTicks: Array<{ t: number; label: string }>;
  yTicks: Array<{ p: number; label: string }>;
  readout: "single" | "beforeAndRecorded";
  beforeLabel: string;
  recordedLabel: string;
  markKey: string | null;
  notes: string[];
  summary: string;
  absence: { title: string; words: string | null } | null;
  detailsLabel: string;
}

// ─── Stories (soccerMatchStories.ts) ────────────────────────────────────────

export type SoccerStoryId = "goals" | "exact" | "both" | "first" | "halves";

/** One shown chance: the raw value, the figure, a short clock and the full clock and venue. */
export interface SoccerObservation {
  probability: number;
  text: string;
  clock: string | null;
  detail: string;
}

export type SoccerPregame = { kind: "value"; observation: SoccerObservation } | { kind: "missing"; words: string };

export type SoccerCurrent =
  | { kind: "recorded"; observation: SoccerObservation }
  /** A quote exists but may not be the current chance. */
  | { kind: "withheld"; words: string }
  | { kind: "unavailable"; words: string }
  /** Goals only: the milestone is already reached — performance, never a settlement. */
  | { kind: "reached"; words: string };

/**
 * The venue's settlement, admitted; or why there is none. A verdict carries no
 * words of its own: the card says it in web's one settled vocabulary.
 */
export type SoccerResult = { kind: "won" } | { kind: "lost" } | { kind: "unconfirmed"; words: string };

/** A row's timing disclosure: every reading with its full clock and venue. */
export interface SoccerTiming {
  title: string;
  lines: string[];
}

export interface SoccerReadingRow {
  /** The row's own original identity (contributor ids, else `market-outcome`). */
  id: string;
  label: string;
  pregame: SoccerPregame;
  /** During play only; null otherwise. */
  current: SoccerCurrent | null;
  /** After the final only (also during play where the card reads one); null otherwise. */
  result: SoccerResult | null;
  timing: SoccerTiming;
}

export interface SoccerGoalsMilestone extends SoccerReadingRow {
  /** The at-least count ("3" for an Over 2.5 line). */
  quantity: number;
  /** "3+". */
  quantityLabel: string;
  /** During play, "1 more for 6+"; null otherwise. */
  performance: string | null;
}

export type SoccerGoalsActual =
  /** `title` is the leaf ("Count so far" / "Final count"); `ruleLabel` the rule's own words ("4 so far" / "5 final"). */
  | {
      kind: "count";
      title: string;
      /** The count itself (home + away goals, both ≥ 0): the plot's actual rule sits here. */
      quantity: number;
      text: string;
      unit: string;
      clock: string | null;
      ruleLabel: string;
      detail: string;
    }
  | { kind: "unavailable"; words: string };

/** A card's own leaf titles for its three readings (each card's native words). */
export interface SoccerLeafTitles {
  pregame: string;
  current: string;
  result: string;
}

export interface SoccerGoalsCard {
  id: "goals";
  name: string;
  eyebrow: string;
  /** "Chance of reaching each total" (the y axis: a fixed 0–100% scale). */
  chartTitle: string;
  /** "Total goals in the match" (the x axis: the milestones' own quantities). */
  quantityAxisTitle: string;
  titles: SoccerLeafTitles;
  title: string;
  milestones: SoccerGoalsMilestone[];
  /** The opening milestone: nearest even odds among printed pre-match chances. */
  defaultId: string | null;
  actual: SoccerGoalsActual | null;
}

export interface SoccerTeamGoals {
  name: string;
  /** The count, or the slot's own words. */
  value: SoccerSlot;
  /** "has scored" / "yet to score" during play; null otherwise. */
  status: string | null;
}

export interface SoccerBothCard {
  id: "both";
  name: string;
  eyebrow: string;
  titles: SoccerLeafTitles;
  /** Before play only, beside the outcomes. */
  beforeContext: string | null;
  outcomes: SoccerReadingRow[];
  defaultId: string | null;
  scoring: { title: string; home: SoccerTeamGoals; away: SoccerTeamGoals; clock: string | null; detail: string | null };
}

export interface SoccerScoreCheckpoint {
  id: string;
  score: string;
  time: string;
  spoken: string;
}

export interface SoccerFirstCard {
  id: "first";
  name: string;
  title: string;
  /** "Pre-match chances" — the lollipop plot of every outcome's pre-match chance. */
  plotTitle: string;
  titles: SoccerLeafTitles;
  /** The venue words ("Polymarket"); null draws none. */
  context: string | null;
  rows: SoccerReadingRow[];
  defaultId: string | null;
  /** During play only: the served score checkpoints, each with its own clock. */
  scorePath: { title: string; note: string; observations: SoccerScoreCheckpoint[] } | null;
}

export interface SoccerHalfCell extends SoccerReadingRow {
  /** The owner's period identity ("first"). */
  periodId: string;
}

export interface SoccerHalfSeries {
  /** "home" · "draw" · "away" — the matrix option's own side. */
  id: string;
  label: string;
  cells: SoccerHalfCell[];
}

export interface SoccerHalvesCard {
  id: "halves";
  name: string;
  eyebrow: string;
  titles: SoccerLeafTitles;
  /** "0–100% scale" and "Lines compare halves, not changes over time." */
  scaleCaption: string;
  lineExplanation: string;
  title: string;
  periods: Array<{ id: string; label: string }>;
  series: SoccerHalfSeries[];
  defaultId: string | null;
  /** "Results so far · Valladolid" / "Final results · Valladolid" for the default series; null before kickoff. */
  resultsTitle: string | null;
  /** The results heading's lead, joined to the chosen series' label by the card; null before kickoff. */
  resultsLead: string | null;
  /** "Half result" during play, "Final result" after it. */
  resultTitle: string;
  /** A series with no original for a half says so in this cell. */
  cellUnavailable: string;
  plotTitle: string;
  pointExplanation: string;
}

export type SoccerExactPlacement = { kind: "grid"; home: number; away: number } | { kind: "nonGrid" };

export interface SoccerExactOriginal extends SoccerReadingRow {
  placement: SoccerExactPlacement;
  /** True for a listed original the payload no longer serves (the owner's held label, no chance). */
  held: boolean;
}

export interface SoccerExactScope {
  id: string;
  label: string;
  rows: number[];
  columns: number[];
  originals: SoccerExactOriginal[];
  actual: { title: string; text: string } | null;
  /**
   * The owner's pre-match shading scale (`scaleUpper`, native `scale`): its
   * upper bound and its ticks as (fraction of the bound, figure). Null when the
   * bound is unusable — then no cell is shaded and the map says so.
   */
  scale: { upper: number; ticks: Array<{ fraction: number; text: string }> } | null;
}

export interface SoccerExactCard {
  id: "exact";
  name: string;
  title: string;
  titles: SoccerLeafTitles;
  /** The map's key lines, each shown only when the scope uses it (native `Words.legend`). */
  legend: { scaleTitle: string; offScale: string; notListed: string; unavailable: string; result: string; selection: string };
  /** "Choose a score to compare." */
  noSelection: string;
  /** "Pre-match scale unavailable. Cells are not shaded." */
  scaleUnavailable: string;
  /** "—": a listed score with no pre-match chance. */
  unavailableMark: string;
  intro: string;
  homeLabel: string;
  awayLabel: string;
  rowsTitle: string;
  columnsTitle: string;
  scopes: SoccerExactScope[];
  defaultScopeId: string | null;
  otherChoicesTitle: string;
  notListed: string;
}

export type SoccerStoryCard = SoccerGoalsCard | SoccerExactCard | SoccerBothCard | SoccerFirstCard | SoccerHalvesCard;

export interface SoccerStoryStream {
  heading: string;
  /** The offered cards, in the screen's fixed order: goals, exact score, both teams, first team, halves. */
  cards: SoccerStoryCard[];
  /** "Use Previous or Next to see each story" when more than one card is offered. */
  manualStatus: string | null;
  storiesLabel: string;
  /** The stream's own words when no card is offered (the owner-unavailable state). */
  emptyWords: string;
}

// ─── The page (soccerMatch.ts) ──────────────────────────────────────────────

export interface SoccerMatchPageModel {
  eventId: number;
  phase: SoccerMatchPhase;
  header: SoccerMatchHeader;
  headline: SoccerMatchHeadline;
  history: SoccerMatchHistory;
  stories: SoccerStoryStream;
  copy: {
    storiesLabel: string;
    /** "All props · 98"; null when no original is listed. */
    allPropsLabel: string | null;
  };
  /** Served team colours for the chart's CSS variables. */
  colors: { home: string | null; away: string | null };
}
