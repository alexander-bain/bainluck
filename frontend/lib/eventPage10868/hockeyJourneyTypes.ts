/**
 * #10868 — the hockey journey's PRESENTATION TYPES, in a module that imports
 * nothing.
 *
 * WHY THIS FILE EXISTS. `settledVocabulary.test.tsx` enrols every component
 * that transitively imports `lib/propGrade.ts` as a surface that can state a
 * settled PROP verdict. The matrix and the history chart state none — the
 * matrix's only result words are the TEAM's ("Won" / "Lost"), the chart's none
 * at all — yet they reached `propGrade` through the `hockeyJourney` barrel
 * (core → `formatPoints` in nflEventCardDeck → playerPropsGrouping → propGrade).
 * Their types live here so their import graph says what they are. The
 * components that DO state prop verdicts (All props, the points/assists card)
 * and the wrappers that render them stay enrolled in that census.
 *
 * Declarations only; re-exported unchanged by `hockeyJourneyCore`,
 * `hockeyJourneyHistory` and `hockeyJourney`.
 */

/** The screen's one phase: before the start, during play, after the final. */
export type HockeyJourneyPhase = "before" | "live" | "final";

/** One printed value, or that slot's own absence words. */
export type HockeyJourneySlot =
  | { kind: "value"; text: string; spoken: string }
  | { kind: "absent"; text: string };

// ─── The matrix and headline (built in hockeyJourney.ts) ─────────────────────

export interface HockeyJourneyTeam {
  side: "home" | "away";
  name: string;
  /** The compact name, when it differs from the full one. */
  short: string | null;
  /** The served team colour when it clears the card-surface contrast floor, else null. */
  tint: string | null;
}

export interface HockeyJourneyColumn {
  title: string;
  provenance: string | null;
}

export interface HockeyJourneyMatrixRow {
  side: "home" | "away";
  /** One slot per column, in column order. */
  values: HockeyJourneySlot[];
  /** "Won" / "Lost" after the final; null otherwise or on a draw. */
  result: string | null;
}

export interface HockeyJourneyMatrix {
  phase: HockeyJourneyPhase;
  columns: HockeyJourneyColumn[];
  /** Home first, then away (the native matrix's order). */
  rows: [HockeyJourneyMatrixRow, HockeyJourneyMatrixRow];
  /**
   * The emphasised column: the current chance during play, else the first.
   * Native `HockeyJourneyMatrixLayout10868.lead`.
   */
  lead: number;
  /**
   * Column indices kept together in the labelled-pairs fallback, in order —
   * before [[0,1]], during [[0,1],[2,3]], final [[0],[1,2]]. Native
   * `HockeyJourneyMatrixLayout10868.groups`.
   */
  groups: number[][];
}

export interface HockeyJourneyHeadline {
  state: string;
  stateContext: string | null;
  home: HockeyJourneyTeam;
  away: HockeyJourneyTeam;
  matrix: HockeyJourneyMatrix;
  /** During play only, under an admitted current forecast. */
  historicalForecast: { title: string; reading: string } | null;
  spokenLabel: string;
}

// ─── The history (built in hockeyJourneyHistory.ts) ──────────────────────────

export type HockeyJourneyLine = "blend" | "consensus";
export type HockeyJourneySide = "home" | "away";

export interface HockeyJourneyHistoryPoint {
  /** `<series id>#<served timestamp>` — the served timestamp is unique inside a series. */
  id: string;
  t: number;
  p: number;
  /** The last pregame row, drawn hollow. */
  hollow: boolean;
  /** Position in the served array. */
  row: number;
  /** The reading's figure, as the readout would print it. */
  figure: string;
}

export type HockeyJourneyReading =
  | { kind: "reading"; figure: string; provenance: string; pointId: string | null }
  | { kind: "absent"; words: string };

export interface HockeyJourneyHistorySeries {
  id: string;
  side: HockeyJourneySide;
  name: string;
  /** Separated runs, in time order. Two runs are never joined. */
  runs: HockeyJourneyHistoryPoint[][];
  before: HockeyJourneyReading;
  recorded: HockeyJourneyReading;
}

export interface HockeyJourneyGuide {
  id: string;
  t: number;
  label: string;
  kind: "period" | "play";
}

export interface HockeyJourneyHistory {
  title: string;
  caption: string;
  /** The line both series are read from; null when no history response is held. */
  line: HockeyJourneyLine | null;
  series: [HockeyJourneyHistorySeries, HockeyJourneyHistorySeries];
  /** First to last drawn row; null under an absence. */
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
