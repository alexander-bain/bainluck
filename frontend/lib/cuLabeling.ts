/** Types and pure validation/draft helpers for /admin/cu-labeling. */

export type CuSplit = "sealed" | "dev";
export type CuRole = "primary" | "second" | "tiebreak";
export type CuScope = "shared_100" | "all";
export type CuStructure = "ladder" | "dated_bucket" | "neither";
export type CuSubjectMode = "candidate" | "custom" | "none_of_these" | "not_sure";

export const DEFAULT_CLAIM_MEASURES: readonly string[] = [
  "appointment",
  "approval_rating",
  "asset_price",
  "atp_points",
  "award_result",
  "bankruptcy_filing",
  "box_office_revenue",
  "ceasefire",
  "close_price",
  "daily_views",
  "data_center_moratorium",
  "economic_growth",
  "election_result",
  "employment",
  "event_count",
  "exchange_rate",
  "goals",
  "high_temperature",
  "housing_starts",
  "index_close",
  "inflation_rate",
  "interest_rate",
  "low_temperature",
  "magnitude",
  "market_cap",
  "nomination",
  "points",
  "poll_share",
  "precipitation",
  "price_high",
  "price_low",
  "price_record_high",
  "price_record_low",
  "ranking",
  "release_date",
  "result",
  "revenue",
  "rt_score",
  "runs",
  "snowfall",
  "subscriber_count",
  "touchdowns",
  "tweet_count",
  "unemployment_rate",
  "victory_margin",
  "vote_share",
  "wins",
];

export const DEFAULT_CLAIM_COMPARATORS: readonly string[] = [
  "gte",
  "gt",
  "lte",
  "lt",
  "eq",
  "ne",
  "range",
];

export const DEFAULT_CLAIM_HORIZON_KINDS: readonly string[] = [
  "intraday",
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "annual",
  "multi_year",
  "open_ended",
];

export const MEASURE_GROUPS: ReadonlyArray<{
  group: string;
  options: ReadonlyArray<{ value: string; label: string }>;
}> = [
  {
    group: "Prices & Markets",
    options: [
      { value: "asset_price", label: "Asset price (price at a point in time)" },
      { value: "close_price", label: "Closing price (end-of-day price)" },
      { value: "price_high", label: "Highest price reached (peak during a period)" },
      { value: "price_low", label: "Lowest price reached (bottom during a period)" },
      { value: "price_record_high", label: "All-time record high price" },
      { value: "price_record_low", label: "All-time record low price" },
      { value: "index_close", label: "Stock index closing level (e.g. S&P 500 close)" },
      { value: "market_cap", label: "Company market value (market cap)" },
      { value: "exchange_rate", label: "Currency exchange rate" },
    ],
  },
  {
    group: "Economy & Business",
    options: [
      { value: "interest_rate", label: "Central bank interest rate" },
      { value: "inflation_rate", label: "Inflation rate (price growth)" },
      { value: "unemployment_rate", label: "Unemployment rate" },
      { value: "economic_growth", label: "Economic growth rate (GDP)" },
      { value: "employment", label: "Jobs added or employment count" },
      { value: "housing_starts", label: "New housing construction starts" },
      { value: "revenue", label: "Company revenue or sales" },
      { value: "bankruptcy_filing", label: "Bankruptcy filing" },
    ],
  },
  {
    group: "Politics & World Events",
    options: [
      { value: "election_result", label: "Election or referendum winner" },
      { value: "vote_share", label: "Share of the vote (%)" },
      { value: "poll_share", label: "Opinion poll percentage" },
      { value: "approval_rating", label: "Leader or government approval rating" },
      { value: "nomination", label: "Party or official nomination" },
      { value: "appointment", label: "Government or court appointment" },
      { value: "ceasefire", label: "Ceasefire or peace agreement" },
    ],
  },
  {
    group: "Sports Stats",
    options: [
      { value: "wins", label: "Games or matches won" },
      { value: "points", label: "Points scored" },
      { value: "goals", label: "Goals scored" },
      { value: "runs", label: "Runs scored (baseball or cricket)" },
      { value: "touchdowns", label: "Touchdowns scored" },
      { value: "atp_points", label: "ATP tennis ranking points" },
    ],
  },
  {
    group: "Weather & Nature",
    options: [
      { value: "high_temperature", label: "Daily high temperature" },
      { value: "low_temperature", label: "Daily low temperature" },
      { value: "precipitation", label: "Rain or total precipitation" },
      { value: "snowfall", label: "Snowfall amount" },
      { value: "magnitude", label: "Earthquake magnitude" },
    ],
  },
  {
    group: "Tech, Media & Culture",
    options: [
      { value: "release_date", label: "Release date (product, film, game, or model)" },
      { value: "subscriber_count", label: "Subscriber or listener count" },
      { value: "daily_views", label: "Daily video or stream views" },
      { value: "tweet_count", label: "Number of social media posts (tweets)" },
      { value: "box_office_revenue", label: "Movie box office ticket sales" },
      { value: "rt_score", label: "Rotten Tomatoes score" },
      { value: "award_result", label: "Award or prize winner" },
      { value: "data_center_moratorium", label: "Data center pause or moratorium" },
    ],
  },
  {
    group: "General Outcomes & Counts",
    options: [
      { value: "event_count", label: "Number of times something happens" },
      { value: "ranking", label: "Chart, poll, or league ranking" },
      { value: "victory_margin", label: "Margin of victory" },
      { value: "result", label: "Outcome or match result" },
    ],
  },
];

