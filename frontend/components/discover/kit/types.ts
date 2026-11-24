/**
 * Issue 13551 (Ruling 366: B, 367: A, and Fable's 7 rules) — Cross-platform Kit v1 contract.
 * Reconciled with Builder C (comment-7122832951); matches `backend/app/utils/kit_v1_spec.py`.
 */

export type KitV1Layout = "stack" | "grid" | "calendar" | "axis";

export type KitV1Variant =
  | "countdown"
  | "road_ahead"
  | "one_in_n"
  | "single_sport_slate"
  | "casting_sheet"
  | "the_cut"
  | "scoreboard_grid"
  | "places_grid"
  | "dated_tiles"
  | "photo_wall"
  | "calendar_strip"
  | "bubble_line"
  | "shared_scale"
  | "deadline_line";

export const VARIANT_TO_LAYOUT: Record<KitV1Variant, KitV1Layout> = {
  countdown: "stack",
  road_ahead: "stack",
  one_in_n: "stack",
  single_sport_slate: "stack",
  casting_sheet: "stack",
  the_cut: "stack",
  scoreboard_grid: "grid",
  places_grid: "grid",
  dated_tiles: "grid",
  photo_wall: "grid",
  calendar_strip: "calendar",
  bubble_line: "axis",
  shared_scale: "axis",
  deadline_line: "axis",
};

export interface KitV1SourceMark {
  label: string;
  count: number;
}

export interface KitV1Route {
  kind: "collection" | "event" | "market" | "team";
  id: number | null;
  slug: string | null;
}

export interface ScoreboardGridColumn {
  key: string;
  label: string;
}

export interface ScoreboardGridRow {
  rank: number;
  name: string;
  image_url: string;
  image_kind: string;
  cells: Record<string, number | null>;
}

export interface ScoreboardGridData {
  columns: ScoreboardGridColumn[];
  rows: ScoreboardGridRow[];
}

export interface DatedTileColumn {
  key: string;
  label: string;
}

export interface DatedTileRow {
  name: string;
  image_url: string;
  image_kind: string;
  cells: Record<string, number | null>;
}

export interface DatedTilesData {
  aligned: boolean;
  columns: DatedTileColumn[];
  rows: DatedTileRow[];
}

export interface CountdownRow {
  name: string;
  p: number;
  image_url: string;
  image_kind: string;
}

export interface CountdownData {
  days_left: number;
  deadline_label: string;
  rows: CountdownRow[];
}

export interface RoadAheadRow {
  opponent_name: string;
  opponent_abbr: string;
  opponent_color: string | null;
  opponent_image_url: string;
  home_or_away: "vs" | "at";
  day: string;
  clock: string;
  team_p: number;
}

export interface RoadAheadData {
  team_name: string;
  team_abbr: string;
  team_color: string | null;
  team_image_url: string;
  rows: RoadAheadRow[];
}

export interface BubbleLinePoint {
  name: string;
  abbr: string;
  p: number;
  lane?: number | null;
  in_doubt: boolean;
  color: string | null;
  image_url: string;
}

export interface BubbleLineData {
  band_low: number;
  band_high: number;
  band_label: string;
  low_count: number;
  high_count: number;
  points: BubbleLinePoint[];
  doubt_summary: string;
}

export interface OneInNRow {
  name: string;
  p: number;
  one_in_n: number;
  image_url: string;
  image_kind: string;
}

export interface OneInNData {
  rows: OneInNRow[];
}

export interface SingleSportSlateSide {
  name: string;
  abbr: string;
  color: string | null;
  image_url: string;
  p: number;
}

export interface SingleSportSlateRow {
  sport_key?: string;
  away: SingleSportSlateSide;
  home: SingleSportSlateSide;
  day: string;
  clock: string;
  status: string;
  score: [number | null, number | null];
}

export interface SingleSportSlateData {
  sport_key: string;
  league_label: string;
  rows: SingleSportSlateRow[];
}

export interface CalendarStripDay {
  dow: string;
  day_num: string;
  month_abbr: string;
  daily_pct: number;
  is_peak: boolean;
}

export interface CalendarStripData {
  month_span_label: string;
  show_percent: true;
  ladder_rule_note: string;
  days: CalendarStripDay[];
}

export type KitV1Data =
  | ScoreboardGridData
  | DatedTilesData
  | CountdownData
  | RoadAheadData
  | BubbleLineData
  | OneInNData
  | SingleSportSlateData
  | CalendarStripData;

export interface KitV1CardSpec {
  kit_version: 1;
  id: string;
  layout: KitV1Layout | null;
  variant: KitV1Variant | null;
  kicker?: string;
  common_headline?: string;
  stat_caption?: string;
  source_mark?: KitV1SourceMark;
  route?: KitV1Route;
  footnote?: string | null;
  disclosure?: string | null;
  refusal_reason: string | null;
  fallback_today?: boolean;
  data?: KitV1Data;
}

export interface KitV1PreviewResponse {
  kit_version: number;
  count: number;
  items: KitV1CardSpec[];
  refusals: Array<{ title: string; spec: KitV1CardSpec }>;
}
