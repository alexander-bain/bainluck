/**
 * #13551 (Ruling 366: B & 367: A & Fable's 7 rules) — Cross-platform Kit v1 contract.
 * Matches `backend/app/utils/kit_v1_spec.py` identically.
 */

export type KitV1Look =
  | "scoreboard_grid"
  | "dated_tiles"
  | "countdown"
  | "road_ahead"
  | "bubble_line"
  | "one_in_n"
  | "single_sport_slate"
  | "calendar_strip";

export interface ScoreboardGridColumn {
  key: string;
  label: string;
  refused_sum?: number | null;
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
  ladder_footer: string;
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
  look: KitV1Look | null;
  kicker?: string;
  common_headline?: string;
  stat_caption?: string;
  disclosure?: string | null;
  notes?: string[];
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