export const MEASURE_LABELS: Record<string, string> = Object.fromEntries(
  MEASURE_GROUPS.flatMap((grp) => grp.options.map((opt) => [opt.value, opt.label]))
);

// Alphabetical ISO 3166-1 alpha-2 country list (excluding US, which has its own button).
export const COUNTRY_OPTIONS: ReadonlyArray<{ code: string; name: string }> = [
  { code: "AF", name: "Afghanistan" },
  { code: "AL", name: "Albania" },
  { code: "DZ", name: "Algeria" },
  { code: "AD", name: "Andorra" },
  { code: "AO", name: "Angola" },
  { code: "AG", name: "Antigua and Barbuda" },
  { code: "AR", name: "Argentina" },
  { code: "AM", name: "Armenia" },
  { code: "AU", name: "Australia" },
  { code: "AT", name: "Austria" },
  { code: "AZ", name: "Azerbaijan" },
  { code: "BS", name: "Bahamas" },
  { code: "BH", name: "Bahrain" },
  { code: "BD", name: "Bangladesh" },
  { code: "BB", name: "Barbados" },
  { code: "BY", name: "Belarus" },
  { code: "BE", name: "Belgium" },
  { code: "BZ", name: "Belize" },
  { code: "BJ", name: "Benin" },
  { code: "BT", name: "Bhutan" },
  { code: "BO", name: "Bolivia" },
  { code: "BA", name: "Bosnia and Herzegovina" },
  { code: "BW", name: "Botswana" },
  { code: "BR", name: "Brazil" },
  { code: "BN", name: "Brunei" },
  { code: "BG", name: "Bulgaria" },
  { code: "BF", name: "Burkina Faso" },
  { code: "BI", name: "Burundi" },
  { code: "CV", name: "Cabo Verde" },
  { code: "KH", name: "Cambodia" },
  { code: "CM", name: "Cameroon" },
  { code: "CA", name: "Canada" },
  { code: "CF", name: "Central African Republic" },
  { code: "TD", name: "Chad" },
  { code: "CL", name: "Chile" },
  { code: "CN", name: "China" },
  { code: "CO", name: "Colombia" },
  { code: "KM", name: "Comoros" },
  { code: "CG", name: "Congo" },
  { code: "CD", name: "DR Congo" },
  { code: "CR", name: "Costa Rica" },
  { code: "CI", name: "Cote d'Ivoire" },
  { code: "HR", name: "Croatia" },
  { code: "CU", name: "Cuba" },
  { code: "CY", name: "Cyprus" },
  { code: "CZ", name: "Czech Republic" },
  { code: "DK", name: "Denmark" },
  { code: "DJ", name: "Djibouti" },
  { code: "DM", name: "Dominica" },
  { code: "DO", name: "Dominican Republic" },
  { code: "EC", name: "Ecuador" },
  { code: "EG", name: "Egypt" },
  { code: "SV", name: "El Salvador" },
  { code: "GQ", name: "Equatorial Guinea" },
  { code: "ER", name: "Eritrea" },
  { code: "EE", name: "Estonia" },
  { code: "SZ", name: "Eswatini" },
  { code: "ET", name: "Ethiopia" },
  { code: "FJ", name: "Fiji" },
  { code: "FI", name: "Finland" },
  { code: "FR", name: "France" },
  { code: "GA", name: "Gabon" },
  { code: "GM", name: "Gambia" },
  { code: "GE", name: "Georgia" },
  { code: "DE", name: "Germany" },
  { code: "GH", name: "Ghana" },
  { code: "GR", name: "Greece" },
  { code: "GD", name: "Grenada" },
  { code: "GT", name: "Guatemala" },
  { code: "GN", name: "Guinea" },
  { code: "GW", name: "Guinea-Bissau" },
  { code: "GY", name: "Guyana" },
  { code: "HT", name: "Haiti" },
  { code: "HN", name: "Honduras" },
  { code: "HK", name: "Hong Kong" },
  { code: "HU", name: "Hungary" },
  { code: "IS", name: "Iceland" },
  { code: "IN", name: "India" },
  { code: "ID", name: "Indonesia" },
  { code: "IR", name: "Iran" },
  { code: "IQ", name: "Iraq" },
  { code: "IE", name: "Ireland" },
  { code: "IL", name: "Israel" },
  { code: "IT", name: "Italy" },
  { code: "JM", name: "Jamaica" },
  { code: "JP", name: "Japan" },
  { code: "JO", name: "Jordan" },
  { code: "KZ", name: "Kazakhstan" },
  { code: "KE", name: "Kenya" },
  { code: "KI", name: "Kiribati" },
  { code: "XK", name: "Kosovo" },
  { code: "KW", name: "Kuwait" },
  { code: "KG", name: "Kyrgyzstan" },
  { code: "LA", name: "Laos" },
  { code: "LV", name: "Latvia" },
  { code: "LB", name: "Lebanon" },
  { code: "LS", name: "Lesotho" },
  { code: "LR", name: "Liberia" },
  { code: "LY", name: "Libya" },
  { code: "LI", name: "Liechtenstein" },
  { code: "LT", name: "Lithuania" },
  { code: "LU", name: "Luxembourg" },
  { code: "MO", name: "Macao" },
  { code: "MG", name: "Madagascar" },
  { code: "MW", name: "Malawi" },
  { code: "MY", name: "Malaysia" },
  { code: "MV", name: "Maldives" },
  { code: "ML", name: "Mali" },
  { code: "MT", name: "Malta" },
  { code: "MH", name: "Marshall Islands" },
  { code: "MR", name: "Mauritania" },
  { code: "MU", name: "Mauritius" },
  { code: "MX", name: "Mexico" },
  { code: "FM", name: "Micronesia" },
  { code: "MD", name: "Moldova" },
  { code: "MC", name: "Monaco" },
  { code: "MN", name: "Mongolia" },
  { code: "ME", name: "Montenegro" },
  { code: "MA", name: "Morocco" },
  { code: "MZ", name: "Mozambique" },
  { code: "MM", name: "Myanmar" },
  { code: "NA", name: "Namibia" },
  { code: "NR", name: "Nauru" },
  { code: "NP", name: "Nepal" },
  { code: "NL", name: "Netherlands" },
  { code: "NZ", name: "New Zealand" },
  { code: "NI", name: "Nicaragua" },
  { code: "NE", name: "Niger" },
  { code: "NG", name: "Nigeria" },
  { code: "KP", name: "North Korea" },
  { code: "MK", name: "North Macedonia" },
  { code: "NO", name: "Norway" },
  { code: "OM", name: "Oman" },
  { code: "PK", name: "Pakistan" },
  { code: "PW", name: "Palau" },
  { code: "PS", name: "Palestine" },
  { code: "PA", name: "Panama" },
  { code: "PG", name: "Papua New Guinea" },
  { code: "PY", name: "Paraguay" },
  { code: "PE", name: "Peru" },
  { code: "PH", name: "Philippines" },
  { code: "PL", name: "Poland" },
  { code: "PT", name: "Portugal" },
  { code: "PR", name: "Puerto Rico" },
  { code: "QA", name: "Qatar" },
  { code: "RO", name: "Romania" },
  { code: "RU", name: "Russia" },
  { code: "RW", name: "Rwanda" },
  { code: "KN", name: "Saint Kitts and Nevis" },
  { code: "LC", name: "Saint Lucia" },
  { code: "VC", name: "Saint Vincent and the Grenadines" },
  { code: "WS", name: "Samoa" },
  { code: "SM", name: "San Marino" },
  { code: "ST", name: "Sao Tome and Principe" },
  { code: "SA", name: "Saudi Arabia" },
  { code: "SN", name: "Senegal" },
  { code: "RS", name: "Serbia" },
  { code: "SC", name: "Seychelles" },
  { code: "SL", name: "Sierra Leone" },
  { code: "SG", name: "Singapore" },
  { code: "SK", name: "Slovakia" },
  { code: "SI", name: "Slovenia" },
  { code: "SB", name: "Solomon Islands" },
  { code: "SO", name: "Somalia" },
  { code: "ZA", name: "South Africa" },
  { code: "KR", name: "South Korea" },
  { code: "SS", name: "South Sudan" },
  { code: "ES", name: "Spain" },
  { code: "LK", name: "Sri Lanka" },
  { code: "SD", name: "Sudan" },
  { code: "SR", name: "Suriname" },
  { code: "SE", name: "Sweden" },
  { code: "CH", name: "Switzerland" },
  { code: "SY", name: "Syria" },
  { code: "TW", name: "Taiwan" },
  { code: "TJ", name: "Tajikistan" },
  { code: "TZ", name: "Tanzania" },
  { code: "TH", name: "Thailand" },
  { code: "TL", name: "Timor-Leste" },
  { code: "TG", name: "Togo" },
  { code: "TO", name: "Tonga" },
  { code: "TT", name: "Trinidad and Tobago" },
  { code: "TN", name: "Tunisia" },
  { code: "TR", name: "Turkey" },
  { code: "TM", name: "Turkmenistan" },
  { code: "TV", name: "Tuvalu" },
  { code: "UG", name: "Uganda" },
  { code: "UA", name: "Ukraine" },
  { code: "AE", name: "United Arab Emirates" },
  { code: "GB", name: "United Kingdom" },
  { code: "UY", name: "Uruguay" },
  { code: "UZ", name: "Uzbekistan" },
  { code: "VU", name: "Vanuatu" },
  { code: "VA", name: "Vatican City" },
  { code: "VE", name: "Venezuela" },
  { code: "VN", name: "Vietnam" },
  { code: "YE", name: "Yemen" },
  { code: "ZM", name: "Zambia" },
  { code: "ZW", name: "Zimbabwe" },
];

