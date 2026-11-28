/** Types and pure validation/draft helpers for /admin/cu-labeling. */

export type CuSplit = "practice" | "sealed" | "dev";
export type CuRole = "primary" | "second" | "tiebreak";
export type CuScope = "shared_100" | "all";
export type CuSubjectMode = "candidate" | "custom" | "none_of_these" | "not_sure";
export type CuEventDateMode = "date" | "no_single_day" | "cannot_tell" | "";

export const EVENT_DATE_CANNOT_TELL = "cannot_tell";

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

export interface CuFactLabelDraft {
  subjectMode: CuSubjectMode;
  selectedCandidates: string[];
  customSubject: string;
  eventDateMode: CuEventDateMode;
  eventDate: string;
  geography: string;
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
}

export interface CuPracticeFeedbackField {
  field: string;
  label: string;
  matched: boolean;
  your_answer: string;
  right_answer: string;
}

export interface CuPracticeFeedback {
  market_id: number;
  all_facts_matched: boolean;
  fields: CuPracticeFeedbackField[];
  typical_stakes: [number, number];
  typical_breadth: [number, number];
  explanation: string;
}

export interface CuPracticeStatus {
  required: number;
  completed: number;
  unlocked_sealed: boolean;
  completed_ids: number[];
  practice_card_ids: number[];
}

export interface CuQueueItem {
  market_id: number;
  title: string;
  source: string;
  category: string;
  draw_bucket?: string | null;
  rules_text: string;
  linked_start?: string | null;
  resolution_date?: string | null;
  venue_url: string;
  venue_link_label: string;
  outcomes: CuQueueOutcome[];
  outcome_names: string[];
  subject_candidates: string[];
  own_label: Record<string, unknown> | null;
  practice_feedback?: CuPracticeFeedback | null;
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
  sealed_locked: boolean;
  practice_status: CuPracticeStatus;
  total_in_scope: number;
  completed_by_rater: number;
  remaining: number;
  items: CuQueueItem[];
}

export interface CuLabelSubmitResponse {
  saved: boolean;
  label: Record<string, unknown>;
  practice_feedback?: CuPracticeFeedback | null;
  practice_status?: CuPracticeStatus;
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
    eventDateMode: "",
    eventDate: "",
    geography: "",
    stakes: null,
    breadth: null,
    evidenceNote: "",
  };
}

export function normalizeRaterName(raw: string): string {
  return raw.trim().replace(/\s+/g, " ");
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

export function formatEventStartSentence(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim()) return null;
  const parsed = new Date(raw.trim());
  if (Number.isNaN(parsed.getTime())) return null;
  const etDate = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
  return `Event starts ${etDate} (US Eastern).`;
}

export function formatPeerEventDate(
  eventDateAnswer: string | null | undefined,
  noSingleDay: boolean
): string {
  if (noSingleDay) return "No single day";
  if ((eventDateAnswer || "").trim().toLowerCase() === EVENT_DATE_CANNOT_TELL) {
    return "Cannot tell from this card";
  }
  return eventDateAnswer || "blank";
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
      return {
        ok: false,
        error: "Select at least one person/team chip, Custom entry, 'None of these', or 'Not sure'.",
      };
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

  let eventDateAnswer: string | null = null;
  let noSingleDay = false;
  if (draft.eventDateMode === "no_single_day") {
    noSingleDay = true;
    eventDateAnswer = null;
  } else if (draft.eventDateMode === "cannot_tell") {
    noSingleDay = false;
    eventDateAnswer = EVENT_DATE_CANNOT_TELL;
  } else if (draft.eventDateMode === "date") {
    const cleaned = draft.eventDate.trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(cleaned)) {
      return {
        ok: false,
        error: "Pick a calendar date (YYYY-MM-DD), 'No single day', or 'Cannot tell from this card'.",
      };
    }
    eventDateAnswer = cleaned;
  } else {
    return {
      ok: false,
      error: "Choose 'Specific day', 'No single day', or 'Cannot tell from this card' for the event's own day.",
    };
  }

  const geography = draft.geography.trim();
  if (!geography) {
    return { ok: false, error: "Choose one option under Where before saving." };
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
      event_date_answer: eventDateAnswer,
      no_single_day: noSingleDay,
      geography_answer: geography,
      // Taste scores are never submitted or tie-broken in tie-break mode.
      stakes: role === "tiebreak" ? null : draft.stakes,
      breadth: role === "tiebreak" ? null : draft.breadth,
      evidence_note: draft.evidenceNote.trim() || null,
    },
  };
}
