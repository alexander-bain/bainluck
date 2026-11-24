export interface MemberArtSpec {
  url: string | null;
  kind: string;
  presentation: "logo" | "portrait" | "poster";
  detail: string;
  accent_color: string;
  initials: string;
  short_label: string;
  canonical_name: string;
}

export interface TruthCheckItem {
  check_id: string;
  passed: boolean;
  reason: string;
  observed: Record<string, unknown>;
}

export interface FallbackRowSpec {
  label: string;
  short_label: string;
  role: string | null;
  pct: number;
  pct_label: string;
  art: MemberArtSpec;
}

export interface GridCellSpec {
  col_key: string;
  col_label: string;
  pct: number;
  pct_label: string;
  alias_tag?: string | null;
  listed?: boolean;
  is_row_peak?: boolean;
  is_col_peak?: boolean;
}

export interface GridRowSpec {
  name: string;
  short_label: string;
  art: MemberArtSpec;
  cells: GridCellSpec[];
}

export interface GridOfCellsBody {
  columns: { key: string; label: string }[];
  rows: GridRowSpec[];
  highlight_mode: "row_peak" | "col_peak";
}

export interface SharedScaleBin {
  label: string;
  lo: number;
  hi: number;
  open_low: boolean;
  open_high: boolean;
  pct: number;
  pct_label: string;
}

export interface SharedScaleSeries {
  id: string;
  name: string;
  short_label: string;
  art: MemberArtSpec;
  unit: string;
  tone: string;
  peak_label: string;
  bins: SharedScaleBin[];
}

export interface DeadlinePoint {
  date: string;
  pct: number;
  pct_label: string;
}

export interface DeadlineRaceSeries {
  id: string;
  name: string;
  short_label: string;
  art: MemberArtSpec;
  tone: string;
  points: DeadlinePoint[];
}

export interface OneAxisBody {
  axis_min?: number;
  axis_max?: number;
  axis_unit?: string;
  ticks?: number[];
  series?: SharedScaleSeries[] | DeadlineRaceSeries[];
  dates?: string[];
  ref_line_pct?: number;
  crossover_note?: string;
  subject?: string;
  art?: MemberArtSpec;
  points?: DeadlinePoint[];
}

export interface CalendarTileSpec {
  date_label: string;
  month: string;
  day_num: number;
  intensity: number;
  is_peak: boolean;
  daily_number_label: string | null;
}

export interface CalendarStripBody {
  art: MemberArtSpec;
  decision_367_daily_numbers_enabled: boolean;
  earlier_label: string;
  later_label: string;
  peak_summary: string;
  tiles: CalendarTileSpec[];
}

export interface CastingCoLeader {
  name: string;
  pct: number;
  pct_label: string;
  art: MemberArtSpec;
}

export interface CastingRowSpec {
  role: string;
  leader: string;
  short_label: string;
  pct: number;
  pct_label: string;
  certainty: string;
  is_tie: boolean;
  art: MemberArtSpec;
  co_leader: CastingCoLeader | null;
}

export interface CastingSheetBody {
  rows: CastingRowSpec[];
}

export interface BubbleTeamSpec {
  name: string;
  code: string;
  conference: string;
  pct: number;
  pct_label: string;
  art: MemberArtSpec;
  rank?: number;
  above_cut?: boolean;
  at_cut_tie?: boolean;
  likelihood_band?: "safe" | "bubble" | "chase" | "longshot";
}

export interface ConferenceCutSpec {
  conference: string;
  total_teams: number;
  places: number;
  cut_label: string;
  has_cut_tie: boolean;
  tie_rule_note: string | null;
  teams: BubbleTeamSpec[];
}

export interface BubbleAndCutBody {
  bubble_low?: number;
  bubble_high?: number;
  counts?: { look_out: number; in_doubt: number; look_in: number };
  teams?: BubbleTeamSpec[];
  focus_teams?: BubbleTeamSpec[];
  conferences?: ConferenceCutSpec[];
}

export interface FormsLabCardEnvelope {
  card_id: string;
  look_id: "grid_of_cells" | "one_axis" | "calendar_strip" | "casting_sheet" | "bubble_and_cut";
  form_variant:
    | "places_grid"
    | "scoreboard_grid"
    | "shared_scale"
    | "deadline_race"
    | "the_climb"
    | "calendar_strip"
    | "casting_sheet"
    | "bubble_line"
    | "the_cut";
  preview_only: boolean;
  is_refusal_demo: boolean;
  topic: string;
  title: string;
  subtitle: string;
  footnote: string;
  source_label: string;
  status: "draw" | "refused_fallback_rows";
  refusal_reasons: string[];
  truth_checks: TruthCheckItem[];
  body: Record<string, unknown>;
  fallback_rows: FallbackRowSpec[];
}

export interface FormsLabRealSetRef {
  set_name: string;
  topic: string;
  source_ref: string;
}

export interface FormsLabLookGroup {
  look_id: FormsLabCardEnvelope["look_id"];
  cards: FormsLabCardEnvelope[];
  real_sets: FormsLabRealSetRef[];
}

export interface FormsLabBatch1PreviewPayload {
  preview_only: boolean;
  public_release: boolean;
  decision_367_daily_numbers_enabled: boolean;
  look_order: FormsLabCardEnvelope["look_id"][];
  looks: FormsLabLookGroup[];
}