export const COMPARATOR_LABELS: Record<string, string> = {
  gte: "At least (>=)",
  gt: "More than (>)",
  lte: "At most (<=)",
  lt: "Fewer than (<)",
  eq: "Exactly (=)",
  ne: "Not equal (!=)",
  range: "Between (range)",
  none_of_these: "None of these",
};

export const HORIZON_LABELS: Record<string, string> = {
  intraday: "Same day (intraday)",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  quarterly: "Quarterly",
  annual: "Yearly (annual)",
  multi_year: "Multi-year",
  open_ended: "Open-ended",
  none_of_these: "None of these",
};

export interface CuClaimVocabulary {
  measures: string[];
  comparators: string[];
  horizon_kinds: string[];
  special_options: string[];
}

export interface CuClaimFrameDraft {
  measure: string;
  comparator: string;
  value: string;
  unit: string;
  horizon_kind: string;
  window_date: string;
}

export interface CuFactLabelDraft {
  subjectMode: CuSubjectMode;
  selectedCandidates: string[];
  customSubject: string;
  eventDate: string;
  noSingleDay: boolean;
  geography: string;
  structure: CuStructure | "";
  claim: CuClaimFrameDraft;
  stakes: number | null;
  breadth: number | null;
  evidenceNote: string;
}

export interface CuQueueOutcome {
  name: string;
  prob?: number | null;
}

