/**
 * Issue 13551 (Rulings 366: B, 367: A, and Fable's 7 rules) — Cross-platform Kit v1 contract.
 * Layout-generic body built exclusively from the 8 marks; `variant` is an optional hint only.
 */

export type KitV1Layout = "stack" | "grid" | "calendar" | "axis";

export type KitV1Tone = "primary" | "secondary" | "muted" | "accent" | "warn";

export type KitV1MarkKind =
  | "picture"
  | "word"
  | "number"
  | "bar"
  | "tile"
  | "ring"
  | "dot"
  | "line";

export const ALLOWED_KIT_V1_LAYOUTS: readonly KitV1Layout[] = [
  "stack",
  "grid",
  "calendar",
  "axis",
];

export const ALLOWED_KIT_V1_MARKS: readonly KitV1MarkKind[] = [
  "picture",
  "word",
  "number",
  "bar",
  "tile",
  "ring",
  "dot",
  "line",
];

export interface KitV1SourceMark {
  label: string;
  count: number;
}

export interface KitV1Route {
  kind: "collection" | "event" | "market" | "team";
  id: number | null;
  slug: string | null;
}

export interface KitV1PictureMark {
  mark: "picture";
  url: string | null;
  initials?: string | null;
  alt: string;
  subject_kind: string;
  size?: "xs" | "sm" | "md";
  contain?: boolean;
}

export interface KitV1WordMark {
  mark: "word";
  text: string;
  secondary_text?: string;
  deadline_iso?: string;
  style?: "row" | "sub" | "kicker" | "pill" | "meta" | "rank" | "hero_label";
  tone?: KitV1Tone;
  align?: "left" | "center" | "right";
  width?: "xs" | "sm" | "flex" | "auto";
  bold?: boolean;
}

export interface KitV1NumberMark {
  mark: "number";
  value: number;
  display: string;
  unit?: "%" | "days" | "one_in_n";
  deadline_iso?: string;
  tone?: KitV1Tone;
  prominence?: "hero" | "primary" | "cell" | "secondary";
  align?: "left" | "center" | "right";
  width?: "xs" | "sm" | "auto";
}

export interface KitV1AdaptiveColor {
  light: string;
  dark: string;
}

export interface KitV1BarSegment {
  fill: number;
  color?: KitV1AdaptiveColor | null;
  label?: string;
}

export interface KitV1BarMark {
  mark: "bar";
  bar_style: "single" | "split" | "range";
  fill?: number;
  fill_color?: KitV1AdaptiveColor | null;
  segments?: KitV1BarSegment[];
  lo?: number;
  hi?: number;
  open_lo?: boolean;
  open_hi?: boolean;
  pct_label?: string;
  width?: "sm" | "md" | "flex";
}

export interface KitV1TileMark {
  mark: "tile";
  shade: number;
  top_label?: string | null;
  center_label: string;
  bottom_label?: string | null;
  muted?: boolean;
  highlight_role?: "day_peak" | "row_peak" | "column_peak" | null;
}

export interface KitV1RingMark {
  mark: "ring";
  progress: number;
  label?: string | null;
  tone?: "accent" | "muted";
}

export interface KitV1DotMark {
  mark: "dot";
  x: number;
  y_lane?: number | null;
  label: string;
  color?: KitV1AdaptiveColor | null;
  in_band?: boolean;
  picture?: KitV1PictureMark | null;
  badge_text?: string | null;
}

export interface KitV1LineMark {
  mark: "line";
  points: Array<{ x: number; y: number; label?: string | null }>;
  dashed?: boolean;
  color?: KitV1AdaptiveColor | null;
  threshold?: number | null;
}

export type KitV1Mark =
  | KitV1PictureMark
  | KitV1WordMark
  | KitV1NumberMark
  | KitV1BarMark
  | KitV1TileMark
  | KitV1RingMark
  | KitV1DotMark
  | KitV1LineMark;

export interface KitV1CellProvenance {
  market_id: number;
  outcome_id?: number | null;
}

export interface KitV1StackItem {
  id: string;
  sport_key?: string;
  marks: KitV1Mark[];
  sub_marks?: KitV1Mark[];
  route?: KitV1Route;
  provenance?: KitV1CellProvenance;
  divider_after?: { style?: string; label?: string } | null;
}

export interface KitV1StackBody {
  single_sport_key?: string;
  header_layout?: "banner" | "split" | "none";
  header_marks?: KitV1Mark[];
  items: KitV1StackItem[];
  footer_marks?: KitV1Mark[];
}

export interface KitV1GridCell {
  column_key: string;
  marks: KitV1Mark[];
  route?: KitV1Route;
  provenance?: KitV1CellProvenance;
}

export interface KitV1GridRow {
  id: string;
  leading: KitV1Mark[];
  cells: KitV1GridCell[];
}

export interface KitV1GridBody {
  leading_label?: string;
  show_column_headers: boolean;
  row_layout: "matrix" | "stacked_cells";
  columns: Array<{ key: string; label: string }>;
  rows: KitV1GridRow[];
  footer_marks?: KitV1Mark[];
}

export interface KitV1CalendarDay {
  date_key: string;
  daily_pct?: number;
  marks: KitV1Mark[];
}

export interface KitV1CalendarBody {
  header_marks?: KitV1Mark[];
  days: KitV1CalendarDay[];
  footer_marks?: KitV1Mark[];
}

export interface KitV1AxisSeries {
  id: string;
  leading?: KitV1Mark[];
  marks: KitV1Mark[];
  provenance?: KitV1CellProvenance;
}

export interface KitV1AxisBody {
  scale: {
    scale_kind: "percent" | "numeric" | "time";
    unit: string;
    min: number;
    max: number;
    ticks: Array<{ x: number; label: string }>;
  };
  highlight_band?: { lo: number; hi: number; label: string } | null;
  marks?: KitV1Mark[];
  series?: KitV1AxisSeries[];
  summary_marks?: KitV1Mark[];
  footer_marks?: KitV1Mark[];
}

export type KitV1Body =
  | KitV1StackBody
  | KitV1GridBody
  | KitV1CalendarBody
  | KitV1AxisBody;

export interface KitV1CardSpec {
  kit_version: 1;
  id: string;
  layout: KitV1Layout | null;
  variant: string | null;
  kicker?: string;
  common_headline?: string;
  stat_caption?: string;
  source_mark?: KitV1SourceMark;
  route?: KitV1Route;
  footnote?: string | null;
  disclosure?: string | null;
  refusal_reason: string | null;
  fallback_today?: boolean;
  body?: KitV1Body;
}

export interface KitV1PreviewResponse {
  kit_version: number;
  count: number;
  items: KitV1CardSpec[];
  refusals: Array<{ title: string; spec: KitV1CardSpec }>;
}
