/**
 * Pure value-model types and semantic colour constants for the unified
 * Direction 199 game page headline (`EventPageHeadline199`), mirroring iOS
 * `HeadlineStyleTable199.swift` without pulling prop-grading modules into the
 * headline component's import graph.
 */

import { SLATE_TEAM_FALLBACK } from "@/lib/teamColors";

export type HeadlinePhase199 = "before" | "during" | "after";

export type HeadlineColumnRole199 =
  | "setScore"
  | "gamePoints"
  | "score"
  | "projected"
  | "chance"
  | "now"
  | "pregame"
  | "finalResult";

export interface HeadlineColumnSpec199 {
  role: HeadlineColumnRole199;
  header: string;
  setIndex?: number;
}

export type HeadlineRowRole199 = "away" | "home" | "draw";

export interface HeadlineCompetitorRow199 {
  role: HeadlineRowRole199;
  fullName: string;
  opponentFullName: string;
  shortName: string;
  record: string | null;
  cells: string[];
  rawProbability: number | null;
  won: boolean | null;
  emphasizedColumns: number[];
  abbreviation: string | null;
  opponentAbbreviation: string | null;
}

export type HeadlineBottomBar199 =
  | {
      kind: "twoWay";
      awayShare: number;
      homeShare: number;
      pregameAwayMarker: number | null;
    }
  | {
      kind: "threeWay";
      homeShare: number;
      drawShare: number;
      awayShare: number;
    };

export interface HeadlineLivePregameSummary199 {
  leadWord: "Pregame";
  bodyText: string;
  fullText: string;
  namedText?: string | null;
  namedSide?: HeadlineRowRole199 | null;
  firstProjText?: string | null;
  firstProjSide?: "home" | "away" | null;
  secondProjText?: string | null;
  secondProjSide?: "home" | "away" | null;
}

export interface HeadlineModel199 {
  eventId: number;
  sportKey: string;
  phase: HeadlinePhase199;
  leagueLabel: string;
  plainMetaText: string | null;
  startTimeText: string | null;
  broadcastText: string | null;
  liveBadgeText: string | null;
  isStoppedOrNoResult: boolean;
  columns: HeadlineColumnSpec199[];
  hasAnyColumnValue: boolean;
  rows: HeadlineCompetitorRow199[];
  bottomBar: HeadlineBottomBar199 | null;
  livePregameSummary: HeadlineLivePregameSummary199 | null;
  colors: {
    away: string;
    home: string;
    drawText: string;
    drawBar: string;
  };
}

/** Semantic colours matching `HeadlineStyleTable199` on iOS. */
export const HEADLINE_STYLE_199 = {
  quietInk: "#526071",
  liveSummaryQuietInk: "#8B98A9", // quiet neutral label ink distinct from #475569 slate team text
  slateTeamTextInk: "#475569", // slate-600 — readable & distinct from liveSummaryQuietInk on grey-fallback pairs
  primaryInk: "#0F172A",
  loserOpacity: 0.65,
  winnerTickInk: "#178F4D",
  drawTextInk: "#94A3B8", // slate-400 — visibly lighter than #64748B slate-500 team fallback
  drawBarInk: "#CBD5E1", // slate-300 — visibly lighter than #64748B slate-500 bar segment
  livePillBg: "#DC2626",
  defaultAwayHex: SLATE_TEAM_FALLBACK, // #64748B
  defaultHomeHex: "#2563EB", // blue-600
} as const;