export interface CuPeerFactAnswer {
  rater: string;
  role: CuRole;
  subjects_answer: { selection_kind: CuSubjectMode; selected: string[] } | null;
  event_date_answer: string | null;
  no_single_day: boolean;
  geography_answer: string | null;
  structure_answer: CuStructure | null;
  claim_frame: Partial<CuClaimFrameDraft> | null;
}

export interface CuQueueItem {
  market_id: number;
  title: string;
  source: string;
  category: string;
  draw_bucket?: string | null;
  rules_text: string;
  resolution_date?: string | null;
  outcomes: CuQueueOutcome[];
  outcome_names: string[];
  subject_candidates: string[];
  own_label: Record<string, unknown> | null;
  pair_complete: boolean;
  peer_labels: CuPeerFactAnswer[];
  disagreeing_fact_fields: string[];
}

export interface CuQueueResponse {
  split: CuSplit;
  role: CuRole;
  scope: CuScope;
  rater: string;
  dataset_file_present: boolean;
  dataset_file_missing_message: string | null;
  claim_vocabulary?: CuClaimVocabulary;
  total_in_scope: number;
  completed_by_rater: number;
  remaining: number;
  items: CuQueueItem[];
}

export interface CuAgreementFieldRow {
  field: string;
  metric: "exact" | "within_1";
  agreed: number;
  total: number;
  agreement_rate: number | null;
  below_80_pct: boolean;
  tiebreak_allowed: boolean;
}

export interface CuAgreementResponse {
  split: CuSplit;
  paired_markets: number;
  needs_tiebreak: number;
  resolved_tiebreaks: number;
  below_80_fields: string[];
  fields: CuAgreementFieldRow[];
}

export const RATER_STORAGE_KEY = "bainluck_cu_fact_rater_name";

export function emptyCuDraft(): CuFactLabelDraft {
  return {
    subjectMode: "candidate",
    selectedCandidates: [],
    customSubject: "",
    eventDate: "",
    noSingleDay: false,
    geography: "",
    structure: "",
    claim: {
      measure: "",
      comparator: "",
      value: "",
      unit: "",
      horizon_kind: "",
      window_date: "",
    },
    stakes: null,
    breadth: null,
    evidenceNote: "",
  };
}

export function normalizeRaterName(raw: string): string {
  return raw.trim().replace(/\s+/g, " ");
}

export function formatMeasureChoiceLabel(measure: string): string {
  if (measure === "none_of_these") return "None of these";
  if (MEASURE_LABELS[measure]) return MEASURE_LABELS[measure];
  return measure
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

export function formatPayoutDateSentence(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim()) return null;
  const trimmed = raw.trim();
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) {
    return `The site pays out on ${trimmed}. That is often not the day of the event.`;
  }
  const month = MONTH_SHORT[parsed.getUTCMonth()];
  const day = parsed.getUTCDate();
  const year = parsed.getUTCFullYear();
  return `The site pays out on ${month} ${day}, ${year}. That is often not the day of the event.`;
}

export function formatPeerClaimFrame(frame: Record<string, unknown> | null | undefined): string {
  if (!frame) return "blank";
  const parts: string[] = [];
  for (const key of ["measure", "comparator", "value", "unit", "horizon_kind", "window_date"]) {
    const val = frame[key];
    if (val !== null && val !== undefined && String(val).trim() !== "") {
      parts.push(`${key}: ${String(val)}`);
    }
  }
  return parts.length > 0 ? parts.join(" · ") : "blank";
}

export function buildSubmissionPayload(params: {
  split: CuSplit;
  role: CuRole;
  rater: string;
  marketId: number;
  draft: CuFactLabelDraft;
}): { ok: true; payload: Record<string, unknown> } | { ok: false; error: string } {
  const rater = normalizeRaterName(params.rater);
  if (!rater || rater.length > 64) {
    return { ok: false, error: "Type your name (1-64 characters) first." };
  }

  const { draft, role, split, marketId } = params;

  let selected: string[] = [];
  if (draft.subjectMode === "candidate") {
    selected = draft.selectedCandidates.map((s) => s.trim()).filter(Boolean);
    if (selected.length === 0) {
      return { ok: false, error: "Select at least one person/team, custom entry, or 'None of these' / 'Not sure'." };
    }
  } else if (draft.subjectMode === "custom") {
    selected = draft.customSubject
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (selected.length === 0) {
      return { ok: false, error: "Enter at least one custom name." };
    }
  }

  if (!draft.noSingleDay && !/^\d{4}-\d{2}-\d{2}$/.test(draft.eventDate.trim())) {
    return { ok: false, error: "Enter YYYY-MM-DD for the event's own day or check 'No single day'." };
  }

  const geography = draft.geography.trim();
  if (!geography) {
    return { ok: false, error: "Select Where ('us', 'global', 'local') or pick a country." };
  }

  if (!draft.structure) {
    return { ok: false, error: "Choose whether this market is a ladder, dated options, or neither." };
  }

  if (role === "tiebreak") {
    if (!draft.evidenceNote.trim()) {
      return { ok: false, error: "Write a short note quoting the evidence before saving." };
    }
  } else {
    if (draft.stakes === null || draft.stakes < 1 || draft.stakes > 5) {
      return { ok: false, error: "Rate how much this matters from 1 to 5." };
    }
    if (draft.breadth === null || draft.breadth < 1 || draft.breadth > 5) {
      return { ok: false, error: "Rate how many people care from 1 to 5." };
    }
  }

  const claimEntries = Object.entries(draft.claim)
    .map(([k, v]) => [k, v.trim()])
    .filter(([, v]) => v.length > 0);
  const claim_frame = claimEntries.length > 0 ? Object.fromEntries(claimEntries) : null;

  return {
    ok: true,
    payload: {
      dataset_split: split,
      market_id: marketId,
      rater,
      role,
      subjects_answer: {
        selection_kind: draft.subjectMode,
        selected,
      },
      event_date_answer: draft.noSingleDay ? null : draft.eventDate.trim(),
      no_single_day: draft.noSingleDay,
      geography_answer: geography,
      structure_answer: draft.structure,
      claim_frame,
      // Taste scores are never submitted or tie-broken in tie-break mode.
      stakes: role === "tiebreak" ? null : draft.stakes,
      breadth: role === "tiebreak" ? null : draft.breadth,
      evidence_note: draft.evidenceNote.trim() || null,
    },
  };
}
